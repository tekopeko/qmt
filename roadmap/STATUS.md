# Where the last session left off — 6.10.2026.

Read `CLAUDE.md` first; this file only carries what isn't obvious from the code.

## 5.10.2026 — the redesign is live; work continues on `master`

`redesign` was merged into `master` (one merge commit, so the whole redesign
reverts with `git revert -m 1 <merge>`) and deployed. There is no long-lived
branch any more: work happens on `master`, and every push deploys.

Same day, first fix on master: as owner on any window wider than 1200px the
avatar stuck out of the topbar pill (eight tabs + the full wordmark need 1086px,
the pill offers 1076). The wordmark now follows the room the tabs leave (a
container query on `.brand-slot`), bars with seven or more tabs run tight, and
the audit checks the pill itself.

6.10.2026 (built 5.10.), deployed: the homepage answers "what do you offer and what does it cost":
the six service cards became **three offer cards with prices** (Online /
Dvorana / Individualno, MojiMakrosi as an add-on: 5 € beside online, 3 € beside
a plan in the dvorana; the online plan includes a monthly Zoom call or a
meeting in person). The hero photo lost its service chips and is a link to the
cards. **Prices are public again** — the owner's call, reversing 28.9.; the
legal question behind that rule was not re-examined here, and
`PUBLIC_PRICES=off` is the one-variable way back. Card titles and copy are
placeholders for the owner to rewrite.

6.10., second change: the guest's bar is Shape's small pill (brand · Što
nudimo in red · Prijava · Kontakt in dark), and the hero lost its buttons and
the "Već imaš račun?" line — the pill carries those now.

And the phone check became a hook: the audit walks 360px as well as 390px
(which at once found two overflows live on prod — the membership table on
/raspored and the contact email on the landing, both fixed), has a ~30 s
`--phone` mode, and a Stop hook runs it whenever UI files changed.

Also new, and only about how Claude works here: delegation to an Opus 5.5
worker sits behind the `QMT_DELEGATE` flag (off by default) — see "Models" in
`CLAUDE.md`.

## 28.9.2026 — prices members-only, registration closed (deployed)

On legal advice the owner received (public prices would need the prior price
shown beside them, the way shop shelves do), `/cjenik` became members-only and
registration closed. Guests see no price, no Cjenik tab and no "Registriraj
se"; service cards say "Javi nam se" → `#kontakt`. Existing accounts log in as
always. The switch is `SIGNUP_MODE` (unset = closed); it replaced `SIGNUP_OPEN`.
To show prices publicly again the cjenik needs the prior-price display first.
The owner's Shopify shop, where the reference prices came from, is outside
this app and still shows them publicly.

## Deploy state

`master` is deployed (Railway auto-deploys on push) and carries everything:
the Shape-club-style redesign, the 28.9. hotfix, the login modal and the
install banner. 91 tests green.

## What this session shipped (25.9.)

- **`qmt-design` skill** (`.claude/skills/qmt-design/`): SKILL.md, generated
  `tokens.md`, the component catalog, borrowed patterns from shapeclub.app, and
  `scripts/audit.py` — a measured audit (overflow, WCAG contrast, tap targets,
  labels, alt, heading order) across every page × role × theme × width, with a
  reviewed baseline so runs report only what is new. The contrast checker now
  alpha-composites backgrounds; the old "ratio 1" false positives are gone.
- **Login/registration modal** (`#authDlg`) and **install banner** (`#a2hs`,
  phones only) — on master.
- **Redesign** (built on a branch, merged 5.10.) — Shape's structure in QMT's colours:
  floating dark-glass topbar pill; pill buttons everywhere; radius scale
  28/20/12 (`--r-xl/--r-lg/--r-md`); landing rebuilt (kicker, centred hero,
  photo stage with on-photo chips, italic uppercase service titles); cjenik
  with a raised "Najpopularnije" grupni card; owned plans and memberships marked
  by tinted borders instead of inset bars; page headers unified (`main > h1`);
  `--accent-tint-ink` for accent text on the accent tint (chips now clear AA).
  Verified: 90 tests, 0 overflow, 0 new audit findings, screenshots at 1280 and
  390 in both themes.

## Next up

1. **Hero photography from the owner.** The only photo asset
   (`static/gallery/dvorana-1.jpg`) has a wall print in its upper third — the
   crop hides it, but real photos would lift the landing more than any CSS.
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
2. Registration is closed while `SIGNUP_MODE` is unset. To test it, set
   `SIGNUP_MODE=invite` on Railway, sign up with an unused allowlist alias
   (`tvrtko.doresic+qmt1/2/3@gmail.com`), verify by email (owner gets the "Novi
   korisnik" notice), then unset it again.
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
