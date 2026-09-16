# Modulo Goals

## Descricao
Modulo responsavel pelo gerenciamento de metas financeiras. Suporta diversos tipos de metas incluindo reserva de emergencia, PNIF (Patrimonio Necessario para Independencia Financeira) e metas personalizadas.

## Responsabilidades
- CRUD de metas financeiras
- Registro de contribuicoes
- Calculo de projecoes
- Calculo de fundo de emergencia (metodologia Dave Ramsey)
- Calculo de PNIF (metodologia Gustavo Cerbasi)
- Acompanhamento de milestones

## Estrutura
```
goals/
├── __init__.py
├── schemas/
│   └── goal.py           # GoalCreate, GoalResponse, GoalContributionResponse, etc.
├── services/
│   └── goal_service.py   # GoalService (CRUD, calculos, projecoes)
└── routers/
    └── goals.py          # Endpoints de metas
```

## Dependencias
- **Models**: `Goal`, `GoalContribution`, `GoalStatus`
- **Outros Modulos**: Nenhum
- **Core**: `deps` (CurrentUser, DbSession)

## Tipos de Meta
- `savings`: Economia para algo especifico
- `emergency`: Fundo de emergencia (Baby Step 3)
- `debt_free`: Quitar dividas
- `investment`: Meta de investimento
- `retirement`: Aposentadoria / PNIF
- `purchase`: Compra especifica
- `custom`: Meta personalizada

## Endpoints

### Router Goals (`/goals`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `` | Lista metas do usuario |
| POST | `` | Cria nova meta financeira |
| GET | `/summary` | Resumo de todas as metas para dashboard |
| GET | `/emergency-fund` | Calcula fundo de emergencia recomendado |
| GET | `/pnif` | Calcula PNIF - Independencia Financeira |
| GET | `/{goal_id}` | Detalhes da meta com contribuicoes e projecao |
| PATCH | `/{goal_id}` | Atualiza meta |
| DELETE | `/{goal_id}` | Remove meta |
| POST | `/{goal_id}/contributions` | Adiciona contribuicao a meta |

## Uso
```python
from app.modules.goals import (
    router,
    GoalService,
    GoalCreate,
    GoalUpdate,
    GoalContributionCreate,
    GoalResponse,
    GoalDetailResponse,
    GoalContributionResponse,
    GoalSummary,
    EmergencyFundCalculation,
    PNIFCalculation,
)
```

## Metodologias

### Fundo de Emergencia (Dave Ramsey - Baby Step 3)
- Recomenda 3-6 meses de despesas
- Calcula quanto ja esta guardado
- Mostra quantos meses de cobertura

### PNIF (Gustavo Cerbasi)
```
PNIF = Gasto Anual / Rentabilidade
```
Exemplo: R$ 60.000/ano / 8% = R$ 750.000
