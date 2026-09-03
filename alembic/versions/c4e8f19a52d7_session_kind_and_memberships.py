"""session kind + memberships (članarine)

Revision ID: c4e8f19a52d7
Revises: 73ce539f9248
Create Date: 2026-09-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8f19a52d7'
down_revision: Union[str, Sequence[str], None] = '73ce539f9248'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('session_templates',
                  sa.Column('kind', sa.String(length=20), server_default=sa.text("'grupni'"), nullable=False))
    op.add_column('training_sessions',
                  sa.Column('kind', sa.String(length=20), server_default=sa.text("'grupni'"), nullable=False))
    # Existing data predates kinds; capacity 1 has always meant a 1:1 termin.
    op.execute("UPDATE session_templates SET kind = 'individualni' WHERE capacity = 1")
    op.execute("UPDATE training_sessions SET kind = 'individualni' WHERE capacity = 1")

    op.create_table(
        'memberships',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('plan', sa.String(length=20), nullable=False),
        sa.Column('paid_on', sa.Date(), nullable=False),
        sa.Column('next_payment', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'plan', name='uq_membership_user_plan'),
    )
    op.create_index('ix_memberships_user_id', 'memberships', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_memberships_user_id', table_name='memberships')
    op.drop_table('memberships')
    op.drop_column('training_sessions', 'kind')
    op.drop_column('session_templates', 'kind')
