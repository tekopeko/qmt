"""Seed local dev data: the trainer, two demo clients, and a week's timetable.

Idempotent — safe to re-run. Passwords are for LOCAL DEV ONLY.

    python scripts/seed_demo.py
    # trener@qmt.local / trener123   (admin)
    # ivan@qmt.local  / lozinka123
    # ana@qmt.local   / lozinka123
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select

from qmt import auth, db
from qmt.models import SessionTemplate, User

TRAINER = ("trener@qmt.local", "Trener QMT", "trener123", True)
CLIENTS = [
    ("ivan@qmt.local", "Ivan Horvat", "lozinka123", False),
    ("ana@qmt.local", "Ana Kovač", "lozinka123", False),
]

# Modeled on the real studio (Setmore: open Mon/Wed/Thu/Fri 07:00-20:00):
# hourly GROUP trainings, capacity 8 — one row per hour block, replacing the
# 16:05/16:10/16:15 capacity hack the old Setmore setup needed. INDIVIDUAL 1:1
# Mon-Fri 20:00-21:00 (placeholder until the trainer confirms his real slots —
# he can edit everything in /admin now).
GROUP_DAYS = [0, 2, 3, 4]                     # pon, sri, čet, pet
GROUP_HOURS = ["07:00", "16:00", "17:00", "18:00", "19:00"]
TIMETABLE = (
    [("Grupni trening", d, h, 60, 8, None) for d in GROUP_DAYS for h in GROUP_HOURS]
    + [("Individualni trening", d, "20:00", 60, 1, None) for d in range(5)]
)


def upsert_user(email: str, name: str, password: str, is_trainer: bool) -> None:
    with db.session_scope() as s:
        u = s.scalar(select(User).where(User.email == email))
        if u is None:
            s.add(User(email=email, name=name,
                       password_hash=auth.hash_password(password), is_trainer=is_trainer))
            print(f"  + {email}" + ("  (trener)" if is_trainer else ""))
        else:
            u.is_trainer = is_trainer
            print(f"  = {email} (postoji)")


def main() -> None:
    print("users:")
    upsert_user(*TRAINER)
    for c in CLIENTS:
        upsert_user(*c)

    print("timetable (dev RESET — replaces all templates/sessions/bookings):")
    from sqlalchemy import delete
    from qmt.models import Booking, TrainingSession
    with db.session_scope() as s:
        s.execute(delete(Booking))
        s.execute(delete(TrainingSession))
        s.execute(delete(SessionTemplate))
        for title, wd, hhmm, dur, cap, note in TIMETABLE:
            h, m = map(int, hhmm.split(":"))
            s.add(SessionTemplate(title=title, weekday=wd, start_min=h * 60 + m,
                                  duration_min=dur, capacity=cap, note=note))
        print(f"  {len(TIMETABLE)} stavki")


if __name__ == "__main__":
    main()
