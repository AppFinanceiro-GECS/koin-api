"""add invoice_password_encrypted to credit_cards

Revision ID: c4163fa87117
Revises: add_receipt_installments
Create Date: 2026-02-07 16:24:25.027968

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4163fa87117"
down_revision: str | None = "add_receipt_installments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add invoice_password_encrypted column to credit_cards table
    op.add_column("credit_cards", sa.Column("invoice_password_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove invoice_password_encrypted column from credit_cards table
    op.drop_column("credit_cards", "invoice_password_encrypted")
