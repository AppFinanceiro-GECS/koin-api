"""Endpoints de Metas Financeiras (Goals)"""

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import CurrentUser, DbSession
from app.models.goal import GoalStatus
from app.modules.goals.schemas.goal import (
    EmergencyFundCalculation,
    GoalContributionCreate,
    GoalContributionResponse,
    GoalCreate,
    GoalDetailResponse,
    GoalResponse,
    GoalSummary,
    GoalUpdate,
    PNIFCalculation,
)
from app.modules.goals.services.goal_service import GoalService

router = APIRouter()


@router.get("", response_model=list[GoalResponse])
async def list_goals(
    current_user: CurrentUser,
    db: DbSession,
    status_filter: GoalStatus | None = Query(None, alias="status"),
):
    """Lista metas do usuário"""
    service = GoalService(db)
    return await service.list_goals(current_user, status_filter)


@router.post("", response_model=GoalResponse, status_code=201)
async def create_goal(
    data: GoalCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Cria nova meta financeira.

    Tipos de meta:
    - savings: Economia para algo específico
    - emergency: Fundo de emergência (Baby Step 3)
    - debt_free: Quitar dívidas
    - investment: Meta de investimento
    - retirement: Aposentadoria / PNIF
    - purchase: Compra específica
    - custom: Meta personalizada
    """
    service = GoalService(db)
    goal = await service.create_goal(current_user, data)
    goals = await service.list_goals(current_user)
    return next(g for g in goals if g.id == goal.id)


@router.get("/summary", response_model=GoalSummary)
async def get_goals_summary(
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna resumo de todas as metas para dashboard"""
    service = GoalService(db)
    return await service.get_summary(current_user)


@router.get("/emergency-fund", response_model=EmergencyFundCalculation)
async def calculate_emergency_fund(
    current_user: CurrentUser,
    db: DbSession,
    months: int = Query(6, ge=1, le=12),
):
    """
    Calcula fundo de emergência recomendado.

    Baseado no Baby Step 3 de Dave Ramsey:
    - Recomenda 3-6 meses de despesas
    - Calcula quanto você já tem guardado
    - Mostra quantos meses você está coberto
    """
    service = GoalService(db)
    return await service.calculate_emergency_fund(current_user, months)


@router.get("/pnif", response_model=PNIFCalculation)
async def calculate_pnif(
    current_user: CurrentUser,
    db: DbSession,
    expected_return: float = Query(
        0.08, ge=0.01, le=0.30, description="Taxa de retorno anual esperada"
    ),
):
    """
    Calcula PNIF - Patrimônio Necessário para Independência Financeira.

    Metodologia Gustavo Cerbasi:
    PNIF = Gasto Anual / Rentabilidade

    Exemplo: Se você gasta R$ 60.000/ano e espera 8% de retorno,
    seu PNIF é R$ 750.000.
    """
    service = GoalService(db)
    return await service.calculate_pnif(current_user, expected_return)


@router.get("/{goal_id}", response_model=GoalDetailResponse)
async def get_goal(
    goal_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna meta com detalhes, contribuições e projeção"""
    service = GoalService(db)
    goal = await service.get_goal(current_user, goal_id)
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta não encontrada")
    return goal


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: int,
    data: GoalUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza meta"""
    service = GoalService(db)
    goal = await service.update_goal(current_user, goal_id, data)
    goals = await service.list_goals(current_user)
    return next(g for g in goals if g.id == goal.id)


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(
    goal_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove meta"""
    service = GoalService(db)
    await service.delete_goal(current_user, goal_id)


@router.post("/{goal_id}/contributions", response_model=GoalContributionResponse, status_code=201)
async def add_contribution(
    goal_id: int,
    data: GoalContributionCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Adiciona contribuição à meta.
    Atualiza automaticamente o valor atual da meta.
    """
    service = GoalService(db)
    return await service.add_contribution(current_user, goal_id, data)
