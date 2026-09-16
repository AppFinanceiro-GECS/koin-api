from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased

from app.core.deps import CurrentUser, DbSession
from app.models.account import Account, AccountType
from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import CreditCardInvoice, InvoiceStatus
from app.models.document import Document
from app.models.transaction import Transaction
from app.modules.credit_cards.schemas.invoice import (
    CardDetectionResult,
    DetectedCardInfo,
    InvoiceCreate,
    InvoiceDetailResponse,
    InvoiceFromDocument,
    InvoicePayment,
    InvoiceResponse,
    InvoiceSummary,
    InvoiceTransactionResponse,
    InvoiceUpdate,
)
from app.modules.credit_cards.services.expected_invoice_service import (
    ExpectedInvoiceService,
)
from app.modules.credit_cards.services.invoice_service import InvoiceService

router = APIRouter()


def build_invoice_response(
    invoice: CreditCardInvoice,
    credit_card_name: str | None = None,
    payment_account_name: str | None = None,
    transaction_count: int = 0,
) -> InvoiceResponse:
    """Helper para construir resposta de fatura"""
    return InvoiceResponse(
        id=invoice.id,
        user_id=invoice.user_id,
        credit_card_id=invoice.credit_card_id,
        document_id=invoice.document_id,
        reference_month=invoice.reference_month,
        reference_year=invoice.reference_year,
        closing_date=invoice.closing_date,
        due_date=invoice.due_date,
        total_amount=float(invoice.total_amount),
        minimum_payment=float(invoice.minimum_payment) if invoice.minimum_payment else None,
        paid_amount=float(invoice.paid_amount),
        remaining_amount=float(invoice.remaining_amount),
        status=invoice.status,
        paid_at=invoice.paid_at,
        payment_account_id=invoice.payment_account_id,
        payment_transaction_id=invoice.payment_transaction_id,
        payment_transaction_ids=invoice.payment_transaction_ids,
        notes=invoice.notes,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        credit_card_name=credit_card_name,
        payment_account_name=payment_account_name,
        period_display=invoice.period_display,
        transaction_count=transaction_count,
    )


