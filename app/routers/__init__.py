"""
API Router Configuration

Este arquivo configura todos os routers da API, importando dos módulos modularizados.
A estrutura modular permite fácil manutenção e futura extração para microserviços.
"""

from fastapi import APIRouter

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

api_router = APIRouter()

# Auth module
api_router.include_router(auth_router, prefix="/auth", tags=["Autenticação"])
api_router.include_router(users_router, prefix="/users", tags=["Usuários"])

# Accounts module
api_router.include_router(accounts_router, prefix="/accounts", tags=["Contas"])

# Categories module
api_router.include_router(categories_router, prefix="/categories", tags=["Categorias"])

# Transactions module
api_router.include_router(transactions_router, prefix="/transactions", tags=["Transações"])

# Documents module
api_router.include_router(documents_router, prefix="/documents", tags=["Documentos"])

# Analytics module
api_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])

# Installments module
api_router.include_router(installments_router, prefix="/installments", tags=["Parcelas"])

# Budgets module
api_router.include_router(budgets_router, prefix="/budgets", tags=["Orçamentos"])

# Goals module
api_router.include_router(goals_router, prefix="/goals", tags=["Metas"])

# Debts module
api_router.include_router(debts_router, prefix="/debts", tags=["Dívidas"])

# Recurring module
api_router.include_router(recurring_router, prefix="/recurring", tags=["Recorrentes"])

# Household module
api_router.include_router(family_router, prefix="/family", tags=["Familia"])
api_router.include_router(
    migration_router, prefix="/household/migration", tags=["Migração Household"]
)

# Chat module
api_router.include_router(chat_router, prefix="/chat", tags=["Chat - Agente IA"])

# Admin module
api_router.include_router(admin_router, prefix="/admin", tags=["Admin - Gestao"])

# Credit Cards module
api_router.include_router(credit_cards_router, prefix="/credit-cards", tags=["Cartões de Crédito"])
api_router.include_router(invoices_router, prefix="/invoices", tags=["Faturas"])

# Benefit Cards module
api_router.include_router(
    benefit_cards_router, prefix="/benefit-cards", tags=["Cartões de Benefício"]
)

# Income module
api_router.include_router(
    income_sources_router, prefix="/income-sources", tags=["Fontes de Receita"]
)
api_router.include_router(
    income_splits_router, prefix="/income-split-rules", tags=["Regras de Divisão de Receita"]
)

# API Keys module (para integrações externas)
api_router.include_router(api_keys_router, tags=["API Keys"])

# MCP module (consultas via Claude Code)
api_router.include_router(mcp_router, tags=["MCP"])

# Notifications module
api_router.include_router(notifications_router, prefix="/notifications", tags=["Notificações"])

# Calendar module
api_router.include_router(calendar_router, prefix="/calendar", tags=["Calendário de Caixa"])

# Envelopes module removed - functionality merged into Budgets module

# Automations module
api_router.include_router(automations_router, prefix="/automations", tags=["Automações"])

# Review module
api_router.include_router(review_router, prefix="/review", tags=["Revisão Semanal"])

# Grocery module
api_router.include_router(grocery_router, prefix="/grocery", tags=["Mercado"])

# Receipts module
api_router.include_router(receipts_router, prefix="/receipts", tags=["Compras"])

# Gamification module
api_router.include_router(gamification_router, prefix="/gamification", tags=["Gamificação"])
