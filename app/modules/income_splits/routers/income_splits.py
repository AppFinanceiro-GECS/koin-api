"""
REST API endpoints for income split rules.
Allows users to configure rules for splitting income into expenses (e.g., tithe, savings).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models.category import Category
from app.modules.income_splits.schemas.income_split import (
    IncomeSplitPreview,
    IncomeSplitRuleCreate,
    IncomeSplitRuleResponse,
    IncomeSplitRuleUpdate,
)
from app.modules.income_splits.services.income_split_service import IncomeSplitService

router = APIRouter()


class PreviewRequest(BaseModel):
    """Request body for previewing splits"""

    amount: float
    rule_ids: list[int] | None = None
    description: str | None = None


@router.get("", response_model=list[IncomeSplitRuleResponse])
async def list_income_split_rules(
    current_user: CurrentUser,
    db: DbSession,
    active_only: bool = Query(True, description="Retorna apenas regras ativas"),
):
    """
    Lista todas as regras de divisão de receita do usuário.
    Por padrão, retorna apenas regras ativas.
    """
    service = IncomeSplitService(db)
    return await service.get_rules_with_category_names(current_user, active_only)


@router.post("", response_model=IncomeSplitRuleResponse, status_code=201)
async def create_income_split_rule(
    data: IncomeSplitRuleCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Cria uma nova regra de divisão de receita.

    Exemplos de uso:
    - Dízimo: 10% de cada receita
    - Poupança: 20% de cada receita
    - Investimento: valor fixo de R$ 500,00
    """
    # Validate category_id if provided
    if data.category_id:
        cat_result = await db.execute(select(Category).where(Category.id == data.category_id))
        if not cat_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Categoria não encontrada")

    service = IncomeSplitService(db)
    rule = await service.create(current_user, data)
    await db.commit()
    await db.refresh(rule)

    # Get category name
    category_name = None
    if rule.category_id:
        cat_result = await db.execute(select(Category.name).where(Category.id == rule.category_id))
        category_name = cat_result.scalar_one_or_none()

    return IncomeSplitRuleResponse(
        id=rule.id,
        user_id=rule.user_id,
        name=rule.name,
        split_type=rule.split_type,
        percentage=float(rule.percentage) if rule.percentage else None,
        fixed_amount=float(rule.fixed_amount) if rule.fixed_amount else None,
        category_id=rule.category_id,
        category_name=category_name,
        description_template=rule.description_template,
        is_active=rule.is_active,
        priority=rule.priority,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("/{rule_id}", response_model=IncomeSplitRuleResponse)
async def get_income_split_rule(
    rule_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna uma regra de divisão específica"""
    service = IncomeSplitService(db)
    rule = await service.get_by_id(current_user, rule_id)

    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    # Get category name
    category_name = None
    if rule.category_id:
        cat_result = await db.execute(select(Category.name).where(Category.id == rule.category_id))
        category_name = cat_result.scalar_one_or_none()

    return IncomeSplitRuleResponse(
        id=rule.id,
        user_id=rule.user_id,
        name=rule.name,
        split_type=rule.split_type,
        percentage=float(rule.percentage) if rule.percentage else None,
        fixed_amount=float(rule.fixed_amount) if rule.fixed_amount else None,
        category_id=rule.category_id,
        category_name=category_name,
        description_template=rule.description_template,
        is_active=rule.is_active,
        priority=rule.priority,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.patch("/{rule_id}", response_model=IncomeSplitRuleResponse)
async def update_income_split_rule(
    rule_id: int,
    data: IncomeSplitRuleUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza uma regra de divisão existente"""
    # Validate category_id if being updated
    if data.category_id:
        cat_result = await db.execute(select(Category).where(Category.id == data.category_id))
        if not cat_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Categoria não encontrada")

    service = IncomeSplitService(db)
    rule = await service.update(current_user, rule_id, data)

    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    await db.commit()
    await db.refresh(rule)

    # Get category name
    category_name = None
    if rule.category_id:
        cat_result = await db.execute(select(Category.name).where(Category.id == rule.category_id))
        category_name = cat_result.scalar_one_or_none()

    return IncomeSplitRuleResponse(
        id=rule.id,
        user_id=rule.user_id,
        name=rule.name,
        split_type=rule.split_type,
        percentage=float(rule.percentage) if rule.percentage else None,
        fixed_amount=float(rule.fixed_amount) if rule.fixed_amount else None,
        category_id=rule.category_id,
        category_name=category_name,
        description_template=rule.description_template,
        is_active=rule.is_active,
        priority=rule.priority,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.delete("/{rule_id}", status_code=204)
async def delete_income_split_rule(
    rule_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove uma regra de divisão"""
    service = IncomeSplitService(db)
    deleted = await service.delete(current_user, rule_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    await db.commit()


@router.post("/preview", response_model=list[IncomeSplitPreview])
async def preview_splits(
    data: PreviewRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Retorna uma prévia dos valores que seriam gerados para uma receita.
    Útil para mostrar no formulário antes de confirmar a criação.

    Exemplo:
    - Receita: R$ 5.000,00
    - Dízimo (10%): R$ 500,00
    - Poupança (20%): R$ 1.000,00
    """
    service = IncomeSplitService(db)
    return await service.preview_splits(
        user=current_user,
        income_amount=data.amount,
        rule_ids=data.rule_ids,
        income_description=data.description,
    )
