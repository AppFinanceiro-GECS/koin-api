"""
Backfill de document_id em CreditCardInvoice.

Contexto do bug:
    O fluxo canonico de upload de fatura (POST /transactions/batch-confirm)
    chama InvoiceService.get_or_create_invoice() para cada item do batch.
    Essa funcao nao aceita nem propaga document_id - entao toda fatura
    criada por esse caminho ficou com document_id = NULL, mesmo quando as
    transacoes dela apontam para um Document valido.

    Resultado visivel: a tela de faturas marca esses cartoes como
    "Sem PDF" / "Pendente" apesar do PDF ter sido carregado e processado
    corretamente.

O que este script faz:
    1. Encontra toda CreditCardInvoice com document_id IS NULL
    2. Para cada uma, olha os documentos das transacoes vinculadas
    3. Se todas (ou a maioria) das transacoes apontam para o MESMO document,
       define invoice.document_id = esse document_id
    4. Chama NotificationService.resolve_pending_for_invoice() para dispensar
       as notificacoes "fatura pendente" daquela (card, ref_month, ref_year)

Seguranca:
    - Modo --dry-run e o padrao: nao altera nada, so reporta o que seria feito
    - Usar --execute explicitamente para aplicar
    - Nenhuma transacao e tocada, so o campo document_id da invoice
    - Idempotente: rodar de novo nao faz nada (filtra por IS NULL)

Uso:
    python backend/scripts/backfill_invoice_document_ids.py             # dry-run
    python backend/scripts/backfill_invoice_document_ids.py --execute   # aplica
    python backend/scripts/backfill_invoice_document_ids.py --execute --user-id 1
"""

import argparse
import asyncio
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import CreditCardInvoice
from app.models.document import Document
from app.models.transaction import Transaction
from app.modules.notifications.services.notification_service import (
    NotificationService,
)

# Se X% ou mais das transacoes da invoice apontam pro mesmo document_id,
# consideramos confianca suficiente para vincular. Abaixo disso, reportamos
# como ambiguo (multiplos docs) e pedimos atencao manual.
CONFIDENCE_THRESHOLD = 0.80


async def find_backfill_candidates(
    db: AsyncSession,
    user_id: int | None = None,
) -> list[dict]:
    """
    Retorna lista de faturas elegiveis para backfill.
    Cada item contem: invoice, inferred_document_id, confidence, tx_count.
    """
    query = select(CreditCardInvoice).where(CreditCardInvoice.document_id.is_(None))
    if user_id:
        query = query.where(CreditCardInvoice.user_id == user_id)

    query = query.order_by(
        CreditCardInvoice.user_id,
        CreditCardInvoice.reference_year.desc(),
        CreditCardInvoice.reference_month.desc(),
    )

    result = await db.execute(query)
    invoices = list(result.scalars().all())

    candidates: list[dict] = []

    for invoice in invoices:
        # Buscar transacoes vinculadas que tenham document_id setado
        tx_result = await db.execute(
            select(Transaction.document_id).where(
                Transaction.invoice_id == invoice.id,
                Transaction.document_id.is_not(None),
            )
        )
        document_ids = [row[0] for row in tx_result.all()]

        if not document_ids:
            # Nenhuma transacao tem documento - invoice provavelmente foi
            # criada por outro fluxo (manual, recorrencia, parcela projetada).
            # Nao vincular.
            continue

        # Contar ocorrencias para escolher o document_id dominante
        counter = Counter(document_ids)
        dominant_doc_id, dominant_count = counter.most_common(1)[0]
        confidence = dominant_count / len(document_ids)

        # Contar tambem o total de transacoes da fatura (incluindo sem doc)
        total_tx_result = await db.execute(
            select(Transaction.id).where(Transaction.invoice_id == invoice.id)
        )
        total_tx_count = len(list(total_tx_result.all()))

        candidates.append(
            {
                "invoice": invoice,
                "inferred_document_id": dominant_doc_id,
                "confidence": confidence,
                "tx_with_doc": len(document_ids),
                "tx_total": total_tx_count,
                "unique_docs": len(counter),
                "all_doc_counts": dict(counter),
            }
        )

    return candidates


