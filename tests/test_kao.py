"""Staff act as a member ("Gledaj kao član", 26.11.2026), and the phone
reminder of the same build.

The owner: "What if we have a user selection somewhere in the app for the
admins much higher in the hierarchy and then Amir can look at the app just
like the user sees the app and he can do everything the user does in the
same way?" … "so that nothing is lost in the communication or display
between him and the user". Amir, the same day: "I ja kao admin nigdje ne
mogu vidjeti trenutne članove", "u tjelesnu kompoziciju nije dozvolio da
dodam dokument" (he was on a member's karton, the trainer's read-only view).

While a staff member (the trainer, the owner) is in a member's account,
app.current_user IS that member: every page and route behaves as for him,
his plans and gates, a staff route refused as for any member; the staff
member is the actor, beside him (app._actor). The session holds it
(as_user_id, as_seen, as_back). The bar over every page says whose account
it is and ends it ("Izađi"); the view also ends at logout and after
config.ACT_AS_IDLE_MINUTES (30) with no request, when nothing at all runs
as the staff member. A write runs only when the page it came from was
drawn for the session's identity now (the page's marker, ?kao= on a form,
X-QMT-Kao on a fetch: app._acting_guard). Closed while acting: a card
payment and sending the upitnik. Every write done so is recorded
(acting_log, migration 5e8c1a3f7b92, run for real on qmt_test there and
back), and the owner alone reads the record (/kao/zapisi). The picker
(/kao) is Admin ▾'s first item; the shortcuts are a termin's roster and the
trainer's view of a karton, and since build 4 of the same day (the owner:
"I would remove the 'Karton ->' and the 'Kao član ->' buttons here and only
leave the 'Admin -> gledaj kao član option' as well as the 'Otvori kao član'
amber button on the Karton tab of the Admin and Trainer with a search bar
where a user can be searched. The button to open as another user should also
be in amber.") the Karton tab of the trainer and the owner (POST /kao), not
/clanarine; every such button amber; and staff acting as a member read on
his karton what only the trainer's view showed of his upitnik. Since
27.11.2026 (the owner: "when a user is pressed, that user's Karton is
opened, not the whole app as his view, but just his Karton which will be
searchable for Amir") the Karton tab's field is a search that opens the
member's karton, the trainer's view (GET /karton/clan), staff's again;
POST /kao and its solid amber button went.

The phone reminder (the owner: "if a user didnt give it, when he opens the
app a popup reminder should appear similarly how a popup appears as a
notification to install the app on the phone"): the install banner's card
for a member with no phone number, on every page but a one-task page and
/profil, away a week after its ✕, never on the load the install banner
shows on. The seconds in steps of 5 and the 20 sets are
tests/test_player.py's and tests/test_karton.py's, the height on the karton
tests/test_karton.py's.

The browser half walks the picker into a member's account at 390 and 360px
(touch) and back out, the Karton tab's search into a member's karton at the
same widths, and the phone reminder at 390 and 1280px."""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import pathlib
import re
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from html import unescape
from urllib.parse import unquote

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect, text as sa_text
from starlette.requests import Request

from qmt import auth, config, copy, db, upitnik
from qmt.models import Base, Booking, User
from qmt.web import app as web
from qmt.web.app import app

PORT = 8117    # test_copy's server is 8111, test_raspored_ui's and test_upitnik_ui's 8112, test_nav's 8113,
               # test_programs' 8114, test_player's 8115, test_karton's 8116


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # a document saved as a member lands in a throwaway dir, never the real
    # data/uploads nor a real R2 bucket (a developer's .env may carry live
    # R2_* keys); the browser test's server is a thread of this process
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "")
    yield


def make_user(email: str, name: str = "", is_trainer: bool = False, plans: tuple[str, ...] = (),
              phone: str = "") -> int:
    """An account, verified and with a complete profile: `name` its first
    and last name ("Ivan Horvat"; its email's first part and "Test" with
    none), `plans` recorded today, `phone` its phone number."""
    first, _, last = (name or f"{email.split('@')[0]} Test").partition(" ")
    u = db.create_user(email, first, auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    db.update_profile(u.id, first, last, date(1990, 1, 1), phone)
    if is_trainer:
        with db.session_scope() as s:
            s.get(User, u.id).is_trainer = True
    for plan in plans:
        db.record_payment(u.id, plan)
    return u.id


def people() -> tuple[int, int, int, int, int]:
    """(coach, the owner, ivan, ana, sara): a trainer who is not the owner,
    the owner (OWNER_EMAIL) who does not train, and three members: ivan
    with grupni and online (his upitnik filled, srednja), ana with grupni,
    sara with no plan."""
    coach = make_user("coach@test.local", "Amir Trener", is_trainer=True)
    owner = make_user("trener@test.local", "Tvrtko Vlasnik")
    ivan = make_user("ivan@test.local", "Ivan Horvat", plans=("grupni", "online"))
    db.save_onboarding(ivan, json.dumps({q["key"]: 0 for q in upitnik.QUESTIONS_V1}), 0, "srednja", "cijelo",
                       version=1, pain_level=None, pain_high=False, needs_review=False, consented_at=None)
    ana = make_user("ana@test.local", "Ana Kovač", plans=("grupni",))
    sara = make_user("sara@test.local", "Sara Jurić")
    return coach, owner, ivan, ana, sara


def client_for(email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"email": email, "password": "lozinka123"}, follow_redirects=False)
    assert r.status_code == 303, "login failed"
    return c


def enter(c: TestClient, member: int, **form):
    """POST /kao/<member> (the picker's "Otvori →"), not followed."""
    return c.post(f"/kao/{member}", data=form, follow_redirects=False)


def location(r) -> str:
    """A redirect's location as a person reads it ("+" a space)."""
    return unquote(r.headers["location"]).replace("+", " ")


def session_of(c: TestClient) -> dict:
    """The client's session as the app keeps it (Starlette's signed cookie)."""
    from itsdangerous import TimestampSigner

    raw = c.cookies.get("session")
    if not raw:
        return {}
    return json.loads(base64.b64decode(TimestampSigner(str(config.SECRET_KEY)).unsign(raw.encode())))


def record() -> list[tuple]:
    """The record, newest first: (who, as whom, method, path, status)."""
    rows, _ = db.acting_log()
    return [(r.actor_name, r.member_name, r.method, r.path, r.status) for r in rows]


def bar(page: str) -> str | None:
    """The strip over a page while acting, or None."""
    m = re.search(r'<div class="kao-bar" role="status">.*?</div>', page, re.S)
    return m.group(0) if m else None


STALE = "/karton?error=Stranica je bila otvorena prije ulaska u pregled kao član — ništa nije spremljeno."
ENDED = "/kao?error=Pregled kao član je završen — ništa nije spremljeno."
EXPIRED = "/kao?error=Pregled kao član je istekao — odaberi člana ponovno."


# ---------- the migration ----------

def _migration(file: str):
    path = pathlib.Path(__file__).parents[1] / "alembic" / "versions" / file
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _run(step) -> None:
    """A revision's upgrade() or downgrade(), run for real on qmt_test."""
    with db.engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        step()


def _schema_diffs(table: str) -> list:
    """What compare_metadata finds between qmt_test and the models about one table."""
    from alembic.autogenerate import compare_metadata

    def about(d):
        d = d[0] if isinstance(d, list) else d
        kind, obj = d[0], d[1]
        if kind.startswith("modify_") or kind in ("add_column", "remove_column"):
            return d[2]
        if kind in ("add_table", "remove_table"):
            return obj.name
        if kind in ("add_fk", "remove_fk"):
            return obj.parent.name
        return obj.table.name

    with db.engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    return [d for d in diffs if about(d) == table]


def test_the_migration_makes_the_record_and_takes_it_away():
    """5e8c1a3f7b92, run on qmt_test as before it (no acting_log): the
    table as the model has it, its index on `at`; a deleted member leaves
    his rows (SET NULL), his name kept; downgrade drops it, and a second
    upgrade makes it again, empty."""
    mig = _migration("5e8c1a3f7b92_acting_log.py")
    assert (mig.revision, mig.down_revision) == ("5e8c1a3f7b92", "d0ed87d5c98f")
    with db.engine.begin() as conn:
        conn.execute(sa_text("DROP TABLE acting_log"))
    _run(mig.upgrade)
    assert "acting_log" in sa_inspect(db.engine).get_table_names() and _schema_diffs("acting_log") == []
    assert {i["name"] for i in sa_inspect(db.engine).get_indexes("acting_log")} == {"ix_acting_log_at"}
    coach, ivan = make_user("coach@test.local", "Amir Trener", is_trainer=True), make_user("ivan@test.local", "Ivan Horvat")
    db.record_acting(db.get_user(coach), db.get_user(ivan), "POST", "/karton/masa", 303)
    with db.engine.begin() as conn:
        conn.execute(sa_text("DELETE FROM users WHERE id = :i"), {"i": ivan})
    rows, older = db.acting_log()
    assert [(r.actor_id, r.member_id, r.actor_name, r.member_name, r.method, r.path, r.status) for r in rows] == [
        (coach, None, "Amir Trener", "Ivan Horvat", "POST", "/karton/masa", 303)] and not older
    _run(mig.downgrade)
    assert "acting_log" not in sa_inspect(db.engine).get_table_names()
    _run(mig.upgrade)
    assert _schema_diffs("acting_log") == [] and db.acting_log() == ([], False)


# ---------- entering ----------

