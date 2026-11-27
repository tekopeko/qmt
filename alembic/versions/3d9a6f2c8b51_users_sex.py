"""users.sex: the sex a member gives on his profile, for the app's grammar

Build 5 of roadmap/2026-11-26-gym-training-plan.md (27.11.2026). The owner,
of his own karton's "Tvoji online treninzi i treninzi koje upišeš sam/a.":
"on login do we know the sex of the user and then to use the correct
grammar instead of" that. We did not: an account held a name, a birth date,
a phone, a height. Fable proposed an optional "Spol" on the profile, with
which the app resolves the slash forms ("bio/la", "sam/a", "siguran/na")
for each member wherever a text prints (grammar.gendered), and leaves them
as they are for anyone who has not said; the owner: "yes".

Adds users.sex: String(1), NULL for not said, and the CHECK ck_users_sex
(sex IN ('f', 'm'): models.SEXES' keys; NULL passes it). Nothing is filled:
every account there has not said, and reads every page as before.

Downgrade drops the CHECK and the column: every member reads the slash
forms again, whatever he had given.

Revision ID: 3d9a6f2c8b51
Revises: 36d6e2c97de7
Create Date: 2026-11-27 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d9a6f2c8b51'
down_revision: Union[str, Sequence[str], None] = '36d6e2c97de7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CK = "ck_users_sex"
SEXES = ("f", "m")              # models.SEXES' keys, this revision's


def upgrade() -> None:
    """Upgrade schema: a member may give his sex; nobody has."""
    op.add_column("users", sa.Column("sex", sa.String(1), nullable=True))
    op.create_check_constraint(CK, "users", "sex IN (" + ", ".join(f"'{s}'" for s in SEXES) + ")")


def downgrade() -> None:
    """Downgrade schema: no sex on any account."""
    op.drop_constraint(CK, "users", type_="check")
    op.drop_column("users", "sex")
