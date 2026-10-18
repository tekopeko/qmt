"""announcements: the landing's announcement cards become rows (event1.* / event2.* fold in)

The landing's announcements (#aktualno, in the hero) were two fixed sets of
copy slots in site_copy, event1.* and event2.*: tag, title, when, text and
cta (texts), show (a switch, "on" / "off") and image (a stored photo's file
name). Since 18.10.2026 the gym owner adds, hides and deletes them himself,
up to eight, so they are rows of a new table, announcements, in creation
order (`position`). This creates the table and seeds it with the two cards
as the site shows them now: per text the edited site_copy row where there is
one, else the slot's default; shown unless event<n>.show is "off"; the photo
the event<n>.image row names (a name that is a path is no photo, as
copy.image_name had it). Then every event1.* and event2.* row goes. The
photos' files stay where they are, under the same names.

The defaults are written out here on purpose: a migration must not import
app code, which will have moved on by the time this runs somewhere.

Downgrade, best effort: the first two cards (by position) go back as
event1.* / event2.* rows, only what differs from the old defaults (as an old
app reads them), then the table goes. A third card and on are lost, their
photos' files left in storage.

Revision ID: b48179fcf538
Revises: 1b09c249c2c6
Create Date: 2026-10-18 14:35:59.207451

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b48179fcf538'
down_revision: Union[str, Sequence[str], None] = '1b09c249c2c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# the event<n>.* slots' defaults as copy.py had them before this revision
OLD_DEFAULTS = {
    1: {"tag": "Novo", "title": "Treninzi za penziće", "when": "Utorkom i četvrtkom u 10:00",
        "text": "Lagani grupni treninzi za zlatne godine: snaga, ravnoteža i pokretljivost u ugodnom "
                "tempu, uz stručno vodstvo. Prijave u dvorani ili porukom.",
        "cta": "Javi nam se"},
    2: {"tag": "Nova grupa", "title": "Pilates za cure", "when": "Srijedom u 18:00",
        "text": "Pilates u maloj grupi: jezgra, držanje i opuštanje, za sve razine. Prijave u tijeku.",
        "cta": "Javi nam se"},
}
# a text slot's last part -> the row's column ("when" is a keyword in too many places)
COLUMNS = {"tag": "tag", "title": "title", "when": "when_text", "text": "body", "cta": "cta"}

site_copy = sa.table(
    "site_copy",
    sa.column("key", sa.String),
    sa.column("text", sa.Text),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("updated_by", sa.Integer),
)
announcements = sa.table(
    "announcements",
    sa.column("position", sa.Integer),
    sa.column("shown", sa.Boolean),
    *(sa.column(c, sa.Text) for c in COLUMNS.values()),
    sa.column("image", sa.String),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("updated_by", sa.Integer),
)
EVENT_ROWS = sa.or_(site_copy.c.key.like("event1.%"), site_copy.c.key.like("event2.%"))


def _photo(name: str) -> str | None:
    """A stored photo's file name, or None: empty, longer than the column,
    or a path rather than a file (never let near storage)."""
    if not name or len(name) > 128 or "/" in name or "\\" in name or ".." in name:
        return None
    return name


def fold_events(conn) -> None:
    """event1.* / event2.* rows -> the announcements at positions 1 and 2;
    the event rows gone."""
    rows = {r.key: r for r in conn.execute(
        sa.select(site_copy.c.key, site_copy.c.text, site_copy.c.updated_at, site_copy.c.updated_by)
        .where(EVENT_ROWS))}
    for n, defaults in OLD_DEFAULTS.items():
        mine = {key.split(".", 1)[1]: r for key, r in rows.items() if key.startswith(f"event{n}.")}
        values = {column: mine[part].text if part in mine else defaults[part] for part, column in COLUMNS.items()}
        values["shown"] = mine["show"].text != "off" if "show" in mine else True   # copy.flag_on, as it was
        values["image"] = _photo(mine["image"].text) if "image" in mine else None
        if mine:                                    # who last touched this card, and when
            latest = max(mine.values(), key=lambda r: r.updated_at)
            values.update(updated_at=latest.updated_at, updated_by=latest.updated_by)
        conn.execute(sa.insert(announcements).values(position=n, **values))
    conn.execute(sa.delete(site_copy).where(EVENT_ROWS))


def unfold_events(conn) -> None:
    """The way back: the first two announcements -> event1.* / event2.* rows
    (an old app reads those slots), only what differs from the defaults."""
    firsts = conn.execute(sa.select(announcements).order_by(announcements.c.position).limit(2)).all()
    conn.execute(sa.delete(site_copy).where(EVENT_ROWS))
    for n, row in enumerate(firsts, start=1):
        texts = [(part, getattr(row, column)) for part, column in COLUMNS.items()
                 if getattr(row, column) != OLD_DEFAULTS[n][part]]
        if not row.shown:
            texts.append(("show", "off"))
        if row.image:
            texts.append(("image", row.image))
        for part, text in texts:
            conn.execute(sa.insert(site_copy).values(key=f"event{n}.{part}", text=text,
                                                     updated_at=row.updated_at, updated_by=row.updated_by))


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("shown", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("tag", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("title", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("when_text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("body", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("cta", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("image", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("position", name="uq_announcements_position"),
    )
    fold_events(op.get_bind())


def downgrade() -> None:
    unfold_events(op.get_bind())
    op.drop_table("announcements")
