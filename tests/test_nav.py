"""The topbar's tabs, grouped (26.10.2026; the owner: "lets somehow group the
tabs which are related for me and in another group the tabs which are there
and different because I am an admin").

A client's row: Početna · Raspored · Karton · Dvoranski treninzi (while a
plan that books termini runs, since 27.11.2026: build 2 of the dvoranski
treninzi; the owner: "I would show the tab only to members with a gym
plan. Similarly how a online training tab shows only to members with an
online plan.") · Online treninzi (while an online plan runs) · Moja
članarina · Prehrana. Staff's, the trainer's and the owner's: that row
(without Karton until 24.11.2026, when staff got a karton of their own; the
owner: "Lets show the Karton tab in the Admin view as well"; Dvoranski
treninzi always, as Online treninzi), then "Admin ▾", a menu in the account
menu's component: Gledaj kao član (/kao, staff act as a member, 26.11.2026),
Termini (/admin), Trenutne članarine (/clanarine), Upitnik
(/upitnik), Vježbe (/treninzi/vjezbe, the library of exercises, 30.10.2026),
Tekstovi (/tekstovi, every text of the app on one page, 25.11.2026)
and, the owner's only, Korisnici and Statistika. The tab is .on
while one of its pages is open, that item aria-current="page"; staff's
Karton at /karton and, since 27.11.2026, on a client's karton (/karton/<id>,
which the Karton tab's search opens), no item of Admin ▾ there (Trenutne
članarine, then Korisnici, until then). The account menu is Profil, the
theme and Odjava for everyone.
In the ☰ drawer (≤900px) a client has the one plain list, staff two
sections under captions, "Kao član" and "Admin" (the menu's items as rows).

The route half reads the HTML. The browser half starts the app in a thread,
as tests/test_copy.py does, and walks the owner and a client at 390 and
1280px: the pill is one row and nothing widens the page, the wordmark rule
holds, the Admin menu opens and closes (a click, Escape, a click outside,
the keyboard) and its items lead to their pages, and the drawer shows its
sections; the owner's bar (seven tabs and Admin ▾ since 27.11.2026, six
until then) is the drawer up to 959px and one row from 960px, measured at
901, 920, 936, 959, 960, 1024, 1100, 1200 and 1280px, both themes, and a
bar of six keeps the drawer at 900px. Then edit mode (26.10.2026, the owner: "when I go to a tab as an
admin, please dont make it editable but default"): no page opens in it by
itself, so staff land on /upitnik, ?uredi=1 (the old way in) or not, in
normal mode with the ✎ pill there to press; leaving a page ends it (a tab,
the menu, a reload by hand), and only the editor's own forms, which reload
the landing, bring it back in edit mode.
"""

from __future__ import annotations

import os
import re
import threading
import time
from datetime import date

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import httpx
import pytest
from fastapi.testclient import TestClient

from qmt import auth, config, db
from qmt.models import Base, User
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
    """The tabs right in the nav, in order: (href, label, .on)."""
    return [(href, label, on == "on")
            for href, on, label in re.findall(r'^\s*<a href="([^"]+)" class="(on|)">([^<]+)</a>', nav(page), re.M)]


def admin_items(page: str) -> list[tuple[str, str, bool]]:
    """Admin ▾'s items, in order: (href, label, aria-current="page")."""
    return [(href, label, bool(current))
            for href, current, label in re.findall(
                r'<a href="([^"]+)" role="menuitem"( aria-current="page")?>\s*<svg.*?</svg><span>([^<]+)</span>',
                nav(page), re.S)]


def admin_tab(page: str) -> tuple[str, bool] | None:
    """Admin ▾ itself: (its label as read, .on), or None without one."""
    m = re.search(r'<button type="button" id="adminBtn" class="navbtn menu-btn( on)?"[^>]*>(.*?)</button>', nav(page), re.S)
    return (re.sub(r"<[^>]+>", "", m.group(2)), bool(m.group(1))) if m else None


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
# "Gledaj kao član" first since 26.11.2026 (staff act as a member: /kao)
TRAINER_ITEMS = [("/kao", "Gledaj kao član"), ("/admin", "Termini"), ("/clanarine", "Trenutne članarine"),
                 ("/upitnik", "Upitnik"), ("/treninzi/vjezbe", "Vježbe"), ("/tekstovi", "Tekstovi")]
