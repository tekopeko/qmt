"""/moja-clanarina (18.10.2026): a member's plans, the plans to add, and the
ledger, on one page (Shape Club's billing page in QMT's look). It took over
/cjenik's price list (the old address leads here) and /profil's članarina
and payment history; the links that led to either now lead here. The Stripe
states (a card subscription, its tier switch, the portal) are in
tests/test_payments.py, which fakes Stripe.

The online plan's tiers (20.10.2026: Membership.tier, QMove START / PRO /
ELITE, the landing's three cards) are here too, on every page they show
on: their migration, the uplata that records one on /clanarine and its
forms, the landing's one owned card and the Paket fact here. The browser
half of /clanarine's form is in tests/test_copy.py, beside its walk."""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
from datetime import date, datetime, timedelta
from urllib.parse import unquote

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local,sara@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect, select, text as sa_text

from qmt import auth, config, copy, db
from qmt.models import PLAN_TYPES, Base, Membership, Payment, User, add_month
from qmt.web.app import app


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
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


def set_membership(uid: int, plan: str, **fields) -> Membership:
    """Move a membership's dates (or tier) to the state a test needs."""
    with db.session_scope() as s:
        m = s.scalar(select(Membership).where(Membership.user_id == uid, Membership.plan == plan))
        for k, v in fields.items():
            setattr(m, k, v)
        s.flush()
        s.expunge(m)
        return m


def _tag_start(page: str, mark: str, start: int = 0) -> int:
    """Where the tag holding `mark` opens (its "<"), searching from `start`;
    -1 when there is none."""
    i = page.find(mark, start)
    return -1 if i < 0 else page.rindex("<", 0, i)


def _until_next(page: str, start: int, *marks: str) -> str:
    """page[start:] up to the first tag holding one of `marks`, or </main>."""
    ends = [_tag_start(page, m, page.index(">", start)) for m in marks] + [page.find("</main>", start)]
    return page[start:min(i for i in ends if i > start)]


def section(page: str, heading_id: str) -> str:
    """One section of the page, by its heading's id, up to the next one."""
    return _until_next(page, _tag_start(page, f'aria-labelledby="{heading_id}"'), 'class="mc-sec"')


def card(page: str, key: str) -> str:
    """The plan's own card, up to the next card or section."""
    return _until_next(page, _tag_start(page, f'id="plan-{key}"'), 'id="plan-', 'class="mc-sec"')


