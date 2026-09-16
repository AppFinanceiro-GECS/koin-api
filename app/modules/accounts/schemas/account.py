from datetime import datetime

from pydantic import BaseModel, Field

from app.models.account import AccountType
from app.models.household import OwnershipType


class AccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: AccountType
    bank_id: str | None = Field(None, max_length=50)
    currency: str = "BRL"
    color: str | None = None
    icon: str | None = None


class AccountCreate(AccountBase):
    balance: float = 0
    ownership_type: OwnershipType = OwnershipType.PERSONAL


class AccountUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    type: AccountType | None = None
    bank_id: str | None = Field(None, max_length=50)
    balance: float | None = None
    currency: str | None = None
    color: str | None = None
    icon: str | None = None
    is_active: bool | None = None


class AccountResponse(AccountBase):
    id: int
    balance: float
    is_active: bool
    ownership_type: str = "personal"
    created_at: datetime

    class Config:
        from_attributes = True
