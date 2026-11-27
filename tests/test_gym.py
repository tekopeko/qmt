"""The gym training (26.11.2026, build 3 of roadmap/2026-11-26-gym-training-plan.md,
parts A and B).

The owner: "I would remove the 'dodaj trening' and automatically add the
training with its title already after a user booked it and he can already
edit it 4 hours before the training up until the next day. Amir can also edit
it later." … "The training should have a date and time written on it so that
there is no confusion which training they edit."; his note to Amir: "Kolko je
zadano a kolko je napravio i onda kvačica."; and, of the online player's walk:
"Maybe a whole 'Kreni' kind of dynamic does not apply to gym trainings the
best way" (ONE page that grows as it goes; online stays as it is).

A member's training (models.GymTraining, GymTrainingItem; migration
c4e1b7f9a2d6, run for real on qmt_test there and back) is his alone. A
termin's is open to him from GYM_OPENS_HOURS before the termin until the end
of the day after it, a training outside a termin always, staff acting as him
at any time (rule 1, db.gym_can_write); it is made the first time it is
opened (rule 2, db.gym_training_for, two opens at once one row); a cancelled
booking takes it along, or lets it go of its termin when it holds a record
(rule 3); a tick saves the exercise's ticked rows whole (rule 4,
db.save_gym_done, under the training's row lock); its first values are the
zadano, nothing else (rule 5: next_load is online's); its saved sets count
for the history and the maxes at once (rule 6); /media shows its exercises'
clips to its member (rule 7); and the login's prompt owes a termin only while
its training's window is open (rule 8). The page (karton_trening.html), its
osvrt (karton_trening_osvrt.html), the karton's diary and termini, the
raspored's card, a roster's "Kao član →", the seed; the browser half walks
the owner's own flow on a phone. Part B (migration 36d6e2c97de7): a part's
own name and its circuit ("Uredi dio", db.set_gym_part), a circuit's rounds
saved a round at a time (db.save_gym_round, under the training's row lock),
a dvoranski programme's training copied in as a template
(db.gym_from_template), a slot's card filled from the library
(db.fill_gym_slot); its browser half a template chosen, its slots filled, a
circuit of two rounds ticked on a phone."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from html import unescape
from urllib.parse import unquote

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect, text as sa_text

from qmt import auth, config, copy, db
from qmt.models import WEEKDAYS, Base, Booking, GymTraining, GymTrainingItem, TrainingLog, User
from qmt.web.app import app

PORT = 8118    # test_copy's 8111, test_raspored_ui's / test_upitnik_ui's 8112, test_nav's 8113, test_programs' 8114,
               # test_player's 8115, test_karton's 8116, test_kao's 8117

TEMPLATES = pathlib.Path(__file__).resolve().parents[1] / "src" / "qmt" / "web" / "templates"
CLOSED = "Upis ovog treninga je zatvoren — trener ga i dalje može urediti."
JSON = {"Accept": "application/json"}


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # a clip lands in a throwaway dir, never data/uploads nor a real R2
    # bucket (a developer's .env may carry live R2_* keys)
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "")
    yield


def make_user(email: str, is_trainer: bool = False, plans: tuple[str, ...] = ("grupni",), phone: str = "") -> int:
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    db.update_profile(u.id, email.split("@")[0].capitalize(), "Test", date(1990, 1, 1), phone)
    if is_trainer:
        with db.session_scope() as s:
            s.get(User, u.id).is_trainer = True
    for plan in plans:
        db.record_payment(u.id, plan)
    return u.id


def client_for(email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"email": email, "password": "lozinka123"}, follow_redirects=False)
    assert r.status_code == 303, "login failed"
    return c


def location(r) -> str:
    """A redirect's location as a person reads it ("+" a space)."""
    return unquote(r.headers["location"]).replace("+", " ")


def termin(uid: int | None, starts: datetime, title: str = "Grupni trening", minutes: int = 60) -> int:
    """A one-off termin at `starts`, booked by `uid` (directly: book()
    refuses a past one); its id."""
    sid = db.add_oneoff_session(title, starts, minutes, 8, None)
    if uid is not None:
        with db.session_scope() as s:
            s.add(Booking(user_id=uid, session_id=sid))
    return sid


def now() -> datetime:
    return datetime.now(config.TZ)


def library(*names: str) -> dict[str, int]:
    return {n: db.create_exercise(n) for n in names}


def bare(html: str) -> str:
    """A page with its texts' spans unwrapped (every text a copy slot)."""
    return re.sub(r'<span class="(?:ed )?t"[^>]*>(.*?)</span>', r"\1", html, flags=re.S)


def card_of(page: str, item_id: int) -> str:
    """A card of the page (its <details>), to the next card (part B: a
    slot's, a circuit's exercise's or a round's too), the next part or the
    add card."""
    chunk = page.split(f'id="stavka-{item_id}"')[1]
    return re.split(r'<details class="card gt-|<section class="gt-part"|<form id="dodaj"|class="gt-finish"'
                    r'|class="card gt-osvrt"', chunk)[0]


def tick(c: TestClient, tid: int, iid: int, polja: str, *rows: dict, effort: str = "", params=None, headers=JSON):
    """A tick's save as the page's script posts it: the ticked rows, numbered
    from 1, the rating; JSON back."""
    data = {"polja": polja, "rows": str(len(rows)), "effort": effort}
    for n, row in enumerate(rows, start=1):
        data.update({f"{k}_{n}": str(v) for k, v in row.items()})
    return c.post(f"/karton/trening/{tid}/stavke/{iid}/odradeno", data=data, headers=headers, params=params,
                  follow_redirects=False)


def done_of(iid: int) -> list[dict]:
    with db.session_scope() as s:
        return s.get(GymTrainingItem, iid).done_sets


# ---------- the migration ----------

def _migration(file: str):
    path = pathlib.Path(__file__).parents[1] / "alembic" / "versions" / file
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _run(step) -> None:
    """A revision's upgrade() or downgrade(), run for real on qmt_test."""
    with db.engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        step()


def _schema_diffs(tables: set[str]) -> list:
    """What compare_metadata finds between qmt_test and the models about these tables."""
    from alembic.autogenerate import compare_metadata

    def about(d):
        d = d[0] if isinstance(d, list) else d
        kind, obj = d[0], d[1]
        if kind.startswith("modify_") or kind in ("add_column", "remove_column"):
            return d[2]
        if kind in ("add_table", "remove_table"):
            return obj.name
        if kind in ("add_fk", "remove_fk"):
            return obj.parent.name
        return obj.table.name

    with db.engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    return [d for d in diffs if about(d) in tables]


GYM_TABLES = {"gym_trainings", "gym_training_items"}


def test_the_migration_makes_the_two_tables_and_takes_them_away():
    """c4e1b7f9a2d6, run on qmt_test as before it (no gym tables): both as
    the models have them, to their indexes (the partial unique one on a
    member and a termin), the CHECK on a part and the deferred position;
    nothing written, the karton's TrainingLog rows untouched; downgrade
    drops both, a training with them, the old rows still there; a second
    upgrade makes them again, empty."""
    mig = _migration("c4e1b7f9a2d6_gym_trainings.py")
    assert (mig.revision, mig.down_revision) == ("c4e1b7f9a2d6", "a7d3c5e9f214")
    ivan = make_user("ivan@test.local")
    with db.session_scope() as s:
        s.add(TrainingLog(user_id=ivan, date=date(2026, 11, 20), effort=6, note="Staro.", sets="[]"))
    with db.engine.begin() as conn:                 # (part B's gym_training_parts, a later table, points at them)
        conn.execute(sa_text("DROP TABLE gym_training_parts, gym_training_items, gym_trainings"))
    _run(mig.upgrade)
    assert GYM_TABLES <= set(sa_inspect(db.engine).get_table_names()) and _schema_diffs(GYM_TABLES) == []
    indexes = {i["name"]: i for i in sa_inspect(db.engine).get_indexes("gym_trainings")}
    assert indexes["uq_gym_trainings_user_session"]["unique"] and "ix_gym_trainings_user_id" in indexes
    with db.engine.connect() as conn:
        where = conn.execute(sa_text("SELECT pg_get_indexdef('uq_gym_trainings_user_session'::regclass)")).scalar_one()
        deferred = conn.execute(sa_text("SELECT condeferrable, condeferred FROM pg_constraint "
                                        "WHERE conname = 'uq_gym_training_items_position'")).one()
    assert "WHERE (session_id IS NOT NULL)" in where and tuple(deferred) == (True, True)
    sid = termin(ivan, now() - timedelta(hours=2))
    tid = db.gym_training_for(ivan, sid)
    iid = db.add_gym_item(tid, ivan, db.create_exercise("Plank"), "trening_c", seconds=30)
    with pytest.raises(Exception, match="ck_gym_training_items_section"):
        with db.engine.begin() as conn:
            conn.execute(sa_text("UPDATE gym_training_items SET section = 'kardio' WHERE id = :i"), {"i": iid})
    _run(mig.downgrade)
    assert not GYM_TABLES & set(sa_inspect(db.engine).get_table_names())
    assert [(x.effort, x.note) for x in db.training_logs(ivan)] == [(6, "Staro.")]
    _run(mig.upgrade)
    assert _schema_diffs(GYM_TABLES) == [] and db.gym_trainings(ivan) == []


# ---------- rule 1: whose and when ----------

def test_the_window_opens_four_hours_before_and_closes_at_the_end_of_the_next_day(monkeypatch):
    """gym_window: from GYM_OPENS_HOURS (4, env) before the termin's start
    until the midnight two days after its Zagreb date; gym_can_write at
    each edge (the first moment in, the last moment in, the first out); a
    training outside a termin (or let go of its termin) always; staff acting
    as the member before the window and after it. The knob through the env:
    6 moves the opening, the closing stays."""
    import subprocess
    import sys
    start = datetime(2026, 11, 25, 18, 0, tzinfo=config.TZ)                 # a Wednesday
    opens, closes = db.gym_window(start)
    assert (opens, closes) == (datetime(2026, 11, 25, 14, 0, tzinfo=config.TZ),
                               datetime(2026, 11, 27, 0, 0, tzinfo=config.TZ))
    t = GymTraining(session_id=1, starts_at=start, held_on=start.date())
    tick_ = timedelta(microseconds=1)
    assert [db.gym_can_write(t, at) for at in (opens - tick_, opens, closes - tick_, closes)] == [False, True, True, False]
    assert db.gym_can_write(t, opens - tick_, staff=True) and db.gym_can_write(t, closes, staff=True)
    outside = GymTraining(session_id=None, starts_at=None, held_on=date(2020, 1, 1))
    assert db.gym_can_write(outside, closes + timedelta(days=400))
    let_go = GymTraining(session_id=None, starts_at=start, held_on=start.date())
    assert db.gym_can_write(let_go, closes + timedelta(days=400))
    late = datetime(2026, 11, 25, 23, 30, tzinfo=config.TZ)                 # a late termin: the same midnight
    assert db.gym_window(late)[1] == closes
    monkeypatch.setattr(config, "GYM_OPENS_HOURS", 6)
    assert db.gym_window(start) == (datetime(2026, 11, 25, 12, 0, tzinfo=config.TZ), closes)
    assert db.gym_opens_text() == "Trening se otvara 6 h prije termina."
    monkeypatch.undo()
    knob = "from qmt import config; print(config.GYM_OPENS_HOURS)"
    env = {k: v for k, v in os.environ.items() if k != "GYM_OPENS_HOURS"}
    assert subprocess.run([sys.executable, "-c", knob], env=env, capture_output=True, text=True,
                          check=True).stdout.split() == ["4"]
    assert subprocess.run([sys.executable, "-c", knob], env=env | {"GYM_OPENS_HOURS": "6"}, capture_output=True,
                          text=True, check=True).stdout.split() == ["6"]


