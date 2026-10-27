"""
Schemas de usuario: criacao, atualizacao e resposta.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.email_address import NormalizedEmail


class UserBase(BaseModel):
    email: NormalizedEmail
    name: str = Field(min_length=2, max_length=100)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=72)


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    email: NormalizedEmail | None = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    is_verified: bool
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ChangePassword(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=72)