OWNER_ITEMS = TRAINER_ITEMS + [("/korisnici", "Korisnici"), ("/statistika", "Statistika")]
ACCOUNT = ["Profil", "Tamna tema", "Odjava"]


def test_a_clients_row_is_the_members_tabs_and_nothing_of_admin():
    """A client's row: a gym plan and an online plan, seven tab links (the
    bar says so, its nav and its ☰ .nav-7: the drawer up to 959px, below);
    no online plan, no Online treninzi; since 27.11.2026 no plan that books
    termini, no Dvoranski treninzi (an online plan alone, none at all). His
    karton lights his Karton tab."""
    make_user("ivan@test.local", plans=("grupni", "online"))
    make_user("ana@test.local", plans=("grupni",))                     # no online plan: no Online treninzi, as before
    make_user("mia@test.local", plans=("online",))                     # online alone: no Dvoranski treninzi
    make_user("sara@test.local")                                       # no plan: neither
    page = client_for("ivan@test.local").get("/raspored").text
    assert tabs(page) == [("/", "Početna", False), ("/raspored", "Raspored", True), ("/karton", "Karton", False),
                          ("/dvoranski", "Dvoranski treninzi", False), ("/treninzi", "Online treninzi", False),
                          ("/moja-clanarina", "Moja članarina", False), ("/prehrana", "Prehrana", False)]
    assert seven(page)
    assert admin_tab(page) is None and admin_items(page) == [] and captions(page) == []   # one plain list in the drawer too
    for mark in ('id="adminMenu"', 'href="/admin"', 'href="/clanarine"', 'href="/korisnici"', 'href="/statistika"', "Admin"):
        assert mark not in nav(page), mark
    assert account_menu(page) == ACCOUNT                                   # no Moja članarina item: the tab is the way
    for email, row in (("ana@test.local", ["Početna", "Raspored", "Karton", "Dvoranski treninzi", "Moja članarina",
                                           "Prehrana"]),
                       ("mia@test.local", ["Početna", "Raspored", "Karton", "Online treninzi", "Moja članarina",
                                           "Prehrana"]),
                       ("sara@test.local", ["Početna", "Raspored", "Karton", "Moja članarina", "Prehrana"])):
        theirs = client_for(email).get("/raspored").text
        assert [label for _, label, _ in tabs(theirs)] == row, email
        assert not seven(theirs) and '<nav class="nav" id="mainNav">' in theirs, email   # six or fewer: today's 900px
        assert '<button type="button" class="navbtn nav-burger" onclick=' in theirs, email
    karton = client_for("ivan@test.local").get("/karton").text                # his karton lights his tab, as ever
    assert [label for _, label, on in tabs(karton) if on] == ["Karton"]


def test_staff_get_the_members_row_and_admin_with_their_items():
    """The member's row, Karton in it since 24.11.2026 (staff have a karton
    of their own now; the owner: "Lets show the Karton tab in the Admin
    view as well so that Amir can check out the changes we made there") and
    Dvoranski treninzi since 27.11.2026 (staff always: seven tab links, the
    bar says so), then Admin ▾: six items for a trainer who is not the owner
    (Tekstovi since 25.11.2026, "Gledaj kao član" first since 26.11.2026),
    eight for the owner. Two captions for the drawer, Karton under "Kao
    član", and the account menu without a Moja članarina item: the tab is in
    their row."""
    make_user("trener@test.local", is_trainer=True)                     # the owner, who trains too (the demo's trener)
    make_user("coach@test.local", is_trainer=True)                      # a trainer who is not the owner
    for email, items in (("coach@test.local", TRAINER_ITEMS), ("trener@test.local", OWNER_ITEMS)):
        page = client_for(email).get("/raspored").text
        assert [(href, label) for href, label, _ in tabs(page)] == MEMBER_ROW, email
        assert seven(page), email
        assert admin_tab(page) == ("Admin ▾", False), email
        assert [(href, label) for href, label, _ in admin_items(page)] == items, email
        assert captions(page) == ["Kao član", "Admin"], email
        assert account_menu(page) == ACCOUNT, email
        assert '<span class="caret" aria-hidden="true">▾</span>' in nav(page), email   # read as "Admin"
        assert 'aria-controls="adminMenu"' in nav(page) and 'role="menu" aria-labelledby="adminBtn"' in nav(page), email


