# Deploy: Railway + qmt.mojimakrosi.com

Interim setup on the owner's Railway/domain; moving to the client's account later
is: new project → paste variables → repoint DNS. Nothing else is account-bound.

## 1. Railway (one-time)

1. **New project** (separate from mojimakrosi — its own bill, its own handover unit)
   → add **PostgreSQL**.
2. Add a service **from this GitHub repo** (push it first). Railway detects the
   Dockerfile; `start.sh` migrates then serves.
3. **Volume**: attach to the app service, mount path **`/app/data`**.
   Without it every redeploy DELETES all uploaded exercise media.
4. **Variables** on the app service:

   | var | value |
   |---|---|
   | `ENV` | `production` |
   | `SECRET_KEY` | `python3 -c "import secrets;print(secrets.token_hex(32))"` |
   | `DATABASE_URL` | reference the Railway Postgres (internal URL) — note driver: `postgresql+psycopg://` |
   | `OWNER_EMAIL` | the app owner's address (Tvrtko) — controls roles and /korisnici |
   | `ALLOWED_EMAILS` | first clients, comma-separated (owner's address too, for testing) |
   | `SIGNUP_OPEN` | unset while invite-only. `true` opens registration to anyone — clearing `ALLOWED_EMAILS` does **not**, it closes signup completely |
   | `R2_ACCOUNT_ID` + `R2_ACCESS_KEY_ID` + `R2_SECRET_ACCESS_KEY` + `R2_BUCKET` | Cloudflare R2 media storage — all four together move uploads off Railway's ephemeral disk; `/media` then serves via presigned URLs. After setting them run `python scripts/migrate_media_to_r2.py` once |
   | `REMINDER_DAYS_BEFORE` | days before dospijeće the članarina email goes out (default 3). Reminders run in-process every 6 h; `python scripts/send_reminders.py` forces a pass |
   | `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` | switch card subscriptions on. Test-mode keys work end to end (card `4242 4242 4242 4242`) |
   | `STRIPE_PRICE_<PLAN>` | one recurring **monthly** Price id per plan (`GRUPNI`, `INDIVIDUALNI`, `POLUINDIVIDUALNI`, `REHABILITACIJA`, `ONLINE`, `PREHRANA`). A plan without one keeps the cash-only path |
   | `PUBLIC_BASE_URL` | `https://qmt.mojimakrosi.com` |
   | `RESEND_API_KEY` | existing Resend account |
   | `EMAIL_FROM` | `QMT <qmt@mojimakrosi.com>` (mojimakrosi.com is already a verified Resend domain) |
   | `MOJIMAKROSI_URL` | `https://mojimakrosi.com` |

5. `/healthz` is the health check path.

## 2. DNS (Cloudflare, mojimakrosi.com zone)

Service → Settings → Networking → **Custom Domain** → `qmt.mojimakrosi.com`;
Railway shows a target → add **CNAME `qmt` → that target** in Cloudflare
(proxy ON is fine). Certificate is automatic.

## 3. First boot (order matters)

1. Open `https://qmt.mojimakrosi.com` — landing should render.
2. Owner **signs up** with `OWNER_EMAIL` → clicks the verification email.
3. Grant admin from the laptop (signup NEVER grants it):
   ```bash
   DATABASE_URL="<railway PUBLIC postgres url, +psycopg>" python scripts/make_trainer.py <trainer email>
   ```
4. Trainer builds the real timetable in `/admin` (seed is dev-only and refuses prod).
5. Add client emails to `ALLOWED_EMAILS` as they join. When the studio is ready
   to take anyone, set `SIGNUP_OPEN=true` — the signup and login copy drop the
   "samo uz poziv" line on their own.

## 4. Backups (from the laptop, like mojimakrosi's)

`.env` gets `QMT_PROD_DATABASE_URL` (Railway **public** URL) + the same `R2_*`
keys mojimakrosi uses; then:
```bash
python scripts/backup_db.py     # → r2://<bucket>/qmt-backups/, keeps 60
```
Schedule it alongside the mojimakrosi backup job.

## 5. Post-deploy smoke test

login → book a session → cancel it → trainer sees roster → trainer creates a
programme with a photo → client sees it → photo survives a **redeploy** (proves
the volume is mounted right).

## Later: handover to the client's account

New Railway project on his account → paste the same variables → repoint the
CNAME (or move to his domain) → `pg_dump | pg_restore` the database → copy the
volume contents. Half a day, no code changes.


## Stripe setup (card subscriptions)

1. In the Stripe dashboard create six **Products**, each with one **recurring monthly
   Price** in EUR. Copy each Price id (`price_...`) into the matching `STRIPE_PRICE_<PLAN>`.
2. **Developers → Webhooks → Add endpoint**: `https://<domain>/stripe/webhook`, events
   `invoice.paid`, `customer.subscription.updated`, `customer.subscription.deleted`.
   Copy the signing secret into `STRIPE_WEBHOOK_SECRET`.
3. **Settings → Billing → Customer portal**: enable it (cancel subscription, update
   payment method, invoice history) — `/placanje/portal` opens it.
4. Locally, `stripe listen --forward-to 127.0.0.1:8100/stripe/webhook` prints a
   `whsec_...` for `.env`.

Access is granted ONLY by the signed `invoice.paid` webhook (→ `db.record_payment`,
`method="stripe"`), never by the success redirect. Redelivered invoices are no-ops
(unique `payments.stripe_invoice_id`). A cancelled subscription keeps the month already
paid; the plan lapses on dospijeće like a cash one.

Before LIVE keys: the owner's Stripe account for the d.o.o., real prices, and the
accountant's Fiskalizacija 2.0 flow (a fiscalized račun per B2C charge — the `payments`
ledger carries amount, date, and the Stripe invoice id for it).
