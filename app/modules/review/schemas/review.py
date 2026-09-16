"""
Schemas for Weekly Review.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class WeekSummary(BaseModel):
    """Summary of the week's financial activity."""

    week_start: date
    week_end: date
    week_number: int
    year: int

    # Income
    total_income: Decimal
    income_count: int
    income_vs_previous: Decimal | None  # Percentage change

    # Expenses
    total_expenses: Decimal
    expenses_count: int
    expenses_vs_previous: Decimal | None

    # Net
    net_balance: Decimal
    net_vs_previous: Decimal | None

    # Averages
    daily_average_expense: Decimal

    # Top categories
    top_expense_categories: list[dict]


class UncategorizedTransaction(BaseModel):
    """An uncategorized transaction."""

    id: int
    date: date
    description: str
    amount: Decimal
    type: str
    account_name: str
    suggested_category_id: int | None = None
    suggested_category_name: str | None = None


class BudgetCategoryComparison(BaseModel):
    """Budget vs actual for a category."""

    category_id: int
    category_name: str
    budgeted: Decimal
    spent: Decimal
    remaining: Decimal
    percentage_used: float
    is_over_budget: bool


class BudgetComparison(BaseModel):
    """Overall budget comparison."""

    total_budgeted: Decimal
    total_spent: Decimal
    total_remaining: Decimal
    percentage_used: float
    categories: list[BudgetCategoryComparison]
    categories_over_budget: int
    categories_near_limit: int  # > 80%


class GoalProgress(BaseModel):
    """Progress on a goal."""

    id: int
    name: str
    target_amount: Decimal
    current_amount: Decimal
    percentage: float
    contribution_this_week: Decimal
    suggested_contribution: Decimal | None
    target_date: date | None
    days_remaining: int | None


class UpcomingItem(BaseModel):
    """An upcoming financial item."""

    type: str  # recurring, invoice, debt_payment
    description: str
    amount: Decimal
    due_date: date
    days_until: int
    entity_id: int
    is_income: bool


class WeeklyReviewResponse(BaseModel):
    """Complete weekly review data."""

    week_summary: WeekSummary
    uncategorized_transactions: list[UncategorizedTransaction]
    uncategorized_count: int
    budget_comparison: BudgetComparison | None
    goal_progress: list[GoalProgress]
    upcoming_items: list[UpcomingItem]
    review_tips: list[str]
    last_review_date: date | None
    streak_weeks: int


class WeeklyReviewComplete(BaseModel):
    """Request to mark weekly review as complete."""

    year: int
    week: int
    notes: str | None = None
