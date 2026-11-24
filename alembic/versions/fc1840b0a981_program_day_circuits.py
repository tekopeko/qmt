"""program_day_circuits: a part of a training done as a circuit (kružni trening)

The owner (24.11.2026): "Amir wants a new type of training called 'kružni
trening' where he has sections of multiple exercises with no pause or a very
short pause between them and then a longer pause between these multiple
sets. Can we add that?"

Adds the table program_day_circuits: a row means that part of that day
(`section`, one of models.SECTIONS' keys: zagrijavanje, trening, trening_b,
istezanje; db.py checks it, no CHECK here) is a circuit: its exercises are
done back to back, once per round, for `rounds` rounds (2–20, a CHECK), with
`rest_seconds` between two rounds (0–3600, a CHECK; NULL for none). The
primary key is (day_id, section): one row per part. day_id → program_days
CASCADE: a day deleted takes its circuits with it.

No row is made: every part already there stays a normal one, as it was.

Downgrade drops the table: every part is a normal one again, and its
items' sets and rests between sets, which stay stored while a part is a
circuit, apply again.

Revision ID: fc1840b0a981
Revises: 49a70497e58a
Create Date: 2026-11-24 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc1840b0a981'
down_revision: Union[str, Sequence[str], None] = '49a70497e58a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: a part of a day may be a circuit."""
    op.create_table(
        'program_day_circuits',
        sa.Column('day_id', sa.Integer(), sa.ForeignKey('program_days.id', ondelete='CASCADE'),
                  primary_key=True, autoincrement=False),
        sa.Column('section', sa.String(length=12), primary_key=True),
        sa.Column('rounds', sa.Integer(), nullable=False),
        sa.Column('rest_seconds', sa.Integer(), nullable=True),
        sa.CheckConstraint('rounds BETWEEN 2 AND 20', name='ck_program_day_circuits_rounds'),
        sa.CheckConstraint('rest_seconds BETWEEN 0 AND 3600', name='ck_program_day_circuits_rest_seconds'),
    )


def downgrade() -> None:
    """Downgrade schema: every part a normal one again."""
    op.drop_table('program_day_circuits')
