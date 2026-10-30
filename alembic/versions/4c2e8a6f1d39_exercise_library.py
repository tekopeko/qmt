"""exercise_library: the library of exercises; a programme's items point at it

The owner (29.-30.10.2026): "We should have a database of exercises which he
can choose from and add them to different training programmes that will be
modular. Each exercise will have a video connected to it which will show the
exercise and show what one rep means." Until this revision a programme was a
flat list of program_items typed by hand: a title, a body (the instructions)
and one media file, an image or a video. Since it every exercise of every
programme is a row of the library, `exercises` (a name, unique whatever its
case, how it is done, what one rep is, a clip, free tags), with the similar
exercises a client may later swap one for (`exercise_alternatives`: one row
a pair, stored one way, read both), and an item is only its programme, its
place, the exercise it points at (`exercise_id`, RESTRICT: an exercise a
programme holds is not deleted) and its own `note`, what it says beside its
exercise: for now the dose, until the days' sets and reps (the spec's stage
2, which keeps the column as the item's note).

This creates the two tables and folds the items into the library. Every
body is split first (split_body): its first line is the item's note when it
looks like a dose (it starts with a digit once trimmed: "3 × 8 · 8 kg", "2 ×
10 sporih ponavljanja", "3 × 30 s po strani"), and the rest, trimmed, is the
candidate for its exercise's instructions; a body whose first line is no dose
is all instructions, one that is only a dose line all note. Prod's every body
was "DOSE\nCUE" (the nine slots' defaults, the dose per razina), so the
library gets the cues and each item keeps its razina's dose. Then for every
program_items row in (program_id, position) order an exercise is made, or
reused, by the item's title (trimmed, its spaces single, compared casefolded:
"Goblet čučanj" and "GOBLET ČUČANJ " are one exercise, named as the first row
writes it); its instructions the first non-empty candidate among the rows of
that name, its clip the first media file of kind "video" among them; rep_note
and tags empty. What it cannot carry is written to the log (print) and left
where it is: an image (the library holds clips only; the file stays in
storage), a second clip of the same name (its file stays too), and a
candidate other than the one kept. Then every item points at its exercise,
and title, body, media_name and media_kind go.

The rules are written out here on purpose: a migration must not import app
code, which will have moved on by the time this runs somewhere.

Downgrade, best effort: the four columns back on every item from its exercise
and its note (title the exercise's name; body the note and the instructions,
a line between them, either alone when the other is empty, NULL when both
are; its clip as a "video" media), then exercise_id, note and the two tables
go. What only the library holds is lost
(rep_note, tags, the similar exercises, and the exercises no programme holds,
whose clips stay in storage); items that shared an exercise share its body and
its clip's file again (the old app deletes an item's media with the item: one
such item deleted takes the file from the others).

Revision ID: 4c2e8a6f1d39
Revises: b18ebed39701
Create Date: 2026-10-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c2e8a6f1d39'
down_revision: Union[str, Sequence[str], None] = 'b18ebed39701'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

items = sa.table(
    "program_items",
    sa.column("id", sa.Integer),
    sa.column("program_id", sa.Integer),
    sa.column("position", sa.Integer),
    sa.column("title", sa.String),
    sa.column("body", sa.Text),
    sa.column("media_name", sa.String),
    sa.column("media_kind", sa.String),
    sa.column("exercise_id", sa.Integer),
    sa.column("note", sa.Text),
)
exercises = sa.table(
    "exercises",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("instructions", sa.Text),
    sa.column("rep_note", sa.Text),
    sa.column("video", sa.String),
    sa.column("tags", sa.Text),
)


def _name(title: str | None) -> str:
    """An item's title as an exercise's name: trimmed, its spaces single (the
    app's db.clean_name). None was ever empty (the route made it "Vježba")."""
    return " ".join((title or "").split()) or "Vježba"


def split_body(body: str | None) -> tuple[str, str]:
    """An item's body -> (its note, the candidate for its exercise's
    instructions): the first line is the note when it starts with a digit
    once trimmed (a dose), the rest, trimmed, the instructions; a body whose
    first line is no dose is all instructions, one that is only a dose line
    all note."""
    text = (body or "").strip()
    first, _, rest = text.partition("\n")
    first = first.strip()
    if first and first[0] in "0123456789":       # an ASCII digit: str.isdigit() would take "²"
        return first, rest.strip()
    return "", text


def fold_items(conn) -> None:
    """Every program_items row -> its note (split_body) and an exercise of
    its name (made the first time, found casefolded after that), the row
    pointing at it."""
    rows = conn.execute(sa.select(items.c.id, items.c.title, items.c.body, items.c.media_name, items.c.media_kind)
                        .order_by(items.c.program_id, items.c.position, items.c.id)).all()
    made: dict[str, dict] = {}                       # casefolded name -> the exercise to make
    for r in rows:
        name = _name(r.title)
        ex = made.setdefault(name.casefold(), {"name": name, "instructions": "", "video": None, "items": []})
        ex["items"].append(r.id)
        note, body = split_body(r.body)
        if note:
            conn.execute(sa.update(items).where(items.c.id == r.id).values(note=note))
        if body and not ex["instructions"]:
            ex["instructions"] = body
        elif body and body != ex["instructions"]:
            print(f"[{revision}] program_items {r.id} ({name!r}): its instructions are not kept, the exercise "
                  f"keeps the first ones: {body!r}")
        if not r.media_name:
            continue
        if r.media_kind != "video":
            print(f"[{revision}] program_items {r.id} ({name!r}): image {r.media_name} dropped "
                  "(the library holds clips only; the file stays in storage)")
        elif ex["video"] is None:
            ex["video"] = r.media_name
        elif r.media_name != ex["video"]:
            print(f"[{revision}] program_items {r.id} ({name!r}): clip {r.media_name} dropped, the exercise keeps "
                  f"{ex['video']} (the file stays in storage)")
    for ex in made.values():
        eid = conn.execute(sa.insert(exercises).values(name=ex["name"], instructions=ex["instructions"], rep_note="",
                                                       video=ex["video"], tags="")
                           .returning(exercises.c.id)).scalar_one()
        conn.execute(sa.update(items).where(items.c.id.in_(ex["items"])).values(exercise_id=eid))


def unfold_items(conn) -> None:
    """The way back: every item's title and media from its exercise, its body
    its note and the exercise's instructions (a line between them)."""
    conn.execute(sa.text(
        "UPDATE program_items AS i SET title = e.name, "
        "body = NULLIF(CONCAT_WS(E'\\n', NULLIF(i.note, ''), NULLIF(e.instructions, '')), ''), "
        "media_name = e.video, media_kind = CASE WHEN e.video IS NULL THEN NULL ELSE 'video' END "
        "FROM exercises AS e WHERE e.id = i.exercise_id"))


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("instructions", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("rep_note", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("video", sa.String(length=200), nullable=True),
        sa.Column("tags", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("uq_exercises_name", "exercises", [sa.text("lower(name)")], unique=True)
    op.create_table(
        "exercise_alternatives",
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("alternative_id", sa.Integer(), sa.ForeignKey("exercises.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.CheckConstraint("exercise_id <> alternative_id", name="ck_exercise_alternatives_other"),
    )
    op.create_index("ix_exercise_alternatives_alternative_id", "exercise_alternatives", ["alternative_id"])
    op.add_column("program_items", sa.Column("exercise_id", sa.Integer(),
                                             sa.ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("program_items", sa.Column("note", sa.Text(), server_default=sa.text("''"), nullable=False))
    fold_items(op.get_bind())
    op.alter_column("program_items", "exercise_id", nullable=False)
    op.create_index("ix_program_items_exercise_id", "program_items", ["exercise_id"])
    for column in ("title", "body", "media_name", "media_kind"):
        op.drop_column("program_items", column)


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("program_items", sa.Column("title", sa.String(length=160), nullable=True))
    op.add_column("program_items", sa.Column("body", sa.Text(), nullable=True))
    op.add_column("program_items", sa.Column("media_name", sa.String(length=200), nullable=True))
    op.add_column("program_items", sa.Column("media_kind", sa.String(length=8), nullable=True))
    unfold_items(op.get_bind())
    op.alter_column("program_items", "title", nullable=False)
    op.drop_index("ix_program_items_exercise_id", table_name="program_items")
    op.drop_column("program_items", "exercise_id")             # its foreign key goes with it
    op.drop_column("program_items", "note")
    op.drop_index("ix_exercise_alternatives_alternative_id", table_name="exercise_alternatives")
    op.drop_table("exercise_alternatives")
    op.drop_index("uq_exercises_name", table_name="exercises")
    op.drop_table("exercises")
