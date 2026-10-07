"""Testes de característica do fluxo de fatura de cartão.

Cobre os critérios de aceite de "Fatura de cartão" (RN003, RN006
e pagamentos parcial/total).
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import InvoiceStatus
from app.models.user import User
from app.modules.credit_cards.services.invoice_service import InvoiceService


@pytest.mark.asyncio
async def test_compra_apos_fechamento_cai_na_fatura_seguinte(
    db_session: AsyncSession, credit_card: CreditCard
):
    """RN003 — Compra depois do fechamento cai na fatura do mês seguinte.

    Cartão fecha dia 15; compra em 20/01 → fatura de fevereiro.
    """
    period = InvoiceService(db_session).calculate_invoice_period(credit_card, date(2026, 1, 20))

    assert period["reference_month"] == 2
    assert period["reference_year"] == 2026
    assert period["closing_date"] == date(2026, 2, 15)
    assert period["due_date"] == date(2026, 2, 25)


@pytest.mark.asyncio
async def test_vencimento_anterior_ao_fechamento_vai_para_mes_seguinte(
    db_session: AsyncSession,
    credit_card_due_before_closing: CreditCard,
):
    """RN003 — Se due_day < closing_day, vencimento fica no mês seguinte ao fechamento."""
    dates = InvoiceService(db_session).calculate_invoice_dates(
        credit_card_due_before_closing, reference_month=3, reference_year=2026
    )

    assert dates["closing_date"] == date(2026, 3, 20)
    assert dates["due_date"] == date(2026, 4, 10)


@pytest.mark.asyncio
async def test_pagar_com_conta_cartao_retorna_400(
    db_session: AsyncSession,
    test_user: User,
    credit_card: CreditCard,
    credit_card_account: Account,
):
    """RN006 — Pagamento de fatura com conta tipo credit_card devolve 400."""
    service = InvoiceService(db_session)
    invoice = await service.get_or_create_invoice(
        user=test_user,
        credit_card=credit_card,
        reference_month=1,
        reference_year=2026,
    )
    invoice.total_amount = Decimal("100.00")
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await service.pay_invoice(
            user=test_user,
            invoice=invoice,
            amount=Decimal("100.00"),
            payment_account_id=credit_card_account.id,
        )

    assert exc_info.value.status_code == 400
    assert "cartao" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_pagamento_parcial_deixa_status_partial(
    db_session: AsyncSession,
    test_user: User,
    credit_card: CreditCard,
    bank_account: Account,
):
    """Pagamento parcial deixa status `partial` e rola o restante."""
    service = InvoiceService(db_session)
    invoice = await service.get_or_create_invoice(
        user=test_user,
        credit_card=credit_card,
        reference_month=2,
        reference_year=2026,
    )
    invoice.total_amount = Decimal("300.00")
    await db_session.flush()

    await service.pay_invoice(
        user=test_user,
        invoice=invoice,
        amount=Decimal("100.00"),
        payment_account_id=bank_account.id,
        payment_date=date(2026, 2, 20),
    )

    assert invoice.status == InvoiceStatus.PARTIAL.value
    assert invoice.paid_amount == Decimal("100.00")
    assert invoice.remaining_amount == Decimal("200.00")
    assert invoice.payment_transaction_id is not None


@pytest.mark.asyncio
async def test_pagamento_total_deixa_status_paid(
    db_session: AsyncSession,
    test_user: User,
    credit_card: CreditCard,
    bank_account: Account,
):
    """Pagamento total deixa status `paid`."""
    service = InvoiceService(db_session)
    invoice = await service.get_or_create_invoice(
        user=test_user,
        credit_card=credit_card,
        reference_month=3,
        reference_year=2026,
    )
    invoice.total_amount = Decimal("250.00")
    await db_session.flush()

    await service.pay_invoice(
        user=test_user,
        invoice=invoice,
        amount=Decimal("250.00"),
        payment_account_id=bank_account.id,
        payment_date=date(2026, 3, 25),
    )

    assert invoice.status == InvoiceStatus.PAID.value
    assert invoice.paid_amount == Decimal("250.00")
    assert invoice.remaining_amount == Decimal("0.00")
