"""Servico para gerenciamento de faturas de cartao de credito"""

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utc_now
from app.models.account import Account
from app.models.category import Category
from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import CreditCardInvoice, InvoiceStatus
from app.models.document import Document
from app.models.recurring import RecurringTransaction
from app.models.transaction import PaymentMethod, Transaction, TransactionType
from app.models.user import User


class InvoiceService:
    """Gerencia faturas de cartao de credito"""

    def __init__(self, db: AsyncSession):
        self.db = db

    def calculate_invoice_period(self, credit_card: CreditCard, reference_date: date) -> dict:
        """
        Calcula o periodo da fatura baseado no closing_day do cartao.

        Para um cartao com fechamento no dia 15:
        - Compra em 10/01: fatura de Jan (fecha 15/01, vence ~25/01)
        - Compra em 20/01: fatura de Fev (fecha 15/02, vence ~25/02)

        Retorna:
        - reference_month: Mes de referencia da fatura
        - reference_year: Ano de referencia
        - closing_date: Data de fechamento
        - due_date: Data de vencimento
        """
        closing_day = credit_card.closing_day

        # Se a compra foi apos o fechamento, vai para a proxima fatura
        if reference_date.day > closing_day:
            # Fatura do proximo mes
            next_month = reference_date + relativedelta(months=1)
            ref_month = next_month.month
            ref_year = next_month.year
        else:
            # Fatura do mes atual
            ref_month = reference_date.month
            ref_year = reference_date.year

        # Usar metodo auxiliar para calcular datas
        dates = self.calculate_invoice_dates(credit_card, ref_month, ref_year)

        return {
            "reference_month": ref_month,
            "reference_year": ref_year,
            "closing_date": dates["closing_date"],
            "due_date": dates["due_date"],
        }

    def calculate_invoice_dates(
        self,
        credit_card: CreditCard,
        reference_month: int,
        reference_year: int,
    ) -> dict:
        """
        Calcula as datas de fechamento e vencimento para um mes/ano especifico.

        Usado quando o mes/ano da fatura e fornecido explicitamente (ex: de um PDF).

        Retorna:
        - closing_date: Data de fechamento
        - due_date: Data de vencimento
        """
        closing_day = credit_card.closing_day
        due_day = credit_card.due_day

        # Calcular data de fechamento (no mes de referencia)
        try:
            closing_date = date(reference_year, reference_month, min(closing_day, 28))
        except ValueError:
            # Em caso de dia invalido, usar ultimo dia do mes
            closing_date = date(reference_year, reference_month, 28)

        # Calcular data de vencimento
        # Se due_day < closing_day, vencimento e no mes seguinte
        if due_day < closing_day:
            due_date_month = closing_date + relativedelta(months=1)
            try:
                due_date = date(due_date_month.year, due_date_month.month, min(due_day, 28))
            except ValueError:
                due_date = date(due_date_month.year, due_date_month.month, 28)
        else:
            try:
                due_date = date(reference_year, reference_month, min(due_day, 28))
            except ValueError:
                due_date = date(reference_year, reference_month, 28)

        return {
            "closing_date": closing_date,
            "due_date": due_date,
        }

    async def get_or_create_invoice(
        self,
        user: User,
        credit_card: CreditCard,
        reference_month: int,
        reference_year: int,
        closing_date: date | None = None,
        due_date: date | None = None,
    ) -> CreditCardInvoice:
        """Obtem ou cria uma fatura para o periodo especificado"""
        # Buscar fatura existente
        result = await self.db.execute(
            select(CreditCardInvoice).where(
                and_(
                    CreditCardInvoice.user_id == user.id,
                    CreditCardInvoice.credit_card_id == credit_card.id,
                    CreditCardInvoice.reference_month == reference_month,
                    CreditCardInvoice.reference_year == reference_year,
                )
            )
        )
        invoice = result.scalar_one_or_none()

        if invoice:
            return invoice

        # Se nao forneceu datas, calcular baseado em uma data de referencia
        if not closing_date or not due_date:
            ref_date = date(reference_year, reference_month, 1)
            period = self.calculate_invoice_period(credit_card, ref_date)
            closing_date = period["closing_date"]
            due_date = period["due_date"]

        # Criar nova fatura
        invoice = CreditCardInvoice(
            user_id=user.id,
            credit_card_id=credit_card.id,
            reference_month=reference_month,
            reference_year=reference_year,
            closing_date=closing_date,
            due_date=due_date,
            total_amount=Decimal("0"),
            paid_amount=Decimal("0"),
            status=InvoiceStatus.OPEN.value,
        )

        self.db.add(invoice)
        await self.db.flush()
        await self.db.refresh(invoice)

        return invoice

    # Padroes de descricao que indicam pagamento de fatura (NAO devem ser somados no total)
    PAYMENT_DESCRIPTION_PATTERNS = [
        "pagamento em ",  # Nubank: "Pagamento em 08 DEZ"
        "pagamento de fatura",
        "pagamento banco",  # "Pagamento Banco CSP", "Pagamento Banco do Brasil"
        "pag fatura",
        "pgto fatura",
        "pgto cobranca",
        "pagamento efetuado",
        "pgto debito automatico",
        "pagamento recebido",
        "credito pagamento",
        "pagto boleto",  # PAN: "Pagto Boleto Recebido"
        "pagamento boleto",
    ]

    async def update_invoice_total(
        self, invoice: CreditCardInvoice, force_recalculate: bool = False
    ) -> None:
        """
        Recalcula o total da fatura baseado nas transacoes vinculadas.

        Calcula: Total = Despesas - Creditos (excluindo pagamentos de fatura)

        - Soma transacoes de DESPESA (type='expense') com valor positivo
        - Subtrai transacoes de CREDITO (type='income') que NAO sao pagamentos de fatura
        - Pagamentos de fatura sao detectados pela descricao e ignorados

        Creditos (type='income' que nao sao pagamentos) representam:
        - Estornos de compras
        - Reembolsos
        - Creditos promocionais

        Args:
            invoice: Fatura a ser recalculada
            force_recalculate: Se True, recalcula mesmo faturas de PDF

        NOTA: Nao recalcula faturas:
        - Já pagas (status='paid') - valor histórico preservado
        - Criadas de PDF (document_id) - a menos que force_recalculate=True
        """
        # Se a fatura ja foi paga, nao recalcular o total
        # O valor historico deve ser preservado
        if invoice.status == InvoiceStatus.PAID.value:
            return

        # Se a fatura veio de PDF e nao esta forcando recalculo, preservar total do PDF
        if invoice.document_id and invoice.total_amount > 0 and not force_recalculate:
            return

        # Buscar todas as transacoes da fatura
        result = await self.db.execute(
            select(Transaction).where(
                and_(Transaction.invoice_id == invoice.id, Transaction.amount > 0)
            )
        )
        transactions = result.scalars().all()

        total_expenses = Decimal("0")
        total_credits = Decimal("0")

        for tx in transactions:
            desc_lower = (tx.description or "").lower()
            is_payment = any(pattern in desc_lower for pattern in self.PAYMENT_DESCRIPTION_PATTERNS)

            if tx.type == "expense":
                # Ignorar pagamentos de fatura salvos incorretamente como expense
                if is_payment:
                    continue
                total_expenses += Decimal(str(tx.amount))

            elif tx.type == "income":
                # Ignorar pagamentos de fatura (esses nao devem afetar o total)
                if is_payment:
                    continue
                # Creditos/estornos reduzem o total da fatura
                total_credits += Decimal(str(tx.amount))

        invoice.total_amount = total_expenses - total_credits
        await self.db.flush()

    async def link_transaction_to_invoice(
        self,
        transaction: Transaction,
        invoice: CreditCardInvoice | None = None,
        credit_card: CreditCard | None = None,
    ) -> CreditCardInvoice:
        """
        Vincula uma transacao a fatura apropriada.

        Se invoice nao for fornecida, calcula a fatura baseada na data da transacao
        e no cartao de credito.
        """
        if not invoice:
            if not credit_card:
                raise ValueError("Deve fornecer invoice ou credit_card")

            # Obter usuario
            result = await self.db.execute(select(User).where(User.id == transaction.user_id))
            user = result.scalar_one()

            # Calcular periodo
            period = self.calculate_invoice_period(credit_card, transaction.date)

            # Obter ou criar fatura
            invoice = await self.get_or_create_invoice(
                user=user,
                credit_card=credit_card,
                reference_month=period["reference_month"],
                reference_year=period["reference_year"],
                closing_date=period["closing_date"],
                due_date=period["due_date"],
            )

        # Vincular transacao
        transaction.invoice_id = invoice.id

        # Atualizar total
        await self.update_invoice_total(invoice)

        return invoice

    async def get_or_create_payment_category(self, user_id: int) -> Category:
        """Obtem ou cria a categoria 'Cartao de Credito' para pagamentos"""
        result = await self.db.execute(
            select(Category).where(
                and_(
                    Category.user_id == user_id,
                    Category.name == "Pagamento de Fatura",
                )
            )
        )
        category = result.scalar_one_or_none()

        if not category:
            category = Category(
                user_id=user_id,
                name="Pagamento de Fatura",
                type="expense",
                icon="credit-card",
            )
            self.db.add(category)
            await self.db.flush()

        return category

    async def pay_invoice(
        self,
        user: User,
        invoice: CreditCardInvoice,
        amount: Decimal,
        payment_account_id: int,
        payment_date: date | None = None,
        payment_method: str | None = None,
    ) -> Transaction:
        """
        Registra o pagamento de uma fatura.

        1. Valida que a conta de pagamento nao e cartao de credito
        2. Cria transacao de saida na conta de pagamento
        3. Atualiza status da fatura

        Args:
            payment_method: Metodo de pagamento (pix, bank_transfer, debit_card, boleto).
                           Se nao fornecido, usa 'bank_transfer' como default.
        """
        # Validar conta de pagamento
        result = await self.db.execute(
            select(Account).where(
                and_(
                    Account.id == payment_account_id,
                    Account.user_id == user.id,
                )
            )
        )
        payment_account = result.scalar_one_or_none()

        if not payment_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta de pagamento nao encontrada",
            )

        if payment_account.type == "credit_card":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nao e possivel pagar fatura com outro cartao de credito",
            )

        # Obter categoria de pagamento
        category = await self.get_or_create_payment_category(user.id)

        # Obter cartao para descricao
        result = await self.db.execute(
            select(CreditCard).where(CreditCard.id == invoice.credit_card_id)
        )
        credit_card = result.scalar_one()

        result = await self.db.execute(select(Account).where(Account.id == credit_card.account_id))
        card_account = result.scalar_one()

        # Determinar metodo de pagamento (default: bank_transfer)
        actual_payment_method = payment_method or PaymentMethod.BANK_TRANSFER.value

        # Criar transacao de pagamento
        payment_transaction = Transaction(
            user_id=user.id,
            account_id=payment_account_id,
            category_id=category.id,
            type=TransactionType.EXPENSE.value,
            payment_method=actual_payment_method,
            amount=amount,
            date=payment_date or date.today(),
            description=f"Pagamento Fatura {card_account.name} - {invoice.period_display}",
            is_fixed=True,
        )

        self.db.add(payment_transaction)
        await self.db.flush()
        await self.db.refresh(payment_transaction)

        # Atualizar fatura
        invoice.paid_amount = (invoice.paid_amount or Decimal("0")) + amount
        invoice.paid_at = utc_now()
        invoice.payment_account_id = payment_account_id
        invoice.payment_transaction_id = payment_transaction.id

        # Adicionar a lista de transacoes de pagamento (para multiplos pagamentos parciais)
        if invoice.payment_transaction_ids is None:
            invoice.payment_transaction_ids = []
        invoice.payment_transaction_ids = invoice.payment_transaction_ids + [payment_transaction.id]

        # Atualizar status
        if invoice.paid_amount >= invoice.total_amount:
            invoice.status = InvoiceStatus.PAID.value
        elif invoice.paid_amount > 0:
            invoice.status = InvoiceStatus.PARTIAL.value

        await self.db.flush()

        return payment_transaction

    async def detect_card_from_document(
        self,
        user: User,
        document_data: dict,
    ) -> list[CreditCard]:
        """
        Detecta possiveis cartoes baseado nos dados extraidos do documento.

        Busca por:
        - card_issuer: nome do banco (itau, nubank, etc)
        - card_last_digits: ultimos 4 digitos
        - card_name: nome do cartao extraido do PDF

        Retorna lista de cartoes que podem corresponder.
        """
        card_issuer = document_data.get("card_issuer", "").lower().strip()
        card_last_digits = document_data.get("card_last_digits", "").strip()
        card_name = document_data.get("card_name", "").lower().strip()
        card_bank = document_data.get("card_bank", "").lower().strip()
        card_brand = document_data.get("card_brand", "").lower().strip()
        card_partner = document_data.get("card_partner", "").lower().strip()

        # Buscar cartoes do usuario
        result = await self.db.execute(
            select(CreditCard).where(
                and_(
                    CreditCard.user_id == user.id,
                    CreditCard.is_active == True,
                )
            )
        )
        cards = list(result.scalars().all())

        if not cards:
            return []

        # Buscar todas as contas de uma vez
        account_ids = [card.account_id for card in cards]
        acc_result = await self.db.execute(select(Account).where(Account.id.in_(account_ids)))
        accounts_by_id = {acc.id: acc for acc in acc_result.scalars().all()}

        matches = []

        for card in cards:
            account = accounts_by_id.get(card.account_id)
            if not account:
                continue

            score = 0
            account_name_lower = self._normalize_string(account.name)

            # Match por ultimos 4 digitos (alta prioridade)
            if card_last_digits and card.last_four_digits:
                if card.last_four_digits == card_last_digits:
                    score += 100

            # Match por nome do cartao extraido do PDF
            if card_name:
                if self._fuzzy_match(account_name_lower, card_name):
                    score += 50

            # Match por parceiro co-branded (amazon, smiles) - alta prioridade
            if card_partner:
                partner_normalized = self._normalize_string(card_partner)
                if partner_normalized in account_name_lower:
                    score += 40

            # Match por nome do banco
            if card_bank:
                bank_normalized = self._normalize_string(card_bank)
                if self._fuzzy_match(account_name_lower, bank_normalized):
                    score += 25

            # Match por emissor no nome da conta
            if card_issuer:
                issuer_normalized = self._normalize_string(card_issuer)
                issuer_variants = self._get_issuer_variants(issuer_normalized)

                # Verificar variantes no nome da conta
                for variant in issuer_variants:
                    if variant in account_name_lower or account_name_lower in variant:
                        score += 30
                        break

                # Verificar match fuzzy com o issuer completo
                if score < 55 and self._fuzzy_match(account_name_lower, issuer_normalized):
                    score += 30

            # Match por bandeira (visa, mastercard) - prioridade baixa
            if card_brand:
                brand_normalized = self._normalize_string(card_brand)
                if brand_normalized in account_name_lower:
                    score += 10

            if score > 0:
                matches.append((score, card))

        # Ordenar por score decrescente
        matches.sort(key=lambda x: x[0], reverse=True)

        return [card for score, card in matches]

    def _normalize_string(self, s: str) -> str:
        """Normaliza string para comparação: remove acentos, underscores, etc."""
        import unicodedata

        # Remove acentos
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        # Lowercase e substitui separadores por espaço
        s = s.lower().replace("_", " ").replace("-", " ").strip()
        return s

    def _fuzzy_match(self, str1: str, str2: str) -> bool:
        """Verifica se duas strings fazem match (fuzzy)."""
        s1 = self._normalize_string(str1)
        s2 = self._normalize_string(str2)

        # Direct includes check both directions
        if s1 in s2 or s2 in s1:
            return True

        # Word-by-word matching: check if any significant word matches
        words1 = [w for w in s1.split() if len(w) > 2]
        words2 = [w for w in s2.split() if len(w) > 2]

        for w1 in words1:
            for w2 in words2:
                if w1 in w2 or w2 in w1:
                    return True

        return False

    def _get_issuer_variants(self, issuer: str) -> list[str]:
        """Retorna variantes do nome do emissor para matching"""
        variants_map = {
            "itau": ["itau", "itaucard"],
            "nubank": ["nubank", "nu"],
            "inter": ["inter", "banco inter"],
            "santander": ["santander"],
            "bradesco": ["bradesco", "bradescard"],
            "bradescard": ["bradescard", "bradesco", "bradesco amazon", "amazon bradesco"],
            "bb": ["banco do brasil", "bb"],
            "caixa": ["caixa", "cef"],
            "c6": ["c6", "c6 bank"],
            "xp": ["xp"],
            "btg": ["btg"],
            "original": ["original"],
            "next": ["next"],
            "neon": ["neon"],
            "pagbank": ["pagbank", "pagseguro"],
            "picpay": ["picpay"],
            "mercadopago": ["mercado pago", "mercadopago"],
            "amazon": ["amazon", "bradesco amazon", "amazon bradesco"],
            "carrefour": ["carrefour"],
            "riachuelo": ["riachuelo"],
            "renner": ["renner"],
            "magalu": ["magalu", "magazine luiza"],
            "casas bahia": ["casas bahia"],
            "ponto": ["ponto", "ponto frio"],
            "marisa": ["marisa"],
            "digio": ["digio"],
        }

        # Buscar variantes conhecidas
        for key, variants in variants_map.items():
            if issuer in variants or key == issuer or key in issuer:
                return variants + [issuer]  # Inclui o issuer original também

        # Se nao encontrou, retornar o proprio issuer e suas palavras
        words = [w for w in issuer.split() if len(w) > 2]
        return [issuer] + words

    async def update_invoice_statuses(self) -> int:
        """
        Atualiza status de faturas baseado em datas.

        - OPEN -> CLOSED: se passou da closing_date
        - CLOSED -> OVERDUE: se passou da due_date e nao foi paga

        Retorna quantidade de faturas atualizadas.
        """
        today = date.today()
        updated_count = 0

        # Buscar faturas OPEN que passaram do fechamento
        result = await self.db.execute(
            select(CreditCardInvoice).where(
                and_(
                    CreditCardInvoice.status == InvoiceStatus.OPEN.value,
                    CreditCardInvoice.closing_date < today,
                )
            )
        )
        open_invoices = list(result.scalars().all())

        for invoice in open_invoices:
            invoice.status = InvoiceStatus.CLOSED.value
            updated_count += 1

        # Buscar faturas CLOSED/PARTIAL que passaram do vencimento
        result = await self.db.execute(
            select(CreditCardInvoice).where(
                and_(
                    CreditCardInvoice.status.in_(
                        [
                            InvoiceStatus.CLOSED.value,
                            InvoiceStatus.PARTIAL.value,
                        ]
                    ),
                    CreditCardInvoice.due_date < today,
                )
            )
        )
        closed_invoices = list(result.scalars().all())

        for invoice in closed_invoices:
            invoice.status = InvoiceStatus.OVERDUE.value
            updated_count += 1

        await self.db.flush()

        return updated_count

    async def get_invoice_by_id(
        self,
        user: User,
        invoice_id: int,
    ) -> CreditCardInvoice | None:
        """Obtem uma fatura por ID"""
        result = await self.db.execute(
            select(CreditCardInvoice).where(
                and_(
                    CreditCardInvoice.id == invoice_id,
                    CreditCardInvoice.user_id == user.id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_invoices(
        self,
        user: User,
        credit_card_id: int | None = None,
        status_filter: str | None = None,
        year: int | None = None,
        month: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CreditCardInvoice]:
        """Lista faturas do usuario com filtros"""
        query = select(CreditCardInvoice).where(CreditCardInvoice.user_id == user.id)

        if credit_card_id:
            query = query.where(CreditCardInvoice.credit_card_id == credit_card_id)

        if status_filter:
            query = query.where(CreditCardInvoice.status == status_filter)

        if year:
            query = query.where(CreditCardInvoice.reference_year == year)

        if month:
            query = query.where(CreditCardInvoice.reference_month == month)

        query = (
            query.order_by(
                CreditCardInvoice.reference_year.desc(),
                CreditCardInvoice.reference_month.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_invoice_transactions(
        self,
        invoice: CreditCardInvoice,
    ) -> list[Transaction]:
        """Obtem todas as transacoes de uma fatura"""
        result = await self.db.execute(
            select(Transaction)
            .where(Transaction.invoice_id == invoice.id)
            .order_by(Transaction.date.desc())
        )
        return list(result.scalars().all())

    async def get_card_current_invoice(
        self,
        user: User,
        credit_card: CreditCard,
    ) -> CreditCardInvoice | None:
        """Obtem a fatura atual (aberta) de um cartao"""
        today = date.today()
        period = self.calculate_invoice_period(credit_card, today)

        result = await self.db.execute(
            select(CreditCardInvoice).where(
                and_(
                    CreditCardInvoice.user_id == user.id,
                    CreditCardInvoice.credit_card_id == credit_card.id,
                    CreditCardInvoice.reference_month == period["reference_month"],
                    CreditCardInvoice.reference_year == period["reference_year"],
                )
            )
        )
        return result.scalar_one_or_none()

    async def delete_invoice(
        self,
        user: User,
        invoice_id: int,
        delete_transactions: bool = False,
    ) -> dict:
        """
        Exclui uma fatura.

        Se delete_transactions=True e houver transacoes parceladas, deleta toda
        a serie de parcelas (incluindo parcelas em outras faturas) e limpa
        faturas que ficarem vazias.

        Args:
            user: Usuario atual
            invoice_id: ID da fatura
            delete_transactions: Se True, deleta as transacoes vinculadas.
                                 Se False, apenas desvincula (invoice_id = None).

        Returns:
            Dict com informacoes sobre o que foi deletado
        """
        from app.models.installment import InstallmentSeries

        invoice = await self.get_invoice_by_id(user, invoice_id)

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fatura nao encontrada",
            )

        result = {
            "transactions_deleted": 0,
            "transactions_unlinked": 0,
            "invoices_deleted": 1,  # A fatura atual
            "series_deleted": 0,
        }

        # Buscar transacoes vinculadas
        tx_result = await self.db.execute(
            select(Transaction).where(Transaction.invoice_id == invoice_id)
        )
        transactions = list(tx_result.scalars().all())

        if delete_transactions:
            # Coletar series de parcelas para deletar
            series_ids_to_delete = set()
            for transaction in transactions:
                if transaction.installment_series_id:
                    series_ids_to_delete.add(transaction.installment_series_id)

            affected_invoice_ids = set()

            if series_ids_to_delete:
                # Buscar TODAS as transacoes de TODAS as series de uma vez
                series_result = await self.db.execute(
                    select(Transaction).where(
                        Transaction.installment_series_id.in_(series_ids_to_delete),
                        Transaction.user_id == user.id,
                    )
                )
                all_series_transactions = list(series_result.scalars().all())

                for tx in all_series_transactions:
                    if tx.invoice_id and tx.invoice_id != invoice_id:
                        affected_invoice_ids.add(tx.invoice_id)
                    await self.db.delete(tx)
                    result["transactions_deleted"] += 1

                # Deletar todas as series de uma vez
                series_obj = await self.db.execute(
                    select(InstallmentSeries).where(InstallmentSeries.id.in_(series_ids_to_delete))
                )
                for series in series_obj.scalars().all():
                    await self.db.delete(series)
                    result["series_deleted"] += 1

            # Deletar transacoes que nao sao de series
            for transaction in transactions:
                if not transaction.installment_series_id:
                    await self.db.delete(transaction)
                    result["transactions_deleted"] += 1

            await self.db.flush()

            # Verificar e limpar faturas que ficaram vazias (batch)
            if affected_invoice_ids:
                # Buscar todas as faturas afetadas de uma vez
                inv_result = await self.db.execute(
                    select(CreditCardInvoice).where(CreditCardInvoice.id.in_(affected_invoice_ids))
                )
                affected_invoices = {inv.id: inv for inv in inv_result.scalars().all()}

                # Contar transacoes restantes de todas as faturas de uma vez
                count_result = await self.db.execute(
                    select(Transaction.invoice_id, func.count(Transaction.id).label("count"))
                    .where(Transaction.invoice_id.in_(affected_invoice_ids))
                    .group_by(Transaction.invoice_id)
                )
                remaining_counts = {row[0]: row[1] for row in count_result.all()}

                for inv_id in affected_invoice_ids:
                    other_invoice = affected_invoices.get(inv_id)
                    if not other_invoice:
                        continue

                    remaining_count = remaining_counts.get(inv_id, 0)
                    if remaining_count == 0:
                        # Fatura vazia, deletar
                        await self.db.delete(other_invoice)
                        result["invoices_deleted"] += 1
                    else:
                        # Atualizar total da fatura
                        await self.update_invoice_total(other_invoice)

        else:
            # Apenas desvincular
            for transaction in transactions:
                transaction.invoice_id = None
                result["transactions_unlinked"] += 1

        # Excluir fatura atual
        await self.db.delete(invoice)
        await self.db.flush()

        return result

    async def create_invoice_from_document(
        self,
        user: User,
        document: Document,
        credit_card: CreditCard,
        reference_month: int,
        reference_year: int,
        total_amount: Decimal | None = None,
    ) -> CreditCardInvoice:
        """
        Cria uma fatura a partir de um documento PDF.

        O documento fica vinculado a fatura para referencia.
        """
        # Calcular datas
        ref_date = date(reference_year, reference_month, 1)
        period = self.calculate_invoice_period(credit_card, ref_date)

        # Verificar se ja existe fatura para o periodo
        existing = await self.db.execute(
            select(CreditCardInvoice).where(
                and_(
                    CreditCardInvoice.credit_card_id == credit_card.id,
                    CreditCardInvoice.reference_month == reference_month,
                    CreditCardInvoice.reference_year == reference_year,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ja existe uma fatura para {reference_month}/{reference_year}",
            )

        invoice = CreditCardInvoice(
            user_id=user.id,
            credit_card_id=credit_card.id,
            document_id=document.id,
            reference_month=reference_month,
            reference_year=reference_year,
            closing_date=period["closing_date"],
            due_date=period["due_date"],
            total_amount=total_amount or Decimal("0"),
            paid_amount=Decimal("0"),
            status=InvoiceStatus.OPEN.value,
        )

        self.db.add(invoice)
        await self.db.flush()
        await self.db.refresh(invoice)

        # Fecha o loop: dispensa notificacoes "fatura pendente" desta
        # (card, ref_month, ref_year) agora que o PDF foi anexado.
        # Import local para evitar circular entre credit_cards e notifications.
        try:
            from app.modules.notifications.services.notification_service import (
                NotificationService,
            )

            await NotificationService(self.db).resolve_pending_for_invoice(
                user_id=user.id,
                credit_card_id=credit_card.id,
                reference_month=reference_month,
                reference_year=reference_year,
            )
        except Exception:
            # Nao falhar a criacao da fatura se o resolve der erro.
            # O job de expiracao periodico compensa cenarios de falha aqui.
            pass

        return invoice

    async def project_recurring_to_invoices(
        self,
        user: User,
        credit_card: CreditCard,
        months_ahead: int = 6,
    ) -> list[Transaction]:
        """
        Projeta transacoes recorrentes para faturas futuras.

        Busca todas as transacoes recorrentes ativas que estao vinculadas
        a conta do cartao de credito e cria transacoes projetadas (is_paid=False)
        para os proximos N meses.

        Args:
            user: Usuario
            credit_card: Cartao de credito
            months_ahead: Numero de meses para projetar (default: 6)

        Returns:
            Lista de transacoes projetadas criadas
        """
        today = date.today()
        created_transactions = []

        # Buscar recorrentes ativas vinculadas a conta do cartao
        result = await self.db.execute(
            select(RecurringTransaction).where(
                and_(
                    RecurringTransaction.user_id == user.id,
                    RecurringTransaction.account_id == credit_card.account_id,
                    RecurringTransaction.status == "active",
                    RecurringTransaction.type == "expense",
                )
            )
        )
        recurring_list = list(result.scalars().all())

        if not recurring_list:
            return []

        # Para cada recorrente, projetar para os proximos meses
        for recurring in recurring_list:
            for month_offset in range(1, months_ahead + 1):
                # Calcular data da transacao
                projected_date = today + relativedelta(months=month_offset)

                # Ajustar para o dia do mes configurado
                if recurring.day_of_month:
                    try:
                        projected_date = date(
                            projected_date.year,
                            projected_date.month,
                            min(recurring.day_of_month, 28),
                        )
                    except ValueError:
                        projected_date = date(projected_date.year, projected_date.month, 28)

                # Verificar se ja existe transacao para esta data e recorrente
                existing_result = await self.db.execute(
                    select(Transaction).where(
                        and_(
                            Transaction.recurring_id == recurring.id,
                            Transaction.date >= projected_date - relativedelta(days=10),
                            Transaction.date <= projected_date + relativedelta(days=10),
                        )
                    )
                )
                if existing_result.scalar_one_or_none():
                    continue  # Ja existe, pular

                # Calcular periodo da fatura
                period = self.calculate_invoice_period(credit_card, projected_date)

                # Obter ou criar fatura
                invoice = await self.get_or_create_invoice(
                    user=user,
                    credit_card=credit_card,
                    reference_month=period["reference_month"],
                    reference_year=period["reference_year"],
                    closing_date=period["closing_date"],
                    due_date=period["due_date"],
                )

                # Criar transacao projetada
                transaction = Transaction(
                    user_id=user.id,
                    account_id=credit_card.account_id,
                    category_id=recurring.category_id,
                    credit_card_id=credit_card.id,
                    invoice_id=invoice.id,
                    recurring_id=recurring.id,
                    type=TransactionType.EXPENSE.value,
                    amount=recurring.amount,
                    date=projected_date,
                    description=f"{recurring.name} (projetado)",
                    is_paid=False,  # Transacao futura/projetada
                    is_fixed=True,
                    ownership_type=recurring.ownership_type,
                )

                self.db.add(transaction)
                created_transactions.append(transaction)

        await self.db.flush()

        # Atualizar totais das faturas (batch)
        invoice_ids = list(set(t.invoice_id for t in created_transactions if t.invoice_id))
        if invoice_ids:
            result = await self.db.execute(
                select(CreditCardInvoice).where(CreditCardInvoice.id.in_(invoice_ids))
            )
            for invoice in result.scalars().all():
                await self.update_invoice_total(invoice)

        return created_transactions

    async def reprocess_orphan_transactions(
        self,
        user: User,
        credit_card_id: int | None = None,
    ) -> dict:
        """
        Reprocessa transações órfãs que estão em contas de cartão de crédito
        mas não têm credit_card_id ou invoice_id definidos.

        Isso é útil para corrigir transações que foram criadas antes do fix
        de auto-inferência de credit_card_id.

        Args:
            user: Usuário autenticado
            credit_card_id: Se fornecido, processa apenas transações desse cartão

        Returns:
            Dict com estatísticas do reprocessamento:
            - found: número de transações órfãs encontradas
            - processed: número de transações processadas com sucesso
            - errors: lista de erros encontrados
            - invoices_updated: conjunto de faturas atualizadas
        """
        result = {
            "found": 0,
            "processed": 0,
            "errors": [],
            "invoices_updated": set(),
            "transactions": [],
        }

        # Buscar todos os cartões de crédito do usuário (ou um específico)
        cc_query = select(CreditCard).where(CreditCard.user_id == user.id)
        if credit_card_id:
            cc_query = cc_query.where(CreditCard.id == credit_card_id)

        cc_result = await self.db.execute(cc_query)
        credit_cards = cc_result.scalars().all()

        if not credit_cards:
            return result

        # Para cada cartão, buscar account_id associado
        for credit_card in credit_cards:
            # Buscar transações órfãs: estão na conta do cartão mas sem credit_card_id
            orphan_query = (
                select(Transaction)
                .where(
                    and_(
                        Transaction.user_id == user.id,
                        Transaction.account_id == credit_card.account_id,
                        Transaction.credit_card_id.is_(None),
                        Transaction.type == TransactionType.EXPENSE.value,
                    )
                )
                .order_by(Transaction.date)
            )

            orphan_result = await self.db.execute(orphan_query)
            orphan_transactions = orphan_result.scalars().all()

            result["found"] += len(orphan_transactions)

            for tx in orphan_transactions:
                try:
                    # Calcular período da fatura baseado na data da transação
                    period = self.calculate_invoice_period(credit_card, tx.date)

                    # Obter ou criar fatura para o período
                    invoice = await self.get_or_create_invoice(
                        user=user,
                        credit_card=credit_card,
                        reference_month=period["reference_month"],
                        reference_year=period["reference_year"],
                        closing_date=period["closing_date"],
                        due_date=period["due_date"],
                    )

                    # Atualizar a transação
                    tx.credit_card_id = credit_card.id
                    tx.invoice_id = invoice.id

                    # Atualizar payment_method se estava incorreto
                    if tx.payment_method != PaymentMethod.CREDIT_CARD.value:
                        tx.payment_method = PaymentMethod.CREDIT_CARD.value

                    result["processed"] += 1
                    result["invoices_updated"].add(invoice.id)
                    result["transactions"].append(
                        {
                            "id": tx.id,
                            "description": tx.description,
                            "amount": float(tx.amount),
                            "date": tx.date.isoformat(),
                            "invoice_id": invoice.id,
                            "invoice_ref": f"{period['reference_month']:02d}/{period['reference_year']}",
                        }
                    )

                except Exception as e:
                    result["errors"].append(
                        {
                            "transaction_id": tx.id,
                            "error": str(e),
                        }
                    )

        await self.db.flush()

        # Atualizar totais das faturas afetadas
        if result["invoices_updated"]:
            invoices_result = await self.db.execute(
                select(CreditCardInvoice).where(
                    CreditCardInvoice.id.in_(result["invoices_updated"])
                )
            )
            for invoice in invoices_result.scalars().all():
                await self.update_invoice_total(invoice)

        # Converter set para lista para serialização JSON
        result["invoices_updated"] = list(result["invoices_updated"])

        return result
