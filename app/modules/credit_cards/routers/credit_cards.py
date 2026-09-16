from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select

from app.core.deps import CurrentUser, DbSession
from app.models.account import Account, AccountType
from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import CreditCardInvoice, InvoiceStatus
from app.models.household import HouseholdMember
from app.modules.credit_cards.schemas.credit_card import (
    CreditCardCreate,
    CreditCardListResponse,
    CreditCardResponse,
    CreditCardUpdate,
    InvoicePasswordRequest,
)
from app.modules.credit_cards.services.invoice_service import InvoiceService
from app.modules.household.utils.household_helpers import validate_create_permission

router = APIRouter()


async def get_household_user_ids(db, user) -> list[int]:
    """Get all user IDs in the same household/license as the user"""
    if not user.license_id:
        return []

    result = await db.execute(
        select(HouseholdMember.user_id).where(HouseholdMember.license_id == user.license_id)
    )
    return list(result.scalars().all())


@router.get("", response_model=list[CreditCardListResponse])
async def list_credit_cards(current_user: CurrentUser, db: DbSession):
    """Lista todos os cartoes de credito do usuario"""
    household_user_ids = await get_household_user_ids(db, current_user)

    if household_user_ids:
        result = await db.execute(
            select(CreditCard, Account)
            .join(Account, CreditCard.account_id == Account.id)
            .where(
                or_(
                    and_(
                        CreditCard.user_id == current_user.id, Account.ownership_type == "personal"
                    ),
                    and_(
                        CreditCard.user_id.in_(household_user_ids),
                        Account.ownership_type == "household",
                    ),
                )
            )
        )
    else:
        result = await db.execute(
            select(CreditCard, Account)
            .join(Account, CreditCard.account_id == Account.id)
            .where(CreditCard.user_id == current_user.id)
        )

    cards = result.all()

    # Calcular saldo em aberto para cada cartao a partir das faturas abertas
    card_ids = [card.id for card, _ in cards]
    used_limits = {}

    if card_ids:
        # Soma o valor restante (total_amount - paid_amount) de faturas NÃO pagas completamente
        # Inclui: open, closed, overdue, partial
        # Exclui apenas: paid (já pagas)
        invoice_result = await db.execute(
            select(
                CreditCardInvoice.credit_card_id,
                func.coalesce(
                    func.sum(CreditCardInvoice.total_amount - CreditCardInvoice.paid_amount), 0
                ).label("total_used"),
            )
            .where(
                CreditCardInvoice.credit_card_id.in_(card_ids),
                CreditCardInvoice.status != InvoiceStatus.PAID.value,
            )
            .group_by(CreditCardInvoice.credit_card_id)
        )
        for row in invoice_result:
            used_limits[row.credit_card_id] = float(row.total_used)

    return [
        CreditCardListResponse(
            id=card.id,
            account_id=card.account_id,
            name=account.name,
            nickname=card.nickname,
            bank_id=card.bank_id,
            credit_limit=float(card.credit_limit),
            current_balance=used_limits.get(card.id, 0.0),
            available_limit=float(card.credit_limit) - used_limits.get(card.id, 0.0),
            closing_day=card.closing_day,
            due_day=card.due_day,
            has_points=card.has_points,
            points_program=card.points_program,
            points_factor=float(card.points_factor) if card.points_factor else None,
            card_brand=card.card_brand,
            card_variant=card.card_variant,
            last_four_digits=card.last_four_digits,
            annual_fee=float(card.annual_fee) if card.annual_fee else None,
            annual_fee_frequency=card.annual_fee_frequency,
            annual_fee_waived=card.annual_fee_waived,
            color=account.color,
            icon=account.icon,
            is_active=card.is_active,
        )
        for card, account in cards
    ]


