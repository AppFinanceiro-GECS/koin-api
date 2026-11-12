"""
Reconhece o cartão de uma fatura lida pela IA.

Só a fatura cria cartão: ela traz banco, final, fechamento, vencimento e limite.
Comprovantes e cupons nunca criam cartão, no máximo apontam para um já cadastrado
pelo final.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.credit_card import CreditCard
from app.models.document import DocumentType
from app.models.household import HouseholdMember
from app.models.user import User

MATCHED = "matched"  # um cartão cadastrado bate com a fatura
NEW = "new"  # fatura de um cartão que ainda não existe: o app oferece cadastrar
AMBIGUOUS = "ambiguous"  # mais de um cartão bate: o app pede para escolher
NONE = "none"  # documento sem dados de cartão


def _norm(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _digits(value: str | None) -> str | None:
    if not value:
        return None
    only = "".join(ch for ch in str(value) if ch.isdigit())
    return only[-4:] if len(only) >= 4 else None


def _day(value) -> int | None:
    try:
        day = int(value)
    except (TypeError, ValueError):
        return None
    return day if 1 <= day <= 31 else None


def _day_from_date(value: str | None) -> int | None:
    if not value or len(str(value)) < 10:
        return None
    return _day(str(value)[8:10])


def _float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


@dataclass
class CardSuggestion:
    """Dados para cadastrar o cartão a partir da fatura"""

    name: str
    last_four_digits: str | None
    bank_id: str | None
    card_brand: str | None
    closing_day: int | None
    due_day: int | None
    credit_limit: float | None


@dataclass
class CardMatch:
    status: str
    credit_card_id: int | None = None
    credit_card_name: str | None = None
    candidate_ids: list[int] = field(default_factory=list)
    suggestion: CardSuggestion | None = None


def is_invoice(document_type: str | None, card_info: dict | None) -> bool:
    if document_type and DocumentType.from_string(document_type) == DocumentType.FATURA_CARTAO:
        return True
    # documentos antigos sem tipo: fatura é o que traz fechamento ou vencimento
    return bool(card_info) and bool(
        card_info.get("closing_day")
        or card_info.get("closing_date")
        or card_info.get("due_day")
        or card_info.get("due_date")
    )


def suggestion_from_card_info(card_info: dict) -> CardSuggestion:
    digits = _digits(card_info.get("card_last_digits"))
    bank = card_info.get("card_bank") or (card_info.get("card_issuer") or "").title() or None
    name = (card_info.get("card_name") or bank or "Cartão").strip()[:50]
    brand = card_info.get("card_brand")
    return CardSuggestion(
        name=name,
        last_four_digits=digits,
        bank_id=(_norm(card_info.get("card_issuer")) or None),
        card_brand=brand.title() if isinstance(brand, str) and brand else None,
        closing_day=_day(card_info.get("closing_day"))
        or _day_from_date(card_info.get("closing_date")),
        due_day=_day(card_info.get("due_day")) or _day_from_date(card_info.get("due_date")),
        credit_limit=_float(card_info.get("credit_limit")),
    )


async def visible_cards(db: AsyncSession, user: User) -> list[tuple[CreditCard, Account]]:
    """Mesma regra da listagem de cartões: pessoais do usuário e compartilhados da família"""
    household_ids: list[int] = []
    if user.license_id:
        result = await db.execute(
            select(HouseholdMember.user_id).where(HouseholdMember.license_id == user.license_id)
        )
        household_ids = list(result.scalars().all())

    query = select(CreditCard, Account).join(Account, CreditCard.account_id == Account.id)
    if household_ids:
        query = query.where(
            or_(
                and_(CreditCard.user_id == user.id, Account.ownership_type == "personal"),
                and_(
                    CreditCard.user_id.in_(household_ids),
                    Account.ownership_type == "household",
                ),
            )
        )
    else:
        query = query.where(CreditCard.user_id == user.id)
    result = await db.execute(query.order_by(CreditCard.id))
    return [(card, account) for card, account in result.all()]


def _bank_matches(card: CreditCard, account: Account, card_info: dict) -> bool:
    wanted = {
        _norm(card_info.get("card_issuer")),
        _norm(card_info.get("card_bank")),
    } - {""}
    if not wanted:
        return False
    haystack = " ".join(
        _norm(v) for v in (card.bank_id, card.nickname, account.name, card.card_variant) if v
    )
    return any(w in haystack or (card.bank_id and _norm(card.bank_id) in w) for w in wanted)


def _label(card: CreditCard, account: Account) -> str:
    base = card.nickname or account.name or "Cartão"
    return f"{base} final {card.last_four_digits}" if card.last_four_digits else base


async def match_card(
    db: AsyncSession,
    user: User,
    card_info: dict | None,
    document_type: str | None,
) -> CardMatch:
    if not card_info:
        return CardMatch(status=NONE)

    cards = await visible_cards(db, user)
    active = [(c, a) for c, a in cards if c.is_active] or cards
    digits = _digits(card_info.get("card_last_digits"))

    candidates: list[tuple[CreditCard, Account]] = []
    if digits:
        candidates = [(c, a) for c, a in active if c.last_four_digits == digits]
        if len(candidates) > 1:
            by_bank = [(c, a) for c, a in candidates if _bank_matches(c, a, card_info)]
            candidates = by_bank or candidates
        if not candidates:
            # cartão cadastrado à mão sem o final: o banco basta para não duplicar
            candidates = [
                (c, a)
                for c, a in active
                if not c.last_four_digits and _bank_matches(c, a, card_info)
            ]
    else:
        # sem o final, só aceita o banco quando há um único cartão dele
        candidates = [(c, a) for c, a in active if _bank_matches(c, a, card_info)]

    if len(candidates) == 1:
        card, account = candidates[0]
        return CardMatch(
            status=MATCHED, credit_card_id=card.id, credit_card_name=_label(card, account)
        )
    if len(candidates) > 1:
        return CardMatch(status=AMBIGUOUS, candidate_ids=[c.id for c, _ in candidates])

    if is_invoice(document_type, card_info):
        return CardMatch(status=NEW, suggestion=suggestion_from_card_info(card_info))
    return CardMatch(status=NONE)
