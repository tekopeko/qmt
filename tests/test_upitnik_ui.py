"""/upitnik in a browser: Shape's questionnaire, one question per screen
(patterns.md §7, 26.10.2026; the rules and the route are
tests/test_upitnik.py).

A client goes through it on a phone (390px, touch) and on a desktop
(1280px): a choice goes on by itself, so does a scale, Nazad goes back with
the answer kept (and the same answer again goes on), q14 at 5 asks where it
hurts (q14b) and Dalje needs it written, q15 Da asks for a note (q15b), the
bar counts the questions asked, the consent is required, and the saved
upitnik lands on /treninzi. On the desktop the keyboard too: the arrows
only mark an answer, Enter goes on. The trainer's edit mode shows every
step, stacked, his preview outside it one step at a time. With the gym
owner's texts at their longest (300 characters, every choice 12 options of
60), and once as one unbreakable word, no step widens the page, leaves the
column or is cut, at 360, 390, 900 and 1280px, and the scale's ten buttons
keep 40px each (5 × 2 until ten fit in a row). No page errors, no console
errors, anywhere.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import date

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import httpx
import pytest

from qmt import auth, config, copy, db, upitnik
from qmt.models import Base, User
from qmt.web.app import app

PORT = 8112                     # tests/test_copy.py's server is 8111


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # nothing here stores media, but the server thread shares this process's
    # config: never a developer's real R2 bucket (as tests/test_copy.py)
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "")
    yield


def make_user(email: str, is_trainer: bool = False, plans: tuple[str, ...] = ("online",)) -> int:
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    db.update_profile(u.id, email.split("@")[0], "Test", date(1990, 1, 1), "")
    if is_trainer:
        with db.session_scope() as s:
            s.get(User, u.id).is_trainer = True
    for plan in plans:
        db.record_payment(u.id, plan)
    return u.id


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


def open_page(browser, server: str, email: str, width: int, still: bool = False):
    """A logged-in page at `width` (a phone below 600px: touch), and the
    list its page errors and console errors land in. `still`: under reduced
    motion, so no step slides in (base.html), for a walk that measures."""
    phone = width < 600
    ctx = browser.new_context(viewport={"width": width, "height": 900}, has_touch=phone, is_mobile=phone,
                              reduced_motion="reduce" if still else "no-preference")
    pg = ctx.new_page(); errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
    pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    pg.goto(server + "/login")
    pg.evaluate("() => localStorage.setItem('qmt-a2hs', 'installed')")      # the install banner stays out of the way
    pg.fill("main input[name=email]", email); pg.fill("main input[name=password]", "lozinka123")
    pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
    pg.goto(server + "/upitnik"); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
    return ctx, pg, errors


def shown(pg) -> list[str]:
    """The ids of the steps on the screen."""
    return pg.evaluate("[...document.querySelectorAll('.q-step')].filter(s => getComputedStyle(s).display !== 'none').map(s => s.id)")


def wait_for(pg, step: str) -> None:
    pg.wait_for_function("id => document.querySelector('.q-step.on')?.id === id", arg=step, timeout=3000)


def bar(pg) -> float:
    """How full the progress bar is set to be, 0–1 (the width it grows to:
    it takes .25 s to get there)."""
    return pg.evaluate("parseFloat(document.querySelector('.q-bar > span').style.width) / 100")


def press(pg, phone: bool, selector: str, n: int = 0) -> None:
    """Choose with a finger on a phone, with the mouse on a desktop."""
    target = pg.locator(selector).nth(n)
    target.tap() if phone else target.click()


# ---------- a client, one question per screen ----------

def test_a_client_goes_through_the_questionnaire_one_screen_at_a_time(server):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    uid = make_user("ivan@test.local")
    q1, q2, q3, q4 = (copy.UPITNIK_CHOICES[q][1] for q in ("q1", "q2", "q3", "q4"))
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w in (390, 1280):
            phone = w < 600
            ctx, pg, errors = open_page(browser, server, "ivan@test.local", w)
            where = f"[{w}px]"

            def check(ok: bool, what: str) -> None:
                if not ok:
                    problems.append(f"{where} {what}")

            # the first screen: q1 alone under the title and the intro, its h1 the page's only one
            check(shown(pg) == ["step-q1"], f"on load the steps shown are {shown(pg)}")
            check(pg.evaluate("[...document.querySelectorAll('h1')].filter(h => h.offsetParent).length") == 1, "not one h1")
            check(pg.locator(".q-intro").is_visible() and pg.locator(".q-bar").is_visible(), "no intro or no bar on q1")
            check(abs(bar(pg) - 1 / 16) < 0.01, f"the bar on q1 is {bar(pg):.3f}, not 1 of 16")
            check(pg.locator(".avatar, .nav-burger, #mainNav").count() == 0, "the topbar carries more than the brand")
            # a choice goes on by itself; the row chosen stays chosen
            press(pg, phone, "#step-q1 .opt", 1); wait_for(pg, "step-q2")
            check(not pg.locator(".q-intro").is_visible(), "the intro stays after q1")
            press(pg, phone, "#step-q2 .opt", 1); wait_for(pg, "step-q3")
            press(pg, phone, "#step-q3 .q-back"); wait_for(pg, "step-q2")
            row = pg.evaluate("""() => { const r = document.querySelector('#step-q2 .opt:has(input:checked)');
              return r && [r.textContent.trim(), getComputedStyle(r).backgroundColor === getComputedStyle(document.body).color,
                           getComputedStyle(r, '::after').content]; }""")
            check(row is not None and row[0] == q2[1] and row[1] and "✓" in row[2],
                  f"back on q2 its answer is not kept, inverted with a ✓: {row}")
            press(pg, phone, "#step-q2 .opt", 1); wait_for(pg, "step-q3")       # the same answer again goes on
            press(pg, phone, "#step-q3 .opt", 2); wait_for(pg, "step-q4")
            press(pg, phone, "#step-q4 .opt", 2); wait_for(pg, "step-q5")
            check(abs(bar(pg) - 5 / 16) < 0.01, f"the bar on q5 is {bar(pg):.3f}, not 5 of 16")
            # a scale goes on by itself; Nazad keeps it
            press(pg, phone, "#step-q5 .sc", 6); wait_for(pg, "step-q6")
            press(pg, phone, "#step-q6 .q-back"); wait_for(pg, "step-q5")
            check(pg.locator("#step-q5 input[value='7']").is_checked(), "back on q5 its 7 is not kept")
            press(pg, phone, "#step-q5 .sc", 6); wait_for(pg, "step-q6")
            if not phone:
                # the keyboard: the arrows only mark, Enter goes on
                pg.focus("#step-q6 input[value='1']"); pg.keyboard.press("Space")
                for _ in range(5):
                    pg.keyboard.press("ArrowRight")
                pg.wait_for_timeout(600)
                six = pg.locator("#step-q6 input[value='6']").is_checked()
                check(shown(pg) == ["step-q6"] and six, f"after the arrow keys: {shown(pg)}, 6 checked: {six}")
                pg.keyboard.press("Enter"); wait_for(pg, "step-q7")
            else:
                press(pg, phone, "#step-q6 .sc", 5); wait_for(pg, "step-q7")
            for q, value in (("q7", 5), ("q8", 6), ("q9", 8), ("q10", 8), ("q11", 6), ("q12", 4), ("q13", 8)):
                nxt = f"q{int(q[1:]) + 1}"
                press(pg, phone, f"#step-{q} .sc", value - 1); wait_for(pg, f"step-{nxt}")
            # q14 at 5 asks where it hurts: one more step in the bar, and Dalje needs it written
            press(pg, phone, "#step-q14 .sc", 4); wait_for(pg, "step-q14b")
            check(abs(bar(pg) - 15 / 17) < 0.01, f"the bar on q14b is {bar(pg):.3f}, not 15 of 17")
            press(pg, phone, "#step-q14b .q-next"); pg.wait_for_timeout(400)
            check(shown(pg) == ["step-q14b"], "Dalje went on with nothing written")
            pg.fill("#a-q14b", "Donji dio leđa"); press(pg, phone, "#step-q14b .q-next"); wait_for(pg, "step-q15")
            # back to q14 and down to 2: q14b is not asked, and goes unsent
            press(pg, phone, "#step-q15 .q-back"); wait_for(pg, "step-q14b")
            press(pg, phone, "#step-q14b .q-back"); wait_for(pg, "step-q14")
            press(pg, phone, "#step-q14 .sc", 1); wait_for(pg, "step-q15")
            check(pg.locator("#a-q14b").is_disabled() and abs(bar(pg) - 15 / 16) < 0.01,
                  f"q14 at 2: q14b disabled {pg.locator('#a-q14b').is_disabled()}, the bar {bar(pg):.3f}")
            press(pg, phone, "#step-q15 .q-back"); wait_for(pg, "step-q14")
            press(pg, phone, "#step-q14 .sc", 4); wait_for(pg, "step-q14b")
            check(pg.locator("#a-q14b").input_value() == "Donji dio leđa", "q14b lost what was written")
            press(pg, phone, "#step-q14b .q-next"); wait_for(pg, "step-q15")
            # q15 Da asks for a note
            press(pg, phone, "#step-q15 .opt", 0); wait_for(pg, "step-q15b")
            pg.fill("#a-q15b", "Operacija koljena 2023."); press(pg, phone, "#step-q15b .q-next"); wait_for(pg, "step-end")
            check(abs(bar(pg) - 1) < 0.01, f"the bar on the last screen is {bar(pg):.3f}")
            # the consent is required
            press(pg, phone, "#step-end .q-submit"); pg.wait_for_timeout(400)
            check(pg.url.endswith("/upitnik") and shown(pg) == ["step-end"], f"sent without the consent: {pg.url}")
            check(not pg.evaluate("document.querySelector('input[name=consent]').validity.valid"), "the consent is not required")
            press(pg, phone, "#step-end .q-consent")
            with pg.expect_navigation():
                press(pg, phone, "#step-end .q-submit")
            pg.wait_for_load_state("networkidle")
            check(pg.url.split("?")[0].endswith("/treninzi") and "Upitnik je spremljen — Srednja razina." in pg.text_content(".alert.ok"),
                  f"after Spremi: {pg.url}")
            stored = json.loads(db.get_onboarding(uid).answers)
            want = {"q1": q1[1], "q2": q2[1], "q3": q3[2], "q4": q4[2], "q5": 7, "q6": 6, "q7": 5, "q8": 6, "q9": 8,
                    "q10": 8, "q11": 6, "q12": 4, "q13": 8, "q14": 5, "q14b": "Donji dio leđa", "q15": True,
                    "q15b": "Operacija koljena 2023."}
            check(stored == want, f"stored {stored}")
            check(db.get_onboarding(uid).score == 6.4, f"the score stored is {db.get_onboarding(uid).score}")
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# ---------- the trainer's edit mode ----------

STACKED = r"""() => {
  const steps = [...document.querySelectorAll('.q-step')], out = [];
  steps.forEach((s, i) => { if (getComputedStyle(s).display === 'none') out.push(`${s.id} hidden`);
    if (i && s.getBoundingClientRect().top < steps[i - 1].getBoundingClientRect().bottom - 1) out.push(`${s.id} not under ${steps[i - 1].id}`); });
  const lefts = new Set(steps.map(s => Math.round(s.getBoundingClientRect().left)));
  if (lefts.size !== 1) out.push(`the steps start at ${[...lefts]}`);
  if (!document.querySelector('#step-q14 .q-preview') || getComputedStyle(document.querySelector('#step-q14 .q-preview')).display === 'none')
    out.push('the pain sentence is not under q14');
  if (getComputedStyle(document.querySelector('.q-bar')).display !== 'none') out.push('the bar shows in edit mode');
  return out;
}"""


def test_the_trainers_edit_mode_shows_every_step_stacked(server):
    """Outside edit mode the trainer sees what a client sees, one step at a
    time (his choices are his options list: a row he clicks goes on as a
    client's does); in edit mode every step shows, one under the other, the
    follow-ups and the pain sentence too, each option with its ✕ and each
    choice with "+ Dodaj odgovor"; out of it again, the step he was on."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True, plans=())
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w in (390, 1280):
            phone = w < 600
            ctx, pg, errors = open_page(browser, server, "trener@test.local", w)
            where = f"[trainer {w}px]"
            if shown(pg) != ["step-q1"]:
                problems.append(f"{where} his preview shows {shown(pg)}")
            press(pg, phone, "#step-q1 .opts > li", 2); wait_for(pg, "step-q2")
            pg.click("#copyToggle")
            problems += [f"{where} {p}" for p in pg.evaluate(STACKED)]
            seen = pg.evaluate("""() => [document.querySelectorAll('.q-step').length,
              [...document.querySelectorAll('.opts .ed-x')].filter(x => x.offsetParent).length,
              [...document.querySelectorAll('.ed-add')].filter(x => x.offsetParent).length,
              document.documentElement.scrollWidth - document.documentElement.clientWidth]""")
            options = sum(len(o) for _, o in copy.UPITNIK_CHOICES.values())
            if seen != [len(upitnik.STEPS) + 1, options, len(copy.UPITNIK_CHOICES), 0]:
                problems.append(f"{where} edit mode (steps, ✕s, + Dodaj odgovor, overflow): {seen}")
            # a text opens in the bar; a click on a row's edge moves nothing
            pg.click("#step-q2 .q-h .ed")
            if pg.locator("#copyBar").is_hidden() or pg.text_content("#copyBar .cb-label") != "Upitnik, pitanje 2":
                problems.append(f"{where} clicking q2's question did not open it in the bar")
            pg.click("#cbCancel")
            pg.click("#copyToggle")
            if shown(pg) != ["step-q2"]:
                problems.append(f"{where} out of edit mode the steps shown are {shown(pg)}")
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# ---------- long texts, every step, every width ----------

MEASURE = r"""() => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().width > 0; };
  const out = [], de = document.documentElement, col = document.getElementById('quiz').getBoundingClientRect();
  if (de.scrollWidth - de.clientWidth > 0) out.push(`the page overflows by ${de.scrollWidth - de.clientWidth}px`);
  for (const el of document.querySelectorAll('main *')) {
    if (!vis(el)) continue; const cs = getComputedStyle(el);
    if (cs.overflowX === 'auto' || cs.overflowX === 'scroll') continue;
    if (el.scrollWidth - el.clientWidth > 2 && el.clientWidth > 0) out.push(`${el.tagName.toLowerCase()}.${el.className} overflows its box by ${el.scrollWidth - el.clientWidth}px`);
  }
  // nothing leaves the column, and no text is cut by a box hiding its overflow
  const hides = cs => ['hidden', 'clip'].includes(cs.overflowX) || ['hidden', 'clip'].includes(cs.overflowY);
  for (const el of document.querySelectorAll('#quiz span.t, #quiz .q-h, #quiz .opts > *, #quiz .sc, #quiz .q-nav > *, #quiz textarea')) {
    if (!vis(el)) continue; const r = el.getBoundingClientRect();
    if (r.left < col.left - 1 || r.right > col.right + 1) out.push(`${el.tagName.toLowerCase()}.${el.className} leaves the column`);
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      if (!hides(getComputedStyle(a))) continue; const b = a.getBoundingClientRect();
      if (r.left < b.left - 1 || r.top < b.top - 1 || r.right > b.right + 1 || r.bottom > b.bottom + 1) { out.push(`${el.className} is cut by ${a.className}`); break; }
    }
  }
  // the brand alone in the pill, inside its padding
  const tb = document.querySelector('.topbar'), cs = getComputedStyle(tb), t = tb.getBoundingClientRect();
  for (const k of [...tb.children].filter(vis)) { const b = k.getBoundingClientRect();
    if (b.left < t.left + parseFloat(cs.paddingLeft) - 0.5 || b.right > t.right - parseFloat(cs.paddingRight) + 0.5) out.push('the brand leaves the pill'); }
  // a scale: ten buttons of 40px or more, 5 × 2 until ten fit in a row
  const sc = [...document.querySelectorAll('.q-step.on .sc > span')];
  if (sc.length) {
    const small = sc.filter(s => s.getBoundingClientRect().width < 40 || s.getBoundingClientRect().height < 40);
    if (small.length) out.push(`${small.length} scale buttons under 40px`);
    const rows = new Set(sc.map(s => Math.round(s.getBoundingClientRect().top))).size;
    const room = document.querySelector('.q-step.on .scale-box').getBoundingClientRect().width;
    if (rows !== (room >= 454 ? 1 : 2)) out.push(`the scale is ${rows} rows in ${Math.round(room)}px`);
  }
  return out;
}"""

LONG, ITEMS, ITEM = 300, 12, 60
WORDS = ("trening snaga pokret zdravlje tehnika grupa trener dvorana program "
         "ravnoteža mobilnost izdržljivost oporavak sprava").split()


def words(n: int) -> str:
    """n characters of real-looking words."""
    out, i = "", 0
    while len(out) < n:
        out = f"{out} {WORDS[i % len(WORDS)]}".strip(); i += 1
    out = out[:n]
    return out[:-1] + "x" if out.endswith(" ") else out


def fill(make) -> None:
    """Every word of the questionnaire at its longest: a text 300
    characters, a choice 12 options of 60."""
    for key, slot in copy.SLOTS.items():
        if not key.startswith("upitnik."):
            continue
        if isinstance(slot, copy.ListSlot):
            db.set_copy(key, copy.dump_items([make(ITEM)] * ITEMS), None)
        else:
            db.set_copy(key, make(LONG), None)


def walk_all(pg, phone: bool) -> list[str]:
    """Every step a client can be shown, measured, answered on the way:
    the first option, 10 on a scale (so q14 asks q14b), Da (so q15 asks
    q15b), a few words in a free text; the last screen measured too."""
    out = []
    while True:
        step = pg.evaluate("document.querySelector('.q-step.on').id")
        out += [f"{step}: {p}" for p in pg.evaluate(MEASURE)]
        kind = pg.get_attribute(f"#{step}", "data-kind")
        if kind is None:
            return out
        if kind in ("choice", "yesno"):
            press(pg, phone, f"#{step} .opt", 0)
        elif kind == "scale":
            press(pg, phone, f"#{step} .sc", 9)
        else:
            pg.fill(f"#{step} textarea", "x"); press(pg, phone, f"#{step} .q-next")
        pg.wait_for_function("id => document.querySelector('.q-step.on').id !== id", arg=step, timeout=3000)


def test_long_texts_hold_on_every_step_at_every_width(server):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True, plans=())
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for make, label, widths in ((words, "words", (360, 390, 900, 1280)), (lambda n: "W" * n, "one-word", (360, 1280))):
            fill(make)
            for w in widths:
                ctx, pg, errors = open_page(browser, server, "ivan@test.local", w, still=True)
                visited = walk_all(pg, w < 600)
                problems += [f"[{label} client {w}px] {p}" for p in visited]
                problems += [f"[{label} client {w}px] {e}" for e in errors]
                ctx.close()
                ctx, pg, errors = open_page(browser, server, "trener@test.local", w, still=True)
                pg.click("#copyToggle")
                problems += [f"[{label} edit mode {w}px] {p}" for p in pg.evaluate(STACKED) + pg.evaluate(MEASURE)]
                problems += [f"[{label} edit mode {w}px] {e}" for e in errors]
                ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} layout problems, listed above"
