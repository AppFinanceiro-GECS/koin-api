"""
Liga um comprovante de pagamento de fatura à fatura em aberto do cartão.

O comprovante traz o banco do cartão (às vezes o final) e o valor pago. A API só sugere:
quem marca a fatura como paga é a pessoa, pelo app, escolhendo a conta de origem
(POST /invoices/{id}/pay). O comprovante nunca cria cartão nem fatura.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import today_br
from app.models.credit_card_invoice import CreditCardInvoice, InvoiceStatus
from app.models.user import User
from app.modules.credit_cards.services.card_matching import (
    AMBIGUOUS,
    MATCHED,
    _label,
    match_card,
    visible_cards,
)

# status de InvoicePaymentMatch
PAYMENT_MATCHED = "matched"  # uma fatura em aberto: o app oferece marcar como paga
PAYMENT_AMBIGUOUS = "ambiguous"  # mais de uma fatura serve: o app pede para escolher
PAYMENT_ALREADY_PAID = "already_paid"  # a fatura com esse valor já está paga
PAYMENT_NONE = "none"  # nenhuma fatura em aberto bate

CENT = Decimal("0.01")


@dataclass
class InvoiceCandidate:
    invoice_id: int
    credit_card_id: int
    credit_card_name: str
    reference_month: int
    reference_year: int
    due_date: date
    total_amount: float
    remaining_amount: float


@dataclass
class InvoicePaymentMatch:
    status: str
    amount_paid: float | None = None
    payment_date: date | None = None
    # a fatura sugerida (matched / already_paid)
    invoice: InvoiceCandidate | None = None
    # o valor pago fecha com o total ou com o que falta pagar da fatura sugerida
    amount_matches: bool = False
    # faturas em aberto que a pessoa pode escolher no lugar da sugerida
    candidates: list[InvoiceCandidate] = field(default_factory=list)


def _amount_paid(extracted: dict) -> Decimal | None:
    total = extracted.get("total_amount")
    if not total:
        total = sum(abs(item.get("amount") or 0) for item in extracted.get("items") or [])
    try:
        value = Decimal(str(total)).quantize(CENT)
    except Exception:
        return None
    return value if value > 0 else None


def _payment_date(extracted: dict) -> date | None:
    for item in extracted.get("items") or []:
        raw = str(item.get("date") or "")[:10]
        try:
            return date.fromisoformat(raw)
        except ValueError:
            continue
    return None


def _close(a: Decimal, b: Decimal | None) -> bool:
    return b is not None and abs(a - b) <= CENT


async def match_invoice_payment(
    db: AsyncSession, user: User, extracted: dict | None
) -> InvoicePaymentMatch:
    extracted = extracted or {}
    amount = _amount_paid(extracted)
    paid_on = _payment_date(extracted)
    if amount is None:
        return InvoicePaymentMatch(status=PAYMENT_NONE, payment_date=paid_on)

    cards = {card.id: (card, account) for card, account in await visible_cards(db, user)}
    card_data = extracted.get("payment_card") or extracted.get("card_info") or {}
    names_card = any(card_data.get(k) for k in ("card_issuer", "card_bank", "card_last_digits"))

    # 1. de qual cartão: pelo banco (e pelo final, quando aparece)
    card_ids: list[int]
    if names_card:
        match = await match_card(db, user, card_data, "comprovante_fatura")
        if match.status == MATCHED:
            card_ids = [match.credit_card_id]
        elif match.status == AMBIGUOUS:
            card_ids = match.candidate_ids
        else:
            # o comprovante cita um banco que não tem cartão cadastrado: não chuta outro
            return InvoicePaymentMatch(
                status=PAYMENT_NONE, amount_paid=float(amount), payment_date=paid_on
            )
    else:
        card_ids = list(cards)
    if not card_ids:
        return InvoicePaymentMatch(
            status=PAYMENT_NONE, amount_paid=float(amount), payment_date=paid_on
        )

    # só faturas da própria pessoa: é o que POST /invoices/{id}/pay aceita
    result = await db.execute(
        select(CreditCardInvoice)
        .where(
            CreditCardInvoice.credit_card_id.in_(card_ids),
            CreditCardInvoice.user_id == user.id,
        )
        .order_by(CreditCardInvoice.due_date, CreditCardInvoice.id)
    )
    invoices = list(result.scalars().all())

    def candidate(inv: CreditCardInvoice) -> InvoiceCandidate:
        card, account = cards[inv.credit_card_id]
        return InvoiceCandidate(
            invoice_id=inv.id,
            credit_card_id=inv.credit_card_id,
            credit_card_name=_label(card, account),
            reference_month=inv.reference_month,
            reference_year=inv.reference_year,
            due_date=inv.due_date,
            total_amount=float(inv.total_amount or 0),
            remaining_amount=float(inv.remaining_amount or 0),
        )

    unpaid = [
        inv
        for inv in invoices
        if inv.status != InvoiceStatus.PAID.value
        and inv.credit_card_id in cards
        and (inv.remaining_amount or 0) > 0
    ]
    base = InvoicePaymentMatch(
        status=PAYMENT_NONE,
        amount_paid=float(amount),
        payment_date=paid_on,
        candidates=[candidate(inv) for inv in unpaid],
    )

    # 2. pelo valor: o total da fatura ou o que falta pagar
    exact = [
        inv
        for inv in unpaid
        if _close(amount, inv.remaining_amount) or _close(amount, inv.total_amount)
    ]
    if len(exact) == 1:
        base.status = PAYMENT_MATCHED
        base.invoice = candidate(exact[0])
        base.amount_matches = True
        return base
    if len(exact) > 1:
        base.status = PAYMENT_AMBIGUOUS
        base.candidates = [candidate(inv) for inv in exact]
        return base

    # 3. cartão certo, valor diferente (pagamento parcial ou fatura com outro total):
    #    sugere a fatura que vence mais perto da data do pagamento
    if len(card_ids) == 1 and unpaid:
        reference = paid_on or today_br()
        nearest = min(unpaid, key=lambda inv: abs((inv.due_date - reference).days))
        base.status = PAYMENT_MATCHED
        base.invoice = candidate(nearest)
        return base

    # 4. o mesmo comprovante de novo: a fatura com esse valor já está paga
    paid = [
        inv
        for inv in invoices
        if inv.status == InvoiceStatus.PAID.value
        and inv.credit_card_id in cards
        and (_close(amount, inv.paid_amount) or _close(amount, inv.total_amount))
    ]
    if paid:
        base.status = PAYMENT_ALREADY_PAID
        base.invoice = candidate(paid[-1])
        return base

    # 5. sem banco e sem valor que feche: a pessoa escolhe entre as faturas em aberto
    if unpaid:
        base.status = PAYMENT_AMBIGUOUS
    return base
