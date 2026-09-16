from datetime import date as date_type

from pydantic import BaseModel


class SpendingPoint(BaseModel):
    """Single point in spending timeline"""

    date: date_type
    total: float
    essential: float
    non_essential: float


class GroceryAnalyticsSpending(BaseModel):
    """Spending over time analytics"""

    period_start: date_type
    period_end: date_type
    total: float
    data_points: list[SpendingPoint]
    trend: str  # "up", "down", "stable"
    average_per_week: float


class CategoryBreakdown(BaseModel):
    """Single category breakdown"""

    category: str
    category_display: str
    total: float
    percentage: float
    item_count: int
    average_price: float


class GroceryAnalyticsByCategory(BaseModel):
    """Analytics grouped by category"""

    period_start: date_type
    period_end: date_type
    total: float
    categories: list[CategoryBreakdown]


class NecessityBreakdown(BaseModel):
    """Breakdown by necessity type"""

    necessity_type: str
    necessity_type_display: str
    total: float
    percentage: float
    item_count: int


class GroceryAnalyticsByNecessity(BaseModel):
    """Analytics grouped by necessity type"""

    period_start: date_type
    period_end: date_type
    total: float
    essential: NecessityBreakdown
    non_essential: NecessityBreakdown


class Insight(BaseModel):
    """Single insight"""

    type: str  # "warning", "info", "success"
    title: str
    description: str
    value: float | None = None
    percentage: float | None = None


class GroceryInsights(BaseModel):
    """AI-generated insights about spending"""

    insights: list[Insight]
    potential_savings: float
    top_expensive_items: list[dict]
    most_frequent_items: list[dict]


class GroceryBudgetStatus(BaseModel):
    """Budget status for the market category"""

    budget_amount: float | None
    spent_amount: float
    remaining: float | None
    percentage_used: float | None
    projected_total: float  # Projected spending by end of month
    on_track: bool


class PricePoint(BaseModel):
    """Single price point in history"""

    date: date_type
    price: float
    merchant_name: str | None


class PriceHistoryResponse(BaseModel):
    """Price history for a product"""

    product_id: int
    product_name: str
    unit: str
    current_price: float | None
    min_price: float | None
    max_price: float | None
    avg_price: float | None
    history: list[PricePoint]


class MerchantPrice(BaseModel):
    """Price at a specific merchant"""

    merchant_id: int
    merchant_name: str
    price: float
    unit: str
    last_seen: date_type


class CheapestPriceResponse(BaseModel):
    """Cheapest prices for products"""

    products: list[dict]  # List of products with their cheapest merchants
