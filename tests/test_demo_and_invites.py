"""
#53: link de convite na resposta do admin e dados de demonstração.
"""

import importlib.util
from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.security import create_access_token, get_password_hash
from app.models import Invitation, InvitationStatus
from app.models.credit_card_invoice import CreditCardInvoice
from app.models.installment import InstallmentSeries
from app.models.recurring import RecurringTransaction
from app.models.transaction import Transaction
from app.models.user import User
from app.modules.auth.services.user_setup import setup_new_user

EMAIL_SERVICE = "app.modules.admin.routers.admin.email_service.send_invitation"


@pytest_asyncio.fixture
async def admin_headers(db_session):
    admin = User(
        email="admin@example.com",
        hashed_password=get_password_hash("TestPass123!"),
        name="Admin",
        is_admin=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(admin.id)}"}


@pytest.mark.parametrize("email_sent", [True, False])
async def test_criar_convite_devolve_link_copiavel(client, admin_headers, monkeypatch, email_sent):
    monkeypatch.setattr(EMAIL_SERVICE, lambda **kwargs: email_sent)

    response = await client.post(
        "/api/v1/admin/invitations", headers=admin_headers, json={"email": "nova@example.com"}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["invite_token"]
    assert body["invite_url"].endswith(f"/invite/{body['invite_token']}")
    assert body["email_sent"] is email_sent


async def test_reenviar_convite_sem_email_nao_da_500(
    client, admin_headers, monkeypatch, db_session
):
    monkeypatch.setattr(EMAIL_SERVICE, lambda **kwargs: True)
    created = (
        await client.post(
            "/api/v1/admin/invitations", headers=admin_headers, json={"email": "nova@example.com"}
        )
    ).json()
    invitation = await db_session.get(Invitation, created["id"])
    invitation.status = InvitationStatus.EXPIRED
    await db_session.commit()
    monkeypatch.setattr(EMAIL_SERVICE, lambda **kwargs: False)

    response = await client.post(
        f"/api/v1/admin/invitations/{created['id']}/resend", headers=admin_headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email_sent"] is False
    assert body["invite_token"] == created["invite_token"]
    await db_session.refresh(invitation)
    assert invitation.status == InvitationStatus.PENDING


async def test_criar_licenca_devolve_link_do_convite(client, admin_headers, monkeypatch):
    monkeypatch.setattr(EMAIL_SERVICE, lambda **kwargs: False)

    response = await client.post(
        "/api/v1/admin/licenses",
        headers=admin_headers,
        json={"owner_email": "dono@example.com", "start_date": date.today().isoformat()},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["invite_url"].endswith(f"/invite/{body['invite_token']}")
    validation = await client.get(f"/api/v1/auth/invite/{body['invite_token']}")
    assert validation.status_code == 200
    assert validation.json()["email"] == "dono@example.com"


async def test_compra_parcelada_pela_api_nao_da_500(client, test_user, db_session):
    """Regressão: Decimal * float no casamento de séries derrubava POST /transactions."""
    await setup_new_user(db_session, test_user.id)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(test_user.id)}"}
    card = (
        await client.post(
            "/api/v1/credit-cards",
            headers=headers,
            json={"name": "Cartão", "credit_limit": 5000, "closing_day": 10, "due_day": 17},
        )
    ).json()

    for _ in range(2):  # a segunda passa pelo casamento com a série existente
        response = await client.post(
            "/api/v1/transactions",
            headers=headers,
            json={
                "description": "Notebook",
                "amount": "420.00",
                "date": date.today().isoformat(),
                "type": "expense",
                "account_id": card["account_id"],
                "credit_card_id": card["id"],
                "is_installment": True,
                "installment_current": 1,
                "installment_total": 10,
                "create_future_installments": True,
            },
        )
        assert response.status_code == 201, response.text


def _load_seed_module():
    path = Path(__file__).resolve().parent.parent / "scripts" / "seed_demo.py"
    spec = importlib.util.spec_from_file_location("seed_demo", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_seed_demo_monta_o_roteiro_completo(client, test_user, db_session):
    seed = _load_seed_module()
    await setup_new_user(db_session, test_user.id)
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {create_access_token(test_user.id)}"

    await seed.Seeder(client).run()

    async def count(model):
        return await db_session.scalar(
            select(func.count()).select_from(model).where(model.user_id == test_user.id)
        )

    assert await count(InstallmentSeries) == 2
    assert await count(RecurringTransaction) == 2
    assert await count(Transaction) >= 30
    paid = await db_session.scalar(
        select(func.count())
        .select_from(CreditCardInvoice)
        .where(CreditCardInvoice.user_id == test_user.id, CreditCardInvoice.status == "paid")
    )
    assert paid == 1
    listing = await client.get("/api/v1/transactions")
    assert listing.status_code == 200


def test_meses_anteriores_atravessam_o_ano():
    seed = _load_seed_module()
    assert seed.months_back(date(2027, 1, 15), 2) == (2026, 11)
    assert seed.day_in(2026, 11, 20, date(2026, 11, 4)) == date(2026, 11, 4)
