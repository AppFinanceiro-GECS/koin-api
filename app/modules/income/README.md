# Modulo Income

## Descricao
Modulo responsavel pelo gerenciamento de fontes de receita. Permite cadastrar salarios, beneficios e outras receitas com suporte a dias uteis brasileiros e geracao automatica de transacoes.

## Responsabilidades
- CRUD de fontes de receita
- Suporte a dias uteis (feriados brasileiros)
- Geracao automatica de transacoes de receita
- Preview de transacoes antes da geracao
- Suporte a receitas variaveis e fixas

## Estrutura
```
income/
├── __init__.py
├── schemas/
│   └── income_source.py  # IncomeSourceCreate, IncomeSourceResponse, etc.
├── services/
│   └── income_transaction_service.py # Geracao de transacoes
└── routers/
    └── income_sources.py # Endpoints de fontes de receita
```

## Dependencias
- **Models**: `IncomeSource`, `Account`, `Category`, `HouseholdMember`
- **Outros Modulos**: Nenhum
- **Core**: `deps`, `business_day_service` (dias uteis)

## Tipos de Receita
- `salary`: Salario
- `freelance`: Trabalho autonomo
- `investment`: Rendimentos de investimento
- `rental`: Aluguel
- `benefit`: Beneficio (VA, VR, etc.)
- `bonus`: Bonus/PLR
- `other`: Outros

## Endpoints

### Router Income Sources (`/income-sources`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `` | Lista fontes de receita |
| POST | `` | Cria nova fonte de receita |
| GET | `/{source_id}` | Retorna fonte especifica |
| PATCH | `/{source_id}` | Atualiza fonte |
| DELETE | `/{source_id}` | Remove fonte |
| POST | `/{source_id}/generate-transaction` | Gera transacao para fonte especifica |
| GET | `/utils/business-day` | Calcula N-esimo dia util do mes |
| GET | `/preview-transactions` | Preview das transacoes do mes |
| POST | `/generate-transactions` | Gera transacoes para todas as fontes |

## Uso
```python
from app.modules.income import (
    router,
    IncomeSourceBase,
    IncomeSourceCreate,
    IncomeSourceUpdate,
    IncomeSourceResponse,
    IncomeSourceListResponse,
    IncomeTransactionService,
)
```

## Dias Uteis
O modulo suporta pagamento em dias uteis considerando feriados nacionais brasileiros:
- `use_business_day`: Se True, usa dias uteis
- `business_day_number`: Qual dia util (ex: 5 para 5o dia util)

Exemplo: 5o dia util de Janeiro/2024 = 08/01/2024 (considerando feriados)