def test_an_owner_who_does_not_train_is_staff_too():
    """Staff is the trainer or the owner (the routes' _require_trainer): an
    owner without is_trainer gets the same bar, Karton in it (24.11.2026),
    all eight items, and since 26.11.2026 Online treninzi as a trainer does,
    whatever his plans (the owner is staff by rule: app._is_staff; until
    then the tab followed his plans, as a client's); Dvoranski treninzi
    too, since 27.11.2026."""
    make_user("trener@test.local", plans=("grupni",))                  # the owner, not a trainer, no online plan
    page = client_for("trener@test.local").get("/raspored").text
    assert [label for _, label, _ in tabs(page)] == ["Početna", "Raspored", "Karton", "Dvoranski treninzi",
                                                     "Online treninzi", "Moja članarina", "Prehrana"]
    assert [(href, label) for href, label, _ in admin_items(page)] == OWNER_ITEMS
    assert account_menu(page) == ACCOUNT


def test_the_owner_is_staff_by_rule_whatever_his_trainer_flag():
    """The owner is staff by rule (26.11.2026, the owner: "can we add
    everything the trainer sees the admin (me) sees"; app._is_staff, the
    templates' can_edit_copy): with his trainer flag OFF he logs in as a
    trainer does (no profile asked first), and gets the trainer's /raspored
    (the rosters' links, no gate line, no "Tjedan | Mjesec" switch), the
    Online treninzi tab and staff's /treninzi table, a programme's and a
    day's page with "Uredi …", the player and its finish screen with
    staff's bar (not the one-task pill), his own /karton as staff's, every
    Admin ▾ item, no install banner and no phone reminder; he is listed on
    neither /clanarine nor /kao, and nobody enters his account (POST
    /kao/<his id>). A member, beside him, keeps a member's page."""
    from datetime import datetime, timedelta
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
    assert ("/treninzi", "Online treninzi") in [(href, label) for href, label, _ in tabs(raspored)]
    assert [(href, label) for href, label, _ in admin_items(raspored)] == OWNER_ITEMS
    assert 'id="a2hs"' not in raspored and 'id="phoneCard"' not in raspored and 'id="a2hs"' in theirs
    assert "Programi po razinama" in c.get("/treninzi").text            # staff's table
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    db.add_day_item(did, db.create_exercise("Plank"), "trening")
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


def test_admin_is_on_while_one_of_its_pages_is_open_and_marks_that_item():
    """On Gledaj kao član (26.11.2026: /kao, and its record, /kao/zapisi),
    Termini (its sub-pages too), Trenutne članarine, Upitnik, Vježbe (an
    exercise's page too: under /treninzi, yet Online treninzi is not .on
    there), Tekstovi, Korisnici and Statistika the Admin tab is
    .on and that item, alone, aria-current; no member tab is (Karton not on
    /upitnik). Elsewhere the member's tab is .on and Admin is not: Karton on
    staff's own karton, /karton, and since 27.11.2026 on a client's karton,
    /karton/<id>, the trainer's and the owner's alike (the Karton tab's
    search opens it; it lit Trenutne članarine from 24.11.2026, then
    Korisnici, the owner's alone, for some hours of that day). The pages
    carry the items' names. Staff's /upitnik keeps the whole bar: the
    brand-only pill is a member's (who fills it)."""
    make_user("trener@test.local", is_trainer=True)
    ivan = make_user("ivan@test.local", plans=("grupni",))
    tid = db.add_template("Grupni trening", 0, 7 * 60, 60, 8, None)
    eid = db.create_exercise("Plank")
    c = client_for("trener@test.local")
    for path, item in (("/kao", "Gledaj kao član"), ("/kao/zapisi", "Gledaj kao član"),
                       ("/admin", "Termini"), (f"/admin/templates/{tid}", "Termini"),
                       ("/clanarine", "Trenutne članarine"), ("/upitnik", "Upitnik"),
                       ("/treninzi/vjezbe", "Vježbe"), ("/treninzi/vjezbe/nova", "Vježbe"),
                       (f"/treninzi/vjezbe/{eid}", "Vježbe"), ("/tekstovi", "Tekstovi"),
                       ("/korisnici", "Korisnici"), ("/statistika", "Statistika")):
        page = c.get(path).text
        assert admin_tab(page) == ("Admin ▾", True), path
        assert [label for _, label, current in admin_items(page) if current] == [item], path
        assert [label for _, label, on in tabs(page) if on] == [], path
    # a client's karton is under the Karton tab since 27.11.2026, whose search
    # opens it: for the owner and for a trainer who is not the owner (refused
    # it for some hours that day), Karton on, Admin ▾ not, no item current
    make_user("coach@test.local", is_trainer=True)
    for who in (c, client_for("coach@test.local")):
        r = who.get(f"/karton/{ivan}")
        assert r.status_code == 200 and admin_tab(r.text) == ("Admin ▾", False)
        assert not any(current for *_, current in admin_items(r.text))
        assert [label for _, label, on in tabs(r.text) if on] == ["Karton"]
    for path, tab in (("/", "Početna"), ("/raspored", "Raspored"), ("/karton", "Karton"),
                      ("/dvoranski", "Dvoranski treninzi"), ("/treninzi", "Online treninzi"),
                      ("/moja-clanarina", "Moja članarina"), ("/prehrana", "Prehrana")):
        page = c.get(path).text
        assert admin_tab(page) == ("Admin ▾", False) and not any(current for *_, current in admin_items(page)), path
        assert [label for _, label, on in tabs(page) if on] == [tab], path
    admin, clanarine = c.get("/admin").text, c.get("/clanarine").text
    assert "<title>Termini — QMT</title>" in admin and "<h1>Termini</h1>" in admin
    assert "<title>Trenutne članarine — QMT</title>" in clanarine and "<h1>Trenutne članarine</h1>" in clanarine
    upitnik = c.get("/upitnik").text
    assert '<header class="topbar">' in upitnik and 'class="avatar' in upitnik   # not the solo pill


