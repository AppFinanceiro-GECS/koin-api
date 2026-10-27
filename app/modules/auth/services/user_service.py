"""
Servico de usuario: operacoes CRUD, configuracao inicial, exportacao e exclusao (LGPD).
"""

import hashlib
from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.category import Category, CategoryType
from app.models.user import User
from app.models.transaction import Transaction
from app.models.credit_card import CreditCard
from app.models.audit_log import AuditLog
from app.modules.auth.schemas.user import UserUpdate
from app.core.security import verify_password


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

    async def export_user_data(self, user: User) -> dict:
        """Coleta e estrutura todos os dados do usuário para exportação LGPD (Art. 18)."""
        # 1. Buscar Contas
        accounts_res = await self.db.execute(select(Account).where(Account.user_id == user.id))
        accounts = accounts_res.scalars().all()

        # 2. Buscar Transações
        transactions_res = await self.db.execute(select(Transaction).where(Transaction.user_id == user.id))
        transactions = transactions_res.scalars().all()

        # 3. Buscar Cartões de Crédito
        cards_res = await self.db.execute(select(CreditCard).where(CreditCard.user_id == user.id))
        cards = cards_res.scalars().all()

        return {
            "export_metadata": {
                "user_email": user.email,
                "exported_at": datetime.utcnow().isoformat(),
                "compliance": "LGPD Art. 18",
            },
            "profile": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            },
            "accounts": [{"id": a.id, "name": a.name, "balance": float(a.balance)} for a in accounts],
            "transactions": [
                {
                    "id": t.id,
                    "amount": float(t.amount),
                    "type": t.type,
                    "date": t.date.isoformat() if t.date else None,
                    "description": t.description,
                }
                for t in transactions
            ],
            "credit_cards": [{"id": c.id, "brand": c.card_brand, "limit": float(c.credit_limit)} for c in cards],
        }

    async def delete_account(self, user: User, password: str) -> dict:
        """Valida senha, aplica soft delete, registra auditoria LGPD e bloqueia acesso."""
        # 1. Reautenticação obrigatória
        if not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Senha atual incorreta. A reautenticação é obrigatória para exclusão da conta."
            )

        # 2. Marcar Soft Delete e desativar acesso imediato
        user.deleted_at = datetime.utcnow()
        user.is_active = False

        # 3. Registrar Auditoria LGPD (Utilizando hash seguro do e-mail para privacidade)
        email_hash = hashlib.sha256(user.email.encode()).hexdigest()
        audit_entry = AuditLog(
            user_hash=email_hash,
            action="account_soft_delete_requested"
        )
        self.db.add(audit_entry)

        # 4. Salvar alterações no banco
        await self.db.commit()

        return {
            "message": "Conta desativada com sucesso. Seus dados e arquivos serão permanentemente removidos em até 30 dias.",
            "scheduled_purge_date": (datetime.utcnow().date()).isoformat()
        }

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