def test_staff_enter_a_members_account_and_the_app_is_his():
    """The trainer and the owner (who does not train) each enter ivan's
    account from the picker: POST /kao/<id> → his karton; the session
    holds him (as_user_id), when (as_seen) and where "Izađi" returns
    (as_back, /kao by default). current_user is the member, _actor the
    staff member; without the view, the staff member himself and no actor."""
    coach, owner, ivan, ana, sara = people()
    for email, staff in (("coach@test.local", coach), ("trener@test.local", owner)):
        c = client_for(email)
        before = time.time()
        r = enter(c, ivan)
        assert r.status_code == 303 and r.headers["location"] == "/karton", email
        s = session_of(c)
        assert (s["user_id"], s["as_user_id"], s["as_back"]) == (staff, ivan, "/kao") and before - 1 <= s["as_seen"] <= time.time()
        page = c.get("/karton").text
        assert f'<body data-kao="{ivan}">' in page and "Gledaš kao: <strong>Ivan Horvat</strong>" in page
    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
    acting = Request({**scope, "session": {"user_id": coach, "as_user_id": ivan}})
    assert web.current_user(acting).id == ivan and web._actor(acting).id == coach
    plain = Request({**scope, "session": {"user_id": coach}})
    assert web.current_user(plain).id == coach and web._actor(plain) is None
    odd = Request({**scope, "session": {"user_id": coach, "as_user_id": owner}})      # never another staff member
    assert web.current_user(odd) is None and web._actor(odd) is None


def test_only_staff_enter_and_only_a_members_account():
    """A member is refused (403, as any staff route refuses him), a guest
    goes to log in; nobody enters a trainer's or the owner's account ("U
    račun trenera ili vlasnika se ne ulazi.", back to the picker), and an
    account that is not there is 404. None of it starts a view or a row."""
    coach, owner, ivan, ana, sara = people()
    other = make_user("druga@test.local", "Druga Trenerica", is_trainer=True)
    member = client_for("ivan@test.local")
    assert enter(member, ana).status_code == 403
    guest = TestClient(app)
    r = enter(guest, ivan)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    c = client_for("coach@test.local")
    for staff in (owner, other, coach):
        r = enter(c, staff)
        assert location(r) == "/kao?error=U račun trenera ili vlasnika se ne ulazi.", staff
    assert enter(c, 999999).status_code == 404
    assert "as_user_id" not in session_of(c) and "as_user_id" not in session_of(member) and record() == []


# ---------- the member's app, as he has it ----------

def _staff_routes() -> list[tuple[str, str, dict]]:
    """Every route that only staff may use (its endpoint calls
    _require_trainer or _require_owner: a name its code loads, read from
    the code itself, not its source text, which a docstring could name and
    an edit of the file could shift), as (method, path with its
    parameters filled, the form fields it requires)."""
    out = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        names = route.endpoint.__code__.co_names
        if "_require_trainer" not in names and "_require_owner" not in names:
            continue
        path = re.sub(r"\{(\w+)\}", lambda m: "trening" if m.group(1) == "section" else "1", route.path)
        form = {p.alias: "1" for p in route.dependant.body_params if p.field_info.is_required()}
        for method in sorted(route.methods - {"HEAD"}):
            out.append((method, path, form))
    return out


def test_acting_the_member_gets_his_pages_and_no_staff_route():
    """As ivan: his karton (his mass, not the coach's), his raspored (his
    booking as "Tvoj sljedeći termin"), the member's bar of tabs (no Admin
    ▾), no ✎ pill and no editor's markup anywhere; and every route only
    staff may use, walked from the app's own routes (GET, and every write
    with his page's marker, so the route itself answers), refuses him as
    it refuses any member: 403."""
    coach, owner, ivan, ana, sara = people()
    today = config.today()
    db.set_weight(ivan, today, Decimal("82.5"))
    db.set_weight(coach, today, Decimal("91"))
    sid = db.add_oneoff_session("Grupni trening srijedom", datetime.now(config.TZ) + timedelta(days=2), 60, 8, None)
    db.book(ivan, sid)
    c = client_for("coach@test.local")
    enter(c, ivan)
    karton = c.get("/karton").text
    assert "82,5 kg" in karton and "91 kg" not in karton and "<h1><span class=\"t\">Moj karton</span></h1>" in karton
    raspored = c.get("/raspored").text
    assert 'id="ntKicker"' in raspored and "Grupni trening srijedom" in raspored   # his next termin's card
    for page in (karton, raspored, c.get("/").text, c.get("/moja-clanarina").text):
        assert 'id="adminBtn"' not in page and 'id="copyToggle"' not in page and "data-copy=" not in page
        assert 'href="/korisnici"' not in page and 'href="/kao"' not in page
    walked = _staff_routes()
    paths = {path for _, path, _ in walked}
    assert {"/kao", "/kao/zapisi", "/kao/1", "/admin", "/clanarine", "/korisnici", "/statistika", "/tekstovi",
            "/karton/1", "/karton/clan", "/treninzi/vjezbe", "/upitnik/pitanje/1"} <= paths and len(walked) > 40
    refused = [(method, path) for method, path, form in walked
               if c.request(method, path + f"?kao={ivan}", data=form or None,
                            follow_redirects=False).status_code != 403]
    assert refused == [], refused
    assert session_of(c)["as_user_id"] == ivan                       # and still in his account


def test_the_bar_is_on_every_page_while_acting_and_never_otherwise():
    """The strip: on a normal page, the error page, the upitnik and the
    player (the one-task pages, the brand-only pill under it), its words
    "Gledaš kao: <the name>", the whole name and the email in its title,
    "Izađi" a form to /kao/izlaz; the page carries his id. Never without
    the view: not on the staff member's own pages, nor on the member's
    own. The install banner is not offered while acting (it is about the
    device), and entering arms no osvrt prompt (ivan's finished termin with
    no osvrt would show in it): since 26.11.2026 no staff login arms one,
    the owner's neither, whatever his trainer flag (staff by rule; until
    then the login of an owner who does not train armed one, and entering
    took it)."""
    coach, owner, ivan, ana, sara = people()
    sid = db.add_oneoff_session("Jutarnji trening", datetime.now(config.TZ) - timedelta(hours=3), 60, 8, None)
    with db.session_scope() as s:                                      # a termin behind him, no osvrt
        s.add(Booking(user_id=ivan, session_id=sid))
    ex = db.create_exercise("Plank")
    pid = db.create_program("Cijelo tijelo", None, "srednja", "cijelo")
    did = db.add_day(pid)
    db.update_day_item(db.add_day_item(did, ex, "trening"), "trening", 3, None, 40, None, None, "")
    own = client_for("ivan@test.local")
    mine = own.get("/raspored").text
    assert bar(mine) is None and 'data-kao="' not in mine and 'id="a2hs"' in mine
    c = client_for("trener@test.local")                                # the owner, staff by rule: no prompt armed
    assert "fb_prompt" not in session_of(c)
    assert bar(c.get("/kao").text) is None
    enter(c, ivan, kamo="/raspored")
    pages = {"raspored": c.get("/raspored").text, "error": c.get("/admin").text, "upitnik": c.get("/upitnik").text}
    step = c.post(f"/treninzi/{pid}/dan/{did}/kreni?kao={ivan}", follow_redirects=False)
    pages["player"] = c.get(step.headers["location"]).text
    for name, page in pages.items():
        strip = bar(page)
        assert strip is not None and f'<body data-kao="{ivan}">' in page, name
        assert 'title="Ivan Horvat · ivan@test.local">Gledaš kao: <strong>Ivan Horvat</strong>' in strip, name
        assert '<form method="post" action="/kao/izlaz"><button type="submit" class="kao-exit">Izađi</button></form>' in strip
        assert 'id="a2hs"' not in page and 'id="fbPrompt"' not in page, name
    assert "<h1" in pages["error"] and "403" in pages["error"]
    for name in ("upitnik", "player"):                                 # the one-task pages: the brand alone under it
        assert '<header class="topbar compact">' in pages[name] and 'id="mainNav"' not in pages[name], name
    assert "fb_prompt" not in session_of(c)
    c.post("/kao/izlaz")
    assert bar(c.get("/kao").text) is None and 'data-kao="' not in c.get("/").text


def test_a_karton_form_saves_into_the_members_karton_and_nobody_elses():
    """Amir's case: a document on "Tjelesna kompozicija", sent as ivan
    from his karton's form (multipart, his page's marker), is ivan's
    entry, and so is his limitations' text; the coach's own karton (staff
    have one) and ana's get nothing."""
    coach, owner, ivan, ana, sara = people()
    c = client_for("coach@test.local")
    enter(c, ivan)
    today = config.today()
    r = c.post(f"/karton/masa?kao={ivan}", data={"kg": "", "day": today.isoformat()},
               files={"dokument": ("sastav.pdf", b"%PDF-1.4\n%test\n", "application/pdf")}, follow_redirects=False)
    assert location(r) == "/karton?ok=Dokument je spremljen.#masa"
    [entry] = db.weights(ivan)
    assert entry.kg is None and entry.file.startswith(f"sastav-{ivan}-") and entry.file_name == "sastav.pdf"
    r = c.post(f"/karton/ogranicenja?kao={ivan}", data={"text": "Koljeno."}, follow_redirects=False)
    assert location(r) == "/karton?ok=Ograničenja su spremljena.#ogranicenja"
    assert db.get_user(ivan).limitations == "Koljeno."
    assert db.weights(coach) == [] == db.weights(ana)
    assert db.get_user(coach).limitations == "" == db.get_user(ana).limitations
    assert "sastav.pdf" in c.get("/karton").text                       # on his karton, as he sees it


