"""add login_attempts table

Revision ID: add_login_attempts
Revises: 001c210abce7
Create Date: 2026-10-21

Rastreia falhas de login por e-mail no Postgres (nao em memoria), para
bloqueio progressivo que sobrevive a deploys/restarts (#49).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_login_attempts"
down_revision: str = "001c210abce7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("email", sa.String(255), primary_key=True),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lock_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("login_attempts")
