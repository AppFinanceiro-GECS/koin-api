"""Challenge Service for gamification"""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utc_now
from app.models.gamification import (
    ChallengeDefinition,
    ChallengeStatus,
    UserChallenge,
)
from app.models.transaction import Transaction
from app.models.user import User

from ..schemas import ChallengeDifficulty as ChallengeDifficultySchema
from ..schemas import ChallengeListResponse, ChallengeResponse
from ..schemas import ChallengeStatus as ChallengeStatusSchema
from .points_service import PointsService


class ChallengeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_status(self, user: User) -> ChallengeListResponse:
        """Lista desafios organizados por status"""

        # Buscar todos os desafios ativos do sistema
        definitions_result = await self.db.execute(
            select(ChallengeDefinition).where(ChallengeDefinition.is_active == True)
        )
        all_definitions = {d.id: d for d in definitions_result.scalars().all()}

        # Buscar desafios do usuário
        user_challenges_result = await self.db.execute(
            select(UserChallenge).where(UserChallenge.user_id == user.id)
        )
        user_challenges = list(user_challenges_result.scalars().all())

        active = []
        completed = []
        failed = []
        available = []

        # Processar desafios do usuário
        participated_ids = set()
        for uc in user_challenges:
            definition = all_definitions.get(uc.challenge_id)
            if not definition:
                continue

            participated_ids.add(uc.challenge_id)

            # Verificar se expirou
            now = utc_now()
            if uc.status == ChallengeStatus.ACTIVE.value and uc.expires_at < now:
                uc.status = ChallengeStatus.FAILED.value
                await self.db.flush()

            response = self._build_challenge_response(definition, uc)

            if uc.status == ChallengeStatus.ACTIVE.value:
                active.append(response)
            elif uc.status == ChallengeStatus.COMPLETED.value:
                completed.append(response)
            else:
                failed.append(response)

        # Desafios disponíveis (não iniciados)
        today = date.today()
        for def_id, definition in all_definitions.items():
            if def_id in participated_ids:
                # Verificar se é recorrente e o mês anterior
                if definition.is_recurring:
                    # Pode participar novamente se o último foi em outro mês
                    last_challenge = next(
                        (uc for uc in user_challenges if uc.challenge_id == def_id), None
                    )
                    if last_challenge:
                        last_month = last_challenge.started_at.month
                        if last_month == today.month:
                            continue  # Já participou este mês
                else:
                    continue

            # Verificar disponibilidade
            if definition.available_from and definition.available_from > today:
                continue
            if definition.available_until and definition.available_until < today:
                continue

            available.append(
                ChallengeResponse(
                    id=definition.id,
                    name=definition.name,
                    description=definition.description,
                    icon=definition.icon,
                    difficulty=ChallengeDifficultySchema(definition.difficulty),
                    status=None,
                    progress=None,
                    progress_percentage=0.0,
                    points_reward=definition.points_reward,
                    badge_reward_id=definition.badge_reward_id,
                    duration_days=definition.duration_days,
                    is_available=True,
                )
            )

        return ChallengeListResponse(
            active=active, completed=completed, failed=failed, available=available
        )

    def _build_challenge_response(
        self, definition: ChallengeDefinition, user_challenge: UserChallenge
    ) -> ChallengeResponse:
        """Constrói resposta de desafio"""

        # Calcular porcentagem de progresso
        progress = user_challenge.progress or {}
        progress_percentage = 0.0

        if definition.challenge_type == "register_streak":
            days_completed = progress.get("days_completed", 0)
            days_required = definition.criteria.get("days", 30)
            progress_percentage = min(days_completed / days_required, 1.0)

        elif definition.challenge_type == "save_percentage":
            amount_saved = progress.get("amount_saved", 0)
            target = progress.get("target", 1)
            progress_percentage = min(amount_saved / target, 1.0) if target > 0 else 0

        elif definition.challenge_type == "budget_compliance":
            days_compliant = progress.get("days_compliant", 0)
            days_required = definition.criteria.get("days", 7)
            progress_percentage = min(days_compliant / days_required, 1.0)

        elif definition.challenge_type == "no_spending_category":
            days_completed = progress.get("days_completed", 0)
            days_required = definition.criteria.get("days", 7)
            progress_percentage = min(days_completed / days_required, 1.0)

        elif definition.challenge_type == "reduce_spending":
            reduction_achieved = progress.get("reduction_percentage", 0)
            target = definition.criteria.get("percentage", 15)
            progress_percentage = min(reduction_achieved / target, 1.0)

        return ChallengeResponse(
            id=definition.id,
            name=definition.name,
            description=definition.description,
            icon=definition.icon,
            difficulty=ChallengeDifficultySchema(definition.difficulty),
            status=ChallengeStatusSchema(user_challenge.status),
            progress=progress,
            progress_percentage=progress_percentage,
            points_reward=definition.points_reward,
            badge_reward_id=definition.badge_reward_id,
            started_at=user_challenge.started_at,
            expires_at=user_challenge.expires_at,
            completed_at=user_challenge.completed_at,
            duration_days=definition.duration_days,
            is_available=False,
        )

    async def start(self, user: User, challenge_id: int) -> ChallengeResponse | None:
        """Inicia um desafio para o usuário"""

        # Verificar se desafio existe
        def_result = await self.db.execute(
            select(ChallengeDefinition).where(ChallengeDefinition.id == challenge_id)
        )
        definition = def_result.scalar_one_or_none()

        if not definition or not definition.is_active:
            return None

        # Verificar se já tem o desafio ativo
        existing = await self.db.execute(
            select(UserChallenge).where(
                UserChallenge.user_id == user.id,
                UserChallenge.challenge_id == challenge_id,
                UserChallenge.status == ChallengeStatus.ACTIVE.value,
            )
        )
        if existing.scalar_one_or_none():
            return None

        # Criar desafio do usuário
        now = utc_now()
        expires_at = now + timedelta(days=definition.duration_days)

        # Progresso inicial baseado no tipo
        initial_progress = self._get_initial_progress(definition)

        user_challenge = UserChallenge(
            user_id=user.id,
            challenge_id=challenge_id,
            status=ChallengeStatus.ACTIVE.value,
            progress=initial_progress,
            started_at=now,
            expires_at=expires_at,
        )
        self.db.add(user_challenge)
        await self.db.flush()
        await self.db.refresh(user_challenge)

        return self._build_challenge_response(definition, user_challenge)

    def _get_initial_progress(self, definition: ChallengeDefinition) -> dict:
        """Retorna o progresso inicial baseado no tipo de desafio"""
        criteria = definition.criteria or {}

        if definition.challenge_type == "register_streak":
            return {"days_completed": 0, "last_register_date": None}

        elif definition.challenge_type == "save_percentage":
            return {"amount_saved": 0, "target": 0, "income_recorded": False}

        elif definition.challenge_type == "budget_compliance":
            return {"days_compliant": 0, "last_check_date": None}

        elif definition.challenge_type == "no_spending_category":
            return {
                "days_completed": 0,
                "category_name": criteria.get("category_name", ""),
                "start_date": date.today().isoformat(),
            }

        elif definition.challenge_type == "reduce_spending":
            return {
                "reduction_percentage": 0,
                "previous_month_spending": 0,
                "current_month_spending": 0,
            }

        return {}

    async def on_transaction(self, user: User, transaction: Transaction) -> list[ChallengeResponse]:
        """Atualiza desafios baseado em nova transação"""
        updated = []

        # Buscar desafios ativos
        result = await self.db.execute(
            select(UserChallenge).where(
                UserChallenge.user_id == user.id,
                UserChallenge.status == ChallengeStatus.ACTIVE.value,
            )
        )
        active_challenges = list(result.scalars().all())

        for uc in active_challenges:
            # Buscar definição
            def_result = await self.db.execute(
                select(ChallengeDefinition).where(ChallengeDefinition.id == uc.challenge_id)
            )
            definition = def_result.scalar_one_or_none()
            if not definition:
                continue

            # Atualizar baseado no tipo
            was_updated = False

            if definition.challenge_type == "register_streak":
                was_updated = await self._update_register_streak(uc, definition)

            elif definition.challenge_type == "no_spending_category":
                was_updated = await self._update_no_spending(uc, definition, transaction)

            if was_updated:
                # Verificar se completou
                if self._is_completed(uc, definition):
                    await self._complete_challenge(user, uc, definition)

                await self.db.flush()
                updated.append(self._build_challenge_response(definition, uc))

        return updated

    async def _update_register_streak(
        self, uc: UserChallenge, definition: ChallengeDefinition
    ) -> bool:
        """Atualiza desafio de registro diário"""
        today = date.today().isoformat()
        progress = uc.progress or {}

        if progress.get("last_register_date") != today:
            progress["last_register_date"] = today
            progress["days_completed"] = progress.get("days_completed", 0) + 1
            uc.progress = progress
            return True

        return False

    async def _update_no_spending(
        self, uc: UserChallenge, definition: ChallengeDefinition, transaction: Transaction
    ) -> bool:
        """Atualiza desafio de não gastar em categoria"""
        if transaction.type != "expense":
            return False

        # Verificar se a transação é da categoria proibida
        # (simplificado - em produção verificaria por category_id)

        # Se gastou na categoria proibida, falha o desafio
        # Aqui seria necessário verificar a categoria real da transação
        # Por simplicidade, vamos apenas atualizar os dias

        return False

    def _is_completed(self, uc: UserChallenge, definition: ChallengeDefinition) -> bool:
        """Verifica se o desafio foi completado"""
        progress = uc.progress or {}
        criteria = definition.criteria or {}

        if definition.challenge_type == "register_streak":
            return progress.get("days_completed", 0) >= criteria.get("days", 30)

        elif definition.challenge_type == "save_percentage":
            target = progress.get("target", 0)
            saved = progress.get("amount_saved", 0)
            return target > 0 and saved >= target

        elif definition.challenge_type == "budget_compliance":
            return progress.get("days_compliant", 0) >= criteria.get("days", 7)

        elif definition.challenge_type == "no_spending_category":
            return progress.get("days_completed", 0) >= criteria.get("days", 7)

        elif definition.challenge_type == "reduce_spending":
            return progress.get("reduction_percentage", 0) >= criteria.get("percentage", 15)

        return False

    async def _complete_challenge(
        self, user: User, uc: UserChallenge, definition: ChallengeDefinition
    ):
        """Marca desafio como completado e concede recompensas"""
        uc.status = ChallengeStatus.COMPLETED.value
        uc.completed_at = utc_now()

        # Adicionar pontos
        points_service = PointsService(self.db)
        await points_service.add_points(
            user=user,
            amount=definition.points_reward,
            reason=f"challenge_completed:{definition.id}",
            reference_type="challenge",
            reference_id=str(definition.id),
        )

        # Conceder badge se houver
        if definition.badge_reward_id:
            from .badge_service import BadgeService

            badge_service = BadgeService(self.db)
            await badge_service.check_and_award_badge(user, definition.badge_reward_id)

    async def count_active(self, user: User) -> int:
        """Conta desafios ativos"""
        result = await self.db.execute(
            select(func.count(UserChallenge.id)).where(
                UserChallenge.user_id == user.id,
                UserChallenge.status == ChallengeStatus.ACTIVE.value,
            )
        )
        return result.scalar() or 0

    async def count_completed_month(self, user: User) -> int:
        """Conta desafios completados este mês"""
        today = date.today()
        first_of_month = today.replace(day=1)

        result = await self.db.execute(
            select(func.count(UserChallenge.id)).where(
                UserChallenge.user_id == user.id,
                UserChallenge.status == ChallengeStatus.COMPLETED.value,
                UserChallenge.completed_at >= first_of_month,
            )
        )
        return result.scalar() or 0

    async def finalize_month(self, user: User, month: date) -> list[ChallengeResponse]:
        """Finaliza desafios do mês"""
        # Implementação para ser chamada por um job mensal
        return []
