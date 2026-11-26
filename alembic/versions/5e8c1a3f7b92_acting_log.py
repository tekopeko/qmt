"""acting_log: the record of staff acting as a member

The owner (26.11.2026): "What if we have a user selection somewhere in the
app for the admins much higher in the hierarchy and then Amir can look at
the app just like the user sees the app and he can do everything the user
does in the same way?"; of what is done that way, "Only a record for me".

Creates acting_log: a row for each entry into a member's account (POST
/kao/<id>) and for every request that is not a GET executed while a staff
member acts as one, read by the owner on /kao/zapisi. `at` (now), the staff
member (`actor_id`) and the member (`member_id`), each a foreign key to
users with ON DELETE SET NULL (a deleted account leaves the trail) and its
name as it was (`actor_name`, `member_name`: the full name, else the
email), the request's `method` and `path` (the path alone, no query), the
response's `status` (NULL when none came). An index on `at`: the page reads
the newest first.

Nothing is there to carry over: the table starts empty.

Downgrade drops the table: the record is lost to the app.

Revision ID: 5e8c1a3f7b92
Revises: d0ed87d5c98f
Create Date: 2026-11-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e8c1a3f7b92'
down_revision: Union[str, Sequence[str], None] = 'd0ed87d5c98f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: the record of acting as a member."""
    op.create_table(
        'acting_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('actor_name', sa.String(length=320), nullable=False),
        sa.Column('member_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('member_name', sa.String(length=320), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('path', sa.String(length=300), nullable=False),
        sa.Column('status', sa.SmallInteger(), nullable=True),
    )
    op.create_index('ix_acting_log_at', 'acting_log', ['at'])


def downgrade() -> None:
    """Downgrade schema: no record."""
    op.drop_index('ix_acting_log_at', table_name='acting_log')
    op.drop_table('acting_log')
