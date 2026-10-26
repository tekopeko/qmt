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
| `.avatar` / `.user-menu` | base | initials circle → account menu on the YouTube pattern: identity header (the email ellipsized on a desktop with the whole address in its `title`, wrapped ≤900px), icon gutter rows (Profil, Moja članarina for a trainer only — the Članarina tab's exact opposite —, theme, Odjava), full-bleed hover |
| `main` | base | max-width 1100px, `clamp(14px,4vw,40px)` side padding; `main.full` for the landing |
| `main > h1`, `main > h1 + .hint` | base | the page header: title `clamp(1.6rem,3vw,2rem)` + one lead sentence, 70ch max — templates write bare `<h1>` / `<p class="hint">` with no inline style |
| `.card` | base | `--surface`, hairline, `--r-lg` (20px), `--shadow`; hero-grade cards (`.svc`, `.plan`, `.upitnik`, `.termini`) take `--r-xl` (28px) with 26px padding |
| `.crumbs` | base | breadcrumb: muted links, `/` separators, `.here` current |
| `.ed` / `.copy-toggle` / `.copy-bar` | base (trainer, owner) | in-place copy editor: `_copy.html` prints every slot in a `span.t` (`white-space: pre-line`, so the owner's line breaks show) and makes it an `.ed` for an editor; the fixed "✎ Uredi tekstove" pill toggles `body.editing` (dashed outlines, click to edit, `.ed-on` while open; an empty `.ed` keeps a 2.5em box so it can be clicked); Enter is a new line, ⌘/Ctrl+Enter saves; the bar under the pill (as wide as its content, at most the window less 20px) shows label, an "n znakova" counter, the `.cb-hint` "Enter = novi red · ⌘/Ctrl+Enter = spremi" (600px and up) and Spremi / Zadano / Odustani. An emptied text stays empty (20.10.2026): the bar says "Prazno: Spremi ostavlja prazno." (from 600px "… · Zadano vraća izvorni tekst." after it, `.cb-more`), and for a number (`data-required`: `price.<plan>.amount`, `addon.*`) "Prazno: Spremi vraća izvorni tekst."; the empty `.ed` keeps its box in edit mode, and the shape around it (a pill, a chip, a link) goes outside it. Visitors get a bare `span.t`, no editor markup, and nothing for an empty text |
| `ul[data-list]` / `.ed-x` / `.ed-add` | base (trainer, owner) | an editable list (`c.points`): each item an `.ed` with `data-index`, a 32px round `.ed-x` ✕ beside it (negative margin, so the line height holds) and an `.act.ed-add` "+ Dodaj stavku" after the list, hidden at the count limit; both only under `body.editing`. The bar names the item ("…: stavka 2") and its Zadano reads "Zadano (cijela lista)" |
| `ul.lines` | landing (everyone; trainer, owner edit) | the extra lines (`c.lines` / `c.field_lines`, 20.10.2026: the owner's "text cells"): the list above printed as plain lines, no dot and no gutter (`li::before` none), the body text at .95rem / 1.5, 6px apart, in `--text`; 14px under a card's bullets; in the hero the old lead's look (`--muted`, 1.05rem, 60ch at most, centred, 16px under the h1; the announcements keep their own distance under it); in the contact block `--muted`. Its `.ed-add` reads "+ Dodaj tekst" and sits on a line of its own (centred in the hero); the ✕ and the bar as the bullets' ("Online 2: dodatni tekst 1"; the ✕ stays inside the contact block's column and sits beside its text in the hero). A visitor gets no `<ul>` for an empty list; the editor's empty one is not displayed (`ul.lines:not(:has(> li))`), so outside edit mode his page is the visitor's |
| `table[data-rows]` / `td.ed-xc` | base (trainer, owner) | an editable table of rows (`c.rows`, a `copy.RowsSlot`: the landing's opening hours, 20.10.2026): each cell an `.ed` with `data-index` (the row) and `data-part` (0, 1), an emptied cell an empty `.ed` that keeps its click box; each row's ✕ is the list's `.ed-x` in a cell of its own, `td.ed-xc`, a column only under `body.editing` (outside it the editor's table is a visitor's), whose padding holds the ✕'s negative margin; "+ Dodaj red" is the list's `.act.ed-add` after the table, hidden at 12 rows. The bar names the cell ("Radno vrijeme, red 2: sati") and its Zadano reads "Zadano (cijela tablica)"; emptied, it says "Prazno: Spremi ostavlja polje prazno." (or "… uklanja red." when the other cell is empty too) |
| `.ed-flag` / `.is-off` | base (trainer, owner) | the edit-mode toggle of a `copy.FlagSlot` (an on/off switch, the landing's announcements): the first child of the box it switches (`data-flag`), a 32px pill, green `--good-fill` "● Prikazano" / grey `--surface-2` "○ Skriveno", saved at a click, no confirm (hiding loses no text). A switched-off box is `.is-off`: hidden, shown only in edit mode with its content dimmed to .55 and the toggle at full strength; its `data-flag-group` follows its boxes (`.is-off` when none is on, `.single` on their row when one is). A visitor gets neither the toggle nor a hidden box |
| `.ed-img` / `.ed-img-x` / `#edImgFile` | base (trainer, owner) | the edit-mode pills of a `copy.ImageSlot`, a photo behind a box (the landing's announcements; the box carries `data-image`): `.ed-img` "Dodaj sliku" / "Promijeni sliku" opens the hidden file picker (`#edImgFile`: jpg, png, webp) and posts to `/copy/<key>/slika`; the answer's URL becomes the box's first child, `img.bg`, and the box turns `.has-img` + `data-photo`. `.ed-img-x` "Ukloni sliku" (only with a photo) asks first, as an item's ✕ ("Ukloni?" for 4 s, then `reset=1`). 32px pills like `.ed-flag` (`--surface-2` / `--muted`), after it; on a photo (`[data-photo]`) a solid `--surface` pill with `--text` ink: the editor's controls, not text on a photograph. A failure is said in the bar |
| `form.ed-ann-x` | base (trainer, owner) | "Obriši najavu", the edit-mode pill that deletes a landing announcement (`POST /aktualno/<id>/obrisi`, a plain form): the `.ed-img-x` pill to the pixel (32px, `--surface-2` / `--muted`, solid `--surface` on a photo), after the photo's pills; the form is `display: contents` in edit mode, so its button lines up with them as a flex item of the card. It asks first, as an item's ✕: one tap arms it into "Obriši?" (the accent tint, `aria-label` "Potvrdi brisanje") for 4 s, any other tap disarms it, the second tap sends the form; the page comes back without the card. On a card that is off it is dimmed with the card's content (a rule of its own: the form has no box to carry the opacity). Hidden outside edit mode; a visitor never gets it. The gym's "Obriši karticu" (`form.ed-gym-x`, `POST /dvorana/<id>/obrisi`, 20.10.2026) is the same pill and the same two taps |
| `form.ed-add-ann` | landing (trainer, owner) | "+ Dodaj najavu": an `.act` pill (32px tall at every pointer) after the announcements' dots, centred in the hero under the stacked cards, in edit mode only; a plain form (`POST /aktualno/nova`) that comes back with a new card last (placeholder texts, shown, no photo). Not rendered at the cap (8 cards); with none left it is all the editor's empty box holds. A visitor never gets it. The gym's "+ Dodaj karticu" (`form.ed-add-gym`, `POST /dvorana/nova`) is the same pill under its row of cards, 18px under them |
| `.featured-tag` | base | "Najpopularnije" chip in the top-right corner of a `position: relative` card: accent tint + `--accent-tint-ink`. Used by `/moja-clanarina`'s "Dodaj plan" and the landing's offer |
| `.period` | base (`_period.html`) | Mjesečno / Godišnje (promoted from the landing 21.10.2026, when `/moja-clanarina` needed it): a switch per group of cards that carry a monthly and a yearly price, `.price[data-period]` month / year — the landing's two sections, `/moja-clanarina`'s two "Dodaj plan" groups. The `.auth-tabs` idiom on a `--surface` track with a hairline (the tint over `--surface-2` is 4.34:1 in dark): 36px pills in muted 600 .85rem, the chosen one `--accent-dim` with `--accent-tint-ink`. `period_switch(start)` renders it `hidden`, its `start` tab `aria-selected`, while the page renders its group's cards with the other line `hidden`; base.html's script shows it and, at a press, sets the lines inside its closest `[data-period-group]` and its own `aria-selected`, never another group's. Per page view, nothing remembered; without JS no switch, the opening price. Where it sits is the page's: centred under each row on the landing (34px, 10px below 900px), under each group's heading on `/moja-clanarina` |
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
| `.u-fact` (karton, upitnik v2) | a fact from the upitnik's part 1 (the goal, "3 dana tjedno", "45-60 min", the place): a neutral pill, `--surface-2` with `--text`, 600 .78rem — facts, not state, so no razina colour |
| `.u-flag` (karton, the trainer's view) | the upitnik's safety flags, 999px pills, 700 .78rem: `.review` "Zahtijeva pregled" (q15 Da) in `--accent-dim` / `--accent-tint-ink`; `.pain` "Bolovi N/10 · where" (q14 ≥ 4) in the karton's amber (`--warn` on `--warn-soft`, the `.act-absent` values, AA on both themes) |
| `.u-note` (karton) | the pain sentence for a client at q14 ≥ 7 (`upitnik.pain_note`), shown to him and the trainer: `--text` on the amber tint, `--r-md`, 10px 14px |

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
(`c.points`, up to six), then a `.foot` pinned to the bottom
(`margin-top: auto`; its 26px `padding-top` is the gap under the bullets,
or the extra lines, of the row's tallest card) holding the `.price`
(2.1rem number + muted unit) and one button, so price and button sit level
across the row. No add-on line over them since 21.10.2026 (the owner:
"lets leave out the moji makrosi out of here completely"): the tiers'
`.addon` line, its words (`slot.addon`, `slot.addon_unit`) and its switch
(`slot.addon_on`) went, as the gym cards' line had on 20.10.2026; the
add-on's amounts are the prehrana hint on `/moja-clanarina`. Each tier has
two `.price` blocks,
`data-period="month"` (`hidden`) and `"year"`: the yearly shows first, and the
tiers' switch renders Godišnje selected (20.10.2026); the `.period` switch
(base, above) under the cards shows one on all three, per page view, and is
hidden until the script runs. Each `.period` is its own section's choice
(`period_switch(start)`, `offer(…, start=)`; each section a
`[data-period-group]`): the script sets the `.price[data-period]` inside its
own section and its own `aria-selected`, never the other switch's. A gym
card a plan prices shows that plan's yearly slots (`price.<plan>.year_amount`
/ `.year_unit`, 21.10.2026), one without plans its row's. Tier prices are mostly owner-typed text, so the
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
**The gym** (`#dvorana`, below): the same `.offer` cards (no add-on line
since 20.10.2026), rows of the `gym_cards` table since 20.10.2026 (`offer(…, card=, n=)` prints
one: its texts under virtual keys `dvorana.<id>.<field>`, `c.field` and
`c.field_points`), not featured. `.gym-grid` has as many columns as the
cards a visitor sees, up to three (`--cols`, set by the template; in edit
mode `--cols-edit`, every card, a hidden one too), each column 380px at
most: two cards the 760px they always were, three the tiers' 1100px row,
one a tier's width, centred; a fourth and on wrap into a second row of the
grid. Below 900px the swipe row, a dot per card; edit mode stacks it there
(one card under the other, no dots), as it does `.evs`. A card with plans
is priced by its first plan's slots and names its other plans' prices in a
muted `.price-note` under its `.price` (Individualno's; each price in it one
inline `.whole` block, so no break falls inside it); every card without
such a line holds the room of the row's longest with an invisible copy
(`.price-note.room`, `aria-hidden`): the line is the owner's text, any
length, and the prices stay level, two lines at least; no line on any card,
no room. A card without plans (every one the gym owner adds) prints its own
monthly price and "Javi nam se →" (`.cta`, to `#kontakt`) for everyone. In
edit mode a card's first line is `.ed-pills`: its `.ed-flag` and
`form.ed-gym-x` "Obriši karticu" side by side; a card that is off is
`.is-off` (hidden outside edit mode, dimmed but for its switch in it), and
the section is `.is-off` when none is on (a visitor gets no section then);
`form.ed-add-gym` "+ Dodaj karticu" under the row. The gym's cards are tiers
too (a monthly and an editable yearly price) with their own `.period` under
`.gym-grid`, its own choice since 20.10.2026 (unlinked from the tiers'): it
opens on Mjesečno, the monthly `.price` shown and the yearly `hidden`, and a
press sets the gym's cards only (no gym switch when its section is not on
the page). A card's `.price-note` says each extra plan's
`price.<plan>.word` slot before its price (free text), the number its
amount slot. Buttons: accent `.btn-sm` on the featured card,
neutral `.cta` beside it, green `.owned` for a plan the visitor has. A
plan's own price is the owner's text, always (18.10.2026: no Stripe Price
prints instead), the `price.<plan>.amount` / `.unit` copy slots printed with
`c.t()` and edited in place. Prices are public unless
`PUBLIC_PRICES=off` (which also hides both switches), and no public page links
to `/moja-clanarina` (nor to the old `/cjenik`). **Aktualno** (`#aktualno`, in the hero since 16.10.2026,
between the h1 and the photo: the first thing on the page): the owner's
announcements for the month (rows of the `announcements` table since
18.10.2026, in creation order, up to eight, added and deleted in edit mode:
`form.ed-add-ann`, `form.ed-ann-x`) as `.event` cards in `.evs` (text left-aligned
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
fewer than two. **Edit mode stacks them** (`body.editing .evs`: a
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
a visitor never gets a hidden one, nor the box when none is on.
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
(`.ed-flag`, `.ed-img`, `.ed-img-x`, `.ed-ann-x`) stack at the top of a photo card. Info band
`.info-grid`: the radno vrijeme table (`c.rows`, rows since 20.10.2026:
`td.d` the days in `--text` 600, the hours `--muted`, 3px / 14px of padding;
an emptied cell an empty `td`; for an editor `table[data-rows]`, above),
`.crow` contact rows
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
is configured. **Dodaj plan** (two groups since 21.10.2026, the owner:
"every tab is one big text cell except the number"): each a
`section.mc-group` (a `[data-period-group]`, 30px apart) whose
`.mc-group-head` stacks its heading, an `h3.pc-kicker` (the "Paket"
caption's look: `clanarina.h.online` "Online treninzi", `clanarina.h.gym`
"Treninzi u dvorani"), 10px over its own `.period` (base; left-aligned
here: on a phone the cards are a column, and a switch under them would be
a long scroll away), 14px above its `.plan-grid` (1 column, 2 from 700px, 3
from 1000px). The online plan's three QMove tiers first, opening on
Godišnje (none while online is held), then the gym's plans in
`PLAN_TYPES` order, opening on Mjesečno; a group with no card left is not
printed. A `.plan` card (`--r-xl`, padding 18px 20px 20px, gap 8px) is, in
order: the italic uppercase name (`h4.plan-h`: a tier's landing title slot,
a plan's `plan.<plan>.name`), its two price lines (`pp.price(amount, unit,
period, hidden)`: 800 1.25rem, `<small>` unit; the group's other line
`hidden`), prehrana's muted `.price-hint` under both (the two `addon.*`
amounts), ONE text (`p.plan-desc`, muted .9rem, its line breaks shown; a
member gets no paragraph for an emptied one) and, where Stripe sells the
plan, the `.foot` pinned to the bottom with "Pretplati se karticom"
(grupni's tier picker in its form; a tier's form names its tier). The
price sits right under the name, not pinned: a row's prices are level
while its names take the same lines (the browser walk measures it with
names of one length). Grupni is
`.featured` (accent-tinted border, `.featured-tag` top-right): on a phone its
name keeps 128px clear beside the chip; from 700px, where the name would wrap
and drop its price below the row's, the card stands 26px taller than its row
(the landing's "taller, not shifted"), the chip in that room above the name,
and the grid starts 38px under its group's heading so the card keeps 12px.
Every price is the owner's text for every plan and every member, a card
subscriber's too (his tier is the Paket fact): the landing's own slots, so
one number is one slot on both pages, printed with `c.t()` so the gym
owner retypes them here — a plan's `price.<plan>.amount` / `.unit` /
`.year_amount` / `.year_unit` (defaults `REFERENCE_PRICES` /
`YEARLY_PRICE`, " €" after a number without a sign of its own), a tier's
START `price.online.*`, `offer.online2/3.price` / `.unit` and
`offer.online*.year_price` / `.year_unit` (as typed, as the landing prints
them). A held plan's Cijena is `pp.plan_price(key)`, its monthly line and
prehrana's hint; no note under a price since 21.10.2026. Stripe's amounts
show only inside the forms that charge them, the
checkout tier picker (`_tiers.html`) and the tier switch (18.10.2026). Every card carries
`id="plan-<key>"` (`scroll-margin-top: 90px`), so `#plan-<key>` links land on
it in either section; QMove START is `#plan-online` (where the landing's
three tiers lead), PRO and ELITE `plan-online-pro` / `-elite`. **Računi**: a `.card.ledger` (max 640px) around an
`.mtable`: date, the plan with the method as a muted second line (`.way`; four
columns did not fit 360px once amounts show), the amount when any is known;
`th` in the `dt` look; tighter below 420px; the wrapper scrolls only as a last
resort. No membership at all: `.card.mc-none` (its two sentences the
`clanarina.none.*` slots) instead of Tvoji planovi. An editor holds no plans,
so he sees that card as a preview inside the Tvoji planovi section, under its
heading and a small muted caption, `.mc-preview` "Ovo vidi član bez
članarine:" (.82rem). The page's own words are copy slots (18.10.2026): the
headings (the two groups' since 21.10.2026), the plans' names (a held
card's `h3`, a "Dodaj plan" card's `h4`), each "Dodaj plan" card's one text
(`cjenik.<plan>.text`, `cjenik.online.<tier>.text`, 21.10.2026), the
no-plan card and the empty ledger's line;
`overflow-wrap: anywhere` is under each, so a long word breaks rather than
widen the page.

**Profil (`profil.html`).** The basic-info form, then for a client one
`.card.mc-link` holding an `.act` to `/moja-clanarina` ("Moja članarina —
planovi, uplate i računi →", allowed to wrap: it nearly fills a 360px card).

**Karton (`karton.html`).** Upitnik block `.upitnik.lvl-*` tinted by razina
(`--lvl`/`--lvl-soft` per theme), diary `.log-entry` rows in four states
(written / `.is-absent` / cancelled / open — `.fresh` gets the accent inset bar),
`.le-actions` right-aligned pills, `.le-edit` inline form toggled by
`qmtToggleForm`. Rail `.termini` holds only Nadolazeći. `.upitnik` and `.termini`
are `--r-xl`; `.log-entry` rows are `--r-md` and keep the accent inset bar for
`.fresh` — at 12px the bar still reads as a bar. A v2 response's block (26.10.2026)
puts `.u-fact` pills and the muted score ("6,4 / 10") on its `.u-meta` line, the
trainer's `.u-flag`s under it, and the `.u-note` under the ramp; under "Odgovori"
a follow-up's free text is `li.follow` (no bullet, indented, muted question).

**Upitnik (`upitnik.html`, 26.10.2026; patterns.md §7).** One `form.quiz` (640px,
centred) holds every step; the page sets `solo_page`, so the bar is the small pill
with the brand alone. `.q-title` (PT Sans 700 .95rem uppercase) and `.q-intro`
(muted; the first screen only) head it, the `?error=` alert under the title.
`.q-bar`: 4px, `--line` track, `--accent` fill, its width the step among the steps
asked (no numbers; `aria-hidden`; hidden without JS and in edit mode). Each
`section.q-step` is `.q-part` (the eyebrow: PT Sans 700 .72rem, muted) and `h1.q-h`
(the question, `clamp(1.45rem, 5vw, 2rem)`, PT Sans uppercase; `tabindex=-1`, the
script focuses it on a new step), then by kind: **`.opts`** rows (a choice, yes /
no): `label.opt` around a hidden radio for a client, the editor's own options list
(`c.field_points`, `li` rows) for him; flex rows, 64px min, `--surface`, hairline,
`--r-md`, 600 1rem; the letter badge is a CSS counter on `::before` (26px, 7px
radius, hairline, muted 700 .72rem; alt text "" so a reader hears the option, not
the letter), so the editor's redrawn rows get it too; chosen
(`:has(input:checked)`, the editor's preview `.on`) the row inverts (`--text`
ground, `--bg` ink) with a ✓ `::after` at its right end; focus is a 2px accent ring
on the row. **`.scale`** (q5–q14): ten `label.sc`, each a circle `span` (≤56px,
`aspect-ratio: 1`, hairline on `--surface`, 700 1rem tabular), chosen inverted like
a row; a 5 × 2 grid until its box (`.scale-box`, a query container) is 454px, ten in
a row from there (40px each at least); `.scale-ends` under it, muted .85rem, "1 = …"
left and "10 = …" right. **A free text** (q14b, q15b): a 128px textarea labelled by
the h1 (a `label` inside it). `.q-nav` closes a step: "Nazad" (`.act.act-quiet`, not
on the first) on the left, "Dalje" / "Spremi upitnik" (`.btn`) on the right; long
words wrap inside the pills. The last screen is `label.q-consent` (a row-like box,
22px checkbox, `accent-color`) and that nav. Without JS every step shows, stacked
with a hairline between them; in edit mode the same, the bar hidden and the pain
sentence previewed under q14 (`.q-preview`, `.q-note`).

**Calendar (`calendar.html`).** Seven `.day-col` on desktop → on phones one day
at a time (17.10.2026): the `.day-strip` picks it, the grid gets `.one-day` and
the chosen column `.is-on` (its `.day-head` hidden, the strip says the day), and
each termin shows as a `.sess-row` that opens `#sheet`. `?day=` carries the day
through reloads, forms (`input[name=day]`, `data-shown-day` where the script
keeps it current) and redirects. Without the script the phone shows every
column as an agenda of cards, empty days saying "Nema termina". "Moje
rezervacije" uses the row style there too (the day as a kicker line, the ✕ at
the row's right end). The plans are not listed here: the "Moja članarina"
block (`ul.mlines`, one line per plan and an `.act` to `/moja-clanarina`)
went on 18.10.2026, that page holds them. A client with no plan running gets
`.gate-line` under the termini instead: the `.hint` "Nemaš aktivnu članarinu
— bez nje rezervacija nije moguća." and a `.btn.btn-sm` "Pogledaj cjenik →"
in one wrapping flex row (the month note's idiom, 24px under the grid).
`.sess.mine` = accent tint + inset bar,
`.past`/`.canceled` at .45 opacity, `.today .day-head` red. A client's
phone also has a month view (18.10.2026): `.view-switch` "Tjedan | Mjesec"
opens `?view=month`, a page of its own (no grid, strip or sheet; the week's
head keeps only its h1): the next-termin card, the switch, `.month-nav`, the
`.month` grid of `.mday` links, its legend and "Članarina vrijedi do …", then
the gate line (a client with no plan running) and "Moje rezervacije" as on
the week page.

## Scripts

- `scripts/audit.py [base_url]` — the measured audit (see SKILL.md). Exit 1 on overflow.
- `scripts/extract_tokens.py` — regenerate `references/tokens.md` from `base.html`.
