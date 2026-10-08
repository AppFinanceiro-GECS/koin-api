"""merge alembic heads

Revision ID: 001c210abce7
Revises: 61f33914871d, add_ai_usage_and_limits
Create Date: 2026-10-08 00:21:40.802560

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001c210abce7"
down_revision: Union[str, None] = ("61f33914871d", "add_ai_usage_and_limits")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
