from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.deps import ApiKeyUser, get_db
from ..schemas import (
    ContextRequest,
    QueryRequest,
    QueryResponse,
    TableListResponse,
    TableStatsResponse,
)
from ..services import MCPService

router = APIRouter(prefix="/mcp", tags=["MCP - Claude Code"])


# OpenAPI Schema para integração com ChatGPT Custom GPTs
OPENAPI_SCHEMA = {
    "openapi": "3.1.0",
    "info": {
        "title": "Biveto MCP API",
        "description": """API para consulta de dados financeiros do Biveto.

IMPORTANTE: Para perguntas de análise financeira (ex: "quanto gastei com X", "como estão minhas finanças"),
use SEMPRE o endpoint /context primeiro! Ele retorna dados pré-agregados ideais para análise por IA.

O endpoint /query é para consultas específicas de registros quando você precisa de dados brutos.""",
        "version": "1.1.0",
    },
    "servers": [{"url": "https://biveto.com/api/v1"}],
    "paths": {
        "/mcp/context": {
            "post": {
                "operationId": "getFinancialContext",
                "summary": "Contexto financeiro agregado para análise (RECOMENDADO)",
                "description": "Retorna dados financeiros agregados do período. Use search para destacar termos específicos. Dados completos sempre disponíveis para análise.",
                "security": [{"ApiKeyAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ContextRequest"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Contexto financeiro agregado",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ContextResponse"}
                            }
                        },
                    }
                },
            }
        },
        "/mcp/tables": {
            "get": {
                "operationId": "listTables",
                "summary": "Lista todas as tabelas disponíveis",
                "description": "Retorna a lista de tabelas que podem ser consultadas, incluindo nome, descrição e colunas de cada uma.",
                "security": [{"ApiKeyAuth": []}],
                "responses": {
                    "200": {
                        "description": "Lista de tabelas",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/TableListResponse"}
                            }
                        },
                    }
                },
            }
        },
        "/mcp/query": {
            "post": {
                "operationId": "queryTable",
                "summary": "Consulta dados de uma tabela",
                "description": "Executa uma consulta em uma tabela específica com filtros opcionais. Os dados são automaticamente filtrados pelo usuário autenticado.",
                "security": [{"ApiKeyAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/QueryRequest"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Dados da consulta",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/QueryResponse"}
                            }
                        },
                    }
                },
            }
        },
        "/mcp/summary": {
            "get": {
                "operationId": "getSummary",
                "summary": "Resumo financeiro do usuário",
                "description": "Retorna um resumo geral incluindo: total de contas e saldo, transações do mês, cartões de crédito ativos, faturas em aberto, metas e dívidas.",
                "security": [{"ApiKeyAuth": []}],
                "responses": {
                    "200": {
                        "description": "Resumo financeiro",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/SummaryResponse"}
                            }
                        },
                    }
                },
            }
        },
        "/mcp/tables/{table_name}/stats": {
            "get": {
                "operationId": "getTableStats",
                "summary": "Estatísticas de uma tabela",
                "description": "Retorna contagem de registros e informações sobre uma tabela específica.",
                "security": [{"ApiKeyAuth": []}],
                "parameters": [
                    {
                        "name": "table_name",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Nome da tabela",
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Estatísticas da tabela",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/TableStatsResponse"}
                            }
                        },
                    }
                },
            }
        },
    },
    "components": {
        "schemas": {
            "TableListResponse": {
                "type": "object",
                "properties": {
                    "tables": {
                        "type": "array",
                        "description": "Lista de tabelas disponíveis",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Nome da tabela"},
                                "description": {
                                    "type": "string",
                                    "description": "Descrição da tabela",
                                },
                                "columns": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "description": {"type": "string"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "total": {"type": "integer", "description": "Total de tabelas"},
                },
            },
            "QueryRequest": {
                "type": "object",
                "required": ["table"],
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "Nome da tabela (ex: transactions, accounts, credit_cards)",
                    },
                    "search": {
                        "type": "string",
                        "description": "RECOMENDADO: Busca por texto em description/name (ex: 'carne', 'mercado', 'uber')",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Data inicial YYYY-MM-DD (ex: '2026-01-01' para início de janeiro)",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Data final YYYY-MM-DD (ex: '2026-01-31' para fim de janeiro)",
                    },
                    "amount_min": {"type": "number", "description": "Valor mínimo"},
                    "amount_max": {"type": "number", "description": "Valor máximo"},
                    "filters": {
                        "type": "object",
                        "description": 'Filtros exatos adicionais. Ex: {"type": "expense"} para despesas',
                        "additionalProperties": True,
                    },
                    "order_by": {
                        "type": "string",
                        "description": "Coluna para ordenação (ex: date, amount)",
                        "default": "date",
                    },
                    "order_desc": {
                        "type": "boolean",
                        "description": "Se true, ordena descendente",
                        "default": True,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Máximo de resultados (1-200)",
                        "default": 50,
                        "maximum": 200,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Offset para paginação",
                        "default": 0,
                    },
                },
            },
            "QueryResponse": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "description": "Registros retornados",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "total": {"type": "integer", "description": "Total de registros encontrados"},
                    "limit": {"type": "integer", "description": "Limite usado na consulta"},
                    "offset": {"type": "integer", "description": "Offset usado na consulta"},
                },
            },
            "SummaryResponse": {
                "type": "object",
                "properties": {
                    "accounts": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer", "description": "Número de contas"},
                            "total_balance": {"type": "number", "description": "Saldo total"},
                        },
                    },
                    "transactions_this_month": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer", "description": "Número de transações"},
                            "total_expenses": {
                                "type": "number",
                                "description": "Total de despesas",
                            },
                            "total_income": {"type": "number", "description": "Total de receitas"},
                        },
                    },
                    "credit_cards": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer", "description": "Número de cartões ativos"}
                        },
                    },
                    "open_invoices": {
                        "type": "object",
                        "properties": {
                            "count": {
                                "type": "integer",
                                "description": "Número de faturas abertas",
                            },
                            "total_amount": {
                                "type": "number",
                                "description": "Valor total das faturas",
                            },
                        },
                    },
                    "active_goals": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer", "description": "Número de metas ativas"},
                            "current_total": {
                                "type": "number",
                                "description": "Valor atual acumulado",
                            },
                            "target_total": {"type": "number", "description": "Valor alvo total"},
                        },
                    },
                    "active_debts": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer", "description": "Número de dívidas ativas"},
                            "total_balance": {
                                "type": "number",
                                "description": "Saldo total das dívidas",
                            },
                        },
                    },
                },
            },
            "TableStatsResponse": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Nome da tabela"},
                    "total_records": {"type": "integer", "description": "Total de registros"},
                    "columns": {
                        "type": "object",
                        "description": "Colunas da tabela com descrições",
                        "additionalProperties": {"type": "string"},
                    },
                },
            },
            "ContextRequest": {
                "type": "object",
                "description": "Parâmetros para contexto financeiro agregado",
                "properties": {
                    "month": {
                        "oneOf": [{"type": "integer"}, {"type": "string"}],
                        "description": "Mês para análise (1-12 ou nome: 'janeiro', 'fevereiro'). Ex: 1 ou 'janeiro'",
                    },
                    "year": {"type": "integer", "description": "Ano para análise (ex: 2026)"},
                    "date_from": {"type": "string", "description": "Data inicial YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "Data final YYYY-MM-DD"},
                    "search": {
                        "type": "string",
                        "description": "Termo para buscar em descrições e estabelecimentos. Resultados aparecem em 'resultado_busca'. Os dados completos SEMPRE são retornados para análise.",
                    },
                },
            },
            "ContextResponse": {
                "type": "object",
                "description": "Contexto financeiro agregado para análise",
                "properties": {
                    "periodo": {
                        "type": "object",
                        "description": "Período analisado",
                        "properties": {"inicio": {"type": "string"}, "fim": {"type": "string"}},
                    },
                    "resumo": {
                        "type": "object",
                        "description": "Resumo financeiro do período",
                        "properties": {
                            "receitas": {"type": "number"},
                            "despesas": {"type": "number"},
                            "saldo": {"type": "number"},
                            "total_transacoes": {"type": "integer"},
                        },
                    },
                    "resultado_busca": {
                        "type": "object",
                        "description": "Transações que correspondem ao termo de busca (quando search é usado). Se total=0, analise gastos_por_categoria para encontrar gastos relacionados.",
                        "properties": {
                            "termo": {"type": "string", "description": "Termo buscado"},
                            "total": {
                                "type": "number",
                                "description": "VALOR TOTAL encontrado com o termo",
                            },
                            "quantidade": {
                                "type": "integer",
                                "description": "Número de transações encontradas",
                            },
                            "transacoes": {
                                "type": "array",
                                "description": "Lista das transações encontradas",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "valor": {"type": "number"},
                                        "data": {"type": "string"},
                                        "estabelecimento": {"type": "string"},
                                        "descricao": {"type": "string"},
                                        "categoria": {"type": "string"},
                                    },
                                },
                            },
                            "dica": {
                                "type": "string",
                                "description": "Dica caso não encontre resultados",
                            },
                        },
                    },
                    "gastos_por_categoria": {
                        "type": "object",
                        "description": "Gastos agrupados por categoria com totais",
                    },
                    "gastos_por_estabelecimento": {
                        "type": "object",
                        "description": "Top 10 estabelecimentos com mais gastos",
                    },
                    "maiores_gastos": {
                        "type": "array",
                        "description": "Top 10 maiores gastos do período",
                        "items": {
                            "type": "object",
                            "properties": {
                                "valor": {"type": "number"},
                                "data": {"type": "string"},
                                "estabelecimento": {"type": "string"},
                                "categoria": {"type": "string"},
                            },
                        },
                    },
                    "contas": {
                        "type": "array",
                        "description": "Lista de contas com saldos",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nome": {"type": "string"},
                                "tipo": {"type": "string"},
                                "saldo": {"type": "number"},
                            },
                        },
                    },
                    "cartoes_credito": {
                        "type": "array",
                        "description": "Cartões de crédito com faturas",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nome": {"type": "string"},
                                "bandeira": {"type": "string"},
                                "limite_total": {"type": "number"},
                                "saldo_em_aberto": {"type": "number"},
                                "limite_disponivel": {"type": "number"},
                            },
                        },
                    },
                    "dividas": {
                        "type": "array",
                        "description": "Dívidas ativas",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nome": {"type": "string"},
                                "saldo": {"type": "number"},
                                "taxa_juros": {"type": "number"},
                                "pagamento_minimo": {"type": "number"},
                            },
                        },
                    },
                    "metas": {
                        "type": "array",
                        "description": "Metas financeiras ativas",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nome": {"type": "string"},
                                "valor_alvo": {"type": "number"},
                                "valor_atual": {"type": "number"},
                                "progresso": {"type": "number"},
                                "falta": {"type": "number"},
                            },
                        },
                    },
                    "comparacao_periodo_anterior": {
                        "type": "object",
                        "description": "Comparação com período anterior",
                    },
                },
            },
        },
        "securitySchemes": {
            "ApiKeyAuth": {
                "type": "http",
                "scheme": "bearer",
                "description": "API Key pessoal gerada em Configurações > API Keys. Use o formato: Bearer biv_xxx",
            }
        },
    },
    "security": [{"ApiKeyAuth": []}],
}


