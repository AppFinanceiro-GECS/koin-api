# Modulo MCP

## Descricao
Modulo responsavel pela integracao com LLMs externos via Model Context Protocol (MCP). Fornece uma API otimizada para consultas de dados financeiros, permitindo integracao com Claude Code, ChatGPT Custom GPTs e outras ferramentas de IA.

## Responsabilidades
- Expor endpoints para consulta de dados financeiros
- Autenticacao via API Key (header `Authorization: Bearer <API_KEY>`)
- Fornecer schema OpenAPI para integracao com ChatGPT Custom GPTs
- Contexto financeiro agregado para analise por IA
- Consultas flexiveis em tabelas especificas
- Resumos e estatisticas financeiras

## Estrutura
```
mcp/
├── __init__.py
├── schemas/
│   ├── __init__.py
│   └── query.py        # ColumnInfo, TableInfo, TableListResponse, QueryRequest,
│                       # QueryResponse, TableStatsResponse, ContextRequest
├── services/
│   ├── __init__.py
│   └── mcp_service.py  # MCPService (consultas, contexto, resumos)
└── routers/
    ├── __init__.py
    └── mcp.py          # Endpoints MCP + OpenAPI Schema
```

## Dependencias
- **Models**: Todas as models principais (Account, Transaction, Category, etc.)
- **Outros Modulos**: Nenhum
- **Core**: `deps` (ApiKeyUser, get_db)

## Autenticacao
Todos os endpoints requerem autenticacao via API Key:
```
Authorization: Bearer biv_xxx...
```

API Keys sao gerenciadas no modulo `api_keys`.

## Endpoints

### Router MCP (`/mcp`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/openapi.json` | Schema OpenAPI para ChatGPT (sem auth) |
| GET | `/tables` | Lista tabelas disponiveis |
| POST | `/query` | Consulta dados de uma tabela |
| GET | `/tables/{table_name}/stats` | Estatisticas de uma tabela |
| GET | `/summary` | Resumo financeiro geral |
| GET | `/me` | Info do usuario autenticado |
| POST | `/context` | **Contexto agregado (RECOMENDADO)** |

## Uso
```python
from app.modules.mcp import router
```

## Tabelas Disponiveis
| Tabela | Descricao |
|--------|-----------|
| `accounts` | Contas financeiras |
| `transactions` | Transacoes |
| `categories` | Categorias |
| `credit_cards` | Cartoes de credito |
| `credit_card_invoices` | Faturas |
| `installment_series` | Series de parcelas |
| `budgets` | Orcamentos |
| `budget_items` | Itens do orcamento |
| `goals` | Metas financeiras |
| `goal_contributions` | Contribuicoes para metas |
| `debts` | Dividas |
| `debt_payments` | Pagamentos de dividas |
| `recurring_transactions` | Transacoes recorrentes |
| `income_sources` | Fontes de renda |
| `documents` | Documentos enviados |
| `merchants` | Estabelecimentos |

## Endpoint Principal: `/context`

O endpoint `/context` e **recomendado para analise por IA**. Retorna dados pre-agregados ideais para responder perguntas como:
- "Quanto gastei com carne em janeiro?"
- "Como estao minhas financas?"
- "Quais meus maiores gastos?"

### Request
```json
{
  "month": "janeiro",      // ou 1-12
  "year": 2026,            // opcional
  "search": "carne"        // busca em descricoes
}
```

### Response
```json
{
  "periodo": {"inicio": "01/01/2026", "fim": "31/01/2026"},
  "resumo": {
    "receitas": 5000.00,
    "despesas": 3500.00,
    "saldo": 1500.00,
    "total_transacoes": 45
  },
  "resultado_busca": {
    "termo": "carne",
    "total": 450.00,
    "quantidade": 5,
    "transacoes": [...]
  },
  "gastos_por_categoria": {...},
  "gastos_por_estabelecimento": {...},
  "maiores_gastos": [...],
  "contas": [...],
  "cartoes_credito": [...],
  "dividas": [...],
  "metas": [...],
  "comparacao_periodo_anterior": {...}
}
```

## Endpoint de Query: `/query`

Para consultas especificas quando precisa de dados brutos.

### Request
```json
{
  "table": "transactions",
  "search": "mercado",
  "date_from": "2026-01-01",
  "date_to": "2026-01-31",
  "filters": {"type": "expense"},
  "order_by": "amount",
  "order_desc": true,
  "limit": 50
}
```

### Response
```json
{
  "data": [...],
  "total": 120,
  "limit": 50,
  "offset": 0
}
```

## Integracao com ChatGPT Custom GPTs

O endpoint `/mcp/openapi.json` fornece o schema OpenAPI completo para integracao com ChatGPT Custom GPTs. Configure a URL `https://biveto.com/api/v1/mcp/openapi.json` nas Actions do GPT.

## Seguranca
- Todos os dados sao automaticamente filtrados pelo `user_id` do usuario autenticado
- Apenas consultas SELECT sao permitidas
- Limite maximo de 200 resultados por query
- API Keys podem ser revogadas a qualquer momento
