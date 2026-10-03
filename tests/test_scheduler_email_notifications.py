"""Testes para o job de entrega de notificações por email (issue #69)."""

from unittest.mock import patch

import pytest

from app.core import scheduler as scheduler_module
from app.models.notification import (
    Notification,
    NotificationSettings,
    NotificationType,
)
from app.models.user import User


async def _create_user(db_session, email="user@example.com") -> User:
    user = User(email=email, hashed_password="x", name="Fulano")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_notification(db_session, user: User, **overrides) -> Notification:
    defaults = {
        "user_id": user.id,
        "type": NotificationType.INVOICE_DUE_3_DAYS.value,
        "title": "Fatura vencendo",
        "message": "Sua fatura vence em 3 dias",
        "sent_email": False,
    }
    defaults.update(overrides)
    notification = Notification(**defaults)
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)
    return notification


@pytest.mark.asyncio
async def test_sends_pending_notification_and_marks_as_sent(db_session):
    user = await _create_user(db_session)
    notification = await _create_notification(db_session, user)

    with patch.object(
        scheduler_module.email_service, "send_notification_email", return_value=True
    ) as mock_send:
        sent_count = await scheduler_module._send_pending_email_notifications(db_session)

    mock_send.assert_called_once_with(
        user.email, user.name, notification.title, notification.message, None, None
    )
    assert sent_count == 1

    await db_session.refresh(notification)
    assert notification.sent_email is True
    assert notification.sent_at is not None


@pytest.mark.asyncio
async def test_keeps_sent_email_false_when_send_fails(db_session):
    user = await _create_user(db_session)
    notification = await _create_notification(db_session, user)

    with patch.object(
        scheduler_module.email_service, "send_notification_email", return_value=False
    ) as mock_send:
        sent_count = await scheduler_module._send_pending_email_notifications(db_session)

    mock_send.assert_called_once()
    assert sent_count == 0

    await db_session.refresh(notification)
    assert notification.sent_email is False
    assert notification.sent_at is None


@pytest.mark.asyncio
async def test_skips_notification_when_user_unsubscribed_from_email(db_session):
    user = await _create_user(db_session)
    await _create_notification(db_session, user)

    db_session.add(NotificationSettings(user_id=user.id, email_unsubscribed=True))
    await db_session.commit()

    with patch.object(
        scheduler_module.email_service, "send_notification_email", return_value=True
    ) as mock_send:
        sent_count = await scheduler_module._send_pending_email_notifications(db_session)

    mock_send.assert_not_called()
    assert sent_count == 0


@pytest.mark.asyncio
async def test_skips_already_sent_and_dismissed_notifications(db_session):
    user = await _create_user(db_session)
    await _create_notification(db_session, user, sent_email=True)
    await _create_notification(db_session, user, is_dismissed=True)

    with patch.object(
        scheduler_module.email_service, "send_notification_email", return_value=True
    ) as mock_send:
        sent_count = await scheduler_module._send_pending_email_notifications(db_session)

    mock_send.assert_not_called()
    assert sent_count == 0
