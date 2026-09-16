from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app.core.deps import CurrentUser, DbSession
from app.models.credit_card import CreditCard
from app.models.installment import InstallmentSeries
from app.models.transaction import Transaction
from app.modules.transactions.schemas.transaction import (
    BatchConfirmItemResult,
    BatchConfirmRequest,
    BatchConfirmResponse,
    TransactionConfirm,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)
from app.modules.transactions.services.transaction_service import TransactionService

router = APIRouter()


class PaginatedTransactions(BaseModel):
    items: list[TransactionResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


async def enrich_transactions_with_linked_account(db, transactions: list) -> list:
    """Enrich transfer transactions with linked account names"""
    from app.models.account import Account
    from app.models.transaction import Transaction as TransactionModel

    # Get all linked transaction IDs
    linked_ids = [t.linked_transaction_id for t in transactions if t.linked_transaction_id]
    if not linked_ids:
        return transactions

    # Fetch linked transactions with their accounts
    result = await db.execute(
        select(TransactionModel, Account.name)
        .join(Account, TransactionModel.account_id == Account.id)
        .where(TransactionModel.id.in_(linked_ids))
    )
    linked_map = {row[0].id: row[1] for row in result.all()}

    # Enrich original transactions
    for t in transactions:
        if t.linked_transaction_id and t.linked_transaction_id in linked_map:
            t.linked_account_name = linked_map[t.linked_transaction_id]

    return transactions


@router.get("", response_model=PaginatedTransactions)
async def list_transactions(
    current_user: CurrentUser,
    db: DbSession,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    category_id: int | None = Query(None),
    account_id: int | None = Query(None),
    type: str | None = Query(None),
    search: str | None = Query(None, min_length=2, max_length=100),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
):
    """Lista transacoes com filtros, busca e paginacao"""
    service = TransactionService(db)

    items = await service.list(
        current_user,
        start_date=start_date,
        end_date=end_date,
        category_id=category_id,
        account_id=account_id,
        transaction_type=type,
        search=search,
        limit=limit,
        offset=offset,
    )

    # Enrich transfer transactions with linked account names
    items = await enrich_transactions_with_linked_account(db, items)

    total = await service.count(
        current_user,
        start_date=start_date,
        end_date=end_date,
        category_id=category_id,
        account_id=account_id,
        transaction_type=type,
        search=search,
    )

    return PaginatedTransactions(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get("/export/csv")
async def export_transactions_csv(
    current_user: CurrentUser,
    db: DbSession,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    category_id: int | None = Query(None),
    account_id: int | None = Query(None),
):
    """Exporta transacoes em formato CSV"""
    service = TransactionService(db)
    transactions = await service.list(
        current_user,
        start_date=start_date,
        end_date=end_date,
        category_id=category_id,
        account_id=account_id,
        limit=10000,  # Higher limit for exports
        offset=0,
    )

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(
        [
            "Data",
            "Tipo",
            "Descricao",
            "Categoria",
            "Conta",
            "Valor",
            "Estabelecimento",
            "Parcela",
        ]
    )

    # Data rows
    for t in transactions:
        tipo_map = {"income": "Receita", "expense": "Despesa", "transfer": "Transferência"}
        tipo = tipo_map.get(t.type, t.type)
        valor = f"{t.amount:.2f}"
        parcela = f"{t.installment_number}/{t.installment_total}" if t.installment_total else ""
        writer.writerow(
            [
                t.date.strftime("%d/%m/%Y"),
                tipo,
                t.description or "",
                t.category_name or "Sem categoria",
                t.account_name or "",
                valor,
                t.merchant_name or "",
                parcela,
            ]
        )

    output.seek(0)
    filename = f"transacoes_{date.today().strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8",
        },
    )


