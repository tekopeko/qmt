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
pytest -q                                  # 108 tests, must stay green
```

Demo logins: `trener@qmt.local/trener123` (trainer **and** owner locally, via
`OWNER_EMAIL` in `.env`), `ivan@qmt.local/lozinka123` (has grupni + individualni +
online plans, filled upitnik, diary entries, one feedback prompt pending),
`ana@qmt.local`, `sara@qmt.local` (deliberately **no plan** — demos the booking gate),
all `lozinka123`.

Prod test aliases already on the allowlist: `tvrtko.doresic+qmt1@gmail.com` (and
`+qmt2`, `+qmt3`) — Gmail delivers them to the owner's inbox, so the verify-email
round trip is testable. Prod demo clients: `*.demo@example.com` / `demo12345`.

### Deployment (Railway)

See **DEPLOY.md**. Dockerfile → `start.sh` runs `alembic upgrade head` then uvicorn;
`/healthz` is the probe. Railway CLI is linked on the owner's machine (`railway
variables --kv` reads config). Pushing to `master` auto-deploys.

## Pages

| Route | Who | What |
|---|---|---|
| `/` | public | Landing: hero (kicker, headline, lead; a member's one action; no buttons for guests, the pill has them) whose photo is a link to the offer; **the offer (`#usluge`) is three tiers of the online plan** (QMove START / PRO, featured / ELITE; each with the MojiMakrosi add-on, 5 €): tier 1's monthly price is the online plan's own, every other price (tiers 2–3 monthly, all three yearly) is editable text until a plan exists; a **Mjesečno / Godišnje** switch under the cards shows one price per card (per page view, monthly without JS); on phones (<900px) the tiers are a swipe carousel with three dots. Below it, quieter, **the gym (`#dvorana`)**: Dvorana and Individualno cards (add-on 3 €; Individualno names its semi-individual and rehab prices in a muted line under its own), tiers too (the plan's real monthly price, an editable yearly one) with their own switch, one choice with the tiers' (pressing either flips both sections), and a two-card swipe row on phones. Gallery from `static/gallery/`; contact. A card's button follows the visitor: owner of the plan → into the app, member → "Odaberi plan" on `/cjenik`, guest → "Registriraj se" when signup is open, else "Javi nam se" → `#kontakt` |
| `/cjenik` | client | **Members only since 28.9.2026** (guests are sent to log in): where plans are bought and managed; the public price list is the landing's offer. Plan pricing from Stripe ("na upit" until Price ids exist) + "Pretplati se karticom" → Stripe Checkout; `/placanje/portal` for card/cancel/invoices |
| `/raspored` | client | Week calendar, booking, "Moja članarina" + "Moje rezervacije" as day columns. After booking a weekly slot the ok alert offers "Isti termin svaki tjedan do …" → `POST /book/{id}/series` books that slot for the rest of the paid period |
| `/karton`, `/upitnik` | client | Personal file: upitnik result, training diary, termini. `/karton/{id}` is the trainer's read-only view |
| `/treninzi` | client/trainer | Online programmes — automatic (see below) |
| `/prehrana` | public | MojiMakrosi link (`/nutricionizam` 301s here) |
| `/profil` | any | Basic info form + članarina overview + billing history |
| `POST /copy/{key}` | trainer/owner | Saves one in-place-edited text (JSON); empty text restores the default |
| `/admin` | trainer | Weekly timetable as an **editable week grid** + one-off termini |
| `/clanarine` | trainer | Record cash/card uplate per client per plan |
| `/korisnici`, `/statistika` | owner | Roster + trainer grants; uplate per plan per month |

