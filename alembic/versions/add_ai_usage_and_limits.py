"""AI usage, durable daily reservations and monthly license quotas.

Revision ID: add_ai_usage_and_limits
Revises: add_unique_document_hash
"""

import sqlalchemy as sa

from alembic import op

revision = "add_ai_usage_and_limits"
down_revision = "add_unique_document_hash"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("feature", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(150), nullable=False),
        sa.Column("requested_model", sa.String(150), nullable=False),
        sa.Column("billing_mode", sa.String(30), nullable=False),
        *[
            sa.Column(name, sa.Integer())
            for name in (
                "input_tokens",
                "output_tokens",
                "thinking_tokens",
                "cached_input_tokens",
                "pages",
                "latency_ms",
            )
        ],
        sa.Column("cost_usd", sa.Numeric(20, 10)),
        sa.Column("pricing_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for name in ("user_id", "document_id", "feature", "model"):
        op.create_index(f"ix_ai_usage_{name}", "ai_usage", [name])
    op.create_index("ix_ai_usage_created_user", "ai_usage", ["created_at", "user_id"])
    op.create_table(
        "ai_daily_budget",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("committed_usd", sa.Numeric(20, 10), nullable=False),
    )
    op.create_table(
        "license_document_usage",
        sa.Column(
            "license_id",
            sa.Integer(),
            sa.ForeignKey("licenses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("month", sa.Date(), primary_key=True),
        sa.Column("documents", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("license_document_usage")
    op.drop_table("ai_daily_budget")
    op.drop_table("ai_usage")
