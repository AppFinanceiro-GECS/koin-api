# 02 — Mapa do código

## Visão geral do repositório

```
koin-app/
├── backend/            # API FastAPI (Python) — serve também o frontend buildado em produção
│   ├── app/
│   │   ├── main.py     # entrypoint: middlewares, startup, scheduler
│   │   ├── core/       # config, database, segurança (JWT), crypto, deps
│   │   ├── models/     # TODOS os models SQLAlchemy (30 arquivos) ficam AQUI, centralizados
│   │   ├── routers/    # apenas o agregador que registra os routers de todos os módulos
│   │   └── modules/    # 29 módulos de feature (ver tabela abaixo)
│   ├── alembic/        # migrações de banco
│   ├── scripts/        # scripts operacionais (create_admin, cleanup_uploads...)
│   └── tests/          # pytest (SQLite in-memory)
├── frontend/           # SPA React + TS + Vite
│   ├── src/pages/      # 1 arquivo por rota (37 páginas)
│   ├── src/components/ # componentes globais + subpastas por domínio
│   ├── src/stores/     # 8 stores Zustand (auth, theme, toast...)
│   ├── src/services/   # camada de API (axios) — api.ts + módulos temáticos
│   └── e2e/            # testes Playwright (page objects em e2e/pages/)
├── mcp-koin-db/      # servidor MCP read-only que consome a API via API key
├── docs/               # documentação (você está aqui)
└── docker-compose.yml  # só o PostgreSQL de dev
```

## Anatomia de um módulo do backend

Cada módulo em `app/modules/<nome>/` segue o padrão **router fino, service gordo**:

```
modules/<nome>/
├── routers/    # endpoints FastAPI: validam entrada, chamam o service, traduzem exceções em HTTP
├── services/   # TODA a regra de negócio e as queries SQLAlchemy
├── schemas/    # Pydantic v2: formatos de request/response
├── models/     # ⚠️ quase sempre VAZIO — os models de verdade estão em app/models/ (centralizados)
└── prompts/    # opcional (documents, grocery): prompts de LLM como arquivos Markdown
```

Jobs agendados não ficam nos módulos: vivem em `app/core/scheduler.py` (APScheduler), que importa os services dos módulos.

**Fluxo de uma requisição** (ex.: `POST /api/v1/transactions`):

1. `app/main.py` aplica middlewares (security headers, CORS, rate limit) e monta o `api_router` com prefixo `/api/v1`.
2. `app/routers/__init__.py` é o agregador — todo router de módulo é registrado ali (se você criar um router novo e esquecer de registrá-lo aqui, ele não existe).
3. O router injeta `CurrentUser` e `DbSession` (aliases em `app/core/deps.py`), instancia o service e delega.
4. O service faz as queries (SQLAlchemy async) e retorna schemas Pydantic.
5. A sessão de banco faz **auto-commit no fim da request** (e rollback em exceção) — você raramente chama `commit()` em service de request; scripts e jobs são exceção.

**Autenticação:** dois esquemas coexistem — JWT Bearer (`CurrentUser`, para o frontend) e API Key `biv_...` (`ApiKeyUser`, para integrações/MCP). JWT é HS256 com access de 30min e refresh de 7 dias; o frontend renova sozinho via interceptor do axios.

## Os 29 módulos

Núcleo (onde a maioria das tarefas acontece):

| Módulo | O que faz |
|---|---|
| `auth` | Login, registro por convite, refresh, reset de senha |
| `accounts` | Contas/carteiras — saldo é **calculado pelas transações**, não armazenado |
| `transactions` | CRUD de transações, confirmação de itens extraídos, transferências |
| `documents` | Upload + pipeline de extração LLM (maior módulo, ~7.700 linhas) |
| `credit_cards` | Cartões e faturas (atenção: `routers/invoices.py` tem muita lógica de negócio no router — dívida conhecida) |
| `installments` | Séries de parcelas, projeções, detecção de duplicatas (fuzzy/rapidfuzz) |
| `categories` | Categorias (sistema + personalizadas) |

