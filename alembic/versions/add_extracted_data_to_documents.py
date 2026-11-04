"""add extracted_data to documents

Revision ID: add_extracted_data
Revises: add_receipts
Create Date: 2025-01-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_extracted_data"
down_revision: str | None = "add_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add extracted_data column if it doesn't exist
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("documents")}
    if "extracted_data" not in columns:
        op.add_column(
            "documents",
            sa.Column("extracted_data", sa.JSON().with_variant(postgresql.JSONB(), "postgresql")),
        )


def downgrade() -> None:
    op.drop_column("documents", "extracted_data")
