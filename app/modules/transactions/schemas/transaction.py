from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.models.household import OwnershipType
from app.models.transaction import PaymentMethod, TransactionType

# Data de transacao: entre 10 anos atras e 1 ano a frente. Parcelas futuras
# projetadas pelo installment_service tem a propria regra (nao passam por aqui).
TRANSACTION_DATE_PAST_YEARS = 10
TRANSACTION_DATE_FUTURE_YEARS = 1


def _validate_transaction_date(value: date_type) -> date_type:
    today = date_type.today()
    earliest = today.replace(year=today.year - TRANSACTION_DATE_PAST_YEARS)
    latest = today.replace(year=today.year + TRANSACTION_DATE_FUTURE_YEARS)
    if value < earliest or value > latest:
        raise ValueError(
            f"Data da transação deve estar entre {earliest.isoformat()} e {latest.isoformat()}"
        )
    return value


TransactionDate = Annotated[date_type, AfterValidator(_validate_transaction_date)]


class TransactionBase(BaseModel):
    type: TransactionType
    payment_method: PaymentMethod | None = None
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = "BRL"
    date: TransactionDate
    description: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    is_fixed: bool = False


class TransactionCreate(TransactionBase):
    account_id: int
    category_id: int | None = None
    merchant_name: str | None = None
    ownership_type: OwnershipType = OwnershipType.PERSONAL
    credit_card_id: int | None = None  # For credit card expenses
    income_source_id: int | None = None  # For income transactions

    # Transfer support - destination account for transfers between accounts
    destination_account_id: int | None = None  # Required when type=transfer

    # Campos para criar recorrencia junto com a transacao
    create_recurring: bool = False
    recurring_frequency: str | None = None  # 'daily', 'weekly', 'monthly', 'yearly'
    recurring_day_of_month: int | None = None  # Para frequencia mensal
    recurring_day_of_week: int | None = None  # Para frequencia semanal (0-6)

    # Campos de parcelamento
    is_installment: bool = False
    installment_current: int | None = None  # Numero da parcela atual (1-based)
    installment_total: int | None = None  # Total de parcelas
    installment_series_id: int | None = None  # Vincular a serie existente (opcional)
    create_future_installments: bool = False  # Criar parcelas futuras automaticamente

    # Campos de fatura (quando cartao de credito)
    invoice_month: int | None = None  # Mes de referencia da fatura (1-12)
    invoice_year: int | None = None  # Ano de referencia da fatura

    # Income split rules - IDs das regras a serem aplicadas (ex: dizimo, poupanca)
    # Apenas usado quando type=income. Gera despesas pendentes vinculadas.
    split_rule_ids: list[int] | None = None


class TransactionConfirm(BaseModel):
    """Confirmacao de transacao a partir de documento processado"""

    document_id: int | None = None  # Opcional para transacoes sem documento
    account_id: int
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    date: TransactionDate
    category_id: int | None = None
    merchant_name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    is_fixed: bool = False
    ownership_type: OwnershipType = OwnershipType.PERSONAL
    payment_method: PaymentMethod | None = None  # Metodo de pagamento
    credit_card_id: int | None = None  # For credit card expenses
    income_source_id: int | None = None  # For income transactions

    # Tipo de transacao extraido do documento (LLM)
    # Valores: compra, estorno, credito, pagamento, anuidade, encargo, saldo_anterior
    # Usado para determinar se e expense ou income
    extracted_transaction_type: str | None = None

    # Campos de fatura (quando vem de PDF de fatura)
    invoice_month: int | None = None  # Mes de referencia da fatura (1-12)
    invoice_year: int | None = None  # Ano de referencia da fatura

    # Campos de parcelamento
    is_installment: bool = False
    installment_current: int | None = None
    installment_total: int | None = None
    installment_series_id: int | None = None  # Vincular a serie existente
    mark_previous_as_paid: bool = False  # Marcar parcelas anteriores como pagas
    create_future_installments: bool = False  # Criar parcelas futuras

    # Forcar salvamento mesmo se detectar duplicado
    force_duplicate: bool = False

    # Campos para cupom fiscal (grocery tracking)
    quantity: float | None = None  # Quantidade do produto
    unit: str | None = None  # Unidade de medida (kg, un, L, etc)
    unit_price: float | None = None  # Preco unitario
    grocery_category: str | None = None  # Categoria de mercado detalhada
    necessity_type: str | None = None  # essential ou non_essential

    # Income split rules - IDs das regras a serem aplicadas (ex: dizimo, poupanca)
    split_rule_ids: list[int] | None = None


class TransactionUpdate(BaseModel):
    amount: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)
    date: TransactionDate | None = None
    type: TransactionType | None = None
    payment_method: PaymentMethod | None = None
    account_id: int | None = None
    category_id: int | None = None
    merchant_name: str | None = None
    description: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    is_fixed: bool | None = None
    is_paid: bool | None = None
    invoice_id: int | None = None  # Para mover transacao entre faturas


