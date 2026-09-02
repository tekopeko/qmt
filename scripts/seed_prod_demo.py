"""Populate PROD with realistic demo data for the closed test — run via a
Railway tunnel so nothing is exposed:

    railway link                 # pick the qmt project/service, once
    railway run python scripts/seed_prod_demo.py

`railway run` injects the real DATABASE_URL (internal, over the tunnel), so this
talks to prod without any public database access.

Creates verified demo clients, a believable week of bookings, and a couple of
personalized programmes, then grants the trainer. ADDITIVE and idempotent — it
never wipes anything (unlike scripts/seed_demo.py, which is dev-only). Safe to
re-run.

    --login-pw PW   also set this password on the demo clients so you can log in
                    AS them (to see the client side). Omit -> they are review-only
                    data with an unusable password.
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import func, select   # noqa: E402

from qmt import auth, config, db      # noqa: E402
from qmt.models import (              # noqa: E402
    Booking, Program, SessionTemplate, TrainingSession, User,
)

OWNER_EMAIL = config.OWNER_EMAIL or "tvrtko.doresic@gmail.com"

CLIENTS = [
    ("marko.horvat.demo@example.com", "Marko Horvat"),
    ("ana.kovac.demo@example.com", "Ana Kovač"),
    ("ivan.juric.demo@example.com", "Ivan Jurić"),
    ("petra.novak.demo@example.com", "Petra Novak"),
    ("luka.babic.demo@example.com", "Luka Babić"),
]

TIMETABLE = (
    [("Grupni trening", d, h, 60, 8, None)
     for d in (0, 2, 3, 4) for h in ("07:00", "16:00", "17:00", "18:00", "19:00")]
    + [("Individualni trening", d, "20:00", 60, 1, None) for d in range(5)]
)

# programme title, intro, [(exercise, instructions)]
PROGRAMS = [
    ("marko.horvat.demo@example.com",
     "Povratak nakon ozljede — tjedan 1",
     "Tri kruga, odmor 90 s između vježbi. Tempo kontroliran, bez boli.",
     [("Goblet čučanj", "3 × 10 · 12 kg\nTempo 3-1-1, pete cijelo vrijeme na podu."),
      ("Mrtvo dizanje s girjom", "3 × 8 · 16 kg\nNeutralna kralježnica, zastani sekundu gore."),
      ("Farmerski nosač", "3 × 30 m · 2 × 20 kg\nRamena dolje, pogled naprijed."),
      ("Mrtvi buba (dead bug)", "3 × 10 po strani\nLumbalni dio prislonjen uz pod cijelo vrijeme.")]),
    ("ana.kovac.demo@example.com",
     "Snaga — uvodni blok",
     "Dva kruga za početak, fokus na tehniku prije težine.",
     [("Iskorak unatrag", "3 × 8 po nozi\nKoljeno prati smjer stopala."),
      ("Potisak s bučicama", "3 × 10 · 8 kg\nLopatice skupljene, spusti kontrolirano."),
      ("Veslanje u pretklonu", "3 × 12 · 10 kg\nPovuci prema pojasu, zadrži leđa ravna.")]),
    ("ivan.juric.demo@example.com",
     "Mobilnost i core — kućni program",
     "Svaki dan ujutro, bez opreme. Kvaliteta pokreta prije brzine.",
     [("Mačka-deva", "2 × 10 sporih ponavljanja\nDišite u ritmu pokreta."),
      ("Bočni plank", "3 × 30 s po strani\nTijelo u ravnoj liniji, bez propadanja kuka."),
      ("Ptica-pas (bird dog)", "3 × 8 po strani\nSuprotna ruka i noga, bez rotacije trupa.")]),
]


def upsert_client(email: str, name: str, login_pw: str | None) -> int:
    with db.session_scope() as s:
        u = s.scalar(select(User).where(func.lower(User.email) == email))
        if u is None:
            u = User(email=email, name=name)
            s.add(u)
        u.name = name
        u.email_verified = True                       # real, loginable-shaped account
        u.password_hash = (auth.hash_password(login_pw) if login_pw
                           else u.password_hash or auth.hash_password("!") )
        s.flush()
        return u.id


def ensure_timetable() -> None:
    with db.session_scope() as s:
        have = s.scalar(select(func.count()).select_from(SessionTemplate))
        if have:
            print(f"  timetable: {have} stavki već postoje, preskačem")
            return
        for title, wd, hhmm, dur, cap, note in TIMETABLE:
            h, m = map(int, hhmm.split(":"))
            s.add(SessionTemplate(title=title, weekday=wd, start_min=h * 60 + m,
                                  duration_min=dur, capacity=cap, note=note))
        print(f"  timetable: {len(TIMETABLE)} stavki dodano")


def fill_bookings(client_ids: list[int]) -> None:
    monday = config.today() - timedelta(days=config.today().weekday())
    db.materialize_week(monday)
    with db.session_scope() as s:
        sessions = list(s.scalars(
            select(TrainingSession)
            .where(TrainingSession.starts_at > db.datetime.now(config.TZ))
            .order_by(TrainingSession.starts_at)))
    spread = [5, 2, 6, 1, 8, 3, 4, 0, 3, 1, 2, 5]
    booked = 0
    for i, (sess, n) in enumerate(zip(sessions, spread)):
        take = min(n, sess.capacity, len(client_ids))
        rotated = client_ids[i % len(client_ids):] + client_ids[: i % len(client_ids)]
        for uid in rotated[:take]:
            try:
                db.book(uid, sess.id)
                booked += 1
            except db.BookingError:
                pass
    print(f"  bookings: {booked} rezervacija")


def seed_programs() -> None:
    """Library programmes + dated assignments (spread across the next days)."""
    made = assigned = 0
    for offset, (email, title, intro, items) in enumerate(PROGRAMS):
        with db.session_scope() as s:
            u = s.scalar(select(User).where(func.lower(User.email) == email))
            pid = s.scalar(select(Program.id).where(Program.title == title))
        if pid is None:
            pid = db.create_program(title, intro)
            for ex_title, body in items:
                db.add_item(pid, ex_title, body, None, None)
            made += 1
        if db.assign_program(pid, u.id, config.today() + timedelta(days=offset)):
            assigned += 1
    print(f"  programmes: {made} novih, {assigned} dodjela")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login-pw", default=None,
                    help="set this password on demo clients so you can log in AS them")
    args = ap.parse_args()

    url = config.DATABASE_URL
    if "railway.internal" not in url and "rlwy.net" not in url and "proxy.rlwy" not in url:
        sys.exit("Refusing: DATABASE_URL is not a Railway prod DB. Run via `railway run …`.")
    print(f"seeding prod ({url.split('@')[-1]}) …")

    print("clients:")
    ids = []
    for email, name in CLIENTS:
        ids.append(upsert_client(email, name, args.login_pw))
        print(f"  + {name} <{email}>" + ("  [login-enabled]" if args.login_pw else ""))

    print("timetable:")
    ensure_timetable()
    print("week:")
    fill_bookings(ids)
    print("treninzi:")
    seed_programs()

    if db.set_trainer(OWNER_EMAIL):
        print(f"trainer: {OWNER_EMAIL} → admin")
    else:
        print(f"trainer: {OWNER_EMAIL} NOT found — sign up first, then re-run "
              f"(or run scripts/make_trainer.py)")
    print("done.")


if __name__ == "__main__":
    main()
