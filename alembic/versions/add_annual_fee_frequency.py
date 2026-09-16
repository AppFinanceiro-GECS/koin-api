"""add annual_fee_frequency to credit_cards

Revision ID: add_annual_fee_freq
Revises: add_business_day_fields
Create Date: 2026-01-09

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_annual_fee_freq"
down_revision = "add_business_day_fields"
branch_labels = None
depends_on = None


def upgrade():
    # Add annual_fee_frequency column to credit_cards table
    op.add_column(
        "credit_cards",
        sa.Column("annual_fee_frequency", sa.String(20), server_default="monthly", nullable=False),
    )


def downgrade():
    op.drop_column("credit_cards", "annual_fee_frequency")
