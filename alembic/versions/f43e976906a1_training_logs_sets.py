"""training_logs.sets: the exercises logged with a gym training's osvrt

Amir (23.11.2026): "da si on može sam upisati koji trening je radio …
izračun maksova, na primjer ako radi bench, napravi mi sa 90 kila 6
ponavljanja, ono piše i da mu automatski kalkulira njegov maks u benchu."
The owner's decisions the same day: the exercise log goes on the termin's
osvrt (an exercise picked from the library with the same search, then its
sets, reps and kilograms, several exercises per termin), a member may log a
training done outside a termin in the same form, and the karton estimates
each exercise's max from these sets and the online passes' (Epley).

A training log (the osvrt) held napor, osjećaj and a comment. This adds
`sets`: Text, NOT NULL, '[]' by default, a JSON array, one entry per exercise
logged in the order logged, {"exercise_id": 12, "name": "<the library's name
when logged>", "sets": [{"reps": 10, "kg": 20.0}, …], "at": "<iso>"}
(db.read_log writes it). Every row already there gets '[]': nothing logged.

Downgrade drops the column (the exercises logged in it are lost).

Revision ID: f43e976906a1
Revises: dc22ce1ed7e6
Create Date: 2026-11-23 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f43e976906a1'
down_revision: Union[str, Sequence[str], None] = 'dc22ce1ed7e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('training_logs', sa.Column('sets', sa.Text(), server_default=sa.text("'[]'"), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('training_logs', 'sets')
