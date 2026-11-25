"""program_day_items.kg: a planned weight for an exercise of a training

The owner (25.11.2026), for Amir's circuits: "For circular exercises, we
need to allow Amir to add exercises which go into one circle of exercises.
And for each of those exercises, the number of reps, the weight if
applicable etc." (his note to Amir: "Broj krugova, kilaža, itd iste vježbe
kao i ove ubaci").

Adds program_day_items.kg, Numeric(5, 1), NULL: the weight a day asks of
an exercise, in kg ("Kilaža (kg)" on the day editor's row and add forms;
0.5–500 in steps of 0.5, which db.py holds: db.ITEM_LIMITS, no CHECK here,
as for the item's other numbers). The dose says it after a middle dot ("3
× 10 · 20 kg"), and the player's KG field starts from it when the client
has no weight of his own for the exercise.

Every item already there gets none: nothing changes until Amir types one.

Downgrade drops the column: every planned weight typed is lost to the app
(a note that says "8 kg" stays, as it always did).

Revision ID: d0ed87d5c98f
Revises: 2b7e4c9a61d3
Create Date: 2026-11-25 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0ed87d5c98f'
down_revision: Union[str, Sequence[str], None] = '2b7e4c9a61d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: an item may ask for a weight."""
    op.add_column('program_day_items', sa.Column('kg', sa.Numeric(5, 1), nullable=True))


def downgrade() -> None:
    """Downgrade schema: no planned weight."""
    op.drop_column('program_day_items', 'kg')
