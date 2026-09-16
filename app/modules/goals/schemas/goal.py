"""Schemas para Goal (Metas Financeiras)"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.goal import GoalStatus, GoalType
from app.models.household import OwnershipType


class GoalContributionBase(BaseModel):
    amount: Decimal = Field(..., gt=0)
    contribution_date: date = Field(default_factory=date.today)
    notes: str | None = None
    transaction_id: int | None = None


class GoalContributionCreate(GoalContributionBase):
    pass


class GoalContributionResponse(GoalContributionBase):
    id: int
    goal_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class GoalBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    type: GoalType = GoalType.SAVINGS
    icon: str | None = None
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    target_amount: Decimal = Field(..., gt=0)
    initial_amount: Decimal = Field(default=Decimal(0), ge=0)
    target_date: date | None = None
    priority: int = Field(default=0, ge=0)
    account_id: int | None = None


class GoalCreate(GoalBase):
    ownership_type: OwnershipType = OwnershipType.PERSONAL


class GoalUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    type: GoalType | None = None
    icon: str | None = None
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    target_amount: Decimal | None = Field(None, gt=0)
    target_date: date | None = None
    priority: int | None = Field(None, ge=0)
    status: GoalStatus | None = None
    account_id: int | None = None


class GoalResponse(GoalBase):
    id: int
    user_id: int
    current_amount: Decimal
    start_date: date
    completed_date: date | None
    monthly_contribution: Decimal | None
    auto_calculate_contribution: bool
    status: GoalStatus
    ownership_type: str = "personal"
    created_at: datetime
    updated_at: datetime

    # Campos calculados
    progress_percentage: float = 0.0
    remaining_amount: Decimal = Decimal(0)
    months_to_goal: int | None = None
    on_track: bool = True
    suggested_monthly: Decimal | None = None

    class Config:
        from_attributes = True


class GoalDetailResponse(GoalResponse):
    """Resposta detalhada com contribuições"""

    contributions: list[GoalContributionResponse] = []
    projection: "GoalProjection | None" = None


class GoalProjection(BaseModel):
    """Projeção de quando a meta será atingida"""

    current_pace_date: date | None  # Data prevista no ritmo atual
    target_pace_date: date | None  # Data prevista se seguir contribuição sugerida
    monthly_needed: Decimal  # Valor mensal necessário para atingir no prazo
    is_achievable: bool  # Se é possível atingir no prazo


class GoalSummary(BaseModel):
    """Resumo de todas as metas para dashboard"""

    total_goals: int
    active_goals: int
    completed_goals: int
    total_target: Decimal
    total_saved: Decimal
    total_remaining: Decimal
    overall_progress: float
    next_milestone: "GoalMilestone | None" = None


class GoalMilestone(BaseModel):
    """Próximo marco a ser atingido"""

    goal_id: int
    goal_name: str
    amount_to_milestone: Decimal
    milestone_type: str  # "25%", "50%", "75%", "complete"


class EmergencyFundCalculation(BaseModel):
    """Cálculo de fundo de emergência (Baby Step 3 - Ramsey)"""

    monthly_expenses: Decimal
    recommended_3_months: Decimal
    recommended_6_months: Decimal
    current_saved: Decimal
    months_covered: float
    status: str  # "none", "starter", "partial", "complete"


class PNIFCalculation(BaseModel):
    """
    Cálculo do PNIF - Patrimônio Necessário para Independência Financeira
    Metodologia Gustavo Cerbasi
    """

    annual_expenses: Decimal
    expected_return_rate: float  # Taxa de retorno anual esperada
    pnif_amount: Decimal  # Patrimônio necessário
    current_net_worth: Decimal
    percentage_achieved: float
    years_to_pnif: int | None  # Anos para atingir com poupança atual
    monthly_savings_needed: Decimal | None  # Poupança mensal necessária
