"""normaliza e-mails e indice unico em lower(email)

Revision ID: normalize_emails
Revises: add_login_attempts
Create Date: 2026-10-26

Tokens de reset antigos eram o segredo em texto puro. São apagados:
os links já enviados deixam de valer e os novos guardam só o hash.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "normalize_emails"
down_revision: str = "add_login_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMAIL_COLUMNS = (
    ("users", "email"),
    ("invitations", "email"),
    ("login_attempts", "email"),
    ("licenses", "owner_email"),
)


def _reject_duplicates(table: str, column: str) -> None:
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                f"SELECT lower(trim({column})) AS normalized, count(*) AS n "
                f"FROM {table} WHERE {column} IS NOT NULL "
                f"GROUP BY normalized HAVING count(*) > 1"
            )
        )
        .fetchall()
    )
    if rows:
        listed = ", ".join(row[0] for row in rows)
        raise RuntimeError(
            f"E-mails duplicados em {table} depois de normalizar: {listed}. "
            "Resolva o conflito antes de migrar; as contas não são fundidas."
        )


def upgrade() -> None:
    for table, column in _EMAIL_COLUMNS:
        _reject_duplicates(table, column)
        op.execute(
            sa.text(
                f"UPDATE {table} SET {column} = lower(trim({column})) WHERE {column} IS NOT NULL"
            )
        )

    op.execute(sa.text("UPDATE users SET reset_token = NULL, reset_token_expires = NULL"))
    op.execute(sa.text("CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email))"))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_users_email_lower"))
