"""Testes do bloqueio progressivo de login por e-mail (issue #49)."""

from datetime import timedelta

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utc_now
from app.models.login_attempt import LoginAttempt
from app.models.user import User
from app.modules.auth.services.auth_service import (
    LOGIN_FAILURE_THRESHOLD,
    AuthService,
)

LOGIN_URL = "/api/v1/auth/login"
WRONG_PASSWORD = "SenhaErrada123!"
RIGHT_PASSWORD = "TestPass123!"


async def _fail_login(client: AsyncClient, email: str, times: int) -> None:
    for _ in range(times):
        response = await client.post(LOGIN_URL, json={"email": email, "password": WRONG_PASSWORD})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_wrong_password_returns_401_without_locking_before_threshold(
    client: AsyncClient, test_user: User
):
    await _fail_login(client, test_user.email, LOGIN_FAILURE_THRESHOLD - 1)

    response = await client.post(
        LOGIN_URL, json={"email": test_user.email, "password": WRONG_PASSWORD}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_locks_after_threshold_failures_with_retry_after(
    client: AsyncClient, test_user: User
):
    await _fail_login(client, test_user.email, LOGIN_FAILURE_THRESHOLD)

    # Mesmo com a senha certa, o e-mail está bloqueado.
    response = await client.post(
        LOGIN_URL, json={"email": test_user.email, "password": RIGHT_PASSWORD}
    )
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0


@pytest.mark.asyncio
async def test_successful_login_resets_attempt_counter(client: AsyncClient, test_user: User):
    await _fail_login(client, test_user.email, LOGIN_FAILURE_THRESHOLD - 1)

    ok = await client.post(LOGIN_URL, json={"email": test_user.email, "password": RIGHT_PASSWORD})
    assert ok.status_code == 200

    # Depois de logar certo, volta a ter o limite inteiro disponível.
    await _fail_login(client, test_user.email, LOGIN_FAILURE_THRESHOLD - 1)
    still_not_locked = await client.post(
        LOGIN_URL, json={"email": test_user.email, "password": WRONG_PASSWORD}
    )
    assert still_not_locked.status_code == 401


@pytest.mark.asyncio
async def test_failures_outside_window_do_not_accumulate(db_session: AsyncSession, test_user: User):
    service = AuthService(db_session)

    # Simula falhas "antigas" (fora da janela de 15 min) direto no banco.
    old_time = utc_now() - timedelta(minutes=30)
    attempt = LoginAttempt(
        email=test_user.email,
        failed_count=LOGIN_FAILURE_THRESHOLD - 1,
        last_failed_at=old_time,
    )
    db_session.add(attempt)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await service.login(test_user.email, WRONG_PASSWORD)

    # Uma falha a mais não deveria bloquear, porque a contagem anterior expirou.
    assert exc_info.value.status_code == 401

    result = await db_session.execute(
        select(LoginAttempt).where(LoginAttempt.email == test_user.email)
    )
    refreshed = result.scalar_one()
    assert refreshed.failed_count == 1
    assert refreshed.locked_until is None


@pytest.mark.asyncio
async def test_repeated_lockouts_increase_delay_progressively(
    db_session: AsyncSession, test_user: User
):
    service = AuthService(db_session)

    async def lock_once(previous_lock_count: int):
        for _ in range(LOGIN_FAILURE_THRESHOLD):
            with pytest.raises(HTTPException):
                await service.login(test_user.email, WRONG_PASSWORD)
            result = await db_session.execute(
                select(LoginAttempt).where(LoginAttempt.email == test_user.email)
            )
            attempt = result.scalar_one()
            if attempt.lock_count > previous_lock_count:
                # Força o bloqueio a já ter expirado, pra poder testar o próximo ciclo.
                attempt.locked_until = utc_now() - timedelta(seconds=1)
                await db_session.commit()
                return attempt
        raise AssertionError("bloqueio nunca foi acionado")

    first_lock = await lock_once(previous_lock_count=0)
    first_count = first_lock.lock_count

    second_lock = await lock_once(previous_lock_count=first_count)
    assert second_lock.lock_count == first_count + 1
