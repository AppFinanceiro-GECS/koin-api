from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    license_id: Mapped[int | None] = mapped_column(ForeignKey("licenses.id"), nullable=True)
    reset_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reset_token_expires: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # License relationship - keep selectin for auth checks
    license: Mapped["License | None"] = relationship(
        back_populates="users", lazy="selectin", foreign_keys="User.license_id"
    )

    # Household membership - keep selectin for auth/permission checks
    household_membership: Mapped["HouseholdMember | None"] = relationship(
        back_populates="user",
        foreign_keys="HouseholdMember.user_id",
        uselist=False,
        lazy="selectin",
    )

    # All other relationships - use noload to avoid N+1 queries on every request
    # Load these explicitly with selectinload() when needed
    accounts: Mapped[list["Account"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    merchant_rules: Mapped[list["UserMerchantRule"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    installment_series: Mapped[list["InstallmentSeries"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    budgets: Mapped[list["Budget"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    goals: Mapped[list["Goal"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    debts: Mapped[list["Debt"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    invitations_sent: Mapped[list["Invitation"]] = relationship(
        back_populates="invited_by", lazy="noload", cascade="all, delete-orphan"
    )
    recurring_transactions: Mapped[list["RecurringTransaction"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    credit_cards: Mapped[list["CreditCard"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    benefit_cards: Mapped[list["BenefitCard"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    income_sources: Mapped[list["IncomeSource"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    income_split_rules: Mapped[list["IncomeSplitRule"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    credit_card_invoices: Mapped[list["CreditCardInvoice"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["APIKey"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    notification_preferences: Mapped[list["NotificationPreference"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    notification_settings: Mapped["NotificationSettings | None"] = relationship(
        back_populates="user", lazy="noload", uselist=False, cascade="all, delete-orphan"
    )
    push_subscriptions: Mapped[list["PushSubscription"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    automation_rules: Mapped[list["AutomationRule"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    receipts: Mapped[list["Receipt"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )

    # Gamification relationships
    badges: Mapped[list["UserBadge"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    streaks: Mapped[list["UserStreak"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    challenges: Mapped[list["UserChallenge"]] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )
    points: Mapped["UserPoints | None"] = relationship(
        back_populates="user", lazy="noload", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def household_role(self) -> str | None:
        """Retorna o role do usuario na familia"""
        if self.household_membership:
            return self.household_membership.role
        return None

    @property
    def is_license_owner(self) -> bool:
        """Verifica se eh o owner da licenca"""
        return self.household_membership is not None and self.household_membership.role == "owner"

    @property
    def can_invite_family_members(self) -> bool:
        """Verifica se pode convidar membros para a familia"""
        if not self.household_membership:
            return False
        return self.household_membership.can_invite_members


from .account import Account
from .api_key import APIKey
from .automation_rule import AutomationRule
from .benefit_card import BenefitCard
from .budget import Budget
from .credit_card import CreditCard
from .credit_card_invoice import CreditCardInvoice
from .debt import Debt
from .document import Document
from .gamification import UserBadge, UserChallenge, UserPoints, UserStreak
from .goal import Goal
from .household import HouseholdMember
from .income_source import IncomeSource
from .income_split_rule import IncomeSplitRule
from .installment import InstallmentSeries
from .invitation import Invitation
from .license import License
from .notification import (
    Notification,
    NotificationPreference,
    NotificationSettings,
    PushSubscription,
)
from .receipt import Receipt
from .recurring import RecurringTransaction
from .rule import UserMerchantRule
from .transaction import Transaction
