"""SQLAlchemy ORM. One booking mechanism for everything QMT runs:

a `TrainingSession` with `capacity=8` is a group class, with `capacity=1` it is a
1:1 termin (personal training, rehab) — no separate appointment system. Sessions
are either generated from a weekly `SessionTemplate` (the standing timetable) or
created one-off.
"""

from __future__ import annotations

import json
from datetime import date as SADate, datetime, timedelta

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Table, Text,
    UniqueConstraint, func, text, text as sql_text,
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
# The online plan is sold in three tiers (20.10.2026), the landing's three
# QMove cards: Membership.tier holds one of them for an online membership.
# A tier's name everywhere in the app is its card's title slot,
# "<slot>.title" in src/qmt/copy.py ("QMove START" by default), as the gym
# owner typed it: renaming a card renames the tier on every page.
ONLINE_TIERS = ("start", "pro", "elite")
ONLINE_TIER_SLOTS = {"start": "offer.online", "pro": "offer.online2", "elite": "offer.online3"}

# Post-training feedback (the Strava pattern): RPE number + how it felt.
FEELING_LABELS = {"slabo": "Slabo", "dobro": "Dobro", "odlicno": "Odlično"}

# An online programme's day (30.10.2026, ProgramDay): its three sections, in
# the day's order (the dict's order), each item in one of them; and the
# weekday a day suggests, 0 = ponedjeljak (a suggestion, never a gate).
SECTIONS = {"zagrijavanje": "Zagrijavanje", "trening": "Trening", "istezanje": "Istezanje"}
WEEKDAYS = ("ponedjeljak", "utorak", "srijeda", "četvrtak", "petak", "subota", "nedjelja")


