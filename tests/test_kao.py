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
POST /kao and its solid amber button went. Since the evening of the same
day (the owner: "when he enters the karton tab via the search bar, it
should be read and write ... When entered via the karton tab search, I dont
want to view the whole app as that user like admin->gledaj kao clan but only
that karton tab. If then Amir or I switch the tab, then its no longer that
users view."; "We need a similar search bar on the top of the 'Dvoranski
treninzi' tab") the search enters a tab's view of the member (POST
/karton/clan, and the same search on staff's own Dvoranski treninzi, POST
/dvoranski/clan): the session's fourth key, as_scope; his Karton and his
Dvoranski treninzi are his, read and write, any other request ends the view
before it runs and is the staff member's own (a page asked for says so,
"Izašao/la si iz pregleda člana."; a write with his marker runs nothing);
the bar over its pages is staff's own, every link of it the exit (GET
/kao/izlaz?kamo=…); while staff act as a member, either way, the two pages'
titles name him. The whole app's way in stays as it was. Since 28.11.2026
(build 2 of roadmap/2026-11-28-admin-view-plan.md; the owner: "I would
remove the search bar and all other admin operations from the Karton and
Dvoranski treninzi ... into separate admin tabs") the two searches are the
admin's lists of members, Članovi → Kartoni (/kartoni) and Treninzi →
Dvoranski treninzi (/dvoranski/clanovi, with "Predlošci treninga →"), /kao's
look and order, each row's form posting the entry with `natrag` the list,
where "Izađi" returns; staff's own Karton and Dvoranski treninzi carry no
search; the bar over a tab's view is the admin view's. Since build 3 of the
same day the strip is a dark bar in both themes, the member's name on it in
his status's colour, and every way into a member's account wears the
admin's indigo where it wore amber (tests/test_status.py: the colours).
Since build 4 (the owner: "We should also somehow separate users which are
for gym and for online trainings … Amir just wants to somehow group this
many users he will have.") the three lists carry four chips, Svi · Dvorana ·
Online · Bez članarine, by what a member runs now (app._member_groups, the
two tabs' rule, never stored; read with the list, one batch), Kartoni and
/kao opening on Svi, the admin's Dvoranski treninzi on Dvorana; each chip a
link (?grupa=), filtering in place with the script, with the search.

The phone reminder (the owner: "if a user didnt give it, when he opens the
app a popup reminder should appear similarly how a popup appears as a
notification to install the app on the phone"): the install banner's card
for a member with no phone number, on every page but a one-task page and
/profil, away a week after its ✕, never on the load the install banner
shows on. The seconds in steps of 5 and the 20 sets are
tests/test_player.py's and tests/test_karton.py's, the height on the karton
tests/test_karton.py's.

The browser half walks the picker into a member's account at 390 and 360px
(touch) and back out, Kartoni into a member's karton at the same widths
(and the three admin pages of 28.11.2026 for overflow), the three lists'
chips at 390px (touch), and the phone reminder at 390 and 1280px."""

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
from sqlalchemy import event, inspect as sa_inspect, text as sa_text
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


def keys_of(ctx) -> dict:
    """A browser context's session keys of a view as a member (its session
    cookie, read as session_of reads a client's)."""
    from itsdangerous import TimestampSigner

    raw = next((c["value"] for c in ctx.cookies() if c["name"] == "session"), "")
    if not raw:
        return {}
    data = json.loads(base64.b64decode(TimestampSigner(str(config.SECRET_KEY)).unsign(raw.encode())))
    return {k: v for k, v in data.items() if k.startswith("as_")}


def record() -> list[tuple]:
    """The record, newest first: (who, as whom, method, path, status)."""
    rows, _ = db.acting_log()
    return [(r.actor_name, r.member_name, r.method, r.path, r.status) for r in rows]


def bar(page: str) -> str | None:
    """The strip over a page while acting, or None (since 28.11.2026 its tag
    carries data-theme="dark": build 3 of the admin view)."""
    m = re.search(r'<div class="kao-bar" role="status"[^>]*>.*?</div>', page, re.S)
    return m.group(0) if m else None


def seen(html: str) -> str:
    """A page as a sighted reader has it (since 28.11.2026, build 3 of the
    admin view, a member's name is in his status's colour, _status.html:
    span.st with his status's words for a screen reader inside it): every
    status span unwrapped, its unseen words dropped. Where a name stands it
    is what the page printed before, byte for byte (tests/test_status.py
    holds the spans themselves)."""
    html = re.sub(r'<span class="st-sr">[^<]*</span>', "", html)
    return re.sub(r'<span class="st st-[a-z]+">([^<]*)</span>', r"\1", html)


STALE = "/karton?error=Stranica je bila otvorena prije ulaska u pregled kao član — ništa nije spremljeno."
ENDED = "/kao?error=Pregled kao član je završen — ništa nije spremljeno."
EXPIRED = "/kao?error=Pregled kao član je istekao — odaberi člana ponovno."
# a tab's view (27.11.2026, evening): a page asked for off the member's two
# areas, its flash (the staff member's slash form: base.html resolves it)
LEFT = "Izašao/la si iz pregleda člana."
PAGE = {"Accept": "text/html"}                 # what a browser's navigation sends (_asks_for_page)


def enter_tab(c: TestClient, member, tab: str = "/karton", **form):
    """A tab's view of `member` (POST /karton/clan or /dvoranski/clan, an
    admin list's row; since 28.11.2026 its form posts `natrag` too, the
    list: with none sent, the list is its default), not followed."""
    return c.post(f"{tab}/clan", data={"clan": str(member), **form}, follow_redirects=False)


# the admin's lists a tab's view is entered from, by the tab (28.11.2026), and
# the admin bar's menu buttons (the old Admin ▾'s place)
LISTS = {"/karton": "/kartoni", "/dvoranski": "/dvoranski/clanovi"}
ADMIN_BAR = ('id="clanoviBtn"', 'id="treninziBtn"', 'id="sadrzajBtn"')


def keys(c: TestClient) -> dict:
    """The session's keys of a view as a member."""
    return {k: v for k, v in session_of(c).items() if k.startswith("as_")}


def h1(page: str) -> str:
    return re.search(r"<h1>.*?</h1>", page, re.S).group(0)


def nav_hrefs(page: str) -> list[str]:
    """Every link of the top bar: the brand, the tabs, the admin menus'
    items (Admin ▾'s until 28.11.2026), the account menu's."""
    head = page.split('<header class="topbar')[1].split("</header>")[0]
    return re.findall(r'<a href="([^"]+)"', head)


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
        assert f'<body data-kao="{ivan}">' in page and "Gledaš kao: <strong>Ivan Horvat</strong>" in seen(page)
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
    booking as "Tvoj sljedeći termin"), the member's bar of tabs (no admin
    menu, no view switch), no ✎ pill and no editor's markup anywhere; and
    every route only staff may use, walked from the app's own routes (GET,
    and every write with his page's marker, so the route itself answers;
    since 28.11.2026 the admin's lists, its table of programmes and the
    switch among them), refuses him as it refuses any member: 403."""
    coach, owner, ivan, ana, sara = people()
    today = config.today()
    db.set_weight(ivan, today, Decimal("82.5"))
    db.set_weight(coach, today, Decimal("91"))
    sid = db.add_oneoff_session("Grupni trening srijedom", datetime.now(config.TZ) + timedelta(days=2), 60, 8, None)
    db.book(ivan, sid)
    c = client_for("coach@test.local")
    enter(c, ivan)
    karton = c.get("/karton").text
    # its title names him since the evening of 27.11.2026 ("Moj karton" his own)
    assert "82,5 kg" in karton and "91 kg" not in karton and "<h1>Karton — Ivan Horvat</h1>" in seen(karton)
    raspored = c.get("/raspored").text
    assert 'id="ntKicker"' in raspored and "Grupni trening srijedom" in raspored   # his next termin's card
    for page in (karton, raspored, c.get("/").text, c.get("/moja-clanarina").text):
        assert not any(mark in page for mark in ADMIN_BAR) and 'id="copyToggle"' not in page and "data-copy=" not in page
        assert 'href="/korisnici"' not in page and 'href="/kao"' not in page and 'action="/pogled"' not in page
    walked = _staff_routes()
    paths = {path for _, path, _ in walked}
    assert {"/kao", "/kao/zapisi", "/kao/1", "/admin", "/clanarine", "/korisnici", "/statistika", "/tekstovi",
            "/karton/1", "/karton/clan", "/treninzi/vjezbe", "/upitnik/pitanje/1", "/kartoni", "/dvoranski/clanovi",
            "/programi", "/pogled"} <= paths and len(walked) > 40
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
        assert 'title="Ivan Horvat · ivan@test.local">Gledaš kao: <strong>Ivan Horvat</strong>' in seen(strip), name
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
    assert 'data-kao="' not in page and 'title="Amir Trener"' in page     # his own karton again, his own bar
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
    # the names as a sighted reader has them (seen(): since build 3 of the
    # admin view "Tko" is in the admin's colour, "Kao koga" in his status's)
    cells = re.findall(r"<tr>\s*<td class=\"num when\">([^<]*)</td>\s*<td class=\"who\">([^<]*)</td>\s*"
                       r"<td class=\"as\">([^<]*)</td>\s*"
                       r"<td class=\"num\">([^<]*)</td>\s*<td class=\"num st\">([^<]*)</td>\s*</tr>", seen(first))
    assert len(cells) == 100 and cells[0][1:] == ("Amir Trener", "Ivan Horvat", "POST /karton/log/99/edit", "303")
    assert 'href="/kao/zapisi?str=2">Starije →</a>' in first and "← Novije</a>" not in first
    second = o.get("/kao/zapisi?str=2").text
    cells = re.findall(r'<td class="num when">([^<]*)</td>\s*<td class="who">[^<]*</td>\s*<td class="as">[^<]*</td>\s*'
                       r'<td class="num">([^<]*)</td>\s*<td class="num st">([^<]*)</td>', seen(second))
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
    /kao/<id> (.act-kao: amber since build 4, the admin's indigo since
    28.11.2026; the name in his status's colour since then, read here as
    a sighted reader has it, seen()); the search's box and lines
    rendered hidden (the script's);
    its tab lit there (Admin ▾ until 28.11.2026, the admin's Članovi since),
    its item current. The trainer's and the owner's; a member is refused, a
    guest goes to log in."""
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
    rows = re.findall(r'<div class="kao-row" data-find="([^"]*)" data-grupe="[a-z ]+">\s*<div class="kao-who">\s*'
                      r'<strong>([^<]*)</strong>\s*'
                      r'(?:<span class="kao-mail">([^<]*)</span>)?\s*<span class="kao-plans">([^<]*)</span>\s*</div>\s*'
                      r'<form method="post" action="/kao/(\d+)"><button type="submit" class="act act-kao">Otvori →</button></form>',
                      seen(page))
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


# ---------- the admin's lists of members (28.11.2026), the way in's colour, the upitnik while acting ----------

def has_search(page: str) -> bool:
    """Whether a page carries the search for a member of 27.11.2026
    (_member_find.html: form.k-find, its select, its rows), gone since
    28.11.2026."""
    return any(mark in page for mark in ('class="k-find"', 'id="kf-json"', 'id="kf-clan"', "kf-row"))


# an admin list's row (kao.html's, kartoni.html's and dvoranski_clanovi.html's
# entry): the name, the email, the plans, and its form into a tab's view; since
# build 4 of the admin view its groups (the chips') and, outside the chosen
# chip's group, hidden
LIST_ROW = (r'<div class="kao-row" data-find="([^"]*)" data-grupe="[a-z ]+"(?: hidden)?>\s*<div class="kao-who">\s*'
            r'<strong>([^<]*)</strong>\s*'
            r'(?:<span class="kao-mail">([^<]*)</span>)?\s*<span class="kao-plans">([^<]*)</span>\s*</div>\s*'
            r'<form method="post" action="{action}"><input type="hidden" name="clan" value="(\d+)">'
            r'<input type="hidden" name="natrag" value="{natrag}"><button type="submit" class="act act-kao">{go}</button>'
            r'</form>')


def list_rows(page: str, action: str, natrag: str, go: str) -> list[tuple]:
    """An admin list's rows, in order: (data-find, the name, the email, the
    plans, the id its form posts)."""
    return [(unescape(f), n, m, p, int(i))
            for f, n, m, p, i in re.findall(LIST_ROW.format(action=re.escape(action), natrag=re.escape(natrag), go=go),
                                             seen(page))]


def test_kartoni_lists_every_member_and_opens_his_karton():
    """Kartoni (/kartoni, the admin's Članovi → Kartoni; the owner: "I would
    remove the search bar and all other admin operations from the Karton
    ... into separate admin tabs"), the trainer's and the owner's: the /kao
    page's look, its lead "Otvori karton člana: čitaš ga i u njega
    upisuješ.", and every member in /kao's order (the alphabet's, a nameless
    one by his email; no trainer, not the owner), the name in 700, the
    email, his running plans ("bez članarine" for none: a lapsed plan runs
    no more), "Otvori karton →" a form posting clan and natrag=/kartoni to
    /karton/clan (.act-kao, as /kao's "Otvori →"); the as-you-type filter's box
    and lines rendered hidden (the script's), its "prikaži sve" this page's
    own address; no "Zapis svih radnji →" (the owner's line on /kao). A
    member is refused, a guest goes to log in; none, "Još nema članova."."""
    coach = make_user("coach@test.local", "Amir Trener", is_trainer=True)
    make_user("trener@test.local", "Tvrtko Vlasnik")
    dario = make_user("dario@test.local", "Dario Kovač", plans=("prehrana",))
    cedo = make_user("cedo@test.local", "Čedo Babić", plans=("online", "grupni"))
    cvita = make_user("cvita@test.local", "Cvita Horvat")
    u = db.create_user("bez.imena@test.local", "", auth.hash_password("lozinka123"))
    db.mark_email_verified("bez.imena@test.local")
    with db.engine.begin() as conn:                                    # dario's plan has lapsed
        conn.execute(sa_text("UPDATE memberships SET next_payment = next_payment - 60 WHERE user_id = :u"), {"u": dario})
    want = [("bez.imena@test.local · bez.imena@test.local", "bez.imena@test.local", "", "bez članarine", u.id),
            ("Cvita Horvat · cvita@test.local", "Cvita Horvat", "cvita@test.local", "bez članarine", cvita),
            ("Čedo Babić · cedo@test.local", "Čedo Babić", "cedo@test.local", "Grupni trening · Online trening", cedo),
            ("Dario Kovač · dario@test.local", "Dario Kovač", "dario@test.local", "bez članarine", dario)]
    for email in ("coach@test.local", "trener@test.local"):
        c = client_for(email)
        page = c.get("/kartoni").text
        assert list_rows(page, "/karton/clan", "/kartoni", "Otvori karton →") == want, email
        order = [int(i) for i in re.findall(r'<form method="post" action="/kao/(\d+)"><button', c.get("/kao").text)]
        assert [row[4] for row in want] == order                        # /kao's order
        assert "<title>Kartoni — QMT</title>" in page
        assert '<h1>Kartoni</h1>\n<p class="hint">Otvori karton člana: čitaš ga i u njega upisuješ.</p>\n<div class="kao">' in page
        assert 'class="kao-search" role="search" hidden' in page and 'class="hint kao-found" aria-live="polite" hidden' in page
        assert '· <a class="tlink" href="/kartoni">prikaži sve</a>' in page and 'qmtFold(row.getAttribute("data-find"))' in page
        main = page.split("<main")[1]
        assert "Amir Trener" not in main and "Tvrtko Vlasnik" not in main and "Zapis svih radnji" not in main, email
    assert client_for("cvita@test.local").get("/kartoni").status_code == 403
    assert TestClient(app).get("/kartoni", follow_redirects=False).headers["location"] == "/login"
    with db.engine.begin() as conn:                                    # an empty list
        conn.execute(sa_text("DELETE FROM users WHERE id <> :c"), {"c": coach})
    assert "Još nema članova." in client_for("coach@test.local").get("/kartoni").text


def test_the_admins_dvoranski_treninzi_lists_every_member_and_the_templates():
    """The admin's Dvoranski treninzi (/dvoranski/clanovi, Treninzi →
    Dvoranski treninzi), the trainer's and the owner's: the /kao page's look,
    its lead "Pripremi ili dodaj trening članu.", "Predlošci treninga →"
    (one .act, the templates' list) under it, and every member in /kao's
    order, a member with no gym plan too (sara: his tab says why nothing
    can be added; since build 4 of the admin view under Svi or Bez
    članarine, the list opening on Dvorana: the chips' own test below),
    each "Otvori treninge →" posting clan and natrag=/dvoranski/clanovi to
    /dvoranski/clan; "prikaži sve" this page in Svi. A member is refused, a
    guest goes to log in."""
    coach, owner, ivan, ana, sara = people()
    for email in ("coach@test.local", "trener@test.local"):
        page = client_for(email).get("/dvoranski/clanovi").text
        assert "<title>Dvoranski treninzi — QMT</title>" in page
        assert ('<h1>Dvoranski treninzi</h1>\n<p class="hint">Pripremi ili dodaj trening članu.</p>\n'
                '<p class="dv-tpl"><a class="act" href="/dvoranski/predlosci">Predlošci treninga →</a></p>\n<div class="kao">') in page
        rows = list_rows(page, "/dvoranski/clan", "/dvoranski/clanovi", "Otvori treninge →")
        assert [(name, plans, i) for _, name, _, plans, i in rows] == [
            ("Ana Kovač", "Grupni trening", ana), ("Ivan Horvat", "Grupni trening · Online trening", ivan),
            ("Sara Jurić", "bez članarine", sara)], email
        assert page.split("<main")[1].count('href="/dvoranski/predlosci"') == 1
        assert '· <a class="tlink" href="/dvoranski/clanovi?grupa=svi">prikaži sve</a>' in page
    assert client_for("ivan@test.local").get("/dvoranski/clanovi").status_code == 403
    assert TestClient(app).get("/dvoranski/clanovi", follow_redirects=False).headers["location"] == "/login"


def test_staffs_own_karton_and_tab_carry_no_search_and_no_templates():
    """The admin operations left the member tabs (28.11.2026): staff's own
    Karton has no search for a member (its lead right over the cards, no
    form, no field, no rows of members), staff's own Dvoranski treninzi
    neither, nor "Predlošci treninga →"; a member's own pages, the trainer's
    view of a karton and his pages while staff act as him (either way in)
    never had them. The two entries stay, the lists post them (above)."""
    coach, owner, ivan, ana, sara = people()
    for email in ("coach@test.local", "trener@test.local"):
        c = client_for(email)
        karton, tab = c.get("/karton").text, c.get("/dvoranski").text
        for page in (karton, tab):
            main = page.split("<main")[1]
            assert not has_search(page) and 'action="/karton/clan"' not in page and 'action="/dvoranski/clan"' not in page
            assert "/dvoranski/predlosci" not in main and "Predlošci treninga" not in main and "Ana Kovač" not in main
        head = karton.split("<h1>")[1].split('<div class="k-cards">')[0]
        assert "<form" not in head and "<select" not in head, email
        assert 'class="dv-tpl"' not in tab and 'href="/kartoni"' not in tab   # the member view's bar: no admin link
    assert not has_search(client_for("ivan@test.local").get("/karton").text)
    c = client_for("coach@test.local")
    assert not has_search(c.get(f"/karton/{ivan}").text)
    for way in ("whole", "tab"):
        if way == "tab":
            enter_tab(c, ivan, "/dvoranski", natrag="/dvoranski/clanovi")
        else:
            enter(c, ivan)
        for path in ("/karton", "/dvoranski"):
            page = c.get(path).text
            assert bar(page) is not None and not has_search(page) and "Predlošci treninga" not in page, (way, path)
        c.post(f"/kao/izlaz?kao={ivan}")


def test_each_list_enters_a_tabs_view_of_the_member_and_refuses_the_rest():
    """The two entries (27.11.2026, evening; since 28.11.2026 posted by the
    admin's lists' rows): POST /karton/clan (Kartoni's) and POST
    /dvoranski/clan (the admin's Dvoranski treninzi's), each `clan` a
    member's id (its spaces aside) and `natrag` the list, for the trainer
    and the owner alike → a tab's view of him, landing on that tab, his own
    page under the strip: the session's four keys (as_user_id him, as_seen
    now, as_back the list, as_scope), the entry the record's row (the
    route's path); "Izađi" back to the list it was entered from. With no
    `natrag` sent, the list all the same; one of another site, never ("/").
    A trainer's or the owner's id, an id naming nobody, nothing, junk: back
    to the list saying "Odaberi člana s popisa." at its top, nothing
    entered, no row. The search's GET of 27.11.2026 enters nothing: it leads
    to the Karton tab. A member asking is refused (403), a guest goes to log
    in. POST /kao stays gone (405)."""
    coach, owner, ivan, ana, sara = people()
    names = {coach: "Amir Trener", owner: "Tvrtko Vlasnik"}
    for email, staff in (("coach@test.local", coach), ("trener@test.local", owner)):
        for tab, lst in LISTS.items():
            c = client_for(email)
            before = time.time()
            r = c.post(f"{tab}/clan", data={"clan": f" {ana} ", "natrag": lst}, follow_redirects=False)
            assert (r.status_code, r.headers["location"]) == (303, tab), (email, tab)
            s = session_of(c)
            assert (s["user_id"], s["as_user_id"], s["as_back"], s["as_scope"]) == (staff, ana, lst, "tab"), (email, tab)
            assert before - 1 <= s["as_seen"] <= time.time() + 1
            assert record()[0] == (names[staff], "Ana Kovač", "POST", f"{tab}/clan", 303), (email, tab)
            page = c.get(tab).text
            assert bar(page) is not None and f'<body data-kao="{ana}">' in page, (email, tab)
            assert c.post(f"/kao/izlaz?kao={ana}", follow_redirects=False).headers["location"] == lst
            assert enter_tab(c, ana, tab).headers["location"] == tab and keys(c)["as_back"] == lst   # no natrag: the list
            c.post(f"/kao/izlaz?kao={ana}")
            assert enter_tab(c, ana, tab, natrag="https://evil.example/").headers["location"] == tab
            assert keys(c)["as_back"] == "/"
            c.post(f"/kao/izlaz?kao={ana}")
            rows = len(record())
            refused = f"{lst}?error=Odaberi člana s popisa."
            for clan in (str(coach), str(owner), "999999", "", "   ", "abc", "-3", f"{ana}.0", "1" * 12):
                r = enter_tab(c, clan, tab, natrag=lst)
                assert (r.status_code, location(r)) == (303, refused), (email, tab, clan)
            assert location(c.post(f"{tab}/clan", follow_redirects=False)) == refused   # no field at all
            assert keys(c) == {} and len(record()) == rows, (email, tab)
            main = c.get(refused).text.split("<main")[1].split("</main>")[0]
            alert = '<div class="alert" role="alert">\n      <span>Odaberi člana s popisa.</span>'
            assert main.count('class="alert"') == 1 and main.index(alert) < main.index("<h1>"), (email, tab)
        r = c.get("/karton/clan", params={"clan": str(ana)}, follow_redirects=False)   # the morning's GET
        assert (r.status_code, r.headers["location"]) == (303, "/kartoni") and keys(c) == {}   # where the search is now
        assert c.post("/kao", data={"clan": str(ana), "natrag": "/karton"}, follow_redirects=False).status_code == 405
    member = client_for("ivan@test.local")
    for tab in LISTS:
        assert enter_tab(member, ana, tab).status_code == 403 and keys(member) == {}
        r = enter_tab(TestClient(app), ana, tab)
        assert r.status_code == 303 and r.headers["location"] == "/login"
    assert member.get("/karton/clan").status_code == 403


# ---------- the lists' chips (28.11.2026, build 4 of the admin view) ----------

# each staff list of members and the chip it opens on (the plan agreed:
# "Dvoranski treninzi opens on Dvorana, Kartoni on Svi"; /kao on Svi)
LIST_PATHS = (("/kao", "svi"), ("/kartoni", "svi"), ("/dvoranski/clanovi", "dvorana"))
CHIP_WORDS = (("svi", "Svi"), ("dvorana", "Dvorana"), ("online", "Online"), ("bez", "Bez članarine"))
# a list's row as drawn: the name (data-find's first part), its groups, whether hidden
ROW = re.compile(r'<div class="kao-row" data-find="([^"]*) · [^"]*" data-grupe="([a-z ]+)"( hidden)?>')
DAY = timedelta(days=1)


def due(uid: int, kind: str, next_payment: date) -> None:
    """A plan of his whose next payment falls on `next_payment`: recorded,
    then dated, so its state is its dates', never the clock's luck."""
    db.record_payment(uid, kind)
    with db.engine.begin() as conn:
        conn.execute(sa_text("UPDATE memberships SET next_payment = :d WHERE user_id = :u AND plan = :p"),
                     {"d": next_payment, "u": uid, "p": kind})


def grouped() -> dict[str, tuple[str, ...]]:
    """A trainer who is not the owner, the owner (who does not train), and
    six members whose groups the chips' tests read their counts off: Ana's
    grupni (Dvorana), Ivan's grupni and online (Dvorana and Online), Olga's
    online (Online), Marko's grupni lapsed, Sara with no plan ever and
    Petar's prehrana alone (the three Bez članarine). Each member's groups
    by his name."""
    make_user("coach@test.local", "Amir Trener", is_trainer=True)
    make_user("trener@test.local", "Tvrtko Vlasnik")
    make_user("ana@test.local", "Ana Kovač", plans=("grupni",))
    make_user("ivan@test.local", "Ivan Horvat", plans=("grupni", "online"))
    make_user("olga@test.local", "Olga Mrežna", plans=("online",))
    due(make_user("marko@test.local", "Marko Babić"), "grupni", config.today() - 40 * DAY)
    make_user("sara@test.local", "Sara Jurić")
    make_user("petar@test.local", "Petar Prehrana", plans=("prehrana",))
    return {"Ana Kovač": ("dvorana",), "Ivan Horvat": ("dvorana", "online"), "Olga Mrežna": ("online",),
            "Marko Babić": ("bez",), "Sara Jurić": ("bez",), "Petar Prehrana": ("bez",)}


def in_groups(groups: dict[str, tuple[str, ...]]) -> dict[str, list[str]]:
    """Each chip's members, in the list's order (the alphabet's: these names
    start with plain letters), "svi" every one."""
    order = sorted(groups)
    return {"svi": order, **{g: [n for n in order if g in groups[n]] for g in ("dvorana", "online", "bez")}}


def count_queries(fn) -> int:
    """How many statements `fn` sends to the database."""
    sent = []
    listen = lambda *args, **kw: sent.append(1)     # noqa: E731
    event.listen(db.engine, "before_cursor_execute", listen)
    try:
        fn()
    finally:
        event.remove(db.engine, "before_cursor_execute", listen)
    return len(sent)


def test_a_members_groups_are_what_he_runs_now():
    """The groups (app._member_groups), derived from the plans a member runs
    now and never stored: Dvorana while a gym plan runs (each of the four
    that book termini, and one in its grace week: it still runs), Online
    while the online plan runs, both when both (that order); a gym plan
    lapsed and online running is Online alone; every plan lapsed, none
    ever, prehrana alone: Bez članarine. One rule: the two tabs ask it
    (_has_gym, _has_online agree with every member's groups, a staff
    account has both), and every list's rows carry it (data-grupe). Staff
    are in no list, as before."""
    today = config.today()
    coach = make_user("coach@test.local", "Amir Trener", is_trainer=True)
    owner = make_user("trener@test.local", "Tvrtko Vlasnik")
    ahead, grace, lapsed = today + 20 * DAY, today - 2 * DAY, today - 8 * DAY   # lapsed: dospijeće was yesterday
    want: dict[str, tuple[str, ...]] = {}
    cases = (("Ana Grupni", (("grupni", ahead),), ("dvorana",)),
             ("Bruno Individualni", (("individualni", ahead),), ("dvorana",)),
             ("Cvita Poluindividualni", (("poluindividualni", ahead),), ("dvorana",)),
             ("Davor Rehabilitacija", (("rehabilitacija", ahead),), ("dvorana",)),
             ("Ema Dospijeva", (("grupni", grace),), ("dvorana",)),
             ("Filip Online", (("online", ahead),), ("online",)),
             ("Goran Oboje", (("grupni", ahead), ("online", ahead)), ("dvorana", "online")),
             ("Hana Prebacila", (("grupni", lapsed), ("online", ahead)), ("online",)),
             ("Iva Istekla", (("grupni", lapsed), ("online", lapsed)), ("bez",)),
             ("Jura Nikad", (), ("bez",)),
             ("Kata Prehrana", (("prehrana", ahead),), ("bez",)))
    for i, (name, plans, groups) in enumerate(cases):
        uid = make_user(f"clan{i}@test.local", name)
        for kind, next_payment in plans:
            due(uid, kind, next_payment)
        want[name] = groups
    members = web._kao_members()
    assert {m["name"]: m["groups"] for m in members} == want                   # staff in none
    for m in members:
        assert web._has_gym(m["user"]) == ("dvorana" in m["groups"]), m["name"]
        assert web._has_online(m["user"]) == ("online" in m["groups"]), m["name"]
    for staff in (coach, owner):
        assert web._has_gym(db.get_user(staff)) and web._has_online(db.get_user(staff))
    assert web._member_groups([]) == web._member_groups(["prehrana"]) == ("bez",)
    assert web._member_groups(["online", "rehabilitacija", "prehrana"]) == ("dvorana", "online")
    c = client_for("coach@test.local")
    for path, _ in LIST_PATHS:
        rows = {unescape(n): tuple(g.split()) for n, g, _ in ROW.findall(c.get(path).text)}
        assert rows == want, path


def test_a_list_reads_its_members_groups_at_once():
    """The groups come with the members in the one read the lists made
    already (_kao_members over db.memberships_overview): each list, with a
    chip asked for and a search kept or not, sends as many statements for
    fifty members as for five, of every group."""
    make_user("coach@test.local", "Amir Trener", is_trainer=True)
    kinds = ((), ("grupni",), ("online",), ("grupni", "online"), ("prehrana",))

    def members(first: int, last: int) -> None:
        for i in range(first, last):
            make_user(f"clan{i}@test.local", f"Član Broj{i}", plans=kinds[i % len(kinds)])

    c = client_for("coach@test.local")
    asked = [path + query for path, _ in LIST_PATHS for query in ("", "?grupa=bez&q=broj")]

    def statements() -> dict[str, int]:
        return {a: count_queries(lambda: c.get(a)) for a in asked}

    members(0, 5)
    statements()                                                         # the first requests' own reads aside
    five = statements()
    members(5, 50)
    assert len(web._kao_members()) == 50
    assert statements() == five, (five, statements())


def test_each_list_opens_on_its_chip_and_draws_the_group_asked_for():
    """The four chips under the search, Svi · Dvorana · Online · Bez
    članarine, a group labelled for a screen reader: each a link to its list
    (?grupa= when it is not the page's own chip), its count the whole
    list's; Kartoni and /kao open on Svi, the admin's Dvoranski treninzi on
    Dvorana; ?grupa= each value chooses its chip (aria-current) and draws
    its members' rows, the rest hidden; one that is none of the four is the
    page's own. The count line shows while a chip other than Svi narrows the
    list ("2 od 6 · prikaži sve", "prikaži sve" leading to Svi), hidden on
    Svi; a group with nobody says "Nema članova u ovoj skupini.". With ?q=
    the chips keep it (the search is the script's: the server draws the
    group), "prikaži sve" drops it."""
    groups = grouped()
    members = in_groups(groups)
    every = len(members["svi"])
    c = client_for("coach@test.local")

    def href(path: str, start: str, key: str, q: str = "") -> str:
        query = "&".join(([f"grupa={key}"] if key != start else []) + ([f"q={q}"] if q else []))
        return path + ("?" + query if query else "")

    for path, start in LIST_PATHS:
        for asked in (None, "svi", "dvorana", "online", "bez", "nepostoji", "", "SVI"):
            group = asked if asked in ("svi", "dvorana", "online", "bez") else start
            page = c.get(path, params={} if asked is None else {"grupa": asked}).text
            where = (path, asked)
            assert ('<div class="tagbar kao-groups" role="group" aria-label="Skupina članova" '
                    f'data-start="{start}">') in page, where
            for key, word in CHIP_WORDS:
                current = ' aria-current="true"' if key == group else ""
                assert (f'<a class="tag-chip" href="{href(path, start, key)}" data-grupa="{key}"{current}>{word} '
                        f'<span class="kao-gn">{len(members[key])}</span></a>') in page, (where, key)
            bar = page.split('<div class="tagbar kao-groups"')[1].split("</div>")[0]
            assert bar.count("<a ") == len(CHIP_WORDS) and bar.count('aria-current="true"') == 1, where
            rows = ROW.findall(page)
            assert [unescape(n) for n, _, hid in rows if not hid] == members[group], where
            assert sorted(unescape(n) for n, _, hid in rows if hid) == sorted(set(members["svi"]) - set(members[group])), where
            found = re.search(r'<p class="hint kao-found" aria-live="polite"( hidden)?><span class="kao-n">([^<]*)</span>'
                              r' od ([^<]*) · <a class="tlink" href="([^"]*)">prikaži sve</a></p>', page)
            assert found.groups() == ((" hidden" if group == "svi" else None), str(len(members[group])), str(every),
                                      href(path, start, "svi")), where
            assert '<p class="kao-nogroup" hidden>Nema članova u ovoj skupini.</p>' in page, where
        # a search kept: the chips carry it, "prikaži sve" not; the server draws the group alone
        page = c.get(path, params={"grupa": "online", "q": "ivan horvat"}).text
        for key, _ in CHIP_WORDS:                                        # (an attribute's "&" is "&amp;")
            assert f'href="{href(path, start, key, "ivan%20horvat").replace("&", "&amp;")}" data-grupa="{key}"' in page, (path, key)
        assert '<a class="tlink" href="{}">prikaži sve</a>'.format(href(path, start, "svi")) in page
        assert [unescape(n) for n, _, hid in ROW.findall(page) if not hid] == members["online"], path
    # nobody in a group: Online with every online plan lapsed
    with db.engine.begin() as conn:
        conn.execute(sa_text("UPDATE memberships SET next_payment = next_payment - 60 WHERE plan = 'online'"))
    groups = {**groups, "Ivan Horvat": ("dvorana",), "Olga Mrežna": ("bez",)}
    members = in_groups(groups)
    assert members["online"] == []
    for path, start in LIST_PATHS:
        page = c.get(path, params={"grupa": "online"}).text
        assert (f'<a class="tag-chip" href="{href(path, start, "online")}" data-grupa="online" aria-current="true">'
                f'Online <span class="kao-gn">{len(members["online"])}</span></a>') in page, path
        assert '<p class="kao-nogroup">Nema članova u ovoj skupini.</p>' in page, path
        assert '<p class="kao-none" hidden>Nijedan član ne odgovara traženju' in page, path
        assert all(hid for _, _, hid in ROW.findall(page)), path
        assert f'<span class="kao-n">{len(members["online"])}</span> od {every} · ' in page, path


# ---------- a tab's view (27.11.2026, evening) ----------

def test_in_a_tabs_view_the_members_karton_and_tab_are_his():
    """Entered from Kartoni (the Karton tab's search until 28.11.2026), the member's two areas are his,
    read and write: his karton (its title naming him, his limitations), a
    form of it sent with his page's marker saves into his karton and is
    recorded (his limitations, a document under them: multipart), his file
    under /media is his to open, his training opened from his diary ("Otvori
    trening") is his page, "← Natrag" from it his tab, a write on it his and
    recorded, his tab his (its title naming him). Nothing of it is the
    staff member's; the view lasts through all of it (the session's four
    keys)."""
    coach, owner, ivan, ana, sara = people()
    db.reset_gym_templates()
    sid = db.add_oneoff_session("Snaga", datetime.now(config.TZ) - timedelta(hours=1), 60, 8, None)
    with db.session_scope() as s:
        s.add(Booking(user_id=ivan, session_id=sid))
    tid = db.gym_training_for(ivan, sid)
    bid = db.add_gym_block(tid, ivan, "stanica")
    db.set_gym_station(bid, ivan, db.create_exercise("Goblet čučanj"), 3, 10)
    c = client_for("coach@test.local")
    assert enter_tab(c, ivan).headers["location"] == "/karton"
    karton = c.get("/karton").text
    assert h1(seen(karton)) == "<h1>Karton — Ivan Horvat</h1>" and bar(karton) is not None
    r = c.post(f"/karton/ogranicenja?kao={ivan}", data={"text": "Koljeno."}, follow_redirects=False)
    assert location(r) == "/karton?ok=Ograničenja su spremljena.#ogranicenja"
    r = c.post(f"/karton/ogranicenja/dokument?kao={ivan}", data={"naziv": "Nalaz"},
               files={"dokument": ("nalaz.pdf", b"%PDF-1.4\n%test\n", "application/pdf")}, follow_redirects=False)
    assert location(r) == "/karton?ok=Dokument je spremljen.#ogranicenja"
    [doc] = db.limitation_files(ivan)
    assert db.get_user(ivan).limitations == "Koljeno." and db.get_user(coach).limitations == ""
    assert db.limitation_files(coach) == [] and doc.file.startswith(f"nalaz-{ivan}-")
    r = c.get(f"/media/{doc.file}")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF-")
    karton = c.get("/karton").text
    assert f'href="/dvoranski/trening/{tid}"' in karton                 # his diary's "Otvori trening"
    page = c.get(f"/dvoranski/trening/{tid}").text
    assert bar(page) is not None and '<a class="act act-quiet" href="/dvoranski"><span class="t">← Natrag</span></a>' in page
    r = c.post(f"/dvoranski/trening/{tid}/blok?kao={ivan}", data={"vrsta": "stanica"}, follow_redirects=False)
    assert r.status_code == 303 and len(db.gym_training(tid, ivan).blocks) == 2
    tab = c.get("/dvoranski").text
    assert h1(seen(tab)) == '<h1><span class="t">Dvoranski treninzi</span> — Ivan Horvat</h1>' and f'id="dv-s-{sid}"' in tab
    who, whom = "Amir Trener", "Ivan Horvat"
    assert record()[:4] == [(who, whom, "POST", f"/dvoranski/trening/{tid}/blok", 303),
                            (who, whom, "POST", "/karton/ogranicenja/dokument", 303),
                            (who, whom, "POST", "/karton/ogranicenja", 303), (who, whom, "POST", "/karton/clan", 303)]
    assert set(keys(c)) == {"as_user_id", "as_seen", "as_back", "as_scope"} and keys(c)["as_user_id"] == ivan


def test_a_tabs_view_draws_the_staff_members_own_bar():
    """In a tab's view the top bar is the staff member's own, since
    28.11.2026 the admin view's (decision A5 of the admin view's build 2):
    its three menus and every item (the owner's Korisnici and Statistika
    too), his avatar and his name in its menu, the area's tab lit and its
    item current (Članovi → Kartoni on his /karton, Treninzi → Dvoranski
    treninzi on his /dvoranski and a training's page), and every link of it
    the exit, GET /kao/izlaz?kamo=<its address>, the brand's and the
    account menu's too; the logout stays a form; no view switch (a form
    sent from it would end the view and run nothing). No ✎ pill, no
    install banner, no phone reminder (ana has no phone: the whole app shows
    it her, as before). The whole app's view keeps the member's bar, its
    links plain."""
    coach, owner, ivan, ana, sara = people()
    sid = db.add_oneoff_session("Snaga", datetime.now(config.TZ) - timedelta(hours=1), 60, 8, None)
    with db.session_scope() as s:
        s.add(Booking(user_id=ana, session_id=sid))
    tid = db.gym_training_for(ana, sid)
    for email, name, owners in (("coach@test.local", "Amir Trener", False), ("trener@test.local", "Tvrtko Vlasnik", True)):
        c = client_for(email)
        enter_tab(c, ana, natrag="/kartoni")
        for path, tab, item in (("/karton", "clanovi", "/kartoni"), ("/dvoranski", "treninzi", "/dvoranski/clanovi"),
                                (f"/dvoranski/trening/{tid}", "treninzi", "/dvoranski/clanovi")):
            page = c.get(path).text
            hrefs = nav_hrefs(page)
            assert hrefs and all(h.startswith("/kao/izlaz?kamo=/") for h in hrefs), (email, path, hrefs)
            assert {h.split("=", 1)[1] for h in hrefs} == {"/", "/kartoni", "/clanarine", "/kao", "/raspored", "/admin",
                                                         "/dvoranski/clanovi", "/programi", "/treninzi/vjezbe", "/tekstovi",
                                                         "/upitnik", "/vodic", "/profil"} | (
                {"/korisnici", "/statistika"} if owners else set()), path
            assert re.search(rf'id="{tab}Btn" class="navbtn menu-btn on"', page), (email, path)
            assert re.findall(r'<a href="([^"]+)" role="menuitem" aria-current="page">', page) == \
                [f"/kao/izlaz?kamo={item}"], (email, path)
            assert all(m in page for m in ADMIN_BAR) and f'title="{name}"' in page and f"<strong>{name}</strong>" in seen(page)
            assert '<form method="post" action="/logout">' in page and 'action="/pogled"' not in page
            for gone in ('id="copyToggle"', 'id="phoneCard"', 'id="a2hs"', "data-copy="):
                assert gone not in page, (email, path, gone)
            assert bar(page) is not None and "Gledaš kao: <strong>Ana Kovač</strong>" in seen(bar(page))
        c.post(f"/kao/izlaz?kao={ana}")
    c = client_for("coach@test.local")
    enter(c, ana)                                                        # the whole app: the member's bar
    page = c.get("/karton").text
    assert "/kao/izlaz?kamo=" not in page and not any(m in page for m in ADMIN_BAR) and 'id="phoneCard"' in page
    assert '<a href="/karton" class="on">Karton</a>' in page and "/treninzi" not in nav_hrefs(page)   # her plans' tabs


def test_a_bar_link_ends_the_view_and_lands_on_the_staff_members_own_page():
    """GET /kao/izlaz?kamo=<address> (every link of a tab's view's bar): the
    view ends, its four keys gone, and it lands where the link says, the
    staff member's own page, no flash, no row of the record (a GET); the
    tabs of the two areas lead to his own Karton and Dvoranski treninzi (no
    search on either since 28.11.2026). An address of another site is never
    followed ("/"); with none, where "Izađi" goes (the list the view was
    entered from). Out of a view it just goes."""
    coach, owner, ivan, ana, sara = people()
    c = client_for("coach@test.local")
    for kamo, lands in (("/raspored", "/raspored"), ("/karton", "/karton"), ("/dvoranski", "/dvoranski"),
                        ("https://evil.example/", "/"), ("//evil.example", "/"), ("", "/kartoni")):
        enter_tab(c, ivan)
        rows = len(record())
        r = c.get("/kao/izlaz", params={"kamo": kamo} if kamo else {}, follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (303, lands), kamo
        assert keys(c) == {} and len(record()) == rows, kamo
    page = c.get("/karton").text
    assert bar(page) is None and 'data-copy="karton.staff.own_lead"' in page and not has_search(page)   # his own Karton
    assert c.get("/kao/izlaz?kamo=/admin", follow_redirects=False).headers["location"] == "/admin"   # out: it goes
    enter_tab(c, ivan, "/dvoranski", natrag="/dvoranski/clanovi")
    assert c.get("/kao/izlaz", follow_redirects=False).headers["location"] == "/dvoranski/clanovi"   # none: Izađi's


def test_off_the_two_areas_a_request_ends_the_view_before_it_runs():
    """In a tab's view any request off the member's two areas, and no exit,
    ends the view before it runs and is the staff member's own: a page asked
    for (a navigation) is sent on to its very address, its query kept, with
    one flash, "Izašao/la si iz pregleda člana.", which the staff member
    reads in his own slash form ("Izašao si …", "Izašla si …"), on his own
    page; anything else that is no write (no page asked for) runs as his at
    once; a write that still carries the member's marker runs nothing (the
    view has ended: nothing booked, nothing saved), and after the end a form
    of the member's page saves nothing either; a write with no marker is his
    own and runs. What the two areas' pages load by themselves never ends
    it: the static files, the service worker, a browser's own icon request,
    his /media."""
    coach, owner, ivan, ana, sara = people()
    mia = make_user("mia@test.local", "Mia Trenerica", is_trainer=True)
    db.update_profile(coach, "Amir", "Trener", date(1990, 1, 1), "", sex="m")
    db.update_profile(mia, "Mia", "Trenerica", date(1990, 1, 1), "", sex="f")
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + timedelta(days=2), 60, 8, None)
    for email, words in (("coach@test.local", "Izašao si iz pregleda člana."),
                         ("mia@test.local", "Izašla si iz pregleda člana.")):
        c = client_for(email)
        enter_tab(c, ivan)
        r = c.get("/raspored", params={"week": "2026-12-07"}, headers=PAGE, follow_redirects=False)
        assert r.status_code == 303 and location(r) == f"/raspored?week=2026-12-07&ok={LEFT}", email
        assert keys(c) == {}, email
        page = c.get(r.headers["location"]).text
        assert f'<div class="alert ok" role="status">{words}</div>' in page and bar(page) is None, email
        assert 'id="clanoviBtn"' in page and "/kao/izlaz?kamo=" not in page, email   # his own bar: the admin view's
    # what a navigation looks like when it comes to the server (app._asks_for_page):
    # a browser's own ("document"); one handed on by the app's service worker,
    # which every returning visitor has (Chromium: Sec-Fetch-Dest "empty",
    # Sec-Fetch-Mode "navigate": Fable's review, 27.11.2026, found the flash
    # missing under it); an old client's (HTML in its Accept). A script's
    # fetch is no page: the view ends and it is served, with no redirect.
    c = client_for("coach@test.local")
    for headers, page in (({"Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate"}, True),
                          ({"Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "navigate", "Accept": "text/html"}, True),
                          ({"Accept": "text/html,application/xhtml+xml"}, True),
                          ({"Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Accept": "text/html"}, False),
                          ({"Sec-Fetch-Dest": "image", "Sec-Fetch-Mode": "no-cors"}, False)):
        enter_tab(c, ivan)
        r = c.get("/moja-clanarina", headers=headers, follow_redirects=False)
        assert keys(c) == {}, headers
        if page:
            assert r.status_code == 303 and location(r) == f"/moja-clanarina?ok={LEFT}", headers
        else:
            assert r.status_code == 200 and "location" not in r.headers, headers
    enter_tab(c, ivan)
    for free in ("/static/logo.png", "/sw.js", "/healthz", "/favicon.ico", "/apple-touch-icon.png"):
        c.get(free, headers=PAGE)
        assert keys(c).get("as_scope") == "tab", free                  # never the end of the view
    r = c.get("/admin", follow_redirects=False)                        # no page asked for: his at once
    assert r.status_code == 200 and "<h1>" in r.text and keys(c) == {}
    enter_tab(c, ivan)
    r = c.post(f"/book/{sid}?kao={ivan}", follow_redirects=False)       # his marker, off the areas
    assert location(r) == ENDED and keys(c) == {} and db.roster(sid) == []
    r = c.post(f"/karton/ogranicenja?kao={ivan}", data={"text": "Leđa."}, follow_redirects=False)
    assert location(r) == ENDED                                         # after the end: his page saves nothing
    assert db.get_user(ivan).limitations == "" == db.get_user(coach).limitations
    enter_tab(c, ivan)
    r = c.post("/copy/gym.tab.lead", data={"text": "Moja dvorana."}, follow_redirects=False)   # no marker: his own
    assert r.status_code == 200 and r.json()["ok"] and keys(c) == {}
    assert db.copy_texts()["gym.tab.lead"] == "Moja dvorana."
    rows = [x for x in record() if x[3] != "/karton/clan"]
    assert rows == [], rows                                             # nothing of it is the member's record


def test_the_staff_routes_under_the_two_areas_are_staffs_and_end_the_view():
    """The areas (app._in_member_tab) are the member's, every route under
    /karton and /dvoranski and /media, but those only staff may use (their
    endpoints ask _require_trainer or _require_owner: read from the app's
    own routes): the entries (/karton/clan, /dvoranski/clan), the read-only
    karton (/karton/<id>), since 28.11.2026 the admin's list of members
    Dvoranski treninzi (/dvoranski/clanovi), and the templates
    (/dvoranski/predlosci…). In a tab's view each of those is the staff
    member's: a page of them ends the view and is his (the read-only
    karton, the list, the templates' list), and the other entry, from a page
    of his own, leaves the one view for the other member's."""
    coach, owner, ivan, ana, sara = people()
    staff_paths, member_paths = set(), set()
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(("/karton", "/dvoranski", "/media")):
            continue
        names = route.endpoint.__code__.co_names
        path = re.sub(r"\{(\w+)\}", "1", route.path)
        (staff_paths if "_require_trainer" in names or "_require_owner" in names else member_paths).add(path)
    assert {"/karton/clan", "/karton/1", "/dvoranski/clan", "/dvoranski/clanovi", "/dvoranski/predlosci",
            "/dvoranski/predlosci/1", "/dvoranski/predlosci/1/blok/1/obrisi"} <= staff_paths
    assert [p for p in staff_paths if web._in_member_tab(p)] == []
    assert [p for p in member_paths if not web._in_member_tab(p)] == []
    assert {"/karton", "/karton/masa", "/dvoranski", "/dvoranski/trening/1/blok/1/odradeno", "/media/1"} <= member_paths
    c = client_for("coach@test.local")
    for path, words in ((f"/karton/{ana}", "<h1>Karton — Ana Kovač</h1>"), ("/dvoranski/predlosci", "Predlošci treninga"),
                        ("/dvoranski/clanovi", "Pripremi ili dodaj trening članu.")):
        enter_tab(c, ivan)
        r = c.get(path, headers=PAGE, follow_redirects=False)
        assert location(r) == f"{path}?ok={LEFT}" and keys(c) == {}, path
        page = c.get(r.headers["location"]).text
        assert words in seen(page) and bar(page) is None, path
    enter_tab(c, ivan)
    r = c.post("/dvoranski/clan", data={"clan": str(ana)}, follow_redirects=False)   # the other entry, from his own page
    assert r.headers["location"] == "/dvoranski" and keys(c)["as_user_id"] == ana and keys(c)["as_scope"] == "tab"


def test_a_tabs_view_keeps_the_idle_limit_and_izadji_returns_to_its_tab(monkeypatch):
    """The idle limit holds in a tab's view as in the whole app: after
    ACT_AS_IDLE_MINUTES with no request the first request, a page or a
    write, runs nothing and goes to the picker saying the view expired.
    "Izađi" ends it back on the list it was entered from (since
    28.11.2026 the admin's: Kartoni for the karton, the admin's Dvoranski
    treninzi for the tab; until then the tab whose search it was), a row of
    the record as every exit."""
    coach, owner, ivan, ana, sara = people()
    now = [time.time()]
    monkeypatch.setattr(web, "_clock", lambda: now[0])
    c = client_for("coach@test.local")
    enter_tab(c, ivan)
    now[0] += 29 * 60
    assert c.get("/karton").status_code == 200
    now[0] += 31 * 60
    assert location(c.get("/karton", follow_redirects=False)) == EXPIRED and keys(c) == {}
    enter_tab(c, ivan, "/dvoranski")
    now[0] += 31 * 60
    r = c.post(f"/karton/ogranicenja?kao={ivan}", data={"text": "Leđa."}, follow_redirects=False)
    assert location(r) == EXPIRED and keys(c) == {} and db.get_user(ivan).limitations == ""
    for tab, lst in LISTS.items():
        enter_tab(c, ivan, tab, natrag=lst)
        r = c.post(f"/kao/izlaz?kao={ivan}", follow_redirects=False)
        assert r.headers["location"] == lst and keys(c) == {} and record()[0][2:] == ("POST", "/kao/izlaz", 303)


def as_member_reads(page: str) -> str:
    """A page less what only staff acting as the member are shown or not
    shown around it: everything between <body and the top bar (the strip,
    its script, the page's marker) and the install banner (never while
    acting)."""
    page = page.split("<body", 1)[0] + page.split('<header class="topbar', 1)[1]
    return re.sub(r'<div id="a2hs" .*?(?=<dialog id="confirmDlg")', "", page, flags=re.S)


def test_the_whole_apps_way_in_is_as_before_but_for_the_two_titles():
    """The whole app (Gledaj kao član, a roster's "Kao član →", the read-only
    karton's "Otvori kao član") is untouched by the tab's view: no as_scope,
    the member's own bar, and a page of it is, byte for byte, the page the
    member himself reads but for what was always the view's (the strip, its
    script, the page's marker, the install banner); past the two areas the
    view goes on. The two titles name him while staff act as him, either way
    in ("Karton — Ivan Horvat", "Dvoranski treninzi — Ivan Horvat"); the
    member himself reads "Moj karton" and "Dvoranski treninzi" exactly as
    before, his name in no title of his. A whole app entered after a tab's
    view has no as_scope left."""
    coach, owner, ivan, ana, sara = people()
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + timedelta(days=1), 60, 8, None)
    db.book(ivan, sid)
    own = client_for("ivan@test.local")
    own.get("/karton")                                                   # the login's prompt asked, once
    c = client_for("coach@test.local")
    for way in ({}, {"natrag": f"/admin/session/{sid}", "kamo": "/raspored"}, {"natrag": f"/karton/{ivan}"}):
        enter(c, ivan, **way)
        assert "as_scope" not in session_of(c), way
        for path in ("/", "/raspored", "/moja-clanarina", "/prehrana", "/profil"):
            page = c.get(path, headers=PAGE).text
            assert bar(page) is not None and "/kao/izlaz?kamo=" not in page, (way, path)
            assert as_member_reads(page) == as_member_reads(own.get(path).text), (way, path)
        assert h1(seen(c.get("/karton").text)) == "<h1>Karton — Ivan Horvat</h1>"
        assert h1(seen(c.get("/dvoranski").text)) == '<h1><span class="t">Dvoranski treninzi</span> — Ivan Horvat</h1>'
        c.post(f"/kao/izlaz?kao={ivan}")
    mine = {path: own.get(path).text for path in ("/karton", "/dvoranski")}
    assert h1(mine["/karton"]) == '<h1><span class="t">Moj karton</span></h1>'
    assert h1(mine["/dvoranski"]) == '<h1><span class="t">Dvoranski treninzi</span></h1>'
    assert all("— Ivan Horvat" not in page for page in mine.values())
    enter_tab(c, ivan)                                                   # the picker's form, sent from a tab's view
    assert enter(c, ivan).headers["location"] == "/karton"
    assert "as_scope" not in session_of(c) and session_of(c)["as_user_id"] == ivan


def test_every_way_into_a_members_app_wears_the_admins_colour():
    """One look for every way into a member's app: /kao's "Otvori →", a
    roster's "Kao član →" and the trainer's view's "Otvori kao član" wear
    base.html's .act.act-kao (its background declared, a deeper tint on
    hover). Amber from build 4 (the owner: "The button to open as another
    user should also be in amber."), the admin's indigo since 28.11.2026
    (build 3 of the admin view: amber says a payment is due now; --admin on
    --admin-soft, tests/test_status.py measures it). The Karton tab's solid
    amber "Otvori kao član" (.btn-kao, from build 4) went on 27.11.2026
    with its way into the app: the tab's field opens a member's karton now
    (the tests above). The strip's "Izađi" keeps its words and its form."""
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
    for rule in (".act-kao { background: var(--admin-soft); color: var(--admin);",
                 ".act-kao:hover { background: color-mix(in srgb, var(--admin) 20%, transparent); color: var(--admin);"):
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
# the strip's words, of the member's name and of "Izađi" against what they
# really sit on (since 28.11.2026, build 3 of the admin view, the strip's
# own dark ground in both themes; the amber tint over the page's background
# until then)
STRIP = r"""() => {
  const bar = document.querySelector('.kao-bar'), who = bar.querySelector('.kao-as'), x = bar.querySelector('.kao-exit');
  const tb = document.querySelector('.topbar').getBoundingClientRect(), b = bar.getBoundingClientRect(), xr = x.getBoundingClientRect();
  const rgb = c => { const m = c.match(/[\d.]+/g).map(Number); return m.length > 3 ? m : [...m, 1]; };
  const lum = ([r, g, bl]) => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); };
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(bl); };
  const ratio = (a, c) => { const [h, l] = [lum(a), lum(c)].sort((p, q) => q - p); return (h + .05) / (l + .05); };
  const ground = rgb(getComputedStyle(bar).backgroundColor);
  const lineH = parseFloat(getComputedStyle(who).lineHeight);
  return {h: b.height, top: b.top, whoH: who.getBoundingClientRect().height, lineH, cut: who.scrollWidth > who.clientWidth,
          exitLeft: xr.left, exitRight: xr.right, exitH: xr.height, width: document.documentElement.clientWidth,
          pillTop: tb.top, pillBottom: tb.bottom, solid: ground[3] === 1,
          words: ratio(rgb(getComputedStyle(who).color), ground), name: ratio(rgb(getComputedStyle(who.querySelector('.st')).color), ground),
          exit: ratio(rgb(getComputedStyle(x).color), rgb(getComputedStyle(x).backgroundColor))};
}"""
# a title as a sighted reader has it: the name without its words for a screen reader
SEEN_H1 = ("() => { const h = document.querySelector('main h1').cloneNode(true); "
           "h.querySelectorAll('.st-sr').forEach(x => x.remove()); return h.textContent; }")


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
            check(s["solid"] and s["words"] >= 4.5 and s["name"] >= 4.5 and s["exit"] >= 4.5,
                  f"{where} contrast: words {s['words']:.2f}, name {s['name']:.2f}, Izađi {s['exit']:.2f}, solid {s['solid']}")
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


# an admin list (28.11.2026) as laid out: its rows shown (each name as a
# sighted reader has it: without its status's words for a screen reader,
# build 3), its count line, the box's text, the page's overflow
LISTED = r"""() => ({rows: [...document.querySelectorAll('.kao-row')].filter(r => !r.hidden).map(r => {
    const s = r.querySelector('strong').cloneNode(true); s.querySelectorAll('.st-sr').forEach(x => x.remove()); return s.textContent; }),
  found: (document.querySelector('.kao-found') || {}).hidden === false ? document.querySelector('.kao-found').textContent.trim() : null,
  box: (document.querySelector('form.kao-search input') || {}).value,
  overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth})"""
# the open ☰ drawer: its captions, its rows (label, href) and the current one
DRAWER = """() => ({caps: [...document.querySelectorAll('#mainNav .nav-cap')].map(p => p.textContent),
  rows: [...document.querySelectorAll('#mainNav a')].filter(a => a.getBoundingClientRect().width > 0)
           .map(a => [a.textContent.trim(), a.getAttribute('href')]),
  current: [...document.querySelectorAll('#mainNav [aria-current="page"]')].map(a => a.textContent.trim())})"""


def test_kartoni_and_the_admin_pages_on_a_phone(server):
    """At 390px (dark) and 360px (light), touch, a trainer who is not the
    owner: the admin's three pages of 28.11.2026, Kartoni, its Dvoranski
    treninzi and its Online treninzi, never scroll sideways. On Kartoni the
    filter shows as typed ("kov": Ana alone, "1 od 3"; "prikaži sve" clears
    it); Ana's "Otvori karton →" opens her karton at once, a tab's view of
    her (/karton under the strip, "Karton — Ana Kovač"), under the admin
    bar: its ☰ drawer the three captions, every row the exit, Kartoni
    current; "Izađi" back to Kartoni, the strip gone. No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", "Tvrtko Vlasnik")
    make_user("coach@test.local", "Amir Trener", is_trainer=True)
    make_user("ana@test.local", "Ana Kovač", plans=("grupni",))
    make_user("ivan@test.local", "Ivan Horvat", plans=("grupni", "online"))
    make_user("mb.trening@test.local", "Marko Babić")
    db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w, theme in ((390, "dark"), (360, "light")):
            where = f"[{w}px {theme}]"
            ctx, pg, errors = _login(browser, server, "coach@test.local", w, theme)
            for path in ("/kartoni", "/dvoranski/clanovi", "/programi"):
                go(pg, server + path)
                check(pg.evaluate(OVERFLOW) == 0, f"{where} {path} overflows by {pg.evaluate(OVERFLOW)}px")
            go(pg, server + "/kartoni")
            s = pg.evaluate(LISTED)
            check(s["rows"] == ["Ana Kovač", "Ivan Horvat", "Marko Babić"] and s["found"] is None and pg.is_visible("form.kao-search"),
                  f"{where} Kartoni: {s}")
            pg.fill("form.kao-search input", "kov")
            s = pg.evaluate(LISTED)
            check(s["rows"] == ["Ana Kovač"] and (s["found"] or "").startswith("1 od 3"), f"{where} 'kov': {s}")
            pg.tap(".kao-found a")
            s = pg.evaluate(LISTED)
            check(len(s["rows"]) == 3 and s["box"] == "", f"{where} prikaži sve: {s}")
            with pg.expect_navigation():
                pg.locator(".kao-row", has_text="Ana Kovač").locator("button").tap()
            pg.wait_for_load_state("networkidle")
            check(pg.url == f"{server}/karton" and pg.evaluate(SEEN_H1) == "Karton — Ana Kovač"
                  and pg.locator("div.kao-bar").count() == 1 and keys_of(ctx).get("as_scope") == "tab",
                  f"{where} Otvori karton led to {pg.url}: {pg.evaluate(SEEN_H1)!r}, {keys_of(ctx)}")
            check(pg.evaluate(OVERFLOW) == 0, f"{where} her karton overflows by {pg.evaluate(OVERFLOW)}px")
            pg.tap(".nav-burger")
            d = pg.evaluate(DRAWER)
            check(d["caps"] == ["Članovi", "Treninzi", "Sadržaj"] and d["current"] == ["Kartoni"]
                  and all(h.startswith("/kao/izlaz?kamo=/") for _, h in d["rows"]), f"{where} the admin bar's drawer: {d}")
            pg.tap(".nav-burger")
            with pg.expect_navigation():
                pg.tap(".kao-exit")
            pg.wait_for_load_state("networkidle")
            check(pg.url == server + "/kartoni" and not pg.locator("div.kao-bar").count() and keys_of(ctx) == {},
                  f"{where} Izađi led to {pg.url}")
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


def test_a_tabs_view_on_a_phone(server):
    """At 390px, touch (dark), a trainer who is not the owner: Kartoni,
    Ivan's "Otvori karton →" → his karton under the strip ("Karton — Ivan
    Horvat"), the admin bar's ☰ drawer (its three groups, every row the
    exit); a document uploaded under his limitations is his (and the view
    lasts); the drawer's Raspored (Treninzi's row) tapped → the trainer's
    own raspored, the strip gone, the view over. Then the admin's Dvoranski
    treninzi, Ivan's "Otvori treninge →" → Ivan's tab ("Dvoranski treninzi —
    Ivan Horvat"), a termin of his three days ahead with "Pripremi trening"
    and when it opens for him; tapped, its training (the chooser, before
    Ivan's window), "+ Stanica", a station filled (Goblet čučanj, 3 × 10)
    and started, his; "Izađi" back to the list. Nothing scrolls sideways at
    390 or 360px; no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("coach@test.local", "Amir Trener", is_trainer=True)
    make_user("trener@test.local", "Tvrtko Vlasnik")
    ivan = make_user("ivan@test.local", "Ivan Horvat", plans=("grupni",))
    make_user("ana@test.local", "Ana Kovač", plans=("grupni",))
    db.reset_gym_templates()
    goblet = db.create_exercise("Goblet čučanj")
    start = (datetime.now(config.TZ) + timedelta(days=3)).replace(hour=18, minute=0, second=0, microsecond=0)
    sid = db.add_oneoff_session("Grupni trening", start, 60, 8, None)
    db.book(ivan, sid)
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _login(browser, server, "coach@test.local", 390, "dark")

        def wide(where: str) -> None:
            for w, h in ((390, 844), (360, 780)):
                pg.set_viewport_size({"width": w, "height": h})
                check(pg.evaluate(OVERFLOW) == 0, f"{where} at {w}px overflows by {pg.evaluate(OVERFLOW)}px")
            pg.set_viewport_size({"width": 390, "height": 844})

        def pick(path: str, name: str) -> None:
            go(pg, server + path)
            with pg.expect_navigation():
                pg.locator(".kao-row", has_text=name).locator("button").tap()
            pg.wait_for_load_state("networkidle")

        pick("/kartoni", "Ivan Horvat")
        check(pg.url == server + "/karton" and pg.evaluate(SEEN_H1) == "Karton — Ivan Horvat"
              and pg.is_visible("div.kao-bar") and keys_of(ctx).get("as_scope") == "tab",
              f"Kartoni's row: {pg.url}, {pg.evaluate(SEEN_H1)!r}, {keys_of(ctx)}")
        wide("his karton")
        pg.tap(".nav-burger")
        drawer = pg.evaluate(DRAWER)
        check(drawer["caps"] == ["Članovi", "Treninzi", "Sadržaj"] and any(r[0] == "Gledaj kao član" for r in drawer["rows"])
              and all(h.startswith("/kao/izlaz?kamo=/") for _, h in drawer["rows"]), f"staff's drawer: {drawer}")
        pg.tap(".nav-burger")
        pg.locator("button.act[onclick=\"qmtToggleForm('lim-docs')\"]").tap()          # "Dodaj dokument"
        pg.set_input_files("#doc-file", files=[{"name": "nalaz.pdf", "mimeType": "application/pdf",
                                                 "buffer": b"%PDF-1.4\n%test\n"}])
        pg.fill("#doc-name", "Nalaz koljena")
        with pg.expect_navigation():
            pg.locator("#lim-docs form[action='/karton/ogranicenja/dokument'] button[type=submit]").tap()
        pg.wait_for_load_state("networkidle")
        docs = db.limitation_files(ivan)
        check([d.name for d in docs] == ["Nalaz koljena"] and pg.is_visible("div.kao-bar") and "ok=" in pg.url,
              f"the document: {[d.name for d in docs]}, {pg.url}")
        wide("his karton, his document")
        pg.tap(".nav-burger")
        with pg.expect_navigation():
            pg.locator("#treninziMenu a", has_text="Raspored").tap()
        pg.wait_for_load_state("networkidle")
        check(pg.url == server + "/raspored" and not pg.locator("div.kao-bar").count() and keys_of(ctx) == {},
              f"the drawer's Raspored: {pg.url}, {keys_of(ctx)}")
        wide("the trainer's own raspored")

        pick("/dvoranski/clanovi", "Ivan Horvat")
        check(pg.url == server + "/dvoranski" and pg.evaluate(SEEN_H1) == "Dvoranski treninzi — Ivan Horvat"
              and pg.is_visible("div.kao-bar"), f"the list's row: {pg.url}, {pg.evaluate(SEEN_H1)!r}")
        card = pg.locator(f"#dv-s-{sid}")
        opens = (start - timedelta(hours=config.CANCEL_CUTOFF_HOURS)).strftime("%-d.%-m. u %H:%M")
        check(card.is_visible() and card.locator(".dv-go").inner_text() == "Pripremi trening"
              and opens in card.locator(".dv-state").inner_text(), f"the termin days ahead: {card.inner_text()!r}")
        wide("his tab")
        with pg.expect_navigation():
            card.locator(".dv-go").tap()
        pg.wait_for_load_state("networkidle")
        made = [t for t in db.gym_trainings(ivan) if t.session_id == sid]
        check(len(made) == 1 and pg.url == f"{server}/dvoranski/trening/{made[0].id}" and pg.is_visible(".gt-chooser"),
              f"Pripremi trening led to {pg.url}")
        wide("his training, prepared")
        if made:
            with pg.expect_navigation():
                pg.locator(".gt-chooser form:has(input[value=stanica]) button").tap()
            pg.wait_for_load_state("networkidle")
            [b] = db.gym_training(made[0].id, ivan).blocks
            box = pg.locator(f"#gt-s{b.id}-ex-q")
            box.tap()
            box.fill("gob")
            pg.locator(f"#gt-s{b.id}-ex-list [role=option]", has_text="Goblet čučanj").first.tap()
            pg.fill(f"#gt-s{b.id}-sets", "3")
            pg.fill(f"#gt-s{b.id}-reps", "10")
            with pg.expect_navigation():
                pg.locator("form.gt-sform button.btn").first.tap()
            pg.wait_for_load_state("networkidle")
            it = db.gym_training(made[0].id, ivan).blocks[0].items[0]
            check((it.exercise_id, it.sets, it.reps) == (goblet, 3, 10) and pg.locator("#gt-log tbody tr").count() == 3,
                  f"the station: {(it.exercise_id, it.sets, it.reps)}, {pg.url}")
            wide("a station filled")
        with pg.expect_navigation():
            pg.tap(".kao-exit")
        pg.wait_for_load_state("networkidle")
        check(pg.url == server + "/dvoranski/clanovi" and not pg.locator("div.kao-bar").count() and keys_of(ctx) == {}
              and pg.is_visible(".kao-list"), f"Izađi led to {pg.url}")
        problems += errors
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# a list's chips and rows as the script left them (build 4 of the admin view):
# the chosen chip, each chip's height, whether every chip sits inside the
# chips' row, the rows shown (each name as a sighted reader has it), the count
# line, the two empty sentences, the box, the address, whether the page is
# still the one loaded (window.__stay), the page's overflow
CHIPS = r"""() => {
  const bar = document.querySelector('.kao-groups'), br = bar.getBoundingClientRect(), chips = [...bar.querySelectorAll('a')];
  const seen = el => { const s = el.cloneNode(true); s.querySelectorAll('.st-sr').forEach(x => x.remove()); return s.textContent; };
  const line = sel => { const p = document.querySelector(sel); return p.hidden ? null : p.textContent.trim(); };
  return {current: chips.filter(a => a.getAttribute('aria-current') === 'true').map(a => a.dataset.grupa),
          heights: chips.map(a => a.getBoundingClientRect().height),
          inside: chips.every(a => { const r = a.getBoundingClientRect(); return r.left >= br.left - .5 && r.right <= br.right + .5; }),
          rows: [...document.querySelectorAll('.kao-row')].filter(r => !r.hidden).map(r => seen(r.querySelector('strong'))),
          found: line('.kao-found'), none: line('.kao-none'), nogroup: line('.kao-nogroup'),
          box: document.querySelector('form.kao-search input').value, address: location.pathname + location.search,
          stayed: window.__stay === 1,
          overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}"""


def test_the_chips_on_a_phone(server):
    """At 390px, touch (dark), a trainer who is not the owner, on each of
    the three lists (Gledaj kao član, Kartoni, the admin's Dvoranski
    treninzi), a long name among the members: the chips under the search,
    the page's own chosen (Svi; Dvorana), each 32px tall at least on the
    coarse pointer, all inside the column, nothing scrolling sideways at 390
    or 360px. A tap on each chip filters the rows in place (no load),
    chooses it, and the address follows (?grupa= when it is not the page's
    own); a chip and a typed word narrow together, the address holding both;
    nothing left with a word typed: the search's sentence; "prikaži sve"
    empties the box, chooses Svi, every row back. A reload keeps the chip.
    From Kartoni and the Dvoranski treninzi list a row's entry into the
    member's tab, then Back: the list in its chip, the view over; entered
    again, "Izađi": the list's own address, its own chip; from /kao (the
    whole app) "Izađi". Then, every online plan lapsed, Online with nobody
    says "Nema članova u ovoj skupini.". No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    groups = grouped()
    long = "Zvonimir Aleksandar Maksimilijan Horvat-Kovačević-Babić"
    make_user("zvonimir.aleksandar.maksimilijan.horvat.kovacevic.babic@test.local", long, plans=("grupni",))
    groups[long] = ("dvorana",)
    members = in_groups(groups)
    every = len(members["svi"])
    lands = {"/kao": "/karton", "/kartoni": "/karton", "/dvoranski/clanovi": "/dvoranski"}
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    def address(path: str, start: str, key: str, typed: str = "") -> str:
        query = "&".join(([f"grupa={key}"] if key != start else []) + ([f"q={typed}"] if typed else []))
        return path + ("?" + query if query else "")

    def found(n: int) -> str:
        return f"{n} od {every} · prikaži sve"

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _login(browser, server, "coach@test.local", 390, "dark")

        def state() -> dict:
            return pg.evaluate(CHIPS)

        def tap(key: str) -> None:
            pg.locator(f'.kao-groups a[data-grupa="{key}"]').tap()

        def wide(where: str) -> None:
            for w, h in ((390, 844), (360, 780)):
                pg.set_viewport_size({"width": w, "height": h})
                s = state()
                check(s["overflow"] == 0 and s["inside"], f"{where} at {w}px: overflow {s['overflow']}, chips inside: {s['inside']}")
            pg.set_viewport_size({"width": 390, "height": 844})

        def enter_sara(path: str) -> None:
            with pg.expect_navigation():
                pg.locator(".kao-row", has_text="Sara Jurić").locator("button").tap()
            pg.wait_for_load_state("networkidle")
            check(pg.url == server + lands[path] and pg.locator("div.kao-bar").count() == 1, f"{path}: Sara's entry led to {pg.url}")

        for path, start in LIST_PATHS:
            go(pg, server + path)
            pg.evaluate("() => { window.__stay = 1; }")
            s = state()
            check(s["current"] == [start] and s["rows"] == members[start] and s["box"] == ""
                  and s["found"] == (None if start == "svi" else found(len(members[start]))), f"{path} as it opens: {s}")
            check(len(s["heights"]) == len(CHIP_WORDS) and all(h >= 32 for h in s["heights"]), f"{path} the chips: {s['heights']}")
            wide(f"{path} as it opens")
            for key, _ in CHIP_WORDS:                                   # each chip, in place
                tap(key)
                s = state()
                check(s["current"] == [key] and s["rows"] == members[key] and s["stayed"]
                      and s["address"] == address(path, start, key)
                      and s["found"] == (None if key == "svi" else found(len(members[key])))
                      and s["none"] is None and s["nogroup"] is None, f"{path} tapped {key}: {s}")
            wide(f"{path} after the taps")
            tap("dvorana")                                              # a chip and a word together
            pg.locator("form.kao-search input").fill("horvat")
            pg.wait_for_timeout(400)                                     # the address, a little after the last key
            s = state()
            want = [n for n in members["dvorana"] if "horvat" in n.lower()]
            check(s["rows"] == want and s["found"] == found(len(want)) and s["stayed"]
                  and s["address"] == address(path, start, "dvorana", "horvat"), f"{path} Dvorana and 'horvat': {s}")
            tap("bez")                                                   # nothing left, a word typed
            s = state()
            check(s["rows"] == [] and s["none"] == "Nijedan član ne odgovara traženju „horvat”." and s["nogroup"] is None
                  and s["address"] == address(path, start, "bez", "horvat"), f"{path} Bez članarine and 'horvat': {s}")
            pg.tap(".kao-found a")                                       # prikaži sve
            s = state()
            check(s["box"] == "" and s["current"] == ["svi"] and s["rows"] == members["svi"] and s["found"] is None
                  and s["none"] is None and s["stayed"] and s["address"] == address(path, start, "svi"), f"{path} prikaži sve: {s}")
            tap("bez")                                                   # a reload keeps the chip
            pg.reload(); pg.wait_for_load_state("networkidle")
            s = state()
            check(s["current"] == ["bez"] and s["rows"] == members["bez"] and not s["stayed"]
                  and s["address"] == address(path, start, "bez"), f"{path} reloaded: {s}")
            enter_sara(path)
            if path != "/kao":                                           # a tab's view: Back re-asks the list
                pg.go_back(); pg.wait_for_load_state("networkidle")
                s = state()
                check(s["address"].startswith(address(path, start, "bez")) and s["current"] == ["bez"]
                      and s["rows"] == members["bez"] and not pg.locator("div.kao-bar").count() and keys_of(ctx) == {},
                      f"{path} Back from Sara's tab: {s}, {keys_of(ctx)}")
                enter_sara(path)
            with pg.expect_navigation():
                pg.tap(".kao-exit")
            pg.wait_for_load_state("networkidle")
            s = state()
            check(pg.url == server + path and s["current"] == [start] and s["rows"] == members[start] and keys_of(ctx) == {},
                  f"{path} Izađi led to {pg.url}: {s}")
        with db.engine.begin() as conn:                                  # nobody in a group
            conn.execute(sa_text("UPDATE memberships SET next_payment = next_payment - 60 WHERE plan = 'online'"))
        online_now: list[str] = []
        for path, start in LIST_PATHS:
            go(pg, server + path)
            tap("online")
            s = state()
            check(s["rows"] == online_now and s["nogroup"] == "Nema članova u ovoj skupini." and s["none"] is None
                  and s["found"] == found(len(online_now)), f"{path} Online with nobody: {s}")
        problems += errors
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


# ---------- where a redirect may lead (the exit's `kamo`, a login's `next`) ----------

def test_a_redirect_leads_to_a_local_path_alone():
    """app._safe_next: a path of this app, with its query and fragment, or
    "/". Never another site: "//host" and a scheme, and (27.11.2026, when
    the exit of a member's view got a GET with `kamo`) nothing with a
    backslash, which browsers read as a slash ("/\\host" is "//host"), nor
    with a control character. GET /kao/izlaz?kamo= follows the same rule."""
    from qmt.web.app import _safe_next

    for good in ("/karton", "/dvoranski/trening/7?blok=3#glavno", "/kao/izlaz?kamo=/raspored"):
        assert _safe_next(good) == good
    for bad in ("//evil.example", "/\\evil.example", "/\\/evil.example", "https://evil.example", "karton",
                "/a\tb", "/a\nb", "/a\x7fb", "", None):
        assert _safe_next(bad) == "/", repr(bad)
    make_user("trener@test.local", "Tvrtko Vlasnik")
    c = client_for("trener@test.local")
    for kamo, to in (("/raspored", "/raspored"), ("/\\evil.example", "/"), ("//evil.example", "/")):
        r = c.get("/kao/izlaz", params={"kamo": kamo}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == to, kamo
