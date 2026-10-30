"""Persistence + booking rules.

The one invariant that must hold under concurrency: a session can never be
overbooked. Two phones tapping the last spot at the same moment both pass a naive
count-then-insert check (the same race macro_tracker's LLM quota had), so
`book()` locks the session row FOR UPDATE and re-counts inside the lock.
"""

from __future__ import annotations

import calendar
import json
import re
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterator

from sqlalchemy import and_, create_engine, delete as sa_delete, func, or_, select, text as sa_text, union
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, joinedload, selectinload, sessionmaker

from . import config, copy, upitnik
from .models import (FEELING_LABELS, ONLINE_TIERS, PLAN_LABELS, SECTIONS, SESSION_KINDS, Announcement, Base, Booking,
                     Exercise, GymCard, Membership, OnboardingResponse, Payment, Program, ProgramDay, ProgramDayItem,
                     ReminderLog, SessionTemplate, SiteCopy, TrainingLog, TrainingSession, UpitnikQuestion, User,
                     WorkoutLog, alpha_key, exercise_alternatives)

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


def mark_email_verified(email: str) -> bool | None:
    """None: no such account. True: NEWLY verified (fire the owner notice).
    False: was already verified (a re-clicked link must not notify again).
    Locked FOR UPDATE so two concurrent clicks can't both read 'newly'."""
    with session_scope() as s:
        u = s.scalar(select(User).where(func.lower(User.email) == email.strip().lower())
                     .with_for_update())
        if u is None:
            return None
        newly = not u.email_verified
        u.email_verified = True
        return newly


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


def update_profile(user_id: int, name: str, last_name: str,
                   birth_date: date | None, phone: str) -> bool:
    with session_scope() as s:
        u = s.get(User, user_id)
        if u is None:
            return False
        u.name = name.strip() or None
        u.last_name = last_name.strip() or None
        u.birth_date = birth_date
        u.phone = phone.strip() or None
        return True


def list_all_users() -> list[User]:
    """Owner roster — every account, newest first."""
    with session_scope() as s:
        return list(s.scalars(select(User).order_by(User.created_at.desc(), User.id.desc())))


# ---------- editable copy (src/qmt/copy.py has the slots and their limits) ----------

def copy_texts() -> dict[str, str]:
    """Every edited text, by slot key. Pages overlay this on the defaults."""
    with session_scope() as s:
        return {row.key: row.text for row in s.scalars(select(SiteCopy))}


def set_copy(key: str, text: str, user_id: int | None) -> None:
    """Store a slot's text as given, "" too: an emptied optional text is a
    row whose text is "" (20.10.2026), which pages print as nothing; only
    reset_copy brings a default back."""
    with session_scope() as s:
        row = s.get(SiteCopy, key)
        if row is None:
            s.add(SiteCopy(key=key, text=text, updated_by=user_id))
        else:
            row.text, row.updated_by = text, user_id


def reset_copy(key: str) -> None:
    """Back to the template's default: the row goes, the default returns."""
    with session_scope() as s:
        s.execute(sa_delete(SiteCopy).where(SiteCopy.key == key))


# ---------- the landing's announcements (#aktualno; models.Announcement) ----------

MAX_ANNOUNCEMENTS = 8          # the owner's number (18.10.2026)


def announcements(all: bool = False) -> list[Announcement]:
    """In position order (the editor's order: a new card last, ↑ / ↓ since
    29.10.2026): the shown ones, or with all=True every one, the hidden too
    (an editor's page)."""
    with session_scope() as s:
        q = select(Announcement).order_by(Announcement.position)
        return list(s.scalars(q if all else q.where(Announcement.shown)))


def announcement(ann_id: int) -> Announcement | None:
    with session_scope() as s:
        return s.get(Announcement, ann_id)


def add_announcement(user_id: int | None) -> Announcement | None:
    """A new card after the last one: the placeholder texts
    (copy.ANNOUNCEMENT_BLANK), shown, no photo. None at the cap
    (MAX_ANNOUNCEMENTS). The count and the next position are read under a
    table lock, so two quick taps (or two editors) never pass the cap
    together nor take one position twice. The lock's mode is self-exclusive
    and lets plain reads through: the landing never waits on it."""
    with session_scope() as s:
        s.execute(sa_text("LOCK TABLE announcements IN SHARE ROW EXCLUSIVE MODE"))
        n, last = s.execute(select(func.count(), func.coalesce(func.max(Announcement.position), 0))
                            .select_from(Announcement)).one()
        if n >= MAX_ANNOUNCEMENTS:
            return None
        a = Announcement(position=last + 1, updated_by=user_id, **copy.ANNOUNCEMENT_BLANK)
        s.add(a)
        s.flush()
        return a


def _announcement_row(s: Session, ann_id: int) -> Announcement:
    """The card, locked for this transaction (a photo replaced while the card
    is deleted must not lose track of a file); LookupError when it is gone."""
    a = s.get(Announcement, ann_id, with_for_update=True)
    if a is None:
        raise LookupError(f"no announcement {ann_id}")
    return a


def delete_announcement(ann_id: int) -> str | None:
    """Delete a card. Returns its photo's file name for the caller to remove
    from storage (the row first, so no page names a file that is gone);
    None when it had none, or was gone already."""
    with session_scope() as s:
        try:
            a = _announcement_row(s, ann_id)
        except LookupError:
            return None
        image = a.image
        s.delete(a)
        return image


def move_announcement(ann_id: int, direction: str, user_id: int | None = None) -> bool:
    """Swap a card with its neighbour in the editor's order, the order the
    landing shows them in (29.10.2026: every card, the hidden too): "gore"
    the one before it, "dolje" the one after. False: no such card, a
    direction that is neither, or none beyond it that way. Under the table
    lock add_announcement takes, so two moves (or a move and an add) never
    read the order half changed. The two positions trade in one flush: the
    unique constraint is deferred to the commit, which sees the swap whole.
    A gap a deleted card left does not matter: the neighbours trade their
    values."""
    if direction not in ("gore", "dolje"):
        return False
    with session_scope() as s:
        s.execute(sa_text("LOCK TABLE announcements IN SHARE ROW EXCLUSIVE MODE"))
        rows = list(s.scalars(select(Announcement).order_by(Announcement.position)))
        i = next((k for k, a in enumerate(rows) if a.id == ann_id), None)
        if i is None:
            return False
        j = i - 1 if direction == "gore" else i + 1
        if not 0 <= j < len(rows):
            return False
        rows[i].position, rows[j].position = rows[j].position, rows[i].position
        rows[i].updated_by = user_id
        return True


def set_announcement_field(ann_id: int, field: str, text: str, user_id: int | None) -> str:
    """Set one text of a card. `field` is its column: tag, title, when_text,
    body or cta. The text is cleaned as copy is (copy.clean) and stored as
    it is, an empty one too (20.10.2026: an emptied text stays empty, as an
    emptied optional slot does; its placeholder, copy.ANNOUNCEMENT_BLANK,
    comes back only when the caller passes it, Zadano). Returns what is
    stored. ValueError: an unknown field, or a text past copy.CAP;
    LookupError: no such card."""
    if field not in copy.ANNOUNCEMENT_BLANK:
        raise ValueError(f"not a text of an announcement: {field!r}")
    cleaned = copy.clean(text)
    if len(cleaned) > copy.CAP:
        raise ValueError(f"{len(cleaned)} characters, at most {copy.CAP}")
    with session_scope() as s:
        a = _announcement_row(s, ann_id)
        setattr(a, field, cleaned)
        a.updated_by = user_id
    return cleaned


def set_announcement_shown(ann_id: int, shown: bool, user_id: int | None = None) -> None:
    """The card's switch: shown to everyone, or on an editor's page only.
    LookupError: no such card."""
    with session_scope() as s:
        a = _announcement_row(s, ann_id)
        a.shown, a.updated_by = shown, user_id


def set_announcement_image(ann_id: int, name: str | None, user_id: int | None = None) -> str | None:
    """Put a stored photo behind a card (its file name), or none. Returns
    the name it held before, for the caller to remove from storage now that
    no row names it. A name that is a path rather than a file is refused
    (ValueError), as copy.image_name refuses one; LookupError: no such card."""
    if name is not None and (not name or len(name) > 128 or "/" in name or "\\" in name or ".." in name):
        raise ValueError(f"not a file name: {name!r}")
    with session_scope() as s:
        a = _announcement_row(s, ann_id)
        old = a.image
        a.image, a.updated_by = name, user_id
        return old


# ---------- the landing's gym cards (#dvorana; models.GymCard) ----------

MAX_GYM_CARDS = 8              # as many as the announcements (20.10.2026)


def gym_cards(all: bool = False) -> list[GymCard]:
    """In position order (creation order): the shown ones, or with all=True
    every one, the hidden too (an editor's page)."""
    with session_scope() as s:
        q = select(GymCard).order_by(GymCard.position)
        return list(s.scalars(q if all else q.where(GymCard.shown)))


def gym_card(card_id: int) -> GymCard | None:
    with session_scope() as s:
        return s.get(GymCard, card_id)


def add_gym_card(user_id: int | None, values: dict | None = None) -> GymCard | None:
    """A new card after the last one: the placeholder texts
    (copy.GYM_CARD_BLANK), shown, standing for no plan. `values` is a
    whole card instead, in the blank's shape plus its plans (one of
    copy.GYM_CARD_EXAMPLES: the demo seed's cards); no route passes it.
    None at the cap (MAX_GYM_CARDS). The count and the next position are
    read under a table lock, as add_announcement reads them: two quick taps
    never pass the cap together nor take one position twice, and the
    landing's plain reads never wait on it."""
    card = dict(copy.GYM_CARD_BLANK if values is None else values)
    for column in ("points", "extra"):                          # a JSON array each, as a list slot's row
        card[column] = copy.dump_items(list(card[column]))
    with session_scope() as s:
        s.execute(sa_text("LOCK TABLE gym_cards IN SHARE ROW EXCLUSIVE MODE"))
        n, last = s.execute(select(func.count(), func.coalesce(func.max(GymCard.position), 0))
                            .select_from(GymCard)).one()
        if n >= MAX_GYM_CARDS:
            return None
        g = GymCard(position=last + 1, updated_by=user_id, **card)
        s.add(g)
        s.flush()
        return g


def _gym_card_row(s: Session, card_id: int) -> GymCard:
    """The card, locked for this transaction; LookupError when it is gone."""
    g = s.get(GymCard, card_id, with_for_update=True)
    if g is None:
        raise LookupError(f"no gym card {card_id}")
    return g


def delete_gym_card(card_id: int) -> bool:
    """Delete a card. False when it was gone already."""
    with session_scope() as s:
        try:
            g = _gym_card_row(s, card_id)
        except LookupError:
            return False
        s.delete(g)
        return True


def set_gym_card_field(card_id: int, column: str, text: str, user_id: int | None) -> str:
    """Set one text of a card. `column` is where the row keeps it
    (copy.GYM_CARD_COLUMNS: title, lead, price, unit, year_price,
    year_unit). The text is cleaned as copy is (copy.clean) and stored as
    it is, an empty one too (20.10.2026, as an announcement's: its
    placeholder, copy.GYM_CARD_BLANK, comes back only when the caller
    passes it, Zadano). Returns what is stored. ValueError: not such a
    column, or a text past copy.CAP; LookupError: no such card."""
    if column not in copy.GYM_CARD_COLUMNS.values():
        raise ValueError(f"not a text of a gym card: {column!r}")
    cleaned = copy.clean(text)
    if len(cleaned) > copy.CAP:
        raise ValueError(f"{len(cleaned)} characters, at most {copy.CAP}")
    with session_scope() as s:
        g = _gym_card_row(s, card_id)
        setattr(g, column, cleaned)
        g.updated_by = user_id
    return cleaned


