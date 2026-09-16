"""Analytics module for financial data analysis and insights."""

from app.modules.analytics.routers.analytics import router
from app.modules.analytics.schemas.analytics import (
    AnalyticsSummary,
    CategorySummary,
    InsightResponse,
    InsightType,
    MerchantSummary,
)
from app.modules.analytics.services.analytics_service import AnalyticsService

__all__ = [
    "router",
    "AnalyticsSummary",
    "CategorySummary",
    "MerchantSummary",
    "InsightResponse",
    "InsightType",
    "AnalyticsService",
]
