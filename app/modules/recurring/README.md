# Modulo Recurring

## Descricao
Modulo responsavel pelo gerenciamento de transacoes recorrentes como assinaturas, contas fixas e pagamentos periodicos. Permite pausar, retomar e gerar transacoes automaticamente.

## Responsabilidades
- CRUD de transacoes recorrentes
- Gerenciamento de frequencias (diaria, semanal, mensal, anual)
- Pausa e retomada de recorrencias
- Geracao automatica de transacoes pendentes
- Resumo de compromissos recorrentes

## Estrutura
```
recurring/
├── __init__.py
├── schemas/
│   └── recurring.py      # RecurringCreate, RecurringResponse, RecurringSummary, BatchRecurringFromSuggestionRequest, etc.
├── services/
│   └── recurring_service.py # RecurringTransactionService (CRUD, geracao)
└── routers/
    └── recurring.py      # Endpoints de recorrentes
```

## Dependencias
- **Models**: `RecurringTransaction`, `Account`, `Category`
- **Outros Modulos**: `known_services` (para criar recorrencia a partir de sugestao)
- **Core**: `deps` (CurrentUser, DbSession)

## Frequencias Suportadas
- `daily`: Diaria
- `weekly`: Semanal
- `biweekly`: Quinzenal
- `monthly`: Mensal
- `bimonthly`: Bimestral
- `quarterly`: Trimestral
- `semiannual`: Semestral
- `annual`: Anual

## Status
- `active`: Ativa
- `paused`: Pausada
- `cancelled`: Cancelada

## Endpoints

### Router Recurring (`/recurring`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `` | Lista transacoes recorrentes |
| POST | `` | Cria nova transacao recorrente |
| GET | `/summary` | Resumo das recorrencias |
| GET | `/{recurring_id}` | Retorna recorrente por ID |
| PATCH | `/{recurring_id}` | Atualiza recorrente |
| DELETE | `/{recurring_id}` | Remove recorrente |
| POST | `/{recurring_id}/pause` | Pausa recorrente |
| POST | `/{recurring_id}/resume` | Retoma recorrente |
| POST | `/generate` | Gera transacoes pendentes |
| POST | `/from-suggestion` | Cria recorrencia a partir de sugestao detectada |
| POST | `/batch-from-suggestion` | Cria multiplas recorrencias de uma vez |

## Uso
```python
from app.modules.recurring import (
    router,
    RecurringTransactionService,
    RecurringCreate,
    RecurringUpdate,
    RecurringResponse,
    RecurringSummary,
    RecurrenceFrequency,
    RecurringStatus,
    TransactionType,
)
```

## Geracao de Transacoes
O endpoint `/generate` verifica todas as recorrencias ativas e cria transacoes para aquelas que estao vencidas, atualizando a `next_due_date` automaticamente.

## Criar Recorrencia a partir de Sugestao

O endpoint `POST /from-suggestion` permite criar uma recorrencia a partir de uma sugestao detectada pelo modulo `known_services` durante a extracao de faturas.

### Request Body
```json
{
  "name": "Netflix",
  "amount": 55.90,
  "account_id": 1,
  "frequency": "monthly",
  "day_of_month": 15,
  "category_name": "streaming",
  "payment_method": "credit_card"
}
```

### Campos

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| name | string | Sim | Nome da recorrencia |
| amount | float | Sim | Valor |
| account_id | int | Sim | ID da conta |
| frequency | string | Nao | Frequencia (default: monthly) |
| day_of_month | int | Nao | Dia do mes para cobranca |
| category_id | int | Nao | ID da categoria |
| category_name | string | Nao | Nome da categoria (alternativa ao ID) |
| payment_method | string | Nao | Metodo de pagamento (default: credit_card) |
| start_date | date | Nao | Data inicio (default: hoje) |

### Fluxo de Uso
1. Usuario faz upload de fatura de cartao
2. Sistema extrai itens e detecta servicos recorrentes
3. Frontend mostra sugestao de cadastrar recorrencia
4. Usuario confirma e chama `POST /from-suggestion`
5. Recorrencia e criada automaticamente

## Criar Multiplas Recorrencias (Batch)

O endpoint `POST /batch-from-suggestion` permite criar varias recorrencias de uma vez a partir de sugestoes detectadas.

### Request Body
```json
{
  "items": [
    {
      "name": "Netflix",
      "amount": 55.90,
      "account_id": 1,
      "frequency": "monthly",
      "day_of_month": 15,
      "category_name": "streaming",
      "payment_method": "credit_card"
    },
    {
      "name": "Spotify",
      "amount": 21.90,
      "account_id": 1,
      "frequency": "monthly",
      "day_of_month": 10,
      "category_name": "streaming",
      "payment_method": "credit_card"
    }
  ]
}
```

### Response
```json
{
  "total": 2,
  "success_count": 2,
  "duplicate_count": 0,
  "error_count": 0,
  "results": [
    {
      "index": 0,
      "success": true,
      "recurring_id": 123,
      "recurring_name": "Netflix"
    },
    {
      "index": 1,
      "success": true,
      "recurring_id": 124,
      "recurring_name": "Spotify"
    }
  ]
}
```

### Schemas

| Schema | Descricao |
|--------|-----------|
| `BatchRecurringFromSuggestionRequest` | Request com lista de items |
| `BatchRecurringItemResult` | Resultado individual de cada item |
| `BatchRecurringResponse` | Response com total, success_count, duplicate_count, error_count |

### Deteccao de Duplicados

O endpoint verifica automaticamente se ja existe uma recorrencia com:
- Mesmo nome (case insensitive)
- Mesmo valor
- Status diferente de "cancelled"

Se duplicado for detectado, o item e marcado como `is_duplicate: true` e nao e criado.

### Fluxo de Uso (Batch)
1. Usuario faz upload de fatura de cartao
2. Sistema extrai itens e detecta multiplos servicos recorrentes
3. Frontend mostra botao "Criar Todas as Recorrencias (N)"
4. Usuario clica no botao
5. Frontend chama `POST /batch-from-suggestion` com todos os itens
6. Backend processa todos de uma vez e retorna resultado individual
