from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.income_split_rule import SplitType


class IncomeSplitRuleBase(BaseModel):
    """Base schema with common fields for income split rules"""

    name: str = Field(min_length=1, max_length=100)
    split_type: SplitType
    percentage: float | None = Field(None, ge=0, le=100)  # 0-100%
    fixed_amount: float | None = Field(None, ge=0)
    category_id: int | None = None
    description_template: str | None = Field(None, max_length=200)
    priority: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_split_config(self):
        """Ensure percentage or fixed_amount is set based on split_type"""
        if self.split_type == SplitType.PERCENTAGE:
            if self.percentage is None:
                raise ValueError("percentage is required when split_type is 'percentage'")
        elif self.split_type == SplitType.FIXED:
            if self.fixed_amount is None:
                raise ValueError("fixed_amount is required when split_type is 'fixed'")
        return self


class IncomeSplitRuleCreate(IncomeSplitRuleBase):
    """Schema for creating a new income split rule"""

    pass


class IncomeSplitRuleUpdate(BaseModel):
    """Schema for updating an existing income split rule (all fields optional)"""

    name: str | None = Field(None, min_length=1, max_length=100)
    split_type: SplitType | None = None
    percentage: float | None = Field(None, ge=0, le=100)
    fixed_amount: float | None = Field(None, ge=0)
    category_id: int | None = None
    description_template: str | None = Field(None, max_length=200)
    is_active: bool | None = None
    priority: int | None = Field(None, ge=0)


class IncomeSplitRuleResponse(BaseModel):
    """Schema for returning an income split rule"""

    id: int
    user_id: int
    name: str
    split_type: str
    percentage: float | None
    fixed_amount: float | None
    category_id: int | None
    category_name: str | None = None
    description_template: str | None
    is_active: bool
    priority: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class IncomeSplitPreview(BaseModel):
    """Preview of what a split would generate for a given income amount"""

    rule_id: int
    rule_name: str
    split_type: str
    calculated_amount: float
    category_id: int | None
    category_name: str | None
    description_preview: str


class AppliedSplitResponse(BaseModel):
    """Response when splits are applied to an income transaction"""

    source_transaction_id: int
    generated_expenses: list[dict]  # List of created expense transactions
    total_split_amount: float
