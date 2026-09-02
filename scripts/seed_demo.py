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
    ("marko@qmt.local", "Marko Babić", "lozinka123", False),
    ("petra@qmt.local", "Petra Novak", "lozinka123", False),
    ("luka@qmt.local", "Luka Perić", "lozinka123", False),
    ("sara@qmt.local", "Sara Jurić", "lozinka123", False),
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
            u = User(email=email, name=name, password_hash=auth.hash_password(password))
            s.add(u)
            print(f"  + {email}" + ("  (trener)" if is_trainer else ""))
        else:
            print(f"  = {email} (postoji)")
        u.is_trainer = is_trainer
        u.email_verified = True   # dev accounts skip the email round-trip


def main() -> None:
    from qmt import config
    if config.IS_PROD or "railway" in config.DATABASE_URL or "rlwy.net" in config.DATABASE_URL:
        sys.exit("ODBIJENO: seed je dev RESET (briše rezervacije i treninge) — nikad na produkciju.")
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


def fill_bookings() -> None:
    """Book a believable spread across this week.

    An all-empty calendar hides the whole point of the app — capacity. Partly
    full sessions ("5/8 mjesta"), one sold-out slot and one taken 1:1 make the
    rules visible at a glance, which is what a demo needs to show.
    """
    from datetime import timedelta

    from sqlalchemy import select

    from qmt.models import TrainingSession, User

    monday = db.config.today() - timedelta(days=db.config.today().weekday())
    db.materialize_week(monday)
    with db.session_scope() as s:
        clients = list(s.scalars(select(User).where(~User.is_trainer).order_by(User.id)))
        sessions = list(s.scalars(
            select(TrainingSession)
            .where(TrainingSession.starts_at > db.datetime.now(db.config.TZ))
            .order_by(TrainingSession.starts_at)))
    # how many of the 6 clients take each of the next sessions
    spread = [6, 3, 5, 1, 8, 2, 4, 0, 3, 1, 2, 5]
    booked = 0
    for i, (sess, n) in enumerate(zip(sessions, spread)):
        # Rotate who attends: always taking clients[:n] puts the first client in
        # every single session, which reads as a bug rather than a busy week.
        take = min(n, sess.capacity, len(clients))
        rotated = clients[i % len(clients):] + clients[: i % len(clients)]
        for c in rotated[:take]:
            try:
                db.book(c.id, sess.id)
                booked += 1
            except db.BookingError:
                pass
    print(f"  {booked} rezervacija")


def seed_program() -> None:
    """One example programme for Ivan, so /treninzi demos non-empty."""
    from sqlalchemy import delete, select

    from qmt.models import Program, User

    with db.session_scope() as s:
        s.execute(delete(Program))
        ivan = s.scalar(select(User).where(User.email == "ivan@qmt.local"))
    pid = db.create_program(ivan.id, "Povratak nakon ozljede — tjedan 1",
                            "Tri kruga, odmor 90 s između vježbi. Tempo kontroliran.")
    db.add_item(pid, "Goblet čučanj", "3 × 10 · 12 kg\nTempo 3-1-1, pete cijelo vrijeme na podu.", None, None)
    db.add_item(pid, "Mrtvo dizanje s girjom", "3 × 8 · 16 kg\nNeutralna kralježnica, zastani sekundu gore.", None, None)
    db.add_item(pid, "Farmerski nosač", "3 × 30 m · 2 × 20 kg\nRamena dolje, pogled naprijed.", None, None)
    print("  primjer programa za Ivana (3 vježbe)")


if __name__ == "__main__":
    main()
    print("bookings:")
    fill_bookings()
    print("treninzi:")
    seed_program()
