"""The player and the history (30.10.2026, stage 3 of
roadmap/2026-10-29-online-treninzi-spec.md).

The owner (29.–30.10.2026): a client does a day exercise by exercise, as on
Shape Club's Gym Program page; "the set log is good, yes, but default value
should be input like in shape club" (reps from the plan, kg from the last
saved log); "the whole list"; the swap among similar exercises, "we should
add it as well"; the tick is stored "so that we have a record of a user's
history. He can repeat the training if he wants"; the osvrt after an online
day asks "the same three for online, yes" (napor 1–10, osjećaj, komentar).

A pass (`WorkoutLog`) is opened by "Kreni" on a day (one in progress per
client and day: a partial unique index), filled exercise by exercise by the
player's "Spremi" (its set log, `done`), may swap an exercise for one of its
similar exercises (`swaps`), and is finished by the osvrt (its length the
server's clock) or dropped. The day says "odrađen N×" and lists the last five
passes with their sets, the programme's day cards say it too, and the karton
lists the passes beside the termini (the trainer's view with their sets).
Migration 3890252ee50f runs for real on qmt_test, there and back, and so does
b61e8d5bf1db (2.11.2026: a day reads "Trening N", and the passes' stored "Dan
N …" labels with it). The browser half walks ivan through a day on a phone.

The rest timers (30.10.2026; the owner: "a timer which he can skip, in
between sets as well as between exercises, which Shape Club also has"): a ✓
per set in the set log starts the rest between sets (the item's
rest_seconds) in a bar at the bottom; the rest after an exercise (the item's
rest_after_seconds) rides on the save's redirect (?odmor=) and starts on the
next exercise's screen. Both count down, skippable; nothing is stored.

Leaving a pass asks, and a pass cannot hang (31.10.2026; the owner: "When a
user tries to leave the training tab, there should be a popup warning asking
if he wants to finish the training and then he decides. It shouldn't be
possible to continue the training and have a hanging training of 9 hours"):
the player and the finish screen carry #leaveDlg (finish or discard, never
"later"), and a pass with no activity for PASS_STALE_HOURS (its start or its
last save) can only be finished, its length to its last save, or dropped.

A swap has a direction (4.11.2026; the owner: "Amir wants it so that he can
choose A -> B but not B -> A for some pairs"): the player offers the plan
exercise's own swaps (Exercise.alternatives), never an exercise that may
merely be swapped for it, and a client watches the clip of a swap's target
of an exercise in his day, not of one that only points at one of his.

An exercise deleted from the library (4.11.2026: it leaves every day that
held it) stays in the passes that saved it (their "Serije" name it), the
counts say the day as it is now, a similar exercise swapped in and deleted
gives the plan's back, and the player's k past the day's count leads to its
last exercise (or to the finish screen when none is left). A pass open on a
day left with no exercise keeps its way out, a day holding none counts a
pass as a deleted day does ("2 vježbe"), and a save names its item: one
from a page drawn before the day changed is refused.

An exercise may ask for reps and seconds together (24.11.2026, the owner:
"5 reps of 30 seconds of plank"): the set log's third shape (db.set_fields),
SET · PON. · SEK., each set stored {"reps": 5, "seconds": 30}, which the
history says "5 × 30 s".

A circuit is ticked a round at a time (25.11.2026; the owner's note to Amir:
"on označi koje krugove koje je odradio. Pauza ide na kraju kruga a između
vježbi nikakva pauza."): one screen per round, every exercise of the part on
it, one button saving the round whole (db.save_circuit_round), the rest after
the round alone. And each exercise may be rated (the owner: an exercise rated
"7 or harder then the next appearance of that particular exercise does not
increase its difficulty but stays the same or if its 9 or 10 out of 10
difficulty, then it gets slightly reduced"): the rating stored in the entry,
the load next time from it (db.next_load), the card saying so.
"""

from __future__ import annotations

import importlib.util
import io
import os
import pathlib
import re
import threading
import time
from datetime import datetime, timedelta
from html import unescape
from types import SimpleNamespace
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
from sqlalchemy.exc import IntegrityError

from qmt import auth, config, db
from qmt.models import Base, Booking, WorkoutLog, set_text
from qmt.web import app as web
from qmt.web.app import app

PORT = 8115    # test_copy's server is 8111, test_raspored_ui's and test_upitnik_ui's 8112, test_nav's 8113, test_programs' 8114

MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00\x00\x00\x08free"


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # media in a throwaway dir, never data/uploads nor a real R2 bucket
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "")
    yield


def make_user(email: str, is_trainer: bool = False, level: str = "pocetna") -> int:
    """An account; a client gets the online plan and an old upitnik (version
    1, all zero, its goal cijelo) whose razina is `level`, as
    tests/test_programs.py's: since 23.11.2026 a client sees every programme
    of his razina, whatever its type."""
    import json
    from datetime import date

    from qmt import upitnik

    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    db.update_profile(u.id, email.split("@")[0], "Test", date(1990, 1, 1), "")
    if is_trainer:
        db.set_trainer(email)
    else:
        db.record_payment(u.id, "online")
        picked = {q["key"]: 0 for q in upitnik.QUESTIONS_V1}
        db.save_onboarding(u.id, json.dumps(picked), 0, level, "cijelo", version=1, pain_level=None,
                           pain_high=False, needs_review=False, consented_at=None)
    return u.id


def client_for(email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"email": email, "password": "lozinka123"}, follow_redirects=False)
    assert r.status_code == 303, "login failed"
    return c


def people():
    """(trainer's id, ivan's, ana's): ivan početna (the day's razina), ana
    srednja (another razina: his programme is not hers)."""
    return (make_user("trener@test.local", is_trainer=True), make_user("ivan@test.local"),
            make_user("ana@test.local", level="srednja"))


def build_day(title: str = "Cijelo tijelo — početna", level: str | None = "pocetna", goal: str | None = "cijelo"):
    """A programme (ivan's razina by default) and its Trening 1 "Cijelo
    tijelo", in the day's display order:
      1 Čučanj s vlastitom težinom (zagrijavanje, 2 × 15, rest 30)
      2 Goblet čučanj (trening, 3 × 10, rest 60, "16 kg"; its swaps, one
        way: Iskorak unatrag, Čučanj s vlastitom težinom)
      3 Plank (trening, 3 × 40 s)
      4 Istezanje stražnje lože (istezanje, nothing asked)
    added out of that order, so the display order is the sections'."""
    names = ("Čučanj s vlastitom težinom", "Goblet čučanj", "Plank", "Istezanje stražnje lože", "Iskorak unatrag")
    existing = {e.name: e.id for e, _ in db.exercises()}              # a second programme reuses the library
    ex = {n: existing.get(n) or db.create_exercise(n) for n in names}
    db.update_exercise(ex["Goblet čučanj"], "Goblet čučanj", "Pete na podu.", "Do paralele i natrag.", "noge, bučice",
                       {ex["Iskorak unatrag"], ex["Čučanj s vlastitom težinom"]})
    pid = db.create_program(title, None, level, goal)
    did = db.add_day(pid)
    db.update_day(did, "Cijelo tijelo", 0, "")
    plan = {"Goblet čučanj": ("trening", 3, 10, None, 60, "16 kg"),
            "Čučanj s vlastitom težinom": ("zagrijavanje", 2, 15, None, 30, ""),
            "Plank": ("trening", 3, None, 40, None, ""),
            "Istezanje stražnje lože": ("istezanje", None, None, None, None, "")}
    ids = {}
    for name, (section, sets, reps, seconds, rest, note) in plan.items():
        ids[name] = db.add_day_item(did, ex[name], section)
        db.update_day_item(ids[name], section, sets, reps, seconds, rest, None, note)
    items = [ids[n] for n in names[:4]]
    return SimpleNamespace(pid=pid, did=did, items=items, ex=ex, base=f"/treninzi/{pid}/dan/{did}")


def item(d, k: int):
    """Exercise k of the day (1-based), the item as the routes load it."""
    return db.get_day_item(d.items[k - 1])


def open_pass(uid: int, d):
    return db.start_pass(uid, db.get_program(d.pid), db.get_day(d.did))


def save(uid: int, log_id: int, d, k: int, sets: list[dict]):
    it = item(d, k)
    swapped = db.get_pass(log_id, uid).swap_items.get(it.id)
    return db.save_sets(log_id, uid, it, sets, db.exercise(swapped) if swapped else it.exercise)


def finished(uid: int, d, sets_by_k: dict | None = None, effort: int = 6, feeling: str | None = "dobro",
             note: str = "", days_ago: int = 0, minutes: int | None = None) -> int:
    """A finished pass of uid's through d's day: each exercise k of
    `sets_by_k` saved, the osvrt given; moved `days_ago` days back, and
    `minutes` long when given. Its id."""
    log = open_pass(uid, d)
    for k, sets in (sets_by_k or {}).items():
        save(uid, log.id, d, k, sets)
    db.finish_pass(log.id, uid, effort, feeling, note)
    shift(log.id, days_ago, minutes)
    return log.id


def shift(log_id: int, days: int = 0, minutes: int | None = None) -> None:
    """Move a pass `days` back; with `minutes`, make it that long (its
    start that much before its finish)."""
    with db.engine.begin() as conn:
        conn.execute(sa_text("UPDATE workout_logs SET started_at = started_at - make_interval(days => :d), "
                             "finished_at = finished_at - make_interval(days => :d) WHERE id = :i"),
                     {"d": days, "i": log_id})
        if minutes is not None:
            conn.execute(sa_text("UPDATE workout_logs SET started_at = finished_at - make_interval(mins => :m), "
                                 "elapsed_seconds = :s WHERE id = :i"), {"m": minutes, "s": minutes * 60, "i": log_id})


def age(log_id: int, hours: float, saves_at: datetime | None = None) -> None:
    """Move a pass's start `hours` back; with `saves_at`, stamp every
    exercise it saved then (each `done` entry's "at", the JSON read and
    written back). `shift` moves the start and the finish only."""
    import json
    with db.engine.begin() as conn:
        conn.execute(sa_text("UPDATE workout_logs SET started_at = started_at - make_interval(secs => :s) "
                             "WHERE id = :i"), {"s": float(hours) * 3600, "i": log_id})
        if saves_at is not None:
            done = json.loads(conn.execute(sa_text("SELECT done FROM workout_logs WHERE id = :i"),
                                           {"i": log_id}).scalar_one())
            for entry in done.values():
                entry["at"] = saves_at.isoformat()
            conn.execute(sa_text("UPDATE workout_logs SET done = :d WHERE id = :i"),
                         {"d": json.dumps(done, ensure_ascii=False), "i": log_id})


def stored() -> list[tuple]:
    """workout_logs as stored: (id, user, day, finished?)."""
    with db.engine.connect() as conn:
        return [tuple(r) for r in conn.execute(sa_text(
            "SELECT id, user_id, day_id, finished_at IS NOT NULL FROM workout_logs ORDER BY id"))]


def location(r) -> str:
    """A redirect's location as a person reads it ("+" a space)."""
    return unquote(r.headers["location"]).replace("+", " ")


def inputs(page: str) -> list[tuple[str, str, str]]:
    """The set log's inputs, in order: (field, row, value)."""
    return re.findall(r'name="(reps|kg|sec)_(\d+)" value="([^"]*)"', page)


def alert(page: str) -> list[str]:
    return [unescape(x) for x in re.findall(r'<div class="alert" role="alert"><span>([^<]*)</span></div>', page)]


def read(markup: str) -> str:
    """Some markup as a reader reads it: tags dropped where they stand,
    entities read, whitespace collapsed (the pages' words are copy slots'
    spans since 25.11.2026, beside the values they name)."""
    return " ".join(unescape(re.sub(r"<[^>]+>", "", markup)).split())


def state_line(page: str) -> str | None:
    m = re.search(r'<p class="dx-state"[^>]*>(.*?)</p>', page, re.S)
    return read(m.group(1)) if m else None


def sub_lines(page: str) -> list[str]:
    """The card's muted lines under the dose (.pl-sub), as read."""
    return [read(x) for x in re.findall(r'<p class="pl-sub">(.*?)</p>', page, re.S)]


def hist_lines(page: str) -> list[str]:
    return [" ".join(unescape(x).split()) for x in re.findall(r'<p class="hist-line">(.*?)</p>', page, re.S)]


def sets_lines(chunk: str) -> list[str]:
    """The "Serije" lines of a piece of a page: "Goblet čučanj: 10 × 20 kg · …"."""
    return [unescape(re.sub(r"<[^>]+>", "", li)) for li in re.findall(r"<li><strong>.*?</li>", chunk, re.S)]


# ---------- the model: one pass in progress per client and day ----------

def test_one_pass_in_progress_per_client_and_day():
    """start_pass opens a pass (its snapshots: the programme's title, the
    day's label) and, while it is open, gives it back rather than another;
    the partial unique index refuses a second open row, not a finished one
    beside an open one, nor another day's or another client's."""
    trainer, ivan, ana = people()
    d = build_day()
    first = open_pass(ivan, d)
    again = open_pass(ivan, d)
    assert again.id == first.id and stored() == [(first.id, ivan, d.did, False)]
    assert (first.program_title, first.day_label, first.done_items, first.swap_items, first.in_progress) == (
        "Cijelo tijelo — početna", "Trening 1 · Cijelo tijelo", {}, {}, True)
    assert first.started_at is not None and first.finished_at is None and first.elapsed_seconds is None
    with pytest.raises(IntegrityError, match="uq_workout_logs_open"):
        with db.session_scope() as s:
            s.add(WorkoutLog(user_id=ivan, program_id=d.pid, day_id=d.did, program_title="x", day_label="y"))
    db.finish_pass(first.id, ivan, 6, None, "")
    second = open_pass(ivan, d)                                             # a finished one beside: a new pass
    other = db.add_day(d.pid)
    third = db.start_pass(ivan, db.get_program(d.pid), db.get_day(other))  # another day: its own
    fourth = open_pass(ana, d)                                              # another client: his own
    assert len({first.id, second.id, third.id, fourth.id}) == 4
    assert db.open_pass(ivan, d.did).id == second.id and db.open_pass(ana, d.did).id == fourth.id


def test_kreni_at_once_opens_one_pass():
    """Eight "Kreni" at once open one pass: each start_pass gives the same
    row back (the insert meets the partial index and does nothing)."""
    trainer, ivan, ana = people()
    d = build_day()
    got, errors = [], []

    def go():
        try:
            got.append(open_pass(ivan, d).id)
        except Exception as e:                                              # pragma: no cover - reported below
            errors.append(e)

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(set(got)) == 1 and len(stored()) == 1


def test_saves_at_once_keep_every_exercise():
    """Four exercises saved at once (four tabs) all land in the pass: each
    save takes the pass's row first, so none overwrites another's entry."""
    trainer, ivan, ana = people()
    d = build_day()
    log = open_pass(ivan, d)
    items = [item(d, k) for k in range(1, 5)]
    errors = []

    def go(it):
        try:
            timed = it.seconds is not None
            db.save_sets(log.id, ivan, it, [{"seconds": 30}] if timed else [{"reps": 5, "kg": 0.0}], it.exercise)
        except Exception as e:                                              # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=go, args=(it,)) for it in items]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and sorted(db.get_pass(log.id, ivan).done_items) == sorted(d.items)


# ---------- Kreni, Nastavi, the player's access ----------

def test_kreni_opens_a_pass_and_nastavi_goes_on_where_it_stopped():
    """"Kreni" (a form) opens a pass and lands on exercise 1; pressed again
    ("Nastavi") it lands on the first exercise the pass has not saved, the
    last when all are; a day with no exercise starts nothing. A rename or a
    deletion later never changes what the pass says it was."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    r = ci.post(f"{d.base}/kreni", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"{d.base}/vjezba/1"
    [(log_id, uid, day_id, done)] = stored()
    assert (uid, day_id, done) == (ivan, d.did, False)
    save(ivan, log_id, d, 1, [{"reps": 15, "kg": 0.0}])
    save(ivan, log_id, d, 3, [{"seconds": 40}])
    assert ci.post(f"{d.base}/kreni", follow_redirects=False).headers["location"] == f"{d.base}/vjezba/2"
    save(ivan, log_id, d, 2, [{"reps": 10, "kg": 20.0}])
    assert ci.post(f"{d.base}/kreni", follow_redirects=False).headers["location"] == f"{d.base}/vjezba/4"
    save(ivan, log_id, d, 4, [{"reps": 1, "kg": 0.0}])
    assert ci.post(f"{d.base}/kreni", follow_redirects=False).headers["location"] == f"{d.base}/vjezba/4"
    assert len(stored()) == 1

    empty = db.add_day(d.pid)
    r = ci.post(f"/treninzi/{d.pid}/dan/{empty}/kreni", follow_redirects=False)
    assert r.headers["location"] == f"/treninzi/{d.pid}/dan/{empty}" and len(stored()) == 1
    page = ci.get(f"/treninzi/{d.pid}/dan/{empty}").text
    assert "Trening još nema vježbi." in page and "/kreni" not in page and 'class="dx-state"' not in page

    db.update_program(d.pid, "Novo ime", None, "pocetna", "cijelo")
    db.update_day(d.did, "Drugi naslov", None, "")
    log = db.get_pass(log_id, ivan)
    assert (log.program_title, log.day_label) == ("Cijelo tijelo — početna", "Trening 1 · Cijelo tijelo")


def test_the_players_access():
    """The player follows the day's page: a guest goes to log in, another
    client's programme is 403, a day of another programme 404, an exercise
    below 1 404 and one past the day's count its last (4.11.2026); without
    a pass in progress the exercise, its save and the finish screen lead to
    the day's page (where Kreni is). Staff may use it: their pass is their
    own."""
    trainer, ivan, ana = people()
    d = build_day()
    other = build_day("Drugi", "srednja", "cijelo")
    ci, ca, ct = client_for("ivan@test.local"), client_for("ana@test.local"), client_for("trener@test.local")
    guest = TestClient(app)
    for path in (f"{d.base}/vjezba/1", f"{d.base}/kraj"):
        assert guest.get(path, follow_redirects=False).headers["location"] == "/login"
    assert guest.post(f"{d.base}/kreni", follow_redirects=False).headers["location"] == "/login"
    for r in (ci.get(f"{d.base}/vjezba/1", follow_redirects=False), ci.get(f"{d.base}/kraj", follow_redirects=False),
              ci.post(f"{d.base}/vjezba/1", data={"rows": "1", "reps_1": "5"}, follow_redirects=False),
              ci.post(f"{d.base}/kraj", data={"effort": "5"}, follow_redirects=False),
              ci.post(f"{d.base}/odustani", follow_redirects=False)):
        assert r.status_code == 303 and r.headers["location"] == d.base, r.request.url
    assert stored() == []
    for r in (ca.get(d.base), ca.post(f"{d.base}/kreni"), ca.get(f"{d.base}/vjezba/1"), ca.get(f"{d.base}/kraj"),
              ca.post(f"{d.base}/vjezba/1/zamjena", data={"vrati": "1"}), ca.post(f"{d.base}/odustani")):
        assert r.status_code == 403, r.request.url
    foreign = f"/treninzi/{d.pid}/dan/{other.did}"                          # other.did is another programme's
    for r in (ci.post(f"{foreign}/kreni"), ci.get(f"{foreign}/vjezba/1"), ci.get(f"{foreign}/kraj"),
              ci.post(f"{foreign}/odustani")):
        assert r.status_code == 404, r.request.url
    ci.post(f"{d.base}/kreni")
    assert ci.get(f"{d.base}/vjezba/0").status_code == 404
    assert ci.post(f"{d.base}/vjezba/0", data={"rows": "1", "reps_1": "5"}).status_code == 404
    for k in (5, 99):                                                       # past the day's 4: its last
        for r in (ci.get(f"{d.base}/vjezba/{k}", follow_redirects=False),
                  ci.post(f"{d.base}/vjezba/{k}", data={"rows": "1", "reps_1": "5"}, follow_redirects=False)):
            assert r.status_code == 303 and r.headers["location"] == f"{d.base}/vjezba/4", r.request.url
    assert db.open_pass(ivan, d.did).done_items == {}
    assert ci.get(f"{d.base}/vjezba/4").status_code == 200 and ci.get(f"{d.base}/kraj").status_code == 200
    assert ca.get(f"{d.base}/vjezba/1").status_code == 403                 # his pass is his
    r = ct.post(f"{d.base}/kreni", follow_redirects=False)
    assert r.headers["location"] == f"{d.base}/vjezba/1"
    page = ct.get(f"{d.base}/vjezba/1").text
    assert "<h1" in page and 'class="topbar compact"' not in page          # staff keep their bar
    assert sorted((u, done) for _, u, _, done in stored()) == [(trainer, False), (ivan, False)]
    assert 'class="topbar compact"' in ci.get(f"{d.base}/vjezba/1").text    # a member's one-task pill


# ---------- the set log: the prefill, the save ----------

def test_the_set_log_is_prefilled_from_the_plan_and_the_last_log():
    """A row per planned set (1 when the plan says none), its reps and
    seconds the plan's, its kg the last saved log's of that exercise (set
    i's, the last one's for a set past them; empty when none or 0), from any
    pass of the client's, another day's too; then one empty row more,
    "dodatna serija"; `rows` counts them."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    page = ci.get(f"{d.base}/vjezba/1").text
    assert inputs(page) == [("reps", "1", "15"), ("kg", "1", ""), ("reps", "2", "15"), ("kg", "2", ""),
                            ("reps", "3", ""), ("kg", "3", "")]
    assert '<input type="hidden" name="rows" value="3">' in page
    extra = '<span class="pl-x"><span class="t">dodatna serija</span></span>'
    assert re.findall(r'<th scope="row">(\d+)(' + re.escape(extra) + ')?</th>', page) == [("1", ""), ("2", ""), ("3", extra)]
    assert re.search(r'<thead><tr><th scope="col"><span class="t">Set</span></th><th scope="col"><span class="t">Pon\.</span></th>'
                     r'<th scope="col"><span class="t">Kg</span></th>'
                     r'<th scope="col" class="pl-tick" hidden>.*?</th></tr></thead>', page)
    page = ci.get(f"{d.base}/vjezba/3").text                               # Plank: 3 × 40 s
    assert inputs(page) == [("sec", "1", "40"), ("sec", "2", "40"), ("sec", "3", "40"), ("sec", "4", "")]
    assert '<th scope="col"><span class="t">Sek.</span></th>' in page and 'name="reps_1"' not in page
    page = ci.get(f"{d.base}/vjezba/4").text                               # nothing asked: one row
    assert inputs(page) == [("reps", "1", ""), ("kg", "1", ""), ("reps", "2", ""), ("kg", "2", "")]
    page = ci.get(f"{d.base}/vjezba/2").text                               # Goblet: never logged
    assert [v for f, _, v in inputs(page) if f == "kg"] == ["", "", "", ""]

    # Goblet logged on ANOTHER day (Trening 2): its weights fill Trening 1's rows
    d2 = db.add_day(d.pid)
    goblet2 = db.add_day_item(d2, d.ex["Goblet čučanj"], "trening")
    db.update_day_item(goblet2, "trening", 2, 8, None, None, None, "")
    other = db.start_pass(ivan, db.get_program(d.pid), db.get_day(d2))
    db.save_sets(other.id, ivan, db.get_day_item(goblet2), [{"reps": 8, "kg": 22.5}, {"reps": 8, "kg": 25.0}],
                 db.exercise(d.ex["Goblet čučanj"]))
    assert db.last_sets(ivan, d.ex["Goblet čučanj"]) == [{"reps": 8, "kg": 22.5}, {"reps": 8, "kg": 25.0}]
    page = ci.get(f"{d.base}/vjezba/2").text
    assert inputs(page) == [("reps", "1", "10"), ("kg", "1", "22.5"), ("reps", "2", "10"), ("kg", "2", "25"),
                            ("reps", "3", "10"), ("kg", "3", "25"), ("reps", "4", ""), ("kg", "4", "")]
    assert db.last_sets(ana, d.ex["Goblet čučanj"]) is None                # his log, not hers
    db.finish_pass(other.id, ivan, 5, None, "")                             # finished: still the last
    later = db.start_pass(ivan, db.get_program(d.pid), db.get_day(d2))
    db.save_sets(later.id, ivan, db.get_day_item(goblet2), [{"reps": 6, "kg": 0.0}], db.exercise(d.ex["Goblet čučanj"]))
    page = ci.get(f"{d.base}/vjezba/2").text                               # the newest: no weight
    assert [v for f, _, v in inputs(page) if f == "kg"] == ["", "", "", ""]


