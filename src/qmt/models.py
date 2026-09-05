"""SQLAlchemy ORM. One booking mechanism for everything QMT runs:

a `TrainingSession` with `capacity=8` is a group class, with `capacity=1` it is a
1:1 termin (personal training, rehab) — no separate appointment system. Sessions
are either generated from a weekly `SessionTemplate` (the standing timetable) or
created one-off.
"""

from __future__ import annotations

from datetime import date as SADate, datetime, timedelta

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, func, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Session kinds double as the bookable membership plans; "online" and "prehrana"
# are plans without sessions (course access / nutrition tracking, billed apart).
SESSION_KINDS = ("grupni", "individualni", "poluindividualni", "rehabilitacija")
PLAN_TYPES = SESSION_KINDS + ("online", "prehrana")
PLAN_LABELS = {
    "grupni": "Grupni trening",
    "individualni": "Individualni trening",
    "poluindividualni": "Poluindividualni trening",
    "rehabilitacija": "Rehabilitacija",
    "online": "Online trening",
    "prehrana": "Prehrana",
}
# Post-training feedback (the Strava pattern): RPE number + how it felt.
FEELING_LABELS = {"slabo": "Slabo", "dobro": "Dobro", "odlicno": "Odlično"}

# Two-letter badges for tight tables (korisnici); legend renders from this.
PLAN_ABBR = {
    "grupni": "GT",
    "individualni": "IT",
    "poluindividualni": "PI",
    "rehabilitacija": "RH",
    "online": "OT",
    "prehrana": "PR",
}


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    # `name` predates the profile and holds the FIRST name; the rest of the
    # basic info (profil page) lives in the columns below, all optional at
    # signup — login nudges clients to /profil until prezime + datum are in.
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    birth_date: Mapped[SADate | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # The trainer runs the timetable and sees rosters; clients only see their own
    # bookings. Same one-owner shape as mojimakrosi's is_admin.
    is_trainer: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    # Sign-up proves nothing about inbox ownership until this is true; login
    # refuses unverified accounts (same contract as mojimakrosi).
    email_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def full_name(self) -> str | None:
        return " ".join(p for p in (self.name, self.last_name) if p) or None

    @property
    def profile_complete(self) -> bool:
        return bool(self.name and self.last_name and self.birth_date)


class SessionTemplate(Base):
    """A standing weekly timetable entry ("Grupni trening, pon 18:00, 8 mjesta").

    Concrete sessions are materialized from templates lazily when a week is first
    viewed — no cron needed, and editing a template only affects weeks nobody has
    opened yet (already-materialized sessions keep their own row and bookings).
    """

    __tablename__ = "session_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), server_default=text("'grupni'"), default="grupni")
    weekday: Mapped[int] = mapped_column(Integer)          # 0 = ponedjeljak
    start_min: Mapped[int] = mapped_column(Integer)        # minutes from midnight, local
    duration_min: Mapped[int] = mapped_column(Integer, server_default=text("60"), default=60)
    capacity: Mapped[int] = mapped_column(Integer, server_default=text("8"), default=8)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("session_templates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), server_default=text("'grupni'"), default="grupni")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_min: Mapped[int] = mapped_column(Integer, server_default=text("60"), default=60)
    capacity: Mapped[int] = mapped_column(Integer, server_default=text("8"), default=8)
    # Cancelled sessions stay visible (crossed out) rather than vanishing — people
    # remember "there was a training here" and an empty gap looks like a bug.
    canceled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # A template must generate a given occurrence at most once (the lazy
    # materializer runs on every week view, possibly concurrently).
    __table_args__ = (UniqueConstraint("template_id", "starts_at", name="uq_session_template_start"),)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="session")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "session_id", name="uq_booking_user_session"),)

    session: Mapped[TrainingSession] = relationship(back_populates="bookings")
    user: Mapped[User] = relationship()


class Membership(Base):
    """One paid plan for one client — the manual precursor to real payments.

    The trainer records each uplata by hand (cash or card at the gym); dates do
    the gating. `next_payment` lands a month after a payment, dospijeće (the
    grace deadline) a week after that, and the plan admits booking of its
    session kind until dospijeće passes.
    """

    __tablename__ = "memberships"

    GRACE_DAYS = 7

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan: Mapped[str] = mapped_column(String(20))          # one of PLAN_TYPES
    paid_on: Mapped[SADate] = mapped_column(Date)
    next_payment: Mapped[SADate] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "plan", name="uq_membership_user_plan"),)

    user: Mapped[User] = relationship()

    @property
    def dospijece(self) -> SADate:
        return self.next_payment + timedelta(days=self.GRACE_DAYS)

    def is_active(self, today: SADate) -> bool:
        return today <= self.dospijece


