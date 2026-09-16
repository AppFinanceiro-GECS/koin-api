"""
Router for Weekly Review.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.modules.review.schemas import (
    WeeklyReviewComplete,
    WeeklyReviewResponse,
)
from app.modules.review.services import WeeklyReviewService

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/weekly/{year}/{week}", response_model=WeeklyReviewResponse)
async def get_weekly_review(
    year: int,
    week: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get weekly review data for a specific week.

    The review includes:
    - Week summary (income, expenses, net balance)
    - Uncategorized transactions to review
    - Budget vs actual comparison
    - Goal progress
    - Upcoming items (recurring, invoices, etc.)
    - Actionable tips
    """
    if week < 1 or week > 53:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Week must be between 1 and 53"
        )

    service = WeeklyReviewService(session)
    return await service.get_weekly_review(current_user, year, week)


@router.get("/weekly/current", response_model=WeeklyReviewResponse)
async def get_current_weekly_review(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get weekly review for the current week."""
    today = date.today()
    year, week, _ = today.isocalendar()

    service = WeeklyReviewService(session)
    return await service.get_weekly_review(current_user, year, week)


@router.post("/weekly/{year}/{week}/complete")
async def complete_weekly_review(
    year: int,
    week: int,
    data: WeeklyReviewComplete | None = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark a weekly review as completed.

    This can be used to track review streaks and history.
    """
    # TODO: Store review completion in database
    # For now, just return success
    return {
        "success": True,
        "year": year,
        "week": week,
        "message": "Revisão semanal concluída!",
    }
