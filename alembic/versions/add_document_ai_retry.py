"""add RN016 retry fields to documents

Revision ID: add_document_ai_retry
Revises: add_refresh_tokens
Create Date: 2026-11-04

RN016 (#57) e #37: status waiting_ai com código de erro estável, próxima
tentativa e contagem; processing_started_at para achar processamento preso.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_document_ai_retry"
down_revision: str = "add_refresh_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("error_code", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("next_retry_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("processing_started_at", sa.DateTime(), nullable=True))
    op.create_index("ix_documents_next_retry_at", "documents", ["next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_documents_next_retry_at", "documents")
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("processing_started_at")
        batch_op.drop_column("attempts")
        batch_op.drop_column("next_retry_at")
        batch_op.drop_column("error_code")
