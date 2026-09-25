"""Regenerate references/tokens.md from base.html — run after any token change.

    python .claude/skills/qmt-design/scripts/extract_tokens.py

The skill quotes tokens from this file; generating it (rather than typing it)
is what keeps the skill from lying about the CSS.
"""
import re, pathlib, datetime
root = pathlib.Path(__file__).resolve().parents[4]
css = (root / "src/qmt/web/templates/base.html").read_text(encoding="utf-8")
def block(sel):
    m = re.search(re.escape(sel) + r"\s*\{(.*?)\n\s*\}", css, re.S)
    return [(k.strip(), v.strip(), (c or "").strip())
            for k, v, c in re.findall(r"(--[\w-]+):\s*([^;]+);\s*(/\*.*?\*/)?", m.group(1))] if m else []
light, dark = block(':root, [data-theme="light"]'), block('[data-theme="dark"]')
dk = {k: v for k, v, _ in dark}
fonts = re.findall(r"(--font-[\w-]+):\s*([^;]+);", css)
out = ["# QMT design tokens (generated from base.html — do not edit by hand)", "",
       f"_Regenerated {datetime.date.today().isoformat()} by scripts/extract_tokens.py_", "",
       "| token | light | dark | note |", "|---|---|---|---|"]
for k, v, c in light:
    out.append(f"| `{k}` | `{v}` | `{dk.get(k, v)}` | {c.strip('/* ').strip(' */')} |")
out += ["", "## Fonts", ""] + [f"- `{k}`: `{v}`" for k, v in fonts]
out += ["", "## Loaded weights", "", "- PT Sans 700 (display, uppercase)  ·  Inter 400/500/600/700/800 (body)"]
(root / ".claude/skills/qmt-design/references/tokens.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"tokens.md: {len(light)} tokens, {len(fonts)} fonts")