class TransactionResponse(TransactionBase):
    id: int
    account_id: int
    category_id: int | None
    merchant_id: int | None
    document_id: int | None
    credit_card_id: int | None = None
    invoice_id: int | None = None
    income_source_id: int | None = None
    is_recurring: bool
    is_paid: bool = True
    installment_series_id: int | None = None
    installment_number: int | None
    installment_total: int | None
    ownership_type: str = "personal"
    created_at: datetime
    updated_at: datetime

    # Transfer support
    linked_transaction_id: int | None = None
    is_transfer_out: bool = False  # True se é a saída de uma transferência
    is_transfer_in: bool = False  # True se é a entrada de uma transferência

    # Income split support
    source_transaction_id: int | None = None  # ID da receita que gerou esta despesa

    # Dados relacionados
    category_name: str | None = None
    account_name: str | None = None
    merchant_name: str | None = None
    credit_card_name: str | None = None
    income_source_name: str | None = None
    invoice_display: str | None = None  # Ex: "Jan/2026"
    payment_method_display: str | None = None  # Ex: "Cartao de Credito"
    signed_amount: float | None = None  # Valor com sinal (negativo para despesas)

    # Transfer related account name (for display purposes)
    linked_account_name: str | None = None  # Nome da conta de destino/origem da transferência

    # Indicador de parcelamento
    @property
    def is_installment(self) -> bool:
        return self.installment_number is not None and self.installment_total is not None

    class Config:
        from_attributes = True


# ============================================
# Schemas para Batch Confirm
# ============================================


class BatchConfirmItem(BaseModel):
    """Item individual do batch confirm - mesmo schema do TransactionConfirm"""

    document_id: int | None = None
    account_id: int
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    date: TransactionDate
    category_id: int | None = None
    merchant_name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    is_fixed: bool = False
    ownership_type: OwnershipType = OwnershipType.PERSONAL
    payment_method: PaymentMethod | None = None
    credit_card_id: int | None = None
    income_source_id: int | None = None
    extracted_transaction_type: str | None = None  # Tipo extraido do LLM
    invoice_month: int | None = None
    invoice_year: int | None = None
    is_installment: bool = False
    installment_current: int | None = None
    installment_total: int | None = None
    installment_series_id: int | None = None
    mark_previous_as_paid: bool = False
    create_future_installments: bool = False
    force_duplicate: bool = False
    # Campos para cupom fiscal (grocery tracking)
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    grocery_category: str | None = None
    necessity_type: str | None = None
    # Income split rules
    split_rule_ids: list[int] | None = None


class BatchConfirmRequest(BaseModel):
    """Request para confirmar múltiplas transações de uma vez"""

    items: list[BatchConfirmItem] = Field(min_length=1, max_length=100)

    # Informacoes do cartao extraidas do PDF (para atualizar o cartao automaticamente)
    card_closing_day: int | None = None  # Dia de fechamento extraido do PDF (1-31)
    card_due_day: int | None = None  # Dia de vencimento extraido do PDF (1-31)


class BatchConfirmItemResult(BaseModel):
    """Resultado de um item do batch"""

    index: int
    success: bool
    transaction_id: int | None = None
    error: str | None = None
    is_duplicate: bool = False


class BatchConfirmResponse(BaseModel):
    """Resposta do batch confirm"""

    total: int
    success_count: int
    duplicate_count: int
    error_count: int
    results: list[BatchConfirmItemResult]


# ============================================
# Schemas para Split Payment (pagamento dividido)
# ============================================


class SplitPaymentItem(BaseModel):
    """Item de pagamento em uma transacao com pagamento dividido"""

    payment_method: PaymentMethod
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    account_id: int
    benefit_card_id: int | None = None  # Se for pagamento com VA/VR
    credit_card_id: int | None = None  # Se for pagamento com cartao de credito


class SplitPaymentRequest(BaseModel):
    """Request para criar transacao com pagamento dividido"""

    document_id: int | None = None
    date: TransactionDate
    total_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    description: str | None = None
    merchant_name: str | None = None
    category_id: int | None = None
    ownership_type: OwnershipType = OwnershipType.PERSONAL
    tags: list[str] | None = None
    is_fixed: bool = False
    payments: list[SplitPaymentItem] = Field(min_length=2)  # Minimo 2 para ser split

    # Campos para cupom fiscal (grocery tracking)
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    grocery_category: str | None = None
    necessity_type: str | None = None


class SplitPaymentResponse(BaseModel):
    """Resposta de transacao com pagamento dividido"""

    transaction_id: int
    total_amount: float
    payments: list["TransactionPaymentResponse"]


class TransactionPaymentResponse(BaseModel):
    """Resposta de um pagamento individual"""

    id: int
    payment_method: str
    payment_method_display: str
    amount: float
    account_id: int
    account_name: str | None = None
    benefit_card_id: int | None = None
    credit_card_id: int | None = None
    sequence: int


class DetectedPaymentMethod(BaseModel):
    """Metodo de pagamento detectado pelo OCR"""

    payment_method: str  # voucher_va, debit_card, etc.
    amount: float
    label: str  # Label original do cupom: "CARTAO ALIMENTACAO", "DEBITO"


class SuggestSplitResponse(BaseModel):
    """Sugestao de split baseada em deteccao do OCR"""

    detected_payments: list[DetectedPaymentMethod]
    total_detected: float
    suggested_benefit_card_id: int | None = None  # Se detectou VA/VR, sugere cartao cadastrado
    suggested_benefit_card_name: str | None = None
