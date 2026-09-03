"""Persistence + booking rules.

The one invariant that must hold under concurrency: a session can never be
overbooked. Two phones tapping the last spot at the same moment both pass a naive
count-then-insert check (the same race macro_tracker's LLM quota had), so
`book()` locks the session row FOR UPDATE and re-counts inside the lock.
"""

from __future__ import annotations

import calendar
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Iterator

from sqlalchemy import create_engine, delete as sa_delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from . import config
from .models import (PLAN_LABELS, Base, Booking, Membership, OnboardingResponse,
                     Program, ProgramAssignment, ProgramItem, SessionTemplate,
                     TrainingLog, TrainingSession, User)

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


def mark_email_verified(email: str) -> bool:
    with session_scope() as s:
        u = s.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
        if u is None:
            return False
        u.email_verified = True
        return True


def reset_password(email: str, password_hash: str, expected_marker: str) -> bool:
    """Set a new password only if the reset token's marker still matches the
    CURRENT hash — locked FOR UPDATE so a token cannot be redeemed twice
    concurrently (mojimakrosi's proven single-use guard)."""
    from . import auth as _auth

    with session_scope() as s:
        u = s.scalar(select(User).where(func.lower(User.email) == email.strip().lower())
                     .with_for_update())
        if u is None or _auth.pw_marker(u.password_hash) != expected_marker:
            return False
        u.password_hash = password_hash
        u.email_verified = True
        return True


def list_all_users() -> list[User]:
    """Owner roster — every account, newest first."""
    with session_scope() as s:
        return list(s.scalars(select(User).order_by(User.created_at.desc(), User.id.desc())))


