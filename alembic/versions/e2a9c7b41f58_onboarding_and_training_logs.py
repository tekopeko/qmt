"""onboarding upitnik + training logs (karton)

Revision ID: e2a9c7b41f58
Revises: c4e8f19a52d7
Create Date: 2026-09-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2a9c7b41f58'
down_revision: Union[str, Sequence[str], None] = 'c4e8f19a52d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'onboarding_responses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('answers', sa.Text(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('level', sa.String(length=12), nullable=False),
        sa.Column('goal', sa.String(length=12), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_onboarding_responses_user_id', 'onboarding_responses', ['user_id'])

    op.create_table(
        'training_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('effort', sa.Integer(), nullable=True),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_training_logs_user_id', 'training_logs', ['user_id'])
    op.create_index('ix_training_logs_date', 'training_logs', ['date'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_training_logs_date', table_name='training_logs')
    op.drop_index('ix_training_logs_user_id', table_name='training_logs')
    op.drop_table('training_logs')
    op.drop_index('ix_onboarding_responses_user_id', table_name='onboarding_responses')
    op.drop_table('onboarding_responses')