def test_a_member_writes_inside_his_window_and_staff_acting_as_him_at_any_time():
    """A member's training is his alone (another member's 404 on every
    route). Inside his window every write goes; after it, each is refused
    with "Upis ovog treninga je zatvoren — trener ga i dalje može urediti."
    and changes nothing, the page read only ("Upis je zatvoren — …": no
    input, no button). Staff acting as him (the trainer) write after the
    window and before it, the page saying "Za člana je upis zatvoren;
    uređuješ kao trener."."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    ex = library("Goblet čučanj")
    old = termin(ivan, now() - timedelta(days=3))                          # its window closed
    ahead = termin(ivan, now() + timedelta(hours=6))                        # not open yet
    tid = db.gym_training_for(ivan, old, staff=True)
    iid = db.add_gym_item(tid, ivan, ex["Goblet čučanj"], "trening", 3, 10, staff=True)
    ci = client_for("ivan@test.local")
    page = ci.get(f"/karton/trening/{tid}").text
    assert '<p class="gt-state"><span class="t">Upis je zatvoren — trener ga i dalje može urediti.</span></p>' in page
    body = page.split("<main")[1]
    assert "<input" not in body.split('id="plRest"')[0] and 'id="dodaj"' not in body and 'class="gt-tools"' not in body
    assert 'class="gt-finish"' not in body and "/isprazni" not in body
    r = tick(ci, tid, iid, "reps,kg", {"reps": 10, "kg": 20})
    assert (r.status_code, r.json()) == (400, {"ok": False, "error": CLOSED, "mark": ""}) and done_of(iid) == []
    for path, data in ((f"/karton/trening/{tid}/stavke", {"exercise_id": str(ex["Goblet čučanj"])}),
                       (f"/karton/trening/{tid}/stavke/{iid}", {"section": "trening", "sets": "2"}),
                       (f"/karton/trening/{tid}/stavke/{iid}/pomak", {"smjer": "gore"}),
                       (f"/karton/trening/{tid}/isprazni", {}), (f"/karton/trening/{tid}/osvrt", {"effort": "7"})):
        r = ci.post(path, data=data, follow_redirects=False)
        assert CLOSED in location(r), path
    r = ci.post(f"/karton/trening/{tid}/stavke/{iid}/obrisi", follow_redirects=False)
    assert CLOSED in location(r)
    [t] = db.gym_trainings(ivan)
    assert [(it.sets, it.done_sets) for it in t.items] == [(3, [])] and t.finished_at is None
    ca = client_for("ana@test.local")                                       # another member's: 404 everywhere
    assert ca.get(f"/karton/trening/{tid}").status_code == 404
    assert tick(ca, tid, iid, "reps,kg", {"reps": 10, "kg": 20}).status_code == 404
    for path in (f"/karton/trening/{tid}/osvrt", f"/karton/trening/{tid}/stavke", f"/karton/trening/{tid}/isprazni",
                 f"/karton/trening/{tid}/stavke/{iid}", f"/karton/trening/{tid}/stavke/{iid}/obrisi"):
        assert ca.post(path, data={"effort": "5", "exercise_id": "1"}).status_code == 404, path

    cs = client_for("coach@test.local")                                     # staff acting as ivan
    assert cs.post(f"/kao/{ivan}", follow_redirects=False).status_code == 303
    page = cs.get(f"/karton/trening/{tid}").text
    assert ('<p class="gt-state"><span class="t">Za člana je upis zatvoren; uređuješ kao trener.</span></p>' in page
            and 'id="dodaj"' in page)
    r = tick(cs, tid, iid, "reps,kg", {"reps": 10, "kg": 20}, headers={**JSON, "X-QMT-Kao": str(ivan)})
    assert r.json() == {"ok": True, "error": "", "mark": "1/3"} and done_of(iid) == [{"reps": 10, "kg": 20.0}]
    r = cs.get(f"/karton/termin/{ahead}/trening", follow_redirects=False)  # before the window: staff may
    assert location(r).startswith("/karton/trening/")
    early = int(location(r).rsplit("/", 1)[1])
    page = cs.get(f"/karton/trening/{early}").text
    assert "Za člana je upis zatvoren; uređuješ kao trener." in page
    cs.post("/kao/izlaz", follow_redirects=False)
    page = ci.get(f"/karton/trening/{early}").text                         # the member, before it: rule 2's words
    assert '<p class="gt-state">Trening se otvara 4 h prije termina.</p>' in page and 'id="dodaj"' not in page


def test_a_training_outside_a_termin_is_always_its_members():
    """A training outside a termin: no state line, every write at any date,
    its date changed ("promijeni datum", read_day's rules), deleted ("Obriši
    trening", asks first; then the karton). A termin's has no date form and
    is not deleted here (404): it goes with its booking."""
    ivan = make_user("ivan@test.local")
    ex = library("Plank")
    ci = client_for("ivan@test.local")
    r = ci.post("/karton/trening", data={"day": "2021-03-04"}, follow_redirects=False)
    tid = int(location(r).rsplit("/", 1)[1])
    page = bare(ci.get(f"/karton/trening/{tid}").text)
    assert "<h1>Trening izvan termina</h1>" in page and 'class="gt-state"' not in page
    assert '<span>četvrtak 4.3.2021.</span>' in page and 'action="/karton/trening/%d/datum"' % tid in page
    assert 'data-confirm-title="Obrisati trening?"' in page and "/isprazni" not in page
    assert ci.post(f"/karton/trening/{tid}/stavke", data={"exercise_id": str(ex["Plank"]), "seconds": "30"},
                   follow_redirects=False).status_code == 303
    r = ci.post(f"/karton/trening/{tid}/datum", data={"day": "2030-01-01"}, follow_redirects=False)
    assert location(r) == f"/karton/trening/{tid}?error=Neispravan datum."
    ci.post(f"/karton/trening/{tid}/datum", data={"day": "2021-03-05"})
    assert db.gym_training(tid, ivan).held_on == date(2021, 3, 5)
    sid = termin(ivan, now() - timedelta(hours=1))
    other = db.gym_training_for(ivan, sid)
    assert ci.post(f"/karton/trening/{other}/datum", data={"day": "2021-03-05"}).status_code == 404
    assert ci.post(f"/karton/trening/{other}/obrisi").status_code == 404
    assert 'action="/karton/trening/%d/datum"' % other not in ci.get(f"/karton/trening/{other}").text
    r = ci.post(f"/karton/trening/{tid}/obrisi", follow_redirects=False)
    assert location(r) == "/karton?ok=Trening je obrisan.#osvrti" and [t.id for t in db.gym_trainings(ivan)] == [other]


# ---------- rule 2: made lazily ----------

def test_a_termins_training_is_made_the_first_time_it_is_opened():
    """GET /karton/termin/<id>/trening makes the member's training of the
    termin (its title and start snapshotted, held_on its Zagreb date) and
    opens it; again, the same one. Refused, back at his karton with the
    sentence: no booking of his ("Nemaš rezervaciju za ovaj termin."), the
    termin canceled ("Termin je otkazan."), before the window ("Trening se
    otvara 4 h prije termina."), after it ("Upis ovog treninga je
    zatvoren."); one already made opens after the window, read only."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    ci = client_for("ivan@test.local")
    sid = termin(ivan, now() - timedelta(hours=1), title="Snaga")
    r = ci.get(f"/karton/termin/{sid}/trening", follow_redirects=False)
    [t] = db.gym_trainings(ivan)
    assert location(r) == f"/karton/trening/{t.id}"
    with db.session_scope() as s:
        sess = s.get(db.TrainingSession, sid)
    assert (t.session_id, t.title, t.starts_at, t.held_on) == (sid, "Snaga", sess.starts_at,
                                                               sess.starts_at.astimezone(config.TZ).date())
    assert location(ci.get(f"/karton/termin/{sid}/trening", follow_redirects=False)) == f"/karton/trening/{t.id}"
    assert len(db.gym_trainings(ivan)) == 1
    theirs = termin(ana, now() - timedelta(hours=1))
    canceled = termin(ivan, now() - timedelta(hours=1))
    db.set_session_canceled(canceled, True)
    for sess_id, sentence in ((theirs, "Nemaš rezervaciju za ovaj termin."), (999999, "Nemaš rezervaciju za ovaj termin."),
                              (canceled, "Termin je otkazan."),
                              (termin(ivan, now() + timedelta(hours=5)), "Trening se otvara 4 h prije termina."),
                              (termin(ivan, now() - timedelta(days=3)), "Upis ovog treninga je zatvoren.")):
        assert location(ci.get(f"/karton/termin/{sess_id}/trening", follow_redirects=False)) == f"/karton?error={sentence}"
    assert len(db.gym_trainings(ivan)) == 1
    later = termin(ivan, now() + timedelta(hours=3, minutes=59))           # the window open: made
    assert location(ci.get(f"/karton/termin/{later}/trening", follow_redirects=False)).startswith("/karton/trening/")
    gone = termin(ivan, now() - timedelta(days=3))                          # made by staff, then read after the window
    tid = db.gym_training_for(ivan, gone, staff=True)
    assert location(ci.get(f"/karton/termin/{gone}/trening", follow_redirects=False)) == f"/karton/trening/{tid}"
    assert "Upis je zatvoren" in ci.get(f"/karton/trening/{tid}").text
    assert TestClient(app).get(f"/karton/termin/{sid}/trening", follow_redirects=False).headers["location"].startswith(
        "/login?next=")


def test_two_opens_at_once_make_one_training():
    """Eight threads open one member's training of one termin at once
    (INSERT … ON CONFLICT DO NOTHING on the partial unique index), three
    rounds: one row each time, every thread handed its id."""
    ivan = make_user("ivan@test.local")
    for _ in range(3):
        sid = termin(ivan, now() - timedelta(hours=1))
        got, errors, gate = [], [], threading.Barrier(8)

        def open_it():
            try:
                gate.wait()
                got.append(db.gym_training_for(ivan, sid))
            except Exception as e:                                          # reported below
                errors.append(repr(e))

        threads = [threading.Thread(target=open_it) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert not errors and len(set(got)) == 1 and len(got) == 8
        with db.session_scope() as s:
            assert s.scalar(sa_text("SELECT count(*) FROM gym_trainings WHERE session_id = :s"), {"s": sid}) == 1


# ---------- rule 3: a cancelled booking takes its training with it ----------

def test_a_cancelled_booking_takes_its_training_or_lets_it_go():
    """cancel_booking, in its transaction: a training with nothing done in
    it goes, its items with it (an exercise added but no set ticked is no
    record); one that holds a record (a set saved, or its osvrt) stays, let
    go of its termin (session_id NULL), its title and start as they were,
    and the karton lists it as a training of its own. Another member's
    training of the same termin is untouched."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    ex = library("Goblet čučanj")
    ci = client_for("ivan@test.local")
    soon = now() + timedelta(hours=5)
    empty_sid, ticked_sid, osvrt_sid = (termin(ivan, soon + timedelta(minutes=k)) for k in (0, 10, 20))
    with db.session_scope() as s:
        s.add(Booking(user_id=ana, session_id=ticked_sid))
    empty, ticked, finished = (db.gym_training_for(ivan, x, staff=True) for x in (empty_sid, ticked_sid, osvrt_sid))
    hers = db.gym_training_for(ana, ticked_sid, staff=True)
    db.add_gym_item(empty, ivan, ex["Goblet čučanj"], "trening", 3, 10, staff=True)   # planned, nothing done
    iid = db.add_gym_item(ticked, ivan, ex["Goblet čučanj"], "trening", staff=True)
    db.save_gym_done(iid, ivan, [{"reps": 10, "kg": 20.0}], staff=True)
    db.finish_gym_training(finished, ivan, 6, None, "", staff=True)
    for sid in (empty_sid, ticked_sid, osvrt_sid):
        assert location(ci.post(f"/cancel/{sid}", follow_redirects=False)).endswith("ok=Rezervacija je otkazana.")
    left = {t.id: t for t in db.gym_trainings(ivan)}
    assert set(left) == {ticked, finished} and all(t.session_id is None for t in left.values())
    assert left[ticked].title == "Grupni trening" and left[ticked].starts_at is not None
    with db.session_scope() as s:
        assert s.scalar(sa_text("SELECT count(*) FROM gym_training_items WHERE training_id = :t"), {"t": empty}) == 0
    assert db.gym_training(hers, ana).session_id == ticked_sid
    page = ci.get("/karton").text
    assert f'id="gt-{ticked}"' in page and f'id="gt-{finished}"' in page
    assert db.gym_can_write(left[ticked])                                   # let go: a training outside a termin now


# ---------- the page ----------

GEN = ("ponedjeljka", "utorka", "srijede", "četvrtka", "petka", "subote", "nedjelje")


def when_text(at: datetime) -> str:
    """A termin's start as the page says it, "srijeda 25.11.2026. · 18:00"."""
    at = at.astimezone(config.TZ)
    return f"{WEEKDAYS[at.weekday()]} {at.day}.{at.month}.{at.year}. · {at:%H:%M}"


def until_text(at: datetime) -> str:
    """Its window's end as the state line says it, "četvrtka 26.11. u ponoć"."""
    day = at.astimezone(config.TZ).date() + timedelta(days=1)
    return f"{GEN[day.weekday()]} {day.day}.{day.month}. u ponoć"


def table(card: str) -> list[tuple]:
    """A card's set table: (the row's number, its inputs' values by field,
    ticked) per row."""
    out = []
    for done, n, cells in re.findall(r'<tr( class="is-done")?>\s*<th scope="row">(\d+)</th>(.*?)</tr>', card, re.S):
        pressed = re.search(r'aria-pressed="(true|false)"', cells).group(1) == "true"
        assert pressed == bool(done), "a ticked row is marked so"
        out.append((int(n), dict(re.findall(r'name="([a-z]+)_\d+" value="([^"]*)"', cells)), pressed))
    return out


def heads(card: str) -> list[str]:
    """A card's set table's column headers as a reader gets them."""
    thead = card.split("<thead>")[1].split("</thead>")[0]
    return [re.sub(r"<[^>]+>", "", h) for h in re.findall(r'<th scope="col"[^>]*>(.*?)</th>', thead)]


def test_the_page_names_its_training_and_says_until_when():
    """GET /karton/termin/<id>/trening opens the member's training of the
    termin: the crumbs (Karton / Trening), the kicker "Trening u dvorani",
    the termin's title as the h1 and right under it its date and time,
    "srijeda 25.11.2026. · 18:00", then "Upis je otvoren do četvrtka 26.11. u
    ponoć."; nothing in it yet, "Trening je još prazan — dodaj prvu vježbu.".
    "Dodaj vježbu" (the library once, #library-json; the tag chips, a tag two
    exercises carry; Dio on Glavni dio A), "Završi trening" (its osvrt), the
    rest bar; no "Isprazni trening" while it holds nothing. No phone reminder
    and no install banner on it (no_nudges: the member has no phone number,
    his karton has both)."""
    ivan = make_user("ivan@test.local")
    ex = {name: db.create_exercise(name, tags="girja") for name in ("Goblet čučanj", "Swing")}
    start = (now() - timedelta(hours=1)).replace(second=0, microsecond=0)
    sid = termin(ivan, start, title="Snaga")
    ci = client_for("ivan@test.local")
    r = ci.get(f"/karton/termin/{sid}/trening")
    [t] = db.gym_trainings(ivan)
    page = r.text
    assert str(r.url).endswith(f"/karton/trening/{t.id}") and r.status_code == 200
    assert ('<nav class="crumbs" aria-label="Putanja"><a href="/karton">Karton</a><span class="sep">/</span>'
            '<span class="here">Trening</span></nav>') in page
    assert ('<p class="gt-kicker"><span class="t">Trening u dvorani</span></p>\n<h1>Snaga</h1>\n<div class="gt-when">\n'
            f'  <span>{when_text(start)}</span>') in page
    assert f'<p class="gt-state"><span class="t">Upis je otvoren do</span> {until_text(start)}.</p>' in page
    assert '<p class="hint gt-empty"><span class="t">Trening je još prazan — dodaj prvu vježbu.</span></p>' in page
    assert 'class="gt-date"' not in page                                    # a termin's date is a fact
    add = page.split('<form id="dodaj" class="card gt-addcard" method="post" '
                     f'action="/karton/trening/{t.id}/stavke">')[1].split("</form>")[0]
    assert '<h2><span class="t">Dodaj vježbu</span></h2>' in add and 'data-tag="girja"' in add
    assert '<option value="trening" selected>Glavni dio A</option>' in add
    assert [o for o in re.findall(r'<option value="(\w+)"', add)] == ["zagrijavanje", "trening", "trening_b", "trening_c",
                                                                       "istezanje"]
    lib = json.loads(unescape(add.split('<script type="application/json" id="library-json">')[1].split("</script>")[0]))
    assert lib == [[ex["Goblet čučanj"], "Goblet čučanj", "girja"], [ex["Swing"], "Swing", "girja"]]
    assert page.count('id="library-json"') == 1
    assert (f'<div class="gt-finish"><a class="btn" href="/karton/trening/{t.id}/osvrt"><span class="t">Završi trening'
            '</span></a></div>') in page
    assert page.count('id="plRest"') == 1 and "/isprazni" not in page and 'class="card gt-card"' not in page
    assert 'id="phoneCard"' not in page and 'id="a2hs"' not in page
    karton = ci.get("/karton").text
    assert 'id="phoneCard"' in karton and 'id="a2hs"' in karton
    tabs = page.split('<nav class="tabs"')[1].split("</nav>")[0] if '<nav class="tabs"' in page else page
    assert '<a href="/karton" class="on">Karton</a>' in tabs


def test_a_card_says_what_was_given_and_what_was_done():
    """Each exercise a card (a native <details>): its summary the name in
    700, "Zadano: 3 × 10 · 20 kg" when anything was given (the dose's
    words), the mark ("2/3" for some sets, "✓" for every planned one; with
    no Serije given, "✓" for any); open, the pause and the note, the set
    table in its shape (Set · Pon. · Kg; Set · Sek.; Set · Pon. · Sek.; the
    ✓ column the script's), a row per planned set (three when none is
    given) prefilled with the zadano, a ticked row as saved, "+ serija",
    the rating (its number chosen as saved), the no-JS "Spremi", "Kako se
    izvodi" (its clip, what one rep is, the instructions; none when it has
    none of them) and the quiet row (Uredi zadano, ↑, ↓, Ukloni vježbu).
    Open: the first card not done. The parts in their order, each under its
    caption while it holds a row. An exercise gone from the library: its
    name, its sets as text, "Ukloni vježbu" alone."""
    ivan = make_user("ivan@test.local")
    goblet = db.create_exercise("Goblet čučanj", "Girja uz prsa, pete na podu.", "Do paralele i natrag.")
    plank, bug, push = (db.create_exercise(n) for n in ("Plank", "Mrtvi kukac", "Sklekovi"))
    sid = termin(ivan, now() - timedelta(hours=1))
    tid = db.gym_training_for(ivan, sid)
    a = db.add_gym_item(tid, ivan, goblet, "trening", 3, 10, kg=20, rest_seconds=60)
    db.update_gym_item(a, ivan, "trening", 3, 10, None, 20, 60, "Polako dolje.")
    b = db.add_gym_item(tid, ivan, plank, "istezanje", 2, seconds=30)
    c = db.add_gym_item(tid, ivan, bug, "trening_b", 2, 5, 30)
    d = db.add_gym_item(tid, ivan, push, "trening")
    db.save_gym_done(a, ivan, [{"reps": 10, "kg": 20.0}, {"reps": 9, "kg": 22.5}], effort=8)
    db.save_gym_done(d, ivan, [{"reps": 12, "kg": 0.0}])
    ci = client_for("ivan@test.local")
    page = ci.get(f"/karton/trening/{tid}").text
    caps = re.findall(r'<h2 class="dx-cap" id="dio-(\w+)">([^<]*)</h2>', page)
    assert caps == [("trening", "Glavni dio A"), ("trening_b", "Glavni dio B"), ("istezanje", "Istezanje")]
    ca, cb, cc, cd = (card_of(page, x) for x in (a, b, c, d))
    assert ('<span class="gt-name">Goblet čučanj</span>\n      <span class="gt-planned"><span class="t">Zadano:</span> '
            '3 × 10 · 20 kg</span>') in ca
    assert '<span class="gt-mark" data-mark role="img" aria-label="2/3 serije odrađene">2/3</span>' in ca
    assert '<span class="gt-mark ok" data-mark role="img" aria-label="odrađeno">✓</span>' in cd   # no Serije: any
    assert '<span class="gt-mark" data-mark></span>' in cb and 'class="gt-planned"' not in cd
    assert ("2 × 30 s" in cb and "2 × 5 × 30 s" in cc)
    assert heads(ca) == heads(cd) == ["Set", "Pon.", "Kg", "✓"] and heads(cb) == ["Set", "Sek.", "✓"]
    assert heads(cc) == ["Set", "Pon.", "Sek.", "✓"]
    assert table(ca) == [(1, {"reps": "10", "kg": "20"}, True), (2, {"reps": "9", "kg": "22.5"}, True),
                         (3, {"reps": "10", "kg": "20"}, False)]
    assert table(cb) == [(1, {"sec": "30"}, False), (2, {"sec": "30"}, False)]
    assert table(cc) == [(1, {"reps": "5", "sec": "30"}, False), (2, {"reps": "5", "sec": "30"}, False)]
    assert table(cd) == [(1, {"reps": "12", "kg": ""}, True), (2, {"reps": "", "kg": ""}, False),
                         (3, {"reps": "", "kg": ""}, False)]
    assert '<p class="gt-sub"><span class="t">Odmor između serija:</span> 60 s · Polako dolje.</p>' in ca
    assert 'class="gt-sub"' not in cd
    assert ('<th scope="col" class="pl-tick" aria-label="Odrađena serija" hidden><span aria-hidden="true">✓</span></th>'
            in ca)
    assert ca.count('class="pl-done" aria-pressed=') == 3 and 'aria-label="Serija 3 odrađena"' in ca
    assert (f'<form class="gt-log" id="gt-log-{a}" method="post" action="/karton/trening/{tid}/stavke/{a}/odradeno"\n'
            '          data-sets="3" data-rest="60" data-max="20"\n          data-reps="10" data-kg="20"\n'
            '          data-sec="">') in ca
    assert '<input type="hidden" name="polja" value="reps,kg">' in ca and '<input type="hidden" name="rows" value="3">' in ca
    assert 'name="polja" value="seconds"' in cb and 'name="polja" value="reps,seconds"' in cc
    assert '<button type="button" class="act gt-add-set" hidden><span class="t">+ serija</span></button>' in ca
    assert (f'<p class="pl-rate-h" id="gt-rate-{a}"><span class="t">Koliko je bilo teško?</span> <span class="pl-opt">'
            '<span class="t">(neobavezno)</span></span></p>') in ca
    assert ca.count('name="effort"') == 10 and 'value="8" checked' in ca and " checked" not in cb
    assert '<button type="submit" class="btn btn-sm gt-save"><span class="t">Spremi</span></button>' in ca
    assert ('<summary><span class="t">Kako se izvodi</span></summary>' in ca
            and '<p><strong><span class="t">Jedno ponavljanje:</span></strong> Do paralele i natrag.</p>' in ca
            and "<p>Girja uz prsa, pete na podu.</p>" in ca)
    assert 'class="gt-how' not in cd                                         # nothing to show how
    assert '<summary class="act act-quiet"><span class="t">Uredi zadano</span></summary>' in ca
    assert (f'<button type="submit" form="gt-up-{a}" class="act act-quiet" disabled aria-label="Pomakni gore: '
            'Goblet čučanj">↑</button>') in ca
    assert f'<button type="submit" form="gt-down-{a}" class="act act-quiet" aria-label=' in ca
    assert f'<button type="submit" form="gt-down-{d}" class="act act-quiet" disabled aria-label=' in cd
    assert (f'<button type="submit" form="gt-x-{a}" class="act act-quiet"><span class="t">Ukloni vježbu</span>'
            '</button>') in ca
    assert re.search(rf'<details class="card gt-card" id="stavka-{a}" open>', page)            # the first not done
    assert not re.search(rf'id="stavka-(?:{d}|{b}|{c})" open', page)
    # the Dio of the row added last, and every part's name as the training gives it (part_label)
    assert '<option value="trening" selected>Glavni dio A</option>' in page.split('id="dodaj"')[1]
    form = ca.split('<form class="gt-form"')[1].split("</form>")[0]
    assert [re.sub(r"<[^>]+>", "", x) for x in re.findall(r'<label for="gt-\d+-\w+">(.*?)</label>', form)] == [
        "Dio", "Serije", "Ponavljanja", "Sekunde", "Kilaža (kg)", "Pauza (s)", "Napomena"]
    assert ('value="3"' in form and 'name="reps" inputmode="numeric" min="1" max="999" value="10"' in form
            and 'step="0.5" value="20"' in form and 'name="rest" inputmode="numeric" min="0" max="3600" value="60"' in form
            and 'value="Polako dolje."' in form)
    # an exercise gone from the library: its name and sets as text, "Ukloni vježbu" alone
    db.delete_exercise(goblet)
    page = ci.get(f"/karton/trening/{tid}").text
    ca = card_of(page, a)
    assert '<span class="gt-name">Goblet čučanj</span>' in ca
    assert ('<p class="gt-done"><strong><span class="t">Odrađeno:</span></strong> 10 × 20 kg · 9 × 22,5 kg · težina '
            '8/10</p>') in ca
    assert "<input" not in ca and "Uredi zadano" not in ca and f'form="gt-up-{a}"' not in ca and f'form="gt-x-{a}"' in ca
    r = tick(ci, tid, a, "reps,kg", {"reps": 10, "kg": 20})
    assert r.json() == {"ok": False, "error": "Nepoznata vježba.", "mark": ""}
    assert done_of(a) == [{"reps": 10, "kg": 20.0}, {"reps": 9, "kg": 22.5}]


def test_dodaj_vjezbu_puts_an_exercise_last_in_its_part():
    """POST …/stavke: an exercise of the library, last in the part chosen,
    its name snapshotted, with what was given (each optional: none, or
    Serije, Ponavljanja, Sekunde, Kilaža (kg) "22,5", Pauza (s)); back at
    its card, open, ?dodano=1 (the focus in its first input). The add
    card's Dio is then the part of the row added last. Refused at the add
    card, nothing added, the sentence there and not at the top: nothing
    picked ("Odaberi vježbu s popisa."), an exercise not in the library
    ("Nepoznata vježba."), a part that is none ("Odaberi dio treninga."), a
    number out of the day editor's limits ("Neispravan broj."). No cap on
    the rows."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    ci = client_for("ivan@test.local")

    def add(**form):
        return ci.post(f"/karton/trening/{tid}/stavke", data=form, follow_redirects=False)

    r = add(exercise_id=str(ex["Goblet čučanj"]), section="trening")
    [it] = db.gym_training(tid, ivan).items
    assert location(r) == f"/karton/trening/{tid}?stavka={it.id}&dodano=1#stavka-{it.id}"
    assert (it.exercise_name, it.section, it.position, it.sets, it.reps, it.seconds, it.kg, it.rest_seconds, it.note,
            it.done_sets, it.effort) == ("Goblet čučanj", "trening", 1, None, None, None, None, None, "", [], None)
    page = ci.get(f"/karton/trening/{tid}?stavka={it.id}&dodano=1").text
    assert re.search(rf'id="stavka-{it.id}" open>', page) and 'class="gt-empty"' not in page
    assert table(card_of(page, it.id)) == [(n, {"reps": "", "kg": ""}, False) for n in (1, 2, 3)]
    r = add(exercise_id=str(ex["Plank"]), section="trening_b", sets="2", seconds="45", rest="30")
    plank = db.gym_training(tid, ivan).items[-1]
    assert location(r) == f"/karton/trening/{tid}?stavka={plank.id}&dodano=1#stavka-{plank.id}"
    assert (plank.section, plank.position, plank.sets, plank.reps, plank.seconds, plank.kg, plank.rest_seconds) == (
        "trening_b", 2, 2, None, 45, None, 30)
    page = ci.get(f"/karton/trening/{tid}").text
    assert '<option value="trening_b" selected>Glavni dio B</option>' in page.split('<form id="dodaj"')[1]
    add(exercise_id=str(ex["Goblet čučanj"]), section="trening", sets="3", reps="10", kg="22,5")
    third = db.gym_training(tid, ivan).items[-1]
    assert (third.position, third.sets, third.reps, third.kg) == (3, 3, 10, Decimal("22.5"))
    for form, sentence in (({"exercise_id": ""}, "Odaberi vježbu s popisa."),
                           ({"exercise_id": "abc"}, "Odaberi vježbu s popisa."),
                           ({"exercise_id": "999999"}, "Nepoznata vježba."),
                           ({"exercise_id": str(ex["Plank"]), "section": "kardio"}, "Odaberi dio treninga."),
                           ({"exercise_id": str(ex["Plank"]), "sets": "0"}, "Neispravan broj."),
                           ({"exercise_id": str(ex["Plank"]), "reps": "1000"}, "Neispravan broj."),
                           ({"exercise_id": str(ex["Plank"]), "kg": "2,3"}, "Neispravan broj."),
                           ({"exercise_id": str(ex["Plank"]), "rest": "4000"}, "Neispravan broj.")):
        r = add(**{"section": "trening", **form})
        assert location(r) == f"/karton/trening/{tid}?dodaj=1&error={sentence}#dodaj", form
    assert len(db.gym_training(tid, ivan).items) == 3
    page = ci.get(f"/karton/trening/{tid}?dodaj=1&error=Odaberi vježbu s popisa.").text
    card = page.split('<form id="dodaj"')[1].split("</form>")[0]
    assert '<div class="alert" role="alert"><span>Odaberi vježbu s popisa.</span></div>' in card
    assert page.count('<div class="alert" role="alert">') == 1
    for _ in range(30):                                                    # no cap on the rows
        add(exercise_id=str(ex["Plank"]), section="istezanje")
    assert len(db.gym_training(tid, ivan).items) == 33


def test_uredi_zadano_changes_what_was_given_and_keeps_what_was_done():
    """POST …/stavke/<id> ("Uredi zadano"): its part, sets, reps, seconds,
    kg, the pause and a note, the day editor's row form's rules; back at
    its card, "Spremljeno." in it (not at the top), the card's words and
    rows the new zadano, what was done as saved. A refusal comes back at
    the card with its form open (?uredi=1) and changes nothing. Moved to
    another part, it goes last there. A changed shape (seconds given to a
    reps exercise) makes a page drawn before it refuse its tick."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    a = db.add_gym_item(tid, ivan, ex["Goblet čučanj"], "trening", 3, 10, kg=20)
    b = db.add_gym_item(tid, ivan, ex["Plank"], "trening_b", 2, seconds=30)
    db.save_gym_done(a, ivan, [{"reps": 10, "kg": 20.0}])
    ci = client_for("ivan@test.local")

    def save(iid, **form):
        return ci.post(f"/karton/trening/{tid}/stavke/{iid}", data=form, follow_redirects=False)

    r = save(a, section="trening", sets="4", reps="8", seconds="", kg="22,5", rest="90", note="Polako dolje.")
    assert location(r) == f"/karton/trening/{tid}?stavka={a}&ok=Spremljeno.#stavka-{a}"
    with db.session_scope() as s:
        it = s.get(GymTrainingItem, a)
        assert (it.sets, it.reps, it.seconds, it.kg, it.rest_seconds, it.note) == (4, 8, None, Decimal("22.5"), 90,
                                                                                    "Polako dolje.")
    assert done_of(a) == [{"reps": 10, "kg": 20.0}]
    page = ci.get(f"/karton/trening/{tid}?stavka={a}&ok=Spremljeno.").text
    card = card_of(page, a)
    assert '<div class="alert ok" role="status">Spremljeno.</div>' in card and page.count('class="alert ok"') == 1
    assert '<span class="t">Zadano:</span> 4 × 8 · 22,5 kg</span>' in card
    assert '<p class="gt-sub"><span class="t">Odmor između serija:</span> 90 s · Polako dolje.</p>' in card
    assert table(card) == [(1, {"reps": "10", "kg": "20"}, True)] + [(n, {"reps": "8", "kg": "22.5"}, False)
                                                                      for n in (2, 3, 4)]
    for form, sentence in (({"sets": "100"}, "Neispravan broj."), ({"reps": "x"}, "Neispravan broj."),
                           ({"kg": "0"}, "Neispravan broj."), ({"rest": "3601"}, "Neispravan broj."),
                           ({"seconds": "0"}, "Neispravan broj."),
                           ({"note": "x" * 501}, "Napomena može imati najviše 500 znakova."),
                           ({"section": "kardio"}, "Odaberi dio treninga.")):
        r = save(a, **{"section": "trening", **form})
        assert location(r) == f"/karton/trening/{tid}?stavka={a}&uredi=1&error={sentence}#stavka-{a}", form
    with db.session_scope() as s:
        assert (s.get(GymTrainingItem, a).sets, s.get(GymTrainingItem, a).note) == (4, "Polako dolje.")
    page = ci.get(f"/karton/trening/{tid}?stavka={a}&uredi=1&error=Neispravan broj.").text
    card = card_of(page, a)
    assert '<details class="gt-edit" open>' in card and '<div class="alert" role="alert"><span>Neispravan broj.' in card
    assert '<details class="gt-edit" open>' not in card_of(page, b)
    save(a, section="trening_b", sets="4", reps="8", kg="22,5")                     # to another part: last in it
    assert [it.id for it in db.gym_training(tid, ivan).by_section["trening_b"]] == [b, a]
    save(a, section="trening_b", sets="2", reps="5", seconds="30")                 # its shape now reps and seconds
    r = tick(ci, tid, a, "reps,kg", {"reps": 10, "kg": 20})
    assert r.json() == {"ok": False, "error": "Trening se u međuvremenu promijenio — provjeri vježbu i spremi ponovno.",
                        "mark": ""} and done_of(a) == [{"reps": 10, "kg": 20.0}]
    other = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=2)))
    assert ci.post(f"/karton/trening/{other}/stavke/{a}", data={"section": "trening"}).status_code == 404


