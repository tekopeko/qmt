"""clanarina texts: a "Dodaj plan" card is one text; a plan's gym card prints the plan's yearly price

A DATA migration on site_copy (reading gym_cards, and writing two of its
columns on the way back), no schema change.

/moja-clanarina's "Dodaj plan" (21.10.2026, the owner: "every tab is one
big text cell except the number i.e. price which is connected to the
front page"): a card was its name, a lead (cjenik.<plan>), its price with a
note under it (price.<plan>.note) and two hints, "Za upis se javi treneru
u dvorani." where the plan is not sold by card (cjenik.note) and the line
under its card button (clanarina.card_hint), every piece its own box.
Since that day a card is its name, its prices and ONE text:
cjenik.<plan>.text for the gym's five plans, cjenik.online.<tier>.text for
each of the three QMove tiers. When any of the pieces a plan's card was
made of is in site_copy, this writes the card's text as those pieces as
the site showed them, a line each, in that order: each the edited text
where there is one, else the old default, an empty one dropped; who
touched them last, and when, is the latest of them. None of them: nothing
is written, and the new slot's default (the same lines) renders. The
online plan's lines go into each tier's text. Then every cjenik.<plan>,
cjenik.note, clanarina.card_hint and price.<plan>.note row goes.
Prehrana's note left the registry on 18.10.2026 (its hint is the add-on's
two amounts): a row of it was never read since, so it is not carried, only
deleted.

The gym's cards that stand for plans (gym_cards rows with plans: Dvorana,
grupni; Individualno, individualni and two more) printed their row's
yearly price (year_price / year_unit); since that day they print their
first plan's yearly slots, price.<plan>.year_amount / .year_unit, the ones
that plan's card on /moja-clanarina prints: one number, one slot. A row's
yearly text that is not the default is carried into its plan's slot: the
amount when it is neither "na upit" nor empty (the slot is a number,
required: an empty one is its default), the unit when it is not empty.
The row's columns are left as they are: no page reads them for such a
card any more. Were two rows to stand for the same first plan (none does:
nothing edits a card's plans), the first in the landing's order is
carried.

The defaults are written out here on purpose: a migration must not import
app code, which will have moved on by the time this runs somewhere.

Downgrade, best effort: the first line of each plan's text back into
cjenik.<plan> when it differs from the old lead (the online plan's from
QMove START's text); the other lines are lost (the old app's cjenik.note,
clanarina.card_hint and price.<plan>.note are their defaults again). Each
plan-backed card's yearly columns are set to what the site showed, its
plan's yearly slots (their defaults where there is no row). Then the
texts' and the yearly slots' rows go.

Revision ID: 6e2b9d41c7a3
Revises: c138157ff6bb
Create Date: 2026-10-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e2b9d41c7a3'
down_revision: Union[str, Sequence[str], None] = 'c138157ff6bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# copy.py's defaults before this revision: each plan's lead (cjenik.<plan>)
OLD_LEADS = {
    "grupni": "Satni termini u malim grupama do 8 polaznika — rezerviraš u rasporedu.",
    "individualni": "Rad 1:1 s trenerom, termini po dogovoru.",
    "poluindividualni": "Trening u dvoje ili troje — pola puta između grupe i 1:1.",
    "rehabilitacija": "Programi povratka nakon ozljede, 1:1 stručno vođeni.",
    "online": "Programi po tvojoj razini i cilju, s video uputama — gdje god jesi.",
    "prehrana": "Vođenje prehrane uz aplikaciju MojiMakrosi i zdrave recepte.",
}
# the note under each price (price.<plan>.note), "" where it shipped empty;
# prehrana had none (its slot left the registry on 18.10.2026)
OLD_NOTES = {"grupni": "8, 12 ili 16 treninga", "individualni": "", "poluindividualni": "",
             "rehabilitacija": "paketi od 5 i 10 tretmana", "online": ""}
# the two hints under every card's price: where it is not sold by card, and
# under the card button
OLD_HINTS = (("cjenik.note", "Za upis se javi treneru u dvorani."),
             ("clanarina.card_hint", "Mjesečno, otkazivo bilo kad. Ili gotovinom u dvorani."))
TIERS = ("start", "pro", "elite")                       # models.ONLINE_TIERS
PLAN_TYPES = ("grupni", "individualni", "poluindividualni", "rehabilitacija", "online", "prehrana")
# the plans with yearly slots: all but online (its tiers' yearly prices are
# their landing cards' offer.online*.year_price / .year_unit)
GYM_PLANS = tuple(plan for plan in PLAN_TYPES if plan != "online")
# a yearly price nobody typed: a gym card row's (copy.GYM_CARD_BLANK) and
# the new slots' defaults (copy.YEARLY_PRICE)
YEAR_DEFAULT = ("na upit", "")

site_copy = sa.table(
    "site_copy",
    sa.column("key", sa.String),
    sa.column("text", sa.Text),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("updated_by", sa.Integer),
)
gym_cards = sa.table(
    "gym_cards",
    sa.column("id", sa.Integer),
    sa.column("position", sa.Integer),
    sa.column("year_price", sa.Text),
    sa.column("year_unit", sa.Text),
    sa.column("plans", sa.String),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("updated_by", sa.Integer),
)


def pieces(plan: str) -> list[tuple[str, str]]:
    """The keys a plan's card was made of, in the card's order, each with
    its old default."""
    keys = [(f"cjenik.{plan}", OLD_LEADS[plan])]
    if plan in OLD_NOTES:
        keys.append((f"price.{plan}.note", OLD_NOTES[plan]))
    return keys + list(OLD_HINTS)


def text_keys(plan: str) -> list[str]:
    """The slots a plan's text is now: a gym plan's one, the online plan's
    three (a tier each)."""
    return [f"cjenik.online.{tier}.text" for tier in TIERS] if plan == "online" else [f"cjenik.{plan}.text"]


def default_text(plan: str) -> str:
    """A plan's card as the site showed it when nobody had edited a piece:
    the new slot's default."""
    return "\n".join(text for _, text in pieces(plan) if text)


