# Modulo Analytics

## Descricao
Modulo responsavel por analises e relatorios financeiros. Fornece resumos mensais, insights sobre gastos e comparativos para ajudar o usuario a entender seus padroes financeiros.

## Responsabilidades
- Resumo analitico mensal (receitas, despesas, saldos)
- Gastos por categoria
- Top merchants (estabelecimentos)
- Comparativo com mes anterior
- Insights explicaveis sobre gastos (vazamentos, drivers, oportunidades)

## Estrutura
```
analytics/
├── __init__.py
├── schemas/
│   └── analytics.py      # AnalyticsSummary, CategorySummary, MerchantSummary, InsightResponse
├── services/
│   └── analytics_service.py # AnalyticsService (resumos, insights)
└── routers/
    └── analytics.py      # Endpoints de analytics
```

## Dependencias
- **Models**: `Transaction`, `Category`, `Merchant`
- **Outros Modulos**: Nenhum
- **Core**: `deps` (CurrentUser, DbSession)

## Endpoints

### Router Analytics (`/analytics`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/summary` | Resumo analitico do mes |
| GET | `/insights` | Insights explicaveis sobre gastos |

## Uso
```python
from app.modules.analytics import (
    router,
    AnalyticsSummary,
    CategorySummary,
    MerchantSummary,
    InsightResponse,
    InsightType,
    AnalyticsService,
)
```

## Tipos de Insight
- **Vazamentos**: Gastos pequenos e frequentes que somam valores significativos
- **Drivers**: Principais categorias responsaveis pelos gastos
- **Oportunidades**: Sugestoes de economia baseadas nos padroes de consumo

## Resumo Mensal
O resumo mensal inclui:
- Total de receitas
- Total de despesas
- Saldo do periodo
- Breakdown por categoria
- Top 5 estabelecimentos
- Comparativo percentual com mes anterior

### Tratamento de Transferencias
Transferencias entre contas (`type: transfer`) sao **excluidas** dos calculos de analytics:
- Nao sao contabilizadas como receita ou despesa
- Nao aparecem nos breakdowns por categoria
- Nao sao listadas nos top merchants

Isso evita que movimentacoes internas entre contas distorcam os relatorios de gastos e receitas reais do usuario.
