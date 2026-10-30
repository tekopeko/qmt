"""workout_logs: a client's passes through a day of an online programme

Stage 3 of roadmap/2026-10-29-online-treninzi-spec.md (30.10.2026), the
player and the history. The owner: a client does a day exercise by exercise,
as on Shape Club's Gym Program page, logging sets, reps and kg ("the set log
is good, yes, but default value should be input like in shape club"),
swapping an exercise for a similar one, and finishing with the osvrt ("the
same three for online, yes": napor 1–10, osjećaj, komentar); the tick is
stored "so that we have a record of a user's history. He can repeat the
training if he wants".

One row per pass (models.WorkoutLog): the client (CASCADE), the programme and
the day (SET NULL: the row keeps their snapshots, `program_title` and
`day_label`, taken at the start), when it started (now() by default) and
finished (NULL while it is in progress), how long it took (whole seconds, set
at the finish), `done` (a JSON object: the set log of each exercise saved,
keyed by the day's item id) and `swaps` (a JSON object: item id -> the
similar exercise swapped in), then the osvrt (`effort`, `feeling`, `note`).
A partial unique index, uq_workout_logs_open on (user_id, day_id) WHERE
finished_at IS NULL, keeps one pass in progress per client and day; an index
on (user_id, started_at) serves the history, newest first.

A new table: nothing to carry over. Downgrade drops it, and every pass with
it.

Revision ID: 3890252ee50f
Revises: 7c3bf996c983
Create Date: 2026-10-30 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3890252ee50f'
down_revision: Union[str, Sequence[str], None] = '7c3bf996c983'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "workout_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("programs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("day_id", sa.Integer(), sa.ForeignKey("program_days.id", ondelete="SET NULL"), nullable=True),
        sa.Column("program_title", sa.String(length=160), nullable=False),
        sa.Column("day_label", sa.String(length=200), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elapsed_seconds", sa.Integer(), nullable=True),
        sa.Column("done", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("swaps", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("effort", sa.Integer(), nullable=True),
        sa.Column("feeling", sa.String(length=10), nullable=True),
        sa.Column("note", sa.Text(), server_default=sa.text("''"), nullable=False),
    )
    op.create_index("ix_workout_logs_user_id", "workout_logs", ["user_id"])
    op.create_index("ix_workout_logs_day_id", "workout_logs", ["day_id"])
    op.create_index("ix_workout_logs_user_id_started_at", "workout_logs", ["user_id", "started_at"])
    op.create_index("uq_workout_logs_open", "workout_logs", ["user_id", "day_id"], unique=True,
                    postgresql_where=sa.text("finished_at IS NULL"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("workout_logs")                   # its indexes and foreign keys with it
