"""Notifications module for alerts and push notifications."""

from app.modules.notifications.routers.notifications import router
from app.modules.notifications.schemas.notification import (
    NotificationCreate,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    NotificationResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    NotificationSummary,
    PushSubscriptionCreate,
)
from app.modules.notifications.services.notification_service import NotificationService

__all__ = [
    "router",
    "NotificationService",
    "NotificationCreate",
    "NotificationResponse",
    "NotificationSummary",
    "NotificationPreferenceResponse",
    "NotificationPreferenceUpdate",
    "NotificationSettingsResponse",
    "NotificationSettingsUpdate",
    "PushSubscriptionCreate",
]
