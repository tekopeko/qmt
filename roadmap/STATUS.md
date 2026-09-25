# Where the last session left off — 25.9.2026.

Read `CLAUDE.md` first; this file only carries what isn't obvious from the code.

## Deploy state

`master` is deployed (Railway auto-deploys on push) and carries everything up to
the login modal + install banner. 90 tests green.

**Branch `redesign` holds the Shape-club-style redesign and is NOT merged.** The
owner decides whether it goes to prod; merging `redesign` into `master` deploys
it. It is two commits of landing work plus one of app-screen work (see below).

## What this session shipped (25.9.)

- **`qmt-design` skill** (`.claude/skills/qmt-design/`): SKILL.md, generated
  `tokens.md`, the component catalog, borrowed patterns from shapeclub.app, and
  `scripts/audit.py` — a measured audit (overflow, WCAG contrast, tap targets,
  labels, alt, heading order) across every page × role × theme × width, with a
  reviewed baseline so runs report only what is new. The contrast checker now
  alpha-composites backgrounds; the old "ratio 1" false positives are gone.
- **Login/registration modal** (`#authDlg`) and **install banner** (`#a2hs`,
  phones only) — on master.
- **Redesign, branch `redesign`** — Shape's structure in QMT's colours:
  floating dark-glass topbar pill; pill buttons everywhere; radius scale
  28/20/12 (`--r-xl/--r-lg/--r-md`); landing rebuilt (kicker, centred hero,
  photo stage with on-photo chips, italic uppercase service titles); cjenik
  with a raised "Najpopularnije" grupni card; owned plans and memberships marked
  by tinted borders instead of inset bars; page headers unified (`main > h1`);
  `--accent-tint-ink` for accent text on the accent tint (chips now clear AA).
  Verified: 90 tests, 0 overflow, 0 new audit findings, screenshots at 1280 and
  390 in both themes.

## Next up

1. **Owner reviews the redesign** on the branch (or a Railway preview) and says
   merge / change. The only photo asset (`static/gallery/dvorana-1.jpg`) has a
   wall print in its upper third — the crop hides it, but real hero photography
   from the owner would lift the landing more than any CSS.
2. Owner writes landing/service copy and records videos (his explicit wish —
   don't draft copy for him beyond placeholders).
3. **Stripe go-live** (owner): the d.o.o.'s Stripe account, real prices, the
   accountant's Fiskalizacija 2.0 flow. Switching accounts means clearing
   `stripe_customer_id` / `stripe_subscription_id` on users (sandbox ids are
   meaningless in the live account). Sandbox is fully verified on prod:
   prices, checkout, webhook, tier switch 12→16→12.
4. Pricing questions parked: the QMT + mojimakrosi bundle and the Prehrana
   plan (needs an entitlement bridge between the two apps).

## Testing the whole pipeline on prod

1. As owner, open **Online treninzi** once — creates the nine programme slots.
2. Sign up with an unused allowlist alias (`tvrtko.doresic+qmt1/2/3@gmail.com`),
   verify by email (owner gets the "Novi korisnik" notice).
3. Login → profile form → landing. Online tab appears only after an Online
   uplata on /clanarine; upitnik then routes to the matched programme.
4. Reminders: `python scripts/send_reminders.py` on Railway forces a pass;
   check the `reminders` table for claims.
5. Stripe sandbox: /cjenik → Pretplati se → card 4242… → webhook 200 →
   `payments` row with `method="stripe"`; /placanje/portal for the tier switch.

## Notes for the next session

- Croatian UI; the owner writes the copy — don't polish text.
- Verify UI in a real browser (Playwright) at 390px; one screenshot per message.
- Run `python .claude/skills/qmt-design/scripts/audit.py` before calling any UI
  work done; `--save-baseline` only after a deliberate review, and say why in
  the commit.
