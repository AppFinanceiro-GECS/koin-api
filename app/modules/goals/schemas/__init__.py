"""Goals schemas"""

from app.modules.goals.schemas.goal import (
    EmergencyFundCalculation,
    GoalBase,
    GoalContributionBase,
    GoalContributionCreate,
    GoalContributionResponse,
    GoalCreate,
    GoalDetailResponse,
    GoalMilestone,
    GoalProjection,
    GoalResponse,
    GoalSummary,
    GoalUpdate,
    PNIFCalculation,
)

__all__ = [
    "GoalContributionBase",
    "GoalContributionCreate",
    "GoalContributionResponse",
    "GoalBase",
    "GoalCreate",
    "GoalUpdate",
    "GoalResponse",
    "GoalDetailResponse",
    "GoalProjection",
    "GoalSummary",
    "GoalMilestone",
    "EmergencyFundCalculation",
    "PNIFCalculation",
]
