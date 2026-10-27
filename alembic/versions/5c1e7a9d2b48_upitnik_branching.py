"""upitnik branching: a question asked only after an answer to an earlier one; the follow-ups become questions

The gym owner (27.10.2026): "add a subquestion in the case for example
'Jeste li imali porod' and if the answer is yes, he would like to again ask
if she had it in the last year and then if she says yes then he would ask
if it was C-section or not etc." Until now a follow-up existed only through
the two roles, one of each: the pain question asked its followup_text at 4
or more, the injuries question at yes.

Any question may now depend on an earlier one: upitnik_questions gains
parent_id, the question it depends on (a foreign key to the table itself,
ON DELETE SET NULL: a parent deleted leaves its questions asked always),
and condition, that question's answer which asks it ("yes" / "no", an
option's text, ">=N"), "" when it is asked always.

The role follow-ups become ordinary conditional questions. Each row that
holds a role on the kind the role needs (pain on a scale, injuries on a
yes / no) gets its follow-up as a new row of kind text right after it: its
text the followup_text, its part and its switch the role question's,
parent_id the role question, condition ">=4" (PAIN_ASK, where the pain
question asked where it hurts) or "yes". A followup_text on a question with
no role (the role moved to another question, or never was there, as on
prod's q20) becomes such a row too, condition "yes", where the question is
a yes / no; anywhere else it goes with the column. The rows are numbered
1..n again in their new order. Then followup_text goes. The stored answers
follow: a response's "q<N>b" (question N's follow-up, answered) becomes the
key of N's new row, "q<id>", in its place among the answers, so the karton
prints it under that question. A "q<N>b" whose N got no row (a question
deleted before this, or a text dropped) stays as it is: the karton prints
it under "(pitanje uklonjeno)".

Downgrade, best effort: followup_text comes back, and each question that
holds a role, or is a yes / no, takes back its first text question (a role
question's whatever its condition, a yes / no's the first asked at "yes"):
that row's text becomes its followup_text, the answers "q<id>" become
"q<N>b" again, and the row goes. Every other condition is lost with the two
columns (those questions are asked always again).

The defaults are written out here on purpose: a migration must not import
app code, which will have moved on by the time this runs somewhere.

Revision ID: 5c1e7a9d2b48
Revises: 3f8a6c2d9b71
Create Date: 2026-10-27 12:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c1e7a9d2b48'
down_revision: Union[str, Sequence[str], None] = '3f8a6c2d9b71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PAIN_ASK = 4                                       # the pain question asked where it hurts from here
ROLE_KINDS = {"pain": "scale", "injuries": "yesno"}
ROLE_CONDITIONS = {"pain": f">={PAIN_ASK}", "injuries": "yes"}
FK = "upitnik_questions_parent_id_fkey"            # the name Postgres gives the model's (create_all's) too
POSITION = "uq_upitnik_questions_position"         # deferred: checked when the transaction commits

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
    sa.column("parent_id", sa.Integer),
    sa.column("condition", sa.String),
)
responses = sa.table(
    "onboarding_responses",
    sa.column("id", sa.Integer),
    sa.column("answers", sa.Text),
)


def follow_up(row) -> str | None:
    """The condition a row's follow-up is asked at, as a question of its
    own, or None: none. A role on the kind it needs: its role's ("where"
    from 4, the note at yes), its text whatever it is (the follow-up was
    asked, an emptied text too); no role: "yes" for a yes / no with a
    text; else none."""
    if ROLE_KINDS.get(row.role) == row.kind:
        return ROLE_CONDITIONS[row.role]
    if row.kind == "yesno" and (row.followup_text or "").strip():
        return "yes"
    return None


def rename(conn, keys: dict[str, str]) -> None:
    """Every stored response's answers with their keys renamed (old ->
    new), each in its place; a response holding none of them stays as it
    is, a version-1 one too (its keys are words)."""
    if not keys:
        return
    for r in conn.execute(sa.select(responses.c.id, responses.c.answers)).all():
        try:
            answers = json.loads(r.answers)
        except (TypeError, ValueError):
            continue
        if not isinstance(answers, dict) or not keys.keys() & answers.keys():
            continue
        renamed = {keys.get(key, key): value for key, value in answers.items()}
        conn.execute(sa.update(responses).where(responses.c.id == r.id)
                     .values(answers=json.dumps(renamed, ensure_ascii=False)))


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.select(questions.c.id, questions.c.position, questions.c.part, questions.c.kind,
                                  questions.c.role, questions.c.followup_text, questions.c.shown)
                        .order_by(questions.c.position)).all()
    op.add_column("upitnik_questions", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.create_foreign_key(FK, "upitnik_questions", "upitnik_questions", ["parent_id"], ["id"], ondelete="SET NULL")
    op.add_column("upitnik_questions",
                  sa.Column("condition", sa.String(length=80), server_default=sa.text("''"), nullable=False))
    order, keys = [], {}
    spare = max((r.position for r in rows), default=0)
    for r in rows:
        order.append(r.id)
        condition = follow_up(r)
        if condition is None:
            continue
        spare += 1                                 # out of the way until the order is written below
        new = conn.execute(sa.insert(questions).values(
            position=spare, part=r.part, kind="text", text=r.followup_text or "", options="[]", low="", high="",
            scoring="", role="", shown=r.shown, parent_id=r.id, condition=condition)
            .returning(questions.c.id)).scalar_one()
        order.append(new)
        keys[f"q{r.id}b"] = f"q{new}"
    for position, qid in enumerate(order, start=1):
        conn.execute(sa.update(questions).where(questions.c.id == qid).values(position=position))
    # the order checked now, not at the commit: a table with checks pending
    # cannot be altered, and the column goes next
    conn.execute(sa.text(f"SET CONSTRAINTS {POSITION} IMMEDIATE"))
    op.drop_column("upitnik_questions", "followup_text")
    rename(conn, keys)


def downgrade() -> None:
    conn = op.get_bind()
    op.add_column("upitnik_questions",
                  sa.Column("followup_text", sa.Text(), server_default=sa.text("''"), nullable=False))
    rows = conn.execute(sa.select(questions.c.id, questions.c.kind, questions.c.role, questions.c.text,
                                  questions.c.parent_id, questions.c.condition)
                        .order_by(questions.c.position)).all()
    keys, folded = {}, set()
    for r in rows:
        role = ROLE_KINDS.get(r.role) == r.kind
        if not role and r.kind != "yesno":
            continue
        child = next((c for c in rows if c.parent_id == r.id and c.kind == "text" and c.id not in folded
                      and (role or c.condition == "yes")), None)
        if child is None:
            continue
        conn.execute(sa.update(questions).where(questions.c.id == r.id).values(followup_text=child.text))
        keys[f"q{child.id}"] = f"q{r.id}b"
        folded.add(child.id)
    if folded:
        conn.execute(sa.delete(questions).where(questions.c.id.in_(folded)))
    rename(conn, keys)
    conn.execute(sa.text(f"SET CONSTRAINTS {POSITION} IMMEDIATE"))
    op.drop_constraint(FK, "upitnik_questions", type_="foreignkey")
    op.drop_column("upitnik_questions", "condition")
    op.drop_column("upitnik_questions", "parent_id")
