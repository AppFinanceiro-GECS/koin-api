from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class UserMerchantRule(Base):
    """Regras personalizadas do usuário para categorização por merchant"""

    __tablename__ = "user_merchant_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    merchant_pattern: Mapped[str] = mapped_column(String(200))  # pode ser regex ou nome exato
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    priority: Mapped[int] = mapped_column(default=0)  # maior = mais prioridade
    confidence: Mapped[float] = mapped_column(Float, default=1.0)  # baseado em uso
    usage_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="merchant_rules")


from .user import User
