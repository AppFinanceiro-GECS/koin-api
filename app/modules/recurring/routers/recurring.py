from fastapi import APIRouter, HTTPException, Query

from app.core.deps import CurrentUser, DbSession
from app.modules.recurring.schemas.recurring import (
    BatchRecurringFromSuggestionRequest,
    BatchRecurringItemResult,
    BatchRecurringResponse,
    RecurringCancelRequest,
    RecurringCreate,
    RecurringFromSuggestionCreate,
    RecurringResponse,
    RecurringSummary,
    RecurringUpdate,
)
from app.modules.recurring.services.recurring_service import RecurringTransactionService

router = APIRouter()


@router.post("", response_model=RecurringResponse, status_code=201)
async def create_recurring(
    data: RecurringCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria uma nova transação recorrente"""
    service = RecurringTransactionService(db)
    try:
        recurring = await service.create(current_user, data)
        # Buscar novamente com relacionamentos
        result = await service.get_by_id(current_user, recurring.id)
        return RecurringResponse(
            id=result.id,
            name=result.name,
            description=result.description,
            amount=float(result.amount),
            type=result.type,
            account_id=result.account_id,
            account_name=result.account.name if result.account else None,
            category_id=result.category_id,
            category_name=result.category.name if result.category else None,
            frequency=result.frequency,
            day_of_month=result.day_of_month,
            day_of_week=result.day_of_week,
            start_date=result.start_date,
            end_date=result.end_date,
            status=result.status,
            last_generated_date=result.last_generated_date,
            next_due_date=result.next_due_date,
            created_at=result.created_at,
            updated_at=result.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[RecurringResponse])
async def list_recurring(
    current_user: CurrentUser,
    db: DbSession,
    include_inactive: bool = Query(False, description="Incluir canceladas"),
):
    """Lista transações recorrentes do usuário"""
    service = RecurringTransactionService(db)
    return await service.list(current_user, include_inactive=include_inactive)


@router.get("/summary", response_model=RecurringSummary)
async def get_summary(
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna resumo das transações recorrentes"""
    service = RecurringTransactionService(db)
    return await service.get_summary(current_user)


@router.get("/{recurring_id}", response_model=RecurringResponse)
async def get_recurring(
    recurring_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna uma transação recorrente por ID"""
    service = RecurringTransactionService(db)
    result = await service.get_by_id(current_user, recurring_id)
    if not result:
        raise HTTPException(status_code=404, detail="Transação recorrente não encontrada")

    return RecurringResponse(
        id=result.id,
        name=result.name,
        description=result.description,
        amount=float(result.amount),
        type=result.type,
        account_id=result.account_id,
        account_name=result.account.name if result.account else None,
        category_id=result.category_id,
        category_name=result.category.name if result.category else None,
        frequency=result.frequency,
        day_of_month=result.day_of_month,
        day_of_week=result.day_of_week,
        start_date=result.start_date,
        end_date=result.end_date,
        status=result.status,
        last_generated_date=result.last_generated_date,
        next_due_date=result.next_due_date,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.patch("/{recurring_id}", response_model=RecurringResponse)
async def update_recurring(
    recurring_id: int,
    data: RecurringUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza uma transação recorrente"""
    service = RecurringTransactionService(db)
    try:
        result = await service.update(current_user, recurring_id, data)
        if not result:
            raise HTTPException(status_code=404, detail="Transação recorrente não encontrada")

        # Recarregar com relacionamentos
        result = await service.get_by_id(current_user, recurring_id)
        return RecurringResponse(
            id=result.id,
            name=result.name,
            description=result.description,
            amount=float(result.amount),
            type=result.type,
            account_id=result.account_id,
            account_name=result.account.name if result.account else None,
            category_id=result.category_id,
            category_name=result.category.name if result.category else None,
            frequency=result.frequency,
            day_of_month=result.day_of_month,
            day_of_week=result.day_of_week,
            start_date=result.start_date,
            end_date=result.end_date,
            status=result.status,
            last_generated_date=result.last_generated_date,
            next_due_date=result.next_due_date,
            created_at=result.created_at,
            updated_at=result.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{recurring_id}", status_code=204)
async def delete_recurring(
    recurring_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove uma transação recorrente"""
    service = RecurringTransactionService(db)
    success = await service.delete(current_user, recurring_id)
    if not success:
        raise HTTPException(status_code=404, detail="Transação recorrente não encontrada")


@router.post("/{recurring_id}/pause", response_model=RecurringResponse)
async def pause_recurring(
    recurring_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Pausa uma transação recorrente"""
    service = RecurringTransactionService(db)
    result = await service.pause(current_user, recurring_id)
    if not result:
        raise HTTPException(status_code=404, detail="Transação recorrente não encontrada")

    result = await service.get_by_id(current_user, recurring_id)
    return RecurringResponse(
        id=result.id,
        name=result.name,
        description=result.description,
        amount=float(result.amount),
        type=result.type,
        account_id=result.account_id,
        account_name=result.account.name if result.account else None,
        category_id=result.category_id,
        category_name=result.category.name if result.category else None,
        frequency=result.frequency,
        day_of_month=result.day_of_month,
        day_of_week=result.day_of_week,
        start_date=result.start_date,
        end_date=result.end_date,
        status=result.status,
        last_generated_date=result.last_generated_date,
        next_due_date=result.next_due_date,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.post("/{recurring_id}/cancel", response_model=dict)
async def cancel_recurring(
    recurring_id: int,
    data: RecurringCancelRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Cancela uma recorrencia.

    - Se `cancel_from_month` e `cancel_from_year` forem fornecidos,
      a recorrencia sera cancelada a partir daquele mes
    - Se `remove_projected=True` (default), remove transacoes projetadas
      das faturas futuras e atualiza os totais
    """
    service = RecurringTransactionService(db)
    result = await service.cancel(
        current_user,
        recurring_id,
        cancel_from_month=data.cancel_from_month,
        cancel_from_year=data.cancel_from_year,
        remove_projected=data.remove_projected,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Recorrencia nao encontrada")
    return result


@router.post("/{recurring_id}/resume", response_model=RecurringResponse)
async def resume_recurring(
    recurring_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retoma uma transação recorrente pausada"""
    service = RecurringTransactionService(db)
    result = await service.resume(current_user, recurring_id)
    if not result:
        raise HTTPException(status_code=404, detail="Transação recorrente não encontrada")

    result = await service.get_by_id(current_user, recurring_id)
    return RecurringResponse(
        id=result.id,
        name=result.name,
        description=result.description,
        amount=float(result.amount),
        type=result.type,
        account_id=result.account_id,
        account_name=result.account.name if result.account else None,
        category_id=result.category_id,
        category_name=result.category.name if result.category else None,
        frequency=result.frequency,
        day_of_month=result.day_of_month,
        day_of_week=result.day_of_week,
        start_date=result.start_date,
        end_date=result.end_date,
        status=result.status,
        last_generated_date=result.last_generated_date,
        next_due_date=result.next_due_date,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.post("/generate", response_model=dict)
async def generate_transactions(
    current_user: CurrentUser,
    db: DbSession,
):
    """Gera transações pendentes para recorrências vencidas"""
    service = RecurringTransactionService(db)
    generated = await service.generate_pending_transactions(current_user)
    return {"generated_count": len(generated)}


@router.post("/from-suggestion", response_model=RecurringResponse, status_code=201)
async def create_from_suggestion(
    data: RecurringFromSuggestionCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Cria uma transação recorrente a partir de uma sugestão detectada.

    Este endpoint é usado quando o sistema detecta um serviço recorrente
    (Netflix, Spotify, etc.) durante a extração de faturas e o usuário
    decide cadastrá-lo como recorrência.
    """
    from datetime import date as date_type

    from sqlalchemy import select

    from app.models.category import Category
    from app.models.recurring import RecurringTransaction

    service = RecurringTransactionService(db)

    # Verificar se já existe recorrência com mesmo nome e valor (evitar duplicados)
    existing = await db.execute(
        select(RecurringTransaction).where(
            RecurringTransaction.user_id == current_user.id,
            RecurringTransaction.name.ilike(data.name),
            RecurringTransaction.amount == data.amount,
            RecurringTransaction.status != "cancelled",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400, detail=f"Recorrência '{data.name}' já existe com mesmo valor"
        )

    # Resolver category_id se category_name foi fornecido
    category_id = data.category_id
    if not category_id and data.category_name:
        result = await db.execute(
            select(Category)
            .where(
                Category.user_id == current_user.id,
                Category.name.ilike(f"%{data.category_name}%"),
            )
            .limit(1)
        )
        category = result.scalar_one_or_none()
        if category:
            category_id = category.id

    # Criar RecurringCreate a partir dos dados da sugestão
    create_data = RecurringCreate(
        name=data.name,
        description=data.description,
        amount=data.amount,
        type=data.type,
        payment_method=data.payment_method,
        account_id=data.account_id,
        category_id=category_id,
        frequency=data.frequency,
        day_of_month=data.day_of_month,
        day_of_week=None,
        start_date=data.start_date or date_type.today(),
        end_date=None,
    )

    try:
        recurring = await service.create(current_user, create_data)
        # Buscar novamente com relacionamentos
        result = await service.get_by_id(current_user, recurring.id)
        return RecurringResponse(
            id=result.id,
            name=result.name,
            description=result.description,
            amount=float(result.amount),
            type=result.type,
            payment_method=result.payment_method,
            account_id=result.account_id,
            account_name=result.account.name if result.account else None,
            category_id=result.category_id,
            category_name=result.category.name if result.category else None,
            frequency=result.frequency,
            day_of_month=result.day_of_month,
            day_of_week=result.day_of_week,
            start_date=result.start_date,
            end_date=result.end_date,
            status=result.status,
            last_generated_date=result.last_generated_date,
            next_due_date=result.next_due_date,
            created_at=result.created_at,
            updated_at=result.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batch-from-suggestion", response_model=BatchRecurringResponse, status_code=201)
async def batch_create_from_suggestion(
    data: BatchRecurringFromSuggestionRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Cria múltiplas transações recorrentes a partir de sugestões detectadas.

    Processa todos os itens e retorna resultado individual para cada um,
    incluindo quais foram sucesso, quais são duplicados e quais tiveram erro.
    """
    from datetime import date as date_type

    from sqlalchemy import select

    from app.models.category import Category
    from app.models.recurring import RecurringTransaction

    service = RecurringTransactionService(db)

    results: list[BatchRecurringItemResult] = []
    success_count = 0
    duplicate_count = 0
    error_count = 0

    for index, item in enumerate(data.items):
        try:
            # Verificar se já existe recorrência com mesmo nome e valor
            existing = await db.execute(
                select(RecurringTransaction).where(
                    RecurringTransaction.user_id == current_user.id,
                    RecurringTransaction.name.ilike(item.name),
                    RecurringTransaction.amount == item.amount,
                    RecurringTransaction.status != "cancelled",
                )
            )
            if existing.scalar_one_or_none():
                results.append(
                    BatchRecurringItemResult(
                        index=index,
                        success=False,
                        recurring_name=item.name,
                        error=f"Recorrência '{item.name}' já existe com mesmo valor",
                        is_duplicate=True,
                    )
                )
                duplicate_count += 1
                continue

            # Resolver category_id se category_name foi fornecido
            category_id = item.category_id
            if not category_id and item.category_name:
                result = await db.execute(
                    select(Category)
                    .where(
                        Category.user_id == current_user.id,
                        Category.name.ilike(f"%{item.category_name}%"),
                    )
                    .limit(1)
                )
                category = result.scalar_one_or_none()
                if category:
                    category_id = category.id

            # Criar RecurringCreate a partir dos dados da sugestão
            create_data = RecurringCreate(
                name=item.name,
                description=item.description,
                amount=item.amount,
                type=item.type,
                payment_method=item.payment_method,
                account_id=item.account_id,
                category_id=category_id,
                frequency=item.frequency,
                day_of_month=item.day_of_month,
                day_of_week=None,
                start_date=item.start_date or date_type.today(),
                end_date=None,
            )

            recurring = await service.create(current_user, create_data)

            results.append(
                BatchRecurringItemResult(
                    index=index,
                    success=True,
                    recurring_id=recurring.id,
                    recurring_name=recurring.name,
                )
            )
            success_count += 1

        except ValueError as e:
            results.append(
                BatchRecurringItemResult(
                    index=index,
                    success=False,
                    recurring_name=item.name,
                    error=str(e),
                )
            )
            error_count += 1

        except Exception as e:
            results.append(
                BatchRecurringItemResult(
                    index=index,
                    success=False,
                    recurring_name=item.name,
                    error=str(e),
                )
            )
            error_count += 1

    return BatchRecurringResponse(
        total=len(data.items),
        success_count=success_count,
        duplicate_count=duplicate_count,
        error_count=error_count,
        results=results,
    )
