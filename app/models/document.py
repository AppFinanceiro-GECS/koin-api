from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    # RN016: IA indisponível; o arquivo está guardado e o scheduler reprocessa
    WAITING_AI = "waiting_ai"


class DocumentStage(str, Enum):
    """Etapa da leitura para o app mostrar o progresso (#37)"""

    RECEIVED = "received"  # arquivo guardado
    EXTRACTING = "extracting"  # IA lendo a fatura
    VALIDATING = "validating"  # conferindo soma e total
    DONE = "done"
    WAITING = "waiting"  # na fila da IA (RN016)
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
    COMPROVANTE_PIX = "comprovante_pix"
    EXTRATO = "extrato"
    EXTRATO_BANCARIO = "extrato_bancario"
    NOTA_FISCAL = "nota_fiscal"
    BOLETO = "boleto"
    NAO_FINANCEIRO = "nao_financeiro"

    @classmethod
    def from_string(cls, val: Any) -> "DocumentType":
        if not val:
            return cls.UNKNOWN
        if isinstance(val, cls):
            return val
        s = str(val).strip().lower()
        try:
            return cls(s)
        except ValueError:
            pass
        if "pix" in s:
            return cls.COMPROVANTE_PIX
        if "fatura" in s or "cartao" in s or "cartão" in s or "card" in s:
            return cls.FATURA_CARTAO
        if "cupom" in s:
            return cls.CUPOM_FISCAL
        if "comprovante" in s or "recibo" in s:
            return cls.COMPROVANTE
        if "extrato" in s:
            return cls.EXTRATO
        if "nota" in s or "danfe" in s or "nf" in s:
            return cls.NOTA_FISCAL
        if "boleto" in s:
            return cls.BOLETO
        if "statement" in s:
            return cls.STATEMENT
        if "invoice" in s:
            return cls.INVOICE
        if "receipt" in s:
            return cls.RECEIPT
        return cls.UNKNOWN


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("uq_documents_user_file_hash", "user_id", "file_hash", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)  # SHA256 para dedupe
    file_size: Mapped[int] = mapped_column()
    mime_type: Mapped[str] = mapped_column(String(100))
    original_filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.PENDING)
    document_type: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    # Código estável do catálogo (ai_failures.py); o app decide por ele, não pelo texto
    error_code: Mapped[str | None] = mapped_column(String(50))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Início do processamento atual: processing antigo = processo reiniciado no meio
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    stage: Mapped[str] = mapped_column(
        String(20), default=DocumentStage.RECEIVED, server_default="received"
    )
    # Retenção (#50): original e extracted_data apagados; a linha fica para o hash e o vínculo
    file_purged_at: Mapped[datetime | None] = mapped_column(DateTime)
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