def test_dvoranski_treninzi_is_on_under_dvoranski_and_karton_is_not():
    """Dvoranski treninzi (27.11.2026, build 2 of the dvoranski treninzi) is
    .on on every /dvoranski page, the tab's, a training's and its osvrt's,
    for a member (a training outside a termin of his, and his termin's, the
    way in opening it) and for staff (one of theirs) alike; the Karton tab,
    lit there from 26.11.2026 until then, is not, nor Admin ▾. A member
    whose gym plan lapsed opens his training by its link still: no tab is
    lit there, he has none for it."""
    from datetime import datetime, timedelta

    from qmt.models import Booking, Membership
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
            assert admin_tab(r.text) in (None, ("Admin ▾", False)), (email, path)
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


def open_page(browser, server: str, email: str, width: int, path: str):
    """A logged-in page at `width` (a phone below 600px: touch), and the
    list its page errors and console errors land in."""
    phone = width < 600
    ctx = browser.new_context(viewport={"width": width, "height": 900}, has_touch=phone, is_mobile=phone)
    pg = ctx.new_page(); errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
    pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    pg.goto(server + "/login")
    pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); localStorage.setItem('qmt-phone', String(Date.now())); }")      # the install banner and the phone reminder stay out of the way
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

# The open Admin menu: under the pill, inside the window (12px off its
# edges), left-aligned to its tab unless the window's edge moved it in.
MENU = r"""() => {
  const m = document.getElementById('adminMenu').getBoundingClientRect(), b = document.getElementById('adminBtn').getBoundingClientRect();
  const pill = document.querySelector('.topbar').getBoundingClientRect(), w = document.documentElement.clientWidth, out = [];
  if (m.left < 12 - .5 || m.right > w - 12 + .5) out.push(`the menu (${Math.round(m.left)}–${Math.round(m.right)}) leaves the window`);
  if (Math.abs(m.left - b.left) > 1 && Math.abs(m.right - (w - 12)) > 1) out.push(`the menu starts at ${Math.round(m.left)}, its tab at ${Math.round(b.left)}`);
  if (m.top < pill.bottom - 2) out.push(`the menu's top (${Math.round(m.top)}) is not under the pill (${Math.round(pill.bottom)})`);
  if (document.documentElement.scrollWidth !== w) out.push('the open menu widens the page');
  return out;
}"""

