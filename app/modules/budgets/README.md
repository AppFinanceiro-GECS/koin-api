# Modulo Budgets

## Descricao
Modulo responsavel pelo controle de orcamentos mensais. Permite definir limites por categoria e acompanhar o progresso dos gastos em relacao ao planejado.

## Responsabilidades
- CRUD de orcamentos mensais
- Definicao de limites por categoria
- Calculo de gastos reais vs planejados
- Copia de orcamento entre meses
- Comparativo orcado vs realizado
- Resumo para dashboard

## Estrutura
```
budgets/
├── __init__.py
├── schemas/
│   └── budget.py         # BudgetCreate, BudgetResponse, BudgetItemResponse, BudgetSummary
├── services/
│   └── budget_service.py # BudgetService (CRUD, calculos, copia)
└── routers/
    └── budgets.py        # Endpoints de orcamento
```

## Dependencias
- **Models**: `Budget`, `BudgetItem`, `Category`, `Transaction`
- **Outros Modulos**: Nenhum
- **Core**: `deps` (CurrentUser, DbSession)

## Endpoints

### Router Budgets (`/budgets`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `` | Retorna orcamento do mes (cria se nao existir) |
| POST | `` | Cria orcamento com itens por categoria |
| PATCH | `` | Atualiza configuracoes do orcamento |
| GET | `/summary` | Resumo do orcamento para dashboard |
| GET | `/comparison` | Compara orcado vs realizado por categoria |
| POST | `/copy` | Copia orcamento de outro mes |
| POST | `/items` | Adiciona item (categoria) ao orcamento |
| PATCH | `/items/{item_id}` | Atualiza item do orcamento |
| DELETE | `/items/{item_id}` | Remove item do orcamento |

## Uso
```python
from app.modules.budgets import (
    router,
    BudgetService,
    BudgetCreate,
    BudgetUpdate,
    BudgetItemCreate,
    BudgetItemUpdate,
    BudgetResponse,
    BudgetItemResponse,
    BudgetSummary,
    BudgetCopyRequest,
    BudgetComparisonResponse,
)
```

## Estrutura do Orcamento
```
Budget (mes/ano)
├── BudgetItem (Alimentacao: R$ 1.000)
├── BudgetItem (Transporte: R$ 500)
├── BudgetItem (Lazer: R$ 300)
└── ...
```

## Funcionalidades
- **Rollover**: Opcao de transferir saldo nao usado para o proximo mes
- **Alertas**: Notificacao quando atingir percentual do limite
- **Copia**: Facilita criacao de orcamentos recorrentes
