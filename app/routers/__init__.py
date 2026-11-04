"""
API Router Configuration

Este arquivo configura todos os routers da API, importando dos módulos modularizados.
A estrutura modular permite fácil manutenção e futura extração para microserviços.
"""

from fastapi import APIRouter

from app.core.modules import enabled_modules
from app.modules.accounts.routers.accounts import router as accounts_router
from app.modules.admin.routers.admin import router as admin_router
from app.modules.analytics.routers.analytics import router as analytics_router
from app.modules.api_keys.routers.api_keys import router as api_keys_router

# Import routers from modular structure
from app.modules.auth.routers.auth import router as auth_router
from app.modules.auth.routers.users import router as users_router

# Envelopes module removed - functionality merged into Budgets module
from app.modules.automations.routers.automations import router as automations_router
from app.modules.benefit_cards.routers.benefit_cards import router as benefit_cards_router
from app.modules.budgets.routers.budgets import router as budgets_router
from app.modules.calendar.routers.cash_calendar import router as calendar_router
from app.modules.categories.routers.categories import router as categories_router
from app.modules.chat.routers.chat import router as chat_router
from app.modules.credit_cards.routers.credit_cards import router as credit_cards_router
from app.modules.credit_cards.routers.invoices import router as invoices_router
from app.modules.debts.routers.debts import router as debts_router
from app.modules.documents.routers.documents import router as documents_router
from app.modules.gamification.routers.gamification import router as gamification_router
from app.modules.goals.routers.goals import router as goals_router
from app.modules.grocery.routers.grocery import router as grocery_router
from app.modules.household.routers.family import router as family_router
from app.modules.household.routers.migration import router as migration_router
from app.modules.income.routers.income_sources import router as income_sources_router
from app.modules.income_splits.routers.income_splits import router as income_splits_router
from app.modules.installments.routers.installments import router as installments_router
from app.modules.mcp.routers.mcp import router as mcp_router
from app.modules.notifications.routers.notifications import router as notifications_router
from app.modules.receipts.routers.receipts import router as receipts_router
from app.modules.recurring.routers.recurring import router as recurring_router
from app.modules.review.routers.review import router as review_router
from app.modules.transactions.routers.transactions import router as transactions_router

# (módulo, router, prefixo, tags). Módulo desligado em ENABLED_MODULES não é registrado (#42)
ROUTES = [
    ("auth", auth_router, "/auth", ["Autenticação"]),
    ("users", users_router, "/users", ["Usuários"]),
    ("accounts", accounts_router, "/accounts", ["Contas"]),
    ("categories", categories_router, "/categories", ["Categorias"]),
    ("transactions", transactions_router, "/transactions", ["Transações"]),
    ("documents", documents_router, "/documents", ["Documentos"]),
    ("analytics", analytics_router, "/analytics", ["Analytics"]),
    ("installments", installments_router, "/installments", ["Parcelas"]),
    ("budgets", budgets_router, "/budgets", ["Orçamentos"]),
    ("goals", goals_router, "/goals", ["Metas"]),
    ("debts", debts_router, "/debts", ["Dívidas"]),
    ("recurring", recurring_router, "/recurring", ["Recorrentes"]),
    ("family", family_router, "/family", ["Familia"]),
    ("household-migration", migration_router, "/household/migration", ["Migração Household"]),
    ("chat", chat_router, "/chat", ["Chat - Agente IA"]),
    ("admin", admin_router, "/admin", ["Admin - Gestao"]),
    ("credit-cards", credit_cards_router, "/credit-cards", ["Cartões de Crédito"]),
    ("invoices", invoices_router, "/invoices", ["Faturas"]),
    ("benefit-cards", benefit_cards_router, "/benefit-cards", ["Cartões de Benefício"]),
    ("income-sources", income_sources_router, "/income-sources", ["Fontes de Receita"]),
    (
        "income-splits",
        income_splits_router,
        "/income-split-rules",
        ["Regras de Divisão de Receita"],
    ),
    # API Keys (integrações externas) e MCP (consultas via Claude Code) definem o próprio prefixo
    ("api-keys", api_keys_router, "", ["API Keys"]),
    ("mcp", mcp_router, "", ["MCP"]),
    ("notifications", notifications_router, "/notifications", ["Notificações"]),
    ("calendar", calendar_router, "/calendar", ["Calendário de Caixa"]),
    # Envelopes module removed - functionality merged into Budgets module
    ("automations", automations_router, "/automations", ["Automações"]),
    ("review", review_router, "/review", ["Revisão Semanal"]),
    ("grocery", grocery_router, "/grocery", ["Mercado"]),
    ("receipts", receipts_router, "/receipts", ["Compras"]),
    ("gamification", gamification_router, "/gamification", ["Gamificação"]),
]


def build_api_router(modules: frozenset[str]) -> APIRouter:
    router = APIRouter()
    for module, module_router, prefix, tags in ROUTES:
        if module in modules:
            router.include_router(module_router, prefix=prefix, tags=tags)
    return router


api_router = build_api_router(enabled_modules())
