"""Add performance indexes for query optimization

Revision ID: add_perf_indexes
Revises: add_known_services
Create Date: 2026-01-13

Adds indexes identified from query pattern analysis to improve performance.
Organized in tiers by impact level.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_perf_indexes"
down_revision = "add_known_services"
branch_labels = None
depends_on = None


def upgrade():
    # ============================================================
    # TIER 1: CRITICAL - Most frequently used query patterns
    # ============================================================

    # Transactions: user_id + date (analytics, reports, monthly summaries)
    op.create_index(
        "ix_transactions_user_date",
        "transactions",
        ["user_id", "date"],
        unique=False,
        if_not_exists=True,
    )

    # Transactions: user_id + type (income/expense filtering)
    op.create_index(
        "ix_transactions_user_type",
        "transactions",
        ["user_id", "type"],
        unique=False,
        if_not_exists=True,
    )

    # Transactions: invoice_id (FK index missing)
    op.create_index(
        "ix_transactions_invoice_id",
        "transactions",
        ["invoice_id"],
        unique=False,
        if_not_exists=True,
    )

    # Transactions: merchant_id (FK index missing)
    op.create_index(
        "ix_transactions_merchant_id",
        "transactions",
        ["merchant_id"],
        unique=False,
        if_not_exists=True,
    )

    # Credit Card Invoices: user + year + month (period queries)
    op.create_index(
        "ix_invoices_user_period",
        "credit_card_invoices",
        ["user_id", "reference_year", "reference_month"],
        unique=False,
        if_not_exists=True,
    )

    # Credit Card Invoices: card + year + month
    op.create_index(
        "ix_invoices_card_period",
        "credit_card_invoices",
        ["credit_card_id", "reference_year", "reference_month"],
        unique=False,
        if_not_exists=True,
    )

    # Credit Card Invoices: user + status (pending invoices)
    op.create_index(
        "ix_invoices_user_status",
        "credit_card_invoices",
        ["user_id", "status"],
        unique=False,
        if_not_exists=True,
    )

    # ============================================================
    # TIER 2: HIGH IMPACT - Common operations
    # ============================================================

    # Transactions: user + is_paid (projected transactions)
    op.create_index(
        "ix_transactions_user_is_paid",
        "transactions",
        ["user_id", "is_paid"],
        unique=False,
        if_not_exists=True,
    )

    # Transactions: credit_card_id + user_id
    op.create_index(
        "ix_transactions_credit_card_user",
        "transactions",
        ["credit_card_id", "user_id"],
        unique=False,
        if_not_exists=True,
    )

    # Documents: user + status (processing queue)
    op.create_index(
        "ix_documents_user_status",
        "documents",
        ["user_id", "status"],
        unique=False,
        if_not_exists=True,
    )

    # Documents: user + created_at (recent docs)
    op.create_index(
        "ix_documents_user_created",
        "documents",
        ["user_id", "created_at"],
        unique=False,
        if_not_exists=True,
    )

    # Categories: user_id (FK index missing)
    op.create_index(
        "ix_categories_user_id", "categories", ["user_id"], unique=False, if_not_exists=True
    )

    # Categories: parent_id (FK index missing)
    op.create_index(
        "ix_categories_parent_id", "categories", ["parent_id"], unique=False, if_not_exists=True
    )

    # Installment Series: user + status
    op.create_index(
        "ix_installment_series_user_status",
        "installment_series",
        ["user_id", "status"],
        unique=False,
        if_not_exists=True,
    )

    # Recurring Transactions: user + status
    op.create_index(
        "ix_recurring_user_status",
        "recurring_transactions",
        ["user_id", "status"],
        unique=False,
        if_not_exists=True,
    )

    # Income Sources: user + is_active
    op.create_index(
        "ix_income_sources_user_active",
        "income_sources",
        ["user_id", "is_active"],
        unique=False,
        if_not_exists=True,
    )

    # Debts: user + status
    op.create_index(
        "ix_debts_user_status", "debts", ["user_id", "status"], unique=False, if_not_exists=True
    )

    # Goals: user + status
    op.create_index(
        "ix_goals_user_status", "goals", ["user_id", "status"], unique=False, if_not_exists=True
    )

    # ============================================================
    # TIER 3: OPTIMIZATION - Less frequent but still beneficial
    # ============================================================

    # Transactions: user + is_recurring
    op.create_index(
        "ix_transactions_user_recurring",
        "transactions",
        ["user_id", "is_recurring"],
        unique=False,
        if_not_exists=True,
    )

    # Transactions: user + is_fixed
    op.create_index(
        "ix_transactions_user_fixed",
        "transactions",
        ["user_id", "is_fixed"],
        unique=False,
        if_not_exists=True,
    )

    # Transactions: user + payment_method
    op.create_index(
        "ix_transactions_user_payment_method",
        "transactions",
        ["user_id", "payment_method"],
        unique=False,
        if_not_exists=True,
    )

    # Credit Card Invoices: payment_account_id (FK index)
    op.create_index(
        "ix_invoices_payment_account",
        "credit_card_invoices",
        ["payment_account_id"],
        unique=False,
        if_not_exists=True,
    )

    # Installment Series: merchant_id (FK index)
    op.create_index(
        "ix_installment_series_merchant",
        "installment_series",
        ["merchant_id"],
        unique=False,
        if_not_exists=True,
    )

    # Merchants: cnpj (deduplication)
    op.create_index("ix_merchants_cnpj", "merchants", ["cnpj"], unique=False, if_not_exists=True)


def downgrade():
    # Drop all indexes in reverse order

    # Tier 3
    op.drop_index("ix_merchants_cnpj", table_name="merchants")
    op.drop_index("ix_installment_series_merchant", table_name="installment_series")
    op.drop_index("ix_invoices_payment_account", table_name="credit_card_invoices")
    op.drop_index("ix_transactions_user_payment_method", table_name="transactions")
    op.drop_index("ix_transactions_user_fixed", table_name="transactions")
    op.drop_index("ix_transactions_user_recurring", table_name="transactions")

    # Tier 2
    op.drop_index("ix_goals_user_status", table_name="goals")
    op.drop_index("ix_debts_user_status", table_name="debts")
    op.drop_index("ix_income_sources_user_active", table_name="income_sources")
    op.drop_index("ix_recurring_user_status", table_name="recurring_transactions")
    op.drop_index("ix_installment_series_user_status", table_name="installment_series")
    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_index("ix_categories_user_id", table_name="categories")
    op.drop_index("ix_documents_user_created", table_name="documents")
    op.drop_index("ix_documents_user_status", table_name="documents")
    op.drop_index("ix_transactions_credit_card_user", table_name="transactions")
    op.drop_index("ix_transactions_user_is_paid", table_name="transactions")

    # Tier 1
    op.drop_index("ix_invoices_user_status", table_name="credit_card_invoices")
    op.drop_index("ix_invoices_card_period", table_name="credit_card_invoices")
    op.drop_index("ix_invoices_user_period", table_name="credit_card_invoices")
    op.drop_index("ix_transactions_merchant_id", table_name="transactions")
    op.drop_index("ix_transactions_invoice_id", table_name="transactions")
    op.drop_index("ix_transactions_user_type", table_name="transactions")
    op.drop_index("ix_transactions_user_date", table_name="transactions")