# The ☰ drawer, open: what it shows, in order (a caption as "# Kao član"),
# the rows' hairline, and whether it stays inside the window.
DRAWER = r"""() => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().height > 0; };
  const nav = document.getElementById('mainNav'), r = nav.getBoundingClientRect(), w = document.documentElement.clientWidth;
  const shown = [...nav.querySelectorAll('.nav-cap, a, button')].filter(vis)
    .map(el => el.matches('.nav-cap') ? '# ' + el.textContent.trim() : el.textContent.trim().replace(/\s+/g, ' '));
  const admin = nav.querySelector('.nav-admin');
  return {shown, inside: r.left >= 0 && r.right <= w, overflow: document.documentElement.scrollWidth - w,
          hairline: admin ? getComputedStyle(admin).borderTopWidth : null,
          current: [...nav.querySelectorAll('[aria-current="page"], a.on')].filter(vis).map(a => [a.textContent.trim(), getComputedStyle(a).backgroundColor])};
}"""

OPEN = "() => [getComputedStyle(document.getElementById('adminMenu')).display !== 'none', document.getElementById('adminBtn').getAttribute('aria-expanded')]"
MEMBER_LABELS = [label for _, label in MEMBER_ROW]


def test_the_bar_menu_and_drawer_in_a_browser(server):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)                   # the owner, a trainer too
    make_user("ivan@test.local", plans=("grupni", "online"))
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for email, staff in (("trener@test.local", True), ("ivan@test.local", False)):
            for w in (390, 1280):
                ctx, pg, errors = open_page(browser, server, email, w, "/raspored")
                where = f"[{email.split('@')[0]} {w}px]"

                def check(ok: bool, what: str) -> None:
                    if not ok:
                        problems.append(f"{where} {what}")

                bar = pg.evaluate(PILL)
                problems += [f"{where} {p}" for p in bar["problems"]]
                # the whole name at 1280px where its slot holds it: a client's seven tabs leave it the room,
                # staff's seven and Admin ▾ (27.11.2026) not even in the 1100px pill, "QMT" (the brand's own query)
                check(bar["wordmark"] == ("full" if w == 1280 and not staff else "QMT"), f"the wordmark shows {bar['wordmark']}")

                if w == 1280 and staff:
                    # the menu: shut, then a click opens it under its tab, Escape shuts it
                    check(pg.evaluate(OPEN) == [False, "false"], f"Admin's menu on load: {pg.evaluate(OPEN)}")
                    pg.click("#adminBtn")
                    check(pg.evaluate(OPEN) == [True, "true"], f"after a click: {pg.evaluate(OPEN)}")
                    problems += [f"{where} {p}" for p in pg.evaluate(MENU)]
                    labels = pg.locator("#adminMenu [role=menuitem]").all_text_contents()
                    check([t.strip() for t in labels] == [label for _, label in OWNER_ITEMS], f"its items: {labels}")
                    pg.keyboard.press("Escape")
                    check(pg.evaluate(OPEN) == [False, "false"], f"after Escape: {pg.evaluate(OPEN)}")
                    # a click outside shuts it; so does opening the account menu, one at a time
                    pg.click("#adminBtn"); pg.click("main h1")
                    check(pg.evaluate(OPEN) == [False, "false"], f"after a click outside: {pg.evaluate(OPEN)}")
                    pg.click("#adminBtn"); pg.click("#avatarBtn")
                    check(pg.evaluate(OPEN) == [False, "false"] and pg.locator("#userMenu").is_visible(),
                          "opening the account menu left Admin's open, or did not open")
                    pg.keyboard.press("Escape")
                    check(not pg.locator("#userMenu").is_visible(), "Escape left the account menu open")
                    # the keyboard: Enter opens it, Tab reaches the first item, Escape gives the focus back
                    pg.focus("#adminBtn"); pg.keyboard.press("Enter")
                    pg.keyboard.press("Tab")
                    check(pg.evaluate("document.activeElement.textContent.trim()") == "Gledaj kao član",
                          f"Tab after Enter is on {pg.evaluate('document.activeElement.textContent.trim()')!r}")
                    pg.keyboard.press("Escape")
                    check(pg.evaluate(OPEN) == [False, "false"] and pg.evaluate("document.activeElement.id") == "adminBtn",
                          "Escape from an item did not shut the menu and give the focus back to Admin")
                    # the items lead to their pages, the tab and the item marked there
                    pg.click("#adminBtn")
                    with pg.expect_navigation():
                        pg.click("#adminMenu >> text=Termini")
                    pg.wait_for_load_state("networkidle")
                    check(pg.url == server + "/admin" and pg.text_content("main h1") == "Termini", f"Termini led to {pg.url}")
                    check(pg.evaluate("document.getElementById('adminBtn').classList.contains('on')"), "Admin is not .on on /admin")
                    check(pg.get_attribute('#adminMenu a[href="/admin"]', "aria-current") == "page", "Termini is not aria-current on /admin")
                    # Upitnik: /upitnik in normal mode, the ✎ pill there to press
                    pg.click("#adminBtn")
                    with pg.expect_navigation():
                        pg.click("#adminMenu >> text=Upitnik")
                    pg.wait_for_load_state("networkidle")
                    state = pg.evaluate("[location.pathname, location.search, document.body.classList.contains('editing')]")
                    check(state == ["/upitnik", "", False], f"Upitnik: {state} (path, search, edit mode)")
                    check(pg.locator("#copyToggle").is_visible() and pg.text_content("#copyToggle") == "✎ Uredi tekstove",
                          "staff's upitnik has no ✎ Uredi tekstove pill")
                    check(pg.locator("#mainNav").count() == 1 and pg.evaluate("document.getElementById('adminBtn').classList.contains('on')"),
                          "staff's upitnik lost the bar, or Admin is not .on there")
                    problems += [f"{where} /upitnik {p}" for p in pg.evaluate(PILL)["problems"]]
                    pg.click("#copyToggle"); pg.reload(); pg.wait_for_load_state("networkidle")   # edit mode on, then a reload by hand
                    check(not pg.evaluate("document.body.classList.contains('editing')"), "edit mode outlived a reload by hand")

                if w == 390:
                    pg.tap(".nav-burger")
                    d = pg.evaluate(DRAWER)
                    want = (["# Kao član", *MEMBER_LABELS, "# Admin", *(label for _, label in OWNER_ITEMS)] if staff else
                            ["Početna", "Raspored", "Karton", "Dvoranski treninzi", "Online treninzi", "Moja članarina",
                             "Prehrana"])
                    check(d["shown"] == want, f"the drawer shows {d['shown']}")
                    check(d["hairline"] == ("1px" if staff else None), f"the hairline between its sections: {d['hairline']}")
                    check(d["inside"] and d["overflow"] == 0, f"the drawer leaves the window (overflow {d['overflow']})")
                    if staff:                                              # an item leads to its page, marked as .on is
                        with pg.expect_navigation():
                            pg.tap("#mainNav >> text=Trenutne članarine")
                        pg.wait_for_load_state("networkidle")
                        check(pg.url == server + "/clanarine", f"Trenutne članarine led to {pg.url}")
                        pg.tap(".nav-burger")
                        on = pg.evaluate(DRAWER)["current"]
                        check(on == [["Trenutne članarine", "rgba(255, 255, 255, 0.13)"]], f"the drawer's current row: {on}")

                if not staff:                                              # a client has no editor, whatever the address says
                    go(pg, server + "/upitnik?uredi=1")
                    state = pg.evaluate("[document.body.classList.contains('editing'), !!document.getElementById('copyToggle')]")
                    check(state == [False, False], f"a client's /upitnik?uredi=1: edit mode, editor = {state}")
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
# the widest (seven tabs and Admin ▾), at every width from 901 to 1280px in
# both themes, its seven tabs tight (base.html's rule for seven): at
# 901–935px the avatar left the pill's padding (the page scrolling sideways
# too, up to 914px), from 936px every tab sat on its line inside the pill,
# the brand's slot 87px there (its floor 86.4px, "QMT").
SEVEN_FIT = 936
# and the fold itself: SEVEN_FIT left 0.6px to spare in Chromium on the Mac it
# was measured on, so the bar of seven shows from 960px (Fable's review: room
# for another browser's letter widths)
SEVEN_FOLD = 960


