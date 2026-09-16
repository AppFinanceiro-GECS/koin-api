from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.license import LicenseStatus, LicenseType

# ========== License Schemas ==========


class LicenseBase(BaseModel):
    type: LicenseType = LicenseType.BASIC
    max_users: int = 1
    max_transactions_per_month: int | None = None
    max_documents_per_month: int | None = None
    has_ai_assistant: bool = True
    has_insights: bool = True
    has_debt_strategies: bool = True
    has_goals: bool = True
    has_budget: bool = True
    start_date: date = Field(default_factory=date.today)
    end_date: date | None = None
    notes: str | None = None


class LicenseCreate(LicenseBase):
    owner_email: EmailStr  # Email do owner (obrigatorio) - recebera convite automatico
    force_transfer: bool = False  # Se True, transfere usuario existente para nova licenca


class LicenseUpdate(BaseModel):
    type: LicenseType | None = None
    status: LicenseStatus | None = None
    max_users: int | None = None
    max_transactions_per_month: int | None = None
    max_documents_per_month: int | None = None
    has_ai_assistant: bool | None = None
    has_insights: bool | None = None
    has_debt_strategies: bool | None = None
    has_goals: bool | None = None
    has_budget: bool | None = None
    end_date: date | None = None
    notes: str | None = None


class HouseholdMemberSummary(BaseModel):
    """Resumo de membro para listagem de licencas"""

    id: int
    user_id: int
    user_name: str | None = None
    user_email: str | None = None
    role: str
    joined_at: datetime

    class Config:
        from_attributes = True


class LicenseResponse(LicenseBase):
    id: int
    key: str
    code: str  # Codigo amigavel: BIV-XXXX-XXXX
    status: LicenseStatus
    created_at: datetime
    updated_at: datetime
    is_valid: bool
    days_remaining: int | None
    user_count: int = 0
    # Campos do owner
    owner_email: str | None = None
    owner_user_id: int | None = None
    owner_name: str | None = None  # Nome do owner se ja cadastrado
    # Membros da familia
    member_count: int = 0
    members: list[HouseholdMemberSummary] | None = None

    class Config:
        from_attributes = True


# ========== User Admin Schemas ==========


class UserAdminCreate(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=2)
    password: str | None = Field(None, min_length=6)  # Opcional - se nao informado, envia convite
    is_admin: bool = False
    license_id: int | None = None


class UserAdminUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
    license_id: int | None = None


class UserAdminResponse(BaseModel):
    id: int
    email: str
    name: str
    is_active: bool
    is_verified: bool
    is_admin: bool
    license_id: int | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    id: int
    email: str
    name: str
    is_active: bool
    is_admin: bool
    license_id: int | None
    created_at: datetime

    class Config:
        from_attributes = True


# ========== Dashboard Schemas ==========


class AdminDashboard(BaseModel):
    total_users: int
    active_users: int
    admin_users: int
    total_licenses: int
    active_licenses: int
    expired_licenses: int
