"""program_days: a programme is made of days, a day of its exercises in three sections

The owner (29.10.2026): "For each group he needs to add the training
programme per days which the user will declare as an exercise performed one
by one"; "Dan 1, … Dan N with suggested days in the week but the user can
do them whenever he wants"; per exercise "sets × reps, or seconds, rest
between sets, a note. That is it for now"; and (30.10.2026) a day has
sections, "warm up and main" (Shape's third, istezanje, allowed). Stage 2 of
roadmap/2026-10-29-online-treninzi-spec.md. Until this revision a programme
was a flat list of program_items, each an exercise of the library and a
`note` holding its razina's dose ("3 × 8 · 8 kg"). Since it a programme is a
list of days (`program_days`: its place, an optional title, a suggested
weekday, an intro, an intro video) and a day a list of items
(`program_day_items`: its place, its section, the exercise, sets, reps or
seconds, the rest between sets, a note).

This creates the two tables, then gives every programme that has items ONE
day (position 1, no title, no weekday, no intro) holding its items in their
order, in section "trening", no rest, each item's note parsed by
parse_dose(note) -> (sets, reps, seconds, note):

- the note must match ^\\s*(\\d{1,2})\\s*[×xX]\\s*(\\d{1,4})\\s*(s|sek|sec)?\\b\\s*(.*)$
  (case-insensitive): the first number is the sets, the second the reps, or
  the seconds when a unit (s, sek, sec) follows it;
- the rest is the item's note, with a leading "·", "-", "–" or "—" and
  whitespace stripped, and one pair of parentheses around the whole of it
  removed;
- a note that does not match is kept whole as the note, nothing set.

  "3 × 8 · 8 kg"      -> (3, 8, None, "8 kg")
  "3 × 20 s"          -> (3, None, 20, "")
  "3 × 5 (s koljena)" -> (3, 5, None, "s koljena")
  "3 × 6 po nozi"     -> (3, 6, None, "po nozi")
  "3 × 10 · 2 × 6 kg" -> (3, 10, None, "2 × 6 kg")
  ""                  -> (None, None, None, "")
  "Tempo 3-1-1"       -> (None, None, None, "Tempo 3-1-1")

A programme with no items gets no day (the app's skeletons fill a slot with
no day when the trainer opens /treninzi; any other is Amir's to fill). One
line is printed per programme it gives a day. Then program_items goes.

The rules are written out here on purpose: a migration must not import app
code, which will have moved on by the time this runs somewhere.

Downgrade, best effort: program_items back (program_id, position counting on
across the days, in each day's display order: its sections in their order,
each in position order; the exercise; the note the dose and the note joined
by " · ", whichever is set alone, as the app words a dose: "3 × 10", "3 × 30
s", "10 ponavljanja", "30 s", "3 serije"), then the two tables go. What
only the days hold is lost: the days themselves (their titles, weekdays and
intros), the sections, the rest, and the intro videos' names (their files
stay in storage).

Revision ID: 7c3bf996c983
Revises: 4c2e8a6f1d39
Create Date: 2026-10-30 18:00:00.000000

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c3bf996c983'
down_revision: Union[str, Sequence[str], None] = '4c2e8a6f1d39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

programs = sa.table(
    "programs",
    sa.column("id", sa.Integer),
    sa.column("title", sa.String),
)
items = sa.table(
    "program_items",
    sa.column("id", sa.Integer),
    sa.column("program_id", sa.Integer),
    sa.column("position", sa.Integer),
    sa.column("exercise_id", sa.Integer),
    sa.column("note", sa.Text),
)
days = sa.table(
    "program_days",
    sa.column("id", sa.Integer),
    sa.column("program_id", sa.Integer),
    sa.column("position", sa.Integer),
    sa.column("title", sa.String),
    sa.column("weekday", sa.Integer),
    sa.column("intro", sa.Text),
)
day_items = sa.table(
    "program_day_items",
    sa.column("id", sa.Integer),
    sa.column("day_id", sa.Integer),
    sa.column("position", sa.Integer),
    sa.column("section", sa.String),
    sa.column("exercise_id", sa.Integer),
    sa.column("sets", sa.Integer),
    sa.column("reps", sa.Integer),
    sa.column("seconds", sa.Integer),
    sa.column("rest_seconds", sa.Integer),
    sa.column("note", sa.Text),
)

SECTIONS = ("zagrijavanje", "trening", "istezanje")       # the day's order
_DOSE = re.compile(r"^\s*(\d{1,2})\s*[×xX]\s*(\d{1,4})\s*(s|sek|sec)?\b\s*(.*)$", re.IGNORECASE)


def _unwrapped(text: str) -> str:
    """The text without one pair of parentheses around the whole of it
    ("(s koljena)" -> "s koljena"); "(a) i (b)" stays: its first one closes
    before the end."""
    if not (text.startswith("(") and text.endswith(")")):
        return text
    depth = 0
    for i, ch in enumerate(text):
        depth += (ch == "(") - (ch == ")")
        if depth == 0 and i < len(text) - 1:
            return text
    return text[1:-1].strip() if depth == 0 else text


def parse_dose(note: str | None) -> tuple[int | None, int | None, int | None, str]:
    """An old item's note -> (sets, reps, seconds, note): the dose it starts
    with ("3 × 8", "3 × 20 s") and what follows it, the module's rules."""
    note = note or ""
    m = _DOSE.match(note)
    if m is None:
        return None, None, None, note
    sets, count, unit, rest = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    rest = _unwrapped(re.sub(r"^[\s·\-–—]+", "", rest).strip())
    return (sets, None, count, rest) if unit else (sets, count, None, rest)


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def dose_text(sets: int | None, reps: int | None, seconds: int | None) -> str:
    """A dose as the app words it (models.ProgramDayItem.dose)."""
    if sets is not None and reps is not None:
        return f"{sets} × {reps}"
    if sets is not None and seconds is not None:
        return f"{sets} × {seconds} s"
    if reps is not None:
        return f"{reps} {_plural(reps, 'ponavljanje', 'ponavljanja', 'ponavljanja')}"
    if seconds is not None:
        return f"{seconds} s"
    if sets is not None:
        return f"{sets} {_plural(sets, 'serija', 'serije', 'serija')}"
    return ""


