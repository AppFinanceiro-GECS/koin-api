from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class CategoryType(str, Enum):
    EXPENSE = "expense"
    INCOME = "income"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    type: Mapped[str] = mapped_column(String(10))  # CategoryType
    icon: Mapped[str | None] = mapped_column(String(50))
    color: Mapped[str | None] = mapped_column(String(7))  # hex color
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # categorias padrão
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    parent: Mapped["Category | None"] = relationship(
        "Category", remote_side=[id], backref="subcategories"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="category", lazy="noload"
    )


from .transaction import Transaction
