"""
Household Migration Router

Endpoints para migração de recursos de personal → household.
Apenas o owner da família pode executar essas operações.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import and_, func, select, update

from app.core.deps import CurrentUser, DbSession
from app.models.account import Account
from app.models.budget import Budget
from app.models.debt import Debt
from app.models.goal import Goal
from app.models.income_source import IncomeSource
from app.models.recurring import RecurringTransaction
from app.models.transaction import Transaction
from app.modules.household.utils.household_helpers import get_household_member

router = APIRouter()


class MigrationPreview(BaseModel):
    """Preview de recursos que serão migrados"""

    accounts: int
    budgets: int
    goals: int
    debts: int
    recurring_transactions: int
    transactions: int
    income_sources: int
    total: int


class MigrationRequest(BaseModel):
    """Request para migração"""

    migrate_all: bool = True  # Se False, permite escolher quais tipos
    include_accounts: bool = True
    include_budgets: bool = True
    include_goals: bool = True
    include_debts: bool = True
    include_recurring: bool = True
    include_transactions: bool = True
    include_income_sources: bool = True


class MigrationResponse(BaseModel):
    """Response da migração"""

    success: bool
    migrated: MigrationPreview
    message: str


@router.get("/preview", response_model=MigrationPreview)
async def preview_migration(
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Preview de quantos recursos seriam migrados de personal → household.
    Apenas o owner da família pode ver isso.
    """
    # Verificar se é owner
    member = await get_household_member(db, current_user)
    if not member or member.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o owner da família pode realizar migração em lote",
        )

    counts = {}

    # Contar cada tipo de recurso
    result = await db.execute(
        select(func.count(Account.id)).where(
            and_(Account.user_id == current_user.id, Account.ownership_type == "personal")
        )
    )
    counts["accounts"] = result.scalar() or 0

    result = await db.execute(
        select(func.count(Budget.id)).where(
            and_(Budget.user_id == current_user.id, Budget.ownership_type == "personal")
        )
    )
    counts["budgets"] = result.scalar() or 0

    result = await db.execute(
        select(func.count(Goal.id)).where(
            and_(Goal.user_id == current_user.id, Goal.ownership_type == "personal")
        )
    )
    counts["goals"] = result.scalar() or 0

    result = await db.execute(
        select(func.count(Debt.id)).where(
            and_(Debt.user_id == current_user.id, Debt.ownership_type == "personal")
        )
    )
    counts["debts"] = result.scalar() or 0

    result = await db.execute(
        select(func.count(RecurringTransaction.id)).where(
            and_(
                RecurringTransaction.user_id == current_user.id,
                RecurringTransaction.ownership_type == "personal",
            )
        )
    )
    counts["recurring_transactions"] = result.scalar() or 0

    result = await db.execute(
        select(func.count(Transaction.id)).where(
            and_(Transaction.user_id == current_user.id, Transaction.ownership_type == "personal")
        )
    )
    counts["transactions"] = result.scalar() or 0

    result = await db.execute(
        select(func.count(IncomeSource.id)).where(
            and_(IncomeSource.user_id == current_user.id, IncomeSource.ownership_type == "personal")
        )
    )
    counts["income_sources"] = result.scalar() or 0

    total = sum(counts.values())

    return MigrationPreview(**counts, total=total)


@router.post("/migrate", response_model=MigrationResponse)
async def migrate_to_household(
    migration: MigrationRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Migra recursos de personal → household.
    Apenas o owner da família pode executar essa operação.

    ATENÇÃO: Esta operação é irreversível. Todos os recursos migrados
    ficarão visíveis para todos os membros da família.
    """
    # Verificar se é owner
    member = await get_household_member(db, current_user)
    if not member or member.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o owner da família pode realizar migração em lote",
        )

    migrated_counts = {
        "accounts": 0,
        "budgets": 0,
        "goals": 0,
        "debts": 0,
        "recurring_transactions": 0,
        "transactions": 0,
        "income_sources": 0,
    }

    # Migrar cada tipo de recurso se solicitado
    if migration.migrate_all or migration.include_accounts:
        result = await db.execute(
            update(Account)
            .where(and_(Account.user_id == current_user.id, Account.ownership_type == "personal"))
            .values(ownership_type="household")
        )
        migrated_counts["accounts"] = result.rowcount or 0

    if migration.migrate_all or migration.include_budgets:
        result = await db.execute(
            update(Budget)
            .where(and_(Budget.user_id == current_user.id, Budget.ownership_type == "personal"))
            .values(ownership_type="household")
        )
        migrated_counts["budgets"] = result.rowcount or 0

    if migration.migrate_all or migration.include_goals:
        result = await db.execute(
            update(Goal)
            .where(and_(Goal.user_id == current_user.id, Goal.ownership_type == "personal"))
            .values(ownership_type="household")
        )
        migrated_counts["goals"] = result.rowcount or 0

    if migration.migrate_all or migration.include_debts:
        result = await db.execute(
            update(Debt)
            .where(and_(Debt.user_id == current_user.id, Debt.ownership_type == "personal"))
            .values(ownership_type="household")
        )
        migrated_counts["debts"] = result.rowcount or 0

    if migration.migrate_all or migration.include_recurring:
        result = await db.execute(
            update(RecurringTransaction)
            .where(
                and_(
                    RecurringTransaction.user_id == current_user.id,
                    RecurringTransaction.ownership_type == "personal",
                )
            )
            .values(ownership_type="household")
        )
        migrated_counts["recurring_transactions"] = result.rowcount or 0

    if migration.migrate_all or migration.include_transactions:
        result = await db.execute(
            update(Transaction)
            .where(
                and_(
                    Transaction.user_id == current_user.id, Transaction.ownership_type == "personal"
                )
            )
            .values(ownership_type="household")
        )
        migrated_counts["transactions"] = result.rowcount or 0

    if migration.migrate_all or migration.include_income_sources:
        result = await db.execute(
            update(IncomeSource)
            .where(
                and_(
                    IncomeSource.user_id == current_user.id,
                    IncomeSource.ownership_type == "personal",
                )
            )
            .values(ownership_type="household")
        )
        migrated_counts["income_sources"] = result.rowcount or 0

    await db.commit()

    total_migrated = sum(migrated_counts.values())

    return MigrationResponse(
        success=True,
        migrated=MigrationPreview(**migrated_counts, total=total_migrated),
        message=f"{total_migrated} recursos foram convertidos para household com sucesso!",
    )
