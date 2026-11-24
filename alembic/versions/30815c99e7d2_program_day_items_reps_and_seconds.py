"""program_day_items: an exercise may ask for reps AND seconds

The owner (24.11.2026), with a photo of the day editor's row for "Bočni
plank 1. razina - bodyweight" (Serije 3, Ponavljanja 5, Sekunde filled)
refused with "Upiši ponavljanja ili sekunde, ne oboje.": "He has some
exercises which he wants to add number of reps as well as length like for
example 5 reps of 30 seconds of plank."

A day's item asked for reps or seconds, never both: the CHECK
ck_program_day_items_reps_or_seconds (reps IS NULL OR seconds IS NULL, made
by 7c3bf996c983) and db.update_day_item's refusal. This drops the CHECK: an
item may hold both, its dose "3 × 5 × 30 s" (ProgramDayItem.dose), the
player's set log SET · PON. · SEK. (db.set_fields), a set saved as
{"reps": 5, "seconds": 30}. No row is written: every item there holds one
of the two, or neither.

Downgrade: an item holding both keeps its reps and loses its seconds (the
seconds typed are lost: "3 × 5 × 30 s" becomes "3 × 5"), then the CHECK
comes back. The passes keep their sets as saved (workout_logs.done is JSON,
no CHECK reads it).

Revision ID: 30815c99e7d2
Revises: 0401f7fb9861
Create Date: 2026-11-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '30815c99e7d2'
down_revision: Union[str, Sequence[str], None] = '0401f7fb9861'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CK = "ck_program_day_items_reps_or_seconds"


def upgrade() -> None:
    """Upgrade schema: reps and seconds together."""
    op.drop_constraint(CK, "program_day_items", type_="check")


def downgrade() -> None:
    """Downgrade schema: one of the two again, the reps kept."""
    op.execute("UPDATE program_day_items SET seconds = NULL WHERE reps IS NOT NULL AND seconds IS NOT NULL")
    op.create_check_constraint(CK, "program_day_items", "reps IS NULL OR seconds IS NULL")
