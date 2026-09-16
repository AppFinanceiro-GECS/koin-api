from datetime import date

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbSession
from app.modules.analytics.schemas.analytics import (
    AnalyticsSummary,
    InsightResponse,
    PaymentMethodReport,
)
from app.modules.analytics.services.analytics_service import AnalyticsService

router = APIRouter()


@router.get("/summary", response_model=AnalyticsSummary)
async def get_monthly_summary(
    current_user: CurrentUser,
    db: DbSession,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
):
    """
    Retorna resumo analitico do mes:
    - Totais de receita/despesa
    - Gastos por categoria
    - Top merchants
    - Comparativo com mes anterior
    """
    service = AnalyticsService(db)
    return await service.get_monthly_summary(current_user, year, month)


@router.get("/insights", response_model=list[InsightResponse])
async def get_insights(
    current_user: CurrentUser,
    db: DbSession,
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    """
    Retorna insights explicaveis sobre os gastos:
    - Vazamentos (gastos pequenos frequentes)
    - Drivers (principais categorias)
    - Oportunidades de economia
    """
    service = AnalyticsService(db)
    return await service.get_insights(current_user, start_date, end_date)


@router.get("/by-payment-method", response_model=PaymentMethodReport)
async def get_spending_by_payment_method(
    current_user: CurrentUser,
    db: DbSession,
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    """
    Retorna relatorio de gastos agrupados por metodo de pagamento:
    - Cartao de credito
    - Cartao de debito
    - PIX
    - Boleto
    - Transferencia
    - Dinheiro
    - Vale alimentacao/refeicao
    """
    service = AnalyticsService(db)
    return await service.get_spending_by_payment_method(current_user, start_date, end_date)
