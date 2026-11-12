"""
Quanto do cartão já está comprometido nos próximos meses.

Soma as parcelas que faltam de cada compra parcelada ativa, no mês da fatura em que cada
parcela cai (respeitando o fechamento do cartão). Não inclui compras que ainda não
aconteceram nem assinaturas: é o que a pessoa já deve, não uma previsão de gasto.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.credit_card import CreditCard
from app.models.household import HouseholdMember
from app.models.installment import InstallmentSeries, InstallmentSeriesStatus
from app.models.user import User
from app.modules.credit_cards.services.invoice_service import InvoiceService


class OutlookItem(BaseModel):
    """Uma parcela que cai na fatura do mês"""

    series_id: int
    description: str
    installment_number: int
    installment_count: int
    amount: float


class OutlookCardMonth(BaseModel):
    """Quanto de um cartão cai na fatura do mês"""

    credit_card_id: int | None  # None: parcelas fora de cartão
    total: float
    installments_count: int
    items: list[OutlookItem]


class OutlookMonth(BaseModel):
    year: int
    month: int
    total: float
    installments_count: int
    by_card: list[OutlookCardMonth] = []


class OutlookCard(BaseModel):
    """Cartão que aparece na projeção, com o que identifica o banco"""

    credit_card_id: int | None
    name: str
    bank_id: str | None
    card_brand: str | None
    last_four_digits: str | None
    total: float


class InvoiceOutlookResponse(BaseModel):
    scope: str
    months: list[OutlookMonth]
    total: float
    cards: list[OutlookCard] = []


def _card_name(card: CreditCard | None, account: Account | None) -> str:
    if card is None:
        return "Fora do cartão"
    return (
        (card.nickname or "").strip()
        or (account.name if account else "").strip()
        or (card.bank_id or "").strip()
        or "Cartão"
    )


async def _household_ids(db: AsyncSession, user: User) -> list[int]:
    if not user.license_id:
        return []
    result = await db.execute(
        select(HouseholdMember.user_id).where(HouseholdMember.license_id == user.license_id)
    )
    return list(result.scalars().all())


async def build_outlook(
    db: AsyncSession, user: User, months: int, scope: str, today: date
) -> InvoiceOutlookResponse:
    query = (
        select(InstallmentSeries, CreditCard, Account)
        .join(Account, InstallmentSeries.account_id == Account.id)
        .outerjoin(CreditCard, InstallmentSeries.credit_card_id == CreditCard.id)
        .where(InstallmentSeries.status == InstallmentSeriesStatus.ACTIVE)
    )
    household_ids = await _household_ids(db, user) if scope == "family" else []
    if household_ids:
        query = query.where(
            or_(
                InstallmentSeries.user_id == user.id,
                and_(
                    InstallmentSeries.user_id.in_(household_ids),
                    Account.ownership_type == "household",
                ),
            )
        )
    else:
        query = query.where(InstallmentSeries.user_id == user.id)

    rows = (await db.execute(query)).all()

    start = (today.year, today.month)
    window = []
    cursor = date(today.year, today.month, 1)
    for _ in range(months):
        window.append((cursor.year, cursor.month))
        cursor += relativedelta(months=1)
    in_window = set(window)

    totals: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    counts: dict[tuple[int, int], int] = defaultdict(int)
    per_card: dict[tuple[int, int], dict[int | None, list[OutlookItem]]] = defaultdict(
        lambda: defaultdict(list)
    )
    card_info: dict[int | None, tuple[CreditCard | None, Account | None]] = {}
    card_totals: dict[int | None, Decimal] = defaultdict(Decimal)
    service = InvoiceService(db)

    for series, card, account in rows:
        amount = Decimal(str(series.installment_amount or 0))
        if amount <= 0 or not series.first_installment_date:
            continue
        for k in range(series.installment_count or 0):
            parcel_date = series.first_installment_date + relativedelta(months=k)
            if card is not None:
                period = service.calculate_invoice_period(card, parcel_date)
                key = (period["reference_year"], period["reference_month"])
            else:
                key = (parcel_date.year, parcel_date.month)
            if key < start:
                continue
            if key not in in_window:
                if key > window[-1]:
                    break
                continue
            totals[key] += amount
            counts[key] += 1
            card_id = card.id if card is not None else None
            card_info.setdefault(card_id, (card, account if card is not None else None))
            card_totals[card_id] += amount
            per_card[key][card_id].append(
                OutlookItem(
                    series_id=series.id,
                    description=series.description or series.merchant_name or "Compra parcelada",
                    installment_number=k + 1,
                    installment_count=series.installment_count or 0,
                    amount=float(amount),
                )
            )

    # cartões em ordem de quanto pesam na projeção: o maior primeiro, igual no gráfico e na lista
    card_order = sorted(card_totals, key=lambda cid: (-card_totals[cid], cid is None, cid or 0))
    cards = [
        OutlookCard(
            credit_card_id=cid,
            name=_card_name(*card_info[cid]),
            bank_id=card_info[cid][0].bank_id if card_info[cid][0] else None,
            card_brand=card_info[cid][0].card_brand if card_info[cid][0] else None,
            last_four_digits=card_info[cid][0].last_four_digits if card_info[cid][0] else None,
            total=float(card_totals[cid]),
        )
        for cid in card_order
    ]

    def _by_card(key: tuple[int, int]) -> list[OutlookCardMonth]:
        month = per_card.get(key, {})
        return [
            OutlookCardMonth(
                credit_card_id=cid,
                total=float(sum((Decimal(str(i.amount)) for i in month[cid]), Decimal(0))),
                installments_count=len(month[cid]),
                items=sorted(month[cid], key=lambda i: -i.amount),
            )
            for cid in card_order
            if cid in month
        ]

    result_months = [
        OutlookMonth(
            year=y,
            month=m,
            total=float(totals[(y, m)]),
            installments_count=counts[(y, m)],
            by_card=_by_card((y, m)),
        )
        for y, m in window
    ]
    return InvoiceOutlookResponse(
        scope="family" if household_ids else "me",
        months=result_months,
        total=float(sum(totals.values(), Decimal(0))),
        cards=cards,
    )
