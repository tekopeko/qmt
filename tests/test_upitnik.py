"""The online-trening upitnik, version 2 (26.10.2026): the gym owner's
questionnaire. Its questions are rows since 26.10.2026
(models.UpitnikQuestion), which he adds, removes, hides, reorders and
classifies in edit mode on /upitnik, and since 27.10.2026 asks one only
after a given answer to an earlier one ("Pita se"), chains included; the
questions he started with (copy.UPITNIK_DEFAULT_QUESTIONS: the fifteen,
ids 1–15, and the two asked after the safety questions, q16 "Gdje te
boli?" at q14 ≥ 4 and q17 "Opiši ukratko." at q15 Da) are seeded here
before every test, as the migrations and the demo seed make them.
src/qmt/upitnik.py holds
what stays code, working on whatever the rows say: the steps, read, the
score (0.6 × the mean of the baza scales + 0.4 × the mean of the navike
scales, to one decimal; a group with no question gives its weight to the
other; none at all: početna), the thresholds (up to 4.0 početna, up to 7.0
srednja, above napredna) and the two safety rules (the pain question at 7
or more: početna, and see the trainer first; the injuries question's yes:
the trainer reviews the profile).

Here: the structure the rows make, the score and read over the live
structure (a question deleted, hidden, added, a role moved, a multi of
several options), the conditions (a chain yes → yes → choice, a scale's
and a multi's, and the ones that cannot work: a parent hidden, after its
question, deleted, unable to give the answer), POST /upitnik (what a
submission must hold, what is stored), the editor's routes (add, delete,
move and its refusal, settings and their rules, Pita se's among them, a
client's 403), a question's words as virtual keys on POST /copy/{key}, the
editor's page (the lines that say what the settings do and when a question
is asked, the summary, the Pita se controls), the karton's block for a new
response, an old one, one whose questions changed since and a chain's
indented answers, the migrations (the one that made the rows already there
version 1, the one that made the slots rows, the one that made the
follow-ups questions, from a database shaped like prod's), and two editors
at once. One question per screen, the editor's controls and the walk
through them, in a browser, are tests/test_upitnik_ui.py.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import threading
from datetime import date, datetime
from html import unescape
from urllib.parse import unquote

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect, text as sa_text

from qmt import auth, config, copy, db, upitnik
from qmt.models import Base, User
from qmt.web.app import app

# the gym owner's questions, by their answers' keys
DEFAULTS = {f"q{q['id']}": q for q in copy.UPITNIK_DEFAULT_QUESTIONS}
CHOICES = {key: q["options"] for key, q in DEFAULTS.items() if q["kind"] == "choice"}          # q1–q4
BASE = tuple(key for key, q in DEFAULTS.items() if q["scoring"] == "baza")                    # q5–q7
HABITS = tuple(key for key, q in DEFAULTS.items() if q["scoring"] == "navike")                # q8–q11
# each question's text as they start (q16 "Gdje te boli?", q17 "Opiši ukratko.")
TEXT = {key: q["text"] for key, q in DEFAULTS.items()}
# their order: q16 under q14, q17 under q15
ORDER = list(range(1, 15)) + [16, 15, 17]


def seed_questions() -> None:
    """The seventeen, with their ids, as the migrations and the demo seed make them."""
    for question in copy.UPITNIK_DEFAULT_QUESTIONS:
        db.add_upitnik_question(None, question)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    seed_questions()
    yield


def make_user(email: str, is_trainer: bool = False, plans: tuple[str, ...] = ("online",)) -> int:
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    db.update_profile(u.id, email.split("@")[0], "Test", date(1990, 1, 1), "")
    if is_trainer:
        with db.session_scope() as s:
            s.get(User, u.id).is_trainer = True
    for plan in plans:
        db.record_payment(u.id, plan)
    return u.id


def client_for(email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"email": email, "password": "lozinka123"}, follow_redirects=False)
    assert r.status_code == 303, "login failed"
    return c


def client_for_trainer() -> TestClient:
    """The studio's account, a trainer with no plan of its own, logged in."""
    make_user("studio@test.local", is_trainer=True, plans=())
    return client_for("studio@test.local")


def asked() -> tuple[upitnik.Question, ...]:
    """The steps a client is asked now: the shown rows no hidden question
    mutes, of every row (upitnik.client_steps, as both routes build them)."""
    return upitnik.client_steps(db.upitnik_questions())


def answers(base=(5, 5, 5), habits=(5, 5, 5, 5), **changes) -> dict:
    """A whole set of answers to the fifteen as stored: part 1 each choice's
    first option, the scored scales as given (q5–q7, q8–q11), q12 and q13
    at 5, no pain (q14 at 1: q16 is not asked), no injuries (q17 is not
    asked); `changes` on top."""
    out = {key: options[0] for key, options in CHOICES.items()}
    out.update(zip(BASE, base))
    out.update(zip(HABITS, habits))
    out.update({"q12": 5, "q13": 5, "q14": 1, "q15": False})
    out.update(changes)
    return out


def form(**changes) -> dict[str, str]:
    """A whole valid submission as the browser posts it: answers()' values
    as text (yes / no as "da" / "ne"), the consent ticked. A change to None
    leaves that field out."""
    out = {q: ("da" if v is True else "ne" if v is False else str(v)) for q, v in answers().items()}
    out["consent"] = "da"
    out.update(changes)
    return {k: v for k, v in out.items() if v is not None}


def question(qid: int):
    return db.upitnik_question(qid)


# ---------- the structure: the fifteen as rows ----------

def test_the_defaults_are_rows_in_four_parts_with_two_questions_asked_after_the_safety_ones():
    """q1–q4 choices (part 1), q5–q11 the scored scales (part 2: baza
    q5–q7, navike q8–q11), q12 and q13 scales for the trainer (part 3), q14
    the pain question (a scale) and q15 the injuries question (yes / no) in
    part 4, each with a free-text question right under it that is asked
    after it (27.10.2026, the roles' follow-ups until then): q16 "Gdje te
    boli?" at 4 or more, q17 "Opiši ukratko." at Da. Their words are the
    rows', not slots: the upitnik.* slots left are the words around the
    questions."""
    steps = asked()
    assert [q.id for q in steps] == [f"q{n}" for n in ORDER]
    shape = {q.id: (q.part, q.kind, q.scoring, q.role) for q in steps}
    assert shape == {**{f"q{n}": (1, "choice", "", "") for n in range(1, 5)},
                     **{q: (2, "scale", "baza", "") for q in ("q5", "q6", "q7")},
                     **{q: (2, "scale", "navike", "") for q in ("q8", "q9", "q10", "q11")},
                     "q12": (3, "scale", "", ""), "q13": (3, "scale", "", ""), "q14": (4, "scale", "", "pain"),
                     "q16": (4, "text", "", ""), "q15": (4, "yesno", "", "injuries"), "q17": (4, "text", "", "")}
    follow = {q.id: (q.follows, q.condition, q.depth) for q in steps if q.follows}
    assert follow == {"q16": ("q14", ">=4", 1), "q17": ("q15", "yes", 1)}
    assert all(not q.void for q in steps)
    assert [q.id for q in db.upitnik_questions()] == ORDER
    assert all(len(q.options) >= upitnik.MIN_OPTIONS for q in steps if q.kind == "choice")
    assert {k for k in copy.SLOTS if k.startswith("upitnik.")} == {
        "upitnik.title", "upitnik.intro", "upitnik.yes", "upitnik.no", "upitnik.consent", "upitnik.submit",
        "upitnik.back", "upitnik.next", "upitnik.pain_note", *(f"upitnik.part{n}.h" for n in range(1, 5))}
    assert question(13).text.startswith("Koliko ti je važna")            # no emoji since 26.10.2026 (the owner)
    assert question(1).option_items[3] == "Rehabilitacija / rješavanje bolova"
    assert [(question(n).text, question(n).parent_id, question(n).condition) for n in (16, 17)] == [
        ("Gdje te boli?", 14, ">=4"), ("Opiši ukratko.", 15, "yes")]
    assert db.add_upitnik_question(None).id == 18                        # the sequence past them


# ---------- the score: the owner's formula and his two safety rules ----------

def test_the_owners_formula_on_three_hand_computed_examples():
    """One per level, at the edges, by hand: a mean of three and a mean of
    four, weighted 0.6 and 0.4, to one decimal."""
    # početna at its edge: baza (4+4+4)/3 = 4, navike (4+4+4+4)/4 = 4; 0.6·4 + 0.4·4 = 4.0
    r = upitnik.evaluate(answers((4, 4, 4), (4, 4, 4, 4)), asked())
    assert (r.score, r.level) == (4.0, "pocetna")
    # a tenth more is srednja: navike (4+4+4+5)/4 = 4.25; 2.4 + 1.7 = 4.1
    r = upitnik.evaluate(answers((4, 4, 4), (4, 4, 4, 5)), asked())
    assert (r.score, r.level) == (4.1, "srednja")
    # srednja at its edge: baza (10+9+9)/3 = 9.333…, navike (4+4+3+3)/4 =
    # 3.5; 0.6·9.333… + 0.4·3.5 = 5.6 + 1.4 = 7.0. The floats add up to
    # 7.000000000000001, which unrounded would be napredna; the score is
    # worked in exact fractions.
    assert 0.6 * (28 / 3) + 0.4 * (14 / 4) > 7.0
    r = upitnik.evaluate(answers((10, 9, 9), (4, 4, 3, 3)), asked())
    assert (r.score, r.level) == (7.0, "srednja")
    # napredna just past it: baza (8+7+7)/3 = 7.333…, navike (7+7+6+7)/4 = 6.75; 4.4 + 2.7 = 7.1
    r = upitnik.evaluate(answers((8, 7, 7), (7, 7, 6, 7)), asked())
    assert (r.score, r.level) == (7.1, "napredna")
    # the two ends of the range
    assert upitnik.evaluate(answers((1, 1, 1), (1, 1, 1, 1)), asked()).score == 1.0
    assert upitnik.evaluate(answers((10, 10, 10), (10, 10, 10, 10)), asked()).score == 10.0
    # every score of the fifteen is a whole tenth: (2 × the three + the four) / 10
    steps = asked()
    for s3 in range(3, 31):
        for s4 in range(4, 41):
            assert upitnik.score(answers((s3, 0, 0), (s4, 0, 0, 0)), steps) == (2 * s3 + s4) / 10
    assert upitnik.score_text(6.4) == "6,4 / 10" and upitnik.score_text(10.0) == "10,0 / 10"


def test_pain_at_seven_or_more_is_pocetna_whatever_the_score():
    """The pain question at 7 or more: početna, and pain_high (the client is
    told to see the trainer first); the score stays what the formula says.
    At 6 the score decides."""
    top = answers((10, 10, 10), (10, 10, 10, 10))
    r = upitnik.evaluate({**top, "q14": 6, "q16": "leđa"}, asked())
    assert (r.score, r.level, r.pain_level, r.pain_high) == (10.0, "napredna", 6, False)
    for pain in (7, 10):
        r = upitnik.evaluate({**top, "q14": pain, "q16": "leđa"}, asked())
        assert (r.score, r.level, r.pain_level, r.pain_high) == (10.0, "pocetna", pain, True)


def test_injuries_flag_the_profile_for_the_trainer_and_change_no_level():
    assert not upitnik.evaluate(answers(), asked()).needs_review
    r = upitnik.evaluate(answers(q15=True, q17="Operacija koljena 2023."), asked())
    assert r.needs_review and (r.score, r.level, r.pain_high) == (5.0, "srednja", False)


def test_parts_one_and_three_and_the_safety_questions_do_not_move_the_score():
    """q1–q4 (they will choose the content), q12 and q13 (the trainer's
    information) and the safety questions never change the score."""
    scored, steps = ((6, 7, 5), (6, 8, 7, 5)), asked()
    expected = upitnik.score(answers(*scored), steps)
    for q, options in CHOICES.items():
        for option in options:
            assert upitnik.score(answers(*scored, **{q: option}), steps) == expected
    for other in ("q12", "q13", "q14"):
        for value in upitnik.SCALE:
            assert upitnik.score(answers(*scored, **{other: value}), steps) == expected
    assert upitnik.score(answers(*scored, q15=True), steps) == expected


def test_the_score_follows_the_questions_there_are():
    """A baza question deleted: baza is the mean of the rest. One hidden:
    it is asked of nobody and scores nothing. A new scale that scores
    navike joins its group. A group with no question gives its weight to
    the other. No scored question at all: početna, whatever the answers,
    and a score of 0.0 (no answer gives one under 1.0)."""
    six_four = answers((6, 6, 6), (4, 4, 4, 4))                     # 0.6·6 + 0.4·4 = 5.2
    assert upitnik.score(six_four, asked()) == 5.2
    given = answers((9, 3, 3), (4, 4, 4, 4))                        # baza 5: 3.0 + 1.6 = 4.6
    assert upitnik.score(given, asked()) == 4.6
    db.delete_upitnik_question(5)                                   # baza (3+3)/2 = 3: 1.8 + 1.6
    assert upitnik.score(given, asked()) == 3.4
    db.set_upitnik_question(6, {"shown": "off"}, None)              # baza is q7 alone: 0.6·5 + 1.6
    assert upitnik.score({**given, "q6": 10, "q7": 5}, asked()) == 4.6
    new = db.add_upitnik_question(None).id
    db.set_upitnik_question(new, {"scoring": "navike"}, None)       # navike (4·4 + 9)/5 = 5: 3.0 + 2.0
    both = {**given, "q6": 10, "q7": 5, f"q{new}": 9}
    assert upitnik.score(both, asked()) == 5.0
    for q in (8, 9, 10, 11, new):                                   # navike has no question: baza alone
        db.set_upitnik_question(q, {"scoring": ""}, None)
    r = upitnik.evaluate(both, asked())
    assert (r.score, r.level) == (5.0, "srednja")
    db.set_upitnik_question(7, {"scoring": ""}, None)               # nothing scores
    r = upitnik.evaluate({**both, "q7": 10}, asked())
    assert upitnik.score(both, asked()) is None
    assert (r.score, r.level, r.pain_high, r.needs_review) == (0.0, "pocetna", False, False)


