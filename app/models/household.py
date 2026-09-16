from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
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


from .license import License
from .user import User
