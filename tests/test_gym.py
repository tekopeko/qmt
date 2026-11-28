"""The gym training (26.11.2026, build 3 of roadmap/2026-11-26-gym-training-plan.md;
since 27.11.2026, build 1 of roadmap/2026-11-27-dvoranski-treninzi-plan.md, a row
of blocks, Stanica and Kružni set, at /dvoranski/trening/<id>).

The owner: "automatically add the training with its title already after a
user booked it and he can already edit it 4 hours before the training up
until the next day. Amir can also edit it later."; and on 27.11.2026: "A gym
training consists of 'Stanica' and 'Kružni set' where the 'Kružni set'
consists of 4 of 'Krug' at default which can be changed. Each 'Krug' is the
set of same exercises, but the user can edit the number of reps done after
each 'Krug' during the pause."

A member's training (models.GymTraining, GymTrainingBlock, GymTrainingItem;
migration 9b4e2d7f1c58, run for real on qmt_test there and back over a
training of the old shape) is his alone. A termin's is open to him from its
booking's cancel deadline (CANCEL_CUTOFF_HOURS before the termin: since
27.11.2026 one number for both) until the end of the day after it, a
training outside a termin always, staff acting as him at any time (rule 1,
db.gym_can_write); it is made the first time it is opened (rule 2); a
cancelled booking takes it along, or lets it go of its termin when it holds a
record (rule 3); a Stanica's tick saves its ticked rows whole (rule 4, under
the training's row lock); its first values are what was asked, nothing else
(rule 5); its saved sets count for the history and the maxes at once (rule
6); /media shows its exercises' clips to its member (rule 7); and the login's
prompt owes a termin only while its training's window is open (rule 8). The
blocks' rules (db.apply_gym_template, add_gym_block, delete_gym_block,
set_gym_station, save_gym_done, rate_gym_block, save_gym_circuit,
add_gym_row, delete_gym_row, set_gym_rounds, save_gym_round), each refusal's
sentence, the four races; the page (karton_trening.html: the chooser, a
Stanica empty and started, a Kružni set set up and started, "Nastavi
trening", the overview, read only), its osvrt, the old addresses leading
here, the karton's diary and termini, the raspored's card, a roster's "Kao
član →", the texts; the browser half walks the owner's two templates on a
phone. The tab the pages hang under since 27.11.2026, "Dvoranski treninzi"
(build 2), is tests/test_dvoranski.py's."""

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
from sqlalchemy import inspect as sa_inspect, select, text as sa_text
from sqlalchemy.orm import selectinload

from qmt import auth, config, copy, db
from qmt.models import WEEKDAYS, Base, Booking, GymTraining, GymTrainingBlock, GymTrainingItem, TrainingLog, User
from qmt.web.app import app

PORT = 8118    # test_copy's 8111, test_raspored_ui's / test_upitnik_ui's 8112, test_nav's 8113, test_programs' 8114,
               # test_player's 8115, test_karton's 8116, test_kao's 8117

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLOSED = "Upis ovog treninga je zatvoren — trener ga i dalje može urediti."
CHANGED = "Trening se u međuvremenu promijenio — provjeri vježbu i spremi ponovno."
JSON = {"Accept": "application/json"}


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    with db.engine.begin() as conn:                 # a migration test's old table, should one stop half way
        conn.execute(sa_text("DROP TABLE IF EXISTS gym_training_parts CASCADE"))
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


def shown(html: str) -> str:
    """What a reader sees of some markup: the tags gone, the spaces folded."""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def station(tid: int, uid: int, exercise: int | None = None, sets=None, reps=None, seconds=None, kg=None, rest=None,
            note: str = "", staff: bool = False) -> int:
    """A Stanica after the last block, its exercise and plan when one is given: its id."""
    bid = db.add_gym_block(tid, uid, "stanica", staff=staff)
    if exercise is not None:
        db.set_gym_station(bid, uid, exercise, sets, reps, seconds, kg, rest, note, staff=staff)
    return bid


def circuit(tid: int, uid: int, rows=(), rounds: int = 4, rest=None, staff: bool = False) -> tuple[int, list[int]]:
    """A Kružni set after the last block, its first rows given as
    (exercise, reps, kg, seconds), the rest empty: (its id, its rows' ids)."""
    bid = db.add_gym_block(tid, uid, "kruzni", staff=staff)
    items = block(bid).items
    plan = {it.id: {"exercise_id": None, "reps": None, "kg": None, "seconds": None} for it in items}
    for it, (ex, reps, kg, sec) in zip(items, rows):
        plan[it.id] = {"exercise_id": ex, "reps": reps, "kg": kg, "seconds": sec}
    db.save_gym_circuit(bid, uid, plan, rounds, rest, staff=staff)
    return bid, [it.id for it in items]


def block(bid: int) -> GymTrainingBlock:
    """A block as stored now, its items loaded."""
    with db.session_scope() as s:
        return s.scalar(select(GymTrainingBlock).where(GymTrainingBlock.id == bid)
                        .options(selectinload(GymTrainingBlock.items)))


def item_of(bid: int) -> GymTrainingItem:
    return block(bid).items[0]


def done_of(iid: int) -> list[dict]:
    with db.session_scope() as s:
        return s.get(GymTrainingItem, iid).done_sets


def tick(c: TestClient, tid: int, bid: int, polja: str, *rows: dict, headers=JSON):
    """A tick's save as the page's script posts it: the ticked rows,
    numbered from 1; JSON back."""
    data = {"polja": polja, "rows": str(len(rows))}
    for n, row in enumerate(rows, start=1):
        data.update({f"{k}_{n}": str(v) for k, v in row.items()})
    return c.post(f"/dvoranski/trening/{tid}/blok/{bid}/odradeno", data=data, headers=headers, follow_redirects=False)


def krug(c: TestClient, tid: int, bid: int, n: int, by_item: dict, stavke=None):
    """A Krug's save as its form posts it: each row's inputs (reps_<id>,
    kg_<id>, sec_<id>), the rows it was drawn for."""
    data = {"stavke": ",".join(str(i) for i in (stavke if stavke is not None else by_item))}
    for iid, values in by_item.items():
        data.update({f"{k}_{iid}": str(v) for k, v in values.items()})
    return c.post(f"/dvoranski/trening/{tid}/blok/{bid}/krug/{n}", data=data, follow_redirects=False)


def plan(c: TestClient, tid: int, bid: int, rows: dict, rounds="4", rest="", **extra):
    """A Kružni set's plan as its form posts it: per row vjezba_<id>,
    reps_<id>, kg_<id>, sec_<id>, the rows it was drawn for, Krugova, the
    pause after a Krug, and a button's own (kreni, dodaj, ukloni)."""
    data = {"stavke": ",".join(str(i) for i in rows), "rounds": rounds, "rest": rest, **extra}
    for iid, (ex, reps, kg, sec) in rows.items():
        data.update({f"vjezba_{iid}": str(ex or ""), f"reps_{iid}": str(reps or ""), f"kg_{iid}": str(kg or ""),
                     f"sec_{iid}": str(sec or "")})
    return c.post(f"/dvoranski/trening/{tid}/blok/{bid}/plan", data=data, follow_redirects=False)


# an empty block's two buttons as a member reads them (28.11.2026): "Kreni"
# filled, "Spremi" beside it; staff acting as him the other way round
KRENI = '<button type="submit" name="kreni" value="1" class="btn"><span class="t">Kreni</span></button>'
SPREMI = '<button type="submit" name="spremi" value="1" class="btn btn-ghost"><span class="t">Spremi</span></button>'


def main_card(page: str) -> str:
    """The page's main card (#glavno), to the overview or the foot."""
    return re.split(r'<aside class="pl-side"|<div class="gt-foot-col">', page.split('id="glavno"')[1])[0]


def overview(page: str) -> str:
    return page.split('<aside class="pl-side" id="pregled"')[1].split("</aside>")[0]


def page_url(tid: int, **query) -> str:
    return f"/dvoranski/trening/{tid}" + ("?" + "&".join(f"{k}={v}" for k, v in query.items()) if query else "")


# ---------- the migrations ----------

def _migration(file: str):
    path = ROOT / "alembic" / "versions" / file
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


GYM_TABLES = {"gym_trainings", "gym_training_items", "gym_training_blocks", "gym_templates", "gym_template_blocks"}
OLD = "c4e1b7f9a2d6_gym_trainings.py"
OLD_PARTS = "36d6e2c97de7_gym_training_parts.py"
BLOCKS = "9b4e2d7f1c58_gym_training_blocks.py"


def _before_the_gym() -> None:
    """qmt_test as before the gym trainings: the models' gym tables gone."""
    with db.engine.begin() as conn:
        conn.execute(sa_text("DROP TABLE gym_template_blocks, gym_templates, gym_training_items, gym_training_blocks, "
                             "gym_trainings"))


def _sql(statement: str, **params):
    with db.engine.begin() as conn:
        return conn.execute(sa_text(statement), params)


def test_the_gym_migrations_run_there_and_back_and_end_as_the_models():
    """c4e1b7f9a2d6 (the trainings and their items: the partial unique
    index on a member and a termin, the deferred place, the CHECK on a
    part) and 36d6e2c97de7 (their parts: two CHECKs) each make their tables
    and take them away, the karton's TrainingLog rows untouched; and
    9b4e2d7f1c58 on top of them leaves the gym tables as the models have
    them, to their indexes and constraints."""
    old, parts, blocks = _migration(OLD), _migration(OLD_PARTS), _migration(BLOCKS)
    assert (blocks.revision, blocks.down_revision) == ("9b4e2d7f1c58", "3d9a6f2c8b51")
    ivan = make_user("ivan@test.local")
    with db.session_scope() as s:
        s.add(TrainingLog(user_id=ivan, date=date(2026, 11, 20), effort=6, note="Staro.", sets="[]"))
    _before_the_gym()
    _run(old.upgrade)
    indexes = {i["name"]: i for i in sa_inspect(db.engine).get_indexes("gym_trainings")}
    assert indexes["uq_gym_trainings_user_session"]["unique"] and "ix_gym_trainings_user_id" in indexes
    where = _sql("SELECT pg_get_indexdef('uq_gym_trainings_user_session'::regclass)").scalar_one()
    deferred = _sql("SELECT condeferrable, condeferred FROM pg_constraint WHERE conname = 'uq_gym_training_items_position'").one()
    assert "WHERE (session_id IS NOT NULL)" in where and tuple(deferred) == (True, True)
    tid = _sql("INSERT INTO gym_trainings (user_id, held_on) VALUES (:u, '2026-11-20') RETURNING id", u=ivan).scalar_one()
    with pytest.raises(Exception, match="ck_gym_training_items_section"):
        _sql("INSERT INTO gym_training_items (training_id, section, position) VALUES (:t, 'kardio', 1)", t=tid)
    _run(old.downgrade)
    assert not {"gym_trainings", "gym_training_items"} & set(sa_inspect(db.engine).get_table_names())
    assert [(x.effort, x.note) for x in db.training_logs(ivan)] == [(6, "Staro.")]
    _run(old.upgrade)
    _run(parts.upgrade)
    tid = _sql("INSERT INTO gym_trainings (user_id, held_on) VALUES (:u, '2026-11-20') RETURNING id", u=ivan).scalar_one()
    _sql("INSERT INTO gym_training_parts (training_id, section, rounds) VALUES (:t, 'trening', 3)", t=tid)
    for bad in ("rounds = 21", "rounds = 1", "rest_seconds = 3601", "rest_seconds = -1"):
        with pytest.raises(Exception, match="ck_gym_training_parts"):
            _sql(f"UPDATE gym_training_parts SET {bad}")
    _run(parts.downgrade)
    assert "gym_training_parts" not in sa_inspect(db.engine).get_table_names()
    _run(parts.upgrade)
    _run(blocks.upgrade)
    assert "gym_training_parts" not in sa_inspect(db.engine).get_table_names()
    assert _schema_diffs(GYM_TABLES) == []
    for name in ("uq_gym_training_blocks_position", "uq_gym_training_items_block_position", "uq_gym_templates_position",
                 "uq_gym_template_blocks_position"):
        assert tuple(_sql("SELECT condeferrable, condeferred FROM pg_constraint WHERE conname = :n", n=name).one()) == (
            True, True), name
    assert [(x.effort, x.note) for x in db.training_logs(ivan)] == [(6, "Staro.")]


def test_the_blocks_migration_converts_a_training_and_takes_it_back():
    """9b4e2d7f1c58 over a training of the old shape: its items in
    SECTIONS' order, then by place; a circuit part (a parts row with
    rounds) ONE Kružni set, its rounds, its rest, its rating the first its
    items hold, its items in their order; every other item, a slot too, a
    Stanica of its own, its rating the item's; the sets, their rounds, the
    numbers and the hints kept; a renamed part's name let go; the two
    templates there. Downgrade: the stations' items into 'trening', the set's
    into 'trening_b' (a circuit part again, its rounds and rest), the ratings
    back on the items, no block, no template. Up again: the same blocks, the
    stations first (the order the old shape can say), as the models have
    them."""
    old, parts, blocks = _migration(OLD), _migration(OLD_PARTS), _migration(BLOCKS)
    ivan = make_user("ivan@test.local")
    ex = library("Plank", "Goblet čučanj", "Sklekovi", "Istezanje")
    sid = termin(ivan, now() - timedelta(hours=2), title="Snaga")
    _before_the_gym()
    _run(old.upgrade)
    _run(parts.upgrade)
    tid = _sql("INSERT INTO gym_trainings (user_id, session_id, title, starts_at, held_on) VALUES (:u, :s, 'Snaga', "
               "now(), current_date) RETURNING id", u=ivan, s=sid).scalar_one()
    out = _sql("INSERT INTO gym_trainings (user_id, held_on) VALUES (:u, '2026-01-05') RETURNING id", u=ivan).scalar_one()
    rows = {   # name: (section, position, exercise, its name, hint, sets, reps, seconds, kg, rest, note, done, effort)
        "D": ("istezanje", 1, ex["Istezanje"], "Istezanje", "", None, None, 30, None, None, "", "[]", None),
        "A": ("zagrijavanje", 2, ex["Plank"], "Plank", "", 2, None, 30, None, 30, "Lagano.", '[{"seconds": 30}]', 5),
        "S": ("zagrijavanje", 3, None, "", "aktivacija", None, 10, None, None, None, "", "[]", None),
        "B": ("trening", 4, ex["Goblet čučanj"], "Goblet čučanj", "čučanj", None, 10, None, 16, 60, "",
              '[{"reps": 10, "kg": 16.0, "round": 1}]', 7),
        "C": ("trening", 5, ex["Sklekovi"], "Sklekovi", "", 3, 10, None, None, None, "",
              '[{"reps": 10, "kg": 0.0, "round": 1}]', 7),
    }
    ids = {}
    for key, (section, position, eid, name, hint, sets, reps, sec, kg, rest, note, done, effort) in rows.items():
        ids[key] = _sql("INSERT INTO gym_training_items (training_id, section, position, exercise_id, exercise_name, hint, "
                        "sets, reps, seconds, kg, rest_seconds, note, done, effort) VALUES (:t, :sec, :p, :e, :n, :h, :s, "
                        ":r, :secs, :kg, :rest, :note, :done, :eff) RETURNING id",
                        t=tid, sec=section, p=position, e=eid, n=name, h=hint, s=sets, r=reps, secs=sec, kg=kg, rest=rest,
                        note=note, done=done, eff=effort).scalar_one()
    _sql("INSERT INTO gym_training_parts (training_id, section, title) VALUES (:t, 'zagrijavanje', 'Mobilnost')", t=tid)
    _sql("INSERT INTO gym_training_parts (training_id, section, title, rounds, rest_seconds) VALUES (:t, 'trening', "
         "'Krug 1', 3, 90)", t=tid)
    A, S, B, C, D = (ids[k] for k in "ASBCD")

    _run(blocks.upgrade)
    t = db.gym_training(tid, ivan)
    assert [(b.position, b.kind, b.rounds, b.rest_seconds, b.effort) for b in t.blocks] == [
        (1, "stanica", None, None, 5), (2, "stanica", None, None, None), (3, "kruzni", 3, 90, 7),
        (4, "stanica", None, None, None)]
    assert [[(it.id, it.position) for it in b.items] for b in t.blocks] == [[(A, 1)], [(S, 1)], [(B, 1), (C, 2)], [(D, 1)]]
    a, s_, k, d = t.blocks
    assert (a.item.sets, a.item.seconds, a.item.rest_seconds, a.item.note, a.item.done_sets) == (2, 30, 30, "Lagano.",
                                                                                               [{"seconds": 30}])
    assert s_.item.is_slot and s_.item.hint == "aktivacija" and s_.item.reps == 10 and not s_.holds_exercise
    assert [(it.exercise_name, it.hint, it.kg, it.done_sets) for it in k.items] == [
        ("Goblet čučanj", "čučanj", Decimal("16.0"), [{"reps": 10, "kg": 16.0, "round": 1}]),
        ("Sklekovi", "", None, [{"reps": 10, "kg": 0.0, "round": 1}])]
    assert k.rounds_saved == {1} and k.current_round == 2
    assert all(it.training_id == tid for b in t.blocks for it in b.items)
    assert db.gym_training(out, ivan).blocks == []
    assert [(x.title, x.facts) for x in db.gym_templates()] == [("Stanični trening", "6 stanica"),
                                                                 ("Kružni trening", "1 stanica · kružni set · 4 kruga")]

    _run(blocks.downgrade)
    names = set(sa_inspect(db.engine).get_table_names())
    assert "gym_training_parts" in names and not {"gym_training_blocks", "gym_templates", "gym_template_blocks"} & names
    back = _sql("SELECT id, section, position, effort, done FROM gym_training_items ORDER BY position").all()
    assert [(i, sec, p, e) for i, sec, p, e, _ in back] == [(A, "trening", 1, 5), (S, "trening", 2, None),
                                                          (D, "trening", 3, None), (B, "trening_b", 4, 7),
                                                          (C, "trening_b", 5, 7)]
    assert {i: json.loads(done) for i, *_, done in back} == {i: json.loads(rows[k][11]) for k, i in ids.items()}
    assert _sql("SELECT training_id, section, title, rounds, rest_seconds FROM gym_training_parts").all() == [
        (tid, "trening_b", "", 3, 90)]

    _run(blocks.upgrade)
    assert _schema_diffs(GYM_TABLES) == []
    t = db.gym_training(tid, ivan)
    assert [(b.kind, b.rounds, b.rest_seconds, b.effort, [it.id for it in b.items]) for b in t.blocks] == [
        ("stanica", None, None, 5, [A]), ("stanica", None, None, None, [S]), ("stanica", None, None, None, [D]),
        ("kruzni", 3, 90, 7, [B, C])]
    assert t.lines()[0] == ("Plank", "zadano 2 × 30 s — odrađeno", ["30 s", "težina 5/10"], "")


def test_the_two_templates_are_the_codes_the_migrations_and_the_seeds():
    """copy.GYM_TEMPLATES (the code's) and the migration's own copy say the
    same two: "Stanični trening" (six Stanica) and "Kružni trening" (a
    Stanica, a Kružni set of 4 rows and 4 Krug, no pause). The dev seed's
    seed_gym_templates puts exactly them back, whatever was there (twice:
    two, not four), each with its facts ("6 stanica", "1 stanica · kružni
    set · 4 kruga")."""
    assert _migration(BLOCKS).TEMPLATES == copy.GYM_TEMPLATES
    path = ROOT / "scripts" / "seed_demo.py"
    spec = importlib.util.spec_from_file_location("seed_demo", path)
    seed = importlib.util.module_from_spec(spec); spec.loader.exec_module(seed)
    seed.seed_gym_templates()
    seed.seed_gym_templates()
    assert [(x.title, x.position, [(b.kind, b.slots, b.rounds, b.rest_seconds) for b in x.blocks], x.facts)
            for x in db.gym_templates()] == [
        ("Stanični trening", 1, [("stanica", None, None, None)] * 6, "6 stanica"),
        ("Kružni trening", 2, [("stanica", None, None, None), ("kruzni", 4, 4, None)], "1 stanica · kružni set · 4 kruga")]