def test_booking_as_the_member_obeys_his_plan():
    """The member's rules hold: sara, with no plan, cannot book (the plan's
    refusal, its offer of the price list), nor is anyone else booked; ivan,
    with grupni, books the termin, his booking alone."""
    coach, owner, ivan, ana, sara = people()
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + timedelta(days=2), 60, 8, None)
    c = client_for("coach@test.local")
    enter(c, sara)
    r = c.post(f"/book/{sid}?kao={sara}", follow_redirects=False)
    assert "error=" in r.headers["location"] and "cta=grupni" in r.headers["location"]
    assert db.roster(sid) == []
    c.post("/kao/izlaz")
    enter(c, ivan)
    r = c.post(f"/book/{sid}?kao={ivan}", follow_redirects=False)
    assert location(r).startswith("/raspored?ok=Rezervirano ✓")
    assert [u.id for u in db.roster(sid)] == [ivan]


def test_card_payments_and_the_upitnik_are_closed_while_acting():
    """The three card routes say "Plaćanje karticom pokreće član sam."
    (nothing sent to Stripe), the upitnik's submission "Upitnik ispunjava
    član sam — privola mora biti njegova." (nothing stored: its consent is
    the member's). The member himself is answered as before."""
    coach, owner, ivan, ana, sara = people()
    before = db.get_onboarding(ivan).level
    c = client_for("coach@test.local")
    enter(c, ivan)
    for path, form in (("/placanje/portal", {}), ("/placanje/grupni/promjena", {"sessions": "8"}),
                       ("/placanje/online", {"tier": "pro"})):
        r = c.post(f"{path}?kao={ivan}", data=form, follow_redirects=False)
        assert location(r) == "/moja-clanarina?error=Plaćanje karticom pokreće član sam.", path
    r = c.post(f"/upitnik?kao={ivan}", data={"consent": "1"}, follow_redirects=False)
    assert location(r) == "/upitnik?od=1&error=Upitnik ispunjava član sam — privola mora biti njegova."
    assert db.get_onboarding(ivan).level == before and db.get_onboarding(coach) is None
    r = client_for("ivan@test.local").post("/placanje/portal", follow_redirects=False)
    assert location(r) == "/moja-clanarina?error=Nemaš aktivnu pretplatu karticom."


# ---------- leaving ----------

