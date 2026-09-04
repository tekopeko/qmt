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


def make_user(email: str, is_trainer: bool = False,
              plans: tuple[str, ...] = ("online",), complete: bool = True) -> int:
    from datetime import date

    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    if complete:  # incomplete profiles bounce login to /profil
        db.update_profile(u.id, email.split("@")[0], "Test", date(1990, 1, 1), "")
    if is_trainer:
        with db.session_scope() as s:
            s.get(User, u.id).is_trainer = True
    for plan in plans:
        db.record_payment(u.id, plan)
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

def test_programs_hidden_until_upitnik_filled():
    make_user("trener@test.local", is_trainer=True)
    make_user("ivan@test.local")                # has the online plan, no upitnik
    pid = db.create_program("Online blok A", None, "pocetna", "cijelo")

    ci = client_for("ivan@test.local")
    page = ci.get("/treninzi").text
    assert "Online blok A" not in page          # programme exists, stays hidden
    assert "Ispuni upitnik" in page
    assert ci.get(f"/treninzi/{pid}").status_code == 403   # direct URL too

    # zeros -> pocetna; goal cijelo -> the combo above matches automatically
    ci.post("/upitnik", data={**{q["key"]: "0" for q in upitnik.QUESTIONS},
                              "goal": "cijelo"}, follow_redirects=False)
    page = ci.get("/treninzi").text
    assert "Online blok A" in page
    assert ci.get(f"/treninzi/{pid}").status_code == 200


# ---------- online tab gated on the plan ----------

def test_online_tab_gated_without_plan():
    make_user("trener@test.local", is_trainer=True, plans=())
    ivan = make_user("ivan@test.local", plans=())      # no online plan
    pid = db.create_program("Online blok B", None, "pocetna", "cijelo")

    ci = client_for("ivan@test.local")
    page = ci.get("/raspored").text
    assert "Online treninzi" not in page               # tab gone from the nav
    page = ci.get("/treninzi").text                    # direct URL: gate card
    assert "dio zasebne članarine" in page and "Online blok B" not in page
    assert ci.get(f"/treninzi/{pid}").status_code == 403
    r = ci.get("/upitnik", follow_redirects=False)     # upitnik gated too
    assert r.status_code == 303 and "error" in r.headers["location"]

    db.record_payment(ivan, "online")                  # plan paid -> tab back
    assert "Online treninzi" in ci.get("/raspored").text
    assert "Ispuni upitnik" in ci.get("/treninzi").text


# ---------- profil ----------

def test_incomplete_profile_bounces_login_then_saves():
    make_user("ivan@test.local", plans=(), complete=False)
    c = TestClient(app)
    r = c.post("/login", data={"email": "ivan@test.local", "password": "lozinka123"},
               follow_redirects=False)
    assert r.headers["location"] == "/profil?dopuni=1"

    # a half-filled form is still incomplete -> stays on the form
    r = c.post("/profil", data={"name": "Ivan", "last_name": "Horvat"},
               follow_redirects=False)
    assert r.headers["location"].startswith("/profil?ok=")

    # finishing the entry form drops them on the landing page, not back here
    r = c.post("/profil", data={"name": "Ivan", "last_name": "Horvat",
                                "birth_date": "1992-04-01", "phone": "091 111 222"},
               follow_redirects=False)
    assert r.headers["location"].startswith("/?ok=")
    u = db.get_user_by_email("ivan@test.local")
    assert u.full_name == "Ivan Horvat" and u.profile_complete
    assert u.birth_date.isoformat() == "1992-04-01"

    # a LATER edit is not the entry pass — it stays on the profile page
    r = c.post("/profil", data={"name": "Ivan", "last_name": "Horvat",
                                "birth_date": "1992-04-01", "phone": "091 222 333"},
               follow_redirects=False)
    assert r.headers["location"].startswith("/profil?ok=")

    r = c.post("/login", data={"email": "ivan@test.local", "password": "lozinka123"},
               follow_redirects=False)
    assert r.headers["location"] == "/"                # complete -> normal login

    # garbage birth date refused
    r = c.post("/profil", data={"name": "Ivan", "last_name": "Horvat",
                                "birth_date": "3000-01-01"}, follow_redirects=False)
    assert "error" in r.headers["location"]


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


