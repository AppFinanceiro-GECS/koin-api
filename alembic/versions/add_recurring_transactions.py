"""add recurring_transactions table

Revision ID: add_recurring
Revises: add_token_expires
Create Date: 2026-01-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_recurring"
down_revision: str | None = "add_token_expires"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Criar tabela recurring_transactions
    op.create_table(
        "recurring_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("type", sa.String(10), nullable=False, server_default="expense"),
        sa.Column("frequency", sa.String(10), nullable=False),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_generated_date", sa.Date(), nullable=True),
        sa.Column("next_due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
    )
    op.create_index("ix_recurring_transactions_user_id", "recurring_transactions", ["user_id"])
    op.create_index(
        "ix_recurring_transactions_next_due_date", "recurring_transactions", ["next_due_date"]
    )

    # Adicionar coluna recurring_id na tabela transactions
    op.add_column("transactions", sa.Column("recurring_id", sa.Integer(), nullable=True))
    op.create_index("ix_transactions_recurring_id", "transactions", ["recurring_id"])
    op.create_foreign_key(
        "fk_transactions_recurring_id",
        "transactions",
        "recurring_transactions",
        ["recurring_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Remover FK e coluna de transactions
    op.drop_constraint("fk_transactions_recurring_id", "transactions", type_="foreignkey")
    op.drop_index("ix_transactions_recurring_id", "transactions")
    op.drop_column("transactions", "recurring_id")

    # Remover tabela recurring_transactions
    op.drop_index("ix_recurring_transactions_next_due_date", "recurring_transactions")
    op.drop_index("ix_recurring_transactions_user_id", "recurring_transactions")
    op.drop_table("recurring_transactions")
