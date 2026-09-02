"""Central config: paths, .env, feature gates.

Mirrors macro_tracker's conventions on purpose — the two apps stay separate
entities, but sharing the same shape (env-gated cloud features, SECRET_KEY prod
guard, allowlist sign-up) is what keeps an eventual merge cheap.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

TZ = ZoneInfo("Europe/Zagreb")

ENV = os.environ.get("ENV", "development").strip().lower()
IS_PROD = ENV == "production"

def _normalize_db_url(url: str) -> str:
    """Managed hosts (Railway, Heroku, …) inject `postgres://` or `postgresql://`,
    which SQLAlchemy maps to the psycopg2 dialect — but we install psycopg 3.
    Same lesson macro_tracker's config already encodes; forgetting it crashed
    the very first Railway deploy at `alembic upgrade head`."""
    for scheme in ("postgres://", "postgresql://", "postgresql+psycopg2://"):
        if url.startswith(scheme):
            return "postgresql+psycopg://" + url[len(scheme):]
    return url


DATABASE_URL = _normalize_db_url(
    os.environ.get("DATABASE_URL", "postgresql+psycopg:///qmt").strip()
)

_DEV_SECRET = "dev-secret-do-not-use-in-prod"
SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET)
if IS_PROD and SECRET_KEY == _DEV_SECRET:
    raise RuntimeError("Set a real SECRET_KEY when ENV=production.")


def _env_email(name: str) -> str:
    # Railway's raw editor stores values WITH surrounding quotes; strip them.
    return os.environ.get(name, "").strip().strip("\"'").strip().lower()


# The trainer (owner). Always allowed, always admin.
TRAINER_EMAIL = _env_email("TRAINER_EMAIL")
if IS_PROD and not TRAINER_EMAIL:
    raise RuntimeError("Set TRAINER_EMAIL when ENV=production.")


def _allowlist() -> set[str]:
    raw = os.environ.get("ALLOWED_EMAILS", "")
    return {e.strip().strip("\"'").lower() for e in raw.split(",") if e.strip()}


def email_allowed(email: str) -> bool:
    e = email.strip().lower()
    if TRAINER_EMAIL and e == TRAINER_EMAIL:
        return True
    return e in _allowlist()


# Optional cross-link to the sibling app (the first, zero-coupling step of the
# eventual merge): set MOJIMAKROSI_URL and the nav shows a link. Nothing else is
# shared — no imports, no DB access.
MOJIMAKROSI_URL = os.environ.get("MOJIMAKROSI_URL", "https://mojimakrosi.com").strip()

# Uploaded programme media (exercise images/videos). Local disk for now — on
# Railway this is EPHEMERAL and needs a volume or R2 before real use (a redeploy
# would eat the trainer's videos). Deliberately outside static/: personal content.
MEDIA_DIR = PROJECT_ROOT / "data" / "uploads"
MAX_MEDIA_MB = int(os.environ.get("MAX_MEDIA_MB", "60"))

# Email (Resend) — verification + password reset. Unset in dev: the links are
# shown on-page instead of sent (never in prod — there they would be public).
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
EMAIL_FROM = os.environ.get("EMAIL_FROM", "QMT <onboarding@resend.dev>").strip()
PUBLIC_BASE_URL = os.environ.get(
    "PUBLIC_BASE_URL", "http://127.0.0.1:8100"
).strip().rstrip("/")


def email_enabled() -> bool:
    return bool(RESEND_API_KEY)


# Booking rules.
CANCEL_CUTOFF_HOURS = int(os.environ.get("CANCEL_CUTOFF_HOURS", "3"))
BOOKING_HORIZON_DAYS = int(os.environ.get("BOOKING_HORIZON_DAYS", "28"))


def today() -> date:
    from datetime import datetime

    return datetime.now(TZ).date()
