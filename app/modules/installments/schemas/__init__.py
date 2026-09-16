"""Installments module schemas"""

from app.modules.installments.schemas.installment import (
    ConfirmInstallmentRequest,
    CreateFutureInstallmentsRequest,
    InstallmentSeriesBase,
    InstallmentSeriesCreate,
    InstallmentSeriesDetailResponse,
    InstallmentSeriesResponse,
    InstallmentStatusResponse,
    MarkInstallmentsPaidRequest,
)

__all__ = [
    "InstallmentSeriesBase",
    "InstallmentSeriesCreate",
    "InstallmentSeriesResponse",
    "InstallmentStatusResponse",
    "InstallmentSeriesDetailResponse",
    "ConfirmInstallmentRequest",
    "MarkInstallmentsPaidRequest",
    "CreateFutureInstallmentsRequest",
]
