"""a training's parts: Glavni dio C, a part's own name, and empty slots

The owner (26.11.2026): "Lets have Glavni dio A, B and C but lets also allow
Amir to rename them."; and for the gym trainings: "we will devise two
templates with no particular exercises connected to them … only slots to
put them in. Also no hard cap on the number of exercises or anything."

Three changes, one revision (build 2 of roadmap/2026-11-26-gym-training-plan.md):

1. Glavni dio C. A day's sections (models.SECTIONS) are five: trening_c,
   "Glavni dio C", right after trening_b. Nothing is written: the CHECK
   ck_program_day_items_section is made again with the five keys, in the
   migration's one transaction (as dc22ce1ed7e6 did for B).
2. A part's own name. The table program_day_parts: a row means that part
   (`section`, one of models.SECTIONS' keys; db.py checks it, no CHECK here)
   of that day is called `title` (String(60)) where the day's pages name
   it. The primary key is (day_id, section): one row per part. day_id →
   program_days CASCADE. No row is made: every part keeps its default name.
3. Empty slots. program_day_items.exercise_id is NULLable (the key and its
   CASCADE as they were) and a column `hint` joins it (String(80), NOT
   NULL, '' by default): an item with no exercise is a slot of a dvoranski
   programme's day, `hint` what goes there ("čučanj"). Every item already
   there holds its exercise and gets no hint.

Downgrade, the other way round: program_day_parts is dropped (the names
are lost, every part reads its default again); every SLOT IS DELETED (an
item with no exercise has no place in a table whose items all hold one:
a template's slots go, its exercises stay), then `hint` is dropped and
exercise_id is NOT NULL again; a circuit on Glavni dio C goes (its items
join Glavni dio B, which is a circuit or not as it was); every item of
trening_c moves to the end of trening_b, in its order (each shifted past
its day's last position, so the positions stay unique and C follows B's
own items), and the CHECK names the four keys again.

Revision ID: a7d3c5e9f214
Revises: 5e8c1a3f7b92
Create Date: 2026-11-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d3c5e9f214'
down_revision: Union[str, Sequence[str], None] = '5e8c1a3f7b92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CK = "ck_program_day_items_section"
SECTIONS = ("zagrijavanje", "trening", "trening_b", "trening_c", "istezanje")   # models.SECTIONS' keys, this revision's
OLD_SECTIONS = ("zagrijavanje", "trening", "trening_b", "istezanje")


def _check(keys: tuple[str, ...]) -> None:
    """The CHECK made again, naming these sections."""
    op.drop_constraint(CK, "program_day_items", type_="check")
    op.create_check_constraint(CK, "program_day_items", "section IN (" + ", ".join(f"'{k}'" for k in keys) + ")")


def upgrade() -> None:
    """Upgrade schema: Glavni dio C, the parts' own names, the slots."""
    _check(SECTIONS)
    op.create_table(
        'program_day_parts',
        sa.Column('day_id', sa.Integer(), sa.ForeignKey('program_days.id', ondelete='CASCADE'),
                  primary_key=True, autoincrement=False),
        sa.Column('section', sa.String(length=12), primary_key=True),
        sa.Column('title', sa.String(length=60), nullable=False),
    )
    op.alter_column('program_day_items', 'exercise_id', existing_type=sa.Integer(), nullable=True)
    op.add_column('program_day_items', sa.Column('hint', sa.String(length=80), server_default=sa.text("''"),
                                                 nullable=False))


def downgrade() -> None:
    """Downgrade schema: no names, no slots, Glavni dio C folded into B."""
    op.drop_table('program_day_parts')
    op.execute("DELETE FROM program_day_items WHERE exercise_id IS NULL")
    op.drop_column('program_day_items', 'hint')
    op.alter_column('program_day_items', 'exercise_id', existing_type=sa.Integer(), nullable=False)
    op.execute("DELETE FROM program_day_circuits WHERE section = 'trening_c'")
    op.execute("UPDATE program_day_items i SET section = 'trening_b', position = i.position + m.top "
               "FROM (SELECT day_id, max(position) AS top FROM program_day_items GROUP BY day_id) m "
               "WHERE i.day_id = m.day_id AND i.section = 'trening_c'")
    _check(OLD_SECTIONS)
