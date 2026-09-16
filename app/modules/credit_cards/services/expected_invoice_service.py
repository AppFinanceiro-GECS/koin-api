"""
ExpectedInvoiceService - Single source of truth sobre "qual fatura o usuario DEVERIA ter".

Calcula faturas esperadas (a partir de closing_day/due_day de cada cartao ativo)
e cruza com as materializadas em credit_card_invoices para derivar um estado:

    - not_created          : closing_day ja passou, nao existe CreditCardInvoice
    - created_no_document  : existe, mas document_id IS NULL (fatura "fantasma/oca")
    - created_with_document: existe e tem PDF anexado
    - paid                 : fatura ja paga
    - future               : closing_day ainda nao chegou (ignorado em pendencias)

Este servico nao materializa nada no banco - os "fantasmas" sao DTOs em memoria.
E consumido por:
    - Endpoint GET /credit-cards/invoices/overview (tela de faturas)
    - AlertEngine (jobs de notificacao de faturas pendentes)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import CreditCardInvoice, InvoiceStatus
from app.models.user import User
from app.modules.credit_cards.services.invoice_service import InvoiceService


class ExpectedInvoiceState(str, Enum):
    NOT_CREATED = "not_created"
    CREATED_NO_DOCUMENT = "created_no_document"
    CREATED_WITH_DOCUMENT = "created_with_document"
    PAID = "paid"
    FUTURE = "future"


# Pendencias "ativas" - aparecem como problema a resolver na tela
PENDING_STATES = {
    ExpectedInvoiceState.NOT_CREATED,
    ExpectedInvoiceState.CREATED_NO_DOCUMENT,
}


@dataclass
class ExpectedInvoiceDTO:
    """Representa uma fatura esperada (materializada ou fantasma)."""

    credit_card_id: int
    credit_card_name: str
    reference_month: int
    reference_year: int
    closing_date: date
    due_date: date
    state: ExpectedInvoiceState

    # Somente quando materializada
    invoice_id: int | None = None
    document_id: int | None = None
    total_amount: Decimal | None = None
    paid_amount: Decimal | None = None
    status: str | None = None

    @property
    def is_pending(self) -> bool:
        return self.state in PENDING_STATES

    @property
    def is_phantom(self) -> bool:
        return self.invoice_id is None


class ExpectedInvoiceService:
    """Deriva o conjunto de faturas esperadas x materializadas."""

    # Janela de tolerancia: cartao inativo ha mais de N dias e ignorado
    INACTIVE_GRACE_DAYS = 90

    # Janela de supressao: se closing_day foi editado recentemente, nao notifica
    # nem lista como pendente no mes da mudanca (evita falso positivo)
    CYCLE_CHANGE_SUPPRESS_DAYS = 30

    def __init__(self, db: AsyncSession):
        self.db = db
        self._invoice_service = InvoiceService(db)

    # -------- API publica --------

    async def get_overview(
        self,
        user: User,
        year: int,
        month: int,
    ) -> list[ExpectedInvoiceDTO]:
        """
        Retorna todas as faturas esperadas (materializadas + fantasmas)
        de um determinado mes de referencia para o usuario.

        Usado pelo endpoint da tela de faturas.
        """
        cards = await self._list_active_cards(user.id)
        invoices_map = await self._load_invoices_map(
            user.id, [(year, month)], [c.id for c in cards]
        )

        result: list[ExpectedInvoiceDTO] = []
        today = date.today()

        for card in cards:
            if not self._card_is_eligible_for_month(card, year, month, today):
                continue

            dto = self._build_dto(card, year, month, invoices_map, today)
            if dto is not None:
                result.append(dto)

        return result

    async def get_pending_for_user(
        self,
        user: User,
        reference_year: int,
        reference_month: int,
        include_states: Iterable[ExpectedInvoiceState] | None = None,
    ) -> list[ExpectedInvoiceDTO]:
        """
        Retorna apenas faturas pendentes (not_created e/ou created_no_document)
        de um mes especifico.

        Usado pelos jobs de notificacao.
        """
        states = set(include_states) if include_states else set(PENDING_STATES)
        overview = await self.get_overview(user, reference_year, reference_month)
        return [dto for dto in overview if dto.state in states]

    async def get_cards_due_in_days(
        self,
        user: User,
        days_ahead: int,
    ) -> list[ExpectedInvoiceDTO]:
        """
        Retorna faturas pendentes cujo vencimento e hoje + days_ahead.
        Usado pelo job de pre-vencimento.

        Calcula o mes de referencia a partir da data do vencimento esperado.
        """
        target_date = date.today() + timedelta(days=days_ahead)
        cards = await self._list_active_cards(user.id)

        results: list[ExpectedInvoiceDTO] = []
        today = date.today()

        for card in cards:
            # Descobrir qual (ref_month, ref_year) tem due_date == target_date
            ref = self._find_reference_for_due_date(card, target_date)
            if ref is None:
                continue

            ref_year, ref_month = ref
            if not self._card_is_eligible_for_month(card, ref_year, ref_month, today):
                continue

            invoices_map = await self._load_invoices_map(
                user.id, [(ref_year, ref_month)], [card.id]
            )
            dto = self._build_dto(card, ref_year, ref_month, invoices_map, today)
            if dto is not None and dto.is_pending:
                results.append(dto)

        return results

    # -------- Helpers internos --------

    async def _list_active_cards(self, user_id: int) -> list[CreditCard]:
        query = select(CreditCard).where(
            CreditCard.user_id == user_id,
            CreditCard.is_active == True,  # noqa: E712
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _load_invoices_map(
        self,
        user_id: int,
        periods: list[tuple[int, int]],
        card_ids: list[int],
    ) -> dict[tuple[int, int, int], CreditCardInvoice]:
        """
        Carrega as faturas materializadas para os (card, ano, mes) solicitados.
        Retorna dict {(card_id, year, month): CreditCardInvoice}.
        """
        if not card_ids or not periods:
            return {}

        ors = []
        for year, month in periods:
            ors.append(
                and_(
                    CreditCardInvoice.reference_year == year,
                    CreditCardInvoice.reference_month == month,
                )
            )

        from sqlalchemy import or_

        query = select(CreditCardInvoice).where(
            CreditCardInvoice.user_id == user_id,
            CreditCardInvoice.credit_card_id.in_(card_ids),
            or_(*ors),
        )
        result = await self.db.execute(query)
        invoices = result.scalars().all()

        return {
            (inv.credit_card_id, inv.reference_year, inv.reference_month): inv for inv in invoices
        }

    def _card_is_eligible_for_month(
        self,
        card: CreditCard,
        year: int,
        month: int,
        today: date,
    ) -> bool:
        """
        Decide se um cartao deve ser considerado para aquele mes de referencia.

        Regras (defensivas, para evitar falsos positivos):
          - Cartao criado DEPOIS do inicio do mes de referencia -> ignora
            (o cartao nem existia naquele mes)
          - Cartao inativo ha mais de INACTIVE_GRACE_DAYS -> ignora
            (ja se passou tempo suficiente, assume que nao tem mais pendencia)
          - Cartao com closing_day/updated_at editado nos ultimos
            CYCLE_CHANGE_SUPPRESS_DAYS E mes de referencia = mes atual -> suprime
            (evita falso positivo quando o usuario acabou de mudar o ciclo)
        """
        # 1. Criado depois do mes de referencia
        if card.created_at and card.created_at.date() > self._end_of_month(year, month):
            return False

        # 2. Inativo ha muito tempo
        if not card.is_active:
            if card.updated_at and (today - card.updated_at.date()).days > self.INACTIVE_GRACE_DAYS:
                return False

        # 3. Ciclo alterado recentemente e estamos olhando o mes atual
        if card.updated_at:
            days_since_update = (today - card.updated_at.date()).days
            is_current_month = year == today.year and month == today.month
            if is_current_month and days_since_update <= self.CYCLE_CHANGE_SUPPRESS_DAYS:
                # Heuristica conservadora: nao podemos saber *qual* campo mudou
                # sem historico, entao so suprimimos se a regra apertar.
                # Na pratica: suprimir apenas se o fechamento ainda nao ocorreu
                # OU se ocorreu ha menos de 3 dias (janela de ajuste).
                dates = self._invoice_service.calculate_invoice_dates(card, month, year)
                days_since_closing = (today - dates["closing_date"]).days
                if 0 <= days_since_closing <= 3:
                    return False

        return True

    def _build_dto(
        self,
        card: CreditCard,
        year: int,
        month: int,
        invoices_map: dict[tuple[int, int, int], CreditCardInvoice],
        today: date,
    ) -> ExpectedInvoiceDTO | None:
        """Monta o DTO com o estado derivado."""
        dates = self._invoice_service.calculate_invoice_dates(card, month, year)
        closing_date = dates["closing_date"]
        due_date = dates["due_date"]

        invoice = invoices_map.get((card.id, year, month))
        state = self._derive_state(invoice, closing_date, today)

        # Se for fatura futura e nao estamos explicitamente pedindo mes futuro,
        # ainda assim devolvemos (a UI pode querer mostrar) - cabe ao consumidor filtrar.

        card_name = card.nickname or card.bank_id or f"Cartão {card.last_four_digits or card.id}"

        return ExpectedInvoiceDTO(
            credit_card_id=card.id,
            credit_card_name=card_name,
            reference_month=month,
            reference_year=year,
            closing_date=closing_date,
            due_date=due_date,
            state=state,
            invoice_id=invoice.id if invoice else None,
            document_id=invoice.document_id if invoice else None,
            total_amount=invoice.total_amount if invoice else None,
            paid_amount=invoice.paid_amount if invoice else None,
            status=invoice.status if invoice else None,
        )

    def _derive_state(
        self,
        invoice: CreditCardInvoice | None,
        closing_date: date,
        today: date,
    ) -> ExpectedInvoiceState:
        if invoice is None:
            if today < closing_date:
                return ExpectedInvoiceState.FUTURE
            return ExpectedInvoiceState.NOT_CREATED

        if invoice.status == InvoiceStatus.PAID.value:
            return ExpectedInvoiceState.PAID

        if invoice.document_id is None:
            if today < closing_date:
                # Existe linha (talvez criada por transacao avulsa) mas ainda nao fechou
                return ExpectedInvoiceState.FUTURE
            return ExpectedInvoiceState.CREATED_NO_DOCUMENT

        return ExpectedInvoiceState.CREATED_WITH_DOCUMENT

    def _find_reference_for_due_date(
        self,
        card: CreditCard,
        target_due_date: date,
    ) -> tuple[int, int] | None:
        """
        Dada uma data de vencimento alvo, descobre qual (ref_year, ref_month)
        produz exatamente esse due_date para o cartao.

        Estrategia: testa o mes do target_due_date e o anterior
        (due_day pode estar no mes seguinte ao closing).
        """
        candidates = [
            (target_due_date.year, target_due_date.month),
        ]
        prev = target_due_date - relativedelta(months=1)
        candidates.append((prev.year, prev.month))

        for year, month in candidates:
            dates = self._invoice_service.calculate_invoice_dates(card, month, year)
            if dates["due_date"] == target_due_date:
                return (year, month)

        return None

    @staticmethod
    def _end_of_month(year: int, month: int) -> date:
        next_month_start = date(year, month, 1) + relativedelta(months=1)
        return next_month_start - timedelta(days=1)
