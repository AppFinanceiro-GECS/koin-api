"""Add budget item history table

Revision ID: add_budget_item_history
Revises: add_income_split_rules
Create Date: 2025-01-25
"""

import sqlalchemy as sa

from alembic import op

revision = "add_budget_item_history"
down_revision = "add_income_split_rules"
branch_labels = None
depends_on = None


def upgrade():
    # Create budget_item_history table
    op.create_table(
        "budget_item_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("budget_item_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_before", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("related_category_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["budget_item_id"], ["budget_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_category_id"], ["categories.id"], ondelete="SET NULL"),
    )

    # Create indexes for efficient queries
    op.create_index(
        "ix_budget_item_history_budget_item_id", "budget_item_history", ["budget_item_id"]
    )
    op.create_index(
        "ix_budget_item_history_transaction_id", "budget_item_history", ["transaction_id"]
    )
    op.create_index(
        "ix_budget_item_history_related_category_id", "budget_item_history", ["related_category_id"]
    )
    op.create_index(
        "ix_budget_item_history_item_date", "budget_item_history", ["budget_item_id", "created_at"]
    )


def downgrade():
    op.drop_index("ix_budget_item_history_item_date", table_name="budget_item_history")
    op.drop_index("ix_budget_item_history_related_category_id", table_name="budget_item_history")
    op.drop_index("ix_budget_item_history_transaction_id", table_name="budget_item_history")
    op.drop_index("ix_budget_item_history_budget_item_id", table_name="budget_item_history")
    op.drop_table("budget_item_history")
