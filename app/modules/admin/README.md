# Modulo Admin

## Descricao
Modulo responsavel pela administracao do sistema. Restrito a usuarios com flag `is_admin`. Permite gerenciar licencas, usuarios e convites do sistema.

## Responsabilidades
- Dashboard com estatisticas gerais
- CRUD de licencas
- CRUD de usuarios
- Gerenciamento de convites
- Envio de emails de reset de senha
- Transferencia de usuarios entre licencas

## Estrutura
```
admin/
├── __init__.py
├── schemas/
│   └── admin.py          # AdminDashboard, LicenseCreate, UserAdminCreate, etc.
├── services/             # (logica no router)
└── routers/
    └── admin.py          # Endpoints administrativos
```

## Dependencias
- **Models**: `User`, `License`, `LicenseStatus`, `Invitation`, `InvitationStatus`, `HouseholdMember`, `HouseholdRole`
- **Outros Modulos**: `auth` (setup de usuario)
- **Core**: `security`, `email_service`, `deps`, `config`

## Endpoints

### Router Admin (`/admin`)

#### Dashboard
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/dashboard` | Estatisticas gerais do sistema |

#### Licencas
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/licenses` | Lista todas as licencas |
| POST | `/licenses` | Cria licenca com convite automatico |
| PATCH | `/licenses/{license_id}` | Atualiza licenca |
| DELETE | `/licenses/{license_id}` | Remove licenca (sem usuarios) |

#### Usuarios
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/users` | Lista todos os usuarios |
| POST | `/users` | Cria usuario (com ou sem senha) |
| GET | `/users/{user_id}` | Detalhes do usuario |
| PATCH | `/users/{user_id}` | Atualiza usuario |
| DELETE | `/users/{user_id}` | Remove usuario |
| POST | `/users/{user_id}/reset-password` | Envia email de reset |

#### Convites
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/invitations` | Lista todos os convites |
| POST | `/invitations` | Cria e envia convite |
| POST | `/invitations/{invitation_id}/resend` | Reenvia email |
| DELETE | `/invitations/{invitation_id}` | Cancela convite |

## Uso
```python
from app.modules.admin import (
    router,
    AdminDashboard,
    LicenseCreate,
    LicenseUpdate,
    LicenseResponse,
    UserAdminCreate,
    UserAdminUpdate,
    UserAdminResponse,
    UserListResponse,
    HouseholdMemberSummary,
)
```

## Tipos de Licenca
- `free`: Gratuita (recursos limitados)
- `basic`: Basica
- `premium`: Premium
- `family`: Familiar (multiplos usuarios)
- `enterprise`: Empresarial

## Recursos por Licenca
- `max_users`: Maximo de usuarios
- `max_transactions_per_month`: Limite de transacoes
- `max_documents_per_month`: Limite de documentos
- `has_ai_assistant`: Acesso ao chat IA
- `has_insights`: Acesso aos insights
- `has_debt_strategies`: Estrategias de dividas
- `has_goals`: Metas financeiras
- `has_budget`: Orcamento

## Seguranca
Todos os endpoints verificam `is_admin` do usuario autenticado antes de executar qualquer acao.
