"""
Routers do modulo auth.
Exporta os routers de autenticacao e usuarios.
"""

from app.modules.auth.routers.auth import router as auth_router
from app.modules.auth.routers.users import router as users_router

__all__ = [
    "auth_router",
    "users_router",
]