PAYMENT_METHODS = {"gotovina": "Gotovina", "kartica": "Kartica", "stripe": "Stripe"}


class ReminderLog(Base):
    """One row per reminder actually sent — the idempotency ledger.

    `ref` pins the reminder to its occasion (plan + cycle date, or a session
    id), so a client is nagged once per dospijeće and once per termin, never
    once per daily run. Claim-then-send: the unique constraint is what makes
    a concurrent double-run harmless.
    """

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12))          # 'clanarina' | 'termin'
    ref: Mapped[str] = mapped_column(String(60))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "kind", "ref", name="uq_reminder_once"),)


class Payment(Base):
    """Immutable ledger: one row per uplata, nothing ever overwrites it.

    Memberships hold only the CURRENT cycle (paid_on/next_payment get
    replaced on renewal); the owner's traffic reporting — how many payments,
    which plan, cash vs card — needs history, and later the Stripe webhook
    writes here too. `amount_eur` stays NULL until prices exist. The user FK
    is SET NULL: deleting an account must not delete the accounting trail.
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    plan: Mapped[str] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(12), server_default=text("'gotovina'"),
                                        default="gotovina")   # PAYMENT_METHODS key
    amount_eur = mapped_column(Numeric(8, 2), nullable=True)
    paid_on: Mapped[SADate] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User | None] = relationship()


class OnboardingResponse(Base):
    """A client's online-trening upitnik: raw answers + the computed routing.

    One row per user — refilling overwrites (the routing should reflect the
    CURRENT state, and the karton is not an archive of old self-assessments).
    Answers are stored as JSON {question key: chosen option index} so the
    karton can re-render them against qmt.upitnik.QUESTIONS.
    """

    __tablename__ = "onboarding_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    answers: Mapped[str] = mapped_column(Text)             # JSON: {key: option index}
    score: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(12))         # pocetna | srednja | napredna
    goal: Mapped[str] = mapped_column(String(12))          # cijelo | gornji | donji
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship()


class TrainingLog(Base):
    """One karton entry: the client's post-training feedback.

    Created by the FEEDBACK flow, not free-form: once a booked termin ends,
    the karton prompts "Kako je bilo?" for exactly that session (the Strava
    pattern) — effort (RPE 1–10), feeling, optional comment. `session_id`
    stays nullable for legacy/manual rows; at most one feedback per
    (user, session).
    """

    __tablename__ = "training_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    date: Mapped[SADate] = mapped_column(Date, index=True)
    effort: Mapped[int | None] = mapped_column(Integer, nullable=True)   # RPE 1–10
    feeling: Mapped[str | None] = mapped_column(String(10), nullable=True)  # FEELING_LABELS key
    note: Mapped[str] = mapped_column(Text)
    # "nisam bio/la" — the client's OWN absence, recorded instead of an osvrt.
    # Never TrainingSession.canceled: that termin belongs to seven other people.
    absent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "session_id", name="uq_training_log_user_session"),)

    user: Mapped[User] = relationship()
    session: Mapped[TrainingSession | None] = relationship()


class Program(Base):
    """An online course variant: fixed (razina × cilj) slots, matched, not
    assigned.

    The online side is AUTOMATED — the upitnik routes a client into a razina
    and a cilj, and they see exactly the programmes tagged with that combo.
    The trainer edits the content of the nine skeleton slots (created by
    `db.ensure_online_skeletons`); no per-client hand-outs anywhere.
    """

    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    level: Mapped[str | None] = mapped_column(String(12), nullable=True)   # upitnik.LEVELS key
    goal: Mapped[str | None] = mapped_column(String(12), nullable=True)    # upitnik.GOALS key
    intro: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["ProgramItem"]] = relationship(
        back_populates="program", cascade="all, delete-orphan", order_by="ProgramItem.position"
    )


class ProgramItem(Base):
    """One exercise/step of a programme: title + instructions + optional media.

    Media is an uploaded file (image or video) stored under data/uploads and
    served only through the auth-gated /media route — programmes are personal.
    """

    __tablename__ = "program_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    media_kind: Mapped[str | None] = mapped_column(String(8), nullable=True)  # "img" | "video"

    program: Mapped[Program] = relationship(back_populates="items")
