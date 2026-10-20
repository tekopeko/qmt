"""gym_cards: the landing's gym cards become rows (offer.dvorana.* / offer.individualno.* fold in)

The gym's section on the landing (#dvorana, under the online tiers) was two
fixed cards, Dvorana and Individualno, each a set of copy slots in
site_copy: offer.<card>.title, .lead and .year_price / .year_unit (texts)
and .points (a list: one row, a JSON array). Since 20.10.2026 the gym owner
adds his own offers beside them ("Treninzi za penziće", "Pilates za cure"),
hides and deletes them, up to eight, as he does the announcements, so the
cards are rows of a new table, gym_cards, in creation order (`position`).

This creates the table and seeds it with the two cards as the site shows
them now: per text the edited site_copy row where there is one, else the
slot's default; the bullets the edited list, or the default list when there
is none (or it cannot be read as one, as copy.load_items had it). Each card
keeps the plans it stands for, the first of which prices it (`plans`:
Dvorana "grupni", Individualno "individualni,poluindividualni,
rehabilitacija"); their own price and unit stay empty, a plan prices them.
Both shown. Then every offer.dvorana.* and offer.individualno.* row goes.

The defaults are written out here on purpose: a migration must not import
app code, which will have moved on by the time this runs somewhere.

Downgrade, best effort: the two cards (found by their plans: a card the
owner adds has none) go back as offer.dvorana.* / offer.individualno.*
rows, only what differs from the old defaults (as an old app reads them),
then the table goes. A card he added is lost, and a card he hid shows again
(the old app has no switch for them).

Revision ID: 78d539161185
Revises: b48179fcf538
Create Date: 2026-10-20 11:18:27.681434

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78d539161185'
down_revision: Union[str, Sequence[str], None] = 'b48179fcf538'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# the offer.<card>.* slots' defaults as copy.py had them before this revision
OLD_DEFAULTS = {
    "dvorana": {"title": "Dvorana", "lead": "Grupni treninzi u Dubravi.",
                "points": ["Male grupe do 8 polaznika", "8, 12 ili 16 treninga mjesečno",
                           "Termin rezerviraš u aplikaciji"],
                "year_price": "na upit", "year_unit": ""},
    "individualno": {"title": "Individualno", "lead": "Trener samo za tebe.",
                     "points": ["Rad 1:1, po dogovoru", "U dvoje ili troje", "Rehabilitacija"],
                     "year_price": "na upit", "year_unit": ""},
}
# the two cards in the landing's order: their slots' prefix and the plans they stand for
CARDS = (("dvorana", "grupni"), ("individualno", "individualni,poluindividualni,rehabilitacija"))
TEXTS = ("title", "lead", "year_price", "year_unit")     # a text slot's last part is the row's column

site_copy = sa.table(
    "site_copy",
    sa.column("key", sa.String),
    sa.column("text", sa.Text),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("updated_by", sa.Integer),
)
gym_cards = sa.table(
    "gym_cards",
    sa.column("position", sa.Integer),
    sa.column("shown", sa.Boolean),
    *(sa.column(c, sa.Text) for c in ("title", "lead", "points", "price", "unit", "year_price", "year_unit")),
    sa.column("plans", sa.String),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("updated_by", sa.Integer),
)
GYM_ROWS = sa.or_(*(site_copy.c.key.like(f"offer.{name}.%") for name, _ in CARDS))


def _items(raw: str | None, default: list[str]) -> list[str]:
    """A list's stored text as the site read it: a JSON array (its items,
    the empty ones dropped), or the default list when it cannot be read as
    one."""
    try:
        data = json.loads(raw) if raw is not None else None
    except ValueError:
        data = None
    if not isinstance(data, list):
        return list(default)
    return [str(x) for x in data if str(x).strip()]


def fold_gym(conn) -> None:
    """offer.dvorana.* / offer.individualno.* rows -> the gym cards at
    positions 1 and 2; those rows gone."""
    rows = {r.key: r for r in conn.execute(
        sa.select(site_copy.c.key, site_copy.c.text, site_copy.c.updated_at, site_copy.c.updated_by)
        .where(GYM_ROWS))}
    for position, (name, plans) in enumerate(CARDS, start=1):
        defaults, prefix = OLD_DEFAULTS[name], f"offer.{name}."
        mine = {key[len(prefix):]: r for key, r in rows.items() if key.startswith(prefix)}
        values = {part: mine[part].text if part in mine else defaults[part] for part in TEXTS}
        items = _items(mine["points"].text, defaults["points"]) if "points" in mine else defaults["points"]
        values.update(points=json.dumps(items, ensure_ascii=False), price="", unit="", plans=plans, shown=True)
        if mine:                                    # who last touched this card, and when
            latest = max(mine.values(), key=lambda r: r.updated_at)
            values.update(updated_at=latest.updated_at, updated_by=latest.updated_by)
        conn.execute(sa.insert(gym_cards).values(position=position, **values))
    conn.execute(sa.delete(site_copy).where(GYM_ROWS))


def unfold_gym(conn) -> None:
    """The way back: the two cards (by their plans) -> offer.dvorana.* /
    offer.individualno.* rows (an old app reads those slots), only what
    differs from the defaults."""
    cards = conn.execute(sa.select(gym_cards).order_by(gym_cards.c.position)).all()
    conn.execute(sa.delete(site_copy).where(GYM_ROWS))
    for name, plans in CARDS:
        row = next((c for c in cards if c.plans == plans), None)
        if row is None:                             # deleted: the old card is its defaults again
            continue
        defaults = OLD_DEFAULTS[name]
        texts = [(part, getattr(row, part)) for part in TEXTS if getattr(row, part) != defaults[part]]
        items = _items(row.points, defaults["points"])
        if items != defaults["points"]:
            texts.append(("points", json.dumps(items, ensure_ascii=False)))
        for part, text in texts:
            conn.execute(sa.insert(site_copy).values(key=f"offer.{name}.{part}", text=text,
                                                     updated_at=row.updated_at, updated_by=row.updated_by))


def upgrade() -> None:
    op.create_table(
        "gym_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("shown", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("title", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("lead", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("points", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("price", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("unit", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("year_price", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("year_unit", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("plans", sa.String(length=80), server_default=sa.text("''"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("position", name="uq_gym_cards_position"),
    )
    fold_gym(op.get_bind())


def downgrade() -> None:
    unfold_gym(op.get_bind())
    op.drop_table("gym_cards")
