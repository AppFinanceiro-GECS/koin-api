#!/usr/bin/env python3
"""
MCP Server para consultas ao Biveto App via API REST.
Usa API Key para autenticação (header X-API-Key).

Permite apenas consultas de leitura para análise de dados.
"""

import os
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# Configuração
API_BASE_URL = os.environ.get("BIVETO_API_URL", "http://localhost:8000/api/v1")
API_KEY = os.environ.get("BIVETO_API_KEY", "")

# Documentação das tabelas (cópia local para acesso offline)
TABLE_DOCS = {
    "accounts": {
        "description": "Contas financeiras (carteira, banco, cartão, investimento)",
        "columns": {
            "id": "ID único da conta",
            "name": "Nome da conta",
            "type": "Tipo: wallet, bank, credit_card, investment",
            "bank_id": "Identificador do banco",
            "balance": "Saldo atual",
            "currency": "Moeda (BRL)",
            "is_active": "Se está ativa",
            "ownership_type": "personal ou household",
            "created_at": "Data de criação",
        },
    },
    "transactions": {
        "description": "Transações financeiras (despesas, receitas, transferências)",
        "columns": {
            "id": "ID único",
            "account_id": "ID da conta",
            "category_id": "ID da categoria",
            "credit_card_id": "ID do cartão (se crédito)",
            "invoice_id": "ID da fatura",
            "type": "expense, income ou transfer",
            "payment_method": "Método de pagamento",
            "amount": "Valor",
            "date": "Data da transação",
            "description": "Descrição",
            "is_paid": "Se foi paga",
            "installment_number": "Parcela atual",
            "installment_total": "Total de parcelas",
            "is_fixed": "Se é despesa fixa",
            "created_at": "Data de criação",
        },
    },
    "categories": {
        "description": "Categorias para classificar transações",
        "columns": {
            "id": "ID único",
            "name": "Nome",
            "type": "expense ou income",
            "icon": "Ícone",
            "color": "Cor",
            "parent_id": "ID da categoria pai",
            "is_system": "Se é do sistema",
        },
    },
    "credit_cards": {
        "description": "Cartões de crédito",
        "columns": {
            "id": "ID único",
            "account_id": "ID da conta vinculada",
            "credit_limit": "Limite de crédito",
            "closing_day": "Dia de fechamento",
            "due_day": "Dia de vencimento",
            "nickname": "Apelido do cartão",
            "card_brand": "Bandeira",
            "is_active": "Se está ativo",
        },
    },
    "credit_card_invoices": {
        "description": "Faturas de cartão de crédito",
        "columns": {
            "id": "ID único",
            "credit_card_id": "ID do cartão",
            "reference_month": "Mês de referência (1-12)",
            "reference_year": "Ano de referência",
            "closing_date": "Data de fechamento",
            "due_date": "Data de vencimento",
            "total_amount": "Valor total",
            "status": "open, closed, paid, partial, overdue",
            "paid_amount": "Valor pago",
        },
    },
    "installment_series": {
        "description": "Séries de compras parceladas",
        "columns": {
            "id": "ID único",
            "description": "Descrição da compra",
            "merchant_name": "Nome do comerciante",
            "total_amount": "Valor total",
            "installment_amount": "Valor da parcela",
            "installment_count": "Total de parcelas",
            "paid_count": "Parcelas pagas",
            "status": "active, completed, cancelled",
        },
    },
    "budgets": {
        "description": "Orçamentos mensais",
        "columns": {
            "id": "ID único",
            "year": "Ano",
            "month": "Mês (1-12)",
            "total_income_planned": "Receita planejada",
            "total_expense_planned": "Despesa planejada",
        },
    },
    "budget_items": {
        "description": "Itens do orçamento por categoria",
        "columns": {
            "id": "ID único",
            "budget_id": "ID do orçamento",
            "category_id": "ID da categoria",
            "planned_amount": "Valor planejado",
            "is_fixed": "Se é despesa fixa",
        },
    },
    "goals": {
        "description": "Metas financeiras",
        "columns": {
            "id": "ID único",
            "name": "Nome",
            "type": "savings, emergency, debt_free, investment, etc",
            "target_amount": "Valor alvo",
            "current_amount": "Valor atual",
            "status": "active, paused, completed, cancelled",
        },
    },
    "goal_contributions": {
        "description": "Contribuições para metas",
        "columns": {
            "id": "ID único",
            "goal_id": "ID da meta",
            "amount": "Valor",
            "contribution_date": "Data",
        },
    },
    "debts": {
        "description": "Dívidas",
        "columns": {
            "id": "ID único",
            "name": "Nome",
            "type": "Tipo da dívida",
            "creditor": "Credor",
            "original_amount": "Valor original",
            "current_balance": "Saldo atual",
            "interest_rate": "Taxa de juros",
            "status": "active, paid_off, negotiating, defaulted",
        },
    },
    "debt_payments": {
        "description": "Pagamentos de dívidas",
        "columns": {
            "id": "ID único",
            "debt_id": "ID da dívida",
            "amount": "Valor total",
            "principal_amount": "Valor amortizado",
            "interest_amount": "Valor de juros",
            "payment_date": "Data",
        },
    },
    "recurring_transactions": {
        "description": "Transações recorrentes programadas",
        "columns": {
            "id": "ID único",
            "name": "Nome",
            "amount": "Valor",
            "type": "expense ou income",
            "frequency": "daily, weekly, monthly, yearly",
            "status": "active, paused, cancelled",
            "next_due_date": "Próxima data",
        },
    },
    "income_sources": {
        "description": "Fontes de renda",
        "columns": {
            "id": "ID único",
            "name": "Nome",
            "type": "salary, freelance, business, rental, etc",
            "expected_amount": "Valor esperado",
            "frequency": "Frequência",
            "is_active": "Se está ativa",
        },
    },
    "documents": {
        "description": "Documentos/comprovantes",
        "columns": {
            "id": "ID único",
            "original_filename": "Nome original",
            "status": "pending, processing, completed, failed",
            "document_type": "Tipo do documento",
        },
    },
    "merchants": {
        "description": "Comerciantes identificados",
        "columns": {
            "id": "ID único",
            "name": "Nome",
            "cnpj": "CNPJ",
        },
    },
    "receipts": {
        "description": "Cupons fiscais/recibos de compras",
        "columns": {
            "id": "ID único",
            "document_id": "ID do documento (se importado)",
            "store_name": "Nome do estabelecimento",
            "store_cnpj": "CNPJ do estabelecimento",
            "total_amount": "Valor total",
            "subtotal": "Subtotal",
            "discount": "Desconto",
            "purchase_date": "Data da compra",
            "status": "pending, confirmed, cancelled",
            "created_at": "Data de criação",
        },
    },
    "receipt_payments": {
        "description": "Pagamentos de recibos (split payment)",
        "columns": {
            "id": "ID único",
            "receipt_id": "ID do recibo",
            "account_id": "ID da conta",
            "benefit_card_id": "ID do cartão de benefício",
            "payment_method": "Método: voucher_va, debit_card, pix, etc",
            "amount": "Valor pago",
            "sequence": "Sequência do pagamento",
        },
    },
    "benefit_cards": {
        "description": "Cartões de benefício (VA/VR/Flex)",
        "columns": {
            "id": "ID único",
            "account_id": "ID da conta vinculada",
            "card_type": "Tipo: va, vr, flex, vt, cultura, combustivel",
            "provider": "Operadora: alelo, sodexo, vr, ticket, flash, etc",
            "last_four_digits": "Últimos 4 dígitos",
            "expected_monthly_recharge": "Recarga mensal esperada",
            "recharge_day": "Dia da recarga (1-31)",
            "is_active": "Se está ativo",
        },
    },
    "grocery_products": {
        "description": "Catálogo de produtos de mercado",
        "columns": {
            "id": "ID único",
            "name": "Nome do produto",
            "normalized_name": "Nome normalizado",
            "category": "Categoria: fruits_vegetables, meat_fish, dairy, etc",
            "necessity_type": "Tipo: essential, non_essential",
            "default_unit": "Unidade padrão (kg, un, L)",
            "is_system": "Se é produto do sistema",
        },
    },
    "grocery_purchases": {
        "description": "Compras de supermercado (itens)",
        "columns": {
            "id": "ID único",
            "transaction_id": "ID da transação",
            "receipt_id": "ID do recibo",
            "product_id": "ID do produto",
            "merchant_id": "ID do comerciante",
            "product_name": "Nome original do cupom",
            "quantity": "Quantidade",
            "unit": "Unidade",
            "unit_price": "Preço unitário",
            "total_price": "Preço total",
            "category": "Categoria do produto",
            "necessity_type": "Tipo de necessidade",
            "purchase_date": "Data da compra",
        },
    },
    "grocery_price_history": {
        "description": "Histórico de preços de produtos",
        "columns": {
            "id": "ID único",
            "product_id": "ID do produto",
            "merchant_id": "ID do comerciante",
            "price": "Preço",
            "unit": "Unidade",
            "recorded_at": "Data do registro",
        },
    },
    "shopping_lists": {
        "description": "Listas de compras",
        "columns": {
            "id": "ID único",
            "name": "Nome da lista",
            "status": "draft, active, completed, archived",
            "source": "Origem: manual, ai_generated, history",
            "notes": "Observações",
            "created_at": "Data de criação",
            "completed_at": "Data de conclusão",
        },
    },
    "shopping_list_items": {
        "description": "Itens da lista de compras",
        "columns": {
            "id": "ID único",
            "list_id": "ID da lista",
            "product_id": "ID do produto",
            "product_name": "Nome do produto",
            "quantity": "Quantidade",
            "unit": "Unidade",
            "estimated_price": "Preço estimado",
            "category": "Categoria",
            "is_checked": "Se foi marcado",
            "priority": "Prioridade",
        },
    },
    "spending_envelopes": {
        "description": "Envelopes de gastos (YNAB style)",
        "columns": {
            "id": "ID único",
            "category_id": "ID da categoria",
            "name": "Nome",
            "period_type": "Período: daily, weekly, biweekly, monthly",
            "limit_amount": "Valor limite",
            "current_balance": "Saldo atual",
            "period_start_date": "Início do período",
            "period_end_date": "Fim do período",
            "allow_rollover": "Permite acumular",
            "status": "available, depleted, overspent",
            "is_active": "Se está ativo",
        },
    },
    "envelope_history": {
        "description": "Histórico de envelopes",
        "columns": {
            "id": "ID único",
            "envelope_id": "ID do envelope",
            "transaction_id": "ID da transação",
            "change_type": "Tipo: refill, spend, refund, rollover, adjustment, transfer",
            "amount": "Valor",
            "balance_before": "Saldo antes",
            "balance_after": "Saldo depois",
            "period_start": "Início do período",
            "period_end": "Fim do período",
        },
    },
    "chat_conversations": {
        "description": "Conversas do chat com assistente financeiro",
        "columns": {
            "id": "ID único (UUID)",
            "title": "Título da conversa",
            "created_at": "Data de criação",
            "updated_at": "Data de atualização",
        },
    },
    "chat_messages": {
        "description": "Mensagens do chat",
        "columns": {
            "id": "ID único",
            "conversation_id": "ID da conversa",
            "role": "user ou assistant",
            "content": "Conteúdo da mensagem",
            "created_at": "Data de criação",
        },
    },
}

