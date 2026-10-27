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

from sqlalchemy import create_engine, delete as sa_delete, func, select, text as sa_text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from . import config, copy, upitnik
from .models import (ONLINE_TIERS, PLAN_LABELS, SESSION_KINDS, Announcement, Base, Booking, GymCard,
                     Membership, OnboardingResponse, Payment, Program, ProgramItem, ReminderLog,
                     SessionTemplate, SiteCopy, TrainingLog, TrainingSession, UpitnikQuestion, User)

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
    """In position order (creation order): the shown ones, or with all=True
    every one, the hidden too (an editor's page)."""
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
            _materialize(s, t, monday + timedelta(days=t.weekday))


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


class MembershipRequired(BookingError):
    """The one refusal the client can fix themselves — so it carries the plan
    kind, and the UI answers it with a link to that plan's price instead of a
    dead end."""

    def __init__(self, message: str, kind: str):
        super().__init__(message)
        self.kind = kind


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


def _refusal(s, user_id: int, sess: TrainingSession | None, now: datetime,
             horizon: bool = True) -> tuple[str, BookingError] | None:
    """Why `user_id` may not book `sess`: (reason, the error book() raises),
    or None when the booking may go in. The caller holds the session row FOR
    UPDATE, so the counts below are the ones that decide.

    book() and book_series() both ask this, so their rules cannot drift. The
    checks run in book()'s order, so a single booking gets exactly the message
    it always got. The series passes horizon=False: it books the paid period
    ahead and is bounded by that period's end instead."""
    if sess is None or sess.canceled:
        return "otkazan", BookingError("Termin ne postoji ili je otkazan.")
    if sess.starts_at <= now:
        return "prošao", BookingError("Termin je već počeo ili prošao.")
    if horizon and sess.starts_at > now + timedelta(days=config.BOOKING_HORIZON_DAYS):
        return "horizont", BookingError(
            f"Rezervacije se otvaraju {config.BOOKING_HORIZON_DAYS} dana unaprijed.")
    if sess.kind not in active_plan_kinds(user_id, s):
        return "članarina", _plan_needed(sess.kind)
    # tiered plan: this termin's cycle must still have a trening left
    m = _membership(s, user_id, sess.kind)
    if m is not None and m.sessions_per_cycle:
        day = sess.starts_at.astimezone(config.TZ).date()
        start, end = m.cycle_bounds(day)
        if _cycle_used(s, user_id, sess.kind, start, end) >= m.sessions_per_cycle:
            return "paket", BookingError(
                f"Iskoristio/la si svih {m.sessions_per_cycle} treninga u ciklusu "
                f"{start:%-d.%-m.}–{(end - timedelta(days=1)):%-d.%-m.} — "
                "otkaži neki termin ili pričekaj sljedeći ciklus.")
    taken = s.scalar(select(func.count()).select_from(Booking).where(Booking.session_id == sess.id))
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
    """The dates of `sess`'s slot on the following weeks of its paid period
    that are still ahead, and that period's last day. The period is the cycle
    containing `sess` (Membership.cycle_bounds), cut at dospijeće: a termin in
    the grace week repeats up to dospijeće, never into a month nobody has paid
    for. Past weeks are left out, so an offer reopened long after the booking
    never creates sessions in history."""
    day = sess.starts_at.astimezone(config.TZ).date()
    end = min(m.cycle_bounds(day)[1], m.dospijece + timedelta(days=1))
    today = config.today()
    dates, nxt = [], day + timedelta(days=7)
    while nxt < end:
        if nxt >= today:
            dates.append(nxt)
        nxt += timedelta(days=7)
    return dates, end - timedelta(days=1)


