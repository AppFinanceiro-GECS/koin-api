"""
Servico de autenticacao: registro, login e refresh de tokens.
"""

from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email_address import normalize_email
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.core.utils import utc_now
from app.models.login_attempt import LoginAttempt
from app.models.user import User
from app.modules.auth.schemas.auth import Token
from app.modules.auth.schemas.user import UserCreate

# Bloqueio progressivo por e-mail (sobrevive a deploy, guardado no Postgres).
# Limite de IP (flood grosseiro) fica no slowapi, em app/modules/auth/routers/auth.py.
LOGIN_FAILURE_THRESHOLD = 5
LOGIN_FAILURE_WINDOW_MINUTES = 15
LOGIN_LOCK_BASE_MINUTES = 15


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, user_data: UserCreate) -> User:
        email = normalize_email(user_data.email)
        # Verificar se email já existe
        result = await self.db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email já cadastrado",
            )

        # Criar usuário
        user = User(
            email=email,
            name=user_data.name,
            hashed_password=get_password_hash(user_data.password),
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def login(self, email: str, password: str) -> Token:
        email = normalize_email(email)
        attempt = await self._get_or_create_login_attempt(email)

        now = utc_now()
        if attempt.locked_until and attempt.locked_until > now:
            retry_after = int((attempt.locked_until - now).total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Muitas tentativas de login. Tente novamente mais tarde.",
                headers={"Retry-After": str(retry_after)},
            )

        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            await self._register_failed_login(attempt, now)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou senha incorretos",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário inativo",
            )

        await self._reset_login_attempt(attempt)

        return Token(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    async def _get_or_create_login_attempt(self, email: str) -> LoginAttempt:
        result = await self.db.execute(select(LoginAttempt).where(LoginAttempt.email == email))
        attempt = result.scalar_one_or_none()
        if not attempt:
            attempt = LoginAttempt(email=email)
            self.db.add(attempt)
            await self.db.flush()
        return attempt

    async def _register_failed_login(self, attempt: LoginAttempt, now: datetime) -> None:
        """Conta só as falhas; reinicia a janela se o último erro foi há mais de
        LOGIN_FAILURE_WINDOW_MINUTES. Ao atingir o limite, bloqueia com atraso
        progressivo (cada bloqueio novo é mais longo que o anterior)."""
        window = timedelta(minutes=LOGIN_FAILURE_WINDOW_MINUTES)
        if attempt.last_failed_at and now - attempt.last_failed_at > window:
            attempt.failed_count = 0

        attempt.failed_count += 1
        attempt.last_failed_at = now

        if attempt.failed_count >= LOGIN_FAILURE_THRESHOLD:
            attempt.lock_count += 1
            lock_minutes = LOGIN_LOCK_BASE_MINUTES * attempt.lock_count
            attempt.locked_until = now + timedelta(minutes=lock_minutes)
            attempt.failed_count = 0

        await self.db.commit()

    async def _reset_login_attempt(self, attempt: LoginAttempt) -> None:
        attempt.failed_count = 0
        attempt.lock_count = 0
        attempt.locked_until = None
        attempt.last_failed_at = None
        await self.db.commit()

    async def refresh_token(self, refresh_token: str) -> Token:
        payload = decode_token(refresh_token)

        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de refresh inválido",
            )

        user_id = payload.get("sub")
        result = await self.db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário não encontrado ou inativo",
            )

        return Token(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )
