# Modulo Transactions

## Descricao
Modulo responsavel pelo gerenciamento de transacoes financeiras. Suporta criacao manual, confirmacao de transacoes extraidas de documentos, parcelas e integracao com series de parcelamento.

## Responsabilidades
- CRUD de transacoes financeiras
- Confirmacao de transacoes extraidas de documentos (1 toque)
- Suporte a parcelas e series de parcelamento
- Busca e filtragem por data, categoria, conta
- Exportacao de transacoes em CSV
- Verificacao de projecoes existentes

## Estrutura
```
transactions/
├── __init__.py
├── schemas/
│   └── transaction.py    # TransactionCreate, TransactionUpdate, TransactionConfirm, TransactionResponse, BatchConfirmRequest, BatchConfirmResponse
├── services/
│   └── transaction_service.py # TransactionService (CRUD, confirmacao, busca)
└── routers/
    └── transactions.py   # Endpoints de transacoes
```

## Dependencias
- **Models**: `Transaction`, `TransactionType`, `Account`, `Category`, `Merchant`
- **Outros Modulos**: `installments` (para parcelas), `documents` (para confirmacao)
- **Core**: `deps` (CurrentUser, DbSession)

## Tipos de Transacao
- `income`: Receita
- `expense`: Despesa
- `transfer`: Transferencia entre contas

### Transferencias entre Contas

O sistema suporta transferencias entre contas atraves do tipo `transfer`. Cada transferencia cria **duas transacoes vinculadas**:

1. **Transacao de saida** (conta origem): Deduz o valor do saldo
2. **Transacao de entrada** (conta destino): Adiciona o valor ao saldo

**Tipos de conta permitidos para transferencia:**
- `wallet` (Carteira)
- `bank` (Banco)
- `investment` (Investimento)

**Nota:** Cartoes de credito (`credit_card`) nao sao permitidos em transferencias, pois o fluxo de pagamento de fatura e diferente.

Ambas as transacoes sao vinculadas pelo campo `linked_transaction_id`, permitindo:
- Exclusao em cascata (deletar uma remove ambas)
- Atualizacao sincronizada (editar valor/data/descricao atualiza ambas)
- Identificacao de direcao (`is_transfer_out` / `is_transfer_in`)

#### Criando uma Transferencia
```json
POST /transactions
{
  "type": "transfer",
  "amount": 500.00,
  "date": "2025-01-15",
  "account_id": 1,
  "destination_account_id": 2,
  "description": "Transferencia para poupanca"
}
```

#### Resposta
A resposta inclui campos adicionais para transferencias:
```json
{
  "id": 123,
  "type": "transfer",
  "amount": 500.00,
  "linked_transaction_id": 124,
  "is_transfer_out": true,
  "is_transfer_in": false,
  "linked_account_name": "Poupanca"
}
```

## Endpoints

### Router Transactions (`/transactions`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `` | Lista transacoes com filtros e paginacao |
| POST | `` | Cria transacao manual |
| POST | `/confirm` | Confirma transacao de documento (1 toque) |
| POST | `/batch-confirm` | Confirma multiplas transacoes de uma vez |
| GET | `/export/csv` | Exporta transacoes em CSV |
| GET | `/{transaction_id}` | Retorna transacao especifica |
| PATCH | `/{transaction_id}` | Atualiza transacao |
| DELETE | `/{transaction_id}` | Remove transacao |
| POST | `/check-projected` | Verifica projecoes existentes |

## Uso
```python
from app.modules.transactions import (
    transactions_router,
    TransactionService,
    TransactionCreate,
    TransactionUpdate,
    TransactionConfirm,
    TransactionResponse,
)
```

## Filtros Disponiveis
- `start_date`: Data inicial
- `end_date`: Data final
- `category_id`: Filtro por categoria
- `account_id`: Filtro por conta
- `search`: Busca textual (min 2, max 100 caracteres)
- `limit`: Limite de resultados (padrao 20, max 100)
- `offset`: Offset para paginacao

## Confirmacao de Documento
O endpoint `/confirm` permite confirmar transacoes extraidas de documentos com suporte a:
- Criacao de nova serie de parcelas
- Vinculacao a serie existente
- Marcacao de parcelas anteriores como pagas
- Criacao de parcelas futuras

## Confirmacao em Lote (Batch Confirm)

O endpoint `POST /batch-confirm` permite confirmar multiplas transacoes de uma vez, melhorando a performance ao processar faturas com muitos itens.

### Request Body
```json
{
  "items": [
    {
      "document_id": 123,
      "account_id": 1,
      "amount": 99.90,
      "date": "2025-01-15",
      "category_id": 5,
      "merchant_name": "Netflix",
      "description": "Assinatura Netflix",
      "payment_method": "credit_card",
      "credit_card_id": 1,
      "invoice_month": 1,
      "invoice_year": 2025
    },
    {
      "document_id": 123,
      "account_id": 1,
      "amount": 150.00,
      "date": "2025-01-10",
      "merchant_name": "Supermercado",
      "is_installment": true,
      "installment_current": 2,
      "installment_total": 3
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
      "transaction_id": 456
    },
    {
      "index": 1,
      "success": true,
      "transaction_id": 457
    }
  ]
}
```

### Schemas

| Schema | Descricao |
|--------|-----------|
| `BatchConfirmRequest` | Request com lista de items (max 100) |
| `BatchConfirmItem` | Item individual com mesmos campos do TransactionConfirm |
| `BatchConfirmItemResult` | Resultado individual de cada item |
| `BatchConfirmResponse` | Response com total, success_count, duplicate_count, error_count |

### Campos do BatchConfirmItem

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| document_id | int | Nao | ID do documento de origem |
| account_id | int | Sim | ID da conta |
| amount | float | Sim | Valor da transacao |
| date | date | Sim | Data da transacao |
| category_id | int | Nao | ID da categoria |
| merchant_name | string | Nao | Nome do estabelecimento |
| description | string | Nao | Descricao |
| payment_method | string | Nao | Metodo de pagamento |
| credit_card_id | int | Nao | ID do cartao de credito |
| invoice_month | int | Nao | Mes da fatura (1-12) |
| invoice_year | int | Nao | Ano da fatura |
| is_installment | bool | Nao | Se e parcelado |
| installment_current | int | Nao | Parcela atual |
| installment_total | int | Nao | Total de parcelas |
| force_duplicate | bool | Nao | Forcar criacao mesmo se duplicado |

### Deteccao de Duplicados

O endpoint verifica automaticamente se ja existe uma transacao com:
- Mesmo valor
- Mesma descricao ou merchant
- Mesma data (ou proxima)

Se duplicado for detectado e `force_duplicate: false`, o item e marcado como `is_duplicate: true`.

### Fluxo de Uso
1. Usuario faz upload de fatura
2. Sistema extrai itens
3. Usuario seleciona itens para adicionar
4. Frontend chama `POST /batch-confirm` com todos os itens selecionados
5. Backend processa todos de uma vez e retorna resultado individual
6. Frontend mostra resumo: X adicionadas, Y duplicadas, Z erros
