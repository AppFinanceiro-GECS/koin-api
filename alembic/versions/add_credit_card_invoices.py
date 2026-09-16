"""add credit card invoices

Revision ID: add_cc_invoices
Revises: add_annual_fee_freq
Create Date: 2026-01-09

"""

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from dateutil.relativedelta import relativedelta
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_cc_invoices"
down_revision: str | None = "add_annual_fee_freq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Criar tabela credit_card_invoices
    op.create_table(
        "credit_card_invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("credit_card_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        # Período de referência
        sa.Column("reference_month", sa.Integer(), nullable=False),
        sa.Column("reference_year", sa.Integer(), nullable=False),
        sa.Column("closing_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        # Valores
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("minimum_payment", sa.Numeric(12, 2), nullable=True),
        # Status e pagamento
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("paid_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("payment_account_id", sa.Integer(), nullable=True),
        sa.Column("payment_transaction_id", sa.Integer(), nullable=True),
        # Notas
        sa.Column("notes", sa.Text(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["credit_card_id"], ["credit_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payment_account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["payment_transaction_id"], ["transactions.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "credit_card_id", "reference_month", "reference_year", name="uq_invoice_card_period"
        ),
    )

    # Índices
    op.create_index("ix_credit_card_invoices_user_id", "credit_card_invoices", ["user_id"])
    op.create_index(
        "ix_credit_card_invoices_credit_card_id", "credit_card_invoices", ["credit_card_id"]
    )
    op.create_index("ix_credit_card_invoices_document_id", "credit_card_invoices", ["document_id"])
    op.create_index("ix_credit_card_invoices_status", "credit_card_invoices", ["status"])
    op.create_index(
        "ix_credit_card_invoices_period",
        "credit_card_invoices",
        ["reference_year", "reference_month"],
    )

    # 2. Adicionar coluna invoice_id na tabela transactions
    op.add_column("transactions", sa.Column("invoice_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_transactions_invoice_id",
        "transactions",
        "credit_card_invoices",
        ["invoice_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_transactions_invoice_id", "transactions", ["invoice_id"])

    # 3. Migrar transações existentes para faturas
    migrate_existing_transactions()


def calculate_invoice_period(closing_day: int, due_day: int, reference_date: date) -> dict:
    """Calcula o período da fatura baseado no closing_day do cartão."""
    # Se a compra foi após o fechamento, vai para a próxima fatura
    if reference_date.day > closing_day:
        next_month = reference_date + relativedelta(months=1)
        ref_month = next_month.month
        ref_year = next_month.year
    else:
        ref_month = reference_date.month
        ref_year = reference_date.year

    # Calcular data de fechamento
    try:
        closing_date = date(ref_year, ref_month, min(closing_day, 28))
    except ValueError:
        closing_date = date(ref_year, ref_month, 28)

    # Calcular data de vencimento
    if due_day < closing_day:
        due_date_month = closing_date + relativedelta(months=1)
        try:
            due_date = date(due_date_month.year, due_date_month.month, min(due_day, 28))
        except ValueError:
            due_date = date(due_date_month.year, due_date_month.month, 28)
    else:
        try:
            due_date = date(ref_year, ref_month, min(due_day, 28))
        except ValueError:
            due_date = date(ref_year, ref_month, 28)

    return {
        "reference_month": ref_month,
        "reference_year": ref_year,
        "closing_date": closing_date,
        "due_date": due_date,
    }


def migrate_existing_transactions() -> None:
    """Migra transações existentes de cartão de crédito para faturas."""
    connection = op.get_bind()

    # Buscar transações de cartão sem fatura
    transactions = connection.execute(
        text("""
        SELECT t.id, t.user_id, t.credit_card_id, t.date, t.amount,
               cc.closing_day, cc.due_day
        FROM transactions t
        JOIN credit_cards cc ON t.credit_card_id = cc.id
        WHERE t.credit_card_id IS NOT NULL
          AND t.invoice_id IS NULL
        ORDER BY t.date
    """)
    ).fetchall()

    if not transactions:
        print("Nenhuma transação para migrar para faturas.")
        return

    print(f"Migrando {len(transactions)} transações para faturas...")

    # Cache de faturas já criadas: (card_id, month, year) -> invoice_id
    invoice_cache = {}
    today = date.today()

    for row in transactions:
        t_id, user_id, card_id, t_date, amount, closing_day, due_day = row

        # Calcular período
        period = calculate_invoice_period(closing_day, due_day, t_date)
        cache_key = (card_id, period["reference_month"], period["reference_year"])

        # Verificar se já temos essa fatura no cache
        if cache_key in invoice_cache:
            invoice_id = invoice_cache[cache_key]
        else:
            # Verificar se já existe no banco
            existing = connection.execute(
                text("""
                SELECT id FROM credit_card_invoices
                WHERE credit_card_id = :card_id
                  AND reference_month = :month
                  AND reference_year = :year
            """),
                {
                    "card_id": card_id,
                    "month": period["reference_month"],
                    "year": period["reference_year"],
                },
            ).fetchone()

            if existing:
                invoice_id = existing[0]
            else:
                # Determinar status inicial
                if period["closing_date"] < today:
                    if period["due_date"] < today:
                        status = "overdue"
                    else:
                        status = "closed"
                else:
                    status = "open"

                # Criar nova fatura
                result = connection.execute(
                    text("""
                    INSERT INTO credit_card_invoices
                    (user_id, credit_card_id, reference_month, reference_year,
                     closing_date, due_date, total_amount, paid_amount, status)
                    VALUES (:user_id, :card_id, :month, :year,
                            :closing_date, :due_date, 0, 0, :status)
                    RETURNING id
                """),
                    {
                        "user_id": user_id,
                        "card_id": card_id,
                        "month": period["reference_month"],
                        "year": period["reference_year"],
                        "closing_date": period["closing_date"],
                        "due_date": period["due_date"],
                        "status": status,
                    },
                )
                invoice_id = result.fetchone()[0]

            invoice_cache[cache_key] = invoice_id

        # Vincular transação à fatura
        connection.execute(
            text("""
            UPDATE transactions SET invoice_id = :invoice_id WHERE id = :t_id
        """),
            {"invoice_id": invoice_id, "t_id": t_id},
        )

    # Atualizar totais das faturas
    connection.execute(
        text("""
        UPDATE credit_card_invoices
        SET total_amount = (
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE invoice_id = credit_card_invoices.id
        )
        WHERE id IN (SELECT DISTINCT invoice_id FROM transactions WHERE invoice_id IS NOT NULL)
    """)
    )

    print(f"Migração concluída: {len(transactions)} transações, {len(invoice_cache)} faturas.")


def downgrade() -> None:
    # Remove foreign key and column from transactions
    op.drop_index("ix_transactions_invoice_id", "transactions")
    op.drop_constraint("fk_transactions_invoice_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "invoice_id")

    # Drop credit_card_invoices table
    op.drop_index("ix_credit_card_invoices_period", "credit_card_invoices")
    op.drop_index("ix_credit_card_invoices_status", "credit_card_invoices")
    op.drop_index("ix_credit_card_invoices_document_id", "credit_card_invoices")
    op.drop_index("ix_credit_card_invoices_credit_card_id", "credit_card_invoices")
    op.drop_index("ix_credit_card_invoices_user_id", "credit_card_invoices")
    op.drop_table("credit_card_invoices")
