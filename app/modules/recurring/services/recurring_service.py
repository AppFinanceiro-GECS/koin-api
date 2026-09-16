from __future__ import annotations

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Account,
    Category,
    RecurrenceFrequency,
    RecurringStatus,
    RecurringTransaction,
    Transaction,
    User,
)
from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import CreditCardInvoice
from app.modules.credit_cards.services.invoice_service import InvoiceService
from app.modules.household.utils import (
    build_ownership_filter,
    get_household_member,
    get_household_user_ids,
    validate_create_permission,
    validate_delete_permission,
    validate_edit_permission,
)
from app.modules.recurring.schemas.recurring import (
    RecurringCreate,
    RecurringResponse,
    RecurringSummary,
    RecurringUpdate,
)


class RecurringTransactionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _calculate_next_due_date(
        self,
        frequency: str,
        start_date: date,
        last_generated: date | None,
        day_of_month: int | None,
        day_of_week: int | None,
    ) -> date:
        """Calcula a próxima data de vencimento"""
        today = date.today()
        base_date = last_generated if last_generated else start_date - timedelta(days=1)

        if frequency == RecurrenceFrequency.DAILY.value:
            next_date = base_date + timedelta(days=1)
        elif frequency == RecurrenceFrequency.WEEKLY.value:
            next_date = base_date + timedelta(weeks=1)
            if day_of_week is not None:
                # Ajustar para o dia da semana correto
                days_ahead = day_of_week - next_date.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                next_date = next_date + timedelta(days=days_ahead)
        elif frequency == RecurrenceFrequency.MONTHLY.value:
            next_date = base_date + relativedelta(months=1)
            if day_of_month:
                # Ajustar para o dia do mês (cuidado com meses com menos dias)
                try:
                    next_date = next_date.replace(day=min(day_of_month, 28))
                except ValueError:
                    next_date = next_date.replace(day=28)
        elif frequency == RecurrenceFrequency.YEARLY.value:
            next_date = base_date + relativedelta(years=1)
        else:
            next_date = base_date + relativedelta(months=1)

        # Se a próxima data já passou, avançar
        while next_date < today:
            if frequency == RecurrenceFrequency.DAILY.value:
                next_date += timedelta(days=1)
            elif frequency == RecurrenceFrequency.WEEKLY.value:
                next_date += timedelta(weeks=1)
            elif frequency == RecurrenceFrequency.MONTHLY.value:
                next_date += relativedelta(months=1)
            elif frequency == RecurrenceFrequency.YEARLY.value:
                next_date += relativedelta(years=1)

        return next_date

    async def _get_credit_card_from_account(
        self, user_id: int, account_id: int
    ) -> CreditCard | None:
        """Verifica se a conta e do tipo credit_card e retorna o CreditCard."""
        account_result = await self.db.execute(select(Account).where(Account.id == account_id))
        account = account_result.scalar_one_or_none()

        if not account or account.type != "credit_card":
            return None

        cc_result = await self.db.execute(
            select(CreditCard).where(CreditCard.account_id == account_id)
        )
        return cc_result.scalar_one_or_none()

    async def create(self, user: User, data: RecurringCreate) -> RecurringTransaction:
        """Cria uma nova transação recorrente"""
        # Validate ownership permissions
        await validate_create_permission(self.db, user, data.ownership_type.value)

        # Verificar se a conta pertence ao usuário
        account = await self.db.scalar(
            select(Account).where(Account.id == data.account_id, Account.user_id == user.id)
        )
        if not account:
            raise ValueError("Conta não encontrada")

        # Verificar categoria se fornecida
        if data.category_id:
            category = await self.db.scalar(
                select(Category).where(Category.id == data.category_id, Category.user_id == user.id)
            )
            if not category:
                raise ValueError("Categoria não encontrada")

        # Calcular próxima data
        next_due = self._calculate_next_due_date(
            data.frequency.value, data.start_date, None, data.day_of_month, data.day_of_week
        )

        recurring = RecurringTransaction(
            user_id=user.id,
            account_id=data.account_id,
            category_id=data.category_id,
            name=data.name,
            description=data.description,
            amount=data.amount,
            type=data.type.value,
            payment_method=data.payment_method.value if data.payment_method else None,
            frequency=data.frequency.value,
            day_of_month=data.day_of_month,
            day_of_week=data.day_of_week,
            start_date=data.start_date,
            end_date=data.end_date,
            next_due_date=next_due,
            status=RecurringStatus.ACTIVE.value,
            ownership_type=data.ownership_type.value,
        )

        self.db.add(recurring)
        await self.db.commit()
        await self.db.refresh(recurring)
        return recurring

    async def list(self, user: User, include_inactive: bool = False) -> list[RecurringResponse]:
        """Lista transações recorrentes do usuário"""
        # Get household context
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        # Build ownership filter
        ownership_filter = build_ownership_filter(
            RecurringTransaction,
            RecurringTransaction.user_id,
            RecurringTransaction.ownership_type,
            user.id,
            household_user_ids,
            member,
        )

        query = (
            select(RecurringTransaction)
            .options(
                selectinload(RecurringTransaction.account),
                selectinload(RecurringTransaction.category),
            )
            .where(ownership_filter)
            .order_by(RecurringTransaction.next_due_date)
        )

        if not include_inactive:
            query = query.where(RecurringTransaction.status != RecurringStatus.CANCELLED.value)

        result = await self.db.execute(query)
        items = result.scalars().all()

        return [
            RecurringResponse(
                id=r.id,
                name=r.name,
                description=r.description,
                amount=float(r.amount),
                type=r.type,
                payment_method=r.payment_method,
                account_id=r.account_id,
                account_name=r.account.name if r.account else None,
                category_id=r.category_id,
                category_name=r.category.name if r.category else None,
                frequency=r.frequency,
                day_of_month=r.day_of_month,
                day_of_week=r.day_of_week,
                start_date=r.start_date,
                end_date=r.end_date,
                status=r.status,
                ownership_type=r.ownership_type,
                last_generated_date=r.last_generated_date,
                next_due_date=r.next_due_date,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in items
        ]

    async def get_by_id(self, user: User, recurring_id: int) -> RecurringTransaction | None:
        """Busca uma transação recorrente por ID"""
        result = await self.db.execute(
            select(RecurringTransaction)
            .options(
                selectinload(RecurringTransaction.account),
                selectinload(RecurringTransaction.category),
            )
            .where(RecurringTransaction.id == recurring_id, RecurringTransaction.user_id == user.id)
        )
        return result.scalar_one_or_none()

    async def update(
        self, user: User, recurring_id: int, data: RecurringUpdate
    ) -> RecurringTransaction | None:
        """Atualiza uma transação recorrente"""
        recurring = await self.get_by_id(user, recurring_id)
        if not recurring:
            return None

        # Validate edit permissions
        await validate_edit_permission(self.db, user, recurring.user_id, recurring.ownership_type)

        update_data = data.model_dump(exclude_unset=True)

        # Verificar conta se alterada
        if "account_id" in update_data:
            account = await self.db.scalar(
                select(Account).where(
                    Account.id == update_data["account_id"], Account.user_id == user.id
                )
            )
            if not account:
                raise ValueError("Conta não encontrada")

        # Verificar categoria se alterada
        if "category_id" in update_data and update_data["category_id"]:
            category = await self.db.scalar(
                select(Category).where(
                    Category.id == update_data["category_id"], Category.user_id == user.id
                )
            )
            if not category:
                raise ValueError("Categoria não encontrada")

        # Aplicar atualizações
        for field, value in update_data.items():
            if field == "type" and value:
                setattr(recurring, field, value.value if hasattr(value, "value") else value)
            elif field == "frequency" and value:
                setattr(recurring, field, value.value if hasattr(value, "value") else value)
            elif field == "status" and value:
                setattr(recurring, field, value.value if hasattr(value, "value") else value)
            elif field == "payment_method" and value:
                setattr(recurring, field, value.value if hasattr(value, "value") else value)
            else:
                setattr(recurring, field, value)

        # Recalcular próxima data se frequência ou dia mudou
        if any(k in update_data for k in ["frequency", "day_of_month", "day_of_week"]):
            recurring.next_due_date = self._calculate_next_due_date(
                recurring.frequency,
                recurring.start_date,
                recurring.last_generated_date,
                recurring.day_of_month,
                recurring.day_of_week,
            )

        await self.db.commit()
        await self.db.refresh(recurring)
        return recurring

    async def delete(self, user: User, recurring_id: int) -> bool:
        """Remove uma transação recorrente"""
        recurring = await self.get_by_id(user, recurring_id)
        if not recurring:
            return False

        # Validate delete permissions
        await validate_delete_permission(self.db, user, recurring.user_id, recurring.ownership_type)

        await self.db.delete(recurring)
        await self.db.commit()
        return True

    async def pause(
        self,
        user: User,
        recurring_id: int,
        remove_projected: bool = True,
    ) -> RecurringTransaction | None:
        """Pausa uma recorrencia e opcionalmente remove transacoes projetadas."""
        recurring = await self.get_by_id(user, recurring_id)
        if not recurring:
            return None

        recurring.status = RecurringStatus.PAUSED.value

        # Remover transacoes projetadas futuras
        if remove_projected:
            proj_result = await self.db.execute(
                select(Transaction).where(
                    Transaction.recurring_id == recurring_id,
                    Transaction.is_paid == False,
                    Transaction.date >= date.today(),
                )
            )
            projected = proj_result.scalars().all()

            invoice_ids = set()
            for tx in projected:
                if tx.invoice_id:
                    invoice_ids.add(tx.invoice_id)
                await self.db.delete(tx)

            # Atualizar faturas
            if invoice_ids:
                invoice_service = InvoiceService(self.db)
                inv_result = await self.db.execute(
                    select(CreditCardInvoice).where(CreditCardInvoice.id.in_(invoice_ids))
                )
                for invoice in inv_result.scalars().all():
                    await invoice_service.update_invoice_total(invoice)

        await self.db.commit()
        await self.db.refresh(recurring)
        return recurring

    async def resume(self, user: User, recurring_id: int) -> RecurringTransaction | None:
        """Retoma uma transação recorrente pausada"""
        recurring = await self.get_by_id(user, recurring_id)
        if not recurring:
            return None

        recurring.status = RecurringStatus.ACTIVE.value
        # Recalcular próxima data
        recurring.next_due_date = self._calculate_next_due_date(
            recurring.frequency,
            recurring.start_date,
            recurring.last_generated_date,
            recurring.day_of_month,
            recurring.day_of_week,
        )
        await self.db.commit()
        await self.db.refresh(recurring)
        return recurring

    async def get_summary(self, user: User) -> RecurringSummary:
        """Retorna resumo das transações recorrentes"""
        result = await self.db.execute(
            select(RecurringTransaction).where(RecurringTransaction.user_id == user.id)
        )
        items = result.scalars().all()

        total_expenses = 0.0
        total_income = 0.0
        active_count = 0
        paused_count = 0

        for r in items:
            if r.status == RecurringStatus.CANCELLED.value:
                continue

            # Calcular valor mensal equivalente
            monthly_amount = float(r.amount)
            if r.frequency == RecurrenceFrequency.DAILY.value:
                monthly_amount *= 30
            elif r.frequency == RecurrenceFrequency.WEEKLY.value:
                monthly_amount *= 4.33
            elif r.frequency == RecurrenceFrequency.YEARLY.value:
                monthly_amount /= 12

            if r.type == "expense":
                total_expenses += monthly_amount
            else:
                total_income += monthly_amount

            if r.status == RecurringStatus.ACTIVE.value:
                active_count += 1
            elif r.status == RecurringStatus.PAUSED.value:
                paused_count += 1

        return RecurringSummary(
            total_monthly_expenses=round(total_expenses, 2),
            total_monthly_income=round(total_income, 2),
            active_count=active_count,
            paused_count=paused_count,
        )

    async def generate_pending_transactions(self, user: User) -> list[Transaction]:
        """Gera transações para recorrências pendentes até hoje"""
        today = date.today()
        generated = []
        invoice_ids_to_update = set()

        result = await self.db.execute(
            select(RecurringTransaction).where(
                RecurringTransaction.user_id == user.id,
                RecurringTransaction.status == RecurringStatus.ACTIVE.value,
                RecurringTransaction.next_due_date <= today,
            )
        )
        pending = result.scalars().all()

        for recurring in pending:
            # Verificar se já passou da data final
            if recurring.end_date and recurring.next_due_date > recurring.end_date:
                recurring.status = RecurringStatus.CANCELLED.value
                continue

            # Verificar se a conta é de cartão de crédito
            credit_card = await self._get_credit_card_from_account(user.id, recurring.account_id)
            credit_card_id = None
            invoice_id = None
            is_paid = True  # Default: transação paga (contas normais)

            if credit_card:
                # Conta é de cartão de crédito - vincular à fatura
                credit_card_id = credit_card.id
                is_paid = False  # Transações de cartão são "não pagas" até pagar a fatura

                # Calcular período da fatura
                invoice_service = InvoiceService(self.db)
                period = invoice_service.calculate_invoice_period(
                    credit_card, recurring.next_due_date
                )

                # Obter ou criar fatura
                invoice = await invoice_service.get_or_create_invoice(
                    user=user,
                    credit_card=credit_card,
                    reference_month=period["reference_month"],
                    reference_year=period["reference_year"],
                    closing_date=period["closing_date"],
                    due_date=period["due_date"],
                )
                invoice_id = invoice.id
                invoice_ids_to_update.add(invoice_id)

            # Criar transação herdando ownership_type da recorrência
            transaction = Transaction(
                user_id=user.id,
                account_id=recurring.account_id,
                category_id=recurring.category_id,
                credit_card_id=credit_card_id,
                invoice_id=invoice_id,
                type=recurring.type,
                payment_method=recurring.payment_method,
                amount=recurring.amount,
                date=recurring.next_due_date,
                description=recurring.name,
                notes=f"Gerado automaticamente de: {recurring.name}",
                is_recurring=True,
                is_fixed=True,
                is_paid=is_paid,
                recurring_id=recurring.id,
                ownership_type=recurring.ownership_type,
            )
            self.db.add(transaction)
            generated.append(transaction)

            # Atualizar recorrência
            recurring.last_generated_date = recurring.next_due_date
            recurring.next_due_date = self._calculate_next_due_date(
                recurring.frequency,
                recurring.start_date,
                recurring.last_generated_date,
                recurring.day_of_month,
                recurring.day_of_week,
            )

        await self.db.flush()

        # Atualizar totais das faturas afetadas
        if invoice_ids_to_update:
            invoice_service = InvoiceService(self.db)
            inv_result = await self.db.execute(
                select(CreditCardInvoice).where(CreditCardInvoice.id.in_(invoice_ids_to_update))
            )
            for invoice in inv_result.scalars().all():
                await invoice_service.update_invoice_total(invoice)

        await self.db.commit()
        return generated

    async def cancel(
        self,
        user: User,
        recurring_id: int,
        cancel_from_month: int | None = None,
        cancel_from_year: int | None = None,
        remove_projected: bool = True,
    ) -> dict | None:
        """
        Cancela uma recorrencia e opcionalmente remove transacoes projetadas.

        Args:
            user: Usuario
            recurring_id: ID da recorrencia
            cancel_from_month: Mes a partir do qual cancelar (None = imediato)
            cancel_from_year: Ano a partir do qual cancelar
            remove_projected: Se True, remove transacoes projetadas (is_paid=False)

        Returns:
            Dict com estatisticas do cancelamento ou None se nao encontrada
        """
        recurring = await self.get_by_id(user, recurring_id)
        if not recurring:
            return None

        await validate_edit_permission(self.db, user, recurring.user_id, recurring.ownership_type)

        result = {
            "recurring_id": recurring_id,
            "status": "cancelled",
            "projected_removed": 0,
            "invoices_updated": [],
        }

        # Definir end_date se especificado
        if cancel_from_month and cancel_from_year:
            # Cancelar a partir de uma data especifica
            end_date = date(cancel_from_year, cancel_from_month, 1) - timedelta(days=1)
            recurring.end_date = end_date

            # Se a data de termino ja passou, marcar como cancelado
            if end_date < date.today():
                recurring.status = RecurringStatus.CANCELLED.value
        else:
            # Cancelamento imediato
            recurring.status = RecurringStatus.CANCELLED.value
            recurring.end_date = date.today()

        # Remover transacoes projetadas (is_paid=False)
        if remove_projected:
            # Determinar data de corte
            if cancel_from_month and cancel_from_year:
                cutoff_date = date(cancel_from_year, cancel_from_month, 1)
            else:
                cutoff_date = date.today()

            # Buscar transacoes projetadas desta recorrencia
            proj_result = await self.db.execute(
                select(Transaction).where(
                    Transaction.recurring_id == recurring_id,
                    Transaction.is_paid == False,
                    Transaction.date >= cutoff_date,
                )
            )
            projected_transactions = proj_result.scalars().all()

            # Coletar invoice_ids afetados
            invoice_ids = set()
            for tx in projected_transactions:
                if tx.invoice_id:
                    invoice_ids.add(tx.invoice_id)
                await self.db.delete(tx)

            result["projected_removed"] = len(projected_transactions)

            # Atualizar totais das faturas afetadas
            if invoice_ids:
                invoice_service = InvoiceService(self.db)
                inv_result = await self.db.execute(
                    select(CreditCardInvoice).where(CreditCardInvoice.id.in_(invoice_ids))
                )
                for invoice in inv_result.scalars().all():
                    await invoice_service.update_invoice_total(invoice)
                    result["invoices_updated"].append(
                        {
                            "id": invoice.id,
                            "month": invoice.reference_month,
                            "year": invoice.reference_year,
                        }
                    )

        await self.db.commit()
        return result
