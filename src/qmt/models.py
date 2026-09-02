"""SQLAlchemy ORM. One booking mechanism for everything QMT runs:

a `TrainingSession` with `capacity=8` is a group class, with `capacity=1` it is a
1:1 termin (personal training, rehab) — no separate appointment system. Sessions
are either generated from a weekly `SessionTemplate` (the standing timetable) or
created one-off.
"""

from __future__ import annotations

from datetime import date as SADate, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # The trainer runs the timetable and sees rosters; clients only see their own
    # bookings. Same one-owner shape as mojimakrosi's is_admin.
    is_trainer: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    # Sign-up proves nothing about inbox ownership until this is true; login
    # refuses unverified accounts (same contract as mojimakrosi).
    email_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SessionTemplate(Base):
    """A standing weekly timetable entry ("Grupni trening, pon 18:00, 8 mjesta").

    Concrete sessions are materialized from templates lazily when a week is first
    viewed — no cron needed, and editing a template only affects weeks nobody has
    opened yet (already-materialized sessions keep their own row and bookings).
    """

    __tablename__ = "session_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
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


class Program(Base):
    """A training programme in the trainer's LIBRARY — content, not ownership.

    Programmes are reusable: the trainer builds one (ordered `ProgramItem`s of
    text + media) and then hands it out via `ProgramAssignment` — this
    programme, this client, this day. A client sees a programme only through
    an assignment; the library itself is trainer-only.
    """

    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    intro: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["ProgramItem"]] = relationship(
        back_populates="program", cascade="all, delete-orphan", order_by="ProgramItem.position"
    )
    assignments: Mapped[list["ProgramAssignment"]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )


class ProgramAssignment(Base):
    """One hand-out: programme X for client Y on day Z.

    The same programme may be assigned to many clients and to the same client
    on many days (repeating a workout is normal) — but only once per
    (programme, client, day).
    """

    __tablename__ = "program_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[SADate] = mapped_column(Date, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("program_id", "user_id", "date", name="uq_assignment_program_user_date"),
    )

    program: Mapped[Program] = relationship(back_populates="assignments")
    user: Mapped["User"] = relationship()


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
