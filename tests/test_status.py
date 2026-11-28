"""A member's status in one colour (28.11.2026, build 3 of
roadmap/2026-11-28-admin-view-plan.md).

The owner: "I am planning to add also a feature where a user's logo is in a
different color depending on his subscription status (green->active, amber
-> grace period, red->inactive subscription). We can then have a separate
color for the admin logo … The Admin view gets its own color for an admin."
… "Whenever a user is displayed, his name should also be colored in green,
amber or red depending on the subscription status." A member who never had
a plan: "neutral grey is fine"; a word beside the name: "no need for the
extra word for the status"; the strip: "I would recolor the user here as
well, maybe then choose a different color for the 'gledas kao' strip".

ONE rule (models.member_status, over a member's rows and a day): grace
(amber) when a plan of his runs and its payment is due (Membership.is_due,
the test /moja-clanarina's chip "dospijeva" asks), else active (green) when
one runs, else lapsed (red) when he holds a row, else none (grey). A staff
account is admin (the admin's indigo) in the admin view and active in its
member view (app._status_of). A list reads its members' statuses at once
(db.member_statuses, or the rows it read already), never a query per row.
The avatar's fill, his name's colour wherever he is shown (_status.html's
span.st, its words for a screen reader unseen) and the chip come from it.
The "Gledaš kao" strip is a dark bar in both themes, his name on it in his
colour, "Izađi" in the admin's fill; the buttons into a member's account
(.act-kao) wear the admin's tint, amber no longer.

The browser half measures, in both themes, every colour where it stands
(a list's row, the karton's title, the strip, the avatar's initials, the
admin's button, rest and hover) and the lists' overflow at 390 and 360px."""

from __future__ import annotations

import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text as sa_text

from qmt import auth, config, db
from qmt.models import Base, Booking, Membership, User, member_status
from qmt.web.app import app

PORT = 8122    # test_copy's 8111, test_raspored_ui's / test_upitnik_ui's 8112, test_nav's 8113, test_programs' 8114,
               # test_player's 8115, test_karton's 8116, test_kao's 8117, test_gym's 8118, test_spol's 8119,
               # test_dvoranski's 8120, test_predlosci's 8121
BASE_HTML = (Path(__file__).resolve().parents[1] / "src" / "qmt" / "web" / "templates" / "base.html").read_text()
DAY = timedelta(days=1)
# a screen reader's words for each status (_status.html); a staff account's none
WORDS = {"active": ", članarina aktivna", "grace": ", plaćanje dospijeva", "lapsed": ", članarina istekla",
         "none": ", bez članarine"}


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "")
    yield


def make_user(email: str, name: str, is_trainer: bool = False) -> int:
    """A verified account with a complete profile and a phone (no phone
    reminder in the way)."""
    first, _, last = name.partition(" ")
    u = db.create_user(email, first, auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    db.update_profile(u.id, first, last, date(1990, 1, 1), "091 123 4567")
    if is_trainer:
        with db.session_scope() as s:
            s.get(User, u.id).is_trainer = True
    return u.id


def plan(uid: int, kind: str, next_payment: date) -> None:
    """A plan of his whose next payment falls on `next_payment`: its state
    is made by its dates, never by the clock's luck."""
    db.record_payment(uid, kind)
    with db.engine.begin() as conn:
        conn.execute(sa_text("UPDATE memberships SET next_payment = :d WHERE user_id = :u AND plan = :p"),
                     {"d": next_payment, "u": uid, "p": kind})


MEMBERS = {"active": ("ana@test.local", "Ana Kovač"), "grace": ("iva@test.local", "Iva Horvat"),
           "lapsed": ("lea@test.local", "Lea Babić"), "none": ("nina@test.local", "Nina Jurić")}


def people() -> tuple[int, int, dict[str, int]]:
    """(coach, the owner, {status: member}): a trainer who is not the owner,
    the owner (OWNER_EMAIL) who does not train, and a member in each state:
    Ana's grupni paid ahead (active), Iva's grupni due two days ago (its
    grace week), Lea's online lapsed a month ago, Nina with no plan ever."""
    today = config.today()
    coach = make_user("coach@test.local", "Amir Trener", is_trainer=True)
    owner = make_user("trener@test.local", "Tvrtko Vlasnik")
    ids = {status: make_user(email, name) for status, (email, name) in MEMBERS.items()}
    plan(ids["active"], "grupni", today + 20 * DAY)
    plan(ids["grace"], "grupni", today - 2 * DAY)
    plan(ids["lapsed"], "online", today - 30 * DAY)
    return coach, owner, ids


def client_for(email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"email": email, "password": "lozinka123"}, follow_redirects=False)
    assert r.status_code == 303, "login failed"
    return c


