from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbSession
from app.models.receipt import ReceiptStatus
from app.modules.receipts.schemas.receipt import (
    ReceiptConfirmRequest,
    ReceiptListResponse,
    ReceiptResponse,
    ReceiptUpdate,
)
from app.modules.receipts.services.receipt_service import ReceiptService

router = APIRouter()


@router.post("/confirm", response_model=ReceiptResponse, status_code=201)
async def confirm_receipt(
    data: ReceiptConfirmRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Confirma um receipt a partir dos dados extraídos do documento.
    Cria o Receipt, os ReceiptPayments e as Transactions vinculadas.
    """
    service = ReceiptService(db)
    return await service.confirm_receipt(current_user, data)


@router.get("", response_model=list[ReceiptListResponse])
async def list_receipts(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(20, le=100, ge=1),
    offset: int = Query(0, ge=0),
    status: ReceiptStatus | None = None,
):
    """Lista todos os receipts do usuário"""
    service = ReceiptService(db)
    return await service.list_receipts(current_user, limit, offset, status)


@router.get("/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna um receipt específico com todos os detalhes"""
    service = ReceiptService(db)
    return await service.get_receipt(current_user, receipt_id)


@router.get("/{receipt_id}/items")
async def get_receipt_items(
    receipt_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna as transações (itens) de um receipt"""
    service = ReceiptService(db)
    return await service.get_receipt_items(current_user, receipt_id)


@router.patch("/{receipt_id}", response_model=ReceiptResponse)
async def update_receipt(
    receipt_id: int,
    data: ReceiptUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza dados de um receipt (store, payments)"""
    service = ReceiptService(db)
    return await service.update_receipt(current_user, receipt_id, data)


@router.delete("/{receipt_id}", status_code=204)
async def cancel_receipt(
    receipt_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cancela um receipt (soft delete)"""
    service = ReceiptService(db)
    await service.cancel_receipt(current_user, receipt_id)
