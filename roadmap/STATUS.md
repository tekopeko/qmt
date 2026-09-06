# Where the last session left off — 6.9.2026.

Read `CLAUDE.md` first; this file only carries what isn't obvious from the code.

## Deploy state

Everything is committed and pushed to `master` (auto-deploys to Railway).
83 tests green. Migrations apply automatically on deploy; the newest are
`b7e2c94d15a8` (reminders ledger) and `c9f3a1d7e2b4` (Stripe links).

The 4.9. header complaint is resolved: the avatar menu was rebuilt on the
YouTube pattern (icon gutter, ellipsized email, CSS-swapped theme icon) and the
owner has since moved on to reviewing other screens.

## What this session shipped (4.–5.9.)

- **Karton redesign**: upitnik block tinted by razina (zelena/jantar/crvena),
  dnevnik holds EVERY past termin (osvrt / "Nisam bio/la" apsence / otkazan /
  still open), osvrti are editable in place, rail shows only Nadolazeći.
- **Post-login prompts**: osvrt modal once per login; generic `data-confirm`
  dialog now guards every destructive form (native `confirm()` is gone).
- **Flow rework**: hero CTAs follow membership (no "Rezerviraj termin" for
  people who can't book), Cjenik in the nav for clients/guests, plan-gate
  booking error links to that plan's price, logout lands on `/`.
- **`SIGNUP_OPEN` env switch**: registration opens ONLY via this flag —
  clearing `ALLOWED_EMAILS` closes signup, it never opens it. Unset in prod.
- **Email reminders** (`src/qmt/reminders.py`): članarina pre-dospijeće +
  day-before termin emails; claim-idempotent via the `reminders` table; runs
  in-process every 6 h (app lifespan) and via `scripts/send_reminders.py`.
  Needs only `RESEND_API_KEY` — already set in prod.
- **R2 media storage** (`src/qmt/storage.py`): set the four `R2_*` vars and
  uploads go to Cloudflare R2, `/media` redirects to presigned URLs. Local
  disk stays the default. `scripts/migrate_media_to_r2.py` copies existing
  files. (Activated in prod on 6.9. — see below.)
- **Design pass** (measured, Playwright): WCAG-AA button fill (`--accent-fill`),
  0 unlabelled controls, 0 overflow, touch-size small buttons, no underlined
  links, no small-button glow, aligned card internals on landing + cjenik.

## 6.9. — R2 live, Stripe built

- **R2 is ACTIVE in prod** (owner's bucket `qmt-media`, scoped token). Verified
  end to end: upload → bucket, `/media` → 307 presigned, delete → gone. The
  test fixture blanks `R2_ACCOUNT_ID` so the suite never touches the bucket.
- **Stripe subscriptions are built and dormant** (`src/qmt/payments.py`,
  migration `c9f3a1d7e2b4`): `/cjenik` → `POST /placanje/{plan}` → Checkout
  (subscription mode, user+plan in subscription metadata) → signed
  `invoice.paid` webhook → `db.record_payment(method="stripe")`;
  `subscription.updated/deleted` track cancellation; `/placanje/portal` opens
  Stripe's portal. Access is granted ONLY by the webhook; invoice ids are
  unique in the ledger so redeliveries are no-ops. Nine tests, real signed
  payloads. Both invoice shapes (pre/post 2025 API) are read.

## Next up (agreed with the owner)

1. **Stripe test-mode run**: the owner (or Tvrtko, for now) creates a free
   Stripe account, makes six Products with monthly EUR Prices, a webhook
   endpoint (`invoice.paid`, `customer.subscription.updated`,
   `customer.subscription.deleted`) and enables the Customer portal; sets
   `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_*` on Railway
   (see DEPLOY.md). Then a full run with card 4242… on prod.
2. **Go-live blockers (owner)**: the d.o.o.'s Stripe account, real prices, and
   the accountant's Fiskalizacija 2.0 flow (fiscalized račun per B2C charge —
   the ledger has amount, date and invoice id for it). Nothing in code waits
   on these; live keys replace test keys.
3. Owner writes landing/service copy and records videos (his explicit wish —
   don't draft copy for him beyond placeholders).

## Testing the whole pipeline on prod

1. As owner, open **Online treninzi** once — creates the nine programme slots.
2. Sign up with an unused allowlist alias (`tvrtko.doresic+qmt1/2/3@gmail.com`),
   verify by email (owner gets the "Novi korisnik" notice).
3. Login → profile form → landing. Online tab appears only after an Online
   uplata on /clanarine; upitnik then routes to the matched programme.
4. Reminders: `python scripts/send_reminders.py` on Railway forces a pass;
   check the `reminders` table for claims.

## Notes for the next session

- Croatian UI; verify UI work in a real browser (Playwright) at 390px too.
- One screenshot per message — oversized images poison later ones.
- The design-audit script lives at the scratchpad but is easy to rebuild: it
  measures overflow, WCAG contrast, tap targets, labels, alt text and heading
  order across all pages/roles/themes. "ratio 1" findings on tinted elements
  are false positives (semi-transparent backgrounds read as solid).
