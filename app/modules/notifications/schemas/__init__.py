"""Notification schemas."""

from .notification import (
    NotificationCreate,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    NotificationResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    NotificationSummary,
    PushSubscriptionCreate,
    PushSubscriptionResponse,
    UnreadCountResponse,
)

__all__ = [
    "NotificationCreate",
    "NotificationResponse",
    "NotificationSummary",
    "NotificationPreferenceResponse",
    "NotificationPreferenceUpdate",
    "NotificationSettingsResponse",
    "NotificationSettingsUpdate",
    "PushSubscriptionCreate",
    "PushSubscriptionResponse",
    "UnreadCountResponse",
]
