# Modulo Accounts

## Descricao
Modulo responsavel pelo gerenciamento de contas bancarias e carteiras do usuario. Suporta contas pessoais e familiares (household) com calculo automatico de saldos baseado nas transacoes.

## Responsabilidades
- CRUD completo de contas bancarias e carteiras
- Calculo de saldos baseado em transacoes
- Suporte a contas pessoais e familiares (household)
- Gerenciamento de tipos de conta (carteira, banco, cartao, investimento)

## Estrutura
```
accounts/
├── __init__.py
├── schemas/
│   └── account.py        # AccountBase, AccountCreate, AccountUpdate, AccountResponse
├── services/             # (logica no router)
└── routers/
    └── accounts.py       # Endpoints de contas
```

## Dependencias
- **Models**: `Account`, `Transaction`, `TransactionType`, `HouseholdMember`
- **Outros Modulos**: `household` (para contas compartilhadas)
- **Core**: `deps` (CurrentUser, DbSession)

## Tipos de Conta
- `wallet`: Carteira / Dinheiro em especie (permite transferencias)
- `bank`: Conta bancaria (permite transferencias)
- `credit_card`: Cartao de credito (NAO permite transferencias)
- `investment`: Investimentos (permite transferencias)

## Endpoints

### Router Accounts (`/accounts`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `` | Lista todas as contas do usuario (pessoais + household) |
| POST | `` | Cria uma nova conta |
| GET | `/{account_id}` | Retorna uma conta especifica com saldo atualizado |
| PATCH | `/{account_id}` | Atualiza uma conta |
| DELETE | `/{account_id}` | Remove uma conta |

## Uso
```python
from app.modules.accounts import (
    router,
    AccountBase,
    AccountCreate,
    AccountUpdate,
    AccountResponse,
)
```

## Calculo de Saldo
O saldo de cada conta e calculado dinamicamente:
```
saldo_atual = saldo_inicial + receitas - despesas + transferencias_entrada - transferencias_saida
```
Onde:
- `saldo_inicial`: Valor definido na criacao da conta
- `receitas`: Soma de transacoes do tipo INCOME
- `despesas`: Soma de transacoes do tipo EXPENSE
- `transferencias_entrada`: Soma de transferencias recebidas (TRANSFER onde `id > linked_transaction_id`)
- `transferencias_saida`: Soma de transferencias enviadas (TRANSFER onde `id < linked_transaction_id`)

### Transferencias entre Contas
O calculo de saldo considera transferencias usando a logica de ID vinculado:
- **Saida**: Transacao TRANSFER onde `id < linked_transaction_id` (deduz do saldo)
- **Entrada**: Transacao TRANSFER onde `id > linked_transaction_id` (soma ao saldo)

Isso garante que:
- A conta de origem tem o valor deduzido
- A conta de destino tem o valor adicionado
- O saldo total do sistema permanece consistente