def test_the_set_log_is_read_saved_and_refused():
    """Spremi reads `rows` rows: reps 0–999, kg 0–500 in steps of 0.5
    ("2,5" and "2.5" both), a timed one's seconds 0–3600; a row with every
    field empty is dropped, an empty field beside a number is 0; then the
    next exercise, or the finish screen after the last. Refused (the
    screen again, 400, the sentence under the name, what was typed kept):
    a number out of its range or none ("Neispravan broj."), nothing left
    ("Upiši bar jednu seriju."), more than 12 ("Najviše 12 serija."). A
    re-save replaces the entry, which names the exercise and its section."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    form = {"rows": "4", "item": str(d.items[1]), "reps_1": "10", "kg_1": "2,5", "reps_2": "", "kg_2": "", "reps_3": "8", "kg_3": "2.5",
            "reps_4": "6", "kg_4": ""}
    r = ci.post(f"{d.base}/vjezba/2", data=form, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"{d.base}/vjezba/3"
    entry = db.get_pass(log_id, ivan).done_items[d.items[1]]
    assert (entry["exercise_id"], entry["name"], entry["section"]) == (d.ex["Goblet čučanj"], "Goblet čučanj", "trening")
    assert entry["sets"] == [{"reps": 10, "kg": 2.5}, {"reps": 8, "kg": 2.5}, {"reps": 6, "kg": 0.0}]
    assert datetime.fromisoformat(entry["at"]).tzinfo is not None
    page = ci.get(f"{d.base}/vjezba/2").text                               # saved: its sets in the inputs
    assert inputs(page) == [("reps", "1", "10"), ("kg", "1", "2.5"), ("reps", "2", "8"), ("kg", "2", "2.5"),
                            ("reps", "3", "6"), ("kg", "3", ""), ("reps", "4", ""), ("kg", "4", "")]
    assert '<span class="pl-saved"><span class="t">✓ Spremljeno</span></span>' in page

    sentences = {"Neispravan broj.": [{"kg_1": "2,25"}, {"reps_1": "1000"}, {"reps_1": "-1"}, {"kg_1": "501"},
                                      {"reps_1": "1.5"}, {"kg_1": "x"}, {"kg_1": "-0,5"}],
                 "Upiši bar jednu seriju.": [{"reps_1": "", "kg_1": ""}, {"reps_1": "  ", "kg_1": " "}]}
    for sentence, changes in sentences.items():
        for change in changes:
            r = ci.post(f"{d.base}/vjezba/2", data={"rows": "1", "item": str(d.items[1]), "reps_1": "10", "kg_1": "20", **change})
            assert r.status_code == 400 and alert(r.text) == [sentence], change
            assert re.search(r'<h1 class="pl-name" id="pl-name">Goblet čučanj</h1>\s*<div class="alert" role="alert">', r.text)
            kept = {**{"reps_1": "10", "kg_1": "20"}, **change}
            assert inputs(r.text) == [("reps", "1", kept["reps_1"]), ("kg", "1", kept["kg_1"].replace(",", "."))], change
    many = {"rows": "13", "item": str(d.items[1]), **{f"reps_{i}": "5" for i in range(1, 14)}}
    r = ci.post(f"{d.base}/vjezba/2", data=many)
    assert r.status_code == 400 and alert(r.text) == ["Najviše 12 serija."] and len(inputs(r.text)) == 26
    assert db.get_pass(log_id, ivan).done_items[d.items[1]]["sets"][0] == {"reps": 10, "kg": 2.5}   # untouched
    r = ci.post(f"{d.base}/vjezba/3", data={"rows": "2", "item": str(d.items[2]), "sec_1": "3601", "sec_2": ""})
    assert r.status_code == 400 and alert(r.text) == ["Neispravan broj."]
    r = ci.post(f"{d.base}/vjezba/3", data={"rows": "3", "item": str(d.items[2]), "sec_1": "40", "sec_2": "", "sec_3": "35"},
                follow_redirects=False)
    assert r.headers["location"] == f"{d.base}/vjezba/4"
    assert db.get_pass(log_id, ivan).done_items[d.items[2]]["sets"] == [{"seconds": 40}, {"seconds": 35}]

    r = ci.post(f"{d.base}/vjezba/2", data={"rows": "1", "item": str(d.items[1]), "reps_1": "12", "kg_1": "500"}, follow_redirects=False)
    log = db.get_pass(log_id, ivan)                                         # a re-save replaces the entry
    assert r.status_code == 303 and log.done_items[d.items[1]]["sets"] == [{"reps": 12, "kg": 500.0}]
    assert log.done_count == 2
    page = ci.get(f"{d.base}/vjezba/4").text
    assert '><span class="t">Spremi i završi</span></button>' in page
    r = ci.post(f"{d.base}/vjezba/4", data={"rows": "1", "item": str(d.items[3]), "reps_1": "1"},
                follow_redirects=False)
    assert r.headers["location"] == f"{d.base}/kraj"                       # after the last: the finish screen

    with pytest.raises(ValueError, match="Upiši bar jednu seriju."):
        db.read_sets([{"reps": "", "kg": ""}], ("reps", "kg"))
    assert db.read_sets([{"reps": "0", "kg": ""}, {"reps": "", "kg": "0,5"}], ("reps", "kg")) == [
        {"reps": 0, "kg": 0.0}, {"reps": 0, "kg": 0.5}]
    assert db.read_sets([{"seconds": "0"}, {"seconds": "3600"}], ("seconds",)) == [{"seconds": 0}, {"seconds": 3600}]
    for bad in ([{"reps": True, "kg": 0.0}], [{"reps": 1}], [{"reps": 1, "kg": 0.25}], [{"seconds": 1.5}], []):
        with pytest.raises(ValueError):
            db.save_sets(log_id, ivan, item(d, 2), bad, item(d, 2).exercise)


def test_an_exercise_of_reps_and_seconds_logs_both():
    """The set log's third shape (24.11.2026, the owner: "5 reps of 30
    seconds of plank"): db.set_fields says an item's fields, reps and kg for
    reps or no number, seconds for seconds, reps and seconds for both. Plank
    asking 3 × 5 × 30 s: SET · PON. · SEK. (· ✓), no KG column, a row per
    planned set prefilled with the plan's 5 and 30, one row more; Spremi
    stores each set {"reps": 5, "seconds": 30} (an empty field beside a
    number 0, a posted weight ignored) and the saved sets come back in the
    inputs; a refused number (400, the sentence) keeps what was typed and
    stores nothing; read_sets and save_sets take that shape and no other.
    The history says "5 × 30 s": the day's Povijest and the karton."""
    trainer, ivan, ana = people()
    d = build_day()
    db.update_day_item(d.items[2], "trening", 3, 5, 30, 60, None, "")
    assert [db.set_fields(item(d, k)) for k in (1, 2, 3, 4)] == [("reps", "kg"), ("reps", "kg"), ("reps", "seconds"),
                                                                  ("reps", "kg")]
    db.update_day_item(d.items[0], "zagrijavanje", 2, None, 30, None, None, "")
    assert db.set_fields(item(d, 1)) == ("seconds",)
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    page = ci.get(f"{d.base}/vjezba/3").text
    head = ('<th scope="col" class="pl-tick" hidden><span aria-hidden="true">✓</span>'
            '<span class="pl-sr">Odrađena serija</span></th></tr></thead>')
    assert (f'<thead><tr><th scope="col"><span class="t">Set</span></th><th scope="col"><span class="t">Pon.</span></th>'
            f'<th scope="col"><span class="t">Sek.</span></th>{head}') in page
    assert 'name="kg_' not in page and '<p class="pl-dose">3 × 5 × 30 s</p>' in page
    assert inputs(page) == [("reps", "1", "5"), ("sec", "1", "30"), ("reps", "2", "5"), ("sec", "2", "30"),
                            ("reps", "3", "5"), ("sec", "3", "30"), ("reps", "4", ""), ("sec", "4", "")]
    assert '<input type="hidden" name="rows" value="4">' in page
    assert len(re.findall(r'<td class="pl-tick" hidden><button type="button" class="pl-done"', page)) == 4

    form = {"rows": "4", "item": str(d.items[2]), "reps_1": "5", "sec_1": "30", "kg_1": "20", "reps_2": "5", "sec_2": "25",
            "reps_3": "4", "sec_3": "", "reps_4": "", "sec_4": ""}
    r = ci.post(f"{d.base}/vjezba/3", data=form, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"{d.base}/vjezba/4"
    sets = [{"reps": 5, "seconds": 30}, {"reps": 5, "seconds": 25}, {"reps": 4, "seconds": 0}]
    assert db.get_pass(log_id, ivan).done_items[d.items[2]]["sets"] == sets
    assert inputs(ci.get(f"{d.base}/vjezba/3").text) == [
        ("reps", "1", "5"), ("sec", "1", "30"), ("reps", "2", "5"), ("sec", "2", "25"), ("reps", "3", "4"), ("sec", "3", "0"),
        ("reps", "4", ""), ("sec", "4", "")]
    for change, kept in (({"sec_1": "3601"}, [("reps", "1", "5"), ("sec", "1", "3601")]),
                         ({"reps_1": "x"}, [("reps", "1", "x"), ("sec", "1", "30")]),
                         ({"reps_1": "1000", "sec_1": ""}, [("reps", "1", "1000"), ("sec", "1", "")])):
        r = ci.post(f"{d.base}/vjezba/3", data={"rows": "1", "item": str(d.items[2]), "reps_1": "5", "sec_1": "30", **change})
        assert r.status_code == 400 and alert(r.text) == ["Neispravan broj."] and inputs(r.text) == kept, change
    r = ci.post(f"{d.base}/vjezba/3", data={"rows": "1", "item": str(d.items[2]), "reps_1": "", "sec_1": "", "kg_1": "20"})
    assert r.status_code == 400 and alert(r.text) == ["Upiši bar jednu seriju."]
    assert db.get_pass(log_id, ivan).done_items[d.items[2]]["sets"] == sets                     # untouched

    assert db.read_sets([{"reps": "5", "seconds": "30"}, {"reps": "", "seconds": ""}, {"reps": "", "seconds": "20"}],
                        ("reps", "seconds")) == [{"reps": 5, "seconds": 30}, {"reps": 0, "seconds": 20}]
    for fields in (("kg",), ("reps", "kg", "seconds"), ()):
        with pytest.raises(ValueError, match="Neispravan broj."):
            db.read_sets([{"reps": "5", "kg": "5", "seconds": "5"}], fields)
    for bad in ([{"reps": 5, "kg": 0.0, "seconds": 30}], [{"reps": 5, "seconds": 30.5}], [{"reps": 1000, "seconds": 30}],
                [{"reps": 5, "seconds": 3601}], [{"kg": 5.0, "seconds": 30}]):
        with pytest.raises(ValueError):
            db.save_sets(log_id, ivan, item(d, 3), bad, item(d, 3).exercise)
    assert db.get_pass(log_id, ivan).done_items[d.items[2]]["sets"] == sets

    db.finish_pass(log_id, ivan, 6, None, "")
    first = ci.get(d.base).text.split('<li class="card hist-row">')[1]
    assert sets_lines(first) == ["Plank: 5 × 30 s · 5 × 25 s · 4 × 0 s"]
    karton = ci.get("/karton").text.split(f'id="pass-{log_id}"')[1].split('<div class="log-entry')[0].split("<aside")[0]
    assert sets_lines(karton) == ["Plank: 5 × 30 s · 5 × 25 s · 4 × 0 s"]


def test_skipping_saves_nothing_and_the_last_leads_to_the_end():
    """"Preskoči →" is a link to the next exercise (nothing saved); the
    last's is "Preskoči i završi", to the finish screen; ‹ › are links to
    the exercises beside it, none before the first nor after the last."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    first = ci.get(f"{d.base}/vjezba/1").text
    assert f'<a class="act act-quiet" href="{d.base}/vjezba/2"><span class="t">Preskoči →</span></a>' in first
    assert f'href="{d.base}/vjezba/2" rel="next" aria-label="Sljedeća vježba">›</a>' in first and 'rel="prev"' not in first
    middle = ci.get(f"{d.base}/vjezba/2").text
    assert f'href="{d.base}/vjezba/1" rel="prev"' in middle and f'href="{d.base}/vjezba/3" rel="next"' in middle
    last = ci.get(f"{d.base}/vjezba/4").text
    assert f'<a class="act act-quiet" href="{d.base}/kraj"><span class="t">Preskoči i završi</span></a>' in last and 'rel="next"' not in last
    assert f'<a class="act act-quiet" href="{d.base}"><span class="t">← Natrag</span></a>' in last
    assert f'<a class="act pl-end" href="{d.base}/kraj"><span class="t">Završi trening</span></a>' in last
    assert db.open_pass(ivan, d.did).done_items == {}


def test_the_bar_the_list_and_the_dock_say_where_the_client_is():
    """The segmented bar: a segment per exercise, a saved one "done", the
    one on screen "cur". The list: every exercise, each a link to it, the
    one on screen ringed (aria-current), a saved one a ✓ before its dose;
    the dock at the bottom counts the saved ones. The timer chip is the
    script's (hidden without it), its start the pass's."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    save(ivan, log_id, d, 1, [{"reps": 15, "kg": 0.0}])
    save(ivan, log_id, d, 4, [{"reps": 1, "kg": 0.0}])
    page = ci.get(f"{d.base}/vjezba/2").text
    assert '<div class="pl-segs" aria-hidden="true"><span class="done"></span><span class="cur"></span><span></span><span class="done"></span></div>' in page
    rows = re.findall(r'<li><a class="card pl-row( is-cur)?" href="([^"]+)"( aria-current="step")?>(.*?)</a></li>', page, re.S)
    assert [(cur, href, aria) for cur, href, aria, _ in rows] == [
        ("", f"{d.base}/vjezba/1", ""), (" is-cur", f"{d.base}/vjezba/2", ' aria-current="step"'),
        ("", f"{d.base}/vjezba/3", ""), ("", f"{d.base}/vjezba/4", "")]
    assert '<span class="dx-dose"><span class="dx-ok" role="img" aria-label="spremljeno">✓</span> 2 × 15</span>' in rows[0][3]
    assert '<span class="dx-dose"><span class="dx-ok" role="img" aria-label="spremljeno">✓</span></span>' in rows[3][3]
    assert "dx-ok" not in rows[1][3] and '<span class="dx-dose">3 × 10</span>' in rows[1][3]
    assert "Odmor između serija: 60 s · 16 kg" in read(rows[1][3])
    assert re.findall(r'<h3 class="dx-cap">([^<]*)</h3>', page) == ["Zagrijavanje", "Glavni dio A", "Istezanje"]
    assert '<a class="pl-dock" href="#popis"><span><span class="t">Vježbe</span> · 2/4 ✓</span></a>' in page
    assert re.search(r'<span class="pl-timer" hidden data-started="[0-9T:+-]+"', page)
    assert '<span class="pl-chip">2/4</span>' in page and '<p class="pl-dose">3 × 10</p>' in page
    assert '<p class="pl-sub"><span class="t">Odmor između serija:</span> 60 s</p>' in page and '<p class="pl-sub">16 kg</p>' in page
    assert ('<summary><span class="t">Kako se izvodi</span></summary>' in page
            and '<strong><span class="t">Jedno ponavljanje:</span></strong> Do paralele i natrag.' in page)
    assert "Kako se izvodi" not in ci.get(f"{d.base}/vjezba/3").text   # Plank: no rep note, no instructions


# ---------- the swap ----------

def test_an_exercise_is_swapped_for_a_similar_one_only():
    """"⇄ Zamijeni vježbu" lists the plan's exercise's similar exercises
    (name, tags, ⇄); one of them swaps in for this pass: the player shows
    its name, clip and cues, "Zamjena za: …" naming the plan's, "Vrati …"
    first in the list, the list's row its name "(zamjena)"; a save names it
    in the entry. Any other exercise is refused ("Ta vježba nije među
    sličnima."), and "vrati" puts the plan's back. Its clip is the client's
    to watch (a swap's target of one his programme holds)."""
    trainer, ivan, ana = people()
    d = build_day()
    ct, ci, ca = client_for("trener@test.local"), client_for("ivan@test.local"), client_for("ana@test.local")
    clip_r = ct.post(f"/treninzi/vjezbe/{d.ex['Iskorak unatrag']}/video",
                     files={"video": ("i.mp4", io.BytesIO(MP4), "video/mp4")}, follow_redirects=False)
    assert clip_r.status_code == 303
    clip = db.exercise(d.ex["Iskorak unatrag"]).video
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    page = ci.get(f"{d.base}/vjezba/2").text
    assert '<summary><span class="t">⇄ Zamijeni vježbu</span></summary>' in page
    assert re.findall(r'<span class="swap-name">([^<]*)(?:<span class="swap-tags">([^<]*)</span>)?</span>', page) == [
        ("Čučanj s vlastitom težinom", ""), ("Iskorak unatrag", "")]                # the alphabet's order: Č before I
    assert "Zamijeni vježbu" not in ci.get(f"{d.base}/vjezba/3").text     # Plank has no similar exercise

    r = ci.post(f"{d.base}/vjezba/2/zamjena", data={"exercise_id": str(d.ex["Plank"])}, follow_redirects=False)
    assert location(r) == f"{d.base}/vjezba/2?error=Ta vježba nije među sličnima."
    assert alert(ci.get(r.headers["location"]).text) == ["Ta vježba nije među sličnima."]
    for bad in ("", "x", "999999"):
        r = ci.post(f"{d.base}/vjezba/2/zamjena", data={"exercise_id": bad}, follow_redirects=False)
        assert "error=" in r.headers["location"]
    assert db.get_pass(log_id, ivan).swap_items == {}
    with pytest.raises(ValueError, match="Ta vježba nije među sličnima."):
        db.swap_exercise(log_id, ivan, item(d, 2), d.ex["Goblet čučanj"])   # not its own

    r = ci.post(f"{d.base}/vjezba/2/zamjena", data={"exercise_id": str(d.ex["Iskorak unatrag"])}, follow_redirects=False)
    assert r.headers["location"] == f"{d.base}/vjezba/2"
    assert db.get_pass(log_id, ivan).swap_items == {d.items[1]: d.ex["Iskorak unatrag"]}
    page = ci.get(f"{d.base}/vjezba/2").text
    assert '<h1 class="pl-name" id="pl-name">Iskorak unatrag</h1>' in page
    assert '<p class="pl-for"><span class="t">Zamjena za:</span> Goblet čučanj</p>' in page
    assert f'<video src="/media/{clip}" playsinline loop muted autoplay controls preload="metadata"></video>' in page
    assert re.search(r'<input type="hidden" name="vrati" value="1">\s*<button type="submit" class="act">'
                     r'<span><span class="t">Vrati</span> Goblet čučanj</span></button>', page)
    assert re.findall(r'<span class="swap-name">([^<]*)', page) == ["Čučanj s vlastitom težinom"]   # the swapped one not offered again
    assert 'Iskorak unatrag <span class="pl-swapped"><span class="t">(zamjena)</span></span>' in page
    assert '<p class="pl-dose">3 × 10</p>' in page                        # the plan's dose stays
    assert ci.get(f"/media/{clip}").status_code == 200 and ca.get(f"/media/{clip}").status_code == 403

    ci.post(f"{d.base}/vjezba/2", data={"rows": "1", "item": str(d.items[1]), "reps_1": "10", "kg_1": "8"})
    entry = db.get_pass(log_id, ivan).done_items[d.items[1]]
    assert (entry["exercise_id"], entry["name"], entry["sets"]) == (d.ex["Iskorak unatrag"], "Iskorak unatrag",
                                                                    [{"reps": 10, "kg": 8.0}])
    with pytest.raises(ValueError, match="Ta vježba nije među sličnima."):
        db.save_sets(log_id, ivan, item(d, 2), [{"reps": 1, "kg": 0.0}], db.exercise(d.ex["Plank"]))
    r = ci.post(f"{d.base}/vjezba/2/zamjena", data={"vrati": "1"}, follow_redirects=False)
    assert r.headers["location"] == f"{d.base}/vjezba/2" and db.get_pass(log_id, ivan).swap_items == {}
    page = ci.get(f"{d.base}/vjezba/2").text
    assert '<h1 class="pl-name" id="pl-name">Goblet čučanj</h1>' in page and "Zamjena za" not in page
    assert db.get_pass(log_id, ivan).done_items[d.items[1]]["name"] == "Iskorak unatrag"   # what was done stays


def test_a_swap_goes_one_way_only():
    """A swap has a direction (4.11.2026): Goblet čučanj's page ticks Čučanj
    s vlastitom težinom (build_day), so a client planned Goblet may do the
    plain squat, and one planned the plain squat (exercise 1) is offered no
    swap: Goblet posted there is refused ("Ta vježba nije među sličnima."),
    by the database's own check too. Ticked on the plain squat's page,
    Goblet is offered there and Goblet's own list stays; unticked on
    Goblet's page, the plain squat leaves Goblet's list and Goblet stays in
    the plain squat's. A clip is the client's to watch when its exercise is
    a swap's target of one in his day (Iskorak unatrag), never when it only
    points at one of his (a jump squat that may be swapped for Goblet, in
    no day: 403 to him; staff watch any)."""
    trainer, ivan, ana = people()
    d = build_day()
    ct, ci = client_for("trener@test.local"), client_for("ivan@test.local")
    goblet, plain, lunge = d.ex["Goblet čučanj"], d.ex["Čučanj s vlastitom težinom"], d.ex["Iskorak unatrag"]
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]

    def offered(k: int) -> list[str]:
        return re.findall(r'<span class="swap-name">([^<]*)', ci.get(f"{d.base}/vjezba/{k}").text)

    def form(eid: int, *ticked: int) -> None:
        """The exercise's page saved by the trainer, its texts as they are,
        these ticked."""
        e = db.exercise(eid)
        r = ct.post(f"/treninzi/vjezbe/{eid}", data={"name": e.name, "instructions": e.instructions,
                                                    "rep_note": e.rep_note, "tags": e.tags,
                                                    "alternative": [str(t) for t in ticked]}, follow_redirects=False)
        assert r.status_code == 303, r.text

    assert offered(1) == [] and "Zamijeni vježbu" not in ci.get(f"{d.base}/vjezba/1").text
    r = ci.post(f"{d.base}/vjezba/1/zamjena", data={"exercise_id": str(goblet)}, follow_redirects=False)
    assert location(r) == f"{d.base}/vjezba/1?error=Ta vježba nije među sličnima."
    with pytest.raises(ValueError, match="Ta vježba nije među sličnima."):
        db.swap_exercise(log_id, ivan, item(d, 1), goblet)
    assert db.get_pass(log_id, ivan).swap_items == {}

    form(plain, goblet)                                                   # the plain squat's own row: plain -> Goblet
    assert offered(1) == ["Goblet čučanj"] and offered(2) == ["Čučanj s vlastitom težinom", "Iskorak unatrag"]
    form(goblet, lunge)                                                   # Goblet's page drops Goblet -> plain
    assert offered(2) == ["Iskorak unatrag"] and offered(1) == ["Goblet čučanj"]
    r = ci.post(f"{d.base}/vjezba/2/zamjena", data={"exercise_id": str(plain)}, follow_redirects=False)
    assert location(r) == f"{d.base}/vjezba/2?error=Ta vježba nije među sličnima."
    r = ci.post(f"{d.base}/vjezba/1/zamjena", data={"exercise_id": str(goblet)}, follow_redirects=False)
    assert r.headers["location"] == f"{d.base}/vjezba/1"
    assert db.get_pass(log_id, ivan).swap_items == {d.items[0]: goblet}

    jump = db.create_exercise("Čučanj skok")
    form(jump, goblet)                                                    # the jump -> Goblet: it points at his
    clips = {}
    for eid in (lunge, jump):
        r = ct.post(f"/treninzi/vjezbe/{eid}/video", files={"video": ("v.mp4", io.BytesIO(MP4), "video/mp4")},
                    follow_redirects=False)
        assert r.status_code == 303
        clips[eid] = db.exercise(eid).video
    assert [p.id for p in db.video_programs(clips[lunge])] == [d.pid] and db.video_programs(clips[jump]) == []
    assert ci.get(f"/media/{clips[lunge]}").status_code == 200                # a target of Goblet, in his day
    assert ci.get(f"/media/{clips[jump]}").status_code == 403                 # only points at Goblet
    assert ct.get(f"/media/{clips[jump]}").status_code == 200                 # staff watch any


