"""cadastro pelo código de evento: origem, aceite de novidades, e-mail confirmado e brinde

Revision ID: add_event_signups
Revises: add_household_settlements
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "add_event_signups"
down_revision: str = "add_household_settlements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_signups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("marketing_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("marketing_opt_in_at", sa.DateTime(), nullable=True),
        sa.Column("consent_version", sa.String(30), nullable=False),
        sa.Column("verification_code_hash", sa.String(64), nullable=True),
        sa.Column("verification_expires_at", sa.DateTime(), nullable=True),
        sa.Column("verification_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verification_sent_at", sa.DateTime(), nullable=True),
        sa.Column("verification_sends", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
        sa.Column("gift_delivered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_event_signups_user_id", "event_signups", ["user_id"], unique=True)
    op.create_index("ix_event_signups_source", "event_signups", ["source"])


def downgrade() -> None:
    op.drop_index("ix_event_signups_source", table_name="event_signups")
    op.drop_index("ix_event_signups_user_id", table_name="event_signups")
    op.drop_table("event_signups")
