"""
Módulo Accounts - Gerenciamento de Contas Bancárias

Este módulo é responsável pelo gerenciamento de contas bancárias e carteiras
do usuário, incluindo:
- CRUD de contas
- Cálculo de saldos
- Suporte a contas pessoais e familiares (household)

Tipos de contas suportados:
- wallet: Carteira/Dinheiro em espécie
- bank: Conta bancária
- credit_card: Cartão de crédito
- investment: Investimentos

Dependências:
- models: Account (centralizado em app.models)
- modules: household (para contas compartilhadas)
"""

from app.modules.accounts.routers.accounts import router
from app.modules.accounts.schemas.account import (
    AccountBase,
    AccountCreate,
    AccountResponse,
    AccountUpdate,
)

__all__ = [
    "router",
    "AccountBase",
    "AccountCreate",
    "AccountUpdate",
    "AccountResponse",
]
