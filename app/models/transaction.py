from datetime import date, datetime
from enum import Enum

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class TransactionType(str, Enum):
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"


class PaymentMethod(str, Enum):
    """Metodo de pagamento utilizado na transacao"""

    CREDIT_CARD = "credit_card"  # Cartao de credito (vinculado a fatura)
    DEBIT_CARD = "debit_card"  # Cartao de debito (debito imediato)
    PIX = "pix"  # PIX (transferencia instantanea)
    BANK_TRANSFER = "bank_transfer"  # TED/DOC (transferencia bancaria)
    BOLETO = "boleto"  # Boleto bancario
    CASH = "cash"  # Dinheiro
    VOUCHER = "voucher"  # Vale generico (legado)
    # Tipos especificos de voucher (novos)
    VOUCHER_VA = "voucher_va"  # Vale Alimentacao
    VOUCHER_VR = "voucher_vr"  # Vale Refeicao
    VOUCHER_FLEX = "voucher_flex"  # Cartao Flex (VA + VR)
    VOUCHER_VT = "voucher_vt"  # Vale Transporte
    VOUCHER_OTHER = "voucher_other"  # Outros beneficios


class RecurrenceType(str, Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))

    # Credit card link (for expenses on credit card)
    credit_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("credit_cards.id", ondelete="SET NULL"), index=True
    )

    # Income source link (for income transactions)
    income_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("income_sources.id", ondelete="SET NULL"), index=True
    )

    # Invoice link (for credit card transactions)
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("credit_card_invoices.id", ondelete="SET NULL"), index=True
    )

    # Receipt link (for fiscal receipt transactions)
    receipt_id: Mapped[int | None] = mapped_column(
        ForeignKey("receipts.id", ondelete="SET NULL"), index=True
    )

    type: Mapped[str] = mapped_column(String(10))  # TransactionType
    payment_method: Mapped[str | None] = mapped_column(String(20), index=True)  # PaymentMethod
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)

    # Recorrência
    is_recurring: Mapped[bool] = mapped_column(default=False)
    recurrence_type: Mapped[str | None] = mapped_column(String(10))
    recurrence_parent_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"))
    recurring_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_transactions.id", ondelete="SET NULL"), index=True
    )

    # Transfer support - links two transactions together for transfers between accounts
    linked_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), index=True
    )

    # Parcelas
    installment_series_id: Mapped[int | None] = mapped_column(
        ForeignKey("installment_series.id", ondelete="SET NULL"), index=True
    )
    installment_number: Mapped[int | None] = mapped_column()  # Parcela atual (ex: 3)
    installment_total: Mapped[int | None] = mapped_column()  # Total de parcelas (ex: 12)
    is_paid: Mapped[bool] = mapped_column(default=True)  # Se a parcela foi paga

    # Income split support - links split-generated expenses back to original income
    source_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), index=True
    )

    # Tags (lista de strings)
    tags: Mapped[list | None] = mapped_column(JSON)

    # Metadados
    is_fixed: Mapped[bool] = mapped_column(default=False)  # gasto fixo vs variável
    ownership_type: Mapped[str] = mapped_column(
        String(20), default="personal"
    )  # personal, household
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships - use noload to avoid N+1 queries
    user: Mapped["User"] = relationship(back_populates="transactions")
    account: Mapped["Account"] = relationship(back_populates="transactions", lazy="noload")
    category: Mapped["Category | None"] = relationship(back_populates="transactions", lazy="noload")
    merchant: Mapped["Merchant | None"] = relationship(back_populates="transactions", lazy="noload")
    document: Mapped["Document | None"] = relationship(back_populates="transaction", lazy="noload")
    installment_series: Mapped["InstallmentSeries | None"] = relationship(
        back_populates="transactions", foreign_keys=[installment_series_id], lazy="noload"
    )
    recurring_source: Mapped["RecurringTransaction | None"] = relationship(
        back_populates="generated_transactions", foreign_keys=[recurring_id], lazy="noload"
    )
    audit_logs: Mapped[list["TransactionAudit"]] = relationship(
        back_populates="transaction", lazy="noload"
    )
    credit_card: Mapped["CreditCard | None"] = relationship(lazy="noload")
    income_source: Mapped["IncomeSource | None"] = relationship(
        back_populates="transactions", lazy="noload"
    )
    invoice: Mapped["CreditCardInvoice | None"] = relationship(
        back_populates="transactions", foreign_keys=[invoice_id], lazy="noload"
    )
    receipt: Mapped["Receipt | None"] = relationship(
        back_populates="items", foreign_keys=[receipt_id], lazy="noload"
    )
    payments: Mapped[list["TransactionPayment"]] = relationship(
        back_populates="transaction", lazy="noload", order_by="TransactionPayment.sequence"
    )
    # Split transactions - expenses generated from this income
    split_transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="source_transaction",
        foreign_keys="Transaction.source_transaction_id",
        lazy="noload",
    )
    # Source income that generated this split expense
    source_transaction: Mapped["Transaction | None"] = relationship(
        back_populates="split_transactions",
        foreign_keys=[source_transaction_id],
        remote_side=[id],
        lazy="noload",
    )

    # Computed properties for API responses
    @property
    def category_name(self) -> str | None:
        return self.category.name if self.category else None

    @property
    def account_name(self) -> str | None:
        return self.account.name if self.account else None

    @property
    def merchant_name(self) -> str | None:
        return self.merchant.name if self.merchant else None

    @property
    def credit_card_name(self) -> str | None:
        if self.credit_card and self.credit_card.account:
            return self.credit_card.account.name
        return None

    @property
    def income_source_name(self) -> str | None:
        return self.income_source.name if self.income_source else None

    @property
    def invoice_display(self) -> str | None:
        if self.invoice:
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
            month_name = months[self.invoice.reference_month - 1]
            return f"{month_name}/{self.invoice.reference_year}"
        return None

    @property
    def signed_amount(self) -> float:
        """Retorna o valor com sinal: negativo para despesas/saidas, positivo para receitas/entradas"""
        if self.type == TransactionType.EXPENSE.value:
            return -float(self.amount)
        # Para transfers, o sinal depende se é a transação de saída ou entrada
        # A transação de saída tem linked_transaction_id apontando para a entrada
        # A transação de entrada é a que não tem linked_transaction_id inicial
        if self.type == TransactionType.TRANSFER.value:
            # Se tem linked_transaction_id, é a transação original (saída = negativo)
            # Se não tem, é a transação linkada (entrada = positivo)
            # Após o link bidirecional, ambas terão linked_transaction_id
            # Usamos a convenção: a primeira criada (menor ID) é a saída
            if self.linked_transaction_id and self.linked_transaction_id > self.id:
                return -float(self.amount)  # Saída (esta é a original)
            return float(self.amount)  # Entrada
        return float(self.amount)

    @property
    def payment_method_display(self) -> str | None:
        """Retorna o nome amigavel do metodo de pagamento"""
        if not self.payment_method:
            return None
        display_names = {
            PaymentMethod.CREDIT_CARD.value: "Cartao de Credito",
            PaymentMethod.DEBIT_CARD.value: "Cartao de Debito",
            PaymentMethod.PIX.value: "PIX",
            PaymentMethod.BANK_TRANSFER.value: "Transferencia",
            PaymentMethod.BOLETO.value: "Boleto",
            PaymentMethod.CASH.value: "Dinheiro",
            PaymentMethod.VOUCHER.value: "Vale",
            PaymentMethod.VOUCHER_VA.value: "Vale Alimentacao",
            PaymentMethod.VOUCHER_VR.value: "Vale Refeicao",
            PaymentMethod.VOUCHER_FLEX.value: "Vale Flex",
            PaymentMethod.VOUCHER_VT.value: "Vale Transporte",
            PaymentMethod.VOUCHER_OTHER.value: "Outro Beneficio",
        }
        return display_names.get(self.payment_method, self.payment_method)

    @property
    def has_split_payment(self) -> bool:
        """Retorna True se a transacao tem pagamento dividido"""
        return len(self.payments) > 1 if self.payments else False

    @property
    def is_transfer_out(self) -> bool:
        """Retorna True se esta é a transação de saída de uma transferência"""
        if self.type != TransactionType.TRANSFER.value:
            return False
        # A transação com menor ID é a de saída (criada primeiro)
        if self.linked_transaction_id:
            return self.id < self.linked_transaction_id
        return False

    @property
    def is_transfer_in(self) -> bool:
        """Retorna True se esta é a transação de entrada de uma transferência"""
        if self.type != TransactionType.TRANSFER.value:
            return False
        # A transação com maior ID é a de entrada (criada segundo)
        if self.linked_transaction_id:
            return self.id > self.linked_transaction_id
        return False


class TransactionAudit(Base):
    """Log de alterações para auditoria"""

    __tablename__ = "transaction_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    field_name: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(String(50))  # manual, ocr_correction, rule
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    transaction: Mapped["Transaction"] = relationship(back_populates="audit_logs")


from .account import Account
from .category import Category
from .credit_card_invoice import CreditCardInvoice
from .document import Document
from .installment import InstallmentSeries
from .merchant import Merchant
from .receipt import Receipt
from .recurring import RecurringTransaction
from .transaction_payment import TransactionPayment
from .user import User
