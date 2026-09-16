from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class BenefitCardType(str, Enum):
    """Tipos de cartao de beneficio"""

    VA = "va"  # Vale Alimentacao (supermercados)
    VR = "vr"  # Vale Refeicao (restaurantes)
    FLEX = "flex"  # Flexivel (aceito como VA e VR)
    VT = "vt"  # Vale Transporte
    CULTURA = "cultura"  # Vale Cultura
    COMBUSTIVEL = "combustivel"  # Vale Combustivel


class BenefitCardProvider(str, Enum):
    """Operadoras de cartao de beneficio"""

    ALELO = "alelo"
    SODEXO = "sodexo"
    VR = "vr"
    TICKET = "ticket"
    FLASH = "flash"
    IFOOD = "ifood"
    CAJU = "caju"
    SWILE = "swile"
    PLUXEE = "pluxee"
    OTHER = "other"


class BenefitCard(Base):
    """
    Cartao de beneficio (VA/VR/VT/Flex) vinculado a uma conta.
    Similar ao CreditCard, mas para beneficios.
    """

    __tablename__ = "benefit_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), unique=True, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Tipo e operadora
    card_type: Mapped[str] = mapped_column(String(20), index=True)  # BenefitCardType
    provider: Mapped[str | None] = mapped_column(String(50))  # BenefitCardProvider

    # Identificacao
    last_four_digits: Mapped[str | None] = mapped_column(String(4))

    # Recarga (vinculo com income_source)
    linked_income_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("income_sources.id", ondelete="SET NULL")
    )
    expected_monthly_recharge: Mapped[float | None] = mapped_column(Numeric(12, 2))
    recharge_day: Mapped[int | None] = mapped_column(Integer)  # Dia do mes (1-31)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    account: Mapped["Account"] = relationship(back_populates="benefit_card_details")
    user: Mapped["User"] = relationship(back_populates="benefit_cards")
    linked_income_source: Mapped["IncomeSource | None"] = relationship(lazy="noload")

    @property
    def card_type_display(self) -> str:
        """Nome amigavel do tipo de cartao"""
        display_names = {
            BenefitCardType.VA.value: "Vale Alimentacao",
            BenefitCardType.VR.value: "Vale Refeicao",
            BenefitCardType.FLEX.value: "Flex (VA/VR)",
            BenefitCardType.VT.value: "Vale Transporte",
            BenefitCardType.CULTURA.value: "Vale Cultura",
            BenefitCardType.COMBUSTIVEL.value: "Vale Combustivel",
        }
        return display_names.get(self.card_type, self.card_type)

    @property
    def provider_display(self) -> str | None:
        """Nome amigavel da operadora"""
        if not self.provider:
            return None
        display_names = {
            BenefitCardProvider.ALELO.value: "Alelo",
            BenefitCardProvider.SODEXO.value: "Sodexo",
            BenefitCardProvider.VR.value: "VR",
            BenefitCardProvider.TICKET.value: "Ticket",
            BenefitCardProvider.FLASH.value: "Flash",
            BenefitCardProvider.IFOOD.value: "iFood Beneficios",
            BenefitCardProvider.CAJU.value: "Caju",
            BenefitCardProvider.SWILE.value: "Swile",
            BenefitCardProvider.PLUXEE.value: "Pluxee",
            BenefitCardProvider.OTHER.value: "Outro",
        }
        return display_names.get(self.provider, self.provider)


from .account import Account
from .income_source import IncomeSource
from .user import User
