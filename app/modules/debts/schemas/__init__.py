"""Debts schemas"""

from app.modules.debts.schemas.debt import (
    AvalanchePlan,
    DebtBase,
    DebtCreate,
    DebtDetailResponse,
    DebtHighlight,
    DebtPaymentBase,
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

__all__ = [
    "DebtPaymentBase",
    "DebtPaymentCreate",
    "DebtPaymentResponse",
    "DebtBase",
    "DebtCreate",
    "DebtUpdate",
    "DebtResponse",
    "DebtDetailResponse",
    "DebtPayoffProjection",
    "DebtSummary",
    "DebtHighlight",
    "SnowballPlan",
    "AvalanchePlan",
    "SnowballDebtStep",
    "PayoffStrategyComparison",
]
