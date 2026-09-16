from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy import and_, func, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models import (
    Account,
    BenefitCard,
    Budget,
    BudgetItem,
    Category,
    ChatConversation,
    ChatMessage,
    CreditCard,
    CreditCardInvoice,
    Debt,
    DebtPayment,
    Document,
    Goal,
    GoalContribution,
    GroceryPriceHistory,
    GroceryProduct,
    GroceryPurchase,
    IncomeSource,
    InstallmentSeries,
    Merchant,
    Receipt,
    ReceiptPayment,
    RecurringTransaction,
    ShoppingList,
    ShoppingListItem,
    Transaction,
    User,
)
from ....models.credit_card_invoice import InvoiceStatus
from ....models.debt import DebtStatus
from ....models.household import HouseholdMember
from ....models.transaction import TransactionType
from ..schemas import ColumnInfo, ContextRequest, QueryRequest, TableInfo

# Mapeamento de tabelas permitidas e suas descrições
ALLOWED_TABLES = {
    "accounts": {
        "model": Account,
        "description": "Contas financeiras (carteira, banco, cartão, investimento)",
        "columns": {
            "id": "ID único da conta",
            "name": "Nome da conta",
            "type": "Tipo: wallet, bank, credit_card, investment",
            "bank_id": "Identificador do banco",
            "balance": "Saldo atual",
            "currency": "Moeda (BRL)",
            "color": "Cor hexadecimal",
            "icon": "Ícone",
            "is_active": "Se está ativa",
            "ownership_type": "personal ou household",
            "created_at": "Data de criação",
            "updated_at": "Data de atualização",
        },
    },
    "transactions": {
        "model": Transaction,
        "description": "Transações financeiras (despesas, receitas, transferências)",
        "columns": {
            "id": "ID único",
            "account_id": "ID da conta",
            "category_id": "ID da categoria",
            "credit_card_id": "ID do cartão (se crédito)",
            "invoice_id": "ID da fatura",
            "income_source_id": "ID da fonte de renda",
            "type": "expense, income ou transfer",
            "payment_method": "Método de pagamento",
            "amount": "Valor",
            "date": "Data da transação",
            "description": "Descrição",
            "notes": "Observações",
            "is_recurring": "Se é recorrente",
            "installment_number": "Parcela atual",
            "installment_total": "Total de parcelas",
            "is_paid": "Se foi paga",
            "tags": "Tags (JSON)",
            "is_fixed": "Se é despesa fixa",
            "ownership_type": "personal ou household",
            "created_at": "Data de criação",
        },
    },
    "categories": {
        "model": Category,
        "description": "Categorias para classificar transações",
        "columns": {
            "id": "ID único",
            "name": "Nome",
            "type": "expense ou income",
            "icon": "Ícone",
            "color": "Cor",
            "parent_id": "ID da categoria pai",
            "is_system": "Se é do sistema",
            "created_at": "Data de criação",
        },
    },
    "credit_cards": {
        "model": CreditCard,
        "description": "Cartões de crédito",
        "columns": {
            "id": "ID único",
            "account_id": "ID da conta vinculada",
            "credit_limit": "Limite de crédito",
            "closing_day": "Dia de fechamento",
            "due_day": "Dia de vencimento",
            "has_points": "Se acumula pontos",
            "points_program": "Programa de pontos",
            "nickname": "Apelido do cartão",
            "card_brand": "Bandeira",
            "card_variant": "Variante (Platinum, Black)",
            "annual_fee": "Anuidade",
            "is_active": "Se está ativo",
            "created_at": "Data de criação",
        },
    },
    "credit_card_invoices": {
        "model": CreditCardInvoice,
        "description": "Faturas de cartão de crédito",
        "columns": {
            "id": "ID único",
            "credit_card_id": "ID do cartão",
            "reference_month": "Mês de referência",
            "reference_year": "Ano de referência",
            "closing_date": "Data de fechamento",
            "due_date": "Data de vencimento",
            "total_amount": "Valor total",
            "minimum_payment": "Pagamento mínimo",
            "status": "open, closed, paid, partial, overdue",
            "paid_amount": "Valor pago",
            "paid_at": "Data de pagamento",
            "created_at": "Data de criação",
        },
    },
    "installment_series": {
        "model": InstallmentSeries,
        "description": "Séries de compras parceladas",
        "columns": {
            "id": "ID único",
            "description": "Descrição da compra",
            "merchant_name": "Nome do comerciante",
            "total_amount": "Valor total",
            "installment_amount": "Valor da parcela",
            "installment_count": "Total de parcelas",
            "purchase_date": "Data da compra",
            "first_installment_date": "Data da primeira parcela",
            "credit_card_id": "ID do cartão",
            "status": "active, completed, cancelled",
            "paid_count": "Parcelas pagas",
            "created_at": "Data de criação",
        },
    },
    "budgets": {
        "model": Budget,
        "description": "Orçamentos mensais",
        "columns": {
            "id": "ID único",
            "year": "Ano",
            "month": "Mês",
            "total_income_planned": "Receita planejada",
            "total_expense_planned": "Despesa planejada",
            "allow_rollover": "Permite acumular",
            "ownership_type": "personal ou household",
            "created_at": "Data de criação",
        },
    },
    "budget_items": {
        "model": BudgetItem,
        "description": "Itens do orçamento por categoria",
        "columns": {
            "id": "ID único",
            "budget_id": "ID do orçamento",
            "category_id": "ID da categoria",
            "planned_amount": "Valor planejado",
            "rollover_amount": "Valor acumulado",
            "is_fixed": "Se é despesa fixa",
            "priority": "Prioridade",
            "created_at": "Data de criação",
        },
    },
    "goals": {
        "model": Goal,
        "description": "Metas financeiras",
        "columns": {
            "id": "ID único",
            "name": "Nome",
            "description": "Descrição",
            "type": "savings, emergency, debt_free, investment, etc",
            "target_amount": "Valor alvo",
            "current_amount": "Valor atual",
            "start_date": "Data de início",
            "target_date": "Data alvo",
            "status": "active, paused, completed, cancelled",
            "ownership_type": "personal ou household",
            "created_at": "Data de criação",
        },
    },
    "goal_contributions": {
        "model": GoalContribution,
        "description": "Contribuições para metas",
        "columns": {
            "id": "ID único",
            "goal_id": "ID da meta",
            "amount": "Valor",
            "contribution_date": "Data",
            "notes": "Observações",
            "created_at": "Data de criação",
        },
    },
    "debts": {
        "model": Debt,
        "description": "Dívidas",
        "columns": {
            "id": "ID único",
            "name": "Nome",
            "type": "Tipo da dívida",
            "creditor": "Credor",
            "original_amount": "Valor original",
            "current_balance": "Saldo atual",
            "minimum_payment": "Pagamento mínimo",
            "interest_rate": "Taxa de juros",
            "status": "active, paid_off, negotiating, defaulted",
            "ownership_type": "personal ou household",
            "created_at": "Data de criação",
        },
    },
    "debt_payments": {
        "model": DebtPayment,
        "description": "Pagamentos de dívidas",
        "columns": {
            "id": "ID único",
            "debt_id": "ID da dívida",
            "amount": "Valor total",
            "principal_amount": "Valor amortizado",
            "interest_amount": "Valor de juros",
            "payment_date": "Data",
            "created_at": "Data de criação",
        },
    },
    "recurring_transactions": {
        "model": RecurringTransaction,
        "description": "Transações recorrentes programadas",
        "columns": {
            "id": "ID único",
            "account_id": "ID da conta",
            "category_id": "ID da categoria",
            "name": "Nome",
            "amount": "Valor",
            "type": "expense ou income",
            "frequency": "daily, weekly, monthly, yearly",
            "day_of_month": "Dia do mês",
            "start_date": "Data de início",
            "end_date": "Data de término",
            "status": "active, paused, cancelled",
            "next_due_date": "Próxima data",
            "ownership_type": "personal ou household",
            "created_at": "Data de criação",
        },
    },
    "income_sources": {
        "model": IncomeSource,
        "description": "Fontes de renda",
        "columns": {
            "id": "ID único",
            "name": "Nome",
            "type": "salary, freelance, business, rental, etc",
            "source_name": "Nome da empresa/fonte",
            "expected_amount": "Valor esperado",
            "is_variable": "Se é variável",
            "frequency": "Frequência",
            "payment_day": "Dia de pagamento",
            "is_active": "Se está ativa",
            "ownership_type": "personal ou household",
            "created_at": "Data de criação",
        },
    },
    "documents": {
        "model": Document,
        "description": "Documentos/comprovantes",
        "columns": {
            "id": "ID único",
            "original_filename": "Nome original",
            "mime_type": "Tipo MIME",
            "status": "pending, processing, completed, failed",
            "document_type": "Tipo do documento",
            "created_at": "Data de criação",
            "processed_at": "Data de processamento",
        },
    },
    "merchants": {
        "model": Merchant,
        "description": "Comerciantes identificados",
        "columns": {
            "id": "ID único",
            "name": "Nome",
            "normalized_name": "Nome normalizado",
            "cnpj": "CNPJ",
            "category_id": "Categoria sugerida",
            "created_at": "Data de criação",
        },
    },
    "receipts": {
        "model": Receipt,
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
            "confirmed_at": "Data de confirmação",
        },
    },
    "receipt_payments": {
        "model": ReceiptPayment,
        "description": "Pagamentos de recibos (split payment)",
        "columns": {
            "id": "ID único",
            "receipt_id": "ID do recibo",
            "account_id": "ID da conta",
            "benefit_card_id": "ID do cartão de benefício (se usado)",
            "payment_method": "Método: voucher_va, debit_card, pix, etc",
            "amount": "Valor pago",
            "sequence": "Sequência do pagamento",
            "original_label": "Label original do OCR",
            "created_at": "Data de criação",
        },
    },
    "benefit_cards": {
        "model": BenefitCard,
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
            "created_at": "Data de criação",
        },
    },
    "grocery_products": {
        "model": GroceryProduct,
        "description": "Catálogo de produtos de mercado",
        "columns": {
            "id": "ID único",
            "name": "Nome do produto",
            "normalized_name": "Nome normalizado",
            "category": "Categoria: fruits_vegetables, meat_fish, dairy, etc",
            "necessity_type": "Tipo: essential, non_essential",
            "default_unit": "Unidade padrão (kg, un, L)",
            "is_system": "Se é produto do sistema",
            "created_at": "Data de criação",
        },
    },
    "grocery_purchases": {
        "model": GroceryPurchase,
        "description": "Compras de supermercado (itens)",
        "columns": {
            "id": "ID único",
            "transaction_id": "ID da transação",
            "document_id": "ID do documento",
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
            "ownership_type": "personal ou household",
            "created_at": "Data de criação",
        },
    },
    "grocery_price_history": {
        "model": GroceryPriceHistory,
        "description": "Histórico de preços de produtos",
        "columns": {
            "id": "ID único",
            "product_id": "ID do produto",
            "merchant_id": "ID do comerciante",
            "price": "Preço",
            "unit": "Unidade",
            "recorded_at": "Data do registro",
            "created_at": "Data de criação",
        },
    },
    "shopping_lists": {
        "model": ShoppingList,
        "description": "Listas de compras",
        "columns": {
            "id": "ID único",
            "license_id": "ID da licença (household)",
            "name": "Nome da lista",
            "status": "draft, active, completed, archived",
            "source": "Origem: manual, ai_generated, history",
            "ownership_type": "personal ou household",
            "notes": "Observações",
            "created_at": "Data de criação",
            "completed_at": "Data de conclusão",
        },
    },
    "shopping_list_items": {
        "model": ShoppingListItem,
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
            "necessity_type": "Tipo de necessidade",
            "is_checked": "Se foi marcado",
            "priority": "Prioridade",
            "notes": "Observações",
            "created_at": "Data de criação",
        },
    },
    "chat_conversations": {
        "model": ChatConversation,
        "description": "Conversas do chat com assistente financeiro",
        "columns": {
            "id": "ID único (UUID)",
            "title": "Título da conversa",
            "created_at": "Data de criação",
            "updated_at": "Data de atualização",
        },
    },
    "chat_messages": {
        "model": ChatMessage,
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


def serialize_value(value: Any) -> Any:
    """Serializa valores para JSON"""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


class MCPService:
    """Service para consultas MCP"""

    def __init__(self, db: AsyncSession):
        self.db = db

    def get_table_list(self) -> list[TableInfo]:
        """Lista todas as tabelas disponíveis com suas descrições"""
        tables = []
        for name, info in ALLOWED_TABLES.items():
            columns = [
                ColumnInfo(name=col, description=desc) for col, desc in info["columns"].items()
            ]
            tables.append(
                TableInfo(
                    name=name,
                    description=info["description"],
                    columns=columns,
                )
            )
        return tables

    async def query_table(
        self,
        user: User,
        request: QueryRequest,
    ) -> tuple[list[dict], int]:
        """
        Consulta uma tabela filtrando pelo user_id.
        Retorna (dados, total).
        """
        if request.table not in ALLOWED_TABLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tabela '{request.table}' não permitida. Use /mcp/tables para ver tabelas disponíveis.",
            )

        table_info = ALLOWED_TABLES[request.table]
        model = table_info["model"]

        # Verifica se a tabela tem user_id (para filtrar)
        has_user_id = hasattr(model, "user_id")

        # Query base
        query = select(model)

        # Filtro por user_id (segurança)
        if has_user_id:
            query = query.where(model.user_id == user.id)

        # Filtro de busca por texto (search)
        if request.search:
            search_term = f"%{request.search}%"
            if hasattr(model, "description"):
                query = query.where(model.description.ilike(search_term))
            elif hasattr(model, "name"):
                query = query.where(model.name.ilike(search_term))

        # Filtro de data (date_from, date_to)
        if hasattr(model, "date"):
            if request.date_from:
                query = query.where(model.date >= request.date_from)
            if request.date_to:
                query = query.where(model.date <= request.date_to)

        # Filtro de valor (amount_min, amount_max)
        if hasattr(model, "amount"):
            if request.amount_min is not None:
                query = query.where(model.amount >= request.amount_min)
            if request.amount_max is not None:
                query = query.where(model.amount <= request.amount_max)

        # Filtros exatos adicionais
        if request.filters:
            for col, val in request.filters.items():
                if hasattr(model, col):
                    column = getattr(model, col)
                    if val is None:
                        query = query.where(column.is_(None))
                    elif isinstance(val, list):
                        query = query.where(column.in_(val))
                    else:
                        query = query.where(column == val)

        # Conta total antes de limit/offset
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Ordenação
        if request.order_by and hasattr(model, request.order_by):
            order_col = getattr(model, request.order_by)
            query = query.order_by(order_col.desc() if request.order_desc else order_col)
        elif hasattr(model, "created_at"):
            query = query.order_by(model.created_at.desc())

        # Paginação
        query = query.limit(request.limit).offset(request.offset)

        # Executa
        result = await self.db.execute(query)
        rows = result.scalars().all()

        # Converte para dicts
        data = []
        for row in rows:
            row_dict = {}
            mapper = inspect(row.__class__)
            for column in mapper.columns:
                value = getattr(row, column.key)
                row_dict[column.key] = serialize_value(value)
            data.append(row_dict)

        return data, total

    async def get_table_stats(self, user: User, table_name: str) -> dict:
        """Retorna estatísticas de uma tabela"""
        if table_name not in ALLOWED_TABLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tabela '{table_name}' não permitida.",
            )

        table_info = ALLOWED_TABLES[table_name]
        model = table_info["model"]
        has_user_id = hasattr(model, "user_id")

        # Query base
        query = select(model)
        if has_user_id:
            query = query.where(model.user_id == user.id)

        # Conta total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        return {
            "table": table_name,
            "total_records": total,
            "columns": table_info["columns"],
        }

    async def get_summary(self, user: User) -> dict:
        """Retorna um resumo geral dos dados do usuário"""
        summary = {}

        # Contas
        accounts_result = await self.db.execute(
            select(func.count(), func.sum(Account.balance)).where(
                Account.user_id == user.id, Account.is_active == True
            )
        )
        accounts_row = accounts_result.fetchone()
        summary["accounts"] = {
            "count": accounts_row[0] or 0,
            "total_balance": float(accounts_row[1]) if accounts_row[1] else 0,
        }

        # Transações do mês atual
        today = date.today()
        first_of_month = date(today.year, today.month, 1)
        transactions_result = await self.db.execute(
            select(
                func.count(),
                func.sum(Transaction.amount).filter(Transaction.type == "expense"),
                func.sum(Transaction.amount).filter(Transaction.type == "income"),
            ).where(
                Transaction.user_id == user.id,
                Transaction.date >= first_of_month,
            )
        )
        trans_row = transactions_result.fetchone()
        summary["transactions_this_month"] = {
            "count": trans_row[0] or 0,
            "total_expenses": float(trans_row[1]) if trans_row[1] else 0,
            "total_income": float(trans_row[2]) if trans_row[2] else 0,
        }

        # Cartões de crédito
        cards_result = await self.db.execute(
            select(func.count()).where(CreditCard.user_id == user.id, CreditCard.is_active == True)
        )
        summary["credit_cards"] = {
            "count": cards_result.scalar() or 0,
        }

        # Faturas abertas
        invoices_result = await self.db.execute(
            select(func.count(), func.sum(CreditCardInvoice.total_amount)).where(
                CreditCardInvoice.user_id == user.id,
                CreditCardInvoice.status.in_(["open", "closed"]),
            )
        )
        inv_row = invoices_result.fetchone()
        summary["open_invoices"] = {
            "count": inv_row[0] or 0,
            "total_amount": float(inv_row[1]) if inv_row[1] else 0,
        }

        # Metas ativas
        goals_result = await self.db.execute(
            select(func.count(), func.sum(Goal.current_amount), func.sum(Goal.target_amount)).where(
                Goal.user_id == user.id, Goal.status == "active"
            )
        )
        goals_row = goals_result.fetchone()
        summary["active_goals"] = {
            "count": goals_row[0] or 0,
            "current_total": float(goals_row[1]) if goals_row[1] else 0,
            "target_total": float(goals_row[2]) if goals_row[2] else 0,
        }

        # Dívidas ativas
        debts_result = await self.db.execute(
            select(func.count(), func.sum(Debt.current_balance)).where(
                Debt.user_id == user.id, Debt.status == "active"
            )
        )
        debts_row = debts_result.fetchone()
        summary["active_debts"] = {
            "count": debts_row[0] or 0,
            "total_balance": float(debts_row[1]) if debts_row[1] else 0,
        }

        return summary

    # Mapeamento de meses em português
    MONTHS_PT = {
        "janeiro": 1,
        "fevereiro": 2,
        "marco": 3,
        "abril": 4,
        "maio": 5,
        "junho": 6,
        "julho": 7,
        "agosto": 8,
        "setembro": 9,
        "outubro": 10,
        "novembro": 11,
        "dezembro": 12,
        "jan": 1,
        "fev": 2,
        "mar": 3,
        "abr": 4,
        "mai": 5,
        "jun": 6,
        "jul": 7,
        "ago": 8,
        "set": 9,
        "out": 10,
        "nov": 11,
        "dez": 12,
    }

    async def _get_household_user_ids(self, user: User) -> list[int]:
        """Busca IDs de usuários do mesmo household"""
        if not user.license_id:
            return []

        result = await self.db.execute(
            select(HouseholdMember.user_id).where(HouseholdMember.license_id == user.license_id)
        )
        return list(result.scalars().all())

    def _parse_period(self, request: ContextRequest) -> dict[str, Any]:
        """Analisa parâmetros de período e retorna datas de início/fim"""
        today = date.today()

        # Se informou mês específico
        if request.month:
            month_num = request.month
            if isinstance(request.month, str):
                month_num = self.MONTHS_PT.get(request.month.lower(), today.month)
            year = request.year or today.year
            # Se mês > mês atual, provavelmente é ano anterior
            if month_num > today.month and not request.year:
                year -= 1
            start = date(year, month_num, 1)
            end = (start + relativedelta(months=1)) - timedelta(days=1)
            return {"start": start, "end": end}

        # Se informou datas customizadas
        if request.date_from and request.date_to:
            return {
                "start": datetime.strptime(request.date_from, "%Y-%m-%d").date(),
                "end": datetime.strptime(request.date_to, "%Y-%m-%d").date(),
            }

        # Padrão: mês atual
        return {
            "start": date(today.year, today.month, 1),
            "end": today,
        }

    async def get_context(self, user: User, request: ContextRequest) -> dict[str, Any]:
        """
        Retorna contexto financeiro agregado para análise por IA.
        Similar ao que o chatbot interno usa, mas otimizado para o MCP.
        """
        context: dict[str, Any] = {}
        period = self._parse_period(request)
        period_start = period["start"]
        period_end = period["end"]

        household_user_ids = await self._get_household_user_ids(user)

        # 1. Buscar categorias do usuário
        categories_result = await self.db.execute(
            select(Category).where(Category.user_id == user.id)
        )
        categories: dict[int | None, str] = {
            c.id: c.name for c in categories_result.scalars().all()
        }

        # 2. Resumo de contas
        if household_user_ids:
            accounts_query = select(Account).where(
                or_(
                    and_(Account.user_id == user.id, Account.ownership_type == "personal"),
                    and_(
                        Account.user_id.in_(household_user_ids),
                        Account.ownership_type == "household",
                    ),
                )
            )
        else:
            accounts_query = select(Account).where(Account.user_id == user.id)

        accounts = await self.db.execute(accounts_query)
        accounts_list = accounts.scalars().all()
        context["contas"] = [
            {"nome": a.name, "tipo": a.type, "saldo": float(a.balance)}
            for a in accounts_list
            if a.is_active
        ]
        context["saldo_total"] = sum(float(a.balance) for a in accounts_list if a.is_active)

        # 3. Transações do período
        if household_user_ids:
            tx_query = select(Transaction).where(
                Transaction.date >= period_start,
                Transaction.date <= period_end,
                or_(
                    and_(Transaction.user_id == user.id, Transaction.ownership_type == "personal"),
                    and_(
                        Transaction.user_id.in_(household_user_ids),
                        Transaction.ownership_type == "household",
                    ),
                ),
            )
        else:
            tx_query = select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.date >= period_start,
                Transaction.date <= period_end,
            )

        transactions = await self.db.execute(tx_query)
        txs = transactions.scalars().all()

        # Buscar merchants para mapear IDs para nomes
        merchant_ids = [t.merchant_id for t in txs if t.merchant_id]
        merchants: dict[int | None, str] = {}
        if merchant_ids:
            merchants_result = await self.db.execute(
                select(Merchant).where(Merchant.id.in_(merchant_ids))
            )
            merchants = {m.id: m.name for m in merchants_result.scalars().all()}

        # Calcular totais
        receitas = sum(float(t.amount) for t in txs if t.type == TransactionType.INCOME.value)
        despesas = sum(float(t.amount) for t in txs if t.type == TransactionType.EXPENSE.value)

        context["periodo"] = {
            "inicio": period_start.strftime("%d/%m/%Y"),
            "fim": period_end.strftime("%d/%m/%Y"),
        }

        context["resumo"] = {
            "receitas": round(receitas, 2),
            "despesas": round(despesas, 2),
            "saldo": round(receitas - despesas, 2),
            "total_transacoes": len(txs),
        }

        # 4. Gastos por categoria - SEMPRE retorna todos para o ChatGPT analisar
        gastos_por_categoria: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total": 0, "count": 0, "transacoes": []}
        )
        search_keyword = request.search.lower() if request.search else None

        # Função para verificar se transação corresponde à busca (para destacar resultados)
        def matches_search(description: str, merchant_name: str, category: str) -> bool:
            """Verifica se a transação corresponde ao termo de busca"""
            if not search_keyword:
                return False
            text_to_search = f"{description} {merchant_name} {category}".lower()
            return search_keyword in text_to_search

        # Acumula transações que correspondem à busca para destaque
        transacoes_encontradas: list[dict[str, Any]] = []
        total_encontrado = 0.0

        for t in txs:
            if t.type == TransactionType.EXPENSE.value:
                cat_name = categories.get(t.category_id, "Sem categoria")
                merchant_name = merchants.get(t.merchant_id, t.description or "Não identificado")
                description = t.description or ""

                # SEMPRE adiciona aos totais por categoria
                gastos_por_categoria[cat_name]["total"] += float(t.amount)
                gastos_por_categoria[cat_name]["count"] += 1
                # Limitar transações detalhadas para não ficar muito grande
                if len(gastos_por_categoria[cat_name]["transacoes"]) < 5:
                    gastos_por_categoria[cat_name]["transacoes"].append(
                        {
                            "valor": float(t.amount),
                            "data": t.date.strftime("%d/%m"),
                            "estabelecimento": merchant_name,
                            "descricao": description,
                        }
                    )

                # Se tem keyword e corresponde, acumula para destaque
                if search_keyword and matches_search(description, merchant_name, cat_name):
                    total_encontrado += float(t.amount)
                    if len(transacoes_encontradas) < 20:
                        transacoes_encontradas.append(
                            {
                                "valor": float(t.amount),
                                "data": t.date.strftime("%d/%m/%Y"),
                                "estabelecimento": merchant_name,
                                "descricao": description,
                                "categoria": cat_name,
                            }
                        )

        # Ordenar por valor e arredondar
        context["gastos_por_categoria"] = {
            k: {"total": round(v["total"], 2), "count": v["count"], "transacoes": v["transacoes"]}
            for k, v in sorted(
                gastos_por_categoria.items(), key=lambda x: x[1]["total"], reverse=True
            )
        }

        # Se teve busca, adiciona resultado destacado
        if search_keyword:
            context["resultado_busca"] = {
                "termo": request.search,
                "total": round(total_encontrado, 2),
                "quantidade": len(transacoes_encontradas),
                "transacoes": sorted(
                    transacoes_encontradas, key=lambda x: x["valor"], reverse=True
                ),
                "dica": "Se não encontrou o que procurava, analise os dados de gastos_por_categoria e gastos_por_estabelecimento para encontrar transações relacionadas.",
            }

        # 5. Gastos por estabelecimento (top 15) - SEMPRE retorna todos
        gastos_por_estabelecimento: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total": 0, "count": 0}
        )
        for t in txs:
            if t.type == TransactionType.EXPENSE.value:
                merchant_name = merchants.get(t.merchant_id, t.description or "Outros")
                gastos_por_estabelecimento[merchant_name]["total"] += float(t.amount)
                gastos_por_estabelecimento[merchant_name]["count"] += 1

        context["gastos_por_estabelecimento"] = {
            k: {"total": round(v["total"], 2), "count": v["count"]}
            for k, v in sorted(
                gastos_por_estabelecimento.items(), key=lambda x: x[1]["total"], reverse=True
            )[:10]
        }

        # 6. Receitas por categoria
        receitas_por_categoria: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total": 0, "count": 0}
        )
        for t in txs:
            if t.type == TransactionType.INCOME.value:
                cat_name = categories.get(t.category_id, "Sem categoria")
                receitas_por_categoria[cat_name]["total"] += float(t.amount)
                receitas_por_categoria[cat_name]["count"] += 1

        context["receitas_por_categoria"] = {
            k: {"total": round(v["total"], 2), "count": v["count"]}
            for k, v in receitas_por_categoria.items()
        }

        # 7. Top 10 maiores gastos do período (SEMPRE sem filtro)
        todas_despesas = [t for t in txs if t.type == TransactionType.EXPENSE.value]
        todas_despesas.sort(key=lambda x: float(x.amount), reverse=True)

        context["maiores_gastos"] = [
            {
                "valor": float(t.amount),
                "data": t.date.strftime("%d/%m/%Y"),
                "estabelecimento": merchants.get(
                    t.merchant_id, t.description or "Não identificado"
                ),
                "categoria": categories.get(t.category_id, "Sem categoria"),
            }
            for t in todas_despesas[:10]
        ]

        # 9. Dívidas ativas
        debts = await self.db.execute(
            select(Debt).where(Debt.user_id == user.id, Debt.status == DebtStatus.ACTIVE.value)
        )
        debts_list = debts.scalars().all()
        context["dividas"] = [
            {
                "nome": d.name,
                "saldo": float(d.current_balance),
                "taxa_juros": float(d.interest_rate) * 100 if d.interest_rate else 0,
                "pagamento_minimo": float(d.minimum_payment) if d.minimum_payment else 0,
            }
            for d in debts_list
        ]
        context["total_dividas"] = round(sum(float(d.current_balance) for d in debts_list), 2)

        # 10. Metas financeiras
        goals = await self.db.execute(
            select(Goal).where(Goal.user_id == user.id, Goal.status == "active")
        )
        goals_list = goals.scalars().all()
        context["metas"] = [
            {
                "nome": g.name,
                "valor_alvo": float(g.target_amount),
                "valor_atual": float(g.current_amount),
                "progresso": round(float(g.current_amount / g.target_amount * 100), 1)
                if g.target_amount > 0
                else 0,
                "falta": round(float(g.target_amount - g.current_amount), 2),
            }
            for g in goals_list
        ]

        # 11. Cartões de crédito e faturas
        credit_cards_result = await self.db.execute(
            select(CreditCard).where(CreditCard.user_id == user.id, CreditCard.is_active == True)
        )
        credit_cards_list = credit_cards_result.scalars().all()

        cartoes_info = []
        for card in credit_cards_list:
            invoices_result = await self.db.execute(
                select(CreditCardInvoice)
                .where(
                    CreditCardInvoice.credit_card_id == card.id,
                    or_(
                        CreditCardInvoice.status == InvoiceStatus.OPEN.value,
                        CreditCardInvoice.status == InvoiceStatus.CLOSED.value,
                        CreditCardInvoice.status == InvoiceStatus.PARTIAL.value,
                        CreditCardInvoice.status == InvoiceStatus.OVERDUE.value,
                    ),
                )
                .order_by(
                    CreditCardInvoice.reference_year.desc(),
                    CreditCardInvoice.reference_month.desc(),
                )
            )
            invoices_list = invoices_result.scalars().all()

            saldo_em_aberto = sum(
                float(inv.remaining_amount)
                for inv in invoices_list
                if inv.status != InvoiceStatus.PAID.value
            )

            # Buscar conta vinculada
            account_result = await self.db.execute(
                select(Account).where(Account.id == card.account_id)
            )
            account = account_result.scalar_one_or_none()

            faturas_info = []
            for inv in invoices_list[:2]:  # Mostrar até 2 faturas
                faturas_info.append(
                    {
                        "periodo": f"{inv.reference_month:02d}/{inv.reference_year}",
                        "status": inv.status,
                        "valor_total": float(inv.total_amount),
                        "valor_restante": float(inv.remaining_amount),
                        "vencimento": inv.due_date.strftime("%d/%m/%Y"),
                    }
                )

            cartoes_info.append(
                {
                    "nome": account.name if account else card.nickname or "Cartão",
                    "bandeira": card.card_brand,
                    "limite_total": float(card.credit_limit),
                    "saldo_em_aberto": round(saldo_em_aberto, 2),
                    "limite_disponivel": round(float(card.credit_limit) - saldo_em_aberto, 2),
                    "faturas": faturas_info,
                }
            )

        context["cartoes_credito"] = cartoes_info

        # 12. Comparação com período anterior
        last_month = period_start - relativedelta(months=1)
        last_month_start = date(last_month.year, last_month.month, 1)
        last_month_end = (last_month_start + relativedelta(months=1)) - timedelta(days=1)

        if household_user_ids:
            last_month_query = select(Transaction).where(
                Transaction.date >= last_month_start,
                Transaction.date <= last_month_end,
                or_(
                    and_(Transaction.user_id == user.id, Transaction.ownership_type == "personal"),
                    and_(
                        Transaction.user_id.in_(household_user_ids),
                        Transaction.ownership_type == "household",
                    ),
                ),
            )
        else:
            last_month_query = select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.date >= last_month_start,
                Transaction.date <= last_month_end,
            )

        last_txs = await self.db.execute(last_month_query)
        last_txs_list = last_txs.scalars().all()

        last_despesas = sum(
            float(t.amount) for t in last_txs_list if t.type == TransactionType.EXPENSE.value
        )
        last_receitas = sum(
            float(t.amount) for t in last_txs_list if t.type == TransactionType.INCOME.value
        )

        context["comparacao_periodo_anterior"] = {
            "periodo": f"{last_month_start.strftime('%d/%m')} - {last_month_end.strftime('%d/%m/%Y')}",
            "despesas": round(last_despesas, 2),
            "receitas": round(last_receitas, 2),
            "variacao_despesas_pct": round(
                ((despesas - last_despesas) / max(1, last_despesas)) * 100, 1
            )
            if last_despesas > 0
            else 0,
        }

        return context