def series_preview(user_id: int, session_id: int) -> dict | None:
    """The offer after booking `session_id`: {"n": weeks left, "last": the
    last of them, "until": the paid period's last day}, or None when there is
    nothing to offer (a one-off termin, a slot off the timetable, no active
    plan of its kind, no week left). Read-only: a week nobody has opened yet
    counts as free, and the real run (book_series) skips what is full."""
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
    """Book `session_id`'s slot on every following week of its paid period.

    ONE transaction, dates in order: the session rows are locked in starts_at
    order, so two series (or a series and book()) cannot deadlock. Each date
    is materialized the way a week view does it, locked FOR UPDATE and judged
    by book()'s own rules (_refusal) except the horizon: the paid period is
    the bound here. A canceled, full or already-held date is skipped and
    reported; a spent paket stops the run and the rest stays unbooked. The
    quota is counted inside this transaction, so what the loop books counts
    as it goes.

    Returns {"booked": [dates], "skipped": [(date, reason)], "stopped":
    "paket" | None, "until": the period's last day, "quota": the paket size
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
            refused = _refusal(s, user_id, occ, now, horizon=False)
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

    Paying early extends from the CURRENT due date, not from today — a payment
    a week ahead must never shorten the cycle. A lapsed plan restarts from
    today (nobody owes "back months" for time the gym wasn't used).

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
        base = m.next_payment if m is not None and m.next_payment > today else today
        if m is None:
            m = Membership(user_id=user_id, plan=plan, paid_on=today,
                           next_payment=_add_month(base))
            s.add(m)
        else:
            m.paid_on, m.next_payment = today, _add_month(base)
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
    upitnik combo. No hand-outs — matching IS the access."""
    from sqlalchemy.orm import selectinload

    with session_scope() as s:
        return list(s.scalars(
            select(Program).where(Program.level == level, Program.goal == goal)
            .options(selectinload(Program.items))
            .order_by(Program.title)))


def client_can_view(program: Program, user_id: int) -> bool:
    """A client sees a programme iff its (razina, cilj) matches their upitnik."""
    onb = get_onboarding(user_id)
    return (onb is not None and program.level is not None
            and program.level == onb.level and program.goal == onb.goal)


# Default content for the combo slots: the SAME structure per cilj, only the
# prescription (serije × ponavljanja · kg) scales with the razina. Nothing
# fancy — placeholders the trainer edits, so no slot ever renders empty.
# (exercise, technique cue, {razina: prescription})
_DEFAULT_ITEMS = {
    "cijelo": [
        ("Goblet čučanj", "Pete cijelo vrijeme na podu, trup uspravan.",
         {"pocetna": "3 × 8 · 8 kg", "srednja": "4 × 10 · 16 kg", "napredna": "4 × 12 · 24 kg"}),
        ("Sklekovi", "Tijelo u ravnoj liniji, bez propadanja kuka.",
         {"pocetna": "3 × 5 (s koljena)", "srednja": "3 × 10", "napredna": "4 × 15"}),
        ("Veslanje u pretklonu", "Povuci prema pojasu, leđa ravna.",
         {"pocetna": "3 × 10 · 2 × 6 kg", "srednja": "3 × 12 · 2 × 10 kg", "napredna": "4 × 12 · 2 × 14 kg"}),
        ("Plank", "Lopatice aktivne, gluteusi stisnuti.",
         {"pocetna": "3 × 20 s", "srednja": "3 × 40 s", "napredna": "3 × 60 s"}),
    ],
    "gornji": [
        ("Potisak s bučicama na klupi", "Lopatice skupljene, spusti kontrolirano.",
         {"pocetna": "3 × 8 · 2 × 6 kg", "srednja": "4 × 10 · 2 × 12 kg", "napredna": "4 × 12 · 2 × 18 kg"}),
        ("Veslanje u pretklonu", "Povuci prema pojasu, leđa ravna.",
         {"pocetna": "3 × 10 · 2 × 6 kg", "srednja": "4 × 10 · 2 × 12 kg", "napredna": "4 × 12 · 2 × 16 kg"}),
        ("Potisak iznad glave", "Trup čvrst, bez zaklona u leđima.",
         {"pocetna": "3 × 8 · 2 × 4 kg", "srednja": "3 × 10 · 2 × 8 kg", "napredna": "4 × 10 · 2 × 12 kg"}),
        ("Biceps pregib", "Laktovi mirni uz tijelo, puni opseg pokreta.",
         {"pocetna": "2 × 10 · 2 × 4 kg", "srednja": "3 × 12 · 2 × 8 kg", "napredna": "3 × 15 · 2 × 10 kg"}),
    ],
    "donji": [
        ("Goblet čučanj", "Koljena prate smjer stopala.",
         {"pocetna": "3 × 8 · 8 kg", "srednja": "4 × 10 · 20 kg", "napredna": "4 × 12 · 28 kg"}),
        ("Iskorak unatrag", "Koljeno prati smjer stopala, trup uspravan.",
         {"pocetna": "3 × 6 po nozi", "srednja": "3 × 10 po nozi · 2 × 8 kg", "napredna": "4 × 10 po nozi · 2 × 12 kg"}),
        ("Rumunjsko mrtvo dizanje", "Neutralna kralježnica, kukovi idu unatrag.",
         {"pocetna": "3 × 8 · 12 kg", "srednja": "4 × 10 · 24 kg", "napredna": "4 × 10 · 32 kg"}),
        ("Glute most", "Stisni gluteuse gore i zadrži sekundu.",
         {"pocetna": "3 × 12", "srednja": "3 × 15 · 10 kg", "napredna": "4 × 15 · 20 kg"}),
    ],
}


