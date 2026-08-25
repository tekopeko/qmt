"""End-to-end booking tests against a throwaway Postgres DB (qmt_test).

Run:  createdb qmt_test  (once)
      .venv/bin/pytest -q
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local,treći@test.local"
os.environ["TRAINER_EMAIL"] = "trener@test.local"

import pytest
from fastapi.testclient import TestClient

from qmt import auth, config, db
from qmt.models import Base, Booking, SessionTemplate, TrainingSession, User
from qmt.web.app import app


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    yield


def make_user(email: str, is_trainer: bool = False) -> int:
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    if is_trainer:
        with db.session_scope() as s:
            s.get(User, u.id).is_trainer = True
    return u.id


def client_for(email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"email": email, "password": "lozinka123"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/raspored", "login failed"
    return c


def future_session(hours_from_now: float = 24, capacity: int = 8, **kw) -> int:
    starts = datetime.now(config.TZ) + timedelta(hours=hours_from_now)
    return db.add_oneoff_session(kw.get("title", "Test trening"), starts,
                                 kw.get("duration_min", 60), capacity, None)


# ---------- auth ----------

def test_signup_allowlist_and_login():
    c = TestClient(app)
    r = c.post("/signup", data={"name": "X", "email": "stranac@test.local",
                                "password": "lozinka123"}, follow_redirects=False)
    assert "samo+uz+poziv" in r.headers["location"]

    r = c.post("/signup", data={"name": "Ivan", "email": "ivan@test.local",
                                "password": "lozinka123"}, follow_redirects=False)
    assert r.headers["location"] == "/raspored"  # signed in immediately

    # SECURITY: signing up with the trainer's email must NOT grant admin —
    # sign-up proves nothing about ownership, so whoever registered first would
    # otherwise take over the studio. Admin comes only from scripts/make_trainer.
    c2 = TestClient(app)
    c2.post("/signup", data={"name": "T", "email": "trener@test.local",
                             "password": "lozinka123"}, follow_redirects=False)
    u = db.get_user_by_email("trener@test.local")
    assert not u.is_trainer
    assert db.set_trainer("trener@test.local")   # the out-of-band grant works
    assert db.get_user_by_email("trener@test.local").is_trainer


def test_wrong_password_rejected():
    make_user("ivan@test.local")
    c = TestClient(app)
    r = c.post("/login", data={"email": "ivan@test.local", "password": "kriva"},
               follow_redirects=False)
    assert "error" in r.headers["location"]


def test_admin_gated():
    make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    assert c.get("/admin").status_code == 403
    tid = make_user("trener@test.local", is_trainer=True)
    ct = client_for("trener@test.local")
    assert ct.get("/admin").status_code == 200


# ---------- booking rules ----------

def test_book_and_cancel_roundtrip():
    uid = make_user("ivan@test.local")
    sid = future_session(hours_from_now=48)
    c = client_for("ivan@test.local")

    r = c.post(f"/book/{sid}", data={}, follow_redirects=False)
    assert "error" not in r.headers["location"]
    assert db.user_booking_ids(uid, [sid]) == {sid}

    # double-book refused
    r = c.post(f"/book/{sid}", data={}, follow_redirects=False)
    assert "error" in r.headers["location"]

    r = c.post(f"/cancel/{sid}", data={}, follow_redirects=False)
    assert "error" not in r.headers["location"]
    assert db.user_booking_ids(uid, [sid]) == set()


def test_cancel_cutoff_enforced():
    uid = make_user("ivan@test.local")
    sid = future_session(hours_from_now=1)      # inside the 3h cutoff
    db.book(uid, sid)
    with pytest.raises(db.BookingError, match="najkasnije"):
        db.cancel_booking(uid, sid)


def test_past_and_canceled_sessions_refuse_booking():
    uid = make_user("ivan@test.local")
    past = future_session(hours_from_now=-2)
    with pytest.raises(db.BookingError, match="prošao"):
        db.book(uid, past)
    sid = future_session(hours_from_now=24)
    db.set_session_canceled(sid, True)
    with pytest.raises(db.BookingError, match="otkazan"):
        db.book(uid, sid)


def test_horizon_enforced():
    uid = make_user("ivan@test.local")
    sid = future_session(hours_from_now=24 * (config.BOOKING_HORIZON_DAYS + 3))
    with pytest.raises(db.BookingError, match="unaprijed"):
        db.book(uid, sid)


def test_capacity_race_no_overbooking():
    """THE invariant: 12 users grabbing 3 spots concurrently -> exactly 3 win."""
    sid = future_session(hours_from_now=24, capacity=3)
    uids = [make_user(f"u{i}.race@test.local") for i in range(12)]
    # (emails not on the allowlist — irrelevant, we book via db directly)
    results = []

    def grab(uid):
        try:
            db.book(uid, sid)
            results.append("ok")
        except db.BookingError:
            results.append("full")

    threads = [threading.Thread(target=grab, args=(u,)) for u in uids]
    for t in threads: t.start()
    for t in threads: t.join()

    assert results.count("ok") == 3, f"overbooked: {results}"
    with db.session_scope() as s:
        from sqlalchemy import func, select
        n = s.scalar(select(func.count()).select_from(Booking).where(Booking.session_id == sid))
    assert n == 3


# ---------- timetable materialization ----------

def test_materialize_is_idempotent_and_concurrent_safe():
    with db.session_scope() as s:
        s.add(SessionTemplate(title="Grupni", weekday=0, start_min=18 * 60))
    monday = config.today() + timedelta(days=(7 - config.today().weekday()))

    threads = [threading.Thread(target=db.materialize_week, args=(monday,)) for _ in range(6)]
    for t in threads: t.start()
    for t in threads: t.join()
    db.materialize_week(monday)                 # and once more

    with db.session_scope() as s:
        from sqlalchemy import func, select
        n = s.scalar(select(func.count()).select_from(TrainingSession))
    assert n == 1, f"materialized {n} sessions for one template occurrence"


def test_calendar_renders_sessions():
    make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    with db.session_scope() as s:
        s.add(SessionTemplate(title="Grupni trening", weekday=0, start_min=18 * 60))
    monday = config.today() + timedelta(days=(7 - config.today().weekday()))
    page = c.get(f"/raspored?week={monday.isoformat()}").text
    assert "Grupni trening" in page
    assert "Rezerviraj" in page


def test_trainer_sees_roster():
    make_user("trener@test.local", is_trainer=True)
    uid = make_user("ivan@test.local")
    sid = future_session(hours_from_now=24)
    db.book(uid, sid)
    ct = client_for("trener@test.local")
    page = ct.get(f"/admin/session/{sid}").text
    assert "ivan@test.local" in page


def test_booking_error_is_visible_even_without_week_param():
    """Regression: back='/' once produced '/&error=...' — a malformed query string,
    so the refusal message silently never displayed."""
    make_user("ivan@test.local")
    sid = future_session(hours_from_now=24, capacity=1)
    other = make_user("ana@test.local")
    db.book(other, sid)                          # fill the only spot
    c = client_for("ivan@test.local")
    r = c.post(f"/book/{sid}", data={}, follow_redirects=False)
    loc = r.headers["location"]
    assert loc.startswith("/raspored?error="), loc   # parseable query, message shown


def test_materialize_clamped_to_booking_window():
    """A client walking ?week= must not mint rows for arbitrary past/future weeks."""
    with db.session_scope() as s:
        s.add(SessionTemplate(title="Grupni", weekday=0, start_min=18 * 60))
    this_monday = config.today() - timedelta(days=config.today().weekday())
    from sqlalchemy import func, select
    for monday, allowed in [
        (this_monday, True),
        (this_monday - timedelta(days=7), False),           # past week
        (this_monday + timedelta(days=7 * 60), False),      # far future
    ]:
        db.materialize_week(monday)
    with db.session_scope() as s:
        n = s.scalar(select(func.count()).select_from(TrainingSession))
    assert n == 1, f"expected only the current week materialized, got {n}"


def test_canceled_session_booking_can_be_dropped_inside_cutoff():
    """The cutoff protects the trainer's planning — meaningless once THEY canceled."""
    uid = make_user("ivan@test.local")
    sid = future_session(hours_from_now=1)      # inside the 3h cutoff
    db.book(uid, sid)
    db.set_session_canceled(sid, True)
    db.cancel_booking(uid, sid)                 # must NOT raise
    assert db.user_booking_ids(uid, [sid]) == set()


