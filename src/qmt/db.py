"""Persistence + booking rules.

The one invariant that must hold under concurrency: a session can never be
overbooked. Two phones tapping the last spot at the same moment both pass a naive
count-then-insert check (the same race macro_tracker's LLM quota had), so
`book()` locks the session row FOR UPDATE and re-counts inside the lock.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator

from sqlalchemy import create_engine, delete as sa_delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from . import config
from .models import Base, Booking, SessionTemplate, TrainingSession, User

# READ COMMITTED is pinned, not assumed: book()'s lock-then-recount is only
# correct if the recount sees rows committed while we waited on the lock. Under
# an environment-overridden REPEATABLE READ the recount would keep its old
# snapshot and sell the last spot twice.
engine = create_engine(config.DATABASE_URL, future=True, isolation_level="READ COMMITTED")
_Session = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# ---------- users ----------

def get_user_by_email(email: str) -> User | None:
    with session_scope() as s:
        return s.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def get_user(user_id: int) -> User | None:
    with session_scope() as s:
        return s.get(User, user_id)


def create_user(email: str, name: str, password_hash: str) -> User:
    """Create a CLIENT account. Never grants is_trainer.

    Sign-up proves nothing about email ownership until verification exists, so
    deriving admin from the claimed address would let whoever registers the
    trainer's email FIRST take over the studio (rosters with every client's
    name+email, timetable control). Trainer status is granted out-of-band:
    scripts/make_trainer.py, or the dev seed.
    """
    email = email.strip().lower()
    with session_scope() as s:
        u = User(email=email, name=name.strip() or None, password_hash=password_hash)
        s.add(u)
        s.flush()
        return u


def set_trainer(email: str, is_trainer: bool = True) -> bool:
    """Out-of-band admin grant (scripts/seed only — no route calls this)."""
    with session_scope() as s:
        u = s.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
        if u is None:
            return False
        u.is_trainer = is_trainer
        return True


# ---------- timetable ----------

def list_templates() -> list[SessionTemplate]:
    with session_scope() as s:
        return list(s.scalars(
            select(SessionTemplate).order_by(SessionTemplate.weekday, SessionTemplate.start_min)
        ).all())


def add_template(title: str, weekday: int, start_min: int, duration_min: int,
                 capacity: int, note: str | None) -> int:
    with session_scope() as s:
        t = SessionTemplate(title=title, weekday=weekday, start_min=start_min,
                            duration_min=duration_min, capacity=capacity, note=note)
        s.add(t)
        s.flush()
        return t.id


def get_template(template_id: int) -> SessionTemplate | None:
    with session_scope() as s:
        return s.get(SessionTemplate, template_id)


def _prune_future_unbooked(s, template_id: int) -> None:
    """Remove this template's future sessions nobody has booked.

    Editing/deleting a template must not silently rewrite history (past sessions
    stay) nor yank sessions people already booked (those stay too — the trainer
    cancels them explicitly if needed). Unbooked future ones are just cache, and
    lazy materialization recreates them from the template's new values.
    """
    now = datetime.now(config.TZ)
    booked = select(Booking.session_id)
    s.execute(sa_delete(TrainingSession).where(
        TrainingSession.template_id == template_id,
        TrainingSession.starts_at > now,
        ~TrainingSession.id.in_(booked),
    ))


def update_template(template_id: int, title: str, weekday: int, start_min: int,
                    duration_min: int, capacity: int, note: str | None) -> bool:
    with session_scope() as s:
        t = s.get(SessionTemplate, template_id)
        if t is None:
            return False
        t.title, t.weekday, t.start_min = title, weekday, start_min
        t.duration_min, t.capacity, t.note = duration_min, capacity, note
        _prune_future_unbooked(s, template_id)
        return True


def delete_template(template_id: int) -> bool:
    with session_scope() as s:
        t = s.get(SessionTemplate, template_id)
        if t is None:
            return False
        _prune_future_unbooked(s, template_id)
        s.delete(t)          # booked/past sessions survive via ondelete=SET NULL
        return True


def set_template_active(template_id: int, active: bool) -> None:
    with session_scope() as s:
        t = s.get(SessionTemplate, template_id)
        if t is not None:
            t.active = active


def materialize_week(monday) -> None:
    """Ensure every active template has a concrete session in the given week.

    Runs on every week view. Safe under concurrency: the INSERT is
    ON CONFLICT DO NOTHING against uq_session_template_start, so two requests
    materializing the same week cannot double-create.
    """
    this_monday = config.today() - timedelta(days=config.today().weekday())
    horizon_monday = this_monday + timedelta(days=config.BOOKING_HORIZON_DAYS + 7)
    if monday < this_monday or monday > horizon_monday:
        # Past weeks render whatever exists; fabricating "history" or letting a
        # client mint unbounded rows by walking ?week= is not materialization's job.
        return
    with session_scope() as s:
        templates = s.scalars(select(SessionTemplate).where(SessionTemplate.active)
                              .order_by(SessionTemplate.id)).all()  # stable order: no deadlocks
        for t in templates:
            day = monday + timedelta(days=t.weekday)
            starts = datetime(day.year, day.month, day.day,
                              t.start_min // 60, t.start_min % 60, tzinfo=config.TZ)
            s.execute(
                pg_insert(TrainingSession).values(
                    template_id=t.id, title=t.title, starts_at=starts,
                    duration_min=t.duration_min, capacity=t.capacity,
                ).on_conflict_do_nothing(constraint="uq_session_template_start")
            )


def sessions_between(start: datetime, end: datetime) -> list[dict]:
    """Sessions in [start, end) with booking counts, oldest first."""
    with session_scope() as s:
        rows = s.execute(
            select(TrainingSession, func.count(Booking.id))
            .join(Booking, Booking.session_id == TrainingSession.id, isouter=True)
            .where(TrainingSession.starts_at >= start, TrainingSession.starts_at < end)
            .group_by(TrainingSession.id)
            .order_by(TrainingSession.starts_at)
        ).all()
        return [{"session": sess, "booked": n} for sess, n in rows]


def user_booking_ids(user_id: int, session_ids: list[int]) -> set[int]:
    if not session_ids:
        return set()
    with session_scope() as s:
        return set(s.scalars(
            select(Booking.session_id)
            .where(Booking.user_id == user_id, Booking.session_id.in_(session_ids))
        ).all())


def add_oneoff_session(title: str, starts_at: datetime, duration_min: int,
                       capacity: int, note: str | None) -> int:
    with session_scope() as s:
        sess = TrainingSession(title=title, starts_at=starts_at,
                               duration_min=duration_min, capacity=capacity, note=note)
        s.add(sess)
        s.flush()
        return sess.id


def set_session_canceled(session_id: int, canceled: bool) -> None:
    with session_scope() as s:
        sess = s.get(TrainingSession, session_id)
        if sess is not None:
            sess.canceled = canceled


def roster(session_id: int) -> list[User]:
    with session_scope() as s:
        return list(s.scalars(
            select(User).join(Booking, Booking.user_id == User.id)
            .where(Booking.session_id == session_id).order_by(Booking.id)
        ).all())


# ---------- booking ----------

class BookingError(Exception):
    """Refusal with a Croatian, user-facing message."""


def book(user_id: int, session_id: int) -> None:
    now = datetime.now(config.TZ)
    with session_scope() as s:
        sess = s.execute(
            select(TrainingSession).where(TrainingSession.id == session_id).with_for_update()
        ).scalar_one_or_none()
        if sess is None or sess.canceled:
            raise BookingError("Termin ne postoji ili je otkazan.")
        if sess.starts_at <= now:
            raise BookingError("Termin je već počeo ili prošao.")
        if sess.starts_at > now + timedelta(days=config.BOOKING_HORIZON_DAYS):
            raise BookingError(f"Rezervacije se otvaraju {config.BOOKING_HORIZON_DAYS} dana unaprijed.")
        taken = s.scalar(select(func.count()).select_from(Booking).where(Booking.session_id == session_id))
        if taken >= sess.capacity:
            raise BookingError("Termin je popunjen.")
        already = s.scalar(select(func.count()).select_from(Booking)
                           .where(Booking.session_id == session_id, Booking.user_id == user_id))
        if already:
            raise BookingError("Već si rezervirao/la ovaj termin.")
        s.add(Booking(user_id=user_id, session_id=session_id))


def cancel_booking(user_id: int, session_id: int) -> None:
    now = datetime.now(config.TZ)
    with session_scope() as s:
        b = s.scalar(select(Booking).where(Booking.session_id == session_id,
                                           Booking.user_id == user_id))
        if b is None:
            raise BookingError("Nemaš rezervaciju za ovaj termin.")
        sess = s.get(TrainingSession, session_id)
        # The cutoff protects the trainer's planning — meaningless for a session
        # the trainer already canceled, so dropping those is always allowed.
        if sess and not sess.canceled \
                and sess.starts_at - timedelta(hours=config.CANCEL_CUTOFF_HOURS) <= now:
            raise BookingError(
                f"Otkazivanje je moguće najkasnije {config.CANCEL_CUTOFF_HOURS} h prije termina."
            )
        s.delete(b)


def my_upcoming(user_id: int) -> list[TrainingSession]:
    """Upcoming booked sessions, INCLUDING trainer-canceled ones — the template
    marks those "otkazano"; silently dropping them would hide exactly the thing
    the client most needs to know."""
    with session_scope() as s:
        return list(s.scalars(
            select(TrainingSession).join(Booking, Booking.session_id == TrainingSession.id)
            .where(Booking.user_id == user_id, TrainingSession.starts_at >= datetime.now(config.TZ))
            .order_by(TrainingSession.starts_at)
        ).all())
