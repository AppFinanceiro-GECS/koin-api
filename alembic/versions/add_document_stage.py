"""add stage to documents

Revision ID: add_document_stage
Revises: add_push_devices
Create Date: 2026-11-06

Etapa da leitura para o app mostrar o progresso (#37): received → extracting
→ validating → done, ou waiting (fila da IA) / failed.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_document_stage"
down_revision: str = "add_push_devices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(
            sa.Column("stage", sa.String(20), nullable=False, server_default="received")
        )
    # documentos que já existiam: etapa coerente com o status
    op.execute(
        """
        UPDATE documents SET stage = CASE status
            WHEN 'completed' THEN 'done'
            WHEN 'failed' THEN 'failed'
            WHEN 'waiting_ai' THEN 'waiting'
            WHEN 'processing' THEN 'extracting'
            ELSE 'received'
        END
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("stage")
