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
Migration 3890252ee50f runs for real on qmt_test, there and back. The browser
half walks ivan through a day on a phone.

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
from qmt.models import Base, Booking, WorkoutLog
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


def make_user(email: str, is_trainer: bool = False, goal: str = "cijelo") -> int:
    """An account; a client gets the online plan and an old upitnik (version
    1, all zero: početna) whose goal is `goal`, as tests/test_programs.py's."""
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
        db.save_onboarding(u.id, json.dumps(picked), 0, "pocetna", goal, version=1, pain_level=None,
                           pain_high=False, needs_review=False, consented_at=None)
    return u.id


def client_for(email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"email": email, "password": "lozinka123"}, follow_redirects=False)
    assert r.status_code == 303, "login failed"
    return c


def people():
    """(trainer's id, ivan's, ana's): ivan početna × cijelo (the day's), ana
    početna × gornji (not his programme)."""
    return (make_user("trener@test.local", is_trainer=True), make_user("ivan@test.local"),
            make_user("ana@test.local", goal="gornji"))


def build_day(title: str = "Cijelo tijelo — početna", level: str | None = "pocetna", goal: str | None = "cijelo"):
    """A programme (ivan's combo by default) and its Dan 1 "Cijelo tijelo",
    in the day's display order:
      1 Čučanj s vlastitom težinom (zagrijavanje, 2 × 15, rest 30)
      2 Goblet čučanj (trening, 3 × 10, rest 60, "16 kg"; similar:
        Iskorak unatrag, Čučanj s vlastitom težinom)
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


def state_line(page: str) -> str | None:
    m = re.search(r'<p class="dx-state">([^<]*)</p>', page)
    return unescape(m.group(1)) if m else None


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
        "Cijelo tijelo — početna", "Dan 1 · Cijelo tijelo", {}, {}, True)
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
    assert "Dan još nema vježbi." in page and "/kreni" not in page and 'class="dx-state"' not in page

    db.update_program(d.pid, "Novo ime", None, "pocetna", "cijelo")
    db.update_day(d.did, "Drugi naslov", None, "")
    log = db.get_pass(log_id, ivan)
    assert (log.program_title, log.day_label) == ("Cijelo tijelo — početna", "Dan 1 · Cijelo tijelo")


def test_the_players_access():
    """The player follows the day's page: a guest goes to log in, another
    client's programme is 403, a day of another programme 404, an exercise
    that is not the day's 404; without a pass in progress the exercise, its
    save and the finish screen lead to the day's page (where Kreni is).
    Staff may use it: their pass is their own."""
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
    for k in (0, 5, 99):
        assert ci.get(f"{d.base}/vjezba/{k}").status_code == 404
        assert ci.post(f"{d.base}/vjezba/{k}", data={"rows": "1", "reps_1": "5"}).status_code == 404
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
    assert re.findall(r'<th scope="row">(\d+)(<span class="pl-x">dodatna serija</span>)?</th>', page) == [
        ("1", ""), ("2", ""), ("3", '<span class="pl-x">dodatna serija</span>')]
    assert re.search(r'<thead><tr><th scope="col">Set</th><th scope="col">Pon.</th><th scope="col">Kg</th>'
                     r'<th scope="col" class="pl-tick" hidden>.*?</th></tr></thead>', page)
    page = ci.get(f"{d.base}/vjezba/3").text                               # Plank: 3 × 40 s
    assert inputs(page) == [("sec", "1", "40"), ("sec", "2", "40"), ("sec", "3", "40"), ("sec", "4", "")]
    assert '<th scope="col">Sek.</th>' in page and 'name="reps_1"' not in page
    page = ci.get(f"{d.base}/vjezba/4").text                               # nothing asked: one row
    assert inputs(page) == [("reps", "1", ""), ("kg", "1", ""), ("reps", "2", ""), ("kg", "2", "")]
    page = ci.get(f"{d.base}/vjezba/2").text                               # Goblet: never logged
    assert [v for f, _, v in inputs(page) if f == "kg"] == ["", "", "", ""]

    # Goblet logged on ANOTHER day (Dan 2): its weights fill Dan 1's rows
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
    form = {"rows": "4", "reps_1": "10", "kg_1": "2,5", "reps_2": "", "kg_2": "", "reps_3": "8", "kg_3": "2.5",
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
    assert '<span class="pl-saved">✓ Spremljeno</span>' in page

    sentences = {"Neispravan broj.": [{"kg_1": "2,25"}, {"reps_1": "1000"}, {"reps_1": "-1"}, {"kg_1": "501"},
                                      {"reps_1": "1.5"}, {"kg_1": "x"}, {"kg_1": "-0,5"}],
                 "Upiši bar jednu seriju.": [{"reps_1": "", "kg_1": ""}, {"reps_1": "  ", "kg_1": " "}]}
    for sentence, changes in sentences.items():
        for change in changes:
            r = ci.post(f"{d.base}/vjezba/2", data={"rows": "1", "reps_1": "10", "kg_1": "20", **change})
            assert r.status_code == 400 and alert(r.text) == [sentence], change
            assert re.search(r'<h1 class="pl-name" id="pl-name">Goblet čučanj</h1>\s*<div class="alert" role="alert">', r.text)
            kept = {**{"reps_1": "10", "kg_1": "20"}, **change}
            assert inputs(r.text) == [("reps", "1", kept["reps_1"]), ("kg", "1", kept["kg_1"].replace(",", "."))], change
    many = {"rows": "13", **{f"reps_{i}": "5" for i in range(1, 14)}}
    r = ci.post(f"{d.base}/vjezba/2", data=many)
    assert r.status_code == 400 and alert(r.text) == ["Najviše 12 serija."] and len(inputs(r.text)) == 26
    assert db.get_pass(log_id, ivan).done_items[d.items[1]]["sets"][0] == {"reps": 10, "kg": 2.5}   # untouched
    r = ci.post(f"{d.base}/vjezba/3", data={"rows": "2", "sec_1": "3601", "sec_2": ""})
    assert r.status_code == 400 and alert(r.text) == ["Neispravan broj."]
    r = ci.post(f"{d.base}/vjezba/3", data={"rows": "3", "sec_1": "40", "sec_2": "", "sec_3": "35"},
                follow_redirects=False)
    assert r.headers["location"] == f"{d.base}/vjezba/4"
    assert db.get_pass(log_id, ivan).done_items[d.items[2]]["sets"] == [{"seconds": 40}, {"seconds": 35}]

    r = ci.post(f"{d.base}/vjezba/2", data={"rows": "1", "reps_1": "12", "kg_1": "500"}, follow_redirects=False)
    log = db.get_pass(log_id, ivan)                                         # a re-save replaces the entry
    assert r.status_code == 303 and log.done_items[d.items[1]]["sets"] == [{"reps": 12, "kg": 500.0}]
    assert log.done_count == 2
    page = ci.get(f"{d.base}/vjezba/4").text
    assert ">Spremi i završi</button>" in page
    r = ci.post(f"{d.base}/vjezba/4", data={"rows": "1", "reps_1": "1"}, follow_redirects=False)
    assert r.headers["location"] == f"{d.base}/kraj"                       # after the last: the finish screen

    with pytest.raises(ValueError, match="Upiši bar jednu seriju."):
        db.read_sets([{"reps": "", "kg": ""}], False)
    assert db.read_sets([{"reps": "0", "kg": ""}, {"reps": "", "kg": "0,5"}], False) == [
        {"reps": 0, "kg": 0.0}, {"reps": 0, "kg": 0.5}]
    assert db.read_sets([{"seconds": "0"}, {"seconds": "3600"}], True) == [{"seconds": 0}, {"seconds": 3600}]
    for bad in ([{"reps": True, "kg": 0.0}], [{"reps": 1}], [{"reps": 1, "kg": 0.25}], [{"seconds": 1.5}], []):
        with pytest.raises(ValueError):
            db.save_sets(log_id, ivan, item(d, 2), bad, item(d, 2).exercise)


def test_skipping_saves_nothing_and_the_last_leads_to_the_end():
    """"Preskoči →" is a link to the next exercise (nothing saved); the
    last's is "Preskoči i završi", to the finish screen; ‹ › are links to
    the exercises beside it, none before the first nor after the last."""
    trainer, ivan, ana = people()
    d = build_day()
    ci = client_for("ivan@test.local")
    ci.post(f"{d.base}/kreni")
    first = ci.get(f"{d.base}/vjezba/1").text
    assert f'<a class="act act-quiet" href="{d.base}/vjezba/2">Preskoči →</a>' in first
    assert f'href="{d.base}/vjezba/2" rel="next" aria-label="Sljedeća vježba">›</a>' in first and 'rel="prev"' not in first
    middle = ci.get(f"{d.base}/vjezba/2").text
    assert f'href="{d.base}/vjezba/1" rel="prev"' in middle and f'href="{d.base}/vjezba/3" rel="next"' in middle
    last = ci.get(f"{d.base}/vjezba/4").text
    assert f'<a class="act act-quiet" href="{d.base}/kraj">Preskoči i završi</a>' in last and 'rel="next"' not in last
    assert f'<a class="act act-quiet" href="{d.base}">← Natrag</a>' in last
    assert f'<a class="act pl-end" href="{d.base}/kraj">Završi trening</a>' in last
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
    assert "Odmor između serija: 60 s · 16 kg" in rows[1][3]
    assert re.findall(r'<h3 class="dx-cap">([^<]*)</h3>', page) == ["Zagrijavanje", "Trening", "Istezanje"]
    assert '<a class="pl-dock" href="#popis">Vježbe · 2/4 ✓</a>' in page
    assert re.search(r'<span class="pl-timer" hidden data-started="[0-9T:+-]+"', page)
    assert '<span class="pl-chip">2/4</span>' in page and '<p class="pl-dose">3 × 10</p>' in page
    assert '<p class="pl-sub">Odmor između serija: 60 s</p>' in page and '<p class="pl-sub">16 kg</p>' in page
    assert "<summary>Kako se izvodi</summary>" in page and "<strong>Jedno ponavljanje:</strong> Do paralele i natrag." in page
    assert "Kako se izvodi" not in ci.get(f"{d.base}/vjezba/3").text   # Plank: no rep note, no instructions


# ---------- the swap ----------

def test_an_exercise_is_swapped_for_a_similar_one_only():
    """"⇄ Zamijeni vježbu" lists the plan's exercise's similar exercises
    (name, tags, ⇄); one of them swaps in for this pass: the player shows
    its name, clip and cues, "Zamjena za: …" naming the plan's, "Vrati …"
    first in the list, the list's row its name "(zamjena)"; a save names it
    in the entry. Any other exercise is refused ("Ta vježba nije među
    sličnima."), and "vrati" puts the plan's back. Its clip is the client's
    to watch (it is similar to one his programme holds)."""
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
    assert "<summary>⇄ Zamijeni vježbu</summary>" in page
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
    assert '<p class="pl-for">Zamjena za: Goblet čučanj</p>' in page
    assert f'<video src="/media/{clip}" playsinline loop muted autoplay controls preload="metadata"></video>' in page
    assert re.search(r'<input type="hidden" name="vrati" value="1">\s*<button type="submit" class="act">Vrati Goblet čučanj</button>', page)
    assert re.findall(r'<span class="swap-name">([^<]*)', page) == ["Čučanj s vlastitom težinom"]   # the swapped one not offered again
    assert 'Iskorak unatrag <span class="pl-swapped">(zamjena)</span>' in page
    assert '<p class="pl-dose">3 × 10</p>' in page                        # the plan's dose stays
    assert ci.get(f"/media/{clip}").status_code == 200 and ca.get(f"/media/{clip}").status_code == 403

    ci.post(f"{d.base}/vjezba/2", data={"rows": "1", "reps_1": "10", "kg_1": "8"})
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
    assert state_line(page) == "Još nije odrađen." and ">Kreni</button>" in page
    ci.post(f"{d.base}/kreni")
    log_id = stored()[0][0]
    save(ivan, log_id, d, 1, [{"reps": 15, "kg": 0.0}])
    with db.engine.begin() as conn:                                        # it started 38 minutes 10 s ago
        conn.execute(sa_text("UPDATE workout_logs SET started_at = now() - interval '38 minutes 10 seconds'"))
    page = ci.get(f"{d.base}/kraj").text
    assert '<p class="kr-eyebrow">Trening odrađen</p>' in page and "<h1>Dan 1 · Cijelo tijelo</h1>" in page
    assert '<p class="kr-sum">1 od 4 vježbe · 38 min</p>' in page
    assert len(re.findall(r'<input type="radio" name="effort" value="(\d+)" required>', page)) == 10
    assert re.findall(r'<input type="radio" name="feeling" value="(\w+)">', page) == ["slabo", "dobro", "odlicno"]
    assert f'<a class="act act-quiet" href="{d.base}/vjezba/4">Natrag na vježbe</a>' in page
    assert 'data-confirm-title="Odbaciti započeti trening?"' in page and ">Odbaci trening</button>" in page
    page = ci.get(d.base).text
    assert state_line(page) == "U tijeku — nastavi gdje si stao/la." and ">Nastavi</button>" in page
    assert ">Odbaci započeti trening</button>" in page

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
    assert state_line(page) == "Odrađen 1× · zadnji put danas" and ">Kreni</button>" in page
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
    finished(ana, build_day("Gornji", "pocetna", "gornji"), {1: [{"reps": 1, "kg": 0.0}]})
    page = ci.get(d.base).text
    day = (datetime.now(config.TZ) - timedelta(days=2)).date()
    lines = hist_lines(page)
    assert len(lines) == 5 and lines[0] == f"{day.day}.{day.month}. · 3/4 vježbe · 38 min · napor 7 · odlično"
    assert lines[1].endswith("· 1/4 vježbe · 35 min · napor 6") and lines[4].endswith("· 1/4 vježbe · 32 min · napor 3")
    assert '<p class="hist-note">Lakše nego prošli put.</p>' in page
    first = page.split('<li class="card hist-row">')[1]
    assert sets_lines(first) == ["Čučanj s vlastitom težinom: 15 · 15 × 2,5 kg",
                                 "Goblet čučanj: 10 × 20 kg · 8 × 20 kg", "Plank: 40 s · 40 s"]
    assert "<summary>Serije</summary>" in first
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
    cards = re.findall(r'<strong>([^<]*)</strong>\s*<span class="hint">([^<]*)</span>', page)
    assert cards == [("Dan 1 · Cijelo tijelo", "Preporučeno: ponedjeljak · 4 vježbe · odrađen 2×"),
                     ("Dan 2", "0 vježbi"), ("Dan 3", "1 vježba · u tijeku"), ("Dan 4", "1 vježba · nedovršen")]
    assert db.day_states(ivan, [d.did, d2, d3])[d.did]["count"] == 2 and d2 not in db.day_states(ivan, [d2])
    assert re.findall(r'<span class="hint">([^<]*)</span>', client_for("ana@test.local").get(
        f"/treninzi/{build_day('Njen', 'pocetna', 'gornji').pid}").text) == ["Preporučeno: ponedjeljak · 4 vježbe"]


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
    a termin's, the comment. The client's karton has no sets; the
    trainer's view folds them under "Serije". A pass in progress is not
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
    assert '<div class="le-kicker">Online trening</div>' in row
    assert '<div class="hint le-sub">Dan 1 · Cijelo tijelo — Cijelo tijelo — početna</div>' in row
    assert '<div class="hint le-sub">2 od 4 vježbe · 38 min</div>' in row
    assert '<span class="rpe">napor 7/10</span>' in row and '<span class="rpe feel ">Odlično</span>' in row
    assert "<p>Online.</p>" in row and "Serije" not in row
    assert '<div class="hint le-sub">1 od 4 vježbe · 1 h 05 min</div>' in entry(page, b)
    assert '<span class="rpe feel low">Slabo</span>' in entry(page, b)
    assert "Uredi" not in row and "Obriši" not in row and "/delete" not in row   # nothing edits a pass here
    assert page.count('class="log-entry online"') == 2

    page = client_for("trener@test.local").get(f"/karton/{ivan}").text
    row = entry(page, a)
    assert "<summary>Serije</summary>" in row
    assert sets_lines(row) == ["Goblet čučanj: 10 × 20 kg · 8 × 20 kg", "Plank: 40 s"]
    db.delete_day(d.did)                                                   # the day gone: the pass stays
    page = client_for("ivan@test.local").get("/karton").text
    assert '<div class="hint le-sub">2 vježbe · 38 min</div>' in entry(page, a)
    assert '<div class="hint le-sub">Dan 1 · Cijelo tijelo — Cijelo tijelo — početna</div>' in entry(page, a)
    assert db.get_pass(a, ivan).day_id is None


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
        r = ci.post(f"{d.base}/vjezba/{k}", data={"rows": "1", **sets}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == to, k
    assert db.get_pass(log_id, ivan).done_count == 4
    ci.post(f"{d.base}/vjezba/2/zamjena", data={"exercise_id": str(d.ex["Iskorak unatrag"])})
    r = ci.post(f"{d.base}/vjezba/2", data={"rows": "1", "reps_1": "10", "kg_1": "8"}, follow_redirects=False)
    assert r.headers["location"] == f"{d.base}/vjezba/3?odmor=90"          # swapped: the plan's item's rest
    r = ci.post(f"{d.base}/vjezba/3?odmor=90", data={"rows": "1", "sec_1": "x"})
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
    assert re.findall(r'<p class="pl-sub">([^<]*)</p>', page) == ["Odmor između serija: 60 s · Odmor nakon vježbe: 90 s", "16 kg"]
    assert re.findall(r'<p class="pl-sub">([^<]*)</p>', ci.get(f"{d.base}/vjezba/4").text) == ["Odmor nakon vježbe: 120 s"]
    assert re.findall(r'<p class="pl-sub">([^<]*)</p>', ci.get(f"{d.base}/vjezba/3").text) == [
        "Odmor između serija: 0 s"]                                         # worded as set; its timer: none
    subs = re.findall(r'<span class="dx-sub">([^<]*)</span>', page)
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
    assert f'<th scope="col">Pon.</th><th scope="col">Kg</th>{head}' in page
    assert re.findall(r'<td class="pl-tick" hidden><button type="button" class="pl-done" aria-pressed="false" '
                      r'aria-label="Serija (\d+) odrađena">✓</button></td>\s*</tr>', page) == ["1", "2", "3", "4"]
    assert f'<th scope="col">Set</th><th scope="col">Sek.</th>{head}' in ci.get(f"{d.base}/vjezba/3").text
    assert re.search(r'<div class="pl-rest" id="plRest" role="timer" hidden>\s*<span class="pl-rest-n">'
                     r'<span class="pl-rest-h">Odmor</span><span class="pl-rest-t">0:00</span></span>\s*'
                     r'<span class="pl-rest-track" aria-hidden="true"><span class="pl-rest-fill"></span></span>\s*'
                     r'<button type="button" class="pl-rest-skip">Preskoči odmor</button>', page)


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
        assert '<h2 id="leaveTitle">Završiti trening?</h2>' in dlg
        assert re.findall(r'<p class="fb-lead">([^<]*)</p>', dlg) == [leads[mode]]
        assert re.search(r'<p class="fb-note" id="leaveErr"[^>]* hidden>Nije uspjelo — pokušaj ponovno.</p>', dlg)
        assert re.findall(r'<button type="button" class="([^"]+)" id="(leave\w+)"( autofocus)?>([^<]*)</button>', dlg) == [
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
        assert ci.post(f"{d.base}/vjezba/{k}", data={"rows": "1", **sets}, follow_redirects=False).status_code == 303
    started = db.get_pass(log_id, ivan).started_at - timedelta(hours=3)
    age(log_id, 3, saves_at=started + timedelta(minutes=25))
    log = db.get_pass(log_id, ivan)
    assert (log.started_at, log.last_activity, log.stale()) == (started, started + timedelta(minutes=25), True)
    kraj = f"{d.base}/kraj"

    r = ci.get(f"{d.base}/vjezba/3", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == kraj
    r = ci.post(f"{d.base}/vjezba/3", data={"rows": "1", "sec_1": "40"}, follow_redirects=False)
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
    assert ">Nastavi</button>" not in page and f'action="{d.base}/kreni"' not in page
    assert f'<div class="go"><a class="btn" href="{kraj}">Završi trening</a></div>' in page
    assert ">Odbaci započeti trening</button>" in page
    assert page.count('<span class="dx-ok" role="img" aria-label="spremljeno">✓</span>') == 2   # what it saved, ticked
    page = ci.get(f"/treninzi/{d.pid}").text
    assert "4 vježbe · nedovršen</span>" in page and "· u tijeku</span>" not in page

    page = ci.get(kraj).text
    assert '<p class="kr-eyebrow">Nedovršen trening</p>' in page and "Trening odrađen</p>" not in page
    assert '<p class="kr-sum">2 od 4 vježbe · 25 min</p>' in page
    assert (f'<p class="kr-stale">Započet {when} i nije završen — nastavak više nije moguć. '
            f'Spremi osvrt ili trening odbaci.</p>') in page
    assert "Natrag na vježbe" not in page and ">Odbaci trening</button>" in page and 'data-mode="kraj"' in page

    r = ci.post(kraj, data={"effort": "6"}, follow_redirects=False)
    assert location(r) == f"{d.base}?ok=Trening je spremljen."
    log = db.get_pass(log_id, ivan)
    assert not log.in_progress and not log.stale() and (log.effort, log.elapsed_seconds) == (6, 1500)
    assert abs((datetime.now(config.TZ) - log.finished_at).total_seconds()) < 5
    page = ci.get(d.base).text
    assert hist_lines(page)[0] == (f"{began.day}.{began.month}." + (f"{began.year}." if began.year != config.today().year else "")
                                   + " · 2/4 vježbe · 25 min · napor 6")
    assert state_line(page).startswith("Odrađen 1×") and ">Kreni</button>" in page


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
    ci.post(f"{d.base}/vjezba/1", data={"rows": "1", "reps_1": "15"})
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
