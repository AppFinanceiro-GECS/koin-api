"""Endpoints de Orçamento (Budget)"""

from datetime import date

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbSession
from app.modules.budgets.schemas.budget import (
    BudgetComparisonResponse,
    BudgetCopyRequest,
    BudgetCreate,
    BudgetItemCreate,
    BudgetItemHistoryResponse,
    BudgetItemResponse,
    BudgetItemUpdate,
    BudgetResponse,
    BudgetSummary,
    BudgetTransferRequest,
    BudgetTransferResponse,
    BudgetUpdate,
)
from app.modules.budgets.services.budget_service import BudgetService

router = APIRouter()


@router.get("", response_model=BudgetResponse)
async def get_budget(
    current_user: CurrentUser,
    db: DbSession,
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
):
    """
    Retorna orçamento do mês com gastos calculados.
    Se não existir, cria um orçamento vazio.
    """
    service = BudgetService(db)
    return await service.get_budget(current_user, year, month)


@router.post("", response_model=BudgetResponse, status_code=201)
async def create_budget(
    data: BudgetCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria orçamento para o mês com itens por categoria"""
    service = BudgetService(db)
    budget = await service.create_budget(current_user, data)
    return await service.get_budget(current_user, budget.year, budget.month)


@router.patch("", response_model=BudgetResponse)
async def update_budget(
    data: BudgetUpdate,
    current_user: CurrentUser,
    db: DbSession,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
):
    """Atualiza configurações do orçamento"""
    service = BudgetService(db)
    await service.update_budget(current_user, year, month, data)
    return await service.get_budget(current_user, year, month)


@router.get("/summary", response_model=BudgetSummary)
async def get_budget_summary(
    current_user: CurrentUser,
    db: DbSession,
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
):
    """Retorna resumo do orçamento para dashboard"""
    service = BudgetService(db)
    return await service.get_summary(current_user, year, month)


@router.get("/comparison", response_model=list[BudgetComparisonResponse])
async def get_budget_comparison(
    current_user: CurrentUser,
    db: DbSession,
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
):
    """Compara orçamento planejado vs realizado por categoria"""
    service = BudgetService(db)
    return await service.get_comparison(current_user, year, month)


@router.post("/copy", response_model=BudgetResponse, status_code=201)
async def copy_budget(
    data: BudgetCopyRequest,
    current_user: CurrentUser,
    db: DbSession,
    target_year: int = Query(...),
    target_month: int = Query(..., ge=1, le=12),
):
    """
    Copia orçamento de outro mês.
    Útil para manter consistência mês a mês.
    """
    service = BudgetService(db)
    budget = await service.copy_budget(
        current_user,
        target_year,
        target_month,
        data.source_year,
        data.source_month,
        data.include_rollover,
    )
    return await service.get_budget(current_user, budget.year, budget.month)


@router.post("/items", response_model=BudgetItemResponse, status_code=201)
async def add_budget_item(
    data: BudgetItemCreate,
    current_user: CurrentUser,
    db: DbSession,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
):
    """Adiciona item (categoria) ao orçamento"""
    service = BudgetService(db)
    return await service.add_budget_item(current_user, year, month, data)


@router.patch("/items/{item_id}", response_model=BudgetItemResponse)
async def update_budget_item(
    item_id: int,
    data: BudgetItemUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza item do orçamento"""
    service = BudgetService(db)
    return await service.update_budget_item(current_user, item_id, data)


@router.delete("/items/{item_id}", status_code=204)
async def delete_budget_item(
    item_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove item do orçamento"""
    service = BudgetService(db)
    await service.delete_budget_item(current_user, item_id)


@router.post("/transfer", response_model=BudgetTransferResponse)
async def transfer_budget(
    data: BudgetTransferRequest,
    current_user: CurrentUser,
    db: DbSession,
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
):
    """
    Transfere orçamento entre categorias.

    "Roll with the Punches" (YNAB) - Ajustar orçamento movendo entre categorias
    quando uma categoria precisa de mais verba.
    """
    service = BudgetService(db)
    return await service.transfer(current_user, year, month, data)


@router.get("/items/{category_id}/history", response_model=list[BudgetItemHistoryResponse])
async def get_budget_item_history(
    category_id: int,
    current_user: CurrentUser,
    db: DbSession,
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    limit: int = Query(default=50, ge=1, le=100),
):
    """
    Retorna histórico de mudanças de um item de orçamento.

    Inclui gastos, estornos, ajustes, transferências e rollovers.
    """
    service = BudgetService(db)
    return await service.get_item_history(current_user, year, month, category_id, limit)