@router.get("", response_model=list[InvoiceResponse])
async def list_invoices(
    current_user: CurrentUser,
    db: DbSession,
    credit_card_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    year: int | None = None,
    month: int | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
):
    """Lista faturas do usuario"""
    from app.modules.household.utils.household_helpers import (
        get_household_member,
        get_household_user_ids,
    )

    service = InvoiceService(db)

    # Lazy update: atualiza status das faturas baseado em datas
    await service.update_invoice_statuses()

    # Get household user IDs for filtering
    household_user_ids = await get_household_user_ids(db, current_user)
    member = await get_household_member(db, current_user)

    # Aliases para os JOINs
    CardAccount = aliased(Account)
    PaymentAccount = aliased(Account)

    # Subquery para contar transacoes
    tx_count_subq = (
        select(Transaction.invoice_id, func.count(Transaction.id).label("tx_count"))
        .where(Transaction.user_id == current_user.id)
        .group_by(Transaction.invoice_id)
        .subquery()
    )

    # Query otimizada com JOINs
    query = (
        select(
            CreditCardInvoice,
            CardAccount.name.label("credit_card_name"),
            PaymentAccount.name.label("payment_account_name"),
            func.coalesce(tx_count_subq.c.tx_count, 0).label("transaction_count"),
        )
        .join(CreditCard, CreditCard.id == CreditCardInvoice.credit_card_id)
        .join(CardAccount, CardAccount.id == CreditCard.account_id)
        .outerjoin(PaymentAccount, PaymentAccount.id == CreditCardInvoice.payment_account_id)
        .outerjoin(tx_count_subq, tx_count_subq.c.invoice_id == CreditCardInvoice.id)
    )

    # Apply household filter based on Account ownership
    if member and member.can_see_all:
        # Can see all household invoices
        query = query.where(CreditCardInvoice.user_id.in_(household_user_ids))
    elif household_user_ids:
        # See personal invoices + household invoices from family
        query = query.where(
            or_(
                and_(
                    CreditCardInvoice.user_id == current_user.id,
                    CardAccount.ownership_type == "personal",
                ),
                and_(
                    CreditCardInvoice.user_id.in_(household_user_ids),
                    CardAccount.ownership_type == "household",
                ),
            )
        )
    else:
        # No household - only user's own invoices
        query = query.where(CreditCardInvoice.user_id == current_user.id)

    # Aplicar filtros
    if credit_card_id:
        query = query.where(CreditCardInvoice.credit_card_id == credit_card_id)
    if status_filter:
        query = query.where(CreditCardInvoice.status == status_filter)
    if year:
        query = query.where(CreditCardInvoice.reference_year == year)
    if month:
        query = query.where(CreditCardInvoice.reference_month == month)

    # Ordenar e paginar
    query = (
        query.order_by(
            CreditCardInvoice.reference_year.desc(),
            CreditCardInvoice.reference_month.desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    rows = result.all()

    # Construir respostas
    responses = []
    for row in rows:
        invoice = row[0]
        responses.append(
            build_invoice_response(
                invoice,
                credit_card_name=row.credit_card_name,
                payment_account_name=row.payment_account_name,
                transaction_count=row.transaction_count,
            )
        )

    return responses


class ExpectedInvoiceItem(BaseModel):
    """Item retornado pelo endpoint /overview - pode ser materializado ou fantasma."""

    credit_card_id: int
    credit_card_name: str
    reference_month: int
    reference_year: int
    closing_date: date
    due_date: date
    state: str  # not_created | created_no_document | created_with_document | paid | future
    is_pending: bool
    is_phantom: bool
    # Somente quando materializada:
    invoice_id: int | None = None
    document_id: int | None = None
    total_amount: float | None = None
    paid_amount: float | None = None
    status: str | None = None


class InvoiceOverviewResponse(BaseModel):
    """Resposta do endpoint overview: lista unificada + resumo."""

    reference_month: int
    reference_year: int
    items: list[ExpectedInvoiceItem]
    total_cards: int
    pending_count: int  # quantos estao em estado not_created ou created_no_document


@router.get("/overview", response_model=InvoiceOverviewResponse)
async def invoices_overview(
    current_user: CurrentUser,
    db: DbSession,
    year: int = Query(..., description="Ano de referencia"),
    month: int = Query(..., ge=1, le=12, description="Mes de referencia (1-12)"),
):
    """
    Retorna a visao unificada de faturas para um mes: materializadas + fantasmas.

    Uma "fatura fantasma" representa um cartao cujo periodo de cobranca ja fechou
    mas para o qual ainda nao existe nenhum CreditCardInvoice - ou seja, o usuario
    esqueceu de carregar. O frontend usa isso para mostrar "placeholders" com CTA.
    """
    service = ExpectedInvoiceService(db)
    dtos = await service.get_overview(current_user, year, month)

    items = [
        ExpectedInvoiceItem(
            credit_card_id=dto.credit_card_id,
            credit_card_name=dto.credit_card_name,
            reference_month=dto.reference_month,
            reference_year=dto.reference_year,
            closing_date=dto.closing_date,
            due_date=dto.due_date,
            state=dto.state.value,
            is_pending=dto.is_pending,
            is_phantom=dto.is_phantom,
            invoice_id=dto.invoice_id,
            document_id=dto.document_id,
            total_amount=float(dto.total_amount) if dto.total_amount is not None else None,
            paid_amount=float(dto.paid_amount) if dto.paid_amount is not None else None,
            status=dto.status,
        )
        for dto in dtos
    ]

    pending_count = sum(1 for item in items if item.is_pending)

    return InvoiceOverviewResponse(
        reference_month=month,
        reference_year=year,
        items=items,
        total_cards=len(items),
        pending_count=pending_count,
    )


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice(
    invoice_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna detalhes de uma fatura com suas transacoes"""
    from app.models.category import Category
    from app.models.merchant import Merchant
    from app.modules.household.utils.household_helpers import (
        get_household_member,
        get_household_user_ids,
    )

    # Get household user IDs for filtering
    household_user_ids = await get_household_user_ids(db, current_user)
    member = await get_household_member(db, current_user)

    # Aliases para os JOINs
    CardAccount = aliased(Account)
    PaymentAccount = aliased(Account)

    # Query otimizada para fatura com nomes
    invoice_query = (
        select(
            CreditCardInvoice,
            CardAccount.name.label("credit_card_name"),
            PaymentAccount.name.label("payment_account_name"),
        )
        .join(CreditCard, CreditCard.id == CreditCardInvoice.credit_card_id)
        .join(CardAccount, CardAccount.id == CreditCard.account_id)
        .outerjoin(PaymentAccount, PaymentAccount.id == CreditCardInvoice.payment_account_id)
        .where(CreditCardInvoice.id == invoice_id)
    )

    # Apply household filter based on Account ownership
    if member and member.can_see_all:
        # Can see all household invoices
        invoice_query = invoice_query.where(CreditCardInvoice.user_id.in_(household_user_ids))
    elif household_user_ids:
        # See personal invoices + household invoices from family
        invoice_query = invoice_query.where(
            or_(
                and_(
                    CreditCardInvoice.user_id == current_user.id,
                    CardAccount.ownership_type == "personal",
                ),
                and_(
                    CreditCardInvoice.user_id.in_(household_user_ids),
                    CardAccount.ownership_type == "household",
                ),
            )
        )
    else:
        # No household - only user's own invoices
        invoice_query = invoice_query.where(CreditCardInvoice.user_id == current_user.id)

    result = await db.execute(invoice_query)
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fatura nao encontrada",
        )

    invoice = row[0]
    credit_card_name = row.credit_card_name
    payment_account_name = row.payment_account_name

    # Query otimizada para transacoes com JOINs
    tx_query = (
        select(
            Transaction,
            Merchant.name.label("merchant_name"),
            Category.name.label("category_name"),
        )
        .outerjoin(Merchant, Merchant.id == Transaction.merchant_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(Transaction.invoice_id == invoice_id)
        .order_by(Transaction.date.desc())
    )

    tx_result = await db.execute(tx_query)
    tx_rows = tx_result.all()

    transaction_responses = []
    for tx_row in tx_rows:
        t = tx_row[0]
        # Aplicar sinal correto: income/creditos sao negativos na fatura
        # (pagamentos, estornos, cashback reduzem o valor a pagar)
        amount = float(t.amount)
        if t.type == "income":
            amount = -amount

        transaction_responses.append(
            InvoiceTransactionResponse(
                id=t.id,
                date=t.date,
                description=t.description,
                merchant_name=tx_row.merchant_name,
                category_name=tx_row.category_name,
                amount=amount,
                installment_number=t.installment_number,
                installment_total=t.installment_total,
                is_paid=t.is_paid,
            )
        )

    return InvoiceDetailResponse(
        id=invoice.id,
        user_id=invoice.user_id,
        credit_card_id=invoice.credit_card_id,
        document_id=invoice.document_id,
        reference_month=invoice.reference_month,
        reference_year=invoice.reference_year,
        closing_date=invoice.closing_date,
        due_date=invoice.due_date,
        total_amount=float(invoice.total_amount),
        minimum_payment=float(invoice.minimum_payment) if invoice.minimum_payment else None,
        paid_amount=float(invoice.paid_amount),
        remaining_amount=float(invoice.remaining_amount),
        status=invoice.status,
        paid_at=invoice.paid_at,
        payment_account_id=invoice.payment_account_id,
        payment_transaction_id=invoice.payment_transaction_id,
        notes=invoice.notes,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        credit_card_name=credit_card_name,
        payment_account_name=payment_account_name,
        period_display=invoice.period_display,
        transaction_count=len(transaction_responses),
        transactions=transaction_responses,
    )


@router.post("", response_model=InvoiceResponse, status_code=201)
async def create_invoice(
    data: InvoiceCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria uma nova fatura manualmente"""
    # Validar cartao
    card_result = await db.execute(
        select(CreditCard).where(
            CreditCard.id == data.credit_card_id,
            CreditCard.user_id == current_user.id,
        )
    )
    credit_card = card_result.scalar_one_or_none()

    if not credit_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cartao nao encontrado",
        )

    service = InvoiceService(db)

    # Verificar se ja existe fatura para o periodo
    existing = await db.execute(
        select(CreditCardInvoice).where(
            CreditCardInvoice.credit_card_id == data.credit_card_id,
            CreditCardInvoice.reference_month == data.reference_month,
            CreditCardInvoice.reference_year == data.reference_year,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ja existe fatura para {data.reference_month}/{data.reference_year}",
        )

    invoice = await service.get_or_create_invoice(
        user=current_user,
        credit_card=credit_card,
        reference_month=data.reference_month,
        reference_year=data.reference_year,
        closing_date=data.closing_date,
        due_date=data.due_date,
    )

    if data.total_amount:
        invoice.total_amount = Decimal(str(data.total_amount))

    if data.notes:
        invoice.notes = data.notes

    await db.commit()
    await db.refresh(invoice)

    # Buscar nome do cartao
    account_result = await db.execute(
        select(Account.name).where(Account.id == credit_card.account_id)
    )
    credit_card_name = account_result.scalar_one_or_none()

    return build_invoice_response(invoice, credit_card_name=credit_card_name)


@router.post("/from-document", response_model=InvoiceResponse, status_code=201)
async def create_invoice_from_document(
    data: InvoiceFromDocument,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria uma fatura a partir de um documento PDF"""
    # Validar documento
    doc_result = await db.execute(
        select(Document).where(
            Document.id == data.document_id,
            Document.user_id == current_user.id,
        )
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento nao encontrado",
        )

    # Validar cartao
    card_result = await db.execute(
        select(CreditCard).where(
            CreditCard.id == data.credit_card_id,
            CreditCard.user_id == current_user.id,
        )
    )
    credit_card = card_result.scalar_one_or_none()

    if not credit_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cartao nao encontrado",
        )

    service = InvoiceService(db)

    invoice = await service.create_invoice_from_document(
        user=current_user,
        document=document,
        credit_card=credit_card,
        reference_month=data.reference_month,
        reference_year=data.reference_year,
        total_amount=Decimal(str(data.total_amount)) if data.total_amount else None,
    )

    await db.commit()
    await db.refresh(invoice)

    # Buscar nome do cartao
    account_result = await db.execute(
        select(Account.name).where(Account.id == credit_card.account_id)
    )
    credit_card_name = account_result.scalar_one_or_none()

    return build_invoice_response(invoice, credit_card_name=credit_card_name)


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: int,
    data: InvoiceUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza uma fatura"""
    service = InvoiceService(db)
    invoice = await service.get_invoice_by_id(current_user, invoice_id)

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fatura nao encontrada",
        )

    update_data = data.model_dump(exclude_unset=True)

    if "notes" in update_data:
        invoice.notes = update_data["notes"]

    if "status" in update_data:
        # Validar status
        valid_statuses = [s.value for s in InvoiceStatus]
        if update_data["status"] not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Status invalido. Valores validos: {valid_statuses}",
            )
        invoice.status = update_data["status"]

    if "minimum_payment" in update_data:
        invoice.minimum_payment = Decimal(str(update_data["minimum_payment"]))

    await db.commit()
    await db.refresh(invoice)

    # Buscar nome do cartao
    card_result = await db.execute(
        select(Account.name)
        .join(CreditCard, CreditCard.account_id == Account.id)
        .where(CreditCard.id == invoice.credit_card_id)
    )
    credit_card_name = card_result.scalar_one_or_none()

    return build_invoice_response(invoice, credit_card_name=credit_card_name)


class DeleteInvoiceResponse(BaseModel):
    message: str
    transactions_deleted: int
    invoices_deleted: int = 1
    series_deleted: int = 0


@router.delete("/{invoice_id}", response_model=DeleteInvoiceResponse)
async def delete_invoice(
    invoice_id: int,
    current_user: CurrentUser,
    db: DbSession,
    delete_transactions: bool = Query(
        False, description="Se True, deleta as transacoes vinculadas. Se False, apenas desvincula."
    ),
):
    """
    Exclui uma fatura.

    - Se delete_transactions=False (padrao): apenas desvincula as transacoes
    - Se delete_transactions=True: deleta a fatura E todas as transacoes vinculadas.
      Se houver transacoes parceladas, deleta toda a serie de parcelas e
      limpa faturas que ficarem vazias.
    """
    service = InvoiceService(db)
    result = await service.delete_invoice(
        current_user,
        invoice_id,
        delete_transactions=delete_transactions,
    )
    await db.commit()

    if delete_transactions:
        parts = [f"{result['transactions_deleted']} transacoes deletadas"]
        if result["series_deleted"] > 0:
            parts.append(f"{result['series_deleted']} series de parcelas removidas")
        if result["invoices_deleted"] > 1:
            parts.append(f"{result['invoices_deleted']} faturas removidas (incluindo vazias)")
        message = f"Fatura excluida. {', '.join(parts)}."
    else:
        message = f"Fatura excluida. {result['transactions_unlinked']} transacoes desvinculadas."

    return DeleteInvoiceResponse(
        message=message,
        transactions_deleted=result["transactions_deleted"],
        invoices_deleted=result["invoices_deleted"],
        series_deleted=result["series_deleted"],
    )


@router.post("/{invoice_id}/pay", response_model=InvoiceResponse)
async def pay_invoice(
    invoice_id: int,
    data: InvoicePayment,
    current_user: CurrentUser,
    db: DbSession,
):
    """Registra pagamento de uma fatura"""
    service = InvoiceService(db)
    invoice = await service.get_invoice_by_id(current_user, invoice_id)

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fatura nao encontrada",
        )

    if invoice.status == InvoiceStatus.PAID.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fatura ja esta paga",
        )

    await service.pay_invoice(
        user=current_user,
        invoice=invoice,
        amount=Decimal(str(data.amount)),
        payment_account_id=data.payment_account_id,
        payment_date=data.payment_date,
        payment_method=data.payment_method.value if data.payment_method else None,
    )

    await db.commit()
    await db.refresh(invoice)

    # Buscar nomes
    card_result = await db.execute(
        select(Account.name)
        .join(CreditCard, CreditCard.account_id == Account.id)
        .where(CreditCard.id == invoice.credit_card_id)
    )
    credit_card_name = card_result.scalar_one_or_none()

    pay_result = await db.execute(select(Account.name).where(Account.id == data.payment_account_id))
    payment_account_name = pay_result.scalar_one_or_none()

    return build_invoice_response(
        invoice,
        credit_card_name=credit_card_name,
        payment_account_name=payment_account_name,
    )