@router.get("/openapi.json", include_in_schema=False)
async def get_openapi_schema():
    """
    Retorna o schema OpenAPI para integração com ChatGPT Custom GPTs.
    Este endpoint não requer autenticação.
    """
    return JSONResponse(content=OPENAPI_SCHEMA)


@router.get("/tables", response_model=TableListResponse)
async def list_tables(
    user: ApiKeyUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Lista todas as tabelas disponíveis para consulta.

    **Autenticação**: Header `X-API-Key` com sua API Key pessoal.

    Retorna nome, descrição e colunas de cada tabela acessível.
    """
    service = MCPService(db)
    tables = service.get_table_list()

    return TableListResponse(
        tables=tables,
        total=len(tables),
    )


@router.post("/query", response_model=QueryResponse)
async def query_table(
    request: QueryRequest,
    user: ApiKeyUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Executa uma consulta em uma tabela específica.

    **Autenticação**: Header `X-API-Key` com sua API Key pessoal.

    Os dados são automaticamente filtrados pelo seu usuário.
    Apenas consultas SELECT são permitidas.

    **Parâmetros**:
    - `table`: Nome da tabela (ex: "transactions", "accounts")
    - `filters`: Filtros no formato {"coluna": valor}
    - `order_by`: Coluna para ordenação
    - `order_desc`: Se true, ordena descendente
    - `limit`: Máximo de resultados (1-1000, padrão 100)
    - `offset`: Offset para paginação

    **Exemplo de filtro**:
    ```json
    {
        "table": "transactions",
        "filters": {"type": "expense", "is_paid": true},
        "order_by": "date",
        "order_desc": true,
        "limit": 50
    }
    ```
    """
    service = MCPService(db)
    data, total = await service.query_table(user, request)

    return QueryResponse(
        data=data,
        total=total,
        limit=request.limit,
        offset=request.offset,
    )


@router.get("/tables/{table_name}/stats", response_model=TableStatsResponse)
async def get_table_stats(
    table_name: str,
    user: ApiKeyUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna estatísticas de uma tabela específica.

    **Autenticação**: Header `X-API-Key` com sua API Key pessoal.

    Inclui contagem de registros e informações das colunas.
    """
    service = MCPService(db)
    stats = await service.get_table_stats(user, table_name)

    return TableStatsResponse(**stats)


@router.get("/summary")
async def get_summary(
    user: ApiKeyUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna um resumo geral dos dados financeiros do usuário.

    **Autenticação**: Header `X-API-Key` com sua API Key pessoal.

    Inclui:
    - Total de contas e saldo
    - Transações do mês atual
    - Cartões de crédito ativos
    - Faturas em aberto
    - Metas ativas
    - Dívidas ativas
    """
    service = MCPService(db)
    return await service.get_summary(user)


@router.get("/me")
async def get_current_user_info(
    user: ApiKeyUser,
):
    """
    Retorna informações do usuário autenticado via API Key.

    **Autenticação**: Header `X-API-Key` com sua API Key pessoal.

    Útil para verificar se a autenticação está funcionando.
    """
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "is_active": user.is_active,
    }


@router.post("/context")
async def get_financial_context(
    request: ContextRequest,
    user: ApiKeyUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna contexto financeiro agregado para análise por IA.

    **ENDPOINT PRINCIPAL!** Use este endpoint para perguntas como:
    - "quanto gastei com carne em janeiro"
    - "como estão minhas finanças"
    - "quais meus maiores gastos"

    **Autenticação**: Header `Authorization: Bearer <API_KEY>`.

    **Parâmetros**:
    - `month`: Mês para análise (1-12 ou nome: 'janeiro', 'fevereiro')
    - `year`: Ano para análise (ex: 2026)
    - `date_from` / `date_to`: Período customizado (alternativa ao mês)
    - `search`: **IMPORTANTE** - Busca por palavra-chave (ex: 'carne', 'mercado', 'uber')

    **Exemplo de uso**:
    ```json
    {
        "month": "janeiro",
        "search": "carne"
    }
    ```

    Retorna dados pré-agregados: gastos por categoria, por estabelecimento,
    maiores gastos, cartões, dívidas, metas e comparação com período anterior.
    """
    service = MCPService(db)
    return await service.get_context(user, request)