def set_gym_card_list(card_id: int, column: str, items: list[str], user_id: int | None) -> list[str]:
    """Set one of a card's lists, the whole list: `column` is points (its
    bullets) or extra (its extra lines under them, 20.10.2026), the
    fields copy.GYM_CARD_SLOTS edits as lists. Each item cleaned as copy
    is, the empty ones dropped, stored as a list slot's row is
    (copy.dump_items). An empty list is a card without bullets, or without
    extra lines. Returns what is stored. ValueError: not such a column,
    more than copy.CAP_ITEMS items, or one past copy.CAP; LookupError: no
    such card."""
    if not isinstance(copy.GYM_CARD_SLOTS.get(column), copy.ListSlot):
        raise ValueError(f"not a list of a gym card: {column!r}")
    kept = [t for t in (copy.clean(x) for x in items) if t]
    if len(kept) > copy.CAP_ITEMS or any(len(t) > copy.CAP for t in kept):
        raise ValueError(f"{len(kept)} items, at most {copy.CAP_ITEMS} of {copy.CAP} characters")
    with session_scope() as s:
        g = _gym_card_row(s, card_id)
        setattr(g, column, copy.dump_items(kept))
        g.updated_by = user_id
    return kept


def set_gym_card_shown(card_id: int, shown: bool, user_id: int | None = None) -> None:
    """The card's switch: shown to everyone, or on an editor's page only.
    LookupError: no such card."""
    with session_scope() as s:
        g = _gym_card_row(s, card_id)
        g.shown, g.updated_by = shown, user_id


# ---------- the upitnik's questions (/upitnik; models.UpitnikQuestion) ----------

MAX_UPITNIK_QUESTIONS = 40     # 26.10.2026: room for many more than the fifteen, and a guard against a runaway list

# Every write to the questions' structure (an add, a move, a setting) runs
# under this lock: self-exclusive, so two quick taps or two editors never
# pass the cap together, take one position twice, or hand one role to two
# questions; plain reads (a client's page, the karton) never wait on it.
_QUESTIONS_LOCK = "LOCK TABLE upitnik_questions IN SHARE ROW EXCLUSIVE MODE"


def upitnik_questions(shown: bool = False) -> list[UpitnikQuestion]:
    """In position order: every question (the editor's page, the karton,
    which prints a hidden question's old answers too, and since 27.10.2026
    a client's page as well: upitnik.client_steps, over every row, so a
    hidden question mutes those asked after it), or with shown=True the
    shown rows only."""
    with session_scope() as s:
        q = select(UpitnikQuestion).order_by(UpitnikQuestion.position)
        return list(s.scalars(q.where(UpitnikQuestion.shown) if shown else q))


def upitnik_question(question_id: int) -> UpitnikQuestion | None:
    with session_scope() as s:
        return s.get(UpitnikQuestion, question_id)


def add_upitnik_question(user_id: int | None, values: dict | None = None) -> UpitnikQuestion | None:
    """A new question after the last one: the placeholders
    (copy.UPITNIK_BLANK: a scale in part 2 that scores nothing), shown,
    asked always. `values` is a whole question instead, in the blank's
    shape plus its id, and the question it is asked after with the answer
    that asks it (parent_id, condition: one of
    copy.UPITNIK_DEFAULT_QUESTIONS, the demo seed's, a test's); no
    route passes it. None at the cap (MAX_UPITNIK_QUESTIONS). A question
    that came with its own id moves the id sequence past every id there,
    never back: an id is an answer's key (q<id>), so a new question never
    takes one an old answer may hold."""
    q = dict(copy.UPITNIK_BLANK if values is None else values)
    q["options"] = copy.dump_items(list(q.get("options", ())))
    with session_scope() as s:
        s.execute(sa_text(_QUESTIONS_LOCK))
        n, last = s.execute(select(func.count(), func.coalesce(func.max(UpitnikQuestion.position), 0))
                            .select_from(UpitnikQuestion)).one()
        if n >= MAX_UPITNIK_QUESTIONS:
            return None
        row = UpitnikQuestion(position=last + 1, updated_by=user_id, **q)
        s.add(row)
        s.flush()
        if "id" in q:
            seq = "pg_get_serial_sequence('upitnik_questions', 'id')"
            s.execute(sa_text(f"SELECT setval({seq}, GREATEST((SELECT max(id) FROM upitnik_questions), "
                              f"COALESCE(pg_sequence_last_value({seq}::regclass), 1)))"))
        return row


def _question_row(s: Session, question_id: int) -> UpitnikQuestion:
    """The question, locked for this transaction; LookupError when it is gone."""
    q = s.get(UpitnikQuestion, question_id, with_for_update=True)
    if q is None:
        raise LookupError(f"no upitnik question {question_id}")
    return q


def delete_upitnik_question(question_id: int) -> bool:
    """Delete a question. The answers clients gave it stay as they are
    (the karton prints them under "(pitanje uklonjeno)"), and its id is
    never given again. The questions asked after it are asked always from
    then on (the foreign key nulls their parent_id; their condition stays,
    so the editor's line can say why). False when it was gone already."""
    with session_scope() as s:
        try:
            q = _question_row(s, question_id)
        except LookupError:
            return False
        s.delete(q)
        return True


def move_upitnik_question(question_id: int, direction: str, user_id: int | None = None) -> bool:
    """Swap a question with its neighbour in the editor's order (every
    question, the hidden too): "gore" the one before it, "dolje" the one
    after. False: no such question, a direction that is neither, or none
    beyond it that way. ValueError, with the editor's sentence, when the
    swap would put a question before the one it is asked after (27.10.2026:
    its condition needs that answer first). The two positions trade in one
    flush: the unique constraint is deferred to the commit, which sees the
    swap whole."""
    if direction not in ("gore", "dolje"):
        return False
    with session_scope() as s:
        s.execute(sa_text(_QUESTIONS_LOCK))
        rows = list(s.scalars(select(UpitnikQuestion).order_by(UpitnikQuestion.position)))
        i = next((k for k, r in enumerate(rows) if r.id == question_id), None)
        if i is None:
            return False
        j = i - 1 if direction == "gore" else i + 1
        if not 0 <= j < len(rows):
            return False
        upper, lower = rows[min(i, j)], rows[max(i, j)]
        if lower.parent_id == upper.id:
            raise ValueError("Potpitanje ne može ići ispred svog pitanja.")
        rows[i].position, rows[j].position = rows[j].position, rows[i].position
        rows[i].updated_by = user_id
        return True


def set_upitnik_question(question_id: int, changes: dict[str, str], user_id: int | None) -> UpitnikQuestion:
    """Change a question's settings: part, kind, scoring, role, shown, as
    an editor posts them (texts; qmt.upitnik.settings checks them and
    raises ValueError with the sentence he reads), and since 27.10.2026
    when it is asked: parent_id and condition, posted together, the
    question it is asked after and the answer that asks it, both empty for
    always (qmt.upitnik.condition checks them against every question as
    they stand under the lock). Taking a role another question holds takes
    it from that one (one pain question, one injuries question: the role's
    unique index). Becoming a choice or a multi with fewer than
    upitnik.MIN_OPTIONS options fills them up with the placeholders
    (copy.UPITNIK_BLANK), so a client always has two to choose from; a
    change of kind keeps every text, its options included, and every
    answer, and leaves the questions asked after this one as they are: a
    condition its new kind cannot meet asks them always, and the editor's
    line says so (qmt.upitnik.steps). Returns the row as stored;
    LookupError: no such question."""
    pair = {key: changes[key] for key in ("parent_id", "condition") if key in changes}
    rest = {key: value for key, value in changes.items() if key not in pair}
    with session_scope() as s:
        s.execute(sa_text(_QUESTIONS_LOCK))
        q = _question_row(s, question_id)
        if pair:
            rows = list(s.scalars(select(UpitnikQuestion).order_by(UpitnikQuestion.position)))
            q.parent_id, q.condition = upitnik.condition(question_id, pair.get("parent_id", ""),
                                                         pair.get("condition", ""), rows)
            if not rest:
                q.updated_by = user_id
                return q
        new = upitnik.settings({"part": q.part, "kind": q.kind, "scoring": q.scoring, "role": q.role,
                                "shown": q.shown}, rest)
        if new["role"] and new["role"] != q.role:
            for other in s.scalars(select(UpitnikQuestion).where(UpitnikQuestion.role == new["role"],
                                                                 UpitnikQuestion.id != question_id)):
                other.role, other.updated_by = "", user_id
            s.flush()                               # the role leaves the other row before it lands on this one
        if new["kind"] in upitnik.OPTION_KINDS and len(q.option_items) < upitnik.MIN_OPTIONS:
            items = q.option_items
            for placeholder in copy.UPITNIK_BLANK["options"]:
                if len(items) < upitnik.MIN_OPTIONS and placeholder not in items:
                    items.append(placeholder)
            q.options = copy.dump_items(items)
        q.part, q.kind, q.scoring, q.role, q.shown = (new["part"], new["kind"], new["scoring"], new["role"],
                                                      new["shown"])
        q.updated_by = user_id
        return q


def set_upitnik_question_field(question_id: int, column: str, text: str, user_id: int | None) -> str:
    """Set one text of a question. `column` is where the row keeps it
    (copy.UPITNIK_QUESTION_COLUMNS: text, low, high). The
    text is cleaned as copy is (copy.clean) and stored as it is, an empty
    one too (an emptied text stays empty, as a gym card's: the placeholder,
    copy.UPITNIK_BLANK, comes back only when the caller passes it, Zadano).
    Returns what is stored. ValueError: not such a column, or a text past
    copy.CAP; LookupError: no such question."""
    if column not in copy.UPITNIK_QUESTION_COLUMNS.values():
        raise ValueError(f"not a text of a question: {column!r}")
    cleaned = copy.clean(text)
    if len(cleaned) > copy.CAP:
        raise ValueError(f"{len(cleaned)} characters, at most {copy.CAP}")
    with session_scope() as s:
        q = _question_row(s, question_id)
        setattr(q, column, cleaned)
        q.updated_by = user_id
    return cleaned


def set_upitnik_question_options(question_id: int, items: list[str], user_id: int | None,
                                 renamed: tuple[str, str] | None = None) -> list[str]:
    """Set a question's options, the whole list: each cleaned as copy is,
    the empty ones dropped, stored as a list slot's row is
    (copy.dump_items). Returns what is stored. ValueError: more than
    copy.CAP_ITEMS options, or one past copy.CAP (the route keeps two at
    least: app.py); LookupError: no such question.

    `renamed` (old text, new text) says the editor re-worded one option in
    place (27.10.2026): on a choice or a multi, the questions asked after
    this one at the old text are asked at the new one from then on, in the
    same transaction, under the questions' lock, so a condition never
    names an option that is gone. Not when the old text is still among the
    options (another option said the same), nor when the new one is past
    upitnik.CONDITION_MAX, the column: that condition stays as it was, and
    the editor's line says it no longer holds. An option removed carries
    nothing (its conditions are let go, the same line)."""
    kept = [t for t in (copy.clean(x) for x in items) if t]
    if len(kept) > copy.CAP_ITEMS or any(len(t) > copy.CAP for t in kept):
        raise ValueError(f"{len(kept)} items, at most {copy.CAP_ITEMS} of {copy.CAP} characters")
    with session_scope() as s:
        if renamed is not None:
            s.execute(sa_text(_QUESTIONS_LOCK))
        q = _question_row(s, question_id)
        q.options, q.updated_by = copy.dump_items(kept), user_id
        if renamed is not None and q.kind in upitnik.OPTION_KINDS:
            old, new = renamed
            if old != new and old not in kept and new in kept and len(new) <= upitnik.CONDITION_MAX:
                for child in s.scalars(select(UpitnikQuestion).where(UpitnikQuestion.parent_id == question_id,
                                                                     UpitnikQuestion.condition == old)):
                    child.condition, child.updated_by = new, user_id
    return kept


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


