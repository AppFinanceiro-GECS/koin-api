"""Admin module for system administration."""

from app.modules.admin.routers.admin import router
from app.modules.admin.schemas.admin import (
    AdminDashboard,
    HouseholdMemberSummary,
    LicenseBase,
    LicenseCreate,
    LicenseResponse,
    LicenseUpdate,
    UserAdminCreate,
    UserAdminResponse,
    UserAdminUpdate,
    UserListResponse,
)

__all__ = [
    "router",
    "AdminDashboard",
    "HouseholdMemberSummary",
    "LicenseBase",
    "LicenseCreate",
    "LicenseResponse",
    "LicenseUpdate",
    "UserAdminCreate",
    "UserAdminResponse",
    "UserAdminUpdate",
    "UserListResponse",
]
