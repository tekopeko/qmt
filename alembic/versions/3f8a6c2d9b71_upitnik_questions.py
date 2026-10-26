"""upitnik_questions: the upitnik's questions become rows (the upitnik.q* slots fold in)

The online-trening upitnik (v2, 26.10.2026) had its fifteen questions fixed
in code (qmt.upitnik) and only their words in copy slots, site_copy rows
upitnik.q<n>.text, a choice's .options (one row, a JSON array), a scale's
.low and .high, and the two follow-ups' upitnik.q14b.text and
upitnik.q15b.text. Since 26.10.2026 the gym owner adds, removes, hides,
reorders and classifies the questions himself (the owner: "so that Amir
can also add or remove questions from the questionnaire"), so they are
rows of a new table, upitnik_questions.

This creates the table and seeds it with the fifteen as the site shows
them now, WITH THEIR IDS 1-15: a client's answers are stored keyed by
question ("q1" ... "q15", a follow-up's "q14b" / "q15b"), and a row's id is
that key from here on, so every answer already given keeps its meaning.
Per text the edited site_copy row where there is one (an emptied one
stays empty), else the slot's default; a choice's options the edited list,
or the default list when there is none (or it cannot be read as one, as
copy.load_items had it). The structure as the code had it: q1-q4 choices
in part 1; q5-q11 scales in part 2 that score, q5-q7 trening baza and
q8-q11 navike; q12-q13 scales in part 3 that do not; q14 the pain question
(a scale in part 4, its follow-up's text the edited upitnik.q14b.text or
its default) and q15 the injuries question (yes / no, upitnik.q15b.text).
All shown. The id sequence is set past 15, so a new question is q16. Then
those slots' rows go (the words around the questions, upitnik.title,
.intro, .part<n>.h, .yes / .no, .consent, the buttons and .pain_note, stay
slots).

The defaults are written out here on purpose: a migration must not import
app code, which will have moved on by the time this runs somewhere.

Downgrade, best effort: the rows with ids 1-15 go back as those slots'
rows, only what differs from the old defaults (as an old app reads them),
each question's words as the old code asked them (a choice's text and
options, a scale's text and ends, q15's text, the follow-ups'), whatever
kind the row has become; then the table goes. A question the gym owner
added is lost, a deleted one is its defaults again, and every setting
(part, kind, scoring, role, the switch, the order) is the old code's
again. The answers are never touched, either way.

Revision ID: 3f8a6c2d9b71
Revises: e6564d9234b8
Create Date: 2026-10-26 18:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f8a6c2d9b71'
down_revision: Union[str, Sequence[str], None] = 'e6564d9234b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _q(n, part, kind, text, options=(), low="", high="", scoring="", role="", followup_text=""):
    return {"id": n, "part": part, "kind": kind, "text": text, "options": list(options), "low": low, "high": high,
            "scoring": scoring, "role": role, "followup_text": followup_text}


# the fifteen as copy.py had them before this revision (their slots'
# defaults) and as the code's structure had them
QUESTIONS = (
    _q(1, 1, "choice", "Koji je tvoj glavni cilj?",
       ("Gubitak težine", "Povećanje snage i mišićne mase", "Bolja kondicija i izdržljivost",
        "Rehabilitacija / rješavanje bolova", "Opće zdravlje i kretanje")),
    _q(2, 1, "choice", "Koliko dana tjedno možeš trenirati?", ("2", "3", "4", "5+")),
    _q(3, 1, "choice", "Koliko minuta imaš za jedan trening?", ("do 30", "30-45", "45-60", "60+")),
    _q(4, 1, "choice", "Gdje ćeš trenirati?", ("Kod kuće bez opreme", "Kod kuće s osnovnom opremom", "U teretani")),
    _q(5, 2, "scale", "Koliko redovito si trenirao/la u zadnjih 6 mjeseci (2x tjedno ili više)?",
       low="uopće nisam", high="stalno i dosljedno", scoring="baza"),
    _q(6, 2, "scale", "Kako bi ocijenio/la svoju fizičku kondiciju?", low="vrlo loša", high="izvrsna", scoring="baza"),
    _q(7, 2, "scale", "Kako ocjenjuješ svoje poznavanje treninga?",
       low="ne znam ništa", high="znam sve i izvodim ispravno", scoring="baza"),
    _q(8, 2, "scale", "Paziš li redovito na prehranu?", low="uopće ne", high="uvijek", scoring="navike"),
    _q(9, 2, "scale", "Vodiš li aktivan životni stil izvan treninga (šetnje, kretanje)?",
       low="sjedim cijeli dan", high="stalno sam u pokretu", scoring="navike"),
    _q(10, 2, "scale", "Koliko si motiviran/a za promjenu i dosljednost?",
       low="uopće nisam", high="jako sam motiviran/a", scoring="navike"),
    _q(11, 2, "scale", "Koliko prosječno spavaš po noći?", low="manje od 4h", high="više od 8h", scoring="navike"),
    _q(12, 3, "scale", "Koristiš li dodatke prehrani (vitamini, minerali, kreatin...)?", low="nikad", high="redovito"),
    _q(13, 3, "scale", "Koliko ti je važna osobna briga o zdravlju i tijelu?",
       low="nije mi prioritet", high="izuzetno važno"),
    _q(14, 4, "scale", "Imaš li često bolove (leđa, vrat, kuk...)?", low="nikad", high="vrlo često",
       role="pain", followup_text="Gdje te boli?"),
    _q(15, 4, "yesno", "Imaš li ozljede, operacije ili zdravstvena ograničenja koja trebamo znati?",
       role="injuries", followup_text="Opiši ukratko."),
)


def slot_keys(q: dict) -> dict[str, str]:
    """A question's old slots, by the column each folds into: its text; a
    choice's options; a scale's two ends; a safety question's follow-up
    (upitnik.q14b.text, upitnik.q15b.text)."""
    n = q["id"]
    keys = {"text": f"upitnik.q{n}.text"}
    if q["kind"] == "choice":
        keys["options"] = f"upitnik.q{n}.options"
    if q["kind"] == "scale":
        keys.update(low=f"upitnik.q{n}.low", high=f"upitnik.q{n}.high")
    if q["role"]:
        keys["followup_text"] = f"upitnik.q{n}b.text"
    return keys


KEYS = [key for q in QUESTIONS for key in slot_keys(q).values()]

site_copy = sa.table(
    "site_copy",
    sa.column("key", sa.String),
    sa.column("text", sa.Text),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("updated_by", sa.Integer),
)
questions = sa.table(
    "upitnik_questions",
    sa.column("id", sa.Integer),
    sa.column("position", sa.Integer),
    sa.column("part", sa.Integer),
    sa.column("kind", sa.String),
    *(sa.column(c, sa.Text) for c in ("text", "options", "low", "high", "followup_text")),
    sa.column("scoring", sa.String),
    sa.column("role", sa.String),
    sa.column("shown", sa.Boolean),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("updated_by", sa.Integer),
)


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


def fold_questions(conn) -> None:
    """The upitnik.q* rows -> the fifteen questions, ids and positions
    1-15, the id sequence past them; those rows gone."""
    rows = {r.key: r for r in conn.execute(
        sa.select(site_copy.c.key, site_copy.c.text, site_copy.c.updated_at, site_copy.c.updated_by)
        .where(site_copy.c.key.in_(KEYS)))}
    for q in QUESTIONS:
        values = {c: q[c] for c in ("part", "kind", "text", "low", "high", "scoring", "role", "followup_text")}
        options = list(q["options"])
        mine = {column: rows[key] for column, key in slot_keys(q).items() if key in rows}
        for column, r in mine.items():
            if column == "options":
                options = _items(r.text, q["options"])
            else:
                values[column] = r.text
        values.update(options=json.dumps(options, ensure_ascii=False), shown=True)
        if mine:                                    # who last touched this question, and when
            latest = max(mine.values(), key=lambda r: r.updated_at)
            values.update(updated_at=latest.updated_at, updated_by=latest.updated_by)
        conn.execute(sa.insert(questions).values(id=q["id"], position=q["id"], **values))
    # the rows came with their own ids: a new question is the next one, q16
    conn.execute(sa.text("SELECT setval(pg_get_serial_sequence('upitnik_questions', 'id'), "
                         "(SELECT max(id) FROM upitnik_questions))"))
    conn.execute(sa.delete(site_copy).where(site_copy.c.key.in_(KEYS)))


def unfold_questions(conn) -> None:
    """The way back: the rows with ids 1-15 -> their old slots' rows (an
    old app reads those), only what differs from the defaults."""
    rows = {r.id: r for r in conn.execute(sa.select(questions).where(questions.c.id.between(1, len(QUESTIONS))))}
    conn.execute(sa.delete(site_copy).where(site_copy.c.key.in_(KEYS)))
    for q in QUESTIONS:
        row = rows.get(q["id"])
        if row is None:                             # deleted: the old question is its defaults again
            continue
        for column, key in slot_keys(q).items():
            if column == "options":
                items = _items(row.options, q["options"])
                if items == q["options"]:
                    continue
                text = json.dumps(items, ensure_ascii=False)
            else:
                text = getattr(row, column)
                if text == q[column]:
                    continue
            conn.execute(sa.insert(site_copy).values(key=key, text=text, updated_at=row.updated_at,
                                                     updated_by=row.updated_by))


def upgrade() -> None:
    op.create_table(
        "upitnik_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("part", sa.Integer(), server_default=sa.text("2"), nullable=False),
        sa.Column("kind", sa.String(length=8), server_default=sa.text("'scale'"), nullable=False),
        sa.Column("text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("options", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("low", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("high", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("scoring", sa.String(length=8), server_default=sa.text("''"), nullable=False),
        sa.Column("role", sa.String(length=10), server_default=sa.text("''"), nullable=False),
        sa.Column("followup_text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("shown", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        # deferred: ↑ / ↓ swap two positions, checked when the swap commits
        sa.UniqueConstraint("position", name="uq_upitnik_questions_position", deferrable=True, initially="DEFERRED"),
    )
    # one pain question and one injuries question at most
    op.create_index("uq_upitnik_questions_role", "upitnik_questions", ["role"], unique=True,
                    postgresql_where=sa.text("role <> ''"))
    fold_questions(op.get_bind())


def downgrade() -> None:
    unfold_questions(op.get_bind())
    op.drop_index("uq_upitnik_questions_role", table_name="upitnik_questions")
    op.drop_table("upitnik_questions")
