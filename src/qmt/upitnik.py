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
most one of each), each asking a free text when its answer calls for it
(`followup_text`). A hidden question (`shown` off) is asked of nobody and
scores nothing.

The gym owner's fifteen start it (copy.UPITNIK_DEFAULT_QUESTIONS, ids
1–15): part 1, q1–q4, the goal, the days a week, the minutes and the place
(choices, never scored: they are for the programme's CONTENT, which they
will choose later; the owner, 26.10.2026: "Later on, we will implement
different types of training depending on the equipment … we will
automatically send them to the appropriate training group"); part 2,
q5–q11, the scored scales (q5–q7 trening baza, q8–q11 navike); part 3,
q12–q13, scales for the trainer; part 4, q14 the pain question (a scale: at
4 or more it asks where it hurts) and q15 the injuries question (yes / no:
yes asks for a short note).

What stays here, in code, works on whatever the rows say: the screens a
list of rows makes (steps: each safety question followed by its
follow-up), what a submitted form must hold (read), the owner's formula
and its thresholds (score, level_for), his two safety rules with their
numbers (evaluate: PAIN_ASK, PAIN_HIGH, needs_review), the rules a
question's settings keep (settings), the editor's lines under his
settings (setting_line, scoring_summary) and the karton's helpers
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
question's row: "q<id>", a follow-up's "q<id>b" (the fifteen kept their ids
when they became rows, so the answers given before keep their meaning; an
id is never used twice). A choice is stored as the option's TEXT at the
time, never its index, so a later re-wording never garbles an old answer; a
multi as the list of the chosen options' texts; a scale as an int, yes / no
as a bool, a free text as a string; a follow-up that was not asked is
absent. Nothing is pruned when a question goes: the karton prints every
answer kept, under its question's current text, or under "(pitanje
uklonjeno)" when the row is gone (answer_rows).

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

PAIN_ASK = 4         # the pain question at this or more asks where it hurts (its follow-up)
PAIN_HIGH = 7        # the pain question at this or more: početna whatever the score, and see the trainer first

MAX_SCORE = 10
SCALE = range(1, 11)                   # a scale question's answers
MIN_OPTIONS = 2                        # a choice (a multi) keeps at least this many options (app.py, the editor)
TEXT_MAX = 2000                        # a free text's characters, as a copy text's (copy.CAP)
YES, NO = "da", "ne"                   # a yes / no question's posted values
REMOVED = "(pitanje uklonjeno)"        # the karton's question for an answer whose question was deleted since


@dataclass(frozen=True)
class Question:
    """One screen of the questionnaire, made from a row (steps). `id` is
    the answer's key, "q<row>", a follow-up's "q<row>b"; `row` the row's id
    (a follow-up's: its question's) and `n` its place in the list it was
    made from, 1-based (the editor's "Pitanje 7"). A follow-up (`follows`)
    is asked only when its question's answer calls for it: a scale's at
    `ask_from` or more, a yes / no's equal to `ask_if`."""
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
    shown: bool = True            # a hidden question (its follow-up too) is asked of nobody
    follows: str | None = None
    ask_from: int | None = None
    ask_if: bool | None = None


def steps(rows: Iterable) -> tuple[Question, ...]:
    """The screens a list of rows makes, in its order (db.upitnik_questions,
    by position: a client's the shown rows, the editor's every row): each
    row's question, and right after a safety question its follow-up, the
    free text its answer may call for (the pain question's at PAIN_ASK or
    more, the injuries question's at yes). A scoring holds only on a scale,
    a role only on a row of the kind it needs and only on the first row
    that holds it: what the routes never let in (settings, the role's
    unique index) asks nothing here either."""
    out: list[Question] = []
    taken: set[str] = set()
    for n, row in enumerate(rows, start=1):
        role = row.role if ROLES.get(row.role) == row.kind and row.role not in taken else ""
        taken.add(role)
        q = Question(f"q{row.id}", row.id, n, row.part, row.kind, row.text, tuple(row.option_items),
                     row.low, row.high, row.scoring if row.kind == "scale" and row.scoring in WEIGHTS else "",
                     role, row.shown)
        out.append(q)
        if role:
            out.append(Question(f"q{row.id}b", row.id, n, row.part, "text", row.followup_text, shown=row.shown,
                                follows=q.id, ask_from=PAIN_ASK if role == "pain" else None,
                                ask_if=True if role == "injuries" else None))
    return tuple(out)


