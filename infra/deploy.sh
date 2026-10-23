#!/usr/bin/env bash
# Deploys QMT and/or mojimakrosi to the webhost box (Scaleway: infra/README.md).
# The trader dashboard's deploy.sh, for two apps:
#
#   infra/deploy.sh <host> [qmt|mojimakrosi|all] [--dry-run] [--skip-tests]
#
#   1. refuses a dirty tree (DEPLOY_ALLOW_DIRTY=1 overrides), a missing env
#      file, or an env file whose required values are empty or inconsistent;
#   2. runs the app's tests (--skip-tests or DEPLOY_SKIP_TESTS=1 skips them);
#   3. copies infra/env/{db,qmt,mojimakrosi}.env to /opt/webhost/ (mode 600),
#      the compose file and initdb/ to /opt/webhost/, backup.sh to /opt/backups/;
#   4. per app: rsyncs its checkout to /opt/webhost/<app>/, keeps the running
#      image as :prev, `docker compose up -d --build <app>`, waits up to 4 min
#      for "healthy", rolls back to :prev when it never gets there;
#   5. prunes dangling images and week-old build cache, prints `docker compose ps`.
#
# --dry-run runs the local checks (a refusal is reported, not fatal) and prints
# every rsync and ssh command instead of running it; any host name will do.
#
# Tests. mojimakrosi: its suite runs when ../macro_tracker/tests holds test
# files (none today). QMT: NOT run by default. Its suite is the review gate
# already (pytest -q before every commit, CLAUDE.md); it needs the local
# qmt_test database and Playwright's browsers, takes minutes, and two runs on
# the shared qmt_test break each other. DEPLOY_QMT_TESTS=1 runs it here too.
#
# Env: DEPLOY_ALLOW_DIRTY=1, DEPLOY_SKIP_TESTS=1, DEPLOY_QMT_TESTS=1,
#      MM_ROOT=<path> (mojimakrosi's checkout, default below).
# Written for macOS's bash 3.2: no associative arrays, no empty-array expansion.
set -euo pipefail

INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QMT_ROOT="$(cd "${INFRA}/.." && pwd)"
# mojimakrosi's code is synced from its own checkout, beside this repo.
MM_ROOT="${MM_ROOT:-${QMT_ROOT}/../macro_tracker}"
MM_ROOT="$(cd "$MM_ROOT" 2>/dev/null && pwd || printf '%s' "$MM_ROOT")"
ENV_DIR="${INFRA}/env"
REMOTE="/opt/webhost"

usage() {
  echo "usage: infra/deploy.sh <host> [qmt|mojimakrosi|all] [--dry-run] [--skip-tests]" >&2
  exit 2
}

DRY_RUN=0
SKIP_TESTS="${DEPLOY_SKIP_TESTS:-0}"
HOST=""
TARGET=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --skip-tests) SKIP_TESTS=1 ;;
    -h|--help) usage ;;
    -*) echo "unknown option: $arg" >&2; usage ;;
    *)
      if [[ -z "$HOST" ]]; then HOST="$arg"
      elif [[ -z "$TARGET" ]]; then TARGET="$arg"
      else usage
      fi ;;
  esac
done
[[ -n "$HOST" ]] || usage
case "${TARGET:-all}" in
  qmt) APPS="qmt" ;;
  mojimakrosi) APPS="mojimakrosi" ;;
  all) APPS="qmt mojimakrosi" ;;
  *) usage ;;
esac

say()  { printf '==> %s\n' "$*"; }
warn() { printf '!! %s\n' "$*" >&2; }

# A refusal stops the deploy after every check has had its say; in a dry run
# it is only reported.
REFUSED=0
refuse() {
  if [[ "$DRY_RUN" == 1 ]]; then warn "would refuse: $*"; else warn "refusing to deploy: $*"; REFUSED=1; fi
}

# A local command (rsync), or its printout in a dry run.
run() {
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '+'; printf ' %q' "$@"; printf '\n'
  else
    "$@"
  fi
}

