#!/usr/bin/env bash
# Nightly dumps of the webhost box's two databases, QMT's and mojimakrosi's.
# Runs ON THE BOX: /etc/cron.d/webhost-backup at 03:17 UTC (cloud-init), or by
# hand as /opt/backups/backup.sh. infra/deploy.sh installs it there on every
# deploy, so this file in the repo is the only copy.
#
#   /opt/backups/<db>-<UTC stamp>.sql.gz
#       pg_dump --no-owner --no-privileges, gzipped: the format of the laptop's
#       Railway dumps, and what infra/restore.sh streams back. Kept 14 days.
#   s3://teko-webhost-backups/<db>/<db>-<UTC stamp>.sql.gz
#       when /opt/backups/s3.env (600) holds AWS_ACCESS_KEY_ID and
#       AWS_SECRET_ACCESS_KEY (a storage-only Scaleway key) and awscli is
#       installed (cloud-init does); the bucket expires objects after 30 days
#       (terraform/storage.tf). S3_BUCKET in s3.env overrides the name.
#
# A dump under 2 KB is refused, not kept: the trader's backups reported
# success for 17 nights while writing empty archives. Every failure is logged
# as ERROR and, when /opt/webhost/qmt.env has RESEND_API_KEY, EMAIL_FROM and
# OWNER_EMAIL, emailed to the owner through QMT's own sender. A database whose
# dump failed keeps all its older dumps. Exit 0 only when every dump and every
# upload tried worked.
set -euo pipefail
umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

BACKUP_DIR=/opt/backups
COMPOSE_DIR=/opt/webhost
DATABASES="qmt mojimakrosi"   # each owned by the role of the same name
KEEP_DAYS=14
MIN_BYTES=2048
S3_ENV="${BACKUP_DIR}/s3.env"
S3_ENDPOINT="https://s3.fr-par.scw.cloud"
S3_BUCKET_DEFAULT="teko-webhost-backups"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

log() { echo "$(date -u --iso-8601=seconds) $*"; }
FAILURES=()
fail() { log "ERROR: $*"; FAILURES+=("$*"); }

# The value of <key> in an env file (last line wins, quotes dropped).
env_value() {
  local line
  line="$(grep -E "^[[:space:]]*${2}=" "$1" 2>/dev/null | tail -n 1 || true)"
  line="${line#*=}"
  line="${line%"${line##*[![:space:]]}"}"
  case "$line" in
    \"*\") line="${line#\"}"; line="${line%\"}" ;;
    \'*\') line="${line#\'}"; line="${line%\'}" ;;
  esac
  printf '%s' "$line"
}

# The owner hears about a failure by email: a log nobody reads is how the
# trader's empty backups went unnoticed. The key travels in a header file,
# not on the command line.
alert() {
  local env="${COMPOSE_DIR}/qmt.env" key from to body
  key="$(env_value "$env" RESEND_API_KEY)"
  from="$(env_value "$env" EMAIL_FROM)"
  to="$(env_value "$env" OWNER_EMAIL)"
  if [[ -z "$key" || -z "$from" || -z "$to" ]]; then
    log "no alert email: ${env} lacks RESEND_API_KEY, EMAIL_FROM or OWNER_EMAIL"
    return 0
  fi
  body="$(printf '%s\n' "$@"; printf '\nThe log: %s/backup.log on %s.\n' "$BACKUP_DIR" "$(hostname)")"
  if python3 -c 'import json, sys; print(json.dumps({"from": sys.argv[1], "to": [sys.argv[2]], "subject": sys.argv[3], "text": sys.argv[4]}))' \
       "$from" "$to" "webhost: the nightly backup FAILED ($(hostname))" "$body" \
     | curl -fsS --max-time 30 -o /dev/null -H "Content-Type: application/json" \
         -H @<(printf 'Authorization: Bearer %s\n' "$key") \
         --data-binary @- https://api.resend.com/emails; then
    log "alert emailed to the owner"
  else
    log "WARNING: the alert email could not be sent either"
  fi
}

# One run at a time (cron and a hand-run must not interleave).
exec 9>/run/lock/webhost-backup.lock
if ! flock -n 9; then
  log "another backup is running: skipped"
  exit 0
fi

if [[ ! -f "${COMPOSE_DIR}/docker-compose.yml" ]]; then
  log "no ${COMPOSE_DIR}/docker-compose.yml: nothing deployed yet, nothing to back up"
  exit 0
fi
cd "$COMPOSE_DIR"
mkdir -p "$BACKUP_DIR"

DUMPS=()
if [[ -z "$(docker compose ps --status running -q db 2>/dev/null)" ]]; then
  fail "the db container is not running: no dumps tonight"
else
  for db in $DATABASES; do
    out="${BACKUP_DIR}/${db}-${STAMP}.sql.gz"
    tmp="${out}.partial"
    if docker compose exec -T db pg_dump -U "$db" -d "$db" --no-owner --no-privileges </dev/null \
         | gzip -6 >"$tmp" && gzip -t "$tmp"; then
      bytes="$(stat -c %s "$tmp")"
      if (( bytes < MIN_BYTES )); then
        rm -f "$tmp"
        fail "${db}: the dump is only ${bytes} bytes, refused (an empty database, or pg_dump wrote nothing)"
      else
        mv "$tmp" "$out"
        DUMPS+=("$out")
        log "${db}: ${out##*/} (${bytes} bytes)"
        # Rotate only a database whose dump worked tonight: a failing one
        # keeps every older dump it has.
        find "$BACKUP_DIR" -maxdepth 1 -name "${db}-*.sql.gz" -mtime "+${KEEP_DAYS}" -delete
      fi
    else
      rm -f "$tmp"
      fail "${db}: pg_dump failed (its error is above)"
    fi
  done
fi
find "$BACKUP_DIR" -maxdepth 1 -name '*.partial' -mmin +60 -delete

if (( ${#DUMPS[@]} > 0 )); then
  if [[ ! -f "$S3_ENV" ]]; then
    log "off-site skipped: no ${S3_ENV} (tonight's dumps are on this box only)"
  elif ! command -v aws >/dev/null 2>&1; then
    log "off-site skipped: awscli is not installed (tonight's dumps are on this box only)"
  else
    set -a
    # shellcheck disable=SC1090
    . "$S3_ENV"
    set +a
    bucket="${S3_BUCKET:-$S3_BUCKET_DEFAULT}"
    export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-fr-par}"
    # awscli >= 2.23 sends integrity checksums by default; "when_required" is
    # the older behaviour, which every S3-compatible store accepts.
    export AWS_REQUEST_CHECKSUM_CALCULATION="${AWS_REQUEST_CHECKSUM_CALCULATION:-when_required}"
    export AWS_RESPONSE_CHECKSUM_VALIDATION="${AWS_RESPONSE_CHECKSUM_VALIDATION:-when_required}"
    for f in "${DUMPS[@]}"; do
      name="${f##*/}"
      key="${name%%-*}/${name}"
      if aws --endpoint-url "$S3_ENDPOINT" s3 cp "$f" "s3://${bucket}/${key}" --only-show-errors; then
        log "off-site: s3://${bucket}/${key}"
      else
        fail "the off-site upload of ${name} failed (the local copy is kept)"
      fi
    done
  fi
fi

log "disk: $(df -h --output=used,avail,pcent / | tail -n 1 | tr -s ' ')"
if (( ${#FAILURES[@]} > 0 )); then
  alert "${FAILURES[@]}"
  exit 1
fi
log "done: ${#DUMPS[@]} dumps"
