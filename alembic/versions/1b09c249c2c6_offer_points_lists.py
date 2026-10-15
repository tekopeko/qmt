"""offer bullets become lists: offer.<card>.p1..p3 fold into offer.<card>.points

A DATA migration on site_copy, no schema change. The landing's offer cards had
three fixed bullet slots each (offer.online.p1..p3, offer.dvorana.p1..p3,
offer.individualno.p1..p3); they are now one list slot per card
(src/qmt/copy.py, ListSlot), stored as one row whose text is a JSON array. A
card with any bullet edited gets its list: the edited bullets where they exist,
the old defaults where they do not, in order. Untouched cards get no row and
show the new defaults.

The old defaults are written out here on purpose: a migration must not import
app code, which will have moved on by the time this runs somewhere.

Revision ID: 1b09c249c2c6
Revises: e5a7c3b9d1f2
Create Date: 2026-10-15 12:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b09c249c2c6'
down_revision: Union[str, Sequence[str], None] = 'e5a7c3b9d1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# the bullets' defaults as copy.py had them before this revision
OLD_DEFAULTS = {
    "online": ("Program po tvojoj razini i cilju", "Video upute za svaku vježbu",
               "Mjesečni Zoom poziv ili susret s trenerom"),
    "dvorana": ("Male grupe do 8 polaznika", "8, 12 ili 16 treninga mjesečno",
                "Termin rezerviraš u aplikaciji"),
    "individualno": ("Rad 1:1, po dogovoru", "U dvoje ili troje", "Rehabilitacija"),
}

site_copy = sa.table(
    "site_copy",
    sa.column("key", sa.String),
    sa.column("text", sa.Text),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("updated_by", sa.Integer),
)


def _clean(text: str) -> str:
    return " ".join(text.split())          # copy.clean, as it was


def fold_points(conn) -> None:
    """p1..p3 rows -> one .points row per card that had any, the pN rows gone."""
    for card, defaults in OLD_DEFAULTS.items():
        keys = [f"offer.{card}.p{n}" for n in (1, 2, 3)]
        rows = {r.key: r for r in conn.execute(
            sa.select(site_copy.c.key, site_copy.c.text, site_copy.c.updated_at, site_copy.c.updated_by)
            .where(site_copy.c.key.in_(keys)))}
        if not rows:
            continue
        items = [_clean(rows[k].text) if k in rows else d for k, d in zip(keys, defaults)]
        items = [t for t in items if t]
        latest = max(rows.values(), key=lambda r: r.updated_at)    # who last touched this card
        points = f"offer.{card}.points"
        conn.execute(sa.delete(site_copy).where(site_copy.c.key.in_(keys + [points])))
        conn.execute(sa.insert(site_copy).values(key=points, text=json.dumps(items, ensure_ascii=False),
                                                 updated_at=latest.updated_at, updated_by=latest.updated_by))


def split_points(conn) -> None:
    """The way back: a .points row -> p1..pN rows (an old app reads p1..p3)."""
    for card in OLD_DEFAULTS:
        points = f"offer.{card}.points"
        row = conn.execute(sa.select(site_copy.c.text, site_copy.c.updated_at, site_copy.c.updated_by)
                           .where(site_copy.c.key == points)).first()
        if row is None:
            continue
        try:
            items = json.loads(row.text)
        except ValueError:
            items = []
        items = [_clean(str(t)) for t in items] if isinstance(items, list) else []
        conn.execute(sa.delete(site_copy).where(site_copy.c.key.like(f"offer.{card}.p_")))
        for n, text in enumerate((t for t in items if t), start=1):
            conn.execute(sa.insert(site_copy).values(key=f"offer.{card}.p{n}", text=text,
                                                     updated_at=row.updated_at, updated_by=row.updated_by))
        conn.execute(sa.delete(site_copy).where(site_copy.c.key == points))


def upgrade() -> None:
    fold_points(op.get_bind())


def downgrade() -> None:
    split_points(op.get_bind())
