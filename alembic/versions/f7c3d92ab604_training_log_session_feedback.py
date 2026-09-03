"""training log becomes per-session feedback

Revision ID: f7c3d92ab604
Revises: e2a9c7b41f58
Create Date: 2026-09-03 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7c3d92ab604'
down_revision: Union[str, Sequence[str], None] = 'e2a9c7b41f58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('training_logs', sa.Column('session_id', sa.Integer(), nullable=True))
    op.add_column('training_logs', sa.Column('feeling', sa.String(length=10), nullable=True))
    op.create_foreign_key('fk_training_logs_session', 'training_logs',
                          'training_sessions', ['session_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_training_logs_session_id', 'training_logs', ['session_id'])
    # NULL session_id (legacy free-form rows) is exempt from uniqueness.
    op.create_unique_constraint('uq_training_log_user_session', 'training_logs',
                                ['user_id', 'session_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_training_log_user_session', 'training_logs', type_='unique')
    op.drop_index('ix_training_logs_session_id', table_name='training_logs')
    op.drop_constraint('fk_training_logs_session', 'training_logs', type_='foreignkey')
    op.drop_column('training_logs', 'feeling')
    op.drop_column('training_logs', 'session_id')
