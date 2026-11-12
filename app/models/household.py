from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class HouseholdRole(str, Enum):
    """Role do membro dentro da licenca/familia"""

    OWNER = "owner"  # Dono da conta, primeiro a aceitar convite
    ADMIN = "admin"  # Admin da familia (pode convidar)
    MEMBER = "member"  # Membro comum


class OwnershipType(str, Enum):
    """Tipo de propriedade de um recurso (conta, transacao, etc)"""

    PERSONAL = "personal"  # So o dono ve
    HOUSEHOLD = "household"  # Toda a familia ve


class HouseholdMember(Base):
    """
    Membro de uma familia/licenca.

    Representa a relacao entre um User e uma License,
    com permissoes especificas para a familia.
    """

    __tablename__ = "household_members"
    __table_args__ = (UniqueConstraint("license_id", "user_id", name="uq_household_license_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default=HouseholdRole.MEMBER.value)
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    invited_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Permissoes do membro
    can_create_transactions: Mapped[bool] = mapped_column(Boolean, default=True)
    can_edit_shared: Mapped[bool] = mapped_column(Boolean, default=True)
    can_invite_members: Mapped[bool] = mapped_column(Boolean, default=False)
    can_see_all: Mapped[bool] = mapped_column(Boolean, default=False)

    # Parte do membro nas despesas da casa (0-100). Nulo em todos = divisão igual
    share_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Relationships
    license: Mapped["License"] = relationship(back_populates="members", foreign_keys=[license_id])
    user: Mapped["User"] = relationship(
        back_populates="household_membership", foreign_keys=[user_id]
    )
    invited_by: Mapped["User | None"] = relationship(foreign_keys=[invited_by_id])

    @property
    def is_owner(self) -> bool:
        return self.role == HouseholdRole.OWNER.value

    @property
    def is_admin(self) -> bool:
        return self.role in (HouseholdRole.OWNER.value, HouseholdRole.ADMIN.value)


class HouseholdSettlement(Base):
    """
    Acerto entre membros da família: quem pagou a mais nas despesas da casa recebe de
    quem pagou a menos. Só registra o acerto; o dinheiro passa por fora (Pix etc.).
    """

    __tablename__ = "household_settlements"

    id: Mapped[int] = mapped_column(primary_key=True)
    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"), index=True
    )
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # mês das despesas que o acerto quita
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


from .license import License
from .user import User
