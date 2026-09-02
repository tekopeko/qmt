"""Auth: bcrypt password hashing + signed email tokens (mojimakrosi ancestry).

Login is password-based, sessions ride a signed cookie. A token is the signed,
lower-cased email validated by signature + max-age — no server-side store.
Password-reset tokens additionally carry a marker of the CURRENT password hash,
so a used token dies the moment the password changes (single-use).

Only file that imports `bcrypt`.
"""

from __future__ import annotations

import re

import bcrypt

_MIN_PASSWORD_LEN = 8


# ---------- passwords ----------

def _pw_bytes(password: str) -> bytes:
    # bcrypt hard-limits the input to 72 bytes; truncate so long inputs don't error.
    return password.encode("utf-8")[:72]


def password_ok(password: str) -> bool:
    """Minimal strength check enforced before hashing."""
    return len(password) >= _MIN_PASSWORD_LEN


# Deliberately loose — the point is to reject junk, not to adjudicate RFC 5322.
# The address is proven by the verification email either way.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def email_ok(email: str) -> bool:
    """Does this look like an address at all?

    The sign-up form has type="email", but that is browser-side only: a plain
    POST bypasses it entirely. Without this, open sign-up lets anything become a
    users row and a Resend send attempt — and repeatedly mailing addresses that
    cannot exist is how a sending domain earns a bad reputation.
    """
    email = email.strip()
    return bool(email) and len(email) <= 320 and bool(_EMAIL_RE.match(email))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time check of a password against a stored hash."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_pw_bytes(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------- signed email tokens ----------

import hashlib

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import config

_VERIFY_SALT = "qmt-verify-email"
_RESET_SALT = "qmt-reset-password"
VERIFY_MAX_AGE_SECONDS = 24 * 60 * 60   # sign-up links: 24 h
RESET_MAX_AGE_SECONDS = 60 * 60         # reset links: 1 h


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(str(config.SECRET_KEY), salt=salt)


def make_verify_token(email: str) -> str:
    return _serializer(_VERIFY_SALT).dumps(email.strip().lower())


def read_verify_token(token: str) -> str | None:
    try:
        return _serializer(_VERIFY_SALT).loads(token, max_age=VERIFY_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None


def pw_marker(password_hash: str | None) -> str:
    """Short fingerprint of the current hash — embedded in reset tokens so each
    token works exactly once (the marker stops matching after the change)."""
    return hashlib.sha256((password_hash or "none").encode()).hexdigest()[:16]


def make_reset_token(email: str, password_hash: str | None) -> str:
    return _serializer(_RESET_SALT).dumps(
        {"e": email.strip().lower(), "m": pw_marker(password_hash)})


def read_reset_token(token: str) -> tuple[str, str] | None:
    """(email, marker) or None."""
    try:
        d = _serializer(_RESET_SALT).loads(token, max_age=RESET_MAX_AGE_SECONDS)
        return d["e"], d["m"]
    except (BadSignature, SignatureExpired, KeyError, TypeError):
        return None
