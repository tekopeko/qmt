"""gym_training_parts: a gym training's part with a name of its own or done as a circuit

Build 3 of roadmap/2026-11-26-gym-training-plan.md, part B (26.11.2026);
Amir: "tu ne mogu staviti kružni dio … nema nigdje da stavi kvačicu...
Pauza itd..."; the owner: "Lets have Glavni dio A, B and C but lets also
allow Amir to rename them." and "the user should be able to choose a
dvoranski programme as a template and then edit the exercises there".

Adds the table gym_training_parts: a row means that part (`section`, one
of models.SECTIONS' keys; db.py checks it, no CHECK here, as
program_day_parts and program_day_circuits) of that gym training has a
name of its own (`title`, String(60), '' for none: the default name)
and / or is done as a circuit: `rounds` (2–20, a CHECK; NULL for a normal
part) rounds, each exercise once per round, and `rest_seconds` (0–3600, a
CHECK; NULL for none) the rest after a round, the circuits table's two
CHECKs. The primary key is (training_id, section): one row per part.
training_id → gym_trainings CASCADE: a training deleted (a cancelled
booking that held nothing, "Obriši trening") takes its parts with it.

No row is made: every part of every training already there keeps its
default name and stays a normal one.

Downgrade drops the table: every part reads its default name again and is
a normal one; its exercises' sets, a circuit's each with its round, stay
stored in gym_training_items as they were (the normal card shows them all).

Revision ID: 36d6e2c97de7
Revises: c4e1b7f9a2d6
Create Date: 2026-11-26 23:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36d6e2c97de7'
down_revision: Union[str, Sequence[str], None] = 'c4e1b7f9a2d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: a gym training's part may have a name and be a circuit."""
    op.create_table(
        'gym_training_parts',
        sa.Column('training_id', sa.Integer(), sa.ForeignKey('gym_trainings.id', ondelete='CASCADE'),
                  primary_key=True, autoincrement=False),
        sa.Column('section', sa.String(length=12), primary_key=True),
        sa.Column('title', sa.String(length=60), server_default=sa.text("''"), nullable=False),
        sa.Column('rounds', sa.Integer(), nullable=True),
        sa.Column('rest_seconds', sa.Integer(), nullable=True),
        sa.CheckConstraint('rounds BETWEEN 2 AND 20', name='ck_gym_training_parts_rounds'),
        sa.CheckConstraint('rest_seconds BETWEEN 0 AND 3600', name='ck_gym_training_parts_rest_seconds'),
    )


def downgrade() -> None:
    """Downgrade schema: every part of every gym training its default name, a normal one."""
    op.drop_table('gym_training_parts')
