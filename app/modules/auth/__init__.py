"""
Modulo Auth - Autenticacao e Gerenciamento de Usuarios

Este modulo e responsavel por:
- Autenticacao de usuarios (login, logout, refresh de tokens)
- Registro de novos usuarios via convite
- Gerenciamento de perfil de usuario
- Reset de senha
- Configuracao inicial de novos usuarios (contas e categorias padrao)

Estrutura:
- schemas/: Definicoes de schemas Pydantic para validacao de dados
  - auth.py: LoginRequest, Token, TokenPayload
  - user.py: UserCreate, UserUpdate, UserResponse, ChangePassword
  - invitation.py: InviteValidation, InviteRegister

- services/: Logica de negocios
  - auth_service.py: AuthService (login, register, refresh_token)
  - user_service.py: UserService (CRUD de usuarios)
  - user_setup.py: Setup inicial de novos usuarios

- routers/: Endpoints da API
  - auth.py: /login, /refresh, /invite/{token}, /reset-password/{token}
  - users.py: /me, /me/change-password

Uso:
    from app.modules.auth.schemas import Token, UserResponse
    from app.modules.auth.services import AuthService
    from app.modules.auth.routers import auth_router, users_router
"""

from app.modules.auth.routers import auth_router, users_router
from app.modules.auth.schemas import (
    ChangePassword,
    InvitationCreate,
    InvitationListResponse,
    InvitationResponse,
    InviteRegister,
    InviteValidation,
    LoginRequest,
    Token,
    TokenPayload,
    UserBase,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.modules.auth.services import (
    AuthService,
    UserService,
    create_default_accounts,
    create_default_categories,
    setup_new_user,
)

__all__ = [
    # Schemas
    "LoginRequest",
    "Token",
    "TokenPayload",
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "ChangePassword",
    "InvitationCreate",
    "InvitationResponse",
    "InvitationListResponse",
    "InviteValidation",
    "InviteRegister",
    # Services
    "AuthService",
    "UserService",
    "setup_new_user",
    "create_default_accounts",
    "create_default_categories",
    # Routers
    "auth_router",
    "users_router",
]
