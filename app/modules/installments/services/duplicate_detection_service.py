"""Serviço para detecção e resolução de duplicatas em séries de parcelas e transações"""

from fastapi import HTTPException, status
from rapidfuzz import fuzz
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.installment import InstallmentSeries, InstallmentSeriesStatus
from app.models.transaction import Transaction
from app.models.user import User
from app.modules.installments.schemas.duplicate import (
    ConflictDetail,
    DuplicateGroup,
    TransactionDuplicatePair,
    TransactionDuplicatesResponse,
)
from app.modules.installments.schemas.installment import InstallmentSeriesResponse
from app.modules.installments.services.installment_service import InstallmentService


class DuplicateDetectionService:
    """
    Detecta e resolve duplicatas em séries de parcelas e transações individuais.

    Funcionalidades:
    1. Detecção de séries duplicadas (find_duplicate_groups)
    2. Detecção de transações duplicadas (find_transaction_duplicates)
    3. Mesclagem de séries (merge_series)
    """

    # Constantes para hard rules de detecção de duplicatas em SÉRIES
    MAX_AMOUNT_DIFFERENCE_BRL = 0.05  # R$ 0,05 (5 centavos) - diferença absoluta máxima
    MIN_NAME_OVERLAP = 0.80  # 80% mínimo de palavras em comum

    # Constantes para detecção de duplicatas em TRANSAÇÕES INDIVIDUAIS
    MAX_TRANSACTION_AMOUNT_DIFF = 0.05  # R$ 0,05 diferença máxima entre valores
    MIN_DESCRIPTION_SIMILARITY = 80.0  # 80% similaridade mínima na descrição (fuzzy)
    MAX_DATE_DIFFERENCE_DAYS = 3  # 3 dias de diferença máxima entre datas (transações normais)
    MAX_DATE_DIFFERENCE_DAYS_INSTALLMENTS = (
        45  # 45 dias para parcelas (permite matching entre meses)
    )

    def __init__(self, db: AsyncSession):
        self.db = db
        self.installment_service = InstallmentService(db)

    def _normalize_description(self, description: str) -> str:
        """
        Normaliza descrição de transação para comparação fuzzy.

        Remove:
        - Acentos
        - Padrões de parcela (3/12, PARC.3/12, "(Parcela 3 de 12)", "- Parcela 3/12")
        - Caracteres especiais extras
        - Espaços duplicados
        """
        import re
        import unicodedata

        if not description:
            return ""

        # Remove acentos
        description = unicodedata.normalize("NFD", description)
        description = "".join(c for c in description if unicodedata.category(c) != "Mn")

        # Lowercase
        description = description.lower()

        # Remove padrões de parcela (do mais específico ao mais genérico)
        parcela_patterns = [
            r"\s*-?\s*parcela\s+\d+\s*/\s*\d+",  # "- Parcela 3/12" ou "Parcela 3/12"
            r"\s*\(parcela\s*\d+\s*de\s*\d+\)",  # "(Parcela 3 de 12)"
            r"\s*parc\.?\s*\d+\s*/\s*\d+",  # "PARC.3/12" ou "PARC 3/12"
            r"\s*\(\s*\d+\s*/\s*\d+\s*\)",  # "(3/12)"
            r"\s*\d+\s*/\s*\d+\s*$",  # "3/12" no final
        ]
        for pattern in parcela_patterns:
            description = re.sub(pattern, "", description, flags=re.IGNORECASE)

        # Remove caracteres especiais, mantendo apenas letras, números e espaços
        description = re.sub(r"[^\w\s]", " ", description)

        # Remove espaços duplicados
        description = re.sub(r"\s+", " ", description).strip()

        return description

    async def find_duplicate_groups(
        self, user: User, min_similarity: float = 0.7
    ) -> list[DuplicateGroup]:
        """
        Detecta grupos de séries similares.

        Algoritmo:
        1. Busca todas séries ativas do usuário
        2. Para cada par, calcula similarity score
        3. Agrupa séries com score >= min_similarity
        4. Identifica conflitos (parcelas duplicadas)
        5. Ordena por probabilidade de ser duplicata
        """
        # Buscar todas séries ativas
        result = await self.db.execute(
            select(InstallmentSeries)
            .where(
                and_(
                    InstallmentSeries.user_id == user.id,
                    InstallmentSeries.status == InstallmentSeriesStatus.ACTIVE,
                )
            )
            .order_by(InstallmentSeries.created_at.desc())
        )
        series_list = list(result.scalars().all())

        if len(series_list) < 2:
            return []

        # Encontrar pares duplicados
        duplicate_groups = []
        processed_ids = set()

        for i, series_a in enumerate(series_list):
            if series_a.id in processed_ids:
                continue

            for series_b in series_list[i + 1 :]:
                if series_b.id in processed_ids:
                    continue

                # Calcular similaridade
                score = self._calculate_similarity_score(series_a, series_b)

                if score >= min_similarity:
                    # Encontrar conflitos
                    conflicts = await self._find_conflicts(series_a, series_b)

                    # Estimar excesso devido a duplicatas
                    estimated_excess = sum(
                        float(series_a.installment_amount)
                        for c in conflicts
                        if c.series_a_transaction_id and c.series_b_transaction_id
                    )

                    # Sugerir série primária (mais antiga)
                    suggested_primary_id = (
                        series_a.id if series_a.created_at < series_b.created_at else series_b.id
                    )

                    duplicate_groups.append(
                        DuplicateGroup(
                            series=[
                                InstallmentSeriesResponse.model_validate(series_a),
                                InstallmentSeriesResponse.model_validate(series_b),
                            ],
                            similarity_score=score,
                            conflicts=conflicts,
                            suggested_primary_id=suggested_primary_id,
                            estimated_excess=estimated_excess,
                        )
                    )

                    # Marcar como processadas
                    processed_ids.add(series_a.id)
                    processed_ids.add(series_b.id)
                    break

        # Ordenar por score (maior primeiro)
        duplicate_groups.sort(key=lambda g: g.similarity_score, reverse=True)

        return duplicate_groups

    async def find_transaction_duplicates(
        self,
        user: User,
        min_similarity: float = 0.80,
        credit_card_id: int | None = None,
        reference_month: int | None = None,
        reference_year: int | None = None,
    ) -> TransactionDuplicatesResponse:
        """
        Detecta duplicatas entre transações individuais.

        Compara:
        - Transações avulsas vs transações de séries
        - Transações avulsas vs transações avulsas

        Critérios:
        - Mesmo valor (±R$ 0,05)
        - Descrição similar (fuzzy matching >= 80%)
        - Mesma data aproximada (±3 dias)

        Args:
            user: Usuário dono das transações
            min_similarity: Similaridade mínima (0.0 a 1.0)
            credit_card_id: Filtrar por cartão específico
            reference_month: Filtrar por mês de referência
            reference_year: Filtrar por ano de referência
        """
        # Buscar transações do usuário
        query = select(Transaction).where(Transaction.user_id == user.id)

        # Filtros opcionais
        if credit_card_id:
            query = query.where(Transaction.credit_card_id == credit_card_id)

        if reference_month and reference_year:
            # Buscar por fatura (transactions que cairiam nessa fatura)
            from datetime import date

            # Aproximação: transações do mês anterior ao fechamento
            start_date = date(reference_year, reference_month - 1 if reference_month > 1 else 12, 1)
            end_date = date(reference_year, reference_month, 28)  # Aproximado
            query = query.where(
                and_(
                    Transaction.date >= start_date,
                    Transaction.date <= end_date,
                )
            )

        result = await self.db.execute(query.order_by(Transaction.date.desc()))
        transactions = list(result.scalars().all())

        if len(transactions) < 2:
            return TransactionDuplicatesResponse(
                duplicate_pairs=[],
                total_pairs=0,
                estimated_excess=0.0,
            )

        # Encontrar pares duplicados
        duplicate_pairs = []
        processed_ids = set()

        for i, tx_a in enumerate(transactions):
            if tx_a.id in processed_ids:
                continue

            for tx_b in transactions[i + 1 :]:
                if tx_b.id in processed_ids:
                    continue

                # Verificar se são duplicatas
                is_duplicate, score = self._check_transaction_duplicate(tx_a, tx_b)

                if is_duplicate and score >= min_similarity:
                    # Calcular diferença de valores
                    amount_diff = abs(float(tx_a.amount) - float(tx_b.amount))

                    # Calcular diferença de dias
                    days_apart = abs((tx_a.date - tx_b.date).days)

                    # Sugerir ação
                    suggested_action = self._suggest_duplicate_action(tx_a, tx_b)

                    duplicate_pairs.append(
                        TransactionDuplicatePair(
                            transaction_a_id=tx_a.id,
                            transaction_a_description=tx_a.description,
                            transaction_a_date=tx_a.date,
                            transaction_a_amount=float(tx_a.amount),
                            transaction_a_is_installment=tx_a.installment_series_id is not None,
                            transaction_b_id=tx_b.id,
                            transaction_b_description=tx_b.description,
                            transaction_b_date=tx_b.date,
                            transaction_b_amount=float(tx_b.amount),
                            transaction_b_is_installment=tx_b.installment_series_id is not None,
                            similarity_score=score,
                            amount_difference=amount_diff,
                            days_apart=days_apart,
                            suggested_action=suggested_action,
                        )
                    )

                    # Marcar como processadas
                    processed_ids.add(tx_a.id)
                    processed_ids.add(tx_b.id)
                    break

        # Ordenar por score (maior primeiro)
        duplicate_pairs.sort(key=lambda p: p.similarity_score, reverse=True)

        # Calcular excesso estimado
        estimated_excess = sum(
            min(pair.transaction_a_amount, pair.transaction_b_amount) for pair in duplicate_pairs
        )

        return TransactionDuplicatesResponse(
            duplicate_pairs=duplicate_pairs,
            total_pairs=len(duplicate_pairs),
            estimated_excess=estimated_excess,
        )

    def _check_transaction_duplicate(
        self,
        tx_a: Transaction,
        tx_b: Transaction,
    ) -> tuple[bool, float]:
        """
        Verifica se duas transações são duplicatas.

        Retorna: (is_duplicate, similarity_score)
        """
        # Hard Rule 1: Valores devem ser muito próximos
        if not tx_a.amount or not tx_b.amount:
            return False, 0.0

        amount_a = float(tx_a.amount)
        amount_b = float(tx_b.amount)
        amount_diff = abs(amount_a - amount_b)

        if amount_diff > self.MAX_TRANSACTION_AMOUNT_DIFF:
            return False, 0.0

        # Hard Rule 2: Datas devem ser próximas
        if not tx_a.date or not tx_b.date:
            return False, 0.0

        days_apart = abs((tx_a.date - tx_b.date).days)

        # Usar tolerância maior para parcelas (permite matching entre meses diferentes)
        is_installment = (
            tx_a.installment_number is not None and tx_a.installment_total is not None
        ) or (tx_b.installment_number is not None and tx_b.installment_total is not None)
        max_date_diff = (
            self.MAX_DATE_DIFFERENCE_DAYS_INSTALLMENTS
            if is_installment
            else self.MAX_DATE_DIFFERENCE_DAYS
        )

        if days_apart > max_date_diff:
            return False, 0.0

        # Soft Scoring: Similaridade de descrição
        if not tx_a.description or not tx_b.description:
            return False, 0.0

        # Normalizar descrições antes do fuzzy matching (remove padrões de parcela)
        normalized_desc_a = self._normalize_description(tx_a.description)
        normalized_desc_b = self._normalize_description(tx_b.description)

        # Usar fuzzy matching para comparar descrições normalizadas
        description_similarity = fuzz.partial_ratio(normalized_desc_a, normalized_desc_b)

        if description_similarity < self.MIN_DESCRIPTION_SIMILARITY:
            return False, 0.0

        # Calcular score final (0.0 a 1.0)
        # - Descrição: 70%
        # - Valor: 20%
        # - Data: 10%
        score = 0.0

        # Componente de descrição (70%)
        score += (description_similarity / 100.0) * 0.7

        # Componente de valor (20%)
        if amount_diff == 0:
            score += 0.2
        else:
            # Quanto menor a diferença, maior o score
            value_score = 1.0 - (amount_diff / self.MAX_TRANSACTION_AMOUNT_DIFF)
            score += value_score * 0.2

        # Componente de data (10%)
        if days_apart == 0:
            score += 0.1
        else:
            # Quanto menor a diferença, maior o score (usar tolerância apropriada)
            date_score = 1.0 - (days_apart / max_date_diff)
            score += date_score * 0.1

        return True, score

    def _suggest_duplicate_action(
        self,
        tx_a: Transaction,
        tx_b: Transaction,
    ) -> str:
        """
        Sugere ação para resolver duplicata.

        Retorna: "delete_a", "delete_b", ou "review"
        """
        # Se uma é de série e outra é avulsa, sugerir deletar a avulsa
        if tx_a.installment_series_id and not tx_b.installment_series_id:
            return "delete_b"  # Deletar a avulsa (tx_b)

        if tx_b.installment_series_id and not tx_a.installment_series_id:
            return "delete_a"  # Deletar a avulsa (tx_a)

        # Se ambas são de séries ou ambas avulsas, deletar a mais recente
        if tx_a.created_at and tx_b.created_at:
            if tx_a.created_at < tx_b.created_at:
                return "delete_b"  # Deletar a mais recente
            else:
                return "delete_a"

        # Se não conseguir decidir, pedir revisão manual
        return "review"

    def _calculate_similarity_score(
        self, series_a: InstallmentSeries, series_b: InstallmentSeries
    ) -> float:
        """
        Calcula score de similaridade entre duas séries (0.0 a 1.0).

        HARD RULES (bloqueiam comparação):
        1. Valores devem diferir em no máximo R$ 0,05 (diferença absoluta)
        2. Nome deve ter pelo menos 80% de palavras em comum
        3. Total de parcelas deve ser igual

        SOFT SCORING (se passar hard rules):
        - Merchant name (fuzzy) - peso 40%
        - Valor parcela - peso 30%
        - Total parcelas - peso 15%
        - Cartão crédito - peso 15%
        """

        # ============================================
        # HARD RULE 1: Amount Difference Check (ABSOLUTA)
        # ============================================
        if series_a.installment_amount and series_b.installment_amount:
            amount_a = float(series_a.installment_amount)
            amount_b = float(series_b.installment_amount)

            # Diferença absoluta em reais (não percentual)
            diff_absolute = abs(amount_a - amount_b)

            # Bloqueia se diferença > R$ 0,05 (5 centavos)
            if diff_absolute > self.MAX_AMOUNT_DIFFERENCE_BRL:
                return 0.0  # CRÍTICO: Retorna 0 imediatamente

        # ============================================
        # HARD RULE 2: Merchant Name Minimum Overlap
        # ============================================
        if series_a.merchant_name and series_b.merchant_name:
            norm_a = self.installment_service._normalize_merchant_name(series_a.merchant_name)
            norm_b = self.installment_service._normalize_merchant_name(series_b.merchant_name)

            words_a = set(norm_a.split())
            words_b = set(norm_b.split())

            if words_a and words_b:
                common = words_a & words_b
                total = max(len(words_a), len(words_b))
                name_overlap = len(common) / total if total > 0 else 0

                # Bloqueia se < 80% de sobreposição no nome
                if name_overlap < self.MIN_NAME_OVERLAP:
                    return 0.0  # Bloqueia matches ruins de nome

        # ============================================
        # HARD RULE 3: Installment Count Must Match
        # ============================================
        if series_a.installment_count != series_b.installment_count:
            return 0.0  # Número de parcelas deve ser idêntico

        # ============================================
        # SOFT SCORING (lógica existente)
        # ============================================
        score = 0.0

        # 1. Similaridade do nome (40%)
        if series_a.merchant_name and series_b.merchant_name:
            norm_a = self.installment_service._normalize_merchant_name(series_a.merchant_name)
            norm_b = self.installment_service._normalize_merchant_name(series_b.merchant_name)

            words_a = set(norm_a.split())
            words_b = set(norm_b.split())

            if words_a and words_b:
                common = words_a & words_b
                total = max(len(words_a), len(words_b))
                if total > 0:
                    name_score = len(common) / total
                    score += name_score * 0.4

        # 2. Similaridade do valor (30%)
        if series_a.installment_amount and series_b.installment_amount:
            amount_a = float(series_a.installment_amount)
            amount_b = float(series_b.installment_amount)

            # Diferença absoluta (já sabemos que é <= R$ 0,05 pelas hard rules)
            diff_absolute = abs(amount_a - amount_b)

            # Score baseado na diferença absoluta
            # R$ 0,00 = 100%, R$ 0,05 = 0%
            if diff_absolute <= self.MAX_AMOUNT_DIFFERENCE_BRL:
                amount_score = 1.0 - (diff_absolute / self.MAX_AMOUNT_DIFFERENCE_BRL)
                score += amount_score * 0.3

        # 3. Mesmo total de parcelas (15%)
        if series_a.installment_count == series_b.installment_count:
            score += 0.15

        # 4. Mesmo cartão de crédito (15%)
        if series_a.credit_card_id and series_b.credit_card_id:
            if series_a.credit_card_id == series_b.credit_card_id:
                score += 0.15
        elif not series_a.credit_card_id and not series_b.credit_card_id:
            # Ambos sem cartão (débito)
            score += 0.15

        return score

    async def _find_conflicts(
        self, series_a: InstallmentSeries, series_b: InstallmentSeries
    ) -> list[ConflictDetail]:
        """
        Encontra conflitos entre duas séries (parcelas duplicadas).

        Conflito = ambas séries têm transação para a mesma parcela N/M.
        """
        # Buscar transações de ambas séries
        result_a = await self.db.execute(
            select(Transaction).where(Transaction.installment_series_id == series_a.id)
        )
        transactions_a = {t.installment_number: t for t in result_a.scalars().all()}

        result_b = await self.db.execute(
            select(Transaction).where(Transaction.installment_series_id == series_b.id)
        )
        transactions_b = {t.installment_number: t for t in result_b.scalars().all()}

        # Encontrar parcelas que existem em ambas
        conflicts = []
        common_numbers = set(transactions_a.keys()) & set(transactions_b.keys())

        for num in sorted(common_numbers):
            tx_a = transactions_a[num]
            tx_b = transactions_b[num]

            conflicts.append(
                ConflictDetail(
                    installment_number=num,
                    series_a_transaction_id=tx_a.id,
                    series_a_date=tx_a.date,
                    series_b_transaction_id=tx_b.id,
                    series_b_date=tx_b.date,
                    description=f"Parcela {num}/{series_a.installment_count} existe em ambas as séries",
                )
            )

        return conflicts

    async def merge_series(
        self,
        user: User,
        source_id: int,
        target_id: int,
        conflict_resolution: str = "keep_oldest",
        new_merchant_name: str | None = None,
    ) -> InstallmentSeries:
        """
        Mescla duas séries.

        Operações em transação:
        1. Verifica conflitos (parcelas duplicadas)
        2. Resolve conflitos conforme estratégia
        3. Move transações de source para target
        4. Atualiza merchant_name se fornecido
        5. Marca source como MERGED
        6. Recalcula totalizadores
        """
        # Buscar séries
        source = await self._get_series(user, source_id)
        target = await self._get_series(user, target_id)

        if not source or not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Série não encontrada"
            )

        # Verificar conflitos
        conflicts = await self._find_conflicts(source, target)

        # Buscar todas transações da source
        result = await self.db.execute(
            select(Transaction).where(Transaction.installment_series_id == source_id)
        )
        source_transactions = list(result.scalars().all())

        # Processar conflitos
        for conflict in conflicts:
            if conflict_resolution == "keep_oldest":
                # Manter a mais antiga, deletar a mais recente
                tx_a_date = conflict.series_a_date
                tx_b_date = conflict.series_b_date

                if tx_a_date and tx_b_date:
                    if tx_a_date < tx_b_date:
                        # A é mais antiga, deletar B
                        tx_to_delete = next(
                            (
                                t
                                for t in source_transactions
                                if t.id == conflict.series_b_transaction_id
                            ),
                            None,
                        )
                    else:
                        # B é mais antiga, deletar A da target
                        result_del = await self.db.execute(
                            select(Transaction).where(
                                Transaction.id == conflict.series_a_transaction_id
                            )
                        )
                        tx_to_delete = result_del.scalar_one_or_none()

                    if tx_to_delete:
                        await self.db.delete(tx_to_delete)
                        # Remover da lista se for de source
                        if tx_to_delete in source_transactions:
                            source_transactions.remove(tx_to_delete)

            elif conflict_resolution == "keep_newest":
                # Inverso do keep_oldest
                tx_a_date = conflict.series_a_date
                tx_b_date = conflict.series_b_date

                if tx_a_date and tx_b_date:
                    if tx_a_date > tx_b_date:
                        # A é mais recente, deletar B
                        tx_to_delete = next(
                            (
                                t
                                for t in source_transactions
                                if t.id == conflict.series_b_transaction_id
                            ),
                            None,
                        )
                    else:
                        # B é mais recente, deletar A da target
                        result_del = await self.db.execute(
                            select(Transaction).where(
                                Transaction.id == conflict.series_a_transaction_id
                            )
                        )
                        tx_to_delete = result_del.scalar_one_or_none()

                    if tx_to_delete:
                        await self.db.delete(tx_to_delete)
                        if tx_to_delete in source_transactions:
                            source_transactions.remove(tx_to_delete)

            # keep_both: não deletar nada (manter ambas)

        # Mover transações restantes de source para target
        for tx in source_transactions:
            tx.installment_series_id = target_id

        # Atualizar merchant_name se fornecido
        if new_merchant_name:
            target.merchant_name = new_merchant_name
            target.description = new_merchant_name

        # Marcar source como MERGED
        source.status = InstallmentSeriesStatus.COMPLETED

        # Recalcular paid_count da target
        result_target = await self.db.execute(
            select(Transaction).where(
                and_(Transaction.installment_series_id == target_id, Transaction.is_paid == True)
            )
        )
        target.paid_count = len(list(result_target.scalars().all()))

        # Verificar se target está completa
        if target.paid_count >= target.installment_count:
            target.status = InstallmentSeriesStatus.COMPLETED

        await self.db.flush()
        await self.db.refresh(target)

        return target

    async def _get_series(self, user: User, series_id: int) -> InstallmentSeries | None:
        """Busca série do usuário"""
        result = await self.db.execute(
            select(InstallmentSeries).where(
                and_(
                    InstallmentSeries.id == series_id,
                    InstallmentSeries.user_id == user.id,
                )
            )
        )
        return result.scalar_one_or_none()