@router.get("/credit-card/{card_id}", response_model=list[InvoiceResponse])
async def list_card_invoices(
    card_id: int,
    current_user: CurrentUser,
    db: DbSession,
    year: int | None = None,
    limit: int = Query(12, le=50),
):
    """Lista faturas de um cartao especifico"""
    # Validar cartao
    card_result = await db.execute(
        select(CreditCard).where(
            CreditCard.id == card_id,
            CreditCard.user_id == current_user.id,
        )
    )
    if not card_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cartao nao encontrado",
        )

    service = InvoiceService(db)
    invoices = await service.list_invoices(
        user=current_user,
        credit_card_id=card_id,
        year=year,
        limit=limit,
    )

    if not invoices:
        return []

    # Buscar nome do cartao uma vez
    account_result = await db.execute(
        select(Account.name)
        .join(CreditCard, CreditCard.account_id == Account.id)
        .where(CreditCard.id == card_id)
    )
    credit_card_name = account_result.scalar_one_or_none()

    # Buscar contagem de transacoes para todas as faturas de uma vez
    invoice_ids = [inv.id for inv in invoices]
    count_result = await db.execute(
        select(Transaction.invoice_id, func.count(Transaction.id).label("count"))
        .where(Transaction.invoice_id.in_(invoice_ids))
        .group_by(Transaction.invoice_id)
    )
    tx_counts = {row[0]: row[1] for row in count_result.all()}

    responses = []
    for invoice in invoices:
        responses.append(
            build_invoice_response(
                invoice,
                credit_card_name=credit_card_name,
                transaction_count=tx_counts.get(invoice.id, 0),
            )
        )

    return responses


