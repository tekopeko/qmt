# CLAUDE.md

Guidance for working in this repo. Read this before making changes.

## What this is

**QMT** — booking app for Quality Movement Training (a Croatian training/rehab studio,
run by the owner's friend). Clients reserve spots in the weekly timetable; the trainer
manages the timetable and sees rosters. Croatian UI throughout. FastAPI + Jinja2 +
Postgres + Alembic, deployable to Railway — deliberately the **same stack and
conventions as `../macro_tracker` (mojimakrosi.com)**, its sibling repo.

**Relationship to mojimakrosi:** two separate entities — separate repo, DB, deploy,
domain — but identical auth shape (email+password, signed-cookie session, allowlist
sign-up) and conventions, so a future merge stays cheap. The merge path, when wanted:
link accounts by email (same person = same address in both), then either cross-link the
two UIs or mount one app under the other. Nothing in this repo may import from
macro_tracker or touch its DB.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
createdb qmt && alembic upgrade head       # schema (Alembic = source of truth)
python scripts/seed_demo.py                # trainer + 2 clients + timetable (dev only)
python serve.py [--reload] [--port 8100]   # 8100 — 8000 is mojimakrosi's local port

createdb qmt_test                          # once
pytest -q                                  # tests live in tests/ and must stay green
```

Demo logins: `trener@qmt.local/trener123` (admin), `ivan@qmt.local/lozinka123`,
`ana@qmt.local/lozinka123` (seed marks them verified; real sign-ups must click the
emailed verify link before login works).

### Deployment (Railway)

See **DEPLOY.md** for the full runbook (Railway project, `/app/data` volume for
media, variables, qmt.mojimakrosi.com DNS, first-boot trainer bootstrap,
backups). Dockerfile → `start.sh` migrates then serves; `/healthz` is the probe.

## Pages

`/` is a **public landing** (hero, services, gallery, contact, "Rezerviraj termin"
CTA) — the shop window, with a reserved "Uskoro" slot for videos/training content.
The **Galerija** auto-lists images in `src/qmt/web/static/gallery/` (sorted by
filename) — adding a photo is a file drop, no code change. Instagram can only be
scraped ~12 posts deep before the login wall, so new gallery material comes from
the trainer's originals or an IG post link (its /embed/ page exposes the
full-size image).
`/raspored` is the authenticated calendar. `/treninzi` is a **library +
assignments**: the trainer builds a programme once (ordered exercises: title,
text, optional image/video upload) and hands it out via `ProgramAssignment`
(programme, client, day) — same programme to many clients/days, unique per
(programme, client, day). A client sees a programme (and its media) ONLY through
an assignment; the library is trainer-only. Media is stored in `data/uploads/`
(gitignored) and served ONLY via the auth-gated `/media/{name}` route — never a
public static mount. `/nutricionizam` explains and links the
sibling app (mojimakrosi.com, `MOJIMAKROSI_URL`): accounts are separate for now,
clients are told to register with the same email so linking stays possible.
Trainer tools live under `/admin`; login lands on `/` (or `?next=`).

## Architecture — the one idea

**A single booking mechanism covers everything the studio offers.**
`TrainingSession.capacity = 8` → group class; `capacity = 1` → individual termin
(personal training, rehab). No separate appointment system. Concrete sessions come from
`SessionTemplate` rows (the standing weekly timetable) via **lazy materialization**:
viewing a week upserts that week's sessions (`ON CONFLICT DO NOTHING` on
`uq_session_template_start`), clamped to the booking window — no cron,
concurrency-safe. The trainer edits/deletes templates freely in /admin; on edit,
**future sessions with no bookings are pruned and re-materialize with the new
values**, while booked sessions are never touched (the trainer cancels those
explicitly). Semantics locked by tests.

| Path | Role |
|---|---|
| `src/qmt/config.py` | `.env`, `TRAINER_EMAIL`/`ALLOWED_EMAILS` allowlist, booking knobs (`CANCEL_CUTOFF_HOURS`, `BOOKING_HORIZON_DAYS`), prod guards |
| `src/qmt/models.py` | `User` (`is_trainer`), `SessionTemplate`, `TrainingSession`, `Booking` |
| `src/qmt/db.py` | Queries + booking rules. **`book()` locks the session row FOR UPDATE** and re-counts inside the lock — capacity must hold under concurrent taps (tested) |
| `src/qmt/auth.py` | Only bcrypt importer + signed email tokens (verify 24 h; reset 1 h, single-use via `pw_marker`) |
| `src/qmt/mailer.py` | Only Resend importer (lazy httpx). Senders return `False` without a key → dev shows the link on-page (app.py refuses that path in prod) |
| `src/qmt/web/app.py` | All routes. Auth = `current_user()` helper per route (promote to middleware if routes multiply) |
| `src/qmt/web/templates/` | Jinja2. Design tokens in `base.html` |

## Conventions (follow these)

- **Croatian everywhere** in the UI. Errors are user-facing sentences raised as
  `db.BookingError`.
- **QMT design tokens come from the LOGO, not the old store theme.** The logo
  (`src/qmt/web/static/logo.png`, red/grey triangle — sampled `#f80000` red,
  `#606060` grey) is the identity. Accent `--accent` (#e10600 light / #ff342b
  dark), neutral surfaces, PT Sans uppercase display + Inter body. The Shopify
  theme's acid yellow was a false lead — do not reintroduce it.