def seen(html: str) -> str:
    """A page as a sighted reader has it: every status span (_status.html)
    unwrapped and its words for a screen reader dropped. What a page printed
    before build 3 is this, byte for byte, where a name stands."""
    html = re.sub(r'<span class="st-sr">[^<]*</span>', "", html)
    return re.sub(r'<span class="st st-[a-z]+">([^<]*)</span>', r"\1", html)


def names(html: str) -> list[tuple[str, str, str]]:
    """Every status span of a page, in order: (its status, the name, the
    words a screen reader hears after it; "" for none)."""
    return [(s, unescape(n), unescape(w)) for s, n, w in
            re.findall(r'<span class="st st-([a-z]+)">([^<]*)(?:<span class="st-sr">([^<]*)</span>)?</span>', html)]


def avatar(html: str) -> str | None:
    """The avatar's status class (the account menu's button)."""
    m = re.search(r'id="avatarBtn"\s+class="avatar st-([a-z]+)[" ]', html)
    return m.group(1) if m else None


def head(html: str) -> tuple[str, str, str]:
    """The account menu's head: its circle's status, then the name's
    status span (status, name, words)."""
    who = re.search(r'<div class="who">(.*?)</div>', html, re.S).group(1)
    circle = re.search(r'<span class="who-av st-([a-z]+)" data-theme="dark" aria-hidden="true">', who).group(1)
    [name] = names(who)
    return circle, name


# ---------- the rule ----------

def ms(kind: str, next_payment: date) -> Membership:
    """A membership row, in memory: its plan and when its next payment is."""
    return Membership(plan=kind, paid_on=next_payment - 30 * DAY, next_payment=next_payment)


def test_the_rule_reads_a_members_plans_by_their_dates():
    """models.member_status, pure: none with no row; active while a plan
    runs and nothing is due (the day before next_payment too); grace from
    the day of next_payment itself through dospijeće's (a week later: the
    grace week, still running); lapsed from the day after dospijeće. Several
    plans: one in its grace week and one running is grace (a payment is
    due); one lapsed long ago and one running is active; all lapsed is
    lapsed. Any plan counts, prehrana too. Membership.is_due is the test,
    the chip's: due only while the plan runs. Held on any day of the year,
    a leap day too."""
    for today in (date(2026, 11, 28), date(2026, 1, 1), date(2028, 2, 29), date(2027, 12, 31)):
        def status(*rows):
            return member_status(rows, today)
        assert status() == "none", today
        assert status(ms("grupni", today + 20 * DAY)) == "active"
        assert status(ms("grupni", today + DAY)) == "active"                 # the day before next_payment
        assert status(ms("grupni", today)) == "grace"                        # next_payment's day itself
        assert status(ms("grupni", today - 7 * DAY)) == "grace"              # dospijeće's day: still runs
        assert status(ms("grupni", today - 8 * DAY)) == "lapsed"             # the day after dospijeće
        assert status(ms("grupni", today - 2 * DAY), ms("online", today + 20 * DAY)) == "grace"
        assert status(ms("online", today + 3 * DAY), ms("grupni", today - 400 * DAY)) == "active"
        assert status(ms("grupni", today - 9 * DAY), ms("online", today - 60 * DAY)) == "lapsed"
        assert status(ms("prehrana", today + 5 * DAY)) == "active"
        assert status(ms("prehrana", today - 3 * DAY)) == "grace"
        assert ms("grupni", today).is_due(today) and ms("grupni", today - 7 * DAY).is_due(today)
        assert not ms("grupni", today + DAY).is_due(today) and not ms("grupni", today - 8 * DAY).is_due(today)


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


