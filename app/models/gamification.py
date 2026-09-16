# backend/app/models/gamification.py
"""
Gamification System Models

Sistema de gamificação com:
- Badges (conquistas)
- Streaks (sequências)
- Challenges (desafios mensais)
- Points (pontos)
"""

from datetime import date, datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base

# =============================================================================
# ENUMS
# =============================================================================


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


class ChallengeDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ChallengeStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class StreakType(str, Enum):
    DAILY_REGISTER = "daily_register"  # Registrou transação no dia
    CHECK_IN = "check_in"  # Abriu o app
    BUDGET_ON_TRACK = "budget_on_track"  # Orçamento em dia


# =============================================================================
# BADGES
# =============================================================================


class BadgeDefinition(Base):
    """Catálogo de badges disponíveis no sistema"""

    __tablename__ = "badge_definitions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # ex: "first_transaction"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    icon: Mapped[str] = mapped_column(String(50), nullable=False)  # nome do ícone Lucide
    category: Mapped[str] = mapped_column(String(30), nullable=False)  # BadgeCategory
    rarity: Mapped[str] = mapped_column(String(20), nullable=False)  # BadgeRarity
    points_reward: Mapped[int] = mapped_column(Integer, default=10)

    # Critérios para desbloquear (JSON flexível)
    criteria_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # ex: "transaction_count", "streak_days", "goal_completed", "month_positive"
    criteria_value: Mapped[int] = mapped_column(Integer, nullable=False)
    # ex: 10 (para 10 transações), 7 (para 7 dias de streak)

    # Ordem de exibição
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)  # Não mostra até desbloquear

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    user_badges: Mapped[list["UserBadge"]] = relationship(back_populates="badge", lazy="noload")


class UserBadge(Base):
    """Badges conquistados por usuário"""

    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    badge_id: Mapped[str] = mapped_column(
        ForeignKey("badge_definitions.id", ondelete="CASCADE"), index=True
    )

    earned_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    seen_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )  # Quando viu a notificação

    # Índice único para evitar duplicatas
    __table_args__ = (UniqueConstraint("user_id", "badge_id", name="uq_user_badges_user_badge"),)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="badges")
    badge: Mapped["BadgeDefinition"] = relationship(back_populates="user_badges")


# =============================================================================
# STREAKS
# =============================================================================


class UserStreak(Base):
    """Streaks ativos do usuário"""

    __tablename__ = "user_streaks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    streak_type: Mapped[str] = mapped_column(String(30), nullable=False)  # StreakType

    current_count: Mapped[int] = mapped_column(Integer, default=0)
    longest_count: Mapped[int] = mapped_column(Integer, default=0)
    last_action_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Freeze (pular um dia sem perder streak)
    freeze_available: Mapped[int] = mapped_column(Integer, default=1)
    freeze_used_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Índice composto
    __table_args__ = (UniqueConstraint("user_id", "streak_type", name="uq_user_streaks_user_type"),)

    user: Mapped["User"] = relationship(back_populates="streaks")


class StreakHistory(Base):
    """Histórico de streaks (para analytics)"""

    __tablename__ = "streak_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    streak_type: Mapped[str] = mapped_column(String(30), nullable=False)

    started_at: Mapped[date] = mapped_column(Date, nullable=False)
    ended_at: Mapped[date] = mapped_column(Date, nullable=False)
    final_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ended_reason: Mapped[str] = mapped_column(String(20), nullable=False)  # "broken", "reset"


# =============================================================================
# CHALLENGES (DESAFIOS)
# =============================================================================


class ChallengeDefinition(Base):
    """Catálogo de desafios disponíveis"""

    __tablename__ = "challenge_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    icon: Mapped[str] = mapped_column(String(50), nullable=False)

    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)  # ChallengeDifficulty
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)  # 7, 30, etc

    # Tipo de desafio e critérios
    challenge_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Tipos: "no_spending_category", "save_percentage", "register_streak", "reduce_spending"
    criteria: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Ex: {"category_id": 5, "days": 7} para "sem delivery por 7 dias"
    # Ex: {"percentage": 10} para "economize 10%"
    # Ex: {"days": 30} para "registre todos os dias"

    # Recompensas
    points_reward: Mapped[int] = mapped_column(Integer, default=50)
    badge_reward_id: Mapped[str | None] = mapped_column(
        ForeignKey("badge_definitions.id", ondelete="SET NULL"), nullable=True
    )

    # Quando fica disponível
    available_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    available_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=True)  # Mensal

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    badge_reward: Mapped["BadgeDefinition | None"] = relationship()
    user_challenges: Mapped[list["UserChallenge"]] = relationship(
        back_populates="challenge", lazy="noload"
    )


class UserChallenge(Base):
    """Progresso do usuário em desafios"""

    __tablename__ = "user_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    challenge_id: Mapped[int] = mapped_column(
        ForeignKey("challenge_definitions.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[str] = mapped_column(String(20), default="active")  # ChallengeStatus

    # Progresso
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    # Ex: {"days_completed": 5, "days_required": 7}
    # Ex: {"amount_saved": 500, "target": 1000}

    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="challenges")
    challenge: Mapped["ChallengeDefinition"] = relationship(back_populates="user_challenges")


# =============================================================================
# PONTOS
# =============================================================================


class UserPoints(Base):
    """Saldo de pontos do usuário"""

    __tablename__ = "user_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    current_points: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_points: Mapped[int] = mapped_column(Integer, default=0)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    user: Mapped["User"] = relationship(back_populates="points")


class PointsTransaction(Base):
    """Histórico de movimentação de pontos"""

    __tablename__ = "points_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # Positivo ou negativo
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)

    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    # Ex: "badge_earned:first_transaction", "challenge_completed:5", "streak_milestone:7"

    reference_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # "badge", "challenge", "streak", "purchase"
    reference_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


# =============================================================================
# FORWARD REFERENCE
# =============================================================================
from .user import User
