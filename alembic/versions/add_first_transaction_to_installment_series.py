"""Add first_transaction_id to installment_series

Revision ID: add_first_tx_series
Revises: 6ab1c1835f16
Create Date: 2026-01-22

Adiciona campo first_transaction_id na tabela installment_series para
vincular cada série à transação que a originou. Isso resolve o problema
de parcelas duplicadas (como ZP*KAS) serem incorretamente mescladas em
uma única série quando têm mesmo merchant, valor e total de parcelas.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_first_tx_series"
down_revision = "6ab1c1835f16"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Adicionar coluna first_transaction_id
    op.add_column(
        "installment_series", sa.Column("first_transaction_id", sa.Integer(), nullable=True)
    )

    # 2. Criar foreign key
    op.create_foreign_key(
        "fk_installment_series_first_transaction",
        "installment_series",
        "transactions",
        ["first_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. Criar índice único para garantir que cada transação só pode ser
    # "primeira" de uma série
    op.create_index(
        "ix_installment_series_first_transaction_id",
        "installment_series",
        ["first_transaction_id"],
        unique=True,
    )

    # 4. Popular com dados existentes (primeira transação de cada série por created_at)
    op.execute("""
        UPDATE installment_series s
        SET first_transaction_id = (
            SELECT t.id FROM transactions t
            WHERE t.installment_series_id = s.id
            ORDER BY t.created_at ASC
            LIMIT 1
        )
        WHERE s.first_transaction_id IS NULL
    """)


def downgrade():
    op.drop_index("ix_installment_series_first_transaction_id", table_name="installment_series")
    op.drop_constraint(
        "fk_installment_series_first_transaction", "installment_series", type_="foreignkey"
    )
    op.drop_column("installment_series", "first_transaction_id")
