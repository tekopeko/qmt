"""Karton + onboarding upitnik: scoring, access control, diary ownership."""

from __future__ import annotations

import os
from datetime import timedelta

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import pytest
from fastapi.testclient import TestClient

from qmt import auth, config, db, upitnik
from qmt.models import Base, User
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


# ---------- diary ----------

def test_log_add_and_delete_own_only():
    ivan = make_user("ivan@test.local")
    make_user("ana@test.local")
    ci = client_for("ivan@test.local")

    today = config.today()
    r = ci.post("/karton/log", data={"day": today.isoformat(), "effort": "7",
                                     "note": "Čučanj 3×8 · 60 kg"}, follow_redirects=False)
    assert "ok=" in r.headers["location"]
    logs = db.training_logs(ivan)
    assert len(logs) == 1 and logs[0].effort == 7

    # future date refused — the diary records what happened
    r = ci.post("/karton/log", data={"day": (today + timedelta(days=2)).isoformat(),
                                     "note": "x"}, follow_redirects=False)
    assert "error" in r.headers["location"]

    # ana cannot delete ivan's entry
    ca = client_for("ana@test.local")
    assert ca.post(f"/karton/log/{logs[0].id}/delete").status_code == 404
    assert len(db.training_logs(ivan)) == 1

    r = ci.post(f"/karton/log/{logs[0].id}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert db.training_logs(ivan) == []
