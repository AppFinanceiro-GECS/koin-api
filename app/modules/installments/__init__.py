"""
Installments Module

This module handles installment series and installment transaction management.
"""

from app.modules.installments.routers.installments import router
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
from app.modules.installments.services.installment_service import InstallmentService

__all__ = [
    "router",
    "InstallmentSeriesBase",
    "InstallmentSeriesCreate",
    "InstallmentSeriesResponse",
    "InstallmentStatusResponse",
    "InstallmentSeriesDetailResponse",
    "ConfirmInstallmentRequest",
    "MarkInstallmentsPaidRequest",
    "CreateFutureInstallmentsRequest",
    "InstallmentService",
]
