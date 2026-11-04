"""add file_purged_at to documents

Revision ID: add_document_file_purged_at
Revises: add_document_ai_retry
Create Date: 2026-11-04

Retenção das faturas enviadas (#50): marca quando o original e os dados
extraídos foram apagados.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_document_file_purged_at"
down_revision: str = "add_document_ai_retry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("file_purged_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("file_purged_at")
