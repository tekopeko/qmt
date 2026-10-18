"""End-to-end booking tests against a throwaway Postgres DB (qmt_test).

Run:  createdb qmt_test  (once)
      .venv/bin/pytest -q
"""

from __future__ import annotations

import os
import re
import threading
from datetime import date, datetime, timedelta
from html import unescape

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
    an invitation to the whole internet — only SIGNUP_MODE=open is."""
    monkeypatch.setenv("SIGNUP_MODE", "invite")
    monkeypatch.setenv("ALLOWED_EMAILS", "")          # nothing configured at all
    assert not config.email_allowed("stranac@example.com")
    c = TestClient(app)
    r = c.post("/signup", data={"name": "X", "email": "stranac@example.com",
                                "password": "lozinka123"}, follow_redirects=False)
    assert "samo+uz+poziv" in r.headers["location"]
    assert db.get_user_by_email("stranac@example.com") is None
    assert "samo pozvani" in c.get("/signup").text

    monkeypatch.setenv("SIGNUP_MODE", "open")         # the explicit switch
    assert config.email_allowed("stranac@example.com")
    r = c.post("/signup", data={"name": "X", "email": "stranac@example.com",
                                "password": "lozinka123"}, follow_redirects=False)
    assert r.status_code == 200                       # verify-email page
    assert db.get_user_by_email("stranac@example.com") is not None
    assert "samo pozvani" not in c.get("/signup").text   # the copy follows the flag


def test_signup_is_closed_by_default_and_members_still_log_in(monkeypatch):
    """Production runs with SIGNUP_MODE unset, i.e. closed (28.9.2026): nobody
    opens an account, not even an invited email, and no page offers to. Everyone
    who already has an account logs in exactly as before."""
    for unset_or_junk in (None, "", "true", "otvoreno"):   # anything unknown = closed
        if unset_or_junk is None:
            monkeypatch.delenv("SIGNUP_MODE", raising=False)
        else:
            monkeypatch.setenv("SIGNUP_MODE", unset_or_junk)
        assert config.signup_mode() == "closed"
        assert not config.email_allowed("ivan@test.local")   # invited, still no
    monkeypatch.delenv("SIGNUP_MODE", raising=False)

    c = TestClient(app)
    r = c.post("/signup", data={"name": "Ivan", "email": "ivan@test.local",
                                "password": "lozinka123"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/signup"
    assert db.get_user_by_email("ivan@test.local") is None
    page = c.get("/signup").text
    assert "trenutno zatvorena" in page and 'action="/signup"' not in page

    for path in ("/", "/login", "/prehrana", "/forgot"):
        page = c.get(path).text
        assert 'href="/signup"' not in page and 'data-auth="signup"' not in page, path
        assert 'id="authSignup"' not in page and 'class="auth-tabs"' not in page, path
    assert "trenutno zatvorena" in c.get("/login").text
    page = c.get("/").text
    assert 'data-auth="login"' in page                  # Prijava stays
    assert 'href="/#kontakt" class="dark">Kontakt' in page and 'class="cta" data-auth="login">Prijava' in page   # the guest's bar

    make_user("ana@test.local")                         # an existing member...
    client_for("ana@test.local")                        # ...logs in as always


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

    # the 12 h cutoff through the route the calendar's ✕ posts to
    from urllib.parse import unquote
    early, late = future_session(hours_from_now=13), future_session(hours_from_now=11)
    db.book(uid, early)
    db.book(uid, late)
    r = c.post(f"/cancel/{early}", data={"week": ""}, follow_redirects=False)
    assert r.status_code == 303 and "ok=" in r.headers["location"]
    assert db.user_booking_ids(uid, [early]) == set()
    r = c.post(f"/cancel/{late}", data={"week": ""}, follow_redirects=False)
    assert r.status_code == 303 and "error=" in r.headers["location"]
    assert "najkasnije 12 h prije termina" in unquote(r.headers["location"])
    assert db.user_booking_ids(uid, [late]) == {late}       # the booking stays


def test_cancel_cutoff_enforced():
    """A client cancels until 12 h before the termin (CANCEL_CUTOFF_HOURS, the
    owner's call of 17.10.2026); after that the place is the trainer's to plan."""
    uid = make_user("ivan@test.local")
    late = future_session(hours_from_now=11)    # inside the 12 h cutoff
    db.book(uid, late)
    with pytest.raises(db.BookingError, match="najkasnije 12 h prije termina"):
        db.cancel_booking(uid, late)
    assert db.user_booking_ids(uid, [late]) == {late}
    early = future_session(hours_from_now=13)   # outside it
    db.book(uid, early)
    db.cancel_booking(uid, early)
    assert db.user_booking_ids(uid, [early]) == set()


def test_cancel_deadline_is_twelve_hours_before_the_termin():
    """One rule, one place: cancel_booking(), the grid's Otkaži and the list's
    ✕ all ask db.cancel_deadline, so the button and the refusal agree."""
    assert config.CANCEL_CUTOFF_HOURS == 12
    sid = future_session(hours_from_now=30)
    with db.session_scope() as s:
        sess = s.get(TrainingSession, sid)
        assert db.cancel_deadline(sess) == sess.starts_at - timedelta(hours=12)
        assert db.cancel_deadline(sess).tzinfo is not None


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
    sid = future_session(hours_from_now=1)      # inside the 12 h cutoff
    db.book(uid, sid)
    db.set_session_canceled(sid, True)
    db.cancel_booking(uid, sid)                 # must NOT raise
    assert db.user_booking_ids(uid, [sid]) == set()


def test_moje_rezervacije_x_asks_first_and_only_while_cancelling_is_allowed():
    """Each card in "Moje rezervacije" carries a ✕ that asks before it cancels
    (data-confirm → base.html's #confirmDlg), only while cancelling is allowed;
    inside the 12 h the card says so instead. A termin the trainer canceled can
    always be removed. The week grid's Otkaži asks the same way."""
    from qmt.web.app import WEEKDAYS, WEEKDAYS_SHORT
    uid = make_user("ivan@test.local")
    early = future_session(hours_from_now=13, title="Grupni trening")
    late = future_session(hours_from_now=11, title="Jutarnji trening")
    gone = future_session(hours_from_now=5, title="Večernji trening")
    for sid in (early, late, gone):
        db.book(uid, sid)
    db.set_session_canceled(gone, True)          # the trainer called it off

    def local(sid):
        with db.session_scope() as s:
            sess = s.get(TrainingSession, sid)
            start = sess.starts_at.astimezone(config.TZ)
            return start, start + timedelta(minutes=sess.duration_min)

    start, end = local(early)
    monday = (start.date() - timedelta(days=start.weekday())).isoformat()
    page = client_for("ivan@test.local").get(f"/raspored?week={monday}").text
    assert 'id="confirmDlg"' in page             # the dialog the forms open
    grid, mine = page.split("<h2>Moje rezervacije</h2>")
    cards = {card.split('<div class="name">')[1].split("<")[0]: card
             for card in mine.split('<div class="sess')[1:]}

    card = cards["Grupni trening"]               # 13 h ahead: the ✕
    assert f'<form method="post" action="/cancel/{early}" class="unbook"' in card
    assert 'data-confirm-title="Otkazati rezervaciju?"' in card
    assert (f'data-confirm="Grupni trening, {WEEKDAYS_SHORT[start.weekday()]} {start:%-d.%-m.} '
            f'u {start:%H:%M}–{end:%H:%M}. Mjesto se oslobađa za druge."') in card
    assert 'data-confirm-cta="Otkaži rezervaciju"' in card
    assert f'<input type="hidden" name="week" value="{monday}">' in card
    assert (f'<button type="submit" class="unbook-x" aria-label="Otkaži Grupni trening '
            f'{start:%-d.%-m.} u {start:%H:%M}">✕</button>') in card
    assert "Otkazivanje do" not in card

    card = cards["Jutarnji trening"]             # 11 h ahead: no ✕, the state instead
    assert 'class="unbook"' not in card and f"/cancel/{late}" not in card
    assert '<div class="cap">Otkazivanje do 12 h prije termina</div>' in card

    card = cards["Večernji trening"]             # canceled by the trainer: always removable
    start, end = local(gone)
    assert f'action="/cancel/{gone}" class="unbook"' in card
    assert 'data-confirm-title="Maknuti otkazani termin?"' in card
    assert 'data-confirm-cta="Makni"' in card
    assert (f'data-confirm="Večernji trening, {WEEKDAYS_SHORT[start.weekday()]} {start:%-d.%-m.} '
            f'u {start:%H:%M}–{end:%H:%M}."') in card     # no place to free up
    assert f'aria-label="Makni Večernji trening {start:%-d.%-m.} u {start:%H:%M}">✕</button>' in card

    start, _ = local(early)                      # the grid's Otkaži asks too
    form = grid[grid.index(f'action="/cancel/{early}"'):]
    form = form[:form.index("</form>")]
    assert 'data-confirm-title="Otkazati rezervaciju?"' in form
    assert (f'data-confirm="Grupni trening, {WEEKDAYS[start.weekday()].lower()} {start:%-d.%-m.} '
            f'u {start:%H:%M}. Mjesto se oslobađa za druge."') in form
    assert 'data-confirm-cta="Otkaži rezervaciju"' in form and ">Otkaži</button>" in form

    # a trainer's calendar has no list, so no ✕, even with a booking of their own
    tid = make_user("trener@test.local", is_trainer=True)
    db.book(tid, early)
    assert 'class="unbook"' not in client_for("trener@test.local").get(f"/raspored?week={monday}").text


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
    """A guest cannot book without an account, so while registration is open
    (the suite runs SIGNUP_MODE=invite) the landing offers the account (the
    offer cards' "Registriraj se"), never a booking they'd be refused and
    never the members' plans page. The hero itself carries no button for
    anyone (16.10.2026)."""
    c = TestClient(app)
    r = c.get("/")                               # no login required
    assert r.status_code == 200
    assert "Pogledaj cjenik" not in r.text and 'href="/cjenik' not in r.text
    assert 'href="/moja-clanarina' not in r.text
    assert "/signup" in r.text                   # the account they need first
    assert "Rezerviraj termin" not in r.text     # would dead-end at the plan gate

    # calendar itself still requires auth
    r = c.get("/raspored", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=/raspored"


def test_landing_hero_follows_the_membership():
    """The hero has no button for anyone since 16.10.2026 (the owner's call:
    his announcements are the first thing on the page). A member's way in is
    the offer cards' buttons, which follow the membership: the card of a plan
    he can book with leads to /raspored, a card he does not own to its card
    on /moja-clanarina."""
    make_user("ivan@test.local", plans=("grupni",))
    make_user("ana@test.local", plans=())
    make_user("sara@test.local", plans=("online",))      # not a bookable kind

    for c in (TestClient(app), *(client_for(e) for e in ("ivan@test.local", "ana@test.local", "sara@test.local"))):
        page = c.get("/").text
        assert "cta-row" not in page and "btn-hero" not in page    # no hero button, guest or member

    gym = client_for("ivan@test.local").get("/").text.split('id="dvorana"')[1]
    assert '<a class="btn btn-sm owned" href="/raspored"' in gym              # can book: his Dvorana card
    assert 'title="Aktivna članarina">✓ Rezerviraj termin →</a>' in gym      # leads to the timetable

    for email in ("ana@test.local", "sara@test.local"):
        page = client_for(email).get("/").text
        assert 'href="/moja-clanarina#plan-' in page, email   # the cards' "Odaberi plan"
        assert "Rezerviraj termin" not in page, email    # no bookable plan


def test_the_plans_page_is_reachable_without_hunting_for_it():
    make_user("ana@test.local", plans=())
    ca = client_for("ana@test.local")
    assert 'href="/moja-clanarina"' in ca.get("/raspored").text   # nav tab + the empty state
    assert "Pogledaj cjenik" in ca.get("/raspored").text
    assert 'href="/moja-clanarina' not in TestClient(app).get("/").text   # never for a guest: members only

    # the trainer's nav is already full and they do not buy plans: no tab;
    # the account menu keeps the item (they edit the plans' texts there)
    make_user("trener@test.local", is_trainer=True, plans=())
    page = client_for("trener@test.local").get("/raspored").text
    assert ">Članarina</a>" not in page and "<span>Moja članarina</span>" in page


def test_plan_gate_offers_the_price_instead_of_a_dead_end():
    make_user("ana@test.local", plans=())                # no membership at all
    sid = future_session()
    ca = client_for("ana@test.local")
    r = ca.post(f"/book/{sid}", data={"week": ""}, follow_redirects=False)
    loc = r.headers["location"]
    assert "error=" in loc
    assert "cta=grupni" in loc                          # straight at that plan
    assert "javi+se+treneru" not in loc                  # the old dead end is gone
    # and the alert renders it as a button, to that plan's card and price
    assert '<a class="act" href="/moja-clanarina#plan-grupni">Pogledaj cjenik →</a>' in ca.get(loc).text


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


def test_cjenik_is_members_only_and_landing_plan_cta_states():
    """Plans are bought and managed on /moja-clanarina (the old /cjenik leads
    there since 18.10.2026), so it is for members: a guest who opens either
    is sent to log in, and no public page links to them. The one public
    place with prices is the landing's offer (since 5.10.2026)."""
    guest = TestClient(app)
    r = guest.get("/cjenik", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?next=/cjenik"
    r = guest.get("/moja-clanarina", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?next=/moja-clanarina"
    for path in ("/", "/login", "/signup", "/prehrana", "/forgot"):
        page = guest.get(path).text
        assert 'href="/cjenik' not in page and 'href="/moja-clanarina' not in page, path
        assert ("€" in page) == (path == "/"), path     # prices: the landing, nowhere else
    page = guest.get("/").text
    assert "Javi nam se" in page and 'id="kontakt"' in page   # cards point at the studio
    assert "Odaberi plan →</a>" not in page             # the button, not the CSS comment naming it

    make_user("ana@test.local", plans=())
    assert "Odaberi plan →</a>" in client_for("ana@test.local").get("/").text   # members pick plans

    make_user("ivan@test.local")                        # default plan: grupni
    ci = client_for("ivan@test.local")
    assert "Aktivna članarina" in ci.get("/").text      # owned state on landing
    assert '<span class="chip ok">aktivna</span>' in ci.get("/cjenik").text   # the old address, the new page


def shown(html: str) -> str:
    """What a reader sees of some markup: tags dropped, entities read,
    whitespace (a non-breaking space too) collapsed."""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def test_landing_offer_is_three_cards_with_public_prices(monkeypatch):
    """The homepage answers "what do you offer and what does it cost" by itself
    (5.10.2026): cards, each with its price and the MojiMakrosi add-on, visible
    to guests. The photo above them is a link to that section. Since 15.10.2026
    the offer is three tiers of the online plan, and the gym's two cards sit in
    a section below it."""
    page = TestClient(app).get("/").text
    offer, gym = page.split('id="usluge"')[1].split('id="dvorana"')
    assert offer.count('class="card offer') == 3 and gym.count('class="card offer') == 2
    for section, cards in ((offer, 3), (gym, 2)):       # a Mjesečno / Godišnje switch under each row, and
        assert section.count('class="period"') == 1     # every card's yearly price behind it
        assert section.count('data-period="year" hidden>') == cards
    assert page.count('<span class="featured-tag">Najpopularnije</span>') == 1   # the chip, not the CSS comment naming it
    assert '<span class="featured-tag">' in offer       # on a tier, not in the gym
    # the shop's reference prices as typed (the price slots' defaults), each
    # with its unit: no range cut to its floor any more ("od 60 €")
    assert "50 € / mjesečno" in shown(offer.split('class="card offer featured"')[0])   # QMove START
    for price in ("60–80 € / paket", "35 € / trening",
                  "u dvoje ili troje 25 € / trening · rehabilitacija od 30 € / tretman"):   # Individualno's line
        assert price in shown(gym), price
    assert "od 60" not in shown(offer + gym)
    for amount, unit in (("25", "/ trening"), ("od 30", "/ tretman")):   # a price and its unit are held together
        assert f'<span class="t">{amount}</span>&nbsp;€&nbsp;<span class="t">{unit}</span>' in gym, amount
    assert offer.count('+<span class="t">5</span> € / mjesečno') == 3    # MojiMakrosi: online 5, dvorana 3
    assert gym.count('+<span class="t">3</span> € / mjesečno') == 2
    assert "Zoom poziv" in page                         # what the online plan includes
    assert '<a class="stage" href="#usluge"' in page and 'id="usluge"' in page
    for chip in ("Grupni", "1:1", "Rehabilitacija"):    # the photo carries no service chips any more
        assert f'<span class="tag">{chip}</span>' not in page, chip
    assert page.count('href="#kontakt">Javi nam se →</a>') == 5      # invite-only: the studio is the way in

    monkeypatch.setenv("SIGNUP_MODE", "open")           # open to anyone: the cards register instead
    assert TestClient(app).get("/").text.count('data-auth="signup">Registriraj se →</a>') == 5
    monkeypatch.setenv("SIGNUP_MODE", "invite")

    make_user("ivan@test.local")                        # owns grupni: his card says so and leads into the app
    page = client_for("ivan@test.local").get("/").text
    assert 'class="card offer mine"' in page.split('id="dvorana"')[1] and "Aktivna članarina" in page
    assert page.count("Odaberi plan →</a>") == 4        # the four he does not have (three tiers, individualno)


def test_public_prices_switch_hides_them_from_guests_only(monkeypatch):
    """PUBLIC_PRICES=off is the one-variable way back to the 28.9. rule: guests
    see the offer without a single price, members see everything."""
    assert config.prices_public()                       # the default since 5.10.2026
    monkeypatch.setenv("PUBLIC_PRICES", "off")
    assert not config.prices_public()
    page = TestClient(app).get("/").text
    assert page.count('class="card offer') == 5 and "€" not in page
    assert page.count("Cijene nakon prijave") == 5
    # no Mjesečno / Godišnje switch under either row, and no yearly price behind one
    assert 'class="period"' not in page and 'data-period="' not in page

    make_user("ana@test.local", plans=())
    page = client_for("ana@test.local").get("/").text
    assert "50 € / mjesečno" in shown(page) and '+<span class="t">3</span> € / mjesečno' in page
    assert "Cijene nakon prijave" not in page
    assert page.count('class="period"') == 2            # a member gets both switches


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


def test_moja_clanarina_shows_membership_overview_and_billing_history():
    """The overview and the history moved from /profil to /moja-clanarina
    (18.10.2026); the profile keeps a way there."""
    uid = make_user("ivan@test.local", plans=("grupni",))   # 1st uplata: gotovina
    db.record_payment(uid, "grupni", "kartica")             # renewal
    from qmt.models import Membership
    with db.session_scope() as s:
        from sqlalchemy import select
        m = s.scalar(select(Membership).where(Membership.user_id == uid))
        due, expiry = m.next_payment, m.dospijece

    c = client_for("ivan@test.local")
    page = c.get("/moja-clanarina").text
    assert "Tvoji planovi" in page and "Grupni trening" in page
    assert '<span class="chip ok">aktivna</span>' in page
    assert due.strftime("%-d.%-m.%Y.") in page              # sljedeća uplata
    assert expiry.strftime("%-d.%-m.%Y.") in page           # dospijeće
    # the ledger lists BOTH uplate with their methods
    assert "Računi" in page
    assert "Gotovina" in page and "Kartica" in page
    # an active plan is a door to what it unlocks
    assert 'href="/raspored">Rezerviraj termin' in page

    db.record_payment(uid, "online")
    page = c.get("/moja-clanarina").text
    assert 'href="/treninzi">Otvori online treninge' in page

    profil = c.get("/profil").text
    assert "Povijest plaćanja" not in profil and 'href="/moja-clanarina"' in profil


def test_profil_without_plan_points_to_moja_clanarina():
    make_user("ana@test.local", plans=())
    c = client_for("ana@test.local")
    assert 'href="/moja-clanarina"' in c.get("/profil").text
    page = c.get("/moja-clanarina").text
    assert "Nemaš aktivnu članarinu" in page
    assert "Još nema zabilježenih uplata" in page


# ---------- session quota (8/12/16 treninga a month) ----------

def test_tiered_plan_caps_bookings_per_cycle():
    uid = make_user("ivan@test.local", plans=())
    db.record_payment(uid, "grupni", sessions_per_cycle=2)       # a 2-tier keeps the test small
    s1, s2, s3 = (future_session(hours_from_now=24 * d) for d in (1, 2, 3))
    db.book(uid, s1)
    db.book(uid, s2)
    with pytest.raises(db.BookingError, match="Iskoristio"):
        db.book(uid, s3)
    u = db.cycle_usage(uid, "grupni")
    assert (u["used"], u["quota"]) == (2, 2)

    db.cancel_booking(uid, s1)                                   # a cancelled booking frees the slot
    db.book(uid, s3)
    assert db.cycle_usage(uid, "grupni")["used"] == 2

    db.set_session_canceled(s2, True)                            # a termin the trainer cancels does not count
    assert db.cycle_usage(uid, "grupni")["used"] == 1

    # the next uplata restates the tier; unlimited is NULL
    db.record_payment(uid, "grupni")
    assert db.cycle_usage(uid, "grupni") is None
    db.book(uid, future_session(hours_from_now=24 * 4))         # no cap any more


def test_unlimited_plans_are_untouched_by_quota():
    uid = make_user("ivan@test.local")                           # plain grupni, no tier
    for d in range(1, 6):
        db.book(uid, future_session(hours_from_now=24 * d))
    assert db.cycle_usage(uid, "grupni") is None
    page = client_for("ivan@test.local").get("/raspored").text
    assert "u ovom ciklusu" not in page


def test_cycle_is_anchored_on_the_due_date_not_the_payment():
    from qmt.models import Membership, add_month, sub_month
    m = Membership(user_id=1, plan="grupni", paid_on=date(2026, 9, 26),   # paid 10 days early
                   next_payment=date(2026, 11, 6), sessions_per_cycle=8)
    assert m.cycle_bounds(date(2026, 9, 28)) == (date(2026, 9, 6), date(2026, 10, 6))   # still the old month
    assert m.cycle_bounds(date(2026, 10, 20)) == (date(2026, 10, 6), date(2026, 11, 6))  # the month just paid
    assert m.cycle_bounds(date(2026, 11, 6)) == (date(2026, 11, 6), date(2026, 12, 6))   # booking ahead
    assert add_month(date(2026, 1, 31)) == date(2026, 2, 28) and sub_month(date(2026, 3, 31)) == date(2026, 2, 28)


# ---------- weekly series: "isti termin svaki tjedan" ----------

def _weekly(days_ahead: int = 2, capacity: int = 8, kind: str = "grupni"):
    """A weekly template whose next termin is `days_ahead` days out at 18:00,
    with that week opened: (template id, the termin's session id, its date)."""
    day = config.today() + timedelta(days=days_ahead)
    tid = db.add_template("Tjedni trening", day.weekday(), 18 * 60, 60, capacity, None, kind=kind)
    return tid, _occurrence(tid, day), day


def _occurrence(tid: int, day: date, open_week: bool = True) -> int | None:
    """Template `tid`'s session on `day`. Its week is opened first, the way a
    client viewing it would; with open_week=False it is None until something
    else (a series) has created it."""
    from sqlalchemy import select
    if open_week:
        db.materialize_week(day - timedelta(days=day.weekday()))
    starts = datetime(day.year, day.month, day.day, 18, tzinfo=config.TZ)
    with db.session_scope() as s:
        return s.scalar(select(TrainingSession.id).where(
            TrainingSession.template_id == tid, TrainingSession.starts_at == starts))


def _due(uid: int, next_payment: date, plan: str = "grupni", sessions: int | None = None):
    """Pin a plan's next_payment, so the paid period is known in any month the
    suite runs: the cycle is [next_payment − 1 mj, next_payment)."""
    from qmt.models import Membership
    with db.session_scope() as s:
        m = s.scalar(db.select(Membership).where(Membership.user_id == uid,
                                                 Membership.plan == plan))
        m.next_payment, m.sessions_per_cycle = next_payment, sessions


def _weeks(day: date, *ks: int) -> list[date]:
    return [day + timedelta(days=7 * k) for k in ks]


def test_series_books_each_following_week_of_the_paid_period_and_no_further():
    from sqlalchemy import func, select
    uid = make_user("ivan@test.local")
    tid, sid, day = _weekly()
    _due(uid, day + timedelta(days=24))              # paid until day+23: three more weeks fit
    db.book(uid, sid)
    with db.session_scope() as s:
        rows = s.scalar(select(func.count()).select_from(TrainingSession))

    weeks = _weeks(day, 1, 2, 3)
    assert db.series_preview(uid, sid) == {"n": 3, "last": weeks[-1],
                                            "until": day + timedelta(days=23)}
    with db.session_scope() as s:                     # read-only: unopened weeks count as free
        assert s.scalar(select(func.count()).select_from(TrainingSession)) == rows

    res = db.book_series(uid, sid)
    assert res == {"booked": weeks, "skipped": [], "stopped": None,
                   "until": day + timedelta(days=23), "quota": None}
    ids = [_occurrence(tid, d, open_week=False) for d in weeks]
    assert db.user_booking_ids(uid, ids) == set(ids)
    assert _occurrence(tid, day + timedelta(days=28), open_week=False) is None   # past the period: untouched

    again = db.book_series(uid, sid)                 # twice: nothing new, and each date says why
    assert again["booked"] == [] and again["skipped"] == [(d, "već rezervirano") for d in weeks]


def test_series_ignores_the_booking_horizon_inside_the_paid_period(monkeypatch):
    """book() refuses a termin more than BOOKING_HORIZON_DAYS ahead; the series
    books the paid period, creating weeks nobody has opened. The horizon is
    shrunk to 10 days so this holds in any month: with the real 28, a date past
    it fits in one cycle only when the cycle is longer than 28 days, and a
    February cycle is not."""
    monkeypatch.setattr(config, "BOOKING_HORIZON_DAYS", 10)
    uid = make_user("ivan@test.local")
    ana = make_user("ana@test.local")
    tid, sid, day = _weekly()
    _due(uid, day + timedelta(days=24))
    db.book(uid, sid)
    far = _weeks(day, 2, 3)                          # 16 and 23 days out
    assert [_occurrence(tid, d, open_week=False) for d in far] == [None, None]

    assert db.book_series(uid, sid)["booked"] == _weeks(day, 1, 2, 3)
    for d in far:
        occ = _occurrence(tid, d, open_week=False)   # the series created it...
        assert db.user_booking_ids(uid, [occ]) == {occ}
        with pytest.raises(db.BookingError, match="unaprijed"):
            db.book(ana, occ)                        # ...and book() alone still refuses it


def test_series_skips_full_canceled_and_held_dates_and_says_why():
    uid = make_user("ivan@test.local", plans=("individualni",))
    ana = make_user("ana@test.local", plans=("individualni",))
    tid, sid, day = _weekly(capacity=1, kind="individualni")    # a weekly 1:1 slot
    _due(uid, day + timedelta(days=24), plan="individualni")
    db.book(uid, sid)
    full, canceled, held = (_occurrence(tid, d) for d in _weeks(day, 1, 2, 3))
    db.book(ana, full)                               # the one spot is ana's
    db.set_session_canceled(canceled, True)          # the trainer called it off
    db.book(uid, held)                               # booked by hand already

    res = db.book_series(uid, sid)
    assert res["booked"] == [] and res["stopped"] is None
    assert res["skipped"] == [(day + timedelta(days=7), "popunjen"),
                              (day + timedelta(days=14), "otkazan"),
                              (day + timedelta(days=21), "već rezervirano")]   # full as well, but by them
    assert db.user_booking_ids(uid, [full, canceled]) == set()


def test_series_stops_where_the_paket_runs_out():
    uid = make_user("ivan@test.local", plans=())
    db.record_payment(uid, "grupni", sessions_per_cycle=12)
    tid, sid, day = _weekly()
    _due(uid, day + timedelta(days=24), sessions=12)
    db.book(uid, sid)
    for h in range(9):                               # 10 of 12 used in this cycle
        db.book(uid, future_session(hours_from_now=24 + h))
    assert db.cycle_usage(uid, "grupni", on=day)["used"] == 10

    res = db.book_series(uid, sid)
    assert res["booked"] == _weeks(day, 1, 2) and res["stopped"] == "paket" and res["quota"] == 12
    third = _occurrence(tid, day + timedelta(days=21), open_week=False)
    assert db.user_booking_ids(uid, [third]) == set()   # the rest stays unbooked
    assert db.cycle_usage(uid, "grupni", on=day)["used"] == 12

    again = db.book_series(uid, sid)                 # their own dates are "held", not the stop
    assert again["skipped"] == [(d, "već rezervirano") for d in _weeks(day, 1, 2)]
    assert again["booked"] == [] and again["stopped"] == "paket"


def test_series_refuses_one_off_termini_missing_plans_and_slots_off_the_timetable():
    uid = make_user("ivan@test.local")
    one_off = future_session(hours_from_now=48)
    db.book(uid, one_off)
    assert db.series_preview(uid, one_off) is None
    with pytest.raises(db.BookingError, match="nema tjedni raspored"):
        db.book_series(uid, one_off)

    tid, sid, day = _weekly()
    ana = make_user("ana@test.local", plans=())     # no plan at all
    assert db.series_preview(ana, sid) is None
    with pytest.raises(db.MembershipRequired, match="članarina"):
        db.book_series(ana, sid)

    db.book(uid, sid)
    db.set_template_active(tid, False)               # the trainer switched the slot off
    assert db.series_preview(uid, sid) is None
    with pytest.raises(db.BookingError, match="više nije u tjednom rasporedu"):
        db.book_series(uid, sid)

    db.set_template_active(tid, True)                # ...or moved it a day on: the booked
    db.update_template(tid, "Tjedni trening", (day.weekday() + 1) % 7, 18 * 60, 60, 8, None)
    assert db.series_preview(uid, sid) is None       # termin stays, its old weekday is not repeated
    with pytest.raises(db.BookingError, match="više nije u tjednom rasporedu"):
        db.book_series(uid, sid)
    assert _occurrence(tid, day + timedelta(days=7), open_week=False) is None


def test_series_in_the_grace_week_stops_at_dospijece():
    """A termin on or after next_payment sits in the grace week: the series
    repeats it at most up to dospijeće, never into the month nobody paid."""
    uid = make_user("ivan@test.local")
    tid, sid, day = _weekly()
    db.book(uid, sid)
    _due(uid, day - timedelta(days=1))               # due the day before: dospijeće is day+6
    assert db.series_preview(uid, sid) is None
    assert db.book_series(uid, sid)["booked"] == []

    _due(uid, day)                                   # due that day: dospijeće is day+7
    res = db.book_series(uid, sid)
    assert res["booked"] == [day + timedelta(days=7)] and res["until"] == day + timedelta(days=7)
    assert _occurrence(tid, day + timedelta(days=14), open_week=False) is None


def test_series_reopened_late_counts_only_the_weeks_still_ahead():
    """A ?series= link reopened long after its termin: the weeks already past
    neither count nor get a session created (week views never make history)."""
    uid = make_user("ivan@test.local")
    past = config.today() - timedelta(days=9)
    tid = db.add_template("Tjedni trening", past.weekday(), 18 * 60, 60, 8, None)
    with db.session_scope() as s:                    # the termin they booked, nine days ago
        sess = TrainingSession(template_id=tid, title="Tjedni trening", kind="grupni",
                               starts_at=datetime(past.year, past.month, past.day, 18, tzinfo=config.TZ))
        s.add(sess)
        s.flush()
        s.add(Booking(user_id=uid, session_id=sess.id))
        sid = sess.id
    _due(uid, past + timedelta(days=20))             # paid until past+19: weeks past+7 (gone) and past+14
    assert db.series_preview(uid, sid) == {"n": 1, "last": past + timedelta(days=14),
                                            "until": past + timedelta(days=19)}
    assert db.book_series(uid, sid)["booked"] == [past + timedelta(days=14)]
    assert _occurrence(tid, past + timedelta(days=7), open_week=False) is None


def test_series_offer_follows_a_booking_and_runs_from_the_calendar():
    from urllib.parse import unquote
    uid = make_user("ivan@test.local")
    tid, sid, day = _weekly()
    _due(uid, day + timedelta(days=24))
    monday = (day - timedelta(days=day.weekday())).isoformat()
    weeks = _weeks(day, 1, 2, 3)
    c = client_for("ivan@test.local")

    r = c.post(f"/book/{sid}", data={"week": monday}, follow_redirects=False)
    loc = r.headers["location"]
    assert "ok=" in loc and loc.endswith(f"&series={sid}")      # the usual ok, plus the offer
    page = c.get(loc).text.replace("&nbsp;", " ")
    until = day + timedelta(days=23)
    assert f"Isti termin svaki tjedan do {until:%-d.%-m.} — još 3 termina →" in page
    assert f'action="/book/{sid}/series"' in page
    assert page.count('class="alert ok"') == 1      # the offer IS the confirmation

    r = c.post(f"/book/{sid}/series", data={"week": monday}, follow_redirects=False)
    assert unquote(r.headers["location"]) == (f"/raspored?week={monday}&ok=Rezervirano još 3 termina: "
                                              + ", ".join(f"{d:%-d.%-m.}" for d in weeks))
    ids = [_occurrence(tid, d, open_week=False) for d in weeks]
    assert db.user_booking_ids(uid, ids) == set(ids)
    loc = unquote(c.post(f"/book/{sid}/series", data={"week": monday},
                         follow_redirects=False).headers["location"])
    assert "error=Nijedan termin nije rezerviran" in loc and "(već rezervirano)" in loc

    # someone else's booking: no offer, and running it anyway books nothing
    ana = make_user("ana@test.local")
    ca = client_for("ana@test.local")
    assert 'class="series-offer"' not in ca.get(f"/raspored?week={monday}&series={sid}").text
    r = ca.post(f"/book/{sid}/series", data={"week": monday}, follow_redirects=False)
    assert "error=" in r.headers["location"]
    assert db.user_booking_ids(ana, ids) == set()

    # a one-off termin: the plain confirmation, exactly as before
    one = future_session(hours_from_now=30)
    page = c.get(c.post(f"/book/{one}", data={}, follow_redirects=False).headers["location"]).text
    assert '<div class="alert ok" role="status">Rezervirano ✓</div>' in page
    assert 'class="series-offer"' not in page
    for junk in ("abc", "-1", "99999999999999999999"):   # a crafted id offers nothing, never a 500
        assert c.get(f"/raspored?series={junk}").status_code == 200


def test_series_message_names_the_dates_the_skips_and_a_spent_paket():
    from qmt.web.app import _series_feedback
    d = [date(2026, 10, 18), date(2026, 10, 25), date(2026, 11, 1), date(2026, 11, 8)]
    run = {"skipped": [], "stopped": None, "until": date(2026, 11, 14), "quota": None}
    assert _series_feedback({**run, "booked": d[:3]}) == (
        "Rezervirano još 3 termina: 18.10., 25.10., 1.11.", True)
    assert _series_feedback({**run, "booked": d[:3], "skipped": [(d[3], "popunjen")]}) == (
        "Rezervirano još 3 termina: 18.10., 25.10., 1.11. — preskočeno 8.11. (popunjen)", True)
    assert _series_feedback({**run, "booked": d[:1], "stopped": "paket", "quota": 12}) == (
        "Rezervirano još 1 termin: 18.10. — paket od 12 treninga je popunjen, "
        "ostatak nije rezerviran", True)
    assert _series_feedback({**run, "booked": [], "stopped": "paket", "quota": 12}) == (
        "Nijedan termin nije rezerviran — paket od 12 treninga je popunjen.", False)


def test_series_race_for_the_last_spot_no_overbooking():
    """Six clients run their series at the same moment while one date has a
    single spot left: exactly one gets it, and nobody deadlocks (each series
    locks its dates in order)."""
    from sqlalchemy import func, select
    tid, sid, day = _weekly(capacity=8)
    first = _occurrence(tid, day + timedelta(days=7))
    for i in range(7):                               # 7 of 8 taken
        db.book(make_user(f"f{i}.race@test.local"), first)
    racers = [make_user(f"r{i}.race@test.local") for i in range(6)]
    for u in racers:
        _due(u, day + timedelta(days=24))
    results, gate = {}, threading.Barrier(len(racers))

    def run(uid):
        gate.wait()
        results[uid] = db.book_series(uid, sid)

    threads = [threading.Thread(target=run, args=(u,)) for u in racers]
    for t in threads: t.start()
    for t in threads: t.join()

    assert len(results) == len(racers), "a series raised (deadlock?)"
    won = [u for u, r in results.items() if day + timedelta(days=7) in r["booked"]]
    assert len(won) == 1, f"overbooked: {results}"
    for u, r in results.items():
        assert r["booked"] == (_weeks(day, 1, 2, 3) if u in won else _weeks(day, 2, 3))
        assert r["skipped"] == ([] if u in won else [(day + timedelta(days=7), "popunjen")])
    with db.session_scope() as s:
        n = s.scalar(select(func.count()).select_from(Booking).where(Booking.session_id == first))
        rows = s.scalar(select(func.count()).select_from(TrainingSession)
                        .where(TrainingSession.template_id == tid))
    assert n == 8 and rows == 4                      # full, and no week was created twice


# ---------- auth modal + install banner (patterns.md §2, §3) ----------

def test_guest_pages_carry_the_auth_modal_and_clients_the_install_banner():
    c = TestClient(app)
    page = c.get("/prehrana").text
    assert 'id="authDlg"' in page                          # one modal, two tabs
    assert 'id="authLogin"' in page and 'id="authSignup"' in page
    assert 'data-auth="login"' in page and 'data-auth="signup"' in page
    assert 'name="next" value="/prehrana"' in page         # login returns you where you were
    assert 'id="a2hs"' not in page                         # guests are never asked to install
    assert "samo pozvani" in page                          # invite-only note under SIGNUP_MODE=invite
    # auth pages themselves send you home, never back to /login
    assert 'name="next" value="/"' in c.get("/login").text

    make_user("ivan@test.local")
    ci = client_for("ivan@test.local")
    page = ci.get("/raspored").text
    assert 'id="authDlg"' not in page                      # logged in: no modal
    assert 'id="a2hs"' in page and 'id="a2hsIos"' in page and 'id="a2hsAndroid"' in page

    make_user("trener@test.local", is_trainer=True)
    assert 'id="a2hs"' not in client_for("trener@test.local").get("/raspored").text


# ---------- /raspored on a phone: one day at a time (17.10.2026) ----------
# The day strip, the rows and the sheet are the phone's; the route decides
# which day shows (?day=), carries it through every form and redirect, and
# answers "Tvoj sljedeći termin" at the top. The browser half (one column
# visible, the strip's taps, the sheet) is tests/test_raspored_ui.py.

def _at(day: date, hour: int = 18) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=config.TZ)


def _tag(page: str, start: str) -> str:
    """The opening tag that starts with `start` (attributes may wrap lines)."""
    i = page.index(start)
    return page[i:page.index(">", i) + 1]


def _row(page: str, sid: int) -> str:
    """The phone row (a <button>) that opens the sheet for session `sid`."""
    i = page.index(f'data-id="{sid}"')
    return page[page.rfind("<button", 0, i):page.index(">", i) + 1]


NEXT = '<section class="card next-termin"'


def test_day_param_picks_the_shown_day_else_today_else_the_first_day_with_termini():
    make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    today = config.today()
    monday = today - timedelta(days=today.weekday())
    other = monday + timedelta(days=(today.weekday() + 3) % 7)      # another day of this week
    db.add_oneoff_session("Grupni trening", _at(other), 60, 8, None)   # a week with termini has a strip

    page = c.get(f"/raspored?week={monday}&day={other}").text
    assert f'data-selected="{other}"' in page
    assert 'aria-pressed="true"' in _tag(page, f'<button type="button" data-day="{other}"')
    assert 'aria-pressed="false"' in _tag(page, f'<button type="button" data-day="{today}"')
    assert 'aria-current="date"' in _tag(page, f'<button type="button" data-day="{today}"')
    strip = page[page.index('<nav class="day-strip"'):]
    assert strip[:strip.index("</nav>")].count('aria-pressed="true"') == 1

    for junk in (monday + timedelta(days=7), "nije-datum", ""):     # outside the week, garbage: today
        page = c.get(f"/raspored?week={monday}&day={junk}").text
        assert f'data-selected="{today}"' in page, junk
        assert 'aria-pressed="true"' in _tag(page, f'<button type="button" data-day="{today}"')

    nxt = monday + timedelta(days=7)                    # a week without today: its first day with termini
    db.add_oneoff_session("Grupni trening", _at(nxt + timedelta(days=2)), 60, 8, None)
    assert f'data-selected="{nxt + timedelta(days=2)}"' in c.get(f"/raspored?week={nxt}").text
    empty = monday + timedelta(days=14)                 # ...and without termini: its Monday, and no strip
    page = c.get(f"/raspored?week={empty}").text
    assert f'data-selected="{empty}"' in page and 'class="day-strip"' not in page


def test_the_strip_has_seven_days_a_dot_on_booked_ones_and_the_grid_forms_carry_their_day():
    from qmt.web.app import WEEKDAYS_SHORT
    uid = make_user("ivan@test.local")
    monday = config.today() - timedelta(days=config.today().weekday()) + timedelta(days=7)   # next week
    wed, fri = monday + timedelta(days=2), monday + timedelta(days=4)
    mine = db.add_oneoff_session("Grupni trening", _at(wed), 60, 8, None)
    free = db.add_oneoff_session("Grupni trening", _at(fri), 60, 8, None)
    db.book(uid, mine)
    page = client_for("ivan@test.local").get(f"/raspored?week={monday}").text

    strip = page[page.index('<nav class="day-strip"'):]
    strip = strip[:strip.index("</nav>")]
    assert 'aria-label="Dani u tjednu" hidden' in strip     # shown by the script only
    days = [monday + timedelta(days=i) for i in range(7)]
    tags = {d: _tag(strip, f'<button type="button" data-day="{d}"') for d in days}
    assert strip.count("<button") == 7
    for d, tag in tags.items():
        assert f'aria-label="{WEEKDAYS_SHORT[d.weekday()]} {d:%-d.%-m.}"' in tag
        assert ("has-mine" in tag) == (d == wed), d          # the dot: a booking of mine that day
        assert ("is-empty" in tag) == (d not in (wed, fri)), d
    assert f'data-selected="{wed}"' in page                 # next week: its first day with termini
    assert f'data-week="{monday}"' in page

    # each grid form posts its own day; the shown-day forms (the ✕) the selected one
    grid = page[page.index('<div class="week" data-selected'):page.index("<h2>Moje rezervacije</h2>")]
    form = grid[grid.index(f'action="/book/{free}"'):]
    assert f'<input type="hidden" name="day" value="{fri}">' in form[:form.index("</form>")]
    form = grid[grid.index(f'action="/cancel/{mine}"'):]
    assert f'<input type="hidden" name="day" value="{wed}">' in form[:form.index("</form>")]
    unbook = page[page.index(f'<form method="post" action="/cancel/{mine}" class="unbook"'):]
    assert f'<input type="hidden" name="day" value="{wed}" data-shown-day>' in unbook[:unbook.index("</form>")]


def test_phone_rows_open_the_sheet_for_clients_and_link_the_trainer_to_the_roster():
    tr = make_user("trener@test.local", is_trainer=True)
    uid = make_user("ivan@test.local", plans=("grupni",))
    tid, weekly, day = _weekly(days_ahead=9)                 # next week or the one after: all ahead
    monday = day - timedelta(days=day.weekday())
    one_off = db.add_oneoff_session("Jutarnji trening", _at(day, 7), 60, 8, None)
    solo = db.add_oneoff_session("Individualni trening", _at(day, 20), 60, 1, None, kind="individualni")
    db.book(uid, one_off)
    db.book(tr, weekly)                                      # the trainer's own booking changes nothing

    page = client_for("ivan@test.local").get(f"/raspored?week={monday}").text
    assert page.count('<dialog id="sheet" class="fb-modal sheet"') == 1
    row = _row(page, weekly)
    assert row.startswith('<button type="button" class="sess-row" aria-haspopup="dialog"')
    assert 'data-state="book"' in row and 'data-weekly="1"' in row and 'data-title="Tjedni trening"' in row
    assert f'data-date="{day}"' in row and 'data-time="18:00" data-end="19:00"' in row
    assert 'data-booked="1" data-capacity="8"' in row and 'data-oneonone="0"' in row
    row = _row(page, one_off)
    assert row.startswith('<button type="button" class="sess-row mine"')
    assert 'data-state="mine"' in row and 'data-weekly="0"' in row
    # no plan for a 1:1: a plain row that says so, nothing to tap
    i = page.index('<span class="rn">Individualni trening</span>')
    assert page.rfind('<div class="sess-row">', 0, i) > page.rfind("<button", 0, i)
    assert '<span class="need">potrebna članarina</span>' in page[i:i + 300]

    page = client_for("trener@test.local").get(f"/raspored?week={monday}").text
    for sid in (weekly, one_off, solo):
        assert f'<a class="sess-row" href="/admin/session/{sid}">' in page
    assert 'id="sheet"' not in page and "sess-row mine" not in page and 'data-state=' not in page


def test_book_with_series_books_the_following_weeks_at_once():
    """The sheet's checkbox: POST /book with series=1 books the termin and
    runs the weekly repeat in one go; the alert says both and offers nothing
    more. Without it the flow is the old one (the offer in the alert)."""
    from urllib.parse import unquote
    uid = make_user("ivan@test.local")
    tid, sid, day = _weekly()
    _due(uid, day + timedelta(days=24))
    monday = (day - timedelta(days=day.weekday())).isoformat()
    weeks = _weeks(day, 1, 2, 3)
    c = client_for("ivan@test.local")

    r = c.post(f"/book/{sid}", data={"week": monday, "day": day.isoformat(), "series": "1"},
               follow_redirects=False)
    loc = unquote(r.headers["location"])
    assert loc == (f"/raspored?week={monday}&day={day}&ok=Rezervirano ✓ — rezervirano još 3 termina: "
                   + ", ".join(f"{d:%-d.%-m.}" for d in weeks))
    assert "series=" not in loc
    ids = [_occurrence(tid, d, open_week=False) for d in weeks]
    assert db.user_booking_ids(uid, [sid, *ids]) == {sid, *ids}
    page = c.get(loc).text
    assert 'class="series-offer"' not in page and page.count('class="alert ok"') == 1

    # a termin with no weekly slot: the booking stands, the alert says why the rest did not
    one = future_session(hours_from_now=30)
    loc = unquote(c.post(f"/book/{one}", data={"series": "1"}, follow_redirects=False).headers["location"])
    assert loc == "/raspored?error=Rezervirano ✓, ali ovaj termin nema tjedni raspored."
    assert db.user_booking_ids(uid, [one]) == {one}

    # without the box: exactly the flow before, one booking and the offer
    ana = make_user("ana@test.local")
    _due(ana, day + timedelta(days=24))
    r = client_for("ana@test.local").post(f"/book/{sid}", data={"week": monday, "series": ""},
                                          follow_redirects=False)
    assert r.headers["location"].endswith(f"&series={sid}")
    assert db.user_booking_ids(ana, [sid, *ids]) == {sid}


def test_the_shown_day_survives_book_cancel_and_refusals():
    uid = make_user("ivan@test.local")
    sid = future_session(hours_from_now=48)
    c = client_for("ivan@test.local")
    week, day = "2026-10-19", "2026-10-21"
    for path in (f"/book/{sid}", f"/cancel/{sid}"):         # done: ok, on the same day
        loc = c.post(path, data={"week": week, "day": day}, follow_redirects=False).headers["location"]
        assert loc.startswith(f"/raspored?week={week}&day={day}&ok="), loc
    loc = c.post(f"/cancel/{sid}", data={"week": week, "day": day},     # nothing to cancel: the error, same day
                 follow_redirects=False).headers["location"]
    assert loc.startswith(f"/raspored?week={week}&day={day}&error="), loc
    for junk in ("<script>", "2026-13-45", "21.10.2026"):  # not a date: dropped, never echoed
        loc = c.post(f"/book/{sid}", data={"week": week, "day": junk}, follow_redirects=False).headers["location"]
        assert "day=" not in loc and loc.startswith(f"/raspored?week={week}&ok="), loc
        c.post(f"/cancel/{sid}", data={"week": week})
    assert db.user_booking_ids(uid, [sid]) == set()


def test_relative_day_hint():
    from qmt.web.app import _relative_day
    d = date(2026, 10, 17)
    assert [_relative_day(d + timedelta(days=n), d) for n in (0, 1, 2, 3, 4, 5, 11, 21, 22)] == [
        "danas", "sutra", "za 2 dana", "za 3 dana", "za 4 dana", "za 5 dana", "za 11 dana",
        "za 21 dan", "za 22 dana"]


def test_next_termin_card_shows_the_soonest_booking_to_clients_only():
    from qmt.web.app import WEEKDAYS_SHORT
    uid = make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    assert NEXT not in c.get("/raspored").text              # no booking: no card, no empty state

    today = config.today()
    tomorrow, later = today + timedelta(days=1), today + timedelta(days=3)
    first = db.add_oneoff_session("Grupni trening", _at(tomorrow), 60, 8, None)
    second = db.add_oneoff_session("Individualni trening", _at(later), 60, 1, None)
    db.book(uid, first)
    db.book(uid, second)

    def card(page):
        i = page.index(NEXT)
        return page[i:page.index("</section>", i)]

    page = c.get("/raspored").text                          # right under the week's head, above the days
    assert page.index('<div class="week-head">') < page.index(NEXT) < page.index("data-selected=")
    nt = card(page)
    assert "Tvoj sljedeći termin" in nt and "Grupni trening" in nt and "Individualni" not in nt
    assert f"{WEEKDAYS_SHORT[tomorrow.weekday()]} {tomorrow:%-d.%-m.} · 18:00–19:00" in nt
    assert '<span class="nt-rel">sutra</span>' in nt
    assert f'<form method="post" action="/cancel/{first}" class="unbook"' in nt     # the list's ✕, asking first
    assert 'data-confirm-title="Otkazati rezervaciju?"' in nt and 'data-confirm-cta="Otkaži rezervaciju"' in nt
    assert (f'data-confirm="Grupni trening, {WEEKDAYS_SHORT[tomorrow.weekday()]} {tomorrow:%-d.%-m.} '
            'u 18:00–19:00. Mjesto se oslobađa za druge."') in nt
    mine = page.split("<h2>Moje rezervacije</h2>")[1]       # a shortcut, not a split: the list keeps it
    assert f'action="/cancel/{first}" class="unbook"' in mine and f'action="/cancel/{second}"' in mine

    db.cancel_booking(uid, first)                           # the next one: in three days, 1:1
    nt = card(c.get("/raspored").text)
    assert '<span class="nt-rel">za 3 dana</span>' in nt and '<span class="tag-11">1:1</span>' in nt

    db.set_session_canceled(second, True)                   # called off by the trainer: said, and removable
    nt = card(c.get("/raspored").text)
    assert '<span class="nt-off">OTKAZANO</span>' in nt and "nt-rel" not in nt
    assert 'data-confirm-title="Maknuti otkazani termin?"' in nt and 'data-confirm-cta="Makni"' in nt

    soon = future_session(hours_from_now=5, title="Kasni trening")   # inside the 12 h: no ✕, says until when
    db.book(uid, soon)
    nt = card(c.get("/raspored").text)
    assert "Kasni trening" in nt and "unbook" not in nt
    assert '<div class="nt-late">Otkazivanje do 12 h prije termina</div>' in nt

    tid = make_user("trener@test.local", is_trainer=True)   # a trainer with a booking: no card
    db.book(tid, soon)
    assert NEXT not in client_for("trener@test.local").get("/raspored").text


# ---------- /raspored's month view (18.10.2026) ----------
# The phone's "Mjesec": the month as a grid, the paid period tinted
# (db.covered_days), my bookings dotted, every day a link to its week on that
# day. The browser half (the switch, a tap on a day, the tint's contrast) is
# tests/test_raspored_ui.py.

MONTH = '<div class="month card">'
SWITCH = '<div class="view-switch"'
MONTHS_HR = ["siječanj", "veljača", "ožujak", "travanj", "svibanj", "lipanj",
             "srpanj", "kolovoz", "rujan", "listopad", "studeni", "prosinac"]


def _days(a: date, b: date) -> set[date]:
    """Every day from a to b, inclusive."""
    return {a + timedelta(days=i) for i in range((b - a).days + 1)}


def _attrs(tag: str) -> dict:
    return dict(re.findall(r'([\w-]+)="([^"]*)"', tag))


def _month_cells(page: str) -> list[dict]:
    """The grid's cells in order: the <a>'s attributes, its classes as a set
    and the day its link opens."""
    cells = []
    for tag in re.findall(r'<a class="mday[^>]*>', page):
        a = _attrs(tag)
        a["classes"], a["day"] = set(a["class"].split()), date.fromisoformat(a["href"].rsplit("day=", 1)[1])
        cells.append(a)
    return cells


def _switch(page: str) -> dict:
    """Tjedan | Mjesec: {"week" | "month": (href, "true" when it is the current page)}."""
    i = page.index(SWITCH)
    links = [_attrs(t) for t in re.findall(r"<a [^>]*>", page[i:page.index("</div>", i)])]
    return {a["data-view"]: (a["href"], "true" if a.get("aria-current") == "page" else "false") for a in links}


def test_covered_days_are_the_paid_periods_of_the_plans_that_book_termini(monkeypatch):
    monkeypatch.setattr(config, "today", lambda: date(2026, 10, 18))
    autumn = (date(2026, 8, 1), date(2026, 12, 31))
    uid = make_user("ivan@test.local")                           # grupni
    _due(uid, date(2026, 10, 25))                                # cycle 25.9.–24.10., dospijeće 1.11.
    assert db.covered_days(uid, *autumn) == _days(date(2026, 9, 25), date(2026, 11, 1))
    assert db.covered_days(uid, date(2026, 10, 1), date(2026, 10, 31)) == \
        _days(date(2026, 10, 1), date(2026, 10, 31))             # only the days asked for
    _due(uid, date(2026, 10, 15))                                # the grace week: the paid month stays in
    assert db.covered_days(uid, *autumn) == _days(date(2026, 9, 15), date(2026, 10, 22))
    _due(uid, date(2026, 10, 1))                                 # lapsed on 8.10.: its last period, nothing after
    assert db.covered_days(uid, *autumn) == _days(date(2026, 9, 1), date(2026, 10, 8))
    _due(uid, date(2026, 12, 20))                                # paid a month ahead: from the cycle today is in
    assert db.covered_days(uid, *autumn) == _days(date(2026, 9, 20), date(2026, 12, 27))

    ana = make_user("ana@test.local", plans=("online", "prehrana"))   # no termin to hold a day
    assert db.covered_days(ana, *autumn) == set()

    both = make_user("petra@test.local", plans=("grupni", "individualni"))
    _due(both, date(2026, 9, 1))                                 # grupni: 1.8.–8.9., lapsed
    _due(both, date(2026, 11, 5), plan="individualni")           # individualni: 5.10.–12.11.
    assert db.covered_days(both, *autumn) == (_days(date(2026, 8, 1), date(2026, 9, 8))
                                              | _days(date(2026, 10, 5), date(2026, 11, 12)))


def test_month_view_tints_the_paid_period_dots_my_bookings_and_links_every_day_to_its_week():
    from qmt.models import add_month, sub_month
    from qmt.web.app import WEEKDAYS_SHORT
    uid = make_user("ivan@test.local", plans=("grupni", "online"))
    today = config.today()
    due = today + timedelta(days=10)
    _due(uid, due)                                               # grupni: sub_month(due) … due + 7 (dospijeće)
    paid = _days(sub_month(due), due + timedelta(days=7))
    booked = (today + timedelta(days=2), today + timedelta(days=9))
    for d in booked:
        db.book(uid, db.add_oneoff_session("Grupni trening", _at(d), 60, 8, None))
    c = client_for("ivan@test.local")

    def check(page: str, first: date):
        """The grid of `first`'s month: Monday-first weeks of seven, every
        cell's states and link, the label and the month links."""
        grid = page[page.index(MONTH):page.index('<div class="month-legend')]
        weeks = grid.split('<div class="mweek">')[1:]
        assert weeks and all(w.count('<a class="mday') == 7 for w in weeks)
        cells = _month_cells(page)
        days = [x["day"] for x in cells]
        last = add_month(first) - timedelta(days=1)
        assert len(days) == 7 * len(weeks) and all(b - a == timedelta(days=1) for a, b in zip(days, days[1:]))
        assert days[0].weekday() == 0 and first - timedelta(days=6) <= days[0] <= first
        assert days[-1].weekday() == 6 and last <= days[-1] <= last + timedelta(days=6)
        for x in cells:
            d, cls = x["day"], x["classes"]
            inside = d.month == first.month
            assert x["href"] == f"/raspored?week={d - timedelta(days=d.weekday())}&day={d}", x
            assert ("other" in cls) != inside and ("past" in cls) == (d < today), x
            assert ("today" in cls) == (d == today) == (x.get("aria-current") == "date"), x
            assert ("covered" in cls) == (inside and d in paid), x       # other months' days: context only
            assert ("mine" in cls) == (inside and d in booked), x
            assert x["aria-label"] == (f"{WEEKDAYS_SHORT[d.weekday()]} {d:%-d.%-m.}"
                                       + (", danas" if d == today else "")
                                       + (", članarina aktivna" if "covered" in cls else "")
                                       + (", rezervacija" if "mine" in cls else "")), x
        assert f'<span class="range">{MONTHS_HR[first.month - 1]} {first.year}.</span>' in page
        assert f'<a class="btn btn-ghost btn-sm" href="/raspored?view=month&month={sub_month(first):%Y-%m}">‹ prošli mjesec</a>' in page
        assert f'<a class="btn btn-ghost btn-sm" href="/raspored?view=month&month={add_month(first):%Y-%m}">idući mjesec ›</a>' in page
        assert ('href="/raspored?view=month">danas</a>' in page) == (first != today.replace(day=1))
        return cells

    first = today.replace(day=1)
    page = c.get("/raspored?view=month").text
    cells = check(page, first)
    assert sum("today" in x["classes"] for x in cells) == 1
    assert "Članarina vrijedi do " + f"{due + timedelta(days=7):%-d.%-m.%Y.}" in page   # grupni's; online books nothing
    legend = page[page.index('<div class="month-legend'):]
    legend = legend[:legend.index("</div>")]
    assert all(t in legend for t in ("članarina aktivna", "tvoja rezervacija", "danas"))
    # the page is the month: no week buttons, grid, strip or sheet; the next
    # termin above the switch, "Moja članarina" and "Moje rezervacije" below
    for gone in ("← prošli tjedan</a>", 'data-selected="', 'class="day-strip"', 'id="sheet"'):
        assert gone not in page, gone
    assert page.index(NEXT) < page.index(SWITCH) < page.index(MONTH) < page.index("<h2>Moja članarina") \
        < page.index("<h2>Moje rezervacije</h2>")
    monday = today - timedelta(days=today.weekday())
    assert _switch(page) == {"week": (f"/raspored?week={monday}&day={today}", "false"),
                             "month": (f"/raspored?view=month&month={today:%Y-%m}", "true")}

    later = add_month(first)                                     # next month: "danas" leads back, "Tjedan" to its 1st
    page = c.get(f"/raspored?view=month&month={later:%Y-%m}").text
    dots = [x["day"] for x in cells + check(page, later) if "mine" in x["classes"]]
    assert dots and set(dots) <= set(booked)                     # each booking shows in its own month
    assert _switch(page)["week"] == (f"/raspored?week={later - timedelta(days=later.weekday())}&day={later}", "false")

    page = c.get("/raspored?view=month&month=2027-01").text      # over the year's edge
    assert '<span class="range">siječanj 2027.</span>' in page
    assert "month=2026-12" in page and "month=2027-02" in page
    this = f'<span class="range">{MONTHS_HR[today.month - 1]} {today.year}.</span>'
    for junk in ("", "nije-mjesec", "2026-13", "2026-1", "2026-10-05", "0001-01", "9999-12"):   # today's month
        page = c.get(f"/raspored?view=month&month={junk}").text
        assert this in page and 'href="/raspored?view=month">danas</a>' not in page, junk


def test_month_view_without_a_plan_tints_nothing_and_points_to_the_cjenik():
    make_user("ana@test.local", plans=())                        # no plan at all (sara in the demo)
    page = client_for("ana@test.local").get("/raspored?view=month").text
    cells = _month_cells(page)
    assert len(cells) >= 28 and not any("covered" in x["classes"] for x in cells)
    assert ('<p class="hint month-note">Nemaš aktivnu članarinu za treninge u dvorani. '
            '<a class="act" href="/moja-clanarina">Pogledaj cjenik →</a></p>') in page
    assert "Članarina vrijedi do" not in page


def test_the_switch_is_for_clients_and_the_trainer_keeps_the_week():
    make_user("trener@test.local", is_trainer=True)
    uid = make_user("ivan@test.local")
    today = config.today()
    monday = today - timedelta(days=today.weekday())
    other = monday + timedelta(days=(today.weekday() + 3) % 7)   # another day of this week
    db.add_oneoff_session("Grupni trening", _at(other), 60, 8, None)
    db.book(uid, future_session(hours_from_now=30))              # the next-termin card

    page = client_for("ivan@test.local").get(f"/raspored?week={monday}&day={other}").text
    assert _switch(page) == {"week": (f"/raspored?week={monday}&day={other}", "true"),
                             "month": (f"/raspored?view=month&month={other:%Y-%m}", "false")}
    # under the week buttons, above the next-termin card (in the week's head)
    assert page.index("idući tjedan →") < page.index(SWITCH) < page.index(NEXT) < page.index('data-selected="')
    assert MONTH not in page

    tr = client_for("trener@test.local")
    for path in ("/raspored", "/raspored?view=month", f"/raspored?view=month&month={today:%Y-%m}"):
        page = tr.get(path).text
        assert SWITCH not in page and MONTH not in page, path
        assert 'data-selected="' in page and "← prošli tjedan</a>" in page, path   # the week page
