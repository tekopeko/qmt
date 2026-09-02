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
5. Add client emails to `ALLOWED_EMAILS` as they join.

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
