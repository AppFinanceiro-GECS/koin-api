from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.grocery import GroceryCategory, NecessityType
from app.models.household import OwnershipType


class GroceryPurchaseBase(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, gt=0)
    unit: str = Field(default="un", max_length=10)
    unit_price: float = Field(gt=0)
    total_price: float = Field(gt=0)
    category: GroceryCategory = GroceryCategory.OTHER
    necessity_type: NecessityType = NecessityType.ESSENTIAL
    purchase_date: date_type


class GroceryPurchaseCreate(GroceryPurchaseBase):
    transaction_id: int | None = None
    document_id: int | None = None
    product_id: int | None = None
    merchant_id: int | None = None
    merchant_name: str | None = None  # For creating new merchant
    ownership_type: OwnershipType = OwnershipType.PERSONAL


class GroceryPurchaseBulkItem(BaseModel):
    """Single item for bulk purchase creation"""

    product_name: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, gt=0)
    unit: str = Field(default="un", max_length=10)
    unit_price: float = Field(gt=0)
    total_price: float = Field(gt=0)
    category: GroceryCategory = GroceryCategory.OTHER
    necessity_type: NecessityType = NecessityType.ESSENTIAL


class GroceryPurchaseBulkCreate(BaseModel):
    """Create multiple purchase items at once (from a single receipt)"""

    items: list[GroceryPurchaseBulkItem] = Field(min_length=1, max_length=200)
    transaction_id: int | None = None
    document_id: int | None = None
    merchant_id: int | None = None
    merchant_name: str | None = None
    purchase_date: date_type
    ownership_type: OwnershipType = OwnershipType.PERSONAL


class GroceryPurchaseUpdate(BaseModel):
    product_name: str | None = Field(None, min_length=1, max_length=200)
    quantity: float | None = Field(None, gt=0)
    unit: str | None = Field(None, max_length=10)
    unit_price: float | None = Field(None, gt=0)
    total_price: float | None = Field(None, gt=0)
    category: GroceryCategory | None = None
    necessity_type: NecessityType | None = None
    product_id: int | None = None


class GroceryPurchaseResponse(GroceryPurchaseBase):
    id: int
    user_id: int
    transaction_id: int | None
    document_id: int | None
    product_id: int | None
    merchant_id: int | None
    ownership_type: str
    created_at: datetime

    # Display names
    category_display: str | None = None
    necessity_type_display: str | None = None
    merchant_name: str | None = None

    class Config:
        from_attributes = True


class CategorySummary(BaseModel):
    """Summary for a single category"""

    category: str
    category_display: str
    total: float
    count: int
    percentage: float


class NecessitySummary(BaseModel):
    """Summary by necessity type"""

    necessity_type: str
    necessity_type_display: str
    total: float
    count: int
    percentage: float


class GroceryPurchaseSummary(BaseModel):
    """Monthly summary of grocery purchases"""

    month: int
    year: int
    total: float
    essential_total: float
    non_essential_total: float
    item_count: int
    by_category: list[CategorySummary]
    by_necessity: list[NecessitySummary]


class MonthData(BaseModel):
    """Data for a single month"""

    total: float
    essential: float
    non_essential: float
    item_count: int
    by_category: dict[str, float]


class ComparisonItem(BaseModel):
    """Item that changed between months"""

    product_name: str
    current_quantity: float
    previous_quantity: float
    diff: float


class GroceryPurchaseComparison(BaseModel):
    """Comparison between two months"""

    current_month: MonthData
    previous_month: MonthData
    comparison: dict  # Contains diffs and analysis


# ==================== BACKFILL ====================


class BackfillRequest(BaseModel):
    """Request to backfill grocery purchases from existing transactions"""

    dry_run: bool = Field(default=True, description="Se True, apenas simula sem criar registros")
    category_names: list[str] | None = Field(
        default=None,
        description="Nomes das categorias a considerar (ex: Supermercado, alimentação)",
    )


class BackfillTransactionDetail(BaseModel):
    """Detail of a transaction being backfilled"""

    transaction_id: int
    description: str | None
    amount: float
    date: str  # YYYY-MM-DD
    status: str  # 'created', 'skipped', 'would_create'


class BackfillResponse(BaseModel):
    """Response from backfill operation"""

    transactions_found: int
    already_have_purchases: int
    to_create: int
    created: int  # 0 se dry_run=True
    details: list[BackfillTransactionDetail]
