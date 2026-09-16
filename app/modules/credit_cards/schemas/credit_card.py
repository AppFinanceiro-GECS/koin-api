from datetime import datetime

from pydantic import BaseModel, Field

from app.models.credit_card import PointsProgram
from app.models.household import OwnershipType


class CreditCardBase(BaseModel):
    credit_limit: float = Field(ge=0)
    closing_day: int = Field(ge=1, le=31, default=1)
    due_day: int = Field(ge=1, le=31, default=10)
    has_points: bool = False
    points_program: PointsProgram | None = None
    points_program_name: str | None = None
    points_factor: float = Field(ge=0, default=1.0)
    points_factor_international: float | None = None
    nickname: str | None = Field(None, max_length=50)
    bank_id: str | None = Field(None, max_length=50)
    card_brand: str | None = None
    card_variant: str | None = None
    last_four_digits: str | None = Field(None, max_length=4)
    annual_fee: float | None = None
    annual_fee_frequency: str = "monthly"  # 'monthly' or 'yearly'
    annual_fee_waived: bool = False
    benefits_notes: str | None = None


class CreditCardCreate(CreditCardBase):
    # Account info - will create the linked account
    name: str = Field(min_length=1, max_length=100)
    color: str | None = None
    icon: str | None = None
    initial_balance: float = 0  # Current credit card bill
    ownership_type: OwnershipType = OwnershipType.PERSONAL


class CreditCardUpdate(BaseModel):
    credit_limit: float | None = Field(None, ge=0)
    closing_day: int | None = Field(None, ge=1, le=31)
    due_day: int | None = Field(None, ge=1, le=31)
    has_points: bool | None = None
    points_program: PointsProgram | None = None
    points_program_name: str | None = None
    points_factor: float | None = Field(None, ge=0)
    points_factor_international: float | None = None
    nickname: str | None = Field(None, max_length=50)
    bank_id: str | None = Field(None, max_length=50)
    card_brand: str | None = None
    card_variant: str | None = None
    last_four_digits: str | None = Field(None, max_length=4)
    annual_fee: float | None = None
    annual_fee_frequency: str | None = None
    annual_fee_waived: bool | None = None
    benefits_notes: str | None = None
    is_active: bool | None = None
    # Account fields
    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = None
    icon: str | None = None


class CreditCardResponse(CreditCardBase):
    id: int
    account_id: int
    user_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    has_invoice_password: bool = (
        False  # Indicates if invoice password is saved (does not return the password)
    )

    # Account info
    account_name: str | None = None
    account_balance: float = 0
    account_color: str | None = None
    account_icon: str | None = None

    class Config:
        from_attributes = True


class CreditCardListResponse(BaseModel):
    """Simplified response for listing"""

    id: int
    account_id: int
    name: str  # from account
    nickname: str | None
    bank_id: str | None
    credit_limit: float
    current_balance: float  # from account
    available_limit: float  # computed: limit - balance
    closing_day: int
    due_day: int
    has_points: bool
    points_program: str | None
    points_factor: float | None
    card_brand: str | None
    card_variant: str | None
    last_four_digits: str | None
    annual_fee: float | None
    annual_fee_frequency: str
    annual_fee_waived: bool
    color: str | None
    icon: str | None
    is_active: bool

    class Config:
        from_attributes = True


class InvoicePasswordRequest(BaseModel):
    """Request to save invoice password"""

    password: str

    class Config:
        json_schema_extra = {"example": {"password": "mypassword123"}}
