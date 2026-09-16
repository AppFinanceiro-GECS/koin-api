"""
Modulo Categories - Gerenciamento de Categorias

Este modulo e responsavel pelo gerenciamento de categorias de transacoes
do usuario, incluindo:
- CRUD de categorias personalizadas
- Categorias padrao do sistema (is_system=True)
- Hierarquia de categorias (parent_id)

Tipos de categorias:
- expense: Categorias de despesas
- income: Categorias de receitas

Dependencias:
- models: Category (centralizado em app.models)
"""

from app.modules.categories.routers.categories import router
from app.modules.categories.schemas.category import (
    CategoryBase,
    CategoryCreate,
    CategoryResponse,
)

__all__ = [
    "router",
    "CategoryBase",
    "CategoryCreate",
    "CategoryResponse",
]
