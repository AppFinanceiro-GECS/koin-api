"""
Cash Calendar API Routes.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.modules.calendar.schemas import CashCalendarResponse, WeeklySummary
from app.modules.calendar.services import CashCalendarService

router = APIRouter(prefix="/calendar", tags=["Cash Calendar"])


@router.get("/daily", response_model=CashCalendarResponse)
async def get_daily_calendar(
    start_date: date = Query(default=None, description="Start date (defaults to today)"),
    end_date: date = Query(default=None, description="End date (defaults to 30 days from start)"),
    include_details: bool = Query(default=False, description="Include transaction details"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get cash calendar with daily entries.

    Combines confirmed transactions with projections from:
    - Recurring transactions
    - Credit card invoices
    - Debt payments
    - Installments
    """
    if not start_date:
        start_date = date.today()
    if not end_date:
        end_date = start_date + timedelta(days=30)

    # Limit to 90 days max
    if (end_date - start_date).days > 90:
        end_date = start_date + timedelta(days=90)

    service = CashCalendarService(db)
    return await service.get_cash_calendar(current_user, start_date, end_date, include_details)


@router.get("/weekly/{year}/{week}", response_model=WeeklySummary)
async def get_weekly_summary(
    year: int,
    week: int,
    compare_previous: bool = Query(default=True, description="Compare with previous week"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get summary for a specific ISO week.
    """
    if week < 1 or week > 53:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Week must be between 1 and 53")

    service = CashCalendarService(db)
    return await service.get_weekly_summary(current_user, year, week, compare_previous)


@router.get("/monthly/{year}/{month}", response_model=CashCalendarResponse)
async def get_monthly_calendar(
    year: int,
    month: int,
    include_details: bool = Query(default=False, description="Include transaction details"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get cash calendar for a specific month.
    """
    if month < 1 or month > 12:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Month must be between 1 and 12")

    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)

    service = CashCalendarService(db)
    return await service.get_cash_calendar(current_user, start_date, end_date, include_details)


@router.get("/running-balance", response_model=CashCalendarResponse)
async def get_running_balance(
    start_date: date = Query(default=None, description="Start date"),
    end_date: date = Query(default=None, description="End date"),
    days: int = Query(default=30, description="Number of days to project"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get running balance projection.

    Shows how account balance changes day by day,
    highlighting potential shortfall dates.
    """
    if not start_date:
        start_date = date.today()
    if not end_date:
        end_date = start_date + timedelta(days=days)

    service = CashCalendarService(db)
    return await service.get_cash_calendar(
        current_user, start_date, end_date, include_details=False
    )


@router.get("/projections/{days_ahead}", response_model=CashCalendarResponse)
async def get_projections(
    days_ahead: int,
    include_details: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get future projections for the specified number of days.

    Only includes future dates, with projections for:
    - Recurring transactions
    - Invoice due dates
    - Debt payments
    - Installments
    """
    if days_ahead < 1 or days_ahead > 365:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="days_ahead must be between 1 and 365")

    start_date = date.today()
    end_date = start_date + timedelta(days=days_ahead)

    service = CashCalendarService(db)
    return await service.get_cash_calendar(current_user, start_date, end_date, include_details)
