"""Badge schemas for gamification"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class BadgeRarity(str, Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class BadgeCategory(str, Enum):
    REGISTRO = "registro"
    ECONOMIA = "economia"
    CONTROLE = "controle"
    DIVIDAS = "dividas"
    EDUCACAO = "educacao"
    STREAK = "streak"
    ESPECIAL = "especial"


class BadgeResponse(BaseModel):
    """Resposta de um badge"""

    id: str
    name: str
    description: str
    icon: str
    category: BadgeCategory
    rarity: BadgeRarity
    points_reward: int

    # Estado do usuário
    is_earned: bool = False
    earned_at: datetime | None = None
    seen_at: datetime | None = None
    progress: float | None = None  # 0.0 a 1.0 se não conquistado

    class Config:
        from_attributes = True


class BadgeEarnedEvent(BaseModel):
    """Evento quando badge é conquistado"""

    badge: BadgeResponse
    points_earned: int
    new_total_points: int


class BadgeListResponse(BaseModel):
    """Lista de badges"""

    badges: list[BadgeResponse]
    total_earned: int
    total_available: int
