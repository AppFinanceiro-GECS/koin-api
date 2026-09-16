from datetime import datetime

from pydantic import BaseModel, Field

from app.models.benefit_card import BenefitCardProvider, BenefitCardType
from app.models.household import OwnershipType


class BenefitCardBase(BaseModel):
    card_type: BenefitCardType
    provider: BenefitCardProvider | None = None
    last_four_digits: str | None = Field(None, max_length=4)
    linked_income_source_id: int | None = None
    expected_monthly_recharge: float | None = Field(None, ge=0)
    recharge_day: int | None = Field(None, ge=1, le=31)


class BenefitCardCreate(BenefitCardBase):
    # Account info - will create the linked account
    name: str = Field(min_length=1, max_length=100)
    color: str | None = None
    icon: str | None = None
    initial_balance: float = 0  # Current balance
    ownership_type: OwnershipType = OwnershipType.PERSONAL


class BenefitCardUpdate(BaseModel):
    card_type: BenefitCardType | None = None
    provider: BenefitCardProvider | None = None
    last_four_digits: str | None = Field(None, max_length=4)
    linked_income_source_id: int | None = None
    expected_monthly_recharge: float | None = Field(None, ge=0)
    recharge_day: int | None = Field(None, ge=1, le=31)
    is_active: bool | None = None
    # Account fields
    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = None
    icon: str | None = None
    initial_balance: float | None = None  # Update account balance


class BenefitCardResponse(BenefitCardBase):
    id: int
    account_id: int
    user_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Account info
    account_name: str | None = None
    account_balance: float = 0
    account_color: str | None = None
    account_icon: str | None = None

    # Display helpers
    card_type_display: str | None = None
    provider_display: str | None = None

    class Config:
        from_attributes = True


class BenefitCardListResponse(BaseModel):
    """Simplified response for listing"""

    id: int
    account_id: int
    name: str  # from account
    card_type: str
    card_type_display: str
    provider: str | None
    provider_display: str | None
    last_four_digits: str | None
    current_balance: float
    expected_monthly_recharge: float | None
    recharge_day: int | None
    color: str | None
    icon: str | None
    is_active: bool

    class Config:
        from_attributes = True


class BalanceAdjustmentRequest(BaseModel):
    """Request para ajuste manual de saldo"""

    adjustment_amount: float = Field(
        description="Valor do ajuste (positivo para adicionar, negativo para subtrair)"
    )
    reason: str = Field(min_length=3, max_length=500, description="Motivo do ajuste")


class BalanceAdjustmentResponse(BaseModel):
    """Response de ajuste de saldo"""

    old_balance: float
    adjustment: float
    new_balance: float
    transaction_id: int
    reason: str
    timestamp: datetime
