from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class IncomeType(str, Enum):
    """Types of income sources"""

    SALARY = "salary"  # Salario CLT
    FREELANCE = "freelance"  # Trabalho autonomo
    BUSINESS = "business"  # Empresa/MEI
    RENTAL = "rental"  # Aluguel
    INVESTMENT = "investment"  # Rendimentos de investimentos
    BENEFIT_VA = "benefit_va"  # Vale Alimentacao
    BENEFIT_VR = "benefit_vr"  # Vale Refeicao
    BENEFIT_VT = "benefit_vt"  # Vale Transporte
    BENEFIT_HEALTH = "benefit_health"  # Plano de Saude (reembolso)
    BENEFIT_OTHER = "benefit_other"  # Outros beneficios
    BONUS = "bonus"  # Bonus/PLR
    THIRTEENTH = "thirteenth"  # 13o salario
    VACATION = "vacation"  # Ferias
    PENSION = "pension"  # Aposentadoria/Pensao
    ALIMONY = "alimony"  # Pensao alimenticia recebida
    GIFT = "gift"  # Presente/Doacao
    OTHER = "other"  # Outros


class IncomeFrequency(str, Enum):
    """How often the income is received"""

    MONTHLY = "monthly"
    BIWEEKLY = "biweekly"
    WEEKLY = "weekly"
    YEARLY = "yearly"
    ONE_TIME = "one_time"
    VARIABLE = "variable"


class IncomeSource(Base):
    """
    Income sources for better tracking of where money comes from.
    Supports salary, benefits (VA, VR, VT), freelance, etc.
    """

    __tablename__ = "income_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(100))  # e.g., "Salario Empresa X", "VA Alelo"
    type: Mapped[str] = mapped_column(String(30))  # IncomeType enum

    # Source details
    source_name: Mapped[str | None] = mapped_column(String(100))  # Company name, client name, etc.

    # Amount
    expected_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))  # Expected/fixed amount
    is_variable: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # Amount varies month to month

    # Frequency and dates
    frequency: Mapped[str] = mapped_column(String(20), default="monthly")  # IncomeFrequency enum
    payment_day: Mapped[int | None] = mapped_column(Integer)  # Day of month when received (1-31)
    use_business_day: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # Use business day instead of fixed day
    business_day_number: Mapped[int | None] = mapped_column(
        Integer
    )  # Which business day (e.g., 5 for 5th business day)

    # Linked account (where money goes)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))

    # Category link (optional default category for transactions)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )

    # For benefits - card details
    benefit_card_number: Mapped[str | None] = mapped_column(
        String(20)
    )  # Last 4 digits of benefit card
    benefit_provider: Mapped[str | None] = mapped_column(
        String(50)
    )  # Alelo, Sodexo, VR, Flash, etc.

    # Tax info (optional)
    is_taxable: Mapped[bool] = mapped_column(Boolean, default=True)
    tax_category: Mapped[str | None] = mapped_column(String(50))  # CLT, PJ, Isento, etc.

    # Notes
    notes: Mapped[str | None] = mapped_column(Text)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ownership_type: Mapped[str] = mapped_column(
        String(20), default="personal"
    )  # personal, household

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="income_sources")
    account: Mapped["Account"] = relationship(back_populates="income_sources")
    category: Mapped["Category"] = relationship()
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="income_source")


from .account import Account
from .category import Category
from .transaction import Transaction
from .user import User
