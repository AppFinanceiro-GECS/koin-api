"""add receipts and receipt_payments tables

Revision ID: add_receipts
Revises: add_benefit_cards
Create Date: 2026-01-21

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_receipts"
down_revision: str | None = "add_benefit_cards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create receipts table
    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        # Estabelecimento
        sa.Column("store_name", sa.String(200), nullable=False),
        sa.Column("store_cnpj", sa.String(18), nullable=True),
        # Valores
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=True),
        sa.Column("discount", sa.Numeric(12, 2), nullable=True),
        # Data da compra
        sa.Column("purchase_date", sa.Date(), nullable=False),
        # Status
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_receipts_user_id", "receipts", ["user_id"])
    op.create_index("ix_receipts_document_id", "receipts", ["document_id"])
    op.create_index("ix_receipts_purchase_date", "receipts", ["purchase_date"])

    # 2. Create receipt_payments table
    op.create_table(
        "receipt_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("benefit_card_id", sa.Integer(), nullable=True),
        # Dados do pagamento
        sa.Column("payment_method", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        # Label original do OCR
        sa.Column("original_label", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["benefit_card_id"], ["benefit_cards.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_receipt_payments_receipt_id", "receipt_payments", ["receipt_id"])
    op.create_index("ix_receipt_payments_account_id", "receipt_payments", ["account_id"])
    op.create_index("ix_receipt_payments_benefit_card_id", "receipt_payments", ["benefit_card_id"])

    # 3. Add receipt_id column to transactions table
    op.add_column("transactions", sa.Column("receipt_id", sa.Integer(), nullable=True))
    op.create_index("ix_transactions_receipt_id", "transactions", ["receipt_id"])
    op.create_foreign_key(
        "fk_transactions_receipt_id",
        "transactions",
        "receipts",
        ["receipt_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 4. Add receipt_id column to grocery_purchases table
    op.add_column("grocery_purchases", sa.Column("receipt_id", sa.Integer(), nullable=True))
    op.create_index("ix_grocery_purchases_receipt_id", "grocery_purchases", ["receipt_id"])
    op.create_foreign_key(
        "fk_grocery_purchases_receipt_id",
        "grocery_purchases",
        "receipts",
        ["receipt_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Remove FK and column from grocery_purchases
    op.drop_constraint("fk_grocery_purchases_receipt_id", "grocery_purchases", type_="foreignkey")
    op.drop_index("ix_grocery_purchases_receipt_id", table_name="grocery_purchases")
    op.drop_column("grocery_purchases", "receipt_id")

    # Remove FK and column from transactions
    op.drop_constraint("fk_transactions_receipt_id", "transactions", type_="foreignkey")
    op.drop_index("ix_transactions_receipt_id", table_name="transactions")
    op.drop_column("transactions", "receipt_id")

    # Drop receipt_payments
    op.drop_index("ix_receipt_payments_benefit_card_id", table_name="receipt_payments")
    op.drop_index("ix_receipt_payments_account_id", table_name="receipt_payments")
    op.drop_index("ix_receipt_payments_receipt_id", table_name="receipt_payments")
    op.drop_table("receipt_payments")

    # Drop receipts
    op.drop_index("ix_receipts_purchase_date", table_name="receipts")
    op.drop_index("ix_receipts_document_id", table_name="receipts")
    op.drop_index("ix_receipts_user_id", table_name="receipts")
    op.drop_table("receipts")
