"""add business day fields to income sources

Revision ID: add_business_day_fields
Revises: add_credit_cards_and_income_sources
Create Date: 2026-01-08

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_business_day_fields"
down_revision = "add_credit_income"
branch_labels = None
depends_on = None


def upgrade():
    # Add business day fields to income_sources table
    op.add_column(
        "income_sources",
        sa.Column("use_business_day", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("income_sources", sa.Column("business_day_number", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("income_sources", "business_day_number")
    op.drop_column("income_sources", "use_business_day")