def plural(n: int, one: str, few: str, many: str) -> str:
    """The noun after a count, as Croatian says it: `one` after 1, 21, 31 …
    (not 11), `few` after 2–4, 22–24 … (not 12–14), `many` after the rest
    ("1 dan", "3 dana", "5 dana"; "1 vježba", "2 vježbe", "7 vježbi")."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


# Two-letter badges for tight tables (korisnici); legend renders from this.
PLAN_ABBR = {
    "grupni": "GT",
    "individualni": "IT",
    "poluindividualni": "PI",
    "rehabilitacija": "RH",
    "online": "OT",
    "prehrana": "PR",
}


def add_month(d: SADate) -> SADate:
    """Same day next month, clamped to month length (31.1. → 28.2.)."""
    import calendar
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return SADate(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def sub_month(d: SADate) -> SADate:
    """Same day previous month, clamped (31.3. → 28.2.)."""
    import calendar
    y, m = (d.year - 1, 12) if d.month == 1 else (d.year, d.month - 1)
    return SADate(y, m, min(d.day, calendar.monthrange(y, m)[1]))


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
    # One Stripe Customer per account, created on the first checkout and reused
    # for every subscription and the billing portal after that.
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
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
    # Set while a Stripe subscription renews this plan; cleared when Stripe
    # reports it deleted. The DATES still gate access — a cancelled
    # subscription just stops extending them, and the plan lapses on its own.
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    # The shop sells grupni as 8/12/16 treninga a month; NULL means unlimited
    # (every other plan, and cash uplate recorded without a tier).
    sessions_per_cycle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The online plan's tier (20.10.2026): one of ONLINE_TIERS, the
    # landing's QMove card that is the member's, for an online membership;
    # NULL for every other plan. Each uplata restates it (db.record_payment);
    # a NULL on an online row reads as "start", the base tier.
    tier: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "plan", name="uq_membership_user_plan"),)

    @property
    def auto_renew(self) -> bool:
        return bool(self.stripe_subscription_id) and not self.cancel_at_period_end

    def cycle_bounds(self, on: SADate) -> tuple[SADate, SADate]:
        """[start, end) of the monthly cycle containing `on`.

        Anchored on `next_payment`, not `paid_on`: paying early moves paid_on
        but keeps the cycle grid, so the paid month is always exactly
        [next_payment − 1 mj, next_payment) and quotas never smear across an
        early renewal. Dates beyond next_payment fall into the following
        window — booking ahead spends next month's quota, not this month's.
        """
        start, end = sub_month(self.next_payment), self.next_payment
        while on >= end:
            start, end = end, add_month(end)
        while on < start:
            start, end = sub_month(start), start
        return start, end

    user: Mapped[User] = relationship()

    @property
    def dospijece(self) -> SADate:
        return self.next_payment + timedelta(days=self.GRACE_DAYS)

    def is_active(self, today: SADate) -> bool:
        return today <= self.dospijece


PAYMENT_METHODS = {"gotovina": "Gotovina", "kartica": "Kartica", "stripe": "Stripe"}


class SiteCopy(Base):
    """A text the trainer or owner edited in place. One row per edited slot;
    no row means the template's default (src/qmt/copy.py). The key is the
    slot name, the text is already cleaned (copy.clean)."""

    __tablename__ = "site_copy"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Announcement(Base):
    """One of the landing's announcements (#aktualno, in the hero: a new
    group, a course). Since 18.10.2026 a row the trainer or owner adds,
    hides and deletes in edit mode, at most db.MAX_ANNOUNCEMENTS of them;
    before, two fixed sets of copy slots (event1.* / event2.*, which
    migration b48179fcf538 turned into the first two rows). Its texts are
    edited in place like copy, through virtual keys aktualno.<id>.<field>
    (app.py, copy_save), cleaned as copy is (copy.clean); an emptied one
    stays empty since 20.10.2026, and Zadano puts its placeholder back
    (copy.ANNOUNCEMENT_BLANK).
    `position` is the editor's order, 1-based: the order the landing shows
    them in. A new card comes last, and since 29.10.2026 his ↑ / ↓ swap a
    card with its neighbour (db.move_announcement; the owner: "Lets make it
    so that Amir can change the order of these announcement pages"), which
    is why the constraint is deferred, as the upitnik's: a swap is checked
    when it commits, whole (migration b18ebed39701). A deleted card leaves a
    gap. `shown` is the switch: a hidden card is on an editor's page only.
    `image` is the stored photo's file name (served by /slika), or NULL: a
    plain card."""

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    shown: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
    tag: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    title: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    # "when" is a keyword in too many places (SQL's CASE among them)
    when_text: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    body: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    cta: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    image: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # deferred: ↑ / ↓ swap two positions, checked when the swap commits
    __table_args__ = (UniqueConstraint("position", name="uq_announcements_position", deferrable=True,
                                       initially="DEFERRED"),)


class GymCard(Base):
    """One of the landing's gym cards (#dvorana, the section under the online
    tiers: Dvorana, Individualno, and what the gym owner adds beside them,
    "Treninzi za penziće", "Pilates za cure"). Since 20.10.2026 a row the
    trainer or owner adds, hides and deletes in edit mode, at most
    db.MAX_GYM_CARDS of them, as he does the announcements; before, two
    fixed sets of copy slots (offer.dvorana.* / offer.individualno.*, which
    migration 78d539161185 turned into the first two rows). Its texts are
    edited in place like copy, through virtual keys dvorana.<id>.<field>
    (app.py, copy_save), cleaned as copy is (copy.clean); an emptied one
    stays empty since 20.10.2026, and Zadano puts its placeholder back
    (copy.GYM_CARD_BLANK). `points`
    is its bullets, a JSON array of strings, as a ListSlot's site_copy row
    holds them, and `extra` its extra lines under them the same way
    (20.10.2026: plain lines, none until the editor adds one; migration
    c138157ff6bb). `plans` is the plans the card stands for, comma-separated
    ("grupni", "individualni,poluindividualni,rehabilitacija"), "" for
    none: the first prices the card (its price.<plan>.* slots, the ones
    /moja-clanarina prints), the others are the muted line under that
    price, and the button follows them. A card with none (every card the
    owner adds: nothing edits `plans` in place) is his text alone, `price`
    and `unit` its monthly price, `year_price` / `year_unit` its yearly
    one, its button the contact. A card with plans prints its first plan's
    yearly slots too since 21.10.2026 (price.<plan>.year_amount /
    .year_unit, migration 6e2b9d41c7a3), so its own yearly columns are not
    read. `position` is creation order, 1-based; `shown` the switch: a
    hidden card is on an editor's page only."""

    __tablename__ = "gym_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    shown: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
    title: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    lead: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    points: Mapped[str] = mapped_column(Text, server_default=text("'[]'"), default="[]")
    extra: Mapped[str] = mapped_column(Text, server_default=text("'[]'"), default="[]")
    price: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    unit: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    year_price: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    year_unit: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    plans: Mapped[str] = mapped_column(String(80), server_default=text("''"), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (UniqueConstraint("position", name="uq_gym_cards_position"),)

    @property
    def plan_keys(self) -> list[str]:
        """The plans, in order: the first prices the card. [] for a card
        that stands for none; a key that is no plan is left out."""
        return [p for p in (k.strip() for k in (self.plans or "").split(",")) if p in PLAN_TYPES]

    @property
    def point_items(self) -> list[str]:
        """The bullets: the points column read (list_items)."""
        return self.list_items("points")

    @property
    def extra_items(self) -> list[str]:
        """The extra lines under the bullets: the extra column read (list_items)."""
        return self.list_items("extra")

    def list_items(self, column: str) -> list[str]:
        """A list column read, points or extra: a JSON array of strings
        (copy.dump_items writes it); [] when it holds none, or none that
        can be read."""
        try:
            data = json.loads(getattr(self, column) or "[]")
        except ValueError:
            return []
        return [x for x in data if isinstance(x, str) and x] if isinstance(data, list) else []


class UpitnikQuestion(Base):
    """One question of the online-trening upitnik (/upitnik). Since
    26.10.2026 a row the trainer or owner adds, removes, hides, reorders and
    classifies in edit mode, at most db.MAX_UPITNIK_QUESTIONS of them (the
    owner: "so that Amir can also add or remove questions from the
    questionnaire"); until then the gym owner's fifteen were fixed in code
    (qmt.upitnik) and only their words were copy slots (upitnik.q<n>.*,
    which migration 3f8a6c2d9b71 turned into rows 1–15, their ids kept).

    The id is the answers' key: a client's answer is stored as "q<id>"
    (OnboardingResponse.answers), so ids come from a sequence and are never
    reused, and a question deleted or hidden since still names its old
    answers on the karton (qmt.upitnik.answer_rows).
    Its texts are edited in place like copy, through virtual keys
    upitnik.<id>.<field> (app.py, copy_save; copy.UPITNIK_QUESTION_SLOTS),
    cleaned as copy is (copy.clean); an emptied one stays empty, and Zadano
    puts a new question's placeholder back (copy.UPITNIK_BLANK). Its
    settings go through POST /upitnik/pitanje/{id} (qmt.upitnik.settings
    holds their rules).

    `position` is the order on the page, 1-based (a deleted row leaves a
    gap; ↑ / ↓ swap two rows, which is why the constraint is deferred: a
    swap is checked when it commits, whole). `part` is 1–4, the heading
    above it (the upitnik.part<n>.h slots). `kind` is what it asks: choice
    (one option), multi (several), scale (1–10), yesno or text. `options`
    are a choice's (and a multi's), a JSON array as a list slot's row holds
    them; `low` / `high` a scale's two ends. `scoring` is the group a
    scale's answer joins in the score, "" (none), "baza" or "navike"; only
    a scale scores. `role` makes it one of the two safety questions, ""
    (none), "pain" (a scale) or "injuries" (a yes / no), at most one row of
    each (the partial unique index). `shown` is the switch: a hidden
    question is asked of nobody and scores nothing, and stays on the
    editor's page.

    Since 27.10.2026 any question may be asked only after a given answer
    to an earlier one (the owner: "if the answer is yes, he would like to
    again ask if she had it in the last year and then if she says yes …
    if it was C-section or not"): `parent_id` is the question it depends
    on and `condition` that question's answer which asks it, "" when it is
    asked always: "yes" / "no" for a yes / no, an option's text for a
    choice or a multi (asked when it is among the answers), ">=N" for a
    scale (N 1–10). Chains are questions whose parent depends on another.
    A parent deleted nulls parent_id (ON DELETE SET NULL) and leaves the
    condition, so the editor's line can say the condition no longer holds:
    such a question, and one whose parent is placed after it or cannot be
    given that answer any more, is asked always; one whose parent is
    hidden (or under a hidden one) is asked of nobody (qmt.upitnik.steps:
    void, muted). The two roles' follow-ups ("Gdje te boli?",
    "Opiši ukratko.", a followup_text column until then) became such
    questions that day (migration 5c1e7a9d2b48)."""

    __tablename__ = "upitnik_questions"
    # `text` is a column of this class: SQLAlchemy's text() is sql_text in its body

    id: Mapped[int] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    part: Mapped[int] = mapped_column(Integer, server_default=sql_text("2"), default=2)
    kind: Mapped[str] = mapped_column(String(8), server_default=sql_text("'scale'"), default="scale")
    text: Mapped[str] = mapped_column(Text, server_default=sql_text("''"), default="")
    options: Mapped[str] = mapped_column(Text, server_default=sql_text("'[]'"), default="[]")
    low: Mapped[str] = mapped_column(Text, server_default=sql_text("''"), default="")
    high: Mapped[str] = mapped_column(Text, server_default=sql_text("''"), default="")
    scoring: Mapped[str] = mapped_column(String(8), server_default=sql_text("''"), default="")
    role: Mapped[str] = mapped_column(String(10), server_default=sql_text("''"), default="")
    shown: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"), default=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("upitnik_questions.id", ondelete="SET NULL"),
                                                  nullable=True)
    condition: Mapped[str] = mapped_column(String(80), server_default=sql_text("''"), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        UniqueConstraint("position", name="uq_upitnik_questions_position", deferrable=True, initially="DEFERRED"),
        Index("uq_upitnik_questions_role", "role", unique=True, postgresql_where=sql_text("role <> ''")),
    )

    @property
    def option_items(self) -> list[str]:
        """The options: the options column read, a JSON array of strings
        (copy.dump_items writes it); [] when it holds none, or none that can
        be read."""
        try:
            data = json.loads(self.options or "[]")
        except ValueError:
            return []
        return [x for x in data if isinstance(x, str) and x] if isinstance(data, list) else []


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
    # Stripe delivers webhooks at-least-once; the invoice id's uniqueness is
    # what turns a redelivery into a no-op instead of a second month.
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User | None] = relationship()


