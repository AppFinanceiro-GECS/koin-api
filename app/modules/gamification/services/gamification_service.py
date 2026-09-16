"""Gamification Service - Main Orchestrator"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gamification import StreakType
from app.models.transaction import Transaction
from app.models.user import User

from ..schemas import (
    BadgeResponse,
    ChallengeListResponse,
    ChallengeResponse,
    GamificationEvent,
    GamificationSummary,
    StreakWeekView,
)
from .badge_service import BadgeService
from .challenge_service import ChallengeService
from .points_service import PointsService
from .streak_service import StreakService


class GamificationService:
    """Serviço orquestrador principal de gamificação"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.badge_service = BadgeService(db)
        self.streak_service = StreakService(db)
        self.challenge_service = ChallengeService(db)
        self.points_service = PointsService(db)

    # =========================================================================
    # AÇÕES DO USUÁRIO (chamados de outros services)
    # =========================================================================

    async def on_transaction_created(
        self, user: User, transaction: Transaction
    ) -> GamificationEvent:
        """
        Chamado quando uma transação é criada.
        Retorna eventos de gamificação (badges, streaks, etc)
        """
        badges_earned: list[BadgeResponse] = []
        challenges_updated: list[ChallengeResponse] = []
        points_earned = 0

        # 1. Atualizar streak de registro diário
        streak = await self.streak_service.record_action(user, StreakType.DAILY_REGISTER)
        streak_response = await self.streak_service.get_streak(user, StreakType.DAILY_REGISTER)

        # 2. Verificar badges de transação
        transaction_badges = await self.badge_service.check_transaction_badges(user)
        badges_earned.extend(transaction_badges)

        # 3. Verificar badges de streak
        streak_badges = await self.badge_service.check_streak_badges(user, streak)
        badges_earned.extend(streak_badges)

        # 4. Atualizar progresso de desafios
        challenges = await self.challenge_service.on_transaction(user, transaction)
        challenges_updated.extend(challenges)

        # 5. Calcular pontos ganhos
        for badge in badges_earned:
            points_earned += badge.points_reward

        # Obter saldo atual
        points_balance = await self.points_service.get_or_create_balance(user)

        return GamificationEvent(
            badges_earned=badges_earned,
            streak_updated=streak_response,
            challenges_updated=challenges_updated,
            points_earned=points_earned,
            new_total_points=points_balance.current_points,
        )

    async def on_goal_created(self, user: User) -> GamificationEvent:
        """Chamado quando uma meta é criada"""
        badges_earned = await self.badge_service.check_goal_badges(user)
        points_earned = sum(b.points_reward for b in badges_earned)

        points_balance = await self.points_service.get_or_create_balance(user)

        return GamificationEvent(
            badges_earned=badges_earned,
            streak_updated=None,
            challenges_updated=[],
            points_earned=points_earned,
            new_total_points=points_balance.current_points,
        )

    async def on_goal_completed(self, user: User) -> GamificationEvent:
        """Chamado quando uma meta é atingida"""
        badges_earned = await self.badge_service.check_goal_badges(user)
        points_earned = sum(b.points_reward for b in badges_earned)

        points_balance = await self.points_service.get_or_create_balance(user)

        return GamificationEvent(
            badges_earned=badges_earned,
            streak_updated=None,
            challenges_updated=[],
            points_earned=points_earned,
            new_total_points=points_balance.current_points,
        )

    async def on_debt_paid(self, user: User) -> GamificationEvent:
        """Chamado quando uma dívida é quitada"""
        badges_earned = await self.badge_service.check_debt_badges(user)
        points_earned = sum(b.points_reward for b in badges_earned)

        points_balance = await self.points_service.get_or_create_balance(user)

        return GamificationEvent(
            badges_earned=badges_earned,
            streak_updated=None,
            challenges_updated=[],
            points_earned=points_earned,
            new_total_points=points_balance.current_points,
        )

    async def on_month_closed(self, user: User, month: date) -> GamificationEvent:
        """
        Chamado no fechamento do mês (via scheduler/cron).
        Verifica badges de controle financeiro.
        """
        badges_earned: list[BadgeResponse] = []
        challenges_updated: list[ChallengeResponse] = []
        points_earned = 0

        # Verificar badges mensais (month_positive, etc)
        # Aqui seria necessário calcular se o mês foi positivo

        # Finalizar desafios do mês
        challenges = await self.challenge_service.finalize_month(user, month)
        challenges_updated.extend(challenges)

        for badge in badges_earned:
            points_earned += badge.points_reward

        points_balance = await self.points_service.get_or_create_balance(user)

        return GamificationEvent(
            badges_earned=badges_earned,
            streak_updated=None,
            challenges_updated=challenges_updated,
            points_earned=points_earned,
            new_total_points=points_balance.current_points,
        )

    # =========================================================================
    # CONSULTAS
    # =========================================================================

    async def get_summary(self, user: User) -> GamificationSummary:
        """Resumo para o dashboard"""

        # Pontos
        points = await self.points_service.get_or_create_balance(user)

        # Badges
        badges_earned = await self.badge_service.count_earned(user)
        badges_total = await self.badge_service.count_total()
        recent_badge = await self.badge_service.get_most_recent(user)
        unseen_badges = await self.badge_service.count_unseen(user)

        # Streak principal
        main_streak = await self.streak_service.get_streak(user, StreakType.DAILY_REGISTER)

        # Desafios
        active_challenges = await self.challenge_service.count_active(user)
        completed_this_month = await self.challenge_service.count_completed_month(user)

        return GamificationSummary(
            current_points=points.current_points if points else 0,
            lifetime_points=points.lifetime_points if points else 0,
            badges_earned=badges_earned,
            badges_total=badges_total,
            recent_badge=recent_badge,
            main_streak=main_streak,
            active_challenges=active_challenges,
            completed_challenges_month=completed_this_month,
            unseen_badges=unseen_badges,
        )

    async def get_streak_week_view(self, user: User) -> StreakWeekView:
        """Dados para o widget de streak da semana"""
        return await self.streak_service.get_week_view(user, StreakType.DAILY_REGISTER)

    async def get_all_badges(self, user: User, category: str | None = None) -> list[BadgeResponse]:
        """Lista todos os badges com status do usuário"""
        return await self.badge_service.list_all_with_status(user, category)

    async def get_challenges(self, user: User) -> ChallengeListResponse:
        """Lista desafios organizados por status"""
        return await self.challenge_service.list_by_status(user)

    async def mark_badges_seen(self, user: User) -> int:
        """Marca badges não vistos como vistos"""
        return await self.badge_service.mark_all_seen(user)

    async def start_challenge(self, user: User, challenge_id: int) -> ChallengeResponse | None:
        """Inicia um desafio para o usuário"""
        return await self.challenge_service.start(user, challenge_id)
