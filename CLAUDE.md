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
pytest -q                                  # 324 tests, must stay green
```

Demo logins: `trener@qmt.local/trener123` (trainer **and** owner locally, via
`OWNER_EMAIL` in `.env`), `ivan@qmt.local/lozinka123` (has grupni + individualni +
online plans, online on the QMove PRO tier, filled upitnik (v2: srednja, 6,4 / 10, no
flags), diary entries, one feedback prompt pending, two finished passes of his online Dan 1
"Cijelo tijelo", Goblet čučanj at 16 then 20 kg, none in progress),
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
image); a push deploys nothing. **Live since 24.10.2026** (the cutover: Railway's app services taken down, final dumps restored on the box, the three Cloudflare A records switched; Railway's projects are deleted once the first nightly backups are in).

## Pages

| Route | Who | What |
|---|---|---|
| `/` | public | Landing: hero = kicker, headline, then **`#aktualno`**: the owner's announcement cards for the month, any number up to 8, rows of the `announcements` table in the editor's order (chip, title, when, a few lines, a grey "Javi nam se" → `/#kontakt`; added in edit mode with "+ Dodaj najavu" (placeholder texts to retype, last), deleted with each card's "Obriši najavu" (two taps) and moved one place with its ↑ / ↓ (one tap, 29.10.2026); each switched off by the editor, gone when all are; each optionally over a photo of the owner's (uploaded in edit mode, shrunk to a 1600px JPEG, stored like other media, in R2 on prod), then Shape's photo card: glass chip on top, white type and a white pill at the bottom): one card per view at every width, as wide as the row (the screen less the gutter on a phone, the 1100px column on a desktop), dots under it, moving on by itself every 5 s (quiet while touched, hovered or focused, off-screen, in a hidden tab, or under reduced motion); edit mode stacks them, one under the other; then the photo card that links to the offer; no lead, no button, no note since 16.10.2026 (the owner's call: the announcements are the first thing on the page). **The offer (`#usluge`) is three tiers of the online plan** (QMove START / PRO, featured / ELITE; no MojiMakrosi add-on line since 21.10.2026, the owner: "lets leave out the moji makrosi out of here completely"; its amounts live on in prehrana's hint on `/moja-clanarina`): tier 1's monthly price is the online plan's own, every other price (tiers 2–3 monthly, all three yearly) is editable text until a plan exists; a **Mjesečno / Godišnje** switch under the cards shows one price per card (per page view, yearly first, monthly on a press; yearly without JS); on phones (<900px) the tiers are a swipe carousel (cards 92% wide, a sliver of the next) with three dots that opens on PRO (the featured middle card: START a swipe to the left, ELITE to the right). Below it, quieter, **the gym (`#dvorana`)**: its cards are rows of the `gym_cards` table since 20.10.2026, in creation order (Dvorana and Individualno, the first two, then whatever the gym owner adds: "Pilates za cure"), added ("+ Dodaj karticu"), hidden (its switch) and deleted ("Obriši karticu", two taps) in edit mode like the announcements, up to 8; a visitor gets no section when none is shown. No MojiMakrosi add-on line since 20.10.2026. A card with plans is priced by its first plan's slots (`price.<plan>.*`, the ones `/moja-clanarina` prints: edit one, both change; its yearly price too since 21.10.2026, the plan's `price.<plan>.year_amount` / `.year_unit`, into which migration `6e2b9d41c7a3` carried the row's typed one) and names its other plans' prices in a muted line under its own (Individualno: semi-individual and rehab; the words before each price are slots since 20.10.2026, `price.poluindividualni.word` / `price.rehabilitacija.word`, the number stays the plan's amount slot, its default back when emptied); a card without plans (every one he adds) is his text alone, its own monthly price, and "Javi nam se →" → `#kontakt` for everyone. Tiers too (a monthly and an editable yearly price: a card without plans its row's own) with their own switch, its own choice since 20.10.2026 (the owner: "unlink them"): it opens on Mjesečno, the monthly price (monthly without JS too), and a press flips the gym's cards only, as the tiers' switch flips the tiers only; from 900px as many columns as cards, up to three (a fourth wraps), on phones a swipe row. Gallery from `static/gallery/`; contact, its opening hours rows the editor empties, removes and adds (`info.hours.rows`, a `RowsSlot`, 20.10.2026). Extra lines (20.10.2026): plain lines of text the editor adds with "+ Dodaj tekst" under the headline, under every card's bullets, under the hours and under the contact rows (`*.extra`, `c.lines`), none until he does. A card's button follows the visitor: owner of the plan → into the app (a QMove card: only the owner of its tier, `Membership.tier`, since 20.10.2026; the other two say "Odaberi plan" to him), member → "Odaberi plan" → that plan's card on `/moja-clanarina`, guest → "Registriraj se" when signup is open, else "Javi nam se" → `#kontakt` (a gym card without plans: "Javi nam se" for everyone) |
| `/moja-clanarina` | client | **"Moja članarina"** (18.10.2026, Shape Club's billing page in QMT's look; the nav's tab says "Moja članarina" too since 26.10.2026, a client's and staff's alike): **members only** (guests are sent to log in; the trainer and the owner, who manage members on `/clanarine`, see it with no plans of their own: it is where its texts are edited), where plans are seen, bought and managed; the public price list is the landing's offer. **Tvoji planovi**: a card per plan held, active or lapsed (active first, `PLAN_TYPES` order): PAKET + name, a chip that says the state (aktivna / dospijeva za N dana, N ≤ 7 to dospijeće / istekla / otkazana · vrijedi do kraja), the facts (cijena, uplaćeno, sljedeća uplata, vrijedi do; a tiered grupni's paket and "n od N u ovom ciklusu"; the online plan's paket, its QMove tier's name, printed through the landing card's title slot, `offer.online*.title`, so a rename shows on both pages), one sentence on how and by when it is paid, and only what fits how it is paid: the plan's door (`PLAN_LINKS`) while it runs; a card subscriber's portal ("Kartica, računi, otkazivanje") and tier switch; a cash member's "Prebaci na karticu" once Stripe is configured (nothing more without it). **Dodaj plan**, the plans not held, in two groups since 21.10.2026 (the owner: "every tab is one big text cell except the number i.e. price which is connected to the front page"; "split into the QMOVE online trainings with 'godišnje' as default and everything else in the gym separate with 'mjesečni' as default"): **Online treninzi** (`clanarina.h.online`), the landing's three QMove tiers (none while online is held), its Mjesečno / Godišnje switch opening on Godišnje; then **Treninzi u dvorani** (`clanarina.h.gym`), the other plans not held in `PLAN_TYPES` order, its switch opening on Mjesečno (each group a `[data-period-group]` with its own switch, `_period.html`, which base.html's script flips for its cards only; a group with no card left is not on the page). A card is its name (a tier's its landing card's title slot, a plan's `plan.<plan>.name`), its monthly and yearly price lines (the landing's own slots: START's `price.online.amount` / `.unit`, PRO's and ELITE's `offer.online2/3.price` / `.unit`, every tier's `offer.online*.year_price` / `.year_unit`, printed as typed; a plan's `price.<plan>.amount` / `.unit` and `.year_amount` / `.year_unit`, " €" after a number), ONE text (`cjenik.<plan>.text`, `cjenik.online.<tier>.text`, its default the lines the old pieces said: the lead, the note, "Za upis se javi treneru u dvorani.", "Mjesečno, otkazivo bilo kad. Ili gotovinom u dvorani."; migration `6e2b9d41c7a3` carried what was edited) and "Pretplati se karticom" → Stripe Checkout where sellable, nothing otherwise (a tier's form names its tier, which `/placanje/online` ignores until online has a Price per tier). QMove START carries `#plan-online` (PRO and ELITE `plan-online-pro` / `-elite`). **Računi**: the `payments` ledger, newest first (date, plan with the method under it, amount when known), plus the portal's invoices for a subscriber. Price lines are the `_plan_price.html` macros (`pp.price`, a plan held's Cijena `pp.plan_price`; no note under a price since 21.10.2026; prehrana's hint: the two `addon.*` amounts); Stripe's amounts show only inside the forms that charge them, a checkout form's tier picker and a subscriber's tier switch. **Editable in place** (trainer/owner): the lead (`cjenik.hint`) and each Dodaj plan card's one text (`cjenik.<plan>.text`, `cjenik.online.<tier>.text`), every price (`price.<plan>.*`, the tiers' `offer.online*.*`, `addon.*`: the landing's own slots), and since 18.10.2026 the headings (`clanarina.h.*`, the two groups' since 21.10.2026), the plans' names on its cards (`plan.<plan>.name`, this page's own; a tier's is its landing title), the no-plan card (`clanarina.none.*`; an editor holds no plans, so he gets it as a preview under "Ovo vidi član bez članarine:") and the empty ledger's line (`clanarina.bills.empty`). The line under a lapsed plan's "Pretplati se karticom" was `clanarina.card_hint` until 21.10.2026: fixed text since, its last default. `plan.online.name`, a held online card's heading, is on no page an editor opens since then (open question). Not the sentences built around a date or a number (the status box, the chips, the facts) or the ledger's headers. **`/cjenik`** (the old price list; the reminder email still links it) redirects here, query and `#plan-<key>` kept |
| `/raspored` | client | Week calendar, booking, "Moje rezervacije" as day columns, each booking with a ✕ that asks before it cancels; cancelling is allowed until 12 h before the termin, `CANCEL_CUTOFF_HOURS`. The plans are `/moja-clanarina`'s (the "Moja članarina" block that listed them here went 18.10.2026): a client with no plan running, a lapsed one's too, gets only the booking gate's line under the termini, "Nemaš aktivnu članarinu — bez nje rezervacija nije moguća." with "Pogledaj cjenik →". Booking is open in the running week and three more (`BOOKING_WEEKS`, `db.booking_window`, 29.10.2026): a client's "idući tjedan" (and the phone's swipe) stops at the window's last week, and a week past it (a day of the month view, a typed `?week=`) shows him no termin, only "Termini se objavljuju 4 tjedna unaprijed." (the trainer walks every week); a termin after the client's dospijeće offers nothing (no Rezerviraj, no sheet) and the week says so once under its termini, "Članarina vrijedi do 8.5. — za kasnije termine produlji članarinu." with "Moja članarina →". An empty termin closes 4 h before it starts (`CLOSE_EMPTY_HOURS`, `db.is_closed`): "zatvoreno" where "otkazano" would sit, muted, the row dimmed as a past one and never crossed out, for a client (no Rezerviraj, no sheet) and on the trainer's grid (his row still leads to the roster). After booking a weekly slot the ok alert offers "Isti termin svaki tjedan do … — još N termina →" → `POST /book/{id}/series` books that slot on every later week of the window, up to the client's dospijeće; a run that skipped a date or ran out of its paket comes back with its line and the dialog `#seriesDlg` ("Nisu rezervirani svi termini": what was booked, each date not booked with its reason in words, the paket's sentence, "U redu"; the redirect carries `booked=` / `skipped=` / `paket=`, dates and reason keys). A client's **"Tvoj sljedeći termin"** card (the soonest booking, with its ✕) sits right under the week's head at every width. **On phones (≤860px) one day at a time** (17.10.2026, so nobody scrolls the whole week): a day strip (Shape's "Moj napredak" week: pon 12 … ned 18, the chosen day filled, today ringed, a dot on days with my booking) picks the day, `?day=` keeps it through a reload, every form and redirect, and a sideways swipe moves a day; each termin is one 56px row, and a row with an action opens the bottom sheet (`#sheet`): the facts and one action, "Rezerviraj" (with the "Isti termin svaki tjedan do …" checkbox on weekly slots, the row's own bound, `data-until`, while a later week fits it: `POST /book/{id}` with `series=1` books the repeat at once, its dialog too) or "Otkaži rezervaciju". The trainer's rows link to the roster. Without JS the phone keeps the agenda of cards; the desktop keeps the 7-column grid. **A month overview on phones** (18.10.2026, clients): a "Tjedan | Mjesec" switch under the week buttons opens `?view=month&month=YYYY-MM`, the month as Shape's "Moj napredak" grid: the days of the paid period tinted a light green (`db.covered_days`: the plans that book termini, from the cycle's start to dospijeće), my bookings dotted, today ringed, and a tap on a day opens its week on that day; "Članarina vrijedi do …" under it. The switch is hidden from 861px and never shown to the trainer (`?view=month` is the week page for him) |
| `/karton`, `/upitnik` | client | Personal file: upitnik result, training diary, termini. `/karton/{id}` is the trainer's read-only view. **The diary holds the online passes too** (30.10.2026, stage 3 of the online treninzi spec: `_diary_rows`): each finished pass of the client's among his termini by when it started, newest first, in a termin row's shape: the kicker "Online trening", the day and date, napor and osjećaj as a termin's, "Dan 1 · Cijelo tijelo — Cijelo tijelo — srednja razina" (the day's label and the programme's title as they were when it started: the snapshots), "6 od 8 vježbi · 38 min" (the day's exercises now; a day since deleted: "6 vježbi"), the comment; the trainer's view adds "Serije", every exercise's sets folded (`details.sets`). A pass in progress is not there, and nothing on the karton edits or deletes a pass (an open question for the owner); the termin rows are as they were. **The upitnik** (v2 since 26.10.2026, the gym owner's final version; its questions rows he edits since the same day, idea 3): Shape's questionnaire in QMT's clothes (patterns.md §7), one question per screen: for a member the brand alone in the small pill at the top (base.html's `solo_page` flag: no tabs, no account menu; since 26.10.2026 the trainer and the owner, who open it to edit, keep their whole bar, Admin ▾ `.on` and its Upitnik item current: `solo_page = not can_edit_copy`), a 640px column, the title (`upitnik.title`; the intro under it on question 1's screen, the `?error=` alert under the title), a thin `--accent` progress bar counting the questions asked so far and the ones always asked ahead, the part as an eyebrow, the question as the h1, then lettered rows (a choice, yes / no; the chosen one inverted with a ✓, going on ~250 ms after a tap; a multi's rows are checkboxes, several ticked, and "Dalje" goes on, dimmed, `aria-disabled`, until one is) or ten round buttons (a scale, 5 × 2 until ten fit at 40px), a free text with "Dalje" (a text question's, "Gdje te boli?" under the pain question among them), "Nazad" under every question (the first one's back to the guide), and last the consent checkbox (required) with "Spremi upitnik". ONE form holds every question (the script shows one step and the inputs keep the answers; the keyboard's arrows only mark, Enter goes on): without JS it is the whole questionnaire with one submit. **The guide through the training comes first** (29.10.2026, the owner: the gym owner's introduction, "for now put it before the questionnaire"): a step of the one form before question 1 (`#step-vodic`, `_vodic.html`, `/vodic`'s guide): its title (`vodic.title`) the h1 in a question's place, its sections, and at the bottom ONE `.btn`, "Idemo na upitnik!" (`vodic.cta`, full-width on a phone), which goes on to question 1 as "Dalje" does; no bar on its screen (`.at-guide`: the bar counts the questions, its room kept) and no intro (question 1's); question 1's "Nazad" comes back to it. A refill and the editor's preview open on it too; `?od=1` (the guide read: `/vodic`'s button, a refused submission) opens on the first question asked (the form's `data-start` names the step, the guide's `step-vodic` or `step-q<id>`); without JS the guide stands above the questions; in edit mode it is at the top of the stack, every text of it a box, the scoring's summary between it and question 1. **A question asked only after an answer** (27.10.2026, idea 3: "Pita se") carries its condition on its step (`data-parent`, the step it is asked after, and `data-is` a yes / no's value, `data-from` a scale's N, `data-has` an option), which the script checks live, down a chain: it shows only once that answer is given, and a step not asked has its inputs disabled; without JS it shows to everyone, none of its inputs required, and the POST drops it when it was not asked. A refill starts fresh, nothing preselected. The trainer and the owner get the page with no plan of their own, to edit it (Admin ▾ → Upitnik opens `/upitnik` in normal mode, as every page opens; the ✎ pill turns edit mode on); their page holds every question, a hidden one (`.is-off`) a step in edit mode only. In edit mode every step shows, stacked, a hidden one dimmed, his choices are his options lists, the pain sentence (`upitnik.pain_note`) is previewed under the pain question, and each question carries his controls (`.q-ed`, 32px pills: its switch, ↑ / ↓, "Obriši pitanje" (two taps), then a select per setting, Dio, Vrsta, Bodovanje on a scale, Uloga on a scale or a yes / no offering the role its kind can hold; a select saves at a change, `POST /upitnik/pitanje/{id}`, and the page comes back in edit mode; and **"Pita se"** (27.10.2026): "Uvijek" / "Samo ako …", which shows two more pills, "Pitanje" (the questions before it whose answer a condition can name, "16 · " and their first 40 characters; "Samo ako …" picks the nearest) and "Odgovor" (Da / Ne, a scale's 1–10 with "ili više", a choice's or a multi's options, listed by the page from the question chosen), saved together once an answer is chosen, `parent_id` + `condition`; an ↑ / ↓ that would put a question above the one it is asked after says "Potpitanje ne može ići ispred svog pitanja." in the bar at the press, `data-refuse`, and the route refuses it too) and a grey line under them saying what they do ("Dio 2 · skala · boduje se: trening baza", "Dio 4 · skala · uloga: bolovi (7+ početna)"), for a conditional question a second line, "Pita se samo ako pitanje 16 = Da" ("… ≥ 4", "… = Kod kuće s girjom"), in amber when its condition cannot work ("Pita se uvijek — uvjet ne vrijedi: pitanje 16 dolazi kasnije" / "pitanje je obrisano" / "nema odgovor „Da”") or when a hidden question above it mutes it (the step dimmed, `.is-muted`: "… — pitanje 16 je skriveno, pa ni ovo nitko ne dobiva"; a client gets no step of it); a conditional question sits indented under the one it is asked after, 16px a level behind a left hairline (`data-depth`), so a chain reads as one; above the first question the scoring's summary ("Bodovanje: trening baza = 3 pitanja, navike = 4 pitanja. Rezultat = 0,6 × baza + 0,4 × navike.", and when nothing scores the alert "Nijedno pitanje se ne boduje — svi dobivaju početnu razinu."), under the last "+ Dodaj pitanje" (not at 40). The POST refuses them both ("Upitnik ispunjavaju članovi …"). POST validates every question asked (the shown rows: an option must be among the row's options now, each of a multi's ticks too; a question not asked, its condition's answer not given, is dropped) and the consent, else back with the error and nothing stored (on the first question, `?od=1&error=`: the guide was read); then `/treninzi`, the flash naming the level (plus the pain sentence when `pain_high`). **The karton's block** for a v2 response: the razina ramp, part 1's answers as chips ("3 dana tjedno", "45-60 min"; a multi's texts joined with " · "), the score "6,4 / 10", the pain sentence when `pain_high` (the client too); the trainer's view adds a red "Zahtijeva pregled" (`needs_review`), an amber "Bolovi N/10 · where" (`pain_level` ≥ 4, `PAIN_ASK`; where: the answer to the first free-text question asked after the question that holds the pain role now, `upitnik.pain_where`, "" when it has none) and under Odgovori every answer the response holds, under its question as the owner words it now (every row, a hidden one's too; an answer printed by what was stored, a multi's texts joined with " · "), a conditional question's answer indented under the one it is asked after, a step a level (`li.follow d1`–`d3`: "Gdje te boli?" under the pain question, a chain's each further in), and last a deleted question's, under "(pitanje uklonjeno)": nothing is pruned. A v1 row keeps its level, goal and "9/14 bodova", its answers through `QUESTIONS_V1`, and "Stari upitnik — ispuni novi." (the link for the client) |
| `/vodic` | member, staff | **"Vodič kroz trening"** (29.10.2026): the guide through the training on a page of its own, the one `/upitnik` opens on (`_vodic.html` prints both: `guide(href)`), in the questionnaire's clothes (its 640px column; `solo_page` for a member, the trainer and the owner keep their bar and edit its texts here as on `/upitnik`); its button a link to `/upitnik?od=1`, which opens on question 1. For any member, a plan or not; a guest is sent to log in. In no nav and linked from nowhere yet: the owner wants it to greet a client at the first sign-up / the first payment (not built), one link each |
| `/treninzi` | client/trainer | Online programmes — automatic (see below). A client's list: his matched programmes, each card "2 dana" (how many days, 30.10.2026) and the intro's start; none for his combination: "Program za tvoju kombinaciju još se priprema." Staff's: the lead (the matching is automatic, the programmes are his: "Programe slažeš sam: za svaku kombinaciju koju nudiš napravi program pa mu dodaj dane i vježbe. …", 30.10.2026), the table of every programme per razina, its Dani and Vježbe (across its days; "prazno!" with none; a razina with none, "Nema programa za ovu razinu."), then **Novi program** (naziv, cilj, razina, uvod; "Kreiraj i dodaj dane" → its editor, the programme with no day). Opening it makes nothing since 30.10.2026: every programme is Amir's (idea 3) |
| `/treninzi/{id}`, `/treninzi/{id}/dan/{did}` | client/trainer | **A programme is days since 30.10.2026** (stage 2 of the online treninzi spec; idea 3). Its page: crumbs, the title, "2 dana", its intro, then its days as cards, each one link (52px, → at the right): "Dan 1 · Cijelo tijelo" in 700 and, muted, "Preporučeno: ponedjeljak · 7 vježbi" (no weekday: "7 vježbi"); none, "Trening još nema dana." (the trainer: "… — dodaj prvi u uređivanju."); any day opens any time. **The day's page** (the normal layout, a 640px column; the trainer gets "Uredi dan" under its intro): crumbs, the label as the h1, "Preporučeno: ponedjeljak · 7 vježbi", the intro (its line breaks), the intro video first when it has one ("Uvodni video — pogledaj ga prije treninga.", `controls playsinline preload="metadata"`, the clip's dark box), then the whole list, Shape's in QMT's tokens: per section that holds an exercise its caption (ZAGRIJAVANJE, TRENING, ISTEZANJE: display .78rem, letter-spaced, muted), each exercise a native `<details>` (works without JS) whose `<summary>` is the row, 56px: "Vježba n" (counted across the day), the name in 700, the dose at the right ("3 × 10", "2 × 30 s", tabular), under them one muted line, "Odmor između serija: 60 s · Odmor nakon vježbe: 90 s · 8 kg" (each part only when set; the rest after the exercise since 30.10.2026), ▷ at the far right turning down when open; open, the clip (`preload="none"`: twenty rows fetch no twenty clips) or "Vježba još nema videa.", "Jedno ponavljanje: …", the instructions. **Since 30.10.2026 (stage 3, the player)** each day card's muted line ends with the viewer's state ("… · odrađen 2×", "… · u tijeku", nothing for a day never done; `db.day_states`, one query), and the day's page says it under the lead (muted 600: "Još nije odrađen." / "Odrađen 2× · zadnji put 12.11." ("danas", "jučer", another year's date with its year) / "U tijeku — nastavi gdje si stao/la."), then **"Kreni"** (`.btn`, a form, `POST …/kreni`; full width on a phone) or, while a pass is open, **"Nastavi"** (the same form: the route lands on the first exercise the pass has not saved, the last when all are) with "Odbaci započeti trening" beside it (`.act.act-quiet`, `data-confirm` "Odbaciti započeti trening?" / "Spremljene serije ovog pokušaja se brišu. Dan možeš započeti ponovno." / "Odbaci"); a day with no exercise offers none. While a pass is open the list's saved rows carry a green ✓ before the dose. At the bottom **"Povijest"**: the viewer's last five finished passes of the day, a card each ("12.11. · 6/8 vježbi · 38 min · napor 7 · dobro", the comment under it, "Serije" folded: "Goblet čučanj: 10 × 20 kg · 10 × 20 kg · 8 × 20 kg", a timed one "30 s · 30 s", a set with no weight its reps alone) |
| `/treninzi/{id}/dan/{did}/vjezba/{k}`, `…/kraj` | client/trainer | **The player** (30.10.2026, stage 3 of the online treninzi spec; idea 3; the owner: as on Shape Club's Gym Program page, "the set log is good, yes, but default value should be input like in shape club", "the whole list", the swap "we should add it as well"; no first-open tour, no music). `POST …/kreni` opens a pass (`db.start_pass`); `GET …/vjezba/{k}` is exercise k (1-based, the day's display order; k that is none 404; no pass in progress → the day's page), through `_program_or_403` as the day's page (staff may use it, their passes their own; they have no karton). The one-task layout (`solo_page = not user.is_trainer`: a member's small pill, staff's bar), a 640px column; from 1000px two columns, the player and the list (380px) beside it. Top to bottom: **the segmented bar** (a 4px segment per exercise, a saved one `--accent`, the one on screen `--text` at 60%, the rest `--surface-2`), under it "← Natrag" (the day; the pass stays open) · the timer chip (a clock and "0:18" since the pass started, the script's: none without it) · "Završi trening" (`…/kraj`); **the clip** in its dark box (`playsinline loop muted autoplay controls preload="metadata"`; "Vježba još nema videa." on `--surface-2`), round 40px ‹ › at its edges (links to k−1 / k+1; none on the first / the last), a sideways swipe of 60px on the box or the card the same (the script); **the card**: "TRENUTNA VJEŽBA" + "3/8" (+ "✓ Spremljeno" in `--good` once saved), the name as the h1, a refusal's sentence under it, the dose, "Odmor između serija: 60 s · Odmor nakon vježbe: 90 s" (each only when set), the note, "Kako se izvodi" (`<details>`: "Jedno ponavljanje: …", the instructions); swapped, the similar exercise's name, clip and cues and "Zamjena za: <the plan's>" muted. **The set log** (one form, `rows` + `reps_n` / `kg_n`, a timed exercise's `sec_n`): SET · PON. · KG (SEK.), a row per planned set (1 when the plan says none, 12 at most), PON. the plan's reps, KG the last saved log's of that exercise (`db.last_sets`: any pass of the client's, any day; set i's, the last one's past them; empty for none or 0), SEK. the plan's seconds, then one empty row more ("dodatna serija"); "+" (the script) adds rows up to 12; 44px inputs (`type=number`, kg `inputmode=decimal step=0.5`); **"Spremi"** (`.btn`, full width on a phone; "Spremi i završi" on the last) saves (`POST …/vjezba/{k}`, `db.read_sets` → `db.save_sets`: the exercise done, the swapped one when swapped) and goes on to k+1 or `…/kraj`; a refusal is the screen again, 400, its sentence under the name, what was typed kept ("Neispravan broj.", "Upiši bar jednu seriju.", "Najviše 12 serija."); a saved exercise's sets stay in its inputs (a re-save replaces them). **The ✓ per set and the rest bar** (30.10.2026; the owner: "a timer which he can skip, in between sets as well as between exercises, which Shape Club also has"): the set log's last column, SET · PON. · KG · ✓ (a timed one's SET · SEK. · ✓), a round 44px `button.pl-done` per row ("Serija n odrađena", `aria-pressed`; the header's ✓ says "Odrađena serija" to a screen reader), its cells rendered `hidden`, the script's ("+"'s clone carries one); a press marks the row done (`tr.is-done`: its number `--good`, the button `--good-fill`; the inputs as they were) and, when the exercise has a rest between sets (the form's `data-rest`, the item's `rest_seconds`; none for NULL or 0), starts the rest bar with it, afresh when one runs; a second press unmarks the row and starts nothing. The ticks live on the page: nothing is posted, a reload loses them, "Spremi" saves as before. The rest after an exercise (the item's `rest_after_seconds`, the plan's item's when swapped) rides on Spremi's redirect, `…/vjezba/{k+1}?odmor=<s>` (when > 0; never to `…/kraj`, never on Preskoči, ‹ ›, the swipe or the list), whose GET puts it on the form (`data-odmor`: an int 1–3600, anything else ignored; a refused save none) and the bar starts at load. **The bar** (`div.pl-rest`, `role="timer"`, hidden until a rest): fixed at the bottom at every width, the dock's place and glass, 16px from the screen's edges, 640px at most, 64px, `--r-lg`, lifted over staff's ✎ pill; "ODMOR" over the countdown ("0:45", Inter 800, from an end time redrawn every 250 ms, so a tab woken from the background shows what is left), a 4px track whose `--accent` fill drains, and "Preskoči odmor" (a white pill, 44px on a coarse pointer: ends it at once, silently; not "Preskoči", the quiet link's word, which skips the exercise); at zero "KRENI" and "0:00" for about 1.5 s, then it goes, the phone vibrating (`[150, 80, 150]`, only after a tap on the page) and two quiet 880 Hz beeps where the browser allows (the AudioContext made and resumed at the first ✓, a tap, for iOS; a rest that starts at load may end silent, "KRENI" its signal); while it shows the dock is hidden and `.pl` gets room under it (`.has-rest`); leaving the page ends it, nothing is kept. Under it, quiet: "Preskoči →" (k+1, nothing saved; the last's "Preskoči i završi" → `…/kraj`) and, when the plan's exercise has similar ones, **"⇄ Zamijeni vježbu"**, a `<details class="swap">`: "Slične vježbe", a row each (name, tags, ⇄ posting `…/vjezba/{k}/zamjena` with its id; when swapped "Vrati <the plan's>" first, `vrati=1`; any other id: "Ta vježba nije među sličnima."). **The list** (`#popis`): the day's sections and rows (the day page's `.dx-*`), each a link to its exercise, the one on screen ringed in `--accent` (`aria-current="step"`), a saved one a green ✓ before its dose, a swapped one its similar exercise's name "(zamjena)"; on a phone under the player, and a fixed dark pill at the bottom (the topbar's glass, `env(safe-area-inset-bottom)`, lifted over staff's ✎ pill) "Vježbe · 3/8 ✓" → `#popis`, gone from 1000px. **The finish screen** (`…/kraj`, the same layout; no pass in progress → the day's page): "TRENING ODRAĐEN", the day's label as the h1, "6 od 8 vježbi · 38 min" (saved of the day's, the time so far), the osvrt in the questionnaire's clothes: Napor, its ten round buttons (radio, required), Osjećaj, its three choice rows (`FEELING_LABELS`, optional), Komentar (optional), **"Spremi trening"** (`POST …/kraj`, `db.finish_pass`: its length the server's clock) → the day's page `?ok=Trening je spremljen.`; a refused osvrt ("Neispravan osvrt.", the karton's) the screen again with what was chosen; under it "Natrag na vježbe" (the last exercise) and "Odbaci trening" (the accent, `data-confirm`, `POST …/odustani` → `?ok=Započeti trening je odbačen.`, a finished pass never) |
| `/treninzi/{id}/uredi`, `/treninzi/{id}/dan/{did}/uredi` | trainer/owner | **The programme's editor**: its form (cilj, razina, naziv, uvod), its lead ("Trening ima dane; svaki dan ima zagrijavanje, trening i istezanje, a vježbe biraš iz baze vježbi." + "pogledaj kako polaznik vidi →"), then **Dani**: a row per day (`#dan-<id>`): its label (a link to its editor), "ponedjeljak · 7 vježbi" muted, Uredi, ↑ / ↓ (the day trades places and numbers with its neighbour) and ✕ ("Obrisati dan?", the exercises stay in the library); "+ Dodaj dan" (a day after the last, then its editor); "Obriši cijeli trening". **The day's editor** (crumbs to the programme's editor, "Dan N"): its form (Naslov, Preporučeni dan "Bez preporuke" / ponedjeljak … nedjelja, Uvod), **Uvodni video** (the exercise page's video card: upload, replace, remove, the iPhone hint; `dan-<id>-<hex>.<ext>`), then **Vježbe**: every section's caption, its rows or "Nema vježbi."; a row (`#stavka-<id>`) the exercise's name (a link to it in the library), "video ✓" / "bez videa", ↑ / ↓ (within its section) and ✕ (their forms after the list: a form holds no form), and under them the row's own form, Dio, Serije, Ponavljanja, Sekunde, Odmor (s), Nakon vježbe (s) (`rest_after`: the rest after the exercise, before the next one, the player's rest between exercises; 30.10.2026, the lead saying what the two rests are), Napomena, Spremi (two columns on a phone, Dio beside Serije and the two rests side by side, four from 600px, every control 44px on a coarse pointer; a label its column cannot hold on one line wraps, each field's control at its bottom, so a line's controls stay level); empty is none, sets 1–99, reps 1–999, seconds 1–3600, either rest 0–3600 ("Neispravan broj."), reps and seconds both refused ("Upiši ponavljanja ili sekunde, ne oboje."), a note up to 500; a row moved to another section goes last in it; the save comes back at the row (`?stavka=<id>#stavka-<id>`), which carries its own "Spremljeno." or the refusal's sentence, the page's top none (a phone scrolled to the row would not see it; Fable's review, 30.10.2026). "Dodaj vježbu": the library's select (name · tags), a Dio select opening on Trening, Dodaj, "Nova vježba →" (`natrag=` this editor; back with it chosen, `?vjezba=`). "Obriši dan" at the bottom (asks first; its intro video's file goes with it) |
| `/treninzi/vjezbe` | trainer/owner | **"Vježbe"** (Admin ▾'s item after Upitnik, 30.10.2026; its pages light Admin ▾, not the Online treninzi tab): the library of exercises, every one a row in the Croatian alphabet's order (`models.alpha_key`: Č after C, before D), the whole row a link: its name, its tags as chips, "video ✓" (green) or "bez videa", "u N programa" ("u 1 programu", "ni u jednom programu"); a search `?q=` (the name or the tags hold it, whatever its case; blank shows all); "+ Nova vježba"; empty, "Još nema vježbi." with the button |
| `/treninzi/vjezbe/nova`, `/treninzi/vjezbe/{id}` | trainer/owner | An exercise's one form page (the `/admin` pages' look): Naziv, Upute, Što je jedno ponavljanje, Oznake (odvoji zarezom), **Slične vježbe** (every other exercise a checkbox row, the ticked ones first, a filter box the script shows), one POST for all of it (a name taken whatever its case comes back as the page, what was typed kept: "Vježba s tim imenom već postoji."). An existing one's lead says where it is ("U 2 programa: …"; a programme with a razina by its title and the razina, "Booty build (napredna razina)", since 30.10.2026: three live programmes share that title, one per razina, `db.program_name`), then **Video**: none, a file input "Video (mp4, mov ili webm, do 95 MB)" (`VIDEO_MAX_MB`) and the recording hint (upright, 10–30 s, one rep; iPhone's "Najkompatibilnije", or Chrome on Android and Windows cannot play it); one, the clip (`<video controls playsinline muted loop preload="metadata">`), "Zamijeni video" and "Ukloni video" (asks first). `POST …/video` (multipart: mp4 / mov / webm by extension AND by their first bytes, at most `VIDEO_MAX_MB`; the new file stored, the row then names it, the old file deleted) and `…/video/ukloni`. "Obriši vježbu" at the bottom (asks first; `…/obrisi`), refused while a programme holds it: "Vježba je u N programa (A, B, C …) — prvo je makni iz njih." (the programmes named as the lead names them) |
| `/prehrana` | public | MojiMakrosi link (`/nutricionizam` 301s here) |
| `/profil` | any | Basic info form; under it the **Račun** card (the email as plain text, "Registriran/a od …"; back 20.10.2026); a client's link to `/moja-clanarina` (plans, uplate and računi moved there 18.10.2026) |
| `POST /copy/{key}` | trainer/owner | Saves one in-place-edited text (JSON); an emptied text is stored empty since 20.10.2026, except a number (a `required` slot: `price.<plan>.amount`, `addon.*`), whose default comes back; `reset=1` (Zadano) restores the default (a row's cell stays empty too). An announcement's field too, by its virtual key `aktualno.<id>.<field>`, and a gym card's, `dvorana.<id>.<field>`; a rows slot's cell by `index` + `part`, a row by `index` + `remove=1`, a new row by `add=1` |
| `POST /aktualno/nova`, `POST /aktualno/{id}/obrisi` | trainer/owner | Adds an announcement after the last (placeholder texts; at most 8) / deletes one with its photo. Plain forms from edit mode, back to `/#aktualno` |
| `POST /aktualno/{id}/pomak` | trainer/owner | ↑ / ↓ (29.10.2026): `smjer` = `gore` / `dolje` swaps the card with its neighbour in the editor's order (every card, the hidden too; `db.move_announcement`); at either end, for a card gone or any other `smjer`, nothing moves. A plain form from edit mode, back to `/#najava-<id>`, the card, in edit mode (the one-shot flag) |
| `POST /dvorana/nova`, `POST /dvorana/{id}/obrisi` | trainer/owner | The same for the gym's cards: adds one after the last (placeholder texts, no plans; at most 8) / deletes one. Plain forms from edit mode, back to `/#dvorana` |
| `/admin` | trainer | **"Termini"** (Admin ▾'s first item; the page's h1 and title since 26.10.2026): the weekly timetable as an **editable week grid** + one-off termini |
| `/clanarine` | trainer | **"Trenutne članarine"** (Admin ▾'s item; the page's h1 and title since 26.10.2026): the breakdown per client; record cash/card uplate per client per plan. The add form's `sessions` select (grupni's treninga a month) and `tier` select ("Paket (samo online)": the three QMove names, the cards' titles) show only for their plan (an inline script; without JS both show, and the route ignores the one that does not fit); an online row's `tier` select stands on the member's tier, so the next uplata can move him, and the flash names it ("Online trening (QMove PRO): uplata evidentirana — …", 20.10.2026). Each plan's row says what an uplata recorded now buys, under its button: "Uplata produljuje do 1.6. (vrijedi do 8.6.)" (`db.next_cycle`, 29.10.2026; the add form's "Uplata: od danas do …"), and the flash names the same dates ("… — sljedeća 1.6.2026. (vrijedi do 8.6.2026.)"); a lapsed plan whose grace week holds the client's termini says "3 termina na povjerenje — neplaćeno" there in amber (`db.trust_bookings`), gone once an uplata lands. Under its lead a line to the members' page, "Stranica koju vide članovi — cjenik, tekstovi i cijene uređuju se tamo: Moja članarina →" (18.10.2026, when the trainer's and the owner's way there was an account-menu item the owner missed; their nav has the Moja članarina tab since 26.10.2026) |
| `/korisnici`, `/statistika` | owner | Roster + trainer grants; uplate per plan per month. Admin ▾'s last two items, the owner's only |

Media (`data/uploads/`, gitignored) is served ONLY via the auth-gated `/media/{name}` (the exercises' clips and the days' intro videos: staff any, a client one whose exercise is in a day of a programme matched to him, or similar to one that is (the player shows a swapped exercise's clip, 30.10.2026), or whose day is one) — except the announcements' images, public by nature, which `/slika/{name}` serves (only names an announcement holds, cached a year).

## Architecture — the three ideas

**1. One booking mechanism covers everything.** `TrainingSession.capacity = 8` → group
class; `capacity = 1` → individual termin. Concrete sessions come from `SessionTemplate`
rows via **lazy materialization**: viewing a week upserts that week's sessions
(`ON CONFLICT DO NOTHING` on `uq_session_template_start`), clamped to the booking window
— no cron, concurrency-safe. Editing a template prunes future **unbooked** sessions so
they re-materialize; booked ones are never touched. **The booking window** (29.10.2026,
the owner's "the running week and three more weeks"): `db.booking_window(today)` = this
Monday through the Sunday `BOOKING_WEEKS` − 1 (3) weeks on, week-aligned (28 days on a
Monday, 22 on a Sunday); nothing past it is materialized or booked. **An empty termin
closes** `CLOSE_EMPTY_HOURS` (4) before it starts (`db.is_closed`: derived, never stored;
one booking keeps it open to anyone until the start; a canceled one stays canceled), every
kind alike. `_refusal`, which `book()` and the series share, says no in this order:
otkazan, prošao, zatvoren, prozor (past the window), članarina, razdoblje (after the
plan's dospijeće), paket, popunjen, već rezervirano. **A booking can repeat weekly**
(`db.book_series`, offered right after booking a templated session): the same slot on
every later week of the window, cut at the plan's dospijeće (the owner: "all 4 weeks …
that is the hard cap"); each date is materialized and judged by `book()`'s own rules,
full / canceled / closed / already-held dates are skipped and reported, and a spent paket
stops the run; a run that left a date out opens the calendar's dialog (`#seriesDlg`).

**2. Plans gate everything.** Six `PLAN_TYPES` (grupni, individualni, poluindividualni,
rehabilitacija, online, prehrana). Every session carries a `kind`; `book()` refuses
unless the client has an active membership of that kind. `Membership` holds only the
CURRENT cycle: recording an uplata sets `next_payment` a month out and `dospijece` a
week after that, and the plan admits booking until dospijeće passes, termini up to
dospijeće. **The membership month is fixed** (29.10.2026, `db.next_cycle`): it runs from
due date to due date and never moves while the client keeps paying; paying early, in the
grace week, or after dospijeće while that month runs all buy the month that began at the
due date, and only after a whole month unpaid does an uplata start afresh from today (the
old "a lapsed plan restarts from today" let a client pay on the last grace day every month
and get five weeks for four). **The grace week is on trust**: due 1.5., the client books
and trains through 8.5. unpaid, and is locked out after it; `/clanarine` counts a lapsed
plan's termini in that week in amber (`db.trust_bookings`). Every uplata also appends
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
are not enforced. The weekly series is idea 1's (the window and dospijeće bound it).

**3. The online side is automated, never hand-assigned.** The upitnik
(`src/qmt/upitnik.py`) routes a client into a razina (pocetna/srednja/napredna) and a
cilj (cijelo/gornji/donji). Programmes are tagged with that combo and **matching IS the
access** — no per-client hand-outs exist. **Nothing makes, fills or refills a
programme but Amir** (30.10.2026, the owner: "he should be able to create a training
with no exercises, if he does that its his fault, okay? No refilling either way please,
no default, everything modular so that he can change it."): no programme makes itself,
none gets default exercises, and a programme with no day, or a day with no exercise,
stays so for as long as he leaves it. A client is told what is not there yet: a
combination with no programme "Program za tvoju kombinaciju još se priprema.", a
programme with no day "Trening još nema dana.", a day with no exercise "Dan još nema
vježbi.". (Until then the nine (razina × cilj) slots made themselves with default
exercises when the trainer opened /treninzi, `db.ensure_online_skeletons`, which went
with its `_DEFAULT_EXERCISES`, `_DEFAULT_ITEMS` and `DEFAULT_REST`.) Gates stack:
active `online` plan → filled upitnik → matched programmes.
**A programme is made of the library's exercises since 30.10.2026** (stage 1 of
`roadmap/2026-10-29-online-treninzi-spec.md`; the owner: "We should have a database of
exercises which he can choose from and add them to different training programmes that
will be modular. Each exercise will have a video connected to it which will show the
exercise and show what one rep means."): `models.Exercise` (a name, unique whatever its
case; `instructions`; `rep_note`, what one rep is; `video`, a stored clip; free `tags`,
comma-separated, stored cleaned) is a row Amir makes on `/treninzi/vjezbe`, and a
programme's days' items point at it (`exercise_id`, RESTRICT: an exercise a day holds is
not deleted, `db.delete_exercise` names the programmes). Renamed or given a new clip, an
exercise changes in every programme that holds it. **A programme is a list of days since
30.10.2026** (stage 2; the owner: "Dan 1, … Dan N with suggested days in the week but the
user can do them whenever he wants"; per exercise "sets × reps, or seconds, rest between
sets, a note. That is it for now"; a day has sections, "warm up and main"):
`models.ProgramDay` is its place (`position`, "Dan N", dense: `db.delete_day` closes the
gap; unique per programme, DEFERRABLE INITIALLY DEFERRED, so ↑ / ↓ swap two in one
commit), an optional `title` (`label`: "Dan 1 · Cijelo tijelo"), a suggested `weekday`
(0–6 or NULL: a suggestion, never a gate), an `intro` and an `intro_video` (a stored
clip, as an exercise's); `models.ProgramDayItem` is its exercise, its `section`
(`SECTIONS`: zagrijavanje, trening, istezanje; a CHECK), its `position` (unique across the
day, deferred; the display order is section by section, each in position order:
`ProgramDay.by_section`; a row moved to another section goes last in it), `sets`, `reps`
or `seconds` (one of the two, a CHECK), `rest_seconds` (between sets),
`rest_after_seconds` (after the exercise, before the next one: the player's rest between
exercises, 30.10.2026, migration `4f9d6f7103ad`) and a `note`; `dose` words it ("3
× 10", "3 × 30 s", "10 ponavljanja", "30 s", "3 serije"), `rest_text` ("60 s") and
`rest_after_text` ("90 s") the rests. The
spec's full training video is left out (a file over `VIDEO_MAX_MB` cannot pass
Cloudflare: a direct-to-R2 upload or a link, the owner's call). Every write to a
programme's days or their items locks the programme's row, then the day's
(`db._day_locked`). **Similar exercises** (`exercise_alternatives`, one row a pair,
stored from the side whose form ticked the other, read both ways as
`Exercise.alternatives`, unticked on either form the pair goes) are what the player's
swap offers (below). **The player and the history since 30.10.2026** (stage 3; the
owner: a client does a day exercise by exercise, as on Shape Club's Gym Program page;
"the set log is good, yes, but default value should be input like in shape club"; "the
whole list"; the swap, "we should add it as well"; the tick is stored "so that we have a
record of a user's history. He can repeat the training if he wants"; the osvrt after an
online day asks "the same three for online, yes"; no first-open tour, no music): a
**pass** is `models.WorkoutLog` (`workout_logs`, migration `3890252ee50f`), one row per
time a client goes through a day: the client (CASCADE), the programme and the day (SET
NULL: the row keeps `program_title` and `day_label`, snapshots taken at the start, so a
rename or a deletion never garbles the history), `started_at`, `finished_at` (NULL while
in progress), `elapsed_seconds` (set at the finish from the server's clock, finished −
started, never posted), `done` (a JSON object, one entry per exercise saved, keyed by the
day's item id: the exercise done, its name then, its section, the sets `[{"reps": 10,
"kg": 20.0}, …]` or a timed one's `[{"seconds": 30}, …]`, when; a re-save replaces it),
`swaps` (a JSON object, item id → the similar exercise swapped in for this pass), then
the osvrt (`effort` 1–10, `feeling` a `FEELING_LABELS` key or NULL, `note`). **One pass in
progress per client and day**: the partial unique index `uq_workout_logs_open` (`user_id`,
`day_id` WHERE `finished_at IS NULL`), which `db.start_pass` inserts against with ON
CONFLICT DO NOTHING (two Kreni at once open one pass, tested); a day is done again as
often as wanted, a pass each. "Kreni" on a day opens it (or "Nastavi" the one in
progress), the player saves each exercise's set log into it (`db.save_sets`, the row
locked FOR UPDATE: two saves at once keep both entries, tested), may swap an exercise
for one of its plan exercise's similar ones (`db.swap_exercise`: "Ta vježba nije među
sličnima." otherwise; what was saved stays as saved), and the finish screen's osvrt
closes it (`db.finish_pass`: "Neispravan osvrt." for napor outside 1–10 or an osjećaj
that is none; "Trening je već završen." twice); "Odbaci" deletes a pass in progress
(`db.drop_pass`; a finished one never). The day says "odrađen N×" (`db.day_state`; the
programme's cards `db.day_states`, one query), lists the last five passes with their sets
(`db.passes`), and the karton lists every finished pass beside the termini. The next
pass prefills each exercise's weights from the client's newest saved entry for that
exercise, any pass, any day (`db.last_sets`). Staff may use the player; their passes are
theirs and show on the days only (they have no karton).
Migration `4c2e8a6f1d39` made the items typed by hand until then into library rows:
each body split (`split_body`: a first line that starts with a digit is a dose, the
item's note; the rest the exercise's instructions; prod's every body was "DOSE\nCUE"),
one exercise per name (trimmed, compared casefolded), the first cue its instructions,
the first video its clip; an image, a second clip and a cue not kept are printed to the
log, their files left in storage. Migration `7c3bf996c983` then made each programme's
items its Dan 1, in section trening, no rest, each note parsed by its own `parse_dose`
("3 × 8 · 8 kg" → 3 sets, 8 reps, note "8 kg"; "3 × 20 s" → 3 × 20 seconds; "3 × 5 (s
koljena)" → note "s koljena"; a note that starts with no dose kept whole), and dropped
`program_items`. No programme has defaults since 30.10.2026 (above): the demo's nine
are the dev seed's own tables (`scripts/seed_demo.py`: `DEMO_EXERCISES`, library rows,
the cues only, one row per name; `DEMO_PROGRAMS`, each programme's Dan 1 in section
trening, each item its razina's dose; 60 s of rest, `DEMO_REST`: what the app's
defaults were, name for name and dose for dose), and the live site's are Amir's.
**What stays code**: the name rule (casefolded under the table's lock,
`_EXERCISES_LOCK`: the dev and test databases' C locale folds ASCII only, so the
`lower(name)` index alone would let "Čučanj" and "čučanj" both in), the alphabet's order
(`alpha_key`), the clip's formats and cap (`app._save_video`: mp4 / mov / webm by
extension and by their first bytes, ISO base media's `ftyp` or WebM's EBML,
`config.VIDEO_MAX_MB`, default 95: Cloudflare's free plan refuses a body over 100 MB
with its own page, so 95 leaves the multipart room; no transcoding; a stored file is
named by the caller's prefix, `vjezba-<id>-…` or `dan-<id>-…`), a day item's numbers
(`db.ITEM_LIMITS`: sets 1–99, reps 1–999, seconds 1–3600, either rest 0–3600, a note
up to 500) and the dose's words (`ProgramDayItem.dose`, `models.plural`'s Croatian forms);
since 30.10.2026 a logged set's numbers (`db.SET_LIMITS`: reps 0–999, kg 0–500 in steps
of 0.5, "2,5" or "2.5", seconds 0–3600; at most `db.MAX_SETS`, 12; a row with every
field empty dropped, an empty field beside a number 0; `db.read_sets`, checked again by
`save_sets`), their words (`models.set_text`: "10 × 20 kg", "10" with no weight, "30 s";
`kg_text` "2,5"; `duration_text` "38 min", "1 h 05 min"), the one-pass-in-progress index
and the server's clock for a pass's length.
**The upitnik is v2 since 26.10.2026**, the gym owner's final version, and **its
questions are rows since the same day** (`models.UpitnikQuestion`; the owner: "so that
Amir can also add or remove questions from the questionnaire"): he adds (at most 40,
`db.MAX_UPITNIK_QUESTIONS`), removes, hides, reorders and classifies them himself in edit
mode on /upitnik. A row has its place (`position`), a `part` (1–4, the heading above
it), a `kind` (`choice`, `multi` = several options ticked, `scale` 1–10, `yesno`,
`text`), its words (the text, a choice's or a multi's options, a scale's two ends), a
`scoring` (the group a scale joins: `baza` = trening baza, `navike`; only a scale
scores), a `role` (`pain`, a scale, and `injuries`, a yes / no: at most one of each, a
partial unique index; a role asks nothing itself since 27.10.2026, below) and `shown`
(a hidden question is asked of nobody and scores nothing). **Branching (27.10.2026**,
the owner: "add a subquestion … 'Jeste li imali porod' and if the answer is yes … ask
if she had it in the last year and then if she says yes … if it was C-section or not
etc."): any question may be asked only after a given answer to an earlier one,
`parent_id` (the question it depends on; a foreign key to the table, `ON DELETE SET
NULL`) and `condition` (String(80): `"yes"` / `"no"` for a yes / no, an option's TEXT
for a choice or a multi, asked when it is among the answers, `">=N"` for a scale, N
1–10; `""` asks it always). Chains follow by construction: a question is asked when its
parent was asked and answered so (`upitnik.steps` / `is_asked` / `asked_of`, `read`; the
page's script the same, live). **A hidden question hides the questions asked after it**,
down the whole chain (Fable's review the same day: a gym owner who hides "Jeste li
imali porod?" means its questions too): `Question.muted` (and `muted_by`, the hidden
one's place), asked of nobody whatever their own switch says, scored by nobody (nor
counted in the summary), still indented under it; so both routes build from every row
and give a client `upitnik.client_steps` (the shown, unmuted steps), and the editor gets
them dimmed (`.is-muted`) with an amber line, "Pita se samo ako pitanje 16 = Da —
pitanje 16 je skriveno, pa ni ovo nitko ne dobiva". A condition that cannot work
otherwise, its parent deleted (the key nulled, the condition kept), placed after it, or
no longer able to give that answer (its kind changed, the option removed), asks the
question always (`Question.void`), and the editor's line says so in amber; a deletion
says so first, at "Obriši pitanje"'s first tap on a question shown ones hang under
("Pitanja koja ovise o njemu ostaju i pitat će se svakoga.", in the bar). **An option
re-worded carries into the conditions that named it** (`db.set_upitnik_question_options`,
`renamed`: in the same save, under the questions' lock; not past 80 characters, the
column, where the condition stays and goes amber). The editor's "Pita se" sets
it (`POST /upitnik/pitanje/{id}`, `parent_id` + `condition` posted together;
`upitnik.condition` refuses a parent after it, a circle, a free text, an answer of the
wrong shape or one it does not have, an option past 80 characters), and a move that
would put a question above the one it is asked after is refused ("Potpitanje ne može
ići ispred svog pitanja."). **The roles' follow-ups are such questions since**:
migration `5c1e7a9d2b48` turned each role question's `followup_text` into a `text` row
right after it (the pain question's at `">=4"`, the injuries question's at `"yes"`), a
`followup_text` on a yes / no without a role likewise at `"yes"` (prod's q20; dropped
anywhere else), renamed the stored `q<id>b` answers to the new rows' keys, and dropped
the column. The roles keep their rules (`pain`: the pain rule and the karton's flag,
whose "where" is `upitnik.pain_where`, the answer to the first `text` question asked
after the pain question, "" without one; `injuries`: `needs_review`). His questions
start it (`copy.UPITNIK_DEFAULT_QUESTIONS`, the demo seed's; migration `3f8a6c2d9b71`
folded the old `upitnik.q<n>.*` slots into ids 1–15): part 1, q1–q4 (choices: the goal,
days a week, minutes, where); part 2, q5–q11 (the scored scales: q5–q7 baza, q8–q11
navike); part 3, q12–q13 (scales, information for the trainer); part 4, q14 the pain
question (how often it hurts) with q16 "Gdje te boli?" under it, asked at 4 or more,
and q15 the injuries question with q17 "Opiši ukratko." under it, asked at Da (16 and
17: the ids the migration gives them on a database that starts from the fifteen).
**What stays code** (`upitnik.py`, working on the live rows,
`db.upitnik_questions(shown=True)`): the steps (one per row, each with its condition
as far as it can work), what a submission must hold, the owner's formula, his
thresholds and his safety rules. The formula: "Trening baza = prosjek pitanja 5, 6 i 7.
Navike = prosjek pitanja 8, 9, 10 i 11. Rezultat = 0,6 × trening baza + 0,4 × navike",
over whatever scales score now (each group the mean of its shown scales; a group with
no question gives its weight to the other; none at all: every result početna, score
0.0), to one decimal, worked in exact fractions and rounded half up: up to 4 početna,
4,1–7 srednja, 7,1–10 napredna. His safety rules: the pain question at 7 or more
(`PAIN_HIGH`) is početna whatever the score, with a word to see the trainer
(`pain_high`, `upitnik.pain_note`), and at 4 (`PAIN_ASK`) the trainer's karton flags
it; where it hurts is asked by its own question's condition since 27.10.2026 (`">=4"`
as the migration and the defaults made it); the injuries question's Da flags the
profile for the trainer (`needs_review`). A conditional question counts only when it
was asked (a scale's score too). The questionnaire
decides the **level only** for now (the owner: "The questionnaire will only determine
the difficulty level of the trainings"): every v2 response's `goal` is `cijelo`, so a
client gets the level's whole-body programmes; q1–q4 are stored for the later routing by
equipment / type of training (and the later "change your level and type"), and route
nothing yet. **The words around the questions stay copy slots** (`upitnik.*`: the title,
the intro, the parts' headings, Da / Ne, the consent, the buttons, the pain sentence; no
emoji, the owner's call of 26.10.2026). `OnboardingResponse` carries `version` (2;
migration `e6564d9234b8` made the rows already there 1), a decimal `score`,
`pain_level` (the pain question's answer, NULL with none asked), `pain_high`,
`needs_review`, `consented_at`; its `answers` JSON is keyed by the row, `q<id>` (ids
come from a sequence and are never given twice; the old follow-ups' `q<id>b` became
their questions' keys, `5c1e7a9d2b48`), and stores a choice as the option's TEXT at the
time (never an index: a re-wording never garbles an old answer), a multi as the list of
the options' texts, a scale as an int, Da / Ne as a bool, a free text as a string, a
question not asked absent. **A client's answers are never pruned**: a question deleted
since still has its answers printed on the karton, under "(pitanje uklonjeno)" (an old
`q<id>b` the migration had no question for too); a conditional question's indented under
the one it is asked after. A v1 row (five questions + a goal, `QUESTIONS_V1`) still
counts as filled, and its goal still routes, until the client fills the new one.

| Path | Role |
|---|---|
| `src/qmt/config.py` | `.env`, `OWNER_EMAIL`/`ALLOWED_EMAILS`, booking knobs, `VIDEO_MAX_MB` (an exercise's clip, MB), prod guards |
| `src/qmt/copy.py` | The texts a trainer/owner may edit in place: slot → default text, label; a 2000-character cap, no design limit since 16.10.2026; an emptied text stays empty since 20.10.2026 but a `required` slot's (the numbers, `price.<plan>.amount` / `.year_amount`, `addon.*`), whose default comes back; lists (`ListSlot`; the extra lines, `*.extra`, are lists that start empty), tables of rows (`RowsSlot`: the opening hours, `load_rows` / `dump_rows`, a new row's `ROW_BLANK`), on/off flags (`FlagSlot`) and photos (`ImageSlot`); the prices (`price.<plan>.*`, `addon.*`, defaults `REFERENCE_PRICES` / `YEARLY_PRICE` / `MOJIMAKROSI_ADDON`), every price the site shows; the `/moja-clanarina` cards' one text each (`cjenik.<plan>.text`, defaults `PLAN_TEXTS` + `PLAN_TEXT_END`); how an announcement's fields are edited (`ANNOUNCEMENT_SLOTS`, `ANNOUNCEMENT_COLUMNS`), a new card's placeholders (`ANNOUNCEMENT_BLANK`) and the seed's two examples (`ANNOUNCEMENT_EXAMPLES`); the same for a gym card (`GYM_CARD_SLOTS`, `GYM_CARD_COLUMNS`, `GYM_CARD_BLANK`, `GYM_CARD_EXAMPLES`); the upitnik's words around its questions (`upitnik.*`, the parts' headings `UPITNIK_PARTS`), and for its questions, rows since 26.10.2026: the gym owner's questions as they start (`UPITNIK_DEFAULT_QUESTIONS`: the fifteen, ids 1–15, and q16 / q17 asked after q14 / q15, the seed's; the migrations carry their own copies), a new question's placeholders (`UPITNIK_BLANK`), how a question's words are edited (`UPITNIK_QUESTION_SLOTS`: text, options, low, high) and where a row keeps them (`UPITNIK_QUESTION_COLUMNS`); the guide through the training (29.10.2026: `VODIC_SECTIONS`, the gym owner's eleven sections as they start, each the four slots `VODIC_PARTS` names, `vodic.<n>.h` / `.text` / `.points` / `.after`, and `vodic.title` / `vodic.cta`) |
| `src/qmt/models.py` | `User` (+profile fields), `SessionTemplate`, `TrainingSession`, `Booking`, `Membership`, `Payment`, `OnboardingResponse`, `TrainingLog`, `Program`(level/goal; `days`)/`ProgramDay` (a programme's day: its place, `title`, `weekday`, `intro`, `intro_video`; `label`, `by_section`; its position constraint deferred)/`ProgramDayItem` (a day's exercise: `section`, its place, `sets`, `reps` or `seconds`, `rest_seconds`, `rest_after_seconds` (30.10.2026), `note`; `dose`, `rest_text`, `rest_after_text`), `Exercise` (the library of exercises: `alternatives`, read both ways from the `exercise_alternatives` table, `tag_items`; `alpha_key`, the Croatian alphabet's order), `WorkoutLog` (a client's pass through a day, 30.10.2026: the snapshots, `done` / `swaps` JSON read through `done_items` / `swap_items`, `done_count`, `in_progress`, `elapsed_text`, `date`, `lines(order)` the history's "Serije"; one in progress per client and day, a partial unique index; `kg_text`, `set_text`, `duration_text` say its numbers), `SiteCopy`, `Announcement` (the landing's cards), `GymCard` (the gym's cards; `plan_keys`, `point_items`, `extra_items`), `UpitnikQuestion` (the upitnik's questions; `option_items`; its position constraint deferred, so ↑ / ↓ swap two in one commit; one row per role, a partial unique index); `PLAN_*`, `ONLINE_TIERS` / `ONLINE_TIER_SLOTS` (the online plan's QMove tiers and their cards), `FEELING_LABELS`, `SECTIONS` / `WEEKDAYS` (a day's sections in their order, its suggested weekday), `plural` (a noun after its count, "2 vježbe"), `PAYMENT_METHODS` |
| `src/qmt/db.py` | Queries + rules. **`book()` locks the session row FOR UPDATE** and re-counts inside the lock (tested); `add_announcement` locks the `announcements` table, so the cap of 8 (`MAX_ANNOUNCEMENTS`) holds when adds race (tested); `add_gym_card` the same for `gym_cards` (`MAX_GYM_CARDS`), and every structural write to `upitnik_questions` (add, move, a setting) takes that table's lock, so the cap of 40 (`MAX_UPITNIK_QUESTIONS`) holds and no role lands on two questions when editors race (tested); a question that comes with its own id (the seed's) moves the id sequence past it, never back; every write that may set an exercise's name (a new one, a save) takes `exercises`' lock (`_EXERCISES_LOCK`), so a name is taken once, whatever its case, when saves race (tested); every write to a programme's days or their items locks the programme's row, then the day's (`_day_locked`), so two "+ Dodaj dan" never take one number (tested); the passes (30.10.2026): `start_pass` (ON CONFLICT DO NOTHING on the partial index: two Kreni at once open one pass, tested), `open_pass`, `get_pass`, `save_sets` / `swap_exercise` / `finish_pass` / `drop_pass` (each takes the pass's row FOR UPDATE: two saves at once keep both entries, tested), `passes`, `last_sets`, `day_state` / `day_states`, `day_sizes`, `read_sets` (a posted set log's rules); `update_day_item` (an item's section, numbers and note; `ITEM_LIMITS`, `rest_after_seconds` among them since 30.10.2026, its argument after `rest_seconds`); `program_name` ("Booty build (napredna razina)", the library's pages and `in_programs`) |
| `src/qmt/upitnik.py` | What stays code of the upitnik, v2 (26.10.2026), over the live rows: `steps` (the rows → the screens, one per row with its condition as far as it can work, `void` when it cannot, `muted` under a hidden question; `Question`), `client_steps` (a client's: shown, unmuted, built from every row), `is_asked` / `meets` / `fits` / `asked_of` (branching, 27.10.2026), `read` (a posted form → the stored answers, or ValueError), the owner's `score` (exact fractions, half up) / `level_for`, `evaluate` (the two safety rules on top: `PAIN_HIGH`, `needs_review`; `PAIN_ASK` is the karton's pain flag), `settings` (a question's part, kind, scoring, role, shown and their rules, the editor's refusals), `condition` (Pita se's rules), the editor's `setting_line` / `condition_line` / `scoring_summary` / `blocked_moves` / `short` / `answer_choices`, the karton's `answer_rows` (every answer kept, a conditional one's depth, "(pitanje uklonjeno)"), `chips`, `pain_where`, `score_text` ("6,4 / 10"); `KINDS`, `SCORING`, `ROLES`; `GOAL` (every v2 response's, `cijelo`); `LEVELS`, `GOALS` (the programmes' cilj); `QUESTIONS_V1` / `MAX_SCORE_V1` / `answer_rows_v1`, frozen, to read an old row. No word of it: those are the rows' and the copy slots' |
| `src/qmt/auth.py` | bcrypt + signed email tokens (verify 24 h; reset 1 h, single-use) |
| `src/qmt/mailer.py` | Only Resend importer. Also `send_new_user_notice` → owner hears about each first verification |
| `src/qmt/reminders.py` | Email podsjetnici (pre-dospijeće + day-before termin), claim-idempotent via the `reminders` table; app lifespan ticks every 6 h, `scripts/send_reminders.py` forces a pass |
| `src/qmt/storage.py` | Media backend: local disk, or Cloudflare R2 when the four `R2_*` vars are set (then `/media` 307s to presigned URLs); `stream()` hands out a stored file's bytes, for `/slika`, which proxies the bytes so its public URL stays cacheable |
| `src/qmt/payments.py` | Stripe: Prices for /moja-clanarina's checkout tier picker and tier switch (cached), Checkout + portal sessions, signed webhook → `record_payment`. Tolerates both invoice shapes (pre/post 2025 API) |
| `src/qmt/web/app.py` | All routes. `current_user()` per route; `PLAN_LINKS` maps an active plan to the page it unlocks; `/copy/{key}` takes a slot's key or an announcement's virtual key (`aktualno.<id>.<field>`, `_announcement_field`) or a gym card's (`dvorana.<id>.<field>`, `_gym_card_field`) or an upitnik question's (`upitnik.<id>.<field>`, `_upitnik_field`); `/upitnik/pitanje/…` are the editor's question routes; `/treninzi/vjezbe…` the library's (declared before `/treninzi/{program_id}`, which would take "vjezbe" for an id), `/treninzi/{id}/dan…` a programme's days (`_program_day`, `_day_item`: a day not the programme's, an item not the day's, 404), the player's (30.10.2026: `…/kreni`, `…/vjezba/{k}` (`?odmor=`: the rest after the exercise before, from its save's redirect) and its `…/zamjena`, `…/kraj`, `…/odustani`; `_pass_day`, `_player`, `_log_rows` the set log's rows and their prefill, `_finish_page`, `_state_line`), `_diary_rows` the karton's diary (termini and passes), `_save_video` a clip's upload (an exercise's or a day's intro video, named by a prefix), `/media/{name}` an exercise's clip or a day's intro video |
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
  with their tabs; a page that is one task (the upitnik, `{% set solo_page = not can_edit_copy %}`
  at its top, 26.10.2026) gets the small pill with the brand alone, no tabs and no
  avatar, as the auth pages keep the brand alone: a member's, who fills it (staff
  open it to edit it and keep their bar). **The tabs come in two groups since
  26.10.2026** (the owner: the tabs he shares with the members in one, "the tabs
  which are there and different because I am an admin" in another). A client's
  row: Početna · Raspored · Karton · Online treninzi (while an online plan runs,
  `show_online`) · Moja članarina · Prehrana. Staff's (the trainer, the owner): the
  same row without Karton (staff have none of their own), then **"Admin ▾"**, a
  dropdown in the account menu's component (`.menu`, one script for both: a click
  opens it, another shuts it, so do a click outside and Escape, one menu open at a
  time): Termini (`/admin`), Trenutne članarine (`/clanarine`), Upitnik
  (`/upitnik`), Vježbe (`/treninzi/vjezbe`, the library of exercises, 30.10.2026:
  under /treninzi, yet its pages light Admin ▾, not Online treninzi) and, the
  owner's only, Korisnici and Statistika. The tab is
  `.on` while one of its pages is open, that item `aria-current="page"` (an accent
  bar and bold); the menu hangs under its tab, left-aligned to it, moved in by the
  script where the window's edge is nearer than the menu is wide. No item opens
  its page in edit mode (Upitnik's `?uredi=1`, which did, went the day it
  came, 26.10.2026): staff land on every page in normal mode, its ✎ pill
  there to press (the copy convention's edit mode). The wordmark shows in full only when the room the tabs leave allows it, otherwise
  "QMT": a container query on `.brand-slot`, never a window breakpoint — the pill is
  capped at 1100px, so the window width says nothing about the room inside it.
  No bar has more than six tabs (seven or more would run tight); all tabs tighten
  ≤1200px and fold into the ☰ drawer ≤900px: a client's drawer is the one plain
  list, staff's two sections under small captions, "Kao član" (the member's tabs)
  and "Admin" (the menu's items as rows; the Admin tab is no row there), a hairline
  between them; a drawer taller than the window scrolls inside itself. Tabs never
  wrap their own label. The avatar opens the account menu (identity header: the
  name over the email, one line with an ellipsis on a desktop and the whole
  address in its title, wrapped ≤900px where there is no hover; then Profil, the
  theme toggle and Odjava, for everyone: since 26.10.2026 the Moja članarina tab
  is everyone's one way to that page, so the menu has no item for it).
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
  again and stores the text in `site_copy`. **Edit mode belongs to the page**
  (26.10.2026, the owner: "when I go to a tab as an admin, please dont make it
  editable but default"): every page opens in normal mode, the ✎ pill on
  each, and leaving the page ends it (a tab, the menu, a link, a reload by
  hand; Back / Forward too, which can bring a page out of the browser's cache:
  `pageshow`). The one way it outlives a load is the editor's own forms that
  reload the page ("+ Dodaj najavu", "Obriši najavu" and a card's ↑ / ↓,
  "+ Dodaj karticu" / "Obriši karticu", /upitnik's "+ Dodaj pitanje", ↑ / ↓,
  "Obriši pitanje" and a question's setting or switch): right before one
  goes it sets a one-shot `sessionStorage['qmt-editing-once']`, and the next
  load reads it, drops it and turns edit mode on, so the editor lands back
  where he was (until then the tab kept edit mode on at every load).
  **No per-box limits since
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
  table (`models.Announcement`: `position` = the editor's order, `shown`,
  five texts, `image`), up to 8 (`db.MAX_ANNOUNCEMENTS`), which the gym owner
  adds, hides, deletes and reorders himself. The editor edits a card as it edits slots,
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
  offered (and refused with "Najviše 8 najava."). **Moving** (29.10.2026,
  the owner: "Lets make it so that Amir can change the order of these
  announcement pages"): each card's ↑ / ↓ (`form.ed-ann-mv`, after the
  photo's pills: /upitnik's `.ed-mv` pills, base.html's since then; one
  tap, nothing asks first) post `smjer=gore` / `dolje` to `POST
  /aktualno/{id}/pomak`, which swaps the card with its neighbour in the
  editor's order, every card's, a hidden one's too (`db.move_announcement`,
  under the table lock `add_announcement` takes; the two positions trade in
  one flush, which is why `uq_announcements_position` is DEFERRABLE
  INITIALLY DEFERRED since migration `b18ebed39701`, as the upitnik's is).
  ↑ on the first card and ↓ on the last are disabled. The page comes back
  at the card, `/#najava-<id>` (the editor's article carries that id, a
  visitor's none), in edit mode (the one-shot flag). The slot types `FlagSlot`
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
  **The upitnik's questions** (/upitnik, 26.10.2026: the fifteen were
  fixed in code and only their words slots, `upitnik.q<n>.*`, until
  migration `3f8a6c2d9b71` made them rows 1–15) are rows the same way:
  `upitnik_questions` (`models.UpitnikQuestion`, idea 3), up to 40, their
  words edited through virtual keys `upitnik.<id>.<field>` on `POST
  /copy/{key}` (`copy.UPITNIK_QUESTION_SLOTS`: `text`, `low`, `high` as
  slots, `options` item by item as a list slot, two at least, "Pitanje
  treba bar dva odgovora."; a follow-up's `followup_text` is no key since
  27.10.2026, the follow-ups are questions; an emptied text stays empty and
  "Zadano" is a new question's placeholder, `copy.UPITNIK_BLANK`: "Novo
  pitanje", "Prvi odgovor" / "Drugi odgovor", a scale's ends "1 = …" / "10
  = …"; the bar says "Pitanje 7: tekst", the number its place). What a
  question is and does is no text: `POST /upitnik/pitanje/{id}` (JSON, a
  field at a time: `part`, `kind`, `scoring`, `role`, `shown`, and since
  27.10.2026 "Pita se"'s pair together, `parent_id` + `condition`, which
  `upitnik.condition` checks: an earlier question, no circle, no free
  text, an answer it can give; `upitnik.settings` holds the rest: only a
  scale scores, the pain question is a scale and the injuries one a yes /
  no, taking a role another question holds moves it, a change of kind
  keeps the row and its answers but is refused while the question scores
  or holds a role its new kind cannot (a condition on it its new kind
  cannot meet is let go: that question is asked always, its line in
  amber), and a choice or a multi gets two placeholder options when it
  has fewer; an option re-worded in place carries into the conditions
  that named it, `_renamed` → `db.set_upitnik_question_options(renamed=)`).
  In edit mode each question's first line is its controls (`.q-ed`):
  its switch (an `.ed-flag` posting to that route, `data-url` /
  `data-field`, the page drawn again: `data-reload`), ↑ / ↓ (`POST
  /upitnik/pitanje/{id}/pomak`, `smjer=gore|dolje`), "Obriši pitanje"
  (`button.ed-q-x`, two taps, `POST /upitnik/pitanje/{id}/obrisi`: the
  answers clients gave it stay; the questions asked after it are asked
  always then, their lines in amber, which its first tap says in the bar
  on a question shown ones hang under, `data-warn`; a hidden question
  mutes them instead, `.is-muted`) and a select per setting
  (`label.ed-set`, saved at a change; "Pita se" three in one `.ed-if`,
  saved together once an answer is chosen, base.html's `ask`, the answers
  listed by upitnik.html's script), then the grey line of what they do
  (`.q-ed-line`, and a conditional question's `.q-ed-if`, `.void` in
  amber); the scoring's summary sits above the first (`.q-sum`), "+ Dodaj pitanje"
  under the last (`.q-add`, `POST /upitnik/pitanje/nova`: a scale in part 2
  that scores nothing; "Najviše 40 pitanja." at the cap). A question sits
  inside the questionnaire's one form, and a form holds no form: its move,
  delete and add buttons name forms after it (`form="q-mv-<id>"`, …). Each
  comes back to `/upitnik#step-q<id>` in edit mode.
  **The guide through the training** (29.10.2026, the owner: "This should
  again be editable text which Amir can change as he likes") is slots,
  `vodic.*`: the gym owner's text in eleven sections
  (`copy.VODIC_SECTIONS`, registered by a loop), each the same four:
  `vodic.<n>.h` (the heading, an h2), `vodic.<n>.text` (lines),
  `vodic.<n>.points` (a `ListSlot`, up to 12: the offer cards' bullets)
  and `vodic.<n>.after` (lines under the list), any of them empty; then
  `vodic.title` (the h1) and `vodic.cta` (the button). Their labels name
  the section ("Vodič 5: naslov", "Vodič 5: stavka 2"). None is required:
  an emptied one prints nothing for a reader (no h2, no p, no ul; a
  section with all four empty no box) and an empty box for the editor in
  edit mode, which outside it takes no room. No emoji (the owner's word;
  his bullet marks are the list's dots) and no consent line (the
  questionnaire asks for it at its end, `upitnik.consent`). One partial,
  `_vodic.html`, prints it wherever it goes (`/upitnik`, `/vodic`; later
  the first sign-up and the first payment), its look base.html's
  (`.vodic`).
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
  calendar buttons; a termin the trainer canceled can always be dropped).
  A termin nobody has booked closes `CLOSE_EMPTY_HOURS` (4) before it starts
  (`db.is_closed`); one with a booking stays open until it starts. Termini can
  be booked in the running week and `BOOKING_WEEKS` − 1 more (`BOOKING_WEEKS`
  = 4, `db.booking_window`), never past the plan's dospijeće. The three knobs
  are env vars (DEPLOY.md); `BOOKING_HORIZON_DAYS` is gone.
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
   Fiskalizacija 2.0 flow (mandatory since 1.1.2026, fiscalized račun per B2C charge). And one rule to settle before the keys: **the fixed membership month
   (29.10.2026) against a card subscription's own cycle**: a lapsed member who
   subscribes by card is charged on checkout day, while `record_payment` continues
   the month from the old due date, so the card's "obnavlja se" date would come
   before Stripe's real charge; the likely answer is that a card subscription
   starts a fresh month from checkout day (Stripe's cycle is the truth for card
   payers), decided when card payments return.
5. ⏳ Owner's own content: landing/service copy, exercise videos. The R2 storage
   layer is BUILT (`storage.py` + `scripts/migrate_media_to_r2.py`) — activating it
   is just the four `R2_*` vars on Railway; until then `data/uploads` stays ephemeral
6. ⏳ Mini-kuharica (30–50 recipes) + deeper mojimakrosi link-up

See `roadmap/2026-09-03-owner-voice-note.md` for the owner's own wish list and
`roadmap/STATUS.md` for where the last session left off.
