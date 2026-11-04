"""program_day_items.exercise_id: ON DELETE CASCADE, an exercise deleted leaves every training that held it

The owner (4.11.2026): "Can you now please allow Amir to delete exercises
even if they are part of some training and that the programme/training
stays but it will just be without that exercise and allow that there is a
training with no exercises. For example the exercise bird dog, he wants to
remove it but he can't without removing it from all trainings."

Until this revision the foreign key from a day's item to its exercise of the
library was ON DELETE RESTRICT: an exercise any day held could not be
deleted, and db.delete_exercise refused it, naming the programmes ("Vježba je
u 3 programa (…) — prvo je makni iz njih."). Since it the key is ON DELETE
CASCADE: deleting an exercise takes its items out of every day that holds
them; the days and the programmes stay (a day left with none says "Trening
još nema vježbi.", and nothing refills it). A pass keeps what it saved of the
exercise (workout_logs.done is a snapshot: its name, its sets).

The constraint keeps its name, program_day_items_exercise_id_fkey: the one
Postgres gave it when 7c3bf996c983 created the table (an unnamed key), the
one the dev database's inspector reports, and the one the model's unnamed key
gets from create_all. It is dropped and made again with the new rule, in the
migration's one transaction. No data changes.

Downgrade puts RESTRICT back: an exercise a day holds cannot be deleted
again. Nothing is lost either way.

Revision ID: 45c543c860f3
Revises: b61e8d5bf1db
Create Date: 2026-11-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '45c543c860f3'
down_revision: Union[str, Sequence[str], None] = 'b61e8d5bf1db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK = "program_day_items_exercise_id_fkey"


def _rule(ondelete: str) -> None:
    """The item's key to its exercise, made again with this ON DELETE rule."""
    op.drop_constraint(FK, "program_day_items", type_="foreignkey")
    op.create_foreign_key(FK, "program_day_items", "exercises", ["exercise_id"], ["id"], ondelete=ondelete)


def upgrade() -> None:
    """Upgrade schema: an exercise deleted takes its items with it."""
    _rule("CASCADE")


def downgrade() -> None:
    """Downgrade schema: an exercise a day holds cannot be deleted."""
    _rule("RESTRICT")