def test_a_bar_of_seven_is_the_drawer_up_to_959px_and_one_row_from_960px(server):
    """Since 27.11.2026 a bar has seven tab links: staff's seven and Admin ▾
    (Dvoranski treninzi joined their row; six and Admin ▾ from 24.11.2026,
    which fitted at every width from 901px), a member's with a gym plan and
    an online plan seven. They do not fit below SEVEN_FIT (936px, measured),
    so a bar of seven (its nav and its ☰, .nav-7) is the ☰ drawer up to
    SEVEN_FOLD − 1 (959px: the fold leaves room past the first fit), as every
    bar is up to 900px. The owner's, at 901, 920, 936 and 959px: the drawer
    (the ☰ shown, the tabs not in the bar), the pill's children inside its
    padding, the page no wider than the window, and the drawer opened shows
    his two sections as a phone's does, inside the window; at 960,
    1024, 1100, 1200 and 1280px the bar: the tabs in it, Dvoranski treninzi
    among them, the pill one row (every child inside its padding and on its
    line, none over another, the avatar's room kept; the tabs on one line,
    none wrapping or cutting its label), the page no wider than the window,
    the wordmark one of its two; in both themes. A client's bar of seven the
    same at 959 and 960px; a client's bar of six (a gym plan, no online
    plan) keeps today's 900px: at 901px a row. No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)                   # the owner, a trainer too
    make_user("ivan@test.local", plans=("grupni", "online"))           # seven tab links
    make_user("ana@test.local", plans=("grupni",))                     # six
    problems: list[str] = []
    admin_labels = [label for _, label in OWNER_ITEMS]
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
            ctx, pg, errors = open_page(browser, server, "trener@test.local", 1280, "/raspored")
            pg.evaluate(f"() => localStorage.setItem('qmt-theme', '{theme}')")
            for w in (901, 920, SEVEN_FIT, SEVEN_FOLD - 1, SEVEN_FOLD, 1024, 1100, 1200, 1280):
                pg.set_viewport_size({"width": w, "height": 900})
                go(pg, server + "/raspored")
                where = f"[owner {theme} {w}px]"
                measure(pg, where, [*MEMBER_LABELS, "Admin ▾"], w < SEVEN_FOLD,
                        ["# Kao član", *MEMBER_LABELS, "# Admin", *admin_labels])
                if pg.evaluate("document.documentElement.getAttribute('data-theme')") != theme:
                    problems.append(f"{where} the page is not in the {theme} theme")
            problems += [f"[owner {theme}] {e}" for e in errors]
            ctx.close()
        client_row = ["Početna", "Raspored", "Karton", "Dvoranski treninzi", "Online treninzi", "Moja članarina", "Prehrana"]
        for email, w, labels, drawer in (("ivan@test.local", SEVEN_FOLD - 1, client_row, True),
                                         ("ivan@test.local", SEVEN_FOLD, client_row, False),
                                         ("ana@test.local", 901, [x for x in client_row if x != "Online treninzi"], False)):
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
    the trainer's Admin ▾ has his five items. No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)                   # the owner, a trainer too
    make_user("coach@test.local", is_trainer=True)                    # a trainer who is not the owner
    problems: list[str] = []
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
                    labels = [t.strip() for t in pg.locator("#adminMenu [role=menuitem]").all_text_contents()]
                    if labels != [label for _, label in TRAINER_ITEMS]:
                        problems.append(f"{where} Admin ▾'s items: {labels}")
                problems += [f"{where} {e}" for e in errors]
                ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


def test_edit_mode_ends_when_the_editor_leaves_the_page(server):
    """Edit mode belongs to the page (26.10.2026, the owner: "I dont exit
    the edit mode when switching tabs"). The trainer turns it on on the
    landing and follows a tab: Raspored is in normal mode; on there, then
    Admin ▾ → Upitnik: normal mode too, and the pill on every page. The
    editor's own forms reload the page and are the one way it outlives a
    load: "+ Dodaj najavu" (a plain submit) and the second tap of "Obriši
    najavu" (form.submit()) bring the landing back in edit mode, the
    one-shot flag spent; a reload by hand then lands in normal mode. On a
    phone (the drawer's rows) and at 1280px (the tabs, the menu); no page
    errors."""
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

            def follow(link: str) -> None:
                """A tab or an Admin item, the way this width reaches it: the
                ☰ drawer on a phone, the Admin menu opened on a desktop."""
                if phone:
                    pg.tap(".nav-burger")
                elif link.startswith("#adminMenu"):
                    pg.click("#adminBtn")
                with pg.expect_navigation():
                    pg.tap(link) if phone else pg.click(link)
                pg.wait_for_load_state("networkidle")

            check(normal("/"), "the landing opens")
            pg.click("#copyToggle")
            check(editing("/"), "the pill pressed")
            follow('#mainNav > a[href="/raspored"]')
            check(normal("/raspored"), "a tab followed in edit mode")
            pg.click("#copyToggle")
            check(editing("/raspored"), "the pill pressed on Raspored")
            follow('#adminMenu a[href="/upitnik"]')
            check(normal("/upitnik"), "Admin ▾ → Upitnik followed in edit mode")
            follow('#mainNav > a[href="/"]')
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
