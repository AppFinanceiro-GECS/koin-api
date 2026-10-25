"""Testes de característica de transações e analytics.

Cobre duplicata (RN004), confirmação de item extraído e analytics (RN008).
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
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
from app.modules.transactions.schemas.transaction import (
    TransactionConfirm,
    TransactionCreate,
    TransactionResponse,
)
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


# ============================================
# Issue #39 — validação de amount e date
# ============================================


def _valid_transaction_kwargs(**overrides) -> dict:
    kwargs = {
        "type": TransactionType.EXPENSE,
        "account_id": 1,
        "amount": Decimal("50.00"),
        "date": date.today(),
    }
    kwargs.update(overrides)
    return kwargs


def test_amount_zero_e_rejeitado():
    with pytest.raises(ValidationError):
        TransactionCreate(**_valid_transaction_kwargs(amount=Decimal("0")))


def test_amount_negativo_e_rejeitado():
    with pytest.raises(ValidationError):
        TransactionCreate(**_valid_transaction_kwargs(amount=Decimal("-10.00")))


def test_amount_com_mais_de_duas_casas_decimais_e_rejeitado_sem_arredondar():
    """Issue #39 — recusa, não arredonda (ex.: 0.001 não vira 0.00)."""
    with pytest.raises(ValidationError):
        TransactionCreate(**_valid_transaction_kwargs(amount=Decimal("10.999")))


def test_amount_valido_com_duas_casas_decimais_e_aceito():
    transaction = TransactionCreate(**_valid_transaction_kwargs(amount=Decimal("79.90")))
    assert transaction.amount == Decimal("79.90")


def test_data_muito_no_futuro_e_rejeitada():
    """Issue #39 — data além de hoje + 1 ano (ex.: 2999-01-01) deve ser recusada."""
    with pytest.raises(ValidationError):
        TransactionCreate(**_valid_transaction_kwargs(date=date(2999, 1, 1)))


def test_data_muito_no_passado_e_rejeitada():
    too_old = date.today().replace(year=date.today().year - 11)
    with pytest.raises(ValidationError):
        TransactionCreate(**_valid_transaction_kwargs(date=too_old))


def test_data_dentro_da_janela_permitida_e_aceita():
    transaction = TransactionCreate(**_valid_transaction_kwargs(date=date.today()))
    assert transaction.date == date.today()


def test_transaction_confirm_tambem_valida_amount_e_date():
    """O mesmo validador vale pro fluxo de confirmação de documento extraído."""
    with pytest.raises(ValidationError):
        TransactionConfirm(
            account_id=1,
            amount=Decimal("0"),
            date=date.today(),
        )

    with pytest.raises(ValidationError):
        TransactionConfirm(
            account_id=1,
            amount=Decimal("50.00"),
            date=date(2999, 1, 1),
        )


# ============================================
# Issue #33 — GET /transactions 500 com compra no cartão
# ============================================


@pytest.mark.asyncio
async def test_listar_transacoes_com_compra_no_cartao_nao_quebra(
    db_session: AsyncSession,
    test_user: User,
    credit_card_account: Account,
    credit_card: CreditCard,
):
    """credit_card_name acessa self.credit_card.account, que usa lazy loading
    padrão (diferente das demais relações de Transaction, que são noload).
    Sem eager load encadeado (selectinload(credit_card).selectinload(account)),
    serializar a resposta quebra com MissingGreenlet em sessão async."""
    service = TransactionService(db_session)
    created = await service.create(
        test_user,
        TransactionCreate(
            type=TransactionType.EXPENSE,
            account_id=credit_card_account.id,
            amount=Decimal("150.00"),
            date=date.today(),
            description="Compra no cartão",
        ),
    )
    assert created.credit_card_id == credit_card.id

    transactions = await service.list(test_user)
    assert len(transactions) == 1

    # Reproduz o crash original: serializar a transação acessando
    # credit_card_name (via self.credit_card.account) fora de sessão síncrona.
    response = TransactionResponse.model_validate(transactions[0])
    assert response.credit_card_name == credit_card_account.name


@pytest.mark.asyncio
async def test_detalhar_transacao_com_compra_no_cartao_nao_quebra(
    db_session: AsyncSession,
    test_user: User,
    credit_card_account: Account,
    credit_card: CreditCard,
):
    """Mesma proteção precisa valer pro GET /transactions/{id} (get_by_id)."""
    service = TransactionService(db_session)
    created = await service.create(
        test_user,
        TransactionCreate(
            type=TransactionType.EXPENSE,
            account_id=credit_card_account.id,
            amount=Decimal("89.90"),
            date=date.today(),
        ),
    )

    fetched = await service.get_by_id(test_user, created.id)
    response = TransactionResponse.model_validate(fetched)
    assert response.credit_card_name == credit_card_account.name


@pytest.mark.asyncio
async def test_criar_transacao_no_cartao_ja_retorna_credit_card_name(
    db_session: AsyncSession,
    test_user: User,
    credit_card_account: Account,
    credit_card: CreditCard,
):
    """O retorno do POST /transactions (criar) também precisa vir com o
    relacionamento carregado, sem precisar de um GET separado depois."""
    service = TransactionService(db_session)
    created = await service.create(
        test_user,
        TransactionCreate(
            type=TransactionType.EXPENSE,
            account_id=credit_card_account.id,
            amount=Decimal("42.00"),
            date=date.today(),
        ),
    )

    response = TransactionResponse.model_validate(created)
    assert response.credit_card_name == credit_card_account.name
