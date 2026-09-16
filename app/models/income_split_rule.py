from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class SplitType(str, Enum):
    """Type of split calculation"""

    PERCENTAGE = "percentage"  # Percentage of income (e.g., 10%)
    FIXED = "fixed"  # Fixed amount (e.g., R$ 100.00)


class IncomeSplitRule(Base):
    """
    Rules for automatically splitting income into expenses.
    For example: Tithe (10%), Savings (20%), Investment (15%)

    When a user creates an income transaction, they can select which
    split rules to apply. Each rule generates a pending expense
    linked back to the original income.
    """

    __tablename__ = "income_split_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(100))  # e.g., "Dizimo", "Poupanca"

    # Split configuration
    split_type: Mapped[str] = mapped_column(String(20))  # SplitType enum
    percentage: Mapped[float | None] = mapped_column(Numeric(5, 2))  # e.g., 10.00 for 10%
    fixed_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))  # e.g., 100.00

    # Destination (always expense per user decision)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    description_template: Mapped[str | None] = mapped_column(
        String(200)
    )  # e.g., "Dizimo (10%) - {description}"

    # Behavior
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Order in list

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="income_split_rules")
    category: Mapped["Category | None"] = relationship(lazy="noload")

    # Computed properties
    @property
    def category_name(self) -> str | None:
        return self.category.name if self.category else None

    def calculate_split_amount(self, income_amount: float) -> float:
        """Calculate the split amount based on rule type"""
        if self.split_type == SplitType.PERCENTAGE.value:
            return round(income_amount * (float(self.percentage or 0) / 100), 2)
        elif self.split_type == SplitType.FIXED.value:
            return float(self.fixed_amount or 0)
        return 0.0

    def format_description(self, original_description: str | None) -> str:
        """Format the description using the template"""
        template = self.description_template or "{name} - {description}"
        return template.format(
            name=self.name,
            description=original_description or "",
            percentage=self.percentage or "",
            amount=self.fixed_amount or "",
        ).strip()


from .category import Category
from .user import User
