"""Remove envelopes tables - functionality merged into budgets

Revision ID: remove_envelopes_tables
Revises: add_budget_item_history
Create Date: 2025-01-25
"""

import sqlalchemy as sa

from alembic import op

revision = "remove_envelopes_tables"
down_revision = "add_budget_item_history"
branch_labels = None
depends_on = None


def upgrade():
    # Drop envelope_history first due to FK constraint
    op.drop_table("envelope_history")

    # Drop spending_envelopes
    op.drop_table("spending_envelopes")


def downgrade():
    # Recreate spending_envelopes table
    op.create_table(
        "spending_envelopes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("period_type", sa.String(20), nullable=False),
        sa.Column("limit_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("spent_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("allow_rollover", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("max_rollover_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("refill_schedule", sa.String(20), nullable=True),
        sa.Column("custom_refill_day", sa.Integer(), nullable=True),
        sa.Column("auto_refill", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("ownership_type", sa.String(20), nullable=False, server_default="personal"),
        sa.Column("last_refill_date", sa.Date(), nullable=True),
        sa.Column("period_start_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
    )

    # Recreate envelope_history table
    op.create_table(
        "envelope_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("envelope_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_before", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["envelope_id"], ["spending_envelopes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="SET NULL"),
    )
