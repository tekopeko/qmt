"""the gym training: a member's training of a termin, one page that grows

The owner (26.11.2026): "I would remove the 'dodaj trening' and
automatically add the training with its title already after a user booked
it and he can already edit it 4 hours before the training up until the next
day. Amir can also edit it later." … "The training should have a date and
time written on it so that there is no confusion which training they
edit."; his note to Amir: "Kolko je zadano a kolko je napravio i onda
kvačica." Build 3 of roadmap/2026-11-26-gym-training-plan.md, part A: its
own two tables (the online days and passes are not reused).

1. gym_trainings: a member's training (user_id → users CASCADE, indexed), of
   a termin (session_id → training_sessions SET NULL; NULL a training
   outside a termin), its title and start the termin's when it was made
   (snapshots; '' and NULL outside one), held_on its Zagreb date (or the
   date picked), the osvrt (effort, feeling, note) and finished_at (the
   osvrt's first save), created_at / updated_at. A partial unique index,
   uq_gym_trainings_user_session (user_id, session_id) WHERE session_id IS
   NOT NULL: one training a member and termin, made lazily with ON CONFLICT
   DO NOTHING against it.
2. gym_training_items: a training's exercises (training_id CASCADE,
   indexed), each in a part (section, models.SECTIONS' five keys, the CHECK
   ck_gym_training_items_section), its place (position, unique in the
   training, DEFERRABLE INITIALLY DEFERRED: ↑ / ↓ swap two in one commit),
   its exercise (exercise_id → exercises SET NULL, indexed) and that
   exercise's name when added (exercise_name: an exercise deleted from the
   library stays by name), a hint (a slot's, part B), what was given (sets,
   reps, seconds, kg Numeric(5, 1), rest_seconds, note) and what was done
   (done, a JSON list of the ticked sets; effort, the rating; done_at).

Nothing is written: no training exists until a member opens one. The
karton's TrainingLog rows (the plain form of 23.11.2026, its osvrti and its
exercise logs) are not touched: they stay as they are, read as before.

Downgrade drops both tables (the items first), every gym training with
them.

Revision ID: c4e1b7f9a2d6
Revises: a7d3c5e9f214
Create Date: 2026-11-26 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e1b7f9a2d6'
down_revision: Union[str, Sequence[str], None] = 'a7d3c5e9f214'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SECTIONS = ("zagrijavanje", "trening", "trening_b", "trening_c", "istezanje")   # models.SECTIONS' keys, this revision's


def upgrade() -> None:
    """Upgrade schema: gym_trainings and gym_training_items."""
    op.create_table(
        'gym_trainings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('training_sessions.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('title', sa.String(length=160), server_default=sa.text("''"), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('held_on', sa.Date(), nullable=False),
        sa.Column('effort', sa.Integer(), nullable=True),
        sa.Column('feeling', sa.String(length=10), nullable=True),
        sa.Column('note', sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_gym_trainings_user_id', 'gym_trainings', ['user_id'])
    op.create_index('uq_gym_trainings_user_session', 'gym_trainings', ['user_id', 'session_id'], unique=True,
                    postgresql_where=sa.text('session_id IS NOT NULL'))
    op.create_table(
        'gym_training_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('training_id', sa.Integer(), sa.ForeignKey('gym_trainings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('section', sa.String(length=12), server_default=sa.text("'trening'"), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('exercise_id', sa.Integer(), sa.ForeignKey('exercises.id', ondelete='SET NULL'), nullable=True),
        sa.Column('exercise_name', sa.String(length=160), server_default=sa.text("''"), nullable=False),
        sa.Column('hint', sa.String(length=80), server_default=sa.text("''"), nullable=False),
        sa.Column('sets', sa.Integer(), nullable=True),
        sa.Column('reps', sa.Integer(), nullable=True),
        sa.Column('seconds', sa.Integer(), nullable=True),
        sa.Column('kg', sa.Numeric(5, 1), nullable=True),
        sa.Column('rest_seconds', sa.Integer(), nullable=True),
        sa.Column('note', sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column('done', sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column('effort', sa.Integer(), nullable=True),
        sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('training_id', 'position', name='uq_gym_training_items_position',
                            deferrable=True, initially='DEFERRED'),
        sa.CheckConstraint("section IN (" + ", ".join(f"'{k}'" for k in SECTIONS) + ")",
                           name='ck_gym_training_items_section'),
    )
    op.create_index('ix_gym_training_items_training_id', 'gym_training_items', ['training_id'])
    op.create_index('ix_gym_training_items_exercise_id', 'gym_training_items', ['exercise_id'])


def downgrade() -> None:
    """Downgrade schema: both tables dropped, every gym training with them."""
    op.drop_table('gym_training_items')
    op.drop_table('gym_trainings')
