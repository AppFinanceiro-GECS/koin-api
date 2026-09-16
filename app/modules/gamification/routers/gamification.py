"""Gamification API Router"""

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import CurrentUser, DbSession

from ..schemas import (
    BadgeResponse,
    ChallengeListResponse,
    ChallengeStartResponse,
    GamificationSummary,
    PointsHistoryResponse,
    StreakWeekView,
)
from ..services import GamificationService

router = APIRouter()


@router.get("/summary", response_model=GamificationSummary)
async def get_gamification_summary(
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Retorna resumo de gamificação para o dashboard.
    Inclui pontos, badges, streaks e desafios.
    """
    service = GamificationService(db)
    return await service.get_summary(current_user)


@router.get("/streak/week", response_model=StreakWeekView)
async def get_streak_week_view(
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Retorna visualização da semana para o widget de streak.
    Mostra dias completados, atual e futuros.
    """
    service = GamificationService(db)
    return await service.get_streak_week_view(current_user)


@router.get("/badges", response_model=list[BadgeResponse])
async def list_badges(
    current_user: CurrentUser,
    db: DbSession,
    category: str | None = Query(None, description="Filtrar por categoria"),
):
    """
    Lista todos os badges com status do usuário.
    Mostra progresso para badges não conquistados.
    """
    service = GamificationService(db)
    return await service.get_all_badges(current_user, category)


@router.post("/badges/mark-seen")
async def mark_badges_seen(
    current_user: CurrentUser,
    db: DbSession,
):
    """Marca todos os badges não vistos como vistos"""
    service = GamificationService(db)
    count = await service.mark_badges_seen(current_user)
    return {"marked_seen": count}


@router.get("/challenges", response_model=ChallengeListResponse)
async def list_challenges(
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Lista desafios organizados por status.
    Retorna ativos, completados, falhados e disponíveis.
    """
    service = GamificationService(db)
    return await service.get_challenges(current_user)


@router.post("/challenges/{challenge_id}/start", response_model=ChallengeStartResponse)
async def start_challenge(
    challenge_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Inicia um desafio para o usuário"""
    service = GamificationService(db)
    result = await service.start_challenge(current_user, challenge_id)
    if not result:
        raise HTTPException(status_code=404, detail="Desafio não encontrado ou já iniciado")
    return ChallengeStartResponse(challenge=result, message="Desafio iniciado com sucesso!")


@router.get("/points/history", response_model=PointsHistoryResponse)
async def get_points_history(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
):
    """Histórico de movimentação de pontos"""
    service = GamificationService(db)

    # Obter histórico
    transactions = await service.points_service.get_history(
        current_user, limit=limit, offset=offset
    )

    # Obter saldo atual
    balance = await service.points_service.get_or_create_balance(current_user)

    return PointsHistoryResponse(
        transactions=transactions,
        current_balance=balance.current_points,
        lifetime_total=balance.lifetime_points,
    )
