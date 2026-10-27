"""Token de redefinição de senha: uso único, só o hash fica no banco."""

import hashlib
import secrets
import time
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utc_now
from app.models.user import User

RESET_TOKEN_EXPIRE_HOURS = 1
FORGOT_EMAIL_LIMIT = 5
FORGOT_EMAIL_WINDOW_SECONDS = 60 * 60

_forgot_hits: dict[str, list[float]] = {}


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def assign_reset_token(user: User) -> str:
    """Grava o hash e devolve o token cru, que só vai no e-mail."""
    raw = secrets.token_urlsafe(32)
    user.reset_token = hash_reset_token(raw)
    user.reset_token_expires = utc_now() + timedelta(hours=RESET_TOKEN_EXPIRE_HOURS)
    return raw


async def user_by_reset_token(db: AsyncSession, token: str) -> User | None:
    digest = hash_reset_token(token)
    return await db.scalar(select(User).where(User.reset_token == digest))


def forgot_email_is_limited(email: str) -> bool:
    """Cinco pedidos por hora para o mesmo e-mail, exista a conta ou não."""
    now = time.monotonic()
    recent = [hit for hit in _forgot_hits.get(email, []) if now - hit < FORGOT_EMAIL_WINDOW_SECONDS]
    if len(recent) >= FORGOT_EMAIL_LIMIT:
        _forgot_hits[email] = recent
        return True
    recent.append(now)
    _forgot_hits[email] = recent
    return False
