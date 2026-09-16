from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from ..core.utils import utc_now


class InvoiceStatus(str, Enum):
    """Status da fatura do cartão de crédito"""

    OPEN = "open"  # Período atual, acumulando transações
    CLOSED = "closed"  # Fechada, aguardando pagamento
    PAID = "paid"  # Paga integralmente
    PARTIAL = "partial"  # Parcialmente paga
    OVERDUE = "overdue"  # Vencida


class CreditCardInvoice(Base):
    """
    Fatura de cartão de crédito.
    Agrupa transações por período de cobrança e controla pagamento.
    """

    __tablename__ = "credit_card_invoices"
    __table_args__ = (
        UniqueConstraint(
            "credit_card_id", "reference_month", "reference_year", name="uq_invoice_card_period"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    credit_card_id: Mapped[int] = mapped_column(
        ForeignKey("credit_cards.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )

    # Período de referência
    reference_month: Mapped[int] = mapped_column(Integer)  # 1-12
    reference_year: Mapped[int] = mapped_column(Integer)
    closing_date: Mapped[date] = mapped_column(Date)  # Data de fechamento
    due_date: Mapped[date] = mapped_column(Date)  # Data de vencimento

    # Valores
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    minimum_payment: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    # Status e pagamento
    status: Mapped[str] = mapped_column(String(20), default=InvoiceStatus.OPEN.value)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Conta usada para pagamento
    payment_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL")
    )
    # Transação de pagamento gerada (mantido para compatibilidade)
    payment_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    # Lista de IDs de transações de pagamento (para pagamentos parciais múltiplos)
    payment_transaction_ids: Mapped[list[int] | None] = mapped_column(
        JSON, default=list, nullable=True
    )

    # Notas/observações
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="credit_card_invoices")
    credit_card: Mapped["CreditCard"] = relationship(back_populates="invoices")
    document: Mapped["Document | None"] = relationship(back_populates="invoice")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="invoice", foreign_keys="Transaction.invoice_id"
    )
    payment_account: Mapped["Account | None"] = relationship(foreign_keys=[payment_account_id])
    payment_transaction: Mapped["Transaction | None"] = relationship(
        foreign_keys=[payment_transaction_id],
        post_update=True,  # Evita referência circular
    )

    @property
    def remaining_amount(self) -> Decimal:
        """Valor restante a pagar"""
        return self.total_amount - self.paid_amount

    @property
    def is_overdue(self) -> bool:
        """Verifica se está vencida"""
        if self.status == InvoiceStatus.PAID.value:
            return False
        return date.today() > self.due_date

    @property
    def period_display(self) -> str:
        """Exibe o período formatado"""
        months = [
            "Jan",
            "Fev",
            "Mar",
            "Abr",
            "Mai",
            "Jun",
            "Jul",
            "Ago",
            "Set",
            "Out",
            "Nov",
            "Dez",
        ]
        return f"{months[self.reference_month - 1]}/{self.reference_year}"


from .account import Account
from .credit_card import CreditCard
from .document import Document
from .transaction import Transaction
from .user import User
