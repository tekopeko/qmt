"""Grant (or revoke) trainer/admin status — the ONLY way to become admin.

Sign-up never grants it: without email verification, deriving admin from a
self-asserted address would hand the studio to whoever registers the trainer's
email first.

    python scripts/make_trainer.py trener@example.com
    python scripts/make_trainer.py trener@example.com --revoke
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qmt import db  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("email")
    ap.add_argument("--revoke", action="store_true")
    a = ap.parse_args()
    if db.set_trainer(a.email, not a.revoke):
        print(("revoked: " if a.revoke else "trainer: ") + a.email)
    else:
        sys.exit(f"no user with email {a.email!r} — they must sign up first")
