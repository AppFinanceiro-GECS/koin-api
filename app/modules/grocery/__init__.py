"""
Grocery (Mercado) Module

Manages grocery shopping tracking, shopping lists, and price history.
"""

from .routers import router
from .schemas import (
    CheapestPriceResponse,
    GroceryAnalyticsByCategory,
    GroceryAnalyticsByNecessity,
    GroceryAnalyticsSpending,
    GroceryBudgetStatus,
    GroceryInsights,
    GroceryProductCreate,
    GroceryProductResponse,
    GroceryProductUpdate,
    GroceryPurchaseBulkCreate,
    GroceryPurchaseComparison,
    GroceryPurchaseCreate,
    GroceryPurchaseResponse,
    GroceryPurchaseSummary,
    GroceryPurchaseUpdate,
    PriceHistoryResponse,
    ShoppingListCreate,
    ShoppingListGenerateRequest,
    ShoppingListItemCreate,
    ShoppingListItemResponse,
    ShoppingListItemUpdate,
    ShoppingListResponse,
    ShoppingListUpdate,
)
from .services import (
    GroceryAnalyticsService,
    GroceryService,
    PriceTrackingService,
    ShoppingListService,
)

__all__ = [
    "router",
    # Schemas
    "GroceryProductCreate",
    "GroceryProductUpdate",
    "GroceryProductResponse",
    "GroceryPurchaseCreate",
    "GroceryPurchaseBulkCreate",
    "GroceryPurchaseUpdate",
    "GroceryPurchaseResponse",
    "GroceryPurchaseSummary",
    "GroceryPurchaseComparison",
    "ShoppingListCreate",
    "ShoppingListUpdate",
    "ShoppingListResponse",
    "ShoppingListItemCreate",
    "ShoppingListItemUpdate",
    "ShoppingListItemResponse",
    "ShoppingListGenerateRequest",
    "GroceryAnalyticsSpending",
    "GroceryAnalyticsByCategory",
    "GroceryAnalyticsByNecessity",
    "GroceryInsights",
    "GroceryBudgetStatus",
    "PriceHistoryResponse",
    "CheapestPriceResponse",
    # Services
    "GroceryService",
    "ShoppingListService",
    "GroceryAnalyticsService",
    "PriceTrackingService",
]
