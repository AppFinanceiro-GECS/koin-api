"""Streak schemas for gamification"""

from datetime import date
from enum import Enum

from pydantic import BaseModel


class StreakType(str, Enum):
    DAILY_REGISTER = "daily_register"
    CHECK_IN = "check_in"
    BUDGET_ON_TRACK = "budget_on_track"


class StreakResponse(BaseModel):
    """Resposta de um streak"""

    streak_type: StreakType
    current_count: int
    longest_count: int
    last_action_date: date | None
    freeze_available: int

    # Dados calculados
    is_active_today: bool
    days_until_next_milestone: int | None  # Próximo badge
    next_milestone: int | None  # 7, 30, 100, etc

    class Config:
        from_attributes = True


class StreakDayInfo(BaseModel):
    """Informação de um dia no calendário de streak"""

    date: str
    day_name: str  # S, T, Q, Q, S, S, D
    completed: bool
    is_today: bool
    is_future: bool


class StreakWeekView(BaseModel):
    """Visualização da semana para o widget"""

    days: list[StreakDayInfo]
    current_streak: int
    streak_type: StreakType
    next_milestone: int | None
    days_until_next_milestone: int | None
