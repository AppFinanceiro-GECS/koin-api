"""
Serviço de Metas Financeiras (Goals)
Implementa funcionalidades baseadas em YNAB, Cerbasi (PNIF) e Ramsey (Emergency Fund)
"""

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.goal import Goal, GoalContribution, GoalStatus, GoalType
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
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
from app.modules.household.utils import (
    build_ownership_filter,
    get_household_member,
    get_household_user_ids,
    validate_create_permission,
    validate_delete_permission,
    validate_edit_permission,
)


class GoalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_goals(
        self, user: User, status_filter: GoalStatus | None = None
    ) -> list[GoalResponse]:
        """Lista metas do usuário (personal + household da família)"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        query = select(Goal).where(
            build_ownership_filter(
                Goal, Goal.user_id, Goal.ownership_type, user.id, household_user_ids, member
            )
        )

        if status_filter:
            query = query.where(Goal.status == status_filter.value)

        query = query.order_by(Goal.priority.desc(), Goal.created_at.desc())
        result = await self.db.execute(query)
        goals = result.scalars().all()

        return [await self._build_goal_response(goal) for goal in goals]

    async def get_goal(self, user: User, goal_id: int) -> GoalDetailResponse | None:
        """Retorna meta com detalhes e projeção"""
        result = await self.db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id)
        )
        goal = result.scalar_one_or_none()

        if not goal:
            return None

        response = await self._build_goal_response(goal)
        contributions = [
            GoalContributionResponse(
                id=c.id,
                goal_id=c.goal_id,
                amount=c.amount,
                contribution_date=c.contribution_date,
                notes=c.notes,
                transaction_id=c.transaction_id,
                created_at=c.created_at,
            )
            for c in goal.contributions
        ]

        projection = self._calculate_projection(goal)

        return GoalDetailResponse(
            **response.model_dump(), contributions=contributions, projection=projection
        )

    async def create_goal(self, user: User, data: GoalCreate) -> Goal:
        """Cria nova meta"""
        # Validar permissão para criar household
        await validate_create_permission(self.db, user, data.ownership_type.value)

        goal = Goal(
            user_id=user.id,
            name=data.name,
            description=data.description,
            type=data.type.value,
            icon=data.icon,
            color=data.color,
            target_amount=data.target_amount,
            current_amount=data.initial_amount,
            initial_amount=data.initial_amount,
            target_date=data.target_date,
            priority=data.priority,
            account_id=data.account_id,
            ownership_type=data.ownership_type.value,
        )

        # Calcular contribuição mensal sugerida
        if data.target_date and goal.auto_calculate_contribution:
            goal.monthly_contribution = self._calculate_monthly_contribution(
                goal.target_amount - goal.current_amount, date.today(), data.target_date
            )

        self.db.add(goal)
        await self.db.flush()
        await self.db.refresh(goal)
        return goal

    async def update_goal(self, user: User, goal_id: int, data: GoalUpdate) -> Goal:
        """Atualiza meta"""
        result = await self.db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id)
        )
        goal = result.scalar_one_or_none()

        if not goal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta não encontrada")

        # Validar permissão para editar
        await validate_edit_permission(self.db, user, goal.user_id, goal.ownership_type)

        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "status" and value:
                value = value.value
            if field == "type" and value:
                value = value.value
            setattr(goal, field, value)

        # Recalcular contribuição se necessário
        if goal.auto_calculate_contribution and goal.target_date:
            goal.monthly_contribution = self._calculate_monthly_contribution(
                goal.target_amount - goal.current_amount, date.today(), goal.target_date
            )

        # Marcar como concluída se atingiu o valor
        if goal.current_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE.value:
            goal.status = GoalStatus.COMPLETED.value
            goal.completed_date = date.today()

        await self.db.flush()
        await self.db.refresh(goal)
        return goal

    async def delete_goal(self, user: User, goal_id: int) -> None:
        """Remove meta"""
        result = await self.db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id)
        )
        goal = result.scalar_one_or_none()

        if not goal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta não encontrada")

        # Validar permissão para deletar
        await validate_delete_permission(self.db, user, goal.user_id, goal.ownership_type)

        await self.db.delete(goal)

    async def add_contribution(
        self, user: User, goal_id: int, data: GoalContributionCreate
    ) -> GoalContribution:
        """Adiciona contribuição à meta"""
        result = await self.db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id)
        )
        goal = result.scalar_one_or_none()

        if not goal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta não encontrada")

        if goal.status != GoalStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível adicionar contribuição a meta inativa",
            )

        contribution = GoalContribution(
            goal_id=goal.id,
            amount=data.amount,
            contribution_date=data.contribution_date,
            notes=data.notes,
            transaction_id=data.transaction_id,
        )
        self.db.add(contribution)

        # Atualizar valor atual da meta
        goal.current_amount += data.amount

        # Verificar se atingiu a meta
        if goal.current_amount >= goal.target_amount:
            goal.status = GoalStatus.COMPLETED.value
            goal.completed_date = date.today()

        await self.db.flush()
        await self.db.refresh(contribution)
        return contribution

    async def get_summary(self, user: User) -> GoalSummary:
        """Retorna resumo de todas as metas"""
        result = await self.db.execute(select(Goal).where(Goal.user_id == user.id))
        goals = result.scalars().all()

        active = [g for g in goals if g.status == GoalStatus.ACTIVE.value]
        completed = [g for g in goals if g.status == GoalStatus.COMPLETED.value]

        total_target = sum(g.target_amount for g in active)
        total_saved = sum(g.current_amount for g in active)
        total_remaining = total_target - total_saved

        overall_progress = 0.0
        if total_target > 0:
            overall_progress = float(total_saved / total_target * 100)

        # Encontrar próximo marco
        next_milestone = None
        for goal in active:
            milestone = self._get_next_milestone(goal)
            if milestone and (
                next_milestone is None
                or milestone.amount_to_milestone < next_milestone.amount_to_milestone
            ):
                next_milestone = milestone

        return GoalSummary(
            total_goals=len(goals),
            active_goals=len(active),
            completed_goals=len(completed),
            total_target=total_target,
            total_saved=total_saved,
            total_remaining=total_remaining,
            overall_progress=overall_progress,
            next_milestone=next_milestone,
        )

    async def calculate_emergency_fund(
        self, user: User, months: int = 6
    ) -> EmergencyFundCalculation:
        """
        Calcula fundo de emergência (Baby Step 3 - Dave Ramsey)
        Recomenda 3-6 meses de despesas
        """
        # Calcular média de despesas dos últimos 3 meses
        three_months_ago = date.today() - relativedelta(months=3)

        result = await self.db.execute(
            select(func.sum(Transaction.amount)).where(
                Transaction.user_id == user.id,
                Transaction.type == TransactionType.EXPENSE.value,
                Transaction.date >= three_months_ago,
            )
        )
        total_expenses = result.scalar() or Decimal(0)
        monthly_expenses = total_expenses / 3

        # Buscar valor atual guardado para emergência
        emergency_goals = await self.db.execute(
            select(Goal).where(
                Goal.user_id == user.id,
                Goal.type == GoalType.EMERGENCY_FUND.value,
                Goal.status == GoalStatus.ACTIVE.value,
            )
        )
        emergency_goal = emergency_goals.scalar_one_or_none()
        current_saved = emergency_goal.current_amount if emergency_goal else Decimal(0)

        recommended_3 = monthly_expenses * 3
        recommended_6 = monthly_expenses * 6
        months_covered = float(current_saved / monthly_expenses) if monthly_expenses > 0 else 0

        # Determinar status
        if months_covered >= 6:
            fund_status = "complete"
        elif months_covered >= 3:
            fund_status = "partial"
        elif months_covered >= 1:
            fund_status = "starter"
        else:
            fund_status = "none"

        return EmergencyFundCalculation(
            monthly_expenses=monthly_expenses,
            recommended_3_months=recommended_3,
            recommended_6_months=recommended_6,
            current_saved=current_saved,
            months_covered=months_covered,
            status=fund_status,
        )

    async def calculate_pnif(self, user: User, expected_return: float = 0.08) -> PNIFCalculation:
        """
        Calcula PNIF - Patrimônio Necessário para Independência Financeira
        Metodologia Gustavo Cerbasi: PNIF = Gasto Anual / Rentabilidade
        """
        # Calcular média de despesas dos últimos 12 meses
        twelve_months_ago = date.today() - relativedelta(months=12)

        result = await self.db.execute(
            select(func.sum(Transaction.amount)).where(
                Transaction.user_id == user.id,
                Transaction.type == TransactionType.EXPENSE.value,
                Transaction.date >= twelve_months_ago,
            )
        )
        annual_expenses = result.scalar() or Decimal(0)

        # Calcular patrimônio atual (soma dos saldos das contas)
        accounts_result = await self.db.execute(
            select(func.sum(Account.balance)).where(Account.user_id == user.id)
        )
        current_net_worth = accounts_result.scalar() or Decimal(0)

        # Calcular PNIF
        if expected_return > 0:
            pnif_amount = annual_expenses / Decimal(str(expected_return))
        else:
            pnif_amount = Decimal(0)

        percentage_achieved = 0.0
        if pnif_amount > 0:
            percentage_achieved = float(current_net_worth / pnif_amount * 100)

        # Calcular tempo para atingir PNIF
        # Assumindo poupança mensal baseada em receitas - despesas
        income_result = await self.db.execute(
            select(func.sum(Transaction.amount)).where(
                Transaction.user_id == user.id,
                Transaction.type == TransactionType.INCOME.value,
                Transaction.date >= twelve_months_ago,
            )
        )
        annual_income = income_result.scalar() or Decimal(0)
        annual_savings = annual_income - annual_expenses

        years_to_pnif = None
        monthly_savings_needed = None

        remaining = pnif_amount - current_net_worth
        if remaining > 0:
            if annual_savings > 0:
                # Fórmula simplificada sem considerar juros compostos
                years_to_pnif = int(remaining / annual_savings) + 1

            # Quanto precisa poupar por mês para atingir em 20 anos
            monthly_savings_needed = remaining / (20 * 12)

        return PNIFCalculation(
            annual_expenses=annual_expenses,
            expected_return_rate=expected_return,
            pnif_amount=pnif_amount,
            current_net_worth=current_net_worth,
            percentage_achieved=percentage_achieved,
            years_to_pnif=years_to_pnif,
            monthly_savings_needed=monthly_savings_needed,
        )

    async def _build_goal_response(self, goal: Goal) -> GoalResponse:
        """Constrói resposta com campos calculados"""
        remaining = max(Decimal(0), goal.target_amount - goal.current_amount)
        progress = goal.progress_percentage

        # Calcular meses para meta
        months_to_goal = None
        if goal.target_date:
            today = date.today()
            if goal.target_date > today:
                delta = relativedelta(goal.target_date, today)
                months_to_goal = delta.years * 12 + delta.months

        # Verificar se está no caminho certo
        on_track = True
        suggested_monthly = None
        if goal.target_date and goal.status == GoalStatus.ACTIVE.value:
            suggested_monthly = self._calculate_monthly_contribution(
                remaining, date.today(), goal.target_date
            )
            if goal.monthly_contribution and suggested_monthly:
                # Se a contribuição necessária é maior que 120% da planejada, está atrasado
                if suggested_monthly > goal.monthly_contribution * Decimal("1.2"):
                    on_track = False

        return GoalResponse(
            id=goal.id,
            user_id=goal.user_id,
            name=goal.name,
            description=goal.description,
            type=GoalType(goal.type),
            icon=goal.icon,
            color=goal.color,
            target_amount=goal.target_amount,
            initial_amount=goal.initial_amount,
            target_date=goal.target_date,
            priority=goal.priority,
            account_id=goal.account_id,
            current_amount=goal.current_amount,
            start_date=goal.start_date,
            completed_date=goal.completed_date,
            monthly_contribution=goal.monthly_contribution,
            auto_calculate_contribution=goal.auto_calculate_contribution,
            status=GoalStatus(goal.status),
            created_at=goal.created_at,
            updated_at=goal.updated_at,
            progress_percentage=progress,
            remaining_amount=remaining,
            months_to_goal=months_to_goal,
            on_track=on_track,
            suggested_monthly=suggested_monthly,
        )

    def _calculate_monthly_contribution(
        self, remaining: Decimal, start: date, end: date
    ) -> Decimal | None:
        """Calcula contribuição mensal necessária"""
        if end <= start:
            return None

        delta = relativedelta(end, start)
        months = delta.years * 12 + delta.months

        if months <= 0:
            return remaining

        return remaining / months

    def _calculate_projection(self, goal: Goal) -> GoalProjection | None:
        """Calcula projeção de quando a meta será atingida"""
        if goal.status != GoalStatus.ACTIVE.value:
            return None

        remaining = goal.target_amount - goal.current_amount
        if remaining <= 0:
            return GoalProjection(
                current_pace_date=date.today(),
                target_pace_date=date.today(),
                monthly_needed=Decimal(0),
                is_achievable=True,
            )

        # Calcular ritmo atual baseado em contribuições
        if goal.contributions:
            # Média mensal das últimas contribuições
            total_contributed = sum(c.amount for c in goal.contributions)
            first_contribution = min(c.contribution_date for c in goal.contributions)
            months_contributing = max(1, (date.today() - first_contribution).days / 30)
            avg_monthly = total_contributed / Decimal(str(months_contributing))

            if avg_monthly > 0:
                months_needed = int(remaining / avg_monthly) + 1
                current_pace_date = date.today() + relativedelta(months=months_needed)
            else:
                current_pace_date = None
        else:
            current_pace_date = None
            avg_monthly = Decimal(0)

        # Calcular necessário para atingir no prazo
        target_pace_date = goal.target_date
        monthly_needed = Decimal(0)
        is_achievable = True

        if goal.target_date:
            monthly_needed = self._calculate_monthly_contribution(
                remaining, date.today(), goal.target_date
            ) or Decimal(0)

            if current_pace_date and current_pace_date > goal.target_date:
                is_achievable = False

        return GoalProjection(
            current_pace_date=current_pace_date,
            target_pace_date=target_pace_date,
            monthly_needed=monthly_needed,
            is_achievable=is_achievable,
        )

    def _get_next_milestone(self, goal: Goal) -> GoalMilestone | None:
        """Retorna próximo marco da meta"""
        progress = goal.progress_percentage

        milestones = [(25, "25%"), (50, "50%"), (75, "75%"), (100, "complete")]

        for pct, label in milestones:
            if progress < pct:
                milestone_amount = goal.target_amount * Decimal(str(pct / 100))
                amount_to_milestone = milestone_amount - goal.current_amount

                return GoalMilestone(
                    goal_id=goal.id,
                    goal_name=goal.name,
                    amount_to_milestone=amount_to_milestone,
                    milestone_type=label,
                )

        return None
