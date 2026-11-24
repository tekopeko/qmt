"""programs.venue: a programme is online or dvoranski

The owner (24.11.2026): "A training can be of online training class or gym
training class ('dvoranski' or 'online') and he would like to create
trainings which are only aimed for a gym training."

Adds programs.venue: String(8), NOT NULL, 'online' by default, and the CHECK
ck_programs_venue (venue IN ('online', 'dvorana'): models.VENUES' keys).
Every programme already there is online, seen as before by its razina's
clients. A dvoranski one is the trainer's own plan for the gym: no client
lists or opens it (db.programs_for_level, db.client_can_view: its pages,
its player and its clips are 403 to every client); staff see and run it as
any.

Downgrade drops the CHECK and the column: every programme is online again,
a dvoranski one too (its razina's clients see it).

Revision ID: 49a70497e58a
Revises: 30815c99e7d2
Create Date: 2026-11-24 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '49a70497e58a'
down_revision: Union[str, Sequence[str], None] = '30815c99e7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CK = "ck_programs_venue"
VENUES = ("online", "dvorana")          # models.VENUES' keys, this revision's


def upgrade() -> None:
    """Upgrade schema: every programme online, a gym one possible."""
    op.add_column("programs", sa.Column("venue", sa.String(8), server_default=sa.text("'online'"), nullable=False))
    op.create_check_constraint(CK, "programs", "venue IN (" + ", ".join(f"'{v}'" for v in VENUES) + ")")


def downgrade() -> None:
    """Downgrade schema: every programme online again."""
    op.drop_constraint(CK, "programs", type_="check")
    op.drop_column("programs", "venue")
