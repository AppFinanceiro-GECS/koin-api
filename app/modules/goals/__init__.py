"""Goals module - Financial goals management"""

from app.modules.goals.routers.goals import router
from app.modules.goals.schemas.goal import (
    EmergencyFundCalculation,
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
from app.modules.goals.services.goal_service import GoalService

__all__ = [
    "router",
    "GoalService",
    "GoalCreate",
    "GoalUpdate",
    "GoalContributionCreate",
    "GoalResponse",
    "GoalDetailResponse",
    "GoalContributionResponse",
    "GoalProjection",
    "GoalSummary",
    "GoalMilestone",
    "EmergencyFundCalculation",
    "PNIFCalculation",
]
