# Modulo Categories

## Descricao
Modulo responsavel pelo gerenciamento de categorias de transacoes. Suporta categorias do sistema (padrao) e categorias personalizadas criadas pelo usuario, com hierarquia opcional.

## Responsabilidades
- CRUD de categorias personalizadas
- Listagem de categorias do sistema (is_system=True)
- Suporte a hierarquia de categorias (parent_id)
- Separacao entre categorias de receita e despesa

## Estrutura
```
categories/
├── __init__.py
├── schemas/
│   └── category.py       # CategoryBase, CategoryCreate, CategoryResponse
├── services/             # (logica no router)
└── routers/
    └── categories.py     # Endpoints de categorias
```

## Dependencias
- **Models**: `Category`
- **Outros Modulos**: Nenhum
- **Core**: `deps` (CurrentUser, DbSession)

## Tipos de Categoria
- `expense`: Categorias de despesas
- `income`: Categorias de receitas

## Endpoints

### Router Categories (`/categories`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `` | Lista todas as categorias do usuario (padrao + personalizadas) |
| POST | `` | Cria uma categoria personalizada |
| DELETE | `/{category_id}` | Remove categoria personalizada (nao do sistema) |

## Uso
```python
from app.modules.categories import (
    router,
    CategoryBase,
    CategoryCreate,
    CategoryResponse,
)
```

## Categorias do Sistema
As categorias do sistema (`is_system=True`) sao criadas automaticamente durante o setup inicial do usuario e nao podem ser removidas. Exemplos:
- Alimentacao
- Transporte
- Moradia
- Lazer
- Saude
- Educacao
- Salario
- Investimentos
