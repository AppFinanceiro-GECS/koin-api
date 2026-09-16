"""restore removed indexes and add missing foreign keys

Revision ID: restore_indexes_fks
Revises: c4163fa87117
Create Date: 2026-03-23

Restores composite indexes removed in ba9ea6b64409.
Adds missing FK constraints on DocumentExtraction.suggested_category_id
and Merchant.category_id.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "restore_indexes_fks"
down_revision: str = "c4163fa87117"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_index_if_not_exists(name: str, table: str, columns: list[str]):
    """Create index only if it doesn't already exist (safe for re-runs)."""
    cols = ", ".join(columns)
    op.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})"))


def upgrade() -> None:
    # ===== RESTORE INDEXES (idempotent — skips if already exists) =====

    # CreditCardInvoice indexes (removed in ba9ea6b64409)
    _create_index_if_not_exists(
        "ix_invoices_user_status", "credit_card_invoices", ["user_id", "status"]
    )
    _create_index_if_not_exists(
        "ix_invoices_card_period",
        "credit_card_invoices",
        ["credit_card_id", "reference_year", "reference_month"],
    )

    # Category indexes (removed in ba9ea6b64409)
    _create_index_if_not_exists("ix_categories_user", "categories", ["user_id"])
    _create_index_if_not_exists("ix_categories_parent", "categories", ["parent_id"])

    # Missing FK column indexes
    _create_index_if_not_exists("ix_income_sources_category_id", "income_sources", ["category_id"])
    _create_index_if_not_exists(
        "ix_installment_series_category_id", "installment_series", ["category_id"]
    )
    _create_index_if_not_exists(
        "ix_user_merchant_rules_category_id", "user_merchant_rules", ["category_id"]
    )
    _create_index_if_not_exists(
        "ix_transactions_credit_card_id", "transactions", ["credit_card_id"]
    )
    _create_index_if_not_exists("ix_transactions_recurring_id", "transactions", ["recurring_id"])

    # ===== ADD MISSING FOREIGN KEYS =====

    # DocumentExtraction.suggested_category_id → categories.id
    # Clean orphaned references first
    op.execute(
        sa.text("""
        UPDATE document_extractions SET suggested_category_id = NULL
        WHERE suggested_category_id IS NOT NULL
        AND suggested_category_id NOT IN (SELECT id FROM categories)
    """)
    )
    # Add FK only if not exists (check pg_constraint)
    op.execute(
        sa.text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_document_extractions_category') THEN
                ALTER TABLE document_extractions
                ADD CONSTRAINT fk_document_extractions_category
                FOREIGN KEY (suggested_category_id) REFERENCES categories(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)
    )
    _create_index_if_not_exists(
        "ix_document_extractions_category_id", "document_extractions", ["suggested_category_id"]
    )

    # Merchant.category_id → categories.id
    op.execute(
        sa.text("""
        UPDATE merchants SET category_id = NULL
        WHERE category_id IS NOT NULL
        AND category_id NOT IN (SELECT id FROM categories)
    """)
    )
    op.execute(
        sa.text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_merchants_category') THEN
                ALTER TABLE merchants
                ADD CONSTRAINT fk_merchants_category
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)
    )
    _create_index_if_not_exists("ix_merchants_category_id", "merchants", ["category_id"])


def downgrade() -> None:
    # Remove FKs
    op.drop_constraint("fk_merchants_category", "merchants", type_="foreignkey")
    op.drop_index("ix_merchants_category_id", "merchants")
    op.drop_constraint(
        "fk_document_extractions_category", "document_extractions", type_="foreignkey"
    )
    op.drop_index("ix_document_extractions_category_id", "document_extractions")

    # Remove restored indexes
    op.drop_index("ix_transactions_recurring_id", "transactions")
    op.drop_index("ix_transactions_credit_card_id", "transactions")
    op.drop_index("ix_user_merchant_rules_category_id", "user_merchant_rules")
    op.drop_index("ix_installment_series_category_id", "installment_series")
    op.drop_index("ix_income_sources_category_id", "income_sources")
    op.drop_index("ix_categories_parent", "categories")
    op.drop_index("ix_categories_user", "categories")
    op.drop_index("ix_invoices_card_period", "credit_card_invoices")
    op.drop_index("ix_invoices_user_status", "credit_card_invoices")
