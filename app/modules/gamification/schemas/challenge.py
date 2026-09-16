"""Challenge schemas for gamification"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ChallengeDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ChallengeStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class ChallengeResponse(BaseModel):
    """Resposta de um desafio"""

    id: int
    name: str
    description: str
    icon: str
    difficulty: ChallengeDifficulty

    status: ChallengeStatus | None = None  # None se não iniciado
    progress: dict | None = None  # Específico do tipo de desafio
    progress_percentage: float = 0.0  # 0.0 a 1.0

    points_reward: int
    badge_reward_id: str | None

    started_at: datetime | None = None
    expires_at: datetime | None = None
    completed_at: datetime | None = None

    # Para desafios não iniciados
    duration_days: int
    is_available: bool = True

    class Config:
        from_attributes = True


class ChallengeListResponse(BaseModel):
    """Lista de desafios organizados por status"""

    active: list[ChallengeResponse]
    completed: list[ChallengeResponse]
    failed: list[ChallengeResponse]
    available: list[ChallengeResponse]  # Não iniciados ainda


class ChallengeStartResponse(BaseModel):
    """Resposta ao iniciar um desafio"""

    challenge: ChallengeResponse
    message: str
