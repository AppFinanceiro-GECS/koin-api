"""merge alembic heads

Revision ID: 61f33914871d
Revises: 3a82572f6835
Create Date: 2026-10-08 00:14:14.323461

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "61f33914871d"
down_revision: str | None = "3a82572f6835"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