def test_a_list_reads_its_members_statuses_at_once():
    """db.member_statuses: the statuses of a whole list in ONE statement,
    an id with no row "none", an empty list none at all. And the pages that
    show a list of members (the admin's three lists, Trenutne članarine,
    Korisnici, a termin's roster, the acting record) send as many
    statements for six members as for two: no query per row."""
    coach, owner, ids = people()
    today = config.today()
    every = list(ids.values()) + [coach]
    got = {}
    assert count_queries(lambda: got.update(db.member_statuses(every))) == 1
    assert got == {**{uid: status for status, uid in ids.items()}, coach: "none"}
    assert count_queries(lambda: db.member_statuses([])) == 0
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + DAY, 60, 8, None)
    c = client_for("trener@test.local")

    def statements() -> dict[str, int]:
        paths = ("/kao", "/kartoni", "/dvoranski/clanovi", "/clanarine", "/korisnici", f"/admin/session/{sid}",
                 "/kao/zapisi")
        return {p: count_queries(lambda: c.get(p)) for p in paths}

    def booked_and_acted(uid: int) -> None:
        with db.session_scope() as s:
            s.add(Booking(user_id=uid, session_id=sid))
        assert c.post(f"/kao/{uid}", follow_redirects=False).status_code == 303
        c.post("/kao/izlaz")

    for uid in (ids["active"], ids["grace"]):
        booked_and_acted(uid)
    two = statements()
    for n in range(4):                                              # four more members, each a plan running
        uid = make_user(f"novi{n}@test.local", f"Novi Član{n}")
        plan(uid, "grupni", today + (5 + n) * DAY)
        booked_and_acted(uid)
    assert statements() == two, (two, statements())


# ---------- the places ----------

def test_a_staff_account_is_the_admins_colour_in_the_admin_view_and_active_in_its_member_view():
    """The trainer and the owner (who does not train): in the admin view
    their avatar and the name at its menu's head are the admin's (no words
    for a screen reader: the role is said where it stands); in the member
    view, where a staff account counts as holding every plan, active; back
    in the admin view, the admin's again. In a tab's view of a member the
    bar is the staff member's own: admin. In the whole app the bar is the
    member's: his status."""
    coach, owner, ids = people()
    for email, name in (("coach@test.local", "Amir Trener"), ("trener@test.local", "Tvrtko Vlasnik")):
        c = client_for(email)
        page = c.get("/").text
        assert avatar(page) == "admin" and head(page) == ("admin", ("admin", name, "")), email
        c.post("/pogled", data={"view": "member"})
        page = c.get("/").text
        assert avatar(page) == "active" and head(page) == ("active", ("active", name, WORDS["active"])), email
        c.post("/pogled", data={"view": "admin"})
        assert avatar(c.get("/kartoni").text) == "admin", email
        c.post("/karton/clan", data={"clan": str(ids["grace"]), "natrag": "/kartoni"})
        page = c.get("/karton").text
        assert avatar(page) == "admin" and head(page)[0] == "admin", email           # a tab's view: his own bar
        c.post(f"/kao/izlaz?kao={ids['grace']}")
        c.post(f"/kao/{ids['lapsed']}")
        page = c.get("/karton").text
        assert avatar(page) == "lapsed" and head(page) == ("lapsed", ("lapsed", "Lea Babić", WORDS["lapsed"]))
        c.post(f"/kao/izlaz?kao={ids['lapsed']}")


CHIP = {"active": ["ok"], "grace": ["due"], "lapsed": ["lapsed"], "none": []}


def test_the_avatar_a_name_and_the_chip_never_disagree():
    """One member in each state: his own avatar, his name at the head of his
    menu, his name on the admin's lists, and /moja-clanarina's chip (aktivna
    / dospijeva / istekla / none for no plan) say the same state; the words
    a screen reader hears after his name are its own."""
    coach, owner, ids = people()
    staff = client_for("coach@test.local")
    listed = {name: (status, words) for status, name, words in names(staff.get("/kartoni").text.split("<main")[1])}
    for status, (email, name) in MEMBERS.items():
        c = client_for(email)
        home = c.get("/").text
        assert avatar(home) == status and head(home) == (status, (status, name, WORDS[status])), status
        assert re.findall(r'class="chip ([a-z]+)"', c.get("/moja-clanarina").text) == CHIP[status], status
        assert listed[name] == (status, WORDS[status]), status


