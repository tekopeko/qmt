"""program_day_items.section: two main parts, "Glavni dio A" (trening) and "Glavni dio B" (trening_b)

The owner (23.11.2026), for the gym owner: "in the trainings, he needs an
option to add 'glavni dio A' and 'glavni dio B', so two separate main parts
of a training. The training which he already created can switch the 'glavni
dio' to 'glavni dio A' of course."

A day's sections were three (models.SECTIONS: zagrijavanje, trening,
istezanje), and the CHECK ck_program_day_items_section named them. Since this
revision they are four: trening_b, "Glavni dio B", right after trening, which
reads "Glavni dio A" now. Its key stays, so every item already there (and
every pass's stored section) is simply in Glavni dio A, and nothing is
written: the CHECK is dropped and made again with the four keys, in the
migration's one transaction.

Downgrade puts every item of trening_b into trening (positions are unique
across the day already, so nothing else moves: the day reads the main part
in position order) and the CHECK back to the three keys.

Revision ID: dc22ce1ed7e6
Revises: 8a67c43d0bb4
Create Date: 2026-11-23 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'dc22ce1ed7e6'
down_revision: Union[str, Sequence[str], None] = '8a67c43d0bb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CK = "ck_program_day_items_section"
SECTIONS = ("zagrijavanje", "trening", "trening_b", "istezanje")     # models.SECTIONS' keys, this revision's
OLD_SECTIONS = ("zagrijavanje", "trening", "istezanje")


def _check(keys: tuple[str, ...]) -> None:
    """The CHECK made again, naming these sections."""
    op.drop_constraint(CK, "program_day_items", type_="check")
    op.create_check_constraint(CK, "program_day_items", "section IN (" + ", ".join(f"'{k}'" for k in keys) + ")")


def upgrade() -> None:
    """Upgrade schema: a second main part, trening_b."""
    _check(SECTIONS)


def downgrade() -> None:
    """Downgrade schema: Glavni dio B folded into the one main part."""
    op.execute("UPDATE program_day_items SET section = 'trening' WHERE section = 'trening_b'")
    _check(OLD_SECTIONS)
