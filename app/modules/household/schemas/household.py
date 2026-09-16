"""
Schemas de household: membros da familia, contexto e convites.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.household import HouseholdRole, OwnershipType

# ========== Household Member Schemas ==========


class HouseholdMemberBase(BaseModel):
    nickname: str | None = None
    can_create_transactions: bool = True
    can_edit_shared: bool = True
    can_invite_members: bool = False
    can_see_all: bool = False


class HouseholdMemberCreate(HouseholdMemberBase):
    user_id: int
    role: str = HouseholdRole.MEMBER.value


class HouseholdMemberResponse(HouseholdMemberBase):
    id: int
    license_id: int
    user_id: int
    user_name: str | None = None
    user_email: str | None = None
    role: str
    joined_at: datetime
    invited_by_id: int | None = None

    class Config:
        from_attributes = True


class HouseholdMemberUpdate(BaseModel):
    nickname: str | None = None
    role: str | None = None
    can_create_transactions: bool | None = None
    can_edit_shared: bool | None = None
    can_invite_members: bool | None = None
    can_see_all: bool | None = None


# ========== Family Context Schemas ==========


class FamilyContext(BaseModel):
    """Contexto da familia do usuario logado"""

    license_id: int
    license_type: str
    is_owner: bool
    can_invite: bool
    member_count: int
    max_members: int
    members: list[HouseholdMemberResponse]


# ========== Family Invite Schemas ==========


class FamilyInviteRequest(BaseModel):
    """Request para convidar membro da familia"""

    email: EmailStr
    nickname: str | None = None


class FamilyInviteResponse(BaseModel):
    """Response do convite da familia"""

    invitation_id: int
    email: str
    status: str
    expires_at: datetime


# ========== Pending Invitations ==========


class FamilyInvitationResponse(BaseModel):
    """Convite pendente da familia"""

    id: int
    email: str
    status: str
    created_at: datetime
    expires_at: datetime


# ========== Ownership Type ==========


class OwnershipUpdate(BaseModel):
    """Update para ownership_type de um recurso"""

    ownership_type: OwnershipType = OwnershipType.PERSONAL
