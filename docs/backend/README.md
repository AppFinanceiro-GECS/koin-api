# Koin - Backend

API REST de gestao financeira pessoal construida com FastAPI, SQLAlchemy e PostgreSQL.

## Tech Stack

| Tecnologia | Versao | Proposito |
|------------|--------|-----------|
| Python | 3.12 | Linguagem |
| FastAPI | 0.109 | Framework web |
| SQLAlchemy | 2.0 | ORM (async) |
| PostgreSQL | 15+ | Banco de dados |
| Pydantic | 2.0 | Validacao |
| Alembic | 1.13 | Migracoes |
| JWT (python-jose) | 3.3 | Autenticacao |

## Estrutura do Projeto

```
backend/
├── app/
│   ├── core/                    # Infraestrutura
│   │   ├── config.py           # Settings via Pydantic
│   │   ├── database.py         # Conexao async com PostgreSQL
│   │   ├── deps.py             # Dependencias injetaveis
│   │   ├── security.py         # JWT, hashing, autenticacao
│   │   ├── rate_limit.py       # Rate limiting com slowapi
│   │   └── services/           # Servicos compartilhados
│   │       ├── email_service.py
│   │       ├── llm_ocr_service.py
│   │       └── business_day_service.py
│   │
│   ├── models/                  # SQLAlchemy models (30+)
│   │   ├── __init__.py         # Exports centralizados
│   │   ├── user.py
│   │   ├── transaction.py
│   │   ├── credit_card.py
│   │   └── ...
│   │
│   ├── modules/                 # Modulos de features (20)
│   │   ├── auth/
│   │   ├── accounts/
│   │   ├── transactions/
│   │   ├── documents/
│   │   ├── credit_cards/
│   │   ├── budgets/
│   │   ├── goals/
│   │   ├── debts/
│   │   ├── recurring/
│   │   ├── analytics/
│   │   ├── chat/
│   │   ├── income/
│   │   ├── installments/
│   │   ├── household/
│   │   ├── admin/
│   │   ├── api_keys/
│   │   ├── mcp/
│   │   ├── known_services/
│   │   ├── categories/
│   │   └── notifications/
│   │
│   ├── routers/                 # Agregador de rotas
│   │   └── __init__.py
│   │
│   └── main.py                  # Entry point FastAPI
│
├── alembic/                     # Migracoes do banco
│   ├── versions/               # Arquivos de migracao
│   └── env.py
│
├── tests/                       # Testes
│   ├── conftest.py
│   └── test_*.py
│
├── uploads/                     # Arquivos enviados
├── requirements.txt
├── alembic.ini
└── .env
```

## Modulos

Cada modulo segue a estrutura:

```
module_name/
├── __init__.py
├── schemas/           # Pydantic models (request/response)
│   └── *.py
├── services/          # Logica de negocio
│   └── *.py
├── routers/           # Endpoints FastAPI
│   └── *.py
└── README.md          # Documentacao do modulo
```

Veja [MODULES.md](./MODULES.md) para descricao detalhada de cada modulo.

## Endpoints Principais

### Autenticacao

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/api/v1/auth/login` | Login com email/senha |
| POST | `/api/v1/auth/register/invite/{token}` | Registro via convite |
| POST | `/api/v1/auth/refresh` | Renovar tokens |
| POST | `/api/v1/auth/logout` | Logout |

### Transacoes

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/api/v1/transactions` | Listar com filtros |
| POST | `/api/v1/transactions` | Criar transacao |
| PUT | `/api/v1/transactions/{id}` | Atualizar |
| DELETE | `/api/v1/transactions/{id}` | Excluir |
| POST | `/api/v1/transactions/confirm` | Confirmar de documento |

### Documentos

| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/api/v1/documents` | Upload de documento |
| GET | `/api/v1/documents` | Listar documentos |
| POST | `/api/v1/documents/{id}/retry` | Reprocessar |

### Faturas

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/api/v1/invoices` | Listar faturas |
| POST | `/api/v1/invoices/{id}/pay` | Pagar fatura |

### Analytics

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/api/v1/analytics/monthly` | Resumo mensal |
| GET | `/api/v1/analytics/insights` | Insights financeiros |

## Autenticacao

### JWT

- **Access Token**: Expira em 30 minutos
- **Refresh Token**: Expira em 7 dias
- **Algoritmo**: HS256

### Roles

- `user`: Usuario padrao
- `admin`: Acesso administrativo

### Multi-tenancy

- Todos os dados sao filtrados por `user_id`
- Suporte a `household` para compartilhamento familiar
- Isolamento por `license_id`

## Servicos Externos

### LLM Vision Service

Extracao de dados de documentos com multiplos providers:

| Provider | Modelo | Processo |
|----------|--------|----------|
| Google | Gemini 2.0 Flash | Vision direto |
| OpenAI | GPT-4o | Vision direto |
| Anthropic | Claude 3.5 | Vision direto |
| Mistral | OCR + Large | 2 etapas |

### Email Service

Envio de emails via SMTP (Hostinger):
- Convites para familia
- Reset de senha
- Notificacoes

## Scripts Uteis

```bash
# Iniciar servidor de desenvolvimento
uvicorn app.main:app --reload --port 8000

# Rodar testes
pytest

# Rodar testes com cobertura
pytest --cov=app --cov-report=html

# Criar migracao
alembic revision --autogenerate -m "descricao"

# Aplicar migracoes
alembic upgrade head

# Verificar tipos
mypy app

# Formatar codigo
black app && isort app

# Lint
ruff app
```

## Variaveis de Ambiente

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/koin

# JWT
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# LLM Providers
VISION_PROVIDER=google  # google, openai, anthropic, mistral
GOOGLE_API_KEY=xxx
OPENAI_API_KEY=xxx
ANTHROPIC_API_KEY=xxx
MISTRAL_API_KEY=xxx

# Email
SMTP_HOST=smtp.hostinger.com
SMTP_PORT=465
SMTP_USER=xxx
SMTP_PASSWORD=xxx

# Environment
ENVIRONMENT=development
DEBUG=true
```

## Documentacao Adicional

- [Modulos](./MODULES.md) - Descricao dos 20 modulos
- [Arquitetura](../architecture/OVERVIEW.md) - Arquitetura do sistema
- [Database Schema](../architecture/DATABASE_SCHEMA.md) - Esquema do banco
