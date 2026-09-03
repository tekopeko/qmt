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
    [("Grupni trening", d, h, 60, 8, None, "grupni")
     for d in (0, 2, 3, 4) for h in ("07:00", "16:00", "17:00", "18:00", "19:00")]
    + [("Individualni trening", d, "20:00", 60, 1, None, "individualni") for d in range(5)]
)

def upsert_client(email: str, name: str, login_pw: str | None) -> int:
    from datetime import date

    first, _, last = name.partition(" ")
    with db.session_scope() as s:
        u = s.scalar(select(User).where(func.lower(User.email) == email))
        if u is None:
            u = User(email=email)
            s.add(u)
        u.name, u.last_name = first, last or None
        # complete profile so demo logins don't bounce to /profil
        u.birth_date = u.birth_date or date(1988 + len(email) % 12, 6, 21)
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
        for title, wd, hhmm, dur, cap, note, kind in TIMETABLE:
            h, m = map(int, hhmm.split(":"))
            s.add(SessionTemplate(title=title, kind=kind, weekday=wd, start_min=h * 60 + m,
                                  duration_min=dur, capacity=cap, note=note))
        print(f"  timetable: {len(TIMETABLE)} stavki dodano")


def ensure_memberships(client_ids: list[int]) -> None:
    """Booking is gated by plan since c4e8f19a52d7 — demo clients need one."""
    n = 0
    for i, uid in enumerate(client_ids):
        if not db.active_plan_kinds(uid):
            db.record_payment(uid, "grupni")
            if i % 2 == 0:                       # a couple also take 1:1 termine
                db.record_payment(uid, "individualni")
            n += 1
    print(f"  memberships: {n} klijenata dobilo plan")


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
    """The 9 (razina × cilj) skeletons — the trainer fills in the content."""
    made = db.ensure_online_skeletons()
    print(f"  programmes: {made} skica (razina × cilj)")


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
    print("clanarine:")
    ensure_memberships(ids)
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
