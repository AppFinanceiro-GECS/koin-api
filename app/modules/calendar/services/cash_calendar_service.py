"""
Cash Calendar Service.

Provides cash flow projections by combining confirmed transactions
with future projections from recurring transactions, invoices, debts, etc.
"""

from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Account,
    CreditCardInvoice,
    Debt,
    DebtStatus,
    InvoiceStatus,
    RecurrenceFrequency,
    RecurringStatus,
    RecurringTransaction,
    Transaction,
    User,
)
from app.modules.calendar.schemas import (
    CashCalendarResponse,
    DailyEntry,
    MajorExpense,
    ProjectionItem,
    ProjectionType,
    RunningBalanceEntry,
    TransactionSummary,
    WeeklySummary,
)
from app.modules.household.utils import get_household_user_ids


class CashCalendarService:
    """Service for cash calendar projections."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_cash_calendar(
        self,
        user: User,
        start_date: date,
        end_date: date,
        include_details: bool = False,
    ) -> CashCalendarResponse:
        """
        Get cash calendar with confirmed transactions and projections.
        """
        today = date.today()

        # Get current balance from accounts
        current_balance = await self._get_current_balance(user)

        # Get confirmed transactions
        confirmed_by_date = await self._get_confirmed_transactions(user, start_date, end_date)

        # Get projections
        projections_by_date = await self._get_projections(user, start_date, end_date)

        # Build daily entries
        daily_entries = []
        running_balance = []
        balance = float(current_balance)

        # Adjust balance to start_date if start_date is in the past
        if start_date < today:
            # Get transactions from start_date to today to calculate starting balance
            past_adjust = await self._get_net_change(user, start_date, today - timedelta(days=1))
            balance -= past_adjust

        shortfall_dates = []
        major_expenses = []

        current = start_date
        while current <= end_date:
            is_past = current < today
            is_today = current == today
            is_weekend = current.weekday() >= 5

            # Get data for this day
            transactions = confirmed_by_date.get(current, [])
            projections = projections_by_date.get(current, [])

            # Calculate totals
            confirmed_income = sum(t.amount for t in transactions if t.type == "income")
            confirmed_expense = sum(t.amount for t in transactions if t.type == "expense")
            projected_income = sum(p.amount for p in projections if p.is_income)
            projected_expense = sum(p.amount for p in projections if not p.is_income)

            net_confirmed = confirmed_income - confirmed_expense
            net_projected = projected_income - projected_expense
            net_total = net_confirmed + net_projected

            # Track major expenses
            for proj in projections:
                if not proj.is_income and proj.amount >= 500:
                    major_expenses.append(
                        MajorExpense(
                            date=current,
                            description=proj.description,
                            amount=proj.amount,
                            type=proj.projection_type,
                            entity_id=proj.entity_id,
                            days_until=(current - today).days,
                        )
                    )

            # Build daily entry
            entry = DailyEntry(
                date=current,
                is_past=is_past,
                is_today=is_today,
                is_weekend=is_weekend,
                confirmed_income=confirmed_income,
                confirmed_expense=confirmed_expense,
                confirmed_count=len(transactions),
                projected_income=projected_income,
                projected_expense=projected_expense,
                projected_count=len(projections),
                net_confirmed=net_confirmed,
                net_projected=net_projected,
                net_total=net_total,
                transactions=transactions if include_details else [],
                projections=projections if include_details else [],
            )
            daily_entries.append(entry)

            # Running balance
            opening_balance = balance
            day_income = confirmed_income + (projected_income if not is_past else 0)
            day_expense = confirmed_expense + (projected_expense if not is_past else 0)
            day_net = day_income - day_expense
            closing_balance = opening_balance + day_net

            if closing_balance < 0:
                shortfall_dates.append(current)

            running_balance.append(
                RunningBalanceEntry(
                    date=current,
                    opening_balance=opening_balance,
                    income=day_income,
                    expense=day_expense,
                    net=day_net,
                    closing_balance=closing_balance,
                    is_projected=not is_past,
                    is_negative=closing_balance < 0,
                )
            )

            balance = closing_balance
            current += timedelta(days=1)

        # Sort major expenses by amount
        major_expenses.sort(key=lambda x: x.amount, reverse=True)
        major_expenses = major_expenses[:5]  # Top 5

        # Calculate totals
        total_confirmed_income = sum(e.confirmed_income for e in daily_entries)
        total_confirmed_expense = sum(e.confirmed_expense for e in daily_entries)
        total_projected_income = sum(e.projected_income for e in daily_entries)
        total_projected_expense = sum(e.projected_expense for e in daily_entries)

        return CashCalendarResponse(
            start_date=start_date,
            end_date=end_date,
            current_balance=float(current_balance),
            projected_end_balance=balance,
            shortfall_dates=shortfall_dates,
            major_expenses=major_expenses,
            daily_entries=daily_entries,
            running_balance=running_balance,
            total_confirmed_income=total_confirmed_income,
            total_confirmed_expense=total_confirmed_expense,
            total_projected_income=total_projected_income,
            total_projected_expense=total_projected_expense,
        )

    async def get_weekly_summary(
        self,
        user: User,
        year: int,
        week: int,
        compare_previous: bool = True,
    ) -> WeeklySummary:
        """Get summary for a specific week."""
        # Calculate week dates (ISO week)
        start_date = date.fromisocalendar(year, week, 1)
        end_date = date.fromisocalendar(year, week, 7)

        # Get transactions for this week
        transactions = await self._get_confirmed_transactions_flat(user, start_date, end_date)

        total_income = sum(t.amount for t in transactions if t.type == "income")
        total_expense = sum(t.amount for t in transactions if t.type == "expense")

        # Get top expense categories
        category_expenses = {}
        for t in transactions:
            if t.type == "expense" and t.category_name:
                category_expenses[t.category_name] = (
                    category_expenses.get(t.category_name, 0) + t.amount
                )

        top_categories = sorted(
            [{"name": k, "amount": v} for k, v in category_expenses.items()],
            key=lambda x: x["amount"],
            reverse=True,
        )[:5]

        # Compare with previous week
        income_change = None
        expense_change = None
        if compare_previous:
            prev_start = start_date - timedelta(weeks=1)
            prev_end = end_date - timedelta(weeks=1)
            prev_transactions = await self._get_confirmed_transactions_flat(
                user, prev_start, prev_end
            )

            prev_income = sum(t.amount for t in prev_transactions if t.type == "income")
            prev_expense = sum(t.amount for t in prev_transactions if t.type == "expense")

            if prev_income > 0:
                income_change = ((total_income - prev_income) / prev_income) * 100
            if prev_expense > 0:
                expense_change = ((total_expense - prev_expense) / prev_expense) * 100

        return WeeklySummary(
            year=year,
            week=week,
            start_date=start_date,
            end_date=end_date,
            total_income=total_income,
            total_expense=total_expense,
            net=total_income - total_expense,
            income_change_percent=income_change,
            expense_change_percent=expense_change,
            daily_average_expense=total_expense / 7 if total_expense > 0 else 0,
            top_expense_categories=top_categories,
        )

    async def _get_current_balance(self, user: User) -> Decimal:
        """Get total balance from active accounts."""
        household_ids = await get_household_user_ids(self.db, user)

        query = select(func.coalesce(func.sum(Account.balance), 0)).where(
            Account.user_id.in_(household_ids),
            Account.is_active == True,
            Account.type.in_(["checking", "savings", "wallet", "bank"]),
        )
        result = await self.db.execute(query)
        return result.scalar() or Decimal(0)

    async def _get_net_change(self, user: User, start_date: date, end_date: date) -> float:
        """Get net change in balance for a period."""
        household_ids = await get_household_user_ids(self.db, user)

        query = select(
            func.coalesce(
                func.sum(
                    func.case(
                        (Transaction.type == "income", Transaction.amount),
                        else_=-Transaction.amount,
                    )
                ),
                0,
            )
        ).where(
            Transaction.user_id.in_(household_ids),
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
        result = await self.db.execute(query)
        return float(result.scalar() or 0)

    async def _get_confirmed_transactions(
        self, user: User, start_date: date, end_date: date
    ) -> dict[date, list[TransactionSummary]]:
        """Get confirmed transactions grouped by date."""
        household_ids = await get_household_user_ids(self.db, user)

        query = (
            select(Transaction)
            .options(
                selectinload(Transaction.category),
                selectinload(Transaction.account),
            )
            .where(
                Transaction.user_id.in_(household_ids),
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            )
            .order_by(Transaction.date)
        )
        result = await self.db.execute(query)
        transactions = result.scalars().all()

        grouped = {}
        for t in transactions:
            summary = TransactionSummary(
                id=t.id,
                description=t.description or "",
                amount=float(t.amount),
                type=t.type,
                category_name=t.category.name if t.category else None,
                category_icon=t.category.icon if t.category else None,
                account_name=t.account.name if t.account else None,
                is_paid=t.is_paid,
            )
            if t.date not in grouped:
                grouped[t.date] = []
            grouped[t.date].append(summary)

        return grouped

    async def _get_confirmed_transactions_flat(
        self, user: User, start_date: date, end_date: date
    ) -> list[TransactionSummary]:
        """Get confirmed transactions as flat list."""
        grouped = await self._get_confirmed_transactions(user, start_date, end_date)
        return [t for transactions in grouped.values() for t in transactions]

    async def _get_projections(
        self, user: User, start_date: date, end_date: date
    ) -> dict[date, list[ProjectionItem]]:
        """Get all projections for the period."""
        today = date.today()
        # Only project for future dates
        proj_start = max(start_date, today)

        if proj_start > end_date:
            return {}

        projections = {}

        # Get recurring transaction projections
        recurring_projs = await self._project_recurring_transactions(user, proj_start, end_date)
        for d, items in recurring_projs.items():
            if d not in projections:
                projections[d] = []
            projections[d].extend(items)

        # Get invoice due date projections
        invoice_projs = await self._project_invoices(user, proj_start, end_date)
        for d, items in invoice_projs.items():
            if d not in projections:
                projections[d] = []
            projections[d].extend(items)

        # Get debt payment projections
        debt_projs = await self._project_debt_payments(user, proj_start, end_date)
        for d, items in debt_projs.items():
            if d not in projections:
                projections[d] = []
            projections[d].extend(items)

        # Parcelas futuras NAO sao projetadas aqui: elas ja existem como Transactions
        # futuras (is_paid=false) geradas pela InstallmentSeries e entram pela query
        # de transacoes do periodo — projeta-las de novo duplicaria os valores.

        return projections

    async def _project_recurring_transactions(
        self, user: User, start_date: date, end_date: date
    ) -> dict[date, list[ProjectionItem]]:
        """Project future occurrences of recurring transactions."""
        household_ids = await get_household_user_ids(self.db, user)

        query = (
            select(RecurringTransaction)
            .options(
                selectinload(RecurringTransaction.category),
                selectinload(RecurringTransaction.account),
            )
            .where(
                RecurringTransaction.user_id.in_(household_ids),
                RecurringTransaction.status == RecurringStatus.ACTIVE.value,
            )
        )
        result = await self.db.execute(query)
        recurrings = result.scalars().all()

        projections = {}

        for r in recurrings:
            # Generate future dates for this recurring
            dates = self._generate_future_dates(
                r.frequency,
                r.next_due_date,
                r.end_date,
                r.day_of_month,
                r.day_of_week,
                start_date,
                end_date,
            )

            for d in dates:
                item = ProjectionItem(
                    projection_type=ProjectionType.RECURRING,
                    description=r.name,
                    amount=float(r.amount),
                    is_income=r.type == "income",
                    category_name=r.category.name if r.category else None,
                    category_icon=r.category.icon if r.category else None,
                    account_name=r.account.name if r.account else None,
                    entity_type="recurring",
                    entity_id=r.id,
                    confidence=1.0,
                )
                if d not in projections:
                    projections[d] = []
                projections[d].append(item)

        return projections

    async def _project_invoices(
        self, user: User, start_date: date, end_date: date
    ) -> dict[date, list[ProjectionItem]]:
        """Project credit card invoice due dates."""
        household_ids = await get_household_user_ids(self.db, user)

        query = (
            select(CreditCardInvoice)
            .options(selectinload(CreditCardInvoice.credit_card))
            .where(
                CreditCardInvoice.user_id.in_(household_ids),
                CreditCardInvoice.status.in_(
                    [InvoiceStatus.OPEN.value, InvoiceStatus.CLOSED.value]
                ),
                CreditCardInvoice.due_date >= start_date,
                CreditCardInvoice.due_date <= end_date,
            )
        )
        result = await self.db.execute(query)
        invoices = result.scalars().all()

        projections = {}
        for inv in invoices:
            remaining = float(inv.total_amount - inv.paid_amount)
            if remaining <= 0:
                continue

            item = ProjectionItem(
                projection_type=ProjectionType.INVOICE,
                description=f"Fatura {inv.credit_card.name if inv.credit_card else 'Cartão'}",
                amount=remaining,
                is_income=False,
                entity_type="invoice",
                entity_id=inv.id,
                confidence=1.0,
            )
            if inv.due_date not in projections:
                projections[inv.due_date] = []
            projections[inv.due_date].append(item)

        return projections

    async def _project_debt_payments(
        self, user: User, start_date: date, end_date: date
    ) -> dict[date, list[ProjectionItem]]:
        """Project debt payments."""
        household_ids = await get_household_user_ids(self.db, user)

        query = select(Debt).where(
            Debt.user_id.in_(household_ids),
            Debt.status == DebtStatus.ACTIVE.value,
            Debt.due_day.isnot(None),
        )
        result = await self.db.execute(query)
        debts = result.scalars().all()

        projections = {}

        for debt in debts:
            if not debt.due_day or debt.minimum_payment <= 0:
                continue

            # Generate monthly due dates
            current = start_date.replace(day=min(debt.due_day, 28))
            if current < start_date:
                current = (current + relativedelta(months=1)).replace(day=min(debt.due_day, 28))

            while current <= end_date:
                item = ProjectionItem(
                    projection_type=ProjectionType.DEBT,
                    description=f"Parcela: {debt.name}",
                    amount=float(debt.minimum_payment),
                    is_income=False,
                    entity_type="debt",
                    entity_id=debt.id,
                    confidence=1.0,
                )
                if current not in projections:
                    projections[current] = []
                projections[current].append(item)

                current = (current + relativedelta(months=1)).replace(day=min(debt.due_day, 28))

        return projections

    def _generate_future_dates(
        self,
        frequency: str,
        next_due: date,
        end_date_limit: date | None,
        day_of_month: int | None,
        day_of_week: int | None,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """Generate future occurrence dates for a recurring transaction."""
        dates = []
        current = next_due

        # Limit to end_date_limit if set
        effective_end = end_date
        if end_date_limit:
            effective_end = min(end_date, end_date_limit)

        while current <= effective_end:
            if current >= start_date:
                dates.append(current)

            # Calculate next date
            if frequency == RecurrenceFrequency.DAILY.value:
                current = current + timedelta(days=1)
            elif frequency == RecurrenceFrequency.WEEKLY.value:
                current = current + timedelta(weeks=1)
            elif frequency == RecurrenceFrequency.MONTHLY.value:
                current = current + relativedelta(months=1)
                if day_of_month:
                    try:
                        current = current.replace(day=min(day_of_month, 28))
                    except ValueError:
                        current = current.replace(day=28)
            elif frequency == RecurrenceFrequency.YEARLY.value:
                current = current + relativedelta(years=1)
            else:
                current = current + relativedelta(months=1)

        return dates
