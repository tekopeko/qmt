"""Nightly-ish backup of the QMT prod DB to Cloudflare R2 (run locally).

Ported from macro_tracker's battle-tested script — including the lessons it
learned the hard way: pg_dump stderr is SURFACED (a silent failure once went
unnoticed for 4 days there), transient failures retry, and a macOS notification
fires when a run dies.

    python scripts/backup_db.py            # uses QMT_PROD_DATABASE_URL from .env
    BACKUP_KEEP=30 python scripts/backup_db.py

Reads from .env: QMT_PROD_DATABASE_URL (Railway public URL) and the R2_* keys
(same bucket as mojimakrosi's backups; QMT lives under its own prefix).
"""

from __future__ import annotations

import gzip
import os
import subprocess
import sys
import time
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


def _pg_dump(url: str) -> bytes:
    last_err = ""
    for attempt in range(1, RETRIES + 1):
        proc = subprocess.run(["pg_dump", "--no-owner", "--no-privileges", url],
                              capture_output=True)
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
        last_err = proc.stderr.decode(errors="replace").strip()
        print(f"  pg_dump attempt {attempt}/{RETRIES} failed: {last_err[:200]}",
              file=sys.stderr)
        time.sleep(min(60, 5 * attempt))
    raise RuntimeError(f"pg_dump failed after {RETRIES} attempts: {last_err[:300]}")


def main() -> None:
    url = os.environ.get("QMT_PROD_DATABASE_URL", "").strip().replace("+psycopg", "")
    if not url:
        sys.exit("QMT_PROD_DATABASE_URL not set in .env")
    for var in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        if not os.environ.get(var, "").strip():
            sys.exit(f"{var} not set in .env")

    try:
        dump = gzip.compress(_pg_dump(url), 6)
    except Exception as exc:
        _alert(str(exc)[:120])
        sys.exit(1)

    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"].strip(),
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
