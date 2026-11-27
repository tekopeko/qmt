# Component catalog

All classes live in `src/qmt/web/templates/base.html` unless a page is named.
Class → what it is → how it behaves. When a row needs a control, find it here
first; a new class is a last resort and needs a comment explaining the gap.

## Layout

| class | where | what |
|---|---|---|
| `.topbar` | base | a floating dark-glass pill (999px, blur, sticky 10px below the top, max 1100px) on every screen and both themes; ONE row at every width: brand left, tabs middle, avatar right, all inside the pill's padding. `.brand-slot` takes the room the tabs leave and is a query container: the wordmark shows in full when the slot is ≥19.2rem, else "QMT" (never a window breakpoint — the pill is capped, so the window says nothing about the room inside). 7+ tabs run tight (`.nav:has(> a:nth-of-type(7))`; no bar has seven links: a client six at most, staff six and Admin ▾ since 24.11.2026, Karton joining their row, which the rule does not count and which needs none of it: the owner's bar measured at 901, 960, 1024, 1100, 1200 and 1280px in both themes keeps every tab on its line inside the pill, the brand's slot 191px at 901px, the whole name from 1024px), all tabs tighten ≤1200px and fold into ☰ ≤900px. Tabs never wrap. The ☰ drawer: a client's is one plain list; staff's two sections under `.nav-cap` captions (PT Sans 700 .72rem uppercase, `#9a9aa0` on the bar's glass), "Kao član" and "Admin", a hairline (`.nav-admin`'s border-top) between them, Admin ▾'s items as rows like the tabs (no icons, the current one `.on`'s look) and the tab itself no row; it scrolls inside itself when taller than the window (the bar is sticky) |
| `.nav > a` / `.nav .navbtn` / `.nav a.cta` / `.nav a.dark` / `.on` | base | tab: a link right in `.nav` (`> a`: Admin ▾'s items are links further in, rows of its menu) or a `.navbtn` (Admin ▾, `.menu-btn`, its caret part of its label, `aria-hidden`); red pill (`.cta`); dark glass pill (`.dark`, the pill's own "black", theme-free because the bar is always dark); current page (`.on`; Admin ▾ while one of its pages is open, and the same look while its menu is open). A client: Početna · Raspored · Karton · Online treninzi (with an online plan) · Moja članarina · Prehrana; staff (trainer, owner): that row, Karton in it since 24.11.2026 (their own karton: `.on` at `/karton` alone, a client's `/karton/<id>` lighting Admin ▾ → Trenutne članarine, `/upitnik` Admin ▾ → Upitnik), then Admin ▾ (26.10.2026). Guest bar: Prijava `.cta` (plus Registriraj se at the same weight while signup is open) · "Kontakt" `.dark`; never a Cjenik tab, and no "Što nudimo" — the photo leads to the offer |
| `.topbar.compact` | base (guests) | Shape's small pill: `width: fit-content`, centred; the brand is content-sized (no slot query) and the wordmark shortens below 420px, where even the small pill cannot hold the name beside the ☰. Its drawer is a centred 300px card, not a sliver the pill's width |
| `.kao-bar` | base (staff acting as a member, 26.11.2026) | the strip over every page while a trainer or the owner is in a member's account (`kao` in the context; the one-task pages and the error page too): the first child of `body`, sticky at the very top, `--kao-h` tall (44px, 52px on a coarse pointer), `z-index` 45; the topbar's pill sits under it (`body[data-kao] .topbar`'s sticky top is `--kao-h` + 10px) and html's `scroll-padding-top` is `--kao-h`, so a jump to an anchor clears both (its own `scroll-margin` on top); a drawer under it scrolls in the window less the strip. The karton's amber: `--warn` text on `--warn-soft` laid over `--bg` (`linear-gradient(var(--warn-soft), var(--warn-soft)) var(--bg)`: solid, no page text shows through; 4.6:1 light, 8.5:1 dark), a 30% `--warn` hairline under it, Inter 500 .88rem. ONE line at every width, its content on the pill's column (`padding: 0 max(16px, (100% − 1100px) / 2)`): `.kao-as` "Gledaš kao: **name**" (700), cut with an ellipsis (its `title` the whole name and the email), then "Izađi" (`.kao-exit`, a form posting `/kao/izlaz`): a `--warn` pill with `--bg` ink (5.5:1 light, 11:1 dark), 700 .82rem, 32px, 44px on a coarse pointer, never pushed off a 360px screen; its hover a 18% `--text` mix, never the base red. `role="status"`. Staff's own chrome: fixed words, no slot. The page carries the member's id (`body[data-kao]`), whose script marks every form that posts (`?kao=`) and every fetch that is no GET (`X-QMT-Kao`): the server runs a write only for the identity it was drawn for |
| `.menu-wrap` / `.menu` | base | the topbar's dropdown, one component for two menus (26.10.2026): a `.menu-wrap` (`position: relative`) holds a button (`aria-controls`, `aria-haspopup`, `aria-expanded`) and its `.menu` panel, `role="menu"`, `--surface`, hairline, 12px radius, `--shadow`, hung `calc(100% + 9px)` under the button; rows (`role="menuitem"`) full-bleed, 10px 16px, 500 .92rem, a 22px line icon (`.mi`, 24px viewBox, stroke 1.7) on one gutter, hover / focus `--surface-2`; `.sep` a hairline. One script in base.html: a click on the button opens it and the next shuts it, one menu open at a time (the account menu also shuts the ☰ drawer), a click outside or Escape shuts it (Escape gives the focus back to the button when it was in the menu); an open panel is moved in to stay 12px inside the window. Tab reaches its rows; no arrow keys |
| `.avatar` / `.user-menu` | base | initials circle → the account menu (`.menu.user-menu`, 288px, right-aligned to the avatar) on the YouTube pattern: identity header (the email ellipsized on a desktop with the whole address in its `title`, wrapped ≤900px), icon gutter rows: Profil, theme, Odjava — for everyone since 26.10.2026 (the Moja članarina tab is everyone's way to that page) |
| `.admin-menu` | base (trainer, owner) | Admin ▾'s menu (`.menu.admin-menu`, as wide as its longest row, left-aligned to its tab): Gledaj kao član (eye; 26.11.2026, first) → `/kao` (its record, `/kao/zapisi`, lights it too), Termini (calendar icon) → `/admin`, Trenutne članarine (card) → `/clanarine`, Upitnik (clipboard) → `/upitnik` (in normal mode, as every page opens: the ✎ pill turns edit mode on), Vježbe (dumbbell) → `/treninzi/vjezbe` (30.10.2026: the library's pages are under /treninzi, yet they light Admin ▾ and this item, never the Online treninzi tab), and the owner's Korisnici (people) and Statistika (chart). The page that is open: `aria-current="page"`, an inset 3px `--accent` bar on the row's left edge and the label in 700. In the ☰ drawer it is static rows under the "Admin" caption |
| `main` | base | max-width 1100px, `clamp(14px,4vw,40px)` side padding; `main.full` for the landing |
| `main > h1`, `main > h1 + .hint` | base | the page header: title `clamp(1.6rem,3vw,2rem)` + one lead sentence, 70ch max — templates write bare `<h1>` / `<p class="hint">` with no inline style |
| `.card` | base | `--surface`, hairline, `--r-lg` (20px), `--shadow`; hero-grade cards (`.svc`, `.plan`, `.upitnik`; the karton's `.termini` until 25.11.2026) take `--r-xl` (28px) with 26px padding |
| `.crumbs` | base | breadcrumb: muted links, `/` separators, `.here` current |
| `.ed` / `.copy-toggle` / `.copy-bar` | base (trainer, owner) | in-place copy editor: `_copy.html` prints every slot in a `span.t` (`white-space: pre-line`, so the owner's line breaks show) and makes it an `.ed` for an editor; the fixed "✎ Uredi tekstove" pill toggles `body.editing` (dashed outlines, click to edit, `.ed-on` while open; an empty `.ed` keeps a 2.5em box so it can be clicked); Enter is a new line, ⌘/Ctrl+Enter saves; the bar under the pill (as wide as its content, at most the window less 20px) shows label, an "n znakova" counter, the `.cb-hint` "Enter = novi red · ⌘/Ctrl+Enter = spremi" (600px and up) and Spremi / Zadano / Odustani. An emptied text stays empty (20.10.2026): the bar says "Prazno: Spremi ostavlja prazno." (from 600px "… · Zadano vraća izvorni tekst." after it, `.cb-more`), and for a number (`data-required`: `price.<plan>.amount`, `addon.*`) "Prazno: Spremi vraća izvorni tekst."; the empty `.ed` keeps its box in edit mode, and the shape around it (a pill, a chip, a link) goes outside it. Visitors get a bare `span.t`, no editor markup, and nothing for an empty text |
| `ul[data-list]` / `.ed-x` / `.ed-add` | base (trainer, owner) | an editable list (`c.points`): each item an `.ed` with `data-index`, a 32px round `.ed-x` ✕ beside it (negative margin, so the line height holds) and an `.act.ed-add` "+ Dodaj stavku" after the list, hidden at the count limit; both only under `body.editing`. The bar names the item ("…: stavka 2") and its Zadano reads "Zadano (cijela lista)" |
| `ul.lines` | landing (everyone; trainer, owner edit) | the extra lines (`c.lines` / `c.field_lines`, 20.10.2026: the owner's "text cells"): the list above printed as plain lines, no dot and no gutter (`li::before` none), the body text at .95rem / 1.5, 6px apart, in `--text`; 14px under a card's bullets; in the hero the old lead's look (`--muted`, 1.05rem, 60ch at most, centred, 16px under the h1; the announcements keep their own distance under it); in the contact block `--muted`. Its `.ed-add` reads "+ Dodaj tekst" and sits on a line of its own (centred in the hero); the ✕ and the bar as the bullets' ("Online 2: dodatni tekst 1"; the ✕ stays inside the contact block's column and sits beside its text in the hero). A visitor gets no `<ul>` for an empty list; the editor's empty one is not displayed (`ul.lines:not(:has(> li))`), so outside edit mode his page is the visitor's |
| `table[data-rows]` / `td.ed-xc` | base (trainer, owner) | an editable table of rows (`c.rows`, a `copy.RowsSlot`: the landing's opening hours, 20.10.2026): each cell an `.ed` with `data-index` (the row) and `data-part` (0, 1), an emptied cell an empty `.ed` that keeps its click box; each row's ✕ is the list's `.ed-x` in a cell of its own, `td.ed-xc`, a column only under `body.editing` (outside it the editor's table is a visitor's), whose padding holds the ✕'s negative margin; "+ Dodaj red" is the list's `.act.ed-add` after the table, hidden at 12 rows. The bar names the cell ("Radno vrijeme, red 2: sati") and its Zadano reads "Zadano (cijela tablica)"; emptied, it says "Prazno: Spremi ostavlja polje prazno." (or "… uklanja red." when the other cell is empty too) |
| `.ed-flag` / `.is-off` | base (trainer, owner) | the edit-mode toggle of a `copy.FlagSlot` (an on/off switch, the landing's announcements): the first child of the box it switches (`data-flag`), a 32px pill, green `--good-fill` "● Prikazano" / grey `--surface-2` "○ Skriveno", saved at a click, no confirm (hiding loses no text). A switched-off box is `.is-off`: hidden, shown only in edit mode with its content dimmed to .55 and the toggle at full strength; its `data-flag-group` follows its boxes (`.is-off` when none is on, `.single` on their row when one is). A visitor gets neither the toggle nor a hidden box |
| `.ed-img` / `.ed-img-x` / `#edImgFile` | base (trainer, owner) | the edit-mode pills of a `copy.ImageSlot`, a photo behind a box (the landing's announcements; the box carries `data-image`): `.ed-img` "Dodaj sliku" / "Promijeni sliku" opens the hidden file picker (`#edImgFile`: jpg, png, webp) and posts to `/copy/<key>/slika`; the answer's URL becomes the box's first child, `img.bg`, and the box turns `.has-img` + `data-photo`. `.ed-img-x` "Ukloni sliku" (only with a photo) asks first, as an item's ✕ ("Ukloni?" for 4 s, then `reset=1`). 32px pills like `.ed-flag` (`--surface-2` / `--muted`), after it; on a photo (`[data-photo]`) a solid `--surface` pill with `--text` ink: the editor's controls, not text on a photograph. A failure is said in the bar |
| `form.ed-ann-x` | base (trainer, owner) | "Obriši najavu", the edit-mode pill that deletes a landing announcement (`POST /aktualno/<id>/obrisi`, a plain form): the `.ed-img-x` pill to the pixel (32px, `--surface-2` / `--muted`, solid `--surface` on a photo), after the photo's pills; the form is `display: contents` in edit mode, so its button lines up with them as a flex item of the card. It asks first, as an item's ✕: one tap arms it into "Obriši?" (the accent tint, `aria-label` "Potvrdi brisanje") for 4 s, any other tap disarms it, the second tap sends the form; the page comes back without the card. On a card that is off it is dimmed with the card's content (a rule of its own: the form has no box to carry the opacity). Hidden outside edit mode; a visitor never gets it. The gym's "Obriši karticu" (`form.ed-gym-x`, `POST /dvorana/<id>/obrisi`, 20.10.2026) is the same pill and the same two taps |
| `form.ed-ann-mv` | landing (trainer, owner) | ↑ / ↓ on a landing announcement (29.10.2026, the owner's request: the gym owner puts the cards in his order): a plain form per card (`POST /aktualno/<id>/pomak`, `smjer` gore / dolje) after the photo's pills, before "Obriši najavu"; its two buttons are `.ed-mv`, /upitnik's arrows (the rule is base.html's since that day: a 32px round pill, `--surface-2` / `--muted`, a hairline, no glow; disabled at .45 where there is no place to go, the first card's ↑ and the last one's ↓), side by side 8px apart. The form is their box (`display: flex` in edit mode), not `display: contents` as `form.ed-ann-x`'s: in a column (a phone's card below 700px, a photo card at every width) the pair keeps one line, and as the card's own child it is lifted over a photo's gradient and dimmed with the content of a card that is off. One tap, nothing asks first (a move loses nothing); the order is every card's, a hidden one's too; the page comes back at the card (`#najava-<id>`, the editor's article, clear of the floating pill: `.event`'s `scroll-margin-top: 96px`) in edit mode (the one-shot flag). Hidden outside edit mode; a visitor never gets it, nor the article's id |
| `.q-ed` / `.ed-mv` / `label.ed-set` / `span.ed-if` / `button.ed-q-x` / `.q-ed-line` / `.q-ed-if` / `.is-muted` | upitnik (trainer, owner) | an upitnik question's controls in edit mode (26.10.2026), its first line, a wrapping flex row of 32px pills, 8px apart: its switch (an `.ed-flag` that posts to `/upitnik/pitanje/<id>` with `data-url` / `data-field` and brings the page back, `data-reload`), ↑ / ↓ (`.ed-mv`, `--surface-2` / `--muted` like the switch's off state, a disabled one at .45 on the first and the last question; base.html's since 29.10.2026, shared with the landing's `form.ed-ann-mv`), "Obriši pitanje" (`button.ed-q-x`: `form.ed-gym-x`'s pill and two taps, the button itself carrying the class since it names its form with `form="…"`), then a select per setting in a pill (`label.ed-set`: its word, Dio / Vrsta / Bodovanje / Uloga, in `--muted` 700 .8rem, the select borderless in `--text` 600 and 32px tall at every pointer, the tap target: the pill's hairline is an inset shadow, so the pill is the select's height, the row's one footprint; it turns `--accent` while the select has focus), saved at a change. Bodovanje only on a scale; Uloga only on a scale or a yes / no, offering the role its kind can hold. **Pita se** (27.10.2026): `span.ed-if` (no box, `display: contents`: its pills are the row's) holding three such pills, "Pita se" (Uvijek / Samo ako …), and once that says Samo ako … (`.open`) "Pitanje" (the earlier questions a condition can name, "16 · " and their first 40 characters) and "Odgovor" (Da / Ne; a scale's 1–10 with a muted "ili više" after the select, `.if-tail`, shown when the box's `data-kind` is scale; a choice's or a multi's options); the pair saves together once an answer is chosen (base.html's `ask`), Uvijek at once. A pill never grows past the row (`max-width: 100%`, its select `min-width: 0`: a long question's words are cut by the select, not the page). An ↑ / ↓ that would put a question above the one it is asked after keeps its look and says why in the copy bar at the press (`data-refuse`). Under the row, `.q-ed-line`: muted .82rem, what the settings do ("Dio 2 · skala · boduje se: trening baza"), and for a conditional question a second line, `.q-ed-if` ("Pita se samo ako pitanje 16 = Da"), in the karton's amber at 600 when its condition cannot work (`.void`: "Pita se uvijek — uvjet ne vrijedi: pitanje 16 dolazi kasnije") or a hidden question above it mutes it (`.muted`: "Pita se samo ako pitanje 17 = Da — pitanje 16 je skriveno, pa ni ovo nitko ne dobiva"; the step itself `.is-muted`, dimmed to .55 as a hidden one, no step outside edit mode); `--warn` defined on `.quiz` per theme, AA on `--bg`. "Obriši pitanje" on a question shown ones hang under carries `data-warn`: its first tap says in the copy bar "Pitanja koja ovise o njemu ostaju i pitat će se svakoga." and stays armed 8 s (4 s otherwise). In edit mode a conditional step sits under the one it is asked after: `data-depth` 1–4, a 1px `--line` hairline at its left and its content 16px in a level (padding 15 + the hairline; margin-left 16px for each level past the first). A hidden question (`.is-off`) is dimmed to .55 but this row and its line. Above the first question `.q-sum` (a muted .88rem line, and `p.alert` when nothing scores); under the last `.q-add` ("+ Dodaj pitanje", the gym's `.act` pill, centred, 26px under it). Edit mode only; a client never gets any of it |
| `.vodic` / `.v-sec` / `.v-nav` | `_vodic.html` (base's CSS: /upitnik's first screen, /vodic) | the guide through the training (29.10.2026, the gym owner's introduction): one box, in the questionnaire's clothes. Its title the h1 in a question's look (`.q-h`'s values: PT Sans uppercase `clamp(1.45rem, 5vw, 2rem)`, 1.15, `margin: 8px 0 22px`; `tabindex=-1`, focused by the questionnaire's script), then eleven `.v-sec`, 22px apart, each the same four slots in order: an `h2` at the section-title size (1.05rem), a `p` of lines at body size (`span.t`'s `pre-line` keeps the owner's breaks), a `ul` of the landing's offer bullets (the 8px `--accent` dot in its 5px `--accent-dim` halo, on the first line's middle, 12px before the text, items 8px apart) and a `p` of lines under it; 10px between a section's pieces. Last `.v-nav` (26px above): ONE `.btn`, at the right as Dalje is, the column's width below 600px (a phone); on /upitnik the questionnaire's `.q-next` (goes on to question 1), on /vodic a link to `/upitnik?od=1`. An emptied slot prints nothing for a reader (no `h2`, no `p`, no `ul`; a section with all four empty no `.v-sec`); the editor gets each as an `.ed` box, an empty list its empty `ul` (no room) and "+ Dodaj stavku", in edit mode only (outside it an `h1` / `h2` / `p` whose `.ed` is empty, and a section with no text, take no room). In edit mode an item's ✕ keeps inside the column (`margin-right: 0`, as the landing's contact lines'). No card, no tint: it is reading, between the questionnaire's title and its first question |
| `form.ed-add-ann` | landing (trainer, owner) | "+ Dodaj najavu": an `.act` pill (32px tall at every pointer) after the announcements' dots, centred in the hero under the stacked cards, in edit mode only; a plain form (`POST /aktualno/nova`) that comes back with a new card last (placeholder texts, shown, no photo). Not rendered at the cap (8 cards); with none left it is all the editor's empty box holds. A visitor never gets it. The gym's "+ Dodaj karticu" (`form.ed-add-gym`, `POST /dvorana/nova`) is the same pill under its row of cards, 18px under them |
| `.featured-tag` | base | "Najpopularnije" chip in the top-right corner of a `position: relative` card: accent tint + `--accent-tint-ink`. Used by `/moja-clanarina`'s "Dodaj plan" and the landing's offer |
| `.period` | base (`_period.html`) | Mjesečno / Godišnje (promoted from the landing 21.10.2026, when `/moja-clanarina` needed it): a switch per group of cards that carry a monthly and a yearly price, `.price[data-period]` month / year — the landing's two sections, `/moja-clanarina`'s two "Dodaj plan" groups. The `.auth-tabs` idiom on a `--surface` track with a hairline (the tint over `--surface-2` is 4.34:1 in dark): 36px pills in muted 600 .85rem, the chosen one `--accent-dim` with `--accent-tint-ink`. `period_switch(start)` renders it `hidden`, its `start` tab `aria-selected`, while the page renders its group's cards with the other line `hidden`; base.html's script shows it and, at a press, sets the lines inside its closest `[data-period-group]` and its own `aria-selected`, never another group's. Per page view, nothing remembered; without JS no switch, the opening price. Where it sits is the page's: centred under each row on the landing (34px, 10px below 900px), under each group's heading on `/moja-clanarina` |
| `.alert` / `.alert.ok` | base | flash after a redirect (`?error=` / `?ok=`); `?cta=<plan>` adds a "Pogledaj cjenik →" pill to that plan's card on `/moja-clanarina` (`#plan-<key>`) |
| `#authDlg` `.fb-modal.auth` | base (guests) | login + registration in one modal (login only, no tabs, while signup is closed), `.auth-tabs` segmented (accent-tinted selected), 48px inputs, `.pw-eye` toggle; opened by any `<a data-auth="login\|signup">`, hrefs stay as the no-JS fallback; `next` = current page |
| `#a2hs` `.card.a2hs` | base (clients) | install banner: phones only (`pointer: coarse`, plus a `pointer: fine` CSS kill-switch), not in standalone mode, not on the first page load, back a week after each dismissal until installed (`localStorage qmt-a2hs`: when it was dismissed, or `installed` once the native prompt was accepted; the owner's call, 16.10.2026); iOS gets share-sheet steps, Chrome gets a real "Instaliraj" via `beforeinstallprompt`. Never while staff act as a member (it is about the device), never on the load the phone reminder shows on (below: that one first) |
| `#phoneCard` `.card.phone-card` | base (a member with no phone number, 26.11.2026) | the phone reminder, the install banner's card, its look and its place (fixed 16px off the bottom and the sides, 420px at most, centred; scrolling inside itself past the screen's height); on a fine pointer too, there 360px wide at the bottom right. On every page but a one-task page (`solo_page`) and `/profil`, for a member whose phone is empty (staff acting as him too: it is about the member); never staff's, never a guest's. Its ✕ (`.phone-x`, the banner's `.a2hs-x`, `aria-label` "Kasnije"), its head (`.phone-head`): a 44px tile (`.phone-ic`, `--surface-2`, 10px radius, a phone's 22px line icon in `--text`) where the banner has the app's icon, and the title (1rem 700, `app.phone.title`); its lead (`.phone-lead`, the hint's look .88rem, `app.phone.lead`, optional); one `.btn.btn-sm` at the right, "Upiši broj" (`app.phone.go`) → `/profil#p-phone`, whose field takes the focus. Rendered `hidden`, shown by the script: no JS, no card. Its ✕ stores when (`localStorage qmt-phone`) and it stays away a week, then asks again, until a number is saved (the page renders no card then); on the load it shows, the install banner waits |
| `.next-termin` | calendar (clients) | "Tvoj sljedeći termin", every width, right under `.week-head`: a `.card` (padding 14px 16px) with `.sess.mine`'s inset accent bar on its left edge; a `.sec-kicker` caption (700 .74rem uppercase, letter-spaced, `--accent`), the day and time (700, tabular) with a muted "danas" / "sutra" / "za N dana" (or "OTKAZANO" in `--danger`), the title + `.tag-11`; at the right end the list's `.unbook` ✕ (the same `unbook` macro), or "Otkazivanje do 12 h prije termina" under the title. No booking, no card (no empty state) |
| `.day-strip` | calendar (≤860px) | the week as seven `<button data-day>` (Shape's "Moj napredak" strip): `pon` (.72rem, uppercase, muted) over `12` (1rem 700, tabular), 52px tall, `flex: 1 1 0` up to 44px wide so seven fit 360px, `--r-md`, hairline on `--surface`. Chosen: `aria-pressed="true"`, `--accent-fill` with `--accent-ink`; today (not chosen): a 2px `--accent` ring, `aria-current="date"`; no termini: muted label at .6 (still tappable: "Nema termina"); `.has-mine`: a 6px dot under the number. `aria-label="pon 12.10."`. Rendered `hidden`; the script shows it, so without JS there is no dead strip. Absent for an empty week |
| `.sess-row` | calendar (≤860px, one-day view) | one termin as one row, min-height 56px (the row is the tap target): time (700, tabular) · title on one line (a `-webkit-line-clamp: 1` clamp, so a long title ends in "…" without widening the row) + `.tag-11` outside the clamp · the state at the right end in .8rem: `n/8 ›` (count `--good`), "slobodno ›" (1:1), "rezervirano ✓ ›" (`--good`, inset accent bar), "puno" / "zauzeto" (`--danger`), "potrebna članarina" (muted, may break in two), "otkazano" (`--danger`, title struck), "zatvoreno" (29.10.2026: an empty termin `CLOSE_EMPTY_HOURS` or less before its start, `db.is_closed`; the state's muted .8rem, the row `.closed`, never struck: a line through means the trainer canceled it; the trainer's row says it in place of "Polaznici", still a link). A `<button>` when a tap does something for a client (`data-state` book / mine / mine-late opens `#sheet`; book only when the termin is open and inside his paid period: a row after his dospijeće keeps its count, no chevron), the trainer's `<a>` to `/admin/session/{id}` ("Polaznici n/8 ›"), else a plain `div`; past, canceled and closed at .45. The desktop's `.sess` card the same: "zatvoreno" in its `.cap`, `.sess.closed` at .45, no Rezerviraj (nor after dospijeće) Shown instead of the `.sess` cards only once the script marks the week `.one-day` |
| `#sheet` `.fb-modal.sheet` | calendar (clients) | the bottom sheet a row opens: ONE dialog filled from the row's `data-*` (kicker day, h2 "07:00–08:00 · Grupni trening" + chip, `.fb-lead` "0 od 8 mjesta zauzeto" / "Termin je slobodan." / "Rezervirano"), then ONE action: Odustani + "Rezerviraj" (`POST /book/{id}`, with the "Isti termin svaki tjedan do 23.11." checkbox, `series=1`, on weekly slots: the date the row's `data-until`, the earlier of the booking window's last day and the client's dospijeće, and no checkbox when no later week fits it; its label's text one `span`, so the flex gap does not split "do" from the date), Odustani + "Otkaži rezervaciju" (`POST /cancel/{id}`; the sheet is the confirmation, no `data-confirm`), or, inside the 12 h, the sentence and "U redu". ≤860px it is docked to the bottom (full width, top corners `--r-lg`, `env(safe-area-inset-bottom)`); the ✕, Escape, the backdrop and Odustani close it; the primary action takes the focus |
| `#seriesDlg` `.fb-modal.series-dlg` | calendar (clients) | a weekly series that left dates out (29.10.2026, the owner's "popup warning"): rendered `open` when the page's query carries `skipped=` (`date:key`) or `paket=` (with `booked=`, ISO dates; `app._series_report`), and the script makes it the modal at load (`close()` then `showModal()`); without JS it is a card in the page's flow under the alert (`:not(:modal)` → `position: static`). The h2 "Nisu rezervirani svi termini", `.fb-lead` "Rezervirano: 5.11., 12.11." (or "ništa"), "Nije rezervirano:" and `.sd-list`, one `--text` line per date ("19.11. — termin je popunjen"; the reasons' words are the template's: popunjen, otkazan, već imaš rezervaciju, zatvoren, već prošao), the paket's sentence as a lead, and ONE button, "U redu" (`.btn.btn-sm`, `autofocus`, a `method="dialog"` form); Escape and the backdrop close it too. No ✕. A run that booked every date gets the alert alone |
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
| `.unbook-x` in `form.unbook` (calendar) | 32px round ✕ at every pointer, no fill, `--muted`; pinned 6px into the top-right corner of a "Moje rezervacije" card (the card's `.t` line reserves 28px for it and never wraps); on phones at the right end of the booking's row, and at the right end of `.next-termin` | faint `--text` wash, ink → `--text`; never the red flood | cancel a booking: asks first via `data-confirm` ("Otkazati rezervaciju?" / "Otkaži rezervaciju"; "Maknuti otkazani termin?" / "Makni" for a termin the trainer canceled, whose ✕ stays unfaded on the faded card). Only while cancelling is allowed (`db.cancel_deadline`); after that the card says "Otkazivanje do 4 h prije termina" (12 h until 25.11.2026: the number is `CANCEL_CUTOFF_HOURS`) |

**Amber = someone else's account** (26.11.2026, build 4; the owner: "The
button to open as another user should also be in amber"): every control that
opens a member's app as he has it wears the strip's amber (`.kao-bar`, Layout
above), so nobody takes it for an action on his own account. Two looks,
base.html's, AA in both themes. **`.act-kao`**, on an `.act` (/kao's "Otvori →",
a roster's "Kao član →", the trainer's view's "Otvori kao član"): the karton's
tint, `--warn` on `--warn-soft` with a 40% `--warn` hairline (`.act-absent`'s
values: 4.9:1 on a light card, 4.6:1 on the light page, 7.5–8.5:1 dark), its
hover a deeper tint (`--warn` at 26%, the border `--warn`), never a flood, the
background declared so a `<button>` and an `<a>` look the same. **`.btn-kao`**
(the Karton tab's "Otvori kao član"): the strip's solid pill, `.kao-exit`'s
colours, `--warn` with `--bg` for ink (5.5:1 light, 11.4:1 dark), its hover an
18% `--text` mix, at a form button's size (600 .92rem, 0 20px, 40px tall, 44px
on a coarse pointer), no glow, whole in itself (no `button` base needed). The
strip's "Izađi" (`.kao-exit`) stays as it was.

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
| combobox (`.cbx`, base.html's `qmtCombobox(src, opts)`) | a list too long to scroll, typed into instead (23.11.2026: the library, 275 exercises on prod; the day editor's "Dodaj vježbu", from the same day until 26.11.2026 each exercise block of the karton's exercise log, and since 26.11.2026 the gym training's "Dodaj vježbu"; the script and its look were trening_day_edit.html's until the karton needed them). Two sources: a `<select>` (the day editor: it stays in the form, carries the value posted, and is the no-JS picker, `required` there; hidden here, its options the rows), or `{rows: [{id, name, tags}], value: a hidden input}` (the gym training's add card, the karton's blocks before it: the library on the page once as JSON, each row folded once for every combobox over it). In the value's place `.cbx` (`position: relative`), holding the app's text input (the value's id + `-q`, `#add-ex-q` on the day editor: `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-autocomplete="list"`, `aria-activedescendant`; the label's `for` moved to it; 44px on a coarse pointer, the day editor's Dio select beside it too, the karton's `.xb .cbx > input`) and `.cbx-list` (`role="listbox"`, `hidden` until the input has the focus): absolute, 4px under the input and exactly its width at every width, `z-index: 5`, at most 280px tall and scrolling, `--surface`, hairline, `--r-md`, `--shadow`, 4px padding. It lies over what follows (the Dio select, the buttons), never pushes it down. Its rows (`li[role=option]`, built from the select's options, "name · tags"): 44px at least, 8px 12px, 8px radius, the name (`.cbx-name`, 600 .95rem) over its tags (`.cbx-tags`, muted .78rem); the active one (the arrows') and the hovered one `--surface-2`. At most 60, then a muted line that is no option (`.cbx-note`: "… još N — nastavi tipkati", or "Nijedna vježba ne odgovara traženju."). It matches with `qmtFold` (base.html; `models.fold` is the same table on the server): every word typed in the name or the tags, the names that start with it first, then a word of the name that does, then the rest, the alphabet within each. ↓ / ↑ move the active row (scrolled into view), Enter picks it and never submits while the list is open, Escape and Tab close it, a tap picks (a mousedown on the list keeps the focus in the input). A pick sets the select, puts the name in the input and keeps the focus there; typing again clears the select. The ids are the value's (`-q`, `-list`, `-err`, `-o-<exercise id>`), so several live on one page. The script checks the submit: nothing picked, `.cbx-err` "Odaberi vježbu s popisa." under the input (.85rem 600 `--accent`, `aria-live="polite"`, `aria-invalid` on the input) and the focus back in it; `opts.submit: false` leaves the check to the page, with the returned `fail()` (the karton: an exercise is needed only once a set is typed, and the focus goes to the first block that lacks one). `opts.tagbar` wires the tag chips (the day editor's). Its words are the library's by default; a list of something else gives its own (26.11.2026, build 4: the Karton tab's members): `opts.placeholder` (the input's), `opts.listLabel` (the list's `aria-label`), `opts.missing` (nothing picked), `opts.noMatch` (nothing matches); and a given row may carry `find`, what it matches by besides its name in place of its tags (a member's email, not the plans his muted line shows) |
| tag chips (`.tagbar`, `.tag-chip`; base.html, `_tagbar.html`) | a search helper under an exercise search (23.11.2026, the owner: "search the items used in the exercise like for example 'girja'"): the library's (`vjezbe.html`, between the tools row and the count line) and the day editor's "Dodaj vježbu" (above `.add-fields`, so the combobox's open list never covers it), the same row on both, so base's. `div.tagbar` (`role="group"`, `aria-label="Oznake"`, no caption: the row explains itself): a wrapping flex row, 6px gap, never a sideways scroll. A chip per tag at least two exercises carry (`db.tag_counts`, the most used first), each a `<button type="button" class="tag-chip" data-tag>` (never a submit: the day editor's sit inside `form#dodaj`): the library's `.ex-tag` look at a tap size, `--surface-2` with `--text`, 600 .74rem, a pill, 6px 12px, 32px tall (36px on a coarse pointer), a hover a 10% `--text` wash; no count after the tag (noise). **Pressed** (`aria-pressed="true"`: every word of its tag is a word of the box) the `.period` switch's chosen side, `--accent-dim` with `--accent-tint-ink`, which a hover keeps (5.2:1 on `--bg`, 4.8:1 in a dark card). The first 12, then **"još N"** (`.tag-chip.tag-more`: no fill, a hairline, `--muted`, the text `--text` on hover; an action, not a tag), which shows the rest and goes (the focus it had moves to the first one shown, not to the page). Rendered `hidden`; `qmtTagbar(bar, box, focus)` (base.html) shows it and makes a tap toggle the tag's word(s) in the box, then fires `input` on it (the page's filter runs as for a key); `focus` leaves the focus in the box (the day editor: its combobox opens filtered), else on the chip (the library: no phone keyboard over the list). The returned function re-syncs the chips where a page sets the box itself ("prikaži sve", a pick). Without JS: the library's `<noscript>` row of `<a class="tag-chip">` links to `?q=<tag>`, every chip shown, the one that is the whole `?q=` `aria-current="true"` (the pressed look) and linking back to the whole list; the day editor's row stays hidden (the select is the picker) |

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
| `.u-flag` (karton, the trainer's view; since 26.11.2026, build 4, the member's karton while staff act as him, under `.u-staff` "Vidi samo trener") | the upitnik's safety flags, 999px pills, 700 .78rem: `.review` "Zahtijeva pregled" (q15 Da) in `--accent-dim` / `--accent-tint-ink`; `.pain` "Bolovi N/10 · where" (q14 ≥ 4) in the karton's amber (`--warn` on `--warn-soft`, the `.act-absent` values, AA on both themes); since 23.11.2026 the same `.pain` chip "Ograničenja" heads the limitations card on the trainer's view while the member's text holds anything |
| `.u-note` (karton) | the pain sentence for a client at q14 ≥ 7 (`upitnik.pain_note`), shown to him and the trainer: `--text` on the amber tint, `--r-md`, 10px 14px |
| `.venue-chip` (base.html; staff's /treninzi table, a programme's page and its editor) | "dvoranski" after a dvoranski programme's title (24.11.2026: a gym programme, the trainer's own, which no client sees): a muted fact, not a state, the karton `.chip`'s values in a pill (`--muted` on `--surface-2`: 4.6:1 light, 5.6:1 dark), Inter 600 .72rem/1.5, 2px 9px, never broken, `vertical-align: middle`; lower-case even inside an uppercase PT Sans h1 (`text-transform: none`): after the h1's title on the programme's page (staff only) and after "Uredi program" in its editor. In the table it follows the title's `strong` in the same cell (no new column) and wraps under it on a phone |
| `.price > .base` / `.base-l` (base.html; the landing, /moja-clanarina) | the **bazna cijena** under a price (23.11.2026, the law's base price; `_plan_price.html`'s `base`): `<small class="base">`, the last child of its `.price` block, so the Mjesečno / Godišnje switch shows and hides it with its price; a block of its own under the amount and its unit (`flex-basis: 100%` in the landing's flex row), 500 .8rem/1.3 `--muted`, 2px under the amount, tabular-nums, `overflow-wrap: anywhere`. Its words: `.base-l` "Bazna cijena na 10.9.2026.:" (the `price.base_label` slot, the colon the template's), then the base slot, " €" after a number without its sign (`priced`). Only under a price that holds a number, and for a visitor only when the base holds one too (the editor's box shows as soon as the price does). In a line of prices it goes in brackets after each price instead (`base_paren`: Individualno's other plans, prehrana's MojiMakrosi line), " (Bazna cijena na 10.9.2026.: 25 €)", a `span.base-paren` (an inline block in the landing's `.price-note`, as a price's `.whole` is) |

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
and stay level whatever is typed. Under every price that holds a number its
bazna cijena (`.base`, above; 23.11.2026), none under "na upit": when any
card of a row shows one, every price of that row keeps its room (`min-height`
adds the line, the row gap and its 2px, the number at the top:
`.swipe-row:has(.price:not([hidden]) > .base)`), so a "na upit" beside "50 €"
stays level; a row that shows none keeps none. `.featured` (tier 2) is taller, not shifted
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
18.10.2026, in the editor's order, up to eight, added, deleted and moved in
edit mode: `form.ed-add-ann`, `form.ed-ann-x`, `form.ed-ann-mv`) as `.event` cards in `.evs` (text left-aligned
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
(`.ed-flag`, `.ed-img`, `.ed-img-x`, `form.ed-ann-mv`'s pair, `.ed-ann-x`) stack at the top of a photo card. Info band
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
prehrana's hint; no note under a price since 21.10.2026. Every price line
carries its bazna cijena under it (`.base`, above; each `pp.price` call
passes its base's key, `base_key=BASE_OF[…]`), and prehrana's hint each
add-on amount's in brackets. Stripe's amounts
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
`qmtToggleForm`. **The page's order** (25.11.2026; a grid with a rail, `aside.k-rail`, the weight and the termini, beside the diary until then): the upitnik block, `.limits`, `.masa`, `.photos`, `.maxes`, `.hist` (since 25.11.2026's later build), `.termini`, each a card of the column, then the diary (`.k-sec`) last. Below 1000px one column, every card 720px at most at its left edge; from 1000px `.k-cards` is a grid of two equal columns across the page's width (`repeat(2, minmax(0, 1fr))`, 20px gap, the two of a row one height: the grid stretches them), in the same reading order, the upitnik block, `.hist` and `.termini` (half a row, a termin's title gave way to a long retyped "OTKAZANO") and a `.card` left alone in its row (`:last-child:nth-child(odd of .card)`, its own rule) across both; the diary under it at the page's width, its forms (`.k-sec .le-edit`) 640px at most. Staff's own karton (24.11.2026, `staff_own`: the trainer's, the owner's) is a member's with no upitnik block (nothing in its place) and no `.termini`, its empty diary "Još nema treninga u dnevniku.". **Its way into a member's app** (26.11.2026, build 4): `form.kao-pick` right under the lead, above `.k-cards`, 26px over them: "Član" (base.html's `label`) over `.kp-row`, the member field (`.kp-field`: the combobox, Forms above, in `{rows, value}` mode over `#kp-json`, each row the name over the muted "email · plans"; the native `select` without the script) and "Otvori kao član" (`.btn-kao`, Buttons above); the input and the select 40px tall (`padding: 0 13px`), 44px on a coarse pointer, as the button; from 600px one row, the field `flex: 1 1 auto` and 420px at most, the button beside it, their tops level (`align-items: flex-start`: the "nothing picked" line under the field lengthens its own column alone); under 600px one column, the button the column's width under the field. The list lies over the cards (absolute), never pushes them; on a phone, open, it covers the button, which a pick uncovers. Never while acting, on the trainer's view or a member's karton; no member, no form. `.upitnik`
is `--r-xl`; `.log-entry` rows are `--r-md` and keep the accent inset bar for
`.fresh` — at 12px the bar still reads as a bar. A v2 response's block (26.10.2026)
puts `.u-fact` pills and the muted score ("6,4 / 10") on its `.u-meta` line, the
trainer's `.u-flag`s under it, and the `.u-note` under the ramp; under "Odgovori"
a conditional question's answer is `li.follow` (no bullet, muted question), indented 14px a level under the one it is asked after: `.d1`, `.d2`, `.d3` (deeper stays at `.d3`), since 27.10.2026 ("Gdje te boli?" under the pain question, a chain's answers each further in).
While staff act as the member (26.11.2026, build 4) his own block prints the
trainer's `.u-flag`s and "Odgovori" too, the view's markup, each group under
`p.hint.u-staff` "Vidi samo trener" (muted .78rem, 10px over the flags' row,
14px over "Odgovori", the group 4px under it; there, on a coarse pointer,
"Odgovori" is 6px padded, a 33px target); none over a group that prints
nothing, nothing of it on the member's own view.
**An online pass in the diary** (30.10.2026, `.log-entry.online`, `id="pass-<id>"`):
a finished pass among the termini by when it started, a written termin row's
shape: `.le-kicker` "Online trening" over it (700 .7rem, .12em, uppercase,
muted: a caption, not the accent's), then `.le-head` (the date, `.rpe` "napor
7/10", `.rpe.feel` the osjećaj, grey for "Slabo"), two muted `.le-sub` lines
(.8rem: "Trening 1 · Cijelo tijelo — Cijelo tijelo — srednja razina", the
snapshots; "6 od 8 vježbi · 38 min", a day since deleted "6 vježbi") and the
comment. No `.le-actions`: nothing on the karton edits or deletes a pass. Under
it `details.sets` "Serije" (base.html, below): the trainer's view's only until
23.11.2026, the client's too since.
**A training's exercises** (23.11.2026): an old osvrt row (and an old training
outside a termin's, `.le-kicker` "Trening izvan termina" over its head, where a
termin's row says its title) puts under its comment a muted `.le-sub.le-ex`
("3 vježbe") and `details.sets`; both give way to the edit form while it is
open (`.editing`), as the comment does. A row with no exercise shows neither.
**The exercise log in a form** (`fieldset.xl`, `.xb`, 23.11.2026) went on
26.11.2026 with the plain osvrt form (build 3: the gym training below); the old
rows' exercises are read only, "Serije" as before.
**A gym training's row** (`.log-entry.gym#gt-<id>`, 26.11.2026): a termin's row
in shape, its title the `.le-kicker` (outside a termin "Trening izvan
termina"), the day, date and time in `.when`, napor and osjećaj as `.rpe`
chips, "Otvori trening" (`.act`, `.le-actions`) while the member may write it,
its comment, then `.le-sub.le-ex` ("3 vježbe") and `details.sets` whose lines
say "Goblet čučanj: zadano 3 × 10 · 20 kg — odrađeno 10 × 20 kg · … · težina
8/10" (the name in 600, each set a `span.set`). A booked termin with none: its
row's `.le-actions` "Upiši trening" (`.act`, inside the window) beside "Nisam
bio/la", and under the head its state, `.le-state` (muted .8rem, the online
pass's `.le-sub` size): "Trening još nije upisan." / "Trening nije upisan.".
**"+ Dodaj trening izvan termina"** (`.log-new`, the member's own karton, above
the diary's rows): an `.act` that opens its form (`qmtToggleForm`) in a hairline
box (`--surface`, `--r-md`, 14px 12px 12px), Datum (`type=date`) alone and
"Dodaj trening" (`.btn-sm.btn-signal`): its training's page does the rest.
**"Nadolazeći termini"**' way in (26.11.2026): a termin whose training is open
ends its `.cal-row` with "Upiši trening →" (`.act.cal-go`, pushed right), and
under the list, once, a muted `.hint.gym-when` (.82rem, 8px over it) says when
a training opens. The raspored's "Tvoj sljedeći termin" carries the same link
(`.act.nt-gym`, 8px under the card's lines, wrapping inside the card).
**The gym training's page** (`karton_trening.html`, 26.11.2026, build 3): the
normal layout and nav, one page that grows as the training goes, a 640px column
(`.gt`). The head: `.gt-kicker` (700 .74rem, .16em, uppercase, muted) over the
bare h1 (the termin's title), right under it `.gt-when`, the date and time in 700
tabular `--text` (never muted: the owner's "so that there is no confusion which
training they edit"), outside a termin a quiet "promijeni datum" (`.act.act-quiet`
summary of `details.gt-date`, its form wrapping under the line); then
`.gt-state` (muted .92rem), one line. The parts: `section.gt-part`, each its
`h2.dx-cap` (the day page's caption, 26px between parts) over `.gt-cards` (a grid
10px apart). **A card** (`details.card.gt-card`, `--r-lg`): its summary the row,
56px at least, 12px 14px 12px 18px, the whole row the tap target (hover a 4%
`--text` tint): `.gt-main` (`.gt-name` 700 over `.gt-planned`, muted .85rem
tabular "Zadano: 3 × 10 · 20 kg"), `.gt-mark` (700 tabular, muted "2/3", `--good`
"✓" as `.ok`, `role="img"` with its words), `.gt-go` (the day page's 32px round
▷ on `--surface-2`, turned 90° open). Open, `.gt-body` (0 16px 16px, 18px from
600px): `.gt-sub` (muted .85rem: the pause, the note), the set log (`.pl-sets`
with its ✓ column; `.gt-err` under it, 600 .85rem `--accent`, `role="status"`),
then `.gt-foot-row` (a column, 12px apart, left-aligned): "+ serija" (`.act`),
the rating (`.pl-rate`), the no-JS "Spremi" (`.btn.btn-sm.gt-save`, which the
script hides); read only, `.gt-done` ("Odrađeno:" muted 600, then the sets,
tabular); `details.gt-how` ("Kako se izvodi", the player's `›` that turns);
`.gt-tools`, the quiet row (12px over it, wrapping, 6px 8px): "Uredi zadano"
(`.act.act-quiet` summary of `details.gt-edit`, whose open form takes the row's
width under it: `.gt-form`, the day editor's row grid, two columns, four from
600px, 40px controls, 44px on a coarse pointer; a closed one's form has no box),
↑ / ↓ (`.act.act-quiet`, `disabled` at 35% at a part's end) and "Ukloni vježbu"
(`.act.act-quiet`). **"Dodaj vježbu"** (`form#dodaj.card.gt-addcard`, 18px 20px,
16px under 600px): h2 1.05rem, the `.tagbar`, `.gt-add-fields` (the combobox
over the library and Dio, side by side from 600px, `minmax(0, 1fr) 180px`, 44px
on a coarse pointer), `details.gt-zadano` ("Zadano (neobavezno)", muted 600
.85rem with a turning `›`; open, `.gt-nums`, the same grid), "Dodaj"
(`.btn.btn-sm`). The end: "Završi trening" (`.gt-finish .btn`, the page's one
glowing button, the column's width under 600px) or, saved, `section.card.gt-osvrt`
(16px 18px; h2 1.05rem, `.gt-facts` 600 tabular "napor 7/10 · Dobro",
`.gt-comment` muted pre-line, "Uredi osvrt" `.act`); then `.gt-foot` (26px over
it): "Isprazni trening" / "Obriši trening" (`.act.act-quiet.gt-drop`, in
`--accent`, `--accent-strong` on hover; it asks first). While the rest bar shows,
`body.has-rest main` keeps 100px under the column (150px with the ✎ pill). A
form's word comes back inside its card or the add card (`.alert`, its text
wrapping anywhere), never at the page's top. Every control's words wrap inside
their pill (`main :is(.act, .btn, .btn-sm)`). **Its osvrt**
(`karton_trening_osvrt.html`): the finish screen's `.kr` (below) with
`.kr-eyebrow` "Osvrt na trening", the title as the h1, `.kr-when` (700 tabular),
Napor, Osjećaj, Komentar, "Spremi trening" and `.kr-more`'s "Natrag na trening"
(`.act.act-quiet`).
**The gym training, part B** (26.11.2026): **a part's head** (`.gt-part-head`, a
wrapping flex row, 6px 10px, 10px over its cards; parts 26px apart): its `h2.dx-cap`
(no margin of its own there; a circuit's "KRUG 1 · KRUŽNO · 3 KRUGA · ODMOR 90 S")
and, while writable, **"Uredi dio"** beside it (`.act.act-quiet` summary of
`details.gt-part-edit`; open, it takes the head's width and its ONE form,
`.gt-part-form`, lies under it in the day editor's "Kružno" box: hairline,
`--surface`, `--r-md`, 12px 14px; "Naziv dijela" across, "Kružni dio" a whole-row
checkbox label (`.gt-check`, 44px, 500 .92rem in the text's case), Krugova and
"Odmor nakon kruga (s)" side by side and Spremi across both on a phone, the two and
Spremi on one line from 600px; 40px controls, 44px on a coarse pointer; a closed
one's form has no box). Its word (`.alert`) under the head. **A circuit's
exercise** (`details.card.gt-card.gt-crow`): the card with a 48px summary (8px 12px
8px 16px), what one round asks under the name, its mark the rounds ("1/3", "✓");
open, the note, "Kako se izvodi", the quiet row (its "Uredi zadano" two fields fewer:
from 600px Dio and the three numbers on its first line, the note and Spremi on its
second, as a normal card's). **A round** (`details.card.gt-round#krug-<key>-<n>`, the cards'
summary: "Krug 2" in 700, a saved round's ✓ in `--good`, the ▷), the rounds a grid
10px apart, 14px under the exercises (`.gt-rounds`); open, `.gt-rform`: an exercise a
hairline box each (`.gt-rrow`: `--r-md`, 10px 14px 12px; the player's round screen's
`.cr-row`), its name (600) over what one round asks (`.gt-rdose`, muted .85rem
tabular), its inputs two to a row (`.gt-rin`: the set log's header words over 44px
centred tabular inputs), then `.gt-rfoot` (a column, 12px): the round's rating
(`.pl-rate`) and "Krug 2 odrađen" (`.btn.btn-sm`, one span). **A slot**
(`details.card.gt-card.gt-slot`): dashed, no fill, no shadow (the day page's
`.dx-slot`), "Prazno mjesto · čučanj" muted 600; open, `.gt-fill` (the combobox's
field and "Odaberi", its words' width; side by side from 600px, the field 12rem at
least, so a long retyped button wraps rather than squeezing the picker; rendered
hidden, the script's) and "Ukloni" (`.act.act-quiet`). **"Odaberi gotov trening"**
(`details.gt-tpl`, 18px over what follows, while the training holds no row): an
`.act` summary; open, `.gt-tpl-list` (a grid 8px apart, 10px under it) of
`button.gt-tpl-row`, each a hairline row 56px at least (`--surface`, `--r-md`, 10px
14px 10px 16px): `.gt-tpl-name` 700 over `.gt-tpl-facts` (muted 500 .82rem), a muted
→ at the right (`.gt-tpl-go`), the whole row the target, its hover `--surface-2`.
After a round's save the page starts the rest bar at load (`.gt[data-odmor]`).
**"Procijenjeni maksimumi"** (`section.card.maxes`, 23.11.2026): between the
upitnik block and the diary grid, 720px at most like the upitnik block, 18px
20px (16px under 600px); its h2 1.05rem, `.mx-hint` .82rem, then a compact
table (`.maxes table`: full width, collapsed, .88rem, tabular): the header the
set log's words (700 .7rem, .12em, uppercase, muted, never wrapped), each row
a hairline over it and 8px above and below its text, the cells 10px apart,
top-aligned and wrapping anywhere (no sideways scroll at 360px). Vježba (the
row's `th`, 600), Procjena (`.mx-val`,
700, never broken: "108 kg", "9 ponavljanja"), Iz (the set and its date each
whole, `.nw`, then `.mx-src` "dvorana" / "online" muted; a bodyweight row the
date and the source alone: its reps are the Procjena). Empty: the hint and
`.mx-empty` (muted .88rem).
**The body and the photos** (23.11.2026, part 2 of Amir's karton). **The head
line**: the lead under the h1 carries "Visina 178 cm · Masa 82,5 kg (12.11.)",
each part only when known; the member's a block line of its own inside the
`.hint` (`span.k-body`, tabular), the trainer's after the age and the phone.
A card's head is `.kc-head` (a wrapping flex row, the ends apart: the h2 with
no margin and, on the member's own karton, the `.act` that opens its form,
`qmtToggleForm`: `.editing` on the card shows its `.le-edit`; a narrow card
puts the button on a line of its own under the title, left), its buttons row
`.kc-btns` (Spremi `.btn-sm.btn-signal`, Odustani `.btn-sm.btn-ghost`), an
empty card's line `.kc-empty` (muted .88rem). `qmtToggleForm` focuses the
form's `[data-focus]` control, else its first select or textarea, else its
first input. **`.k-x`**: the quiet ✕ (the calendar's `.unbook-x`): 32px round
at every pointer, no fill, `--muted`, a faint `--text` wash on hover; its form
asks first (`data-confirm`).
**"Ograničenja i bolovi"** (`section.card.limits#ogranicenja`) and **"Napredak
— fotografije"** (`section.card.photos#napredak`): blocks of their own between
the upitnik block and the maxes, in that order, the maxes' look (`.card`,
720px at most, 18px 20px, 16px under 600px; h2 1.05rem). The limitations'
text `.lim-text` (.92rem, `pre-line`, wrapping anywhere), hidden with the
empty line while the textarea is open (`aria-label`, `maxlength` 2000,
resizable); the trainer's head carries the upitnik's `.u-flag.pain`
"Ograničenja" (the pain flag's amber, `.limits .u-flag`) while it holds any
text. The photos: `ul.ph-row`, a wrapping flex row (14px 12px), never a
sideways scroll; `li.ph` 120px wide, `a.ph-img` its 120 × 160 box
(`--r-md`, `--surface-2` under the photo, `overflow: hidden`, the img
`object-fit: cover`, lazy), a new tab; `.ph-cap` the month under it on one
line (.8rem); the member's ✕ `form.ph-x` on the photo's top-right corner, 6px
in, its `.k-x` a solid `--surface` circle with `--shadow` (a control on a
photo, never text on it: `--surface-2` on hover). The photo form's two fields
`.ph-fields` side by side where two of 220px fit, else stacked, its rule line
`.ph-rule` (muted .82rem); the empty card's hint `.kc-hint`.
**The documents' list** (`.lim-docs#lim-docs` inside `.limits`, 25.11.2026:
a member's findings and scans under his limitations): a block of the card
with its own toggle, 16px under the text, so `qmtToggleForm` opens a card's
OWN form only (`:scope > .le-edit`; the CSS `:is(.masa, .limits, .photos,
.lim-docs).editing > .le-edit`: Uredi never opens the documents' form, nor
"Dodaj dokument" the textarea). Its caption "Dokumenti" an `h3` in the
karton's kicker look (700 .7rem, .12em, uppercase, `--muted`), shown when
there is a document and always on the member's own karton; the member's
"Dodaj dokument" an `.act` beside Uredi in the head (both in a `.kc-btns`,
which wraps under the title on a narrow card; not offered at ten). Its form
sits in a hairline box (the training outside a termin's: `--surface`,
`--r-md`, 14px 12px 12px, 8px under the caption): the file (`data-focus`)
and "Naziv (neobavezno)", then Spremi / Odustani. Then `ul.doc-list`
(.88rem): a row per document, newest first, a hairline over each, 44px at
least, 6px above and below, a flex row, the ends apart: `.doc-main` (`flex:
1 1 auto`, `min-width: 0`) holding the name, a `.tlink.doc-name` to the file
in a new tab, wrapping anywhere (a long name of one word breaks inside the
card, never widens the page), and under it `.doc-meta` (a wrapping flex row,
4px 8px, muted .8rem, tabular): the karton's `.chip` ("PDF" / "slika") and
the date; at the row's end the member's `.k-x` (asks first, naming the
document). The trainer's view the same list, no form, no ✕.
**"Tjelesna kompozicija"** ("Tjelesna masa" until 25.11.2026's later build;
`section.card.masa#masa`) and **"Nadolazeći termini"**
(`section.card.termini`): cards of the column like the limitations' and the
photos' (`.card`, 720px at most below 1000px, 18px 20px, 16px under 600px; h2
1.05rem; until 25.11.2026 the rail's two, `--r-xl`, h2 .95rem). Under
the head `.ms-height` (muted .82rem: "Visina 178 cm"; on one's own karton since
26.11.2026, when the height left /profil, in `.ms-hgt#visina` a wrapping flex
line with a quiet "uredi" pill beside it, `.act.act-quiet`, "Visina nije
upisana" and "upiši" with none, which opens its own form under the line,
`qmtToggleForm('visina')`: one number field, "Visina (cm)", 200px at most and
44px tall, then Spremi / Odustani in `.kc-btns`, the card's other forms' look;
the trainer's view reads the line alone), `.ms-val` the newest entry's mass that has one (Inter 800 1.6rem,
tabular), `.ms-date` its date (muted .82rem); the form's `.ms-fields`,
Kilogrami beside Datum (`minmax(0, 1fr) minmax(0, 1.35fr)`, 12px; both
inputs 44px, one line), under them the document's field and `.ms-hint` (the
photo form's rule line: muted .82rem); then `ul.ms-list` (.88rem, tabular):
a row per day, a hairline over each, 34px at least (its text 6px above and
below, so a wrapped document's name keeps clear of the hairlines),
"12.11.2026. · 82,5 kg" and, with a document, " · " and its `.tlink` (a new
tab), an entry with no mass the date and the link alone, and the member's
`.k-x`; past twelve the rest under base.html's `details.sets` fold, "prikaži
sve" (the trainer's whole history under "Povijest"). Every card clears the
floating bar when a save comes back to it (`scroll-margin-top: 96px`).
**"Povijest vježbe"** (`section.card.hist#povijest-vjezbe`, 25.11.2026):
right after the maxes, the limitations' card look; from 1000px across both
columns (its form 640px at most, as the diary's forms) and the termini
across both after it. A GET form: "Vježba" over the picker (base.html's
combobox, Forms above, in `{rows, value}` mode over `#hx-json`, each row's
muted line "5× · zadnji put 23.11.2026."; its input 44px on a coarse
pointer; a native select of the same exercises without the script), then
"Prikaži" (`.btn-sm.btn-signal`) under it, the day editor's order. Picked,
`.hx` under a hairline, 16px down: the name an `h3` (.98rem), `.hx-last`
(.88rem: "Zadnji put: … · dvorana"), `.hx-sets` (600 .92rem, each set
`.set` whole), `.hx-max` (.88rem, its value `strong`), then `ul.hx-list`
(.88rem, tabular): a row per time, a hairline over each, 8px above and
below, `.hx-when` (the date 700, `.hx-where` muted 400 after it) over its
sets; past ten the rest under `details.sets`. Empty lines `.kc-empty`.
**The karton's texts** (25.11.2026) are copy slots (`karton.*`, the `.ed`
editor of every page): a long one wraps, never widens the page. A pill's,
a button's and a `<summary>`'s label wraps inside it once it is longer than
its row (`white-space: normal`, `overflow-wrap: anywhere`, `min-width: 0`,
`max-width: 100%`; the default labels stay one line, measured). A table
header's span is an inline box whose word stays whole up to 7.5em (the
maxes' three; 6em over the set log's numbers), so a column keeps its width
and a 300-character header fits a 360px row; the set log's other two break
anywhere. "OTKAZANO" in a termin row stays whole and wraps in half the row
(`max-width: 50%`, `overflow-wrap: break-word`). An emptied optional text (a
lead, a hint, a kicker, a chip, an empty line) prints nothing for a member;
its empty `.ed` box the editor gets in edit mode only (`:has(> .ed:empty)`).
**`.k-texts`, "Svi tekstovi kartona"** (a staff member's own karton, under
the diary): every karton text, area by area, so those only a member, the
trainer's view or a confirm dialog shows are in the editor's reach. In edit
mode only (`display: none` outside it: no room, nothing read aloud); a
`.card` of the column (720px below 1000px, the diary's width from it), 18px
20px (16px under 600px), 26px under the diary; its h2 1.05rem and one muted
.82rem line under it ("Ovdje su i tekstovi koje vidi samo član ili su u
prozorima za potvrdu. Promjena u prozorima i poljima vidi se nakon
osvježavanja stranice."); an `h3` per area (the kicker's look: 700 .7rem,
.12em, uppercase, muted, 20px above it), then a `dl`, a row per text
(8px 0, a hairline over it): its label (`dt`, muted .82rem) over the text
(`dd`, .92rem), an `.ed` a click opens. Its own words are the editor's, no
slot.

**Tekstovi (`tekstovi.html`, 25.11.2026; Admin ▾ → Tekstovi).** Every plain
slot of the app on one page (`copy.TEXT_PAGES`), the ones only a member or a
guest sees among them: the /admin pages' look, `.tx` a 720px column under the
h1 and its muted lead. The search first (`form.tx-search`, one full-width
`input[type=search]`, `autocomplete="off"`; hidden without JS, which shows it:
the whole list then), the library's way (vjezbe.html): every word typed, folded
(`qmtFold`), in a row's label or its text as it is now; the count line under it
(`.tx-found`, the hint's look, "12 od 543 · prikaži sve", the link a `.tlink`
that clears the box) while the box holds text, `.tx-none` muted when nothing is
kept; a row, an area or a page with nothing kept `hidden`. Then a `section.tx-page`
per page, 28px apart: `.tx-head` a wrapping row, its h2 (1.15rem) and
"Otvori stranicu →" (`.act`) where staff open the page; under the landing's, the
upitnik's and the guide's h2 a muted .82rem line, "Liste, tablice i kartice
uređuju se na samoj stranici."; then one `.card.tx-card` (2px 20px 12px, 16px
sides under 600px) of its areas: each an `h3` in the karton panel's caption look
(700 .7rem, .12em, uppercase, muted, 18px above it) over a `dl` of rows
(`.tx-row`, 8px 0, a hairline over each): the label (`dt`, muted .82rem) over the
text (`dd`, .92rem, an `.ed` a click opens in edit mode). An emptied text reads
"(prazno)" (`.tx-empty`, muted) outside edit mode, its empty box in it. Its own
words are the editor's, no slot.

**Gledaj kao član (`kao.html`, `kao_zapisi.html`, 26.11.2026; Admin ▾'s first
item).** Staff open a member's app as he has it (`app.current_user` is the
member while they do; the strip `.kao-bar` over every page then, above). The
picker is the /admin pages' look, `.kao` a 720px column under the h1 and its
muted lead; the owner gets one more muted line under the lead, "Zapis svih
radnji →" (a `.tlink`, `.kao-log`, tucked 10px up). The search first
(`form.kao-search`, /tekstovi's: hidden without JS, the whole list then), every
word typed, folded (`qmtFold`), in a row's name or email; the count line
(`.kao-found`, "3 od 41 · prikaži sve") while the box holds text, `.kao-none`
muted ("Nijedan član ne odgovara traženju „…”.") when nothing is kept, `?q=`
followed (`replaceState`). Then ONE `.card.kao-list` of rows (`.kao-row`, 60px at
least, 10px 18px, a hairline between the rows shown, the library's rule): at
the left `.kao-who`, a column, the name in 700 over the email (`.kao-mail`,
muted .88rem; none when the name is the email) and his running plans
(`.kao-plans`, muted .8rem, `PLAN_LABELS` in the plans' order joined by " · ",
"bez članarine" for none), each wrapping anywhere; at the right end "Otvori →"
(`.act.act-kao`, amber since build 4; a form posting `/kao/<id>`), which wraps
under the words on a narrow phone. No member: "Još nema članova." in a card. The record, `/kao/zapisi`
(the owner's), is one table (`.kz`, 980px at most, .88rem): Vrijeme · Tko · Kao
koga · Radnja · Status, the headers the form labels' look (600 .76rem
uppercase, muted, a 2px hairline under them), a hairline under each row, the
time, the action and the status in tabular figures; up to 600px a row is three
lines, not five columns (which broke every name and date mid-word): the time
(muted .8rem), "Trener QMT → Ana Kovač" (600), then the action and " · " its
status (muted), the head not shown there; "Još nema zapisa." muted; under it "←
Novije" / "Starije →" (`.act`). The shortcuts, amber since build 4
(`.act.act-kao`, Buttons above): on a termin's roster (`roster.html`) "Kao
član →" at each member's row's end (`.roster-row` wraps on a phone, the email
breaking anywhere); on the trainer's view of a karton "Otvori kao član"
(`form.kao-open`, under the head line); and the Karton tab's form (`form.kao-pick`,
`.btn-kao`: Karton above). None on /clanarine since build 4 (its `.row-acts`
pair of "Karton →" and "Kao član →" went). All their words are staff's own, no
slot.

**Every member page's optional text** (25.11.2026): `_copy.html`'s
`c.opt(key, tag, attrs)` prints the element around an optional slot only while
it holds a text (a reader gets no element and no gap once it is emptied); the
editor keeps the element, marked `data-opt`, and base.html hides it outside edit
mode (`body:not(.editing) [data-opt]:has(.ed:empty)`). A control whose words
sit beside a value keeps them in one `<span>` (a button, an `.act`, a summary
and a pill are flex boxes: two items would take the gap between them). A word
too long for its box breaks anywhere: base.html's `main span.t, dialog span.t,
#a2hs span.t { overflow-wrap: anywhere }`, and `.fb-modal` and the rest bar
whole (their scripts write words as bare text). Where a box takes its width
from its words, "anywhere" would let it shrink to a letter, so the box is as
wide as its words up to a bound instead (`width: max-content; max-width: 5em`
on a `.pl-sets` header, 8em on the player's "dodatna serija"), or the word
breaks only when it does not fit (`overflow-wrap: break-word` on a raspored
card's button, its form `width: fit-content` up to the card's right padding:
from 861px to 1000px "Rezerviraj" always reached into it).
A pill or switch whose words are a slot gets `max-width: 100%` and its text
`min-width: 0` (`.period`, `.chip`), so a long label wraps inside it; the
install banner scrolls inside itself past the screen's height. Measured: with
the pages' own words no word of a member page moves (the untouched tree beside
the build, every word's place, 360–1280px).

**Upitnik (`upitnik.html`, 26.10.2026; patterns.md §7).** One `form.quiz` (640px,
centred) holds every step; for a member the page sets `solo_page` (`not can_edit_copy`),
so the bar is the small pill with the brand alone; the trainer and the owner, who open
it to edit (Admin ▾ → Upitnik), keep their bar. `.q-title` (PT Sans 700 .95rem uppercase) and `.q-intro`
(muted; question 1's screen only) head it, the `?error=` alert under the title.
`.q-bar`: 4px, `--line` track, `--accent` fill, its width the step among the steps
asked (no numbers; `aria-hidden`; hidden without JS and in edit mode, and on the
guide's screen, `.at-guide`, `visibility: hidden`: its room kept).
**The first screen is the guide through the training** (29.10.2026, `#step-vodic`,
the `.vodic` box above): a step with no answer, its title in the question's h1
place, its button a `.q-next` that goes on to question 1, whose "Nazad" comes back
to it; the intro (`.at-start`) is question 1's. The form's `data-start` names the
step the page opens on: the guide, or with `?od=1` (the guide read: /vodic's
button, a refused submission) the first question asked. Without JS the guide
stands above the questions, in edit mode at the top of the stack (`.q-sum` between
it and question 1). Each question's
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
on the row (`.opts` / `.opt` and the scale below are base.html's since 30.10.2026,
when the online trening's finish screen asked its osvrt in them). **`.scale`** (a scale question: q5–q14 of the fifteen): ten `label.sc`, each a circle `span` (≤56px,
`aspect-ratio: 1`, hairline on `--surface`, 700 1rem tabular), chosen inverted like
a row; a 5 × 2 grid until its box (`.scale-box`, a query container) is 454px, ten in
a row from there (40px each at least); `.scale-ends` under it, muted .85rem, "1 = …"
left and "10 = …" right. **A free text** (a text question: where it hurts, a short note, since 27.10.2026 questions asked after the safety ones): a 128px textarea labelled by
the h1 (a `label` inside it). `.q-nav` closes a step: "Nazad" (`.act.act-quiet`, not
on the first until 29.10.2026, when the guide came before it) on the left, "Dalje" / "Spremi upitnik" (`.btn`) on the right; long
words wrap inside the pills. The last screen is `label.q-consent` (a row-like box,
22px checkbox, `accent-color`) and that nav. Without JS every step shows, stacked
with a hairline between them; in edit mode the same, the bar hidden and the pain
sentence previewed under the pain question (`.q-preview`, `.q-note`). A **multi**
(several options, 26.10.2026) is a choice's `.opts` rows around checkboxes
(`role="group"`), several inverted at once, and its step goes on with "Dalje",
which stays dimmed (.45, `aria-disabled="true"`, a press does nothing) until a
row is ticked. The questions are rows the gym owner edits (26.10.2026): in edit
mode each carries his controls (`.q-ed`, in the catalog above) and a hidden one
is dimmed; outside edit mode a hidden one is no step, nor is one a hidden question mutes (`.is-muted`; a client never gets its markup). A question asked only after an answer (27.10.2026) is a step like any other, skipped while that answer is not given (the script reads its `data-parent` and condition), and not counted in `.q-bar` until it is asked; edit mode indents it (`data-depth`, in the catalog above). A step keeps 96px of
`scroll-margin-top`, so a reload that lands on `#step-q<id>` clears the bar.

**The library of exercises (`vjezbe.html`, `vjezba.html`, 30.10.2026; Admin ▾ →
Vježbe).** The list: the page header, then `.ex-tools`, one wrapping row of the
search (`form.ex-search`, `role="search"`: a `type=search` input and a
`.btn-ghost.btn-sm` "Traži", `?q=`) and "+ Nova vježba" (`.btn.btn-sm`, the page's
one primary), `align-items: stretch` so the buttons are the input's height (one
footprint); with `q`, a muted "2 od 13 · prikaži sve" (`.tlink`). **The search filters
as it is typed** (23.11.2026; no new component, the same input and rows): the page's
script hides "Traži" (the input then fills the form) and, at each key, puts `hidden`
on the rows not every typed word is in (`qmtFold` over each row's `data-find`, "name ·
tags"); every row is on the page, `?q=` too, where the server hides the same ones. The
count line (`p.hint.ex-found`, its number `.ex-n`) is always rendered, `hidden` while the
box is empty; the none line (`p.ex-none`, its quote `.ex-q`) is the list's last child,
`hidden` unless nothing is left. The input is `autocomplete="off"`: the browser's own
dropdown of past entries hung over the rows. Under the tools row, 10px below it, the
tag chips (Forms, above; 23.11.2026), the list's width (860px). With rows hidden, the hairline is drawn
between two visible rows (`.ex-row:not([hidden]) ~ .ex-row:not([hidden])`), never
above the first one shown. Then ONE
`.card.ex-list` of rows, a hairline between them: each row an `a.ex-row`, the whole
row the tap target (52px at least, as the client's /treninzi cards are links
whole), in the Croatian alphabet's order (`models.alpha_key`): `.ex-name` (600), the
tags as `.ex-tag` chips (facts, not state: `--surface-2` with `--text`, 600 .74rem,
the karton's `.u-fact` values), and at the right end `.ex-meta` (muted .82rem):
"video ✓" in `--good` 600 (`.has`) or "bez videa", and "u N programa" ("u 1
programu", "ni u jednom programu"); on a phone it wraps under the name. Hover is a
4% `--text` wash, never a flood. None matching: `.ex-none` "Nijedna vježba ne
odgovara traženju „q”."; an empty library: `.card.ex-empty`, "Još nema vježbi." and
the button. **An exercise's page**: crumbs (Vježbe / its name), the h1, the lead
(where it is, "U 2 programa: A, B." in the hint's muted words, not links: the
accent is the actions'; "Još nije ni u jednom programu."; a new one: what to fill),
then `.card.ex-card` (640px) holding the one form: labelled fields (Naziv,
Upute, Što je jedno ponavljanje, Oznake (odvoji zarezom)) and **Zamjene za ovu
vježbu** ("Slične vježbe" until 4.11.2026, when a swap got a direction), a
`fieldset.ex-alts` (its legend in the label's look) with a muted hint ("Polaznik
smije odraditi označene vježbe umjesto ove. Da ova vježba zamijeni neku drugu, označi
je na stranici te vježbe."), the
`.alt-filter` search (rendered `hidden`, the script shows it and keeps the rows
whose name or tags hold what is typed, folded with `qmtFold` since 23.11.2026: "cuc"
finds "Čučanj"; a row it hides keeps its tick; Enter
there only filters: in the form, a phone keyboard's "Go" would save it half
typed) and
`.alt-list`, a 300px box that scrolls, of `label` rows (40px, a checkbox, the name
and its tags muted, then, on a ticked row whose reverse row exists too (a mutual pair), `.alt-back` "· u oba
smjera", muted as the tags and unbroken: text, not a control, an unticked row none (the line
under the box names what this one stands in for); the ticked ones first, each group in the alphabet's order; a ticked
row, a swap this one → that one, in `--accent-dim`), and under the box, when this one
stands in for any, `p.hint.alt-for` "Zamjena je za: A, B.", each name a `.tlink` to
its page (where that direction is ticked); then `.ex-actions`: "Spremi" (`.btn.btn-sm`; a new
one's "Odustani" `.btn-ghost.btn-sm` beside it). A refused save comes back as the
page, what was typed kept, its sentence in the page's own alert (the
`error_alert` block). For an existing exercise a second card, **Video**
(`section.ex-video`, base.html's rules since 30.10.2026, below): the clip
(`<video controls playsinline muted loop preload="metadata">`, the card's width,
at most 440px tall, letterboxed on black, `--r-md`), the file input labelled "Video (mp4, mov ili webm, do 95 MB)" ("Zamijeni
video …" with one) and the recording hint under it (`.ex-hint`), then "Dodaj video"
/ "Zamijeni video" (`.btn.btn-sm`) and "Ukloni video" (`.btn-ghost.btn-sm`, its
form named with `form=`, `data-confirm`) side by side, one footprint. Last
"Obriši vježbu" (`.btn-ghost` in the accent, its border too, as "Obriši cijeli
trening"; `data-confirm`: "Obrisati vježbu?", the text for one a programme holds
naming them as the lead does, three then " …", and saying the trainings stay
without it), never refused since 4.11.2026: deleted, it leaves every training that
held it, and the library's flash says how many ("… maknuta iz 4 treninga.").

**The online programmes' shared rules (base.html since 30.10.2026, when the
day editor and the day page needed vjezba.html's).** `.ex-card` (a 640px admin
card, 18px 20px, its `h2` 1.05rem, a resizable `textarea`), `.ex-hint` (a
field's hint under its input), `.ex-actions` (a wrapping row of pills, one
footprint), `.ex-video video` (the clip as it plays: the card's width, at most
440px tall, letterboxed on `#000`, `--r-md`: the one raw hex, the clip's box in
both themes) and `.ex-delete` ("Obriši …": `.btn-ghost` in the accent, its
border too). The editors' rows: `.it-row` (a `.card` row, 10px 14px 10px 18px,
a wrapping flex row, `scroll-margin-top: 90px` so `#dan-<id>` / `#stavka-<id>`
land clear of the pill), `.it-name` (the name, `--text` 700, a 32px link, the
accent on hover), `.it-note` (muted .85rem after it), `.it-end` (`margin-left:
auto`: one group at the right end, wrapping under the name whole on a phone),
`.it-video` ("video ✓" `.has` in `--good` 600, or "bez videa" muted) and
`.it-acts` (↑ / ↓ / ✕, `.btn-ghost.btn-sm`, a disabled one at .35).

**The programme editor (`trening_edit.html`).** The h1 "Uredi program" (a dvoranski
programme's followed by `.venue-chip` "dvoranski", 24.11.2026); its lead:
"Program ima treninge; svaki trening ima zagrijavanje, glavni dio A, B i C te istezanje, a
vježbe biraš iz baze vježbi." (A and B since 23.11.2026, C since 26.11.2026) (a `.tlink` to the library), since 24.11.2026 "Svaki
dio može biti kružni: vježbe idu jedna za drugom, s odmorom između krugova.", and "pogledaj kako
polaznik vidi →" (`.act.act-quiet`). The programme's form (`.card`, 640px: Tip programa,
Razina and since 24.11.2026 Vrsta, Online / Dvoranski, three selects in one grid,
`repeat(auto-fit, minmax(160px, 1fr))`, `gap: 0 12px`: a row where they fit, one under
the other on a phone, the `.field`s' 14px apart; staff's "Novi program" on /treninzi
the same three, Online chosen), then
**Treninzi** (30.10.2026; a day reads "Trening N" since 2.11.2026): a
`.card.it-row` per day, `id="dan-<id>"`: its label as `.it-name` (a link to the
day's editor),
`.it-note` "ponedjeljak · 7 vježbi" (no weekday: "7 vježbi"), then `.it-end`:
"Uredi" (`.btn-quiet.btn-sm`, the day's editor) and `.it-acts` ↑ / ↓ (each its
own small form, `smjer` gore / dolje; the first's ↑ and the last's ↓ disabled;
`aria-label` "Pomakni gore: Trening 1 · …") and ✕ (`data-confirm-title` "Obrisati
trening?", "„Trening 2 · Gornji dio” se briše s popisom vježbi; same vježbe ostaju u
bazi vježbi.", cta "Obriši trening"). Empty: "Program još nema treninga — dodaj
prvi." "+ Dodaj trening" (`form.days-add`, a `.btn.btn-sm`) under the rows, 14px;
"Obriši cijeli program" at the bottom ("„…” — briše se program s treninzima i
vježbama; …").

**The day editor (`trening_day_edit.html`, 30.10.2026).** Crumbs Treninzi / the
programme (its editor) / Trening N, the h1 "Trening N", the lead ("Naslov, preporučeni dan
u tjednu i uvod; ispod toga vježbe po dijelovima — …", since 24.11.2026 "Ponavljanja i
sekunde mogu zajedno: 5 ponavljanja po 30 s." after it and, after the rests' sentence,
"Svaki dio može biti kružni: vježbe idu jedna za drugom, s odmorom između krugova.", + "pogledaj kako polaznik
vidi →" to the day's page). Card 1, `.card.ex-card`: Naslov ("npr. Cijelo
tijelo"), Preporučeni dan (a select: "Bez preporuke", then the weekdays
capitalised), Uvod, Spremi (`.btn.btn-sm`). Card 2, **Uvodni video**: the
exercise page's video card (`section.ex-video`, `#video`) with its own hint first
("Kratko objašnjenje treninga — polaznik ga gleda prije prve vježbe."), the clip
(`controls playsinline preload="metadata"`, not muted: it speaks), the file input,
the iPhone hint, "Dodaj / Zamijeni video" and "Ukloni video" (`form=`, asks
first). Then **Vježbe**: each section (`SECTIONS`, in their order) an `h3.st-cap`
(PT Sans 700 .78rem, letter-spaced .14em, muted; `scroll-margin-top: 90px`, the anchor
`#dio-<key>`) and its rows, or a muted "Nema
vježbi." (`.st-none`). **Under each caption its "Kružno"** (24.11.2026, kružni trening):
`details.st-circ` (native: it opens without JS), its summary a pill stating the part's
state with a › that turns down when open (the player's swap summary's size: 32px, 5px
13px, 600 .8rem; 8px 15px on a coarse pointer): "Kružno: isključeno" muted on a
hairline (hover: `--text`, its border at 40%), or, `.on`, "Kružno · 3 kruga · odmor
između krugova 120 s" in `--accent-tint-ink` on `--accent-dim` with no border (the
pressed tag chip's pair, which a hover keeps: the part's state, not decoration). Open,
ONE `form.st-circ-form` in a hairline box (`--line`, `--r-md`, `--surface`, 12px 14px,
10px under the summary): `label.st-check` "Kružni dio" (a whole-row label, 44px, Inter
500 .92rem, its checkbox 20px in `--accent-fill`), then Krugova and "Odmor između
krugova (s)" side by side (two columns at every width below 600px, each control at its
field's bottom so a label that wraps keeps the two level; 40px inputs, 44px on a coarse
pointer) and Spremi (`.btn.btn-sm`) across both; from 600px three columns, the two and
Spremi on one line. A save's alert (`?dio=<key>`) stands between the caption and the
summary (`.st-sec > .st-alert`), the details open again after a refusal. In a circuit
part a muted `.hint.st-circ-hint` under the details (since 25.11.2026 "U kružnom dijelu
vježbe idu jedna za drugom, bez pauze: upiši ponavljanja ili sekunde i kilažu. Odmor je
nakon kruga."), and each row's form drops Serije, Odmor (s) and since 25.11.2026 Nakon
vježbe (s) (no pause between a circuit's exercises): the same grid, three fields fewer,
Dio | Ponavljanja, Sekunde | Kilaža (kg), Napomena, Spremi on a phone, its lines level at
360 and 390 px. Each part ends with **"+ Dodaj vježbu u ovaj dio"** (25.11.2026,
`a.act.st-add`, 10px under the rows or "Nema vježbi.": the part's quiet row action): a
link to the add card with this part chosen (`?dodaj=<key>#dodaj`), which the script
follows in place (the card's Dio set, the card scrolled to, the focus in the picker
with its list shut: the combobox's `focus()`, base.html). A row is `.card.it-row`, `id="stavka-<id>"`: line 1 the
exercise's `.it-name` (to its library page), `.it-video`, ↑ / ↓ (within its
section; disabled at the section's ends) / ✕ — buttons naming forms that stand
after the list (`form="st-gore-<id>"`, `st-dolje-`, `st-x-` with `data-confirm`
"Maknuti vježbu iz treninga?" / "„Goblet čučanj” izlazi iz ovog treninga; u bazi
vježbi ostaje." / "Makni"): a form holds no form; after a save (`?ok=` / `?error=` with `?stavka=<id>`, the row's id) the row carries the page's alert itself (`.alert.st-alert`, the row's width, above its form; the top prints none: a phone comes back scrolled to the row), a stavka that names no row leaving the alert at the top; line 2 the row's own `form.st-form`
(`flex: 1 0 100%`), a compact grid of labelled fields in the caption style:
Dio (a select), Serije, Ponavljanja, Sekunde, Kilaža (kg) (25.11.2026, the planned
weight: `inputmode=decimal`, `min` 0.5, `max` 500, `step` 0.5), Odmor (s), Nakon
vježbe (s) (`type=number`, `inputmode=numeric`, `min` / `max`), Napomena, Spremi
(`.btn.btn-sm`); two columns on a phone (Dio, Napomena and Spremi across both),
four from 600px (Dio and the dose on line 1, then the weight and the rests, the
note over two columns and Spremi);
every control 40px tall, 44px on a coarse pointer, so the grid is one
footprint. "Dodaj vježbu" (`form#dodaj.card.add-ex`): `.add-fields` (Vježba iz
baze, the combobox over the library's select, name · tags (Forms, above; 23.11.2026);
Dio, opening on Glavni dio A (four options since 23.11.2026: Glavni dio B after it; five since 26.11.2026, Glavni dio C after B, each as the day names it); one column on a phone, the combobox and a 180px Dio from
600px), the tag chips above them (Forms, above; 23.11.2026: a tap opens the combobox's list
filtered, under the input, so the chips stay in reach), since 25.11.2026 `.add-nums`
(Serije, Ponavljanja, Sekunde, Kilaža (kg), all optional: the row form's grid and
look, two columns on a phone, four from 600px, 40px controls, 44px on a coarse
pointer, 16px over the buttons), and `.add-row` (Dodaj `.btn.btn-sm`, "Nova vježba →"
`.btn-ghost.btn-sm`, `natrag=` this editor). After an add (`?dodaj=<part>&ok=…`) the
card's first line is the page's ok alert, "Dodano u Glavni dio A: Sklekovi." (a
refusal its error alert; the page's top none), its Dio as it was and the focus in the
picker (at the load: the browser's move to `#dodaj` takes a focus given before it).
Last "Obriši trening" (`form.ex-delete`, asks first).
**A part's own name (26.11.2026, build 2; the owner: "Lets have Glavni dio A, B and C but
lets also allow Amir to rename them.").** Five parts since that day (Glavni dio C after
B). Under each caption `.st-tools`, a wrapping flex row (8px gap, the player's `.pl-more`
idiom): "Kružno" and **"Preimenuj"**, a native `details.st-circ.st-name` in the "Kružno"
pill's look (32px, 5px 13px, 600 .8rem, a › that turns; 8px 15px on a coarse pointer).
The one open takes the row's width (`flex: 1 0 100%`), its form under its own pill; a
closed one is its pill alone (its form `display: none`: Chromium lays a closed
`<details>`' content out at the pill's width when it is measured, which the audit read as
a 5px overflow). Open, ONE `form.st-name-form` in the "Kružno" form's hairline box
(`--line`, `--r-md`, `--surface`, 12px 14px, 10px under the pill): "Naziv dijela" (a 40px
text input, 44px on a coarse pointer, maxlength 60, its placeholder the default name, its
value the day's) and Spremi (`.btn.btn-sm`), one under the other on a phone (Spremi the
box's width), side by side from 600px (`minmax(0, 1fr) auto`, Spremi 120px at least). Its
save answers in the part as "Kružno"'s does (`?dio=<key>&naziv=1`; a refusal opens
"Preimenuj" again, not "Kružno"). A renamed part's caption (`h3.st-cap`) is its name, then
the default in brackets in `.st-cap-def` (Inter 500 .8rem, its own case, no letter-spacing:
"KRUG 1 (Glavni dio A)"), so Amir sees which of the five it is; everywhere else, the Dio
options of that day's forms among them, the name alone.
**A dvoranski day's empty slots (26.11.2026, build 2: Amir's templates).** A slot's row is
an `.it-row` whose name is `span.it-slot-name` ("Prazno mjesto", 700, no link, no hover,
32px tall) with its hint after it in `.it-note` ("· čučanj", muted .85rem); no `.it-video`;
↑ / ↓ / ✕ as any row (`aria-label` "Pomakni gore: Prazno mjesto · čučanj"; ✕ asks
"Maknuti prazno mjesto?" / "Prazno mjesto „čučanj” izlazi iz ovog treninga." / "Makni").
Its form is the row form plus "Natuknica" (`.st-hint`, maxlength 80), which lies as the
note does (across both columns on a phone, two of four from 600px, before Napomena).
Under the form **"Popuni vježbom"**: `details.st-circ.st-fill` (the "Kružno" pill, the
row's width, 4px above), its `form.st-fill-form` the rename form's box and grid:
"Vježba iz baze", the library's combobox (base.html's `qmtCombobox` in its rows mode, the
rows the add card's select's options: the library on the page once; its value a hidden
`exercise_id`; the input 40px, 44px on a coarse pointer), and "Postavi" (`.btn.btn-sm`).
Rendered `hidden` and shown by the script, which types the slot's hint into the input
(`data-hint`) and gives it the focus when the details opens, so its list is already
narrowed ("čučanj": the squats); its list lies over the rows below (z-index 5). Without
JS nothing fills a slot. The add card's second way (dvoranski only), `.add-slot` under a
hairline (16px above and inside): "Natuknica (neobavezno)" (a 40px text input, 44px
coarse) over its hint (`.ex-hint`, "npr. čučanj, potisak — sužava popis vježbi kad se
mjesto popunjava") and "Dodaj prazno mjesto" (`.btn.btn-sm`, `formaction` →
`…/mjesto`, `formnovalidate`: the card's Dio and numbers posted with it; Enter in its
field presses it, never the card's "Dodaj"). With an empty library the card keeps its Dio,
its numbers and this way.

**The programme page (`trening_view.html`) and the day page (`trening_day.html`,
30.10.2026).** The programme: crumbs, the h1 (a dvoranski programme's, for staff, its
title then `.venue-chip` "dvoranski", 24.11.2026), "2 treninga" (`.hint`), its intro, the
trainer's "Uredi program" (`.btn-quiet.btn-sm`), then its days as `.card.day-card`
links (the client's /treninzi cards' look, 52px at least, padding 16px 20px, the
whole card one link): the label in 700 over a muted "Preporučeno: ponedjeljak · 7
vježbi", the → in the accent at the right (`aria-hidden`); 640px. The day: the
normal layout, the h1 the day's label, the lead "Preporučeno: ponedjeljak · 7
vježbi", then a 640px column (`.day-body`): the intro (`pre-line`), the trainer's
"Uredi trening" (`.btn-quiet.btn-sm`), the intro video in `.ex-video`'s box under a
muted "Uvodni video — pogledaj ga prije treninga.", and the list, Shape's Gym
Program list in QMT's tokens: per section that holds an item an `h2.dx-cap`
(PT Sans 700 .78rem uppercase, letter-spaced .14em, `--muted`, 26px above), its
items in `.dx-list` (10px apart), each a `details.card.ex`: the `<summary>` is the
row (the native marker hidden, 56px at least, 12px 14px 12px 18px; a 4% `--text`
wash on hover, a 2px inset accent ring on focus): `.dx-n` "Vježba n" (Inter 600
.72rem uppercase, .1em, muted; counted across the day), `.dx-line` the name
(`.dx-name`, 700) and at its right the dose (`.dx-dose`, 700, tabular-nums,
nowrap), `.dx-sub` one muted .85rem line ("Odmor između serija: 60 s · 8 kg",
each part only when set), and `.dx-go`, a 32px `--surface-2` circle with ▷ that
turns 90° (points down) on `details[open]`. Open, `.dx-body` (also `.ex-video`):
the clip (`controls playsinline preload="none"`) or a muted "Vježba još nema
videa.", "Jedno ponavljanje: …" and the instructions (`pre-line`). Native
`<details>`: it opens without JS. A day with no item says "Trening još nema vježbi."
(the trainer: "… — dodaj ih u uređivanju."). A dvoranski day's slot (26.11.2026,
staff's: no client reaches such a day) is `div.card.dx-slot`, a muted row in the list's
place: no fill, no shadow, a dashed `--line` border, `--muted` text, 56px at least, 12px
14px 12px 18px; its `.dx-line` "Prazno mjesto · čučanj" (the words the copy slot
`dan.slot`, the hint after them) and its dose at the right, `.dx-sub` its rests and note
as a row's; no `<details>`, no "Vježba n" (the exercises are counted alone). The lead
and the programme page's day card say the slots after the count, "0 vježbi · 3 prazna
mjesta". Each caption says the part as the day names it (`part_label`, "KRUG 1").
The row's words (`.dx-cap`,
`.dx-list`, `.dx-n`, `.dx-line`, `.dx-name`, `.dx-dose`, `.dx-sub`) are base.html's
since 30.10.2026: the player's list is the same rows. **A circuit part** (24.11.2026,
kružni trening): its caption followed by `p.dx-circ`, one muted line in the `.dx-sub`
size (.85rem), pulled 6px up to the caption, 10px above the list ("Kružno · 3 kruga ·
odmor između krugova 120 s", the rest only when set); its rows the dose of a round
("10 ponavljanja", "40 s", "5 × 30 s", "10 ponavljanja · 20 kg") and in `.dx-sub` the
note alone (since 25.11.2026: no pause between a circuit's exercises, no rest of an
exercise's applies there). Any dose carries the planned weight after a middle dot
(25.11.2026, "3 × 10 · 20 kg"). An exercise the client rated ends its Povijest's
Serije with "težina 8/10" (the karton's too). A day with one says "· kružni trening" in its muted
lines (the lead under the h1, the programme page's day card). While a pass is open a
circuit row's dose starts with `.dx-ok` once every round is saved, and with
`.dx-rounds` "2/3" (base.html: `--muted` in the dose's tabular 700; `role="img"`,
`aria-label` "spremljeno 2 od 3 kruga") while some are.
**The way into the player (30.10.2026, stage 3).** A day card's muted line ends
with the viewer's state ("… · odrađen 2×", "… · u tijeku"; nothing for a day never
done). The day's page: under the lead `.dx-state`, one muted 600 .92rem line
("Još nije odrađen." / "Odrađen 2× · zadnji put 12.11." / "U tijeku — nastavi
gdje si stao/la."), pulled 12px up into the lead's room; then `.dx-start`, a
wrapping row: "Kreni" / "Nastavi" (the page's one `.btn`, its own form
`form.go`, the column's width below 600px) and, while a pass is open, "Odbaci
započeti trening" (`.act.act-quiet`, `data-confirm`); 24px under it the
`.day-body`. A day with no item has neither (the state line stays when it has
passes). While a pass is open a saved row's `.dx-dose` starts with `.dx-ok`, a
`--good` ✓ (`role="img"`, `aria-label="spremljeno"`). **Povijest** at the
bottom (`.dx-hist`, 34px above): an `h2.dx-cap`, then an `ol.hist` of
`.card.hist-row` (12px 16px, 10px apart): `.hist-line` (600, tabular: "12.11. ·
6/8 vježbi · 38 min · napor 7 · dobro"), `.hist-note` (the comment, muted .9rem,
`pre-line`) and `details.sets`.
**`details.sets`** (base.html, 30.10.2026: the day's Povijest, the karton's
rows, the client's as the trainer's since 23.11.2026, a gym training's exercise
log's too): a pass's sets folded under "Serije": the summary a 32px muted row (600
.85rem) with a › that turns down when open, then a line per exercise
("<strong>Goblet čučanj:</strong> 10 × 20 kg · 10 × 20 kg", .88rem, tabular),
each set a `.set` that never breaks across lines.

**The player (`trening_player.html`) and the finish screen (`trening_kraj.html`,
30.10.2026).** Shape's Gym Program training page in QMT's tokens, the one-task
layout (`solo_page = not can_edit_copy`: a member's; staff, the trainer and the owner whatever his flag, keep their bar). `.pl`: 640px, centred; from 1000px
1044px with `.pl-grid`, two columns (`minmax(0, 640px) minmax(0, 380px)`, 24px
apart: the list keeps 380px, the player takes the rest), the dock hidden. On top
`.pl-segs`: a 4px segment per step (an exercise; in a circuit part one round of it,
24.11.2026), 4px apart in a rounded track, `.done`
`--accent`, `.cur` `--text` at 60%, the rest `--surface-2`; past 40 steps (a circuit's
rounds multiply them) `.pl-track` instead: one track, the segments' 4px and 999px radius,
`--surface-2`, its span an `--accent` fill as wide as the share of the steps saved (an
inline `width`), `aria-hidden` as the segments; under it `.pl-line`:
"← Natrag" (`.act.act-quiet`) · `.pl-timer` (a `--surface-2` pill, a 14px clock,
600 .82rem tabular "0:18"; rendered `hidden`, the script counts from
`data-started`) · "Završi trening" (`.act.pl-end`, at the right). `.pl-stage`: the
clip in `.ex-video`'s black box (`--r-lg`, at most `min(62vh, 560px)` tall), or
`.empty` (`--surface-2`, 120px, the muted sentence); `.pl-nav` ‹ › 40px round at
its edges (`--surface` at 90% with a hairline and the shadow, `--text`), links;
a 60px sideways swipe on the stage or the card does the same (the script; not
from inside the form, the swap list or "Kako se izvodi"). `.card.pl-card` (18px
16px, 22px 24px from 600px): `.pl-eyebrow` "TRENUTNA VJEŽBA" (700 .74rem, .16em,
muted) with `.pl-chip` "3/8" (`--surface-2`; k of the day's steps), on a circuit's
step `.pl-round` "Krug 2 od 3" after it (24.11.2026: a pill in `--accent-dim` with
`--accent-tint-ink`, the pressed chip's pair, PT Sans 700 .78rem capitals, .06em, never
broken; at 360px it wraps under the kicker, the eyebrow being a wrapping row) and
`.pl-saved` "✓ Spremljeno"
(`--good`), `h1.pl-name` (`clamp(1.35rem, 5vw, 1.9rem)`), `.pl-for` "Zamjena za:
…" (muted), the alert, `.pl-dose` (700 1.05rem), since 25.11.2026 **`.pl-next`**, the line for the next time
(2px under the dose, `--muted` .88rem, the `.pl-sub` lines' look, wrapping anywhere;
only when the client rated the exercise last time: "Prošli put (23.11.): 10 × 20 kg,
težina 5 — malo više: 21 kg." / "…, težina 8 — ostaje isto." / "…, težina 9 — malo
lakše: 18 kg."), `.pl-sub` lines (rest, note),
`details.pl-how` "Kako se izvodi" (a 32px summary, a › that turns). The set log
`form.pl-log`: `table.pl-sets` (base.html's since 23.11.2026: the karton's exercise log printed it until 26.11.2026, the gym training's cards since, with the ✓ column and the rating, `.pl-done` / `.pl-rate`, base.html's too; rows 8px apart; `thead` SET · PON. · KG (the item's fields, `db.set_fields`, in the order reps, kg, seconds: a timed exercise's SET · SEK., and since 24.11.2026 one that asks reps and seconds SET · PON. · SEK., `reps_n` / `sec_n` prefilled with the plan's two, no KG column; the same widths: two value columns or one), 700
.72rem muted, the value columns centred; `tbody th` the set's number, 700 1rem,
`tr.extra`'s muted with `.pl-x` "dodatna serija" under it; inputs 44px,
centred, 600 tabular), then `.pl-foot`: "+" (`.btn-ghost.pl-add`, 40px round, at
the right; rendered `hidden`, the script's; it goes at 20 rows, `db.MAX_SETS`, 12
until 26.11.2026, as the karton's "+ serija" does), since 25.11.2026 **`.pl-rate`, the
rating** (the foot's width, 4px more above it): `.pl-rate-h` "Koliko je bilo teško?"
(Inter 600 .9rem `--text`) with `.pl-opt` "(neobavezno)" (500 .8rem muted), 10px over
the finish screen's `.scale-box` / `.scale` of ten `label.sc` radios (`effort`, none
chosen; `role="radiogroup"` named by the question), their circles at 36px (.92rem),
40px on a coarse pointer, five and five where ten do not fit (the scale's container
query); then "Spremi" (`.btn.pl-save`, the card's width on a phone, 200px from
600px). **The ✓ column** (30.10.2026): the
log's last, SET · PON. · KG · ✓ (SET · SEK. · ✓, SET · PON. · SEK. · ✓), its `.pl-tick` cells rendered
`hidden` (the script's, as "+"), as narrow as their button: `button.pl-done`, a
44px circle (`--surface`, a 1px `--line` hairline, a muted ✓, 700 1.05rem),
`aria-pressed`, "Serija n odrađena"; hover `--surface-2`; pressed `--good-fill`
under `--good-ink` (hover `--good-strong`), its row `tr.is-done`, the set's number
`--good`, the inputs as they were. The header's ✓ is `aria-hidden` beside
`.pl-sr` "Odrađena serija", screen-reader text that is NOT the usual 1px box (its
text overflows that box, which the audit's element-overflow check fails): the
text at its own width, `clip-path: inset(50%)`, set against its cell's right edge
(the `th` is `position: relative`). **A circuit's round** (25.11.2026, kružni trening; from 24.11.2026 a step per exercise
per round, one row of `.pl-sets`, gone) is one screen, the player's layout with no
`.pl-stage` (no clip box, so no ‹ ›): `.card.pl-card.cr-card`, its `.pl-eyebrow`
"KRUŽNI DIO" with `.pl-chip` "2/5" and `.pl-round` "Krug 1 od 3" (`.pl-saved` once
saved), `h1.pl-name` the part's name ("Glavni dio A"), `.cr-intro` one muted .88rem
line ("Vježbe idu jedna za drugom, bez pauze. Odmor nakon kruga: 120 s."), the alert,
then `.cr-rows` (14px under, 10px apart), a `.cr-row` per exercise: a hairline box
(`--line`, `--r-md`, `--surface`, 4px 14px 12px), its name the summary of a native
`details.cr-ex` (700, 40px tall, 44px on a coarse pointer, a muted › that turns down when
open, a 2px accent ring on focus; open, `.cr-body.ex-video`: the clip `preload="none"` or
"Vježba još nema videa.", "Jedno ponavljanje: …", the instructions, .92rem), `.cr-dose`
lines (muted .88rem tabular: the dose of a round with its weight and, after a rating,
the word for the next time, "10 ponavljanja · 16 kg · malo više"; the note), and
`.cr-in`, two columns 10px apart, each a small label (the set log's header words: PON.,
KG, SEK.; 700 .72rem .12em, the global label's uppercase muted) over a 44px centred 600
tabular input (one field: its column alone), named for a screen reader by the
exercise's name and the label (`aria-labelledby`). Then `.pl-foot` (14px under) with the
round's `.pl-rate` ("Koliko je bio težak ovaj krug?") and ONE `.btn.pl-save` "Krug 1
odrađen" ("Krug 3 odrađen — završi" on the day's last step), no "+", no ✓, no swap.
`.pl-more`: "Preskoči →"
(`.act.act-quiet`) and `details.swap` (its summary the same quiet pill "⇄
Zamijeni vježbu"; open, it takes the line: `.swap-h` "Slične vježbe", `.swap-row`s
(a hairline row, the name 600 and `.swap-tags` muted, an `.act` ⇄), "Vrati …"
first when swapped). `aside.pl-side#popis`: `h2` "Vježbe", the sections'
`h3.dx-cap` (a circuit part's "Glavni dio A · kružno · 3 kruga", 24.11.2026), `ol.dx-list` of `a.card.pl-row` (56px, the day page's row words; the
current one `.is-cur`, a 2px inset `--accent` ring and `aria-current="step"`: the
exercise on screen, on a round's screen every exercise of the round; a
swapped one's name with `.pl-swapped` "(zamjena)" muted; a saved one `.dx-ok`, a
circuit's once every round is, `.dx-rounds` "2/3" while some are; each a link to its
first step not saved, a circuit's exercise its part's first round not saved; a
circuit's rows the dose of a round and the note alone).
`.pl-dock` (phones): a fixed dark pill, the topbar's glass (theme-free), 48px,
700 .9rem tabular "Vježbe · 3/8 ✓" (by exercise) → `#popis`, centred 12px over
`env(safe-area-inset-bottom)`, 70px when staff's ✎ pill is on the page; `.pl`
keeps 56px under it. **`.pl-rest`, the rest bar** (30.10.2026; the rest between
sets after a ✓, the rest between exercises on the next screen; since 26.11.2026
`_rest_bar.html`, its look base.html's and its script `window.qmtRest`, `begin` /
`stop` / `unlock`, shared with the gym training's page, where a ✓ starts it with
the exercise's Pauza): `role="timer"`,
rendered `hidden`, shown by the script for a rest; fixed at the bottom at every
width in the dock's place and glass (theme-free: `rgba(22, 22, 24, .86)`, the
hairline, the shadow, the 14px blur; 12px over `env(safe-area-inset-bottom)`,
70px with staff's ✎ pill), 16px from the screen's edges, at most 640px, centred,
64px, `--r-lg`; inside, 14px apart: `.pl-rest-n` (`.pl-rest-h` "ODMOR", at zero
"KRENI": the set log's header words, 700 .72rem .12em uppercase, white at 62%;
over `.pl-rest-t`, the countdown "0:45": Inter 800 1.4rem, tabular, white), the
track `.pl-rest-track` (4px, white at 18%, its `.pl-rest-fill` `--accent`, scaled
to the rest left) and "Preskoči odmor" (`.pl-rest-skip`; not "Preskoči", which
under Spremi skips the exercise: a white pill, `rgb(22, 22,
24)` text, 700 .88rem, 40px, 44px on a coarse pointer; hover white at 86%). While
it shows the dock is hidden and `body.has-rest` gives each page's column room
under it: the player's `.pl` 92px (150px with the ✎ pill), the gym training's
`main` 100px (150px). **The finish screen** `.kr` (640px, centred):
`.kr-eyebrow` "TRENING ODRAĐEN", the day's label as the h1, `.kr-sum` (muted 600
tabular "6 od 8 vježbi · 38 min"), the alert, then the osvrt: three `.kr-field`s
26px apart, each under an `h2.dx-cap` (Napor: the upitnik's `.scale-box` /
`.scale` of ten `label.sc` radios, required, and `.scale-ends` "1 = lagano" /
"10 = maksimalno"; Osjećaj "(neobavezno)": `.opts` of three `label.opt` radios;
Komentar "(neobavezno)": a 96px textarea), "Spremi trening" (`.btn`, the
column's width below 600px), and `.kr-more`: "Natrag na vježbe"
(`.act.act-quiet`) and "Odbaci trening" (`.act.act-quiet` in `--accent`,
`data-confirm`).
**`#leaveDlg`, leaving a pass asks** (`_pass_leave.html`, 31.10.2026; the owner:
leaving the training asks "if he wants to finish the training and then he
decides"): on the player and the finish screen, at the end of their content.
The `.fb-modal` idiom: `.fb-box`, the ✕ a `method="dialog"` `.fb-x` form,
`h2` "Završiti trening?", `.fb-lead` the page's sentence, `p.fb-note#leaveErr`
in `--accent` ("Nije uspjelo — pokušaj ponovno.", hidden until a discard
fails), `.fb-actions` with two buttons: "Odbaci trening" (`.btn-ghost.btn-sm`)
and the primary last (`.btn.btn-sm`, `autofocus`): "Završi trening" (→ the
finish screen) on the player, "Natrag na osvrt" (closes it on the first napor
button) on the finish screen. 358px wide at 390px, the two buttons on one row
there and at 360px (37px tall on a coarse pointer: `.btn-sm`'s growth; the ✕
fbPrompt's, 32 × 29). Opened by the page's script (capture-phase listeners)
for a link or a form that leaves the pass, never for its exercises, `…/kraj`
or `…/odustani`; ✕, Escape and the backdrop close it, nothing more.
**A stale pass** (31.10.2026, no activity for `PASS_STALE_HOURS`): the finish
screen's `.kr-eyebrow` says "NEDOVRŠEN TRENING", `p.kr-stale` (6px under
`.kr-sum`, muted .92rem) says why it ends there, and `.kr-more` holds "Odbaci
trening" alone; the day page's `.dx-state` says "Nedovršen trening od jučer (6
od 8 vježbi) — nastavak nije moguć: završi ga ili ga odbaci." and `.dx-start`
holds `div.go` with an `a.btn` "Završi trening" (→ `…/kraj`; the form's place
and width) and "Odbaci započeti trening" beside it; the programme's day card
ends "· nedovršen".

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
in one wrapping flex row (the month note's idiom, 24px under the grid). A
week with termini after a running plan's dospijeće gets the same line
(29.10.2026): "Članarina vrijedi do 8.5. — za kasnije termine produlji
članarinu." with "Moja članarina →". A client's week past the booking
window shows no termin, only the `.hint` "Termini se objavljuju 4 tjedna
unaprijed." in the empty week's place, and his "idući tjedan →" is not on
the window's last week.
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
