"""Badge Service for gamification"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utc_now
from app.models.debt import Debt, DebtStatus
from app.models.gamification import (
    BadgeDefinition,
    UserBadge,
    UserStreak,
)
from app.models.goal import Goal, GoalStatus
from app.models.transaction import Transaction
from app.models.user import User

from ..schemas import BadgeCategory as BadgeCategorySchema
from ..schemas import BadgeResponse
from .points_service import PointsService


class BadgeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all_with_status(
        self, user: User, category: str | None = None
    ) -> list[BadgeResponse]:
        """Lista todos os badges com status do usuário"""

        # Query base para badge definitions
        query = select(BadgeDefinition).where(BadgeDefinition.is_active == True)

        if category:
            query = query.where(BadgeDefinition.category == category)

        query = query.order_by(BadgeDefinition.display_order)
        result = await self.db.execute(query)
        definitions = list(result.scalars().all())

        # Buscar badges do usuário
        user_badges_result = await self.db.execute(
            select(UserBadge).where(UserBadge.user_id == user.id)
        )
        user_badges = {ub.badge_id: ub for ub in user_badges_result.scalars().all()}

        # Montar resposta
        badges = []
        for definition in definitions:
            user_badge = user_badges.get(definition.id)
            is_earned = user_badge is not None

            # Calcular progresso se não conquistado
            progress = None
            if not is_earned and not definition.is_secret:
                progress = await self._calculate_progress(user, definition)

            # Se é secreto e não conquistado, pular
            if definition.is_secret and not is_earned:
                continue

            badges.append(
                BadgeResponse(
                    id=definition.id,
                    name=definition.name,
                    description=definition.description,
                    icon=definition.icon,
                    category=BadgeCategorySchema(definition.category),
                    rarity=definition.rarity,
                    points_reward=definition.points_reward,
                    is_earned=is_earned,
                    earned_at=user_badge.earned_at if user_badge else None,
                    seen_at=user_badge.seen_at if user_badge else None,
                    progress=progress,
                )
            )

        return badges

    async def _calculate_progress(self, user: User, definition: BadgeDefinition) -> float:
        """Calcula o progresso para um badge não conquistado"""
        criteria_type = definition.criteria_type
        criteria_value = definition.criteria_value

        current_value = 0

        if criteria_type == "transaction_count":
            result = await self.db.execute(
                select(func.count(Transaction.id)).where(Transaction.user_id == user.id)
            )
            current_value = result.scalar() or 0

        elif criteria_type == "streak_days":
            result = await self.db.execute(
                select(UserStreak.current_count).where(
                    UserStreak.user_id == user.id, UserStreak.streak_type == "daily_register"
                )
            )
            current_value = result.scalar() or 0

        elif criteria_type == "goal_created":
            result = await self.db.execute(
                select(func.count(Goal.id)).where(Goal.user_id == user.id)
            )
            current_value = result.scalar() or 0

        elif criteria_type == "goal_completed":
            result = await self.db.execute(
                select(func.count(Goal.id)).where(
                    Goal.user_id == user.id, Goal.status == GoalStatus.COMPLETED.value
                )
            )
            current_value = result.scalar() or 0

        elif criteria_type == "debt_paid":
            result = await self.db.execute(
                select(func.count(Debt.id)).where(
                    Debt.user_id == user.id, Debt.status == DebtStatus.PAID.value
                )
            )
            current_value = result.scalar() or 0

        # Calcular porcentagem (0.0 a 1.0)
        if criteria_value > 0:
            return min(current_value / criteria_value, 1.0)
        return 0.0

    async def check_and_award_badge(self, user: User, badge_id: str) -> BadgeResponse | None:
        """Verifica e concede um badge específico se os critérios forem atendidos"""

        # Verificar se já tem o badge
        existing = await self.db.execute(
            select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.badge_id == badge_id)
        )
        if existing.scalar_one_or_none():
            return None

        # Buscar definição
        def_result = await self.db.execute(
            select(BadgeDefinition).where(BadgeDefinition.id == badge_id)
        )
        definition = def_result.scalar_one_or_none()
        if not definition:
            return None

        # Verificar critérios
        progress = await self._calculate_progress(user, definition)
        if progress < 1.0:
            return None

        # Conceder badge
        user_badge = UserBadge(user_id=user.id, badge_id=badge_id, earned_at=utc_now())
        self.db.add(user_badge)

        # Adicionar pontos
        points_service = PointsService(self.db)
        await points_service.add_points(
            user=user,
            amount=definition.points_reward,
            reason=f"badge_earned:{badge_id}",
            reference_type="badge",
            reference_id=badge_id,
        )

        await self.db.flush()

        return BadgeResponse(
            id=definition.id,
            name=definition.name,
            description=definition.description,
            icon=definition.icon,
            category=BadgeCategorySchema(definition.category),
            rarity=definition.rarity,
            points_reward=definition.points_reward,
            is_earned=True,
            earned_at=user_badge.earned_at,
        )

    async def check_transaction_badges(self, user: User) -> list[BadgeResponse]:
        """Verifica badges relacionados a transações"""
        badges_earned = []

        # IDs dos badges de transação
        transaction_badges = [
            "first_transaction",
            "transactions_10",
            "transactions_50",
            "transactions_100",
            "transactions_500",
            "transactions_1000",
        ]

        for badge_id in transaction_badges:
            badge = await self.check_and_award_badge(user, badge_id)
            if badge:
                badges_earned.append(badge)

        return badges_earned

    async def check_streak_badges(self, user: User, streak: UserStreak) -> list[BadgeResponse]:
        """Verifica badges de streak"""
        badges_earned = []

        # Mapear milestones para badge IDs
        milestone_badges = {
            7: "streak_7",
            14: "streak_14",
            30: "streak_30",
            60: "streak_60",
            100: "streak_100",
            365: "streak_365",
        }

        # Verificar se atingiu algum milestone
        for milestone, badge_id in milestone_badges.items():
            if streak.current_count >= milestone:
                badge = await self.check_and_award_badge(user, badge_id)
                if badge:
                    badges_earned.append(badge)

        return badges_earned

    async def check_goal_badges(self, user: User) -> list[BadgeResponse]:
        """Verifica badges de metas"""
        badges_earned = []

        goal_badges = ["first_goal", "goal_completed", "goals_3"]
        for badge_id in goal_badges:
            badge = await self.check_and_award_badge(user, badge_id)
            if badge:
                badges_earned.append(badge)

        return badges_earned

    async def check_debt_badges(self, user: User) -> list[BadgeResponse]:
        """Verifica badges de dívidas"""
        badges_earned = []

        debt_badges = ["first_debt_paid", "debts_3_paid"]
        for badge_id in debt_badges:
            badge = await self.check_and_award_badge(user, badge_id)
            if badge:
                badges_earned.append(badge)

        # Verificar se quitou todas as dívidas
        result = await self.db.execute(
            select(func.count(Debt.id)).where(
                Debt.user_id == user.id, Debt.status != DebtStatus.PAID.value
            )
        )
        unpaid_count = result.scalar() or 0

        if unpaid_count == 0:
            # Verificar se tem pelo menos uma dívida paga
            paid_result = await self.db.execute(
                select(func.count(Debt.id)).where(
                    Debt.user_id == user.id, Debt.status == DebtStatus.PAID.value
                )
            )
            paid_count = paid_result.scalar() or 0
            if paid_count > 0:
                badge = await self.check_and_award_badge(user, "all_debts_paid")
                if badge:
                    badges_earned.append(badge)

        return badges_earned

    async def count_earned(self, user: User) -> int:
        """Conta badges conquistados"""
        result = await self.db.execute(
            select(func.count(UserBadge.id)).where(UserBadge.user_id == user.id)
        )
        return result.scalar() or 0

    async def count_total(self) -> int:
        """Conta total de badges disponíveis"""
        result = await self.db.execute(
            select(func.count(BadgeDefinition.id)).where(
                BadgeDefinition.is_active == True, BadgeDefinition.is_secret == False
            )
        )
        return result.scalar() or 0

    async def get_most_recent(self, user: User) -> BadgeResponse | None:
        """Obtém o badge mais recente"""
        result = await self.db.execute(
            select(UserBadge)
            .where(UserBadge.user_id == user.id)
            .order_by(UserBadge.earned_at.desc())
            .limit(1)
        )
        user_badge = result.scalar_one_or_none()

        if not user_badge:
            return None

        # Buscar definição
        def_result = await self.db.execute(
            select(BadgeDefinition).where(BadgeDefinition.id == user_badge.badge_id)
        )
        definition = def_result.scalar_one_or_none()

        if not definition:
            return None

        return BadgeResponse(
            id=definition.id,
            name=definition.name,
            description=definition.description,
            icon=definition.icon,
            category=BadgeCategorySchema(definition.category),
            rarity=definition.rarity,
            points_reward=definition.points_reward,
            is_earned=True,
            earned_at=user_badge.earned_at,
            seen_at=user_badge.seen_at,
        )

    async def count_unseen(self, user: User) -> int:
        """Conta badges não vistos"""
        result = await self.db.execute(
            select(func.count(UserBadge.id)).where(
                UserBadge.user_id == user.id, UserBadge.seen_at == None
            )
        )
        return result.scalar() or 0

    async def mark_all_seen(self, user: User) -> int:
        """Marca todos os badges como vistos"""

        result = await self.db.execute(
            select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.seen_at == None)
        )
        unseen_badges = list(result.scalars().all())

        count = 0
        for badge in unseen_badges:
            badge.seen_at = utc_now()
            count += 1

        await self.db.flush()
        return count
