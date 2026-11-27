"""The tab "Dvoranski treninzi" (27.11.2026, build 2 of
roadmap/2026-11-27-dvoranski-treninzi-plan.md).

The owner: "how long would it take to create a new tab called 'Dvoranski
treninzi' in the same level of hierarchy as the 'Online treninzi' … Maybe it
would make sense for the user to only input in the 'Dvoranski treninzi' tab
but Amir and I can always check the user's Karton?" … "I would show the tab
only to members with a gym plan. Similarly how a online training tab shows
only to members with an online plan."

Who has the tab and its page (app._has_gym: a running plan that books
termini, staff always, while staff act as a member his plans for the tab and
since the evening of 27.11.2026 the page whatever they are: the actor
decides); the page's two sections in each of their states: "Otvoreni
treninzi", since that evening everything still being written (the owner, of
"Zadnji treninzi", which went: "remove it, only list the active trainings
which Amir can see always and the user 4 hours before the slot when the
training is confirmed and cant be cancelled"): his booked termini whose
training he may write now (db.gym_open_termini), his trainings outside a
termin with no osvrt held today or yesterday, and for staff acting as him
every later booked termin however far ahead (db.gym_later_termini: "He can
see all booked slots by the users, no matter how far ahead they are"); none
open his next termin or "Nemaš otvorenih treninga."; "Trening izvan termina"
(the Karton's form, moved: POST /dvoranski/trening and its refusals, who may
make one); the way to the karton at the page's foot; the texts (gym.tab.*);
and on a phone, at 390px with touch: the tab's page, a training made outside
a termin from it, back to it, and at 1280px the bar with seven tabs. The
nav's half (the tab's place, .on, the drawer, the bar of seven measured) is
tests/test_nav.py's; the karton's (its forms gone, its rows' links)
tests/test_karton.py's and tests/test_gym.py's, and the training's page under
the tab ("← Natrag") tests/test_gym.py's. The search on staff's own tab and
the tab's view of a member it enters are tests/test_kao.py's.
"""

from __future__ import annotations

import os
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
from fastapi.testclient import TestClient
from sqlalchemy import select

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
SECTIONS = ('aria-labelledby="dv-open-h"', 'aria-labelledby="dv-new-h"')
FOOT = '<a class="act act-quiet dv-all" href="/karton#osvrti"><span class="t">Svi tvoji treninzi su u kartonu →</span></a>'


# ---------- who has the tab and the page ----------

