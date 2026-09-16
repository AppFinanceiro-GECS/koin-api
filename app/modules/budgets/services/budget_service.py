"""
Serviço de Orçamento (Budget)
Implementa funcionalidades baseadas em YNAB e Dave Ramsey

Evolução: Incorpora funcionalidades de Envelopes (histórico, status dinâmico,
transferências, subsídio diário) para uma experiência mais completa de orçamento.
"""

from calendar import monthrange
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.utils import utc_now
from app.models.budget import (
    Budget,
    BudgetHistoryChangeType,
    BudgetItem,
    BudgetItemHistory,
    BudgetItemStatus,
)
from app.models.category import Category
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.modules.budgets.schemas.budget import (
    BudgetComparisonResponse,
    BudgetCreate,
    BudgetItemCreate,
    BudgetItemHistoryResponse,
    BudgetItemResponse,
    BudgetItemUpdate,
    BudgetResponse,
    BudgetSummary,
    BudgetTransferRequest,
    BudgetTransferResponse,
    BudgetUpdate,
)
from app.modules.household.utils import (
    build_ownership_filter,
    get_household_member,
    get_household_user_ids,
    validate_create_permission,
    validate_edit_permission,
)


class BudgetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_budgets(self, user: User, year: int | None = None) -> list[Budget]:
        """Lista orçamentos do usuário (personal + household da família)"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        query = select(Budget).where(
            build_ownership_filter(
                Budget, Budget.user_id, Budget.ownership_type, user.id, household_user_ids, member
            )
        )

        if year is not None:
            query = query.where(Budget.year == year)

        query = query.order_by(Budget.year.desc(), Budget.month.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_or_create_budget(self, user: User, year: int, month: int) -> Budget:
        """Obtém ou cria orçamento para o mês"""
        result = await self.db.execute(
            select(Budget).where(
                Budget.user_id == user.id, Budget.year == year, Budget.month == month
            )
        )
        budget = result.scalar_one_or_none()

        if not budget:
            budget = Budget(user_id=user.id, year=year, month=month)
            self.db.add(budget)
            await self.db.flush()
            await self.db.refresh(budget)

        return budget

    async def get_budget(self, user: User, year: int, month: int) -> BudgetResponse | None:
        """Retorna orçamento com gastos calculados"""
        budget = await self.get_or_create_budget(user, year, month)

        # Calcular gastos reais por categoria
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)

        # Buscar transações do mês
        expenses_by_category = await self._get_expenses_by_category(user, start_date, end_date)
        total_income = await self._get_total_income(user, start_date, end_date)
        total_spent = sum(expenses_by_category.values())

        # Buscar nomes de todas as categorias de uma vez
        category_ids = [item.category_id for item in budget.items if item.category_id]
        category_names = {}
        if category_ids:
            cat_result = await self.db.execute(
                select(Category.id, Category.name).where(Category.id.in_(category_ids))
            )
            category_names = {row[0]: row[1] for row in cat_result.all()}

        # Calcular dias restantes no mês
        today = date.today()
        _, last_day = monthrange(year, month)
        if today.year == year and today.month == month:
            days_remaining = max(0, last_day - today.day)
        elif date(year, month, 1) > today:
            days_remaining = last_day
        else:
            days_remaining = 0

        # Montar itens com valores calculados
        items_response = []
        for item in budget.items:
            spent = expenses_by_category.get(item.category_id, Decimal(0))
            available = item.planned_amount + item.rollover_amount - spent
            percentage_used = (
                float(spent / item.planned_amount * 100) if item.planned_amount > 0 else 0
            )

            # Calcular status dinâmico (inspirado em Envelopes)
            item_status = self._calculate_item_status(percentage_used, available)

            # Calcular subsídio diário (inspirado em Envelopes)
            daily_allowance = Decimal(0)
            if days_remaining > 0 and available > 0:
                daily_allowance = available / days_remaining

            items_response.append(
                BudgetItemResponse(
                    id=item.id,
                    budget_id=item.budget_id,
                    category_id=item.category_id,
                    planned_amount=item.planned_amount,
                    rollover_amount=item.rollover_amount,
                    is_fixed=item.is_fixed,
                    priority=item.priority,
                    notes=item.notes,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                    spent_amount=spent,
                    available_amount=available,
                    percentage_used=percentage_used,
                    category_name=category_names.get(item.category_id),
                    status=item_status,
                    daily_allowance=daily_allowance,
                    days_remaining=days_remaining,
                )
            )

        total_planned = sum(item.planned_amount for item in budget.items)
        total_available = sum(i.available_amount for i in items_response)

        # Calcular score de saúde (0-100)
        health_score = self._calculate_health_score(
            total_planned, total_spent, budget.total_income_planned, total_income
        )

        return BudgetResponse(
            id=budget.id,
            user_id=budget.user_id,
            year=budget.year,
            month=budget.month,
            total_income_planned=budget.total_income_planned,
            total_expense_planned=total_planned,
            allow_rollover=budget.allow_rollover,
            notes=budget.notes,
            created_at=budget.created_at,
            updated_at=budget.updated_at,
            items=items_response,
            total_spent=total_spent,
            total_available=total_available,
            total_income_actual=total_income,
            balance=total_income - total_spent,
            health_score=health_score,
        )

    async def create_budget(self, user: User, data: BudgetCreate) -> Budget:
        """Cria orçamento com itens"""
        # Validar permissão para criar household
        await validate_create_permission(self.db, user, data.ownership_type.value)

        # Verificar se já existe
        existing = await self.db.execute(
            select(Budget).where(
                Budget.user_id == user.id, Budget.year == data.year, Budget.month == data.month
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Já existe orçamento para {data.month}/{data.year}",
            )

        budget = Budget(
            user_id=user.id,
            year=data.year,
            month=data.month,
            total_income_planned=data.total_income_planned,
            allow_rollover=data.allow_rollover,
            notes=data.notes,
            ownership_type=data.ownership_type.value,
        )
        self.db.add(budget)
        await self.db.flush()

        # Adicionar itens
        total_expense = Decimal(0)
        for item_data in data.items:
            item = BudgetItem(
                budget_id=budget.id,
                category_id=item_data.category_id,
                planned_amount=item_data.planned_amount,
                is_fixed=item_data.is_fixed,
                priority=item_data.priority,
                notes=item_data.notes,
            )
            self.db.add(item)
            total_expense += item_data.planned_amount

        budget.total_expense_planned = total_expense
        await self.db.flush()
        await self.db.refresh(budget)

        return budget

    async def update_budget(self, user: User, year: int, month: int, data: BudgetUpdate) -> Budget:
        """Atualiza orçamento"""
        budget = await self.get_or_create_budget(user, year, month)

        # Validar permissão para editar
        await validate_edit_permission(self.db, user, budget.user_id, budget.ownership_type)

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(budget, field, value)

        await self.db.flush()
        await self.db.refresh(budget)
        return budget

    async def add_budget_item(
        self, user: User, year: int, month: int, data: BudgetItemCreate
    ) -> BudgetItem:
        """Adiciona item ao orçamento"""
        budget = await self.get_or_create_budget(user, year, month)

        # Verificar se categoria já existe no orçamento
        existing = await self.db.execute(
            select(BudgetItem).where(
                BudgetItem.budget_id == budget.id, BudgetItem.category_id == data.category_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Categoria já existe neste orçamento",
            )

        item = BudgetItem(
            budget_id=budget.id,
            category_id=data.category_id,
            planned_amount=data.planned_amount,
            is_fixed=data.is_fixed,
            priority=data.priority,
            notes=data.notes,
        )
        self.db.add(item)

        # Atualizar total do orçamento
        budget.total_expense_planned += data.planned_amount

        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def update_budget_item(
        self, user: User, item_id: int, data: BudgetItemUpdate
    ) -> BudgetItem:
        """Atualiza item do orçamento"""
        result = await self.db.execute(
            select(BudgetItem)
            .join(Budget)
            .where(BudgetItem.id == item_id, Budget.user_id == user.id)
        )
        item = result.scalar_one_or_none()

        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado")

        old_amount = item.planned_amount

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(item, field, value)

        # Atualizar total do orçamento se valor mudou
        if data.planned_amount is not None and data.planned_amount != old_amount:
            budget_result = await self.db.execute(select(Budget).where(Budget.id == item.budget_id))
            budget = budget_result.scalar_one()
            budget.total_expense_planned += data.planned_amount - old_amount

        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def delete_budget_item(self, user: User, item_id: int) -> None:
        """Remove item do orçamento"""
        result = await self.db.execute(
            select(BudgetItem)
            .join(Budget)
            .where(BudgetItem.id == item_id, Budget.user_id == user.id)
        )
        item = result.scalar_one_or_none()

        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado")

        # Atualizar total do orçamento
        budget_result = await self.db.execute(select(Budget).where(Budget.id == item.budget_id))
        budget = budget_result.scalar_one()
        budget.total_expense_planned -= item.planned_amount

        await self.db.delete(item)

    async def copy_budget(
        self,
        user: User,
        target_year: int,
        target_month: int,
        source_year: int,
        source_month: int,
        include_rollover: bool = True,
    ) -> Budget:
        """Copia orçamento de outro mês"""
        # Buscar orçamento fonte
        source_result = await self.db.execute(
            select(Budget).where(
                Budget.user_id == user.id, Budget.year == source_year, Budget.month == source_month
            )
        )
        source = source_result.scalar_one_or_none()

        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Orçamento de {source_month}/{source_year} não encontrado",
            )

        # Verificar se já existe orçamento destino
        existing = await self.db.execute(
            select(Budget).where(
                Budget.user_id == user.id, Budget.year == target_year, Budget.month == target_month
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Já existe orçamento para {target_month}/{target_year}",
            )

        # Criar novo orçamento
        new_budget = Budget(
            user_id=user.id,
            year=target_year,
            month=target_month,
            total_income_planned=source.total_income_planned,
            total_expense_planned=source.total_expense_planned,
            allow_rollover=source.allow_rollover,
        )
        self.db.add(new_budget)
        await self.db.flush()

        # Copiar itens
        for source_item in source.items:
            # Calcular rollover se solicitado
            rollover = Decimal(0)
            if include_rollover and source.allow_rollover:
                # Buscar gasto real da categoria no mês fonte
                start_date = date(source_year, source_month, 1)
                _, last_day = monthrange(source_year, source_month)
                end_date = date(source_year, source_month, last_day)

                expenses = await self._get_expenses_by_category(user, start_date, end_date)
                spent = expenses.get(source_item.category_id, Decimal(0))
                available = source_item.planned_amount + source_item.rollover_amount - spent
                rollover = max(Decimal(0), available)  # Só rola saldo positivo

            new_item = BudgetItem(
                budget_id=new_budget.id,
                category_id=source_item.category_id,
                planned_amount=source_item.planned_amount,
                rollover_amount=rollover,
                is_fixed=source_item.is_fixed,
                priority=source_item.priority,
                notes=source_item.notes,
            )
            self.db.add(new_item)

        await self.db.flush()
        await self.db.refresh(new_budget)
        return new_budget

    async def get_summary(self, user: User, year: int, month: int) -> BudgetSummary:
        """Retorna resumo do orçamento para dashboard"""
        budget_response = await self.get_budget(user, year, month)

        if not budget_response:
            return BudgetSummary(
                year=year,
                month=month,
                total_planned=Decimal(0),
                total_spent=Decimal(0),
                total_available=Decimal(0),
                percentage_used=0,
                days_remaining=0,
                daily_budget_remaining=Decimal(0),
                categories_over_budget=0,
                categories_on_track=0,
            )

        # Calcular dias restantes no mês
        today = date.today()
        _, last_day = monthrange(year, month)
        if today.year == year and today.month == month:
            days_remaining = last_day - today.day
        elif date(year, month, 1) > today:
            days_remaining = last_day
        else:
            days_remaining = 0

        # Calcular orçamento diário restante
        daily_remaining = Decimal(0)
        if days_remaining > 0 and budget_response.total_available > 0:
            daily_remaining = budget_response.total_available / days_remaining

        # Contar categorias por status
        over_budget = sum(
            1 for i in budget_response.items if i.status == BudgetItemStatus.OVERSPENT.value
        )
        depleted = sum(
            1 for i in budget_response.items if i.status == BudgetItemStatus.DEPLETED.value
        )
        warning = sum(
            1 for i in budget_response.items if i.status == BudgetItemStatus.WARNING.value
        )
        on_track = sum(
            1 for i in budget_response.items if i.status == BudgetItemStatus.ON_TRACK.value
        )

        percentage_used = 0.0
        if budget_response.total_expense_planned > 0:
            percentage_used = float(
                budget_response.total_spent / budget_response.total_expense_planned * 100
            )

        return BudgetSummary(
            year=year,
            month=month,
            total_planned=budget_response.total_expense_planned,
            total_spent=budget_response.total_spent,
            total_available=budget_response.total_available,
            percentage_used=percentage_used,
            days_remaining=days_remaining,
            daily_budget_remaining=daily_remaining,
            categories_over_budget=over_budget,
            categories_on_track=on_track,
            categories_warning=warning,
            categories_depleted=depleted,
        )

    async def get_comparison(
        self, user: User, year: int, month: int
    ) -> list[BudgetComparisonResponse]:
        """Compara orçamento planejado vs realizado por categoria"""
        budget_response = await self.get_budget(user, year, month)

        comparisons = []
        for item in budget_response.items:
            difference = item.planned_amount - item.spent_amount

            if item.spent_amount > item.planned_amount:
                item_status = "over"
            elif item.spent_amount < item.planned_amount * Decimal("0.8"):
                item_status = "under"
            else:
                item_status = "on_track"

            comparisons.append(
                BudgetComparisonResponse(
                    category_id=item.category_id,
                    category_name=item.category_name or "",
                    planned=item.planned_amount,
                    actual=item.spent_amount,
                    difference=difference,
                    percentage=item.percentage_used,
                    status=item_status,
                )
            )

        return sorted(comparisons, key=lambda x: x.actual, reverse=True)

    async def _get_expenses_by_category(
        self, user: User, start_date: date, end_date: date
    ) -> dict[int, Decimal]:
        """Retorna gastos por categoria no período (considera household)"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        result = await self.db.execute(
            select(Transaction.category_id, func.sum(Transaction.amount).label("total"))
            .where(
                Transaction.type == TransactionType.EXPENSE.value,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                Transaction.category_id.isnot(None),
                build_ownership_filter(
                    Transaction,
                    Transaction.user_id,
                    Transaction.ownership_type,
                    user.id,
                    household_user_ids,
                    member,
                ),
            )
            .group_by(Transaction.category_id)
        )

        return {row.category_id: row.total for row in result.all()}

    async def _get_total_income(self, user: User, start_date: date, end_date: date) -> Decimal:
        """Retorna total de receitas no período (considera household)"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        result = await self.db.execute(
            select(func.sum(Transaction.amount)).where(
                Transaction.type == TransactionType.INCOME.value,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                build_ownership_filter(
                    Transaction,
                    Transaction.user_id,
                    Transaction.ownership_type,
                    user.id,
                    household_user_ids,
                    member,
                ),
            )
        )
        return result.scalar() or Decimal(0)

    def _calculate_health_score(
        self, planned: Decimal, spent: Decimal, income_planned: Decimal, income_actual: Decimal
    ) -> float:
        """
        Calcula score de saúde do orçamento (0-100)
        Considera: aderência ao planejado, margem, e receita vs despesa
        """
        if planned == 0:
            return 50.0

        score = 100.0

        # Penalizar se gastou mais que o planejado
        if spent > planned:
            overspend_pct = float((spent - planned) / planned * 100)
            score -= min(40, overspend_pct)

        # Penalizar se gastou mais que a receita
        if income_actual > 0 and spent > income_actual:
            deficit_pct = float((spent - income_actual) / income_actual * 100)
            score -= min(30, deficit_pct)

        # Bônus se receita superou o esperado
        if income_planned > 0 and income_actual > income_planned:
            bonus = min(10, float((income_actual - income_planned) / income_planned * 100))
            score += bonus

        return max(0, min(100, score))

    def _calculate_item_status(self, percentage_used: float, available: Decimal) -> str:
        """
        Calcula status dinâmico do item de orçamento (inspirado em Envelopes).

        Returns:
            str: Status do item (on_track, warning, depleted, overspent)
        """
        if available < 0:
            return BudgetItemStatus.OVERSPENT.value
        elif percentage_used >= 100:
            return BudgetItemStatus.DEPLETED.value
        elif percentage_used >= 80:
            return BudgetItemStatus.WARNING.value
        return BudgetItemStatus.ON_TRACK.value

    # ============================================
    # Novos métodos (inspirados em Envelopes)
    # ============================================

    async def transfer(
        self, user: User, year: int, month: int, data: BudgetTransferRequest
    ) -> BudgetTransferResponse:
        """
        Transfere orçamento entre categorias (inspirado em Envelopes).

        "Roll with the Punches" - Ajustar orçamento movendo entre categorias
        quando uma categoria precisa de mais verba.
        """
        if data.from_category_id == data.to_category_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Categoria de origem e destino devem ser diferentes",
            )

        budget = await self.get_or_create_budget(user, year, month)

        # Buscar itens de origem e destino
        from_item = None
        to_item = None
        for item in budget.items:
            if item.category_id == data.from_category_id:
                from_item = item
            if item.category_id == data.to_category_id:
                to_item = item

        if not from_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoria de origem não encontrada no orçamento",
            )
        if not to_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoria de destino não encontrada no orçamento",
            )

        # Calcular saldo disponível da categoria de origem
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        expenses_by_category = await self._get_expenses_by_category(user, start_date, end_date)

        from_spent = expenses_by_category.get(from_item.category_id, Decimal(0))
        from_available = from_item.planned_amount + from_item.rollover_amount - from_spent

        if data.amount > from_available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Saldo insuficiente. Disponível: R$ {from_available:.2f}",
            )

        # Registrar histórico na origem (saída)
        from_history = BudgetItemHistory(
            budget_item_id=from_item.id,
            change_type=BudgetHistoryChangeType.TRANSFER.value,
            amount=-data.amount,
            balance_before=from_available,
            balance_after=from_available - data.amount,
            related_category_id=data.to_category_id,
            notes=data.notes or "Transferido para outra categoria",
        )
        self.db.add(from_history)

        # Calcular saldo disponível da categoria de destino
        to_spent = expenses_by_category.get(to_item.category_id, Decimal(0))
        to_available = to_item.planned_amount + to_item.rollover_amount - to_spent

        # Registrar histórico no destino (entrada)
        to_history = BudgetItemHistory(
            budget_item_id=to_item.id,
            change_type=BudgetHistoryChangeType.TRANSFER.value,
            amount=data.amount,
            balance_before=to_available,
            balance_after=to_available + data.amount,
            related_category_id=data.from_category_id,
            notes=data.notes or "Recebido de outra categoria",
        )
        self.db.add(to_history)

        # Atualizar planned_amount (a transferência afeta o planejado)
        from_item.planned_amount -= data.amount
        to_item.planned_amount += data.amount

        # Atualizar total do orçamento (não muda, apenas redistribuição)
        await self.db.flush()

        # Retornar resposta com itens atualizados
        budget_response = await self.get_budget(user, year, month)
        from_item_response = next(
            (i for i in budget_response.items if i.category_id == data.from_category_id), None
        )
        to_item_response = next(
            (i for i in budget_response.items if i.category_id == data.to_category_id), None
        )

        return BudgetTransferResponse(
            from_item=from_item_response,
            to_item=to_item_response,
            amount=data.amount,
            notes=data.notes,
            created_at=utc_now(),
        )

    async def get_item_history(
        self, user: User, year: int, month: int, category_id: int, limit: int = 50
    ) -> list[BudgetItemHistoryResponse]:
        """
        Retorna histórico de mudanças de um item de orçamento.
        """
        budget = await self.get_or_create_budget(user, year, month)

        # Encontrar o item
        item = next((i for i in budget.items if i.category_id == category_id), None)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoria não encontrada no orçamento",
            )

        # Buscar histórico com related_category
        result = await self.db.execute(
            select(BudgetItemHistory)
            .options(selectinload(BudgetItemHistory.related_category))
            .where(BudgetItemHistory.budget_item_id == item.id)
            .order_by(BudgetItemHistory.created_at.desc())
            .limit(limit)
        )
        history_items = result.scalars().all()

        return [
            BudgetItemHistoryResponse(
                id=h.id,
                budget_item_id=h.budget_item_id,
                transaction_id=h.transaction_id,
                change_type=h.change_type,
                amount=h.amount,
                balance_before=h.balance_before,
                balance_after=h.balance_after,
                related_category_id=h.related_category_id,
                related_category_name=h.related_category.name if h.related_category else None,
                notes=h.notes,
                created_at=h.created_at,
            )
            for h in history_items
        ]

    async def record_expense(
        self,
        user: User,
        category_id: int,
        amount: Decimal,
        transaction_date: date,
        transaction_id: int,
    ) -> BudgetItemHistory | None:
        """
        Registra gasto no orçamento quando transação é criada.

        Chamado pelo TransactionService.create() para manter o histórico
        de consumo do orçamento vinculado às transações.
        """
        year, month = transaction_date.year, transaction_date.month
        budget = await self.get_or_create_budget(user, year, month)

        # Encontrar item da categoria
        item = next((i for i in budget.items if i.category_id == category_id), None)
        if not item:
            return None  # Categoria não tem limite definido

        # Calcular saldo atual
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        expenses = await self._get_expenses_by_category(user, start_date, end_date)
        current_spent = expenses.get(category_id, Decimal(0))
        balance_before = item.planned_amount + item.rollover_amount - current_spent

        # Criar registro de histórico
        history = BudgetItemHistory(
            budget_item_id=item.id,
            transaction_id=transaction_id,
            change_type=BudgetHistoryChangeType.SPEND.value,
            amount=-amount,
            balance_before=balance_before,
            balance_after=balance_before - amount,
            notes=None,
        )
        self.db.add(history)
        await self.db.flush()

        return history

    async def record_refund(
        self,
        user: User,
        category_id: int,
        amount: Decimal,
        transaction_date: date,
        transaction_id: int,
    ) -> BudgetItemHistory | None:
        """
        Registra estorno no orçamento quando transação é deletada/editada.

        Chamado pelo TransactionService.delete/update() para manter o histórico
        de consumo do orçamento atualizado.
        """
        year, month = transaction_date.year, transaction_date.month

        # Verificar se o orçamento existe (não criar se não existir)
        result = await self.db.execute(
            select(Budget).where(
                Budget.user_id == user.id, Budget.year == year, Budget.month == month
            )
        )
        budget = result.scalar_one_or_none()
        if not budget:
            return None

        # Carregar itens do orçamento
        items_result = await self.db.execute(
            select(BudgetItem).where(BudgetItem.budget_id == budget.id)
        )
        items = items_result.scalars().all()

        # Encontrar item da categoria
        item = next((i for i in items if i.category_id == category_id), None)
        if not item:
            return None

        # Calcular saldo atual
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        expenses = await self._get_expenses_by_category(user, start_date, end_date)
        current_spent = expenses.get(category_id, Decimal(0))
        balance_before = item.planned_amount + item.rollover_amount - current_spent

        # Criar registro de histórico
        history = BudgetItemHistory(
            budget_item_id=item.id,
            transaction_id=transaction_id,
            change_type=BudgetHistoryChangeType.REFUND.value,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_before + amount,
            notes="Estorno de transação",
        )
        self.db.add(history)
        await self.db.flush()

        return history
