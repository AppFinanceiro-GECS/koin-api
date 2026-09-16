from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class APIKeyStatus(str, Enum):
    """Status da API Key"""

    active = "active"
    revoked = "revoked"
    expired = "expired"


class APIKey(Base):
    """
    API Keys para acesso externo (MCP, integrações).
    Cada usuário pode ter múltiplas API Keys.
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    # Identificador público (prefixo visível: biv_xxx...)
    key_prefix: Mapped[str] = mapped_column(String(12), index=True)

    # Hash da chave completa (nunca armazenamos a chave em texto)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Nome/descrição para identificar a chave
    name: Mapped[str] = mapped_column(String(100))

    # Permissões (JSON ou flags)
    # Por enquanto, todas as keys têm permissão de leitura apenas
    can_read: Mapped[bool] = mapped_column(Boolean, default=True)
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status e controle
    status: Mapped[str] = mapped_column(String(20), default=APIKeyStatus.active.value)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Metadados de uso
    usage_count: Mapped[int] = mapped_column(default=0)
    last_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max length

    # Notas do usuário
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationship
    user: Mapped["User"] = relationship(back_populates="api_keys", lazy="selectin")

    @property
    def is_active(self) -> bool:
        """Verifica se a API Key está ativa e não expirada"""
        if self.status != APIKeyStatus.active.value:
            return False
        if self.expires_at and self.expires_at < utc_now():
            return False
        return True

    @property
    def masked_key(self) -> str:
        """Retorna a chave mascarada para exibição"""
        return f"{self.key_prefix}...{'*' * 20}"


from .user import User
