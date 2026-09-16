"""Schemas para Debt (Gestao de Dividas)"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.debt import DebtStatus, DebtType
from app.models.household import OwnershipType


class DebtPaymentBase(BaseModel):
    amount: Decimal = Field(..., gt=0)
    payment_date: date = Field(default_factory=date.today)
    principal_amount: Decimal = Field(default=Decimal(0), ge=0)
    interest_amount: Decimal = Field(default=Decimal(0), ge=0)
    notes: str | None = None
    transaction_id: int | None = None


class DebtPaymentCreate(DebtPaymentBase):
    pass


class DebtPaymentResponse(DebtPaymentBase):
    id: int
    debt_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class DebtBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    type: DebtType = DebtType.OTHER
    creditor: str | None = Field(None, max_length=100)
    original_amount: Decimal = Field(..., gt=0)
    current_balance: Decimal = Field(..., ge=0)
    minimum_payment: Decimal = Field(default=Decimal(0), ge=0)
    interest_rate: Decimal = Field(default=Decimal(0), ge=0, le=100)
    interest_type: str = Field(default="monthly", pattern=r"^(monthly|yearly)$")
    start_date: date
    due_day: int | None = Field(None, ge=1, le=31)
    priority: int = Field(default=0, ge=0)
    account_id: int | None = None
    installment_series_id: int | None = None


class DebtCreate(DebtBase):
    ownership_type: OwnershipType = OwnershipType.PERSONAL


class DebtUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    type: DebtType | None = None
    creditor: str | None = Field(None, max_length=100)
    current_balance: Decimal | None = Field(None, ge=0)
    minimum_payment: Decimal | None = Field(None, ge=0)
    interest_rate: Decimal | None = Field(None, ge=0, le=100)
    due_day: int | None = Field(None, ge=1, le=31)
    priority: int | None = Field(None, ge=0)
    status: DebtStatus | None = None
    account_id: int | None = None


class DebtResponse(DebtBase):
    id: int
    user_id: int
    status: DebtStatus
    expected_payoff_date: date | None
    paid_off_date: date | None
    ownership_type: str = "personal"
    created_at: datetime
    updated_at: datetime

    # Campos calculados
    total_paid: Decimal = Decimal(0)
    progress_percentage: float = 0.0
    monthly_interest_amount: Decimal = Decimal(0)
    next_payment_date: date | None = None

    class Config:
        from_attributes = True


class DebtDetailResponse(DebtResponse):
    """Resposta detalhada com pagamentos"""

    payments: list[DebtPaymentResponse] = []
    payoff_projection: "DebtPayoffProjection | None" = None


class DebtPayoffProjection(BaseModel):
    """Projeção de quitação da dívida"""

    months_to_payoff: int
    total_interest_if_minimum: Decimal
    total_paid_if_minimum: Decimal
    payoff_date_if_minimum: date
    # Com pagamento extra
    extra_payment: Decimal | None = None
    months_saved: int | None = None
    interest_saved: Decimal | None = None
    payoff_date_with_extra: date | None = None


class DebtSummary(BaseModel):
    """Resumo de todas as dívidas para dashboard"""

    total_debts: int
    active_debts: int
    paid_off_debts: int
    total_owed: Decimal
    total_minimum_payments: Decimal
    total_interest_monthly: Decimal
    highest_interest_debt: "DebtHighlight | None" = None
    smallest_balance_debt: "DebtHighlight | None" = None
    debt_free_date: date | None = None


class DebtHighlight(BaseModel):
    """Destaque de dívida para estratégias"""

    debt_id: int
    name: str
    balance: Decimal
    interest_rate: Decimal
    monthly_interest: Decimal


class SnowballPlan(BaseModel):
    """
    Plano de quitação pelo método Snowball (Dave Ramsey)
    Foca em quitar a menor dívida primeiro para motivação
    """

    strategy: str = "snowball"
    monthly_payment: Decimal  # Valor total disponível para dívidas
    debts_order: list["SnowballDebtStep"]
    total_months: int
    total_interest: Decimal
    debt_free_date: date


class AvalanchePlan(BaseModel):
    """
    Plano de quitação pelo método Avalanche
    Foca em quitar a dívida com maior juros primeiro (matemático)
    """

    strategy: str = "avalanche"
    monthly_payment: Decimal
    debts_order: list["SnowballDebtStep"]
    total_months: int
    total_interest: Decimal
    debt_free_date: date
    interest_saved_vs_snowball: Decimal


class SnowballDebtStep(BaseModel):
    """Passo no plano de quitação"""

    debt_id: int
    debt_name: str
    starting_balance: Decimal
    interest_rate: Decimal
    monthly_payment: Decimal
    months_to_payoff: int
    payoff_date: date
    total_interest_paid: Decimal
    order: int


class PayoffStrategyComparison(BaseModel):
    """Comparação entre estratégias Snowball e Avalanche"""

    snowball: SnowballPlan
    avalanche: AvalanchePlan
    recommendation: str  # "snowball" ou "avalanche"
    recommendation_reason: str
    months_difference: int
    interest_difference: Decimal
