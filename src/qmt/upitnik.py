"""The online-trening upitnik, version 2 (26.10.2026): the gym owner's final
questionnaire, asked one question per screen on /upitnik (Shape's design).

Fifteen questions in four parts, and two free texts asked only when an
answer calls for them:

  Dio 1, q1–q4 (a choice each): the goal, days a week, minutes a training,
      where. Not scored: they are for the programme's CONTENT, which they
      will choose later (the owner, 26.10.2026: "Later on, we will implement
      different types of training depending on the equipment … we will
      automatically send them to the appropriate training group"). Stored
      with the answers and shown on the karton; they route nothing yet.
  Dio 2, q5–q11 (a scale of 1 to 10 each): training and habits, the score.
  Dio 3, q12, q13 (scales): for the trainer only, shown on the karton.
  Dio 4, q14 (a scale: pain) and q15 (yes / no: injuries): safety. q14 at 4
      or more asks q14b, where it hurts; q15 yes asks q15b, a short note.

The score, the owner's formula: trening baza = the mean of q5, q6 and q7;
navike = the mean of q8, q9, q10 and q11; score = 0.6 × baza + 0.4 × navike,
to one decimal. Up to 4.0 početna, up to 7.0 srednja, above that napredna.
(0.6 of a mean of three and 0.4 of a mean of four make every score a whole
tenth, so the rounding only takes the float's noise away.) His two safety
rules: q14 at 7 or more is početna whatever the score, with a word to see
the trainer first (pain_high, upitnik.pain_note); q15 yes flags the profile
for the trainer to look at (needs_review).

The questionnaire decides the LEVEL only (the owner: "The questionnaire will
only determine the difficulty level of the trainings … for now"): every
response's goal, the column the programmes are matched on (db.programs_for_
combo, db.client_can_view), is GOAL, "cijelo", so a client gets the level's
whole-body programmes until the "type of training" step comes. q1's goal is
kept in the answers and shown on the karton; it routes nothing yet.

The structure lives here, in code: the questions' order, parts and kinds,
which are scored, the scoring and the safety rules. Every WORD of it is a
copy slot the gym owner retypes in place on /upitnik (src/qmt/copy.py,
upitnik.*: the title, the intro, the parts' headings, each question, a
choice's options, a scale's two ends, yes / no, the consent, the buttons).
Re-wording is his; adding or removing a QUESTION is not: the scoring
depends on the structure, so a new question is a code change here.

Answers are stored as JSON (models.OnboardingResponse.answers): a choice as
the option's TEXT at the time, never its index, so a later re-wording never
garbles an old answer; a scale as an int, yes / no as a bool, a free text
as a string; a follow-up that was not asked is absent.

Version 1 (3.9. – 26.10.2026: five scored questions and a goal, points per
option, the goal routing too) stays readable: QUESTIONS_V1 renders an old
row's answers on the karton (OnboardingResponse.version 1). Such a row
still counts as a filled upitnik, its level and goal still route, until
the client fills the new one.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

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

VERSION = 2          # OnboardingResponse.version of a response to QUESTIONS
GOAL = "cijelo"      # every version-2 response's goal (above)


@dataclass(frozen=True)
class Question:
    """One screen of the questionnaire. `id` is the answer's key and its
    slots' (upitnik.<id>.text, a choice's .options, a scale's .low / .high).
    A follow-up (`follows`) is asked only when its question's answer calls
    for it: a scale's at `ask_from` or more, a yes / no's equal to `ask_if`."""
    id: str
    part: int                     # 1–4: the heading above it, upitnik.part<n>.h
    kind: str                     # "choice" | "scale" | "yesno" | "text"
    scored: bool = False          # in the score (q5–q11)
    follows: str | None = None
    ask_from: int | None = None
    ask_if: bool | None = None


PAIN_ASK = 4         # q14 at this or more asks where it hurts (q14b)
PAIN_HIGH = 7        # q14 at this or more: početna whatever the score, and see the trainer first

BASE = ("q5", "q6", "q7")              # trening baza
HABITS = ("q8", "q9", "q10", "q11")    # navike
MAX_SCORE = 10
SCALE = range(1, 11)                   # a scale question's answers
MIN_OPTIONS = 2                        # a choice keeps at least this many options (app.py, the editor)
TEXT_MAX = 2000                        # a free text's characters, as a copy text's (copy.CAP)

QUESTIONS: tuple[Question, ...] = (
    Question("q1", 1, "choice"),
    Question("q2", 1, "choice"),
    Question("q3", 1, "choice"),
    Question("q4", 1, "choice"),
    *(Question(q, 2, "scale", scored=True) for q in BASE + HABITS),
    Question("q12", 3, "scale"),
    Question("q13", 3, "scale"),
    Question("q14", 4, "scale"),
    Question("q15", 4, "yesno"),
)
FOLLOWUPS: tuple[Question, ...] = (
    Question("q14b", 4, "text", follows="q14", ask_from=PAIN_ASK),
    Question("q15b", 4, "text", follows="q15", ask_if=True),
)
# the screens in order: each follow-up right after its question
STEPS: tuple[Question, ...] = tuple(
    s for q in QUESTIONS for s in (q, *(f for f in FOLLOWUPS if f.follows == q.id)))

YES, NO = "da", "ne"                   # a yes / no question's posted values


def is_asked(q: Question, answers: Mapping) -> bool:
    """Whether `q` is asked, given the answers before it: always, but for a
    follow-up, which its question's answer must call for."""
    if q.follows is None:
        return True
    given = answers.get(q.follows)
    if q.ask_if is not None:
        return given is q.ask_if
    return isinstance(given, int) and not isinstance(given, bool) and given >= q.ask_from


