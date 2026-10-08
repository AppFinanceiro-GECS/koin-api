"""migrate_credit_card_transactions

Revision ID: 3a82572f6835
Revises: restore_indexes_fks
Create Date: 2026-10-07 19:05:42.841461

"""

from collections.abc import Sequence
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy.sql import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a82572f6835"
down_revision: str | None = "restore_indexes_fks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def calculate_invoice_period(closing_day: int, due_day: int, reference_date: date) -> dict:
    """Função auxiliar isolada na migração para não poluir o sistema."""
    if reference_date.day > closing_day:
        next_month = reference_date + relativedelta(months=1)
        ref_month = next_month.month
        ref_year = next_month.year
    else:
        ref_month = reference_date.month
        ref_year = reference_date.year

    try:
        closing_date = date(ref_year, ref_month, min(closing_day, 28))
    except ValueError:
        closing_date = date(ref_year, ref_month, 28)

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


def upgrade() -> None:
    # A conexão com o banco é fornecida nativamente pelo Alembic
    conn = op.get_bind()

    # 1. Verificar pendências
    result = conn.execute(
        text("""
        SELECT COUNT(*) FROM transactions
        WHERE credit_card_id IS NOT NULL AND invoice_id IS NULL
        """)
    )
    pending_count = result.scalar()

    if pending_count == 0:
        print("Nenhuma transação de cartão pendente para migração.")
        return

    print(f"Migrando {pending_count} transações de cartão para faturas...")

    # 2. Buscar transações
    result = conn.execute(
        text("""
        SELECT t.id, t.user_id, t.credit_card_id, t.date, t.amount,
               cc.closing_day, cc.due_day
        FROM transactions t
        JOIN credit_cards cc ON t.credit_card_id = cc.id
        WHERE t.credit_card_id IS NOT NULL AND t.invoice_id IS NULL
        ORDER BY t.date
        """)
    )
    transactions = result.fetchall()

    invoice_cache = {}
    today = date.today()

    for row in transactions:
        t_id, user_id, card_id, t_date, amount, closing_day, due_day = row

        # Converte strings para date se necessário
        if isinstance(t_date, str):
            t_date = date.fromisoformat(t_date.split(" ")[0])

        period = calculate_invoice_period(closing_day, due_day, t_date)
        cache_key = (card_id, period["reference_month"], period["reference_year"])

        if cache_key in invoice_cache:
            invoice_id = invoice_cache[cache_key]
        else:
            existing = conn.execute(
                text("""
                SELECT id FROM credit_card_invoices
                WHERE credit_card_id = :card_id
                  AND reference_month = :month AND reference_year = :year
                """),
                {
                    "card_id": card_id,
                    "month": period["reference_month"],
                    "year": period["reference_year"],
                },
            )
            existing_row = existing.fetchone()

            if existing_row:
                invoice_id = existing_row[0]
            else:
                if period["closing_date"] < today:
                    status = "overdue" if period["due_date"] < today else "closed"
                else:
                    status = "open"

                result = conn.execute(
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

        # Atualiza a transação para linkar com a fatura criada
        conn.execute(
            text("""
            UPDATE transactions SET invoice_id = :invoice_id WHERE id = :t_id
            """),
            {"invoice_id": invoice_id, "t_id": t_id},
        )

    # 3. Atualizar totais das faturas
    conn.execute(
        text("""
        UPDATE credit_card_invoices
        SET total_amount = (
            SELECT COALESCE(SUM(amount), 0) FROM transactions
            WHERE invoice_id = credit_card_invoices.id
        )
        WHERE id IN (SELECT DISTINCT invoice_id FROM transactions WHERE invoice_id IS NOT NULL)
        """)
    )

    print(
        f"Migração concluída: {len(transactions)} transações migradas em {len(invoice_cache)} faturas."
    )
    invoice_cache.clear()


def downgrade() -> None:
    pass
