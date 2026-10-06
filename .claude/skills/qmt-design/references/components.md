# Component catalog

All classes live in `src/qmt/web/templates/base.html` unless a page is named.
Class → what it is → how it behaves. When a row needs a control, find it here
first; a new class is a last resort and needs a comment explaining the gap.

## Layout

| class | where | what |
|---|---|---|
| `.topbar` | base | a floating dark-glass pill (999px, blur, sticky 10px below the top, max 1100px) on every screen and both themes; ONE row at every width: brand left, tabs middle, avatar right, all inside the pill's padding. `.brand-slot` takes the room the tabs leave and is a query container: the wordmark shows in full when the slot is ≥19.2rem, else "QMT" (never a window breakpoint — the pill is capped, so the window says nothing about the room inside). 7+ tabs run tight (`.nav:has(> a:nth-of-type(7))`), all tabs tighten ≤1200px and fold into ☰ ≤900px. Tabs never wrap. |
| `.nav a` / `.nav a.cta` / `.on` | base | tab, red pill tab (guest: Prijava, plus Registriraj se at equal weight while `SIGNUP_MODE` is not closed; never a Cjenik tab), current page |
| `.avatar` / `.user-menu` | base | initials circle → account menu on the YouTube pattern: identity header (ellipsized email), icon gutter rows (Profil, theme, Odjava), full-bleed hover |
| `main` | base | max-width 1100px, `clamp(14px,4vw,40px)` side padding; `main.full` for the landing |
| `main > h1`, `main > h1 + .hint` | base | the page header: title `clamp(1.6rem,3vw,2rem)` + one lead sentence, 70ch max — templates write bare `<h1>` / `<p class="hint">` with no inline style |
| `.card` | base | `--surface`, hairline, `--r-lg` (20px), `--shadow`; hero-grade cards (`.svc`, `.plan`, `.upitnik`, `.termini`) take `--r-xl` (28px) with 26px padding |
| `.crumbs` | base | breadcrumb: muted links, `/` separators, `.here` current |
| `.featured-tag` | base | "Najpopularnije" chip in the top-right corner of a `position: relative` card: accent tint + `--accent-tint-ink`. Used by `/cjenik` and the landing's offer |
| `.alert` / `.alert.ok` | base | flash after a redirect (`?error=` / `?ok=`); `?cta=<plan>` adds a "Pogledaj cjenik →" pill |
| `#authDlg` `.fb-modal.auth` | base (guests) | login + registration in one modal (login only, no tabs, while signup is closed), `.auth-tabs` segmented (accent-tinted selected), 48px inputs, `.pw-eye` toggle; opened by any `<a data-auth="login\|signup">`, hrefs stay as the no-JS fallback; `next` = current page |
| `#a2hs` `.card.a2hs` | base (clients) | install banner: phones only (`pointer: coarse`, plus a `pointer: fine` CSS kill-switch), not in standalone mode, not on the first page load, dismissed once (`localStorage qmt-a2hs`); iOS gets share-sheet steps, Chrome gets a real "Instaliraj" via `beforeinstallprompt` |

## Buttons and links

| class | look | hover | use |
|---|---|---|---|
| `.btn` | filled `--accent-fill` pill (999px), `--shadow-btn` | fill → `--accent-fill-hover`, lifts 1px | the page's ONE primary |
| `.btn-sm` (with `.btn`) | pill, 7px/14px, no glow; grows under `pointer: coarse` | as `.btn` | primary inside a card |
| `.btn-ghost` | surface + hairline | `--surface-2` | secondary beside a primary |
| `.btn-quiet` | `--accent-dim` tint, `--accent-tint-ink` text | fills accent | accent action in dense rows |
| `.act` | grey pill 999px, 5px/13px | tint deepens via `color-mix`, border darkens | row action |
| `.act-quiet` | transparent pill, muted text | faint wash | least important row action |
| `.act-absent` (karton) | amber tint + amber border | deeper tint, **not** a flood | "Nisam bio/la" — the only non-brand hue |
| `.tlink` | accent, 600, no underline | colour → `--accent-strong` | link inside prose |
| `.redo` (karton) | hairline pill, hover-revealed on pointer devices only | takes the razina colour | "Ispuni ponovno" |

`a.btn, a.btn-sm, a.btn-ghost, a.btn-quiet, a.act` get `text-decoration: none;
display: inline-flex` — an anchor with only `.btn-sm` otherwise keeps the
browser underline while looking like a button.