def test_izadji_goes_back_and_logout_ends_both():
    """"Izađi" ends the view and goes where it was entered from (natrag:
    /clanarine; /kao when none was given; a path of another site never,
    "/" then), its page's marker or none; `kamo` is where the entry
    lands. The logout, from a page of the view, logs the staff member out
    and ends the view with him."""
    coach, owner, ivan, ana, sara = people()
    c = client_for("coach@test.local")
    r = enter(c, ivan, natrag="/clanarine", kamo="/raspored")
    assert r.headers["location"] == "/raspored"
    r = c.post("/kao/izlaz", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/clanarine"
    assert {k for k in session_of(c) if k.startswith("as_")} == set()
    page = c.get("/karton").text
    assert 'data-kao="' not in page and 'id="adminBtn"' in page          # his own karton again
    enter(c, ivan)
    assert c.post(f"/kao/izlaz?kao={ivan}", follow_redirects=False).headers["location"] == "/kao"
    for unsafe in ("https://evil.example/", "//evil.example"):
        assert enter(c, ivan, natrag=unsafe, kamo=unsafe).headers["location"] == "/"
        assert c.post("/kao/izlaz", follow_redirects=False).headers["location"] == "/"
    assert c.post("/kao/izlaz", follow_redirects=False).headers["location"] == "/kao"   # out already: the picker
    enter(c, ivan)
    r = c.post("/logout", follow_redirects=False)
    assert r.headers["location"] == "/" and session_of(c) == {}
    assert c.get("/karton", follow_redirects=False).headers["location"].startswith("/login")


def test_the_idle_limit_ends_the_view_and_runs_nothing(monkeypatch):
    """After ACT_AS_IDLE_MINUTES (30) with no request the first request,
    GET or POST, runs nothing: its three keys go, back to the picker
    saying so ("Pregled kao član je istekao — odaberi člana ponovno."),
    and a form left open on the member's karton saves into no karton, his
    nor the coach's own. Each request moves the limit on. A logout after
    it still logs out. The same when the member has become staff or is
    gone; an actor who is no longer staff goes to /. The knob is read
    from the environment (30 when unset)."""
    coach, owner, ivan, ana, sara = people()
    now = [time.time()]
    monkeypatch.setattr(web, "_clock", lambda: now[0])
    c = client_for("coach@test.local")
    enter(c, ivan)
    now[0] += 29 * 60
    assert c.get("/karton").status_code == 200                         # within the limit: and it moves on
    now[0] += 29 * 60
    assert c.get("/karton").status_code == 200
    now[0] += 31 * 60
    r = c.get("/karton", follow_redirects=False)
    assert location(r) == EXPIRED and {k for k in session_of(c) if k.startswith("as_")} == set()
    enter(c, ivan)
    now[0] += 31 * 60
    r = c.post(f"/karton/ogranicenja?kao={ivan}", data={"text": "Leđa."}, follow_redirects=False)
    assert location(r) == EXPIRED and "as_user_id" not in session_of(c)
    assert db.get_user(ivan).limitations == "" == db.get_user(coach).limitations
    monkeypatch.setattr(config, "ACT_AS_IDLE_MINUTES", 5)              # the knob
    enter(c, ivan)
    now[0] += 4 * 60
    assert c.get("/karton").status_code == 200
    now[0] += 6 * 60
    assert location(c.get("/karton", follow_redirects=False)) == EXPIRED
    enter(c, ivan)
    now[0] += 6 * 60
    r = c.post("/logout", follow_redirects=False)                      # the logout still runs
    assert r.headers["location"] == "/" and session_of(c) == {}
    monkeypatch.setattr(config, "ACT_AS_IDLE_MINUTES", 30)
    c = client_for("coach@test.local")
    enter(c, ivan)
    with db.session_scope() as s:                                      # the member made staff meanwhile
        s.get(User, ivan).is_trainer = True
    assert location(c.get("/karton", follow_redirects=False)) == EXPIRED and "as_user_id" not in session_of(c)
    with db.session_scope() as s:
        s.get(User, ivan).is_trainer = False
    enter(c, ana)
    with db.engine.begin() as conn:                                    # the member gone
        conn.execute(sa_text("DELETE FROM users WHERE id = :i"), {"i": ana})
    assert location(c.get("/karton", follow_redirects=False)) == EXPIRED and "as_user_id" not in session_of(c)
    enter(c, ivan)
    with db.session_scope() as s:                                      # the actor no longer staff
        s.get(User, coach).is_trainer = False
    r = c.get("/karton", follow_redirects=False)
    assert r.headers["location"] == "/" and "as_user_id" not in session_of(c) and session_of(c)["user_id"] == coach

    import subprocess
    import sys
    read = "from qmt import config; print(config.ACT_AS_IDLE_MINUTES)"
    env = {k: v for k, v in os.environ.items() if k != "ACT_AS_IDLE_MINUTES"}
    assert subprocess.run([sys.executable, "-c", read], env=env, capture_output=True, text=True, check=True).stdout.split() == ["30"]
    env["ACT_AS_IDLE_MINUTES"] = "7"
    assert subprocess.run([sys.executable, "-c", read], env=env, capture_output=True, text=True, check=True).stdout.split() == ["7"]


def test_a_page_drawn_for_another_identity_saves_nothing():
    """A write runs only when its page was drawn for the session's identity
    now. A form left open on ivan's karton after "Izađi" in another tab
    (its marker, no view): nothing, back to the picker ("Pregled kao član
    je završen — ništa nije spremljeno."). The staff member's own karton,
    open while another tab entered ivan's account (no marker): nothing,
    back to the member's karton ("Stranica je bila otvorena prije ulaska u
    pregled kao član — ništa nije spremljeno."). Ana's page while the view
    is ivan's (her marker): the same. Nothing saved anywhere, in either
    direction. A fetch says it in its header (X-QMT-Kao); the exit and the
    logout always pass."""
    coach, owner, ivan, ana, sara = people()
    c = client_for("coach@test.local")
    enter(c, ivan)
    c.post("/kao/izlaz")
    r = c.post(f"/karton/ogranicenja?kao={ivan}", data={"text": "Ramena."}, follow_redirects=False)
    assert location(r) == ENDED
    enter(c, ivan)
    r = c.post("/karton/ogranicenja", data={"text": "Moja leđa."}, follow_redirects=False)
    assert location(r) == STALE
    r = c.post(f"/karton/ogranicenja?kao={ivan}", data={"text": "Moja leđa."}, headers={"X-QMT-Kao": str(ana)},
               follow_redirects=False)
    assert location(r) == "/karton?ok=Ograničenja su spremljena.#ogranicenja"      # the query's: his
    c.post(f"/karton/ogranicenja?kao={ivan}", data={"text": ""})
    c.post("/kao/izlaz")
    enter(c, ana)
    r = c.post(f"/karton/ogranicenja?kao={ivan}", data={"text": "Ivanova stranica."}, follow_redirects=False)
    assert location(r) == STALE
    assert {u: db.get_user(u).limitations for u in (coach, ivan, ana)} == {coach: "", ivan: "", ana: ""}
    r = c.post("/karton/ogranicenja", data={"text": "Fetch."}, headers={"X-QMT-Kao": str(ana)}, follow_redirects=False)
    assert location(r) == "/karton?ok=Ograničenja su spremljena.#ogranicenja" and db.get_user(ana).limitations == "Fetch."
    assert c.post("/kao/izlaz", follow_redirects=False).headers["location"] == "/kao"   # no marker: it passes
    r = client_for("ivan@test.local").post(f"/karton/ogranicenja?kao={ana}", data={"text": "x"}, follow_redirects=False)
    assert location(r) == ENDED and db.get_user(ivan).limitations == ""   # a member's own session, a marker: nothing


def test_the_record_holds_every_write_done_as_a_member_and_nothing_else(monkeypatch):
    """A row for the entry, for every write that runs while acting (its
    status; None when the app failed under it) and for the exit; none for
    a GET, none for a write refused before it ran, none outside the view.
    A record that cannot be written fails nothing."""
    coach, owner, ivan, ana, sara = people()
    c = client_for("coach@test.local")
    enter(c, ivan)
    c.get("/karton"); c.get("/raspored")
    c.post(f"/karton/ogranicenja?kao={ivan}", data={"text": "Koljeno."})
    c.post("/karton/ogranicenja", data={"text": "bez oznake"})          # refused: no row
    c.post(f"/karton/visina?kao={ivan}", data={"visina": "abc"})        # refused by the route: a row, its status
    c.post("/kao/izlaz")
    client_for("ivan@test.local").post("/karton/ogranicenja", data={"text": "Sam."})   # his own: no row
    who, whom = "Amir Trener", "Ivan Horvat"
    assert record() == [(who, whom, "POST", "/kao/izlaz", 303), (who, whom, "POST", "/karton/visina", 303),
                        (who, whom, "POST", "/karton/ogranicenja", 303), (who, whom, "POST", f"/kao/{ivan}", 303)]

    failing = TestClient(app, raise_server_exceptions=False)
    failing.post("/login", data={"email": "coach@test.local", "password": "lozinka123"})
    enter(failing, ana)

    def broken(*args, **kwargs):
        raise RuntimeError("the database is gone")

    keep = db.set_limitations
    monkeypatch.setattr(db, "set_limitations", broken)
    assert failing.post(f"/karton/ogranicenja?kao={ana}", data={"text": "x"}).status_code == 500
    assert record()[0] == (who, "Ana Kovač", "POST", "/karton/ogranicenja", None)
    monkeypatch.setattr(db, "set_limitations", keep)
    monkeypatch.setattr(db, "record_acting", broken)                   # the record fails: the write stands
    r = failing.post(f"/karton/ogranicenja?kao={ana}", data={"text": "Kuk."}, follow_redirects=False)
    assert r.status_code == 303 and db.get_user(ana).limitations == "Kuk."


def test_the_owner_reads_the_record_and_nobody_else():
    """/kao/zapisi, "Radnje u ime članova": the owner's (from the picker's
    "Zapis svih radnji →" and /korisnici's lead); the trainer and a member
    are refused, a guest goes to log in. Newest first, its time in Zagreb
    ("20.11.2026. 14:03:07"), who, as whom, the method and the path, the
    status ("—" for none); 100 a page, "Starije" to the next (?str=2) and
    "Novije" back; empty, "Još nema zapisa.". The cells carry their
    classes (who, as, st): on a phone a row is three lines, the time, "who
    → as whom", the action and its status (kao_zapisi.html's CSS)."""
    coach, owner, ivan, ana, sara = people()
    o = client_for("trener@test.local")
    page = o.get("/kao/zapisi").text
    assert "<h1>Radnje u ime članova</h1>" in page and "Još nema zapisa." in page and "<table" not in page
    assert 'href="/kao/zapisi"' in o.get("/kao").text and 'href="/kao/zapisi"' in o.get("/korisnici").text
    assert client_for("coach@test.local").get("/kao/zapisi").status_code == 403
    assert 'href="/kao/zapisi"' not in client_for("coach@test.local").get("/kao").text
    assert client_for("ivan@test.local").get("/kao/zapisi").status_code == 403
    assert TestClient(app).get("/kao/zapisi", follow_redirects=False).headers["location"] == "/login"
    cu, iu = db.get_user(coach), db.get_user(ivan)
    db.record_acting(cu, iu, "POST", "/karton/masa", None)
    for n in range(100):
        db.record_acting(cu, iu, "POST", f"/karton/log/{n}/edit", 303)
    with db.engine.begin() as conn:                                    # the first one at a known time
        conn.execute(sa_text("UPDATE acting_log SET at = :at WHERE path = '/karton/masa'"),
                     {"at": datetime(2026, 11, 20, 14, 3, 7, tzinfo=config.TZ)})
    first = o.get("/kao/zapisi").text
    cells = re.findall(r"<tr>\s*<td class=\"num when\">([^<]*)</td>\s*<td class=\"who\">([^<]*)</td>\s*"
                       r"<td class=\"as\">([^<]*)</td>\s*"
                       r"<td class=\"num\">([^<]*)</td>\s*<td class=\"num st\">([^<]*)</td>\s*</tr>", first)
    assert len(cells) == 100 and cells[0][1:] == ("Amir Trener", "Ivan Horvat", "POST /karton/log/99/edit", "303")
    assert 'href="/kao/zapisi?str=2">Starije →</a>' in first and "← Novije</a>" not in first
    second = o.get("/kao/zapisi?str=2").text
    cells = re.findall(r'<td class="num when">([^<]*)</td>\s*<td class="who">[^<]*</td>\s*<td class="as">[^<]*</td>\s*'
                       r'<td class="num">([^<]*)</td>\s*<td class="num st">([^<]*)</td>', second)
    assert cells == [("20.11.2026. 14:03:07", "POST /karton/masa", "—")]
    assert 'href="/kao/zapisi">← Novije</a>' in second and "Starije →</a>" not in second
    assert o.get("/kao/zapisi?str=abc").text.count('<td class="num when">') == 100


# ---------- the picker and the shortcuts ----------

def test_the_picker_lists_every_member_in_the_alphabets_order():
    """/kao, "Gledaj kao član": every member (no trainer, not the owner),
    in the alphabet's order by his full name (Čedo after Cvita, before
    Dario), by the email for one with none; a row each, the name in 700,
    the email, his running plans by their names in the plans' order ("bez
    članarine" for none: a lapsed plan runs no more), "Otvori →" posting
    /kao/<id> (amber since build 4, .act-kao); the search's box and lines
    rendered hidden (the script's);
    Admin ▾ lit there, its item current. The trainer's and the owner's; a
    member is refused, a guest goes to log in."""
    coach = make_user("coach@test.local", "Amir Trener", is_trainer=True)
    make_user("trener@test.local", "Tvrtko Vlasnik")
    dario = make_user("dario@test.local", "Dario Kovač", plans=("prehrana",))
    cedo = make_user("cedo@test.local", "Čedo Babić", plans=("online", "grupni"))
    cvita = make_user("cvita@test.local", "Cvita Horvat")
    u = db.create_user("bez.imena@test.local", "", auth.hash_password("lozinka123"))
    db.mark_email_verified("bez.imena@test.local")
    with db.engine.begin() as conn:                                    # dario's plan has lapsed
        conn.execute(sa_text("UPDATE memberships SET next_payment = next_payment - 60 WHERE user_id = :u"), {"u": dario})
    page = client_for("coach@test.local").get("/kao").text
    rows = re.findall(r'<div class="kao-row" data-find="([^"]*)">\s*<div class="kao-who">\s*<strong>([^<]*)</strong>\s*'
                      r'(?:<span class="kao-mail">([^<]*)</span>)?\s*<span class="kao-plans">([^<]*)</span>\s*</div>\s*'
                      r'<form method="post" action="/kao/(\d+)"><button type="submit" class="act act-kao">Otvori →</button></form>',
                      page)
    assert [(unescape(f), n, m, p, int(i)) for f, n, m, p, i in rows] == [
        ("bez.imena@test.local · bez.imena@test.local", "bez.imena@test.local", "", "bez članarine", u.id),
        ("Cvita Horvat · cvita@test.local", "Cvita Horvat", "cvita@test.local", "bez članarine", cvita),
        ("Čedo Babić · cedo@test.local", "Čedo Babić", "cedo@test.local", "Grupni trening · Online trening", cedo),
        ("Dario Kovač · dario@test.local", "Dario Kovač", "dario@test.local", "bez članarine", dario)]
    assert 'class="kao-search" role="search" hidden' in page and 'class="hint kao-found" aria-live="polite" hidden' in page
    assert '<p class="kao-none" hidden>Nijedan član ne odgovara traženju' in page
    assert "Amir Trener" not in page.split("<main")[1] and "Tvrtko Vlasnik" not in page.split("<main")[1]
    assert re.search(r'<a href="/kao" role="menuitem" aria-current="page">', page)
    assert client_for("cvita@test.local").get("/kao").status_code == 403
    assert TestClient(app).get("/kao", follow_redirects=False).headers["location"] == "/login"
    with db.engine.begin() as conn:                                    # an empty picker
        conn.execute(sa_text("DELETE FROM users WHERE id <> :c"), {"c": coach})
    assert "Još nema članova." in client_for("coach@test.local").get("/kao").text


def test_the_shortcuts_lead_into_the_members_account():
    """"Kao član →" at the end of each booked member's row of a termin's
    roster (none for staff) and "Otvori kao član" on the trainer's view of
    a member's karton (none on a staff member's; the view the trainer's and
    the owner's alike, staff's again since 27.11.2026, when the Karton tab's
    search came to open it): each into his account, its "Izađi" back where
    it was pressed. /clanarine has none since build 4 (the owner: "I would
    remove the 'Karton ->' and the 'Kao član ->' buttons here"): no form
    into an account, no link to a karton, beside no member (the owner, who
    does not train, is not listed there since 26.11.2026: staff by rule,
    db.memberships_overview)."""
    coach, owner, ivan, ana, sara = people()
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + timedelta(days=1), 60, 8, None)
    db.book(ivan, sid)
    with db.session_scope() as s:                                      # a staff member in the roster too
        s.add(Booking(user_id=coach, session_id=sid))
    c = client_for("coach@test.local")
    clanarine = c.get("/clanarine").text.split("<main")[1]
    assert f'action="/clanarine/{ivan}/uplata"' in clanarine            # his card is there,
    assert 'action="/kao' not in clanarine and 'href="/karton/' not in clanarine   # its two buttons are not
    assert "Kao član →" not in clanarine and "Karton →" not in clanarine and "row-acts" not in clanarine
    assert f'action="/clanarine/{owner}/' not in clanarine              # the owner: not listed at all
    roster = c.get(f"/admin/session/{sid}").text
    assert (f'<form method="post" action="/kao/{ivan}">\n      <input type="hidden" name="natrag" value="/admin/session/{sid}">\n'
            f'      <input type="hidden" name="kamo" value="/dvoranski/termin/{sid}">\n'   # his training of it (build 3; /dvoranski since 27.11.2026)
            '      <button type="submit" class="act act-kao">Kao član →</button>') in roster
    assert f'action="/kao/{coach}"' not in roster
    # a member's karton, /karton/<id>, is staff's again since 27.11.2026: the
    # Karton tab's search leads the trainer there (it was the owner's alone
    # for some hours that day), and its "Otvori kao član" is his as the owner's
    o = client_for("trener@test.local")
    form = (f'<form class="kao-open" method="post" action="/kao/{ivan}">\n  <input type="hidden" name="natrag" '
            f'value="/karton/{ivan}">\n  <button type="submit" class="act act-kao">Otvori kao član</button>')
    for who in (c, o):
        r = who.get(f"/karton/{ivan}")
        assert r.status_code == 200 and form in r.text
        assert 'class="kao-open"' not in who.get(f"/karton/{coach}").text and 'class="kao-open"' not in who.get("/karton").text
    for who, back in ((c, f"/admin/session/{sid}"), (c, f"/karton/{ivan}"), (o, f"/karton/{ivan}")):
        assert enter(who, ivan, natrag=back).headers["location"] == "/karton"
        assert who.post("/kao/izlaz", follow_redirects=False).headers["location"] == back


