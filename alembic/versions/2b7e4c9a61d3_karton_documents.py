"""the karton's documents: under "Ograničenja i bolovi", and "Tjelesna kompozicija"

Amir (25.11.2026, on the karton): "Sve je napravio. 1. U ograničenja i
bolovi treba dodati mogućnost da se doda slika ili pdf. 2. Tjelesna masa tu
bi promijenio u tjelesna kompozicija gdje opet mogu dodati pdf ili sliku ili
samo upisati ručno masu."

- limitation_files: a member's documents under "Ograničenja i bolovi" (a
  finding, a scan, a photo of a printout), `file` the stored file's name
  (nalaz-<user id>-<hex>.pdf or .jpg, in storage: data/uploads or R2,
  served by the auth-gated /media to the member and staff only), `name`
  what the list shows; user_id indexed, the member's rows go with him
  (CASCADE). At most ten a member: db.py holds that rule, under his row
  lock.
- weights: an entry of "Tjelesna kompozicija" is a day with a mass, a
  document, or both. `kg` may be NULL now; `file` (String(120), NULL: none)
  is the entry's document (sastav-<user id>-<YYYYMMDD>-<hex>.pdf or .jpg)
  and `file_name` (String(120), NOT NULL, '' by default) what its link
  says; ck_weights_kg_or_file keeps one or the other. One entry a day, as
  before (uq_weights_user_day).

Every weight already there keeps its mass and gets no document; the new
table starts empty.

Downgrade deletes the entries that have no mass (a document alone), then
drops the two columns, the CHECK and the new table, and makes kg NOT NULL
again: what was typed or uploaded in them is lost to the app. Their files
stay in storage, under their names, as the progress photos' do when
0401f7fb9861 is taken back: no row names them any more (an entry that had
a mass and a document keeps its mass, its document's file stays behind).

Revision ID: 2b7e4c9a61d3
Revises: fc1840b0a981
Create Date: 2026-11-25 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b7e4c9a61d3'
down_revision: Union[str, Sequence[str], None] = 'fc1840b0a981'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: documents on the karton."""
    op.create_table(
        'limitation_files',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file', sa.String(length=120), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_limitation_files_user_id', 'limitation_files', ['user_id'])
    op.alter_column('weights', 'kg', existing_type=sa.Numeric(5, 1), nullable=True)
    op.add_column('weights', sa.Column('file', sa.String(length=120), nullable=True))
    op.add_column('weights', sa.Column('file_name', sa.String(length=120), server_default=sa.text("''"),
                                       nullable=False))
    op.create_check_constraint('ck_weights_kg_or_file', 'weights', 'kg IS NOT NULL OR file IS NOT NULL')


def downgrade() -> None:
    """Downgrade schema: a weight is a mass again (the files stay in storage)."""
    op.execute("DELETE FROM weights WHERE kg IS NULL")      # a document alone: its file stays in storage
    op.drop_constraint('ck_weights_kg_or_file', 'weights', type_='check')
    op.drop_column('weights', 'file_name')
    op.drop_column('weights', 'file')
    op.alter_column('weights', 'kg', existing_type=sa.Numeric(5, 1), nullable=False)
    op.drop_index('ix_limitation_files_user_id', table_name='limitation_files')
    op.drop_table('limitation_files')                       # the files stay in storage
