"""
Smart Shopping List Schemas - LLM-powered intelligent list generation
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.grocery import (
    GroceryCategory,
    NecessityType,
    ShoppingListSource,
    ShoppingListStatus,
)


class SmartListGenerateRequest(BaseModel):
    """Request to generate a smart shopping list using LLM analysis"""

    period_days: int = Field(default=90, ge=30, le=180)
    include_non_essential: bool = True
    filter_non_grocery: bool = Field(
        default=True, description="Filter out non-grocery items (restaurants, delivery, etc.)"
    )
    name: str | None = None


class OriginalProductDetail(BaseModel):
    """Detail of an original product from purchase history"""

    product_name: str
    purchase_date: date
    unit_price: float
    quantity: float
    merchant_name: str | None = None


class SmartListItemResponse(BaseModel):
    """Smart list item with LLM-generated insights"""

    product_type: str  # Normalized type (e.g., "Frango Congelado")
    display_name: str  # Shorter display name (e.g., "Frango")
    category: GroceryCategory
    necessity_type: NecessityType
    suggested_quantity: float
    unit: str
    estimated_price: float | None
    urgency: str  # high, medium, low
    reasoning: str  # LLM justification

    # Original products grouped into this item
    original_products: list[OriginalProductDetail]

    # Metrics
    purchase_count: int
    days_since_last_purchase: int
    avg_cycle_days: float | None = None


class ExcludedItem(BaseModel):
    """Item excluded from the list by LLM"""

    name: str
    reason: str


class SmartListLLMResponse(BaseModel):
    """Response structure expected from LLM"""

    shopping_list: list[SmartListItemResponse]
    excluded: list[ExcludedItem]
    insights: list[str]


class SmartListFullResponse(BaseModel):
    """Full response for smart list generation"""

    id: int
    user_id: int
    license_id: int | None
    name: str
    notes: str | None
    status: ShoppingListStatus
    source: ShoppingListSource
    ownership_type: str
    created_at: datetime
    updated_at: datetime

    # Smart list specific fields
    items: list[SmartListItemResponse]
    excluded: list[ExcludedItem]
    insights: list[str]

    # Computed
    total_items: int = 0
    estimated_total: float = 0
    creator_name: str | None = None

    class Config:
        from_attributes = True
