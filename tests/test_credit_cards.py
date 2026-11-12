"""
CRUD de cartões de crédito: exclusão com e sem dados vinculados, edição parcial e validação.
"""

from datetime import date
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.models.account import Account
from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import CreditCardInvoice
from app.models.installment import InstallmentSeries
from app.models.transaction import Transaction
from app.models.user import User

BASE = "/api/v1/credit-cards"


@pytest_asyncio.fixture
async def auth(client, test_user, db_session):
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {create_access_token(test_user.id)}"
    return client


async def _create_card(client, **overrides) -> dict:
    payload = {
        "name": "Cartão Teste",
        "credit_limit": 3000,
        "closing_day": 5,
        "due_day": 15,
        "last_four_digits": "1234",
        **overrides,
    }
    response = await client.post(BASE, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _count(db: AsyncSession, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def test_excluir_cartao_sem_dados_remove_cartao_e_conta(auth, db_session):
    card = await _create_card(auth)

    response = await auth.delete(f"{BASE}/{card['id']}")

    assert response.status_code == 204
    assert (await auth.get(BASE)).json() == []
    assert await _count(db_session, Account, Account.id == card["account_id"]) == 0


async def test_excluir_cartao_com_lancamentos_pede_confirmacao(auth, db_session, test_user):
    card = await _create_card(auth)
    response = await auth.post(
        "/api/v1/transactions",
        json={
            "account_id": card["account_id"],
            "credit_card_id": card["id"],
            "type": "expense",
            "amount": 120,
            "description": "Compra parcelada",
            "date": "2026-11-01",
            "is_installment": True,
            "installment_current": 1,
            "installment_total": 3,
            "create_future_installments": True,
        },
    )
    assert response.status_code in (200, 201), response.text

    response = await auth.delete(f"{BASE}/{card['id']}")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "credit_card_has_linked_data"
    assert body["detail"]["transactions"] >= 3
    assert body["detail"]["invoices"] >= 1
    assert "lançamentos" in body["detail"]["message"]
    # nada foi apagado
    assert len((await auth.get(BASE)).json()) == 1


async def test_excluir_cartao_com_force_apaga_dados_vinculados(auth, db_session, test_user):
    card = await _create_card(auth)
    await auth.post(
        "/api/v1/transactions",
        json={
            "account_id": card["account_id"],
            "credit_card_id": card["id"],
            "type": "expense",
            "amount": 90,
            "description": "Compra parcelada",
            "date": "2026-11-01",
            "is_installment": True,
            "installment_current": 1,
            "installment_total": 3,
            "create_future_installments": True,
        },
    )

    response = await auth.delete(f"{BASE}/{card['id']}", params={"force": "true"})

    assert response.status_code == 204, response.text
    assert (await auth.get(BASE)).json() == []
    assert await _count(db_session, Transaction, Transaction.account_id == card["account_id"]) == 0
    assert (
        await _count(db_session, CreditCardInvoice, CreditCardInvoice.credit_card_id == card["id"])
        == 0
    )
    assert (
        await _count(
            db_session, InstallmentSeries, InstallmentSeries.account_id == card["account_id"]
        )
        == 0
    )


async def test_compra_no_cartao_lancada_em_outra_conta_conta_e_sai_junto(
    auth, db_session, test_user, bank_account
):
    """O app lança compras com account_id da carteira e credit_card_id do cartão"""
    card = await _create_card(auth)
    db_session.add(
        Transaction(
            user_id=test_user.id,
            account_id=bank_account.id,
            credit_card_id=card["id"],
            type="expense",
            amount=Decimal("30"),
            date=date(2026, 11, 3),
            description="Mercado",
        )
    )
    await db_session.commit()

    response = await auth.delete(f"{BASE}/{card['id']}")
    assert response.status_code == 409
    assert response.json()["detail"]["transactions"] == 1

    response = await auth.delete(f"{BASE}/{card['id']}", params={"force": "true"})
    assert response.status_code == 204
    assert await _count(db_session, Transaction, Transaction.account_id == bank_account.id) == 0


async def test_force_solta_recorrencia_que_aponta_para_lancamento_do_cartao(
    auth, db_session, test_user, bank_account
):
    """recurrence_parent_id não tem ON DELETE: sem o ajuste, o Postgres recusaria a exclusão"""
    card = await _create_card(auth)
    parent = Transaction(
        user_id=test_user.id,
        account_id=card["account_id"],
        credit_card_id=card["id"],
        type="expense",
        amount=Decimal("50"),
        date=date(2026, 11, 2),
        description="Assinatura",
    )
    db_session.add(parent)
    await db_session.flush()
    child = Transaction(
        user_id=test_user.id,
        account_id=bank_account.id,
        type="expense",
        amount=Decimal("50"),
        date=date(2026, 12, 2),
        description="Assinatura (cópia)",
        recurrence_parent_id=parent.id,
    )
    db_session.add(child)
    await db_session.commit()
    child_id = child.id

    response = await auth.delete(f"{BASE}/{card['id']}", params={"force": "true"})

    assert response.status_code == 204, response.text
    db_session.expire_all()
    remaining = await db_session.get(Transaction, child_id)
    assert remaining is not None
    assert remaining.recurrence_parent_id is None


async def test_excluir_cartao_de_outro_usuario_da_404(auth, db_session):
    other = User(
        email="outro@example.com",
        hashed_password=get_password_hash("TestPass123!"),
        name="Outro",
        is_active=True,
        is_verified=True,
    )
    db_session.add(other)
    await db_session.flush()
    account = Account(user_id=other.id, name="Cartão alheio", type="credit_card", balance=0)
    db_session.add(account)
    await db_session.flush()
    card = CreditCard(user_id=other.id, account_id=account.id, credit_limit=1000)
    db_session.add(card)
    await db_session.commit()

    response = await auth.delete(f"{BASE}/{card.id}")

    assert response.status_code == 404
    assert await _count(db_session, CreditCard, CreditCard.id == card.id) == 1


async def test_editar_so_um_campo_preserva_os_demais(auth):
    card = await _create_card(auth, name="Roxinho", annual_fee_frequency="yearly")

    response = await auth.patch(f"{BASE}/{card['id']}", json={"credit_limit": 4500})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["credit_limit"] == 4500
    assert body["account_name"] == "Roxinho"
    assert body["last_four_digits"] == "1234"
    assert body["closing_day"] == 5
    assert body["annual_fee_frequency"] == "yearly"


async def test_editar_com_null_em_campo_obrigatorio_nao_quebra(auth):
    card = await _create_card(auth)

    response = await auth.patch(
        f"{BASE}/{card['id']}", json={"closing_day": None, "nickname": None}
    )

    assert response.status_code == 200, response.text
    assert response.json()["closing_day"] == 5


async def test_final_do_cartao_precisa_ter_4_digitos(auth):
    response = await auth.post(
        BASE,
        json={"name": "X", "credit_limit": 100, "last_four_digits": "12a"},
    )
    assert response.status_code == 422

    card = await _create_card(auth)
    response = await auth.patch(f"{BASE}/{card['id']}", json={"last_four_digits": "12"})
    assert response.status_code == 422


async def test_listagem_traz_senha_salva_e_ordem_de_criacao(auth):
    first = await _create_card(auth, name="Primeiro")
    await _create_card(auth, name="Segundo")
    response = await auth.post(f"{BASE}/{first['id']}/invoice-password", json={"password": "abc"})
    assert response.status_code == 200

    cards = (await auth.get(BASE)).json()

    assert [c["name"] for c in cards] == ["Primeiro", "Segundo"]
    assert cards[0]["has_invoice_password"] is True
    assert cards[1]["has_invoice_password"] is False

    response = await auth.post(f"{BASE}/{first['id']}/invoice-password", json={"password": ""})
    assert response.status_code == 422