def test_moving_removing_and_emptying():
    """↑ / ↓ swap an exercise with its neighbour in its part (at either end,
    or no direction, nothing moves; ↑ disabled on a part's first, ↓ on its
    last); "Ukloni vježbu" asks first only while it holds a ticked set (its
    words always on the form, data-ask-*, which the script turns into
    data-confirm-*), and it goes with its sets; "Isprazni trening" (asks:
    "Isprazniti trening?") takes every exercise, the osvrt stays."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank", "Sklekovi")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    a, b, c = (db.add_gym_item(tid, ivan, ex[n], "trening") for n in ("Goblet čučanj", "Plank", "Sklekovi"))
    alone = db.add_gym_item(tid, ivan, ex["Plank"], "istezanje")
    ci = client_for("ivan@test.local")

    def move(iid, smjer):
        return ci.post(f"/karton/trening/{tid}/stavke/{iid}/pomak", data={"smjer": smjer}, follow_redirects=False)

    def order(key="trening"):
        return [it.id for it in db.gym_training(tid, ivan).by_section[key]]

    assert location(move(b, "gore")) == f"/karton/trening/{tid}?stavka={b}#stavka-{b}" and order() == [b, a, c]
    for iid, smjer in ((b, "gore"), (c, "dolje"), (a, "lijevo"), (alone, "gore"), (alone, "dolje")):
        move(iid, smjer)
    assert order() == [b, a, c] and order("istezanje") == [alone]
    move(a, "dolje")
    assert order() == [b, c, a]
    page = ci.get(f"/karton/trening/{tid}").text
    for iid, up, down in ((b, True, False), (c, False, False), (a, False, True), (alone, True, True)):
        assert (f'form="gt-up-{iid}" class="act act-quiet" disabled' in page) is up, iid
        assert (f'form="gt-down-{iid}" class="act act-quiet" disabled' in page) is down, iid
    db.save_gym_done(a, ivan, [{"reps": 10, "kg": 0.0}])
    page = ci.get(f"/karton/trening/{tid}").text

    def drop(iid):
        return page.split(f'<form id="gt-x-{iid}" method="post" action="/karton/trening/{tid}/stavke/{iid}/obrisi"')[1] \
            .split("</form>")[0]

    ask = 'data-ask-title="Ukloniti vježbu?" data-ask="Upisane serije ove vježbe se brišu." data-ask-cta="Ukloni vježbu"'
    assert ask in drop(c) and "data-confirm" not in drop(c)
    assert (ask + ' data-confirm-title="Ukloniti vježbu?" data-confirm="Upisane serije ove vježbe se brišu." '
            'data-confirm-cta="Ukloni vježbu">') in drop(a)
    r = ci.post(f"/karton/trening/{tid}/stavke/{a}/obrisi", follow_redirects=False)
    assert location(r) == f"/karton/trening/{tid}?ok=Vježba je uklonjena." and order() == [b, c]
    db.finish_gym_training(tid, ivan, 6, "dobro", "Dobro je.")
    page = ci.get(f"/karton/trening/{tid}").text
    assert (f'<form method="post" action="/karton/trening/{tid}/isprazni"\n'
            '          data-confirm-title="Isprazniti trening?"\n'
            '          data-confirm="Sve vježbe i upisane serije ovog treninga se brišu."\n'
            '          data-confirm-cta="Isprazni">\n'
            '      <button type="submit" class="act act-quiet gt-drop"><span class="t">Isprazni trening</span></button>') \
        in page
    assert f'action="/karton/trening/{tid}/obrisi"' not in page                # a termin's goes with its booking
    r = ci.post(f"/karton/trening/{tid}/isprazni", follow_redirects=False)
    assert location(r) == f"/karton/trening/{tid}?ok=Trening je ispražnjen."
    t = db.gym_training(tid, ivan)
    assert t.items == [] and (t.effort, t.feeling, t.note) == (6, "dobro", "Dobro je.") and t.finished_at is not None
    assert "/isprazni" not in ci.get(f"/karton/trening/{tid}").text            # nothing left to empty


def test_the_osvrt_is_zavrsi_trening():
    """"Završi trening" → …/osvrt: the finish screen's clothes (its kicker
    "Osvrt na trening", the title, the date and time; Napor, ten round
    buttons, required; Osjećaj; Komentar; "Spremi trening"; "Natrag na
    trening"), no nudges. Refused ("Neispravan osvrt.": no napor, one
    outside 1–10, an osjećaj that is none): the page again, 400, what was
    chosen kept, nothing stored. Saved: the karton at its diary row,
    "Trening je spremljen.", the page saying the osvrt ("napor 7/10 ·
    Dobro", the comment, "Uredi osvrt") with no "Završi trening"; saved
    again, its first save's time stays."""
    ivan = make_user("ivan@test.local")
    start = (now() - timedelta(hours=2)).replace(second=0, microsecond=0)
    tid = db.gym_training_for(ivan, termin(ivan, start, title="Snaga"))
    ci = client_for("ivan@test.local")
    page = ci.get(f"/karton/trening/{tid}/osvrt").text
    assert ('<p class="kr-eyebrow"><span class="t">Osvrt na trening</span></p>\n  <h1>Snaga</h1>\n'
            f'  <p class="kr-when">{when_text(start)}</p>') in page
    assert f'<form class="kr-form" method="post" action="/karton/trening/{tid}/osvrt">' in page
    assert re.findall(r'name="effort" value="(\d+)" required', page) == [str(n) for n in range(1, 11)]
    assert re.findall(r'name="feeling" value="(\w+)"', page) == ["slabo", "dobro", "odlicno"]
    assert '<button type="submit" class="btn"><span class="t">Spremi trening</span></button>' in page
    assert f'<a class="act act-quiet" href="/karton/trening/{tid}"><span class="t">Natrag na trening</span></a>' in page
    assert 'id="phoneCard"' not in page and 'id="a2hs"' not in page

    def post(**form):
        return ci.post(f"/karton/trening/{tid}/osvrt", data=form, follow_redirects=False)

    for form in ({"effort": "", "feeling": "dobro", "note": "Teško."}, {"effort": "11"}, {"effort": "0"},
                 {"effort": "x"}, {"effort": "7", "feeling": "super"}):
        r = post(**form)
        assert r.status_code == 400 and '<div class="alert" role="alert"><span>Neispravan osvrt.</span></div>' in r.text
    r = post(effort="", feeling="dobro", note="Teško.")
    assert 'value="dobro" checked' in r.text and ">Teško.</textarea>" in r.text and " required checked" not in r.text
    assert db.gym_training(tid, ivan).finished_at is None
    r = post(effort="7", feeling="dobro", note="  Teško.  ")
    assert location(r) == f"/karton?ok=Trening je spremljen.#gt-{tid}"
    t = db.gym_training(tid, ivan)
    first = t.finished_at
    assert (t.effort, t.feeling, t.note) == (7, "dobro", "Teško.") and first is not None
    page = ci.get(f"/karton/trening/{tid}").text
    assert ('<section class="card gt-osvrt" aria-labelledby="gt-osvrt-h">\n    <h2 id="gt-osvrt-h"><span class="t">Osvrt'
            '</span></h2>\n    <p class="gt-facts">napor 7/10 · Dobro</p>\n    <p class="gt-comment">Teško.</p>\n'
            f'    <a class="act" href="/karton/trening/{tid}/osvrt"><span class="t">Uredi osvrt</span></a>') in page
    assert 'class="gt-finish"' not in page
    again = ci.get(f"/karton/trening/{tid}/osvrt").text
    assert 'value="7" required checked' in again and 'value="dobro" checked' in again and ">Teško.</textarea>" in again
    post(effort="5", feeling="", note="")
    t = db.gym_training(tid, ivan)
    assert (t.effort, t.feeling, t.note, t.finished_at) == (5, None, "", first)
    assert '<p class="gt-facts">napor 5/10</p>' in ci.get(f"/karton/trening/{tid}").text


def test_after_the_window_the_page_reads_only():
    """Past its window the member's page is the record: the state line says
    so, every card its sets as text ("Odrađeno: …", "—" for none), the
    osvrt's facts without "Uredi osvrt", no add card, no "Završi trening",
    no rest bar, no form at all; …/osvrt leads back to the page."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(days=3)), staff=True)
    a = db.add_gym_item(tid, ivan, ex["Goblet čučanj"], "trening", 3, 10, staff=True)
    b = db.add_gym_item(tid, ivan, ex["Plank"], "trening", staff=True)
    db.save_gym_done(a, ivan, [{"reps": 10, "kg": 20.0}], effort=6, staff=True)
    db.finish_gym_training(tid, ivan, 7, None, "Dobro.", staff=True)
    ci = client_for("ivan@test.local")
    page = ci.get(f"/karton/trening/{tid}").text
    main = page.split("<main")[1].split("</main>")[0]
    assert '<p class="gt-state"><span class="t">Upis je zatvoren — trener ga i dalje može urediti.</span></p>' in main
    assert '<p class="gt-done"><strong><span class="t">Odrađeno:</span></strong> 10 × 20 kg · težina 6/10</p>' in main
    assert '<p class="gt-done"><strong><span class="t">Odrađeno:</span></strong> —</p>' in card_of(page, b)
    assert '<p class="gt-facts">napor 7/10</p>' in main and "Uredi osvrt" not in main
    for gone in ("<form", "<input", "<button", 'id="dodaj"', "gt-finish", 'id="plRest"', "gt-tools", "library-json"):
        assert gone not in main, gone
    r = ci.get(f"/karton/trening/{tid}/osvrt", follow_redirects=False)
    assert location(r) == f"/karton/trening/{tid}"


# ---------- rule 4: a tick saves ----------

def test_a_tick_saves_the_ticked_rows_whole():
    """POST …/odradeno, as the page's script posts it (Accept JSON: {"ok",
    "error", "mark"}): the exercise's ticked rows saved whole, its rating
    with them; a tick more, an untick (the rows still ticked), a ticked
    row's number changed: each the list as it is then; none ticked, nothing
    done (no time, no rating). Each shape as its zadano asks (PON. · KG,
    SEK., PON. · SEK.). Refused, 400, nothing changed: 21 sets ("Najviše 20
    serija."), a number that is none or out of range ("Neispravan broj."),
    a rating outside 1–10, a page drawn for another shape. An exercise of
    another training: 404. Without JS the card's "Spremi" posts every row
    that holds a number and comes back at the card, its word in it."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank", "Mrtvi kukac")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    goblet = db.add_gym_item(tid, ivan, ex["Goblet čučanj"], "trening", 3, 10, kg=20, rest_seconds=60)
    plank = db.add_gym_item(tid, ivan, ex["Plank"], "trening", 2, seconds=30)
    bug = db.add_gym_item(tid, ivan, ex["Mrtvi kukac"], "trening", 2, 5, 30)
    ci = client_for("ivan@test.local")

    def item(iid):
        with db.session_scope() as s:
            return s.get(GymTrainingItem, iid)

    r = tick(ci, tid, goblet, "reps,kg", {"reps": 10, "kg": 20})
    assert (r.status_code, r.json()) == (200, {"ok": True, "error": "", "mark": "1/3"})
    assert done_of(goblet) == [{"reps": 10, "kg": 20.0}] and item(goblet).done_at is not None
    r = tick(ci, tid, goblet, "reps,kg", {"reps": 10, "kg": 20}, {"reps": 9, "kg": "22,5"}, effort="8")
    assert r.json()["mark"] == "2/3" and done_of(goblet) == [{"reps": 10, "kg": 20.0}, {"reps": 9, "kg": 22.5}]
    assert item(goblet).effort == 8
    r = tick(ci, tid, goblet, "reps,kg", {"reps": 9, "kg": "22.5"}, effort="8")          # the first unticked
    assert r.json()["mark"] == "1/3" and done_of(goblet) == [{"reps": 9, "kg": 22.5}]
    tick(ci, tid, goblet, "reps,kg", {"reps": 9, "kg": "25"}, effort="8")                # its number changed
    assert done_of(goblet) == [{"reps": 9, "kg": 25.0}]
    r = tick(ci, tid, goblet, "reps,kg", *[{"reps": 10, "kg": 20}] * 3, effort="8")
    assert r.json()["mark"] == "✓" and len(done_of(goblet)) == 3
    r = tick(ci, tid, goblet, "reps,kg")                                                 # the last unticked
    assert r.json() == {"ok": True, "error": "", "mark": ""} and done_of(goblet) == []
    assert (item(goblet).effort, item(goblet).done_at) == (None, None)
    r = tick(ci, tid, plank, "seconds", {"sec": 30}, {"sec": 35})
    assert r.json()["mark"] == "✓" and done_of(plank) == [{"seconds": 30}, {"seconds": 35}]
    r = tick(ci, tid, bug, "reps,seconds", {"reps": 5, "sec": 30})
    assert r.json()["mark"] == "1/2" and done_of(bug) == [{"reps": 5, "seconds": 30}]
    for polja, rows, effort, sentence in (
            ("seconds", [{"sec": 30}] * 21, "", "Najviše 20 serija."),
            ("seconds", [{"sec": "abc"}], "", "Neispravan broj."),
            ("seconds", [{"sec": "3601"}], "", "Neispravan broj."),
            ("seconds", [{"sec": "-5"}], "", "Neispravan broj."),
            ("seconds", [{"sec": 30}], "11", "Neispravan broj."),
            ("seconds", [{"sec": 30}], "x", "Neispravan broj."),
            ("reps,kg", [{"reps": 10, "kg": 20}], "", "Trening se u međuvremenu promijenio — provjeri vježbu i spremi "
                                                      "ponovno.")):
        r = tick(ci, tid, plank, polja, *rows, effort=effort)
        assert (r.status_code, r.json()) == (400, {"ok": False, "error": sentence, "mark": ""}), (rows[:1], effort)
    assert done_of(plank) == [{"seconds": 30}, {"seconds": 35}]
    # a ticked row with no number in it (an exercise given no zadano starts
    # empty) is no set: the whole save refused, nothing changed, so a tick
    # shown is always a set saved (Fable's review, 26.11.2026)
    for rows in ([{"sec": ""}], [{"sec": 30}, {"sec": " "}]):
        r = tick(ci, tid, plank, "seconds", *rows)
        assert (r.status_code, r.json()) == (400, {"ok": False, "error": "Upiši broj pa označi seriju.", "mark": ""})
    r = tick(ci, tid, goblet, "reps,kg", {"reps": "", "kg": ""})
    assert r.status_code == 400 and r.json()["error"] == "Upiši broj pa označi seriju."
    assert tick(ci, tid, goblet, "reps,kg", {"reps": 10, "kg": ""}).json()["ok"]         # one number is a set
    assert done_of(goblet) == [{"reps": 10, "kg": 0.0}] and tick(ci, tid, goblet, "reps,kg").json()["ok"]
    assert done_of(plank) == [{"seconds": 30}, {"seconds": 35}] and done_of(goblet) == []
    rows = [{"sec": 30}] * 20                                                            # twenty: the most
    assert tick(ci, tid, plank, "seconds", *rows).json()["mark"] == "✓" and len(done_of(plank)) == 20
    other = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=2)))
    assert tick(ci, other, goblet, "reps,kg", {"reps": 10, "kg": 20}).status_code == 404
    # without JS: "Spremi" posts every row; the ones that hold a number are what was done
    r = ci.post(f"/karton/trening/{tid}/stavke/{goblet}/odradeno",
                data={"polja": "reps,kg", "rows": "3", "reps_1": "10", "kg_1": "20", "reps_2": "8", "kg_2": "20",
                      "reps_3": "", "kg_3": "", "effort": "7"}, follow_redirects=False)
    assert location(r) == f"/karton/trening/{tid}?stavka={goblet}&ok=Spremljeno.#stavka-{goblet}"
    assert done_of(goblet) == [{"reps": 10, "kg": 20.0}, {"reps": 8, "kg": 20.0}] and item(goblet).effort == 7
    page = ci.get(f"/karton/trening/{tid}?stavka={goblet}&ok=Spremljeno.").text
    assert '<div class="alert ok" role="status">Spremljeno.</div>' in card_of(page, goblet)
    r = ci.post(f"/karton/trening/{tid}/stavke/{goblet}/odradeno",
                data={"polja": "reps,kg", "rows": "1", "reps_1": "abc", "kg_1": "20"}, follow_redirects=False)
    assert location(r) == f"/karton/trening/{tid}?stavka={goblet}&error=Neispravan broj.#stavka-{goblet}"
    assert len(done_of(goblet)) == 2
    db.save_gym_done(goblet, ivan, [{"reps": 10, "kg": 20.0, "round": 2}])               # a round's set (part B) is kept
    assert done_of(goblet) == [{"reps": 10, "kg": 20.0, "round": 2}]