# ---------- the finish, the drop ----------

def test_the_finish_takes_the_osvrt_and_the_servers_clock():
    """The finish screen: "TRENING ODRAĐEN", the day, "1 od 4 vježbe ·
    N min", the osvrt (napor 1–10 required, osjećaj optional, a comment).
    Refused ("Neispravan osvrt.", 400, the alert under the title, what was
    chosen kept): no napor, outside 1–10, an osjećaj that is none. Saved,
    the pass is finished, its length the server's clock (finished −
    started, whatever is posted), and the day's page says so; a pass is
    finished once."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    page = ci.get(d.base).text
    assert state_line(page) == "Još nije odrađen." and '<span class="t">Kreni</span></button>' in page
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    save(ivan, log_id, d, 1, [{"reps": 15, "kg": 0.0}])
    with db.engine.begin() as conn:                                        # it started 38 minutes 10 s ago
        conn.execute(sa_text("UPDATE workout_logs SET started_at = now() - interval '38 minutes 10 seconds'"))
    page = ci.get(f"{d.base}/kraj").text
    assert '<p class="kr-eyebrow"><span class="t">Trening odrađen</span></p>' in page and "<h1>Trening 1 · Cijelo tijelo</h1>" in page
    assert '<p class="kr-sum">1 od 4 vježbe · 38 min</p>' in page
    assert len(re.findall(r'<input type="radio" name="effort" value="(\d+)" required>', page)) == 10
    assert re.findall(r'<input type="radio" name="feeling" value="(\w+)">', page) == ["slabo", "dobro", "odlicno"]
    assert f'<a class="act act-quiet" href="{d.base}/vjezba/4"><span class="t">Natrag na vježbe</span></a>' in page
    assert 'data-confirm-title="Odbaciti započeti trening?"' in page and '<span class="t">Odbaci trening</span></button>' in page
    assert 'data-confirm="Spremljene serije ovog pokušaja se brišu. Trening možeš započeti ponovno."' in page
    page = ci.get(d.base).text
    assert state_line(page) == "U tijeku — nastavi gdje si stao/la." and '<span class="t">Nastavi</span></button>' in page
    assert '<span class="t">Odbaci započeti trening</span></button>' in page
    assert 'data-confirm="Spremljene serije ovog pokušaja se brišu. Trening možeš započeti ponovno."' in page

    for form in ({"feeling": "dobro", "note": "x"}, {"effort": "0"}, {"effort": "11"}, {"effort": "abc"},
                 {"effort": "7", "feeling": "super"}):
        r = ci.post(f"{d.base}/kraj", data=form)
        assert r.status_code == 400 and alert(r.text) == ["Neispravan osvrt."], form
    r = ci.post(f"{d.base}/kraj", data={"effort": "7", "feeling": "super", "note": "Teško."})
    assert 'value="7" required checked>' in r.text and "Teško.</textarea>" in r.text
    r = ci.post(f"{d.base}/kraj", data={"effort": "11", "feeling": "dobro"})
    assert 'value="dobro" checked>' in r.text and not re.search(r'name="effort" value="\d+" required checked', r.text)
    assert db.get_pass(log_id, ivan).in_progress

    r = ci.post(f"{d.base}/kraj", data={"effort": "7", "feeling": "dobro", "note": "  Dobar trening.  ",
                                        "elapsed_seconds": "5"}, follow_redirects=False)
    assert location(r) == f"{d.base}?ok=Trening je spremljen."
    log = db.get_pass(log_id, ivan)
    assert not log.in_progress and (log.effort, log.feeling, log.note) == (7, "dobro", "Dobar trening.")
    assert 38 * 60 + 10 <= log.elapsed_seconds <= 38 * 60 + 20 and log.elapsed_text == "38 min"
    assert log.elapsed_seconds == int((log.finished_at - log.started_at).total_seconds())
    with pytest.raises(ValueError, match="Trening je već završen."):
        db.finish_pass(log_id, ivan, 5, None, "")
    with pytest.raises(ValueError, match="Trening je već završen."):
        db.save_sets(log_id, ivan, item(d, 2), [{"reps": 1, "kg": 0.0}], item(d, 2).exercise)
    r = ci.post(f"{d.base}/kraj", data={"effort": "3"}, follow_redirects=False)
    assert r.headers["location"] == d.base and db.get_pass(log_id, ivan).effort == 7
    page = ci.get(r.headers["location"] + "?ok=x").text
    assert state_line(page) == "Odrađen 1× · zadnji put danas" and '<span class="t">Kreni</span></button>' in page
    assert db.finish_pass(987654, ivan, 5, None, "") is False
    with pytest.raises(ValueError, match="Neispravan osvrt."):
        db.finish_pass(log_id, ivan, None, None, "")

    shift(log_id, days=1)
    assert state_line(ci.get(d.base).text) == "Odrađen 1× · zadnji put jučer"
    shift(log_id, days=6)
    last = (datetime.now(config.TZ) - timedelta(days=7)).date()
    assert state_line(ci.get(d.base).text) == (f"Odrađen 1× · zadnji put {last.day}.{last.month}."
                                               + (f"{last.year}." if last.year != config.today().year else ""))
    finished(ivan, d)
    assert state_line(ci.get(d.base).text) == "Odrađen 2× · zadnji put danas"


def test_odbaci_drops_the_pass_in_progress_only():
    """"Odbaci" deletes the pass in progress and what it saved (the day's
    page says so); a finished pass is never deleted that way."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    done_id = finished(ivan, d, {1: [{"reps": 15, "kg": 0.0}]})
    ci.post(f"{d.base}/kreni")
    open_id = db.open_pass(ivan, d.did).id
    save(ivan, open_id, d, 2, [{"reps": 10, "kg": 20.0}])
    assert db.drop_pass(done_id, ivan) is False and db.drop_pass(open_id, ana) is False
    r = ci.post(f"{d.base}/odustani", follow_redirects=False)
    assert location(r) == f"{d.base}?ok=Započeti trening je odbačen."
    assert [(i, done) for i, _, _, done in stored()] == [(done_id, True)]
    assert db.last_sets(ivan, d.ex["Goblet čučanj"]) is None               # what it saved went with it
    r = ci.post(f"{d.base}/odustani", follow_redirects=False)              # nothing in progress: nothing to say
    assert r.headers["location"] == d.base and len(stored()) == 1


# ---------- the day's page, the programme's, the karton ----------

