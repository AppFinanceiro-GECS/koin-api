"""Endpoints de Gestão de Dívidas (Debts)"""

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import CurrentUser, DbSession
from app.models.debt import DebtStatus
from app.modules.debts.schemas.debt import (
    AvalanchePlan,
    DebtCreate,
    DebtDetailResponse,
    DebtPaymentCreate,
    DebtPaymentResponse,
    DebtResponse,
    DebtSummary,
    DebtUpdate,
    PayoffStrategyComparison,
    SnowballPlan,
)
from app.modules.debts.services.debt_service import DebtService

router = APIRouter()


@router.get("", response_model=list[DebtResponse])
async def list_debts(
    current_user: CurrentUser,
    db: DbSession,
    status_filter: DebtStatus | None = Query(None, alias="status"),
):
    """Lista dívidas do usuário"""
    service = DebtService(db)
    return await service.list_debts(current_user, status_filter)


@router.post("", response_model=DebtResponse, status_code=201)
async def create_debt(
    data: DebtCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Registra nova dívida.

    Tipos de dívida:
    - credit_card: Cartão de crédito
    - personal_loan: Empréstimo pessoal
    - car_loan: Financiamento de carro
    - mortgage: Financiamento imobiliário
    - student_loan: Empréstimo estudantil
    - medical: Dívida médica
    - store_credit: Crediário de loja
    - other: Outros
    """
    service = DebtService(db)
    debt = await service.create_debt(current_user, data)
    debts = await service.list_debts(current_user)
    return next(d for d in debts if d.id == debt.id)


@router.get("/summary", response_model=DebtSummary)
async def get_debts_summary(
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna resumo de todas as dívidas para dashboard"""
    service = DebtService(db)
    return await service.get_summary(current_user)


@router.get("/snowball", response_model=SnowballPlan)
async def get_snowball_plan(
    current_user: CurrentUser,
    db: DbSession,
    monthly_payment: Decimal = Query(
        ..., gt=0, description="Valor total disponível para pagar dívidas por mês"
    ),
):
    """
    Gera plano de quitação pelo método Snowball (Dave Ramsey).

    O método Snowball ordena as dívidas do menor para o maior saldo.
    Você paga o mínimo em todas as dívidas, exceto a menor, que recebe
    todo o extra. Quando uma dívida é quitada, o valor vai para a próxima.

    Vantagem: Vitórias rápidas que motivam a continuar.
    """
    service = DebtService(db)
    return await service.get_snowball_plan(current_user, monthly_payment)


@router.get("/avalanche", response_model=AvalanchePlan)
async def get_avalanche_plan(
    current_user: CurrentUser,
    db: DbSession,
    monthly_payment: Decimal = Query(
        ..., gt=0, description="Valor total disponível para pagar dívidas por mês"
    ),
):
    """
    Gera plano de quitação pelo método Avalanche.

    O método Avalanche ordena as dívidas da maior para a menor taxa de juros.
    Matematicamente mais eficiente, economiza mais em juros.

    Vantagem: Menor custo total de juros.
    """
    service = DebtService(db)
    return await service.get_avalanche_plan(current_user, monthly_payment)


@router.get("/compare-strategies", response_model=PayoffStrategyComparison)
async def compare_payoff_strategies(
    current_user: CurrentUser,
    db: DbSession,
    monthly_payment: Decimal = Query(
        ..., gt=0, description="Valor total disponível para pagar dívidas por mês"
    ),
):
    """
    Compara estratégias Snowball e Avalanche.

    Retorna recomendação baseada em:
    - Diferença de tempo para quitar
    - Diferença de juros pagos
    - Perfil psicológico (motivação vs matemática)
    """
    service = DebtService(db)
    return await service.compare_strategies(current_user, monthly_payment)


@router.get("/{debt_id}", response_model=DebtDetailResponse)
async def get_debt(
    debt_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna dívida com detalhes, pagamentos e projeção"""
    service = DebtService(db)
    debt = await service.get_debt(current_user, debt_id)
    if not debt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dívida não encontrada")
    return debt


@router.patch("/{debt_id}", response_model=DebtResponse)
async def update_debt(
    debt_id: int,
    data: DebtUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza dívida"""
    service = DebtService(db)
    debt = await service.update_debt(current_user, debt_id, data)
    debts = await service.list_debts(current_user)
    return next(d for d in debts if d.id == debt.id)


@router.delete("/{debt_id}", status_code=204)
async def delete_debt(
    debt_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove dívida"""
    service = DebtService(db)
    await service.delete_debt(current_user, debt_id)


@router.post("/{debt_id}/payments", response_model=DebtPaymentResponse, status_code=201)
async def add_payment(
    debt_id: int,
    data: DebtPaymentCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Registra pagamento de dívida.
    Atualiza automaticamente o saldo devedor.
    """
    service = DebtService(db)
    return await service.add_payment(current_user, debt_id, data)