def test_two_ticks_at_once_keep_both_exercises():
    """Eight exercises of one training ticked at the same moment (eight
    threads; each save takes the training's row FOR UPDATE), three times:
    every exercise holds what was ticked of it, none lost."""
    ivan = make_user("ivan@test.local")
    eid = db.create_exercise("Goblet čučanj")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    items = [db.add_gym_item(tid, ivan, eid, "trening", 3, 10) for _ in range(8)]
    for times in (1, 2, 3):
        errors, gate = [], threading.Barrier(len(items))

        def save(k, iid, times=times):
            try:
                gate.wait()
                db.save_gym_done(iid, ivan, [{"reps": k + 1, "kg": float(times)}] * times, effort=k + 1)
            except Exception as e:                                          # reported below
                errors.append(repr(e))

        threads = [threading.Thread(target=save, args=(k, iid)) for k, iid in enumerate(items)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert not errors
        assert [done_of(iid) for iid in items] == [[{"reps": k + 1, "kg": float(times)}] * times for k in range(8)]


# ---------- rules 5, 6, 7, 8 ----------

def test_a_gym_training_has_no_load_next_time():
    """Rule 5: a rated gym exercise changes nothing next time. A new
    training's rows are its zadano (none given: empty), never last time's
    weights or an adjusted one, no "Prošli put" line; next_load reads the
    online passes alone."""
    ivan = make_user("ivan@test.local")
    eid = db.create_exercise("Goblet čučanj")
    first = db.gym_training_for(ivan, termin(ivan, now() - timedelta(days=1)), staff=True)
    iid = db.add_gym_item(first, ivan, eid, "trening", 3, 10, kg=20, staff=True)
    db.save_gym_done(iid, ivan, [{"reps": 10, "kg": 20.0}] * 3, effort=2, staff=True)     # easy: online would add 5 %
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    planned = db.add_gym_item(tid, ivan, eid, "trening", 3, 10, kg=20)
    nothing = db.add_gym_item(tid, ivan, eid, "trening")
    page = client_for("ivan@test.local").get(f"/karton/trening/{tid}").text
    assert table(card_of(page, planned)) == [(n, {"reps": "10", "kg": "20"}, False) for n in (1, 2, 3)]
    assert table(card_of(page, nothing)) == [(n, {"reps": "", "kg": ""}, False) for n in (1, 2, 3)]
    # the adjusted weight (21 kg) as an input's value: a bare "21" is also an
    # hour or a day the page prints (the termin's "21:24": the suite's run of
    # 26.11.2026 at 22:24 failed on it)
    for word in ("Prošli put", "pl-next", "malo više", 'value="21"'):
        assert word not in page.split("<main")[1].split('id="dodaj"')[0], word
    assert db.next_load(ivan, eid) is None and db.next_loads(ivan, [eid]) == {}


def test_its_saved_sets_count_for_the_history_and_the_maxes_at_once():
    """Rule 6: a gym training's saved sets are in "Procijenjeni maksimumi"
    and "Povijest vježbe" as soon as they are saved, no osvrt needed:
    source "dvorana", where the training's title and time ("Snaga · 18:00"),
    or "Trening izvan termina"; an exercise deleted from the library since
    stays in both under its name (db.gone_key, a negative key the history's
    ?vjezba= takes)."""
    ivan = make_user("ivan@test.local")
    eid = db.create_exercise("Goblet čučanj")
    start = (now() - timedelta(hours=2)).replace(second=0, microsecond=0)
    at = f"{start.astimezone(config.TZ):%H:%M}"
    tid = db.gym_training_for(ivan, termin(ivan, start, title="Snaga"))
    iid = db.add_gym_item(tid, ivan, eid, "trening", 3, 6, kg=90)
    db.save_gym_done(iid, ivan, [{"reps": 6, "kg": 90.0}, {"reps": 5, "kg": 90.0}])
    [m] = db.estimated_maxes(ivan)
    assert (m.exercise_id, m.name, m.value_text, m.set_text, m.source_text) == (eid, "Goblet čučanj", "108 kg",
                                                                               "90 kg × 6", "dvorana")
    [h] = db.exercise_history(ivan, eid)
    assert (h.on, h.source_text, h.where, h.sets) == (start.astimezone(config.TZ).date(), "dvorana", f"Snaga · {at}",
                                                      ("6 × 90 kg", "5 × 90 kg"))
    out = db.add_gym_outside(ivan, date(2026, 1, 5))
    db.save_gym_done(db.add_gym_item(out, ivan, eid, "trening"), ivan, [{"reps": 3, "kg": 100.0}])
    assert [(h.on, h.where) for h in db.exercise_history(ivan, eid)] == [
        (start.astimezone(config.TZ).date(), f"Snaga · {at}"), (date(2026, 1, 5), "Trening izvan termina")]
    assert [(e.exercise_id, e.times) for e in db.logged_exercises(ivan)] == [(eid, 2)]
    assert db.estimated_maxes(ivan)[0].value_text == "110 kg"
    ci = client_for("ivan@test.local")
    page = ci.get(f"/karton?vjezba={eid}").text
    assert f"Snaga · {at}" in page and "Trening izvan termina" in page and "110 kg" in page
    db.delete_exercise(eid)
    key = db.gone_key("Goblet čučanj")
    assert key < 0 and key == db.gone_key("goblet ČUČANJ")
    [m] = db.estimated_maxes(ivan)
    assert (m.exercise_id, m.name, m.value_text) == (key, "Goblet čučanj", "110 kg")
    assert [h.where for h in db.exercise_history(ivan, key)] == [f"Snaga · {at}", "Trening izvan termina"]
    page = ci.get(f"/karton?vjezba={key}").text
    assert f"Snaga · {at}" in page and "Ta vježba nije u ovom kartonu." not in page


MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64


def test_media_shows_the_clip_of_an_exercise_in_his_own_gym_training():
    """Rule 7: a member with no online plan fetches the clip of an exercise
    in one of HIS gym trainings ("Kako se izvodi" on its card, preload
    none); another member does not, nor he once it is out of his
    trainings."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    eid = db.create_exercise("Goblet čučanj")
    name = f"vjezba-{eid}-0123456789abcdef.mp4"
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    (config.MEDIA_DIR / name).write_bytes(MP4)
    db.set_exercise_video(eid, name)
    ci, ca = client_for("ivan@test.local"), client_for("ana@test.local")
    assert ci.get(f"/media/{name}").status_code == 403
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    iid = db.add_gym_item(tid, ivan, eid, "trening")
    r = ci.get(f"/media/{name}")
    assert r.status_code == 200 and r.content == MP4
    assert ca.get(f"/media/{name}").status_code == 403
    assert f'<video src="/media/{name}" controls playsinline preload="none"></video>' in ci.get(f"/karton/trening/{tid}").text
    ci.post(f"/karton/trening/{tid}/stavke/{iid}/obrisi")
    assert ci.get(f"/media/{name}").status_code == 403


def test_a_termin_is_owed_while_its_trainings_window_is_open():
    """Rule 8 (db.pending_feedback, the login's prompt): a booked termin is
    owed once it has ended, while its training's window is open, until its
    training's osvrt is saved; one begun but not finished is owed still; not
    one not ended yet, past its window, canceled by the trainer, or marked
    "Nisam bio/la". The prompt leads to the training."""
    ivan = make_user("ivan@test.local")
    owed = termin(ivan, now() - timedelta(hours=2))
    termin(ivan, now() - timedelta(minutes=10))                            # not ended yet
    termin(ivan, now() - timedelta(days=2, hours=1))                        # past its window
    canceled = termin(ivan, now() - timedelta(hours=3))
    db.set_session_canceled(canceled, True)
    absent = termin(ivan, now() - timedelta(hours=4))
    db.mark_session_absent(ivan, absent)
    finished = termin(ivan, now() - timedelta(hours=5))
    db.finish_gym_training(db.gym_training_for(ivan, finished), ivan, 7, None, "")
    begun = termin(ivan, now() - timedelta(hours=6))
    db.add_gym_item(db.gym_training_for(ivan, begun), ivan, db.create_exercise("Plank"), "trening")
    assert [x.id for x in db.pending_feedback(ivan)] == [owed, begun]
    ci = client_for("ivan@test.local")
    assert f'href="/karton/termin/{owed}/trening" autofocus' in ci.get("/raspored").text


# ---------- the karton, the raspored, a roster ----------

def test_the_diary_lists_each_training_in_its_state():
    """The karton's diary: a termin's training that holds anything on its
    termin's row (its title the kicker, the day, date and time, napor and
    osjećaj, the comment, "2 vježbe", "Serije": each exercise what was
    given and what was done, "odrađeno —" for nothing; "Otvori trening"
    while the member may write it); a booked termin with none inside its
    window "Trening još nije upisan." with "Upiši trening" and "Nisam
    bio/la", after it "Trening nije upisan." with "Nisam bio/la" alone; a
    training opened and left empty its termin's row; one outside a termin a
    row of its own ("Trening izvan termina", no time, "Otvori trening"
    always); an old TrainingLog row as it was. Newest first. The trainer's
    view the same rows with no button; staff acting as the member "Upiši
    trening" past the window too."""
    ivan = make_user("ivan@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    ex = library("Goblet čučanj", "Plank")
    y = (now() - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    done_sid = termin(ivan, y, title="Snaga")
    tid = db.gym_training_for(ivan, done_sid, staff=True)
    a = db.add_gym_item(tid, ivan, ex["Goblet čučanj"], "trening", 3, 10, kg=20, staff=True)
    db.add_gym_item(tid, ivan, ex["Plank"], "trening", staff=True)
    db.save_gym_done(a, ivan, [{"reps": 10, "kg": 20.0}, {"reps": 10, "kg": 20.0}, {"reps": 8, "kg": 20.0}], effort=8,
                     staff=True)
    db.finish_gym_training(tid, ivan, 7, "dobro", "Zadnja serija teška.", staff=True)
    fresh = termin(ivan, now() - timedelta(hours=2))
    empty_sid = termin(ivan, now() - timedelta(hours=3))
    empty = db.gym_training_for(ivan, empty_sid)
    stale = termin(ivan, now() - timedelta(days=4))
    out = db.add_gym_outside(ivan, config.today() - timedelta(days=2))
    db.add_gym_item(out, ivan, ex["Plank"], "trening", 2, seconds=30)
    with db.session_scope() as s:
        old = TrainingLog(user_id=ivan, session_id=None, date=config.today() - timedelta(days=10), effort=5, note="Staro.",
                          sets=json.dumps([{"exercise_id": ex["Plank"], "name": "Plank", "sets": [{"reps": 1, "kg": 0.0}]}]))
        s.add(old)
        s.flush()
        old_id = old.id

    def shown_(html: str) -> str:
        return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()

    def row(page: str, rid: str) -> str:
        return page.split(f'id="{rid}"')[1].split('<div class="log-entry')[0]

    page = client_for("ivan@test.local").get("/karton").text
    diary = page.split('<h2 id="osvrti">')[1]
    order = re.findall(r'<div class="log-entry[^"]*" id="([a-z]+-\d+)"', diary)
    assert order == [f"s-{fresh}", f"s-{empty_sid}", f"gt-{tid}", f"gt-{out}", f"s-{stale}", f"log-{old_id}"]
    g = row(diary, f"gt-{tid}")
    short = ("pon", "uto", "sri", "čet", "pet", "sub", "ned")[y.weekday()]
    assert ('<div class="le-kicker">Snaga</div>' in g
            and f'<span class="when">{short} {y:%-d.%-m.%Y.} · 18:00</span>' in g
            and '<span class="rpe">napor 7/10</span>' in g and '<span class="rpe feel ">Dobro</span>' in g
            and f'<a class="act" href="/karton/trening/{tid}"><span class="t">Otvori trening</span></a>' in g
            and "<p>Zadnja serija teška.</p>" in g and '<div class="hint le-sub le-ex">2 vježbe</div>' in g)
    assert ("Goblet čučanj: zadano 3 × 10 · 20 kg — odrađeno 10 × 20 kg · 10 × 20 kg · 8 × 20 kg · težina 8/10"
            in shown_(g) and "Plank: odrađeno —" in shown_(g))
    f = row(diary, f"s-{fresh}")
    assert (f'<a class="act" href="/karton/termin/{fresh}/trening"><span class="t">Upiši trening</span></a>' in f
            and f'action="/karton/absent/{fresh}"' in f
            and '<div class="hint le-state"><span class="t">Trening još nije upisan.</span></div>' in f)
    assert f'class="log-entry fresh" id="s-{fresh}"' in diary
    e = row(diary, f"s-{empty_sid}")
    assert f'href="/karton/termin/{empty_sid}/trening"' in e and f'id="gt-{empty}"' not in diary
    st = row(diary, f"s-{stale}")
    assert (f"/karton/termin/{stale}/trening" not in st and f'action="/karton/absent/{stale}"' in st
            and '<div class="hint le-state"><span class="t">Trening nije upisan.</span></div>' in st)
    o = row(diary, f"gt-{out}")
    assert ('<div class="le-kicker"><span class="t">Trening izvan termina</span></div>' in o
            and " · " not in o.split('<span class="when">')[1].split("</span>")[0]
            and f'href="/karton/trening/{out}"' in o and "Plank: zadano 2 × 30 s — odrađeno —" in shown_(o)
            and '<div class="hint le-sub le-ex">1 vježba</div>' in o)
    lg = row(diary, f"log-{old_id}")
    assert "<p>Staro.</p>" in lg and f'action="/karton/log/{old_id}/edit"' in lg and "Plank:" in shown_(lg)
    cs = client_for("coach@test.local")
    make_user("trener@test.local", plans=())                    # the owner, staff: the trainer's view is his too
    assert cs.get(f"/karton/{ivan}").status_code == 200        # the trainer's again: the Karton tab's search leads there (27.11.2026)
    view = client_for("trener@test.local").get(f"/karton/{ivan}").text.split('<h2 id="osvrti">')[1]
    assert re.findall(r'<div class="log-entry[^"]*" id="([a-z]+-\d+)"', view) == order
    assert "/karton/trening/" not in view and "/karton/termin/" not in view and "/karton/absent/" not in view
    assert "Trening još nije upisan." in view and "Trening nije upisan." in view
    assert "Goblet čučanj: zadano 3 × 10 · 20 kg — odrađeno 10 × 20 kg" in shown_(view)
    assert cs.post(f"/kao/{ivan}", follow_redirects=False).status_code == 303
    acting = cs.get("/karton").text.split('<h2 id="osvrti">')[1]
    assert f'href="/karton/termin/{stale}/trening"' in acting and f'href="/karton/trening/{tid}"' in acting


def test_the_way_in_is_on_the_termini_and_the_raspored_while_the_window_is_open():
    """"Nadolazeći termini": a termin whose training is open carries
    "Upiši trening →" (none further ahead, none canceled, none on the
    trainer's view), and under the list, once, "Trening upisuješ od 4 h
    prije termina do kraja idućeg dana."; the raspored's "Tvoj sljedeći
    termin" carries the same link while it is open."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    soon = termin(ivan, now() + timedelta(hours=3), title="Snaga")
    later = termin(ivan, now() + timedelta(hours=6), title="Mobilnost")
    with db.session_scope() as s:
        s.add(Booking(user_id=ana, session_id=later))
    link = '<a class="act cal-go" href="/karton/termin/{}/trening"><span class="t">Upiši trening →</span></a>'
    hint = ('<p class="hint gym-when"><span class="t">Trening upisuješ od</span> 4 <span class="t">h prije termina do '
            'kraja idućeg dana.</span></p>')

    def termini(page: str) -> str:
        return page.split('<section class="card termini"')[1].split("</section>")[0]

    ci = client_for("ivan@test.local")
    mine = termini(ci.get("/karton").text)
    assert link.format(soon) in mine and f"/karton/termin/{later}/" not in mine and mine.count(hint) == 1
    card = ci.get("/raspored").text.split('<section class="card next-termin"')[1].split("</section>")[0]
    assert f'<a class="act nt-gym" href="/karton/termin/{soon}/trening"><span class="t">Upiši trening →</span></a>' in card
    ca = client_for("ana@test.local")
    assert "/karton/termin/" not in termini(ca.get("/karton").text)
    assert "nt-gym" not in ca.get("/raspored").text.split('<section class="card next-termin"')[1].split("</section>")[0]
    make_user("trener@test.local", plans=())                    # the owner, staff: the trainer's view is his too
    assert "/karton/termin/" not in termini(client_for("trener@test.local").get(f"/karton/{ivan}").text)
    db.set_session_canceled(soon, True)
    assert "/karton/termin/" not in termini(ci.get("/karton").text)
    assert "nt-gym" not in ci.get("/raspored").text.split('<section class="card next-termin"')[1].split("</section>")[0]


def test_a_rosters_kao_clan_lands_on_his_training_and_every_write_there_is_recorded():
    """A termin's roster's "Kao član →" goes into the member's account at
    his training of that termin (kamo=/karton/termin/<id>/trening, rule 2
    for staff: made before its window too); a tick there carries the page's
    identity (X-QMT-Kao, base.html's) and is a row of the acting record, as
    every write is; one without it runs nothing. A termin canceled since
    says rule 2's sentence on his karton."""
    ivan = make_user("ivan@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    sid = termin(ivan, now() + timedelta(days=1))
    cs = client_for("coach@test.local")
    roster = cs.get(f"/admin/session/{sid}").text
    assert f'<input type="hidden" name="kamo" value="/karton/termin/{sid}/trening">' in roster
    r = cs.post(f"/kao/{ivan}", data={"natrag": f"/admin/session/{sid}", "kamo": f"/karton/termin/{sid}/trening"},
                follow_redirects=False)
    assert location(r) == f"/karton/termin/{sid}/trening"
    r = cs.get(location(r), follow_redirects=False)
    [t] = db.gym_trainings(ivan)
    assert location(r) == f"/karton/trening/{t.id}"
    page = cs.get(location(r)).text
    assert f'data-kao="{ivan}"' in page and "Za člana je upis zatvoren; uređuješ kao trener." in page
    iid = db.add_gym_item(t.id, ivan, db.create_exercise("Plank"), "trening", 2, seconds=30, staff=True)
    r = tick(cs, t.id, iid, "seconds", {"sec": 30})                               # no identity: runs nothing
    assert r.status_code == 303 and done_of(iid) == []
    r = tick(cs, t.id, iid, "seconds", {"sec": 30}, headers={**JSON, "X-QMT-Kao": str(ivan)})
    assert r.json() == {"ok": True, "error": "", "mark": "1/2"} and done_of(iid) == [{"seconds": 30}]
    rows, _ = db.acting_log()
    assert (rows[0].method, rows[0].path, rows[0].status, rows[0].member_id) == (
        "POST", f"/karton/trening/{t.id}/stavke/{iid}/odradeno", 200, ivan)
    db.set_session_canceled(sid, True)
    other = termin(ivan, now() + timedelta(days=2))
    db.set_session_canceled(other, True)
    r = cs.get(f"/karton/termin/{other}/trening", follow_redirects=False)
    assert location(r) == "/karton?error=Termin je otkazan."


# ---------- part B: a part's name and circuit, the rounds, the templates, a slot ----------

GYM_CHANGED = "Trening se u međuvremenu promijenio — provjeri vježbu i spremi ponovno."


def dvoranski(title: str = "Predložak — snaga", level: str | None = "srednja", day_title: str = "") -> int:
    """A dvoranski programme with one training, its day's id (the template
    a gym training is made from)."""
    day = db.add_day(db.create_program(title, None, level, "cijelo", "dvorana"))
    if day_title:
        db.update_day(day, day_title, None, "")
    return day


def part_of(page: str, key: str) -> str:
    """A part's section of the page (its head, its cards, its rounds)."""
    return page.split(f'<section class="gt-part" aria-labelledby="dio-{key}">')[1].split("</section>")[0]


def rnd(c: TestClient, tid: int, key: str, n: int, by_item: dict, effort: str = "", stavke=None):
    """A round's save as its block's form posts it: each exercise's inputs
    (reps_<id>, kg_<id>, sec_<id>), the exercises it was drawn for."""
    data = {"stavke": ",".join(str(i) for i in (stavke if stavke is not None else by_item)), "effort": effort}
    for iid, values in by_item.items():
        data.update({f"{k}_{iid}": str(v) for k, v in values.items()})
    return c.post(f"/karton/trening/{tid}/dio/{key}/krug/{n}", data=data, follow_redirects=False)


def test_the_parts_migration_makes_its_table_and_takes_it_away():
    """36d6e2c97de7 (part B), run on qmt_test as before it (no parts
    table): gym_training_parts as the model has it, empty, its two CHECKs
    (rounds 2–20, a rest after a round 0–3600) and its key CASCADE from the
    training. Downgrade drops it, the trainings and their items as they
    were (a circuit's sets with their rounds); a second upgrade makes it
    again, empty."""
    mig = _migration("36d6e2c97de7_gym_training_parts.py")
    assert (mig.revision, mig.down_revision) == ("36d6e2c97de7", "c4e1b7f9a2d6")
    ivan = make_user("ivan@test.local")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=2)))
    iid = db.add_gym_item(tid, ivan, db.create_exercise("Plank"), "trening", seconds=30)
    with db.engine.begin() as conn:
        conn.execute(sa_text("DROP TABLE gym_training_parts"))
    _run(mig.upgrade)
    assert "gym_training_parts" in sa_inspect(db.engine).get_table_names()
    assert _schema_diffs({"gym_training_parts"}) == [] and db.gym_training(tid, ivan).parts == []
    db.set_gym_part(tid, ivan, "trening", "Krug 1", True, 3, 90)
    db.save_gym_round(tid, ivan, "trening", 1, {iid: {"seconds": 30}})
    for bad in ("rounds = 21", "rounds = 1", "rest_seconds = 3601", "rest_seconds = -1"):
        with pytest.raises(Exception, match="ck_gym_training_parts"):
            with db.engine.begin() as conn:
                conn.execute(sa_text(f"UPDATE gym_training_parts SET {bad}"))
    out = db.add_gym_outside(ivan, date(2026, 1, 5))
    db.set_gym_part(out, ivan, "trening_b", "Snaga", False)
    db.delete_gym_training(out, ivan)                                       # its part goes with it (CASCADE)
    with db.engine.connect() as conn:
        assert conn.execute(sa_text("SELECT training_id, section, title, rounds, rest_seconds FROM gym_training_parts")
                            ).all() == [(tid, "trening", "Krug 1", 3, 90)]
    _run(mig.downgrade)
    assert "gym_training_parts" not in sa_inspect(db.engine).get_table_names()
    with db.engine.connect() as conn:                                       # the sets as they were, with their round
        assert json.loads(conn.execute(sa_text("SELECT done FROM gym_training_items WHERE id = :i"), {"i": iid}
                                       ).scalar_one()) == [{"seconds": 30, "round": 1}]
    _run(mig.upgrade)
    assert _schema_diffs({"gym_training_parts"}) == [] and db.gym_training(tid, ivan).parts == []


def test_uredi_dio_names_a_part_and_makes_it_a_circuit():
    """"Uredi dio", beside each part's caption while the page is writable
    (POST …/dio/<key>): a name of its own (one line, 60 characters at most;
    empty: the default back) and "Kružni dio" with Krugova (2–20) and "Odmor
    nakon kruga (s)" (0–3600, empty for none); unticked, a normal part
    whatever the numbers say, the row gone with no name. Back at the part,
    "Spremljeno." under its caption; a refusal there with its form open
    again, nothing changed. The caption and every Dio name the part as
    named, a circuit's caption "· kružno · 3 kruga · odmor 90 s"; its
    exercises' sets stay as they were either way. A part that is none: the
    page's top. Another member's 404; past the window refused, and no
    "Uredi dio" on the page read only."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    ex = library("Goblet čučanj", "Plank")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    a = db.add_gym_item(tid, ivan, ex["Goblet čučanj"], "trening", 3, 10, kg=20, rest_seconds=60)
    db.save_gym_done(a, ivan, [{"reps": 10, "kg": 20.0}])
    ci = client_for("ivan@test.local")

    def save(key="trening", **form):
        return ci.post(f"/karton/trening/{tid}/dio/{key}", data=form, follow_redirects=False)

    def parts():
        return [(p.section, p.title, p.rounds, p.rest_seconds) for p in db.gym_training(tid, ivan).parts]

    page = ci.get(f"/karton/trening/{tid}").text
    head = part_of(page, "trening").split('<div class="gt-cards">')[0]
    assert '<h2 class="dx-cap" id="dio-trening">Glavni dio A</h2>' in head
    assert ('<details class="gt-part-edit">\n  <summary class="act act-quiet"><span class="t">Uredi dio</span></summary>\n'
            f'  <form class="gt-part-form" method="post" action="/karton/trening/{tid}/dio/trening">') in head
    assert [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<label[^>]*>(.*?)</label>", head, re.S)] == [
        "Naziv dijela", "Kružni dio", "Krugova", "Odmor nakon kruga (s)"]
    assert ('name="title" maxlength="60" value="" placeholder="Glavni dio A"' in head and 'value="1"> <span' in head
            and 'name="rounds" inputmode="numeric" min="2" max="20" value="3"' in head
            and 'name="rest" inputmode="numeric" min="0" max="3600" value=""' in head)
    r = save(title="  Krug   1 ", rounds="5")
    assert location(r) == f"/karton/trening/{tid}?dio=trening&ok=Spremljeno.#dio-trening"
    assert parts() == [("trening", "Krug 1", None, None)]                  # unticked: no circuit
    page = ci.get(f"/karton/trening/{tid}?dio=trening&ok=Spremljeno.").text
    assert '<h2 class="dx-cap" id="dio-trening">Krug 1</h2>' in page
    assert '<div class="alert ok" role="status">Spremljeno.</div>' in part_of(page, "trening")
    assert page.count('class="alert ok"') == 1                              # not at the page's top
    for where in (page.split('<form id="dodaj"')[1], card_of(page, a)):    # every Dio names it so
        assert '<option value="trening" selected>Krug 1</option>' in where
    r = save(title="Krug 1", circuit="1", rounds="3", rest="90")
    assert parts() == [("trening", "Krug 1", 3, 90)] and done_of(a) == [{"reps": 10, "kg": 20.0}]
    page = ci.get(f"/karton/trening/{tid}").text
    assert ('<h2 class="dx-cap" id="dio-trening">Krug 1 · <span class="t">kružno</span> · 3 kruga · '
            '<span class="t">odmor</span> 90 s</h2>') in page
    head = part_of(page, "trening").split('<div class="gt-cards">')[0]
    assert ('value="1" checked> <span' in head and 'min="2" max="20" value="3"' in head
            and 'min="0" max="3600" value="90"' in head and 'value="Krug 1" placeholder="Glavni dio A"' in head)
    save(circuit="1", rounds="4")                                           # no name, a circuit: its default and its rounds
    assert parts() == [("trening", "", 4, None)]
    assert '<h2 class="dx-cap" id="dio-trening">Glavni dio A · <span class="t">kružno</span> · 4 kruga</h2>' in ci.get(
        f"/karton/trening/{tid}").text
    save(rounds="4", rest="90")                                             # neither: the row goes
    assert parts() == [] and done_of(a) == [{"reps": 10, "kg": 20.0}]
    save(title="Krug 1", circuit="1", rounds="3", rest="90")
    for form, sentence in (({"title": "x" * 61}, "Najviše 60 znakova."),
                           ({"circuit": "1", "rounds": "1"}, "Neispravan broj."),
                           ({"circuit": "1", "rounds": "21"}, "Neispravan broj."),
                           ({"circuit": "1", "rounds": ""}, "Neispravan broj."),
                           ({"circuit": "1", "rounds": "x"}, "Neispravan broj."),
                           ({"circuit": "1", "rounds": "3", "rest": "3601"}, "Neispravan broj."),
                           ({"circuit": "1", "rounds": "3", "rest": "-1"}, "Neispravan broj.")):
        r = save(**form)
        assert location(r) == f"/karton/trening/{tid}?dio=trening&uredi=1&error={sentence}#dio-trening", form
    assert parts() == [("trening", "Krug 1", 3, 90)]
    page = ci.get(f"/karton/trening/{tid}?dio=trening&uredi=1&error=Neispravan broj.").text
    assert '<details class="gt-part-edit" open>' in part_of(page, "trening")
    assert '<div class="alert" role="alert"><span>Neispravan broj.</span></div>' in part_of(page, "trening")
    assert page.count('<div class="alert" role="alert">') == 1
    assert location(save("kardio", title="X")) == f"/karton/trening/{tid}?error=Odaberi dio treninga."
    assert client_for("ana@test.local").post(f"/karton/trening/{tid}/dio/trening", data={"title": "X"}).status_code == 404
    closed = db.gym_training_for(ivan, termin(ivan, now() - timedelta(days=3)), staff=True)
    db.add_gym_item(closed, ivan, ex["Plank"], "trening", staff=True)
    r = ci.post(f"/karton/trening/{closed}/dio/trening", data={"title": "X"}, follow_redirects=False)
    assert CLOSED in location(r) and db.gym_training(closed, ivan).parts == []
    assert 'class="gt-part-edit"' not in ci.get(f"/karton/trening/{closed}").text


def test_a_circuits_rounds_are_ticked_a_round_at_a_time():
    """A circuit part: its exercises compact cards (what one round asks, the
    rounds' mark, no set table; "Uredi zadano" without Serije and Pauza,
    which it keeps), then a block per round, "Krug 1" … "Krug 3", the first
    not saved open, each exercise's inputs by its shape, first values the
    round's own, else what was given and the round before's weight; the
    round's rating; ONE button "Krug 1 odrađen". A round saved (POST
    …/dio/<key>/krug/<n>): each exercise with an input its set of the round
    (its round kept), the rating on each, back at the part with the rest
    after a round (?odmor=90: the page starts the rest bar at load), the
    round folded with its ✓; saved again it replaces itself alone, an
    exercise left empty losing its set of that round. Refused there with
    the round open, nothing saved: nothing typed, a bad number or rating, a
    round past its rounds or a page drawn for other exercises (GYM_CHANGED).
    A tick posted to a circuit's exercise is refused. Every round saved:
    "✓". Switched off, every set stays, the cards' tables tick them."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank", "Mrtvi kukac", "Sklekovi")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    g = db.add_gym_item(tid, ivan, ex["Goblet čučanj"], "trening", 3, 10, kg=16, rest_seconds=60)
    p = db.add_gym_item(tid, ivan, ex["Plank"], "trening", seconds=30)
    m = db.add_gym_item(tid, ivan, ex["Mrtvi kukac"], "trening", reps=5, seconds=30)
    db.add_gym_item(tid, ivan, ex["Sklekovi"], "trening_b", 3, 10)
    db.set_gym_part(tid, ivan, "trening", "Krug 1", True, 3, 90)
    ci = client_for("ivan@test.local")
    page = ci.get(f"/karton/trening/{tid}").text
    part = part_of(page, "trening")
    cg = card_of(page, g)
    assert f'<details class="card gt-card gt-crow" id="stavka-{g}">' in page
    assert '<span class="gt-planned"><span class="t">Zadano:</span> 10 ponavljanja · 16 kg</span>' in cg
    assert '<span class="gt-mark"></span>' in cg and "gt-log" not in part and "Odmor između serija" not in part
    form = cg.split('<form class="gt-form"')[1].split("</form>")[0]
    assert [re.sub(r"<[^>]+>", "", x) for x in re.findall(r'<label for="gt-\d+-\w+">(.*?)</label>', form)] == [
        "Dio", "Ponavljanja", "Sekunde", "Kilaža (kg)", "Napomena"] and '<input type="hidden" name="circuit" value="1">' in form
    assert re.findall(r'<details class="card gt-round" id="krug-trening-(\d)"( open)?>', page) == [
        ("1", " open"), ("2", ""), ("3", "")]
    one = part.split('id="krug-trening-1"')[1].split('id="krug-trening-2"')[0]
    assert '<span class="gt-name">Krug 1</span>' in one and f'name="stavke" value="{g},{p},{m}"' in one
    assert (f'name="reps_{g}" value="10"' in one and f'name="kg_{g}" value="16"' in one and f'name="sec_{p}" value="30"' in one
            and f'name="reps_{m}" value="5"' in one and f'name="sec_{m}" value="30"' in one and f'kg_{p}' not in one)
    assert '<p class="pl-rate-h" id="gt-rate-trening-1"><span class="t">Koliko je bio težak ovaj krug?</span>' in one
    assert one.count('name="effort"') == 10 and " checked" not in one
    assert '<button type="submit" class="btn btn-sm"><span>Krug 1 <span class="t">odrađen</span></span></button>' in one
    assert '<div class="gt">' in page                                       # no rest to count down

    r = rnd(ci, tid, "trening", 1, {g: {"reps": 10, "kg": "16"}, p: {"sec": 30}, m: {"reps": 5, "sec": 30}}, effort="7")
    assert location(r) == f"/karton/trening/{tid}?dio=trening&odmor=90#dio-trening"
    assert done_of(g) == [{"reps": 10, "kg": 16.0, "round": 1}] and done_of(p) == [{"seconds": 30, "round": 1}]
    assert done_of(m) == [{"reps": 5, "seconds": 30, "round": 1}]
    page = ci.get(f"/karton/trening/{tid}?dio=trening&odmor=90").text
    assert '<div class="gt" data-odmor="90">' in page and 'id="plRest"' in page
    assert re.findall(r'<details class="card gt-round" id="krug-trening-(\d)"( open)?>', page) == [
        ("1", ""), ("2", " open"), ("3", "")]
    assert ('<span class="gt-mark ok" role="img" aria-label="spremljeno">✓</span>'
            in page.split('id="krug-trening-1"')[1].split("</summary>")[0])
    assert '<span class="gt-mark" role="img" aria-label="1/3 kruga odrađena">1/3</span>' in card_of(page, g)
    assert '<div class="gt">' in ci.get(f"/karton/trening/{tid}?odmor=9999").text       # out of range: ignored
    with db.session_scope() as s:
        assert [s.get(GymTrainingItem, x).effort for x in (g, p, m)] == [7, 7, 7]
    rnd(ci, tid, "trening", 2, {g: {"reps": 8, "kg": "18"}, p: {"sec": ""}, m: {"reps": "", "sec": ""}})
    assert done_of(g)[1] == {"reps": 8, "kg": 18.0, "round": 2} and len(done_of(p)) == 1
    with db.session_scope() as s:                                          # an unrated round: the ratings stay
        assert s.get(GymTrainingItem, g).effort == 7
    three = ci.get(f"/karton/trening/{tid}").text.split('id="krug-trening-3"')[1].split("</details>")[0]
    assert f'name="reps_{g}" value="10"' in three and f'name="kg_{g}" value="18"' in three   # the round before's weight
    # round 1 again: it replaces itself alone; one left empty loses its set of that round
    rnd(ci, tid, "trening", 1, {g: {"reps": 9, "kg": "16"}, p: {"sec": ""}, m: {"reps": 5, "sec": 30}}, effort="9")
    assert done_of(g) == [{"reps": 9, "kg": 16.0, "round": 1}, {"reps": 8, "kg": 18.0, "round": 2}]
    assert done_of(p) == []
    with db.session_scope() as s:
        assert (s.get(GymTrainingItem, p).effort, s.get(GymTrainingItem, p).done_at) == (None, None)
        assert (s.get(GymTrainingItem, g).effort, s.get(GymTrainingItem, m).effort) == (9, 9)
    before = [done_of(x) for x in (g, p, m)]
    for n, by_item, effort, stavke, sentence in (
            (2, {g: {"reps": "", "kg": ""}, p: {"sec": ""}, m: {"reps": "", "sec": ""}}, "", None, "Upiši bar jednu vježbu."),
            (2, {g: {"reps": "abc", "kg": "16"}, p: {"sec": ""}, m: {"reps": "", "sec": ""}}, "", None, "Neispravan broj."),
            (2, {g: {"reps": 10, "kg": "16,3"}, p: {"sec": ""}, m: {"reps": "", "sec": ""}}, "", None, "Neispravan broj."),
            (2, {g: {"reps": 10, "kg": "16"}, p: {"sec": ""}, m: {"reps": "", "sec": ""}}, "11", None, "Neispravan broj."),
            (4, {g: {"reps": 10, "kg": "16"}, p: {"sec": ""}, m: {"reps": "", "sec": ""}}, "", None, GYM_CHANGED),
            (2, {g: {"reps": 10, "kg": "16"}, p: {"sec": ""}}, "", [g, p], GYM_CHANGED)):
        r = rnd(ci, tid, "trening", n, by_item, effort, stavke)
        assert location(r) == f"/karton/trening/{tid}?dio=trening&krug={n}&error={sentence}#krug-trening-{n}", sentence
    assert [done_of(x) for x in (g, p, m)] == before
    page = ci.get(f"/karton/trening/{tid}?dio=trening&krug=2&error=Upiši bar jednu vježbu.").text
    two = page.split('id="krug-trening-2"')[1].split("</details>")[0]
    assert page.count('<div class="alert" role="alert">') == 1
    assert ('<details class="card gt-round" id="krug-trening-2" open>' in page
            and '<div class="alert" role="alert"><span>Upiši bar jednu vježbu.</span></div>' in two)
    r = tick(ci, tid, g, "reps,kg", {"reps": 10, "kg": 20})                 # a circuit's exercise takes no tick
    assert (r.status_code, r.json()["error"]) == (400, GYM_CHANGED) and done_of(g) == before[0]
    for n in (2, 3):
        rnd(ci, tid, "trening", n, {g: {"reps": 10, "kg": "16"}, p: {"sec": 30}, m: {"reps": 5, "sec": 30}})
    page = ci.get(f"/karton/trening/{tid}").text
    assert '<span class="gt-mark ok" role="img" aria-label="odrađeno">✓</span>' in card_of(page, g)
    assert '<span class="gt-mark" role="img" aria-label="2/3 kruga odrađena">2/3</span>' in card_of(page, p)
    assert not re.search(r'id="krug-trening-\d" open', page)               # every round saved: all folded
    [line] = [x for x in db.gym_training(tid, ivan).lines() if x[0] == "Goblet čučanj"]
    assert line == ("Goblet čučanj", "zadano 10 ponavljanja · 16 kg — odrađeno",
                    ["9 × 16 kg", "10 × 16 kg", "10 × 16 kg", "težina 9/10"])
    # "Uredi zadano" in a circuit part: no Serije, no Pauza, which it keeps
    r = ci.post(f"/karton/trening/{tid}/stavke/{g}", data={"section": "trening", "reps": "12", "kg": "16", "circuit": "1"},
                follow_redirects=False)
    assert location(r) == f"/karton/trening/{tid}?stavka={g}&ok=Spremljeno.#stavka-{g}"
    with db.session_scope() as s:
        it = s.get(GymTrainingItem, g)
        assert (it.sets, it.reps, it.rest_seconds) == (3, 12, 60)
    # switched off: every set stays, and the card's table ticks them all
    db.set_gym_part(tid, ivan, "trening", "Krug 1", False)
    page = ci.get(f"/karton/trening/{tid}").text
    assert 'class="card gt-round"' not in page and done_of(g) == [{"reps": 9, "kg": 16.0, "round": 1}, {"reps": 10, "kg": 16.0, "round": 2},
                                                    {"reps": 10, "kg": 16.0, "round": 3}]
    assert [ticked for _, _, ticked in table(card_of(page, g))] == [True, True, True]
    db.set_gym_part(tid, ivan, "trening", "", True, 2, None)               # a circuit with no rest: no odmor
    r = rnd(ci, tid, "trening", 1, {g: {"reps": 10, "kg": "16"}, p: {"sec": 30}, m: {"reps": 5, "sec": 30}})
    assert location(r) == f"/karton/trening/{tid}?dio=trening#dio-trening"


def test_two_rounds_at_once_keep_both():
    """Eight rounds of one circuit part saved at the same moment (eight
    threads, a round each; save_gym_round takes the training's row FOR
    UPDATE), twice: every exercise holds a set of every round, none lost,
    sorted by round."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    a = db.add_gym_item(tid, ivan, ex["Goblet čučanj"], "trening", reps=10, kg=16)
    b = db.add_gym_item(tid, ivan, ex["Plank"], "trening", seconds=30)
    db.set_gym_part(tid, ivan, "trening", "", True, 8, 60)
    for times in (1, 2):
        errors, gate = [], threading.Barrier(8)

        def save(n, times=times):
            try:
                gate.wait()
                db.save_gym_round(tid, ivan, "trening", n, {a: {"reps": n + times, "kg": 16.0}, b: {"seconds": 30 + n}})
            except Exception as e:                                          # reported below
                errors.append(repr(e))

        threads = [threading.Thread(target=save, args=(n,)) for n in range(1, 9)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert not errors
        assert done_of(a) == [{"reps": n + times, "kg": 16.0, "round": n} for n in range(1, 9)]
        assert done_of(b) == [{"seconds": 30 + n, "round": n} for n in range(1, 9)]


def test_a_template_is_copied_into_an_empty_training():
    """While a training holds no row, "Odaberi gotov trening" lists every
    dvoranski programme's training that holds a row ("<programme> · Trening
    N · <naslov>", muted its razina and "2 vježbe · 2 prazna mjesta"; not an
    online programme's, not an empty one; none: no control). Chosen (POST
    …/predlozak): its parts' names and circuits and its rows, exercises and
    slots alike, in its order, with their numbers and notes (a day's rest
    after an exercise not carried); the template unchanged. Refused on a
    training that holds a row ("Trening već ima vježbe — isprazni ga pa
    odaberi predložak."), for a day that is none or no dvoranski
    programme's ("Odaberi predložak s popisa."); emptied, another template
    replaces the parts too. Read only: no list, a post refused."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank", "Sklekovi")
    day = dvoranski(day_title="Cijelo tijelo")
    db.set_part_name(day, "trening", "Krug 1")
    db.set_circuit(day, "trening", 3, 90)
    db.set_part_name(day, "istezanje", "Mobilnost")
    db.add_day_slot(day, "zagrijavanje", "mobilnost", reps=10)
    x = db.add_day_item(day, ex["Goblet čučanj"], "trening", 3, 10, kg=16)
    db.update_day_item(x, "trening", 3, 10, None, 60, 90, "Polako.", kg=16)    # 90 s after it: not carried
    db.add_day_slot(day, "trening", "potisak", reps=12)
    db.add_day_item(day, ex["Plank"], "istezanje", 2, None, 30)
    pid = db.get_day(day).program_id
    db.add_day(pid)                                                         # Trening 2, empty: not offered
    online_day = db.add_day(db.create_program("Online", None, "srednja", "cijelo"))
    db.add_day_item(online_day, ex["Sklekovi"], "trening")
    template_before = [(it.section, it.position, it.exercise_id, it.hint, it.note) for it in db.get_day(day).items]
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    ci = client_for("ivan@test.local")
    page = ci.get(f"/karton/trening/{tid}").text
    tpl = page.split('<details class="gt-tpl">')[1].split("</details>")[0]
    assert '<summary class="act"><span class="t">Odaberi gotov trening</span></summary>' in tpl
    assert re.findall(r'<input type="hidden" name="dan" value="(\d+)">\s*<button type="submit" class="gt-tpl-row">'
                      r'<span class="gt-tpl-txt"><span class="gt-tpl-name">([^<]*)</span><span class="gt-tpl-facts">([^<]*)'
                      r'</span></span><span class="gt-tpl-go" aria-hidden="true">→</span></button>', tpl) == [
        (str(day), "Predložak — snaga · Trening 1 · Cijelo tijelo", "Srednja razina · 2 vježbe · 2 prazna mjesta")]
    assert f'<form method="post" action="/karton/trening/{tid}/predlozak">' in tpl
    r = ci.post(f"/karton/trening/{tid}/predlozak", data={"dan": str(day)}, follow_redirects=False)
    assert location(r) == f"/karton/trening/{tid}?ok=Predložak je dodan."
    t = db.gym_training(tid, ivan)
    assert [(it.section, it.position, it.exercise_id, it.exercise_name, it.hint, it.sets, it.reps, it.seconds, it.kg,
             it.rest_seconds, it.note, it.done_sets) for it in t.items] == [
        ("zagrijavanje", 1, None, "", "mobilnost", None, 10, None, None, None, "", []),
        ("trening", 2, ex["Goblet čučanj"], "Goblet čučanj", "", 3, 10, None, Decimal("16.0"), 60, "Polako.", []),
        ("trening", 3, None, "", "potisak", None, 12, None, None, None, "", []),
        ("istezanje", 4, ex["Plank"], "Plank", "", 2, None, 30, None, None, "", [])]
    assert sorted((p.section, p.title, p.rounds, p.rest_seconds) for p in t.parts) == [
        ("istezanje", "Mobilnost", None, None), ("trening", "Krug 1", 3, 90)]
    assert [(it.section, it.position, it.exercise_id, it.hint, it.note) for it in db.get_day(day).items] == template_before
    page = ci.get(f"/karton/trening/{tid}?ok=Predložak je dodan.").text
    assert re.findall(r'<h2 class="dx-cap" id="dio-(\w+)">([^<]*)', page) == [
        ("zagrijavanje", "Zagrijavanje"), ("trening", "Krug 1 · "), ("istezanje", "Mobilnost")]
    assert 'class="gt-tpl"' not in page and 'class="hint gt-empty"' not in page
    assert '<div class="alert ok" role="status">Predložak je dodan.</div>' in page.split('class="gt-when"')[0]
    assert t.count_text == "2 vježbe"                                       # a slot is no exercise
    # refused on a training that holds a row; a day that is none
    r = ci.post(f"/karton/trening/{tid}/predlozak", data={"dan": str(day)}, follow_redirects=False)
    assert location(r) == (f"/karton/trening/{tid}?predlozak=1&error=Trening već ima vježbe — isprazni ga pa odaberi "
                           "predložak.")
    assert len(db.gym_training(tid, ivan).items) == 4
    out = db.add_gym_outside(ivan, config.today())
    for dan in (str(online_day), "abc", "", "999999"):
        r = ci.post(f"/karton/trening/{out}/predlozak", data={"dan": dan}, follow_redirects=False)
        assert location(r) == f"/karton/trening/{out}?predlozak=1&error=Odaberi predložak s popisa.", dan
    assert db.gym_training(out, ivan).items == []
    page = ci.get(f"/karton/trening/{out}?predlozak=1&error=Odaberi predložak s popisa.").text   # its word in the list
    assert ('<details class="gt-tpl" open>' in page and page.count('<div class="alert" role="alert">') == 1
            and '<div class="alert" role="alert"><span>Odaberi predložak s popisa.</span></div>'
            in page.split('<details class="gt-tpl" open>')[1].split("</details>")[0])
    assert '<details class="gt-date">' in page                              # not the date's word: its form stays shut
    # emptied, another template: its parts in place of the first's
    plain = dvoranski("Predložak — lagano", None)
    db.add_day_item(plain, ex["Sklekovi"], "trening_b", 2, 8)
    assert db.gym_training(tid, ivan).parts != []                           # the first template's names and circuits
    ci.post(f"/karton/trening/{tid}/isprazni")
    # emptied, the parts are their defaults again, normal ones: an exercise
    # added by hand meets no "· kružno" of the template that went (Fable's
    # review, 26.11.2026)
    assert db.gym_training(tid, ivan).parts == []
    page = ci.get(f"/karton/trening/{tid}").text
    names = re.findall(r'<span class="gt-tpl-name">([^<]*)</span>(?:<span class="gt-tpl-facts">([^<]*)</span>)?', page)
    assert names == [("Predložak — lagano · Trening 1", "1 vježba"), ("Predložak — snaga · Trening 1 · Cijelo tijelo",
                                                                     "Srednja razina · 2 vježbe · 2 prazna mjesta")]
    ci.post(f"/karton/trening/{tid}/predlozak", data={"dan": str(plain)})
    t = db.gym_training(tid, ivan)
    assert [(it.section, it.exercise_name, it.sets, it.reps) for it in t.items] == [("trening_b", "Sklekovi", 2, 8)]
    assert t.parts == []
    # read only: no list, refused
    closed = db.gym_training_for(ivan, termin(ivan, now() - timedelta(days=3)), staff=True)
    assert 'class="gt-tpl"' not in ci.get(f"/karton/trening/{closed}").text
    r = ci.post(f"/karton/trening/{closed}/predlozak", data={"dan": str(day)}, follow_redirects=False)
    assert CLOSED in location(r) and db.gym_training(closed, ivan).items == []
    # no template at all: no control
    with db.session_scope() as s:
        s.execute(sa_text("DELETE FROM programs WHERE venue = 'dvorana'"))
    assert 'class="gt-tpl"' not in ci.get(f"/karton/trening/{out}").text


