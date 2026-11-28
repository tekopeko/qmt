"""The tab "Dvoranski treninzi" (27.11.2026, build 2 of
roadmap/2026-11-27-dvoranski-treninzi-plan.md).

The owner: "how long would it take to create a new tab called 'Dvoranski
treninzi' in the same level of hierarchy as the 'Online treninzi' … Maybe it
would make sense for the user to only input in the 'Dvoranski treninzi' tab
but Amir and I can always check the user's Karton?" … "I would show the tab
only to members with a gym plan. Similarly how a online training tab shows
only to members with an online plan."

Who has the tab and its page (app._has_gym: a running plan that books
termini, staff always, while staff act as a member his plans, for the tab and
since 28.11.2026 for the page again, the owner: "This is also only for people
with a gym membership."; from the evening of 27.11.2026 until then the page
whatever his plans); the page's two sections in each of their states:
"Otvoreni treninzi", since that evening everything still being written (the
owner, of "Zadnji treninzi", which went: "remove it, only list the active
trainings which Amir can see always and the user 4 hours before the slot when
the training is confirmed and cant be cancelled"): his booked termini whose
training he may write now (db.gym_open_termini), his trainings outside a
termin with no osvrt (made outside a termin dated yesterday or later, let go
of its termin today or yesterday), and for staff acting as him every later
booked termin however far ahead (db.gym_later_termini: "He can see all booked
slots by the users, no matter how far ahead they are"), since 28.11.2026 in
one order by when they are; none open his next termin or "Nemaš otvorenih
treninga."; "Trening izvan termina" (the Karton's form, moved: POST
/dvoranski/trening and its refusals, who may make one); the way to the karton
at the page's foot; the texts (gym.tab.*). Since 28.11.2026 (the owner: "I
would also like to add an admin privelege where Amir can add a training
outside of the booked slots for a specific user. For example a he adds a
training for a user coming to the gym on his own on a saturday at some time
slot."; and "Will this extra training slot be counted in the subscription
total? It should be counted."): staff acting as a member plan his training up
to 60 days ahead at a time of day, "promijeni datum" moves it with its time,
its page and his diary say when; it counts against a gym plan of his
(gym_trainings.plan, migration a3f6c1e8d47b, there and back): one count for
the paket (db._cycle_used), refused after dospijeće and in a full cycle, a
booking and an add never both taking its last place. And on a phone, at
390px with touch: the tab's page, a training made outside a termin from it,
back to it, and at 1280px the bar with seven tabs; a training planned ahead
as staff in the member's tab, a station written with "Spremi", and the
member's card of it and the station ready to tick. The
nav's half (the tab's place, .on, the drawer, the bar of seven measured) is
tests/test_nav.py's; the karton's (its forms gone, its rows' links)
tests/test_karton.py's and tests/test_gym.py's, and the training's page under
the tab ("← Natrag") tests/test_gym.py's. The search on staff's own tab and
the tab's view of a member it enters are tests/test_kao.py's.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import threading
import time
from datetime import date, datetime, time as dtime, timedelta
from html import unescape
from urllib.parse import unquote

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect, select, text as sa_text
from sqlalchemy.exc import IntegrityError

from qmt import auth, config, copy, db
from qmt.models import SESSION_KINDS, WEEKDAYS, Base, Booking, GymTraining, Membership, User
from qmt.web.app import app

PORT = 8120    # test_copy's 8111, test_raspored_ui's / test_upitnik_ui's 8112, test_nav's 8113, test_programs' 8114,
               # test_player's 8115, test_karton's 8116, test_kao's 8117, test_gym's 8118, test_spol's 8119

GEN = ("ponedjeljka", "utorka", "srijede", "četvrtka", "petka", "subote", "nedjelje")
SHORT = ("pon", "uto", "sri", "čet", "pet", "sub", "ned")
TAB = [k for k in copy.SLOTS if k.startswith("gym.tab.")]
TAB_OPTIONAL = {"gym.tab.lead", "gym.tab.no_plan", "gym.tab.next_opens", "gym.tab.next_hours", "gym.tab.none"}


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # nothing here stores media, but the server thread shares this process's
    # config: never a developer's real R2 bucket (as tests/test_gym.py)
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "")
    yield


def make_user(email: str, is_trainer: bool = False, plans: tuple[str, ...] = ("grupni",)) -> int:
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    db.update_profile(u.id, email.split("@")[0].capitalize(), "Test", date(1990, 1, 1), "")
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


def location(r) -> str:
    """A redirect's location as a person reads it ("+" a space)."""
    return unquote(r.headers["location"]).replace("+", " ")


def now() -> datetime:
    return datetime.now(config.TZ)


def termin(uid: int | None, starts: datetime, title: str = "Grupni trening") -> int:
    """A one-off termin at `starts`, booked by `uid` (directly: book()
    refuses a past one); its id."""
    sid = db.add_oneoff_session(title, starts, 60, 8, None)
    if uid is not None:
        with db.session_scope() as s:
            s.add(Booking(user_id=uid, session_id=sid))
    return sid


def lapse(uid: int) -> None:
    """Every plan of his past its dospijeće (the grace week over)."""
    with db.session_scope() as s:
        for m in s.scalars(select(Membership).where(Membership.user_id == uid)):
            m.next_payment = config.today() - timedelta(days=Membership.GRACE_DAYS + 1)


def station(tid: int, uid: int, name: str, staff: bool = True) -> int:
    """A Stanica of a new exercise after the training's last block: its id."""
    bid = db.add_gym_block(tid, uid, "stanica", staff=staff)
    db.set_gym_station(bid, uid, db.create_exercise(f"{name} {tid}-{bid}"), 3, 10, staff=staff)
    return bid


def bare(html: str) -> str:
    """A page with its texts' spans unwrapped (every text a copy slot)."""
    return re.sub(r'<span class="(?:ed )?t"[^>]*>(.*?)</span>', r"\1", html, flags=re.S)


def shown(html: str) -> str:
    """What a reader sees of some markup: the tags gone, the spaces folded."""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def tabs(page: str) -> list[str]:
    """The nav's tab labels, in order."""
    start = re.search(r'<nav class="nav(?: nav-7)?" id="mainNav">', page).start()
    return re.findall(r'^\s*<a href="[^"]+" class="(?:on|)">([^<]+)</a>', page[start:page.index("</nav>", start)], re.M)


def main_of(page: str) -> str:
    return page.split("<main", 1)[1].split("</main>", 1)[0]


def section(page: str, h2: str) -> str:
    """A section of the tab's page, by its heading's id (dv-open-h,
    dv-new-h), to its end."""
    return page.split(f'aria-labelledby="{h2}"')[1].split("</section>")[0]


def cards(page: str) -> list[tuple[str, str]]:
    """The cards of "Otvoreni treninzi", in order: (their id, their markup)."""
    return re.findall(r'<article class="card dv-open" id="([^"]+)">(.*?)</article>', section(page, "dv-open-h"), re.S)


def when_text(at: datetime) -> str:
    """A termin's start as an open card says it, "srijeda 25.11.2026. · 18:00"."""
    at = at.astimezone(config.TZ)
    return f"{WEEKDAYS[at.weekday()]} {at.day}.{at.month}.{at.year}. · {at:%H:%M}"


def until_text(at: datetime) -> str:
    """Its window's end as the state line says it, "četvrtka 26.11. u ponoć"."""
    day = at.astimezone(config.TZ).date() + timedelta(days=1)
    return f"{GEN[day.weekday()]} {day.day}.{day.month}. u ponoć"


GATE = '<div class="card dv-gate"><p><strong><span class="t">Dvoranski treninzi su dio članarine za dvoranu.</span></strong></p></div>'
# the gate as staff acting as such a member read it (28.11.2026): their sentence under the member's
STAFF_GATE = ('<div class="card dv-gate"><p><strong><span class="t">Dvoranski treninzi su dio članarine za dvoranu.'
              '</span></strong></p><p class="hint dv-gate-staff">Član nema aktivnu članarinu za dvoranu, pa mu se '
              'trening ne može dodati.</p></div>')
SECTIONS = ('aria-labelledby="dv-open-h"', 'aria-labelledby="dv-new-h"')
FOOT = '<a class="act act-quiet dv-all" href="/karton#osvrti"><span class="t">Svi tvoji treninzi su u kartonu →</span></a>'


def day_text(d: date) -> str:
    """A day as a training outside a termin's card and page say it, "subota 5.12.2026."."""
    return f"{WEEKDAYS[d.weekday()]} {d.day}.{d.month}.{d.year}."


def counted(plan_label: str, cls: str) -> str:
    """The line of a training staff made against a gym plan (28.11.2026), on
    the tab's card (dv-plan) or its page (gt-state)."""
    return f'<p class="{cls}"><span class="t">Broji se u članarinu:</span> {plan_label}.</p>'


def cycle_text(start: date, end: date) -> str:
    """A cycle as book()'s refusal words it: "1.5.–31.5." (its last day, end − 1)."""
    last = end - timedelta(days=1)
    return f"{start.day}.{start.month}.–{last.day}.{last.month}."


def plan_due(uid: int, plan: str, next_payment: date, sessions: int | None) -> None:
    """Pin a plan's next_payment and paket (test_booking.py's _due): its
    cycle [next_payment − 1 mj, next_payment), dospijeće 7 days after it."""
    with db.session_scope() as s:
        m = s.scalar(select(Membership).where(Membership.user_id == uid, Membership.plan == plan))
        m.next_payment, m.sessions_per_cycle = next_payment, sessions


def booked_at(uid: int, *days: date) -> list[int]:
    """A group termin booked by `uid` at 10:00 on each day (directly, as
    termin() books): the paket's places they take."""
    return [termin(uid, datetime.combine(d, dtime(10, 0), tzinfo=config.TZ)) for d in days]


def staff_add(c: TestClient, uid: int, day: date, at: str = "", plan: str = "grupni"):
    """Staff acting as `uid` post the tab's form (the page's marker as base.html's script adds it)."""
    return c.post(f"/dvoranski/trening?kao={uid}", data={"day": day.isoformat(), "time": at, "plan": plan},
                  follow_redirects=False)


def made_id(r) -> int:
    """The training a form made: its page, where the redirect leads."""
    assert location(r).startswith("/dvoranski/trening/"), location(r)
    return int(location(r).rsplit("/", 1)[1])


# ---------- who has the tab and the page ----------

