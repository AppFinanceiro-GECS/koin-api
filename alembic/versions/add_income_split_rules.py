"""Add income_split_rules table and source_transaction_id

Revision ID: add_income_split_rules
Revises: add_first_tx_series
Create Date: 2026-01-22

Sistema de divisao de receitas (Dizimo, Poupanca, etc.)
- Nova tabela income_split_rules para configurar regras de divisao
- Novo campo source_transaction_id em transactions para vincular
  despesas geradas a receita original
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_income_split_rules"
down_revision = "add_first_tx_series"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create income_split_rules table
    op.create_table(
        "income_split_rules",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        # Split configuration
        sa.Column("split_type", sa.String(20), nullable=False),  # "percentage" | "fixed"
        sa.Column("percentage", sa.Numeric(5, 2), nullable=True),  # e.g., 10.00 for 10%
        sa.Column("fixed_amount", sa.Numeric(12, 2), nullable=True),
        # Destination (always expense per user decision)
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "description_template", sa.String(200), nullable=True
        ),  # e.g., "Dizimo (10%) - {description}"
        # Behavior
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("priority", sa.Integer(), nullable=False, default=0),  # Order in list
        # Timestamps
        sa.Column("created_at", sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # 2. Add source_transaction_id to transactions table
    # This links split-generated expenses back to the original income
    op.add_column("transactions", sa.Column("source_transaction_id", sa.Integer(), nullable=True))

    # 3. Create foreign key for source_transaction_id
    op.create_foreign_key(
        "fk_transactions_source_transaction",
        "transactions",
        "transactions",
        ["source_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 4. Create index for faster lookups
    op.create_index(
        "ix_transactions_source_transaction_id", "transactions", ["source_transaction_id"]
    )


def downgrade():
    # Remove from transactions
    op.drop_index("ix_transactions_source_transaction_id", table_name="transactions")
    op.drop_constraint("fk_transactions_source_transaction", "transactions", type_="foreignkey")
    op.drop_column("transactions", "source_transaction_id")

    # Remove income_split_rules table
    op.drop_table("income_split_rules")
