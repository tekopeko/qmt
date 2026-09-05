"""End-to-end booking tests against a throwaway Postgres DB (qmt_test).

Run:  createdb qmt_test  (once)
      .venv/bin/pytest -q
"""

from __future__ import annotations

import os
import threading
from datetime import date, datetime, timedelta

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local,treći@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

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


def make_user(email: str, is_trainer: bool = False,
              plans: tuple[str, ...] = ("grupni",)) -> int:
    """Default users can book grupni sessions — booking is plan-gated.
    Pass plans=() for a user with no membership."""
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)   # login refuses unverified accounts
    # complete profile — an incomplete one bounces login to /profil
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
    assert r.status_code == 303 and r.headers["location"] == "/", "login failed"
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
    assert r.status_code == 200                   # verify page, NOT signed in
    assert "Provjeri email" in r.text or "Link (dev)" in r.text

    # SECURITY: signing up with the trainer's email must NOT grant admin —
    # sign-up proves nothing about ownership, so whoever registered first would
    # otherwise take over the studio. Admin comes only from scripts/make_trainer.
    c2 = TestClient(app)
    c2.post("/signup", data={"name": "T", "email": "trener@test.local",
                             "password": "lozinka123"}, follow_redirects=False)
    u = db.get_user_by_email("trener@test.local")
    assert not u.email_verified
    assert not u.is_trainer
    assert db.set_trainer("trener@test.local")   # the out-of-band grant works
    assert db.get_user_by_email("trener@test.local").is_trainer


def test_signup_stays_closed_unless_explicitly_opened(monkeypatch):
    """Registration must fail CLOSED. An empty or missing ALLOWED_EMAILS is not
    an invitation to the whole internet — only SIGNUP_OPEN is."""
    monkeypatch.delenv("SIGNUP_OPEN", raising=False)
    monkeypatch.setenv("ALLOWED_EMAILS", "")          # nothing configured at all
    assert not config.email_allowed("stranac@example.com")
    c = TestClient(app)
    r = c.post("/signup", data={"name": "X", "email": "stranac@example.com",
                                "password": "lozinka123"}, follow_redirects=False)
    assert "samo+uz+poziv" in r.headers["location"]
    assert db.get_user_by_email("stranac@example.com") is None
    assert "samo pozvani" in c.get("/signup").text

    monkeypatch.setenv("SIGNUP_OPEN", "true")         # the explicit switch
    assert config.email_allowed("stranac@example.com")
    r = c.post("/signup", data={"name": "X", "email": "stranac@example.com",
                                "password": "lozinka123"}, follow_redirects=False)
    assert r.status_code == 200                       # verify-email page
    assert db.get_user_by_email("stranac@example.com") is not None
    assert "samo pozvani" not in c.get("/signup").text   # the copy follows the flag


def test_logout_lands_on_the_landing_page():
    make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    r = c.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    # and the session really is gone
    assert c.get("/raspored", follow_redirects=False).headers["location"] == "/login?next=/raspored"


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