def test_login_prompts_for_owed_feedback_once():
    ivan = make_user("ivan@test.local")
    sid = attended_session(ivan)
    ci = client_for("ivan@test.local")           # logging in arms the prompt

    first = ci.get("/").text
    assert 'id="fbPrompt"' in first              # asked on the page the login landed on
    assert "Grupni trening" in first             # and it names the termin
    assert "/karton#osvrti" in first             # primary action goes to the forms

    assert 'id="fbPrompt"' not in ci.get("/").text   # exactly once per login

    # nothing owed -> the next login says nothing
    ci.post(f"/karton/feedback/{sid}", data={"effort": "6"}, follow_redirects=False)
    assert 'id="fbPrompt"' not in client_for("ivan@test.local").get("/").text


def test_login_straight_to_karton_skips_the_prompt():
    ivan = make_user("ivan@test.local")
    attended_session(ivan)
    c = TestClient(app)
    r = c.post("/login", data={"email": "ivan@test.local", "password": "lozinka123",
                               "next": "/karton"}, follow_redirects=False)
    assert r.headers["location"] == "/karton"

    page = c.get("/karton").text
    assert 'id="fbPrompt"' not in page           # the forms are already on screen
    assert "Kako je bilo?" in page
    assert 'id="fbPrompt"' not in c.get("/").text    # and it doesn't ambush the next page


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


def test_feedback_is_editable_by_its_author_only():
    ivan = make_user("ivan@test.local")
    make_user("ana@test.local")
    sid = attended_session(ivan)
    ci = client_for("ivan@test.local")
    ci.post(f"/karton/feedback/{sid}",
            data={"effort": "7", "feeling": "dobro", "note": "Prvi zapis"},
            follow_redirects=False)
    entry = db.training_logs(ivan)[0]

    # the osvrt is readable in the dnevnik, and carries its own editor
    page = ci.get("/karton").text
    assert "Prvi zapis" in page
    assert f'id="log-{entry.id}"' in page
    assert f"/karton/log/{entry.id}/edit" in page

    r = ci.post(f"/karton/log/{entry.id}/edit",
                data={"effort": "4", "feeling": "", "note": "Ipak lakše"},
                follow_redirects=False)
    assert "ok=" in r.headers["location"]
    edited = db.training_logs(ivan)[0]
    assert (edited.effort, edited.feeling, edited.note) == (4, None, "Ipak lakše")
    assert edited.session_id == sid and edited.date == entry.date   # facts stay put

    # somebody else's osvrt, and nonsense values, are both refused
    ca = client_for("ana@test.local")
    ca.post(f"/karton/log/{entry.id}/edit", data={"effort": "9", "note": "tuđe"},
            follow_redirects=False)
    r = ci.post(f"/karton/log/{entry.id}/edit", data={"effort": "44"},
                follow_redirects=False)
    assert "error" in r.headers["location"]
    still = db.training_logs(ivan)[0]
    assert (still.effort, still.note) == (4, "Ipak lakše")


def test_absence_is_logged_without_touching_the_shared_termin():
    ivan = make_user("ivan@test.local")
    ana = make_user("ana@test.local")
    sid = attended_session(ivan)
    with db.session_scope() as s:                     # ana was in the same termin
        s.add(Booking(user_id=ana, session_id=sid))
    ci = client_for("ivan@test.local")

    # every past termin is in the dnevnik, osvrt or not
    page = ci.get("/karton").text
    assert f'action="/karton/absent/{sid}"' in page

    r = ci.post(f"/karton/absent/{sid}", follow_redirects=False)
    assert "ok=" in r.headers["location"]
    entry = db.training_logs(ivan)[0]
    assert entry.absent and entry.session_id == sid
    assert entry.effort is None and entry.feeling is None
    assert db.pending_feedback(ivan) == []            # it stops asking

    with db.session_scope() as s:                     # the termin itself is untouched
        assert not s.get(db.TrainingSession, sid).canceled
    assert [x.id for x in db.pending_feedback(ana)] == [sid]   # ana is still asked

    # one row per termin: an osvrt can't follow an absence, and vice versa
    r = ci.post(f"/karton/feedback/{sid}", data={"effort": "5"}, follow_redirects=False)
    assert "error" in r.headers["location"]
    r = ci.post(f"/karton/absent/{sid}", follow_redirects=False)
    assert "error" in r.headers["location"]
    # an absence has nothing to edit — undo it by deleting, then write the osvrt
    assert not db.update_training_log(entry.id, ivan, 5, None, "ipak sam bio")
    ci.post(f"/karton/log/{entry.id}/delete", follow_redirects=False)
    assert [x.id for x in db.pending_feedback(ivan)] == [sid]


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
