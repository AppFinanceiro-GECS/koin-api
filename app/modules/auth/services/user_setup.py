"""
Servico para configuracao inicial de novos usuarios.
Cria contas e categorias padrao.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.category import Category, CategoryType

# Contas padrão para novos usuários
DEFAULT_ACCOUNTS = [
    {
        "name": "Carteira",
        "type": AccountType.WALLET,
        "balance": 0,
        "color": "#22c55e",
        "icon": "wallet",
    },
    {
        "name": "Banco",
        "type": AccountType.BANK,
        "balance": 0,
        "color": "#3b82f6",
        "icon": "building",
    },
]

# Categorias padrão para novos usuários
# Baseado no método 50-30-20 e apps populares (Mobills, Organizze, GuiaBolso)
# Referência: https://www.mobills.com.br/blog/planejamento-financeiro/regra-50-30-20/
DEFAULT_CATEGORIES = [
    # ========================================
    # DESPESAS ESSENCIAIS (Necessidades - 50%)
    # ========================================
    {"name": "Moradia", "type": CategoryType.EXPENSE, "icon": "home", "color": "#ef4444"},
    {
        "name": "Supermercado",
        "type": CategoryType.EXPENSE,
        "icon": "shopping-cart",
        "color": "#f97316",
    },
    {"name": "Transporte", "type": CategoryType.EXPENSE, "icon": "car", "color": "#eab308"},
    {"name": "Saúde", "type": CategoryType.EXPENSE, "icon": "heart-pulse", "color": "#22c55e"},
    {
        "name": "Educação",
        "type": CategoryType.EXPENSE,
        "icon": "graduation-cap",
        "color": "#06b6d4",
    },
    {
        "name": "Contas e Serviços",
        "type": CategoryType.EXPENSE,
        "icon": "file-text",
        "color": "#6366f1",
    },
    # ========================================
    # DESPESAS VARIÁVEIS (Desejos - 30%)
    # ========================================
    {
        "name": "Alimentação Fora",
        "type": CategoryType.EXPENSE,
        "icon": "utensils",
        "color": "#ec4899",
    },
    {"name": "Lazer", "type": CategoryType.EXPENSE, "icon": "gamepad-2", "color": "#8b5cf6"},
    {"name": "Vestuário", "type": CategoryType.EXPENSE, "icon": "shirt", "color": "#14b8a6"},
    {
        "name": "Beleza e Cuidados",
        "type": CategoryType.EXPENSE,
        "icon": "sparkles",
        "color": "#f472b6",
    },
    {"name": "Assinaturas", "type": CategoryType.EXPENSE, "icon": "tv", "color": "#a855f7"},
    {"name": "Compras Online", "type": CategoryType.EXPENSE, "icon": "package", "color": "#0ea5e9"},
    # ========================================
    # OUTRAS DESPESAS
    # ========================================
    {"name": "Pet", "type": CategoryType.EXPENSE, "icon": "paw-print", "color": "#84cc16"},
    {"name": "Filhos", "type": CategoryType.EXPENSE, "icon": "baby", "color": "#fbbf24"},
    {
        "name": "Presentes e Doações",
        "type": CategoryType.EXPENSE,
        "icon": "gift",
        "color": "#fb7185",
    },
    {
        "name": "Dízimo/Ofertas",
        "type": CategoryType.EXPENSE,
        "icon": "heart-handshake",
        "color": "#8b5cf6",
    },
    {
        "name": "Impostos e Taxas",
        "type": CategoryType.EXPENSE,
        "icon": "landmark",
        "color": "#94a3b8",
    },
    {"name": "Viagens", "type": CategoryType.EXPENSE, "icon": "plane", "color": "#38bdf8"},
    {"name": "Outros", "type": CategoryType.EXPENSE, "icon": "more-horizontal", "color": "#64748b"},
    # ========================================
    # RECEITAS
    # ========================================
    {"name": "Salário", "type": CategoryType.INCOME, "icon": "briefcase", "color": "#22c55e"},
    {"name": "Freelance", "type": CategoryType.INCOME, "icon": "laptop", "color": "#3b82f6"},
    {"name": "Rendimentos", "type": CategoryType.INCOME, "icon": "trending-up", "color": "#8b5cf6"},
    {"name": "Benefícios", "type": CategoryType.INCOME, "icon": "credit-card", "color": "#f97316"},
    {"name": "Vendas", "type": CategoryType.INCOME, "icon": "store", "color": "#14b8a6"},
    {
        "name": "Aluguel Recebido",
        "type": CategoryType.INCOME,
        "icon": "building",
        "color": "#eab308",
    },
    {"name": "Presente Recebido", "type": CategoryType.INCOME, "icon": "gift", "color": "#ec4899"},
    {"name": "Reembolso", "type": CategoryType.INCOME, "icon": "rotate-ccw", "color": "#06b6d4"},
    {"name": "Outros", "type": CategoryType.INCOME, "icon": "plus-circle", "color": "#64748b"},
]


async def create_default_accounts(db: AsyncSession, user_id: int) -> list[Account]:
    """Cria contas padrão para um novo usuário."""
    accounts = []
    for acc_data in DEFAULT_ACCOUNTS:
        account = Account(
            user_id=user_id,
            name=acc_data["name"],
            type=acc_data["type"].value,
            balance=acc_data["balance"],
            color=acc_data["color"],
            icon=acc_data["icon"],
        )
        db.add(account)
        accounts.append(account)

    await db.flush()
    return accounts


async def create_default_categories(db: AsyncSession, user_id: int) -> list[Category]:
    """Cria categorias padrão para um novo usuário."""
    categories = []
    for cat_data in DEFAULT_CATEGORIES:
        category = Category(
            user_id=user_id,
            name=cat_data["name"],
            type=cat_data["type"].value,
            icon=cat_data["icon"],
            color=cat_data["color"],
            is_system=True,  # Marca como categoria do sistema
        )
        db.add(category)
        categories.append(category)

    await db.flush()
    return categories


async def setup_new_user(db: AsyncSession, user_id: int) -> dict:
    """
    Configura dados iniciais para um novo usuário.
    Cria contas e categorias padrão.
    """
    accounts = await create_default_accounts(db, user_id)
    categories = await create_default_categories(db, user_id)

    return {
        "accounts_created": len(accounts),
        "categories_created": len(categories),
    }