class OnboardingResponse(Base):
    """A client's online-trening upitnik: raw answers + the computed routing.

    One row per user — refilling overwrites (the routing should reflect the
    CURRENT state, and the karton is not an archive of old self-assessments).
    `version` says which questionnaire the row answers (qmt.upitnik):
    2 since 26.10.2026, the gym owner's questions (UpitnikQuestion rows
    since the same day), answers as JSON {"q<the question's id>": the
    option's text, a multi's list of texts, a scale's int, yes / no's bool,
    a free text; until 27.10.2026 a role follow-up's "q<id>b", which
    migration 5c1e7a9d2b48 renamed to its new question's key}, kept as
    given whatever becomes of the questions, a score of 10 to one decimal
    (0.0 when no question scored), the goal always "cijelo" (the level
    alone routes) and the safety flags; 1 for a row from before, {key: the
    option's index} read against qmt.upitnik.QUESTIONS_V1, an integer
    score of 14, its goal its own.
    """

    __tablename__ = "onboarding_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    answers: Mapped[str] = mapped_column(Text)             # JSON, by version (above)
    # "6,4 / 10" since version 2; a version-1 row's whole points stay as they were
    score: Mapped[float] = mapped_column(Numeric(4, 1, asdecimal=False))
    level: Mapped[str] = mapped_column(String(12))         # pocetna | srednja | napredna
    goal: Mapped[str] = mapped_column(String(12))          # cijelo | gornji | donji
    version: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    pain_level: Mapped[int | None] = mapped_column(Integer, nullable=True)        # the pain question's 1–10, if asked
    # the pain question at 7 or more: početna whatever the score, and the client sees the trainer first
    pain_high: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # the injuries question's yes (injuries, operations, conditions): the trainer looks at the profile
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # the consent to process health data, ticked under the questionnaire
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


