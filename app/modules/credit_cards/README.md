# Modulo Credit Cards

## Descricao
Modulo responsavel pelo gerenciamento de cartoes de credito e suas faturas. Inclui controle de limite, fechamento, vencimento, programas de pontos e integracao com documentos para importacao automatica de faturas.

## Responsabilidades
- CRUD de cartoes de credito
- Gerenciamento de faturas (invoices)
- Calculo de limite usado e disponivel
- Projecao de transacoes recorrentes para faturas futuras
- Deteccao automatica de cartao a partir de documentos
- Pagamento de faturas com registro de transacao
- Criacao de cartao a partir de dados extraidos de fatura

## Estrutura
```
credit_cards/
├── __init__.py
├── schemas/
│   ├── credit_card.py    # CreditCardCreate, CreditCardResponse, CreditCardListResponse
│   └── invoice.py        # InvoiceCreate, InvoiceResponse, InvoicePayment, etc.
├── services/
│   └── invoice_service.py # InvoiceService (faturas, projecoes, pagamentos)
└── routers/
    ├── credit_cards.py   # Endpoints de cartoes
    └── invoices.py       # Endpoints de faturas
```

## Dependencias
- **Models**: `CreditCard`, `CreditCardInvoice`, `InvoiceStatus`, `Account`, `AccountType`, `Transaction`, `Document`, `HouseholdMember`
- **Outros Modulos**: `documents` (para extracao de faturas)
- **Core**: `deps` (CurrentUser, DbSession)

## Endpoints

### Router Credit Cards (`/credit-cards`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `` | Lista todos os cartoes de credito |
| POST | `` | Cria novo cartao (com conta associada) |
| GET | `/{card_id}` | Retorna cartao especifico |
| PATCH | `/{card_id}` | Atualiza cartao |
| DELETE | `/{card_id}` | Remove cartao e conta associada |
| POST | `/{card_id}/project-recurring` | Projeta recorrentes para faturas futuras |

### Router Invoices (`/invoices`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `` | Lista faturas do usuario |
| POST | `` | Cria fatura manualmente |
| POST | `/from-document` | Cria fatura a partir de documento |
| GET | `/{invoice_id}` | Detalhes da fatura com transacoes |
| PATCH | `/{invoice_id}` | Atualiza fatura |
| DELETE | `/{invoice_id}` | Exclui fatura |
| POST | `/{invoice_id}/pay` | Registra pagamento de fatura |
| GET | `/credit-card/{card_id}` | Lista faturas de um cartao |
| GET | `/credit-card/{card_id}/current` | Resumo da fatura atual |
| POST | `/detect-card` | Detecta cartao por dados do documento |
| POST | `/create-card-from-invoice` | Cria cartao a partir de fatura |
| POST | `/project-future` | Projeta transacoes futuras |

## Uso
```python
from app.modules.credit_cards import (
    credit_cards_router,
    invoices_router,
    InvoiceService,
    CreditCardCreate,
    CreditCardResponse,
    InvoiceCreate,
    InvoiceResponse,
    InvoicePayment,
)
```

## Status de Fatura
- `open`: Fatura aberta (periodo atual)
- `closed`: Fatura fechada (aguardando pagamento)
- `paid`: Fatura paga
- `partial`: Fatura parcialmente paga
- `overdue`: Fatura vencida

## Deteccao Automatica de Cartao

O sistema detecta automaticamente qual cartao corresponde a uma fatura enviada usando multiplos criterios com sistema de pontuacao.

### Criterios de Matching

| Criterio | Pontos | Descricao |
|----------|--------|-----------|
| Ultimos 4 digitos | +100 | Match exato dos digitos do cartao |
| Nome do cartao | +50 | Fuzzy match entre nome extraido e nome cadastrado |
| Parceiro co-branded | +40 | Ex: "amazon" encontrado no nome do cartao |
| Emissor (issuer) | +30 | Ex: "bradescard" → variantes "bradesco", "amazon" |
| Banco | +25 | Fuzzy match com nome do banco |
| Bandeira | +10 | Ex: "visa", "mastercard" |

### Mapa de Variantes de Emissores

Para melhorar o matching, o sistema mapeia emissores para variantes conhecidas:

```python
{
    "bradescard": ["bradescard", "bradesco", "bradesco amazon", "amazon bradesco"],
    "itau": ["itau", "itaucard"],
    "nubank": ["nubank", "nu"],
    "santander": ["santander"],
    "amazon": ["amazon", "bradesco", "bradescard"],
    # ... outros
}
```

### Distinguindo Cartoes do Mesmo Banco

Com os campos de identificacao extraidos (issuer, bank, brand, partner, last_digits), o sistema consegue distinguir cartoes do mesmo banco pelo parceiro co-branded e/ou pela bandeira.
