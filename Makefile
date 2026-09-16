# Makefile POSIX (Linux/Mac/WSL/Git Bash).
.PHONY: help env up down logs ps restart migrate shell create-admin prod-up prod-down prod-logs \
        install dev test lint format mcp-server clean

COMPOSE      := docker compose
COMPOSE_PROD := docker compose -f docker-compose.yml -f docker-compose.prod.yml

help: ## Mostra esta ajuda
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[33m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

env: ## Cria o .env a partir do .env.example com SECRET_KEY aleatório
	@test -f .env && echo ".env já existe, nada feito" || \
	  (sed "s#^SECRET_KEY=.*#SECRET_KEY=$$(openssl rand -hex 32)#" .env.example > .env && echo ".env criado")

# ==================== Docker (dev) ====================

up: env ## Sobe API + Postgres (http://localhost:8000/docs)
	$(COMPOSE) up -d --build

down: ## Para os containers
	$(COMPOSE) down

logs: ## Segue os logs da API
	$(COMPOSE) logs -f api

ps: ## Status dos containers
	$(COMPOSE) ps

restart: ## Reinicia a API
	$(COMPOSE) restart api

migrate: ## Roda alembic upgrade head no container
	$(COMPOSE) exec api alembic upgrade head

shell: ## Shell dentro do container da API
	$(COMPOSE) exec api sh

create-admin: ## Cria admin (uso: make create-admin email=x senha=y nome=z)
	$(COMPOSE) exec api python scripts/create_admin.py "$(email)" "$(senha)" "$(nome)"

# ==================== Docker (produção/VPS) ====================

prod-up: ## Sobe em produção com Caddy + HTTPS (requer API_DOMAIN e DEBUG=false no .env)
	$(COMPOSE_PROD) up -d --build

prod-down: ## Para a stack de produção
	$(COMPOSE_PROD) down

prod-logs: ## Logs da stack de produção
	$(COMPOSE_PROD) logs -f

# ==================== Sem Docker ====================

install: ## Cria venv e instala dependências
	python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt ruff

dev: env ## Roda a API local com reload (SQLite)
	. venv/bin/activate && alembic upgrade head && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test: ## Roda os testes
	. venv/bin/activate && pytest

lint: ## Lint + checagem de formatação (o mesmo que o CI cobra)
	. venv/bin/activate && ruff check . && ruff format --check .

format: ## Formata o código
	. venv/bin/activate && ruff check --fix . && ruff format .

mcp-server: ## Servidor MCP read-only (requer API rodando e BIVETO_API_KEY)
	cd tools/mcp-biveto-db && pip install -q -r requirements.txt && python server.py

clean: ## Remove caches
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