@router.post("", response_model=CreditCardResponse, status_code=201)
async def create_credit_card(
    data: CreditCardCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria um novo cartao de credito (cria conta associada automaticamente)"""
    # Validate permission to create with specified ownership_type
    await validate_create_permission(db, current_user, data.ownership_type.value)

    # Create the linked account
    account = Account(
        user_id=current_user.id,
        name=data.name,
        type=AccountType.CREDIT_CARD.value,
        balance=data.initial_balance,
        currency="BRL",
        color=data.color,
        icon=data.icon,
        ownership_type=data.ownership_type.value,
    )
    db.add(account)
    await db.flush()  # Get account.id

    # Create the credit card
    credit_card = CreditCard(
        account_id=account.id,
        user_id=current_user.id,
        credit_limit=data.credit_limit,
        closing_day=data.closing_day,
        due_day=data.due_day,
        has_points=data.has_points,
        points_program=data.points_program.value if data.points_program else None,
        points_program_name=data.points_program_name,
        points_factor=data.points_factor,
        points_factor_international=data.points_factor_international,
        nickname=data.nickname,
        bank_id=data.bank_id,
        card_brand=data.card_brand,
        card_variant=data.card_variant,
        last_four_digits=data.last_four_digits,
        annual_fee=data.annual_fee,
        annual_fee_frequency=data.annual_fee_frequency,
        annual_fee_waived=data.annual_fee_waived,
        benefits_notes=data.benefits_notes,
    )
    db.add(credit_card)
    await db.commit()
    await db.refresh(credit_card)
    await db.refresh(account)

    return CreditCardResponse(
        id=credit_card.id,
        account_id=credit_card.account_id,
        user_id=credit_card.user_id,
        credit_limit=float(credit_card.credit_limit),
        closing_day=credit_card.closing_day,
        due_day=credit_card.due_day,
        has_points=credit_card.has_points,
        points_program=credit_card.points_program,
        points_program_name=credit_card.points_program_name,
        points_factor=float(credit_card.points_factor),
        points_factor_international=float(credit_card.points_factor_international)
        if credit_card.points_factor_international
        else None,
        nickname=credit_card.nickname,
        bank_id=credit_card.bank_id,
        card_brand=credit_card.card_brand,
        card_variant=credit_card.card_variant,
        last_four_digits=credit_card.last_four_digits,
        annual_fee=float(credit_card.annual_fee) if credit_card.annual_fee else None,
        annual_fee_waived=credit_card.annual_fee_waived,
        benefits_notes=credit_card.benefits_notes,
        is_active=credit_card.is_active,
        created_at=credit_card.created_at,
        updated_at=credit_card.updated_at,
        account_name=account.name,
        account_balance=float(account.balance),
        account_color=account.color,
        account_icon=account.icon,
    )


@router.get("/{card_id}", response_model=CreditCardResponse)
async def get_credit_card(
    card_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna um cartao de credito especifico"""
    result = await db.execute(
        select(CreditCard, Account)
        .join(Account, CreditCard.account_id == Account.id)
        .where(
            CreditCard.id == card_id,
            CreditCard.user_id == current_user.id,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Cartao nao encontrado")

    card, account = row

    return CreditCardResponse(
        id=card.id,
        account_id=card.account_id,
        user_id=card.user_id,
        credit_limit=float(card.credit_limit),
        closing_day=card.closing_day,
        due_day=card.due_day,
        has_points=card.has_points,
        points_program=card.points_program,
        points_program_name=card.points_program_name,
        points_factor=float(card.points_factor),
        points_factor_international=float(card.points_factor_international)
        if card.points_factor_international
        else None,
        nickname=card.nickname,
        bank_id=card.bank_id,
        card_brand=card.card_brand,
        card_variant=card.card_variant,
        last_four_digits=card.last_four_digits,
        annual_fee=float(card.annual_fee) if card.annual_fee else None,
        annual_fee_waived=card.annual_fee_waived,
        benefits_notes=card.benefits_notes,
        is_active=card.is_active,
        created_at=card.created_at,
        updated_at=card.updated_at,
        has_invoice_password=bool(card.invoice_password_encrypted),
        account_name=account.name,
        account_balance=float(account.balance),
        account_color=account.color,
        account_icon=account.icon,
    )


@router.patch("/{card_id}", response_model=CreditCardResponse)
async def update_credit_card(
    card_id: int,
    data: CreditCardUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza um cartao de credito"""
    result = await db.execute(
        select(CreditCard, Account)
        .join(Account, CreditCard.account_id == Account.id)
        .where(
            CreditCard.id == card_id,
            CreditCard.user_id == current_user.id,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Cartao nao encontrado")

    card, account = row

    # Update card fields
    card_fields = [
        "credit_limit",
        "closing_day",
        "due_day",
        "has_points",
        "points_program",
        "points_program_name",
        "points_factor",
        "points_factor_international",
        "nickname",
        "bank_id",
        "card_brand",
        "card_variant",
        "last_four_digits",
        "annual_fee",
        "annual_fee_frequency",
        "annual_fee_waived",
        "benefits_notes",
        "is_active",
    ]
    account_fields = ["name", "color", "icon"]

    update_data = data.model_dump(exclude_unset=True)

    for field in card_fields:
        if field in update_data:
            value = update_data[field]
            if field == "points_program" and value:
                value = value.value
            setattr(card, field, value)

    for field in account_fields:
        if field in update_data:
            setattr(account, field, update_data[field])

    await db.commit()
    await db.refresh(card)
    await db.refresh(account)

    return CreditCardResponse(
        id=card.id,
        account_id=card.account_id,
        user_id=card.user_id,
        credit_limit=float(card.credit_limit),
        closing_day=card.closing_day,
        due_day=card.due_day,
        has_points=card.has_points,
        points_program=card.points_program,
        points_program_name=card.points_program_name,
        points_factor=float(card.points_factor),
        points_factor_international=float(card.points_factor_international)
        if card.points_factor_international
        else None,
        nickname=card.nickname,
        bank_id=card.bank_id,
        card_brand=card.card_brand,
        card_variant=card.card_variant,
        last_four_digits=card.last_four_digits,
        annual_fee=float(card.annual_fee) if card.annual_fee else None,
        annual_fee_waived=card.annual_fee_waived,
        benefits_notes=card.benefits_notes,
        is_active=card.is_active,
        created_at=card.created_at,
        updated_at=card.updated_at,
        has_invoice_password=bool(card.invoice_password_encrypted),
        account_name=account.name,
        account_balance=float(account.balance),
        account_color=account.color,
        account_icon=account.icon,
    )


@router.delete("/{card_id}", status_code=204)
async def delete_credit_card(
    card_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove um cartao de credito (e sua conta associada)"""
    result = await db.execute(
        select(CreditCard).where(
            CreditCard.id == card_id,
            CreditCard.user_id == current_user.id,
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Cartao nao encontrado")

    # Deleting the card will cascade delete the account due to ondelete="CASCADE"
    # Actually, account has the cascade, so we need to delete account first
    account_result = await db.execute(select(Account).where(Account.id == card.account_id))
    account = account_result.scalar_one_or_none()

    if account:
        await db.delete(account)  # This cascades to delete the card
    else:
        await db.delete(card)

    await db.commit()


class ProjectRecurringResponse(BaseModel):
    """Resposta da projecao de recorrentes"""

    message: str
    transactions_created: int
    months_projected: int


@router.post("/{card_id}/project-recurring", response_model=ProjectRecurringResponse)
async def project_recurring_transactions(
    card_id: int,
    current_user: CurrentUser,
    db: DbSession,
    months_ahead: int = Query(6, ge=1, le=12, description="Numero de meses para projetar"),
):
    """
    Projeta transacoes recorrentes para faturas futuras do cartao.

    Busca todas as transacoes recorrentes ativas vinculadas ao cartao
    e cria projecoes (is_paid=False) para os proximos N meses.
    """
    # Verificar se o cartao pertence ao usuario
    result = await db.execute(
        select(CreditCard).where(
            CreditCard.id == card_id,
            CreditCard.user_id == current_user.id,
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Cartao nao encontrado")

    # Projetar recorrentes
    service = InvoiceService(db)
    created_transactions = await service.project_recurring_to_invoices(
        user=current_user,
        credit_card=card,
        months_ahead=months_ahead,
    )

    return ProjectRecurringResponse(
        message="Projecao concluida com sucesso",
        transactions_created=len(created_transactions),
        months_projected=months_ahead,
    )


class RecalculateInvoicesResponse(BaseModel):
    """Resposta do recalculo de faturas"""

    message: str
    transactions_linked: int
    invoices_created: int
    invoices_updated: int


@router.post("/{card_id}/recalculate-invoices", response_model=RecalculateInvoicesResponse)
async def recalculate_card_invoices(
    card_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Recalcula e vincula transações do cartão às faturas corretas.

    Este endpoint:
    1. Busca todas as transações do cartão sem invoice_id e vincula à fatura correta
    2. Verifica transações que JÁ têm invoice_id mas estão na fatura ERRADA (baseado na data)
    3. Move transações para as faturas corretas quando necessário
    4. Cria as faturas se não existirem
    5. Recalcula os totais de todas as faturas afetadas

    Útil para corrigir transações que foram criadas antes do sistema de faturas,
    que tiveram a data alterada, ou que por algum motivo estão na fatura errada.
    """
    from app.models.transaction import Transaction

    # Verificar se o cartao pertence ao usuario
    result = await db.execute(
        select(CreditCard).where(
            CreditCard.id == card_id,
            CreditCard.user_id == current_user.id,
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Cartao nao encontrado")

    service = InvoiceService(db)
    affected_invoices = set()
    invoices_created = 0
    transactions_linked = 0
    transactions_moved = 0

    # 1. Buscar transações do cartão sem invoice_id
    tx_result = await db.execute(
        select(Transaction).where(
            Transaction.credit_card_id == card_id,
            Transaction.user_id == current_user.id,
            Transaction.invoice_id.is_(None),
        )
    )
    transactions_without_invoice = list(tx_result.scalars().all())

    # Para cada transação sem fatura, vincular à fatura correta
    for transaction in transactions_without_invoice:
        period = service.calculate_invoice_period(card, transaction.date)

        invoice = await service.get_or_create_invoice(
            user=current_user,
            credit_card=card,
            reference_month=period["reference_month"],
            reference_year=period["reference_year"],
            closing_date=period["closing_date"],
            due_date=period["due_date"],
        )

        if invoice.total_amount == 0 and invoice.id not in affected_invoices:
            invoices_created += 1

        transaction.invoice_id = invoice.id
        affected_invoices.add(invoice.id)
        transactions_linked += 1

    # 2. Buscar transações que JÁ têm invoice_id para verificar se estão na fatura correta
    tx_with_invoice_result = await db.execute(
        select(Transaction).where(
            Transaction.credit_card_id == card_id,
            Transaction.user_id == current_user.id,
            Transaction.invoice_id.isnot(None),
        )
    )
    transactions_with_invoice = list(tx_with_invoice_result.scalars().all())

    # Buscar todas as faturas do cartão para comparação
    all_invoices_result = await db.execute(
        select(CreditCardInvoice).where(
            CreditCardInvoice.credit_card_id == card_id,
            CreditCardInvoice.user_id == current_user.id,
        )
    )
    invoices_by_id = {inv.id: inv for inv in all_invoices_result.scalars().all()}

    # Verificar cada transação com invoice_id
    for transaction in transactions_with_invoice:
        current_invoice = invoices_by_id.get(transaction.invoice_id)
        if not current_invoice:
            # Fatura não existe mais, vincular à fatura correta
            period = service.calculate_invoice_period(card, transaction.date)
            invoice = await service.get_or_create_invoice(
                user=current_user,
                credit_card=card,
                reference_month=period["reference_month"],
                reference_year=period["reference_year"],
                closing_date=period["closing_date"],
                due_date=period["due_date"],
            )
            transaction.invoice_id = invoice.id
            affected_invoices.add(invoice.id)
            transactions_moved += 1
            continue

        # Calcular qual fatura a transação DEVERIA estar baseado na data
        period = service.calculate_invoice_period(card, transaction.date)

        # Verificar se está na fatura errada
        if (
            current_invoice.reference_month != period["reference_month"]
            or current_invoice.reference_year != period["reference_year"]
        ):
            # Marcar fatura antiga como afetada
            affected_invoices.add(current_invoice.id)

            # Obter ou criar a fatura correta
            correct_invoice = await service.get_or_create_invoice(
                user=current_user,
                credit_card=card,
                reference_month=period["reference_month"],
                reference_year=period["reference_year"],
                closing_date=period["closing_date"],
                due_date=period["due_date"],
            )

            if correct_invoice.total_amount == 0 and correct_invoice.id not in affected_invoices:
                invoices_created += 1

            # Mover transação para a fatura correta
            transaction.invoice_id = correct_invoice.id
            affected_invoices.add(correct_invoice.id)
            transactions_moved += 1
        else:
            # Está na fatura correta, apenas marcar para recalcular total
            affected_invoices.add(current_invoice.id)

    await db.flush()

    # 3. Recalcular totais de todas as faturas afetadas
    for invoice_id in affected_invoices:
        inv_result = await db.execute(
            select(CreditCardInvoice).where(CreditCardInvoice.id == invoice_id)
        )
        invoice = inv_result.scalar_one_or_none()
        if invoice:
            await service.update_invoice_total(invoice)

    await db.commit()

    total_linked = transactions_linked + transactions_moved
    message = f"Recalculo concluido: {transactions_linked} vinculadas, {transactions_moved} movidas"

    return RecalculateInvoicesResponse(
        message=message,
        transactions_linked=total_linked,
        invoices_created=invoices_created,
        invoices_updated=len(affected_invoices),
    )


@router.post("/{card_id}/invoice-password", status_code=200)
async def save_invoice_password(
    card_id: int,
    request: InvoicePasswordRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Save encrypted invoice PDF password for automatic unlock.

    IMPORTANT: This password is ONLY for unlocking password-protected invoice PDF files.
    It has no relation to the credit card security or bank account password.

    Args:
        card_id: Credit card ID
        request: Request with password field
    """
    from app.core.crypto import encrypt_password

    # Fetch card and verify ownership
    result = await db.execute(
        select(CreditCard).where(CreditCard.id == card_id, CreditCard.user_id == current_user.id)
    )
    card = result.scalar_one_or_none()

    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado")

    # Encrypt and save password
    card.invoice_password_encrypted = encrypt_password(request.password)
    await db.commit()

    return {"message": "Senha salva com sucesso"}


@router.delete("/{card_id}/invoice-password", status_code=204)
async def delete_invoice_password(
    card_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Remove saved invoice PDF password from credit card.

    Args:
        card_id: Credit card ID
    """
    # Fetch card and verify ownership
    result = await db.execute(
        select(CreditCard).where(CreditCard.id == card_id, CreditCard.user_id == current_user.id)
    )
    card = result.scalar_one_or_none()

    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado")

    # Remove password
    card.invoice_password_encrypted = None
    await db.commit()

    return None