Media (`data/uploads/`, gitignored) is served ONLY via the auth-gated `/media/{name}`.

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
renewal never smears two months' quotas together. **A booking can repeat weekly**
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
| `src/qmt/copy.py` | The texts a trainer/owner may edit in place: slot → default, character limit, label |
| `src/qmt/models.py` | `User` (+profile fields), `SessionTemplate`, `TrainingSession`, `Booking`, `Membership`, `Payment`, `OnboardingResponse`, `TrainingLog`, `Program`(level/goal)/`ProgramItem`; `PLAN_*`, `FEELING_LABELS`, `PAYMENT_METHODS` |
| `src/qmt/db.py` | Queries + rules. **`book()` locks the session row FOR UPDATE** and re-counts inside the lock (tested) |
| `src/qmt/upitnik.py` | Questions, scoring thresholds, level/goal labels |
| `src/qmt/auth.py` | bcrypt + signed email tokens (verify 24 h; reset 1 h, single-use) |
| `src/qmt/mailer.py` | Only Resend importer. Also `send_new_user_notice` → owner hears about each first verification |
| `src/qmt/reminders.py` | Email podsjetnici (pre-dospijeće + day-before termin), claim-idempotent via the `reminders` table; app lifespan ticks every 6 h, `scripts/send_reminders.py` forces a pass |
| `src/qmt/storage.py` | Media backend: local disk, or Cloudflare R2 when the four `R2_*` vars are set (then `/media` 307s to presigned URLs) |
| `src/qmt/payments.py` | Stripe: prices for /cjenik (cached), Checkout + portal sessions, signed webhook → `record_payment`. Tolerates both invoice shapes (pre/post 2025 API) |
| `src/qmt/web/app.py` | All routes. `current_user()` per route; `PLAN_LINKS` maps an active plan to the page it unlocks |
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
  account menu (identity header, Profil, theme toggle, Odjava).
- **Guests log in through a modal** (`#authDlg`, opened by `data-auth` links; `/login`
  and `/signup` remain the no-JS fallback). **Clients on phones get an install
  banner** (`#a2hs`) once, never on desktop. Both live in `base.html`.
- **Prices are public on the landing since 5.10.2026** — the owner's decision,
  reversing the members-only rule of 28.9. (which was legal advice: public
  prices would need the prior price shown beside them, the way shop shelves do).
  The way back is one variable: `PUBLIC_PRICES=off` hides every price from
  guests again. Card prices come from `_offer_prices` in `app.py` (the Stripe
  Price, else `REFERENCE_PRICES`), never from the template. `/cjenik` stays
  members-only and no public page links to it. **Registration is one switch**,
  `SIGNUP_MODE` = `closed` (the default, also when unset or mistyped) / `invite`
  (owner + `ALLOWED_EMAILS`) / `open`; closed hides every "Registriraj se" and
  the modal's Registracija tab. Existing accounts always log in. Tests run with
  `invite` (`tests/conftest.py`).
- **Public copy is editable in place** by the trainer and the owner (6.10.2026, so
  the gym owner fine-tunes the texts himself). Every such text is a slot in
  `src/qmt/copy.py` with a character limit its box can take, printed through
  `{{ c.t("key") }}` (`_copy.html`); the editor in `base.html` ("✎ Uredi
  tekstove", then click a text; Enter saves, Esc cancels, "Zadano" restores the
  default) posts to `/copy/{key}`, which enforces the limit again and stores
  the text in `site_copy`. Adding a text = one registry line + the macro call;
  `tests/test_copy.py` then checks it is on a page and, in a real browser, that
  every slot at its limit still fits at 360 / 390 / 900 / 1280px. Never put a
  slot inside a link's `href` or an attribute — the editor edits text nodes.
  **Lists** (15.10.2026, the offer cards' bullets) are a `ListSlot`: a count
  limit and a per-item limit, one `site_copy` row holding a JSON array, printed
  through `{{ c.points("key") }}`. In edit mode each item has a ✕ and the list
  a "+ Dodaj stavku"; an item saves with its `index` (n appends, an empty text
  removes it) and "Zadano (cijela lista)" (`reset=1`) restores the whole list.
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
   (auto-renew monthly): `/cjenik` → `POST /placanje/{plan}` → Checkout; signed
   `invoice.paid` webhook → `db.record_payment(method="stripe")`; portal at
   `/placanje/portal`. Everything is in `src/qmt/payments.py`, switched on by
   `STRIPE_*` vars (see DEPLOY.md). Still owed by the owner before LIVE keys: the
   d.o.o.'s Stripe account, real prices, and the accountant's Fiskalizacija 2.0 flow
   (mandatory since 1.1.2026, fiscalized račun per B2C charge).
5. ⏳ Owner's own content: landing/service copy, exercise videos. The R2 storage
   layer is BUILT (`storage.py` + `scripts/migrate_media_to_r2.py`) — activating it
   is just the four `R2_*` vars on Railway; until then `data/uploads` stays ephemeral
6. ⏳ Mini-kuharica (30–50 recipes) + deeper mojimakrosi link-up

See `roadmap/2026-09-03-owner-voice-note.md` for the owner's own wish list and
`roadmap/STATUS.md` for where the last session left off.