def test_every_place_a_member_is_shown_colours_his_name_and_adds_no_visible_word():
    """His name in a span.st.st-<status> with his words for a screen reader
    inside it, and the page as a sighted reader has it exactly what it
    printed before (seen()): the rows of Gledaj kao član, Kartoni and the
    admin's Dvoranski treninzi; Trenutne članarine's members; Korisnici's
    rows (a staff account's name in the admin's colour, no words); a
    termin's roster (a staff member booked: the admin's); the acting record
    ("Tko" the admin's, "Kao koga" his status now, plain once his account is
    gone); the read-only karton's title (the name alone); while staff act as
    him, his karton's and his Dvoranski treninzi's titles and the strip; the
    head of his own menu. The email and the plans beside a name stay as
    they were."""
    coach, owner, ids = people()
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + DAY, 60, 8, None)
    with db.session_scope() as s:
        for uid in (ids["active"], ids["grace"], coach):
            s.add(Booking(user_id=uid, session_id=sid))
    c = client_for("trener@test.local")
    each = [(status, name, WORDS[status]) for status, (_, name) in sorted(MEMBERS.items(), key=lambda x: x[1][1])]
    for path in ("/kao", "/kartoni", "/dvoranski/clanovi"):
        page = c.get(path).text
        assert names(page.split("<main")[1]) == each, path
        for status, (email, name) in MEMBERS.items():
            assert re.search(rf'<div class="kao-who">\s*<strong>{name}</strong>\s*<span class="kao-mail">{email}</span>',
                             seen(page)), (path, name)
    page = c.get("/clanarine").text
    assert sorted(names(page.split("<main")[1])) == sorted(each)
    for status, (email, name) in MEMBERS.items():
        assert f'<strong>{name}</strong><span class="hint">{email}</span>' in seen(page), name
    page = c.get("/korisnici").text
    rows = names(page.split("<main")[1])
    assert sorted(rows) == sorted(each + [("admin", "Amir Trener", ""), ("admin", "Tvrtko Vlasnik", "")])
    assert '<td style="padding:9px 6px;"><strong>Amir Trener</strong></td>' in seen(page)
    page = c.get(f"/admin/session/{sid}").text
    assert names(page.split("<main")[1]) == [("active", "Ana Kovač", WORDS["active"]), ("grace", "Iva Horvat", WORDS["grace"]),
                                             ("admin", "Amir Trener", "")]
    assert '<strong>Iva Horvat</strong><span class="hint">iva@test.local</span>' in seen(page)
    for status in ("lapsed", "none"):
        assert c.get(f"/karton/{ids[status]}").status_code == 200
        page = c.get(f"/karton/{ids[status]}").text
        name = MEMBERS[status][1]
        assert re.search(r"<h1>.*?</h1>", page, re.S).group(0) == \
            f'<h1>Karton — <span class="st st-{status}">{name}<span class="st-sr">{WORDS[status]}</span></span></h1>'
        assert f"<h1>Karton — {name}</h1>" in seen(page)
    # staff acting as Iva (the whole app): the strip, the two titles, her bar
    c.post(f"/kao/{ids['grace']}")
    for path, title in (("/karton", "<h1>Karton — Iva Horvat</h1>"),
                        ("/dvoranski", '<h1><span class="t">Dvoranski treninzi</span> — Iva Horvat</h1>')):
        page = c.get(path).text
        strip = re.search(r'<div class="kao-bar" role="status" data-theme="dark">.*?</div>', page, re.S).group(0)
        assert names(strip) == [("grace", "Iva Horvat", WORDS["grace"])] and "Gledaš kao: <strong>Iva Horvat</strong>" in seen(strip)
        assert title in seen(page) and ("grace", "Iva Horvat", WORDS["grace"]) in names(re.search(r"<h1>.*?</h1>", page).group(0))
        assert head(page) == ("grace", ("grace", "Iva Horvat", WORDS["grace"]))
        assert '<strong>Iva Horvat</strong><span class="mail" title="iva@test.local">iva@test.local</span>' in seen(page)
    c.post(f"/kao/izlaz?kao={ids['grace']}")
    # the record: "Tko" the admin's, "Kao koga" her status now; a member whose account went, plain
    gone = make_user("gone@test.local", "Bivši Član")
    c.post(f"/kao/{gone}")
    c.post(f"/kao/izlaz?kao={gone}")
    with db.engine.begin() as conn:
        conn.execute(sa_text("DELETE FROM users WHERE id = :u"), {"u": gone})
    page = c.get("/kao/zapisi").text
    table = page.split('<table class="kz">')[1].split("</table>")[0]
    assert set(names(table)) == {("admin", "Tvrtko Vlasnik", ""), ("grace", "Iva Horvat", WORDS["grace"])}
    assert '<td class="who">Tvrtko Vlasnik</td>' in seen(table) and '<td class="as">Iva Horvat</td>' in seen(table)
    assert '<td class="as">Bivši Član</td>' in table                    # no account, no colour: the name as it was


