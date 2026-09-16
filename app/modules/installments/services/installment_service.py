"""Serviço para gerenciamento de parcelas e detecção de duplicatas"""

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_card import CreditCard
from app.models.installment import InstallmentSeries, InstallmentSeriesStatus
from app.models.merchant import Merchant
from app.models.transaction import Transaction, TransactionType
from app.models.user import User


class InstallmentService:
    """Gerencia séries de parcelas e detecta duplicatas"""

    # Tolerância para considerar valores "similares" (5%)
    AMOUNT_TOLERANCE = 0.05

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_matching_series(
        self,
        user: User,
        first_transaction_id: int | None = None,
        # Parâmetros legados mantidos para compatibilidade (depreciar no futuro)
        merchant_name: str | None = None,
        installment_amount: float | None = None,
        installment_total: int | None = None,
        account_id: int | None = None,
        transaction_date: date | None = None,
        installment_number: int | None = None,
    ) -> InstallmentSeries | None:
        """
        Busca uma série de parcelas existente.

        NOVA LÓGICA (preferencial):
        - Se first_transaction_id fornecido, busca série vinculada a essa transação
        - Isso garante que cada compra tenha sua própria série

        LÓGICA LEGADA (fallback para compatibilidade):
        - Mesmo merchant (normalizado)
        - Valor similar (±5%)
        - Mesmo total de parcelas
        - Série ainda ativa
        - Data da primeira parcela compatível (se fornecida data e número da parcela)
        """
        # Nova lógica: buscar por first_transaction_id (preferencial)
        if first_transaction_id:
            result = await self.db.execute(
                select(InstallmentSeries).where(
                    and_(
                        InstallmentSeries.user_id == user.id,
                        InstallmentSeries.first_transaction_id == first_transaction_id,
                        InstallmentSeries.status == InstallmentSeriesStatus.ACTIVE,
                    )
                )
            )
            return result.scalar_one_or_none()

        # Fallback: lógica legada para compatibilidade
        if not merchant_name or not installment_amount or not installment_total:
            return None

        normalized_merchant = merchant_name.lower().strip()

        # Calcular range de valor
        min_amount = installment_amount * (1 - self.AMOUNT_TOLERANCE)
        max_amount = installment_amount * (1 + self.AMOUNT_TOLERANCE)

        query = select(InstallmentSeries).where(
            and_(
                InstallmentSeries.user_id == user.id,
                InstallmentSeries.status == InstallmentSeriesStatus.ACTIVE,
                InstallmentSeries.installment_count == installment_total,
                InstallmentSeries.installment_amount >= min_amount,
                InstallmentSeries.installment_amount <= max_amount,
                func.lower(InstallmentSeries.merchant_name) == normalized_merchant,
            )
        )

        # Se account_id fornecido, usar como filtro adicional
        if account_id:
            query = query.where(InstallmentSeries.account_id == account_id)

        result = await self.db.execute(query)
        candidates = list(result.scalars().all())

        if not candidates:
            return None

        # Se temos data e número da parcela, filtrar por compatibilidade de data
        if transaction_date and installment_number:
            # Calcular a data esperada da primeira parcela desta compra
            # Se estou na parcela N com data X, a primeira parcela seria X - (N-1) meses
            expected_first_date = transaction_date - relativedelta(months=installment_number - 1)

            for series in candidates:
                # A série é compatível se a first_installment_date está próxima (±45 dias)
                # da data esperada calculada
                date_diff = abs((series.first_installment_date - expected_first_date).days)
                if date_diff <= 45:
                    return series

            # Nenhuma série com data compatível encontrada
            return None

        # Sem data para validar, retorna a primeira (comportamento antigo)
        return candidates[0] if candidates else None

    async def find_matching_series_fuzzy(
        self,
        user: User,
        merchant_name: str,
        installment_amount: float,
        installment_total: int,
        credit_card_id: int | None = None,
        invoice_month: int | None = None,
        invoice_year: int | None = None,
    ) -> InstallmentSeries | None:
        """
        Busca serie de parcelas usando fuzzy matching no nome do merchant.

        Criterios de match (todos devem bater):
        1. Mesmo credit_card_id (se fornecido)
        2. Mesmo installment_total
        3. Valor similar (+/- 5% tolerancia)
        4. Nome do merchant similar (>=50% word overlap apos normalizacao)
        5. Serie ainda ativa com parcelas pendentes

        Args:
            user: Usuario atual
            merchant_name: Nome do estabelecimento da fatura
            installment_amount: Valor da parcela
            installment_total: Total de parcelas
            credit_card_id: ID do cartao de credito (opcional)
            invoice_month: Mes da fatura (para contexto)
            invoice_year: Ano da fatura (para contexto)

        Returns:
            InstallmentSeries se encontrar match, None caso contrario
        """
        # DEBUG: Log dos parâmetros recebidos
        print(
            f"[FUZZY DEBUG] find_matching_series_fuzzy chamada: "
            f"merchant='{merchant_name}', amount={installment_amount}, "
            f"total={installment_total}, card_id={credit_card_id}"
        )

        if not merchant_name or not installment_amount or not installment_total:
            print(
                f"[FUZZY DEBUG] Retornando None - parametros invalidos: "
                f"merchant={bool(merchant_name)}, amount={bool(installment_amount)}, total={bool(installment_total)}"
            )
            return None

        # Normalizar merchant name da fatura
        normalized_merchant = self._normalize_merchant_name(merchant_name)
        merchant_words = set(normalized_merchant.split())

        if not merchant_words:
            return None

        # Calcular range de valor (tolerancia de 5%)
        min_amount = installment_amount * (1 - self.AMOUNT_TOLERANCE)
        max_amount = installment_amount * (1 + self.AMOUNT_TOLERANCE)

        # Query base: series ativas com mesmo total de parcelas e valor similar
        query = select(InstallmentSeries).where(
            and_(
                InstallmentSeries.user_id == user.id,
                InstallmentSeries.status == InstallmentSeriesStatus.ACTIVE,
                InstallmentSeries.installment_count == installment_total,
                InstallmentSeries.installment_amount >= min_amount,
                InstallmentSeries.installment_amount <= max_amount,
                InstallmentSeries.paid_count < InstallmentSeries.installment_count,
            )
        )

        # Filtrar por credit_card_id se fornecido
        if credit_card_id:
            query = query.where(InstallmentSeries.credit_card_id == credit_card_id)

        result = await self.db.execute(query)
        candidates = list(result.scalars().all())

        # DEBUG: Log dos candidatos encontrados
        print(f"[FUZZY DEBUG] Candidatos encontrados: {len(candidates)}")
        for c in candidates[:5]:  # Mostrar max 5
            print(
                f"  - id={c.id}, merchant='{c.merchant_name}', amount={c.installment_amount}, "
                f"count={c.installment_count}, paid={c.paid_count}"
            )

        if not candidates:
            print(
                f"[FUZZY DEBUG] Nenhum candidato encontrado para: "
                f"amount_range=[{min_amount:.2f}, {max_amount:.2f}], total={installment_total}"
            )
            return None

        # Score candidates por similaridade do nome do merchant
        best_match = None
        best_score = 0.0

        for series in candidates:
            if not series.merchant_name:
                continue

            series_normalized = self._normalize_merchant_name(series.merchant_name)
            series_words = set(series_normalized.split())

            if not series_words:
                continue

            # Calcular word overlap similarity
            common_words = merchant_words & series_words
            total_words = max(len(merchant_words), len(series_words))

            if total_words == 0:
                continue

            similarity = len(common_words) / total_words

            # Bonus para match de palavras significativas (>=4 caracteres)
            significant_words = {w for w in merchant_words if len(w) >= 4}
            significant_match = significant_words & series_words
            if significant_match:
                similarity += 0.2 * len(significant_match)

            # Bonus para match exato de primeira palavra significativa
            if significant_words and series_words:
                first_significant = sorted(significant_words, key=len, reverse=True)
                if first_significant and first_significant[0] in series_words:
                    similarity += 0.3

            if similarity > best_score and similarity >= 0.5:  # Minimo 50% match
                best_score = similarity
                best_match = series

                print(
                    f"[InstallmentService] Fuzzy match candidato: "
                    f"'{merchant_name}' ~= '{series.merchant_name}' "
                    f"(score: {similarity:.2f})"
                )

                # Se match quase perfeito, usar imediatamente
                if similarity >= 0.9:
                    break

        if best_match:
            print(
                f"[InstallmentService] Fuzzy match encontrado: series_id={best_match.id}, "
                f"merchant='{best_match.merchant_name}', score={best_score:.2f}"
            )

        return best_match

    def _normalize_merchant_name(self, name: str) -> str:
        """
        Normaliza nome do merchant para comparacao fuzzy.

        Remove:
        - Acentos
        - Sufixos de empresa (LTDA, S.A., etc.)
        - Padroes de parcela (3/12, PARC.3/12)
        - Caracteres especiais (*, -, _)
        """
        import unicodedata

        if not name:
            return ""

        # Remove acentos
        name = unicodedata.normalize("NFD", name)
        name = "".join(c for c in name if unicodedata.category(c) != "Mn")

        # Lowercase
        name = name.lower()

        # Remove padroes de parcela: "3/12", "PARC.3/12", "PARC 3/12", "(Parcela 3 de 12)"
        # IMPORTANTE: Padroes mais especificos devem vir ANTES dos genericos
        import re

        parcela_patterns = [
            r"\s*\(parcela\s*\d+\s*de\s*\d+\)",  # "(Parcela 3 de 12)"
            r"\s*parc\.?\s*\d+/\d+",  # "PARC.3/12" ou "PARC 3/12"
            r"\s*\d+/\d+\s*$",  # "3/12" no final (mais generico)
        ]
        for pattern in parcela_patterns:
            name = re.sub(pattern, "", name, flags=re.IGNORECASE)

        # Remove sufixos de empresa
        company_suffixes = [
            r"\s+ltda\.?$",
            r"\s+s\.?a\.?$",
            r"\s+eireli$",
            r"\s+mei$",
            r"\s+me$",
        ]
        for pattern in company_suffixes:
            name = re.sub(pattern, "", name, flags=re.IGNORECASE)

        # Remove caracteres especiais
        name = re.sub(r"[\*\-_\.]", " ", name)

        # Remove espacos extras
        name = " ".join(name.split())

        return name.strip()

    async def find_potential_duplicate(
        self,
        user: User,
        merchant_name: str,
        installment_amount: float,
        installment_total: int,
        credit_card_id: int | None = None,
        min_similarity: float = 0.75,
    ) -> tuple[InstallmentSeries, float] | None:
        """
        Busca série similar para detectar duplicatas durante upload.

        Similar a find_matching_series_fuzzy, mas retorna também o score
        de similaridade para exibir ao usuário.

        Critérios:
        - Fuzzy match no merchant_name (>= min_similarity)
        - Valor da parcela com tolerância de 5%
        - Mesmo total de parcelas
        - Mesmo cartão de crédito (se fornecido)
        - Série ativa com parcelas pendentes

        Returns:
            Tupla (série, similarity_score) ou None se não encontrar match
        """
        if not merchant_name or not installment_amount or not installment_total:
            return None

        # Normalizar merchant name
        normalized_merchant = self._normalize_merchant_name(merchant_name)
        merchant_words = set(normalized_merchant.split())

        if not merchant_words:
            return None

        # Calcular range de valor (tolerância de 5%)
        min_amount = installment_amount * (1 - self.AMOUNT_TOLERANCE)
        max_amount = installment_amount * (1 + self.AMOUNT_TOLERANCE)

        # Query base: séries ativas com mesmo total de parcelas e valor similar
        query = select(InstallmentSeries).where(
            and_(
                InstallmentSeries.user_id == user.id,
                InstallmentSeries.status == InstallmentSeriesStatus.ACTIVE,
                InstallmentSeries.installment_count == installment_total,
                InstallmentSeries.installment_amount >= min_amount,
                InstallmentSeries.installment_amount <= max_amount,
                InstallmentSeries.paid_count < InstallmentSeries.installment_count,
            )
        )

        # Filtrar por credit_card_id se fornecido
        if credit_card_id:
            query = query.where(InstallmentSeries.credit_card_id == credit_card_id)

        result = await self.db.execute(query)
        candidates = list(result.scalars().all())

        if not candidates:
            return None

        # Score candidates por similaridade do nome do merchant
        best_match = None
        best_score = 0.0

        for series in candidates:
            if not series.merchant_name:
                continue

            series_normalized = self._normalize_merchant_name(series.merchant_name)
            series_words = set(series_normalized.split())

            if not series_words:
                continue

            # Calcular word overlap similarity
            common_words = merchant_words & series_words
            total_words = max(len(merchant_words), len(series_words))

            if total_words == 0:
                continue

            similarity = len(common_words) / total_words

            # Bonus para match de palavras significativas (>=4 caracteres)
            significant_words = {w for w in merchant_words if len(w) >= 4}
            significant_match = significant_words & series_words
            if significant_match:
                similarity += 0.2 * len(significant_match)

            # Bonus para match exato de primeira palavra significativa
            if significant_words and series_words:
                first_significant = sorted(significant_words, key=len, reverse=True)
                if first_significant and first_significant[0] in series_words:
                    similarity += 0.3

            if similarity > best_score and similarity >= min_similarity:
                best_score = similarity
                best_match = series

        if best_match:
            return (best_match, best_score)

        return None

    async def find_existing_installment(
        self,
        series: InstallmentSeries,
        installment_number: int,
    ) -> Transaction | None:
        """Verifica se uma parcela específica já foi cadastrada na série"""
        result = await self.db.execute(
            select(Transaction).where(
                and_(
                    Transaction.installment_series_id == series.id,
                    Transaction.installment_number == installment_number,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_series_status(
        self,
        series: InstallmentSeries,
    ) -> dict:
        """
        Retorna o status detalhado de uma série de parcelas.

        Retorna:
        - Quais parcelas foram pagas
        - Quais estão pendentes
        - Próxima parcela esperada
        """
        # Buscar todas as transações da série
        result = await self.db.execute(
            select(Transaction)
            .where(Transaction.installment_series_id == series.id)
            .order_by(Transaction.installment_number)
        )
        transactions = list(result.scalars().all())

        # Mapear parcelas cadastradas
        registered = {t.installment_number: t for t in transactions}

        # Construir status de cada parcela
        installments_status = []
        for i in range(1, series.installment_count + 1):
            if i in registered:
                t = registered[i]
                installments_status.append(
                    {
                        "number": i,
                        "status": "paid" if t.is_paid else "registered",
                        "date": t.date.isoformat() if t.date else None,
                        "transaction_id": t.id,
                    }
                )
            else:
                # Calcular data esperada
                expected_date = series.first_installment_date + relativedelta(months=i - 1)
                installments_status.append(
                    {
                        "number": i,
                        "status": "pending",
                        "expected_date": expected_date.isoformat(),
                        "transaction_id": None,
                    }
                )

        paid_count = sum(1 for s in installments_status if s["status"] == "paid")

        return {
            "series_id": series.id,
            "description": series.description,
            "merchant_name": series.merchant_name,
            "total_amount": float(series.total_amount),
            "installment_amount": float(series.installment_amount),
            "installment_count": series.installment_count,
            "paid_count": paid_count,
            "remaining_count": series.installment_count - paid_count,
            "remaining_amount": float(
                series.installment_amount * (series.installment_count - paid_count)
            ),
            "status": series.status,
            "installments": installments_status,
        }

    async def create_series(
        self,
        user: User,
        description: str,
        merchant_name: str,
        installment_amount: float,
        installment_count: int,
        first_installment_date: date,
        account_id: int,
        first_transaction_id: int | None = None,  # NOVO: vincula à transação que originou a série
        category_id: int | None = None,
        purchase_date: date | None = None,
        credit_card_id: int | None = None,
    ) -> InstallmentSeries:
        """
        Cria uma nova série de parcelas.

        Args:
            first_transaction_id: ID da transação que originou esta série.
                                  Garante unicidade - uma transação só pode ser origem de uma série.
        """
        # Obter ou criar merchant
        merchant_id = await self._get_or_create_merchant(merchant_name)

        total_amount = installment_amount * installment_count

        series = InstallmentSeries(
            user_id=user.id,
            description=description,
            merchant_id=merchant_id,
            merchant_name=merchant_name,
            total_amount=total_amount,
            installment_amount=installment_amount,
            installment_count=installment_count,
            purchase_date=purchase_date,
            first_installment_date=first_installment_date,
            account_id=account_id,
            category_id=category_id,
            credit_card_id=credit_card_id,
            first_transaction_id=first_transaction_id,  # NOVO
            status=InstallmentSeriesStatus.ACTIVE,
            paid_count=0,
        )

        self.db.add(series)
        await self.db.flush()
        await self.db.refresh(series)

        return series

    async def create_installment_transaction(
        self,
        user: User,
        series: InstallmentSeries,
        installment_number: int,
        transaction_date: date,
        is_paid: bool = True,
        document_id: int | None = None,
        credit_card_id: int | None = None,
        invoice_id: int | None = None,
        force_duplicate: bool = False,
    ) -> Transaction:
        """Cria uma transação de parcela vinculada a uma série"""
        # Verificar se parcela já existe (a menos que force_duplicate seja True)
        if not force_duplicate:
            existing = await self.find_existing_installment(series, installment_number)
            if existing:
                # Usar 409 Conflict para que o frontend trate como "skip e continuar"
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Parcela {installment_number}/{series.installment_count} de '{series.description}' (R$ {series.total_amount:.2f}) já cadastrada em {existing.date.strftime('%d/%m/%Y')}",
                )

        # Usar credit_card_id da série se não fornecido
        card_id = credit_card_id or series.credit_card_id

        transaction = Transaction(
            user_id=user.id,
            account_id=series.account_id,
            category_id=series.category_id,
            merchant_id=series.merchant_id,
            document_id=document_id,
            credit_card_id=card_id,
            invoice_id=invoice_id,
            installment_series_id=series.id,
            type=TransactionType.EXPENSE,
            amount=series.installment_amount,
            date=transaction_date,
            description=f"{series.description} - Parcela {installment_number}/{series.installment_count}",
            installment_number=installment_number,
            installment_total=series.installment_count,
            is_paid=is_paid,
            is_fixed=True,  # Parcelas são consideradas gastos fixos
        )

        self.db.add(transaction)

        # Atualizar contador de parcelas pagas
        if is_paid:
            series.paid_count += 1
            if series.paid_count >= series.installment_count:
                series.status = InstallmentSeriesStatus.COMPLETED

        await self.db.flush()
        await self.db.refresh(transaction)

        return transaction

    async def mark_previous_installments_as_paid(
        self,
        user: User,
        series: InstallmentSeries,
        up_to_installment: int,
    ) -> list[Transaction]:
        """
        Marca parcelas anteriores como pagas (sem documento vinculado).

        Útil para o cenário onde o usuário já pagou parcelas antes de começar
        a usar o sistema.
        """
        created_transactions = []

        for i in range(1, up_to_installment):
            existing = await self.find_existing_installment(series, i)
            if existing:
                continue

            # Calcular data estimada da parcela
            estimated_date = series.first_installment_date + relativedelta(months=i - 1)

            transaction = Transaction(
                user_id=user.id,
                account_id=series.account_id,
                category_id=series.category_id,
                merchant_id=series.merchant_id,
                document_id=None,  # Sem documento
                installment_series_id=series.id,
                type=TransactionType.EXPENSE,
                amount=series.installment_amount,
                date=estimated_date,
                description=f"{series.description} - Parcela {i}/{series.installment_count} (retroativa)",
                installment_number=i,
                installment_total=series.installment_count,
                is_paid=True,
                is_fixed=True,
            )

            self.db.add(transaction)
            series.paid_count += 1
            created_transactions.append(transaction)

        if series.paid_count >= series.installment_count:
            series.status = InstallmentSeriesStatus.COMPLETED

        await self.db.flush()

        return created_transactions

    async def create_future_installments(
        self,
        user: User,
        series: InstallmentSeries,
        from_installment: int,
        current_invoice_month: int | None = None,
        current_invoice_year: int | None = None,
    ) -> list[Transaction]:
        """
        Cria transações para parcelas futuras (marcadas como não pagas).
        Também cria as faturas futuras correspondentes se o cartão de crédito estiver vinculado.

        IMPORTANTE: Para parcelamentos, a fatura é determinada pelo MÊS, não pela data da transação.
        - Parcela N vai para a fatura do mês (current_invoice_month + (N - from_installment))

        Args:
            current_invoice_month/year: Mês/ano da fatura onde a parcela atual foi lançada.
                                        Se fornecido, as parcelas futuras são calculadas incrementando o mês.
        """
        created_transactions = []

        print(
            f"[INSTALLMENT_SVC] create_future_installments: series_id={series.id}, "
            f"first_installment_date={series.first_installment_date}, "
            f"from_installment={from_installment}, total={series.installment_count}, "
            f"current_invoice={current_invoice_month}/{current_invoice_year}"
        )

        # Buscar cartão de crédito se houver
        credit_card = None
        invoice_service = None
        if series.credit_card_id:
            result = await self.db.execute(
                select(CreditCard).where(CreditCard.id == series.credit_card_id)
            )
            credit_card = result.scalar_one_or_none()

            if credit_card:
                from app.modules.credit_cards.services.invoice_service import InvoiceService

                invoice_service = InvoiceService(self.db)
                print(
                    f"[INSTALLMENT_SVC] Card: closing_day={credit_card.closing_day}, "
                    f"due_day={credit_card.due_day}"
                )

        for i in range(from_installment + 1, series.installment_count + 1):
            existing = await self.find_existing_installment(series, i)
            if existing:
                continue

            # Calcular data estimada da parcela (para registro)
            estimated_date = series.first_installment_date + relativedelta(months=i - 1)
            print(
                f"[INSTALLMENT_SVC] Parcela {i}/{series.installment_count}: estimated_date={estimated_date}"
            )

            # Se tem cartão de crédito, obter/criar fatura para o período
            invoice_id = None
            if credit_card and invoice_service:
                # NOVO: Se temos o mês/ano da fatura atual, calcular diretamente pelo offset de meses
                if current_invoice_month and current_invoice_year:
                    # Parcela futura vai para: fatura_atual + (parcela_futura - parcela_atual) meses
                    months_offset = i - from_installment
                    base_date = date(current_invoice_year, current_invoice_month, 1)
                    future_date = base_date + relativedelta(months=months_offset)
                    ref_month = future_date.month
                    ref_year = future_date.year

                    print(
                        f"[INSTALLMENT_SVC] Parcela {i}: usando fatura atual + {months_offset} meses "
                        f"-> ({ref_month}/{ref_year})"
                    )

                    # Calcular datas de fechamento/vencimento para o mês
                    dates = invoice_service.calculate_invoice_dates(
                        credit_card, ref_month, ref_year
                    )

                    invoice = await invoice_service.get_or_create_invoice(
                        user=user,
                        credit_card=credit_card,
                        reference_month=ref_month,
                        reference_year=ref_year,
                        closing_date=dates["closing_date"],
                        due_date=dates["due_date"],
                    )
                else:
                    # Fallback: calcular pelo período baseado na data (comportamento antigo)
                    period = invoice_service.calculate_invoice_period(credit_card, estimated_date)
                    print(
                        f"[INSTALLMENT_SVC] Parcela {i}: usando calculate_invoice_period "
                        f"-> ({period['reference_month']}/{period['reference_year']})"
                    )
                    invoice = await invoice_service.get_or_create_invoice(
                        user=user,
                        credit_card=credit_card,
                        reference_month=period["reference_month"],
                        reference_year=period["reference_year"],
                        closing_date=period["closing_date"],
                        due_date=period["due_date"],
                    )

                invoice_id = invoice.id
                print(f"[INSTALLMENT_SVC] Parcela {i} -> invoice_id={invoice_id}")

            transaction = Transaction(
                user_id=user.id,
                account_id=series.account_id,
                category_id=series.category_id,
                merchant_id=series.merchant_id,
                document_id=None,
                credit_card_id=series.credit_card_id,
                invoice_id=invoice_id,
                installment_series_id=series.id,
                type=TransactionType.EXPENSE,
                amount=series.installment_amount,
                date=estimated_date,
                description=f"{series.description} - Parcela {i}/{series.installment_count}",
                installment_number=i,
                installment_total=series.installment_count,
                is_paid=False,  # Parcela futura
                is_fixed=True,
            )

            self.db.add(transaction)
            created_transactions.append(transaction)

        await self.db.flush()

        # Atualizar totais das faturas criadas (batch)
        if credit_card and invoice_service:
            from app.models.credit_card_invoice import CreditCardInvoice

            invoice_ids = list(set(t.invoice_id for t in created_transactions if t.invoice_id))
            if invoice_ids:
                result = await self.db.execute(
                    select(CreditCardInvoice).where(CreditCardInvoice.id.in_(invoice_ids))
                )
                for invoice in result.scalars().all():
                    await invoice_service.update_invoice_total(invoice)

        return created_transactions

    async def confirm_existing_installment(
        self,
        user: User,
        series: InstallmentSeries,
        installment_number: int,
        document_id: int | None = None,
        actual_amount: float | None = None,
        actual_date: date | None = None,
    ) -> Transaction | None:
        """
        Confirma uma parcela existente (criada como futura) quando o PDF da fatura é enviado.

        Atualiza:
        - document_id: vincula ao documento
        - is_paid: marca como paga
        - amount: atualiza se diferente (ex: correção de valor)
        - date: atualiza se diferente

        Retorna a transação atualizada ou None se não existir.
        """
        existing = await self.find_existing_installment(series, installment_number)

        if not existing:
            return None

        # Atualizar campos
        if document_id:
            existing.document_id = document_id

        if not existing.is_paid:
            existing.is_paid = True
            series.paid_count += 1

            if series.paid_count >= series.installment_count:
                series.status = InstallmentSeriesStatus.COMPLETED

        # Atualizar valor com o valor real da fatura (corrige arredondamentos de projeção)
        if actual_amount and float(existing.amount) != actual_amount:
            existing.amount = actual_amount

        # Atualizar data se fornecida e diferente
        if actual_date and existing.date != actual_date:
            existing.date = actual_date

        await self.db.flush()
        await self.db.refresh(existing)

        return existing

    async def find_matching_transaction_for_pdf(
        self,
        user: User,
        merchant_name: str,
        amount: float,
        transaction_date: date,
        installment_number: int | None = None,
        installment_total: int | None = None,
        credit_card_id: int | None = None,
    ) -> Transaction | None:
        """
        Busca uma transação existente (parcela futura ou recorrente projetada)
        que corresponda aos dados do PDF.

        Usado para evitar duplicatas quando o PDF real é enviado.

        Critérios de match:
        - Mesmo cartão de crédito
        - Valor similar (±5%)
        - Data próxima (±15 dias)
        - Se for parcela: mesmo installment_number e installment_total
        - Descrição similar (contém mesmo merchant)
        """
        normalized_merchant = merchant_name.lower().strip()
        min_amount = amount * 0.95
        max_amount = amount * 1.05
        min_date = transaction_date - timedelta(days=15)
        max_date = transaction_date + timedelta(days=15)

        query = select(Transaction).where(
            and_(
                Transaction.user_id == user.id,
                Transaction.amount >= min_amount,
                Transaction.amount <= max_amount,
                Transaction.date >= min_date,
                Transaction.date <= max_date,
                Transaction.is_paid == False,  # Transação futura/projetada
            )
        )

        if credit_card_id:
            query = query.where(Transaction.credit_card_id == credit_card_id)

        # Se for parcela, filtrar por número
        if installment_number and installment_total:
            query = query.where(
                and_(
                    Transaction.installment_number == installment_number,
                    Transaction.installment_total == installment_total,
                )
            )

        result = await self.db.execute(query)
        candidates = list(result.scalars().all())

        if not candidates:
            return None

        # Filtrar por merchant name similar
        for tx in candidates:
            if tx.description and normalized_merchant in tx.description.lower():
                return tx

        # Se não encontrou match exato, retornar o primeiro candidato
        return candidates[0] if candidates else None

    async def get_user_series(
        self,
        user: User,
        status_filter: InstallmentSeriesStatus | None = None,
        limit: int = 50,
    ) -> list[InstallmentSeries]:
        """Lista séries de parcelas do usuário"""
        query = select(InstallmentSeries).where(InstallmentSeries.user_id == user.id)

        if status_filter:
            query = query.where(InstallmentSeries.status == status_filter)

        query = query.order_by(InstallmentSeries.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_series_by_id(
        self,
        user: User,
        series_id: int,
    ) -> InstallmentSeries | None:
        """Obtém uma série por ID"""
        result = await self.db.execute(
            select(InstallmentSeries).where(
                and_(
                    InstallmentSeries.id == series_id,
                    InstallmentSeries.user_id == user.id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def analyze_extracted_item(
        self,
        user: User,
        item: dict,
        account_id: int,
    ) -> dict:
        """
        Analisa um item extraído e verifica se é uma parcela de série existente.

        Retorna informações sobre:
        - Se é uma parcela
        - Se a série já existe
        - Se a parcela específica já foi cadastrada
        - Sugestões de ação
        """
        result = {
            "is_installment": item.get("is_installment", False),
            "series_found": None,
            "series_status": None,
            "installment_exists": False,
            "suggestion": None,
        }

        if not result["is_installment"]:
            result["suggestion"] = "create_single"  # Criar transação única
            return result

        installment_current = item.get("installment_current")
        installment_total = item.get("installment_total")
        amount = item.get("amount", 0)
        description = item.get("description", "")

        # Buscar série existente
        series = await self.find_matching_series(
            user=user,
            merchant_name=description,
            installment_amount=amount,
            installment_total=installment_total,
            account_id=account_id,
        )

        if series:
            result["series_found"] = {
                "id": series.id,
                "description": series.description,
                "merchant_name": series.merchant_name,
                "installment_count": series.installment_count,
                "paid_count": series.paid_count,
            }

            # Verificar se esta parcela específica já existe
            existing = await self.find_existing_installment(series, installment_current)
            if existing:
                result["installment_exists"] = True
                result["suggestion"] = "skip"  # Pular, já existe
            else:
                # Verificar se há parcelas anteriores não cadastradas
                series_status = await self.get_series_status(series)
                result["series_status"] = series_status

                pending_before = [
                    s
                    for s in series_status["installments"]
                    if s["number"] < installment_current and s["status"] == "pending"
                ]

                if pending_before:
                    result["suggestion"] = "mark_previous_paid"
                    result["pending_installments"] = pending_before
                else:
                    result["suggestion"] = "add_to_series"
        else:
            # Série não existe, sugerir criar
            result["suggestion"] = "create_series"
            result["suggested_series"] = {
                "description": description,
                "merchant_name": description,
                "installment_amount": amount,
                "installment_count": installment_total,
                "current_installment": installment_current,
            }

        return result

    async def _get_or_create_merchant(self, name: str) -> int:
        """Obtém ou cria um merchant pelo nome"""
        normalized = name.lower().strip()
        result = await self.db.execute(
            select(Merchant).where(Merchant.normalized_name == normalized)
        )
        merchant = result.scalar_one_or_none()

        if not merchant:
            merchant = Merchant(name=name, normalized_name=normalized)
            self.db.add(merchant)
            await self.db.flush()

        return merchant.id