def test_the_tab_and_its_page_follow_a_plan_that_books_termini():
    """The tab, after Karton and before Online treninzi, and its page with
    its two sections and the way to the karton at its foot: a member with
    each of the four plans that book termini (grupni, individualni,
    poluindividualni, rehabilitacija) and staff, the trainer and the owner
    (no plan of theirs; since 28.11.2026 in their member view, which their
    own /dvoranski, a member page, takes them to: the bar is read after it).
    No tab, and the page the gate's one sentence
    ("Dvoranski treninzi su dio članarine za dvoranu.", /treninzi's way for
    one with no online plan, no section, no form): an online plan alone, no
    plan, a gym plan lapsed. A guest is sent to log in. Staff acting as a
    member (the whole app): his plans decide the tab and the page, his open
    termin there with a gym plan; with none his gate, and under it one
    sentence of theirs (since 28.11.2026, the owner: "This is also only for
    people with a gym membership."; from the evening of 27.11.2026 until
    then his page whatever his plans), which the member never reads."""
    members = {plan: make_user(f"{plan}@test.local", plans=(plan,)) for plan in SESSION_KINDS}
    make_user("mia@test.local", plans=("online",))
    sara = make_user("sara@test.local", plans=())
    lapsed = make_user("lara@test.local", plans=("grupni", "online"))
    lapse(lapsed)
    make_user("coach@test.local", is_trainer=True, plans=())
    make_user("trener@test.local", plans=())                                # the owner, not a trainer
    for email in [f"{plan}@test.local" for plan in SESSION_KINDS] + ["coach@test.local", "trener@test.local"]:
        c = client_for(email)
        page = c.get("/dvoranski").text                 # a member page: a staff account's member view from here on
        assert "Dvoranski treninzi" in tabs(page) and "Dvoranski treninzi" in tabs(c.get("/raspored").text), email
        assert all(mark in page for mark in SECTIONS) and 'class="card dv-gate"' not in page, email
        assert '<h1><span class="' in page and "<title>Dvoranski treninzi — QMT</title>" in page, email
        assert 'aria-labelledby="dv-last-h"' not in page and "Zadnji treninzi" not in page, email   # gone (27.11.2026)
        assert 'href="/karton#osvrti"' in main_of(page).split('id="trening-novi"')[1], email        # at the foot
    row = tabs(client_for("grupni@test.local").get("/raspored").text)
    assert row[row.index("Karton") + 1] == "Dvoranski treninzi"
    coach = client_for("coach@test.local")
    assert "Dvoranski treninzi" not in tabs(coach.get("/raspored").text)     # the admin view's bar: its three menus
    staff_row = tabs(coach.get("/dvoranski").text)                           # his member view: a member's seven
    assert staff_row.index("Dvoranski treninzi") == staff_row.index("Karton") + 1 == staff_row.index("Online treninzi") - 1
    for email in ("mia@test.local", "sara@test.local", "lara@test.local"):
        c = client_for(email)
        assert "Dvoranski treninzi" not in tabs(c.get("/raspored").text), email
        r = c.get("/dvoranski")
        assert r.status_code == 200 and GATE in r.text, email
        assert not any(mark in r.text for mark in SECTIONS) and 'action="/dvoranski/trening"' not in r.text, email
        assert '<h1><span class="t">Dvoranski treninzi</span></h1>' in r.text, email
    r = TestClient(app).get("/dvoranski", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/login?next=/dvoranski")

    ivan = members["grupni"]
    sid = termin(ivan, now() - timedelta(hours=1), title="Snaga")
    cs = client_for("coach@test.local")
    assert cs.post(f"/kao/{ivan}", follow_redirects=False).status_code == 303
    page = cs.get("/dvoranski").text
    assert "Dvoranski treninzi" in tabs(page) and all(mark in page for mark in SECTIONS)
    assert f'href="/dvoranski/termin/{sid}"' in section(page, "dv-open-h")
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    cs.post(f"/kao/{sara}")
    page = cs.get("/dvoranski").text
    assert "Dvoranski treninzi" not in tabs(page) and f'data-kao="{sara}"' in page   # her plans: no tab
    assert STAFF_GATE in page and not any(mark in page for mark in SECTIONS)        # her gate, staff's sentence
    assert 'action="/dvoranski/trening"' not in page
    hers = client_for("sara@test.local").get("/dvoranski").text
    assert GATE in hers and "Član nema aktivnu članarinu" not in hers              # hers: the gate alone
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(sara)})
    assert all(mark in cs.get("/dvoranski").text for mark in SECTIONS)        # his own again


# ---------- "Otvoreni treninzi" ----------