def text(html: str) -> str:
    """What a reader sees: tags dropped, whitespace collapsed."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


D = "%-d.%-m.%Y."


# ---------- who gets the page ----------

def test_members_only_the_trainer_has_his_own_page_and_the_old_address_leads_here():
    make_user("ivan@test.local", plans=("grupni",))
    make_user("trener@test.local", is_trainer=True)
    guest, ivan, trener = TestClient(app), client_for("ivan@test.local"), client_for("trener@test.local")

    r = guest.get("/moja-clanarina", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?next=/moja-clanarina"
    r = trener.get("/moja-clanarina")                                # the trainer and the owner see it too:
    assert r.status_code == 200 and 'id="plan-grupni"' in r.text     # it is where the page's texts are edited
    assert r.text.count("Nemaš aktivnu članarinu") == 1              # no membership talk for them: only the
    assert r.text.index("Ovo vidi član bez članarine:") < r.text.index("Nemaš aktivnu članarinu")   # preview
    assert 'data-copy="cjenik.hint"' in r.text
    r = ivan.get("/moja-clanarina")
    assert r.status_code == 200 and "<h1>Moja članarina</h1>" in r.text
    assert "<title>Moja članarina — QMT</title>" in r.text
    assert copy.SLOTS["cjenik.hint"].default in r.text               # the lead keeps its slot

    # /cjenik: anyone logged in is sent on (the browser keeps a #plan-
    # fragment), a guest to log in as before
    r = ivan.get("/cjenik", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/moja-clanarina"
    r = ivan.get("/cjenik?error=Nešto", follow_redirects=False)       # a flash survives the move
    assert r.headers["location"] == "/moja-clanarina?error=Ne%C5%A1to"
    r = guest.get("/cjenik", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?next=/cjenik"
    r = trener.get("/cjenik", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/moja-clanarina"


# ---------- a cash member's page ----------

def test_cash_member_sees_a_card_per_plan_the_plans_to_add_and_the_ledger():
    uid = make_user("ivan@test.local", plans=("online", "grupni", "individualni"))
    # a tiered grupni with one termin booked in this cycle
    set_membership(uid, "grupni", sessions_per_cycle=12)
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + timedelta(days=1), 60, 8, None)
    db.book(uid, sid)
    # the ledger: an older uplata, then today's three (newest first)
    with db.session_scope() as s:
        s.add(Payment(user_id=uid, plan="grupni", method="kartica", paid_on=date(2026, 8, 3)))
    m = {x.plan: x for x in db.memberships_for(uid)}

    page = client_for("ivan@test.local").get("/moja-clanarina").text
    mine = section(page, "mcPlans")
    assert '<h2 id="mcPlans"><span class="t">Tvoji planovi</span></h2>' in mine   # a slot (clanarina.h.plans)
    # one card per plan, in PLAN_TYPES order, each saying it is active
    ids = re.findall(r'<section class="card plan-card is-active" id="plan-(\w+)"', mine)
    assert ids == ["grupni", "individualni", "online"]
    assert mine.count('<span class="chip ok">aktivna</span>') == 3
    for key in ids:
        c = text(card(page, key))
        assert c.startswith("Paket"), c[:40]
        x = m[key]
        assert f"Uplaćeno {x.paid_on:{D}}" in c and f"Sljedeća uplata {x.next_payment:{D}}" in c
        assert f"Vrijedi do {x.dospijece:{D}}" in c
        # cash: where and by when to pay, in one sentence
        assert (f"Članarina vrijedi do {x.dospijece:{D}} Sljedeću uplatu obavi do "
                f"{x.next_payment:{D}} — u dvorani, gotovinom ili karticom.") in c
        assert "/placanje" not in card(page, key)                      # Stripe is off: no card actions
    grupni = text(card(page, "grupni"))
    assert "Cijena 60–80 € / paket" in grupni                         # the shop's reference price
    assert "Paket 12 treninga mjesečno" in grupni and "Iskorišteno 1 od 12 u ovom ciklusu" in grupni
    assert 'href="/raspored">Rezerviraj termin →</a>' in card(page, "grupni")   # a running plan is a door
    assert 'href="/treninzi">Otvori online treninge →</a>' in card(page, "online")
    assert "Iskorišteno" not in text(card(page, "individualni"))      # unlimited: no usage line

    # Dodaj plan: exactly the three he does not hold, with their texts; he
    # holds online, so no QMove tier and no online group at all (21.10.2026)
    add = section(page, "mcAdd")
    assert re.findall(r'<div class="card plan[^"]*" id="plan-(\w+)"', add) == \
        ["poluindividualni", "rehabilitacija", "prehrana"]
    assert 'id="mcOnline"' not in add and add.count('class="period"') == 1
    for key in ("poluindividualni", "rehabilitacija", "prehrana"):
        assert copy.SLOTS[f"cjenik.{key}.text"].default in add
    assert add.count("Za upis se javi treneru u dvorani.") == 3        # in each card's text; cash only: no button
    assert "Pretplati se karticom" not in page and "Najpopularnije</span>" not in add   # grupni is his

    # Računi: every uplata, newest first, with plan and method
    bills = section(page, "mcBills")
    rows = [text(r) for r in re.findall(r"<tr>(.*?)</tr>", bills, re.S)][1:]   # [0] is the header
    assert len(rows) == 4
    assert rows[-1] == "3.8.2026. Grupni trening Kartica"
    assert all(r.startswith(f"{config.today():{D}}") and r.endswith("Gotovina") for r in rows[:3])
    assert "Iznos" not in bills                                       # no amounts recorded: no column
    assert "Stripe portalu" not in page


def test_a_lapsed_plan_says_so_and_one_due_soon_counts_the_days():
    uid = make_user("ivan@test.local", plans=("grupni", "online"))
    today = config.today()
    lapsed = set_membership(uid, "grupni", next_payment=today - timedelta(days=20))   # dospijeće 13 days ago
    soon = set_membership(uid, "online", next_payment=today - timedelta(days=4))      # dospijeće in 3 days

    page = client_for("ivan@test.local").get("/moja-clanarina").text
    mine = section(page, "mcPlans")
    # active first, lapsed after
    assert re.findall(r'class="card plan-card (is-\w+)" id="plan-(\w+)"', mine) == \
        [("is-active", "online"), ("is-lapsed", "grupni")]
    g = card(page, "grupni")
    assert '<span class="chip lapsed">istekla</span>' in g
    # lapsed inside the month that began at its due date: an uplata buys
    # that month (the fixed month, 29.10.2026), so it starts at the due date
    assert f"Članarina je istekla {lapsed.dospijece:{D}} Nova uplata počinje od {lapsed.next_payment:{D}}" in text(g)
    assert "Rezerviraj termin" not in g                               # no door while lapsed
    gone = set_membership(uid, "grupni", next_payment=today - timedelta(days=40))   # a whole month unpaid
    g = card(client_for("ivan@test.local").get("/moja-clanarina").text, "grupni")
    assert f"Članarina je istekla {gone.dospijece:{D}} Nova uplata počinje od dana uplate." in text(g)
    assert '<span class="chip due">dospijeva za 3 dana</span>' in card(page, "online")
    assert "Otvori online treninge" in card(page, "online")           # still running: still a door
    assert f"Vrijedi do {soon.dospijece:{D}}" in text(card(page, "online"))

    set_membership(uid, "online", next_payment=today - timedelta(days=6))   # tomorrow, then today
    assert '<span class="chip due">dospijeva sutra</span>' in client_for("ivan@test.local").get("/moja-clanarina").text
    set_membership(uid, "online", next_payment=today - timedelta(days=7))
    assert '<span class="chip due">dospijeva danas</span>' in client_for("ivan@test.local").get("/moja-clanarina").text
    set_membership(uid, "online", next_payment=today)                  # due today: the grace week is the countdown
    assert '<span class="chip due">dospijeva za 7 dana</span>' in client_for("ivan@test.local").get("/moja-clanarina").text
    set_membership(uid, "online", next_payment=today + timedelta(days=1))
    assert '<span class="chip ok">aktivna</span>' in client_for("ivan@test.local").get("/moja-clanarina").text


def test_member_without_a_plan_sees_why_every_plan_and_an_empty_ledger():
    make_user("sara@test.local")
    page = client_for("sara@test.local").get("/moja-clanarina").text
    assert 'aria-labelledby="mcPlans"' not in page                     # no "Tvoji planovi"
    none = text(_until_next(page, _tag_start(page, 'class="card mc-none"'), 'class="mc-sec"'))
    assert "Nemaš aktivnu članarinu — bez nje rezervacija nije moguća." in none
    assert "Za upis se javi treneru u dvorani — plaćanje gotovinom ili karticom." in none
    add = section(page, "mcAdd")                                      # every plan: the three tiers, then the gym's five
    assert re.findall(r'<div class="card plan[^"]*" id="plan-([\w-]+)"', add) == \
        ["online", "online-pro", "online-elite", *(p for p in PLAN_TYPES if p != "online")]
    assert '<span class="featured-tag">Najpopularnije</span>' in card(page, "grupni")
    assert "Još nema zabilježenih uplata." in section(page, "mcBills")
    assert "<table" not in page


# ---------- the fixed month (29.10.2026) ----------

def test_the_month_is_fixed_an_uplata_buys_the_month_from_the_due_date(monkeypatch):
    """The owner: the membership month runs from due date to due date and
    never moves while the client keeps paying. Due 1.5.: paying on 28.4.
    (early), 7.5. (the grace week, on trust) or 12.5. (locked out since 8.5.,
    the month still running) all buy 1.5.-1.6.; 2.6., after a whole month
    unpaid, starts afresh, 2.6.-2.7. A plan never held starts from today.
    db.next_cycle says it before; record_payment does it."""
    uid = make_user("ivan@test.local", plans=("grupni",))
    due = date(2026, 5, 1)
    for paid, buys in ((date(2026, 4, 28), date(2026, 6, 1)), (date(2026, 5, 7), date(2026, 6, 1)),
                       (date(2026, 5, 12), date(2026, 6, 1)), (date(2026, 6, 2), date(2026, 7, 2))):
        monkeypatch.setattr(config, "today", lambda paid=paid: paid)
        m = set_membership(uid, "grupni", next_payment=due)
        assert db.next_cycle(m, paid) == (buys, buys + timedelta(days=7)), paid
        m = db.record_payment(uid, "grupni")
        assert (m.paid_on, m.next_payment, m.dospijece) == (paid, buys, buys + timedelta(days=7)), paid
    assert db.next_cycle(None, date(2026, 5, 12)) == (date(2026, 6, 12), date(2026, 6, 19))
    fresh = make_user("sara@test.local")
    assert db.record_payment(fresh, "online").next_payment == date(2026, 7, 2)   # new: from today (2.6.)


def test_clanarine_says_what_an_uplata_buys_and_the_flash_names_the_same_dates():
    """Before an uplata is recorded, each plan's row says what it buys
    (db.next_cycle), the add form says it for a plan not held, "od danas";
    the flash after it names the same dates."""
    make_user("trener@test.local", is_trainer=True)
    uid = make_user("ivan@test.local", plans=("grupni", "online"))
    today = config.today()
    due = today - timedelta(days=3)                                     # in the grace week
    set_membership(uid, "grupni", next_payment=due)
    gone = today - timedelta(days=45)                                   # a whole month unpaid
    set_membership(uid, "online", next_payment=gone)
    t = client_for("trener@test.local")
    row = member_card(t.get("/clanarine").text, "ivan@test.local")
    for start in (add_month(due), add_month(today)):                    # grupni's month, online's fresh one
        line = (f'<div class="hint next-cycle">Uplata produljuje do {start:%-d.%-m.} '
                f'(vrijedi do {start + timedelta(days=7):%-d.%-m.})</div>')
        assert line in row, line
    nxt = add_month(today)
    assert (f'<p class="hint next-cycle">Uplata: od danas do {nxt:%-d.%-m.} '
            f'(vrijedi do {nxt + timedelta(days=7):%-d.%-m.})</p>') in row
    r = t.post(f"/clanarine/{uid}/uplata", data={"plan": "grupni"}, follow_redirects=False)
    m = {x.plan: x for x in db.memberships_for(uid)}["grupni"]
    assert m.next_payment == add_month(due)                             # the month that began at the due date
    assert unquote(r.headers["location"]) == (
        f"/clanarine?ok=Grupni trening: uplata evidentirana — sljedeća {add_month(due):{D}} "
        f"(vrijedi do {add_month(due) + timedelta(days=7):{D}})")


def test_a_lapsed_plans_grace_week_termini_show_on_trust_until_an_uplata():
    """The grace week is on trust: due 1.5., the client trains through 8.5.
    unpaid. A lapsed plan whose grace week holds his termini (next_payment
    through dospijeće, not canceled) says so in its row, in amber, until a
    payment lands, whichever month it buys; a plan still running says
    nothing."""
    from qmt.models import Booking
    make_user("trener@test.local", is_trainer=True)
    uid = make_user("ivan@test.local", plans=("grupni",))
    today = config.today()
    due = today - timedelta(days=10)                                    # dospijeće 3 days ago: lapsed

    def termin(day: date, canceled: bool = False):
        sid = db.add_oneoff_session("Grupni trening", datetime(day.year, day.month, day.day, 18, tzinfo=config.TZ),
                                    60, 8, None)
        with db.session_scope() as s:
            s.add(Booking(user_id=uid, session_id=sid))
        if canceled:
            db.set_session_canceled(sid, True)

    for day in (due, due + timedelta(days=4), due + timedelta(days=7)):  # the grace week, both ends counted
        termin(day)
    termin(due + timedelta(days=2), canceled=True)                      # called off: not counted
    termin(due - timedelta(days=2))                                     # the paid month: not counted
    t = client_for("trener@test.local")

    def note() -> str | None:
        m = re.search(r'<div class="trust">(.*?)</div>', member_card(t.get("/clanarine").text, "ivan@test.local"))
        return m and m.group(1)

    set_membership(uid, "grupni", next_payment=due)
    assert db.trust_bookings(uid, "grupni") == 3
    assert note() == "3 termina na povjerenje — neplaćeno"
    set_membership(uid, "grupni", next_payment=due + timedelta(days=4))   # still in its grace week: running
    assert note() is None
    set_membership(uid, "grupni", next_payment=due)
    db.record_payment(uid, "grupni")                                    # paid: the month from the due date
    assert db.trust_bookings(uid, "grupni") == 0 and note() is None
    set_membership(uid, "grupni", next_payment=today - timedelta(days=40))   # a month gone: a fresh start
    termin(today - timedelta(days=38))
    assert note() == "1 termin na povjerenje — neplaćeno"
    db.record_payment(uid, "grupni")
    assert note() is None


# ---------- the links that lead here ----------

def test_every_way_to_plans_and_money_leads_to_the_new_page():
    uid = make_user("ivan@test.local", plans=("grupni",))
    make_user("ana@test.local")
    make_user("trener@test.local", is_trainer=True)
    ivan, ana = client_for("ivan@test.local"), client_for("ana@test.local")

    page = ivan.get("/raspored").text
    # the nav tab, "Moja članarina" since 26.10.2026, and no account-menu
    # item beside it: one way there, never two (20.10.2026; staff have the
    # tab too since 26.10.2026, below)
    assert '<a href="/moja-clanarina" class="">Moja članarina</a>' in page
    assert '<a href="/moja-clanarina" class="on">Moja članarina</a>' in ivan.get("/moja-clanarina").text
    menu = page[page.index('id="userMenu"'):page.index('onclick="qmtToggleTheme()"')]
    assert 'href="/moja-clanarina"' not in menu and "<span>Moja članarina</span>" not in page
    # the timetable lists no plans since 18.10.2026 (the tab's page holds
    # them): no block, no lines, no link of its own while a plan runs
    for gone in ("<h2>Moja članarina", "Grupni trening · aktivna", "Moja članarina →",
                 'class="hint gate-line"', "mtable", "povijest plaćanja"):
        assert gone not in page, gone
    # with none running, a lapsed plan's too, the booking gate's one line
    set_membership(uid, "grupni", next_payment=config.today() - timedelta(days=30))
    page = ivan.get("/raspored").text
    assert '<p class="hint gate-line">Nemaš aktivnu članarinu — bez nje rezervacija nije moguća. ' in page
    assert "istekla" not in page                                      # the lapsed plan is the tab's to show

    # without a plan: the timetable, its month page and the plan gate's alert
    assert '<a class="btn btn-sm" href="/moja-clanarina">Pogledaj cjenik →</a>' in ana.get("/raspored").text
    assert '<a class="act" href="/moja-clanarina">Pogledaj cjenik →</a>' in ana.get("/raspored?view=month").text
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + timedelta(days=1), 60, 8, None)
    loc = ana.post(f"/book/{sid}", data={"week": ""}, follow_redirects=False).headers["location"]
    assert '<a class="act" href="/moja-clanarina#plan-grupni">Pogledaj cjenik →</a>' in ana.get(loc).text

    # the profile keeps the person's own data and a way to the rest
    profil = ivan.get("/profil").text
    assert '<a class="act" href="/moja-clanarina">Moja članarina — planovi, uplate i računi →</a>' in profil
    for gone in ("Povijest plaćanja", "Dospijeće plaćanja", "/placanje/portal"):
        assert gone not in profil, gone

    # the landing: a member's card for a plan he does not hold
    assert 'href="/moja-clanarina#plan-online">Odaberi plan →</a>' in ivan.get("/").text

    # the trainer manages members elsewhere (Admin ▾'s Trenutne članarine):
    # no membership links for him, but the member's row has the tab since
    # 26.10.2026: it is where he edits the plans' texts (the page shows him
    # no plans of his own). The account menu has no item for it any more.
    for path in ("/raspored", "/profil"):
        page = client_for("trener@test.local").get(path).text
        assert '<a href="/moja-clanarina" class="">Moja članarina</a>' in page, path   # the nav tab
        assert "Moja članarina →" not in page, path                        # the member links
        menu = page[page.index('id="userMenu"'):page.index('onclick="qmtToggleTheme()"')]
        assert 'href="/moja-clanarina"' not in menu, path                  # no menu item
        assert "<span>Moja članarina</span>" not in page, path


def test_the_profile_and_the_account_menu_show_the_whole_email():
    """The email again on /profil (20.10.2026, the owner: "the email address
    should show somewhere in the 'Profil' tab"; the 18.10. task had dropped
    the Račun card with the plans): under the basic-info form, above the
    link to the plans, the Račun card says it as plain text, not a field,
    and since when the account exists, in the studio's time zone. The
    account menu's header cuts a long address with an ellipsis on a desktop,
    so its line carries the whole address as its title, for a hover."""
    uid = make_user("ivan@test.local", plans=("grupni",))
    page = client_for("ivan@test.local").get("/profil").text
    start = page.index('<div class="card acct">')
    card = page[start:page.index("</div>", start)]
    since = db.get_user(uid).created_at.astimezone(config.TZ)
    assert "<h2>Račun</h2>" in card and '<p class="mail">ivan@test.local</p>' in card
    assert f"Registriran/a od {since:%-d.%-m.%Y.}" in card and "<input" not in card
    assert page.index('action="/profil"') < start < page.index('class="card mc-link"')
    assert '<span class="mail" title="ivan@test.local">ivan@test.local</span>' in page   # the menu's header


# ---------- the page's own words (copy slots, 18.10.2026) ----------

def test_the_headings_and_the_plans_names_are_the_owners_text_on_this_page_only():
    """The page's own words are copy slots: its three headings and the
    plans' names on its cards, a plan held and a plan to add. A name is this
    page's own: edited to "Grupa", the cards here say it, while the pages
    that name the app's records keep PLAN_LABELS, the trainer's /clanarine
    and this page's ledger among them."""
    make_user("ivan@test.local", plans=("grupni",))
    make_user("sara@test.local")
    make_user("trener@test.local", is_trainer=True)
    t = client_for("trener@test.local")
    for key, txt in (("plan.grupni.name", "Grupa"), ("clanarina.h.plans", "Moji paketi"),
                     ("clanarina.h.add", "Još planova"), ("clanarina.h.bills", "Uplate")):
        assert t.post(f"/copy/{key}", data={"text": txt}).json() == {"ok": True, "text": txt, "default": False}, key

    page = client_for("ivan@test.local").get("/moja-clanarina").text
    assert '<h2 id="mcPlans"><span class="t">Moji paketi</span></h2>' in page
    assert '<h3 id="pc-grupni"><span class="t">Grupa</span></h3>' in card(page, "grupni")   # his plan's card
    assert '<h2 id="mcAdd"><span class="t">Još planova</span></h2>' in page
    assert '<h2 id="mcBills"><span class="t">Uplate</span></h2>' in page
    bills = section(page, "mcBills")
    assert "Grupni trening" in bills and "Grupa<" not in bills       # the ledger names the record
    sara = client_for("sara@test.local").get("/moja-clanarina").text
    assert '<h4 class="plan-h"><span class="t">Grupa</span></h4>' in card(sara, "grupni")   # a plan to add
    assert '<h4 class="plan-h"><span class="t">Individualni trening</span></h4>' in card(sara, "individualni")

    clanarine = t.get("/clanarine").text                              # the app's own names stay
    assert "<strong>Grupni trening</strong>" in clanarine and "Grupa<" not in clanarine
    assert 'data-copy="plan.' not in clanarine                       # and are no slot there
    editor = t.get("/moja-clanarina").text                           # the editor gets every one to open
    for key in ("clanarina.h.plans", "clanarina.h.add", "clanarina.h.online", "clanarina.h.gym",
                "clanarina.h.bills", *(f"plan.{p}.name" for p in PLAN_TYPES if p != "online")):
        assert f'data-copy="{key}"' in editor, key
    assert 'data-copy="plan.online.name"' not in section(editor, "mcAdd")   # the tiers: their cards' titles


