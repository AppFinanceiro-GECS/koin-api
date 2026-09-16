"""add household_members table and ownership_type fields

Revision ID: add_household
Revises: add_recurring
Create Date: 2026-01-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_household"
down_revision: str | None = "add_recurring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Adicionar colunas owner na tabela licenses
    op.add_column("licenses", sa.Column("owner_email", sa.String(255), nullable=True))
    op.add_column("licenses", sa.Column("owner_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_licenses_owner_user_id",
        "licenses",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 2. Criar tabela household_members
    op.create_table(
        "household_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("license_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("nickname", sa.String(50), nullable=True),
        sa.Column("joined_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("invited_by_id", sa.Integer(), nullable=True),
        sa.Column("can_create_transactions", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("can_edit_shared", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("can_invite_members", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("can_see_all", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["license_id"], ["licenses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("license_id", "user_id", name="uq_household_license_user"),
    )
    op.create_index("ix_household_members_license_id", "household_members", ["license_id"])
    op.create_index("ix_household_members_user_id", "household_members", ["user_id"])

    # 3. Adicionar ownership_type em todas as tabelas relevantes
    tables_with_ownership = [
        "accounts",
        "transactions",
        "budgets",
        "goals",
        "debts",
        "recurring_transactions",
    ]
    for table in tables_with_ownership:
        op.add_column(
            table,
            sa.Column("ownership_type", sa.String(20), server_default="personal", nullable=False),
        )

    # 4. Migrar dados existentes: criar HouseholdMember para cada usuario com licenca
    op.execute("""
        INSERT INTO household_members (license_id, user_id, role, can_invite_members, can_see_all)
        SELECT license_id, id, 'owner', true, true
        FROM users
        WHERE license_id IS NOT NULL
    """)

    # 5. Atualizar owner_user_id nas licencas
    op.execute("""
        UPDATE licenses SET owner_user_id = (
            SELECT id FROM users WHERE users.license_id = licenses.id LIMIT 1
        )
    """)


def downgrade() -> None:
    # Remover ownership_type das tabelas
    tables_with_ownership = [
        "accounts",
        "transactions",
        "budgets",
        "goals",
        "debts",
        "recurring_transactions",
    ]
    for table in tables_with_ownership:
        op.drop_column(table, "ownership_type")

    # Remover tabela household_members
    op.drop_index("ix_household_members_user_id", "household_members")
    op.drop_index("ix_household_members_license_id", "household_members")
    op.drop_table("household_members")

    # Remover colunas owner da tabela licenses
    op.drop_constraint("fk_licenses_owner_user_id", "licenses", type_="foreignkey")
    op.drop_column("licenses", "owner_user_id")
    op.drop_column("licenses", "owner_email")
