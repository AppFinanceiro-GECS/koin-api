"""Add license code and invitation model

Revision ID: add_license_code_inv
Revises: 51cb514d2b47
Create Date: 2026-01-06

"""

import secrets
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_license_code_inv"
down_revision: str | None = "51cb514d2b47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def generate_license_code() -> str:
    """Gera código amigável: BIV-XXXX-XXXX"""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    part1 = "".join(secrets.choice(chars) for _ in range(4))
    part2 = "".join(secrets.choice(chars) for _ in range(4))
    return f"BIV-{part1}-{part2}"


def upgrade() -> None:
    # Adicionar coluna code à tabela licenses
    op.add_column("licenses", sa.Column("code", sa.String(13), nullable=True))

    # Gerar códigos para licenças existentes
    conn = op.get_bind()
    licenses = conn.execute(sa.text("SELECT id FROM licenses")).fetchall()
    for lic in licenses:
        code = generate_license_code()
        conn.execute(
            sa.text("UPDATE licenses SET code = :code WHERE id = :id"), {"code": code, "id": lic[0]}
        )

    # Tornar coluna NOT NULL e criar índice único
    with op.batch_alter_table("licenses") as batch_op:
        batch_op.alter_column("code", nullable=False)
        batch_op.create_unique_constraint("uq_licenses_code", ["code"])
        batch_op.create_index("ix_licenses_code", ["code"])

    # Criar tabela de convites
    op.create_table(
        "invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("license_id", sa.Integer(), sa.ForeignKey("licenses.id"), nullable=True),
        sa.Column("invited_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, default="pending"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("invitations")
    with op.batch_alter_table("licenses") as batch_op:
        batch_op.drop_index("ix_licenses_code")
        batch_op.drop_constraint("uq_licenses_code", type_="unique")
        batch_op.drop_column("code")