def test_the_no_plan_card_is_the_owners_text_and_the_editor_sees_it_as_a_preview():
    """A member without a plan sees the card in place of Tvoji planovi, its
    two sentences the clanarina.none.* slots, and the empty ledger's line is
    a slot too. The trainer and the owner hold no plans and are told no
    membership talk, so the card would be on no page they open: an editor
    gets it as a preview, in the section under its heading, after a caption
    that says whose view it is (static, not a slot). (The line under
    "Pretplati se karticom" was a slot of its own, clanarina.card_hint,
    until 21.10.2026: a line of every Dodaj plan card's one text since.)"""
    make_user("sara@test.local")
    make_user("trener@test.local", is_trainer=True)
    db.set_copy("clanarina.none.title", "Bez plana nema rezervacija.", None)
    db.set_copy("clanarina.none.text", "Javi se u dvorani.", None)
    db.set_copy("clanarina.bills.empty", "Nema uplata.", None)

    page = client_for("sara@test.local").get("/moja-clanarina").text
    none = _until_next(page, _tag_start(page, 'class="card mc-none"'), 'class="mc-sec"')
    assert '<p><span class="t">Bez plana nema rezervacija.</span></p>' in none
    assert '<p class="hint"><span class="t">Javi se u dvorani.</span></p>' in none
    assert "Ovo vidi član bez članarine" not in page and 'aria-labelledby="mcPlans"' not in page
    assert '<p class="hint"><span class="t">Nema uplata.</span></p>' in section(page, "mcBills")

    page = client_for("trener@test.local").get("/moja-clanarina").text
    plans = section(page, "mcPlans")                                 # heading, caption, the card
    assert 'data-copy="clanarina.h.plans"' in plans and 'class="plan-cards"' not in plans
    caption = plans.index('<p class="hint mc-preview">Ovo vidi član bez članarine:</p>')
    preview = plans[plans.index('<div class="card mc-none">'):]
    assert caption < plans.index('<div class="card mc-none">')
    for key, txt in (("clanarina.none.title", "Bez plana nema rezervacija."), ("clanarina.none.text", "Javi se u dvorani.")):
        assert f'data-copy="{key}"' in preview and f">{txt}</span>" in preview, key
    assert 'data-copy="clanarina.bills.empty"' in section(page, "mcBills")
    assert "Pretplati se karticom" not in section(page, "mcAdd")    # no card payments for anyone


