"""Add payment_method column to transactions

Revision ID: add_payment_method
Revises: add_payment_transaction_ids
Create Date: 2025-01-13

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_payment_method"
down_revision = "add_payment_txn_ids"
branch_labels = None
depends_on = None


def upgrade():
    # Add payment_method column to transactions
    op.add_column("transactions", sa.Column("payment_method", sa.String(20), nullable=True))

    # Create index for payment_method
    op.create_index("ix_transactions_payment_method", "transactions", ["payment_method"])

    # Backfill existing data:
    # - Transactions with credit_card_id get 'credit_card'
    # - Other expense transactions get 'debit_card' as default
    op.execute("""
        UPDATE transactions
        SET payment_method = 'credit_card'
        WHERE credit_card_id IS NOT NULL
    """)

    op.execute("""
        UPDATE transactions
        SET payment_method = 'debit_card'
        WHERE credit_card_id IS NULL
        AND type = 'expense'
        AND payment_method IS NULL
    """)

    # Income transactions with income_source get 'bank_transfer' as default
    op.execute("""
        UPDATE transactions
        SET payment_method = 'bank_transfer'
        WHERE type = 'income'
        AND income_source_id IS NOT NULL
        AND payment_method IS NULL
    """)

    # Add payment_method column to recurring_transactions
    op.add_column(
        "recurring_transactions", sa.Column("payment_method", sa.String(20), nullable=True)
    )


def downgrade():
    op.drop_column("recurring_transactions", "payment_method")
    op.drop_index("ix_transactions_payment_method", "transactions")
    op.drop_column("transactions", "payment_method")
