# Component catalog

All classes live in `src/qmt/web/templates/base.html` unless a page is named.
Class → what it is → how it behaves. When a row needs a control, find it here
first; a new class is a last resort and needs a comment explaining the gap.

## Layout

| class | where | what |
|---|---|---|
| `.topbar` | base | ONE row at every width: brand left, tabs middle, avatar right. Wordmark shortens to "QMT" ≤1200px, tabs fold into ☰ ≤900px. Tabs never wrap. |
| `.nav a` / `.nav a.cta` / `.on` | base | tab, red pill tab (guest: Prijava + Registriraj se, both red — equal weight), current page |
| `.avatar` / `.user-menu` | base | initials circle → account menu on the YouTube pattern: identity header (ellipsized email), icon gutter rows (Profil, theme, Odjava), full-bleed hover |
| `main` | base | max-width 1100px, `clamp(14px,4vw,40px)` side padding; `main.full` for the landing |
| `.card` | base | `--surface`, hairline, 16px radius, `--shadow` |
| `.crumbs` | base | breadcrumb: muted links, `/` separators, `.here` current |
| `.alert` / `.alert.ok` | base | flash after a redirect (`?error=` / `?ok=`); `?cta=<plan>` adds a "Pogledaj cjenik →" pill |

## Buttons and links

| class | look | hover | use |
|---|---|---|---|
| `.btn` | filled `--accent-fill`, 12px, `--shadow-btn` | fill → `--accent-fill-hover`, lifts 1px | the page's ONE primary |
| `.btn-sm` (with `.btn`) | 10px, no glow; grows under `pointer: coarse` | as `.btn` | primary inside a card |
| `.btn-ghost` | surface + hairline | `--surface-2` | secondary beside a primary |
| `.btn-quiet` | `--accent-dim` tint, accent text | fills accent | accent action in dense rows |
| `.act` | grey pill 999px, 5px/13px | tint deepens via `color-mix`, border darkens | row action |
| `.act-quiet` | transparent pill, muted text | faint wash | least important row action |
| `.act-absent` (karton) | amber tint + amber border | deeper tint, **not** a flood | "Nisam bio/la" — the only non-brand hue |
| `.tlink` | accent, 600, no underline | colour → `--accent-strong` | link inside prose |
| `.redo` (karton) | hairline pill, hover-revealed on pointer devices only | takes the razina colour | "Ispuni ponovno" |

`a.btn, a.btn-sm, a.btn-ghost, a.btn-quiet, a.act` get `text-decoration: none;
display: inline-flex` — an anchor with only `.btn-sm` otherwise keeps the
browser underline while looking like a button.

## Forms

| element | rule |
|---|---|
| `input, select, textarea` | 12px radius, 1.5px hairline, `--surface`, 10px/13px; focus → accent border, no outline |
| `label` | uppercase .76rem `--muted`, letter-spacing .06em — **every label**, so override it (`text-transform: none`) when a `<label>` is a pill, e.g. `.tiers label` on /cjenik |
| `.field` | 14px bottom margin |
| radio/checkbox pills | `.tiers` on /cjenik: `label:has(input:checked)` → accent border + tint; `accent-color: var(--accent)` |
| confirm | form with `data-confirm` / `-title` / `-cta` → `#confirmDlg` opens before submit |

## Status text and chips

| class | what |
|---|---|
| `.hint` | secondary sentence, `--muted` |
| `.owned` (cjenik/landing) | green bold state line "✓ Aktivna članarina"; muted variant for "otkazana" |
| `.chip` (karton) | small grey label — "Nisam bio/la", "bez osvrta"; `.chip.off` uppercase for OTKAZANO |
| `.rpe` (karton) | grey numeric badge "napor 7/10"; `.rpe.feel` green for osjećaj, `.rpe.feel.low` grey for "slabo" (green "slabo" read as a contradiction) |
| `.ramp` (karton) | three rungs, filled to the razina, captioned "Razina N od 3" — colour never alone |

## Page conventions

**Landing (`landing.html`).** Hero: kicker with a red dash, uppercase PT Sans h1
with `.red` on the last line, lead paragraph, `.cta-row` of `.btn-hero` (15px/28px,
14px radius; `.secondary` = translucent white). Hero CTAs follow membership: guest →
Registriraj se (primary) + Pogledaj cjenik + Što nudimo; plan-less client → Pogledaj
cjenik; member → Rezerviraj termin. Service cards `.svc` in a 3×2 `.svc-grid`:
icon tile, title, copy with `min-height: 4.65em`, accent meta line, CTA pinned with
`margin-top: auto` — owned plan = green filled `.owned` (`--good-fill`, transparent
1px border so it matches the neutral button's height), open plan = neutral
`.svc-cta`. Info band `.info-grid`: radno vrijeme table, `.crow` contact rows
(14px stroke icon + text, address is the Maps link), `.socials` icon row (20px
glyphs, muted → accent on hover, 32px targets).

**Cjenik (`cjenik.html`).** `.plan` cards, copy `min-height: 3.9em`, `.price` with
`<small>` unit, `.foot` pinned bottom. Price source order: Stripe Price → shop
reference (`REFERENCE_PRICES`, in the shop's own unit) → "na upit". Subscribed
tier shows ITS price ("70 € / mjesečno · 12 treninga"), other tiers as `.act`
switch buttons under a hairline `.switch`; `.plan.mine` gets a green inset bar.

**Karton (`karton.html`).** Upitnik block `.upitnik.lvl-*` tinted by razina
(`--lvl`/`--lvl-soft` per theme), diary `.log-entry` rows in four states
(written / `.is-absent` / cancelled / open — `.fresh` gets the accent inset bar),
`.le-actions` right-aligned pills, `.le-edit` inline form toggled by
`qmtToggleForm`. Rail `.termini` holds only Nadolazeći.

**Calendar (`calendar.html`).** Seven `.day-col` on desktop → single agenda on
phones (`.empty-day` hidden). `.sess.mine` = accent tint + inset bar,
`.past`/`.canceled` at .45 opacity, `.today .day-head` red. "Moja članarina" table
+ usage line "3 od 12 treninga u ovom ciklusu" for tiered plans.

## Scripts

- `scripts/audit.py [base_url]` — the measured audit (see SKILL.md). Exit 1 on overflow.
- `scripts/extract_tokens.py` — regenerate `references/tokens.md` from `base.html`.
