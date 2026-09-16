# Modulo Household

## Descricao
Modulo responsavel pelo gerenciamento de familias (households). Permite a criacao de grupos familiares para compartilhamento de recursos financeiros, convites para novos membros e controle de permissoes.

## Responsabilidades
- Gerenciamento de membros da familia (household)
- Contexto da familia do usuario logado
- Convites para novos membros da familia
- Permissoes e roles dentro da familia (owner, member)
- Controle de acesso a recursos compartilhados
- Remocao de membros pelo owner

## Estrutura
```
household/
├── __init__.py
├── schemas/
│   └── household.py      # HouseholdMemberResponse, FamilyContext, FamilyInviteRequest
├── services/             # (logica no router)
└── routers/
    └── family.py         # Endpoints de familia
```

## Dependencias
- **Models**: `HouseholdMember`, `HouseholdRole`, `User`, `License`, `Invitation`, `InvitationStatus`
- **Outros Modulos**: Nenhum
- **Core**: `email_service`, `deps` (CurrentUser, DbSession), `config` (settings)

## Endpoints

### Router Family (`/family`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/context` | Retorna contexto da familia do usuario logado |
| GET | `/members` | Lista membros da familia |
| POST | `/invite` | Convida novo membro para a familia |
| GET | `/invitations` | Lista convites pendentes da familia |
| DELETE | `/invitations/{invitation_id}` | Cancela convite pendente |
| POST | `/invitations/{invitation_id}/resend` | Reenvia email de convite |
| DELETE | `/members/{member_id}` | Remove membro da familia (apenas owner) |

## Uso
```python
from app.modules.household import (
    # Schemas
    HouseholdMemberResponse,
    FamilyContext,
    FamilyInviteRequest,
    FamilyInviteResponse,
    # Router
    family_router,
)
```

## Roles e Permissoes
- **OWNER**: Proprietario da familia, pode convidar e remover membros
- **MEMBER**: Membro comum, acesso aos recursos compartilhados

### Permissoes Configuraveir
- `can_create_transactions`: Pode criar transacoes
- `can_edit_shared`: Pode editar recursos compartilhados
- `can_invite_members`: Pode convidar novos membros
- `can_see_all`: Pode ver todas as transacoes da familia
