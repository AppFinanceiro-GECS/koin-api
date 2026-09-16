from datetime import datetime

from pydantic import BaseModel, Field

from app.models.household import OwnershipType
from app.models.income_source import IncomeFrequency, IncomeType


class IncomeSourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: IncomeType
    source_name: str | None = None
    expected_amount: float | None = Field(None, ge=0)
    is_variable: bool = False
    frequency: IncomeFrequency = IncomeFrequency.MONTHLY
    payment_day: int | None = Field(None, ge=1, le=31)
    use_business_day: bool = False  # Se True, usa dia útil ao invés de dia fixo
    business_day_number: int | None = Field(
        None, ge=1, le=23
    )  # Qual dia útil (ex: 5 para 5º dia útil)
    benefit_card_number: str | None = Field(None, max_length=20)
    benefit_provider: str | None = None
    is_taxable: bool = True
    tax_category: str | None = None
    notes: str | None = None


class IncomeSourceCreate(IncomeSourceBase):
    account_id: int | None = None
    category_id: int | None = None
    ownership_type: OwnershipType = OwnershipType.PERSONAL


class IncomeSourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    type: IncomeType | None = None
    source_name: str | None = None
    expected_amount: float | None = Field(None, ge=0)
    is_variable: bool | None = None
    frequency: IncomeFrequency | None = None
    payment_day: int | None = Field(None, ge=1, le=31)
    use_business_day: bool | None = None
    business_day_number: int | None = Field(None, ge=1, le=23)
    account_id: int | None = None
    category_id: int | None = None
    benefit_card_number: str | None = Field(None, max_length=20)
    benefit_provider: str | None = None
    is_taxable: bool | None = None
    tax_category: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class IncomeSourceResponse(IncomeSourceBase):
    id: int
    user_id: int
    account_id: int | None
    category_id: int | None
    is_active: bool
    ownership_type: str
    created_at: datetime
    updated_at: datetime

    # Related data
    account_name: str | None = None
    category_name: str | None = None

    class Config:
        from_attributes = True


class IncomeSourceListResponse(BaseModel):
    """Simplified response for listing"""

    id: int
    name: str
    type: str
    source_name: str | None
    expected_amount: float | None
    is_variable: bool
    frequency: str
    payment_day: int | None
    use_business_day: bool
    business_day_number: int | None
    benefit_provider: str | None
    account_name: str | None
    is_active: bool

    class Config:
        from_attributes = True
