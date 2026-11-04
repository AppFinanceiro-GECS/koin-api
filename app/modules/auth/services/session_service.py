"""
Sessões com refresh token rotativo (#45).

- Login abre uma família (um aparelho) e emite o primeiro refresh token dela.
- Cada refresh revoga o token usado e emite o próximo da mesma família.
- Reusar um token já trocado indica roubo: a família inteira é revogada.
- Logout revoga a família; "sair de todos" e troca de senha revogam todas.

O access token continua sem estado e vale até expirar (ACCESS_TOKEN_EXPIRE_MINUTES).
"""

import logging
import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.utils import utc_now
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.modules.auth.schemas.auth import Token

logger = logging.getLogger(__name__)

INVALID_REFRESH = "Token de refresh inválido"


def _unauthorized(detail: str = INVALID_REFRESH) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def _load(db: AsyncSession, jti: str) -> RefreshToken | None:
    """Lê do banco, não do identity map: as revogações são UPDATE em massa."""
    return await db.scalar(
        select(RefreshToken)
        .where(RefreshToken.jti == jti)
        .execution_options(populate_existing=True)
    )


async def issue_tokens(
    db: AsyncSession,
    user: User,
    device_name: str | None = None,
    family_id: str | None = None,
) -> tuple[Token, RefreshToken]:
    """Emite access + refresh. Sem family_id, abre uma sessão nova. Não faz commit."""
    now = utc_now()
    row = RefreshToken(
        jti=str(uuid.uuid4()),
        family_id=family_id or str(uuid.uuid4()),
        user_id=user.id,
        device_name=device_name,
        created_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(row)
    token = Token(
        access_token=create_access_token(user.id, session_id=row.family_id),
        refresh_token=create_refresh_token(user.id, row.jti, row.expires_at),
    )
    return token, row


async def rotate(db: AsyncSession, refresh_token: str) -> Token:
    """Troca um refresh válido pelo próximo da família. Reuso revoga a família."""
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh" or not payload.get("jti"):
        # tokens sem jti são de antes da #45 e não podem ser revogados: novo login
        raise _unauthorized()

    current = await _load(db, payload["jti"])
    if current is None or str(current.user_id) != str(payload.get("sub")):
        raise _unauthorized()

    now = utc_now()
    if current.revoked_at is not None:
        if current.replaced_by is not None:
            # token já trocado voltou a ser usado: quem tem a cópia não é o aparelho
            logger.warning(
                "refresh_token_reuse user_id=%s family=%s", current.user_id, current.family_id
            )
            await revoke_family(db, current.family_id)
            await db.commit()
        raise _unauthorized()

    if current.expires_at <= now:
        raise _unauthorized()

    user = await db.get(User, current.user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Usuário não encontrado ou inativo")

    token, new_row = await issue_tokens(db, user, current.device_name, current.family_id)
    # Só um refresh concorrente com o mesmo token vence; o outro cai no reuso acima
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == current.jti, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now, last_used_at=now, replaced_by=new_row.jti)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await db.rollback()
        raise _unauthorized()
    await db.commit()
    return token


async def revoke_family(db: AsyncSession, family_id: str) -> int:
    """Revoga os tokens ainda ativos da família. Não faz commit."""
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utc_now())
        .execution_options(synchronize_session=False)
    )
    return result.rowcount


async def revoke_all(db: AsyncSession, user_id: int, keep_family_id: str | None = None) -> int:
    """Revoga todas as sessões do usuário (opcionalmente menos uma). Não faz commit."""
    stmt = update(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    )
    if keep_family_id:
        stmt = stmt.where(RefreshToken.family_id != keep_family_id)
    result = await db.execute(
        stmt.values(revoked_at=utc_now()).execution_options(synchronize_session=False)
    )
    return result.rowcount


async def logout(db: AsyncSession, refresh_token: str) -> None:
    """Revoga a família do token. Token inválido ou já revogado: nada a fazer."""
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh" or not payload.get("jti"):
        return
    current = await _load(db, payload["jti"])
    if current is None:
        return
    await revoke_family(db, current.family_id)
    await db.commit()


async def active_sessions(db: AsyncSession, user_id: int) -> list[dict]:
    """Uma linha por aparelho com token ativo; início = primeiro token da família."""
    now = utc_now()
    active = (
        await db.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .execution_options(populate_existing=True)
        )
    ).scalars()
    by_family = {row.family_id: row for row in active}
    if not by_family:
        return []

    started = dict(
        (
            await db.execute(
                select(RefreshToken.family_id, func.min(RefreshToken.created_at))
                .where(RefreshToken.family_id.in_(by_family))
                .group_by(RefreshToken.family_id)
            )
        ).all()
    )
    sessions = [
        {
            "id": family_id,
            "device_name": row.device_name,
            "created_at": started[family_id],
            # o token ativo nasceu no último refresh (ou no login)
            "last_used_at": row.created_at,
            "expires_at": row.expires_at,
        }
        for family_id, row in by_family.items()
    ]
    return sorted(sessions, key=lambda s: s["last_used_at"], reverse=True)


def session_id_from_access_token(token: str) -> str | None:
    payload = decode_token(token)
    return payload.get("sid") if payload else None
