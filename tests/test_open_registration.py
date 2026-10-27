"""Testes do cadastro aberto, só na homologação (issue #66)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limit import limiter
from app.models.account import Account
from app.models.user import User

REGISTER_URL = "/api/v1/auth/register"
PAYLOAD = {"email": "novo@example.com", "name": "Novo Usuario", "password": "SenhaForte123!"}


@pytest.fixture(autouse=True)
def reset_rate_limit():
    limiter.reset()


@pytest.fixture
def open_registration(monkeypatch):
    monkeypatch.setattr(settings, "allow_open_registration", True)
    monkeypatch.setattr(settings, "environment", "staging")


@pytest.mark.asyncio
async def test_register_is_not_found_by_default(client: AsyncClient):
    response = await client.post(REGISTER_URL, json=PAYLOAD)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_register_is_blocked_in_production_even_with_flag(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "allow_open_registration", True)
    monkeypatch.setattr(settings, "environment", "production")

    response = await client.post(REGISTER_URL, json=PAYLOAD)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_register_creates_user_with_default_data(
    client: AsyncClient, db_session: AsyncSession, open_registration
):
    response = await client.post(REGISTER_URL, json=PAYLOAD)
    assert response.status_code == 201
    assert response.json()["email"] == PAYLOAD["email"]

    user = await db_session.scalar(select(User).where(User.email == PAYLOAD["email"]))
    assert user is not None
    accounts = (await db_session.scalars(select(Account).where(Account.user_id == user.id))).all()
    assert accounts, "setup_new_user deveria criar as contas padrão"


@pytest.mark.asyncio
async def test_register_can_login_afterwards(client: AsyncClient, open_registration):
    await client.post(REGISTER_URL, json=PAYLOAD)

    response = await client.post(
        "/api/v1/auth/login", json={"email": PAYLOAD["email"], "password": PAYLOAD["password"]}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_register_rejects_weak_password(client: AsyncClient, open_registration):
    response = await client.post(REGISTER_URL, json={**PAYLOAD, "password": "abcdefg"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(client: AsyncClient, open_registration):
    assert (await client.post(REGISTER_URL, json=PAYLOAD)).status_code == 201

    response = await client.post(REGISTER_URL, json=PAYLOAD)
    assert response.status_code == 400
