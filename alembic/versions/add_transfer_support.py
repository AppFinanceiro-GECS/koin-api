"""Add transfer support with linked_transaction_id

Revision ID: add_transfer_support
Revises: add_api_keys
Create Date: 2026-01-18

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_transfer_support"
down_revision = "add_api_keys"
branch_labels = None
depends_on = None


def upgrade():
    # Add linked_transaction_id column to transactions table
    # This field links two transactions together for transfers
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "linked_transaction_id",
                sa.Integer(),
                # mesmo nome que o Postgres gera sem nome explícito (o batch do SQLite exige um)
                sa.ForeignKey(
                    "transactions.id",
                    name="transactions_linked_transaction_id_fkey",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
        )

    # Create index for faster lookups
    op.create_index(
        "ix_transactions_linked_transaction_id", "transactions", ["linked_transaction_id"]
    )


def downgrade():
    # Remove index first
    op.drop_index("ix_transactions_linked_transaction_id", table_name="transactions")

    # Remove column
    op.drop_column("transactions", "linked_transaction_id")
