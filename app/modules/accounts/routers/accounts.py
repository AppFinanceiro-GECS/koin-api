from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import and_, case, func, or_, select

from app.core.deps import CurrentUser, DbSession
from app.models.account import Account
from app.models.household import HouseholdMember
from app.models.receipt import Receipt, ReceiptPayment, ReceiptStatus
from app.models.transaction import Transaction, TransactionType
from app.modules.accounts.schemas.account import AccountCreate, AccountResponse, AccountUpdate

router = APIRouter()


async def get_household_user_ids(db, user) -> list[int]:
    """Get all user IDs in the same household/license as the user"""
    if not user.license_id:
        return []

    result = await db.execute(
        select(HouseholdMember.user_id).where(HouseholdMember.license_id == user.license_id)
    )
    return list(result.scalars().all())


async def calculate_account_balance(db, account_id: int) -> Decimal:
    """
    Calcula o saldo real da conta baseado nas transações e pagamentos de receipts.

    Saldo =
        (Transações normais sem receipt: receitas - despesas + transfers)
      + (ReceiptPayments desta conta - sempre despesas)

    Regra: Transações com receipt_id NÃO afetam saldo diretamente
    O saldo de compras vem dos ReceiptPayments.
    """
    # 1. Saldo de transações normais (sem receipt_id)
    transactions_result = await db.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.type == TransactionType.INCOME.value, Transaction.amount),
                        (Transaction.type == TransactionType.EXPENSE.value, -Transaction.amount),
                        # Transfer: saída (id menor que linked) = subtrai
                        (
                            and_(
                                Transaction.type == TransactionType.TRANSFER.value,
                                Transaction.linked_transaction_id.isnot(None),
                                Transaction.id < Transaction.linked_transaction_id,
                            ),
                            -Transaction.amount,
                        ),
                        # Transfer: entrada (id maior que linked) = soma
                        (
                            and_(
                                Transaction.type == TransactionType.TRANSFER.value,
                                Transaction.linked_transaction_id.isnot(None),
                                Transaction.id > Transaction.linked_transaction_id,
                            ),
                            Transaction.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            )
        ).where(
            Transaction.account_id == account_id,
            Transaction.receipt_id.is_(None),  # Apenas transações sem receipt
        )
    )
    transactions_balance = transactions_result.scalar() or Decimal(0)

    # 2. Total de ReceiptPayments (sempre despesas)
    receipt_payments_result = await db.execute(
        select(func.coalesce(func.sum(ReceiptPayment.amount), 0))
        .select_from(ReceiptPayment)
        .join(Receipt)
        .where(
            ReceiptPayment.account_id == account_id, Receipt.status == ReceiptStatus.CONFIRMED.value
        )
    )
    receipt_payments_total = receipt_payments_result.scalar() or Decimal(0)

    # Saldo = transações normais - pagamentos de receipts
    return Decimal(str(transactions_balance)) - Decimal(str(receipt_payments_total))


