# biveto-api

[![CI](https://github.com/AppFinanceiro-GECS/biveto-api/actions/workflows/ci.yml/badge.svg)](https://github.com/AppFinanceiro-GECS/biveto-api/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Backend e infraestrutura do **Biveto**, app de gestão financeira pessoal (Android/iOS). API REST em FastAPI, PostgreSQL e deploy com Docker Compose numa VPS.

O app mobile (React Native/Expo) fica em **[biveto-app](https://github.com/AppFinanceiro-GECS/biveto-app)**.

```
 biveto-app (Android/iOS) ──HTTPS──▶ Caddy :443 ──▶ api :8000 (FastAPI + APScheduler) ──▶ db (PostgreSQL 16)
                                                        │
                                                        └── volume uploads (faturas/cupons)
```

## Subir com Docker (recomendado)

Requisitos: Docker + Docker Compose v2.

```bash
make up          # cria .env (com SECRET_KEY aleatório) e sobe API + Postgres
```

Sem `make`: `cp .env.example .env` (troque o `SECRET_KEY`) e `docker compose up -d --build`.

| O quê | Onde |
|---|---|
| API | http://localhost:8000/api/v1 |
| Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Postgres | `localhost:5433` (user/senha do `.env`) |

As migrações Alembic rodam sozinhas no start do container (`RUN_MIGRATIONS=false` desliga).

Criar o primeiro usuário (admin):

```bash
make create-admin email=voce@exemplo.com senha='SenhaForte123' nome='Seu Nome'
```

Outros alvos: `make logs`, `make ps`, `make shell`, `make migrate`, `make down`. Lista completa: `make help`.

> Para o app no celular físico acessar a API local, use o IP da sua máquina na rede (ex.: `http://192.168.0.10:8000`) no `EXPO_PUBLIC_API_URL` do biveto-app.

## Produção (VPS)

```bash
# no .env: DEBUG=false, ENVIRONMENT=production, SECRET_KEY forte, POSTGRES_PASSWORD forte, API_DOMAIN=api.seudominio.com
make prod-up     # docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

O override de produção coloca o **Caddy** na frente com HTTPS automático (Let's Encrypt) e fecha as portas da API e do banco. Passo a passo, backup e atualização: **[docs/infra/DEPLOY.md](docs/infra/DEPLOY.md)**.

A cada push na `main`, o CI publica a imagem em `ghcr.io/appfinanceiro-gecs/biveto-api` (`latest` e `sha-xxxxxxx`).

## Desenvolvimento sem Docker

```bash
make install     # venv + dependências (Python 3.11+)
make dev         # alembic upgrade head + uvicorn --reload (SQLite por padrão)
make lint test   # o mesmo que o CI cobra
```

OCR local precisa de `tesseract` (com idioma `por`) e `zbar` instalados no sistema; no Docker já vêm na imagem.

## Estrutura

```
app/
  core/          config, banco, segurança, rate limit, scheduler (APScheduler)
  models/        models SQLAlchemy (centralizados)
  modules/       um diretório por domínio: auth, accounts, transactions, documents, credit_cards...
  routers/       agrega os routers dos módulos em /api/v1
alembic/         migrações
scripts/         scripts operacionais (create_admin, cleanup_uploads, backfills)
tests/           pytest
tools/           mcp-biveto-db: servidor MCP read-only que consome a API
docker/          entrypoint do container
Dockerfile, docker-compose.yml, docker-compose.prod.yml, Caddyfile
docs/            infra, arquitetura, módulos, regras de negócio, onboarding
```

## Stack

| | |
|---|---|
| API | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic |
| Banco | PostgreSQL 16 (Docker/produção), SQLite (dev local e testes) |
| Auth | JWT (access + refresh) e API Keys |
| IA | Google Gemini (padrão) ou Mistral para extração de documentos e chat |
| Jobs | APScheduler dentro do processo da API (por isso **1 worker** uvicorn) |
| Infra | Docker, Docker Compose, Caddy, GitHub Actions, GHCR |

## Documentação

- [docs/infra/DEPLOY.md](docs/infra/DEPLOY.md): deploy na VPS, backup, atualização e rollback
- [docs/onboarding/](docs/onboarding/README.md): onboarding do time (domínio, mapa do código, decisões)
- [docs/README.md](docs/README.md): índice completo
- [CONTRIBUTING.md](CONTRIBUTING.md): fluxo de branches, PRs e o que o CI cobra

## Licença

[MIT](LICENSE)