def read(form: Mapping[str, str], options: Mapping[str, Sequence[str]]) -> dict:
    """The answers a submitted form gives, in the stored shape, or
    ValueError. `form` holds the posted fields, each already cleaned as a
    copy text is (copy.clean: the line breaks a browser sends as CRLF come
    back as they were stored); `options` each choice question's options as
    its slot holds them now. Every question asked must be answered: a
    choice with one of its options' texts, a scale with 1–10, yes / no with
    YES or NO, a follow-up's free text not empty. A follow-up not asked is
    left out, whatever was sent for it (without JS the page shows it to
    everyone)."""
    answers: dict = {}
    for q in STEPS:
        if not is_asked(q, answers):
            continue
        given = form.get(q.id, "")
        if q.kind == "choice":
            if given not in options.get(q.id, ()):
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


def score(answers: Mapping) -> float:
    """The owner's formula: 0.6 × the mean of BASE + 0.4 × the mean of
    HABITS, to one decimal."""
    base = sum(answers[q] for q in BASE) / len(BASE)
    habits = sum(answers[q] for q in HABITS) / len(HABITS)
    return round(0.6 * base + 0.4 * habits, 1)


def level_for(value: float) -> str:
    """Up to 4.0 početna, up to 7.0 srednja, above that napredna."""
    return "pocetna" if value <= 4.0 else "srednja" if value <= 7.0 else "napredna"


@dataclass(frozen=True)
class Result:
    score: float
    level: str
    pain_level: int          # q14's answer
    pain_high: bool          # q14 at PAIN_HIGH or more: početna, and see the trainer first
    needs_review: bool       # q15 yes: the trainer looks at the profile


def evaluate(answers: Mapping) -> Result:
    """Score and level, with the two safety rules on top: q14 at PAIN_HIGH
    or more is početna whatever the score; q15 yes needs the trainer's
    review."""
    value, pain = score(answers), answers["q14"]
    pain_high = pain >= PAIN_HIGH
    return Result(value, "pocetna" if pain_high else level_for(value), pain, pain_high, answers["q15"] is True)


def score_text(value: float) -> str:
    """A version-2 score as the karton says it: "6,4 / 10"."""
    return f"{value:.1f}".replace(".", ",") + f" / {MAX_SCORE}"


# Part 1's answers as the karton's chips, each with the words a bare number
# needs ("3" -> "3 dana tjedno", "45-60" -> "45-60 min"), left off when the
# gym owner's option already says them (a re-worded "3 puta tjedno").
_CHIP_UNITS = (("q1", "", ""), ("q2", " dana tjedno", "tjed"), ("q3", " min", "min"), ("q4", "", ""))


def chips(answers: Mapping) -> list[str]:
    """Part 1's four answers as the karton shows them, in order: the goal,
    the days a week, the minutes, the place."""
    out = []
    for q, unit, word in _CHIP_UNITS:
        text = answers.get(q)
        if isinstance(text, str) and text:
            out.append(text + unit if unit and word not in text.lower() else text)
    return out


def answer_rows(answers: Mapping, text: Callable[[str], str]) -> list[tuple[str, str, bool]]:
    """(question, answer, is a follow-up) for every question answered, in
    the questionnaire's order, the trainer's list on the karton. `text`
    gives a slot's text by its key (the question as the gym owner words it
    now; yes / no, upitnik.yes / .no). A scale reads "7 / 10"."""
    rows = []
    for q in STEPS:
        if q.id not in answers:
            continue
        given = answers[q.id]
        if q.kind == "scale":
            shown = f"{given} / {MAX_SCORE}"
        elif q.kind == "yesno":
            shown = text("upitnik.yes" if given is True else "upitnik.no")
        else:
            shown = str(given)
        rows.append((text(f"upitnik.{q.id}.text"), shown, q.follows is not None))
    return rows


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