def _materialize(s, t: SessionTemplate, day: date) -> datetime:
    """Template `t`'s session on `day`, inserted unless it already exists;
    returns its starts_at. ON CONFLICT DO NOTHING against
    uq_session_template_start, so concurrent week views (and series) cannot
    double-create. Week views and book_series() share this statement, so a
    series creates exactly the session a week view would."""
    starts = datetime(day.year, day.month, day.day,
                      t.start_min // 60, t.start_min % 60, tzinfo=config.TZ)
    s.execute(
        pg_insert(TrainingSession).values(
            template_id=t.id, title=t.title, kind=t.kind, starts_at=starts,
            duration_min=t.duration_min, capacity=t.capacity,
        ).on_conflict_do_nothing(constraint="uq_session_template_start")
    )
    return starts


def materialize_week(monday) -> None:
    """Ensure every active template has a concrete session in the given week.

    Runs on every week view. Safe under concurrency: the INSERT is
    ON CONFLICT DO NOTHING against uq_session_template_start, so two requests
    materializing the same week cannot double-create. Only the weeks of the
    booking window (booking_window: this week and BOOKING_WEEKS - 1 more): a
    termin further ahead could not be booked yet.
    """
    this_monday, last_day = booking_window(config.today())
    if monday < this_monday or monday > last_day - timedelta(days=6):
        # Past weeks render whatever exists; fabricating "history" or letting a
        # client mint unbounded rows by walking ?week= is not materialization's job.
        return
    with session_scope() as s:
        templates = s.scalars(select(SessionTemplate).where(SessionTemplate.active)
                              .order_by(SessionTemplate.id)).all()  # stable order: no deadlocks
        for t in templates:
            _materialize(s, t, monday + timedelta(days=t.weekday))


def sessions_between(start: datetime, end: datetime, now: datetime | None = None) -> list[dict]:
    """Sessions in [start, end) with booking counts, oldest first. `closed`
    is is_closed() at `now` (the page's own moment, so a row and the page
    around it agree; the current time when none is given)."""
    now = now or datetime.now(config.TZ)
    with session_scope() as s:
        rows = s.execute(
            select(TrainingSession, func.count(Booking.id))
            .join(Booking, Booking.session_id == TrainingSession.id, isouter=True)
            .where(TrainingSession.starts_at >= start, TrainingSession.starts_at < end)
            .group_by(TrainingSession.id)
            .order_by(TrainingSession.starts_at)
        ).all()
        return [{"session": sess, "booked": n, "closed": is_closed(sess, n, now)} for sess, n in rows]


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


class MembershipRequired(BookingError):
    """The one refusal the client can fix themselves — so it carries the plan
    kind, and the UI answers it with a link to that plan's price instead of a
    dead end."""

    def __init__(self, message: str, kind: str):
        super().__init__(message)
        self.kind = kind


def booking_window(today: date) -> tuple[date, date]:
    """The days a termin may be booked on: (this week's Monday, the Sunday
    of the week BOOKING_WEEKS - 1 weeks on). Week-aligned on purpose, the
    owner's "the running week and three more weeks" (29.10.2026): 28 days
    on a Monday, 22 on a Sunday, and each Monday a whole week more."""
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=7 * config.BOOKING_WEEKS - 1)


def is_closed(sess: TrainingSession, booked: int, now: datetime) -> bool:
    """Has this termin closed? An empty termin closes CLOSE_EMPTY_HOURS
    before it starts (the owner, 29.10.2026: nobody booked it by then, so
    nobody comes); one booking keeps it open to anyone until it starts.
    Derived, never stored, so no cron: a termin the trainer canceled stays
    "otkazan" and one that started is "prošao". Every kind alike, a 1:1
    termin too."""
    return (not sess.canceled and now < sess.starts_at
            and sess.starts_at - now <= timedelta(hours=config.CLOSE_EMPTY_HOURS) and booked == 0)


_NUMBER_WORDS = ("nula", "jedan", "dva", "tri", "četiri", "pet", "šest", "sedam", "osam", "devet", "deset")


def weeks_text(n: int, words: bool = False) -> str:
    """n weeks in Croatian, the noun after its count: "4 tjedna" (words:
    "četiri tjedna"); 1 tjedan, 2-4 tjedna, 5 and on tjedana (21 tjedan)."""
    if n % 10 == 1 and n % 100 != 11:
        noun = "tjedan"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        noun = "tjedna"
    else:
        noun = "tjedana"
    count = _NUMBER_WORDS[n] if words and 0 <= n < len(_NUMBER_WORDS) else str(n)
    return f"{count} {noun}"


def book(user_id: int, session_id: int) -> None:
    now = datetime.now(config.TZ)
    with session_scope() as s:
        sess = s.execute(
            select(TrainingSession).where(TrainingSession.id == session_id).with_for_update()
        ).scalar_one_or_none()
        refused = _refusal(s, user_id, sess, now)
        if refused:
            raise refused[1]
        s.add(Booking(user_id=user_id, session_id=session_id))


def _refusal(s, user_id: int, sess: TrainingSession | None,
             now: datetime) -> tuple[str, BookingError] | None:
    """Why `user_id` may not book `sess`: (reason, the error book() raises),
    or None when the booking may go in. The caller holds the session row FOR
    UPDATE, so the counts below are the ones that decide.

    book() and book_series() both ask this, so their rules cannot drift, and
    both are bound by the same two limits: the booking window (this week and
    BOOKING_WEEKS - 1 more) and the plan's paid period with its grace week
    (dospijeće). In order: canceled, started, closed (an empty termin
    CLOSE_EMPTY_HOURS before it starts), past the window, no plan, past
    dospijeće, a spent paket, full, already held."""
    if sess is None or sess.canceled:
        return "otkazan", BookingError("Termin ne postoji ili je otkazan.")
    if sess.starts_at <= now:
        return "prošao", BookingError("Termin je već počeo ili prošao.")
    # counted once, inside the lock: it decides "zatvoren" and "popunjen"
    taken = s.scalar(select(func.count()).select_from(Booking).where(Booking.session_id == sess.id))
    if is_closed(sess, taken, now):
        return "zatvoren", BookingError("Termin je zatvoren.")
    day = sess.starts_at.astimezone(config.TZ).date()
    last = booking_window(config.today())[1]
    if day > last:
        return "prozor", BookingError(
            f"Rezervacije su moguće do {last:%-d.%-m.}, "
            f"{weeks_text(config.BOOKING_WEEKS, words=True)} unaprijed.")
    if sess.kind not in active_plan_kinds(user_id, s):
        return "članarina", _plan_needed(sess.kind)
    m = _membership(s, user_id, sess.kind)
    if day > m.dospijece:
        return "razdoblje", BookingError(
            f"Članarina vrijedi do {m.dospijece:%-d.%-m.} — za kasnije termine treba nova uplata.")
    # tiered plan: this termin's cycle must still have a trening left
    if m.sessions_per_cycle:
        start, end = m.cycle_bounds(day)
        if _cycle_used(s, user_id, sess.kind, start, end) >= m.sessions_per_cycle:
            return "paket", BookingError(
                f"Iskoristio/la si svih {m.sessions_per_cycle} treninga u ciklusu "
                f"{start:%-d.%-m.}–{(end - timedelta(days=1)):%-d.%-m.} — "
                "otkaži neki termin ili pričekaj sljedeći ciklus.")
    if taken >= sess.capacity:
        return "popunjen", BookingError("Termin je popunjen.")
    if _holds(s, user_id, sess.id):
        return "već rezervirano", BookingError("Već si rezervirao/la ovaj termin.")
    return None


def _plan_needed(kind: str) -> MembershipRequired:
    return MembershipRequired(
        f"Za termin \"{PLAN_LABELS.get(kind, kind)}\" treba ti aktivna članarina.", kind)


def _membership(s, user_id: int, plan: str) -> Membership | None:
    return s.scalar(select(Membership).where(Membership.user_id == user_id,
                                             Membership.plan == plan))


def _holds(s, user_id: int, session_id: int) -> bool:
    """Has this user already booked this session?"""
    return bool(s.scalar(select(func.count()).select_from(Booking)
                         .where(Booking.session_id == session_id, Booking.user_id == user_id)))


def _cycle_used(s, user_id: int, kind: str, start: date, end: date) -> int:
    """Live bookings of `kind` whose termin falls inside [start, end) local."""
    lo = datetime.combine(start, datetime.min.time(), tzinfo=config.TZ)
    hi = datetime.combine(end, datetime.min.time(), tzinfo=config.TZ)
    return s.scalar(
        select(func.count()).select_from(Booking)
        .join(TrainingSession, TrainingSession.id == Booking.session_id)
        .where(Booking.user_id == user_id, TrainingSession.kind == kind,
               ~TrainingSession.canceled,
               TrainingSession.starts_at >= lo, TrainingSession.starts_at < hi)) or 0


def cycle_usage(user_id: int, plan: str, on: date | None = None) -> dict | None:
    """{"used", "quota", "start", "end"} for a tiered plan's cycle containing
    `on` (today by default); None when the plan is unlimited or absent."""
    on = on or config.today()
    with session_scope() as s:
        m = s.scalar(select(Membership).where(Membership.user_id == user_id,
                                              Membership.plan == plan))
        if m is None or not m.sessions_per_cycle:
            return None
        start, end = m.cycle_bounds(on)
        return {"used": _cycle_used(s, user_id, plan, start, end),
                "quota": m.sessions_per_cycle, "start": start, "end": end}


def cancel_deadline(sess: TrainingSession) -> datetime:
    """When cancelling `sess` closes for a client (tz-aware, like starts_at):
    CANCEL_CUTOFF_HOURS before it starts. cancel_booking() refuses from that
    moment on and the calendar offers its Otkaži / ✕ only before it, so the
    button and the refusal can never disagree."""
    return sess.starts_at - timedelta(hours=config.CANCEL_CUTOFF_HOURS)


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
        if sess and not sess.canceled and cancel_deadline(sess) <= now:
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


# ---------- weekly series: "isti termin svaki tjedan" ----------

def _weekly_template(s, sess: TrainingSession) -> SessionTemplate:
    """The weekly template `sess` repeats, or the BookingError saying there is
    none. A session left over from before the trainer moved its slot (another
    day, hour or kind) counts as off the timetable: the template's following
    weeks hold a different termin, and repeating the old weekday would create
    sessions no week view ever would."""
    t = s.get(SessionTemplate, sess.template_id) if sess.template_id else None
    if t is None:
        raise BookingError("Ovaj termin nema tjedni raspored.")
    local = sess.starts_at.astimezone(config.TZ)
    if not t.active or (t.weekday, t.start_min, t.kind) != (
            local.weekday(), local.hour * 60 + local.minute, sess.kind):
        raise BookingError("Ovaj termin više nije u tjednom rasporedu.")
    return t


