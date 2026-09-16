from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select

from app.core.deps import CurrentUser, DbSession
from app.core.services.business_day_service import get_nth_business_day
from app.models.account import Account
from app.models.category import Category
from app.models.household import HouseholdMember
from app.models.income_source import IncomeSource
from app.modules.income.schemas.income_source import (
    IncomeSourceCreate,
    IncomeSourceListResponse,
    IncomeSourceResponse,
    IncomeSourceUpdate,
)
from app.modules.income.services.income_transaction_service import IncomeTransactionService


class SourceAmountOverride(BaseModel):
    source_id: int
    amount: float


class GenerateTransactionsRequest(BaseModel):
    year: int
    month: int
    overwrite: bool = False
    source_ids: list[int] | None = None  # IDs específicos para gerar (None = todas)
    amount_overrides: list[SourceAmountOverride] | None = None


class TransactionPreview(BaseModel):
    source_id: int
    source_name: str
    type: str
    amount: float
    date: str
    is_business_day: bool
    business_day_number: int | None


class BusinessDayResponse(BaseModel):
    year: int
    month: int
    business_day_number: int
    date: str


router = APIRouter()


async def get_household_user_ids(db, user) -> list[int]:
    """Get all user IDs in the same household/license as the user"""
    if not user.license_id:
        return []

    result = await db.execute(
        select(HouseholdMember.user_id).where(HouseholdMember.license_id == user.license_id)
    )
    return list(result.scalars().all())


# ========== Rotas estáticas DEVEM vir antes de /{source_id} ==========


