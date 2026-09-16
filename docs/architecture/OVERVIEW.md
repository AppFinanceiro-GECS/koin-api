# Arquitetura do Sistema

## Visao Geral

O Biveto e uma aplicacao de gestao financeira pessoal construida com arquitetura moderna de monolit modular. O sistema e dividido em duas partes principais:

- **Backend**: API REST em Python com FastAPI
- **Frontend**: SPA em React com TypeScript

## Diagrama de Arquitetura

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1E3A5F', 'primaryTextColor': '#e2e8f0', 'primaryBorderColor': '#4ade80', 'lineColor': '#4ade80', 'secondaryColor': '#0f172a', 'tertiaryColor': '#1e293b', 'background': 'transparent', 'mainBkg': '#1e293b', 'textColor': '#e2e8f0', 'nodeTextColor': '#e2e8f0', 'clusterBkg': '#1e293b', 'clusterBorder': '#4ade80'}}}%%
flowchart TB
    subgraph Clients["CLIENTES"]
        Browser["Browser<br/>(React)"]
        PWA["Mobile PWA<br/>(React)"]
        Claude["Claude Code<br/>(MCP)"]
        ChatGPT["ChatGPT<br/>Custom GPT"]
    end

    subgraph Gateway["API GATEWAY"]
        FastAPI["FastAPI (Python)"]
        subgraph Middleware
            CORS["CORS"]
            Rate["Rate Limit"]
            Auth["Auth"]
        end
    end

    subgraph Modules["CAMADA DE MODULOS"]
        direction TB
        subgraph Row1
            M1["Auth"]
            M2["Accounts"]
            M3["Transactions"]
            M4["Documents"]
            M5["Credit Cards"]
        end
        subgraph Row2
            M6["Budgets"]
            M7["Goals"]
            M8["Debts"]
            M9["Recurring"]
            M10["Analytics"]
        end
        subgraph Row3
            M11["Chat (IA)"]
            M12["Income"]
            M13["Installments"]
            M14["Household"]
            M15["Admin"]
        end
        subgraph Row4
            M16["API Keys"]
            M17["MCP"]
            M18["Known Services"]
            M19["Categories"]
        end
    end

    subgraph Services["CAMADA DE SERVICOS"]
        subgraph LLM["LLM Vision Service"]
            Google["Google<br/>Gemini"]
            OpenAI["OpenAI<br/>GPT-4o"]
            Anthropic["Anthropic<br/>Claude"]
            Mistral["Mistral<br/>OCR"]
        end
        Email["Email Service"]
        BusinessDay["Business Day"]
        RecurringDet["Recurring Detection"]
    end

    subgraph Data["CAMADA DE DADOS"]
        SQLAlchemy["SQLAlchemy 2.0 (Async)"]
        Models["Models<br/>(30+ tables)"]
        Sessions["Sessions<br/>(async)"]
        Queries["Queries<br/>(select)"]
        PostgreSQL[(PostgreSQL 15+)]
    end

    Clients --> Gateway
    Gateway --> Modules
    Modules --> Services
    Modules --> Data
    SQLAlchemy --> PostgreSQL
