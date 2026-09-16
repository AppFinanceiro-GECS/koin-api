"""Add notifications tables

Revision ID: add_notifications
Revises: add_transfer_support
Create Date: 2026-01-18

Adds tables for the notification system:
- notifications: Main notification storage
- notification_preferences: User preferences per notification type
- notification_settings: Global user notification settings
- push_subscriptions: Web Push API subscriptions
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_notifications"
down_revision = "add_transfer_support"
branch_labels = None
depends_on = None


def upgrade():
    # Create notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        # Content
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("color", sa.String(20), nullable=True),
        # Priority
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
        # References
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("action_url", sa.String(500), nullable=True),
        sa.Column("action_label", sa.String(100), nullable=True),
        # Read status
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        # Dismiss status
        sa.Column("is_dismissed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        # Delivery channels
        sa.Column("sent_in_app", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sent_email", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sent_push", sa.Boolean(), nullable=False, server_default="false"),
        # Scheduling
        sa.Column("scheduled_for", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        # Metadata
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create indexes for notifications
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "is_read"])
    op.create_index("ix_notifications_user_type", "notifications", ["user_id", "type"])
    op.create_index("ix_notifications_scheduled", "notifications", ["scheduled_for"])
    op.create_index("ix_notifications_created", "notifications", ["created_at"])

    # Create notification_preferences table
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("notification_type", sa.String(50), nullable=False),
        # Channel settings
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("push_enabled", sa.Boolean(), nullable=False, server_default="true"),
        # Frequency
        sa.Column("frequency", sa.String(20), nullable=False, server_default="immediate"),
        # Custom settings
        sa.Column("custom_threshold", sa.Integer(), nullable=True),
        sa.Column("days_before", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        # Unique constraint
        sa.UniqueConstraint("user_id", "notification_type", name="uq_user_notification_type"),
    )

    op.create_index("ix_notification_preferences_user_id", "notification_preferences", ["user_id"])

    # Create notification_settings table
    op.create_table(
        "notification_settings",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        # Quiet hours
        sa.Column("quiet_hours_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
        # Timezone
        sa.Column("timezone", sa.String(50), nullable=False, server_default="America/Sao_Paulo"),
        # Digest
        sa.Column("digest_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("digest_frequency", sa.String(20), nullable=False, server_default="daily"),
        sa.Column("digest_time", sa.Time(), nullable=False, server_default="09:00:00"),
        # Global settings
        sa.Column("email_unsubscribed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("push_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # Create push_subscriptions table
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        # Web Push API
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("p256dh_key", sa.String(200), nullable=False),
        sa.Column("auth_key", sa.String(100), nullable=False),
        # Device info
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("device_name", sa.String(100), nullable=True),
        # Status
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        # Unique constraint
        sa.UniqueConstraint("user_id", "endpoint", name="uq_user_endpoint"),
    )

    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])
    op.create_index(
        "ix_push_subscriptions_user_active", "push_subscriptions", ["user_id", "is_active"]
    )


def downgrade():
    op.drop_table("push_subscriptions")
    op.drop_table("notification_settings")
    op.drop_table("notification_preferences")
    op.drop_table("notifications")
