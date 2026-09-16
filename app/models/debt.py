"""
Modelo de Gestão de Dívidas (Debt)
Baseado nas metodologias Dave Ramsey (Snowball/Avalanche) e Gustavo Cerbasi
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class DebtType(str, Enum):
    """Tipo de dívida"""

    CREDIT_CARD = "credit_card"
    PERSONAL_LOAN = "personal_loan"
    CAR_LOAN = "car_loan"
    MORTGAGE = "mortgage"
    STUDENT_LOAN = "student_loan"
    MEDICAL = "medical"
    STORE_CREDIT = "store_credit"
    OTHER = "other"


class DebtStatus(str, Enum):
    """Status da dívida"""

    ACTIVE = "active"
    PAID_OFF = "paid_off"
    NEGOTIATING = "negotiating"
    DEFAULTED = "defaulted"


class PayoffStrategy(str, Enum):
    """Estratégia de quitação (Dave Ramsey)"""

    SNOWBALL = "snowball"  # Menor saldo primeiro (motivacional)
    AVALANCHE = "avalanche"  # Maior juros primeiro (matemático)


class Debt(Base):
    """
    Dívida do usuário.
    Permite rastrear dívidas e planejar quitação.
    """

    __tablename__ = "debts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Informações básicas
    name: Mapped[str] = mapped_column(String(100))  # Ex: "Cartão Nubank", "Financiamento Carro"
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(20))  # DebtType
    creditor: Mapped[str | None] = mapped_column(String(100))  # Nome do credor

    # Valores
    original_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # Valor original da dívida
    current_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # Saldo atual
    minimum_payment: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)  # Pagamento mínimo

    # Juros
    interest_rate: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=0
    )  # Taxa de juros mensal (%)
    interest_type: Mapped[str] = mapped_column(String(20), default="monthly")  # monthly, yearly

    # Datas
    start_date: Mapped[date] = mapped_column(Date)  # Data que contraiu a dívida
    due_day: Mapped[int | None] = mapped_column(Integer)  # Dia de vencimento (1-31)
    expected_payoff_date: Mapped[date | None] = mapped_column(Date)  # Data prevista de quitação
    paid_off_date: Mapped[date | None] = mapped_column(Date)  # Data de quitação real

    # Status
    status: Mapped[str] = mapped_column(String(20), default=DebtStatus.ACTIVE.value)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Ordem de prioridade
    ownership_type: Mapped[str] = mapped_column(
        String(20), default="personal"
    )  # personal, household

    # Vinculação opcional
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    installment_series_id: Mapped[int | None] = mapped_column(
        ForeignKey("installment_series.id", ondelete="SET NULL")
    )  # Vincula a série de parcelas se aplicável

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="debts")
    account: Mapped["Account | None"] = relationship()
    installment_series: Mapped["InstallmentSeries | None"] = relationship()
    payments: Mapped[list["DebtPayment"]] = relationship(
        back_populates="debt", cascade="all, delete-orphan", lazy="noload"
    )

    @property
    def total_paid(self) -> Decimal:
        """Total já pago desta dívida"""
        return sum(p.amount for p in self.payments) if self.payments else Decimal(0)

    @property
    def progress_percentage(self) -> float:
        """Percentual de progresso na quitação"""
        if self.original_amount <= 0:
            return 100.0
        paid = self.original_amount - self.current_balance
        return float((paid / self.original_amount) * 100)

    @property
    def monthly_interest_amount(self) -> Decimal:
        """Valor mensal de juros sobre saldo atual"""
        if self.interest_type == "yearly":
            monthly_rate = self.interest_rate / 12
        else:
            monthly_rate = self.interest_rate
        return self.current_balance * (monthly_rate / 100)


class DebtPayment(Base):
    """
    Pagamento de dívida.
    Registra cada pagamento feito para a dívida.
    """

    __tablename__ = "debt_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    debt_id: Mapped[int] = mapped_column(ForeignKey("debts.id", ondelete="CASCADE"), index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    principal_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0
    )  # Parte do principal
    interest_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)  # Parte dos juros
    payment_date: Mapped[date] = mapped_column(Date, default=date.today)
    notes: Mapped[str | None] = mapped_column(String(200))

    # Vinculação opcional a transação
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    debt: Mapped["Debt"] = relationship(back_populates="payments")
    transaction: Mapped["Transaction | None"] = relationship()


# Imports para evitar circular import
from .account import Account
from .installment import InstallmentSeries
from .transaction import Transaction
from .user import User