def test_the_trainers_page_leads_to_the_members_page():
    """The trainer's way to the members' page was an account-menu item that
    was easy to miss (the owner, 18.10.2026: "How will my friend be able to
    even change the 'moja članarina' tab then?"). So /clanarine, the
    trainer's and the owner's page for the members' payments ("Trenutne
    članarine" since 26.10.2026, Admin ▾'s item), says under its lead where
    the members' page is and that its texts and prices are edited there.
    The bar's way there is one, never two: since 26.10.2026 the Moja
    članarina tab in staff's member row, for the trainer and for an owner
    who does not train alike, and no menu item. A client never reaches
    /clanarine."""
    make_user("ivan@test.local", plans=("grupni",))
    make_user("trener@test.local")                                   # the owner (OWNER_EMAIL), not a trainer
    make_user("coach@test.local", is_trainer=True)                   # a trainer
    link = '<a class="act" href="/moja-clanarina">Moja članarina →</a>'
    for email in ("coach@test.local", "trener@test.local"):
        page = client_for(email).get("/clanarine").text
        assert "Stranica koju vide članovi — cjenik, tekstovi i cijene uređuju se tamo:" in text(page), email
        assert "<title>Trenutne članarine — QMT</title>" in page, email
        assert page.index("<h1>Trenutne članarine</h1>") < page.index(link), email
        assert page.index(link) < page.index('href="/karton/'), email   # above the roster
        assert '<a href="/moja-clanarina" class="">Moja članarina</a>' in page, email   # the nav tab
        assert "<span>Moja članarina</span>" not in page, email        # no account-menu item
    assert client_for("ivan@test.local").get("/clanarine").status_code == 403
    r = TestClient(app).get("/clanarine", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


# ---------- Dodaj plan: two groups, a card one text (21.10.2026) ----------
#
# The owner, of "Dodaj plan" in edit mode (six cards, each a heading, a
# lead, the price, a note and two hints, every piece its own box): "every
# tab is one big text cell except the number i.e. price which is connected
# to the front page. Here, it should also be split into the QMOVE online
# trainings with 'godišnje' as default and everything else in the gym
# separate with 'mjesečni' as default."

def group(page: str, heading_id: str) -> str:
    """One of Dodaj plan's groups, by its heading's id, up to the next group
    or section."""
    return _until_next(page, _tag_start(page, f'aria-labelledby="{heading_id}"'), 'class="mc-group"', 'class="mc-sec"')


def cards_in(markup: str) -> dict[str, str]:
    """The Dodaj plan cards in some markup, by their ids (plan-<id>), each
    from its class list to the next card."""
    return {re.search(r'id="plan-([\w-]+)"', part).group(1): part for part in markup.split('<div class="card plan')[1:]}


def shown_lines(markup: str) -> list[str]:
    """The periods of a card's price lines that are not hidden."""
    return re.findall(r'<div class="price" data-period="(\w+)">', markup)


def test_dodaj_plan_is_two_groups_each_with_its_own_switch():
    """Dodaj plan is two groups, each its heading (a slot) and its own
    Mjesečno / Godišnje switch (_period.html), a [data-period-group] whose
    cards' prices base.html's script flips (in a browser:
    tests/test_copy.py). Online first: the landing's three QMove tiers,
    named by their cards' title slots (a rename shows on both pages),
    opening on Godišnje: every tier's yearly line shown, its monthly hidden.
    Then the gym's plans in PLAN_TYPES order, opening on Mjesečno, the
    other way round. A plan held is left out, all three tiers when it is
    online, and a group left with no card is not on the page (ivan holds
    online: no online group). Sara holds none: every card."""
    make_user("trener@test.local", is_trainer=True)
    make_user("ivan@test.local", plans=("grupni", "individualni", "online"))
    make_user("sara@test.local")
    t = client_for("trener@test.local")
    assert t.post("/copy/offer.online2.title", data={"text": "QMove PRO+"}).json()["text"] == "QMove PRO+"

    page = t.get("/moja-clanarina").text
    add = section(page, "mcAdd")
    assert add.count("data-period-group") == 2 and add.count('class="period"') == 2
    assert add.index('id="mcOnline"') < add.index('id="mcGym"')
    online, gym = group(page, "mcOnline"), group(page, "mcGym")
    assert '<h3 class="pc-kicker" id="mcOnline"><span class="ed t" data-copy="clanarina.h.online"' in online
    assert '<h3 class="pc-kicker" id="mcGym"><span class="ed t" data-copy="clanarina.h.gym"' in gym
    tab = '<button type="button" role="tab" aria-selected="{}" data-period="{}">{}</button>'
    for markup, start in ((online, "year"), (gym, "month")):    # each switch says its group's opening
        assert markup.count('class="period"') == 1 and '<div class="period" role="tablist"' in markup
        assert tab.format(str(start == "month").lower(), "month", "Mjesečno") in markup, start
        assert tab.format(str(start == "year").lower(), "year", "Godišnje") in markup, start
    tiers = cards_in(online)                                     # the tiers by their landing titles, in order
    assert list(tiers) == ["online", "online-pro", "online-elite"]
    for markup, slot in zip(tiers.values(), ("offer.online", "offer.online2", "offer.online3")):
        assert f'<h4 class="plan-h"><span class="ed t" data-copy="{slot}.title"' in markup, slot
        assert shown_lines(markup) == ["year"] and markup.count('data-period="month" hidden>') == 1, slot
    assert ">QMove PRO+</span></h4>" in tiers["online-pro"]       # the landing card's title, renamed
    plans = cards_in(gym)                                        # the gym's plans, each opening monthly
    assert list(plans) == [p for p in PLAN_TYPES if p != "online"]
    for key, markup in plans.items():
        assert f'data-copy="plan.{key}.name"' in markup, key
        assert shown_lines(markup) == ["month"] and markup.count('data-period="year" hidden>') == 1, key

    page = client_for("ivan@test.local").get("/moja-clanarina").text   # online held: no tier, no group
    add = section(page, "mcAdd")
    assert 'id="mcOnline"' not in add and "QMove" not in add and add.count('class="period"') == 1
    assert list(cards_in(group(page, "mcGym"))) == ["poluindividualni", "rehabilitacija", "prehrana"]
    page = client_for("sara@test.local").get("/moja-clanarina").text   # nothing held: every card
    assert list(cards_in(group(page, "mcOnline"))) == ["online", "online-pro", "online-elite"]
    assert list(cards_in(group(page, "mcGym"))) == [p for p in PLAN_TYPES if p != "online"]
    assert "data-copy" not in section(page, "mcAdd")                    # a member's: no editor markup


def test_a_plan_card_is_its_name_its_prices_and_one_text():
    """A Dodaj plan card is its name, its two price lines and ONE text, in
    that order (then the button while Stripe sells the plan:
    tests/test_payments.py). The text is a slot, cjenik.<plan>.text
    (cjenik.online.<tier>.text for a tier), whose default is what the card
    said in its pieces until 21.10.2026, a line each: for grupni its lead,
    its note, "Za upis…" and the card line. An edit shows, line breaks and
    all; emptied it stays empty, and a member gets no paragraph for it, the
    editor an empty box; Zadano brings the four lines back. The pieces left
    the registry, and POST /copy/{key} knows them no more."""
    make_user("trener@test.local", is_trainer=True)
    make_user("sara@test.local")
    gone = [*(f"cjenik.{p}" for p in PLAN_TYPES), "cjenik.note", "clanarina.card_hint",
            *(f"price.{p}.note" for p in PLAN_TYPES)]
    assert not set(gone) & set(copy.SLOTS)
    end = "Za upis se javi treneru u dvorani.\nMjesečno, otkazivo bilo kad. Ili gotovinom u dvorani."
    four = "Satni termini u malim grupama do 8 polaznika — rezerviraš u rasporedu.\n8, 12 ili 16 treninga\n" + end
    assert copy.SLOTS["cjenik.grupni.text"] == copy.Slot(four, copy.CAP, "Članarina: tekst plana · grupni")
    assert copy.SLOTS["cjenik.individualni.text"].default == "Rad 1:1 s trenerom, termini po dogovoru.\n" + end
    for n, tier in enumerate(("start", "pro", "elite"), start=1):   # each tier starts with the online plan's lines
        assert copy.SLOTS[f"cjenik.online.{tier}.text"] == copy.Slot(
            "Programi po tvojoj razini i cilju, s video uputama — gdje god jesi.\n" + end, copy.CAP,
            f"Članarina: tekst plana · online {n}")
    t = client_for("trener@test.local")
    for key in gone:
        assert t.post(f"/copy/{key}", data={"text": "x"}).status_code == 404, key

    def grupni(c) -> str:
        return cards_in(section(c.get("/moja-clanarina").text, "mcAdd"))["grupni"]

    sara = client_for("sara@test.local")
    g = grupni(sara)
    assert f'<p class="plan-desc"><span class="t">{four}</span></p>' in g
    at = [g.index(mark) for mark in ('<h4 class="plan-h">', 'data-period="month"', 'data-period="year"', 'class="plan-desc"')]
    assert at == sorted(at) and g.count("plan-desc") == 1 and "price-hint" not in g   # one text, no note
    r = t.post("/copy/cjenik.grupni.text", data={"text": "Male grupe.\n\nJavi se treneru."})
    assert r.json() == {"ok": True, "text": "Male grupe.\n\nJavi se treneru.", "default": False}
    assert '<p class="plan-desc"><span class="t">Male grupe.\n\nJavi se treneru.</span></p>' in grupni(sara)
    r = t.post("/copy/cjenik.grupni.text", data={"text": " \n "})    # emptied: it stays empty
    assert r.json() == {"ok": True, "text": "", "default": False}
    assert "plan-desc" not in grupni(sara) and "Male grupe" not in grupni(sara)
    assert ('<p class="plan-desc"><span class="ed t" data-copy="cjenik.grupni.text" data-max="2000" '
            'data-label="Članarina: tekst plana · grupni"></span></p>') in grupni(t)
    r = t.post("/copy/cjenik.grupni.text", data={"text": "x", "reset": "1"})
    assert r.json() == {"ok": True, "text": four, "default": True} and db.copy_texts() == {}


def test_no_price_carries_a_note_and_prehranas_hint_keeps_the_two_amounts():
    """_plan_price.html prints no note under a price since 21.10.2026 (the
    price.<plan>.note slots went; grupni's and rehabilitacija's notes are
    lines of their Dodaj plan texts): not on a Dodaj plan card, not under a
    held plan's Cijena, not for the editor. Prehrana's hint, the
    MojiMakrosi add-on's two amounts (addon.dvorana, addon.online), still
    prints under its price: on its Dodaj plan card under both price lines,
    and under a member's own card's Cijena."""
    make_user("trener@test.local", is_trainer=True)
    make_user("ivan@test.local", plans=("grupni", "rehabilitacija", "prehrana"))
    ivan = client_for("ivan@test.local").get("/moja-clanarina").text
    for key in ("grupni", "rehabilitacija"):                       # his own cards: the price alone under Cijena
        cijena = card(ivan, key).split("<dt>Cijena</dt>")[1].split("</dd>")[0]
        assert cijena.count('<div class="price">') == 1 and "price-hint" not in cijena, key
    assert "8, 12 ili 16 treninga" not in card(ivan, "grupni") and "paketi od 5" not in card(ivan, "rehabilitacija")
    assert "Cijena od 3 € / mjesečno 3 € uz dvoranu, 5 € uz online Uplaćeno" in text(card(ivan, "prehrana"))
    editor = client_for("trener@test.local").get("/moja-clanarina").text
    assert not re.search(r'data-copy="price\.\w+\.note"', editor)
    prehrana = cards_in(section(editor, "mcAdd"))["prehrana"]      # its card to add: the hint after both lines
    assert '<div class="hint price-hint"><span class="ed t" data-copy="addon.dvorana"' in prehrana
    assert 'data-copy="addon.online"' in prehrana
    assert "od 3 € / mjesečno na upit 3 € uz dvoranu, 5 € uz online" in text(prehrana)


# ---------- the online plan's tiers (20.10.2026) ----------
#
# The owner: "The online training tiers should be the same as the QMOVE tabs
# and depending which tier is paid/unlocked, that tier the user is only
# allowed to use." Membership.tier (start / pro / elite: the landing's three
# QMove cards), recorded with each uplata on /clanarine; the landing owns one
# card, this page names it. The app's gates stay per plan: any active online
# plan opens /treninzi (tests/test_karton.py), whatever its tier.

def _migration(file: str):
    """An Alembic revision's module, loaded from its file."""
    path = pathlib.Path(__file__).parents[1] / "alembic" / "versions" / file
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _run(step) -> None:
    """A revision's upgrade() or downgrade(), run for real on qmt_test."""
    with db.engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        step()


def test_the_migration_gives_every_online_membership_the_base_tier_and_back():
    """914d4b4556e5 adds memberships.tier and gives every online row already
    there 'start', the base tier (prod has one, Marko Horvat's); every other
    plan's stays NULL. Run on qmt_test as a database from before the revision
    is: the rows there, the column not. Downgrade drops the column."""
    mig = _migration("914d4b4556e5_membership_online_tier.py")
    ivan = make_user("ivan@test.local", plans=("online", "grupni"))
    ana = make_user("ana@test.local", plans=("online",))
    with db.engine.begin() as conn:
        conn.execute(sa_text("ALTER TABLE memberships DROP COLUMN tier"))
    _run(mig.upgrade)
    with db.engine.begin() as conn:
        rows = {tuple(r) for r in conn.execute(sa_text("SELECT user_id, plan, tier FROM memberships"))}
    assert rows == {(ivan, "online", "start"), (ivan, "grupni", None), (ana, "online", "start")}
    assert db.online_tier(ivan) == "start"                              # the app reads it
    _run(mig.downgrade)
    assert "tier" not in {c["name"] for c in sa_inspect(db.engine).get_columns("memberships")}


def test_each_uplata_restates_the_online_tier_and_no_other_plan_has_one():
    """record_payment(tier=): an online uplata names its QMove tier and the
    next one restates it; none named, or a word that is no tier, keeps the
    row's tier (a Stripe renewal names none: it never demotes a member),
    START for a new row. No other plan has one, whatever is passed (grupni keeps its own, the
    treninga a month). db.online_tier is the running online plan's: a row
    from before the tiers (NULL) reads as START, a lapsed plan or none as
    None."""
    uid = make_user("ivan@test.local")
    assert db.online_tier(uid) is None                                  # no online plan
    assert db.record_payment(uid, "online", tier="pro").tier == "pro"
    assert db.online_tier(uid) == "pro"
    assert db.record_payment(uid, "online", tier="elite").tier == "elite"   # the next uplata restates it
    assert db.online_tier(uid) == "elite"
    assert db.record_payment(uid, "online").tier == "elite"             # none named: the row's tier kept
    assert db.record_payment(uid, "online", tier="gold").tier == "elite"    # no such tier: kept too
    other = make_user("sara@test.local")
    assert db.record_payment(other, "online").tier == "start"           # a new row, none named: the base tier
    g = db.record_payment(uid, "grupni", tier="pro", sessions_per_cycle=12)
    assert g.tier is None and g.sessions_per_cycle == 12                # grupni: no QMove tier, its own kept
    set_membership(uid, "online", tier=None)                            # a row from before the tiers
    assert db.online_tier(uid) == "start"
    set_membership(uid, "online", tier="pro", next_payment=config.today() - timedelta(days=8))
    assert db.online_tier(uid) is None and db.active_plan_kinds(uid) == {"grupni"}   # lapsed yesterday


def test_the_trainer_records_the_online_tier_and_the_flash_names_it():
    """POST /clanarine/{id}/uplata takes the QMove tier with plan=online, and
    the flash names it by its card's title, as grupni's names its treninga;
    the card renamed, the flash says the new name. None sent is START. With
    another plan a tier sent is ignored. A client is refused, as before."""
    make_user("trener@test.local", is_trainer=True)
    uid = make_user("ivan@test.local")
    t = client_for("trener@test.local")

    def uplata(**data) -> str:
        r = t.post(f"/clanarine/{uid}/uplata", data=data, follow_redirects=False)
        assert r.status_code == 303, r.status_code
        return unquote(r.headers["location"])

    loc = uplata(plan="online", tier="elite")
    m = {x.plan: x for x in db.memberships_for(uid)}["online"]
    assert m.tier == "elite"
    assert loc == (f"/clanarine?ok=Online trening (QMove ELITE): uplata evidentirana — "
                   f"sljedeća {m.next_payment:{D}} (vrijedi do {m.dospijece:{D}})")
    db.set_copy("offer.online3.title", "", None)                        # the title emptied: the default names the tier
    assert copy.online_tier_names(db.copy_texts())["elite"] == "QMove ELITE"
    db.set_copy("offer.online3.title", "QMove ELITE+", None)            # the card renamed: the tier with it
    assert uplata(plan="online", tier="elite").startswith("/clanarine?ok=Online trening (QMove ELITE+): uplata evidentirana — ")
    # none sent: the row's tier is kept (a Stripe renewal names none); a new row with none sent is START
    assert "(QMove ELITE+)" in uplata(plan="online") and db.online_tier(uid) == "elite"
    fresh = make_user("sara@test.local")
    assert "(QMove START)" in unquote(t.post(f"/clanarine/{fresh}/uplata", data={"plan": "online"},
                                              follow_redirects=False).headers["location"])
    assert db.online_tier(fresh) == "start"
    loc = uplata(plan="grupni", tier="pro", sessions="12")              # grupni: the tier ignored
    g = {x.plan: x for x in db.memberships_for(uid)}["grupni"]
    assert g.tier is None and g.sessions_per_cycle == 12
    assert loc.startswith("/clanarine?ok=Grupni trening (12 treninga/mj): uplata evidentirana — ") and "QMove" not in loc
    r = client_for("ivan@test.local").post(f"/clanarine/{uid}/uplata", data={"plan": "online", "tier": "pro"},
                                           follow_redirects=False)
    assert r.status_code == 403 and db.online_tier(uid) == "elite"      # a client changes nothing


def tier_cards(page: str) -> dict[str, str]:
    """The landing's three QMove cards (#usluge) by their titles (a
    visitor's span or an editor's), each from its class list on."""
    offer = page.split('id="usluge"')[1].split("</section>")[0]
    return {re.search(r'<h3><span class="(?:ed )?t"[^>]*>(.*?)</span></h3>', markup).group(1): markup
            for markup in offer.split('<div class="card offer')[1:]}


def owned(cards: dict[str, str]) -> list[str]:
    """The cards marked as the visitor's own (.mine)."""
    return [name for name, markup in cards.items() if "mine" in markup[:markup.index('"')].split()]


def test_the_landing_owns_only_the_card_of_the_members_tier():
    """A member with the online plan owns one QMove card, his tier's: its
    border (.mine) and its button into the app, "✓ Otvori online
    treninge →". The other two offer him what any member gets, "Odaberi
    plan →" to the plan's card here. An uplata that moves him moves the
    card; a row from before the tiers (NULL) owns START; a member without
    the plan, or with a lapsed one, owns none. The gym's cards follow their
    plans as before."""
    ivan = make_user("ivan@test.local", plans=("grupni",))
    db.record_payment(ivan, "online", tier="pro")
    ana = make_user("ana@test.local")
    with db.session_scope() as s:                                       # inserted as before the tiers: NULL
        s.add(Membership(user_id=ana, plan="online", paid_on=config.today(), next_payment=add_month(config.today())))
    make_user("sara@test.local")
    make_user("trener@test.local", is_trainer=True)
    db.add_gym_card(None, copy.GYM_CARD_EXAMPLES[0])                    # Dvorana: his grupni's card
    c = client_for("ivan@test.local")
    choose = 'href="/moja-clanarina#plan-online">Odaberi plan →</a>'

    page = c.get("/").text
    cards = tier_cards(page)
    assert list(cards) == ["QMove START", "QMove PRO", "QMove ELITE"]
    assert owned(cards) == ["QMove PRO"] and cards["QMove PRO"].startswith(' featured mine">')
    assert '<a class="btn btn-sm owned" href="/treninzi"' in cards["QMove PRO"]
    assert 'title="Aktivna članarina">✓ Otvori online treninge →</a>' in cards["QMove PRO"]
    assert page.count("Otvori online treninge") == 1
    for name in ("QMove START", "QMove ELITE"):
        assert f'<a class="btn btn-sm cta" {choose}' in cards[name] and "owned" not in cards[name], name
    gym = page.split('id="dvorana"')[1]                                 # the gym's cards: as before
    assert '<div class="card offer mine">' in gym and 'title="Aktivna članarina">✓ Rezerviraj termin →</a>' in gym

    client_for("trener@test.local").post(f"/clanarine/{ivan}/uplata", data={"plan": "online", "tier": "elite"})
    cards = tier_cards(c.get("/").text)                                 # moved to ELITE: the card moves
    assert owned(cards) == ["QMove ELITE"] and "✓ Otvori online treninge →" in cards["QMove ELITE"]
    assert f'<a class="btn btn-sm" {choose}' in cards["QMove PRO"]      # featured: the red button again
    assert f'<a class="btn btn-sm cta" {choose}' in cards["QMove START"]

    assert owned(tier_cards(client_for("ana@test.local").get("/").text)) == ["QMove START"]
    cards = tier_cards(client_for("sara@test.local").get("/").text)    # no online plan: none
    assert owned(cards) == [] and all(choose in markup for markup in cards.values())
    set_membership(ivan, "online", next_payment=config.today() - timedelta(days=8))   # lapsed: none
    assert owned(tier_cards(c.get("/").text)) == []
    assert owned(tier_cards(client_for("trener@test.local").get("/").text)) == []   # no plans of his own


def test_moja_clanarina_names_the_online_tier_by_its_cards_title():
    """The online plan's card here says its tier as grupni's says "12
    treninga mjesečno": a Paket fact, the tier's name, printed through the
    slot that titles its QMove card on the landing, so a rename through
    /copy/ shows on both pages. Grupni's Paket is as it was; a plan with no
    tier has none."""
    ivan = make_user("ivan@test.local", plans=("grupni", "individualni"))
    db.record_payment(ivan, "online", tier="pro")
    set_membership(ivan, "grupni", sessions_per_cycle=12)
    make_user("trener@test.local", is_trainer=True)
    c = client_for("ivan@test.local")

    page = c.get("/moja-clanarina").text
    online = card(page, "online")
    assert '<div><dt>Paket</dt><dd><span class="t">QMove PRO</span></dd></div>' in online
    assert "Paket QMove PRO" in text(online)
    assert "Paket 12 treninga mjesečno" in text(card(page, "grupni")) and "QMove" not in card(page, "grupni")
    assert "<dt>Paket</dt>" not in card(page, "individualni")

    r = client_for("trener@test.local").post("/copy/offer.online2.title", data={"text": "QMove PRO+"})
    assert r.json() == {"ok": True, "text": "QMove PRO+", "default": False}
    assert '<dd><span class="t">QMove PRO+</span></dd>' in card(c.get("/moja-clanarina").text, "online")
    assert owned(tier_cards(c.get("/").text)) == ["QMove PRO+"]        # the landing's card, the same slot


def member_card(page: str, email: str) -> str:
    """A member's card on /clanarine, up to the next member's."""
    head = '<div class="card" style="padding:14px 18px; margin-bottom:14px; max-width:860px;">'
    return next(m for m in page.split(head)[1:] if f'<span class="hint">{email}</span>' in m)


def select_in(html: str, opening: str) -> list[tuple[str, bool, str]]:
    """The options of the select that opens with `opening`: (value, selected, text)."""
    select = html[html.index(opening):]
    return [(value, bool(sel), name) for value, sel, name in
            re.findall(r'<option value="([^"]*)"( selected)?>([^<]*)</option>', select[:select.index("</select>")])]


def test_the_clanarine_forms_offer_the_tiers_by_name():
    """/clanarine records the tier: the add form has a Paket select, the
    three QMove names, beside grupni's Treninga mjesečno, and an online row
    its own, on the member's tier, so the next uplata can move him (a row
    from before the tiers is on START). The names are the cards' titles,
    the gym owner's text. The markup carries both of the add form's selects
    (without JavaScript both show); the page's script shows the one that
    fits the chosen plan (tests/test_copy.py, in a browser)."""
    make_user("trener@test.local", is_trainer=True)
    ivan = make_user("ivan@test.local", plans=("grupni",))
    db.record_payment(ivan, "online", tier="pro")
    make_user("sara@test.local")
    db.set_copy("offer.online3.title", "QMove ELITE+", None)
    t = client_for("trener@test.local")
    names = [("start", "QMove START"), ("pro", "QMove PRO"), ("elite", "QMove ELITE+")]

    page = t.get("/clanarine").text
    add = member_card(page, "sara@test.local")
    add = add[add.index('<select name="plan"'):add.index("</form>")]
    assert select_in(add, '<select name="tier" aria-label="Paket (samo online)"') == [(v, False, n) for v, n in names]
    assert select_in(add, '<select name="sessions" aria-label="Treninga mjesečno (samo grupni)"')[0] == ("", False, "neograničeno")
    assert " hidden" not in add                                         # the server hides neither

    def rows(page: str) -> dict[str, str]:
        """ivan's plan rows' uplata forms, by plan."""
        html = member_card(page, "ivan@test.local")
        return {plan: html[html.index(f'<input type="hidden" name="plan" value="{plan}">'):].split("</form>")[0]
                for plan in ("grupni", "online")}

    online = rows(page)["online"]
    assert select_in(online, '<select name="tier" aria-label="Paket"') == [(v, v == "pro", n) for v, n in names]
    assert 'name="tier"' not in rows(page)["grupni"] and 'name="sessions"' in rows(page)["grupni"]
    assert 'name="sessions"' not in online
    set_membership(ivan, "online", tier=None)                           # a row from before the tiers: START
    online = rows(t.get("/clanarine").text)["online"]
    assert select_in(online, '<select name="tier" aria-label="Paket"') == [(v, v == "start", n) for v, n in names]
