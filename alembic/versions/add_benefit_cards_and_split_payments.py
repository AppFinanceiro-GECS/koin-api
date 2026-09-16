"""add benefit cards and split payments

Revision ID: add_benefit_cards
Revises: add_grocery_tables
Create Date: 2026-01-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_benefit_cards"
down_revision: str | None = "add_grocery_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create benefit_cards table
    op.create_table(
        "benefit_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Card type and provider
        sa.Column(
            "card_type", sa.String(20), nullable=False
        ),  # va, vr, flex, vt, cultura, combustivel
        sa.Column(
            "provider", sa.String(50), nullable=True
        ),  # alelo, sodexo, vr, ticket, flash, ifood, caju
        # Identification
        sa.Column("last_four_digits", sa.String(4), nullable=True),
        # Linked income source for automatic recharge tracking
        sa.Column("linked_income_source_id", sa.Integer(), nullable=True),
        sa.Column("expected_monthly_recharge", sa.Numeric(12, 2), nullable=True),
        sa.Column("recharge_day", sa.Integer(), nullable=True),
        # Status
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["linked_income_source_id"], ["income_sources.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("account_id", name="uq_benefit_card_account"),
    )
    op.create_index("ix_benefit_cards_account_id", "benefit_cards", ["account_id"])
    op.create_index("ix_benefit_cards_user_id", "benefit_cards", ["user_id"])
    op.create_index("ix_benefit_cards_card_type", "benefit_cards", ["card_type"])

    # 2. Create transaction_payments table for split payments
    op.create_table(
        "transaction_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        # Payment details
        sa.Column("payment_method", sa.String(30), nullable=False),  # voucher_va, debit_card, etc.
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        # Optional links to specific card details
        sa.Column("benefit_card_id", sa.Integer(), nullable=True),
        sa.Column("credit_card_id", sa.Integer(), nullable=True),
        # Display order
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["benefit_card_id"], ["benefit_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["credit_card_id"], ["credit_cards.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_transaction_payments_transaction_id", "transaction_payments", ["transaction_id"]
    )
    op.create_index("ix_transaction_payments_account_id", "transaction_payments", ["account_id"])
    op.create_index(
        "ix_transaction_payments_benefit_card_id", "transaction_payments", ["benefit_card_id"]
    )


def downgrade() -> None:
    # Drop transaction_payments
    op.drop_index("ix_transaction_payments_benefit_card_id", table_name="transaction_payments")
    op.drop_index("ix_transaction_payments_account_id", table_name="transaction_payments")
    op.drop_index("ix_transaction_payments_transaction_id", table_name="transaction_payments")
    op.drop_table("transaction_payments")

    # Drop benefit_cards
    op.drop_index("ix_benefit_cards_card_type", table_name="benefit_cards")
    op.drop_index("ix_benefit_cards_user_id", table_name="benefit_cards")
    op.drop_index("ix_benefit_cards_account_id", table_name="benefit_cards")
    op.drop_table("benefit_cards")
