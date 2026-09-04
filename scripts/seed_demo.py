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
    [("Grupni trening", d, h, 60, 8, None, "grupni") for d in GROUP_DAYS for h in GROUP_HOURS]
    + [("Individualni trening", d, "20:00", 60, 1, None, "individualni") for d in range(5)]
)

# Who pays for what (sara deliberately has NO plan — shows the booking gate).
PLANS = {
    "ivan@qmt.local": ("grupni", "individualni", "online"),
    "ana@qmt.local": ("grupni",),
    "marko@qmt.local": ("grupni",),
    "petra@qmt.local": ("grupni", "individualni"),
    "luka@qmt.local": ("grupni",),
}


def upsert_user(email: str, name: str, password: str, is_trainer: bool) -> None:
    from datetime import date

    first, _, last = name.partition(" ")
    with db.session_scope() as s:
        u = s.scalar(select(User).where(User.email == email))
        if u is None:
            u = User(email=email, password_hash=auth.hash_password(password))
            s.add(u)
            print(f"  + {email}" + ("  (trener)" if is_trainer else ""))
        else:
            print(f"  = {email} (postoji)")
        u.name, u.last_name = first, last or None
        # complete profiles — otherwise every dev login bounces to /profil
        u.birth_date = u.birth_date or date(1990 + len(email) % 9, 3, 14)
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
    from qmt.models import (Booking, Membership, OnboardingResponse, Payment,
                            TrainingLog, TrainingSession)
    with db.session_scope() as s:
        s.execute(delete(Booking))
        s.execute(delete(TrainingSession))
        s.execute(delete(SessionTemplate))
        s.execute(delete(Membership))
        s.execute(delete(Payment))
        s.execute(delete(OnboardingResponse))
        s.execute(delete(TrainingLog))
        for title, wd, hhmm, dur, cap, note, kind in TIMETABLE:
            h, m = map(int, hhmm.split(":"))
            s.add(SessionTemplate(title=title, kind=kind, weekday=wd, start_min=h * 60 + m,
                                  duration_min=dur, capacity=cap, note=note))
        print(f"  {len(TIMETABLE)} stavki")

    print("clanarine:")
    n = 0
    for email, plans in PLANS.items():
        u = db.get_user_by_email(email)
        for plan in plans:
            db.record_payment(u.id, plan)
            n += 1
    print(f"  {n} članarina (sara@qmt.local namjerno bez — demo blokade)")


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
    """The 9 combo programmes, each pre-filled with the default exercises."""
    from sqlalchemy import delete

    from qmt.models import Program

    with db.session_scope() as s:
        s.execute(delete(Program))
    made = db.ensure_online_skeletons()
    print(f"  {made} programa (razina × cilj), svi s osnovnim vježbama")


def seed_karton() -> None:
    """Ivan: filled upitnik + two diary entries — the karton demo."""
    import json
    from datetime import timedelta

    from qmt import upitnik

    ivan = db.get_user_by_email("ivan@qmt.local")
    picked = {"staz": 2, "tjedno": 2, "sklekovi": 1, "cucanj": 2, "ozljede": 2}
    score, level = upitnik.score_answers(picked)
    db.save_onboarding(ivan.id, json.dumps(picked), score, level, "gornji")
    today = db.config.today()
    db.add_training_log(ivan.id, today - timedelta(days=2), 7,
                        "Čučanj 3×8 · 60 kg\nPotisak s klupe 3×10 · 40 kg\nVeslanje 3×12 · 35 kg",
                        feeling="dobro")
    db.add_training_log(ivan.id, today - timedelta(days=5), 5,
                        "Mobilnost + core, lagani dan.")
    # a termin that ended two hours ago -> karton greets Ivan with "Kako je bilo?"
    from qmt.models import Booking
    sid = db.add_oneoff_session("Grupni trening",
                                db.datetime.now(db.config.TZ) - timedelta(hours=2),
                                60, 8, None, "grupni")
    with db.session_scope() as s:
        s.add(Booking(user_id=ivan.id, session_id=sid))
    print(f"  Ivan: upitnik ({level}, gornji dio), 2 zapisa, 1 osvrt na čekanju")


if __name__ == "__main__":
    main()
    print("bookings:")
    fill_bookings()
    print("treninzi:")
    seed_program()
    print("karton:")
    seed_karton()
