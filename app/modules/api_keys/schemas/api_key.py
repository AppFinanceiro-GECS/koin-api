from datetime import datetime

from pydantic import BaseModel, Field


class APIKeyCreate(BaseModel):
    """Schema para criar uma nova API Key"""

    name: str = Field(
        ..., min_length=1, max_length=100, description="Nome para identificar a chave"
    )
    notes: str | None = Field(None, max_length=500, description="Observações opcionais")
    expires_in_days: int | None = Field(
        None, ge=1, le=365, description="Dias até expirar (null = nunca)"
    )


class APIKeyResponse(BaseModel):
    """Schema de resposta para API Key (sem a chave completa)"""

    id: int
    name: str
    key_prefix: str
    status: str
    can_read: bool
    can_write: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    usage_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyCreatedResponse(BaseModel):
    """
    Resposta ao criar uma API Key.
    IMPORTANTE: A chave completa só é mostrada uma vez!
    """

    id: int
    name: str
    api_key: str = Field(
        ..., description="Chave completa - guarde em local seguro! Só é mostrada uma vez."
    )
    key_prefix: str
    expires_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyListResponse(BaseModel):
    """Lista de API Keys do usuário"""

    items: list[APIKeyResponse]
    total: int