# Two exercises of the library a client may swap one for the other (the
# spec's stage 3, "Zamijeni vježbu — Slične vježbe"; Amir ticks them on an
# exercise's form, 30.10.2026). ONE row per pair, stored from the side whose
# form ticked the other, read from both (Exercise.alternatives); unticked on
# either form, the pair goes whichever way it was stored (db.update_exercise).
# Either exercise deleted takes its pairs with it.
exercise_alternatives = Table(
    "exercise_alternatives", Base.metadata,
    Column("exercise_id", ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True),
    Column("alternative_id", ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True),
    CheckConstraint("exercise_id <> alternative_id", name="ck_exercise_alternatives_other"),
    Index("ix_exercise_alternatives_alternative_id", "alternative_id"),
)

# The Croatian alphabet's letters in their order (q, w, x and y in their
# Latin places): č and ć come after c, đ after d, š after s, ž after z.
_ALPHABET = "abcčćdđefghijklmnopqrsštuvwxyzž"


def alpha_key(text: str) -> tuple[int, ...]:
    """A sort key that puts names in the alphabet's order, whatever their
    case: "Čučanj" after every "C…" and before "D…". The databases sort by
    code point under the C locale (the dev and test ones), which puts every
    Č, Š and Ž after Z. A letter with another mark (é, ü) sorts as its base
    letter; a space, a digit or a sign before every letter."""
    import unicodedata

    key = []
    for ch in text.casefold():
        base = ch if ch in _ALPHABET else unicodedata.normalize("NFD", ch)[:1]
        key.append(1000 + _ALPHABET.index(base) if base and base in _ALPHABET else ord(ch))
    return tuple(key)