def _number(value) -> bool:
    """A scale's answer: an int (a bool is an int to Python, and no number here)."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_asked(q: Question, answers: Mapping) -> bool:
    """Whether `q` is asked, given the answers before it: always, but for a
    follow-up, which its question's answer must call for."""
    if q.follows is None:
        return True
    given = answers.get(q.follows)
    if q.ask_if is not None:
        return given is q.ask_if
    return _number(given) and given >= q.ask_from


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
    a free text (a follow-up's too) not empty. A follow-up not asked is
    left out, whatever was sent for it (without JS the page shows it to
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
    the other; None when no question scores at all."""
    asked = tuple(asked)
    means = {}
    for group in WEIGHTS:
        given = [answers[q.id] for q in asked
                 if q.shown and q.kind == "scale" and q.scoring == group and _number(answers.get(q.id))]
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
    scored question, početna (and a score of 0.0, which no answer gives)."""
    asked = tuple(asked)
    value = score(answers, asked)
    pain = next((answers.get(q.id) for q in asked if q.shown and q.role == "pain"), None)
    pain = pain if _number(pain) else None
    pain_high = pain is not None and pain >= PAIN_HIGH
    review = any(answers.get(q.id) is True for q in asked if q.shown and q.role == "injuries")
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


def setting_line(q: Question) -> str:
    """The grey line under a question's settings in edit mode, what they
    do: "Dio 2 · skala · boduje se: trening baza", "Dio 4 · skala · uloga:
    bolovi (4+ pita gdje, 7+ početna)"; a hidden question's says it is
    asked of nobody, a follow-up's when it is asked."""
    if q.follows is not None:
        if not q.shown:
            return f"Dodatno pitanje uz pitanje {q.n} · skriveno s njim"
        when = f"odgovor {q.ask_from} ili više" if q.ask_from is not None else "odgovor Da"
        return f"Dodatno pitanje uz pitanje {q.n} · pita se kad je {when}"
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
        words.append(f"uloga: bolovi ({PAIN_ASK}+ pita gdje, {PAIN_HIGH}+ početna)")
    elif q.role == "injuries":
        words.append("uloga: ozljede (Da pita opis i traži pregled trenera)")
    return " · ".join(words)


def _pitanja(n: int) -> str:
    """"1 pitanje", "2 pitanja", "5 pitanja", "21 pitanje", "11 pitanja"."""
    return f"{n} pitanje" if n % 10 == 1 and n % 100 != 11 else f"{n} pitanja"


def scoring_summary(questions: Iterable[Question]) -> tuple[str, bool]:
    """The editor's line above the first question in edit mode: how many
    questions each group scores with (the shown scales) and what the result
    is then, and whether none scores at all (his page then says that every
    client starts at početna)."""
    questions = tuple(questions)
    count = {g: sum(1 for q in questions if q.shown and q.kind == "scale" and q.scoring == g) for g in WEIGHTS}
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


_ANSWER_KEY = re.compile(r"q([1-9][0-9]*)(b?)")


def answer_rows(answers: Mapping, rows: Iterable, yes: str = "Da", no: str = "Ne") -> list[tuple[str, str, bool]]:
    """(question, answer, is a follow-up) for every answer stored, the
    trainer's list on the karton. `rows` are every question there is now
    (db.upitnik_questions(): the hidden too), in their order: each answer
    of one prints under its current text (a follow-up's under its
    follow-up's, wherever the role is now; an emptied text names the
    question by its place, "Pitanje 3"); then the answers to questions
    deleted since, under REMOVED, by their number. A client's answers are
    kept as they were given: nothing here drops one."""
    out, seen = [], set()
    for n, row in enumerate(rows, start=1):
        for key, text, follow in ((f"q{row.id}", row.text, False), (f"q{row.id}b", row.followup_text, True)):
            if key in answers:
                seen.add(key)
                name = text or (f"Pitanje {n}, dodatno" if follow else f"Pitanje {n}")
                out.append((name, answer_text(answers[key], yes, no), follow))
    gone = [(int(m.group(1)), m.group(2), key) for key in answers
            if key not in seen and (m := _ANSWER_KEY.fullmatch(key))]
    out += [(REMOVED, answer_text(answers[key], yes, no), bool(b)) for _, b, key in sorted(gone)]
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


def pain_where(answers: Mapping) -> str | None:
    """Where it hurts, as the client wrote it, for the trainer's pain flag
    on the karton: the follow-up asked after a scale ("q<id>b" whose
    "q<id>" holds a number). Only the pain question, a scale, has one (the
    injuries question's follows a yes / no), so this finds it in any
    response, whichever question held the role when it was given."""
    for key, given in answers.items():
        if key.endswith("b") and isinstance(given, str) and _number(answers.get(key[:-1])):
            return given
    return None


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
