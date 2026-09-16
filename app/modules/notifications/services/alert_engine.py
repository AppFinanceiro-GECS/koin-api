"""
Alert Engine - Detects financial events and generates notifications.

This service analyzes user data to detect important financial events:
- Invoice due dates approaching
- Budget thresholds exceeded
- Credit card limit warnings
- Goal milestones reached
- Low balance warnings
- Recurring transactions due
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utc_now
from app.models.account import Account
from app.models.budget import Budget, BudgetItem
from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import CreditCardInvoice, InvoiceStatus
from app.models.goal import Goal, GoalStatus
from app.models.notification import (
    Notification,
    NotificationPriority,
    NotificationType,
)
from app.models.recurring import RecurringStatus, RecurringTransaction
from app.models.transaction import Transaction
from app.models.user import User

from .notification_service import NotificationService


class AlertEngine:
    """Engine for detecting financial alerts and generating notifications."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notification_service = NotificationService(db)

    async def check_all_alerts_for_user(self, user: User) -> int:
        """
        Run all alert checks for a user.
        Returns the number of notifications created.
        """
        count = 0
        count += await self.check_invoice_due_dates(user)
        count += await self.check_budget_thresholds(user)
        count += await self.check_credit_card_limits(user)
        count += await self.check_goal_milestones(user)
        count += await self.check_low_balance(user)
        count += await self.check_recurring_due(user)
        count += await self.check_missing_invoices_start_of_month(user)
        count += await self.check_missing_invoices_pre_due(user)
        return count

    async def check_invoice_due_dates(self, user: User) -> int:
        """Check for invoices approaching due date."""
        today = date.today()
        count = 0

        # Get open invoices
        query = select(CreditCardInvoice).where(
            CreditCardInvoice.user_id == user.id,
            CreditCardInvoice.status == InvoiceStatus.OPEN.value,
            CreditCardInvoice.due_date >= today,
        )
        result = await self.db.execute(query)
        invoices = result.scalars().all()

        for invoice in invoices:
            days_until_due = (invoice.due_date - today).days

            # Check if notification already sent
            notification_type = None
            if days_until_due == 7:
                notification_type = NotificationType.INVOICE_DUE_7_DAYS
            elif days_until_due == 3:
                notification_type = NotificationType.INVOICE_DUE_3_DAYS
            elif days_until_due == 1:
                notification_type = NotificationType.INVOICE_DUE_1_DAY

            if notification_type:
                if not await self._notification_exists(
                    user.id, notification_type, "invoice", invoice.id
                ):
                    await self.notification_service.send_notification(
                        user_id=user.id,
                        notification_type=notification_type,
                        title=f"Fatura vence em {days_until_due} {'dia' if days_until_due == 1 else 'dias'}",
                        message=f"A fatura de R$ {invoice.total_amount:.2f} vence em {invoice.due_date.strftime('%d/%m')}.",
                        entity_type="invoice",
                        entity_id=invoice.id,
                        action_url=f"/invoices/{invoice.id}",
                        action_label="Ver fatura",
                        priority=NotificationPriority.HIGH
                        if days_until_due <= 3
                        else NotificationPriority.NORMAL,
                        icon="credit-card",
                        color="orange" if days_until_due > 1 else "red",
                    )
                    count += 1

        # Check overdue invoices
        overdue_query = select(CreditCardInvoice).where(
            CreditCardInvoice.user_id == user.id,
            CreditCardInvoice.status == InvoiceStatus.OPEN.value,
            CreditCardInvoice.due_date < today,
        )
        overdue_result = await self.db.execute(overdue_query)
        overdue_invoices = overdue_result.scalars().all()

        for invoice in overdue_invoices:
            if not await self._notification_exists(
                user.id, NotificationType.INVOICE_OVERDUE, "invoice", invoice.id
            ):
                days_overdue = (today - invoice.due_date).days
                await self.notification_service.send_notification(
                    user_id=user.id,
                    notification_type=NotificationType.INVOICE_OVERDUE,
                    title="Fatura vencida!",
                    message=f"A fatura de R$ {invoice.total_amount:.2f} está vencida há {days_overdue} {'dia' if days_overdue == 1 else 'dias'}.",
                    entity_type="invoice",
                    entity_id=invoice.id,
                    action_url=f"/invoices/{invoice.id}",
                    action_label="Pagar agora",
                    priority=NotificationPriority.URGENT,
                    icon="alert-triangle",
                    color="red",
                )
                count += 1

        return count

    async def check_budget_thresholds(self, user: User) -> int:
        """Check for budget thresholds exceeded."""
        today = date.today()
        count = 0

        # Get current month's budget
        query = select(Budget).where(
            Budget.user_id == user.id,
            Budget.year == today.year,
            Budget.month == today.month,
        )
        result = await self.db.execute(query)
        budget = result.scalar_one_or_none()

        if not budget:
            return 0

        # Get budget items with spending
        items_query = select(BudgetItem).where(BudgetItem.budget_id == budget.id)
        items_result = await self.db.execute(items_query)
        items = items_result.scalars().all()

        # Fetch ALL category spending in ONE query (instead of N queries)
        category_ids = [
            item.category_id for item in items if item.limit_amount > 0 and item.category_id
        ]
        spending_by_category: dict[int, Decimal] = {}
        if category_ids:
            spending_query = (
                select(
                    Transaction.category_id,
                    func.coalesce(func.sum(Transaction.amount), 0).label("spent"),
                )
                .where(
                    Transaction.user_id == user.id,
                    Transaction.category_id.in_(category_ids),
                    Transaction.type == "expense",
                    func.extract("year", Transaction.date) == today.year,
                    func.extract("month", Transaction.date) == today.month,
                )
                .group_by(Transaction.category_id)
            )
            spending_result = await self.db.execute(spending_query)
            spending_by_category = {row.category_id: row.spent for row in spending_result.all()}

        for item in items:
            if item.limit_amount <= 0:
                continue

            spent = spending_by_category.get(item.category_id, Decimal(0))

            percentage = float(spent / item.limit_amount * 100)

            if percentage >= 100:
                if not await self._notification_exists(
                    user.id, NotificationType.BUDGET_EXCEEDED, "budget_item", item.id
                ):
                    await self.notification_service.send_notification(
                        user_id=user.id,
                        notification_type=NotificationType.BUDGET_EXCEEDED,
                        title="Orçamento excedido!",
                        message=f"Você gastou R$ {spent:.2f} de R$ {item.limit_amount:.2f} em {item.category.name if item.category else 'uma categoria'}.",
                        entity_type="budget_item",
                        entity_id=item.id,
                        action_url="/budget",
                        action_label="Ver orçamento",
                        priority=NotificationPriority.HIGH,
                        icon="wallet",
                        color="red",
                    )
                    count += 1
            elif percentage >= 80:
                if not await self._notification_exists(
                    user.id, NotificationType.BUDGET_WARNING_80, "budget_item", item.id
                ):
                    await self.notification_service.send_notification(
                        user_id=user.id,
                        notification_type=NotificationType.BUDGET_WARNING_80,
                        title="Orçamento em 80%",
                        message=f"Você já gastou {percentage:.0f}% do orçamento em {item.category.name if item.category else 'uma categoria'}.",
                        entity_type="budget_item",
                        entity_id=item.id,
                        action_url="/budget",
                        action_label="Ver orçamento",
                        priority=NotificationPriority.NORMAL,
                        icon="wallet",
                        color="orange",
                    )
                    count += 1

        return count

    async def check_credit_card_limits(self, user: User) -> int:
        """Check for credit card limit warnings."""
        count = 0

        query = select(CreditCard).where(
            CreditCard.user_id == user.id,
            CreditCard.is_active == True,
        )
        result = await self.db.execute(query)
        cards = result.scalars().all()

        for card in cards:
            if not card.credit_limit or card.credit_limit <= 0:
                continue

            # Get current invoice total
            invoice_query = select(CreditCardInvoice).where(
                CreditCardInvoice.credit_card_id == card.id,
                CreditCardInvoice.status == InvoiceStatus.OPEN.value,
            )
            invoice_result = await self.db.execute(invoice_query)
            current_invoice = invoice_result.scalar_one_or_none()

            if not current_invoice:
                continue

            used = current_invoice.total_amount or Decimal(0)
            percentage = float(used / card.credit_limit * 100)

            if percentage >= 100:
                if not await self._notification_exists(
                    user.id, NotificationType.CREDIT_LIMIT_EXCEEDED, "credit_card", card.id
                ):
                    await self.notification_service.send_notification(
                        user_id=user.id,
                        notification_type=NotificationType.CREDIT_LIMIT_EXCEEDED,
                        title="Limite do cartão excedido!",
                        message=f"O cartão {card.name} excedeu o limite de R$ {card.credit_limit:.2f}.",
                        entity_type="credit_card",
                        entity_id=card.id,
                        action_url=f"/credit-cards/{card.id}",
                        action_label="Ver cartão",
                        priority=NotificationPriority.URGENT,
                        icon="credit-card",
                        color="red",
                    )
                    count += 1
            elif percentage >= 80:
                if not await self._notification_exists(
                    user.id, NotificationType.CREDIT_LIMIT_80, "credit_card", card.id
                ):
                    await self.notification_service.send_notification(
                        user_id=user.id,
                        notification_type=NotificationType.CREDIT_LIMIT_80,
                        title="Limite do cartão em 80%",
                        message=f"O cartão {card.name} está com {percentage:.0f}% do limite usado.",
                        entity_type="credit_card",
                        entity_id=card.id,
                        action_url=f"/credit-cards/{card.id}",
                        action_label="Ver cartão",
                        priority=NotificationPriority.NORMAL,
                        icon="credit-card",
                        color="orange",
                    )
                    count += 1

        return count

    async def check_goal_milestones(self, user: User) -> int:
        """Check for goal milestones reached."""
        count = 0

        query = select(Goal).where(
            Goal.user_id == user.id,
            Goal.status == GoalStatus.ACTIVE.value,
        )
        result = await self.db.execute(query)
        goals = result.scalars().all()

        for goal in goals:
            if goal.target_amount <= 0:
                continue

            percentage = float(goal.current_amount / goal.target_amount * 100)

            # Check milestones
            milestones = [
                (
                    100,
                    NotificationType.GOAL_ACHIEVED,
                    "Meta alcançada! 🎉",
                    NotificationPriority.HIGH,
                ),
                (
                    75,
                    NotificationType.GOAL_MILESTONE_75,
                    "75% da meta!",
                    NotificationPriority.NORMAL,
                ),
                (
                    50,
                    NotificationType.GOAL_MILESTONE_50,
                    "50% da meta!",
                    NotificationPriority.NORMAL,
                ),
                (25, NotificationType.GOAL_MILESTONE_25, "25% da meta!", NotificationPriority.LOW),
            ]

            for threshold, notification_type, title, priority in milestones:
                if percentage >= threshold:
                    if not await self._notification_exists(
                        user.id, notification_type, "goal", goal.id
                    ):
                        message = (
                            f"Parabéns! Você alcançou a meta '{goal.name}'!"
                            if threshold == 100
                            else f"Você atingiu {threshold}% da meta '{goal.name}'. Continue assim!"
                        )
                        await self.notification_service.send_notification(
                            user_id=user.id,
                            notification_type=notification_type,
                            title=title,
                            message=message,
                            entity_type="goal",
                            entity_id=goal.id,
                            action_url=f"/goals/{goal.id}",
                            action_label="Ver meta",
                            priority=priority,
                            icon="target",
                            color="green",
                        )
                        count += 1
                    break  # Only send the highest milestone not yet sent

        return count

    async def check_low_balance(self, user: User) -> int:
        """Check for low account balances."""
        count = 0
        low_balance_threshold = Decimal("100")  # R$ 100

        query = select(Account).where(
            Account.user_id == user.id,
            Account.is_active == True,
            Account.type.in_(["checking", "wallet"]),  # Only check main accounts
        )
        result = await self.db.execute(query)
        accounts = result.scalars().all()

        for account in accounts:
            if account.balance < low_balance_threshold:
                if not await self._notification_exists_today(
                    user.id, NotificationType.BALANCE_LOW, "account", account.id
                ):
                    await self.notification_service.send_notification(
                        user_id=user.id,
                        notification_type=NotificationType.BALANCE_LOW,
                        title="Saldo baixo",
                        message=f"A conta '{account.name}' está com saldo de R$ {account.balance:.2f}.",
                        entity_type="account",
                        entity_id=account.id,
                        action_url="/accounts",
                        action_label="Ver contas",
                        priority=NotificationPriority.NORMAL
                        if account.balance >= 0
                        else NotificationPriority.HIGH,
                        icon="alert-triangle",
                        color="orange" if account.balance >= 0 else "red",
                    )
                    count += 1

        return count

    async def check_recurring_due(self, user: User) -> int:
        """Check for recurring transactions due tomorrow."""
        tomorrow = date.today() + timedelta(days=1)
        count = 0

        query = select(RecurringTransaction).where(
            RecurringTransaction.user_id == user.id,
            RecurringTransaction.status == RecurringStatus.ACTIVE.value,
            RecurringTransaction.next_due_date == tomorrow,
        )
        result = await self.db.execute(query)
        recurrings = result.scalars().all()

        for recurring in recurrings:
            if not await self._notification_exists(
                user.id, NotificationType.RECURRING_DUE_TOMORROW, "recurring", recurring.id
            ):
                await self.notification_service.send_notification(
                    user_id=user.id,
                    notification_type=NotificationType.RECURRING_DUE_TOMORROW,
                    title="Lembrete: transação amanhã",
                    message=f"'{recurring.description}' de R$ {recurring.amount:.2f} vence amanhã.",
                    entity_type="recurring",
                    entity_id=recurring.id,
                    action_url="/recurring",
                    action_label="Ver recorrentes",
                    priority=NotificationPriority.NORMAL,
                    icon="calendar",
                    color="blue",
                )
                count += 1

        return count

    # === Faturas pendentes de carregamento ===

    # Delay base (em minutos) entre notificacoes no job de inicio de mes,
    # para espalhar a entrega de push e nao virar enxurrada no celular.
    _START_OF_MONTH_STAGGER_MINUTES = 5

    async def check_missing_invoices_start_of_month(self, user: User) -> int:
        """
        Lembrete "inicio do mes": para cada cartao cujo mes anterior ja fechou
        e a fatura ainda nao foi carregada, cria 1 notificacao (granular por cartao).

        So cria notificacoes no dia 1 do mes - em outros dias e no-op.
        As notificacoes sao escalonadas via scheduled_for para evitar burst de push.
        """
        today = date.today()
        if today.day != 1:
            return 0

        # Importacao local para evitar ciclo credit_cards <-> notifications
        from app.modules.credit_cards.services.expected_invoice_service import (
            ExpectedInvoiceService,
        )

        # Mes anterior
        prev_month_ref = today - timedelta(days=1)
        ref_year = prev_month_ref.year
        ref_month = prev_month_ref.month

        service = ExpectedInvoiceService(self.db)
        pending = await service.get_pending_for_user(user, ref_year, ref_month)

        count = 0
        now = utc_now()

        for idx, dto in enumerate(pending):
            if await self._missing_invoice_notification_exists(
                user_id=user.id,
                notification_type=NotificationType.INVOICE_MISSING_CURRENT,
                credit_card_id=dto.credit_card_id,
                reference_month=dto.reference_month,
                reference_year=dto.reference_year,
            ):
                continue

            scheduled_for = now + timedelta(minutes=idx * self._START_OF_MONTH_STAGGER_MINUTES)

            await self._create_missing_invoice_notification(
                user_id=user.id,
                notification_type=NotificationType.INVOICE_MISSING_CURRENT,
                title=f"Fatura de {self._month_name(ref_month)} não carregada",
                message=(
                    f"A fatura do seu {dto.credit_card_name} de "
                    f"{self._month_name(ref_month)}/{ref_year} ainda não foi carregada."
                ),
                dto=dto,
                scheduled_for=scheduled_for,
                priority=NotificationPriority.NORMAL,
                icon="file-warning",
                color="orange",
            )
            count += 1

        return count

    async def check_missing_invoices_pre_due(self, user: User) -> int:
        """
        Lembrete "pre-vencimento": para cada cartao cujo vencimento e daqui a 3 dias
        e a fatura ainda nao foi carregada, cria 1 notificacao urgente.

        Seguro de ser chamado diariamente - filtra internamente por due_date alvo.
        """
        # Importacao local para evitar ciclo
        from app.modules.credit_cards.services.expected_invoice_service import (
            ExpectedInvoiceService,
        )

        service = ExpectedInvoiceService(self.db)
        pending = await service.get_cards_due_in_days(user, days_ahead=3)

        count = 0
        for dto in pending:
            if await self._missing_invoice_notification_exists(
                user_id=user.id,
                notification_type=NotificationType.INVOICE_MISSING_PRE_DUE,
                credit_card_id=dto.credit_card_id,
                reference_month=dto.reference_month,
                reference_year=dto.reference_year,
            ):
                continue

            days_until_due = (dto.due_date - date.today()).days
            await self._create_missing_invoice_notification(
                user_id=user.id,
                notification_type=NotificationType.INVOICE_MISSING_PRE_DUE,
                title=f"{dto.credit_card_name} vence em {days_until_due} dias",
                message=(
                    f"Seu {dto.credit_card_name} vence em {days_until_due} dias "
                    f"({dto.due_date.strftime('%d/%m')}) e a fatura ainda não foi carregada. "
                    "Sem ela não dá pra conferir os lançamentos."
                ),
                dto=dto,
                priority=NotificationPriority.HIGH,
                icon="alert-triangle",
                color="red",
            )
            count += 1

        return count

    async def _create_missing_invoice_notification(
        self,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: str,
        dto,  # ExpectedInvoiceDTO
        priority: NotificationPriority,
        icon: str,
        color: str,
        scheduled_for: datetime | None = None,
    ) -> Notification:
        """
        Cria uma notificacao de "fatura pendente" usando credit_card como entity
        e armazenando ref_month/ref_year/trigger em extra_data (chave de dedup).

        Usa o modelo diretamente em vez de NotificationService.send_notification
        porque precisamos gravar extra_data e scheduled_for de forma consistente.
        """
        # Respeita preferencia do usuario (se desabilitou esse tipo, nao cria).
        preference = await self.notification_service._get_or_create_preference(
            user_id, notification_type
        )
        if preference.frequency == "disabled":
            return None

        notification = Notification(
            user_id=user_id,
            type=notification_type.value,
            title=title,
            message=message,
            icon=icon,
            color=color,
            priority=priority.value,
            entity_type="credit_card",
            entity_id=dto.credit_card_id,
            action_url=(
                f"/invoices?year={dto.reference_year}"
                f"&month={dto.reference_month}"
                f"&card={dto.credit_card_id}"
            ),
            action_label="Carregar fatura",
            scheduled_for=scheduled_for,
            extra_data={
                "ref_month": dto.reference_month,
                "ref_year": dto.reference_year,
                "trigger": notification_type.value,
                "due_date": dto.due_date.isoformat(),
            },
            sent_in_app=preference.in_app_enabled,
        )
        self.db.add(notification)
        await self.db.flush()
        return notification

    async def _missing_invoice_notification_exists(
        self,
        user_id: int,
        notification_type: NotificationType,
        credit_card_id: int,
        reference_month: int,
        reference_year: int,
    ) -> bool:
        """
        Dedup especifico para notificacoes de fatura pendente.
        Chave logica: (user, type, card_id, ref_month, ref_year).

        Considera apenas notificacoes ativas (nao dispensadas).
        """
        query = select(Notification).where(
            Notification.user_id == user_id,
            Notification.type == notification_type.value,
            Notification.entity_type == "credit_card",
            Notification.entity_id == credit_card_id,
            Notification.is_dismissed == False,  # noqa: E712
        )
        result = await self.db.execute(query)
        for notification in result.scalars().all():
            data = notification.extra_data or {}
            if data.get("ref_month") == reference_month and data.get("ref_year") == reference_year:
                return True
        return False

    @staticmethod
    def _month_name(month: int) -> str:
        names = [
            "Janeiro",
            "Fevereiro",
            "Março",
            "Abril",
            "Maio",
            "Junho",
            "Julho",
            "Agosto",
            "Setembro",
            "Outubro",
            "Novembro",
            "Dezembro",
        ]
        return names[month - 1]

    async def _notification_exists(
        self,
        user_id: int,
        notification_type: NotificationType,
        entity_type: str,
        entity_id: int,
    ) -> bool:
        """Check if a notification of this type already exists for the entity."""
        query = select(Notification).where(
            Notification.user_id == user_id,
            Notification.type == notification_type.value,
            Notification.entity_type == entity_type,
            Notification.entity_id == entity_id,
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

    async def _notification_exists_today(
        self,
        user_id: int,
        notification_type: NotificationType,
        entity_type: str,
        entity_id: int,
    ) -> bool:
        """Check if a notification was already sent today."""
        today_start = datetime.combine(date.today(), datetime.min.time())
        query = select(Notification).where(
            Notification.user_id == user_id,
            Notification.type == notification_type.value,
            Notification.entity_type == entity_type,
            Notification.entity_id == entity_id,
            Notification.created_at >= today_start,
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None
