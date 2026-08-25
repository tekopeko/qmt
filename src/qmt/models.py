"""SQLAlchemy ORM. One booking mechanism for everything QMT runs:

a `TrainingSession` with `capacity=8` is a group class, with `capacity=1` it is a
1:1 termin (personal training, rehab) — no separate appointment system. Sessions
are either generated from a weekly `SessionTemplate` (the standing timetable) or
created one-off.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, text,
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