def test_malformed_week_param_falls_back():
    make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    assert c.get("/raspored?week=not-a-date").status_code == 200
    assert c.get("/raspored?week=9999-99-99").status_code == 200


# ---------- template editing (the trainer reshapes the schedule at will) ----------

def _materialized_next_week():
    monday = config.today() + timedelta(days=(7 - config.today().weekday()))
    db.materialize_week(monday)
    return monday


def test_template_edit_recalculates_future_unbooked_sessions():
    with db.session_scope() as s:
        s.add(SessionTemplate(title="Grupni", weekday=0, start_min=18 * 60, capacity=8))
        s.flush(); tid = s.scalar(__import__("sqlalchemy").select(SessionTemplate.id))
    _materialized_next_week()
    assert db.update_template(tid, "Grupni novi", 1, 17 * 60, 60, 10, None)
    monday = _materialized_next_week()          # re-view triggers re-materialization
    with db.session_scope() as s:
        from sqlalchemy import select
        rows = s.scalars(select(TrainingSession)).all()
        assert len(rows) == 1, [r.starts_at for r in rows]
        sess = rows[0]
    assert sess.title == "Grupni novi" and sess.capacity == 10
    assert sess.starts_at.astimezone(config.TZ).weekday() == 1
    assert sess.starts_at.astimezone(config.TZ).hour == 17


