"""memberships.tier: the online plan's tier (QMove START / PRO / ELITE)

The online plan is sold in three tiers since 20.10.2026, the landing's three
QMove cards (the offer.online / offer.online2 / offer.online3 copy slots).
Until then it had none in the data: one `online` membership, and its member
was shown as the owner of all three cards. `tier` is one of 'start', 'pro',
'elite' for an online membership and NULL for every other plan; each uplata
restates it (db.record_payment).

Every online row already there gets 'start', the base tier, until the
trainer records otherwise on /clanarine (prod has one, Marko Horvat's).

Downgrade drops the column.

Revision ID: 914d4b4556e5
Revises: 78d539161185
Create Date: 2026-10-20 12:16:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '914d4b4556e5'
down_revision: Union[str, Sequence[str], None] = '78d539161185'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('memberships', sa.Column('tier', sa.String(length=10), nullable=True))
    op.execute("UPDATE memberships SET tier = 'start' WHERE plan = 'online'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('memberships', 'tier')
