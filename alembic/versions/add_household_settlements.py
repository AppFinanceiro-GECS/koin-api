"""divisão das despesas da família: parte de cada membro e acertos

Revision ID: add_household_settlements
Revises: add_document_stage
Create Date: 2026-11-12

household_members.share_percent: parte do membro nas despesas da casa (nulo = igual).
household_settlements: acertos registrados entre membros ("Acertar" no app).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "add_household_settlements"
down_revision: str = "add_document_stage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("household_members") as batch_op:
        batch_op.add_column(sa.Column("share_percent", sa.Numeric(5, 2), nullable=True))

    op.create_table(
        "household_settlements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "license_id",
            sa.Integer(),
            sa.ForeignKey("licenses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_household_settlements_license_id", "household_settlements", ["license_id"])


def downgrade() -> None:
    op.drop_index("ix_household_settlements_license_id", table_name="household_settlements")
    op.drop_table("household_settlements")
    with op.batch_alter_table("household_members") as batch_op:
        batch_op.drop_column("share_percent")
