"""Testes de característica de transações e analytics.

Cobre duplicata (RN004), confirmação de item extraído e analytics (RN008).
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import InvoiceStatus
from app.models.document import Document
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.modules.analytics.services.analytics_service import AnalyticsService
from app.modules.credit_cards.services.invoice_service import InvoiceService
from app.modules.transactions.schemas.transaction import TransactionConfirm
from app.modules.transactions.services.transaction_service import TransactionService


async def _confirm(
    db: AsyncSession,
    user: User,
    data: TransactionConfirm,
) -> dict:
    return await TransactionService(db).confirm_from_document(user, data)


@pytest.mark.asyncio
async def test_duplicata_descricao_valor_data_retorna_409(
    db_session: AsyncSession,
    test_user: User,
    bank_account: Account,
    expense_category: Category,
    document: Document,
    second_document_factory,
):
    """RN004 — Duplicata por description + amount + date devolve 409."""
    payload = TransactionConfirm(
        document_id=document.id,
        account_id=bank_account.id,
        category_id=expense_category.id,
        amount=42.50,
        date=date(2026, 3, 10),
        merchant_name="Padaria Central",
        description="Padaria Central",
    )
    first = await _confirm(db_session, test_user, payload)
    assert first["transaction"] is not None

    other_doc = await second_document_factory("dup")
    duplicate = TransactionConfirm(
        document_id=other_doc.id,
        account_id=bank_account.id,
        category_id=expense_category.id,
        amount=42.50,
        date=date(2026, 3, 10),
        merchant_name="Padaria Central",
        description="Padaria Central",
    )

    with pytest.raises(HTTPException) as exc_info:
        await _confirm(db_session, test_user, duplicate)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_confirmacao_item_extraido_cria_transacao_com_categoria_sugerida(
    db_session: AsyncSession,
    test_user: User,
    bank_account: Account,
    expense_category: Category,
    document: Document,
):
    """Confirmação de item extraído cria a transação com a categoria sugerida."""
    result = await _confirm(
        db_session,
        test_user,
        TransactionConfirm(
            document_id=document.id,
            account_id=bank_account.id,
            category_id=expense_category.id,
            amount=79.90,
            date=date(2026, 3, 12),
            merchant_name="Supermercado Bom Preço",
            description="Supermercado Bom Preço",
        ),
    )

    tx = result["transaction"]
    assert tx is not None
    assert tx.category_id == expense_category.id
    assert float(tx.amount) == 79.90
    assert tx.description == "Supermercado Bom Preço"


@pytest.mark.asyncio
async def test_analytics_mes_exclui_pagamento_de_fatura(
    db_session: AsyncSession,
    test_user: User,
    credit_card: CreditCard,
    bank_account: Account,
    expense_category: Category,
):
    """RN008 — Analytics do mês exclui o pagamento de fatura (não conta em dobro)."""
    invoice_service = InvoiceService(db_session)
    invoice = await invoice_service.get_or_create_invoice(
        user=test_user,
        credit_card=credit_card,
        reference_month=3,
        reference_year=2026,
    )
    invoice.total_amount = Decimal("200.00")
    await db_session.flush()

    # Despesa em débito no mesmo mês (deve entrar no total)
    debit_expense = Transaction(
        user_id=test_user.id,
        account_id=bank_account.id,
        category_id=expense_category.id,
        type=TransactionType.EXPENSE.value,
        amount=50.00,
        date=date(2026, 3, 5),
        description="Mercado débito",
        is_paid=True,
    )
    db_session.add(debit_expense)
    await db_session.flush()

    # Pagar a fatura gera expense na conta bancária
    await invoice_service.pay_invoice(
        user=test_user,
        invoice=invoice,
        amount=Decimal("200.00"),
        payment_account_id=bank_account.id,
        payment_date=date(2026, 3, 25),
    )
    assert invoice.status == InvoiceStatus.PAID.value

    summary = await AnalyticsService(db_session).get_monthly_summary(test_user, year=2026, month=3)

    # Fatura 200 + débito 50 = 250. Sem exclusão seria 200 + 50 + 200 = 450.
    assert summary.total_expense == pytest.approx(250.0)
    assert invoice.payment_transaction_id is not None
