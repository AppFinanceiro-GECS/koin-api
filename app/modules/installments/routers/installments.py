"""Router para gerenciamento de séries de parcelas"""

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import CurrentUser, DbSession
from app.models.installment import InstallmentSeriesStatus
from app.modules.installments.schemas.duplicate import (
    DuplicateGroupsResponse,
    MergeSeriesRequest,
    TransactionDuplicatesResponse,
    UpdateSeriesRequest,
)
from app.modules.installments.schemas.installment import InstallmentSeriesResponse
from app.modules.installments.services.duplicate_detection_service import DuplicateDetectionService
from app.modules.installments.services.installment_service import InstallmentService

router = APIRouter()


@router.get("", response_model=list[InstallmentSeriesResponse])
async def list_series(
    current_user: CurrentUser,
    db: DbSession,
    status_filter: InstallmentSeriesStatus | None = Query(None),
    limit: int = Query(50, le=100),
):
    """Lista séries de parcelas do usuário"""
    service = InstallmentService(db)
    series = await service.get_user_series(
        user=current_user,
        status_filter=status_filter,
        limit=limit,
    )
    return series


@router.get("/{series_id}", response_model=InstallmentSeriesResponse)
async def get_series(
    series_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna uma série específica"""
    service = InstallmentService(db)
    series = await service.get_series_by_id(current_user, series_id)
    if not series:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Série não encontrada")
    return series


@router.post("/detect-duplicates", response_model=DuplicateGroupsResponse)
async def detect_duplicates(
    current_user: CurrentUser,
    db: DbSession,
    min_similarity: float = Query(0.80, ge=0.5, le=1.0),
):
    """
    Detecta séries potencialmente duplicadas.

    Retorna grupos de séries similares com score de similaridade,
    conflitos identificados e sugestão de série primária.

    O threshold padrão de 0.80 (80%) foi escolhido para minimizar falsos positivos,
    garantindo que apenas duplicatas com alta confiança sejam detectadas.
    """
    service = DuplicateDetectionService(db)
    duplicate_groups = await service.find_duplicate_groups(
        user=current_user,
        min_similarity=min_similarity,
    )

    return DuplicateGroupsResponse(
        duplicate_groups=duplicate_groups,
        total_groups=len(duplicate_groups),
    )


@router.post("/detect-transaction-duplicates", response_model=TransactionDuplicatesResponse)
async def detect_transaction_duplicates(
    current_user: CurrentUser,
    db: DbSession,
    min_similarity: float = Query(0.80, ge=0.5, le=1.0),
    credit_card_id: int | None = Query(None, description="Filtrar por cartão específico"),
    reference_month: int | None = Query(None, ge=1, le=12, description="Mês de referência"),
    reference_year: int | None = Query(None, ge=2020, le=2100, description="Ano de referência"),
):
    """
    Detecta duplicatas entre transações individuais.

    Compara transações avulsas vs transações de séries, detectando duplicatas como:
    - "cartao protegido" vs "Seg. Cartão Protegido com Piv. jan/26"

    Critérios de detecção:
    - Valores iguais ou muito próximos (±R$ 0,05)
    - Descrições similares (fuzzy matching >= 80%)
    - Datas próximas (±3 dias)

    O threshold padrão de 0.80 (80%) foi escolhido para minimizar falsos positivos.
    """
    service = DuplicateDetectionService(db)
    result = await service.find_transaction_duplicates(
        user=current_user,
        min_similarity=min_similarity,
        credit_card_id=credit_card_id,
        reference_month=reference_month,
        reference_year=reference_year,
    )

    return result


@router.post("/merge", response_model=InstallmentSeriesResponse)
async def merge_series(
    data: MergeSeriesRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Mescla duas séries de parcelas.

    A série source será marcada como MERGED e suas transações
    movidas para a série target. Conflitos são resolvidos
    conforme a estratégia escolhida.
    """
    service = DuplicateDetectionService(db)
    merged = await service.merge_series(
        user=current_user,
        source_id=data.source_series_id,
        target_id=data.target_series_id,
        conflict_resolution=data.conflict_resolution,
        new_merchant_name=data.new_merchant_name,
    )
    await db.commit()
    return merged


@router.patch("/{series_id}", response_model=InstallmentSeriesResponse)
async def update_series(
    series_id: int,
    data: UpdateSeriesRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Atualiza informações de uma série.

    Permite renomear série ou marcar como não duplicata de outras.
    """
    service = InstallmentService(db)
    series = await service.get_series_by_id(current_user, series_id)

    if not series:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Série não encontrada")

    # Atualizar campos fornecidos
    if data.description is not None:
        series.description = data.description

    if data.merchant_name is not None:
        series.merchant_name = data.merchant_name

    if data.not_duplicate_with is not None:
        series.not_duplicate_with = data.not_duplicate_with

    await db.flush()
    await db.refresh(series)
    await db.commit()

    return series
