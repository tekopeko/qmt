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
/korisnici and runs the gym day to day. The owner is staff by rule (26.11.2026, the owner:
"can we add everything the trainer sees the admin (me) sees"): he sees and may do
everything a trainer does whatever his trainer flag (`app._is_staff`, which every staff
decision asks, templates through `can_edit_copy`), and keeps what is his alone: the roles
(/korisnici), /statistika and the record of acting as a member (/kao/zapisi).

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
createdb qmt && alembic upgrade head       # schema (Alembic = source of truth)
python scripts/seed_demo.py                # dev RESET: users, timetable, plans, content
python serve.py [--reload] [--port 8100]   # 8100 — 8000 is mojimakrosi's local port

createdb qmt_test                          # once
pytest -q                                  # 703 tests, must stay green (about 17 min)
```

Demo logins: `trener@qmt.local/trener123` (trainer **and** owner locally, via
`OWNER_EMAIL` in `.env`), `ivan@qmt.local/lozinka123` (has grupni + individualni +
online plans, online on the QMove PRO tier, filled upitnik (v2: srednja, 6,4 / 10, no
flags), diary entries, one feedback prompt pending, two finished passes of his online
Trening 1 "Cijelo tijelo", Goblet čučanj at 16 then 20 kg, none in progress; that
day's Glavni dio A is a circuit since 24.11.2026, 2 kruga, 90 s after a round, no
pause between its four exercises since 25.11.2026, the seed's `DEMO_CIRCUIT`, so the audit walks one;
since 26.11.2026 his gym training of yesterday's group termin at 18:00, filled in: since 27.11.2026
three Stanica, every set ticked, Goblet čučanj's rated 8/10, an osvrt, `GYM_TRAINING` / `seed_gym_training`
(every block done: its page the "what next" card); and the group termin that ended two hours ago, its
training open and with no block, the one the login's prompt asks for (its page the template chooser);
and a training of his outside a termin today made from "Kružni trening", its Stanica done (Goblet čučanj
3 × 10 · 16 kg, rated 7), its Kružni set's four rows filled (Iskorak unatrag 10 × 8 kg, Sklekovi,
Veslanje u pretklonu 10 × 10 kg, Plank 30 s), 90 s after a Krug, Krug 1 saved, Krug 2 open, then an empty
Stanica and an empty Kružni set after them (`GYM_STATION` / `GYM_ROWS` / `GYM_KRUG` / `seed_gym_template`):
the audit's client walk opens all three, `gym:filled` / `gym:open` / `gym:krug`, the empty two,
`gym:stanica` / `gym:setup`, and the filled one's osvrt, `gym:osvrt`; the seed puts the two templates
back too, `seed_gym_templates`),
`ana@qmt.local`, `sara@qmt.local` (deliberately **no plan** — demos the booking gate),
all `lozinka123`. Since 26.11.2026 the seed also makes one dvoranski programme, the
trainer's template "Predložak — kružni trening" (srednja, cijelo; `TEMPLATE`,
`seed_template`): its Trening 1 empty slots alone, two in Zagrijavanje ("mobilnost",
"aktivacija"), four in Glavni dio A, renamed "Krug 1", a circuit of 3 rounds, 90 s after a
round ("čučanj", "potisak", "povlačenje", "core", 10 reps each), one in Istezanje; no client
sees it, and the audit walks its editor and its day page as the owner (since 27.11.2026 no gym
training is made from it, and since build 3 of the dvoranski treninzi no form makes a new dvoranski
programme: this one stays staff's, to edit or delete, as every one there). The audit's owner walks the
gym training's templates too: their list and "Kružni trening"'s editor (`/dvoranski/predlosci`,
`gymtpl:Kružni trening`).

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
| `/` | public | Landing: hero = kicker, headline, then **`#aktualno`**: the owner's announcement cards for the month, any number up to 8, rows of the `announcements` table in the editor's order (chip, title, when, a few lines, a grey "Javi nam se" → `/#kontakt`; added in edit mode with "+ Dodaj najavu" (placeholder texts to retype, last), deleted with each card's "Obriši najavu" (two taps) and moved one place with its ↑ / ↓ (one tap, 29.10.2026); each switched off by the editor, gone when all are; each optionally over a photo of the owner's (uploaded in edit mode, shrunk to a 1600px JPEG, stored like other media, in R2 on prod), then Shape's photo card: glass chip on top, white type and a white pill at the bottom): one card per view at every width, as wide as the row (the screen less the gutter on a phone, the 1100px column on a desktop), dots under it, moving on by itself every 5 s (quiet while touched, hovered or focused, off-screen, in a hidden tab, or under reduced motion); edit mode stacks them, one under the other; then the photo card that links to the offer; no lead, no button, no note since 16.10.2026 (the owner's call: the announcements are the first thing on the page). **The offer (`#usluge`) is three tiers of the online plan** (QMove START / PRO, featured / ELITE; no MojiMakrosi add-on line since 21.10.2026, the owner: "lets leave out the moji makrosi out of here completely"; its amounts live on in prehrana's hint on `/moja-clanarina`): tier 1's monthly price is the online plan's own, every other price (tiers 2–3 monthly, all three yearly) is editable text until a plan exists; under every price that holds a number its **bazna cijena** (23.11.2026, the law's base price: "Bazna cijena na 10.9.2026.: 50 €", a muted line inside the price's block, so the switch shows it with its price; none under "na upit"; Individualno's line of its other plans says each one's in brackets, "(Bazna cijena na 10.9.2026.: 25 €)"; the Prices convention below); a **Mjesečno / Godišnje** switch under the cards shows one price per card (per page view, yearly first, monthly on a press; yearly without JS); on phones (<900px) the tiers are a swipe carousel (cards 92% wide, a sliver of the next) with three dots that opens on PRO (the featured middle card: START a swipe to the left, ELITE to the right). Below it, quieter, **the gym (`#dvorana`)**: its cards are rows of the `gym_cards` table since 20.10.2026, in creation order (Dvorana and Individualno, the first two, then whatever the gym owner adds: "Pilates za cure"), added ("+ Dodaj karticu"), hidden (its switch) and deleted ("Obriši karticu", two taps) in edit mode like the announcements, up to 8; a visitor gets no section when none is shown. No MojiMakrosi add-on line since 20.10.2026. A card with plans is priced by its first plan's slots (`price.<plan>.*`, the ones `/moja-clanarina` prints: edit one, both change; its yearly price too since 21.10.2026, the plan's `price.<plan>.year_amount` / `.year_unit`, into which migration `6e2b9d41c7a3` carried the row's typed one) and names its other plans' prices in a muted line under its own (Individualno: semi-individual and rehab; the words before each price are slots since 20.10.2026, `price.poluindividualni.word` / `price.rehabilitacija.word`, the number stays the plan's amount slot, its default back when emptied); a card without plans (every one he adds) is his text alone, its own monthly price, and "Javi nam se →" → `#kontakt` for everyone. Tiers too (a monthly and an editable yearly price: a card without plans its row's own) with their own switch, its own choice since 20.10.2026 (the owner: "unlink them"): it opens on Mjesečno, the monthly price (monthly without JS too), and a press flips the gym's cards only, as the tiers' switch flips the tiers only; from 900px as many columns as cards, up to three (a fourth wraps), on phones a swipe row. Gallery from `static/gallery/`; contact, its opening hours rows the editor empties, removes and adds (`info.hours.rows`, a `RowsSlot`, 20.10.2026). Extra lines (20.10.2026): plain lines of text the editor adds with "+ Dodaj tekst" under the headline, under every card's bullets, under the hours and under the contact rows (`*.extra`, `c.lines`), none until he does. A card's button follows the visitor: owner of the plan → into the app (a QMove card: only the owner of its tier, `Membership.tier`, since 20.10.2026; the other two say "Odaberi plan" to him), member → "Odaberi plan" → that plan's card on `/moja-clanarina`, guest → "Registriraj se" when signup is open, else "Javi nam se" → `#kontakt` (a gym card without plans: "Javi nam se" for everyone) Since 25.11.2026 what was still a literal is a slot too (`landing.*`: the buttons that follow the visitor, the featured chip, the no-prices line, the gallery's caption; the owner's door the plan's `app.door.*`); the studio's address, phone and email stay the texts of their links. |
| `/moja-clanarina` | client | **"Moja članarina"** (18.10.2026, Shape Club's billing page in QMT's look; the nav's tab says "Moja članarina" too since 26.10.2026, a client's and staff's alike): **members only** (guests are sent to log in; the trainer and the owner, who manage members on `/clanarine`, see it with no plans of their own: it is where its texts are edited), where plans are seen, bought and managed; the public price list is the landing's offer. **Tvoji planovi**: a card per plan held, active or lapsed (active first, `PLAN_TYPES` order): PAKET + name, a chip that says the state (aktivna / dospijeva za N dana, N ≤ 7 to dospijeće / istekla / otkazana · vrijedi do kraja), the facts (cijena, uplaćeno, sljedeća uplata, vrijedi do; a tiered grupni's paket and "n od N u ovom ciklusu"; the online plan's paket, its QMove tier's name, printed through the landing card's title slot, `offer.online*.title`, so a rename shows on both pages), one sentence on how and by when it is paid, and only what fits how it is paid: the plan's door (`PLAN_LINKS`) while it runs; a card subscriber's portal ("Kartica, računi, otkazivanje") and tier switch; a cash member's "Prebaci na karticu" once Stripe is configured (nothing more without it). **Dodaj plan**, the plans not held, in two groups since 21.10.2026 (the owner: "every tab is one big text cell except the number i.e. price which is connected to the front page"; "split into the QMOVE online trainings with 'godišnje' as default and everything else in the gym separate with 'mjesečni' as default"): **Online treninzi** (`clanarina.h.online`), the landing's three QMove tiers (none while online is held), its Mjesečno / Godišnje switch opening on Godišnje; then **Treninzi u dvorani** (`clanarina.h.gym`), the other plans not held in `PLAN_TYPES` order, its switch opening on Mjesečno (each group a `[data-period-group]` with its own switch, `_period.html`, which base.html's script flips for its cards only; a group with no card left is not on the page). A card is its name (a tier's its landing card's title slot, a plan's `plan.<plan>.name`), its monthly and yearly price lines (the landing's own slots: START's `price.online.amount` / `.unit`, PRO's and ELITE's `offer.online2/3.price` / `.unit`, every tier's `offer.online*.year_price` / `.year_unit`, printed as typed; a plan's `price.<plan>.amount` / `.unit` and `.year_amount` / `.year_unit`, " €" after a number), ONE text (`cjenik.<plan>.text`, `cjenik.online.<tier>.text`, its default the lines the old pieces said: the lead, the note, "Za upis se javi treneru u dvorani.", "Mjesečno, otkazivo bilo kad. Ili gotovinom u dvorani."; migration `6e2b9d41c7a3` carried what was edited) and "Pretplati se karticom" → Stripe Checkout where sellable, nothing otherwise (a tier's form names its tier, which `/placanje/online` ignores until online has a Price per tier). QMove START carries `#plan-online` (PRO and ELITE `plan-online-pro` / `-elite`). **Računi**: the `payments` ledger, newest first (date, plan with the method under it, amount when known), plus the portal's invoices for a subscriber. Price lines are the `_plan_price.html` macros (`pp.price`, a plan held's Cijena `pp.plan_price`; no note under a price since 21.10.2026; prehrana's hint: the two `addon.*` amounts), each price over its bazna cijena since 23.11.2026 ("Bazna cijena na 10.9.2026.: 60–80 €", `pp.base`: every `pp.price` call passes its base's key, `base_key=BASE_OF[…]`), each add-on amount in prehrana's hint with its own in brackets ("3 € uz dvoranu (Bazna cijena na 10.9.2026.: 3 €), …", `pp.base_paren`); Stripe's amounts show only inside the forms that charge them, a checkout form's tier picker and a subscriber's tier switch. **Editable in place** (trainer/owner): the lead (`cjenik.hint`) and each Dodaj plan card's one text (`cjenik.<plan>.text`, `cjenik.online.<tier>.text`), every price (`price.<plan>.*`, the tiers' `offer.online*.*`, `addon.*`: the landing's own slots), and since 18.10.2026 the headings (`clanarina.h.*`, the two groups' since 21.10.2026), the plans' names on its cards (`plan.<plan>.name`, this page's own; a tier's is its landing title), the no-plan card (`clanarina.none.*`; an editor holds no plans, so he gets it as a preview under "Ovo vidi član bez članarine:") and the empty ledger's line (`clanarina.bills.empty`). The line under a lapsed plan's "Pretplati se karticom" was `clanarina.card_hint` until 21.10.2026, fixed text until 25.11.2026 and a slot again since (`clanarina.lapsed.hint`, its default that text). `plan.online.name`, a held online card's heading, is on no page an editor sees (he holds no plan): he edits it on `/tekstovi` since 25.11.2026. Not the sentences built around a date or a number (the status box's dates, a chip's "za 3 dana", the facts' values). **`/cjenik`** (the old price list; the reminder email still links it) redirects here, query and `#plan-<key>` kept Since 25.11.2026 its title, a plan's kicker, its chips' words, its facts' captions, the status box's fixed words (its dates code), the card and portal buttons and the ledger's headers are slots too (`clanarina.*`), a plan's door `app.door.*`. |
| `/raspored` | client | Week calendar, booking, "Moje rezervacije" as day columns, each booking with a ✕ that asks before it cancels; cancelling is allowed until 4 h before the termin, `CANCEL_CUTOFF_HOURS` (25.11.2026, the owner: "Instead of 12 hours ahead of training for a cancellation, lets allow 4 hours"; 12 h from 17.10.2026; a booked termin stays open until it starts, so a booking inside the 4 h is still on the calendar, with "Otkazivanje do 4 h prije termina" in place of its ✕). The plans are `/moja-clanarina`'s (the "Moja članarina" block that listed them here went 18.10.2026): a client with no plan running, a lapsed one's too, gets only the booking gate's line under the termini, "Nemaš aktivnu članarinu — bez nje rezervacija nije moguća." with "Pogledaj cjenik →". Booking is open in the running week and three more (`BOOKING_WEEKS`, `db.booking_window`, 29.10.2026): a client's "idući tjedan" (and the phone's swipe) stops at the window's last week, and a week past it (a day of the month view, a typed `?week=`) shows him no termin, only "Termini se objavljuju 4 tjedna unaprijed." (the trainer walks every week); a termin after the client's dospijeće offers nothing (no Rezerviraj, no sheet) and the week says so once under its termini, "Članarina vrijedi do 8.5. — za kasnije termine produlji članarinu." with "Moja članarina →". An empty termin closes 4 h before it starts (`CLOSE_EMPTY_HOURS`, `db.is_closed`): "zatvoreno" where "otkazano" would sit, muted, the row dimmed as a past one and never crossed out, for a client (no Rezerviraj, no sheet) and on the trainer's grid (his row still leads to the roster). After booking a weekly slot the ok alert offers "Isti termin svaki tjedan do … — još N termina →" → `POST /book/{id}/series` books that slot on every later week of the window, up to the client's dospijeće; a run that skipped a date or ran out of its paket comes back with its line and the dialog `#seriesDlg` ("Nisu rezervirani svi termini": what was booked, each date not booked with its reason in words, the paket's sentence, "U redu"; the redirect carries `booked=` / `skipped=` / `paket=`, dates and reason keys). A client's **"Tvoj sljedeći termin"** card (the soonest booking, with its ✕) sits right under the week's head at every width; since 26.11.2026 (build 3) it carries "Upiši trening →" (`.act.nt-gym`, the karton's slot `karton.termini.gym_link`) while its termin's gym training is open (from `GYM_OPENS_HOURS` before it to the end of the next day; never a canceled one). **On phones (≤860px) one day at a time** (17.10.2026, so nobody scrolls the whole week): a day strip (Shape's "Moj napredak" week: pon 12 … ned 18, the chosen day filled, today ringed, a dot on days with my booking) picks the day, `?day=` keeps it through a reload, every form and redirect, and a sideways swipe moves a day; each termin is one 56px row, and a row with an action opens the bottom sheet (`#sheet`): the facts and one action, "Rezerviraj" (with the "Isti termin svaki tjedan do …" checkbox on weekly slots, the row's own bound, `data-until`, while a later week fits it: `POST /book/{id}` with `series=1` books the repeat at once, its dialog too) or "Otkaži rezervaciju". The trainer's rows link to the roster. Without JS the phone keeps the agenda of cards; the desktop keeps the 7-column grid. **A month overview on phones** (18.10.2026, clients): a "Tjedan | Mjesec" switch under the week buttons opens `?view=month&month=YYYY-MM`, the month as Shape's "Moj napredak" grid: the days of the paid period tinted a light green (`db.covered_days`: the plans that book termini, from the cycle's start to dospijeće), my bookings dotted, today ringed, and a tap on a day opens its week on that day; "Članarina vrijedi do …" under it. The switch is hidden from 861px and never shown to the trainer (`?view=month` is the week page for him) **Every text a slot since 25.11.2026** (`raspored.*`: the week, the day view, its sheet (the script's "Rezervirano" / "Termin je slobodan." too), the month, the next termin's card, the series' offer and report, the gate's lines, the ✕'s confirm titles and buttons, the trainer's "Polaznici" and "Dodaj ih u rasporedu →"); a sentence around a value stays code ("3 od 8 mjesta zauzeto", "4 h prije termina"). |
| `/karton`, `/upitnik` | client; staff's own `/karton` | Personal file: upitnik result, training diary, termini. `/karton/{id}` is the trainer's read-only view, staff's (`_require_trainer`; the owner's alone for some hours of 27.11.2026, `_require_owner`: the owner, of Amir, who had no link to it then, "I would then not even allow him to open that"; the Karton tab's search, below, made it the trainer's way to a member's karton the same day); its crumb "Karton / <ime>" leads to `/karton`, where the search is, for the trainer and the owner alike (Korisnici that morning, Trenutne članarine until then), staff's Karton tab on there; Korisnici's "Karton", the owner's, leads to it too. Since 26.11.2026 it carries "Otvori kao član" under its head line (`.act`, amber since build 4, `.act-kao`; a form into the member's account, back there at "Izađi"; Architecture, "Staff act as a member"): the view itself stays, it shows what a member never sees; from build 4 of the same day no page staff reached linked to it but Korisnici's "Karton" (/clanarine's "Karton →" went) until the Karton tab's search, and what only it showed of the upitnik staff acting as the member read on his karton (below). **Staff have a karton of their own since 24.11.2026** (the owner: "Lets show the Karton tab in the Admin view as well so that Amir can check out the changes we made there"; until then `/karton` sent a trainer to `/clanarine`): `/karton` is the trainer's and the owner's as a member's (`_render_karton(…, own=True)`, `staff_own`): his diary (his own online passes, his trainings outside a termin), maxes, weight, limitations and photos, every karton POST his; no upitnik card (staff never fill it: POST /upitnik refuses them; nothing in its place), no "Nadolazeći termini" (they book none), and the empty diary's line "Još nema treninga u dnevniku." (no "rezerviraj prvi"); `/karton/{id}` as it was. **The search for a member's karton** (27.11.2026; the owner, of the Karton tab's field and its amber button: "I would rather replace the search bar and the button with just a search bar and when a user is pressed, that user's Karton is opened, not the whole app as his view, but just his Karton which will be searchable for Amir. … The 'Admin' -> 'Gledaj kao član' option stays."; from 26.11.2026, build 4 of `roadmap/2026-11-26-gym-training-plan.md`, it was the way into a member's app, `form.kao-pick` posting `POST /kao` with "Otvori kao član" beside the field, `.btn-kao`, all three gone): right under the lead of the trainer's and the owner's own karton (`staff_own`), above the cards, ONE field (`form.k-find`, a GET to `/karton/clan`): "Član" (the page's label look) over a field of every member `/kao` lists, in its order (`app._kao_members`, one list for both); without JS a native `select name=clan required` ("Ime Prezime · email", one named by his email the email alone, after its empty "Odaberi člana…") and beside it "Otvori karton" (`.act`), with it base.html's `qmtCombobox` over `#kf-json` (`[id, name, "email · plans", email]`: the name over the muted "email · plans", "bez članarine" for none, the plans alone for one named by his email; typed into by the name and the email alone, folded, the row's `find`; "Ime ili email člana", the list "Članovi", nothing found "Nijedan član ne odgovara traženju.") and no button (the script takes "Otvori karton" away): a pick, a tap on a row or Enter on the highlighted one, sends the form at once (the combobox's `opts.onPick`) and opens his karton, the trainer's view (its "Povijest vježbe" the search the owner meant, "searchable for Amir"); Enter with nothing picked says "Odaberi člana s popisa." under the field and sends nothing; back with the browser's Back the field is empty, ready for the next name (`pageshow`: a page out of the browser's cache still holds the pick). The field 420px at most from 600px, the column's width on a phone; 40px, 44px on a coarse pointer; the list lies over the cards. Never while acting (the page is then the member's own karton), on the trainer's view or a member's karton; no member at all, no form. Staff's own chrome: literals, no slot. **`GET /karton/clan`** (declared before `/karton/{id}`, which would take "clan" for an id; `_require_trainer`, a member 403, while acting too): `clan`, 1–9 digits (its spaces aside) naming a member (neither a trainer nor the owner: `_kao_members`' rule) → 303 to `/karton/<id>`; nothing, junk, an id naming nobody or a staff account → 303 to `/karton?error=Odaberi člana s popisa.`; a GET: it enters nothing, records nothing. **One column, the diary last** (25.11.2026, the owner: "Everything should be one above the other and the 'dnevnik treninga' should be last"; until then a two-column grid, the weight and the termini in a rail beside the diary): the upitnik block, "Ograničenja i bolovi", "Tjelesna kompozicija" ("Tjelesna masa" until the same day's later build), "Napredak — fotografije", "Procijenjeni maksimumi", "Povijest vježbe" (the later build), "Nadolazeći termini" (a member's own and the trainer's view; the weight and the termini cards of the column like the others, `.card`, 1.05rem headings), then "Dnevnik treninga" and its rows, on every view ("+ Dodaj trening izvan termina" above them from 26.11.2026 until 27.11.2026, when it went to the tab Dvoranski treninzi); below 1000px every card 720px at most at the column's left edge, the same order on a phone. From 1000px (the owner: "if you have more room on the PC layout, you can use more columns"; the number Fable's) the cards above the diary flow in two equal columns across the page's width (`.k-cards`, a grid 20px apart, the two of a row one height): the limitations beside the weight, the photos beside the maxes; the upitnik block, "Povijest vježbe" (its picker 640px at most) and the termini each across both (half a row, a termin's title gave way to a long retyped "OTKAZANO": the walk of `tests/test_copy.py` measured it), and a card left alone in its row across both; the diary under them at the page's width, its forms 640px at most. **Every text is editable in place** (25.11.2026, the owner: "In the moji karton tab, lets allow the admin to change all of the text, like in other tabs as well"): every static text karton.html prints is a copy slot, `karton.<area>.<name>` (126 since the later build of 25.11.2026, its documents, the body form's hint and the history's 16 among them; 129 since 26.11.2026, the height's six in place of the three that led to /profil; 120 since build 3 the same day, the plain osvrt form's and the exercise log's seventeen gone, the gym training's eight come (the termini's way in and its hint, the diary's states and buttons, "Dodaj trening"); 114 since 27.11.2026, build 2 of the dvoranski treninzi, the form of a training outside a termin's four and the termini's hint's two gone to the tab, `karton.outside.add` / `.title` / `.create` / `.cancel`, `karton.termini.gym_before` / `.gym_after`; the copy convention's "The karton's texts"), on a member's own karton, a staff member's own and the trainer's view (their own variants, `karton.staff.*`), the ✎ pill on each; not the sentences built around a value (the head line, "Razina 2 od 3 — …", "napor 7/10", "3 vježbe", "6 od 8 vježbi · 38 min", "Karton — <ime>", a confirm that names a value, the photo field's label with its MB, the line the script writes for an exercise gone from the library), the tables' cells, `LEVELS` / `FEELING_LABELS` / the months, the upitnik's own questions and answers, the routes' flashes, every aria-label and alt, the `<title>`, the crumbs and the nav. At the bottom of a staff member's own karton, under the diary, in edit mode only (outside it no room, nothing read aloud), the panel **"Svi tekstovi kartona"** (`section.card.k-texts`) lists every karton text area by area (`copy.KARTON_PANEL`), its label over the text, a click there edits it as on the page: the texts only a member or the trainer's view prints, and those in a confirm dialog or a placeholder (attributes, `copy_text`: a change shows there after a reload), are in his reach. **The diary holds the online passes too** (30.10.2026, stage 3 of the online treninzi spec: `_diary_rows`): each finished pass of the client's among his termini by when it started, newest first, in a termin row's shape: the kicker "Online trening", the day and date, napor and osjećaj as a termin's, "Trening 1 · Cijelo tijelo — Cijelo tijelo — srednja razina" (the day's label and the programme's title as they were when it started: the snapshots; a pass stored before 2.11.2026 said "Dan 1 · …", which migration `b61e8d5bf1db` made "Trening 1 · …"), "6 od 8 vježbi · 38 min" (the day's exercises now, and of them the ones it saved: an exercise deleted from the library since stays in the trainer's "Serije", uncounted, 4.11.2026; a day since deleted: "6 vježbi", every entry), the comment, then "Serije", every exercise's sets folded (`details.sets`; the trainer's view's only until 23.11.2026, the client's too since: Amir, "u kartonu može ući u povijest svojih treninga"). A pass in progress is not there, and nothing on the karton edits or deletes a pass (an open question for the owner). **The exercise log on a training** (23.11.2026, part 1 of `roadmap/2026-11-23-karton-amir.md`; Amir: "da si on može sam upisati koji trening je radio … izračun maksova") **went on 26.11.2026** with the plain osvrt form it rode on (build 3, the gym training, below): "Ispuni osvrt" and its form, the exercise blocks under Komentar (`log=1`, `db.read_log`, `app._posted_log`, `app._log_entries`, the `<template id="ex-block">` and its script, `db.MAX_LOG_EXERCISES`), `db.add_session_feedback` and `db.add_training_log` (no `TrainingLog` row is made since; the karton slots only they printed left the registry). **What stays**: every `TrainingLog` row already there (a termin's osvrt, a training outside a termin, an absence), listed as before with its "Serije" (`TrainingLog.lines`, "3 vježbe"), its napor, osjećaj and komentar edited in place (`POST /karton/log/{id}/edit`, its exercises read only; a training outside a termin's date too), its delete, and "Nisam bio/la" (`db.mark_session_absent`), as it was. **The gym training in the diary** (26.11.2026, build 3 of `roadmap/2026-11-26-gym-training-plan.md`; its page and rules: the rows after this one and Architecture, "The gym training"; `_diary_rows`' `gym` and `open`): a termin's training that holds anything (an exercise, or its osvrt; since 27.11.2026 blocks alone hold nothing: a template applied and left) is its termin's row (`.log-entry.gym#gt-<id>`): its title the kicker, the day, date and time ("sri 25.11.2026. · 18:00"), napor and osjećaj as a termin's, its comment, "3 vježbe" and "Serije" folded, since 27.11.2026 block by block (`GymTraining.lines`, a block with no exercise in no line): a Stanica's line, what was given and what was done and the block's rating ("Goblet čučanj: zadano 3 × 10 · 20 kg — odrađeno 10 × 20 kg · 10 × 20 kg · 8 × 20 kg · težina 8/10"; "zadano …" only when anything was given, "odrađeno —" when nothing was ticked), a Kružni set's line of its own ("Kružni set · 4 kruga · težina 7/10") and its exercises under it, a step in (`li.kin`), each what one round asks and what each round did, and "Otvori trening" (→ `/dvoranski/trening/<id>`) while the member may write it (his window; staff acting as him at any time). A booked termin that has ended with none, or with an empty one: inside its training's window "Trening još nije upisan." (`.le-state`, an optional slot) with "Upiši trening" (→ `/dvoranski/termin/<id>` since 27.11.2026, `/karton/termin/<id>/trening` until then, which makes the training the first time it is opened) and "Nisam bio/la" as it was; after it "Trening nije upisan." and "Nisam bio/la" alone (staff acting as him get "Upiši trening" still). A training outside a termin, or one a cancelled booking let go of its termin, is a row of its own: "Trening izvan termina" its kicker where it has no title, no time, "Otvori trening" always. The trainer's view reads the same rows with no button. **A training outside a termin** (since 26.11.2026) is made on the tab Dvoranski treninzi since 27.11.2026 (build 2 of `roadmap/2026-11-27-dvoranski-treninzi-plan.md`; the owner: "Maybe it would make sense for the user to only input in the 'Dvoranski treninzi' tab but Amir and I can always check the user's Karton?": the karton keeps the record, the tab the forms), its section "Trening izvan termina" (`POST /dvoranski/trening`, the `/dvoranski` row); from 26.11.2026 until then the karton's "+ Dodaj trening izvan termina" (`.act` above the diary's rows, a member's own karton and a staff member's, `qmtToggleForm`, its date alone) and `POST /karton/trening` (405 since): gone, a member's own karton and a staff member's. Its row is the diary's as above. "Nadolazeći termini" carried "Upiši trening →" (`.act.cal-go`) on a termin whose training was open and under its list "Trening upisuješ od 4 h prije termina do kraja idućeg dana." from 26.11.2026 until 27.11.2026: the termini are the termini alone since (the tab's "Otvoreni treninzi" lists the open trainings; the raspored's card keeps its "Upiši trening →", `karton.termini.gym_link`). The login's osvrt prompt (`db.pending_feedback`) owes a termin only while its training's window is open, once it has ended, until its training's osvrt is saved or a `TrainingLog` holds it (an absence, an old osvrt); its button leads to the training (`/dvoranski/termin/<id>` since 27.11.2026), where "Završi trening" is the osvrt. **"Procijenjeni maksimumi"** (23.11.2026; the owner: "the standard Epley formula (90 kg × 6 reps gives about 108 kg), best value per exercise, fed by gym logs and online passes alike; bodyweight exercises show the best reps instead"): a card between the upitnik block and the diary, the client's and the trainer's, its hint ("Iz najbolje serije svake vježbe, Epleyevom formulom (kg × (1 + ponavljanja / 30)), do 12 ponavljanja. Vježbe bez utega: najviše ponavljanja.") over a compact table, Vježba · Procjena ("108 kg", to the nearest 0.5 kg; a bodyweight exercise's "9 ponavljanja") · Iz ("90 kg × 6 · 12.11.2026.", then "dvorana" / "online" muted; a bodyweight row the date and the source alone, its reps being the estimate), its cells wrapping on a phone; `db.estimated_maxes` (a set that holds seconds never counts: since 24.11.2026 an online exercise may ask for reps and seconds, "5 × 30 s", which is no bodyweight record of 5 reps). Empty: the hint and "Još nema serija — upiši vježbe u svoj trening." (the slot's default since 26.11.2026, build 3; "… upiši vježbe uz osvrt treninga." until then; the trainer: "Još nema serija."). Since 25.11.2026 each row's name is a `.tlink` to its history, `?vjezba=<id>#povijest-vjezbe`. **"Povijest vježbe"** (`section.card.hist#povijest-vjezbe`, 25.11.2026, the later build; the owner: "We need a search bar for each user. Admins can access everyone's karton and search a particular exercise."; his note to Amir: "search unutar kartona vježbe kad je radio i kaj je zadnje radio"), right after the maxes, on a member's own karton, a staff member's own and the trainer's view of a client: a GET form to that karton (`/karton` or `/karton/{id}`, `#povijest-vjezbe`, so the page comes back at the card), "Vježba", the exercises this karton holds (`db.logged_exercises`: from its trainings' logs and its finished online passes, a swapped exercise under the swap, named by the library now or, deleted, by the newest name it was logged under, the alphabet's order) in a native `select name=vjezba`, which the page's script swaps for a hidden `vjezba` and base.html's `qmtCombobox` over `#hx-json` (`[id, name, "5× · zadnji put 23.11.2026."]`, the muted line under each row's name; "Prikaži" with nothing picked stops at "Odaberi vježbu s popisa."), then "Prikaži". With `?vjezba=<id>` under a hairline: the exercise's name (an h3), "Zadnji put: 23.11.2026. · dvorana" and that time's sets on a line, its estimated max when it has one ("Procjena maksimuma: 28,5 kg", the maxes' own `value_text`), then every time it was done, newest first (`db.exercise_history`: a row per training, an exercise logged twice in one being one row, its sets in the order logged), the date, muted where ("dvorana" / "online" · the termin's title, "Trening izvan termina", or the online day's label as the pass keeps it), its sets under it (`set_text`); the newest ten and the rest under "prikaži sve" (`details.sets`, `app.HISTORY_SHOWN`). An id the karton does not hold (another member's exercise, a word): "Ta vježba nije u ovom kartonu."; nothing logged: "Još nema upisanih vježbi." and no form. A client never reaches another member's karton (`/karton/{id}` is staff's). **The body and the photos** (23.11.2026, part 2 of `roadmap/2026-11-23-karton-amir.md`; Amir: "tjelesna visina, tjelesna masa, onda slika jednomjesečno … ograničenja koja će se on napisati, bolovi itd."; the owner: "Height is one number, weight a dated history, limitations a free text, the photo optional and shrunk like the landing's photos, visible to the member and Amir only"; migration `0401f7fb9861`): **the head line** under the title, "Visina 178 cm · Masa 82,5 kg (12.11.)" (the height (the profile's until 26.11.2026, the karton's since), the newest weight and its day, since 25.11.2026 the newest entry that has one, each part only when known; the member's on a line of its own under the lead, `.k-body`, the trainer's after the age and the phone; `app._body_line`). **"Ograničenja i bolovi"** and **"Napredak — fotografije"** (the weight card between them since 25.11.2026) are blocks of their own between the upitnik block and the maxes (the maxes card's look): the member's text of his limitations and pains (`User.limitations`), as saved (its line breaks), or "Nema upisanih ograničenja."; his "Uredi" (`.act`, `qmtToggleForm`) opens the textarea (2000 characters, cleaned as copy is: `db.set_limitations`, "Najviše 2000 znakova.") → `POST /karton/ogranicenja`; the trainer reads it, the pain flag's amber `.u-flag.pain` "Ograničenja" in the card's head while it holds anything, since 25.11.2026 a document too. **Its documents** (25.11.2026, the later build; Amir: "U ograničenja i bolovi treba dodati mogućnost da se doda slika ili pdf"; migration `2b7e4c9a61d3`): under the text a block of their own (`.lim-docs#lim-docs`), its caption "Dokumenti" (an h3, when there is one, and always on the member's own karton), the member's "Dodaj dokument" (`.act` beside Uredi, its own `qmtToggleForm`; not offered at ten) opening its form in a hairline box: "Dokument (pdf, jpg, png ili webp, do 15 MB)" (`data-focus`) and "Naziv (neobavezno)" (80 characters; empty: the upload's own file name without its path, cleaned and cut to 80, or "Dokument": `db.doc_name`) → `POST /karton/ogranicenja/dokument` (multipart, `app._store_document`: a PDF by its name AND its first bytes, `%PDF-`, stored as it came; an image by its name and by what Pillow finds, `_shrink_image` at `DOC_PX` 2400 so a photographed printout stays legible, stored as a JPEG; stored as `nalaz-<user id>-<hex>.<ext>`; another format, a fake PDF, one over 15 MB: "Nepodržan format — dozvoljeno: pdf, jpg, png, webp." / "Dokument je veći od 15 MB.", nothing stored; at most ten, `db.MAX_LIMITATION_FILES`, under the member's row lock, "Najviše 10 dokumenata."), back at `#ogranicenja`, "Dokument je spremljen." (no flash names a file); then a row per document, newest first (`ul.doc-list`): its name a `.tlink` to `/media/<file>` in a new tab (wrapping anywhere), under it its chip ("PDF" / "slika") and its date, the member's quiet ✕ ("Obrisati dokument?", its text naming it → `POST /karton/ogranicenja/dokument/{id}/obrisi`: the row, then the file; another member's 404); the trainer's view the list, read only. The photos: one a month at most (`ProgressPhoto`), the newest month first, a wrapping row of 120 × 160 thumbnails (`object-fit: cover`, `loading="lazy"`), each a link to the whole photo (`/media/<name>`, a new tab), its month under it ("studeni 2026.", `month_label`), the member's ✕ on the photo's corner (a solid `--surface` circle; "Obrisati fotografiju?" → `POST /karton/slika/{id}/obrisi`, the row, then the file; another member's 404); his "Dodaj fotografiju" ("Zamijeni ovomjesečnu" once this month has one) opens the form: the file (jpg / png / webp, at most 15 MB; `data-focus`, it takes the focus) and Mjesec, the month the photo is OF (this one, selected, and the eleven before it: `db.photo_months`, "Neispravan mjesec." for another), "Jedna fotografija po mjesecu: nova za isti mjesec zamjenjuje staru." → `POST /karton/slika` (multipart; spooled to the cap, then `app._shrink_image`, the announcements' pipeline: upright, 1600 px on its long side at most, a progressive JPEG with no EXIF; stored as `napredak-<user id>-<YYYYMM>-<hex>.jpg`; a month's new photo replaces its old, whose file goes, `db.set_photo`); empty, "Još nema fotografija." and the member's hint, "Jedna fotografija mjesečno, kad želiš — za usporedbu kroz vrijeme.". **"Tjelesna kompozicija"** ("Tjelesna masa" until the later build of 25.11.2026; Amir: "Tjelesna masa tu bi promijenio u tjelesna kompozicija gdje opet mogu dodati pdf ili sliku ili samo upisati ručno masu"; the anchor `#masa` and the routes as they were), a card of the column under the limitations (the head of a rail beside the diary until 25.11.2026, `aside.k-rail`, which followed the diary on a phone): an entry is a day with a mass, a document, or both. "Visina 178 cm" (since 26.11.2026 the karton's own, the owner's note: "visinu maknut iz profila u karton"; /profil's field from 23.11.2026, which its "uredi" led to): on one's own karton, a member's and a staff member's, a quiet "uredi" beside it (`.act.act-quiet`, `qmtToggleForm('visina')`; with none "Visina nije upisana" and "upiši") opens its form under the line (`.ms-hgt#visina`), one field, "Visina (cm)" (`type=number`, 100–250, `inputmode=numeric`), Spremi and Odustani → `POST /karton/visina` (`db.read_height`, "Neispravna visina.", nothing changed; empty clears it; `db.set_height`) → back at `#masa`, "Visina je spremljena."; its texts `karton.weight.height_*`, new keys (the three old ones, `height_edit`, `no_height`, `no_height_link`, left the registry so an edit of their words never prints in a new place); the trainer's view reads the line, the newest entry that has a mass big ("82,5 kg", `kg_text`) and its date under it (a newer entry with a document alone does not count), or "Još nije upisana."; his "Upiši" opens the form, Kilogrami (`type=number`, `step=0.1`, `inputmode=decimal`, 20–300, "82,5" or "82.5": `db.read_weight`, "Neispravna masa."; no longer required) beside Datum (`type=date`, today by default, not in the future, not before 2020-01-01: `db.read_day`, "Neispravan datum."), "Dokument (pdf, jpg, png ili webp, do 15 MB)" (optional) and the hint "Upiši masu, dodaj dokument (npr. ispis analize sastava tijela) ili oboje." → `POST /karton/masa` (multipart; neither: "Upiši masu ili dodaj dokument."; the document as the limitations' are, `_store_document`, stored as `sastav-<user id>-<YYYYMMDD>-<hex>.<ext>`, its link named by the upload's own name; one entry a day: a second save that day replaces what it gives and keeps what it does not, a new document's old file deleted, `db.set_weight`; the flash "Masa je spremljena." / "Dokument je spremljen." / "Masa i dokument su spremljeni."); then the history, newest first, "12.11.2026. · 82,5 kg" and, with a document, " · " and its link (a new tab), an entry with no mass "12.11.2026. · <its link>", each row with its quiet ✕ ("Obrisati unos?" → `POST /karton/masa/{id}/obrisi`: the entry, then its file; another member's 404), the newest twelve and the rest under "prikaži sve" (`details.sets`); the trainer's card the same, read only, the whole history folded under "Povijest" when it is longer than twelve. No BMI (not asked). Every save or refusal comes back to its card (`#masa`, `#ogranicenja`, `#napredak`). **The upitnik** (v2 since 26.10.2026, the gym owner's final version; its questions rows he edits since the same day, idea 3): Shape's questionnaire in QMT's clothes (patterns.md §7), one question per screen: for a member the brand alone in the small pill at the top (base.html's `solo_page` flag: no tabs, no account menu; since 26.10.2026 the trainer and the owner, who open it to edit, keep their whole bar, Admin ▾ `.on` and its Upitnik item current: `solo_page = not can_edit_copy`), a 640px column, the title (`upitnik.title`; the intro under it on question 1's screen, the `?error=` alert under the title), a thin `--accent` progress bar counting the questions asked so far and the ones always asked ahead, the part as an eyebrow, the question as the h1, then lettered rows (a choice, yes / no; the chosen one inverted with a ✓, going on ~250 ms after a tap; a multi's rows are checkboxes, several ticked, and "Dalje" goes on, dimmed, `aria-disabled`, until one is) or ten round buttons (a scale, 5 × 2 until ten fit at 40px), a free text with "Dalje" (a text question's, "Gdje te boli?" under the pain question among them), "Nazad" under every question (the first one's back to the guide), and last the consent checkbox (required) with "Spremi upitnik". ONE form holds every question (the script shows one step and the inputs keep the answers; the keyboard's arrows only mark, Enter goes on): without JS it is the whole questionnaire with one submit. **The guide through the training comes first** (29.10.2026, the owner: the gym owner's introduction, "for now put it before the questionnaire"): a step of the one form before question 1 (`#step-vodic`, `_vodic.html`, `/vodic`'s guide): its title (`vodic.title`) the h1 in a question's place, its sections, and at the bottom ONE `.btn`, "Idemo na upitnik!" (`vodic.cta`, full-width on a phone), which goes on to question 1 as "Dalje" does; no bar on its screen (`.at-guide`: the bar counts the questions, its room kept) and no intro (question 1's); question 1's "Nazad" comes back to it. A refill and the editor's preview open on it too; `?od=1` (the guide read: `/vodic`'s button, a refused submission) opens on the first question asked (the form's `data-start` names the step, the guide's `step-vodic` or `step-q<id>`); without JS the guide stands above the questions; in edit mode it is at the top of the stack, every text of it a box, the scoring's summary between it and question 1. **A question asked only after an answer** (27.10.2026, idea 3: "Pita se") carries its condition on its step (`data-parent`, the step it is asked after, and `data-is` a yes / no's value, `data-from` a scale's N, `data-has` an option), which the script checks live, down a chain: it shows only once that answer is given, and a step not asked has its inputs disabled; without JS it shows to everyone, none of its inputs required, and the POST drops it when it was not asked. A refill starts fresh, nothing preselected. The trainer and the owner get the page with no plan of their own, to edit it (Admin ▾ → Upitnik opens `/upitnik` in normal mode, as every page opens; the ✎ pill turns edit mode on); their page holds every question, a hidden one (`.is-off`) a step in edit mode only. In edit mode every step shows, stacked, a hidden one dimmed, his choices are his options lists, the pain sentence (`upitnik.pain_note`) is previewed under the pain question, and each question carries his controls (`.q-ed`, 32px pills: its switch, ↑ / ↓, "Obriši pitanje" (two taps), then a select per setting, Dio, Vrsta, Bodovanje on a scale, Uloga on a scale or a yes / no offering the role its kind can hold; a select saves at a change, `POST /upitnik/pitanje/{id}`, and the page comes back in edit mode; and **"Pita se"** (27.10.2026): "Uvijek" / "Samo ako …", which shows two more pills, "Pitanje" (the questions before it whose answer a condition can name, "16 · " and their first 40 characters; "Samo ako …" picks the nearest) and "Odgovor" (Da / Ne, a scale's 1–10 with "ili više", a choice's or a multi's options, listed by the page from the question chosen), saved together once an answer is chosen, `parent_id` + `condition`; an ↑ / ↓ that would put a question above the one it is asked after says "Potpitanje ne može ići ispred svog pitanja." in the bar at the press, `data-refuse`, and the route refuses it too) and a grey line under them saying what they do ("Dio 2 · skala · boduje se: trening baza", "Dio 4 · skala · uloga: bolovi (7+ početna)"), for a conditional question a second line, "Pita se samo ako pitanje 16 = Da" ("… ≥ 4", "… = Kod kuće s girjom"), in amber when its condition cannot work ("Pita se uvijek — uvjet ne vrijedi: pitanje 16 dolazi kasnije" / "pitanje je obrisano" / "nema odgovor „Da”") or when a hidden question above it mutes it (the step dimmed, `.is-muted`: "… — pitanje 16 je skriveno, pa ni ovo nitko ne dobiva"; a client gets no step of it); a conditional question sits indented under the one it is asked after, 16px a level behind a left hairline (`data-depth`), so a chain reads as one; above the first question the scoring's summary ("Bodovanje: trening baza = 3 pitanja, navike = 4 pitanja. Rezultat = 0,6 × baza + 0,4 × navike.", and when nothing scores the alert "Nijedno pitanje se ne boduje — svi dobivaju početnu razinu."), under the last "+ Dodaj pitanje" (not at 40). The POST refuses them both ("Upitnik ispunjavaju članovi …"). POST validates every question asked (the shown rows: an option must be among the row's options now, each of a multi's ticks too; a question not asked, its condition's answer not given, is dropped) and the consent, else back with the error and nothing stored (on the first question, `?od=1&error=`: the guide was read); then `/treninzi`, the flash naming the level (plus the pain sentence when `pain_high`). **The karton's block** for a v2 response: the razina ramp, part 1's answers as chips ("3 dana tjedno", "45-60 min"; a multi's texts joined with " · "), the score "6,4 / 10", the pain sentence when `pain_high` (the client too); the trainer's view (and since 26.11.2026, build 4, the member's own karton while staff act as him, `actor`: the same markup, slots and rules, each group under a small muted caption "Vidi samo trener", `p.hint.u-staff` .78rem, once over the flags' row and once over Odgovori, none over a group that prints nothing; on a touch screen there "Odgovori" a 32px target; nothing else of the view, its head line of email, age and phone staying the view's; the member himself as before, byte for byte) adds a red "Zahtijeva pregled" (`needs_review`), an amber "Bolovi N/10 · where" (`pain_level` ≥ 4, `PAIN_ASK`; where: the answer to the first free-text question asked after the question that holds the pain role now, `upitnik.pain_where`, "" when it has none) and under Odgovori every answer the response holds, under its question as the owner words it now (every row, a hidden one's too; an answer printed by what was stored, a multi's texts joined with " · "), a conditional question's answer indented under the one it is asked after, a step a level (`li.follow d1`–`d3`: "Gdje te boli?" under the pain question, a chain's each further in), and last a deleted question's, under "(pitanje uklonjeno)": nothing is pruned. A v1 row keeps its level, goal and "9/14 bodova", its answers through `QUESTIONS_V1`, and "Stari upitnik — ispuni novi." (the link for the client) |
| `/dvoranski`, `POST /dvoranski/trening` | member with a gym plan; staff (their own); staff acting as a member | **"Dvoranski treninzi"** (27.11.2026, build 2 of `roadmap/2026-11-27-dvoranski-treninzi-plan.md`; the owner: "how long would it take to create a new tab called 'Dvoranski treninzi' in the same level of hierarchy as the 'Online treninzi' … Maybe it would make sense for the user to only input in the 'Dvoranski treninzi' tab but Amir and I can always check the user's Karton?" … "I would show the tab only to members with a gym plan. Similarly how a online training tab shows only to members with an online plan."): the tab's page (`dvoranski.html`, `app.dvoranski_page`), the `/treninzi` list's twin: the normal layout, its 640px column, the title "Dvoranski treninzi" and an optional lead ("Ovdje upisuješ svoje treninge u dvorani. Sve što upišeš ostaje u tvom kartonu."); since 27.11.2026 (build 3) staff get, under it, one `.act`, "Predlošci treninga →" (`p.dv-tpl` → `/dvoranski/predlosci`, Amir's templates: staff's own words, allowlisted in `tests/test_copy_rule.py`; never a member's, nor while staff act as one). A guest to the login (`?next=/dvoranski`); a member with no gym plan (an online plan alone, none, a gym plan lapsed: `app._has_gym`) the gate's one sentence in /treninzi's card, "Dvoranski treninzi su dio članarine za dvoranu.", no section; staff always, for their own trainings (outside a termin); staff acting as a member his page, his plans deciding. Its sections, each its h2 (1.05rem) over what it holds: **"Otvoreni treninzi"**, his booked termini whose training he may write now (`db.gym_open_termini`: `db.gym_window_open`, the termin not canceled, the soonest first), a card each (`article.card.dv-open#dv-s-<id>`): the termin's title (an h3), its date and time in 700 ("srijeda 25.11.2026. · 18:00", `_gym_when`), the training page's state line ("Upis je otvoren do četvrtka 26.11. u ponoć.", `gym.state.open`), what it holds ("3 vježbe"; nothing while no exercise) and ONE button (`.btn.btn-sm`), "Upiši trening" while it holds no block (no training yet, or one opened and left empty), else "Nastavi trening", → `/dvoranski/termin/<id>`; none open, one muted line: his next booked termin (a canceled one skipped), "Sljedeći termin: Grupni trening, pon 30.11. u 18:00 — upis se otvara 4 h prije." (the hours `GYM_OPENS_HOURS` between two optional slots), or "Nemaš otvorenih treninga." with "Raspored →" (`.tlink`). **"Trening izvan termina"** (`#trening-novi`), the Karton's form of 26.11.2026 moved, in a card: Datum (`type=date`, today by default, not in the future, not before 2020-01-01; the training page's `gym.head.date_field`) and "Dodaj trening" → `POST /dvoranski/trening` (`gym_outside`: `db.read_day`, `db.add_gym_outside`) → the new training's page (its template chooser); refused, "Neispravan datum." in the card, `?error=…#trening-novi` (the page's top shows none: its `error_alert` is empty), nothing made. Made by a member with a gym plan, by staff for themselves and by staff acting as a member whatever his plans (rule 1's "at any time": the actor decides; the page shows such a member the gate, the route takes it); anyone else back to `/dvoranski` (the gate), nothing made; a guest to the login. **"Zadnji treninzi"**, his newest ten gym trainings that hold anything (`GYM_TAB_LAST`: an exercise or a saved osvrt; the karton diary's order, a termin's by its start, one outside a termin by its date, the newest made first on a tie), one card of rows (`.dv-row#dv-gt-<id>`): its title a kicker (outside a termin "Trening izvan termina", `gym.head.outside`), its date in 700 ("sri 25.11.2026.", a termin's " · 18:00" after it), "3 vježbe · napor 7/10 · Dobro" muted (`count_text`, `osvrt_text`), "Otvori trening" (`.act`) → its page, which says whether it is still his to write (a read-only one's link too); under them "Svi tvoji treninzi su u kartonu →" (`.act.act-quiet` → `/karton#osvrti`); none, "Još nema upisanih treninga." and no link. Every text a slot (`gym.tab.*`, 17: on /tekstovi under "Trening u dvorani", its first area "Dvoranski treninzi", whose "Otvori stranicu →" is `/dvoranski`) and the training page's where the tab says the same (`gym.state.open`, `gym.head.outside`, `gym.head.date_field`); the nav's label is the nav's. The login's osvrt prompt is not shown here (the open trainings are) |
| `/dvoranski/termin/{id}`, `/dvoranski/trening/{id}` | member; staff's own (outside a termin); staff acting as a member | **The gym training** (26.11.2026, build 3 of `roadmap/2026-11-26-gym-training-plan.md`; since 27.11.2026, build 1 of `roadmap/2026-11-27-dvoranski-treninzi-plan.md`, a row of **blocks**, Stanica and Kružni set, on the online player's layout; Architecture, "The gym training"; the owner: "A gym training consists of 'Stanica' and 'Kružni set' where the 'Kružni set' consists of 4 of 'Krug' at default which can be changed. Each 'Krug' is the set of same exercises, but the user can edit the number of reps done after each 'Krug' during the pause."). `GET /dvoranski/termin/{id}` makes the member's training of a termin the first time it is opened (rule 2: his booking, "Nemaš rezervaciju za ovaj termin."; the termin not canceled, "Termin je otkazan."; for a member the window open, "Trening se otvara 4 h prije termina." / "Upis ovog treninga je zatvoren."; a refusal: his karton, its sentence at the top) and leads to `GET /dvoranski/trening/{id}`, the page; its ways in: the tab's "Otvoreni treninzi" (since 27.11.2026, build 2: the `/dvoranski` row), the karton diary's "Upiši trening" / "Otvori trening", the raspored card's "Upiši trening →", the login's prompt, a roster's "Kao član →", and for a training outside a termin the tab's "Trening izvan termina" (`POST /dvoranski/trening`; "Nadolazeći termini"' "Upiši trening →" and the Karton's "+ Dodaj trening izvan termina", `POST /karton/trening`, until build 2). The page hangs under the tab since build 2 (the owner: "Maybe it would make sense for the user to only input in the 'Dvoranski treninzi' tab but Amir and I can always check the user's Karton?"); a training's page asks no plan (rule 1 and its owner, as before): one already there stays reachable by its links after a gym plan lapses. The page (`karton_trening.html`): the player's layout (its rules copied into the page, the same classes: `.pl`, `.pl-segs` / `.pl-track`, `.pl-line`, `.pl-timer`, `.pl-card`, `.pl-side`, `.pl-row`, `.pl-dock`), the normal nav kept, **its tab Dvoranski treninzi lit** (base.html: `.on` on every `/dvoranski` page, since build 2; the Karton tab until then, `at_karton`), `no_nudges`. Top to bottom: the segmented strip, a piece per block (done `--accent`, the one on screen `--text` at 60%, the rest `--surface-2`; past 40, `SEGMENTS_MAX`, one track); "← Natrag" (`player.top.back`: since build 2 the tab, `/dvoranski`; a viewer with no tab, a member whose gym plan lapsed or staff acting as one with none, the karton at the training's diary row, `#gt-<id>`, or the termin's, `#s-<id>`, while it holds nothing, as build 1's), the clock chip (`.pl-timer`, the script's: from the training's first tick, `GymTraining.first_tick`, the earliest `done_at` of an item that holds a set; shown while the page is writable, the osvrt not saved and that tick at most 4 h old, `app.GYM_CLOCK_HOURS`; recorded nowhere; a first tick on the page starts it) and "Završi trening" (`.act.pl-end` → the osvrt); the head (`.gt-head`: the kicker "Trening u dvorani", the termin's title as the h1, outside a termin "Trening izvan termina", the date and time in 700, outside a termin "promijeni datum", then the state line: "Upis je otvoren do četvrtka 26.11. u ponoć." / "Upis je zatvoren — trener ga i dalje može urediti." / before the window rule 2's sentence / staff acting as him outside it "Za člana je upis zatvoren; uređuješ kao trener."); then `.pl-grid.gt-grid`, from 1000px two columns (the block and the foot in `minmax(0, 640px)`, the overview in 380px beside them, `grid-template-areas: "main side" "foot side"`), below one column, the overview under the block and the player's dark pill at the bottom, "Pregled · 2/6 ✓" (`.pl-dock` → `#pregled`, the count the done blocks; hidden while the pause bar shows, gone from 1000px). **The main card** (`#glavno`) is one block: `?blok=<id>`, else the first block not done; every one done (or `?dalje=1`), **the "what next" card** ("Sve je odrađeno — dodaj stanicu ili kružni set, ili završi trening.", "+ Stanica", "+ Kružni set", "Završi trening"); no block at all, **the template chooser** ("Odaberi predložak", a button per template in its order, its title in 700 over its muted facts, "6 stanica", "1 stanica · kružni set · 4 kruga", `GymTemplate.facts`; since build 3, 27.11.2026, the templates that hold a block, staff's on `/dvoranski/predlosci`, in their order there; under a hairline "ili složi sam/a:" with "+ Stanica" and "+ Kružni set"). **A Stanica, empty**: the kicker "Stanica 2 od 6" (its number among the stations, the route's), ONE form, all in sight: Vježba (the library's combobox over the page's one `#library-json`, the tag chips above it, a converted slot's hint starting it, `qmtHintStart`), Serije, Ponavljanja, Opterećenje (kg), Pauza (s), Vrijeme (s), Komentar, "Kreni" (`.btn`; nothing picked "Odaberi vježbu s popisa."); sent, the page back at it started, the focus in its first set (`?kreni=1`); a quiet "Ukloni stanicu". **A Stanica, started**: its exercise's name (h2), what was asked ("6 × 10 · 40 kg · pauza 90 s", `GymTrainingItem.asked`), its comment, "Kako se izvodi" (the clip, preload none, what one rep is, the cues), the set table (base.html's `.pl-sets`: a row per planned set, three with none given, prefilled with the plan alone, rule 5; a ticked row as saved; the round ✓ per row, the script's, which saves the ticked rows whole, a fetch, and starts the pause bar with the station's Pauza; a tick on a row with no number refused, "Upiši broj pa označi seriju."; "+ serija" to `db.MAX_SETS`; the no-JS "Spremi"), "Koliko je bilo teško? (neobavezno)" and its ten buttons (a tap saves the block's rating, a fetch; its "Spremi" the no-JS way), "Nastavi trening" (`.btn`: the next block after it not done, else the first not done before it, else the "what next" card, `app._gym_next`) and "Završi trening" (`.btn.btn-ghost`), both always there, then quiet "Uredi" (a `<details>`: the form again with its values, the exercise fixed as text once a set is ticked; refused, open again, `?uredi=1`) and "Ukloni stanicu" (asks while it holds a tick: "Ukloniti stanicu?", "Upisane serije ove stanice se brišu."). An exercise gone from the library: its name, its sets as text ("Odrađeno: …") and "Ukloni stanicu". **A Kružni set, being set up** (no Krug saved and none asked for): the kicker "Kružni set", ONE form, a hairline box per row (Vježba, the combobox, an empty row let be; Ponavljanja, Opterećenje (kg), Vrijeme (s); its quiet ✕, a submit of the form that saves the other rows first, asking while the row holds a set), "+ vježba" (the same: saves, then a row more, at most 12, its picker focused, `?red=`), Krugova (4) and "Pauza nakon kruga (s)", "Kreni" (saves the rows and the plan and opens Krug 1, `?krug=1`); a quiet "Ukloni kružni set". **A Kružni set, started**: "Krug 2 od 4" (`.pl-round`; every Krug saved, "4 kruga" and "✓ Spremljeno") with quiet "− krug" and "+ krug"; its Krug, each a `<details class="gt-kr">`: a saved one folded to its line ("Krug 1 ✓ · 10 × 16 kg · 10 · 30 s", `GymTrainingBlock.round_line`), opened again to be corrected ("Spremi izmjene", `.btn-ghost.btn-sm`); the Krug on screen, the first not saved, open: each row a hairline box, its name, what a round asks (`round_dose`), "Kako se izvodi", its inputs by its shape (PON. · KG, SEK., PON. · SEK.), their first values what this Krug saved, else what the Krug before did, else the plan, ONE button "Krug 2 odrađen" (`.btn.btn-sm`) → saved, the pause bar counting the set's pause after a Krug (`?odmor=`, a first save's alone: a correction is made during the pause), the Krug just saved still open under its ✓ (`?spremljen=<n>`), the next open under it, its first values the corrected ones; with its last Krug saved "Koliko je bio težak ovaj kružni set? (neobavezno)" and its ten buttons; "Nastavi trening" and "Završi trening" as a station's; quiet "Uredi" (the rows and the plan again: a row that holds a set fixed, its ✕ asking first, "Ukloniti vježbu?") and "Ukloni kružni set" (asks while it holds a set). **The overview** (`aside.pl-side#pregled`, "Pregled"): every block in order, each a link (`?blok=<id>`; nothing gates a tap): "STANICA 1" over its exercise and its mark ("✓", "2/6", none) and what was asked, an empty one "prazna"; "KRUŽNI SET" over "4 vježbe · krug 2/4" (every Krug saved "4 vježbe · 4 kruga") or "prazan", its mark ("✓"); the one on screen ringed (`.is-cur`, `aria-current="step"`); at its end "+ Stanica" and "+ Kružni set" (not at 40). A tick updates its row's mark, the strip and the pill in place. **The pause bar** is the player's (`_rest_bar.html`), and a pause survives a reload of the same training's page (`qmtRest.keep("qmt-gym-rest-<id>")`: its end in sessionStorage, picked up while it lies ahead; "Preskoči odmor" and its end forget it; a `?odmor=` leaves the address once begun, `history.replaceState`). **The foot** (`.gt-foot-col`): the saved osvrt's facts with "Uredi osvrt"; while the training holds blocks and no tick, a quiet "Promijeni predložak" (`details.gt-change#predlozak`: the chooser's templates again, each asking while any exercise is chosen, "Zamijeniti predložak?", "Odabrane vježbe se brišu."); "Isprazni trening" (a termin's, while it holds a block; asks; every block goes) or, outside a termin, "Obriši trening". **Read only** (a member after the window): "← Natrag", the head, the state line, the overview with each block's record as text (a block with no exercise not shown: the diary's lines), the saved osvrt; no card, no form, no input, no button. A form's word comes back to the main card (`?blok=`) or to the chooser (`?predlozak=1`, the main card's, or the foot's, open), never to the page's top. Every text a slot (`gym.*`, 65; the player's and the day page's where the words do the same job) |
| `/dvoranski/trening/{id}/osvrt` | as above | The gym training's osvrt (`karton_trening_osvrt.html`): the online finish screen's clothes and slots (`kraj.*`: Napor, ten round buttons, required; Osjećaj (neobavezno); Komentar; "Spremi trening"), its kicker "Osvrt na trening", the title, the date and time, "Natrag na trening", no nudges, the tab Dvoranski treninzi lit as on the training's page (since build 2, 27.11.2026); `POST` → `db.finish_gym_training` ("Neispravan osvrt." for a napor outside 1–10 or an osjećaj that is none: the page again, 400, what was chosen kept) → the karton at its diary row (`#gt-<id>`), "Trening je spremljen."; `finished_at` its first save, kept at the next. A training not writable now: its page |
| `POST /dvoranski/trening/{id}/…` | as above | The gym training's writes (27.11.2026), each the effective user's own (another member's training or block 404) and asking rule 1 (`db.gym_can_write`, `staff` = `app._actor`; refused: "Upis ovog treninga je zatvoren — trener ga i dalje može urediti.", nothing changed), plain forms but the tick and the rating's tap; declared after the GETs, under `/dvoranski`, which no other route uses (the landing's gym cards are `/dvorana`): `…/predlozak` (`predlozak`, a template's id: `db.apply_gym_template`; the page on its first block; refused, "Odaberi predložak s popisa." / "Trening je već započet — predložak se više ne može zamijeniti.", at the chooser, `?predlozak=1#predlozak`), `…/blok` (`vrsta` stanica / kruzni: `db.add_gym_block`, the page on the new block; "Najviše 40 stanica i kružnih setova." at the top), `…/blok/{bid}/obrisi` (`db.delete_gym_block`; "Stanica je uklonjena." / "Kružni set je uklonjen." at the top), `…/blok/{bid}/stanica` (a Stanica's "Kreni" and "Uredi"'s "Spremi", `uredi`: `exercise_id`, `sets`, `reps`, `kg`, `rest`, `seconds`, `note`, `db.set_gym_station`; Kreni back started, `?kreni=1`, Spremi "Spremljeno."; refused in the card, `?uredi=1` for Uredi), `…/blok/{bid}/odradeno` (a Stanica's tick: `polja` the shape the page was drawn for, else the player's "Trening se u međuvremenu promijenio — …"; `rows` rows of `reps_n` / `kg_n` / `sec_n`, at most 30 read; JSON for an `Accept` of application/json, `{"ok", "error", "mark", "done"}`, else back at the station; a Kružni set's block refused the same way), `…/blok/{bid}/ocjena` (the block's rating, `effort` 1–10 or empty, `db.rate_gym_block`; JSON `{"ok", "error"}` or back at the block), `…/blok/{bid}/plan` (a Kružni set's rows and plan, `stavke` the rows the page was drawn for, `vjezba_<id>` / `reps_<id>` / `kg_<id>` / `sec_<id>`, `rounds`, `rest`, `db.save_gym_circuit`; `kreni` (the setup's: Krug 1, `?krug=1`), `dodaj` (saved, then `db.add_gym_row`, `?uredi=1&red=<id>#red-<id>`), `ukloni` (a row's id: the rest saved, that row kept as stored, then `db.delete_gym_row`; a refused save removes nothing), else "Spremljeno."; refused in the card, `?uredi=1`), `…/blok/{bid}/krug/{n}` (a Krug: `reps_<id>` / `kg_<id>` / `sec_<id>`, a row with every input empty not done in it, `stavke`; `db.save_gym_round`; back at it, `?spremljen=<n>` and on a first save `&odmor=<the pause after a Krug>`, `#krug-<bid>-<n>`; refused there, open, `?krug=<n>`), `…/blok/{bid}/krugovi` (`smjer` plus / minus: `db.set_gym_rounds`), `…/isprazni`, and outside a termin `…/datum` (`db.read_day`) and `…/obrisi` (a termin's 404: it goes with its booking); `…/osvrt` the osvrt's. While staff act as the member, base.html marks the tick's and the rating's fetch as it marks every form, and the guard records each write |
| `GET /karton/termin/{id}/trening`, `/karton/trening/{id}`, `…/osvrt` | anyone | The gym training's addresses of 26.11.2026: each 303s to its `/dvoranski` one, its query kept (`app._same_query`); their writes went (a POST there is 404 or 405) |
| `/dvoranski/predlosci` | trainer/owner | **"Predlošci treninga"** (27.11.2026, build 3 of `roadmap/2026-11-27-dvoranski-treninzi-plan.md`; the owner: "In the start, there would be two templates. […]"; "Amir will create the third template later and give it a name"; "I dont like the fact that I need to go to 'Online treninzi' and create a new programme there which is not applicable to gym trainings."): staff's list of the gym training's templates (`dvoranski_predlosci.html`, `app.gym_templates_page`; `_require_trainer`: a member 403, a guest to the login, refused while staff act as a member, as every staff page), under the tab Dvoranski treninzi (lit there, Admin ▾ not), its way in staff's own `/dvoranski`'s "Predlošci treninga →". The /admin pages' look, a 720px column: the h1, the lead "Od predloška član kreće kad otvori prazan trening: stanice i kružni setovi redom, bez vježbi. Vježbe i brojke upisuje sam.", then a row per template in its order, the member's chooser's (the programme editor's day rows, `.card.it-row#predlozak-<id>`): its name in 700 (`.it-name`, a link to its editor), its facts muted, the chooser's words (`GymTemplate.facts`: "6 stanica", "1 stanica · kružni set · 4 kruga"; one with no block "prazan — članovi ga ne vide"), "Uredi" (`.btn-quiet.btn-sm`), ↑ / ↓ (one tap; the first's ↑ and the last's ↓ disabled) and ✕ (asks: "Obrisati predložak?", "Treninzi koji su već krenuli od njega ostaju kakvi jesu.", "Obriši"); none, "Još nema predložaka.". Under them "+ Novi predložak" (`form.card.tp-new#novi`: Naziv, needed, 80 characters at most, then the button); at 12 (`db.GYM_MAX_TEMPLATES`) not offered, "Najviše 12 predložaka." in its place (`.tp-cap#novi`). A move's word in its row, the add's in its card, never at the page's top; a template deleted, "Predložak je obrisan." at the top. Staff's own words (a staff-only template: literals) |
| `/dvoranski/predlosci/{id}` | trainer/owner | A template's editor (27.11.2026, build 3; `dvoranski_predlozak.html`, `app.gym_template_page`; none such 404): a crumb back to the list, its name the h1 (no lead: the column keeps a lead's room); Naziv and Spremi (`form.card.tp-card#naziv`); then **"Blokovi"** (`section.tp-sec#blokovi`), a row per block in its order (`.card.it-row#blok-<id>`): a Stanica named by its number among the stations, as a member's overview numbers them ("Stanica 2", `GymTemplate.labelled`), nothing to set; a Kružni set ("Kružni set") with its three numbers in ONE small form on the row's second line (`form.tp-nums`: Vježbi, its rows, 1–12; Krugova, 1–20; "Pauza nakon kruga (s)", 0–3600, empty for none; Spremi; the three side by side and Spremi across under them on a phone, the four on one line from 600px); each row ↑ / ↓ and ✕ (one tap: nothing a member wrote is in a template; their forms stand after the list, `form=`); "+ Stanica" and "+ Kružni set" after the last (`.act`; a Kružni set starts with 4 rows and 4 Krug, no pause; at 40, a training's own cap, not offered, "Najviše 40 stanica i kružnih setova." in their place); the muted line "Član blokove vidi ovim redom; svaki može preskočiti, ukloniti ili dodati svoj."; at the bottom "Obriši predložak" (`.ex-delete`, asking as the list's ✕). A save or a move comes back at its row (`?blok=<id>#blok-<id>`, "Spremljeno." there), the name's at its card (`?naziv=1#naziv`), a block removed or an add refused in the blocks' section (`?blokovi=1#blokovi`: "Stanica je uklonjena." / "Kružni set je uklonjen.", the training page's words), never at the page's top. A template is its blocks alone: no exercise, no Stanica's numbers (the owner: "The template's stations are empty") |
| `POST /dvoranski/predlosci…` | trainer/owner | The templates' writes (27.11.2026, build 3), each `_require_trainer`'s and under the `gym_templates` table's lock (Architecture, "The gym training", rule 9), plain forms (`app._tpl_url` their addresses): `POST /dvoranski/predlosci` (`title`: `db.add_gym_template`, then its editor; "Upiši naziv predloška.", "Najviše 80 znakova.", "Najviše 12 predložaka." in the add card, `?novi=1#novi`, nothing made), `…/{id}/naziv` (`title`: `db.rename_gym_template`, the same refusals in its card), `…/{id}/pomak` (`smjer` gore / dolje: `db.move_gym_template`; back at its row, "Spremljeno." when it moved, no word at either end), `…/{id}/obrisi` (`db.delete_gym_template`; the list, "Predložak je obrisan."; one gone already, no word), `…/{id}/blok` (`vrsta` stanica / kruzni: `db.add_gym_template_block`; a kind that is none or a template gone 404), `…/{id}/blok/{bid}` (`slots`, `rounds`, `rest`: `db.set_gym_template_block`, "Neispravan broj." in its row, nothing changed; a Stanica's or another template's block 404), `…/{id}/blok/{bid}/pomak` (`db.move_gym_template_block`) and `…/{id}/blok/{bid}/obrisi` (`db.delete_gym_template_block`; gone already, no word) |
| `/vodic` | member, staff | **"Vodič kroz trening"** (29.10.2026): the guide through the training on a page of its own, the one `/upitnik` opens on (`_vodic.html` prints both: `guide(href)`), in the questionnaire's clothes (its 640px column; `solo_page` for a member, the trainer and the owner keep their bar and edit its texts here as on `/upitnik`); its button a link to `/upitnik?od=1`, which opens on question 1. For any member, a plan or not; a guest is sent to log in. In no nav and linked from nowhere yet: the owner wants it to greet a client at the first sign-up / the first payment (not built), one link each |
| `/treninzi` | client/trainer | Online programmes — automatic (see below). A client's list: **every online programme of his razina, whatever its type** since 23.11.2026 (the owner: "I want to allow the users to be able to access all types of training. The questionnaire only determines the level of fitness and the trainings are available for everybody."; his razina × cilj combo until then; a dvoranski one never, 24.11.2026), grouped by type: a caption per type that has one (the day page's `.dx-cap`, `upitnik.GOALS`' label in its order: Cijelo tijelo, Gornji dio tijela, Donji dio tijela, Core), its cards under it, each card "2 treninga" (how many days, 30.10.2026) and the intro's start; the head pill his razina alone ("Srednja razina"), the lead "Programi tvoje razine — određuje je upitnik."; none for his razina: "Programi za tvoju razinu još se pripremaju." Staff's: the lead (the matching is automatic, the programmes are his: "Programe slažeš sam: za svaku razinu napravi programe po tipu pa im dodaj treninge i vježbe. …", 23.11.2026), the table of every programme per razina, its Tip (the types' order, Core fourth), Treninzi and Vježbe (across its days; "prazno!" with none; since 26.11.2026 a programme that holds empty slots says them after the count, muted, "0 · 7 praznih mjesta", `db.program_slot_counts`, and only one with neither exercise nor slot is "prazno!"; a razina with none, "Nema programa za ovu razinu."), a dvoranski programme's title followed by a muted chip "dvoranski" (`.venue-chip`, base.html; 24.11.2026, no new column), the lead's last sentence "Dvoranski programi su samo tvoji: polaznici ih ne vide." (since 27.11.2026, build 3 of the dvoranski treninzi, only while one exists: `has_gym_programs`), then **Novi program** (naziv, **Tip programa** ("Tip treninga" from 23.11.2026 until 26.11.2026, when the owner renamed it: "that is the name of the Programme and not of the training. We have Program->Trening->Vjezbe hierarchy."; "Cilj" until 23.11.2026, the column still `goal`; four types since then, Core last: the owner, "we need 'cijelo tijelo' 'gornji dio tijela' 'donji dio tijela', but also 'core'"), razina, the two selects in one grid, `repeat(auto-fit, minmax(160px, 1fr))`, a row where they fit and stacked on a phone, uvod; "Kreiraj i dodaj treninge" → its editor, the programme with no day; a type or razina that is none: "Odaberi razinu i tip programa."; **no Vrsta since 27.11.2026** (build 3 of `roadmap/2026-11-27-dvoranski-treninzi-plan.md`; the owner: "I dont like the fact that I need to go to 'Online treninzi' and create a new programme there which is not applicable to gym trainings": a gym training starts from Amir's templates, `/dvoranski/predlosci`): every new programme is online, a posted `venue` ignored; from 24.11.2026 until then "Vrsta", Online or Dvoranski, `Program.venue`, idea 3). Opening it makes nothing since 30.10.2026: every programme is Amir's (idea 3) The client's list's texts are slots since 25.11.2026 (`treninzi.*`), edited on /tekstovi (staff's /treninzi is the table). |
| `/treninzi/{id}`, `/treninzi/{id}/dan/{did}` | client/trainer | **A programme is days since 30.10.2026** (stage 2 of the online treninzi spec; idea 3). Its page: crumbs, the title (a dvoranski programme's, for staff, with the muted "dvoranski" chip beside it, 24.11.2026; a client never reaches one: 403), "2 treninga", its intro (the trainer's "Uredi program" under it), then its days as cards, each one link (52px, → at the right): "Trening 1 · Cijelo tijelo" in 700 and, muted, "Preporučeno: ponedjeljak · 7 vježbi" (no weekday: "7 vježbi"; a day with a circuit part, 24.11.2026, "… · 7 vježbi · kružni trening", `ProgramDay.has_circuit`: a circuit on a part that holds an exercise); none, "Program još nema treninga." (the trainer: "… — dodaj prvi u uređivanju."); any day opens any time. **The day's page** (the normal layout, a 640px column; the trainer gets "Uredi trening" under its intro): crumbs (… / "Trening N"), the label as the h1, "Preporučeno: ponedjeljak · 7 vježbi" (" · kružni trening" after it as on the card), the intro (its line breaks), the intro video first when it has one ("Uvodni video — pogledaj ga prije treninga.", `controls playsinline preload="metadata"`, the clip's dark box), then the whole list, Shape's in QMT's tokens: per section that holds an exercise its caption (ZAGRIJAVANJE, GLAVNI DIO A, GLAVNI DIO B, ISTEZANJE since 23.11.2026, GLAVNI DIO C since 26.11.2026, after B: display .78rem, letter-spaced, muted; a day with nothing in B shows no B; since 26.11.2026 a part as the day names it, "KRUG 1", `part_label`; a dvoranski day's slot, staff's, a muted row, dashed, "Prazno mjesto · čučanj" (`dan.slot`, the hint after it) and its dose, no `<details>`, no "Vježba n", the lead "0 vježbi · 3 prazna mjesta", the slots after the count, the programme page's card too; a day of slots alone offers no Kreni), each exercise a native `<details>` (works without JS) whose `<summary>` is the row, 56px: "Vježba n" (counted across the day), the name in 700, the dose at the right ("3 × 10", "2 × 30 s", tabular; since 25.11.2026 a planned weight after a middle dot, "3 × 10 · 20 kg"), under them one muted line, "Odmor između serija: 60 s · Odmor nakon vježbe: 90 s · 8 kg" (each part only when set; the rest after the exercise since 30.10.2026), ▷ at the far right turning down when open; open, the clip (`preload="none"`: twenty rows fetch no twenty clips) or "Vježba još nema videa.", "Jedno ponavljanje: …", the instructions. **A circuit part** (24.11.2026, kružni trening; idea 3): its caption followed by one muted line (`.dx-circ`, the `.dx-sub` size), "Kružno · 3 kruga · odmor između krugova 120 s" (the rest only when set, `ProgramDayCircuit.line`), its rows the dose of a round (`round_dose`: "10 ponavljanja", "30 s", "5 × 30 s", "10 ponavljanja · 20 kg") and under it the note alone (since 25.11.2026 no rest of an exercise's applies there: no pause between a circuit's exercises, the rest is after the round). **Since 30.10.2026 (stage 3, the player)** each day card's muted line ends with the viewer's state ("… · odrađen 2×", "… · u tijeku", "… · nedovršen" for a pass open too long (31.10.2026, the player's row), nothing for a day never done; `db.day_states`, one query), and the day's page says it under the lead (muted 600: "Još nije odrađen." / "Odrađen 2× · zadnji put 12.11." ("danas", "jučer", another year's date with its year) / "U tijeku — nastavi gdje si stao/la." / since 31.10.2026 a stale pass's "Nedovršen trening od jučer (6 od 8 vježbi) — nastavak nije moguć: završi ga ili ga odbaci."), then **"Kreni"** (`.btn`, a form, `POST …/kreni`; full width on a phone) or, while a pass is open, **"Nastavi"** (the same form: the route lands on the first step the pass has not saved, a circuit's round when no exercise of it holds a set of it, the last when all are) with "Odbaci započeti trening" beside it (`.act.act-quiet`, `data-confirm` "Odbaciti započeti trening?" / "Spremljene serije ovog pokušaja se brišu. Trening možeš započeti ponovno." / "Odbaci"); a day with no exercise offers none, unless a pass is open on it (its exercises deleted since, 4.11.2026): then the state line stays, with Nastavi (→ its finish screen), or a stale one's Završi trening, and Odbaci, Kreni alone hidden; a stale pass (31.10.2026) gets **"Završi trening"** (a link to its `…/kraj`, a `.btn` in Kreni's `.go` place) instead of Kreni / Nastavi, Odbaci beside it. While a pass is open the list's saved rows carry a green ✓ before the dose (a circuit's once every round is saved; some of them, a muted "2/3", `.dx-rounds`, its words for a screen reader "spremljeno 2 od 3 kruga": `app._marks`, 24.11.2026). At the bottom **"Povijest"**: the viewer's last five finished passes of the day, a card each ("12.11. · 6/8 vježbi · 38 min · napor 7 · dobro": the day's exercises now and the ones of them it saved, `WorkoutLog.done_in`, 4.11.2026; an exercise deleted from the library since stays in its "Serije", by name, after the day's own; the comment under it, "Serije" folded: "Goblet čučanj: 10 × 20 kg · 10 × 20 kg · 8 × 20 kg", a timed one "30 s · 30 s", a set with no weight its reps alone; since 25.11.2026 an exercise the client rated ends with its rating, "… · težina 8/10", `WorkoutLog.lines`, the karton's too) Every text of both pages a slot since 25.11.2026 (`program.*`, `dan.*`: "Preporučeno:", the state's two lines that name no value, Kreni / Nastavi, Odbaci and its confirm, the rests' captions, which the player shares, "Uredi program" / "Uredi trening"). |
| `/treninzi/{id}/dan/{did}/vjezba/{k}`, `…/kraj` | client/trainer | **The player** (30.10.2026, stage 3 of the online treninzi spec; idea 3; the owner: as on Shape Club's Gym Program page, "the set log is good, yes, but default value should be input like in shape club", "the whole list", the swap "we should add it as well"; no first-open tour, no music). `POST …/kreni` opens a pass (`db.start_pass`); `GET …/vjezba/{k}` is step k (1-based, the day's display order: an exercise, or in a circuit part one round of it, every exercise of the part on one screen since 25.11.2026 (one exercise of one round a step from 24.11.2026), `app._steps`, below; k below 1 404; since 4.11.2026 a k past the day's count, with a pass in progress (an exercise deleted from the library while the pass was open), its last exercise, or `…/kraj` when the day has none left, its save and its swap alike, which save and swap nothing; no pass in progress → the day's page), through `_program_or_403` as the day's page (staff may use it, their passes their own; since 24.11.2026 on their own karton too). The one-task layout (`solo_page = not can_edit_copy`: a member's small pill, staff's bar, the owner's whatever his flag), a 640px column; from 1000px two columns, the player and the list (380px) beside it. Top to bottom: **the segmented bar** (a 4px segment per step, a saved one `--accent`, the one on screen `--text` at 60%, the rest `--surface-2`; past 40 steps, `app.SEGMENTS_MAX`, one track instead, `.pl-track`, the segments' height and radius, its `--accent` fill the share of the steps saved, 24.11.2026), under it "← Natrag" (the day; the pass stays open) · the timer chip (a clock and "0:18" since the pass started, the script's: none without it) · "Završi trening" (`…/kraj`); **the clip** in its dark box (`playsinline loop muted autoplay controls preload="metadata"`; "Vježba još nema videa." on `--surface-2`), round 40px ‹ › at its edges (links to k−1 / k+1; none on the first / the last), a sideways swipe of 60px on the box or the card the same (the script); **the card**: "TRENUTNA VJEŽBA" + "3/8" (+ "✓ Spremljeno" in `--good` once saved), the name as the h1, a refusal's sentence under it, the dose (a planned weight after a middle dot, "3 × 10 · 20 kg", 25.11.2026), since 25.11.2026 **the line for the next time** when the client rated the exercise last time (`.pl-next`, muted: "Prošli put (23.11.): 10 × 20 kg, težina 5 — malo više: 21 kg.", "…, težina 8 — ostaje isto.", "…, težina 9 — malo lakše: 18 kg.", reps and seconds in their own words, "… — malo više: 11 ponavljanja."; `app._next_line`, from `db.next_load`, this pass's own entry of the step not counting as last time; with no rating nothing), "Odmor između serija: 60 s · Odmor nakon vježbe: 90 s" (each only when set), the note, "Kako se izvodi" (`<details>`: "Jedno ponavljanje: …", the instructions); swapped, the similar exercise's name, clip and cues and "Zamjena za: <the plan's>" muted. **The set log** (one form, `rows` + `reps_n` / `kg_n`, a timed exercise's `sec_n`, one that asks reps and seconds `reps_n` / `sec_n` (24.11.2026: its columns the item's `db.set_fields`), and since 4.11.2026 the hidden `item`, the exercise the page was drawn for: a save whose item is not exercise k's now, or none, is refused as a bad number is, "Trening se u međuvremenu promijenio — provjeri vježbu i spremi ponovno.", `DAY_CHANGED`, nothing saved): SET · PON. · KG (SEK.; an exercise that asks reps and seconds, the owner's "5 reps of 30 seconds of plank", SET · PON. · SEK., no KG, each set stored `{"reps": 5, "seconds": 30}`, the history's "5 × 30 s"), a row per planned set (1 when the plan says none, 20 at most: `db.MAX_SETS`, 12 until 26.11.2026, the owner: "Lets increase the 12 sets to 20 sets limit."), PON. the plan's reps, KG the last saved log's of that exercise (since 25.11.2026 read through `db.next_load`, where `db.last_sets` was: any pass of the client's, any day; set i's, the last one's past them; for none or 0 the plan's planned weight, else empty), SEK. the plan's seconds (after a rating the load next time fills them, `app._first_values`: a weighted exercise's KG, one he did with no weight its PON., a timed one its SEK.; idea 3), then one empty row more ("dodatna serija"); "+" (the script) adds rows up to 20; 44px inputs (`type=number`, kg `inputmode=decimal step=0.5`); **the rating** (25.11.2026; the owner: "if someone gave a feedback on a particular exercise of 7 or harder then the next appearance of that particular exercise does not increase its difficulty"): under the set log, above Spremi, "Koliko je bilo teško? (neobavezno)" (`.pl-rate`) and ten round buttons 1–10 (the finish screen's `.scale`, 36px, 40px on a coarse pointer, five and five where ten do not fit; a radio group `effort`, none chosen, a saved step's own chosen); **"Spremi"** (`.btn`, full width on a phone; "Spremi i završi" on the last) saves (`POST …/vjezba/{k}`, `db.read_sets` and `db.read_effort` → `db.save_sets`: the exercise done, the swapped one when swapped, the rating in its entry, `"effort": 7`, none no key, a re-save replacing it; anything else "Neispravan broj.") and goes on to k+1 or `…/kraj`; a refusal is the screen again, 400, its sentence under the name, what was typed kept ("Neispravan broj.", "Upiši bar jednu seriju.", "Najviše 20 serija."); a saved exercise's sets stay in its inputs (a re-save replaces them). **A circuit part is one screen per round** (25.11.2026; the owner's note to Amir: "Za krugove dodat da može dodat vježbe i onda on označi koje krugove koje je odradio. Pauza ide na kraju kruga a između vježbi nikakva pauza."; from 24.11.2026 each exercise of each round was a step of its own, saved by `db.save_round`, gone): `app._steps` gives a circuit part one `Step` per round (its round, its circuit, the part's `items` in the day's order, no `item`), and the round's screen is the player's layout with no clip box (so no ‹ ›, no swipe): the card's kicker "KRUŽNI DIO" with "k/n" and "Krug 2 od 3" (`.pl-round`, `--accent-dim` with `--accent-tint-ink`, PT Sans .78rem capitals; "✓ Spremljeno" once saved), the part's name as the h1 ("Glavni dio A", the page's title too; since 26.11.2026 the day's own name for it, "Krug 1"), one muted line (`.cr-intro`), "Vježbe idu jedna za drugom, bez pauze. Odmor nakon kruga: 120 s." (the second sentence only when set, "0 s" for a 0), a refusal's sentence, then a hairline box per exercise in the day's order (`.cr-row`): its name the summary of a native `<details>` (open: its clip, `preload="none"`, "Jedno ponavljanje: …", the instructions, as the day page's rows), its dose of a round muted (`round_dose`, the planned weight in it, and after a rating the word for the next time after it: "10 ponavljanja · 16 kg · malo više", "… · isto", "… · malo lakše"), its note, and its inputs by `db.set_fields` under small labels (PON. · KG, SEK., PON. · SEK.; `reps_<item id>`, `kg_<item id>`, `sec_<item id>`, 44px, the set log's look, named for a screen reader by the exercise and the label), their first values (`app._round_blocks`) what this pass saved for the exercise in this round, else the plan's reps / seconds (after a rating the load next time's, as on a normal step) and for the weight this pass's in the round before, else the load next time of this round's place (`db.next_loads`, this pass's entries of the round's exercises left out: the rounds before are this training, not last time), else the plan's kg; then the round's rating ("Koliko je bio težak ovaj krug? (neobavezno)"), ONE button, "Krug 2 odrađen" (`.btn`, full width on a phone; the day's last step's "Krug 3 odrađen — završi"), and "Preskoči →"; no ✓, no "+", no swap (a swap is a normal step's: one posted to a round swaps nothing). The button posts the round with a hidden `part` (the section's key) and `round` (either not step k's now, a normal step's form posted to a round, or a `round` or a `part` posted to a normal step, is refused as `DAY_CHANGED`) → `db.save_circuit_round` (in one write under the pass's row lock, two rounds at once keeping both: each exercise done gets its set of the round, `{"reps": 10, "kg": 20.0, "round": 2}`, sorted by round, a round saved again replacing itself alone; an exercise with every input empty is not done in it and loses the set of that round it had, its entry going when none is left; every one empty "Upiši bar jednu vježbu."; a bad number the screen again, 400, what was typed and chosen kept; the round's rating written on every exercise it saved, an unrated round leaving theirs: the last rated round's stands) and goes on to the next step with the circuit's rest after a round (`app._step_rest`: that alone, after the final round too, the pause before the next part; none for none or 0, never an exercise's own; never to `…/kraj`). A round is saved when any exercise of it holds a set of that round (`app._saved`): Kreni / Nastavi land on the first step not saved. Not built: a countdown for a timed exercise's work (rests alone count down). **The ✓ per set and the rest bar** (30.10.2026; the owner: "a timer which he can skip, in between sets as well as between exercises, which Shape Club also has"): the set log's last column, SET · PON. · KG · ✓ (a timed one's SET · SEK. · ✓, reps and seconds' SET · PON. · SEK. · ✓), a round 44px `button.pl-done` per row ("Serija n odrađena", `aria-pressed`; the header's ✓ says "Odrađena serija" to a screen reader), its cells rendered `hidden`, the script's ("+"'s clone carries one); a press marks the row done (`tr.is-done`: its number `--good`, the button `--good-fill`; the inputs as they were) and, when the exercise has a rest between sets (the form's `data-rest`, the item's `rest_seconds`; none for NULL or 0), starts the rest bar with it, afresh when one runs; a second press unmarks the row and starts nothing. The ticks live on the page: nothing is posted, a reload loses them, "Spremi" saves as before. The rest after an exercise (the item's `rest_after_seconds`, the plan's item's when swapped) rides on Spremi's redirect, `…/vjezba/{k+1}?odmor=<s>` (when > 0; never to `…/kraj`, never on Preskoči, ‹ ›, the swipe or the list), whose GET puts it on the form (`data-odmor`: an int 1–3600, anything else ignored; a refused save none) and the bar starts at load. **The bar** (`div.pl-rest`, `role="timer"`, hidden until a rest; since 26.11.2026 a partial of its own, `_rest_bar.html`, its look base.html's and its script `window.qmtRest` (`begin`, `stop`, `unlock`), shared with the gym training's page, the player's behaviour as it was): fixed at the bottom at every width, the dock's place and glass, 16px from the screen's edges, 640px at most, 64px, `--r-lg`, lifted over staff's ✎ pill; "ODMOR" over the countdown ("0:45", Inter 800, from an end time redrawn every 250 ms, so a tab woken from the background shows what is left), a 4px track whose `--accent` fill drains, and "Preskoči odmor" (a white pill, 44px on a coarse pointer: ends it at once, silently; not "Preskoči", the quiet link's word, which skips the exercise); at zero "KRENI" and "0:00" for about 1.5 s, then it goes, the phone vibrating (`[150, 80, 150]`, only after a tap on the page) and two quiet 880 Hz beeps where the browser allows (the AudioContext made and resumed at the first ✓, a tap, for iOS; a rest that starts at load may end silent, "KRENI" its signal); while it shows the dock is hidden and `.pl` gets room under it (`.has-rest`); leaving the page ends it, nothing is kept. Under it, quiet: "Preskoči →" (k+1, nothing saved; the last's "Preskoči i završi" → `…/kraj`) and, when the plan's exercise has similar ones (its own swaps, `Exercise.alternatives`: one way since 4.11.2026), **"⇄ Zamijeni vježbu"**, a `<details class="swap">`: "Slične vježbe", a row each (name, tags, ⇄ posting `…/vjezba/{k}/zamjena` with its id; when swapped "Vrati <the plan's>" first, `vrati=1`; any other id: "Ta vježba nije među sličnima."). **The list** (`#popis`): the day's sections that hold an exercise, each its caption (Glavni dio A, then Glavni dio B, since 23.11.2026, then Glavni dio C, 26.11.2026; a part as the day names it, `part_label`, 26.11.2026; a circuit part's followed by "· kružno · 3 kruga", 24.11.2026; a slot is no step, no row, not counted), and their rows (the day page's `.dx-*`; a circuit's the round's dose and the note alone), each a link to its exercise's first step not saved (its first when all are; a circuit's exercise its part's first round not saved, 25.11.2026), the ones on screen ringed in `--accent` (`aria-current="step"`; a round's every exercise), a saved one a green ✓ before its dose (a circuit's every round; some, a muted "2/3"), a swapped one its similar exercise's name "(zamjena)"; on a phone under the player, and a fixed dark pill at the bottom (the topbar's glass, `env(safe-area-inset-bottom)`, lifted over staff's ✎ pill) "Vježbe · 3/8 ✓" (counted by exercise: one counts once it has any entry, a circuit's after one round) → `#popis`, gone from 1000px. **The finish screen** (`…/kraj`, the same layout; no pass in progress → the day's page): "TRENING ODRAĐEN", the day's label as the h1, "6 od 8 vježbi · 38 min" (saved of the day's items now, the time so far; a day holding no exercise now "3 vježbe · 38 min", every entry, `WorkoutLog.done_text`, the karton's words for a day gone: the Povijest's cards and the stale state line say it the same way, 4.11.2026), the osvrt in the questionnaire's clothes: Napor, its ten round buttons (radio, required), Osjećaj, its three choice rows (`FEELING_LABELS`, optional), Komentar (optional), **"Spremi trening"** (`POST …/kraj`, `db.finish_pass`: its length the server's clock) → the day's page `?ok=Trening je spremljen.`; a refused osvrt ("Neispravan osvrt.", the karton's) the screen again with what was chosen; under it "Natrag na vježbe" (the last step) and "Odbaci trening" (the accent, `data-confirm`, `POST …/odustani` → `?ok=Započeti trening je odbačen.`, a finished pass never). **Leaving asks, and a pass cannot hang** (31.10.2026; the owner: "When a user tries to leave the training tab, there should be a popup warning asking if he wants to finish the training and then he decides. It shouldn't be possible to continue the training and have a hanging training of 9 hours like my account now does."): the player and the finish screen carry `#leaveDlg` (`_pass_leave.html`, included at the end of their content, `leave_mode` `player` / `kraj`; base.html's modal idiom, `data-pass` the day's path): a tap on a link or a form sent that leaves the pass (anything but its exercises, `…/kraj` and `…/odustani`: the brand, "← Natrag", a tab, Odjava; not a `#` link, a new tab or another site; capture-phase listeners) opens it instead, "Završiti trening?", finish or discard, never "later": on the player its sentence and "Odbaci trening" (`.btn-ghost.btn-sm`) · **"Završi trening"** (`.btn.btn-sm`, autofocus: → `…/kraj`), on the finish screen "Osvrt još nije spremljen. …" and "Odbaci trening" · **"Natrag na osvrt"** (closes it on the first napor button); "Odbaci trening" POSTs `…/odustani` (fetch) and then goes where the tap was going (a failed one: "Nije uspjelo — pokušaj ponovno.", the page stays); the ✕, Escape and the backdrop only close it. The finish screen's own Odbaci is inside the pass (`#confirmDlg` asks; cancelled there, the page counts as not left). What no link carries (the tab or the app closed, an address typed, a reload) meets the browser's own `beforeunload` prompt (its words; Chrome's only after a tap on the page; iOS Safari never shows one); the swipe goes unasked (`window.qmtPassGo`). Without JS every link goes as before. **The server's rule** for what no prompt catches: a pass with no activity for `PASS_STALE_HOURS` (2; its start or its last save, `WorkoutLog.stale`) is stale: Kreni / Nastavi, an exercise's screen, its save and its swap 303 to `…/kraj` (nothing saved or swapped), whose kicker says "Nedovršen trening", a muted `p.kr-stale` under the sum "Započet jučer i nije završen — nastavak više nije moguć. Spremi osvrt ili trening odbaci." ("danas" / "jučer" / a date, the day page's words: `pass_when`), and no "Natrag na vježbe"; the sum's time and the stored length run to its last save (`active_seconds`), not to the osvrt hours later Every text of the player, the finish screen and the leave dialog a slot since 25.11.2026 (`player.*`, `kraj.*`, `leave.*`: the round's screen ("Krug 2" code, its button's "odrađen" a slot), the rating's questions, the set log's headers, the swap list, the dock's word, the rest bar's words, the script's too); the route passes the rests' values, the template their captions. |
| `/treninzi/{id}/uredi`, `/treninzi/{id}/dan/{did}/uredi` | trainer/owner | **The programme's editor** ("Uredi program"; a dvoranski programme's h1 followed by the muted "dvoranski" chip, 24.11.2026): its form (tip programa, razina, the two selects in one auto-fit grid, naziv, uvod; no vrsta since 27.11.2026, build 3 of the dvoranski treninzi: the programme keeps the stored one, a posted `venue` ignored, so a dvoranski one stays staff's, edited, its days' empty slots as they work, and deleted; Online / Dvoranski from 24.11.2026 until then), its lead ("Program ima treninge; svaki trening ima zagrijavanje, glavni dio A, B i C te istezanje, a vježbe biraš iz baze vježbi." (C since 26.11.2026; the day editor's lead names them too, then "Svaki dio možeš preimenovati za ovaj trening." and, on a dvoranski day, a sentence on the slots) + since 24.11.2026 "Svaki dio može biti kružni: vježbe idu jedna za drugom, s odmorom između krugova." + "pogledaj kako polaznik vidi →"), then **Treninzi**: a row per day (`#dan-<id>`): its label (a link to its editor), "ponedjeljak · 7 vježbi" muted, Uredi, ↑ / ↓ (the day trades places and numbers with its neighbour) and ✕ ("Obrisati trening?", the exercises stay in the library); "+ Dodaj trening" (a day after the last, then its editor); "Obriši cijeli program". **The day's editor** (crumbs to the programme's editor, "Trening N"): its form (Naslov, Preporučeni dan "Bez preporuke" / ponedjeljak … nedjelja, Uvod), **Uvodni video** (the exercise page's video card: upload, replace, remove, the iPhone hint; `dan-<id>-<hex>.<ext>`), then **Vježbe**: every section's caption (five since 26.11.2026, Glavni dio C after B; a renamed part's its name and its default in brackets, "KRUG 1 (Glavni dio A)", `.st-cap-def`), its rows or "Nema vježbi."; **"Preimenuj"** (26.11.2026): beside "Kružno", the two in one wrapping row (`.st-tools`, the open one the row's width), a native `<details class="st-circ st-name">` in its look, ONE form, "Naziv dijela" (maxlength 60, its placeholder the default) and Spremi → `POST …/dio/<key>/naziv` (`db.set_part_name`; empty, the default back), back at the part (`?dio=<key>&naziv=1#dio-<key>`) with its word there, a refusal ("Najviše 60 znakova.") opening "Preimenuj" again, not "Kružno"; every Dio option of the day's forms names the part as the day does; **a dvoranski day's slots** (26.11.2026): a slot's row says "Prazno mjesto" and its hint muted after a middle dot where an exercise's name stands (`.it-slot-name`, no link, no "video ✓"), ↑ / ↓ / ✕ as any row (✕: "Maknuti prazno mjesto?"), its form the row form plus "Natuknica" (maxlength 80), and under it **"Popuni vježbom"** (a `<details>` in the "Kružno" pill's look, rendered hidden, the script's: the library's combobox, base.html's `qmtCombobox` in its rows mode over the add card's select's options, opening with the hint typed in, so the list is already narrowed (since 27.11.2026 only while the hint finds something: one that matches no exercise's name or tag starts the picker empty, on the whole list, base.html's `qmtHintStart`, a gym training's slot card too), and "Postavi" → `POST …/stavke/<id>/vjezba`, `db.fill_slot`, back at the row, `?stavka=<id>`, a refusal with `&popuni=1` opening it again; without JS nothing fills a slot); the add card's second way on a dvoranski day, under a hairline (`.add-slot`): "Natuknica (neobavezno)" and its hint ("npr. čučanj, potisak — sužava popis vježbi kad se mjesto popunjava") and "Dodaj prazno mjesto" (its own button, `formaction` → `POST …/mjesto`, `formnovalidate`: the card's Dio and numbers, `db.add_day_slot`; Enter in its field adds the slot, never the picked exercise; base.html's combobox skips its "nothing picked" check for such a button), back at the card, "Dodano u Krug 1: prazno mjesto."; with an empty library the card keeps its Dio, numbers and this way; an online day's card has no such way and the route refuses it; **under each caption its "Kružno"** (24.11.2026, kružni trening; the lead's sentence "Svaki dio može biti kružni: …" too): a native `<details class="st-circ">` whose summary says the part's state, "Kružno: isključeno" (muted, a hairline pill) or "Kružno · 3 kruga · odmor između krugova 120 s" (`.on`, the accent's tint), and whose ONE form (`POST …/dio/<key>/krug`): "Kružni dio" (a checkbox, `circuit`), Krugova (`rounds`, 2–20, 3 when new), "Odmor između krugova (s)" (`rest`, 0–3600, empty for none), Spremi → `db.set_circuit`, unticked `db.clear_circuit` whatever the numbers; back at the part (`?dio=<key>#dio-<key>`) with "Spremljeno." or the refusal's sentence ("Neispravan broj.") in that part, under its caption, the page's top none, the details open again after a refusal (a section that is none: "Odaberi dio treninga." at the top). In a circuit part a muted hint under it, since 25.11.2026 "U kružnom dijelu vježbe idu jedna za drugom, bez pauze: upiši ponavljanja ili sekunde i kilažu. Odmor je nakon kruga.", and each row's form asks no Serije, no Odmor (s) and since 25.11.2026 no Nakon vježbe (s) (none applies there: no pause between a circuit's exercises, the rest is after the round; the grid as it is, three fields fewer, Dio · Ponavljanja, Sekunde · Kilaža (kg), its lines level at 360 / 390 px) and posts a hidden `circuit`, so the route keeps the item's stored sets, rest between sets and rest after it (`db.KEEP`), into another part too, where they apply again. Each part ends with **"+ Dodaj vježbu u ovaj dio"** (25.11.2026, `.act.st-add`; the owner: "we need to allow Amir to add exercises which go into one circle of exercises"): a link to the add card with that part chosen, `?dodaj=<key>#dodaj` (its Dio selected, the picker the page's autofocus), which the script follows in place (no reload: the Dio set, the card scrolled to, the focus in the picker with its list shut, the combobox's `focus()`); a row (`#stavka-<id>`) the exercise's name (a link to it in the library), "video ✓" / "bez videa", ↑ / ↓ (within its section) and ✕ (their forms after the list: a form holds no form), and under them the row's own form, Dio, Serije, Ponavljanja, Sekunde, **Kilaža (kg)** (25.11.2026, the planned weight, `kg`: 0.5–500 in steps of 0.5, "2,5" or "2.5", `db.read_item_kg`, empty none; the dose says it, "3 × 10 · 20 kg"), Odmor (s), Nakon vježbe (s) (`rest_after`: the rest after the exercise, before the next one, the player's rest between exercises; 30.10.2026, the lead saying what the two rests are), Napomena, Spremi (two columns on a phone, Dio beside Serije, Kilaža beside Odmor (s), four from 600px, every control 44px on a coarse pointer; a label its column cannot hold on one line wraps, each field's control at its bottom, so a line's controls stay level); empty is none, sets 1–99, reps 1–999, seconds 1–3600, either rest 0–3600 ("Neispravan broj."), reps and seconds together since 24.11.2026 (the owner: "5 reps of 30 seconds of plank"; refused until then, "Upiši ponavljanja ili sekunde, ne oboje.", which went with the CHECK; the lead's sentence "Ponavljanja i sekunde mogu zajedno: 5 ponavljanja po 30 s."), a note up to 500; a row moved to another section goes last in it; the save comes back at the row (`?stavka=<id>#stavka-<id>`), which carries its own "Spremljeno." or the refusal's sentence, the page's top none (a phone scrolled to the row would not see it; Fable's review, 30.10.2026). "Dodaj vježbu": a combobox over the library since 23.11.2026 (the owner: "start typing in the exercise and then show only those"): typing filters its list as it goes, a row kept when every word typed is in its name or its tags, folded (case, č ć → c, đ → d, š → s, ž → z, any other mark dropped: "cuc" finds "Čučanj"; `qmtFold`, base.html), the names that start with it first, then a word of the name that does, then the rest, 60 rows at most ("… još N — nastavi tipkati"); a focus opens it, ↓ / ↑ move, Enter picks (never sends the form while it is open), Escape and Tab close it, a tap picks; typing after a pick clears it, and Dodaj with nothing picked sends nothing ("Odaberi vježbu s popisa." under the input). The library's select (name · tags) stays in the form, hidden: it carries the value posted and is the no-JS picker, `required` there. Then a Dio select opening on Glavni dio A (its four options, a row's Dio's too: Zagrijavanje, Glavni dio A, Glavni dio B, Istezanje; the part `?dodaj=` names since 25.11.2026), and since 25.11.2026 the numbers, all optional, Serije, Ponavljanja, Sekunde, Kilaža (kg) (`.add-nums`, the row form's grid), so a row is complete in one step (`db.add_day_item` takes them: a refused number adds nothing, "Neispravan broj." in the card, the Dio and the exercise kept, `?vjezba=`); above them the library's **tag chips** (23.11.2026, the library's row, `_tagbar.html`; hidden without JS, the select the picker there): a tap toggles its word in the combobox's input and leaves the focus there, so the list opens filtered (under the input, never over the chips: a second chip stays a tap away; it lies over what follows: a second chip after it closes); a pick puts the name in the input and the chips let go; then Dodaj, "Nova vježba →" (`natrag=` this editor; back with it chosen, `?vjezba=`, its name in the input). After an add (25.11.2026; until then back at its row) the page comes back to the add card, `?dodaj=<the part>&ok=…#dodaj`, its Dio as it was, its picker focused (at the load, after the browser's move to `#dodaj`, which takes a focus given before it), the card saying what went where, "Dodano u Glavni dio A: Sklekovi." (the add's word in the card, the page's top none), so several go in one after another. "Obriši trening" at the bottom (asks first; its intro video's file goes with it) |
| `/treninzi/vjezbe` | trainer/owner | **"Vježbe"** (Admin ▾'s item after Upitnik, 30.10.2026; its pages light Admin ▾, not the Online treninzi tab): the library of exercises, every one a row in the Croatian alphabet's order (`models.alpha_key`: Č after C, before D), the whole row a link: its name, its tags as chips, "video ✓" (green) or "bez videa", "u N programa" ("u 1 programu", "ni u jednom programu"); a search that **filters as it is typed** since 23.11.2026 (the owner: "I want this to be in real time i.e. when I search the dropdown changes"): a row stays when every word typed is in its name or its tags, whatever its case and the Croatian letters' marks (`models.matches` over `models.fold`: "cuc" and "ČUČ" find "Čučanj", "kod kuce" the tag "kod kuće", "hinge bucica" not "… s girjom - girja"; one table with base.html's `qmtFold`, which the day editor's "Dodaj vježbu" and an exercise's swaps filter fold with; blank shows all), the alphabet's order kept. Every row is on the page, `?q=` too (the server's `hidden` on the ones it drops, each row's `data-find` "name · tags" for the script); the page's script hides the rest at each key, says "2 od 4 · prikaži sve" while the box holds text (its link clears the box in place), "Nijedna vježba ne odgovara traženju „…”." when nothing is left, and keeps the address (`history.replaceState`: `?q=…`, the bare page when emptied), so a reload, a share or Back shows the same list; "Traži" goes and Enter does nothing, and the box is `autocomplete="off"` (the browser's own past entries hung over the list). Without JS the form submits `?q=` as before. **Tag chips** under the search (23.11.2026, the owner: "a search helper where we can search the items used in the exercise like for example 'girja' and then show all exercises with 'girja' in the dropdown"; the day editor's "Dodaj vježbu" has the same row): `.tagbar`, `_tagbar.html`, a chip per tag at least two exercises carry (`app._tag_chips` over `db.tag_counts`: counted folded, "TRX" and "trx" one tag, each in its most frequent spelling, the most used first; a tag one exercise carries is no chip: prod's typos), the first 12 and "još N" for the rest; a tap toggles its word in the box (not pressed: added after the box's words, "hinge girja", the every-word rule narrowing; pressed: its words taken out; a two-word tag as its two words), then the list filters as for a key (the address too), the focus kept on the chip (no phone keyboard over the list); the chips follow the box (`aria-pressed` while every word of the tag is a word of the box: typed, the ✕, "prikaži sve"). Without JS a `<noscript>` row of links to `?q=<tag>`, every chip shown, the one that is the whole `?q=` pressed (`aria-current`) and linking back to the whole list; "+ Nova vježba"; empty, "Još nema vježbi." with the button |
| `/treninzi/vjezbe/nova`, `/treninzi/vjezbe/{id}` | trainer/owner | An exercise's one form page (the `/admin` pages' look): Naziv, Upute, Što je jedno ponavljanje, Oznake (odvoji zarezom), **Zamjene za ovu vježbu** ("Slične vježbe" until 4.11.2026, when a swap got a direction; its hint "Polaznik smije odraditi označene vježbe umjesto ove. Da ova vježba zamijeni neku drugu, označi je na stranici te vježbe.": every other exercise a checkbox row, a tick a swap this one → that one, the ticked ones first, a filter box the script shows; a ticked row whose reverse row exists too (a mutual pair) carries a muted "u oba smjera" after its tags, text, not a control, an unticked row none; under the list, when it stands in for any, "Zamjena je za: A, B.", each name a `.tlink` to that exercise's page, where that direction is ticked), one POST for all of it (a name taken whatever its case comes back as the page, what was typed kept: "Vježba s tim imenom već postoji."). An existing one's lead says where it is ("U 2 programa: …"; a programme with a razina by its title and the razina, "Booty build (napredna razina)", since 30.10.2026: three live programmes share that title, one per razina, `db.program_name`), then **Video**: none, a file input "Video (mp4, mov ili webm, do 95 MB)" (`VIDEO_MAX_MB`) and the recording hint (upright, 10–30 s, one rep; iPhone's "Najkompatibilnije", or Chrome on Android and Windows cannot play it); one, the clip (`<video controls playsinline muted loop preload="metadata">`), "Zamijeni video" and "Ukloni video" (asks first). `POST …/video` (multipart: mp4 / mov / webm by extension AND by their first bytes, at most `VIDEO_MAX_MB`; the new file stored, the row then names it, the old file deleted) and `…/video/ukloni`. "Obriši vježbu" at the bottom (`…/obrisi`), asking first ("Obrisati vježbu?", "„Plank” se briše iz baze vježbi, s uputama i videom."; for one a programme holds, since 4.11.2026, "„Plank” se briše iz baze vježbi, s uputama i videom, i izlazi iz svakog treninga koji je drži (u N programa: A, B, C …). Treninzi ostaju bez nje; odrađeni treninzi u kartonima zadrže njezino ime.", the programmes named as the lead names them, three, then " …"; cta "Obriši vježbu"): it goes whatever holds it (the owner, 4.11.2026: "allow Amir to delete exercises even if they are part of some training and that the programme/training stays but it will just be without that exercise"), leaving every training (day) that held it, the trainings staying, one emptied too, and the library says "Vježba je obrisana i maknuta iz N treninga." (N the days; "Vježba je obrisana." when none held it). Until then one a programme held was refused |
| `/prehrana` | public | MojiMakrosi link (`/nutricionizam` 301s here); every text of it a slot since 25.11.2026 (`prehrana.*`: its two paragraphs split at their bold words) |
| `/profil` | any | Basic info form (from 23.11.2026 with "Visina (cm)", which moved to the karton on 26.11.2026, the owner's note: "visinu maknut iz profila u karton": the form has no height, `POST /profil` reads none, and a save keeps the stored one; its slot `profil.form.height` left the registry); since 27.11.2026 **"Spol (neobavezno)"** after "Datum rođenja" (build 5 of `roadmap/2026-11-26-gym-training-plan.md`, `users.sex`: a native select `name="sex"`, "Ne želim navesti" then Žensko / Muško, `models.SEXES`, the stored one selected; under it the hint "Da ti se aplikacija obraća u pravom rodu: „bio” ili „bila”, ne „bio/la”."; three slots, `profil.form.sex` and `.sex_none` required, `.sex_hint` optional, the none option's words edited on /tekstovi; `POST /profil` reads it off the form itself (FastAPI takes an emptied field for one not sent), `db.read_sex`: "" clears it, anything but f / m "Neispravan spol." and nothing saved, a form that posts none keeps the stored one; staff acting as the member set his; asked nowhere else, never required; the app's grammar alone reads it, the copy convention's "The slash forms"; where the form is narrow, a phone, the date, "Spol" and the phone a row each and the names side by side, a container query on the form: in a column of two its select cut "Ne želim navesti"); `#p-phone`, its phone field, takes the focus when the address names it (the phone reminder's "Upiši broj", 26.11.2026); under it the **Račun** card (the email as plain text, "Registriran/a od …"; back 20.10.2026); a client's link to `/moja-clanarina` (plans, uplate and računi moved there 18.10.2026). Every text a slot since 25.11.2026 (`profil.*`) |
| `/login`, `/signup`, `/forgot`, `/reset`, the sent-link page | guest | Their texts and base.html's login window's are slots since 25.11.2026 (`auth.*`; the words a page and the window share one slot); the dev server's "Link (dev)" line stays code |
| `/tekstovi` | trainer/owner | **"Tekstovi"** (25.11.2026; Admin ▾'s item after Vježbe, the drawer's Admin section too; `_require_trainer`, it lights Admin ▾): every plain slot of the app on one page, the ones only a member or a guest sees among them. The /admin pages' look, a 720px column: the lead, a search that filters as it is typed (the library's way: `qmtFold`, every word typed in a row's label or its text as it is now; "12 od 543 · prikaži sve"; "Nijedan tekst ne odgovara traženju „…”."; `?q=` follows; hidden without JS, the whole list then), then a section per page in the nav's order (`copy.TEXT_PAGES`: Početna, Raspored, Karton, Online treninzi, Trening (izvođenje), Trening u dvorani, Moja članarina, Prehrana, Upitnik, Vodič, Profil, Prijava i registracija, Aplikacija), its h2 with "Otvori stranicu →" where staff open the page, "Liste, tablice i kartice uređuju se na samoj stranici." under the landing's, the upitnik's and the guide's, a card of its areas (the karton panel's small captions), each row its label (muted .82rem) over its text, which edit mode edits as anywhere; an emptied one reads "(prazno)" outside edit mode. Opens in normal mode, the ✎ pill on it |
| `/kao` | trainer/owner | **"Gledaj kao član"** ("… člana" until the same day's correction, the owner: "the grammatically correct term should be 'otvori kao član' not 'člana'"; 26.11.2026; Admin ▾'s first item, the drawer's Admin section too; `_require_trainer`, it lights Admin ▾, its item current; the owner: "What if we have a user selection somewhere in the app for the admins much higher in the hierarchy and then Amir can look at the app just like the user sees the app and he can do everything the user does in the same way?"; Architecture, "Staff act as a member"): the /admin pages' look, a 720px column, its lead "Otvori aplikaciju kao član: vidiš što on vidi i radiš što on može. Sve što ovako promijeniš bilježi se."; every member (no trainer, not the owner) in the alphabet's order (`models.alpha_key` on his full name, the email for one with none), a row each: the name in 700, the email muted, his running plans small and muted (`PLAN_LABELS` in the plans' order, joined by " · "; none: "bez članarine"), "Otvori →" (`.act`, amber since build 4, `.act-kao`; a form, `POST /kao/{id}`). The list is `app._kao_members`, the Karton tab's too (build 4; since 27.11.2026 its search, which opens a member's karton). A search that filters as it is typed (/tekstovi's way: `qmtFold`, every word typed in a row's name or email; "3 od 41 · prikaži sve"; "Nijedan član ne odgovara traženju „…”."; `?q=` followed; hidden without JS, the whole list then); none at all, "Još nema članova.". The owner's line under the lead, "Zapis svih radnji →" (`/kao/zapisi`). While acting it is refused as every staff page is: "Izađi" first |
| `POST /kao/{id}` | trainer/owner | Into a member's account, only a member's (a trainer's or the owner's: "U račun trenera ili vlasnika se ne ulazi.", back to /kao; none there 404): the session's `as_user_id` (him), `as_seen` (now), `as_back` (`natrag`, through `_safe_next`, /kao by default), landing on `kamo` (`_safe_next`; his `/karton` by default); the record's first row; it arms no osvrt prompt (a staff login's flag goes). `app._enter_member` is the entry itself (the Karton tab's `POST /kao` went through it too, from build 4 until 27.11.2026). The shortcuts, each a small form with its `natrag`, each amber since build 4 (`.act.act-kao`): a termin's roster's "Kao član →" at each booked member's row's end (none on staff's), landing on his gym training of that termin since 26.11.2026 (`kamo=/dvoranski/termin/<id>` since 27.11.2026, `/karton/termin/<id>/trening` until then, build 3: made for staff before its window too; a termin canceled or a booking gone says its sentence on his karton), the trainer's view of a member's karton's "Otvori kao član" (under the head line; that view stays as it was: it shows what a member never sees). /clanarine's "Kao član →" and "Karton →" went in build 4 (the owner: "I would remove the 'Karton ->' and the 'Kao član ->' buttons here"), and the Karton tab's form into the app, `POST /kao`, on 27.11.2026 (its field opens a member's karton since, `GET /karton/clan`: the karton's row; a `POST /kao` is 405 now, /kao a GET alone). Declared after `/kao/izlaz` and `/kao/zapisi` |
| `POST /kao/izlaz` | anyone | "Izađi" (the strip's): the three keys go, back to `as_back` (/kao by default, or when not acting). It always passes the page-identity check, as `/logout` does |
| `/kao/zapisi` | owner | **"Radnje u ime članova"** (the record, the owner's alone: "Only a record for me"; linked from /kao and from /korisnici's lead; the trainer never sees it, the member sees no mark): newest first, 100 a page (`?str=2`, "← Novije" / "Starije →", `.act`), one table: Vrijeme (Zagreb, "26.11.2026. 14:03:07"), Tko, Kao koga, Radnja (the method and the path, tabular), Status ("—" for none); empty, "Još nema zapisa."; up to 600px a row is three lines, the time, "who → as whom", the action and its status |
| `POST /copy/{key}` | trainer/owner | Saves one in-place-edited text (JSON); an emptied text is stored empty since 20.10.2026, except a number (a `required` slot: `price.<plan>.amount`, `addon.*`), whose default comes back; `reset=1` (Zadano) restores the default (a row's cell stays empty too). An announcement's field too, by its virtual key `aktualno.<id>.<field>`, and a gym card's, `dvorana.<id>.<field>`; a rows slot's cell by `index` + `part`, a row by `index` + `remove=1`, a new row by `add=1` |
| `POST /aktualno/nova`, `POST /aktualno/{id}/obrisi` | trainer/owner | Adds an announcement after the last (placeholder texts; at most 8) / deletes one with its photo. Plain forms from edit mode, back to `/#aktualno` |
| `POST /aktualno/{id}/pomak` | trainer/owner | ↑ / ↓ (29.10.2026): `smjer` = `gore` / `dolje` swaps the card with its neighbour in the editor's order (every card, the hidden too; `db.move_announcement`); at either end, for a card gone or any other `smjer`, nothing moves. A plain form from edit mode, back to `/#najava-<id>`, the card, in edit mode (the one-shot flag) |
| `POST /dvorana/nova`, `POST /dvorana/{id}/obrisi` | trainer/owner | The same for the gym's cards: adds one after the last (placeholder texts, no plans; at most 8) / deletes one. Plain forms from edit mode, back to `/#dvorana` |
| `/admin` | trainer | **"Termini"** (Admin ▾'s first item; the page's h1 and title since 26.10.2026): the weekly timetable as an **editable week grid** + one-off termini |
| `/clanarine` | trainer | **"Trenutne članarine"** (Admin ▾'s item; the page's h1 and title since 26.10.2026): the breakdown per client; record cash/card uplate per client per plan. The add form's `sessions` select (grupni's treninga a month) and `tier` select ("Paket (samo online)": the three QMove names, the cards' titles) show only for their plan (an inline script; without JS both show, and the route ignores the one that does not fit); an online row's `tier` select stands on the member's tier, so the next uplata can move him, and the flash names it ("Online trening (QMove PRO): uplata evidentirana — …", 20.10.2026). Each plan's row says what an uplata recorded now buys, under its button: "Uplata produljuje do 1.6. (vrijedi do 8.6.)" (`db.next_cycle`, 29.10.2026; the add form's "Uplata: od danas do …"), and the flash names the same dates ("… — sljedeća 1.6.2026. (vrijedi do 8.6.2026.)"); a lapsed plan whose grace week holds the client's termini says "3 termina na povjerenje — neplaćeno" there in amber (`db.trust_bookings`), gone once an uplata lands. Since 26.11.2026 (build 4) a member's card holds no button of its own: its "Karton →" and "Kao član →" went (the owner: "I would remove the 'Karton ->' and the 'Kao član ->' buttons here and only leave the 'Admin -> gledaj kao član option' as well as the 'Otvori kao član' amber button on the Karton tab"), and so did the line under the lead to the members' page, "Stranica koju vide članovi — … Moja članarina →" (18.10.2026–26.11.2026; the owner: "this is now obsolete": staff's nav has the Moja članarina tab since 26.10.2026) |
| `/korisnici`, `/statistika` | owner | Roster + trainer grants (its lead links the record of staff acting as members, `/kao/zapisi`, since 26.11.2026); uplate per plan per month. Admin ▾'s last two items, the owner's only |

Media (`data/uploads/`, gitignored) is served ONLY via the auth-gated `/media/{name}` (the exercises' clips and the days' intro videos: staff any, a client one whose exercise is in a day of a programme matched to him, or a target of one that is (the player shows a swapped exercise's clip, 30.10.2026; a swap has a direction since 4.11.2026, so not an exercise that only points at one of his), or whose day is one; since 26.11.2026 one of an exercise in one of his gym trainings, whatever his plans, `db.gym_clip`; and since 23.11.2026 a member's monthly photos from his karton, `napredak-<user id>-<YYYYMM>-<hex>.jpg`, and since 25.11.2026 his health documents, under his limitations (`nalaz-<user id>-<hex>.pdf|.jpg`) and of his "Tjelesna kompozicija" (`sastav-<user id>-<YYYYMMDD>-<hex>.pdf|.jpg`): the member whose file it is and staff, nobody else, whatever his plans (`db.file_owner`, `db.photo_owner` until then; 403 "Ovo nije tvoj sadržaj."), `Cache-Control: private` (the R2 307 too), typed by the stored name's extension (`application/pdf`, `image/jpeg`) with `X-Content-Type-Options: nosniff`, a PDF `Content-Disposition: inline` under its stored name (never the name the member typed), never `/slika`, never named in a flash or a log line) — except the announcements' images, public by nature, which `/slika/{name}` serves (only names an announcement holds, cached a year).

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
(`src/qmt/upitnik.py`) routes a client into a razina (pocetna/srednja/napredna).
Programmes are tagged with a razina and a type (`Program.goal`, "Tip programa":
`upitnik.GOALS`, cijelo/gornji/donji and, since 23.11.2026, core) and **matching IS the
access**, by razina alone since 23.11.2026 (the owner: "I want to allow the users to be
able to access all types of training. The questionnaire only determines the level of
fitness and the trainings are available for everybody."): a client sees every programme
of his razina, whatever its type, grouped by type (`db.programs_for_level`,
`db.client_can_view`; the programme pages, the player and `/media` follow; until then
the razina × cilj combo, which kept Amir's "Upper strong" (gornji), "Booty build" and
"Ski ready" (donji) from every client) — no per-client hand-outs exist. **A programme is
online or dvoranski since 24.11.2026** (the owner: "A training can be of online training
class or gym training class ('dvoranski' or 'online') and he would like to create
trainings which are only aimed for a gym training"; the owner was told the assumption
that a gym one is the trainer's alone, and may widen it later): `Program.venue`
(`models.VENUES`, "online" / "dvorana", a CHECK; migration `49a70497e58a` made every
programme there online), "Vrsta" on both programme forms until 27.11.2026; the matching
takes online programmes only (`db.programs_for_level`), and `db.client_can_view` is false
for a dvoranski one, so its pages, its player and its clips are 403 to every client. It is
the trainer's own plan for the gym: staff see and run it as any. **No new one since
27.11.2026** (build 3 of `roadmap/2026-11-27-dvoranski-treninzi-plan.md`; the owner: "I dont
like the fact that I need to go to 'Online treninzi' and create a new programme there which
is not applicable to gym trainings"): neither programme form asks "Vrsta" (a new programme
is online, an edited one keeps the stored kind, a posted `venue` ignored on both routes); the
dvoranski ones there stay staff's as they were, listed with their chip, edited (their days'
empty slots working) and deleted. A gym training starts from Amir's templates instead
(`/dvoranski/predlosci`, "The gym training", rule 9). **Nothing makes, fills or refills a
programme but Amir** (30.10.2026, the owner: "he should be able to create a training
with no exercises, if he does that its his fault, okay? No refilling either way please,
no default, everything modular so that he can change it."): no programme makes itself,
none gets default exercises, and a programme with no day, or a day with no exercise,
stays so for as long as he leaves it. A client is told what is not there yet: a
razina with no programme "Programi za tvoju razinu još se pripremaju.", a
programme with no day "Program još nema treninga.", a day with no exercise "Trening još
nema vježbi.". (Until then the nine (razina × cilj) slots made themselves with default
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
programme's days' items point at it (`exercise_id`, CASCADE since 4.11.2026, migration
`45c543c860f3`; the owner: "allow Amir to delete exercises even if they are part of some
training and that the programme/training stays but it will just be without that exercise
and allow that there is a training with no exercises": an exercise deleted leaves every day
that held it, the days and the programmes stay, `db.delete_exercise`, and a pass keeps what
it saved of it; RESTRICT until then, when the delete named the programmes and refused).
Renamed or given a new clip, an exercise changes in every programme that holds it. **A programme is a list of days since
30.10.2026** (stage 2; the owner: "Dan 1, … Dan N with suggested days in the week but the
user can do them whenever he wants"; per exercise "sets × reps, or seconds, rest between
sets, a note. That is it for now"; a day has sections, "warm up and main"):
`models.ProgramDay` is its place (`position`, "Trening N", dense: `db.delete_day` closes
the gap; unique per programme, DEFERRABLE INITIALLY DEFERRED, so ↑ / ↓ swap two in one
commit), an optional `title` (`label`: "Trening 1 · Cijelo tijelo"), a suggested `weekday`
(0–6 or NULL: a suggestion, never a gate), an `intro` and an `intro_video` (a stored
clip, as an exercise's); `models.ProgramDayItem` is its exercise, its `section`
(`SECTIONS`: zagrijavanje, trening ("Glavni dio A"), trening_b ("Glavni dio B", 23.11.2026), trening_c ("Glavni dio C", 26.11.2026), istezanje; a CHECK), its `position` (unique across the
day, deferred; the display order is section by section, each in position order:
`ProgramDay.by_section`; a row moved to another section goes last in it), `sets`, `reps`
and `seconds` (either or both since 24.11.2026, the owner: "5 reps of 30 seconds of
plank"; one of the two until migration `30815c99e7d2` dropped the CHECK that said so),
`rest_seconds` (between sets),
`rest_after_seconds` (after the exercise, before the next one: the player's rest between
exercises, 30.10.2026, migration `4f9d6f7103ad`), a `note` and since 25.11.2026 a
planned weight, `kg` (migration `d0ed87d5c98f`, Numeric(5, 1), NULL for none; the
owner, for Amir's circuits: "the number of reps, the weight if applicable etc."; "Kilaža
(kg)" on the day editor's row and add forms); `dose` words it ("3
× 10", "3 × 30 s", "3 × 5 × 30 s" and with no sets "5 × 30 s" for reps and seconds,
"10 ponavljanja", "30 s", "3 serije", the weight after a middle dot, "3 × 10 · 20 kg"),
`rest_text` ("60 s") and
`rest_after_text` ("90 s") the rests. **A day reads "Trening 1 … Trening N" since
2.11.2026** (Amir's wish, via the owner: "Instead of calling the training parts Day 1, 2,
etc Amir would like them to be called Training 1, Training 2 and so on so that it is
clear."): `ProgramDay.label` says "Trening 1 · Cijelo tijelo", the programme around it
reads "program" wherever the pages said "trening" ("Uredi program", "+ Dodaj trening"),
the section `trening` reads "Glavni dio" (its key stays: a "Trening 1" with a section
called "Trening" was the confusion; since 23.11.2026 "Glavni dio A", and `trening_b`
"Glavni dio B", a second main part: the owner, for Amir, "an option to add 'glavni dio A'
and 'glavni dio B', so two separate main parts of a training", every item and pass already
there in A; migration `dc22ce1ed7e6`, the CHECK's four keys), and the passes' stored labels followed (migration
`b61e8d5bf1db`, "Dan N …" → "Trening N …"); the model, the routes, the ids and the files
still say day. The
spec's full training video is left out (a file over `VIDEO_MAX_MB` cannot pass
Cloudflare: a direct-to-R2 upload or a link, the owner's call). Every write to a
programme's days or their items locks the programme's row, then the day's
(`db._day_locked`). **A part of a day can be a circuit since 24.11.2026** (kružni trening;
the owner: "Amir wants a new type of training called 'kružni trening' where he has
sections of multiple exercises with no pause or a very short pause between them and then a
longer pause between these multiple sets"): `models.ProgramDayCircuit`
(`program_day_circuits`, migration `fc1840b0a981`; the day CASCADE, the primary key
(`day_id`, `section`), `rounds` 2–20 and `rest_seconds` 0–3600 or NULL, two CHECKs; the
section a `SECTIONS` key, which db.py checks) is a row per part done as a circuit, read as
`ProgramDay.circuits` (loaded with the day wherever its items are), `circuit(section)` and
`has_circuit` (a circuit on a part that holds an exercise: the day's "kružni trening"),
and said by `line` ("Kružno · 3 kruga · odmor između krugova 120 s"). Its exercises are
done back to back, each once per round, and since 25.11.2026 with no pause between two of
them (the owner's note to Amir: "Pauza ide na kraju kruga a između vježbi nikakva
pauza."; until then each one's own `rest_after_seconds`): the circuit's `rest_seconds`
is the one rest, after a round; an item's `sets`, `rest_seconds` and
`rest_after_seconds` do not apply there, stay stored and apply again once the circuit is
switched off (`round_dose` is its dose without its sets). Written by `db.set_circuit` /
`db.clear_circuit` under `_day_locked` ("Neispravan broj.", "Odaberi dio treninga."); the
player shows it one screen per round, every exercise of the part on it (`app._steps`:
a `Step` per round; until 25.11.2026 a step per exercise per round), and saves the round
whole (`db.save_circuit_round`; `db.save_round`, an exercise of a round at a time, went);
a day may mix normal and circuit parts. **A training's parts since 26.11.2026** (build 2
of `roadmap/2026-11-26-gym-training-plan.md`; the owner: "Lets have Glavni dio A, B and C
but lets also allow Amir to rename them."; migration `a7d3c5e9f214`): a third main part,
`trening_c` ("Glavni dio C", the CHECK's five keys; its downgrade puts C's items at the
end of B), and **a part's own name**, per day: `models.ProgramDayPart`
(`program_day_parts`: the day CASCADE, the primary key (`day_id`, `section`), `title`
String(60); the section a `SECTIONS` key, which db.py checks) is a row per renamed part,
read as `ProgramDay.parts` (loaded with the day as its circuits are), `part_title` and
`part_label(section)` (its name, else `SECTIONS`' default), which every place that names a
part of a day prints (the day page, the editor's captions and Dio options, the add card's
line, the player's list, a circuit round's h1 and title); written by `db.set_part_name`
under `_day_locked`, ON CONFLICT on the key (one line, `clean_name`; empty deletes the
row; past 60 "Najviše 60 znakova."); a pass keeps the part's key, never its name. **Empty
slots, in a dvoranski programme's days only** (the owner, for the gym trainings: "two
templates with no particular exercises connected to them … only slots to put them in.
Also no hard cap"): `program_day_items.exercise_id` is NULLable and `hint` (String(80),
'' for none) joins it; an item with no exercise is a slot (`ProgramDayItem.is_slot`; its
`exercise` relationship an outer join since, or the day would drop it), its numbers, rests
and note an item's. `ProgramDay.by_section` keeps every row; `exercise_items` /
`exercises_by_section` are the rows that hold an exercise, what the player walks
(`app._day_items`), "7 vježbi" counts and `has_circuit` asks; `slot_count` / `slots_text`
("3 prazna mjesta", `plural`'s forms) the rest. `db.add_day_slot` (the hint cleaned and
cut to 80, `HINT_MAX`; an online programme's day refused, "Prazna mjesta idu samo u
dvoranske programe.") and `db.fill_slot` (the exercise's row FOR KEY SHARE first, as
`add_day_item`; "Nepoznata vježba.", a row that is no slot "Mjesto je već popunjeno.";
an ordinary row after, its hint kept unshown) write them; `db.update_program` refuses to
make a programme online while it holds one ("Program ima prazna mjesta — popuni ih ili
obriši prije nego postane online.", its row FOR UPDATE: a client never meets a slot); not
in `db.day_item_ids`, nor in the staff table's count (`all_programs`). No cap on a part's
or a day's rows. A member's gym training took such a day as its template from that build's part B until 27.11.2026, when the gym's own templates came ("Its blocks", `/dvoranski/predlosci`): a dvoranski programme's days are offered to nobody since. **Swaps** (`exercise_alternatives`) **have a direction since
4.11.2026** (the owner: "We can now replace an exercise A with exercise B for example
and this is commutative meaning that I can always replace B with A. But Amir wants it
so that he can choose A -> B but not B -> A for some pairs"): a row (A, B) lets a client
doing A do B instead (usually a regression: one planned the jump squat may do the plain
squat, not the other way), and a mutual pair is two rows. An exercise's form sets its
own rows only (`db._set_alternatives`); it reads them as `Exercise.alternatives` (its
targets) and the rows pointing at it as `Exercise.stands_in_for`. No migration: the rows stay exactly as ticked, only their reading narrowed (until then a row
swapped either way). On prod Amir had ticked about 300 rows, every one from the page of the
harder or more equipped exercise pointing at what may replace it and not one pair both ways:
his ticks were the directions he wants, and the reverse rows would have been exactly the
swaps he asked to forbid. The swaps are what the player offers (below). **The player and the
history since 30.10.2026** (stage 3; the
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
"kg": 20.0}, …]` or a timed one's `[{"seconds": 30}, …]`, when; a re-save replaces it; a
circuit's exercise, since 24.11.2026, a set per round saved, each carrying its `round`,
`{"reps": 10, "kg": 20.0, "round": 2}`, sorted by round, a round saved again replacing
itself alone: since 25.11.2026 `db.save_circuit_round`, the round's every exercise in one
write, an exercise not done in it no set; `_checked_sets` takes a `round` 1–99 on any
shape and keeps it, and the history, the karton and the maxes read such a set as any
other; since 25.11.2026 an entry may carry the client's rating of the exercise,
`"effort": 7`, 1–10, none no key: the player's "Koliko je bilo teško?", a circuit's the
round's on every exercise it saved, the last rated round's standing; `models.effort_of`
reads it, `WorkoutLog.lines` ends the exercise's sets with "težina 7/10"),
`swaps` (a JSON object, item id → the similar exercise swapped in for this pass), then
the osvrt (`effort` 1–10, `feeling` a `FEELING_LABELS` key or NULL, `note`). **One pass in
progress per client and day**: the partial unique index `uq_workout_logs_open` (`user_id`,
`day_id` WHERE `finished_at IS NULL`), which `db.start_pass` inserts against with ON
CONFLICT DO NOTHING (two Kreni at once open one pass, tested); a day is done again as
often as wanted, a pass each. "Kreni" on a day opens it (or "Nastavi" the one in
progress), the player saves each exercise's set log into it (`db.save_sets`, the row
locked FOR UPDATE: two saves at once keep both entries, tested; a circuit's a round at a
time, `db.save_circuit_round`, under the same lock: two rounds at once keep both, tested), may swap an exercise
for one of its plan exercise's similar ones (`db.swap_exercise`: "Ta vježba nije među
sličnima." otherwise; what was saved stays as saved), and the finish screen's osvrt
closes it (`db.finish_pass`: "Neispravan osvrt." for napor outside 1–10 or an osjećaj
that is none; "Trening je već završen." twice); "Odbaci" deletes a pass in progress
(`db.drop_pass`; a finished one never). **A pass cannot hang** (31.10.2026; the owner:
"It shouldn't be possible to continue the training and have a hanging training of 9
hours"): a pass with no activity for `config.PASS_STALE_HOURS` (2;
`WorkoutLog.last_activity`, its start or its newest saved exercise's `at`) is stale
(`WorkoutLog.stale()`): it takes no more sets or swaps (`db.PASS_STALE`, "Trening je
predugo otvoren — završi ga ili ga odbaci."), every way back into it leads to its finish
screen, where it is finished or dropped, and its length is `active_seconds()` (to its
last save); the player and the finish screen ask before the client leaves (`#leaveDlg`,
finish or discard), the browser's own prompt the rest (iOS Safari has none: the rule is
the net). The day says "odrađen N×" (`db.day_state`; the
programme's cards `db.day_states`, one query), lists the last five passes with their sets
(`db.passes`), and the karton lists every finished pass beside the termini. The next
pass prefills each exercise's weights from the client's newest saved entry for that
exercise, any pass, any day (`db.last_sets` until 25.11.2026, `db.next_load` since),
and the plan's `kg` where he has none. **The load next time** (25.11.2026; the owner,
his note to Amir: "Ako je odradio sklek na prvom treningu i teška mu je, neka ta ista
vježba idući put bude ista ili mrvicu lakša ovisno kaj je recenzirao"; to Fable: "if
someone gave a feedback on a particular exercise of 7 or harder then the next appearance
of that particular exercise does not increase its difficulty but stays the same or if
its 9 or 10 out of 10 difficulty, then it gets slightly reduced by a certain
percentage"; Fable's numbers, put to the owner): `db.next_load(user_id, exercise_id,
skip)` (`next_loads` for several in one query, a round's screen) reads that newest entry
(`skip`, (pass, item) pairs: the screen's own entries, this pass's, are not last time)
and gives `NextLoad`: its day, its rating, its sets as done and `next`, each set as the
next time fills it (`db.next_set`, by the rating's band): no rating or 7–8, as he did
it; 6 or lower, a weighted set's kg × (1 + `PROGRESS_UP_PERCENT` %, 5) to the nearest
0.5 and at least 0.5 more (500 at most), a set with no weight its reps +
`PROGRESS_REPS_STEP` (1; 999 at most), a timed set the smallest multiple of 5 at or
past its seconds + `PROGRESS_SECONDS_STEP` (5; 3600 at most: 30 → 35, 27 → 35); 9 or 10,
the kg × (1 − `PROGRESS_DOWN_PERCENT` %, 10) to the nearest 0.5 and at least 0.5 less
(never below 0.5), the reps × (1 − 10 %) rounded down and at least one less (never below
1), the seconds × (1 − 10 %) rounded down to a multiple of 5 and at least 5 less (never
below 5: 30 → 25, 45 → 40, 10 → 5); never more than it was (5 → 5, 3 → 3). Seconds move
in steps of 5 since 26.11.2026 (the owner: "make sure this is rounded to a logical
number"; 30 s rated 9 gave 27 s until then); its `kind` ("kg", "reps": kg 0 in every set, "seconds") says what it fills
(`app._first_values`): after a rating a weighted exercise's KG (its reps the plan's), one
done with no weight its PON. (his reps, adjusted, in place of the plan's), a timed one
its SEK.; with no rating the prefill as it was (the last weights, the plan's reps and
seconds); never logged, the plan's numbers and its `kg`. The card says it
(`app._next_line`, "Prošli put (23.11.): 10 × 20 kg, težina 5 — malo više: 21 kg.", a
round's word after the dose, "malo više" / "isto" / "malo lakše"); the knobs are env
vars (`config.PROGRESS_*`, DEPLOY.md). The karton's gym log is untouched (the owner:
"online"). The finish screen's napor stays the whole training's. Staff may use the player; their passes are
theirs and show on the days and, since 24.11.2026, on their own karton's diary.
Migration `4c2e8a6f1d39` made the items typed by hand until then into library rows:
each body split (`split_body`: a first line that starts with a digit is a dose, the
item's note; the rest the exercise's instructions; prod's every body was "DOSE\nCUE"),
one exercise per name (trimmed, compared casefolded), the first cue its instructions,
the first video its clip; an image, a second clip and a cue not kept are printed to the
log, their files left in storage. Migration `7c3bf996c983` then made each programme's
items its first day (Trening 1), in section trening, no rest, each note parsed by its own `parse_dose`
("3 × 8 · 8 kg" → 3 sets, 8 reps, note "8 kg"; "3 × 20 s" → 3 × 20 seconds; "3 × 5 (s
koljena)" → note "s koljena"; a note that starts with no dose kept whole), and dropped
`program_items`. No programme has defaults since 30.10.2026 (above): the demo's nine
are the dev seed's own tables (`scripts/seed_demo.py`: `DEMO_EXERCISES`, library rows,
the cues only, one row per name; `DEMO_PROGRAMS`, each programme's Trening 1 in section
trening, each item its razina's dose; 60 s of rest, `DEMO_REST`: what the app's
defaults were, name for name and dose for dose), and the live site's are Amir's.
**What stays code**: the name rule (casefolded under the table's lock,
`_EXERCISES_LOCK`, which every write to an exercise takes first since 4.11.2026, a deletion
then the row FOR UPDATE and the programmes that hold it in id order, a save or a clip the
row: the dev and test databases' C locale folds ASCII only, so the
`lower(name)` index alone would let "Čučanj" and "čučanj" both in), the alphabet's order
(`alpha_key`), the clip's formats and cap (`app._save_video`: mp4 / mov / webm by
extension and by their first bytes, ISO base media's `ftyp` or WebM's EBML,
`config.VIDEO_MAX_MB`, default 95: Cloudflare's free plan refuses a body over 100 MB
with its own page, so 95 leaves the multipart room; no transcoding; a stored file is
named by the caller's prefix, `vjezba-<id>-…` or `dan-<id>-…`), a day item's numbers
(`db.ITEM_LIMITS`: sets 1–99, reps 1–999, seconds 1–3600, either rest 0–3600, since
25.11.2026 the planned weight 0.5–500 in steps of 0.5, `db.read_item_kg`, a note
up to 500) and the dose's words (`ProgramDayItem.dose`, `models.plural`'s Croatian forms);
since 30.10.2026 a logged set's numbers (`db.SET_LIMITS`: reps 0–999, kg 0–500 in steps
of 0.5, "2,5" or "2.5", seconds 0–3600; at most `db.MAX_SETS`, 20 since 26.11.2026 (12 until then: a circuit of 20 rounds, a set a round, now fits); a row with every
field empty dropped, an empty field beside a number 0; `db.read_sets`, checked again by
`save_sets`) and since 24.11.2026 its three shapes (`db.SET_SHAPES`, by the plan's item:
`db.set_fields`): reps and kg for an item that asks reps or no number, seconds alone for
one that asks seconds, reps and seconds for one that asks both (stored `{"reps": 5,
"seconds": 30}`, no weight; the karton's log is reps and kg only, and the maxes never
count a set that holds seconds), their words (`models.set_text`: "10 × 20 kg", "10" with
no weight, "30 s", "5 × 30 s";
`kg_text` "2,5"; `duration_text` "38 min", "1 h 05 min"), since 25.11.2026 an exercise's
rating (`db.read_effort`, `db.EFFORT_LIMITS` 1–10, "Neispravan broj." otherwise) and the
load next time's rule (`db.next_set`, its bands and bounds; the percentages and steps
the env's), the one-pass-in-progress index
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
the difficulty level of the trainings"): every v2 response's `goal` is `cijelo`
(`upitnik.GOAL`), which gates nothing since 23.11.2026: a client gets every programme of
his level, whatever its type (above); q1–q4 are stored for the later routing by
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
counts as filled, and its level still routes (its goal no longer does, since 23.11.2026:
the karton keeps its goal's pill, its ramp line "… prate ovu razinu." as a new row's),
until the client fills the new one.

**Staff act as a member** (26.11.2026, "Gledaj kao član"; the owner: "Amir can look
at the app just like the user sees the app and he can do everything the user does in
the same way", "so that nothing is lost in the communication or display between him and
the user"). While a trainer or the owner is "in" a member's account (an account that is
neither; `/kao` and `POST /kao/{id}`, through `app._enter_member`, as the Karton tab's
`POST /kao` was from build 4 until 27.11.2026), `current_user(request)` IS that member, so every
page and route behaves exactly as for him: his plans and gates (no plan no booking, the
paket, the 4 h cutoff, the window), his karton's forms (Amir's document on "Tjelesna
kompozicija" among them), every `_require_trainer` / `_require_owner` route refused as
for any member (no Admin ▾, no ✎ pill). The staff member is the actor beside him
(`request.state.actor`, the pair as `request.state.acting`; `app._acting` / `_actor`). The session holds it: `as_user_id`,
`as_seen` (the last request's time), `as_back` (where "Izađi" returns); a new login
drops them, `/logout` clears everything. **The strip** (`.kao-bar`, base.html) over every
page while acting, the one-task pages and the error page too: sticky above the topbar's
pill (which sits under it), the karton's amber, one line, "Gledaš kao: **Ivan Horvat**"
(an ellipsis when long; the name and the email in its title) and "Izađi" (`POST
/kao/izlaz`); staff's own chrome, fixed words. No install banner while acting (it is
about the device); the phone reminder shows (it is about the member). **It ends** at
"Izađi", at logout, and after `config.ACT_AS_IDLE_MINUTES` (30) with no request, when
the first request after it, GET or POST, runs NOTHING: the three keys go and it is a
redirect to `/kao?error=Pregled kao član je istekao — odaberi člana ponovno.` (a form
left open on the member's karton must never save into the staff member's own); a logout
still logs out. The same when the member is gone or has become staff; an actor who is
no longer staff goes to `/`. **A write goes only to the identity its page was drawn
for**: a page drawn while acting carries `<body data-kao="<id>">`, and its script adds
`?kao=<id>` to every form that posts as it is sent (a button, `requestSubmit`, or
`.submit()`, patched) and `X-QMT-Kao` to every same-origin fetch that is no GET. The
check runs before every route (`app._acting_guard`, a pure ASGI middleware added before
`SessionMiddleware`, so inside it, with the session; the static files, `/slika`, `/sw.js`
and `/healthz` aside): acting and the marker absent or another member's → nothing runs,
`/karton?error=Stranica je bila otvorena prije ulaska u pregled kao član — ništa nije
spremljeno.`; not acting and a marker present → nothing runs, `/kao?error=Pregled kao
član je završen — ništa nije spremljeno.`; `POST /kao/izlaz` and `/logout` always pass
(acting therefore needs JavaScript; a member's own no-JS forms carry no marker and are
untouched). **Closed while acting**: the three `/placanje` routes (`/moja-clanarina?
error=Plaćanje karticom pokreće član sam.`) and `POST /upitnik` (`/upitnik?od=1&error=
Upitnik ispunjava član sam — privola mora biti njegova.`). **The record**
(`models.ActingLog`, `acting_log`, migration `5e8c1a3f7b92`): a row for the entry and for
every write that runs while acting (the exit and a logout too; none for a GET, none for
one refused before it ran): when, the actor and the member (SET NULL, their names kept),
the method, the path (no query), the response's status (NULL when the app failed);
writing it never fails the request (`app._record_acting`). The owner reads it on
`/kao/zapisi`; the trainer never does, the member sees no mark. Statistics, reminders
and emails are untouched. **Where staff open a member's app** (26.11.2026, build 4 of
`roadmap/2026-11-26-gym-training-plan.md`; the owner: "I would remove the 'Karton ->' and
the 'Kao član ->' buttons here and only leave the 'Admin -> gledaj kao član option' as
well as the 'Otvori kao član' amber button on the Karton tab of the Admin and Trainer with
a search bar where a user can be searched. The button to open as another user should also
be in amber."): Admin ▾ → Gledaj kao član (`/kao`), a termin's roster's "Kao član →" and
the trainer's view's "Otvori kao član"; none on /clanarine, and since 27.11.2026 none on
the Karton tab (the owner: "when a user is pressed, that user's Karton is opened, not the
whole app as his view"): its field opens the member's karton, the trainer's view (the
karton's row), and its form into the app (`POST /kao`) and solid amber button
(`.btn-kao`) went. Every one is amber (base.html: `.act-kao`, the karton's tint, `--warn`
on `--warn-soft`, on /kao's rows, the roster's and the view's: amber = someone else's
account); "Izađi" as it was. With "Karton →" gone the trainer's read-only view had no link
staff reached but Korisnici's (the owner's) until the Karton tab's search (27.11.2026),
and it alone showed the upitnik's "Zahtijeva pregled", the pain flag and every answer: so
on a member's karton while staff act as him (`actor`) the upitnik block prints those three
as the view does, each group under "Vidi samo trener" (the karton's row).

**The gym training** (26.11.2026, build 3 of `roadmap/2026-11-26-gym-training-plan.md`, part A; the owner:
"I would remove the 'dodaj trening' and automatically add the training with its title already after a user
booked it and he can already edit it 4 hours before the training up until the next day. Amir can also edit
it later." … "Everyone does his own type of training. Amir wont prepare gym trainings ahead of time, but
live."; since 27.11.2026 a row of blocks, below). A member's training in the gym is a record of its own,
not the online days and passes: `models.GymTraining` (`gym_trainings`, migration `c4e1b7f9a2d6`: the member
CASCADE; the termin SET NULL, none for a training outside a termin; `title` and `starts_at` the termin's
when made, snapshots, '' and NULL outside one; `held_on` its Zagreb date or the date picked; the osvrt
`effort` / `feeling` / `note`; `finished_at` its first save; the partial unique index
`uq_gym_trainings_user_session` on (`user_id`, `session_id`) WHERE `session_id IS NOT NULL`), its blocks
`models.GymTrainingBlock` (`gym_training_blocks`, migration `9b4e2d7f1c58`: the training CASCADE;
`position` unique in the training, DEFERRABLE INITIALLY DEFERRED; `kind` 'stanica' or 'kruzni'
(`GYM_BLOCK_KINDS`); a Kružni set's `rounds`, its Krug, 1–20, and `rest_seconds`, the pause after a Krug,
0–3600 or NULL; `effort`, the block's rating, 1–10 or NULL, a Stanica's and a Kružni set's alike; four
CHECKs) and their items `models.GymTrainingItem` (`gym_training_items`: the block CASCADE, `block_id`, and
the training's `training_id` kept beside it, which the history, the maxes and `/media` read; `position`
unique in its block, deferred; `exercise_id` SET NULL beside `exercise_name`, the name when chosen, so an
exercise deleted from the library stays by name, `gone`; an item with neither is empty, `is_slot`, its
`hint` (a converted slot's word) starting its picker; what was asked, `sets`, `reps`, `seconds`, `kg`,
`rest_seconds` (a Stanica's pause after a set), `note` (its comment), each NULL or '' for none within
`db.ITEM_LIMITS`; what was done, `done`, a JSON list of the saved sets in a pass's entry's shapes under
`db._checked_sets`' rules, a Kružni set's each carrying its `round`; `done_at` its first save's time, kept
while a set stays saved: the page's clock runs from the training's earliest, `first_tick`). A Stanica holds
exactly one item, a Kružni set its rows. Its rules, db.py's: **1. Whose and when**: a training is its
member's alone (every function matches its id AND its member; another's 404); a termin's is his to write
from `config.GYM_OPENS_HOURS` (4) before the termin until the end of the day after it (`db.gym_window`: the
midnight two days after its Zagreb date), a training outside a termin (or let go of its termin) always, and
staff acting as him (`app._actor`) at any time, before the window and after it: `db.gym_can_write(training,
now, staff)`, asked by every write, which takes the training's row FOR UPDATE first (`_gym_locked`, and a
block's write `_gym_block_locked`, the block read fresh under it; refused, `GYM_CLOSED`, nothing changed).
**2. Made lazily**: `db.gym_training_for(user, session, staff)`, INSERT … ON CONFLICT DO NOTHING on the
partial index (two opens at once make one row, tested), holding no block (its page offers the templates);
`NO_BOOKING`, `TERMIN_CANCELED`, and for a member `gym_opens_text()` / `GYM_SHUT`. **3. A cancelled booking
takes it along** (`db.cancel_booking`, the same transaction): the row, its blocks and items go when nothing
was done in it (no set saved, no osvrt: `GymTraining.has_record`); one that holds a record stays,
let go of its termin (`session_id` NULL), its title and start as they were, and reads on as a training
outside a termin. **4. A tick saves**: `db.save_gym_done(block, user, sets)` writes a Stanica's ticked rows
whole under the training's lock (two saves at once keep both stations', tested); the rating is the block's
own write (rule 13). **5. No load next time**: a Stanica's rows start from what was asked, nothing else, a
Krug's from what that Krug saved, else what the Krug before did, else what was asked; `db.next_load` reads
the online passes alone, and the rating is stored and printed only ("težina 8/10"). **6. What counts
where**: its saved sets count for "Povijest vježbe" and "Procijenjeni maksimumi" at once, no osvrt needed
(`db._logged_sets`, block by block in the page's order: source "dvorana", where its title and time,
"Grupni trening · 18:00", or "Trening izvan termina"; an exercise gone from the library under its name,
`db.gone_key`, a negative key the history's `?vjezba=` takes). **7.** `/media` shows a member the clip of an
exercise in one of his trainings, whatever his plans (`db.gym_clip`). **8.** The login's prompt
(`db.pending_feedback`) owes a termin only while its training's window is open, once it has ended, until
its osvrt is saved (or a `TrainingLog` holds it); a first page after the login on `/karton` or `/dvoranski` counts as answered. Until
26.11.2026 the karton's plain osvrt form and its exercise log (23.11.2026) wrote `TrainingLog` rows; both
went, and the rows already there stay as they were: listed, their napor, osjećaj and komentar edited,
deleted.

**Its blocks** (27.11.2026, build 1 of `roadmap/2026-11-27-dvoranski-treninzi-plan.md`; the owner: "A gym
training consists of 'Stanica' and 'Kružni set' where the 'Kružni set' consists of 4 of 'Krug' at default
which can be changed. Each 'Krug' is the set of same exercises, but the user can edit the number of reps
done after each 'Krug' during the pause."; "In the start, there would be two templates."). They replaced
part B of 26.11.2026, which went whole: the parts (`gym_training_parts`, `models.GymTrainingPart`, "Uredi
dio", `db.set_gym_part`, a part's own name), an item's `section` and `effort`, the templates taken from a
dvoranski programme's days ("Odaberi gotov trening", `db.gym_from_template`: no gym training reads a
programme since; a dvoranski programme is the trainer's own plan, as before), the slot's card and its fill
(`db.fill_gym_slot`), and the writes under `/karton/trening/…` (its three GETs 303 to `/dvoranski`).
Migration `9b4e2d7f1c58` converted every training there: its items in `SECTIONS`' order, then position; a
part that was a circuit became ONE Kružni set (its rounds, its rest, its rating the first its items held)
holding its items in their order; every other item, a slot too, a Stanica of its own (its rating the
item's); the part names let go. Its downgrade restores the old shape as far as it can be said (every
Stanica's item into Glavni dio A in order, the first Kružni set into B, a circuit part of its rounds and
rest, a second into C and any further one's items after it there, the ratings back on the items, the
template tables dropped); not the blocks' order across kinds, a Kružni set of one Krug as a circuit (the old
circuits had two at least), a third or later set's own rounds and rest, the part names, a rating on a block
that holds no exercise, the templates (its docstring says so).
Their rules, db.py's, each write under the training's row lock and rule 1: **9. Templates**
(`models.GymTemplate` / `models.GymTemplateBlock`, `gym_templates` / `gym_template_blocks`: a title of 80
characters and its place (unique, deferred), its blocks in their places, a Kružni set's `slots` (its empty
rows, 1–12), `rounds` (1–20) and `rest_seconds`, CHECKs; no exercise in one): the two the owner asked for,
"Stanični trening" (six Stanica) and "Kružni trening" (a Stanica, then a Kružni set of 4 rows, 4 Krug, no
pause), the migration's insert and `copy.GYM_TEMPLATES`, the code's own table (`db.reset_gym_templates`:
the dev seed's and the tests'), and since build 3 (27.11.2026; the owner: "Amir will create the third
template later and give it a name") staff's rows, made on `/dvoranski/predlosci`: `db.add_gym_template` (a
name, needed, one line, 80 characters at most: `TEMPLATE_NO_TITLE` "Upiši naziv predloška.",
`TEMPLATE_TITLE_TOO_LONG` "Najviše 80 znakova."; after the last, with no block; at most `GYM_MAX_TEMPLATES`
12, `TOO_MANY_TEMPLATES` "Najviše 12 predložaka."), `rename_gym_template`, `move_gym_template` (↑ / ↓: two
places trade in one commit), `delete_gym_template` (its blocks with it, the places after it closing up:
dense, 1 … n), and the blocks' `add_gym_template_block` (a Stanica, or a Kružni set of `GYM_FIRST_ROWS` rows
and `GYM_FIRST_ROUNDS` Krug, no pause; at most `GYM_MAX_BLOCKS`, a training's cap and its sentence),
`set_gym_template_block` (a Kružni set's rows 1–12, Krug 1–20, pause 0–3600 or none; `BAD_NUMBER`),
`move_gym_template_block` and `delete_gym_template_block` (the places closing up); every one takes the
`gym_templates` table's lock first (`_TEMPLATES_LOCK`, SHARE ROW EXCLUSIVE, the announcements' way: two adds
at once take two places, two "+ Novi predložak" at eleven make twelve and refuse the other, tested; a plain
read never waits). A member's chooser offers the templates that hold a block (`db.gym_templates()`;
`all=True`, the list's, every one); `db.apply_gym_template` copies a template's blocks, empty, into a
training ONLY while no set is ticked in it, the blocks it had gone (`GYM_STARTED`, "Trening je već započet —
predložak se više ne može zamijeniti.", once one is; `NO_TEMPLATE`, "Odaberi predložak s popisa.", for one
that is none or, since build 3, holds no block; a template against a tick at once: one wins whole,
tested); applying never changes the template, and a training keeps its copy whatever happens to the
template after. **10. Blocks**: `db.add_gym_block` ("+ Stanica", its one empty item; "+ Kružni set",
`GYM_FIRST_ROWS` 4 empty rows, `GYM_FIRST_ROUNDS` 4 Krug, no pause) after the last, at any time, at most
`GYM_MAX_BLOCKS` 40 (`TOO_MANY_BLOCKS`, "Najviše 40 stanica i kružnih setova."; two at once take two
places, tested); `db.delete_gym_block`, any block at any time, its items and sets with it (the page asks
while it holds a set); `db.empty_gym_training`, every block (the osvrt stays). **11. A Stanica**
(`db.set_gym_station`, "Kreni" and "Uredi"'s Spremi, one write): its exercise (needed, `NO_EXERCISE`,
"Odaberi vježbu s popisa."; `UNKNOWN_EXERCISE`, "Nepoznata vježba.", its row FOR KEY SHARE before the
training's) and Serije, Ponavljanja, Opterećenje (kg), Pauza (s), Vrijeme (s), Komentar (500,
`COMMENT_TOO_LONG`), all optional within `ITEM_LIMITS` ("Neispravan broj."); the exercise changes only
while it holds no tick (`STATION_TICKED`, "Stanica već ima upisane serije — ukloni je pa dodaj novu."), its
numbers at any time; its tick rule 4; done when every planned set is ticked (with no Serije given, any).
**12. A Kružni set** (`db.save_gym_circuit`, its setup's and Uredi's one write, and the save "+ vježba" and a
row's ✕ make first): its rows, the page's own (`GYM_CHANGED` otherwise), each an exercise with Ponavljanja,
Opterećenje (kg) and Vrijeme (s), no Serije and no pause (none between the exercises of a Krug), a row's
exercise set, changed or cleared only while it holds no set, its numbers at any time, an empty row let be;
Krugova 1–20, never below a saved Krug; "Pauza nakon kruga (s)" 0–3600 or none. `db.add_gym_row` ("+
vježba", at most `GYM_MAX_ROWS` 12, `TOO_MANY_ROWS`) and `db.delete_gym_row` at any time; `db.set_gym_rounds`
("+ krug" / "− krug": 1–20, never taking away a saved Krug, `LAST_ROUND_SAVED`, "Zadnji krug je već upisan
— ne može se ukloniti."); a Krug, `db.save_gym_round`: every row that holds a library exercise
(`round_rows`) in one write, the page's own rows or `GYM_CHANGED`, each row done its set of the Krug
carrying `round` (`{"reps": 10, "kg": 16.0, "round": 2}`, sorted by round after the sets that carry none), a
Krug saved again replacing itself alone, a row left empty in it losing its set of that Krug, none typed
`NO_ROUND_EXERCISE`, "Upiši bar jednu vježbu."; two Krug at once keep both (tested). A Krug is saved when any
row holds a set of it (`rounds_saved`), the one on screen the first not saved (`current_round`), the set
done when every Krug is. A tick posted to a Kružni set is refused. **13. The rating** (`db.rate_gym_block`):
one per block, 1–10 or none, its own small write at any time (the page offers a Kružni set's once its last
Krug is saved); none per Krug anywhere. **14. The record**: a block that holds no exercise is in no record
(the diary's lines, "3 vježbe", the read-only page, the history, the maxes) and is never deleted for that:
on the page it stays, to be filled. A training holds anything as before, an exercise or its osvrt: blocks
alone hold nothing (a template applied and left). The diary's lines are `GymTraining.lines`
(`models.GymLine`): a Stanica's one line with the block's rating; a Kružni set's own line, "Kružni set · 4
kruga" with its rating, then its exercises', each what one round asks and what each Krug did.

| Path | Role |
|---|---|
| `src/qmt/config.py` | `.env`, `OWNER_EMAIL`/`ALLOWED_EMAILS`, booking knobs, `VIDEO_MAX_MB` (an exercise's clip, MB), `PASS_STALE_HOURS` (an online pass with no activity that long cannot be continued, 31.10.2026), the load next time's knobs (25.11.2026: `PROGRESS_UP_PERCENT` 5, `PROGRESS_DOWN_PERCENT` 10, `PROGRESS_REPS_STEP` 1, `PROGRESS_SECONDS_STEP` 5; `db.next_set`), `ACT_AS_IDLE_MINUTES` (26.11.2026: 30, the minutes with no request after which staff acting as a member leave the view, `app._acting_guard`), `GYM_OPENS_HOURS` (26.11.2026: 4, the hours before a termin from which its gym training is the member's to write, until the end of the day after it: `db.gym_window`), prod guards |
| `src/qmt/grammar.py` | The slash forms resolved by the reader's sex (27.11.2026, build 5): `gendered(text, sex)` ("f", "m"; anything else the very text), its rules and its tables of whole words (`FLEETING_LA` with the "šao" rule `FLEETING_SAO`, `JETI`, `FLEETING_A`); a module of its own, not copy.py's, so the mailer asks it without the registry and the models (the copy convention's "The slash forms") |
| `src/qmt/copy.py` | The texts a trainer/owner may edit in place (their slash forms read by `grammar.gendered`, since 27.11.2026; the profile's "Spol", `profil.form.sex*`): slot → default text, label; a 2000-character cap, no design limit since 16.10.2026; an emptied text stays empty since 20.10.2026 but a `required` slot's (the numbers, `price.<plan>.amount` / `.year_amount`, `addon.*`), whose default comes back; lists (`ListSlot`; the extra lines, `*.extra`, are lists that start empty), tables of rows (`RowsSlot`: the opening hours, `load_rows` / `dump_rows`, a new row's `ROW_BLANK`), on/off flags (`FlagSlot`) and photos (`ImageSlot`); the prices (`price.<plan>.*`, `addon.*`, defaults `REFERENCE_PRICES` / `YEARLY_PRICE` / `MOJIMAKROSI_ADDON`), every price the site shows, and since 23.11.2026 each price's bazna cijena (`BASE_OF`, price key → base key: `price.<plan>.base` / `.year_base`, `offer.online*.base` / `.year_base`, `addon.*.base`, and `price.base_label`; a gym card's `GYM_CARD_BASE_OF`); the `/moja-clanarina` cards' one text each (`cjenik.<plan>.text`, defaults `PLAN_TEXTS` + `PLAN_TEXT_END`); how an announcement's fields are edited (`ANNOUNCEMENT_SLOTS`, `ANNOUNCEMENT_COLUMNS`), a new card's placeholders (`ANNOUNCEMENT_BLANK`) and the seed's two examples (`ANNOUNCEMENT_EXAMPLES`); the same for a gym card (`GYM_CARD_SLOTS`, `GYM_CARD_COLUMNS`, `GYM_CARD_BLANK`, `GYM_CARD_EXAMPLES`); the upitnik's words around its questions (`upitnik.*`, the parts' headings `UPITNIK_PARTS`), and for its questions, rows since 26.10.2026: the gym owner's questions as they start (`UPITNIK_DEFAULT_QUESTIONS`: the fifteen, ids 1–15, and q16 / q17 asked after q14 / q15, the seed's; the migrations carry their own copies), a new question's placeholders (`UPITNIK_BLANK`), how a question's words are edited (`UPITNIK_QUESTION_SLOTS`: text, options, low, high) and where a row keeps them (`UPITNIK_QUESTION_COLUMNS`); the guide through the training (29.10.2026: `VODIC_SECTIONS`, the gym owner's eleven sections as they start, each the four slots `VODIC_PARTS` names, `vodic.<n>.h` / `.text` / `.points` / `.after`, and `vodic.title` / `vodic.cta`); the karton's texts (25.11.2026: `karton.<area>.<name>`, 126 since the same day's later build (its documents, the body form's hint, "Povijest vježbe" and its own area, `history`), area by area in the page's order, `KARTON_AREAS` their captions, `KARTON_PANEL` the editor's panel's grouping); every other member-facing text (25.11.2026: `raspored.*`, `treninzi.*`, `program.*`, `dan.*`, `player.*`, `kraj.*`, `leave.*`, `profil.*`, `auth.*`, `app.*`, `period.*`, `landing.*` and the rest of `clanarina.*` / `prehrana.*`, page by page in each page's order) and `TEXT_PAGES` (/tekstovi's grouping: every plain slot by page and area, from the keys' prefixes, `_TEXT_RULES`) |
| `src/qmt/models.py` | `User` (+profile fields; since 23.11.2026 `height_cm`, the karton's height, and `limitations`, the member's own text of his limitations and pains; since 27.11.2026 `sex`, "f" / "m" / NULL for not said, the profile's "Spol", for the grammar alone, the CHECK `ck_users_sex`, migration `3d9a6f2c8b51`; `SEXES`, Žensko / Muško), `Weight` (an entry of a member's "Tjelesna kompozicija" on a day, one a day: `uq_weights_user_day`; 23.11.2026, a weight alone until 25.11.2026: `kg` Numeric(5, 1) NULL since then, `file` the stored document or NULL, `file_name` its link's name, `ck_weights_kg_or_file` one or the other; `kg_text`), `LimitationFile` (25.11.2026: a document under a member's limitations, `file` the stored file's name, `name` what the list shows; `is_pdf`; ten a member, held by db.py), `ProgressPhoto` (a member's photo of a month, `month` its first, `image` the stored file's name, one a month: `uq_progress_photos_user_month`; 23.11.2026), `SessionTemplate`, `TrainingSession`, `Booking`, `Membership`, `Payment`, `OnboardingResponse`, `TrainingLog` (the osvrt of a gym termin, or with `session_id` NULL a training outside a termin, 23.11.2026; `sets` since the same day, the exercises logged, a JSON array of entries, the exercise's id, its name when logged, its sets `[{"reps", "kg"}]`, when: read through `set_items`, `lines()` (the karton's "Serije") and `exercise_count`), `Program`(level/goal/venue: online or dvorana since 24.11.2026, `VENUES`, a CHECK; `days`)/`ProgramDay` (a programme's day: its place, `title`, `weekday`, `intro`, `intro_video`; `label`, `by_section`; its position constraint deferred; since 24.11.2026 `circuits`, `circuit(section)`, `has_circuit`)/`ProgramDayItem` (a day's exercise, its key to it CASCADE since 4.11.2026: `section`, its place, `sets`, `reps` and / or `seconds` (both since 24.11.2026, no CHECK), `rest_seconds`, `rest_after_seconds` (30.10.2026), `note`, `kg` (25.11.2026, the planned weight, Numeric(5, 1) or NULL); `dose` ("3 × 5 × 30 s" for both; the weight after a middle dot, "3 × 10 · 20 kg"), `round_dose` (24.11.2026: without its sets, a circuit's round's; the weight too), `rest_text`, `rest_after_text`), `ProgramDayCircuit` (24.11.2026, kružni trening: a part of a day done as a circuit, (`day_id`, `section`) its key, `rounds` 2–20, `rest_seconds` after a round 0–3600 or NULL, two CHECKs, since 25.11.2026 the part's one rest: no pause between its exercises; `rounds_text`, `rest_text`, `line`), `ProgramDayPart` (26.11.2026: a part of a day with a name of its own, (`day_id`, `section`) its key, `title` String(60); `ProgramDay.parts`, `part_title`, `part_label`; and since the same day `ProgramDayItem.exercise_id` NULLable, `hint`, `is_slot`: a dvoranski day's empty slot; `ProgramDay.exercise_items`, `exercises_by_section`, `slot_count`, `slots_text`; `SECTIONS`' fifth key, `trening_c`), `Exercise` (the library of exercises: `alternatives`, the exercises a client may swap it for, its own rows of the `exercise_alternatives` table (a direction since 4.11.2026), and `stands_in_for`, those it may stand in for, the rows pointing at it; `tag_items`; `alpha_key`, the Croatian alphabet's order), `WorkoutLog` (a client's pass through a day, 30.10.2026: the snapshots, `done` / `swaps` JSON read through `done_items` / `swap_items`, `done_count`, `done_in` (how many of a day's items now it saved: the history's and the karton's count, 4.11.2026) / `done_text` ("2 vježbe", every entry: a day gone or holding no exercise now), `in_progress`, `elapsed_text`, `date`, `lines(order)` the history's "Serije" (since 25.11.2026 an exercise the client rated ending with "težina 8/10"; an entry's rating, `"effort"`, read by `effort_of`); `last_activity`, `stale()` and `active_seconds()` since 31.10.2026: no activity for `PASS_STALE_HOURS`, its length to its last save; one in progress per client and day, a partial unique index; `kg_text`, `set_text`, `duration_text` say its numbers), `SiteCopy`, `Announcement` (the landing's cards), `GymCard` (the gym's cards; `plan_keys`, `point_items`, `extra_items`; `base_price` / `base_year_price`, its own prices' bazna cijena, 23.11.2026), `UpitnikQuestion` (the upitnik's questions; `option_items`; its position constraint deferred, so ↑ / ↓ swap two in one commit; one row per role, a partial unique index); `PLAN_*`, `ONLINE_TIERS` / `ONLINE_TIER_SLOTS` (the online plan's QMove tiers and their cards), `FEELING_LABELS`, `SECTIONS` / `WEEKDAYS` (a day's sections in their order, its suggested weekday), `VENUES` (a programme's Vrsta, 24.11.2026: Online, Dvoranski; asked by no form since 27.11.2026), `plural` (a noun after its count, "2 vježbe"), `PAYMENT_METHODS`; `ActingLog` (26.11.2026, `acting_log`: the record of staff acting as a member, a row per entry and per write done as one: `at`, `actor_id` / `member_id` SET NULL with `actor_name` / `member_name` snapshots, `method`, `path`, `status` or NULL); `GymTraining` / `GymTrainingBlock` / `GymTrainingItem` (26.11.2026, build 3: a member's training in the gym and its exercises; since 27.11.2026 its blocks between them, migration `9b4e2d7f1c58`, Architecture's "The gym training": the training's `blocks`, `outside`, `items`, `exercise_items`, `record_blocks`, `station_number`, `stations_count`, `count_text`, `holds_anything`, `has_record`, `ticked`, `first_tick`, `osvrt_text`, `lines` (`GymLine`, a line of the diary's "Serije" and its `kind`); a block's `kind` (`GYM_BLOCK_KINDS`: Stanica, Kružni set), `circuit`, `item`, `exercise_rows`, `round_rows`, `holds_exercise`, `rounds_saved`, `current_round`, `started`, `done`, `mark`, `rounds_text`, `rest_text`, `rating_text`, `facts`, `done_text`, `round_line`, `lines`; an item's `dose` / `round_dose` / `rest_text` the day item's own, `asked`, `is_slot`, `gone`, `name`, `sets_of`, `done_sets`, `mark`, `round_set`, `line(circuit)`); `GymTemplate` / `GymTemplateBlock` (27.11.2026, `gym_templates` / `gym_template_blocks`: a template's title, its place and its blocks, a Kružni set's `slots`, `rounds` and `rest_seconds`; `facts`, the chooser's muted line and the list's; since build 3 staff's rows, `labelled`, each block with its name on the editor, "Stanica 2" / "Kružni set"); part B's `GymTrainingPart` (26.11.2026) went the next day |
| `src/qmt/db.py` | Queries + rules. **`book()` locks the session row FOR UPDATE** and re-counts inside the lock (tested); `read_sex` and `update_profile(…, sex=KEEP)` (27.11.2026, the profile's "Spol": "f", "m", None for not said, else `BAD_SEX` "Neispravan spol."; KEEP, a caller that names none, leaves the stored one); `add_announcement` locks the `announcements` table, so the cap of 8 (`MAX_ANNOUNCEMENTS`) holds when adds race (tested); `add_gym_card` the same for `gym_cards` (`MAX_GYM_CARDS`), and every structural write to `upitnik_questions` (add, move, a setting) takes that table's lock, so the cap of 40 (`MAX_UPITNIK_QUESTIONS`) holds and no role lands on two questions when editors race (tested); a question that comes with its own id (the seed's) moves the id sequence past it, never back; every write to an exercise (a new one, a save, its clip, and since 4.11.2026 its deletion) takes `exercises`' lock (`_EXERCISES_LOCK`) first, then the row (a deletion then the programmes that hold it, in id order), so a name is taken once, whatever its case, when saves race, and a save or a clip against a deletion never deadlocks (tested, each); `delete_exercise` returns the clip's name and how many days it left, `add_day_item` takes the exercise's row FOR KEY SHARE before the programme's (the same order) and an exercise deleted under it is not added (tested); every write to a programme's days or their items locks the programme's row, then the day's (`_day_locked`), so two "+ Dodaj trening" never take one number (tested); since 4.11.2026 `delete_exercise` deletes an exercise whatever holds it, under its row's lock and then the holding programmes' rows in their ids' order (two deletes at once never deadlock), returning its clip's name and the days it left, and `add_day_item` takes the exercise's row (FOR KEY SHARE) before the programme's, so an add and a delete of one exercise never deadlock (tested); the passes (30.10.2026): `start_pass` (ON CONFLICT DO NOTHING on the partial index: two Kreni at once open one pass, tested), `open_pass`, `get_pass`, `save_sets` / `swap_exercise` / `finish_pass` / `drop_pass` (each takes the pass's row FOR UPDATE: two saves at once keep both entries, tested; since 31.10.2026 `save_sets` and `swap_exercise` refuse a stale pass, `PASS_STALE`, and `finish_pass` stores `active_seconds`), `save_circuit_round` (25.11.2026, a circuit's round, in place of 24.11.2026's `save_round`, an exercise of a round at a time: every exercise of the round in one write, each one's set carrying its `round` into its entry, its other rounds kept, sorted by round; an exercise not done in it no set, and the set of that round it had gone; none done `NO_ROUND_EXERCISE`, "Upiši bar jednu vježbu."; save_sets' lock and refusals: two rounds at once keep both, tested), the rating (25.11.2026: `save_sets(…, effort=)` and `save_circuit_round(…, effort=)` write `"effort"` into the entry, `read_effort` reads the posted one, `EFFORT_LIMITS` 1–10, else "Neispravan broj."; a round's on every exercise it saved, an unrated round keeping theirs), `passes`, `last_sets`, `next_load` / `next_loads` (25.11.2026, the load next time: `NextLoad` from the newest entry of an exercise, `_newest_entries`, `skip` the screen's own; `next_set` a set by the rating's band, `config.PROGRESS_*`; `LOAD_WORDS` / `LOAD_SHORT` the card's words), `day_state` / `day_states`, `day_item_ids` (the items each day holds now: the karton's count, 4.11.2026, `day_sizes` until then), `read_sets` (a posted set log's rules; since 24.11.2026 it takes the item's fields, `set_fields`: one of `SET_SHAPES`, reps and kg, seconds, or reps and seconds; `_checked_sets` takes a set's `round`, `ROUND_LIMITS` 1–99, on any shape, and keeps it); `update_day_item` (an item's section, numbers and note; `ITEM_LIMITS`, `rest_after_seconds` among them since 30.10.2026, its argument after `rest_seconds`; reps and seconds together since 24.11.2026, `REPS_OR_SECONDS` gone; `sets` / `rest_seconds` given as `KEEP` stay as stored, a circuit part's row form's, 24.11.2026, and since 25.11.2026 `rest_after_seconds` too; `kg`, the planned weight, `read_item_kg` / `ITEM_LIMITS["kg"]` 0.5–500 in steps of 0.5, kept when not given); `add_day_item` (since 25.11.2026 with the numbers too, sets, reps, seconds, kg, a refused one adding nothing); `set_circuit` / `clear_circuit` (24.11.2026, kružni trening: a part of a day a circuit, `CIRCUIT_LIMITS` rounds 2–20 and a rest 0–3600 or none, or a normal one again, under `_day_locked`, the programme's `updated_at` moved; "Neispravan broj.", `NO_SECTION` "Odaberi dio treninga."); `set_part_name` (26.11.2026: a part's own name on its day, `PART_TITLE_MAX` 60, empty deletes the row, ON CONFLICT on its key: two renames at once leave one row, tested), `add_day_slot` / `fill_slot` / `clean_hint` (a dvoranski day's empty slot, `HINT_MAX` 80, `SLOTS_GYM_ONLY`, `SLOT_FILLED`), `update_day_item(…, hint=KEEP)`, `update_program` refusing online while a day holds a slot (`SLOTS_NOT_ONLINE`, the programme's row FOR UPDATE), and `day_item_ids` / `all_programs` / `exercises` counting the rows that hold an exercise; `program_name` ("Booty build (napredna razina)", the library's pages and the delete's confirm); `programs_for_level` (23.11.2026, `programs_for_combo` until then: a client's programmes, every online one of his razina, in `upitnik.GOALS`' order, then by title) and `client_can_view` (his razina alone; never a dvoranski programme, 24.11.2026); `create_program` / `update_program` take `venue` (online unless said / None keeps it); `tag_counts` (23.11.2026: every tag of the library with how many exercises carry it, counted folded, `models.fold`, each in its most frequent spelling, the most used first: the tag chips', `app._tag_chips`, a tag at least two carry); the karton's exercise log (23.11.2026): `read_log` (a karton form's exercise blocks, `ex_<n>` / `reps_<n>_<i>` / `kg_<n>_<i>`, → `TrainingLog.sets`' entries: a block with no set dropped, the refusals' sentences, the exercises looked up in one query and their names snapshotted, at most `MAX_LOG_EXERCISES`, 15), `read_day` (a training outside a termin's date: not in the future, not before `FIRST_DAY`, 2020-01-01), and `add_session_feedback` / `update_training_log` (`sets` replaces the log, None keeps it; `day` moves a training outside a termin only) / `add_training_log` taking `sets`, checked again where written (`_checked_log`); `estimated_maxes` (the karton's maxes, `Max`: every set of a client's gym logs and finished passes but one that holds seconds (24.11.2026), Epley's 1RM, `epley`, a single its weight, for a weight and 1–`EPLEY_MAX_REPS` reps, the best per exercise, ties the later day; a bodyweight exercise's most reps when it has no 1RM; to the nearest 0.5 kg, `_to_half`; named by the library now or the snapshot, the alphabet's order); the karton's body and photos (23.11.2026): `read_height` (`HEIGHT_LIMITS`, 100–250) and `update_profile(…, height_cm=)`, `read_weight` (`WEIGHT_LIMITS`, 20–300 in tenths, a comma or a point) / `set_weight` (since 25.11.2026 `set_weight(user_id, on, kg=None, file=None, file_name="")`: a mass, a document or both, neither `NO_MASS_NOR_FILE` "Upiši masu ili dodaj dokument."; one entry a day, a second save that day replaces what it gives and keeps what it does not, returning the document it replaced for its file to go, under the member's row lock, FOR NO KEY UPDATE: two saves at once leave one row, tested) / `weights` (newest first) / `delete_weight` (his own only; its document's name, "" for none, None for no such entry), `set_limitations` (`copy.clean`, `LIMITATIONS_MAX` 2000), the documents under them (25.11.2026): `limitation_files` (newest first), `add_limitation_file` (at most `MAX_LIMITATION_FILES`, 10, "Najviše 10 dokumenata.", under the member's row lock: uploads at once at nine make ten, tested), `delete_limitation_file` (his own only; its file's name), `doc_name` (a document's list name: the typed one, else the upload's own name without its path, cleaned, cut to `DOC_NAME_MAX` 80, else "Dokument"), `photo_months` / `read_month` (this month and the eleven before it), `photos` (newest month first), `set_photo` (one a month: returns the photo it replaced for its file to go; under the member's row lock, FOR NO KEY UPDATE, so two uploads for one month take turns and each replaced file is named to one caller, tested) / `delete_photo` (his own only; its file's name), `file_owner` (/media: a progress photo's, a limitation document's or a weight document's member; `photo_owner` until 25.11.2026); an exercise's history on the karton (25.11.2026): `logged_exercises` (`Logged`: every exercise a member has logged, its name now or its newest snapshot, `times` the trainings holding it, `last_on`; the alphabet's order) and `exercise_history` (`Done`: every time he did one, newest first, its day, source, where, sets as `set_text` says them), both over `_logged_sets`, the one reading of a member's sets that `estimated_maxes` goes over too; since 26.11.2026 `set_height` (the karton's height form, `read_height`'s rules, None clears it), `record_acting` / `acting_log` (the record of staff acting as a member, newest first, `ACTING_LOG_PAGE` 100 a page, and whether an older page has rows), `MAX_SETS` 20 (12 until then) and `next_set`'s seconds in steps of 5; the gym training (26.11.2026, build 3; its blocks since 27.11.2026): `gym_window` / `gym_window_open` / `gym_can_write` (rule 1), `gym_training_for` (rule 2), `add_gym_outside`, `gym_training` / `gym_trainings` (`_gym_query`: its blocks and their items loaded), `gym_open_termini` (27.11.2026, the tab's "Otvoreni treninzi": a member's booked termini whose window is open, not canceled, the soonest first), `_gym_locked` / `_gym_block_locked` (a block's write: the training's row, then the block read fresh), `save_gym_done` (rule 4, a Stanica's ticks; two at once keep both, tested), `empty_gym_training`, `delete_gym_training`, `set_gym_day`, `finish_gym_training`, `gym_clip` (rule 7), `gone_key`; the blocks (27.11.2026): `gym_templates` (since build 3 the chooser's, those that hold a block; `all=True` every one) / `reset_gym_templates` / `apply_gym_template` (rule 9, `NO_TEMPLATE`, a template with no block too since build 3, `GYM_STARTED`; a template against a tick, tested), Amir's templates (27.11.2026, build 3, rule 9; each under `_TEMPLATES_LOCK`): `gym_template`, `add_gym_template` (`GYM_MAX_TEMPLATES` 12, `TOO_MANY_TEMPLATES`, `TEMPLATE_NO_TITLE`, `TEMPLATE_TITLE_TOO_LONG`, `GYM_TEMPLATE_TITLE_MAX` 80; two at once at eleven, tested), `rename_gym_template`, `move_gym_template`, `delete_gym_template`, `add_gym_template_block` (two at once take two places, tested), `set_gym_template_block`, `move_gym_template_block`, `delete_gym_template_block` (`_dense`, `_swap`, `_template_blocks`), `add_gym_block` / `delete_gym_block` (rule 10, `GYM_MAX_BLOCKS` 40, `TOO_MANY_BLOCKS`; two adds at once, tested), `set_gym_station` (rule 11, `STATION_TICKED`, `COMMENT_TOO_LONG`), `save_gym_circuit` / `add_gym_row` / `delete_gym_row` / `set_gym_rounds` / `save_gym_round` (rule 12: `GYM_MAX_ROWS` 12, `TOO_MANY_ROWS`, `GYM_ROUNDS` 1–20, `GYM_FIRST_ROUNDS` / `GYM_FIRST_ROWS` 4, `LAST_ROUND_SAVED`, `GYM_CHANGED`; two Krug at once keep both, tested), `rate_gym_block` (rule 13); part B's `set_gym_part`, `gym_from_template`, `fill_gym_slot` and `add_gym_item` / `update_gym_item` / `move_gym_item` / `delete_gym_item` went with it; `cancel_booking` takes the training along (rule 3), `pending_feedback` asks its window (rule 8), `_logged_sets` reads its sets (rule 6); `add_session_feedback`, `add_training_log`, `read_log` and `MAX_LOG_EXERCISES` went, and `update_training_log` edits an old row's napor, osjećaj, komentar and date, its exercises read only |
| `src/qmt/upitnik.py` | What stays code of the upitnik, v2 (26.10.2026), over the live rows: `steps` (the rows → the screens, one per row with its condition as far as it can work, `void` when it cannot, `muted` under a hidden question; `Question`), `client_steps` (a client's: shown, unmuted, built from every row), `is_asked` / `meets` / `fits` / `asked_of` (branching, 27.10.2026), `read` (a posted form → the stored answers, or ValueError), the owner's `score` (exact fractions, half up) / `level_for`, `evaluate` (the two safety rules on top: `PAIN_HIGH`, `needs_review`; `PAIN_ASK` is the karton's pain flag), `settings` (a question's part, kind, scoring, role, shown and their rules, the editor's refusals), `condition` (Pita se's rules), the editor's `setting_line` / `condition_line` / `scoring_summary` / `blocked_moves` / `short` / `answer_choices`, the karton's `answer_rows` (every answer kept, a conditional one's depth, "(pitanje uklonjeno)"), `chips`, `pain_where`, `score_text` ("6,4 / 10"); `KINDS`, `SCORING`, `ROLES`; `GOAL` (every v2 response's, `cijelo`; it gates nothing since 23.11.2026); `LEVELS`, `GOALS` (the programmes' type, "Tip programa": cijelo, gornji, donji, and `core` since 23.11.2026; a client sees every type of his level, grouped in this order); `QUESTIONS_V1` / `MAX_SCORE_V1` / `answer_rows_v1`, frozen, to read an old row. No word of it: those are the rows' and the copy slots' |
| `src/qmt/auth.py` | bcrypt + signed email tokens (verify 24 h; reset 1 h, single-use). The hash's cost is the constant `BCRYPT_ROUNDS` (12, bcrypt's default), which no setting reaches; the test suite alone lowers it to 4 in its own process (`tests/conftest.py`'s `_cheap_password_hashes`, 27.11.2026: the whole suite went from 23.7 to 16.3 minutes), and `test_a_password_is_hashed_at_full_cost_outside_the_suite` holds the constant |
| `src/qmt/mailer.py` | Only Resend importer. Also `send_new_user_notice` → owner hears about each first verification. The reset email's "tražio/la" as the account's sex (`send_password_reset_email(…, sex)`, 27.11.2026, `grammar.gendered`); the verification email as it is |
| `src/qmt/reminders.py` | Email podsjetnici (pre-dospijeće + day-before termin), claim-idempotent via the `reminders` table; app lifespan ticks every 6 h, `scripts/send_reminders.py` forces a pass |
| `src/qmt/storage.py` | Media backend: local disk, or Cloudflare R2 when the four `R2_*` vars are set (then `/media` 307s to presigned URLs); `stream()` hands out a stored file's bytes, for `/slika`, which proxies the bytes so its public URL stays cacheable |
| `src/qmt/payments.py` | Stripe: Prices for /moja-clanarina's checkout tier picker and tier switch (cached), Checkout + portal sessions, signed webhook → `record_payment`. Tolerates both invoice shapes (pre/post 2025 API) |
| `src/qmt/web/app.py` | All routes. `current_user()` per route; the slash forms (27.11.2026): `_ctx`'s `rod` (whose sex a page reads as: the effective user's, on the trainer's view of a karton the member's), the filter `gendered` (`_gendered`) and a context-aware `copy_text` (`_copy_text`), `_shown` (`POST /copy/{key}`'s text to show beside each it stores, by the posted `rod`; the save itself `_copy_save`), the gym tick's JSON sentence resolved, `POST /profil` (async since: "Spol" read off the form) and `/forgot` passing the account's sex to the reset email; `PLAN_LINKS` maps an active plan to the page it unlocks; `/copy/{key}` takes a slot's key or an announcement's virtual key (`aktualno.<id>.<field>`, `_announcement_field`) or a gym card's (`dvorana.<id>.<field>`, `_gym_card_field`) or an upitnik question's (`upitnik.<id>.<field>`, `_upitnik_field`); `/upitnik/pitanje/…` are the editor's question routes; `/treninzi/vjezbe…` the library's (declared before `/treninzi/{program_id}`, which would take "vjezbe" for an id), `/treninzi/{id}/dan…` a programme's days (`_program_day`, `_day_item`: a day not the programme's, an item not the day's, 404; since 24.11.2026 `…/dio/{section}/krug`, a part made a circuit or a normal one again), the player's (30.10.2026: `…/kreni`, `…/vjezba/{k}` (`?odmor=`: the rest after the exercise before, from its save's redirect) and its `…/zamjena`, `…/kraj`, `…/odustani`; `_pass_day`, `_player`, `_log_rows` the set log's rows and their prefill, `_finish_page`, `_state_line`; since 24.11.2026, kružni trening: `Step` / `_steps` (k counts steps: an exercise, or since 25.11.2026 a circuit part's round, every exercise of the part on it, `Step.items`), `_saved` (a step saved: a round's when any exercise of it holds a set of it), `_marks` / `Mark` (a list row's "✓" or "2/3"), `_round_blocks` (25.11.2026, a round's exercises and their first values, in place of `_round_rows`), `_round_save` (a round's save), since 26.11.2026 `_day_items` the day's exercises alone (`ProgramDay.exercise_items`: a slot is no step), a round's title its part as the day names it (`part_label`), `day_part_name_save` (`POST …/dio/{section}/naziv`, `?naziv=1`), `day_slot_add` (`POST …/mjesto`) and `day_slot_fill` (`POST …/stavke/{item_id}/vjezba`, `?popuni=1`), `_first_values` / `_next_line` (25.11.2026: the first values from the load next time, the card's line), `_step_rest` (the rest after a step, `?odmor=`; a round's the circuit's alone), `SEGMENTS_MAX` (40: past it the bar is one track)); the day editor's add card (25.11.2026: `?dodaj=<part>`, the numbers, back at the card after an add), `_diary_rows` the karton's diary (termini and passes), `_save_video` a clip's upload (an exercise's or a day's intro video, named by a prefix), `/media/{name}` an exercise's clip or a day's intro video, or since 23.11.2026 a member's monthly photo and since 25.11.2026 his documents (the member and staff only); the karton's part 2 (23.11.2026: `/karton/masa` and `…/masa/{id}/obrisi`, `/karton/ogranicenja`, `/karton/slika` and `…/slika/{id}/obrisi`, each back at its card, `_karton_back`; `_body_line` the head line, `_month_label` "studeni 2026."), `_shrink_image` a photo's pipeline (upright, `IMAGE_PX` or the `px` given, a progressive JPEG with no EXIF: an announcement's photo and a karton's); the karton's documents (25.11.2026: `/karton/ogranicenja/dokument` and `…/dokument/{id}/obrisi`, `/karton/masa` multipart; `_spool_upload` an upload to `IMAGE_MB`, the photo's and the documents'; `_store_document` a PDF as it came or an image at `DOC_PX` 2400, `_DOC_UNSUPPORTED`), `/media`'s member files (`_MEMBER_FILE_TYPES`), and "Povijest vježbe" (`_render_karton` reads `?vjezba=`; `HISTORY_SHOWN` 10); `/tekstovi` (25.11.2026, `tekstovi_page`, `_require_trainer`) and the Jinja global `copy_on` (whether an optional slot's element prints: always for an editor, else while it holds a text); `PLAN_LINKS` names its door's slot (`app.door.*`), a plan's chip is its kind (`clanarina.chip.<kind>`), `_state_line` leaves its two lines that name no value to the template's slots, and the player passes the rests' values (`rest_between`, `rest_after`, `round_rest`) for the template's captions. Staff acting as a member (26.11.2026): `current_user` is the member while they do (`request.state.actor`, `request.state.acting`, `_acting`, `_actor`; `_ctx`'s `kao` and `actor`, base.html's strip and `data-kao`), `_ActingGuard` / `_acting_guard` (before every route, inside `SessionMiddleware`: the idle limit, `_clock`; the member or the actor no longer what they were; the page's identity, `?kao=` / `X-QMT-Kao`; the record, `_record_acting`), `/kao`, `/kao/zapisi`, `/kao/izlaz`, `/kao/{id}` (from build 4 until 27.11.2026 `POST /kao` too, the Karton tab's, `kao_pick`), the entry's one function `_enter_member` and the members' one list `_kao_members` (/kao's rows, the Karton tab's search's `find_members` / `find_rows`), `GET /karton/clan` (27.11.2026, `karton_find`, `PICK_MEMBER`: the Karton tab's search, a member's id → his karton, `/karton/{id}`, staff's again), `_card_by_member` (the card routes closed), a login drops the view (`_ACTING_KEYS`); `POST /karton/visina` (the height, the karton's since the same day); the gym training (26.11.2026, build 3; since 27.11.2026 its blocks, at `/dvoranski`, build 1 of `roadmap/2026-11-27-dvoranski-treninzi-plan.md`): `GET /dvoranski/termin/{id}` (`gym_from_termin`), `/dvoranski/trening/{id}` (`gym_page`; `_gym_page`: the main card's view, the chooser, the "what next" card, a Stanica or a Kružni set, and its query, `?blok=`, `?dalje=`, `?uredi=`, `?krug=`, `?spremljen=`, `?kreni=`, `?red=`, `?odmor=`, `?predlozak=`), its osvrt and its writes (`gym_template`, `gym_block_add`, `gym_block_delete`, `gym_station_save`, `gym_station_done` (the tick, JSON), `gym_block_rate` (the rating, JSON), `gym_circuit_plan`, `gym_round_save`, `gym_rounds_change`, `gym_empty`, `gym_day`, `gym_delete`), `_gym_of`, `_gym_block`, `_gym_url` / `_gym_back`, `_gym_rows` (a Stanica's set table), `_gym_krugs` (a Kružni set's Krug and their first values), `_gym_next` ("Nastavi trening"'s block), `_gym_overview` (`#pregled`'s rows), `_gym_when`, `_gym_until`, `_gym_staff`, `GYM_CLOCK_HOURS` (4: the clock shows while the first tick is that young), the old addresses' 303s (`gym_from_termin_old`, `gym_page_old`, `gym_osvrt_old`: `_same_query`), `_diary_rows`' `gym` and `open`; the tab Dvoranski treninzi (27.11.2026, build 2): `_has_gym` (`_has_online`'s twin: staff always, a member while a plan of `SESSION_KINDS` runs; `_ctx`'s `show_gym`), `GET /dvoranski` (`dvoranski_page`: the gate, "Otvoreni treninzi", "Trening izvan termina", "Zadnji treninzi", `GYM_TAB_LAST` 10), `POST /dvoranski/trening` (`gym_outside`, a training outside a termin: a member with a gym plan, staff for themselves, staff acting as a member whatever his plans), Amir's templates (27.11.2026, build 3: `gym_templates_page`, `gym_template_new`, `gym_template_page`, `gym_template_rename`, `gym_template_move`, `gym_template_delete`, `gym_template_block_add`, `gym_template_block_save`, `gym_template_block_move`, `gym_template_block_delete`, each `_require_trainer`'s; `GYM_TEMPLATES_URL`, `_tpl_url`), `treninzi`'s `has_gym_programs` and the programme forms with no `venue` (`BAD_VENUE` and the `VENUES` global went), `_gym_page`'s `back` (the tab, or the karton's row for a viewer with no tab), and `POST /karton/trening` (`karton_training`, the Karton's form, 26.11.2026) went; part B's routes (`…/dio/…`, `…/stavke…`, its `…/predlozak`) went; `karton_feedback`, `_posted_log` and `_log_entries` went |
| `src/qmt/web/templates/` | Jinja2. Design tokens + topbar/avatar menu in `base.html`; `_rest_bar.html` the rest bar the player and the gym training share (26.11.2026; since 27.11.2026 `qmtRest.keep`, a pause that outlives a reload), `karton_trening.html` / `karton_trening_osvrt.html` the gym training (since 27.11.2026 its blocks on the player's layout, at `/dvoranski`) and its osvrt, `dvoranski.html` the tab Dvoranski treninzi (27.11.2026, build 2), `dvoranski_predlosci.html` / `dvoranski_predlozak.html` the gym training's templates, their list and a template's editor (27.11.2026, build 3; staff's) |

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
  row: Početna · Raspored · Karton · Dvoranski treninzi (while a plan that books
  termini runs, grupni, individualni, poluindividualni or rehabilitacija:
  `show_gym`, `app._has_gym`, the twin of `_has_online`; since 27.11.2026, build 2
  of the dvoranski treninzi, the owner: "I would show the tab only to members
  with a gym plan. Similarly how a online training tab shows only to members
  with an online plan."; `.on` on every `/dvoranski` page, the tab's, a
  training's and its osvrt's) · Online treninzi (while an online plan runs,
  `show_online`) · Moja članarina · Prehrana; while staff act as a member his
  plans decide, as every tab. Staff's (the trainer, the owner): the
  same row, Dvoranski treninzi always (their own trainings outside a termin),
  Karton in it since 24.11.2026 (staff have a karton of their own; the
  owner: "Lets show the Karton tab in the Admin view as well so that Amir can
  check out the changes we made there"; their Karton is `.on` at `/karton` (from 26.11.2026 until build 2 at their own gym trainings' pages too,
  which are Dvoranski treninzi's since) and since 27.11.2026 at a
  client's karton, `/karton/<id>`, which the Karton tab's search opens, its crumb
  leading back there, Admin ▾ not on, no item current (it lit Admin ▾ → Trenutne
  članarine from 24.11.2026, where it was reached from until build 4, then for some hours
  of 27.11.2026 Korisnici, the owner's, while the view was his alone), and
  `/upitnik` Admin ▾ → Upitnik), then **"Admin ▾"**, a
  dropdown in the account menu's component (`.menu`, one script for both: a click
  opens it, another shuts it, so do a click outside and Escape, one menu open at a
  time): Gledaj kao član (`/kao`, a member's app as he has it, 26.11.2026,
  first; its record `/kao/zapisi` lights it too), Termini (`/admin`), Trenutne
  članarine (`/clanarine`), Upitnik (`/upitnik`), Vježbe (`/treninzi/vjezbe`, the library of exercises, 30.10.2026:
  under /treninzi, yet its pages light Admin ▾, not Online treninzi), Tekstovi
  (`/tekstovi`, every text of the app on one page, 25.11.2026) and, the
  owner's only, Korisnici and Statistika. The tab is
  `.on` while one of its pages is open, that item `aria-current="page"` (an accent
  bar and bold); the menu hangs under its tab, left-aligned to it, moved in by the
  script where the window's edge is nearer than the menu is wide. No item opens
  its page in edit mode (Upitnik's `?uredi=1`, which did, went the day it
  came, 26.10.2026): staff land on every page in normal mode, its ✎ pill
  there to press (the copy convention's edit mode). The wordmark shows in full only when the room the tabs leave allows it, otherwise
  "QMT": a container query on `.brand-slot`, never a window breakpoint — the pill is
  capped at 1100px, so the window width says nothing about the room inside it.
  **A bar of seven tab links** (since 27.11.2026: a member with a gym plan and an
  online plan; staff, seven and Admin ▾; six and Admin ▾ from 24.11.2026 fitted at
  every width from 901px) runs tight (base.html's rule for seven) and does not
  fit below 936px: measured for the owner's bar, the widest, at every width from
  901 to 1280px in both themes, the avatar left the pill's padding at 901–935px
  (the page scrolling sideways up to 914px), from 936px every tab sat on its line
  inside the pill, the brand's slot 87px there (its floor 86.4px), with 0.6px to
  spare. So the fold is at 960px, 24px on for another browser's letter widths
  (Fable's review): a bar of
  seven (its nav and its ☰ marked `.nav-7`, the template counting the tabs) is
  the ☰ drawer up to 959px (Step 2's rules again for `.nav-7`, between 901 and
  959px: keep the two in step) and one row from 960px (`tests/test_nav.py`,
  `SEVEN_FIT` the measured first fit, `SEVEN_FOLD` the fold); a bar of six or fewer keeps the drawer at ≤900px; nothing else
  tightens. Staff's wordmark is "QMT" at every width since (the brand's own
  query: seven tabs and Admin ▾ leave its slot under 19.2rem even in the
  1100px pill; a client's seven leave the whole name room at 1280px). All tabs tighten
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
  dismissal until they install, never on desktop, never while staff act as a
  member (it is about the device). **A member with no phone number gets the
  phone reminder** (`#phoneCard`, 26.11.2026, the owner: "if a user didnt give
  it, when he opens the app a popup reminder should appear similarly how a
  popup appears as a notification to install the app on the phone"; the phone
  stays optional): the install banner's card and place (on a fine pointer too,
  there 360px wide at the bottom right), on every page but the one-task pages
  (`solo_page`), `/profil` and the gym training's two (`no_nudges`, 26.11.2026: there the rest
  bar and "Dodaj vježbu" own the bottom; no install banner there either), staff acting as him included: ✕ ("Kasnije"),
  "Dodaj broj mobitela", "Da ti se trener može javiti ako se termin
  promijeni." and "Upiši broj" → `/profil#p-phone` (the field takes the
  focus); its ✕ keeps it away a week (`localStorage['qmt-phone']`), then it
  is back, until a number is saved; never on the load the install banner
  shows on (the phone one first, that one on a later load); no JS, no card.
  Its three texts are slots (`app.phone.title` and `.go` required, `.lead`
  optional), on /tekstovi under Aplikacija. All of it lives in `base.html`.
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
  **The karton's texts** (25.11.2026, the owner: "In the moji karton tab,
  lets allow the admin to change all of the text, like in other tabs as
  well") are slots, `karton.<area>.<name>` (114 since build 2 of the dvoranski treninzi, 27.11.2026, its form of a training outside a termin and the termini's hint gone to the tab; 120 since build 3 of 26.11.2026, 129 before it that day, 126 the day before, area by area in the
  page's order: `copy.KARTON_AREAS`): every static text karton.html
  prints, a member's own karton's, a staff member's own and the
  trainer's view's, each view's variant a slot of its own
  (`karton.staff.*`), its default the text the page printed. A
  control's words are `required` (a heading, a button, a link, a label,
  a `<summary>`, a table header, a confirm's three texts); a lead, a
  hint, a kicker, a chip, an empty line and a placeholder are not, and
  emptied print nothing for a member (no element, its box gone for the
  editor outside edit mode: karton.html's CSS). The words before a link
  carry its dash ("Visina nije upisana —"), the period after it is the
  template's. Attributes (the confirms' texts, two placeholders) print
  with `copy_text`, so they and the texts only another view prints are
  edited in the panel "Svi tekstovi kartona" at the bottom of the
  editor's own karton in edit mode (`copy.KARTON_PANEL`). A text inside
  a control is edited without pressing it: while it is open base.html's
  editor keeps its button, link, `<summary>` or label still (a space
  typed into a button's words made the browser click it, measured on
  25.11.2026: /upitnik's buttons had it too). What stays code is in
  copy.py's docstring.
  **Every member-facing text** (25.11.2026, the owner to Amir: "svugdje
  ikad uvest pravilo da može uređivat"; to Fable: "If there is a place
  where he is not allowed to change text, lets allow it") is a slot the
  same way, on every page a member or a guest reaches: the raspored
  (`raspored.*`: the week, the phone's day view and its sheet, the month,
  "Tvoj sljedeći termin", the series' offer and report, the booking gate,
  the trainer's variants), the online list, a programme and a day
  (`treninzi.*`, `program.*`, `dan.*`, staff's "Uredi …" too), the player,
  its finish screen and its leave dialog (`player.*`, `kraj.*`, `leave.*`:
  the round's screen, the rating, the rest bar, the dock), the profile
  (`profil.*`), the login pages and the login window (`auth.*`; the
  words a page and the window share are ONE slot), base.html's own
  pieces (`app.*`: a plan's door, `PLAN_LINKS`' words, printed on
  /moja-clanarina and the landing; the error alert's link, the install
  banner, since 26.11.2026 the phone reminder, the confirm dialog's default
  words, the osvrt prompt), the error
  page, the Mjesečno / Godišnje switch (`period.*`), and what was still a
  literal on the landing (`landing.*`), /moja-clanarina (`clanarina.*`:
  its facts' captions, its chips' words, the status box's fixed words, the
  ledger's headers) and /prehrana (`prehrana.*`, each paragraph split at
  its bold words). 268 slots (270 since 26.11.2026: the profile's
  "Visina (cm)" left, the phone reminder's three came), each its page's
  default character for character; required as the karton's, a caption
  before a value
  ("Odmor između serija:") among them; an optional one emptied prints no
  element for a reader (`_copy.html`'s `c.opt(key, tag, attrs)`, or the
  page's `copy_on(key)`: the editor keeps the element, `data-opt`, which
  base.html hides outside edit mode). Where the same words do the same
  job in two places one slot prints in both ("Odmor između serija:" on
  the day page and in the player). A control's words are edited without
  pressing it, as on the karton (in edit mode the player's leave dialog
  lets a click on an editable text be: "← Natrag"'s words open in the
  editor, not the dialog). A control's text whose words sit beside
  a value is one `<span>` inside the control (a button is a flex box: "Krug
  2 <odrađen>"). A word too long for its box breaks anywhere (base.html's
  `main span.t, dialog span.t, #a2hs span.t, #phoneCard span.t`, `.fb-modal`, the rest bar),
  save where a box takes its width from its words (the set log's headers
  and its "dodatna serija", a raspored card's button from 861px): there it
  is as wide as its words up to a bound, inside which a long text wraps;
  and the buttons, pills and switches whose words are slots wrap rather
  than push the page (the Mjesečno / Godišnje switch, a chip on
  /moja-clanarina, the week's buttons, the rest bar's pill; the install
  banner scrolls inside itself). With the pages' own words no word moves:
  measured on every member page, the untouched tree beside the build,
  every word's place, 360–1280px. The Mjesečno / Godišnje switch's two
  words are edited on /tekstovi only (printed plain, no box): in edit
  mode the switch must keep switching, the yearly prices behind it being
  edited in place. A script's static words come from a slot (`copy_text`,
  `|tojson`: the sheet's "Rezervirano", the rest bar's "Kreni"); one built
  around a value stays the script's. What stays code: a sentence built
  around a value (its fixed words a slot only when they read as a phrase
  of their own: "Preporučeno:", "Članarina vrijedi do"; not "odrađen 2×",
  "6 od 8 vježbi", "Krug 2"), what a row or a model prints (`PLAN_LABELS`,
  `SECTIONS`, `LEVELS`, `GOALS`, `FEELING_LABELS`, the weekdays and months,
  "danas" / "sutra"), the routes' flashes and refusals, the emails, every
  aria-label, alt, title attribute and `<title>`, the crumbs, the nav, the
  editor's own controls, the strip over a page while staff act as a member
  and the trainer's "Otvori kao član" (26.11.2026: staff's own chrome; since
  build 4 the Karton tab's way into a member's app and the caption "Vidi samo
  trener" too), the studio's address, phone and email (the text of
  the link each opens) and the dev server's own lines. The staff-only
  templates stay as they are. **`/tekstovi`** (Admin ▾ → Tekstovi) lists
  every plain slot by page and area (`copy.TEXT_PAGES`), so the texts only
  a member or a guest sees are in the editor's reach; the karton's panel
  stays. The gym training's texts (26.11.2026, build 3) are slots the same way, `gym.<area>.*` (65 since 27.11.2026, its blocks: 34 came, 22 went; 53 with part B;
  the landing's `gym.kicker` and `gym.h2` are the landing's), on /tekstovi under "Trening u
  dvorani", after "Trening (izvođenje)", and so are its tab's since 27.11.2026 (`gym.tab.*`,
  17, the section's first area "Dvoranski treninzi", its "Otvori stranicu →" `/dvoranski`; the
  training page's slots print where the tab says the same: `gym.state.open`, `gym.head.outside`,
  `gym.head.date_field`); where the words do the same job as in the player and
  its finish screen, the player's slots print in both (`player.*`, `dan.*`, `kraj.*`).
  **The slash forms** (27.11.2026, build 5; the owner, of his karton's "Tvoji online
  treninzi i treninzi koje upišeš sam/a.": "on login do we know the sex of the user and
  then to use the correct grammar instead of" that): a text that does not know its reader
  says both forms, "bio/la", "sam/a", "siguran/na", and the gym owner types his so too. A
  member who gave his sex on /profil (`users.sex`, optional) reads each as his, wherever a
  text prints, through `grammar.gendered(text, sex)` (`src/qmt/grammar.py`: a whole token of
  letters, a slash and "la" after an "o" (the l-participle), "na" after "an" or "a" after
  two letters or more, nothing after it but punctuation; the fleeting a ("šao" by rule,
  `FLEETING_LA`), the -jeti verbs (`JETI`) and the adjectives with a fleeting a
  (`FLEETING_A`) by tables of whole words, a line each to add one; the word's capitals
  kept; "24/7", "km/h", "i/ili", "n/a", a quoted „bio/la”, a path, an address never
  touched; a form the rules do not cover as it is; no sex, the very text; two whole
  words are a form too where the second can be nothing but the first's feminine, an
  l-participle and its feminine, "bio/bila", or a `FLEETING_A` adjective and its,
  "Spreman/spremna" (Fable's review: the guide's own two; its fifth section's default
  says "bio/bila siguran/sigurna" since, the masculine it lacked), never "the word and an
  a", which "dan/dana" or "mjesec/mjeseca", a noun's forms by number, look like). Whose sex is one
  value, the template context's `rod` (`_ctx`: the effective user's, the member's while
  staff act as him, None for a guest; on the trainer's view of a karton the member's,
  `_render_karton`), read by `_copy.html`'s macros and `copy_text` (the filter
  `gendered`), the flashes (base.html's two alerts, every page's own `?error=` / `?ok=`
  print and the routes' refusal alerts: the same filter), the upitnik's questions, options
  and scale ends on /upitnik (an option's value, what is posted and stored, stays the
  row's text) and the karton's "Odgovori" (each question by the member whose answers they
  are; the answers as given), a JSON sentence to a script in its route (the gym tick's),
  and the password-reset email (the account's; the verification email stays as it is).
  **What is stored, and what the editor edits, is always the text with its slashes**: an
  editor's span whose text resolves otherwise carries the stored one (`data-raw`), which
  base.html's editor shows and edits in edit mode (the resolved one waits in
  `data-shown`), the resolved one back when edit mode ends; a save posts the page's sex
  (the toggle's `data-rod`) and `POST /copy/{key}` answers with the text to show beside
  each it stores (`shown`, `shown_items`, `shown_rows`, `also`'s: `app._shown`), so no
  reload. A reader who has not said, and every guest, gets every page byte for byte as
  before; an editor who has not, his texts as stored and his answers as they were
  (`tests/test_spol.py`); /tekstovi's lead says it in one sentence.
  **The rule is tested for the pages to come**
  (`tests/test_copy_rule.py`): a static scan of every member-facing
  template finds every literal text (Jinja, scripts, styles, the
  `<title>` and the tags stripped; a placeholder's and a confirm's words
  kept), and each must be a slot or in its allowlist, a group per reason; a
  new literal fails with "make it a slot (copy.py) or add it to the
  allowlist with the reason".
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
  `site_copy` row of a removed key is never read. **Every price has its
  bazna cijena since 23.11.2026** (Croatia's Pravilnik o isticanju bazne
  cijene proizvoda, NN 132/2026, in force since 17.11.2026 under art. 7 of
  the Zakon o zaštiti potrošača: beside each retail price the base price,
  for a service the one applied on 10.9.2026, or on the day it was first
  offered after that; the owner: "add it to every price", today every base
  is the current price): a slot of its own beside each price slot,
  `copy.BASE_OF` (price key → base key, a Jinja global: `price.<plan>.amount`
  → `price.<plan>.base`, `.year_amount` → `.year_base`, the tiers'
  `offer.online*.price` / `.year_price` → `.base` / `.year_base`,
  `addon.online` / `addon.dvorana` → `addon.*.base`), each a number
  (`required`) defaulting to its price's default, and the words before
  them, `price.base_label` ("Bazna cijena na 10.9.2026.", required too, the owner's wording of 24.11.2026; the template puts
  the colon after it). A gym card's own prices have theirs in its row,
  `base_price` / `base_year_price` (`copy.GYM_CARD_BASE_OF`). One macro
  prints it, `_plan_price.html`'s `base(price_key, base_key)`: `<small
  class="base">` (base.html's `.price > .base`, a muted .8rem line of its
  own), the last child of its `.price` block, when the price holds a number
  (the Jinja test `numeric`) and, for a visitor, the base does too (never
  "Bazna cijena na 10.9.2026.:" with nothing after it, nor under "na upit"; the editor
  gets the box as soon as the price holds a number), " €" after a base that
  is a number without a sign of its own (`priced`); `base_paren` the same in
  brackets, `span.base-paren`, in a line of prices (Individualno's,
  prehrana's hint). The
  landing's rows of cards keep their prices level: when any card of a row
  shows a base line, every price of the row keeps its room
  (`.swipe-row:has(.price:not([hidden]) > .base)`). **A price's first number
  is its base too**: `POST /copy/{key}` that stores a number into a price of
  `BASE_OF` whose base holds none (stored, else its default: "na upit")
  stores the base as well, the same text, and its answer carries `"also":
  [{"key", "text"}]`, which base.html's editor applies to every span of that
  key; a gym card's `price` / `year_price` the same on its row's base
  columns; Zadano (and a number emptied, which is Zadano) never touches a
  base. Migration `8a67c43d0bb4` added the two columns (each card's base =
  its price) and gave every price slot the gym owner had typed a base row
  with its text: on prod every base starts equal to what he typed.
  **Plan names** (18.10.2026) are slots on `/moja-clanarina`
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
  `_require_owner`. Clients only ever see their own data. "Trainer" there means STAFF,
  the trainer or the owner (`app._is_staff`, 26.11.2026): every decision about what a
  viewer sees or may do as staff asks it (a template `can_edit_copy`), never `is_trainer`
  alone, which stays the datum /korisnici reads and grants (`db.set_trainer*`); the owner is
  never a member either (`db.memberships_overview` leaves him out by `OWNER_EMAIL`).
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
- A booking can be cancelled until 4 h before the termin, `CANCEL_CUTOFF_HOURS`
  (12 h until 25.11.2026; one rule, `db.cancel_deadline`, asked by
  `cancel_booking` and by both calendar buttons, and its number printed
  from config in every sentence, the day-before reminder's email too; a
  termin the trainer canceled can always be dropped). Since the cutoff and
  the closing below are both 4 h, a test that needs a booking inside the
  cutoff makes it directly (`book()` refuses an empty termin that close).
  A termin nobody has booked closes `CLOSE_EMPTY_HOURS` (4) before it starts
  (`db.is_closed`); one with a booking stays open until it starts. Termini can
  be booked in the running week and `BOOKING_WEEKS` − 1 more (`BOOKING_WEEKS`
  = 4, `db.booking_window`), never past the plan's dospijeće. An online pass
  with no activity for `PASS_STALE_HOURS` (2) cannot be continued, only
  finished or discarded (`WorkoutLog.stale`, 31.10.2026). The four knobs are
  env vars (DEPLOY.md); `BOOKING_HORIZON_DAYS` is gone. So are the load next
  time's four (25.11.2026, `db.next_set`): `PROGRESS_UP_PERCENT` (5: an exercise
  rated 6 or lower, its weight up 5 %, half a kilo at least), `PROGRESS_DOWN_PERCENT`
  (10: rated 9 or 10, its weight, reps or seconds down 10 %, a step at least;
  seconds to a multiple of 5 since 26.11.2026, 5 less at least),
  `PROGRESS_REPS_STEP` (1: a rep more for one done with no weight) and
  `PROGRESS_SECONDS_STEP` (5: seconds more for a timed one, to the next multiple
  of 5); 7 or 8, and no rating, as he did it. And staff acting as a member
  (26.11.2026): `ACT_AS_IDLE_MINUTES` (30), the minutes with no request after
  which the view ends; the first request after it runs nothing, GET or POST
  (`app._acting_guard`, DEPLOY.md). And the gym training's (26.11.2026, build 3):
  `GYM_OPENS_HOURS` (4), the hours before a termin from which its training is the member's to
  write, until the end of the day after it (`db.gym_window`; staff acting as him at any time).
  Its blocks' numbers are code, no env var (27.11.2026): 40 blocks a training
  (`db.GYM_MAX_BLOCKS`), 12 rows a Kružni set (`GYM_MAX_ROWS`), 1–20 Krug, 4 to start
  (`GYM_ROUNDS`, `GYM_FIRST_ROUNDS`); its page's clock shows while the first tick is at most
  `app.GYM_CLOCK_HOURS` (4) old and is stored nowhere. The two templates are migration
  `9b4e2d7f1c58`'s rows on prod; the dev seed and the tests put back `copy.GYM_TEMPLATES`
  (`db.reset_gym_templates`), which deletes every template first.
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