# Server instance
server = Server("biveto-mcp")


def get_headers() -> dict:
    """Retorna headers para requisições à API"""
    if not API_KEY:
        raise ValueError(
            "BIVETO_API_KEY não configurada. Gere uma API Key em Configurações > API Keys no Biveto."
        )
    return {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }


async def api_request(method: str, endpoint: str, **kwargs) -> dict | list | None:
    """Faz requisição à API do Biveto"""
    url = f"{API_BASE_URL}{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, headers=get_headers(), **kwargs)

            if response.status_code == 401:
                return {"error": "API Key inválida ou expirada. Gere uma nova API Key."}
            if response.status_code == 403:
                return {"error": "Sem permissão para acessar este recurso."}
            if response.status_code >= 400:
                return {"error": f"Erro {response.status_code}: {response.text}"}

            return response.json()
    except httpx.ConnectError:
        return {
            "error": f"Não foi possível conectar à API ({API_BASE_URL}). Verifique se o servidor está rodando."
        }
    except Exception as e:
        return {"error": f"Erro na requisição: {str(e)}"}


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Lista as ferramentas disponíveis."""
    return [
        Tool(
            name="list_tables",
            description="Lista todas as tabelas disponíveis para consulta com descrição de cada uma.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="describe_table",
            description="Mostra a estrutura de uma tabela: colunas e suas descrições.",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Nome da tabela a descrever"}
                },
                "required": ["table_name"],
            },
        ),
        Tool(
            name="query",
            description="Consulta dados de uma tabela. Os dados são automaticamente filtrados pelo seu usuário.",
            inputSchema={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "Nome da tabela (ex: transactions, accounts)",
                    },
                    "filters": {
                        "type": "object",
                        "description": 'Filtros no formato {coluna: valor}. Ex: {"type": "expense", "is_paid": true}',
                    },
                    "order_by": {"type": "string", "description": "Coluna para ordenação"},
                    "order_desc": {
                        "type": "boolean",
                        "description": "Se true, ordena descendente",
                        "default": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Limite de resultados (1-1000)",
                        "default": 100,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Offset para paginação",
                        "default": 0,
                    },
                },
                "required": ["table"],
            },
        ),
        Tool(
            name="get_summary",
            description="Retorna um resumo geral dos dados financeiros: contas, transações do mês, cartões, faturas, metas e dívidas.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_table_stats",
            description="Retorna estatísticas de uma tabela: contagem de registros e informações das colunas.",
            inputSchema={
                "type": "object",
                "properties": {"table_name": {"type": "string", "description": "Nome da tabela"}},
                "required": ["table_name"],
            },
        ),
        Tool(
            name="check_connection",
            description="Verifica se a conexão com a API está funcionando e mostra informações do usuário autenticado.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Executa uma ferramenta."""

    if name == "list_tables":
        result = "# Tabelas Disponíveis\n\n"
        for table_name, info in TABLE_DOCS.items():
            result += f"## {table_name}\n{info['description']}\n\n"
        return [TextContent(type="text", text=result)]

    elif name == "describe_table":
        table_name = arguments.get("table_name", "").lower()

        if table_name not in TABLE_DOCS:
            return [
                TextContent(
                    type="text",
                    text=f"Tabela '{table_name}' não encontrada. Use 'list_tables' para ver as tabelas disponíveis.",
                )
            ]

        info = TABLE_DOCS[table_name]
        result = f"# Tabela: {table_name}\n\n"
        result += f"**Descrição:** {info['description']}\n\n"
        result += "## Colunas\n\n"
        result += "| Coluna | Descrição |\n|--------|------------|\n"

        for col, desc in info["columns"].items():
            result += f"| {col} | {desc} |\n"

        return [TextContent(type="text", text=result)]

    elif name == "query":
        table = arguments.get("table", "")
        filters = arguments.get("filters", {})
        order_by = arguments.get("order_by")
        order_desc = arguments.get("order_desc", False)
        limit = min(arguments.get("limit", 100), 1000)
        offset = arguments.get("offset", 0)

        if table not in TABLE_DOCS:
            return [
                TextContent(
                    type="text",
                    text=f"Tabela '{table}' não encontrada. Use 'list_tables' para ver as tabelas disponíveis.",
                )
            ]

        # Faz a requisição
        data = await api_request(
            "POST",
            "/mcp/query",
            json={
                "table": table,
                "filters": filters,
                "order_by": order_by,
                "order_desc": order_desc,
                "limit": limit,
                "offset": offset,
            },
        )

        if isinstance(data, dict) and "error" in data:
            return [TextContent(type="text", text=f"ERRO: {data['error']}")]

        if not data or "data" not in data:
            return [TextContent(type="text", text="Nenhum resultado encontrado.")]

        rows = data["data"]
        total = data.get("total", len(rows))

        if not rows:
            return [TextContent(type="text", text="Nenhum resultado encontrado.")]

        # Formata como tabela markdown
        result = f"**{total} registro(s)** (mostrando {len(rows)})\n\n"

        # Pega as colunas do primeiro registro
        columns = list(rows[0].keys())
        result += "| " + " | ".join(columns) + " |\n"
        result += "| " + " | ".join(["---"] * len(columns)) + " |\n"

        for row in rows:
            values = []
            for col in columns:
                v = row.get(col)
                if v is None:
                    values.append("NULL")
                else:
                    s = str(v)
                    # Trunca valores longos
                    if len(s) > 40:
                        s = s[:40] + "..."
                    values.append(s)
            result += "| " + " | ".join(values) + " |\n"

        return [TextContent(type="text", text=result)]

    elif name == "get_summary":
        data = await api_request("GET", "/mcp/summary")

        if isinstance(data, dict) and "error" in data:
            return [TextContent(type="text", text=f"ERRO: {data['error']}")]

        result = "# Resumo Financeiro\n\n"

        if "accounts" in data:
            acc = data["accounts"]
            result += f"## Contas\n- Total: {acc['count']}\n- Saldo total: R$ {acc['total_balance']:.2f}\n\n"

        if "transactions_this_month" in data:
            t = data["transactions_this_month"]
            result += "## Transações do Mês\n"
            result += f"- Total: {t['count']} transações\n"
            result += f"- Despesas: R$ {t['total_expenses']:.2f}\n"
            result += f"- Receitas: R$ {t['total_income']:.2f}\n"
            result += f"- Saldo: R$ {t['total_income'] - t['total_expenses']:.2f}\n\n"

        if "credit_cards" in data:
            cc = data["credit_cards"]
            result += f"## Cartões de Crédito\n- Ativos: {cc['count']}\n\n"

        if "open_invoices" in data:
            inv = data["open_invoices"]
            result += f"## Faturas em Aberto\n- Quantidade: {inv['count']}\n- Total: R$ {inv['total_amount']:.2f}\n\n"

        if "active_goals" in data:
            g = data["active_goals"]
            progress = (
                (g["current_total"] / g["target_total"] * 100) if g["target_total"] > 0 else 0
            )
            result += f"## Metas Ativas\n- Quantidade: {g['count']}\n"
            result += f"- Progresso: R$ {g['current_total']:.2f} / R$ {g['target_total']:.2f} ({progress:.1f}%)\n\n"

        if "active_debts" in data:
            d = data["active_debts"]
            result += f"## Dívidas Ativas\n- Quantidade: {d['count']}\n- Saldo total: R$ {d['total_balance']:.2f}\n\n"

        return [TextContent(type="text", text=result)]

    elif name == "get_table_stats":
        table_name = arguments.get("table_name", "").lower()

        if table_name not in TABLE_DOCS:
            return [TextContent(type="text", text=f"Tabela '{table_name}' não encontrada.")]

        data = await api_request("GET", f"/mcp/tables/{table_name}/stats")

        if isinstance(data, dict) and "error" in data:
            return [TextContent(type="text", text=f"ERRO: {data['error']}")]

        result = f"# Estatísticas: {table_name}\n\n"
        result += f"**Total de registros:** {data.get('total_records', 0)}\n\n"

        if "columns" in data:
            result += "## Colunas\n\n"
            for col, desc in data["columns"].items():
                result += f"- **{col}**: {desc}\n"

        return [TextContent(type="text", text=result)]

    elif name == "check_connection":
        data = await api_request("GET", "/mcp/me")

        if isinstance(data, dict) and "error" in data:
            return [TextContent(type="text", text=f"ERRO: {data['error']}")]

        result = "# Conexão OK\n\n"
        result += f"**Usuário:** {data.get('name', 'N/A')}\n"
        result += f"**Email:** {data.get('email', 'N/A')}\n"
        result += f"**ID:** {data.get('id', 'N/A')}\n"
        result += f"**Ativo:** {'Sim' if data.get('is_active') else 'Não'}\n"

        return [TextContent(type="text", text=result)]

    return [TextContent(type="text", text=f"Ferramenta '{name}' não encontrada.")]


async def main():
    """Executa o servidor MCP."""
    if not API_KEY:
        print("AVISO: BIVETO_API_KEY não configurada.")
        print("Para usar o MCP, gere uma API Key em: Configurações > API Keys")
        print("Depois configure a variável de ambiente BIVETO_API_KEY")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
