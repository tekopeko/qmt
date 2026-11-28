"""The topbar's tabs (26.10.2026; the owner: "lets somehow group the tabs
which are related for me and in another group the tabs which are there and
different because I am an admin") and, since 28.11.2026, the two views of a
staff account (build 2 of roadmap/2026-11-28-admin-view-plan.md; the owner:
"What do you think of an option where we have a button which switches from
his admin and his member view? Then he doesnt need to have 2 different
accounts?").

A client's row: Početna · Raspored · Karton · Dvoranski treninzi (while a
plan that books termini runs, since 27.11.2026: build 2 of the dvoranski
treninzi; the owner: "I would show the tab only to members with a gym
plan. Similarly how a online training tab shows only to members with an
online plan.") · Online treninzi (while an online plan runs) · Moja
članarina · Prehrana; the account menu Profil, the theme and Odjava; in the
☰ drawer (≤900px, a bar of seven ≤959px) the one plain list.

A staff account (the trainer, the owner by rule: app._is_staff) has a view,
admin or member, kept in its session (`view`): after a login the admin
view, landing on the front page as every login does (a `next` honoured);
the avatar's menu switches it, after Profil ("Pogled člana" in the admin
view, "Admin pogled" in the member view: POST /pogled, landing on the front
page; a member 403); and the bar follows the page: every GET route of the
app is an admin page, a member page or a shared one (app._page_kind, held
here route by route: a route nobody classified fails), a page of either
side asked for takes the view along, a shared page keeps it, and a write, a
fetch, a prefetch, an asset, and anything while staff act as a member,
never change it. The admin view's bar: three tabs, each a menu in the
account menu's component, Članovi ▾ (Kartoni, Trenutne članarine, Gledaj
kao član, the owner's Korisnici), Treninzi ▾ (Raspored, Termini, Dvoranski
treninzi, Online treninzi, Vježbe), Sadržaj ▾ (Tekstovi, Početna, Upitnik,
Vodič), and the owner's Statistika, a plain tab; a tab .on while one of its
pages is open, that item aria-current; Admin ▾ and the captions "Kao član"
/ "Admin" gone. In the drawer three captions, ČLANOVI, TRENINZI, SADRŽAJ,
their items as rows, a hairline before each next group, Statistika last.
The member view's bar is a member's with every plan: seven tabs, no admin
tab.

The route half reads the HTML. The browser half starts the app in a thread,
as tests/test_copy.py does: the owner's admin bar at 1280 and 901px (the
pill one row, each menu opened under its tab, one at a time, closed by
Escape, a click outside and the account menu, the keyboard; one item
followed, its tab lit), its drawer at 390px (its groups and hairlines, an
item followed), the switch and back; a client at 390 and 1280px; the bars'
room at 901–1280px in both themes (the admin bar one row at every width
from 901px; a bar of seven, a client's and the member view's, the drawer up
to 959px and one row from 960px; a bar of six the drawer at 900px). Then
edit mode (26.10.2026, the owner: "when I go to a tab as an admin, please
dont make it editable but default"): no page opens in it by itself, so
staff land on /upitnik, ?uredi=1 (the old way in) or not, in normal mode
with the ✎ pill there to press; leaving a page ends it (a tab, a menu's
item, a reload by hand), and only the editor's own forms, which reload the
landing, bring it back in edit mode.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from datetime import date, datetime, timedelta

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from qmt import auth, config, db
from qmt.models import Base, Booking, User
from qmt.web import app as web
from qmt.web.app import app

PORT = 8113                      # tests/test_copy.py's server is 8111, test_raspored_ui's and test_upitnik_ui's 8112


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # nothing here stores media, but the server thread shares this process's
    # config: never a developer's real R2 bucket (as tests/test_copy.py)
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "")
    yield


def make_user(email: str, is_trainer: bool = False, plans: tuple[str, ...] = ()) -> int:
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


def view_of(c: TestClient) -> str | None:
    """The client's view, as its session keeps it (Starlette's signed cookie)."""
    from itsdangerous import TimestampSigner

    raw = c.cookies.get("session")
    if not raw:
        return None
    return json.loads(base64.b64decode(TimestampSigner(str(config.SECRET_KEY)).unsign(raw.encode()))).get("view")


# ---------- the markup ----------

def nav(page: str) -> str:
    """The nav's markup, from its tag to its end (a bar of seven tab links
    is `nav nav-7`, 27.11.2026)."""
    start = re.search(r'<nav class="nav(?: nav-7)?" id="mainNav">', page).start()
    return page[start:page.index("</nav>", start)]


def seven(page: str) -> bool:
    """Whether the page's bar says it holds seven tab links: its nav and its ☰."""
    return ('<nav class="nav nav-7" id="mainNav">' in page
            and '<button type="button" class="navbtn nav-burger nav-7"' in page)


def tabs(page: str) -> list[tuple[str, str, bool]]:
    """The tabs right in the nav, in order: (href, label, .on). The admin
    bar has none: its tabs are menus and Statistika (stat_tab)."""
    return [(href, label, on == "on")
            for href, on, label in re.findall(r'^\s*<a href="([^"]+)" class="(on|)">([^<]+)</a>', nav(page), re.M)]


MENU_RE = re.compile(r'<p class="nav-cap">([^<]+)</p>\s*<button type="button" id="(\w+)Btn" class="navbtn menu-btn( on)?"'
                     r'[^>]*>\1 <span class="caret" aria-hidden="true">▾</span></button>\s*'
                     r'<div class="menu admin-menu" id="\2Menu" role="menu" aria-labelledby="\2Btn">(.*?)</div>', re.S)


def menus(page: str) -> dict[str, tuple[bool, list[tuple[str, str, bool]]]]:
    """The admin bar's menus, in order: {its tab's label, the drawer's
    caption too: (the tab .on, [(href, label, aria-current="page")])}; {}
    for a member's bar."""
    out = {}
    for label, _, on, body in MENU_RE.findall(nav(page)):
        out[label] = (bool(on), [(href, name, bool(current)) for href, current, name in re.findall(
            r'<a href="([^"]+)" role="menuitem"( aria-current="page")?>\s*<svg.*?</svg><span>([^<]+)</span>', body, re.S)])
    return out


def items_of(page: str) -> dict[str, list[tuple[str, str]]]:
    """Each admin menu's items, (href, label), in order."""
    return {label: [(href, name) for href, name, _ in items] for label, (_, items) in menus(page).items()}


def stat_tab(page: str) -> tuple[str, bool] | None:
    """The owner's Statistika, the admin bar's plain tab: (href, .on), or None."""
    m = re.search(r'<div class="menu-wrap nav-admin"><a href="([^"]+)" class="navbtn( on)?">Statistika</a></div>', nav(page))
    return (m.group(1), bool(m.group(2))) if m else None


def lit(page: str) -> tuple[list[str], list[str]]:
    """What the bar marks: the tabs .on (a member row's, an admin menu's,
    Statistika) and the items aria-current."""
    m = menus(page)
    on = [label for _, label, o in tabs(page) if o] + [label for label, (o, _) in m.items() if o]
    if (stat_tab(page) or ("", False))[1]:
        on.append("Statistika")
    return on, [name for _, (_, items) in m.items() for _, name, current in items if current]


def captions(page: str) -> list[str]:
    """The drawer's captions, in order."""
    return re.findall(r'<p class="nav-cap">([^<]+)</p>', nav(page))


def account_menu(page: str) -> list[str]:
    """The account menu's rows, in order (the theme row by its label)."""
    menu = page[page.index('id="userMenu"'):page.index("</header>")]
    return re.findall(r'<span(?: id="themeLabel")?>([^<]+)</span>', menu)


# Dvoranski treninzi after Karton since 27.11.2026 (staff always; a member while a gym plan runs)
MEMBER_ROW = [("/", "Početna"), ("/raspored", "Raspored"), ("/karton", "Karton"), ("/dvoranski", "Dvoranski treninzi"),
              ("/treninzi", "Online treninzi"), ("/moja-clanarina", "Moja članarina"), ("/prehrana", "Prehrana")]