def _series_dates(sess: TrainingSession, m: Membership) -> tuple[list[date], date]:
    """The dates of `sess`'s slot on every later week of the booking window
    that are still ahead, and the series' bound: the earlier of the window's
    last day and the plan's dospijeće (the owner, 29.10.2026: the same
    termin "for all 4 weeks … that is the hard cap", and never past the paid
    period with its grace week, the bound book() keeps too). Past weeks are
    left out, so an offer reopened long after the booking never creates
    sessions in history."""
    day = sess.starts_at.astimezone(config.TZ).date()
    today = config.today()
    until = min(booking_window(today)[1], m.dospijece)
    dates, nxt = [], day + timedelta(days=7)
    while nxt <= until:
        if nxt >= today:
            dates.append(nxt)
        nxt += timedelta(days=7)
    return dates, until


def series_preview(user_id: int, session_id: int) -> dict | None:
    """The offer after booking `session_id`: {"n": weeks left, "last": the
    last of them, "until": the series' bound (_series_dates)}, or None when
    there is nothing to offer (a one-off termin, a slot off the timetable, no
    active plan of its kind, no week left). Read-only: a week nobody has
    opened yet counts as free, and the real run (book_series) skips what is
    full."""
    with session_scope() as s:
        sess = s.get(TrainingSession, session_id)
        if sess is None or sess.kind not in active_plan_kinds(user_id, s):
            return None
        try:
            _weekly_template(s, sess)
        except BookingError:
            return None
        dates, until = _series_dates(sess, _membership(s, user_id, sess.kind))
        return {"n": len(dates), "last": dates[-1], "until": until} if dates else None


def book_series(user_id: int, session_id: int) -> dict:
    """Book `session_id`'s slot on every later week of the booking window,
    up to the plan's dospijeće (_series_dates).

    ONE transaction, dates in order: the session rows are locked in starts_at
    order, so two series (or a series and book()) cannot deadlock. Each date
    is materialized the way a week view does it, locked FOR UPDATE and judged
    by book()'s own rules (_refusal), the window and the period included. A
    canceled, closed, full or already-held date is skipped and reported; a
    spent paket stops the run and the rest stays unbooked. The quota is
    counted inside this transaction, so what the loop books counts as it
    goes.

    Returns {"booked": [dates], "skipped": [(date, reason)], "stopped":
    "paket" | None, "until": the series' bound, "quota": the paket size
    (None = unlimited), which the message names}."""
    now = datetime.now(config.TZ)
    with session_scope() as s:
        sess = s.get(TrainingSession, session_id)
        if sess is None:
            raise BookingError("Termin ne postoji ili je otkazan.")
        t = _weekly_template(s, sess)
        if sess.kind not in active_plan_kinds(user_id, s):
            raise _plan_needed(sess.kind)
        m = _membership(s, user_id, sess.kind)
        dates, until = _series_dates(sess, m)
        booked, skipped, stopped = [], [], None
        for day in dates:
            starts = _materialize(s, t, day)
            occ = s.execute(select(TrainingSession).where(
                TrainingSession.template_id == t.id, TrainingSession.starts_at == starts,
            ).with_for_update()).scalar_one_or_none()
            refused = _refusal(s, user_id, occ, now)
            if refused is None:
                s.add(Booking(user_id=user_id, session_id=occ.id))
                s.flush()                    # counted by the next date's quota check
                booked.append(day)
                continue
            reason, err = refused
            if reason in ("paket", "popunjen") and _holds(s, user_id, occ.id):
                reason = "već rezervirano"   # spent or full with their own booking in it
            if reason == "paket":
                stopped = "paket"
                break
            if reason == "članarina":
                raise err                    # the plan lapsed mid-run: book nothing
            skipped.append((day, reason))
        return {"booked": booked, "skipped": skipped, "stopped": stopped,
                "until": until, "quota": m.sessions_per_cycle}


# ---------- memberships (članarine) ----------

from .models import add_month as _add_month  # noqa: E402  (one definition, shared with models)


def active_plan_kinds(user_id: int, s: Session | None = None) -> set[str]:
    """Plans whose dospijeće (next_payment + grace week) hasn't passed."""
    cutoff = config.today() - timedelta(days=Membership.GRACE_DAYS)
    q = select(Membership.plan).where(Membership.user_id == user_id,
                                      Membership.next_payment >= cutoff)
    if s is not None:
        return set(s.scalars(q))
    with session_scope() as scope:
        return set(scope.scalars(q))


def online_tier(user_id: int) -> str | None:
    """The tier of the client's online plan while it runs (one of
    ONLINE_TIERS: the landing's QMove card that is his), "start" for a row
    that names none; None without an active online plan. Active as
    active_plan_kinds has it: until dospijeće passes."""
    cutoff = config.today() - timedelta(days=Membership.GRACE_DAYS)
    with session_scope() as s:
        row = s.execute(select(Membership.tier).where(
            Membership.user_id == user_id, Membership.plan == "online",
            Membership.next_payment >= cutoff)).first()
    if row is None:
        return None
    return row.tier if row.tier in ONLINE_TIERS else "start"


def memberships_for(user_id: int) -> list[Membership]:
    with session_scope() as s:
        return list(s.scalars(select(Membership).where(Membership.user_id == user_id)
                              .order_by(Membership.plan)))


def covered_days(user_id: int, first: date, last: date) -> set[date]:
    """The days in [first, last] that the client's paid period covers: the
    days /raspored's month view tints ("članarina aktivna").

    Only the plans that book termini count (SESSION_KINDS: grupni,
    individualni, poluindividualni, rehabilitacija); online and prehrana hold
    no termin, so they cover no day. Each such plan covers its paid period:
    from the start of its cycle (Membership.cycle_bounds, anchored on
    next_payment) through its dospijeće, inclusive, because the plan admits
    booking until dospijeće passes (Membership.is_active): the grace week
    counts. The cycle is the one today falls in, cycle_usage's "ovaj ciklus",
    so a client who paid a month ahead is covered from the cycle they are in
    now, not only the month just paid; once next_payment has passed (the
    grace week, a lapsed plan) it is the last paid cycle. Days of the period
    already behind count too: the overview shows the paid period as a whole.
    A lapsed plan keeps its last period and covers nothing after dospijeće."""
    today = config.today()
    days: set[date] = set()
    with session_scope() as s:
        for m in s.scalars(select(Membership).where(Membership.user_id == user_id,
                                                    Membership.plan.in_(SESSION_KINDS))):
            start = m.cycle_bounds(min(today, m.next_payment - timedelta(days=1)))[0]
            day, stop = max(start, first), min(m.dospijece, last)
            while day <= stop:
                days.add(day)
                day += timedelta(days=1)
    return days


def memberships_expiring(within_days: int) -> list[tuple[User, Membership]]:
    """Members whose dospijeće falls inside the next `within_days` days —
    the window in which a reminder is useful. Already-lapsed plans are not
    nagged: past dospijeće the calendar itself says no."""
    today = config.today()
    # dospijeće = next_payment + grace, so shift the window onto next_payment
    lo = today - timedelta(days=Membership.GRACE_DAYS)
    hi = today + timedelta(days=within_days) - timedelta(days=Membership.GRACE_DAYS)
    with session_scope() as s:
        rows = s.execute(
            select(User, Membership).join(Membership, Membership.user_id == User.id)
            .where(Membership.next_payment >= lo, Membership.next_payment <= hi,
                   User.email_verified)
            .order_by(User.id)).all()
        return [(u, m) for u, m in rows]


def bookings_on(day: date) -> list[tuple[User, TrainingSession]]:
    """Everyone booked into a live termin on `day` (local dates) — the
    day-before training reminder reads from this."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=config.TZ)
    end = start + timedelta(days=1)
    with session_scope() as s:
        rows = s.execute(
            select(User, TrainingSession)
            .join(Booking, Booking.user_id == User.id)
            .join(TrainingSession, TrainingSession.id == Booking.session_id)
            .where(TrainingSession.starts_at >= start, TrainingSession.starts_at < end,
                   ~TrainingSession.canceled, User.email_verified)
            .order_by(User.id, TrainingSession.starts_at)).all()
        return [(u, sess) for u, sess in rows]


def claim_reminder(user_id: int, kind: str, ref: str) -> bool:
    """True exactly once per (user, kind, ref) — the send happens only on a
    successful claim, so concurrent runs and restarts cannot double-mail."""
    with session_scope() as s:
        # RETURNING, not rowcount: psycopg3 reports rowcount -1 ("unknown") for
        # this construct, which reads as truthy and let every duplicate through
        row = s.execute(pg_insert(ReminderLog).values(
            user_id=user_id, kind=kind, ref=ref)
            .on_conflict_do_nothing(constraint="uq_reminder_once")
            .returning(ReminderLog.id)).first()
        return row is not None


def release_reminder(user_id: int, kind: str, ref: str) -> None:
    """A claim whose email failed to send is handed back for the next run."""
    with session_scope() as s:
        s.execute(sa_delete(ReminderLog).where(
            ReminderLog.user_id == user_id, ReminderLog.kind == kind,
            ReminderLog.ref == ref))


def next_cycle(m: Membership | None, today: date) -> tuple[date, date]:
    """What an uplata recorded on `today` buys: the plan's new (next_payment,
    dospijeće). One rule, which record_payment() follows and /clanarine
    states before the uplata is recorded.

    The membership month is fixed (the owner, 29.10.2026): due 1.5., paying
    on 28.4., 1.5., 7.5. (the grace week, trained on trust) or 12.5. (locked
    out since 8.5.) all buy 1.5.-1.6., the month that began at the due date
    and has not ended. Only once that whole month has passed unpaid (a real
    gap) does a payment start a fresh month from that day: 2.6. buys
    2.6.-2.7. A plan never held starts from today."""
    base = m.next_payment if m is not None and today < _add_month(m.next_payment) else today
    nxt = _add_month(base)
    return nxt, nxt + timedelta(days=Membership.GRACE_DAYS)


def trust_bookings(user_id: int, plan: str) -> int:
    """The client's live termini of `plan` in its grace week, next_payment
    through dospijeće: booked and trained on trust. While the plan is lapsed
    they are unpaid (/clanarine's amber note); any uplata moves next_payment
    on, and they stop counting, whichever month it buys."""
    with session_scope() as s:
        m = _membership(s, user_id, plan)
        if m is None:
            return 0
        return _cycle_used(s, user_id, plan, m.next_payment, m.dospijece + timedelta(days=1))


def record_payment(user_id: int, plan: str, method: str = "gotovina",
                   amount_eur=None, stripe_invoice_id: str | None = None,
                   stripe_subscription_id: str | None = None,
                   sessions_per_cycle: int | None = None,
                   tier: str | None = None) -> Membership:
    """An uplata — cash/card at the gym, or a paid Stripe invoice: start the
    plan or extend it by a month.

    Each uplata restates the plan's tier: grupni's treninga a month
    (`sessions_per_cycle`), and the online plan's QMove tier (`tier`, one of
    ONLINE_TIERS; none named, or one that is no tier: the tier the row has,
    "start", the base tier, for a new one — so a Stripe renewal, which names
    none, never demotes a member). No other plan has a tier: theirs is NULL
    whatever is passed.

    The membership month is fixed (next_cycle): it runs from due date to due
    date and never moves while the client keeps paying. Paying early, in the
    grace week, or after dospijeće while the month that began at the due date
    is still running all buy that same month; only a payment after a whole
    month passed unpaid starts afresh from today (nobody owes "back months"
    for time the gym wasn't used). Until 29.10.2026 a lapsed plan restarted
    from today, which let a client pay on the last grace day every month and
    get five weeks for four.

    Every call also appends to the immutable `payments` ledger — memberships
    hold only the current cycle, the ledger holds the owner's history. A Stripe
    invoice id already in the ledger means a redelivered webhook: the current
    membership is returned untouched, no second month is granted.
    """
    today = config.today()
    with session_scope() as s:
        m = s.scalar(select(Membership).where(Membership.user_id == user_id,
                                              Membership.plan == plan).with_for_update())
        if stripe_invoice_id and s.scalar(select(Payment.id).where(
                Payment.stripe_invoice_id == stripe_invoice_id)):
            return m
        next_payment = next_cycle(m, today)[0]
        if m is None:
            m = Membership(user_id=user_id, plan=plan, paid_on=today, next_payment=next_payment)
            s.add(m)
        else:
            m.paid_on, m.next_payment = today, next_payment
        if stripe_subscription_id:
            # a paid invoice is proof the subscription is live again
            m.stripe_subscription_id = stripe_subscription_id
            m.cancel_at_period_end = False
        m.sessions_per_cycle = sessions_per_cycle        # each uplata (re)states the tier
        # the online tier: the one named; none named (the Stripe webhook, which
        # knows no tiers yet), the row's own, "start" for a new row
        if plan == "online":
            m.tier = tier if tier in ONLINE_TIERS else (m.tier if m.tier in ONLINE_TIERS else "start")
        else:
            m.tier = None
        s.add(Payment(user_id=user_id, plan=plan, method=method, paid_on=today,
                      amount_eur=amount_eur, stripe_invoice_id=stripe_invoice_id))
        s.flush()
        return m


def set_stripe_customer(user_id: int, customer_id: str) -> None:
    with session_scope() as s:
        u = s.get(User, user_id)
        if u is not None and not u.stripe_customer_id:
            u.stripe_customer_id = customer_id


def subscription_membership(subscription_id: str) -> Membership | None:
    with session_scope() as s:
        return s.scalar(select(Membership).where(
            Membership.stripe_subscription_id == subscription_id))


def set_subscription_cancelling(subscription_id: str, cancel_at_period_end: bool) -> bool:
    """Stripe says the client cancelled (or un-cancelled) in the portal — the
    plan keeps its dates and simply will (not) be extended again."""
    with session_scope() as s:
        m = s.scalar(select(Membership).where(
            Membership.stripe_subscription_id == subscription_id))
        if m is None:
            return False
        m.cancel_at_period_end = cancel_at_period_end
        return True


def set_subscription_tier(subscription_id: str, sessions: int | None) -> bool:
    """The subscription's price changed (our button or Stripe's portal) — the
    quota follows it immediately; the dates are untouched."""
    with session_scope() as s:
        m = s.scalar(select(Membership).where(
            Membership.stripe_subscription_id == subscription_id))
        if m is None:
            return False
        m.sessions_per_cycle = sessions
        return True


def clear_subscription(subscription_id: str) -> bool:
    """The subscription is gone at Stripe. Access is NOT revoked here: the
    dates already paid for stay valid, and the plan lapses on dospijeće."""
    with session_scope() as s:
        m = s.scalar(select(Membership).where(
            Membership.stripe_subscription_id == subscription_id))
        if m is None:
            return False
        m.stripe_subscription_id = None
        m.cancel_at_period_end = False
        return True


def payments_for(user_id: int, limit: int = 50) -> list[Payment]:
    """One client's uplate, newest first — their billing history."""
    with session_scope() as s:
        return list(s.scalars(
            select(Payment).where(Payment.user_id == user_id)
            .order_by(Payment.paid_on.desc(), Payment.id.desc()).limit(limit)))


