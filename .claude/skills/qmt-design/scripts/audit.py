"""Measured design audit — run BEFORE calling any UI work done.

    python .claude/skills/qmt-design/scripts/audit.py [http://127.0.0.1:8100]

Walks every page as anon / client / owner, dark + light, 1280px + 390px, and
reports: page + element horizontal overflow, WCAG-AA contrast failures, tap
targets under 32px, images without alt, unlabelled form controls, heading
order. Needs the dev server up and the demo seed loaded (scripts/seed_demo.py).
Contrast "ratio 1" on tinted elements is a known false positive (semi-
transparent backgrounds read as solid) — judge those by eye.
"""
import collections
import json
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100"
ANON = ["/", "/cjenik", "/login", "/signup", "/forgot", "/prehrana"]
CLIENT = ["/", "/raspored", "/karton", "/cjenik", "/prehrana", "/profil", "/treninzi", "/upitnik"]
OWNER = ["/", "/raspored", "/admin", "/clanarine", "/korisnici", "/statistika", "/treninzi", "/profil"]

CHECKS = r"""
() => {
  const out = {overflow: [], contrast: [], tap: [], alt: [], label: [], head: [], inner: []};
  const px = v => parseFloat(v) || 0;
  const de = document.documentElement;
  if (de.scrollWidth - de.clientWidth > 0) out.overflow.push(de.scrollWidth - de.clientWidth);

  const lum = c => {
    const m = c.match(/[\d.]+/g); if (!m) return null;
    if (m.length > 3 && parseFloat(m[3]) === 0) return null;
    const [r,g,b] = m.slice(0,3).map(x => { x = x/255; return x <= .03928 ? x/12.92 : Math.pow((x+.055)/1.055, 2.4); });
    return .2126*r + .7152*g + .0722*b;
  };
  const bgOf = el => {
    let n = el;
    while (n && n !== document.documentElement) {
      const l = lum(getComputedStyle(n).backgroundColor);
      if (l !== null) return l;
      n = n.parentElement;
    }
    return lum(getComputedStyle(document.body).backgroundColor) ?? 1;
  };
  const vis = el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'
           && getComputedStyle(el).opacity !== '0';
  };

  const TEXT = 'p,span,a,button,h1,h2,h3,h4,li,td,th,label,strong,em,div.hint,summary';
  for (const el of document.querySelectorAll(TEXT)) {
    if (!vis(el)) continue;
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
  return out;
}
"""


def run(pg, routes, who, theme, width, findings):
    for r in routes:
        pg.goto(BASE + r)
        pg.wait_for_load_state("networkidle")
        if pg.locator("#fbPrompt").count():
            pg.keyboard.press("Escape")
        res = pg.evaluate(CHECKS)
        key = f"{who}/{theme}/{width}px{r}"
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


def main():
    findings = collections.defaultdict(list)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for theme in ("dark", "light"):
            for width in (1280, 390):
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

    print("=" * 72)
    total = 0
    for k, label in (("overflow", "PAGE OVERFLOW"), ("inner", "ELEMENT OVERFLOW"),
                     ("contrast", "CONTRAST BELOW WCAG AA"), ("tap", "TAP TARGET < 32px"),
                     ("alt", "IMG WITHOUT ALT"), ("label", "UNLABELLED FORM CONTROL"),
                     ("head", "HEADINGS")):
        items = findings[k]
        total += len(items)
        print(f"\n### {label}: {len(items)}")
        seen = {}
        for where, item in items:
            sig = json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
            seen.setdefault(sig, [0, where])
            seen[sig][0] += 1
        for sig, (n, where) in sorted(seen.items(), key=lambda x: -x[1][0])[:14]:
            print(f"  ×{n:<3} {sig[:100]}")
            print(f"       e.g. {where}")
    print(f"\nfindings: {total}")
    sys.exit(1 if findings["overflow"] or findings["inner"] else 0)


if __name__ == "__main__":
    main()