def fold_items(conn) -> None:
    """Every programme with items -> its Dan 1, the items in it in their
    order, each note parsed (parse_dose)."""
    held = conn.execute(sa.select(programs.c.id, programs.c.title)
                        .where(programs.c.id.in_(sa.select(items.c.program_id)))
                        .order_by(programs.c.id)).all()
    for pid, title in held:
        rows = conn.execute(sa.select(items.c.exercise_id, items.c.note).where(items.c.program_id == pid)
                            .order_by(items.c.position, items.c.id)).all()
        day_id = conn.execute(sa.insert(days).values(program_id=pid, position=1, title="", weekday=None, intro="")
                              .returning(days.c.id)).scalar_one()
        values = []
        for position, (exercise_id, note) in enumerate(rows, start=1):
            sets, reps, seconds, rest = parse_dose(note)
            values.append({"day_id": day_id, "position": position, "section": "trening", "exercise_id": exercise_id,
                           "sets": sets, "reps": reps, "seconds": seconds, "rest_seconds": None, "note": rest})
        conn.execute(sa.insert(day_items), values)
        print(f"[{revision}] programs {pid} ({title!r}): Dan 1 with {len(rows)} "
              f"exercise{'' if len(rows) == 1 else 's'}")


def unfold_items(conn) -> None:
    """The way back: every programme's items across its days, in order, as
    flat program_items, each note its dose and its note."""
    rank = sa.case({key: n for n, key in enumerate(SECTIONS)}, value=day_items.c.section, else_=len(SECTIONS))
    rows = conn.execute(
        sa.select(days.c.program_id, day_items.c.exercise_id, day_items.c.sets, day_items.c.reps,
                  day_items.c.seconds, day_items.c.note)
        .select_from(day_items.join(days, days.c.id == day_items.c.day_id))
        .order_by(days.c.program_id, days.c.position, rank, day_items.c.position, day_items.c.id)).all()
    values, place = [], {}
    for pid, exercise_id, sets, reps, seconds, note in rows:
        place[pid] = place.get(pid, 0) + 1
        values.append({"program_id": pid, "position": place[pid], "exercise_id": exercise_id,
                       "note": " · ".join(x for x in (dose_text(sets, reps, seconds), note or "") if x)})
    if values:
        conn.execute(sa.insert(items), values)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "program_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), server_default=sa.text("''"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("intro", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("intro_video", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("program_id", "position", name="uq_program_days_position",
                            deferrable=True, initially="DEFERRED"),
    )
    op.create_index("ix_program_days_program_id", "program_days", ["program_id"])
    op.create_table(
        "program_day_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day_id", sa.Integer(), sa.ForeignKey("program_days.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=12), server_default=sa.text("'trening'"), nullable=False),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("seconds", sa.Integer(), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.UniqueConstraint("day_id", "position", name="uq_program_day_items_position",
                            deferrable=True, initially="DEFERRED"),
        sa.CheckConstraint("section IN ('zagrijavanje', 'trening', 'istezanje')", name="ck_program_day_items_section"),
        sa.CheckConstraint("reps IS NULL OR seconds IS NULL", name="ck_program_day_items_reps_or_seconds"),
    )
    op.create_index("ix_program_day_items_day_id", "program_day_items", ["day_id"])
    op.create_index("ix_program_day_items_exercise_id", "program_day_items", ["exercise_id"])
    fold_items(op.get_bind())
    op.drop_table("program_items")                  # its indexes and foreign keys with it


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "program_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("note", sa.Text(), server_default=sa.text("''"), nullable=False),
    )
    op.create_index("ix_program_items_program_id", "program_items", ["program_id"])
    op.create_index("ix_program_items_exercise_id", "program_items", ["exercise_id"])
    unfold_items(op.get_bind())
    op.drop_table("program_day_items")
    op.drop_table("program_days")
