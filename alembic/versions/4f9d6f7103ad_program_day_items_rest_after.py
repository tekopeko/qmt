"""program_day_items.rest_after_seconds: the rest after an exercise, before the next one

The owner (30.10.2026): "Can someone click anything after finishing a set of
exercises? We would like to add a timer which he can skip, in between sets as
well as between exercises, which Shape Club also has." A day's item already
holds the rest between its sets (`rest_seconds`, the player's timer after a
set ticked done); nothing held the rest between one exercise and the next,
which Shape Club's list prints ("ODMOR —" between two items). This adds it to
the item, beside the other: `rest_after_seconds`, a nullable Integer, the
seconds of rest after the exercise (0–3600, the day editor's "Nakon vježbe
(s)"); the player counts it down on the next exercise's screen.

Every item already there gets NULL, no rest after it: Amir types one where he
wants it, and until then the player is what it was.

Downgrade drops the column (the rests typed into it are lost).

Revision ID: 4f9d6f7103ad
Revises: 3890252ee50f
Create Date: 2026-10-30 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f9d6f7103ad'
down_revision: Union[str, Sequence[str], None] = '3890252ee50f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('program_day_items', sa.Column('rest_after_seconds', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('program_day_items', 'rest_after_seconds')