# ---------- rule 1: whose and when ----------

def test_the_window_opens_at_the_cancel_deadline_and_closes_at_the_end_of_the_next_day(monkeypatch):
    """gym_window: from the booking's cancel deadline (db.cancel_deadline,
    CANCEL_CUTOFF_HOURS, 4, before the termin's start: the moment the
    booking can no longer be cancelled; since 27.11.2026 one number for
    both, the owner: "connect this 4 hours with the same paremeter which
    decides when the training slot is confirmed and cant be cancelled
    anymore") until the midnight two days after its Zagreb date;
    gym_can_write at each edge (the first moment in, the last moment in,
    the first out); a training outside a termin (or let go of its termin)
    always; staff acting as the member before the window and after it.
    Moving CANCEL_CUTOFF_HOURS moves both, the window's opening and the
    cancellation (a booking 5 h ahead is no longer cancelled at 6, and its
    training is its member's to make; one 7 h ahead still cancels and its
    training is not his yet), and the sentences that say the hours; the
    closing stays. The gym's own knob of 26.11.2026 is nowhere: not in
    config, nor anywhere in the code, the scripts, the tests or DEPLOY.md."""
    start = datetime(2026, 11, 25, 18, 0, tzinfo=config.TZ)                 # a Wednesday
    opens, closes = db.gym_window(start)
    assert (opens, closes) == (datetime(2026, 11, 25, 14, 0, tzinfo=config.TZ),
                               datetime(2026, 11, 27, 0, 0, tzinfo=config.TZ))
    sess = db.TrainingSession(title="Snaga", starts_at=start)
    assert opens == db.cancel_deadline(start) == db.cancel_deadline(sess)   # one rule, a termin's or its start's
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
    assert db.gym_opens_text() == "Trening se otvara 4 h prije termina."
    monkeypatch.setattr(config, "CANCEL_CUTOFF_HOURS", 6)                   # the one knob moves both
    assert db.gym_window(start) == (datetime(2026, 11, 25, 12, 0, tzinfo=config.TZ), closes)
    assert db.cancel_deadline(sess) == datetime(2026, 11, 25, 12, 0, tzinfo=config.TZ)
    assert db.gym_opens_text() == "Trening se otvara 6 h prije termina."
    ivan = make_user("ivan@test.local")
    inside, outside_ = termin(ivan, now() + timedelta(hours=5)), termin(ivan, now() + timedelta(hours=7))
    with pytest.raises(db.BookingError, match="najkasnije 6 h prije termina"):
        db.cancel_booking(ivan, inside)
    assert db.gym_training_for(ivan, inside) > 0                            # confirmed: his training opens
    with pytest.raises(db.BookingError, match="Trening se otvara 6 h prije termina."):
        db.gym_training_for(ivan, outside_)
    db.cancel_booking(ivan, outside_)                                        # not confirmed yet: it cancels
    assert db.roster(outside_) == []
    monkeypatch.undo()
    name = "GYM_" + "OPENS_HOURS"                                            # written so, this file says it nowhere
    assert not hasattr(config, name)
    files = [*(ROOT / "src").rglob("*.py"), *(ROOT / "src").rglob("*.html"), *(ROOT / "scripts").rglob("*.py"),
             *(ROOT / "tests").rglob("*.py"), ROOT / "DEPLOY.md"]
    assert [str(f.relative_to(ROOT)) for f in files if name in f.read_text()] == []


