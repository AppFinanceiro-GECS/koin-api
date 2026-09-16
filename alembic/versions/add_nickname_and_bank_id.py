"""Add nickname and bank_id to credit_cards and accounts

Revision ID: add_nickname_bank_id
Revises: add_perf_indexes
Create Date: 2026-01-16

Adds nickname and bank_id fields to credit_cards table,
and bank_id to accounts table for bank logo integration.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_nickname_bank_id"
down_revision = "add_perf_indexes"
branch_labels = None
depends_on = None


def upgrade():
    # Add nickname and bank_id columns to credit_cards table
    op.add_column("credit_cards", sa.Column("nickname", sa.String(50), nullable=True))
    op.add_column("credit_cards", sa.Column("bank_id", sa.String(50), nullable=True))

    # Add bank_id column to accounts table
    op.add_column("accounts", sa.Column("bank_id", sa.String(50), nullable=True))


def downgrade():
    op.drop_column("accounts", "bank_id")
    op.drop_column("credit_cards", "bank_id")
    op.drop_column("credit_cards", "nickname")
