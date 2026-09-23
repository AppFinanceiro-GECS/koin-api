# Guia de Desenvolvimento

Este documento contem instrucoes para desenvolvedores que trabalham no Koin.

## Ambiente de Desenvolvimento

### Pre-requisitos

| Ferramenta | Versao | Instalacao |
|------------|--------|------------|
| Python | 3.12+ | [python.org](https://python.org) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org) |
| PostgreSQL | 15+ | [postgresql.org](https://postgresql.org) |
| Git | 2.40+ | [git-scm.com](https://git-scm.com) |

### Configuracao Inicial

#### 1. Clonar o Repositorio

```bash
git clone https://github.com/seu-usuario/koin-app.git
cd koin-app
```

#### 2. Configurar Backend

```bash
cd backend

# Criar ambiente virtual
python -m venv venv

# Ativar ambiente
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -r requirements.txt

# Copiar arquivo de ambiente
cp .env.example .env
```

Editar `.env` com suas configuracoes:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/koin

# JWT
SECRET_KEY=development-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# LLM Provider (escolha um)
VISION_PROVIDER=google
GOOGLE_API_KEY=your-api-key

# Debug
DEBUG=true
ENVIRONMENT=development
```

#### 3. Configurar Banco de Dados

```bash
# Criar banco de dados
createdb koin

# Rodar migracoes
alembic upgrade head
```

#### 4. Configurar Frontend

```bash
cd ../frontend

# Instalar dependencias
npm install

# Copiar arquivo de ambiente
cp .env.example .env
```

Editar `.env`:

```env
VITE_API_URL=http://localhost:8000
```

### Executar o Projeto

#### Terminal 1 - Backend

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

#### Terminal 2 - Frontend

```bash
cd frontend
npm run dev
```

### URLs de Desenvolvimento

| Servico | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |

---

## Estrutura do Codigo

### Backend

```
backend/
├── app/
│   ├── core/                    # Infraestrutura
│   │   ├── config.py           # Configuracoes
│   │   ├── database.py         # Conexao BD
│   │   ├── deps.py             # Dependencias
│   │   ├── security.py         # JWT, hashing
│   │   ├── rate_limit.py       # Rate limiting
│   │   └── services/           # Servicos core
│   │
│   ├── models/                  # SQLAlchemy models
│   │   ├── __init__.py         # Exports
│   │   ├── user.py
│   │   ├── transaction.py
│   │   └── ...
│   │
│   ├── modules/                 # Modulos de features
│   │   ├── auth/
│   │   │   ├── schemas/        # Pydantic
│   │   │   ├── services/       # Logica
│   │   │   ├── routers/        # Endpoints
│   │   │   └── README.md
│   │   ├── transactions/
│   │   └── ...
│   │
│   ├── routers/                 # Agregador de routers
│   │   └── __init__.py
│   │
│   └── main.py                  # Entry point
│
├── alembic/                     # Migracoes
├── tests/                       # Testes
├── uploads/                     # Arquivos enviados
├── requirements.txt
└── .env
```

### Frontend

```
frontend/
├── src/
│   ├── pages/                   # Paginas (rotas)
│   │   ├── Dashboard.tsx
│   │   ├── Transactions.tsx
│   │   └── ...
│   │
│   ├── components/              # Componentes
│   │   ├── shared/             # Reutilizaveis
│   │   ├── upload/             # Upload flow
│   │   ├── credit-cards/       # Cartoes
│   │   └── Layout.tsx
│   │
│   ├── stores/                  # Zustand stores
│   │   ├── authStore.ts
│   │   ├── toastStore.ts
│   │   └── ...
│   │
│   ├── services/                # API
│   │   └── api.ts
│   │
│   ├── hooks/                   # Custom hooks
│   ├── types/                   # TypeScript types
│   ├── schemas/                 # Zod schemas
│   ├── data/                    # Dados estaticos
│   ├── styles/                  # CSS global
│   │
│   ├── App.tsx                  # Rotas
│   └── main.tsx                 # Entry point
│
├── public/                      # Assets estaticos
├── e2e/                         # Testes Playwright
└── package.json
```

---

## Testes

### Backend

```bash
cd backend

# Rodar todos os testes
pytest

# Com cobertura
pytest --cov=app --cov-report=html

# Testes especificos
pytest tests/test_transactions.py
pytest -k "test_create"
```

### Frontend

```bash
cd frontend

# Testes E2E com Playwright
npm run test:e2e

# Modo interativo
npm run test:e2e:ui

# Com browser visivel
npm run test:e2e:headed

# Debug
npm run test:e2e:debug
```

---

## Banco de Dados

### Migracoes

```bash
cd backend

# Criar nova migracao
alembic revision --autogenerate -m "descricao da mudanca"

# Aplicar migracoes
alembic upgrade head

# Reverter ultima migracao
alembic downgrade -1

# Ver historico
alembic history
```

### Reset do Banco

```bash
# Apagar e recriar
dropdb koin
createdb koin
alembic upgrade head
```

---

## Debugging

### Backend

```python
# Adicionar breakpoint
import pdb; pdb.set_trace()

# Ou usar debugpy para VS Code
import debugpy
debugpy.listen(5678)
debugpy.wait_for_client()
```

### Frontend

```typescript
// Console
console.log('Debug:', data);

// Debugger statement
debugger;

// React Query Devtools (ja configurado)
// Zustand Devtools (ja configurado)
```

---

## Ferramentas Uteis

### Backend

```bash
# Formatar codigo
black app
isort app

# Verificar tipos
mypy app

# Lint
ruff app
```

### Frontend

```bash
# Lint
npm run lint

# Formatar (se configurado)
npm run format
```

---

## Troubleshooting

### Erro de CORS

```python
# Verificar configuracao em main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Erro de Conexao com Banco

```bash
# Verificar se PostgreSQL esta rodando
pg_isready

# Verificar DATABASE_URL no .env
echo $DATABASE_URL
```

### Token Expirado

O frontend faz refresh automatico, mas se persistir:

```typescript
// Limpar storage e relogar
localStorage.clear();
window.location.href = '/login';
```

### LLM Nao Funciona

1. Verificar API Key no `.env`
2. Verificar `VISION_PROVIDER`
3. Verificar logs do backend

```bash
# Ver logs em tempo real
uvicorn app.main:app --reload --log-level debug
```

---

## Recursos

### Documentacao

- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- [React](https://react.dev/)
- [TanStack Query](https://tanstack.com/query/latest)
- [Zustand](https://zustand-demo.pmnd.rs/)
- [Tailwind CSS](https://tailwindcss.com/)

### Ferramentas

- [Postman](https://postman.com/) - Testar API
- [DBeaver](https://dbeaver.io/) - Cliente PostgreSQL
- [React DevTools](https://react.dev/learn/react-developer-tools)