class Exercise(Base):
    """One exercise of the library (/treninzi/vjezbe, 30.10.2026; the owner:
    "We should have a database of exercises which he can choose from and add
    them to different training programmes that will be modular. Each exercise
    will have a video connected to it which will show the exercise and show
    what one rep means."). A programme's items point at these rows (since
    30.10.2026 its days' items, ProgramDayItem.exercise_id), so an exercise
    renamed or given a new clip is renamed and re-shown in every programme
    that holds it, and one that a programme holds cannot be deleted
    (db.delete_exercise; the foreign key is RESTRICT). Migration 4c2e8a6f1d39
    made the items typed by hand until then into these rows.

    `name` is unique whatever its case: db.create_exercise / update_exercise
    compare the names casefolded under the table's lock (the rule, with the
    Croatian sentence), and uq_exercises_name, on lower(name), backs them
    wherever the database folds the letter (the C locale folds ASCII only).
    `instructions` is how it is done and `rep_note` what one rep is, "" for
    none. `video` is the stored clip's file name (storage.py), served only by
    the auth-gated /media, NULL for none. `tags` are free words as Amir types
    them, comma-separated, stored cleaned (db.clean_tags: "noge, bučice"), ""
    for none; the later routing by equipment is to read them.
    """

    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    instructions: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    rep_note: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    video: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tags: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # the pairs this side stored, and those the other side stored: read
    # together as `alternatives`, loaded by the query that needs them
    # (db.exercise), written only through the table (db.update_exercise)
    alternatives_to: Mapped[list["Exercise"]] = relationship(
        secondary=exercise_alternatives, viewonly=True,
        primaryjoin=lambda: Exercise.id == exercise_alternatives.c.exercise_id,
        secondaryjoin=lambda: Exercise.id == exercise_alternatives.c.alternative_id)
    alternatives_from: Mapped[list["Exercise"]] = relationship(
        secondary=exercise_alternatives, viewonly=True,
        primaryjoin=lambda: Exercise.id == exercise_alternatives.c.alternative_id,
        secondaryjoin=lambda: Exercise.id == exercise_alternatives.c.exercise_id)

    @property
    def alternatives(self) -> list["Exercise"]:
        """The similar exercises, whichever side stored the pair: the union
        of both directions, in the alphabet's order."""
        both = {e.id: e for e in [*self.alternatives_to, *self.alternatives_from]}
        return sorted(both.values(), key=lambda e: alpha_key(e.name))

    @property
    def tag_items(self) -> list[str]:
        """The tags, one word or phrase each: the tags column read."""
        return [t for t in (x.strip() for x in (self.tags or "").split(",")) if t]


Index("uq_exercises_name", func.lower(Exercise.name), unique=True)


