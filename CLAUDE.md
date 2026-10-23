# CLAUDE.md

Guidance for working in this repo. Read this before making changes.

## What this is

**QMT** — booking + membership app for Quality Movement Training (a Croatian
training/rehab studio, run by the owner's friend). Clients reserve spots in the weekly
timetable, follow online programmes, and keep a personal karton; the trainer manages the
timetable, memberships and content. Croatian UI throughout. FastAPI + Jinja2 + Postgres +
Alembic on Railway — deliberately the **same stack and conventions as `../macro_tracker`
(mojimakrosi.com)**, its sibling repo.

**Relationship to mojimakrosi:** two separate entities — separate repo, DB, deploy,
domain — but identical auth shape (email+password, signed-cookie session, allowlist
sign-up) and conventions, so a future merge stays cheap. Nothing here may import from
macro_tracker or touch its DB.

**Who is who:** `OWNER_EMAIL` (tvrtko.doresic@gmail.com) is the app owner — permanently,
by env var, never handed over in-app; only the owner manages roles and sees /statistika.
The studio account (qualitymovementtraining@gmail.com) is granted `is_trainer` on
/korisnici and runs the gym day to day.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
createdb qmt && alembic upgrade head       # schema (Alembic = source of truth)
python scripts/seed_demo.py                # dev RESET: users, timetable, plans, content
python serve.py [--reload] [--port 8100]   # 8100 — 8000 is mojimakrosi's local port

createdb qmt_test                          # once
pytest -q                                  # 180 tests, must stay green
```

Demo logins: `trener@qmt.local/trener123` (trainer **and** owner locally, via
`OWNER_EMAIL` in `.env`), `ivan@qmt.local/lozinka123` (has grupni + individualni +
online plans, online on the QMove PRO tier, filled upitnik, diary entries, one
feedback prompt pending),
`ana@qmt.local`, `sara@qmt.local` (deliberately **no plan** — demos the booking gate),
all `lozinka123`.

Prod test aliases already on the allowlist: `tvrtko.doresic+qmt1@gmail.com` (and
`+qmt2`, `+qmt3`) — Gmail delivers them to the owner's inbox, so the verify-email
round trip is testable. Prod demo clients: `*.demo@example.com` / `demo12345`.

### Deployment (Scaleway)

See **DEPLOY.md** and **../webhost/README.md**. One Scaleway instance runs QMT and
mojimakrosi, the way the trader dashboard runs (`../webhost/`, its own repo beside this one, for both:
Terraform + cloud-init, Docker Compose with Postgres 18, Caddy behind Cloudflare,
nightly dumps to Object Storage). Dockerfile → `start.sh` runs `alembic upgrade head`
then uvicorn; `/healthz` is the healthcheck. A deploy is `../webhost/deploy.sh <ip> qmt`
from the laptop (refuses a dirty tree, waits for healthy, rolls back to the previous
image); a push deploys nothing. **Not live yet** (23.10.2026: the infra is a draft
awaiting review): until the cutover, prod is still Railway, where pushing to `master`
auto-deploys and the Railway CLI on the owner's machine reads config (`railway
variables --kv`).

## Pages

| Route | Who | What |
|---|---|---|
| `/` | public | Landing: hero = kicker, headline, then **`#aktualno`**: the owner's announcement cards for the month, any number up to 8, rows of the `announcements` table in creation order (chip, title, when, a few lines, a grey "Javi nam se" → `/#kontakt`; added in edit mode with "+ Dodaj najavu" (placeholder texts to retype) and deleted with each card's "Obriši najavu" (two taps); each switched off by the editor, gone when all are; each optionally over a photo of the owner's (uploaded in edit mode, shrunk to a 1600px JPEG, stored like other media, in R2 on prod), then Shape's photo card: glass chip on top, white type and a white pill at the bottom): one card per view at every width, as wide as the row (the screen less the gutter on a phone, the 1100px column on a desktop), dots under it, moving on by itself every 5 s (quiet while touched, hovered or focused, off-screen, in a hidden tab, or under reduced motion); edit mode stacks them, one under the other; then the photo card that links to the offer; no lead, no button, no note since 16.10.2026 (the owner's call: the announcements are the first thing on the page). **The offer (`#usluge`) is three tiers of the online plan** (QMove START / PRO, featured / ELITE; no MojiMakrosi add-on line since 21.10.2026, the owner: "lets leave out the moji makrosi out of here completely"; its amounts live on in prehrana's hint on `/moja-clanarina`): tier 1's monthly price is the online plan's own, every other price (tiers 2–3 monthly, all three yearly) is editable text until a plan exists; a **Mjesečno / Godišnje** switch under the cards shows one price per card (per page view, yearly first, monthly on a press; yearly without JS); on phones (<900px) the tiers are a swipe carousel (cards 92% wide, a sliver of the next) with three dots that opens on PRO (the featured middle card: START a swipe to the left, ELITE to the right). Below it, quieter, **the gym (`#dvorana`)**: its cards are rows of the `gym_cards` table since 20.10.2026, in creation order (Dvorana and Individualno, the first two, then whatever the gym owner adds: "Pilates za cure"), added ("+ Dodaj karticu"), hidden (its switch) and deleted ("Obriši karticu", two taps) in edit mode like the announcements, up to 8; a visitor gets no section when none is shown. No MojiMakrosi add-on line since 20.10.2026. A card with plans is priced by its first plan's slots (`price.<plan>.*`, the ones `/moja-clanarina` prints: edit one, both change; its yearly price too since 21.10.2026, the plan's `price.<plan>.year_amount` / `.year_unit`, into which migration `6e2b9d41c7a3` carried the row's typed one) and names its other plans' prices in a muted line under its own (Individualno: semi-individual and rehab; the words before each price are slots since 20.10.2026, `price.poluindividualni.word` / `price.rehabilitacija.word`, the number stays the plan's amount slot, its default back when emptied); a card without plans (every one he adds) is his text alone, its own monthly price, and "Javi nam se →" → `#kontakt` for everyone. Tiers too (a monthly and an editable yearly price: a card without plans its row's own) with their own switch, its own choice since 20.10.2026 (the owner: "unlink them"): it opens on Mjesečno, the monthly price (monthly without JS too), and a press flips the gym's cards only, as the tiers' switch flips the tiers only; from 900px as many columns as cards, up to three (a fourth wraps), on phones a swipe row. Gallery from `static/gallery/`; contact, its opening hours rows the editor empties, removes and adds (`info.hours.rows`, a `RowsSlot`, 20.10.2026). Extra lines (20.10.2026): plain lines of text the editor adds with "+ Dodaj tekst" under the headline, under every card's bullets, under the hours and under the contact rows (`*.extra`, `c.lines`), none until he does. A card's button follows the visitor: owner of the plan → into the app (a QMove card: only the owner of its tier, `Membership.tier`, since 20.10.2026; the other two say "Odaberi plan" to him), member → "Odaberi plan" → that plan's card on `/moja-clanarina`, guest → "Registriraj se" when signup is open, else "Javi nam se" → `#kontakt` (a gym card without plans: "Javi nam se" for everyone) |
| `/moja-clanarina` | client | **"Moja članarina"** (18.10.2026, Shape Club's billing page in QMT's look): **members only** (guests are sent to log in; the trainer and the owner, who manage members on `/clanarine`, see it with no plans of their own: it is where its texts are edited), where plans are seen, bought and managed; the public price list is the landing's offer. **Tvoji planovi**: a card per plan held, active or lapsed (active first, `PLAN_TYPES` order): PAKET + name, a chip that says the state (aktivna / dospijeva za N dana, N ≤ 7 to dospijeće / istekla / otkazana · vrijedi do kraja), the facts (cijena, uplaćeno, sljedeća uplata, vrijedi do; a tiered grupni's paket and "n od N u ovom ciklusu"; the online plan's paket, its QMove tier's name, printed through the landing card's title slot, `offer.online*.title`, so a rename shows on both pages), one sentence on how and by when it is paid, and only what fits how it is paid: the plan's door (`PLAN_LINKS`) while it runs; a card subscriber's portal ("Kartica, računi, otkazivanje") and tier switch; a cash member's "Prebaci na karticu" once Stripe is configured (nothing more without it). **Dodaj plan**, the plans not held, in two groups since 21.10.2026 (the owner: "every tab is one big text cell except the number i.e. price which is connected to the front page"; "split into the QMOVE online trainings with 'godišnje' as default and everything else in the gym separate with 'mjesečni' as default"): **Online treninzi** (`clanarina.h.online`), the landing's three QMove tiers (none while online is held), its Mjesečno / Godišnje switch opening on Godišnje; then **Treninzi u dvorani** (`clanarina.h.gym`), the other plans not held in `PLAN_TYPES` order, its switch opening on Mjesečno (each group a `[data-period-group]` with its own switch, `_period.html`, which base.html's script flips for its cards only; a group with no card left is not on the page). A card is its name (a tier's its landing card's title slot, a plan's `plan.<plan>.name`), its monthly and yearly price lines (the landing's own slots: START's `price.online.amount` / `.unit`, PRO's and ELITE's `offer.online2/3.price` / `.unit`, every tier's `offer.online*.year_price` / `.year_unit`, printed as typed; a plan's `price.<plan>.amount` / `.unit` and `.year_amount` / `.year_unit`, " €" after a number), ONE text (`cjenik.<plan>.text`, `cjenik.online.<tier>.text`, its default the lines the old pieces said: the lead, the note, "Za upis se javi treneru u dvorani.", "Mjesečno, otkazivo bilo kad. Ili gotovinom u dvorani."; migration `6e2b9d41c7a3` carried what was edited) and "Pretplati se karticom" → Stripe Checkout where sellable, nothing otherwise (a tier's form names its tier, which `/placanje/online` ignores until online has a Price per tier). QMove START carries `#plan-online` (PRO and ELITE `plan-online-pro` / `-elite`). **Računi**: the `payments` ledger, newest first (date, plan with the method under it, amount when known), plus the portal's invoices for a subscriber. Price lines are the `_plan_price.html` macros (`pp.price`, a plan held's Cijena `pp.plan_price`; no note under a price since 21.10.2026; prehrana's hint: the two `addon.*` amounts); Stripe's amounts show only inside the forms that charge them, a checkout form's tier picker and a subscriber's tier switch. **Editable in place** (trainer/owner): the lead (`cjenik.hint`) and each Dodaj plan card's one text (`cjenik.<plan>.text`, `cjenik.online.<tier>.text`), every price (`price.<plan>.*`, the tiers' `offer.online*.*`, `addon.*`: the landing's own slots), and since 18.10.2026 the headings (`clanarina.h.*`, the two groups' since 21.10.2026), the plans' names on its cards (`plan.<plan>.name`, this page's own; a tier's is its landing title), the no-plan card (`clanarina.none.*`; an editor holds no plans, so he gets it as a preview under "Ovo vidi član bez članarine:") and the empty ledger's line (`clanarina.bills.empty`). The line under a lapsed plan's "Pretplati se karticom" was `clanarina.card_hint` until 21.10.2026: fixed text since, its last default. `plan.online.name`, a held online card's heading, is on no page an editor opens since then (open question). Not the sentences built around a date or a number (the status box, the chips, the facts) or the ledger's headers. **`/cjenik`** (the old price list; the reminder email still links it) redirects here, query and `#plan-<key>` kept |
| `/raspored` | client | Week calendar, booking, "Moje rezervacije" as day columns, each booking with a ✕ that asks before it cancels; cancelling is allowed until 12 h before the termin, `CANCEL_CUTOFF_HOURS`. The plans are `/moja-clanarina`'s (the "Moja članarina" block that listed them here went 18.10.2026): a client with no plan running, a lapsed one's too, gets only the booking gate's line under the termini, "Nemaš aktivnu članarinu — bez nje rezervacija nije moguća." with "Pogledaj cjenik →". After booking a weekly slot the ok alert offers "Isti termin svaki tjedan do …" → `POST /book/{id}/series` books that slot for the rest of the paid period. A client's **"Tvoj sljedeći termin"** card (the soonest booking, with its ✕) sits right under the week's head at every width. **On phones (≤860px) one day at a time** (17.10.2026, so nobody scrolls the whole week): a day strip (Shape's "Moj napredak" week: pon 12 … ned 18, the chosen day filled, today ringed, a dot on days with my booking) picks the day, `?day=` keeps it through a reload, every form and redirect, and a sideways swipe moves a day; each termin is one 56px row, and a row with an action opens the bottom sheet (`#sheet`): the facts and one action, "Rezerviraj" (with the "isti termin svaki tjedan" checkbox on weekly slots: `POST /book/{id}` with `series=1` books the repeat at once) or "Otkaži rezervaciju". The trainer's rows link to the roster. Without JS the phone keeps the agenda of cards; the desktop keeps the 7-column grid. **A month overview on phones** (18.10.2026, clients): a "Tjedan | Mjesec" switch under the week buttons opens `?view=month&month=YYYY-MM`, the month as Shape's "Moj napredak" grid: the days of the paid period tinted a light green (`db.covered_days`: the plans that book termini, from the cycle's start to dospijeće), my bookings dotted, today ringed, and a tap on a day opens its week on that day; "Članarina vrijedi do …" under it. The switch is hidden from 861px and never shown to the trainer (`?view=month` is the week page for him) |
| `/karton`, `/upitnik` | client | Personal file: upitnik result, training diary, termini. `/karton/{id}` is the trainer's read-only view |
| `/treninzi` | client/trainer | Online programmes — automatic (see below) |
| `/prehrana` | public | MojiMakrosi link (`/nutricionizam` 301s here) |
| `/profil` | any | Basic info form; under it the **Račun** card (the email as plain text, "Registriran/a od …"; back 20.10.2026); a client's link to `/moja-clanarina` (plans, uplate and računi moved there 18.10.2026) |
| `POST /copy/{key}` | trainer/owner | Saves one in-place-edited text (JSON); an emptied text is stored empty since 20.10.2026, except a number (a `required` slot: `price.<plan>.amount`, `addon.*`), whose default comes back; `reset=1` (Zadano) restores the default (a row's cell stays empty too). An announcement's field too, by its virtual key `aktualno.<id>.<field>`, and a gym card's, `dvorana.<id>.<field>`; a rows slot's cell by `index` + `part`, a row by `index` + `remove=1`, a new row by `add=1` |
| `POST /aktualno/nova`, `POST /aktualno/{id}/obrisi` | trainer/owner | Adds an announcement after the last (placeholder texts; at most 8) / deletes one with its photo. Plain forms from edit mode, back to `/#aktualno` |
| `POST /dvorana/nova`, `POST /dvorana/{id}/obrisi` | trainer/owner | The same for the gym's cards: adds one after the last (placeholder texts, no plans; at most 8) / deletes one. Plain forms from edit mode, back to `/#dvorana` |
| `/admin` | trainer | Weekly timetable as an **editable week grid** + one-off termini |
| `/clanarine` | trainer | Record cash/card uplate per client per plan. The add form's `sessions` select (grupni's treninga a month) and `tier` select ("Paket (samo online)": the three QMove names, the cards' titles) show only for their plan (an inline script; without JS both show, and the route ignores the one that does not fit); an online row's `tier` select stands on the member's tier, so the next uplata can move him, and the flash names it ("Online trening (QMove PRO): uplata evidentirana — …", 20.10.2026). Under its lead a line to the members' page, "Stranica koju vide članovi — cjenik, tekstovi i cijene uređuju se tamo: Moja članarina →" (18.10.2026: the trainer's and the owner's nav has no Članarina tab, only the account menu's item, which the owner missed) |
| `/korisnici`, `/statistika` | owner | Roster + trainer grants; uplate per plan per month |

Media (`data/uploads/`, gitignored) is served ONLY via the auth-gated `/media/{name}` — except the announcements' images, public by nature, which `/slika/{name}` serves (only names an announcement holds, cached a year).

## Architecture — the three ideas

**1. One booking mechanism covers everything.** `TrainingSession.capacity = 8` → group
class; `capacity = 1` → individual termin. Concrete sessions come from `SessionTemplate`
rows via **lazy materialization**: viewing a week upserts that week's sessions
(`ON CONFLICT DO NOTHING` on `uq_session_template_start`), clamped to the booking window
— no cron, concurrency-safe. Editing a template prunes future **unbooked** sessions so
they re-materialize; booked ones are never touched.

**2. Plans gate everything.** Six `PLAN_TYPES` (grupni, individualni, poluindividualni,
rehabilitacija, online, prehrana). Every session carries a `kind`; `book()` refuses
unless the client has an active membership of that kind. `Membership` holds only the
CURRENT cycle: recording an uplata sets `next_payment` a month out and `dospijece` a
week after that, and the plan admits booking until dospijeće passes. Paying early
extends from the due date; a lapsed plan restarts from today. Every uplata also appends
to the immutable **`payments` ledger** (user, plan, method, date, amount-when-known) —
memberships answer "who is active", the ledger answers "how much traffic". The Stripe
webhook writes the same rows with `method="stripe"`. **Grupni is tiered** like the
owner's shop — 8 / 12 / 16 treninga a month (`Membership.sessions_per_cycle`, NULL =
unlimited); `book()` counts the cycle's live bookings of that kind and refuses past the
quota. Cycles are anchored on `next_payment` (`Membership.cycle_bounds`), so an early
renewal never smears two months' quotas together. **Online is tiered** since
20.10.2026: QMove START / PRO / ELITE, the landing's three cards (`models.ONLINE_TIERS`;
`Membership.tier`, NULL for every other plan; migration `914d4b4556e5` gave every
online row there `start`). A tier's name is its card's title slot (`ONLINE_TIER_SLOTS`,
`copy.online_tier_names`), the gym owner's text. Each uplata on `/clanarine` restates
it (`record_payment(tier=)`; none named keeps the row's tier, `start` for a new row,
so the Stripe webhook, which names none, never demotes a member: a new card
subscription is START until online has a Price per tier), and the landing owns
one card, the tier's (`db.online_tier`). The app's gates are per plan, not per tier:
any active online plan opens `/treninzi`, and the tiers' differences in their bullets
(one programme / three / all, the MojiMakrosi photo limits, the chat and the calls)
are not enforced. **A booking can repeat weekly**
(`db.book_series`, offered right after booking a templated session): the same slot on
every following week of the paid period, i.e. the cycle containing that termin, cut at
dospijeće. No 28-day horizon there (the period is the bound); each date is materialized
and judged by `book()`'s own rules (`_refusal`, shared so they cannot drift), full /
canceled / already-held dates are skipped and reported, and a spent paket stops the run.

**3. The online side is automated, never hand-assigned.** The upitnik
(`src/qmt/upitnik.py`, five scored questions + a goal) routes a client into a razina
(pocetna/srednja/napredna) and a cilj (cijelo/gornji/donji). Programmes are tagged with
that combo and **matching IS the access** — no per-client hand-outs exist. The nine
(razina × cilj) slots create themselves with default exercises via
`db.ensure_online_skeletons()` when the trainer opens /treninzi (fresh deploys
self-heal); a slot with any trainer-made item is never overwritten. Gates stack:
active `online` plan → filled upitnik → matched programmes.

| Path | Role |
|---|---|
| `src/qmt/config.py` | `.env`, `OWNER_EMAIL`/`ALLOWED_EMAILS`, booking knobs, prod guards |
| `src/qmt/copy.py` | The texts a trainer/owner may edit in place: slot → default text, label; a 2000-character cap, no design limit since 16.10.2026; an emptied text stays empty since 20.10.2026 but a `required` slot's (the numbers, `price.<plan>.amount` / `.year_amount`, `addon.*`), whose default comes back; lists (`ListSlot`; the extra lines, `*.extra`, are lists that start empty), tables of rows (`RowsSlot`: the opening hours, `load_rows` / `dump_rows`, a new row's `ROW_BLANK`), on/off flags (`FlagSlot`) and photos (`ImageSlot`); the prices (`price.<plan>.*`, `addon.*`, defaults `REFERENCE_PRICES` / `YEARLY_PRICE` / `MOJIMAKROSI_ADDON`), every price the site shows; the `/moja-clanarina` cards' one text each (`cjenik.<plan>.text`, defaults `PLAN_TEXTS` + `PLAN_TEXT_END`); how an announcement's fields are edited (`ANNOUNCEMENT_SLOTS`, `ANNOUNCEMENT_COLUMNS`), a new card's placeholders (`ANNOUNCEMENT_BLANK`) and the seed's two examples (`ANNOUNCEMENT_EXAMPLES`); the same for a gym card (`GYM_CARD_SLOTS`, `GYM_CARD_COLUMNS`, `GYM_CARD_BLANK`, `GYM_CARD_EXAMPLES`) |
| `src/qmt/models.py` | `User` (+profile fields), `SessionTemplate`, `TrainingSession`, `Booking`, `Membership`, `Payment`, `OnboardingResponse`, `TrainingLog`, `Program`(level/goal)/`ProgramItem`, `SiteCopy`, `Announcement` (the landing's cards), `GymCard` (the gym's cards; `plan_keys`, `point_items`, `extra_items`); `PLAN_*`, `ONLINE_TIERS` / `ONLINE_TIER_SLOTS` (the online plan's QMove tiers and their cards), `FEELING_LABELS`, `PAYMENT_METHODS` |
| `src/qmt/db.py` | Queries + rules. **`book()` locks the session row FOR UPDATE** and re-counts inside the lock (tested); `add_announcement` locks the `announcements` table, so the cap of 8 (`MAX_ANNOUNCEMENTS`) holds when adds race (tested); `add_gym_card` the same for `gym_cards` (`MAX_GYM_CARDS`) |
| `src/qmt/upitnik.py` | Questions, scoring thresholds, level/goal labels |
| `src/qmt/auth.py` | bcrypt + signed email tokens (verify 24 h; reset 1 h, single-use) |
| `src/qmt/mailer.py` | Only Resend importer. Also `send_new_user_notice` → owner hears about each first verification |
| `src/qmt/reminders.py` | Email podsjetnici (pre-dospijeće + day-before termin), claim-idempotent via the `reminders` table; app lifespan ticks every 6 h, `scripts/send_reminders.py` forces a pass |
| `src/qmt/storage.py` | Media backend: local disk, or Cloudflare R2 when the four `R2_*` vars are set (then `/media` 307s to presigned URLs); `stream()` hands out a stored file's bytes, for `/slika`, which proxies the bytes so its public URL stays cacheable |
| `src/qmt/payments.py` | Stripe: Prices for /moja-clanarina's checkout tier picker and tier switch (cached), Checkout + portal sessions, signed webhook → `record_payment`. Tolerates both invoice shapes (pre/post 2025 API) |
| `src/qmt/web/app.py` | All routes. `current_user()` per route; `PLAN_LINKS` maps an active plan to the page it unlocks; `/copy/{key}` takes a slot's key or an announcement's virtual key (`aktualno.<id>.<field>`, `_announcement_field`) or a gym card's (`dvorana.<id>.<field>`, `_gym_card_field`) |
| `src/qmt/web/templates/` | Jinja2. Design tokens + topbar/avatar menu in `base.html` |

## Conventions (follow these)

- **Croatian everywhere** in the UI. Errors are user-facing sentences raised as
  `db.BookingError`.
- **Design tokens come from the LOGO** (`static/logo.png`): accent `--accent` (#e10600
  light / #ff342b dark), neutral surfaces, PT Sans uppercase display + Inter body.
  Three radius tokens (`--r-xl` 28 / `--r-lg` 20 / `--r-md` 12), every button a
  pill, soft shadows — the Shape-club language in QMT's colours. Both themes are
  first-class (`[data-theme]` tokens, pre-paint script, saved in
  `localStorage['qmt-theme']`). Never style with a raw hex that only works in one theme.
- **The topbar is a floating dark pill, ONE row at every width**: `flex-wrap: nowrap`,
  brand left, tabs middle, avatar right, everything inside the pill's padding.
  **A guest's pill is Shape's small one** (`.topbar.compact`, content-sized and
  centred): brand · Prijava (red) · "Kontakt" (dark, `/#kontakt`); the hero
  below it carries no buttons, the photo leads to the offer. Members get the wide pill
  with their tabs. The wordmark shows in full only when the room the tabs leave allows it, otherwise
  "QMT": a container query on `.brand-slot`, never a window breakpoint — the pill is
  capped at 1100px, so the window width says nothing about the room inside it.
  Seven or more tabs (trainer, owner) run tight; all tabs tighten ≤1200px and fold
  into the ☰ drawer ≤900px. Tabs never wrap their own label. The avatar opens the
  account menu (identity header: the name over the email, one line with an
  ellipsis on a desktop and the whole address in its title, wrapped ≤900px where
  there is no hover; Profil; **Moja članarina for a trainer only**, the exact
  opposite of the Članarina tab, which every non-trainer has, an owner who does
  not train too: nobody gets both (20.10.2026); theme toggle; Odjava).
- **Guests log in through a modal** (`#authDlg`, opened by `data-auth` links; `/login`
  and `/signup` remain the no-JS fallback). **Clients on phones get an install
  banner** (`#a2hs`) from their second visit, again a week after each
  dismissal until they install, never on desktop. Both live in `base.html`.
- **Prices are public on the landing since 5.10.2026** — the owner's decision,
  reversing the members-only rule of 28.9. (which was legal advice: public
  prices would need the prior price shown beside them, the way shop shelves do).
  The way back is one variable: `PUBLIC_PRICES=off` hides every price from
  guests again. Every displayed price is the owner's text (the
  `price.<plan>.*` and `addon.*` slots in `copy.py`, printed through `c.t()`
  so the gym owner edits them in place), everywhere it appears; Stripe's
  Prices (when card payments return) are to be aligned to them in one place,
  and until then only the checkout tier picker (`_tiers.html`, and a
  subscriber's tier switch) shows a Stripe amount (18.10.2026, the owner's
  call: his friend's numbers are the truth). `/moja-clanarina`
  (where the old `/cjenik` leads) stays members-only and no public page links
  to it. **Registration is one switch**,
  `SIGNUP_MODE` = `closed` (the default, also when unset or mistyped) / `invite`
  (owner + `ALLOWED_EMAILS`) / `open`; closed hides every "Registriraj se" and
  the modal's Registracija tab. Existing accounts always log in. Tests run with
  `invite` (`tests/conftest.py`).
- **Public copy is editable in place** by the trainer and the owner (6.10.2026, so
  the gym owner fine-tunes the texts himself). Every such text is a slot in
  `src/qmt/copy.py`, printed through `{{ c.t("key") }}` (`_copy.html`) in a
  `span.t` for every viewer; the editor in `base.html` ("✎ Uredi tekstove",
  then click a text; Enter is a new line, ⌘/Ctrl+Enter saves, Esc cancels,
  "Zadano" restores the default) posts to `/copy/{key}`, which enforces the cap
  again and stores the text in `site_copy`. **No per-box limits since
  16.10.2026** (the owner's call: the copy first, then a design pass that fits
  the boxes to the final texts): every text takes up to 2000 characters, a cap
  against a stray paste. Line breaks are kept (`copy.clean` collapses spaces
  and tabs, allows one empty line in a row) and show (`span.t`, `white-space:
  pre-line`). Adding a text = one registry line + the macro call;
  `tests/test_copy.py` then checks it is on a page and, in a real browser at
  360 / 390 / 900 / 1280px, guards overflow only: 300-character texts and line
  breaks never widen a page or get cut (the photo card's caption, clamped in
  the card, is the one cut on purpose), and the cards' prices stay level.
  Never put a slot inside a link's `href` or an attribute — the editor edits
  text nodes.
  **An emptied text stays empty since 20.10.2026** (the owner: "once he
  removes the text, the text box and the space it occupies gets removed"):
  `POST /copy/{key}` stores it as "" and a visitor gets nothing for it, nor
  the shape around it (the hero's kicker pill, the photo's chips, an
  announcement's chip, when line, text and link, a price's unit and the
  space before it: `c.t` prints no span, the templates guard the shapes),
  while the editor keeps each as an empty box to click, in edit mode only
  (outside it the landing's CSS hides them, so his page is the visitor's).
  "Zadano" (`reset=1`) is how a default comes back. **The numbers keep
  falling back**: a `required` slot (`copy.Slot.required`: every
  `price.<plan>.amount`, `addon.online`, `addon.dvorana`; "the number is the
  only thing that is not free text") emptied is its default again. The
  editor's span carries `data-required`, and the bar says what Spremi
  will do: "Prazno: Spremi vraća izvorni tekst." for a number, "Prazno:
  Spremi ostavlja prazno." for any other text (from 600px "… · Zadano vraća
  izvorni tekst." after it). Lists and rows keep their rules: an emptied
  item goes, a cell stays empty, a row of two empty cells goes.
  **Lists** (15.10.2026, the offer cards' bullets) are a `ListSlot`: up to 12
  items of up to 2000 characters, one `site_copy` row holding a JSON array, printed
  through `{{ c.points("key") }}`. In edit mode each item has a ✕ and the list
  a "+ Dodaj stavku"; an item saves with its `index` (n appends, an empty text
  removes it) and "Zadano (cijela lista)" (`reset=1`) restores the whole list.
  **Extra lines** (20.10.2026, the owner: "Can we also create a
  functionality to add text cells?") are lists whose default is empty,
  printed as plain lines, no bullet: `{{ c.lines("key") }}` (a row's
  field: `c.field_lines`), the bullets' own markup with the `<ul>` classed
  `.lines` and its button saying "+ Dodaj tekst", so the list editor works
  them unchanged (each line's ✕, `index`, and "Zadano (cijela lista)",
  which empties the list). Their places: under every card's bullets (the
  tiers' `offer.online*.extra`; a gym card's `dvorana.<id>.extra`, its
  row's `extra` column, migration `c138157ff6bb`, set with
  `db.set_gym_card_list`), under the hours' table (`info.hours.extra`),
  under the contact rows (`info.contact.extra`) and under the headline
  (`hero.extra`, in the old lead's look: muted, 16px under the h1).
  Until a line exists a visitor's page is what it was, its body byte for
  byte (the owner: "Only if someone actually adds the text does it
  change, right?"): an empty list prints nothing for him, the editor's
  empty `<ul>` takes no room, and "+ Dodaj tekst" shows in edit mode only.
  **Rows** (20.10.2026, the landing's opening hours, `info.hours.rows`, which
  migration `1a7c144b582a` folded the six `info.hours.d1 … t3` slots into)
  are a `RowsSlot`: up to 12 rows of two texts (days, hours) of up to 2000
  characters each, one `site_copy` row holding a JSON array of pairs, printed
  through `{{ c.rows("key") }}` (the `<table>`, `td.d` the days). A cell
  saves with its row's `index` and its `part` (0, 1), and **an emptied cell
  stays empty** (the first text that did, before every text did on
  20.10.2026): a row has no default per cell, and a row left with two
  empty cells goes. In edit mode each row has a ✕ in a
  cell of its own (`td.ed-xc`, two taps, `index` + `remove=1`) and the table
  a "+ Dodaj red" (`add=1`: a row with the placeholders "dan" / "sati",
  `copy.ROW_BLANK`; "Najviše 12 redova." at the cap); "Zadano (cijela
  tablica)" (`reset=1`) restores the default rows. The answer is always the
  whole table (`rows`), which the editor redraws.
  **Announcements** (the landing's `#aktualno` cards; two fixed sets of slots,
  `event1.*` / `event2.*`, until 18.10.2026, which migration `b48179fcf538`
  turned into the first two rows) are rows, not slots: the `announcements`
  table (`models.Announcement`: `position` = creation order, `shown`, five
  texts, `image`), up to 8 (`db.MAX_ANNOUNCEMENTS`), which the gym owner
  adds, hides and deletes himself. The editor edits a card as it edits slots,
  through **virtual keys** `aktualno.<id>.<field>` on the same routes
  (`copy.ANNOUNCEMENT_SLOTS` says how each field is edited), and the
  template prints a card's text with `c.field(key, text, label)` (`_copy.html`,
  the same span as `c.t`; the bar names a card by its place, "Najava 2:
  naslov"). The texts (`tag`, `title`, `when`, `text`, `cta`) behave as
  slots: an emptied one stays empty (none is required; a visitor gets no
  chip, when line, text or link for an empty one, the title's `h2` stays,
  empty), and "Zadano" puts the new card's placeholder back
  (`copy.ANNOUNCEMENT_BLANK`). **The switch** (`show`) is
  a `FlagSlot`: `POST /copy/{key}` takes exactly "on" or "off", or
  `reset=1` (on). In edit mode the card carries a `.ed-flag` toggle
  ("Prikazano" / "Skriveno") that saves at a click; a hidden card stays on
  an editor's page as `.is-off` (shown, dimmed, in edit mode only), and a
  visitor never gets a hidden card's markup. **The photo** (`image`, like
  Shape's photo cards) is an `ImageSlot`: in edit mode "Dodaj sliku" /
  "Promijeni sliku" (`.ed-img`) opens the file picker and posts to `POST
  /copy/{key}/slika` (jpg / png / webp, at most 15 MB): Pillow turns it
  upright (EXIF), shrinks it to 1600px on its long side and keeps a
  progressive JPEG with no EXIF, under a new name `aktualno-<id>-<hex>.jpg`
  (the card's previous photo is deleted). "Ukloni sliku" (`.ed-img-x`, a
  second tap confirms) is `reset=1` on `POST /copy/{key}`, which deletes
  file and name; that route takes nothing else for a photo. A card with a
  photo is `.has-img` + `data-photo` (the audit counts its text as on a
  photograph). **Adding and deleting**: in edit mode "+ Dodaj najavu"
  (`.ed-add-ann`, under the row's dots, `POST /aktualno/nova`) adds a card
  after the last, with placeholder texts, shown, no photo; each card's
  "Obriši najavu" (`.ed-ann-x`, `POST /aktualno/{id}/obrisi`) asks first
  ("Obriši?" at one tap, as a ✕) and deletes the card, then its photo. Both
  are plain forms that come back to `/#aktualno`; at 8 the add is not
  offered (and refused with "Najviše 8 najava."). The slot types `FlagSlot`
  and `ImageSlot` stay, for any slot that is a switch or a photo (read with
  `copy_flag` / `copy_image`); no `SLOTS` entry is one since 18.10.2026
  (but for the tiers' add-on switches, `offer.online*.addon_on`, from
  20.10.2026 until their line went on 21.10.2026).
  **The gym's cards** (`#dvorana`, 20.10.2026: the `offer.dvorana.*` /
  `offer.individualno.*` slots until migration `78d539161185` made them the
  first two rows) are rows the same way: the `gym_cards` table
  (`models.GymCard`: `position`, `shown`, `title`, `lead`, `points` (a JSON
  array, as a list slot's row), `price` / `unit`, `year_price` /
  `year_unit`, and `plans`, the plan keys it stands for, comma-separated),
  up to 8 (`db.MAX_GYM_CARDS`), edited through virtual keys
  `dvorana.<id>.<field>` on `POST /copy/{key}` (`copy.GYM_CARD_SLOTS`: the
  texts as slots, `points` item by item as a list slot, `show` as a
  switch; no photo; an emptied text stays empty, an empty lead keeping its
  `<p class="lead">` so the lists stay level, and "Zadano" is the new
  card's placeholder, `copy.GYM_CARD_BLANK`; the bar says "Kartica 2: naziv").
  Each card's switch and "Obriši karticu" (`.ed-gym-x`, two taps,
  `POST /dvorana/{id}/obrisi`) sit at its top in edit mode; "+ Dodaj
  karticu" (`.ed-add-gym`, `POST /dvorana/nova`) under the row adds one
  with placeholders and no plans ("Najviše 8 kartica." at the cap). Nothing
  edits `plans` in place: the two migrated cards keep theirs (their price
  is their first plan's slots), a card he adds has none (its own price,
  "Javi nam se" for a button).
  **Prices** (18.10.2026) are plain slots, the only source of a price on
  the site: per plan `price.<plan>.amount` / `.unit`, and for the gym's
  five plans (all but online) a yearly `price.<plan>.year_amount` /
  `.year_unit` since 21.10.2026 ("na upit" until typed: the plan's
  "Dodaj plan" card and the landing's gym card the plan prices; the QMove
  tiers' yearly prices are their cards' `offer.online*.year_price` /
  `.year_unit`), no note under a price since that day (prehrana's hint on
  `/moja-clanarina` is the two add-on amounts), and the
  MojiMakrosi add-on's `addon.online` / `addon.dvorana` (defaults
  `REFERENCE_PRICES` / `YEARLY_PRICE` / `MOJIMAKROSI_ADDON` in `copy.py`,
  the amount printed as typed with " €" after it when it holds a number
  and no sign of its own), on the landing and on `/moja-clanarina` (the
  only slots on two pages: one number, one slot), a Stripe Price for the
  plan or not; `addon.*` are the prehrana hint's numbers on
  `/moja-clanarina`, the one place they print since 21.10.2026. The words
  around a number are slots of their own since 20.10.2026 (the owner: free
  text, "the number is the only thing that is not free text"):
  Individualno's line says `price.poluindividualni.word` and
  `price.rehabilitacija.word` before those plans' amounts. The QMove tiers'
  add-on line went on 21.10.2026 (the owner: "lets leave out the moji
  makrosi out of here completely"; the gym cards' on 20.10.2026), and with
  it its words and its switches, `offer.online*.addon` / `.addon_unit` /
  `.addon_on` (20.10.2026), out of the registry with no migration: a
  `site_copy` row of a removed key is never read. **Plan names** (18.10.2026) are slots on `/moja-clanarina`
  only, `plan.<plan>.name` (defaults `PLAN_LABELS`): the headings of its
  cards. Everywhere else, that page's ledger included, `PLAN_LABELS` stay
  fixed: they are the app's names for its own records (the timetable,
  `/clanarine`, the emails, the alerts). **Plan texts** (21.10.2026): a
  "Dodaj plan" card on `/moja-clanarina` is one text, `cjenik.<plan>.text`
  (a QMove tier's `cjenik.online.<tier>.text`), in place of the pieces a
  card was made of, `cjenik.<plan>`, `price.<plan>.note`, `cjenik.note` and
  `clanarina.card_hint`, which left the registry (migration `6e2b9d41c7a3`
  folded the edited ones in, a line each).
- **Design changes go through the `qmt-design` skill** (`.claude/skills/qmt-design`):
  tokens, components, patterns, and the measured audit that must pass before UI
  work is called done.
- **Every schema change is an Alembic migration.**
- **Tests must stay green** (`pytest -q`). New rules get a test — especially anything
  that must hold under concurrency (`test_capacity_race_no_overbooking`).
- **Trainer-only routes** go through `_require_trainer`, owner-only through
  `_require_owner`. Clients only ever see their own data.
- **Jinja + dicts:** never key a template dict `items` — Jinja resolves `d.items` to the
  builtin method (the calendar uses `sessions`).
- **Every screen works on every device — STANDING GOAL.** Phones are the primary client
  device. Verify at 390px and 360px with Playwright before calling UI work done;
  `document.documentElement.scrollWidth - clientWidth` must be 0. **A Stop hook
  enforces the measurable half**: when templates or static CSS/JS differ from the
  last stamped state, `.claude/hooks/ui-audit-gate.sh` runs the audit's phone pass
  (`audit.py --phone`: 390px + 360px, touch, guest / client / owner, ~30 s) and
  blocks the stop with the findings if it fails. It needs the dev server on 8100.
  It measures; it does not look — one screenshot at 390px is still required.
- **QMT is a PWA** (manifest + icons + root-scoped `/sw.js`). The SW never caches HTML
  or `/media`; bump its VERSION when changing cached assets.

## Models — Fable designs, briefs, reviews and ships; Opus implements

**Fable 5.1 is the main model**: it talks to the owner, decides what to build,
writes the brief, reviews the result and deploys. **Opus 5.5 at maximum
reasoning effort implements** (the `opus-worker` agent,
`.claude/agents/opus-worker.md`: `model: opus`, `effort: max`). The owner's
rule since 15.10.2026: implementations are delegated; Fable then reads the
diff and re-runs the tests and the audit before anything counts.

**The flag is `QMT_DELEGATE`** = `on` | `off`, under `env` in
`.claude/settings.local.json` (untracked, per machine; **on** on the owner's
machine). Missing, mistyped or unreadable means off. A SessionStart hook
(`.claude/settings.json` → `.claude/hooks/delegation-flag.sh`) prints the value
into every session. The owner's word in the conversation beats the flag:
"do it yourself" keeps one task on Fable, "delegation off" flips the flag.

- **On** (the rule): every implementation goes to `opus-worker` — features,
  fixes, tests, migrations, docs — and **delegated work is a draft until Fable
  has reviewed it**.
  - **Keep on Fable**: the design and UX decisions (they go into the brief,
    not to the worker), merge conflicts, anything that touches prod (a push to
    `master`, Railway, Stripe), the final report — and an edit that is quicker
    to make than to brief (a one-line fix, a config flip).
  - **Brief** the worker as someone with no context: the goal in the owner's
    words, the decisions already made (data model, keys, limits, sections),
    the exact files, what done looks like, what to leave alone. Start from a
    clean tree (commit what is pending first) so its work is exactly
    `git diff`. One suite run at a time: `qmt_test` is shared, so a worker and
    Fable must not both run `pytest`.
  - **Review** means reading that diff, not the worker's summary, then
    re-running the checks yourself (`pytest -q`; the audit; a 390px
    screenshot for UI). Fix small things directly, send bigger ones back with
    `SendMessage`. The worker never commits, pushes or deploys: Fable does,
    after review, and answers for the result.
- **Off**: do the work directly. `Explore` and parallel searches stay available.
- If the session itself runs on another model (`/model`), there is nobody to
  hand down to — do the work directly.

The model pins are the owner's, in `~/.claude/settings.json`: `model: fable`
for the session and `CLAUDE_CODE_SUBAGENT_MODEL=claude-opus-5-5` for subagents
without a `model` of their own. A changed agent file loads at the next session
start, not mid-session.

## Gotchas

- `.env` is optional in dev; set `OWNER_EMAIL=trener@qmt.local` or /korisnici and
  /statistika are unreachable locally.
- Sessions are tz-aware (Europe/Zagreb) — compare against `datetime.now(config.TZ)`.
- Cancelled sessions stay in the calendar crossed out on purpose.
- A booking can be cancelled until 12 h before the termin, `CANCEL_CUTOFF_HOURS`
  (one rule, `db.cancel_deadline`, asked by `cancel_booking` and by both
  calendar buttons; a termin the trainer canceled can always be dropped);
  booking itself is allowed until the termin starts, up to
  `BOOKING_HORIZON_DAYS` ahead.
- `seed_demo.py` is a dev RESET (wipes templates/sessions/bookings/plans/programmes);
  `seed_prod_demo.py` is additive and refuses non-Railway DBs.
- Allowlist matching is **exact** — Gmail dot/plus variants are not normalized.
- Verifying an email is what notifies the owner, and only the first time (row-locked);
  a Resend failure never blocks verification.
- Real studio facts: open pon/sri/čet/pet 07:00–20:00, Virovska ulica 1, 10040 Zagreb; group
  trainings hourly, capacity 8.
- **Screenshots:** oversized images earlier in a session can poison every later image
  request. Keep them one per message.

## Roadmap

1. ✅ Booking MVP, email verify/reset, deploy, PWA
2. ✅ Membership plans gating bookings; manual cash/card uplate; payments ledger +
   owner statistika
3. ✅ Karton (upitnik routing, per-termin feedback, diary, calendar); automated online
   programmes by (razina × cilj)
4. ✅ **Card payments — built, dormant until keys exist.** Stripe **subscriptions**
   (auto-renew monthly): `/moja-clanarina` → `POST /placanje/{plan}` → Checkout; signed
   `invoice.paid` webhook → `db.record_payment(method="stripe")`; portal at
   `/placanje/portal`. Everything is in `src/qmt/payments.py`, switched on by
   `STRIPE_*` vars (see DEPLOY.md). Still owed by the owner before LIVE keys: the
   d.o.o.'s Stripe account, real prices (Stripe's Prices aligned BY HAND to the price slots — a central price table that would push the owner's numbers into Stripe was designed and deferred by the owner on 18.10.2026, to be built only if asked;
   first: the site prints only the slots since 18.10.2026), three online Prices (one
   per QMove tier, as grupni has three, and the webhook passing the tier its Price
   stands for: until then a card subscription to online is START), and the accountant's
   Fiskalizacija 2.0 flow (mandatory since 1.1.2026, fiscalized račun per B2C charge).
5. ⏳ Owner's own content: landing/service copy, exercise videos. The R2 storage
   layer is BUILT (`storage.py` + `scripts/migrate_media_to_r2.py`) — activating it
   is just the four `R2_*` vars on Railway; until then `data/uploads` stays ephemeral
6. ⏳ Mini-kuharica (30–50 recipes) + deeper mojimakrosi link-up

See `roadmap/2026-09-03-owner-voice-note.md` for the owner's own wish list and
`roadmap/STATUS.md` for where the last session left off.
