"""
Módulos ligados por ambiente (#42): ENABLED_MODULES.

Módulo desligado não registra rotas nem jobs do scheduler; o código continua no
repositório. Valores aceitos: "all" (padrão), "mvp" (Parte 1 do MVP) ou uma lista
separada por vírgulas, que pode misturar os dois atalhos (ex.: "mvp,goals").
"""

from app.core.config import settings

ALL_MODULES = frozenset(
    {
        "auth",
        "users",
        "accounts",
        "categories",
        "transactions",
        "documents",
        "analytics",
        "installments",
        "budgets",
        "goals",
        "debts",
        "recurring",
        "family",
        "household-migration",
        "chat",
        "admin",
        "credit-cards",
        "invoices",
        "benefit-cards",
        "income-sources",
        "income-splits",
        "api-keys",
        "mcp",
        "notifications",
        "calendar",
        "automations",
        "review",
        "grocery",
        "receipts",
        "gamification",
    }
)

# Parte 1 do MVP. recurring entra porque a assinatura criada junto com a transação
# (create_recurring) depende do job que gera os lançamentos do mês.
MVP_MODULES = frozenset(
    {
        "auth",
        "users",
        "accounts",
        "categories",
        "transactions",
        "documents",
        "installments",
        "credit-cards",
        "invoices",
        "analytics",
        "notifications",
        "recurring",
        "family",
        "admin",
    }
)

# Sem eles a API não autentica ninguém
ALWAYS_ON = frozenset({"auth", "users"})

PRESETS = {"all": ALL_MODULES, "mvp": MVP_MODULES}


def parse_modules(value: str | None) -> frozenset[str]:
    names = [n.strip().lower() for n in (value or "all").split(",") if n.strip()]
    enabled: set[str] = set(ALWAYS_ON)
    for name in names or ["all"]:
        if name in PRESETS:
            enabled |= PRESETS[name]
        elif name in ALL_MODULES:
            enabled.add(name)
        else:
            # erro de digitação desligaria um módulo sem ninguém perceber
            raise ValueError(
                f"ENABLED_MODULES: módulo desconhecido {name!r}. "
                f"Use all, mvp ou: {', '.join(sorted(ALL_MODULES))}"
            )
    return frozenset(enabled)


def enabled_modules() -> frozenset[str]:
    return parse_modules(settings.enabled_modules)


def is_enabled(module: str) -> bool:
    return module in enabled_modules()
