"""Points Service for gamification"""

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gamification import PointsTransaction, UserPoints
from app.models.user import User


class PointsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_balance(self, user: User) -> UserPoints:
        """Obtém ou cria o saldo de pontos do usuário"""
        result = await self.db.execute(select(UserPoints).where(UserPoints.user_id == user.id))
        points = result.scalar_one_or_none()

        if not points:
            points = UserPoints(user_id=user.id, current_points=0, lifetime_points=0)
            self.db.add(points)
            await self.db.flush()
            await self.db.refresh(points)

        return points

    async def get_balance(self, user: User) -> UserPoints | None:
        """Obtém o saldo de pontos do usuário"""
        result = await self.db.execute(select(UserPoints).where(UserPoints.user_id == user.id))
        return result.scalar_one_or_none()

    async def add_points(
        self,
        user: User,
        amount: int,
        reason: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> tuple[UserPoints, PointsTransaction]:
        """Adiciona pontos ao usuário"""
        points = await self.get_or_create_balance(user)

        # Atualizar saldo
        points.current_points += amount
        points.lifetime_points += amount

        # Registrar transação
        transaction = PointsTransaction(
            user_id=user.id,
            amount=amount,
            balance_after=points.current_points,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        self.db.add(transaction)
        await self.db.flush()
        await self.db.refresh(transaction)

        return points, transaction

    async def spend_points(
        self,
        user: User,
        amount: int,
        reason: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> tuple[UserPoints, PointsTransaction] | None:
        """Gasta pontos do usuário (retorna None se saldo insuficiente)"""
        points = await self.get_or_create_balance(user)

        if points.current_points < amount:
            return None

        # Atualizar saldo
        points.current_points -= amount

        # Registrar transação (negativa)
        transaction = PointsTransaction(
            user_id=user.id,
            amount=-amount,
            balance_after=points.current_points,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        self.db.add(transaction)
        await self.db.flush()
        await self.db.refresh(transaction)

        return points, transaction

    async def get_history(
        self, user: User, limit: int = 20, offset: int = 0
    ) -> list[PointsTransaction]:
        """Obtém histórico de transações de pontos"""
        result = await self.db.execute(
            select(PointsTransaction)
            .where(PointsTransaction.user_id == user.id)
            .order_by(desc(PointsTransaction.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
