"""training log records a client's own absence

Revision ID: a1d4f80c37b2
Revises: d3e91f5b0a47
Create Date: 2026-09-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1d4f80c37b2'
down_revision: Union[str, Sequence[str], None] = 'd3e91f5b0a47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('training_logs',
                  sa.Column('absent', sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('training_logs', 'absent')
