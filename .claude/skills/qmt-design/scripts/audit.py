"""Measured design audit — run BEFORE calling any UI work done.

    python .claude/skills/qmt-design/scripts/audit.py [http://127.0.0.1:8100]
    python .claude/skills/qmt-design/scripts/audit.py --phone     # phones only, ~30 s

Walks every page as anon / client / owner. The full run covers dark + light at
1280px and 390px, plus 360px in dark (the narrowest phone, where overflow shows
first). --phone runs only 390px and 360px, dark: the layout half of the audit,
quick enough for the Stop hook (.claude/hooks/ui-audit-gate.sh) to run by
itself. Phone widths emulate a touch device. A passing run against the local
server stamps the UI's fingerprint (.claude/ui-audit.stamp), which is how the
hook knows these exact files were checked on a phone.

Reports: page + element horizontal overflow, WCAG-AA contrast failures, tap
targets under 32px, images without alt, unlabelled form controls, heading
order. Needs the dev server up and the demo seed loaded (scripts/seed_demo.py).
Backgrounds are alpha-composited down to the page, so text on a tinted chip is
measured against what it really sits on; the reported ratio is the real one.
"""
import collections
import json
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

import pathlib

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = ARGS[0] if ARGS else "http://127.0.0.1:8100"
SAVE_BASELINE = "--save-baseline" in sys.argv
PHONE = "--phone" in sys.argv
# (theme, width) runs. Layout does not depend on the theme and contrast does not
# depend on the width, so 360px is walked once, in dark.
RUNS = ([("dark", 390), ("dark", 360)] if PHONE else
        [("dark", 1280), ("dark", 390), ("dark", 360), ("light", 1280), ("light", 390)])
ROOT = pathlib.Path(__file__).resolve().parents[4]
STAMP = ROOT / ".claude" / "ui-audit.stamp"