OLD_KEYS = sorted({key for plan in OLD_LEADS for key, _ in pieces(plan)} | {"price.prehrana.note"})
TEXT_KEYS = [key for plan in OLD_LEADS for key in text_keys(plan)]
YEAR_KEYS = [f"price.{plan}.{part}" for plan in GYM_PLANS for part in ("year_amount", "year_unit")]


def _rows(conn, keys) -> dict:
    return {r.key: r for r in conn.execute(
        sa.select(site_copy.c.key, site_copy.c.text, site_copy.c.updated_at, site_copy.c.updated_by)
        .where(site_copy.c.key.in_(list(keys))))}


def _write(conn, key: str, text: str, row) -> None:
    """One site_copy row, its time and author `row`'s."""
    conn.execute(sa.delete(site_copy).where(site_copy.c.key == key))
    conn.execute(sa.insert(site_copy).values(key=key, text=text, updated_at=row.updated_at, updated_by=row.updated_by))


def plan_cards(conn) -> list[tuple]:
    """(row, its first plan) for each gym card whose first plan has yearly
    slots, in the landing's order; a plan once, its first card's. The
    first plan as the app reads it (models.GymCard.plan_keys): the first
    of its comma-separated plans that is a plan."""
    out, seen = [], set()
    for card in conn.execute(sa.select(gym_cards).order_by(gym_cards.c.position)):
        plans = [p for p in (k.strip() for k in (card.plans or "").split(",")) if p in PLAN_TYPES]
        if plans and plans[0] in GYM_PLANS and plans[0] not in seen:
            seen.add(plans[0])
            out.append((card, plans[0]))
    return out


def fold_texts(conn) -> None:
    """The pieces' rows -> each plan's text row (the online plan's: each
    tier's); the pieces' rows gone."""
    rows = _rows(conn, OLD_KEYS)
    for plan in OLD_LEADS:
        mine = [rows[key] for key, _ in pieces(plan) if key in rows]
        if not mine:
            continue
        lines = (rows[key].text if key in rows else default for key, default in pieces(plan))
        text = "\n".join(line for line in lines if line.strip())
        latest = max(mine, key=lambda r: r.updated_at)       # who last touched this card, and when
        for key in text_keys(plan):
            _write(conn, key, text, latest)
    conn.execute(sa.delete(site_copy).where(site_copy.c.key.in_(OLD_KEYS)))


def fold_years(conn) -> None:
    """A plan-backed gym card's typed yearly price -> its plan's yearly
    slots, the parts that are not the default."""
    for card, plan in plan_cards(conn):
        amount, unit = card.year_price or "", card.year_unit or ""
        if amount.strip() and amount != YEAR_DEFAULT[0]:
            _write(conn, f"price.{plan}.year_amount", amount, card)
        if unit:
            _write(conn, f"price.{plan}.year_unit", unit, card)


def unfold_texts(conn) -> None:
    """The way back: each plan's text's first line -> cjenik.<plan> (an old
    app reads that slot; the online plan's from START's text), when it
    differs from the old lead; the texts' rows gone."""
    rows = _rows(conn, TEXT_KEYS)
    conn.execute(sa.delete(site_copy).where(site_copy.c.key.in_(TEXT_KEYS)))
    for plan, lead in OLD_LEADS.items():
        row = rows.get(text_keys(plan)[0])
        if row is not None and row.text.split("\n", 1)[0] != lead:
            _write(conn, f"cjenik.{plan}", row.text.split("\n", 1)[0], row)


def unfold_years(conn) -> None:
    """The way back: each plan-backed gym card's yearly columns -> what the
    site showed, its plan's yearly slots (or their defaults); those slots'
    rows gone."""
    rows = _rows(conn, YEAR_KEYS)
    for card, plan in plan_cards(conn):
        amount, unit = rows.get(f"price.{plan}.year_amount"), rows.get(f"price.{plan}.year_unit")
        conn.execute(sa.update(gym_cards).where(gym_cards.c.id == card.id).values(
            year_price=amount.text if amount is not None else YEAR_DEFAULT[0],
            year_unit=unit.text if unit is not None else YEAR_DEFAULT[1]))
    conn.execute(sa.delete(site_copy).where(site_copy.c.key.in_(YEAR_KEYS)))


def upgrade() -> None:
    conn = op.get_bind()
    fold_texts(conn)
    fold_years(conn)


def downgrade() -> None:
    conn = op.get_bind()
    unfold_texts(conn)
    unfold_years(conn)
