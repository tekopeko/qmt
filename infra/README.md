# infra/: the webhost box (QMT + mojimakrosi on Scaleway)

**Status, 23.10.2026: a draft awaiting review. Nothing is provisioned yet;
Railway still serves both sites until the cutover below.**

One Scaleway instance runs **both** web apps: QMT (this repo,
`qmt.mojimakrosi.com`) and mojimakrosi (`../macro_tracker`,
`mojimakrosi.com`). It is provisioned and run exactly the way the trader
dashboard is (Terraform + cloud-init, Docker Compose, Caddy, nightly backups to
Object Storage; see `trader/infra/`), but it is never the trader's box. The
owner's decision of 23.10.2026, after Railway's multi-day outage and the breach
in which customers' environment variables were read: "Lets move to scaleway …
since I already host a page trader there already."

This directory lives in QMT's repo and serves both apps: mojimakrosi's code
is rsynced to the box from its own checkout, `../macro_tracker` (`MM_ROOT`
overrides the path).

## What runs where

    Cloudflare (all three names proxied, the zone's SSL mode Full (strict))
      -> the box, Caddy on :80/:443 (Let's Encrypt certificates, HTTP-01)
           qmt.mojimakrosi.com  -> 127.0.0.1:8001 -> container qmt :8000
           mojimakrosi.com      -> 127.0.0.1:8002 -> container mojimakrosi :8000
           www.mojimakrosi.com  -> 308 redirect to https://mojimakrosi.com
         Postgres 18 (container db, no published port): roles and databases
           qmt and mojimakrosi, each owning its own

| In the repo | What it is | On the box |
|---|---|---|
| `terraform/` | the instance (`DEV1-S`, Ubuntu 24.04, 20 GB, tag `webhost`), a reserved IP, a security group (inbound 22/80/443 only), the SSH key, the backups bucket `teko-webhost-backups` (private, objects expire after 30 days) | |
| `terraform/cloud-init.yaml.tftpl` | first boot: Docker and Caddy from their official repos, the Caddyfile, ufw 22/80/443, unattended-upgrades, awscli v2, the backup cron (03:17 UTC) and the autoheal cron (every minute: restart what a healthcheck calls unhealthy) | `/etc/caddy/Caddyfile`, `/etc/cron.d/webhost-backup`, `/etc/cron.d/webhost-autoheal` |
| `compose/docker-compose.yml` | `db` (postgres:18, volume `pgdata`), `qmt` (512m), `mojimakrosi` (768m), healthchecks on `/healthz`, capped logs | `/opt/webhost/docker-compose.yml` |
| `compose/initdb/01-roles.sh` | creates the two roles and databases, once, when `pgdata` is empty | `/opt/webhost/initdb/` |
| `env/*.env.example` | templates; the real `db.env`, `qmt.env`, `mojimakrosi.env` are gitignored | `/opt/webhost/*.env` (600) |
| `deploy.sh` | the deploy, from the laptop | |
| `backup.sh` | the nightly dumps | `/opt/backups/backup.sh` |
| `restore.sh` | a dump into an empty database, from the laptop | |

The Scaleway account and project are the trader's for now (the same API key
runs Terraform). A separate project for this box is a later option: it would
also keep this box's backup key away from the trader's buckets.

## First-time provisioning

1. **Terraform** (local state; `terraform/.gitignore` keeps it out of git).
   The trader's `infra/.env` exports what it needs (`SCW_ACCESS_KEY`,
   `SCW_SECRET_KEY`, `SCW_DEFAULT_PROJECT_ID`):

       cd infra/terraform
       source ../../../trader/infra/.env      # this shell only
       terraform init
       terraform plan                          # 5 to add, 0 to change, 0 to destroy
       terraform apply
       terraform output                        # instance_public_ip, ssh_command

   The trader's box registered the same `~/.ssh/id_ed25519.pub` in this
   project. Should Scaleway refuse a second copy of it (not verified), the
   apply stops at `scaleway_iam_ssh_key.webhost`: the box gets the key
   anyway (Scaleway injects every key of the project at first boot), so the
   way on is to drop that resource or to point `ssh_public_key_path` at
   another key (a choice left to the review, not made here).

   Keep `terraform.tfstate`: it is the only record of what exists. The IP and
   the server carry `prevent_destroy`.

2. **Wait for cloud-init** (the first ssh also records the host key):

       ssh root@<ip> cloud-init status --wait
       ssh root@<ip> 'docker compose version; caddy version; aws --version; ufw status'

