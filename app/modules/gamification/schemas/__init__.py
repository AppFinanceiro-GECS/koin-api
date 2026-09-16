"""Gamification schemas"""

from datetime import datetime

from pydantic import BaseModel

from .badge import (
    BadgeCategory,
    BadgeEarnedEvent,
    BadgeListResponse,
    BadgeRarity,
    BadgeResponse,
)
from .challenge import (
    ChallengeDifficulty,
    ChallengeListResponse,
    ChallengeResponse,
    ChallengeStartResponse,
    ChallengeStatus,
)
from .points import (
    PointsHistoryResponse,
    PointsResponse,
    PointsTransactionResponse,
)
from .streak import (
    StreakDayInfo,
    StreakResponse,
    StreakType,
    StreakWeekView,
)


class GamificationSummary(BaseModel):
    """Resumo de gamificação para o dashboard"""

    # Pontos
    current_points: int
    lifetime_points: int

    # Badges
    badges_earned: int
    badges_total: int
    recent_badge: BadgeResponse | None  # Último conquistado

    # Streak principal
    main_streak: StreakResponse | None  # StreakResponse do daily_register

    # Desafios
    active_challenges: int
    completed_challenges_month: int

    # Novidades (não vistas)
    unseen_badges: int


class GamificationEvent(BaseModel):
    """Evento de gamificação (retornado após ações)"""

    badges_earned: list[BadgeResponse]
    streak_updated: StreakResponse | None
    challenges_updated: list[ChallengeResponse]
    points_earned: int
    new_total_points: int


__all__ = [
    "BadgeRarity",
    "BadgeCategory",
    "BadgeResponse",
    "BadgeEarnedEvent",
    "BadgeListResponse",
    "StreakType",
    "StreakResponse",
    "StreakDayInfo",
    "StreakWeekView",
    "ChallengeDifficulty",
    "ChallengeStatus",
    "ChallengeResponse",
    "ChallengeListResponse",
    "ChallengeStartResponse",
    "PointsResponse",
    "PointsTransactionResponse",
    "PointsHistoryResponse",
    "GamificationSummary",
    "GamificationEvent",
]