def test_the_strip_and_the_buttons_into_an_account_wear_the_admins_colour_not_amber():
    """The strip (.kao-bar) is a dark bar in both themes (data-theme="dark":
    the dark theme's tokens), its words the bar's muted light text, "Izađi"
    in the admin's fill, no amber left in their rules; the buttons into a
    member's account (.act.act-kao: /kao's "Otvori →", Kartoni's "Otvori
    karton →", the admin's Dvoranski treninzi's "Otvori treninge →", a
    roster's "Kao član →", the read-only karton's "Otvori kao član") the
    admin's tint and text, a deeper tint on hover, no amber either. Amber
    keeps its other meanings (the karton's flags, "Nisam bio/la")."""
    def rule(selector: str) -> str:
        m = re.search(rf"^\s*{re.escape(selector)} \{{(.*?)\}}", BASE_HTML, re.S | re.M)
        assert m, selector
        return m.group(1)

    for selector, wants in ((".kao-bar", "background: rgb(22, 22, 24); color: var(--muted);"),
                            (".kao-exit", "background: var(--admin-fill); color: var(--admin-ink);"),
                            (".kao-exit:hover", "var(--admin-fill)"),
                            (".act-kao", "background: var(--admin-soft); color: var(--admin);"),
                            (".act-kao:hover", "color-mix(in srgb, var(--admin) 20%, transparent); color: var(--admin);")):
        body = rule(selector)
        assert "--warn" not in body and wants in body, (selector, body)
    assert ".act-absent" in (Path(__file__).resolve().parents[1] / "src/qmt/web/templates/karton.html").read_text()
    coach, owner, ids = people()
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + DAY, 60, 8, None)
    db.book(ids["active"], sid)
    c = client_for("coach@test.local")
    for path, words, n in (("/kao", "Otvori →", 4), ("/kartoni", "Otvori karton →", 4),
                           ("/dvoranski/clanovi", "Otvori treninge →", 4), (f"/admin/session/{sid}", "Kao član →", 1),
                           (f"/karton/{ids['none']}", "Otvori kao član", 1)):
        page = c.get(path).text
        assert page.count(f'<button type="submit" class="act act-kao">{words}</button>') == n, path
    c.post(f"/kao/{ids['none']}")
    page = c.get("/karton").text
    assert '<div class="kao-bar" role="status" data-theme="dark">' in page
    assert '<form method="post" action="/kao/izlaz"><button type="submit" class="kao-exit">Izađi</button></form>' in page


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


