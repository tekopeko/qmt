"""workout_logs.day_label: the passes' stored "Dan N …" read "Trening N …"

The owner (2.11.2026), Amir's wish: "Instead of calling the training parts
Day 1, 2, etc Amir would like them to be called Training 1, Training 2 and
so on so that it is clear." Since this revision a programme's day reads
"Trening 1", "Trening 2 · Gornji dio" (ProgramDay.label). A pass keeps the
label its day had when it started (`day_label`, a snapshot, so a rename
never garbles the history), and the karton prints it: the passes already
stored would say "Dan 1 · Cijelo tijelo" beside a new one's "Trening 1 ·
Cijelo tijelo". So every stored label that starts "Dan <digit>" now starts
"Trening", the rest kept (its number, its title). No schema change.

Downgrade does the reverse: every label that starts "Trening <digit>"
starts "Dan" again (a pass started since this revision too, which is what
the code before it would have stored).

Revision ID: b61e8d5bf1db
Revises: 4f9d6f7103ad
Create Date: 2026-11-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b61e8d5bf1db'
down_revision: Union[str, Sequence[str], None] = '4f9d6f7103ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# substr is 1-based: "Dan 1 · Cijelo tijelo" from 4 is " 1 · Cijelo tijelo"
# ("Dan", 3 characters, cut), "Trening 1 · …" from 8 is " 1 · …" ("Trening", 7)
UPGRADE = ("UPDATE workout_logs SET day_label = 'Trening' || substr(day_label, 4) "
           "WHERE day_label ~ '^Dan [0-9]'")
DOWNGRADE = ("UPDATE workout_logs SET day_label = 'Dan' || substr(day_label, 8) "
             "WHERE day_label ~ '^Trening [0-9]'")


def upgrade() -> None:
    """Upgrade data: "Dan N …" → "Trening N …"."""
    op.execute(UPGRADE)


def downgrade() -> None:
    """Downgrade data: "Trening N …" → "Dan N …"."""
    op.execute(DOWNGRADE)