```

## Componentes do Sistema

### 1. Frontend (React SPA)

**Tecnologias:**
- React 18 com TypeScript
- Vite para build
- Tailwind CSS para estilos
- Zustand para estado global
- TanStack Query para cache de servidor
- React Router para roteamento

**Responsabilidades:**
- Interface de usuario responsiva
- PWA com suporte offline
- Gerenciamento de estado local
- Cache de dados do servidor
- Autenticacao via JWT

**Estrutura:**
```
frontend/src/
├── pages/          # 22 paginas/rotas
├── components/     # 18 componentes reutilizaveis
├── stores/         # 4 Zustand stores
├── services/       # Camada de API (Axios)
├── hooks/          # Custom hooks
├── types/          # Tipos TypeScript
└── schemas/        # Validacao Zod
```

### 2. Backend (FastAPI)

**Tecnologias:**
- Python 3.12
- FastAPI (async)
- SQLAlchemy 2.0 (async)
- Pydantic v2 para validacao
- JWT para autenticacao
- Alembic para migracoes

**Responsabilidades:**
- API REST
- Autenticacao e autorizacao
- Logica de negocios
- Integracao com LLMs
- Persistencia de dados

**Estrutura:**
```
app/
├── core/           # Config, security, deps
├── models/         # 30+ SQLAlchemy models
├── modules/        # 20 modulos de features
│   ├── auth/
│   ├── transactions/
│   ├── documents/
│   └── ...
└── main.py         # Entry point
```

### 3. Banco de Dados (PostgreSQL)

**Principais Entidades:**

| Entidade | Descricao |
|----------|-----------|
| `users` | Usuarios do sistema |
| `licenses` | Licencas (free, premium, family) |
| `accounts` | Contas bancarias e carteiras |
| `transactions` | Transacoes financeiras |
| `categories` | Categorias (sistema + usuario) |
| `credit_cards` | Cartoes de credito |
| `credit_card_invoices` | Faturas de cartao |
| `installment_series` | Series de parcelamento |
| `budgets` / `budget_items` | Orcamentos mensais |
| `goals` / `goal_contributions` | Metas financeiras |
| `debts` / `debt_payments` | Dividas e pagamentos |
| `recurring_transactions` | Transacoes recorrentes |
| `income_sources` | Fontes de renda |
| `documents` / `document_extractions` | Documentos e extracoes |
| `merchants` | Estabelecimentos |
| `known_recurring_services` | Servicos conhecidos |
| `household_members` | Membros da familia |
| `api_keys` | Chaves de API |

### 4. Servicos de IA

**LLM Vision Service:**
- Extracao de dados de documentos
- Multiplos providers com fallback
- Validacao e normalizacao de dados

| Provider | Modelo | Processo |
|----------|--------|----------|
| Google | Gemini 2.0 Flash | Vision direto |
| OpenAI | GPT-4o | Vision direto |
| Anthropic | Claude 3.5 | Vision direto |
| Mistral | OCR + Large | 2 etapas |

**Chat Service:**
- Assistente financeiro inteligente
- Contexto agregado do usuario
- Sugestoes de perguntas

## Padroes de Arquitetura

### 1. Modular Monolith

O backend segue o padrao de monolit modular onde cada funcionalidade e encapsulada em um modulo independente:

```
modules/
├── auth/
│   ├── schemas/    # Pydantic models
│   ├── services/   # Business logic
│   ├── routers/    # API endpoints
│   └── README.md   # Documentacao
```

**Vantagens:**
- Separacao clara de responsabilidades
- Facil navegacao e manutencao
- Possibilidade de extrair microservicos
- Reutilizacao de codigo

### 2. Repository Pattern

Os services atuam como repositorios, abstraindo o acesso ao banco:

```python
class TransactionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, user: User, filters: dict) -> list[Transaction]:
        query = select(Transaction).where(Transaction.user_id == user.id)
        # ... aplicar filtros
        return await self.db.execute(query)
```

### 3. Dependency Injection

FastAPI injeta dependencias automaticamente:

```python
@router.get("/transactions")
async def list_transactions(
    user: CurrentUser,           # Usuario autenticado
    db: DbSession,              # Sessao do banco
    service: TransactionService = Depends()
):
    return await service.list(user)
```

### 4. Schema-First Validation

Pydantic valida entrada e saida:

```python
class TransactionCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    description: str = Field(..., min_length=1, max_length=255)
    date: date
    category_id: int

class TransactionResponse(BaseModel):
    id: int
    amount: Decimal
    # ... campos de saida

    class Config:
        from_attributes = True
```

## Fluxos Principais

### 1. Autenticacao

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1E3A5F', 'primaryTextColor': '#e2e8f0', 'primaryBorderColor': '#4ade80', 'lineColor': '#4ade80', 'secondaryColor': '#0f172a', 'tertiaryColor': '#1e293b', 'background': 'transparent', 'mainBkg': '#1e293b', 'textColor': '#e2e8f0', 'actorTextColor': '#e2e8f0', 'actorBkg': '#1E3A5F', 'actorBorder': '#4ade80', 'signalColor': '#e2e8f0', 'signalTextColor': '#e2e8f0'}}}%%
sequenceDiagram
    participant Client
    participant Login as /login
    participant Auth as AuthSvc
    participant DB as Database

    Client->>Login: POST {email, password}
    Login->>Auth: validate credentials
    Auth->>DB: query user
    DB-->>Auth: user data
    Auth->>Auth: verify password
    Auth-->>Login: JWT tokens
    Login-->>Client: {access_token, refresh_token}
    Client->>Client: store tokens (Zustand)
```

### 2. Upload de Documento

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1E3A5F', 'primaryTextColor': '#e2e8f0', 'primaryBorderColor': '#4ade80', 'lineColor': '#4ade80', 'secondaryColor': '#0f172a', 'tertiaryColor': '#1e293b', 'background': 'transparent', 'mainBkg': '#1e293b', 'textColor': '#e2e8f0', 'actorTextColor': '#e2e8f0', 'actorBkg': '#1E3A5F', 'actorBorder': '#4ade80', 'signalColor': '#e2e8f0', 'signalTextColor': '#e2e8f0'}}}%%
sequenceDiagram
    participant Client
    participant Upload as /upload
    participant Doc as DocumentSvc
    participant LLM as LLM OCR

    Client->>Upload: POST file (PDF/Image)
    Upload->>Doc: process document
    Doc->>LLM: extract data
    LLM-->>Doc: JSON extract
    Doc->>Doc: validate & detect duplicates
    Doc-->>Upload: extracted items
    Upload-->>Client: items for confirmation
