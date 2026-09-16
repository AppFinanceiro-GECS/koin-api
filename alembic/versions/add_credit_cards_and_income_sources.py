"""add credit cards and income sources

Revision ID: add_credit_income
Revises: add_household
Create Date: 2026-01-07

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_credit_income"
down_revision: str | None = "add_household"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Criar tabela credit_cards
    op.create_table(
        "credit_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("credit_limit", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("closing_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("due_day", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("has_points", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("points_program", sa.String(50), nullable=True),
        sa.Column("points_program_name", sa.String(100), nullable=True),
        sa.Column("points_factor", sa.Numeric(6, 2), nullable=False, server_default="1.0"),
        sa.Column("points_factor_international", sa.Numeric(6, 2), nullable=True),
        sa.Column("card_brand", sa.String(50), nullable=True),
        sa.Column("card_variant", sa.String(100), nullable=True),
        sa.Column("last_four_digits", sa.String(4), nullable=True),
        sa.Column("annual_fee", sa.Numeric(10, 2), nullable=True),
        sa.Column("annual_fee_waived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("benefits_notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("account_id", name="uq_credit_card_account"),
    )
    op.create_index("ix_credit_cards_account_id", "credit_cards", ["account_id"])
    op.create_index("ix_credit_cards_user_id", "credit_cards", ["user_id"])

    # 2. Criar tabela income_sources
    op.create_table(
        "income_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("source_name", sa.String(100), nullable=True),
        sa.Column("expected_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("is_variable", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("frequency", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("payment_day", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("benefit_card_number", sa.String(20), nullable=True),
        sa.Column("benefit_provider", sa.String(50), nullable=True),
        sa.Column("is_taxable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("tax_category", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("ownership_type", sa.String(20), nullable=False, server_default="personal"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_income_sources_user_id", "income_sources", ["user_id"])

    # 3. Adicionar colunas credit_card_id e income_source_id na tabela transactions
    op.add_column("transactions", sa.Column("credit_card_id", sa.Integer(), nullable=True))
    op.add_column("transactions", sa.Column("income_source_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_transactions_credit_card_id",
        "transactions",
        "credit_cards",
        ["credit_card_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_transactions_income_source_id",
        "transactions",
        "income_sources",
        ["income_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_transactions_credit_card_id", "transactions", ["credit_card_id"])
    op.create_index("ix_transactions_income_source_id", "transactions", ["income_source_id"])


def downgrade() -> None:
    # Remove foreign keys and columns from transactions
    op.drop_index("ix_transactions_income_source_id", "transactions")
    op.drop_index("ix_transactions_credit_card_id", "transactions")
    op.drop_constraint("fk_transactions_income_source_id", "transactions", type_="foreignkey")
    op.drop_constraint("fk_transactions_credit_card_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "income_source_id")
    op.drop_column("transactions", "credit_card_id")

    # Drop income_sources table
    op.drop_index("ix_income_sources_user_id", "income_sources")
    op.drop_table("income_sources")

    # Drop credit_cards table
    op.drop_index("ix_credit_cards_user_id", "credit_cards")
    op.drop_index("ix_credit_cards_account_id", "credit_cards")
    op.drop_table("credit_cards")