@router.get("", response_model=list[AccountResponse])
async def list_accounts(current_user: CurrentUser, db: DbSession):
    """Lista todas as contas do usuário (pessoais + household) com saldos atualizados"""
    household_user_ids = await get_household_user_ids(db, current_user)

    # Subquery para calcular saldo de transacoes por conta (excluindo transações de receipt)
    transactions_balance_subquery = (
        select(
            Transaction.account_id,
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.type == TransactionType.INCOME.value, Transaction.amount),
                        (Transaction.type == TransactionType.EXPENSE.value, -Transaction.amount),
                        # Transfer: saída (id menor que linked) = subtrai
                        (
                            and_(
                                Transaction.type == TransactionType.TRANSFER.value,
                                Transaction.linked_transaction_id.isnot(None),
                                Transaction.id < Transaction.linked_transaction_id,
                            ),
                            -Transaction.amount,
                        ),
                        # Transfer: entrada (id maior que linked) = soma
                        (
                            and_(
                                Transaction.type == TransactionType.TRANSFER.value,
                                Transaction.linked_transaction_id.isnot(None),
                                Transaction.id > Transaction.linked_transaction_id,
                            ),
                            Transaction.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("transaction_balance"),
        )
        .where(Transaction.receipt_id.is_(None))  # Excluir transações de receipt
        .group_by(Transaction.account_id)
        .subquery()
    )

    # Subquery para calcular total de receipt payments por conta (sempre despesas)
    receipt_payments_subquery = (
        select(
            ReceiptPayment.account_id,
            func.coalesce(func.sum(ReceiptPayment.amount), 0).label("receipt_payments_total"),
        )
        .select_from(ReceiptPayment)
        .join(Receipt)
        .where(Receipt.status == ReceiptStatus.CONFIRMED.value)
        .group_by(ReceiptPayment.account_id)
        .subquery()
    )

    # Query otimizada com JOIN para pegar saldo das transacoes e receipt payments
    base_query = (
        select(
            Account,
            func.coalesce(transactions_balance_subquery.c.transaction_balance, 0).label(
                "tx_balance"
            ),
            func.coalesce(receipt_payments_subquery.c.receipt_payments_total, 0).label(
                "receipt_total"
            ),
        )
        .outerjoin(
            transactions_balance_subquery, transactions_balance_subquery.c.account_id == Account.id
        )
        .outerjoin(receipt_payments_subquery, receipt_payments_subquery.c.account_id == Account.id)
    )

    if household_user_ids:
        # User is in a household - get personal + household accounts
        base_query = base_query.where(
            or_(
                # Personal accounts from user
                and_(Account.user_id == current_user.id, Account.ownership_type == "personal"),
                # Household accounts from any family member
                and_(
                    Account.user_id.in_(household_user_ids), Account.ownership_type == "household"
                ),
            )
        )
    else:
        base_query = base_query.where(Account.user_id == current_user.id)

    result = await db.execute(base_query)
    rows = result.all()

    # Construir resposta com saldo calculado
    # Saldo = saldo_inicial + transações_normais - receipt_payments
    accounts_with_balance = []
    for row in rows:
        account = row[0]
        tx_balance = row[1] or Decimal(0)
        receipt_total = row[2] or Decimal(0)
        computed_balance = float(account.balance) + float(tx_balance) - float(receipt_total)

        account_dict = {
            "id": account.id,
            "name": account.name,
            "type": account.type,
            "balance": computed_balance,
            "currency": account.currency,
            "color": account.color,
            "icon": account.icon,
            "is_active": account.is_active,
            "ownership_type": account.ownership_type,
            "created_at": account.created_at,
        }
        accounts_with_balance.append(account_dict)

    return accounts_with_balance


@router.post("", response_model=AccountResponse, status_code=201)
async def create_account(
    data: AccountCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria uma nova conta"""
    account = Account(
        user_id=current_user.id,
        name=data.name,
        type=data.type,
        balance=data.balance,
        currency=data.currency,
        color=data.color,
        icon=data.icon,
        ownership_type=data.ownership_type.value,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna uma conta específica com saldo atualizado"""
    household_user_ids = await get_household_user_ids(db, current_user)

    if household_user_ids:
        result = await db.execute(
            select(Account).where(
                Account.id == account_id,
                or_(
                    and_(Account.user_id == current_user.id, Account.ownership_type == "personal"),
                    and_(
                        Account.user_id.in_(household_user_ids),
                        Account.ownership_type == "household",
                    ),
                ),
            )
        )
    else:
        result = await db.execute(
            select(Account).where(
                Account.id == account_id,
                Account.user_id == current_user.id,
            )
        )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    # Calcular saldo real baseado nas transações
    transaction_balance = await calculate_account_balance(db, account.id)
    computed_balance = float(account.balance) + float(transaction_balance)

    return {
        "id": account.id,
        "name": account.name,
        "type": account.type,
        "balance": computed_balance,
        "currency": account.currency,
        "color": account.color,
        "icon": account.icon,
        "is_active": account.is_active,
        "ownership_type": account.ownership_type,
        "created_at": account.created_at,
    }


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    data: AccountUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza uma conta"""
    household_user_ids = await get_household_user_ids(db, current_user)

    if household_user_ids:
        result = await db.execute(
            select(Account).where(
                Account.id == account_id,
                or_(
                    and_(Account.user_id == current_user.id, Account.ownership_type == "personal"),
                    and_(
                        Account.user_id.in_(household_user_ids),
                        Account.ownership_type == "household",
                    ),
                ),
            )
        )
    else:
        result = await db.execute(
            select(Account).where(
                Account.id == account_id,
                Account.user_id == current_user.id,
            )
        )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(account, field, value)

    await db.commit()
    await db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=204)
async def delete_account(
    account_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove uma conta"""
    household_user_ids = await get_household_user_ids(db, current_user)

    if household_user_ids:
        result = await db.execute(
            select(Account).where(
                Account.id == account_id,
                or_(
                    and_(Account.user_id == current_user.id, Account.ownership_type == "personal"),
                    and_(
                        Account.user_id.in_(household_user_ids),
                        Account.ownership_type == "household",
                    ),
                ),
            )
        )
    else:
        result = await db.execute(
            select(Account).where(
                Account.id == account_id,
                Account.user_id == current_user.id,
            )
        )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    await db.delete(account)
    await db.commit()
