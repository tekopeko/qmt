# Component catalog

All classes live in `src/qmt/web/templates/base.html` unless a page is named.
Class → what it is → how it behaves. When a row needs a control, find it here
first; a new class is a last resort and needs a comment explaining the gap.

## Layout

| class | where | what |
|---|---|---|
| `.topbar` | base | a floating dark-glass pill (999px, blur, sticky 10px below the top, max 1100px) on every screen and both themes; ONE row at every width: brand left, tabs middle, avatar right, all inside the pill's padding. `.brand-slot` takes the room the tabs leave and is a query container: the wordmark shows in full when the slot is ≥19.2rem, else "QMT" (never a window breakpoint — the pill is capped, so the window says nothing about the room inside). 7+ tabs run tight (`.nav:has(> a:nth-of-type(7))`), all tabs tighten ≤1200px and fold into ☰ ≤900px. Tabs never wrap. |
| `.nav a` / `.nav a.cta` / `.nav a.dark` / `.on` | base | tab; red pill (`.cta`); dark glass pill (`.dark`, the pill's own "black", theme-free because the bar is always dark); current page. Guest bar: Prijava `.cta` (plus Registriraj se at the same weight while signup is open) · "Kontakt" `.dark`; never a Cjenik tab, and no "Što nudimo" — the photo leads to the offer |
| `.topbar.compact` | base (guests) | Shape's small pill: `width: fit-content`, centred; the brand is content-sized (no slot query) and the wordmark shortens below 420px, where even the small pill cannot hold the name beside the ☰. Its drawer is a centred 300px card, not a sliver the pill's width |
| `.avatar` / `.user-menu` | base | initials circle → account menu on the YouTube pattern: identity header (ellipsized email), icon gutter rows (Profil, theme, Odjava), full-bleed hover |
| `main` | base | max-width 1100px, `clamp(14px,4vw,40px)` side padding; `main.full` for the landing |
| `main > h1`, `main > h1 + .hint` | base | the page header: title `clamp(1.6rem,3vw,2rem)` + one lead sentence, 70ch max — templates write bare `<h1>` / `<p class="hint">` with no inline style |
| `.card` | base | `--surface`, hairline, `--r-lg` (20px), `--shadow`; hero-grade cards (`.svc`, `.plan`, `.upitnik`, `.termini`) take `--r-xl` (28px) with 26px padding |
| `.crumbs` | base | breadcrumb: muted links, `/` separators, `.here` current |
| `.ed` / `.copy-toggle` / `.copy-bar` | base (trainer, owner) | in-place copy editor: `_copy.html` prints every slot in a `span.t` (`white-space: pre-line`, so the owner's line breaks show) and makes it an `.ed` for an editor; the fixed "✎ Uredi tekstove" pill toggles `body.editing` (dashed outlines, click to edit, `.ed-on` while open; an empty `.ed` keeps a 2.5em box so it can be clicked); Enter is a new line, ⌘/Ctrl+Enter saves; the bar under the pill (as wide as its content, at most the window less 20px) shows label, an "n znakova" counter, the `.cb-hint` "Enter = novi red · ⌘/Ctrl+Enter = spremi" (600px and up) and Spremi / Zadano / Odustani. Visitors get a bare `span.t`, no editor markup |
| `ul[data-list]` / `.ed-x` / `.ed-add` | base (trainer, owner) | an editable list (`c.points`): each item an `.ed` with `data-index`, a 32px round `.ed-x` ✕ beside it (negative margin, so the line height holds) and an `.act.ed-add` "+ Dodaj stavku" after the list, hidden at the count limit; both only under `body.editing`. The bar names the item ("…: stavka 2") and its Zadano reads "Zadano (cijela lista)" |
| `.ed-flag` / `.is-off` | base (trainer, owner) | the edit-mode toggle of a `copy.FlagSlot` (an on/off switch, the landing's announcements): the first child of the box it switches (`data-flag`), a 32px pill, green `--good-fill` "● Prikazano" / grey `--surface-2` "○ Skriveno", saved at a click, no confirm (hiding loses no text). A switched-off box is `.is-off`: hidden, shown only in edit mode with its content dimmed to .55 and the toggle at full strength; its `data-flag-group` follows its boxes (`.is-off` when none is on, `.single` on their row when one is). A visitor gets neither the toggle nor a hidden box |
| `.featured-tag` | base | "Najpopularnije" chip in the top-right corner of a `position: relative` card: accent tint + `--accent-tint-ink`. Used by `/cjenik` and the landing's offer |
| `.alert` / `.alert.ok` | base | flash after a redirect (`?error=` / `?ok=`); `?cta=<plan>` adds a "Pogledaj cjenik →" pill |
| `#authDlg` `.fb-modal.auth` | base (guests) | login + registration in one modal (login only, no tabs, while signup is closed), `.auth-tabs` segmented (accent-tinted selected), 48px inputs, `.pw-eye` toggle; opened by any `<a data-auth="login\|signup">`, hrefs stay as the no-JS fallback; `next` = current page |
| `#a2hs` `.card.a2hs` | base (clients) | install banner: phones only (`pointer: coarse`, plus a `pointer: fine` CSS kill-switch), not in standalone mode, not on the first page load, back a week after each dismissal until installed (`localStorage qmt-a2hs`: when it was dismissed, or `installed` once the native prompt was accepted; the owner's call, 16.10.2026); iOS gets share-sheet steps, Chrome gets a real "Instaliraj" via `beforeinstallprompt` |

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
with `.red` on the last line, then the owner's announcements (**Aktualno**,
below), then the photo. No lead, no button and no note in the hero since
16.10.2026, for anyone (the owner's call: the announcements come first): a
guest has the compact pill's Prijava / Kontakt, a member the tabs and the
offer cards' buttons, and the photo leads to the offer. The hero photo `.stage` is an `<a href="#usluge">`: the whole card leads to the
offer, with a small `.go` arrow as the hint a phone needs (no hover there) and
`data-photo` for the audit. **The offer** (`#usluge`): three tiers of the
online plan as `.offer` cards in `.offer-grid` — italic uppercase title, one
`.lead` line (two lines reserved), an editable list of dotted facts
(`c.points`, up to six), then a `.foot` pinned to the bottom holding the
`.addon` line, the `.price` (2.1rem number + muted unit) and one button, so
add-on, price and button sit level across the row. Each tier has two `.price`
blocks, `data-period="month"` and `"year"` (`hidden`); the `.period` switch
under the cards (the `.auth-tabs` idiom on a `--surface` track — the tint over
`--surface-2` is 4.34:1 in dark) shows one on all three, per page view, and is
hidden until the script runs. Tier prices are mostly owner-typed text, so the
cards (tiers and gym) reserve a second price line (`min-height`, 900–1100px)
and stay level whatever is typed. `.featured` (tier 2) is taller, not shifted
(`margin-block: -16px` + matching padding, desktop only) and carries
`.featured-tag`; `.mine` gets the green-tinted border. **Below 900px each row
of cards is a carousel** (`.swipe-row`, on `.offer-grid` and `.gym-grid`):
the band drops its side padding, the row becomes a flex scroller
(`scroll-snap-type: x mandatory`, cards `flex: 0 0 86%` snapping to the
centre, scrollbar hidden, the gutter as its own padding) and the `.dots`
under it are 32px buttons around an 8px dot (`--line`, lit `--accent`,
`aria-current`), one per card, made by the script (no script, no dots; it
skips a card with no box, `display: none`, and makes none for fewer than
two), that follow the scroll (IntersectionObserver) and bring their card in
on tap.
A row opens on its `.featured` card, centred at once (the tiers: PRO, START
a swipe to the left, ELITE to the right), else on its first; the script does
it only where the row scrolls, so the desktop grid is untouched.
**The gym** (`#dvorana`, below): the same `.offer` cards in `.gym-grid` (two
columns ≥900px, capped at 760px so each is about a tier's width; the swipe
row, two dots, below), not featured; Individualno's other
prices are a muted `.price-note` under its `.price`, and an empty one in the
Dvorana card holds the same two lines so both rows stay level. Both gym cards
are tiers too (the plan's real monthly price, an editable yearly one) with
their own `.period` under `.gym-grid`, and the two switches are one choice:
pressing either sets every `.price[data-period]` on the page and
`aria-selected` on both. Buttons: accent `.btn-sm` on the featured card,
neutral `.cta` beside it, green `.owned` for a plan the visitor has. Plan
prices arrive from the route (`offer_prices`), are public unless
`PUBLIC_PRICES=off` (which also hides both switches), and no public page links
to `/cjenik`. **Aktualno** (`#aktualno`, in the hero since 16.10.2026,
between the h1 and the photo: the first thing on the page): the owner's two
announcements for the month as `.event` cards in `.evs` (text left-aligned
in the centred hero): the `.card` surface at `--r-lg` (a shallow card, not
the stage's `--r-xl`), one flex row that WRAPS, its items centred on their
line and its lines at the top (`align-content: flex-start`: a card stretched
to its neighbour's height keeps its chip and title level with the
neighbour's): a `.tag` chip (accent tint + `--accent-tint-ink`; scoped
`.event .tag`, not the photo's glass `.tag`), a `.head` holding the italic
uppercase title of `.offer` at 1.15rem (an `h2`: it sits straight under the
page's `h1`) over a `.when` line behind a 7px accent dot (on the baseline,
so a wrapped line keeps it on its first), a muted `.text` that takes the
free room (`flex: 1 1 280px`), and one grey `.act` to `/#kontakt` in a
`.foot` at the right end (the red button stays on the featured tier). A long
text makes a card taller, never wider: no piece is wider than the card, and
a long one wraps onto a line of its own. **From 900px** the two sit side by
side (two columns 16px apart, together as wide as the photo; the owner's
call, 16.10.2026), each in two lines: chip, title and link, then the text
across the card (`order: 1; flex-basis: 100%`); one card alone (`.single`)
is one 760px column, centred, and edit mode keeps both columns. **Below
900px** `.evs` is a `.swipe-row` with its `.dots`, like the tiers: it runs to
the screen's edges (the hero's side padding moves into `.hero-inner`, and the
row's negative margins reach into it, never past it, which would be
overflow), cards 86% wide, a column below 700px; one card alone takes the
whole row (`.single`, `:only-child`; 86% again in edit mode, where both
show). It **moves on by itself** (`data-auto="5000"`, the owner's 5 s): the
next card glides in as its dot would bring it, after the last the first, and
the lit dot follows. Quiet whenever a person is on the row or its dots (a
finger, a mouse where the device can hover, the focus), with the whole delay
again once they leave; no tick while the tab is hidden or the row is off the
screen; never under `prefers-reduced-motion`; only where the row scrolls.
Each card is switched off with its `.ed-flag`, its first item in edit mode;
a visitor never gets a hidden one, nor the box when both are. Info band
`.info-grid`: radno vrijeme table, `.crow` contact rows
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