@router.get("/credit-card/{card_id}/current", response_model=InvoiceSummary)
async def get_card_current_invoice(
    card_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna resumo da fatura atual de um cartao"""
    # Validar cartao
    card_result = await db.execute(
        select(CreditCard).where(
            CreditCard.id == card_id,
            CreditCard.user_id == current_user.id,
        )
    )
    credit_card = card_result.scalar_one_or_none()

    if not credit_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cartao nao encontrado",
        )

    service = InvoiceService(db)
    invoice = await service.get_card_current_invoice(current_user, credit_card)

    # Se nao tem fatura, calcular periodo atual
    today = date.today()
    period = service.calculate_invoice_period(credit_card, today)

    if not invoice:
        return InvoiceSummary(
            invoice_id=None,
            reference_month=period["reference_month"],
            reference_year=period["reference_year"],
            period_display=f"{['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'][period['reference_month'] - 1]}/{period['reference_year']}",
            total_amount=0,
            paid_amount=0,
            remaining_amount=0,
            status=InvoiceStatus.OPEN.value,
            due_date=period["due_date"],
            days_until_due=(period["due_date"] - today).days,
            transaction_count=0,
        )

    # Contar transacoes
    count_result = await db.execute(
        select(func.count(Transaction.id)).where(Transaction.invoice_id == invoice.id)
    )
    transaction_count = count_result.scalar() or 0

    days_until_due = (invoice.due_date - today).days if invoice.due_date >= today else 0

    return InvoiceSummary(
        invoice_id=invoice.id,
        reference_month=invoice.reference_month,
        reference_year=invoice.reference_year,
        period_display=invoice.period_display,
        total_amount=float(invoice.total_amount),
        paid_amount=float(invoice.paid_amount),
        remaining_amount=float(invoice.remaining_amount),
        status=invoice.status,
        due_date=invoice.due_date,
        days_until_due=days_until_due,
        transaction_count=transaction_count,
    )


@router.post("/detect-card", response_model=CardDetectionResult)
async def detect_card_from_document(
    document_data: dict,
    current_user: CurrentUser,
    db: DbSession,
):
    """Detecta cartao de credito baseado nos dados extraidos do documento"""
    service = InvoiceService(db)
    cards = await service.detect_card_from_document(current_user, document_data)

    if not cards:
        return CardDetectionResult(detected_cards=[], suggested_card_id=None)

    # Buscar nomes de todas as contas de uma vez
    account_ids = [card.account_id for card in cards]
    account_result = await db.execute(
        select(Account.id, Account.name).where(Account.id.in_(account_ids))
    )
    account_names = {row[0]: row[1] for row in account_result.all()}

    detected_cards = []
    for card in cards:
        detected_cards.append(
            DetectedCardInfo(
                credit_card_id=card.id,
                account_name=account_names.get(card.account_id, "Cartao"),
                last_four_digits=card.last_four_digits,
                match_score=1,  # Simplificado
            )
        )

    return CardDetectionResult(
        detected_cards=detected_cards,
        suggested_card_id=cards[0].id if cards else None,
    )


class CreateCardFromInvoiceRequest(BaseModel):
    """Dados para criar um cartao a partir de uma fatura"""

    card_issuer: str  # "itau", "nubank", etc.
    card_last_digits: str | None = None  # "8849"
    card_name: str | None = None  # "Itau Visa Platinum"
    closing_day: int = 1  # Dia do mes de fechamento
    due_day: int = 10  # Dia do mes de vencimento
    credit_limit: float = 0  # Limite do cartao (pode ser 0 se desconhecido)
    color: str | None = None
    icon: str | None = None


class CreateCardFromInvoiceResponse(BaseModel):
    credit_card_id: int
    account_id: int
    account_name: str
    message: str


class ProjectFutureRequest(BaseModel):
    credit_card_id: int
    months_ahead: int = 6
    include_installments: bool = True
    include_recurring: bool = True


class ProjectFutureResponse(BaseModel):
    message: str
    invoices_created: int
    transactions_created: int


# Mapeamento de cores por banco
BANK_COLORS = {
    "itau": "#EC7000",  # Laranja Itau
    "nubank": "#820AD1",  # Roxo Nubank
    "inter": "#FF7A00",  # Laranja Inter
    "santander": "#EC0000",  # Vermelho Santander
    "bradesco": "#CC092F",  # Vermelho Bradesco
    "bb": "#FFCC00",  # Amarelo BB
    "caixa": "#005CA9",  # Azul Caixa
    "c6": "#1A1A1A",  # Preto C6
    "xp": "#FFD100",  # Amarelo XP
    "btg": "#000000",  # Preto BTG
    "original": "#00A857",  # Verde Original
    "next": "#00E676",  # Verde Next
    "neon": "#00D4AA",  # Verde Neon
    "pagbank": "#00AB4E",  # Verde PagBank
    "picpay": "#21C25E",  # Verde PicPay
    "mercadopago": "#00B1EA",  # Azul MercadoPago
    "digio": "#0052FF",  # Azul Digio
    "ame": "#FF007A",  # Rosa Ame
    "default": "#6366F1",  # Indigo (padrao)
}


@router.post(
    "/create-card-from-invoice", response_model=CreateCardFromInvoiceResponse, status_code=201
)
async def create_card_from_invoice(
    data: CreateCardFromInvoiceRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Cria um novo cartao de credito a partir dos dados extraidos de uma fatura.

    Util quando o usuario envia uma fatura de um cartao que ainda nao esta cadastrado.
    O sistema extrai as informacoes do PDF e usa este endpoint para criar o cartao.
    """
    from app.models.credit_card import CreditCard

    # Gerar nome do cartao se nao fornecido
    issuer_names = {
        "itau": "Itau",
        "nubank": "Nubank",
        "inter": "Inter",
        "santander": "Santander",
        "bradesco": "Bradesco",
        "bb": "Banco do Brasil",
        "caixa": "Caixa",
        "c6": "C6 Bank",
        "xp": "XP",
        "btg": "BTG Pactual",
        "original": "Original",
        "next": "Next",
        "neon": "Neon",
        "pagbank": "PagBank",
        "picpay": "PicPay",
        "mercadopago": "Mercado Pago",
        "digio": "Digio",
    }

    issuer_display = issuer_names.get(data.card_issuer.lower(), data.card_issuer.title())

    if data.card_name:
        account_name = data.card_name
    elif data.card_last_digits:
        account_name = f"{issuer_display} *{data.card_last_digits}"
    else:
        account_name = f"{issuer_display} Cartao"

    # Usar cor do banco ou cor fornecida
    color = data.color or BANK_COLORS.get(data.card_issuer.lower(), BANK_COLORS["default"])
    icon = data.icon or "credit-card"

    # Criar conta
    account = Account(
        user_id=current_user.id,
        name=account_name,
        type=AccountType.CREDIT_CARD.value,
        balance=Decimal("0"),
        currency="BRL",
        color=color,
        icon=icon,
        ownership_type="personal",
    )
    db.add(account)
    await db.flush()

    # Criar cartao de credito
    credit_card = CreditCard(
        account_id=account.id,
        user_id=current_user.id,
        credit_limit=Decimal(str(data.credit_limit)),
        closing_day=data.closing_day,
        due_day=data.due_day,
        last_four_digits=data.card_last_digits,
        is_active=True,
    )
    db.add(credit_card)
    await db.commit()
    await db.refresh(credit_card)

    return CreateCardFromInvoiceResponse(
        credit_card_id=credit_card.id,
        account_id=account.id,
        account_name=account_name,
        message=f"Cartao '{account_name}' criado com sucesso!",
    )


@router.post("/project-future", response_model=ProjectFutureResponse)
async def project_future_transactions(
    data: ProjectFutureRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Projeta transacoes futuras (parcelas e recorrentes) para faturas futuras.

    Util para:
    - Visualizar compromissos futuros no cartao
    - Antecipar o valor das proximas faturas
    - Planejar pagamentos

    As transacoes projetadas sao marcadas como is_paid=False e serao
    atualizadas quando o PDF real da fatura for enviado.
    """
    # Buscar cartao de credito
    card_result = await db.execute(
        select(CreditCard).where(
            CreditCard.id == data.credit_card_id,
            CreditCard.user_id == current_user.id,
        )
    )
    credit_card = card_result.scalar_one_or_none()

    if not credit_card:
        raise HTTPException(status_code=404, detail="Cartao nao encontrado")

    total_transactions = 0
    invoices_before = set()
    invoices_after = set()

    # Contar faturas antes
    inv_result = await db.execute(
        select(CreditCardInvoice.id).where(CreditCardInvoice.credit_card_id == data.credit_card_id)
    )
    invoices_before = set(inv_result.scalars().all())

    service = InvoiceService(db)

    # Projetar recorrentes
    if data.include_recurring:
        recurring_txs = await service.project_recurring_to_invoices(
            user=current_user,
            credit_card=credit_card,
            months_ahead=data.months_ahead,
        )
        total_transactions += len(recurring_txs)

    # Parcelas futuras ja sao criadas automaticamente quando uma compra parcelada e registrada
    # com create_future_installments=True, mas podemos forcar a atualizacao aqui
    if data.include_installments:
        from app.models.installment import InstallmentSeries, InstallmentSeriesStatus
        from app.modules.installments.services.installment_service import InstallmentService

        installment_service = InstallmentService(db)

        # Buscar series ativas do cartao
        series_result = await db.execute(
            select(InstallmentSeries).where(
                InstallmentSeries.user_id == current_user.id,
                InstallmentSeries.credit_card_id == data.credit_card_id,
                InstallmentSeries.status == InstallmentSeriesStatus.ACTIVE,
            )
        )
        series_list = list(series_result.scalars().all())

        for series in series_list:
            # Criar parcelas futuras que ainda nao existem
            future_txs = await installment_service.create_future_installments(
                user=current_user,
                series=series,
                from_installment=series.paid_count,
            )
            total_transactions += len(future_txs)

    await db.commit()

    # Contar faturas depois
    inv_result = await db.execute(
        select(CreditCardInvoice.id).where(CreditCardInvoice.credit_card_id == data.credit_card_id)
    )
    invoices_after = set(inv_result.scalars().all())

    new_invoices = len(invoices_after - invoices_before)

    return ProjectFutureResponse(
        message=f"Projecao concluida: {total_transactions} transacoes e {new_invoices} faturas criadas",
        invoices_created=new_invoices,
        transactions_created=total_transactions,
    )


class ReprocessOrphanResponse(BaseModel):
    """Resposta do reprocessamento de transações órfãs"""

    message: str
    found: int
    processed: int
    errors: list[dict]
    invoices_updated: list[int]
    transactions: list[dict]


@router.post("/reprocess-orphan-transactions", response_model=ReprocessOrphanResponse)
async def reprocess_orphan_transactions(
    current_user: CurrentUser,
    db: DbSession,
    credit_card_id: int | None = Query(
        None,
        description="ID do cartão específico para reprocessar. Se não informado, processa todos os cartões.",
    ),
):
    """
    Reprocessa transações órfãs que estão em contas de cartão de crédito
    mas não foram vinculadas à fatura corretamente.

    Isso é útil para corrigir transações que foram criadas antes do fix
    de auto-inferência de credit_card_id a partir do account_id.

    O endpoint irá:
    1. Encontrar transações em contas do tipo 'credit_card' sem credit_card_id
    2. Vincular essas transações ao cartão de crédito correto
    3. Calcular e vincular à fatura apropriada baseado na data da transação
    4. Atualizar o payment_method para 'credit_card'
    5. Recalcular os totais das faturas afetadas
    """
    service = InvoiceService(db)

    result = await service.reprocess_orphan_transactions(
        user=current_user,
        credit_card_id=credit_card_id,
    )

    await db.commit()

    return ReprocessOrphanResponse(
        message=f"Reprocessamento concluído: {result['processed']}/{result['found']} transações processadas",
        found=result["found"],
        processed=result["processed"],
        errors=result["errors"],
        invoices_updated=result["invoices_updated"],
        transactions=result["transactions"],
    )


class DuplicateSeriesPair(BaseModel):
    """Par de séries potencialmente duplicadas"""

    series_a_id: int
    series_b_id: int
    series_a_name: str
    series_b_name: str
    similarity_score: float


class InvoiceDuplicateWarning(BaseModel):
    """Alerta de duplicatas em uma fatura"""

    has_duplicates: bool
    estimated_excess: float = 0.0
    affected_series_pairs: list[DuplicateSeriesPair] = []
    duplicate_count: int = 0


@router.get("/{invoice_id}/duplicate-warnings", response_model=InvoiceDuplicateWarning)
async def get_invoice_duplicate_warnings(
    invoice_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Verifica se a fatura tem parcelas de séries duplicadas.

    Retorna:
    - has_duplicates: bool
    - estimated_excess: float (valor a mais devido a duplicatas)
    - affected_series_pairs: list de pares de séries duplicadas
    - duplicate_count: número de parcelas duplicadas
    """
    from app.modules.installments.services.duplicate_detection_service import (
        DuplicateDetectionService,
    )

    # Verificar se fatura existe e pertence ao usuário
    invoice_result = await db.execute(
        select(CreditCardInvoice).where(
            and_(
                CreditCardInvoice.id == invoice_id,
                CreditCardInvoice.user_id == current_user.id,
            )
        )
    )
    invoice = invoice_result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fatura não encontrada")

    # Buscar todas as transações parceladas desta fatura
    transactions_result = await db.execute(
        select(Transaction).where(
            and_(
                Transaction.invoice_id == invoice_id,
                Transaction.installment_series_id.is_not(None),
            )
        )
    )
    transactions = list(transactions_result.scalars().all())

    if not transactions:
        return InvoiceDuplicateWarning(has_duplicates=False)

    # Obter IDs únicos das séries nesta fatura
    series_ids = list(set(t.installment_series_id for t in transactions if t.installment_series_id))

    if len(series_ids) < 2:
        return InvoiceDuplicateWarning(has_duplicates=False)

    # Criar mapa de transações por ID para lookup rápido
    transactions_by_id = {tx.id: tx for tx in transactions}

    # Detectar duplicatas entre essas séries
    detection_service = DuplicateDetectionService(db)
    all_duplicates = await detection_service.find_duplicate_groups(
        user=current_user, min_similarity=0.7
    )

    # Filtrar apenas duplicatas que afetam esta fatura
    affected_pairs = []
    total_excess = 0.0
    duplicate_count = 0

    for group in all_duplicates:
        series_in_group = [s.id for s in group.series]

        # Verificar se AMBAS as séries do grupo estão nesta fatura
        intersection = set(series_in_group) & set(series_ids)

        if len(intersection) >= 2:  # Ambas séries do grupo estão na fatura
            # Calcular excesso APENAS para conflitos nesta fatura
            conflicts_in_invoice = []

            for conflict in group.conflicts:
                # Verificar se AMBAS as transações do conflito estão nesta fatura
                tx_a_in_invoice = conflict.series_a_transaction_id in transactions_by_id
                tx_b_in_invoice = conflict.series_b_transaction_id in transactions_by_id

                # Só é um conflito nesta fatura se AMBAS as transações estão aqui
                if tx_a_in_invoice and tx_b_in_invoice:
                    conflicts_in_invoice.append(conflict)
                    # Contar o valor de UMA das transações duplicadas como excess
                    tx = transactions_by_id[conflict.series_a_transaction_id]
                    total_excess += float(tx.amount)
                    duplicate_count += 1

            # Só adicionar o par se realmente houver conflitos nesta fatura
            if conflicts_in_invoice:
                affected_pairs.append(
                    DuplicateSeriesPair(
                        series_a_id=group.series[0].id,
                        series_b_id=group.series[1].id,
                        series_a_name=group.series[0].merchant_name,
                        series_b_name=group.series[1].merchant_name,
                        similarity_score=group.similarity_score,
                    )
                )

    return InvoiceDuplicateWarning(
        has_duplicates=len(affected_pairs) > 0,
        estimated_excess=total_excess,
        affected_series_pairs=affected_pairs,
        duplicate_count=duplicate_count,
    )
