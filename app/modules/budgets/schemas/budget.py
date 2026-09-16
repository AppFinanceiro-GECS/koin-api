"""Schemas para Budget (Orcamento)"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.budget import BudgetItemStatus
from app.models.household import OwnershipType


class BudgetItemBase(BaseModel):
    category_id: int
    planned_amount: Decimal = Field(..., ge=0)
    is_fixed: bool = False
    priority: int = 0
    notes: str | None = None


class BudgetItemCreate(BudgetItemBase):
    pass


class BudgetItemUpdate(BaseModel):
    planned_amount: Decimal | None = Field(None, ge=0)
    is_fixed: bool | None = None
    priority: int | None = None
    notes: str | None = None


class BudgetItemResponse(BudgetItemBase):
    id: int
    budget_id: int
    rollover_amount: Decimal
    created_at: datetime
    updated_at: datetime

    # Campos calculados (preenchidos pelo service)
    spent_amount: Decimal = Decimal(0)
    available_amount: Decimal = Decimal(0)
    percentage_used: float = 0.0
    category_name: str | None = None

    # Novos campos (inspirados em Envelopes)
    status: str = BudgetItemStatus.ON_TRACK.value  # Status dinâmico
    daily_allowance: Decimal = Decimal(0)  # Subsídio diário restante
    days_remaining: int = 0  # Dias restantes no mês

    class Config:
        from_attributes = True


class BudgetItemHistoryResponse(BaseModel):
    """Resposta de histórico de item de orçamento"""

    id: int
    budget_item_id: int
    transaction_id: int | None
    change_type: str
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    related_category_id: int | None = None
    related_category_name: str | None = None
    notes: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class BudgetBase(BaseModel):
    year: int = Field(..., ge=2020, le=2100)
    month: int = Field(..., ge=1, le=12)
    total_income_planned: Decimal = Field(default=Decimal(0), ge=0)
    allow_rollover: bool = True
    notes: str | None = None


class BudgetCreate(BudgetBase):
    items: list[BudgetItemCreate] = []
    ownership_type: OwnershipType = OwnershipType.PERSONAL


class BudgetUpdate(BaseModel):
    total_income_planned: Decimal | None = Field(None, ge=0)
    allow_rollover: bool | None = None
    notes: str | None = None


class BudgetResponse(BudgetBase):
    id: int
    user_id: int
    total_expense_planned: Decimal
    ownership_type: str = "personal"
    created_at: datetime
    updated_at: datetime
    items: list[BudgetItemResponse] = []

    # Campos calculados
    total_spent: Decimal = Decimal(0)
    total_available: Decimal = Decimal(0)
    total_income_actual: Decimal = Decimal(0)
    balance: Decimal = Decimal(0)
    health_score: float = 0.0  # 0-100, saude do orcamento

    class Config:
        from_attributes = True


class BudgetSummary(BaseModel):
    """Resumo do orçamento para dashboard"""

    year: int
    month: int
    total_planned: Decimal
    total_spent: Decimal
    total_available: Decimal
    percentage_used: float
    days_remaining: int
    daily_budget_remaining: Decimal
    categories_over_budget: int
    categories_on_track: int
    categories_warning: int = 0  # Categorias acima de 80%
    categories_depleted: int = 0  # Categorias atingiram 100%


class BudgetCopyRequest(BaseModel):
    """Request para copiar orçamento de outro mês"""

    source_year: int
    source_month: int
    include_rollover: bool = True


class BudgetComparisonResponse(BaseModel):
    """Comparação entre orçamento planejado e realizado"""

    category_id: int
    category_name: str
    planned: Decimal
    actual: Decimal
    difference: Decimal
    percentage: float
    status: str  # "on_track", "over", "under"


class BudgetTransferRequest(BaseModel):
    """Request para transferir orçamento entre categorias (inspirado em Envelopes)"""

    from_category_id: int = Field(..., description="Categoria de origem")
    to_category_id: int = Field(..., description="Categoria de destino")
    amount: Decimal = Field(..., gt=0, description="Valor a transferir")
    notes: str | None = Field(None, max_length=200, description="Observações da transferência")


class BudgetTransferResponse(BaseModel):
    """Resposta de transferência entre categorias"""

    from_item: BudgetItemResponse
    to_item: BudgetItemResponse
    amount: Decimal
    notes: str | None = None
    created_at: datetime
