"""The online-trening upitnik, version 2 (26.10.2026): the gym owner's
questionnaire, asked one question per screen on /upitnik (Shape's design).

Its questions are rows since 26.10.2026 (models.UpitnikQuestion; the owner:
"so that Amir can also add or remove questions from the questionnaire"):
the gym owner adds, removes, hides, reorders and classifies them in edit
mode on /upitnik, up to db.MAX_UPITNIK_QUESTIONS. A row says where it
stands and under which of the four parts' headings, what it asks (`kind`:
one option of a choice, several of a multi, a scale of 1 to 10, yes / no,
or a free text), its words (the text, the options, a scale's two ends) and
what it does: `scoring`, the group a scale's answer joins in the score
("baza", trening baza, or "navike"; only a scale scores), and `role`, one
of the two safety questions ("pain", a scale; "injuries", a yes / no; at
most one of each). A hidden question (`shown` off) is asked of nobody and
scores nothing.

Since 27.10.2026 any question may be asked only after a given answer to an
earlier one (the owner: "add a subquestion … 'Jeste li imali porod' and if
the answer is yes … ask if she had it in the last year and then if she
says yes … if it was C-section or not etc."): `parent_id`, the question it
depends on, and `condition`, the answer to it that asks this one: "yes" /
"no" for a yes / no, an option's text for a choice or a multi (asked when
it is among the answers), ">=N" for a scale (N 1–10); "" asks it always.
Chains follow: a question is asked when its parent was asked and answered
so. A hidden question hides the questions asked after it, down the whole
chain (steps: `muted`; Fable's review, the same day: a gym owner who hides
"Jeste li imali porod?" means its questions too). A condition that
cannot work otherwise (its question deleted, after it in the order, or no
longer able to give that answer) asks it always, and the editor's line
says so (steps: `void`). A re-worded option carries into the conditions
that named it (db.set_upitnik_question_options). The two roles keep their rules
but no longer ask anything themselves: their follow-ups became ordinary
conditional questions that day (migration 5c1e7a9d2b48: "Gdje te boli?"
under the pain question at ">=4", "Opiši ukratko." under the injuries one
at "yes").

The gym owner's questions start it (copy.UPITNIK_DEFAULT_QUESTIONS): part
1, q1–q4, the goal, the days a week, the minutes and the place (choices,
never scored: they are for the programme's CONTENT, which they will choose
later; the owner, 26.10.2026: "Later on, we will implement different types
of training depending on the equipment … we will automatically send them
to the appropriate training group"); part 2, q5–q11, the scored scales
(q5–q7 trening baza, q8–q11 navike); part 3, q12–q13, scales for the
trainer; part 4, q14 the pain question (a scale) with q16 under it, where
it hurts, asked at 4 or more, and q15 the injuries question (yes / no) with
q17 under it, a short note, asked at yes.

What stays here, in code, works on whatever the rows say: the screens a
list of rows makes (steps: each with the condition it is asked on, as far
as that condition can work; client_steps, the ones a client gets), whether
a question is asked (is_asked, meets, asked_of), what a submitted form must
hold (read), the owner's formula and
its thresholds (score, level_for), his two safety rules with their numbers
(evaluate: PAIN_HIGH, needs_review), the rules a question's settings keep
(settings, condition), the editor's lines under his settings
(setting_line, condition_line, scoring_summary) and the karton's helpers
(answer_rows, chips, pain_where).

The score, the owner's formula: trening baza = the mean of the baza
scales, navike = the mean of the navike scales (the shown ones: those
asked), score = 0.6 × baza + 0.4 × navike, to one decimal, worked in exact
fractions and rounded half up, so no float's noise ever moves a client
across a threshold whatever the number of questions in a group. A group
with no question gives its weight to the other; with no scored question
at all every result is početna. Up to 4.0 početna, up to 7.0 srednja,
above that napredna. His two safety rules: the pain question at PAIN_HIGH
or more is početna whatever the score, with a word to see the trainer
first (pain_high, upitnik.pain_note); the injuries question's yes flags
the profile for the trainer to look at (needs_review).

The questionnaire decides the LEVEL only (the owner: "The questionnaire will
only determine the difficulty level of the trainings … for now"): every
response's goal, the column the programmes are matched on (db.programs_for_
combo, db.client_can_view), is GOAL, "cijelo", so a client gets the level's
whole-body programmes until the "type of training" step comes. q1's goal is
kept in the answers and shown on the karton; it routes nothing yet.

Answers are stored as JSON (models.OnboardingResponse.answers), keyed by the
question's row: "q<id>" (the fifteen kept their ids when they became rows,
so the answers given before keep their meaning; an id is never used twice;
the old follow-ups' "q<id>b" became their new questions' keys with them,
5c1e7a9d2b48). A choice is stored as the option's TEXT at the time, never
its index, so a later re-wording never garbles an old answer; a multi as
the list of the chosen options' texts; a scale as an int, yes / no as a
bool, a free text as a string; a question that was not asked is absent.
Nothing is pruned when a question goes: the karton prints every answer
kept, under its question's current text (a conditional one indented under
its question), or under "(pitanje uklonjeno)" when the row is gone
(answer_rows).

Version 1 (3.9. – 26.10.2026: five scored questions and a goal, points per
option, the goal routing too) stays readable: QUESTIONS_V1 renders an old
row's answers on the karton (OnboardingResponse.version 1). Such a row
still counts as a filled upitnik, its level and goal still route, until
the client fills the new one.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

LEVELS = {
    "pocetna": "Početna razina",
    "srednja": "Srednja razina",
    "napredna": "Napredna razina",
}

# The programmes' cilj (models.Program.goal: the nine razina × cilj slots).
# A version-2 response's goal is always GOAL; version 1 asked for one.
GOALS = {
    "cijelo": "Cijelo tijelo",
    "gornji": "Gornji dio tijela",
    "donji": "Donji dio tijela",
}

VERSION = 2          # OnboardingResponse.version of a response to these questions
GOAL = "cijelo"      # every version-2 response's goal (above)

PARTS = (1, 2, 3, 4)                   # a question's part: the heading above it, upitnik.part<n>.h
# What a question asks, as the editor's select names it ("Više odgovora":
# a choice whose client may tick several options, 26.10.2026, for the gym
# owner's coming equipment question), and as the line under his settings
# says it.
KINDS = {"choice": "Jedan odgovor", "multi": "Više odgovora", "scale": "Skala 1–10", "yesno": "Da / Ne",
         "text": "Slobodan tekst"}
KIND_WORDS = {"choice": "jedan odgovor", "multi": "više odgovora", "scale": "skala", "yesno": "da / ne",
              "text": "slobodan tekst"}
OPTION_KINDS = ("choice", "multi")     # the kinds whose answer is among the question's options
# The score's two groups, which a scale joins (scoring), as the editor's
# select names them ("" scores nothing), and their weights in the owner's
# formula.
SCORING = {"": "Ne boduje se", "baza": "Trening baza", "navike": "Navike"}
WEIGHTS = {"baza": Fraction(6, 10), "navike": Fraction(4, 10)}
# The two safety questions (role) and the kind each must be, and as the
# editor's select names them ("" none). At most one question holds each.
ROLES = {"pain": "scale", "injuries": "yesno"}
ROLE_LABELS = {"": "—", "pain": "Bolovi", "injuries": "Ozljede"}

# The pain question at this or more: the trainer's amber flag on the
# karton ("Bolovi N/10 · where"). Until 27.10.2026 it also asked where it
# hurts; that is a question of its own since, asked on its own condition
# (">=4" as migration 5c1e7a9d2b48 and the defaults made it).
PAIN_ASK = 4
PAIN_HIGH = 7        # the pain question at this or more: početna whatever the score, and see the trainer first

# What a question may be asked after (27.10.2026): an earlier question of a
# kind whose answer a condition can name (a free text has none), the
# answer as a condition holds it (the column's length: an option longer
# than that is no condition), and how much of a question's text the
# editor's list of them shows.
CONDITION_KINDS = ("yesno", "choice", "multi", "scale")
CONDITION_MAX = 80
SHORT = 40
_AT_LEAST = re.compile(r">=([1-9]|10)")            # a scale's condition, ">=N": N or more

MAX_SCORE = 10
SCALE = range(1, 11)                   # a scale question's answers
MIN_OPTIONS = 2                        # a choice (a multi) keeps at least this many options (app.py, the editor)
TEXT_MAX = 2000                        # a free text's characters, as a copy text's (copy.CAP)
YES, NO = "da", "ne"                   # a yes / no question's posted values
REMOVED = "(pitanje uklonjeno)"        # the karton's question for an answer whose question was deleted since


@dataclass(frozen=True)
class Question:
    """One screen of the questionnaire, made from a row (steps). `id` is
    the answer's key, "q<row>"; `row` the row's id and `n` its place in
    the list it was made from, 1-based (the editor's "Pitanje 7").
    `parent` and `condition` are the row's as stored: the question it is
    asked after (its row id) and the answer that asks it ("" asks it
    always). `follows` is that question's key while the condition can work
    (it is earlier in this list and can be given that answer; its kind
    `parent_kind`), the question then asked only when its parent was asked
    and answered so; None asks it always, and for a condition that cannot
    work `void` says why: "gone" (its question deleted), "later" (it comes
    after this one), "answer" (it can no longer give that answer: its kind
    changed, an option was removed). `muted`: the question it is asked
    after is hidden, or that one's is, up the chain (`muted_by`, the hidden
    one's place): asked of nobody, whatever its own switch (`shown`) says.
    `parent_n` is that question's place here, None when it is gone;
    `depth` how many questions this one hangs under, through conditions
    that work (the editor's indent, the karton's)."""
    id: str
    row: int
    n: int
    part: int                     # 1–4: the heading above it, upitnik.part<n>.h
    kind: str                     # "choice" | "multi" | "scale" | "yesno" | "text"
    text: str = ""                # the question, as the gym owner words it
    options: tuple[str, ...] = ()  # a choice's (a multi's) options
    low: str = ""                 # a scale's words beside its 1 and its 10
    high: str = ""
    scoring: str = ""             # "" | "baza" | "navike": the group a scale joins in the score
    role: str = ""                # "" | "pain" | "injuries": a safety question
    shown: bool = True            # a hidden question is asked of nobody
    parent: int | None = None
    condition: str = ""
    follows: str | None = None
    parent_kind: str = ""
    void: str = ""
    parent_n: int | None = None
    depth: int = 0
    muted: bool = False
    muted_by: int | None = None


def at_least(condition: str) -> int | None:
    """A scale's condition, ">=N", as its N (1–10); None for any other."""
    m = _AT_LEAST.fullmatch(condition)
    return int(m.group(1)) if m else None


def fits(kind: str, options: Sequence[str], condition: str) -> bool:
    """Whether a question of `kind` (with these options) can be given the
    answer `condition` names: a yes / no "yes" or "no", a scale ">=N" (N
    1–10), a choice or a multi one of its options' texts. A free text
    none."""
    if kind == "yesno":
        return condition in ("yes", "no")
    if kind == "scale":
        return at_least(condition) is not None
    if kind in OPTION_KINDS:
        return condition in options
    return False


def steps(rows: Iterable) -> tuple[Question, ...]:
    """The screens a list of rows makes, in its order (db.upitnik_questions,
    by position: a client's the shown rows, the editor's every row), one
    per row. A scoring holds only on a scale, a role only on a row of the
    kind it needs and only on the first row that holds it: what the routes
    never let in (settings, the role's unique index) asks nothing here
    either. A condition holds only when it can work (Question: follows):
    its question earlier in this list and able to give that answer; any
    other asks the question always (`void` says why). A question whose
    question is hidden, or hangs under a hidden one, is `muted` (asked of
    nobody) whether its condition works or not. Build it from every row
    (db.upitnik_questions()): a hidden question left out of the list
    could not mute the ones under it."""
    rows = list(rows)
    place = {row.id: n for n, row in enumerate(rows, start=1)}
    by_id = {row.id: row for row in rows}

    def hidden_above(row) -> int | None:
        """The place of the hidden question a row's condition hangs under,
        its own question or one further up, or None."""
        seen = set()
        while row.condition and row.parent_id in by_id and row.id not in seen:
            seen.add(row.id)
            row = by_id[row.parent_id]
            if not row.shown:
                return place[row.id]
        return None

    out: list[Question] = []
    made: dict[int, Question] = {}
    taken: set[str] = set()
    for n, row in enumerate(rows, start=1):
        role = row.role if ROLES.get(row.role) == row.kind and row.role not in taken else ""
        taken.add(role)
        parent, condition = row.parent_id, row.condition or ""
        follows, parent_kind, void, depth = None, "", "", 0
        if condition:
            p = made.get(parent)
            if parent not in place:
                void = "gone"
            elif p is None:
                void = "later"
            elif not fits(p.kind, p.options, condition):
                void = "answer"
            else:
                follows, parent_kind, depth = p.id, p.kind, p.depth + 1
        muted_by = hidden_above(row)
        q = Question(f"q{row.id}", row.id, n, row.part, row.kind, row.text, tuple(row.option_items),
                     row.low, row.high, row.scoring if row.kind == "scale" and row.scoring in WEIGHTS else "",
                     role, row.shown, parent, condition, follows, parent_kind, void, place.get(parent), depth,
                     muted_by is not None, muted_by)
        out.append(q)
        made[row.id] = q
    return tuple(out)


def client_steps(rows: Iterable) -> tuple[Question, ...]:
    """The screens a client gets, of every row there is (steps): the shown
    ones that no hidden question mutes, in order. POST /upitnik reads and
    scores over the same (read, evaluate)."""
    return tuple(q for q in steps(rows) if q.shown and not q.muted)


def _number(value) -> bool:
    """A scale's answer: an int (a bool is an int to Python, and no number here)."""
    return isinstance(value, int) and not isinstance(value, bool)


def meets(kind: str, given, condition: str) -> bool:
    """Whether an answer, as stored, to a question of `kind` is the one a
    condition names: yes / no's True for "yes", False for "no"; a scale's
    N or more for ">=N"; a choice's that option, a multi's list holding it
    (either shape for either: what was stored)."""
    if kind == "yesno":
        return isinstance(given, bool) and given == (condition == "yes")
    if kind == "scale":
        n = at_least(condition)
        return n is not None and _number(given) and given >= n
    if kind in OPTION_KINDS:
        return given == condition or (isinstance(given, list) and condition in given)
    return False


def is_asked(q: Question, answers: Mapping) -> bool:
    """Whether `q` is asked, given the answers to the questions before it,
    as read() gathers them (a question not asked has no answer there):
    always, but for a conditional question (follows), whose question must
    have been asked and answered as its condition says, and never a muted
    one (a hidden question above it). A chain follows: a question not
    asked never meets a condition."""
    if q.muted:
        return False
    if q.follows is None:
        return True
    return q.follows in answers and meets(q.parent_kind, answers[q.follows], q.condition)


def asked_of(questions: Iterable[Question], answers: Mapping) -> tuple[Question, ...]:
    """The questions a set of answers was asked, in order: the shown ones
    no hidden question mutes, a conditional one only when its question was
    asked and answered as its condition says, whatever else the answers
    hold."""
    out, keys = [], set()
    for q in questions:
        if q.shown and not q.muted and (q.follows is None or (
                q.follows in keys and meets(q.parent_kind, answers.get(q.follows), q.condition))):
            out.append(q)
            keys.add(q.id)
    return tuple(out)


def read(form: Mapping[str, str | Sequence[str]], asked: Iterable[Question]) -> dict:
    """The answers a submitted form gives, in the stored shape, or
    ValueError (the question's id). `asked` are the screens a client is
    asked: steps() over the shown rows (a hidden one is skipped here too).
    `form` holds the posted fields, a text each or a list of texts (a
    multi's ticks; of several texts for one answer the last counts),
    already cleaned as a copy text is (copy.clean: the line breaks a
    browser sends as CRLF come back as they were stored). Every question
    asked must be answered: a choice with one of its options' texts as the
    row holds them now, a multi with one or more of them (stored in the
    options' order, each once), a scale with 1–10, yes / no with YES or NO,
    a free text not empty. A conditional question is asked only when its
    question was asked and answered as its condition says (is_asked, in
    order: a chain is read down its length); one not asked is left out,
    whatever was sent for it (without JS the page shows every question to
    everyone)."""
    answers: dict = {}
    for q in asked:
        if not q.shown or not is_asked(q, answers):
            continue
        sent = form.get(q.id, ())
        sent = [sent] if isinstance(sent, str) else list(sent)
        if q.kind == "multi":
            chosen = set(sent)
            if not chosen or not chosen <= set(q.options):
                raise ValueError(q.id)
            answers[q.id] = [option for option in dict.fromkeys(q.options) if option in chosen]
            continue
        given = sent[-1] if sent else ""
        if q.kind == "choice":
            if given not in q.options:
                raise ValueError(q.id)
            answers[q.id] = given
        elif q.kind == "scale":
            if given not in {str(n) for n in SCALE}:
                raise ValueError(q.id)
            answers[q.id] = int(given)
        elif q.kind == "yesno":
            if given not in (YES, NO):
                raise ValueError(q.id)
            answers[q.id] = given == YES
        else:
            if not given or len(given) > TEXT_MAX:
                raise ValueError(q.id)
            answers[q.id] = given
    return answers


def score(answers: Mapping, asked: Iterable[Question]) -> float | None:
    """The owner's formula over the questions asked: 0.6 × the mean of the
    baza scales + 0.4 × the mean of the navike scales, to one decimal (half
    up, on exact fractions). A group with no question gives its weight to
    the other; None when no question scores at all. A conditional scale
    scores only when it was asked (asked_of)."""
    asked = asked_of(asked, answers)
    means = {}
    for group in WEIGHTS:
        given = [answers[q.id] for q in asked
                 if q.kind == "scale" and q.scoring == group and _number(answers.get(q.id))]
        if given:
            means[group] = Fraction(sum(given), len(given))
    if not means:
        return None
    value = sum(WEIGHTS[g] * m for g, m in means.items()) if len(means) == len(WEIGHTS) else next(iter(means.values()))
    return math.floor(value * 10 + Fraction(1, 2)) / 10


def level_for(value: float) -> str:
    """Up to 4.0 početna, up to 7.0 srednja, above that napredna."""
    return "pocetna" if value <= 4.0 else "srednja" if value <= 7.0 else "napredna"


@dataclass(frozen=True)
class Result:
    score: float             # 0.0 when no question scores (a real score is 1.0 at least)
    level: str
    pain_level: int | None   # the pain question's answer; None with no pain question asked
    pain_high: bool          # the pain question at PAIN_HIGH or more: početna, and see the trainer first
    needs_review: bool       # the injuries question's yes: the trainer looks at the profile


def evaluate(answers: Mapping, asked: Iterable[Question]) -> Result:
    """Score and level over the questions asked, with the two safety rules
    on top: the pain question at PAIN_HIGH or more is početna whatever the
    score; the injuries question's yes needs the trainer's review. With no
    scored question, početna (and a score of 0.0, which no answer gives).
    A safety question that is conditional counts only when it was asked."""
    asked = asked_of(asked, answers)
    value = score(answers, asked)
    pain = next((answers.get(q.id) for q in asked if q.role == "pain"), None)
    pain = pain if _number(pain) else None
    pain_high = pain is not None and pain >= PAIN_HIGH
    review = any(answers.get(q.id) is True for q in asked if q.role == "injuries")
    level = "pocetna" if pain_high or value is None else level_for(value)
    return Result(0.0 if value is None else value, level, pain, pain_high, review)


def score_text(value: float) -> str:
    """A version-2 score as the karton says it: "6,4 / 10"."""
    return f"{value:.1f}".replace(".", ",") + f" / {MAX_SCORE}"


# ---- the editor: a question's settings, and what they do, said ----

def settings(now: Mapping, changes: Mapping[str, str]) -> dict:
    """A question's settings after an editor's change (POST
    /upitnik/pitanje/{id}), or ValueError with the sentence his bar shows.
    `now` holds the row's part, kind, scoring, role and shown; `changes`
    the posted fields, texts: part "1"–"4", kind (KINDS), scoring ("",
    "baza", "navike"), role ("", "pain", "injuries"), shown ("on", "off").
    Only a scale scores; the pain question is a scale, the injuries
    question a yes / no. A change of kind keeps the row and its answers,
    and is refused while the question scores or holds a role its new kind
    cannot: he takes that away first, so no score or safety rule goes
    without his knowing. Which other row loses a role this one takes is
    the database's to say (db.set_upitnik_question)."""
    if not changes:
        raise ValueError("Nepoznata postavka.")
    new = dict(now)
    for field, value in changes.items():
        if field == "part":
            if value not in {str(p) for p in PARTS}:
                raise ValueError("Nepoznat dio.")
            new["part"] = int(value)
        elif field == "kind":
            if value not in KINDS:
                raise ValueError("Nepoznata vrsta pitanja.")
            new["kind"] = value
        elif field == "scoring":
            if value not in SCORING:
                raise ValueError("Nepoznato bodovanje.")
            new["scoring"] = value
        elif field == "role":
            if value not in ROLE_LABELS:
                raise ValueError("Nepoznata uloga.")
            new["role"] = value
        elif field == "shown":
            if value not in ("on", "off"):
                raise ValueError("Nepoznata vrijednost.")
            new["shown"] = value == "on"
        else:
            raise ValueError("Nepoznata postavka.")
    if new["scoring"] and new["kind"] != "scale":
        if "scoring" in changes:
            raise ValueError("Boduje se samo skala (1–10).")
        raise ValueError("Ovo se pitanje boduje, a boduje se samo skala — prvo odaberi „Ne boduje se”.")
    if new["role"] and ROLES[new["role"]] != new["kind"]:
        pain = new["role"] == "pain"
        if "role" in changes:
            raise ValueError("Uloga Bolovi ide samo uz skalu (1–10)." if pain
                             else "Uloga Ozljede ide samo uz pitanje Da / Ne.")
        raise ValueError("Ovo je pitanje o bolovima, a ta uloga ide samo uz skalu — prvo makni ulogu." if pain
                         else "Ovo je pitanje o ozljedama, a ta uloga ide samo uz Da / Ne — prvo makni ulogu.")
    return new


def condition(question_id: int, parent: str, answer: str, rows: Sequence) -> tuple[int | None, str]:
    """The question a question is asked after and the answer that asks
    it, after an editor's change (POST /upitnik/pitanje/{id}: parent_id
    and condition, posted together), as the row stores them, or ValueError
    with the sentence his bar shows. `rows` are every question, in order
    (db.upitnik_questions(), read under the questions' lock). Both empty:
    asked always. Else the question must be one of these rows, never this
    one nor one that hangs under this one, however far down (no circle),
    and before it (its answer is in by then); of a kind whose answer a
    condition can name (CONDITION_KINDS: no free text); and the answer must
    fit it as it is now (fits: yes / no "yes" or "no", a scale ">=N" with N
    1–10, a choice or a multi one of its options), at most CONDITION_MAX
    characters (an option's text, as the column holds it)."""
    if not parent and not answer:
        return None, ""
    if not parent or not answer:
        raise ValueError("Odaberi pitanje i odgovor.")
    by_id = {row.id: row for row in rows}
    pid = int(parent) if parent.isdigit() else None
    if pid not in by_id:
        raise ValueError("Nepoznato pitanje.")
    if pid == question_id:
        raise ValueError("Pitanje ne može ovisiti o samome sebi.")
    seen, up = set(), by_id[pid].parent_id
    while up is not None and up not in seen:       # a stored circle (no route makes one) ends here too
        if up == question_id:
            raise ValueError("Pitanje ne može ovisiti o svom potpitanju.")
        seen.add(up)
        up = by_id[up].parent_id if up in by_id else None
    order = [row.id for row in rows]
    if question_id in order and order.index(pid) > order.index(question_id):
        raise ValueError("Pitanje može ovisiti samo o pitanju prije njega.")
    p = by_id[pid]
    if p.kind not in CONDITION_KINDS:
        raise ValueError("Pitanje sa slobodnim tekstom nema odgovor za uvjet.")
    if not fits(p.kind, p.option_items, answer):
        raise ValueError("Uz pitanje Da / Ne uvjet je Da ili Ne." if p.kind == "yesno"
                         else "Uz skalu uvjet je broj od 1 do 10." if p.kind == "scale"
                         else "To pitanje nema taj odgovor.")
    if len(answer) > CONDITION_MAX:
        raise ValueError(f"Uvjet može biti odgovor od najviše {CONDITION_MAX} znakova — skrati ga.")
    return pid, answer


def short(text: str, n: int = SHORT) -> str:
    """A text as the editor's lists show it: on one line, its first `n`
    characters, "…" when there is more."""
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rstrip() + "…"


def answer_choices(kind: str, options: Sequence[str]) -> list[tuple[str, str]]:
    """The answers a condition may name on a question of `kind`, as the
    editor's select lists them, (value, words): yes / no Da and Ne, a
    scale 1–10 (">=N", "N": the select says "ili više" after it), a choice
    or a multi its options (short); none for a free text."""
    if kind == "yesno":
        return [("yes", "Da"), ("no", "Ne")]
    if kind == "scale":
        return [(f">={n}", str(n)) for n in SCALE]
    if kind in OPTION_KINDS:
        return [(option, short(option)) for option in options]
    return []


def blocked_moves(questions: Sequence[Question]) -> dict[str, tuple[bool, bool]]:
    """Each question's ↑ and ↓ in the editor's order (every question):
    whether that move would put a question before the one it is asked
    after (db.move_upitnik_question refuses it: "Potpitanje ne može ići
    ispred svog pitanja."), so the page says so at the press."""
    out = {}
    for i, q in enumerate(questions):
        above = questions[i - 1] if i else None
        below = questions[i + 1] if i + 1 < len(questions) else None
        out[q.id] = (above is not None and q.parent == above.row,
                     below is not None and below.parent == q.row)
    return out


def setting_line(q: Question) -> str:
    """The grey line under a question's settings in edit mode, what they
    do: "Dio 2 · skala · boduje se: trening baza", "Dio 4 · skala · uloga:
    bolovi (7+ početna)"; a hidden question's says it is asked of nobody.
    When it is asked is condition_line's."""
    words = [f"Dio {q.part}", KIND_WORDS.get(q.kind, q.kind)]
    if not q.shown:
        hidden = "skriveno: nitko ga ne dobiva" + (" i ne boduje se" if q.scoring else "")
        if q.role:
            hidden += f", pravilo o {'bolovima' if q.role == 'pain' else 'ozljedama'} ne vrijedi"
        words.append(hidden)
        return " · ".join(words)
    if q.scoring:
        words.append(f"boduje se: {SCORING[q.scoring].lower()}")
    elif q.kind == "scale" and not q.role:
        words.append("ne boduje se")
    if q.role == "pain":
        words.append(f"uloga: bolovi ({PAIN_HIGH}+ početna)")
    elif q.role == "injuries":
        words.append("uloga: ozljede (Da traži pregled trenera)")
    return " · ".join(words)


def condition_words(condition: str) -> str:
    """A condition as the editor's line says it, after "pitanje N": "= Da",
    "= Ne", "≥ 4", "= Kod kuće s girjom"."""
    n = at_least(condition)
    if n is not None:
        return f"≥ {n}"
    return "= " + {"yes": "Da", "no": "Ne"}.get(condition, condition)


def condition_line(q: Question) -> str:
    """The editor's line under the grey one, when a question is asked only
    after an answer: "Pita se samo ako pitanje 16 = Da" ("… ≥ 4", "… = Kod
    kuće s girjom"); for a muted one, that nobody gets it and which hidden
    question is why ("Pita se samo ako pitanje 17 = Da — pitanje 16 je
    skriveno, pa ni ovo nitko ne dobiva"); and when its condition cannot
    work, that the question is asked always and why ("Pita se uvijek —
    uvjet ne vrijedi: pitanje 16 dolazi kasnije", "… pitanje je obrisano",
    "… pitanje 16 nema odgovor „Da”"). His page says the last two in
    amber. "" for a question asked always by its settings."""
    if not q.condition:
        return ""
    if q.muted:
        return (f"Pita se samo ako pitanje {q.parent_n} {condition_words(q.condition)} — "
                f"pitanje {q.muted_by} je skriveno, pa ni ovo nitko ne dobiva")
    if q.follows is not None:
        return f"Pita se samo ako pitanje {q.parent_n} {condition_words(q.condition)}"
    n = at_least(q.condition)
    said = f"{n} ili više" if n is not None else {"yes": "Da", "no": "Ne"}.get(q.condition, q.condition)
    why = {"gone": "pitanje je obrisano", "later": f"pitanje {q.parent_n} dolazi kasnije",
           "answer": f"pitanje {q.parent_n} nema odgovor „{said}”"}.get(q.void, "pitanje je obrisano")
    return f"Pita se uvijek — uvjet ne vrijedi: {why}"


def _pitanja(n: int) -> str:
    """"1 pitanje", "2 pitanja", "5 pitanja", "21 pitanje", "11 pitanja"."""
    return f"{n} pitanje" if n % 10 == 1 and n % 100 != 11 else f"{n} pitanja"


def scoring_summary(questions: Iterable[Question]) -> tuple[str, bool]:
    """The editor's line above the first question in edit mode: how many
    questions each group scores with (the shown scales no hidden question
    mutes) and what the result is then, and whether none scores at all
    (his page then says that every client starts at početna)."""
    questions = tuple(questions)
    count = {g: sum(1 for q in questions if q.shown and not q.muted and q.kind == "scale" and q.scoring == g)
             for g in WEIGHTS}
    line = f"Bodovanje: trening baza = {_pitanja(count['baza'])}, navike = {_pitanja(count['navike'])}."
    if count["baza"] and count["navike"]:
        line += " Rezultat = 0,6 × baza + 0,4 × navike."
    elif count["baza"]:
        line += " Rezultat = trening baza (navike nemaju pitanja)."
    elif count["navike"]:
        line += " Rezultat = navike (trening baza nema pitanja)."
    return line, not any(count.values())


# ---- the karton: every answer kept, under its question as it is now ----

def answer_text(value, yes: str = "Da", no: str = "Ne") -> str:
    """An answer as the karton prints it, by what was stored (a question's
    kind may have changed since): a scale's "7 / 10", yes / no as `yes` /
    `no` (the upitnik.yes / .no slots), a multi's texts joined with " · ",
    a text as it is."""
    if isinstance(value, bool):
        return yes if value else no
    if _number(value):
        return f"{value} / {MAX_SCORE}"
    if isinstance(value, list):
        return " · ".join(str(x) for x in value)
    return str(value)


# an answer's key: "q<id>", or an old follow-up's "q<id>b" that migration
# 5c1e7a9d2b48 had no question to give to (its question deleted before it)
_ANSWER_KEY = re.compile(r"q([1-9][0-9]*)(b?)")


def answer_rows(answers: Mapping, rows: Iterable, yes: str = "Da", no: str = "Ne") -> list[tuple[str, str, int]]:
    """(question, answer, depth) for every answer stored, the trainer's
    list on the karton. `rows` are every question there is now
    (db.upitnik_questions(): the hidden too), in their order: each answer
    of one prints under its current text (an emptied text names the
    question by its place, "Pitanje 3"), a conditional question's `depth`
    levels in, under the question it is asked after (steps: as far as its
    condition works now); then the answers to questions deleted since,
    under REMOVED, by their number (an old follow-up's one level in). A
    client's answers are kept as they were given: nothing here drops one."""
    out, seen = [], set()
    for q in steps(rows):
        if q.id in answers:
            seen.add(q.id)
            out.append((q.text or f"Pitanje {q.n}", answer_text(answers[q.id], yes, no), q.depth))
    gone = [(int(m.group(1)), m.group(2), key) for key in answers
            if key not in seen and (m := _ANSWER_KEY.fullmatch(key))]
    out += [(REMOVED, answer_text(answers[key], yes, no), 1 if b else 0) for _, b, key in sorted(gone)]
    return out


# The days a week and the minutes (q2, q3: the gym owner's first questions,
# their ids since they became rows) as the karton's chips, with the words a
# bare number needs ("3" -> "3 dana tjedno", "45-60" -> "45-60 min"), left
# off when his option already says them (a re-worded "3 puta tjedno").
_CHIP_UNITS = {"q2": (" dana tjedno", "tjed"), "q3": (" min", "min")}


def chips(answers: Mapping, rows: Iterable) -> list[str]:
    """Part 1's answers as the karton shows them, in the questionnaire's
    order: each question of part 1 there is now (a hidden one too) answered
    with a text or with several (a multi's, joined with " · ")."""
    out = []
    for row in rows:
        if row.part != 1:
            continue
        key = f"q{row.id}"
        given = answers.get(key)
        if isinstance(given, list):
            given = answer_text(given)
        if isinstance(given, str) and given:
            unit, word = _CHIP_UNITS.get(key, ("", ""))
            out.append(given + unit if unit and word not in given.lower() else given)
    return out


def pain_where(answers: Mapping, rows: Iterable) -> str:
    """Where it hurts, as the client wrote it, for the trainer's pain flag
    on the karton: the answer to the first free-text question asked after
    the pain question (the first text row, in order, whose parent is the
    row holding the pain role now, whatever its condition: "Gdje te
    boli?", asked at 4 or more, as migration 5c1e7a9d2b48 and the defaults
    made it); "" when there is no such question or no answer to it. `rows`
    are every question there is now (db.upitnik_questions())."""
    rows = list(rows)
    pain = next((row for row in rows if row.role == "pain" and row.kind == ROLES["pain"]), None)
    where = next((row for row in rows if pain is not None and row.parent_id == pain.id and row.kind == "text"),
                 None)
    given = answers.get(f"q{where.id}") if where is not None else None
    return given if isinstance(given, str) else ""


# ---- version 1 (3.9. – 26.10.2026), frozen: an old row's answers ----
# {key: the option's index}; (label, points). Read only (answer_rows_v1).
QUESTIONS_V1 = (
    {"key": "staz", "text": "Koliko dugo redovito treniraš?",
     "options": (("Ne treniram", 0), ("Manje od 6 mjeseci", 1),
                 ("6 mjeseci – 2 godine", 2), ("Više od 2 godine", 3))},
    {"key": "tjedno", "text": "Koliko treninga tjedno trenutno odradiš?",
     "options": (("Nijedan", 0), ("1–2", 1), ("3–4", 2), ("5 ili više", 3))},
    {"key": "sklekovi", "text": "Koliko sklekova napraviš u jednoj seriji?",
     "options": (("0–5", 0), ("6–15", 1), ("16–30", 2), ("Više od 30", 3))},
    {"key": "cucanj", "text": "Kakvo je tvoje iskustvo s čučnjem pod opterećenjem?",
     "options": (("Nikad ga nisam radio/la", 0), ("Povremeno, lakši utezi", 1),
                 ("Redovito treniram", 2), ("Radim teške serije", 3))},
    {"key": "ozljede", "text": "Imaš li ozljede ili bolove koji ograničavaju trening?",
     "options": (("Da, značajno", 0), ("Povremeno", 1), ("Ne", 2))},
)
MAX_SCORE_V1 = sum(max(p for _, p in q["options"]) for q in QUESTIONS_V1)   # 14


def answer_rows_v1(answers: Mapping) -> list[tuple[str, str, bool]]:
    """An old row's answers as answer_rows gives a new one's: (question,
    the option it picked, False), for each answer QUESTIONS_V1 can read."""
    rows = []
    for q in QUESTIONS_V1:
        i = answers.get(q["key"])
        if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(q["options"]):
            rows.append((q["text"], q["options"][i][0], False))
    return rows
