"""Seed local dev data: the trainer, two demo clients, and a week's timetable.

Idempotent — safe to re-run. Passwords are for LOCAL DEV ONLY.

    python scripts/seed_demo.py
    # trener@qmt.local / trener123   (admin)
    # ivan@qmt.local  / lozinka123
    # ana@qmt.local   / lozinka123

Also the upitnik's questions (the gym owner's fifteen, ids 1–15, and the two
asked after the safety questions, 16 and 17) and ivan's answers to them.
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
# ivan's online plan is QMove PRO, the featured middle card: the landing
# shows a member one owned tier of the three
ONLINE_TIER = {"ivan@qmt.local": "pro"}


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
            db.record_payment(u.id, plan, tier=ONLINE_TIER.get(email) if plan == "online" else None)
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


# The library's demo (30.10.2026): tags on some of the default exercises,
# a few exercises no programme holds yet, and the similar exercises a
# client may swap one for (stored one way, read both: Exercise.alternatives).
# name -> (tags, instructions for a new one, rep note, similar exercises)
LIBRARY = {
    "Goblet čučanj": ("noge, bučice", None, "Spust dok su bedra paralelna s podom, pa natrag do pune ekstenzije.",
                      ("Čučanj s vlastitom težinom", "Iskorak unatrag")),
    "Sklekovi": ("prsa, kod kuće", None, "Prsa do šake od poda, pa laktovi do kraja.", ("Sklekovi s koljena",)),
    "Veslanje u pretklonu": ("leđa, bučice", None, "", ("Veslanje jednom rukom",)),
    "Rumunjsko mrtvo dizanje": ("noge, stražnja loža, bučice", None, "", ("Glute most",)),
    "Plank": ("core, kod kuće", None, "", ()),
    "Čučanj s vlastitom težinom": ("noge, kod kuće", "Stopala u širini ramena, ruke ispred tijela, pete na podu.",
                                   "", ()),
    "Sklekovi s koljena": ("prsa, kod kuće", "Koljena na podu, tijelo od koljena do glave u ravnoj liniji.", "", ()),
    "Veslanje jednom rukom": ("leđa, bučice", "Slobodna ruka i koljeno na klupi, povuci bučicu prema kuku.", "", ()),
    "Istezanje stražnje lože": ("istezanje, kod kuće", "Sjedni ispružene noge, nagni se naprijed ravnih leđa.", "", ()),
}

# The days' demo (30.10.2026, stage 2): ivan's programme (srednja × cijelo)
# gets a title and a weekday on its Dan 1, a warm-up and a stretch around the
# defaults, and a Dan 2, so the demo shows two days and all three sections.
# (day title, weekday, [(exercise, section, sets, reps, seconds, rest, note)]):
# Dan 1's items are added to the defaults, Dan 2's make a new day.
DAYS = [
    ("Cijelo tijelo", 0, [("Čučanj s vlastitom težinom", "zagrijavanje", 2, 15, None, 30, ""),
                          ("Istezanje stražnje lože", "istezanje", 2, None, 30, None, "po nozi")]),
    ("Gornji dio", 3, [("Sklekovi", "trening", 3, 10, None, 60, ""),
                       ("Veslanje u pretklonu", "trening", 3, 12, None, 60, "2 × 10 kg"),
                       ("Plank", "trening", 3, None, 40, 45, "")]),
]


def seed_program() -> None:
    """The 9 combo programmes, each with its Dan 1 of the default exercises
    (library rows, the cues; each item its razina's dose and 60 s of rest,
    db._DEFAULT_ITEMS), then the library's demo (LIBRARY) and the days' demo
    (DAYS, ivan's programme). A dev RESET: the library goes with the
    programmes (their clips' files are left alone: the dev .env may point
    storage at R2)."""
    from sqlalchemy import delete, select

    from qmt.models import Exercise, Program

    with db.session_scope() as s:
        s.execute(delete(Program))          # their days and items with them
        s.execute(delete(Exercise))         # and the pairs of similar exercises
    made = db.ensure_online_skeletons()
    with db.session_scope() as s:
        ids = {e.name: e.id for e in s.scalars(select(Exercise))}
    for name, (tags, instructions, rep_note, _) in LIBRARY.items():
        if name not in ids:
            ids[name] = db.create_exercise(name, instructions or "", rep_note, tags)
    for name, (tags, _, rep_note, similar) in LIBRARY.items():
        e = db.exercise(ids[name])
        db.update_exercise(e.id, e.name, e.instructions, rep_note or e.rep_note, tags,
                           {ids[x] for x in similar} | {a.id for a in e.alternatives})
    with db.session_scope() as s:
        pid = s.scalar(select(Program.id).where(Program.level == "srednja", Program.goal == "cijelo"))
    for n, (title, weekday, items) in enumerate(DAYS, start=1):
        day_id = db.get_program(pid).days[0].id if n == 1 else db.add_day(pid)
        db.update_day(day_id, title, weekday, "")
        for name, section, sets, reps, seconds, rest, note in items:
            item_id = db.add_day_item(day_id, ids[name], section)
            db.update_day_item(item_id, section, sets, reps, seconds, rest, note)
    print(f"  {made} programa (razina × cilj), svi s osnovnim vježbama (Dan 1); {len(ids)} vježbi u bazi; "
          f"srednja × cijelo: {len(DAYS)} dana, sva tri dijela")


def seed_announcements() -> None:
    """The landing's two example announcements (copy.ANNOUNCEMENT_EXAMPLES),
    in place of whatever cards there were: a dev RESET, as the rest. Their
    photos' files are left alone: the dev .env may point storage at R2."""
    from sqlalchemy import delete

    from qmt.copy import ANNOUNCEMENT_EXAMPLES
    from qmt.models import Announcement

    with db.session_scope() as s:
        s.execute(delete(Announcement))
        for position, example in enumerate(ANNOUNCEMENT_EXAMPLES, start=1):
            s.add(Announcement(position=position, **example))
    print(f"  {len(ANNOUNCEMENT_EXAMPLES)} najave (primjeri)")


def seed_gym_cards() -> None:
    """The landing's two gym cards (copy.GYM_CARD_EXAMPLES: Dvorana and
    Individualno, with the plans they stand for), in place of whatever cards
    there were: a dev RESET, as the rest."""
    from sqlalchemy import delete

    from qmt.copy import GYM_CARD_EXAMPLES
    from qmt.models import GymCard

    with db.session_scope() as s:
        s.execute(delete(GymCard))
    for example in GYM_CARD_EXAMPLES:
        db.add_gym_card(None, example)
    print(f"  {len(GYM_CARD_EXAMPLES)} kartice (Dvorana, Individualno)")


def seed_upitnik() -> None:
    """The upitnik's questions (copy.UPITNIK_DEFAULT_QUESTIONS: the
    fifteen with their ids 1–15, the keys ivan's answers below are stored
    under, and q16 / q17 asked after q14 / q15), in place of whatever
    questions there were: a dev RESET, as the rest (main() has dropped
    every response already)."""
    from sqlalchemy import delete

    from qmt.copy import UPITNIK_DEFAULT_QUESTIONS
    from qmt.models import UpitnikQuestion

    with db.session_scope() as s:
        s.execute(delete(UpitnikQuestion))
    for question in UPITNIK_DEFAULT_QUESTIONS:
        db.add_upitnik_question(None, question)
    print(f"  {len(UPITNIK_DEFAULT_QUESTIONS)} pitanja (vlasnikova)")


def seed_karton() -> None:
    """Ivan: filled upitnik + two diary entries — the karton demo."""
    import json
    from datetime import timedelta

    from qmt import upitnik

    ivan = db.get_user_by_email("ivan@qmt.local")
    # the upitnik v2 (26.10.2026): part 1 as the defaults word it, scales that
    # land him in srednja (6,4 / 10), no pain to speak of, no injuries (so
    # neither q16 nor q17 is asked); scored over the questions seed_upitnik made
    answers = {"q1": "Povećanje snage i mišićne mase", "q2": "3", "q3": "45-60", "q4": "U teretani",
               "q5": 7, "q6": 6, "q7": 5, "q8": 6, "q9": 8, "q10": 8, "q11": 6,
               "q12": 4, "q13": 8, "q14": 3, "q15": False}
    result = upitnik.evaluate(answers, upitnik.client_steps(db.upitnik_questions()))
    level = result.level
    db.save_onboarding(ivan.id, json.dumps(answers, ensure_ascii=False), result.score, level, upitnik.GOAL,
                       version=upitnik.VERSION, pain_level=result.pain_level, pain_high=result.pain_high,
                       needs_review=result.needs_review, consented_at=db.datetime.now(db.config.TZ))
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
    print(f"  Ivan: upitnik ({level}, {upitnik.score_text(result.score)}), 2 zapisa, 1 osvrt na čekanju")


if __name__ == "__main__":
    main()
    print("bookings:")
    fill_bookings()
    print("treninzi:")
    seed_program()
    print("upitnik:")
    seed_upitnik()
    print("karton:")
    seed_karton()
    print("aktualno:")
    seed_announcements()
    print("dvorana:")
    seed_gym_cards()