# ---------- the Karton tab's search, amber, the upitnik while acting ----------

def karton_find(page: str) -> str | None:
    """The Karton tab's search for a member's karton, or None."""
    m = re.search(r'<form class="k-find" method="get" action="/karton/clan">.*?</form>', page, re.S)
    return m.group(0) if m else None


def test_the_karton_tab_of_staff_holds_the_search_for_a_members_karton():
    """On the trainer's and the owner's own karton (the owner who does not
    train: staff by rule), under the lead and above the cards, ONE form, a
    GET to /karton/clan (27.11.2026, the owner: "when a user is pressed,
    that user's Karton is opened, not the whole app as his view"): "Član",
    a required select of every member /kao lists, in its order ("Ime
    Prezime · email"; one named by his email, the email alone), no staff
    account, after its empty first option "Odaberi člana…"; beside it
    "Otvori karton" (.act), the page's without its script, which takes it
    away; and the combobox's rows as JSON, [id, name, "email · plans" ("bez
    članarine" for none; the plans alone for one named by his email), the
    email typing matches besides the name ("" for one named by it)]. Nothing
    on the page goes into a member's app: no solid amber button (.btn-kao,
    from build 4, went with POST /kao), no form to /kao. Not on a member's
    karton, not on the trainer's view of one, not while staff act as a
    member (the page is his own karton then); no member at all, no form."""
    coach, owner, ivan, ana, sara = people()
    nameless = db.create_user("bez.imena@test.local", "", auth.hash_password("lozinka123")).id
    db.mark_email_verified("bez.imena@test.local")
    order = re.findall(r'<form method="post" action="/kao/(\d+)"><button', client_for("coach@test.local").get("/kao").text)
    assert [int(i) for i in order] == [ana, nameless, ivan, sara]       # /kao's order: the alphabet's
    for email in ("coach@test.local", "trener@test.local"):
        page = client_for(email).get("/karton").text
        form = karton_find(page)
        assert form is not None, email
        head = page.split("<h1>")[1].split('<div class="k-cards">')[0]
        assert form in head and head.index('<p class="hint">') < head.index(form), email   # under the lead, above the cards
        assert '<label for="kf-clan">Član</label>' in form and '<select id="kf-clan" name="clan" required>' in form
        assert "<input" not in form                                    # the member alone: nothing hidden beside him
        options = re.findall(r'<option value="(\d*)"( disabled selected)?>([^<]*)</option>', form)
        assert options == [("", " disabled selected", "Odaberi člana…"), (str(ana), "", "Ana Kovač · ana@test.local"),
                           (str(nameless), "", "bez.imena@test.local"), (str(ivan), "", "Ivan Horvat · ivan@test.local"),
                           (str(sara), "", "Sara Jurić · sara@test.local")], email
        assert re.findall(r"<button[^>]*>.*?</button>", form) == ['<button type="submit" class="act">Otvori karton</button>']
        rows = json.loads(re.search(r'<script type="application/json" id="kf-json">(.*?)</script>', form, re.S).group(1))
        assert rows == [[ana, "Ana Kovač", "ana@test.local · Grupni trening", "ana@test.local"],
                        [nameless, "bez.imena@test.local", "bez članarine", ""],
                        [ivan, "Ivan Horvat", "ivan@test.local · Grupni trening · Online trening", "ivan@test.local"],
                        [sara, "Sara Jurić", "sara@test.local · bez članarine", "sara@test.local"]], email
        assert "btn-kao" not in page and 'action="/kao"' not in page, email
    assert karton_find(client_for("ivan@test.local").get("/karton").text) is None      # a member's own
    c = client_for("coach@test.local")
    view = c.get(f"/karton/{ivan}")                                    # the trainer's view, his since 27.11.2026
    assert view.status_code == 200 and karton_find(view.text) is None and 'id="kf-clan"' not in view.text
    enter(c, ivan)
    page = c.get("/karton").text
    assert bar(page) is not None and karton_find(page) is None and 'id="kf-json"' not in page   # acting: his karton
    c.post("/kao/izlaz")
    with db.engine.begin() as conn:                                    # no member at all
        conn.execute(sa_text("DELETE FROM users WHERE id <> :c AND id <> :o"), {"c": coach, "o": owner})
    page = c.get("/karton").text
    assert "<h1>" in page and karton_find(page) is None and 'id="kf-clan"' not in page


