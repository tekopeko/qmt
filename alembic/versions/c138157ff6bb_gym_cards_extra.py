"""gym_cards.extra: a gym card's extra lines under its bullets

Since 20.10.2026 the gym owner adds plain lines of text, no bullet, under
every card's bullets on the landing ("+ Dodaj tekst", the owner: "Can we
also create a functionality to add text cells?"). The QMove tiers', the
hero's and the contact block's are copy slots (site_copy rows, nothing to
migrate); a gym card's are its row's, a JSON array of strings in a new
column, `extra`, as `points` holds the bullets. Every card already there
gets '[]', no lines: the page is as it was until he adds one.

Downgrade drops the column (the lines typed into it are lost).

Revision ID: c138157ff6bb
Revises: 1a7c144b582a
Create Date: 2026-10-20 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c138157ff6bb'
down_revision: Union[str, Sequence[str], None] = '1a7c144b582a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('gym_cards', sa.Column('extra', sa.Text(), server_default=sa.text("'[]'"), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('gym_cards', 'extra')
