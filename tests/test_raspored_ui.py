"""/raspored on a phone, in a real browser (17.10.2026): one day at a time.

The route half (which day shows, the forms and redirects that keep it, the
rows' data, the next-termin card) is in tests/test_booking.py. This file
starts the app in a thread, as tests/test_copy.py does, and walks the phone
layout at 390 and 360px as a client: nothing overflows, the day strip's
seven days fit the width, one day's column shows, a tap on another day (or
a sideways swipe) switches it and the URL keeps it, a row opens the sheet
with the right termin and action, Odustani and Escape close it, and the
next-termin card is the first thing under the week's head. It never submits
the sheet's forms: the route tests cover what they post. At 1280px the week
is the seven-column grid it always was, with no strip and no rows.

The month view (18.10.2026): the Tjedan | Mjesec switch under the week
buttons follows the day the strip shows, "Mjesec" opens the month (no strip,
no sheet), every number on the paid period's tint is AA in both themes, a
tap on a day opens its week on that day, and "Tjedan" leads back. At 1280px
there is no switch.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import date, datetime, timedelta

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import httpx
import pytest

from qmt import auth, config, db
from qmt.models import Base, User
from qmt.web.app import app

PORT = 8112                      # test_copy.py's server is on 8111


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    yield


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


def make_user(email: str, is_trainer: bool = False, plans: tuple[str, ...] = ("grupni",)) -> int:
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    db.update_profile(u.id, email.split("@")[0], "Test", date(1990, 1, 1), "")
    if is_trainer:
        with db.session_scope() as s:
            s.get(User, u.id).is_trainer = True
    for plan in plans:
        db.record_payment(u.id, plan)
    return u.id


def _session_at(day: date, hour: int) -> int:
    """The id of the materialized session starting on `day` at `hour`."""
    start = datetime(day.year, day.month, day.day, hour, tzinfo=config.TZ)
    for r in db.sessions_between(start, start + timedelta(minutes=1)):
        return r["session"].id
    raise AssertionError(f"no session on {day} at {hour}")


STATE = r"""() => {
  const shown = el => getComputedStyle(el).display !== 'none' && el.getBoundingClientRect().height > 0;
  const de = document.documentElement, strip = document.querySelector('.day-strip');
  const sr = strip.getBoundingClientRect();
  const btns = [...strip.querySelectorAll('button')].map(b => b.getBoundingClientRect());
  return {
    overflow: de.scrollWidth - de.clientWidth,
    strip: shown(strip), n: btns.length,
    fits: btns.every(b => b.left >= sr.left - 0.5 && b.right <= sr.right + 0.5 && b.top === btns[0].top
                          && b.left >= 0 && b.right <= innerWidth && b.width >= 32 && b.height >= 32),
    cols: [...document.querySelectorAll('.week .day-col')].filter(shown).map(c => c.dataset.day),
    rows: [...document.querySelectorAll('.week .sess-row')].filter(shown).length,
    cards: [...document.querySelectorAll('.week .sess')].filter(shown).length,
    pressed: [...strip.querySelectorAll('button[aria-pressed="true"]')].map(b => b.dataset.day),
    search: location.search,
    first: (document.querySelector('.week-head').nextElementSibling || {}).className || '',
    sheet: document.getElementById('sheet') ? document.getElementById('sheet').open : null,
  };
}"""

SHEET = r"""() => {
  const vis = el => !!el && !el.closest('[hidden]') && el.getBoundingClientRect().height > 0;
  const s = document.getElementById('sheet'), r = s.getBoundingClientRect();
  return {
    open: s.open, day: document.getElementById('sheetDay').textContent,
    what: document.getElementById('sheetWhat').textContent, chip: vis(document.getElementById('sheetChip')),
    lead: document.getElementById('sheetLead').textContent,
    buttons: [...s.querySelectorAll('button')].filter(vis).map(b => b.textContent.trim()),
    series: vis(document.getElementById('sheetSeries')),
    late: vis(document.getElementById('sheetLate')),
    focus: document.activeElement ? document.activeElement.textContent.trim() : '',
    bottom: Math.round(innerHeight - r.bottom), width: Math.round(r.width),
  };
}"""

SWIPE = r"""dx => {
  const w = document.querySelector('.week'), r = w.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + 40;
  const t = (cx) => new Touch({identifier: 1, target: w, clientX: cx, clientY: y});
  w.dispatchEvent(new TouchEvent('touchstart', {touches: [t(x)], changedTouches: [t(x)], bubbles: true}));
  w.dispatchEvent(new TouchEvent('touchend', {touches: [], changedTouches: [t(x + dx)], bubbles: true}));
}"""


def test_phone_shows_one_day_switches_it_and_opens_the_sheet(server):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    uid = make_user("ivan@test.local", plans=("grupni", "individualni"))
    make_user("trener@test.local", is_trainer=True)
    today = config.today()
    mon = today - timedelta(days=today.weekday()) + timedelta(days=7)     # next week: every termin ahead
    wed, tue = mon + timedelta(days=2), mon + timedelta(days=1)
    for wd in (0, 2):
        db.add_template("Grupni trening", wd, 7 * 60, 60, 8, None)
        db.add_template("Grupni trening", wd, 18 * 60, 60, 8, None)
    db.add_template("Individualni trening", 0, 20 * 60, 60, 1, None, kind="individualni")
    db.materialize_week(mon)
    mine = _session_at(mon, 7)
    db.book(uid, mine)
    late = db.add_oneoff_session("Kasni trening", datetime.now(config.TZ) + timedelta(hours=5), 60, 8, None)
    db.book(uid, late)                       # inside the 12 h: the sheet only says until when
    late_day = (datetime.now(config.TZ) + timedelta(hours=5)).date()
    late_mon = late_day - timedelta(days=late_day.weekday())

    problems = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w in (390, 360):
            ctx = browser.new_context(viewport={"width": w, "height": 800}, has_touch=True, is_mobile=True)
            pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(server + "/login")
            pg.evaluate("localStorage.setItem('qmt-a2hs', 'installed')")      # no install banner in the way
            pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
            pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
            pg.goto(f"{server}/raspored?week={mon}"); pg.wait_for_load_state("networkidle")
            where = f"[{w}px]"

            st = pg.evaluate(STATE)
            if st["overflow"]:
                problems.append(f"{where} the page overflows by {st['overflow']}px")
            if not (st["strip"] and st["n"] == 7 and st["fits"]):
                problems.append(f"{where} the strip's seven days do not fit the width: {st}")
            if st["cols"] != [str(mon)] or st["pressed"] != [str(mon)]:
                problems.append(f"{where} not one day (Monday, its first with termini) on load: {st}")
            if st["rows"] != 3 + (late_day == mon) or st["cards"] != 0:    # (+ the late one on a Sunday night)
                problems.append(f"{where} Monday is not its rows (no cards): {st}")
            if "next-termin" not in st["first"]:
                problems.append(f"{where} the next-termin card is not the first thing under the week head: {st['first']!r}")

            pg.click(f'.day-strip button[data-day="{wed}"]')                  # a tap on another day
            st = pg.evaluate(STATE)
            if st["cols"] != [str(wed)] or st["pressed"] != [str(wed)] or f"day={wed}" not in st["search"] \
                    or f"week={mon}" not in st["search"]:
                problems.append(f"{where} tapping Wednesday did not switch the day and the URL: {st}")

            pg.click(".week .day-col.is-on button.sess-row[data-state=book] >> nth=1")   # 18:00
            sh = pg.evaluate(SHEET)
            want = {"open": True, "what": "18:00–19:00 · Grupni trening", "chip": False, "series": True,
                    "late": False, "lead": "0 od 8 mjesta zauzeto", "focus": "Rezerviraj"}
            if any(sh[k] != v for k, v in want.items()) or sh["buttons"] != ["✕", "Odustani", "Rezerviraj"] \
                    or sh["day"] != f"sri {wed:%-d.%-m.}":
                problems.append(f"{where} the sheet on a bookable row: {sh}")
            if sh["bottom"] != 0 or sh["width"] != w:
                problems.append(f"{where} the sheet is not docked to the bottom edge: {sh}")
            pg.click("#sheet [data-sheet-close] >> visible=true")             # Odustani
            if pg.evaluate(STATE)["sheet"]:
                problems.append(f"{where} Odustani did not close the sheet")

            pg.click(f'.day-strip button[data-day="{mon}"]')
            pg.click(".week .day-col.is-on button.sess-row[data-state=mine]")
            sh = pg.evaluate(SHEET)
            if not sh["open"] or sh["buttons"] != ["✕", "Odustani", "Otkaži rezervaciju"] or sh["lead"] != "Rezervirano" \
                    or sh["what"] != "07:00–08:00 · Grupni trening" or sh["focus"] != "Otkaži rezervaciju":
                problems.append(f"{where} the sheet on my booking: {sh}")
            pg.keyboard.press("Escape")
            if pg.evaluate(STATE)["sheet"]:
                problems.append(f"{where} Escape did not close the sheet")

            pg.click(".week .day-col.is-on button.sess-row[data-oneonone='1']")   # the 1:1 slot: its chip
            sh = pg.evaluate(SHEET)
            if not sh["chip"] or sh["series"] is not True or sh["lead"] != "Termin je slobodan.":
                problems.append(f"{where} the sheet on a 1:1 row: {sh}")
            pg.mouse.click(5, 5)                                              # the backdrop
            if pg.evaluate(STATE)["sheet"]:
                problems.append(f"{where} the backdrop did not close the sheet")

            pg.evaluate(SWIPE, -120)                                          # a swipe to the left: the next day
            st = pg.evaluate(STATE)
            if st["cols"] != [str(tue)] or f"day={tue}" not in st["search"]:
                problems.append(f"{where} a swipe did not move to Tuesday: {st}")
            pg.evaluate(SWIPE, 40)                                            # too short: stays
            if pg.evaluate(STATE)["cols"] != [str(tue)]:
                problems.append(f"{where} a 40px nudge moved the day")
            pg.reload(); pg.wait_for_load_state("networkidle")                # the URL keeps the day
            if pg.evaluate(STATE)["cols"] != [str(tue)]:
                problems.append(f"{where} a reload lost the day")

            pg.goto(f"{server}/raspored?week={late_mon}&day={late_day}"); pg.wait_for_load_state("networkidle")
            pg.click(f".week .day-col.is-on button.sess-row[data-id='{late}']")
            sh = pg.evaluate(SHEET)
            if not sh["late"] or sh["buttons"] != ["✕", "U redu"] or sh["focus"] != "U redu":
                problems.append(f"{where} the sheet inside the 12 h: {sh}")
            if "Otkazivanje je moguće do 12 h prije termina." not in pg.inner_text("#sheetLate"):
                problems.append(f"{where} the sheet inside the 12 h does not say until when")
            pg.click("#sheet [data-sheet-close] >> visible=true")
            problems += [f"{where} js: {e}" for e in errs]
            ctx.close()

        # the desktop keeps the week grid: seven columns of cards, no strip, no rows
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        pg.goto(server + "/login")
        pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
        pg.goto(f"{server}/raspored?week={mon}"); pg.wait_for_load_state("networkidle")
        st = pg.evaluate(STATE)
        if st["strip"] or len(st["cols"]) != 7 or st["rows"] or st["cards"] != 5 + (late_mon == mon) \
                or st["overflow"]:                                          # 3 on Monday, 2 on Wednesday
            problems.append(f"[1280px] not the week grid: {st}")
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# ---------- the month view (18.10.2026) ----------

VIEW = r"""() => {
  const shown = el => !!el && getComputedStyle(el).display !== 'none' && el.getBoundingClientRect().height > 0;
  const de = document.documentElement, sw = document.querySelector('.view-switch');
  const cells = [...document.querySelectorAll('.month .mday')].map(c => c.getBoundingClientRect());
  const strip = document.querySelector('.day-strip');
  return {
    overflow: de.scrollWidth - de.clientWidth, search: location.search,
    switch: shown(sw),
    pressed: sw ? [...sw.querySelectorAll('a[aria-current="page"]')].map(a => a.textContent.trim()) : [],
    links: sw ? Object.fromEntries([...sw.querySelectorAll('a')].map(a => [a.dataset.view, a.getAttribute('href')])) : {},
    month: shown(document.querySelector('.month')), grid: !!document.querySelector('.week[data-selected]'),
    strip: !!strip, sheet: !!document.getElementById('sheet'),
    day: strip ? ([...strip.querySelectorAll('button[aria-pressed="true"]')].map(b => b.dataset.day)[0] || null) : null,
    cells: cells.length, rows: new Set(cells.map(r => Math.round(r.top))).size,
    fit: cells.every(r => r.left >= 0 && r.right <= innerWidth && r.height >= 40 && r.width >= 32),
  };
}"""

# the audit's colour arithmetic (audit.py CHECKS): each background is
# alpha-composited down the ancestor chain, and a color-mix() computes to
# color(srgb r g b / a), channels 0-1
TINT = r"""() => {
  const parse = c => { const m = c.match(/[\d.]+/g); if (!m) return null;
    const k = c.startsWith('color(srgb') ? 255 : 1;
    return {r: +m[0]*k, g: +m[1]*k, b: +m[2]*k, a: m.length > 3 ? parseFloat(m[3]) : 1}; };
  const lum = ({r, g, b}) => { const f = x => { x = x/255; return x <= .03928 ? x/12.92 : Math.pow((x+.055)/1.055, 2.4); };
    return .2126*f(r) + .7152*f(g) + .0722*f(b); };
  const ground = el => { const chain = []; let n = el;
    while (n && n !== document.documentElement) { chain.push(getComputedStyle(n).backgroundColor); n = n.parentElement; }
    chain.push(getComputedStyle(document.body).backgroundColor);
    let acc = {r: 255, g: 255, b: 255};
    for (let i = chain.length - 1; i >= 0; i--) { const p = parse(chain[i]); if (!p || p.a === 0) continue;
      acc = {r: p.r*p.a + acc.r*(1-p.a), g: p.g*p.a + acc.g*(1-p.a), b: p.b*p.a + acc.b*(1-p.a)}; }
    return acc; };
  const ratio = el => { const a = lum(parse(getComputedStyle(el).color)), b = lum(ground(el));
    return (Math.max(a, b) + .05) / (Math.min(a, b) + .05); };
  const days = [...document.querySelectorAll('.month .mday:not(.other)')];
  return days.map(c => ({n: c.firstChild.textContent, covered: c.classList.contains('covered'),
                         past: c.classList.contains('past'), ratio: +ratio(c).toFixed(2),
                         bg: getComputedStyle(c).backgroundColor}));
}"""


def test_phone_switches_to_the_month_and_back(server):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    from qmt.models import Membership, sub_month

    uid = make_user("ivan@test.local", plans=("grupni",))
    today = config.today()
    with db.session_scope() as s:            # paid until 3 days from now: the period began about a month
        m = s.scalar(db.select(Membership).where(Membership.user_id == uid))   # ago, so past days carry the tint too
        m.next_payment = today + timedelta(days=3)
    for wd in range(7):                       # a termin every day: every week opens with its strip
        db.add_template("Grupni trening", wd, 18 * 60, 60, 8, None)
    mon = today - timedelta(days=today.weekday())
    other = mon + timedelta(days=(today.weekday() + 3) % 7)                  # another day of this week
    first = today.replace(day=1)
    this_month, last_month = f"{first:%Y-%m}", f"{sub_month(first):%Y-%m}"

    def week_of(d: date) -> str:
        return f"?week={d - timedelta(days=d.weekday())}&day={d}"

    problems = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        def phone(w: int, theme: str = "dark"):
            ctx = browser.new_context(viewport={"width": w, "height": 800}, has_touch=True, is_mobile=True)
            pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(server + "/login")
            pg.evaluate("t => { localStorage.setItem('qmt-a2hs', 'installed'); localStorage.setItem('qmt-theme', t); }",
                        theme)
            pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
            pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
            return ctx, pg, errs

        def go(pg, path: str):
            pg.goto(server + path); pg.wait_for_load_state("networkidle")

        def tap(pg, selector: str):
            with pg.expect_navigation():
                pg.click(selector)
            pg.wait_for_load_state("networkidle")

        # 390px, dark: the round trip
        ctx, pg, errs = phone(390)
        where = "[390px]"
        go(pg, "/raspored")
        st = pg.evaluate(VIEW)
        if not st["switch"] or st["pressed"] != ["Tjedan"] or st["links"] != {
                "week": f"/raspored{week_of(today)}", "month": f"/raspored?view=month&month={this_month}"}:
            problems.append(f"{where} the week page's switch: {st}")
        pg.click(f'.day-strip button[data-day="{other}"]')                    # the switch follows the strip
        st = pg.evaluate(VIEW)
        if st["links"] != {"week": f"/raspored{week_of(other)}", "month": f"/raspored?view=month&month={other:%Y-%m}"}:
            problems.append(f"{where} the switch did not follow the strip to {other}: {st['links']}")
        pg.click(f'.day-strip button[data-day="{today}"]')

        tap(pg, '.view-switch a[data-view="month"]')                           # Mjesec
        st = pg.evaluate(VIEW)
        if st["search"] != f"?view=month&month={this_month}" or not st["month"] or st["strip"] or st["sheet"] \
                or st["grid"] or st["pressed"] != ["Mjesec"] or not st["fit"] or st["cells"] != 7 * st["rows"] \
                or st["overflow"]:
            problems.append(f"{where} Mjesec did not open the month page: {st}")
        target = pg.evaluate("""() => { const c = [...document.querySelectorAll('.month .mday.covered:not(.past)')];
                                        return c.length ? c[c.length - 1].getAttribute('href') : null; }""")
        day = date.fromisoformat(target.rsplit("day=", 1)[1]) if target else None
        if day is None or not today <= day <= today + timedelta(days=10):
            problems.append(f"{where} no paid day ahead in the month: {target}")
        else:
            tap(pg, f'.month a.mday[href="{target}"]')                         # a tap on a paid day: its week
            st = pg.evaluate(VIEW)
            if st["search"] != week_of(day) or st["day"] != str(day) or not st["grid"]:
                problems.append(f"{where} a tap on {day} did not open its week on it: {st}")
            tap(pg, '.view-switch a[data-view="month"]')
            tap(pg, '.view-switch a[data-view="week"]')                        # Tjedan: back to the week
            st = pg.evaluate(VIEW)
            if st["search"] != week_of(today) or st["day"] != str(today) or st["pressed"] != ["Tjedan"] \
                    or st["month"]:
                problems.append(f"{where} Tjedan did not lead back to the week: {st}")
        problems += [f"{where} js: {e}" for e in errs]
        ctx.close()

        # both themes: every number on the tint is AA, and the tint is a colour of its own
        for theme in ("dark", "light"):
            ctx, pg, errs = phone(390, theme)
            days = []
            for m in (this_month, last_month):                              # past paid days are in one of them
                go(pg, f"/raspored?view=month&month={m}")
                days += pg.evaluate(TINT)
            tinted = [d for d in days if d["covered"]]
            low = [d for d in tinted if d["ratio"] < 4.5]
            if low or not any(d["past"] for d in tinted) or all(d["past"] for d in tinted):
                problems.append(f"[390px {theme}] numbers on the tint under AA, or a state missing: {low or tinted}")
            plain = {d["bg"] for d in days if not d["covered"]}
            if not plain or plain & {d["bg"] for d in tinted}:
                problems.append(f"[390px {theme}] the tint is not a colour of its own: {plain}")
            print(f"[390px {theme}] lowest number on the tint: {min(d['ratio'] for d in tinted) if tinted else None}")
            ctx.close()

        # 360px: the grid fits the narrowest phone
        ctx, pg, errs = phone(360)
        go(pg, "/raspored?view=month")
        st = pg.evaluate(VIEW)
        if st["overflow"] or not st["fit"] or not st["switch"] or st["cells"] != 7 * st["rows"]:
            problems.append(f"[360px] the month page: {st}")
        ctx.close()

        # the desktop never offers the month
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        pg.goto(server + "/login")
        pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
        go(pg, "/raspored")
        st = pg.evaluate(VIEW)
        if st["switch"] or not st["grid"]:
            problems.append(f"[1280px] the switch shows on the desktop: {st}")
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"
