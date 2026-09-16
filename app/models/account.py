from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class AccountType(str, Enum):
    WALLET = "wallet"
    BANK = "bank"
    CREDIT_CARD = "credit_card"
    INVESTMENT = "investment"
    BENEFIT_CARD = "benefit_card"  # VA, VR, VT, Flex, etc.


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))  # AccountType
    bank_id: Mapped[str | None] = mapped_column(String(50))  # Bank ID: 'nubank', 'itau', etc.
    balance: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    color: Mapped[str | None] = mapped_column(String(7))  # hex color
    icon: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(default=True)
    ownership_type: Mapped[str] = mapped_column(
        String(20), default="personal"
    )  # personal, household
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships - use noload to avoid N+1 queries
    user: Mapped["User"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account", lazy="noload"
    )
    installment_series: Mapped[list["InstallmentSeries"]] = relationship(
        back_populates="account", lazy="noload"
    )
    credit_card_details: Mapped["CreditCard | None"] = relationship(
        back_populates="account", uselist=False, lazy="noload"
    )
    benefit_card_details: Mapped["BenefitCard | None"] = relationship(
        back_populates="account", uselist=False, lazy="noload"
    )
    income_sources: Mapped[list["IncomeSource"]] = relationship(
        back_populates="account", lazy="noload"
    )


from .benefit_card import BenefitCard
from .credit_card import CreditCard
from .income_source import IncomeSource
from .installment import InstallmentSeries
from .transaction import Transaction
from .user import User
