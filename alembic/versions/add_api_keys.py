"""Add API Keys table for MCP integration

Revision ID: add_api_keys
Revises: add_nickname_bank_id
Create Date: 2026-01-17

Adds api_keys table for external API access (MCP, integrations).
Users can generate personal API keys to access their data via MCP.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_api_keys"
down_revision = "add_nickname_bank_id"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("key_prefix", sa.String(12), nullable=False, index=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("can_read", sa.Boolean(), nullable=False, default=True),
        sa.Column("can_write", sa.Boolean(), nullable=False, default=False),
        sa.Column("status", sa.String(20), nullable=False, default="active"),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, default=0),
        sa.Column("last_ip", sa.String(45), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("api_keys")
