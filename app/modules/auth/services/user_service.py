"""
Servico de usuario: operacoes CRUD e configuracao inicial.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.category import Category, CategoryType
from app.models.user import User
from app.modules.auth.schemas.user import UserUpdate


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def update(self, user: User, data: UserUpdate) -> User:
        if data.email and data.email != user.email:
            # Verificar se novo email já existe
            result = await self.db.execute(
                select(User).where(User.email == data.email, User.id != user.id)
            )
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email já em uso",
                )
            user.email = data.email

        if data.name:
            user.name = data.name

        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def setup_initial_data(self, user: User) -> None:
        """Configura dados iniciais para novo usuário (conta padrão, categorias)"""

        # Criar conta padrão "Carteira"
        default_account = Account(
            user_id=user.id,
            name="Carteira",
            type=AccountType.WALLET,
            balance=0,
            color="#4CAF50",
        )
        self.db.add(default_account)

        # Criar categorias padrão se não existirem
        system_categories = await self.db.execute(
            select(Category).where(Category.is_system == True)
        )
        if not system_categories.scalars().all():
            await self._create_default_categories()

        await self.db.flush()

    async def _create_default_categories(self) -> None:
        """Cria categorias padrão do sistema"""
        expense_categories = [
            ("Alimentação", "#FF5722", "restaurant"),
            ("Transporte", "#2196F3", "directions_car"),
            ("Moradia", "#795548", "home"),
            ("Saúde", "#E91E63", "local_hospital"),
            ("Educação", "#9C27B0", "school"),
            ("Lazer", "#FF9800", "sports_esports"),
            ("Compras", "#00BCD4", "shopping_bag"),
            ("Serviços", "#607D8B", "build"),
            ("Assinaturas", "#673AB7", "subscriptions"),
            ("Outros", "#9E9E9E", "more_horiz"),
        ]

        income_categories = [
            ("Salário", "#4CAF50", "payments"),
            ("Freelance", "#8BC34A", "work"),
            ("Investimentos", "#CDDC39", "trending_up"),
            ("Outros", "#9E9E9E", "more_horiz"),
        ]

        for name, color, icon in expense_categories:
            cat = Category(
                name=name,
                type=CategoryType.EXPENSE,
                color=color,
                icon=icon,
                is_system=True,
            )
            self.db.add(cat)

        for name, color, icon in income_categories:
            cat = Category(
                name=name,
                type=CategoryType.INCOME,
                color=color,
                icon=icon,
                is_system=True,
            )
            self.db.add(cat)