# the admin view's three menus (28.11.2026), a trainer's; the owner's Korisnici too, and his Statistika tab
TRAINER_MENUS = {
    "Članovi": [("/kartoni", "Kartoni"), ("/clanarine", "Trenutne članarine"), ("/kao", "Gledaj kao član")],
    "Treninzi": [("/raspored", "Raspored"), ("/admin", "Termini"), ("/dvoranski/clanovi", "Dvoranski treninzi"),
                 ("/programi", "Online treninzi"), ("/treninzi/vjezbe", "Vježbe")],
    "Sadržaj": [("/tekstovi", "Tekstovi"), ("/", "Početna"), ("/upitnik", "Upitnik"), ("/vodic", "Vodič")]}
OWNER_MENUS = {**TRAINER_MENUS, "Članovi": TRAINER_MENUS["Članovi"] + [("/korisnici", "Korisnici")]}
CAPTIONS = ["Članovi", "Treninzi", "Sadržaj"]
ACCOUNT = ["Profil", "Tamna tema", "Odjava"]
ADMIN_ACCOUNT = ["Profil", "Pogled člana", "Tamna tema", "Odjava"]           # the switch after Profil
MEMBER_VIEW_ACCOUNT = ["Profil", "Admin pogled", "Tamna tema", "Odjava"]
# what a navigation sends (app._page_asked: a browser's own)
NAVIGATE = {"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}


def test_a_clients_row_is_the_members_tabs_and_nothing_of_admin():
    """A client's row: a gym plan and an online plan, seven tab links (the
    bar says so, its nav and its ☰ .nav-7: the drawer up to 959px, below);
    no online plan, no Online treninzi; since 27.11.2026 no plan that books
    termini, no Dvoranski treninzi (an online plan alone, none at all). His
    karton lights his Karton tab. No admin menu, caption or switch: a
    member's account has no view (none is kept, a page asked for sets
    none)."""
    make_user("ivan@test.local", plans=("grupni", "online"))
    make_user("ana@test.local", plans=("grupni",))                     # no online plan: no Online treninzi, as before
    make_user("mia@test.local", plans=("online",))                     # online alone: no Dvoranski treninzi
    make_user("sara@test.local")                                       # no plan: neither
    ivan = client_for("ivan@test.local")
    page = ivan.get("/raspored").text
    assert tabs(page) == [("/", "Početna", False), ("/raspored", "Raspored", True), ("/karton", "Karton", False),
                          ("/dvoranski", "Dvoranski treninzi", False), ("/treninzi", "Online treninzi", False),
                          ("/moja-clanarina", "Moja članarina", False), ("/prehrana", "Prehrana", False)]
    assert seven(page)
    assert menus(page) == {} and stat_tab(page) is None and captions(page) == []   # one plain list in the drawer too
    for mark in ('class="menu admin-menu"', 'href="/admin"', 'href="/clanarine"', 'href="/korisnici"', 'href="/statistika"',
                 'href="/kartoni"', 'href="/programi"', "Admin", "menu-btn"):
        assert mark not in nav(page), mark
    assert account_menu(page) == ACCOUNT and 'action="/pogled"' not in page   # no Moja članarina item: the tab is the way
    for email, row in (("ana@test.local", ["Početna", "Raspored", "Karton", "Dvoranski treninzi", "Moja članarina",
                                           "Prehrana"]),
                       ("mia@test.local", ["Početna", "Raspored", "Karton", "Online treninzi", "Moja članarina",
                                           "Prehrana"]),
                       ("sara@test.local", ["Početna", "Raspored", "Karton", "Moja članarina", "Prehrana"])):
        theirs = client_for(email).get("/raspored").text
        assert [label for _, label, _ in tabs(theirs)] == row, email
        assert not seven(theirs) and '<nav class="nav" id="mainNav">' in theirs, email   # six or fewer: today's 900px
        assert '<button type="button" class="navbtn nav-burger" onclick=' in theirs, email
    karton = ivan.get("/karton").text                                    # his karton lights his tab, as ever
    assert [label for _, label, on in tabs(karton) if on] == ["Karton"]
    assert view_of(ivan) is None


def test_a_staff_login_is_the_admin_view_and_lands_on_the_front_page():
    """After a login a staff account, the trainer's and the owner's, is in
    the admin view and lands on /, as every login does (the owner, asked
    whether the login should land there too: "yes"); a `next` it was sent
    to log in for is honoured, and a member page there takes the view
    along. A new login is the admin view again, whatever the view before. A
    member's login keeps no view."""
    make_user("trener@test.local", is_trainer=True)                     # the owner, a trainer too
    make_user("coach@test.local", is_trainer=True)                      # a trainer who is not the owner
    make_user("ivan@test.local", plans=("grupni",))
    for email in ("coach@test.local", "trener@test.local"):
        c = TestClient(app)
        r = c.post("/login", data={"email": email, "password": "lozinka123"}, follow_redirects=False)
        assert (r.status_code, r.headers["location"], view_of(c)) == (303, "/", "admin"), email
        page = c.get("/").text
        assert set(menus(page)) == set(CAPTIONS) and tabs(page) == [] and view_of(c) == "admin", email
        r = c.post("/login", data={"email": email, "password": "lozinka123", "next": "/karton"}, follow_redirects=False)
        assert (r.headers["location"], view_of(c)) == ("/karton", "admin"), email
        page = c.get("/karton").text
        assert view_of(c) == "member" and menus(page) == {} and [l for _, l, on in tabs(page) if on] == ["Karton"], email
        c.post("/login", data={"email": email, "password": "lozinka123"})
        assert view_of(c) == "admin", email                              # a new login: the admin view again
    m = TestClient(app)
    r = m.post("/login", data={"email": "ivan@test.local", "password": "lozinka123"}, follow_redirects=False)
    assert r.headers["location"] == "/" and view_of(m) is None


def test_the_admin_bar_the_member_views_bar_and_the_switch_between_them():
    """The admin view's bar, the trainer's and the owner's: no tab of a
    member's row; three menus, each its tab (its caret part of its label,
    read as the word) over its items in order, Korisnici the owner's; the
    owner's Statistika a plain tab after them; the drawer's captions
    Članovi, Treninzi, Sadržaj; not a bar of seven; the account menu with
    the switch after Profil, "Pogled člana", a form posting view=member to
    /pogled. The switch lands on / in the member view: a member's bar with
    every plan, seven tabs (.nav-7), no menu, no caption, no Statistika, the
    switch saying "Admin pogled"; and back. A view that is none changes
    nothing. A member posting it is refused (403), a guest goes to log in."""
    make_user("trener@test.local", is_trainer=True)
    make_user("coach@test.local", is_trainer=True)
    make_user("ivan@test.local", plans=("grupni",))
    for email, want, owner in (("coach@test.local", TRAINER_MENUS, False), ("trener@test.local", OWNER_MENUS, True)):
        c = client_for(email)
        page = c.get("/").text
        assert items_of(page) == want and tabs(page) == [] and not seven(page), email
        assert '<nav class="nav" id="mainNav">' in page and '<button type="button" class="navbtn nav-burger" onclick=' in page
        assert stat_tab(page) == (("/statistika", False) if owner else None), email
        assert captions(page) == CAPTIONS and account_menu(page) == ADMIN_ACCOUNT, email
        for key in ("clanovi", "treninzi", "sadrzaj"):
            assert f'aria-controls="{key}Menu">' in nav(page) and f'role="menu" aria-labelledby="{key}Btn"' in nav(page)
        for gone in ('id="adminBtn"', 'id="adminMenu"', "Admin ▾", ">Admin <", "Kao član"):
            assert gone not in nav(page), (email, gone)
        menu = page[page.index('id="userMenu"'):page.index("</header>")]
        assert ('<form method="post" action="/pogled">\n        <input type="hidden" name="view" value="member">\n'
                '        <button type="submit" role="menuitem">') in menu
        assert menu.index("<span>Profil</span>") < menu.index("<span>Pogled člana</span>") < menu.index('id="themeLabel"')
        r = c.post("/pogled", data={"view": "member"}, follow_redirects=False)
        assert (r.status_code, r.headers["location"], view_of(c)) == (303, "/", "member"), email
        page = c.get("/").text
        assert [(h, l) for h, l, _ in tabs(page)] == MEMBER_ROW and seven(page), email
        assert menus(page) == {} and captions(page) == [] and stat_tab(page) is None, email
        assert account_menu(page) == MEMBER_VIEW_ACCOUNT and 'name="view" value="admin"' in page, email
        assert [l for _, l, on in tabs(page) if on] == ["Početna"], email
        r = c.post("/pogled", data={"view": "admin"}, follow_redirects=False)
        assert (r.headers["location"], view_of(c)) == ("/", "admin") and items_of(c.get("/").text) == want, email
        for junk in ("", "x", "clan", "ADMIN"):
            c.post("/pogled", data={"view": junk})
            assert view_of(c) == "admin", (email, junk)
    member = client_for("ivan@test.local")
    assert member.post("/pogled", data={"view": "admin"}).status_code == 403 and view_of(member) is None
    r = TestClient(app).post("/pogled", data={"view": "admin"}, follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/login")


def test_an_owner_who_does_not_train_is_staff_too():
    """Staff is the trainer or the owner (the routes' _require_trainer): an
    owner without is_trainer gets the same views: the admin bar with every
    item, Korisnici and Statistika his, and in the member view a member's
    bar with every plan (since 26.11.2026 Online treninzi whatever his
    plans, the owner being staff by rule; Dvoranski treninzi too, since
    27.11.2026)."""
    make_user("trener@test.local", plans=("grupni",))                  # the owner, not a trainer, no online plan
    c = client_for("trener@test.local")
    page = c.get("/raspored").text
    assert items_of(page) == OWNER_MENUS and stat_tab(page) == ("/statistika", False)
    assert account_menu(page) == ADMIN_ACCOUNT
    c.post("/pogled", data={"view": "member"})
    page = c.get("/raspored").text
    assert [label for _, label, _ in tabs(page)] == ["Početna", "Raspored", "Karton", "Dvoranski treninzi",
                                                     "Online treninzi", "Moja članarina", "Prehrana"]
    assert account_menu(page) == MEMBER_VIEW_ACCOUNT


def test_the_owner_is_staff_by_rule_whatever_his_trainer_flag():
    """The owner is staff by rule (26.11.2026, the owner: "can we add
    everything the trainer sees the admin (me) sees"; app._is_staff, the
    templates' can_edit_copy): with his trainer flag OFF he logs in as a
    trainer does (no profile asked first) and is in the admin view, and gets
    the trainer's /raspored (the rosters' links, no gate line, no "Tjedan |
    Mjesec" switch), the admin's table of programmes (/programi) and, in the
    member view, Online treninzi and staff's /treninzi list, a programme's
    and a day's page with "Uredi …", the player and its finish screen with
    staff's bar (not the one-task pill), his own /karton as staff's, every
    admin item, no install banner and no phone reminder; he is listed on
    neither /clanarine nor /kao, and nobody enters his account (POST
    /kao/<his id>). A member, beside him, keeps a member's page."""
    from urllib.parse import unquote

    owner = db.create_user("trener@test.local", "trener", auth.hash_password("lozinka123")).id
    db.mark_email_verified("trener@test.local")                         # no profile yet, no trainer flag
    r = TestClient(app).post("/login", data={"email": "trener@test.local", "password": "lozinka123"},
                             follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/")         # not /profil?dopuni=1: staff are exempt
    db.update_profile(owner, "Trener", "Test", date(1990, 1, 1), "")    # no phone: no reminder for staff either
    make_user("coach@test.local", is_trainer=True)
    ivan = make_user("ivan@test.local", plans=("grupni",))
    assert not db.get_user(owner).is_trainer
    starts = datetime.now(config.TZ).replace(second=0, microsecond=0) + timedelta(days=1)
    sid = db.add_oneoff_session("Grupni trening", starts, 60, 8, None)
    c, ci = client_for("trener@test.local"), client_for("ivan@test.local")

    week = f"/raspored?week={starts.date().isoformat()}"
    raspored, theirs = c.get(week).text, ci.get(week).text
    assert f'action="/admin/session/{sid}"' in raspored and f'action="/admin/session/{sid}"' not in theirs
    assert 'class="view-switch"' not in raspored and 'class="view-switch"' in theirs
    assert 'class="hint gate-line"' not in raspored
    assert items_of(raspored) == OWNER_MENUS and ("/programi", "Online treninzi") in items_of(raspored)["Treninzi"]
    assert 'id="a2hs"' not in raspored and 'id="phoneCard"' not in raspored and 'id="a2hs"' in theirs
    assert "Programi po razinama" in c.get("/programi").text            # the admin's table
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    db.add_day_item(did, db.create_exercise("Plank"), "trening")
    lista = c.get("/treninzi").text                                     # the member's list, by razina
    assert "Svi online programi, po razini." in lista and "Programi po razinama" not in lista
    assert ("/treninzi", "Online treninzi") in [(href, label) for href, label, _ in tabs(lista)]
    assert f'href="/treninzi/{pid}/uredi"' in c.get(f"/treninzi/{pid}").text
    assert f'href="/treninzi/{pid}/dan/{did}/uredi"' in c.get(f"/treninzi/{pid}/dan/{did}").text
    r = c.post(f"/treninzi/{pid}/dan/{did}/kreni", follow_redirects=False)
    assert r.headers["location"] == f"/treninzi/{pid}/dan/{did}/vjezba/1"
    for page in (c.get(r.headers["location"]).text, c.get(f"/treninzi/{pid}/dan/{did}/kraj").text):
        assert '<header class="topbar">' in page and 'class="avatar' in page    # staff's bar, not the solo pill
    assert 'data-copy="karton.staff.own_lead"' in c.get("/karton").text  # his own karton, as staff's
    clanarine, kao = c.get("/clanarine").text, c.get("/kao").text
    assert f'action="/clanarine/{owner}/' not in clanarine and f'action="/clanarine/{ivan}/uplata"' in clanarine
    assert f'action="/kao/{owner}"' not in kao and f'action="/kao/{ivan}"' in kao
    r = client_for("coach@test.local").post(f"/kao/{owner}", follow_redirects=False)
    assert unquote(r.headers["location"]) == "/kao?error=U račun trenera ili vlasnika se ne ulazi."


# ---------- which page is which (28.11.2026) ----------

# every GET route of the app, as the bar reads its page (app._page_kind):
# "admin", staff's side; "member", a member's tabs; "shared", both views'
KINDS = {
    "/": "shared", "/raspored": "shared", "/prehrana": "shared", "/nutricionizam": "shared", "/profil": "shared",
    "/login": "shared", "/signup": "shared", "/forgot": "shared", "/reset": "shared", "/auth/verify": "shared",
    "/slika/{name}": "shared", "/media/{name}": "shared", "/sw.js": "shared", "/healthz": "shared",
    "/moja-clanarina": "member", "/cjenik": "member",
    "/karton": "member", "/karton/clan": "member", "/karton/termin/{session_id}/trening": "member",
    "/karton/trening/{training_id}": "member", "/karton/trening/{training_id}/osvrt": "member",
    "/dvoranski": "member", "/dvoranski/termin/{session_id}": "member", "/dvoranski/trening/{training_id}": "member",
    "/dvoranski/trening/{training_id}/osvrt": "member",
    "/treninzi": "member", "/treninzi/{program_id}": "member", "/treninzi/{program_id}/dan/{day_id}": "member",
    "/treninzi/{program_id}/dan/{day_id}/vjezba/{k}": "member", "/treninzi/{program_id}/dan/{day_id}/kraj": "member",
    "/kartoni": "admin", "/karton/{user_id}": "admin", "/clanarine": "admin", "/kao": "admin", "/kao/zapisi": "admin",
    "/kao/izlaz": "admin", "/korisnici": "admin", "/statistika": "admin", "/tekstovi": "admin", "/upitnik": "admin",
    "/vodic": "admin", "/admin": "admin", "/admin/templates/{template_id}": "admin",
    "/admin/session/{session_id}": "admin", "/dvoranski/clanovi": "admin", "/dvoranski/predlosci": "admin",
    "/dvoranski/predlosci/{template_id}": "admin", "/programi": "admin", "/treninzi/vjezbe": "admin",
    "/treninzi/vjezbe/nova": "admin", "/treninzi/vjezbe/{exercise_id}": "admin",
    "/treninzi/{program_id}/uredi": "admin", "/treninzi/{program_id}/dan/{day_id}/uredi": "admin",
}


def test_every_get_route_is_one_kind_of_page():
    """The table of decision A3, route by route: every GET route of the
    app is in KINDS (a route nobody classified fails here, and one gone
    leaves the table), and app._page_kind names each as KINDS does, its
    parameters filled in, with a trailing slash too; a path the app has no
    route for has no kind."""
    gets = {r.path for r in app.routes if isinstance(r, APIRoute) and "GET" in r.methods}
    assert gets - set(KINDS) == set(), f"GET routes nobody classified: {gets - set(KINDS)}"
    assert set(KINDS) - gets == set(), f"classified, but no such GET route: {set(KINDS) - gets}"
    for path, kind in KINDS.items():
        sample = re.sub(r"\{\w+\}", "7", path)
        assert web._page_kind(sample) == kind, path
        assert web._page_kind(sample + "/") == kind, path
    for path in ("/nepostoji", "/kartoni/7", "/programi/7", "/kartonx"):
        assert web._page_kind(path) is None, path


def test_a_page_takes_the_view_along_and_a_shared_page_keeps_it():
    """The bar follows the page: from the login's admin view, a shared page
    keeps the view it was opened in, a member page takes it to the member
    view and an admin page back, each drawn under its view's bar."""
    make_user("trener@test.local", is_trainer=True)
    ivan = make_user("ivan@test.local", plans=("grupni",))
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    c = client_for("trener@test.local")
    for path, view in (("/", "admin"), ("/prehrana", "admin"), ("/profil", "admin"), ("/raspored", "admin"),
                       ("/karton", "member"), ("/", "member"), ("/raspored", "member"), ("/profil", "member"),
                       ("/kartoni", "admin"), ("/prehrana", "admin"), ("/dvoranski", "member"), ("/kao", "admin"),
                       ("/treninzi", "member"), (f"/treninzi/{pid}/uredi", "admin"), (f"/treninzi/{pid}", "member"),
                       (f"/treninzi/{pid}/dan/{did}/uredi", "admin"), (f"/treninzi/{pid}/dan/{did}", "member"),
                       ("/upitnik", "admin"), ("/moja-clanarina", "member"), ("/vodic", "admin"),
                       ("/dvoranski", "member"), ("/dvoranski/clanovi", "admin"), (f"/karton/{ivan}", "admin"),
                       ("/programi", "admin"), ("/treninzi/vjezbe", "admin")):
        page = c.get(path).text
        assert view_of(c) == view, path
        assert (menus(page) != {}) == (view == "admin") and (tabs(page) != []) == (view == "member"), path


def test_a_write_a_fetch_a_prefetch_and_an_asset_never_change_the_view():
    """The view changes on a GET of a page alone: a write (its redirect not
    followed), a script's fetch of a page (drawn in the view it is in), a
    prefetch, a HEAD and what is no page (the static files, the service
    worker, the healthcheck, a clip, a photo) leave it as it was; a browser's
    navigation takes it along, its own and one the service worker hands on
    (Sec-Fetch-Dest "empty", Sec-Fetch-Mode "navigate")."""
    make_user("trener@test.local", is_trainer=True)
    c = client_for("trener@test.local")
    c.get("/")
    r = c.post("/karton/ogranicenja", data={"text": "Koljeno."}, follow_redirects=False)
    assert r.status_code == 303 and view_of(c) == "admin"
    for headers in ({"Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty"}, {"Sec-Fetch-Mode": "same-origin"},
                    {"Sec-Fetch-Dest": "empty"}, {"Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Dest": "script"},
                    {"Sec-Purpose": "prefetch", **NAVIGATE}, {"Purpose": "prefetch"}):
        page = c.get("/karton", headers=headers).text
        assert view_of(c) == "admin" and menus(page) != {}, headers
    c.head("/karton")
    assert view_of(c) == "admin"
    for asset in ("/static/logo.png", "/sw.js", "/healthz", "/media/nema.jpg", "/slika/nema.jpg"):
        c.get(asset, headers=NAVIGATE)
        assert view_of(c) == "admin", asset
    c.get("/karton", headers=NAVIGATE)
    assert view_of(c) == "member"
    c.get("/kartoni", headers={"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "empty"})   # the service worker's
    assert view_of(c) == "admin"
    c.post("/pogled", data={"view": "member"})
    page = c.get("/kartoni", headers={"Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty"}).text
    assert view_of(c) == "member" and menus(page) == {}                 # a fetch of an admin page: drawn, the view kept


def test_acting_never_changes_the_view():
    """While staff act as a member nothing changes the view: in the whole
    app every page is the member's, his bar (no admin menu), his pages of
    either side asked for, the view as it was before; in a tab's view
    (Kartoni's entry) the bar over his karton and his tab is the admin bar,
    whatever the view before (the member view here), Članovi or Treninzi
    lit, and the view is the member view still once out."""
    make_user("coach@test.local", is_trainer=True)
    ivan = make_user("ivan@test.local", plans=("grupni",))
    c = client_for("coach@test.local")
    c.get("/")
    c.post(f"/kao/{ivan}", data={"natrag": "/kao"})
    for path in ("/karton", "/raspored", "/dvoranski", "/moja-clanarina", "/", "/kartoni", "/programi"):
        page = c.get(path, headers=NAVIGATE).text
        assert view_of(c) == "admin" and menus(page) == {}, path        # his bar (an admin page refuses him: 403)
    c.post(f"/kao/izlaz?kao={ivan}")
    c.post("/pogled", data={"view": "member"})
    r = c.post("/karton/clan", data={"clan": str(ivan), "natrag": "/kartoni"}, follow_redirects=False)
    assert r.headers["location"] == "/karton"
    exits = {label: [("/kao/izlaz?kamo=" + href, name) for href, name in items] for label, items in TRAINER_MENUS.items()}
    for path, tab, item in (("/karton", "Članovi", "Kartoni"), ("/dvoranski", "Treninzi", "Dvoranski treninzi")):
        page = c.get(path, headers=NAVIGATE).text
        assert items_of(page) == exits and lit(page) == ([tab], [item]), path   # every link the exit
        assert view_of(c) == "member" and 'action="/pogled"' not in page, path   # no switch in a tab's view
    c.get("/kao/izlaz", params={"kamo": "/raspored"})
    assert view_of(c) == "member" and menus(c.get("/raspored").text) == {}


# ---------- the bar on every page ----------

def test_each_admin_page_lights_its_tab_and_its_item():
    """In the admin view each admin page lights its tab and its item alone:
    Članovi (Kartoni, and the read-only karton, its crumb "Kartoni";
    Trenutne članarine; Gledaj kao član and its record; the owner's
    Korisnici), Treninzi (Raspored, and a termin's roster, opened from the
    week; Termini and its other pages; Dvoranski treninzi, and the
    templates' pages; Online treninzi, and the programme's and a day's
    editors; Vježbe, and an exercise's pages), Sadržaj (Tekstovi, Početna,
    Upitnik, Vodič), the owner's Statistika its plain tab; a shared page of
    no tab (Prehrana, the profile) nothing. In the member view a member
    page lights its tab. The three new pages carry their names."""
    make_user("trener@test.local", is_trainer=True)
    make_user("coach@test.local", is_trainer=True)
    ivan = make_user("ivan@test.local", plans=("grupni",))
    tid = db.add_template("Grupni trening", 0, 7 * 60, 60, 8, None)
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + timedelta(days=1), 60, 8, None)
    eid = db.create_exercise("Plank")
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    db.reset_gym_templates()
    gtid = db.gym_templates(all=True)[0].id
    cases = [("/kartoni", "Članovi", "Kartoni"), (f"/karton/{ivan}", "Članovi", "Kartoni"),
             ("/clanarine", "Članovi", "Trenutne članarine"), ("/kao", "Članovi", "Gledaj kao član"),
             ("/raspored", "Treninzi", "Raspored"), (f"/admin/session/{sid}", "Treninzi", "Raspored"),
             ("/admin", "Treninzi", "Termini"), (f"/admin/templates/{tid}", "Treninzi", "Termini"),
             ("/dvoranski/clanovi", "Treninzi", "Dvoranski treninzi"),
             ("/dvoranski/predlosci", "Treninzi", "Dvoranski treninzi"),
             (f"/dvoranski/predlosci/{gtid}", "Treninzi", "Dvoranski treninzi"),
             ("/programi", "Treninzi", "Online treninzi"), (f"/treninzi/{pid}/uredi", "Treninzi", "Online treninzi"),
             (f"/treninzi/{pid}/dan/{did}/uredi", "Treninzi", "Online treninzi"),
             ("/treninzi/vjezbe", "Treninzi", "Vježbe"), ("/treninzi/vjezbe/nova", "Treninzi", "Vježbe"),
             (f"/treninzi/vjezbe/{eid}", "Treninzi", "Vježbe"),
             ("/tekstovi", "Sadržaj", "Tekstovi"), ("/", "Sadržaj", "Početna"), ("/upitnik", "Sadržaj", "Upitnik"),
             ("/vodic", "Sadržaj", "Vodič")]
    owners = [("/kao/zapisi", "Članovi", "Gledaj kao član"), ("/korisnici", "Članovi", "Korisnici")]
    for email, walk in (("coach@test.local", cases), ("trener@test.local", cases + owners)):
        c = client_for(email)
        for path, tab, item in walk:
            r = c.get(path)
            assert r.status_code == 200 and view_of(c) == "admin", (email, path)
            assert lit(r.text) == ([tab], [item]), (email, path, lit(r.text))
        for path in ("/prehrana", "/profil"):
            assert lit(c.get(path).text) == ([], []), (email, path)
    o = client_for("trener@test.local")
    page = o.get("/statistika").text
    assert lit(page) == (["Statistika"], []) and stat_tab(page) == ("/statistika", True)
    assert client_for("coach@test.local").get("/statistika").status_code == 403
    for path, title in (("/kartoni", "Kartoni"), ("/dvoranski/clanovi", "Dvoranski treninzi"), ("/programi", "Online treninzi")):
        page = o.get(path).text
        assert f"<title>{title} — QMT</title>" in page and f"<h1>{title}</h1>" in page, path
    assert ('<nav class="crumbs" aria-label="Putanja"><a href="/kartoni">Kartoni</a><span class="sep">/</span>'
            in o.get(f"/karton/{ivan}").text)
    o.post("/pogled", data={"view": "member"})
    for path, tab in (("/", "Početna"), ("/raspored", "Raspored"), ("/karton", "Karton"),
                      ("/dvoranski", "Dvoranski treninzi"), ("/treninzi", "Online treninzi"),
                      ("/moja-clanarina", "Moja članarina"), ("/prehrana", "Prehrana")):
        page = o.get(path).text
        assert view_of(o) == "member" and lit(page) == ([tab], []), path
    upitnik = o.get("/upitnik").text                                    # an admin page: back in the admin view
    assert '<header class="topbar">' in upitnik and 'class="avatar' in upitnik   # not the solo pill
    assert lit(upitnik) == (["Sadržaj"], ["Upitnik"])


def test_dvoranski_treninzi_is_on_under_dvoranski_and_karton_is_not():
    """Dvoranski treninzi (27.11.2026, build 2 of the dvoranski treninzi) is
    .on on every /dvoranski page, the tab's, a training's and its osvrt's,
    for a member (a training outside a termin of his, and his termin's, the
    way in opening it) and for staff (one of theirs, in the member view
    those pages take them to) alike; the Karton tab, lit there from
    26.11.2026 until then, is not, nor any admin menu. A member whose gym
    plan lapsed opens his training by its link still: no tab is lit there,
    he has none for it."""
    from qmt.models import Membership
    ivan = make_user("ivan@test.local", plans=("grupni",))
    coach = make_user("coach@test.local", is_trainer=True)
    ana = make_user("ana@test.local", plans=("grupni",))
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) - timedelta(hours=1), 60, 8, None)
    with db.session_scope() as s:
        s.add(Booking(user_id=ivan, session_id=sid))
    ci = client_for("ivan@test.local")
    termin = ci.get(f"/dvoranski/termin/{sid}")                        # made as it is opened: its page
    [made] = db.gym_trainings(ivan)
    assert termin.url.path == f"/dvoranski/trening/{made.id}"
    pages = {"ivan@test.local": (db.add_gym_outside(ivan, config.today()), made.id),
             "coach@test.local": (db.add_gym_outside(coach, config.today()),)}
    for email, ids in pages.items():
        c = client_for(email)
        paths = ["/dvoranski"] + [p for tid in ids for p in (f"/dvoranski/trening/{tid}", f"/dvoranski/trening/{tid}/osvrt")]
        for path in paths:
            r = c.get(path)
            assert r.status_code == 200 and r.url.path == path, (email, path)
            assert [label for _, label, on in tabs(r.text) if on] == ["Dvoranski treninzi"], (email, path)
            assert menus(r.text) == {}, (email, path)
            assert '<a href="/karton" class="on">' not in r.text, (email, path)
    lapsed = db.add_gym_outside(ana, config.today())
    with db.session_scope() as s:                                       # her plan past its dospijeće
        s.scalar(db.select(Membership).where(Membership.user_id == ana)).next_payment = \
            config.today() - timedelta(days=Membership.GRACE_DAYS + 1)
    page = client_for("ana@test.local").get(f"/dvoranski/trening/{lapsed}").text
    assert "Dvoranski treninzi" not in nav(page) and [label for _, label, on in tabs(page) if on] == []


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


def open_page(browser, server: str, email: str, width: int, path: str, theme: str | None = None):
    """A logged-in page at `width` (a phone below 600px: touch), its theme
    set when one is given, and the list its page errors and console errors
    land in."""
    phone = width < 600
    ctx = browser.new_context(viewport={"width": width, "height": 900}, has_touch=phone, is_mobile=phone)
    pg = ctx.new_page(); errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
    pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    pg.goto(server + "/login")
    pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); localStorage.setItem('qmt-phone', String(Date.now())); }")      # the install banner and the phone reminder stay out of the way
    if theme:
        pg.evaluate("t => localStorage.setItem('qmt-theme', t)", theme)
    pg.fill("main input[name=email]", email); pg.fill("main input[name=password]", "lozinka123")
    pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
    go(pg, server + path)
    return ctx, pg, errors


