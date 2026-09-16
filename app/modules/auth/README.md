# Modulo Auth

## Descricao
Modulo responsavel pela autenticacao e gerenciamento de usuarios do sistema. Controla login, registro via convite, renovacao de tokens, reset de senha e gerenciamento do perfil do usuario.

## Responsabilidades
- Autenticacao de usuarios (login, logout, refresh de tokens JWT)
- Registro de novos usuarios exclusivamente via convite
- Gerenciamento de perfil de usuario
- Reset de senha com token temporario
- Configuracao inicial de novos usuarios (contas e categorias padrao)
- Validacao de convites de registro

## Estrutura
```
auth/
├── __init__.py
├── schemas/
│   ├── auth.py           # LoginRequest, Token, TokenPayload
│   ├── user.py           # UserCreate, UserUpdate, UserResponse, ChangePassword
│   └── invitation.py     # InviteValidation, InviteRegister
├── services/
│   ├── auth_service.py   # AuthService (login, register, refresh_token)
│   ├── user_service.py   # UserService (CRUD de usuarios)
│   └── user_setup.py     # Setup inicial de novos usuarios
└── routers/
    ├── auth.py           # Endpoints de autenticacao
    └── users.py          # Endpoints de usuario
```

## Dependencias
- **Models**: `User`, `Invitation`, `InvitationStatus`, `License`, `HouseholdMember`, `HouseholdRole`
- **Outros Modulos**: Nenhum
- **Core**: `security` (hash, JWT), `rate_limit`, `email_service`, `deps` (CurrentUser, DbSession)

## Endpoints

### Router Auth (`/auth`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/me` | Retorna informacoes do usuario autenticado |
| POST | `/login` | Autentica usuario e retorna tokens JWT |
| POST | `/refresh` | Renova access token usando refresh token |
| GET | `/invite/{token}` | Valida token de convite |
| POST | `/invite/{token}` | Registra usuario via convite |
| GET | `/reset-password/{token}` | Valida token de reset de senha |
| POST | `/reset-password/{token}` | Redefine senha usando token |

### Router Users (`/users`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/me` | Retorna dados do usuario autenticado |
| PATCH | `/me` | Atualiza dados do usuario autenticado |
| POST | `/me/change-password` | Altera senha do usuario autenticado |

## Uso
```python
from app.modules.auth import (
    # Schemas
    LoginRequest,
    Token,
    TokenPayload,
    UserCreate,
    UserUpdate,
    UserResponse,
    ChangePassword,
    InviteValidation,
    InviteRegister,
    # Services
    AuthService,
    UserService,
    setup_new_user,
    # Routers
    auth_router,
    users_router,
)
```
