# Modulo API Keys

## Descricao
Modulo responsavel pelo gerenciamento de API Keys para integracao com servicos externos. Permite que usuarios criem chaves de acesso para usar com Claude Code, ChatGPT Custom GPTs e outras ferramentas que consomem a API MCP.

## Responsabilidades
- Geracao segura de API Keys
- CRUD de API Keys (criar, listar, revogar, deletar)
- Controle de permissoes (leitura/escrita)
- Expiracao configuravel
- Tracking de uso (last_used_at, usage_count)

## Estrutura
```
api_keys/
├── __init__.py
├── schemas/
│   ├── __init__.py
│   └── api_key.py      # APIKeyCreate, APIKeyResponse, APIKeyCreatedResponse, APIKeyListResponse
├── services/
│   ├── __init__.py
│   └── api_key_service.py  # APIKeyService (CRUD de API Keys)
└── routers/
    ├── __init__.py
    └── api_keys.py     # Endpoints de API Keys
```

## Dependencias
- **Models**: `APIKey`, `APIKeyStatus`, `User`
- **Outros Modulos**: Nenhum
- **Core**: `deps` (CurrentUser, get_db), `security` (generate_api_key)

## Restricoes de Acesso
- Apenas o **owner da licenca** pode gerenciar API Keys
- Limite maximo de **10 API Keys ativas** por usuario
- Chave completa e mostrada **apenas uma vez** na criacao

## Endpoints

### Router API Keys (`/api-keys`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `` | Cria nova API Key |
| GET | `` | Lista todas as API Keys |
| GET | `/{key_id}` | Detalhes de uma API Key |
| POST | `/{key_id}/revoke` | Revoga uma API Key |
| DELETE | `/{key_id}` | Deleta permanentemente |

## Uso
```python
from app.modules.api_keys import (
    router,
    APIKeyService,
    APIKeyCreate,
    APIKeyResponse,
    APIKeyCreatedResponse,
    APIKeyListResponse,
)
```

## Schemas

### APIKeyCreate
Request para criar uma nova API Key.

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| `name` | `str` | Sim | Nome para identificar a chave (1-100 chars) |
| `notes` | `str` | Nao | Observacoes opcionais (max 500 chars) |
| `expires_in_days` | `int` | Nao | Dias ate expirar (1-365, null = nunca) |

### APIKeyCreatedResponse
Resposta ao criar uma API Key.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `id` | `int` | ID da API Key |
| `name` | `str` | Nome da chave |
| `api_key` | `str` | **Chave completa** (so mostrada uma vez!) |
| `key_prefix` | `str` | Prefixo para identificacao (ex: `biv_abc...`) |
| `expires_at` | `datetime \| None` | Data de expiracao |
| `created_at` | `datetime` | Data de criacao |

### APIKeyResponse
Response padrao (sem a chave completa).

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `id` | `int` | ID da API Key |
| `name` | `str` | Nome da chave |
| `key_prefix` | `str` | Prefixo para identificacao |
| `status` | `str` | `active`, `revoked`, `expired` |
| `can_read` | `bool` | Permissao de leitura |
| `can_write` | `bool` | Permissao de escrita |
| `last_used_at` | `datetime \| None` | Ultimo uso |
| `expires_at` | `datetime \| None` | Data de expiracao |
| `usage_count` | `int` | Contador de usos |
| `created_at` | `datetime` | Data de criacao |

## Fluxo de Uso

### 1. Criar API Key
```bash
POST /api-keys
{
  "name": "Claude Code",
  "notes": "Integracao com IDE",
  "expires_in_days": 90
}
```

### 2. Guardar a Chave
A resposta contem `api_key` com a chave completa (ex: `biv_xxx...`).
**Guarde em local seguro!** Nao sera mostrada novamente.

### 3. Usar nos Endpoints MCP
```bash
curl -H "Authorization: Bearer biv_xxx..." \
     https://biveto.com/api/v1/mcp/summary
```

### 4. Revogar se Necessario
```bash
POST /api-keys/{key_id}/revoke
```

## Status da API Key
| Status | Descricao |
|--------|-----------|
| `active` | Chave ativa e funcional |
| `revoked` | Chave revogada manualmente |
| `expired` | Chave expirada (data passou) |

## Seguranca
- Chaves sao armazenadas como hash (SHA256)
- Apenas o prefixo e visivel apos criacao
- Permissao de escrita desabilitada por padrao
- Tracking de uso para auditoria