# Contrast as the audit has it (alpha composited from the page up), of every
# element matched: its text as a sighted reader has it (the name without its
# unseen words), its class, its ratio against what it sits on.
MEASURE = r"""sel => {
  const parse = c => { const m = c.match(/[\d.]+/g); if (!m) return null; const k = c.startsWith('color(srgb') ? 255 : 1;
    return {r: +m[0] * k, g: +m[1] * k, b: +m[2] * k, a: m.length > 3 ? parseFloat(m[3]) : 1}; };
  const lum = ({r, g, b}) => { const f = x => { x /= 255; return x <= .03928 ? x / 12.92 : Math.pow((x + .055) / 1.055, 2.4); };
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
  const ground = el => { const chain = []; let n = el; while (n) { chain.push(getComputedStyle(n).backgroundColor); n = n.parentElement; }
    let acc = {r: 255, g: 255, b: 255};
    for (let i = chain.length - 1; i >= 0; i--) { const p = parse(chain[i]); if (!p || p.a === 0) continue;
      acc = {r: p.r * p.a + acc.r * (1 - p.a), g: p.g * p.a + acc.g * (1 - p.a), b: p.b * p.a + acc.b * (1 - p.a)}; }
    return acc; };
  const ratio = (a, b) => { const [h, l] = [lum(a), lum(b)].sort((x, y) => y - x); return (h + .05) / (l + .05); };
  return [...document.querySelectorAll(sel)].map(el => {
    const copy = el.cloneNode(true); copy.querySelectorAll('.st-sr').forEach(x => x.remove());
    return {text: copy.textContent.trim(), cls: String(el.className),
            ratio: +ratio(parse(getComputedStyle(el).color), ground(el)).toFixed(2)}; });
}"""
# the avatar as drawn: its status, its fill, the token its status names (read
# on the avatar itself, dark there in both themes) and its initials' ratio
AVATAR = r"""() => {
  const av = document.getElementById('avatarBtn'), cs = getComputedStyle(av);
  const token = {active: '--good-fill', grace: '--warn', lapsed: '--accent-fill', none: '--muted', admin: '--admin-fill'};
  const status = [...av.classList].find(c => c.startsWith('st-')).slice(3);
  const hex = cs.getPropertyValue(token[status]).trim();
  const rgb = h => 'rgb(' + [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)).join(', ') + ')';
  return {status, fill: cs.backgroundColor, token: rgb(hex)};
}"""
OVERFLOW = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
SEEN_H1 = "() => { const h = document.querySelector('main h1').cloneNode(true); h.querySelectorAll('.st-sr').forEach(x => x.remove()); return h.textContent; }"


