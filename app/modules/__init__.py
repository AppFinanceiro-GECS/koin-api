"""
Biveto App - Modular Backend Architecture

Este pacote contém todos os módulos de domínio da aplicação, organizados
seguindo os princípios de Domain-Driven Design (DDD) e Modular Monolith.

Cada módulo é independente e pode ser extraído como microserviço no futuro.

Módulos disponíveis:
- auth: Autenticação, usuários e licenças
- household: Gestão de famílias/household
- accounts: Contas bancárias e carteiras
- credit_cards: Cartões de crédito e faturas
- transactions: Transações financeiras
- categories: Categorias e regras de categorização
- documents: Upload e extração de documentos (OCR/LLM)
- analytics: Análises e relatórios financeiros
- budgets: Controle de orçamentos
- goals: Metas financeiras
- debts: Gestão de dívidas
- recurring: Transações recorrentes
- income: Fontes de receita
- installments: Parcelas
- chat: Assistente financeiro IA
- admin: Administração do sistema
- api_keys: Gerenciamento de API Keys para integrações
- mcp: Endpoints para Model Context Protocol (Claude Code)

Estrutura de cada módulo:
/module_name/
    __init__.py     # Exports públicos do módulo
    /models/        # Referência aos models (centralizados em app.models)
    /schemas/       # Schemas Pydantic para API
    /services/      # Lógica de negócio
    /routers/       # Endpoints FastAPI
    README.md       # Documentação do módulo
"""

# Modules são importados sob demanda para evitar imports circulares
# Use: from app.modules.auth import router, schemas, etc.

__all__ = [
    "auth",
    "household",
    "accounts",
    "credit_cards",
    "transactions",
    "categories",
    "documents",
    "analytics",
    "budgets",
    "goals",
    "debts",
    "recurring",
    "income",
    "installments",
    "chat",
    "admin",
    "api_keys",
    "mcp",
]
