from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.transaction import PaymentMethod


class InvoiceBase(BaseModel):
    reference_month: int = Field(ge=1, le=12)
    reference_year: int = Field(ge=2000, le=2100)
    notes: str | None = None


class InvoiceCreate(InvoiceBase):
    credit_card_id: int
    closing_date: date_type | None = None
    due_date: date_type | None = None
    total_amount: float | None = None


class InvoiceFromDocument(BaseModel):
    """Criar fatura a partir de documento PDF"""

    document_id: int
    credit_card_id: int
    reference_month: int = Field(ge=1, le=12)
    reference_year: int = Field(ge=2000, le=2100)
    total_amount: float | None = None


class InvoiceUpdate(BaseModel):
    notes: str | None = None
    status: str | None = None
    minimum_payment: float | None = None


class InvoicePayment(BaseModel):
    """Registrar pagamento de fatura"""

    amount: float = Field(gt=0)
    payment_account_id: int
    payment_date: date_type | None = None
    payment_method: PaymentMethod | None = None  # pix, bank_transfer, debit_card, boleto


class InvoiceResponse(InvoiceBase):
    id: int
    user_id: int
    credit_card_id: int
    document_id: int | None

    closing_date: date_type
    due_date: date_type

    total_amount: float
    minimum_payment: float | None
    paid_amount: float
    remaining_amount: float

    status: str
    paid_at: datetime | None
    payment_account_id: int | None
    payment_transaction_id: int | None
    payment_transaction_ids: list[int] | None = None

    created_at: datetime
    updated_at: datetime

    # Dados relacionados
    credit_card_name: str | None = None
    payment_account_name: str | None = None
    period_display: str | None = None
    transaction_count: int = 0

    class Config:
        from_attributes = True


class InvoiceDetailResponse(InvoiceResponse):
    """Resposta detalhada com transacoes"""

    transactions: list["InvoiceTransactionResponse"] = []


class InvoiceTransactionResponse(BaseModel):
    """Transacao resumida para listagem na fatura"""

    id: int
    date: date_type
    description: str | None
    merchant_name: str | None
    category_name: str | None
    amount: float
    installment_number: int | None
    installment_total: int | None
    is_paid: bool = True  # True = confirmada, False = projetada

    class Config:
        from_attributes = True


class InvoiceSummary(BaseModel):
    """Resumo da fatura atual para exibir no card do cartao"""

    invoice_id: int | None
    reference_month: int
    reference_year: int
    period_display: str
    total_amount: float
    paid_amount: float
    remaining_amount: float
    status: str
    due_date: date_type | None
    days_until_due: int | None
    transaction_count: int


class CardDetectionResult(BaseModel):
    """Resultado da deteccao de cartao a partir do documento"""

    detected_cards: list["DetectedCardInfo"]
    suggested_card_id: int | None = None


class DetectedCardInfo(BaseModel):
    """Informacoes de um cartao detectado"""

    credit_card_id: int
    account_name: str
    last_four_digits: str | None
    match_score: int


# Atualizar referencia forward
InvoiceDetailResponse.model_rebuild()
