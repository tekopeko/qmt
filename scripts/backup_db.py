"""Nightly-ish backup of the QMT prod DB to Cloudflare R2 (run locally).

Ported from macro_tracker's battle-tested script — including the lessons it
learned the hard way: pg_dump stderr is SURFACED (a silent failure once went
unnoticed for 4 days there), transient failures retry, and a macOS notification
fires when a run dies.

    python scripts/backup_db.py            # through a Railway SSH tunnel (default)
    BACKUP_KEEP=30 python scripts/backup_db.py

Reads from .env: the R2_* keys the app uses (the dump goes to the media bucket
under qmt-backups/). The database is reached through `railway connect Postgres
--tunnel-only`, so it needs no public address: the Railway CLI is logged in on
this laptop and its SSH key is registered (`railway ssh keys add`). Setting
QMT_PROD_DATABASE_URL in .env skips the tunnel and dumps that URL instead.
pg_dump must match the server's major version; the script picks
/opt/homebrew/opt/postgresql@<major>/bin/pg_dump when the default one is older.
"""

from __future__ import annotations

import gzip
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qmt import config  # noqa: E402  (loads .env)

KEEP = int(os.environ.get("BACKUP_KEEP", "60"))
PREFIX = "qmt-backups/"
RETRIES = 5


def _alert(msg: str) -> None:
    print(f"ALERT: {msg}", file=sys.stderr)
    try:  # best-effort desktop ping on macOS
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{msg}" with title "QMT backup FAILED"'],
            capture_output=True, timeout=10)
    except Exception:
        pass


def _railway() -> str:
    """The Railway CLI, also under launchd's bare PATH."""
    return shutil.which("railway") or "/opt/homebrew/bin/railway"


@contextmanager
def _database_url():
    """Yield a URL pg_dump can reach. QMT_PROD_DATABASE_URL when set; otherwise
    an SSH tunnel to the Postgres service, opened for the duration and closed
    after — the database keeps no public address that way."""
    url = os.environ.get("QMT_PROD_DATABASE_URL", "").strip().replace("+psycopg", "")
    if url:
        yield url
        return
    with socket.socket() as sock:              # a free local port
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    kv = subprocess.run([_railway(), "variables", "--service", "Postgres", "--kv"],
                        capture_output=True, text=True, timeout=60)
    creds = dict(line.split("=", 1) for line in kv.stdout.splitlines() if "=" in line)
    missing = [k for k in ("PGUSER", "PGPASSWORD", "PGDATABASE") if not creds.get(k)]
    if missing:
        raise RuntimeError(f"railway variables gave no {', '.join(missing)} (is the CLI logged in and linked?)")
    tunnel = subprocess.Popen([_railway(), "connect", "Postgres", "--tunnel-only", "--port", str(port)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        for _ in range(60):                    # the tunnel takes a few seconds
            if tunnel.poll() is not None:
                raise RuntimeError(f"railway connect exited: {(tunnel.stderr.read() or '')[:200]}")
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError("the Railway tunnel never opened")
        print(f"tunnel open on 127.0.0.1:{port}")
        yield f"postgresql://{creds['PGUSER']}:{creds['PGPASSWORD']}@127.0.0.1:{port}/{creds['PGDATABASE']}"
    finally:
        tunnel.terminate()
        try:
            tunnel.wait(timeout=10)
        except subprocess.TimeoutExpired:
            tunnel.kill()


def _server_major(url: str) -> int:
    import psycopg
    with psycopg.connect(url, connect_timeout=15) as c, c.cursor() as cur:
        cur.execute("SHOW server_version_num")
        return int(cur.fetchone()[0]) // 10000


def _find_pg_dump(min_major: int) -> str | None:
    """A pg_dump at least as new as the server: the default one, else Homebrew's
    versioned keg (mojimakrosi's script learned this the hard way)."""
    candidates = ["pg_dump",
                  f"/opt/homebrew/opt/postgresql@{min_major}/bin/pg_dump",
                  f"/usr/local/opt/postgresql@{min_major}/bin/pg_dump",
                  "/opt/homebrew/opt/libpq/bin/pg_dump", "/usr/local/opt/libpq/bin/pg_dump"]
    for c in candidates:
        path = shutil.which(c) if "/" not in c else (c if os.path.exists(c) else None)
        if not path:
            continue
        nums = re.findall(r"\d+", subprocess.run([path, "--version"], capture_output=True, text=True).stdout)
        if nums and int(nums[0]) >= min_major:
            return path
    return None


def _pg_dump(url: str) -> bytes:
    major = _server_major(url)
    binary = _find_pg_dump(major)
    if not binary:
        raise RuntimeError(f"no pg_dump for PostgreSQL {major}: brew install postgresql@{major}")
    print(f"dumping with {binary} (server PG {major}) ...")
    last_err = ""
    for attempt in range(1, RETRIES + 1):
        proc = subprocess.run([binary, "--no-owner", "--no-privileges", url],
                              capture_output=True)
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
        last_err = proc.stderr.decode(errors="replace").strip()
        print(f"  pg_dump attempt {attempt}/{RETRIES} failed: {last_err[:200]}",
              file=sys.stderr)
        time.sleep(min(60, 5 * attempt))
    raise RuntimeError(f"pg_dump failed after {RETRIES} attempts: {last_err[:300]}")


def main() -> None:
    for var in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        if not os.environ.get(var, "").strip():
            sys.exit(f"{var} not set in .env")
    # the endpoint the app itself derives from the account id (storage.py); R2_ENDPOINT overrides
    endpoint = os.environ.get("R2_ENDPOINT", "").strip() or (
        f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com"
        if os.environ.get("R2_ACCOUNT_ID", "").strip() else "")
    if not endpoint:
        sys.exit("R2_ACCOUNT_ID (or R2_ENDPOINT) not set in .env")

    try:
        with _database_url() as url:
            dump = gzip.compress(_pg_dump(url), 6)
    except Exception as exc:
        _alert(str(exc)[:120])
        sys.exit(1)

    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
        region_name="auto")
    bucket = os.environ["R2_BUCKET"].strip()

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    key = f"{PREFIX}qmt-{stamp}.sql.gz"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=dump,
                      ContentType="application/gzip")
    except Exception as exc:
        _alert(f"R2 upload failed: {str(exc)[:100]}")
        sys.exit(1)
    print(f"uploaded {key} ({len(dump) // 1024} KB)")

    # rotate: newest KEEP stay
    objs = s3.list_objects_v2(Bucket=bucket, Prefix=PREFIX).get("Contents", [])
    objs.sort(key=lambda o: o["LastModified"], reverse=True)
    for o in objs[KEEP:]:
        s3.delete_object(Bucket=bucket, Key=o["Key"])
        print(f"rotated out {o['Key']}")
    print(f"backups kept: {min(len(objs), KEEP)}")


if __name__ == "__main__":
    main()
