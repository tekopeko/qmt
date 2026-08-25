"""Auth: bcrypt password hashing (lifted from mojimakrosi's proven auth.py).

Login is password-based, sessions ride a signed cookie. Email verification /
password reset come later, together with Resend — before the public deploy.

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
