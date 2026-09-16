# 01 — Comece aqui

## O que é o Biveto

O Biveto é um app de **gestão financeira pessoal e familiar** (web + PWA instalável no celular), focado no contexto brasileiro. O diferencial é a **extração inteligente de documentos**: o usuário fotografa ou envia a fatura do cartão, um cupom fiscal ou um extrato (PDF/imagem/CSV/Excel) e o app usa LLMs com visão (Google Gemini por padrão) para extrair as transações, detectar parcelamentos e reconhecer assinaturas recorrentes (Netflix, Spotify etc.).

Principais áreas funcionais:

- **Transações** — receitas, despesas e transferências entre contas.
- **Cartões de crédito e faturas** — limite, dia de fechamento/vencimento, geração e pagamento de fatura.
- **Parcelamentos** — séries de parcelas com projeção das futuras.
- **Upload/extração de documentos** — o coração do produto (maior módulo do backend).
- **Orçamento, metas e dívidas** — orçamento mensal por categoria, metas (reserva de emergência), quitação de dívidas (Snowball/Avalanche).
- **Household (família)** — contas e despesas compartilhadas entre membros, com convites e permissões.
- **Assistente IA** — chat que responde perguntas sobre as finanças do usuário.
- **Integração MCP** — expõe os dados do usuário (read-only, via API key) para assistentes como o Claude.

**Importante:** o registro público é desabilitado — só entra por **convite** ou pelo script de criação de admin (ver setup abaixo).

## Glossário do domínio

Termos que aparecem no código e nas conversas — vale internalizar antes de mexer:

| Termo | Significado |
|---|---|
| **Transação** (`Transaction`) | Um lançamento: receita, despesa ou perna de uma transferência. Transferências são um *par* de transações ligadas por `linked_transaction_id` e ficam fora dos totais de analytics. |
| **Fatura** (`CreditCardInvoice`) | O agrupamento mensal das compras de um cartão de crédito. Gerada pelo `closing_day` (dia de fechamento); vence no `due_day`. Pagar fatura com outro cartão é proibido por regra de negócio. |
| **Série de parcelas** (`InstallmentSeries`) | Uma compra parcelada ("TV 10x"). Gera N transações futuras projetadas (`is_paid=false`). O casamento entre parcelas extraídas e séries existentes usa *fuzzy matching* com tolerância de 5% no valor. |
| **Recorrente** (`RecurringTransaction`) | Assinatura ou conta fixa (aluguel, Netflix). Diferente de parcela: não tem fim definido. |
| **Documento** (`Document`) | Um arquivo enviado pelo usuário (fatura em PDF, foto de cupom). Passa pelo pipeline de extração e vira itens que o usuário confirma como transações. |
| **Extração** | O processo LLM: classificar o documento → escolher o prompt (há prompts por banco: Nubank, Itaú, Bradesco) → chamar o provider (Gemini/Mistral) → validar o resultado (`ExtractionValidator`). |
| **Household** | O grupo familiar. Contas e transações têm `ownership_type` = `personal` ou `household`. |
| **Cartão benefício** (`BenefitCard`) | VR/VA — cartão de benefício com saldo próprio. |
| **closing_day vs due_day** | Fechamento = quando a fatura "corta" (compras depois vão para a próxima); vencimento = quando se paga. |
| **Snowball / Avalanche** | Estratégias de quitação de dívidas: menor saldo primeiro (motivação) vs maior juros primeiro (matemática). |
| **API Key `biv_...`** | Chave de integração gerada pelo usuário em Configurações → API Keys. Guardada como SHA-256; usada pelo servidor MCP. |

## Stack em uma linha

**Backend:** FastAPI + SQLAlchemy 2 (async) + Alembic + Pydantic v2, Python 3.11+. **Frontend:** React 18 + TypeScript + Vite + Zustand + TanStack Query + Tailwind. **Banco:** SQLite no dev (padrão, zero setup), PostgreSQL 16 via Docker (opcional). **Jobs:** APScheduler. **E2E:** Playwright.

---

## Setup do ambiente

Pré-requisitos: **Python 3.11+**, **Node 20+**, **Git**. Docker é opcional (só se quiser PostgreSQL).

> O caminho feliz usa **SQLite** — não precisa de Docker nem de banco instalado.

### Backend (Windows / PowerShell)

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1        # se der erro de política: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head               # cria o banco SQLite (financeiro.db) com todas as tabelas
uvicorn app.main:app --reload --port 8000
```

### Backend (Linux / Mac)

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**Verificação:** abra http://localhost:8000/docs — deve aparecer o Swagger com todos os endpoints.

Com o venv ativo, instale também os hooks de pre-commit (na raiz do repo): `pip install pre-commit && pre-commit install`. Eles rodam gitleaks (segredos) e ruff (lint/format) automaticamente antes de cada commit — o mesmo que o CI cobra.

> O `Makefile` da raiz automatiza isso (`make install`, `make dev`), mas **só funciona em Linux/Mac** — no Windows use os comandos acima.

### Criar seu usuário

O registro é fechado por convite, então o primeiro usuário é criado por script (com o venv ativo, dentro de `backend/`):

```powershell
python scripts/create_admin.py voce@exemplo.com 'SuaSenha@123' 'Seu Nome'
```

A senha precisa de 8+ caracteres com maiúscula, minúscula, número e especial. O script já cria contas e categorias iniciais.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

**Verificação:** abra http://localhost:3000 (o Vite faz proxy de `/api` para o backend em `localhost:8000`) e faça login com o usuário criado acima.

### Chave de LLM (opcional, mas recomendada)

Sem chave, o app funciona normalmente **exceto** upload/extração de documentos e o chat IA. Para habilitar:

1. Gere uma chave gratuita em https://aistudio.google.com/apikey
2. Coloque em `.env`: `GOOGLE_API_KEY=sua-chave`
3. Reinicie o backend.

⚠️ **Nunca commite a chave.** O `.env` está no `.gitignore` — deixe assim. Leia a seção de segurança do [04-SUSTENTACAO.md](04-SUSTENTACAO.md).

### PostgreSQL (opcional)

Só necessário se você for trabalhar em algo sensível a diferenças de banco (a produção usa PostgreSQL):

```powershell
docker compose up -d               # sobe Postgres 16 em localhost:5433 (não 5432!)
```

E no `.env` troque o `DATABASE_URL` pela linha comentada do PostgreSQL. Rode `alembic upgrade head` de novo (o banco novo nasce vazio).

---

## Erros comuns no setup

| Sintoma | Causa/solução |
|---|---|
| `Activate.ps1 cannot be loaded` | Política de execução do PowerShell: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `alembic: command not found` | O venv não está ativo, ou você não está dentro de `backend/` |
| Login funciona mas tela vazia | Normal — banco novo não tem dados. Crie transações à mão ou envie uma fatura (com chave LLM configurada) |
| Porta 8000/3000 ocupada | `netstat -ano \| findstr :8000` e finalize o processo, ou use `--port` diferente (e ajuste o proxy no `vite.config.ts`) |
| Upload falha com erro de provider | Falta `GOOGLE_API_KEY` no `.env`, ou a chave estourou a cota gratuita (espere ou gere outra) |
| `docker compose up` conflita com Postgres local | O compose já mapeia para **5433** justamente por isso; confira se o `.env` usa 5433 |
| Erro de migração em banco antigo | Apague `backend/financeiro.db` e rode `alembic upgrade head` de novo (dev, SQLite — sem medo) |

Próximo passo: [02-MAPA-DO-CODIGO.md](02-MAPA-DO-CODIGO.md).