def payment_stats(months: int = 12) -> dict:
    """Ledger rollup for the owner: per-month × per-plan counts + method split."""
    today = config.today()
    y, mo = today.year, today.month
    keys = []                                    # newest month first
    for _ in range(months):
        keys.append(f"{y:04d}-{mo:02d}")
        y, mo = (y - 1, 12) if mo == 1 else (y, mo - 1)
    start = date(int(keys[-1][:4]), int(keys[-1][5:]), 1)
    with session_scope() as s:
        rows = s.execute(select(Payment.paid_on, Payment.plan, Payment.method)
                         .where(Payment.paid_on >= start)).all()
    per_month: dict[str, dict[str, int]] = {k: {} for k in keys}
    plan_totals: dict[str, int] = {}
    method_totals: dict[str, int] = {}
    for paid_on, plan, method in rows:
        k = f"{paid_on.year:04d}-{paid_on.month:02d}"
        if k in per_month:
            per_month[k][plan] = per_month[k].get(plan, 0) + 1
        plan_totals[plan] = plan_totals.get(plan, 0) + 1
        method_totals[method] = method_totals.get(method, 0) + 1
    return {
        "months": [{"key": k, "label": f"{int(k[5:])}/{k[:4]}",
                    "per_plan": per_month[k], "total": sum(per_month[k].values())}
                   for k in keys],
        "plan_totals": plan_totals,
        "method_totals": method_totals,
    }


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

def save_onboarding(user_id: int, answers_json: str, score: float, level: str, goal: str, *,
                    version: int = 2, pain_level: int | None, pain_high: bool, needs_review: bool,
                    consented_at: datetime | None) -> None:
    """Upsert — refilling the upitnik replaces the previous routing: every
    field is the new response's, an old version-1 row's included."""
    fields = {"answers": answers_json, "score": score, "level": level, "goal": goal, "version": version,
              "pain_level": pain_level, "pain_high": pain_high, "needs_review": needs_review,
              "consented_at": consented_at}
    with session_scope() as s:
        r = s.scalar(select(OnboardingResponse)
                     .where(OnboardingResponse.user_id == user_id).with_for_update())
        if r is None:
            s.add(OnboardingResponse(user_id=user_id, **fields))
        else:
            for name, value in fields.items():
                setattr(r, name, value)


def get_onboarding(user_id: int) -> OnboardingResponse | None:
    with session_scope() as s:
        return s.scalar(select(OnboardingResponse)
                        .where(OnboardingResponse.user_id == user_id))


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


def _log_target(s, user_id: int, session_id: int) -> TrainingSession:
    """The one termin a diary row may be written against: booked by this client,
    finished, not called off, and not already written up."""
    now = datetime.now(config.TZ)
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
        raise BookingError("Zapis za ovaj termin već postoji.")
    return sess


def add_session_feedback(user_id: int, session_id: int, effort: int,
                         feeling: str | None, note: str) -> None:
    """Feedback is tied to an ATTENDED, FINISHED termin — never free-floating."""
    with session_scope() as s:
        sess = _log_target(s, user_id, session_id)
        s.add(TrainingLog(user_id=user_id, session_id=session_id,
                          date=sess.starts_at.astimezone(config.TZ).date(),
                          effort=effort, feeling=feeling, note=note))


def mark_session_absent(user_id: int, session_id: int, note: str = "") -> None:
    """"Nisam bio/la" — the client's own no-show. It closes the termin off the
    same way an osvrt does (one row per user+session, so the karton stops
    asking), but records absence instead of effort. The TrainingSession is left
    alone: it is shared with everyone else who booked it."""
    with session_scope() as s:
        sess = _log_target(s, user_id, session_id)
        s.add(TrainingLog(user_id=user_id, session_id=session_id,
                          date=sess.starts_at.astimezone(config.TZ).date(),
                          effort=None, feeling=None, note=note, absent=True))


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


def update_training_log(log_id: int, user_id: int, effort: int | None,
                        feeling: str | None, note: str) -> bool:
    """Edit an osvrt in place. Only what the client wrote is editable — the
    termin it hangs off, and its date, are facts and stay put."""
    with session_scope() as s:
        entry = s.scalar(select(TrainingLog).where(TrainingLog.id == log_id,
                                                   TrainingLog.user_id == user_id))
        if entry is None or entry.absent:
            # an absence has nothing to edit — delete it and write the osvrt
            return False
        entry.effort = effort
        entry.feeling = feeling
        entry.note = note
        return True


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

def programs_for_combo(level: str, goal: str) -> list[Program]:
    """The client's automatic programme(s): whatever is tagged with their
    upitnik combo. No hand-outs — matching IS the access. Each with its days
    and their items loaded (the list says how many days)."""
    with session_scope() as s:
        return list(s.scalars(
            select(Program).where(Program.level == level, Program.goal == goal)
            .options(selectinload(Program.days).selectinload(ProgramDay.items))
            .order_by(Program.title)))


def client_can_view(program: Program, user_id: int) -> bool:
    """A client sees a programme iff its (razina, cilj) matches their upitnik."""
    onb = get_onboarding(user_id)
    return (onb is not None and program.level is not None
            and program.level == onb.level and program.goal == onb.goal)


# ---------- the library of exercises (/treninzi/vjezbe, 30.10.2026) ----------

EXERCISE_NAME_MAX = 160          # the column's length
EXERCISE_DUPLICATE = "Vježba s tim imenom već postoji."
# Every write that may set a name (a new exercise, a save) takes the table in
# this mode first: it conflicts with itself, so two saves cannot both find a
# name free and both write it (tested: without it the C locale's index lets
# "Čučanj" and "ČUČANJ" both in).
_EXERCISES_LOCK = "LOCK TABLE exercises IN SHARE ROW EXCLUSIVE MODE"


def clean_name(text: str) -> str:
    """An exercise's name as stored: one line, trimmed, its spaces single."""
    return " ".join((text or "").split())


def clean_tags(text: str) -> str:
    """Tags as stored: each between two commas trimmed, its spaces single,
    the empty ones gone, joined by ", " ("  noge ,bučice,, kod   kuće " ->
    "noge, bučice, kod kuće")."""
    return ", ".join(t for t in (" ".join(x.split()) for x in (text or "").split(",")) if t)


def _checked_name(name: str) -> str:
    name = clean_name(name)
    if not name:
        raise ValueError("Naziv je obavezan.")
    if len(name) > EXERCISE_NAME_MAX:
        raise ValueError(f"Naziv može imati najviše {EXERCISE_NAME_MAX} znakova.")
    return name


def _named(s: Session, name: str, but: int | None = None) -> int | None:
    """The id of the exercise with this name, whatever its case (other than
    `but`), or None. Asked under _EXERCISES_LOCK. Casefolded here, not with
    the database's lower(): under the C locale (the dev and test databases)
    that folds ASCII only, so "Čučanj" and "čučanj" would pass as two."""
    want = name.casefold()
    return next((i for i, n in s.execute(select(Exercise.id, Exercise.name))
                 if i != but and n.casefold() == want), None)


def _duplicate(err: IntegrityError) -> bool:
    """Was it uq_exercises_name (a name the database folds to one it has)?"""
    return getattr(getattr(err.orig, "diag", None), "constraint_name", None) == "uq_exercises_name"


