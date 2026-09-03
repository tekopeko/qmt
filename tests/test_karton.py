"""Karton + onboarding upitnik: scoring, access control, diary ownership."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import pytest
from fastapi.testclient import TestClient

from qmt import auth, config, db, upitnik
from qmt.models import Base, Booking, User
from qmt.web.app import app


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    yield


def make_user(email: str, is_trainer: bool = False) -> int:
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    if is_trainer:
        with db.session_scope() as s:
            s.get(User, u.id).is_trainer = True
    return u.id


def client_for(email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"email": email, "password": "lozinka123"},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/", "login failed"
    return c


# ---------- scoring ----------

def test_score_levels():
    lowest = {q["key"]: 0 for q in upitnik.QUESTIONS}
    assert upitnik.score_answers(lowest) == (0, "pocetna")

    highest = {q["key"]: len(q["options"]) - 1 for q in upitnik.QUESTIONS}
    score, level = upitnik.score_answers(highest)
    assert score == upitnik.MAX_SCORE and level == "napredna"

    # boundary: 6 points is the first srednja score
    assert upitnik.score_answers({"staz": 3, "tjedno": 3, "sklekovi": 0,
                                  "cucanj": 0, "ozljede": 0})[1] == "srednja"
    assert upitnik.score_answers({"staz": 3, "tjedno": 2, "sklekovi": 0,
                                  "cucanj": 0, "ozljede": 0})[1] == "pocetna"


# ---------- upitnik flow ----------

def test_upitnik_submit_and_refill():
    uid = make_user("ivan@test.local")
    c = client_for("ivan@test.local")

    answers = {q["key"]: len(q["options"]) - 1 for q in upitnik.QUESTIONS}
    r = c.post("/upitnik", data={**{k: str(v) for k, v in answers.items()},
                                 "goal": "gornji"}, follow_redirects=False)
    assert r.status_code == 303 and "ok=" in r.headers["location"]

    resp = db.get_onboarding(uid)
    assert resp.level == "napredna" and resp.goal == "gornji"
    assert resp.score == upitnik.MAX_SCORE

    # refill replaces, never duplicates
    r = c.post("/upitnik", data={**{q["key"]: "0" for q in upitnik.QUESTIONS},
                                 "goal": "cijelo"}, follow_redirects=False)
    resp = db.get_onboarding(uid)
    assert resp.level == "pocetna" and resp.goal == "cijelo"


def test_upitnik_rejects_incomplete_or_invalid():
    make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    r = c.post("/upitnik", data={"staz": "1", "goal": "gornji"}, follow_redirects=False)
    assert "error" in r.headers["location"]
    assert db.get_onboarding(db.get_user_by_email("ivan@test.local").id) is None

    r = c.post("/upitnik", data={**{q["key"]: "99" for q in upitnik.QUESTIONS},
                                 "goal": "gornji"}, follow_redirects=False)
    assert "error" in r.headers["location"]


# ---------- karton access ----------

def test_karton_self_other_and_trainer():
    ivan = make_user("ivan@test.local")
    make_user("ana@test.local")
    make_user("trener@test.local", is_trainer=True)

    ci = client_for("ivan@test.local")
    assert ci.get("/karton").status_code == 200
    # the /karton/{id} route is trainer-only — even for one's own id
    assert ci.get(f"/karton/{ivan}").status_code == 403
    ca = client_for("ana@test.local")
    assert ca.get(f"/karton/{ivan}").status_code == 403

    ct = client_for("trener@test.local")
    assert ct.get(f"/karton/{ivan}").status_code == 200
    # trainer has no personal karton — bounced to članarine
    r = ct.get("/karton", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/clanarine"


# ---------- upitnik gates online treninzi ----------

def test_assignments_hidden_until_upitnik_filled():
    make_user("trener@test.local", is_trainer=True)
    ivan = make_user("ivan@test.local")
    pid = db.create_program("Online blok A", None)
    db.assign_program(pid, ivan, config.today())

    ci = client_for("ivan@test.local")
    page = ci.get("/treninzi").text
    assert "Online blok A" not in page          # assignment exists, stays hidden
    assert "Ispuni upitnik" in page
    assert ci.get(f"/treninzi/{pid}").status_code == 403   # direct URL too

    ci.post("/upitnik", data={**{q["key"]: "0" for q in upitnik.QUESTIONS},
                              "goal": "cijelo"}, follow_redirects=False)
    page = ci.get("/treninzi").text
    assert "Online blok A" in page
    assert ci.get(f"/treninzi/{pid}").status_code == 200


# ---------- post-training feedback ----------

def attended_session(uid: int, hours_ago: float = 3, duration: int = 60) -> int:
    """A finished termin the user was booked into (booked directly — book()
    rightly refuses past sessions)."""
    sid = db.add_oneoff_session("Grupni trening",
                                datetime.now(config.TZ) - timedelta(hours=hours_ago),
                                duration, 8, None)
    with db.session_scope() as s:
        s.add(Booking(user_id=uid, session_id=sid))
    return sid


def test_feedback_prompted_after_attended_session():
    ivan = make_user("ivan@test.local")
    sid = attended_session(ivan)
    ci = client_for("ivan@test.local")

    assert [s.id for s in db.pending_feedback(ivan)] == [sid]
    assert "Kako je bilo?" in ci.get("/karton").text

    r = ci.post(f"/karton/feedback/{sid}",
                data={"effort": "7", "feeling": "dobro", "note": "Čučanj 3×8 · 60 kg"},
                follow_redirects=False)
    assert "ok=" in r.headers["location"]
    logs = db.training_logs(ivan)
    assert len(logs) == 1
    assert logs[0].session_id == sid and logs[0].effort == 7 and logs[0].feeling == "dobro"
    assert db.pending_feedback(ivan) == []           # prompt is gone

    # one feedback per termin
    r = ci.post(f"/karton/feedback/{sid}", data={"effort": "5"}, follow_redirects=False)
    assert "error" in r.headers["location"]
    assert len(db.training_logs(ivan)) == 1


def test_feedback_needs_attended_and_finished_session():
    ivan = make_user("ivan@test.local")
    make_user("ana@test.local")
    ci = client_for("ivan@test.local")

    # still running (started 10 min ago, lasts 60) -> refused, not yet pending
    running = attended_session(ivan, hours_ago=10 / 60)
    assert db.pending_feedback(ivan) == []
    r = ci.post(f"/karton/feedback/{running}", data={"effort": "5"}, follow_redirects=False)
    assert "error" in r.headers["location"]

    # somebody else's session -> refused
    ana = db.get_user_by_email("ana@test.local").id
    theirs = attended_session(ana)
    r = ci.post(f"/karton/feedback/{theirs}", data={"effort": "5"}, follow_redirects=False)
    assert "error" in r.headers["location"]
    assert db.training_logs(ivan) == []

    # canceled session never asks for feedback
    sid = attended_session(ivan)
    db.set_session_canceled(sid, True)
    assert db.pending_feedback(ivan) == []


def test_feedback_delete_own_only():
    ivan = make_user("ivan@test.local")
    make_user("ana@test.local")
    sid = attended_session(ivan)
    ci = client_for("ivan@test.local")
    ci.post(f"/karton/feedback/{sid}", data={"effort": "6"}, follow_redirects=False)
    entry = db.training_logs(ivan)[0]

    ca = client_for("ana@test.local")
    assert ca.post(f"/karton/log/{entry.id}/delete").status_code == 404
    assert len(db.training_logs(ivan)) == 1

    r = ci.post(f"/karton/log/{entry.id}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert db.training_logs(ivan) == []
    assert [s.id for s in db.pending_feedback(ivan)] == [sid]   # prompt returns