- **Modern surface language, light + dark.** Rounded controls (12px) and cards
  (14–16px), soft shadows, no hard boxy borders. Both themes are first-class:
  tokens per `[data-theme]` in base.html, toggle top-right, saved as
  `localStorage['qmt-theme']`, pre-paint script avoids theme flash. Legacy token
  names (`--ink`, `--signal`…) are aliased in base.html — new code uses the new
  names. Never style with a raw hex that only works in one theme (the 1:1 chip
  bug: white-on-white in dark).
- **Every schema change is an Alembic migration** (`alembic revision --autogenerate`).
- **Tests must stay green** (`pytest -q`). New booking rules get a test — especially
  anything that must hold under concurrency (see `test_capacity_race_no_overbooking`).
- **Trainer-only routes** go through `_require_trainer`. Clients may only ever see
  their own bookings; rosters (other people's names/emails) are trainer-only.
- **Jinja + dicts:** never key a template dict `items` — Jinja resolves `d.items` to
  the builtin method (this bit us on day one; the calendar uses `sessions`).
- **Every screen works on every device — STANDING GOAL.** Phones are the primary
  client device. Any UI change must hold at 390 px: no horizontal page pan (wide
  tables scroll inside their own `overflow-x:auto` container), tap targets stay
  comfortable, grids collapse to single column. Verify with the phone emulator
  (Playwright 390×844) before calling UI work done — same discipline as
  mojimakrosi. `document.documentElement.scrollWidth - clientWidth` must be 0.
- **QMT is a PWA** (manifest + icons from the logo + root-scoped `/sw.js` with
  `Service-Worker-Allowed: /`). The SW never caches HTML or `/media` — pages are
  per-user and time-sensitive; it caches immutable statics only and shows a
  Croatian offline notice. `start_url` is `/raspored`. Playwright's Chromium
  registers it, so a stale SW can explain "weird" test behaviour — bump the
  VERSION string in sw.js when changing cached assets.

## Gotchas

- `.env` is optional in dev — defaults hit local Postgres DB `qmt`, session key is a
  dev constant, allowlist is empty (only `TRAINER_EMAIL`, if set, may sign up).
- Sessions are stored tz-aware (Europe/Zagreb) — compare against
  `datetime.now(config.TZ)`, never naive `now()`.
- Cancelled sessions stay in the calendar crossed out on purpose (a vanished session
  reads as a bug to clients). "Otkaži termin" on the roster page, undoable.
- The seed script is a dev RESET: it wipes templates/sessions/bookings and
  re-seeds the timetable (users are upserted). Never point it at prod.
- Real studio facts (from their Setmore): open pon/sri/čet/pet 07:00–20:00,
  Virovska 1, Zagreb. Group trainings are hourly, capacity 8 — the old Setmore
  system faked capacity with 16:05/16:10/16:15 slots, which is exactly what this
  app replaces. Individual 1:1 seeded Mon–Fri 20:00 as a placeholder until the
  trainer confirms his real slots.

## Roadmap (agreed with the owner)

1. ✅ Booking MVP
2. ✅ Treninzi: programme library + dated per-client assignments, media;
   /nutricionizam sibling link; PWA; standing mobile-first rule
3. ✅ Email verify + password reset (Resend); deploy runbook in DEPLOY.md
4. Deeper mojimakrosi link-up (shared identity by email, plan-gated bundles)
