"""hours rows: info.hours.d1 … t3 fold into info.hours.rows; offer.addon goes per tier

A DATA migration on site_copy, no schema change.

The landing's opening hours (#kontakt) were six fixed copy slots, the days
and the hours of three rows (info.hours.d1 / t1 … d3 / t3). Since
20.10.2026 they are one rows slot, info.hours.rows (copy.RowsSlot: a JSON
array of [days, hours] pairs), so the gym owner removes a row, adds one and
leaves a cell empty (his friend emptied "uto" and the box stayed). When any
of the six rows is in site_copy, this writes one info.hours.rows row holding
the three rows as the site shows them now: each cell the edited text where
there is one, else the old default; who touched them last, and when, is the
latest of the six. Then the six go. None of them: nothing is written, the
new slot's default (the same three rows) renders.

The QMove tiers' MojiMakrosi line had one word slot for all three,
offer.addon; each tier has its own since that day (offer.online.addon,
offer.online2.addon, offer.online3.addon). An edited offer.addon is carried
into the three, then deleted.

The defaults are written out here on purpose: a migration must not import
app code, which will have moved on by the time this runs somewhere.

Downgrade, best effort: the first three rows go back into the six keys,
only the cells that differ from the old defaults (an emptied cell as an
empty text, which the old app prints as it is); a row removed comes back
as its old default (the old app has three fixed rows), and rows past the
third are lost. The first tier's word goes back into offer.addon when it
differs from the default, and the three .addon rows go (the other tiers'
words are lost). The tiers' .addon_unit rows stay: the old app never reads
them.

Revision ID: 1a7c144b582a
Revises: 914d4b4556e5
Create Date: 2026-10-20 15:40:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a7c144b582a'
down_revision: Union[str, Sequence[str], None] = '914d4b4556e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# the info.hours.* slots' defaults as copy.py had them before this revision:
# (days, hours) per row
OLD_HOURS = (("pon · sri · čet · pet", "07:00 – 20:00"), ("uto", "individualni termini"), ("sub · ned", "zatvoreno"))
# their keys, (days, hours) per row
HOURS_KEYS = tuple((f"info.hours.d{n}", f"info.hours.t{n}") for n in (1, 2, 3))
ROWS = "info.hours.rows"
# offer.addon's default as copy.py had it, and the three tiers' slots it becomes
OLD_ADDON, ADDON = "MojiMakrosi prehrana", "offer.addon"
TIER_ADDONS = ("offer.online.addon", "offer.online2.addon", "offer.online3.addon")

site_copy = sa.table(
    "site_copy",
    sa.column("key", sa.String),
    sa.column("text", sa.Text),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("updated_by", sa.Integer),
)
OLD_KEYS = [key for pair in HOURS_KEYS for key in pair]


def _rows(conn, keys) -> dict:
    return {r.key: r for r in conn.execute(
        sa.select(site_copy.c.key, site_copy.c.text, site_copy.c.updated_at, site_copy.c.updated_by)
        .where(site_copy.c.key.in_(list(keys))))}


def fold_hours(conn) -> None:
    """info.hours.d1 … t3 rows -> one info.hours.rows row, the six gone."""
    rows = _rows(conn, OLD_KEYS)
    if not rows:
        return
    table = [[rows[key].text if key in rows else default for key, default in zip(keys, defaults)]
             for keys, defaults in zip(HOURS_KEYS, OLD_HOURS)]
    latest = max(rows.values(), key=lambda r: r.updated_at)    # who last touched the hours
    conn.execute(sa.delete(site_copy).where(site_copy.c.key.in_(OLD_KEYS + [ROWS])))
    conn.execute(sa.insert(site_copy).values(key=ROWS, text=json.dumps(table, ensure_ascii=False),
                                             updated_at=latest.updated_at, updated_by=latest.updated_by))


def fold_addon(conn) -> None:
    """An offer.addon row -> the three tiers' .addon rows, offer.addon gone."""
    row = _rows(conn, [ADDON]).get(ADDON)
    if row is None:
        return
    conn.execute(sa.delete(site_copy).where(site_copy.c.key.in_([ADDON, *TIER_ADDONS])))
    for key in TIER_ADDONS:
        conn.execute(sa.insert(site_copy).values(key=key, text=row.text,
                                                 updated_at=row.updated_at, updated_by=row.updated_by))


def unfold_hours(conn) -> None:
    """The way back: the first three rows -> info.hours.d1 … t3 rows (an old
    app reads those slots), only the cells that differ from the defaults."""
    row = _rows(conn, [ROWS]).get(ROWS)
    if row is None:
        return
    try:
        table = json.loads(row.text)
    except ValueError:
        table = None
    if not isinstance(table, list) or not all(isinstance(r, list) and len(r) == 2 for r in table):
        table = [list(pair) for pair in OLD_HOURS]               # unreadable: the default rows, nothing to write
    conn.execute(sa.delete(site_copy).where(site_copy.c.key.in_(OLD_KEYS + [ROWS])))
    for cells, keys, defaults in zip(table, HOURS_KEYS, OLD_HOURS):
        for text, key, default in zip(cells, keys, defaults):
            if str(text) != default:
                conn.execute(sa.insert(site_copy).values(key=key, text=str(text),
                                                         updated_at=row.updated_at, updated_by=row.updated_by))


def unfold_addon(conn) -> None:
    """The way back: the first tier's word -> offer.addon (when it is not
    the default); the three tiers' .addon rows gone."""
    first = _rows(conn, [TIER_ADDONS[0]]).get(TIER_ADDONS[0])
    conn.execute(sa.delete(site_copy).where(site_copy.c.key.in_([ADDON, *TIER_ADDONS])))
    if first is not None and first.text != OLD_ADDON:
        conn.execute(sa.insert(site_copy).values(key=ADDON, text=first.text,
                                                 updated_at=first.updated_at, updated_by=first.updated_by))


def upgrade() -> None:
    conn = op.get_bind()
    fold_hours(conn)
    fold_addon(conn)


def downgrade() -> None:
    conn = op.get_bind()
    unfold_hours(conn)
    unfold_addon(conn)
