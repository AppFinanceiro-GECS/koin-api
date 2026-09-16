"""Add payment_transaction_ids JSON column to invoices

Revision ID: add_payment_txn_ids
Revises:
Create Date: 2026-01-11

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_payment_txn_ids"
down_revision = "add_cc_installment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add JSON column for multiple payment transaction IDs
    op.add_column(
        "credit_card_invoices",
        sa.Column("payment_transaction_ids", sa.JSON, nullable=True, default=[]),
    )


def downgrade() -> None:
    op.drop_column("credit_card_invoices", "payment_transaction_ids")
