import secrets
from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


def generate_license_code() -> str:
    """Gera código amigável: BIV-XXXX-XXXX"""
    # Caracteres sem I,O,0,1 para evitar confusão
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    part1 = "".join(secrets.choice(chars) for _ in range(4))
    part2 = "".join(secrets.choice(chars) for _ in range(4))
    return f"BIV-{part1}-{part2}"


class LicenseType(str, Enum):
    TRIAL = "trial"
    BASIC = "basic"
    PREMIUM = "premium"
    LIFETIME = "lifetime"


class LicenseStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    code: Mapped[str] = mapped_column(
        String(13), unique=True, index=True, default=generate_license_code
    )
    type: Mapped[LicenseType] = mapped_column(String(20), default=LicenseType.BASIC)
    status: Mapped[LicenseStatus] = mapped_column(String(20), default=LicenseStatus.ACTIVE)

    # Limites
    max_users: Mapped[int] = mapped_column(Integer, default=1)
    max_transactions_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_documents_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Features
    has_ai_assistant: Mapped[bool] = mapped_column(Boolean, default=True)
    has_insights: Mapped[bool] = mapped_column(Boolean, default=True)
    has_debt_strategies: Mapped[bool] = mapped_column(Boolean, default=True)
    has_goals: Mapped[bool] = mapped_column(Boolean, default=True)
    has_budget: Mapped[bool] = mapped_column(Boolean, default=True)

    # Datas
    start_date: Mapped[date] = mapped_column(Date, default=date.today)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Owner da licenca (primeiro usuario a aceitar convite)
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Metadados
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    users: Mapped[list["User"]] = relationship(
        back_populates="license", lazy="noload", foreign_keys="User.license_id"
    )
    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_user_id], lazy="noload")
    members: Mapped[list["HouseholdMember"]] = relationship(back_populates="license", lazy="noload")

    @property
    def is_valid(self) -> bool:
        """Verifica se a licença está válida"""
        if self.status != LicenseStatus.ACTIVE:
            return False
        if self.end_date and self.end_date < date.today():
            return False
        return True

    @property
    def days_remaining(self) -> int | None:
        """Retorna dias restantes da licença"""
        if not self.end_date:
            return None
        delta = self.end_date - date.today()
        return max(0, delta.days)

    @property
    def member_count(self) -> int:
        """Retorna quantidade de membros da familia"""
        return len(self.members) if self.members else 0

    @property
    def can_add_members(self) -> bool:
        """Verifica se ainda pode adicionar membros"""
        return self.member_count < self.max_users


from .household import HouseholdMember
from .user import User
