from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.models.household import OwnershipType
from app.models.transaction import PaymentMethod


class RecurrenceFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class RecurringStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class TransactionType(str, Enum):
    EXPENSE = "expense"
    INCOME = "income"


class RecurringCreate(BaseModel):
    """Schema para criar uma transacao recorrente"""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    amount: float = Field(..., gt=0)
    type: TransactionType = TransactionType.EXPENSE
    payment_method: PaymentMethod | None = None  # credit_card, pix, boleto, etc.
    account_id: int
    category_id: int | None = None
    frequency: RecurrenceFrequency
    day_of_month: int | None = Field(None, ge=1, le=31)
    day_of_week: int | None = Field(None, ge=0, le=6)
    start_date: date
    end_date: date | None = None
    ownership_type: OwnershipType = OwnershipType.PERSONAL


class RecurringUpdate(BaseModel):
    """Schema para atualizar uma transação recorrente"""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    amount: float | None = Field(None, gt=0)
    type: TransactionType | None = None
    payment_method: PaymentMethod | None = None
    account_id: int | None = None
    category_id: int | None = None
    frequency: RecurrenceFrequency | None = None
    day_of_month: int | None = Field(None, ge=1, le=31)
    day_of_week: int | None = Field(None, ge=0, le=6)
    end_date: date | None = None
    status: RecurringStatus | None = None


class RecurringResponse(BaseModel):
    """Schema de resposta de uma transacao recorrente"""

    id: int
    name: str
    description: str | None
    amount: float
    type: str
    payment_method: str | None = None
    account_id: int
    account_name: str | None = None
    category_id: int | None
    category_name: str | None = None
    frequency: str
    day_of_month: int | None
    day_of_week: int | None
    start_date: date
    end_date: date | None
    status: str
    ownership_type: str = "personal"
    last_generated_date: date | None
    next_due_date: date | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecurringSummary(BaseModel):
    """Resumo das transações recorrentes"""

    total_monthly_expenses: float
    total_monthly_income: float
    active_count: int
    paused_count: int


class RecurringFromSuggestionCreate(BaseModel):
    """Schema para criar recorrência a partir de sugestão detectada"""

    # Campos obrigatórios
    name: str = Field(..., min_length=1, max_length=100)
    amount: float = Field(..., gt=0)
    account_id: int

    # Campos da sugestão (opcionais com defaults)
    frequency: RecurrenceFrequency = RecurrenceFrequency.MONTHLY
    day_of_month: int | None = Field(None, ge=1, le=31)
    category_id: int | None = None
    category_name: str | None = None  # Alternativa ao category_id - busca por nome

    # Campos extras
    description: str | None = Field(None, max_length=500)
    start_date: date | None = None  # Se não informado, usa hoje
    payment_method: PaymentMethod | None = PaymentMethod.CREDIT_CARD
    type: TransactionType = TransactionType.EXPENSE
    known_service_id: int | None = None  # ID do serviço conhecido (opcional, para tracking)
    credit_card_id: int | None = None  # ID do cartão de crédito (para faturas)
    ownership_type: OwnershipType = OwnershipType.PERSONAL


# ============================================
# Schemas para Batch Create from Suggestion
# ============================================


class BatchRecurringFromSuggestionRequest(BaseModel):
    """Request para criar múltiplas recorrências de uma vez"""

    items: list[RecurringFromSuggestionCreate] = Field(min_length=1, max_length=50)


class BatchRecurringItemResult(BaseModel):
    """Resultado de um item do batch"""

    index: int
    success: bool
    recurring_id: int | None = None
    recurring_name: str | None = None
    error: str | None = None
    is_duplicate: bool = False


class BatchRecurringResponse(BaseModel):
    """Resposta do batch create"""

    total: int
    success_count: int
    duplicate_count: int
    error_count: int
    results: list[BatchRecurringItemResult]


class RecurringCancelRequest(BaseModel):
    """Schema para cancelamento de recorrencia"""

    cancel_from_month: int | None = Field(
        None, ge=1, le=12, description="Mes a partir do qual cancelar (1-12)"
    )
    cancel_from_year: int | None = Field(
        None, ge=2020, le=2100, description="Ano a partir do qual cancelar"
    )
    remove_projected: bool = Field(True, description="Remover transacoes projetadas?")

    @model_validator(mode="after")
    def validate_dates(self):
        # Se um for fornecido, ambos devem ser
        if (self.cancel_from_month is None) != (self.cancel_from_year is None):
            raise ValueError("cancel_from_month e cancel_from_year devem ser fornecidos juntos")
        return self
