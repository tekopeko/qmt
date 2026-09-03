"""user profile fields (prezime, datum rođenja, telefon)

Revision ID: a91b3e57cd20
Revises: f7c3d92ab604
Create Date: 2026-09-03 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a91b3e57cd20'
down_revision: Union[str, Sequence[str], None] = 'f7c3d92ab604'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('last_name', sa.String(length=120), nullable=True))
    op.add_column('users', sa.Column('birth_date', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('phone', sa.String(length=40), nullable=True))
    # `name` has held "Ime Prezime" until now — split what splits cleanly so
    # existing accounts don't all bounce to /profil for data they already gave.
    op.execute("""
        UPDATE users
           SET last_name = split_part(name, ' ', 2),
               name = split_part(name, ' ', 1)
         WHERE name LIKE '% %' AND split_part(name, ' ', 3) = ''
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE users SET name = trim(name || ' ' || coalesce(last_name, ''))")
    op.drop_column('users', 'phone')
    op.drop_column('users', 'birth_date')
    op.drop_column('users', 'last_name')
