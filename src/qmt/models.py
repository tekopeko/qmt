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
    Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
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
