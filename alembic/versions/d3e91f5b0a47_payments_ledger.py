"""payments ledger (immutable uplata history)

Revision ID: d3e91f5b0a47
Revises: b58fd0c72e19
Create Date: 2026-09-04 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3e91f5b0a47'
down_revision: Union[str, Sequence[str], None] = 'b58fd0c72e19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('plan', sa.String(length=20), nullable=False),
        sa.Column('method', sa.String(length=12), server_default=sa.text("'gotovina'"), nullable=False),
        sa.Column('amount_eur', sa.Numeric(8, 2), nullable=True),
        sa.Column('paid_on', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_payments_user_id', 'payments', ['user_id'])
    op.create_index('ix_payments_paid_on', 'payments', ['paid_on'])
    # Backfill what we can: each membership's latest uplata is at least known.
    op.execute("""
        INSERT INTO payments (user_id, plan, method, paid_on, created_at)
        SELECT user_id, plan, 'gotovina', paid_on, now() FROM memberships
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_payments_paid_on', table_name='payments')
    op.drop_index('ix_payments_user_id', table_name='payments')
    op.drop_table('payments')