Demais features: `budgets`, `goals`, `debts`, `income`, `income_splits`, `recurring`, `benefit_cards`, `receipts`, `grocery` (mercado/listas), `analytics`, `calendar`, `chat` (assistente IA), `automations`, `notifications`, `gamification`, `household`, `review` (revisão semanal), `known_services`, `mcp`, `api_keys`, `admin`.

## Frontend — onde as coisas ficam

- **Página nova** = arquivo em `src/pages/` + rota em `src/App.tsx` + entrada no menu em `src/components/Layout.tsx`.
- **Chamadas de API**: `src/services/api.ts` tem a instância axios com interceptors de auth/refresh; os módulos (`transactions.api.ts` etc.) são wrappers finos. O padrão preferido nas páginas é **TanStack Query** (`useQuery`/`useMutation`) — algumas páginas antigas ainda usam `useEffect` + axios direto; ao mexer nelas, migre para react-query.
- **Estado global**: Zustand em `src/stores/` (só o que precisa sobreviver entre páginas: auth, tema, toasts). Estado de servidor fica no react-query, não em store.
- **Estilo**: Tailwind puro, sem biblioteca de componentes — copie padrões visuais de páginas existentes.
- **PWA**: service worker manual em `public/sw.js` — ao mudar assets cacheados, é preciso *bumpar* o `CACHE_VERSION` manualmente.

## "Quero mexer em X — começo por onde?"

| Tarefa | Backend | Frontend |
|---|---|---|
| Bug em transação/transferência | `modules/transactions/services/transaction_service.py` | `pages/Transactions.tsx` |
| Fatura calculando errado | `modules/credit_cards/` (routers/invoices.py + services) | `pages/Invoices.tsx` |
| Extração de documento errando | `modules/documents/services/` — classificador → prompt (`prompts/banks/*.md`) → provider → `extraction_validator.py` | `pages/Upload.tsx` |
| Parcelas duplicadas/erradas | `modules/installments/` (fuzzy match) | `components/installments/` |
| Chat IA respondendo errado | `modules/chat/services/financial_agent_service.py` (3.500 linhas — cuidado) | `components/FloatingAssistant.tsx` |
| Orçamento/metas/dívidas | `modules/budgets/` / `goals/` / `debts/` | `pages/Budget.tsx` / `Goals.tsx` / `Debts.tsx` |
| Família/compartilhamento | `modules/household/` | `pages/Family.tsx` |
| Notificações | `modules/notifications/` (⚠️ entrega por email/push está incompleta — TODOs) | `components/notifications/` |
| Coisas de admin | `modules/admin/` | `pages/admin/` |

## Como adicionar uma feature de ponta a ponta

Roteiro para uma entidade nova (ex.: "assinatura de academia"):

1. **Model** — crie em `app/models/` e exporte no `__init__.py` de lá.
2. **Migração** — `alembic revision --autogenerate -m "add academia"` (confira o arquivo gerado! o autogenerate erra em renomes) e `alembic upgrade head`.
3. **Módulo** — crie `modules/academia/` com `schemas/`, `services/`, `routers/` seguindo um módulo pequeno como referência (`categories` é o mais simples).
4. **Registro** — adicione o router no agregador `app/routers/__init__.py` com prefixo e tag.
5. **Teste** — adicione um teste em `tests/` (o `conftest.py` dá `db_session` e `client` prontos com SQLite in-memory).
6. **API client** — adicione as chamadas em `frontend/src/services/`.
7. **Página** — crie em `src/pages/`, registre a rota em `App.tsx` e o item de menu em `Layout.tsx`; use `useQuery`/`useMutation`.
8. Rode `ruff check app/` + `pytest` (backend) e `npm run lint` + `npx tsc --noEmit && npm run build` (frontend) antes do PR — é exatamente o que o CI verifica.

Próximo: [03-DECISOES-E-MOTIVOS.md](03-DECISOES-E-MOTIVOS.md) para entender os porquês.