def test_a_member_writes_inside_his_window_and_staff_acting_as_him_at_any_time():
    """A member's training is his alone (another member's 404 on every
    route). After his window every write is refused with "Upis ovog
    treninga je zatvoren — trener ga i dalje može urediti." and changes
    nothing, the page read only ("Upis je zatvoren — …": no card, no form,
    no input, no button). Staff acting as him (the trainer) write after the
    window and before it, the page saying "Za člana je upis zatvoren;
    uređuješ kao trener."."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    db.reset_gym_templates()
    tpl = db.gym_templates()[0].id
    ex = library("Goblet čučanj")
    old = termin(ivan, now() - timedelta(days=3))                          # its window closed
    ahead = termin(ivan, now() + timedelta(hours=6))                        # not open yet
    tid = db.gym_training_for(ivan, old, staff=True)
    bid = station(tid, ivan, ex["Goblet čučanj"], 3, 10, staff=True)
    ci = client_for("ivan@test.local")
    page = ci.get(page_url(tid)).text
    assert '<p class="gt-state"><span class="t">Upis je zatvoren — trener ga i dalje može urediti.</span></p>' in page
    body = page.split("<main")[1].split("</main>")[0]
    for gone in ("<form", "<input", "<button", 'id="glavno"', "pl-timer", "pl-end", 'id="plRest"', "library-json"):
        assert gone not in body, gone
    r = tick(ci, tid, bid, "reps,kg", {"reps": 10, "kg": 20})
    assert (r.status_code, r.json()) == (400, {"ok": False, "error": CLOSED, "mark": "", "done": False})
    for path, data in ((f"/predlozak", {"predlozak": str(tpl)}), ("/blok", {"vrsta": "stanica"}),
                       (f"/blok/{bid}/stanica", {"exercise_id": str(ex["Goblet čučanj"]), "sets": "2"}),
                       (f"/blok/{bid}/ocjena", {"effort": "7"}), (f"/blok/{bid}/obrisi", {}), ("/isprazni", {}),
                       ("/osvrt", {"effort": "7"})):
        r = ci.post(f"/dvoranski/trening/{tid}{path}", data=data, follow_redirects=False)
        assert CLOSED in location(r), path
    [t] = db.gym_trainings(ivan)
    assert [(b.kind, b.item.sets, b.item.done_sets, b.effort) for b in t.blocks] == [("stanica", 3, [], None)]
    assert t.finished_at is None
    ca = client_for("ana@test.local")                                       # another member's: 404 everywhere
    assert ca.get(page_url(tid)).status_code == 404
    assert tick(ca, tid, bid, "reps,kg", {"reps": 10, "kg": 20}).status_code == 404
    for path in ("/osvrt", "/blok", "/isprazni", "/predlozak", f"/blok/{bid}/stanica", f"/blok/{bid}/obrisi",
                 f"/blok/{bid}/ocjena", f"/blok/{bid}/plan", f"/blok/{bid}/krug/1", f"/blok/{bid}/krugovi"):
        assert ca.post(f"/dvoranski/trening/{tid}{path}", data={"effort": "5", "vrsta": "stanica"}).status_code == 404, path

    cs = client_for("coach@test.local")                                     # staff acting as ivan
    assert cs.post(f"/kao/{ivan}", follow_redirects=False).status_code == 303
    page = cs.get(page_url(tid)).text
    assert ('<p class="gt-state"><span class="t">Za člana je upis zatvoren; uređuješ kao trener.</span></p>' in page
            and 'id="glavno"' in page)
    r = tick(cs, tid, bid, "reps,kg", {"reps": 10, "kg": 20}, headers={**JSON, "X-QMT-Kao": str(ivan)})
    assert r.json() == {"ok": True, "error": "", "mark": "1/3", "done": False}
    assert done_of(item_of(bid).id) == [{"reps": 10, "kg": 20.0}]
    r = cs.get(f"/dvoranski/termin/{ahead}", follow_redirects=False)       # before the window: staff may
    assert location(r).startswith("/dvoranski/trening/")
    early = int(location(r).rsplit("/", 1)[1])
    assert "Za člana je upis zatvoren; uređuješ kao trener." in cs.get(page_url(early)).text
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    page = ci.get(page_url(early)).text                                    # the member, before it: rule 2's words
    assert '<p class="gt-state">Trening se otvara 4 h prije termina.</p>' in page and 'id="glavno"' not in page


def test_a_training_outside_a_termin_is_always_its_members():
    """A training outside a termin (POST /dvoranski/trening, the tab's form
    since 27.11.2026, the Karton's until then, leads to its page): no state
    line, every write at any date, its date changed ("promijeni datum",
    read_day's rules), deleted ("Obriši trening", asks first; then the
    karton). A termin's has no date form and is not deleted here (404): it
    goes with its booking."""
    ivan = make_user("ivan@test.local")
    ci = client_for("ivan@test.local")
    r = ci.post("/dvoranski/trening", data={"day": "2021-03-04"}, follow_redirects=False)
    [t] = db.gym_trainings(ivan)
    tid = t.id
    assert location(r) == f"/dvoranski/trening/{tid}"
    page = bare(ci.get(page_url(tid)).text)
    assert "<h1>Trening izvan termina</h1>" in page and 'class="gt-state"' not in page
    assert '<span>četvrtak 4.3.2021.</span>' in page and f'action="/dvoranski/trening/{tid}/datum"' in page
    assert 'data-confirm-title="Obrisati trening?"' in page and "/isprazni" not in page
    r = ci.post(f"/dvoranski/trening/{tid}/blok", data={"vrsta": "stanica"}, follow_redirects=False)
    [b] = db.gym_training(tid, ivan).blocks
    assert location(r) == page_url(tid, blok=b.id)
    r = ci.post(f"/dvoranski/trening/{tid}/datum", data={"day": "2030-01-01"}, follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}?error=Neispravan datum."
    ci.post(f"/dvoranski/trening/{tid}/datum", data={"day": "2021-03-05"})
    assert db.gym_training(tid, ivan).held_on == date(2021, 3, 5)
    other = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    assert ci.post(f"/dvoranski/trening/{other}/datum", data={"day": "2021-03-05"}).status_code == 404
    assert ci.post(f"/dvoranski/trening/{other}/obrisi").status_code == 404
    assert f'action="/dvoranski/trening/{other}/datum"' not in ci.get(page_url(other)).text
    r = ci.post(f"/dvoranski/trening/{tid}/obrisi", follow_redirects=False)
    # back at the tab (27.11.2026: a viewer who has it; the karton for one who has not, tests/test_dvoranski.py)
    assert location(r) == "/dvoranski?ok=Trening je obrisan." and [x.id for x in db.gym_trainings(ivan)] == [other]
    with db.session_scope() as s:                                           # its block went with it
        assert s.scalar(sa_text("SELECT count(*) FROM gym_training_blocks WHERE training_id = :t"), {"t": tid}) == 0


# ---------- rule 2: made lazily ----------

def test_a_termins_training_is_made_the_first_time_it_is_opened():
    """GET /dvoranski/termin/<id> makes the member's training of the termin
    (its title and start snapshotted, held_on its Zagreb date; no block) and
    opens it; again, the same one. Refused, back at his karton with the
    sentence: no booking of his ("Nemaš rezervaciju za ovaj termin."), the
    termin canceled ("Termin je otkazan."), before the window ("Trening se
    otvara 4 h prije termina."), after it ("Upis ovog treninga je
    zatvoren."); one already made opens after the window, read only. A guest
    is sent to log in."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    ci = client_for("ivan@test.local")
    sid = termin(ivan, now() - timedelta(hours=1), title="Snaga")
    r = ci.get(f"/dvoranski/termin/{sid}", follow_redirects=False)
    [t] = db.gym_trainings(ivan)
    assert location(r) == f"/dvoranski/trening/{t.id}" and t.blocks == []
    with db.session_scope() as s:
        sess = s.get(db.TrainingSession, sid)
    assert (t.session_id, t.title, t.starts_at, t.held_on) == (sid, "Snaga", sess.starts_at,
                                                               sess.starts_at.astimezone(config.TZ).date())
    assert location(ci.get(f"/dvoranski/termin/{sid}", follow_redirects=False)) == f"/dvoranski/trening/{t.id}"
    assert len(db.gym_trainings(ivan)) == 1
    theirs = termin(ana, now() - timedelta(hours=1))
    canceled = termin(ivan, now() - timedelta(hours=1))
    db.set_session_canceled(canceled, True)
    for sess_id, sentence in ((theirs, "Nemaš rezervaciju za ovaj termin."), (999999, "Nemaš rezervaciju za ovaj termin."),
                              (canceled, "Termin je otkazan."),
                              (termin(ivan, now() + timedelta(hours=5)), "Trening se otvara 4 h prije termina."),
                              (termin(ivan, now() - timedelta(days=3)), "Upis ovog treninga je zatvoren.")):
        assert location(ci.get(f"/dvoranski/termin/{sess_id}", follow_redirects=False)) == f"/karton?error={sentence}"
    assert len(db.gym_trainings(ivan)) == 1
    later = termin(ivan, now() + timedelta(hours=3, minutes=59))           # the window open: made
    assert location(ci.get(f"/dvoranski/termin/{later}", follow_redirects=False)).startswith("/dvoranski/trening/")
    gone = termin(ivan, now() - timedelta(days=3))                          # made by staff, then read after the window
    tid = db.gym_training_for(ivan, gone, staff=True)
    assert location(ci.get(f"/dvoranski/termin/{gone}", follow_redirects=False)) == f"/dvoranski/trening/{tid}"
    assert "Upis je zatvoren" in ci.get(page_url(tid)).text
    guest = TestClient(app)
    assert guest.get(f"/dvoranski/termin/{sid}", follow_redirects=False).headers["location"].startswith("/login?next=")
    assert guest.get(page_url(t.id), follow_redirects=False).headers["location"].startswith("/login?next=")


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
    it goes, its blocks and items with it (a template applied and an
    exercise chosen but no set ticked is no record); one that holds a
    record (a set saved, or its osvrt) stays, let go of its termin
    (session_id NULL), its title and start as they were, and the karton
    lists it as a training of its own. Another member's training of the
    same termin is untouched."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    db.reset_gym_templates()
    ex = library("Goblet čučanj")
    ci = client_for("ivan@test.local")
    soon = now() + timedelta(hours=5)
    empty_sid, ticked_sid, osvrt_sid = (termin(ivan, soon + timedelta(minutes=k)) for k in (0, 10, 20))
    with db.session_scope() as s:
        s.add(Booking(user_id=ana, session_id=ticked_sid))
    empty, ticked, finished = (db.gym_training_for(ivan, x, staff=True) for x in (empty_sid, ticked_sid, osvrt_sid))
    hers = db.gym_training_for(ana, ticked_sid, staff=True)
    db.apply_gym_template(empty, ivan, db.gym_templates()[1].id, staff=True)
    station(empty, ivan, ex["Goblet čučanj"], 3, 10, staff=True)          # chosen, nothing done
    bid = station(ticked, ivan, ex["Goblet čučanj"], staff=True)
    db.save_gym_done(bid, ivan, [{"reps": 10, "kg": 20.0}], staff=True)
    db.finish_gym_training(finished, ivan, 6, None, "", staff=True)
    for sid in (empty_sid, ticked_sid, osvrt_sid):
        assert location(ci.post(f"/cancel/{sid}", follow_redirects=False)).endswith("ok=Rezervacija je otkazana.")
    left = {t.id: t for t in db.gym_trainings(ivan)}
    assert set(left) == {ticked, finished} and all(t.session_id is None for t in left.values())
    assert left[ticked].title == "Grupni trening" and left[ticked].starts_at is not None
    with db.session_scope() as s:
        for table in ("gym_training_items", "gym_training_blocks"):
            assert s.scalar(sa_text(f"SELECT count(*) FROM {table} WHERE training_id = :t"), {"t": empty}) == 0, table
    assert db.gym_training(hers, ana).session_id == ticked_sid
    page = ci.get("/karton").text
    assert f'id="gt-{ticked}"' in page and f'id="gt-{finished}"' in page
    assert db.gym_can_write(left[ticked])                                   # let go: a training outside a termin now


# ---------- the addresses ----------

def test_the_old_addresses_lead_to_the_new_ones_and_their_writes_are_gone():
    """/karton/termin/<id>/trening, /karton/trening/<id> and its osvrt (the
    pages of 26.11.2026) 303 to /dvoranski/termin/<id>,
    /dvoranski/trening/<id> and its osvrt, the query kept (a guest too,
    who is then sent to log in there); the old writes went (404 or 405),
    nothing changed. POST /karton/trening, the Karton's form, went with
    build 2 (27.11.2026: the tab's POST /dvoranski/trening makes one):
    nothing made."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj")
    sid = termin(ivan, now() - timedelta(hours=1))
    tid = db.gym_training_for(ivan, sid)
    bid = station(tid, ivan, ex["Goblet čučanj"], 3, 10)
    ci = client_for("ivan@test.local")
    for old, new in ((f"/karton/termin/{sid}/trening", f"/dvoranski/termin/{sid}"),
                     (f"/karton/termin/{sid}/trening?a=1&b=2", f"/dvoranski/termin/{sid}?a=1&b=2"),
                     (f"/karton/trening/{tid}", f"/dvoranski/trening/{tid}"),
                     (f"/karton/trening/{tid}?blok={bid}&uredi=1", f"/dvoranski/trening/{tid}?blok={bid}&uredi=1"),
                     (f"/karton/trening/{tid}/osvrt", f"/dvoranski/trening/{tid}/osvrt")):
        for c in (ci, TestClient(app)):
            r = c.get(old, follow_redirects=False)
            assert (r.status_code, r.headers["location"]) == (303, new), old
    assert ci.get(f"/karton/trening/{tid}").url.path == f"/dvoranski/trening/{tid}"
    item = item_of(bid).id
    for path in ("/stavke", f"/stavke/{item}", f"/stavke/{item}/odradeno", f"/stavke/{item}/pomak",
                 f"/stavke/{item}/obrisi", f"/stavke/{item}/vjezba", "/dio/trening", "/dio/trening/krug/1",
                 "/predlozak", "/isprazni", "/datum", "/obrisi", "/osvrt"):
        r = ci.post(f"/karton/trening/{tid}{path}", data={"effort": "7", "polja": "reps,kg", "rows": "1",
                                                          "reps_1": "10", "exercise_id": "1"}, follow_redirects=False)
        assert r.status_code in (404, 405), path
    t = db.gym_training(tid, ivan)
    assert (len(t.blocks), t.finished_at, done_of(item)) == (1, None, [])
    r = ci.post("/karton/trening", data={"day": config.today().isoformat()}, follow_redirects=False)
    assert r.status_code in (404, 405) and [x.id for x in db.gym_trainings(ivan)] == [tid]


# ---------- the blocks' rules (db.py) ----------

def test_a_template_is_applied_only_before_the_first_tick():
    """apply_gym_template: a template's blocks in place of the training's,
    each empty (a Stanica its one item, a Kružni set its rows, its Krug and
    its pause), the template unchanged; again, its blocks replace the
    first's. "Odaberi predložak s popisa." for a template that is none;
    once a set is ticked, "Trening je već započet — predložak se više ne
    može zamijeniti.", nothing changed. The route: the page on its first
    block; refused, at the chooser (?predlozak=1#predlozak)."""
    ivan = make_user("ivan@test.local")
    db.reset_gym_templates()
    stanicni, kruzni = db.gym_templates()
    ex = library("Goblet čučanj")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    assert db.apply_gym_template(tid, ivan, kruzni.id)
    t = db.gym_training(tid, ivan)
    assert [(b.position, b.kind, b.rounds, b.rest_seconds, len(b.items), all(i.is_slot for i in b.items))
            for b in t.blocks] == [(1, "stanica", None, None, 1, True), (2, "kruzni", 4, None, 4, True)]
    db.apply_gym_template(tid, ivan, stanicni.id)
    t = db.gym_training(tid, ivan)
    assert [b.kind for b in t.blocks] == ["stanica"] * 6 and len(t.items) == 6
    with db.session_scope() as s:
        assert s.scalar(sa_text("SELECT count(*) FROM gym_training_items WHERE training_id = :t"), {"t": tid}) == 6
    assert [(x.title, [(b.kind, b.slots, b.rounds) for b in x.blocks]) for x in db.gym_templates()] == [
        ("Stanični trening", [("stanica", None, None)] * 6), ("Kružni trening", [("stanica", None, None), ("kruzni", 4, 4)])]
    for none in (None, 999999):
        with pytest.raises(ValueError, match="^Odaberi predložak s popisa.$"):
            db.apply_gym_template(tid, ivan, none)
    first = t.blocks[0].id
    db.set_gym_station(first, ivan, ex["Goblet čučanj"], 3, 10)
    assert db.apply_gym_template(tid, ivan, kruzni.id)                     # chosen, not ticked: it may still
    first = db.gym_training(tid, ivan).blocks[0].id
    db.set_gym_station(first, ivan, ex["Goblet čučanj"], 3, 10)
    db.save_gym_done(first, ivan, [{"reps": 10, "kg": 20.0}])
    with pytest.raises(ValueError, match="^Trening je već započet — predložak se više ne može zamijeniti.$"):
        db.apply_gym_template(tid, ivan, stanicni.id)
    assert [b.kind for b in db.gym_training(tid, ivan).blocks] == ["stanica", "kruzni"]
    ci = client_for("ivan@test.local")
    r = ci.post(f"/dvoranski/trening/{tid}/predlozak", data={"predlozak": str(stanicni.id)}, follow_redirects=False)
    assert location(r) == (f"/dvoranski/trening/{tid}?predlozak=1&error=Trening je već započet — predložak se više ne "
                           "može zamijeniti.#predlozak")
    other = db.add_gym_outside(ivan, config.today())
    for value in ("", "abc", "999999"):
        r = ci.post(f"/dvoranski/trening/{other}/predlozak", data={"predlozak": value}, follow_redirects=False)
        assert location(r) == f"/dvoranski/trening/{other}?predlozak=1&error=Odaberi predložak s popisa.#predlozak"
    r = ci.post(f"/dvoranski/trening/{other}/predlozak", data={"predlozak": str(kruzni.id)}, follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{other}" and len(db.gym_training(other, ivan).blocks) == 2


def test_blocks_are_added_up_to_forty_and_removed_at_any_time():
    """"+ Stanica" (one empty item) and "+ Kružni set" (four empty rows,
    four Krug, no pause) after the last block, at any time, at most 40
    ("Najviše 40 stanica i kružnih setova."; a kind that is none:
    GYM_CHANGED); the page back on the new one. Any block removed at any
    time, its items and their sets with it ("Stanica je uklonjena.",
    "Kružni set je uklonjen."); another member's 404."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    ex = library("Goblet čučanj")
    tid = db.add_gym_outside(ivan, config.today())
    ci = client_for("ivan@test.local")
    r = ci.post(f"/dvoranski/trening/{tid}/blok", data={"vrsta": "stanica"}, follow_redirects=False)
    [s1] = db.gym_training(tid, ivan).blocks
    assert location(r) == page_url(tid, blok=s1.id)
    assert (s1.position, s1.kind, s1.rounds, len(s1.items), s1.item.is_slot) == (1, "stanica", None, 1, True)
    ci.post(f"/dvoranski/trening/{tid}/blok", data={"vrsta": "kruzni"})
    k = db.gym_training(tid, ivan).blocks[1]
    assert (k.position, k.kind, k.rounds, k.rest_seconds, [i.position for i in k.items], k.holds_exercise) == (
        2, "kruzni", 4, None, [1, 2, 3, 4], False)
    r = ci.post(f"/dvoranski/trening/{tid}/blok", data={"vrsta": "kardio"}, follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}?error={CHANGED}"
    for _ in range(38):
        db.add_gym_block(tid, ivan, "stanica")
    with pytest.raises(ValueError, match="^Najviše 40 stanica i kružnih setova.$"):
        db.add_gym_block(tid, ivan, "kruzni")
    r = ci.post(f"/dvoranski/trening/{tid}/blok", data={"vrsta": "stanica"}, follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}?error=Najviše 40 stanica i kružnih setova."
    assert len(db.gym_training(tid, ivan).blocks) == 40
    assert "/blok\"><input type=\"hidden\" name=\"vrsta\"" not in ci.get(page_url(tid)).text   # not offered at 40
    db.set_gym_station(s1.id, ivan, ex["Goblet čučanj"], 3, 10)
    db.save_gym_done(s1.id, ivan, [{"reps": 10, "kg": 20.0}])
    r = ci.post(f"/dvoranski/trening/{tid}/blok/{s1.id}/obrisi", follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}?ok=Stanica je uklonjena."
    r = ci.post(f"/dvoranski/trening/{tid}/blok/{k.id}/obrisi", follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}?ok=Kružni set je uklonjen."
    assert len(db.gym_training(tid, ivan).blocks) == 38
    with db.session_scope() as s:
        assert s.scalar(sa_text("SELECT count(*) FROM gym_training_items WHERE block_id IN (:a, :b)"),
                        {"a": s1.id, "b": k.id}) == 0
    other = db.gym_training(tid, ivan).blocks[0].id
    assert client_for("ana@test.local").post(f"/dvoranski/trening/{tid}/blok/{other}/obrisi").status_code == 404
    assert not db.delete_gym_block(other, ana)


def test_a_stations_exercise_and_plan_are_one_write():
    """A Stanica's "Kreni" (POST …/blok/<id>/stanica): the exercise, needed
    ("Odaberi vježbu s popisa."; one not in the library "Nepoznata
    vježba."), Serije, Ponavljanja, Opterećenje (kg), Pauza (s), Vrijeme
    (s), Komentar, each optional and within the day editor's limits
    ("Neispravan broj."; the comment 500 characters: "Komentar može imati
    najviše 500 znakova."): back started, the focus in its first set
    (?kreni=1). "Uredi"'s "Spremi" (`uredi`): back, "Spremljeno."; a refusal
    in the card, its form open again. The exercise may change only while no
    set is ticked ("Stanica već ima upisane serije — ukloni je pa dodaj
    novu."), the numbers at any time; a Kružni set's block is no Stanica."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank")
    tid = db.add_gym_outside(ivan, config.today())
    bid = station(tid, ivan)
    ci = client_for("ivan@test.local")

    def save(**form):
        return ci.post(f"/dvoranski/trening/{tid}/blok/{bid}/stanica", data=form, follow_redirects=False)

    for form, sentence in (({"exercise_id": ""}, "Odaberi vježbu s popisa."),
                           ({"exercise_id": "abc"}, "Odaberi vježbu s popisa."),
                           ({"exercise_id": "999999"}, "Nepoznata vježba."),
                           ({"exercise_id": str(ex["Plank"]), "sets": "0"}, "Neispravan broj."),
                           ({"exercise_id": str(ex["Plank"]), "reps": "1000"}, "Neispravan broj."),
                           ({"exercise_id": str(ex["Plank"]), "kg": "2,3"}, "Neispravan broj."),
                           ({"exercise_id": str(ex["Plank"]), "rest": "3601"}, "Neispravan broj."),
                           ({"exercise_id": str(ex["Plank"]), "seconds": "0"}, "Neispravan broj."),
                           ({"exercise_id": str(ex["Plank"]), "note": "x" * 501},
                            "Komentar može imati najviše 500 znakova.")):
        assert location(save(**form)) == f"/dvoranski/trening/{tid}?blok={bid}&error={sentence}#glavno", form
    assert item_of(bid).is_slot
    r = save(exercise_id=str(ex["Goblet čučanj"]), sets="6", reps="10", kg="40", rest="90", seconds="", note=" Polako. ")
    assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&kreni=1#glavno"
    it = item_of(bid)
    assert (it.exercise_id, it.exercise_name, it.sets, it.reps, it.kg, it.rest_seconds, it.seconds, it.note) == (
        ex["Goblet čučanj"], "Goblet čučanj", 6, 10, Decimal("40.0"), 90, None, "Polako.")
    assert it.asked == "6 × 10 · 40 kg · pauza 90 s"
    db.set_gym_station(bid, ivan, ex["Plank"], 3, None, 30)                 # no tick: the exercise may change
    assert (item_of(bid).exercise_name, item_of(bid).asked) == ("Plank", "3 × 30 s")
    db.save_gym_done(bid, ivan, [{"seconds": 30}])
    with pytest.raises(ValueError, match="^Stanica već ima upisane serije — ukloni je pa dodaj novu.$"):
        db.set_gym_station(bid, ivan, ex["Goblet čučanj"], 3, None, 30)
    r = save(exercise_id=str(ex["Goblet čučanj"]), seconds="30", uredi="1")
    assert location(r) == (f"/dvoranski/trening/{tid}?blok={bid}&uredi=1&error=Stanica već ima upisane serije — "
                           "ukloni je pa dodaj novu.#glavno")
    for form in ({"exercise_id": str(ex["Plank"])}, {"exercise_id": ""}):   # its own, or none: kept, the numbers changed
        r = save(**form, sets="4", seconds="45", note="Ravna leđa.", uredi="1")
        assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&ok=Spremljeno.#glavno"
    it = item_of(bid)
    assert (it.exercise_name, it.sets, it.seconds, it.note, it.done_sets) == ("Plank", 4, 45, "Ravna leđa.", [{"seconds": 30}])
    k, _ = circuit(tid, ivan)
    with pytest.raises(ValueError, match=f"^{CHANGED}$"):
        db.set_gym_station(k, ivan, ex["Plank"])
    other = db.add_gym_outside(ivan, config.today())
    assert ci.post(f"/dvoranski/trening/{other}/blok/{bid}/stanica", data={"exercise_id": "1"}).status_code == 404


def test_a_tick_saves_the_ticked_rows_whole():
    """POST …/blok/<id>/odradeno, as the page's script posts it (Accept
    JSON: {"ok", "error", "mark", "done"}): a Stanica's ticked rows saved
    whole; a tick more, an untick, a ticked row's number changed: each the
    list as it is then; none ticked, nothing done. Each shape as what was
    asked makes it (PON. · KG, SEK., PON. · SEK.). Its first save's time is
    kept while a set stays saved (the page's clock). Refused, 400, nothing
    changed: 21 sets, a number that is none or out of range, a page drawn
    for another shape, a ticked row with no number ("Upiši broj pa označi
    seriju."), an empty Stanica ("Nepoznata vježba."), a Kružni set's block
    (CHANGED). Without JS the table's "Spremi" posts every row and comes
    back at the station, its word in it."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank", "Mrtvi kukac")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    goblet = station(tid, ivan, ex["Goblet čučanj"], 3, 10, kg=20, rest=60)
    plank = station(tid, ivan, ex["Plank"], 2, seconds=30)
    bug = station(tid, ivan, ex["Mrtvi kukac"], 2, 5, 30)
    empty = station(tid, ivan)
    ci = client_for("ivan@test.local")
    r = tick(ci, tid, goblet, "reps,kg", {"reps": 10, "kg": 20})
    assert (r.status_code, r.json()) == (200, {"ok": True, "error": "", "mark": "1/3", "done": False})
    first = item_of(goblet).done_at
    assert done_of(item_of(goblet).id) == [{"reps": 10, "kg": 20.0}] and first is not None
    r = tick(ci, tid, goblet, "reps,kg", {"reps": 10, "kg": 20}, {"reps": 9, "kg": "22,5"})
    assert r.json()["mark"] == "2/3" and item_of(goblet).done_at == first                # its first save's time kept
    r = tick(ci, tid, goblet, "reps,kg", {"reps": 9, "kg": "22.5"})                       # the first unticked
    assert r.json()["mark"] == "1/3" and done_of(item_of(goblet).id) == [{"reps": 9, "kg": 22.5}]
    r = tick(ci, tid, goblet, "reps,kg", *[{"reps": 10, "kg": 20}] * 3)
    assert r.json() == {"ok": True, "error": "", "mark": "✓", "done": True}
    r = tick(ci, tid, goblet, "reps,kg")                                                  # the last unticked
    assert r.json() == {"ok": True, "error": "", "mark": "", "done": False} and item_of(goblet).done_at is None
    assert tick(ci, tid, plank, "seconds", {"sec": 30}, {"sec": 35}).json()["mark"] == "✓"
    assert done_of(item_of(plank).id) == [{"seconds": 30}, {"seconds": 35}]
    assert tick(ci, tid, bug, "reps,seconds", {"reps": 5, "sec": 30}).json()["mark"] == "1/2"
    assert done_of(item_of(bug).id) == [{"reps": 5, "seconds": 30}]
    for polja, rows, sentence in (("seconds", [{"sec": 30}] * 21, "Najviše 20 serija."),
                                  ("seconds", [{"sec": "abc"}], "Neispravan broj."),
                                  ("seconds", [{"sec": "3601"}], "Neispravan broj."),
                                  ("seconds", [{"sec": "-5"}], "Neispravan broj."),
                                  ("reps,kg", [{"reps": 10, "kg": 20}], CHANGED),
                                  ("seconds", [{"sec": ""}], "Upiši broj pa označi seriju."),
                                  ("seconds", [{"sec": 30}, {"sec": " "}], "Upiši broj pa označi seriju.")):
        r = tick(ci, tid, plank, polja, *rows)
        assert (r.status_code, r.json()) == (400, {"ok": False, "error": sentence, "mark": "", "done": False}), rows[:1]
    assert done_of(item_of(plank).id) == [{"seconds": 30}, {"seconds": 35}]
    assert tick(ci, tid, goblet, "reps,kg", {"reps": 10, "kg": ""}).json()["ok"]         # one number is a set
    assert done_of(item_of(goblet).id) == [{"reps": 10, "kg": 0.0}]
    assert tick(ci, tid, plank, "seconds", *[{"sec": 30}] * 20).json()["mark"] == "✓"    # twenty: the most
    r = tick(ci, tid, empty, "reps,kg", {"reps": 10, "kg": 20})
    assert (r.status_code, r.json()["error"]) == (400, "Nepoznata vježba.")
    k, _ = circuit(tid, ivan, [(ex["Plank"], None, None, 30)])
    assert tick(ci, tid, k, "seconds", {"sec": 30}).json()["error"] == CHANGED
    other = db.add_gym_outside(ivan, config.today())
    assert tick(ci, other, goblet, "reps,kg", {"reps": 10, "kg": 20}).status_code == 404
    # without JS: "Spremi" posts every row; the ones that hold a number are what was done
    r = ci.post(f"/dvoranski/trening/{tid}/blok/{goblet}/odradeno",
                data={"polja": "reps,kg", "rows": "3", "reps_1": "10", "kg_1": "20", "reps_2": "8", "kg_2": "20",
                      "reps_3": "", "kg_3": ""}, follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}?blok={goblet}&ok=Spremljeno.#glavno"
    assert done_of(item_of(goblet).id) == [{"reps": 10, "kg": 20.0}, {"reps": 8, "kg": 20.0}]
    card = main_card(ci.get(page_url(tid, blok=goblet, ok="Spremljeno.")).text)
    assert '<div class="alert ok" role="status">Spremljeno.</div>' in card
    r = ci.post(f"/dvoranski/trening/{tid}/blok/{goblet}/odradeno",
                data={"polja": "reps,kg", "rows": "1", "reps_1": "abc", "kg_1": "20"}, follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}?blok={goblet}&error=Neispravan broj.#glavno"


def test_a_circuits_rows_and_plan_are_one_write():
    """A Kružni set's rows and plan (POST …/blok/<id>/plan, db.
    save_gym_circuit): each row's exercise (or none: an empty row is let
    be), reps, kg and seconds, Krugova (1–20) and its pause after a Krug
    (0–3600 or none), in one write; "Kreni" opens Krug 1 (?krug=1), "+
    vježba" saves and adds a row (?red=<id>, at most 12: "Najviše 12 vježbi
    u kružnom setu."), a row's ✕ saves the rest and then removes it (what
    was typed in that row goes with it; a refused save removes nothing),
    "Uredi"'s
    "Spremi" says "Spremljeno.". Refused, its sentence in the card, the
    form open again (?uredi=1), nothing changed: a number out of range
    ("Neispravan broj."), an exercise not in the library ("Nepoznata
    vježba."), a page drawn for other rows (CHANGED); once a Krug is saved
    a row that holds a set keeps its exercise (CHANGED) and the Krug never
    go below a saved one ("Zadnji krug je već upisan — ne može se
    ukloniti."), its numbers changing at any time."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Sklekovi", "Plank", "Mrtvi kukac")
    tid = db.add_gym_outside(ivan, config.today())
    bid, (r1, r2, r3, r4) = circuit(tid, ivan)
    ci = client_for("ivan@test.local")
    full = {r1: (ex["Goblet čučanj"], 10, "16", None), r2: (ex["Sklekovi"], 12, None, None), r3: (ex["Plank"], None, None, 30),
            r4: (None, None, None, None)}
    r = plan(ci, tid, bid, full, rounds="3", rest="90", kreni="1")
    assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&krug=1#glavno"
    b = block(bid)
    assert (b.rounds, b.rest_seconds) == (3, 90)
    assert [(it.exercise_name, it.reps, it.kg, it.seconds, it.is_slot) for it in b.items] == [
        ("Goblet čučanj", 10, Decimal("16.0"), None, False), ("Sklekovi", 12, None, None, False),
        ("Plank", None, None, 30, False), ("", None, None, None, True)]
    for rows, rounds, rest, sentence in ((full, "0", "", "Neispravan broj."), (full, "21", "", "Neispravan broj."),
                                         (full, "", "", "Neispravan broj."), (full, "3", "3601", "Neispravan broj."),
                                         ({**full, r1: (ex["Goblet čučanj"], 1000, None, None)}, "3", "", "Neispravan broj."),
                                         ({**full, r1: (999999, 10, None, None)}, "3", "", "Nepoznata vježba."),
                                         ({r1: full[r1], r2: full[r2]}, "3", "", CHANGED)):
        r = plan(ci, tid, bid, rows, rounds=rounds, rest=rest)
        assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&uredi=1&error={sentence}#glavno", sentence
    assert (block(bid).rounds, block(bid).items[0].reps) == (3, 10)
    r = plan(ci, tid, bid, full, rounds="3", rest="90", dodaj="1")
    new = block(bid).items[-1].id
    assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&uredi=1&red={new}#red-{new}" and len(block(bid).items) == 5
    r = plan(ci, tid, bid, {**full, r1: (ex["Goblet čučanj"], 1000, None, None), new: (None, None, None, None)},
             rounds="3", rest="90", ukloni=str(r4))
    assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&uredi=1&error=Neispravan broj.#glavno"
    assert [it.id for it in block(bid).items] == [r1, r2, r3, r4, new]
    r = plan(ci, tid, bid, {**full, r4: (None, 1000, None, None), new: (None, None, None, None)}, rounds="3", rest="90",
             ukloni=str(r4))
    assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&uredi=1#glavno"
    assert [it.id for it in block(bid).items] == [r1, r2, r3, new]
    for _ in range(8):
        db.add_gym_row(bid, ivan)
    with pytest.raises(ValueError, match="^Najviše 12 vježbi u kružnom setu.$"):
        db.add_gym_row(bid, ivan)
    rows12 = {it.id: (None, None, None, None) for it in block(bid).items} | {r1: full[r1], r2: full[r2], r3: full[r3]}
    r = plan(ci, tid, bid, rows12, rounds="3", dodaj="1")
    assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&uredi=1&error=Najviše 12 vježbi u kružnom setu.#glavno"
    for extra in [it.id for it in block(bid).items][4:]:
        db.delete_gym_row(extra, ivan)
    keep = {r1: full[r1], r2: full[r2], r3: full[r3], new: (None, None, None, None)}
    db.save_gym_round(bid, ivan, 1, {r1: {"reps": 10, "kg": 16.0}, r2: {"reps": 12, "kg": 0.0}, r3: {"seconds": 30}})
    db.save_gym_round(bid, ivan, 2, {r1: {"reps": 10, "kg": 16.0}, r2: None, r3: {"seconds": 30}})
    r = plan(ci, tid, bid, {**keep, r1: (ex["Mrtvi kukac"], 10, None, None)}, rounds="3")
    assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&uredi=1&error={CHANGED}#glavno"
    r = plan(ci, tid, bid, keep, rounds="1")
    assert location(r) == (f"/dvoranski/trening/{tid}?blok={bid}&uredi=1&error=Zadnji krug je već upisan — ne može se "
                           "ukloniti.#glavno")
    r = plan(ci, tid, bid, {**keep, r1: (ex["Goblet čučanj"], 8, "18", None), new: (ex["Mrtvi kukac"], 5, None, 30)},
             rounds="2", rest="60")
    assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&ok=Spremljeno.#glavno"
    b = block(bid)
    assert (b.rounds, b.rest_seconds, b.items[0].reps, b.items[0].kg, b.items[3].exercise_name) == (2, 60, 8,
                                                                                                    Decimal("18.0"),
                                                                                                    "Mrtvi kukac")
    assert db.delete_gym_row(r2, ivan) and [it.id for it in block(bid).items] == [r1, r3, new]   # its sets with it
    s = station(tid, ivan)
    with pytest.raises(ValueError, match=f"^{CHANGED}$"):
        db.delete_gym_row(item_of(s).id, ivan)
    with pytest.raises(ValueError, match=f"^{CHANGED}$"):
        db.add_gym_row(s, ivan)


def test_krug_plus_and_minus():
    """"+ krug" one more, to 20; "− krug" the last one less, to 1, never a
    saved one ("Zadnji krug je već upisan — ne može se ukloniti."); past
    either end "Neispravan broj."; a Stanica has none (CHANGED). Back at
    the set, the word in its card."""
    ivan = make_user("ivan@test.local")
    ex = library("Plank")
    tid = db.add_gym_outside(ivan, config.today())
    bid, rows = circuit(tid, ivan, [(ex["Plank"], None, None, 30)], rounds=2)
    ci = client_for("ivan@test.local")

    def press(smjer):
        return ci.post(f"/dvoranski/trening/{tid}/blok/{bid}/krugovi", data={"smjer": smjer}, follow_redirects=False)

    assert location(press("plus")) == f"/dvoranski/trening/{tid}?blok={bid}#glavno" and block(bid).rounds == 3
    for _ in range(17):
        db.set_gym_rounds(bid, ivan, 1)
    assert block(bid).rounds == 20
    assert location(press("plus")) == f"/dvoranski/trening/{tid}?blok={bid}&error=Neispravan broj.#glavno"
    for _ in range(19):
        press("minus")
    assert block(bid).rounds == 1
    assert location(press("minus")) == f"/dvoranski/trening/{tid}?blok={bid}&error=Neispravan broj.#glavno"
    db.save_gym_round(bid, ivan, 1, {rows[0]: {"seconds": 30}})
    press("plus")
    db.save_gym_round(bid, ivan, 2, {rows[0]: {"seconds": 30}})
    assert location(press("minus")) == (f"/dvoranski/trening/{tid}?blok={bid}&error=Zadnji krug je već upisan — ne može "
                                        "se ukloniti.#glavno")
    assert block(bid).rounds == 2
    assert location(press("lijevo")) == f"/dvoranski/trening/{tid}?blok={bid}&error={CHANGED}#glavno"
    s = station(tid, ivan)
    with pytest.raises(ValueError, match=f"^{CHANGED}$"):
        db.set_gym_rounds(s, ivan, 1)


def test_a_krug_is_saved_whole_and_corrected():
    """"Krug 1 odrađen" (POST …/blok/<id>/krug/1): every row of the set
    with an input its set of the Krug, carrying its round, in one write;
    back at it (?spremljen=1#krug-<b>-1), the pause after a Krug at load
    (?odmor=90: a first save's alone). The page: Krug 1 under its ✓, open,
    its inputs as saved and "Spremi izmjene"; Krug 2 open under it, its
    first values Krug 1's. "Spremi izmjene" (a correction, during the
    pause: no ?odmor) replaces Krug 1 alone, and Krug 2's first values
    follow it. A row left empty in a Krug loses its set of that Krug.
    Refused at that Krug, open, its sentence in it, nothing saved: nothing
    typed ("Upiši bar jednu vježbu."), a bad number, a Krug past its Krug
    or a page drawn for other rows (CHANGED). No rating is written: the
    block holds it."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank", "Mrtvi kukac")
    tid = db.add_gym_outside(ivan, config.today())
    bid, (g, p, m, empty) = circuit(tid, ivan, [(ex["Goblet čučanj"], 10, 16, None), (ex["Plank"], None, None, 30),
                                                (ex["Mrtvi kukac"], 5, None, 30)], rounds=3, rest=90)
    ci = client_for("ivan@test.local")
    page = ci.get(page_url(tid, blok=bid, krug=1)).text
    one = page.split(f'id="krug-{bid}-1"')[1].split("</details>")[0]
    assert f'name="stavke" value="{g},{p},{m}"' in one and f"_{empty}" not in one         # an empty row is in no round
    assert (f'name="reps_{g}" value="10"' in one and f'name="kg_{g}" value="16"' in one and f'name="sec_{p}" value="30"'
            in one and f'name="reps_{m}" value="5"' in one and f'name="sec_{m}" value="30"' in one)
    assert '<span>Krug 1 <span class="t">odrađen</span></span>' in one

    r = krug(ci, tid, bid, 1, {g: {"reps": 10, "kg": "16"}, p: {"sec": 30}, m: {"reps": 5, "sec": 30}})
    assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&spremljen=1&odmor=90#krug-{bid}-1"
    assert (done_of(g), done_of(p), done_of(m)) == ([{"reps": 10, "kg": 16.0, "round": 1}], [{"seconds": 30, "round": 1}],
                                                    [{"reps": 5, "seconds": 30, "round": 1}])
    assert block(bid).effort is None
    page = ci.get(page_url(tid, blok=bid, spremljen=1, odmor=90)).text
    assert f'data-odmor="90"' in page
    assert re.findall(rf'<details class="gt-kr" id="krug-{bid}-(\d)"( open)?>', page) == [("1", " open"), ("2", " open")]
    one = page.split(f'id="krug-{bid}-1"')[1].split("</details>")[0]
    assert ('<span class="gt-kr-ok" role="img" aria-label="spremljeno">✓</span><span class="gt-kr-line">· 10 × 16 kg · '
            '30 s · 5 × 30 s</span>') in one
    assert '<button type="submit" class="btn-ghost btn-sm"><span class="t">Spremi izmjene</span></button>' in one
    # a correction during the pause: Krug 1 alone, no pause again; Krug 2 starts from it
    r = krug(ci, tid, bid, 1, {g: {"reps": 8, "kg": "16"}, p: {"sec": 25}, m: {"reps": 5, "sec": 30}})
    assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&spremljen=1#krug-{bid}-1"
    assert done_of(g) == [{"reps": 8, "kg": 16.0, "round": 1}]
    two = ci.get(page_url(tid, blok=bid)).text.split(f'id="krug-{bid}-2"')[1].split("</details>")[0]
    assert f'name="reps_{g}" value="8"' in two and f'name="sec_{p}" value="25"' in two
    krug(ci, tid, bid, 2, {g: {"reps": 8, "kg": "18"}, p: {"sec": ""}, m: {"reps": "", "sec": ""}})
    assert done_of(g)[1] == {"reps": 8, "kg": 18.0, "round": 2} and len(done_of(p)) == 1
    krug(ci, tid, bid, 1, {g: {"reps": 8, "kg": "16"}, p: {"sec": ""}, m: {"reps": 5, "sec": 30}})   # p left empty in Krug 1
    assert done_of(p) == []
    with db.session_scope() as s:
        assert s.get(GymTrainingItem, p).done_at is None
    before = [done_of(x) for x in (g, p, m)]
    for n, by_item, stavke, sentence in (
            (3, {g: {"reps": "", "kg": ""}, p: {"sec": ""}, m: {"reps": "", "sec": ""}}, None, "Upiši bar jednu vježbu."),
            (3, {g: {"reps": "abc", "kg": "16"}, p: {"sec": ""}, m: {"reps": "", "sec": ""}}, None, "Neispravan broj."),
            (3, {g: {"reps": 10, "kg": "16,3"}, p: {"sec": ""}, m: {"reps": "", "sec": ""}}, None, "Neispravan broj."),
            (4, {g: {"reps": 10, "kg": "16"}, p: {"sec": ""}, m: {"reps": "", "sec": ""}}, None, CHANGED),
            (3, {g: {"reps": 10, "kg": "16"}, p: {"sec": ""}}, [g, p], CHANGED)):
        r = krug(ci, tid, bid, n, by_item, stavke)
        assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&krug={n}&error={sentence}#krug-{bid}-{n}", sentence
    assert [done_of(x) for x in (g, p, m)] == before
    page = ci.get(page_url(tid, blok=bid, krug=3, error="Upiši bar jednu vježbu.")).text
    three = page.split(f'id="krug-{bid}-3"')[1].split("</details>")[0]
    assert '<div class="alert" role="alert"><span>Upiši bar jednu vježbu.</span></div>' in three
    assert page.count('<div class="alert" role="alert">') == 1
    krug(ci, tid, bid, 3, {g: {"reps": 8, "kg": "18"}, p: {"sec": 30}, m: {"reps": 5, "sec": 30}})
    assert block(bid).done and block(bid).effort is None


def test_the_ratings_are_one_per_block():
    """A block's rating (POST …/blok/<id>/ocjena, its own small write): 1–10
    or none ("Neispravan broj." otherwise), a Stanica's at any time
    (JSON for the page's script, a plain form back at the block), a Kružni
    set's offered once its last Krug is saved ("Koliko je bio težak ovaj
    kružni set?"); none per Krug."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank")
    tid = db.add_gym_outside(ivan, config.today())
    s = station(tid, ivan, ex["Goblet čučanj"], 3, 10)
    ci = client_for("ivan@test.local")
    r = ci.post(f"/dvoranski/trening/{tid}/blok/{s}/ocjena", data={"effort": "8"}, headers=JSON)
    assert (r.status_code, r.json()) == (200, {"ok": True, "error": ""}) and block(s).effort == 8
    for bad in ("0", "11", "x"):
        r = ci.post(f"/dvoranski/trening/{tid}/blok/{s}/ocjena", data={"effort": bad}, headers=JSON)
        assert (r.status_code, r.json()) == (400, {"ok": False, "error": "Neispravan broj."}), bad
    r = ci.post(f"/dvoranski/trening/{tid}/blok/{s}/ocjena", data={"effort": "6"}, follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}?blok={s}&ok=Spremljeno.#glavno" and block(s).effort == 6
    assert db.rate_gym_block(s, ivan, None) and block(s).effort is None
    db.rate_gym_block(s, ivan, 7)
    card = main_card(ci.get(page_url(tid, blok=s)).text)
    assert ('<form class="gt-rate pl-rate" method="post" action="/dvoranski/trening/%d/blok/%d/ocjena">' % (tid, s)) in card
    assert '<span class="t">Koliko je bilo teško?</span>' in card and card.count('name="effort"') == 10
    assert 'value="7" checked' in card
    k, rows = circuit(tid, ivan, [(ex["Plank"], None, None, 30)], rounds=2)
    db.save_gym_round(k, ivan, 1, {rows[0]: {"seconds": 30}})
    assert "gt-rate" not in main_card(ci.get(page_url(tid, blok=k)).text)          # Krug 2 not saved yet
    db.save_gym_round(k, ivan, 2, {rows[0]: {"seconds": 30}})
    card = main_card(ci.get(page_url(tid, blok=k)).text)
    assert '<span class="t">Koliko je bio težak ovaj kružni set?</span>' in card and card.count('name="effort"') == 10
    assert block(k).effort is None                                                  # saving a Krug rates nothing


def test_done_blocks_and_the_record_leave_empty_blocks_out():
    """A Stanica is done when every planned set is ticked (with no Serije
    given, any); a Kružni set when every Krug is saved. The record (the
    diary's lines, "3 vježbe", holds_anything) holds the blocks that hold
    an exercise: a Stanica's line ("Goblet čučanj: zadano 2 × 10 · 20 kg —
    odrađeno 10 × 20 kg · 10 × 20 kg · težina 8/10"), a Kružni set's own
    ("Kružni set · 2 kruga · težina 7/10") and its exercises under it; an
    empty block is in none, and stays on the page (never deleted for
    that)."""
    ivan = make_user("ivan@test.local")
    db.reset_gym_templates()
    ex = library("Goblet čučanj", "Plank", "Sklekovi")
    tid = db.add_gym_outside(ivan, config.today())
    db.apply_gym_template(tid, ivan, db.gym_templates()[1].id)              # a Stanica and a Kružni set, empty
    t = db.gym_training(tid, ivan)
    assert (t.holds_anything, t.lines(), t.count_text, t.record_blocks) == (False, [], "0 vježbi", [])
    s, k = t.blocks
    db.set_gym_station(s.id, ivan, ex["Goblet čučanj"], 2, 10, kg=20)
    db.save_gym_done(s.id, ivan, [{"reps": 10, "kg": 20.0}])
    assert (block(s.id).done, block(s.id).mark) == (False, "1/2")
    db.save_gym_done(s.id, ivan, [{"reps": 10, "kg": 20.0}] * 2)
    db.rate_gym_block(s.id, ivan, 8)
    assert (block(s.id).done, block(s.id).mark) == (True, "✓")
    any_ = station(tid, ivan, ex["Sklekovi"])                               # no Serije given: any set
    db.save_gym_done(any_, ivan, [{"reps": 12, "kg": 0.0}])
    assert block(any_).done
    rows = {it.id: {"exercise_id": None, "reps": None, "kg": None, "seconds": None} for it in k.items}
    rows[k.items[0].id] = {"exercise_id": ex["Plank"], "reps": None, "kg": None, "seconds": 30}
    db.save_gym_circuit(k.id, ivan, rows, 2, None)
    db.save_gym_round(k.id, ivan, 1, {k.items[0].id: {"seconds": 30}})
    assert not block(k.id).done
    db.save_gym_round(k.id, ivan, 2, {k.items[0].id: {"seconds": 35}})
    db.rate_gym_block(k.id, ivan, 7)
    assert (block(k.id).done, block(k.id).mark) == (True, "✓")
    station(tid, ivan)                                                      # empty, after them
    t = db.gym_training(tid, ivan)
    assert [tuple(ln) for ln in t.lines()] == [
        ("Goblet čučanj", "zadano 2 × 10 · 20 kg — odrađeno", ["10 × 20 kg", "10 × 20 kg", "težina 8/10"], ""),
        ("Kružni set · 2 kruga", "", ["težina 7/10"], "set"),
        ("Plank", "zadano 30 s — odrađeno", ["30 s", "35 s"], "in"),
        ("Sklekovi", "odrađeno", ["12"], "")]
    assert t.count_text == "3 vježbe" and t.holds_anything and len(t.blocks) == 4
    assert [b.id for b in t.record_blocks] == [s.id, k.id, any_]


def test_isprazni_trening_takes_every_block():
    """"Isprazni trening" (a termin's, it asks first): every block and its
    sets go, the training and its osvrt stay, its page the chooser again."""
    ivan = make_user("ivan@test.local")
    db.reset_gym_templates()
    ex = library("Goblet čučanj")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    s = station(tid, ivan, ex["Goblet čučanj"], 3, 10)
    circuit(tid, ivan, [(ex["Goblet čučanj"], 10, None, None)])
    db.save_gym_done(s, ivan, [{"reps": 10, "kg": 20.0}])
    db.finish_gym_training(tid, ivan, 6, "dobro", "Dobro je.")
    ci = client_for("ivan@test.local")
    page = ci.get(page_url(tid)).text
    assert (f'<form method="post" action="/dvoranski/trening/{tid}/isprazni"\n'
            '              data-confirm-title="Isprazniti trening?"\n'
            '              data-confirm="Sve vježbe i upisane serije ovog treninga se brišu."\n'
            '              data-confirm-cta="Isprazni">') in page
    assert f'action="/dvoranski/trening/{tid}/obrisi"' not in page          # a termin's goes with its booking
    r = ci.post(f"/dvoranski/trening/{tid}/isprazni", follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}?ok=Trening je ispražnjen."
    t = db.gym_training(tid, ivan)
    assert t.blocks == [] and (t.effort, t.feeling, t.note) == (6, "dobro", "Dobro je.") and t.finished_at is not None
    with db.session_scope() as s_:
        assert s_.scalar(sa_text("SELECT count(*) FROM gym_training_items WHERE training_id = :t"), {"t": tid}) == 0
    page = ci.get(page_url(tid)).text
    assert "/isprazni" not in page and 'class="card pl-card gt-chooser"' in page


# ---------- the races ----------

def _race(n: int, work) -> list[str]:
    """`work(k)` in n threads at the same moment: the errors."""
    errors, gate = [], threading.Barrier(n)

    def run(k):
        try:
            gate.wait()
            work(k)
        except Exception as e:                                              # reported by the caller
            errors.append(repr(e))

    threads = [threading.Thread(target=run, args=(k,)) for k in range(n)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    return errors


def test_two_ticks_at_once_keep_both():
    """Eight stations of one training ticked at the same moment (eight
    threads; each save takes the training's row FOR UPDATE), three times:
    every station holds what was ticked of it, none lost."""
    ivan = make_user("ivan@test.local")
    eid = db.create_exercise("Goblet čučanj")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    blocks = [station(tid, ivan, eid, 3, 10) for _ in range(8)]
    for times in (1, 2, 3):
        assert not _race(8, lambda k, times=times: db.save_gym_done(blocks[k], ivan,
                                                                     [{"reps": k + 1, "kg": float(times)}] * times))
        assert [done_of(item_of(b).id) for b in blocks] == [[{"reps": k + 1, "kg": float(times)}] * times for k in range(8)]


def test_two_rounds_at_once_keep_both():
    """Eight Krug of one Kružni set saved at the same moment (eight threads,
    a Krug each; save_gym_round takes the training's row FOR UPDATE),
    twice: every row holds a set of every Krug, none lost, sorted by
    round."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    bid, (a, b, *_) = circuit(tid, ivan, [(ex["Goblet čučanj"], 10, 16, None), (ex["Plank"], None, None, 30)], rounds=8)
    for times in (1, 2):
        assert not _race(8, lambda k, times=times: db.save_gym_round(bid, ivan, k + 1, {
            a: {"reps": k + 1 + times, "kg": 16.0}, b: {"seconds": 31 + k}}))
        assert done_of(a) == [{"reps": n + times, "kg": 16.0, "round": n} for n in range(1, 9)]
        assert done_of(b) == [{"seconds": 30 + n, "round": n} for n in range(1, 9)]


def test_two_adds_at_once_take_two_places():
    """Eight "+ Stanica" / "+ Kružni set" of one training at the same moment
    (add_gym_block under the training's row lock), three times: eight
    blocks more each time, every one its own place, none lost; at the cap
    the race adds no 41st."""
    ivan = make_user("ivan@test.local")
    tid = db.add_gym_outside(ivan, config.today())
    for times in (1, 2, 3):
        assert not _race(8, lambda k: db.add_gym_block(tid, ivan, "kruzni" if k % 2 else "stanica"))
        positions = [b.position for b in db.gym_training(tid, ivan).blocks]
        assert len(positions) == 8 * times and len(set(positions)) == len(positions)
    for _ in range(14):
        db.add_gym_block(tid, ivan, "stanica")
    errors = _race(4, lambda k: db.add_gym_block(tid, ivan, "stanica"))
    assert len(db.gym_training(tid, ivan).blocks) == 40 and len(errors) == 2
    assert all("Najviše 40 stanica i kružnih setova." in e for e in errors)


def test_a_template_against_a_tick_one_wins_whole():
    """A template applied while a tick of the training's station is saved
    (two threads, the training's row FOR UPDATE in both), twenty times:
    either the tick won and the template was refused ("Trening je već
    započet …", the ticked station still there with its set), or the
    template won and the tick found its station gone (False), the
    training the template's blocks, no set anywhere. Never a ticked set in
    a replaced block left behind, never a template over a tick."""
    ivan = make_user("ivan@test.local")
    db.reset_gym_templates()
    stanicni = db.gym_templates()[0].id
    eid = db.create_exercise("Goblet čučanj")
    seen = set()
    for _ in range(20):
        tid = db.add_gym_outside(ivan, config.today())
        bid = station(tid, ivan, eid, 3, 10)
        got = {}

        def work(k, tid=tid, bid=bid, got=got):
            if k == 0:
                got["tick"] = db.save_gym_done(bid, ivan, [{"reps": 10, "kg": 20.0}])
            else:
                try:
                    got["template"] = db.apply_gym_template(tid, ivan, stanicni)
                except ValueError as e:
                    got["template"] = str(e)

        assert not _race(2, work)
        t = db.gym_training(tid, ivan)
        if got["template"] is True:
            assert got["tick"] is False and [b.kind for b in t.blocks] == ["stanica"] * 6 and not t.ticked
            assert bid not in [b.id for b in t.blocks]
            seen.add("template")
        else:
            assert got["template"] == "Trening je već započet — predložak se više ne može zamijeniti."
            assert got["tick"] is True and [b.id for b in t.blocks] == [bid] and t.ticked
            seen.add("tick")
        with db.session_scope() as s:
            orphans = s.scalar(sa_text("SELECT count(*) FROM gym_training_items i LEFT JOIN gym_training_blocks b "
                                       "ON b.id = i.block_id WHERE i.training_id = :t AND b.id IS NULL"), {"t": tid})
            assert orphans == 0
    assert seen                                                             # (which wins is the scheduler's)


# ---------- rules 5, 6, 7, 8 ----------

def test_a_gym_training_has_no_load_next_time():
    """Rule 5: a rated gym exercise changes nothing next time. A new
    station's rows are what was asked (none asked: empty), never last
    time's weights or an adjusted one, no "Prošli put" line; next_load
    reads the online passes alone."""
    ivan = make_user("ivan@test.local")
    eid = db.create_exercise("Goblet čučanj")
    first = db.gym_training_for(ivan, termin(ivan, now() - timedelta(days=1)), staff=True)
    bid = station(first, ivan, eid, 3, 10, kg=20, staff=True)
    db.save_gym_done(bid, ivan, [{"reps": 10, "kg": 20.0}] * 3, staff=True)
    db.rate_gym_block(bid, ivan, 2, staff=True)                             # easy: online would add 5 %
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    planned = station(tid, ivan, eid, 3, 10, kg=20)
    nothing = station(tid, ivan, eid)
    ci = client_for("ivan@test.local")
    for bid_, values in ((planned, ("10", "20")), (nothing, ("", ""))):
        card = main_card(ci.get(page_url(tid, blok=bid_)).text)
        assert re.findall(r'name="reps_\d" value="([^"]*)"', card) == [values[0]] * 3
        assert re.findall(r'name="kg_\d" value="([^"]*)"', card) == [values[1]] * 3
        # the adjusted weight (21 kg) as an input's value: a bare "21" is
        # also an hour or a day the page prints
        for word in ("Prošli put", "pl-next", "malo više", 'value="21"'):
            assert word not in card, word
    assert db.next_load(ivan, eid) is None and db.next_loads(ivan, [eid]) == {}


def test_its_saved_sets_count_for_the_history_and_the_maxes_at_once():
    """Rule 6: a gym training's saved sets are in "Procijenjeni maksimumi"
    and "Povijest vježbe" as soon as they are saved, no osvrt needed (a
    Stanica's, a Kružni set's rows' sets too, in the blocks' order): source
    "dvorana", where the training's title and time ("Snaga · 18:00"), or
    "Trening izvan termina"; an empty block is in none; an exercise deleted
    from the library since stays in both under its name (db.gone_key, a
    negative key the history's ?vjezba= takes)."""
    ivan = make_user("ivan@test.local")
    eid, plank = db.create_exercise("Goblet čučanj"), db.create_exercise("Plank")
    start = (now() - timedelta(hours=2)).replace(second=0, microsecond=0)
    at = f"{start.astimezone(config.TZ):%H:%M}"
    tid = db.gym_training_for(ivan, termin(ivan, start, title="Snaga"))
    station(tid, ivan)                                                      # empty: no history
    bid = station(tid, ivan, eid, 3, 6, kg=90)
    db.save_gym_done(bid, ivan, [{"reps": 6, "kg": 90.0}, {"reps": 5, "kg": 90.0}])
    [m] = db.estimated_maxes(ivan)
    assert (m.exercise_id, m.name, m.value_text, m.set_text, m.source_text) == (eid, "Goblet čučanj", "108 kg",
                                                                               "90 kg × 6", "dvorana")
    [h] = db.exercise_history(ivan, eid)
    assert (h.on, h.source_text, h.where, h.sets) == (start.astimezone(config.TZ).date(), "dvorana", f"Snaga · {at}",
                                                      ("6 × 90 kg", "5 × 90 kg"))
    out = db.add_gym_outside(ivan, date(2026, 1, 5))
    k, rows = circuit(out, ivan, [(eid, 3, 100, None), (plank, None, None, 30)], rounds=2)
    db.save_gym_round(k, ivan, 1, {rows[0]: {"reps": 3, "kg": 100.0}, rows[1]: {"seconds": 30}})
    assert [(h.on, h.where, h.sets) for h in db.exercise_history(ivan, eid)] == [
        (start.astimezone(config.TZ).date(), f"Snaga · {at}", ("6 × 90 kg", "5 × 90 kg")),
        (date(2026, 1, 5), "Trening izvan termina", ("3 × 100 kg",))]
    assert [(e.exercise_id, e.times) for e in db.logged_exercises(ivan)] == [(eid, 2), (plank, 1)]
    assert db.estimated_maxes(ivan)[0].value_text == "110 kg"
    ci = client_for("ivan@test.local")
    page = ci.get(f"/karton?vjezba={eid}").text
    assert f"Snaga · {at}" in page and "Trening izvan termina" in page and "110 kg" in page
    db.delete_exercise(eid)
    key = db.gone_key("Goblet čučanj")
    assert key < 0 and key == db.gone_key("goblet ČUČANJ")
    [m] = [x for x in db.estimated_maxes(ivan) if x.exercise_id == key]
    assert (m.name, m.value_text) == ("Goblet čučanj", "110 kg")
    assert [h.where for h in db.exercise_history(ivan, key)] == [f"Snaga · {at}", "Trening izvan termina"]
    page = ci.get(f"/karton?vjezba={key}").text
    assert f"Snaga · {at}" in page and "Ta vježba nije u ovom kartonu." not in page


MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64


def test_media_shows_the_clip_of_an_exercise_in_his_own_gym_training():
    """Rule 7: a member with no online plan fetches the clip of an exercise
    in one of HIS gym trainings ("Kako se izvodi" on its station, preload
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
    bid = station(tid, ivan, eid, 3, 10)
    r = ci.get(f"/media/{name}")
    assert r.status_code == 200 and r.content == MP4
    assert ca.get(f"/media/{name}").status_code == 403
    assert f'<video src="/media/{name}" controls playsinline preload="none"></video>' in main_card(
        ci.get(page_url(tid, blok=bid)).text)
    ci.post(f"/dvoranski/trening/{tid}/blok/{bid}/obrisi")
    assert ci.get(f"/media/{name}").status_code == 403


def test_a_termin_is_owed_while_its_trainings_window_is_open():
    """Rule 8 (db.pending_feedback, the login's prompt): a booked termin is
    owed once it has ended, while its training's window is open, until its
    training's osvrt is saved; one begun but not finished is owed still; not
    one not ended yet, past its window, canceled by the trainer, or marked
    "Nisam bio/la". The prompt leads to the training's new address."""
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
    station(db.gym_training_for(ivan, begun), ivan, db.create_exercise("Plank"))
    assert [x.id for x in db.pending_feedback(ivan)] == [owed, begun]
    ci = client_for("ivan@test.local")
    assert f'href="/dvoranski/termin/{owed}" autofocus' in ci.get("/raspored").text


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
    """A station's set table: (the row's number, its inputs' values by field,
    ticked) per row."""
    out = []
    for done, n, cells in re.findall(r'<tr( class="is-done")?>\s*<th scope="row">(\d+)</th>(.*?)</tr>', card, re.S):
        pressed = re.search(r'aria-pressed="(true|false)"', cells).group(1) == "true"
        assert pressed == bool(done), "a ticked row is marked so"
        out.append((int(n), dict(re.findall(r'name="([a-z]+)_\d+" value="([^"]*)"', cells)), pressed))
    return out


def heads(card: str) -> list[str]:
    """A set table's column headers as a reader gets them."""
    thead = card.split("<thead>")[1].split("</thead>")[0]
    return [re.sub(r"<[^>]+>", "", h) for h in re.findall(r'<th scope="col"[^>]*>(.*?)</th>', thead)]


def test_the_page_names_its_training_and_offers_the_templates():
    """GET /dvoranski/termin/<id> opens the member's training: the player's
    top (no strip with no block, "← Natrag" to the tab "Dvoranski treninzi"
    since build 2, 27.11.2026, his karton at the termin's row until then,
    the clock rendered hidden with no tick to count from, "Završi trening"
    its osvrt), the head (the kicker "Trening u dvorani", the termin's title
    as the h1, right under it its date and time, "Upis je otvoren do
    četvrtka 26.11. u ponoć."), then, with no block, the template chooser:
    "Odaberi predložak", a button per template in its order (its title over
    its facts), under a hairline "ili složi sam/a:" with "+ Stanica" and "+
    Kružni set"; no overview, no dock, no "Isprazni trening"; the rest bar.
    No phone reminder and no install banner (no_nudges); the tab Dvoranski
    treninzi lit, the Karton tab not (its until build 2)."""
    ivan = make_user("ivan@test.local")
    db.reset_gym_templates()
    stanicni, kruzni = db.gym_templates()
    start = (now() - timedelta(hours=1)).replace(second=0, microsecond=0)
    sid = termin(ivan, start, title="Snaga")
    ci = client_for("ivan@test.local")
    r = ci.get(f"/dvoranski/termin/{sid}")
    [t] = db.gym_trainings(ivan)
    page = r.text
    assert str(r.url).endswith(f"/dvoranski/trening/{t.id}") and r.status_code == 200
    assert 'class="pl-segs"' not in page and 'class="pl-track"' not in page
    assert '<a class="act act-quiet" href="/dvoranski"><span class="t">← Natrag</span></a>' in page
    assert '<span class="pl-timer" hidden title="Vrijeme treninga">' in page
    assert (f'<a class="act pl-end" href="/dvoranski/trening/{t.id}/osvrt"><span class="t">Završi trening</span></a>'
            in page)
    assert ('<p class="gt-kicker"><span class="t">Trening u dvorani</span></p>\n    <h1>Snaga</h1>\n'
            f'    <div class="gt-when">\n      <span>{when_text(start)}</span>') in page
    assert f'<p class="gt-state"><span class="t">Upis je otvoren do</span> {until_text(start)}.</p>' in page
    card = main_card(page)
    assert '<h2 class="gt-ch-h" id="gt-ch-h"><span class="t">Odaberi predložak</span></h2>' in card
    assert re.findall(r'<input type="hidden" name="predlozak" value="(\d+)">\s*<button type="submit" class="gt-tpl-row">'
                      r'<span class="gt-tpl-txt"><span class="gt-tpl-name">([^<]*)</span><span class="gt-tpl-facts">'
                      r'([^<]*)</span></span><span class="gt-tpl-go" aria-hidden="true">→</span></button>', card) == [
        (str(stanicni.id), "Stanični trening", "6 stanica"),
        (str(kruzni.id), "Kružni trening", "1 stanica · kružni set · 4 kruga")]
    assert "data-confirm" not in card                                       # nothing chosen yet: it asks nothing
    assert '<p class="gt-own-t"><span class="t">ili složi sam/a:</span></p>' in card
    assert re.findall(r'name="vrsta" value="(\w+)">\s*<button type="submit" class="act"><span class="t">([^<]*)', card) == [
        ("stanica", "+ Stanica"), ("kruzni", "+ Kružni set")]
    for gone in ('id="pregled"', 'class="pl-dock"', "/isprazni", 'id="library-json"'):
        assert gone not in page, gone
    assert page.count('id="plRest"') == 1
    assert 'id="phoneCard"' not in page and 'id="a2hs"' not in page
    assert '<a href="/dvoranski" class="on">Dvoranski treninzi</a>' in page and '<a href="/karton" class="">' in page
    with db.session_scope() as s:                                           # "ili složi sama:" as she reads it
        s.get(User, ivan).sex = "f"
    assert '<span class="t">ili složi sama:</span>' in ci.get(page_url(t.id)).text


def test_the_chooser_applies_a_template_and_is_offered_again_until_the_first_tick():
    """Applied (POST …/predlozak), the page on the template's first block;
    while the training holds blocks and no tick, a quiet "Promijeni
    predložak" at the page's foot opens the chooser again (no "ili složi
    sam/a:" there), each template asking first once an exercise is chosen
    ("Zamijeniti predložak?", "Odabrane vježbe se brišu.", "Zamijeni
    predložak"); a refused one says why in it, open; after a tick it is not
    offered and a refusal says so at the page's top."""
    ivan = make_user("ivan@test.local")
    db.reset_gym_templates()
    stanicni, kruzni = db.gym_templates()
    ex = library("Goblet čučanj")
    tid = db.add_gym_outside(ivan, config.today())
    ci = client_for("ivan@test.local")
    r = ci.post(f"/dvoranski/trening/{tid}/predlozak", data={"predlozak": str(kruzni.id)})
    t = db.gym_training(tid, ivan)
    assert "Stanica 1 od 1" in main_card(r.text) and 'name="exercise_id"' in main_card(r.text)
    foot = r.text.split('<div class="gt-foot-col">')[1]
    assert ('<details class="gt-change" id="predlozak">\n        <summary class="act act-quiet"><span class="t">Promijeni '
            'predložak</span></summary>') in foot
    assert "gt-own" not in foot and "data-confirm-title=\"Zamijeniti" not in foot
    db.set_gym_station(t.blocks[0].id, ivan, ex["Goblet čučanj"], 3, 10)
    foot = ci.get(page_url(tid)).text.split('<div class="gt-foot-col">')[1]
    assert foot.count('data-confirm-title="Zamijeniti predložak?" data-confirm="Odabrane vježbe se brišu." '
                      'data-confirm-cta="Zamijeni predložak"') == 2
    page = ci.get(page_url(tid, predlozak=1, error="Odaberi predložak s popisa.")).text
    assert '<details class="gt-change" id="predlozak" open>' in page
    assert ('<div class="alert" role="alert"><span>Odaberi predložak s popisa.</span></div>'
            in page.split('<details class="gt-change"')[1])
    assert page.count('<div class="alert" role="alert">') == 1
    db.save_gym_done(t.blocks[0].id, ivan, [{"reps": 10, "kg": 20.0}])
    page = ci.get(page_url(tid, predlozak=1, error="Trening je već započet — predložak se više ne može zamijeniti.")).text
    main = page.split("<main")[1].split("</main>")[0]
    assert 'class="gt-change"' not in main and "Promijeni predložak" not in main
    top = main.split('<div class="pl gt"')[0]
    assert '<span>Trening je već započet — predložak se više ne može zamijeniti.</span>' in top   # at the top


def test_a_station_empty_and_started():
    """An empty Stanica: "Stanica 2 od 3", ONE form, all in sight: Vježba
    (the library's combobox over the page's #library-json, the tag chips
    above it), Serije, Ponavljanja, Opterećenje (kg), Pauza (s), Vrijeme
    (s), Komentar, "Kreni"; a quiet "Ukloni stanicu". Started: the
    exercise's name (h2), what was asked ("6 × 10 · 40 kg · pauza 90 s"),
    its comment, "Kako se izvodi", the set table (a row per planned set,
    three with none given, prefilled with the plan, a ticked row as saved,
    the ✓ column the script's), "+ serija", the no-JS "Spremi", the rating,
    "Nastavi trening" and "Završi trening", quiet "Uredi" (the form again,
    its values; the exercise fixed once a set is ticked) and "Ukloni
    stanicu" (asking while it holds a tick). An exercise gone from the
    library: its name, its sets as text and "Ukloni stanicu"."""
    ivan = make_user("ivan@test.local")
    goblet = db.create_exercise("Goblet čučanj", "Girja uz prsa, pete na podu.", "Do paralele i natrag.", "girja")
    db.create_exercise("Swing", tags="girja")
    tid = db.add_gym_outside(ivan, config.today())
    first = station(tid, ivan, goblet, 6, 10, kg=40, rest=90, note="Polako dolje.")
    empty = station(tid, ivan)
    station(tid, ivan)
    ci = client_for("ivan@test.local")
    page = ci.get(page_url(tid, blok=empty)).text
    card = main_card(page)
    assert '<p class="pl-eyebrow"><span>Stanica 2 od 3</span></p>' in card
    form = card.split('<form class="gt-sform"')[1].split("</form>")[0]
    assert f'method="post" action="/dvoranski/trening/{tid}/blok/{empty}/stanica">' in form
    assert [re.sub(r"<[^>]+>", "", x) for x in re.findall(r'<label for="gt-s\d+-\w+">(.*?)</label>', form)] == [
        "Vježba", "Serije", "Ponavljanja", "Opterećenje (kg)", "Pauza (s)", "Vrijeme (s)", "Komentar"]
    assert f'<input type="hidden" id="gt-s{empty}-ex" name="exercise_id" value="" data-hint="">' in form
    assert 'data-tag="girja"' in form and "<details" not in form            # nothing folded
    # its two buttons (28.11.2026): "Kreni", the member's filled one, then "Spremi"
    assert form.index(KRENI) < form.index(SPREMI) and form.count('type="submit"') == 2
    assert f'<button type="submit" form="gt-bx-{empty}" class="act act-quiet"><span class="t">Ukloni stanicu</span>' in card
    lib = json.loads(unescape(page.split('<script type="application/json" id="library-json">')[1].split("</script>")[0]))
    assert [row[1:] for row in lib] == [["Goblet čučanj", "girja"], ["Swing", "girja"]]

    page = ci.get(page_url(tid, blok=first)).text
    card = main_card(page)
    assert '<span>Stanica 1 od 3</span>' in card and '<h2 class="pl-name">Goblet čučanj</h2>' in card
    assert '<p class="pl-dose">6 × 10 · 40 kg · pauza 90 s</p>' in card and '<p class="pl-sub">Polako dolje.</p>' in card
    assert ('<summary><span class="t">Kako se izvodi</span></summary>' in card
            and '<p><strong><span class="t">Jedno ponavljanje:</span></strong> Do paralele i natrag.</p>' in card)
    assert heads(card) == ["Set", "Pon.", "Kg", "✓"]
    assert table(card) == [(n, {"reps": "10", "kg": "40"}, False) for n in range(1, 7)]
    assert ('<form class="gt-log" id="gt-log" method="post" action="/dvoranski/trening/%d/blok/%d/odradeno"' % (tid, first)
            in card and f'data-blok="{first}" data-sets="6" data-rest="90" data-max="20"' in card)
    assert '<input type="hidden" name="polja" value="reps,kg">' in card
    assert '<button type="button" class="act gt-add-set" hidden><span class="t">+ serija</span></button>' in card
    assert '<button type="submit" class="btn btn-sm gt-save"><span class="t">Spremi</span></button>' in card
    assert ('<a class="btn btn-ghost" href="/dvoranski/trening/%d/osvrt"><span class="t">Završi trening</span></a>' % tid
            in card)
    assert re.search(r'<a class="btn" href="[^"]*"><span class="t">Nastavi trening</span></a>', card)
    edit = card.split('<details class="gt-edit">')[1].split("</details>")[0]
    assert '<summary class="act act-quiet"><span class="t">Uredi</span></summary>' in edit
    assert (f'<input type="hidden" id="gt-s{first}-ex" name="exercise_id" value="{goblet}"' in edit
            and 'name="sets" inputmode="numeric" min="1" max="99" value="6"' in edit and 'value="Polako dolje."' in edit)
    assert '<button type="submit" class="btn btn-sm"><span class="t">Spremi</span></button>' in edit
    drop = page.split(f'<form id="gt-bx-{first}"')[1].split("</form>")[0]
    assert 'data-ask-title="Ukloniti stanicu?" data-ask="Upisane serije ove stanice se brišu." ' \
           'data-ask-cta="Ukloni stanicu"' in drop and "data-confirm" not in drop
    db.save_gym_done(first, ivan, [{"reps": 10, "kg": 40.0}, {"reps": 9, "kg": 42.5}])
    page = ci.get(page_url(tid, blok=first, uredi=1)).text
    card = main_card(page)
    assert table(card)[:3] == [(1, {"reps": "10", "kg": "40"}, True), (2, {"reps": "9", "kg": "42.5"}, True),
                               (3, {"reps": "10", "kg": "40"}, False)]
    edit = card.split('<details class="gt-edit" open>')[1].split("</details>")[0]
    assert ('<p class="gt-fixed"><span class="gt-flabel"><span class="t">Vježba</span></span> <strong>Goblet čučanj'
            '</strong></p>') in edit and f'<input type="hidden" name="exercise_id" value="{goblet}">' in edit
    assert ' data-confirm-title="Ukloniti stanicu?"' in page.split(f'<form id="gt-bx-{first}"')[1].split("</form>")[0]
    db.rate_gym_block(first, ivan, 8)
    db.delete_exercise(goblet)                                              # gone from the library
    card = main_card(ci.get(page_url(tid, blok=first)).text)
    assert '<h2 class="pl-name">Goblet čučanj</h2>' in card and "<input" not in card and "gt-log" not in card
    assert ('<p class="gt-done"><strong><span class="t">Odrađeno:</span></strong> 10 × 40 kg · 9 × 42,5 kg · težina '
            '8/10</p>') in card and "Ukloni stanicu" in card and "Uredi" not in card


def test_nastavi_trening_goes_to_the_next_block_not_done():
    """"Nastavi trening": the next block after this one that is not done,
    else the first not done before it, else the "what next" card
    (?dalje=1: "Sve je odrađeno — …", "+ Stanica", "+ Kružni set", "Završi
    trening"). With no ?blok= the page shows the first block not done;
    every one done, the "what next" card. Blocks are done in any order."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank")
    tid = db.add_gym_outside(ivan, config.today())
    s1 = station(tid, ivan, ex["Goblet čučanj"], 1, 10)
    s2 = station(tid, ivan, ex["Plank"], 1, seconds=30)
    k3, rows = circuit(tid, ivan, [(ex["Plank"], None, None, 30)], rounds=2)
    db.save_gym_round(k3, ivan, 1, {rows[0]: {"seconds": 30}})              # started, not done
    s4 = station(tid, ivan, ex["Goblet čučanj"], 1, 10)
    for b in (s1, s4):
        db.save_gym_done(b, ivan, [{"reps": 10, "kg": 20.0}])
    ci = client_for("ivan@test.local")

    def nastavi(bid):
        card = main_card(ci.get(page_url(tid, blok=bid)).text)
        return unescape(re.search(r'<a class="btn(?: btn-ghost)?" href="([^"]*)"><span class="t">Nastavi trening', card).group(1))

    assert nastavi(s2) == page_url(tid, blok=k3)                            # the next one not done
    assert nastavi(k3) == page_url(tid, blok=s2)                            # none after: the first before
    assert nastavi(s1) == page_url(tid, blok=s2)
    # the card's one filled button: a Stanica's "Nastavi trening"; on a
    # Kružni set with a Krug still to save that is "Krug 2 odrađen", and
    # "Nastavi trening" stands back (a ghost) until the set is done
    assert '<a class="btn" href=' in main_card(ci.get(page_url(tid, blok=s2)).text).split("Nastavi trening")[0][-160:]
    k3_card = main_card(ci.get(page_url(tid, blok=k3)).text)
    assert '<a class="btn btn-ghost" href=' in k3_card.split("Nastavi trening")[0][-160:]
    assert 'id="glavno"' in (page := ci.get(page_url(tid)).text) and f"Stanica 2 od 3" in main_card(page)
    db.save_gym_done(s2, ivan, [{"seconds": 30}])
    assert nastavi(k3) == page_url(tid, dalje=1)                            # every other one done
    assert "Kružni set" in main_card(ci.get(page_url(tid)).text)            # the first not done
    db.save_gym_round(k3, ivan, 2, {rows[0]: {"seconds": 30}})
    k3_card = main_card(ci.get(page_url(tid, blok=k3)).text)                # the set done: filled again
    assert '<a class="btn" href=' in k3_card.split("Nastavi trening")[0][-160:]
    for url in (page_url(tid), page_url(tid, dalje=1)):
        card = main_card(ci.get(url).text)
        assert ('<p class="gt-next-t"><span class="t">Sve je odrađeno — dodaj stanicu ili kružni set, ili završi '
                'trening.</span></p>') in card
        assert "+ Stanica" in card and "+ Kružni set" in card
        assert f'<a class="btn" href="/dvoranski/trening/{tid}/osvrt"><span class="t">Završi trening</span></a>' in card


def test_spremi_writes_a_block_and_opens_the_next_empty_one():
    """An empty block's second button (28.11.2026; the owner, preparing a
    member's training as Amir will: "Why dont we have a 'save' button here?
    How can Amir prepare a training then?"): "Spremi" writes the block
    exactly as "Kreni" does and opens the next block that holds no exercise
    ("Spremljeno." in it), so a training is written one block after another;
    with none after it the first empty one before it, with none at all the
    block itself. Nothing is ticked and no Krug is opened by it. A Kružni
    set's setup the same. The filled button is the member's "Kreni"; for
    staff acting as him "Spremi", first in the form, so Enter in a field
    means it (the set's form: its hidden default button says so)."""
    ivan = make_user("ivan@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    ex = library("Goblet čučanj", "Plank")
    tid = db.add_gym_outside(ivan, config.today())
    s1, s2 = station(tid, ivan), station(tid, ivan)
    k3, rows = circuit(tid, ivan)
    s4 = station(tid, ivan)
    ci = client_for("ivan@test.local")

    def save_station(c, bid, exercise, **extra):
        return c.post(f"/dvoranski/trening/{tid}/blok/{bid}/stanica", follow_redirects=False,
                      data={"exercise_id": str(exercise), "sets": "3", "reps": "10", **extra})

    r = save_station(ci, s2, ex["Plank"], spremi="1")                       # the next empty one after it
    assert location(r) == f"/dvoranski/trening/{tid}?blok={k3}&ok=Spremljeno.#glavno"
    it = block(s2).item
    assert (it.exercise_id, it.sets, it.reps, it.done_sets) == (ex["Plank"], 3, 10, [])
    assert "Spremljeno." in main_card(ci.get(r.headers["location"]).text)
    full = {rows[0]: (ex["Goblet čučanj"], 10, 16, None), **{x: (None, None, None, None) for x in rows[1:]}}
    r = plan(ci, tid, k3, full, rounds="3", rest="60", spremi="1")           # the set: written, not started
    assert location(r) == f"/dvoranski/trening/{tid}?blok={s4}&ok=Spremljeno.#glavno"
    assert (block(k3).rounds, block(k3).rest_seconds, block(k3).rounds_saved) == (3, 60, set())
    assert "gt-kr" not in main_card(ci.get(page_url(tid, blok=k3)).text)     # still its setup, no Krug opened
    r = save_station(ci, s4, ex["Plank"], spremi="1")                       # none after: the first before
    assert location(r) == f"/dvoranski/trening/{tid}?blok={s1}&ok=Spremljeno.#glavno"
    r = save_station(ci, s1, ex["Goblet čučanj"], spremi="1")               # none left: the block itself
    assert location(r) == f"/dvoranski/trening/{tid}?blok={s1}&ok=Spremljeno.#glavno"
    assert all(not it.done_sets for b in db.gym_training(tid, ivan).blocks for it in b.items)
    r = save_station(ci, s1, ex["Goblet čučanj"])                           # "Kreni", and a form with no button: as before
    assert location(r) == f"/dvoranski/trening/{tid}?blok={s1}&kreni=1#glavno"
    r = save_station(ci, s1, "", spremi="1", exercise_id="")                 # a refusal: its own card, nothing moved on
    empty = station(tid, ivan)
    r = ci.post(f"/dvoranski/trening/{tid}/blok/{empty}/stanica", data={"spremi": "1"}, follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}?blok={empty}&error=Odaberi vježbu s popisa.#glavno"

    # staff acting as him: "Spremi" is the filled one and comes first
    k5, _ = circuit(tid, ivan)
    cs = client_for("coach@test.local")
    assert cs.post(f"/kao/{ivan}", follow_redirects=False).status_code == 303
    staff_kreni = KRENI.replace('class="btn"', 'class="btn btn-ghost"')
    staff_spremi = SPREMI.replace('class="btn btn-ghost"', 'class="btn"')
    form = main_card(cs.get(page_url(tid, blok=empty)).text).split('<form class="gt-sform"')[1].split("</form>")[0]
    assert form.index(staff_spremi) < form.index(staff_kreni) and KRENI not in form
    form = main_card(cs.get(page_url(tid, blok=k5)).text).split('<form class="gt-plan" id="gt-plan"')[1].split("</form>")[0]
    assert '<button type="submit" hidden name="spremi" value="1"></button>' in form
    assert form.index(staff_spremi) < form.index(staff_kreni)
    mine = main_card(ci.get(page_url(tid, blok=k5)).text)                    # the member's own: Kreni first, as before
    assert mine.index(KRENI) < mine.index(SPREMI)


def test_a_circuit_set_up_and_started():
    """A Kružni set being set up (no Krug saved, none asked for): the
    kicker "Kružni set", ONE form, a box per row (Vježba, the combobox, a
    converted slot's hint on it; Ponavljanja, Opterećenje (kg), Vrijeme (s);
    its ✕, a submit of the form), "+ vježba", Krugova (4), "Pauza nakon
    kruga (s)", "Kreni". Started: "Krug 2 od 4" with "− krug" / "+ krug",
    the saved Krug folded to its line, the Krug on screen open with "Krug 2
    odrađen", quiet "Uredi" (the rows and the plan again, a row that holds a
    set fixed, its ✕ asking first) and "Ukloni kružni set" (asking while
    it holds a set); every Krug saved: "✓ Spremljeno" and "4 kruga"."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank")
    tid = db.add_gym_outside(ivan, config.today())
    bid, (r1, r2, r3, r4) = circuit(tid, ivan)
    with db.session_scope() as s:
        s.get(GymTrainingItem, r2).hint = "core"
    ci = client_for("ivan@test.local")
    page = ci.get(page_url(tid, blok=bid)).text
    card = main_card(page)
    assert '<p class="pl-eyebrow" id="gt-k-h"><span><span class="t">Kružni set</span></span></p>' in card
    form = card.split('<form class="gt-plan" id="gt-plan"')[1].split("</form>")[0]
    assert f'name="stavke" value="{r1},{r2},{r3},{r4}"' in form and '<input type="hidden" name="kreni"' not in form
    # what Enter in a field sends is the form's FIRST submit button: the
    # hidden one that says "kreni", before any row's ✕ (28.11.2026: a number
    # typed and Enter took the first row away)
    assert 'name="kreni"' in re.search(r'<button type="submit"[^>]*>', form).group(0)
    assert '<button type="submit" hidden name="kreni" value="1"></button>' in form
    assert form.count('class="gt-prow"') == 4
    assert f'<input type="hidden" id="gt-r{r2}" name="vjezba_{r2}" value="" data-hint="core">' in form
    assert [re.sub(r"<[^>]+>", "", x) for x in re.findall(rf'<label for="gt-r{r1}(?:-\w+)?">(.*?)</label>', form)] == [
        "Vježba", "Ponavljanja", "Opterećenje (kg)", "Vrijeme (s)"]
    assert f'<button type="submit" name="ukloni" value="{r1}" class="act act-quiet gt-px" formnovalidate' in form
    assert ('<button type="submit" name="dodaj" value="1" class="act gt-padd" formnovalidate><span class="t">+ vježba'
            in form)
    assert 'name="rounds" inputmode="numeric" min="1" max="20" value="4"' in form
    assert 'name="rest" inputmode="numeric" min="0" max="3600" value=""' in form
    assert form.index(KRENI) < form.index(SPREMI)                          # the member's filled one first
    assert "gt-kr" not in card and "Krug 1" not in card
    # "Kreni" with every row empty: a Krug needs an exercise, so the setup
    # stays and says so (what was typed, the Krug and the pause, is saved)
    empty = {r: (None, None, None, None) for r in (r1, r2, r3, r4)}
    r = plan(ci, tid, bid, empty, rounds="3", rest="45", kreni="1")
    assert location(r) == f"/dvoranski/trening/{tid}?blok={bid}&uredi=1&error=Upiši bar jednu vježbu.#glavno"
    card = main_card(ci.get(r.headers["location"]).text)
    assert "Upiši bar jednu vježbu." in card and 'id="gt-plan"' in card and "gt-kr" not in card
    assert 'name="rounds" inputmode="numeric" min="1" max="20" value="3"' in card
    plan(ci, tid, bid, {r1: (ex["Goblet čučanj"], 10, 16, None), r2: (ex["Plank"], None, None, 30),
                        r3: (None, None, None, None), r4: (None, None, None, None)}, rounds="4", rest="60", kreni="1")
    card = main_card(ci.get(page_url(tid, blok=bid, krug=1)).text)
    assert '<span class="pl-round">Krug 1 od 4</span>' in card and "gt-plan\" id=\"gt-plan\"" not in card.split(
        '<details class="gt-edit">')[0]
    db.save_gym_round(bid, ivan, 1, {r1: {"reps": 10, "kg": 16.0}, r2: {"seconds": 30}})
    page = ci.get(page_url(tid, blok=bid)).text
    card = main_card(page)
    assert '<span class="pl-round">Krug 2 od 4</span>' in card
    assert ('<button type="submit" class="act act-quiet"><span class="t">− krug</span></button>' in card
            and '<button type="submit" class="act act-quiet"><span class="t">+ krug</span></button>' in card)
    assert re.findall(rf'<details class="gt-kr" id="krug-{bid}-(\d)"( open)?>', card) == [("1", ""), ("2", " open")]
    assert '<span class="gt-kr-line">· 10 × 16 kg · 30 s</span>' in card
    edit = card.split('<details class="gt-edit">')[1].split("</details>")[0]
    assert (f'<p class="gt-fixed"><span class="gt-flabel"><span class="t">Vježba</span></span> <strong>Goblet čučanj'
            f'</strong></p>\n      <input type="hidden" name="vjezba_{r1}" value="{ex["Goblet čučanj"]}">') in edit
    assert ('data-ask-title="Ukloniti vježbu?" data-ask="Upisane serije ove vježbe se brišu." data-ask-cta="Ukloni '
            'vježbu"') in edit.split(f'value="{r1}" class="act act-quiet gt-px"')[1].split(">")[0]
    assert "data-ask" not in edit.split(f'value="{r3}" class="act act-quiet gt-px"')[1].split(">")[0]
    assert '<input type="hidden" name="kreni"' not in edit and '<span class="t">Spremi</span></button>' in edit
    drop = page.split(f'<form id="gt-bx-{bid}"')[1].split("</form>")[0]
    assert 'data-confirm-title="Ukloniti kružni set?" data-confirm="Upisani krugovi ovog kružnog seta se brišu." ' \
           'data-confirm-cta="Ukloni kružni set"' in drop
    for n in (2, 3, 4):
        db.save_gym_round(bid, ivan, n, {r1: {"reps": 10, "kg": 16.0}, r2: {"seconds": 30}})
    card = main_card(ci.get(page_url(tid, blok=bid)).text)
    assert ('<span class="pl-round">4 kruga</span> <span class="pl-saved"><span class="t">✓ Spremljeno</span></span>'
            in card)
    assert 'disabled' not in card.split('<div class="gt-kctl">')[1].split("</div>")[0]


def test_the_overview_marks_each_block_and_rings_the_one_on_screen():
    """The overview (#pregled): every block in order, each a link
    (?blok=<id>), "STANICA 1" over its exercise and its mark ("✓", "1/3",
    none), what was asked under it, an empty one "prazna"; "KRUŽNI SET"
    over "2 vježbe · krug 2/3" or "prazan"; the one on screen ringed
    (is-cur, aria-current="step"); at its end "+ Stanica" and "+ Kružni
    set". The strip: a piece per block, done --accent, the one on screen
    cur; the phone's pill "Pregled · 1/5 ✓"; the clock from the first tick
    while it is at most 4 hours old."""
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank")
    tid = db.add_gym_outside(ivan, config.today())
    s1 = station(tid, ivan, ex["Goblet čučanj"], 3, 10, kg=20)
    s2 = station(tid, ivan, ex["Plank"], 3, seconds=30)
    k3, rows = circuit(tid, ivan, [(ex["Goblet čučanj"], 10, None, None), (ex["Plank"], None, None, 30)], rounds=3)
    s4 = station(tid, ivan)
    k5, _ = circuit(tid, ivan)
    db.save_gym_done(s1, ivan, [{"reps": 10, "kg": 20.0}] * 3)
    db.save_gym_done(s2, ivan, [{"seconds": 30}])
    db.save_gym_round(k3, ivan, 1, {rows[0]: {"reps": 10, "kg": 0.0}, rows[1]: {"seconds": 30}})
    ci = client_for("ivan@test.local")
    page = ci.get(page_url(tid, blok=s2)).text
    side = overview(page)
    links = re.findall(r'<a class="card pl-row( is-cur)?( is-empty)?" href="([^"]*)"\s+data-kind="(\w+)" data-blok="(\d+)"'
                       r'( aria-current="step")?>', side)
    assert [(unescape(h), k, int(b), bool(c), bool(e), bool(a)) for c, e, h, k, b, a in links] == [
        (page_url(tid, blok=s1), "stanica", s1, False, False, False),
        (page_url(tid, blok=s2), "stanica", s2, True, False, True),
        (page_url(tid, blok=k3), "kruzni", k3, False, False, False),
        (page_url(tid, blok=s4), "stanica", s4, False, True, False),
        (page_url(tid, blok=k5), "kruzni", k5, False, True, False)]
    rows_ = [shown(x) for x in side.split('<li>')[1:]]
    assert rows_ == ["Stanica 1 Goblet čučanj ✓ 3 × 10 · 20 kg", "Stanica 2 Plank 1/3 3 × 30 s",
                     "Kružni set 2 vježbe · krug 2/3", "Stanica 3 prazna", "Kružni set prazan + Stanica + Kružni set"]
    assert ('<span class="dx-dose gt-mark ok" data-mark role="img" aria-label="odrađeno">✓</span>' in side
            and '<span class="dx-dose gt-mark" data-mark role="img" aria-label="1/3 serije odrađene">1/3</span>' in side)
    assert '<span class="t">prazna</span>' in side and '<span class="t">prazan</span>' in side
    assert re.findall(r'<span data-seg="\d"(?: class="(\w+)")?></span>', page) == ["done", "cur", "", "", ""]
    assert ('<a class="pl-dock" href="#pregled"><span><span class="t">Pregled</span> · <span class="gt-dock-n">1/5'
            '</span> ✓</span></a>') in page
    started = re.search(r'<span class="pl-timer" hidden data-started="([^"]+)"', page).group(1)
    assert abs((datetime.fromisoformat(started) - now()).total_seconds()) < 60
    with db.session_scope() as s:                                           # the first tick 5 h ago: no clock
        for it in s.scalars(select(GymTrainingItem).where(GymTrainingItem.training_id == tid,
                                                         GymTrainingItem.done_at.is_not(None))):
            it.done_at = now() - timedelta(hours=5)
    assert '<span class="pl-timer" hidden title="Vrijeme treninga">' in ci.get(page_url(tid)).text


def test_after_the_window_the_page_reads_only():
    """Past its window the member's page is the record: "← Natrag" (the
    tab, since 27.11.2026; once his gym plan has lapsed, and the tab with
    it, his karton at the training's row, as until then), the head, the
    state line, the overview of what was done as text (a block with no
    exercise not shown: a Stanica's line, a Kružni set's own line and its
    exercises), the saved osvrt without "Uredi osvrt"; no card, no form, no
    input, no button, no strip, no clock, no rest bar; …/osvrt leads back
    to the page."""
    from qmt.models import Membership
    ivan = make_user("ivan@test.local")
    ex = library("Goblet čučanj", "Plank")
    tid = db.gym_training_for(ivan, termin(ivan, now() - timedelta(days=3)), staff=True)
    s1 = station(tid, ivan, ex["Goblet čučanj"], 3, 10, staff=True)
    station(tid, ivan, staff=True)                                          # empty: not on the record
    k, rows = circuit(tid, ivan, [(ex["Plank"], None, None, 30)], rounds=2, staff=True)
    db.save_gym_done(s1, ivan, [{"reps": 10, "kg": 20.0}], staff=True)
    db.rate_gym_block(s1, ivan, 6, staff=True)
    db.save_gym_round(k, ivan, 1, {rows[0]: {"seconds": 30}}, staff=True)
    db.finish_gym_training(tid, ivan, 7, None, "Dobro.", staff=True)
    ci = client_for("ivan@test.local")
    page = ci.get(page_url(tid)).text
    main = page.split("<main")[1].split("</main>")[0]
    assert '<p class="gt-state"><span class="t">Upis je zatvoren — trener ga i dalje može urediti.</span></p>' in main
    side = overview(page)
    assert [shown(x) for x in re.findall(r'<div class="card pl-row gt-rec">(.*?)</div>', side, re.S)] == [
        "Stanica 1 Goblet čučanj: zadano 3 × 10 — odrađeno 10 × 20 kg · težina 6/10",
        "Kružni set Kružni set · 2 kruga Plank: zadano 30 s — odrađeno 30 s"]
    assert '<li class="kin"><strong>Plank:</strong>' in side and "prazna" not in side and "<a " not in side
    assert '<p class="gt-facts">napor 7/10</p>' in main and "Uredi osvrt" not in main
    for gone in ("<form", "<input", "<button", 'id="glavno"', "pl-segs", "pl-timer", 'id="plRest"', "pl-dock", "pl-end"):
        assert gone not in main, gone
    assert '<a class="act act-quiet" href="/dvoranski"><span class="t">← Natrag</span></a>' in main
    r = ci.get(f"/dvoranski/trening/{tid}/osvrt", follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{tid}"
    with db.session_scope() as s:                                           # his gym plan lapsed: no tab
        s.scalar(select(Membership).where(Membership.user_id == ivan)).next_payment = \
            config.today() - timedelta(days=Membership.GRACE_DAYS + 1)
    page = ci.get(page_url(tid)).text
    assert f'<a class="act act-quiet" href="/karton#gt-{tid}"><span class="t">← Natrag</span></a>' in page
    assert 'href="/dvoranski"' not in page and "Upis je zatvoren" in page


def test_the_osvrt_is_zavrsi_trening():
    """"Završi trening" → …/osvrt: the finish screen's clothes (its kicker
    "Osvrt na trening", the title, the date and time; Napor, ten round
    buttons, required; Osjećaj; Komentar; "Spremi trening"; "Natrag na
    trening"), no nudges. Refused ("Neispravan osvrt."): the page again,
    400, what was chosen kept, nothing stored. Saved: the tab (since
    27.11.2026; the karton's diary row for a viewer with no tab),
    "Trening je spremljen.", the page saying the osvrt ("napor
    7/10 · Dobro", the comment, "Uredi osvrt"); saved again, its first
    save's time stays."""
    ivan = make_user("ivan@test.local")
    start = (now() - timedelta(hours=2)).replace(second=0, microsecond=0)
    tid = db.gym_training_for(ivan, termin(ivan, start, title="Snaga"))
    ci = client_for("ivan@test.local")
    page = ci.get(f"/dvoranski/trening/{tid}/osvrt").text
    assert ('<p class="kr-eyebrow"><span class="t">Osvrt na trening</span></p>\n  <h1>Snaga</h1>\n'
            f'  <p class="kr-when">{when_text(start)}</p>') in page
    assert f'<form class="kr-form" method="post" action="/dvoranski/trening/{tid}/osvrt">' in page
    assert re.findall(r'name="effort" value="(\d+)" required', page) == [str(n) for n in range(1, 11)]
    assert re.findall(r'name="feeling" value="(\w+)"', page) == ["slabo", "dobro", "odlicno"]
    assert '<button type="submit" class="btn"><span class="t">Spremi trening</span></button>' in page
    assert (f'<a class="act act-quiet" href="/dvoranski/trening/{tid}"><span class="t">Natrag na trening</span></a>'
            in page)
    assert 'id="phoneCard"' not in page and 'id="a2hs"' not in page

    def post(**form):
        return ci.post(f"/dvoranski/trening/{tid}/osvrt", data=form, follow_redirects=False)

    for form in ({"effort": "", "feeling": "dobro", "note": "Teško."}, {"effort": "11"}, {"effort": "0"},
                 {"effort": "x"}, {"effort": "7", "feeling": "super"}):
        r = post(**form)
        assert r.status_code == 400 and '<div class="alert" role="alert"><span>Neispravan osvrt.</span></div>' in r.text
    r = post(effort="", feeling="dobro", note="Teško.")
    assert 'value="dobro" checked' in r.text and ">Teško.</textarea>" in r.text and " required checked" not in r.text
    assert db.gym_training(tid, ivan).finished_at is None
    r = post(effort="7", feeling="dobro", note="  Teško.  ")
    assert location(r) == "/dvoranski?ok=Trening je spremljen."            # the tab, his: its last trainings show it
    t = db.gym_training(tid, ivan)
    first = t.finished_at
    assert (t.effort, t.feeling, t.note) == (7, "dobro", "Teško.") and first is not None
    page = ci.get(page_url(tid)).text
    assert ('<section class="card gt-osvrt" aria-labelledby="gt-osvrt-h">\n        <h2 id="gt-osvrt-h"><span class="t">'
            'Osvrt</span></h2>\n        <p class="gt-facts">napor 7/10 · Dobro</p>\n        <p class="gt-comment">Teško.</p>\n'
            f'        <a class="act" href="/dvoranski/trening/{tid}/osvrt"><span class="t">Uredi osvrt</span></a>') in page
    again = ci.get(f"/dvoranski/trening/{tid}/osvrt").text
    assert 'value="7" required checked' in again and 'value="dobro" checked' in again and ">Teško.</textarea>" in again
    post(effort="5", feeling="", note="")
    t = db.gym_training(tid, ivan)
    assert (t.effort, t.feeling, t.note, t.finished_at) == (5, None, "", first)
    assert '<p class="gt-facts">napor 5/10</p>' in ci.get(page_url(tid)).text


# ---------- the karton, the raspored, a roster ----------

def test_the_diary_lists_each_training_in_its_state():
    """The karton's diary: a termin's training that holds anything on its
    termin's row (its title the kicker, the day, date and time, napor and
    osjećaj, the comment, "3 vježbe", "Serije": a Stanica's line, a Kružni
    set's own line and its exercises under it; an empty block in no line;
    "Otvori trening" while the member may write it, to /dvoranski); a
    booked termin with none inside its window "Trening još nije upisan."
    with "Upiši trening" (→ /dvoranski/termin/<id>) and "Nisam bio/la",
    after it "Trening nije upisan." with "Nisam bio/la" alone; a training
    opened and left empty (blocks alone hold nothing) its termin's row; one
    outside a termin a row of its own ("Trening izvan termina", no time,
    "Otvori trening" always); an old TrainingLog row as it was. Newest
    first. The trainer's view the same rows with no button; staff acting as
    the member "Upiši trening" past the window too."""
    ivan = make_user("ivan@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    db.reset_gym_templates()
    ex = library("Goblet čučanj", "Plank", "Sklekovi")
    y = (now() - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    done_sid = termin(ivan, y, title="Snaga")
    tid = db.gym_training_for(ivan, done_sid, staff=True)
    a = station(tid, ivan, ex["Goblet čučanj"], 3, 10, kg=20, staff=True)
    station(tid, ivan, staff=True)                                          # empty: no line
    k, rows = circuit(tid, ivan, [(ex["Plank"], None, None, 30), (ex["Sklekovi"], 10, None, None)], rounds=2, staff=True)
    db.save_gym_done(a, ivan, [{"reps": 10, "kg": 20.0}, {"reps": 10, "kg": 20.0}, {"reps": 8, "kg": 20.0}], staff=True)
    db.rate_gym_block(a, ivan, 8, staff=True)
    db.save_gym_round(k, ivan, 1, {rows[0]: {"seconds": 30}, rows[1]: {"reps": 10, "kg": 0.0}}, staff=True)
    db.rate_gym_block(k, ivan, 7, staff=True)
    db.finish_gym_training(tid, ivan, 7, "dobro", "Zadnja serija teška.", staff=True)
    fresh = termin(ivan, now() - timedelta(hours=2))
    empty_sid = termin(ivan, now() - timedelta(hours=3))
    empty = db.gym_training_for(ivan, empty_sid)
    db.apply_gym_template(empty, ivan, db.gym_templates()[0].id)            # blocks alone: still nothing
    stale = termin(ivan, now() - timedelta(days=4))
    out = db.add_gym_outside(ivan, config.today() - timedelta(days=2))
    station(out, ivan, ex["Plank"], 2, seconds=30)
    with db.session_scope() as s:
        old = TrainingLog(user_id=ivan, session_id=None, date=config.today() - timedelta(days=10), effort=5, note="Staro.",
                          sets=json.dumps([{"exercise_id": ex["Plank"], "name": "Plank", "sets": [{"reps": 1, "kg": 0.0}]}]))
        s.add(old)
        s.flush()
        old_id = old.id

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
            and f'<a class="act" href="/dvoranski/trening/{tid}"><span class="t">Otvori trening</span></a>' in g
            and "<p>Zadnja serija teška.</p>" in g and '<div class="hint le-sub le-ex">3 vježbe</div>' in g)
    assert [shown(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", g)] == [
        "Goblet čučanj: zadano 3 × 10 · 20 kg — odrađeno 10 × 20 kg · 10 × 20 kg · 8 × 20 kg · težina 8/10",
        "Kružni set · 2 kruga · težina 7/10",
        "Plank: zadano 30 s — odrađeno 30 s",
        "Sklekovi: zadano 10 ponavljanja — odrađeno 10"]
    assert '<li class="kin"><strong>Plank:</strong>' in g
    f = row(diary, f"s-{fresh}")
    assert (f'<a class="act" href="/dvoranski/termin/{fresh}"><span class="t">Upiši trening</span></a>' in f
            and f'action="/karton/absent/{fresh}"' in f
            and '<div class="hint le-state"><span class="t">Trening još nije upisan.</span></div>' in f)
    assert f'class="log-entry fresh" id="s-{fresh}"' in diary
    e = row(diary, f"s-{empty_sid}")
    assert f'href="/dvoranski/termin/{empty_sid}"' in e and f'id="gt-{empty}"' not in diary
    st = row(diary, f"s-{stale}")
    assert (f"/dvoranski/termin/{stale}" not in st and f'action="/karton/absent/{stale}"' in st
            and '<div class="hint le-state"><span class="t">Trening nije upisan.</span></div>' in st)
    o = row(diary, f"gt-{out}")
    assert ('<div class="le-kicker"><span class="t">Trening izvan termina</span></div>' in o
            and " · " not in o.split('<span class="when">')[1].split("</span>")[0]
            and f'href="/dvoranski/trening/{out}"' in o and "Plank: zadano 2 × 30 s — odrađeno —" in shown(o)
            and '<div class="hint le-sub le-ex">1 vježba</div>' in o)
    lg = row(diary, f"log-{old_id}")
    assert "<p>Staro.</p>" in lg and f'action="/karton/log/{old_id}/edit"' in lg and "Plank:" in shown(lg)
    cs = client_for("coach@test.local")
    make_user("trener@test.local", plans=())                                # the owner, staff: the view is his too
    view = client_for("trener@test.local").get(f"/karton/{ivan}").text.split('<h2 id="osvrti">')[1]
    assert re.findall(r'<div class="log-entry[^"]*" id="([a-z]+-\d+)"', view) == order
    assert "/dvoranski/" not in view and "/karton/absent/" not in view
    assert "Trening još nije upisan." in view and "Trening nije upisan." in view
    assert "Kružni set · 2 kruga · težina 7/10" in shown(view)
    assert cs.post(f"/kao/{ivan}", follow_redirects=False).status_code == 303
    acting = cs.get("/karton").text.split('<h2 id="osvrti">')[1]
    assert f'href="/dvoranski/termin/{stale}"' in acting and f'href="/dvoranski/trening/{tid}"' in acting


def test_the_way_in_is_on_the_raspored_while_the_window_is_open_and_no_more_on_the_termini():
    """The raspored's "Tvoj sljedeći termin" carries "Upiši trening →" (→
    /dvoranski/termin/<id>) while its training is open: none further ahead,
    none canceled. "Nadolazeći termini" on the karton carried it too, and
    under its list "Trening upisuješ od 4 h prije termina do kraja idućeg
    dana.", from 26.11.2026 until build 2 of the dvoranski treninzi
    (27.11.2026): the tab lists the open trainings since, the karton's
    termini are the termini alone, a member's and the trainer's view's."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    soon = termin(ivan, now() + timedelta(hours=3), title="Snaga")
    later = termin(ivan, now() + timedelta(hours=6), title="Mobilnost")
    with db.session_scope() as s:
        s.add(Booking(user_id=ana, session_id=later))

    def termini(page: str) -> str:
        return page.split('<section class="card termini"')[1].split("</section>")[0]

    ci = client_for("ivan@test.local")
    mine = termini(ci.get("/karton").text)
    assert "Snaga" in mine and "Mobilnost" in mine
    for gone in ("/dvoranski/", "cal-go", "Upiši trening", "gym-when", "Trening upisuješ od", "h prije termina"):
        assert gone not in mine, gone
    card = ci.get("/raspored").text.split('<section class="card next-termin"')[1].split("</section>")[0]
    assert f'<a class="act nt-gym" href="/dvoranski/termin/{soon}"><span class="t">Upiši trening →</span></a>' in card
    ca = client_for("ana@test.local")
    assert "nt-gym" not in ca.get("/raspored").text.split('<section class="card next-termin"')[1].split("</section>")[0]
    make_user("trener@test.local", plans=())
    assert "/dvoranski/termin/" not in termini(client_for("trener@test.local").get(f"/karton/{ivan}").text)
    db.set_session_canceled(soon, True)
    assert "nt-gym" not in ci.get("/raspored").text.split('<section class="card next-termin"')[1].split("</section>")[0]


def test_a_rosters_kao_clan_lands_on_his_training_and_every_write_there_is_recorded():
    """A termin's roster's "Kao član →" goes into the member's account at
    his training of that termin (kamo=/dvoranski/termin/<id>, rule 2 for
    staff: made before its window too); a tick there carries the page's
    identity (X-QMT-Kao, base.html's) and is a row of the acting record, as
    every write is; one without it runs nothing. A termin canceled since
    says rule 2's sentence on his karton."""
    ivan = make_user("ivan@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    sid = termin(ivan, now() + timedelta(days=1))
    cs = client_for("coach@test.local")
    roster = cs.get(f"/admin/session/{sid}").text
    assert f'<input type="hidden" name="kamo" value="/dvoranski/termin/{sid}">' in roster
    r = cs.post(f"/kao/{ivan}", data={"natrag": f"/admin/session/{sid}", "kamo": f"/dvoranski/termin/{sid}"},
                follow_redirects=False)
    assert location(r) == f"/dvoranski/termin/{sid}"
    r = cs.get(location(r), follow_redirects=False)
    [t] = db.gym_trainings(ivan)
    assert location(r) == f"/dvoranski/trening/{t.id}"
    page = cs.get(location(r)).text
    assert f'data-kao="{ivan}"' in page and "Za člana je upis zatvoren; uređuješ kao trener." in page
    bid = station(t.id, ivan, db.create_exercise("Plank"), 2, seconds=30, staff=True)
    r = tick(cs, t.id, bid, "seconds", {"sec": 30})                         # no identity: runs nothing
    assert r.status_code == 303 and done_of(item_of(bid).id) == []
    r = tick(cs, t.id, bid, "seconds", {"sec": 30}, headers={**JSON, "X-QMT-Kao": str(ivan)})
    assert r.json() == {"ok": True, "error": "", "mark": "1/2", "done": False}
    rows, _ = db.acting_log()
    assert (rows[0].method, rows[0].path, rows[0].status, rows[0].member_id) == (
        "POST", f"/dvoranski/trening/{t.id}/blok/{bid}/odradeno", 200, ivan)
    other = termin(ivan, now() + timedelta(days=2))
    db.set_session_canceled(other, True)
    r = cs.get(f"/dvoranski/termin/{other}", follow_redirects=False)
    assert location(r) == "/karton?error=Termin je otkazan."


# ---------- the texts ----------

# the training page's and its osvrt's: gym.* but the landing's two and the
# tab's (gym.tab.*, 27.11.2026: tests/test_dvoranski.py)
GYM_SLOTS = [k for k in copy.SLOTS if k.startswith("gym.") and k not in ("gym.kicker", "gym.h2")
             and not k.startswith("gym.tab.")]
GYM_OPTIONAL = {"gym.head.kicker", "gym.state.closed", "gym.state.staff", "gym.osvrt.kicker", "gym.chooser.own",
                "gym.block.circuit", "gym.whatnext", "gym.overview.empty_station", "gym.overview.empty_circuit"}
GONE = ("gym.empty", "gym.template.open", "gym.part.edit", "gym.part.name", "gym.part.circuit", "gym.part.rounds",
        "gym.part.rest", "gym.part.save", "gym.part.rest_caption", "gym.card.planned", "gym.card.edit",
        "gym.card.remove", "gym.form.section", "gym.form.seconds", "gym.form.kg", "gym.form.note", "gym.slot.pick",
        "gym.slot.remove", "gym.add.title", "gym.add.exercise", "gym.add.planned", "gym.add.go")


def test_every_text_of_the_page_is_a_slot_with_its_words():
    """The page's and its osvrt's texts are slots, gym.<area>.* (65 since
    27.11.2026: the blocks' 34 came, part A's and part B's 22 that the page
    no longer prints went), labelled "Trening u dvorani…" in the editor's
    bar, required but for a kicker, a state's whole sentence, a lead line
    and an empty block's word; each printed on a page the member reads with
    its default words (a confirm's in its attribute, the script's in the
    script); where the words do the same job as in the player, on the day
    page or its finish screen, theirs print (player.*, dan.*, kraj.*). One
    edited prints in its place; /tekstovi lists them under "Trening u
    dvorani", after "Trening (izvođenje)", area by area, after the tab's
    own (since 27.11.2026, "Dvoranski treninzi": gym.tab.*)."""
    assert len(GYM_SLOTS) == 65 and not set(GONE) & set(copy.SLOTS)
    assert {k for k in GYM_SLOTS if not copy.SLOTS[k].required} == GYM_OPTIONAL
    assert all(copy.SLOTS[k].label.startswith("Trening u dvorani") for k in GYM_SLOTS)
    ivan = make_user("ivan@test.local")
    make_user("coach@test.local", is_trainer=True, plans=())
    db.reset_gym_templates()
    ex = {"Goblet čučanj": db.create_exercise("Goblet čučanj", "Pete na podu."), "Plank": db.create_exercise("Plank")}
    live = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=1)))
    s1 = station(live, ivan, ex["Goblet čučanj"], 3, 10)
    db.save_gym_done(s1, ivan, [{"reps": 10, "kg": 20.0}])
    k, rows = circuit(live, ivan, [(ex["Plank"], None, None, 30)], rounds=2)   # Krug 2 to do
    db.save_gym_round(k, ivan, 1, {rows[0]: {"seconds": 30}})
    s3 = station(live, ivan)
    setup, _ = circuit(live, ivan)
    chooser = db.gym_training_for(ivan, termin(ivan, now() - timedelta(hours=2)))
    picked = db.add_gym_outside(ivan, config.today())                       # blocks, an exercise chosen, no tick
    db.apply_gym_template(picked, ivan, db.gym_templates()[1].id)
    db.set_gym_station(db.gym_training(picked, ivan).blocks[0].id, ivan, ex["Plank"], 2, seconds=30)
    closed = db.gym_training_for(ivan, termin(ivan, now() - timedelta(days=3)), staff=True)
    station(closed, ivan, ex["Plank"], staff=True)
    done = db.add_gym_outside(ivan, config.today())
    station(done, ivan, ex["Plank"])
    db.finish_gym_training(done, ivan, 7, None, "")
    alldone = db.add_gym_outside(ivan, config.today())
    db.save_gym_done(station(alldone, ivan, ex["Plank"], 1), ivan, [{"reps": 1, "kg": 0.0}])
    kdone, krows = circuit(alldone, ivan, [(ex["Plank"], None, None, 30)], rounds=1)   # every Krug saved
    db.save_gym_round(kdone, ivan, 1, {krows[0]: {"seconds": 30}})
    gone = station(alldone, ivan, db.create_exercise("Stara vježba"), 1)
    db.save_gym_done(gone, ivan, [{"reps": 5, "kg": 0.0}])
    db.delete_exercise(block(gone).items[0].exercise_id)                    # its sets as text, "Odrađeno:"
    ci, cs = client_for("ivan@test.local"), client_for("coach@test.local")
    pages = [ci.get(page_url(live, blok=b)).text for b in (s1, k, s3, setup)]
    pages += [ci.get(page_url(x)).text for x in (chooser, picked, closed, done, alldone)]
    pages += [ci.get(page_url(alldone, blok=b)).text for b in (kdone, gone)]
    pages.append(ci.get(f"/dvoranski/trening/{live}/osvrt").text)
    cs.post(f"/kao/{ivan}")
    pages.append(cs.get(page_url(closed)).text)                             # staff, past his window
    cs.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    every = "\n".join(pages)
    assert 'data-copy="' not in every
    for key in GYM_SLOTS:
        text = copy.SLOTS[key].default
        assert f'<span class="t">{text}</span>' in every or f'="{text}"' in every or json.dumps(text) in every, key
    for key in ("player.col.set", "player.col.reps", "player.col.sec", "player.rate.step", "player.finish",
                "player.top.back", "player.rest.skip", "player.step.how", "player.round.done", "player.saved",
                "player.optional", "dan.go.start", "kraj.effort", "kraj.feeling", "kraj.save"):
        assert f'<span class="t">{copy.SLOTS[key].default}</span>' in every, key
    for key, text in (("gym.next", "Dalje"), ("gym.confirm.station_title", "Van?"), ("gym.card.failed", "Nije prošlo.")):
        assert cs.post(f"/copy/{key}", data={"text": text}).json()["text"] == text
    page = ci.get(page_url(live, blok=s1)).text
    assert '<span class="t">Dalje</span></a>' in page
    assert 'data-ask-title="Van?"' in page and 'var NOT_SAVED = "Nije pro\\u0161lo.";' in page
    tekstovi = cs.get("/tekstovi").text
    h2 = re.findall(r'<h2 id="tx-\d+">([^<]*)</h2>', tekstovi)
    assert h2.index("Trening u dvorani") == h2.index("Trening (izvođenje)") + 1
    section = tekstovi.split(">Trening u dvorani</h2>")[1].split("<h2")[0]
    assert re.findall(r"<h3>([^<]*)</h3>", section) == ["Dvoranski treninzi", "Zaglavlje", "Predložak",
                                                       "Stanica i kružni set", "Polja", "Stanica", "Kružni set",
                                                       "Pregled", "Kraj treninga", "Osvrt", "Prozori za potvrdu"]
    assert all(f'data-copy="{k}"' in section for k in GYM_SLOTS)


def test_staffs_own_training_lights_their_tab():
    """Staff have trainings outside a termin of their own (no termini), made
    on the tab (POST /dvoranski/trening, 27.11.2026): the page serves them
    as a member's, the nav's Dvoranski treninzi lit (their Karton until
    build 2) and Admin ▾ not, "← Natrag" to the tab, the editor's ✎ on it."""
    coach = make_user("coach@test.local", is_trainer=True, plans=())
    cs = client_for("coach@test.local")
    r = cs.post("/dvoranski/trening", data={"day": config.today().isoformat()}, follow_redirects=False)
    tid = int(location(r).rsplit("/", 1)[1])
    page = cs.get(page_url(tid)).text
    assert db.gym_training(tid, coach).session_id is None and 'class="card pl-card gt-chooser"' in page
    assert 'id="copyToggle"' in page and '<a href="/dvoranski" class="on">Dvoranski treninzi</a>' in page
    assert '<a href="/karton" class="">Karton</a>' in page
    assert '<a class="act act-quiet" href="/dvoranski"><span class="ed t" data-copy="player.top.back"' in page
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


def _phone(pw, server: str, email: str = "ivan@test.local"):
    """A 390px touch browser logged in as `email` (no install banner, no
    phone reminder): (browser, context, page, errors)."""
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    pg = ctx.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
    pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    pg.goto(server + "/login")
    pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); localStorage.setItem('qmt-phone', String(Date.now())); }")
    pg.fill("main input[name=email]", email)
    pg.fill("main input[name=password]", "lozinka123")
    pg.click("main button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return browser, ctx, pg, errors


def test_stanicni_trening_on_a_phone(server):
    """The owner's flow at 390px, touch, as ivan, on his termin's training
    (from the karton's "Upiši trening"): "Stanični trening" chosen; station
    1's exercise typed into the combobox and picked, its plan (6 × 10 · 40
    kg, 30 s pause), "Kreni": back started, the focus in its first set; a ✓
    saves the set ("1/6" in the overview) and starts the pause bar, which a
    reload of the page keeps counting; the rating 8 by a tap; "Nastavi
    trening" → station 2, filled, a set ticked; a tap in the overview →
    station 4, filled and a set ticked before 3; then 3. "Završi trening" →
    the osvrt → the karton at its diary row, where the four stations are
    listed and the two never filled are not. No page scrolls sideways, at
    360px either (the chooser, a station empty and started); no page
    errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    ivan = make_user("ivan@test.local")
    db.reset_gym_templates()
    for name in ("Goblet čučanj", "Plank", "Sklekovi", "Veslanje u pretklonu"):
        db.create_exercise(name, "Upute za: " + name, tags="girja")
    start = (now() - timedelta(minutes=90)).replace(second=0, microsecond=0)
    sid = termin(ivan, start, title="Snaga")
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser, ctx, pg, errors = _phone(pw, server)

        def wide(where: str) -> None:
            for w, h in ((390, 844), (360, 780)):
                pg.set_viewport_size({"width": w, "height": h})
                check(pg.evaluate(OVERFLOW) == 0, f"{where} at {w}px overflows by {pg.evaluate(OVERFLOW)}px")
            pg.set_viewport_size({"width": 390, "height": 844})

        pg.goto(server + "/karton")
        if pg.locator("#fbPrompt[open], dialog[open]").count():               # the login's prompt: later
            pg.keyboard.press("Escape")
        pg.locator(f'#s-{sid} a[href="/dvoranski/termin/{sid}"]').tap()
        pg.wait_for_load_state("networkidle")
        [t] = db.gym_trainings(ivan)
        check(pg.url.endswith(f"/dvoranski/trening/{t.id}"), f"Upiši trening led to {pg.url}")
        check(pg.locator(".gt-when > span").first.inner_text() == when_text(start), "the date and the time")
        wide("the chooser")
        with pg.expect_navigation():
            pg.locator(".gt-tpl-row", has_text="Stanični trening").tap()
        pg.wait_for_load_state("networkidle")
        blocks = [b.id for b in db.gym_training(t.id, ivan).blocks]
        check(len(blocks) == 6, f"{len(blocks)} blocks")
        check(pg.locator(".pl-eyebrow").first.inner_text().upper() == "STANICA 1 OD 6", "not on station 1")
        wide("an empty station")

        def fill(bid: int, query: str, name: str, **plan):
            box = pg.locator(f"#gt-s{bid}-ex-q")
            box.tap()
            box.fill(query)
            pg.locator(f"#gt-s{bid}-ex-list [role=option]", has_text=name).first.tap()
            check(box.input_value() == name, f"the combobox holds {box.input_value()!r}")
            for field, value in plan.items():
                pg.fill(f"#gt-s{bid}-{field}", str(value))
            with pg.expect_navigation():
                pg.locator("form.gt-sform button.btn").first.tap()
            pg.wait_for_load_state("networkidle")
            pg.wait_for_timeout(150)

        def tick_row(n: int):
            with pg.expect_response(lambda r: r.url.endswith("/odradeno") and r.request.method == "POST"):
                pg.locator("#gt-log tbody tr").nth(n - 1).locator(".pl-done").tap()

        fill(blocks[0], "gob", "Goblet čučanj", sets=6, reps=10, kg=40, rest=30)
        check(f"blok={blocks[0]}" in pg.url and "kreni=1" in pg.url, f"Kreni led to {pg.url}")
        check(pg.evaluate("document.activeElement && document.activeElement.name") == "reps_1", "the focus is not in set 1")
        check(pg.locator(".pl-dose").inner_text() == "6 × 10 · 40 kg · pauza 30 s", "what was asked")
        rows = pg.locator("#gt-log tbody tr")
        check(rows.count() == 6 and rows.nth(0).locator("input[name=kg_1]").input_value() == "40", "the rows")
        wide("a station started")
        tick_row(1)
        first = item_of(blocks[0]).id
        check(done_of(first) == [{"reps": 10, "kg": 40.0}], f"saved {done_of(first)}")
        check(pg.locator(f'#pregled [data-blok="{blocks[0]}"] [data-mark]').inner_text() == "1/6", "the overview's mark")
        rest = pg.locator("#plRest")
        check(rest.is_visible() and pg.locator(".pl-rest-h").inner_text().upper() == "ODMOR", "the pause did not start")
        pg.wait_for_timeout(2500)
        pg.reload()                                                         # kept: on, and not from the start (0:30)
        pg.wait_for_load_state("networkidle")
        left = pg.locator(".pl-rest-t").inner_text()
        check(pg.locator("#plRest").is_visible() and left in ("0:28", "0:27", "0:26", "0:25", "0:24", "0:23"),
              f"the reload lost the pause ({left})")
        wide("a station, the pause bar showing")
        pg.locator(".pl-rest-skip").tap()
        check(pg.locator("#plRest").is_hidden(), "Preskoči odmor did not end the pause")
        pg.reload()
        pg.wait_for_load_state("networkidle")
        check(pg.locator("#plRest").is_hidden(), "a skipped pause came back at the reload")
        with pg.expect_response(lambda r: r.url.endswith("/ocjena")):
            pg.locator("form.gt-rate label.sc").nth(7).tap()
        check(block(blocks[0]).effort == 8, "the rating is not saved")
        with pg.expect_navigation():
            pg.locator(".gt-go a.btn").first.tap()                           # Nastavi trening
        pg.wait_for_load_state("networkidle")
        check(f"blok={blocks[1]}" in pg.url, f"Nastavi trening led to {pg.url}")
        fill(blocks[1], "plank", "Plank", sets=2, sec=30)
        check(pg.locator("#gt-log thead th").all_inner_texts()[1].strip().upper() == "SEK.", "the plank's columns")
        tick_row(1)                                                         # no pause asked: no bar
        check(pg.locator("#plRest").is_hidden(), "a pause with none asked")
        with pg.expect_navigation():
            pg.locator(f'#pregled a[data-blok="{blocks[3]}"]').tap()        # station 4 before 3
        pg.wait_for_load_state("networkidle")
        check(pg.locator(".pl-eyebrow").first.inner_text().upper() == "STANICA 4 OD 6", "the overview's tap")
        fill(blocks[3], "skl", "Sklekovi", sets=1, reps=12)
        tick_row(1)
        with pg.expect_navigation():
            pg.locator(f'#pregled a[data-blok="{blocks[2]}"]').tap()
        pg.wait_for_load_state("networkidle")
        fill(blocks[2], "vesl", "Veslanje u pretklonu", sets=1, reps=10, kg=12)
        tick_row(1)
        check(pg.locator(".gt-dock-n").inner_text() == "2/6", f"the pill says {pg.locator('.gt-dock-n').inner_text()}")
        with pg.expect_navigation():
            pg.locator(".pl-end").tap()
        check(pg.url.endswith(f"/dvoranski/trening/{t.id}/osvrt"), f"Završi trening led to {pg.url}")
        pg.locator(".scale label.sc").nth(6).tap()
        with pg.expect_navigation():
            pg.locator(".kr-go .btn").tap()
        pg.wait_for_load_state("networkidle")
        # back at the tab, his (27.11.2026): since the evening the tab lists
        # what is still being written, the termin's training open there until
        # its window closes, its card saying its napor; the record is in the
        # karton's diary
        check(pg.url.split("?")[0].endswith("/dvoranski") and pg.locator(".alert.ok").inner_text() == "Trening je spremljen.",
              f"the osvrt led to {pg.url}")
        check("napor 7/10" in pg.locator(f"#dv-s-{sid} .dv-holds").inner_text(),
              "the saved training's card does not say its napor")
        pg.goto(server + f"/karton#gt-{t.id}")
        row = pg.locator(f"#gt-{t.id}")
        row.locator("details.sets > summary").tap()
        lines = [" ".join(x.split()) for x in row.locator("details.sets li").all_inner_texts()]
        check([x.split(":")[0] for x in lines] == ["Goblet čučanj", "Plank", "Veslanje u pretklonu", "Sklekovi"],
              f"the diary's lines: {lines}")
        check(lines[0] == "Goblet čučanj: zadano 6 × 10 · 40 kg — odrađeno 10 × 40 kg · težina 8/10", lines[0])
        check(row.locator(".le-ex").inner_text() == "4 vježbe", "the count")
        browser.close()
    assert not problems and not errors, problems + errors


def test_kruzni_trening_on_a_phone(server):
    """"Kružni trening" at 390px, touch, on a training outside a termin:
    applied; its Stanica left for later; the Kružni set's rows filled (a
    pick each), its pause 45 s, "Kreni": Krug 1 open, its first values the
    plan; "Krug 1 odrađen": the pause counts 45 s, Krug 1 under its ✓
    still open with "Spremi izmjene", Krug 2 open under it; Krug 1
    corrected during the pause (no new pause), its correction Krug 2's
    first values; "+ krug" makes it "Krug 2 od 5". No page scrolls sideways
    at 390 or 360px (the set up, the started); at 1280px the block and the
    overview are two columns; the read-only page (a past termin's) at 360
    and 390px too. No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    ivan = make_user("ivan@test.local")
    db.reset_gym_templates()
    kruzni = db.gym_templates()[1].id
    for name in ("Goblet čučanj", "Plank", "Sklekovi"):
        db.create_exercise(name, "Upute za: " + name, tags="core")
    tid = db.add_gym_outside(ivan, config.today())
    db.apply_gym_template(tid, ivan, kruzni)
    _, k = db.gym_training(tid, ivan).blocks
    rows = [it.id for it in k.items]
    past = db.gym_training_for(ivan, termin(ivan, now() - timedelta(days=3)), staff=True)
    station(past, ivan, db.create_exercise("Iskorak"), 3, 10, staff=True)
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser, ctx, pg, errors = _phone(pw, server)

        def wide(where: str) -> None:
            for w, h in ((390, 844), (360, 780)):
                pg.set_viewport_size({"width": w, "height": h})
                check(pg.evaluate(OVERFLOW) == 0, f"{where} at {w}px overflows by {pg.evaluate(OVERFLOW)}px")
            pg.set_viewport_size({"width": 390, "height": 844})

        pg.goto(server + page_url(tid, blok=k.id))
        pg.wait_for_load_state("networkidle")
        wide("a Kružni set set up")
        for rid, (query, name, reps, kg, sec) in zip(rows, (("gob", "Goblet čučanj", 10, 16, ""),
                                                             ("skl", "Sklekovi", 12, "", ""),
                                                             ("plank", "Plank", "", "", 30))):
            box = pg.locator(f"#gt-r{rid}-q")
            box.tap()
            box.fill(query)
            pg.locator(f"#gt-r{rid}-list [role=option]", has_text=name).first.tap()
            for field, value in (("reps", reps), ("kg", kg), ("sec", sec)):
                if value != "":
                    pg.fill(f"#gt-r{rid}-{field}", str(value))
        pg.fill(f"#gt-p{k.id}-rest", "45")
        with pg.expect_navigation():
            pg.locator('form.gt-plan .gt-sgo button[name="kreni"]').tap()
        pg.wait_for_load_state("networkidle")
        check("krug=1" in pg.url, f"Kreni led to {pg.url}")
        one = pg.locator(f"#krug-{k.id}-1")
        check(one.get_attribute("open") is not None, "Krug 1 is not open")
        check(one.locator(f"input[name=kg_{rows[0]}]").input_value() == "16"
              and one.locator(f"input[name=sec_{rows[2]}]").input_value() == "30", "Krug 1's first values")
        check(pg.locator(".pl-round").inner_text().upper() == "KRUG 1 OD 4", "the head")
        wide("a Kružni set started")
        one.locator(f"input[name=reps_{rows[1]}]").fill("12")
        with pg.expect_navigation():
            one.locator("button.btn").tap()
        pg.wait_for_load_state("networkidle")
        check("spremljen=1" in pg.url and "odmor" not in pg.url, f"the address keeps the pause: {pg.url}")
        check(pg.locator("#plRest").is_visible() and pg.locator(".pl-rest-t").inner_text() in ("0:45", "0:44", "0:43"),
              "the pause after a Krug did not start")
        wide("a Krug saved, the pause bar showing")
        one, two = pg.locator(f"#krug-{k.id}-1"), pg.locator(f"#krug-{k.id}-2")
        check(one.get_attribute("open") is not None and "Spremi izmjene" in one.inner_text()
              and one.locator(".gt-kr-ok").count() == 1, "Krug 1 is not open under its ✓ with Spremi izmjene")
        check(two.get_attribute("open") is not None, "Krug 2 is not open under it")
        one.locator(f"input[name=reps_{rows[1]}]").fill("9")                # what she could not do
        with pg.expect_navigation():
            one.locator("button.btn-ghost").tap()
        pg.wait_for_load_state("networkidle")
        check(done_of(rows[1]) == [{"reps": 9, "kg": 0.0, "round": 1}], f"the correction: {done_of(rows[1])}")
        check(pg.locator("#plRest").is_visible(), "the correction ended the pause")
        check(pg.locator(f"#krug-{k.id}-2 input[name=reps_{rows[1]}]").input_value() == "9",
              "Krug 2 does not start from the correction")
        pg.locator(".pl-rest-skip").tap()
        with pg.expect_navigation():
            pg.locator(".gt-kctl form").nth(1).locator("button").tap()
        pg.wait_for_load_state("networkidle")
        check(pg.locator(".pl-round").inner_text().upper() == "KRUG 2 OD 5", "+ krug")
        pg.set_viewport_size({"width": 1280, "height": 900})
        main, side = pg.locator("#glavno").bounding_box(), pg.locator("#pregled").bounding_box()
        check(main["x"] + main["width"] <= side["x"] and abs(main["y"] - side["y"]) < 2,
              f"at 1280px not two columns: {main}, {side}")
        check(pg.evaluate(OVERFLOW) == 0, "at 1280px the page overflows")
        pg.goto(server + page_url(past))
        pg.wait_for_load_state("networkidle")
        wide("the read-only page")
        browser.close()
    assert not problems and not errors, problems + errors