def test_a_score_is_rounded_half_up_on_exact_fractions():
    """With a fourth baza scale a score can fall on a half: baza
    (4+4+4+3)/4 = 3.75, navike (5+5+4+4)/4 = 4.5, 0.6·3.75 + 0.4·4.5 = 2.25
    + 1.8 = 4.05, which is 4.1, srednja. Floats would have said 4.0,
    početna: the client's level hung on the float's noise."""
    new = db.add_upitnik_question(None).id
    db.set_upitnik_question(new, {"scoring": "baza"}, None)
    assert round(0.6 * (15 / 4) + 0.4 * (18 / 4), 1) == 4.0
    r = upitnik.evaluate(answers((4, 4, 4), (5, 5, 4, 4), **{f"q{new}": 3}), asked())
    assert (r.score, r.level) == (4.1, "srednja")


# ---------- read: the questions asked are the shown rows ----------

def test_read_asks_the_questions_there_are():
    """A hidden question is not asked: nothing is required of it and
    nothing stored, whatever is sent. A new question is: required, stored
    under its id. The pain role moved to q13: the pain rule reads q13, and
    where it hurts (q16) is still asked after q14 at 4 or more: its own
    condition, not the role's, asks it (27.10.2026)."""
    sent = form()
    db.set_upitnik_question(12, {"shown": "off"}, None)
    assert "q12" not in upitnik.read({k: v for k, v in sent.items() if k != "q12"}, asked())
    assert "q12" not in upitnik.read({**sent, "q12": "7"}, asked())
    new = db.add_upitnik_question(None).id
    with pytest.raises(ValueError) as missing:
        upitnik.read(sent, asked())
    assert str(missing.value) == f"q{new}"
    assert upitnik.read({**sent, f"q{new}": "8"}, asked())[f"q{new}"] == 8
    db.set_upitnik_question(13, {"role": "pain"}, None)
    assert question(14).role == "" and question(13).role == "pain"
    sent = {**sent, f"q{new}": "8", "q13": "6", "q14": "9"}
    with pytest.raises(ValueError) as missing:
        upitnik.read(sent, asked())
    assert str(missing.value) == "q16"
    got = upitnik.read({**sent, "q16": "koljeno", "q13b": "leđa"}, asked())
    assert (got["q13"], got["q14"], got["q16"]) == (6, 9, "koljeno") and "q13b" not in got
    r = upitnik.evaluate(got, asked())
    assert (r.pain_level, r.pain_high) == (6, False)


def test_a_multi_takes_one_option_or_more_and_never_scores():
    """A multi (Više odgovora): one option or more, each the text of one of
    its options as the row holds them now, stored as a list in the
    options' order, each once. None, or a text it does not have, is
    refused. It never scores, and never takes a role."""
    new = db.add_upitnik_question(None).id
    db.set_upitnik_question(new, {"kind": "multi"}, None)
    db.set_upitnik_question_options(new, ["bez opreme", "bučice", "girja", "TRX"], None)
    key, sent = f"q{new}", form()
    assert upitnik.read({**sent, key: ["girja", "bučice"]}, asked())[key] == ["bučice", "girja"]
    assert upitnik.read({**sent, key: ["TRX", "TRX"]}, asked())[key] == ["TRX"]
    assert upitnik.read({**sent, key: "girja"}, asked())[key] == ["girja"]            # one tick
    for bad in ([], ["girja", "kettlebell"], ["2"], ""):
        with pytest.raises(ValueError):
            upitnik.read({**sent, key: bad}, asked())
    with pytest.raises(ValueError):
        upitnik.read(sent, asked())
    assert upitnik.score({**answers(), key: ["girja"]}, asked()) == upitnik.score(answers(), asked())
    t = client_for_trainer()
    assert t.post(f"/upitnik/pitanje/{new}", data={"scoring": "baza"}).json()["error"] == "Boduje se samo skala (1–10)."
    assert t.post(f"/upitnik/pitanje/{new}", data={"role": "pain"}).json()["error"] == "Uloga Bolovi ide samo uz skalu (1–10)."


# ---------- conditions (27.10.2026): a question asked only after an answer ----------

def chain() -> tuple[int, int, int]:
    """The gym owner's example, after the seventeen (part 3): "Jeste li
    imali porod?" (yes / no), "Je li to bilo u zadnjih godinu dana?" (yes /
    no, asked at its Da) and "Kako je završio porod?" (a choice, asked at
    the second one's Da): q18, q19, q20, places 18, 19, 20."""
    ids = []
    for text, kind in (("Jeste li imali porod?", "yesno"), ("Je li to bilo u zadnjih godinu dana?", "yesno"),
                       ("Kako je završio porod?", "choice")):
        qid = db.add_upitnik_question(None).id
        db.set_upitnik_question(qid, {"kind": kind, "part": "3"}, None)
        db.set_upitnik_question_field(qid, "text", text, None)
        ids.append(qid)
    db.set_upitnik_question_options(ids[2], ["Carski rez", "Prirodni porod"], None)
    db.set_upitnik_question(ids[1], {"parent_id": str(ids[0]), "condition": "yes"}, None)
    db.set_upitnik_question(ids[2], {"parent_id": str(ids[1]), "condition": "yes"}, None)
    return ids[0], ids[1], ids[2]


def test_a_chain_asks_each_question_only_after_the_answer_before_it():
    """yes → yes → choice: the second is asked at the first's Da, the third
    at the second's Da, each one level deeper. Da / Da / an option: all
    three asked, each required in its turn. Ne: neither child, whatever is
    sent for them; Da then Ne: the second, not the third. asked_of agrees,
    and no condition moves the score."""
    porod, godina, rez = chain()
    P, G, R = (f"q{i}" for i in (porod, godina, rez))
    steps = {q.id: q for q in asked()}
    assert [(steps[k].follows, steps[k].parent_kind, steps[k].condition, steps[k].depth) for k in (P, G, R)] == [
        (None, "", "", 0), (P, "yesno", "yes", 1), (G, "yesno", "yes", 2)]
    sent = form()
    for given, missing in (({}, P), ({P: "da"}, G), ({P: "da", G: "da"}, R)):
        with pytest.raises(ValueError) as refused:
            upitnik.read({**sent, **given}, asked())
        assert str(refused.value) == missing
    got = upitnik.read({**sent, P: "da", G: "da", R: "Carski rez"}, asked())
    assert (got[P], got[G], got[R]) == (True, True, "Carski rez")
    with pytest.raises(ValueError):
        upitnik.read({**sent, P: "da", G: "da", R: "Nešto treće"}, asked())
    got = upitnik.read({**sent, P: "ne", G: "da", R: "Carski rez"}, asked())
    assert got[P] is False and G not in got and R not in got
    got = upitnik.read({**sent, P: "da", G: "ne", R: "Carski rez"}, asked())
    assert (got[P], got[G]) == (True, False) and R not in got
    full = {**answers(), P: True, G: True, R: "Carski rez"}
    assert [q.id for q in upitnik.asked_of(asked(), full)][-3:] == [P, G, R]
    assert [q.id for q in upitnik.asked_of(asked(), {**full, P: False})][-1] == P
    assert [q.id for q in upitnik.asked_of(asked(), {**full, G: False})][-2:] == [P, G]
    assert upitnik.score(full, asked()) == upitnik.score(answers(), asked()) == 5.0


def test_a_scale_or_an_option_asks_a_question():
    """A scale's condition (">=N"): asked at N or more. A multi's (an
    option): asked when it is among the ticks. A choice's: when it is the
    answer. A conditional scale that scores counts only when asked."""
    gear = db.add_upitnik_question(None).id
    db.set_upitnik_question(gear, {"kind": "multi"}, None)
    db.set_upitnik_question_options(gear, ["bez opreme", "girja", "bučice"], None)
    weight = db.add_upitnik_question(None).id                       # a scale, asked when a girja is ticked
    db.set_upitnik_question(weight, {"parent_id": str(gear), "condition": "girja", "scoring": "navike"}, None)
    note = db.add_upitnik_question(None).id                         # a text, asked at q13 6 or more
    db.set_upitnik_question(note, {"kind": "text", "parent_id": "13", "condition": ">=6"}, None)
    where = db.add_upitnik_question(None).id                        # a text, asked when q4 is "U teretani"
    db.set_upitnik_question(where, {"kind": "text", "parent_id": "4", "condition": "U teretani"}, None)
    G, W, N, H = (f"q{i}" for i in (gear, weight, note, where))
    sent = {**form(), G: ["bez opreme"], W: "10", N: "x", H: "y"}   # q13 at 5, q4 its first option
    got = upitnik.read(sent, asked())
    assert got[G] == ["bez opreme"] and not {W, N, H} & got.keys()
    assert upitnik.score(got, asked()) == upitnik.score(answers(), asked()) == 5.0
    got = upitnik.read({**sent, G: ["girja", "bučice"], "q13": "6", "q4": "U teretani"}, asked())
    assert (got[G], got[W], got[N], got[H]) == (["girja", "bučice"], 10, "x", "y")
    assert upitnik.score(got, asked()) == 5.4                          # navike (4 × 5 + 10) / 5 = 6: 3.0 + 2.4
    with pytest.raises(ValueError) as missing:
        upitnik.read({**sent, "q13": "10", N: ""}, asked())                 # a blank, as copy.clean leaves it
    assert str(missing.value) == N
    assert upitnik.read({**sent, "q13": "10"}, asked())[N] == "x"


def test_a_condition_that_cannot_work_asks_the_question_always():
    """A conditional question whose question comes after it in the order
    (no route puts it there: a database can), was deleted, or can no longer
    give that answer (its kind changed, the option removed) is asked always,
    and the editor's line says so in amber, and why. Back as it was, it is
    conditional again; Uvijek clears it. (A hidden question is another
    rule: it mutes the questions under it, the next test.)"""
    porod, godina, rez = chain()
    t = client_for_trainer()
    G, R = f"q{godina}", f"q{rez}"

    def state(key: str = G) -> tuple:
        q = {s.id: s for s in upitnik.steps(db.upitnik_questions())}[key]
        return q.follows, q.void

    def line(key: str = G) -> tuple[str, str]:
        return ifs(t.get("/upitnik").text)[key]

    assert state() == (f"q{porod}", "") and line() == ("Pita se samo ako pitanje 18 = Da", "")
    with db.engine.begin() as conn:                                          # porod after godina
        conn.execute(sa_text("UPDATE upitnik_questions SET position = CASE WHEN id = :a THEN 19 ELSE 18 END "
                             "WHERE id IN (:a, :b)"), {"a": porod, "b": godina})
    assert state() == (None, "later") and line() == ("Pita se uvijek — uvjet ne vrijedi: pitanje 19 dolazi kasnije", "void")
    assert state(R) == (G, "")
    assert {q.id: q for q in asked()}[G].follows is None                    # asked of everyone
    assert upitnik.read({**form(), f"q{porod}": "ne", G: "ne"}, asked())[G] is False      # porod's Ne or not
    with db.engine.begin() as conn:
        conn.execute(sa_text("UPDATE upitnik_questions SET position = CASE WHEN id = :a THEN 18 ELSE 19 END "
                             "WHERE id IN (:a, :b)"), {"a": porod, "b": godina})
    t.post(f"/upitnik/pitanje/{porod}", data={"kind": "scale"})             # allowed: its question's line says why
    assert state() == (None, "answer") and line() == ("Pita se uvijek — uvjet ne vrijedi: pitanje 18 nema odgovor „Da”", "void")
    t.post(f"/upitnik/pitanje/{porod}", data={"kind": "yesno"})
    assert state() == (f"q{porod}", "")
    extra = db.add_upitnik_question(None).id                                 # asked after rez's "Carski rez"
    db.set_upitnik_question(extra, {"kind": "text", "parent_id": str(rez), "condition": "Carski rez"}, None)
    assert state(f"q{extra}") == (R, "")
    t.post(f"/copy/upitnik.{rez}.options", data={"text": "Ne znam", "index": "2"})        # a third, then the first goes
    assert t.post(f"/copy/upitnik.{rez}.options", data={"text": "", "index": "0"}).json()["items"] == [
        "Prirodni porod", "Ne znam"]
    assert question(extra).condition == "Carski rez" and state(f"q{extra}") == (None, "answer")
    assert line(f"q{extra}") == ("Pita se uvijek — uvjet ne vrijedi: pitanje 20 nema odgovor „Carski rez”", "void")
    t.post(f"/upitnik/pitanje/{porod}/obrisi")
    assert (question(godina).parent_id, question(godina).condition) == (None, "yes")      # the key nulled, the answer kept
    assert state() == (None, "gone") and line() == ("Pita se uvijek — uvjet ne vrijedi: pitanje je obrisano", "void")
    assert line(R) == ("Pita se samo ako pitanje 18 = Da", "")               # the chain under it holds
    assert t.post(f"/upitnik/pitanje/{godina}", data={"parent_id": "", "condition": ""}).json()["ok"]
    assert G not in ifs(t.get("/upitnik").text) and state() == (None, "")


