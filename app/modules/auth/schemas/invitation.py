"""
Schemas de convite: criacao, validacao e registro via convite.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.invitation import InvitationStatus


class InvitationCreate(BaseModel):
    email: EmailStr
    license_id: int | None = None


class InvitationResponse(BaseModel):
    id: int
    email: str
    status: InvitationStatus
    license_id: int | None
    license_code: str | None = None
    invited_by_name: str
    expires_at: datetime
    created_at: datetime
    is_valid: bool

    class Config:
        from_attributes = True


class InvitationListResponse(BaseModel):
    id: int
    email: str
    status: InvitationStatus
    license_id: int | None
    license_code: str | None = None
    invited_by_name: str
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class InviteValidation(BaseModel):
    email: str
    license_type: str | None = None
    is_valid: bool


class InviteRegister(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=6, max_length=100)
