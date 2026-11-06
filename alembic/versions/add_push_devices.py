"""add push_devices table

Revision ID: add_push_devices
Revises: add_document_file_purged_at
Create Date: 2026-11-06

Aparelhos que recebem push pelo Expo Push Service (#43).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_push_devices"
down_revision: str = "add_document_file_purged_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expo_push_token", sa.String(200), nullable=False, unique=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("app_version", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_push_devices_user_id", "push_devices", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_push_devices_user_id", "push_devices")
    op.drop_table("push_devices")
