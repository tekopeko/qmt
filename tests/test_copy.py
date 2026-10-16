"""In-place editable copy: src/qmt/copy.py (the slots and their caps),
POST /copy/{key} (the save), _copy.html (the macros), the editor in base.html,
and the migration that turned the offer cards' bullets into lists.

The browser half is the net under the texts. Their design limits were lifted
on 16.10.2026 (src/qmt/copy.py): it starts the app in a thread, fills every
slot with a long text — once with words, once with one unbreakable word —
gives the first announcement's text three lines, and measures the pages at
four widths.
Nothing may overflow or be cut, and the cards' prices stay level. It proves
no design; that pass comes once the copy is final. On the way it walks the
landing's rows of cards, the announcements' among them (on a phone they move
on by themselves, and hold still when they must), and the install banner's
week between asks.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import threading
import time
from datetime import date

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import httpx
import pytest
from fastapi.testclient import TestClient

from qmt import auth, copy, db
from qmt.models import Base, User
from qmt.web.app import app

PAGES = ("/", "/cjenik", "/prehrana")          # every page that has editable text


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


# ---------- the route ----------

def test_only_a_trainer_saves_and_the_limit_and_reset_hold():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    key, slot = "hero.kicker", copy.SLOTS["hero.kicker"]

    assert TestClient(app).post(f"/copy/{key}", data={"text": "x"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{key}", data={"text": "x"}).status_code == 403

    t = client_for("trener@test.local")
    r = t.post(f"/copy/{key}", data={"text": "  Novi   uvodni\n tekst.  "})   # spaces collapse, the line break stays
    assert r.status_code == 200 and r.json() == {"ok": True, "text": "Novi uvodni\ntekst.", "default": False}
    page = TestClient(app).get("/").text                                    # everyone reads the edit, in a .t span
    assert '<span class="t">Novi uvodni\ntekst.</span>' in page             # (span.t prints the line break)
    assert 'data-copy="hero.kicker"' not in page                            # ...without editor markup
    assert (f'<span class="ed t" data-copy="{key}" data-max="2000" data-label="{slot.label}">'
            "Novi uvodni\ntekst.</span>") in t.get("/").text                 # the editor has it
    r = t.post(f"/copy/{key}", data={"text": " a \n\n\n\n b "})              # one empty line at most
    assert r.json()["text"] == "a\n\nb" and db.copy_texts()[key] == "a\n\nb"

    r = t.post(f"/copy/{key}", data={"text": "x" * 2001})                   # the cap: against a stray paste
    assert r.status_code == 400 and r.json()["error"] == "Najviše 2000 znakova — ovo ih ima 2001."
    assert t.post(f"/copy/{key}", data={"text": "x" * 2000}).status_code == 200
    assert t.post("/copy/no.such.slot", data={"text": "x"}).status_code == 404

    for blank in ("   ", " \n \n\n "):                                       # empty = back to the default,
        t.post(f"/copy/{key}", data={"text": "Nešto."})                     # line breaks alone are empty too
        r = t.post(f"/copy/{key}", data={"text": blank})
        assert r.json() == {"ok": True, "text": slot.default, "default": True}
    assert slot.default in TestClient(app).get("/").text and db.copy_texts() == {}

    t.post(f"/copy/{key}", data={"text": "Opet novi."})                     # reset=1 does the same
    r = t.post(f"/copy/{key}", data={"text": "ignoriran", "reset": "1"})
    assert r.json() == {"ok": True, "text": slot.default, "default": True} and db.copy_texts() == {}


def test_a_list_slot_takes_edits_additions_and_removals_within_its_limits():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    key, slot = "offer.dvorana.points", copy.SLOTS["offer.dvorana.points"]
    d = list(slot.default)

    assert TestClient(app).post(f"/copy/{key}", data={"text": "x", "index": "0"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{key}", data={"text": "x", "index": "0"}).status_code == 403

    t = client_for("trener@test.local")
    def post(**data):
        return t.post(f"/copy/{key}", data=data)

    r = post(text="  Grupe   do 8 ", index="1")                             # edit one item
    assert r.status_code == 200 and r.json() == {"ok": True, "items": [d[0], "Grupe do 8", d[2]], "default": False}
    r = post(text="Četvrta stavka", index="3")                              # index == count appends
    assert r.json()["items"] == [d[0], "Grupe do 8", d[2], "Četvrta stavka"]
    assert json.loads(db.copy_texts()[key]) == r.json()["items"]            # one row, a JSON array
    page = TestClient(app).get("/").text                                    # everyone reads it...
    assert "Četvrta stavka" in page and f'data-copy="{key}"' not in page and 'class="ed-x"' not in page
    page = t.get("/").text                                                  # ...the editor gets a span per item
    assert page.count(f'data-copy="{key}"') == 4 and 'data-index="3"' in page

    r = post(text="", index="0")                                            # empty text removes the item
    assert r.json() == {"ok": True, "items": ["Grupe do 8", d[2], "Četvrta stavka"], "default": False}
    assert post(text="").json()["items"] == ["Grupe do 8", d[2], "Četvrta stavka"]    # no index: nothing to remove
    assert post(text="  ", index="3").json()["items"] == ["Grupe do 8", d[2], "Četvrta stavka"]  # nothing at n
    assert post(text="x").status_code == 400                                # a text needs an index
    assert post(text="x", index="9").status_code == 400                     # past the end
    assert post(text="x", index="-1").status_code == 400
    assert post(text="x", index="dva").status_code == 400

    for n in range(3, 12):                                                  # up to twelve...
        assert post(text=f"Stavka {n}", index=str(n)).status_code == 200
    r = post(text="Trinaesta", index="12")                                  # ...and not one more
    assert r.status_code == 400 and r.json()["error"] == "Najviše 12 stavki."
    r = post(text="x" * 2001, index="0")
    assert r.status_code == 400 and r.json()["error"] == "Najviše 2000 znakova — ovo ih ima 2001."
    assert post(text="x" * 2000, index="0").status_code == 200
    assert len(json.loads(db.copy_texts()[key])) == 12
    r = post(text=" Prvi red \n\n\n drugi red ", index="1")                # an item keeps its line breaks too
    assert r.json()["items"][1] == "Prvi red\n\ndrugi red"
    assert '<li><span class="t">Prvi red\n\ndrugi red</span></li>' in TestClient(app).get("/").text

    r = post(text="ignoriran", reset="1")                                   # Zadano: the whole default list
    assert r.json() == {"ok": True, "items": d, "default": True} and key not in db.copy_texts()

    for _ in d:                                                             # an emptied list stays empty...
        post(text="", index="0")
    assert json.loads(db.copy_texts()[key]) == []
    page = TestClient(app).get("/").text                                    # ...and a visitor sees no bullets
    assert d[1] not in page and d[2] not in page and "Grupni treninzi u Dubravi." in page
    assert 'data-list="offer.dvorana.points"' in t.get("/").text            # the editor can still add one


def test_a_flag_slot_switches_on_and_off_and_takes_nothing_else():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    key, slot = "event1.show", copy.SLOTS["event1.show"]
    assert isinstance(slot, copy.FlagSlot) and slot.default is True

    assert TestClient(app).post(f"/copy/{key}", data={"text": "off"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{key}", data={"text": "off"}).status_code == 403
    assert key not in db.copy_texts()

    t = client_for("trener@test.local")
    r = t.post(f"/copy/{key}", data={"text": "off"})                        # stored like any slot: the text "off"
    assert r.status_code == 200 and r.json() == {"ok": True, "on": False, "default": False}
    assert db.copy_texts()[key] == "off" and copy.flag_on(key, db.copy_texts()) is False
    r = t.post(f"/copy/{key}", data={"text": "on"})
    assert r.json() == {"ok": True, "on": True, "default": False} and db.copy_texts()[key] == "on"
    for bad in ("maybe", "", " off", "OFF", "1"):                          # exactly "on" or "off"
        r = t.post(f"/copy/{key}", data={"text": bad})
        assert r.status_code == 400 and r.json() == {"ok": False, "error": "Nepoznata vrijednost."}, bad
    assert db.copy_texts()[key] == "on"                                     # a refused value changes nothing

    t.post(f"/copy/{key}", data={"text": "off"})                            # reset=1: the default, and no row
    r = t.post(f"/copy/{key}", data={"text": "off", "reset": "1"})
    assert r.json() == {"ok": True, "on": True, "default": True} and key not in db.copy_texts()
    db.set_copy(key, "nešto", None)                                         # a row that is neither: the default
    assert copy.flag_on(key, db.copy_texts()) is True


def test_the_announcements_show_what_is_on_and_the_editor_keeps_what_is_off():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    one, two = copy.SLOTS["event1.title"].default, copy.SLOTS["event2.title"].default
    page = TestClient(app).get("/").text                                    # both by default, in the hero:
    assert 'id="aktualno"' in page and one in page and two in page          # under the headline, above the photo
    assert page.index("<h1") < page.index('id="aktualno"') < page.index('class="stage"')
    assert page.count('<a class="act" href="/#kontakt"><span class="t">Javi nam se</span></a>') == 2
    assert '<div class="evs swipe-row" id="aktualno" data-auto="5000">' in page          # a phone's swipe row,
    assert '<div class="dots" role="group" aria-label="Aktualno" hidden></div>' in page  # its dots the script's

    db.set_copy("event2.show", "off", None)                                 # one off: gone from a visitor's page
    for c in (TestClient(app), client_for("ivan@test.local")):              # and a client's, the one left alone
        page = c.get("/").text
        assert one in page and two not in page and 'class="evs swipe-row single"' in page
        assert 'is-off"' not in page
    page = client_for("trener@test.local").get("/").text                    # the editor has it, marked off
    assert two in page and 'data-flag-group' in page and 'class="evs swipe-row single"' in page
    assert '<article class="card event is-off" data-flag="event2.show">' in page

    db.set_copy("event1.show", "off", None)                                 # both off: not even their box
    page = TestClient(app).get("/").text
    assert 'id="aktualno"' not in page and one not in page and two not in page and 'aria-label="Aktualno"' not in page
    page = client_for("trener@test.local").get("/").text                    # the editor keeps both, and the box
    assert '<div class="evs swipe-row is-off" id="aktualno"' in page and one in page and two in page
    assert page.count('<article class="card event is-off" data-flag="') == 2
    assert page.count('aria-pressed="false">Skriveno</button>') == 2


def _migration():
    path = pathlib.Path(__file__).parents[1] / "alembic" / "versions" / "1b09c249c2c6_offer_points_lists.py"
    spec = importlib.util.spec_from_file_location("offer_points_lists", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def test_the_migration_folds_the_old_bullet_slots_into_lists():
    mig = _migration(); uid = make_user("trener@test.local", is_trainer=True)
    for key, text in [("offer.online.p1", "Prva"), ("offer.online.p2", "Druga"), ("offer.online.p3", "Treća"),
                      ("offer.individualno.p2", "U paru"),             # only the middle one edited
                      ("hero.kicker", "Ostaje kakav jest.")]:
        db.set_copy(key, text, uid)
    with db.engine.begin() as conn:
        mig.fold_points(conn)
    texts = db.copy_texts()
    assert json.loads(texts["offer.online.points"]) == ["Prva", "Druga", "Treća"]
    # the bullets nobody edited come back as the old defaults, in their places
    assert json.loads(texts["offer.individualno.points"]) == ["Rad 1:1, po dogovoru", "U paru", "Rehabilitacija"]
    assert "offer.dvorana.points" not in texts                              # never edited: no row, new defaults
    assert not [k for k in texts if re.fullmatch(r"offer\.\w+\.p\d", k)]   # the old rows are gone
    assert texts["hero.kicker"] == "Ostaje kakav jest."
    page = TestClient(app).get("/").text
    assert "U paru" in page and "Treća" in page                             # and the page reads them

    with db.engine.begin() as conn:                                         # the way back
        mig.split_points(conn)
    texts = db.copy_texts()
    assert [texts[f"offer.online.p{n}"] for n in (1, 2, 3)] == ["Prva", "Druga", "Treća"]
    assert texts["offer.individualno.p2"] == "U paru" and not [k for k in texts if k.endswith(".points")]


def test_every_slot_is_on_exactly_one_page_and_only_editors_see_the_editor():
    make_user("ivan@test.local", plans=("grupni",)); make_user("trener@test.local", is_trainer=True)
    t = client_for("trener@test.local"); seen: dict[str, str] = {}
    for path in PAGES:
        page = t.get(path).text
        assert 'id="copyToggle"' in page, path
        for key, slot in copy.SLOTS.items():
            if f'data-copy="{key}"' in page:
                assert key not in seen, f"{key} is on {seen[key]} and {path}"
                seen[key] = path
                if isinstance(slot, copy.ListSlot):     # one list, an editable span per item
                    assert page.count(f'data-list="{key}"') == 1, key
                    assert page.count(f'data-copy="{key}"') == len(slot.default), key
                if isinstance(slot, copy.FlagSlot):     # a switch: its toggle, once
                    assert page.count(f'data-copy="{key}"') == 1 and f'class="ed-flag" data-copy="{key}"' in page, key
    assert set(seen) == set(copy.SLOTS), f"slots on no page: {set(copy.SLOTS) - set(seen)}"
    for c in (TestClient(app), client_for("ivan@test.local")):
        for path in PAGES:
            page = c.get(path).text
            if c.get(path, follow_redirects=False).status_code == 200:
                for mark in ("data-copy", "copyToggle", "data-list", 'class="ed-x"', 'ed-add"', 'class="ed-flag"', "data-flag"):
                    assert mark not in page, (path, mark)


# ---------- the layout, measured in a browser ----------
#
# No slot has a design limit since 16.10.2026 (src/qmt/copy.py): the copy
# comes first, and a design pass fits the boxes to it once it is final. So
# this proves no design at a limit; it proves the net under the texts. Long
# texts (300 characters, lists of 12 items of 60) and line breaks may make a
# box tall, but nothing may widen a page or leave the topbar's pill, an
# editable span never changes a font, nothing is cut by a box that hides its
# overflow, and the cards' prices stay level across each row.

WORDS = ("trening snaga pokret zdravlje tehnika grupa trener dvorana program "
         "ravnoteža mobilnost izdržljivost oporavak sprava").split()

LONG, ITEMS, ITEM = 300, 12, 60     # a long text; a list of 12 items, 60 characters each
LINES = "Male grupe do 8 polaznika.\nIndividualni rad 1:1.\nPovratak nakon ozljede."   # a text in three lines
IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")   # the install banner's iOS steps


def words(n: int) -> str:
    """n characters of real-looking words."""
    out, i = "", 0
    while len(out) < n:
        out = f"{out} {WORDS[i % len(WORDS)]}".strip(); i += 1
    out = out[:n]
    return out[:-1] + "x" if out.endswith(" ") else out


@pytest.fixture(scope="module")
def server():
    import uvicorn
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8111, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True); th.start()
    for _ in range(100):
        try:
            if httpx.get("http://127.0.0.1:8111/healthz", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    yield "http://127.0.0.1:8111"
    srv.should_exit = True; th.join(timeout=5)


MEASURE = r"""(strict) => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().width > 0; };
  const px = v => parseFloat(v) || 0, out = {problems: []};
  const de = document.documentElement;
  if (de.scrollWidth - de.clientWidth > 0) out.problems.push(`page overflows by ${de.scrollWidth - de.clientWidth}px`);
  for (const el of document.querySelectorAll('main *')) {
    if (!vis(el)) continue; const cs = getComputedStyle(el);
    if (cs.overflowX === 'auto' || cs.overflowX === 'scroll') continue;
    if (el.scrollWidth - el.clientWidth > 2 && el.clientWidth > 0) out.problems.push(`${el.tagName.toLowerCase()}.${(el.className || '').toString().slice(0, 30)} overflows its box by ${el.scrollWidth - el.clientWidth}px`);
  }
  const tb = document.querySelector('.topbar');
  if (tb) { const cs = getComputedStyle(tb), r = tb.getBoundingClientRect(), l = r.left + px(cs.borderLeftWidth) + px(cs.paddingLeft), rr = r.right - px(cs.borderRightWidth) - px(cs.paddingRight);
    for (const k of [...tb.children].filter(k => vis(k) && getComputedStyle(k).position !== 'absolute')) { const b = k.getBoundingClientRect(); if (b.right - rr > 0.5 || l - b.left > 0.5) out.problems.push('topbar child leaves the pill'); } }
  // typography: an editable span never changes the font of what it sits in
  // (a flag's toggle is a button of its own, not a text)
  for (const el of document.querySelectorAll('[data-copy]:not(.ed-flag)')) { const a = getComputedStyle(el), b = getComputedStyle(el.parentElement);
    if (a.fontFamily !== b.fontFamily || a.fontSize !== b.fontSize || a.fontWeight !== b.fontWeight) out.problems.push(`${el.dataset.copy} changes the font`); }
  // nothing is cut: a text (span.t, every viewer's, editor or not) never
  // reaches past an ancestor that hides its overflow. The one clamp on
  // purpose is the photo card's caption (.stage .copy, landing.html): what is
  // in it counts as far as it shows, and the caption must sit in the card.
  const hides = cs => ['hidden', 'clip'].includes(cs.overflowX) || ['hidden', 'clip'].includes(cs.overflowY);
  for (const el of document.querySelectorAll('span.t')) {
    if (!vis(el)) continue;
    let {left: l, top: t, right: r, bottom: b} = el.getBoundingClientRect();
    for (let a = el.parentElement; a; a = a.parentElement) {
      if (!hides(getComputedStyle(a))) continue;
      const box = a.getBoundingClientRect();
      if (a.matches('.stage .copy')) { l = Math.max(l, box.left); t = Math.max(t, box.top); r = Math.min(r, box.right); b = Math.min(b, box.bottom); continue; }
      if (l < box.left - 1 || t < box.top - 1 || r > box.right + 1 || b > box.bottom + 1) {
        const what = el.dataset.copy || `${el.parentElement.tagName.toLowerCase()}.${el.parentElement.className}`;
        out.problems.push(`${what} "${el.textContent.slice(0, 12)}…" is cut by ${a.tagName.toLowerCase()}.${(a.className || '').toString().slice(0, 30)}`); break; }
    }
  }
  if (!strict) return out;      // one unbreakable word: it may wrap anywhere, it must only never widen or be cut
  // rows of cards: the prices sit level across each row. A price is text the
  // owner may make any length, so it may wrap: it is measured at its bottom
  // edge, which the foot pinned to the bottom of a landing card keeps level
  // whatever is typed (the cjenik's featured card is raised by a transform on
  // purpose; measure as if it were not)
  const ty = el => { const m = getComputedStyle(el).transform.match(/matrix\(([^)]+)\)/); return m ? px(m[1].split(',')[5]) : 0; };
  // a tier card holds a monthly and a yearly price; the one shown is measured
  const price = card => [...card.querySelectorAll('.price')].find(vis);
  for (const sel of ['.offer', '.plan']) { const rows = {};
    for (const card of document.querySelectorAll(sel)) { const top = Math.round((card.getBoundingClientRect().top - ty(card)) / 20); (rows[top] ||= []).push(Math.round(price(card).getBoundingClientRect().bottom - ty(card))); }
    for (const bottoms of Object.values(rows)) if (Math.max(...bottoms) - Math.min(...bottoms) > 1) out.problems.push(`${sel} prices not level: ${bottoms.join(', ')}`); }
  return out;
}"""

# The landing's two offer sections, each a row of cards (.swipe-row): the three
# online tiers and the gym's two. On a wide screen the tiers are three columns
# and the gym two; below 900px each is a swipe row with a dot per card (made
# by the script, so the count and the labels follow the cards) and starts on
# its featured card, centred, with that card's dot lit: the tiers on QMove PRO
# in the middle, the gym (no featured card) on its first. The shown prices are
# level across a row either way, at their bottom edge as in MEASURE (the
# featured tier hangs 16px past its neighbours on a desktop, so the row check
# above can miss it; this one cannot).
LANDING = r"""([w, strict]) => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().width > 0; };
  const out = [], top = el => el.getBoundingClientRect().top, price = card => [...card.querySelectorAll('.price')].find(vis);
  const level = (cards, what) => { if (!strict) return;       // one unbreakable word: it only must not widen
    const b = cards.map(c => Math.round(price(c).getBoundingClientRect().bottom));
    if (Math.max(...b) - Math.min(...b) > 1) out.push(`${what} prices not level: ${b.join(', ')}`); };
  // [section, cards, name, how far a card may stand out of the row on a desktop, the card a phone starts on]
  for (const [sec, n, what, slack, first] of [['#usluge', 3, 'tier', 17, 1], ['#dvorana', 2, 'gym', 1, 0]]) {
    const row = document.querySelector(`${sec} .swipe-row`), cards = row ? [...row.children] : [];
    const dots = [...document.querySelectorAll(`${sec} .dots button`)].filter(vis);
    if (cards.length !== n || !cards.every(c => c.classList.contains('offer'))) { out.push(`${cards.length} ${what} cards`); continue; }
    if (w < 900) {
      if (getComputedStyle(row).overflowX !== 'auto' || row.scrollWidth <= row.clientWidth) out.push(`the ${what} cards do not scroll sideways`);
      const snaps = cards.filter(c => getComputedStyle(c).scrollSnapAlign.includes('center'));
      if (snaps.length !== n) out.push(`${snaps.length} ${what} cards snap`);
      if (dots.length !== n) out.push(`${dots.length} dots under the ${what} cards`);
      dots.forEach((d, i) => { const r = d.getBoundingClientRect();
        if (r.width < 32 || r.height < 32) out.push(`a ${what} dot is ${r.width}x${r.height}`);
        if (d.getAttribute('aria-label') !== `Kartica ${i + 1} od ${n}`) out.push(`${what} dot ${i + 1} says "${d.getAttribute('aria-label')}"`); });
      const lit = dots.findIndex(d => d.getAttribute('aria-current') === 'true');
      if (lit !== first) out.push(`the ${what} row starts on card ${lit + 1}, not ${first + 1}`);
      if (first) { const g = row.getBoundingClientRect(), r = cards[first].getBoundingClientRect(), off = r.left + r.width / 2 - (g.left + g.width / 2);
        if (!cards[first].classList.contains('featured')) out.push(`${what} card ${first + 1} is not the featured one`);
        if (Math.abs(off) > 4) out.push(`the featured ${what} card is ${Math.round(off)}px off its row's centre`); }
    } else {
      if (dots.length) out.push(`dots under the ${what} cards on a wide screen`);
      const cols = getComputedStyle(row).gridTemplateColumns.split(' ').length;
      if (cols !== n) out.push(`the ${what} cards are in ${cols} columns`);
      const t = cards.map(top); if (Math.max(...t) - Math.min(...t) > slack) out.push(`the ${what} cards are not one row: ${t.join(', ')}`);
    }
    level(cards, what);
  }
  return out;
}"""

# The announcements (#aktualno, in the hero), both on in every walk (fill()
# leaves the flags alone). Below 900px a swipe row exactly as wide as the
# screen (it runs to the edges like the tiers' row; the hero keeps its gutter
# for the rest) with a dot per card under it, the first lit on load. From
# 900px two cards side by side and no dots, each card a header line (chip,
# title over when, the link) with its text on a line of its own under it.
AKTUALNO = r"""(w) => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().width > 0; };
  const out = [], row = document.querySelector('#aktualno');
  if (!row) return ['no announcements'];
  const cards = [...row.querySelectorAll('.event')].filter(vis), dots = [...document.querySelectorAll('#aktualno + .dots button')].filter(vis);
  if (cards.length !== 2) out.push(`${cards.length} announcements shown`);
  if (w < 900) {
    const r = row.getBoundingClientRect();
    if (!row.classList.contains('swipe-row') || getComputedStyle(row).overflowX !== 'auto') out.push('the announcements are not a swipe row');
    if (Math.abs(r.width - innerWidth) > 1 || Math.abs(r.left) > 1) out.push(`the announcements' row is ${r.width}px wide at ${r.left}, the screen ${innerWidth}px`);
    if (dots.length !== 2) out.push(`${dots.length} dots under the announcements`);
    dots.forEach((d, i) => { const b = d.getBoundingClientRect();
      if (b.width < 32 || b.height < 32) out.push(`an announcement dot is ${b.width}x${b.height}`);
      if (d.getAttribute('aria-label') !== `Kartica ${i + 1} od 2`) out.push(`announcement dot ${i + 1} says "${d.getAttribute('aria-label')}"`); });
    const lit = dots.findIndex(d => d.getAttribute('aria-current') === 'true');
    if (lit !== 0) out.push(`the announcements start on card ${lit + 1}, not 1`);
  } else {
    if (dots.length) out.push('dots under the announcements on a wide screen');
    const cols = getComputedStyle(row).gridTemplateColumns.split(' ').length;
    if (cols !== 2) out.push(`the announcements are in ${cols} columns`);
    const t = cards.map(c => c.getBoundingClientRect().top);
    if (Math.max(...t) - Math.min(...t) > 1) out.push(`the announcements are not side by side: ${t.join(', ')}`);
    for (const c of cards)
      if (c.querySelector('.text').getBoundingClientRect().top < c.querySelector('.foot').getBoundingClientRect().bottom - 1)
        out.push("an announcement's text is not on a line of its own under the link");
  }
  return out;
}"""

# Mjesečno / Godišnje: one choice, two switches (under the tiers, under the
# gym). Every card of both sections shows exactly the chosen price, and both
# switches say it.
PERIOD = r"""(p) => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && el.getBoundingClientRect().width > 0; };
  const out = [];
  for (const c of document.querySelectorAll('#usluge .offer, #dvorana .offer')) {
    const shown = [...c.querySelectorAll('.price')].filter(vis).map(x => x.dataset.period);
    if (shown.join() !== p) out.push(`a card in #${c.closest('section').id} shows "${shown.join('+')}" for ${p}`);
  }
  const switches = [...document.querySelectorAll('.period')], where = switches.map(s => s.closest('section').id);
  if (where.join() !== 'usluge,dvorana') out.push(`switches in: ${where.join(', ')}`);
  for (const sw of switches) {
    const said = [...sw.querySelectorAll('[aria-selected="true"]')].map(b => b.dataset.period);
    if (said.join() !== p) out.push(`the #${sw.closest('section').id} switch says "${said.join('+')}" for ${p}`);
  }
  return out;
}"""

# The first announcement's text in three lines (LINES): the line breaks show,
# so its span.t is three lines tall, not the one line the same words take
# without them.
EVENT_TEXT = r"""() => {
  const t = document.querySelector('#aktualno .event .text span.t');
  if (!t) return ['no span.t in the first announcement\'s text'];
  const cs = getComputedStyle(t), lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.2;
  const n = t.getBoundingClientRect().height / lh;
  return n < 2.5 ? [`the three-line announcement text shows as ${n.toFixed(1)} lines`] : [];
}"""


def test_layout_holds_with_long_texts_and_line_breaks(server):
    pytest.importorskip("playwright")
    from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright
    make_user("trener@test.local", is_trainer=True); make_user("ivan@test.local", plans=("grupni",))

    def fill(make):
        for key, slot in copy.SLOTS.items():
            if isinstance(slot, copy.FlagSlot):         # a switch, not a text: left on, both announcements show
                continue
            if isinstance(slot, copy.ListSlot):         # every list 12 items long, each item 60 characters
                db.set_copy(key, copy.dump_items([make(min(slot.max_chars, ITEM))] * min(slot.max_items, ITEMS)), None)
            else:                                       # every text 300 characters
                db.set_copy(key, make(min(slot.max, LONG)), None)

    def flip(pg, w):
        """The editor's switch in a browser: in edit mode the first
        announcement, switched off, stays on the page with its content dimmed
        (not its toggle), and on a wide screen both columns stay; after a
        reload it is gone and the second is alone (.single on their box): the
        whole row on a phone, one column of at most 760px on a wide screen.
        Switched back on for the walks after this one."""
        out = []
        pg.click("#copyToggle"); pg.locator("#aktualno .ed-flag").first.click()
        pg.wait_for_function("""() => { const b = document.querySelector('#aktualno .ed-flag');
          return b.getAttribute('aria-pressed') === 'false' && b.closest('.event').classList.contains('is-off'); }""", timeout=5000)
        seen = pg.evaluate("""() => { const c = document.querySelector('#aktualno .event'), o = el => +getComputedStyle(el).opacity;
          return [c.getBoundingClientRect().height > 0, o(c.querySelector('.head')), o(c.querySelector('.ed-flag'))]; }""")
        if seen != [True, 0.55, 1]:
            out.append(f"a strip switched off in edit mode (shown, its title block's and its toggle's opacity): {seen}")
        cols = "() => getComputedStyle(document.querySelector('#aktualno')).gridTemplateColumns.split(' ').length"
        if w >= 900 and pg.evaluate(cols) != 2:
            out.append(f"in edit mode, one announcement off, they are in {pg.evaluate(cols)} columns, not both")
        pg.reload(); pg.wait_for_load_state("networkidle")
        cards = pg.locator("#aktualno .event")
        if cards.nth(0).is_visible() or not cards.nth(1).is_visible():
            out.append("after a reload the card switched off shows, or the other one does not")
        alone = pg.evaluate("""() => { const row = document.querySelector('#aktualno'), cs = getComputedStyle(row), [a, b] = row.querySelectorAll('.event');
          return {single: row.classList.contains('single'), off: getComputedStyle(a).display, width: b.getBoundingClientRect().width,
                  room: row.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight),
                  cols: cs.gridTemplateColumns.split(' ').length, row: row.getBoundingClientRect().width}; }""")
        if not alone["single"] or alone["off"] != "none":
            out.append(f"after a reload their box is not .single, or the card switched off is not display: none: {alone}")
        if w < 900 and abs(alone["width"] - alone["room"]) > 1:
            out.append(f"the one announcement left is {alone['width']}px of the row's {alone['room']}px")
        if w >= 900 and (alone["cols"] != 1 or alone["row"] > 761):
            out.append(f"the one announcement left is in {alone['cols']} columns, {alone['row']}px wide")
        if db.copy_texts().get("event1.show") != "off":
            out.append("the switch was not stored")
        out += pg.evaluate(MEASURE, True)["problems"]
        db.set_copy("event1.show", "on", None)
        return out

    ROW = "document.querySelector('#aktualno')"
    STATE = f"() => [{ROW}.scrollLeft, [...document.querySelectorAll('#aktualno + .dots button')].map(d => d.getAttribute('aria-current')).join()]"
    IN_VIEW = f"() => window.scrollTo({{top: scrollY + {ROW}.getBoundingClientRect().top - 60, behavior: 'instant'}})"

    def advance(pg):
        """The announcements move on by themselves on a phone (the landing's
        script): with their row on the screen (the long texts push it below
        the fold, and off the screen it holds still), the second card is in
        and its dot lit within one tick (5 s) and the glide. A touch starts
        the whole delay again: tapped about a second before the next tick
        was due, nothing moves for the 2 s after the finger lifts."""
        pg.evaluate(IN_VIEW)
        try:
            t = pg.wait_for_function(f"""() => {{ const d = document.querySelectorAll('#aktualno + .dots button');
              return d.length === 2 && d[1].getAttribute('aria-current') === 'true' && {ROW}.scrollLeft > 0 && performance.now(); }}""",
              timeout=8000).json_value()
        except PlaywrightTimeout:
            return [f"the announcements did not move on by themselves in 8 s: {pg.evaluate(STATE)}"]
        pg.wait_for_function(f"() => performance.now() > {t + 3500}")      # the next tick about a second away
        h = pg.locator("#aktualno .event").nth(1).locator("h2").bounding_box()
        pg.touchscreen.tap(h["x"] + h["width"] / 2, h["y"] + h["height"] / 2)
        before = pg.evaluate(STATE); pg.wait_for_timeout(2000); after = pg.evaluate(STATE)
        return [] if after == before else [f"the announcements moved within 2 s of a touch: {before} -> {after}"]

    def still(pw):
        """Under reduced motion the announcements never move by themselves
        (a swipe and the dots still work): 6.5 s on, with their row on the
        screen, the first card is still the one in view."""
        ctx = pw.chromium.launch().new_context(viewport={"width": 390, "height": 900}, has_touch=True, is_mobile=True,
                                               reduced_motion="reduce")
        pg = ctx.new_page(); pg.goto(server + "/"); pg.wait_for_load_state("networkidle")
        pg.evaluate(IN_VIEW); pg.wait_for_timeout(6500); seen = pg.evaluate(STATE)
        ctx.browser.close()
        return [] if seen == [0, "true,false"] else [f"[reduced motion 390px] the announcements moved by themselves: {seen}"]

    def banner(pw):
        """The install banner (base.html) asks again a week after it was
        dismissed, until the app is installed. On an iPhone it shows at load
        (the share-sheet steps, no native prompt to wait for), so each case
        is one reload, from the second page on: dismissed with its ✕ just
        now, or six days ago, it stays away; eight days ago, or the old "no"
        (one dismissal was for good before 16.10.2026), it is back; and
        "installed" (the native prompt accepted) keeps it away."""
        out, ctx = [], pw.chromium.launch().new_context(viewport={"width": 390, "height": 900}, has_touch=True,
                                                         is_mobile=True, user_agent=IPHONE)
        pg = ctx.new_page()
        pg.goto(server + "/login"); pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
        pg.goto(server + "/prehrana")                 # the second page with the banner: it asks
        if not pg.locator("#a2hs").is_visible():
            out.append("not shown on the second page")
        pg.click("#a2hs .a2hs-x"); stored = pg.evaluate("localStorage.getItem('qmt-a2hs')"); pg.reload()
        if pg.locator("#a2hs").is_visible() or not (stored or "").isdigit():
            out.append(f"dismissed with its ✕ ({stored!r} stored), it is back at once")
        for when, value, back in (("six days ago", "Date.now() - 6 * 864e5", False), ("eight days ago", "Date.now() - 8 * 864e5", True),
                                  ('with the old "no"', "'no'", True), ('as "installed"', "'installed'", False)):
            pg.evaluate(f"localStorage.setItem('qmt-a2hs', String({value}))"); pg.reload()
            if pg.locator("#a2hs").is_visible() != back:
                out.append(f"dismissed {when}, it is {'still away' if back else 'back'}")
        ctx.browser.close()
        return [f"[install banner 390px] {p}" for p in out]

    def walk(pw, email, widths, label, strict=True, lines=False, switch=(), auto=None):
        problems = []
        for w in widths:
            phone = w < 600
            ctx = pw.chromium.launch().new_context(viewport={"width": w, "height": 900}, has_touch=phone, is_mobile=phone)
            pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            if email:
                pg.goto(server + "/login"); pg.fill("main input[name=email]", email); pg.fill("main input[name=password]", "lozinka123")
                pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
            for path in PAGES if email else ("/",):
                pg.goto(server + path); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
                where = f"[{label} {email or 'guest'} {w}px {path}]"
                problems += [f"{where} {p}" for p in pg.evaluate(MEASURE, strict)["problems"]]
                if path != "/":
                    continue
                if lines:
                    problems += [f"{where} {p}" for p in pg.evaluate(EVENT_TEXT)]
                problems += [f"{where} {p}" for p in pg.evaluate(LANDING, [w, strict])]
                problems += [f"{where} {p}" for p in pg.evaluate(AKTUALNO, w)]
                if w == auto:                               # the announcements moving by themselves, once
                    problems += [f"{where} {p}" for p in advance(pg)]
                if not all(pg.locator(f"{sec} .period").is_visible() for sec in ("#usluge", "#dvorana")):
                    problems.append(f"{where} no Mjesečno / Godišnje switch under each row"); continue
                problems += [f"{where} on load: {p}" for p in pg.evaluate(PERIOD, "month")]   # monthly first
                # either switch flips both sections: each pressed both ways,
                # the same checks after every press
                for sec, period in (("#usluge", "year"), ("#dvorana", "month"), ("#dvorana", "year"), ("#usluge", "month")):
                    pg.click(f'{sec} .period button[data-period="{period}"]')
                    did = f"{where} {sec} {period}:"
                    problems += [f"{did} {p}" for p in pg.evaluate(PERIOD, period)]
                    problems += [f"{did} {p}" for p in pg.evaluate(MEASURE, strict)["problems"]]
                    problems += [f"{did} {p}" for p in pg.evaluate(LANDING, [w, strict])]
                if w in switch:                             # the editor's switch, on a phone and a wide screen
                    problems += [f"{where} switch: {p}" for p in flip(pg, w)]
            problems += [f"[{label} {w}px] js: {e}" for e in errs]
            ctx.browser.close()
        return problems

    with sync_playwright() as pw:
        fill(words)                                   # long texts: 300 characters, lists of 12
        problems = walk(pw, None, (360, 390, 900, 1280), "words", auto=390)
        problems += still(pw)                         # under reduced motion: never by themselves
        problems += walk(pw, "trener@test.local", (360, 390, 900, 1280), "words", switch=(390, 1280))
        problems += walk(pw, "ivan@test.local", (360, 1280), "words")
        problems += banner(pw)                        # the install banner's week between asks
        db.set_copy("event1.text", LINES, None)       # line breaks: the first announcement's text in three lines
        problems += walk(pw, None, (390, 1280), "lines", lines=True)
        problems += walk(pw, "trener@test.local", (390,), "lines", lines=True)
        fill(lambda n: "W" * n)                       # one unbreakable word: must wrap, never widen
        problems += walk(pw, "trener@test.local", (360, 1280), "one-word", strict=False)
    print("\n".join(problems))
    assert not problems, f"{len(problems)} layout problems, listed above"
