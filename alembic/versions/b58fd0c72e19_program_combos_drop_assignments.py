"""programs get (razina, cilj); per-client assignments dropped

Revision ID: b58fd0c72e19
Revises: a91b3e57cd20
Create Date: 2026-09-03 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b58fd0c72e19'
down_revision: Union[str, Sequence[str], None] = 'a91b3e57cd20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('programs', sa.Column('level', sa.String(length=12), nullable=True))
    op.add_column('programs', sa.Column('goal', sa.String(length=12), nullable=True))
    # the online side is matched by (razina, cilj) now — hand-outs are gone
    op.drop_table('program_assignments')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        'program_assignments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('program_id', 'user_id', 'date', name='uq_assignment_program_user_date'),
    )
    op.drop_column('programs', 'goal')
    op.drop_column('programs', 'level')