def go(pg, url: str) -> None:
    pg.goto(url); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")


# The pill: ONE row (every child of the bar on its line, inside its padding,
# none over another; the tabs on one line, none wrapping its label), and
# nothing wider than the window. Then which wordmark shows.
PILL = r"""() => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().width > 0; };
  const px = v => parseFloat(v) || 0, out = [], de = document.documentElement;
  if (de.scrollWidth !== de.clientWidth) out.push(`the page is ${de.scrollWidth - de.clientWidth}px wider than the window`);
  const tb = document.querySelector('.topbar'), cs = getComputedStyle(tb), r = tb.getBoundingClientRect();
  const left = r.left + px(cs.borderLeftWidth) + px(cs.paddingLeft), right = r.right - px(cs.borderRightWidth) - px(cs.paddingRight);
  const top = r.top + px(cs.borderTopWidth) + px(cs.paddingTop), bottom = r.bottom - px(cs.borderBottomWidth) - px(cs.paddingBottom);
  const kids = [...tb.children].filter(k => vis(k) && getComputedStyle(k).position !== 'absolute');
  kids.forEach((k, i) => { const b = k.getBoundingClientRect(), mid = (b.top + b.bottom) / 2;
    if (b.left < left - .5 || b.right > right + .5) out.push(`${k.className} leaves the pill's padding`);
    if (mid < top || mid > bottom) out.push(`${k.className} is off the pill's row`);
    if (i && b.left < kids[i - 1].getBoundingClientRect().right - .5) out.push(`${k.className} overlaps ${kids[i - 1].className}`); });
  const nav = document.getElementById('mainNav');
  if (getComputedStyle(nav).position !== 'absolute') {
    const mids = [...nav.children].filter(vis).map(k => { const b = k.getBoundingClientRect(); return (b.top + b.bottom) / 2; });
    if (Math.max(...mids) - Math.min(...mids) > 2) out.push('the tabs are on more than one line');
    for (const t of nav.querySelectorAll(':scope > a, .navbtn')) if (vis(t) && t.getBoundingClientRect().height > 44) out.push(`"${t.textContent.trim()}" wraps`);
  }
  const shown = s => vis(document.querySelector(s));
  return {problems: out, wordmark: shown('.brand .full') && !shown('.brand .short') ? 'full' : shown('.brand .short') && !shown('.brand .full') ? 'QMT' : 'both or none'};
}"""

