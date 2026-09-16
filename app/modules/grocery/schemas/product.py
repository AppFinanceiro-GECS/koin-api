from datetime import datetime

from pydantic import BaseModel, Field

from app.models.grocery import GroceryCategory, NecessityType


class GroceryProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: GroceryCategory = GroceryCategory.OTHER
    necessity_type: NecessityType = NecessityType.ESSENTIAL
    default_unit: str = Field(default="un", max_length=10)


class GroceryProductCreate(GroceryProductBase):
    pass


class GroceryProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    category: GroceryCategory | None = None
    necessity_type: NecessityType | None = None
    default_unit: str | None = Field(None, max_length=10)


class GroceryProductResponse(GroceryProductBase):
    id: int
    user_id: int | None
    normalized_name: str
    is_system: bool
    created_at: datetime

    # Display names
    category_display: str | None = None
    necessity_type_display: str | None = None

    class Config:
        from_attributes = True