class Program(Base):
    """An online course variant: tagged with a (razina × cilj) combo,
    matched, not assigned.

    The online side is AUTOMATED — the upitnik routes a client into a razina
    and a cilj, and they see exactly the programmes tagged with that combo.
    Every programme is the trainer's own (30.10.2026: no default slots, no
    default exercises, nothing refilled; one with no day, or a day with no
    exercise, stays so until he changes it); no per-client hand-outs
    anywhere. Since 30.10.2026 a programme is a list of days (ProgramDay),
    each day its exercises in three sections (ProgramDayItem).
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

    days: Mapped[list["ProgramDay"]] = relationship(
        back_populates="program", cascade="all, delete-orphan", order_by="ProgramDay.position"
    )


class ProgramDay(Base):
    """One day of a programme (30.10.2026, stage 2 of
    roadmap/2026-10-29-online-treninzi-spec.md; the owner: "Dan 1, … Dan N
    with suggested days in the week but the user can do them whenever he
    wants"). Until then a programme was a flat list of items, which
    migration 7c3bf996c983 made its Dan 1.

    `position` is its number, 1-based and dense ("Dan 2": db.delete_day
    closes the gap), unique per programme; Amir's ↑ / ↓ swap two days'
    positions in one flush (db.move_day), which is why the constraint is
    deferred, as the announcements' is: a swap is checked when it commits,
    whole. `title` is optional ("Cijelo tijelo"), "" for none; `weekday` the
    day of the week it suggests, 0 = ponedjeljak … 6 = nedjelja (WEEKDAYS),
    NULL for none: a suggestion, never a gate. `intro` is Amir's words for
    the day (its line breaks kept), `intro_video` a stored clip's file name
    (storage.py, served only by the auth-gated /media, as an exercise's),
    NULL for none: "always watch the intro video first", the guide says.
    The spec's full training video is left out (a file over VIDEO_MAX_MB
    cannot pass Cloudflare)."""

    __tablename__ = "program_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160), server_default=text("''"), default="")
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intro: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    intro_video: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())

    # deferred: ↑ / ↓ swap two positions, checked when the swap commits
    __table_args__ = (UniqueConstraint("program_id", "position", name="uq_program_days_position",
                                       deferrable=True, initially="DEFERRED"),)

    program: Mapped[Program] = relationship(back_populates="days")
    items: Mapped[list["ProgramDayItem"]] = relationship(
        back_populates="day", cascade="all, delete-orphan", order_by="ProgramDayItem.position"
    )

    @property
    def label(self) -> str:
        """"Dan 1", or "Dan 1 · Cijelo tijelo" with a title."""
        return f"Dan {self.position}" + (f" · {self.title}" if self.title else "")

    @property
    def by_section(self) -> dict[str, list["ProgramDayItem"]]:
        """The items per section, in SECTIONS' order, each section's in
        position order: the day's display order. A section with none holds
        an empty list."""
        out: dict[str, list[ProgramDayItem]] = {key: [] for key in SECTIONS}
        for it in self.items:                          # in position order
            if it.section in out:
                out[it.section].append(it)
        return out


class ProgramDayItem(Base):
    """One exercise of a day, in its place (30.10.2026; the owner: per
    exercise "sets × reps, or seconds, rest between sets, a note. That is it
    for now"): a library row (Exercise: the name, the instructions, what one
    rep is, the clip) and what the day asks of it.

    `section` is one of SECTIONS (zagrijavanje, trening, istezanje; the
    owner: "warm up and main", Shape's third allowed and may stay empty).
    `position` is unique across the day, and the day reads its items section
    by section in SECTIONS' order, each section in position order (the
    display order, ProgramDay.by_section); a gap a deleted item left does
    not matter, and an item moved to another section goes last in it
    (db.update_day_item). The constraint is deferred so ↑ / ↓ swap two in
    one commit. `sets`, `reps` or `seconds` (one of the two: the CHECK),
    `rest_seconds` (the rest between sets) and `rest_after_seconds` (the
    rest after the exercise, before the next one; 30.10.2026, the player's
    rest timers) are NULL when not set, `note` "" for none ("8 kg", "po
    nozi"). Migration 7c3bf996c983 parsed each old item's note, its razina's
    dose ("3 × 8 · 8 kg"), into these.

    The exercise's foreign key is RESTRICT: an exercise a day holds cannot be
    deleted (db.delete_exercise says where it is first)."""

    __tablename__ = "program_day_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    day_id: Mapped[int] = mapped_column(ForeignKey("program_days.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(12), server_default=text("'trening'"), default="trening")
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="RESTRICT"), index=True)
    sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rest_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # the rest before the next exercise (migration 4f9d6f7103ad)
    rest_after_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")

    __table_args__ = (
        # deferred: ↑ / ↓ swap two positions, checked when the swap commits
        UniqueConstraint("day_id", "position", name="uq_program_day_items_position",
                         deferrable=True, initially="DEFERRED"),
        CheckConstraint("section IN ('zagrijavanje', 'trening', 'istezanje')", name="ck_program_day_items_section"),
        CheckConstraint("reps IS NULL OR seconds IS NULL", name="ck_program_day_items_reps_or_seconds"),
    )

    day: Mapped[ProgramDay] = relationship(back_populates="items")
    # every page that shows an item shows its exercise: loaded with it
    exercise: Mapped[Exercise] = relationship(lazy="joined", innerjoin=True)

    @property
    def dose(self) -> str:
        """What the day asks, in the list's words: "3 × 10" (sets and
        reps), "3 × 30 s" (sets and seconds), "10 ponavljanja" (reps alone),
        "30 s" (seconds alone), "3 serije" (sets alone), "" (none)."""
        sets, reps, seconds = self.sets, self.reps, self.seconds
        if sets is not None and reps is not None:
            return f"{sets} × {reps}"
        if sets is not None and seconds is not None:
            return f"{sets} × {seconds} s"
        if reps is not None:
            return f"{reps} {plural(reps, 'ponavljanje', 'ponavljanja', 'ponavljanja')}"
        if seconds is not None:
            return f"{seconds} s"
        if sets is not None:
            return f"{sets} {plural(sets, 'serija', 'serije', 'serija')}"
        return ""

    @property
    def rest_text(self) -> str:
        """The rest between sets, "60 s" (always seconds), "" when not set."""
        return "" if self.rest_seconds is None else f"{self.rest_seconds} s"

    @property
    def rest_after_text(self) -> str:
        """The rest after the exercise, before the next one, "90 s" (always
        seconds), "" when not set."""
        return "" if self.rest_after_seconds is None else f"{self.rest_after_seconds} s"


def kg_text(kg: float | int | None) -> str:
    """A weight as the app prints it, a comma for the half: "20", "2,5";
    "" for none (0: no weight)."""
    return f"{float(kg):g}".replace(".", ",") if kg else ""


def set_text(s: dict) -> str:
    """One logged set as the history prints it: "10 × 20 kg", "10" with no
    weight (its kg 0), "30 s" for a timed exercise's."""
    if "seconds" in s:
        return f"{s.get('seconds') or 0} s"
    reps, kg = s.get("reps") or 0, kg_text(s.get("kg"))
    return f"{reps} × {kg} kg" if kg else f"{reps}"


class WorkoutLog(Base):
    """One pass of a client through a day of an online programme (30.10.2026,
    stage 3 of roadmap/2026-10-29-online-treninzi-spec.md; the owner: the
    tick is stored "so that we have a record of a user's history. He can
    repeat the training if he wants"). "Kreni" on a day opens one
    (db.start_pass), the player walks the day exercise by exercise and each
    "Spremi" writes that exercise's set log into it, and the osvrt at the end
    (the same three fields as after a termin: napor, osjećaj, komentar)
    finishes it (db.finish_pass). A day can be done again and again: every
    pass is a row. At most one pass per client and day is in progress
    (`finished_at` NULL: the partial unique index uq_workout_logs_open); one
    left open is continued ("Nastavi") or dropped ("Odbaci"). Since
    31.10.2026 (the owner: no hanging training) one with no activity for
    PASS_STALE_HOURS (stale: its start or its last save that long ago) can
    no longer be continued, only finished or dropped.

    `program_title` and `day_label` are snapshots taken at the start, as the
    exercises' names in `done` are at each save, so a programme or a day
    renamed or deleted later never garbles the history (the foreign keys are
    SET NULL; the upitnik's rule: a client's record is never pruned).
    `elapsed_seconds` is set at the finish from the server's clock (finished
    − started, whole seconds; a stale pass's last activity − started:
    active_seconds), never from what a page posts.

    `done` is a JSON object, one entry per exercise saved in this pass, keyed
    by the day's item id: {"<item id>": {"exercise_id": 12, "name": "Goblet
    čučanj", "section": "trening", "sets": [{"reps": 10, "kg": 20.0}, …] (a
    timed exercise's [{"seconds": 30}, …]), "at": "<iso>"}}; a re-save
    replaces the entry. The exercise is the one done, the swapped one when
    the client swapped it. `swaps` is a JSON object {"<item id>": <exercise
    id>}, the similar exercise swapped in for this pass (absent: the plan's).
    Both are written by db.py only (json), read through done_items and
    swap_items. `effort` (1–10), `feeling` (a FEELING_LABELS key) and `note`
    are the osvrt."""

    __tablename__ = "workout_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    program_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id", ondelete="SET NULL"), nullable=True)
    day_id: Mapped[int | None] = mapped_column(ForeignKey("program_days.id", ondelete="SET NULL"), nullable=True,
                                               index=True)
    program_title: Mapped[str] = mapped_column(String(160))
    day_label: Mapped[str] = mapped_column(String(200))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    done: Mapped[str] = mapped_column(Text, server_default=text("'{}'"), default="{}")
    swaps: Mapped[str] = mapped_column(Text, server_default=text("'{}'"), default="{}")
    effort: Mapped[int | None] = mapped_column(Integer, nullable=True)       # RPE 1–10
    feeling: Mapped[str | None] = mapped_column(String(10), nullable=True)  # FEELING_LABELS key
    note: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")

    __table_args__ = (
        # one pass in progress per client and day
        Index("uq_workout_logs_open", "user_id", "day_id", unique=True,
              postgresql_where=sql_text("finished_at IS NULL")),
        Index("ix_workout_logs_user_id_started_at", "user_id", "started_at"),
    )

    @staticmethod
    def _object(raw: str | None) -> dict:
        try:
            data = json.loads(raw or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def in_progress(self) -> bool:
        return self.finished_at is None

    @property
    def done_items(self) -> dict[int, dict]:
        """The exercises saved in this pass: item id -> its entry (above);
        an entry that cannot be read is left out."""
        return {int(k): v for k, v in self._object(self.done).items()
                if k.isascii() and k.isdigit() and isinstance(v, dict)}

    @property
    def done_count(self) -> int:
        return len(self.done_items)

    @property
    def swap_items(self) -> dict[int, int]:
        """The swaps of this pass: item id -> the similar exercise's id."""
        return {int(k): v for k, v in self._object(self.swaps).items()
                if k.isascii() and k.isdigit() and isinstance(v, int)}

    @property
    def elapsed_text(self) -> str:
        """How long the pass took, "38 min", "1 h 05 min" (to the nearest
        minute, one at least); "" before it is finished."""
        return duration_text(self.elapsed_seconds)

    @property
    def date(self) -> SADate:
        """The day it was started on, in Zagreb."""
        from .config import TZ
        return self.started_at.astimezone(TZ).date()

    @property
    def last_activity(self) -> datetime:
        """When the pass last moved: its start, or the newest exercise it
        saved when that is later (an entry's "at", read as db.last_sets reads
        it: ISO, a naive one Zagreb's; one that cannot be read is skipped)."""
        from .config import TZ
        last = self.started_at
        for entry in self.done_items.values():
            try:
                at = datetime.fromisoformat(str(entry.get("at")))
            except ValueError:
                continue
            if at.tzinfo is None:
                at = at.replace(tzinfo=TZ)
            if at > last:
                last = at
        return last

    def stale(self, now: datetime | None = None) -> bool:
        """A pass in progress with no activity for PASS_STALE_HOURS (31.10.2026,
        the owner: "It shouldn't be possible to continue the training and have
        a hanging training of 9 hours"): it can no longer be continued, only
        finished with its osvrt or dropped. A finished pass is never stale."""
        from .config import PASS_STALE_HOURS, TZ
        if not self.in_progress:
            return False
        now = now or datetime.now(TZ)
        return now - self.last_activity >= timedelta(hours=PASS_STALE_HOURS)

    def active_seconds(self, now: datetime | None = None) -> int:
        """The pass's length so far, whole seconds, 0 at least: from its start
        to now, or, once stale, to its last activity (a pass left open
        overnight is as long as it was worked, not as long as it hung)."""
        from .config import TZ
        now = now or datetime.now(TZ)
        end = self.last_activity if self.stale(now) else now
        return max(0, int((end - self.started_at).total_seconds()))

    def lines(self, order=()) -> list[tuple[str, list[str]]]:
        """Each exercise saved, (its name, its sets as the history says them:
        ["10 × 20 kg", "10 × 20 kg"]), the history's "Serije": in `order`
        (item ids, the day's display order) first, the rest in the order
        they were saved."""
        rank = {item_id: n for n, item_id in enumerate(order)}
        entries = sorted(self.done_items.items(),
                         key=lambda kv: (rank.get(kv[0], len(rank)), str(kv[1].get("at", ""))))
        return [(str(e.get("name", "")), [set_text(s) for s in e.get("sets", []) if isinstance(s, dict)])
                for _, e in entries]


def duration_text(seconds: int | None) -> str:
    """A duration as the player and the history say it: "38 min", "1 h 05
    min", to the nearest minute and one at least; "" for none."""
    if seconds is None:
        return ""
    minutes = max(1, (int(seconds) + 30) // 60)
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60:02d} min"
