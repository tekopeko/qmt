"""gym_trainings.plan: the gym plan a training staff add outside a termin counts against

28.11.2026. The owner, of staff (Amir) adding a member's training outside the
booked slots ("a training for a user coming to the gym on his own on a
saturday at some time slot"): "Will this extra training slot be counted in the
subscription total? It should be counted. This is also only for people with a
gym membership." Fable put five suggestions to him; he: "I agree with all your
suggestions".

Adds gym_trainings.plan: String(20), NULL for none, and the CHECK
ck_gym_trainings_plan (plan IN the four plans that book termini: grupni,
individualni, poluindividualni, rehabilitacija, models.SESSION_KINDS; NULL
passes it). Staff acting as a member set it when they make him a training
outside a termin, the member never; db._cycle_used counts such a training in
the cycle that holds its day, as a booked termin of that plan. Nothing is
filled: every training there (a member's own, a termin's, one let go of its
termin, one staff made before today) counts nothing, as before.

Downgrade drops the CHECK and the column: no training outside a termin
counts any more, whatever it was set to.

Revision ID: a3f6c1e8d47b
Revises: 9b4e2d7f1c58
Create Date: 2026-11-28 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f6c1e8d47b'
down_revision: Union[str, Sequence[str], None] = '9b4e2d7f1c58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CK = "ck_gym_trainings_plan"
PLANS = ("grupni", "individualni", "poluindividualni", "rehabilitacija")   # models.SESSION_KINDS, this revision's


def upgrade() -> None:
    """Upgrade schema: a training may count against a gym plan; none does."""
    op.add_column("gym_trainings", sa.Column("plan", sa.String(20), nullable=True))
    op.create_check_constraint(CK, "gym_trainings", "plan IN (" + ", ".join(f"'{p}'" for p in PLANS) + ")")


def downgrade() -> None:
    """Downgrade schema: no training outside a termin counts."""
    op.drop_constraint(CK, "gym_trainings", type_="check")
    op.drop_column("gym_trainings", "plan")