def test_a_hidden_question_hides_the_questions_asked_after_it():
    """Fable's review (27.10.2026): hiding a question hides every question
    asked after it, down the chain. porod hidden: zadnjih godinu
    dana and carski rez (and a scored scale asked after porod) are muted,
    asked of nobody: no step on a client's page, an answer posted for them
    dropped, the score as if they were not there (the summary does not
    count the scale). Their own switches still say Prikazano; on the
    editor's page they are dimmed (.is-muted) and still hang under porod,
    their lines in amber naming the hidden question. Shown again, they are
    asked again. A question deleted mutes nothing: it asks those under it
    always, and its "Obriši pitanje" says so first (data-warn), as does
    every question shown ones are asked after."""
    porod, godina, rez = chain()
    scale = db.add_upitnik_question(None).id
    db.set_upitnik_question(scale, {"scoring": "baza", "parent_id": str(porod), "condition": "yes"}, None)
    uid = make_user("ivan@test.local")
    t, c = client_for_trainer(), client_for("ivan@test.local")
    P, G, R, S = (f"q{i}" for i in (porod, godina, rez, scale))
    sent = {**form(), P: "da", G: "da", R: "Carski rez", S: "10"}
    assert upitnik.score(upitnik.read(sent, asked()), asked()) == 5.8          # baza (5 · 3 + 10) / 4: 3.75 + 2.0
    assert t.post(f"/upitnik/pitanje/{porod}", data={"shown": "off"}).json()["on"] is False
    every = {q.id: q for q in upitnik.steps(db.upitnik_questions())}
    assert [(every[k].shown, every[k].muted, every[k].muted_by, every[k].follows, every[k].depth) for k in (G, R, S)] == [
        (True, True, 18, P, 1), (True, True, 18, G, 2), (True, True, 18, P, 1)]
    assert not upitnik.is_asked(every[G], {P: True})
    assert not {P, G, R, S} & {q.id for q in upitnik.asked_of(list(every.values()), {P: True, G: True})}
    page = c.get("/upitnik").text
    for k in (P, G, R, S):
        assert f'id="step-{k}"' not in page and f'name="{k}"' not in page, k
    r = c.post("/upitnik", data=sent, follow_redirects=False)
    stored = json.loads(db.get_onboarding(uid).answers)
    assert "ok=" in r.headers["location"] and not {P, G, R, S} & stored.keys()
    assert db.get_onboarding(uid).score == 5.0                                  # the muted scale scores nothing
    page = t.get("/upitnik").text
    assert summary(page).startswith("Bodovanje: trening baza = 3 pitanja,")
    assert [f'<section class="q-step is-off" id="step-{P}"' in page] + [
        f'<section class="q-step is-muted" id="step-{k}"' in page for k in (G, R, S)] == [True] * 4
    step = page.split(f'id="step-{G}"')[1].split("</section>")[0]
    assert 'aria-pressed="true">Prikazano</button>' in step and 'data-depth="1"' in page.split(f'id="step-{G}"')[1].split(">")[0]
    assert ifs(page)[G] == ("Pita se samo ako pitanje 18 = Da — pitanje 18 je skriveno, pa ni ovo nitko ne dobiva", "muted")
    assert ifs(page)[R] == ("Pita se samo ako pitanje 19 = Da — pitanje 18 je skriveno, pa ni ovo nitko ne dobiva", "muted")
    t.post(f"/upitnik/pitanje/{porod}", data={"shown": "on"})
    page = c.get("/upitnik").text
    assert all(f'id="step-{k}"' in page for k in (P, G, R, S))
    c.post("/upitnik", data=sent, follow_redirects=False)
    assert json.loads(db.get_onboarding(uid).answers)[R] == "Carski rez" and db.get_onboarding(uid).score == 5.8
    # deleting: a question shown ones hang under warns at "Obriši pitanje";
    # one with none (or only hidden ones) does not
    db.set_upitnik_question(rez, {"shown": "off"}, None)
    page = t.get("/upitnik").text
    warn = 'data-warn="Pitanja koja ovise o njemu ostaju i pitat će se svakoga."'
    def x(qid: int) -> str:
        return page.split(f'form="q-x-{qid}"')[1].split(">")[0]
    assert [warn in x(q) for q in (porod, godina, rez, 14, 15, 16, 1)] == [True, False, False, True, True, False, False]
    t.post(f"/upitnik/pitanje/{porod}/obrisi")
    every = {q.id: q for q in upitnik.steps(db.upitnik_questions())}
    assert (every[G].muted, every[G].void, every[S].void) == (False, "gone", "gone") and G in {q.id for q in asked()}


def test_a_reworded_option_carries_into_the_conditions_that_named_it():
    """The editor re-words an option a question is asked after (27.10.2026):
    its condition follows, in the same save, and a client is asked it at
    the new words. Re-worded past 80 characters (the column), the condition
    stays as it was and its line goes amber. An option added or removed,
    or one on a question asked after another option, carries nothing."""
    make_user("ivan@test.local")
    t = client_for_trainer()
    gym = db.add_upitnik_question(None).id
    db.set_upitnik_question(gym, {"kind": "text", "parent_id": "4", "condition": "U teretani"}, None)
    other = db.add_upitnik_question(None).id                                  # asked after another option
    db.set_upitnik_question(other, {"kind": "text", "parent_id": "4", "condition": "Kod kuće bez opreme"}, None)
    r = t.post("/copy/upitnik.4.options", data={"text": "U dvorani QMT", "index": "2"})
    assert r.json()["items"] == ["Kod kuće bez opreme", "Kod kuće s osnovnom opremom", "U dvorani QMT"]
    assert (question(gym).condition, question(other).condition) == ("U dvorani QMT", "Kod kuće bez opreme")
    H = f"q{gym}"
    assert upitnik.read({**form(), "q4": "U dvorani QMT", H: "QMT"}, asked())[H] == "QMT"
    assert H not in upitnik.read({**form(), H: "QMT", f"q{other}": "doma"}, asked())   # q4 its first option
    assert f'data-parent="q4" data-has="U dvorani QMT"' in client_for("ivan@test.local").get("/upitnik").text
    t.post("/copy/upitnik.4.options", data={"text": "Na otvorenom", "index": "3"})            # added: nothing moves
    t.post("/copy/upitnik.4.options", data={"text": "", "index": "3"})                        # removed: nothing moves
    assert (question(gym).condition, question(other).condition) == ("U dvorani QMT", "Kod kuće bez opreme")
    long = "U dvorani QMT, Virovska ulica 1, Zagreb, ponedjeljkom, srijedom, četvrtkom i petkom"   # 83 characters
    assert len(long) > upitnik.CONDITION_MAX
    assert t.post("/copy/upitnik.4.options", data={"text": long, "index": "2"}).json()["items"][2] == long
    assert question(gym).condition == "U dvorani QMT"
    assert ifs(t.get("/upitnik").text)[H] == ("Pita se uvijek — uvjet ne vrijedi: pitanje 4 nema odgovor „U dvorani QMT”", "void")


# ---------- POST /upitnik ----------

def test_a_whole_submission_stores_the_answers_the_flags_and_the_consent():
    """A choice is stored as its option's text, a scale as an int, yes / no
    as a bool, a free text as written (cleaned as copy is: a browser's CRLF
    a line break again). Version 2, goal cijelo (the level alone routes),
    the score and the flags, and when the consent was given; then the
    programmes, the flash naming the level."""
    uid = make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    before = datetime.now(config.TZ)
    r = c.post("/upitnik", data=form(
        q1="Povećanje snage i mišićne mase", q2="3", q3="45-60", q4="U teretani",
        q5="7", q6="6", q7="5", q8="6", q9="8", q10="8", q11="6", q12="4", q13="8",
        q14="5", q16="  Leđa,\r\n   donji   dio ", q15="da", q17="Operacija koljena 2023."), follow_redirects=False)
    assert r.status_code == 303
    assert unquote(r.headers["location"]) == "/treninzi?ok=Upitnik je spremljen — Srednja razina."
    row = db.get_onboarding(uid)
    assert json.loads(row.answers) == {
        "q1": "Povećanje snage i mišićne mase", "q2": "3", "q3": "45-60", "q4": "U teretani",
        "q5": 7, "q6": 6, "q7": 5, "q8": 6, "q9": 8, "q10": 8, "q11": 6, "q12": 4, "q13": 8,
        "q14": 5, "q16": "Leđa,\ndonji dio", "q15": True, "q17": "Operacija koljena 2023."}
    assert list(json.loads(row.answers))[13:] == ["q14", "q16", "q15", "q17"]      # in the questionnaire's order
    # baza (7+6+5)/3 = 6, navike (6+8+8+6)/4 = 7; 3.6 + 2.8 = 6.4
    assert (row.version, row.score, row.level, row.goal) == (2, 6.4, "srednja", "cijelo")
    assert (row.pain_level, row.pain_high, row.needs_review) == (5, False, True)
    assert before <= row.consented_at <= datetime.now(config.TZ)
    assert "Upitnik je spremljen — Srednja razina." in c.get(r.headers["location"]).text


def test_a_conditional_question_that_was_not_asked_is_not_stored():
    """Without JS every step is on the page, the conditional ones too (and
    none of their inputs required): what was typed into one whose answer
    was not given is left out."""
    uid = make_user("ivan@test.local")
    r = client_for("ivan@test.local").post("/upitnik", data=form(q14="3", q16="ništa", q15="ne", q17="ništa"),
                                           follow_redirects=False)
    assert "ok=" in r.headers["location"]
    stored = json.loads(db.get_onboarding(uid).answers)
    assert "q16" not in stored and "q17" not in stored and (stored["q14"], stored["q15"]) == (3, False)


def test_a_refill_replaces_the_row_an_old_one_included_and_pain_starts_at_pocetna():
    """One row per client: refilling overwrites it, a version-1 row too
    (its goal gornji gives way to cijelo). Pain at 7 or more: početna, the
    flash adds the sentence that sends the client to the trainer first, as
    the gym owner words it (upitnik.pain_note); emptied, it says nothing."""
    uid = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    db.save_onboarding(uid, json.dumps({"staz": 2}), 9, "srednja", "gornji", version=1, pain_level=None,
                       pain_high=False, needs_review=False, consented_at=None)
    c = client_for("ivan@test.local")
    top = {q: "10" for q in BASE + HABITS}
    r = c.post("/upitnik", data=form(**top, q14="8", q16="vrat"), follow_redirects=False)
    assert unquote(r.headers["location"]) == (
        "/treninzi?ok=Upitnik je spremljen — Početna razina. Zbog čestih bolova krećeš od početne razine — "
        "javi se treneru prije prvog treninga.")
    row = db.get_onboarding(uid)
    assert (row.version, row.score, row.level, row.goal, row.pain_level, row.pain_high) == (2, 10.0, "pocetna", "cijelo", 8, True)
    with db.engine.connect() as conn:
        assert conn.execute(sa_text("SELECT count(*) FROM onboarding_responses")).scalar() == 1
    t = client_for("trener@test.local")
    t.post("/copy/upitnik.pain_note", data={"text": "Javi se treneru."})
    r = c.post("/upitnik", data=form(**top, q14="7", q16="vrat"), follow_redirects=False)
    assert unquote(r.headers["location"]).endswith("Početna razina. Javi se treneru.")
    t.post("/copy/upitnik.pain_note", data={"text": ""})
    r = c.post("/upitnik", data=form(**top, q14="7", q16="vrat"), follow_redirects=False)
    assert unquote(r.headers["location"]).endswith("Upitnik je spremljen — Početna razina.")
    r = c.post("/upitnik", data=form(**top, q14="6", q16="vrat"), follow_redirects=False)
    assert unquote(r.headers["location"]).endswith("— Napredna razina.") and not db.get_onboarding(uid).pain_high


ERROR = "/upitnik?error=Odgovori+na+sva+pitanja."