def test_the_tab_and_its_page_follow_a_plan_that_books_termini():
    """The tab, after Karton and before Online treninzi, and its page with
    its two sections and the way to the karton at its foot: a member with
    each of the four plans that book termini (grupni, individualni,
    poluindividualni, rehabilitacija) and staff, the trainer and the owner
    (no plan of theirs). No tab, and the page the gate's one sentence
    ("Dvoranski treninzi su dio članarine za dvoranu.", /treninzi's way for
    one with no online plan, no section, no form): an online plan alone, no
    plan, a gym plan lapsed. A guest is sent to log in. Staff acting as a
    member (the whole app): his plans decide the tab, the page is his
    whatever they are (since the evening of 27.11.2026: the actor decides,
    as POST /dvoranski/trening; until then the gate for one without), his
    open termin there with a gym plan; the gate stays the member's own."""
    members = {plan: make_user(f"{plan}@test.local", plans=(plan,)) for plan in SESSION_KINDS}
    make_user("mia@test.local", plans=("online",))
    sara = make_user("sara@test.local", plans=())
    lapsed = make_user("lara@test.local", plans=("grupni", "online"))
    lapse(lapsed)
    make_user("coach@test.local", is_trainer=True, plans=())
    make_user("trener@test.local", plans=())                                # the owner, not a trainer
    for email in [f"{plan}@test.local" for plan in SESSION_KINDS] + ["coach@test.local", "trener@test.local"]:
        c = client_for(email)
        assert "Dvoranski treninzi" in tabs(c.get("/raspored").text), email
        page = c.get("/dvoranski").text
        assert all(mark in page for mark in SECTIONS) and 'class="card dv-gate"' not in page, email
        assert '<h1><span class="' in page and "<title>Dvoranski treninzi — QMT</title>" in page, email
        assert 'aria-labelledby="dv-last-h"' not in page and "Zadnji treninzi" not in page, email   # gone (27.11.2026)
        assert 'href="/karton#osvrti"' in main_of(page).split('id="trening-novi"')[1], email        # at the foot
    row = tabs(client_for("grupni@test.local").get("/raspored").text)
    assert row[row.index("Karton") + 1] == "Dvoranski treninzi"
    staff_row = tabs(client_for("coach@test.local").get("/raspored").text)
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
    assert all(mark in page for mark in SECTIONS) and 'class="card dv-gate"' not in page   # the page: staff's to use
    assert GATE in client_for("sara@test.local").get("/dvoranski").text              # the gate: hers
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
    top. Made by a member with a gym plan and by staff for themselves; by
    staff acting as a member whatever his plans (the actor decides: one with
    no gym plan too, the record holding the write); anyone else is turned
    away to the tab, which shows him the gate, nothing made (an online plan
    alone, a gym plan lapsed); a guest to the login."""
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
    assert 'id="trening-novi"' in ci.get("/dvoranski").text
    for day in ((today + timedelta(days=1)).isoformat(), "2019-12-31", "", "23.11.2026", "2026-02-30"):
        r = ci.post("/dvoranski/trening", data={"day": day}, follow_redirects=False)
        assert location(r) == "/dvoranski?error=Neispravan datum.#trening-novi", day
    assert db.gym_trainings(ivan) == []
    page = ci.get("/dvoranski?error=Neispravan datum.").text
    assert ('<div class="alert" role="alert"><span>Neispravan datum.</span></div>'
            in section(page, "dv-new-h")) and main_of(page).count('class="alert"') == 1
    r = ci.post("/dvoranski/trening", data={"day": "2021-03-04"}, follow_redirects=False)
    [t] = db.gym_trainings(ivan)
    assert location(r) == f"/dvoranski/trening/{t.id}"
    assert (t.session_id, t.title, t.starts_at, t.held_on) == (None, "", None, date(2021, 3, 4))
    assert 'class="card pl-card gt-chooser"' in ci.get(location(r)).text
    for email, uid in (("mia@test.local", mia), ("lara@test.local", lara), ("sara@test.local", sara)):
        r = client_for(email).post("/dvoranski/trening", data={"day": today.isoformat()}, follow_redirects=False)
        assert location(r) == "/dvoranski" and db.gym_trainings(uid) == [], email
    cs = client_for("coach@test.local")
    r = cs.post("/dvoranski/trening", data={"day": today.isoformat()}, follow_redirects=False)
    [mine] = db.gym_trainings(coach)
    assert location(r) == f"/dvoranski/trening/{mine.id}" and mine.held_on == today
    cs.post(f"/kao/{sara}")                                                 # acting as one with no gym plan
    r = cs.post(f"/dvoranski/trening?kao={sara}", data={"day": today.isoformat()}, follow_redirects=False)
    [hers] = db.gym_trainings(sara)
    assert location(r) == f"/dvoranski/trening/{hers.id}"
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
    """"Otvoreni treninzi" holds, after his open termini, every training of
    his outside a termin that is still being written: no osvrt saved, held
    today or yesterday (the termin's own rule, "until the end of the day
    after it"), the newest first; a card each (id dv-gt-<training>): "Trening
    izvan termina" (or, let go of its termin by a cancelled booking, the
    title it kept), its date (with its time for one that kept its start),
    what it holds, and "Upiši trening" while it holds no block, else
    "Nastavi trening", → its page. Not there: one held two days back, one
    whose osvrt is saved (the karton's alone), another member's. "Zadnji
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
    # the newest first (db.gym_trainings: its date, then the newest made): today's, then yesterday's
    assert [k for k, _ in cards(page)] == [f"dv-gt-{let_go}", f"dv-gt-{shaped}", f"dv-gt-{blank}", f"dv-gt-{started}"]
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


def test_a_member_with_no_gym_plan_gets_the_gate_and_staff_his_page():
    """A member with no gym plan (sara): the gate's sentence, no section, no
    form. Staff acting as her (either way in) get her page whatever her
    plans (the actor decides, as POST /dvoranski/trening always did): her
    booked termini (a one-off booked for her), a training outside a termin
    made for her, "← Natrag" on its page to the tab, its osvrt landing
    there."""
    sara = make_user("sara@test.local", plans=())
    make_user("coach@test.local", is_trainer=True, plans=())
    sid = termin(sara, (now() + timedelta(days=5)).replace(second=0, microsecond=0), title="Individualni")
    assert GATE in client_for("sara@test.local").get("/dvoranski").text
    cs = client_for("coach@test.local")
    cs.post(f"/kao/{sara}")
    page = cs.get("/dvoranski").text
    assert GATE not in page and all(mark in page for mark in SECTIONS)
    assert [k for k, _ in cards(page)] == [f"dv-s-{sid}"] and "Pripremi trening" in page
    r = cs.post(f"/dvoranski/trening?kao={sara}", data={"day": config.today().isoformat()}, follow_redirects=False)
    tid = int(location(r).rsplit("/", 1)[1])
    assert '<a class="act act-quiet" href="/dvoranski"><span class="t">← Natrag</span></a>' in cs.get(location(r)).text
    r = cs.post(f"/dvoranski/trening/{tid}/osvrt?kao={sara}", data={"effort": "6"}, follow_redirects=False)
    assert location(r) == "/dvoranski?ok=Trening je spremljen."


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
