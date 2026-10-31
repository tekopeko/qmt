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


# The app owner. May sign up whenever signup is not closed, passes every
# trainer gate, and is the only account that may manage roles (/korisnici).
OWNER_EMAIL = _env_email("OWNER_EMAIL")
if IS_PROD and not OWNER_EMAIL:
    raise RuntimeError("Set OWNER_EMAIL when ENV=production.")


def _allowlist() -> set[str]:
    raw = os.environ.get("ALLOWED_EMAILS", "")
    return {e.strip().strip("\"'").lower() for e in raw.split(",") if e.strip()}


SIGNUP_MODES = ("closed", "invite", "open")


def signup_mode() -> str:
    """Who may open an account right now. One switch, three words:

        closed   nobody                         (the DEFAULT)
        invite   the owner + ALLOWED_EMAILS
        open     anyone

    Set with SIGNUP_MODE. Missing or unrecognised config fails CLOSED: a lost or
    mistyped env var must never become an open door, and an empty ALLOWED_EMAILS
    is not an invitation to the whole internet either.

    Closed by default since 28.9.2026: the owner was advised that prices may be
    shown only to people who already have an account until the price list carries a
    prior price beside the current one, the way shop shelves do. So the members' price list (/moja-clanarina) is
    members-only and no new accounts are opened; existing accounts log in as
    always. Reopening is SIGNUP_MODE=invite on Railway, no code change.
    """
    mode = os.environ.get("SIGNUP_MODE", "").strip().strip("\"'").lower()
    return mode if mode in SIGNUP_MODES else "closed"


def signup_open() -> bool:
    """Open to anyone, not only invited emails (drives the "samo uz poziv" copy)."""
    return signup_mode() == "open"


def prices_public() -> bool:
    """May someone who is not logged in see prices on the landing page?

    Yes, since 5.10.2026: the owner decided to show the offer and its prices on
    the homepage, reversing the members-only rule of 28.9. (see signup_mode).
    That rule existed on legal advice, so the way back is kept to one variable:
    PUBLIC_PRICES=off hides every price from guests again, no code change.
    /moja-clanarina (the old /cjenik) stays members-only either way; it is where plans are bought and
    managed, not the shop window.
    """
    v = os.environ.get("PUBLIC_PRICES", "").strip().strip("\"'").lower()
    return v not in ("0", "false", "no", "off")


def email_allowed(email: str) -> bool:
    mode = signup_mode()
    if mode == "closed":
        return False
    if mode == "open":
        return True
    e = email.strip().lower()
    if OWNER_EMAIL and e == OWNER_EMAIL:
        return True
    return e in _allowlist()


# Optional cross-link to the sibling app (the first, zero-coupling step of the
# eventual merge): set MOJIMAKROSI_URL and the nav shows a link. Nothing else is
# shared — no imports, no DB access.
MOJIMAKROSI_URL = os.environ.get("MOJIMAKROSI_URL", "https://mojimakrosi.com").strip()

# Uploaded media: the exercises' clips (the library, /treninzi/vjezbe), served
# only by the auth-gated /media, and the announcements' photos (/slika). Local
# disk without R2 (the four R2_* vars below), and a container keeps nothing
# across a deploy. Deliberately outside static/.
MEDIA_DIR = PROJECT_ROOT / "data" / "uploads"
# The largest exercise clip, in MB (30.10.2026). The owner's number was 100 MB
# a video ("we will change that when we get the actual videos"), but the box
# sits behind Cloudflare, whose free plan refuses a request body over 100 MB
# with its own 413 page before the app sees it: at 95 a refused clip meets the
# app's own sentence, and an allowed one leaves room for the multipart
# overhead. It replaces MAX_MEDIA_MB, the cap of the programme items' own
# images and videos, which went with them.
VIDEO_MAX_MB = int(os.environ.get("VIDEO_MAX_MB", "95"))

# How many days before dospijeće the članarina reminder goes out.
REMINDER_DAYS_BEFORE = int(os.environ.get("REMINDER_DAYS_BEFORE", "3"))

# Cloudflare R2 (S3-compatible) media storage. All four set => uploads go to
# the bucket and /media redirects to presigned URLs; any missing => local disk
# (data/uploads — fine in dev, EPHEMERAL on Railway).
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET = os.environ.get("R2_BUCKET", "").strip()

# Email (Resend) — verification + password reset. Unset in dev: the links are
# shown on-page instead of sent (never in prod — there they would be public).
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
EMAIL_FROM = os.environ.get("EMAIL_FROM", "QMT <onboarding@resend.dev>").strip()
PUBLIC_BASE_URL = os.environ.get(
    "PUBLIC_BASE_URL", "http://127.0.0.1:8100"
).strip().rstrip("/")


def email_enabled() -> bool:
    return bool(RESEND_API_KEY)


# Stripe — card payments as monthly subscriptions. Secret key + webhook secret
# switch the feature on; one Price id per plan (created in the Stripe
# dashboard, pasted here). Any plan without a price simply keeps the manual
# "javi se treneru" path, so a half-configured Stripe never breaks /moja-clanarina.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_PRICES = {
    plan: os.environ.get(f"STRIPE_PRICE_{plan.upper()}", "").strip()
    for plan in ("individualni", "poluindividualni", "rehabilitacija", "online", "prehrana")
}
# Grupni is sold in tiers — the shop's 8 / 12 / 16 treninga a month — so it
# carries one Price per tier (STRIPE_PRICE_GRUPNI_8 / _12 / _16) instead.
GRUPNI_TIERS = (8, 12, 16)
STRIPE_TIER_PRICES = {
    "grupni": {n: os.environ.get(f"STRIPE_PRICE_GRUPNI_{n}", "").strip() for n in GRUPNI_TIERS}
}


def stripe_enabled() -> bool:
    return bool(STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET)


# Booking rules. A client may cancel a booking until CANCEL_CUTOFF_HOURS before
# the termin (12 h, the owner's call of 17.10.2026; db.cancel_deadline); a termin
# the trainer canceled can always be dropped. A termin nobody has booked closes
# CLOSE_EMPTY_HOURS before it starts (4 h, the owner's call of 29.10.2026;
# db.is_closed): one booking keeps it open until it starts. Termini can be
# booked in the running week and BOOKING_WEEKS - 1 more (db.booking_window:
# this week and three more, the owner's "four weeks in total"), never past the
# plan's dospijeće.
CANCEL_CUTOFF_HOURS = int(os.environ.get("CANCEL_CUTOFF_HOURS", "12"))
CLOSE_EMPTY_HOURS = int(os.environ.get("CLOSE_EMPTY_HOURS", "4"))
BOOKING_WEEKS = int(os.environ.get("BOOKING_WEEKS", "4"))
# An online pass (the player's, models.WorkoutLog) with no activity for
# PASS_STALE_HOURS (2 h, the owner's call of 31.10.2026: no hanging training;
# activity is its start or its last saved exercise, WorkoutLog.stale) can no
# longer be continued, only finished with its osvrt or discarded, and its
# length runs to its last save, not to the osvrt a day later.
PASS_STALE_HOURS = int(os.environ.get("PASS_STALE_HOURS", "2"))


def today() -> date:
    from datetime import datetime

    return datetime.now(TZ).date()
