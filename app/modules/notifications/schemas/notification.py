from datetime import datetime, time
from typing import Any

from pydantic import BaseModel, Field

from app.models.notification import (
    NotificationFrequency,
    NotificationPriority,
    NotificationType,
)

# === Notification Schemas ===


class NotificationBase(BaseModel):
    """Base schema for notifications."""

    type: NotificationType
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1)
    icon: str | None = None
    color: str | None = None
    priority: NotificationPriority = NotificationPriority.NORMAL
    entity_type: str | None = None
    entity_id: int | None = None
    action_url: str | None = None
    action_label: str | None = None


class NotificationCreate(NotificationBase):
    """Schema for creating notifications."""

    scheduled_for: datetime | None = None
    metadata: dict[str, Any] | None = None


class NotificationResponse(NotificationBase):
    """Schema for notification responses."""

    id: int
    user_id: int
    is_read: bool
    read_at: datetime | None
    is_dismissed: bool
    dismissed_at: datetime | None
    sent_in_app: bool
    sent_email: bool
    sent_push: bool
    scheduled_for: datetime | None
    sent_at: datetime | None
    metadata: dict[str, Any] | None
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationSummary(BaseModel):
    """Summary of user notifications."""

    total_count: int
    unread_count: int
    high_priority_count: int
    recent_notifications: list[NotificationResponse]


class UnreadCountResponse(BaseModel):
    """Response for unread count endpoint."""

    unread_count: int
    high_priority_count: int


# === Notification Preference Schemas ===


class NotificationPreferenceBase(BaseModel):
    """Base schema for notification preferences."""

    in_app_enabled: bool = True
    email_enabled: bool = True
    push_enabled: bool = True
    frequency: NotificationFrequency = NotificationFrequency.IMMEDIATE
    custom_threshold: int | None = None
    days_before: int | None = None


class NotificationPreferenceUpdate(NotificationPreferenceBase):
    """Schema for updating preferences."""

    pass


class NotificationPreferenceResponse(NotificationPreferenceBase):
    """Schema for preference responses."""

    id: int
    user_id: int
    notification_type: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotificationPreferenceWithDefaults(BaseModel):
    """Preference with type info and defaults."""

    notification_type: str
    type_label: str
    type_description: str
    in_app_enabled: bool
    email_enabled: bool
    push_enabled: bool
    frequency: NotificationFrequency
    custom_threshold: int | None
    days_before: int | None
    is_customized: bool  # Se o usuário já customizou


# === Notification Settings Schemas ===


class NotificationSettingsBase(BaseModel):
    """Base schema for notification settings."""

    quiet_hours_enabled: bool = False
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    timezone: str = "America/Sao_Paulo"
    digest_enabled: bool = True
    digest_frequency: str = "daily"
    digest_time: time = Field(default_factory=lambda: time(9, 0))
    email_unsubscribed: bool = False
    push_enabled: bool = True


class NotificationSettingsUpdate(BaseModel):
    """Schema for updating settings."""

    quiet_hours_enabled: bool | None = None
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    timezone: str | None = None
    digest_enabled: bool | None = None
    digest_frequency: str | None = None
    digest_time: time | None = None
    email_unsubscribed: bool | None = None
    push_enabled: bool | None = None


class NotificationSettingsResponse(NotificationSettingsBase):
    """Schema for settings responses."""

    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# === Push Subscription Schemas ===


class PushSubscriptionCreate(BaseModel):
    """Schema for creating push subscriptions."""

    endpoint: str = Field(..., max_length=500)
    p256dh_key: str = Field(..., max_length=200)
    auth_key: str = Field(..., max_length=100)
    user_agent: str | None = None
    device_name: str | None = None


class PushSubscriptionResponse(BaseModel):
    """Schema for push subscription responses."""

    id: int
    user_id: int
    endpoint: str
    device_name: str | None
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None

    class Config:
        from_attributes = True


# === Type Definitions ===


NOTIFICATION_TYPE_INFO = {
    NotificationType.INVOICE_DUE_7_DAYS: {
        "label": "Fatura vence em 7 dias",
        "description": "Alerta quando a fatura do cartão vence em 7 dias",
        "default_days_before": 7,
    },
    NotificationType.INVOICE_DUE_3_DAYS: {
        "label": "Fatura vence em 3 dias",
        "description": "Alerta quando a fatura do cartão vence em 3 dias",
        "default_days_before": 3,
    },
    NotificationType.INVOICE_DUE_1_DAY: {
        "label": "Fatura vence amanhã",
        "description": "Alerta quando a fatura do cartão vence amanhã",
        "default_days_before": 1,
    },
    NotificationType.INVOICE_OVERDUE: {
        "label": "Fatura vencida",
        "description": "Alerta quando a fatura do cartão está vencida",
    },
    NotificationType.INVOICE_MISSING_CURRENT: {
        "label": "Fatura do mês não carregada",
        "description": "Lembrete no início do mês sobre faturas do mês anterior que ainda não foram carregadas",
    },
    NotificationType.INVOICE_MISSING_PRE_DUE: {
        "label": "Fatura não carregada perto do vencimento",
        "description": "Alerta quando o vencimento do cartão se aproxima e a fatura ainda não foi carregada",
        "default_days_before": 3,
    },
    NotificationType.BUDGET_WARNING_80: {
        "label": "Orçamento em 80%",
        "description": "Alerta quando você atinge 80% do orçamento de uma categoria",
        "default_threshold": 80,
    },
    NotificationType.BUDGET_EXCEEDED: {
        "label": "Orçamento excedido",
        "description": "Alerta quando você excede o orçamento de uma categoria",
    },
    NotificationType.CREDIT_LIMIT_80: {
        "label": "Limite do cartão em 80%",
        "description": "Alerta quando você usa 80% do limite do cartão",
        "default_threshold": 80,
    },
    NotificationType.CREDIT_LIMIT_EXCEEDED: {
        "label": "Limite do cartão excedido",
        "description": "Alerta quando você excede o limite do cartão",
    },
    NotificationType.GOAL_MILESTONE_25: {
        "label": "Meta em 25%",
        "description": "Comemoração quando você atinge 25% de uma meta",
    },
    NotificationType.GOAL_MILESTONE_50: {
        "label": "Meta em 50%",
        "description": "Comemoração quando você atinge 50% de uma meta",
    },
    NotificationType.GOAL_MILESTONE_75: {
        "label": "Meta em 75%",
        "description": "Comemoração quando você atinge 75% de uma meta",
    },
    NotificationType.GOAL_ACHIEVED: {
        "label": "Meta alcançada",
        "description": "Comemoração quando você alcança uma meta",
    },
    NotificationType.RECURRING_DUE_TOMORROW: {
        "label": "Recorrência amanhã",
        "description": "Lembrete de transação recorrente que vence amanhã",
    },
    NotificationType.BALANCE_LOW: {
        "label": "Saldo baixo",
        "description": "Alerta quando o saldo de uma conta está baixo",
    },
    NotificationType.BALANCE_NEGATIVE_RISK: {
        "label": "Risco de saldo negativo",
        "description": "Alerta quando há risco de ficar com saldo negativo",
    },
    NotificationType.WEEKLY_DIGEST: {
        "label": "Resumo semanal",
        "description": "Resumo semanal das suas finanças",
    },
    NotificationType.DAILY_DIGEST: {
        "label": "Resumo diário",
        "description": "Resumo diário das suas finanças",
    },
}
