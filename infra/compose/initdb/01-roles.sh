#!/usr/bin/env bash
# Postgres image hook (/docker-entrypoint-initdb.d): runs ONCE, when the pgdata
# volume is empty, as the superuser on a socket-only temporary server.
# One login role and one database per app, each database owned by its role and
# closed to everyone else (CONNECT and TEMPORARY revoked from PUBLIC).
#
# The passwords come from /opt/webhost/db.env (the db service's env_file).
# Changing them there later does NOT re-run this: see infra/README.md,
# "Changing a database password".
#
# No `set -u`: should the image ever source this file instead of running it,
# the option would leak into its entrypoint.
set -eo pipefail

: "${QMT_DB_PASSWORD:?QMT_DB_PASSWORD is empty (db.env)}"
: "${MM_DB_PASSWORD:?MM_DB_PASSWORD is empty (db.env)}"

# :'name' is psql's quoted-literal interpolation: any character is safe.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set qmt_pw="$QMT_DB_PASSWORD" --set mm_pw="$MM_DB_PASSWORD" <<'SQL'
CREATE ROLE qmt LOGIN PASSWORD :'qmt_pw';
CREATE DATABASE qmt OWNER qmt;
REVOKE CONNECT, TEMPORARY ON DATABASE qmt FROM PUBLIC;

CREATE ROLE mojimakrosi LOGIN PASSWORD :'mm_pw';
CREATE DATABASE mojimakrosi OWNER mojimakrosi;
REVOKE CONNECT, TEMPORARY ON DATABASE mojimakrosi FROM PUBLIC;
SQL
