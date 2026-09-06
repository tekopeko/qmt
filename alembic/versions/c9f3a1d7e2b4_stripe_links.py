"""stripe links: customer on users, subscription on memberships, invoice on payments

Revision ID: c9f3a1d7e2b4
Revises: b7e2c94d15a8
Create Date: 2026-09-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9f3a1d7e2b4'
down_revision: Union[str, Sequence[str], None] = 'b7e2c94d15a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('stripe_customer_id', sa.String(length=64), nullable=True))
    op.create_unique_constraint('uq_users_stripe_customer', 'users', ['stripe_customer_id'])
    op.add_column('memberships', sa.Column('stripe_subscription_id', sa.String(length=64), nullable=True))
    op.add_column('memberships', sa.Column('cancel_at_period_end', sa.Boolean(),
                                           nullable=False, server_default=sa.false()))
    op.create_unique_constraint('uq_memberships_stripe_subscription', 'memberships',
                                ['stripe_subscription_id'])
    op.add_column('payments', sa.Column('stripe_invoice_id', sa.String(length=64), nullable=True))
    op.create_unique_constraint('uq_payments_stripe_invoice', 'payments', ['stripe_invoice_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_payments_stripe_invoice', 'payments', type_='unique')
    op.drop_column('payments', 'stripe_invoice_id')
    op.drop_constraint('uq_memberships_stripe_subscription', 'memberships', type_='unique')
    op.drop_column('memberships', 'cancel_at_period_end')
    op.drop_column('memberships', 'stripe_subscription_id')
    op.drop_constraint('uq_users_stripe_customer', 'users', type_='unique')
    op.drop_column('users', 'stripe_customer_id')