def ensure_online_skeletons() -> int:
    """Create any missing (razina × cilj) slot and fill EMPTY ones with the
    default exercises.

    Runs when the trainer opens Online treninzi — a fresh deploy heals itself,
    no seed run needed. A slot the trainer already put ANY item into is never
    touched. Returns how many programmes were created.
    """
    from .upitnik import GOALS, LEVELS

    made = 0
    with session_scope() as s:
        have = {(p.level, p.goal) for p in s.scalars(
            select(Program).where(Program.level.is_not(None)))}
        for level, level_label in LEVELS.items():
            for goal, goal_label in GOALS.items():
                if (level, goal) in have:
                    continue
                s.add(Program(title=f"{goal_label} — {level_label.lower()}",
                              level=level, goal=goal,
                              intro="Odmor 60–90 s između serija. Tempo kontroliran."))
                made += 1
    with session_scope() as s:
        empty = s.execute(
            select(Program.id, Program.level, Program.goal)
            .outerjoin(ProgramItem, ProgramItem.program_id == Program.id)
            .where(Program.level.is_not(None))
            .group_by(Program.id).having(func.count(ProgramItem.id) == 0)).all()
    for pid, level, goal in empty:
        for title, cue, by_level in _DEFAULT_ITEMS.get(goal, []):
            if level in by_level:
                add_item(pid, title, f"{by_level[level]}\n{cue}", None, None)
    return made


def all_programs() -> list[tuple[Program, int]]:
    """Trainer library: every programme + item count, combos first."""
    with session_scope() as s:
        items = (select(ProgramItem.program_id, func.count().label("n"))
                 .group_by(ProgramItem.program_id).subquery())
        rows = s.execute(
            select(Program, func.coalesce(items.c.n, 0))
            .join(items, items.c.program_id == Program.id, isouter=True)
            .order_by(Program.level.desc(), Program.goal, Program.title)
        ).all()
        return [(p, ni) for p, ni in rows]


def create_program(title: str, intro: str | None,
                   level: str | None = None, goal: str | None = None) -> int:
    with session_scope() as s:
        p = Program(title=title, intro=intro, level=level, goal=goal)
        s.add(p)
        s.flush()
        return p.id


def get_program(program_id: int) -> Program | None:
    from sqlalchemy.orm import selectinload

    with session_scope() as s:
        return s.scalar(select(Program).where(Program.id == program_id)
                        .options(selectinload(Program.items)))


def update_program(program_id: int, title: str, intro: str | None,
                   level: str | None = None, goal: str | None = None) -> None:
    with session_scope() as s:
        p = s.get(Program, program_id)
        if p is not None:
            p.title, p.intro, p.level, p.goal = title, intro, level, goal


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
