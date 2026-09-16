"""
Modelo de Metas Financeiras (Goals)
Baseado nas metodologias YNAB, Cerbasi (PNIF) e Thiago Nigro
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class GoalType(str, Enum):
    """Tipo de meta financeira"""

    SAVINGS = "savings"  # Economia para algo específico
    EMERGENCY_FUND = "emergency"  # Fundo de emergência (Ramsey Baby Step 3)
    DEBT_FREE = "debt_free"  # Quitar dívidas
    INVESTMENT = "investment"  # Meta de investimento
    RETIREMENT = "retirement"  # Aposentadoria / PNIF
    PURCHASE = "purchase"  # Compra específica
    CUSTOM = "custom"  # Meta personalizada


class GoalStatus(str, Enum):
    """Status da meta"""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Goal(Base):
    """
    Meta financeira do usuário.
    Permite definir objetivos com prazo e acompanhar progresso.
    """

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Informações básicas
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(20))  # GoalType
    icon: Mapped[str | None] = mapped_column(String(50))
    color: Mapped[str | None] = mapped_column(String(7))  # hex color

    # Valores
    target_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # Valor alvo
    current_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)  # Valor atual
    initial_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)  # Valor inicial

    # Datas
    start_date: Mapped[date] = mapped_column(Date, default=date.today)
    target_date: Mapped[date | None] = mapped_column(Date)  # Prazo desejado
    completed_date: Mapped[date | None] = mapped_column(Date)  # Data de conclusão

    # Configurações
    monthly_contribution: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2)
    )  # Contribuição mensal sugerida
    auto_calculate_contribution: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Ordem de prioridade

    # Status
    status: Mapped[str] = mapped_column(String(20), default=GoalStatus.ACTIVE.value)
    ownership_type: Mapped[str] = mapped_column(
        String(20), default="personal"
    )  # personal, household

    # Vinculação opcional a conta específica
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="goals")
    account: Mapped["Account | None"] = relationship()
    contributions: Mapped[list["GoalContribution"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan", lazy="noload"
    )

    @property
    def progress_percentage(self) -> float:
        """Percentual de progresso da meta"""
        if self.target_amount <= 0:
            return 100.0
        return float((self.current_amount / self.target_amount) * 100)

    @property
    def remaining_amount(self) -> Decimal:
        """Valor restante para atingir a meta"""
        return max(Decimal(0), self.target_amount - self.current_amount)


class GoalContribution(Base):
    """
    Contribuição para uma meta.
    Registra cada depósito/aporte feito para a meta.
    """

    __tablename__ = "goal_contributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    contribution_date: Mapped[date] = mapped_column(Date, default=date.today)
    notes: Mapped[str | None] = mapped_column(String(200))

    # Vinculação opcional a transação
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    goal: Mapped["Goal"] = relationship(back_populates="contributions")
    transaction: Mapped["Transaction | None"] = relationship()


# Imports para evitar circular import
from .account import Account
from .transaction import Transaction
from .user import User