def test_the_colours_where_they_stand_in_both_themes(server):
    """In a browser, dark and light: every status colour where a name stands
    (a row of Kartoni on its card, the read-only karton's title on the page,
    the strip over a member's page) and the admin's (a staff row of
    Korisnici, the head of the owner's menu), each at AA or better; each
    avatar's initials on its fill, its fill the token its status names, the
    same in both themes (the bar is dark in both); the admin's tint button,
    at rest and under the pointer. The lists, the record, the roster and a
    member's karton under the strip never scroll sideways at 390 or 360px.
    No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    coach, owner, ids = people()
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + DAY, 60, 8, None)
    for status in ("active", "grace"):
        db.book(ids[status], sid)
    db.record_acting(db.get_user(coach), db.get_user(ids["grace"]), "POST", f"/kao/{ids['grace']}", 303)  # the record's row
    problems: list[str] = []
    fills: dict[str, set[str]] = {}

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for theme, width in (("dark", 390), ("light", 390), ("dark", 1280), ("light", 1280)):
            where = f"[{theme} {width}px]"
            phone = width < 600
            ctx = browser.new_context(viewport={"width": width, "height": 844 if phone else 900},
                                      has_touch=phone, is_mobile=phone)
            pg = ctx.new_page(); errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
            pg.goto(server + "/login")
            pg.evaluate("t => localStorage.setItem('qmt-theme', t)", theme)
            pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); localStorage.setItem('qmt-phone', String(Date.now())); }")
            pg.fill("main input[name=email]", "trener@test.local"); pg.fill("main input[name=password]", "lozinka123")
            pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")

            def go(path: str) -> None:
                pg.goto(server + path); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")

            def wide(what: str) -> None:
                if not phone:
                    return
                for w, h in ((390, 844), (360, 780)):
                    pg.set_viewport_size({"width": w, "height": h})
                    check(pg.evaluate(OVERFLOW) == 0, f"{where} {what} overflows at {w}px by {pg.evaluate(OVERFLOW)}px")
                pg.set_viewport_size({"width": 390, "height": 844})

            go("/kartoni")
            rows = pg.evaluate(MEASURE, ".kao-who .st")
            check(sorted((r["cls"], r["text"]) for r in rows) == sorted((f"st st-{s}", n) for s, (_, n) in MEMBERS.items()),
                  f"{where} Kartoni's names: {rows}")
            check(all(r["ratio"] >= 4.5 for r in rows), f"{where} Kartoni's names: {rows}")
            buttons = pg.evaluate(MEASURE, ".act-kao")
            check(len(buttons) == 4 and all(b["ratio"] >= 4.5 for b in buttons), f"{where} the admin's buttons: {buttons}")
            if not phone:
                pg.hover(".kao-row .act-kao")
                pg.wait_for_timeout(300)                                   # its .15s transition
                [hover] = pg.evaluate(MEASURE, ".kao-row:first-child .act-kao")
                check(hover["ratio"] >= 4.5, f"{where} the admin's button under the pointer: {hover}")
            pg.click("#avatarBtn")
            [mine] = pg.evaluate(MEASURE, ".user-menu .who .st")
            check(mine["cls"] == "st st-admin" and mine["text"] == "Tvrtko Vlasnik" and mine["ratio"] >= 4.5,
                  f"{where} the head of the owner's menu: {mine}")
            [circle] = pg.evaluate(MEASURE, ".user-menu .who-av")
            check(circle["ratio"] >= 4.5, f"{where} the menu's circle: {circle}")
            pg.click("#avatarBtn")
            wide("Kartoni")
            for path in ("/kao", "/dvoranski/clanovi", "/clanarine", "/korisnici", f"/admin/session/{sid}", "/kao/zapisi"):
                go(path)
                shown = pg.evaluate(MEASURE, "main .st")
                check(shown and all(r["ratio"] >= 4.5 for r in shown), f"{where} {path}: {shown}")
                wide(path)
            for status, uid in ids.items():
                go(f"/karton/{uid}")
                [title] = pg.evaluate(MEASURE, "main h1 .st")
                check(title["cls"] == f"st st-{status}" and title["ratio"] >= 4.5, f"{where} the karton's title: {title}")
                check(pg.evaluate(SEEN_H1) == f"Karton — {MEMBERS[status][1]}", f"{where} the title as read: {pg.evaluate(SEEN_H1)!r}")
            go("/")
            a = pg.evaluate(AVATAR)
            [ink] = pg.evaluate(MEASURE, "#avatarBtn")
            check(a["status"] == "admin" and a["fill"] == a["token"] and ink["ratio"] >= 4.5, f"{where} the admin's avatar: {a}, {ink}")
            fills.setdefault("admin", set()).add(a["fill"])
            # each member's app (the whole app): the strip names him in his colour, the bar is his, his avatar his
            for status, uid in ids.items():
                pg.request.post(f"{server}/kao/{uid}")
                go("/karton")
                [name] = pg.evaluate(MEASURE, ".kao-bar .st")
                [words] = pg.evaluate(MEASURE, ".kao-bar .kao-as")
                [exit_] = pg.evaluate(MEASURE, ".kao-exit")
                check(name["cls"] == f"st st-{status}" and name["ratio"] >= 4.5 and words["ratio"] >= 4.5 and exit_["ratio"] >= 4.5,
                      f"{where} the strip over {status}: {name}, {words}, {exit_}")
                bar = pg.evaluate("() => getComputedStyle(document.querySelector('.kao-bar')).backgroundColor")
                check(bar == "rgb(22, 22, 24)", f"{where} the strip's ground: {bar}")
                a = pg.evaluate(AVATAR)
                [ink] = pg.evaluate(MEASURE, "#avatarBtn")
                check(a["status"] == status and a["fill"] == a["token"] and ink["ratio"] >= 4.5,
                      f"{where} {status}'s avatar: {a}, {ink}")
                fills.setdefault(status, set()).add(a["fill"])
                wide(f"{status}'s karton under the strip")
                pg.request.post(f"{server}/kao/izlaz?kao={uid}")
            pg.request.post(server + "/pogled", form={"view": "member"})
            go("/")
            a = pg.evaluate(AVATAR)
            check(a["status"] == "active" and a["fill"] == a["token"], f"{where} the member view's avatar: {a}")
            pg.request.post(server + "/pogled", form={"view": "admin"})
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    # the avatar on the dark bar is the same in both themes
    check(all(len(v) == 1 for v in fills.values()) and len(fills) == 5, f"the avatar's fills by theme: {fills}")
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"
