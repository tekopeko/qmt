"""/upitnik in a browser: Shape's questionnaire, one question per screen
(patterns.md §7, 26.10.2026; the rules and the route are
tests/test_upitnik.py). Its questions are rows since 26.10.2026: the gym
owner's (copy.UPITNIK_DEFAULT_QUESTIONS: the fifteen, and q16 / q17 asked
after q14 / q15 since 27.10.2026) are seeded before every test, as the
migrations make them.

A client goes through it on a phone (390px, touch) and on a desktop
(1280px): the guide through the training first (29.10.2026, the gym
owner's introduction: no bar, its button goes on to question 1, whose
Nazad comes back to it), then a choice goes on by itself, so does a
scale, Nazad goes back with the answer kept (and the same answer again
goes on), q14 at 5 asks where it hurts (q16) and Dalje needs it written,
q15 Da asks for a note (q17), the bar counts the questions asked, the
consent is required, and the saved upitnik lands on /treninzi. On the
desktop the keyboard too: the arrows only mark an answer, Enter goes on.
The trainer's edit mode shows every step, stacked, the guide's boxes at
the top, his preview outside it one step at a time. With the gym owner's
texts at their longest (300 characters, every choice 12 options of 60;
the guide's texts in three lines, its lists 12 items), and once as one
unbreakable word, no step, the guide's among them, widens the page,
leaves the column or is cut, at 360, 390, 900 and 1280px, and the scale's
ten buttons keep 40px each (5 × 2 until ten fit in a row). The editor builds a
question in edit mode, at 360, 390 and 1280px: adds it (the page comes back
in edit mode, at it), retypes it, makes it a multi and a scale again that
scores navike (the summary counts it), moves it up, hides it (a client is
not asked it), deletes it (a client gets the fifteen), and nothing ever
overflows. A client ticks several options of a multi and goes on with
Dalje, which waits for a tick. The gym owner's chain (27.10.2026): the
trainer builds porod → zadnjih godinu dana → carski rez on a phone with
Pita se, the chain indented in edit mode, which never overflows with it at
360, 390 and 1280px; a client answering Da / Da / an option sees exactly
those steps, Ne none of the children, the bar counting as it goes. An
option asks its question too, a client's and the trainer's preview. The
walks about the questions open on question 1 (?od=1, the guide read). No
page errors, no console errors, anywhere.
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


# the gym owner's questions, by their answers' keys, and their order (q16 under q14, q17 under q15)
DEFAULTS = {f"q{q['id']}": q for q in copy.UPITNIK_DEFAULT_QUESTIONS}
CHOICES = {key: q["options"] for key, q in DEFAULTS.items() if q["kind"] == "choice"}
ORDER = list(range(1, 15)) + [16, 15, 17]


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    for question in copy.UPITNIK_DEFAULT_QUESTIONS:      # the seventeen, as the migrations make them
        db.add_upitnik_question(None, question)
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


def open_page(browser, server: str, email: str, width: int, still: bool = False, path: str = "/upitnik"):
    """A logged-in page at `width` (a phone below 600px: touch), and the
    list its page errors and console errors land in. `still`: under reduced
    motion, so no step slides in (base.html), for a walk that measures.
    `path`: /upitnik opens on the guide, /upitnik?od=1 on question 1."""
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
    pg.goto(server + path); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
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
    q1, q2, q3, q4 = (CHOICES[q] for q in ("q1", "q2", "q3", "q4"))
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

            # the first screen: the guide through the training, its title the page's only h1, no bar, no intro
            check(shown(pg) == ["step-vodic"], f"on load the steps shown are {shown(pg)}")
            check(pg.evaluate("[...document.querySelectorAll('h1')].filter(h => h.offsetParent).map(h => h.textContent.trim())")
                  == ["Dobrodošao/la u vodič kroz trening"], "not the guide's title, the one h1")
            check(not pg.locator(".q-bar").is_visible() and not pg.locator(".q-intro").is_visible(), "a bar or the intro on the guide")
            check(pg.locator(".avatar, .nav-burger, #mainNav").count() == 0, "the topbar carries more than the brand")
            # its button goes on to q1, whose Nazad comes back to it; then q1 alone under the title and the intro
            press(pg, phone, "#step-vodic .q-next"); wait_for(pg, "step-q1")
            press(pg, phone, "#step-q1 .q-back"); wait_for(pg, "step-vodic")
            check(not pg.locator(".q-bar").is_visible(), "the bar on the guide, back from q1")
            press(pg, phone, "#step-vodic .q-next"); wait_for(pg, "step-q1")
            check(shown(pg) == ["step-q1"], f"after the guide's button the steps shown are {shown(pg)}")
            check(pg.evaluate("[...document.querySelectorAll('h1')].filter(h => h.offsetParent).length") == 1, "not one h1")
            check(pg.locator(".q-intro").is_visible() and pg.locator(".q-bar").is_visible(), "no intro or no bar on q1")
            check(abs(bar(pg) - 1 / 16) < 0.01, f"the bar on q1 is {bar(pg):.3f}, not 1 of 16")
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
            # q14 at 5 asks where it hurts (q16): one more step in the bar, and Dalje needs it written
            press(pg, phone, "#step-q14 .sc", 4); wait_for(pg, "step-q16")
            check(abs(bar(pg) - 15 / 17) < 0.01, f"the bar on q16 is {bar(pg):.3f}, not 15 of 17")
            press(pg, phone, "#step-q16 .q-next"); pg.wait_for_timeout(400)
            check(shown(pg) == ["step-q16"], "Dalje went on with nothing written")
            pg.fill("#a-q16", "Donji dio leđa"); press(pg, phone, "#step-q16 .q-next"); wait_for(pg, "step-q15")
            # back to q14 and down to 2: q16 is not asked, and goes unsent
            press(pg, phone, "#step-q15 .q-back"); wait_for(pg, "step-q16")
            press(pg, phone, "#step-q16 .q-back"); wait_for(pg, "step-q14")
            press(pg, phone, "#step-q14 .sc", 1); wait_for(pg, "step-q15")
            check(pg.locator("#a-q16").is_disabled() and abs(bar(pg) - 15 / 16) < 0.01,
                  f"q14 at 2: q16 disabled {pg.locator('#a-q16').is_disabled()}, the bar {bar(pg):.3f}")
            press(pg, phone, "#step-q15 .q-back"); wait_for(pg, "step-q14")
            press(pg, phone, "#step-q14 .sc", 4); wait_for(pg, "step-q16")
            check(pg.locator("#a-q16").input_value() == "Donji dio leđa", "q16 lost what was written")
            press(pg, phone, "#step-q16 .q-next"); wait_for(pg, "step-q15")
            # q15 Da asks for a note (q17)
            press(pg, phone, "#step-q15 .opt", 0); wait_for(pg, "step-q17")
            pg.fill("#a-q17", "Operacija koljena 2023."); press(pg, phone, "#step-q17 .q-next"); wait_for(pg, "step-end")
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
                    "q10": 8, "q11": 6, "q12": 4, "q13": 8, "q14": 5, "q16": "Donji dio leđa", "q15": True,
                    "q17": "Operacija koljena 2023."}
            check(stored == want, f"stored {stored}")
            check(db.get_onboarding(uid).score == 6.4, f"the score stored is {db.get_onboarding(uid).score}")
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# ---------- the trainer's edit mode ----------

# every step shown, one under the other, each one's content 16px in a
# level under the question it is asked after (data-depth: 27.10.2026)
STACKED = r"""() => {
  const steps = [...document.querySelectorAll('.q-step')], out = [];
  steps.forEach((s, i) => { if (getComputedStyle(s).display === 'none') out.push(`${s.id} hidden`);
    if (i && s.getBoundingClientRect().top < steps[i - 1].getBoundingClientRect().bottom - 1) out.push(`${s.id} not under ${steps[i - 1].id}`); });
  const lefts = new Set(steps.map(s => { const cs = getComputedStyle(s);
    return Math.round(s.getBoundingClientRect().left + parseFloat(cs.borderLeftWidth) + parseFloat(cs.paddingLeft)
                      - 16 * (+s.dataset.depth || 0)); }));
  if (lefts.size !== 1) out.push(`the steps' content does not start 16px in a level: ${[...lefts]}`);
  if (!document.querySelector('#step-q14 .q-preview') || getComputedStyle(document.querySelector('#step-q14 .q-preview')).display === 'none')
    out.push('the pain sentence is not under q14');
  if (getComputedStyle(document.querySelector('.q-bar')).display !== 'none') out.push('the bar shows in edit mode');
  return out;
}"""


def test_the_trainers_edit_mode_shows_every_step_stacked(server):
    """Outside edit mode the trainer sees what a client sees, one step at a
    time, the guide first (his choices are his options list: a row he
    clicks goes on as a client's does); in edit mode every step shows, one
    under the other, the guide at the top with every text of it a box (an
    empty one too: section 1's heading) and each list its "+ Dodaj
    stavku", the follow-ups and the pain sentence too, each option with its
    ✕ and each choice with "+ Dodaj odgovor"; out of it again, the step he
    was on, and the guide's empty heading takes no room."""
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
            if shown(pg) != ["step-vodic"]:
                problems.append(f"{where} his preview shows {shown(pg)}")
            press(pg, phone, "#step-vodic .q-next"); wait_for(pg, "step-q1")
            press(pg, phone, "#step-q1 .opts > li", 2); wait_for(pg, "step-q2")
            pg.click("#copyToggle")
            problems += [f"{where} {p}" for p in pg.evaluate(STACKED)]
            seen = pg.evaluate("""() => [document.querySelectorAll('.q-step').length,
              [...document.querySelectorAll('.opts .ed-x')].filter(x => x.offsetParent).length,
              [...document.querySelectorAll('.ed-add')].filter(x => x.offsetParent).length,
              document.documentElement.scrollWidth - document.documentElement.clientWidth]""")
            options = sum(len(o) for o in CHOICES.values())
            steps = len(upitnik.steps(db.upitnik_questions()))
            # every step, the guide's and the last screen too; "+ Dodaj odgovor" per choice, "+ Dodaj stavku" per guide section
            if seen != [steps + 2, options, len(CHOICES) + 11, 0]:
                problems.append(f"{where} edit mode (steps, ✕s, + Dodaj odgovor / stavku, overflow): {seen}")
            boxes = pg.evaluate("""() => [...document.querySelectorAll('#step-vodic [data-copy]')]
              .filter(e => { const r = e.getBoundingClientRect(); return r.width >= 30 && r.height > 0; }).length""")
            keys = [k for k, s in copy.SLOTS.items() if k.startswith("vodic.")]
            items = sum(len(s.default) for k, s in copy.SLOTS.items() if k.startswith("vodic.") and k.endswith(".points"))
            if boxes != len(keys) - 11 + items:                     # a box per text, one per item of every list
                problems.append(f"{where} {boxes} of the guide's boxes show in edit mode")
            # a text opens in the bar; a click on a row's edge moves nothing
            pg.click("#step-q2 .q-h .ed")
            if pg.locator("#copyBar").is_hidden() or pg.text_content("#copyBar .cb-label") != "Pitanje 2: tekst":
                problems.append(f"{where} clicking q2's question did not open it in the bar")
            pg.click("#cbCancel")
            pg.click("#copyToggle")
            if shown(pg) != ["step-q2"]:
                problems.append(f"{where} out of edit mode the steps shown are {shown(pg)}")
            empty = pg.evaluate("""getComputedStyle(document.querySelector('[data-copy="vodic.1.h"]').parentElement).display""")
            if empty != "none":
                problems.append(f"{where} out of edit mode the guide's empty heading is {empty}")
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
    characters (the slots around the questions, and each question's text,
    a scale's ends, a follow-up's text), a choice 12 options of 60; and the
    guide's (29.10.2026): each text 300 characters in three lines, each
    list 12 items of 60."""
    for key, slot in copy.SLOTS.items():
        if key.startswith("upitnik."):
            db.set_copy(key, make(LONG), None)
        elif key.startswith("vodic."):
            db.set_copy(key, copy.dump_items([make(ITEM)] * ITEMS) if isinstance(slot, copy.ListSlot)
                        else "\n".join([make(LONG // 3)] * 3), None)
    for q in db.upitnik_questions():
        for column in copy.UPITNIK_QUESTION_COLUMNS.values():
            db.set_upitnik_question_field(q.id, column, make(LONG), None)
        if q.kind == "choice":
            db.set_upitnik_question_options(q.id, [make(ITEM)] * ITEMS, None)


def walk_all(pg, phone: bool) -> list[str]:
    """Every step a client can be shown, measured, answered on the way:
    the guide (its button), the first option, 10 on a scale (so q14 asks
    q16), Da (so q15 asks q17), a few words in a free text; the last
    screen measured too."""
    out = []
    while True:
        step = pg.evaluate("document.querySelector('.q-step.on').id")
        out += [f"{step}: {p}" for p in pg.evaluate(MEASURE)]
        kind = pg.get_attribute(f"#{step}", "data-kind")
        if step == "step-vodic":
            press(pg, phone, f"#{step} .q-next")
        elif kind is None:
            return out
        elif kind in ("choice", "yesno"):
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


# ---------- the editor builds a question; a client meets it, then does not ----------

EDITING = "() => document.body.classList.contains('editing')"
SUMMARY = "() => document.querySelector('.q-sum > p').textContent.replace(/\\s+/g, ' ').trim()"
STEP_IDS = "() => [...document.querySelectorAll('.q-step')].map(s => s.id)"
# the step a reload landed on is in view, under the sticky bar (its
# scroll-margin), not off the screen
IN_VIEW = """id => { const r = document.getElementById(id).getBoundingClientRect();
  return r.top >= 0 && r.top < innerHeight / 2; }"""


def reloads(pg, act) -> None:
    """Do what reloads the page (a form, a setting, the switch), and wait
    for the page that comes back: its load, not any navigation (a setting
    first tidies the URL in place, history.replaceState, which Playwright
    counts as one)."""
    with pg.expect_event("load"):
        act()
    pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(150)                       # the fragment's scroll lands


def overflow(pg) -> int:
    return pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")


def test_the_trainer_builds_a_question_and_a_client_never_meets_it_once_deleted(server):
    """In edit mode, at 360, 390 (touch) and 1280px: "+ Dodaj pitanje" brings
    the page back in edit mode at the new question (the sixteenth: a scale
    in part 2 that scores nothing); he retypes its text; makes it "Više
    odgovora" (two placeholder options to retype) and a scale again, then
    "Navike" (the summary counts five navike questions); moves it up (before
    q17, still in edit mode, at it); hides it (Skriveno, dimmed, the summary
    back to four): a client is not asked it; deletes it with two taps (the
    first only arms it): it is gone, and a client gets the fifteen. Nothing
    overflows, the editor's page in edit mode or the client's."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True, plans=()); make_user("ivan@test.local")
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w in (360, 390, 1280):
            phone = w < 600
            ctx, pg, errors = open_page(browser, server, "trener@test.local", w)
            where = f"[builder {w}px]"

            def check(ok: bool, what: str) -> None:
                if not ok:
                    problems.append(f"{where} {what}")

            pg.click("#copyToggle")
            reloads(pg, lambda: press(pg, phone, ".q-add .act"))
            new = max(q.id for q in db.upitnik_questions())
            step = f"step-q{new}"
            check(pg.evaluate(EDITING), "the page came back from + Dodaj pitanje out of edit mode")
            check(pg.url.endswith(f"/upitnik#{step}") and pg.evaluate(IN_VIEW, step),
                  f"+ Dodaj pitanje did not land at the new question: {pg.url}")
            check(pg.text_content(f"#{step} .q-ed-line") == "Dio 2 · skala · ne boduje se",
                  f"the new question's line: {pg.text_content(f'#{step} .q-ed-line')!r}")
            # he retypes it: click, the text, ⌘/Ctrl+Enter
            press(pg, phone, f"#{step} .q-h .ed")
            pg.keyboard.press("ControlOrMeta+A"); pg.keyboard.type("Koju opremu imaš?")
            pg.keyboard.press("ControlOrMeta+Enter")
            pg.wait_for_function("() => document.getElementById('copyBar').hidden", timeout=3000)
            check(db.upitnik_question(new).text == "Koju opremu imaš?", f"retyped: {db.upitnik_question(new).text!r}")
            # Više odgovora: two options to retype; a scale again; Navike
            reloads(pg, lambda: pg.select_option(f"#{step} select[data-field=kind]", "multi"))
            check(pg.evaluate(EDITING), "a setting brought the page back out of edit mode")
            got = pg.evaluate(f"() => [document.getElementById('{step}').dataset.kind, [...document.querySelectorAll('#{step} .opts > li .ed')].map(x => x.textContent)]")
            check(got == ["multi", ["Prvi odgovor", "Drugi odgovor"]], f"as a multi: {got}")
            reloads(pg, lambda: pg.select_option(f"#{step} select[data-field=kind]", "scale"))
            reloads(pg, lambda: pg.select_option(f"#{step} select[data-field=scoring]", "navike"))
            check("navike = 5 pitanja" in pg.evaluate(SUMMARY), f"the summary after Navike: {pg.evaluate(SUMMARY)!r}")
            check(pg.text_content(f"#{step} .q-ed-line") == "Dio 2 · skala · boduje se: navike", "its line after Navike")
            # ↑: before q17, in edit mode, at it
            reloads(pg, lambda: press(pg, phone, f"#{step} .ed-mv[value=gore]"))
            ids = pg.evaluate(STEP_IDS)
            check(ids.index(step) == ids.index("step-q17") - 1 and pg.evaluate(EDITING) and pg.evaluate(IN_VIEW, step),
                  f"after ↑: {ids[-6:]}, editing {pg.evaluate(EDITING)}")
            # the switch: hidden, dimmed, out of the score
            reloads(pg, lambda: press(pg, phone, f"#{step} .ed-flag"))
            state = pg.evaluate(f"""() => {{ const s = document.getElementById('{step}');
              return [s.classList.contains('is-off'), s.querySelector('.ed-flag').textContent,
                      getComputedStyle(s.querySelector('.q-h')).opacity, getComputedStyle(s).display]; }}""")
            check(state == [True, "Skriveno", "0.55", "block"], f"hidden in edit mode: {state}")
            check("navike = 4 pitanja" in pg.evaluate(SUMMARY), f"the summary after hiding: {pg.evaluate(SUMMARY)!r}")
            check(overflow(pg) == 0, f"edit mode overflows by {overflow(pg)}px")
            problems += [f"{where} edit mode: {p}" for p in pg.evaluate(STACKED)]
            # a client is not asked it
            cctx, cpg, cerrors = open_page(browser, server, "ivan@test.local", w)
            cids = cpg.evaluate(STEP_IDS)
            check(step not in cids and len(cids) == 19, f"the client's steps with it hidden: {len(cids)}, {step in cids}")
            check(overflow(cpg) == 0, f"the client's page overflows by {overflow(cpg)}px")
            problems += [f"{where} client: {e}" for e in cerrors]
            cctx.close()
            # Obriši pitanje: the first tap arms it, the second deletes
            press(pg, phone, f"#{step} .ed-q-x")
            check(pg.text_content(f"#{step} .ed-q-x") == "Obriši?" and db.upitnik_question(new) is not None,
                  "one tap on Obriši pitanje did more than arm it")
            reloads(pg, lambda: press(pg, phone, f"#{step} .ed-q-x"))
            check(db.upitnik_question(new) is None and pg.locator(f"#{step}").count() == 0, "Obriši pitanje left it")
            check(pg.evaluate(EDITING), "the page came back from Obriši pitanje out of edit mode")
            check(overflow(pg) == 0, f"edit mode after the delete overflows by {overflow(pg)}px")
            cctx, cpg, cerrors = open_page(browser, server, "ivan@test.local", w)
            check(cpg.evaluate(STEP_IDS) == ["step-vodic"] + [f"step-q{n}" for n in ORDER] + ["step-end"],
                  f"the client's steps after the delete: {cpg.evaluate(STEP_IDS)}")
            check(overflow(cpg) == 0, f"the client's page overflows by {overflow(cpg)}px")
            problems += [f"{where} client: {e}" for e in cerrors]
            cctx.close()
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# ---------- a multi: several ticks, then Dalje ----------

def test_a_client_ticks_several_options_and_goes_on_with_dalje(server):
    """The gym owner's equipment question as a multi (Više odgovora), first
    in the questionnaire: its rows are a choice's, letters and all, and
    several are chosen (each inverted with its ✓); a tap moves nothing on;
    Dalje waits for a tick (aria-disabled: a press does nothing), then goes
    on; Nazad keeps the ticks. The saved upitnik stores the options ticked,
    a list. On a phone (390, touch) and a desktop (1280)."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    uid = make_user("ivan@test.local")
    gear = ["bez opreme", "bučice", "girja", "TRX", "minibandsi", "teretana"]
    new = db.add_upitnik_question(None).id
    db.set_upitnik_question(new, {"kind": "multi", "part": "1"}, None)
    db.set_upitnik_question_options(new, gear, None)
    db.set_upitnik_question_field(new, "text", "Koju opremu imaš?", None)
    for _ in range(len(ORDER)):                                          # to the top
        db.move_upitnik_question(new, "gore")
    step = f"step-q{new}"
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w in (390, 1280):
            phone = w < 600
            ctx, pg, errors = open_page(browser, server, "ivan@test.local", w, path="/upitnik?od=1")
            where = f"[multi {w}px]"

            def check(ok: bool, what: str) -> None:
                if not ok:
                    problems.append(f"{where} {what}")

            def waits() -> str:
                return pg.get_attribute(f"#{step} .q-next", "aria-disabled")

            check(shown(pg) == [step] and abs(bar(pg) - 1 / 17) < 0.01, f"on load: {shown(pg)}, the bar {bar(pg):.3f}")
            check(pg.locator(f"#{step} .opt").count() == 6 and waits() == "true", f"6 rows and a waiting Dalje: {waits()}")
            # a press on it then (Playwright itself will not press an
            # aria-disabled button: the click is dispatched)
            pg.locator(f"#{step} .q-next").dispatch_event("click"); pg.wait_for_timeout(400)
            check(shown(pg) == [step], "Dalje went on with nothing ticked")
            press(pg, phone, f"#{step} .opt", 1); press(pg, phone, f"#{step} .opt", 3); pg.wait_for_timeout(600)
            check(shown(pg) == [step], "a tick went on by itself")
            rows = pg.evaluate(f"""() => [...document.querySelectorAll('#{step} .opt')].map(r => [r.querySelector('input').checked,
              getComputedStyle(r).backgroundColor === getComputedStyle(document.body).color, getComputedStyle(r, '::after').content.includes('✓'),
              getComputedStyle(r, '::before').content.includes('"')])""")
            check([r[:3] for r in rows] == [[i in (1, 3)] * 3 for i in range(6)], f"the rows' state: {rows}")
            check(waits() == "false", "Dalje still waits after two ticks")
            press(pg, phone, f"#{step} .q-next"); wait_for(pg, "step-q1")
            press(pg, phone, "#step-q1 .q-back"); wait_for(pg, step)
            ticked = pg.evaluate(f"() => [...document.querySelectorAll('#{step} input:checked')].map(i => i.value)")
            check(ticked == ["bučice", "TRX"], f"back on it, the ticks are {ticked}")
            press(pg, phone, f"#{step} .q-next"); wait_for(pg, "step-q1")
            for q, n in (("q1", 0), ("q2", 0), ("q3", 0), ("q4", 0)):
                nxt = f"step-q{int(q[1:]) + 1}"
                press(pg, phone, f"#step-{q} .opt", n); wait_for(pg, nxt)
            for q in range(5, 14):
                press(pg, phone, f"#step-q{q} .sc", 4); wait_for(pg, f"step-q{q + 1}")
            press(pg, phone, "#step-q14 .sc", 0); wait_for(pg, "step-q15")
            press(pg, phone, "#step-q15 .opt", 1); wait_for(pg, "step-end")
            press(pg, phone, "#step-end .q-consent")
            with pg.expect_navigation():
                press(pg, phone, "#step-end .q-submit")
            pg.wait_for_load_state("networkidle")
            check(pg.url.split("?")[0].endswith("/treninzi"), f"after Spremi: {pg.url}")
            stored = json.loads(db.get_onboarding(uid).answers)
            check(stored.get(f"q{new}") == ["bučice", "TRX"], f"stored {stored.get(f'q{new}')}")
            check(overflow(pg) == 0, "overflow")
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# ---------- a chain (27.10.2026): built with Pita se, walked by a client ----------

CHAIN = (("Jeste li imali porod?", "yesno"), ("Je li to bilo u zadnjih godinu dana?", "yesno"),
         ("Kako je završio porod?", "choice"))


def retype(pg, phone: bool, selector: str, text: str, n: int = 0) -> None:
    """Open a text in the editor's bar, type it anew, save it (⌘/Ctrl+Enter)."""
    press(pg, phone, selector, n)
    pg.keyboard.press("ControlOrMeta+A"); pg.keyboard.type(text); pg.keyboard.press("ControlOrMeta+Enter")
    pg.wait_for_function("() => document.getElementById('copyBar').hidden", timeout=3000)


def next_step(pg, current: str) -> str:
    """The step the questionnaire went on to from `current`."""
    pg.wait_for_function("id => document.querySelector('.q-step.on').id !== id", arg=current, timeout=3000)
    return pg.evaluate("document.querySelector('.q-step.on').id")


def test_the_trainer_chains_three_questions_and_a_client_walks_them(server):
    """The gym owner's example: on a phone (390, touch) the trainer adds
    three questions in edit mode, words them, makes the first two Da / Ne
    and the third a choice of two, and with Pita se asks the second only
    after the first's Da and the third only after the second's Da ("Samo ako
    …" picks the question right before it and lists its answers; the answer
    chosen saves the pair, the page back in edit mode). The lines say so,
    and the chain sits 16px in a level. In edit mode, with the chain and its
    Pita se open, nothing overflows at 360, 390 or 1280. A client: Da / Da /
    an option goes through exactly those three steps, the bar counting the
    questions asked so far and the ones always asked ahead (16 of 17, 17 of
    18, 18 of 19); back to the first and Ne goes straight to the last
    screen, none of the children shown (their inputs disabled), the bar
    full. What is stored is what was asked."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True, plans=()); uid = make_user("ivan@test.local")
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = open_page(browser, server, "trener@test.local", 390)
        where = "[chain builder 390px]"

        def check(ok: bool, what: str) -> None:
            if not ok:
                problems.append(f"{where} {what}")

        pg.click("#copyToggle")
        ids = []
        for text, kind in CHAIN:
            reloads(pg, lambda: press(pg, True, ".q-add .act"))
            ids.append(max(q.id for q in db.upitnik_questions()))
            retype(pg, True, f"#step-q{ids[-1]} .q-h .ed", text)
            reloads(pg, lambda: pg.select_option(f"#step-q{ids[-1]} select[data-field=kind]", kind))
        porod, godina, rez = ids
        for i, option in enumerate(("Carski rez", "Prirodni porod")):
            retype(pg, True, f"#step-q{rez} .opts > li .ed", option, i)
        check([db.upitnik_question(q).text for q in ids] == [t for t, _ in CHAIN]
              and db.upitnik_question(rez).option_items == ["Carski rez", "Prirodni porod"], "the texts were not saved")
        for child, parent in ((godina, porod), (rez, godina)):
            box = f"#step-q{child} .ed-if"
            check(not pg.locator(f"{box} .if-q").is_visible(), f"q{child}: the question shows before Samo ako …")
            pg.select_option(f"{box} .if-ask", "if")
            got = pg.evaluate(f"""() => [document.querySelector('{box} .if-q').value,
              [...document.querySelectorAll('{box} .if-a option')].map(o => o.value + '=' + o.textContent)]""")
            check(pg.locator(f"{box} .if-q").is_visible() and got == [str(parent), ["=—", "yes=Da", "no=Ne"]],
                  f"q{child}: Samo ako … picked {got}")
            reloads(pg, lambda: pg.select_option(f"{box} .if-a", "yes"))
            check(pg.evaluate(EDITING), "the page came back from Pita se out of edit mode")
            q = db.upitnik_question(child)
            check((q.parent_id, q.condition) == (parent, "yes"), f"q{child} stored {(q.parent_id, q.condition)}")
        lines = [pg.text_content(f"#step-q{q} .q-ed-if") for q in (godina, rez)]
        check(lines == ["Pita se samo ako pitanje 18 = Da", "Pita se samo ako pitanje 19 = Da"], f"the lines: {lines}")
        lefts = pg.evaluate(f"""() => [{porod}, {godina}, {rez}].map(id =>
          Math.round(document.querySelector('#step-q' + id + ' .q-part').getBoundingClientRect().left))""")
        check([x - lefts[0] for x in lefts] == [0, 16, 32], f"the chain's indents: {lefts}")
        # "Obriši pitanje" on porod, which others hang under: its first tap
        # says in the bar what becomes of them; a tap elsewhere lets it go
        press(pg, True, f"#step-q{porod} .ed-q-x")
        said = pg.evaluate("() => [document.getElementById('copyBar').hidden, document.querySelector('#copyBar .cb-msg').textContent]")
        check(said == [False, "Pitanja koja ovise o njemu ostaju i pitat će se svakoga."]
              and pg.text_content(f"#step-q{porod} .ed-q-x") == "Obriši?", f"the first tap on porod's Obriši pitanje: {said}")
        press(pg, True, f"#step-q{porod} .q-ed-line")
        check(pg.evaluate("() => document.getElementById('copyBar').hidden") and db.upitnik_question(porod) is not None
              and pg.text_content(f"#step-q{porod} .ed-q-x") == "Obriši pitanje", "a tap elsewhere did not let the delete go")
        # porod hidden: the two under it are muted, dimmed, their lines amber; shown again, they are not
        reloads(pg, lambda: press(pg, True, f"#step-q{porod} .ed-flag"))
        muted = pg.evaluate(f"""() => [{godina}, {rez}].map(id => {{ const s = document.getElementById('step-q' + id);
          return [s.classList.contains('is-muted'), getComputedStyle(s.querySelector('.q-h')).opacity,
                  s.querySelector('.q-ed-if').className, s.querySelector('.ed-flag').textContent]; }})""")
        check(muted == [[True, "0.55", "q-ed-if muted", "Prikazano"]] * 2, f"porod hidden, the chain under it: {muted}")
        check(overflow(pg) == 0, f"edit mode with a muted chain overflows by {overflow(pg)}px")
        reloads(pg, lambda: press(pg, True, f"#step-q{porod} .ed-flag"))
        check(not pg.evaluate("() => document.querySelectorAll('.q-step.is-muted').length"), "shown again, a step stays muted")
        problems += [f"{where} {e}" for e in errors]
        ctx.close()

        for w in (360, 390, 1280):
            ctx, pg, errors = open_page(browser, server, "trener@test.local", w, still=True)
            pg.click("#copyToggle")
            box = f"#step-q{rez} .ed-if"
            shown_box = pg.evaluate(f"""() => [...document.querySelectorAll('{box} select')].map(s => !!s.offsetParent)""")
            if shown_box != [True, True, True]:
                problems.append(f"[chain edit mode {w}px] the third question's Pita se is not open: {shown_box}")
            problems += [f"[chain edit mode {w}px] {p}" for p in pg.evaluate(STACKED) + pg.evaluate(MEASURE)]
            if overflow(pg):
                problems.append(f"[chain edit mode {w}px] the page overflows by {overflow(pg)}px")
            problems += [f"[chain edit mode {w}px] {e}" for e in errors]
            ctx.close()

        P, G, R = (f"step-q{q}" for q in (porod, godina, rez))
        for w in (390, 1280):
            phone = w < 600
            ctx, pg, errors = open_page(browser, server, "ivan@test.local", w, path="/upitnik?od=1")
            where = f"[chain client {w}px]"
            for q in (1, 2, 3, 4):
                press(pg, phone, f"#step-q{q} .opt", 0); wait_for(pg, f"step-q{q + 1}")
            for q in range(5, 14):
                press(pg, phone, f"#step-q{q} .sc", 4); wait_for(pg, f"step-q{q + 1}")
            press(pg, phone, "#step-q14 .sc", 0); wait_for(pg, "step-q15")
            press(pg, phone, "#step-q15 .opt", 1)
            check(next_step(pg, "step-q15") == P, "q15 Ne did not go on to the first of the chain")
            bars = [bar(pg)]
            press(pg, phone, f"#{P} .opt", 0); seen = [P, next_step(pg, P)]; bars.append(bar(pg))
            press(pg, phone, f"#{G} .opt", 0); seen.append(next_step(pg, G)); bars.append(bar(pg))
            press(pg, phone, f"#{R} .opt", 0); seen.append(next_step(pg, R)); bars.append(bar(pg))
            check(seen == [P, G, R, "step-end"], f"Da / Da / an option went through {seen}")
            want = [16 / 17, 17 / 18, 18 / 19, 1]
            check(all(abs(b - x) < 0.01 for b, x in zip(bars, want)), f"the bar: {[round(b, 3) for b in bars]}")
            if w == 1280:
                for back, to in (("step-end", R), (R, G), (G, P)):
                    press(pg, phone, f"#{back} .q-back"); wait_for(pg, to)
                press(pg, phone, f"#{P} .opt", 1)
                check(next_step(pg, P) == "step-end" and abs(bar(pg) - 1) < 0.01, f"Ne went to {shown(pg)}, the bar {bar(pg):.3f}")
                off = pg.evaluate(f"""() => ['{G}', '{R}'].map(id => [...document.querySelectorAll('#' + id + ' input')].every(i => i.disabled))""")
                check(off == [True, True], f"the children's inputs after Ne, disabled: {off}")
            press(pg, phone, "#step-end .q-consent")
            with pg.expect_navigation():
                press(pg, phone, "#step-end .q-submit")
            pg.wait_for_load_state("networkidle")
            stored = json.loads(db.get_onboarding(uid).answers)
            chain = {k: stored[k] for k in (f"q{porod}", f"q{godina}", f"q{rez}") if k in stored}
            expected = ({f"q{porod}": True, f"q{godina}": True, f"q{rez}": "Carski rez"} if w == 390
                        else {f"q{porod}": False})
            check(pg.url.split("?")[0].endswith("/treninzi") and chain == expected, f"stored {chain}, at {pg.url}")
            check("q16" not in stored and "q17" not in stored, "a question not asked was stored")
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


def test_an_option_asks_its_question_for_a_client_and_in_the_trainers_preview(server):
    """A question asked after an option (q4 "U teretani", a choice), the
    option then re-worded by the editor ("U dvorani QMT": the condition
    follows it, 27.10.2026): a client who picks it is asked the question
    next, one who picks another goes past it; the trainer's preview (out of
    edit mode, his choice rows marked .on) does the same. At 390 (touch)
    and 1280."""
    pytest.importorskip("playwright")
    from fastapi.testclient import TestClient
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True, plans=()); make_user("ivan@test.local")
    gym = db.add_upitnik_question(None).id
    db.set_upitnik_question(gym, {"kind": "text", "part": "1", "parent_id": "4", "condition": "U teretani"}, None)
    db.set_upitnik_question_field(gym, "text", "Koju teretanu?", None)
    for _ in range(13):                                                   # right after q4
        db.move_upitnik_question(gym, "gore")
    assert [q.id for q in db.upitnik_questions()][3:6] == [4, gym, 5]
    t = TestClient(app)
    t.post("/login", data={"email": "trener@test.local", "password": "lozinka123"})
    assert t.post("/copy/upitnik.4.options", data={"text": "U dvorani QMT", "index": "2"}).json()["ok"]
    assert db.upitnik_question(gym).condition == "U dvorani QMT"
    step = f"step-q{gym}"
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for email, w in (("ivan@test.local", 390), ("ivan@test.local", 1280), ("trener@test.local", 1280)):
            phone = w < 600
            ctx, pg, errors = open_page(browser, server, email, w, path="/upitnik?od=1")
            where = f"[{email.split('@')[0]} {w}px]"
            row = "#step-q{} .opts > li" if email.startswith("trener") else "#step-q{} .opt"
            for q in (1, 2, 3):
                press(pg, phone, row.format(q), 0); wait_for(pg, f"step-q{q + 1}")
            press(pg, phone, row.format(4), 2)                               # U dvorani QMT (was U teretani)
            got = next_step(pg, "step-q4")
            if got != step:
                problems.append(f"{where} U dvorani QMT went on to {got}, not the question asked after it")
            press(pg, phone, f"#{step} .q-back"); wait_for(pg, "step-q4")
            press(pg, phone, row.format(4), 0)                               # Kod kuće bez opreme
            got = next_step(pg, "step-q4")
            if got != "step-q5":
                problems.append(f"{where} another option went on to {got}, not past it")
            problems += [f"{where} {e}" for e in errors]
            ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"
