from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.budget import BudgetItemStatus
from app.models.category import Category
from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import CreditCardInvoice, InvoiceStatus
from app.models.household import HouseholdMember
from app.models.merchant import Merchant
from app.models.transaction import PaymentMethod, Transaction, TransactionType
from app.models.user import User
from app.modules.analytics.schemas.analytics import (
    AnalyticsSummary,
    CategorySummary,
    InsightResponse,
    MerchantSummary,
    PaymentMethodReport,
    PaymentMethodSummary,
)


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._household_user_ids_cache: dict[int, list[int]] = {}

    async def _get_household_user_ids_cached(self, user: User) -> list[int]:
        """Cached version of _get_household_user_ids"""
        if user.id not in self._household_user_ids_cache:
            self._household_user_ids_cache[user.id] = await self._get_household_user_ids(user)
        return self._household_user_ids_cache[user.id]

    async def get_monthly_summary(self, user: User, year: int, month: int) -> AnalyticsSummary:
        # Calcular periodo
        _, last_day = monthrange(year, month)
        period_start = date(year, month, 1)
        period_end = date(year, month, last_day)

        # Periodo anterior para comparacao
        prev_start = period_start - timedelta(days=period_start.day)
        prev_end = period_start - timedelta(days=1)

        # Pre-cache household_user_ids (uma unica query)
        household_user_ids = await self._get_household_user_ids_cached(user)
        user_ids = [user.id] + household_user_ids if household_user_ids else [user.id]

        # Executar queries sequencialmente (SQLAlchemy async nao suporta paralelo na mesma sessao)
        transactions = await self._get_transactions_fast(
            user_ids, household_user_ids, period_start, period_end
        )
        payment_transaction_ids = await self._get_invoice_payment_ids_fast(user_ids)
        credit_card_expenses = await self._get_invoices_total_fast(user_ids, year, month)
        pending_invoices = await self._get_pending_invoices_fast(user_ids, year, month)

        # Calcular totais (converter para float para evitar problemas com Decimal)
        # Excluir transfers dos totais de receita/despesa
        total_income = float(
            sum(
                t.amount
                for t in transactions
                if t.type == TransactionType.INCOME
                and t.type != TransactionType.TRANSFER  # Excluir transfers
            )
            or 0
        )

        # Debito/Dinheiro = despesas SEM invoice_id (nao sao de cartao) no periodo
        # Excluir transfers dos totais
        debit_cash_expenses = float(
            sum(
                t.amount
                for t in transactions
                if t.type == TransactionType.EXPENSE
                and t.type != TransactionType.TRANSFER  # Excluir transfers
                and t.id not in payment_transaction_ids
                and getattr(t, "invoice_id", None) is None
            )
            or 0
        )

        # Total de despesas = faturas do mes + gastos no debito/dinheiro
        total_expense = credit_card_expenses + debit_cash_expenses

        # Fixos = despesas fixas no debito (nao conta cartao pois ja esta na fatura)
        # Excluir transfers
        fixed_expenses = float(
            sum(
                t.amount
                for t in transactions
                if t.type == TransactionType.EXPENSE
                and t.type != TransactionType.TRANSFER  # Excluir transfers
                and t.is_fixed
                and t.id not in payment_transaction_ids
                and getattr(t, "invoice_id", None) is None
            )
            or 0
        )
        variable_expenses = debit_cash_expenses - fixed_expenses

        # Agrupar por categoria e merchant via SQL GROUP BY (mais eficiente)
        categories = await self._group_by_category_sql(
            user_ids, household_user_ids, period_start, period_end, payment_transaction_ids
        )
        top_merchants = await self._group_by_merchant_sql(
            user_ids, household_user_ids, period_start, period_end, payment_transaction_ids
        )

        # Buscar nomes de categorias e merchants em batch
        category_ids = [c["category_id"] for c in categories if c["category_id"]]
        merchant_ids = [m["merchant_id"] for m in top_merchants if m["merchant_id"]]

        cat_names = await self._get_category_names(category_ids) if category_ids else {}
        merch_names = await self._get_merchant_names(merchant_ids) if merchant_ids else {}

        # Aplicar nomes
        for c in categories:
            c["category_name"] = (
                cat_names.get(c["category_id"], "Sem categoria")
                if c["category_id"]
                else "Sem categoria"
            )
        for m in top_merchants:
            m["merchant_name"] = (
                merch_names.get(m["merchant_id"], "Outros") if m["merchant_id"] else "Outros"
            )

        # Converter para schemas
        categories_response = [CategorySummary(**c) for c in categories]
        merchants_response = [MerchantSummary(**m) for m in top_merchants[:10]]

        # Buscar transacoes do periodo anterior para comparacao
        prev_transactions = await self._get_transactions_fast(
            user_ids, household_user_ids, prev_start, prev_end
        )
        prev_expense = float(
            sum(
                t.amount
                for t in prev_transactions
                if t.type == TransactionType.EXPENSE and t.id not in payment_transaction_ids
            )
            or 0
        )

        expense_variation = None
        if prev_expense > 0:
            expense_variation = ((total_expense - prev_expense) / prev_expense) * 100

        # Total pendente = faturas nao pagas
        pending_total = pending_invoices

        # Saldo disponivel = Receitas - Despesas pagas - Pendentes
        available_balance = total_income - total_expense - pending_total

        return AnalyticsSummary(
            period_start=period_start,
            period_end=period_end,
            total_income=total_income,
            total_expense=total_expense,
            balance=total_income - total_expense,
            margin=total_income - total_expense,
            fixed_expenses=fixed_expenses,
            variable_expenses=variable_expenses,
            credit_card_expenses=credit_card_expenses,
            debit_cash_expenses=debit_cash_expenses,
            pending_invoices=pending_invoices,
            pending_total=pending_total,
            available_balance=available_balance,
            categories=categories_response,
            top_merchants=merchants_response,
            previous_period_expense=prev_expense if prev_expense > 0 else None,
            expense_variation=expense_variation,
        )

    async def _get_transactions_fast(
        self, user_ids: list[int], household_user_ids: list[int], start_date: date, end_date: date
    ) -> list[Transaction]:
        """Versao otimizada sem lookup de household_user_ids"""
        if household_user_ids:
            result = await self.db.execute(
                select(Transaction).where(
                    Transaction.date >= start_date,
                    Transaction.date <= end_date,
                    or_(
                        and_(
                            Transaction.user_id.in_(user_ids),
                            Transaction.ownership_type == "personal",
                        ),
                        and_(
                            Transaction.user_id.in_(user_ids),
                            Transaction.ownership_type == "household",
                        ),
                    ),
                )
            )
        else:
            result = await self.db.execute(
                select(Transaction).where(
                    Transaction.user_id.in_(user_ids),
                    Transaction.date >= start_date,
                    Transaction.date <= end_date,
                )
            )
        return list(result.scalars().all())

    async def _get_invoice_payment_ids_fast(self, user_ids: list[int]) -> set[int]:
        """Versao otimizada sem lookup de household_user_ids"""
        try:
            result = await self.db.execute(
                select(CreditCardInvoice.payment_transaction_id).where(
                    CreditCardInvoice.user_id.in_(user_ids),
                    CreditCardInvoice.payment_transaction_id.isnot(None),
                )
            )
            return set(result.scalars().all())
        except Exception:
            return set()

    async def _get_invoices_total_fast(self, user_ids: list[int], year: int, month: int) -> float:
        """Versao otimizada com SUM no banco"""
        try:
            result = await self.db.execute(
                select(func.coalesce(func.sum(CreditCardInvoice.total_amount), 0)).where(
                    CreditCardInvoice.user_id.in_(user_ids),
                    CreditCardInvoice.reference_year == year,
                    CreditCardInvoice.reference_month == month,
                )
            )
            return float(result.scalar() or 0)
        except Exception:
            return 0.0

    async def _get_pending_invoices_fast(self, user_ids: list[int], year: int, month: int) -> float:
        """Versao otimizada com calculo no banco"""
        try:
            result = await self.db.execute(
                select(
                    func.coalesce(
                        func.sum(
                            CreditCardInvoice.total_amount
                            - func.coalesce(CreditCardInvoice.paid_amount, 0)
                        ),
                        0,
                    )
                ).where(
                    CreditCardInvoice.user_id.in_(user_ids),
                    CreditCardInvoice.reference_year == year,
                    CreditCardInvoice.reference_month == month,
                    CreditCardInvoice.status.in_(
                        [
                            InvoiceStatus.OPEN.value,
                            InvoiceStatus.CLOSED.value,
                            InvoiceStatus.OVERDUE.value,
                        ]
                    ),
                )
            )
            return float(result.scalar() or 0)
        except Exception:
            return 0.0

    async def _group_by_category_sql(
        self,
        user_ids: list[int],
        household_user_ids: list[int],
        start_date: date,
        end_date: date,
        payment_exclude_ids: set[int],
    ) -> list[dict]:
        """Group expenses by category using SQL GROUP BY (replaces in-memory version)."""
        # Build base filter
        base_filter = [
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.type == TransactionType.EXPENSE.value,
            Transaction.type != TransactionType.TRANSFER.value,
        ]

        if household_user_ids:
            base_filter.append(
                or_(
                    and_(
                        Transaction.user_id.in_(user_ids), Transaction.ownership_type == "personal"
                    ),
                    and_(
                        Transaction.user_id.in_(user_ids), Transaction.ownership_type == "household"
                    ),
                )
            )
        else:
            base_filter.append(Transaction.user_id.in_(user_ids))

        # Exclude invoice payments
        if payment_exclude_ids:
            base_filter.append(Transaction.id.notin_(payment_exclude_ids))

        result = await self.db.execute(
            select(
                Transaction.category_id,
                func.coalesce(func.sum(Transaction.amount), 0).label("total"),
                func.count(Transaction.id).label("count"),
            )
            .where(*base_filter)
            .group_by(Transaction.category_id)
            .order_by(func.sum(Transaction.amount).desc())
        )
        rows = result.all()

        grand_total = float(sum(r.total for r in rows)) if rows else 0

        return [
            {
                "category_id": row.category_id,
                "category_name": "",
                "total": float(row.total),
                "count": row.count,
                "percentage": (float(row.total) / grand_total * 100) if grand_total > 0 else 0,
                "average": float(row.total) / row.count if row.count > 0 else 0,
            }
            for row in rows
        ]

    async def _group_by_merchant_sql(
        self,
        user_ids: list[int],
        household_user_ids: list[int],
        start_date: date,
        end_date: date,
        payment_exclude_ids: set[int],
    ) -> list[dict]:
        """Group expenses by merchant using SQL GROUP BY (replaces in-memory version)."""
        base_filter = [
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.type == TransactionType.EXPENSE.value,
            Transaction.type != TransactionType.TRANSFER.value,
        ]

        if household_user_ids:
            base_filter.append(
                or_(
                    and_(
                        Transaction.user_id.in_(user_ids), Transaction.ownership_type == "personal"
                    ),
                    and_(
                        Transaction.user_id.in_(user_ids), Transaction.ownership_type == "household"
                    ),
                )
            )
        else:
            base_filter.append(Transaction.user_id.in_(user_ids))

        if payment_exclude_ids:
            base_filter.append(Transaction.id.notin_(payment_exclude_ids))

        result = await self.db.execute(
            select(
                Transaction.merchant_id,
                func.coalesce(func.sum(Transaction.amount), 0).label("total"),
                func.count(Transaction.id).label("count"),
            )
            .where(*base_filter)
            .group_by(Transaction.merchant_id)
            .order_by(func.sum(Transaction.amount).desc())
        )
        rows = result.all()

        return [
            {
                "merchant_id": row.merchant_id,
                "merchant_name": "",
                "total": float(row.total),
                "count": row.count,
            }
            for row in rows
        ]

    # Legacy methods kept for reference — will be removed after validation
    def _group_by_category_sync(
        self, transactions: list[Transaction], exclude_ids: set[int]
    ) -> list[dict]:
        """DEPRECATED: Use _group_by_category_sql instead. Kept for comparison."""
        from collections import defaultdict

        by_category: dict[int | None, list[Transaction]] = defaultdict(list)
        for t in transactions:
            if (
                t.type == TransactionType.EXPENSE
                and t.type != TransactionType.TRANSFER
                and t.id not in exclude_ids
            ):
                by_category[t.category_id].append(t)
        total = float(
            sum(
                t.amount
                for t in transactions
                if t.type == TransactionType.EXPENSE
                and t.type != TransactionType.TRANSFER
                and t.id not in exclude_ids
            )
            or 0
        )
        summaries = []
        for category_id, txs in by_category.items():
            cat_total = float(sum(t.amount for t in txs) or 0)
            summaries.append(
                {
                    "category_id": category_id,
                    "category_name": "",
                    "total": cat_total,
                    "count": len(txs),
                    "percentage": (cat_total / total * 100) if total > 0 else 0,
                    "average": cat_total / len(txs) if txs else 0,
                }
            )
        return sorted(summaries, key=lambda x: x["total"], reverse=True)

    def _group_by_merchant_sync(
        self, transactions: list[Transaction], exclude_ids: set[int]
    ) -> list[dict]:
        """DEPRECATED: Use _group_by_merchant_sql instead. Kept for comparison."""
        from collections import defaultdict

        by_merchant: dict[int | None, list[Transaction]] = defaultdict(list)
        for t in transactions:
            if (
                t.type == TransactionType.EXPENSE
                and t.type != TransactionType.TRANSFER
                and t.id not in exclude_ids
            ):
                by_merchant[t.merchant_id].append(t)
        summaries = []
        for merchant_id, txs in by_merchant.items():
            summaries.append(
                {
                    "merchant_id": merchant_id,
                    "merchant_name": "",
                    "total": float(sum(t.amount for t in txs) or 0),
                    "count": len(txs),
                }
            )
        return sorted(summaries, key=lambda x: x["total"], reverse=True)

    async def _get_category_names(self, category_ids: list[int]) -> dict[int, str]:
        """Busca nomes de categorias em batch"""
        if not category_ids:
            return {}
        result = await self.db.execute(
            select(Category.id, Category.name).where(Category.id.in_(category_ids))
        )
        return {row[0]: row[1] for row in result.all()}

    async def _get_merchant_names(self, merchant_ids: list[int]) -> dict[int, str]:
        """Busca nomes de merchants em batch"""
        if not merchant_ids:
            return {}
        result = await self.db.execute(
            select(Merchant.id, Merchant.name).where(Merchant.id.in_(merchant_ids))
        )
        return {row[0]: row[1] for row in result.all()}

    async def get_insights(
        self, user: User, start_date: date, end_date: date
    ) -> list[InsightResponse]:
        """Gera insights explicaveis sobre os gastos do usuario"""
        try:
            insights = []

            transactions = await self._get_transactions(user, start_date, end_date)

            # CRÍTICO: Excluir pagamentos de fatura para evitar contagem dupla
            payment_transaction_ids = await self._get_invoice_payment_transaction_ids(user)

            expense_transactions = [
                t
                for t in transactions
                if t.type == TransactionType.EXPENSE
                and t.id not in payment_transaction_ids  # Excluir pagamentos de fatura
            ]

            if not expense_transactions:
                return insights

            # Converter Decimal para float para evitar erros
            total_expense = float(sum(t.amount for t in expense_transactions) or 0)

            # 1. Detectar vazamentos (gastos pequenos e frequentes que somam alto)
            try:
                leak_insights = await self._detect_leaks(expense_transactions, total_expense)
                insights.extend(leak_insights)
            except Exception as e:
                print(f"Error detecting leaks: {e}")

            # 2. Identificar principais drivers de gasto
            try:
                driver_insights = await self._identify_drivers(expense_transactions, total_expense)
                insights.extend(driver_insights)
            except Exception as e:
                print(f"Error identifying drivers: {e}")

            # 3. Oportunidades de reducao
            try:
                opportunity_insights = await self._find_opportunities(expense_transactions)
                insights.extend(opportunity_insights)
            except Exception as e:
                print(f"Error finding opportunities: {e}")

            # 4. Analise de cartoes de credito
            try:
                credit_card_insights = await self._analyze_credit_cards(user)
                insights.extend(credit_card_insights)
            except Exception as e:
                print(f"Error analyzing credit cards: {e}")

            # 5. Analise de orcamento
            try:
                budget_insights = await self._analyze_budget(user, start_date, end_date)
                insights.extend(budget_insights)
            except Exception as e:
                print(f"Error analyzing budget: {e}")

            return insights[:5]  # Top 5 insights
        except Exception as e:
            print(f"Fatal error in get_insights: {e}")
            import traceback

            traceback.print_exc()
            raise

    async def get_spending_by_payment_method(
        self, user: User, start_date: date, end_date: date
    ) -> PaymentMethodReport:
        """Retorna relatorio de gastos agrupados por metodo de pagamento"""
        from collections import defaultdict

        transactions = await self._get_transactions(user, start_date, end_date)

        # Filtrar apenas despesas
        expense_transactions = [t for t in transactions if t.type == TransactionType.EXPENSE]

        # Excluir pagamentos de fatura
        try:
            payment_transaction_ids = await self._get_invoice_payment_transaction_ids(user)
        except Exception:
            payment_transaction_ids = set()

        expense_transactions = [
            t for t in expense_transactions if t.id not in payment_transaction_ids
        ]

        total_expenses = float(sum(t.amount for t in expense_transactions) or 0)

        # Agrupar por payment_method
        by_payment_method: dict[str | None, list[Transaction]] = defaultdict(list)
        for t in expense_transactions:
            by_payment_method[t.payment_method].append(t)

        summaries = []
        for payment_method, txs in by_payment_method.items():
            method_total = float(sum(t.amount for t in txs))

            # Obter nome amigavel do metodo de pagamento
            display_name = self._get_payment_method_display(payment_method)

            summaries.append(
                PaymentMethodSummary(
                    payment_method=payment_method,
                    payment_method_display=display_name,
                    total=method_total,
                    count=len(txs),
                    percentage=(method_total / total_expenses * 100) if total_expenses > 0 else 0,
                    average=method_total / len(txs) if txs else 0,
                )
            )

        # Ordenar por total (maior primeiro)
        summaries.sort(key=lambda x: x.total, reverse=True)

        return PaymentMethodReport(
            period_start=start_date,
            period_end=end_date,
            total_expenses=total_expenses,
            by_payment_method=summaries,
        )

    def _get_payment_method_display(self, payment_method: str | None) -> str:
        """Retorna nome amigavel do metodo de pagamento"""
        if not payment_method:
            return "Nao especificado"

        display_names = {
            PaymentMethod.CREDIT_CARD.value: "Cartao de Credito",
            PaymentMethod.DEBIT_CARD.value: "Cartao de Debito",
            PaymentMethod.PIX.value: "PIX",
            PaymentMethod.BANK_TRANSFER.value: "Transferencia Bancaria",
            PaymentMethod.BOLETO.value: "Boleto",
            PaymentMethod.CASH.value: "Dinheiro",
            PaymentMethod.VOUCHER.value: "Vale Alimentacao/Refeicao",
        }
        return display_names.get(payment_method, payment_method)

    async def _get_transactions(
        self, user: User, start_date: date, end_date: date
    ) -> list[Transaction]:
        # Get household member IDs if user is part of a household
        household_user_ids = await self._get_household_user_ids(user)

        if household_user_ids:
            # User is in a household - get personal + household transactions
            result = await self.db.execute(
                select(Transaction).where(
                    Transaction.date >= start_date,
                    Transaction.date <= end_date,
                    or_(
                        # Personal transactions from user
                        and_(
                            Transaction.user_id == user.id, Transaction.ownership_type == "personal"
                        ),
                        # Household transactions from any family member
                        and_(
                            Transaction.user_id.in_(household_user_ids),
                            Transaction.ownership_type == "household",
                        ),
                    ),
                )
            )
        else:
            # User is not in a household - get only their transactions
            result = await self.db.execute(
                select(Transaction).where(
                    Transaction.user_id == user.id,
                    Transaction.date >= start_date,
                    Transaction.date <= end_date,
                )
            )
        return list(result.scalars().all())

    async def _get_household_user_ids(self, user: User) -> list[int]:
        """Get all user IDs in the same household/license as the user"""
        if not user.license_id:
            return []

        result = await self.db.execute(
            select(HouseholdMember.user_id).where(HouseholdMember.license_id == user.license_id)
        )
        return list(result.scalars().all())

    async def _get_invoice_payment_transaction_ids(self, user: User) -> set[int]:
        """
        Retorna IDs de transacoes que sao pagamentos de fatura.
        Essas transacoes devem ser excluidas do calculo de despesas
        para evitar contagem dupla (contamos as compras, nao o pagamento).
        """
        try:
            household_user_ids = await self._get_household_user_ids(user)
            user_ids = [user.id] + household_user_ids if household_user_ids else [user.id]

            result = await self.db.execute(
                select(CreditCardInvoice.payment_transaction_id).where(
                    CreditCardInvoice.user_id.in_(user_ids),
                    CreditCardInvoice.payment_transaction_id.isnot(None),
                )
            )
            return set(result.scalars().all())
        except Exception:
            return set()

    async def _get_invoices_total_for_month(self, user: User, year: int, month: int) -> float:
        """
        Retorna o total de TODAS as faturas do mes de referencia.
        Isso representa o valor total que sera/foi pago no mes, independente do status.
        """
        try:
            household_user_ids = await self._get_household_user_ids(user)
            user_ids = [user.id] + household_user_ids if household_user_ids else [user.id]

            result = await self.db.execute(
                select(CreditCardInvoice).where(
                    CreditCardInvoice.user_id.in_(user_ids),
                    CreditCardInvoice.reference_year == year,
                    CreditCardInvoice.reference_month == month,
                )
            )
            invoices = result.scalars().all()

            return float(sum(inv.total_amount or 0 for inv in invoices))
        except Exception:
            return 0.0

    async def _get_pending_invoices_total(self, user: User, year: int, month: int) -> float:
        """
        Retorna o total de faturas nao pagas para o mes.
        Considera faturas com status OPEN, CLOSED ou OVERDUE.
        """
        try:
            household_user_ids = await self._get_household_user_ids(user)
            user_ids = [user.id] + household_user_ids if household_user_ids else [user.id]

            # Buscar faturas nao pagas do mes
            result = await self.db.execute(
                select(CreditCardInvoice).where(
                    CreditCardInvoice.user_id.in_(user_ids),
                    CreditCardInvoice.reference_year == year,
                    CreditCardInvoice.reference_month == month,
                    CreditCardInvoice.status.in_(
                        [
                            InvoiceStatus.OPEN.value,
                            InvoiceStatus.CLOSED.value,
                            InvoiceStatus.OVERDUE.value,
                        ]
                    ),
                )
            )
            invoices = result.scalars().all()

            # Somar total das faturas menos o que ja foi pago parcialmente
            total = sum(
                float(inv.total_amount or 0) - float(inv.paid_amount or 0) for inv in invoices
            )
            return total
        except Exception:
            return 0.0

    async def _group_by_category(
        self, transactions: list[Transaction], exclude_ids: set[int] | None = None
    ) -> list[CategorySummary]:
        from collections import defaultdict

        exclude_ids = exclude_ids or set()

        by_category: dict[int, list[Transaction]] = defaultdict(list)
        for t in transactions:
            if t.type == TransactionType.EXPENSE and t.category_id and t.id not in exclude_ids:
                by_category[t.category_id].append(t)

        total = sum(
            t.amount
            for t in transactions
            if t.type == TransactionType.EXPENSE and t.id not in exclude_ids
        )

        # Buscar nomes de todas as categorias de uma vez
        category_ids = list(by_category.keys())
        category_names = {}
        if category_ids:
            result = await self.db.execute(
                select(Category.id, Category.name).where(Category.id.in_(category_ids))
            )
            category_names = {row[0]: row[1] for row in result.all()}

        summaries = []
        for category_id, txs in by_category.items():
            cat_total = sum(t.amount for t in txs)
            name = category_names.get(category_id, "Sem categoria")

            summaries.append(
                CategorySummary(
                    category_id=category_id,
                    category_name=name,
                    total=cat_total,
                    count=len(txs),
                    percentage=(cat_total / total * 100) if total > 0 else 0,
                    average=cat_total / len(txs) if txs else 0,
                )
            )

        return sorted(summaries, key=lambda x: x.total, reverse=True)

    async def _group_by_merchant(
        self, transactions: list[Transaction], exclude_ids: set[int] | None = None
    ) -> list[MerchantSummary]:
        from collections import defaultdict

        exclude_ids = exclude_ids or set()

        by_merchant: dict[int | None, list[Transaction]] = defaultdict(list)
        for t in transactions:
            if t.type == TransactionType.EXPENSE and t.id not in exclude_ids:
                by_merchant[t.merchant_id].append(t)

        # Buscar nomes de todos os merchants de uma vez
        merchant_ids = [mid for mid in by_merchant.keys() if mid is not None]
        merchant_names = {}
        if merchant_ids:
            result = await self.db.execute(
                select(Merchant.id, Merchant.name).where(Merchant.id.in_(merchant_ids))
            )
            merchant_names = {row[0]: row[1] for row in result.all()}

        summaries = []
        for merchant_id, txs in by_merchant.items():
            if merchant_id:
                name = merchant_names.get(merchant_id, "Desconhecido")
            else:
                name = "Outros"

            summaries.append(
                MerchantSummary(
                    merchant_id=merchant_id,
                    merchant_name=name,
                    total=sum(t.amount for t in txs),
                    count=len(txs),
                )
            )

        return sorted(summaries, key=lambda x: x.total, reverse=True)

    async def _detect_leaks(
        self, transactions: list[Transaction], total: float
    ) -> list[InsightResponse]:
        """Detecta gastos pequenos frequentes que somam valores altos"""
        from collections import defaultdict

        insights = []

        # Agrupar por merchant
        by_merchant: dict[int, list[Transaction]] = defaultdict(list)
        for t in transactions:
            if t.merchant_id and float(t.amount) < 50:  # Gastos pequenos
                by_merchant[t.merchant_id].append(t)

        # Filtrar merchants que atendem os criterios
        leak_candidates = {}
        for merchant_id, txs in by_merchant.items():
            if len(txs) >= 3:  # Pelo menos 3 ocorrencias
                leak_total = float(sum(t.amount for t in txs) or 0)
                if leak_total >= total * 0.05:  # Representa pelo menos 5% do total
                    leak_candidates[merchant_id] = (txs, leak_total)

        if not leak_candidates:
            return insights

        # Buscar nomes de todos os merchants de uma vez
        merchant_ids = list(leak_candidates.keys())
        merchant_names = {}
        if merchant_ids:  # Proteger contra lista vazia
            result = await self.db.execute(
                select(Merchant.id, Merchant.name).where(Merchant.id.in_(merchant_ids))
            )
            merchant_names = {row[0]: row[1] for row in result.all()}

        for merchant_id, (txs, leak_total) in leak_candidates.items():
            name = merchant_names.get(merchant_id, "Estabelecimento")
            avg_value = leak_total / len(txs) if len(txs) > 0 else 0
            insights.append(
                InsightResponse(
                    type="leak",
                    title=f"Vazamento: {name}",
                    description=f"{len(txs)} gastos pequenos em {name} somaram R$ {leak_total:.2f}",
                    impact_value=float(leak_total),
                    calculation=f"{len(txs)} transacoes x media de R$ {avg_value:.2f}",
                    action=f"Reduza visitas a {name} pela metade para economizar R$ {leak_total / 2:.2f}/mes",
                    merchant_id=merchant_id,
                )
            )

        return insights

    async def _identify_drivers(
        self, transactions: list[Transaction], total: float
    ) -> list[InsightResponse]:
        """Identifica principais categorias de gasto"""
        insights = []
        categories = await self._group_by_category(transactions)

        for cat in categories[:2]:  # Top 2 categorias
            if cat.percentage >= 20:
                insights.append(
                    InsightResponse(
                        type="driver",
                        title=f"Principal gasto: {cat.category_name}",
                        description=f"{cat.category_name} representa {cat.percentage:.1f}% dos seus gastos",
                        impact_value=float(cat.total),
                        calculation=f"R$ {float(cat.total):.2f} de R$ {total:.2f} total",
                        action=f"Defina um teto de R$ {float(cat.total) * 0.8:.2f} para {cat.category_name}",
                        category_id=cat.category_id,
                    )
                )

        return insights

    async def _find_opportunities(self, transactions: list[Transaction]) -> list[InsightResponse]:
        """Encontra oportunidades de economia"""
        insights = []

        # Verificar assinaturas/recorrencias
        recurring = [t for t in transactions if t.is_recurring or t.is_fixed]
        recurring_total = float(sum(t.amount for t in recurring) or 0)

        if recurring_total > 0:
            insights.append(
                InsightResponse(
                    type="opportunity",
                    title="Revise gastos fixos",
                    description=f"Voce tem R$ {recurring_total:.2f} em gastos fixos/recorrentes",
                    impact_value=float(recurring_total * 0.1),
                    calculation=f"Reducao de 10% em R$ {recurring_total:.2f}",
                    action="Revise assinaturas e contratos para possivel renegociacao",
                )
            )

        return insights

    async def _analyze_credit_cards(self, user: User) -> list[InsightResponse]:
        """Analisa cartoes de credito e gera insights sobre limites, juros e oportunidades"""
        insights = []

        try:
            # Buscar cartoes ativos do usuario
            household_user_ids = await self._get_household_user_ids(user)
            user_ids = [user.id] + household_user_ids if household_user_ids else [user.id]

            cards_result = await self.db.execute(
                select(CreditCard).where(
                    CreditCard.user_id.in_(user_ids), CreditCard.is_active == True
                )
            )
            cards = cards_result.scalars().all()

            if not cards:
                return insights

            # Analisar cada cartao
            cards_with_balance = []
            total_outstanding = 0.0

            for card in cards:
                # Buscar conta vinculada para pegar o nome do cartao
                account_result = await self.db.execute(
                    select(Account).where(Account.id == card.account_id)
                )
                account = account_result.scalar_one_or_none()
                card_name = account.name if account else "Cartao"

                # Calcular saldo em aberto (faturas nao pagas)
                invoices_result = await self.db.execute(
                    select(CreditCardInvoice).where(
                        CreditCardInvoice.credit_card_id == card.id,
                        CreditCardInvoice.status.in_(["open", "closed", "partial", "overdue"]),
                    )
                )
                invoices = invoices_result.scalars().all()

                outstanding_balance = float(
                    sum(inv.total_amount - inv.paid_amount for inv in invoices) or 0
                )

                if outstanding_balance > 0:
                    cards_with_balance.append(
                        {
                            "card": card,
                            "name": card_name,
                            "balance": outstanding_balance,
                            "invoices": invoices,
                        }
                    )
                    total_outstanding += outstanding_balance

                # 1. Alerta de limite de credito (>70% utilizado)
                if card.credit_limit and card.credit_limit > 0:
                    utilization = (outstanding_balance / float(card.credit_limit)) * 100

                    if utilization >= 70:
                        # Calcular quanto precisa pagar para voltar a 50%
                        target_balance = float(card.credit_limit) * 0.5
                        amount_to_pay = outstanding_balance - target_balance

                        insights.append(
                            InsightResponse(
                                type="credit_alert",
                                title=f"⚠️ Alerta: {card_name}",
                                description=f"Cartao com {utilization:.1f}% do limite utilizado (R$ {outstanding_balance:,.2f} de R$ {float(card.credit_limit):,.2f})",
                                impact_value=amount_to_pay,
                                calculation=f"Utilizacao: {utilization:.1f}% (ideal: <50%)",
                                action=f"Pague R$ {amount_to_pay:,.2f} para reduzir utilizacao para 50% e proteger seu score de credito",
                                credit_card_id=card.id,
                            )
                        )

            # 2. Aviso de juros projetados para cartoes com saldo
            if cards_with_balance:
                # Estimar juros mensais (assumindo taxa media de 12% a.m.)
                avg_interest_rate = 0.12
                monthly_interest = total_outstanding * avg_interest_rate

                if monthly_interest > 50:  # Apenas se juros forem significativos
                    insights.append(
                        InsightResponse(
                            type="interest_warning",
                            title="💰 Atenção aos Juros",
                            description=f"Voce tem R$ {total_outstanding:,.2f} em saldo devedor em {len(cards_with_balance)} cartao(oes)",
                            impact_value=float(monthly_interest),
                            calculation=f"Juros estimados: R$ {monthly_interest:,.2f}/mes (taxa media: {avg_interest_rate * 100}% a.m.)",
                            action="Priorize quitar os cartoes com maiores saldos. Se tiver R$ 10.000 disponiveis, use para abater e economizar juros",
                        )
                    )

            # 3. Oportunidade de consolidacao (se tiver 2+ cartoes com saldo)
            if len(cards_with_balance) >= 2:
                # Ordenar por maior saldo
                cards_with_balance.sort(key=lambda x: x["balance"], reverse=True)
                top_2 = cards_with_balance[:2]
                top_2_total = sum(c["balance"] for c in top_2)

                insights.append(
                    InsightResponse(
                        type="consolidation",
                        title="🔄 Oportunidade de Consolidacao",
                        description=f"Seus 2 maiores saldos: {top_2[0]['name']} (R$ {top_2[0]['balance']:,.2f}) e {top_2[1]['name']} (R$ {top_2[1]['balance']:,.2f})",
                        impact_value=float(top_2_total),
                        calculation=f"Total consolidavel: R$ {top_2_total:,.2f}",
                        action="Priorize pagar estes cartoes primeiro para reduzir juros e simplificar suas financas",
                    )
                )

        except Exception as e:
            print(f"Error in _analyze_credit_cards: {e}")
            import traceback

            traceback.print_exc()

        return insights

    async def _analyze_budget(
        self, user: User, start_date: date, end_date: date
    ) -> list[InsightResponse]:
        """
        Gera insights relacionados ao orcamento.

        Analisa:
        - Categorias excedidas
        - Categorias proximas do limite
        - Oportunidades de rebalanceamento
        """
        from app.modules.budgets.services.budget_service import BudgetService

        insights = []
        year = start_date.year
        month = start_date.month

        try:
            budget_service = BudgetService(self.db)
            budget = await budget_service.get_budget(user, year, month)

            if not budget or not budget.items:
                return insights

            # Categorias excedidas (overspent)
            overspent_items = [
                item for item in budget.items if item.status == BudgetItemStatus.OVERSPENT.value
            ]

            if overspent_items:
                total_overspent = sum(abs(item.available_amount) for item in overspent_items)
                category_names = ", ".join(item.category_name for item in overspent_items[:3])
                insights.append(
                    InsightResponse(
                        type="budget_alert",
                        title="⚠️ Orcamento Excedido",
                        description=f"{len(overspent_items)} categoria(s) excedeu o limite: {category_names}",
                        impact_value=float(total_overspent),
                        calculation=f"Total excedido: R$ {total_overspent:,.2f}",
                        action="Considere transferir de categorias com sobra ou ajustar o planejamento",
                    )
                )

            # Categorias em alerta (warning - acima de 80%)
            warning_items = [
                item for item in budget.items if item.status == BudgetItemStatus.WARNING.value
            ]

            if warning_items and not overspent_items:  # Nao duplicar alertas
                category_names = ", ".join(
                    f"{item.category_name} ({item.percentage_used:.0f}%)"
                    for item in warning_items[:3]
                )
                insights.append(
                    InsightResponse(
                        type="budget_warning",
                        title="📊 Categorias Proximas do Limite",
                        description=f"{len(warning_items)} categoria(s) acima de 80%: {category_names}",
                        impact_value=float(sum(item.available_amount for item in warning_items)),
                        calculation=f"Saldo restante: R$ {sum(item.available_amount for item in warning_items):,.2f}",
                        action="Monitore seus gastos nestas categorias para nao exceder o limite",
                    )
                )

            # Oportunidade de rebalanceamento (categorias com muita sobra)
            on_track_items = [
                item
                for item in budget.items
                if item.status == BudgetItemStatus.ON_TRACK.value
                and item.percentage_used < 50
                and item.days_remaining <= 10
                and item.available_amount > 100  # Pelo menos R$ 100 sobrando
            ]

            if on_track_items and overspent_items:
                total_available = sum(item.available_amount for item in on_track_items)
                category_names = ", ".join(item.category_name for item in on_track_items[:3])
                insights.append(
                    InsightResponse(
                        type="budget_opportunity",
                        title="💡 Oportunidade de Rebalanceamento",
                        description=f"Categorias com sobra: {category_names}",
                        impact_value=float(total_available),
                        calculation=f"Total disponivel para transferencia: R$ {total_available:,.2f}",
                        action="Use a funcao 'Transferir' no Orcamento para mover verba entre categorias",
                    )
                )

        except Exception as e:
            print(f"Error in _analyze_budget: {e}")
            import traceback

            traceback.print_exc()

        return insights