def test_the_search_opens_the_members_karton_and_refuses_the_rest():
    """GET /karton/clan, the Karton tab's search (27.11.2026): a member's id
    (its spaces aside) → his karton, the trainer's view (/karton/<id>), for
    the trainer and the owner alike, its crumb "Karton" back to the search,
    no strip over it. A trainer's or the owner's id, an id naming nobody,
    nothing, junk: back to the Karton tab saying "Odaberi člana s popisa.".
    A GET: nothing enters (no acting key in the session) and the record
    holds no row. A member asking is refused (403, as every staff route
    refuses him; while acting too: the walk above), a guest goes to log in.
    POST /kao, the Karton tab's way into a member's app from build 4, is
    gone: 405, /kao being a GET alone."""
    coach, owner, ivan, ana, sara = people()
    refused = "/karton?error=Odaberi člana s popisa."
    for email in ("coach@test.local", "trener@test.local"):
        c = client_for(email)
        r = c.get(f"/karton/clan?clan={ana}", follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (303, f"/karton/{ana}"), email
        page = c.get(r.headers["location"]).text
        assert "<h1>Karton — Ana Kovač</h1>" in page and bar(page) is None, email
        assert '<nav class="crumbs" aria-label="Putanja"><a href="/karton">Karton</a><span class="sep">/</span>' in page
        assert c.get("/karton/clan", params={"clan": f" {ana} "}, follow_redirects=False).headers["location"] == \
            f"/karton/{ana}"
        for clan in (str(coach), str(owner), "999999", "", "   ", "abc", "-3", f"{ana}.0", "1" * 12):
            r = c.get("/karton/clan", params={"clan": clan}, follow_redirects=False)
            assert (r.status_code, location(r)) == (303, refused), (email, clan)
        assert location(c.get("/karton/clan", follow_redirects=False)) == refused        # no field at all
        assert '<div class="alert" role="alert">\n      <span>Odaberi člana s popisa.</span>' in c.get(refused).text
        r = c.post("/kao", data={"clan": str(ana), "natrag": "/karton"}, follow_redirects=False)
        assert r.status_code == 405, email                             # gone: the Karton tab's way into his app
        assert {k for k in session_of(c) if k.startswith("as_")} == set(), email
    assert record() == []
    assert client_for("ivan@test.local").get(f"/karton/clan?clan={ana}").status_code == 403
    r = TestClient(app).get(f"/karton/clan?clan={ana}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_every_way_into_a_members_app_is_amber():
    """The owner: "The button to open as another user should also be in
    amber." /kao's "Otvori →", a roster's "Kao član →" and the trainer's
    view's "Otvori kao član" wear base.html's tint (.act.act-kao: --warn on
    --warn-soft, a deeper tint on hover, its background declared). The
    Karton tab's solid amber "Otvori kao član" (.btn-kao, from build 4)
    went on 27.11.2026 with its way into the app: the tab's field opens a
    member's karton now, nothing amber (the tests above). The strip's
    "Izađi" stays as it was."""
    coach, owner, ivan, ana, sara = people()
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + timedelta(days=1), 60, 8, None)
    db.book(ivan, sid)
    c = client_for("coach@test.local")
    kao = c.get("/kao").text
    assert kao.count('<button type="submit" class="act act-kao">Otvori →</button>') == 3 and 'class="act">' not in kao
    assert '<button type="submit" class="act act-kao">Kao član →</button>' in c.get(f"/admin/session/{sid}").text
    # the trainer's view: the trainer's again since the Karton tab's search leads there (27.11.2026)
    assert '<button type="submit" class="act act-kao">Otvori kao član</button>' in c.get(f"/karton/{ivan}").text
    own = c.get("/karton").text
    assert "btn-kao" not in own and ">Otvori kao član</button>" not in own
    for rule in (".act-kao { background: var(--warn-soft); color: var(--warn);",
                 ".act-kao:hover { background: color-mix(in srgb, var(--warn) 26%, transparent); color: var(--warn);"):
        assert rule in own, rule
    enter(c, ivan)
    assert '<form method="post" action="/kao/izlaz"><button type="submit" class="kao-exit">Izađi</button></form>' in c.get("/karton").text


def flagged_upitnik(member: int) -> None:
    """The gym owner's questions (copy.UPITNIK_DEFAULT_QUESTIONS) and the
    member's answers to them, version 2, both of the trainer's flags up: the
    pain question at 5 (where it hurts asked: "donji dio leđa") and the
    injuries question Da (its note asked)."""
    for q in copy.UPITNIK_DEFAULT_QUESTIONS:
        db.add_upitnik_question(None, q)
    answers = {f"q{q['id']}": q["options"][0] if q["kind"] == "choice" else 5
               for q in copy.UPITNIK_DEFAULT_QUESTIONS if q["kind"] in ("choice", "scale")}
    answers.update({"q14": 5, "q16": "donji dio leđa", "q15": True, "q17": "Operacija koljena."})
    db.save_onboarding(member, json.dumps(answers, ensure_ascii=False), 5.0, "srednja", "cijelo", pain_level=5,
                       pain_high=False, needs_review=True, consented_at=datetime.now(config.TZ))


def upitnik_block(page: str) -> str:
    """The karton's upitnik block, as printed."""
    return page.split('<section class="upitnik')[1].split("</section>")[0]


# what staff acting as the member read in his upitnik block and he does not:
# the flags' row under its caption, "Odgovori" under its own
STAFF_FLAGS = re.compile(r'<p class="hint u-staff">Vidi samo trener</p>\n  <div class="u-flags">\n.*?\n  </div>\n  ', re.S)
STAFF_ANSWERS = re.compile(r'<p class="hint u-staff u-answers">Vidi samo trener</p>\n.*?</details>\n  ', re.S)


def test_acting_staff_read_what_only_the_trainers_view_showed_of_the_upitnik():
    """With "Karton →" gone from /clanarine (build 4) the trainer's
    read-only view had no link Amir reached (until 27.11.2026, when the
    Karton tab's search came to open it), and it alone showed the upitnik's
    "Zahtijeva pregled", the pain flag and every answer. So staff acting as
    the member read those three on his karton exactly as that view prints
    them, each group under one small muted caption, "Vidi samo trener"
    (twice, once each). The member himself reads none of the three nor a
    caption: his block is the acting one less those two groups, byte for
    byte. The trainer's view as before (no caption); nothing else of it
    comes over (its head line of email, age and phone)."""
    coach, owner, ivan, ana, sara = people()
    flagged_upitnik(ivan)
    t = client_for("coach@test.local")
    r = t.get(f"/karton/{ivan}")             # the trainer's view, his again: the Karton tab's search leads there (27.11.2026)
    assert r.status_code == 200
    view = upitnik_block(r.text)
    assert ('<span class="u-flag review"><span class="ed t" data-copy="karton.staff.review"' in view
            and '<span class="u-flag pain">Bolovi 5/10 · donji dio leđa</span>' in view)
    assert '<details>\n    <summary><span class="ed t" data-copy="karton.staff.answers"' in view
    assert "Vidi samo trener" not in view and "u-staff" not in view
    enter(t, ivan)
    page = t.get("/karton").text
    acting = upitnik_block(page)
    assert acting.count("Vidi samo trener") == 2
    flags, answers = STAFF_FLAGS.search(acting).group(0), STAFF_ANSWERS.search(acting).group(0)
    assert '<span class="u-flag review"><span class="t">Zahtijeva pregled</span></span>' in flags
    assert '<span class="u-flag pain">Bolovi 5/10 · donji dio leđa</span>' in flags
    assert '<summary><span class="t">Odgovori</span></summary>' in answers
    rows = re.findall(r"<li( class=\"follow d1\")?>(.*?) — <strong>(.*?)</strong></li>", answers)
    assert len(rows) == 17 and (' class="follow d1"', "Gdje te boli?", "donji dio leđa") in rows
    assert (' class="follow d1"', "Opiši ukratko.", "Operacija koljena.") in rows
    assert acting.index(flags) < acting.index('<div class="ramp"') < acting.index(answers)   # each in its own place
    head = page.split("<h1")[1].split('<div class="k-cards">')[0]
    assert "god." not in head and "ivan@test.local" not in head      # the view's head line stays the view's
    assert 'data-copy="' not in page                                  # the member's page: no editor's markup
    own = upitnik_block(client_for("ivan@test.local").get("/karton").text)
    for gone in ("u-flags", "Zahtijeva pregled", "Bolovi", "<details>", "Odgovori", "Vidi samo trener", "u-staff"):
        assert gone not in own, gone
    assert STAFF_ANSWERS.sub("", STAFF_FLAGS.sub("", acting)) == own   # nothing else differs


# ---------- the phone reminder (26.11.2026) ----------

def test_the_phone_reminder_is_a_members_with_no_phone_number():
    """The card (rendered hidden: the script shows it) for a member whose
    phone is empty, on every page but /profil and a one-task page (the
    upitnik, the player); its title, its lead and "Upiši broj" to
    /profil#p-phone, its ✕ "Kasnije". Not for a member with a number, nor
    for staff, nor a guest; while staff act as a member it is the
    member's. The profile's field is p-phone."""
    coach, owner, ivan, ana, sara = people()
    ex = db.create_exercise("Plank")
    pid = db.create_program("Cijelo tijelo", None, "srednja", "cijelo")
    did = db.add_day(pid)
    db.update_day_item(db.add_day_item(did, ex, "trening"), "trening", 3, None, 40, None, None, "")
    db.update_profile(ana, "Ana", "Kovač", date(1990, 1, 1), "091 234 5678")
    ci = client_for("ivan@test.local")
    card = re.compile(r'<div id="phoneCard" class="card phone-card" hidden role="dialog" aria-labelledby="phoneTitle">\s*'
                      r'<button type="button" class="phone-x" aria-label="Kasnije" onclick="qmtPhoneLater\(\)">✕</button>.*?'
                      r'<strong id="phoneTitle"><span class="t">Dodaj broj mobitela</span></strong>\s*</div>\s*'
                      r'<p class="hint phone-lead"><span class="t">Da ti se trener može javiti ako se termin promijeni.</span></p>\s*'
                      r'<div class="phone-actions"><a class="btn btn-sm" href="/profil#p-phone"><span class="t">Upiši broj</span></a></div>',
                      re.S)
    for path in ("/", "/raspored", "/karton", "/moja-clanarina", "/prehrana", "/treninzi", f"/treninzi/{pid}/dan/{did}"):
        assert card.search(ci.get(path).text), path
    step = ci.post(f"/treninzi/{pid}/dan/{did}/kreni", follow_redirects=False).headers["location"]
    for path in ("/profil", "/upitnik", "/vodic", step, f"/treninzi/{pid}/dan/{did}/kraj"):
        assert 'id="phoneCard"' not in ci.get(path).text, path
    assert 'id="p-phone"' in ci.get("/profil").text
    for email in ("ana@test.local", "coach@test.local", "trener@test.local"):
        assert 'id="phoneCard"' not in client_for(email).get("/raspored").text, email
    assert 'id="phoneCard"' not in TestClient(app).get("/").text
    c = client_for("coach@test.local")
    enter(c, ivan)
    assert card.search(c.get("/raspored").text)
    c.post("/kao/izlaz")
    enter(c, ana)
    assert 'id="phoneCard"' not in c.get("/raspored").text


# ---------- in a browser ----------

@pytest.fixture(scope="module")
def server():
    import uvicorn
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True); th.start()
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/healthz", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{PORT}"
    srv.should_exit = True; th.join(timeout=5)