# An open menu (its id, its tab's id): under the pill, inside the window
# (12px off its edges), left-aligned to its tab unless the window's edge
# moved it in.
MENU = r"""([menu, btn]) => {
  const m = document.getElementById(menu).getBoundingClientRect(), b = document.getElementById(btn).getBoundingClientRect();
  const pill = document.querySelector('.topbar').getBoundingClientRect(), w = document.documentElement.clientWidth, out = [];
  if (m.left < 12 - .5 || m.right > w - 12 + .5) out.push(`the menu (${Math.round(m.left)}–${Math.round(m.right)}) leaves the window`);
  if (Math.abs(m.left - b.left) > 1 && Math.abs(m.right - (w - 12)) > 1) out.push(`the menu starts at ${Math.round(m.left)}, its tab at ${Math.round(b.left)}`);
  if (m.top < pill.bottom - 2) out.push(`the menu's top (${Math.round(m.top)}) is not under the pill (${Math.round(pill.bottom)})`);
  if (document.documentElement.scrollWidth !== w) out.push('the open menu widens the page');
  return out;
}"""

# The ☰ drawer, open: what it shows, in order (a caption as "# Članovi"),
# the groups' hairlines, and whether it stays inside the window.
DRAWER = r"""() => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().height > 0; };
  const nav = document.getElementById('mainNav'), r = nav.getBoundingClientRect(), w = document.documentElement.clientWidth;
  const shown = [...nav.querySelectorAll('.nav-cap, a, button')].filter(vis)
    .map(el => el.matches('.nav-cap') ? '# ' + el.textContent.trim() : el.textContent.trim().replace(/\s+/g, ' '));
  return {shown, inside: r.left >= 0 && r.right <= w, overflow: document.documentElement.scrollWidth - w,
          hairlines: [...nav.querySelectorAll('.nav-admin')].map(g => getComputedStyle(g).borderTopWidth),
          scrolls: getComputedStyle(nav).overflowY,
          current: [...nav.querySelectorAll('[aria-current="page"], a.on')].filter(vis).map(a => [a.textContent.trim(), getComputedStyle(a).backgroundColor])};
}"""

