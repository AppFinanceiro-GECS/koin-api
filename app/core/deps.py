from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utc_now

from ..models.api_key import APIKey
from ..models.user import User
from .database import get_db
from .security import decode_token, hash_api_key, verify_api_key_format

security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    token = credentials.credentials
    payload = decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tipo de token inválido",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_user_from_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Autentica usuário via API Key.
    Aceita múltiplos métodos:
    - Header X-API-Key: biv_xxx
    - Header Authorization: Bearer biv_xxx
    """
    # Tenta extrair API Key de diferentes fontes
    api_key_value = None

    if x_api_key:
        api_key_value = x_api_key
    elif authorization:
        # Suporta "Bearer biv_xxx" ou apenas "biv_xxx"
        if authorization.lower().startswith("bearer "):
            api_key_value = authorization[7:].strip()
        else:
            api_key_value = authorization.strip()

    if not api_key_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key não fornecida. Use o header X-API-Key ou Authorization: Bearer <key>.",
        )

    # Valida formato
    if not verify_api_key_format(api_key_value):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato de API Key inválido",
        )

    # Busca a API Key pelo hash
    key_hash = hash_api_key(api_key_value)
    result = await db.execute(select(APIKey).where(APIKey.key_hash == key_hash))
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida",
        )

    # Verifica se está ativa
    if not api_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key expirada ou revogada",
        )

    # Verifica se o usuário existe e está ativo
    if not api_key.user or not api_key.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário associado inativo",
        )

    # Atualiza estatísticas de uso
    api_key.last_used_at = utc_now()
    api_key.usage_count += 1
    api_key.last_ip = request.client.host if request.client else None
    await db.commit()

    return api_key.user


ApiKeyUser = Annotated[User, Depends(get_user_from_api_key)]


async def get_api_key_object(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> APIKey:
    """
    Retorna o objeto APIKey (não apenas o usuário).
    Útil para verificar permissões específicas da key.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key não fornecida",
        )

    if not verify_api_key_format(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato de API Key inválido",
        )

    key_hash = hash_api_key(x_api_key)
    result = await db.execute(select(APIKey).where(APIKey.key_hash == key_hash))
    api_key = result.scalar_one_or_none()

    if api_key is None or not api_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida ou expirada",
        )

    # Atualiza estatísticas
    api_key.last_used_at = utc_now()
    api_key.usage_count += 1
    api_key.last_ip = request.client.host if request.client else None
    await db.commit()

    return api_key


CurrentApiKey = Annotated[APIKey, Depends(get_api_key_object)]
