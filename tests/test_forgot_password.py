"""Esqueci a senha, e-mail sem maiúsculas e uma política de senha só (issue #46)."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email_address import normalize_email
from app.core.security import create_access_token
from app.models.user import User
from app.modules.auth.services.password_reset import hash_reset_token
from scripts.create_admin import AdminInputError, validated_admin_credentials

FORGOT_URL = "/api/v1/auth/forgot-password"
LOGIN_URL = "/api/v1/auth/login"
CHANGE_URL = "/api/v1/users/me/change-password"


def test_create_admin_recusa_dominio_test_e_senha_comum():
    assert normalize_email("  A@B.com ") == "a@b.com"

    with pytest.raises(AdminInputError):
        validated_admin_credentials("admin@foo.test", "frase-longa-do-admin")

    with pytest.raises(AdminInputError):
        validated_admin_credentials("admin@exemplo.com", "senha123")

    assert validated_admin_credentials("Admin@Exemplo.com", "frase-longa-do-admin") == (
        "admin@exemplo.com"
    )


def test_senha_longa_em_bytes_e_recusada():
    from app.core.security import validate_password_or_raise

    with pytest.raises(HTTPException):
        validate_password_or_raise("á" * 40)

    validate_password_or_raise("uma frase longa")


@pytest.mark.asyncio
async def test_email_que_so_difere_em_maiuscula_nao_grava(
    db_session: AsyncSession,
):
    db_session.add(User(email="dup@example.com", name="Um", hashed_password="x", is_active=True))
    await db_session.flush()
    db_session.add(User(email="Dup@example.com", name="Dois", hashed_password="x", is_active=True))
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_login_ignora_maiusculas(client: AsyncClient, test_user: User):
    response = await client.post(
        LOGIN_URL,
        json={"email": "Test@Example.com", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_forgot_password_desconhecido_e_inativo_respondem_202(
    client: AsyncClient, db_session: AsyncSession, test_user: User
):
    unknown = await client.post(FORGOT_URL, json={"email": "ninguem@example.com"})
    assert unknown.status_code == 202
    assert "token" not in unknown.text.lower()

    test_user.is_active = False
    await db_session.flush()

    inactive = await client.post(FORGOT_URL, json={"email": test_user.email})
    assert inactive.status_code == 202
    await db_session.refresh(test_user)
    assert test_user.reset_token is None


@pytest.mark.asyncio
async def test_forgot_password_grava_hash_e_o_token_vale_uma_vez(
    client: AsyncClient, db_session: AsyncSession, test_user: User, monkeypatch
):
    captured: dict[str, str] = {}

    def fake_send(to_email: str, reset_url: str, user_name: str) -> bool:
        captured["url"] = reset_url
        captured["to"] = to_email
        return True

    monkeypatch.setattr(
        "app.modules.auth.routers.auth.email_service.send_password_reset",
        fake_send,
    )

    response = await client.post(FORGOT_URL, json={"email": "TEST@example.com"})
    assert response.status_code == 202
    assert captured["to"] == "test@example.com"

    raw = captured["url"].rsplit("/", 1)[-1]
    await db_session.refresh(test_user)
    assert test_user.reset_token == hash_reset_token(raw)
    assert test_user.reset_token != raw
    assert len(test_user.reset_token) == 64

    check = await client.get(f"/api/v1/auth/reset-password/{raw}")
    assert check.status_code == 200
    assert check.json()["email"] == "test@example.com"

    reset = await client.post(
        f"/api/v1/auth/reset-password/{raw}",
        json={"password": "uma frase longa"},
    )
    assert reset.status_code == 200

    again = await client.get(f"/api/v1/auth/reset-password/{raw}")
    assert again.status_code == 404


@pytest.mark.asyncio
async def test_sexto_pedido_do_mesmo_email_e_429_sem_revelar_a_conta(client: AsyncClient):
    email = "limite@example.com"
    for _ in range(5):
        response = await client.post(FORGOT_URL, json={"email": email})
        assert response.status_code == 202

    blocked = await client.post(FORGOT_URL, json={"email": "Limite@Example.com"})
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == (
        "Muitas solicitações de recuperação. Tente novamente mais tarde."
    )


@pytest.mark.asyncio
async def test_troca_de_senha_usa_a_politica_unica(client: AsyncClient, test_user: User):
    headers = {"Authorization": f"Bearer {create_access_token(test_user.id)}"}

    short = await client.post(
        CHANGE_URL,
        json={"current_password": "TestPass123!", "new_password": "curta"},
        headers=headers,
    )
    assert short.status_code == 422

    common = await client.post(
        CHANGE_URL,
        json={"current_password": "TestPass123!", "new_password": "password"},
        headers=headers,
    )
    assert common.status_code == 400

    changed = await client.post(
        CHANGE_URL,
        json={"current_password": "TestPass123!", "new_password": "uma frase longa"},
        headers=headers,
    )
    assert changed.status_code == 200

    login = await client.post(
        LOGIN_URL, json={"email": test_user.email, "password": "uma frase longa"}
    )
    assert login.status_code == 200