def ui_fingerprint() -> str:
    """One hash over everything a browser renders (templates + static CSS/JS),
    from the same script the Stop hook uses, so the two can never disagree."""
    import subprocess
    try:
        return subprocess.run([str(ROOT / ".claude" / "hooks" / "ui-fingerprint.sh")],
                              capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ""

BASELINE = pathlib.Path(__file__).resolve().parent.parent / "references" / "audit-baseline.json"
# ?ok= / ?error= pages: the flash alerts are text nobody audits otherwise
ANON = ["/", "/cjenik", "/login", "/signup", "/forgot", "/prehrana",
        "/login?ok=Lozinka+je+promijenjena", "/login?error=Pogre%C5%A1an+email+ili+lozinka."]
# /upitnik opens on the guide through the training (29.10.2026), ?od=1 on its first question; /vodic is the guide alone.
# The programmes' days (30.10.2026): "trening:1" is the first programme on
# the client's /treninzi, "dan:1" its first day's page (the demo seed: ivan's
# Dan 1, all three sections, two finished passes in its Povijest), both found
# by their links (a reseed gives new ids). The player (30.10.2026, stage 3):
# "kreni:1" presses Kreni on dan:1 and lands on its first exercise, "kraj:1"
# is the finish screen the player's "Završi trening" leads to; after it the
# walk drops that pass (…/odustani), so the next run starts clean.
CLIENT = ["/", "/raspored", "/raspored?ok=Rezervirano+%E2%9C%93", "/raspored?view=month", "/karton", "/moja-clanarina", "/prehrana", "/profil", "/treninzi",
          "trening:1", "dan:1", "kreni:1", "kraj:1", "/upitnik", "/upitnik?od=1", "/vodic"]
# the library of exercises (30.10.2026): its list, and one exercise's page,
# "vjezba:<name>", found on the list by the seed's name (scripts/seed_demo.py:
# a reseed gives the exercises new ids). Goblet čučanj has tags, similar
# exercises and a rep note there. "dan:1:uredi" is the editor of the day the
# client's walk found as "dan:1" (staff's /treninzi is the table of every
# programme, so the owner's walk takes the path the client's found).
OWNER = ["/", "/raspored", "/admin", "/clanarine", "/korisnici", "/statistika", "/treninzi",
         "/treninzi/vjezbe", "vjezba:Goblet čučanj", "dan:1:uredi", "/profil"]

FIND_EXERCISE = """n => { const row = [...document.querySelectorAll('a.ex-row')]
  .find(a => (a.querySelector('.ex-name') || {}).textContent === n); return row ? row.getAttribute('href') : null; }"""
# the n-th link of a kind on a page: a programme's card on /treninzi, a day's on its programme's page
NTH_LINK = """([sel, n]) => { const a = document.querySelectorAll(sel)[n - 1]; return a ? a.getAttribute('href') : null; }"""
FOUND: dict[str, str] = {}               # "trening:1" / "dan:1" -> the path the client's walk found

CHECKS = r"""
() => {
  const out = {overflow: [], contrast: [], tap: [], alt: [], label: [], head: [], inner: []};
  const px = v => parseFloat(v) || 0;
  const de = document.documentElement;
  if (de.scrollWidth - de.clientWidth > 0) out.overflow.push(de.scrollWidth - de.clientWidth);

  // colour math that respects alpha: a tinted chip (rgba(255,52,43,.12)) is
  // NOT solid red — it is 12% red over whatever sits behind it. Composite the
  // ancestor chain from the body outward, then measure. This is what turned the
  // old "ratio 1" false positives into real numbers.
  // A color-mix() computes to "color(srgb r g b / a)" with channels 0–1,
  // not rgb()'s 0–255: scaled here, or the month view's 12% green tint was
  // measured as 12% black (18.10.2026).
  const parse = c => { const m = c.match(/[\d.]+/g); if (!m) return null;
    const k = c.startsWith('color(srgb') ? 255 : 1;
    return {r:+m[0]*k, g:+m[1]*k, b:+m[2]*k, a: m.length > 3 ? parseFloat(m[3]) : 1}; };
  const lumRGB = ({r,g,b}) => { const f = x => { x = x/255; return x <= .03928 ? x/12.92 : Math.pow((x+.055)/1.055, 2.4); };
    return .2126*f(r) + .7152*f(g) + .0722*f(b); };
  const lum = c => { const p = parse(c); return (!p || p.a === 0) ? null : lumRGB(p); };
  const bgOf = el => {
    const chain = []; let n = el;
    while (n && n !== document.documentElement) { chain.push(getComputedStyle(n).backgroundColor); n = n.parentElement; }
    chain.push(getComputedStyle(document.body).backgroundColor);
    let acc = {r:255, g:255, b:255};                 // the page canvas, if nothing paints
    for (let i = chain.length - 1; i >= 0; i--) {   // outermost first
      const p = parse(chain[i]); if (!p || p.a === 0) continue;
      acc = {r: p.r*p.a + acc.r*(1-p.a), g: p.g*p.a + acc.g*(1-p.a), b: p.b*p.a + acc.b*(1-p.a)};
    }
    return lumRGB(acc);
  };
  const vis = el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'
           && getComputedStyle(el).opacity !== '0';
  };

  const TEXT = 'p,span,a,button,h1,h2,h3,h4,li,td,th,label,strong,em,div.hint,summary';
  out.onPhoto = 0;
  for (const el of document.querySelectorAll(TEXT)) {
    if (!vis(el)) continue;
    // text a template declares to sit on a photograph: the background is the
    // image, which no colour math can see — counted, never scored
    if (el.closest('[data-photo]')) { out.onPhoto++; continue; }
    const direct = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (!direct) continue;
    const cs = getComputedStyle(el);
    const fl = lum(cs.color), bl = bgOf(el);
    if (fl === null || bl === null) continue;
    const [hi, lo] = fl > bl ? [fl, bl] : [bl, fl];
    const ratio = (hi + .05) / (lo + .05);
    const size = px(cs.fontSize), bold = px(cs.fontWeight) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const need = large ? 3 : 4.5;
    if (ratio < need) out.contrast.push({t: el.textContent.trim().slice(0, 34), ratio: +ratio.toFixed(2), need,
      size: +size.toFixed(1), cls: (el.className || '').toString().slice(0, 30)});
  }

  for (const el of document.querySelectorAll('a,button,input[type=submit],select,summary')) {
    if (!vis(el)) continue;
    if (el.classList.contains('tlink')) continue;   // a link inside prose is text, not a control
    const r = el.getBoundingClientRect();
    if (r.height < 32 || r.width < 32) out.tap.push({t: (el.textContent || el.value || el.type || '').trim().slice(0, 26),
      w: Math.round(r.width), h: Math.round(r.height), cls: (el.className||'').toString().slice(0,28)});
  }
  for (const im of document.querySelectorAll('img')) if (!im.hasAttribute('alt')) out.alt.push(im.getAttribute('src') || '(no src)');
  for (const f of document.querySelectorAll('input,select,textarea')) {
    if (f.type === 'hidden' || !vis(f)) continue;
    const named = (f.id && document.querySelector(`label[for="${CSS.escape(f.id)}"]`)) || f.getAttribute('aria-label') || f.closest('label');
    if (!named) out.label.push({name: f.name || f.id || f.type, type: f.type});
  }
  const hs = [...document.querySelectorAll('h1,h2,h3,h4')].filter(vis);
  let prev = 0, jump = null;
  for (const h of hs) { const lv = +h.tagName[1]; if (prev && lv > prev + 1) jump = `h${prev} → h${lv} (${h.textContent.trim().slice(0,24)})`; prev = lv; }
  out.head.push({h1: hs.filter(h => h.tagName === 'H1').length, jump, title: document.title.slice(0, 40)});
  for (const el of document.querySelectorAll('main *')) {
    if (!vis(el)) continue;
    const cs = getComputedStyle(el);
    if (cs.overflowX === 'auto' || cs.overflowX === 'scroll') continue;
    if (el.scrollWidth - el.clientWidth > 2 && el.clientWidth > 0)
      out.inner.push({tag: el.tagName.toLowerCase(), cls: (el.className||'').toString().slice(0,28), by: el.scrollWidth - el.clientWidth});
  }
  // The topbar pill: everything in it must sit inside its padding, and nothing
  // in it may overlap. The loop above never sees the header (it walks `main`),
  // and a child that only eats the pill's padding does not grow scrollWidth —
  // the owner's avatar sat flush on the pill's edge under "0 overflow" until a
  // screenshot from prod showed it (5.10.2026).
  const tb = document.querySelector('.topbar');
  if (tb) {
    const tcs = getComputedStyle(tb), tr = tb.getBoundingClientRect();
    const l = tr.left + px(tcs.borderLeftWidth) + px(tcs.paddingLeft), r = tr.right - px(tcs.borderRightWidth) - px(tcs.paddingRight);
    const kids = [...tb.children].filter(k => vis(k) && getComputedStyle(k).position !== 'absolute').map(k => k.getBoundingClientRect());
    let by = 0;
    for (const k of kids) by = Math.max(by, k.right - r, l - k.left);
    for (let i = 0; i < kids.length; i++) for (let j = i + 1; j < kids.length; j++)
      by = Math.max(by, Math.min(kids[i].right, kids[j].right) - Math.max(kids[i].left, kids[j].left));
    if (by > 0.5) out.inner.push({tag: 'header', cls: 'topbar', by: Math.round(by)});
  }
  return out;
}
"""


def resolve(pg, r: str) -> str | None:
    """A programme's or a day's path, by its link: "trening:N" the N-th
    programme on /treninzi, "dan:N" the N-th day of "trening:1" (both kept
    in FOUND for the owner's walk), "dan:N:uredi" the editor of that day."""
    kind, n, *rest = r.split(":")
    if rest == ["uredi"]:
        return FOUND[f"{kind}:{n}"] + "/uredi" if f"{kind}:{n}" in FOUND else None
    if kind == "trening":
        page, link = "/treninzi", 'main a.card[href^="/treninzi/"]'
    else:
        page, link = resolve(pg, "trening:1"), "main a.day-card"
        if page is None:
            return None
    pg.goto(BASE + page)
    pg.wait_for_load_state("networkidle")
    path = pg.evaluate(NTH_LINK, [link, int(n)])
    if path:
        FOUND[r] = path
    return path


def player(pg, r: str) -> str | None:
    """The player's pages of the pass the walk opens on day N (dan:N, found
    first): "kreni:N" presses the day's Kreni (Nastavi, should a pass be in
    progress already: the same form) and is the exercise it lands on;
    "kraj:N" is where that exercise's "Završi trening" leads. Both kept in
    FOUND."""
    kind, n = r.split(":")[:2]
    if kind == "kreni":
        day = FOUND.get(f"dan:{n}") or resolve(pg, f"dan:{n}")
        if not day:
            return None
        pg.goto(BASE + day)
        pg.wait_for_load_state("networkidle")
        button = pg.locator("main form.go button[type=submit]")
        if not button.count():
            return None
        with pg.expect_navigation():
            button.first.click()
    else:
        start = FOUND.get(f"kreni:{n}")
        if not start:
            return None
        pg.goto(BASE + start)
        pg.wait_for_load_state("networkidle")
        end = pg.locator("main a.pl-end")
        if not end.count():
            return None
        with pg.expect_navigation():
            end.first.click()
    pg.wait_for_load_state("networkidle")
    path = urlparse(pg.url).path
    FOUND[r] = path
    return path


def run(pg, routes, who, theme, width, findings):
    for r in routes:
        key = f"{who}/{theme}/{width}px{r}"
        path = r
        if r.startswith("vjezba:"):                   # an exercise's page, by its name on the library's list
            pg.goto(BASE + "/treninzi/vjezbe")
            pg.wait_for_load_state("networkidle")
            path = pg.evaluate(FIND_EXERCISE, r.split(":", 1)[1])
            if not path:
                findings["head"].append((key, f"no exercise {r.split(':', 1)[1]!r} on /treninzi/vjezbe (the demo seed?)"))
                continue
        elif r.startswith(("trening:", "dan:")):       # a programme or a day of ivan's, by its link
            path = resolve(pg, r)
            if not path:
                findings["head"].append((key, f"nothing found for {r!r} (the demo seed? the client's walk first?)"))
                continue
        elif r.startswith(("kreni:", "kraj:")):        # the player, on the pass the walk opens
            path = player(pg, r)
            if not path:
                findings["head"].append((key, f"nothing found for {r!r} (the demo seed? dan:N first?)"))
                continue
        pg.goto(BASE + path)
        pg.wait_for_load_state("networkidle")
        if pg.locator("#fbPrompt").count():
            pg.keyboard.press("Escape")
        res = pg.evaluate(CHECKS)
        findings["_onphoto"].append(res.get("onPhoto", 0))
        for k in ("overflow", "contrast", "tap", "alt", "label", "inner"):
            if k == "tap" and width >= 500:
                continue                      # tap size is a touch concern only
            for item in res[k]:
                findings[k].append((key, item))
        h = res["head"][0]
        if h["h1"] != 1:
            findings["head"].append((key, f"h1 count = {h['h1']}"))
        if h["jump"]:
            findings["head"].append((key, f"heading jump {h['jump']}"))
        if r.startswith("kraj:") and f"dan:{r.split(':')[1]}" in FOUND:
            # the pass "kreni:N" opened goes again, so a re-run starts clean
            pg.request.post(BASE + FOUND[f"dan:{r.split(':')[1]}"] + "/odustani")


def main():
    findings = collections.defaultdict(list)
    fingerprint = ui_fingerprint()        # taken BEFORE the walk: an edit made mid-run must not get stamped
    with sync_playwright() as p:
        b = p.chromium.launch()
        for theme, width in RUNS:
            for email, pw, routes, who in (
                    (None, None, ANON, "anon"),
                    ("ivan@qmt.local", "lozinka123", CLIENT, "client"),
                    ("trener@qmt.local", "trener123", OWNER, "owner")):
                # 390px is a PHONE: emulate a touch device so `pointer: coarse`
                # rules (the grown .btn-sm/.act) actually apply — otherwise every
                # small button fails the tap check for a reason no phone has
                ctx = b.new_context(viewport={"width": width, "height": 900},
                                    has_touch=(width < 500), is_mobile=(width < 500))
                pg = ctx.new_page()
                pg.goto(BASE + "/login")
                pg.evaluate("t => localStorage.setItem('qmt-theme', t)", theme)
                if email:
                    pg.fill("input[name=email]", email)
                    pg.fill("input[name=password]", pw)
                    pg.click("button[type=submit]")
                    pg.wait_for_load_state("networkidle")
                run(pg, routes, who, theme, width, findings)
                ctx.close()
        b.close()

    # A baseline holds the signatures of findings already judged. Runs report
    # what is NEW relative to it; --save-baseline re-records the current state
    # after a deliberate review (say why in the commit).
    known = set(json.loads(BASELINE.read_text())) if BASELINE.exists() and not SAVE_BASELINE else set()
    sigs_now = set()
    print("=" * 72)
    total_new = 0
    for k, label in (("overflow", "PAGE OVERFLOW"), ("inner", "ELEMENT OVERFLOW"),
                     ("contrast", "CONTRAST BELOW WCAG AA"), ("tap", "TAP TARGET < 32px"),
                     ("alt", "IMG WITHOUT ALT"), ("label", "UNLABELLED FORM CONTROL"),
                     ("head", "HEADINGS")):
        seen = {}
        for where, item in findings[k]:
            sig = k + "|" + (json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item))
            sigs_now.add(sig)
            seen.setdefault(sig, [0, where])
            seen[sig][0] += 1
        new = {s_: v for s_, v in seen.items() if s_ not in known}
        total_new += sum(v[0] for v in new.values())
        base_n = sum(v[0] for s_, v in seen.items() if s_ in known)
        print(f"\n### {label}: {sum(v[0] for v in new.values())} new" + (f"  (+{base_n} in baseline)" if base_n else ""))
        for sig, (n, where) in sorted(new.items(), key=lambda x: -x[1][0])[:14]:
            print(f"  ×{n:<3} {sig.split('|',1)[1][:100]}")
            print(f"       e.g. {where}")
    if SAVE_BASELINE:
        BASELINE.write_text(json.dumps(sorted(sigs_now), indent=0, ensure_ascii=False))
        print(f"\nbaseline saved: {len(sigs_now)} signatures → {BASELINE.name}")
    if sum(findings["_onphoto"]):
        print(f"\n(text on photographs, unmeasured by design: {sum(findings['_onphoto'])} elements across runs)")
    print(f"\nnew findings: {total_new}")
    failed = bool(findings["overflow"] or findings["inner"] or total_new)
    # Stamp only what was really checked: these files, served locally, and clean.
    if not failed and fingerprint and ("127.0.0.1" in BASE or "localhost" in BASE):
        STAMP.write_text(fingerprint + "\n")
        print(f"phone check passed at {', '.join(sorted({str(w) for _, w in RUNS if w < 500}))}px -> stamped {STAMP.name}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
