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


class OutlookMonth(BaseModel):
    year: int
    month: int
    total: float
    installments_count: int


class InvoiceOutlookResponse(BaseModel):
    scope: str
    months: list[OutlookMonth]
    total: float


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
        select(InstallmentSeries, CreditCard)
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
    service = InvoiceService(db)

    for series, card in rows:
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

    result_months = [
        OutlookMonth(
            year=y, month=m, total=float(totals[(y, m)]), installments_count=counts[(y, m)]
        )
        for y, m in window
    ]
    return InvoiceOutlookResponse(
        scope="family" if household_ids else "me",
        months=result_months,
        total=float(sum(totals.values(), Decimal(0))),
    )
