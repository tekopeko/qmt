"""The online-trening upitnik, version 2 (26.10.2026): the gym owner's final
questionnaire. src/qmt/upitnik.py holds its structure (fifteen questions in
four parts, two follow-ups) and his rules: the score (0.6 × the mean of
q5–q7 + 0.4 × the mean of q8–q11, to one decimal; up to 4.0 početna, up to
7.0 srednja, above napredna) and the two safety rules (q14 at 7 or more:
početna, and see the trainer first; q15 yes: the trainer reviews the
profile). src/qmt/copy.py holds his words, every one a slot (upitnik.*).
Here: the scoring, POST /upitnik (what a submission must hold, what is
stored), the migration that made the rows already there version 1, the
karton's block for a new response and an old one, and the copy rules that
are the questionnaire's own (every slot on /upitnik for the editor, at
least two options per choice). One question per screen, in a browser, is
tests/test_upitnik_ui.py.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
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


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
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


def answers(base=(5, 5, 5), habits=(5, 5, 5, 5), **changes) -> dict:
    """A whole set of answers as stored: part 1 each choice's first option
    (the slots' defaults), the scored scales as given (q5–q7, q8–q11), q12
    and q13 at 5, no pain (q14 at 1), no injuries; `changes` on top."""
    out = {q: options[0] for q, (_, options) in copy.UPITNIK_CHOICES.items()}
    out.update(zip(upitnik.BASE, base))
    out.update(zip(upitnik.HABITS, habits))
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


# ---------- the structure: fifteen questions, every word a slot ----------

def test_fifteen_questions_in_four_parts_two_follow_ups_and_every_word_a_slot():
    """q1–q4 choices (part 1), q5–q11 the scored scales (part 2), q12 and
    q13 scales for the trainer (part 3), q14 a scale and q15 yes / no (part
    4), each followed by its free text. Every word is a slot of the kind
    the question needs, and no upitnik.* slot is anything else."""
    assert [q.id for q in upitnik.QUESTIONS] == [f"q{n}" for n in range(1, 16)]
    assert [q.id for q in upitnik.STEPS] == [f"q{n}" for n in range(1, 15)] + ["q14b", "q15", "q15b"]
    kinds = {q.id: (q.part, q.kind, q.scored) for q in upitnik.STEPS}
    assert kinds == {**{f"q{n}": (1, "choice", False) for n in range(1, 5)},
                     **{f"q{n}": (2, "scale", True) for n in range(5, 12)},
                     "q12": (3, "scale", False), "q13": (3, "scale", False), "q14": (4, "scale", False),
                     "q14b": (4, "text", False), "q15": (4, "yesno", False), "q15b": (4, "text", False)}
    assert {q.id for q in upitnik.QUESTIONS if q.scored} == set(upitnik.BASE + upitnik.HABITS)
    want = {"upitnik.title", "upitnik.intro", "upitnik.yes", "upitnik.no", "upitnik.consent", "upitnik.submit",
            "upitnik.back", "upitnik.next", "upitnik.pain_note", *(f"upitnik.part{n}.h" for n in range(1, 5))}
    for q in upitnik.STEPS:
        want.add(f"upitnik.{q.id}.text")
        if q.kind == "choice":
            want.add(f"upitnik.{q.id}.options")
            assert isinstance(copy.SLOTS[f"upitnik.{q.id}.options"], copy.ListSlot)
            assert len(copy.SLOTS[f"upitnik.{q.id}.options"].default) >= upitnik.MIN_OPTIONS
        if q.kind == "scale":
            want |= {f"upitnik.{q.id}.low", f"upitnik.{q.id}.high"}
    assert {k for k in copy.SLOTS if k.startswith("upitnik.")} == want
    assert copy.UPITNIK_OPTION_KEYS == {k for k in want if k.endswith(".options")}
    assert copy.SLOTS["upitnik.q13.text"].default.startswith("❤️‍🔥 Koliko ti je važna")   # his emoji, a ZWJ sequence
    assert copy.SLOTS["upitnik.q1.options"].default[3] == "Rehabilitacija / rješavanje bolova"   # one option


# ---------- the score: the owner's formula and his two safety rules ----------

def test_the_owners_formula_on_three_hand_computed_examples():
    """One per level, at the edges, by hand: a mean of three and a mean of
    four, weighted 0.6 and 0.4, to one decimal."""
    # početna at its edge: baza (4+4+4)/3 = 4, navike (4+4+4+4)/4 = 4; 0.6·4 + 0.4·4 = 4.0
    r = upitnik.evaluate(answers((4, 4, 4), (4, 4, 4, 4)))
    assert (r.score, r.level) == (4.0, "pocetna")
    # a tenth more is srednja: navike (4+4+4+5)/4 = 4.25; 2.4 + 1.7 = 4.1
    r = upitnik.evaluate(answers((4, 4, 4), (4, 4, 4, 5)))
    assert (r.score, r.level) == (4.1, "srednja")
    # srednja at its edge, and the rounding: baza (10+9+9)/3 = 9.333…, navike
    # (4+4+3+3)/4 = 3.5; 0.6·9.333… + 0.4·3.5 = 5.6 + 1.4 = 7.0. The floats
    # add up to 7.000000000000001, which unrounded would be napredna.
    assert 0.6 * (28 / 3) + 0.4 * (14 / 4) > 7.0
    r = upitnik.evaluate(answers((10, 9, 9), (4, 4, 3, 3)))
    assert (r.score, r.level) == (7.0, "srednja")
    # napredna just past it: baza (8+7+7)/3 = 7.333…, navike (7+7+6+7)/4 = 6.75; 4.4 + 2.7 = 7.1
    r = upitnik.evaluate(answers((8, 7, 7), (7, 7, 6, 7)))
    assert (r.score, r.level) == (7.1, "napredna")
    # the two ends of the range
    assert upitnik.evaluate(answers((1, 1, 1), (1, 1, 1, 1))).score == 1.0
    assert upitnik.evaluate(answers((10, 10, 10), (10, 10, 10, 10))).score == 10.0
    # every score is a whole tenth: (2 × the three + the four) / 10, never more digits
    for s3 in range(3, 31):
        for s4 in range(4, 41):
            assert upitnik.score(answers((s3, 0, 0), (s4, 0, 0, 0))) == (2 * s3 + s4) / 10
    assert upitnik.score_text(6.4) == "6,4 / 10" and upitnik.score_text(10.0) == "10,0 / 10"


def test_pain_at_seven_or_more_is_pocetna_whatever_the_score():
    """q14 at 7 or more: početna, and pain_high (the client is told to see
    the trainer first); the score stays what the formula says. At 6 the
    score decides."""
    top = answers((10, 10, 10), (10, 10, 10, 10))
    r = upitnik.evaluate({**top, "q14": 6, "q14b": "leđa"})
    assert (r.score, r.level, r.pain_level, r.pain_high) == (10.0, "napredna", 6, False)
    for pain in (7, 10):
        r = upitnik.evaluate({**top, "q14": pain, "q14b": "leđa"})
        assert (r.score, r.level, r.pain_level, r.pain_high) == (10.0, "pocetna", pain, True)


def test_injuries_flag_the_profile_for_the_trainer_and_change_no_level():
    assert not upitnik.evaluate(answers()).needs_review
    r = upitnik.evaluate(answers(q15=True, q15b="Operacija koljena 2023."))
    assert r.needs_review and (r.score, r.level, r.pain_high) == (5.0, "srednja", False)


def test_parts_one_and_three_and_the_safety_questions_do_not_move_the_score():
    """q1–q4 (they will choose the content), q12 and q13 (the trainer's
    information) and q14 / q15 never change the score."""
    scored = ((6, 7, 5), (6, 8, 7, 5))
    expected = upitnik.score(answers(*scored))
    for q, (_, options) in copy.UPITNIK_CHOICES.items():
        for option in options:
            assert upitnik.score(answers(*scored, **{q: option})) == expected
    for other in ("q12", "q13", "q14"):
        for value in upitnik.SCALE:
            assert upitnik.score(answers(*scored, **{other: value})) == expected
    assert upitnik.score(answers(*scored, q15=True)) == expected


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
        q14="5", q14b="  Leđa,\r\n   donji   dio ", q15="da", q15b="Operacija koljena 2023."), follow_redirects=False)
    assert r.status_code == 303
    assert unquote(r.headers["location"]) == "/treninzi?ok=Upitnik je spremljen — Srednja razina."
    row = db.get_onboarding(uid)
    assert json.loads(row.answers) == {
        "q1": "Povećanje snage i mišićne mase", "q2": "3", "q3": "45-60", "q4": "U teretani",
        "q5": 7, "q6": 6, "q7": 5, "q8": 6, "q9": 8, "q10": 8, "q11": 6, "q12": 4, "q13": 8,
        "q14": 5, "q14b": "Leđa,\ndonji dio", "q15": True, "q15b": "Operacija koljena 2023."}
    # baza (7+6+5)/3 = 6, navike (6+8+8+6)/4 = 7; 3.6 + 2.8 = 6.4
    assert (row.version, row.score, row.level, row.goal) == (2, 6.4, "srednja", "cijelo")
    assert (row.pain_level, row.pain_high, row.needs_review) == (5, False, True)
    assert before <= row.consented_at <= datetime.now(config.TZ)
    assert "Upitnik je spremljen — Srednja razina." in c.get(r.headers["location"]).text


def test_a_follow_up_that_was_not_asked_is_not_stored():
    """Without JS every step is on the page, the follow-ups too: what was
    typed into one its question did not call for is left out."""
    uid = make_user("ivan@test.local")
    r = client_for("ivan@test.local").post("/upitnik", data=form(q14="3", q14b="ništa", q15="ne", q15b="ništa"),
                                           follow_redirects=False)
    assert "ok=" in r.headers["location"]
    stored = json.loads(db.get_onboarding(uid).answers)
    assert "q14b" not in stored and "q15b" not in stored and (stored["q14"], stored["q15"]) == (3, False)


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
    top = {q: "10" for q in upitnik.BASE + upitnik.HABITS}
    r = c.post("/upitnik", data=form(**top, q14="8", q14b="vrat"), follow_redirects=False)
    assert unquote(r.headers["location"]) == (
        "/treninzi?ok=Upitnik je spremljen — Početna razina. Zbog čestih bolova krećeš od početne razine — "
        "javi se treneru prije prvog treninga.")
    row = db.get_onboarding(uid)
    assert (row.version, row.score, row.level, row.goal, row.pain_level, row.pain_high) == (2, 10.0, "pocetna", "cijelo", 8, True)
    with db.engine.connect() as conn:
        assert conn.execute(sa_text("SELECT count(*) FROM onboarding_responses")).scalar() == 1
    t = client_for("trener@test.local")
    t.post("/copy/upitnik.pain_note", data={"text": "Javi se treneru."})
    r = c.post("/upitnik", data=form(**top, q14="7", q14b="vrat"), follow_redirects=False)
    assert unquote(r.headers["location"]).endswith("Početna razina. Javi se treneru.")
    t.post("/copy/upitnik.pain_note", data={"text": ""})
    r = c.post("/upitnik", data=form(**top, q14="7", q14b="vrat"), follow_redirects=False)
    assert unquote(r.headers["location"]).endswith("Upitnik je spremljen — Početna razina.")
    r = c.post("/upitnik", data=form(**top, q14="6", q14b="vrat"), follow_redirects=False)
    assert unquote(r.headers["location"]).endswith("— Napredna razina.") and not db.get_onboarding(uid).pain_high


ERROR = "/upitnik?error=Odgovori+na+sva+pitanja."


@pytest.mark.parametrize("what, sent, where", [
    ("a scale missing", {"q9": None}, ERROR),
    ("a scale out of range", {"q9": "11"}, ERROR),
    ("a scale of zero", {"q12": "0"}, ERROR),
    ("a scale in between", {"q6": "7.5"}, ERROR),
    ("a choice missing", {"q3": None}, ERROR),
    ("an option the slot does not have", {"q4": "Na plaži"}, ERROR),
    ("an option's index, not its text", {"q1": "0"}, ERROR),
    ("yes / no neither", {"q15": "možda"}, ERROR),
    ("q14b missing when q14 is 4", {"q14": "4"}, ERROR),
    ("q14b blank when q14 is 9", {"q14": "9", "q14b": "  \r\n "}, ERROR),
    ("q15b missing when q15 is yes", {"q15": "da"}, ERROR),
    ("a free text past the cap", {"q15": "da", "q15b": "x" * (upitnik.TEXT_MAX + 1)}, ERROR),
    ("the consent missing", {"consent": None},
     "/upitnik?error=Potvrdi%20pristanak%20na%20obradu%20podataka%20o%20zdravlju."),
])
def test_an_incomplete_or_invalid_submission_stores_nothing(what, sent, where):
    uid = make_user("ivan@test.local")
    r = client_for("ivan@test.local").post("/upitnik", data=form(**sent), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == where, what
    assert db.get_onboarding(uid) is None, what


def test_an_answer_is_an_option_as_its_slot_holds_it_now():
    """The gym owner re-words an option: a form still holding the old text
    is refused (nothing stored), the new text is what is stored. An option
    he writes in two lines comes back from a browser with a CRLF, and is
    the same option."""
    uid = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    t, c = client_for("trener@test.local"), client_for("ivan@test.local")
    assert t.post("/copy/upitnik.q4.options", data={"text": "U dvorani QMT", "index": "2"}).json()["ok"]
    r = c.post("/upitnik", data=form(q4="U teretani"), follow_redirects=False)
    assert r.headers["location"] == ERROR and db.get_onboarding(uid) is None
    c.post("/upitnik", data=form(q4="U dvorani QMT"), follow_redirects=False)
    assert json.loads(db.get_onboarding(uid).answers)["q4"] == "U dvorani QMT"
    t.post("/copy/upitnik.q1.options", data={"text": "Gubitak težine\ni oblikovanje", "index": "0"})
    r = c.post("/upitnik", data=form(q1="Gubitak težine\r\ni oblikovanje"), follow_redirects=False)
    assert "ok=" in r.headers["location"]
    assert json.loads(db.get_onboarding(uid).answers)["q1"] == "Gubitak težine\ni oblikovanje"


def test_who_gets_the_page_and_who_may_send_it():
    """A client with an online plan fills it; one without is sent to his
    karton, both ways, as before. The trainer and the owner get the page
    with no plan of their own (it is where its words are edited) and never
    send it: their submission is refused and stores nothing, the owner's
    too when he holds an online plan (his page is the editor's, a choice
    his options list)."""
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
    for mark in ("data-copy", "data-list", "copyToggle", 'class="ed-x"'):
        assert mark not in page, mark
    for q, (_, options) in copy.UPITNIK_CHOICES.items():
        for option in options:
            assert f'<input type="radio" name="{q}" value="{option}" required>' in page
    assert page.count('type="radio" name="q5"') == 10 and 'name="q14b"' in page and 'name="consent"' in page
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


# ---------- the migration ----------

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
                                 q14="5", q14b="leđa", q15="da", q15b="Operacija."), follow_redirects=False)
    block = upitnik_block(c.get("/karton").text)
    assert ">Srednja razina</h2>" in block and "Razina 2 od 3 — programi na /treninzi prate ovu razinu." in block
    assert '<span class="u-score">6,4 / 10</span>' in block
    chips = [unescape(x.split("<")[0]) for x in block.split('<span class="u-fact">')[1:]]
    assert chips == ["Povećanje snage i mišićne mase", "3 dana tjedno", "45-60 min", "U teretani"]
    assert 'href="/upitnik"' in block and "Ispuni ponovno" in block
    for theirs in ("Zahtijeva pregled", "Bolovi", "<details>", "u-note", "Stari upitnik"):
        assert theirs not in block, theirs
    c.post("/upitnik", data=form(q14="9", q14b="leđa"), follow_redirects=False)
    block = upitnik_block(c.get("/karton").text)
    assert ">Početna razina</h2>" in block
    assert ('<p class="u-note">Zbog čestih bolova krećeš od početne razine — javi se treneru prije prvog treninga.</p>'
            in unescape(block))


def test_the_trainers_karton_flags_review_and_pain_and_lists_every_answer():
    """The trainer's view of a client: a red "Zahtijeva pregled" when q15
    was yes, an amber "Bolovi N/10 · where" when q14 was 4 or more, and
    under Odgovori all fifteen questions as the gym owner words them now,
    each with its answer, the free texts under theirs. Neither chip
    without its reason."""
    uid = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    client_for("ivan@test.local").post("/upitnik", data=form(
        q5="7", q14="5", q14b="donji dio leđa", q15="da", q15b="Operacija koljena 2023."), follow_redirects=False)
    t = client_for("trener@test.local")
    t.post("/copy/upitnik.q6.text", data={"text": "Kakva ti je kondicija?"})
    block = unescape(upitnik_block(t.get(f"/karton/{uid}").text))
    assert '<span class="u-flag review">Zahtijeva pregled</span>' in block
    assert '<span class="u-flag pain">Bolovi 5/10 · donji dio leđa</span>' in block
    rows = block.split("<details>")[1].split("</details>")[0].split("<li")[1:]
    assert len(rows) == 17                                              # 15 questions, 2 follow-ups
    texts = {q: copy.SLOTS[f"upitnik.{q}.text"].default for q in ("q1", "q5", "q14b", "q15", "q15b")}
    assert f'>{texts["q1"]} — <strong>Gubitak težine</strong></li>' in rows[0]
    assert f'>{texts["q5"]} — <strong>7 / 10</strong></li>' in rows[4]
    assert ">Kakva ti je kondicija? — <strong>5 / 10</strong></li>" in rows[5]     # the question as he words it now
    assert f' class="follow">{texts["q14b"]} — <strong>donji dio leđa</strong></li>' in rows[14]
    assert f'>{texts["q15"]} — <strong>Da</strong></li>' in rows[15]
    assert f' class="follow">{texts["q15b"]} — <strong>Operacija koljena 2023.</strong></li>' in rows[16]
    assert "Ispuni ponovno" not in block
    client_for("ivan@test.local").post("/upitnik", data=form(q14="3"), follow_redirects=False)
    block = upitnik_block(t.get(f"/karton/{uid}").text)
    assert "u-flags" not in block and "Zahtijeva pregled" not in block and "Bolovi" not in block


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


# ---------- the copy: every word on /upitnik, two options at least ----------

def test_every_word_is_on_the_page_for_the_editor_and_an_edit_shows_to_the_client():
    make_user("trener@test.local", is_trainer=True)
    make_user("ivan@test.local")
    t = client_for("trener@test.local")
    page = t.get("/upitnik").text
    for key, slot in copy.SLOTS.items():
        if not key.startswith("upitnik."):
            continue
        if isinstance(slot, copy.ListSlot):                 # one list, an editable span per option
            assert page.count(f'data-list="{key}"') == 1 and page.count(f'data-copy="{key}"') == len(slot.default), key
        else:
            assert f'data-copy="{key}"' in page, key
    assert page.count('class="act ed-add">+ Dodaj odgovor</button>') == len(copy.UPITNIK_CHOICES)
    assert t.post("/copy/upitnik.q6.text", data={"text": "💪 Kakva ti je kondicija?"}).json()["ok"]
    assert t.post("/copy/upitnik.q2.options", data={"text": "6 ili više", "index": "4"}).json()["ok"]
    page = client_for("ivan@test.local").get("/upitnik").text
    assert '<h1 class="q-h" id="h-q6" tabindex="-1"><span class="t">💪 Kakva ti je kondicija?</span></h1>' in page
    assert '<input type="radio" name="q2" value="6 ili više" required><span class="t">6 ili više</span>' in page


def test_a_question_keeps_at_least_two_options():
    """An option goes with its ✕ (an emptied item), down to two; the last
    two stay ("Pitanje treba bar dva odgovora."), though either may be
    re-worded, and adding one or Zadano still works."""
    make_user("trener@test.local", is_trainer=True)
    t = client_for("trener@test.local")
    key = "upitnik.q2.options"                                      # 2 / 3 / 4 / 5+
    assert t.post(f"/copy/{key}", data={"text": "", "index": "3"}).json()["items"] == ["2", "3", "4"]
    assert t.post(f"/copy/{key}", data={"text": "", "index": "0"}).json()["items"] == ["3", "4"]
    for i in ("0", "1"):
        r = t.post(f"/copy/{key}", data={"text": "  ", "index": i})
        assert r.status_code == 400 and r.json() == {"ok": False, "error": "Pitanje treba bar dva odgovora."}
    assert json.loads(db.copy_texts()[key]) == ["3", "4"]
    assert t.post(f"/copy/{key}", data={"text": "3 ili 4", "index": "0"}).json()["items"] == ["3 ili 4", "4"]
    assert t.post(f"/copy/{key}", data={"text": "", "index": "2"}).json()["items"] == ["3 ili 4", "4"]   # nothing at n
    assert t.post(f"/copy/{key}", data={"text": "5", "index": "2"}).json()["items"] == ["3 ili 4", "4", "5"]
    assert t.post(f"/copy/{key}", data={"text": "", "index": "0"}).json()["items"] == ["4", "5"]
    assert t.post(f"/copy/{key}", data={"reset": "1"}).json() == {"ok": True, "items": ["2", "3", "4", "5+"], "default": True}
