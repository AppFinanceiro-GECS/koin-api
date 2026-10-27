"""add_audit_and_soft_delete

Revision ID: 0c2a06bf1b9f
Revises: normalize_emails
Create Date: 2026-10-27 01:01:32.179012

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c2a06bf1b9f'
down_revision: Union[str, None] = 'normalize_emails'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Criar tabela de auditoria (LGPD)
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_hash", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_user_hash", "audit_logs", ["user_hash"])

    # 2. Adicionar coluna deleted_at na tabela users em Batch Mode (compatível com SQLite)
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    # 1. Remover coluna de usuários
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("deleted_at")

    # 2. Remover tabela de auditoria
    op.drop_index("ix_audit_logs_user_hash", table_name="audit_logs")
    op.drop_table("audit_logs")