async def format_candidate_line(db: AsyncSession, candidate: dict) -> str:
    """Formata uma linha de relatorio amigavel para um candidato."""
    invoice: CreditCardInvoice = candidate["invoice"]

    # Buscar nome do cartao
    card_result = await db.execute(
        select(CreditCard).where(CreditCard.id == invoice.credit_card_id)
    )
    card = card_result.scalar_one_or_none()
    card_name = (
        (card.nickname or card.bank_id or f"Cartao#{card.id}")
        if card
        else f"Cartao#{invoice.credit_card_id}"
    )

    # Buscar nome do arquivo do documento
    doc_result = await db.execute(
        select(Document).where(Document.id == candidate["inferred_document_id"])
    )
    doc = doc_result.scalar_one_or_none()
    doc_name = doc.original_filename if doc else f"doc#{candidate['inferred_document_id']}"

    period = f"{invoice.reference_month:02d}/{invoice.reference_year}"
    conf = f"{candidate['confidence'] * 100:.0f}%"

    warn = ""
    if candidate["confidence"] < CONFIDENCE_THRESHOLD:
        warn = f" [AMBIGUO: {candidate['unique_docs']} docs distintos, confianca {conf}]"
    elif candidate["unique_docs"] > 1:
        warn = f" [multiplos docs, dominante={conf}]"

    return (
        f"  invoice#{invoice.id:<6} user#{invoice.user_id} {card_name:<25} "
        f"{period}  tx={candidate['tx_with_doc']}/{candidate['tx_total']}  "
        f"-> doc#{candidate['inferred_document_id']} ({doc_name}){warn}"
    )


async def apply_backfill(
    db: AsyncSession,
    candidate: dict,
    dry_run: bool,
) -> tuple[bool, int]:
    """
    Aplica o backfill para um candidato.
    Retorna (applied, notifications_dismissed).
    """
    invoice: CreditCardInvoice = candidate["invoice"]

    # Pular candidatos com confianca baixa - preferimos deixar passar
    # a arriscar vincular o documento errado
    if candidate["confidence"] < CONFIDENCE_THRESHOLD:
        return (False, 0)

    if dry_run:
        return (True, 0)

    invoice.document_id = candidate["inferred_document_id"]
    await db.flush()

    notification_service = NotificationService(db)
    dismissed = await notification_service.resolve_pending_for_invoice(
        user_id=invoice.user_id,
        credit_card_id=invoice.credit_card_id,
        reference_month=invoice.reference_month,
        reference_year=invoice.reference_year,
    )

    return (True, dismissed)


async def run(user_id: int | None, execute: bool):
    dry_run = not execute

    async with async_session_maker() as db:
        print("=" * 80)
        print("BACKFILL de CreditCardInvoice.document_id")
        print("=" * 80)
        print(f"Modo: {'APLICANDO MUDANCAS' if execute else 'DRY-RUN (nada sera alterado)'}")
        if user_id:
            print(f"Filtrado por user_id={user_id}")
        print("=" * 80)
        print()

        candidates = await find_backfill_candidates(db, user_id)

        if not candidates:
            print("Nenhuma fatura elegivel encontrada. Nada a fazer.")
            return

        print(
            f"Encontradas {len(candidates)} faturas sem document_id com transacoes ligadas a documentos."
        )
        print()

        high_conf = [c for c in candidates if c["confidence"] >= CONFIDENCE_THRESHOLD]
        low_conf = [c for c in candidates if c["confidence"] < CONFIDENCE_THRESHOLD]

        print(f"Alta confianca (>= {int(CONFIDENCE_THRESHOLD * 100)}%): {len(high_conf)}")
        print(f"Baixa confianca (ignoradas): {len(low_conf)}")
        print()

        if high_conf:
            print("--- ALTA CONFIANCA (serao vinculadas) ---")
            for c in high_conf:
                print(await format_candidate_line(db, c))
            print()

        if low_conf:
            print("--- BAIXA CONFIANCA (serao IGNORADAS - revise manualmente) ---")
            for c in low_conf:
                print(await format_candidate_line(db, c))
            print()

        applied_count = 0
        dismissed_total = 0

        for c in high_conf:
            applied, dismissed = await apply_backfill(db, c, dry_run)
            if applied:
                applied_count += 1
                dismissed_total += dismissed

        if execute:
            await db.commit()
            print(f"[OK] {applied_count} faturas atualizadas.")
            print(f"[OK] {dismissed_total} notificacoes 'fatura pendente' dispensadas.")
        else:
            print(f"[DRY-RUN] {applied_count} faturas SERIAM atualizadas.")
            print("[DRY-RUN] Use --execute para aplicar de verdade.")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill document_id em CreditCardInvoice existentes."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Aplica as mudancas. Sem esta flag, roda em dry-run.",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Limita o backfill a um usuario especifico (opcional).",
    )
    args = parser.parse_args()

    asyncio.run(run(user_id=args.user_id, execute=args.execute))


if __name__ == "__main__":
    main()
