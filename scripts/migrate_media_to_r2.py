"""One-time copy of data/uploads into the R2 bucket.

    python scripts/migrate_media_to_r2.py          # copies, keeps local files
    python scripts/migrate_media_to_r2.py --purge  # copies, then deletes local

Run AFTER the four R2_* env vars are set; refuses to run without them.
Idempotent — re-uploading the same key just overwrites it with itself.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qmt import config, storage  # noqa: E402

_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
          ".webp": "image/webp", ".gif": "image/gif", ".mp4": "video/mp4",
          ".mov": "video/quicktime", ".webm": "video/webm"}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--purge", action="store_true", help="delete local copies after upload")
    args = ap.parse_args()

    if not storage.r2_enabled():
        sys.exit("R2 nije konfiguriran — postavi R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/"
                 "R2_SECRET_ACCESS_KEY/R2_BUCKET pa pokreni ponovno.")
    if not config.MEDIA_DIR.is_dir():
        sys.exit(f"Nema {config.MEDIA_DIR} — nema se što kopirati.")

    files = [p for p in sorted(config.MEDIA_DIR.iterdir())
             if p.is_file() and p.suffix.lower() in _TYPES]
    client = storage._client()
    for p in files:
        client.upload_file(str(p), config.R2_BUCKET, p.name,
                           ExtraArgs={"ContentType": _TYPES[p.suffix.lower()]})
        print(f"  ↑ {p.name}")
        if args.purge:
            p.unlink()
    print(f"{len(files)} datoteka u bucketu '{config.R2_BUCKET}'"
          + (" (lokalne kopije obrisane)" if args.purge else ""))
