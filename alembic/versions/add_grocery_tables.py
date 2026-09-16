"""add_grocery_tables

Revision ID: add_grocery_tables
Revises: ba9ea6b64409
Create Date: 2026-01-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_grocery_tables"
down_revision: str | None = "ba9ea6b64409"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Grocery Products - catalog of products
    op.create_table(
        "grocery_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("necessity_type", sa.String(length=20), nullable=False),
        sa.Column("default_unit", sa.String(length=10), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_grocery_products_user_id"), "grocery_products", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_grocery_products_normalized_name"),
        "grocery_products",
        ["normalized_name"],
        unique=False,
    )

    # Grocery Purchases - items bought
    op.create_table(
        "grocery_purchases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("merchant_id", sa.Integer(), nullable=True),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=10), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("necessity_type", sa.String(length=20), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("ownership_type", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["grocery_products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_grocery_purchases_user_id"), "grocery_purchases", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_grocery_purchases_purchase_date"),
        "grocery_purchases",
        ["purchase_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grocery_purchases_transaction_id"),
        "grocery_purchases",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grocery_purchases_document_id"), "grocery_purchases", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_grocery_purchases_product_id"), "grocery_purchases", ["product_id"], unique=False
    )
    op.create_index(
        op.f("ix_grocery_purchases_merchant_id"), "grocery_purchases", ["merchant_id"], unique=False
    )

    # Grocery Price History - track prices over time
    op.create_table(
        "grocery_price_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("merchant_id", sa.Integer(), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("unit", sa.String(length=10), nullable=False),
        sa.Column("recorded_at", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["grocery_products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_grocery_price_history_product_id"),
        "grocery_price_history",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grocery_price_history_merchant_id"),
        "grocery_price_history",
        ["merchant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grocery_price_history_recorded_at"),
        "grocery_price_history",
        ["recorded_at"],
        unique=False,
    )

    # Shopping Lists - shared with household
    op.create_table(
        "shopping_lists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("license_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("ownership_type", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["license_id"], ["licenses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_shopping_lists_user_id"), "shopping_lists", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_shopping_lists_license_id"), "shopping_lists", ["license_id"], unique=False
    )

    # Shopping List Items
    op.create_table(
        "shopping_list_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("list_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=10), nullable=False),
        sa.Column("estimated_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("necessity_type", sa.String(length=20), nullable=False),
        sa.Column("is_checked", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["list_id"], ["shopping_lists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["grocery_products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_shopping_list_items_list_id"), "shopping_list_items", ["list_id"], unique=False
    )
    op.create_index(
        op.f("ix_shopping_list_items_product_id"),
        "shopping_list_items",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_shopping_list_items_product_id"), table_name="shopping_list_items")
    op.drop_index(op.f("ix_shopping_list_items_list_id"), table_name="shopping_list_items")
    op.drop_table("shopping_list_items")

    op.drop_index(op.f("ix_shopping_lists_license_id"), table_name="shopping_lists")
    op.drop_index(op.f("ix_shopping_lists_user_id"), table_name="shopping_lists")
    op.drop_table("shopping_lists")

    op.drop_index(op.f("ix_grocery_price_history_recorded_at"), table_name="grocery_price_history")
    op.drop_index(op.f("ix_grocery_price_history_merchant_id"), table_name="grocery_price_history")
    op.drop_index(op.f("ix_grocery_price_history_product_id"), table_name="grocery_price_history")
    op.drop_table("grocery_price_history")

    op.drop_index(op.f("ix_grocery_purchases_merchant_id"), table_name="grocery_purchases")
    op.drop_index(op.f("ix_grocery_purchases_product_id"), table_name="grocery_purchases")
    op.drop_index(op.f("ix_grocery_purchases_document_id"), table_name="grocery_purchases")
    op.drop_index(op.f("ix_grocery_purchases_transaction_id"), table_name="grocery_purchases")
    op.drop_index(op.f("ix_grocery_purchases_purchase_date"), table_name="grocery_purchases")
    op.drop_index(op.f("ix_grocery_purchases_user_id"), table_name="grocery_purchases")
    op.drop_table("grocery_purchases")

    op.drop_index(op.f("ix_grocery_products_normalized_name"), table_name="grocery_products")
    op.drop_index(op.f("ix_grocery_products_user_id"), table_name="grocery_products")
    op.drop_table("grocery_products")
