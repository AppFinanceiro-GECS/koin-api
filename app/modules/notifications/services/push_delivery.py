"""
Entrega por push das notificações já geradas (#43). Roda no scheduler.

- Só notificações das últimas 24 h: o primeiro deploy não dispara o histórico antigo.
- Respeita NotificationSettings.push_enabled, a preferência do tipo (push_enabled e
  frequência) e o horário silencioso no fuso do usuário (a notificação fica para depois).
- Marca sent_push quando pelo menos um aparelho aceitou; token de app desinstalado
  (DeviceNotRegistered) é apagado.
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.push_service import build_message, is_unregistered, send_push
from app.core.utils import utc_now
from app.models.notification import Notification, NotificationSettings, NotificationType
from app.models.push_device import PushDevice
from app.models.user import User
from app.modules.notifications.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

MAX_AGE = timedelta(hours=24)
BATCH = 500


def in_quiet_hours(user_settings: NotificationSettings | None, now: datetime) -> bool:
    if not user_settings or not user_settings.quiet_hours_enabled:
        return False
    start, end = user_settings.quiet_hours_start, user_settings.quiet_hours_end
    if not isinstance(start, time) or not isinstance(end, time):
        return False
    tz = ZoneInfo(user_settings.timezone or "America/Sao_Paulo")
    local = now.replace(tzinfo=UTC).astimezone(tz).time()
    if start <= end:
        return start <= local < end
    return local >= start or local < end  # atravessa a meia-noite (ex.: 22h-7h)


async def deliver_pending_push(db: AsyncSession, client: httpx.AsyncClient | None = None) -> int:
    """Envia o push das notificações pendentes. Devolve quantas foram entregues."""
    now = utc_now()
    rows = (
        await db.execute(
            select(Notification)
            .join(User, Notification.user_id == User.id)
            .where(
                Notification.sent_push == False,  # noqa: E712
                Notification.is_dismissed == False,  # noqa: E712
                User.is_active == True,  # noqa: E712
                Notification.created_at >= now - MAX_AGE,
                or_(Notification.scheduled_for.is_(None), Notification.scheduled_for <= now),
            )
            .order_by(Notification.created_at)
            .limit(BATCH)
        )
    ).scalars()
    notifications = list(rows)
    if not notifications:
        return 0

    user_ids = {n.user_id for n in notifications}
    devices: dict[int, list[PushDevice]] = defaultdict(list)
    for device in (
        await db.execute(select(PushDevice).where(PushDevice.user_id.in_(user_ids)))
    ).scalars():
        devices[device.user_id].append(device)
    user_settings = {
        s.user_id: s
        for s in (
            await db.execute(
                select(NotificationSettings).where(NotificationSettings.user_id.in_(user_ids))
            )
        ).scalars()
    }

    preferences = NotificationService(db)
    messages: list[dict] = []
    targets: list[tuple[Notification, PushDevice]] = []
    for notification in notifications:
        if not devices[notification.user_id]:
            continue
        settings_row = user_settings.get(notification.user_id)
        if settings_row and not settings_row.push_enabled:
            continue
        if in_quiet_hours(settings_row, now):
            continue  # tenta de novo no próximo ciclo
        preference = await preferences._get_or_create_preference(
            notification.user_id, NotificationType(notification.type)
        )
        if not preference.push_enabled or preference.frequency == "disabled":
            continue
        for device in devices[notification.user_id]:
            messages.append(
                build_message(
                    device.expo_push_token,
                    notification.title,
                    notification.message,
                    {
                        "notification_id": notification.id,
                        "type": notification.type,
                        "action_url": notification.action_url,
                    },
                )
            )
            targets.append((notification, device))

    if not messages:
        await db.commit()
        return 0

    tickets = await send_push(messages, client)
    delivered: set[int] = set()
    dead_tokens: set[int] = set()
    for (notification, device), ticket in zip(targets, tickets, strict=True):
        if ticket.get("status") == "ok":
            delivered.add(notification.id)
        elif is_unregistered(ticket):
            dead_tokens.add(device.id)

    for notification in notifications:
        if notification.id in delivered:
            notification.sent_push = True
            notification.sent_at = notification.sent_at or now
    if dead_tokens:
        await db.execute(delete(PushDevice).where(PushDevice.id.in_(dead_tokens)))
        logger.info("push_devices_removed count=%s", len(dead_tokens))
    await db.commit()
    return len(delivered)
