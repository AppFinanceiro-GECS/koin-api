from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class ReceiptStatus(str, Enum):
    """Status do cupom fiscal"""

    PENDING = "pending"  # Aguardando confirmação
    CONFIRMED = "confirmed"  # Itens confirmados
    CANCELLED = "cancelled"  # Cancelado pelo usuário


# Display names for status (Portuguese)
RECEIPT_STATUS_DISPLAY = {
    ReceiptStatus.PENDING.value: "Pendente",
    ReceiptStatus.CONFIRMED.value: "Confirmado",
    ReceiptStatus.CANCELLED.value: "Cancelado",
}


class Receipt(Base):
    """
    Representa uma compra/cupom fiscal.
    Análogo ao CreditCardInvoice para faturas, permite:
    - Agrupar itens (Transactions) de um mesmo cupom
    - Vincular múltiplos pagamentos (ReceiptPayment) à compra, não aos itens
    - Cálculo de saldo correto por conta/cartão
    """

    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )

    # Estabelecimento
    store_name: Mapped[str] = mapped_column(String(200))
    store_cnpj: Mapped[str | None] = mapped_column(String(18))

    # Valores
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    discount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    # Data da compra
    purchase_date: Mapped[date] = mapped_column(Date, index=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default=ReceiptStatus.PENDING.value)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="receipts")
    document: Mapped["Document | None"] = relationship(back_populates="receipt")
    items: Mapped[list["Transaction"]] = relationship(
        back_populates="receipt", lazy="noload", order_by="Transaction.id"
    )
    payments: Mapped[list["ReceiptPayment"]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        lazy="noload",
        order_by="ReceiptPayment.sequence",
    )
    grocery_purchase: Mapped["GroceryPurchase | None"] = relationship(
        back_populates="receipt", uselist=False, lazy="noload"
    )

    @property
    def status_display(self) -> str:
        """Nome amigável do status"""
        return RECEIPT_STATUS_DISPLAY.get(self.status, self.status)

    @property
    def items_count(self) -> int:
        """Quantidade de itens no receipt"""
        return len(self.items) if self.items else 0

    @property
    def payments_count(self) -> int:
        """Quantidade de formas de pagamento"""
        return len(self.payments) if self.payments else 0

    @property
    def has_split_payment(self) -> bool:
        """Retorna True se tem mais de uma forma de pagamento"""
        return self.payments_count > 1


class ReceiptPayment(Base):
    """
    Forma de pagamento de um receipt (split payment).
    Cada pagamento representa um débito em uma conta específica.
    """

    __tablename__ = "receipt_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("receipts.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    benefit_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("benefit_cards.id", ondelete="SET NULL"), index=True
    )

    # Dados do pagamento
    payment_method: Mapped[str] = mapped_column(String(30))  # voucher_va, debit_card, pix, etc.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sequence: Mapped[int] = mapped_column(default=1)

    # Label original do OCR para debug
    original_label: Mapped[str | None] = mapped_column(String(200))

    # Campos de parcelamento (para pagamentos no crédito)
    is_installment: Mapped[bool] = mapped_column(default=False)
    installment_count: Mapped[int | None] = mapped_column()  # Total de parcelas (ex: 3)
    credit_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("credit_cards.id", ondelete="SET NULL"), index=True
    )
    installment_series_id: Mapped[int | None] = mapped_column(
        ForeignKey("installment_series.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    receipt: Mapped["Receipt"] = relationship(back_populates="payments")
    account: Mapped["Account"] = relationship(lazy="noload")
    benefit_card: Mapped["BenefitCard | None"] = relationship(lazy="noload")
    credit_card: Mapped["CreditCard | None"] = relationship(lazy="noload")
    installment_series: Mapped["InstallmentSeries | None"] = relationship(lazy="noload")

    @property
    def account_name(self) -> str | None:
        """Nome da conta"""
        return self.account.name if self.account else None

    @property
    def benefit_card_name(self) -> str | None:
        """Nome do cartão de benefício"""
        if self.benefit_card and self.benefit_card.account:
            return self.benefit_card.account.name
        return None


# Imports for relationships (at the end to avoid circular imports)
from .account import Account
from .benefit_card import BenefitCard
from .credit_card import CreditCard
from .document import Document
from .grocery import GroceryPurchase
from .installment import InstallmentSeries
from .transaction import Transaction
from .user import User
