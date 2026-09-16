from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utc_now

from ....core.security import generate_api_key
from ....models import APIKey, APIKeyStatus, User
from ..schemas import APIKeyCreate


def _check_is_owner(user: User) -> None:
    """
    Verifica se o usuário é o owner da licença.
    Apenas owners podem gerenciar API Keys.
    """
    if not user.is_license_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o proprietário da conta pode gerenciar API Keys",
        )


class APIKeyService:
    """Service para gerenciar API Keys"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_api_key(
        self,
        user: User,
        data: APIKeyCreate,
    ) -> tuple[APIKey, str]:
        """
        Cria uma nova API Key para o usuário.
        Retorna a APIKey e a chave completa (só mostrada uma vez).
        """
        # Verifica se é owner
        _check_is_owner(user)

        # Limite de 10 API Keys por usuário
        result = await self.db.execute(
            select(APIKey).where(
                APIKey.user_id == user.id, APIKey.status == APIKeyStatus.active.value
            )
        )
        existing_keys = result.scalars().all()

        if len(existing_keys) >= 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limite máximo de 10 API Keys ativas atingido",
            )

        # Gera a chave
        full_key, key_prefix, key_hash = generate_api_key()

        # Calcula expiração
        expires_at = None
        if data.expires_in_days:
            expires_at = utc_now() + timedelta(days=data.expires_in_days)

        # Cria o registro
        api_key = APIKey(
            user_id=user.id,
            key_prefix=key_prefix,
            key_hash=key_hash,
            name=data.name,
            notes=data.notes,
            expires_at=expires_at,
            can_read=True,
            can_write=False,  # Por enquanto só leitura
            status=APIKeyStatus.active.value,
        )

        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)

        return api_key, full_key

    async def list_api_keys(self, user: User) -> list[APIKey]:
        """Lista todas as API Keys do usuário (ativas e revogadas)"""
        # Verifica se é owner
        _check_is_owner(user)

        result = await self.db.execute(
            select(APIKey).where(APIKey.user_id == user.id).order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_api_key(self, user: User, key_id: int) -> APIKey:
        """Busca uma API Key específica do usuário"""
        # Verifica se é owner
        _check_is_owner(user)

        result = await self.db.execute(
            select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user.id)
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="API Key não encontrada"
            )

        return api_key

    async def revoke_api_key(self, user: User, key_id: int) -> APIKey:
        """Revoga uma API Key"""
        api_key = await self.get_api_key(user, key_id)

        if api_key.status == APIKeyStatus.revoked.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="API Key já está revogada"
            )

        api_key.status = APIKeyStatus.revoked.value
        api_key.revoked_at = utc_now()

        await self.db.commit()
        await self.db.refresh(api_key)

        return api_key

    async def delete_api_key(self, user: User, key_id: int) -> None:
        """Deleta uma API Key permanentemente"""
        api_key = await self.get_api_key(user, key_id)
        await self.db.delete(api_key)
        await self.db.commit()