def test_a_slots_card_is_filled_from_the_library():
    """A slot (a template's empty place): its card "Prazno mjesto · potisak"
    muted with what was given (a circuit's: what one round asks), dashed;
    open, its note, the library's combobox (the script's: its form rendered
    hidden, the hint on it) and "Odaberi", then "Ukloni" (it holds nothing:
    no confirm). In no count, no diary line, no round. "Odaberi" (POST
    …/stavke/<id>/vjezba): the exercise in it, its name snapshotted, its
    place, numbers, note and hint as they were, an ordinary card back open
    with the focus in its first input (?dodano=1); in a circuit part it
    joins the rounds. Refused at its card: nothing picked, an exercise not
    in the library, a row that is no slot."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Sklekovi", "Plank")
    day = dvoranski()
    db.set_circuit(day, "trening_b", 2, 60)
    s1 = db.add_day_slot(day, "trening", "potisak", reps=12)
    db.update_day_item(s1, "trening", None, 12, None, None, None, "Lagano.")
    db.add_day_item(day, ex["Goblet čučanj"], "trening_b", reps=10, kg=16)
    db.add_day_slot(day, "trening_b", "core", seconds=30)
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    db.gym_from_template(tid, ivan, day)
    slot, goblet, core = (it.id for it in db.gym_training(tid, ivan).items)
    ci = client_for("ivan@test.local")
    page = ci.get(f"/karton/trening/{tid}").text
    cs = card_of(page, slot)
    assert f'<details class="card gt-card gt-slot" id="stavka-{slot}" open>' in page          # the first not done
    assert ('<span class="gt-name"><span class="t">Prazno mjesto</span> · potisak</span>\n      '
            '<span class="gt-planned"><span class="t">Zadano:</span> 12 ponavljanja</span>') in cs
    assert '<p class="gt-sub">Lagano.</p>' in cs and "gt-mark" not in cs and "pl-sets" not in cs
    assert (f'<form class="gt-fill" method="post" action="/karton/trening/{tid}/stavke/{slot}/vjezba" data-hint="potisak" '
            'hidden>') in cs
    assert (f'<label for="gt-fill-{slot}"><span class="t">Vježba</span></label>' in cs
            and '<button type="submit" class="btn btn-sm"><span class="t">Odaberi</span></button>' in cs
            and f'<button type="submit" form="gt-x-{slot}" class="act act-quiet"><span class="t">Ukloni</span></button>' in cs)
    assert '<span class="gt-planned"><span class="t">Zadano:</span> 30 s</span>' in card_of(page, core)
    one = page.split('id="krug-trening_b-1"')[1].split("</details>")[0]
    assert f'name="stavke" value="{goblet}"' in one and f'name="sec_{core}"' not in one   # a slot is in no round
    t = db.gym_training(tid, ivan)
    assert t.count_text == "1 vježba" and [name for name, *_ in t.lines()] == ["Goblet čučanj"]
    assert "data-confirm" not in page.split(f'<form id="gt-x-{slot}"')[1].split("</form>")[0]

    def fill(iid, exercise_id):
        return ci.post(f"/karton/trening/{tid}/stavke/{iid}/vjezba", data={"exercise_id": exercise_id},
                       follow_redirects=False)

    for value, sentence in (("", "Odaberi vježbu s popisa."), ("abc", "Odaberi vježbu s popisa."),
                            ("999999", "Nepoznata vježba.")):
        assert location(fill(slot, value)) == f"/karton/trening/{tid}?stavka={slot}&error={sentence}#stavka-{slot}"
    r = fill(slot, str(ex["Sklekovi"]))
    assert location(r) == f"/karton/trening/{tid}?stavka={slot}&dodano=1#stavka-{slot}"
    with db.session_scope() as s:
        it = s.get(GymTrainingItem, slot)
        assert (it.exercise_id, it.exercise_name, it.hint, it.reps, it.note, it.position) == (
            ex["Sklekovi"], "Sklekovi", "potisak", 12, "Lagano.", 1)
    assert location(fill(slot, str(ex["Plank"]))) == (f"/karton/trening/{tid}?stavka={slot}&error=Mjesto je već "
                                                      f"popunjeno.#stavka-{slot}")
    page = ci.get(f"/karton/trening/{tid}?stavka={slot}&dodano=1").text
    assert f'<details class="card gt-card" id="stavka-{slot}" open>' in page
    assert table(card_of(page, slot)) == [(n, {"reps": "12", "kg": ""}, False) for n in (1, 2, 3)]
    fill(core, str(ex["Plank"]))                                            # in a circuit: it joins the rounds
    one = ci.get(f"/karton/trening/{tid}").text.split('id="krug-trening_b-1"')[1].split("</details>")[0]
    assert f'name="stavke" value="{goblet},{core}"' in one and f'name="sec_{core}" value="30"' in one
    assert db.gym_training(tid, ivan).count_text == "3 vježbe"
    other = db.add_gym_outside(ivan, config.today())
    assert ci.post(f"/karton/trening/{other}/stavke/{slot}/vjezba", data={"exercise_id": "1"}).status_code == 404


# ---------- the texts ----------

GYM_SLOTS = [k for k in copy.SLOTS if k.startswith("gym.") and k not in ("gym.kicker", "gym.h2")]   # the landing's two
GYM_OPTIONAL = {"gym.head.kicker", "gym.state.closed", "gym.state.staff", "gym.empty", "gym.osvrt.kicker"}


def test_every_text_of_the_page_is_a_slot_with_its_words():
    """The page's and its osvrt's texts are slots, gym.<area>.* (53 since
    part B: the template's button, "Uredi dio"'s seven, a slot's two),
    labelled "Trening u dvorani…" in the editor's bar, required but for a
    kicker, a state's whole sentence and the empty line; each printed on a
    page the member reads with its default words (a confirm's in its
    attribute, the script's in the script); where the words do the same job
    as in the player and its finish screen, the player's slots print
    (player.*, dan.*, kraj.*: a round's rating and button, "kružno", a
    slot's "Prazno mjesto"). One edited prints in its place; /tekstovi
    lists them under "Trening u dvorani", after "Trening (izvođenje)"."""
    assert len(GYM_SLOTS) == 53
    assert {k for k in GYM_SLOTS if not copy.SLOTS[k].required} == GYM_OPTIONAL
    assert all(copy.SLOTS[k].label.startswith("Trening u dvorani") for k in GYM_SLOTS)
    ivan = make_user("ivan@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    ex = library("Goblet čučanj", "Plank")
    day = dvoranski()                                                       # part B: a template, a slot, a circuit
    db.add_day_slot(day, "trening_c", "potisak", reps=12)
    db.set_circuit(day, "istezanje", 2, 60)
    db.add_day_item(day, ex["Plank"], "istezanje", seconds=30)
    live = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    db.gym_from_template(live, ivan, day)
    empty = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=2)))
    a = db.add_gym_item(live, ivan, ex["Goblet čučanj"], "trening", 3, 10)
    db.add_gym_item(live, ivan, ex["Plank"], "trening", 2, seconds=30)
    db.save_gym_done(a, ivan, [{"reps": 10, "kg": 20.0}])
    closed = db.gym_training_for(ivan, termin(ivan, now() - timedelta(days=3)), staff=True)
    db.add_gym_item(closed, ivan, ex["Plank"], "trening", staff=True)
    done = db.add_gym_outside(ivan, config.today())
    db.finish_gym_training(done, ivan, 7, None, "")
    ci, cs = client_for("ivan@test.local"), client_for("coach@test.local")
    pages = [ci.get(f"/karton/trening/{x}").text for x in (live, empty, closed, done)]
    pages.append(ci.get(f"/karton/trening/{live}/osvrt").text)
    cs.post(f"/kao/{ivan}")
    pages.append(cs.get(f"/karton/trening/{closed}").text)                  # staff, past his window
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    every = "\n".join(pages)
    assert 'data-copy="' not in every
    for key in GYM_SLOTS:
        text = copy.SLOTS[key].default
        assert f'<span class="t">{text}</span>' in every or f'="{text}"' in every or json.dumps(text) in every, key
    for key in ("player.col.set", "player.col.reps", "player.col.sec", "player.rate.step", "player.finish",
                "player.rest.skip", "kraj.effort", "kraj.feeling", "kraj.save", "player.rate.round", "player.round.done",
                "player.list.circuit", "dan.slot"):
        assert f'<span class="t">{copy.SLOTS[key].default}</span>' in every, key
    for key, text in (("gym.card.edit", "Promijeni zadano"), ("gym.confirm.empty_title", "Sve van?"),
                      ("gym.card.failed", "Nije prošlo.")):
        assert cs.post(f"/copy/{key}", data={"text": text}).json()["text"] == text
    page = ci.get(f"/karton/trening/{live}").text
    assert '<summary class="act act-quiet"><span class="t">Promijeni zadano</span></summary>' in page
    assert 'data-confirm-title="Sve van?"' in page and 'var NOT_SAVED = "Nije pro\\u0161lo.";' in page
    tekstovi = cs.get("/tekstovi").text
    h2 = re.findall(r'<h2 id="tx-\d+">([^<]*)</h2>', tekstovi)
    assert h2.index("Trening u dvorani") == h2.index("Trening (izvođenje)") + 1
    section = tekstovi.split(">Trening u dvorani</h2>")[1].split("<h2")[0]
    assert re.findall(r"<h3>([^<]*)</h3>", section) == ["Zaglavlje", "Predložak", "Dio i krugovi", "Vježba",
                                                       "Prazno mjesto", "Dodaj vježbu", "Kraj treninga", "Osvrt",
                                                       "Prozori za potvrdu"]
    assert all(f'data-copy="{k}"' in section for k in GYM_SLOTS)


def test_staffs_own_training_lights_their_karton():
    """Staff have trainings outside a termin of their own (no termini): the
    page serves them as a member's, the nav's Karton lit and Admin ▾ not
    (their own karton's pages, not a member's), the editor's ✎ on it."""
    coach = make_user("coach@test.local", is_trainer=True, plans=())
    cs = client_for("coach@test.local")
    r = cs.post("/karton/trening", data={"day": config.today().isoformat()}, follow_redirects=False)
    tid = int(location(r).rsplit("/", 1)[1])
    page = cs.get(f"/karton/trening/{tid}").text
    assert db.gym_training(tid, coach).session_id is None and 'id="dodaj"' in page and 'id="copyToggle"' in page
    assert '<a href="/karton" class="on">Karton</a>' in page
    assert re.search(r'id="adminBtn" class="navbtn menu-btn"\s', page)               # not .on
    assert 'href="/clanarine" role="menuitem" aria-current' not in page


# ---------- in a browser, on a phone ----------

@pytest.fixture(scope="module")
def server():
    import uvicorn
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/healthz", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{PORT}"
    srv.should_exit = True
    th.join(timeout=5)


OVERFLOW = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"


def test_a_training_on_a_phone(server):
    """The owner's flow at 390px, touch, as ivan: his termin's training from
    the karton's "Upiši trening"; "Dodaj vježbu" (typed into the combobox,
    picked, its zadano folded: 3 × 10 · 20 kg, 60 s) brings its card back
    open, the focus in its first input; a ✓ ticks a row, saves it (the
    mark "1/3") and starts the rest bar ("ODMOR", 1:00, "Preskoči odmor"
    ends it); a second row's weight changed and ticked; offline, a tick
    comes back unticked with "Nije spremljeno — pokušaj ponovno."; the
    third ticked (✓), the rating 8 saved by its tap; then, only then, the
    next exercise (Plank, 2 × 30 s, SET · SEK.), both its sets ticked.
    "Završi trening": napor 7, Dobro, a comment, "Spremi trening" → the
    karton at its row, "Serije" opened: each exercise what was given and
    what was done. No page ever scrolls sideways, at 360px either, the
    rest bar showing; no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    ivan = make_user("ivan@test.local")
    for name in ("Goblet čučanj", "Plank", "Swing"):
        db.create_exercise(name, "Upute za: " + name, tags="girja")
    start = (now() - timedelta(minutes=90)).replace(second=0, microsecond=0)
    sid = termin(ivan, start, title="Snaga")
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    def items():
        [t] = db.gym_trainings(ivan)
        return t, t.items

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(server + "/login")
        pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); "
                    "localStorage.setItem('qmt-phone', String(Date.now())); }")
        pg.fill("main input[name=email]", "ivan@test.local")
        pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]")
        pg.wait_for_load_state("networkidle")
        pg.goto(server + "/karton")
        if pg.locator("#fbDlg[open], dialog[open]").count():               # the login's prompt: later
            pg.keyboard.press("Escape")
        pg.locator(f'#s-{sid} a[href="/karton/termin/{sid}/trening"]').tap()
        pg.wait_for_load_state("networkidle")
        t, _ = items()
        check(pg.url.endswith(f"/karton/trening/{t.id}"), f"Upiši trening led to {pg.url}")
        check(pg.evaluate(OVERFLOW) == 0, f"the empty training overflows by {pg.evaluate(OVERFLOW)}px")
        check(pg.locator(".gt-when > span").first.inner_text() == when_text(start), "the date and the time")

        def add(query: str, name: str, **zadano):
            box = pg.locator("#gt-add-ex-q")
            box.tap()
            box.fill(query)
            pg.locator("#gt-add-ex-list [role=option]", has_text=name).first.tap()
            check(box.input_value() == name, f"the combobox holds {box.input_value()!r}")
            pg.locator(".gt-zadano > summary").tap()
            for field, value in zadano.items():
                pg.fill(f"#gt-add-{field}", str(value))
            with pg.expect_navigation():
                pg.locator('#dodaj button[type="submit"]').tap()
            pg.wait_for_load_state("networkidle")
            pg.wait_for_timeout(100)

        def tick_row(card, n: int):
            """Tap the ✓ of row n (1-based) and wait for its save."""
            with pg.expect_response(lambda r: r.url.endswith("/odradeno") and r.request.method == "POST"):
                card.locator("tbody tr").nth(n - 1).locator(".pl-done").tap()

        add("gob", "Goblet čučanj", sets=3, reps=10, kg=20, rest=60)
        _, its = items()
        goblet = its[0].id
        card = pg.locator(f"#stavka-{goblet}")
        check(card.get_attribute("open") is not None, "the new card is not open")
        check(pg.evaluate("document.activeElement && document.activeElement.name") == "reps_1",
              f"the focus is on {pg.evaluate('document.activeElement && document.activeElement.name')}")
        check(card.locator(".gt-save").is_hidden() and card.locator(".gt-add-set").is_visible(),
              "with JS: no Spremi, + serija shown")
        check(card.locator("thead th.pl-tick").is_visible(), "the ✓ column is not shown")
        rows = card.locator("tbody tr")
        check(rows.count() == 3 and rows.nth(0).locator("input[name=reps_1]").input_value() == "10"
              and rows.nth(0).locator("input[name=kg_1]").input_value() == "20", "the rows are not the zadano")
        tick_row(card, 1)
        check(done_of(goblet) == [{"reps": 10, "kg": 20.0}], f"saved {done_of(goblet)}")
        check(card.locator("[data-mark]").inner_text() == "1/3", "the mark is not 1/3")
        rest = pg.locator("#plRest")
        check(rest.is_visible() and pg.locator(".pl-rest-h").inner_text().upper() == "ODMOR"
              and pg.locator(".pl-rest-t").inner_text() in ("1:00", "0:59", "0:58"), "the rest bar did not start")
        box = rest.bounding_box()
        check(box is not None and box["y"] + box["height"] <= 844 and box["x"] >= 0 and box["x"] + box["width"] <= 390,
              f"the rest bar is off the screen: {box}")
        pg.set_viewport_size({"width": 360, "height": 780})
        check(pg.evaluate(OVERFLOW) == 0, f"at 360px, the rest bar showing, the page overflows by {pg.evaluate(OVERFLOW)}px")
        pg.set_viewport_size({"width": 390, "height": 844})
        pg.locator(".pl-rest-skip").tap()
        check(rest.is_hidden(), "Preskoči odmor did not end the rest")
        rows.nth(1).locator("input[name=kg_2]").fill("22.5")
        tick_row(card, 2)
        check(done_of(goblet) == [{"reps": 10, "kg": 20.0}, {"reps": 10, "kg": 22.5}], f"saved {done_of(goblet)}")
        pg.locator(".pl-rest-skip").tap()
        ctx.set_offline(True)                                               # a tick that cannot be saved
        rows.nth(2).locator(".pl-done").tap()
        pg.wait_for_function(f"!document.querySelector('#stavka-{goblet} .gt-err').hidden")
        check(rows.nth(2).locator(".pl-done").get_attribute("aria-pressed") == "false", "a failed tick stays ticked")
        check(card.locator(".gt-err").inner_text() == "Nije spremljeno — pokušaj ponovno.", "the failure is not said")
        check(card.locator("[data-mark]").inner_text() == "2/3", "the mark counts a failed tick")
        ctx.set_offline(False)
        pg.locator(".pl-rest-skip").tap()
        tick_row(card, 3)
        check(card.locator(".gt-err").is_hidden(), "the failure's line stays after a save")
        check(card.locator("[data-mark]").inner_text() == "✓", "every planned set ticked: no ✓")
        with pg.expect_response(lambda r: r.url.endswith("/odradeno")):
            card.locator(".pl-rate label.sc").nth(7).tap()
        with db.session_scope() as s:
            check(s.get(GymTrainingItem, goblet).effort == 8, "the rating is not saved")
        pg.locator(".pl-rest-skip").tap()
        check(pg.evaluate(OVERFLOW) == 0, f"the card overflows by {pg.evaluate(OVERFLOW)}px")
        add("plank", "Plank", sets=2, secs=30, rest=30)                    # the next, only now
        _, its = items()
        plank = its[-1].id
        card = pg.locator(f"#stavka-{plank}")
        check(pg.locator(f"#stavka-{goblet}").get_attribute("open") is None, "the done card stays open")
        cols = [h.strip().upper() for h in card.locator("thead th").all_inner_texts()]
        check(cols[:2] == ["SET", "SEK."] and len(cols) == 3, f"the plank's columns: {cols}")
        tick_row(card, 1)
        check(pg.locator("#plRest").is_visible(), "its pause did not start the rest bar")
        tick_row(card, 2)
        check(done_of(plank) == [{"seconds": 30}, {"seconds": 30}], f"the plank saved {done_of(plank)}")
        pg.set_viewport_size({"width": 360, "height": 780})
        check(pg.evaluate(OVERFLOW) == 0, f"at 360px the training overflows by {pg.evaluate(OVERFLOW)}px")
        pg.set_viewport_size({"width": 390, "height": 844})
        pg.locator(".pl-rest-skip").tap()
        with pg.expect_navigation():
            pg.locator(".gt-finish .btn").tap()
        check(pg.url.endswith(f"/karton/trening/{t.id}/osvrt"), f"Završi trening led to {pg.url}")
        check(pg.evaluate(OVERFLOW) == 0, f"the osvrt overflows by {pg.evaluate(OVERFLOW)}px")
        pg.locator(".scale label.sc").nth(6).tap()
        pg.locator("label.opt", has_text="Dobro").tap()
        pg.fill("#kr-note", "Dobar trening.")
        with pg.expect_navigation():
            pg.locator(".kr-go .btn").tap()
        pg.wait_for_load_state("networkidle")
        check(f"/karton?ok=" in pg.url and pg.url.endswith(f"#gt-{t.id}"), f"the osvrt led to {pg.url}")
        check("Trening je spremljen." in pg.locator("main").inner_text(), "no word that it is saved")
        row = pg.locator(f"#gt-{t.id}")
        row.locator("details.sets > summary").tap()
        lines = [" ".join(x.split()) for x in row.locator("details.sets li").all_inner_texts()]
        check(lines == ["Goblet čučanj: zadano 3 × 10 · 20 kg — odrađeno 10 × 20 kg · 10 × 22,5 kg · 10 × 20 kg · "
                        "težina 8/10", "Plank: zadano 2 × 30 s — odrađeno 30 s · 30 s"], f"the diary's lines: {lines}")
        check("napor 7/10" in row.inner_text() and "Dobro" in row.inner_text() and "Dobar trening." in row.inner_text(),
              "the diary's row does not say the osvrt")
        check(pg.evaluate(OVERFLOW) == 0, f"the karton overflows by {pg.evaluate(OVERFLOW)}px")
        pg.set_viewport_size({"width": 360, "height": 780})
        check(pg.evaluate(OVERFLOW) == 0, f"at 360px the karton overflows by {pg.evaluate(OVERFLOW)}px")
        browser.close()
    t = db.gym_trainings(ivan)[0]
    check((t.effort, t.feeling, t.note) == (7, "dobro", "Dobar trening."), f"the osvrt stored {(t.effort, t.feeling, t.note)}")
    offline = [e for e in errors if "ERR_INTERNET_DISCONNECTED" not in e and "Failed to load resource" not in e]
    assert not problems and not offline, problems + offline


def test_a_template_and_its_circuit_on_a_phone(server):
    """Part B at 390px, touch, as ivan, on his termin's training: empty, its
    "Odaberi gotov trening" opens the list and a row copies the template in
    (a circuit part "Krug 1" of two rounds, 60 s after a round, of two
    slots); the first slot's card is open, its combobox on the slot's hint
    ("čučanj": the list already narrowed), a pick and "Odaberi" make it a
    card of the circuit, whose rounds appear; the second slot, opened by a
    tap (the focus in its picker, the list open), filled the same way. Round
    1 (its first values what was given) "Krug 1 odrađen": the page back at
    the part, the rest bar counting the part's 60 s, round 1 folded with its
    ✓ and round 2 open, the weight carried; round 2's weight changed, "Krug 2
    odrađen": every round ✓, each exercise's mark ✓, the sets stored a set
    a round. No page scrolls sideways, at 360px either; no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    ivan = make_user("ivan@test.local")
    ex = {name: db.create_exercise(name, "Upute za: " + name, tags=tags)
          for name, tags in (("Goblet čučanj", "noge"), ("Čučanj s vlastitom težinom", "noge"), ("Plank", "core"))}
    day = dvoranski("Predložak — kružni", day_title="Krug")
    db.set_part_name(day, "trening", "Krug 1")
    db.set_circuit(day, "trening", 2, 60)
    db.add_day_slot(day, "trening", "čučanj", reps=10, kg=16)
    db.add_day_slot(day, "trening", "core", seconds=30)
    start = (now() - timedelta(minutes=90)).replace(second=0, microsecond=0)
    sid = termin(ivan, start, title="Snaga")
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    def items():
        [t] = db.gym_trainings(ivan)
        return t, t.items

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(server + "/login")
        pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); "
                    "localStorage.setItem('qmt-phone', String(Date.now())); }")
        pg.fill("main input[name=email]", "ivan@test.local")
        pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]")
        pg.wait_for_load_state("networkidle")

        def wide(where: str) -> None:
            for w, h in ((390, 844), (360, 780)):
                pg.set_viewport_size({"width": w, "height": h})
                check(pg.evaluate(OVERFLOW) == 0, f"{where} at {w}px overflows by {pg.evaluate(OVERFLOW)}px")
            pg.set_viewport_size({"width": 390, "height": 844})

        pg.goto(server + f"/karton/termin/{sid}/trening")
        pg.wait_for_load_state("networkidle")
        t, _ = items()
        check(pg.url.endswith(f"/karton/trening/{t.id}"), f"the training is at {pg.url}")
        pg.locator(".gt-tpl > summary").tap()
        row = pg.locator(".gt-tpl-row", has_text="Predložak — kružni · Trening 1 · Krug")
        check(row.is_visible(), "the template's row is not shown")
        wide("the template list")
        with pg.expect_navigation():
            row.tap()
        pg.wait_for_load_state("networkidle")
        _, its = items()
        squat, core = its[0].id, its[1].id
        check([it.hint for it in its] == ["čučanj", "core"] and all(it.is_slot for it in its), "the slots are not copied")
        check(pg.locator(f"#stavka-{squat}").get_attribute("open") is not None, "the first slot is not open")
        box = pg.locator(f"#gt-fill-{squat}-q")
        check(box.input_value() == "čučanj", f"the picker holds {box.input_value()!r}, not the hint")
        wide("the slots")
        box.tap()
        options = pg.locator(f"#gt-fill-{squat}-list [role=option]")
        check(options.count() == 2, f"the hint narrows the list to {options.count()} rows")
        options.filter(has_text="Goblet čučanj").first.tap()
        with pg.expect_navigation():
            pg.locator(f"#stavka-{squat} form.gt-fill button[type=submit]").tap()
        pg.wait_for_load_state("networkidle")
        check(pg.locator(f"#stavka-{squat}.gt-crow").count() == 1, "the filled slot is no circuit's card")
        check(pg.locator("#krug-trening-1").count() == 1, "its rounds did not appear")
        pg.locator(f"#stavka-{core} > summary").tap()
        pg.wait_for_timeout(150)
        check(pg.evaluate("document.activeElement && document.activeElement.id") == f"gt-fill-{core}-q",
              "a slot opened by a tap does not take the focus in its picker")
        pg.locator(f"#gt-fill-{core}-q").fill("plank")
        pg.locator(f"#gt-fill-{core}-list [role=option]", has_text="Plank").first.tap()
        with pg.expect_navigation():
            pg.locator(f"#stavka-{core} form.gt-fill button[type=submit]").tap()
        pg.wait_for_load_state("networkidle")
        one = pg.locator("#krug-trening-1")
        check(one.get_attribute("open") is not None, "round 1 is not open")
        check(one.locator(f"input[name=kg_{squat}]").input_value() == "16"
              and one.locator(f"input[name=sec_{core}]").input_value() == "30", "round 1's first values are not the zadano")
        wide("the rounds")
        with pg.expect_navigation():
            one.locator('button[type="submit"]').tap()
        pg.wait_for_load_state("networkidle")
        check("?dio=trening&odmor=60" in pg.url and pg.url.endswith("#dio-trening"), f"round 1 led to {pg.url}")
        rest = pg.locator("#plRest")
        check(rest.is_visible() and pg.locator(".pl-rest-t").inner_text() in ("1:00", "0:59", "0:58"),
              "the rest after a round did not start")
        wide("a round saved, the rest bar showing")
        pg.locator(".pl-rest-skip").tap()
        one, two = pg.locator("#krug-trening-1"), pg.locator("#krug-trening-2")
        check(one.get_attribute("open") is None and one.locator(".gt-mark").inner_text() == "✓", "round 1 is not folded, ✓")
        check(two.get_attribute("open") is not None and two.locator(f"input[name=kg_{squat}]").input_value() == "16",
              "round 2 is not open with the weight carried")
        two.locator(f"input[name=kg_{squat}]").fill("18")
        with pg.expect_navigation():
            two.locator('button[type="submit"]').tap()
        pg.wait_for_load_state("networkidle")
        check(pg.locator("details.gt-round[open]").count() == 0, "a round stays open when every one is saved")
        check([pg.locator(f"#stavka-{x} .gt-mark").inner_text() for x in (squat, core)] == ["✓", "✓"],
              "the exercises' marks are not ✓")
        pg.locator(".pl-rest-skip").tap()
        wide("every round saved")
        browser.close()
    check(done_of(squat) == [{"reps": 10, "kg": 16.0, "round": 1}, {"reps": 10, "kg": 18.0, "round": 2}],
          f"the squat stored {done_of(squat)}")
    check(done_of(core) == [{"seconds": 30, "round": 1}, {"seconds": 30, "round": 2}], f"the plank stored {done_of(core)}")
    assert not problems and not errors, problems + errors
