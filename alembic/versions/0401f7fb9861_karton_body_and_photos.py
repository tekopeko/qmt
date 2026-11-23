"""the karton, part 2: height, weight with its history, limitations, a monthly photo

Amir (23.11.2026): "treba mi karton svakog polaznika … tjelesna visina,
tjelesna masa, onda slika jednomjesečno koja će biti proizvoljna i po želji
… Naravno tu će biti ograničenja koja će se on napisati, bolovi itd." The
owner the same day: "Height not needing a history. I agree with the rest."
and "Height is one number, weight a dated history, limitations a free text,
the photo optional and shrunk like the landing's photos, visible to the
member and Amir only."

- users.height_cm: SmallInteger, NULL (none typed). The profile's "Visina
  (cm)", 100–250 (db.read_height).
- users.limitations: Text, NOT NULL, '' by default (none written). The
  karton's "Ograničenja i bolovi", the member's own text, cleaned as copy is.
- weights: one body weight of a member's per day (unique user_id +
  measured_on: a second save that day replaces it, db.set_weight), kg
  Numeric(5, 1) (20–300); the member's rows go with him (CASCADE).
- progress_photos: one photo of a member's per month (unique user_id +
  month: a new one for that month replaces it, db.set_photo), `month` the
  first of the month the photo is OF, `image` the stored file's name
  (napredak-<user id>-<YYYYMM>-<hex>.jpg, in storage: data/uploads or R2,
  served by the auth-gated /media); the member's rows go with him (CASCADE).

Every user already there gets no height and an empty text; the two tables
start empty.

Downgrade drops the two tables and the two columns (what was typed in them
is lost). The photos' files stay in storage, under their names, as the
announcements' photos do when b48179fcf538 is taken back: no row names them
any more.

Revision ID: 0401f7fb9861
Revises: f43e976906a1
Create Date: 2026-11-23 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0401f7fb9861'
down_revision: Union[str, Sequence[str], None] = 'f43e976906a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('height_cm', sa.SmallInteger(), nullable=True))
    op.add_column('users', sa.Column('limitations', sa.Text(), server_default=sa.text("''"), nullable=False))
    op.create_table(
        'weights',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('measured_on', sa.Date(), nullable=False),
        sa.Column('kg', sa.Numeric(5, 1), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # one value a day; its index serves a member's history (user_id first)
        sa.UniqueConstraint('user_id', 'measured_on', name='uq_weights_user_day'),
    )
    op.create_table(
        'progress_photos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('month', sa.Date(), nullable=False),
        sa.Column('image', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # one photo a month; its index serves a member's row of photos
        sa.UniqueConstraint('user_id', 'month', name='uq_progress_photos_user_month'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('progress_photos')               # the files stay in storage
    op.drop_table('weights')
    op.drop_column('users', 'limitations')
    op.drop_column('users', 'height_cm')
