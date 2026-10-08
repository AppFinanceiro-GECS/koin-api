"""merge alembic heads

Revision ID: 001c210abce7
Revises: 61f33914871d, add_ai_usage_and_limits
Create Date: 2026-10-08 00:21:40.802560

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "001c210abce7"
down_revision: str | None = ("61f33914871d", "add_ai_usage_and_limits")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
