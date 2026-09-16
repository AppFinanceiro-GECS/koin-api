"""Serviço para detectar transações recorrentes em itens extraídos de faturas"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recurring import RecurringStatus, RecurringTransaction
from app.models.user import User
from app.modules.known_services.models.known_service import KnownRecurringService
from app.modules.known_services.schemas.recurring_detection import (
    DuplicateAnalysis,
    DuplicateType,
    RecurringDetection,
    RecurringSuggestion,
)


class RecurringDetectorService:
    """Detecta e enriquece itens extraídos com informações de recorrência"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._known_services_cache: list[KnownRecurringService] | None = None

    async def detect_all(
        self,
        user: User,
        items: list[dict],
        invoice_month: int | None = None,
        invoice_year: int | None = None,
    ) -> list[dict]:
        """
        Analisa todos os itens e adiciona recurring_detection a cada um.

        Args:
            user: Usuário atual
            items: Lista de itens extraídos da fatura
            invoice_month: Mês de referência da fatura (para análise de duplicidade)
            invoice_year: Ano de referência da fatura

        Returns:
            Lista de itens com recurring_detection preenchido
        """
        # Carregar dados necessários
        known_services = await self._get_known_services()
        user_recurrings = await self._get_user_recurrings(user)

        # Agrupar itens por descrição normalizada (para análise de duplicidade)
        items_by_description = self._group_items_by_description(items)

        # Processar cada item
        for item in items:
            detection = await self._detect_single(
                item=item,
                known_services=known_services,
                user_recurrings=user_recurrings,
                items_by_description=items_by_description,
                invoice_month=invoice_month,
                invoice_year=invoice_year,
            )
            item["recurring_detection"] = detection.model_dump() if detection else None

        return items

    async def _detect_single(
        self,
        item: dict,
        known_services: list[KnownRecurringService],
        user_recurrings: list[RecurringTransaction],
        items_by_description: dict[str, list[dict]],
        invoice_month: int | None,
        invoice_year: int | None,
    ) -> RecurringDetection | None:
        """Detecta recorrência para um único item"""
        description = item.get("description", "")
        amount = item.get("amount", 0)
        item_date = item.get("date")

        # Ignorar itens que não são compras (pagamentos, créditos, etc.)
        transaction_type = item.get("transaction_type", "compra")
        if transaction_type not in ["compra", "anuidade"]:
            return None

        # 1. Verificar se é um serviço conhecido
        known_service = self._match_known_service(description, known_services)

        # 2. Verificar se o usuário já tem esta recorrência cadastrada
        user_recurring = self._match_user_recurring(
            description, amount, user_recurrings, known_service
        )

        # 3. Analisar duplicidade
        duplicate_analysis = self._analyze_duplicates(
            item=item,
            items_by_description=items_by_description,
        )

        # 4. Montar sugestão se for serviço conhecido mas não cadastrado
        suggestion = None
        if known_service and not user_recurring:
            day_of_month = None
            if item_date:
                try:
                    if isinstance(item_date, str):
                        parsed_date = datetime.strptime(item_date, "%Y-%m-%d")
                        day_of_month = parsed_date.day
                    elif isinstance(item_date, date):
                        day_of_month = item_date.day
                except ValueError:
                    pass

            suggestion = RecurringSuggestion(
                name=known_service.name,
                amount=amount,
                frequency=known_service.default_frequency,
                default_category=known_service.default_category,
                day_of_month=day_of_month,
            )

        # 5. Calcular confiança
        confidence = self._calculate_confidence(
            known_service=known_service,
            user_recurring=user_recurring,
            description=description,
        )

        # Se não encontrou nada relevante, retornar None
        if not known_service and not user_recurring:
            return None

        return RecurringDetection(
            is_known_service=known_service is not None,
            known_service_id=known_service.id if known_service else None,
            known_service_name=known_service.name if known_service else None,
            is_user_recurring=user_recurring is not None,
            user_recurring_id=user_recurring.id if user_recurring else None,
            user_recurring_name=user_recurring.name if user_recurring else None,
            duplicate_analysis=duplicate_analysis,
            suggested_recurring=suggestion,
            confidence=confidence,
        )

    def _match_known_service(
        self,
        description: str,
        known_services: list[KnownRecurringService],
    ) -> KnownRecurringService | None:
        """Verifica se a descrição corresponde a um serviço conhecido"""
        description_upper = description.upper()

        for service in known_services:
            for pattern in service.patterns:
                # Suporta wildcards (* no final)
                if pattern.endswith("*"):
                    if description_upper.startswith(pattern[:-1]):
                        return service
                elif pattern in description_upper:
                    return service

        return None

    def _match_user_recurring(
        self,
        description: str,
        amount: float,
        user_recurrings: list[RecurringTransaction],
        known_service: KnownRecurringService | None = None,
    ) -> RecurringTransaction | None:
        """Verifica se o usuário já tem esta recorrência cadastrada.

        Verifica em ordem:
        1. Se é um serviço conhecido, verifica se existe recorrência com mesmo nome do serviço
        2. Match por descrição similar ao nome da recorrência (com validação de valor)
        3. Match por descrição similar à descrição da recorrência (com validação de valor)
        """
        description_normalized = self._normalize_description(description)

        for recurring in user_recurrings:
            recurring_name_normalized = self._normalize_description(recurring.name)

            # Match por serviço conhecido: se detectamos "OPENAI" como ChatGPT Plus,
            # e usuário já tem uma recorrência chamada "ChatGPT Plus", é match!
            if known_service:
                known_service_name_normalized = self._normalize_description(known_service.name)
                if recurring_name_normalized == known_service_name_normalized:
                    # Validar valor se disponível
                    if self._amount_matches(amount, recurring.amount):
                        return recurring
                # Também verifica se o nome da recorrência contém o nome do serviço conhecido
                if self._descriptions_match(
                    recurring_name_normalized, known_service_name_normalized
                ):
                    if self._amount_matches(amount, recurring.amount):
                        return recurring

            # Match por nome similar (descrição da fatura vs nome da recorrência)
            # IMPORTANTE: Agora também valida o valor para evitar falsos positivos
            if self._descriptions_match(description_normalized, recurring_name_normalized):
                if self._amount_matches(amount, recurring.amount):
                    return recurring

            # Match por descrição similar (se tiver)
            if recurring.description:
                recurring_desc_normalized = self._normalize_description(recurring.description)
                if self._descriptions_match(description_normalized, recurring_desc_normalized):
                    if self._amount_matches(amount, recurring.amount):
                        return recurring

        return None

    def _amount_matches(self, amount1: float, amount2: float | None) -> bool:
        """Verifica se dois valores são similares o suficiente.

        Considera match se:
        - Valores são exatamente iguais
        - Diferença é menor que 10% OU menor que R$ 5,00
        - amount2 é None (não há valor cadastrado para comparar)
        """
        if amount2 is None:
            return True  # Sem valor cadastrado, aceitar

        # Converter ambos para float para evitar TypeError com Decimal
        amount1_float = float(amount1)
        amount2_float = float(amount2)

        # Valores exatos
        if abs(amount1_float - amount2_float) < 0.01:
            return True

        # Diferença percentual
        max_amount = max(abs(amount1_float), abs(amount2_float))
        if max_amount > 0:
            diff_percentage = abs(amount1_float - amount2_float) / max_amount
            if diff_percentage <= 0.10:  # 10% de tolerância
                return True

        # Diferença absoluta pequena (até R$ 5,00)
        if abs(amount1_float - amount2_float) <= 5.0:
            return True

        return False

    def _analyze_duplicates(
        self,
        item: dict,
        items_by_description: dict[str, list[dict]],
    ) -> DuplicateAnalysis | None:
        """Analisa se há duplicidade no período"""
        description = item.get("description", "")
        amount = item.get("amount", 0)
        item_date_str = item.get("date")

        # Normalizar descrição para agrupamento
        desc_key = self._normalize_description(description)

        # Buscar outras ocorrências com descrição similar
        similar_items = items_by_description.get(desc_key, [])

        # Se só tem 1 (o próprio item), não há duplicidade
        if len(similar_items) <= 1:
            return DuplicateAnalysis(
                duplicate_type=DuplicateType.NONE,
                reason="Única ocorrência no período",
                occurrences_count=1,
            )

        # Analisar as outras ocorrências
        other_amounts = [i["amount"] for i in similar_items if i is not item]
        occurrences_count = len(similar_items)

        # Caso 1: Valores diferentes → provavelmente 2 assinaturas diferentes
        if all(abs(other - amount) > 5.0 for other in other_amounts):
            return DuplicateAnalysis(
                duplicate_type=DuplicateType.LEGITIMATE,
                reason="Valores diferentes - provavelmente assinaturas distintas",
                occurrences_count=occurrences_count,
                other_amounts=other_amounts,
            )

        # Caso 2: Mais de 2 cobranças → muito suspeito
        if occurrences_count > 2:
            return DuplicateAnalysis(
                duplicate_type=DuplicateType.ERROR,
                reason=f"Múltiplas cobranças ({occurrences_count}x) - provável erro",
                occurrences_count=occurrences_count,
                other_amounts=other_amounts,
            )

        # Caso 3: 2 cobranças com valores iguais - verificar datas
        item_date = self._parse_date(item_date_str)
        for other_item in similar_items:
            if other_item is item:
                continue

            other_date = self._parse_date(other_item.get("date"))
            other_amount = other_item.get("amount", 0)

            # Valores iguais e datas próximas (<7 dias) → suspeito
            if abs(other_amount - amount) < 1.0:
                if item_date and other_date:
                    days_diff = abs((item_date - other_date).days)
                    if days_diff <= 7:
                        return DuplicateAnalysis(
                            duplicate_type=DuplicateType.SUSPICIOUS,
                            reason=f"Valores iguais com {days_diff} dias de diferença",
                            occurrences_count=occurrences_count,
                            other_amounts=other_amounts,
                        )
                else:
                    # Sem data, assume suspeito por segurança
                    return DuplicateAnalysis(
                        duplicate_type=DuplicateType.SUSPICIOUS,
                        reason="Valores iguais no mesmo período (datas indisponíveis)",
                        occurrences_count=occurrences_count,
                        other_amounts=other_amounts,
                    )

        # Caso 4: 2 cobranças com valores iguais mas datas distantes → legítimo
        return DuplicateAnalysis(
            duplicate_type=DuplicateType.LEGITIMATE,
            reason="Ciclos de cobrança diferentes",
            occurrences_count=occurrences_count,
            other_amounts=other_amounts,
        )

    def _calculate_confidence(
        self,
        known_service: KnownRecurringService | None,
        user_recurring: RecurringTransaction | None,
        description: str,
    ) -> float:
        """Calcula a confiança da detecção"""
        if user_recurring and known_service:
            # Match perfeito: serviço conhecido + recorrência cadastrada
            return 0.99

        if user_recurring:
            # Apenas recorrência cadastrada (sem serviço conhecido)
            # Confiança menor pois pode ser match incorreto por similaridade
            return 0.85

        if known_service:
            # Verificar quão bem o padrão combina
            description_upper = description.upper()
            for pattern in known_service.patterns:
                if pattern.endswith("*"):
                    if description_upper.startswith(pattern[:-1]):
                        return 0.95
                elif pattern == description_upper:
                    return 0.98
                elif pattern in description_upper:
                    return 0.90

        return 0.0

    def _normalize_description(self, description: str) -> str:
        """Normaliza descrição para comparação"""
        # Remove caracteres especiais, converte para maiúsculas
        normalized = re.sub(r"[^A-Za-z0-9]", "", description.upper())
        return normalized

    def _descriptions_match(self, desc1: str, desc2: str) -> bool:
        """Verifica se duas descrições são similares o suficiente"""
        # Match exato após normalização
        if desc1 == desc2:
            return True

        # Ambas as descrições devem ter pelo menos 4 caracteres
        if len(desc1) < 4 or len(desc2) < 4:
            return False

        # Um contém o outro - MAS com threshold mínimo
        # Para evitar falsos positivos, o menor deve ter pelo menos 60% do tamanho do maior
        shorter = min(desc1, desc2, key=len)
        longer = max(desc1, desc2, key=len)

        # Se a string menor é muito pequena em relação à maior, não considerar match
        size_ratio = len(shorter) / len(longer) if len(longer) > 0 else 0
        if size_ratio < 0.6:
            return False

        # Agora verifica se um contém o outro
        if shorter in longer:
            return True

        return False

    def _group_items_by_description(self, items: list[dict]) -> dict[str, list[dict]]:
        """Agrupa itens por descrição normalizada"""
        groups: dict[str, list[dict]] = defaultdict(list)

        for item in items:
            description = item.get("description", "")
            # Extrair parte principal da descrição (sem sufixos numéricos)
            desc_key = self._normalize_description(description)

            # Remove apenas sufixos numéricos de parcelamento (ex: "02/06", "04/12")
            # mas mantém o resto da descrição intacta
            desc_key = re.sub(r"\d{2}\d{2}$", "", desc_key)  # Remove padrões como "0206", "0412"

            groups[desc_key].append(item)

        return groups

    def _parse_date(self, date_str: str | None) -> date | None:
        """Converte string de data para objeto date"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None

    async def _get_known_services(self) -> list[KnownRecurringService]:
        """Carrega serviços conhecidos do banco (com cache)"""
        if self._known_services_cache is None:
            result = await self.db.execute(
                select(KnownRecurringService).where(KnownRecurringService.is_active == True)
            )
            self._known_services_cache = list(result.scalars().all())
        return self._known_services_cache

    async def _get_user_recurrings(self, user: User) -> list[RecurringTransaction]:
        """Carrega recorrências cadastradas do usuário"""
        result = await self.db.execute(
            select(RecurringTransaction).where(
                RecurringTransaction.user_id == user.id,
                RecurringTransaction.status != RecurringStatus.CANCELLED.value,
            )
        )
        return list(result.scalars().all())