@router.get("/utils/business-day", response_model=BusinessDayResponse)
async def get_business_day(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    n: int = Query(..., ge=1, le=23, description="Qual dia útil (ex: 5 para 5º dia útil)"),
    current_user: CurrentUser = None,
):
    """
    Calcula o N-ésimo dia útil de um mês.
    Considera feriados nacionais brasileiros.
    """
    try:
        business_day = get_nth_business_day(year, month, n)
        return BusinessDayResponse(
            year=year, month=month, business_day_number=n, date=business_day.isoformat()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/preview-transactions", response_model=list[TransactionPreview])
async def preview_income_transactions(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    """
    Retorna uma prévia das transações que seriam criadas para um mês.
    Não cria nada no banco, apenas mostra o que seria gerado.
    """
    service = IncomeTransactionService(db)
    preview = await service.preview_transactions(user_id=current_user.id, year=year, month=month)
    return preview


@router.post("/generate-transactions")
async def generate_income_transactions(
    data: GenerateTransactionsRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Gera transações no histórico para todas as fontes de receita ativas.
    Útil para criar o histórico de receitas mensais como salário, benefícios, etc.
    Permite sobrescrever os valores esperados com amount_overrides.
    """
    # Convert overrides to dict for easier lookup
    amount_overrides_dict = None
    if data.amount_overrides:
        amount_overrides_dict = {
            override.source_id: override.amount for override in data.amount_overrides
        }

    service = IncomeTransactionService(db)
    transactions = await service.generate_income_transactions(
        user_id=current_user.id,
        year=data.year,
        month=data.month,
        overwrite=data.overwrite,
        source_ids=data.source_ids,  # Filtrar por IDs específicos
        amount_overrides=amount_overrides_dict,
    )

    return {
        "message": f"{len(transactions)} transações criadas/atualizadas",
        "count": len(transactions),
        "year": data.year,
        "month": data.month,
    }


# ========== Rotas CRUD ==========


@router.get("", response_model=list[IncomeSourceListResponse])
async def list_income_sources(current_user: CurrentUser, db: DbSession):
    """Lista todas as fontes de receita do usuário"""
    household_user_ids = await get_household_user_ids(db, current_user)

    if household_user_ids:
        result = await db.execute(
            select(IncomeSource)
            .outerjoin(Account, IncomeSource.account_id == Account.id)
            .where(
                or_(
                    and_(
                        IncomeSource.user_id == current_user.id,
                        IncomeSource.ownership_type == "personal",
                    ),
                    and_(
                        IncomeSource.user_id.in_(household_user_ids),
                        IncomeSource.ownership_type == "household",
                    ),
                )
            )
        )
    else:
        result = await db.execute(
            select(IncomeSource)
            .outerjoin(Account, IncomeSource.account_id == Account.id)
            .where(IncomeSource.user_id == current_user.id)
        )

    sources = result.scalars().all()

    if not sources:
        return []

    # Buscar nomes de todas as contas de uma vez
    account_ids = [s.account_id for s in sources if s.account_id]
    account_names = {}
    if account_ids:
        acc_result = await db.execute(
            select(Account.id, Account.name).where(Account.id.in_(account_ids))
        )
        account_names = {row[0]: row[1] for row in acc_result.all()}

    response_list = []
    for source in sources:
        response_list.append(
            IncomeSourceListResponse(
                id=source.id,
                name=source.name,
                type=source.type,
                source_name=source.source_name,
                expected_amount=float(source.expected_amount) if source.expected_amount else None,
                is_variable=source.is_variable,
                frequency=source.frequency,
                payment_day=source.payment_day,
                use_business_day=source.use_business_day,
                business_day_number=source.business_day_number,
                benefit_provider=source.benefit_provider,
                account_name=account_names.get(source.account_id),
                is_active=source.is_active,
            )
        )

    return response_list


@router.post("", response_model=IncomeSourceResponse, status_code=201)
async def create_income_source(
    data: IncomeSourceCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria uma nova fonte de receita"""
    # Validate account_id if provided
    if data.account_id:
        acc_result = await db.execute(
            select(Account).where(
                Account.id == data.account_id,
                Account.user_id == current_user.id,
            )
        )
        if not acc_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Conta não encontrada")

    # Validate category_id if provided
    if data.category_id:
        cat_result = await db.execute(select(Category).where(Category.id == data.category_id))
        if not cat_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Categoria não encontrada")

    source = IncomeSource(
        user_id=current_user.id,
        name=data.name,
        type=data.type.value,
        source_name=data.source_name,
        expected_amount=data.expected_amount,
        is_variable=data.is_variable,
        frequency=data.frequency.value,
        payment_day=data.payment_day,
        use_business_day=data.use_business_day,
        business_day_number=data.business_day_number,
        account_id=data.account_id,
        category_id=data.category_id,
        benefit_card_number=data.benefit_card_number,
        benefit_provider=data.benefit_provider,
        is_taxable=data.is_taxable,
        tax_category=data.tax_category,
        notes=data.notes,
        ownership_type=data.ownership_type.value,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    # Get related names
    account_name = None
    category_name = None

    if source.account_id:
        acc_result = await db.execute(select(Account.name).where(Account.id == source.account_id))
        account_name = acc_result.scalar_one_or_none()

    if source.category_id:
        cat_result = await db.execute(
            select(Category.name).where(Category.id == source.category_id)
        )
        category_name = cat_result.scalar_one_or_none()

    return IncomeSourceResponse(
        id=source.id,
        user_id=source.user_id,
        name=source.name,
        type=source.type,
        source_name=source.source_name,
        expected_amount=float(source.expected_amount) if source.expected_amount else None,
        is_variable=source.is_variable,
        frequency=source.frequency,
        payment_day=source.payment_day,
        account_id=source.account_id,
        category_id=source.category_id,
        benefit_card_number=source.benefit_card_number,
        benefit_provider=source.benefit_provider,
        is_taxable=source.is_taxable,
        tax_category=source.tax_category,
        notes=source.notes,
        is_active=source.is_active,
        ownership_type=source.ownership_type,
        created_at=source.created_at,
        updated_at=source.updated_at,
        account_name=account_name,
        category_name=category_name,
    )


@router.get("/{source_id}", response_model=IncomeSourceResponse)
async def get_income_source(
    source_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna uma fonte de receita específica"""
    result = await db.execute(
        select(IncomeSource).where(
            IncomeSource.id == source_id,
            IncomeSource.user_id == current_user.id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Fonte de receita não encontrada")

    # Get related names
    account_name = None
    category_name = None

    if source.account_id:
        acc_result = await db.execute(select(Account.name).where(Account.id == source.account_id))
        account_name = acc_result.scalar_one_or_none()

    if source.category_id:
        cat_result = await db.execute(
            select(Category.name).where(Category.id == source.category_id)
        )
        category_name = cat_result.scalar_one_or_none()

    return IncomeSourceResponse(
        id=source.id,
        user_id=source.user_id,
        name=source.name,
        type=source.type,
        source_name=source.source_name,
        expected_amount=float(source.expected_amount) if source.expected_amount else None,
        is_variable=source.is_variable,
        frequency=source.frequency,
        payment_day=source.payment_day,
        account_id=source.account_id,
        category_id=source.category_id,
        benefit_card_number=source.benefit_card_number,
        benefit_provider=source.benefit_provider,
        is_taxable=source.is_taxable,
        tax_category=source.tax_category,
        notes=source.notes,
        is_active=source.is_active,
        ownership_type=source.ownership_type,
        created_at=source.created_at,
        updated_at=source.updated_at,
        account_name=account_name,
        category_name=category_name,
    )


@router.patch("/{source_id}", response_model=IncomeSourceResponse)
async def update_income_source(
    source_id: int,
    data: IncomeSourceUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza uma fonte de receita"""
    result = await db.execute(
        select(IncomeSource).where(
            IncomeSource.id == source_id,
            IncomeSource.user_id == current_user.id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Fonte de receita não encontrada")

    update_data = data.model_dump(exclude_unset=True)

    # Validate account_id if being updated
    if "account_id" in update_data and update_data["account_id"]:
        acc_result = await db.execute(
            select(Account).where(
                Account.id == update_data["account_id"],
                Account.user_id == current_user.id,
            )
        )
        if not acc_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Conta não encontrada")

    for field, value in update_data.items():
        if field == "type" and value:
            value = value.value
        elif field == "frequency" and value:
            value = value.value
        setattr(source, field, value)

    await db.commit()
    await db.refresh(source)

    # Get related names
    account_name = None
    category_name = None

    if source.account_id:
        acc_result = await db.execute(select(Account.name).where(Account.id == source.account_id))
        account_name = acc_result.scalar_one_or_none()

    if source.category_id:
        cat_result = await db.execute(
            select(Category.name).where(Category.id == source.category_id)
        )
        category_name = cat_result.scalar_one_or_none()

    return IncomeSourceResponse(
        id=source.id,
        user_id=source.user_id,
        name=source.name,
        type=source.type,
        source_name=source.source_name,
        expected_amount=float(source.expected_amount) if source.expected_amount else None,
        is_variable=source.is_variable,
        frequency=source.frequency,
        payment_day=source.payment_day,
        account_id=source.account_id,
        category_id=source.category_id,
        benefit_card_number=source.benefit_card_number,
        benefit_provider=source.benefit_provider,
        is_taxable=source.is_taxable,
        tax_category=source.tax_category,
        notes=source.notes,
        is_active=source.is_active,
        ownership_type=source.ownership_type,
        created_at=source.created_at,
        updated_at=source.updated_at,
        account_name=account_name,
        category_name=category_name,
    )


@router.delete("/{source_id}", status_code=204)
async def delete_income_source(
    source_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove uma fonte de receita"""
    result = await db.execute(
        select(IncomeSource).where(
            IncomeSource.id == source_id,
            IncomeSource.user_id == current_user.id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Fonte de receita não encontrada")

    await db.delete(source)
    await db.commit()


# ========== Rotas com {source_id} no final ==========


@router.post("/{source_id}/generate-transaction")
async def generate_single_source_transaction(
    source_id: int,
    data: GenerateTransactionsRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Gera transação para uma fonte de receita específica.
    """
    service = IncomeTransactionService(db)
    transactions = await service.generate_for_specific_source(
        source_id=source_id,
        user_id=current_user.id,
        year=data.year,
        month=data.month,
        overwrite=data.overwrite,
    )

    if not transactions:
        raise HTTPException(status_code=404, detail="Fonte não encontrada ou transação já existe")

    return {
        "message": f"{len(transactions)} transação(ões) criada(s)",
        "count": len(transactions),
    }
