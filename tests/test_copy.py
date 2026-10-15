"""In-place editable copy: src/qmt/copy.py (the slots and their limits),
POST /copy/{key} (the save), _copy.html (the macros), the editor in base.html,
and the migration that turned the offer cards' bullets into lists.

The browser half is what makes the limits TRUE: it starts the app in a thread,
fills every slot to its limit — once with words, once with one unbreakable
word — and measures the pages at four widths. A limit generous enough to let a
text break its box fails here, not on the owner's phone.
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
    key, slot = "hero.lead", copy.SLOTS["hero.lead"]

    assert TestClient(app).post(f"/copy/{key}", data={"text": "x"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{key}", data={"text": "x"}).status_code == 403

    t = client_for("trener@test.local")
    r = t.post(f"/copy/{key}", data={"text": "  Novi   uvodni\n tekst.  "})
    assert r.status_code == 200 and r.json() == {"ok": True, "text": "Novi uvodni tekst.", "default": False}
    assert "Novi uvodni tekst." in TestClient(app).get("/").text          # everyone reads the edit
    assert 'data-copy="hero.lead"' not in TestClient(app).get("/").text   # ...without editor markup
    assert 'data-copy="hero.lead"' in t.get("/").text                     # the editor has it

    r = t.post(f"/copy/{key}", data={"text": "x" * (slot.max + 1)})
    assert r.status_code == 400 and f"Najviše {slot.max} znakova" in r.json()["error"]
    assert t.post(f"/copy/{key}", data={"text": "x" * slot.max}).status_code == 200
    assert t.post("/copy/no.such.slot", data={"text": "x"}).status_code == 404

    r = t.post(f"/copy/{key}", data={"text": "   "})                       # empty = back to the default
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

    for n in range(3, slot.max_items):                                      # up to six...
        assert post(text=f"Stavka {n}", index=str(n)).status_code == 200
    r = post(text="Sedma", index=str(slot.max_items))                       # ...and not one more
    assert r.status_code == 400 and r.json()["error"] == f"Najviše {slot.max_items} stavki."
    r = post(text="x" * (slot.max_chars + 1), index="0")
    assert r.status_code == 400 and f"Najviše {slot.max_chars} znakova" in r.json()["error"]
    assert post(text="x" * slot.max_chars, index="0").status_code == 200
    assert len(json.loads(db.copy_texts()[key])) == slot.max_items

    r = post(text="ignoriran", reset="1")                                   # Zadano: the whole default list
    assert r.json() == {"ok": True, "items": d, "default": True} and key not in db.copy_texts()

    for _ in d:                                                             # an emptied list stays empty...
        post(text="", index="0")
    assert json.loads(db.copy_texts()[key]) == []
    page = TestClient(app).get("/").text                                    # ...and a visitor sees no bullets
    assert d[1] not in page and d[2] not in page and "Grupni treninzi u Dubravi." in page
    assert 'data-list="offer.dvorana.points"' in t.get("/").text            # the editor can still add one


def _migration():
    path = pathlib.Path(__file__).parents[1] / "alembic" / "versions" / "1b09c249c2c6_offer_points_lists.py"
    spec = importlib.util.spec_from_file_location("offer_points_lists", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def test_the_migration_folds_the_old_bullet_slots_into_lists():
    mig = _migration(); uid = make_user("trener@test.local", is_trainer=True)
    for key, text in [("offer.online.p1", "Prva"), ("offer.online.p2", "Druga"), ("offer.online.p3", "Treća"),
                      ("offer.individualno.p2", "U paru"),             # only the middle one edited
                      ("hero.lead", "Ostaje kakav jest.")]:
        db.set_copy(key, text, uid)
    with db.engine.begin() as conn:
        mig.fold_points(conn)
    texts = db.copy_texts()
    assert json.loads(texts["offer.online.points"]) == ["Prva", "Druga", "Treća"]
    # the bullets nobody edited come back as the old defaults, in their places
    assert json.loads(texts["offer.individualno.points"]) == ["Rad 1:1, po dogovoru", "U paru", "Rehabilitacija"]
    assert "offer.dvorana.points" not in texts                              # never edited: no row, new defaults
    assert not [k for k in texts if re.fullmatch(r"offer\.\w+\.p\d", k)]   # the old rows are gone
    assert texts["hero.lead"] == "Ostaje kakav jest."
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
    assert set(seen) == set(copy.SLOTS), f"slots on no page: {set(copy.SLOTS) - set(seen)}"
    for c in (TestClient(app), client_for("ivan@test.local")):
        for path in PAGES:
            page = c.get(path).text
            if c.get(path, follow_redirects=False).status_code == 200:
                for mark in ("data-copy", "copyToggle", "data-list", 'class="ed-x"', 'ed-add"'):
                    assert mark not in page, (path, mark)


# ---------- the layout, measured in a browser ----------

WORDS = ("trening snaga pokret zdravlje tehnika grupa trener dvorana program "
         "ravnoteža mobilnost izdržljivost oporavak sprava").split()


def words(n: int) -> str:
    """n characters of real-looking words (the longest text a slot allows)."""
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
  for (const el of document.querySelectorAll('[data-copy]')) { const a = getComputedStyle(el), b = getComputedStyle(el.parentElement);
    if (a.fontFamily !== b.fontFamily || a.fontSize !== b.fontSize || a.fontWeight !== b.fontWeight) out.problems.push(`${el.dataset.copy} changes the font`); }
  if (!strict) return out;      // one unbreakable word: it may wrap anywhere, it must only never widen
  const lines = el => { const cs = getComputedStyle(el); const lh = px(cs.lineHeight) || px(cs.fontSize) * 1.2; return el.getBoundingClientRect().height / lh; };
  const h1 = document.querySelector('.hero h1');
  if (h1 && lines(h1) > 4.3) out.problems.push(`hero h1 runs to ${lines(h1).toFixed(1)} lines`);
  for (const h of document.querySelectorAll('.offer h3')) if (lines(h) > 1.3) out.problems.push(`offer title "${h.textContent.slice(0, 20)}" wraps`);
  for (const l of document.querySelectorAll('.offer .lead')) if (lines(l) > 2.3) out.problems.push(`offer lead runs to ${lines(l).toFixed(1)} lines`);
  for (const p of document.querySelectorAll('.plan p')) if (lines(p) > 3.3) out.problems.push(`cjenik description runs to ${lines(p).toFixed(1)} lines`);
  const stage = document.querySelector('.stage'); if (stage) { const s = stage.getBoundingClientRect(), c = stage.querySelector('.copy').getBoundingClientRect(), h2 = stage.querySelector('.copy h2');
    if (c.top < s.top + 40 || c.bottom > s.bottom) out.problems.push('stage copy leaves the photo'); if (lines(h2) > 2.3) out.problems.push('stage title runs past two lines'); }
  // rows of cards: the prices sit on one line across each row (the cjenik's
  // featured card is raised by a transform on purpose; measure as if it were not)
  const ty = el => { const m = getComputedStyle(el).transform.match(/matrix\(([^)]+)\)/); return m ? px(m[1].split(',')[5]) : 0; };
  // a tier card holds a monthly and a yearly price; the one shown is measured
  const price = card => [...card.querySelectorAll('.price')].find(vis);
  for (const sel of ['.offer', '.plan']) { const rows = {};
    for (const card of document.querySelectorAll(sel)) { const top = Math.round((card.getBoundingClientRect().top - ty(card)) / 20); (rows[top] ||= []).push(Math.round(price(card).getBoundingClientRect().top - ty(card))); }
    for (const tops of Object.values(rows)) if (Math.max(...tops) - Math.min(...tops) > 1) out.problems.push(`${sel} prices not level: ${tops.join(', ')}`); }
  return out;
}"""

