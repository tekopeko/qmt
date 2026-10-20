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

    # Dodaj plan: exactly the three he does not hold, with their descriptions
    add = section(page, "mcAdd")
    assert re.findall(r'<div class="card plan[^"]*" id="plan-(\w+)"', add) == \
        ["poluindividualni", "rehabilitacija", "prehrana"]
    for key in ("poluindividualni", "rehabilitacija", "prehrana"):
        assert copy.SLOTS[f"cjenik.{key}"].default in add
    assert add.count(copy.SLOTS["cjenik.note"].default) == 3           # cash only: the note, no button
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
    assert f"Članarina je istekla {lapsed.dospijece:{D}} Nova uplata počinje od dana uplate." in text(g)
    assert "Rezerviraj termin" not in g                               # no door while lapsed
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
    add = section(page, "mcAdd")
    assert re.findall(r'<div class="card plan[^"]*" id="plan-(\w+)"', add) == list(PLAN_TYPES)
    assert '<span class="featured-tag">Najpopularnije</span>' in card(page, "grupni")
    assert "Još nema zabilježenih uplata." in section(page, "mcBills")
    assert "<table" not in page


# ---------- the links that lead here ----------

def test_every_way_to_plans_and_money_leads_to_the_new_page():
    uid = make_user("ivan@test.local", plans=("grupni",))
    make_user("ana@test.local")
    make_user("trener@test.local", is_trainer=True)
    ivan, ana = client_for("ivan@test.local"), client_for("ana@test.local")

    page = ivan.get("/raspored").text
    # the nav tab, and no account-menu item beside it: one way there, never
    # two (20.10.2026; the item is the trainer's, who has no tab, below)
    assert '<a href="/moja-clanarina" class="">Članarina</a>' in page
    assert '<a href="/moja-clanarina" class="on">Članarina</a>' in ivan.get("/moja-clanarina").text
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

    # the trainer manages members elsewhere: no tab and no membership links
    # for him, but the account menu has the item (between Profil and the
    # theme): it is where he edits the plans' texts (the page shows him no
    # plans of his own)
    for path in ("/raspored", "/profil"):
        page = client_for("trener@test.local").get(path).text
        assert ">Članarina</a>" not in page, path                          # the client's nav tab
        assert "Moja članarina →" not in page, path                        # the member links
        menu = page[page.index('id="userMenu"'):page.index('onclick="qmtToggleTheme()"')]
        assert "<span>Moja članarina</span>" in menu, path                 # the menu item
        assert menu.index('href="/profil"') < menu.index('href="/moja-clanarina"'), path


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
    assert '<h3 class="plan-h"><span class="t">Grupa</span></h3>' in card(sara, "grupni")   # a plan to add
    assert '<h3 class="plan-h"><span class="t">Individualni trening</span></h3>' in card(sara, "individualni")

    clanarine = t.get("/clanarine").text                              # the app's own names stay
    assert "<strong>Grupni trening</strong>" in clanarine and "Grupa<" not in clanarine
    assert 'data-copy="plan.' not in clanarine                       # and are no slot there
    editor = t.get("/moja-clanarina").text                           # the editor gets every one to open
    for key in ("clanarina.h.plans", "clanarina.h.add", "clanarina.h.bills",
                *(f"plan.{p}.name" for p in PLAN_TYPES)):
        assert f'data-copy="{key}"' in editor, key


def test_the_no_plan_card_is_the_owners_text_and_the_editor_sees_it_as_a_preview():
    """A member without a plan sees the card in place of Tvoji planovi, its
    two sentences the clanarina.none.* slots, and the empty ledger's line is
    a slot too. The trainer and the owner hold no plans and are told no
    membership talk, so the card would be on no page they open: an editor
    gets it as a preview, in the section under its heading, after a caption
    that says whose view it is (static, not a slot). The line under
    "Pretplati se karticom" shows only while Stripe is configured; with card
    payments off an editor gets it regardless, in every Dodaj plan card, and
    a member never."""
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
    assert copy.SLOTS["clanarina.card_hint"].default not in page    # no card payments, no card's line

    page = client_for("trener@test.local").get("/moja-clanarina").text
    plans = section(page, "mcPlans")                                 # heading, caption, the card
    assert 'data-copy="clanarina.h.plans"' in plans and 'class="plan-cards"' not in plans
    caption = plans.index('<p class="hint mc-preview">Ovo vidi član bez članarine:</p>')
    preview = plans[plans.index('<div class="card mc-none">'):]
    assert caption < plans.index('<div class="card mc-none">')
    for key, txt in (("clanarina.none.title", "Bez plana nema rezervacija."), ("clanarina.none.text", "Javi se u dvorani.")):
        assert f'data-copy="{key}"' in preview and f">{txt}</span>" in preview, key
    assert 'data-copy="clanarina.bills.empty"' in section(page, "mcBills")
    add = section(page, "mcAdd")
    assert add.count('data-copy="clanarina.card_hint"') == len(PLAN_TYPES)
    assert "Pretplati se karticom" not in add                       # still no card payments for anyone


def test_the_trainers_page_leads_to_the_members_page():
    """The trainer's nav has no Članarina tab, and the account menu's item
    was easy to miss (the owner, 18.10.2026: "How will my friend be able to
    even change the 'moja članarina' tab then?"). So /clanarine, the
    trainer's and the owner's page for the members' payments, says under its
    lead where the members' page is and that its texts and prices are edited
    there. The bar's way there is one, never two (20.10.2026): the trainer
    has the menu item, an owner who does not train the Članarina tab, as a
    client does. A client never reaches /clanarine."""
    make_user("ivan@test.local", plans=("grupni",))
    make_user("trener@test.local")                                   # the owner (OWNER_EMAIL), not a trainer
    make_user("coach@test.local", is_trainer=True)                   # a trainer
    link = '<a class="act" href="/moja-clanarina">Moja članarina →</a>'
    for email, tab in (("coach@test.local", False), ("trener@test.local", True)):
        page = client_for(email).get("/clanarine").text
        assert "Stranica koju vide članovi — cjenik, tekstovi i cijene uređuju se tamo:" in text(page), email
        assert page.index("<h1>Članarine</h1>") < page.index(link), email
        assert page.index(link) < page.index('href="/karton/'), email   # above the roster
        assert (">Članarina</a>" in page) == tab, email                # the nav tab: the owner who does not train
        assert ("<span>Moja članarina</span>" in page) != tab, email   # the account menu's item: the trainer
    assert client_for("ivan@test.local").get("/clanarine").status_code == 403
    r = TestClient(app).get("/clanarine", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


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
    assert loc == f"/clanarine?ok=Online trening (QMove ELITE): uplata evidentirana — sljedeća {m.next_payment:{D}}"
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
