from datetime import date, datetime
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class RecurrenceFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class RecurringStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class RecurringTransaction(Base):
    """Template de transação recorrente (aluguel, Netflix, etc.)"""

    __tablename__ = "recurring_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)

    # Dados da transação
    name: Mapped[str] = mapped_column(String(100))  # "Aluguel", "Netflix", etc.
    description: Mapped[str | None] = mapped_column(String(500))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    type: Mapped[str] = mapped_column(String(10), default="expense")  # expense ou income
    payment_method: Mapped[str | None] = mapped_column(String(20))  # credit_card, pix, boleto, etc.

    # Configuração de recorrência
    frequency: Mapped[str] = mapped_column(String(10))  # RecurrenceFrequency
    day_of_month: Mapped[int | None] = mapped_column(Integer)  # Dia do mês (1-31)
    day_of_week: Mapped[int | None] = mapped_column(Integer)  # Dia da semana (0=seg, 6=dom)

    # Período de vigência
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)  # None = sem fim

    # Controle
    status: Mapped[str] = mapped_column(String(20), default="active")  # RecurringStatus
    last_generated_date: Mapped[date | None] = mapped_column(Date)  # Última data gerada
    next_due_date: Mapped[date | None] = mapped_column(Date, index=True)  # Próxima data
    ownership_type: Mapped[str] = mapped_column(
        String(20), default="personal"
    )  # personal, household

    # Metadados
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="recurring_transactions")
    account: Mapped["Account"] = relationship()
    category: Mapped["Category | None"] = relationship()
    generated_transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="recurring_source", foreign_keys="Transaction.recurring_id"
    )


from .account import Account
from .category import Category
from .transaction import Transaction
from .user import User