```

### 3. Confirmacao de Transacoes

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1E3A5F', 'primaryTextColor': '#e2e8f0', 'primaryBorderColor': '#4ade80', 'lineColor': '#4ade80', 'secondaryColor': '#0f172a', 'tertiaryColor': '#1e293b', 'background': 'transparent', 'mainBkg': '#1e293b', 'textColor': '#e2e8f0', 'actorTextColor': '#e2e8f0', 'actorBkg': '#1E3A5F', 'actorBorder': '#4ade80', 'signalColor': '#e2e8f0', 'signalTextColor': '#e2e8f0'}}}%%
sequenceDiagram
    participant Client
    participant Confirm as /confirm
    participant Tx as TransactionSvc
    participant DB as Database

    Client->>Confirm: POST selected items
    Confirm->>Tx: validate
    Tx->>DB: create transactions
    Tx->>DB: update invoice
    DB-->>Tx: created
    Tx-->>Confirm: transactions
    Confirm-->>Client: created transactions
```

### 4. Transferencia entre Contas

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1E3A5F', 'primaryTextColor': '#e2e8f0', 'primaryBorderColor': '#4ade80', 'lineColor': '#4ade80', 'secondaryColor': '#0f172a', 'tertiaryColor': '#1e293b', 'background': 'transparent', 'mainBkg': '#1e293b', 'textColor': '#e2e8f0', 'actorTextColor': '#e2e8f0', 'actorBkg': '#1E3A5F', 'actorBorder': '#4ade80', 'signalColor': '#e2e8f0', 'signalTextColor': '#e2e8f0'}}}%%
sequenceDiagram
    participant Client
    participant API as /transactions
    participant Tx as TransactionSvc
    participant DB as Database

    Client->>API: POST {type: transfer, from: A, to: B}
    API->>Tx: validate accounts
    Tx->>DB: create tx_out (conta A, -)
    Tx->>DB: create tx_in (conta B, +)
    Tx->>DB: link txs via linked_tx_id
    DB-->>Tx: transfer created
    Tx-->>API: transfer response
    API-->>Client: success
```

**Logica de Transferencia:**
- Cria duas transacoes do tipo `transfer`
- Transacao de saida: conta origem, amount negativo no calculo de saldo
- Transacao de entrada: conta destino, amount positivo no calculo de saldo
- Ambas linkadas via `linked_transaction_id` (relacao bidirecional)
- Ao deletar uma, ambas sao removidas
- Ao editar valor/data/descricao, ambas sao sincronizadas
- Transfers sao **excluidos** dos totais de receita/despesa no analytics

**Tipos de conta permitidos:**
- `wallet` (Carteira)
- `bank` (Banco)
- `investment` (Investimento)

**Nota:** Cartoes de credito (`credit_card`) nao sao permitidos em transferencias.

## Seguranca

### Autenticacao
- JWT com access token (30 min) e refresh token (7 dias)
- Tokens armazenados em memoria (Zustand)
- Refresh automatico antes da expiracao

### Autorizacao
- Role-based: `user`, `admin`
- Resource-based: `personal`, `household`
- Owner check em todas as operacoes

### Protecao de Dados
- Senhas com bcrypt
- API Keys com SHA256
- Rate limiting por IP/usuario
- CORS configurado

### Multi-tenancy
- Filtro automatico por `user_id`
- Suporte a `household` compartilhado
- Isolamento de dados por licenca

## Escalabilidade

### Horizontal
- Backend stateless (pode escalar replicas)
- Banco de dados centralizado
- Cache com React Query no frontend

### Vertical
- Async I/O no backend (FastAPI + SQLAlchemy)
- Connection pooling no banco
- Lazy loading de relacoes

### Performance
- Indices otimizados no banco
- Paginacao em todas as listagens
- Agregacoes pre-calculadas para analytics

## Monitoramento

### Logs
- Estruturados em JSON
- Niveis: DEBUG, INFO, WARNING, ERROR
- Correlacao por request_id

### Metricas
- Tempo de resposta por endpoint
- Taxa de erro por modulo
- Uso de LLM (tokens, custo)

### Alertas
- Erros de autenticacao
- Falhas de LLM
- Rate limit atingido
