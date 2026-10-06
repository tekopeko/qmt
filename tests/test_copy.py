"""In-place editable copy: src/qmt/copy.py (the slots and their limits),
POST /copy/{key} (the save), _copy.html (the macro), the editor in base.html.

The browser half is what makes the limits TRUE: it starts the app in a thread,
fills every slot to its limit — once with words, once with one unbreakable
word — and measures the pages at four widths. A limit generous enough to let a
text break its box fails here, not on the owner's phone.
"""

from __future__ import annotations

import os
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


def test_every_slot_is_on_exactly_one_page_and_only_editors_see_the_editor():
    make_user("ivan@test.local", plans=("grupni",)); make_user("trener@test.local", is_trainer=True)
    t = client_for("trener@test.local"); seen: dict[str, str] = {}
    for path in PAGES:
        page = t.get(path).text
        assert 'id="copyToggle"' in page, path
        for key in copy.SLOTS:
            if f'data-copy="{key}"' in page:
                assert key not in seen, f"{key} is on {seen[key]} and {path}"
                seen[key] = path
    assert set(seen) == set(copy.SLOTS), f"slots on no page: {set(copy.SLOTS) - set(seen)}"
    for c in (TestClient(app), client_for("ivan@test.local")):
        for path in PAGES:
            page = c.get(path).text
            if c.get(path, follow_redirects=False).status_code == 200:
                assert "data-copy" not in page and "copyToggle" not in page, path


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
  for (const sel of ['.offer', '.plan']) { const rows = {};
    for (const card of document.querySelectorAll(sel)) { const top = Math.round((card.getBoundingClientRect().top - ty(card)) / 20); (rows[top] ||= []).push(Math.round(card.querySelector('.price').getBoundingClientRect().top - ty(card))); }
    for (const tops of Object.values(rows)) if (Math.max(...tops) - Math.min(...tops) > 1) out.problems.push(`${sel} prices not level: ${tops.join(', ')}`); }
  return out;
}"""


def test_layout_holds_with_every_slot_at_its_limit(server):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True); make_user("ivan@test.local", plans=("grupni",))

    def fill(make):
        for key, slot in copy.SLOTS.items():
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
                for p in pg.evaluate(MEASURE, strict)["problems"]:
                    problems.append(f"[{label} {email or 'guest'} {w}px {path}] {p}")
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
