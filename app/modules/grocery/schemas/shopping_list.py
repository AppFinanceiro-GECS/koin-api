from datetime import datetime

from pydantic import BaseModel, Field

from app.models.grocery import (
    GroceryCategory,
    NecessityType,
    ShoppingListSource,
    ShoppingListStatus,
)


class ShoppingListItemBase(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, gt=0)
    unit: str = Field(default="un", max_length=10)
    category: GroceryCategory = GroceryCategory.OTHER
    necessity_type: NecessityType = NecessityType.ESSENTIAL
    priority: int = Field(default=0, ge=0)
    notes: str | None = Field(None, max_length=200)


class ShoppingListItemCreate(ShoppingListItemBase):
    product_id: int | None = None
    estimated_price: float | None = None


class ShoppingListItemUpdate(BaseModel):
    product_name: str | None = Field(None, min_length=1, max_length=200)
    quantity: float | None = Field(None, gt=0)
    unit: str | None = Field(None, max_length=10)
    category: GroceryCategory | None = None
    necessity_type: NecessityType | None = None
    is_checked: bool | None = None
    priority: int | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=200)
    estimated_price: float | None = None


class ShoppingListItemResponse(ShoppingListItemBase):
    id: int
    list_id: int
    product_id: int | None
    estimated_price: float | None
    is_checked: bool
    created_at: datetime

    # Display names
    category_display: str | None = None
    necessity_type_display: str | None = None

    # Computed
    estimated_total: float | None = None

    class Config:
        from_attributes = True


class ShoppingListBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    notes: str | None = None


class ShoppingListCreate(ShoppingListBase):
    items: list[ShoppingListItemCreate] | None = None


class ShoppingListUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    status: ShoppingListStatus | None = None
    notes: str | None = None


class ShoppingListResponse(ShoppingListBase):
    id: int
    user_id: int
    license_id: int | None
    status: ShoppingListStatus
    source: ShoppingListSource
    ownership_type: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    # Items
    items: list[ShoppingListItemResponse] = []

    # Computed
    total_items: int = 0
    checked_items: int = 0
    progress_percent: float = 0
    estimated_total: float = 0
    creator_name: str | None = None

    class Config:
        from_attributes = True


class ShoppingListGenerateRequest(BaseModel):
    """Request to generate a shopping list from history"""

    period_days: int = Field(default=90, ge=7, le=180)
    min_frequency: int = Field(default=1, ge=1, le=10)  # 1 = include single purchases
    min_urgency: float = Field(default=0.5, ge=0.0, le=2.0)  # 0.5 = include items at 50%+ of cycle
    default_cycle_days: int = Field(default=14, ge=7, le=60)  # Default cycle for single purchases
    include_non_essential: bool = True
    name: str | None = None  # Optional name for the list
