"""
Services do modulo auth.
Exporta os servicos de autenticacao, usuario e setup inicial.
"""

from app.modules.auth.services.auth_service import AuthService
from app.modules.auth.services.user_service import UserService
from app.modules.auth.services.user_setup import (
    DEFAULT_ACCOUNTS,
    DEFAULT_CATEGORIES,
    create_default_accounts,
    create_default_categories,
    setup_new_user,
)

__all__ = [
    "AuthService",
    "UserService",
    "setup_new_user",
    "create_default_accounts",
    "create_default_categories",
    "DEFAULT_ACCOUNTS",
    "DEFAULT_CATEGORIES",
]