def _set_alternatives(s: Session, exercise_id: int, wanted) -> None:
    """Make an exercise's similar exercises exactly `wanted` (ids): a pair
    ticked and not held is stored from this side, one held and not ticked
    goes whichever side stored it. Ids that are no exercise, and its own, are
    ignored."""
    t = exercise_alternatives
    wanted = {int(x) for x in wanted} - {exercise_id}
    if wanted:
        wanted &= set(s.scalars(select(Exercise.id).where(Exercise.id.in_(wanted))))
    held = (set(s.scalars(select(t.c.alternative_id).where(t.c.exercise_id == exercise_id)))
            | set(s.scalars(select(t.c.exercise_id).where(t.c.alternative_id == exercise_id))))
    for other in sorted(wanted - held):
        s.execute(pg_insert(t).values(exercise_id=exercise_id, alternative_id=other).on_conflict_do_nothing())
    gone = held - wanted
    if gone:
        s.execute(sa_delete(t).where(or_((t.c.exercise_id == exercise_id) & t.c.alternative_id.in_(gone),
                                         (t.c.alternative_id == exercise_id) & t.c.exercise_id.in_(gone))))


def create_exercise(name: str, instructions: str = "", rep_note: str = "", tags: str = "",
                    alternatives=(), user_id: int | None = None) -> int:
    """A new library row with its similar exercises; its id. ValueError with
    the sentence to show when the name is empty, too long or taken, whatever
    its case ("Vježba s tim imenom već postoji."). The texts are cleaned as
    copy is (copy.clean), the tags by clean_tags."""
    name = _checked_name(name)
    try:
        with session_scope() as s:
            s.execute(sa_text(_EXERCISES_LOCK))
            if _named(s, name) is not None:
                raise ValueError(EXERCISE_DUPLICATE)
            e = Exercise(name=name, instructions=copy.clean(instructions or ""),
                         rep_note=copy.clean(rep_note or ""), tags=clean_tags(tags), updated_by=user_id)
            s.add(e)
            s.flush()
            _set_alternatives(s, e.id, alternatives)
            return e.id
    except IntegrityError as err:
        if _duplicate(err):
            raise ValueError(EXERCISE_DUPLICATE) from None
        raise


def update_exercise(exercise_id: int, name: str, instructions: str, rep_note: str, tags: str,
                    alternatives=(), user_id: int | None = None) -> bool:
    """Save an exercise's texts and its similar exercises in one go (the
    form's one POST); False for an exercise that is gone. ValueError as
    create_exercise's."""
    name = _checked_name(name)
    try:
        with session_scope() as s:
            s.execute(sa_text(_EXERCISES_LOCK))
            e = s.get(Exercise, exercise_id)
            if e is None:
                return False
            if _named(s, name, but=exercise_id) is not None:
                raise ValueError(EXERCISE_DUPLICATE)
            e.name, e.tags = name, clean_tags(tags)
            e.instructions, e.rep_note = copy.clean(instructions or ""), copy.clean(rep_note or "")
            e.updated_by = user_id
            _set_alternatives(s, exercise_id, alternatives)
            return True
    except IntegrityError as err:
        if _duplicate(err):
            raise ValueError(EXERCISE_DUPLICATE) from None
        raise


def exercise(exercise_id: int) -> Exercise | None:
    """One library row, its similar exercises loaded (both directions)."""
    with session_scope() as s:
        return s.scalar(select(Exercise).where(Exercise.id == exercise_id)
                        .options(selectinload(Exercise.alternatives_to), selectinload(Exercise.alternatives_from)))


def _holding(exercise_ids):
    """The ids of the programmes whose days hold any of these exercises (a
    select of exercise ids, or a list): a subquery."""
    return (select(ProgramDay.program_id).join(ProgramDayItem, ProgramDayItem.day_id == ProgramDay.id)
            .where(ProgramDayItem.exercise_id.in_(exercise_ids)))


def exercises(q: str = "") -> list[tuple[Exercise, int]]:
    """The library in the alphabet's order (alpha_key), each exercise with the
    number of programmes that hold it (in any of their days). With q, only
    those whose name or tags hold it, whatever its case (the list's search);
    every one without."""
    with session_scope() as s:
        used = dict(s.execute(select(ProgramDayItem.exercise_id, func.count(func.distinct(ProgramDay.program_id)))
                              .join(ProgramDay, ProgramDay.id == ProgramDayItem.day_id)
                              .group_by(ProgramDayItem.exercise_id)).all())
        rows = list(s.scalars(select(Exercise)))
    needle = " ".join((q or "").split()).casefold()
    if needle:
        rows = [e for e in rows if needle in e.name.casefold() or needle in e.tags.casefold()]
    return [(e, used.get(e.id, 0)) for e in sorted(rows, key=lambda e: alpha_key(e.name))]


def program_name(p: Program) -> str:
    """A programme as the library's pages name it: its title, and its
    razina's label after it when it has one, "Booty build (napredna
    razina)" (30.10.2026, the owner: three live programmes share the title
    "Booty build", one per razina, and the title alone sent him to the wrong
    one). The label is upitnik.LEVELS', lower-cased mid-sentence."""
    label = upitnik.LEVELS.get(p.level or "")
    return f"{p.title} ({label.lower()})" if label else p.title


def exercise_programs(exercise_id: int) -> list[Program]:
    """The programmes that hold an exercise in any of their days, in the
    alphabet's order of their names (program_name)."""
    with session_scope() as s:
        rows = list(s.scalars(select(Program).where(Program.id.in_(_holding([exercise_id])))))
    return sorted(rows, key=lambda p: alpha_key(program_name(p)))


def in_programs(titles: list[str]) -> str:
    """Why an exercise cannot be deleted: "Vježba je u 3 programa (Booty
    build (napredna razina), Core control, Donji dio tijela — srednja) —
    prvo je makni iz njih.", the programmes' names (program_name) up to
    three, then "…"."""
    n = len(titles)
    named = ", ".join(titles[:3]) + (" …" if n > 3 else "")
    noun = "programu" if n % 10 == 1 and n % 100 != 11 else "programa"
    return f"Vježba je u {n} {noun} ({named}) — prvo je makni iz {'njega' if n == 1 else 'njih'}."


def delete_exercise(exercise_id: int) -> str | None:
    """Delete a library row nothing holds (its pairs of similar exercises go
    with it); returns its clip's file name for the caller to delete from
    storage, None without one or for a row already gone. One a programme
    holds is refused: ValueError with in_programs' sentence."""
    with session_scope() as s:
        e = s.get(Exercise, exercise_id, with_for_update=True)
        if e is None:
            return None
        titles = sorted((program_name(p) for p in s.scalars(select(Program)
                                                              .where(Program.id.in_(_holding([exercise_id]))))),
                        key=alpha_key)
        if titles:
            raise ValueError(in_programs(titles))
        video = e.video
        s.delete(e)
        return video


def set_exercise_video(exercise_id: int, name: str | None, user_id: int | None = None) -> str | None:
    """Give an exercise a stored clip (None: no clip) and return the one it
    had, which the caller deletes from storage once no row names it (the
    announcements' photos' order). LookupError for an exercise that is gone:
    the caller deletes the clip it stored for it."""
    with session_scope() as s:
        e = s.get(Exercise, exercise_id, with_for_update=True)
        if e is None:
            raise LookupError(exercise_id)
        old = e.video
        e.video, e.updated_by = name, user_id
        return old


def video_programs(name: str) -> list[Program] | None:
    """Who may watch a stored clip (/media): None when neither an exercise
    nor a day holds it (an exercise's clip, a day's intro video), else the
    programmes that hold its exercise in a day, or an exercise it is similar
    to (since 30.10.2026 the player shows a similar exercise swapped in, its
    clip too), or whose day it introduces (a client watches it through one
    of his matched programmes; staff watch any)."""
    with session_scope() as s:
        ids = select(Exercise.id).where(Exercise.video == name)
        intro = select(ProgramDay.program_id).where(ProgramDay.intro_video == name)
        if not (s.scalar(select(func.count()).select_from(ids.subquery()))
                or s.scalar(select(func.count()).select_from(intro.subquery()))):
            return None
        t = exercise_alternatives
        similar = union(select(t.c.alternative_id).where(t.c.exercise_id.in_(ids)),
                        select(t.c.exercise_id).where(t.c.alternative_id.in_(ids)))
        return list(s.scalars(select(Program).where(or_(Program.id.in_(_holding(ids)),
                                                        Program.id.in_(_holding(select(similar.subquery()))),
                                                        Program.id.in_(intro)))))


def all_programs() -> list[tuple[Program, int, int]]:
    """Trainer library: every programme with its number of days and of
    exercises across them, combos first."""
    with session_scope() as s:
        days = (select(ProgramDay.program_id, func.count().label("n"))
                .group_by(ProgramDay.program_id).subquery())
        items = (select(ProgramDay.program_id, func.count(ProgramDayItem.id).label("n"))
                 .join(ProgramDayItem, ProgramDayItem.day_id == ProgramDay.id)
                 .group_by(ProgramDay.program_id).subquery())
        rows = s.execute(
            select(Program, func.coalesce(days.c.n, 0), func.coalesce(items.c.n, 0))
            .join(days, days.c.program_id == Program.id, isouter=True)
            .join(items, items.c.program_id == Program.id, isouter=True)
            .order_by(Program.level.desc(), Program.goal, Program.title)
        ).all()
        return [(p, nd, ni) for p, nd, ni in rows]


def create_program(title: str, intro: str | None,
                   level: str | None = None, goal: str | None = None) -> int:
    with session_scope() as s:
        p = Program(title=title, intro=intro, level=level, goal=goal)
        s.add(p)
        s.flush()
        return p.id


def get_program(program_id: int) -> Program | None:
    """A programme with its days and their items, each item with its
    exercise (ProgramDayItem's joined load)."""
    with session_scope() as s:
        return s.scalar(select(Program).where(Program.id == program_id)
                        .options(selectinload(Program.days).selectinload(ProgramDay.items)))


def update_program(program_id: int, title: str, intro: str | None,
                   level: str | None = None, goal: str | None = None) -> None:
    with session_scope() as s:
        p = s.get(Program, program_id)
        if p is not None:
            p.title, p.intro, p.level, p.goal = title, intro, level, goal


def delete_program(program_id: int) -> list[str] | None:
    """Delete a programme, its days and their items. The exercises they
    pointed at, and their clips, stay in the library; the days' intro videos
    go with the days: their file names are returned for the caller to delete
    from storage (the rows first, so no page names a file that is gone).
    None for a programme already gone."""
    with session_scope() as s:
        p = s.get(Program, program_id, with_for_update=True)
        if p is None:
            return None
        videos = list(s.scalars(select(ProgramDay.intro_video)
                                .where(ProgramDay.program_id == program_id, ProgramDay.intro_video.is_not(None))))
        s.delete(p)
        return videos


# ---------- a programme's days and their exercises (30.10.2026, stage 2) ----------
# Every write to a programme's days or their items takes the programme's row
# first, then the day's (_day_locked): one lock, one order, so two editors at
# once never read the order half changed nor take one position twice (the
# positions are unique, deferred to the commit for ↑ / ↓).

DAY_TITLE_MAX = 160              # the column's length
ITEM_NOTE_MAX = 500
# what an item's numbers may be, (least, most); else BAD_NUMBER
ITEM_LIMITS = {"sets": (1, 99), "reps": (1, 999), "seconds": (1, 3600), "rest_seconds": (0, 3600),
               "rest_after_seconds": (0, 3600)}
BAD_NUMBER = "Neispravan broj."
REPS_OR_SECONDS = "Upiši ponavljanja ili sekunde, ne oboje."


