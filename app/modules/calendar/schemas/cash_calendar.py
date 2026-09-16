"""
Schemas for Cash Calendar API.
"""

from datetime import date
from enum import Enum

from pydantic import BaseModel


class ProjectionType(str, Enum):
    """Type of projected transaction."""

    RECURRING = "recurring"
    INVOICE = "invoice"
    DEBT = "debt"
    INSTALLMENT = "installment"


class TransactionSummary(BaseModel):
    """Summary of a confirmed transaction."""

    id: int
    description: str
    amount: float
    type: str  # income/expense
    category_name: str | None = None
    category_icon: str | None = None
    account_name: str | None = None
    is_paid: bool = True

    class Config:
        from_attributes = True


class ProjectionItem(BaseModel):
    """A projected future transaction."""

    projection_type: ProjectionType
    description: str
    amount: float
    is_income: bool
    category_name: str | None = None
    category_icon: str | None = None
    account_name: str | None = None

    # Reference to source entity
    entity_type: str | None = None  # recurring, invoice, debt, installment
    entity_id: int | None = None

    # Confidence level (1.0 = confirmed, lower for variable income)
    confidence: float = 1.0


class DailyEntry(BaseModel):
    """Cash flow data for a single day."""

    date: date
    is_past: bool
    is_today: bool
    is_weekend: bool

    # Confirmed transactions
    confirmed_income: float = 0
    confirmed_expense: float = 0
    confirmed_count: int = 0

    # Projected transactions
    projected_income: float = 0
    projected_expense: float = 0
    projected_count: int = 0

    # Net values
    net_confirmed: float = 0
    net_projected: float = 0
    net_total: float = 0

    # Details (optional, only when requested)
    transactions: list[TransactionSummary] = []
    projections: list[ProjectionItem] = []


class RunningBalanceEntry(BaseModel):
    """Running balance for a day."""

    date: date
    opening_balance: float
    income: float
    expense: float
    net: float
    closing_balance: float
    is_projected: bool
    is_negative: bool = False


class MajorExpense(BaseModel):
    """A major upcoming expense."""

    date: date
    description: str
    amount: float
    type: ProjectionType
    entity_id: int | None = None
    days_until: int


class WeeklySummary(BaseModel):
    """Summary for a week."""

    year: int
    week: int
    start_date: date
    end_date: date

    total_income: float
    total_expense: float
    net: float

    # Comparison with previous week
    income_change_percent: float | None = None
    expense_change_percent: float | None = None

    daily_average_expense: float
    top_expense_categories: list[dict] = []


class CashCalendarResponse(BaseModel):
    """Response for cash calendar queries."""

    start_date: date
    end_date: date

    # Current state
    current_balance: float
    projected_end_balance: float

    # Alerts
    shortfall_dates: list[date] = []  # Days with negative balance
    major_expenses: list[MajorExpense] = []

    # Data
    daily_entries: list[DailyEntry] = []
    running_balance: list[RunningBalanceEntry] = []

    # Totals for period
    total_confirmed_income: float = 0
    total_confirmed_expense: float = 0
    total_projected_income: float = 0
    total_projected_expense: float = 0