OVERFLOW = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
# the strip and the pill under it, measured: its height and its line's,
# whether the name is cut, "Izađi"'s box, the pill's top, the contrast of
# the strip's words and of "Izađi" against what they really sit on (the
# tint laid over the page's background)
STRIP = r"""() => {
  const bar = document.querySelector('.kao-bar'), who = bar.querySelector('.kao-as'), x = bar.querySelector('.kao-exit');
  const tb = document.querySelector('.topbar').getBoundingClientRect(), b = bar.getBoundingClientRect(), xr = x.getBoundingClientRect();
  const rgb = c => { const m = c.match(/[\d.]+/g).map(Number); return m.length > 3 ? m : [...m, 1]; };
  const lum = ([r, g, bl]) => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); };
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(bl); };
  const ratio = (a, c) => { const [h, l] = [lum(a), lum(c)].sort((p, q) => q - p); return (h + .05) / (l + .05); };
  const page = rgb(getComputedStyle(document.body).backgroundColor);
  const tint = rgb(getComputedStyle(document.documentElement).getPropertyValue('--warn-soft').trim());
  const ground = [0, 1, 2].map(i => tint[i] * tint[3] + page[i] * (1 - tint[3]));
  const lineH = parseFloat(getComputedStyle(who).lineHeight);
  return {h: b.height, top: b.top, whoH: who.getBoundingClientRect().height, lineH, cut: who.scrollWidth > who.clientWidth,
          exitLeft: xr.left, exitRight: xr.right, exitH: xr.height, width: document.documentElement.clientWidth,
          pillTop: tb.top, pillBottom: tb.bottom,
          words: ratio(rgb(getComputedStyle(who).color), ground), exit: ratio(rgb(getComputedStyle(x).color), rgb(getComputedStyle(x).backgroundColor))};
}"""


def _login(browser, server: str, email: str, width: int, theme: str = "dark", ua: str | None = None, keep_phone: bool = False):
    """A logged-in page at `width` (below 600px a touch phone), its theme
    set, the install banner installed (out of the way) and, unless
    `keep_phone`, the phone reminder dismissed this week: (context, page,
    errors)."""
    phone = width < 600
    extra = {"user_agent": ua} if ua else {}
    ctx = browser.new_context(viewport={"width": width, "height": 844 if phone else 900}, has_touch=phone, is_mobile=phone,
                              **extra)
    pg = ctx.new_page(); errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
    pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    pg.goto(server + "/login")
    pg.evaluate("t => localStorage.setItem('qmt-theme', t)", theme)
    if not ua:
        pg.evaluate("() => localStorage.setItem('qmt-a2hs', 'installed')")
    if not keep_phone:
        pg.evaluate("() => localStorage.setItem('qmt-phone', String(Date.now()))")
    pg.fill("main input[name=email]", email); pg.fill("main input[name=password]", "lozinka123")
    pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
    return ctx, pg, errors


def go(pg, url: str) -> None:
    pg.goto(url); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")


