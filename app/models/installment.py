from datetime import date, datetime
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class InstallmentSeriesStatus(str, Enum):
    ACTIVE = "active"  # Série em andamento
    COMPLETED = "completed"  # Todas as parcelas pagas
    CANCELLED = "cancelled"  # Série cancelada


class InstallmentSeries(Base):
    """
    Agrupa parcelas de uma mesma compra parcelada.
    Permite rastrear compras parceladas e detectar duplicatas.
    """

    __tablename__ = "installment_series"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Identificação da compra
    description: Mapped[str] = mapped_column(String(500))
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id"))
    merchant_name: Mapped[str] = mapped_column(String(200))  # Nome original extraído

    # Valores
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2))  # Valor total da compra
    installment_amount: Mapped[float] = mapped_column(Numeric(12, 2))  # Valor de cada parcela
    installment_count: Mapped[int] = mapped_column()  # Total de parcelas (ex: 12)

    # Datas
    purchase_date: Mapped[date | None] = mapped_column(Date)  # Data da compra original
    first_installment_date: Mapped[date] = mapped_column(Date)  # Data da primeira parcela

    # Vínculo com conta/categoria/cartão
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    credit_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("credit_cards.id", ondelete="SET NULL"), index=True
    )

    # Status e controle
    status: Mapped[str] = mapped_column(String(20), default=InstallmentSeriesStatus.ACTIVE)
    paid_count: Mapped[int] = mapped_column(default=0)  # Quantas parcelas foram pagas

    # Vínculo à transação que originou a série
    # Isso garante que cada compra tenha sua própria série, mesmo com mesmo merchant/valor
    first_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,  # Uma transação só pode ser origem de uma série
        index=True,
    )

    # Metadados
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="installment_series")
    account: Mapped["Account"] = relationship(back_populates="installment_series")
    category: Mapped["Category | None"] = relationship()
    merchant: Mapped["Merchant | None"] = relationship()
    credit_card: Mapped["CreditCard | None"] = relationship()
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="installment_series",
        foreign_keys="Transaction.installment_series_id",
        lazy="noload",
    )
    # Relacionamento com a transação que originou a série
    first_transaction: Mapped["Transaction | None"] = relationship(
        foreign_keys=[first_transaction_id], lazy="noload"
    )

    @property
    def remaining_count(self) -> int:
        """Parcelas restantes"""
        return self.installment_count - self.paid_count

    @property
    def remaining_amount(self) -> float:
        """Valor restante a pagar"""
        return self.installment_amount * self.remaining_count

    @property
    def is_completed(self) -> bool:
        """Se todas as parcelas foram pagas"""
        return self.paid_count >= self.installment_count


# Imports circulares
from .account import Account
from .category import Category
from .credit_card import CreditCard
from .merchant import Merchant
from .transaction import Transaction
from .user import User