# remote <script> [args...]: runs <script> with bash on the box, as root, its
# arguments as $1...; prints it instead in a dry run. The script travels as
# `bash -c` text, not on stdin, so nothing it runs can swallow the rest of it.
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

# The value of <key> in an env file: its last line wins, surrounding quotes
# and trailing blanks go. Read to check it, never printed.
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

require_env() {  # require_env <env name> <key>...
  local name="$1" key
  shift
  for key in "$@"; do
    if [[ -z "$(env_value "${ENV_DIR}/${name}.env" "$key")" ]]; then
      refuse "infra/env/${name}.env: ${key} is empty or missing"
    fi
  done
}

# ---------------------------------------------------------------- the box's side
# (single-quoted heredocs: nothing in them expands here)

IFS= read -r -d '' REMOTE_PREP <<'SH' || true
set -euo pipefail
mkdir -p /opt/webhost/initdb
install -d -m 0700 /opt/backups
SH

IFS= read -r -d '' REMOTE_UP <<'SH' || true
set -euo pipefail
app="$1"
cd /opt/webhost
if docker image inspect "webhost-${app}:latest" >/dev/null 2>&1; then
  docker tag "webhost-${app}:latest" "webhost-${app}:prev"
  echo "the running image is kept as webhost-${app}:prev"
else
  echo "no webhost-${app}:latest yet (first deploy): nothing to roll back to"
fi
docker compose up -d --build "$app"
SH

IFS= read -r -d '' REMOTE_WAIT <<'SH' || true
set -uo pipefail
app="$1"
tries="$2"
cd /opt/webhost
s=""
for i in $(seq 1 "$tries"); do
  id="$(docker compose ps -q "$app" 2>/dev/null || true)"
  if [ -n "$id" ]; then
    s="$(docker inspect --format "{{.State.Health.Status}}" "$id" 2>/dev/null || true)"
    if [ "$s" = healthy ]; then echo "${app}: healthy"; exit 0; fi
  fi
  sleep 5
done
echo "${app}: not healthy after $((tries * 5)) s (last status: ${s:-none}); its last log lines:"
docker compose logs --no-color --tail 40 "$app" || true
exit 1
SH

IFS= read -r -d '' REMOTE_ROLLBACK <<'SH' || true
set -euo pipefail
app="$1"
cd /opt/webhost
if ! docker image inspect "webhost-${app}:prev" >/dev/null 2>&1; then
  echo "no webhost-${app}:prev (first deploy): nothing to roll back to"
  exit 3
fi
docker tag "webhost-${app}:prev" "webhost-${app}:latest"
docker compose up -d --no-build "$app"
SH

IFS= read -r -d '' REMOTE_PRUNE <<'SH' || true
docker image prune -f >/dev/null
docker builder prune -f --filter until=168h >/dev/null
df -h / | tail -n 1
SH

IFS= read -r -d '' REMOTE_PS <<'SH' || true
cd /opt/webhost && docker compose ps
SH

# ---------------------------------------------------------------- preflight

say "Deploying ${APPS} to root@${HOST}$([[ "$DRY_RUN" == 1 ]] && echo ' (DRY RUN: nothing runs on the box)')"

if [[ " ${APPS} " == *" mojimakrosi "* && ! -f "${MM_ROOT}/Dockerfile" ]]; then
  refuse "no mojimakrosi checkout at ${MM_ROOT} (set MM_ROOT)"
fi

# The deployed code must be the committed code. The infra (compose file,
# backup.sh) comes from this repo whichever app ships.
if [[ -z "${DEPLOY_ALLOW_DIRTY:-}" ]]; then
  if [[ " ${APPS} " == *" qmt "* ]]; then
    if [[ -n "$(git -C "$QMT_ROOT" status --porcelain)" ]]; then
      refuse "QMT's working tree is dirty (commit first, or DEPLOY_ALLOW_DIRTY=1)"
    fi
  elif [[ -n "$(git -C "$QMT_ROOT" status --porcelain -- infra)" ]]; then
    refuse "infra/ has uncommitted changes (commit first, or DEPLOY_ALLOW_DIRTY=1)"
  fi
  if [[ " ${APPS} " == *" mojimakrosi "* && -d "${MM_ROOT}/.git" ]]; then
    if [[ -n "$(git -C "$MM_ROOT" status --porcelain)" ]]; then
      refuse "mojimakrosi's working tree (${MM_ROOT}) is dirty (commit first, or DEPLOY_ALLOW_DIRTY=1)"
    fi
  fi
