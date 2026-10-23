# Deploy: Scaleway + qmt.mojimakrosi.com

**Status, 23.10.2026: drafted, not live.** Production still runs on Railway
until the cutover in [`infra/README.md`](infra/README.md) ("Cutover from
Railway"); the last section here is what Railway was.

## 1. Where it runs

One Scaleway instance (`webhost`: DEV1-S, Ubuntu 24.04, fr-par-1) runs QMT
**and** mojimakrosi, provisioned the way the trader dashboard is: Terraform +
cloud-init (`infra/terraform/`), Docker Compose (`infra/compose/`), Caddy in
front, nightly database dumps to Object Storage. Never on the trader's box.

    Cloudflare (proxied, SSL Full (strict))
      -> Caddy on the box (Let's Encrypt, HTTP-01 through the proxy)
           qmt.mojimakrosi.com -> 127.0.0.1:8001 -> the qmt container (:8000)
      Postgres 18 in the compose service db: database and role qmt

The image is this repo's `Dockerfile`; `start.sh` runs `alembic upgrade head`,
then uvicorn on `$PORT`; `/healthz` is the healthcheck. Provisioning, DNS,
the env files, the first deploy, the restore of the Railway dumps and the
cutover: `infra/README.md`.

## 2. Deploying a change

Nothing deploys on a push. From the laptop, with the change committed:

    infra/deploy.sh <ip> qmt              # --dry-run prints every step instead

It refuses a dirty tree (`DEPLOY_ALLOW_DIRTY=1` overrides) and an incomplete
env file, rsyncs the repo to `/opt/webhost/qmt/`, copies the env files (mode
600), keeps the running image as `:prev`, builds and starts the new one,
waits up to 4 minutes for `healthy` and rolls back to `:prev` when it never
gets there. A migration ships with its code (`start.sh`); a rollback cannot
undo one. The script does not re-run QMT's suite (the review gate runs
`pytest -q` before each commit; `DEPLOY_QMT_TESTS=1` runs it there too).

## 3. Variables: `infra/env/qmt.env` → `/opt/webhost/qmt.env`

The template is `infra/env/qmt.env.example`. Every secret is a new one:
Railway's variables were read in the October 2026 breach. Compose also sets
`FORWARDED_ALLOW_IPS=*` on the container (uvicorn then trusts Caddy's
`X-Forwarded-Proto`; the port is reachable from the box only).

| var | value |
|---|---|
| `ENV` | `production` (fixed in the template; `deploy.sh` refuses anything else) |
| `PORT` | `8000` (fixed: compose maps 127.0.0.1:8001 to it, the healthcheck probes it) |
| `SECRET_KEY` | `python3 -c "import secrets;print(secrets.token_hex(32))"` |
| `DATABASE_URL` | `postgresql+psycopg://qmt:<QMT_DB_PASSWORD>@db:5432/qmt`: the compose `db` service, the password `infra/env/db.env`'s (note the driver, `+psycopg`) |
| `OWNER_EMAIL` | the app owner's address (Tvrtko): controls roles and /korisnici |
| `ALLOWED_EMAILS` | first clients, comma-separated (owner's address too, for testing) |
| `SIGNUP_MODE` | `closed` (the default, also when unset or mistyped): no new accounts, and no page offers one. `invite`: the owner + `ALLOWED_EMAILS`. `open`: anyone. **Leave unset for now**: registration has stayed closed since 28.9.2026 |
| `PUBLIC_PRICES` | leave unset: guests see the offer's prices on the landing (the owner's decision of 5.10.2026). `off` hides every price from guests again — the 28.9. rule, no code change. `/cjenik` is members-only either way |
| `R2_ACCOUNT_ID` + `R2_ACCESS_KEY_ID` + `R2_SECRET_ACCESS_KEY` + `R2_BUCKET` | Cloudflare R2 media storage, all four together. Required on the box: the containers keep nothing across a deploy, so without them every upload is lost at the next one. `/media` serves via presigned URLs. The announcements' photos live in the same bucket (names `aktualno-*`), served publicly by `/slika`, which proxies the bytes |
| `CANCEL_CUTOFF_HOURS` | leave unset: a client may cancel a booking until 12 h before the termin (the default, the owner's call of 17.10.2026); a number of hours overrides it. A termin the trainer canceled can always be dropped. Booking itself stays open until the termin starts, up to `BOOKING_HORIZON_DAYS` (default 28) ahead |
| `REMINDER_DAYS_BEFORE` | days before dospijeće the članarina email goes out (default 3). Reminders run in-process every 6 h; `docker compose exec -T qmt python - < qmt/scripts/send_reminders.py` (in `/opt/webhost`) forces a pass |
| `MAX_MEDIA_MB` | largest media upload, default 60 |
| `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` | switch card subscriptions on. Test-mode keys work end to end (card `4242 4242 4242 4242`). **18.10.2026: the six test variables were removed from Railway** (the owner's call) so every price on the site is the owner's text (the price slots; the code prints only them since that day, keys or not). Leave them out of `qmt.env` until go-live; adding them switches checkout back on, and the Prices must then be aligned to the slots first: checkout charges the Price, the site shows the slot |
| `STRIPE_PRICE_<PLAN>` | one recurring **monthly** Price id per flat plan (`INDIVIDUALNI`, `POLUINDIVIDUALNI`, `REHABILITACIJA`, `ONLINE`, `PREHRANA`). A plan without one keeps the cash-only path. Online is tiered since 20.10.2026 (QMove START / PRO / ELITE, `Membership.tier`), but `STRIPE_PRICE_ONLINE` is one flat Price: a card subscription records START. **Before go-live online needs three Prices, one per tier**, as grupni has three (below), and the code that maps them, as `STRIPE_TIER_PRICES` maps grupni's |
| `STRIPE_PRICE_GRUPNI_8` / `_12` / `_16` | grupni is tiered like the shop — one monthly Price per tier (60/70/80 € as of 6.9.2026). Booking counts against the tier's quota per cycle |
| `PUBLIC_BASE_URL` | `https://qmt.mojimakrosi.com` |
| `RESEND_API_KEY` | existing Resend account (a new key) |
| `EMAIL_FROM` | `QMT <qmt@mojimakrosi.com>` (mojimakrosi.com is already a verified Resend domain) |
| `MOJIMAKROSI_URL` | `https://mojimakrosi.com` (the default) |

## 4. DNS (Cloudflare, mojimakrosi.com zone)

`qmt` is an **A** record to the box's IP, **Proxied**; the zone's SSL/TLS mode
is **Full (strict)**. Caddy gets the certificate itself, with Let's Encrypt's
HTTP-01 challenge through the proxy (details and the fallback:
`infra/README.md`, "Cloudflare").

## 5. First boot on an empty database

Only for a fresh install; the cutover restores the existing database instead.

1. Open `https://qmt.mojimakrosi.com`: the landing should render.
2. Registration is closed by default, the owner's account too: set
   `SIGNUP_MODE=invite` in `qmt.env`, deploy, sign up with `OWNER_EMAIL`,
   click the verification email.
3. Grant the trainer (signup NEVER grants it):
   ```bash
   ssh root@<ip> 'cd /opt/webhost && docker compose exec -T qmt python - <trainer email> < qmt/scripts/make_trainer.py'
   ```
4. Trainer builds the real timetable in `/admin` (seed is dev-only and refuses prod).
   The texts on the landing, moja-clanarina and prehrana pages are edited in place: log
   in as the trainer, press "✎ Uredi tekstove" bottom right, click a text.
5. To take invited clients, keep `SIGNUP_MODE=invite` and add their emails to
   `ALLOWED_EMAILS` as they join; `SIGNUP_MODE=open` takes anyone; unset it to
   close again. The signup and login copy follow the switch on their own.

## 6. Backups

On the box, nightly at 03:17 UTC: `infra/backup.sh` (installed by every
deploy as `/opt/backups/backup.sh`) dumps both databases with `pg_dump
--no-owner --no-privileges` to `/opt/backups/<db>-<stamp>.sql.gz` (14 days),
refuses a dump under 2 KB, and copies each to the `teko-webhost-backups`
bucket (30 days) when `/opt/backups/s3.env` holds a storage-only key. A
failure is emailed to `OWNER_EMAIL` through QMT's Resend sender.

    ssh root@<ip> 'tail -n 20 /opt/backups/backup.log; ls -lh /opt/backups'
    scp root@<ip>:/opt/backups/qmt-<stamp>.sql.gz .
    infra/restore.sh <ip> qmt qmt-<stamp>.sql.gz --force    # into an empty database; --force empties it first

## 7. Post-deploy smoke test

login → book a session → cancel it → trainer sees roster → trainer creates a
programme with a photo → client sees it → photo survives a **redeploy** (proves
the media is in R2: the containers keep nothing).

## 8. Later: handover to the client's account

A Scaleway project (or account) of his → `terraform apply` there with its keys
→ the env files → `infra/deploy.sh` → `infra/restore.sh` the newest dump →
repoint the DNS (or move to his domain) → copy the R2 bucket if the media moves
too. Half a day, no code changes.

## Stripe setup (card subscriptions)

1. In the Stripe dashboard create the **Products**, each with a **recurring monthly
   Price** in EUR: one Product per flat plan, and for Grupni one Product with three
   Prices (8 / 12 / 16 treninga). Online is tiered as well since 20.10.2026 (QMove
   START / PRO / ELITE, the landing's cards): at go-live it needs one Product with
   three Prices, one per tier, and their mapping in the code (`config.py`,
   `payments._plan_from`); until then its one flat Price records START. Copy each
   Price id (`price_...`) into the matching
   `STRIPE_PRICE_<PLAN>` / `STRIPE_PRICE_GRUPNI_<N>`. Amounts: the price slots, what
   the site shows (the gym owner's text on the landing and `/moja-clanarina`, the one
   truth since 18.10.2026); their defaults are the owner's Shopify shop (grupni
   60/70/80, individualni 35/trening, poluindividualni 25/trening, online 50/mj, rehab
   from 30/tretman).
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

## Railway, until October 2026

QMT ran on Railway from its first deploy until the cutover: one project with
the app service (built from the `Dockerfile`, auto-deployed on every push to
`master`) and a PostgreSQL 18 service, behind
`qmt.mojimakrosi.com` as a Railway custom domain (a CNAME at Cloudflare). It
was left after the October 2026 outage and the breach in which customers'
environment variables were read (the owner's decision of 23.10.2026); every
secret it held is replaced in the new env files.

Its backups ran from the laptop: `scripts/backup_db.py` dumped the database
through a `railway connect Postgres --tunnel-only` SSH tunnel into the media
bucket under `qmt-backups/`, every morning at 07:10, from the LaunchAgent
`~/Library/LaunchAgents/com.qmt.backup.plist` (log
`~/Library/Logs/qmt-backup.log`); mojimakrosi's own `scripts/backup_db.py`
ran at 07:00 from `com.mojimakrosi.backup.plist`. Both only reach Railway,
so they retire at the cutover:

    launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.qmt.backup.plist
    launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.mojimakrosi.backup.plist

(then move the two plists out of `~/Library/LaunchAgents`, or they load again
at the next login). `scripts/backup_db.py` stays in the repo until then; the
dumps already in R2 stay as the pre-move history.
