"""
Modelo de Orçamento (Budget) - Sistema de orçamento por categoria
Baseado nas metodologias YNAB e Dave Ramsey

Evolução: Incorpora funcionalidades de Envelopes (histórico, status dinâmico,
transferências, subsídio diário) para uma experiência mais completa de orçamento.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class BudgetPeriodType(str, Enum):
    """Tipo de período do orçamento"""

    MONTHLY = "monthly"
    WEEKLY = "weekly"
    YEARLY = "yearly"


class BudgetItemStatus(str, Enum):
    """Status dinâmico do item de orçamento (baseado em Envelopes)"""

    ON_TRACK = "on_track"  # Verde - Dentro do orçamento
    WARNING = "warning"  # Laranja - Acima de 80%
    DEPLETED = "depleted"  # Amarelo - Atingiu 100%
    OVERSPENT = "overspent"  # Vermelho - Acima de 100%


class BudgetHistoryChangeType(str, Enum):
    """Tipo de mudança no histórico do orçamento (inspirado em EnvelopeHistory)"""

    SPEND = "spend"  # Gasto registrado automaticamente
    REFUND = "refund"  # Estorno/devolução
    ADJUSTMENT = "adjustment"  # Ajuste manual
    ROLLOVER = "rollover"  # Saldo rolado do mês anterior
    TRANSFER = "transfer"  # Transferência entre categorias


class Budget(Base):
    """
    Orçamento mensal do usuário.
    Cada usuário tem um orçamento por mês que contém limites por categoria.
    """

    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)  # 1-12

    # Valores totais planejados
    total_income_planned: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total_expense_planned: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    # Configurações
    allow_rollover: Mapped[bool] = mapped_column(
        Boolean, default=True
    )  # Permite rolar saldo não usado
    notes: Mapped[str | None] = mapped_column(Text)
    ownership_type: Mapped[str] = mapped_column(
        String(20), default="personal"
    )  # personal, household

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="budgets")
    items: Mapped[list["BudgetItem"]] = relationship(
        back_populates="budget", cascade="all, delete-orphan", lazy="noload"
    )


class BudgetItem(Base):
    """
    Item de orçamento por categoria.
    Define o limite planejado para cada categoria no mês.
    """

    __tablename__ = "budget_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    budget_id: Mapped[int] = mapped_column(ForeignKey("budgets.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)

    # Valores
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # Valor planejado
    rollover_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0
    )  # Valor do mês anterior

    # Configurações do item
    is_fixed: Mapped[bool] = mapped_column(Boolean, default=False)  # Gasto fixo (aluguel, etc)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Ordem de prioridade
    notes: Mapped[str | None] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    budget: Mapped["Budget"] = relationship(back_populates="items")
    category: Mapped["Category"] = relationship()
    history: Mapped[list["BudgetItemHistory"]] = relationship(
        back_populates="budget_item", cascade="all, delete-orphan", lazy="noload"
    )


class BudgetItemHistory(Base):
    """
    Histórico de mudanças em itens de orçamento.

    Inspirado no EnvelopeHistory, rastreia todas as mudanças no orçamento
    para auditoria e analytics. Vincula transações específicas para
    rastreabilidade completa.
    """

    __tablename__ = "budget_item_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    budget_item_id: Mapped[int] = mapped_column(
        ForeignKey("budget_items.id", ondelete="CASCADE"), index=True
    )
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), index=True
    )

    # Detalhes da mudança
    change_type: Mapped[str] = mapped_column(String(20))  # BudgetHistoryChangeType
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    balance_before: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    # Referência para transferências (de qual categoria veio/foi)
    related_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )

    # Metadados
    notes: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    budget_item: Mapped["BudgetItem"] = relationship(back_populates="history")
    transaction: Mapped["Transaction | None"] = relationship()
    related_category: Mapped["Category | None"] = relationship()

    __table_args__ = (Index("ix_budget_item_history_item_date", "budget_item_id", "created_at"),)


# Import para evitar circular import
from .category import Category
from .transaction import Transaction
from .user import User
