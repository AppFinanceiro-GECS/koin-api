from datetime import datetime

from pydantic import BaseModel, Field

from app.models.category import CategoryType


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    type: CategoryType
    icon: str | None = None
    color: str | None = None
    parent_id: int | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryResponse(CategoryBase):
    id: int
    is_system: bool
    created_at: datetime

    class Config:
        from_attributes = True
