from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.deps import CurrentUser, get_db
from ..schemas import (
    APIKeyCreate,
    APIKeyCreatedResponse,
    APIKeyListResponse,
    APIKeyResponse,
)
from ..services import APIKeyService

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.post("", response_model=APIKeyCreatedResponse, status_code=201)
async def create_api_key(
    data: APIKeyCreate,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Cria uma nova API Key para o usuário.

    **IMPORTANTE**: A chave completa (`api_key`) só é mostrada uma vez!
    Guarde em local seguro antes de fechar esta resposta.

    A chave pode ser usada no header `X-API-Key` para autenticar
    requisições aos endpoints de MCP/integração.
    """
    service = APIKeyService(db)
    api_key, full_key = await service.create_api_key(user, data)

    return APIKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        api_key=full_key,
        key_prefix=api_key.key_prefix,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
    )


@router.get("", response_model=APIKeyListResponse)
async def list_api_keys(
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Lista todas as API Keys do usuário.
    Inclui chaves ativas, expiradas e revogadas.
    """
    service = APIKeyService(db)
    keys = await service.list_api_keys(user)

    return APIKeyListResponse(
        items=[APIKeyResponse.model_validate(k) for k in keys],
        total=len(keys),
    )


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: int,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Busca detalhes de uma API Key específica."""
    service = APIKeyService(db)
    api_key = await service.get_api_key(user, key_id)
    return APIKeyResponse.model_validate(api_key)


@router.post("/{key_id}/revoke", response_model=APIKeyResponse)
async def revoke_api_key(
    key_id: int,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Revoga uma API Key.
    A chave não poderá mais ser usada para autenticação.
    """
    service = APIKeyService(db)
    api_key = await service.revoke_api_key(user, key_id)
    return APIKeyResponse.model_validate(api_key)


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(
    key_id: int,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Deleta uma API Key permanentemente.
    Esta ação não pode ser desfeita.
    """
    service = APIKeyService(db)
    await service.delete_api_key(user, key_id)