# The landing's two offer sections, each a row of cards (.swipe-row): the three
# online tiers and the gym's two. On a wide screen the tiers are three columns
# and the gym two; below 900px each is a swipe row with a dot per card (made
# by the script, so the count and the labels follow the cards). The shown
# prices are level across a row either way (the featured tier hangs 16px past
# its neighbours on a desktop, so the row check above can miss it; this one
# cannot).
LANDING = r"""([w, strict]) => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().width > 0; };
  const out = [], top = el => el.getBoundingClientRect().top, price = card => [...card.querySelectorAll('.price')].find(vis);
  const level = (cards, what) => { if (!strict) return;       // one unbreakable word: it only must not widen
    const t = cards.map(c => Math.round(top(price(c))));
    if (Math.max(...t) - Math.min(...t) > 1) out.push(`${what} prices not level: ${t.join(', ')}`); };
  // [section, cards, name, how far a card may stand out of the row on a desktop]
  for (const [sec, n, what, slack] of [['#usluge', 3, 'tier', 17], ['#dvorana', 2, 'gym', 1]]) {
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


def test_layout_holds_with_every_slot_at_its_limit(server):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True); make_user("ivan@test.local", plans=("grupni",))

    def fill(make):
        for key, slot in copy.SLOTS.items():
            if isinstance(slot, copy.ListSlot):         # every list full, every item at its limit
                db.set_copy(key, copy.dump_items([make(slot.max_chars)] * slot.max_items), None)
            else:
                db.set_copy(key, make(slot.max), None)

    def walk(pw, email, widths, label, strict=True):
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
                problems += [f"{where} {p}" for p in pg.evaluate(LANDING, [w, strict])]
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
            problems += [f"[{label} {w}px] js: {e}" for e in errs]
            ctx.browser.close()
        return problems

    with sync_playwright() as pw:
        fill(words)                                   # the longest texts the limits allow
        problems = walk(pw, None, (360, 390, 900, 1280), "words")
        problems += walk(pw, "trener@test.local", (360, 390, 900, 1280), "words")
        problems += walk(pw, "ivan@test.local", (360, 1280), "words")
        fill(lambda n: "W" * n)                       # one unbreakable word: must wrap, never widen
        problems += walk(pw, "trener@test.local", (360, 1280), "one-word", strict=False)
    print("\n".join(problems))
    assert not problems, f"{len(problems)} layout problems, listed above"