3. **The env files.** Railway's variables were read in the breach: every
   secret is a NEW one (revoke the old keys at Resend, Cloudflare R2, OpenAI,
   Anthropic, Turnstile). New `SECRET_KEY`s log everyone out once.

       cd infra/env
       cp db.env.example db.env; cp qmt.env.example qmt.env; cp mojimakrosi.env.example mojimakrosi.env
       chmod 600 *.env

   `db.env`: three values from `openssl rand -hex 24`. Each app's
   `DATABASE_URL` carries its role's password from `db.env`
   (`postgresql+psycopg://qmt:<QMT_DB_PASSWORD>@db:5432/qmt`, the
   `+psycopg` both apps' configs want). The comments in each template say
   what each key is; `deploy.sh` refuses to ship an empty required value, a
   `SECRET_KEY` under 32 characters, an `ENV` other than `production`, or a
   `DATABASE_URL` that does not match `db.env`.

4. **The backup key.** Scaleway console → IAM → Applications: a new
   application (`webhost-backup`) with Object Storage rights in the project
   (the trader's backup key has ObjectStorageFullAccess; in a shared project
   it reaches the trader's buckets too), never the Terraform key; an API key
   for it. On the box, `/opt/backups/s3.env`, mode 600, two lines:

       AWS_ACCESS_KEY_ID=<its access key>
       AWS_SECRET_ACCESS_KEY=<its secret key>

   (`ssh -t root@<ip> 'umask 077; cat > /opt/backups/s3.env'`, paste,
   Ctrl-D: nothing lands in the shell history.) Without it the dumps stay on
   the box and the log says so.

5. **The first deploy** (both checkouts committed and clean):

       infra/deploy.sh <ip> all --dry-run      # read what it will do
       infra/deploy.sh <ip> all

   Both apps start on empty databases (alembic creates the schema) and must
   report healthy. Caddy cannot get certificates yet (the names still point
   at Railway); look through a tunnel instead:

       ssh -L 8001:127.0.0.1:8001 -L 8002:127.0.0.1:8002 root@<ip>
       curl http://127.0.0.1:8001/healthz; curl http://127.0.0.1:8002/healthz

## Cloudflare (mojimakrosi.com zone)

Three records, all **Proxied** (orange cloud), set at the cutover (step 4
below), not before:

| Type | Name | Content |
|---|---|---|
| A | `qmt` | the box's IP |
| A | `@` (mojimakrosi.com) | the box's IP |
| A | `www` | the box's IP |

They replace what points at Railway today (delete the old record, add the A
record; behind the proxy the switch takes seconds).

SSL/TLS → encryption mode **Full (strict)**. Caddy gets each name's Let's
Encrypt certificate with the HTTP-01 challenge **through the proxy**: in the
Full modes Cloudflare reaches the origin over the visitor's scheme, so
Let's Encrypt's `http://…/.well-known/acme-challenge/` request lands on
Caddy's port 80. Full (strict) then makes Cloudflare check that certificate.
Should issuance fail (a Cloudflare redirect rule, or "Always Use HTTPS",
sending the challenge to https before a certificate exists), set the three
records to DNS only for the minute it takes, then back to Proxied.

## Cutover from Railway

The order: final dump on Railway → restore → DNS → smoke test → keep Railway
a week.

1. **Freeze Railway.** Stop the two app services (not their databases), and
   make sure nothing starts them again: disconnect QMT's GitHub auto-deploy
   (a push to `master` would bring it back), and run no more of
   mojimakrosi's `scripts/deploy.sh` (`railway up`). After the final dump,
   any write on Railway is lost, and a running Railway QMT would keep
   sending its reminder emails from its own copy of the data.
2. **The final dumps**, from the laptop, with pg_dump 18 and the same flags
   the restore expects (`--no-owner --no-privileges`):

       # QMT: its database has no public address; the tunnel, as
       # scripts/backup_db.py opens it (the Railway CLI logged in and linked here)
       cd ~/Documents/GIT/qmt
       railway connect Postgres --tunnel-only --port 6543 &
       env $(railway variables --service Postgres --kv | grep -E '^PG(USER|PASSWORD|DATABASE)=') \
         /opt/homebrew/opt/postgresql@18/bin/pg_dump -h 127.0.0.1 -p 6543 --no-owner --no-privileges \
         | gzip > ~/qmt-final.sql.gz
       kill %1

       # mojimakrosi: PROD_DATABASE_URL in ../macro_tracker/.env, without "+psycopg"
       /opt/homebrew/opt/postgresql@18/bin/pg_dump --no-owner --no-privileges "<that URL>" \
         | gzip > ~/mojimakrosi-final.sql.gz

   (The laptop's nightly jobs have failed since 22.10.2026 and are no
   source for this: their last good dumps in R2 are from 21.10.)
3. **Restore** (`--force`: the first deploy migrated empty databases). Each
   run stops the app, recreates its database, loads the dump as the app's
   role in one transaction, and starts the app again (`alembic upgrade
   head` brings an older dump up to the code):

       infra/restore.sh <ip> qmt ~/qmt-final.sql.gz --force
       infra/restore.sh <ip> mojimakrosi ~/mojimakrosi-final.sql.gz --force

4. **DNS**: the three records above. Then make Caddy try at once (it backs
   off while the names pointed elsewhere) and watch it get the three
   certificates:

       ssh root@<ip> systemctl restart caddy
       ssh root@<ip> journalctl -u caddy -f      # "certificate obtained successfully" x3

5. **Smoke test.** QMT: the landing, log in, book a termin and cancel it, the
   trainer's roster, an upload (it must land in R2: the containers keep
   nothing), `/moja-clanarina`, a password-reset email (Resend). mojimakrosi:
   log in, add an entry (OpenAI), a photo (R2, served from `R2_PUBLIC_URL`),
   a password-reset email whose link is `https://`. `www.mojimakrosi.com`
   redirects to the apex.
6. **Keep Railway a week**: the services stopped, the databases kept. The
   way back is to start them and point the records at Railway again (data
   written on the box meanwhile would then need a dump the other way).
   Then delete the Railway projects.
7. **Retire the laptop backups** (they can only reach Railway):

       launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.qmt.backup.plist
       launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.mojimakrosi.backup.plist

   and move the two plists out of `~/Library/LaunchAgents` (or they load
   again at the next login). The dumps already in R2 stay as the pre-move
   history.
8. **The next morning**: `ssh root@<ip> 'tail -n 20 /opt/backups/backup.log'`
   shows two dumps and two off-site copies.
9. **The docs**: drop the "not live yet" lines in this file, DEPLOY.md,
   CLAUDE.md ("Deployment") and roadmap/STATUS.md.

## Day to day

- **Deploy**: `infra/deploy.sh <ip> qmt` (or `mojimakrosi`, or `all`).
  Nothing deploys on a push. It refuses a dirty tree (`DEPLOY_ALLOW_DIRTY=1`),
  waits up to 4 minutes for `healthy` and rolls back to the previous image
  when it does not get there. A rollback cannot undo a migration the new
  version ran: the old code then fails on the newer schema, and the way out
  is a fix forward or last night's dump. QMT's test suite is not run by the
  script (it is the review gate before each commit; `DEPLOY_QMT_TESTS=1`
  runs it); mojimakrosi's would be, but it has no tests.
- **Logs**: `ssh root@<ip> 'cd /opt/webhost && docker compose logs -f --tail 100 qmt'`.
- **psql**: `ssh -t root@<ip> 'cd /opt/webhost && docker compose exec db psql -U qmt qmt'`.
- **One-off scripts** (the images carry no `scripts/`; the synced checkout does):

      ssh root@<ip> 'cd /opt/webhost && docker compose exec -T qmt python - trener@example.com < qmt/scripts/make_trainer.py'
      ssh root@<ip> 'cd /opt/webhost && docker compose exec -T qmt python - < qmt/scripts/send_reminders.py'

- **Backups**: `ssh root@<ip> 'tail -n 20 /opt/backups/backup.log; ls -lh /opt/backups'`.
  By hand: `ssh root@<ip> /opt/backups/backup.sh`. A failed night is
  emailed to `OWNER_EMAIL` through QMT's Resend sender. Pull one with
  `scp root@<ip>:/opt/backups/qmt-<stamp>.sql.gz .`, or from the bucket.
  Restore: `infra/restore.sh <ip> qmt qmt-<stamp>.sql.gz --force`.
- **Reboots**: unattended-upgrades installs security updates and never
  reboots. When `/var/run/reboot-required` exists, `ssh root@<ip> reboot` at
  a quiet hour: Docker and Caddy start on boot, the containers follow.
- **Caddy**: `/etc/caddy/Caddyfile` came from cloud-init once. Change it
  on the box (`systemctl reload caddy`) and in the template both.

## Changing a database password

`initdb/01-roles.sh` ran once; a new value in `db.env` changes nothing in the
database by itself. Set it in Postgres, then in both files, then deploy (the
container is recreated with the new `DATABASE_URL`):

    ssh -t root@<ip> 'cd /opt/webhost && docker compose exec db psql -U postgres'
    postgres=# \password qmt

then `QMT_DB_PASSWORD` in `env/db.env`, the password in `env/qmt.env`'s
`DATABASE_URL`, and `infra/deploy.sh <ip> qmt`.

## Later

- A separate Scaleway project (or the client's own account) for this box.
- The Terraform state in Object Storage, as the trader's (the block is in
  `terraform/versions.tf`).
- Ports 80/443 open to Cloudflare's address ranges only, so the box cannot
  be reached around the proxy.
- An uptime monitor, and a check that the nightly backup ran at all: the
  email only comes when the script runs and fails.