def test_into_a_members_account_and_out_on_a_phone(server):
    """At 390 and 360px, touch, both themes: the owner opens the picker,
    types "kova" (2 od 3), clears it ("prikaži sve"), and taps Ivan's
    "Otvori →": his karton, the strip over it, one line, "Izađi" 44px and
    inside the screen, the words AA on what they sit on and "Izađi" too;
    the pill under the strip, not behind it, scrolled or not; a jump to
    the weight card (#masa) clears both. A long name is cut with an
    ellipsis, still one line, "Izađi" still in the screen. The karton and
    the raspored never scroll sideways. A form sent from the page (his
    limitations) is his; "Izađi" goes back to the picker, no strip. No
    page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", "Tvrtko Vlasnik")
    ivan = make_user("ivan@test.local", "Ivan Horvat", plans=("grupni",))
    make_user("ana@test.local", "Ana Kovač", plans=("grupni",))
    make_user("dario@test.local", "Dario Kovačević")
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w, theme in ((390, "dark"), (360, "light")):
            where = f"[{w}px {theme}]"
            ctx, pg, errors = _login(browser, server, "trener@test.local", w, theme)
            go(pg, server + "/kao")
            check(pg.is_visible("form.kao-search") and pg.evaluate(OVERFLOW) == 0, f"{where} the picker's search, overflow")
            pg.fill("form.kao-search input", "kova")
            check(pg.locator(".kao-row:visible").count() == 2 and (pg.text_content(".kao-found") or "").startswith("2 od 3"),
                  f"{where} 'kova' keeps {pg.locator('.kao-row:visible').count()} rows: {pg.text_content('.kao-found')}")
            pg.tap(".kao-found a")
            check(pg.locator(".kao-row:visible").count() == 3 and pg.input_value("form.kao-search input") == "",
                  f"{where} prikaži sve")
            with pg.expect_navigation():
                pg.locator(".kao-row", has_text="Ivan Horvat").locator("button").tap()
            pg.wait_for_load_state("networkidle")
            check(pg.url == server + "/karton", f"{where} Otvori led to {pg.url}")
            s = pg.evaluate(STRIP)
            check(s["h"] == 52 and s["top"] == 0 and s["whoH"] <= s["lineH"] * 1.2 and not s["cut"],
                  f"{where} the strip: {s}")
            check(s["exitH"] >= 44 and s["exitRight"] <= s["width"] - 15 and s["exitLeft"] > 0, f"{where} Izađi: {s}")
            check(s["words"] >= 4.5 and s["exit"] >= 4.5, f"{where} contrast: words {s['words']:.2f}, Izađi {s['exit']:.2f}")
            check(s["pillTop"] >= s["h"], f"{where} the pill's top {s['pillTop']} is behind the strip ({s['h']})")
            pg.evaluate("() => window.scrollTo(0, 400)"); pg.wait_for_timeout(150)
            s = pg.evaluate(STRIP)
            check(s["top"] == 0 and abs(s["pillTop"] - (s["h"] + 10)) < 1, f"{where} scrolled: the strip and the pill: {s}")
            check(pg.evaluate(OVERFLOW) == 0, f"{where} the karton overflows by {pg.evaluate(OVERFLOW)}px")
            go(pg, server + "/karton#masa"); pg.wait_for_timeout(800)
            top = pg.evaluate("() => document.getElementById('masa').getBoundingClientRect().top")
            check(top >= pg.evaluate(STRIP)["pillBottom"] - 1, f"{where} #masa at {top}, under the pill")
            go(pg, server + "/raspored")
            check(pg.evaluate(OVERFLOW) == 0 and pg.is_visible(".kao-bar"), f"{where} the raspored: overflow, strip")
            go(pg, server + "/karton")
            pg.tap("#ogranicenja .kc-btns button.act")
            pg.fill("#lim-input", "Koljeno.")
            with pg.expect_navigation():
                pg.tap("#ogranicenja form[action='/karton/ogranicenja'] button[type=submit]")
            pg.wait_for_load_state("networkidle")
            check(db.get_user(ivan).limitations.startswith("Koljeno") and "ok=" in pg.url, f"{where} the form: {pg.url}")
            db.update_profile(ivan, "Ivan Aleksandar Maksimilijan", "Horvat-Kovačević-Babić", date(1990, 1, 1), "")
            go(pg, server + "/raspored")
            s = pg.evaluate(STRIP)
            check(s["cut"] and s["whoH"] <= s["lineH"] * 1.2 and s["exitRight"] <= s["width"] - 15,
                  f"{where} a long name: {s}")
            check(pg.get_attribute(".kao-as", "title") == "Ivan Aleksandar Maksimilijan Horvat-Kovačević-Babić · ivan@test.local",
                  f"{where} the title: {pg.get_attribute('.kao-as', 'title')}")
            with pg.expect_navigation():
                pg.tap(".kao-exit")
            pg.wait_for_load_state("networkidle")
            check(pg.url == server + "/kao" and not pg.locator(".kao-bar").count(), f"{where} Izađi led to {pg.url}")
            db.update_profile(ivan, "Ivan", "Horvat", date(1990, 1, 1), "")
            db.set_limitations(ivan, "")
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# the Karton tab's search as laid out (27.11.2026): the field's input, the
# form and the cards under it, the buttons in the form, the label, the
# list's rows by name and its note, the line under the field, what is typed
# and the value the form sends
FIND = r"""() => {
  const q = s => document.querySelector(s), r = e => e.getBoundingClientRect();
  const input = q('#kf-clan-q'), list = q('#kf-clan-list'), label = q('.k-find label');
  const i = r(input), f = r(q('.k-find')), l = list.hidden ? null : r(list);
  return {input: [i.left, i.top, i.width, i.height], form: [f.left, f.width], list: l && [l.top, l.bottom, l.width],
          cardsTop: r(q('.k-cards')).top, buttons: q('.k-find').querySelectorAll('button').length,
          label: label.textContent, labelFor: label.htmlFor,
          names: [...list.querySelectorAll('[role=option] .cbx-name')].map(o => o.textContent),
          lines: [...list.querySelectorAll('[role=option] .cbx-tags')].map(o => o.textContent),
          active: [...list.querySelectorAll('[role=option][aria-selected=true] .cbx-name')].map(o => o.textContent),
          note: (list.querySelector('.cbx-note') || {}).textContent || null, placeholder: input.placeholder,
          listLabel: list.getAttribute('aria-label'), err: q('#kf-clan-err').textContent,
          invalid: input.getAttribute('aria-invalid'), typed: input.value, value: q('#kf-clan').value,
          overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}"""


def test_the_karton_tabs_search_on_a_phone(server):
    """At 390px (dark) and 360px (light), touch, the Karton tab of a trainer
    who is not the owner (the view is staff's again, 27.11.2026): "Član"
    over the field ("Ime ili email člana"), 44px, the column's width, and no
    button in the form (the script took the no-JS "Otvori karton" away).
    Enter with nothing picked says "Odaberi člana s popisa." and goes
    nowhere. A tap opens the list ("Članovi") of every member, the name over
    "email · plans", laid over the cards (they do not move); "kov" finds
    "Kovač" by the name, "mb.tr" Marko by his email's start, "grupni" (a
    plan) nobody: "Nijedan član ne odgovara traženju.". Ana's row tapped:
    her karton at once, the trainer's view (/karton/<id>, "Karton — Ana
    Kovač"), no strip (nobody acts as her). Back: the Karton tab, the field
    empty, the value too; and so when the page comes back out of the
    browser's cache with the pick still in it (its pageshow, persisted, sent
    by hand: Playwright's Chromium keeps no such cache). "mb.tr" highlights
    Marko, and Enter opens his karton the same way. Nothing scrolls sideways
    at either width; no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", "Tvrtko Vlasnik")
    make_user("coach@test.local", "Amir Trener", is_trainer=True)
    ana = make_user("ana@test.local", "Ana Kovač", plans=("grupni",))
    make_user("ivan@test.local", "Ivan Horvat", plans=("grupni", "online"))
    marko = make_user("mb.trening@test.local", "Marko Babić")
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w, theme in ((390, "dark"), (360, "light")):
            where = f"[{w}px {theme}]"
            ctx, pg, errors = _login(browser, server, "coach@test.local", w, theme)
            go(pg, server + "/karton")
            s = pg.evaluate(FIND)
            check(s["overflow"] == 0, f"{where} the Karton tab overflows by {s['overflow']}px")
            (ix, iy, iw, ih), (fx, fw) = s["input"], s["form"]
            check(abs(ih - 44) < .5 and max(abs(ix - fx), abs(iw - fw)) < .5 and s["buttons"] == 0,
                  f"{where} 44px, the column's width, no button: input {s['input']}, form {s['form']}, {s['buttons']} buttons")
            check(s["label"] == "Član" and s["labelFor"] == "kf-clan-q" and s["placeholder"] == "Ime ili email člana"
                  and s["listLabel"] == "Članovi", f"{where} the words: {s}")
            url = pg.url
            pg.tap("#kf-clan-q")
            pg.keyboard.press("Enter")                                  # nothing picked
            pg.wait_for_timeout(300)
            s = pg.evaluate(FIND)
            check(pg.url == url and s["err"] == "Odaberi člana s popisa." and s["invalid"] == "true" and s["list"] is None,
                  f"{where} Enter with nothing picked: {pg.url}, {s['err']!r}, the list {s['list']}")
            pg.evaluate("() => document.getElementById('kf-clan-q').blur()")
            top = pg.evaluate(FIND)["cardsTop"]
            pg.tap("#kf-clan-q")
            s = pg.evaluate(FIND)
            check(s["names"] == ["Ana Kovač", "Ivan Horvat", "Marko Babić"]
                  and s["lines"] == ["ana@test.local · Grupni trening", "ivan@test.local · Grupni trening · Online trening",
                                     "mb.trening@test.local · bez članarine"], f"{where} the list: {s['names']} {s['lines']}")
            check(s["list"] is not None and s["cardsTop"] == top and s["list"][1] > top,
                  f"{where} the list lies over the cards: list {s['list']}, cards at {s['cardsTop']} (were {top})")
            for typed, names, note in (("kov", ["Ana Kovač"], None), ("mb.tr", ["Marko Babić"], None),
                                       ("grupni", [], "Nijedan član ne odgovara traženju.")):
                pg.fill("#kf-clan-q", typed)
                s = pg.evaluate(FIND)
                check(s["names"] == names and s["note"] == note, f"{where} {typed!r} finds {s['names']}, {s['note']!r}")
            pg.fill("#kf-clan-q", "kov")
            with pg.expect_navigation():
                pg.locator("#kf-clan-list [role=option]", has_text="Ana Kovač").first.tap()
            pg.wait_for_load_state("networkidle")
            check(pg.url == f"{server}/karton/{ana}" and pg.text_content("main h1") == "Karton — Ana Kovač"
                  and not pg.locator(".kao-bar").count(), f"{where} the tap led to {pg.url}: {pg.text_content('main h1')!r}")
            check(pg.evaluate(OVERFLOW) == 0, f"{where} her karton overflows by {pg.evaluate(OVERFLOW)}px")
            pg.go_back(); pg.wait_for_load_state("networkidle")
            s = pg.evaluate(FIND)
            check(pg.url == server + "/karton" and s["typed"] == "" and s["value"] == "" and s["err"] == "",
                  f"{where} Back: {pg.url}, the field {s['typed']!r}, the value {s['value']!r}, {s['err']!r}")
            pg.evaluate("""a => { document.getElementById('kf-clan-q').value = 'Ana Kovač';
                                  document.getElementById('kf-clan').value = String(a);
                                  window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true})); }""", ana)
            s = pg.evaluate(FIND)
            check(s["typed"] == "" and s["value"] == "", f"{where} out of the cache: {s['typed']!r}, {s['value']!r}")
            pg.tap("#kf-clan-q")
            pg.fill("#kf-clan-q", "mb.tr")
            check(pg.evaluate(FIND)["active"] == ["Marko Babić"], f"{where} 'mb.tr' highlights {pg.evaluate(FIND)['active']}")
            with pg.expect_navigation():
                pg.keyboard.press("Enter")
            pg.wait_for_load_state("networkidle")
            check(pg.url == f"{server}/karton/{marko}" and pg.text_content("main h1") == "Karton — Marko Babić"
                  and not pg.locator(".kao-bar").count(), f"{where} Enter led to {pg.url}: {pg.text_content('main h1')!r}")
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# the phone reminder as shown: its box, the install banner's, the focus
CARDS = """() => { const c = document.getElementById('phoneCard'), a = document.getElementById('a2hs');
  const r = c && !c.hidden ? c.getBoundingClientRect() : null;
  return {card: !!r && r.width > 0, a2hs: !!a && !a.hidden && a.getBoundingClientRect().width > 0,
          left: r ? r.left : null, right: r ? r.right : null, w: r ? r.width : null, bottom: r ? r.bottom : null,
          width: document.documentElement.clientWidth, height: innerHeight,
          overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth}; }"""


def test_the_phone_reminder_on_a_phone_and_a_desktop(server):
    """At 390px (an iPhone: the install banner shows at load, from the
    second page on) the card shows at the bottom, the install banner not
    beside it; its ✕ keeps it away (qmt-phone, when), the install banner
    takes the next load; six days on it is still away, eight days on back,
    and the install banner away again. "Upiši broj" goes to the profile,
    whose phone field has the focus. At 1280px the card is 360px wide at
    the bottom right, its link the same. A number saved, the card is gone.
    Nothing scrolls sideways; no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("ivan@test.local", "Ivan Horvat", plans=("grupni",))
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _login(browser, server, "ivan@test.local", 390, ua=IPHONE, keep_phone=True)
        go(pg, server + "/raspored")                                   # the second page: the install banner could ask
        s = pg.evaluate(CARDS)
        check(s["card"] and not s["a2hs"] and s["left"] == 16 and s["right"] == 374 and s["overflow"] == 0,
              f"[390] the card, not the banner: {s}")
        pg.tap("#phoneCard .phone-x")
        stored = pg.evaluate("localStorage.getItem('qmt-phone')")
        check((stored or "").isdigit() and not pg.evaluate(CARDS)["card"], f"[390] ✕ stored {stored!r}")
        pg.reload(); pg.wait_for_load_state("networkidle")
        s = pg.evaluate(CARDS)
        check(not s["card"] and s["a2hs"], f"[390] the next load: {s}")
        for days, back in ((6, False), (8, True)):
            pg.evaluate(f"() => localStorage.setItem('qmt-phone', String(Date.now() - {days} * 864e5))")
            pg.reload(); pg.wait_for_load_state("networkidle")
            s = pg.evaluate(CARDS)
            check(s["card"] == back and not (s["card"] and s["a2hs"]), f"[390] {days} days on: {s}")
        with pg.expect_navigation():
            pg.tap("#phoneCard .phone-actions a")
        pg.wait_for_load_state("networkidle")
        check(pg.url == server + "/profil#p-phone" and pg.evaluate("document.activeElement.id") == "p-phone",
              f"[390] Upiši broj: {pg.url}, the focus on {pg.evaluate('document.activeElement.id')!r}")
        check(pg.evaluate(OVERFLOW) == 0 and not pg.locator("#phoneCard").count(), "[390] the profile")
        problems += [f"[390] {e}" for e in errors]
        ctx.close()

        ctx, pg, errors = _login(browser, server, "ivan@test.local", 1280, keep_phone=True)
        go(pg, server + "/karton")
        s = pg.evaluate(CARDS)
        check(s["card"] and s["w"] == 360 and s["right"] == s["width"] - 16 and s["bottom"] == s["height"] - 16
              and s["overflow"] == 0, f"[1280] the card at the bottom right: {s}")
        with pg.expect_navigation():
            pg.click("#phoneCard .phone-actions a")
        pg.wait_for_load_state("networkidle")
        check(pg.evaluate("document.activeElement.id") == "p-phone", "[1280] the phone field has no focus")
        pg.fill("#p-phone", "091 234 5678")
        with pg.expect_navigation():
            pg.click("form[action='/profil'] button[type=submit]")
        pg.wait_for_load_state("networkidle")
        go(pg, server + "/karton")
        check(not pg.locator("#phoneCard").count(), "[1280] a number saved, the card is still there")
        problems += [f"[1280] {e}" for e in errors]
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"
