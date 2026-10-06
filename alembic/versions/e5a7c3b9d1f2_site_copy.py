"""site_copy — texts the trainer or owner edited in place (defaults live in src/qmt/copy.py)

Revision ID: e5a7c3b9d1f2
Revises: d4b8e6f1a9c3
Create Date: 2026-10-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a7c3b9d1f2'
down_revision: Union[str, Sequence[str], None] = 'd4b8e6f1a9c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'site_copy',
        sa.Column('key', sa.String(length=64), primary_key=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('site_copy')
