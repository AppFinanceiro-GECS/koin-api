"""
Schemas do modulo auth.
Exporta os schemas de autenticacao, usuario e convites.
"""

from app.modules.auth.schemas.auth import (
    LoginRequest,
    Token,
    TokenPayload,
)
from app.modules.auth.schemas.invitation import (
    InvitationCreate,
    InvitationListResponse,
    InvitationResponse,
    InviteRegister,
    InviteValidation,
)
from app.modules.auth.schemas.user import (
    ChangePassword,
    UserBase,
    UserCreate,
    UserResponse,
    UserUpdate,
)

__all__ = [
    # Auth schemas
    "LoginRequest",
    "Token",
    "TokenPayload",
    # User schemas
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "ChangePassword",
    # Invitation schemas
    "InvitationCreate",
    "InvitationResponse",
    "InvitationListResponse",
    "InviteValidation",
    "InviteRegister",
]
