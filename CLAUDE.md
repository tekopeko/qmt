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
pytest -q                                  # 61 tests, must stay green
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
| `/` | public | Landing: hero, six service cards (hover CTA → `/cjenik`, or "✓ Aktivna članarina" linking into the app), gallery from `static/gallery/`, contact |
| `/cjenik` | public | Plan pricing — **prices are still "na upit" placeholders**; the future Stripe checkout entry point |
| `/raspored` | client | Week calendar, booking, "Moja članarina" + "Moje rezervacije" as day columns |
| `/karton`, `/upitnik` | client | Personal file: upitnik result, training diary, termini. `/karton/{id}` is the trainer's read-only view |
| `/treninzi` | client/trainer | Online programmes — automatic (see below) |
| `/prehrana` | public | MojiMakrosi link (`/nutricionizam` 301s here) |
| `/profil` | any | Basic info form + članarina overview + billing history |
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
webhook will write the same rows with `method="stripe"`.

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
| `src/qmt/models.py` | `User` (+profile fields), `SessionTemplate`, `TrainingSession`, `Booking`, `Membership`, `Payment`, `OnboardingResponse`, `TrainingLog`, `Program`(level/goal)/`ProgramItem`; `PLAN_*`, `FEELING_LABELS`, `PAYMENT_METHODS` |
| `src/qmt/db.py` | Queries + rules. **`book()` locks the session row FOR UPDATE** and re-counts inside the lock (tested) |
| `src/qmt/upitnik.py` | Questions, scoring thresholds, level/goal labels |
| `src/qmt/auth.py` | bcrypt + signed email tokens (verify 24 h; reset 1 h, single-use) |
| `src/qmt/mailer.py` | Only Resend importer. Also `send_new_user_notice` → owner hears about each first verification |
| `src/qmt/web/app.py` | All routes. `current_user()` per route; `PLAN_LINKS` maps an active plan to the page it unlocks |
| `src/qmt/web/templates/` | Jinja2. Design tokens + topbar/avatar menu in `base.html` |

## Conventions (follow these)

- **Croatian everywhere** in the UI. Errors are user-facing sentences raised as
  `db.BookingError`.
- **Design tokens come from the LOGO** (`static/logo.png`): accent `--accent` (#e10600
  light / #ff342b dark), neutral surfaces, PT Sans uppercase display + Inter body.
  Rounded controls (12px) and cards (14–16px), soft shadows. Both themes are
  first-class (`[data-theme]` tokens, pre-paint script, saved in
  `localStorage['qmt-theme']`). Never style with a raw hex that only works in one theme.
- **The topbar is ONE row at every width** (the YouTube header): `flex-wrap: nowrap`,
  brand left, tabs middle, avatar right. When space runs out the wordmark shortens to
  "QMT" (≤1200px), then the tabs fold into the ☰ drawer (≤900px, sized for the owner's
  eight tabs). Tabs never wrap their own label. The avatar opens the account menu
  (identity header, Profil, theme toggle, Odjava).
- **Every schema change is an Alembic migration.**
- **Tests must stay green** (`pytest -q`). New rules get a test — especially anything
  that must hold under concurrency (`test_capacity_race_no_overbooking`).
- **Trainer-only routes** go through `_require_trainer`, owner-only through
  `_require_owner`. Clients only ever see their own data.
- **Jinja + dicts:** never key a template dict `items` — Jinja resolves `d.items` to the
  builtin method (the calendar uses `sessions`).
- **Every screen works on every device — STANDING GOAL.** Phones are the primary client
  device. Verify at 390px (and 360px) with Playwright before calling UI work done;
  `document.documentElement.scrollWidth - clientWidth` must be 0.
- **QMT is a PWA** (manifest + icons + root-scoped `/sw.js`). The SW never caches HTML
  or `/media`; bump its VERSION when changing cached assets.

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
- Real studio facts: open pon/sri/čet/pet 07:00–20:00, Virovska 1, Zagreb; group
  trainings hourly, capacity 8.
- **Screenshots:** oversized images earlier in a session can poison every later image
  request. Keep them one per message.

## Roadmap

1. ✅ Booking MVP, email verify/reset, deploy, PWA
2. ✅ Membership plans gating bookings; manual cash/card uplate; payments ledger +
   owner statistika
3. ✅ Karton (upitnik routing, per-termin feedback, diary, calendar); automated online
   programmes by (razina × cilj)
4. ⏳ **Card payments** — Stripe chosen (see `roadmap/` and memory). Blockers: owner's
   Stripe account for the d.o.o., real prices for `/cjenik`, and the accountant
   confirming Fiskalizacija 2.0 (mandatory since 1.1.2026, fiscalized račun per B2C
   charge). Then: Checkout on /cjenik + `invoice.paid` webhook → `db.record_payment`.
5. ⏳ Owner's own content: landing/service copy, exercise videos (host on Cloudflare R2
   ≈ $7.50/mo for 500 GB with free egress — also fixes the ephemeral `data/uploads`)
6. ⏳ Mini-kuharica (30–50 recipes) + deeper mojimakrosi link-up

See `roadmap/2026-09-03-owner-voice-note.md` for the owner's own wish list and
`roadmap/STATUS.md` for where the last session left off.