def set_trainer_id(user_id: int, is_trainer: bool) -> bool:
    with session_scope() as s:
        u = s.get(User, user_id)
        if u is None:
            return False
        u.is_trainer = is_trainer
        return True


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
                 capacity: int, note: str | None, kind: str = "grupni") -> int:
    with session_scope() as s:
        t = SessionTemplate(title=title, kind=kind, weekday=weekday, start_min=start_min,
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
                    duration_min: int, capacity: int, note: str | None,
                    kind: str = "grupni") -> bool:
    with session_scope() as s:
        t = s.get(SessionTemplate, template_id)
        if t is None:
            return False
        t.title, t.weekday, t.start_min = title, weekday, start_min
        t.duration_min, t.capacity, t.note, t.kind = duration_min, capacity, note, kind
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
                    template_id=t.id, title=t.title, kind=t.kind, starts_at=starts,
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
                       capacity: int, note: str | None, kind: str = "grupni") -> int:
    with session_scope() as s:
        sess = TrainingSession(title=title, kind=kind, starts_at=starts_at,
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
        if sess.kind not in active_plan_kinds(user_id, s):
            raise BookingError(
                f"Za termin \"{PLAN_LABELS.get(sess.kind, sess.kind)}\" treba "
                "aktivna članarina — javi se treneru.")
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


# ---------- memberships (članarine) ----------

def _add_month(d: date) -> date:
    """Same day next month, clamped to month length (31.1. → 28.2.)."""
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def active_plan_kinds(user_id: int, s: Session | None = None) -> set[str]:
    """Plans whose dospijeće (next_payment + grace week) hasn't passed."""
    cutoff = config.today() - timedelta(days=Membership.GRACE_DAYS)
    q = select(Membership.plan).where(Membership.user_id == user_id,
                                      Membership.next_payment >= cutoff)
    if s is not None:
        return set(s.scalars(q))
    with session_scope() as scope:
        return set(scope.scalars(q))


def memberships_for(user_id: int) -> list[Membership]:
    with session_scope() as s:
        return list(s.scalars(select(Membership).where(Membership.user_id == user_id)
                              .order_by(Membership.plan)))


def record_payment(user_id: int, plan: str) -> Membership:
    """Cash/card taken at the gym: start the plan or extend it by a month.

    Paying early extends from the CURRENT due date, not from today — a payment
    a week ahead must never shorten the cycle. A lapsed plan restarts from
    today (nobody owes "back months" for time the gym wasn't used).
    """
    today = config.today()
    with session_scope() as s:
        m = s.scalar(select(Membership).where(Membership.user_id == user_id,
                                              Membership.plan == plan).with_for_update())
        base = m.next_payment if m is not None and m.next_payment > today else today
        if m is None:
            m = Membership(user_id=user_id, plan=plan, paid_on=today,
                           next_payment=_add_month(base))
            s.add(m)
        else:
            m.paid_on, m.next_payment = today, _add_month(base)
        s.flush()
        return m


def remove_membership(user_id: int, plan: str) -> bool:
    with session_scope() as s:
        m = s.scalar(select(Membership).where(Membership.user_id == user_id,
                                              Membership.plan == plan))
        if m is None:
            return False
        s.delete(m)
        return True


def memberships_overview() -> list[dict]:
    """Every client with their plans — the trainer's Članarine page."""
    with session_scope() as s:
        users = list(s.scalars(select(User).where(~User.is_trainer)
                               .order_by(User.name, User.email)))
        all_m = list(s.scalars(select(Membership).order_by(Membership.plan)))
    by_user: dict[int, list[Membership]] = {}
    for m in all_m:
        by_user.setdefault(m.user_id, []).append(m)
    return [{"user": u, "plans": by_user.get(u.id, [])} for u in users]


# ---------- karton (onboarding upitnik + training diary) ----------

def save_onboarding(user_id: int, answers_json: str, score: int,
                    level: str, goal: str) -> None:
    """Upsert — refilling the upitnik replaces the previous routing."""
    with session_scope() as s:
        r = s.scalar(select(OnboardingResponse)
                     .where(OnboardingResponse.user_id == user_id).with_for_update())
        if r is None:
            s.add(OnboardingResponse(user_id=user_id, answers=answers_json,
                                     score=score, level=level, goal=goal))
        else:
            r.answers, r.score, r.level, r.goal = answers_json, score, level, goal


def get_onboarding(user_id: int) -> OnboardingResponse | None:
    with session_scope() as s:
        return s.scalar(select(OnboardingResponse)
                        .where(OnboardingResponse.user_id == user_id))


def onboarding_user_ids() -> set[int]:
    """Who has filled the upitnik — the trainer's assign UI marks the rest."""
    with session_scope() as s:
        return set(s.scalars(select(OnboardingResponse.user_id)))


def pending_feedback(user_id: int, days: int = 7) -> list[TrainingSession]:
    """Attended sessions that ENDED (within the last `days`) and still have no
    feedback — the karton prompts these. Old unfilled ones expire quietly."""
    now = datetime.now(config.TZ)
    with session_scope() as s:
        done = select(TrainingLog.session_id).where(
            TrainingLog.user_id == user_id, TrainingLog.session_id.is_not(None))
        rows = s.scalars(
            select(TrainingSession)
            .join(Booking, Booking.session_id == TrainingSession.id)
            .where(Booking.user_id == user_id,
                   ~TrainingSession.canceled,
                   TrainingSession.starts_at >= now - timedelta(days=days),
                   ~TrainingSession.id.in_(done))
            .order_by(TrainingSession.starts_at.desc())).all()
    # "ended" depends on each session's own duration — filter in Python
    return [x for x in rows if x.starts_at + timedelta(minutes=x.duration_min) < now]


def add_session_feedback(user_id: int, session_id: int, effort: int,
                         feeling: str | None, note: str) -> None:
    """Feedback is tied to an ATTENDED, FINISHED termin — never free-floating."""
    now = datetime.now(config.TZ)
    with session_scope() as s:
        sess = s.get(TrainingSession, session_id)
        booked = s.scalar(select(func.count()).select_from(Booking).where(
            Booking.session_id == session_id, Booking.user_id == user_id))
        if sess is None or not booked:
            raise BookingError("Termin ne postoji ili nisi bio/la prijavljen/a.")
        if sess.canceled:
            raise BookingError("Termin je otkazan — nema osvrta.")
        if sess.starts_at + timedelta(minutes=sess.duration_min) >= now:
            raise BookingError("Termin još nije završio.")
        existing = s.scalar(select(func.count()).select_from(TrainingLog).where(
            TrainingLog.user_id == user_id, TrainingLog.session_id == session_id))
        if existing:
            raise BookingError("Osvrt za ovaj termin već postoji.")
        s.add(TrainingLog(user_id=user_id, session_id=session_id,
                          date=sess.starts_at.astimezone(config.TZ).date(),
                          effort=effort, feeling=feeling, note=note))


def add_training_log(user_id: int, day: date, effort: int | None, note: str,
                     feeling: str | None = None) -> int:
    """Direct insert without a session link — seeds/legacy only; the app flow
    goes through add_session_feedback."""
    with session_scope() as s:
        entry = TrainingLog(user_id=user_id, date=day, effort=effort,
                            feeling=feeling, note=note)
        s.add(entry)
        s.flush()
        return entry.id


def delete_training_log(log_id: int, user_id: int) -> bool:
    """Clients delete only their OWN entries — user_id is part of the match."""
    with session_scope() as s:
        entry = s.scalar(select(TrainingLog).where(TrainingLog.id == log_id,
                                                   TrainingLog.user_id == user_id))
        if entry is None:
            return False
        s.delete(entry)
        return True


def training_logs(user_id: int) -> list[TrainingLog]:
    from sqlalchemy.orm import joinedload

    with session_scope() as s:
        return list(s.scalars(
            select(TrainingLog).where(TrainingLog.user_id == user_id)
            .options(joinedload(TrainingLog.session))    # rendered after the scope closes
            .order_by(TrainingLog.date.desc(), TrainingLog.id.desc())))


def booking_history(user_id: int, limit: int = 20) -> list[TrainingSession]:
    """Past booked sessions, newest first — the karton's 'personal calendar'."""
    with session_scope() as s:
        return list(s.scalars(
            select(TrainingSession).join(Booking, Booking.session_id == TrainingSession.id)
            .where(Booking.user_id == user_id,
                   TrainingSession.starts_at < datetime.now(config.TZ))
            .order_by(TrainingSession.starts_at.desc()).limit(limit)))


# ---------- training programmes (treninzi) ----------

def list_clients() -> list[User]:
    """Everyone the trainer can build a programme for."""
    with session_scope() as s:
        return list(s.scalars(select(User).where(~User.is_trainer)
                              .order_by(User.name, User.email)))


def assignments_for(user_id: int) -> list[ProgramAssignment]:
    """A client's handed-out trainings, newest date first (programme+items eager)."""
    from sqlalchemy.orm import selectinload

    with session_scope() as s:
        return list(s.scalars(
            select(ProgramAssignment).where(ProgramAssignment.user_id == user_id)
            .options(selectinload(ProgramAssignment.program).selectinload(Program.items))
            .order_by(ProgramAssignment.date.desc(), ProgramAssignment.id.desc())))


def client_can_view(program_id: int, user_id: int) -> bool:
    """A client may open a programme (and its media) only if it was assigned to them."""
    with session_scope() as s:
        return bool(s.scalar(select(func.count()).select_from(ProgramAssignment)
                             .where(ProgramAssignment.program_id == program_id,
                                    ProgramAssignment.user_id == user_id)))


def all_programs() -> list[tuple[Program, int, int]]:
    """Trainer library: every programme + item count + assignment count."""
    with session_scope() as s:
        items = (select(ProgramItem.program_id, func.count().label("n"))
                 .group_by(ProgramItem.program_id).subquery())
        assigns = (select(ProgramAssignment.program_id, func.count().label("n"))
                   .group_by(ProgramAssignment.program_id).subquery())
        rows = s.execute(
            select(Program, func.coalesce(items.c.n, 0), func.coalesce(assigns.c.n, 0))
            .join(items, items.c.program_id == Program.id, isouter=True)
            .join(assigns, assigns.c.program_id == Program.id, isouter=True)
            .order_by(Program.updated_at.desc())
        ).all()
        return [(p, ni, na) for p, ni, na in rows]


def assignments_overview(limit: int = 100) -> list[tuple[ProgramAssignment, Program, User]]:
    """Trainer view of hand-outs, newest date first."""
    with session_scope() as s:
        rows = s.execute(
            select(ProgramAssignment, Program, User)
            .join(Program, Program.id == ProgramAssignment.program_id)
            .join(User, User.id == ProgramAssignment.user_id)
            .order_by(ProgramAssignment.date.desc(), ProgramAssignment.id.desc())
            .limit(limit)
        ).all()
        return [(a, p, u) for a, p, u in rows]


def assign_program(program_id: int, user_id: int, on_date, note: str | None = None) -> bool:
    """Hand a programme to a client for a day. False on the (program, user, day)
    duplicate — assigning the same workout twice for the same day is a mistake,
    not a request."""
    from sqlalchemy.exc import IntegrityError

    try:
        with session_scope() as s:
            s.add(ProgramAssignment(program_id=program_id, user_id=user_id,
                                    date=on_date, note=note))
        return True
    except IntegrityError:
        return False


def unassign(assignment_id: int) -> bool:
    with session_scope() as s:
        a = s.get(ProgramAssignment, assignment_id)
        if a is None:
            return False
        s.delete(a)
        return True


def create_program(title: str, intro: str | None) -> int:
    with session_scope() as s:
        p = Program(title=title, intro=intro)
        s.add(p)
        s.flush()
        return p.id


def get_program(program_id: int) -> Program | None:
    from sqlalchemy.orm import selectinload

    with session_scope() as s:
        return s.scalar(select(Program).where(Program.id == program_id)
                        .options(selectinload(Program.items)))


def update_program(program_id: int, title: str, intro: str | None) -> None:
    with session_scope() as s:
        p = s.get(Program, program_id)
        if p is not None:
            p.title, p.intro = title, intro


def delete_program(program_id: int) -> list[str]:
    """Delete a programme; returns media filenames the caller should unlink."""
    with session_scope() as s:
        p = s.get(Program, program_id)
        if p is None:
            return []
        media = [i.media_name for i in p.items if i.media_name]
        s.delete(p)
        return media


def add_item(program_id: int, title: str, body: str | None,
             media_name: str | None, media_kind: str | None) -> int:
    with session_scope() as s:
        last = s.scalar(select(func.coalesce(func.max(ProgramItem.position), 0))
                        .where(ProgramItem.program_id == program_id))
        it = ProgramItem(program_id=program_id, position=last + 1, title=title,
                         body=body, media_name=media_name, media_kind=media_kind)
        s.add(it)
        s.get(Program, program_id).updated_at = func.now()
        s.flush()
        return it.id


def get_item(item_id: int) -> ProgramItem | None:
    with session_scope() as s:
        return s.get(ProgramItem, item_id)


def update_item(item_id: int, title: str, body: str | None,
                media_name: str | None = None, media_kind: str | None = None) -> str | None:
    """Update text; if new media given, swap it in and return the OLD filename."""
    with session_scope() as s:
        it = s.get(ProgramItem, item_id)
        if it is None:
            return None
        old = None
        it.title, it.body = title, body
        if media_name:
            old = it.media_name
            it.media_name, it.media_kind = media_name, media_kind
        return old


def delete_item(item_id: int) -> str | None:
    """Delete an item; returns its media filename for the caller to unlink."""
    with session_scope() as s:
        it = s.get(ProgramItem, item_id)
        if it is None:
            return None
        media = it.media_name
        pid = it.program_id
        s.delete(it)
        s.flush()
        # close the gap so positions stay 1..n and moves keep working
        for i, row in enumerate(s.scalars(
                select(ProgramItem).where(ProgramItem.program_id == pid)
                .order_by(ProgramItem.position)), start=1):
            row.position = i
        return media


def move_item(item_id: int, direction: str) -> None:
    """Swap an item with its neighbour ("up" | "down")."""
    with session_scope() as s:
        it = s.get(ProgramItem, item_id)
        if it is None:
            return
        rows = list(s.scalars(select(ProgramItem)
                              .where(ProgramItem.program_id == it.program_id)
                              .order_by(ProgramItem.position)))
        idx = next(i for i, r in enumerate(rows) if r.id == item_id)
        j = idx - 1 if direction == "up" else idx + 1
        if 0 <= j < len(rows):
            rows[idx].position, rows[j].position = rows[j].position, rows[idx].position


def media_owner_program(media_name: str) -> Program | None:
    """Which programme owns this media file? (for the auth-gated /media route)"""
    with session_scope() as s:
        it = s.scalar(select(ProgramItem).where(ProgramItem.media_name == media_name))
        return s.get(Program, it.program_id) if it else None
