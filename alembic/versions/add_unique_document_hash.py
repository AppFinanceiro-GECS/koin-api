"""unique (user_id, file_hash) on documents

Revision ID: add_unique_document_hash
Revises: restore_indexes_fks
Create Date: 2026-10-07

Bloqueia no banco o reenvio do mesmo arquivo pelo mesmo usuario (N11).
Duplicatas antigas nao sao apagadas (podem ter transacoes ligadas): o documento
mais antigo mantem o hash real e os demais recebem um hash derivado do id.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_unique_document_hash"
down_revision: str = "restore_indexes_fks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text("""
        UPDATE documents d
        SET file_hash = encode(sha256(convert_to(d.file_hash || ':' || d.id::text, 'UTF8')), 'hex')
        WHERE EXISTS (
            SELECT 1 FROM documents older
            WHERE older.user_id = d.user_id
            AND older.file_hash = d.file_hash
            AND older.id < d.id
        )
    """)
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_user_file_hash "
            "ON documents (user_id, file_hash)"
        )
    )


def downgrade() -> None:
    op.drop_index("uq_documents_user_file_hash", "documents")