fi

# All three env files, always: Compose reads every service's env_file even
# when it starts one. The deployed apps' must be complete and consistent.
env_files_present=1
for name in db qmt mojimakrosi; do
  if [[ ! -f "${ENV_DIR}/${name}.env" ]]; then
    refuse "infra/env/${name}.env is missing (copy ${name}.env.example, fill it in)"
    env_files_present=0
  fi
done
if [[ "$env_files_present" == 1 ]]; then
  require_env db POSTGRES_PASSWORD QMT_DB_PASSWORD MM_DB_PASSWORD
  for app in $APPS; do
    if [[ "$app" == qmt ]]; then
      role=qmt; pw_key=QMT_DB_PASSWORD
      require_env qmt SECRET_KEY OWNER_EMAIL PUBLIC_BASE_URL RESEND_API_KEY EMAIL_FROM \
        R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_BUCKET
    else
      role=mojimakrosi; pw_key=MM_DB_PASSWORD
      require_env mojimakrosi SECRET_KEY USER_EMAIL OPENAI_API_KEY RESEND_API_KEY EMAIL_FROM \
        R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_BUCKET R2_PUBLIC_URL
    fi
    file="${ENV_DIR}/${app}.env"
    # The apps refuse only their dev default: an empty or short key would sign
    # the session cookies of production (token_hex(32) gives 64 characters).
    secret="$(env_value "$file" SECRET_KEY)"
    if [[ -n "$secret" && ${#secret} -lt 32 ]]; then
      refuse "infra/env/${app}.env: SECRET_KEY is shorter than 32 characters"
    fi
    if [[ "$(env_value "$file" ENV)" != production ]]; then
      refuse "infra/env/${app}.env: ENV must be production (anything else boots with the dev defaults)"
    fi
    port="$(env_value "$file" PORT)"
    if [[ -n "$port" && "$port" != 8000 ]]; then
      refuse "infra/env/${app}.env: PORT must be 8000 (compose and the healthcheck expect it)"
    fi
    if [[ "$(env_value "$file" DATABASE_URL)" != "postgresql+psycopg://${role}:$(env_value "${ENV_DIR}/db.env" "$pw_key")@db:5432/${role}" ]]; then
      refuse "infra/env/${app}.env: DATABASE_URL must be postgresql+psycopg://${role}:<${pw_key} from db.env>@db:5432/${role}"
    fi
  done
fi

[[ "$REFUSED" == 0 ]] || exit 1

# ---------------------------------------------------------------- tests

run_tests() {  # run_tests <app> <checkout>
  local app="$1" root="$2"
  if [[ "$SKIP_TESTS" == 1 ]]; then
    say "${app}: tests skipped (--skip-tests / DEPLOY_SKIP_TESTS=1)"
    return 0
  fi
  if [[ "$app" == qmt && "${DEPLOY_QMT_TESTS:-0}" != 1 ]]; then
    say "qmt: suite not run here (the review gate before each commit runs it; DEPLOY_QMT_TESTS=1 runs it here)"
    return 0
  fi
  if ! compgen -G "${root}/tests/test_*.py" >/dev/null && ! compgen -G "${root}/tests/*_test.py" >/dev/null; then
    say "${app}: no tests in ${root}/tests, nothing to run"
    return 0
  fi
  if [[ ! -x "${root}/.venv/bin/python" ]]; then
    refuse "${app}: no ${root}/.venv to run the tests with (--skip-tests deploys without them)"
    return 0
  fi
  say "${app}: running the tests"
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '+ (cd %q && %q -m pytest -q)\n' "$root" "${root}/.venv/bin/python"
  elif ! (cd "$root" && "${root}/.venv/bin/python" -m pytest -q); then
    refuse "${app}: the tests failed"
  fi
}

for app in $APPS; do
  if [[ "$app" == qmt ]]; then run_tests qmt "$QMT_ROOT"; else run_tests mojimakrosi "$MM_ROOT"; fi
done
[[ "$REFUSED" == 0 ]] || exit 1

# ---------------------------------------------------------------- infra files

say "Copying the env files (600), the compose files and backup.sh"
remote "$REMOTE_PREP"
run rsync -a --no-owner --no-group --chmod=F600 \
  "${ENV_DIR}/db.env" "${ENV_DIR}/qmt.env" "${ENV_DIR}/mojimakrosi.env" "root@${HOST}:${REMOTE}/"
run rsync -a --no-owner --no-group --chmod=F644 \
  "${INFRA}/compose/docker-compose.yml" "root@${HOST}:${REMOTE}/docker-compose.yml"
run rsync -a --delete --no-owner --no-group --chmod=D755,F755 \
  "${INFRA}/compose/initdb/" "root@${HOST}:${REMOTE}/initdb/"
run rsync -a --no-owner --no-group --chmod=F755 \
  "${INFRA}/backup.sh" "root@${HOST}:/opt/backups/backup.sh"

# ---------------------------------------------------------------- the apps

# What never ships: the brief's list, plus whatever the checkout's own
# .gitignore ignores (mojimakrosi keeps a food diary, input.txt, its legacy
# SQLite file and source images there). --chmod keeps the exec bits: QMT's
# Dockerfile runs ./start.sh without a chmod of its own.
SYNC_FILTERS=(
  "--filter=:- .gitignore"
  --exclude=.git --exclude='.venv*' --exclude='.env*' --exclude=__pycache__
  --exclude=/infra/ --exclude=/tests/ --exclude=node_modules --exclude='*.log' --exclude=.claude
)

deploy_app() {  # deploy_app <app> <checkout>
  local app="$1" root="$2"
  if [[ "$app" == qmt ]]; then
    # data/ holds design references and dev uploads; the image needs none of it.
    DATA_RULES=(--exclude=/data/)
  else
    # mojimakrosi's image copies data/products_hr.json (the product bank seed).
    DATA_RULES=(--include=/data/ --include=/data/products_hr.json --exclude='/data/*')
  fi
  say "${app}: syncing ${root} to root@${HOST}:${REMOTE}/${app}/"
  run rsync -az --delete --no-owner --no-group --chmod=Dgo-w,Fgo-w \
    "${DATA_RULES[@]}" "${SYNC_FILTERS[@]}" "${root}/" "root@${HOST}:${REMOTE}/${app}/"

  say "${app}: building and starting it (the running image is kept as :prev)"
  remote "$REMOTE_UP" "$app"

  say "${app}: waiting for healthy (up to 4 min)"
  if ! remote "$REMOTE_WAIT" "$app" 48; then
    warn "${app}: the new container never became healthy: ROLLING BACK to webhost-${app}:prev"
    local rc=0
    remote "$REMOTE_ROLLBACK" "$app" || rc=$?
    if [[ "$rc" == 3 ]]; then
      warn "${app}: a first deploy has no previous image: ${app} stays down until a fixed version deploys."
    elif [[ "$rc" == 0 ]] && remote "$REMOTE_WAIT" "$app" 24; then
      warn "${app}: rolled back, the previous version serves. The code on the box is the NEW one: fix it and deploy again."
    else
      warn "${app}: the rollback is not healthy either."
      warn "If the new version migrated the database (alembic), the old code cannot start on it: fix forward, or restore last night's dump (infra/restore.sh)."
    fi
    exit 1
  fi
}

for app in $APPS; do
  if [[ "$app" == qmt ]]; then deploy_app qmt "$QMT_ROOT"; else deploy_app mojimakrosi "$MM_ROOT"; fi
done

say "Pruning dangling images and build cache older than a week"
remote "$REMOTE_PRUNE"

say "Done. docker compose ps:"
remote "$REMOTE_PS"