def test_the_day_page_lists_the_last_five_passes_with_their_sets():
    """Povijest: the client's last five passes of the day, newest first:
    "12.11. · 6/8 vježbi · 38 min · napor 7 · dobro", the comment under it,
    and "Serije", each exercise's sets in the day's order ("Goblet čučanj:
    10 × 20 kg · 8 × 20 kg", "Plank: 40 s · 40 s", a set with no weight its
    reps alone, a half kilo with a comma). Another client's passes are not
    his; a day never done has no Povijest."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    assert 'id="povijest"' not in ci.get(d.base).text
    for n in range(6):
        finished(ivan, d, {1: [{"reps": 15, "kg": 0.0}]}, effort=n + 1, feeling=None, days_ago=20 - n, minutes=30 + n)
    newest = finished(ivan, d, {3: [{"seconds": 40}, {"seconds": 40}], 2: [{"reps": 10, "kg": 20.0}, {"reps": 8, "kg": 20.0}],
                                1: [{"reps": 15, "kg": 0.0}, {"reps": 15, "kg": 2.5}]},
                      effort=7, feeling="odlicno", note="Lakše nego prošli put.", days_ago=2, minutes=38)
    finished(ana, build_day("Gornji", "srednja", "gornji"), {1: [{"reps": 1, "kg": 0.0}]})
    page = ci.get(d.base).text
    day = (datetime.now(config.TZ) - timedelta(days=2)).date()
    lines = hist_lines(page)
    assert len(lines) == 5 and lines[0] == f"{day.day}.{day.month}. · 3/4 vježbe · 38 min · napor 7 · odlično"
    assert lines[1].endswith("· 1/4 vježbe · 35 min · napor 6") and lines[4].endswith("· 1/4 vježbe · 32 min · napor 3")
    assert '<p class="hist-note">Lakše nego prošli put.</p>' in page
    first = page.split('<li class="card hist-row">')[1]
    assert sets_lines(first) == ["Čučanj s vlastitom težinom: 15 · 15 × 2,5 kg",
                                 "Goblet čučanj: 10 × 20 kg · 8 × 20 kg", "Plank: 40 s · 40 s"]
    assert '<summary><span class="t">Serije</span></summary>' in first
    assert state_line(page) == f"Odrađen 7× · zadnji put {day.day}.{day.month}." + (
        f"{day.year}." if day.year != config.today().year else "")
    assert [w.id for w in db.passes(ivan, d.did, limit=1)] == [newest]


def test_the_programme_page_says_each_days_state(monkeypatch):
    """Each day card's muted line: "… · odrađen 2×" for a day done, "… · u
    tijeku" while a pass is open, "… · nedovršen" for a pass open too long
    (31.10.2026: no activity for PASS_STALE_HOURS), nothing for a day never
    done."""
    monkeypatch.setattr(config, "PASS_STALE_HOURS", 2)
    trainer, ivan, ana = people()
    d = build_day()
    d2 = db.add_day(d.pid)
    d3 = db.add_day(d.pid)
    db.add_day_item(d3, d.ex["Plank"], "trening")
    d4 = db.add_day(d.pid)
    db.add_day_item(d4, d.ex["Plank"], "trening")
    ci = client_for("ivan@test.local")
    finished(ivan, d)
    finished(ivan, d)
    p, day3 = db.get_program(d.pid), db.get_day(d3)
    db.start_pass(ivan, p, day3)
    age(db.start_pass(ivan, p, db.get_day(d4)).id, 3)
    page = ci.get(f"/treninzi/{d.pid}").text
    cards = [(day, read(hint)) for day, hint in re.findall(
        r'<strong>([^<]*)</strong>\s*<span class="hint">(.*?)</span>\s*</span>\s*<span class="dc-go"', page, re.S)]
    assert cards == [("Trening 1 · Cijelo tijelo", "Preporučeno: ponedjeljak · 4 vježbe · odrađen 2×"),
                     ("Trening 2", "0 vježbi"), ("Trening 3", "1 vježba · u tijeku"),
                     ("Trening 4", "1 vježba · nedovršen")]
    assert db.day_states(ivan, [d.did, d2, d3])[d.did]["count"] == 2 and d2 not in db.day_states(ivan, [d2])
    assert [read(h) for h in re.findall(r'<span class="hint">(.*?)</span>\s*</span>\s*<span class="dc-go"', client_for(
        "ana@test.local").get(f"/treninzi/{build_day('Njen', 'srednja', 'gornji').pid}").text, re.S)] == [
        "Preporučeno: ponedjeljak · 4 vježbe"]


def attended_session(uid: int, starts: datetime) -> int:
    """A finished termin the client was booked into (booked directly:
    book() rightly refuses past sessions)."""
    sid = db.add_oneoff_session("Grupni trening", starts, 60, 8, None)
    with db.session_scope() as s:
        s.add(Booking(user_id=uid, session_id=sid))
    return sid


def test_the_karton_lists_the_passes_among_the_termini():
    """The diary holds the client's finished passes beside his termini, by
    when they started, newest first (_diary_rows): the kicker "Online
    trening", the day and the programme as named when it started, "N od M
    vježbi · X min" (a day since deleted: "N vježbi"), napor and osjećaj as
    a termin's, the comment, and its sets folded under "Serije": the
    trainer's view's until 23.11.2026, the client's too since (Amir: "u
    kartonu može ući u povijest svojih treninga"). A pass in progress is not
    there."""
    trainer, ivan, ana = people()
    d = build_day()
    now = datetime.now(config.TZ)
    old_termin = attended_session(ivan, now - timedelta(days=5, hours=2))
    new_termin = attended_session(ivan, now - timedelta(days=1, hours=3))
    db.add_session_feedback(ivan, new_termin, 6, "dobro", "Termin.")
    a = finished(ivan, d, {2: [{"reps": 10, "kg": 20.0}, {"reps": 8, "kg": 20.0}], 3: [{"seconds": 40}]},
                 effort=7, feeling="odlicno", note="Online.", days_ago=3, minutes=38)
    b = finished(ivan, d, {1: [{"reps": 15, "kg": 0.0}]}, effort=5, feeling="slabo", days_ago=0, minutes=65)
    db.start_pass(ivan, db.get_program(d.pid), db.get_day(d.did))         # in progress: not in the diary
    rows = web._diary_rows(ivan)
    kinds = [("pass", r["workout"].id) if r.get("workout") else ("termin", r["session"].id) for r in rows]
    assert kinds == [("pass", b), ("termin", new_termin), ("pass", a), ("termin", old_termin)]
    assert [r["at"] for r in rows] == sorted((r["at"] for r in rows), reverse=True)
    assert rows[0]["size"] == 4

    def entry(page: str, log_id: int) -> str:
        return page.split(f'id="pass-{log_id}"')[1].split('<div class="log-entry')[0]

    page = client_for("ivan@test.local").get("/karton").text
    row = entry(page, a)
    # the karton's own words are copy slots since 25.11.2026, each in a span
    # (a member's span.t; the trainer's view, an editor's, its span.ed.t)
    assert '<div class="le-kicker"><span class="t">Online trening</span></div>' in row
    assert '<div class="hint le-sub">Trening 1 · Cijelo tijelo — Cijelo tijelo — početna</div>' in row
    assert '<div class="hint le-sub">2 od 4 vježbe · 38 min</div>' in row
    assert '<span class="rpe">napor 7/10</span>' in row and '<span class="rpe feel ">Odlično</span>' in row
    assert "<p>Online.</p>" in row and '<summary><span class="t">Serije</span></summary>' in row
    assert sets_lines(row) == ["Goblet čučanj: 10 × 20 kg · 8 × 20 kg", "Plank: 40 s"]
    assert '<div class="hint le-sub">1 od 4 vježbe · 1 h 05 min</div>' in entry(page, b)
    assert '<span class="rpe feel low">Slabo</span>' in entry(page, b)
    assert "Uredi" not in row and "Obriši" not in row and "/delete" not in row   # nothing edits a pass here
    assert page.count('class="log-entry online"') == 2

    page = client_for("trener@test.local").get(f"/karton/{ivan}").text
    row = entry(page, a)
    assert re.search(r'<summary><span class="ed t" data-copy="karton\.diary\.sets"[^>]*>Serije</span></summary>', row)
    assert sets_lines(row) == ["Goblet čučanj: 10 × 20 kg · 8 × 20 kg", "Plank: 40 s"]
    db.delete_day(d.did)                                                   # the day gone: the pass stays
    page = client_for("ivan@test.local").get("/karton").text
    assert '<div class="hint le-sub">2 vježbe · 38 min</div>' in entry(page, a)
    assert '<div class="hint le-sub">Trening 1 · Cijelo tijelo — Cijelo tijelo — početna</div>' in entry(page, a)
    assert db.get_pass(a, ivan).day_id is None


# ---------- an exercise deleted from the library (4.11.2026) ----------

def test_a_pass_keeps_an_exercise_deleted_from_the_library():
    """Deleted from the library, an exercise leaves the day, and a pass
    that saved it keeps its entry (`done` is a snapshot: the name, the
    sets), listed by name in "Serije", after the day's own. The counts say
    the day as it is now (n: the entries whose exercise is still in the
    day; N: the day's exercises now): the day page's Povijest "3/3 vježbe",
    the karton's "3 od 3 vježbe", and a pass in progress its finish
    screen's "1 od 3 vježbe", the player's dock and chip; once the day is
    gone the karton counts every entry, "4 vježbe"."""
    trainer, ivan, ana = people()
    d = build_day()
    ci, ct = client_for("ivan@test.local"), client_for("trener@test.local")
    done_id = finished(ivan, d, {1: [{"reps": 15, "kg": 0.0}], 2: [{"reps": 10, "kg": 20.0}],
                                 3: [{"seconds": 40}, {"seconds": 40}], 4: [{"reps": 1, "kg": 0.0}]}, minutes=38)
    ci.post(f"{d.base}/kreni")
    open_id = db.open_pass(ivan, d.did).id
    save(ivan, open_id, d, 2, [{"reps": 10, "kg": 20.0}])
    save(ivan, open_id, d, 3, [{"seconds": 40}])
    assert db.delete_exercise(d.ex["Plank"]) == (None, 1)
    kept = db.get_pass(done_id, ivan).done_items
    assert len(kept) == 4 and (kept[d.items[2]]["name"], kept[d.items[2]]["sets"]) == (
        "Plank", [{"seconds": 40}, {"seconds": 40}])

    page = ci.get(d.base).text
    listed = page.split('id="povijest"')[0]                                # the day's list, before Povijest
    assert [unescape(n) for n in re.findall(r'<span class="dx-name">([^<]*)</span>', listed)] == [
        "Čučanj s vlastitom težinom", "Goblet čučanj", "Istezanje stražnje lože"]
    [line] = hist_lines(page)
    assert line.split(" · ", 1)[1] == "3/3 vježbe · 38 min · napor 6 · dobro"
    first = page.split('<li class="card hist-row">')[1]
    assert sets_lines(first) == ["Čučanj s vlastitom težinom: 15", "Goblet čučanj: 10 × 20 kg",
                                 "Istezanje stražnje lože: 1", "Plank: 40 s · 40 s"]

    def entry(page: str, log_id: int) -> str:
        return page.split(f'id="pass-{log_id}"')[1].split('<div class="log-entry')[0]

    assert '<div class="hint le-sub">3 od 3 vježbe · 38 min</div>' in entry(ci.get("/karton").text, done_id)
    row = entry(ct.get(f"/karton/{ivan}").text, done_id)
    assert '<div class="hint le-sub">3 od 3 vježbe · 38 min</div>' in row and "Plank: 40 s · 40 s" in sets_lines(row)
    assert re.search(r'<p class="kr-sum">1 od 3 vježbe · \d+ min</p>', ci.get(f"{d.base}/kraj").text)
    page = ci.get(f"{d.base}/vjezba/2").text
    assert '<a class="pl-dock" href="#popis"><span><span class="t">Vježbe</span> · 1/3 ✓</span></a>' in page and '<span class="pl-chip">2/3</span>' in page

    db.delete_day(d.did)                                                   # the day gone: every entry counts
    assert '<div class="hint le-sub">4 vježbe · 38 min</div>' in entry(ci.get("/karton").text, done_id)


def test_a_swapped_in_exercise_deleted_gives_the_plans_back():
    """A similar exercise swapped in for this pass, then deleted from the
    library: the pass's swap points at nothing, and the player falls back
    to the plan's exercise (its name, no "Zamjena za", no "(zamjena)" in
    the list, no "Vrati …"; the swap list its similar ones left), a save
    names the plan's; what the pass saved of the swapped one stays."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    ci.post(f"{d.base}/vjezba/2/zamjena", data={"exercise_id": str(d.ex["Iskorak unatrag"])})
    ci.post(f"{d.base}/vjezba/2", data={"rows": "1", "item": str(d.items[1]), "reps_1": "10", "kg_1": "8"})
    assert db.get_pass(log_id, ivan).done_items[d.items[1]]["name"] == "Iskorak unatrag"
    assert db.delete_exercise(d.ex["Iskorak unatrag"]) == (None, 0)        # only similar: no day held it
    assert db.get_pass(log_id, ivan).swap_items == {d.items[1]: d.ex["Iskorak unatrag"]}
    page = ci.get(f"{d.base}/vjezba/2").text
    assert '<h1 class="pl-name" id="pl-name">Goblet čučanj</h1>' in page
    assert "Zamjena za" not in page and "(zamjena)" not in page and 'name="vrati"' not in page
    assert re.findall(r'<span class="swap-name">([^<]*)', page) == ["Čučanj s vlastitom težinom"]
    assert '<p class="pl-dose">3 × 10</p>' in page
    assert db.get_pass(log_id, ivan).done_items[d.items[1]]["name"] == "Iskorak unatrag"   # what was saved stays
    r = ci.post(f"{d.base}/vjezba/2", data={"rows": "1", "item": str(d.items[1]), "reps_1": "10", "kg_1": "16"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith(f"{d.base}/vjezba/3")
    entry = db.get_pass(log_id, ivan).done_items[d.items[1]]
    assert (entry["exercise_id"], entry["name"], entry["sets"]) == (d.ex["Goblet čučanj"], "Goblet čučanj",
                                                                    [{"reps": 10, "kg": 16.0}])


def test_a_k_past_the_days_count_leads_to_its_last_exercise():
    """An exercise deleted from the day while a pass is open: the player's
    k past the day's count (a page counting the old list) goes to the
    day's last exercise, its screen, its save and its swap alike (saving
    and swapping nothing), or to the finish screen once the day has none
    left (its sum then the deleted day's words, "0 vježbi"); k below 1
    stays 404, and without a pass in progress any k leads to the day's
    page."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    swap_to = {"exercise_id": str(d.ex["Iskorak unatrag"])}
    for r in (ci.get(f"{d.base}/vjezba/9", follow_redirects=False),
              ci.post(f"{d.base}/vjezba/9/zamjena", data=swap_to, follow_redirects=False)):
        assert r.status_code == 303 and r.headers["location"] == d.base, r.request.url
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    assert db.delete_exercise(d.ex["Goblet čučanj"]) == (None, 1)
    for k in (4, 5, 99):
        for r in (ci.get(f"{d.base}/vjezba/{k}", follow_redirects=False),
                  ci.post(f"{d.base}/vjezba/{k}", data={"rows": "1", "reps_1": "5"}, follow_redirects=False),
                  ci.post(f"{d.base}/vjezba/{k}/zamjena", data=swap_to, follow_redirects=False)):
            assert r.status_code == 303 and r.headers["location"] == f"{d.base}/vjezba/3", r.request.url
    log = db.get_pass(log_id, ivan)
    assert log.done_items == {} and log.swap_items == {}
    assert ci.get(f"{d.base}/vjezba/0").status_code == 404
    assert ci.post(f"{d.base}/vjezba/0/zamjena", data=swap_to).status_code == 404
    page = ci.get(f"{d.base}/vjezba/3").text
    assert '<span class="pl-chip">3/3</span>' in page
    assert '<h1 class="pl-name" id="pl-name">Istezanje stražnje lože</h1>' in page
    for name in ("Čučanj s vlastitom težinom", "Plank", "Istezanje stražnje lože"):
        db.delete_exercise(d.ex[name])
    for r in (ci.get(f"{d.base}/vjezba/1", follow_redirects=False),
              ci.post(f"{d.base}/vjezba/1", data={"rows": "1", "reps_1": "5"}, follow_redirects=False),
              ci.post(f"{d.base}/vjezba/1/zamjena", data=swap_to, follow_redirects=False)):
        assert r.status_code == 303 and r.headers["location"] == f"{d.base}/kraj", r.request.url
    page = ci.get(f"{d.base}/kraj").text
    assert re.search(r'<p class="kr-sum">0 vježbi · \d+ min</p>', page)
    assert f'<a class="act act-quiet" href="{d.base}"><span class="t">Natrag na vježbe</span></a>' in page
    assert db.get_pass(log_id, ivan).in_progress


def test_a_pass_open_on_a_day_left_empty_keeps_its_way_out(monkeypatch):
    """A pass open on a day whose exercises have all been deleted from the
    library since: the day page still says it ("U tijeku — …") and keeps
    its way out, "Nastavi" (to the finish screen: nothing is left to do)
    and "Odbaci započeti trening", never "Kreni"; once stale, "Završi
    trening" and Odbaci. Counted against a day that holds no exercise now,
    a pass says what it saved as a deleted day's does, "2 vježbe": the
    finish screen's sum, the stale sentence, Povijest and the karton. With
    the pass finished, the empty day offers nothing to start."""
    monkeypatch.setattr(config, "PASS_STALE_HOURS", 2)
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    save(ivan, log_id, d, 1, [{"reps": 15, "kg": 0.0}])
    save(ivan, log_id, d, 3, [{"seconds": 40}])
    for name in ("Čučanj s vlastitom težinom", "Goblet čučanj", "Plank", "Istezanje stražnje lože"):
        db.delete_exercise(d.ex[name])
    page = ci.get(d.base).text
    assert "Trening još nema vježbi." in page and state_line(page) == "U tijeku — nastavi gdje si stao/la."
    assert '<span class="t">Nastavi</span></button>' in page and '<span class="t">Kreni</span></button>' not in page
    assert '<span class="t">Odbaci započeti trening</span></button>' in page
    r = ci.post(f"{d.base}/kreni", follow_redirects=False)                # Nastavi: nothing left but the end
    assert r.status_code == 303 and r.headers["location"] == f"{d.base}/kraj" and len(stored()) == 1
    assert re.search(r'<p class="kr-sum">2 vježbe · \d+ min</p>', ci.get(f"{d.base}/kraj").text)

    started = db.get_pass(log_id, ivan).started_at - timedelta(hours=3)
    age(log_id, 3, saves_at=started + timedelta(minutes=25))
    began = started.astimezone(config.TZ).date()
    when = "danas" if began == config.today() else "jučer"
    page = ci.get(d.base).text
    assert state_line(page) == f"Nedovršen trening od {when} (2 vježbe) — nastavak nije moguć: završi ga ili ga odbaci."
    assert f'<div class="go"><a class="btn" href="{d.base}/kraj"><span class="t">Završi trening</span></a></div>' in page
    assert '<span class="t">Odbaci započeti trening</span></button>' in page and '<span class="t">Nastavi</span></button>' not in page
    assert '<p class="kr-sum">2 vježbe · 25 min</p>' in ci.get(f"{d.base}/kraj").text
    ci.post(f"{d.base}/kraj", data={"effort": "6"})
    page = ci.get(d.base).text
    assert hist_lines(page)[0].split(" · ", 1)[1] == "2 vježbe · 25 min · napor 6"
    assert state_line(page).startswith("Odrađen 1×") and 'class="dx-start"' not in page
    karton = ci.get("/karton").text.split(f'id="pass-{log_id}"')[1].split('<div class="log-entry')[0]
    assert '<div class="hint le-sub">2 vježbe · 25 min</div>' in karton


def test_a_save_from_a_page_drawn_before_the_day_changed_is_refused():
    """The set log names its item (a hidden `item`): a save whose item is
    not exercise k's now (its exercise deleted from the day between the
    page and its Spremi), or that names none, is refused, nothing saved:
    the screen again (exercise k as it is now), 400, "Trening se u
    međuvremenu promijenio — provjeri vježbu i spremi ponovno." under the
    name, what was typed kept. Saved again from that screen, it goes
    through."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    assert f'<input type="hidden" name="item" value="{d.items[0]}">' in ci.get(f"{d.base}/vjezba/1").text
    db.delete_exercise(d.ex["Čučanj s vlastitom težinom"])                  # exercise 1 is Goblet čučanj now
    assert web.DAY_CHANGED == "Trening se u međuvremenu promijenio — provjeri vježbu i spremi ponovno."
    typed = {"rows": "2", "reps_1": "12", "kg_1": "2,5", "reps_2": "10", "kg_2": "5"}
    for posted in ({**typed, "item": str(d.items[0])}, typed):               # the page's item; none at all
        r = ci.post(f"{d.base}/vjezba/1", data=posted)
        assert r.status_code == 400 and alert(r.text) == [web.DAY_CHANGED]
        assert re.search(r'<h1 class="pl-name" id="pl-name">Goblet čučanj</h1>\s*<div class="alert" role="alert">', r.text)
        assert inputs(r.text) == [("reps", "1", "12"), ("kg", "1", "2.5"), ("reps", "2", "10"), ("kg", "2", "5")]
        assert f'<input type="hidden" name="item" value="{d.items[1]}">' in r.text
    assert db.get_pass(log_id, ivan).done_items == {}
    r = ci.post(f"{d.base}/vjezba/1", data={**typed, "item": str(d.items[1])}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"{d.base}/vjezba/2"
    assert db.get_pass(log_id, ivan).done_items[d.items[1]]["sets"] == [{"reps": 12, "kg": 2.5}, {"reps": 10, "kg": 5.0}]


# ---------- the rest timers (30.10.2026) ----------

def form_tag(page: str) -> str:
    """The set log's <form> tag, its attributes."""
    return re.search(r'<form class="pl-log" id="plLog"[^>]*>', page).group(0)


def test_the_rest_after_an_exercise_comes_with_the_next_one():
    """Spremi on exercise k < last goes on to k + 1 with ?odmor=<seconds>
    when the plan's item has a rest after it (a swapped exercise's save
    too: the plan's item says it), plainly when it has none or 0; the
    last's goes to /kraj without it. The player's GET puts an odmor of 1–
    3600 on the form as data-odmor and ignores anything else; a refused
    save (400) carries none. The form carries the rest between sets
    (data-rest) when the plan has one, not for none or 0. The card's line
    prints both rests, the list's both and the note."""
    trainer, ivan, ana = people()
    d = build_day()
    db.update_day_item(d.items[0], "zagrijavanje", 2, 15, None, 30, 0, "")          # 0 after it: none
    db.update_day_item(d.items[1], "trening", 3, 10, None, 60, 90, "16 kg")
    db.update_day_item(d.items[2], "trening", 3, None, 40, 0, None, "")              # 0 between sets: none
    db.update_day_item(d.items[3], "istezanje", None, None, None, None, 120, "")     # the last: never carried
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    steps = ((1, {"reps_1": "15"}, f"{d.base}/vjezba/2"), (2, {"reps_1": "10", "kg_1": "16"}, f"{d.base}/vjezba/3?odmor=90"),
             (3, {"sec_1": "40"}, f"{d.base}/vjezba/4"), (4, {"reps_1": "1"}, f"{d.base}/kraj"))
    for k, sets, to in steps:
        r = ci.post(f"{d.base}/vjezba/{k}", data={"rows": "1", "item": str(d.items[k - 1]), **sets}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == to, k
    assert db.get_pass(log_id, ivan).done_count == 4
    ci.post(f"{d.base}/vjezba/2/zamjena", data={"exercise_id": str(d.ex["Iskorak unatrag"])})
    r = ci.post(f"{d.base}/vjezba/2", data={"rows": "1", "item": str(d.items[1]), "reps_1": "10", "kg_1": "8"}, follow_redirects=False)
    assert r.headers["location"] == f"{d.base}/vjezba/3?odmor=90"          # swapped: the plan's item's rest
    r = ci.post(f"{d.base}/vjezba/3?odmor=90", data={"rows": "1", "item": str(d.items[2]), "sec_1": "x"})
    assert r.status_code == 400 and "data-odmor" not in form_tag(r.text)     # refused: the screen, no rest

    for q in ("abc", "0", "5000", "3601", "-5", "1.5", "", "90s", "²"):
        assert "data-odmor" not in form_tag(ci.get(f"{d.base}/vjezba/3", params={"odmor": q}).text), q
    for q in ("90", "1", "3600"):
        assert f'data-odmor="{q}"' in form_tag(ci.get(f"{d.base}/vjezba/3?odmor={q}").text), q
    assert "data-odmor" not in form_tag(ci.get(f"{d.base}/vjezba/3").text)

    def rest_between(k: int) -> str | None:
        m = re.search(r'data-rest="(\d+)"', form_tag(ci.get(f"{d.base}/vjezba/{k}").text))
        return m and m.group(1)

    assert [rest_between(k) for k in (1, 2, 3, 4)] == ["30", "60", None, None]

    page = ci.get(f"{d.base}/vjezba/2").text
    assert sub_lines(page) == ["Odmor između serija: 60 s · Odmor nakon vježbe: 90 s", "16 kg"]
    assert sub_lines(ci.get(f"{d.base}/vjezba/4").text) == ["Odmor nakon vježbe: 120 s"]
    assert sub_lines(ci.get(f"{d.base}/vjezba/3").text) == [
        "Odmor između serija: 0 s"]                                         # worded as set; its timer: none
    subs = [read(x) for x in re.findall(r'<span class="dx-sub">(.*?)</span>\s*</a>', page, re.S)]   # the list's rows
    assert subs == ["Odmor između serija: 30 s · Odmor nakon vježbe: 0 s",   # a 0 is worded, as rest_text words one
                    "Odmor između serija: 60 s · Odmor nakon vježbe: 90 s · 16 kg",
                    "Odmor između serija: 0 s", "Odmor nakon vježbe: 120 s"]


def test_the_set_log_has_a_tick_per_set_and_the_page_a_rest_bar():
    """The ✓ column, the script's: its header "✓" (for a screen reader
    "Odrađena serija") and a round button per row, "Serija n odrađena",
    not pressed, all rendered hidden (without the script the log is as it
    was): SET · PON. · KG · ✓, a timed exercise's SET · SEK. · ✓. The rest
    bar is on the page, hidden: "Odmor", the countdown, the track,
    "Preskoči odmor"."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    page = ci.get(f"{d.base}/vjezba/2").text                               # Goblet: 3 sets and the extra one
    head = ('<th scope="col" class="pl-tick" hidden><span aria-hidden="true">✓</span>'
            '<span class="pl-sr">Odrađena serija</span></th></tr></thead>')
    assert f'<th scope="col"><span class="t">Pon.</span></th><th scope="col"><span class="t">Kg</span></th>{head}' in page
    assert re.findall(r'<td class="pl-tick" hidden><button type="button" class="pl-done" aria-pressed="false" '
                      r'aria-label="Serija (\d+) odrađena">✓</button></td>\s*</tr>', page) == ["1", "2", "3", "4"]
    assert (f'<th scope="col"><span class="t">Set</span></th><th scope="col"><span class="t">Sek.</span></th>{head}'
            in ci.get(f"{d.base}/vjezba/3").text)
    assert re.search(r'<div class="pl-rest" id="plRest" role="timer" hidden>\s*<span class="pl-rest-n">'
                     r'<span class="pl-rest-h"><span class="t">Odmor</span></span><span class="pl-rest-t">0:00</span></span>\s*'
                     r'<span class="pl-rest-track" aria-hidden="true"><span class="pl-rest-fill"></span></span>\s*'
                     r'<button type="button" class="pl-rest-skip"><span class="t">Preskoči odmor</span></button>', page)


# ---------- leaving the pass, a pass left open (31.10.2026) ----------

def test_the_player_and_the_finish_screen_ask_before_leaving():
    """#leaveDlg (the owner: leaving "there should be a popup warning
    asking if he wants to finish the training and then he decides") is on
    the player and on the finish screen, once each: the pass's path
    (data-pass, the day's) and the page's mode, "Završiti trening?", the
    page's sentence, the ✕ (a dialog form), a hidden line for a failed
    discard, and two buttons, "Odbaci trening" and the primary: "Završi
    trening" on the player, "Natrag na osvrt" on the finish screen. The
    day's page has none: it is outside the pass."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    leads = {"player": "Trening je u tijeku. Završi ga osvrtom ili ga odbaci — odbačenom se brišu spremljene "
                       "serije ovog pokušaja.",
             "kraj": "Osvrt još nije spremljen. Spremi ga i trening je završen, ili trening odbaci — odbačenom "
                     "se brišu spremljene serije."}
    for path, mode, primary in ((f"{d.base}/vjezba/1", "player", "Završi trening"),
                                (f"{d.base}/kraj", "kraj", "Natrag na osvrt")):
        page = ci.get(path).text
        assert page.count('<dialog id="leaveDlg"') == 1, mode
        dlg = page.split('<dialog id="leaveDlg"')[1].split("</dialog>")[0]
        assert dlg.startswith(f' class="fb-modal" aria-labelledby="leaveTitle" data-pass="{d.base}" data-mode="{mode}">')
        assert '<form method="dialog" class="fb-x"><button type="submit" aria-label="Zatvori">✕</button></form>' in dlg
        assert '<h2 id="leaveTitle"><span class="t">Završiti trening?</span></h2>' in dlg
        assert [read(x) for x in re.findall(r'<p class="fb-lead">(.*?)</p>', dlg, re.S)] == [leads[mode]]
        assert re.search(r'<p class="fb-note" id="leaveErr"[^>]* hidden><span class="t">Nije uspjelo — pokušaj ponovno.</span></p>', dlg)
        assert re.findall(r'<button type="button" class="([^"]+)" id="(leave\w+)"( autofocus)?><span class="t">([^<]*)</span></button>', dlg) == [
            ("btn-ghost btn-sm", "leaveDrop", "", "Odbaci trening"), ("btn btn-sm", "leaveGo", " autofocus", primary)]
    assert "leaveDlg" not in ci.get(d.base).text


def test_a_stale_pass_is_finished_or_dropped_never_continued(monkeypatch):
    """A pass with no activity for PASS_STALE_HOURS (2 h; the owner: no
    "hanging training of 9 hours") cannot be continued: an exercise's
    screen, its save, its swap and Kreni / Nastavi all lead to the finish
    screen, nothing saved or swapped (db.save_sets and db.swap_exercise say
    "Trening je predugo otvoren — završi ga ili ga odbaci."). The day says
    "Nedovršen trening od danas (2 od 4 vježbe) — …" with "Završi trening"
    in Kreni's place and Odbaci beside it, the programme's card "·
    nedovršen"; the finish screen is "Nedovršen trening", its length to the
    last save (25 min, not the 3 h it hung), a sentence why it ends there,
    and no way back to the exercises. Its osvrt finishes it as ever, 25 min
    long, finished now; the history says so."""
    monkeypatch.setattr(config, "PASS_STALE_HOURS", 2)
    assert db.PASS_STALE == "Trening je predugo otvoren — završi ga ili ga odbaci."
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    for k, sets in ((1, {"reps_1": "15"}), (2, {"reps_1": "10", "kg_1": "20"})):
        assert ci.post(f"{d.base}/vjezba/{k}", data={"rows": "1", "item": str(d.items[k - 1]), **sets}, follow_redirects=False).status_code == 303
    started = db.get_pass(log_id, ivan).started_at - timedelta(hours=3)
    age(log_id, 3, saves_at=started + timedelta(minutes=25))
    log = db.get_pass(log_id, ivan)
    assert (log.started_at, log.last_activity, log.stale()) == (started, started + timedelta(minutes=25), True)
    kraj = f"{d.base}/kraj"

    r = ci.get(f"{d.base}/vjezba/3", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == kraj
    r = ci.post(f"{d.base}/vjezba/3", data={"rows": "1", "item": str(d.items[2]), "sec_1": "40"},
                follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == kraj and db.get_pass(log_id, ivan).done_count == 2
    for k in (3, 2):                                                    # 2: Goblet, a similar one that would swap
        r = ci.post(f"{d.base}/vjezba/{k}/zamjena", data={"exercise_id": str(d.ex["Iskorak unatrag"])},
                    follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == kraj, k
    assert db.get_pass(log_id, ivan).swap_items == {}
    r = ci.post(f"{d.base}/kreni", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == kraj and len(stored()) == 1
    with pytest.raises(ValueError, match=re.escape(db.PASS_STALE)):
        save(ivan, log_id, d, 3, [{"seconds": 40}])
    with pytest.raises(ValueError, match=re.escape(db.PASS_STALE)):
        db.swap_exercise(log_id, ivan, item(d, 2), d.ex["Iskorak unatrag"])
    log = db.get_pass(log_id, ivan)
    assert (log.done_count, log.swap_items, log.in_progress) == (2, {}, True)

    began = started.astimezone(config.TZ).date()
    when = "danas" if began == config.today() else "jučer"
    page = ci.get(d.base).text
    assert state_line(page) == f"Nedovršen trening od {when} (2 od 4 vježbe) — nastavak nije moguć: završi ga ili ga odbaci."
    assert '<span class="t">Nastavi</span></button>' not in page and f'action="{d.base}/kreni"' not in page
    assert f'<div class="go"><a class="btn" href="{kraj}"><span class="t">Završi trening</span></a></div>' in page
    assert '<span class="t">Odbaci započeti trening</span></button>' in page
    assert page.count('<span class="dx-ok" role="img" aria-label="spremljeno">✓</span>') == 2   # what it saved, ticked
    page = ci.get(f"/treninzi/{d.pid}").text
    assert '4 vježbe · <span class="t">nedovršen</span></span>' in page and '· <span class="t">u tijeku</span>' not in page

    page = ci.get(kraj).text
    assert '<p class="kr-eyebrow"><span class="t">Nedovršen trening</span></p>' in page and '<span class="t">Trening odrađen</span>' not in page
    assert '<p class="kr-sum">2 od 4 vježbe · 25 min</p>' in page
    assert (f'<p class="kr-stale">Započet {when} i nije završen — nastavak više nije moguć. '
            f'<span class="t">Spremi osvrt ili trening odbaci.</span></p>') in page
    assert "Natrag na vježbe" not in page and '<span class="t">Odbaci trening</span></button>' in page and 'data-mode="kraj"' in page

    r = ci.post(kraj, data={"effort": "6"}, follow_redirects=False)
    assert location(r) == f"{d.base}?ok=Trening je spremljen."
    log = db.get_pass(log_id, ivan)
    assert not log.in_progress and not log.stale() and (log.effort, log.elapsed_seconds) == (6, 1500)
    assert abs((datetime.now(config.TZ) - log.finished_at).total_seconds()) < 5
    page = ci.get(d.base).text
    assert hist_lines(page)[0] == (f"{began.day}.{began.month}." + (f"{began.year}." if began.year != config.today().year else "")
                                   + " · 2/4 vježbe · 25 min · napor 6")
    assert state_line(page).startswith("Odrađen 1×") and '<span class="t">Kreni</span></button>' in page


def test_staleness_is_counted_from_the_last_activity(monkeypatch):
    """Stale is PASS_STALE_HOURS (2) since the pass last moved, its start or
    its newest save: started 3 h ago with a save 10 min ago it goes on (its
    length the whole 3 h); started 1 h 59 min ago with no save it goes on;
    at 2 h 1 min it is stale (the finish screen), and finished it is 0 s
    long, which the finish screen and the history say as "1 min" (a
    duration is a minute at least)."""
    monkeypatch.setattr(config, "PASS_STALE_HOURS", 2)
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    first = stored()[0][0]
    ci.post(f"{d.base}/vjezba/1", data={"rows": "1", "item": str(d.items[0]), "reps_1": "15"})
    age(first, 3, saves_at=datetime.now(config.TZ) - timedelta(minutes=10))
    assert not db.get_pass(first, ivan).stale()
    assert ci.get(f"{d.base}/vjezba/2", follow_redirects=False).status_code == 200
    ci.post(f"{d.base}/kraj", data={"effort": "5"})
    assert abs(db.get_pass(first, ivan).elapsed_seconds - 3 * 3600) <= 5

    ci.post(f"{d.base}/kreni")
    second = db.open_pass(ivan, d.did).id
    age(second, 1 + 59 / 60)
    assert not db.get_pass(second, ivan).stale()
    assert ci.get(f"{d.base}/vjezba/1", follow_redirects=False).status_code == 200
    age(second, 2 / 60)                                                 # 2 h 1 min
    assert db.get_pass(second, ivan).stale()
    r = ci.get(f"{d.base}/vjezba/1", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"{d.base}/kraj"
    assert '<p class="kr-sum">0 od 4 vježbe · 1 min</p>' in ci.get(f"{d.base}/kraj").text
    ci.post(f"{d.base}/kraj", data={"effort": "4"})
    log = db.get_pass(second, ivan)
    assert (log.in_progress, log.elapsed_seconds, log.elapsed_text) == (False, 0, "1 min")
    assert hist_lines(ci.get(d.base).text)[0].endswith(" · 0/4 vježbe · 1 min · napor 4")


# ---------- a part done as a circuit (24.11.2026, kružni trening; one screen per round since 25.11.2026) ----------

def build_circuit(rounds: int = 3, rest: int | None = 120, title: str = "Kružni — početna"):
    """A programme of ivan's razina whose Trening 1 does its Glavni dio A as
    a circuit of `rounds` rounds, `rest` seconds after each round, in the
    day's display order:
      Zagrijavanje (normal): Čučanj s vlastitom težinom (2 × 15, rest 30, 20 after it)
      Glavni dio A (the circuit): Goblet čučanj (3 × 10, rest 60, 15 after
        it, 16 kg planned, "pete na podu"; its swap, one way: Iskorak
        unatrag), Plank (3 × 40 s, 25 after it): their sets and rests stay
        stored and do not apply there
      Glavni dio B (normal): Sklekovi (3 × 10, rest 60, 90 after it)
    so its steps are the warm-up, then `rounds` rounds of the circuit (a
    step each, both exercises on it), then Sklekovi: 5 for three rounds."""
    names = ("Čučanj s vlastitom težinom", "Goblet čučanj", "Plank", "Sklekovi", "Iskorak unatrag")
    existing = {e.name: e.id for e, _ in db.exercises()}
    ex = {n: existing.get(n) or db.create_exercise(n) for n in names}
    db.update_exercise(ex["Goblet čučanj"], "Goblet čučanj", "Pete na podu.", "Do paralele i natrag.", "",
                       {ex["Iskorak unatrag"]})
    pid = db.create_program(title, None, "pocetna", "cijelo")
    did = db.add_day(pid)
    db.update_day(did, "Kružni", 0, "")
    ids = {}
    for name, section, sets, reps, seconds, between, after, note, kg in (
            ("Čučanj s vlastitom težinom", "zagrijavanje", 2, 15, None, 30, 20, "", None),
            ("Goblet čučanj", "trening", 3, 10, None, 60, 15, "pete na podu", 16),
            ("Plank", "trening", 3, None, 40, None, 25, "", None),
            ("Sklekovi", "trening_b", 3, 10, None, 60, 90, "", None)):
        ids[name] = db.add_day_item(did, ex[name], section)
        db.update_day_item(ids[name], section, sets, reps, seconds, between, after, note, kg=kg)
    db.set_circuit(did, "trening", rounds, rest)
    return SimpleNamespace(pid=pid, did=did, ids=ids, ex=ex, base=f"/treninzi/{pid}/dan/{did}",
                           warm=ids["Čučanj s vlastitom težinom"], goblet=ids["Goblet čučanj"], plank=ids["Plank"],
                           skl=ids["Sklekovi"])


def part_items(c, section: str = "trening") -> list:
    """A day's part's items as the routes load them (the day's order)."""
    return db.get_day(c.did).by_section[section]


def save_round(uid: int, log_id: int, c, rnd: int, sets: dict, effort: int | None = None, section: str = "trening"):
    """db.save_circuit_round for c's part: `sets` item id -> its set of the
    round, an item not named not done in it."""
    items = part_items(c, section)
    return db.save_circuit_round(log_id, uid, items, rnd, {it.id: sets.get(it.id) for it in items}, effort=effort)


def round_form(rnd: int, values: dict, part: str = "trening", effort: str | None = None) -> dict:
    """What a round's screen posts: its part and round, its inputs
    (reps_<item id>, kg_<item id>, sec_<item id>), the rating when chosen."""
    return {"part": part, "round": str(rnd), **values, **({} if effort is None else {"effort": effort})}


def list_rows(page: str) -> list[tuple[str, str, str, str]]:
    """The player's list: (" is-cur" or "", its link, its aria-current, its inside), in order."""
    return re.findall(r'<li><a class="card pl-row( is-cur)?" href="([^"]+)"( aria-current="step")?>(.*?)</a></li>', page, re.S)


def blocks(page: str) -> list[str]:
    """A round's screen's exercise blocks (.cr-row), in order, each its markup."""
    return [b.split('<div class="pl-foot">')[0] for b in page.split('<div class="cr-row" id="cr-')[1:]]


def test_a_circuits_steps_are_its_rounds():
    """app._steps (25.11.2026): the day's display order, a normal part one
    step per item, a circuit part ONE step per round (its round, its
    circuit, its every item in the day's order, no item of its own): a day
    of a warm-up (normal), A (a circuit of 3 rounds × 2) and B (normal) is
    1 + 3 + 1 = 5 steps. A day with no circuit is exactly its items, a
    step each, none with a round; a circuit on a part of one item is that
    item a round at a time, and one on a part with none adds nothing.
    Until 25.11.2026 a circuit's step was one exercise of one round."""
    trainer, ivan, ana = people()
    c = build_circuit()
    day = db.get_day(c.did)
    steps = web._steps(day, web._day_items(day))
    assert [(s.item.id if s.item else None, s.round, [it.id for it in s.items]) for s in steps] == [
        (c.warm, None, []), (None, 1, [c.goblet, c.plank]), (None, 2, [c.goblet, c.plank]),
        (None, 3, [c.goblet, c.plank]), (c.skl, None, [])]
    assert [s.item_ids for s in steps] == [[c.warm], [c.goblet, c.plank], [c.goblet, c.plank], [c.goblet, c.plank],
                                           [c.skl]]
    assert {s.circuit.rounds for s in steps if s.round} == {3} and all(s.circuit is None for s in steps if not s.round)
    assert not hasattr(steps[1], "last")
    d = build_day()
    plain = db.get_day(d.did)
    steps = web._steps(plain, web._day_items(plain))
    assert [s.item.id for s in steps] == d.items and {(s.round, s.circuit, s.items) for s in steps} == {(None, None, ())}
    db.set_circuit(d.did, "istezanje", 2, None)                             # one item: a round at a time
    db.set_circuit(d.did, "trening_b", 4, 30)                               # none: nothing
    plain = db.get_day(d.did)
    assert [(s.item_ids, s.round) for s in web._steps(plain, web._day_items(plain))] == [
        ([d.items[0]], None), ([d.items[1]], None), ([d.items[2]], None), ([d.items[3]], 1), ([d.items[3]], 2)]


def test_a_circuit_round_is_one_screen():
    """The round's screen (25.11.2026; the owner's note to Amir: "on označi
    koje krugove koje je odradio. Pauza ide na kraju kruga a između vježbi
    nikakva pauza."): the player's layout with no clip box (no ‹ ›), the
    card's kicker "Kružni dio", "2/5" and "Krug 1 od 3", the part's name as
    the h1 (the page's title too), "Vježbe idu jedna za drugom, bez pauze.
    Odmor nakon kruga: 120 s."; a block per exercise in the day's order:
    its name a <details> summary (open: the clip, preload none, what one
    rep is, the instructions), its dose of a round muted (the planned
    weight in it), its note, its inputs by its fields with small labels
    (Goblet PON. · KG, Plank SEK.: reps_<id>, kg_<id>, sec_<id>, named for
    a screen reader by the exercise and the label), first values the plan's
    reps and seconds and the plan's kg (he never logged them), then last
    time's set of this round's place, then this pass's weight in the round
    before; the round's rating, ONE button "Krug 1 odrađen", "Preskoči →";
    no ✓, no "+", no swap (one posted swaps nothing). The hidden part and
    round. The last step's button: "Krug 3 odrađen — završi"."""
    trainer, ivan, ana = people()
    c = build_circuit()
    ct, ci = client_for("trener@test.local"), client_for("ivan@test.local")
    assert ct.post(f"/treninzi/vjezbe/{c.ex['Goblet čučanj']}/video",
                   files={"video": ("g.mp4", io.BytesIO(MP4), "video/mp4")}, follow_redirects=False).status_code == 303
    clip = db.exercise(c.ex["Goblet čučanj"]).video
    ci.post(f"{c.base}/kreni")
    page = ci.get(f"{c.base}/vjezba/2").text
    assert re.search(r'<p class="pl-eyebrow"><span><span class="t">Kružni dio</span></span> <span class="pl-chip">2/5</span>\s*'
                     r'<span class="pl-round">Krug 1 od 3</span></p>', page)
    assert '<h1 class="pl-name" id="pl-name">Glavni dio A</h1>' in page
    assert "<title>Glavni dio A — Trening 1 · Kružni — QMT</title>" in page
    assert ('<p class="cr-intro"><span class="t">Vježbe idu jedna za drugom, bez pauze.</span> '
            '<span class="t">Odmor nakon kruga:</span> 120 s.</p>') in page
    assert 'id="plStage"' not in page and 'class="pl-nav' not in page and 'id="plAdd"' not in page
    assert 'class="pl-tick"' not in page and "Zamijeni vježbu" not in page and "data-rest" not in form_tag(page)
    assert 'name="rows"' not in page and 'name="item"' not in page
    assert '<input type="hidden" name="part" value="trening">' in page and '<input type="hidden" name="round" value="1">' in page
    rows = blocks(page)
    assert [r.split('"')[0] for r in rows] == [str(c.goblet), str(c.plank)]
    assert f'<summary><span class="cr-name" id="cr-{c.goblet}-n">Goblet čučanj</span></summary>' in rows[0]
    assert f'<video src="/media/{clip}" controls playsinline preload="none"></video>' in rows[0]
    assert ('<strong><span class="t">Jedno ponavljanje:</span></strong> Do paralele i natrag.' in rows[0]
            and '<p class="pre">Pete na podu.</p>' in rows[0])
    assert "Vježba još nema videa." in rows[1]
    assert re.findall(r'<p class="cr-dose">([^<]*)</p>', rows[0]) == ["10 ponavljanja · 16 kg", "pete na podu"]
    assert re.findall(r'<p class="cr-dose">([^<]*)</p>', rows[1]) == ["40 s"]
    labels = r'<label id="cr-\d+-(\w+)-l" for="cr-\d+-\w+"><span class="t">([^<]*)</span></label>'
    assert re.findall(labels, rows[0]) == [("reps", "Pon."), ("kg", "Kg")] and re.findall(labels, rows[1]) == [("sec", "Sek.")]
    assert f'aria-labelledby="cr-{c.goblet}-n cr-{c.goblet}-kg-l"' in rows[0]
    assert inputs(page) == [("reps", str(c.goblet), "10"), ("kg", str(c.goblet), "16"), ("sec", str(c.plank), "40")]
    assert ('<p class="pl-rate-h" id="pl-rate-h"><span class="t">Koliko je bio težak ovaj krug?</span> '
            '<span class="pl-opt"><span class="t">(neobavezno)</span></span></p>') in page
    assert re.findall(r'<input type="radio" name="effort" value="(\d+)">', page) == [str(n) for n in range(1, 11)]
    assert '<button type="submit" class="btn pl-save"><span>Krug 1 <span class="t">odrađen</span></span></button>' in page
    assert f'<a class="act act-quiet" href="{c.base}/vjezba/3"><span class="t">Preskoči →</span></a>' in page
    r = ci.post(f"{c.base}/vjezba/2/zamjena", data={"exercise_id": str(c.ex["Iskorak unatrag"])}, follow_redirects=False)
    assert r.headers["location"] == f"{c.base}/vjezba/2" and db.open_pass(ivan, c.did).swap_items == {}

    ci.post(f"{c.base}/odustani")                                           # last time: a finished pass, unrated
    old = db.start_pass(ivan, db.get_program(c.pid), db.get_day(c.did))
    for rnd, kg, sec in ((1, 17.0, 30), (2, 18.0, 35), (3, 19.0, 40)):
        save_round(ivan, old.id, c, rnd, {c.goblet: {"reps": 8, "kg": kg}, c.plank: {"seconds": sec}})
    db.finish_pass(old.id, ivan, 6, None, "")
    ci.post(f"{c.base}/kreni")
    assert inputs(ci.get(f"{c.base}/vjezba/2").text) == [   # last time's round 1 weight; the plan's reps and seconds
        ("reps", str(c.goblet), "10"), ("kg", str(c.goblet), "17"), ("sec", str(c.plank), "40")]
    r = ci.post(f"{c.base}/vjezba/2", data=round_form(1, {f"reps_{c.goblet}": "10", f"kg_{c.goblet}": "20",
                                                          f"sec_{c.plank}": "40"}), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"{c.base}/vjezba/3?odmor=120"
    page = ci.get(f"{c.base}/vjezba/3").text                               # round 2: this pass's round 1 weight
    assert "Krug 2 od 3" in page and '<button type="submit" class="btn pl-save"><span>Krug 2 <span class="t">odrađen</span></span></button>' in page
    assert inputs(page) == [("reps", str(c.goblet), "10"), ("kg", str(c.goblet), "20"), ("sec", str(c.plank), "40")]
    page = ci.get(f"{c.base}/vjezba/2").text                               # round 1 saved: as saved
    assert inputs(page) == [("reps", str(c.goblet), "10"), ("kg", str(c.goblet), "20"), ("sec", str(c.plank), "40")]
    assert '<span class="pl-saved"><span class="t">✓ Spremljeno</span></span>' in page

    db.delete_day_item(c.skl)                                               # the circuit last: its last round ends the day
    page = ci.get(f"{c.base}/vjezba/4").text
    assert '<button type="submit" class="btn pl-save"><span>Krug 3 <span class="t">odrađen — završi</span></span></button>' in page
    assert f'<a class="act act-quiet" href="{c.base}/kraj"><span class="t">Preskoči i završi</span></a>' in page
    r = ci.post(f"{c.base}/vjezba/4", data=round_form(3, {f"sec_{c.plank}": "30"}), follow_redirects=False)
    assert r.headers["location"] == f"{c.base}/kraj"                       # never a rest to the finish screen


def test_a_circuit_is_walked_a_round_at_a_time():
    """The rounds through the routes (25.11.2026): "Krug n odrađen" saves
    the round whole (each exercise's set of it, the round carried), an
    exercise with its inputs empty not done in it, then the next step with
    the circuit's rest after a round (the final round's too, the pause
    before the next part); every exercise empty is refused ("Upiši bar
    jednu vježbu."), a bad number too ("Neispravan broj."), each the screen
    again, 400, what was typed kept; a part or a round that is not the
    step's now (or a normal step's form on a round, or a round posted to a
    normal step) is refused as a changed day, nothing saved. A round saved
    again replaces itself alone (an exercise left empty loses its set of
    that round, its entry gone when it has none left). Kreni / Nastavi
    lands on the first step not saved. The list: the circuit's caption,
    each of its rows a link to the part's first round not saved, the
    round's exercises ringed, their marks per exercise ("2/3", then ✓), the
    rows' dose of a round and the note alone; the dock and the finish
    screen count by exercise; the history's Serije are in round order."""
    trainer, ivan, ana = people()
    c = build_circuit()
    ci = client_for("ivan@test.local")
    assert ci.post(f"{c.base}/kreni", follow_redirects=False).headers["location"] == f"{c.base}/vjezba/1"
    log_id = db.open_pass(ivan, c.did).id

    def post(k: int, data: dict):
        return ci.post(f"{c.base}/vjezba/{k}", data=data, follow_redirects=False)

    def entry(item: int):
        return db.get_pass(log_id, ivan).done_items.get(item)

    full = {f"reps_{c.goblet}": "10", f"kg_{c.goblet}": "20", f"sec_{c.plank}": "40"}
    assert post(2, round_form(1, full)).headers["location"] == f"{c.base}/vjezba/3?odmor=120"
    assert entry(c.goblet)["sets"] == [{"reps": 10, "kg": 20.0, "round": 1}]
    assert (entry(c.goblet)["name"], entry(c.goblet)["section"]) == ("Goblet čučanj", "trening")
    assert entry(c.plank)["sets"] == [{"seconds": 40, "round": 1}]
    assert post(3, round_form(2, {f"reps_{c.goblet}": "10", f"kg_{c.goblet}": "22", f"sec_{c.plank}": " "})
                ).headers["location"] == f"{c.base}/vjezba/4?odmor=120"     # Plank not done in round 2
    assert entry(c.plank)["sets"] == [{"seconds": 40, "round": 1}]
    assert entry(c.goblet)["sets"] == [{"reps": 10, "kg": 20.0, "round": 1}, {"reps": 10, "kg": 22.0, "round": 2}]

    empty = {f"reps_{c.goblet}": "", f"kg_{c.goblet}": "", f"sec_{c.plank}": ""}
    for values, sentence, kept in ((empty, "Upiši bar jednu vježbu.", ["", "", ""]),
                                   ({**full, f"reps_{c.goblet}": "x", f"kg_{c.goblet}": "22,5"}, "Neispravan broj.",
                                    ["x", "22.5", "40"]),
                                   ({**full, f"sec_{c.plank}": "3601"}, "Neispravan broj.", ["10", "20", "3601"])):
        r = post(4, round_form(3, values, effort="8"))
        assert r.status_code == 400 and alert(r.text) == [sentence] and "Krug 3 od 3" in r.text, sentence
        assert [v for _, _, v in inputs(r.text)] == kept, sentence
        assert re.search(r'<h1 class="pl-name" id="pl-name">Glavni dio A</h1>\s*<p class="cr-intro">.*?</p>\s*'
                         r'<div class="alert" role="alert">', r.text)
        assert 'value="8" checked>' in r.text                                # the rating chosen, kept
    for k, data in ((4, round_form(3, full, part="trening_b")), (4, round_form(2, full)), (4, {**full, "round": "3"}),
                    (4, {"rows": "1", "item": str(c.goblet), "reps_1": "10"}),
                    (1, {"rows": "1", "item": str(c.warm), "reps_1": "15", "round": "1"}),
                    (1, {"rows": "1", "item": str(c.warm), "reps_1": "15", "part": "zagrijavanje"})):
        r = post(k, data)
        assert r.status_code == 400 and alert(r.text) == [web.DAY_CHANGED], (k, data)
    assert len(entry(c.goblet)["sets"]) == 2 and entry(c.warm) is None and entry(c.skl) is None

    r = post(2, round_form(1, {f"reps_{c.goblet}": "9", f"kg_{c.goblet}": "21", f"sec_{c.plank}": ""}))
    assert r.headers["location"] == f"{c.base}/vjezba/3?odmor=120"          # round 1 again: itself alone
    assert entry(c.goblet)["sets"] == [{"reps": 9, "kg": 21.0, "round": 1}, {"reps": 10, "kg": 22.0, "round": 2}]
    assert entry(c.plank) is None                                           # its one set gone with it
    assert ci.post(f"{c.base}/kreni", follow_redirects=False).headers["location"] == f"{c.base}/vjezba/1"   # the warm-up
    r = post(1, {"rows": "3", "item": str(c.warm), "reps_1": "15", "reps_2": "15"})
    assert r.headers["location"] == f"{c.base}/vjezba/2?odmor=20"
    assert ci.post(f"{c.base}/kreni", follow_redirects=False).headers["location"] == f"{c.base}/vjezba/4"   # round 3

    page = ci.get(f"{c.base}/vjezba/4").text
    rows = list_rows(page)
    assert [(cur, href, aria) for cur, href, aria, _ in rows] == [
        ("", f"{c.base}/vjezba/1", ""), (" is-cur", f"{c.base}/vjezba/4", ' aria-current="step"'),
        (" is-cur", f"{c.base}/vjezba/4", ' aria-current="step"'), ("", f"{c.base}/vjezba/5", "")]
    assert ('<span class="dx-dose"><span class="dx-rounds" role="img" aria-label="spremljeno 2 od 3 kruga">2/3</span> '
            '10 ponavljanja · 16 kg</span>') in rows[1][3]
    assert '<span class="dx-dose">40 s</span>' in rows[2][3] and "dx-rounds" not in rows[2][3]
    assert '<span class="dx-sub">pete na podu</span>' in rows[1][3] and "dx-sub" not in rows[2][3]   # never a rest
    assert ('<span class="dx-sub"><span class="t">Odmor između serija:</span> 30 s · '
            '<span class="t">Odmor nakon vježbe:</span> 20 s</span>') in rows[0][3]
    assert [read(h) for h in re.findall(r'<h3 class="dx-cap">(.*?)</h3>', page)] == [
        "Zagrijavanje", "Glavni dio A · kružno · 3 kruga", "Glavni dio B"]
    assert '<a class="pl-dock" href="#popis"><span><span class="t">Vježbe</span> · 2/4 ✓</span></a>' in page
    assert ('<div class="pl-segs" aria-hidden="true"><span class="done"></span><span class="done"></span>'
            '<span class="done"></span><span class="cur"></span><span></span></div>') in page

    assert post(4, round_form(3, {f"reps_{c.goblet}": "10", f"kg_{c.goblet}": "24", f"sec_{c.plank}": "30"})
                ).headers["location"] == f"{c.base}/vjezba/5?odmor=120"     # the final round: the pause before B
    page = ci.get(f"{c.base}/vjezba/5").text
    rows = list_rows(page)
    assert rows[1][1] == f"{c.base}/vjezba/2"                                # every round saved: the part's first
    assert '<span class="dx-ok" role="img" aria-label="spremljeno">✓</span> 10 ponavljanja · 16 kg' in rows[1][3]
    assert '<span class="dx-rounds" role="img" aria-label="spremljeno 1 od 3 kruga">1/3</span> 40 s' in rows[2][3]
    assert '<a class="pl-dock" href="#popis"><span><span class="t">Vježbe</span> · 3/4 ✓</span></a>' in page
    assert re.search(r'<p class="kr-sum">3 od 4 vježbe · \d+ min</p>', ci.get(f"{c.base}/kraj").text)
    assert post(5, {"rows": "1", "item": str(c.skl), "reps_1": "10"}).headers["location"] == f"{c.base}/kraj"
    ci.post(f"{c.base}/kraj", data={"effort": "7"})
    first = ci.get(c.base).text.split('<li class="card hist-row">')[1]
    assert sets_lines(first) == ["Čučanj s vlastitom težinom: 15 · 15", "Goblet čučanj: 9 × 21 kg · 10 × 22 kg · 10 × 24 kg",
                                 "Plank: 30 s", "Sklekovi: 10"]


def test_the_rest_after_a_round_is_the_circuits():
    """The rest after a round (25.11.2026: no pause between a circuit's
    exercises) is the circuit's alone, after every round, the final one
    too (the pause before the next part): ?odmor=<its seconds>; a circuit
    with none (NULL) or 0 gives none, never an exercise's own rest after
    it; the screen says it ("Odmor nakon kruga: 120 s.", "0 s" for a 0,
    nothing with none). A normal step's rest is its item's, as ever."""
    trainer, ivan, ana = people()
    c = build_circuit(rounds=2, rest=None)
    ci = client_for("ivan@test.local")
    ci.post(f"{c.base}/kreni")
    data = round_form(1, {f"sec_{c.plank}": "40"})

    def intro() -> str:
        return read(re.search(r'<p class="cr-intro">(.*?)</p>', ci.get(f"{c.base}/vjezba/2").text, re.S).group(1))

    assert intro() == "Vježbe idu jedna za drugom, bez pauze."
    assert ci.post(f"{c.base}/vjezba/2", data=data, follow_redirects=False).headers["location"] == f"{c.base}/vjezba/3"
    db.set_circuit(c.did, "trening", 2, 0)                                  # 0: none
    assert ci.post(f"{c.base}/vjezba/2", data=data, follow_redirects=False).headers["location"] == f"{c.base}/vjezba/3"
    assert intro() == "Vježbe idu jedna za drugom, bez pauze. Odmor nakon kruga: 0 s."
    db.set_circuit(c.did, "trening", 2, 45)
    assert ci.post(f"{c.base}/vjezba/2", data=data, follow_redirects=False).headers["location"] == f"{c.base}/vjezba/3?odmor=45"
    data = round_form(2, {f"sec_{c.plank}": "40"})
    assert ci.post(f"{c.base}/vjezba/3", data=data, follow_redirects=False).headers["location"] == f"{c.base}/vjezba/4?odmor=45"
    assert 'data-odmor="45"' in form_tag(ci.get(f"{c.base}/vjezba/4?odmor=45").text)   # Sklekovi's screen counts it
    day = db.get_day(c.did)
    steps = web._steps(day, web._day_items(day))
    assert [web._step_rest(s) for s in steps] == [20, 45, 45, 90]           # the warm-up's and Sklekovi's their own


def test_the_bar_is_one_track_past_forty_steps():
    """The bar over the player: one segment per step while the day has at
    most 40 (a round is a step since 25.11.2026: a warm-up, 20 rounds of A
    and 19 of B, 40 segments), past that one track (.pl-track, no segment)
    whose fill is the share of the steps saved (3 of 41: 7.32 %)."""
    trainer, ivan, ana = people()
    c = build_circuit(rounds=20, title="Dvadeset")
    db.set_circuit(c.did, "trening_b", 19, 30)
    ci = client_for("ivan@test.local")
    ci.post(f"{c.base}/kreni")
    page = ci.get(f"{c.base}/vjezba/1").text
    assert page.split('<div class="pl-segs" aria-hidden="true">')[1].split("</div>")[0].count("<span") == 40
    assert 'class="pl-track"' not in page and '<span class="pl-chip">1/40</span>' in page
    db.set_circuit(c.did, "trening_b", 20, 30)
    log_id = db.open_pass(ivan, c.did).id
    save(ivan, log_id, SimpleNamespace(items=[c.warm]), 1, [{"reps": 15, "kg": 0.0}])
    save_round(ivan, log_id, c, 1, {c.goblet: {"reps": 10, "kg": 16.0}})
    save_round(ivan, log_id, c, 20, {c.skl: {"reps": 10, "kg": 0.0}}, section="trening_b")
    page = ci.get(f"{c.base}/vjezba/2").text
    assert '<div class="pl-track" aria-hidden="true"><span style="width: 7.32%"></span></div>' in page
    assert 'class="pl-segs"' not in page.split("<main")[1] and '<span class="pl-chip">2/41</span>' in page
    assert "Krug 20 od 20" in ci.get(f"{c.base}/vjezba/41").text
    assert ci.get(f"{c.base}/vjezba/42", follow_redirects=False).headers["location"] == f"{c.base}/vjezba/41"


def test_rounds_saved_at_once_keep_every_one():
    """Rounds 1, 2 and 3 of a circuit saved at once (three tabs): each
    db.save_circuit_round takes the pass's row first, so none overwrites
    another's round; each exercise's entry holds the three, sorted by
    round."""
    trainer, ivan, ana = people()
    c = build_circuit()
    log = db.start_pass(ivan, db.get_program(c.pid), db.get_day(c.did))
    errors = []

    def go(rnd):
        try:
            save_round(ivan, log.id, c, rnd, {c.goblet: {"reps": 10, "kg": float(10 + rnd)}, c.plank: {"seconds": 30 + rnd}})
        except Exception as e:                                              # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=go, args=(rnd,)) for rnd in (3, 1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    done = db.get_pass(log.id, ivan).done_items
    assert not errors and done[c.goblet]["sets"] == [
        {"reps": 10, "kg": 11.0, "round": 1}, {"reps": 10, "kg": 12.0, "round": 2}, {"reps": 10, "kg": 13.0, "round": 3}]
    assert done[c.plank]["sets"] == [{"seconds": 31, "round": 1}, {"seconds": 32, "round": 2}, {"seconds": 33, "round": 3}]


def test_a_round_is_saved_whole_and_checked(monkeypatch):
    """db.save_circuit_round (25.11.2026; db.save_round, an exercise of a
    round at a time, went): every exercise done gets its set of the round
    in one write ({"reps": 10, "kg": 20.0, "round": 2}, the entry's sets
    sorted by round, the other rounds kept, a set of a normal save no
    round's: it goes), an exercise not done none, and loses the set of this
    round it had; with none done "Upiši bar jednu vježbu."; a set carries
    its round (1–99) on any of the three shapes, "Neispravan broj." for
    anything else; refused as save_sets is (a pass finished, open too long;
    another day's item or another client's pass False). The entry names
    the exercise the pass swapped in, else the plan's. The history, the
    karton and the estimated maxes read a round's set as any other."""
    monkeypatch.setattr(config, "PASS_STALE_HOURS", 2)
    trainer, ivan, ana = people()
    c = build_circuit()
    checked = db._checked_sets([{"reps": 10, "kg": 20.0, "round": 2}, {"seconds": 30, "round": 1},
                                {"reps": 5, "seconds": 30, "round": 99}, {"reps": 6, "kg": 0.0}])
    assert checked == [{"reps": 10, "kg": 20.0, "round": 2}, {"seconds": 30, "round": 1},
                       {"reps": 5, "seconds": 30, "round": 99}, {"reps": 6, "kg": 0.0}]
    for bad in (0, 100, -1, True, 1.0, "2", None):
        with pytest.raises(ValueError, match="^Neispravan broj.$"):
            db._checked_sets([{"reps": 10, "kg": 20.0, "round": bad}])
    with pytest.raises(ValueError, match="^Neispravan broj.$"):
        db._checked_sets([{"round": 1}])
    assert [set_text(s) for s in checked] == ["10 × 20 kg", "30 s", "5 × 30 s", "6"]
    assert db.NO_ROUND_EXERCISE == "Upiši bar jednu vježbu."

    log = db.start_pass(ivan, db.get_program(c.pid), db.get_day(c.did))
    goblet = db.get_day_item(c.goblet)
    db.save_sets(log.id, ivan, goblet, [{"reps": 8, "kg": 20.0}, {"reps": 8, "kg": 20.0}], goblet.exercise)
    assert save_round(ivan, log.id, c, 2, {c.goblet: {"reps": 6, "kg": 90.0}})
    done = db.get_pass(log.id, ivan).done_items
    assert done[c.goblet]["sets"] == [{"reps": 6, "kg": 90.0, "round": 2}] and c.plank not in done
    with pytest.raises(ValueError, match=f"^{db.NO_ROUND_EXERCISE}$"):
        save_round(ivan, log.id, c, 1, {})
    for one in ({"reps": 1000, "kg": 0.0}, {"reps": 5}, "5"):
        with pytest.raises(ValueError, match="^Neispravan broj.$"):
            save_round(ivan, log.id, c, 1, {c.goblet: one})
    for rnd in (0, 100):
        with pytest.raises(ValueError, match="^Neispravan broj.$"):
            save_round(ivan, log.id, c, rnd, {c.goblet: {"reps": 5, "kg": 0.0}})
    assert db.get_pass(log.id, ivan).done_items[c.goblet]["sets"] == [{"reps": 6, "kg": 90.0, "round": 2}]
    other = build_day()
    assert not db.save_circuit_round(log.id, ivan, [db.get_day_item(other.items[0])], 1,
                                     {other.items[0]: {"reps": 5, "kg": 0.0}})          # another day's item
    assert not save_round(ana, log.id, c, 1, {c.goblet: {"reps": 5, "kg": 0.0}})        # another's pass

    db.swap_exercise(log.id, ivan, goblet, c.ex["Iskorak unatrag"])         # a swap made on a normal step before
    assert save_round(ivan, log.id, c, 1, {c.goblet: {"reps": 8, "kg": 10.0}, c.plank: {"seconds": 40}})
    done = db.get_pass(log.id, ivan).done_items
    assert (done[c.goblet]["exercise_id"], done[c.goblet]["name"]) == (c.ex["Iskorak unatrag"], "Iskorak unatrag")
    assert (done[c.plank]["exercise_id"], done[c.plank]["name"]) == (c.ex["Plank"], "Plank")
    db.finish_pass(log.id, ivan, 7, None, "")
    with pytest.raises(ValueError, match=f"^{db.PASS_FINISHED}$"):
        save_round(ivan, log.id, c, 1, {c.goblet: {"reps": 5, "kg": 0.0}})
    maxes = {m.name: m.value_text for m in db.estimated_maxes(ivan)}
    assert maxes == {"Iskorak unatrag": "108 kg"}                           # 90 kg × 6, a round's set as any
    karton = client_for("ivan@test.local").get("/karton").text.split(f'id="pass-{log.id}"')[1].split('<div class="log-entry')[0]
    assert sets_lines(karton) == ["Iskorak unatrag: 8 × 10 kg · 6 × 90 kg", "Plank: 40 s"]
    stale = db.start_pass(ivan, db.get_program(c.pid), db.get_day(c.did))
    age(stale.id, 3)
    with pytest.raises(ValueError, match=f"^{db.PASS_STALE}$"):
        save_round(ivan, stale.id, c, 1, {c.goblet: {"reps": 5, "kg": 0.0}})


# ---------- the rating per exercise, and the load next time (25.11.2026) ----------

def rate_rows(page: str) -> list[str]:
    """The rating's radios as the page has them: their values, a checked one "n*"."""
    return [v + ("*" if on else "") for v, on in re.findall(r'<input type="radio" name="effort" value="(\d+)"( checked)?>', page)]


def test_an_exercise_is_rated_with_its_save():
    """On a normal step, under the set log and above Spremi, "Koliko je bilo
    teško? (neobavezno)" and ten radios 1–10 (`effort`), none chosen;
    posted with Spremi, stored in the exercise's entry ("effort": 7, an int;
    none: no key), shown chosen again on its screen, a re-save replacing it
    (with none: gone); anything else is "Neispravan broj.", the screen
    again, 400, nothing saved, what was typed and chosen kept (a refused
    set keeps its rating chosen). On a round's screen the round's rating
    ("Koliko je bio težak ovaj krug?") goes on every exercise the round
    saved, an unrated round keeping the rating they had (the last rated
    round's stands). The history's Serije end an exercise's sets with
    "težina 8/10" (the day's Povijest and the karton). The finish screen's
    napor stays as it is."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    page = ci.get(f"{d.base}/vjezba/2").text
    assert ('<p class="pl-rate-h" id="pl-rate-h"><span class="t">Koliko je bilo teško?</span> '
            '<span class="pl-opt"><span class="t">(neobavezno)</span></span></p>' in page)
    assert rate_rows(page) == [str(n) for n in range(1, 11)] and 'role="radiogroup" aria-labelledby="pl-rate-h"' in page
    log_form = page.split('id="plLog"')[1].split("</form>")[0]
    assert log_form.index("</table>") < log_form.index('class="pl-rate"') < log_form.index('class="btn pl-save"')
    form = {"rows": "1", "item": str(d.items[1]), "reps_1": "10", "kg_1": "20"}
    r = ci.post(f"{d.base}/vjezba/2", data={**form, "effort": "7"}, follow_redirects=False)
    assert r.status_code == 303 and db.get_pass(log_id, ivan).done_items[d.items[1]]["effort"] == 7
    assert rate_rows(ci.get(f"{d.base}/vjezba/2").text)[6] == "7*"
    ci.post(f"{d.base}/vjezba/2", data={**form, "effort": "10"})
    assert db.get_pass(log_id, ivan).done_items[d.items[1]]["effort"] == 10
    ci.post(f"{d.base}/vjezba/2", data=form)                                 # a re-save with none: none
    assert "effort" not in db.get_pass(log_id, ivan).done_items[d.items[1]]
    assert "*" not in "".join(rate_rows(ci.get(f"{d.base}/vjezba/2").text))
    for bad in ("0", "11", "abc", "7.5", "-1", "007"):
        r = ci.post(f"{d.base}/vjezba/2", data={**form, "kg_1": "22", "effort": bad})
        assert r.status_code == 400 and alert(r.text) == ["Neispravan broj."], bad
        assert inputs(r.text)[:2] == [("reps", "1", "10"), ("kg", "1", "22")]
    assert db.get_pass(log_id, ivan).done_items[d.items[1]]["sets"] == [{"reps": 10, "kg": 20.0}]
    r = ci.post(f"{d.base}/vjezba/2", data={**form, "kg_1": "x", "effort": "8"})   # a refused set: its rating kept
    assert r.status_code == 400 and rate_rows(r.text)[7] == "8*"
    for bad in (0, 11, True, 7.0, "7"):
        with pytest.raises(ValueError, match="^Neispravan broj.$"):
            db.save_sets(log_id, ivan, item(d, 2), [{"reps": 1, "kg": 0.0}], item(d, 2).exercise, effort=bad)
    assert db.read_effort("") is None and db.read_effort(" 9 ") == 9
    ci.post(f"{d.base}/vjezba/2", data={**form, "effort": "8"})
    ci.post(f"{d.base}/vjezba/3", data={"rows": "1", "item": str(d.items[2]), "sec_1": "40"})   # Plank: unrated
    ci.post(f"{d.base}/kraj", data={"effort": "6"})
    first = ci.get(d.base).text.split('<li class="card hist-row">')[1]
    assert sets_lines(first) == ["Goblet čučanj: 10 × 20 kg · težina 8/10", "Plank: 40 s"]
    karton = ci.get("/karton").text.split(f'id="pass-{log_id}"')[1].split('<div class="log-entry')[0]
    assert sets_lines(karton) == ["Goblet čučanj: 10 × 20 kg · težina 8/10", "Plank: 40 s"]
    assert db.get_pass(log_id, ivan).effort == 6                            # the training's napor, as ever

    c = build_circuit(title="Kružni 2")
    ci.post(f"{c.base}/kreni")
    log_id = db.open_pass(ivan, c.did).id
    ci.post(f"{c.base}/vjezba/2", data=round_form(1, {f"reps_{c.goblet}": "10", f"kg_{c.goblet}": "16",
                                                      f"sec_{c.plank}": "40"}, effort="7"))
    done = db.get_pass(log_id, ivan).done_items
    assert (done[c.goblet]["effort"], done[c.plank]["effort"]) == (7, 7)
    ci.post(f"{c.base}/vjezba/3", data=round_form(2, {f"reps_{c.goblet}": "10", f"kg_{c.goblet}": "16"}))
    done = db.get_pass(log_id, ivan).done_items
    assert (done[c.goblet]["effort"], done[c.plank]["effort"]) == (7, 7)    # unrated: the last rated round's stands
    ci.post(f"{c.base}/vjezba/4", data=round_form(3, {f"sec_{c.plank}": "35"}, effort="9"))
    done = db.get_pass(log_id, ivan).done_items
    assert (done[c.goblet]["effort"], done[c.plank]["effort"]) == (7, 9)    # only the exercises the round saved
    assert "*" not in "".join(rate_rows(ci.get(f"{c.base}/vjezba/2").text))   # a round's own rating is not kept
    r = ci.post(f"{c.base}/vjezba/2", data=round_form(1, {f"sec_{c.plank}": "40"}, effort="11"))
    assert r.status_code == 400 and alert(r.text) == ["Neispravan broj."]
    with pytest.raises(ValueError, match="^Neispravan broj.$"):
        save_round(ivan, log_id, c, 1, {c.plank: {"seconds": 40}}, effort=0)


# the load next time, set by set (db.next_set), by the band of the rating:
# (the set, the band, what it becomes), the knobs at their defaults (5 % up,
# 10 % down, 1 rep, 5 s)
NEXT_SETS = [
    ({"reps": 10, "kg": 20.0}, "up", {"reps": 10, "kg": 21.0}),            # 21: × 1.05
    ({"reps": 10, "kg": 2.0}, "up", {"reps": 10, "kg": 2.5}),              # 2.1 → 2.0, then half a kilo at least
    ({"reps": 8, "kg": 5.0}, "up", {"reps": 8, "kg": 5.5}),                # 5.25: a quarter rounds up
    ({"reps": 8, "kg": 31.0}, "up", {"reps": 8, "kg": 32.5}),              # 32.55 → 32.5
    ({"reps": 5, "kg": 499.5}, "up", {"reps": 5, "kg": 500.0}),            # 500 at most
    ({"reps": 5, "kg": 500.0}, "up", {"reps": 5, "kg": 500.0}),
    ({"reps": 12, "kg": 0.0}, "up", {"reps": 13, "kg": 0.0}),              # no weight: a rep more
    ({"reps": 999, "kg": 0.0}, "up", {"reps": 999, "kg": 0.0}),
    ({"seconds": 40}, "up", {"seconds": 45}),                              # timed: 5 s more
    ({"seconds": 3598}, "up", {"seconds": 3600}),
    ({"reps": 5, "seconds": 30}, "up", {"reps": 5, "seconds": 35}),        # reps and seconds: the seconds
    ({"reps": 10, "kg": 20.0, "round": 2}, "up", {"reps": 10, "kg": 21.0, "round": 2}),   # its round kept
    ({"reps": 10, "kg": 20.0}, "down", {"reps": 10, "kg": 18.0}),          # × 0.9
    ({"reps": 10, "kg": 22.5}, "down", {"reps": 10, "kg": 20.5}),          # 20.25 → 20.5
    ({"reps": 10, "kg": 2.0}, "down", {"reps": 10, "kg": 1.5}),            # 1.8 → 2.0, then half a kilo less
    ({"reps": 10, "kg": 1.0}, "down", {"reps": 10, "kg": 0.5}),
    ({"reps": 10, "kg": 0.5}, "down", {"reps": 10, "kg": 0.5}),            # never below 0.5
    ({"reps": 12, "kg": 0.0}, "down", {"reps": 10, "kg": 0.0}),            # 10.8, rounded down
    ({"reps": 5, "kg": 0.0}, "down", {"reps": 4, "kg": 0.0}),
    ({"reps": 2, "kg": 0.0}, "down", {"reps": 1, "kg": 0.0}),              # one less at least
    ({"reps": 1, "kg": 0.0}, "down", {"reps": 1, "kg": 0.0}),              # never below 1
    ({"reps": 0, "kg": 0.0}, "down", {"reps": 0, "kg": 0.0}),              # never more than it was
    ({"seconds": 40}, "down", {"seconds": 36}),
    ({"seconds": 9}, "down", {"seconds": 8}),                              # 8.1 → 8
    ({"seconds": 6}, "down", {"seconds": 5}),
    ({"seconds": 5}, "down", {"seconds": 5}),                              # never below 5
    ({"seconds": 3}, "down", {"seconds": 3}),
    ({"reps": 5, "seconds": 30}, "down", {"reps": 5, "seconds": 27}),
    ({"reps": 10, "kg": 20.0}, "same", {"reps": 10, "kg": 20.0}),          # 7–8: as he did it
    ({"seconds": 40}, None, {"seconds": 40}),                              # no rating: as he did it
]


def test_the_load_next_time_follows_the_rating(monkeypatch):
    """db.next_set, set by set, by the band of the rating (NEXT_SETS: each
    kind of set, its rounding and its bounds); the bands: 1–6 "up", 7–8
    "same", 9–10 "down". db.next_load reads the client's newest saved entry
    of the exercise (any pass, any day, by when it was saved; `skip` the
    screen's own entries; None for one never logged): its day (its pass's
    start), its rating, its sets as done and as the next time fills them,
    its kind ("kg" a weight in a set, "reps" kg 0 in every set, "seconds"
    a timed one). The knobs: config.PROGRESS_UP_PERCENT,
    PROGRESS_DOWN_PERCENT, PROGRESS_REPS_STEP, PROGRESS_SECONDS_STEP, read
    from the environment (5, 10, 1, 5 when unset)."""
    for st, band, want in NEXT_SETS:
        assert db.next_set(st, band) == want, (st, band)
    assert [db._band(e) for e in (None, 1, 6, 7, 8, 9, 10)] == [None, "up", "up", "same", "same", "down", "down"]
    monkeypatch.setattr(config, "PROGRESS_UP_PERCENT", 10)
    monkeypatch.setattr(config, "PROGRESS_DOWN_PERCENT", 20)
    monkeypatch.setattr(config, "PROGRESS_REPS_STEP", 2)
    monkeypatch.setattr(config, "PROGRESS_SECONDS_STEP", 10)
    assert [db.next_set(st, band) for st, band in (({"reps": 10, "kg": 20.0}, "up"), ({"reps": 10, "kg": 20.0}, "down"),
                                                    ({"reps": 12, "kg": 0.0}, "up"), ({"reps": 12, "kg": 0.0}, "down"),
                                                    ({"seconds": 40}, "up"), ({"seconds": 40}, "down"))] == [
        {"reps": 10, "kg": 22.0}, {"reps": 10, "kg": 16.0}, {"reps": 14, "kg": 0.0}, {"reps": 9, "kg": 0.0},
        {"seconds": 50}, {"seconds": 32}]
    monkeypatch.undo()

    import subprocess
    import sys
    knobs = "from qmt import config; print(config.PROGRESS_UP_PERCENT, config.PROGRESS_DOWN_PERCENT, " \
            "config.PROGRESS_REPS_STEP, config.PROGRESS_SECONDS_STEP)"
    env = {k: v for k, v in os.environ.items() if not k.startswith("PROGRESS_")}
    out = subprocess.run([sys.executable, "-c", knobs], env=env, capture_output=True, text=True, check=True).stdout
    assert out.split() == ["5", "10", "1", "5"]
    env |= {"PROGRESS_UP_PERCENT": "7", "PROGRESS_DOWN_PERCENT": "15", "PROGRESS_REPS_STEP": "2",
            "PROGRESS_SECONDS_STEP": "10"}
    out = subprocess.run([sys.executable, "-c", knobs], env=env, capture_output=True, text=True, check=True).stdout
    assert out.split() == ["7", "15", "2", "10"]

    trainer, ivan, ana = people()
    d = build_day()
    assert db.next_load(ivan, d.ex["Goblet čučanj"]) is None
    first = finished(ivan, d, {2: [{"reps": 10, "kg": 20.0}, {"reps": 8, "kg": 22.5}]}, days_ago=3)
    load = db.next_load(ivan, d.ex["Goblet čučanj"])
    assert (load.effort, load.band, load.kind, load.rated, load.word, load.short) == (None, None, "kg", False, "", "")
    assert load.next == load.sets == ({"reps": 10, "kg": 20.0}, {"reps": 8, "kg": 22.5})
    assert load.on == (datetime.now(config.TZ) - timedelta(days=3)).date()
    log = open_pass(ivan, d)
    db.save_sets(log.id, ivan, item(d, 2), [{"reps": 10, "kg": 20.0}, {"reps": 10, "kg": 20.0}], item(d, 2).exercise,
                 effort=9)
    load = db.next_load(ivan, d.ex["Goblet čučanj"])                        # the newest: this pass's, rated 9
    assert (load.effort, load.band, load.word, load.short, load.on) == (9, "down", "malo lakše", "malo lakše", config.today())
    assert load.next == ({"reps": 10, "kg": 18.0}, {"reps": 10, "kg": 18.0})
    assert (load.done_text, load.next_text) == ("10 × 20 kg", "18 kg")
    skipped = db.next_load(ivan, d.ex["Goblet čučanj"], {(log.id, d.items[1])})   # the screen's own left out
    assert skipped.effort is None and skipped.sets[1] == {"reps": 8, "kg": 22.5}
    assert db.next_load(ana, d.ex["Goblet čučanj"]) is None                 # his log, not hers
    db.save_sets(log.id, ivan, item(d, 1), [{"reps": 12, "kg": 0.0}, {"reps": 15, "kg": 0.0}], item(d, 1).exercise,
                 effort=4)
    load = db.next_load(ivan, d.ex["Čučanj s vlastitom težinom"])
    assert (load.kind, load.band, load.next, load.done_text, load.next_text) == (
        "reps", "up", ({"reps": 13, "kg": 0.0}, {"reps": 16, "kg": 0.0}), "12 ponavljanja", "13 ponavljanja")
    db.save_sets(log.id, ivan, item(d, 3), [{"seconds": 40}], item(d, 3).exercise, effort=8)
    load = db.next_load(ivan, d.ex["Plank"])
    assert (load.kind, load.band, load.word, load.short, load.next) == ("seconds", "same", "ostaje isto", "isto",
                                                                         ({"seconds": 40},))
    assert first and db.next_loads(ivan, [d.ex["Plank"], d.ex["Goblet čučanj"], 987654]).keys() == {
        d.ex["Plank"], d.ex["Goblet čučanj"]}


def test_the_card_says_the_load_and_the_set_log_starts_from_it():
    """After a rated pass the next one's set log starts from the load next
    time: a weighted exercise's KG (rated 9: 20 → 18; its reps the
    plan's), one done with no weight its PON. (rated 5: 12 → 13), a timed
    one its SEK. (rated 9: 40 → 36); an unrated one as before (KG as he
    did it, PON. and SEK. the plan's); one never logged the plan's numbers
    and the plan's kg. The card says it under the dose (.pl-next): "Prošli
    put (D): 10 × 20 kg, težina 9 — malo lakše: 18 kg.", "…, težina 8 —
    ostaje isto.", "Prošli put (D): 12 ponavljanja, težina 5 — malo više:
    13 ponavljanja.", "Prošli put (D): 40 s, težina 9 — malo lakše: 36 s.";
    with no rating nothing is said. A circuit's round says a word after an
    exercise's planned dose ("malo više" / "isto" / "malo lakše") and its
    inputs start from the load of its place (the weight of this pass's
    round before first)."""
    trainer, ivan, ana = people()
    d = build_day()
    db.update_day_item(d.items[3], "istezanje", None, None, None, None, None, "", kg=5)   # never logged: its kg
    ci = client_for("ivan@test.local")
    log = open_pass(ivan, d)
    for k, sets, effort in ((1, [{"reps": 12, "kg": 0.0}, {"reps": 10, "kg": 0.0}], 5),
                            (2, [{"reps": 10, "kg": 20.0}, {"reps": 8, "kg": 20.0}], 9),
                            (3, [{"seconds": 40}, {"seconds": 30}], 9)):
        it = item(d, k)
        db.save_sets(log.id, ivan, it, sets, it.exercise, effort=effort)
    db.finish_pass(log.id, ivan, 7, None, "")
    shift(log.id, days=2)
    on = (datetime.now(config.TZ) - timedelta(days=2)).date()
    day = f"{on.day}.{on.month}." + (f"{on.year}." if on.year != config.today().year else "")
    ci.post(f"{d.base}/kreni")

    def line(k: int) -> str | None:
        m = re.search(r'<p class="pl-next">([^<]*)</p>', ci.get(f"{d.base}/vjezba/{k}").text)
        return m and unescape(m.group(1))

    page = ci.get(f"{d.base}/vjezba/1").text                               # 2 × 15, no weight, rated 5
    assert inputs(page) == [("reps", "1", "13"), ("kg", "1", ""), ("reps", "2", "11"), ("kg", "2", ""),
                            ("reps", "3", ""), ("kg", "3", "")]
    assert line(1) == f"Prošli put ({day}): 12 ponavljanja, težina 5 — malo više: 13 ponavljanja."
    page = ci.get(f"{d.base}/vjezba/2").text                               # 3 × 10, weighted, rated 9
    assert re.search(r'<p class="pl-dose">3 × 10</p>\s*<p class="pl-next">', page)
    assert inputs(page) == [("reps", "1", "10"), ("kg", "1", "18"), ("reps", "2", "10"), ("kg", "2", "18"),
                            ("reps", "3", "10"), ("kg", "3", "18"), ("reps", "4", ""), ("kg", "4", "")]
    assert line(2) == f"Prošli put ({day}): 10 × 20 kg, težina 9 — malo lakše: 18 kg."
    page = ci.get(f"{d.base}/vjezba/3").text                               # 3 × 40 s, rated 9
    assert inputs(page) == [("sec", "1", "36"), ("sec", "2", "27"), ("sec", "3", "27"), ("sec", "4", "")]
    assert line(3) == f"Prošli put ({day}): 40 s, težina 9 — malo lakše: 36 s."
    page = ci.get(f"{d.base}/vjezba/4").text                               # never logged: the plan's kg
    assert inputs(page) == [("reps", "1", ""), ("kg", "1", "5"), ("reps", "2", ""), ("kg", "2", "")]
    assert line(4) is None and 'class="pl-next"' not in page

    now = db.open_pass(ivan, d.did)
    ci.post(f"{d.base}/vjezba/2", data={"rows": "1", "item": str(d.items[1]), "reps_1": "10", "kg_1": "18", "effort": "8"})
    assert line(2) == f"Prošli put ({day}): 10 × 20 kg, težina 9 — malo lakše: 18 kg."   # its own save is not last time
    db.finish_pass(now.id, ivan, 6, None, "")
    ci.post(f"{d.base}/kreni")
    today = web._date_text(config.today())
    assert line(2) == f"Prošli put ({today}): 10 × 18 kg, težina 8 — ostaje isto."
    assert [v for f, _, v in inputs(ci.get(f"{d.base}/vjezba/2").text) if f == "kg"] == ["18", "18", "18", ""]
    db.drop_pass(db.open_pass(ivan, d.did).id, ivan)
    unrated = open_pass(ivan, d)
    db.save_sets(unrated.id, ivan, item(d, 2), [{"reps": 6, "kg": 22.5}], item(d, 2).exercise)
    db.save_sets(unrated.id, ivan, item(d, 1), [{"reps": 9, "kg": 0.0}], item(d, 1).exercise)
    db.finish_pass(unrated.id, ivan, 6, None, "")
    ci.post(f"{d.base}/kreni")
    assert line(2) is None and line(1) is None                               # no rating, nothing said
    assert [v for f, _, v in inputs(ci.get(f"{d.base}/vjezba/2").text) if f in ("reps", "kg")][:2] == ["10", "22.5"]
    assert [v for f, _, v in inputs(ci.get(f"{d.base}/vjezba/1").text) if f == "reps"][:2] == ["15", "15"]   # the plan's
    db.drop_pass(db.open_pass(ivan, d.did).id, ivan)
    easy = open_pass(ivan, d)                                               # a weighted one rated 5: a little more
    db.save_sets(easy.id, ivan, item(d, 2), [{"reps": 10, "kg": 20.0}], item(d, 2).exercise, effort=5)
    db.finish_pass(easy.id, ivan, 5, None, "")
    ci.post(f"{d.base}/kreni")
    assert line(2) == f"Prošli put ({today}): 10 × 20 kg, težina 5 — malo više: 21 kg."
    assert [v for f, _, v in inputs(ci.get(f"{d.base}/vjezba/2").text) if f == "kg"] == ["21", "21", "21", ""]
    db.drop_pass(db.open_pass(ivan, d.did).id, ivan)

    c = build_circuit(title="Kružni 2")
    old = db.start_pass(ivan, db.get_program(c.pid), db.get_day(c.did))
    save_round(ivan, old.id, c, 1, {c.goblet: {"reps": 10, "kg": 20.0}, c.plank: {"seconds": 40}}, effort=9)
    save_round(ivan, old.id, c, 2, {c.goblet: {"reps": 10, "kg": 30.0}}, effort=5)
    db.finish_pass(old.id, ivan, 7, None, "")
    ci.post(f"{c.base}/kreni")
    page = ci.get(f"{c.base}/vjezba/2").text                               # round 1: Goblet rated 5 last, Plank 9
    rows = blocks(page)
    assert re.findall(r'<p class="cr-dose">([^<]*)</p>', rows[0]) == ["10 ponavljanja · 16 kg · malo više", "pete na podu"]
    assert re.findall(r'<p class="cr-dose">([^<]*)</p>', rows[1]) == ["40 s · malo lakše"]
    assert inputs(page) == [("reps", str(c.goblet), "10"), ("kg", str(c.goblet), "21"), ("sec", str(c.plank), "36")]
    assert 'class="pl-next"' not in page
    page = ci.get(f"{c.base}/vjezba/3").text                               # round 2: its place's load
    assert inputs(page) == [("reps", str(c.goblet), "10"), ("kg", str(c.goblet), "31.5"), ("sec", str(c.plank), "36")]
    ci.post(f"{c.base}/vjezba/2", data=round_form(1, {f"reps_{c.goblet}": "10", f"kg_{c.goblet}": "21",
                                                      f"sec_{c.plank}": "36"}, effort="8"))
    page = ci.get(f"{c.base}/vjezba/3").text                               # this pass's round 1 weight first
    assert inputs(page) == [("reps", str(c.goblet), "10"), ("kg", str(c.goblet), "21"), ("sec", str(c.plank), "36")]
    assert re.findall(r'<p class="cr-dose">([^<]*)</p>', blocks(page)[0])[0] == "10 ponavljanja · 16 kg · malo više"


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


def _schema_diffs(table: str) -> list:
    """What compare_metadata finds between qmt_test and the models about one table."""
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
    return [d for d in diffs if about(d) == table]


def test_the_migration_makes_the_table_and_takes_it_away():
    """3890252ee50f, run on qmt_test as before it (no workout_logs): the
    table as the model has it, to the indexes (the partial unique one
    refuses a second pass in progress of a client's day, not a finished one
    beside it); downgrade drops it, and a second upgrade makes it again."""
    mig = _migration("3890252ee50f_workout_logs.py")
    assert (mig.revision, mig.down_revision) == ("3890252ee50f", "7c3bf996c983")
    trainer, ivan, ana = people()
    d = build_day()
    with db.engine.begin() as conn:
        conn.execute(sa_text("DROP TABLE workout_logs"))
    _run(mig.upgrade)
    assert "workout_logs" in sa_inspect(db.engine).get_table_names() and _schema_diffs("workout_logs") == []
    assert {i["name"] for i in sa_inspect(db.engine).get_indexes("workout_logs")} == {
        "ix_workout_logs_user_id", "ix_workout_logs_day_id", "ix_workout_logs_user_id_started_at", "uq_workout_logs_open"}
    first = open_pass(ivan, d)
    with pytest.raises(IntegrityError, match="uq_workout_logs_open"):
        with db.engine.begin() as conn:
            conn.execute(sa_text("INSERT INTO workout_logs (user_id, program_id, day_id, program_title, day_label) "
                                 "VALUES (:u, :p, :d, 'x', 'y')"), {"u": ivan, "p": d.pid, "d": d.did})
    db.finish_pass(first.id, ivan, 5, None, "")
    assert open_pass(ivan, d).id != first.id
    with db.engine.begin() as conn:                                        # the defaults: a finished row, as bare as can be
        assert conn.execute(sa_text("INSERT INTO workout_logs (user_id, program_id, day_id, program_title, day_label, "
                                    "finished_at) VALUES (:u, :p, :d, 'x', 'y', now()) "
                                    "RETURNING done, swaps, note, started_at IS NOT NULL"),
                            {"u": ivan, "p": d.pid, "d": d.did}).one() == ("{}", "{}", "", True)
    db.delete_day(d.did)                                                   # SET NULL: the passes stay
    assert [day for _, _, day, _ in stored()] == [None, None, None]
    _run(mig.downgrade)
    assert "workout_logs" not in sa_inspect(db.engine).get_table_names()
    _run(mig.upgrade)
    assert _schema_diffs("workout_logs") == [] and stored() == []


def test_the_label_migration_renames_the_stored_days():
    """b61e8d5bf1db (2.11.2026: a day reads "Trening N", Amir's word), run on
    qmt_test with passes stored as before it: every day_label that starts
    "Dan <digit>" starts "Trening", its number and title kept (prod's "Dan 1
    · Cijelo tijelo", "Dan 3 · X", "Dan 12"); nothing else changes: a label
    already new (a pass started since, "Trening 1 · Cijelo tijelo"), one
    with no number or that only starts so ("Danas"), a "Dan 1" further in,
    the programme's title. Downgrade makes every "Trening <digit>" "Dan"
    again, and a second upgrade renames them again. No schema change."""
    mig = _migration("b61e8d5bf1db_workout_logs_day_label_trening.py")
    assert (mig.revision, mig.down_revision) == ("b61e8d5bf1db", "4f9d6f7103ad")
    trainer, ivan, ana = people()
    d = build_day()
    finished(ivan, d)                                                       # its snapshot already the new label
    old = ["Dan 1 · Cijelo tijelo", "Dan 3 · X", "Dan 12", "Dan 2 · Dan 1", "Trening 2", "Danas", "Dan · bez broja", "y"]
    with db.engine.begin() as conn:
        for label in old:
            conn.execute(sa_text("INSERT INTO workout_logs (user_id, program_id, day_id, program_title, day_label, "
                                 "finished_at) VALUES (:u, :p, :d, 'Dan 1', :l, now())"),
                         {"u": ivan, "p": d.pid, "d": d.did, "l": label})

    def labels() -> list[str]:
        with db.engine.connect() as conn:
            return [label for label, in conn.execute(sa_text("SELECT day_label FROM workout_logs ORDER BY id"))]

    def titles() -> list[str]:
        with db.engine.connect() as conn:
            return [title for title, in conn.execute(sa_text("SELECT program_title FROM workout_logs ORDER BY id"))]

    assert labels() == ["Trening 1 · Cijelo tijelo", *old]
    renamed = ["Trening 1 · Cijelo tijelo", "Trening 1 · Cijelo tijelo", "Trening 3 · X", "Trening 12",
               "Trening 2 · Dan 1", "Trening 2", "Danas", "Dan · bez broja", "y"]
    _run(mig.upgrade)
    assert labels() == renamed and titles() == ["Cijelo tijelo — početna"] + ["Dan 1"] * len(old)
    _run(mig.downgrade)
    assert labels() == ["Dan 1 · Cijelo tijelo", "Dan 1 · Cijelo tijelo", "Dan 3 · X", "Dan 12", "Dan 2 · Dan 1",
                        "Dan 2", "Danas", "Dan · bez broja", "y"]
    _run(mig.upgrade)
    assert labels() == renamed and _schema_diffs("workout_logs") == []


# ---------- in a browser, on a phone ----------

@pytest.fixture(scope="module")
def server():
    import uvicorn
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True); th.start()
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/healthz", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{PORT}"
    srv.should_exit = True; th.join(timeout=5)


OVERFLOW = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"


def test_a_client_walks_a_day_on_a_phone(server):
    """At 390px, touch: ivan, two passes of the day behind him (Goblet
    čučanj at 20 kg the last time), presses Kreni, sees exercise 1 (Goblet)
    with its kg prefilled, saves its set log, swaps exercise 2 (Sklekovi)
    for its similar one, skips to the end, finishes with napor 7, and sees
    "Odrađen 3× · zadnji put danas" and the new history row. The player,
    the finish screen and the day's page never scroll sideways; no page
    errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("ivan@test.local")
    names = ("Goblet čučanj", "Sklekovi", "Plank", "Sklekovi s koljena")
    ex = {n: db.create_exercise(n) for n in names}
    db.update_exercise(ex["Sklekovi"], "Sklekovi", "Tijelo u ravnoj liniji.", "", "prsa, kod kuće", {ex["Sklekovi s koljena"]})
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    db.update_day(did, "Cijelo tijelo", 0, "")
    for name, sets, reps, seconds in (("Goblet čučanj", 3, 10, None), ("Sklekovi", 3, 10, None), ("Plank", 3, None, 40)):
        iid = db.add_day_item(did, ex[name], "trening")
        db.update_day_item(iid, "trening", sets, reps, seconds, 60, None, "")
    d = SimpleNamespace(pid=pid, did=did, items=[it.id for it in db.get_day(did).items], ex=ex, base=f"/treninzi/{pid}/dan/{did}")
    ivan = db.get_user_by_email("ivan@test.local").id
    finished(ivan, d, {1: [{"reps": 10, "kg": 16.0}] * 3}, effort=6, days_ago=7, minutes=41)
    finished(ivan, d, {1: [{"reps": 10, "kg": 20.0}] * 3}, effort=7, days_ago=3, minutes=38)
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(server + "/login")
        pg.evaluate("() => localStorage.setItem('qmt-a2hs', 'installed')")
        pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
        pg.goto(server + d.base); pg.wait_for_load_state("networkidle")
        check((pg.text_content(".dx-state") or "").startswith("Odrađen 2× · zadnji put"), f"the state: {pg.text_content('.dx-state')}")
        with pg.expect_navigation():
            pg.tap(".dx-start .go button")
        pg.wait_for_load_state("networkidle")
        check(pg.url == f"{server}{d.base}/vjezba/1", f"Kreni led to {pg.url}")
        check(pg.text_content("h1.pl-name") == "Goblet čučanj", f"exercise 1 is {pg.text_content('h1.pl-name')}")
        check([pg.input_value(f"input[name=kg_{i}]") for i in (1, 2, 3)] == ["20", "20", "20"],
              f"the kg prefilled: {[pg.input_value(f'input[name=kg_{i}]') for i in (1, 2, 3)]}")
        check(pg.evaluate(OVERFLOW) == 0, f"the player overflows by {pg.evaluate(OVERFLOW)}px")
        check(pg.is_visible(".pl-timer") and pg.is_visible("#plAdd") and pg.is_visible(".pl-dock"),
              "the timer, + or the dock is not shown")
        pg.fill("input[name=kg_3]", "22.5")
        with pg.expect_navigation():
            pg.tap(".pl-save")
        pg.wait_for_load_state("networkidle")
        check(pg.url == f"{server}{d.base}/vjezba/2", f"Spremi led to {pg.url}")
        log = db.open_pass(ivan, did)
        check(log is not None and log.done_items.get(d.items[0], {}).get("sets") ==
              [{"reps": 10, "kg": 20.0}, {"reps": 10, "kg": 20.0}, {"reps": 10, "kg": 22.5}], "the set log was not saved")
        check(pg.get_attribute(".pl-segs > span:first-child", "class") == "done", "the bar's first segment is not done")
        pg.tap(".swap > summary")
        with pg.expect_navigation():
            pg.tap(".swap-row button")
        pg.wait_for_load_state("networkidle")
        check(pg.text_content("h1.pl-name") == "Sklekovi s koljena" and pg.is_visible("text=Zamjena za: Sklekovi"),
              f"the swap shows {pg.text_content('h1.pl-name')}")
        with pg.expect_navigation():
            pg.tap("text=Preskoči →")
        pg.wait_for_load_state("networkidle")
        with pg.expect_navigation():
            pg.tap("text=Preskoči i završi")
        pg.wait_for_load_state("networkidle")
        check(pg.url == f"{server}{d.base}/kraj", f"the end is {pg.url}")
        check("1 od 3 vježbe" in (pg.text_content(".kr-sum") or ""), f"the finish screen says {pg.text_content('.kr-sum')}")
        check(pg.evaluate(OVERFLOW) == 0, f"the finish screen overflows by {pg.evaluate(OVERFLOW)}px")
        pg.tap(".scale label.sc:nth-child(7)")
        with pg.expect_navigation():
            pg.tap(".kr-go .btn")
        pg.wait_for_load_state("networkidle")
        check(pg.url.startswith(f"{server}{d.base}?ok="), f"Spremi trening led to {pg.url}")
        check(pg.text_content(".dx-state") == "Odrađen 3× · zadnji put danas", f"the state: {pg.text_content('.dx-state')}")
        first = " ".join((pg.text_content(".hist-row .hist-line") or "").split())
        today = config.today()
        check(first.startswith(f"{today.day}.{today.month}. · 1/3 vježbe ·") and first.endswith("· napor 7"),
              f"the new history row says {first!r}")
        check(pg.evaluate(OVERFLOW) == 0, f"the day's page overflows by {pg.evaluate(OVERFLOW)}px")
        done = db.passes(ivan, did)
        check(len(done) == 3 and done[0].effort == 7 and done[0].swap_items == {d.items[1]: ex["Sklekovi s koljena"]},
              "the pass was not stored as walked")
        problems += errors
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


def test_the_rest_timers_on_a_phone(server):
    """At 390px, touch: ivan on an exercise with 60 s of rest between sets
    (and 90 s after it) presses ✓ on set 1: the row is done and the rest
    bar shows "1:00" with the dock hidden, the page never wider than the
    screen; "Preskoči odmor" hides the bar and the dock is back; a second ✓
    unmarks the row and starts nothing. Spremi goes on to the next
    exercise with ?odmor=90, whose screen opens with the bar at "1:30"; a
    ✓ there restarts it with that exercise's rest between sets (1 s),
    which runs out: "Kreni" and "0:00", then the bar goes and the dock is
    back. No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("ivan@test.local")
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    goblet = db.add_day_item(did, db.create_exercise("Goblet čučanj"), "trening")
    db.update_day_item(goblet, "trening", 3, 10, None, 60, 90, "")
    plank = db.add_day_item(did, db.create_exercise("Plank"), "trening")
    db.update_day_item(plank, "trening", 3, None, 40, 1, None, "")
    base = f"/treninzi/{pid}/dan/{did}"
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    def bar(pg) -> tuple:
        """(the bar shown, its eyebrow, its countdown, the dock shown)."""
        return (pg.is_visible("#plRest"), pg.text_content(".pl-rest-h"), pg.text_content(".pl-rest-t"),
                pg.is_visible(".pl-dock"))

    def tick(pg) -> tuple:
        """Set 1's ✓: (pressed, its row's class)."""
        return (pg.get_attribute(".pl-done >> nth=0", "aria-pressed"),
                pg.evaluate("() => document.querySelector('.pl-sets tbody tr').className"))

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(server + "/login")
        pg.evaluate("() => localStorage.setItem('qmt-a2hs', 'installed')")
        pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
        pg.goto(server + base); pg.wait_for_load_state("networkidle")
        with pg.expect_navigation():
            pg.tap(".dx-start .go button")
        pg.wait_for_load_state("networkidle")
        check(pg.url == f"{server}{base}/vjezba/1", f"Kreni led to {pg.url}")
        check(pg.is_visible("thead th.pl-tick") and pg.locator("td.pl-tick:visible").count() == 4,
              "the ✓ column is not shown on every row")
        check(bar(pg)[0] is False and bar(pg)[3] is True, f"before a ✓: {bar(pg)}")
        pg.locator(".pl-done").first.tap()
        pg.wait_for_timeout(100)
        check(tick(pg) == ("true", "is-done"), f"the ✓ pressed: {tick(pg)}")
        check(bar(pg) == (True, "Odmor", "1:00", False), f"the rest between sets: {bar(pg)}")
        check(pg.evaluate(OVERFLOW) == 0, f"the player with the bar overflows by {pg.evaluate(OVERFLOW)}px")
        pg.tap(".pl-rest-skip")
        pg.wait_for_timeout(100)
        check(bar(pg)[0] is False and bar(pg)[3] is True, f"after Preskoči: {bar(pg)}")
        pg.locator(".pl-done").first.tap()
        pg.wait_for_timeout(100)
        check(tick(pg) == ("false", "") and bar(pg)[0] is False, f"the second ✓: {tick(pg)}, {bar(pg)}")
        with pg.expect_navigation():
            pg.tap(".pl-save")
        pg.wait_for_load_state("networkidle")
        check(pg.url == f"{server}{base}/vjezba/2?odmor=90", f"Spremi led to {pg.url}")
        check(bar(pg) == (True, "Odmor", "1:30", False), f"the rest between exercises: {bar(pg)}")
        check(pg.evaluate(OVERFLOW) == 0, f"the next exercise with the bar overflows by {pg.evaluate(OVERFLOW)}px")
        pg.locator(".pl-done").first.tap()
        pg.wait_for_timeout(100)
        check(bar(pg)[:3] == (True, "Odmor", "0:01"), f"a ✓ while a rest runs: {bar(pg)}")
        try:
            pg.wait_for_function("() => document.querySelector('.pl-rest-h').textContent === 'Kreni'", timeout=5000)
            check(bar(pg)[:3] == (True, "Kreni", "0:00"), f"at zero: {bar(pg)}")
            pg.wait_for_function("() => document.getElementById('plRest').hidden", timeout=5000)
            check(bar(pg)[3] is True, "the dock is not back after the rest")
        except Exception as e:                                              # reported below
            problems.append(f"the rest did not run out: {bar(pg)} ({type(e).__name__})")
        problems += errors
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


def test_leaving_the_player_on_a_phone(server):
    """At 390px, touch (31.10.2026; the owner: leaving the training asks "if
    he wants to finish the training and then he decides"): ivan on exercise
    1 of a pass taps "← Natrag": #leaveDlg opens ("Završi trening" its
    primary) and the page stays, never wider than the screen; its ✕ closes
    it, still there. The brand (a member's one-task pill, to /) opens it
    too, and its "Odbaci trening" drops the pass and goes on to /. A new
    pass: "← Natrag", then "Završi trening", lands on the finish screen;
    there the brand opens it with "Natrag na osvrt", which closes it on the
    first napor button; the finish screen's own "Odbaci trening" is inside
    the pass (#confirmDlg asks, not #leaveDlg). What no link carries (a
    script's navigation: the stand-in for a closed tab or a typed address)
    meets the browser's own prompt (beforeunload), dismissed: the page
    stays, the pass open. No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("ivan@test.local")
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    for name in ("Goblet čučanj", "Sklekovi"):
        iid = db.add_day_item(did, db.create_exercise(name), "trening")
        db.update_day_item(iid, "trening", 3, 10, None, None, None, "")
    base = f"/treninzi/{pid}/dan/{did}"
    ivan = db.get_user_by_email("ivan@test.local").id
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    def shown(pg, dialog: str = "#leaveDlg") -> bool:
        return pg.evaluate("s => document.querySelector(s).open", dialog)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(server + "/login")
        pg.evaluate("() => localStorage.setItem('qmt-a2hs', 'installed')")
        pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
        player, kraj = f"{server}{base}/vjezba/1", f"{server}{base}/kraj"

        ctx.request.post(f"{server}{base}/kreni")
        pg.goto(player); pg.wait_for_load_state("networkidle")
        pg.tap(".pl-line a.act-quiet")                                     # ← Natrag
        pg.wait_for_timeout(150)
        check(shown(pg) and pg.url == player, f"← Natrag: the dialog {shown(pg)}, the page {pg.url}")
        check(pg.text_content("#leaveGo") == "Završi trening", f"the player's primary: {pg.text_content('#leaveGo')}")
        check(pg.evaluate(OVERFLOW) == 0, f"the player with the dialog overflows by {pg.evaluate(OVERFLOW)}px")
        pg.tap("#leaveDlg .fb-x button")
        pg.wait_for_timeout(150)
        check(not shown(pg) and pg.url == player, f"the ✕: the dialog {shown(pg)}, the page {pg.url}")
        pg.tap(".topbar.compact a.brand")
        pg.wait_for_timeout(150)
        check(shown(pg) and pg.url == player, f"the brand: the dialog {shown(pg)}, the page {pg.url}")
        with pg.expect_navigation():
            pg.tap("#leaveDrop")
        pg.wait_for_load_state("networkidle")
        check(pg.url == f"{server}/", f"Odbaci trening led to {pg.url}")
        check(db.open_pass(ivan, did) is None, "Odbaci trening left the pass open")

        ctx.request.post(f"{server}{base}/kreni")
        pg.goto(player); pg.wait_for_load_state("networkidle")
        pg.tap(".pl-line a.act-quiet")
        pg.wait_for_timeout(150)
        with pg.expect_navigation():
            pg.tap("#leaveGo")
        pg.wait_for_load_state("networkidle")
        check(pg.url == kraj, f"Završi trening led to {pg.url}")
        pg.tap(".topbar.compact a.brand")
        pg.wait_for_timeout(150)
        check(shown(pg) and pg.text_content("#leaveGo") == "Natrag na osvrt",
              f"the finish screen's dialog: {shown(pg)}, its primary {pg.text_content('#leaveGo')}")
        pg.tap("#leaveGo")
        pg.wait_for_timeout(150)
        check(not shown(pg) and pg.url == kraj, f"Natrag na osvrt: the dialog {shown(pg)}, the page {pg.url}")
        check(pg.evaluate("() => document.activeElement.matches('.kr-form input[name=effort][value=\"1\"]')"),
              "Natrag na osvrt did not focus the first napor button")
        pg.tap(".kr-drop")
        pg.wait_for_timeout(150)
        check(shown(pg, "#confirmDlg") and not shown(pg), "the finish screen's Odbaci did not ask in #confirmDlg alone")
        pg.tap("#confirmDlg .btn-ghost")                                   # Odustani
        pg.wait_for_timeout(150)
        check(not shown(pg, "#confirmDlg") and pg.url == kraj, "Odustani did not keep the finish screen")

        types: list[str] = []

        def on_dialog(d) -> None:
            types.append(d.type)
            d.dismiss()

        pg.on("dialog", on_dialog)
        pg.evaluate("() => { location.href = '/'; }")
        pg.wait_for_timeout(500)
        check(types == ["beforeunload"] and pg.url == kraj, f"leaving by script: dialogs {types}, the page {pg.url}")
        check(db.open_pass(ivan, did) is not None, "the pass is not open after staying")
        problems += errors
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


def test_a_circuit_on_a_phone(server):
    """At 390px, touch (25.11.2026: a circuit ticked a round at a time): ivan
    walks a day whose Glavni dio A is a circuit of 2 rounds × 3 exercises
    (Goblet čučanj with 16 kg planned, Sklekovi, Plank; 30 s after a round)
    and whose Istezanje is a normal part, to the finish screen. The day's
    page says the part's line; Kreni lands on round 1, "Krug 1 od 2", the
    three exercises on one card with their inputs prefilled (the plan's
    reps, seconds and weight), no clip box, no ✓, no "+"; an exercise's
    name opens its clip and cues in place. ONE tap per round ("Krug 1
    odrađen", the round rated 7) saves the round whole and goes on with
    the rest bar counting the rest after the round (data-odmor 30, "0:30",
    the dock hidden): after round 1 on round 2 (its weight this pass's
    round 1's), after round 2 on the stretch; the list's marks "1/2" each,
    then a ✓ each; the stretch's "Spremi i završi" leads to the finish
    screen, "4 od 4 vježbe". No screen is wider than the phone; no page
    errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    ivan = make_user("ivan@test.local")
    pid = db.create_program("Kružni — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    db.update_day(did, "Kružni", 0, "")
    for name, section, reps, seconds, kg in (("Goblet čučanj", "trening", 10, None, 16), ("Sklekovi", "trening", 10, None, None),
                                             ("Plank", "trening", None, 40, None),
                                             ("Istezanje stražnje lože", "istezanje", None, 30, None)):
        iid = db.add_day_item(did, db.create_exercise(name, "Polako, kontrolirano."), section)
        db.update_day_item(iid, section, 3, reps, seconds, 60, 10, "", kg=kg)
    db.set_circuit(did, "trening", 2, 30)
    base = f"/treninzi/{pid}/dan/{did}"
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    def tap_save(pg, to: str) -> None:
        """Skip a rest that runs (its bar lies over the column's foot), then the round's (or the step's) one button."""
        if pg.is_visible("#plRest"):
            pg.tap(".pl-rest-skip")
        with pg.expect_navigation():
            pg.tap(".pl-save")
        pg.wait_for_load_state("networkidle")
        check(pg.url == f"{server}{base}{to}", f"the button led to {pg.url}, not {to}")
        check(pg.evaluate(OVERFLOW) == 0, f"{to} overflows by {pg.evaluate(OVERFLOW)}px")

    def values(pg) -> list[str]:
        return pg.evaluate("() => [...document.querySelectorAll('.cr-in input')].map(i => i.value)")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(server + "/login")
        pg.evaluate("() => localStorage.setItem('qmt-a2hs', 'installed')")
        pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
        pg.goto(server + base); pg.wait_for_load_state("networkidle")
        check(pg.text_content(".dx-circ") == "Kružno · 2 kruga · odmor između krugova 30 s",
              f"the day's circuit line: {pg.text_content('.dx-circ')}")
        check(pg.evaluate(OVERFLOW) == 0, f"the day's page overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap(".dx-start .go button")
        pg.wait_for_load_state("networkidle")
        check(pg.url == f"{server}{base}/vjezba/1", f"Kreni led to {pg.url}")
        check(pg.text_content(".pl-round") == "Krug 1 od 2" and pg.text_content("h1.pl-name") == "Glavni dio A",
              f"round 1: {pg.text_content('.pl-round')}, {pg.text_content('h1.pl-name')}")
        check(pg.locator(".cr-row").count() == 3 and pg.locator("#plAdd").count() == 0 and pg.locator(".pl-tick").count() == 0
              and pg.locator("#plStage").count() == 0, "the round is not one card of three without the clip box, + and ✓")
        check(values(pg) == ["10", "16", "10", "", "40"], f"round 1's first values: {values(pg)}")
        check(pg.evaluate(OVERFLOW) == 0, f"the round overflows by {pg.evaluate(OVERFLOW)}px")
        pg.locator(".cr-ex summary").first.tap()
        pg.wait_for_timeout(200)
        check(pg.locator(".cr-ex").first.evaluate("d => d.open") and pg.locator(".cr-body").first.is_visible(),
              "an exercise's name did not open its clip and cues")
        check(pg.evaluate(OVERFLOW) == 0, f"the round with an exercise open overflows by {pg.evaluate(OVERFLOW)}px")
        pg.locator(".pl-rate label.sc").nth(6).tap()                        # the round rated 7
        tap_save(pg, "/vjezba/2?odmor=30")                                  # one tap: round 1 saved whole
        bar = (pg.is_visible("#plRest"), pg.text_content(".pl-rest-t"), pg.is_visible(".pl-dock"))
        check(bar[0] and bar[1] in ("0:30", "0:29") and not bar[2], f"the rest after round 1: {bar}")
        check(pg.get_attribute("#plLog", "data-odmor") == "30", "the rest after the round is not on the form")
        check(pg.text_content(".pl-round") == "Krug 2 od 2" and values(pg) == ["10", "16", "10", "", "40"],
              f"round 2: {pg.text_content('.pl-round')}, {values(pg)}")
        check(pg.locator("#popis .dx-rounds").all_text_contents() == ["1/2", "1/2", "1/2"],
              f"the list's marks: {pg.locator('#popis .dx-rounds').all_text_contents()}")
        check(pg.text_content(".pl-save") == "Krug 2 odrađen", f"round 2's button: {pg.text_content('.pl-save')}")
        pg.locator(".cr-in input[name^=kg_]").first.fill("18")              # Goblet's, round 2
        tap_save(pg, "/vjezba/3?odmor=30")                                  # the final round: its rest on the stretch
        bar = (pg.is_visible("#plRest"), pg.text_content(".pl-rest-t"), pg.is_visible(".pl-dock"))
        check(bar[0] and bar[1] in ("0:30", "0:29") and not bar[2], f"the rest after round 2: {bar}")
        check(pg.locator("#popis .dx-ok").count() == 3 and pg.locator("#popis .dx-rounds").count() == 0,
              "the circuit's three exercises are not ✓ in the list")
        check(pg.text_content(".pl-save") == "Spremi i završi", f"the last step's button: {pg.text_content('.pl-save')}")
        tap_save(pg, "/kraj")
        check("4 od 4 vježbe" in (pg.text_content(".kr-sum") or ""), f"the finish screen says {pg.text_content('.kr-sum')}")
        done = db.open_pass(ivan, did).done_items
        circuit = sorted((e["name"], [(s.get("round"), s.get("kg")) for s in e["sets"]], e.get("effort"))
                         for e in done.values() if e["section"] == "trening")
        check(circuit == [("Goblet čučanj", [(1, 16.0), (2, 18.0)], 7), ("Plank", [(1, None), (2, None)], 7),
                          ("Sklekovi", [(1, 0.0), (2, 0.0)], 7)], f"the pass saved {circuit}")
        problems += errors
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


def test_a_rating_lowers_the_load_on_a_phone(server):
    """At 390px, touch (25.11.2026: the owner's "if its 9 or 10 out of 10
    difficulty, then it gets slightly reduced by a certain percentage"):
    ivan does Goblet čučanj (3 × 10, 20 kg planned), sees the rating under
    the set log (ten round buttons, five and five, none chosen), rates it 9
    and saves, finishes the training; starts again: the KG comes lower (18
    in every row) and the card says so under the dose, "Prošli put (D): 10
    × 20 kg, težina 9 — malo lakše: 18 kg."; the day's Povijest says
    "težina 9/10". No page is wider than the phone; no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    ivan = make_user("ivan@test.local")
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    db.update_day(did, "Cijelo tijelo", 0, "")
    for name, reps, seconds, kg in (("Goblet čučanj", 10, None, 20), ("Plank", None, 40, None)):
        iid = db.add_day_item(did, db.create_exercise(name), "trening")
        db.update_day_item(iid, "trening", 3, reps, seconds, 60, None, "", kg=kg)
    base = f"/treninzi/{pid}/dan/{did}"
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    def kgs(pg) -> list[str]:
        return [pg.input_value(f"input[name=kg_{i}]") for i in (1, 2, 3)]

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(server + "/login")
        pg.evaluate("() => localStorage.setItem('qmt-a2hs', 'installed')")
        pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
        pg.goto(server + base); pg.wait_for_load_state("networkidle")
        with pg.expect_navigation():
            pg.tap(".dx-start .go button")
        pg.wait_for_load_state("networkidle")
        check(kgs(pg) == ["20", "20", "20"], f"the plan's kg: {kgs(pg)}")
        check(pg.locator(".pl-next").count() == 0, "a line for the next time before any rating")
        tops = pg.evaluate("() => [...document.querySelectorAll('.pl-rate .sc > span')].map(s => Math.round(s.getBoundingClientRect().top))")
        sizes = pg.evaluate("() => [...document.querySelectorAll('.pl-rate .sc > span')].map(s => Math.round(s.getBoundingClientRect().width))")
        check(len(tops) == 10 and len(set(tops[:5])) == 1 and len(set(tops[5:])) == 1 and tops[5] > tops[0]
              and set(sizes) == {40}, f"the rating's buttons: rows {tops}, sizes {sizes}")
        check(pg.evaluate("() => document.querySelectorAll('.pl-rate input:checked').length") == 0, "a rating chosen at load")
        check(pg.evaluate(OVERFLOW) == 0, f"the step with the rating overflows by {pg.evaluate(OVERFLOW)}px")
        pg.locator(".pl-rate label.sc").nth(8).tap()                        # 9
        with pg.expect_navigation():
            pg.tap(".pl-save")
        pg.wait_for_load_state("networkidle")
        log = db.open_pass(ivan, did)
        entry = log.done_items.get(db.get_day(did).items[0].id, {}) if log else {}
        check(entry.get("effort") == 9 and entry.get("sets") == [{"reps": 10, "kg": 20.0}] * 3, f"saved: {entry}")
        with pg.expect_navigation():
            pg.tap("text=Preskoči i završi")
        pg.wait_for_load_state("networkidle")
        pg.tap(".scale label.sc:nth-child(8)")
        with pg.expect_navigation():
            pg.tap(".kr-go .btn")
        pg.wait_for_load_state("networkidle")
        check("težina 9/10" in pg.evaluate("() => document.querySelector('.hist-row details.sets').textContent"),
              "the day's Povijest does not say the rating")
        check(pg.evaluate(OVERFLOW) == 0, f"the day's page overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap(".dx-start .go button")
        pg.wait_for_load_state("networkidle")
        today = config.today()
        check(kgs(pg) == ["18", "18", "18"], f"the weight next time: {kgs(pg)}")
        check(pg.text_content(".pl-next") == f"Prošli put ({today.day}.{today.month}.): 10 × 20 kg, težina 9 — malo lakše: 18 kg.",
              f"the line: {pg.text_content('.pl-next')!r}")
        check(pg.evaluate(OVERFLOW) == 0, f"the step with the line overflows by {pg.evaluate(OVERFLOW)}px")
        problems += errors
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"