**Footprint parity.** Every button carries a 1px border — transparent on filled
ones, `--line` on ghosts — so a filled `.btn-sm` and a `.btn-ghost.btn-sm` in the
same row are the same height (the confirm modal's Odustani/Potvrdi were 31/29
until this rule). If you add a button variant, keep the border box.

**Legacy aliases still in templates** (`base.html` compat block): `--ink`,
`--ink-2`, `--ground`, `--ground-2`, `--signal`, `--signal-ink` → the modern
tokens; `--danger` → `--accent`; `.btn-signal` → plain `.btn`. Read them as their
targets; do not introduce new uses.

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
14px radius; `.secondary` = translucent white). Hero CTAs follow membership: member →
Rezerviraj termin; plan-less client → Pogledaj cjenik; guest → Registriraj se while
signup is open, else Što nudimo + Kontakt. The hero photo `.stage` is an `<a href="#usluge">`: the whole card leads to the
offer, with a small `.go` arrow as the hint a phone needs (no hover there) and
`data-photo` for the audit. **The offer** (`#usluge`): three `.offer` cards in
`.offer-grid` (stacked below 900px) — italic uppercase title, one `.lead` line
(two lines reserved), three dotted facts, then a `.foot` pinned to the bottom
holding the `.addon` line, the `.price` (2.1rem number + muted unit) and one
button, so add-on, price and button sit level across the row. `.featured` is
taller, not shifted (`margin-block: -16px` + matching padding) and carries
`.featured-tag`; `.mine` gets the green-tinted border. Buttons: accent
`.btn-sm` on the featured card, neutral `.cta` beside it, green `.owned` for a
plan the visitor has. Prices arrive from the route (`offer_prices`), are public
unless `PUBLIC_PRICES=off`, and no public page links to `/cjenik`. Info band `.info-grid`: radno vrijeme table, `.crow` contact rows
(14px stroke icon + text, address is the Maps link), `.socials` icon row (20px
glyphs, muted → accent on hover, 32px targets).

**Cjenik (`cjenik.html`).** `.plan` cards (`--r-xl`, italic uppercase `.plan-h`), copy
`min-height: 3.9em`, `.price` with `<small>` unit, `.foot` pinned bottom. Grupni is
`.featured`: accent-tinted border, raised 8px on desktop, `.featured-tag`
"Najpopularnije" chip top-right. Price source order: Stripe Price → shop
reference (`REFERENCE_PRICES`, in the shop's own unit) → "na upit". Subscribed
tier shows ITS price ("70 € / mjesečno · 12 treninga"), other tiers as `.act`
switch buttons under a hairline `.switch`; `.plan.mine` gets a green-tinted border
(the same move as `.featured`; `.mine` is declared later so it wins on grupni).

**Profil (`profil.html`).** Membership cards `.mcard.active` / `.mcard.lapsed`:
green- or accent-tinted border, state word top-right, plan CTA pinned bottom.

**Karton (`karton.html`).** Upitnik block `.upitnik.lvl-*` tinted by razina
(`--lvl`/`--lvl-soft` per theme), diary `.log-entry` rows in four states
(written / `.is-absent` / cancelled / open — `.fresh` gets the accent inset bar),
`.le-actions` right-aligned pills, `.le-edit` inline form toggled by
`qmtToggleForm`. Rail `.termini` holds only Nadolazeći. `.upitnik` and `.termini`
are `--r-xl`; `.log-entry` rows are `--r-md` and keep the accent inset bar for
`.fresh` — at 12px the bar still reads as a bar.

**Calendar (`calendar.html`).** Seven `.day-col` on desktop → single agenda on
phones (`.empty-day` hidden). "Moja članarina" is `.mtable` in a `.mtable-wrap`
(scrolls as a last resort): four columns that fit 360px through tighter gutters
and a smaller face below 420px. `.sess.mine` = accent tint + inset bar,
`.past`/`.canceled` at .45 opacity, `.today .day-head` red. "Moja članarina" table
+ usage line "3 od 12 treninga u ovom ciklusu" for tiered plans.

## Scripts

- `scripts/audit.py [base_url]` — the measured audit (see SKILL.md). Exit 1 on overflow.
- `scripts/extract_tokens.py` — regenerate `references/tokens.md` from `base.html`.
