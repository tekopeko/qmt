#!/usr/bin/env bash
# Streams a plain-SQL dump (.sql.gz) into one of the webhost box's databases:
#
#   infra/restore.sh <host> <qmt|mojimakrosi> <dump.sql.gz> [--force] [--dry-run]
#
# For the cutover (the final Railway dumps: infra/README.md) and for a bad day
# (a nightly dump from /opt/backups or the backups bucket). Both kinds are
# pg_dump --no-owner --no-privileges, gzipped: what scripts/backup_db.py (the
# laptop, Railway) and infra/backup.sh (the box) write.
#
# psql runs AS THE APP'S ROLE (qmt or mojimakrosi), so every restored object
# belongs to the app, and in ONE transaction that stops at the first error,
# so a failed restore leaves the database as it found it.
#
# Refuses a database that already has tables. --force empties it first: the
# database is dropped and created again, owned by its role. Either way the
# app's container is stopped for the restore and started after it (start.sh
# then runs alembic upgrade head: a dump older than the code is migrated
# forward). The box must have been deployed once (infra/deploy.sh): the db
# service and the compose file must be there.
#
# --dry-run checks the dump and prints the ssh commands instead of running them.
# Written for macOS's bash 3.2.
set -euo pipefail

usage() {
  echo "usage: infra/restore.sh <host> <qmt|mojimakrosi> <dump.sql.gz> [--force] [--dry-run]" >&2
  exit 2
}

FORCE=0
DRY_RUN=0
HOST=""
DB=""
DUMP=""
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage ;;
    -*) echo "unknown option: $arg" >&2; usage ;;
    *)
      if [[ -z "$HOST" ]]; then HOST="$arg"
      elif [[ -z "$DB" ]]; then DB="$arg"
      elif [[ -z "$DUMP" ]]; then DUMP="$arg"
      else usage
      fi ;;
  esac
done
[[ -n "$DUMP" ]] || usage
# The compose service, the role and the database share the name.
case "$DB" in
  qmt|mojimakrosi) ;;
  *) echo "the database is qmt or mojimakrosi, not ${DB}" >&2; usage ;;
esac

say()  { printf '==> %s\n' "$*"; }
die()  { printf '!! %s\n' "$*" >&2; exit 1; }

# As in deploy.sh: <script> runs with bash on the box as root, $1... its
# arguments; a dry run prints it.
remote() {
  local script="$1" args=""
  shift
  if [[ $# -gt 0 ]]; then args="$(printf ' %q' "$@")"; fi
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '+ ssh -n root@%s bash -c <<script>> remote%s\n' "$HOST" "$args"
    printf '%s\n' "$script" | sed -e '/^$/d' -e 's/^/      | /'
    return 0
  fi
  ssh -n "root@${HOST}" "bash -c $(printf '%q' "$script") remote${args}"
}

# ---------------------------------------------------------------- the dump

[[ -f "$DUMP" && -r "$DUMP" ]] || die "no readable file at ${DUMP}"
case "$DUMP" in
  *.json.gz) die "${DUMP} is mojimakrosi's JSON fallback dump (made without a pg_dump 18), not SQL: psql cannot load it. Take a pg_dump one." ;;
  *.sql.gz) ;;
  *) die "${DUMP}: expected a gzipped plain-SQL dump, *.sql.gz" ;;
esac
gzip -t "$DUMP" 2>/dev/null || die "${DUMP} is not a valid gzip file (truncated download?)"
HEAD="$(gzip -dc "$DUMP" 2>/dev/null | head -c 4096 || true)"
[[ "$HEAD" == *"PostgreSQL database dump"* ]] || die "${DUMP} does not start like a pg_dump plain-SQL dump"
FROM="$(printf '%s\n' "$HEAD" | grep -m 1 'Dumped from database version' | sed 's/^-- //' || true)"
say "${DUMP}: $(wc -c <"$DUMP" | tr -d ' ') bytes gzipped; ${FROM:-server version not stated}"

# ---------------------------------------------------------------- the box's side

IFS= read -r -d '' REMOTE_STATE <<'SH' || true
set -uo pipefail
db="$1"
cd /opt/webhost 2>/dev/null && [ -f docker-compose.yml ] || { echo "no /opt/webhost/docker-compose.yml on the box: deploy once first (infra/deploy.sh)" >&2; exit 3; }
[ -n "$(docker compose ps --status running -q db 2>/dev/null)" ] || { echo "the db service is not running (cd /opt/webhost && docker compose up -d db)" >&2; exit 3; }
q() { docker compose exec -T db psql -U postgres -X -tA -v ON_ERROR_STOP=1 "$@"; }
exists="$(q -d postgres -v db="$db" <<<"select count(*) from pg_database where datname = :'db'")" || exit 3
tables=0
if [ "$exists" = 1 ]; then
  tables="$(q -d "$db" <<<"select count(*) from pg_tables where schemaname not in ('pg_catalog', 'information_schema')")" || exit 3
