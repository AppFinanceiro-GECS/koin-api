from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class ReceiptPaymentCreate(BaseModel):
    """Pagamento individual do receipt"""

    payment_method: str
    amount: Decimal = Field(gt=0)
    account_id: int
    benefit_card_id: int | None = None
    original_label: str | None = None

    # Campos de parcelamento (para pagamentos no crédito)
    is_installment: bool = False
    installment_count: int | None = None  # Total de parcelas (ex: 3)
    credit_card_id: int | None = None

    @model_validator(mode="after")
    def validate_installment(self):
        """Valida campos de parcelamento"""
        if self.is_installment:
            if not self.installment_count or self.installment_count < 2:
                raise ValueError("Parcelamento requer pelo menos 2 parcelas")
            if not self.credit_card_id:
                raise ValueError("Parcelamento requer cartão de crédito selecionado")
            if self.payment_method != "credit_card":
                raise ValueError("Parcelamento só é permitido para pagamentos no crédito")
        return self


class ReceiptItemCreate(BaseModel):
    """Item a ser convertido em Transaction"""

    description: str
    amount: Decimal = Field(gt=0)
    category_id: int | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    grocery_category: str | None = None  # Categoria de mercado (dairy, cleaning, etc)
    necessity_type: str | None = None  # essential ou non_essential


class ReceiptConfirmRequest(BaseModel):
    """Request para confirmar um receipt"""

    document_id: int

    # Dados do estabelecimento (extraídos ou editados)
    store_name: str
    store_cnpj: str | None = None
    purchase_date: date

    # Valores
    total_amount: Decimal
    subtotal: Decimal | None = None
    discount: Decimal | None = None

    # Itens selecionados
    items: list[ReceiptItemCreate]

    # Formas de pagamento com cartões vinculados
    payments: list[ReceiptPaymentCreate]

    # Categoria padrão para itens sem categoria
    default_category_id: int | None = None

    @model_validator(mode="after")
    def validate_payment_total(self):
        payment_total = sum(p.amount for p in self.payments)
        if abs(payment_total - self.total_amount) > Decimal("0.01"):
            raise ValueError(
                f"Soma dos pagamentos ({payment_total}) diferente do total ({self.total_amount})"
            )
        return self


class ReceiptPaymentResponse(BaseModel):
    """Resposta de um pagamento do receipt"""

    id: int
    payment_method: str
    amount: float
    account_id: int
    account_name: str | None = None
    benefit_card_id: int | None = None
    benefit_card_name: str | None = None
    sequence: int
    original_label: str | None = None

    # Campos de parcelamento
    is_installment: bool = False
    installment_count: int | None = None
    credit_card_id: int | None = None
    installment_series_id: int | None = None

    class Config:
        from_attributes = True


class ReceiptResponse(BaseModel):
    """Resposta completa de um receipt"""

    id: int
    document_id: int | None
    store_name: str
    store_cnpj: str | None
    purchase_date: date
    total_amount: float
    subtotal: float | None
    discount: float | None
    status: str
    status_display: str
    created_at: datetime
    confirmed_at: datetime | None

    # Contadores
    items_count: int
    payments_count: int
    has_split_payment: bool

    # Relacionamentos (eager load)
    payments: list[ReceiptPaymentResponse] = []

    class Config:
        from_attributes = True


class ReceiptListResponse(BaseModel):
    """Resposta simplificada para listagem"""

    id: int
    document_id: int | None
    store_name: str
    purchase_date: date
    total_amount: float
    status: str
    status_display: str
    items_count: int
    payments_count: int
    has_split_payment: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ReceiptUpdate(BaseModel):
    """Request para atualizar um receipt"""

    store_name: str | None = None
    store_cnpj: str | None = None
    purchase_date: date | None = None
    # Payments podem ser atualizados separadamente