def test_landing_offers_only_what_the_visitor_can_actually_do():
    """A guest can neither book nor register without an account, so the hero
    sells the prices and the account — never a booking they'd be refused."""
    c = TestClient(app)
    r = c.get("/")                               # no login required
    assert r.status_code == 200
    assert "Pogledaj cjenik" in r.text
    assert "/signup" in r.text                   # the account they need first
    assert "Rezerviraj termin" not in r.text     # would dead-end at the plan gate

    # calendar itself still requires auth
    r = c.get("/raspored", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=/raspored"


def test_landing_hero_follows_the_membership():
    make_user("ivan@test.local", plans=("grupni",))
    make_user("ana@test.local", plans=())
    make_user("sara@test.local", plans=("online",))      # not a bookable kind

    page = client_for("ivan@test.local").get("/").text
    assert "Rezerviraj termin" in page                   # can book, so it is offered

    for email in ("ana@test.local", "sara@test.local"):
        page = client_for(email).get("/").text
        assert "Pogledaj cjenik" in page
        assert "Rezerviraj termin" not in page, email    # no bookable plan


def test_cjenik_is_reachable_without_hunting_for_it():
    make_user("ana@test.local", plans=())
    ca = client_for("ana@test.local")
    assert '/cjenik"' in ca.get("/raspored").text        # nav tab + the empty state
    assert "Pogledaj cjenik" in ca.get("/raspored").text
    assert '/cjenik"' in TestClient(app).get("/").text   # and for a logged-out guest

    # the trainer's nav is already full and they do not buy plans
    make_user("trener@test.local", is_trainer=True, plans=())
    assert '/cjenik"' not in client_for("trener@test.local").get("/raspored").text


def test_plan_gate_offers_the_price_instead_of_a_dead_end():
    make_user("ana@test.local", plans=())                # no membership at all
    sid = future_session()
    ca = client_for("ana@test.local")
    r = ca.post(f"/book/{sid}", data={"week": ""}, follow_redirects=False)
    loc = r.headers["location"]
    assert "error=" in loc
    assert "cta=grupni" in loc                          # straight at that plan
    assert "javi+se+treneru" not in loc                  # the old dead end is gone
    # and the alert renders it as a button
    assert "Pogledaj cjenik" in ca.get(loc).text


def test_login_returns_to_the_page_that_bounced_you():
    make_user("ivan@test.local")
    c = TestClient(app)
    r = c.post("/login", data={"email": "ivan@test.local", "password": "lozinka123",
                               "next": "/raspored"}, follow_redirects=False)
    assert r.headers["location"] == "/raspored"


def test_login_next_cannot_be_an_open_redirect():
    make_user("ivan@test.local")
    for evil in ("https://evil.example", "//evil.example", "javascript:alert(1)"):
        c = TestClient(app)
        r = c.post("/login", data={"email": "ivan@test.local", "password": "lozinka123",
                                   "next": evil}, follow_redirects=False)
        assert r.headers["location"] == "/", evil


# ---------- korisnici (owner-only roster + trainer grants) ----------

def test_owner_roster_and_trainer_grants():
    """Owner (OWNER_EMAIL account) sees all users and grants/revokes trainer.
    A mere trainer is NOT the owner and gets 403 — roles are the owner's alone."""
    make_user("trener@test.local")               # email matches OWNER_EMAIL -> owner
    ivan = make_user("ivan@test.local")
    co = client_for("trener@test.local")

    page = co.get("/korisnici").text
    assert "ivan@test.local" in page and "vlasnik" in page

    # promote ivan -> he gains trainer powers
    r = co.post(f"/korisnici/{ivan}/trainer", data={}, follow_redirects=False)
    assert "ok=" in r.headers["location"]
    ci = client_for("ivan@test.local")
    assert ci.get("/admin").status_code == 200   # trainer now
    # ...but still NOT owner: no roster access
    assert ci.get("/korisnici").status_code == 403
    assert ci.post(f"/korisnici/{ivan}/trainer", data={}).status_code == 403

    # revoke
    r = co.post(f"/korisnici/{ivan}/trainer", data={"revoke": "1"}, follow_redirects=False)
    assert "ok=" in r.headers["location"]
    ci2 = client_for("ivan@test.local")
    assert ci2.get("/admin").status_code == 403


def test_owner_cannot_be_revoked_and_passes_trainer_gates():
    uid = make_user("trener@test.local")         # owner WITHOUT is_trainer flag
    co = client_for("trener@test.local")
    assert co.get("/admin").status_code == 200   # owner passes trainer gates
    r = co.post(f"/korisnici/{uid}/trainer", data={"revoke": "1"}, follow_redirects=False)
    assert "error=" in r.headers["location"]     # refuses to strip the owner


# ---------- članarine (membership plans gate booking) ----------

def test_booking_requires_matching_active_plan():
    uid = make_user("ivan@test.local", plans=())
    sid = future_session(hours_from_now=24)                    # kind: grupni
    with pytest.raises(db.BookingError, match="članarina"):
        db.book(uid, sid)
    db.record_payment(uid, "individualni")                     # wrong plan
    with pytest.raises(db.BookingError, match="članarina"):
        db.book(uid, sid)
    db.record_payment(uid, "grupni")
    db.book(uid, sid)                                          # now allowed


def test_plan_kinds_are_separate():
    uid = make_user("ana@test.local", plans=("rehabilitacija",))
    sid = db.add_oneoff_session("Rehabilitacija",
                                datetime.now(config.TZ) + timedelta(hours=24),
                                60, 1, None, kind="rehabilitacija")
    db.book(uid, sid)
    grupni_sid = future_session(hours_from_now=25)
    with pytest.raises(db.BookingError, match="članarina"):
        db.book(uid, grupni_sid)


def test_expired_plan_blocks_after_grace_week():
    from qmt.models import Membership
    uid = make_user("ivan@test.local")
    sid = future_session(hours_from_now=24)
    today = config.today()

    def backdate(days: int):
        with db.session_scope() as s:
            m = s.scalar(db.select(Membership).where(Membership.user_id == uid))
            m.next_payment = today - timedelta(days=days)

    backdate(8)                                  # dospijeće (grace 7d) passed
    with pytest.raises(db.BookingError, match="članarina"):
        db.book(uid, sid)
    backdate(7)                                  # dospijeće is exactly today
    db.book(uid, sid)


def test_record_payment_date_math():
    uid = make_user("ivan@test.local", plans=())
    today = config.today()

    m = db.record_payment(uid, "grupni")         # first payment: month from today
    assert m.paid_on == today
    assert m.next_payment == db._add_month(today)
    assert m.dospijece == m.next_payment + timedelta(days=7)

    first_due = m.next_payment                   # paying early extends from the
    m2 = db.record_payment(uid, "grupni")        # due date, never shortens
    assert m2.next_payment == db._add_month(first_due)

    from qmt.models import Membership
    with db.session_scope() as s:                # long-lapsed plan restarts
        row = s.scalar(db.select(Membership).where(Membership.user_id == uid))
        row.next_payment = today - timedelta(days=40)
    m3 = db.record_payment(uid, "grupni")
    assert m3.next_payment == db._add_month(today)


def test_add_month_clamps_to_month_length():
    from datetime import date
    assert db._add_month(date(2026, 1, 31)) == date(2026, 2, 28)
    assert db._add_month(date(2026, 12, 15)) == date(2027, 1, 15)
    assert db._add_month(date(2028, 1, 31)) == date(2028, 2, 29)   # leap year


def test_clanarine_page_trainer_only_and_records_payment():
    make_user("trener@test.local", is_trainer=True, plans=())
    uid = make_user("ivan@test.local", plans=())

    c = client_for("ivan@test.local")
    assert c.get("/clanarine").status_code == 403

    ct = client_for("trener@test.local")
    assert ct.get("/clanarine").status_code == 200
    r = ct.post(f"/clanarine/{uid}/uplata", data={"plan": "grupni"},
                follow_redirects=False)
    assert r.status_code == 303 and "ok=" in r.headers["location"]
    assert db.active_plan_kinds(uid) == {"grupni"}

    r = ct.post(f"/clanarine/{uid}/ukloni", data={"plan": "grupni"},
                follow_redirects=False)
    assert r.status_code == 303
    assert db.active_plan_kinds(uid) == set()


def test_calendar_shows_membership_gate():
    make_user("ana@test.local", plans=())        # no plan at all
    future_session(hours_from_now=1)             # today, this week
    c = client_for("ana@test.local")
    page = c.get("/raspored").text
    assert "Nemaš aktivnu članarinu" in page


def test_cjenik_public_and_landing_plan_cta_states():
    page = TestClient(app).get("/").text
    assert "Odaberi plan" in page                       # hover CTA on service cards
    assert TestClient(app).get("/cjenik").status_code == 200

    make_user("ivan@test.local")                        # default plan: grupni
    ci = client_for("ivan@test.local")
    assert "Aktivna članarina" in ci.get("/").text      # owned state on landing
    assert "Aktivna članarina" in ci.get("/cjenik").text


def test_payment_ledger_accumulates_and_stats():
    make_user("trener@test.local", is_trainer=True, plans=())
    ivan = make_user("ivan@test.local", plans=())
    ct = client_for("trener@test.local")

    ct.post(f"/clanarine/{ivan}/uplata", data={"plan": "grupni", "method": "kartica"},
            follow_redirects=False)
    ct.post(f"/clanarine/{ivan}/uplata", data={"plan": "grupni"},   # renewal, cash
            follow_redirects=False)

    from qmt.models import Membership, Payment
    with db.session_scope() as s:
        from sqlalchemy import select
        payments = list(s.scalars(select(Payment).where(Payment.user_id == ivan)
                                  .order_by(Payment.id)))
        memberships = list(s.scalars(select(Membership).where(Membership.user_id == ivan)))
    # ledger accumulates; membership stays a single current-cycle row
    assert [(p.plan, p.method) for p in payments] == [("grupni", "kartica"),
                                                      ("grupni", "gotovina")]
    assert len(memberships) == 1

    stats = db.payment_stats()
    assert stats["months"][0]["per_plan"]["grupni"] == 2   # current month, newest first
    assert stats["method_totals"] == {"kartica": 1, "gotovina": 1}

    # bogus method refused, nothing written
    r = ct.post(f"/clanarine/{ivan}/uplata", data={"plan": "grupni", "method": "bitcoin"},
                follow_redirects=False)
    assert r.status_code == 400

    # statistika is OWNER-only: trainer-owner passes, a client does not
    assert ct.get("/statistika").status_code == 200
    assert client_for("ivan@test.local").get("/statistika").status_code == 403


def test_profil_shows_membership_overview_and_billing_history():
    uid = make_user("ivan@test.local", plans=("grupni",))   # 1st uplata: gotovina
    db.record_payment(uid, "grupni", "kartica")             # renewal
    from qmt.models import Membership
    with db.session_scope() as s:
        from sqlalchemy import select
        m = s.scalar(select(Membership).where(Membership.user_id == uid))
        due, expiry = m.next_payment, m.dospijece

    page = client_for("ivan@test.local").get("/profil").text
    assert "Moja članarina" in page and "Grupni trening" in page
    assert "aktivna" in page
    assert due.strftime("%-d.%-m.%Y.") in page              # sljedeća uplata
    assert expiry.strftime("%-d.%-m.%Y.") in page           # dospijeće
    # billing history lists BOTH uplate with their methods
    assert "Povijest plaćanja" in page
    assert "Gotovina" in page and "Kartica" in page
    # an active plan is a door to what it unlocks
    assert 'href="/raspored">Rezerviraj termin' in page

    db.record_payment(uid, "online")
    page = client_for("ivan@test.local").get("/profil").text
    assert 'href="/treninzi">Otvori online treninge' in page


def test_profil_without_plan_points_to_cjenik():
    make_user("ana@test.local", plans=())
    page = client_for("ana@test.local").get("/profil").text
    assert "Nemaš aktivnu članarinu" in page and "/cjenik" in page
    assert "Još nema evidentiranih uplata" in page
