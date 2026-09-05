"""reminders ledger — one row per reminder actually sent

Revision ID: b7e2c94d15a8
Revises: a1d4f80c37b2
Create Date: 2026-09-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2c94d15a8'
down_revision: Union[str, Sequence[str], None] = 'a1d4f80c37b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'reminders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('ref', sa.String(length=60), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'kind', 'ref', name='uq_reminder_once'),
    )
    op.create_index('ix_reminders_user_id', 'reminders', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_reminders_user_id', table_name='reminders')
    op.drop_table('reminders')
