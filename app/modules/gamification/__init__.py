"""
Gamification Module

Sistema de gamificação para o Biveto com:
- Badges (conquistas)
- Streaks (sequências de uso)
- Challenges (desafios mensais)
- Points (sistema de pontos)
"""

from .routers.gamification import router
from .schemas import (
    BadgeResponse,
    ChallengeListResponse,
    ChallengeResponse,
    GamificationEvent,
    GamificationSummary,
    StreakResponse,
    StreakWeekView,
)
from .services import (
    BadgeService,
    ChallengeService,
    GamificationService,
    PointsService,
    StreakService,
)

__all__ = [
    "router",
    "GamificationService",
    "BadgeService",
    "StreakService",
    "ChallengeService",
    "PointsService",
    "GamificationSummary",
    "GamificationEvent",
    "BadgeResponse",
    "StreakResponse",
    "StreakWeekView",
    "ChallengeResponse",
    "ChallengeListResponse",
]
