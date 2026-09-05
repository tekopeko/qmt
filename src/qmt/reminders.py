"""Email reminders — the owner's ask: "mail podsjetnik i za treninge i za plaćanje".

Two kinds, one idempotent pass:

- **članarina**: dospijeće falls within REMINDER_DAYS_BEFORE days → one mail per
  plan per cycle (the ref carries the cycle's next_payment date, so the next
  paid month naturally re-arms the reminder).
- **termin**: booked, live sessions happening TOMORROW → one mail per client per
  day listing them (each session is claimed individually, so a booking made
  after today's run still gets picked up by tomorrow morning's).

Claim-then-send against the `reminders` unique constraint makes any schedule
safe: hourly ticks, restarts, or two processes racing all collapse into one
email. A failed send releases its claim and the next run retries.

Driven two ways, same function:
- in-process: app startup schedules `run_once()` every few hours (no cron infra)
- manually / external cron: `python scripts/send_reminders.py`
"""

from __future__ import annotations

from datetime import timedelta

from . import config, db, mailer
from .models import PLAN_LABELS

WEEKDAYS_SHORT = ["pon", "uto", "sri", "čet", "pet", "sub", "ned"]


def run_once() -> dict[str, int]:
    """One reminder pass; returns counts for logs/tests. No-op without email —
    claiming with a dead mailer would eat every reminder and send none."""
    counts = {"clanarina": 0, "termin": 0, "failed": 0}
    if not config.email_enabled():
        return counts

    # --- članarina: dospijeće approaching ---
    for user, m in db.memberships_expiring(config.REMINDER_DAYS_BEFORE):
        ref = f"{m.plan}:{m.next_payment.isoformat()}"
        if not db.claim_reminder(user.id, "clanarina", ref):
            continue
        if mailer.send_membership_reminder(user.email, PLAN_LABELS.get(m.plan, m.plan),
                                           m.dospijece):
            counts["clanarina"] += 1
        else:
            db.release_reminder(user.id, "clanarina", ref)
            counts["failed"] += 1

    # --- termin: tomorrow's booked sessions, one mail per client ---
    tomorrow = config.today() + timedelta(days=1)
    per_user: dict[int, tuple[str, list]] = {}
    for user, sess in db.bookings_on(tomorrow):
        per_user.setdefault(user.id, (user.email, []))[1].append(sess)

    for uid, (email, sessions) in per_user.items():
        claimed = [s for s in sessions if db.claim_reminder(uid, "termin", str(s.id))]
        if not claimed:
            continue
        termini = []
        for s in claimed:
            at = s.starts_at.astimezone(config.TZ)
            termini.append((s.title, f"{WEEKDAYS_SHORT[at.weekday()]} {at:%-d.%-m. %H:%M}"))
        if mailer.send_termin_reminder(email, termini):
            counts["termin"] += 1
        else:
            for s in claimed:
                db.release_reminder(uid, "termin", str(s.id))
            counts["failed"] += 1

    return counts