def _day_locked(s: Session, day_id: int) -> tuple[Program, ProgramDay] | None:
    """(programme, day), the programme's row locked, then the day's; None
    when the day is gone (or went while the lock was awaited)."""
    pid = s.scalar(select(ProgramDay.program_id).where(ProgramDay.id == day_id))
    if pid is None:
        return None
    p = s.get(Program, pid, with_for_update=True)
    day = s.get(ProgramDay, day_id, with_for_update=True, populate_existing=True) if p is not None else None
    if day is None or day.program_id != pid:
        return None
    return p, day


def _item_locked(s: Session, item_id: int) -> tuple[Program, ProgramDay, ProgramDayItem] | None:
    """(programme, day, item) under _day_locked's locks; None when the item
    is gone."""
    day_id = s.scalar(select(ProgramDayItem.day_id).where(ProgramDayItem.id == item_id))
    found = _day_locked(s, day_id) if day_id is not None else None
    it = s.get(ProgramDayItem, item_id, populate_existing=True) if found else None
    if it is None or it.day_id != day_id:
        return None
    return (*found, it)


def add_day(program_id: int) -> int | None:
    """A new day after the last ("Dan N+1": no title, no weekday, no intro);
    its id. None when the programme is gone."""
    with session_scope() as s:
        p = s.get(Program, program_id, with_for_update=True)
        if p is None:
            return None
        last = s.scalar(select(func.coalesce(func.max(ProgramDay.position), 0))
                        .where(ProgramDay.program_id == program_id))
        day = ProgramDay(program_id=program_id, position=last + 1, title="", weekday=None, intro="")
        s.add(day)
        p.updated_at = func.now()
        s.flush()
        return day.id


def get_day(day_id: int) -> ProgramDay | None:
    """A day with its programme and its items, each with its exercise,
    loaded (usable once the session is closed)."""
    with session_scope() as s:
        return s.scalar(select(ProgramDay).where(ProgramDay.id == day_id)
                        .options(selectinload(ProgramDay.items), joinedload(ProgramDay.program)))


def update_day(day_id: int, title: str, weekday: int | None, intro: str) -> bool:
    """Save a day's title (one line, its spaces single), suggested weekday
    (0–6, None for none) and intro (cleaned as copy is: its line breaks
    kept); False for a day that is gone. ValueError with the sentence to show
    for a title past DAY_TITLE_MAX or a weekday that is none."""
    title = clean_name(title)
    if len(title) > DAY_TITLE_MAX:
        raise ValueError(f"Naslov može imati najviše {DAY_TITLE_MAX} znakova.")
    if weekday is not None and not 0 <= weekday <= 6:
        raise ValueError("Odaberi dan u tjednu.")
    with session_scope() as s:
        found = _day_locked(s, day_id)
        if found is None:
            return False
        p, day = found
        day.title, day.weekday, day.intro = title, weekday, copy.clean(intro or "")
        p.updated_at = func.now()
        return True


def delete_day(day_id: int) -> str | None:
    """Delete a day and its items (their exercises stay in the library); the
    later days move up, so the days stay Dan 1 … Dan N. Returns its intro
    video's file name for the caller to delete from storage, None without
    one or for a day already gone."""
    with session_scope() as s:
        found = _day_locked(s, day_id)
        if found is None:
            return None
        p, day = found
        video = day.intro_video
        s.delete(day)
        s.flush()
        for n, d in enumerate(s.scalars(select(ProgramDay).where(ProgramDay.program_id == p.id)
                                        .order_by(ProgramDay.position)), start=1):
            d.position = n
        p.updated_at = func.now()
        return video


def move_day(day_id: int, direction: str) -> bool:
    """Swap a day with its neighbour: "gore" the one before it, "dolje" the
    one after (their numbers trade: Dan 2 becomes Dan 1). False: no such
    day, a direction that is neither, or none beyond it that way. The two
    positions trade in one flush; the unique constraint is deferred to the
    commit, which sees the swap whole."""
    if direction not in ("gore", "dolje"):
        return False
    with session_scope() as s:
        found = _day_locked(s, day_id)
        if found is None:
            return False
        p, day = found
        rows = list(s.scalars(select(ProgramDay).where(ProgramDay.program_id == p.id)
                              .order_by(ProgramDay.position)))
        i = next(k for k, d in enumerate(rows) if d.id == day_id)
        j = i - 1 if direction == "gore" else i + 1
        if not 0 <= j < len(rows):
            return False
        rows[i].position, rows[j].position = rows[j].position, rows[i].position
        p.updated_at = func.now()
        return True


def set_day_video(day_id: int, name: str | None) -> str | None:
    """Give a day a stored intro video (None: no video) and return the one
    it had, which the caller deletes from storage once no row names it (an
    exercise's clip's order). LookupError for a day that is gone: the caller
    deletes the file it stored for it."""
    with session_scope() as s:
        found = _day_locked(s, day_id)
        if found is None:
            raise LookupError(day_id)
        p, day = found
        old = day.intro_video
        day.intro_video = name
        p.updated_at = func.now()
        return old


def add_day_item(day_id: int, exercise_id: int, section: str) -> int | None:
    """Put a library exercise last in a day, in a section (SECTIONS), nothing
    asked of it yet; the new item's id. None when the section is not one,
    or the day or the exercise is gone (deleted while it was added too: the
    foreign key)."""
    if section not in SECTIONS:
        return None
    try:
        with session_scope() as s:
            found = _day_locked(s, day_id)
            if found is None or s.get(Exercise, exercise_id) is None:
                return None
            p, day = found
            last = s.scalar(select(func.coalesce(func.max(ProgramDayItem.position), 0))
                            .where(ProgramDayItem.day_id == day_id))
            it = ProgramDayItem(day_id=day_id, position=last + 1, section=section, exercise_id=exercise_id, note="")
            s.add(it)
            p.updated_at = func.now()
            s.flush()
            return it.id
    except IntegrityError:
        return None


def get_day_item(item_id: int) -> ProgramDayItem | None:
    """An item with its exercise and its day loaded."""
    with session_scope() as s:
        return s.scalar(select(ProgramDayItem).where(ProgramDayItem.id == item_id)
                        .options(joinedload(ProgramDayItem.day)))


def update_day_item(item_id: int, section: str, sets: int | None, reps: int | None, seconds: int | None,
                    rest_seconds: int | None, rest_after_seconds: int | None, note: str) -> bool:
    """Save what a day asks of an exercise: its section, sets, reps or
    seconds (one of the two), the rest between sets, the rest after it
    (before the next exercise) and a note (stripped); None for a number not
    set. An item moved to another section goes last in it. False for an
    item that is gone. ValueError with the sentence to show: a number out
    of ITEM_LIMITS ("Neispravan broj."), reps and seconds both ("Upiši
    ponavljanja ili sekunde, ne oboje."), a note past ITEM_NOTE_MAX, a
    section that is none."""
    if section not in SECTIONS:
        raise ValueError("Odaberi dio dana.")
    for field, value in (("sets", sets), ("reps", reps), ("seconds", seconds), ("rest_seconds", rest_seconds),
                         ("rest_after_seconds", rest_after_seconds)):
        least, most = ITEM_LIMITS[field]
        if value is not None and not least <= value <= most:
            raise ValueError(BAD_NUMBER)
    if reps is not None and seconds is not None:
        raise ValueError(REPS_OR_SECONDS)
    note = (note or "").strip()
    if len(note) > ITEM_NOTE_MAX:
        raise ValueError(f"Napomena može imati najviše {ITEM_NOTE_MAX} znakova.")
    with session_scope() as s:
        found = _item_locked(s, item_id)
        if found is None:
            return False
        p, day, it = found
        if section != it.section:
            it.section = section
            it.position = s.scalar(select(func.max(ProgramDayItem.position))
                                   .where(ProgramDayItem.day_id == day.id)) + 1
        it.sets, it.reps, it.seconds, it.rest_seconds, it.note = sets, reps, seconds, rest_seconds, note
        it.rest_after_seconds = rest_after_seconds
        p.updated_at = func.now()
        return True


def delete_day_item(item_id: int) -> bool:
    """Take an exercise out of its day (it stays in the library). False for
    an item already gone."""
    with session_scope() as s:
        found = _item_locked(s, item_id)
        if found is None:
            return False
        p, _, it = found
        s.delete(it)
        p.updated_at = func.now()
        return True


def move_day_item(item_id: int, direction: str) -> bool:
    """Swap an item with its neighbour in the SAME section, by the day's
    display order: "gore" the one before it, "dolje" the one after. False:
    no such item, a direction that is neither, or none beyond it that way
    in its section (an item changes section through its form, not here)."""
    if direction not in ("gore", "dolje"):
        return False
    with session_scope() as s:
        found = _item_locked(s, item_id)
        if found is None:
            return False
        p, day, it = found
        rows = list(s.scalars(select(ProgramDayItem)
                              .where(ProgramDayItem.day_id == day.id, ProgramDayItem.section == it.section)
                              .order_by(ProgramDayItem.position)))
        i = next(k for k, r in enumerate(rows) if r.id == item_id)
        j = i - 1 if direction == "gore" else i + 1
        if not 0 <= j < len(rows):
            return False
        rows[i].position, rows[j].position = rows[j].position, rows[i].position
        p.updated_at = func.now()
        return True


# ---------- a client's passes through a day (30.10.2026, stage 3: the player) ----------
# A pass (models.WorkoutLog) is opened by "Kreni" on a day, filled exercise by
# exercise by the player's "Spremi" (that exercise's set log), and finished by
# the osvrt at the end. Every write takes the pass's row first (FOR UPDATE):
# `done` and `swaps` are read, changed and written whole, so two saves at once
# (two tabs) never lose one another's entry. A pass is the client's own: every
# function here matches it by its id AND its client.

# what a logged set's numbers may be, (least, most); else BAD_NUMBER. A weight
# goes in steps of half a kilo.
SET_LIMITS = {"reps": (0, 999), "kg": (0, 500), "seconds": (0, 3600)}
MAX_SETS = 12
NO_SET = "Upiši bar jednu seriju."
TOO_MANY_SETS = f"Najviše {MAX_SETS} serija."
NOT_SIMILAR = "Ta vježba nije među sličnima."
BAD_OSVRT = "Neispravan osvrt."                  # the karton's sentence for the same three fields
PASS_FINISHED = "Trening je već završen."


def _set_number(raw: str | None, field: str) -> int | float | None:
    """One number of the set log as posted: "" (or spaces) is none; else
    ASCII digits (a weight "2,5" or "2.5", in steps of 0.5) within
    SET_LIMITS, or ValueError BAD_NUMBER."""
    value = (raw or "").strip()
    if not value:
        return None
    least, most = SET_LIMITS[field]
    if field == "kg":
        if not re.fullmatch(r"[0-9]{1,3}(?:[.,][0-9]{1,2})?", value):
            raise ValueError(BAD_NUMBER)
        kg = Decimal(value.replace(",", "."))
        if (kg * 2) % 1 or not least <= kg <= most:
            raise ValueError(BAD_NUMBER)
        return float(kg)
    if not re.fullmatch(r"[0-9]{1,4}", value):
        raise ValueError(BAD_NUMBER)
    number = int(value)
    if not least <= number <= most:
        raise ValueError(BAD_NUMBER)
    return number


