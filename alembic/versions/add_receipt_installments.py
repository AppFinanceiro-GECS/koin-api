"""Add installment fields to receipt_payments

Revision ID: add_receipt_installments
Revises: add_more_challenges
Create Date: 2026-01-26

Adds support for installment payments in receipt_payments table:
- is_installment: boolean flag
- installment_count: total number of installments
- credit_card_id: FK to credit_cards table
- installment_series_id: FK to installment_series table
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_receipt_installments"
down_revision: str | None = "add_more_challenges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add installment columns to receipt_payments
    op.add_column(
        "receipt_payments",
        sa.Column("is_installment", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("receipt_payments", sa.Column("installment_count", sa.Integer(), nullable=True))
    op.add_column("receipt_payments", sa.Column("credit_card_id", sa.Integer(), nullable=True))
    op.add_column(
        "receipt_payments", sa.Column("installment_series_id", sa.Integer(), nullable=True)
    )

    # Add foreign keys
    op.create_foreign_key(
        "fk_receipt_payments_credit_card_id",
        "receipt_payments",
        "credit_cards",
        ["credit_card_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_receipt_payments_installment_series_id",
        "receipt_payments",
        "installment_series",
        ["installment_series_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add indexes for the new FK columns
    op.create_index("ix_receipt_payments_credit_card_id", "receipt_payments", ["credit_card_id"])
    op.create_index(
        "ix_receipt_payments_installment_series_id", "receipt_payments", ["installment_series_id"]
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_receipt_payments_installment_series_id", table_name="receipt_payments")
    op.drop_index("ix_receipt_payments_credit_card_id", table_name="receipt_payments")

    # Drop foreign keys
    op.drop_constraint(
        "fk_receipt_payments_installment_series_id", "receipt_payments", type_="foreignkey"
    )
    op.drop_constraint("fk_receipt_payments_credit_card_id", "receipt_payments", type_="foreignkey")

    # Drop columns
    op.drop_column("receipt_payments", "installment_series_id")
    op.drop_column("receipt_payments", "credit_card_id")
    op.drop_column("receipt_payments", "installment_count")
    op.drop_column("receipt_payments", "is_installment")
