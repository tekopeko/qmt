"""onboarding_responses: the upitnik v2 (the gym owner's fifteen questions)

The online-trening upitnik is the gym owner's final version since
26.10.2026 (qmt.upitnik): fifteen questions in four parts, a score of 10 to
one decimal (the owner's formula), and two safety rules. A response now
carries:

- version: which questionnaire it answers. Every row already there answers
  the old one (five questions and a goal): 1. A new row is 2 (the server
  default from here on), and the app writes it on every save.
- score: a decimal of 10 ("6,4 / 10") where it was an integer of 14. The
  old rows' integer scores are kept as they are (9 is 9.0).
- pain_level: q14, how often it hurts, 1-10 (NULL on an old row).
- pain_high: q14 at 7 or more, which starts the client at početna whatever
  the score, with a word to see the trainer first.
- needs_review: q15 yes (injuries, operations, conditions), a flag for the
  trainer to look at the profile.
- consented_at: when the consent to process health data, ticked under the
  questionnaire, was given (NULL on an old row: there was no such box).

answers stays the JSON text (its shape is the version's); goal stays the
programmes' matching column (a version-2 response's is always "cijelo").

Downgrade drops the five columns and turns score back to an integer,
rounded. A version-2 row stays a row of the new shape (its answers keyed
by question id), which the old code cannot render on the karton: a
downgrade is for a database without such rows.

Revision ID: e6564d9234b8
Revises: 6e2b9d41c7a3
Create Date: 2026-10-26 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6564d9234b8'
down_revision: Union[str, Sequence[str], None] = '6e2b9d41c7a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # the rows there answer the old questionnaire: 1; a new row 2
    op.add_column('onboarding_responses',
                  sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    op.alter_column('onboarding_responses', 'version', server_default='2')
    op.alter_column('onboarding_responses', 'score', type_=sa.Numeric(4, 1),
                    existing_type=sa.Integer(), existing_nullable=False,
                    postgresql_using='score::numeric(4, 1)')
    op.add_column('onboarding_responses', sa.Column('pain_level', sa.Integer(), nullable=True))
    op.add_column('onboarding_responses',
                  sa.Column('pain_high', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('onboarding_responses',
                  sa.Column('needs_review', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('onboarding_responses',
                  sa.Column('consented_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('onboarding_responses', 'consented_at')
    op.drop_column('onboarding_responses', 'needs_review')
    op.drop_column('onboarding_responses', 'pain_high')
    op.drop_column('onboarding_responses', 'pain_level')
    op.alter_column('onboarding_responses', 'score', type_=sa.Integer(),
                    existing_type=sa.Numeric(4, 1), existing_nullable=False,
                    postgresql_using='round(score)::integer')
    op.drop_column('onboarding_responses', 'version')