def test_the_open_trainings_are_his_termini_whose_training_he_may_write_now():
    """"Otvoreni treninzi": his booked termini whose training is his to
    write now (from 4 h before the termin to the end of the day after it,
    the termin not canceled), the soonest first, a card each: the termin's
    title, its date and time in 700, the training page's state line ("Upis
    je otvoren do …"), what it holds ("1 vježba"; nothing while it holds no
    exercise) and ONE button: "Upiši trening" while it holds no block (no
    training yet, or one opened and left empty), else "Nastavi trening",
    → /dvoranski/termin/<id> (which makes the training the first time it is
    opened). Not there: a termin further ahead than 4 h, one past its
    window, a canceled one, another member's."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    db.reset_gym_templates()
    at = {k: (now() + delta).replace(second=0, microsecond=0) for k, delta in (
        ("yesterday", timedelta(days=-1)), ("ended", timedelta(hours=-2)), ("soon", timedelta(hours=3)),
        ("later", timedelta(hours=6)), ("old", timedelta(days=-3)), ("off", timedelta(hours=-1)))}
    sids = {k: termin(ivan, v, title=f"Termin {k}") for k, v in at.items()}
    db.set_session_canceled(sids["off"], True)
    theirs = termin(ana, at["ended"], title="Anin termin")
    started = db.gym_training_for(ivan, sids["yesterday"], staff=True)      # a Stanica of an exercise: it holds one
    station(started, ivan, "Goblet čučanj")
    empty = db.gym_training_for(ivan, sids["soon"])                          # opened, a template applied: no exercise
    db.apply_gym_template(empty, ivan, db.gym_templates()[0].id)
    ci = client_for("ivan@test.local")
    sec = section(ci.get("/dvoranski").text, "dv-open-h")
    cards = re.findall(r'<article class="card dv-open" id="dv-s-(\d+)">(.*?)</article>', sec, re.S)
    assert [int(k) for k, _ in cards] == [sids["yesterday"], sids["ended"], sids["soon"]]     # the soonest first
    body = {int(k): v for k, v in cards}
    for key, button, holds in (("yesterday", "Nastavi trening", "1 vježba"), ("ended", "Upiši trening", None),
                               ("soon", "Nastavi trening", None)):
        card, sid = body[sids[key]], sids[key]
        assert f"<h3>Termin {key}</h3>" in card, key
        assert f'<p class="dv-when">{when_text(at[key])}</p>' in card, key
        assert f'<p class="dv-state"><span class="t">Upis je otvoren do</span> {until_text(at[key])}.</p>' in card, key
        assert (f'<a class="btn btn-sm dv-go" href="/dvoranski/termin/{sid}"><span class="t">{button}</span></a>'
                in card), key
        assert (f'<p class="dv-holds">{holds}</p>' in card) if holds else 'class="dv-holds"' not in card, key
    for key in ("later", "old", "off"):
        assert f'id="dv-s-{sids[key]}"' not in sec and f"/dvoranski/termin/{sids[key]}" not in sec, key
    assert f"/dvoranski/termin/{theirs}" not in sec and "Anin termin" not in sec
    r = ci.get(f"/dvoranski/termin/{sids['ended']}", follow_redirects=False)  # its way in makes the training
    made = [t for t in db.gym_trainings(ivan) if t.session_id == sids["ended"]]
    assert len(made) == 1 and location(r) == f"/dvoranski/trening/{made[0].id}"
    assert "Nemaš otvorenih treninga." not in sec and "Sljedeći termin:" not in sec


def test_none_open_says_his_next_termin_or_that_there_is_none():
    """No training open: one muted line. His next booked termin when he has
    one (a canceled one skipped), "Sljedeći termin: <title>, <day> u <time>
    — upis se otvara 4 h prije." (the hours config's); its words around the
    hours emptied, the line ends at the time, no number. With none,
    "Nemaš otvorenih treninga." and its link to the raspored; staff's page
    too (they book none)."""
    make_user("trener@test.local", is_trainer=True, plans=())
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    ahead = (now() + timedelta(days=2)).replace(hour=18, minute=0, second=0, microsecond=0)
    off = termin(ivan, ahead - timedelta(hours=20), title="Otkazani")
    db.set_session_canceled(off, True)
    termin(ivan, ahead, title="Snaga")
    termin(ivan, ahead + timedelta(days=1), title="Mobilnost")
    day = f"{SHORT[ahead.weekday()]} {ahead.day}.{ahead.month}."
    line = (f'<p class="hint dv-none"><span class="t">Sljedeći termin:</span> Snaga, {day} u 18:00 '
            '<span class="t">— upis se otvara</span> 4 <span class="t">h prije.</span></p>')
    sec = section(client_for("ivan@test.local").get("/dvoranski").text, "dv-open-h")
    assert line in sec and "dv-open" not in sec.replace("dv-open-h", "") and "Otkazani" not in sec
    assert shown(line) == f"Sljedeći termin: Snaga, {day} u 18:00 — upis se otvara 4 h prije."
    none = ('<p class="hint dv-none"><span class="t">Nemaš otvorenih treninga.</span> '
            '<a class="tlink" href="/raspored"><span class="t">Raspored →</span></a></p>')
    assert none in section(client_for("ana@test.local").get("/dvoranski").text, "dv-open-h")
    t = client_for("trener@test.local")
    assert shown(none) in shown(section(t.get("/dvoranski").text, "dv-open-h"))
    for key in ("gym.tab.next_opens", "gym.tab.next_hours"):
        assert t.post(f"/copy/{key}", data={"text": ""}).json()["text"] == "", key
    sec = section(client_for("ivan@test.local").get("/dvoranski").text, "dv-open-h")
    assert f'<p class="hint dv-none"><span class="t">Sljedeći termin:</span> Snaga, {day} u 18:00</p>' in sec


# ---------- "Trening izvan termina" ----------

def test_a_training_outside_a_termin_is_made_on_the_tab():
    """The Karton's form of 26.11.2026, moved (27.11.2026): Datum (today by
    default, never after it, not before 2020) and "Dodaj trening" → POST
    /dvoranski/trening → the new training's page (no session, no title, no
    start, that date; its template chooser). A date in the future, before
    2020-01-01, empty or no date makes nothing: back at the form
    (#trening-novi), "Neispravan datum." in its section, not at the page's
    top. The member's form is the day alone (no time, no plan: those are
    staff's, 28.11.2026), and a time or a plan he posts is ignored. Made by
    a member with a gym plan and by staff for themselves; anyone else is
    turned away to the tab, which shows him the gate, nothing made (an
    online plan alone, a gym plan lapsed), and since 28.11.2026 so are staff
    acting as a member with no gym plan (the record holding the write; from
    the evening of 27.11.2026 until then the actor decided: the owner, "This
    is also only for people with a gym membership."); a guest to the login."""
    ivan = make_user("ivan@test.local")
    mia = make_user("mia@test.local", plans=("online",))
    lara = make_user("lara@test.local")
    lapse(lara)
    sara = make_user("sara@test.local", plans=())
    coach = make_user("coach@test.local", is_trainer=True, plans=())
    ci, today = client_for("ivan@test.local"), config.today()
    form = " ".join(section(ci.get("/dvoranski").text, "dv-new-h").split())
    assert '<form class="dv-form" method="post" action="/dvoranski/trening">' in form
    assert '<label for="dv-day"><span class="t">Datum</span></label>' in form
    assert (f'<input id="dv-day" type="date" name="day" value="{today.isoformat()}" '
            f'min="2020-01-01" max="{today.isoformat()}" required>') in form
    assert '<button type="submit" class="btn btn-sm"><span class="t">Dodaj trening</span></button>' in form
    assert 'name="time"' not in form and 'name="plan"' not in form and "Članarina" not in form   # staff's alone
    assert 'id="trening-novi"' in ci.get("/dvoranski").text
    for day in ((today + timedelta(days=1)).isoformat(), "2019-12-31", "", "23.11.2026", "2026-02-30"):
        r = ci.post("/dvoranski/trening", data={"day": day}, follow_redirects=False)
        assert location(r) == "/dvoranski?error=Neispravan datum.#trening-novi", day
    assert db.gym_trainings(ivan) == []
    page = ci.get("/dvoranski?error=Neispravan datum.").text
    assert ('<div class="alert" role="alert"><span>Neispravan datum.</span></div>'
            in section(page, "dv-new-h")) and main_of(page).count('class="alert"') == 1
    r = ci.post("/dvoranski/trening", data={"day": "2021-03-04", "time": "10:00", "plan": "grupni"},
                follow_redirects=False)                                     # his time and plan: ignored
    [t] = db.gym_trainings(ivan)
    assert location(r) == f"/dvoranski/trening/{t.id}"
    assert (t.session_id, t.title, t.starts_at, t.held_on, t.plan) == (None, "", None, date(2021, 3, 4), None)
    assert 'class="card pl-card gt-chooser"' in ci.get(location(r)).text
    for email, uid in (("mia@test.local", mia), ("lara@test.local", lara), ("sara@test.local", sara)):
        r = client_for(email).post("/dvoranski/trening", data={"day": today.isoformat()}, follow_redirects=False)
        assert location(r) == "/dvoranski" and db.gym_trainings(uid) == [], email
    cs = client_for("coach@test.local")
    r = cs.post("/dvoranski/trening", data={"day": today.isoformat()}, follow_redirects=False)
    [mine] = db.gym_trainings(coach)
    assert location(r) == f"/dvoranski/trening/{mine.id}" and mine.held_on == today
    cs.post(f"/kao/{sara}")                                                 # acting as one with no gym plan: refused
    r = staff_add(cs, sara, today)
    assert location(r) == "/dvoranski" and db.gym_trainings(sara) == []
    rows, _ = db.acting_log()
    assert (rows[0].method, rows[0].path, rows[0].member_id, rows[0].status) == ("POST", "/dvoranski/trening", sara, 303)
    r = TestClient(app).post("/dvoranski/trening", data={"day": today.isoformat()}, follow_redirects=False)
    assert r.headers["location"].startswith("/login")


# ---------- what is still being written ----------

def test_a_training_saved_or_deleted_lands_on_the_tab_of_a_viewer_who_has_it():
    """"← Natrag" leads to the tab, and so do the two ends of a training:
    its osvrt saved ("Trening je spremljen.") and a training outside a
    termin deleted ("Trening je obrisan."). A termin's training saved in its
    window stays open there, its card saying its napor among its facts;
    one outside a termin, its osvrt saved, is no longer on the tab (it is
    in the karton alone). A viewer with no tab (his gym plan lapsed) lands
    where build 1 sent everyone: the karton, at the training's diary row or
    at the diary."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    ci, ca = client_for("ivan@test.local"), client_for("ana@test.local")
    sid = termin(ivan, now() - timedelta(hours=2), title="Snaga")
    ttid = db.gym_training_for(ivan, sid)
    station(ttid, ivan, "Goblet čučanj", staff=False)
    made = {}
    for c, uid in ((ci, ivan), (ca, ana)):
        tid = db.add_gym_outside(uid, config.today())
        station(tid, uid, "Plank", staff=False)
        made[uid] = (tid, db.add_gym_outside(uid, config.today()))
    lapse(ana)
    tid, spare = made[ivan]
    assert f'id="dv-gt-{tid}"' in section(ci.get("/dvoranski").text, "dv-open-h")   # open while no osvrt
    r = ci.post(f"/dvoranski/trening/{tid}/osvrt", data={"effort": "7"}, follow_redirects=False)
    assert location(r) == "/dvoranski?ok=Trening je spremljen."
    page = ci.get(r.headers["location"]).text
    assert '<div class="alert ok" role="status">Trening je spremljen.</div>' in page
    assert f'id="dv-gt-{tid}"' not in page and f'href="/dvoranski/trening/{tid}"' not in page   # the karton's alone
    r = ci.post(f"/dvoranski/trening/{ttid}/osvrt", data={"effort": "8", "feeling": "dobro"}, follow_redirects=False)
    assert location(r) == "/dvoranski?ok=Trening je spremljen."
    card = dict(cards(ci.get(r.headers["location"]).text))[f"dv-s-{sid}"]
    assert '<p class="dv-holds">1 vježba · napor 8/10 · Dobro</p>' in card and "Nastavi trening" in card
    r = ci.post(f"/dvoranski/trening/{spare}/obrisi", follow_redirects=False)
    assert location(r) == "/dvoranski?ok=Trening je obrisan."
    assert '<div class="alert ok" role="status">Trening je obrisan.</div>' in ci.get(r.headers["location"]).text
    tid, spare = made[ana]                                              # no tab: the karton
    r = ca.post(f"/dvoranski/trening/{tid}/osvrt", data={"effort": "7"}, follow_redirects=False)
    assert location(r) == f"/karton?ok=Trening je spremljen.#gt-{tid}"
    r = ca.post(f"/dvoranski/trening/{spare}/obrisi", follow_redirects=False)
    assert location(r) == "/karton?ok=Trening je obrisan.#osvrti"


def test_a_training_outside_a_termin_is_open_today_and_yesterday_until_its_osvrt():
    """"Otvoreni treninzi" holds, with his open termini, every training of
    his outside a termin that is still being written: no osvrt saved, held
    today or yesterday (the termin's own rule, "until the end of the day
    after it"; one made outside a termin later too since 28.11.2026: the
    planned ones' test below), since 28.11.2026 every card in one order by
    when it is (a time, else its day's start; two at one moment as they
    were made; "the newest first" until then); a card each (id
    dv-gt-<training>): "Trening izvan termina" (or, let go of its termin by
    a cancelled booking, the title it kept), its date (with its time for one
    that kept its start), what it holds, and "Upiši trening" while it holds
    no block, else "Nastavi trening", → its page. Not there: one held two
    days back, one whose osvrt is saved (the karton's alone), another
    member's. "Zadnji
    treninzi" is gone, its three texts out of the registry; with nothing
    open the line under the heading says so as before, and the way to the
    karton is at the page's foot."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    db.reset_gym_templates()
    today = config.today()
    blank = db.add_gym_outside(ivan, today)                                # no block yet: Upiši trening
    started = db.add_gym_outside(ivan, today - timedelta(days=1))          # a Stanica: Nastavi trening
    station(started, ivan, "Plank")
    shaped = db.add_gym_outside(ivan, today)                               # a template's blocks, no exercise
    db.apply_gym_template(shaped, ivan, db.gym_templates()[0].id)
    old = db.add_gym_outside(ivan, today - timedelta(days=2))
    done = db.add_gym_outside(ivan, today)
    db.finish_gym_training(done, ivan, 7, None, "")
    # a termin's training that holds a set, let go of its termin as a
    # cancelled booking lets one go (rule 3: the booking goes, the training
    # stays, no termin's now): its title and start kept, today
    sid = termin(ivan, datetime.combine(today, dtime(0, 30), tzinfo=config.TZ), title="Mobilnost")
    let_go = db.gym_training_for(ivan, sid, staff=True)
    db.save_gym_done(station(let_go, ivan, "Sklekovi"), ivan, [{"reps": 10, "kg": 0.0}], staff=True)
    with db.session_scope() as s:
        s.get(GymTraining, let_go).session_id = None
        s.delete(s.scalar(select(Booking).where(Booking.user_id == ivan, Booking.session_id == sid)))
    hers = db.add_gym_outside(ana, today)
    ci = client_for("ivan@test.local")
    page = ci.get("/dvoranski").text
    # by when they are: yesterday's, today's two with no time (its day's start; as made), then the
    # one that kept its termin's start, today at 00:30
    assert [k for k, _ in cards(page)] == [f"dv-gt-{started}", f"dv-gt-{blank}", f"dv-gt-{shaped}", f"dv-gt-{let_go}"]
    body = dict(cards(page))
    for tid, button, holds in ((blank, "Upiši trening", None), (shaped, "Nastavi trening", None),
                               (started, "Nastavi trening", "1 vježba"), (let_go, "Nastavi trening", "1 vježba")):
        card = body[f"dv-gt-{tid}"]
        assert f'<a class="btn btn-sm dv-go" href="/dvoranski/trening/{tid}"><span class="t">{button}</span></a>' in card, tid
        assert (f'<p class="dv-holds">{holds}</p>' in card) if holds else 'class="dv-holds"' not in card, tid
        assert 'class="dv-state"' not in card, tid                          # always his to write: no state line
    y = today - timedelta(days=1)
    assert '<h3><span class="t">Trening izvan termina</span></h3>' in body[f"dv-gt-{blank}"]
    assert f'<p class="dv-when">{WEEKDAYS[today.weekday()]} {today.day}.{today.month}.{today.year}.</p>' in body[f"dv-gt-{blank}"]
    assert f'<p class="dv-when">{WEEKDAYS[y.weekday()]} {y.day}.{y.month}.{y.year}.</p>' in body[f"dv-gt-{started}"]
    assert "<h3>Mobilnost</h3>" in body[f"dv-gt-{let_go}"] and " · " in body[f"dv-gt-{let_go}"].split("dv-when")[1]
    for gone in (old, done, hers):
        assert f'id="dv-gt-{gone}"' not in page and f'href="/dvoranski/trening/{gone}"' not in page, gone
    assert "Nemaš otvorenih treninga." not in page and FOOT in page
    for key in ("gym.tab.last_title", "gym.tab.last_open", "gym.tab.last_empty"):
        assert key not in copy.SLOTS, key
    assert "Zadnji treninzi" not in page and 'class="dv-row"' not in page
    db.finish_gym_training(hers, ana, 6, None, "")                          # hers saved: nothing open for her
    page = client_for("ana@test.local").get("/dvoranski").text
    assert cards(page) == [] and "Nemaš otvorenih treninga." in section(page, "dv-open-h") and FOOT in page


# ---------- staff acting as a member (27.11.2026, evening) ----------

def opens_text(starts: datetime) -> str:
    """When a termin's training opens for its member, as staff read it:
    "Članu se otvara u petak 28.11. u 14:00." (4 h before: the cancel deadline)."""
    acc = ("ponedjeljak", "utorak", "srijedu", "četvrtak", "petak", "subotu", "nedjelju")
    at = (starts - timedelta(hours=config.CANCEL_CUTOFF_HOURS)).astimezone(config.TZ)
    return f"Članu se otvara u {acc[at.weekday()]} {at.day}.{at.month}. u {at:%H:%M}."


def test_staff_acting_as_a_member_see_every_booked_termin_however_far_ahead():
    """The owner: "He can see all booked slots by the users, no matter how
    far ahead they are". Staff acting as ivan (the whole app, and a tab's
    view alike) see his open termin as he does, then every later booked
    termin of his, not canceled, the soonest first (three weeks ahead too),
    a card each (dv-s-<termin>): its title, its date and time, in the state
    line's place when it opens for him ("Članu se otvara u … u 14:00."), and
    ONE button, "Pripremi trening" while it holds no block, "Nastavi trening"
    once it does, → /dvoranski/termin/<id>, which makes the training before
    his window (rule 1: staff write at any time). The member himself sees
    none of the later ones. Canceled termini, another member's: nowhere."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    db.reset_gym_templates()
    at = {k: (now() + delta).replace(second=0, microsecond=0) for k, delta in (
        ("open", timedelta(hours=-1)), ("tomorrow", timedelta(days=1)), ("week", timedelta(days=7)),
        ("far", timedelta(days=21)), ("off", timedelta(days=3)))}
    sids = {k: termin(ivan, v, title=f"Termin {k}") for k, v in at.items()}
    db.set_session_canceled(sids["off"], True)
    theirs = termin(ana, at["tomorrow"], title="Anin termin")
    own = [k for k, _ in cards(client_for("ivan@test.local").get("/dvoranski").text)]
    assert own == [f"dv-s-{sids['open']}"]                                 # the member: his open one alone
    cs = client_for("coach@test.local")
    assert cs.post(f"/kao/{ivan}", follow_redirects=False).status_code == 303
    page = cs.get("/dvoranski").text
    assert [k for k, _ in cards(page)] == [f"dv-s-{sids[k]}" for k in ("open", "tomorrow", "week", "far")]
    body = dict(cards(page))
    assert '<span class="t">Upis je otvoren do</span>' in body[f"dv-s-{sids['open']}"]   # as he sees it
    for key in ("tomorrow", "week", "far"):
        card, sid = body[f"dv-s-{sids[key]}"], sids[key]
        assert f"<h3>Termin {key}</h3>" in card and f'<p class="dv-when">{when_text(at[key])}</p>' in card, key
        assert f'<p class="dv-state">{opens_text(at[key])}</p>' in card, key
        assert f'<a class="btn btn-sm dv-go" href="/dvoranski/termin/{sid}">Pripremi trening</a>' in card, key
    assert "Termin off" not in page and "Anin termin" not in page and f'href="/dvoranski/termin/{theirs}"' not in page
    r = cs.get(f"/dvoranski/termin/{sids['far']}", follow_redirects=False)   # prepared three weeks ahead
    [made] = [t for t in db.gym_trainings(ivan) if t.session_id == sids["far"]]
    assert location(r) == f"/dvoranski/trening/{made.id}"
    assert "Za člana je upis zatvoren; uređuješ kao trener." in cs.get(location(r)).text
    station(made.id, ivan, "Goblet čučanj")
    card = dict(cards(cs.get("/dvoranski").text))[f"dv-s-{sids['far']}"]
    assert ('<a class="btn btn-sm dv-go" href="/dvoranski/termin/'
            f'{sids["far"]}"><span class="t">Nastavi trening</span></a>') in card and '<p class="dv-holds">1 vježba</p>' in card
    r = client_for("ivan@test.local").get(f"/dvoranski/termin/{sids['tomorrow']}", follow_redirects=False)
    assert location(r) == "/karton?error=Trening se otvara 4 h prije termina."   # the member: not before his window
    assert [k for k, _ in cards(client_for("ivan@test.local").get("/dvoranski").text)] == [f"dv-s-{sids['open']}"]


def test_a_member_with_no_gym_plan_gets_the_gate_for_staff_too():
    """The owner, 28.11.2026: "This is also only for people with a gym
    membership." A member with no gym plan running (sara: none; lara: her
    grupni lapsed) gets the gate's sentence, no section, no form; so do
    staff acting as her, either way in (the whole app, a tab's view), with
    one sentence of theirs under it, "Član nema aktivnu članarinu za
    dvoranu, pa mu se trening ne može dodati."; and POST /dvoranski/trening
    refuses for her whoever posts it: back to the tab, nothing made. (From
    the evening of 27.11.2026 until then staff got her page and the form:
    the actor decided.) What she has stays hers to reach and write by its
    links (rule 1 as it was): staff still prepare a booked termin's training
    of hers (her booking decides, rule 2), a training of hers outside a
    termin takes a block and its osvrt; "← Natrag" and the osvrt's save lead
    where hers lead, her karton (she has no tab)."""
    sara = make_user("sara@test.local", plans=())
    lara = make_user("lara@test.local")
    lapse(lara)
    make_user("coach@test.local", is_trainer=True, plans=())
    sid = termin(sara, (now() + timedelta(days=5)).replace(second=0, microsecond=0), title="Individualni")
    hers = db.add_gym_outside(sara, config.today())                          # one she has from before
    for email in ("sara@test.local", "lara@test.local"):
        page = client_for(email).get("/dvoranski").text
        assert GATE in page and "Član nema aktivnu članarinu" not in page, email
        assert not any(mark in page for mark in SECTIONS) and 'action="/dvoranski/trening"' not in page, email
    cs = client_for("coach@test.local")
    for uid, way in ((sara, "whole app"), (lara, "whole app"), (sara, "tab")):
        if way == "tab":
            assert cs.post("/dvoranski/clan", data={"clan": str(uid)}, follow_redirects=False).status_code == 303
        else:
            assert cs.post(f"/kao/{uid}", follow_redirects=False).status_code == 303
        page = cs.get("/dvoranski").text
        assert STAFF_GATE in page and not any(mark in page for mark in SECTIONS), way
        assert 'action="/dvoranski/trening"' not in page and "Pripremi trening" not in page, way
        before = len(db.gym_trainings(uid))
        for plan in ("grupni", ""):
            r = staff_add(cs, uid, config.today(), plan=plan)
            assert location(r) == "/dvoranski" and len(db.gym_trainings(uid)) == before, (way, plan)
        cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(uid)})
    cs.post(f"/kao/{sara}")
    r = cs.get(f"/dvoranski/termin/{sid}", follow_redirects=False)            # her booking: staff prepare it
    page = cs.get(location(r)).text
    assert "Za člana je upis zatvoren; uređuješ kao trener." in page
    assert f'<a class="act act-quiet" href="/karton#s-{sid}"><span class="t">← Natrag</span></a>' in page
    page = cs.get(f"/dvoranski/trening/{hers}").text                        # hers outside a termin, by its link
    assert f'<a class="act act-quiet" href="/karton#gt-{hers}"><span class="t">← Natrag</span></a>' in page
    r = cs.post(f"/dvoranski/trening/{hers}/blok?kao={sara}", data={"vrsta": "stanica"}, follow_redirects=False)
    assert location(r).startswith(f"/dvoranski/trening/{hers}?blok=") and len(db.gym_training(hers, sara).blocks) == 1
    r = cs.post(f"/dvoranski/trening/{hers}/osvrt?kao={sara}", data={"effort": "6"}, follow_redirects=False)
    assert location(r) == f"/karton?ok=Trening je spremljen.#gt-{hers}"


# ---------- staff plan a member's training ahead (28.11.2026) ----------

def test_staff_acting_as_a_member_plan_his_training_ahead_at_a_time():
    """The owner: "Amir can add a training outside of the booked slots for a
    specific user. For example a he adds a training for a user coming to the
    gym on his own on a saturday at some time slot." While staff act as a
    member (the whole app, a tab's view), the tab's "Trening izvan termina"
    takes the day up to 60 days ahead (db.GYM_PLAN_DAYS: the date's max),
    "Vrijeme (neobavezno)" (type=time, empty for none) and his gym plan (one
    plan: its words and its hidden value); the member's own form stays the
    day alone, today at the latest. Made by staff: tomorrow at 10:00
    (held_on tomorrow, starts_at that day at 10:00 in Zagreb), 60 days ahead
    with no time (no start), today with none: no session, no title, the plan
    posted, each. Refused, nothing made, back at the form with its sentence:
    61 days ahead and a day before 2020 ("Neispravan datum."), a time that
    is none ("Neispravno vrijeme."). (Each counts against his grupni, which
    is paid far ahead here: a day after a plan's dospijeće is refused too,
    the paket's tests below.)"""
    ivan = make_user("ivan@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    today = config.today()
    tomorrow, last = today + timedelta(days=1), today + timedelta(days=db.GYM_PLAN_DAYS)
    plan_due(ivan, "grupni", last, None)                                      # dospijeće a week past the 60 days
    assert db.GYM_PLAN_DAYS == 60
    cs = client_for("coach@test.local")
    for way in ("whole app", "tab"):
        if way == "tab":
            cs.post("/dvoranski/clan", data={"clan": str(ivan)})
        else:
            cs.post(f"/kao/{ivan}")
        form = " ".join(section(cs.get("/dvoranski").text, "dv-new-h").split())
        assert (f'<input id="dv-day" type="date" name="day" value="{today.isoformat()}" '
                f'min="2020-01-01" max="{last.isoformat()}" required>') in form, way
        assert ('<div class="field"><label for="dv-time">Vrijeme (neobavezno)</label> '
                '<input id="dv-time" type="time" name="time"></div>') in form, way
        assert ('<p class="dv-plan-cap">Članarina</p> <p class="dv-plan-one">Grupni trening</p>'
                '<input type="hidden" name="plan" value="grupni">') in form, way
        cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    cs.post(f"/kao/{ivan}")
    made = {}
    for key, day, at in (("tomorrow", tomorrow, "10:00"), ("last", last, ""), ("today", today, "")):
        made[key] = made_id(staff_add(cs, ivan, day, at))
    stored = {key: db.gym_training(tid, ivan) for key, tid in made.items()}
    assert [(t.session_id, t.title, t.plan) for t in stored.values()] == [(None, "", "grupni")] * 3
    assert stored["tomorrow"].held_on == tomorrow
    assert stored["tomorrow"].starts_at == datetime.combine(tomorrow, dtime(10, 0), tzinfo=config.TZ)
    assert (stored["last"].held_on, stored["last"].starts_at) == (last, None)
    assert (stored["today"].held_on, stored["today"].starts_at) == (today, None)
    assert all(t.outside for t in stored.values())
    for day, at, error in ((last + timedelta(days=1), "", "Neispravan datum."), (date(2019, 12, 31), "", "Neispravan datum."),
                           (tomorrow, "25:00", "Neispravno vrijeme."), (tomorrow, "10:5", "Neispravno vrijeme."),
                           (tomorrow, "24:00", "Neispravno vrijeme."), (tomorrow, "10:00:00", "Neispravno vrijeme."),
                           (tomorrow, "deset", "Neispravno vrijeme.")):
        r = staff_add(cs, ivan, day, at)
        assert location(r) == f"/dvoranski?error={error}#trening-novi", (day, at)
    assert len(db.gym_trainings(ivan)) == 3
    page = cs.get("/dvoranski?error=Neispravno vrijeme.").text
    assert '<div class="alert" role="alert"><span>Neispravno vrijeme.</span></div>' in section(page, "dv-new-h")
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    ci = client_for("ivan@test.local")                                         # the member: today at the latest
    form = " ".join(section(ci.get("/dvoranski").text, "dv-new-h").split())
    assert f'max="{today.isoformat()}" required>' in form and 'name="time"' not in form and 'name="plan"' not in form
    r = ci.post("/dvoranski/trening", data={"day": tomorrow.isoformat(), "time": "10:00"}, follow_redirects=False)
    assert location(r) == "/dvoranski?error=Neispravan datum.#trening-novi" and len(db.gym_trainings(ivan)) == 3
    mine = db.gym_training(made_id(ci.post("/dvoranski/trening", data={"day": today.isoformat(), "time": "10:00"},
                                           follow_redirects=False)), ivan)
    assert (mine.held_on, mine.starts_at, mine.plan) == (today, None, None)   # his time: ignored


def test_a_planned_training_is_on_his_tab_from_the_moment_it_is_made():
    """"Otvoreni treninzi" lists his trainings made outside a termin with no
    osvrt dated yesterday, today or later: one staff planned is his from the
    moment it is made, to open and to write (rule 1: a training outside a
    termin is always his). Its card: "Trening izvan termina", its day and
    its time when it has one ("subota 5.12.2026. · 10:00"), what it holds,
    "Upiši trening" / "Nastavi trening". The cards in one order by when they
    are: a termin's start, a training's time, or its day's start with no
    time. Staff acting as him see the same cards. Gone once its osvrt is
    saved, and two days after its day (one dated yesterday still there)."""
    ivan = make_user("ivan@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    today = config.today()
    start = (now() - timedelta(hours=1)).replace(second=0, microsecond=0)
    sid = termin(ivan, start, title="Snaga")                                   # open now: his to write
    cs = client_for("coach@test.local")
    cs.post(f"/kao/{ivan}")
    ahead = today + timedelta(days=2)
    planned = made_id(staff_add(cs, ivan, ahead, "10:00"))                     # in two days at 10:00
    later = made_id(staff_add(cs, ivan, today + timedelta(days=9)))            # a day with no time
    plain = made_id(staff_add(cs, ivan, today))                                # today, no time
    gone = db.add_gym_outside(ivan, today - timedelta(days=2), dtime(10, 0), "grupni")   # two days after its day
    kept = db.add_gym_outside(ivan, today - timedelta(days=1), dtime(10, 0), "grupni")   # the day after its day
    at = {f"dv-s-{sid}": start,
          f"dv-gt-{planned}": datetime.combine(ahead, dtime(10, 0), tzinfo=config.TZ),
          f"dv-gt-{later}": datetime.combine(today + timedelta(days=9), dtime(0, 0), tzinfo=config.TZ),
          f"dv-gt-{plain}": datetime.combine(today, dtime(0, 0), tzinfo=config.TZ),
          f"dv-gt-{kept}": datetime.combine(today - timedelta(days=1), dtime(10, 0), tzinfo=config.TZ)}
    expected = sorted(at, key=lambda k: (at[k], k.startswith("dv-gt-")))      # by when, read off the data
    staff_page = cs.get("/dvoranski").text
    assert [k for k, _ in cards(staff_page)] == expected
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    ci = client_for("ivan@test.local")
    page = ci.get("/dvoranski").text
    assert [k for k, _ in cards(page)] == expected and f"dv-gt-{gone}" not in page
    body = dict(cards(page))
    card = body[f"dv-gt-{planned}"]
    assert '<h3><span class="t">Trening izvan termina</span></h3>' in card
    assert f'<p class="dv-when">{day_text(ahead)} · 10:00</p>' in card and 'class="dv-state"' not in card
    assert (f'<a class="btn btn-sm dv-go" href="/dvoranski/trening/{planned}"><span class="t">Upiši trening</span></a>'
            in card)
    assert f'<p class="dv-when">{day_text(today + timedelta(days=9))}</p>' in body[f"dv-gt-{later}"]
    page = ci.get(f"/dvoranski/trening/{planned}").text                       # he opens it before its day
    assert 'class="gt-state"' not in page.replace(counted("Grupni trening", "gt-state"), "")
    r = ci.post(f"/dvoranski/trening/{planned}/blok", data={"vrsta": "stanica"}, follow_redirects=False)
    assert location(r).startswith(f"/dvoranski/trening/{planned}?blok=")      # and writes it
    card = dict(cards(ci.get("/dvoranski").text))[f"dv-gt-{planned}"]
    assert '<span class="t">Nastavi trening</span>' in card
    db.finish_gym_training(planned, ivan, 7, None, "")                       # its osvrt saved: the karton's alone
    page = ci.get("/dvoranski").text
    assert f"dv-gt-{planned}" not in page and f"dv-gt-{later}" in page


def test_promijeni_datum_moves_a_planned_training_and_its_time():
    """"promijeni datum" on a training made outside a termin: for staff
    acting as the member the day up to 60 days ahead and "Vrijeme
    (neobavezno)", the stored time its value: they move the day ahead, set
    the time, change it, and empty it to take it away; for the member the
    day alone, today at the latest, of a training he made himself (a time he
    posts ignored; one staff made is theirs to move: it counts in his
    paket). One let go of its termin is refused as before
    (no form, 404; db.set_gym_day False), and a termin's training too."""
    ivan = make_user("ivan@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    today = config.today()
    cs = client_for("coach@test.local")
    cs.post(f"/kao/{ivan}")
    tid = made_id(staff_add(cs, ivan, today + timedelta(days=1)))

    def stored():
        t = db.gym_training(tid, ivan)
        return t.held_on, (None if t.starts_at is None else t.starts_at.astimezone(config.TZ).strftime("%H:%M"))

    def move(c, day: date, at: str | None = None, marked: bool = True):
        data = {"day": day.isoformat(), **({} if at is None else {"time": at})}
        return c.post(f"/dvoranski/trening/{tid}/datum" + (f"?kao={ivan}" if marked else ""), data=data,
                      follow_redirects=False)

    page = cs.get(f"/dvoranski/trening/{tid}").text
    head = " ".join(page.split('class="gt-date-form"')[1].split("</form>")[0].split())
    assert f'max="{(today + timedelta(days=60)).isoformat()}" required>' in head
    assert ('<label for="gt-time">Vrijeme (neobavezno)</label> '
            '<input id="gt-time" type="time" name="time" value="">') in head
    five = today + timedelta(days=5)
    assert location(move(cs, five, "18:30")) == f"/dvoranski/trening/{tid}?ok=Datum je spremljen."
    assert stored() == (five, "18:30")
    assert 'name="time" value="18:30">' in cs.get(f"/dvoranski/trening/{tid}").text
    move(cs, five, "07:15")
    assert stored() == (five, "07:15")
    move(cs, five, "")                                                        # emptied: no time
    assert stored() == (five, None)
    move(cs, five, "18:30")
    for day, at, error in ((today + timedelta(days=61), "", "Neispravan datum."), (five, "7", "Neispravno vrijeme.")):
        assert location(move(cs, day, at)) == f"/dvoranski/trening/{tid}?error={error}", (day, at)
    assert stored() == (five, "18:30")
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    ci = client_for("ivan@test.local")
    # the member: the day alone, today at the latest, and only of a training
    # he made himself (one staff made counts in his paket: its day is staff's,
    # test_a_counted_trainings_day_and_deletion_are_staffs_alone)
    assert 'class="gt-date-form"' not in ci.get(f"/dvoranski/trening/{tid}").text
    yesterday = today - timedelta(days=1)
    assert "broji se u članarinu" in location(move(ci, yesterday, "09:00", marked=False))
    assert stored() == (five, "18:30")
    own = made_id(ci.post("/dvoranski/trening", data={"day": today.isoformat()}, follow_redirects=False))
    head = " ".join(ci.get(f"/dvoranski/trening/{own}").text.split('class="gt-date-form"')[1].split("</form>")[0].split())
    assert f'max="{today.isoformat()}" required>' in head and 'name="time"' not in head
    r = ci.post(f"/dvoranski/trening/{own}/datum", data={"day": (today + timedelta(days=1)).isoformat()}, follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{own}?error=Neispravan datum."
    ci.post(f"/dvoranski/trening/{own}/datum", data={"day": yesterday.isoformat(), "time": "09:00"})   # a time he posts: ignored
    mine = db.gym_training(own, ivan)
    assert (mine.held_on, mine.starts_at) == (yesterday, None)
    sess = termin(ivan, datetime.combine(today, dtime(0, 30), tzinfo=config.TZ), title="Mobilnost")
    let_go = db.gym_training_for(ivan, sess, staff=True)
    with db.session_scope() as s:                                            # let go of its termin (rule 3)
        s.get(GymTraining, let_go).session_id = None
    termins = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    for other in (let_go, termins):
        assert ci.post(f"/dvoranski/trening/{other}/datum", data={"day": yesterday.isoformat()}).status_code == 404
        assert 'class="gt-date-form"' not in ci.get(f"/dvoranski/trening/{other}").text
        assert db.set_gym_day(other, ivan, yesterday, staff=True) is False


def test_the_page_says_the_day_and_the_time_and_the_diary_lists_a_planned_one():
    """The training's page says the day and the time under its title as a
    termin's does ("subota 5.12.2026. · 10:00"; the day alone with no
    time), its state line as an outside training's (none); and a planned one
    that holds an exercise is a row of his diary at its day, its time
    after its date, as any training outside a termin."""
    ivan = make_user("ivan@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    today = config.today()
    ahead = today + timedelta(days=3)
    cs = client_for("coach@test.local")
    cs.post(f"/kao/{ivan}")
    timed = made_id(staff_add(cs, ivan, ahead, "10:00"))
    untimed = made_id(staff_add(cs, ivan, ahead))
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    ci = client_for("ivan@test.local")
    for tid, when in ((timed, f"{day_text(ahead)} · 10:00"), (untimed, day_text(ahead))):
        page = ci.get(f"/dvoranski/trening/{tid}").text
        head = " ".join(page.split('<div class="gt-head">')[1].split('<div class="pl-grid')[0].split())
        assert '<h1><span class="t">Trening izvan termina</span></h1>' in head
        assert f'<div class="gt-when"> <span>{when}</span>' in head, tid
        assert head.count('<p class="gt-state">') == 1 and counted("Grupni trening", "gt-state") in head, tid
        assert f"<title>Trening izvan termina — {when} — QMT</title>" in page
    db.set_gym_station(db.add_gym_block(timed, ivan, "stanica", staff=True), ivan, db.create_exercise("Goblet čučanj"),
                       3, 10, staff=True)
    own = db.add_gym_outside(ivan, today)                                     # his own, today: under them
    karton = ci.get("/karton").text
    row = karton.split(f'id="gt-{timed}"')[1].split('<div class="log-entry')[0]
    short = ("pon", "uto", "sri", "čet", "pet", "sub", "ned")[ahead.weekday()]
    assert f'<span class="when">{short} {ahead.day}.{ahead.month}.{ahead.year}. · 10:00</span>' in row
    assert '<div class="le-kicker"><span class="t">Trening izvan termina</span></div>' in row
    assert f'href="/dvoranski/trening/{timed}"' in row and "1 vježba" in row and "Broji se" not in row
    order = re.findall(r'class="log-entry gym" id="gt-(\d+)"', karton)          # the diary: newest first, at its day
    assert order == [str(timed), str(untimed), str(own)]


# ---------- a training staff add counts in his paket (28.11.2026) ----------

def _migration(file: str):
    path = pathlib.Path(__file__).parents[1] / "alembic" / "versions" / file
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(step) -> None:
    """A revision's upgrade() or downgrade(), run for real on qmt_test."""
    with db.engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        step()


def _takes(sql: str, **params) -> bool:
    """Whether the database takes a statement (a CHECK refuses it: False)."""
    try:
        with db.engine.begin() as conn:
            conn.execute(sa_text(sql), params)
        return True
    except IntegrityError:
        return False


def test_the_migration_adds_the_plan_and_its_check_and_back():
    """a3f6c1e8d47b, run on qmt_test as before it (gym_trainings with no
    plan, two trainings in it): the column as the model has it (String(20),
    NULL), every training there NULL (none counts), its CHECK taking the
    four plans that book termini and NULL, refusing any other; downgrade
    drops both, the trainings staying; a second upgrade makes them again,
    nothing counting."""
    from alembic.autogenerate import compare_metadata

    mig = _migration("a3f6c1e8d47b_gym_trainings_plan.py")
    assert (mig.revision, mig.down_revision) == ("a3f6c1e8d47b", "9b4e2d7f1c58")
    assert mig.PLANS == SESSION_KINDS                                        # its own copy agrees with the model's
    ivan = make_user("ivan@test.local")
    tids = [db.add_gym_outside(ivan, config.today()), db.add_gym_outside(ivan, config.today(), plan="grupni")]
    with db.engine.begin() as conn:                                          # the table as before the revision
        conn.execute(sa_text("ALTER TABLE gym_trainings DROP COLUMN plan"))
    assert "plan" not in {c["name"] for c in sa_inspect(db.engine).get_columns("gym_trainings")}
    _run(mig.upgrade)
    with db.engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert [d for d in diffs if "gym_trainings" in repr(d)] == []
    col = {c["name"]: c for c in sa_inspect(db.engine).get_columns("gym_trainings")}["plan"]
    assert col["nullable"] and str(col["type"]) == "VARCHAR(20)" and col["default"] is None
    assert [db.gym_training(t, ivan).plan for t in tids] == [None, None]
    assert "ck_gym_trainings_plan" in {c["name"] for c in sa_inspect(db.engine).get_check_constraints("gym_trainings")}
    for value in (*SESSION_KINDS, None):
        assert _takes("UPDATE gym_trainings SET plan = :v WHERE id = :i", v=value, i=tids[0]), value
    for value in ("online", "prehrana", "", "Grupni", "x"):
        assert not _takes("UPDATE gym_trainings SET plan = :v WHERE id = :i", v=value, i=tids[0]), value
    _run(mig.downgrade)
    assert "plan" not in {c["name"] for c in sa_inspect(db.engine).get_columns("gym_trainings")}
    with db.engine.connect() as conn:
        assert conn.execute(sa_text("SELECT count(*) FROM gym_trainings")).scalar() == 2
    _run(mig.upgrade)
    assert [db.gym_training(t, ivan).plan for t in tids] == [None, None]


def test_staff_count_a_training_against_one_of_his_gym_plans():
    """The owner: "Will this extra training slot be counted in the
    subscription total? It should be counted." A training staff add for a
    member outside a termin counts against one of his gym plans
    (GymTraining.plan): "Članarina" in their form, his running plans that
    book termini in their order, each its name and a tiered one's count in
    this cycle; one plan its words (posted hidden), two or more a select,
    each choice stored. Refused, nothing made, "Odaberi članarinu.": a plan
    he lacks, a lapsed one, one that books no termin, junk, none posted. The
    member's own form has no "Članarina" and his own training counts nothing."""
    ivan = make_user("ivan@test.local", plans=("grupni", "online"))
    ana = make_user("ana@test.local", plans=("individualni", "rehabilitacija"))
    db.record_payment(ana, "grupni", sessions_per_cycle=8)
    today = config.today()
    plan_due(ana, "rehabilitacija", today - timedelta(days=Membership.GRACE_DAYS + 1), None)   # lapsed
    make_user("coach@test.local", is_trainer=True, plans=())
    cs = client_for("coach@test.local")
    cs.post(f"/kao/{ana}")
    form = " ".join(section(cs.get("/dvoranski").text, "dv-new-h").split())
    assert ('<label for="dv-plan">Članarina</label> <select id="dv-plan" name="plan"> '
            '<option value="grupni">Grupni trening · 0 od 8 u ovom ciklusu</option> '
            '<option value="individualni">Individualni trening</option> </select>') in form
    for plan in ("grupni", "individualni"):
        assert db.gym_training(made_id(staff_add(cs, ana, today, plan=plan)), ana).plan == plan, plan
    for plan in ("poluindividualni", "rehabilitacija", "online", "x", ""):
        r = staff_add(cs, ana, today, plan=plan)
        assert location(r) == "/dvoranski?error=Odaberi članarinu.#trening-novi", plan
    r = cs.post(f"/dvoranski/trening?kao={ana}", data={"day": today.isoformat()}, follow_redirects=False)
    assert location(r) == "/dvoranski?error=Odaberi članarinu.#trening-novi"   # no plan field at all
    assert sorted(g.plan for g in db.gym_trainings(ana)) == ["grupni", "individualni"]
    assert db.cycle_usage(ana, "grupni")["used"] == 1
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ana)})
    cs.post(f"/kao/{ivan}")
    form = " ".join(section(cs.get("/dvoranski").text, "dv-new-h").split())
    assert ('<p class="dv-plan-cap">Članarina</p> <p class="dv-plan-one">Grupni trening</p>'
            '<input type="hidden" name="plan" value="grupni">') in form and "<select" not in form
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    ca = client_for("ana@test.local")                                       # her own: as before
    assert "Članarina" not in section(ca.get("/dvoranski").text, "dv-new-h")
    own = db.gym_training(made_id(ca.post("/dvoranski/trening", data={"day": today.isoformat(), "plan": "grupni"},
                                          follow_redirects=False)), ana)
    assert own.plan is None and db.cycle_usage(ana, "grupni")["used"] == 1


def test_a_counted_training_takes_a_place_in_his_paket():
    """One count (db._cycle_used): a tiered grupni at 7 of 8, staff add one
    in the cycle → 8 of 8 on /moja-clanarina and in their form; the next
    booking of a group termin in that cycle refused by book() with its own
    sentence; the next add refused, "Član je iskoristio svih 8 treninga u
    ciklusu …." (the cycle in book()'s words). Emptying it changes nothing;
    deleting it gives its place back, 7 of 8, and an add and a booking each
    go through again. A training let go of its termin is not counted (its
    booking gone), nor a member's own training outside a termin."""
    ivan = make_user("ivan@test.local", plans=())
    db.record_payment(ivan, "grupni", sessions_per_cycle=8)
    make_user("coach@test.local", is_trainer=True, plans=())
    today = config.today()
    usage = db.cycle_usage(ivan, "grupni")
    start, end = usage["start"], usage["end"]
    # a termin's training with a record, its booking cancelled: let go (rule 3), it counts nothing
    sid = termin(ivan, datetime.combine(today + timedelta(days=2), dtime(18, 0), tzinfo=config.TZ))
    let_go = db.gym_training_for(ivan, sid, staff=True)
    db.finish_gym_training(let_go, ivan, 6, None, "", staff=True)
    assert db.cycle_usage(ivan, "grupni")["used"] == 1
    db.cancel_booking(ivan, sid)
    t = db.gym_training(let_go, ivan)
    assert (t.session_id, t.title, t.plan) == (None, "Grupni trening", None) and db.cycle_usage(ivan, "grupni")["used"] == 0
    days = [today + timedelta(days=k) for k in range(1, 8)]
    assert all(start <= d < end for d in days)
    booked_at(ivan, *days)                                                   # 7 of 8
    cs = client_for("coach@test.local")
    cs.post(f"/kao/{ivan}")
    form = " ".join(section(cs.get("/dvoranski").text, "dv-new-h").split())
    assert '<p class="dv-plan-one">Grupni trening · 7 od 8 u ovom ciklusu</p>' in form
    tid = made_id(staff_add(cs, ivan, today + timedelta(days=2), "10:00"))
    assert db.cycle_usage(ivan, "grupni")["used"] == 8
    form = " ".join(section(cs.get("/dvoranski").text, "dv-new-h").split())
    assert '<p class="dv-plan-one">Grupni trening · 8 od 8 u ovom ciklusu</p>' in form
    full = f"Član je iskoristio svih 8 treninga u ciklusu {cycle_text(start, end)}."
    r = staff_add(cs, ivan, today + timedelta(days=4))
    assert location(r) == f"/dvoranski?error={full}#trening-novi" and len(db.gym_trainings(ivan)) == 2
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    ci = client_for("ivan@test.local")
    assert "<dd>8 od 8 u ovom ciklusu</dd>" in ci.get("/moja-clanarina").text
    group = db.add_oneoff_session("Grupni trening", datetime.combine(today + timedelta(days=3), dtime(18, 0),
                                                                     tzinfo=config.TZ), 60, 8, None)
    with pytest.raises(db.BookingError) as refused:
        db.book(ivan, group)
    assert str(refused.value) == (f"Iskoristio/la si svih 8 treninga u ciklusu {cycle_text(start, end)} — "
                                  "otkaži neki termin ili pričekaj sljedeći ciklus.")
    mine = made_id(ci.post("/dvoranski/trening", data={"day": today.isoformat()}, follow_redirects=False))
    assert db.gym_training(mine, ivan).plan is None and db.cycle_usage(ivan, "grupni")["used"] == 8   # his own: unmoved
    db.empty_gym_training(tid, ivan, staff=True)                             # emptied: still counted
    assert db.cycle_usage(ivan, "grupni")["used"] == 8
    cs.post(f"/kao/{ivan}")
    r = cs.post(f"/dvoranski/trening/{tid}/obrisi?kao={ivan}", follow_redirects=False)
    assert location(r) == "/dvoranski?ok=Trening je obrisan." and db.cycle_usage(ivan, "grupni")["used"] == 7
    again = made_id(staff_add(cs, ivan, today + timedelta(days=4)))          # an add goes through again
    assert db.cycle_usage(ivan, "grupni")["used"] == 8
    db.delete_gym_training(again, ivan, staff=True)
    db.book(ivan, group)                                                     # and so does a booking
    assert db.cycle_usage(ivan, "grupni")["used"] == 8
    assert "<dd>8 od 8 u ovom ciklusu</dd>" in ci.get("/moja-clanarina").text


def test_the_cycle_and_dospijece_bound_a_counted_training():
    """A counted training sits in the cycle that holds its day: one on the
    next cycle's first day counts there, not here; moved from there into a
    full cycle it is refused, nothing changed; moved within its own full
    cycle it goes (its own place is not a second one). Dospijeće, booking's
    rule: a day after it refused, "Članarina člana vrijedi do … — za
    kasniji dan je treba produljiti.", the day of it allowed; an add and a
    move alike."""
    ivan = make_user("ivan@test.local", plans=())
    db.record_payment(ivan, "grupni", sessions_per_cycle=8)
    today = config.today()
    nxt = today + timedelta(days=20)
    plan_due(ivan, "grupni", nxt, 8)                  # this cycle ends the day before nxt; dospijeće a week after
    due = nxt + timedelta(days=Membership.GRACE_DAYS)
    make_user("coach@test.local", is_trainer=True, plans=())
    cs = client_for("coach@test.local")
    cs.post(f"/kao/{ivan}")

    def move(tid: int, day: date):
        return cs.post(f"/dvoranski/trening/{tid}/datum?kao={ivan}", data={"day": day.isoformat(), "time": ""},
                       follow_redirects=False)

    booked_at(ivan, *(today + timedelta(days=k) for k in range(1, 8)))       # 7 of 8 here
    inside = made_id(staff_add(cs, ivan, today + timedelta(days=8)))          # 8 of 8 here
    there = made_id(staff_add(cs, ivan, nxt))                                 # the next cycle's first day
    here, after = db.cycle_usage(ivan, "grupni"), db.cycle_usage(ivan, "grupni", on=nxt)
    assert (here["used"], after["used"], after["start"]) == (8, 1, nxt)
    full = f"Član je iskoristio svih 8 treninga u ciklusu {cycle_text(here['start'], here['end'])}."
    assert location(move(there, today + timedelta(days=9))) == f"/dvoranski/trening/{there}?error={full}"
    assert db.gym_training(there, ivan).held_on == nxt
    assert location(move(inside, today + timedelta(days=10))) == f"/dvoranski/trening/{inside}?ok=Datum je spremljen."
    assert db.gym_training(inside, ivan).held_on == today + timedelta(days=10)
    assert db.cycle_usage(ivan, "grupni")["used"] == 8
    late = f"Članarina člana vrijedi do {due.day}.{due.month}. — za kasniji dan je treba produljiti."
    r = staff_add(cs, ivan, due + timedelta(days=1))
    assert location(r) == f"/dvoranski?error={late}#trening-novi"
    assert location(move(there, due + timedelta(days=1))) == f"/dvoranski/trening/{there}?error={late}"
    on_due = made_id(staff_add(cs, ivan, due))                                # the day of it: allowed
    assert db.gym_training(on_due, ivan).held_on == due
    assert db.cycle_usage(ivan, "grupni", on=nxt)["used"] == 2 and len(db.gym_trainings(ivan)) == 3


def test_a_booking_and_an_add_never_both_take_the_last_place():
    """At 7 of 8 the paket has one place: two adds at once (six threads) make
    one training; an add and a booking at once (three of each, five rounds,
    each winner undone after its round) take it once a round. The add takes
    his membership row FOR UPDATE before it counts, and so does book()'s
    paket check, after its session row: the paket never passes its number,
    and nothing deadlocks. (Without the add's lock the first race fails
    every time; without book()'s, the rounds catch it.)"""
    ivan = make_user("ivan@test.local", plans=())
    db.record_payment(ivan, "grupni", sessions_per_cycle=8)
    today = config.today()
    booked_at(ivan, *(today + timedelta(days=k) for k in range(1, 8)))       # 7 of 8
    day = today + timedelta(days=9)

    def race(calls: dict) -> dict[str, str]:
        """Every call at once (a barrier): each one's name → "ok", "full", or the error a failure raised."""
        barrier, results = threading.Barrier(len(calls)), {}

        def run(name, call):
            barrier.wait()
            try:
                call()
                results[name] = "ok"
            except db.BookingError:
                results[name] = "full"
            except Exception as e:                                           # a deadlock, anything else: a failure
                results[name] = f"error: {type(e).__name__}"

        threads = [threading.Thread(target=run, args=item) for item in calls.items()]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return results

    def add():
        db.add_gym_outside(ivan, day, None, "grupni")

    results = race({f"add {n}": add for n in range(6)})
    assert sorted(results.values()) == ["full"] * 5 + ["ok"], results
    assert db.cycle_usage(ivan, "grupni")["used"] == 8
    [made] = [g.id for g in db.gym_trainings(ivan) if g.plan]
    db.delete_gym_training(made, ivan, staff=True)
    assert db.cycle_usage(ivan, "grupni")["used"] == 7
    sids = [db.add_oneoff_session("Grupni trening", datetime.combine(today + timedelta(days=k), dtime(18, 0),
                                                                     tzinfo=config.TZ), 60, 8, None) for k in (10, 11, 12)]
    for round_ in range(5):
        calls = {**{f"book {sid}": (lambda sid=sid: db.book(ivan, sid)) for sid in sids},
                 **{f"add {n}": add for n in range(3)}}
        results = race(calls)
        assert sorted(results.values()) == ["full"] * 5 + ["ok"], (round_, results)
        assert db.cycle_usage(ivan, "grupni")["used"] == 8, round_
        [winner] = [name for name, outcome in results.items() if outcome == "ok"]
        if winner.startswith("book "):                                       # undone: 7 of 8 for the next round
            db.cancel_booking(ivan, int(winner.split()[1]))
        else:
            [made] = [g.id for g in db.gym_trainings(ivan) if g.plan]
            db.delete_gym_training(made, ivan, staff=True)
        assert db.cycle_usage(ivan, "grupni")["used"] == 7, round_


def test_a_counted_training_says_so_on_its_card_and_its_page():
    """"Broji se u članarinu: Grupni trening." (gym.state.counted, then the
    plan's name): one muted line on the tab's card of a training staff made
    against a gym plan and under its page's date, for staff and for the
    member; the karton's diary row says nothing new; a member's own training
    says nothing of it. Its words a slot, edited in place."""
    ivan = make_user("ivan@test.local", plans=("grupni", "individualni"))
    make_user("coach@test.local", is_trainer=True, plans=())
    today = config.today()
    cs = client_for("coach@test.local")
    cs.post(f"/kao/{ivan}")
    tid = made_id(staff_add(cs, ivan, today + timedelta(days=1), "18:00", plan="individualni"))
    staff_card, staff_page = dict(cards(cs.get("/dvoranski").text))[f"dv-gt-{tid}"], cs.get(f"/dvoranski/trening/{tid}").text
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    ci = client_for("ivan@test.local")
    own = made_id(ci.post("/dvoranski/trening", data={"day": today.isoformat()}, follow_redirects=False))
    tab = ci.get("/dvoranski").text
    for card, page in ((staff_card, staff_page), (dict(cards(tab))[f"dv-gt-{tid}"], ci.get(f"/dvoranski/trening/{tid}").text)):
        assert counted("Individualni trening", "dv-plan") in card
        assert card.index('class="dv-when"') < card.index('class="dv-plan"')
        head = page.split('<div class="gt-head">')[1].split('<div class="pl-grid')[0]
        assert counted("Individualni trening", "gt-state") in head
    assert "Broji se" not in dict(cards(tab))[f"dv-gt-{own}"] and "Broji se" not in ci.get(f"/dvoranski/trening/{own}").text
    row = ci.get("/karton").text.split(f'id="gt-{tid}"')[1].split('<div class="log-entry')[0]
    assert "Broji se" not in row and "Individualni" not in row
    slot = copy.SLOTS["gym.state.counted"]
    assert slot.required and slot.label.startswith("Trening u dvorani")
    make_user("trener@test.local", is_trainer=True, plans=())
    t = client_for("trener@test.local")
    assert t.post("/copy/gym.state.counted", data={"text": "Ulazi u paket:"}).json()["text"] == "Ulazi u paket:"
    assert '<p class="dv-plan"><span class="t">Ulazi u paket:</span> Individualni trening.</p>' in ci.get("/dvoranski").text


def test_a_counted_trainings_day_and_deletion_are_staffs_alone():
    """A training staff made against a gym plan counts in the member's paket,
    so its day and its being there are staff's to change (Fable's review,
    28.11.2026): the member's page offers neither "promijeni datum" nor
    "Obriši trening" on it, and his posts are refused, nothing changed ("Ovaj
    trening je dodao trener i broji se u članarinu — …"), or he would take
    it out of his cycle himself. He writes it as any of his (a block added).
    Staff acting as him move and delete it, and the place comes back. His own
    training outside a termin: both his, as before."""
    ivan = make_user("ivan@test.local", plans=("grupni",))
    make_user("coach@test.local", is_trainer=True, plans=())
    today = config.today()
    cs = client_for("coach@test.local")
    cs.post(f"/kao/{ivan}")
    tid = made_id(staff_add(cs, ivan, today, "", plan="grupni"))
    staff_page = cs.get(f"/dvoranski/trening/{tid}").text
    assert f'action="/dvoranski/trening/{tid}/datum"' in staff_page and f'action="/dvoranski/trening/{tid}/obrisi"' in staff_page
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    ci = client_for("ivan@test.local")
    page = ci.get(f"/dvoranski/trening/{tid}").text
    assert f'action="/dvoranski/trening/{tid}/datum"' not in page and f'action="/dvoranski/trening/{tid}/obrisi"' not in page
    refused = "Ovaj trening je dodao trener i broji se u članarinu — pomaknuti ga ili obrisati može samo on."
    r = ci.post(f"/dvoranski/trening/{tid}/datum", data={"day": (today - timedelta(days=40)).isoformat()},
                follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}?error={refused}"
    r = ci.post(f"/dvoranski/trening/{tid}/obrisi", follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}?error={refused}"
    t = db.gym_training(tid, ivan)
    assert t is not None and (t.held_on, t.plan) == (today, "grupni")
    r = ci.post(f"/dvoranski/trening/{tid}/blok", data={"vrsta": "stanica"}, follow_redirects=False)   # his to write
    assert r.status_code == 303 and len(db.gym_training(tid, ivan).blocks) == 1
    own = made_id(ci.post("/dvoranski/trening", data={"day": today.isoformat()}, follow_redirects=False))
    mine = ci.get(f"/dvoranski/trening/{own}").text
    assert f'action="/dvoranski/trening/{own}/datum"' in mine and f'action="/dvoranski/trening/{own}/obrisi"' in mine
    cs.post(f"/kao/{ivan}")
    r = cs.post(f"/dvoranski/trening/{tid}/obrisi", headers={"X-QMT-Kao": str(ivan)}, follow_redirects=False)
    assert r.status_code == 303 and db.gym_training(tid, ivan) is None           # staff's: gone, its place back


# ---------- the texts ----------

def test_every_text_of_the_tab_is_a_slot_with_its_words():
    """The tab's texts are slots, gym.tab.* (14: its title and lead, the
    gate's sentence, "Otvoreni treninzi" and its two buttons, the next
    termin's caption and the words around the hours, the empty line and its
    link, "Trening izvan termina" and "Dodaj trening", the link to the
    karton; 17 until the evening of 27.11.2026, when "Zadnji treninzi", a
    row's "Otvori trening" and its empty line went with the section),
    labelled "Dvoranski treninzi…" in the editor's bar, required but for the
    lead, the gate's sentence, the words around the hours and the empty
    line; the training page's print where the tab says the same (the state
    line, a training outside a termin's name, Datum). Each printed with its
    default words on the pages a member reads; one edited prints in its
    place; an optional one emptied no element. /tekstovi lists them under
    "Trening u dvorani", the first area ("Dvoranski treninzi"), its "Otvori
    stranicu →" the tab."""
    assert len(TAB) == 14 and {k for k in TAB if not copy.SLOTS[k].required} == TAB_OPTIONAL
    assert all(copy.SLOTS[k].label.startswith("Dvoranski treninzi") for k in TAB)
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    make_user("mia@test.local", plans=("online",))
    make_user("trener@test.local", is_trainer=True, plans=())
    db.reset_gym_templates()
    termin(ivan, now() - timedelta(hours=2))                                 # open, no training: Upiši trening
    started = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)), staff=True)
    station(started, ivan, "Plank")                                         # open, a block: Nastavi trening
    station(db.add_gym_outside(ivan, config.today()), ivan, "Sklekovi")      # one outside a termin, open
    termin(ana, now() + timedelta(days=2))                                   # none open: her next termin
    pages = [client_for("ivan@test.local").get("/dvoranski").text, client_for("ana@test.local").get("/dvoranski").text,
             client_for("ana@test.local").get("/dvoranski?error=Neispravan datum.").text,
             client_for("mia@test.local").get("/dvoranski").text]
    make_user("lea@test.local")                                              # nothing open, nothing upcoming
    pages.append(client_for("lea@test.local").get("/dvoranski").text)
    every = "\n".join(pages)
    assert 'data-copy="' not in every
    for key in TAB + ["gym.state.open", "gym.head.outside", "gym.head.date_field"]:
        assert f'<span class="t">{copy.SLOTS[key].default}</span>' in every, key
    t = client_for("trener@test.local")
    for key, text in (("gym.tab.title", "Moji treninzi u dvorani"), ("gym.tab.fill", "Upiši"), ("gym.tab.lead", "")):
        assert t.post(f"/copy/{key}", data={"text": text}).json()["text"] == text, key
    page = client_for("ivan@test.local").get("/dvoranski").text
    assert '<h1><span class="t">Moji treninzi u dvorani</span></h1>' in page and '<span class="t">Upiši</span></a>' in page
    assert '<p class="hint"' not in main_of(page).split('<div class="dv">')[0]   # the emptied lead: no element
    editor = t.get("/dvoranski").text
    assert '<p class="hint" data-opt><span class="ed t" data-copy="gym.tab.lead"' in editor   # his empty box
    tekstovi = t.get("/tekstovi").text
    part = tekstovi.split(">Trening u dvorani</h2>")[1].split("<h2")[0]
    assert '<a class="act" href="/dvoranski">Otvori stranicu →</a>' in part
    assert re.findall(r"<h3>([^<]*)</h3>", part)[0] == "Dvoranski treninzi"
    first = part.split("<h3>Dvoranski treninzi</h3>")[1].split("<h3>")[0]
    assert re.findall(r'data-copy="([^"]+)"', first) == TAB


# ---------- in a browser, on a phone ----------

@pytest.fixture(scope="module")
def server():
    import uvicorn
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/healthz", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{PORT}"
    srv.should_exit = True
    th.join(timeout=5)


OVERFLOW = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
# the pill one row: every child of the bar on its line and inside its padding, none over another
PILL = r"""() => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && el.getBoundingClientRect().width > 0; };
  const px = v => parseFloat(v) || 0, out = [];
  const tb = document.querySelector('.topbar'), cs = getComputedStyle(tb), r = tb.getBoundingClientRect();
  const left = r.left + px(cs.borderLeftWidth) + px(cs.paddingLeft), right = r.right - px(cs.borderRightWidth) - px(cs.paddingRight);
  const kids = [...tb.children].filter(k => vis(k) && getComputedStyle(k).position !== 'absolute');
  kids.forEach((k, i) => { const b = k.getBoundingClientRect();
    if (b.left < left - .5 || b.right > right + .5) out.push(`${k.className} leaves the pill's padding`);
    if (i && b.left < kids[i - 1].getBoundingClientRect().right - .5) out.push(`${k.className} overlaps`); });
  const nav = document.getElementById('mainNav');
  const tabs = [...nav.querySelectorAll(':scope > a')].filter(vis);
  const mids = tabs.map(t => { const b = t.getBoundingClientRect(); return (b.top + b.bottom) / 2; });
  if (Math.max(...mids) - Math.min(...mids) > 2) out.push('the tabs are on more than one line');
  return {problems: out, drawer: getComputedStyle(nav).position === 'absolute', labels: tabs.map(t => t.textContent.trim())};
}"""


def test_the_tab_on_a_phone(server):
    """At 390px, touch, as ivan (a gym plan and an online plan): the ☰
    drawer holds Dvoranski treninzi after Karton, a tap opens the tab's page
    (the tab current in the drawer); its open termin's card; no page
    scrolls sideways, at 360px either; "Dodaj trening" with today's date →
    the new training's page (its template chooser, the tab lit), "← Natrag"
    → the tab again, where the training is among the open ones (no osvrt,
    today: since the evening of 27.11.2026). At 1280px the bar holds the
    seven tabs on one row inside the pill, the tab lit. No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    ivan = make_user("ivan@test.local", plans=("grupni", "online"))
    db.reset_gym_templates()
    sid = termin(ivan, now() - timedelta(hours=1), title="Snaga")
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(server + "/login")
        pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); localStorage.setItem('qmt-phone', String(Date.now())); }")
        pg.fill("main input[name=email]", "ivan@test.local")
        pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]")
        pg.wait_for_load_state("networkidle")
        if pg.locator("#fbPrompt[open], dialog[open]").count():               # the login's prompt: later
            pg.keyboard.press("Escape")

        def wide(where: str) -> None:
            for w, h in ((390, 844), (360, 780)):
                pg.set_viewport_size({"width": w, "height": h})
                check(pg.evaluate(OVERFLOW) == 0, f"{where} at {w}px overflows by {pg.evaluate(OVERFLOW)}px")
            pg.set_viewport_size({"width": 390, "height": 844})

        pg.tap(".nav-burger")
        rows = [t.strip() for t in pg.locator("#mainNav > a").all_inner_texts()]
        check(rows[rows.index("Karton") + 1:rows.index("Karton") + 2] == ["Dvoranski treninzi"], f"the drawer: {rows}")
        with pg.expect_navigation():
            pg.tap('#mainNav > a[href="/dvoranski"]')
        pg.wait_for_load_state("networkidle")
        check(pg.url == server + "/dvoranski", f"the drawer's row led to {pg.url}")
        pg.tap(".nav-burger")
        current = pg.evaluate("() => [...document.querySelectorAll('#mainNav > a.on')].map(a => a.textContent.trim())")
        check(current == ["Dvoranski treninzi"], f"the drawer's current row: {current}")
        pg.tap(".nav-burger")
        check(pg.locator(f"#dv-s-{sid}").is_visible(), "the open termin's card is not shown")
        check(pg.locator(f"#dv-s-{sid} .dv-when").inner_text() == when_text(
            db.gym_open_termini(ivan)[0].starts_at), "the card's date and time")
        wide("the tab's page")
        pg.locator("#dv-day").scroll_into_view_if_needed()
        check(pg.locator("#dv-day").input_value() == config.today().isoformat(), "the date is not today by default")
        with pg.expect_navigation():
            pg.locator("form.dv-form button[type=submit]").tap()
        pg.wait_for_load_state("networkidle")
        made = [t for t in db.gym_trainings(ivan) if t.session_id is None]
        check(len(made) == 1 and pg.url == server + f"/dvoranski/trening/{made[0].id}" if made else False,
              f"Dodaj trening led to {pg.url}")
        check(pg.locator(".gt-chooser").is_visible(), "the new training's page shows no template chooser")
        lit = pg.evaluate("() => [...document.querySelectorAll('#mainNav > a.on')].map(a => a.textContent.trim())")
        check(lit == ["Dvoranski treninzi"], f"on the training's page the lit tab is {lit}")
        wide("the new training's page")
        if made:
            station(made[0].id, ivan, "Plank")
        with pg.expect_navigation():
            pg.locator(".pl-line a.act-quiet").first.tap()                  # ← Natrag
        pg.wait_for_load_state("networkidle")
        check(pg.url == server + "/dvoranski", f"← Natrag led to {pg.url}")
        if made:
            check(pg.locator(f"#dv-gt-{made[0].id}").count() == 1, "the training is not among the open ones")
        wide("the tab's page, its training outside a termin")
        pg.set_viewport_size({"width": 1280, "height": 900})
        pg.reload()
        pg.wait_for_load_state("networkidle")
        pg.evaluate("document.fonts.ready")
        bar = pg.evaluate(PILL)
        check(not bar["problems"] and not bar["drawer"] and len(bar["labels"]) == 7
              and "Dvoranski treninzi" in bar["labels"], f"at 1280px the bar: {bar}")
        check(pg.evaluate(OVERFLOW) == 0, "at 1280px the page overflows")
        browser.close()
    assert not problems and not errors, problems + errors


def test_a_training_planned_ahead_on_a_phone(server):
    """At 390px, touch (28.11.2026): staff (the trainer) in ivan's tab (a
    tab's view, as Dvoranski treninzi's search enters it) see the form with
    its day up to 60 days ahead, "Vrijeme (neobavezno)" and his gym plan's
    words; a day three days ahead at 10:00 and "Dodaj trening" → its page,
    the day and the time under its title and "Broji se u članarinu: Grupni
    trening."; "+ Stanica", Goblet čučanj 3 × 10 and "Spremi" (nothing
    ticked). Then ivan himself: his tab's card of it (its day and time, the
    plan's line, "Nastavi trening") and on its page the station's three rows
    ready to tick. No page scrolls sideways at 390px or 360px; no page
    errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    ivan = make_user("ivan@test.local", plans=("grupni", "online"))
    make_user("coach@test.local", is_trainer=True, plans=())
    goblet = db.create_exercise("Goblet čučanj")
    db.reset_gym_templates()
    today = config.today()
    ahead = today + timedelta(days=3)
    when = f"{day_text(ahead)} · 10:00"
    line = "Broji se u članarinu: Grupni trening."
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        def phone(email: str):
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: problems.append(f"{email}: page error: {e}"))
            pg.on("console", lambda m: problems.append(f"{email}: console: {m.text}") if m.type == "error" else None)
            pg.goto(server + "/login")
            pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); "
                        "localStorage.setItem('qmt-phone', String(Date.now())); }")
            pg.fill("main input[name=email]", email)
            pg.fill("main input[name=password]", "lozinka123")
            pg.click("main button[type=submit]")
            pg.wait_for_load_state("networkidle")
            if pg.locator("#fbPrompt[open], dialog[open]").count():           # the login's prompt: later
                pg.keyboard.press("Escape")
            return ctx, pg

        def wide(pg, where: str) -> None:
            for w, h in ((390, 844), (360, 780)):
                pg.set_viewport_size({"width": w, "height": h})
                gap = pg.evaluate(OVERFLOW)
                check(gap == 0, f"{where} at {w}px overflows by {gap}px")
            pg.set_viewport_size({"width": 390, "height": 844})

        def go(pg, tap: str) -> None:
            with pg.expect_navigation():
                pg.locator(tap).first.tap()
            pg.wait_for_load_state("networkidle")

        ctx, pg = phone("coach@test.local")
        pg.request.post(server + "/dvoranski/clan", form={"clan": str(ivan)})  # a tab's view of him
        pg.goto(server + "/dvoranski")
        pg.wait_for_load_state("networkidle")
        check(pg.is_visible("div.kao-bar") and pg.text_content("main h1") == "Dvoranski treninzi — Ivan Test",
              f"the tab's view: {pg.text_content('main h1')!r}")
        check(pg.get_attribute("#dv-day", "max") == (today + timedelta(days=60)).isoformat(), "the day's max")
        check(pg.is_visible("#dv-time") and pg.inner_text(".dv-plan-one") == "Grupni trening",
              "the time field and the plan's words")
        pg.fill("#dv-day", ahead.isoformat())
        pg.fill("#dv-time", "10:00")
        wide(pg, "staff's form in his tab")
        go(pg, "form.dv-form button[type=submit]")
        made = [t for t in db.gym_trainings(ivan) if t.session_id is None]
        check(len(made) == 1 and pg.url == f"{server}/dvoranski/trening/{made[0].id}" if made else False,
              f"Dodaj trening led to {pg.url}")
        if made:
            t = made[0]
            check((t.held_on, t.starts_at, t.plan) == (ahead, datetime.combine(ahead, dtime(10, 0), tzinfo=config.TZ),
                                                       "grupni"), f"stored: {(t.held_on, t.starts_at, t.plan)}")
            check(pg.inner_text(".gt-when > span") == when, f"the page's day and time: {pg.inner_text('.gt-when > span')!r}")
            check(pg.inner_text(".gt-head .gt-state") == line, "the counted line under the date")
            wide(pg, "the planned training's page, staff")
            go(pg, ".gt-chooser form:has(input[value=stanica]) button")
            [b] = db.gym_training(t.id, ivan).blocks
            box = pg.locator(f"#gt-s{b.id}-ex-q")
            box.tap()
            box.fill("gob")
            pg.locator(f"#gt-s{b.id}-ex-list [role=option]", has_text="Goblet čučanj").first.tap()
            pg.fill(f"#gt-s{b.id}-sets", "3")
            pg.fill(f"#gt-s{b.id}-reps", "10")
            wide(pg, "the station's form, staff")
            go(pg, "form.gt-sform button[name=spremi]")
            it = db.gym_training(t.id, ivan).blocks[0].items[0]
            check((it.exercise_id, it.sets, it.reps, it.done_sets) == (goblet, 3, 10, []),
                  f"the station written: {(it.exercise_id, it.sets, it.reps, it.done_sets)}")
            wide(pg, "the station written, staff")
        ctx.close()

        ctx, pg = phone("ivan@test.local")
        pg.goto(server + "/dvoranski")
        pg.wait_for_load_state("networkidle")
        if made:
            card = pg.locator(f"#dv-gt-{made[0].id}")
            check(card.is_visible() and card.locator(".dv-when").inner_text() == when
                  and card.locator(".dv-plan").inner_text() == line
                  and card.locator(".dv-go").inner_text() == "Nastavi trening", f"his card: {card.inner_text()!r}")
            wide(pg, "his tab with the planned training")
            go(pg, f"#dv-gt-{made[0].id} .dv-go")
            check(pg.locator("#gt-log tbody tr").count() == 3 and pg.locator("#gt-log .pl-done").first.is_visible()
                  and pg.locator("#gt-log tbody tr input").first.input_value() == "10",
                  "the station is not ready to tick: three rows of 10, each its ✓")
            wide(pg, "the planned training's page, the member")
        ctx.close()
        browser.close()
    assert not problems, problems
