"""memberships.sessions_per_cycle — 8/12/16 treninga tiers, NULL = unlimited

Revision ID: d4b8e6f1a9c3
Revises: c9f3a1d7e2b4
Create Date: 2026-09-06 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4b8e6f1a9c3'
down_revision: Union[str, Sequence[str], None] = 'c9f3a1d7e2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('memberships', sa.Column('sessions_per_cycle', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('memberships', 'sessions_per_cycle')
