# Modulo Debts

## Descricao
Modulo responsavel pela gestao de dividas. Oferece estrategias de quitacao baseadas nas metodologias Snowball (Dave Ramsey) e Avalanche, com projecoes e comparativos.

## Responsabilidades
- CRUD de dividas
- Registro de pagamentos
- Calculo de saldo devedor
- Estrategia Snowball (menor saldo primeiro)
- Estrategia Avalanche (maior taxa primeiro)
- Comparativo entre estrategias
- Projecao de quitacao

## Estrutura
```
debts/
├── __init__.py
├── schemas/
│   └── debt.py           # DebtCreate, DebtResponse, SnowballPlan, AvalanchePlan, etc.
├── services/
│   └── debt_service.py   # DebtService (CRUD, estrategias, projecoes)
└── routers/
    └── debts.py          # Endpoints de dividas
```

## Dependencias
- **Models**: `Debt`, `DebtPayment`, `DebtStatus`
- **Outros Modulos**: Nenhum
- **Core**: `deps` (CurrentUser, DbSession)

## Tipos de Divida
- `credit_card`: Cartao de credito
- `personal_loan`: Emprestimo pessoal
- `car_loan`: Financiamento de carro
- `mortgage`: Financiamento imobiliario
- `student_loan`: Emprestimo estudantil
- `medical`: Divida medica
- `store_credit`: Crediario de loja
- `other`: Outros

## Endpoints

### Router Debts (`/debts`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `` | Lista dividas do usuario |
| POST | `` | Registra nova divida |
| GET | `/summary` | Resumo de todas as dividas |
| GET | `/snowball` | Plano de quitacao Snowball |
| GET | `/avalanche` | Plano de quitacao Avalanche |
| GET | `/compare-strategies` | Compara Snowball vs Avalanche |
| GET | `/{debt_id}` | Detalhes da divida com pagamentos |
| PATCH | `/{debt_id}` | Atualiza divida |
| DELETE | `/{debt_id}` | Remove divida |
| POST | `/{debt_id}/payments` | Registra pagamento |

## Uso
```python
from app.modules.debts import (
    router,
    DebtService,
    DebtCreate,
    DebtUpdate,
    DebtPaymentCreate,
    DebtResponse,
    DebtDetailResponse,
    DebtPaymentResponse,
    DebtSummary,
    SnowballPlan,
    AvalanchePlan,
    PayoffStrategyComparison,
)
```

## Estrategias de Quitacao

### Snowball (Dave Ramsey)
- Ordena dividas do menor para o maior saldo
- Paga minimo em todas, exceto a menor
- **Vantagem**: Vitorias rapidas que motivam

### Avalanche
- Ordena dividas da maior para a menor taxa de juros
- Matematicamente mais eficiente
- **Vantagem**: Menor custo total de juros