@pytest.mark.parametrize("what, sent, where", [
    ("a scale missing", {"q9": None}, ERROR),
    ("a scale out of range", {"q9": "11"}, ERROR),
    ("a scale of zero", {"q12": "0"}, ERROR),
    ("a scale in between", {"q6": "7.5"}, ERROR),
    ("a choice missing", {"q3": None}, ERROR),
    ("an option the question does not have", {"q4": "Na plaži"}, ERROR),
    ("an option's index, not its text", {"q1": "0"}, ERROR),
    ("yes / no neither", {"q15": "možda"}, ERROR),
    ("q16 missing when q14 is 4", {"q14": "4"}, ERROR),
    ("q16 blank when q14 is 9", {"q14": "9", "q16": "  \r\n "}, ERROR),
    ("q17 missing when q15 is yes", {"q15": "da"}, ERROR),
    ("a free text past the cap", {"q15": "da", "q17": "x" * (upitnik.TEXT_MAX + 1)}, ERROR),
    ("the consent missing", {"consent": None},
     "/upitnik?error=Potvrdi%20pristanak%20na%20obradu%20podataka%20o%20zdravlju."),
])
def test_an_incomplete_or_invalid_submission_stores_nothing(what, sent, where):
    uid = make_user("ivan@test.local")
    r = client_for("ivan@test.local").post("/upitnik", data=form(**sent), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == where, what
    assert db.get_onboarding(uid) is None, what


def test_an_answer_is_an_option_as_its_question_holds_it_now():
    """The gym owner re-words an option: a form still holding the old text
    is refused (nothing stored), the new text is what is stored. An option
    he writes in two lines comes back from a browser with a CRLF, and is
    the same option."""
    uid = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    t, c = client_for("trener@test.local"), client_for("ivan@test.local")
    assert t.post("/copy/upitnik.4.options", data={"text": "U dvorani QMT", "index": "2"}).json()["ok"]
    r = c.post("/upitnik", data=form(q4="U teretani"), follow_redirects=False)
    assert r.headers["location"] == ERROR and db.get_onboarding(uid) is None
    c.post("/upitnik", data=form(q4="U dvorani QMT"), follow_redirects=False)
    assert json.loads(db.get_onboarding(uid).answers)["q4"] == "U dvorani QMT"
    t.post("/copy/upitnik.1.options", data={"text": "Gubitak težine\ni oblikovanje", "index": "0"})
    r = c.post("/upitnik", data=form(q1="Gubitak težine\r\ni oblikovanje"), follow_redirects=False)
    assert "ok=" in r.headers["location"]
    assert json.loads(db.get_onboarding(uid).answers)["q1"] == "Gubitak težine\ni oblikovanje"


def test_a_multi_is_sent_as_several_ticks_stored_as_a_list_and_joined_on_the_karton():
    """A multi on the client's page is a checkbox per option in the
    lettered rows, its step going on with Dalje; the ticks arrive as
    several values of one field and are stored as a list. None ticked is
    refused. On the karton the answer is its texts joined with " · ", in
    the trainer's list and, in part 1, as a chip."""
    uid = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    new = db.add_upitnik_question(None).id
    db.set_upitnik_question(new, {"kind": "multi", "part": "1"}, None)
    db.set_upitnik_question_options(new, ["bez opreme", "bučice", "girja"], None)
    db.set_upitnik_question_field(new, "text", "Koju opremu imaš?", None)
    c = client_for("ivan@test.local")
    step = c.get("/upitnik").text.split(f'id="step-q{new}"')[1].split("</section>")[0]
    assert 'data-kind="multi"' in step and '<div class="opts" role="group"' in step
    assert step.count(f'<input type="checkbox" name="q{new}" value="') == 3
    assert '<label class="opt"><input type="checkbox" name="q{0}" value="bučice"><span class="t">bučice</span></label>'.format(new) in step
    assert 'class="btn q-next"' in step and "required" not in step
    r = c.post("/upitnik", data=form(), follow_redirects=False)
    assert r.headers["location"] == ERROR and db.get_onboarding(uid) is None
    r = c.post("/upitnik", data={**form(), f"q{new}": ["girja", "bez opreme"]}, follow_redirects=False)
    assert "ok=" in r.headers["location"]
    assert json.loads(db.get_onboarding(uid).answers)[f"q{new}"] == ["bez opreme", "girja"]
    block = unescape(upitnik_block(client_for("trener@test.local").get(f"/karton/{uid}").text))
    assert ">Koju opremu imaš? — <strong>bez opreme · girja</strong></li>" in block
    assert '<span class="u-fact">bez opreme · girja</span>' in block


def test_who_gets_the_page_and_who_may_send_it():
    """A client with an online plan fills it; one without is sent to his
    karton, both ways, as before. The trainer and the owner get the page
    with no plan of their own (it is where it is edited) and never send
    it: their submission is refused and stores nothing, the owner's too
    when he holds an online plan (his page is the editor's, a choice his
    options list)."""
    owner = make_user("trener@test.local")                      # the owner (OWNER_EMAIL), not a trainer, an online plan
    studio = make_user("studio@test.local", is_trainer=True, plans=())
    make_user("sara@test.local", plans=("grupni",))
    make_user("ivan@test.local")
    gate = "/karton?error=Upitnik+je+dio+online+članarine+—+javi+se+treneru."
    sara = client_for("sara@test.local")
    for r in (sara.get("/upitnik", follow_redirects=False), sara.post("/upitnik", data=form(), follow_redirects=False)):
        assert r.status_code == 303 and unquote(r.headers["location"]) == gate
    anon = TestClient(app).get("/upitnik", follow_redirects=False)
    assert anon.status_code == 303 and anon.headers["location"].startswith("/login")

    for email, uid in (("studio@test.local", studio), ("trener@test.local", owner)):
        c = client_for(email)
        page = c.get("/upitnik")
        assert page.status_code == 200 and 'id="copyToggle"' in page.text, email
        r = c.post("/upitnik", data=form(), follow_redirects=False)
        assert unquote(r.headers["location"]) == "/upitnik?error=Upitnik+ispunjavaju+članovi+—+ovdje+se+uređuju+samo+tekstovi."
        assert db.get_onboarding(uid) is None, email

    page = client_for("ivan@test.local").get("/upitnik").text      # a client: the form, no editor
    for mark in ("data-copy", "data-list", "copyToggle", 'class="ed-x"', 'class="q-ed', 'class="ed-q-x"',
                 'action="/upitnik/pitanje', 'form="q-', "data-url", 'class="q-sum"', 'class="q-add"', "data-flag"):
        assert mark not in page, mark
    for q, options in CHOICES.items():
        for option in options:
            assert f'<input type="radio" name="{q}" value="{option}" required>' in page
    assert page.count('type="radio" name="q5"') == 10 and 'name="q16"' in page and 'name="consent"' in page
    assert '<section class="q-step" id="step-q16" data-q="q16" data-kind="text" data-parent="q14" data-from="4">' in page
    assert '<section class="q-step" id="step-q17" data-q="q17" data-kind="text" data-parent="q15" data-is="da">' in page
    assert 'class="avatar' not in page and 'id="mainNav"' not in page     # the brand alone at the top
    assert 'class="topbar compact"' in page


def test_the_error_shows_under_the_title_and_the_form_starts_empty():
    """A refused submission comes back with why, under the questionnaire's
    title (not over it, base.html's place), and the form starts on the
    first question again with nothing chosen: a refill starts fresh."""
    make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    c.post("/upitnik", data=form(), follow_redirects=False)        # a filled one exists
    page = c.get("/upitnik?error=Odgovori+na+sva+pitanja.").text
    title, alert = page.index('class="q-title"'), page.index('<div class="alert" role="alert">')
    assert title < alert < page.index('class="q-intro"') and page.count('class="alert"') == 1
    assert "checked" not in page.split('id="quiz"')[1].split("</form>")[0]


# ---------- the editor's routes: add, delete, move, settings ----------

def order() -> list[int]:
    return [q.id for q in db.upitnik_questions()]


def test_the_editor_adds_questions_up_to_forty_and_deletes_them():
    """"+ Dodaj pitanje": a scale in part 2 that scores nothing, shown, its
    placeholders to retype, after the last; back on /upitnik at it. At 40
    it is refused with why. "Obriši pitanje": the question goes, back at
    the one before it (the next one, for the first); an id is never given
    again, so an answer kept under a deleted question's id stays that
    question's. The owner, who does not train, may as well."""
    make_user("trener@test.local", plans=())                    # the owner, not a trainer
    t = client_for("trener@test.local")
    r = t.post("/upitnik/pitanje/nova", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/upitnik#step-q18"
    q = question(18)
    assert (q.position, q.part, q.kind, q.scoring, q.role, q.shown) == (18, 2, "scale", "", "", True)
    assert (q.text, q.option_items, q.low, q.high, q.parent_id, q.condition) == (
        "Novo pitanje", ["Prvi odgovor", "Drugi odgovor"], "…", "…", None, "")
    page = t.get("/upitnik").text
    assert 'id="step-q18"' in page and '<form id="q-add" class="ed-add-q" method="post" action="/upitnik/pitanje/nova" hidden></form>' in page
    for _ in range(db.MAX_UPITNIK_QUESTIONS - 18):
        t.post("/upitnik/pitanje/nova")
    assert len(order()) == db.MAX_UPITNIK_QUESTIONS
    r = t.post("/upitnik/pitanje/nova", follow_redirects=False)
    assert unquote(r.headers["location"]) == "/upitnik?error=Najviše+40+pitanja." and len(order()) == 40
    page = t.get("/upitnik").text
    assert '<div class="q-add">' not in page and 'id="q-add"' not in page and 'form="q-add"' not in page
    r = t.post("/upitnik/pitanje/18/obrisi", follow_redirects=False)
    assert r.headers["location"] == "/upitnik#step-q17" and question(18) is None
    r = t.post("/upitnik/pitanje/1/obrisi", follow_redirects=False)
    assert r.headers["location"] == "/upitnik#step-q2" and order()[0] == 2
    assert t.post("/upitnik/pitanje/1/obrisi", follow_redirects=False).headers["location"] == "/upitnik"   # gone already
    r = t.post("/upitnik/pitanje/nova", follow_redirects=False)
    assert r.headers["location"] == "/upitnik#step-q41"                 # 18 and 1 are never given again


def test_a_question_moves_one_place_up_or_down():
    """↑ / ↓ trade a question's place with the one before or after it, in
    the order of every question (a hidden one too); back on /upitnik at it.
    At either end, or with a direction that is neither, nothing moves."""
    make_user("trener@test.local", is_trainer=True)
    t = client_for("trener@test.local")
    r = t.post("/upitnik/pitanje/14/pomak", data={"smjer": "gore"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/upitnik#step-q14"
    assert order()[11:] == [12, 14, 13, 16, 15, 17]
    t.post("/upitnik/pitanje/14/pomak", data={"smjer": "dolje"})
    assert order() == ORDER
    db.set_upitnik_question(14, {"shown": "off"}, None)             # a hidden one is still in the order
    t.post("/upitnik/pitanje/15/pomak", data={"smjer": "gore"})
    assert order()[12:] == [13, 14, 15, 16, 17]
    for qid, way in ((1, "gore"), (17, "dolje"), (5, "lijevo"), (99, "gore")):
        t.post(f"/upitnik/pitanje/{qid}/pomak", data={"smjer": way})
    assert order()[12:] == [13, 14, 15, 16, 17] and order()[:2] == [1, 2]
    # the steps follow (q14 hidden: no step for a client, nor for q16,
    # asked after it, which it mutes; q16 still hangs under it)
    every = upitnik.steps(db.upitnik_questions())
    assert [(q.id, q.follows, q.muted) for q in every][-5:] == [
        ("q13", None, False), ("q14", None, False), ("q15", None, False), ("q16", "q14", True), ("q17", "q15", False)]
    assert [q.id for q in asked()][-3:] == ["q13", "q15", "q17"]


def test_a_questions_settings_keep_their_rules():
    """POST /upitnik/pitanje/{id}, a field at a time: part 1–4, kind,
    scoring (a scale's), role (pain a scale, injuries a yes / no, one of
    each: taking one moves it), shown. Refused with the sentence the
    editor's bar shows: a scoring on what is no scale, a role on the wrong
    kind, a change of kind while the question scores or holds a role its
    new kind cannot hold, anything unknown. The answer is the row as
    stored."""
    t = client_for_trainer()

    def post(qid, **fields):
        return t.post(f"/upitnik/pitanje/{qid}", data=fields)

    r = post(12, part="1")
    assert r.json() == {"ok": True, "id": 12, "part": 1, "kind": "scale", "scoring": "", "role": "", "shown": True, "on": True,
                        "parent_id": None, "condition": ""}
    for fields, error in (({"part": "5"}, "Nepoznat dio."), ({"part": "x"}, "Nepoznat dio."),
                          ({"kind": "slider"}, "Nepoznata vrsta pitanja."), ({"scoring": "snaga"}, "Nepoznato bodovanje."),
                          ({"role": "boss"}, "Nepoznata uloga."), ({"shown": "maybe"}, "Nepoznata vrijednost."),
                          ({"colour": "red"}, "Nepoznata postavka."), ({}, "Nepoznata postavka.")):
        r = post(12, **fields)
        assert (r.status_code, r.json()) == (400, {"ok": False, "error": error}), fields
    assert post(12, scoring="navike").json()["scoring"] == "navike"
    r = post(1, scoring="baza")
    assert (r.status_code, r.json()["error"]) == (400, "Boduje se samo skala (1–10).")
    r = post(12, kind="choice")
    assert r.json()["error"] == "Ovo se pitanje boduje, a boduje se samo skala — prvo odaberi „Ne boduje se”."
    post(12, scoring="")
    assert post(12, kind="choice").json()["kind"] == "choice"
    assert question(12).option_items == ["Prvi odgovor", "Drugi odgovor"]   # a choice has two to choose from
    assert (question(12).low, question(12).high) == ("nikad", "redovito")    # its texts are kept
    # the roles: on the kind each needs, one of each
    assert post(1, role="pain").json()["error"] == "Uloga Bolovi ide samo uz skalu (1–10)."
    assert post(13, role="injuries").json()["error"] == "Uloga Ozljede ide samo uz pitanje Da / Ne."
    assert post(13, role="pain").json()["role"] == "pain"
    assert (question(13).role, question(14).role) == ("pain", "")           # it moved
    r = post(13, kind="yesno")
    assert r.json()["error"] == "Ovo je pitanje o bolovima, a ta uloga ide samo uz skalu — prvo makni ulogu."
    r = post(15, kind="scale")
    assert r.json()["error"] == "Ovo je pitanje o ozljedama, a ta uloga ide samo uz Da / Ne — prvo makni ulogu."
    new = db.add_upitnik_question(None).id
    post(new, kind="yesno")
    assert post(new, role="injuries").json()["role"] == "injuries"
    assert (question(new).role, question(15).role) == ("injuries", "")
    assert sorted(q.role for q in db.upitnik_questions() if q.role) == ["injuries", "pain"]
    # the switch, its answer as a flag's
    assert post(12, shown="off").json()["on"] is False and question(12).shown is False
    assert post(12, shown="on").json()["on"] is True
    # several at once, checked together; a question that is not there
    assert post(12, kind="scale", scoring="baza").json()["scoring"] == "baza"
    assert post(99, part="2").status_code == 404


def test_pita_se_keeps_its_rules():
    """POST /upitnik/pitanje/{id} with parent_id and condition (27.10.2026,
    posted together): an earlier question and an answer it can give is
    stored, both empty asks the question always again. Refused with the
    sentence the editor's bar shows, nothing changed: half of the pair, a
    question that is not there, the question itself, one that hangs under
    it (a circle, whatever the order says), one after it, a free text, an
    answer of the wrong shape for its kind (yes / no, ">=N" with N 1–10,
    an option it has), an option longer than the column. With another
    setting in the same post, both are saved."""
    porod, godina, rez = chain()
    t = client_for_trainer()

    def post(qid, parent, condition, **more):
        return t.post(f"/upitnik/pitanje/{qid}", data={"parent_id": parent, "condition": condition, **more})

    r = post(rez, str(porod), "no")
    assert r.json() == {"ok": True, "id": rez, "part": 3, "kind": "choice", "scoring": "", "role": "", "shown": True,
                        "on": True, "parent_id": porod, "condition": "no"}
    assert (question(rez).parent_id, question(rez).condition) == (porod, "no")
    assert post(rez, "", "").json()["condition"] == "" and question(rez).parent_id is None
    assert post(rez, str(godina), "yes").json()["parent_id"] == godina
    assert post(16, "13", ">=10").json()["condition"] == ">=10"             # any N 1–10, any earlier scale
    long = "dugi odgovor " * 7                                             # 91 characters
    db.set_upitnik_question_options(rez, ["Carski rez", long.strip()], None)
    extra = db.add_upitnik_question(None).id
    cases = (((godina, "", "yes"), "Odaberi pitanje i odgovor."),
             ((godina, str(porod), ""), "Odaberi pitanje i odgovor."),
             ((godina, "999", "yes"), "Nepoznato pitanje."), ((godina, "x", "yes"), "Nepoznato pitanje."),
             ((godina, str(godina), "yes"), "Pitanje ne može ovisiti o samome sebi."),
             ((porod, str(rez), "Carski rez"), "Pitanje ne može ovisiti o svom potpitanju."),
             ((12, "14", ">=4"), "Pitanje može ovisiti samo o pitanju prije njega."),
             ((godina, "17", "x"), "Pitanje sa slobodnim tekstom nema odgovor za uvjet."),
             ((godina, str(porod), ">=4"), "Uz pitanje Da / Ne uvjet je Da ili Ne."),
             ((godina, str(porod), "da"), "Uz pitanje Da / Ne uvjet je Da ili Ne."),
             ((godina, "13", "yes"), "Uz skalu uvjet je broj od 1 do 10."),
             ((godina, "13", ">=11"), "Uz skalu uvjet je broj od 1 do 10."),
             ((godina, "13", ">=0"), "Uz skalu uvjet je broj od 1 do 10."),
             ((godina, "13", "4"), "Uz skalu uvjet je broj od 1 do 10."),
             ((godina, "4", "Na plaži"), "To pitanje nema taj odgovor."),
             ((extra, str(rez), long.strip()), "Uvjet može biti odgovor od najviše 80 znakova — skrati ga."))
    for (qid, parent, condition), sentence in cases:
        r = post(qid, parent, condition)
        assert (r.status_code, r.json()) == (400, {"ok": False, "error": sentence}), (qid, parent, condition)
    assert [(question(q).parent_id, question(q).condition) for q in (porod, godina, rez, 12, extra)] == [
        (None, ""), (porod, "yes"), (godina, "yes"), (None, ""), (None, "")]
    # a circle the order cannot see: a database where godina came before
    # porod, the question it is asked after (no route puts it there)
    with db.engine.begin() as conn:
        conn.execute(sa_text("UPDATE upitnik_questions SET position = CASE WHEN id = :a THEN 19 ELSE 18 END "
                             "WHERE id IN (:a, :b)"), {"a": porod, "b": godina})
    r = post(porod, str(godina), "yes")
    assert (r.status_code, r.json()["error"]) == (400, "Pitanje ne može ovisiti o svom potpitanju.")
    assert post(porod, "", "").json()["ok"]                                  # Uvijek: nothing to refuse
    r = post(extra, str(porod), "yes", part="1")
    assert (r.json()["part"], r.json()["parent_id"], r.json()["condition"]) == (1, porod, "yes")
    assert post(99, "1", "Gubitak težine").status_code == 404


def test_a_question_never_moves_above_the_one_it_is_asked_after():
    """↑ on a question right under the one it is asked after, or ↓ on that
    one, is refused ("Potpitanje ne može ići ispred svog pitanja.", at the
    top of the page) and nothing moves; any other move is as before. The
    editor's page marks those arrows (data-refuse: his press says it in
    the bar and sends nothing)."""
    t = client_for_trainer()
    page = t.get("/upitnik").text

    def refused(qid: int) -> list[bool]:
        step = page.split(f'id="step-q{qid}"')[1].split("</section>")[0]
        return ["data-refuse=" in arrow.split(">")[0] for arrow in step.split('class="ed-mv"')[1:]]

    assert [refused(q) for q in (14, 16, 15, 17, 13)] == [[False, True], [True, False], [False, True], [True, False],
                                                         [False, False]]
    assert page.count('data-refuse="Potpitanje ne može ići ispred svog pitanja."') == 4
    for qid, way in ((16, "gore"), (14, "dolje"), (17, "gore"), (15, "dolje")):
        r = t.post(f"/upitnik/pitanje/{qid}/pomak", data={"smjer": way}, follow_redirects=False)
        assert unquote(r.headers["location"]) == "/upitnik?error=Potpitanje ne može ići ispred svog pitanja.", (qid, way)
    assert order() == ORDER
    t.post("/upitnik/pitanje/16/pomak", data={"smjer": "dolje"})              # past q15: q14 is still above it
    assert order()[13:] == [14, 15, 16, 17]
    page = t.get("/upitnik").text
    assert 'data-refuse="' not in page


def test_the_editors_page_shows_when_each_question_is_asked():
    """Pita se on every question: Uvijek, or Samo ako … with the question
    (the earlier ones a condition can name, numbered by their places, their
    first 40 characters) and the answer (a yes / no's Da / Ne, a scale's
    1–10 with "ili više", a choice's options) chosen; on the first
    question, with nothing before it, Samo ako … cannot be chosen. A
    conditional step is indented by its depth (data-depth) and carries its
    condition for the script (data-parent, data-is / data-from / data-has),
    on the client's page too, which gets none of the editor's markup and
    none of the chain's inputs required."""
    porod, godina, rez = chain()
    extra = db.add_upitnik_question(None).id
    db.set_upitnik_question(extra, {"kind": "text", "parent_id": str(rez), "condition": "Carski rez"}, None)
    make_user("ivan@test.local")
    page = client_for_trainer().get("/upitnik").text

    def step(qid: int) -> str:
        return page.split(f'id="step-q{qid}"')[1].split("</section>")[0]

    assert '<span class="ed-if" data-url="/upitnik/pitanje/1">' in step(1)
    assert '<option value="" selected>Uvijek</option>' in step(1) and '<option value="if" disabled>Samo ako …</option>' in step(1)
    g = step(godina)
    assert f'<span class="ed-if open" data-url="/upitnik/pitanje/{godina}" data-kind="yesno">' in g
    assert '<option value="if" selected>Samo ako …</option>' in g
    assert f'<option value="{porod}" selected>18 · Jeste li imali porod?</option>' in g
    assert '<option value="yes" selected>Da</option><option value="no">Ne</option>' in g
    listed = re.findall(r'<option value="(\d+)"', g.split('class="if-q"')[1].split("</select>")[0])
    assert listed == [str(n) for n in range(1, 16)] + [str(porod)]           # no free text (q16, q17), none after it
    assert '<option value="5">5 · Koliko redovito si trenirao/la u zadnjih…</option>' in g     # 40 characters
    s = step(16)
    assert '<span class="ed-if open" data-url="/upitnik/pitanje/16" data-kind="scale">' in s
    assert '<option value="&gt;=4" selected>4</option>' in s and '<span class="if-tail">ili više</span>' in s
    e = step(extra)
    assert f'<span class="ed-if open" data-url="/upitnik/pitanje/{extra}" data-kind="choice">' in e
    assert '<option value="Carski rez" selected>Carski rez</option><option value="Prirodni porod">Prirodni porod</option>' in e
    for qid, depth, cond in ((godina, 1, f'data-parent="q{porod}" data-is="da"'), (rez, 2, f'data-parent="q{godina}" data-is="da"'),
                             (extra, 3, f'data-parent="q{rez}" data-has="Carski rez"'), (16, 1, 'data-parent="q14" data-from="4"')):
        assert re.search(rf'id="step-q{qid}" data-q="q{qid}" data-kind="\w+" {cond} data-flag data-depth="{depth}">', page), qid
    assert f'id="step-q{porod}" data-q="q{porod}" data-kind="yesno" data-flag>' in page
    client = client_for("ivan@test.local").get("/upitnik").text
    assert f'<section class="q-step" id="step-q{rez}" data-q="q{rez}" data-kind="choice" data-parent="q{godina}" data-is="da">' in client
    for mark in ('class="ed-if', 'class="if-ask"', ' data-depth="', ' data-refuse="', 'class="q-ed-if'):
        assert mark not in client, mark
    assert f'<input type="radio" name="q{porod}" value="da" required>' in client
    assert f'<input type="radio" name="q{godina}" value="da">' in client          # asked only after porod's Da
    assert f'<input type="radio" name="q{rez}" value="Carski rez">' in client


def test_a_kind_switch_keeps_the_row_its_options_and_its_answers():
    """A choice becomes a multi (Više odgovora, the editor's select says)
    and back with its options as they were; a scale, which has none,
    becomes a multi with the two placeholders to retype. A response given
    before keeps its answers, printed as they were given."""
    uid = make_user("ivan@test.local")
    t = client_for_trainer()
    client_for("ivan@test.local").post("/upitnik", data=form(), follow_redirects=False)
    assert '<option value="multi">Više odgovora</option>' in t.get("/upitnik").text
    assert t.post("/upitnik/pitanje/4", data={"kind": "multi"}).json()["kind"] == "multi"
    assert question(4).option_items == list(CHOICES["q4"])
    assert t.post("/upitnik/pitanje/4", data={"kind": "choice"}).json()["kind"] == "choice"
    assert question(4).option_items == list(CHOICES["q4"])
    assert t.post("/upitnik/pitanje/12", data={"kind": "multi"}).json()["kind"] == "multi"
    assert question(12).option_items == ["Prvi odgovor", "Drugi odgovor"]
    t.post("/upitnik/pitanje/4", data={"kind": "multi"})
    block = unescape(upitnik_block(t.get(f"/karton/{uid}").text))
    assert f'>{TEXT["q4"]} — <strong>{CHOICES["q4"][0]}</strong></li>' in block      # a string, as given
    assert f'>{TEXT["q12"]} — <strong>5 / 10</strong></li>' in block                # a scale's, as given
    assert json.loads(db.get_onboarding(uid).answers)["q12"] == 5


def test_only_the_trainer_and_the_owner_touch_the_questions():
    """A client gets 403 from every route of the editor's, POST /copy/{key}
    on a question's words included; a guest is sent to log in. Nothing
    changes."""
    make_user("ivan@test.local")
    c, anon = client_for("ivan@test.local"), TestClient(app)
    calls = (("/upitnik/pitanje/nova", {}), ("/upitnik/pitanje/5", {"part": "3"}),
             ("/upitnik/pitanje/17", {"parent_id": "", "condition": ""}),
             ("/upitnik/pitanje/5/pomak", {"smjer": "gore"}), ("/upitnik/pitanje/5/obrisi", {}))
    for path, data in calls:
        assert c.post(path, data=data, follow_redirects=False).status_code == 403, path
        r = anon.post(path, data=data, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", path
    assert c.post("/copy/upitnik.5.text", data={"text": "x"}).status_code == 403
    assert anon.post("/copy/upitnik.5.text", data={"text": "x"}).status_code == 401
    assert order() == ORDER and (question(5).part, question(5).text) == (2, TEXT["q5"])
    assert (question(17).parent_id, question(17).condition) == (15, "yes")


# ---------- a question's words: virtual keys on POST /copy/{key} ----------

def test_a_questions_words_are_edited_through_virtual_keys():
    """upitnik.<id>.text / .low / .high as slots are: saved cleaned, an
    emptied one stays empty, Zadano puts a new question's placeholder
    back; .options as a list slot is, an item at a time, two at least,
    Zadano the two placeholders. A key of no question, or of no such
    field, is unknown; so are the slots of before (upitnik.q6.text) and a
    follow-up's text, a question's own since 27.10.2026
    (upitnik.14.followup_text)."""
    t = client_for_trainer()
    r = t.post("/copy/upitnik.6.text", data={"text": "  Kakva ti je\r\n kondicija? "})
    assert r.json() == {"ok": True, "text": "Kakva ti je\nkondicija?", "default": False}
    assert question(6).text == "Kakva ti je\nkondicija?" and question(6).updated_by is not None
    assert t.post("/copy/upitnik.6.text", data={"text": "  "}).json() == {"ok": True, "text": "", "default": False}
    assert question(6).text == ""
    assert t.post("/copy/upitnik.6.text", data={"reset": "1"}).json() == {"ok": True, "text": "Novo pitanje", "default": True}
    for field, placeholder in (("low", "…"), ("high", "…")):
        key = f"upitnik.14.{field}"
        assert t.post(f"/copy/{key}", data={"text": "drugo"}).json()["text"] == "drugo"
        assert getattr(question(14), field) == "drugo"
        assert t.post(f"/copy/{key}", data={"reset": "1"}).json()["text"] == placeholder
    r = t.post("/copy/upitnik.6.text", data={"text": "x" * (copy.CAP + 1)})
    assert r.status_code == 400 and question(6).text == "Novo pitanje"
    assert t.post("/copy/upitnik.3.options", data={"text": "90+", "index": "4"}).json()["items"] == [
        "do 30", "30-45", "45-60", "60+", "90+"]
    assert question(3).option_items[-1] == "90+"
    for key in ("upitnik.99.text", "upitnik.6.colour", "upitnik.q6.text", "upitnik.q1.options", "upitnik.q14b.text",
                "upitnik.14.followup_text"):
        r = t.post(f"/copy/{key}", data={"text": "x"})
        assert (r.status_code, r.json()) == (404, {"ok": False, "error": "Nepoznat tekst."}), key


def test_a_question_keeps_at_least_two_options():
    """An option goes with its ✕ (an emptied item), down to two; the last
    two stay ("Pitanje treba bar dva odgovora."), though either may be
    re-worded, and adding one or Zadano still works."""
    t = client_for_trainer()
    key = "upitnik.2.options"                                       # 2 / 3 / 4 / 5+
    assert t.post(f"/copy/{key}", data={"text": "", "index": "3"}).json()["items"] == ["2", "3", "4"]
    assert t.post(f"/copy/{key}", data={"text": "", "index": "0"}).json()["items"] == ["3", "4"]
    for i in ("0", "1"):
        r = t.post(f"/copy/{key}", data={"text": "  ", "index": i})
        assert r.status_code == 400 and r.json() == {"ok": False, "error": "Pitanje treba bar dva odgovora."}
    assert question(2).option_items == ["3", "4"]
    assert t.post(f"/copy/{key}", data={"text": "3 ili 4", "index": "0"}).json()["items"] == ["3 ili 4", "4"]
    assert t.post(f"/copy/{key}", data={"text": "", "index": "2"}).json()["items"] == ["3 ili 4", "4"]   # nothing at n
    assert t.post(f"/copy/{key}", data={"text": "5", "index": "2"}).json()["items"] == ["3 ili 4", "4", "5"]
    assert t.post(f"/copy/{key}", data={"text": "", "index": "0"}).json()["items"] == ["4", "5"]
    assert t.post(f"/copy/{key}", data={"reset": "1"}).json() == {
        "ok": True, "items": ["Prvi odgovor", "Drugi odgovor"], "default": True}


# ---------- the editor's page ----------

def test_every_word_is_on_the_page_for_the_editor_and_an_edit_shows_to_the_client():
    make_user("ivan@test.local")
    t = client_for_trainer()
    page = t.get("/upitnik").text
    for key in (k for k in copy.SLOTS if k.startswith("upitnik.")):
        assert f'data-copy="{key}"' in page, key
    for q in asked():
        key = f"upitnik.{q.row}"
        assert page.count(f'data-copy="{key}.text"') == 1, q.id
        if q.kind == "choice":                                  # one list, an editable span per option
            assert page.count(f'data-list="{key}.options"') == 1 and page.count(f'data-copy="{key}.options"') == len(q.options)
        if q.kind == "scale":
            assert page.count(f'data-copy="{key}.low"') == page.count(f'data-copy="{key}.high"') == 1, q.id
    assert page.count('class="act ed-add">+ Dodaj odgovor</button>') == len(CHOICES)
    assert 'data-label="Pitanje 6: tekst"' in page and 'data-label="Pitanje 15: tekst"' in page   # q16, 15th
    assert "followup_text" not in page and "dodatno pitanje" not in page
    assert t.post("/copy/upitnik.6.text", data={"text": "Kakva ti je kondicija?"}).json()["ok"]
    assert t.post("/copy/upitnik.2.options", data={"text": "6 ili više", "index": "4"}).json()["ok"]
    page = client_for("ivan@test.local").get("/upitnik").text
    assert '<h1 class="q-h" id="h-q6" tabindex="-1"><span class="t">Kakva ti je kondicija?</span></h1>' in page
    assert '<input type="radio" name="q2" value="6 ili više" required><span class="t">6 ili više</span>' in page


def lines(page: str) -> dict[str, str]:
    """Each step's grey line (the editor's), by its step's id: what its
    settings do (the line's first half; when it is asked is ifs')."""
    out = {}
    for part in page.split('<section class="q-step')[1:]:
        step = part.split('id="step-')[1].split('"')[0]
        if '<p class="q-ed-line">' in part.split("</section>")[0]:
            out[step] = unescape(part.split('<p class="q-ed-line">')[1].split("</p>")[0].split('<span class="q-ed-if')[0])
    return out


def ifs(page: str) -> dict[str, tuple[str, str]]:
    """Each conditional step's second line (the editor's, 27.10.2026): when
    it is asked, and its amber class if it has one ("void": its condition
    cannot work, it is asked always; "muted": a hidden question above it,
    nobody gets it; "" for the grey one), by its step's id."""
    out = {}
    for part in page.split('<section class="q-step')[1:]:
        step = part.split('id="step-')[1].split('"')[0]
        line = part.split("</section>")[0].split('<p class="q-ed-line">')[-1].split("</p>")[0]
        if '<span class="q-ed-if' in line:
            span = line.split('<span class="q-ed-if')[1]
            out[step] = (unescape(span.split(">", 1)[1].split("</span>")[0]), span.split('"')[0].strip())
    return out


def summary(page: str) -> str:
    """The scoring's summary (the editor's), as read: its words, tags dropped."""
    box = page.split('<div class="q-sum">')[1].split("</div>")[0]
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", box)).split())


def test_the_editors_page_says_what_each_question_does():
    """In edit mode each question has its controls (its switch, ↑ / ↓,
    Obriši pitanje, Dio, Vrsta, Bodovanje on a scale, Uloga on a scale or a
    yes / no, offering the role its kind can hold, Pita se) and a grey line
    saying what its settings do, and a conditional one when it is asked
    (in amber when that cannot work: its question hidden); above the
    first, how the score is made, and when nothing scores the alert that
    everyone starts at početna. A hidden question is on his page, marked
    off, and on no client's."""
    make_user("ivan@test.local")
    t = client_for_trainer()
    page = t.get("/upitnik").text
    got = lines(page)
    assert got["q1"] == "Dio 1 · jedan odgovor"
    assert got["q5"] == "Dio 2 · skala · boduje se: trening baza"
    assert got["q8"] == "Dio 2 · skala · boduje se: navike"
    assert got["q12"] == "Dio 3 · skala · ne boduje se"
    assert got["q14"] == "Dio 4 · skala · uloga: bolovi (7+ početna)"
    assert got["q16"] == "Dio 4 · slobodan tekst"
    assert got["q15"] == "Dio 4 · da / ne · uloga: ozljede (Da traži pregled trenera)"
    assert got["q17"] == "Dio 4 · slobodan tekst"
    # when the conditional ones are asked (the questions' numbers are their places: q15 is the 16th)
    assert ifs(page) == {"q16": ("Pita se samo ako pitanje 14 ≥ 4", ""), "q17": ("Pita se samo ako pitanje 16 = Da", "")}
    assert summary(page) == ("Bodovanje: trening baza = 3 pitanja, navike = 4 pitanja. "
                             "Rezultat = 0,6 × baza + 0,4 × navike.")
    step = page.split('id="step-q14"')[1].split("</section>")[0]
    for control in ('class="ed-flag" data-url="/upitnik/pitanje/14" data-field="shown" data-reload',
                    'form="q-mv-14" name="smjer" value="gore"', 'form="q-mv-14" name="smjer" value="dolje"',
                    'class="ed-q-x" form="q-x-14"', 'data-field="part"', 'data-field="kind"', 'data-field="scoring"',
                    '<option value="pain" selected>Bolovi</option>'):
        assert control in step, control
    assert "Ozljede" not in step                                      # a scale's role is pain alone
    assert 'data-field="scoring"' not in page.split('id="step-q15"')[1].split("</section>")[0]
    assert 'data-field="role"' not in page.split('id="step-q1"')[1].split("</section>")[0]
    first = page.split('id="step-q1"')[1].split("</section>")[0]
    assert 'value="gore" aria-label="Pitanje 1: jedno mjesto gore" disabled' in first
    for q in (8, 9, 10, 11):
        t.post(f"/upitnik/pitanje/{q}", data={"shown": "off"})
    page = t.get("/upitnik").text
    assert summary(page) == "Bodovanje: trening baza = 3 pitanja, navike = 0 pitanja. Rezultat = trening baza (navike nemaju pitanja)."
    assert lines(page)["q8"] == "Dio 2 · skala · skriveno: nitko ga ne dobiva i ne boduje se"
    assert '<section class="q-step is-off" id="step-q8"' in page
    client = client_for("ivan@test.local").get("/upitnik").text
    assert 'id="step-q8"' not in client and 'id="step-q7"' in client
    for q in (5, 6, 7):
        t.post(f"/upitnik/pitanje/{q}", data={"scoring": ""})
    page = t.get("/upitnik").text
    assert summary(page) == ("Bodovanje: trening baza = 0 pitanja, navike = 0 pitanja. "
                             "Nijedno pitanje se ne boduje — svi dobivaju početnu razinu.")
    assert '<p class="alert">Nijedno pitanje se ne boduje — svi dobivaju početnu razinu.</p>' in page
    t.post("/upitnik/pitanje/14", data={"shown": "off"})
    page = t.get("/upitnik").text
    assert lines(page)["q14"] == "Dio 4 · skala · skriveno: nitko ga ne dobiva, pravilo o bolovima ne vrijedi"
    assert ifs(page)["q16"] == ("Pita se samo ako pitanje 14 ≥ 4 — pitanje 14 je skriveno, pa ni ovo nitko ne dobiva",
                                "muted")
    assert '<section class="q-step is-muted" id="step-q16"' in page


# ---------- the migrations ----------

def _migration(file: str):
    """An Alembic revision's module, loaded from its file."""
    path = pathlib.Path(__file__).parents[1] / "alembic" / "versions" / file
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _run(step) -> None:
    """A revision's upgrade() or downgrade(), run for real on qmt_test."""
    with db.engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        step()


NEW = ("version", "pain_level", "pain_high", "needs_review", "consented_at")


def test_the_migration_makes_the_rows_there_version_1_and_keeps_their_scores():
    """e6564d9234b8, run on qmt_test as a database from before it is (the
    five columns not there, the score an integer): a row already there
    becomes version 1 and keeps its score (9 is 9.0), no pain, no flags, no
    consent; a row written after it is version 2 by default. Downgrade
    drops the five columns and makes the score an integer again, rounded."""
    mig = _migration("e6564d9234b8_upitnik_v2.py")
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    with db.engine.begin() as conn:
        for column in NEW:
            conn.execute(sa_text(f"ALTER TABLE onboarding_responses DROP COLUMN {column}"))
        conn.execute(sa_text("ALTER TABLE onboarding_responses ALTER COLUMN score TYPE integer USING round(score)::integer"))
        conn.execute(sa_text("INSERT INTO onboarding_responses (user_id, answers, score, level, goal) "
                             "VALUES (:u, '{\"staz\": 2}', 9, 'srednja', 'gornji')"), {"u": ivan})
    _run(mig.upgrade)
    columns = {c["name"]: c for c in sa_inspect(db.engine).get_columns("onboarding_responses")}
    assert set(NEW) <= set(columns) and str(columns["score"]["type"]) == "NUMERIC(4, 1)"
    old = db.get_onboarding(ivan)                                              # the app reads it
    assert (old.version, old.score, old.level, old.goal) == (1, 9.0, "srednja", "gornji")
    assert (old.pain_level, old.pain_high, old.needs_review, old.consented_at) == (None, False, False, None)
    with db.engine.begin() as conn:
        conn.execute(sa_text("INSERT INTO onboarding_responses (user_id, answers, score, level, goal) "
                             "VALUES (:u, '{}', 6.4, 'srednja', 'cijelo')"), {"u": ana})
    assert (db.get_onboarding(ana).version, db.get_onboarding(ana).score) == (2, 6.4)
    _run(mig.downgrade)
    columns = {c["name"]: c for c in sa_inspect(db.engine).get_columns("onboarding_responses")}
    assert not set(NEW) & set(columns) and str(columns["score"]["type"]) == "INTEGER"
    with db.engine.connect() as conn:
        scores = dict(conn.execute(sa_text("SELECT user_id, score FROM onboarding_responses")).all())
    assert scores == {ivan: 9, ana: 6}


def test_the_migration_turns_the_question_slots_into_rows_and_back():
    """3f8a6c2d9b71, run on qmt_test as a database from before it is (no
    upitnik_questions; the gym owner's edits in upitnik.q* slots): the
    fifteen rows with ids and positions 1–15, each text his edited one (an
    emptied one empty) or the default, a choice's options his list, the
    structure the code had (parts, kinds, the scoring, the two roles with
    their follow-ups' texts), all shown; the folded slots' rows gone, the
    other upitnik.* slots left; the id sequence past 15. Then he edits the
    rows; downgrade puts the first fifteen back as slots, only what differs
    from the defaults (a question deleted is its defaults again; a row's
    new kind takes no slot the old code lacks), and drops the table; a
    second upgrade folds them in again. The answers never move. Since
    27.10.2026 the next revision runs after it (5c1e7a9d2b48: the app
    reads its columns): the two follow-ups become q16 and q17 (the next
    ids), and their texts and a follow-up's answer go back with its
    downgrade before this one's."""
    mig = _migration("3f8a6c2d9b71_upitnik_questions.py")
    nxt = _migration("5c1e7a9d2b48_upitnik_branching.py")
    uid = make_user("trener@test.local", is_trainer=True)
    ivan = make_user("ivan@test.local")
    given = json.dumps(answers(q14=5, q14b="leđa"), ensure_ascii=False)        # a response given before it
    db.save_onboarding(ivan, given, 5.0, "srednja", "cijelo", pain_level=5, pain_high=False, needs_review=False,
                       consented_at=None)
    with db.engine.begin() as conn:
        conn.execute(sa_text("DROP TABLE upitnik_questions"))                 # the database before it
    edited = {"upitnik.q1.text": "Što želiš postići?", "upitnik.q3.text": "",
              "upitnik.q2.options": json.dumps(["2", "3", "4 ili više"], ensure_ascii=False),
              "upitnik.q6.high": "odlična", "upitnik.q14b.text": "Gdje točno?", "upitnik.q15.text": "Ozljede?",
              "upitnik.title": "Moj upitnik", "upitnik.part2.h": "Dio 2"}
    for key, text in edited.items():
        db.set_copy(key, text, uid)
    _run(mig.upgrade)
    _run(nxt.upgrade)
    rows = db.upitnik_questions()
    assert [(r.id, r.position, r.shown) for r in rows] == [(n, i, True) for i, n in enumerate(ORDER, start=1)]
    shape = [(r.part, r.kind, r.scoring, r.role, r.parent_id, r.condition) for r in rows]
    assert shape == [(q["part"], q["kind"], q["scoring"], q["role"], q["parent_id"], q["condition"])
                     for q in copy.UPITNIK_DEFAULT_QUESTIONS]
    by = {r.id: r for r in rows}
    assert (by[1].text, by[1].updated_by) == ("Što želiš postići?", uid) and by[3].text == ""
    assert by[2].option_items == ["2", "3", "4 ili više"] and by[1].option_items == list(CHOICES["q1"])
    assert (by[6].low, by[6].high) == ("vrlo loša", "odlična")
    assert (by[16].text, by[15].text, by[17].text) == ("Gdje točno?", "Ozljede?", "Opiši ukratko.")
    untouched = [r for r in rows if r.id in (4, 5, 7, 8, 9, 10, 11, 12, 13)]
    assert all((r.text, r.low, r.high, r.updated_by) == (TEXT[f"q{r.id}"], DEFAULTS[f"q{r.id}"]["low"],
                                                          DEFAULTS[f"q{r.id}"]["high"], None) for r in untouched)
    assert db.copy_texts() == {"upitnik.title": "Moj upitnik", "upitnik.part2.h": "Dio 2"}
    assert db.add_upitnik_question(None).id == 18                             # the sequence past 17
    assert "q16" in json.loads(db.get_onboarding(ivan).answers)              # q14b's answer, q16's now
    # the gym owner at work, then the way back
    db.set_upitnik_question_field(5, "text", "Treniraš li redovito?", uid)
    db.set_upitnik_question(12, {"kind": "choice"}, uid)                      # the old q12 has no options slot
    db.set_upitnik_question_field(12, "low", "nikada", uid)
    db.delete_upitnik_question(6)                                             # its defaults again
    db.set_upitnik_question_options(2, ["2", "3", "4", "5+"], uid)            # the default list again
    _run(nxt.downgrade)
    assert db.get_onboarding(ivan).answers == given                           # q14b's again
    _run(mig.downgrade)
    assert "upitnik_questions" not in sa_inspect(db.engine).get_table_names()
    assert db.copy_texts() == {"upitnik.q1.text": "Što želiš postići?", "upitnik.q3.text": "",
                               "upitnik.q5.text": "Treniraš li redovito?", "upitnik.q12.low": "nikada",
                               "upitnik.q14b.text": "Gdje točno?", "upitnik.q15.text": "Ozljede?",
                               "upitnik.title": "Moj upitnik", "upitnik.part2.h": "Dio 2"}
    _run(mig.upgrade)
    assert db.get_onboarding(ivan).answers == given                           # the answers never moved
    _run(nxt.upgrade)
    rows = {r.id: r for r in db.upitnik_questions()}
    assert len(rows) == 17 and (rows[5].text, rows[12].kind, rows[12].low) == ("Treniraš li redovito?", "scale", "nikada")
    assert rows[6].high == "izvrsna" and rows[2].option_items == ["2", "3", "4", "5+"]
    assert (rows[16].text, rows[16].parent_id, rows[17].text) == ("Gdje točno?", 14, "Opiši ukratko.")
    stored = json.loads(given)
    stored["q16"] = stored.pop("q14b")
    assert json.loads(db.get_onboarding(ivan).answers) == stored


def _prod_like_questions(conn) -> None:
    """upitnik_questions as prod had it on 27.10.2026, before 5c1e7a9d2b48:
    the follow-ups' texts in followup_text (no parent_id, no condition),
    the fifteen with q14 still the pain question ("Gdje te boli?") and q15
    a yes / no that lost the injuries role but kept its text ("Opiši
    ukratko."), q16 and q18 deleted, q17 a hidden scale he added (its text
    the placeholder every new question had: no role, no yes / no, dropped),
    q19 the yes / no that holds the injuries role now with a text of its
    own, q20 a yes / no with a text and no role (asked never until now);
    the id sequence at 20."""
    conn.execute(sa_text("DELETE FROM upitnik_questions"))
    conn.execute(sa_text('ALTER TABLE upitnik_questions DROP COLUMN parent_id, DROP COLUMN "condition", '
                         "ADD COLUMN followup_text text NOT NULL DEFAULT ''"))
    rows = [{**q, "role": "pain" if q["id"] == 14 else "", "shown": True,
             "followup_text": {14: "Gdje te boli?", 15: "Opiši ukratko."}.get(q["id"], "")}
            for q in copy.UPITNIK_DEFAULT_QUESTIONS if q["id"] <= 15]
    rows += [{**copy.UPITNIK_BLANK, "id": 17, "shown": False, "followup_text": "Opiši ukratko."},
             {**copy.UPITNIK_BLANK, "id": 19, "part": 3, "kind": "yesno", "text": "Jeste li rodili unazad godinu dana?",
              "role": "injuries", "shown": True, "followup_text": "Kada točno?"},
             {**copy.UPITNIK_BLANK, "id": 20, "part": 3, "kind": "yesno",
              "text": "imate li povijest srčanih bolesti u obitelji?", "shown": True, "followup_text": "Koje?"}]
    for position, q in enumerate(sorted(rows, key=lambda q: q["id"]), start=1):
        conn.execute(sa_text("INSERT INTO upitnik_questions (id, position, part, kind, text, options, low, high, "
                             "scoring, role, followup_text, shown) VALUES (:id, :position, :part, :kind, :text, "
                             ":options, :low, :high, :scoring, :role, :followup_text, :shown)"),
                     {**{k: q[k] for k in ("id", "part", "kind", "text", "low", "high", "scoring", "role",
                                          "followup_text", "shown")},
                      "position": position, "options": json.dumps(list(q["options"]), ensure_ascii=False)})
    conn.execute(sa_text("SELECT setval(pg_get_serial_sequence('upitnik_questions', 'id'), 20)"))


def test_the_branching_migration_turns_the_follow_ups_into_questions_and_back():
    """5c1e7a9d2b48, run on qmt_test shaped as prod was (_prod_like_questions):
    each follow-up becomes a text question right after its question, asked
    after it (parent_id, condition), with the next ids: q14's at ">=4"
    (the pain role), q15's at "yes" (a yes / no without a role but a text),
    q19's at "yes" (the injuries role), q20's at "yes" (a text no role
    asked); q17's text (a scale, no role) goes. The order is 1..n again,
    followup_text gone. A stored response's q14b / q15b (and a later one's
    q19b) become those questions' keys in their places, a version-1 one is
    untouched, and the karton prints the old answers under the new
    questions, a level in, the pain flag's "where" too. Downgrade: the
    texts back in followup_text, the rows and the columns gone, the keys
    back; a second upgrade makes them again, with new ids."""
    mig = _migration("5c1e7a9d2b48_upitnik_branching.py")
    ivan, ana, sara = make_user("ivan@test.local"), make_user("ana@test.local"), make_user("sara@test.local")
    make_user("trener@test.local", is_trainer=True)
    before = {}
    for key, value in answers(q14=5, q15=True).items():         # as read() stored them: a follow-up after its question
        before[key] = value
        if key in ("q14", "q15"):
            before[f"{key}b"] = "donji dio leđa" if key == "q14" else "Operacija koljena 2023."
    given = json.dumps(before, ensure_ascii=False)
    later = json.dumps({**answers(), "q19": True, "q19b": "Prošle godine"}, ensure_ascii=False)
    old = json.dumps({"staz": 2, "ozljede": 1})
    db.save_onboarding(ivan, given, 5.0, "srednja", "cijelo", pain_level=5, pain_high=False, needs_review=True,
                       consented_at=None)
    db.save_onboarding(ana, later, 5.0, "srednja", "cijelo", pain_level=1, pain_high=False, needs_review=True,
                       consented_at=None)
    db.save_onboarding(sara, old, 9, "srednja", "gornji", version=1, pain_level=None, pain_high=False,
                       needs_review=False, consented_at=None)
    with db.engine.begin() as conn:
        _prod_like_questions(conn)
    _run(mig.upgrade)
    columns = {c["name"] for c in sa_inspect(db.engine).get_columns("upitnik_questions")}
    assert {"parent_id", "condition"} <= columns and "followup_text" not in columns
    rows = db.upitnik_questions()
    assert [(r.id, r.position) for r in rows] == [(n, i) for i, n in enumerate(
        list(range(1, 15)) + [21, 15, 22, 17, 19, 23, 20, 24], start=1)]
    made = {r.id: (r.part, r.kind, r.text, r.parent_id, r.condition, r.shown) for r in rows if r.id > 20}
    assert made == {21: (4, "text", "Gdje te boli?", 14, ">=4", True), 22: (4, "text", "Opiši ukratko.", 15, "yes", True),
                    23: (3, "text", "Kada točno?", 19, "yes", True), 24: (3, "text", "Koje?", 20, "yes", True)}
    assert all((r.parent_id, r.condition) == (None, "") for r in rows if r.id <= 20)
    assert [(q.id, q.follows, q.depth) for q in asked() if q.follows] == [
        ("q21", "q14", 1), ("q22", "q15", 1), ("q23", "q19", 1), ("q24", "q20", 1)]
    stored = json.loads(db.get_onboarding(ivan).answers)
    assert list(stored)[13:] == ["q14", "q21", "q15", "q22"]
    assert (stored["q21"], stored["q22"]) == ("donji dio leđa", "Operacija koljena 2023.") and "q14b" not in stored
    assert json.loads(db.get_onboarding(ana).answers)["q23"] == "Prošle godine"
    assert db.get_onboarding(sara).answers == old
    block = unescape(upitnik_block(client_for("trener@test.local").get(f"/karton/{ivan}").text))
    assert ' class="follow d1">Gdje te boli? — <strong>donji dio leđa</strong></li>' in block
    assert ' class="follow d1">Opiši ukratko. — <strong>Operacija koljena 2023.</strong></li>' in block
    assert '<span class="u-flag pain">Bolovi 5/10 · donji dio leđa</span>' in block and "(pitanje uklonjeno)" not in block
    _run(mig.downgrade)
    columns = {c["name"] for c in sa_inspect(db.engine).get_columns("upitnik_questions")}
    assert "followup_text" in columns and not {"parent_id", "condition"} & columns
    with db.engine.connect() as conn:
        back = conn.execute(sa_text("SELECT id, followup_text FROM upitnik_questions ORDER BY position")).all()
    assert [r.id for r in back] == list(range(1, 16)) + [17, 19, 20]
    assert {r.id: r.followup_text for r in back if r.followup_text} == {
        14: "Gdje te boli?", 15: "Opiši ukratko.", 19: "Kada točno?", 20: "Koje?"}
    assert [db.get_onboarding(u).answers for u in (ivan, ana, sara)] == [given, later, old]
    _run(mig.upgrade)
    rows = db.upitnik_questions()
    assert [(r.text, r.parent_id, r.condition) for r in rows if r.parent_id] == [
        ("Gdje te boli?", 14, ">=4"), ("Opiši ukratko.", 15, "yes"), ("Kada točno?", 19, "yes"), ("Koje?", 20, "yes")]
    assert sorted(r.id for r in rows if r.parent_id) == [25, 26, 27, 28]     # ids are never given twice
    assert json.loads(db.get_onboarding(ivan).answers)["q25"] == "donji dio leđa"


# ---------- the karton ----------

def upitnik_block(page: str) -> str:
    return page.split('<section class="upitnik')[1].split("</section>")[0]


def test_the_clients_karton_shows_the_score_the_four_chips_and_the_pain_note():
    """Version 2 on the client's own karton: the level and its ramp, the
    score as "6,4 / 10", part 1's answers as four chips ("3 dana tjedno",
    "45-60 min"), "Ispuni ponovno"; the sentence for a client in pain when
    he is; never the trainer's flags or the list of answers."""
    make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    c.post("/upitnik", data=form(q1="Povećanje snage i mišićne mase", q2="3", q3="45-60", q4="U teretani",
                                 q5="7", q6="6", q7="5", q8="6", q9="8", q10="8", q11="6",
                                 q14="5", q16="leđa", q15="da", q17="Operacija."), follow_redirects=False)
    block = upitnik_block(c.get("/karton").text)
    assert ">Srednja razina</h2>" in block and "Razina 2 od 3 — programi na /treninzi prate ovu razinu." in block
    assert '<span class="u-score">6,4 / 10</span>' in block
    chips = [unescape(x.split("<")[0]) for x in block.split('<span class="u-fact">')[1:]]
    assert chips == ["Povećanje snage i mišićne mase", "3 dana tjedno", "45-60 min", "U teretani"]
    assert 'href="/upitnik"' in block and "Ispuni ponovno" in block
    for theirs in ("Zahtijeva pregled", "Bolovi", "<details>", "u-note", "Stari upitnik"):
        assert theirs not in block, theirs
    c.post("/upitnik", data=form(q14="9", q16="leđa"), follow_redirects=False)
    block = upitnik_block(c.get("/karton").text)
    assert ">Početna razina</h2>" in block
    assert ('<p class="u-note">Zbog čestih bolova krećeš od početne razine — javi se treneru prije prvog treninga.</p>'
            in unescape(block))


def test_the_trainers_karton_flags_review_and_pain_and_lists_every_answer():
    """The trainer's view of a client: a red "Zahtijeva pregled" when the
    injuries question was yes, an amber "Bolovi N/10 · where" when the pain
    question was 4 or more, and under Odgovori every question answered as
    the gym owner words it now, each with its answer, the free texts asked
    after the safety questions one step in under theirs. Neither chip
    without its reason."""
    uid = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    client_for("ivan@test.local").post("/upitnik", data=form(
        q5="7", q14="5", q16="donji dio leđa", q15="da", q17="Operacija koljena 2023."), follow_redirects=False)
    t = client_for("trener@test.local")
    t.post("/copy/upitnik.6.text", data={"text": "Kakva ti je kondicija?"})
    block = unescape(upitnik_block(t.get(f"/karton/{uid}").text))
    assert '<span class="u-flag review">Zahtijeva pregled</span>' in block
    assert '<span class="u-flag pain">Bolovi 5/10 · donji dio leđa</span>' in block
    rows = block.split("<details>")[1].split("</details>")[0].split("<li")[1:]
    assert len(rows) == 17                                              # the seventeen, all asked
    assert f'>{TEXT["q1"]} — <strong>Gubitak težine</strong></li>' in rows[0]
    assert f'>{TEXT["q5"]} — <strong>7 / 10</strong></li>' in rows[4]
    assert ">Kakva ti je kondicija? — <strong>5 / 10</strong></li>" in rows[5]     # the question as he words it now
    assert f' class="follow d1">{TEXT["q16"]} — <strong>donji dio leđa</strong></li>' in rows[14]
    assert f'>{TEXT["q15"]} — <strong>Da</strong></li>' in rows[15]
    assert f' class="follow d1">{TEXT["q17"]} — <strong>Operacija koljena 2023.</strong></li>' in rows[16]
    assert sum(' class="follow' in row for row in rows) == 2
    assert "Ispuni ponovno" not in block
    client_for("ivan@test.local").post("/upitnik", data=form(q14="3"), follow_redirects=False)
    block = upitnik_block(t.get(f"/karton/{uid}").text)
    assert "u-flags" not in block and "Zahtijeva pregled" not in block and "Bolovi" not in block


def test_the_karton_keeps_every_answer_under_its_question_as_it_is_now():
    """The questions change after a client answered: one re-worded, one
    hidden, one of another kind, the pain role moved, two deleted. Under
    Odgovori every answer is still there: under its question's current
    text (a hidden one's too), as it was given (a choice's text under a
    question that is a multi now), and the deleted ones' last, by their
    number, under "(pitanje uklonjeno)". Where it hurts stays under q14,
    the question it is asked after, wherever the role is; the note asked
    after the deleted injuries question is asked always now, so it is no
    longer one step in. The pain flag's "where" is the answer under the
    question that holds the pain role now (27.10.2026: pain_where): moved
    to q13, which has none, the flag says the level alone."""
    uid = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    client_for("ivan@test.local").post("/upitnik", data=form(
        q5="8", q12="7", q14="6", q16="donji dio leđa", q15="da", q17="Operacija."), follow_redirects=False)
    t = client_for("trener@test.local")
    t.post("/copy/upitnik.6.text", data={"text": "Kakva ti je kondicija?"})
    t.post("/upitnik/pitanje/12", data={"shown": "off"})
    t.post("/upitnik/pitanje/4", data={"kind": "multi"})
    t.post("/upitnik/pitanje/13", data={"role": "pain"})
    for qid in (15, 5):
        t.post(f"/upitnik/pitanje/{qid}/obrisi")
    block = unescape(upitnik_block(t.get(f"/karton/{uid}").text))
    rows = block.split("<details>")[1].split("</details>")[0].split("<li")[1:]
    assert len(rows) == 17                                              # nothing dropped
    assert f'>{TEXT["q4"]} — <strong>{CHOICES["q4"][0]}</strong></li>' in rows[3]
    assert ">Kakva ti je kondicija? — <strong>5 / 10</strong></li>" in rows[4]
    assert f'>{TEXT["q12"]} — <strong>7 / 10</strong></li>' in rows[10]
    assert f'>{TEXT["q14"]} — <strong>6 / 10</strong></li>' in rows[12]
    assert f' class="follow d1">{TEXT["q16"]} — <strong>donji dio leđa</strong></li>' in rows[13]
    assert f'<li>{TEXT["q17"]} — <strong>Operacija.</strong></li>' in "<li" + rows[14]
    assert ">(pitanje uklonjeno) — <strong>8 / 10</strong></li>" in rows[15]
    assert ">(pitanje uklonjeno) — <strong>Da</strong></li>" in rows[16]
    assert '<span class="u-flag pain">Bolovi 6/10</span>' in block
    assert '<span class="u-flag review">Zahtijeva pregled</span>' in block
    assert json.loads(db.get_onboarding(uid).answers)["q17"] == "Operacija."      # kept as given


def test_the_karton_indents_a_chain_under_its_questions():
    """Da / Da / an option: the trainer's list prints the chain's answers
    each a level further in under the question it is asked after
    (li.follow d1, d2); the client's own karton is as it was (its chips,
    part 1's, no list). Ne: neither child was asked, so neither prints."""
    uid = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    porod, godina, rez = chain()
    c, t = client_for("ivan@test.local"), client_for("trener@test.local")
    sent = {**form(), f"q{porod}": "da", f"q{godina}": "da", f"q{rez}": "Carski rez"}
    assert "ok=" in c.post("/upitnik", data=sent, follow_redirects=False).headers["location"]
    block = unescape(upitnik_block(t.get(f"/karton/{uid}").text))
    rows = block.split("<details>")[1].split("</details>")[0].split("<li")[1:]
    assert [row.split("</li>")[0] for row in rows[-3:]] == [
        ">Jeste li imali porod? — <strong>Da</strong>",
        ' class="follow d1">Je li to bilo u zadnjih godinu dana? — <strong>Da</strong>',
        ' class="follow d2">Kako je završio porod? — <strong>Carski rez</strong>']
    own = upitnik_block(c.get("/karton").text)
    chips = [unescape(x.split("<")[0]) for x in own.split('<span class="u-fact">')[1:]]
    assert chips == [CHOICES["q1"][0], "2 dana tjedno", "do 30 min", CHOICES["q4"][0]] and "<details>" not in own
    c.post("/upitnik", data={**sent, f"q{porod}": "ne"}, follow_redirects=False)
    block = unescape(upitnik_block(t.get(f"/karton/{uid}").text))
    assert ">Jeste li imali porod? — <strong>Ne</strong></li>" in block
    assert "zadnjih godinu dana" not in block and "Carski rez" not in block


def test_an_old_rows_block_reads_its_old_answers_and_asks_for_the_new_one():
    """A version-1 row (five questions and a goal) shows its level, goal
    and points of 14 as before, its answers through QUESTIONS_V1 for the
    trainer, and "Stari upitnik — ispuni novi." with the link for the
    client. It still counts as filled: its programmes stay open."""
    uid = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    db.save_onboarding(uid, json.dumps({"staz": 2, "tjedno": 2, "sklekovi": 1, "cucanj": 2, "ozljede": 2}), 9,
                       "srednja", "gornji", version=1, pain_level=None, pain_high=False, needs_review=False,
                       consented_at=None)
    pid = db.create_program("Gornji blok", None, "srednja", "gornji")
    c = client_for("ivan@test.local")
    block = upitnik_block(c.get("/karton").text)
    assert ">Srednja razina</h2>" in block and '<span class="u-pill">Gornji dio tijela</span>' in block
    assert '<span class="u-score">9/14 bodova</span>' in block and "i cilj." in block
    assert 'Stari upitnik — <a class="tlink" href="/upitnik">ispuni novi</a>.' in block
    assert "u-fact" not in block
    assert "Gornji blok" in c.get("/treninzi").text and c.get(f"/treninzi/{pid}").status_code == 200
    block = unescape(upitnik_block(client_for("trener@test.local").get(f"/karton/{uid}").text))
    assert '<p class="u-old">Stari upitnik.</p>' in block
    assert "<li>Koliko dugo redovito treniraš? — <strong>6 mjeseci – 2 godine</strong></li>" in block
    assert "<li>Imaš li ozljede ili bolove koji ograničavaju trening? — <strong>Ne</strong></li>" in block


# ---------- two editors at once ----------

def test_two_quick_adds_never_pass_the_cap():
    """"+ Dodaj pitanje" tapped twice, or by two editors at once, near the
    cap: the table lock makes the count and the next position one step,
    so never more than 40, and no position twice."""
    for _ in range(db.MAX_UPITNIK_QUESTIONS - len(ORDER) - 2):
        db.add_upitnik_question(None)
    landed: list[bool] = []
    threads = [threading.Thread(target=lambda: landed.append(db.add_upitnik_question(None) is not None)) for _ in range(6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert landed.count(True) == 2 and len(order()) == db.MAX_UPITNIK_QUESTIONS
    assert [q.position for q in db.upitnik_questions()] == list(range(1, db.MAX_UPITNIK_QUESTIONS + 1))


def test_two_editors_never_leave_two_pain_questions():
    """Two editors give the pain role to two questions at the same moment:
    one of them holds it after, never both (the lock and the role's unique
    index), and the question that held it before has lost it."""
    for _ in range(5):
        db.set_upitnik_question(13, {"role": ""}, None)
        db.set_upitnik_question(12, {"role": ""}, None)
        db.set_upitnik_question(14, {"role": "pain"}, None)
        start, failed = threading.Barrier(2), []

        def take(qid: int) -> None:
            start.wait()
            try:
                db.set_upitnik_question(qid, {"role": "pain"}, None)
            except Exception as e:                                   # pragma: no cover - the failure we guard against
                failed.append(e)

        threads = [threading.Thread(target=take, args=(qid,)) for qid in (12, 13)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        pain = [q.id for q in db.upitnik_questions() if q.role == "pain"]
        assert not failed and len(pain) == 1 and pain[0] in (12, 13)