@router.post("", response_model=TransactionResponse, status_code=201)
async def create_transaction(
    data: TransactionCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria uma transacao manual"""
    service = TransactionService(db)
    transaction = await service.create(current_user, data)
    await db.commit()  # ← COMMIT para persistir mudanças na fatura!
    return transaction


class ConfirmTransactionResponse(TransactionResponse):
    """Resposta de confirmacao com dados de parcelas"""

    series_id: int | None = None
    series_description: str | None = None
    additional_transactions_count: int = 0


@router.post("/confirm", response_model=ConfirmTransactionResponse, status_code=201)
async def confirm_transaction(
    data: TransactionConfirm,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Confirma transacao a partir de documento processado (1 toque).

    Para parcelas, pode:
    - Criar nova serie de parcelas automaticamente
    - Vincular a serie existente
    - Marcar parcelas anteriores como pagas
    - Criar parcelas futuras
    """
    service = TransactionService(db)
    result = await service.confirm_from_document(current_user, data)
    await db.commit()  # ← COMMIT para persistir mudanças na fatura!

    transaction = result["transaction"]
    series = result.get("series")
    additional = result.get("created_transactions", [])

    response = ConfirmTransactionResponse(
        id=transaction.id,
        type=transaction.type,
        amount=float(transaction.amount),
        currency=transaction.currency,
        date=transaction.date,
        description=transaction.description,
        notes=transaction.notes,
        tags=transaction.tags,
        is_fixed=transaction.is_fixed,
        account_id=transaction.account_id,
        category_id=transaction.category_id,
        merchant_id=transaction.merchant_id,
        document_id=transaction.document_id,
        is_recurring=transaction.is_recurring,
        is_paid=transaction.is_paid,
        installment_series_id=transaction.installment_series_id,
        installment_number=transaction.installment_number,
        installment_total=transaction.installment_total,
        created_at=transaction.created_at,
        updated_at=transaction.updated_at,
        series_id=series.id if series else None,
        series_description=series.description if series else None,
        additional_transactions_count=len(additional),
    )

    return response


@router.post("/batch-confirm", response_model=BatchConfirmResponse, status_code=201)
async def batch_confirm_transactions(
    data: BatchConfirmRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Confirma múltiplas transações de uma vez a partir de documento processado.

    Processa todos os itens e retorna resultado individual para cada um,
    incluindo quais foram sucesso, quais são duplicados e quais tiveram erro.

    Se card_closing_day e card_due_day forem fornecidos (extraidos do PDF),
    atualiza automaticamente o cartao de credito com esses valores.
    """
    service = TransactionService(db)

    # Atualizar cartao de credito com closing_day e due_day do PDF (se fornecidos)
    if data.card_closing_day or data.card_due_day:
        # Pegar o credit_card_id do primeiro item que tiver
        credit_card_id = None
        for item in data.items:
            if item.credit_card_id:
                credit_card_id = item.credit_card_id
                break

        if credit_card_id:
            # Buscar e atualizar o cartao
            card_result = await db.execute(
                select(CreditCard).where(
                    CreditCard.id == credit_card_id,
                    CreditCard.user_id == current_user.id,
                )
            )
            credit_card = card_result.scalar_one_or_none()

            if credit_card:
                updated = False
                if data.card_closing_day and 1 <= data.card_closing_day <= 31:
                    if credit_card.closing_day != data.card_closing_day:
                        print(
                            f"[BATCH_CONFIRM] Atualizando closing_day do cartao {credit_card_id}: "
                            f"{credit_card.closing_day} -> {data.card_closing_day}"
                        )
                        credit_card.closing_day = data.card_closing_day
                        updated = True

                if data.card_due_day and 1 <= data.card_due_day <= 31:
                    if credit_card.due_day != data.card_due_day:
                        print(
                            f"[BATCH_CONFIRM] Atualizando due_day do cartao {credit_card_id}: "
                            f"{credit_card.due_day} -> {data.card_due_day}"
                        )
                        credit_card.due_day = data.card_due_day
                        updated = True

                if updated:
                    await db.flush()

    results: list[BatchConfirmItemResult] = []
    success_count = 0
    duplicate_count = 0
    error_count = 0

    for index, item in enumerate(data.items):
        try:
            # Converter BatchConfirmItem para TransactionConfirm
            confirm_data = TransactionConfirm(
                document_id=item.document_id,
                account_id=item.account_id,
                amount=item.amount,
                date=item.date,
                category_id=item.category_id,
                merchant_name=item.merchant_name,
                description=item.description,
                tags=item.tags,
                is_fixed=item.is_fixed,
                ownership_type=item.ownership_type,
                payment_method=item.payment_method,
                credit_card_id=item.credit_card_id,
                income_source_id=item.income_source_id,
                extracted_transaction_type=item.extracted_transaction_type,
                invoice_month=item.invoice_month,
                invoice_year=item.invoice_year,
                is_installment=item.is_installment,
                installment_current=item.installment_current,
                installment_total=item.installment_total,
                installment_series_id=item.installment_series_id,
                mark_previous_as_paid=item.mark_previous_as_paid,
                create_future_installments=item.create_future_installments,
                force_duplicate=item.force_duplicate,
                # Campos para cupom fiscal (grocery tracking)
                quantity=item.quantity,
                unit=item.unit,
                unit_price=item.unit_price,
                grocery_category=item.grocery_category,
                necessity_type=item.necessity_type,
            )

            result = await service.confirm_from_document(current_user, confirm_data)
            transaction = result["transaction"]

            results.append(
                BatchConfirmItemResult(
                    index=index,
                    success=True,
                    transaction_id=transaction.id,
                )
            )
            success_count += 1

        except HTTPException as e:
            is_duplicate = e.status_code == 409
            results.append(
                BatchConfirmItemResult(
                    index=index,
                    success=False,
                    error=e.detail if isinstance(e.detail, str) else str(e.detail),
                    is_duplicate=is_duplicate,
                )
            )
            if is_duplicate:
                duplicate_count += 1
            else:
                error_count += 1

        except Exception as e:
            results.append(
                BatchConfirmItemResult(
                    index=index,
                    success=False,
                    error=str(e),
                )
            )
            error_count += 1

    # Limpar transações projetadas das faturas que receberam transações reais do PDF.
    # O PDF é a fonte de verdade — projetadas que sobraram são duplicatas.
    if success_count > 0:
        # Coletar invoice_ids das transações criadas com sucesso
        confirmed_invoice_ids: set[int] = set()
        for r in results:
            if r.success and r.transaction_id:
                tx_result = await db.execute(
                    select(Transaction.invoice_id).where(Transaction.id == r.transaction_id)
                )
                inv_id = tx_result.scalar_one_or_none()
                if inv_id:
                    confirmed_invoice_ids.add(inv_id)

        for invoice_id in confirmed_invoice_ids:
            # Buscar projetadas que sobraram nesta fatura
            projected_result = await db.execute(
                select(Transaction).where(
                    Transaction.invoice_id == invoice_id,
                    Transaction.is_paid == False,
                )
            )
            projected_txs = projected_result.scalars().all()

            if projected_txs:
                print(
                    f"[BATCH_CONFIRM] Removendo {len(projected_txs)} transações projetadas "
                    f"da fatura {invoice_id} (PDF é fonte de verdade)"
                )

                # Ajustar installment_series: decrementar contadores
                series_to_update: dict[int, int] = {}  # series_id -> count to decrement
                for tx in projected_txs:
                    if tx.installment_series_id:
                        series_to_update[tx.installment_series_id] = (
                            series_to_update.get(tx.installment_series_id, 0) + 1
                        )

                # Deletar as projetadas
                await db.execute(
                    delete(Transaction).where(
                        Transaction.invoice_id == invoice_id,
                        Transaction.is_paid == False,
                    )
                )

                # Recalcular paid_count das séries afetadas (count real de is_paid=True)
                for series_id in series_to_update:
                    paid_count_result = await db.execute(
                        select(func.count()).where(
                            Transaction.installment_series_id == series_id,
                            Transaction.is_paid == True,
                        )
                    )
                    actual_paid = paid_count_result.scalar() or 0
                    await db.execute(
                        InstallmentSeries.__table__.update()
                        .where(InstallmentSeries.id == series_id)
                        .values(paid_count=actual_paid)
                    )
                    print(
                        f"[BATCH_CONFIRM] Série {series_id}: paid_count atualizado para {actual_paid}"
                    )

                await db.flush()

                # Recalcular total da fatura
                from app.models.credit_card_invoice import CreditCardInvoice
                from app.modules.credit_cards.services.invoice_service import InvoiceService

                invoice_result = await db.execute(
                    select(CreditCardInvoice).where(CreditCardInvoice.id == invoice_id)
                )
                invoice = invoice_result.scalar_one_or_none()
                if invoice:
                    invoice_service = InvoiceService(db)
                    await invoice_service.update_invoice_total(invoice, force_recalculate=True)
                    print(
                        f"[BATCH_CONFIRM] Fatura {invoice_id}: total recalculado para {invoice.total_amount}"
                    )

    await db.commit()  # ← COMMIT para persistir todas as mudanças nas faturas!

    return BatchConfirmResponse(
        total=len(data.items),
        success_count=success_count,
        duplicate_count=duplicate_count,
        error_count=error_count,
        results=results,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna uma transacao especifica"""
    service = TransactionService(db)
    transaction = await service.get_by_id(current_user, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacao nao encontrada")
    return transaction


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: int,
    data: TransactionUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza uma transacao"""
    service = TransactionService(db)
    transaction = await service.update(current_user, transaction_id, data)
    await db.commit()  # ← COMMIT para persistir mudanças na fatura!
    return transaction


class DeleteTransactionResponse(BaseModel):
    message: str
    transactions_deleted: int
    invoices_deleted: int = 0
    series_deleted: bool = False


@router.delete("/{transaction_id}", response_model=DeleteTransactionResponse)
async def delete_transaction(
    transaction_id: int,
    current_user: CurrentUser,
    db: DbSession,
    delete_series: bool = Query(
        True, description="Se True e a transacao for parcelada, deleta toda a serie de parcelas"
    ),
):
    """
    Remove uma transacao.

    Se a transacao faz parte de uma serie de parcelas e delete_series=True,
    deleta todas as parcelas da serie e limpa faturas que ficarem vazias.
    """
    service = TransactionService(db)
    result = await service.delete(current_user, transaction_id, delete_series=delete_series)
    await db.commit()

    if result["series_deleted"]:
        message = (
            f"Serie de parcelas removida. {result['transactions_deleted']} transacoes deletadas."
        )
        if result["invoices_deleted"] > 0:
            message += f" {result['invoices_deleted']} faturas vazias removidas."
    else:
        message = "Transacao removida."

    return DeleteTransactionResponse(
        message=message,
        transactions_deleted=result["transactions_deleted"],
        invoices_deleted=result["invoices_deleted"],
        series_deleted=result["series_deleted"],
    )


class ExtractedItemCheck(BaseModel):
    """Item extraido para verificar se existe projecao"""

    index: int
    description: str
    amount: float
    date: str | None = None  # Data como string YYYY-MM-DD
    is_installment: bool = False
    installment_current: int | None = None
    installment_total: int | None = None


class PotentialDuplicateSeries(BaseModel):
    """Informações sobre uma série potencialmente duplicada"""

    series_id: int
    description: str
    merchant_name: str
    installment_count: int
    installment_amount: float
    paid_count: int
    similarity_score: float
    first_installment_date: date


class ProjectedMatchResult(BaseModel):
    """Resultado da verificacao de match com projecao"""

    index: int
    has_projected: bool
    projected_transaction_id: int | None = None
    projected_date: date | None = None
    series_id: int | None = None
    series_description: str | None = None
    message: str | None = None
    potential_duplicate_series: PotentialDuplicateSeries | None = None


class CheckProjectedRequest(BaseModel):
    """Request para verificar projecoes"""

    items: list[ExtractedItemCheck]
    credit_card_id: int | None = None
    invoice_month: int | None = None
    invoice_year: int | None = None


class CheckProjectedResponse(BaseModel):
    """Response com resultados das verificacoes"""

    results: list[ProjectedMatchResult]
    total_projected: int


@router.post("/check-projected", response_model=CheckProjectedResponse)
async def check_projected_transactions(
    data: CheckProjectedRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Verifica quais itens extraidos tem parcelas/transacoes projetadas.

    Usado pelo frontend para mostrar ao usuario quais itens ja existem
    como projecoes futuras e serao confirmados ao inves de criados.
    """
    from app.modules.installments.services.installment_service import InstallmentService

    installment_service = InstallmentService(db)
    results = []
    total_projected = 0

    for item in data.items:
        result = ProjectedMatchResult(
            index=item.index,
            has_projected=False,
        )

        if item.is_installment and item.installment_current and item.installment_total:
            # Para itens parcelados, buscar serie existente
            # Converter date string para date object
            from datetime import datetime as dt

            transaction_date = None
            if item.date:
                try:
                    transaction_date = dt.strptime(item.date, "%Y-%m-%d").date()
                except ValueError:
                    pass

            series = await installment_service.find_matching_series(
                user=current_user,
                merchant_name=item.description,
                installment_amount=item.amount,
                installment_total=item.installment_total,
                account_id=None,  # Nao temos account_id aqui
                transaction_date=transaction_date,
                installment_number=item.installment_current,
            )

            if series:
                # Verificar se existe parcela projetada
                existing = await installment_service.find_existing_installment(
                    series, item.installment_current
                )

                if existing and not existing.is_paid:
                    result.has_projected = True
                    result.projected_transaction_id = existing.id
                    result.projected_date = existing.date
                    result.series_id = series.id
                    result.series_description = series.description
                    result.message = f"Parcela {item.installment_current}/{item.installment_total} ja projetada para {existing.date.strftime('%d/%m/%Y')}"
                    total_projected += 1
                elif existing and existing.is_paid:
                    result.message = f"Parcela {item.installment_current}/{item.installment_total} ja confirmada em {existing.date.strftime('%d/%m/%Y')}"

            # Se não tem projeção, verificar se há duplicata potencial
            if not result.has_projected:
                potential_dup = await installment_service.find_potential_duplicate(
                    user=current_user,
                    merchant_name=item.description,
                    installment_amount=item.amount,
                    installment_total=item.installment_total,
                    credit_card_id=data.credit_card_id,
                )

                if potential_dup:
                    series, similarity_score = potential_dup
                    result.potential_duplicate_series = PotentialDuplicateSeries(
                        series_id=series.id,
                        description=series.description,
                        merchant_name=series.merchant_name,
                        installment_count=series.installment_count,
                        installment_amount=float(series.installment_amount),
                        paid_count=series.paid_count,
                        similarity_score=similarity_score,
                        first_installment_date=series.first_installment_date,
                    )

        results.append(result)

    return CheckProjectedResponse(
        results=results,
        total_projected=total_projected,
    )
