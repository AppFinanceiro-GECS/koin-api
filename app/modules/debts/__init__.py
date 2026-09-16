"""Debts module - Debt management"""

from app.modules.debts.routers.debts import router
from app.modules.debts.schemas.debt import (
    AvalanchePlan,
    DebtCreate,
    DebtDetailResponse,
    DebtHighlight,
    DebtPaymentCreate,
    DebtPaymentResponse,
    DebtPayoffProjection,
    DebtResponse,
    DebtSummary,
    DebtUpdate,
    PayoffStrategyComparison,
    SnowballDebtStep,
    SnowballPlan,
)
from app.modules.debts.services.debt_service import DebtService

__all__ = [
    "router",
    "DebtService",
    "DebtCreate",
    "DebtUpdate",
    "DebtPaymentCreate",
    "DebtResponse",
    "DebtDetailResponse",
    "DebtPaymentResponse",
    "DebtPayoffProjection",
    "DebtSummary",
    "DebtHighlight",
    "SnowballPlan",
    "AvalanchePlan",
    "SnowballDebtStep",
    "PayoffStrategyComparison",
]
