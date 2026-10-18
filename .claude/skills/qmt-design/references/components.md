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
| `.ed-img` / `.ed-img-x` / `#edImgFile` | base (trainer, owner) | the edit-mode pills of a `copy.ImageSlot`, a photo behind a box (the landing's announcements; the box carries `data-image`): `.ed-img` "Dodaj sliku" / "Promijeni sliku" opens the hidden file picker (`#edImgFile`: jpg, png, webp) and posts to `/copy/<key>/slika`; the answer's URL becomes the box's first child, `img.bg`, and the box turns `.has-img` + `data-photo`. `.ed-img-x` "Ukloni sliku" (only with a photo) asks first, as an item's ✕ ("Ukloni?" for 4 s, then `reset=1`). 32px pills like `.ed-flag` (`--surface-2` / `--muted`), after it; on a photo (`[data-photo]`) a solid `--surface` pill with `--text` ink: the editor's controls, not text on a photograph. A failure is said in the bar |
| `.featured-tag` | base | "Najpopularnije" chip in the top-right corner of a `position: relative` card: accent tint + `--accent-tint-ink`. Used by `/moja-clanarina`'s "Dodaj plan" and the landing's offer |
| `.alert` / `.alert.ok` | base | flash after a redirect (`?error=` / `?ok=`); `?cta=<plan>` adds a "Pogledaj cjenik →" pill to that plan's card on `/moja-clanarina` (`#plan-<key>`) |
| `#authDlg` `.fb-modal.auth` | base (guests) | login + registration in one modal (login only, no tabs, while signup is closed), `.auth-tabs` segmented (accent-tinted selected), 48px inputs, `.pw-eye` toggle; opened by any `<a data-auth="login\|signup">`, hrefs stay as the no-JS fallback; `next` = current page |
| `#a2hs` `.card.a2hs` | base (clients) | install banner: phones only (`pointer: coarse`, plus a `pointer: fine` CSS kill-switch), not in standalone mode, not on the first page load, back a week after each dismissal until installed (`localStorage qmt-a2hs`: when it was dismissed, or `installed` once the native prompt was accepted; the owner's call, 16.10.2026); iOS gets share-sheet steps, Chrome gets a real "Instaliraj" via `beforeinstallprompt` |
| `.next-termin` | calendar (clients) | "Tvoj sljedeći termin", every width, right under `.week-head`: a `.card` (padding 14px 16px) with `.sess.mine`'s inset accent bar on its left edge; a `.sec-kicker` caption (700 .74rem uppercase, letter-spaced, `--accent`), the day and time (700, tabular) with a muted "danas" / "sutra" / "za N dana" (or "OTKAZANO" in `--danger`), the title + `.tag-11`; at the right end the list's `.unbook` ✕ (the same `unbook` macro), or "Otkazivanje do 12 h prije termina" under the title. No booking, no card (no empty state) |
| `.day-strip` | calendar (≤860px) | the week as seven `<button data-day>` (Shape's "Moj napredak" strip): `pon` (.72rem, uppercase, muted) over `12` (1rem 700, tabular), 52px tall, `flex: 1 1 0` up to 44px wide so seven fit 360px, `--r-md`, hairline on `--surface`. Chosen: `aria-pressed="true"`, `--accent-fill` with `--accent-ink`; today (not chosen): a 2px `--accent` ring, `aria-current="date"`; no termini: muted label at .6 (still tappable: "Nema termina"); `.has-mine`: a 6px dot under the number. `aria-label="pon 12.10."`. Rendered `hidden`; the script shows it, so without JS there is no dead strip. Absent for an empty week |
| `.sess-row` | calendar (≤860px, one-day view) | one termin as one row, min-height 56px (the row is the tap target): time (700, tabular) · title on one line (a `-webkit-line-clamp: 1` clamp, so a long title ends in "…" without widening the row) + `.tag-11` outside the clamp · the state at the right end in .8rem: `n/8 ›` (count `--good`), "slobodno ›" (1:1), "rezervirano ✓ ›" (`--good`, inset accent bar), "puno" / "zauzeto" (`--danger`), "potrebna članarina" (muted, may break in two), "otkazano" (`--danger`, title struck). A `<button>` when a tap does something for a client (`data-state` book / mine / mine-late opens `#sheet`), the trainer's `<a>` to `/admin/session/{id}` ("Polaznici n/8 ›"), else a plain `div`; past and canceled at .45. Shown instead of the `.sess` cards only once the script marks the week `.one-day` |
| `#sheet` `.fb-modal.sheet` | calendar (clients) | the bottom sheet a row opens: ONE dialog filled from the row's `data-*` (kicker day, h2 "07:00–08:00 · Grupni trening" + chip, `.fb-lead` "0 od 8 mjesta zauzeto" / "Termin je slobodan." / "Rezervirano"), then ONE action: Odustani + "Rezerviraj" (`POST /book/{id}`, with the "Isti termin svaki tjedan do kraja plaćenog razdoblja" checkbox, `series=1`, on weekly slots), Odustani + "Otkaži rezervaciju" (`POST /cancel/{id}`; the sheet is the confirmation, no `data-confirm`), or, inside the 12 h, the sentence and "U redu". ≤860px it is docked to the bottom (full width, top corners `--r-lg`, `env(safe-area-inset-bottom)`); the ✕, Escape, the backdrop and Odustani close it; the primary action takes the focus |
| `.view-switch` in `.view-row` | calendar (≤860px, clients) | "Tjedan \| Mjesec" (18.10.2026): the landing's `.period` idiom as two links with `aria-pressed` (each view is its own URL): a `--surface` track with a hairline, 36px pills in muted 600 .85rem, the chosen one `--accent-dim` with `--accent-tint-ink`. "Tjedan" → `?week=&day=` of the shown day, "Mjesec" → `?view=month&month=` of its month; the strip's script keeps both on the day it shows. On the week page under the week buttons (`.view-row` takes `.week-head`'s whole line), on the month page under the next-termin card. Hidden from 861px, never rendered for the trainer |
| `.month` / `.mday` | calendar (`?view=month`, clients) | the month overview, Shape's "Moj napredak" grid: a `.card` (max 480px, padding 10px 8px 12px), a `.mhead` row PON … NED (600 .72rem uppercase, muted, `aria-hidden`), then Monday-first `.mweek` rows of seven `<a class="mday">`: 44px tall, `--r-md`, the number 700 .95rem tabular over a 6px dot slot, each a link to `?week=<its Monday>&day=<date>` with `aria-label="pon 20.10., članarina aktivna, rezervacija"`. States compose: `.covered` (the paid period, `db.covered_days`) a `--good` tint at 12% (in both themes: at the planned 16 / 14% the past days' muted numbers fell under AA; at 12% the lowest is 4.87:1 dark, 4.51:1 light); `.mine` the strip's accent dot; `.today` a 2px inset `--accent` ring + `aria-current="date"`; `.past` a muted number; `.other` (another month) muted 400, never tinted or dotted. A mouse's hover rings the cell (1px, `--text` at 30%): a deeper tint would take the muted numbers under AA. `.month-legend` at the card's foot (swatch, dot, ring), `.month-note` under it ("Članarina vrijedi do …", or "Nemaš aktivnu članarinu" + "Pogledaj cjenik →"), `.month-nav` above it, as wide as the card: the label (`.range`, "listopad 2026.") and ‹ prošli mjesec · danas · idući mjesec › (`.week-nav`; "danas" only away from today's month), the buttons on a line of their own on a phone |

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
| `.unbook-x` in `form.unbook` (calendar) | 32px round ✕ at every pointer, no fill, `--muted`; pinned 6px into the top-right corner of a "Moje rezervacije" card (the card's `.t` line reserves 28px for it and never wraps); on phones at the right end of the booking's row, and at the right end of `.next-termin` | faint `--text` wash, ink → `--text`; never the red flood | cancel a booking: asks first via `data-confirm` ("Otkazati rezervaciju?" / "Otkaži rezervaciju"; "Maknuti otkazani termin?" / "Makni" for a termin the trainer canceled, whose ✕ stays unfaded on the faded card). Only while cancelling is allowed (`db.cancel_deadline`); after that the card says "Otkazivanje do 12 h prije termina" |

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
| `label` | uppercase .76rem `--muted`, letter-spacing .06em — **every label**, so override it (`text-transform: none`) when a `<label>` is a pill, e.g. `.tiers label` on /moja-clanarina |
| `.field` | 14px bottom margin |
| radio/checkbox pills | `.tiers` on /moja-clanarina (`_tiers.html`): `label:has(input:checked)` → accent border + tint, `--accent-tint-ink` text; `accent-color: var(--accent)` |
| confirm | form with `data-confirm` / `-title` / `-cta` → `#confirmDlg` opens before submit |

## Status text and chips

| class | what |
|---|---|
| `.hint` | secondary sentence, `--muted` |
| `.owned` (landing) | the offer card's green "✓ Rezerviraj termin →" for a plan the visitor has |
| `.chip` (karton) | small grey label — "Nisam bio/la", "bez osvrta"; `.chip.off` uppercase for OTKAZANO |
| `.chip` (moja_clanarina) | a plan's state in words, at the right of its name (999px, 700 .78rem, nowrap; it goes under the name when both do not fit): `.ok` "aktivna" (`--good-fill` / `--good-ink`), `.due` "dospijeva za N dana" / "sutra" / "danas", N ≤ 7 to dospijeće (`--accent-dim` / `--accent-tint-ink`), `.lapsed` "istekla" (`--accent-tint-ink` on `--surface-2`: plain `--danger` there is 4.3:1, under AA), `.off` "otkazana · vrijedi do kraja" (`--muted` on `--surface-2`) |
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
(`scroll-snap-type: x mandatory`, cards `flex: 0 0 92%` snapping to the
centre, scrollbar hidden, the gutter as its own padding: a card a little
bigger and a sliver of the next, about 18px at 390px, as Shape's; the
owner's call, 17.10.2026, it was 86%) and the `.dots`
under it are 32px buttons around an 8px dot (`--line`, lit `--accent`,
`aria-current`), one per card, made by the script (no script, no dots; it
skips a card with no box, `display: none`, and makes none for fewer than
two), that follow the scroll (IntersectionObserver) and bring their card in
on tap.
A row opens on its `.featured` card, centred at once (the tiers: PRO, START
a swipe to the left, ELITE to the right), else on its first; the script does
it only where the row scrolls, so the desktop grid is untouched. The
announcements' `.evs` is a `.swipe-row` too, at every width and one card per
view (**Aktualno**, below).
**The gym** (`#dvorana`, below): the same `.offer` cards in `.gym-grid` (two
columns ≥900px, capped at 760px so each is about a tier's width; the swipe
row, two dots, below), not featured; Individualno's other
prices are a muted `.price-note` under its `.price` (each price in it one
inline `.whole` block, so no break falls inside it), and the Dvorana card
holds its room with an invisible copy of it (`.price-note.room`,
`aria-hidden`): the line is the owner's text, any length, and both prices
stay level, two lines at least. Both gym cards
are tiers too (the plan's real monthly price, an editable yearly one) with
their own `.period` under `.gym-grid`, and the two switches are one choice:
pressing either sets every `.price[data-period]` on the page and
`aria-selected` on both. Buttons: accent `.btn-sm` on the featured card,
neutral `.cta` beside it, green `.owned` for a plan the visitor has. A
plan's own price is its Stripe Price once it has one (`offer_prices`, the
plans in `stripe_priced`), else its reference price, the
`price.<plan>.amount` / `.unit` copy slots printed with `c.t()` and edited in
place (the add-on's amount: `addon.<where>`). Prices are public unless
`PUBLIC_PRICES=off` (which also hides both switches), and no public page links
to `/moja-clanarina` (nor to the old `/cjenik`). **Aktualno** (`#aktualno`, in the hero since 16.10.2026,
between the h1 and the photo: the first thing on the page): the owner's two
announcements for the month as `.event` cards in `.evs` (text left-aligned
in the centred hero): the `.card` surface at `--r-lg` (a shallow card, not
the stage's `--r-xl`), one flex row that WRAPS, its items centred on their
line and its lines at the top (`align-content: flex-start`: a card the row
stretches to its neighbour's height keeps its lines at the top): a `.tag`
chip (accent tint + `--accent-tint-ink`; scoped `.event .tag`, not the
photo's glass `.tag`), a `.head` holding the italic
uppercase title of `.offer` at 1.15rem (an `h2`: it sits straight under the
page's `h1`) over a `.when` line behind a 7px accent dot (on the baseline,
so a wrapped line keeps it on its first), a muted `.text` that takes the
free room (`flex: 1 1 280px`), and one grey `.act` to `/#kontakt` in a
`.foot` at the right end (the red button stays on the featured tier). A long
text makes a card taller, never wider: no piece is wider than the card, and
a long one wraps onto a line of its own. From 700px a plain card is the
one-line strip (chip, title over when, the text taking the room, the link
at the right end), wrapping only when a text is long; below 700px a column.
**One card per view at every width** (the
owner's call, 17.10.2026, as Shape's "Novo" cards; side by side on a desktop
before): `.evs` is a snap scroller (a `.swipe-row`, `scroll-snap-type: x
mandatory`, scrollbar hidden) whose `.event` is `flex: 0 0 100%` of its
content box, and that box is the hero's column: the screen less the gutter
on a phone, the photo's 1100px on a desktop, so the card is exactly as wide
as the photo under it. The hero's side gutter is `.hero-inner`'s padding at
every width; the row's negative margins reach into it, never past it (that
would be overflow), and its own padding gives it back: on a phone the row
runs to the screen's edges, and the card's shadow is not cut (12px over,
20px under, the gutter at the sides). Its gap is the gutter, never less, so
none of the next card shows. Its `.dots` show at every width (`.evs +
.dots`; the tiers' and the gym's stay phone-only). One card shown
(`.single`) has no dots and does not move: the script makes neither for
fewer than two. **Edit mode stacks the two** (`body.editing .evs`: a
one-column grid, not a scroller, its dots hidden), so the editor reaches a
card that is off, which has no dot. It **moves on by itself**
(`data-auto="5000"`, the owner's 5 s): the next card glides in as its dot
would bring it, after the last the first, and
the lit dot follows. Quiet whenever a person is on the row or its dots (a
finger, a mouse where the device can hover, the focus), with the whole delay
again once they leave; no tick while the tab is hidden or the row is off the
screen; never under `prefers-reduced-motion`; only where the row scrolls,
which the announcements' row does at every width (in edit mode its glide
moves nothing: the grid does not scroll).
Each card is switched off with its `.ed-flag`, its first item in edit mode;
a visitor never gets a hidden one, nor the box when both are.
**A card over a photo** (`.has-img`: the owner's upload, a `copy.ImageSlot`;
Shape's photo cards, 16.10.2026): the photo (`img.bg`, its first child, from
`/slika`) fills the card under the stage's kind of gradient (`rgba(0,0,0,.25)`
at the top, `.05` at 35%, `.82` at the bottom) on the stage's `#141416`
ground, no hairline, light-on-dark in both themes; a column at every width:
the glass chip (`.tag`'s own, not the accent tint) at the top, then, pushed
down by the head's `margin-top: auto`, the white title and `.when` (its dot
stays `--accent`), the text at `rgba(255,255,255,.85)` (48ch at most, never
clamped: a long text makes the card taller) and Shape's white pill (`.act` in
`#fff` / `#111`, a light grey on hover) at the bottom. At least 300px tall on
a phone, 320px from 900px (a wide banner across the column). `data-photo`
makes the audit count its text instead of scoring it. The plain card in the
same row is stretched to its height, its lines at the top: the row keeps one
height, so its dots stay put as the cards change. In edit mode the pills
(`.ed-flag`, `.ed-img`, `.ed-img-x`) stack at the top of a photo card. Info band
`.info-grid`: radno vrijeme table, `.crow` contact rows
(14px stroke icon + text, address is the Maps link), `.socials` icon row (20px
glyphs, muted → accent on hover, 32px targets).

**Moja članarina (`moja_clanarina.html`, 18.10.2026).** Shape Club's billing
page in QMT's look; `/cjenik` leads here. Three `.mc-sec` sections under the
page header, each a bare `h2` (1.05rem). **Tvoji planovi**: one `.plan-card`
per plan held (`section.card`, `--r-xl`, padding 18px / 22px 24px from 700px,
one column, two from 1000px), active first. Its state is a tinted border
(`.is-active` green, `.is-lapsed` the accent, 45% into `--line`, never an inset
bar) AND words: `.pc-head` is a wrapping row of `.pc-name` (the `.pc-kicker`
caption "Paket": `.sec-kicker`'s 700 .74rem / .16em uppercase, in `--muted`
here, over the italic uppercase `h3`) and the `.chip` (above). **The facts**
(`dl.facts`): label over value, a 2-column grid on phones, 3 from 700px; `dt`
700 .7rem uppercase `--muted`, `dd` 600 tabular-nums; Cijena (the
`_plan_price.html` macro), Uplaćeno, Sljedeća uplata, Vrijedi do, and for a
tiered plan Paket "12 treninga mjesečno" and, while it runs, Iskorišteno
"5 od 12 u ovom ciklusu". **The status box** (`.pc-status`): `--surface-2`,
`--r-md`, 12px 14px, .9rem, one plain sentence (cash: "Članarina vrijedi do …
Sljedeću uplatu obavi do … — u dvorani, gotovinom ili karticom."; card: "Pretplata
se obnavlja automatski … karticom."; cancelled, lapsed); a date ends in its own
full stop. Then `.foot` (pinned to the bottom, wrapping pills), rendered only
when it holds something: the plan's door `.btn.btn-sm` while it runs, a card
subscriber's portal `.act` and the tier switch (`.switch`: a hairline, the
`.pc-kicker` "Promijeni paket", the other tiers as `.act` forms with
`data-confirm`), a cash member's "Prebaci na karticu" `.switch` form once Stripe
is configured. **Dodaj plan**: `.plan` cards (`--r-xl`, padding 18px 20px 20px,
italic uppercase `.plan-h`) in `.plan-grid` (1 column, 2 from 700px, 3 from
1000px): the name, the `cjenik.<plan>` text (`.plan-desc`, `min-height: 3.9em`
from 700px so the prices of a row sit level), the price (800 1.25rem, `<small>`
unit, the muted `.price-hint`), the `.foot` pinned bottom. Grupni is
`.featured` (accent-tinted border, `.featured-tag` top-right): on a phone its
name keeps 128px clear beside the chip; from 700px, where the name would wrap
and drop its price below the row's, the card stands 26px taller than its row
(the landing's "taller, not shifted"), the chip in that room above the name,
and the grid starts 38px under the heading so the card keeps 12px. Price source order (the macro): the subscribed tier's own
("70 € / mjesečno · 12 treninga") → Stripe Price → the reference price in
the shop's own unit, the `price.<plan>.*` copy slots (defaults
`REFERENCE_PRICES`) printed with `c.t()`, so the gym owner retypes them here
(an editor also gets an empty note's slot to fill). Every card carries
`id="plan-<key>"` (`scroll-margin-top: 90px`), so `#plan-<key>` links land on
it in either section. **Računi**: a `.card.ledger` (max 640px) around an
`.mtable`: date, the plan with the method as a muted second line (`.way`; four
columns did not fit 360px once amounts show), the amount when any is known;
`th` in the `dt` look; tighter below 420px; the wrapper scrolls only as a last
resort. No membership at all: `.card.mc-none` with the calendar's sentence
instead of Tvoji planovi.

**Profil (`profil.html`).** The basic-info form, then for a client one
`.card.mc-link` holding an `.act` to `/moja-clanarina` ("Moja članarina —
planovi, uplate i računi →", allowed to wrap: it nearly fills a 360px card).

**Karton (`karton.html`).** Upitnik block `.upitnik.lvl-*` tinted by razina
(`--lvl`/`--lvl-soft` per theme), diary `.log-entry` rows in four states
(written / `.is-absent` / cancelled / open — `.fresh` gets the accent inset bar),
`.le-actions` right-aligned pills, `.le-edit` inline form toggled by
`qmtToggleForm`. Rail `.termini` holds only Nadolazeći. `.upitnik` and `.termini`
are `--r-xl`; `.log-entry` rows are `--r-md` and keep the accent inset bar for
`.fresh` — at 12px the bar still reads as a bar.

**Calendar (`calendar.html`).** Seven `.day-col` on desktop → on phones one day
at a time (17.10.2026): the `.day-strip` picks it, the grid gets `.one-day` and
the chosen column `.is-on` (its `.day-head` hidden, the strip says the day), and
each termin shows as a `.sess-row` that opens `#sheet`. `?day=` carries the day
through reloads, forms (`input[name=day]`, `data-shown-day` where the script
keeps it current) and redirects. Without the script the phone shows every
column as an agenda of cards, empty days saying "Nema termina". "Moje
rezervacije" uses the row style there too (the day as a kicker line, the ✕ at
the row's right end). "Moja članarina" is `ul.mlines`, one line per plan
("Grupni trening · aktivna do 1.11.2026. · 5/12" for a tiered plan, or
"istekla …" in `--danger`), then an `.act` "Moja članarina →" to
`/moja-clanarina` (18.10.2026; a four-column `.mtable` before, which moved to
that page's ledger). `.sess.mine` = accent tint + inset bar,
`.past`/`.canceled` at .45 opacity, `.today .day-head` red. A client's
phone also has a month view (18.10.2026): `.view-switch` "Tjedan | Mjesec"
opens `?view=month`, a page of its own (no grid, strip or sheet; the week's
head keeps only its h1): the next-termin card, the switch, `.month-nav`, the
`.month` grid of `.mday` links, its legend and "Članarina vrijedi do …", then
"Moja članarina" and "Moje rezervacije" as on the week page.

## Scripts

- `scripts/audit.py [base_url]` — the measured audit (see SKILL.md). Exit 1 on overflow.
- `scripts/extract_tokens.py` — regenerate `references/tokens.md` from `base.html`.
