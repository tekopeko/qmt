"""bazna cijena: every price's base price, a site_copy slot beside it or a gym card's two columns

Croatia's Pravilnik o isticanju bazne cijene proizvoda (NN 132/2026), in
force since 17.11.2026 under art. 7 of the Zakon o zaštiti potrošača:
beside each retail price a trader shows its bazna cijena, for a service the
price applied on 10.9.2026 (or, first offered after that day, its price on
the day it was first offered). The owner (23.11.2026): add it to every
price the site shows; today every base price is the current price.

Every price is a copy slot or a gym card's column. The slots' bases are new
slots of their own (copy.BASE_OF: price.<plan>.amount -> price.<plan>.base,
.year_amount -> .year_base, the QMove tiers' typed prices, the add-on's two
amounts), each defaulting to its price's default; a gym card's own prices
(price, year_price) get two columns, base_price and base_year_price.

This writes what the gym owner typed as its own base, his statement of fact
today: every card's base_price = price and base_year_price = year_price,
and for every price slot site_copy holds a row of, a row for its base with
the price's text (updated_at now, updated_by NULL), unless the base has a
row already. A price nobody typed keeps no row: its base's default is the
price's default, so the two agree without one.

The pairs are written out here on purpose: a migration must not import app
code, which will have moved on by the time this runs somewhere.

Downgrade drops the two columns and deletes the rows of every base slot and
of price.base_label (the words before a base amount): what was typed there
is lost.

Revision ID: 8a67c43d0bb4
Revises: 45c543c860f3
Create Date: 2026-11-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a67c43d0bb4'
down_revision: Union[str, Sequence[str], None] = '45c543c860f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PLAN_TYPES = ("grupni", "individualni", "poluindividualni", "rehabilitacija", "online", "prehrana")
# copy.BASE_OF as this revision makes it: every price slot -> its base's slot
BASE_OF = {
    **{f"price.{plan}.amount": f"price.{plan}.base" for plan in PLAN_TYPES},
    **{f"price.{plan}.year_amount": f"price.{plan}.year_base" for plan in PLAN_TYPES if plan != "online"},
    "offer.online.year_price": "offer.online.year_base",
    "offer.online2.price": "offer.online2.base",
    "offer.online2.year_price": "offer.online2.year_base",
    "offer.online3.price": "offer.online3.base",
    "offer.online3.year_price": "offer.online3.year_base",
    "addon.online": "addon.online.base",
    "addon.dvorana": "addon.dvorana.base",
}
LABEL = "price.base_label"            # the words before every base amount, "Bazna cijena"

site_copy = sa.table(
    "site_copy",
    sa.column("key", sa.String),
    sa.column("text", sa.Text),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("updated_by", sa.Integer),
)


def upgrade() -> None:
    """Upgrade schema: the gym cards' base columns, every typed price its
    own base."""
    op.add_column('gym_cards', sa.Column('base_price', sa.Text(), server_default=sa.text("''"), nullable=False))
    op.add_column('gym_cards', sa.Column('base_year_price', sa.Text(), server_default=sa.text("''"), nullable=False))
    op.execute("UPDATE gym_cards SET base_price = price, base_year_price = year_price")
    conn = op.get_bind()
    rows = dict(conn.execute(sa.select(site_copy.c.key, site_copy.c.text)
                             .where(site_copy.c.key.in_([*BASE_OF, *BASE_OF.values()]))).all())
    for price, base in BASE_OF.items():
        if price in rows and base not in rows:
            conn.execute(sa.insert(site_copy).values(key=base, text=rows[price], updated_at=sa.func.now(),
                                                     updated_by=None))


def downgrade() -> None:
    """Downgrade schema: no base anywhere."""
    op.drop_column('gym_cards', 'base_year_price')
    op.drop_column('gym_cards', 'base_price')
    op.execute(sa.delete(site_copy).where(site_copy.c.key.in_([*BASE_OF.values(), LABEL])))
