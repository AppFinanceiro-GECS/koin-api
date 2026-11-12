"""
Cartão da casa: as compras dele entram na divisão da família sem marcar uma a uma.
Só o dono do cartão muda; as faturas ainda não pagas acompanham, as pagas ficam como estavam.
Dados fictícios.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.credit_card_invoice import CreditCardInvoice
from app.models.transaction import Transaction
from app.models.user import User

EMAIL_SERVICE = "app.modules.household.routers.family.email_service.send_invitation"


@pytest.fixture
def no_email(monkeypatch):
    monkeypatch.setattr(EMAIL_SERVICE, lambda **kwargs: True)


async def _user(db, email, name):
    user = User(email=email, hashed_password=get_password_hash("Pass123!"), name=name)
    db.add(user)
    await db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def _casal(client, db):
    ana, ana_h = await _user(db, "ana@example.com", "Ana Teste")
    bruno, bruno_h = await _user(db, "bruno@example.com", "Bruno Teste")
    assert (await client.post("/api/v1/family", headers=ana_h, json={})).status_code == 201
    invite = await client.post(
        "/api/v1/family/invite", headers=ana_h, json={"email": "bruno@example.com"}
    )
    joined = await client.post(
        "/api/v1/family/join", headers=bruno_h, json={"code": invite.json()["code"]}
    )
    assert joined.status_code == 200, joined.text
    return ana, ana_h, bruno, bruno_h


async def _card(client, headers):
    response = await client.post(
        "/api/v1/credit-cards",
        headers=headers,
        json={
            "name": "Visa Fictício",
            "credit_limit": 5000,
            "closing_day": 5,
            "due_day": 15,
            "last_four_digits": "4321",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _invoice_with_purchase(db, user, card, month, status, amount):
    invoice = CreditCardInvoice(
        user_id=user.id,
        credit_card_id=card["id"],
        reference_month=month,
        reference_year=2026,
        closing_date=date(2026, month, 5),
        due_date=date(2026, month, 15),
        total_amount=Decimal(amount),
        status=status,
    )
    db.add(invoice)
    await db.flush()
    tx = Transaction(
        user_id=user.id,
        account_id=card["account_id"],
        credit_card_id=card["id"],
        invoice_id=invoice.id,
        type="expense",
        amount=Decimal(amount),
        date=date(2026, month, 1),
        description="Compra fictícia",
        ownership_type="personal",
    )
    db.add(tx)
    await db.commit()
    return tx


async def test_cartao_da_casa_leva_as_faturas_abertas_para_a_divisao(client, db_session, no_email):
    ana, ana_h, _, bruno_h = await _casal(client, db_session)
    card = await _card(client, ana_h)
    paga = await _invoice_with_purchase(db_session, ana, card, 10, "paid", "80.00")
    aberta = await _invoice_with_purchase(db_session, ana, card, 11, "open", "200.00")

    response = await client.patch(
        f"/api/v1/credit-cards/{card['id']}",
        headers=ana_h,
        json={"ownership_type": "household", "apply_to_open_invoices": True},
    )

    assert response.status_code == 200, response.text
    assert response.json()["ownership_type"] == "household"
    await db_session.refresh(paga)
    await db_session.refresh(aberta)
    assert aberta.ownership_type == "household"
    assert paga.ownership_type == "personal"  # fatura paga fica como estava

    # Bruno passa a ver o cartão e a compra entra na divisão: ele deve metade para a Ana
    assert card["id"] in [
        c["id"] for c in (await client.get("/api/v1/credit-cards", headers=bruno_h)).json()
    ]
    split = (
        await client.get(
            "/api/v1/family/split", headers=bruno_h, params={"year": 2026, "month": 11}
        )
    ).json()
    assert split["total"] == 200.0
    assert [t["amount"] for t in split["transfers"]] == [100.0]


async def test_compra_importada_no_cartao_da_casa_entra_como_da_casa(client, db_session, no_email):
    _, ana_h, _, _ = await _casal(client, db_session)
    card = await _card(client, ana_h)
    await client.patch(
        f"/api/v1/credit-cards/{card['id']}", headers=ana_h, json={"ownership_type": "household"}
    )

    response = await client.post(
        "/api/v1/transactions/batch-confirm",
        headers=ana_h,
        json={
            "items": [
                {
                    "account_id": card["account_id"],
                    "credit_card_id": card["id"],
                    "payment_method": "credit_card",
                    "amount": 59.9,
                    "date": "2026-11-10",
                    "description": "Mercado Fictício",
                    "merchant_name": "Mercado Fictício",
                    "ownership_type": "personal",
                }
            ]
        },
    )

    assert response.status_code == 201, response.text
    tx = await db_session.scalar(
        select(Transaction).where(Transaction.description == "Mercado Fictício")
    )
    assert tx.ownership_type == "household"


async def test_so_o_dono_do_cartao_muda(client, db_session, no_email):
    _, ana_h, _, bruno_h = await _casal(client, db_session)
    card = await _card(client, ana_h)
    await client.patch(
        f"/api/v1/credit-cards/{card['id']}", headers=ana_h, json={"ownership_type": "household"}
    )

    response = await client.patch(
        f"/api/v1/credit-cards/{card['id']}", headers=bruno_h, json={"ownership_type": "personal"}
    )

    assert response.status_code == 403
    assert "cadastrou o cartão" in response.json()["detail"]


async def test_sem_familia_nao_vira_da_casa(client, db_session):
    _, solo_h = await _user(db_session, "solo@example.com", "Solo")
    card = await _card(client, solo_h)

    response = await client.patch(
        f"/api/v1/credit-cards/{card['id']}", headers=solo_h, json={"ownership_type": "household"}
    )

    assert response.status_code == 403


async def test_voltar_a_ser_pessoal_tira_as_abertas_da_divisao(client, db_session, no_email):
    ana, ana_h, _, _ = await _casal(client, db_session)
    card = await _card(client, ana_h)
    aberta = await _invoice_with_purchase(db_session, ana, card, 11, "open", "200.00")
    for ownership in ("household", "personal"):
        await client.patch(
            f"/api/v1/credit-cards/{card['id']}",
            headers=ana_h,
            json={"ownership_type": ownership, "apply_to_open_invoices": True},
        )

    await db_session.refresh(aberta)
    assert aberta.ownership_type == "personal"
