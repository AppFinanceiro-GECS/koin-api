from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utc_now
from app.models.notification import (
    Notification,
    NotificationPreference,
    NotificationPriority,
    NotificationSettings,
    NotificationType,
    PushSubscription,
)
from app.models.user import User
from app.modules.notifications.schemas.notification import (
    NOTIFICATION_TYPE_INFO,
    NotificationCreate,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    NotificationPreferenceWithDefaults,
    NotificationResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    NotificationSummary,
    PushSubscriptionCreate,
    PushSubscriptionResponse,
    UnreadCountResponse,
)


class NotificationService:
    """Service for managing notifications."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # === Notification CRUD ===

    async def list_notifications(
        self,
        user: User,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
        notification_type: NotificationType | None = None,
    ) -> list[NotificationResponse]:
        """List notifications for a user."""
        query = select(Notification).where(
            Notification.user_id == user.id,
            Notification.is_dismissed == False,
        )

        if unread_only:
            query = query.where(Notification.is_read == False)

        if notification_type:
            query = query.where(Notification.type == notification_type.value)

        query = query.order_by(Notification.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        notifications = result.scalars().all()

        return [self._build_notification_response(n) for n in notifications]

    async def get_notification(
        self, user: User, notification_id: int
    ) -> NotificationResponse | None:
        """Get a single notification."""
        query = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
        result = await self.db.execute(query)
        notification = result.scalar_one_or_none()

        if not notification:
            return None

        return self._build_notification_response(notification)

    async def create_notification(
        self,
        user: User,
        data: NotificationCreate,
    ) -> Notification:
        """Create a new notification."""
        notification = Notification(
            user_id=user.id,
            type=data.type.value,
            title=data.title,
            message=data.message,
            icon=data.icon,
            color=data.color,
            priority=data.priority.value,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            action_url=data.action_url,
            action_label=data.action_label,
            scheduled_for=data.scheduled_for,
            extra_data=data.metadata,
            sent_in_app=True,
        )
        self.db.add(notification)
        await self.db.flush()
        return notification

    async def send_notification(
        self,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: str,
        entity_type: str | None = None,
        entity_id: int | None = None,
        action_url: str | None = None,
        action_label: str | None = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        icon: str | None = None,
        color: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Notification:
        """
        Send a notification to a user.
        Checks user preferences before sending.
        """
        # Check if user wants this type of notification
        preference = await self._get_or_create_preference(user_id, notification_type)

        if preference.frequency == "disabled":
            return None

        # Create the notification
        notification = Notification(
            user_id=user_id,
            type=notification_type.value,
            title=title,
            message=message,
            icon=icon,
            color=color,
            priority=priority.value,
            entity_type=entity_type,
            entity_id=entity_id,
            action_url=action_url,
            action_label=action_label,
            metadata=metadata,
        )

        # Check which channels to use
        if preference.in_app_enabled:
            notification.sent_in_app = True

        # Email and push will be handled by background tasks
        # For now, just mark the notification

        self.db.add(notification)
        await self.db.flush()

        return notification

    async def mark_as_read(self, user: User, notification_id: int) -> NotificationResponse | None:
        """Mark a notification as read."""
        query = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
        result = await self.db.execute(query)
        notification = result.scalar_one_or_none()

        if not notification:
            return None

        notification.is_read = True
        notification.read_at = utc_now()
        await self.db.flush()

        return self._build_notification_response(notification)

    async def mark_all_as_read(self, user: User) -> int:
        """Mark all notifications as read. Returns count of updated notifications."""
        stmt = (
            update(Notification)
            .where(
                Notification.user_id == user.id,
                Notification.is_read == False,
            )
            .values(is_read=True, read_at=utc_now())
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount

    async def resolve_pending_for_invoice(
        self,
        user_id: int,
        credit_card_id: int,
        reference_month: int,
        reference_year: int,
    ) -> int:
        """
        Marca como dispensadas todas as notificacoes de "fatura pendente"
        (INVOICE_MISSING_CURRENT e INVOICE_MISSING_PRE_DUE) que correspondem
        a uma fatura especifica que acabou de ser carregada.

        Chamada apos um documento ser anexado a uma fatura (fecha o loop UX:
        o usuario sobe o PDF e o lembrete some automaticamente).

        Retorna o numero de notificacoes marcadas como dispensadas.
        """
        # Busca notificacoes ativas dos tipos "missing" para este cartao
        # cuja extra_data aponta para o (ref_month, ref_year) alvo.
        query = select(Notification).where(
            Notification.user_id == user_id,
            Notification.is_dismissed == False,
            Notification.type.in_(
                [
                    NotificationType.INVOICE_MISSING_CURRENT.value,
                    NotificationType.INVOICE_MISSING_PRE_DUE.value,
                ]
            ),
            Notification.entity_type == "credit_card",
            Notification.entity_id == credit_card_id,
        )
        result = await self.db.execute(query)
        candidates = result.scalars().all()

        dismissed = 0
        now = utc_now()
        for notification in candidates:
            data = notification.extra_data or {}
            if data.get("ref_month") == reference_month and data.get("ref_year") == reference_year:
                notification.is_dismissed = True
                notification.dismissed_at = now
                dismissed += 1

        if dismissed:
            await self.db.flush()

        return dismissed

    async def dismiss_notification(self, user: User, notification_id: int) -> bool:
        """Dismiss (soft delete) a notification."""
        query = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
        result = await self.db.execute(query)
        notification = result.scalar_one_or_none()

        if not notification:
            return False

        notification.is_dismissed = True
        notification.dismissed_at = utc_now()
        await self.db.flush()

        return True

    async def get_unread_count(self, user: User) -> UnreadCountResponse:
        """Get count of unread notifications."""
        # Total unread
        unread_query = select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.is_read == False,
            Notification.is_dismissed == False,
        )
        unread_result = await self.db.execute(unread_query)
        unread_count = unread_result.scalar() or 0

        # High priority unread
        high_priority_query = select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.is_read == False,
            Notification.is_dismissed == False,
            Notification.priority.in_(["high", "urgent"]),
        )
        high_result = await self.db.execute(high_priority_query)
        high_priority_count = high_result.scalar() or 0

        return UnreadCountResponse(
            unread_count=unread_count,
            high_priority_count=high_priority_count,
        )

    async def get_summary(self, user: User) -> NotificationSummary:
        """Get notification summary for a user."""
        # Total count
        total_query = select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.is_dismissed == False,
        )
        total_result = await self.db.execute(total_query)
        total_count = total_result.scalar() or 0

        # Unread count
        unread_response = await self.get_unread_count(user)

        # Recent notifications
        recent = await self.list_notifications(user, limit=5)

        return NotificationSummary(
            total_count=total_count,
            unread_count=unread_response.unread_count,
            high_priority_count=unread_response.high_priority_count,
            recent_notifications=recent,
        )

    # === Notification Preferences ===

    async def list_preferences(self, user: User) -> list[NotificationPreferenceWithDefaults]:
        """List all notification preferences with defaults."""
        # Get existing preferences
        query = select(NotificationPreference).where(NotificationPreference.user_id == user.id)
        result = await self.db.execute(query)
        existing = {p.notification_type: p for p in result.scalars().all()}

        # Build list with all types
        preferences = []
        for notification_type in NotificationType:
            type_info = NOTIFICATION_TYPE_INFO.get(notification_type, {})

            if notification_type in existing:
                pref = existing[notification_type]
                preferences.append(
                    NotificationPreferenceWithDefaults(
                        notification_type=notification_type.value,
                        type_label=type_info.get("label", notification_type.value),
                        type_description=type_info.get("description", ""),
                        in_app_enabled=pref.in_app_enabled,
                        email_enabled=pref.email_enabled,
                        push_enabled=pref.push_enabled,
                        frequency=pref.frequency,
                        custom_threshold=pref.custom_threshold,
                        days_before=pref.days_before,
                        is_customized=True,
                    )
                )
            else:
                preferences.append(
                    NotificationPreferenceWithDefaults(
                        notification_type=notification_type.value,
                        type_label=type_info.get("label", notification_type.value),
                        type_description=type_info.get("description", ""),
                        in_app_enabled=True,
                        email_enabled=True,
                        push_enabled=True,
                        frequency="immediate",
                        custom_threshold=type_info.get("default_threshold"),
                        days_before=type_info.get("default_days_before"),
                        is_customized=False,
                    )
                )

        return preferences

    async def get_preference(
        self, user: User, notification_type: NotificationType
    ) -> NotificationPreferenceResponse | None:
        """Get a specific notification preference."""
        query = select(NotificationPreference).where(
            NotificationPreference.user_id == user.id,
            NotificationPreference.notification_type == notification_type.value,
        )
        result = await self.db.execute(query)
        preference = result.scalar_one_or_none()

        if not preference:
            return None

        return NotificationPreferenceResponse.model_validate(preference)

    async def update_preference(
        self,
        user: User,
        notification_type: NotificationType,
        data: NotificationPreferenceUpdate,
    ) -> NotificationPreferenceResponse:
        """Update or create a notification preference."""
        query = select(NotificationPreference).where(
            NotificationPreference.user_id == user.id,
            NotificationPreference.notification_type == notification_type.value,
        )
        result = await self.db.execute(query)
        preference = result.scalar_one_or_none()

        if preference:
            # Update existing
            for field, value in data.model_dump(exclude_unset=True).items():
                setattr(preference, field, value)
        else:
            # Create new
            preference = NotificationPreference(
                user_id=user.id,
                notification_type=notification_type.value,
                **data.model_dump(),
            )
            self.db.add(preference)

        await self.db.flush()
        return NotificationPreferenceResponse.model_validate(preference)

    async def _get_or_create_preference(
        self, user_id: int, notification_type: NotificationType
    ) -> NotificationPreference:
        """Get or create a preference for internal use."""
        query = select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.notification_type == notification_type.value,
        )
        result = await self.db.execute(query)
        preference = result.scalar_one_or_none()

        if not preference:
            # Create with defaults
            type_info = NOTIFICATION_TYPE_INFO.get(notification_type, {})
            preference = NotificationPreference(
                user_id=user_id,
                notification_type=notification_type.value,
                custom_threshold=type_info.get("default_threshold"),
                days_before=type_info.get("default_days_before"),
            )
            self.db.add(preference)
            await self.db.flush()

        return preference

    # === Notification Settings ===

    async def get_settings(self, user: User) -> NotificationSettingsResponse:
        """Get notification settings for a user."""
        query = select(NotificationSettings).where(NotificationSettings.user_id == user.id)
        result = await self.db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            # Create default settings
            settings = NotificationSettings(user_id=user.id)
            self.db.add(settings)
            await self.db.flush()

        return NotificationSettingsResponse.model_validate(settings)

    async def update_settings(
        self, user: User, data: NotificationSettingsUpdate
    ) -> NotificationSettingsResponse:
        """Update notification settings."""
        query = select(NotificationSettings).where(NotificationSettings.user_id == user.id)
        result = await self.db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            settings = NotificationSettings(user_id=user.id)
            self.db.add(settings)

        for field, value in data.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(settings, field, value)

        await self.db.flush()
        return NotificationSettingsResponse.model_validate(settings)

    # === Push Subscriptions ===

    async def subscribe_push(
        self, user: User, data: PushSubscriptionCreate
    ) -> PushSubscriptionResponse:
        """Subscribe to push notifications."""
        # Check if already subscribed with this endpoint
        query = select(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.endpoint == data.endpoint,
        )
        result = await self.db.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing subscription
            existing.p256dh_key = data.p256dh_key
            existing.auth_key = data.auth_key
            existing.user_agent = data.user_agent
            existing.device_name = data.device_name
            existing.is_active = True
            existing.failed_count = 0
            subscription = existing
        else:
            # Create new subscription
            subscription = PushSubscription(
                user_id=user.id,
                endpoint=data.endpoint,
                p256dh_key=data.p256dh_key,
                auth_key=data.auth_key,
                user_agent=data.user_agent,
                device_name=data.device_name,
            )
            self.db.add(subscription)

        await self.db.flush()
        return PushSubscriptionResponse.model_validate(subscription)

    async def unsubscribe_push(self, user: User, endpoint: str) -> bool:
        """Unsubscribe from push notifications."""
        query = select(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.endpoint == endpoint,
        )
        result = await self.db.execute(query)
        subscription = result.scalar_one_or_none()

        if not subscription:
            return False

        subscription.is_active = False
        await self.db.flush()
        return True

    async def list_push_subscriptions(self, user: User) -> list[PushSubscriptionResponse]:
        """List active push subscriptions for a user."""
        query = select(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.is_active == True,
        )
        result = await self.db.execute(query)
        subscriptions = result.scalars().all()

        return [PushSubscriptionResponse.model_validate(s) for s in subscriptions]

    # === Helpers ===

    def _build_notification_response(self, notification: Notification) -> NotificationResponse:
        """Build notification response from model."""
        return NotificationResponse(
            id=notification.id,
            user_id=notification.user_id,
            type=NotificationType(notification.type),
            title=notification.title,
            message=notification.message,
            icon=notification.icon,
            color=notification.color,
            priority=NotificationPriority(notification.priority),
            entity_type=notification.entity_type,
            entity_id=notification.entity_id,
            action_url=notification.action_url,
            action_label=notification.action_label,
            is_read=notification.is_read,
            read_at=notification.read_at,
            is_dismissed=notification.is_dismissed,
            dismissed_at=notification.dismissed_at,
            sent_in_app=notification.sent_in_app,
            sent_email=notification.sent_email,
            sent_push=notification.sent_push,
            scheduled_for=notification.scheduled_for,
            sent_at=notification.sent_at,
            metadata=notification.extra_data,
            created_at=notification.created_at,
        )
