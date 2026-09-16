from datetime import datetime, time
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class NotificationType(str, Enum):
    # Faturas de Cartão de Crédito
    INVOICE_DUE_7_DAYS = "invoice_due_7_days"
    INVOICE_DUE_3_DAYS = "invoice_due_3_days"
    INVOICE_DUE_1_DAY = "invoice_due_1_day"
    INVOICE_OVERDUE = "invoice_overdue"

    # Faturas pendentes de carregamento
    INVOICE_MISSING_CURRENT = (
        "invoice_missing_current"  # Dia 1: fatura do mês anterior ainda não carregada
    )
    INVOICE_MISSING_PRE_DUE = (
        "invoice_missing_pre_due"  # D-3 vencimento: fatura do mês ainda não carregada
    )

    # Orçamento
    BUDGET_WARNING_80 = "budget_warning_80"
    BUDGET_EXCEEDED = "budget_exceeded"

    # Cartão de Crédito - Limite
    CREDIT_LIMIT_80 = "credit_limit_80"
    CREDIT_LIMIT_EXCEEDED = "credit_limit_exceeded"

    # Metas
    GOAL_MILESTONE_25 = "goal_milestone_25"
    GOAL_MILESTONE_50 = "goal_milestone_50"
    GOAL_MILESTONE_75 = "goal_milestone_75"
    GOAL_ACHIEVED = "goal_achieved"

    # Recorrências
    RECURRING_DUE_TOMORROW = "recurring_due_tomorrow"

    # Saldo
    BALANCE_LOW = "balance_low"
    BALANCE_NEGATIVE_RISK = "balance_negative_risk"

    # Sistema
    WEEKLY_DIGEST = "weekly_digest"
    DAILY_DIGEST = "daily_digest"

    # Automações
    AUTOMATION_DISABLED = "automation_disabled"

    # Genérico
    CUSTOM = "custom"


class NotificationPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationFrequency(str, Enum):
    IMMEDIATE = "immediate"
    DAILY_DIGEST = "daily_digest"
    WEEKLY_DIGEST = "weekly_digest"
    DISABLED = "disabled"


class Notification(Base):
    """Armazena notificações enviadas aos usuários."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Conteúdo
    type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Prioridade
    priority: Mapped[str] = mapped_column(String(20), default="normal")

    # Referências para navegação
    entity_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # invoice/budget/goal/debt/etc
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    action_label: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Status de leitura
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Status de dispensa
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Canais de envio
    sent_in_app: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_email: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_push: Mapped[bool] = mapped_column(Boolean, default=False)

    # Agendamento
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Metadados extras (JSON)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "is_read"),
        Index("ix_notifications_user_type", "user_id", "type"),
        Index("ix_notifications_scheduled", "scheduled_for"),
        Index("ix_notifications_created", "created_at"),
    )


class NotificationPreference(Base):
    """Preferências de notificação por tipo."""

    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    notification_type: Mapped[str] = mapped_column(String(50))

    # Canais habilitados
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Frequência
    frequency: Mapped[str] = mapped_column(String(20), default="immediate")

    # Customização para alertas específicos
    custom_threshold: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # Ex: alertar quando orçamento > X%
    days_before: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # Ex: alertar X dias antes do vencimento

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="notification_preferences")

    __table_args__ = (
        UniqueConstraint("user_id", "notification_type", name="uq_user_notification_type"),
    )


class NotificationSettings(Base):
    """Configurações globais de notificação do usuário."""

    __tablename__ = "notification_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    # Horário silencioso (não perturbe)
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    quiet_hours_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time, nullable=True)

    # Timezone do usuário
    timezone: Mapped[str] = mapped_column(String(50), default="America/Sao_Paulo")

    # Digest
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    digest_frequency: Mapped[str] = mapped_column(String(20), default="daily")
    digest_time: Mapped[time] = mapped_column(Time, default=time(9, 0))

    # Configurações globais
    email_unsubscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="notification_settings")


class PushSubscription(Base):
    """Inscrições de Web Push para notificações."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Web Push API
    endpoint: Mapped[str] = mapped_column(String(500))
    p256dh_key: Mapped[str] = mapped_column(String(200))
    auth_key: Mapped[str] = mapped_column(String(100))

    # Metadados do dispositivo
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="push_subscriptions")

    __table_args__ = (
        Index("ix_push_subscriptions_user_active", "user_id", "is_active"),
        UniqueConstraint("user_id", "endpoint", name="uq_user_endpoint"),
    )


# Imports para evitar circular imports
from .user import User
