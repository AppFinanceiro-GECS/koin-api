"""
Retenção das faturas enviadas (#50). Fatura de cartão é dado financeiro pessoal:
guardar o mínimo, pelo menor tempo.

- Documento confirmado (virou transação, fatura ou compra): o original e o
  `extracted_data` são apagados DOCUMENT_RETENTION_DAYS depois do processamento.
- Documento `failed`: o original sai no mesmo prazo (não há o que confirmar).
- pending, processing, waiting_ai e lido-mas-não-confirmado ficam intocados: o
  usuário ainda pode confirmar.

A linha do documento continua (hash para detectar reenvio, vínculo com a transação);
só o arquivo e os dados extraídos somem. Política em docs/backend/RETENCAO.md.
"""

import asyncio
import logging
import os
from datetime import timedelta

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.utils import utc_now
from app.models.credit_card_invoice import CreditCardInvoice
from app.models.document import Document, DocumentStatus
from app.models.receipt import Receipt
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

BATCH_SIZE = 200


def _confirmed():
    return or_(
        exists().where(Transaction.document_id == Document.id),
        exists().where(CreditCardInvoice.document_id == Document.id),
        exists().where(Receipt.document_id == Document.id),
    )


async def purge_expired_documents(db: AsyncSession, days: int | None = None) -> int:
    """Apaga arquivo e dados extraídos dos documentos vencidos. Devolve quantos."""
    days = settings.document_retention_days if days is None else days
    if days <= 0:
        return 0  # 0 desliga a retenção (ex.: ambiente de testes manuais)

    cutoff = utc_now() - timedelta(days=days)
    reference = func.coalesce(Document.processed_at, Document.created_at)
    expired = (
        await db.execute(
            select(Document)
            .where(
                Document.file_purged_at.is_(None),
                reference < cutoff,
                or_(
                    (Document.status == DocumentStatus.COMPLETED) & _confirmed(),
                    Document.status == DocumentStatus.FAILED,
                ),
            )
            .limit(BATCH_SIZE)
        )
    ).scalars()

    purged = 0
    now = utc_now()
    for document in expired:
        # documentos antigos podem dividir o arquivo; só apaga quando nenhum outro usa
        shared = await db.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.file_path == document.file_path,
                Document.id != document.id,
                Document.file_purged_at.is_(None),
            )
        )
        if not shared and document.file_path and os.path.exists(document.file_path):
            await asyncio.to_thread(os.remove, document.file_path)
        document.extracted_data = None
        document.file_purged_at = now
        purged += 1

    await db.commit()
    if purged:
        logger.info("documents_purged count=%s retention_days=%s", purged, days)
    return purged