OPEN = "k => [getComputedStyle(document.getElementById(k + 'Menu')).display !== 'none', document.getElementById(k + 'Btn').getAttribute('aria-expanded')]"
MEMBER_LABELS = [label for _, label in MEMBER_ROW]
ADMIN_TABS = ["Članovi ▾", "Treninzi ▾", "Sadržaj ▾", "Statistika"]           # the owner's admin bar as shown
ADMIN_DRAWER = (["# Članovi"] + [label for _, label in OWNER_MENUS["Članovi"]]
                + ["# Treninzi"] + [label for _, label in OWNER_MENUS["Treninzi"]]
                + ["# Sadržaj"] + [label for _, label in OWNER_MENUS["Sadržaj"]] + ["Statistika"])


def test_the_admin_bar_its_menus_and_its_drawer_in_a_browser(server):
    """The owner's admin view at 1280 and 901px (light): the pill one row,
    the wordmark one of its two, the tabs Članovi ▾ · Treninzi ▾ · Sadržaj ▾
    · Statistika; each menu shut at first, a click opening it under its tab
    inside the window with its items, Escape shutting it; one open at a
    time, a click outside and the account menu shutting it; the keyboard
    (Enter opens, Tab reaches the first item, Escape gives the focus back);
    an item followed, Treninzi → Online treninzi: /programi, its tab .on
    and the item current. The switch and back at 1280px: the account menu's
    "Pogled člana" lands on / under the member's bar of seven, "Admin
    pogled" back. At 390px (dark) the drawer: the three captions over their
    rows, Statistika last, a hairline before each next group, inside the
    window, scrolling inside itself, the page's row current; the edit pill
    out of the open drawer's way; Trenutne članarine tapped leads there,
    marked. A client at 390 and 1280px: his row, the whole wordmark at
    1280px, the drawer's plain list, no editor on /upitnik?uredi=1. No page
    errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)                   # the owner, a trainer too
    make_user("ivan@test.local", plans=("grupni", "online"))
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w in (1280, 901):
            ctx, pg, errors = open_page(browser, server, "trener@test.local", w, "/", "light")
            where = f"[owner {w}px]"

            def check(ok: bool, what: str) -> None:
                if not ok:
                    problems.append(f"{where} {what}")

            bar, shown = pg.evaluate(PILL), pg.evaluate(SHOWN_TABS)
            problems += [f"{where} {p}" for p in bar["problems"]]
            check(bar["wordmark"] in ("full", "QMT"), f"the wordmark shows {bar['wordmark']}")
            check(shown["labels"] == ADMIN_TABS and not shown["drawer"] and not shown["clipped"], f"the bar: {shown}")
            for key, label in (("clanovi", "Članovi"), ("treninzi", "Treninzi"), ("sadrzaj", "Sadržaj")):
                check(pg.evaluate(OPEN, key) == [False, "false"], f"{label} on load: {pg.evaluate(OPEN, key)}")
                pg.click(f"#{key}Btn")
                check(pg.evaluate(OPEN, key) == [True, "true"], f"{label} after a click: {pg.evaluate(OPEN, key)}")
                problems += [f"{where} {label}: {p}" for p in pg.evaluate(MENU, [f"{key}Menu", f"{key}Btn"])]
                items = [t.strip() for t in pg.locator(f"#{key}Menu [role=menuitem]").all_text_contents()]
                check(items == [name for _, name in OWNER_MENUS[label]], f"{label}'s items: {items}")
                pg.keyboard.press("Escape")
                check(pg.evaluate(OPEN, key) == [False, "false"], f"{label} after Escape: {pg.evaluate(OPEN, key)}")
            pg.click("#clanoviBtn"); pg.click("#treninziBtn")                # one at a time
            check(pg.evaluate(OPEN, "clanovi")[0] is False and pg.evaluate(OPEN, "treninzi")[0] is True,
                  "opening Treninzi left Članovi open")
            pg.click("main h1")
            check(pg.evaluate(OPEN, "treninzi") == [False, "false"], "a click outside left Treninzi open")
            pg.click("#sadrzajBtn"); pg.click("#avatarBtn")
            check(pg.evaluate(OPEN, "sadrzaj")[0] is False and pg.locator("#userMenu").is_visible(),
                  "opening the account menu left Sadržaj open, or did not open")
            pg.keyboard.press("Escape")
            pg.focus("#treninziBtn"); pg.keyboard.press("Enter"); pg.keyboard.press("Tab")
            check(pg.evaluate("document.activeElement.textContent.trim()") == "Raspored",
                  f"Tab after Enter is on {pg.evaluate('document.activeElement.textContent.trim()')!r}")
            pg.keyboard.press("Escape")
            check(pg.evaluate(OPEN, "treninzi") == [False, "false"] and pg.evaluate("document.activeElement.id") == "treninziBtn",
                  "Escape from an item did not shut the menu and give the focus back to its tab")
            pg.click("#treninziBtn")
            with pg.expect_navigation():
                pg.click("#treninziMenu >> text=Online treninzi")
            pg.wait_for_load_state("networkidle")
            check(pg.url == server + "/programi" and pg.text_content("main h1") == "Online treninzi", f"Online treninzi led to {pg.url}")
            check(pg.evaluate("document.getElementById('treninziBtn').classList.contains('on')"), "Treninzi is not .on on /programi")
            check(pg.get_attribute('#treninziMenu a[href="/programi"]', "aria-current") == "page", "Online treninzi is not current")
            check(not pg.evaluate("document.getElementById('clanoviBtn').classList.contains('on')"), "Članovi is .on on /programi")
            if w == 1280:                                                  # the switch and back
                pg.click("#avatarBtn")
                with pg.expect_navigation():
                    pg.click("#userMenu >> text=Pogled člana")
                pg.wait_for_load_state("networkidle")
                shown = pg.evaluate(SHOWN_TABS)
                check(pg.url == server + "/" and shown["labels"] == MEMBER_LABELS and pg.locator("#clanoviBtn").count() == 0,
                      f"Pogled člana: {pg.url}, the bar {shown['labels']}")
                problems += [f"{where} the member view: {p}" for p in pg.evaluate(PILL)["problems"]]
                pg.click("#avatarBtn")
                with pg.expect_navigation():
                    pg.click("#userMenu >> text=Admin pogled")
                pg.wait_for_load_state("networkidle")
                check(pg.url == server + "/" and pg.evaluate(SHOWN_TABS)["labels"] == ADMIN_TABS, f"Admin pogled: {pg.url}")
            problems += [f"{where} {e}" for e in errors]
            ctx.close()

        ctx, pg, errors = open_page(browser, server, "trener@test.local", 390, "/", "dark")
        where = "[owner 390px]"
        problems += [f"{where} {p}" for p in pg.evaluate(PILL)["problems"]]
        pg.tap(".nav-burger")
        d = pg.evaluate(DRAWER)
        if d["shown"] != ADMIN_DRAWER:
            problems.append(f"{where} the drawer shows {d['shown']}")
        if d["hairlines"] != ["1px", "1px", "1px"] or not d["inside"] or d["overflow"] or d["scrolls"] != "auto":
            problems.append(f"{where} the drawer: hairlines {d['hairlines']}, inside {d['inside']}, overflow {d['overflow']}, "
                            f"overflow-y {d['scrolls']}")
        if d["current"] != [["Početna", "rgba(255, 255, 255, 0.13)"]]:
            problems.append(f"{where} the drawer's current row on /: {d['current']}")
        if pg.locator("#copyToggle").is_visible():
            problems.append(f"{where} the edit pill shows over the open drawer")
        with pg.expect_navigation():
            pg.tap("#mainNav >> text=Trenutne članarine")
        pg.wait_for_load_state("networkidle")
        pg.tap(".nav-burger")
        d = pg.evaluate(DRAWER)
        if pg.url != server + "/clanarine" or d["current"] != [["Trenutne članarine", "rgba(255, 255, 255, 0.13)"]]:
            problems.append(f"{where} Trenutne članarine led to {pg.url}, current {d['current']}")
        problems += [f"{where} {e}" for e in errors]
        ctx.close()

        for w in (390, 1280):
            ctx, pg, errors = open_page(browser, server, "ivan@test.local", w, "/raspored")
            where = f"[ivan {w}px]"
            bar = pg.evaluate(PILL)
            problems += [f"{where} {p}" for p in bar["problems"]]
            if bar["wordmark"] != ("full" if w == 1280 else "QMT"):
                problems.append(f"{where} the wordmark shows {bar['wordmark']}")
            if w == 390:
                pg.tap(".nav-burger")
                d = pg.evaluate(DRAWER)
                if d["shown"] != MEMBER_LABELS or d["hairlines"] or not d["inside"] or d["overflow"]:
                    problems.append(f"{where} the drawer: {d}")
            go(pg, server + "/upitnik?uredi=1")                          # a client has no editor, whatever the address says
            state = pg.evaluate("[document.body.classList.contains('editing'), !!document.getElementById('copyToggle')]")
            if state != [False, False]:
                problems.append(f"{where} a client's /upitnik?uredi=1: edit mode, editor = {state}")
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# The bar's tabs as shown, in order, and the ones whose label is cut (its
# content wider than its box)
SHOWN_TABS = r"""() => {
  const vis = el => getComputedStyle(el).display !== 'none' && el.getBoundingClientRect().width > 0;
  const tabs = [...document.querySelectorAll('#mainNav > a, #mainNav .navbtn')].filter(vis);
  return {labels: tabs.map(t => t.textContent.trim().replace(/\s+/g, ' ')),
          clipped: tabs.filter(t => t.scrollWidth > t.clientWidth + 1).map(t => t.textContent.trim()),
          drawer: getComputedStyle(document.getElementById('mainNav')).position === 'absolute',
          theme: document.documentElement.getAttribute('data-theme')};
}"""


# A bar of seven tab links is the ☰ drawer up to this width less one, and one
# row from it (27.11.2026, build 2 of the dvoranski treninzi: Dvoranski
# treninzi joined the member's row). Measured that day for the owner's bar,
# the widest then (seven tabs and Admin ▾), at every width from 901 to 1280px
# in both themes, its seven tabs tight (base.html's rule for seven): at
# 901–935px the avatar left the pill's padding (the page scrolling sideways
# too, up to 914px), from 936px every tab sat on its line inside the pill,
# the brand's slot 87px there (its floor 86.4px, "QMT"). Since 28.11.2026 a
# bar of seven is a client's or a staff account's member view, which holds
# no Admin ▾ (narrower: the fold stands, the brief's rule for seven).
SEVEN_FIT = 936
# and the fold itself: SEVEN_FIT left 0.6px to spare in Chromium on the Mac it
# was measured on, so the bar of seven shows from 960px (Fable's review: room
# for another browser's letter widths)
SEVEN_FOLD = 960
WIDTHS = (901, 920, SEVEN_FIT, SEVEN_FOLD - 1, SEVEN_FOLD, 1024, 1100, 1200, 1280)


def test_the_bars_room_from_901px_the_admin_bar_a_row_and_a_bar_of_seven_the_drawer_up_to_959px(server):
    """The owner's admin bar, three menus and Statistika, needs none of a
    bar of seven's rules: at 901, 920, 936, 959, 960, 1024, 1100, 1200 and
    1280px, both themes, it is the bar (never the drawer from 901px), one
    row inside the pill (every child inside its padding and on its line,
    none over another; the tabs on one line, none wrapping or cutting its
    label), the page no wider than the window, the wordmark one of its two.
    A bar of seven, the owner's member view's (switched with POST /pogled),
    is the ☰ drawer up to 959px (the ☰ shown, the tabs not in the bar; the
    drawer opened shows the member's row, inside the window) and the bar
    from 960px, at the same widths and themes. A client's bar of seven the
    same at 959 and 960px; a client's bar of six (a gym plan, no online
    plan) keeps the 900px fold: at 901px a row. No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)                   # the owner, a trainer too
    make_user("ivan@test.local", plans=("grupni", "online"))           # seven tab links
    make_user("ana@test.local", plans=("grupni",))                     # six
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        def measure(pg, where: str, labels: list[str], drawer: bool, opened: list[str] | None = None) -> None:
            bar, shown = pg.evaluate(PILL), pg.evaluate(SHOWN_TABS)
            problems.extend(f"{where} {p}" for p in bar["problems"])
            if bar["wordmark"] not in ("full", "QMT"):
                problems.append(f"{where} the wordmark shows {bar['wordmark']}")
            if drawer:
                if not shown["drawer"] or not pg.locator(".nav-burger").is_visible():
                    problems.append(f"{where} not the drawer: the bar shows {shown['labels']}")
                if opened is not None:                                   # the ☰ opens it, as on a phone
                    pg.click(".nav-burger")
                    d = pg.evaluate(DRAWER)
                    if d["shown"] != opened or not d["inside"] or d["overflow"]:
                        problems.append(f"{where} the drawer shows {d['shown']} (inside {d['inside']}, "
                                        f"overflow {d['overflow']})")
                    pg.click(".nav-burger")
            else:
                if shown["drawer"] or shown["labels"] != labels:
                    problems.append(f"{where} the bar shows {shown['labels']} (in the drawer: {shown['drawer']})")
                if shown["clipped"]:
                    problems.append(f"{where} labels cut: {shown['clipped']}")

        for theme in ("light", "dark"):
            ctx, pg, errors = open_page(browser, server, "trener@test.local", 1280, "/raspored", theme)
            for view in ("admin", "member"):
                pg.request.post(server + "/pogled", form={"view": view})
                for w in WIDTHS:
                    pg.set_viewport_size({"width": w, "height": 900})
                    go(pg, server + "/raspored")
                    where = f"[owner {view} {theme} {w}px]"
                    if view == "admin":
                        measure(pg, where, ADMIN_TABS, False)
                    else:
                        measure(pg, where, MEMBER_LABELS, w < SEVEN_FOLD, MEMBER_LABELS)
                    if pg.evaluate("document.documentElement.getAttribute('data-theme')") != theme:
                        problems.append(f"{where} the page is not in the {theme} theme")
            problems += [f"[owner {theme}] {e}" for e in errors]
            ctx.close()
        for email, w, labels, drawer in (("ivan@test.local", SEVEN_FOLD - 1, MEMBER_LABELS, True),
                                         ("ivan@test.local", SEVEN_FOLD, MEMBER_LABELS, False),
                                         ("ana@test.local", 901, [x for x in MEMBER_LABELS if x != "Online treninzi"], False)):
            ctx, pg, errors = open_page(browser, server, email, w, "/raspored")
            measure(pg, f"[{email.split('@')[0]} {w}px]", labels, drawer, labels if drawer else None)
            problems += [f"[{email.split('@')[0]} {w}px] {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# the copy editor's state: the address, edit mode, the pill's words and
# aria-pressed, and the one-shot flag the editor's own forms leave
EDITOR = """() => { const t = document.getElementById('copyToggle');
  return [location.pathname, document.body.classList.contains('editing'), t.textContent, t.getAttribute('aria-pressed'),
          sessionStorage.getItem('qmt-editing-once')]; }"""


def normal(path: str) -> list:
    return [path, False, "✎ Uredi tekstove", "false", None]


def editing(path: str) -> list:
    return [path, True, "✓ Gotovo", "true", None]


def test_staff_open_the_upitnik_in_normal_mode_with_the_pill(server):
    """No page opens in edit mode by itself (26.10.2026, the owner: "when
    I go to admin's 'upitnik' I go to the edit mode immediately"): the owner
    and a trainer who is not the owner land on /upitnik, and on
    /upitnik?uredi=1 (Admin ▾'s link until then, which meant edit mode), in
    normal mode with the ✎ pill shown to press, at 1280px and on a phone;
    the trainer's admin menus have his items (no Korisnici). No page
    errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)                   # the owner, a trainer too
    make_user("coach@test.local", is_trainer=True)                    # a trainer who is not the owner
    problems: list[str] = []
    want = [name for items in TRAINER_MENUS.values() for _, name in items]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for email, w in (("trener@test.local", 390), ("trener@test.local", 1280), ("coach@test.local", 1280)):
            for path in ("/upitnik", "/upitnik?uredi=1"):
                ctx, pg, errors = open_page(browser, server, email, w, path)
                where = f"[{email.split('@')[0]} {w}px {path}]"
                state, shown = pg.evaluate(EDITOR), pg.locator("#copyToggle").is_visible()
                if state != normal("/upitnik") or not shown:
                    problems.append(f"{where} lands as {state}, the pill shown: {shown}")
                if email == "coach@test.local":
                    labels = [t.strip() for t in pg.locator(".admin-menu [role=menuitem]").all_text_contents()]
                    if labels != want:
                        problems.append(f"{where} the admin menus' items: {labels}")
                problems += [f"{where} {e}" for e in errors]
                ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


def test_edit_mode_ends_when_the_editor_leaves_the_page(server):
    """Edit mode belongs to the page (26.10.2026, the owner: "I dont exit
    the edit mode when switching tabs"). The trainer turns it on on the
    landing and follows the admin bar's Treninzi → Raspored: normal mode;
    on there, then Sadržaj → Upitnik: normal mode too, and the pill on every
    page. The editor's own forms reload the page and are the one way it
    outlives a load: "+ Dodaj najavu" (a plain submit) and the second tap of
    "Obriši najavu" (form.submit()) bring the landing back in edit mode, the
    one-shot flag spent; a reload by hand then lands in normal mode. On a
    phone (the drawer's rows) and at 1280px (the menus); no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w in (390, 1280):
            phone = w < 600
            ctx, pg, errors = open_page(browser, server, "trener@test.local", w, "/")
            where = f"[trener {w}px]"

            def check(want: list, what: str) -> None:
                seen = pg.evaluate(EDITOR)
                if seen != want or not pg.locator("#copyToggle").is_visible():
                    problems.append(f"{where} {what}: {seen}, the pill shown: {pg.locator('#copyToggle').is_visible()}")

            def follow(menu: str, href: str) -> None:
                """An admin menu's item, the way this width reaches it: the
                ☰ drawer on a phone, its menu opened on a desktop."""
                link = f'#{menu}Menu a[href="{href}"]'
                if phone:
                    pg.tap(".nav-burger")
                else:
                    pg.click(f"#{menu}Btn")
                with pg.expect_navigation():
                    pg.tap(link) if phone else pg.click(link)
                pg.wait_for_load_state("networkidle")

            check(normal("/"), "the landing opens")
            pg.click("#copyToggle")
            check(editing("/"), "the pill pressed")
            follow("treninzi", "/raspored")
            check(normal("/raspored"), "Treninzi → Raspored followed in edit mode")
            pg.click("#copyToggle")
            check(editing("/raspored"), "the pill pressed on Raspored")
            follow("sadrzaj", "/upitnik")
            check(normal("/upitnik"), "Sadržaj → Upitnik followed in edit mode")
            follow("sadrzaj", "/")
            check(normal("/"), "Početna followed")
            pg.click("#copyToggle")
            with pg.expect_navigation():
                pg.click(".ed-add-ann button")                             # + Dodaj najavu
            pg.wait_for_load_state("networkidle")
            check(editing("/"), "+ Dodaj najavu came back")
            if len(db.announcements(all=True)) != 1 or pg.evaluate("location.hash") != "#aktualno":
                problems.append(f"{where} + Dodaj najavu: {len(db.announcements(all=True))} cards, at {pg.evaluate('location.hash')!r}")
            x = pg.locator("#aktualno .ed-ann-x > button").first
            x.click()                                                      # Obriši najavu: two taps
            with pg.expect_navigation():
                x.click()
            pg.wait_for_load_state("networkidle")
            check(editing("/"), "Obriši najavu came back")
            if db.announcements(all=True):
                problems.append(f"{where} Obriši najavu left {len(db.announcements(all=True))} cards")
            pg.reload(); pg.wait_for_load_state("networkidle")
            check(normal("/"), "a reload by hand")
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"
