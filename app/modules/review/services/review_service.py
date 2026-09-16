"""
Weekly Review Service.

Provides data for guided weekly financial reviews.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Budget,
    BudgetItem,
    Category,
    CreditCardInvoice,
    Goal,
    RecurringTransaction,
    Transaction,
    User,
)
from app.modules.review.schemas import (
    BudgetCategoryComparison,
    BudgetComparison,
    GoalProgress,
    UncategorizedTransaction,
    UpcomingItem,
    WeeklyReviewResponse,
    WeekSummary,
)

logger = logging.getLogger(__name__)


class WeeklyReviewService:
    """Service for weekly financial reviews."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_weekly_review(self, user: User, year: int, week: int) -> WeeklyReviewResponse:
        """Get comprehensive weekly review data."""
        # Calculate week boundaries
        week_start = self._get_week_start(year, week)
        week_end = week_start + timedelta(days=6)

        # Get data in parallel
        week_summary = await self._get_week_summary(user, year, week, week_start, week_end)
        uncategorized = await self._get_uncategorized_transactions(user, week_start, week_end)
        budget_comparison = await self._get_budget_comparison(
            user, week_start.year, week_start.month
        )
        goal_progress = await self._get_goal_progress(user, week_start, week_end)
        upcoming_items = await self._get_upcoming_items(user, week_end)
        tips = self._generate_tips(week_summary, budget_comparison, uncategorized)

        return WeeklyReviewResponse(
            week_summary=week_summary,
            uncategorized_transactions=uncategorized,
            uncategorized_count=len(uncategorized),
            budget_comparison=budget_comparison,
            goal_progress=goal_progress,
            upcoming_items=upcoming_items,
            review_tips=tips,
            last_review_date=None,  # TODO: Track review completions
            streak_weeks=0,
        )

    def _get_week_start(self, year: int, week: int) -> date:
        """Get the start date (Monday) of a given ISO week."""
        jan_4 = date(year, 1, 4)
        start_of_week_1 = jan_4 - timedelta(days=jan_4.weekday())
        return start_of_week_1 + timedelta(weeks=week - 1)

    async def _get_week_summary(
        self, user: User, year: int, week: int, week_start: date, week_end: date
    ) -> WeekSummary:
        """Get summary of the week's transactions."""
        # Current week transactions
        result = await self.session.execute(
            select(
                func.sum(
                    func.case((Transaction.type == "income", Transaction.amount), else_=Decimal(0))
                ).label("income"),
                func.count(func.case((Transaction.type == "income", 1), else_=None)).label(
                    "income_count"
                ),
                func.sum(
                    func.case((Transaction.type == "expense", Transaction.amount), else_=Decimal(0))
                ).label("expenses"),
                func.count(func.case((Transaction.type == "expense", 1), else_=None)).label(
                    "expenses_count"
                ),
            ).where(
                Transaction.user_id == user.id,
                Transaction.date >= week_start,
                Transaction.date <= week_end,
                Transaction.is_projected == False,
            )
        )
        row = result.one()

        total_income = row.income or Decimal(0)
        income_count = row.income_count or 0
        total_expenses = row.expenses or Decimal(0)
        expenses_count = row.expenses_count or 0
        net_balance = total_income - total_expenses

        # Previous week for comparison
        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = week_end - timedelta(days=7)

        prev_result = await self.session.execute(
            select(
                func.sum(
                    func.case((Transaction.type == "income", Transaction.amount), else_=Decimal(0))
                ).label("income"),
                func.sum(
                    func.case((Transaction.type == "expense", Transaction.amount), else_=Decimal(0))
                ).label("expenses"),
            ).where(
                Transaction.user_id == user.id,
                Transaction.date >= prev_week_start,
                Transaction.date <= prev_week_end,
                Transaction.is_projected == False,
            )
        )
        prev_row = prev_result.one()
        prev_income = prev_row.income or Decimal(0)
        prev_expenses = prev_row.expenses or Decimal(0)
        prev_net = prev_income - prev_expenses

        # Calculate percentages
        income_vs_prev = None
        if prev_income > 0:
            income_vs_prev = ((total_income - prev_income) / prev_income) * 100

        expenses_vs_prev = None
        if prev_expenses > 0:
            expenses_vs_prev = ((total_expenses - prev_expenses) / prev_expenses) * 100

        net_vs_prev = None
        if prev_net != 0:
            net_vs_prev = ((net_balance - prev_net) / abs(prev_net)) * 100

        # Daily average
        days_in_week = 7
        daily_avg = total_expenses / days_in_week if days_in_week > 0 else Decimal(0)

        # Top categories
        top_cats = await self._get_top_expense_categories(user, week_start, week_end, limit=5)

        return WeekSummary(
            week_start=week_start,
            week_end=week_end,
            week_number=week,
            year=year,
            total_income=total_income,
            income_count=income_count,
            income_vs_previous=income_vs_prev,
            total_expenses=total_expenses,
            expenses_count=expenses_count,
            expenses_vs_previous=expenses_vs_prev,
            net_balance=net_balance,
            net_vs_previous=net_vs_prev,
            daily_average_expense=daily_avg,
            top_expense_categories=top_cats,
        )

    async def _get_top_expense_categories(
        self, user: User, start_date: date, end_date: date, limit: int = 5
    ) -> list[dict]:
        """Get top expense categories for the period."""
        result = await self.session.execute(
            select(Category.id, Category.name, func.sum(Transaction.amount).label("total"))
            .join(Transaction, Transaction.category_id == Category.id)
            .where(
                Transaction.user_id == user.id,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                Transaction.type == "expense",
                Transaction.is_projected == False,
            )
            .group_by(Category.id, Category.name)
            .order_by(func.sum(Transaction.amount).desc())
            .limit(limit)
        )
        rows = result.all()

        return [{"id": row.id, "name": row.name, "total": float(row.total)} for row in rows]

    async def _get_uncategorized_transactions(
        self, user: User, start_date: date, end_date: date
    ) -> list[UncategorizedTransaction]:
        """Get transactions without categories."""
        result = await self.session.execute(
            select(Transaction)
            .options(selectinload(Transaction.account))
            .where(
                Transaction.user_id == user.id,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                Transaction.category_id == None,
                Transaction.is_projected == False,
            )
            .order_by(Transaction.date.desc())
            .limit(50)
        )
        transactions = result.scalars().all()

        return [
            UncategorizedTransaction(
                id=t.id,
                date=t.date,
                description=t.description or "",
                amount=t.amount,
                type=t.type,
                account_name=t.account.name if t.account else "N/A",
            )
            for t in transactions
        ]

    async def _get_budget_comparison(
        self, user: User, year: int, month: int
    ) -> BudgetComparison | None:
        """Get budget vs actual comparison."""
        # Get budget
        result = await self.session.execute(
            select(Budget)
            .options(selectinload(Budget.items).selectinload(BudgetItem.category))
            .where(
                Budget.user_id == user.id,
                Budget.year == year,
                Budget.month == month,
            )
        )
        budget = result.scalar_one_or_none()

        if not budget or not budget.items:
            return None

        # Get actual spending per category
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)

        spending_result = await self.session.execute(
            select(Transaction.category_id, func.sum(Transaction.amount).label("total"))
            .where(
                Transaction.user_id == user.id,
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.type == "expense",
                Transaction.is_projected == False,
            )
            .group_by(Transaction.category_id)
        )
        spending_by_cat = {row.category_id: row.total for row in spending_result.all()}

        # Build comparison
        categories = []
        total_budgeted = Decimal(0)
        total_spent = Decimal(0)
        over_budget = 0
        near_limit = 0

        for item in budget.items:
            budgeted = item.amount
            spent = spending_by_cat.get(item.category_id, Decimal(0))
            remaining = budgeted - spent
            pct = float(spent / budgeted * 100) if budgeted > 0 else 0
            is_over = spent > budgeted

            categories.append(
                BudgetCategoryComparison(
                    category_id=item.category_id,
                    category_name=item.category.name if item.category else "N/A",
                    budgeted=budgeted,
                    spent=spent,
                    remaining=remaining,
                    percentage_used=pct,
                    is_over_budget=is_over,
                )
            )

            total_budgeted += budgeted
            total_spent += spent

            if is_over:
                over_budget += 1
            elif pct >= 80:
                near_limit += 1

        total_remaining = total_budgeted - total_spent
        total_pct = float(total_spent / total_budgeted * 100) if total_budgeted > 0 else 0

        return BudgetComparison(
            total_budgeted=total_budgeted,
            total_spent=total_spent,
            total_remaining=total_remaining,
            percentage_used=total_pct,
            categories=sorted(categories, key=lambda x: x.percentage_used, reverse=True),
            categories_over_budget=over_budget,
            categories_near_limit=near_limit,
        )

    async def _get_goal_progress(
        self, user: User, week_start: date, week_end: date
    ) -> list[GoalProgress]:
        """Get progress on active goals."""
        result = await self.session.execute(
            select(Goal)
            .where(
                Goal.user_id == user.id,
                Goal.status == "active",
            )
            .order_by(Goal.priority.desc())
            .limit(10)
        )
        goals = result.scalars().all()
        today = date.today()

        progress_list = []
        for goal in goals:
            pct = (
                float(goal.current_amount / goal.target_amount * 100)
                if goal.target_amount > 0
                else 0
            )

            # Get contributions this week (from transactions or goal contributions)
            # For simplicity, just show current amounts
            contrib_this_week = Decimal(0)  # TODO: Calculate from contributions table

            # Calculate suggested contribution if target date exists
            suggested = None
            days_remaining = None
            if goal.target_date:
                days_remaining = (goal.target_date - today).days
                if days_remaining > 0:
                    remaining = goal.target_amount - goal.current_amount
                    weeks_left = max(1, days_remaining / 7)
                    suggested = remaining / Decimal(str(weeks_left))

            progress_list.append(
                GoalProgress(
                    id=goal.id,
                    name=goal.name,
                    target_amount=goal.target_amount,
                    current_amount=goal.current_amount,
                    percentage=pct,
                    contribution_this_week=contrib_this_week,
                    suggested_contribution=suggested,
                    target_date=goal.target_date,
                    days_remaining=days_remaining,
                )
            )

        return progress_list

    async def _get_upcoming_items(
        self, user: User, after_date: date, days_ahead: int = 7
    ) -> list[UpcomingItem]:
        """Get upcoming financial items."""
        end_date = after_date + timedelta(days=days_ahead)
        today = date.today()
        items = []

        # Recurring transactions
        result = await self.session.execute(
            select(RecurringTransaction).where(
                RecurringTransaction.user_id == user.id,
                RecurringTransaction.status == "active",
                RecurringTransaction.next_due_date != None,
                RecurringTransaction.next_due_date <= end_date,
            )
        )
        for rec in result.scalars().all():
            if rec.next_due_date:
                items.append(
                    UpcomingItem(
                        type="recurring",
                        description=rec.name,
                        amount=rec.amount,
                        due_date=rec.next_due_date,
                        days_until=(rec.next_due_date - today).days,
                        entity_id=rec.id,
                        is_income=rec.type == "income",
                    )
                )

        # Credit card invoices
        result = await self.session.execute(
            select(CreditCardInvoice).where(
                CreditCardInvoice.user_id == user.id,
                CreditCardInvoice.status == "open",
                CreditCardInvoice.due_date <= end_date,
            )
        )
        for inv in result.scalars().all():
            items.append(
                UpcomingItem(
                    type="invoice",
                    description="Fatura cartão",
                    amount=inv.total_amount,
                    due_date=inv.due_date,
                    days_until=(inv.due_date - today).days,
                    entity_id=inv.id,
                    is_income=False,
                )
            )

        # Sort by due date
        items.sort(key=lambda x: x.due_date)
        return items[:10]

    def _generate_tips(
        self,
        summary: WeekSummary,
        budget: BudgetComparison | None,
        uncategorized: list[UncategorizedTransaction],
    ) -> list[str]:
        """Generate actionable tips based on the review data."""
        tips = []

        # Spending trend
        if summary.expenses_vs_previous is not None:
            if summary.expenses_vs_previous > 20:
                tips.append(
                    f"Seus gastos aumentaram {summary.expenses_vs_previous:.0f}% em relação à semana passada. "
                    "Considere revisar onde você pode economizar."
                )
            elif summary.expenses_vs_previous < -10:
                tips.append(
                    f"Parabéns! Você reduziu seus gastos em {abs(summary.expenses_vs_previous):.0f}% "
                    "comparado à semana passada."
                )

        # Budget issues
        if budget:
            if budget.categories_over_budget > 0:
                tips.append(
                    f"{budget.categories_over_budget} categoria(s) já ultrapassaram o orçamento. "
                    "Revise seus gastos para evitar surpresas no fim do mês."
                )
            if budget.categories_near_limit > 0:
                tips.append(
                    f"{budget.categories_near_limit} categoria(s) estão perto do limite (>80%). "
                    "Fique atento nos próximos dias."
                )

        # Uncategorized
        if len(uncategorized) > 5:
            tips.append(
                f"Você tem {len(uncategorized)} transações sem categoria. "
                "Categorize-as para ter uma visão mais clara dos seus gastos."
            )

        # Positive balance
        if summary.net_balance > 0:
            tips.append(
                f"Sua semana foi positiva em R$ {summary.net_balance:,.2f}. "
                "Considere investir o excedente ou contribuir para suas metas."
            )

        return tips