def read_sets(rows: list[dict[str, str]], timed: bool) -> list[dict]:
    """A set log as the player posts it, row by row ({"reps": "10", "kg":
    "2,5"}, a timed exercise's {"seconds": "30"}), as it is stored: [{"reps":
    10, "kg": 2.5}, …] or [{"seconds": 30}, …]. A row with every field empty
    is dropped; in a row that has a number, an empty field is 0 (a weight of
    0 is none). ValueError with the sentence to show: a number that is none
    or out of its range ("Neispravan broj."), no set left ("Upiši bar jednu
    seriju."), more than MAX_SETS ("Najviše 12 serija.")."""
    fields = ("seconds",) if timed else ("reps", "kg")
    sets = []
    for row in rows:
        values = {f: _set_number(row.get(f), f) for f in fields}
        if all(v is None for v in values.values()):
            continue
        sets.append({"seconds": values["seconds"] or 0} if timed
                    else {"reps": values["reps"] or 0, "kg": float(values["kg"] or 0)})
    return _checked_sets(sets)


def _checked_sets(sets: list[dict]) -> list[dict]:
    """Sets as stored (read_sets'), checked again where they are written."""
    if not sets:
        raise ValueError(NO_SET)
    if len(sets) > MAX_SETS:
        raise ValueError(TOO_MANY_SETS)
    clean = []
    for st in sets:
        if set(st) == {"seconds"}:
            fields = ("seconds",)
        elif set(st) == {"reps", "kg"}:
            fields = ("reps", "kg")
        else:
            raise ValueError(BAD_NUMBER)
        for f in fields:
            least, most = SET_LIMITS[f]
            v = st[f]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not least <= v <= most:
                raise ValueError(BAD_NUMBER)
            if f != "kg" and v != int(v) or f == "kg" and (v * 2) % 1:
                raise ValueError(BAD_NUMBER)
        clean.append({"seconds": int(st["seconds"])} if fields == ("seconds",)
                     else {"reps": int(st["reps"]), "kg": float(st["kg"])})
    return clean


def _pass_row(s: Session, log_id: int, user_id: int) -> WorkoutLog | None:
    """A client's pass, its row locked."""
    return s.scalar(select(WorkoutLog).where(WorkoutLog.id == log_id, WorkoutLog.user_id == user_id)
                    .with_for_update())


def _json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def start_pass(user_id: int, program: Program, day: ProgramDay) -> WorkoutLog:
    """The client's pass in progress through a day: the open one if there is
    one, else a new one, its snapshots taken now (the programme's title, the
    day's label). Two "Kreni" at once open one pass: the second insert meets
    the partial unique index (uq_workout_logs_open) and does nothing, and
    both read the one row."""
    with session_scope() as s:
        s.execute(pg_insert(WorkoutLog).values(
            user_id=user_id, program_id=program.id, day_id=day.id, program_title=program.title[:160],
            day_label=day.label[:200], done="{}", swaps="{}", note="",
        ).on_conflict_do_nothing(index_elements=["user_id", "day_id"], index_where=WorkoutLog.finished_at.is_(None)))
        return s.scalar(select(WorkoutLog).where(WorkoutLog.user_id == user_id, WorkoutLog.day_id == day.id,
                                                 WorkoutLog.finished_at.is_(None)))


def open_pass(user_id: int, day_id: int) -> WorkoutLog | None:
    """The client's pass in progress through a day, or None."""
    with session_scope() as s:
        return s.scalar(select(WorkoutLog).where(WorkoutLog.user_id == user_id, WorkoutLog.day_id == day_id,
                                                 WorkoutLog.finished_at.is_(None)))


def get_pass(log_id: int, user_id: int) -> WorkoutLog | None:
    """A pass of this client's, in progress or finished; None for another's."""
    with session_scope() as s:
        return s.scalar(select(WorkoutLog).where(WorkoutLog.id == log_id, WorkoutLog.user_id == user_id))


def save_sets(log_id: int, user_id: int, item: ProgramDayItem, sets: list[dict], exercise: Exercise) -> bool:
    """Write an exercise's set log into a pass in progress: `item`'s entry
    (the exercise done, its name as it is now, the item's section, `sets`,
    stamped now), replacing the one it had. `exercise` is the item's, or the
    similar one swapped in for this pass. False for no such pass of this
    client, or an item of another day. ValueError: the sets' sentences
    (read_sets), PASS_FINISHED for a pass already finished, NOT_SIMILAR for
    an exercise that is neither the item's nor its swap."""
    sets = _checked_sets(sets)
    with session_scope() as s:
        log = _pass_row(s, log_id, user_id)
        if log is None or log.day_id != item.day_id:
            return False
        if log.finished_at is not None:
            raise ValueError(PASS_FINISHED)
        if exercise.id != item.exercise_id and log.swap_items.get(item.id) != exercise.id:
            raise ValueError(NOT_SIMILAR)
        done = WorkoutLog._object(log.done)
        done[str(item.id)] = {"exercise_id": exercise.id, "name": exercise.name, "section": item.section,
                              "sets": sets, "at": datetime.now(config.TZ).isoformat()}
        log.done = _json(done)
        return True


def swap_exercise(log_id: int, user_id: int, item: ProgramDayItem, exercise_id: int | None) -> bool:
    """Swap the similar exercise `exercise_id` in for `item` in this pass
    (None: the plan's back). Only one of the item's exercise's similar
    exercises (Exercise.alternatives), else ValueError NOT_SIMILAR
    ("Ta vježba nije među sličnima."); PASS_FINISHED for a pass finished.
    What the pass saved of the item stays as it was saved. False for no
    such pass of this client, or an item of another day."""
    with session_scope() as s:
        if exercise_id is not None:
            planned = s.scalar(select(Exercise).where(Exercise.id == item.exercise_id)
                               .options(selectinload(Exercise.alternatives_to),
                                        selectinload(Exercise.alternatives_from)))
            if planned is None or exercise_id not in {a.id for a in planned.alternatives}:
                raise ValueError(NOT_SIMILAR)
        log = _pass_row(s, log_id, user_id)
        if log is None or log.day_id != item.day_id:
            return False
        if log.finished_at is not None:
            raise ValueError(PASS_FINISHED)
        swaps = WorkoutLog._object(log.swaps)
        if exercise_id is None:
            swaps.pop(str(item.id), None)
        else:
            swaps[str(item.id)] = exercise_id
        log.swaps = _json(swaps)
        return True


def finish_pass(log_id: int, user_id: int, effort: int | None, feeling: str | None, note: str) -> bool:
    """Finish a pass with its osvrt: napor 1–10, osjećaj (a FEELING_LABELS
    key, or none), a comment (stripped). The finish is the server's clock,
    and so is the pass's length (finished − started, whole seconds). False
    for no such pass of this client. ValueError: BAD_OSVRT ("Neispravan
    osvrt.", the karton's) for an effort outside 1–10 or a feeling that is
    none of the labels, PASS_FINISHED for a pass finished already."""
    if effort is None or not 1 <= effort <= 10 or (feeling and feeling not in FEELING_LABELS):
        raise ValueError(BAD_OSVRT)
    with session_scope() as s:
        log = _pass_row(s, log_id, user_id)
        if log is None:
            return False
        if log.finished_at is not None:
            raise ValueError(PASS_FINISHED)
        now = datetime.now(config.TZ)
        log.finished_at = now
        log.elapsed_seconds = max(0, int((now - log.started_at).total_seconds()))
        log.effort, log.feeling, log.note = effort, feeling or None, (note or "").strip()
        return True


def drop_pass(log_id: int, user_id: int) -> bool:
    """Delete a pass in progress ("Odbaci"), what it saved with it. A
    finished pass is never deleted here: False, as for none."""
    with session_scope() as s:
        log = _pass_row(s, log_id, user_id)
        if log is None or log.finished_at is not None:
            return False
        s.delete(log)
        return True


def passes(user_id: int, day_id: int | None = None, limit: int | None = None) -> list[WorkoutLog]:
    """A client's finished passes, newest first: a day's, or every day's
    when none is named; at most `limit`."""
    q = select(WorkoutLog).where(WorkoutLog.user_id == user_id, WorkoutLog.finished_at.is_not(None))
    if day_id is not None:
        q = q.where(WorkoutLog.day_id == day_id)
    q = q.order_by(WorkoutLog.started_at.desc(), WorkoutLog.id.desc())
    if limit is not None:
        q = q.limit(limit)
    with session_scope() as s:
        return list(s.scalars(q))


def last_sets(user_id: int, exercise_id: int) -> list[dict] | None:
    """The sets the client last saved for an exercise, in any pass of his,
    finished or in progress, any day of any programme (the newest entry for
    it by when it was saved): what the player prefills the weights from.
    None when he never logged it."""
    with session_scope() as s:
        rows = list(s.scalars(select(WorkoutLog.done).where(WorkoutLog.user_id == user_id)
                              .order_by(WorkoutLog.started_at, WorkoutLog.id)))
    newest, sets = None, None
    for raw in rows:                     # oldest pass first: on a tie the later pass's entry wins
        for entry in WorkoutLog._object(raw).values():
            if not isinstance(entry, dict) or entry.get("exercise_id") != exercise_id:
                continue
            try:
                at = datetime.fromisoformat(str(entry.get("at")))
            except ValueError:
                continue
            if at.tzinfo is None:
                at = at.replace(tzinfo=config.TZ)
            if newest is None or at >= newest:
                newest, sets = at, [x for x in entry.get("sets", []) if isinstance(x, dict)]
    return sets


def day_states(user_id: int, day_ids) -> dict[int, dict]:
    """A client's state on each of these days, in one query: day id ->
    {"open": his pass in progress or None, "count": his finished passes,
    "last": the newest one's day (Zagreb) or None}. A day he never started
    is not in it."""
    day_ids = list(day_ids)
    if not day_ids:
        return {}
    finished = WorkoutLog.finished_at.is_not(None)
    agg = (select(WorkoutLog.day_id.label("day_id"),
                  func.count().filter(finished).label("n"),
                  func.max(WorkoutLog.started_at).filter(finished).label("last"))
           .where(WorkoutLog.user_id == user_id, WorkoutLog.day_id.in_(day_ids))
           .group_by(WorkoutLog.day_id).subquery())
    opened = aliased(WorkoutLog)
    with session_scope() as s:
        rows = s.execute(select(agg.c.day_id, agg.c.n, agg.c.last, opened)
                         .outerjoin(opened, and_(opened.user_id == user_id, opened.day_id == agg.c.day_id,
                                                 opened.finished_at.is_(None)))).all()
    return {day_id: {"open": log, "count": n, "last": last.astimezone(config.TZ).date() if last else None}
            for day_id, n, last, log in rows}


def day_state(user_id: int, day_id: int) -> dict:
    """A client's state on a day (day_states' dict): {"open": None, "count":
    0, "last": None} for a day he never started."""
    return day_states(user_id, [day_id]).get(day_id, {"open": None, "count": 0, "last": None})


def day_sizes(day_ids) -> dict[int, int]:
    """How many exercises each of these days holds now (a day that is gone,
    or holds none, is not in it)."""
    day_ids = list(day_ids)
    if not day_ids:
        return {}
    with session_scope() as s:
        return dict(s.execute(select(ProgramDayItem.day_id, func.count()).where(ProgramDayItem.day_id.in_(day_ids))
                              .group_by(ProgramDayItem.day_id)).all())


def exercises_by_id(ids) -> dict[int, Exercise]:
    """These exercises of the library, each with its similar exercises loaded."""
    ids = list(ids)
    if not ids:
        return {}
    with session_scope() as s:
        return {e.id: e for e in s.scalars(select(Exercise).where(Exercise.id.in_(ids))
                                           .options(selectinload(Exercise.alternatives_to),
                                                    selectinload(Exercise.alternatives_from)))}