fi
echo "$exists $tables"
SH

IFS= read -r -d '' REMOTE_PREPARE <<'SH' || true
set -euo pipefail
db="$1"
recreate="$2"
cd /opt/webhost
docker compose stop "$db"
if [ "$recreate" = 1 ]; then
  docker compose exec -T db psql -U postgres -X -q -v ON_ERROR_STOP=1 -v db="$db" -d postgres <<'SQL'
DROP DATABASE IF EXISTS :"db" WITH (FORCE);
CREATE DATABASE :"db" OWNER :"db";
REVOKE CONNECT, TEMPORARY ON DATABASE :"db" FROM PUBLIC;
SQL
  echo "database ${db}: (re)created empty, owned by ${db}"
fi
SH

# The dump arrives on stdin (gzipped over the wire, unpacked on the box).
# Query output (set_config, setval) goes to /dev/null; errors stay on stderr.
IFS= read -r -d '' REMOTE_LOAD <<'SH' || true
set -euo pipefail
db="$1"
cd /opt/webhost
gunzip -c | docker compose exec -T db psql -U "$db" -d "$db" -X -q -v ON_ERROR_STOP=1 --single-transaction >/dev/null
echo "database ${db}: the dump is in"
SH

IFS= read -r -d '' REMOTE_FINISH <<'SH' || true
set -uo pipefail
db="$1"
cd /opt/webhost
q() { docker compose exec -T db psql -U postgres -X -tA -d "$db" "$@"; }
echo "tables: $(q <<<"select count(*) from pg_tables where schemaname not in ('pg_catalog', 'information_schema')")"
echo "alembic_version: $(q <<<"select version_num from alembic_version" 2>/dev/null || echo none)"
q <<<"analyze" >/dev/null
if [ -z "$(docker compose ps -a -q "$db" 2>/dev/null)" ]; then
  echo "${db}: no container yet; deploy it next (infra/deploy.sh <host> ${db})"
  exit 0
fi
docker compose up -d --no-build "$db"
s=""
for i in $(seq 1 48); do
  s="$(docker inspect --format "{{.State.Health.Status}}" "$(docker compose ps -q "$db")" 2>/dev/null || true)"
  if [ "$s" = healthy ]; then echo "${db}: started again, healthy (alembic upgrade head ran first)"; exit 0; fi
  sleep 5
done
echo "${db}: started, but not healthy after 4 min (${s:-no status}): docker compose logs ${db}"
exit 1
SH

# ---------------------------------------------------------------- run

say "Restoring into ${DB} on root@${HOST}$([[ "$DRY_RUN" == 1 ]] && echo ' (DRY RUN: nothing runs on the box)')"
if [[ "$DRY_RUN" == 1 ]]; then
  remote "$REMOTE_STATE" "$DB"
  say "(the box answers \"<database exists 0|1> <tables>\"; more than 0 tables without --force stops here)"
  recreate=1
else
  state="$(remote "$REMOTE_STATE" "$DB")" || die "could not read the database's state on ${HOST} (see above)"
  exists="${state%% *}"
  tables="${state##* }"
  if [[ "$tables" != 0 && "$FORCE" != 1 ]]; then
    die "${DB} on ${HOST} already has ${tables} tables: refusing (--force drops the database and creates it empty first)"
  fi
  recreate=0
  if [[ "$FORCE" == 1 || "$exists" != 1 ]]; then recreate=1; fi
fi

say "Stopping ${DB}'s app$([[ "$recreate" == 1 ]] && echo ", dropping and creating the database ${DB}")"
remote "$REMOTE_PREPARE" "$DB" "$recreate"

say "Streaming the dump into ${DB} (as role ${DB}, one transaction)"
if [[ "$DRY_RUN" == 1 ]]; then
  printf '+ ssh root@%s bash -c <<script>> remote %q < %q\n' "$HOST" "$DB" "$DUMP"
  printf '%s\n' "$REMOTE_LOAD" | sed -e '/^$/d' -e 's/^/      | /'
else
  ssh "root@${HOST}" "bash -c $(printf '%q' "$REMOTE_LOAD") remote $(printf '%q' "$DB")" <"$DUMP" \
    || die "the restore failed and was rolled back; ${DB} is empty and its app stopped. Fix the cause and run this again."
fi

say "Checking and starting ${DB}'s app again"
remote "$REMOTE_FINISH" "$DB"