def test_template_edit_leaves_booked_sessions_alone():
    uid = make_user("ivan@test.local")
    with db.session_scope() as s:
        s.add(SessionTemplate(title="Grupni", weekday=0, start_min=18 * 60))
        s.flush()
        from sqlalchemy import select
        tid = s.scalar(select(SessionTemplate.id))
    _materialized_next_week()
    with db.session_scope() as s:
        from sqlalchemy import select
        sid = s.scalar(select(TrainingSession.id))
    db.book(uid, sid)
    db.update_template(tid, "Grupni", 0, 19 * 60, 60, 8, None)   # move by an hour
    _materialized_next_week()
    with db.session_scope() as s:
        from sqlalchemy import select
        rows = s.scalars(select(TrainingSession).order_by(TrainingSession.starts_at)).all()
    # booked 18:00 session survives untouched; new 19:00 one materializes beside it
    assert len(rows) == 2
    assert rows[0].id == sid and rows[0].starts_at.astimezone(config.TZ).hour == 18
    assert rows[1].starts_at.astimezone(config.TZ).hour == 19
    assert db.user_booking_ids(uid, [sid]) == {sid}


def test_template_delete_prunes_unbooked_keeps_booked():
    uid = make_user("ivan@test.local")
    with db.session_scope() as s:
        s.add(SessionTemplate(title="Grupni", weekday=0, start_min=18 * 60))
        s.add(SessionTemplate(title="Jutarnji", weekday=2, start_min=7 * 60))
        s.flush()
        from sqlalchemy import select
        tids = list(s.scalars(select(SessionTemplate.id).order_by(SessionTemplate.id)))
    _materialized_next_week()
    with db.session_scope() as s:
        from sqlalchemy import select
        sid_booked = s.scalar(select(TrainingSession.id)
                              .where(TrainingSession.template_id == tids[0]))
    db.book(uid, sid_booked)
    assert db.delete_template(tids[0])   # has a booked session -> session survives
    assert db.delete_template(tids[1])   # unbooked -> session pruned
    with db.session_scope() as s:
        from sqlalchemy import select
        rows = s.scalars(select(TrainingSession)).all()
    assert len(rows) == 1 and rows[0].id == sid_booked
    assert rows[0].template_id is None   # orphaned but alive, bookings intact


def test_landing_is_public_and_links_to_booking():
    c = TestClient(app)
    r = c.get("/")                               # no login required
    assert r.status_code == 200
    assert "Rezerviraj termin" in r.text
    assert "/raspored" in r.text
    # calendar itself still requires auth
    r = c.get("/raspored", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
