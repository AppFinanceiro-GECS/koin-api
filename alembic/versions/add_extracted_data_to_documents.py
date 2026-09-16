"""add extracted_data to documents

Revision ID: add_extracted_data
Revises: add_receipts
Create Date: 2025-01-21

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_extracted_data"
down_revision: str | None = "add_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add extracted_data column if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'documents' AND column_name = 'extracted_data'
            ) THEN
                ALTER TABLE documents ADD COLUMN extracted_data JSONB;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_column("documents", "extracted_data")
