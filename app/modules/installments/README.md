# Modulo Installments

## Descricao
Modulo responsavel pelo gerenciamento de series de parcelas. Permite controlar compras parceladas, marcar parcelas como pagas, criar projecoes futuras e analisar itens extraidos de documentos.

## Responsabilidades
- CRUD de series de parcelas
- Controle de parcelas pagas e pendentes
- Marcacao retroativa de parcelas
- Criacao de parcelas futuras (projecoes)
- Analise de itens extraidos de documentos
- Calculo de valor restante

## Estrutura
```
installments/
├── __init__.py
├── schemas/
│   └── installment.py    # InstallmentSeriesCreate, InstallmentSeriesResponse, etc.
├── services/
│   └── installment_service.py # InstallmentService (CRUD, analise)
└── routers/
    └── installments.py   # Endpoints de parcelas
```

## Dependencias
- **Models**: `InstallmentSeries`, `InstallmentSeriesStatus`, `Transaction`
- **Outros Modulos**: `transactions` (para criar transacoes)
- **Core**: `deps` (CurrentUser, DbSession)

## Status da Serie
- `active`: Serie ativa (parcelas pendentes)
- `completed`: Todas as parcelas pagas
- `cancelled`: Serie cancelada

## Endpoints

### Router Installments (`/installments`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `` | Lista series de parcelas |
| POST | `` | Cria nova serie de parcelas |
| GET | `/{series_id}` | Detalhes da serie com status de cada parcela |
| POST | `/{series_id}/mark-paid` | Marca parcelas como pagas (retroativo) |
| POST | `/{series_id}/create-future` | Cria transacoes para parcelas futuras |
| DELETE | `/{series_id}` | Cancela serie (mantem transacoes) |
| POST | `/analyze` | Analisa item extraido de documento |

## Uso
```python
from app.modules.installments import (
    router,
    InstallmentService,
    InstallmentSeriesCreate,
    InstallmentSeriesResponse,
    InstallmentSeriesDetailResponse,
    ConfirmInstallmentRequest,
    MarkInstallmentsPaidRequest,
    CreateFutureInstallmentsRequest,
)
```

## Analise de Documento
O endpoint `/analyze` verifica se um item extraido e parcela de serie existente e retorna sugestoes:
- `create_single`: Criar transacao unica (nao e parcela)
- `create_series`: Criar nova serie de parcelas
- `add_to_series`: Adicionar a serie existente
- `mark_previous_paid`: Serie existe, parcelas anteriores pendentes
- `skip`: Parcela ja existe na serie

## Estrutura da Serie
```
InstallmentSeries
├── description: "TV Samsung 55"
├── merchant_name: "Magazine Luiza"
├── total_amount: 3000.00
├── installment_amount: 300.00
├── installment_count: 10
├── paid_count: 3
├── remaining_count: 7
└── remaining_amount: 2100.00
```
