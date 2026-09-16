from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentType(str, Enum):
    RECEIPT = "receipt"
    INVOICE = "invoice"
    STATEMENT = "statement"
    UNKNOWN = "unknown"
    # Tipos brasileiros (compatível com LLM)
    CUPOM_FISCAL = "cupom_fiscal"
    FATURA_CARTAO = "fatura_cartao"
    COMPROVANTE = "comprovante"
    EXTRATO = "extrato"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)  # SHA256 para dedupe
    file_size: Mapped[int] = mapped_column()
    mime_type: Mapped[str] = mapped_column(String(100))
    original_filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.PENDING)
    document_type: Mapped[str | None] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Dados extraidos (para async processing)
    extracted_data: Mapped[dict | None] = mapped_column(JSON)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="documents")
    extractions: Mapped[list["DocumentExtraction"]] = relationship(
        back_populates="document", lazy="noload", order_by="desc(DocumentExtraction.version)"
    )
    transaction: Mapped["Transaction | None"] = relationship(
        back_populates="document", uselist=False
    )
    invoice: Mapped["CreditCardInvoice | None"] = relationship(
        back_populates="document", uselist=False
    )
    receipt: Mapped["Receipt | None"] = relationship(back_populates="document", uselist=False)


class DocumentExtraction(Base):
    """Resultado da extração de dados do documento (versionado)"""

    __tablename__ = "document_extractions"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(default=1)

    # Campos extraídos com confiança
    amount: Mapped[float | None] = mapped_column(Float)
    amount_confidence: Mapped[float | None] = mapped_column(Float)
    amount_source: Mapped[str | None] = mapped_column(String(20))  # PDF_TEXT, OCR, QR, MANUAL

    date: Mapped[datetime | None] = mapped_column(DateTime)
    date_confidence: Mapped[float | None] = mapped_column(Float)
    date_source: Mapped[str | None] = mapped_column(String(20))

    merchant_name: Mapped[str | None] = mapped_column(String(200))
    merchant_confidence: Mapped[float | None] = mapped_column(Float)
    merchant_cnpj: Mapped[str | None] = mapped_column(String(18))

    # Dados adicionais
    items: Mapped[dict | None] = mapped_column(JSON)  # lista de itens do cupom
    payment_method: Mapped[str | None] = mapped_column(String(50))
    installments: Mapped[int | None] = mapped_column()
    raw_text: Mapped[str | None] = mapped_column(Text)  # OCR bruto para debug

    suggested_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="extractions")


from .credit_card_invoice import CreditCardInvoice
from .receipt import Receipt
from .transaction import Transaction
from .user import User
