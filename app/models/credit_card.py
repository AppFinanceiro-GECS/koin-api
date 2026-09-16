from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class PointsProgram(str, Enum):
    """Common points programs in Brazil"""

    LIVELO = "livelo"
    ESFERA = "esfera"
    SMILES = "smiles"
    TUDOAZUL = "tudoazul"
    LATAM_PASS = "latam_pass"
    MULTIPLUS = "multiplus"
    DOTZ = "dotz"
    CASHBACK = "cashback"
    OTHER = "other"


class CreditCard(Base):
    """
    Credit card details linked to an account of type CREDIT_CARD.
    Stores limit, points program, billing dates, etc.
    """

    __tablename__ = "credit_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), unique=True, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Credit limit
    credit_limit: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    # Billing cycle
    closing_day: Mapped[int] = mapped_column(Integer, default=1)  # Day of month (1-31)
    due_day: Mapped[int] = mapped_column(Integer, default=10)  # Day of month (1-31)

    # Points/Rewards program
    has_points: Mapped[bool] = mapped_column(Boolean, default=False)
    points_program: Mapped[str | None] = mapped_column(String(50))  # PointsProgram enum
    points_program_name: Mapped[str | None] = mapped_column(String(100))  # Custom name if OTHER
    points_factor: Mapped[float] = mapped_column(Numeric(6, 2), default=1.0)  # Points per R$1 spent
    points_factor_international: Mapped[float | None] = mapped_column(
        Numeric(6, 2)
    )  # Points for international purchases

    # Card details
    nickname: Mapped[str | None] = mapped_column(
        String(50)
    )  # User-friendly nickname: "Roxinho", "Cartão do trabalho"
    bank_id: Mapped[str | None] = mapped_column(String(50))  # Bank ID: 'nubank', 'itau', etc.
    card_brand: Mapped[str | None] = mapped_column(String(50))  # Visa, Mastercard, Elo, Amex, etc.
    card_variant: Mapped[str | None] = mapped_column(String(100))  # Platinum, Black, Infinite, etc.
    last_four_digits: Mapped[str | None] = mapped_column(String(4))

    # Annual fee
    annual_fee: Mapped[float | None] = mapped_column(Numeric(10, 2))
    annual_fee_frequency: Mapped[str] = mapped_column(
        String(20), default="monthly"
    )  # 'monthly' or 'yearly'
    annual_fee_waived: Mapped[bool] = mapped_column(Boolean, default=False)

    # Additional benefits
    benefits_notes: Mapped[str | None] = mapped_column(
        Text
    )  # Free text for benefits like lounge access, insurance, etc.

    # Invoice PDF password (encrypted for automatic PDF unlock)
    # IMPORTANT: This password is ONLY for unlocking password-protected invoice PDF files
    # It has no relation to the credit card security or bank account password
    invoice_password_encrypted: Mapped[str | None] = mapped_column(Text)  # Encrypted with Fernet

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    account: Mapped["Account"] = relationship(back_populates="credit_card_details")
    user: Mapped["User"] = relationship(back_populates="credit_cards")
    invoices: Mapped[list["CreditCardInvoice"]] = relationship(
        back_populates="credit_card",
        lazy="noload",
        order_by="desc(CreditCardInvoice.reference_year), desc(CreditCardInvoice.reference_month)",
    )


from .account import Account
from .credit_card_invoice import CreditCardInvoice
from .user import User
