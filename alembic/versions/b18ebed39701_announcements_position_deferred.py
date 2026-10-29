"""announcements: the position's unique constraint deferred, so ↑ / ↓ can swap two cards

The owner (29.10.2026): "Lets make it so that Amir can change the order of
these announcement pages as well as edit them and create/remove them." The
landing's announcements showed in creation order (`position`), and nothing
reordered them. Since this revision the editor's ↑ / ↓ swap a card's
position with its neighbour's (db.move_announcement): the two rows trade
values in one flush, which an immediate unique constraint refuses at the
first UPDATE (two rows hold one position until the second lands). So
uq_announcements_position becomes DEFERRABLE INITIALLY DEFERRED, as
uq_upitnik_questions_position is: checked when the swap commits, whole.
No row changes.

Downgrade makes it immediate again; the positions are unique at every
commit, so it holds.

Revision ID: b18ebed39701
Revises: 5c1e7a9d2b48
Create Date: 2026-10-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b18ebed39701'
down_revision: Union[str, Sequence[str], None] = '5c1e7a9d2b48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("uq_announcements_position", "announcements", type_="unique")
    op.create_unique_constraint("uq_announcements_position", "announcements", ["position"],
                                deferrable=True, initially="DEFERRED")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_announcements_position", "announcements", type_="unique")
    op.create_unique_constraint("uq_announcements_position", "announcements", ["position"])
