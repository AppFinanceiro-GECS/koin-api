"""Streak Service for gamification"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gamification import StreakHistory, StreakType, UserStreak
from app.models.user import User

from ..schemas import StreakDayInfo, StreakResponse, StreakWeekView


class StreakService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # Milestones para badges de streak
    MILESTONES = [7, 14, 30, 60, 100, 365]

    async def record_action(self, user: User, streak_type: StreakType) -> UserStreak:
        """Registra uma ação e atualiza o streak"""
        today = date.today()

        # Buscar streak existente
        result = await self.db.execute(
            select(UserStreak).where(
                UserStreak.user_id == user.id, UserStreak.streak_type == streak_type.value
            )
        )
        streak = result.scalar_one_or_none()

        if not streak:
            # Criar novo streak
            streak = UserStreak(
                user_id=user.id,
                streak_type=streak_type.value,
                current_count=1,
                longest_count=1,
                last_action_date=today,
            )
            self.db.add(streak)
            await self.db.flush()
            await self.db.refresh(streak)
            return streak

        # Já registrou hoje
        if streak.last_action_date == today:
            return streak

        # Calcular diferença de dias
        if streak.last_action_date:
            days_diff = (today - streak.last_action_date).days
        else:
            days_diff = 999  # Primeira vez

        if days_diff == 1:
            # Dia consecutivo - incrementar streak
            streak.current_count += 1
        elif days_diff == 2 and streak.freeze_available > 0:
            # Pode usar freeze (pulou 1 dia)
            streak.freeze_available -= 1
            streak.freeze_used_at = today - timedelta(days=1)
            streak.current_count += 1
        else:
            # Streak quebrado - salvar histórico e resetar
            if streak.current_count > 0 and streak.last_action_date:
                history = StreakHistory(
                    user_id=user.id,
                    streak_type=streak_type.value,
                    started_at=streak.last_action_date - timedelta(days=streak.current_count - 1),
                    ended_at=streak.last_action_date,
                    final_count=streak.current_count,
                    ended_reason="broken",
                )
                self.db.add(history)
            streak.current_count = 1

        # Atualizar recorde se necessário
        if streak.current_count > streak.longest_count:
            streak.longest_count = streak.current_count

        streak.last_action_date = today
        await self.db.flush()
        await self.db.refresh(streak)
        return streak

    async def get_streak(self, user: User, streak_type: StreakType) -> StreakResponse | None:
        """Retorna dados do streak com informações adicionais"""
        result = await self.db.execute(
            select(UserStreak).where(
                UserStreak.user_id == user.id, UserStreak.streak_type == streak_type.value
            )
        )
        streak = result.scalar_one_or_none()

        if not streak:
            return None

        today = date.today()
        is_active_today = streak.last_action_date == today

        # Verificar se streak está quebrado (mais de 1 dia sem ação)
        if streak.last_action_date:
            days_since_last = (today - streak.last_action_date).days
            if days_since_last > 1 and streak.freeze_available == 0:
                # Streak foi quebrado, resetar para 0
                current_count = 0
            elif days_since_last > 2:
                # Mesmo com freeze, mais de 2 dias quebra
                current_count = 0
            else:
                current_count = streak.current_count
        else:
            current_count = streak.current_count

        # Calcular próximo milestone
        next_milestone = None
        days_until = None
        for m in self.MILESTONES:
            if current_count < m:
                next_milestone = m
                days_until = m - current_count
                break

        return StreakResponse(
            streak_type=StreakType(streak.streak_type),
            current_count=current_count,
            longest_count=streak.longest_count,
            last_action_date=streak.last_action_date,
            freeze_available=streak.freeze_available,
            is_active_today=is_active_today,
            next_milestone=next_milestone,
            days_until_next_milestone=days_until,
        )

    async def get_week_view(self, user: User, streak_type: StreakType) -> StreakWeekView:
        """Retorna visualização da semana para o widget"""
        today = date.today()

        # Pegar streak atual
        streak_data = await self.get_streak(user, streak_type)
        current_count = streak_data.current_count if streak_data else 0
        last_action = streak_data.last_action_date if streak_data else None

        # Calcular início da semana (segunda-feira)
        start_of_week = today - timedelta(days=today.weekday())

        # Nomes dos dias em português
        day_names = ["S", "T", "Q", "Q", "S", "S", "D"]

        days = []
        for i in range(7):
            day = start_of_week + timedelta(days=i)

            # Determinar se o dia foi completado
            completed = False
            if last_action and current_count > 0:
                # Calcular quantos dias atrás o streak começou
                streak_start = last_action - timedelta(days=current_count - 1)
                completed = streak_start <= day <= last_action

            days.append(
                StreakDayInfo(
                    date=day.isoformat(),
                    day_name=day_names[day.weekday()],
                    completed=completed,
                    is_today=day == today,
                    is_future=day > today,
                )
            )

        return StreakWeekView(
            days=days,
            current_streak=current_count,
            streak_type=streak_type,
            next_milestone=streak_data.next_milestone if streak_data else 7,
            days_until_next_milestone=streak_data.days_until_next_milestone if streak_data else 7,
        )

    async def check_milestone_reached(self, streak: UserStreak) -> int | None:
        """Verifica se um milestone foi atingido, retorna o milestone ou None"""
        for m in self.MILESTONES:
            if streak.current_count == m:
                return m
        return None
