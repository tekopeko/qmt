"""Training-programme (treninzi) tests: authorization, ordering, the library
of exercises (/treninzi/vjezbe, 30.10.2026) and, since the same day, the
programmes' days (stage 2 of roadmap/2026-10-29-online-treninzi-spec.md).

The owner (29.-30.10.2026): "We should have a database of exercises which he
can choose from and add them to different training programmes that will be
modular. Each exercise will have a video connected to it which will show the
exercise and show what one rep means." An exercise is a row (`Exercise`:
name, unique whatever its case, instructions, what one rep is, a clip, free
tags, and the similar exercises a client may later swap one for, one row a
pair, read both ways); a programme's days' items point at it, so one held by
a programme cannot be deleted. Amir builds the library on its own pages.

Stage 2 (the owner: "Dan 1, … Dan N with suggested days in the week but the
user can do them whenever he wants"; per exercise "sets × reps, or seconds,
rest between sets, a note"; a day has sections, "warm up and main"): a
programme is a list of days (`ProgramDay`: its place, an optional title, a
suggested weekday, an intro, an intro video), a day its exercises in three
sections (`ProgramDayItem`: zagrijavanje, trening, istezanje; sets, reps or
seconds, rest, a note). Amir builds a day in its editor, picking from the
library; the client opens a programme, sees its days as cards, and a day's
whole list, each exercise's clip opened in place. Migrations 4c2e8a6f1d39
(the items into the library) and 7c3bf996c983 (the items into days) run for
real on qmt_test, there and back. The browser half walks the trainer through
the library and through a day on a phone.
"""

from __future__ import annotations

import importlib.util
import io
import os
import pathlib
import re
import threading
import time
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

from qmt import auth, config, db
from qmt.models import Base, ProgramDay, ProgramDayItem, alpha_key
from qmt.web.app import app

PORT = 8114                      # test_copy's server is 8111, test_raspored_ui's and test_upitnik_ui's 8112, test_nav's 8113

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)  # enough to be a non-empty "image"
# A tiny MP4 as ISO base media starts: its "ftyp" box (24 bytes: size, type,
# major brand, minor version, compatible brands), then an empty "free" box.
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00\x00\x00\x08free"
# A tiny WebM: its EBML header (1A 45 DF A3, a 31-byte body: EBML versions,
# the ID and size lengths, DocType "webm" and its versions).
WEBM = (b"\x1a\x45\xdf\xa3\x9f" + b"\x42\x86\x81\x01" + b"\x42\xf7\x81\x01" + b"\x42\xf2\x81\x04"
        + b"\x42\xf3\x81\x08" + b"\x42\x82\x84webm" + b"\x42\x87\x81\x04" + b"\x42\x85\x81\x02")
UNSUPPORTED = "Nepodržan format — dozvoljeno: mp4, mov, webm."


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # media lands in a throwaway dir, never the real data/uploads — and never
    # the real R2 bucket: a developer's .env may carry live R2_* credentials
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "")
    yield
    # a migration test builds program_items, a table the models no longer
    # have; left behind by a failure, its foreign keys would stop the next
    # module's drop_all
    with db.engine.begin() as conn:
        conn.execute(sa_text("DROP TABLE IF EXISTS program_items CASCADE"))


def make_user(email: str, is_trainer: bool = False, goal: str = "cijelo") -> int:
    from datetime import date

    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)   # login refuses unverified accounts
    db.update_profile(u.id, email.split("@")[0], "Test", date(1990, 1, 1), "")
    if is_trainer:
        db.set_trainer(email)
    else:
        # online treninzi are gated on the `online` plan + a filled upitnik;
        # these tests exercise programme mechanics, so clients get both
        # (the gates have their own tests). An old upitnik (version 1),
        # all-zero answers -> pocetna: its goal is its own, which is what
        # these tests vary (a version-2 response's goal is always cijelo).
        import json

        from qmt import upitnik
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


def trainer_with_clients():
    make_user("trener@test.local", is_trainer=True)
    ivan = make_user("ivan@test.local")                 # pocetna / cijelo
    ana = make_user("ana@test.local", goal="gornji")    # pocetna / gornji
    return client_for("trener@test.local"), ivan, ana


def upload(c: TestClient, eid: int, filename: str, data: bytes, kind: str = "video/mp4"):
    return c.post(f"/treninzi/vjezbe/{eid}/video", files={"video": (filename, io.BytesIO(data), kind)},
                  follow_redirects=False)


def day_upload(c: TestClient, pid: int, did: int, filename: str, data: bytes, kind: str = "video/mp4"):
    return c.post(f"/treninzi/{pid}/dan/{did}/video", files={"video": (filename, io.BytesIO(data), kind)},
                  follow_redirects=False)


def pairs() -> set[tuple[int, int]]:
    """exercise_alternatives as stored: (exercise_id, alternative_id)."""
    with db.engine.connect() as conn:
        return {tuple(r) for r in conn.execute(sa_text("SELECT exercise_id, alternative_id FROM exercise_alternatives"))}


def names(page: str) -> list[str]:
    """The library list's exercises, in order."""
    return [unescape(n) for n in re.findall(r'<span class="ex-name">([^<]*)</span>', page)]


def items_of(pid: int) -> list:
    """A programme's items across its days, each day in its display order
    (its sections in their order, each in position order)."""
    return [it for d in db.get_program(pid).days for rows in d.by_section.values() for it in rows]


def item_names(pid: int) -> list[str]:
    return [it.exercise.name for it in items_of(pid)]


def hold(pid: int, eid: int, section: str = "trening", day: int = 1) -> int:
    """Put an exercise into a programme's Dan `day`, in a section (the days
    made as needed); the item's id."""
    while len(db.get_program(pid).days) < day:
        db.add_day(pid)
    return db.add_day_item(db.get_program(pid).days[day - 1].id, eid, section)


def location(r) -> str:
    """A redirect's location as a person reads it ("+" a space)."""
    return unquote(r.headers["location"]).replace("+", " ")


# ---------- programmes: matching, gates, order ----------

def test_program_visible_only_by_matching_combo():
    ct, ivan, ana = trainer_with_clients()
    r = ct.post("/treninzi", data={"title": "Tjedan 1", "level": "pocetna",
                                   "goal": "cijelo"}, follow_redirects=False)
    assert "/uredi" in r.headers["location"]
    pid = int(r.headers["location"].split("/")[2])

    # matching IS the access: ivan (pocetna/cijelo) sees it automatically...
    ci = client_for("ivan@test.local")
    assert "Tjedan 1" in ci.get("/treninzi").text
    assert ci.get(f"/treninzi/{pid}").status_code == 200
    # ...ana (pocetna/gornji) does not
    ca = client_for("ana@test.local")
    assert "Tjedan 1" not in ca.get("/treninzi").text
    assert ca.get(f"/treninzi/{pid}").status_code == 403

    # re-tagging the combo instantly moves the audience — no hand-outs anywhere
    ct.post(f"/treninzi/{pid}/edit", data={"title": "Tjedan 1", "level": "pocetna",
                                           "goal": "gornji"}, follow_redirects=False)
    assert ca.get(f"/treninzi/{pid}").status_code == 200
    assert ci.get(f"/treninzi/{pid}").status_code == 403

    # a programme with no combo is trainer-only
    bare = db.create_program("Skica", None)
    assert ci.get(f"/treninzi/{bare}").status_code == 403


def test_ensure_online_skeletons_idempotent_and_prefilled():
    """Every (razina × cilj) slot is made once, with Dan 1 of four default
    exercises; reruns add nothing. A slot with a day is Amir's work, even an
    empty day: emptied, it stays empty, and what he puts in it stays his. A
    slot whose every day he deleted has no day, and gets Dan 1 again."""
    from qmt import upitnik

    assert db.ensure_online_skeletons() == len(upitnik.LEVELS) * len(upitnik.GOALS)
    assert db.ensure_online_skeletons() == 0            # second run adds nothing
    rows = [(p, nd, ni) for p, nd, ni in db.all_programs() if p.level]
    combos = {(p.level, p.goal) for p, _, _ in rows}
    assert combos == {(lv, g) for lv in upitnik.LEVELS for g in upitnik.GOALS}
    # every slot ships with its Dan 1 of default exercises — no combo renders empty...
    assert all((nd, ni) == (1, 4) for _, nd, ni in rows)
    counts = {p.id: (nd, ni) for p, nd, ni in rows}
    db.ensure_online_skeletons()                        # ...and reruns never duplicate them
    assert {p.id: (nd, ni) for p, nd, ni in db.all_programs() if p.level} == counts

    pid, other = rows[0][0].id, rows[1][0].id
    for it in items_of(pid):                            # emptied: the day stays, empty
        db.delete_day_item(it.id)
    db.ensure_online_skeletons()
    assert item_names(pid) == [] and len(db.get_program(pid).days) == 1
    hold(pid, db.create_exercise("Trenerova vježba"))
    db.ensure_online_skeletons()
    assert item_names(pid) == ["Trenerova vježba"]
    db.delete_day(db.get_program(other).days[0].id)    # no day at all: filled again
    db.ensure_online_skeletons()
    assert len(db.get_program(other).days) == 1 and len(item_names(other)) == 4


# The nine slots' doses as the items' notes said them until 30.10.2026
# (HEAD's db._DEFAULT_ITEMS, to the character): the structured defaults are
# these, as the days' migration parses them.
OLD_DEFAULT_DOSES = {
    "cijelo": [{"pocetna": "3 × 8 · 8 kg", "srednja": "4 × 10 · 16 kg", "napredna": "4 × 12 · 24 kg"},
               {"pocetna": "3 × 5 (s koljena)", "srednja": "3 × 10", "napredna": "4 × 15"},
               {"pocetna": "3 × 10 · 2 × 6 kg", "srednja": "3 × 12 · 2 × 10 kg", "napredna": "4 × 12 · 2 × 14 kg"},
               {"pocetna": "3 × 20 s", "srednja": "3 × 40 s", "napredna": "3 × 60 s"}],
    "gornji": [{"pocetna": "3 × 8 · 2 × 6 kg", "srednja": "4 × 10 · 2 × 12 kg", "napredna": "4 × 12 · 2 × 18 kg"},
               {"pocetna": "3 × 10 · 2 × 6 kg", "srednja": "4 × 10 · 2 × 12 kg", "napredna": "4 × 12 · 2 × 16 kg"},
               {"pocetna": "3 × 8 · 2 × 4 kg", "srednja": "3 × 10 · 2 × 8 kg", "napredna": "4 × 10 · 2 × 12 kg"},
               {"pocetna": "2 × 10 · 2 × 4 kg", "srednja": "3 × 12 · 2 × 8 kg", "napredna": "3 × 15 · 2 × 10 kg"}],
    "donji": [{"pocetna": "3 × 8 · 8 kg", "srednja": "4 × 10 · 20 kg", "napredna": "4 × 12 · 28 kg"},
              {"pocetna": "3 × 6 po nozi", "srednja": "3 × 10 po nozi · 2 × 8 kg",
               "napredna": "4 × 10 po nozi · 2 × 12 kg"},
              {"pocetna": "3 × 8 · 12 kg", "srednja": "4 × 10 · 24 kg", "napredna": "4 × 10 · 32 kg"},
              {"pocetna": "3 × 12", "srednja": "3 × 15 · 10 kg", "napredna": "4 × 15 · 20 kg"}],
}


def test_ensure_online_skeletons_makes_one_library_row_per_name():
    """The nine slots' default exercises are library rows, one per name,
    reused across the slots (Goblet čučanj in the six of cijelo and donji);
    an exercise of the name Amir made first, in another case, is the one
    they use, his instructions kept; a rerun makes none. Each slot's Dan 1
    (no title, no weekday, no intro) holds them in section trening, each
    with its razina's dose structured, (sets, reps, seconds, note), the
    doses the items' notes said until then, and 60 s of rest; the library's
    instructions are the cues alone, never a dose."""
    mine = db.create_exercise("goblet ČUČANJ", "Moje upute.")
    db.ensure_online_skeletons()
    rows = db.exercises()
    library = [e.name for e, _ in rows]
    assert len(library) == 10 and len({n.casefold() for n in library}) == 10
    assert library == sorted(library, key=alpha_key)
    used = {e.name: n for e, n in rows}
    assert used["goblet ČUČANJ"] == 6 and used["Veslanje u pretklonu"] == 6 and used["Plank"] == 3
    assert db.exercise(mine).instructions == "Moje upute."
    parse = _migration("7c3bf996c983_program_days.py").parse_dose
    for p, nd, ni in db.all_programs():
        want = {"cijelo": ["goblet ČUČANJ", "Sklekovi", "Veslanje u pretklonu", "Plank"],
                "gornji": ["Potisak s bučicama na klupi", "Veslanje u pretklonu", "Potisak iznad glave", "Biceps pregib"],
                "donji": ["goblet ČUČANJ", "Iskorak unatrag", "Rumunjsko mrtvo dizanje", "Glute most"]}[p.goal]
        assert item_names(p.id) == want, p.title
        day = db.get_program(p.id).days[0]
        assert (day.position, day.title, day.weekday, day.intro, day.intro_video, day.label) == (1, "", None, "", None, "Dan 1")
        doses = [(it.sets, it.reps, it.seconds, it.note) for it in day.items]
        assert doses == [parse(old[p.level]) for old in OLD_DEFAULT_DOSES[p.goal]], p.title
        assert {(it.section, it.rest_seconds) for it in day.items} == {("trening", 60)}
    assert db.exercise(next(e.id for e, _ in rows if e.name == "Plank")).instructions == "Lopatice aktivne, gluteusi stisnuti."
    assert not [e.name for e, _ in rows if e.instructions[:1].isdigit()]
    doses = {(p.level, p.goal): [(i.sets, i.reps, i.seconds, i.note) for i in items_of(p.id)]
             for p, _, _ in db.all_programs()}
    assert doses[("pocetna", "cijelo")] == [(3, 8, None, "8 kg"), (3, 5, None, "s koljena"), (3, 10, None, "2 × 6 kg"),
                                            (3, None, 20, "")]
    assert doses[("napredna", "cijelo")] == [(4, 12, None, "24 kg"), (4, 15, None, ""), (4, 12, None, "2 × 14 kg"),
                                             (3, None, 60, "")]
    assert doses[("srednja", "donji")] == [(4, 10, None, "20 kg"), (3, 10, None, "po nozi · 2 × 8 kg"),
                                           (4, 10, None, "24 kg"), (3, 15, None, "10 kg")]
    assert doses[("srednja", "gornji")][1] == (4, 10, None, "2 × 12 kg")          # Veslanje: its dose per cilj too
    pid = next(p.id for p, _, _ in db.all_programs() if (p.level, p.goal) == ("pocetna", "cijelo"))
    assert [(i.dose, i.rest_text) for i in items_of(pid)] == [("3 × 8", "60 s"), ("3 × 5", "60 s"), ("3 × 10", "60 s"),
                                                              ("3 × 20 s", "60 s")]
    db.ensure_online_skeletons()
    assert len(db.exercises()) == 10


def test_a_day_says_its_label_and_an_item_its_dose_and_rest():
    """A day's label is "Dan N", with its title "Dan N · title"; its items
    read section by section in their order, each in position order. An
    item's dose is the list's words: sets × reps, sets × seconds, reps or
    seconds alone, sets alone, nothing; its rest "60 s" or nothing."""
    assert ProgramDay(position=2, title="").label == "Dan 2"
    assert ProgramDay(position=1, title="Cijelo tijelo").label == "Dan 1 · Cijelo tijelo"

    def dose(sets=None, reps=None, seconds=None):
        return ProgramDayItem(sets=sets, reps=reps, seconds=seconds).dose

    assert [dose(3, 10), dose(3, None, 30), dose(None, 10), dose(None, 1), dose(None, 3), dose(None, None, 30),
            dose(3), dose(1), dose(5), dose(21), dose(12), dose()] == [
        "3 × 10", "3 × 30 s", "10 ponavljanja", "1 ponavljanje", "3 ponavljanja", "30 s",
        "3 serije", "1 serija", "5 serija", "21 serija", "12 serija", ""]
    assert [ProgramDayItem(rest_seconds=r).rest_text for r in (60, 0, None)] == ["60 s", "0 s", ""]
    day = ProgramDay(position=1, title="")
    day.items = [ProgramDayItem(position=1, section="trening", note="a"), ProgramDayItem(position=2, section="istezanje", note="b"),
                 ProgramDayItem(position=3, section="zagrijavanje", note="c"), ProgramDayItem(position=4, section="trening", note="d")]
    assert {k: [i.note for i in v] for k, v in day.by_section.items()} == {
        "zagrijavanje": ["c"], "trening": ["a", "d"], "istezanje": ["b"]}
    assert list(day.by_section) == ["zagrijavanje", "trening", "istezanje"]
    assert ProgramDay(position=1, title="").by_section == {"zagrijavanje": [], "trening": [], "istezanje": []}


def test_clients_and_guests_cannot_create_or_edit():
    """Every editor's page and route is staff's: a client 403, nothing
    changed; a guest goes to log in. A client sees his programme's day."""
    ct, ivan, _ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    eid = db.create_exercise("Plank")
    iid = db.add_day_item(did, eid, "trening")
    ci, anon = client_for("ivan@test.local"), TestClient(app)
    day = f"/treninzi/{pid}/dan/{did}"
    for path in (f"/treninzi/{pid}/uredi", f"{day}/uredi"):
        assert ci.get(path).status_code == 403, path
        r = anon.get(path, follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (303, "/login"), path
    posts = [("/treninzi", {"title": "X", "level": "pocetna", "goal": "cijelo"}),
             (f"/treninzi/{pid}/edit", {"title": "X", "level": "pocetna", "goal": "cijelo"}),
             (f"/treninzi/{pid}/delete", {}), (f"/treninzi/{pid}/dani", {}),
             (day, {"title": "X", "weekday": "1"}), (f"{day}/video/ukloni", {}), (f"{day}/pomak", {"smjer": "gore"}),
             (f"{day}/stavke", {"exercise_id": str(eid), "section": "trening"}),
             (f"{day}/stavke/{iid}", {"section": "trening", "sets": "3"}), (f"{day}/stavke/{iid}/pomak", {"smjer": "dolje"}),
             (f"{day}/stavke/{iid}/obrisi", {}), (f"{day}/obrisi", {})]
    for path, data in posts:
        assert ci.post(path, data=data).status_code == 403, path
        r = anon.post(path, data=data, follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (303, "/login"), path
    assert ci.post(f"{day}/video", files={"video": ("u.mp4", io.BytesIO(MP4), "video/mp4")}).status_code == 403
    p = db.get_program(pid)
    assert [(d.id, d.title) for d in p.days] == [(did, "")] and p.title == "T"
    assert [(i.id, i.sets) for i in items_of(pid)] == [(iid, None)] and list(config.MEDIA_DIR.glob("*")) == []
    assert ci.get(day).status_code == 200 and ci.get(f"/treninzi/{pid}").status_code == 200


def test_delete_program_keeps_the_exercises_and_their_clips():
    """A programme deleted takes its days and their items, never the
    library's rows or their clips (other programmes may hold them); its
    days' intro videos go with the days, files too."""
    ct, ivan, _ = trainer_with_clients()
    pid = db.create_program("T", None)
    eid = db.create_exercise("V")
    upload(ct, eid, "v.mp4", MP4)
    hold(pid, eid)
    did = db.get_program(pid).days[0].id
    day_upload(ct, pid, did, "uvod.mp4", MP4)
    name, intro = db.exercise(eid).video, db.get_day(did).intro_video
    assert (config.MEDIA_DIR / intro).is_file()
    r = ct.post(f"/treninzi/{pid}/delete", follow_redirects=False)
    assert location(r) == "/treninzi?ok=Trening je obrisan."
    assert db.get_program(pid) is None and db.get_day(did) is None
    assert db.exercise(eid).video == name and (config.MEDIA_DIR / name).is_file()
    assert not (config.MEDIA_DIR / intro).exists()
    assert ("briše se trening s danima i vježbama; same vježbe i njihovi videi ostaju u bazi vježbi."
            in ct.get(f"/treninzi/{db.create_program('U', None)}/uredi").text)
    assert db.delete_program(pid) is None                                   # gone already


# ---------- the library: pages and access ----------

def test_the_library_pages_are_staffs_only():
    """Guests go to log in, a client gets 403 (as on every trainer page),
    the trainer and the owner (who need not train) get the pages; a POST
    likewise, nothing changed by a refused one."""
    make_user("trener@test.local")                               # the owner (OWNER_EMAIL), no is_trainer
    make_user("coach@test.local", is_trainer=True)
    make_user("ivan@test.local")
    eid = db.create_exercise("Plank", tags="core")
    anon, ci = TestClient(app), client_for("ivan@test.local")
    staff = [client_for("trener@test.local"), client_for("coach@test.local")]
    for path in ("/treninzi/vjezbe", "/treninzi/vjezbe?q=pl", "/treninzi/vjezbe/nova", f"/treninzi/vjezbe/{eid}"):
        r = anon.get(path, follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (303, "/login"), path
        assert ci.get(path).status_code == 403, path
        assert "Nemaš ovlasti za ovu stranicu." in ci.get(path).text
        for c in staff:
            assert c.get(path).status_code == 200, path
    posts = [("/treninzi/vjezbe/nova", {"name": "X"}), (f"/treninzi/vjezbe/{eid}", {"name": "Y"}),
             (f"/treninzi/vjezbe/{eid}/video/ukloni", {}), (f"/treninzi/vjezbe/{eid}/obrisi", {})]
    for path, data in posts:
        r = anon.post(path, data=data, follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (303, "/login"), path
        assert ci.post(path, data=data).status_code == 403, path
    assert ci.post(f"/treninzi/vjezbe/{eid}/video", files={"video": ("p.mp4", io.BytesIO(MP4), "video/mp4")}).status_code == 403
    assert [(e.name, e.tags, e.video) for e, _ in db.exercises()] == [("Plank", "core", None)]
    assert staff[0].get("/treninzi/vjezbe/987654").status_code == 404


def test_the_library_creates_saves_and_refuses_a_name_taken():
    """"+ Nova vježba" makes a row (the name trimmed, its spaces single) and
    leads to its page; a name taken whatever its case is refused with "Vježba
    s tim imenom već postoji.", what was typed kept in the form; a save of
    another exercise under a taken name likewise, its own in another case
    passes. An empty or too long name is refused too."""
    ct, *_ = trainer_with_clients()
    r = ct.post("/treninzi/vjezbe/nova", data={"name": "  Goblet   čučanj ", "instructions": "  Pete na podu.  \n\n\n\nTrup  uspravan.",
                                               "rep_note": "Do paralele.", "tags": " noge ,bučice,, "}, follow_redirects=False)
    eid = db.exercises()[0][0].id
    assert r.status_code == 303 and unquote(r.headers["location"]) == f"/treninzi/vjezbe/{eid}?ok=Vježba je spremljena — dodaj joj video."
    e = db.exercise(eid)
    assert (e.name, e.instructions, e.rep_note, e.tags, e.video) == (
        "Goblet čučanj", "Pete na podu.\n\nTrup uspravan.", "Do paralele.", "noge, bučice", None)
    page = ct.get(f"/treninzi/vjezbe/{eid}").text
    assert '<h1>Goblet čučanj</h1>' in page and 'value="Goblet čučanj"' in page and ">Do paralele.</textarea>" in page
    assert 'value="noge, bučice"' in page and "Još nije ni u jednom programu." in page

    r = ct.post("/treninzi/vjezbe/nova", data={"name": "GOBLET ČUČANJ", "instructions": "Drugi tekst."})
    assert r.status_code == 400 and "Vježba s tim imenom već postoji." in r.text
    assert 'value="GOBLET ČUČANJ"' in r.text and ">Drugi tekst.</textarea>" in r.text       # what was typed, kept
    assert len(db.exercises()) == 1
    other = db.create_exercise("Plank")
    r = ct.post(f"/treninzi/vjezbe/{other}", data={"name": "goblet čučanj", "tags": "core"})
    assert r.status_code == 400 and "Vježba s tim imenom već postoji." in r.text and 'value="core"' in r.text
    assert db.exercise(other).name == "Plank"
    r = ct.post(f"/treninzi/vjezbe/{eid}", data={"name": "GOBLET čučanj", "instructions": "Novo.", "rep_note": "", "tags": ""},
                follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/treninzi/vjezbe/{eid}?ok=Spremljeno."
    assert (db.exercise(eid).name, db.exercise(eid).instructions, db.exercise(eid).tags) == ("GOBLET čučanj", "Novo.", "")
    for bad, sentence in (("   ", "Naziv je obavezan."), ("x" * 161, "Naziv može imati najviše 160 znakova.")):
        with pytest.raises(ValueError, match=sentence):
            db.create_exercise(bad)
        assert sentence in ct.post("/treninzi/vjezbe/nova", data={"name": bad}).text
    assert db.create_exercise("x" * 160) and len(db.exercises()) == 3
    assert ct.post("/treninzi/vjezbe/987654", data={"name": "Nova"}).status_code == 404


def test_a_name_is_taken_once_when_saves_race():
    """Eight saves of one name at once, in eight cases (Č and Ć among them,
    which the test database's C locale does not fold: its lower(name) index
    lets them all through): the table's lock makes the casefolded check
    whole, so one is made and seven are refused with the sentence."""
    spellings = ["Čučanj", "ČUČANJ", "čučanj", "čuČanj", "ČuČaNj", "čUčAnJ", "Čučanj ", " čučanj"]
    made, refused = [], []

    def save(name: str) -> None:
        try:
            made.append(db.create_exercise(name))
        except ValueError as err:
            refused.append(str(err))

    threads = [threading.Thread(target=save, args=(n,)) for n in spellings]
    for th in threads: th.start()
    for th in threads: th.join()
    assert len(made) == 1 and refused == ["Vježba s tim imenom već postoji."] * 7
    assert [e.name for e, _ in db.exercises()] == [db.exercise(made[0]).name]


def test_tags_are_stored_cleaned_and_shown_as_chips():
    assert db.clean_tags("  noge ,bučice,, kod   kuće , ") == "noge, bučice, kod kuće"
    assert db.clean_tags(" , ,") == "" and db.clean_tags("") == ""
    ct, *_ = trainer_with_clients()
    ct.post("/treninzi/vjezbe/nova", data={"name": "Iskorak", "tags": "noge,, kod  kuće,bučice "})
    e = db.exercises()[0][0]
    assert e.tags == "noge, kod kuće, bučice" and e.tag_items == ["noge", "kod kuće", "bučice"]
    row = ct.get("/treninzi/vjezbe").text.split('class="ex-row"')[1].split("</a>")[0]
    assert re.findall(r'<span class="ex-tag">([^<]*)</span>', row) == ["noge", "kod kuće", "bučice"]


def test_similar_exercises_read_both_ways_and_go_from_either_side():
    """Ticked on A's form, B is stored once, (A, B), and read both ways: B's
    page has A ticked. Unticked on B's form the pair goes, though B's side
    never stored it; ticked there again it is stored from B's side, (B, A),
    and A's form unticking B removes that row. Its own id, an unknown one
    and a pair held already store nothing; a deleted exercise takes its
    pairs."""
    ct, *_ = trainer_with_clients()
    a, b, c = (db.create_exercise(n) for n in ("Goblet čučanj", "Iskorak", "Čučanj s vlastitom težinom"))

    def save(eid: int, name: str, *ticked: int):
        r = ct.post(f"/treninzi/vjezbe/{eid}", data={"name": name, "alternative": [str(t) for t in ticked]},
                    follow_redirects=False)
        assert r.status_code == 303, r.text

    def similar(eid: int) -> list[str]:
        return [x.name for x in db.exercise(eid).alternatives]

    save(a, "Goblet čučanj", b, c)
    assert pairs() == {(a, b), (a, c)}
    assert similar(a) == ["Čučanj s vlastitom težinom", "Iskorak"] and similar(b) == ["Goblet čučanj"] == similar(c)
    page = ct.get(f"/treninzi/vjezbe/{b}").text
    assert re.search(rf'<input type="checkbox" name="alternative" value="{a}" checked>', page)
    assert re.search(rf'<input type="checkbox" name="alternative" value="{c}">', page)
    assert f'value="{b}"' not in page.split('id="altList"')[1].split("</fieldset>")[0]   # never itself
    save(b, "Iskorak")                                                # unticked on the other side
    assert pairs() == {(a, c)} and similar(a) == ["Čučanj s vlastitom težinom"] and similar(b) == []
    save(b, "Iskorak", a)                                             # stored from B's side now
    assert pairs() == {(a, c), (b, a)} and similar(a) == ["Čučanj s vlastitom težinom", "Iskorak"]
    save(a, "Goblet čučanj", c)                                       # A's form removes B's row
    assert pairs() == {(a, c)}
    save(a, "Goblet čučanj", a, c, 987654)
    save(c, "Čučanj s vlastitom težinom", a)                          # held already (from A's side)
    assert pairs() == {(a, c)}
    db.delete_exercise(c)
    assert pairs() == set() and similar(a) == []


def test_the_form_lists_the_ticked_similar_exercises_first():
    """Every other exercise is a checkbox row, the ticked ones first, each
    group in the alphabet's order (Č after C, before D), with its tags; the
    filter box is there for the script to show."""
    ct, *_ = trainer_with_clients()
    ids = {n: db.create_exercise(n, tags=t) for n, t in (("Plank", "core"), ("Čučanj", "noge"), ("Cirkus", ""),
                                                         ("Dizanje", ""), ("Zaklon", ""))}
    db.update_exercise(ids["Plank"], "Plank", "", "", "core", {ids["Zaklon"], ids["Dizanje"]})
    page = ct.get(f"/treninzi/vjezbe/{ids['Plank']}").text
    rows = re.findall(r'<label data-find="([^"]*)"><input type="checkbox" name="alternative" value="(\d+)"( checked)?>', page)
    assert [(int(v), bool(on)) for _, v, on in rows] == [(ids["Dizanje"], True), (ids["Zaklon"], True), (ids["Cirkus"], False),
                                                         (ids["Čučanj"], False)]
    assert [unescape(f) for f, _, _ in rows][3] == "čučanj noge"
    assert 'id="altFilter"' in page and "hidden>" in page.split('id="altFilter"')[1][:120]


def test_an_exercise_a_programme_holds_is_not_deleted():
    """Deleting is refused while any programme holds the exercise in any of
    its days, the sentence naming them (up to three, in the alphabet's
    order, then "…"; one programme, held in two of its days, is one), on
    the page's alert too; once out of them all it goes, and its clip with
    it."""
    ct, *_ = trainer_with_clients()
    eid = db.create_exercise("Goblet čučanj")
    upload(ct, eid, "g.mp4", MP4)
    clip = db.exercise(eid).video
    progs = {t: db.create_program(t, None) for t in ("Donji dio tijela — srednja", "Core control", "Cijelo tijelo — početna",
                                                     "Zadnji")}
    held = [hold(progs["Core control"], eid), hold(progs["Core control"], eid, "zagrijavanje", day=2)]
    with pytest.raises(ValueError) as refused:
        db.delete_exercise(eid)
    assert str(refused.value) == "Vježba je u 1 programu (Core control) — prvo je makni iz njega."
    assert [p.title for p in db.exercise_programs(eid)] == ["Core control"]
    held.append(hold(progs["Donji dio tijela — srednja"], eid))
    with pytest.raises(ValueError) as refused:
        db.delete_exercise(eid)
    assert str(refused.value) == "Vježba je u 2 programa (Core control, Donji dio tijela — srednja) — prvo je makni iz njih."
    held += [hold(progs["Cijelo tijelo — početna"], eid, "istezanje"), hold(progs["Zadnji"], eid)]
    r = ct.post(f"/treninzi/vjezbe/{eid}/obrisi", follow_redirects=False)
    sentence = "Vježba je u 4 programa (Cijelo tijelo — početna, Core control, Donji dio tijela — srednja …) — prvo je makni iz njih."
    assert r.status_code == 303 and location(r) == f"/treninzi/vjezbe/{eid}?error={sentence}"
    page = ct.get(r.headers["location"]).text
    assert f'<div class="alert" role="alert"><span>{sentence}</span></div>' in unescape(page)
    assert ('<p class="hint">U 4 programa: Cijelo tijelo — početna, Core control, Donji dio tijela — srednja, Zadnji.</p>'
            in page)
    assert db.exercise(eid) is not None and (config.MEDIA_DIR / clip).is_file()
    for item_id in held:
        db.delete_day_item(item_id)
    r = ct.post(f"/treninzi/vjezbe/{eid}/obrisi", follow_redirects=False)
    assert location(r) == "/treninzi/vjezbe?ok=Vježba je obrisana."
    assert db.exercise(eid) is None and not (config.MEDIA_DIR / clip).exists()
    assert db.delete_exercise(eid) is None                                  # gone already: nothing to do


# ---------- the library: the clip ----------

def test_a_clip_is_stored_replaced_and_removed(monkeypatch):
    """An MP4 (ISO base media: "ftyp" at byte 4) is stored under a new name
    and plays on the page (muted, looped, inline); a WebM (EBML) replaces it
    and the old file goes; a file whose extension or first bytes are not a
    clip's is refused with the sentence, as is one over VIDEO_MAX_MB, the
    clip and the files as they were; "Ukloni video" deletes it."""
    ct, *_ = trainer_with_clients()
    eid = db.create_exercise("Plank")
    if "VIDEO_MAX_MB" not in os.environ:
        assert config.VIDEO_MAX_MB == 95         # Cloudflare's free plan stops a body over 100 MB: room for the multipart
    cap = config.VIDEO_MAX_MB
    page = ct.get(f"/treninzi/vjezbe/{eid}").text
    assert f"Video (mp4, mov ili webm, do {cap} MB)" in page and ">Dodaj video</button>" in page and "<video" not in page
    assert ("Snimi na mobitelu uspravno, 10–30 s, jedno ponavljanje jasno. iPhone: Postavke → Kamera → Formati → "
            "„Najkompatibilnije”, inače Chrome na Androidu i Windowsu ne može reproducirati snimku.") in page

    r = upload(ct, eid, "plank.MP4", MP4)
    assert r.status_code == 303 and unquote(r.headers["location"]) == f"/treninzi/vjezbe/{eid}?ok=Video je spremljen."
    first = db.exercise(eid).video
    assert re.fullmatch(rf"vjezba-{eid}-[0-9a-f]{{16}}\.mp4", first) and (config.MEDIA_DIR / first).read_bytes() == MP4
    page = ct.get(f"/treninzi/vjezbe/{eid}").text
    assert f'<video src="/media/{first}" controls playsinline muted loop preload="metadata"></video>' in page
    assert f"Zamijeni video (mp4, mov ili webm, do {cap} MB)" in page and ">Zamijeni video</button>" in page
    assert 'form="ex-video-x" class="btn-ghost btn-sm">Ukloni video</button>' in page
    assert re.search(r'<form id="ex-video-x" method="post" action="/treninzi/vjezbe/\d+/video/ukloni"\s+data-confirm-title=', page)
    served = ct.get(f"/media/{first}")
    assert served.status_code == 200 and served.headers["content-type"] == "video/mp4" and served.content == MP4

    upload(ct, eid, "plank.webm", WEBM, "video/webm")
    second = db.exercise(eid).video
    assert second.endswith(".webm") and (config.MEDIA_DIR / second).read_bytes() == WEBM
    assert not (config.MEDIA_DIR / first).exists()                         # replaced: the old file goes
    assert ct.get(f"/media/{second}").headers["content-type"] == "video/webm"
    assert ct.get(f"/media/{first}").status_code == 404

    for filename, data in (("plank.avi", MP4), ("plank.mp4", PNG), ("plank.webm", MP4), ("plank.mov", WEBM),
                           ("plank", MP4), ("plank.mp4", b"\x00\x00")):
        r = upload(ct, eid, filename, data)
        assert unquote(r.headers["location"]) == f"/treninzi/vjezbe/{eid}?error={UNSUPPORTED}", filename
    monkeypatch.setattr(config, "VIDEO_MAX_MB", 1)
    r = upload(ct, eid, "big.mp4", MP4 + b"\x00" * (1024 * 1024))
    assert unquote(r.headers["location"]) == f"/treninzi/vjezbe/{eid}?error=Video je prevelik — najviše 1 MB."
    assert '<div class="alert" role="alert"><span>Video je prevelik — najviše 1 MB.</span></div>' in ct.get(r.headers["location"]).text
    r = upload(ct, eid, "", b"")                                            # no file chosen
    assert unquote(r.headers["location"]) == f"/treninzi/vjezbe/{eid}?error=Odaberi video."
    assert db.exercise(eid).video == second and sorted(p.name for p in config.MEDIA_DIR.iterdir()) == [second]
    monkeypatch.setattr(config, "VIDEO_MAX_MB", cap)

    mov = MP4.replace(b"isom", b"qt  ", 1)                                  # a QuickTime .mov is ISO base media too
    upload(ct, eid, "plank.mov", mov, "video/quicktime")
    third = db.exercise(eid).video
    assert third.endswith(".mov") and ct.get(f"/media/{third}").headers["content-type"] == "video/quicktime"

    r = ct.post(f"/treninzi/vjezbe/{eid}/video/ukloni", follow_redirects=False)
    assert r.status_code == 303 and unquote(r.headers["location"]).replace("+", " ") == f"/treninzi/vjezbe/{eid}?ok=Video je uklonjen."
    assert db.exercise(eid).video is None and list(config.MEDIA_DIR.iterdir()) == []
    assert "<video" not in ct.get(f"/treninzi/vjezbe/{eid}").text
    assert upload(ct, 987654, "x.mp4", MP4).status_code == 404 and list(config.MEDIA_DIR.iterdir()) == []


def test_a_clip_is_watched_by_staff_and_matched_clients_only():
    """/media serves a clip to the trainer and the owner whatever holds it,
    to a client only through a programme matched to him, a day of it
    holding the exercise (his online plan running); a guest goes to log in;
    a name no exercise holds is 404, a path never reaches storage."""
    ct, ivan, ana = trainer_with_clients()
    eid = db.create_exercise("Čučanj")
    upload(ct, eid, "c.mp4", MP4)
    name = db.exercise(eid).video
    ci, ca = client_for("ivan@test.local"), client_for("ana@test.local")
    assert ct.get(f"/media/{name}").status_code == 200
    assert ci.get(f"/media/{name}").status_code == 403                     # in no programme yet
    assert db.video_programs(name) == []
    pid = db.create_program("S videom", None, "pocetna", "cijelo")          # ivan's combo
    hold(pid, eid, "istezanje", day=2)
    assert [p.id for p in db.video_programs(name)] == [pid]
    assert ci.get(f"/media/{name}").status_code == 200 and ci.get(f"/media/{name}").content == MP4
    assert ca.get(f"/media/{name}").status_code == 403
    anon = TestClient(app).get(f"/media/{name}", follow_redirects=False)
    assert anon.status_code == 303 and "/login" in anon.headers["location"]
    assert ct.get("/media/vjezba-1-0000000000000000.mp4").status_code == 404
    assert ct.get("/media/..%2f..%2fetc%2fpasswd").status_code == 404
    assert db.video_programs("vjezba-1-0000000000000000.mp4") is None


# ---------- the library: the list and its search ----------

def test_the_list_and_its_search():
    """The list: every exercise in the alphabet's order, its tags as chips,
    "video ✓" / "bez videa", "u N programa" (one: "u 1 programu", none: "ni
    u jednom programu"; through the programmes' days). ?q= keeps those
    whose name or tags hold it, whatever its case; blank shows all; none
    matching says so. An empty library says "Još nema vježbi." with the
    button."""
    ct, *_ = trainer_with_clients()
    page = ct.get("/treninzi/vjezbe").text
    assert "<h1>Vježbe</h1>" in page and "Još nema vježbi." in page and 'href="/treninzi/vjezbe/nova">+ Nova vježba</a>' in page
    assert ('<p class="hint">Baza vježbi: svaki trening slaže se od njih. Vježba ima upute, što je jedno ponavljanje, '
            'oznake i video.</p>') in page
    ids = {n: db.create_exercise(n, tags=t) for n, t in (("Plank", "core, kod kuće"), ("Goblet čučanj", "noge, bučice"),
                                                         ("Čučanj s vlastitom težinom", "noge, kod kuće"), ("Biceps pregib", ""))}
    upload(ct, ids["Plank"], "p.webm", WEBM, "video/webm")
    for t in ("A", "B"):
        hold(db.create_program(t, None), ids["Goblet čučanj"])
    a = db.get_program(db.exercise_programs(ids["Goblet čučanj"])[0].id)
    hold(a.id, ids["Goblet čučanj"], "zagrijavanje", day=2)                # a second day of A: still 2 programmes
    hold(db.create_program("C", None), ids["Plank"])
    page = ct.get("/treninzi/vjezbe").text
    assert names(page) == ["Biceps pregib", "Čučanj s vlastitom težinom", "Goblet čučanj", "Plank"]
    assert "Još nema vježbi." not in page and 'role="search"' in page and 'name="q" value=""' in page
    rows = {names(r)[0]: r for r in page.split('<a class="ex-row" ')[1:]}
    assert f'href="/treninzi/vjezbe/{ids["Plank"]}"' in rows["Plank"] and '<span class="has">video ✓</span>' in rows["Plank"]
    assert "<span>bez videa</span>" in rows["Goblet čučanj"] and "<span>u 2 programa</span>" in rows["Goblet čučanj"]
    assert "<span>u 1 programu</span>" in rows["Plank"] and "<span>ni u jednom programu</span>" in rows["Biceps pregib"]
    assert 'class="ex-tag"' not in rows["Biceps pregib"]
    assert names(ct.get("/treninzi/vjezbe?q=ČUČANJ").text) == ["Čučanj s vlastitom težinom", "Goblet čučanj"]
    found = ct.get("/treninzi/vjezbe?q=Kod+kuće").text
    assert names(found) == ["Čučanj s vlastitom težinom", "Plank"] and "2 od 4" in found and 'value="Kod kuće"' in found
    assert names(ct.get("/treninzi/vjezbe?q=+++").text) == names(page)
    none = ct.get("/treninzi/vjezbe?q=xyz").text
    assert names(none) == [] and "Nijedna vježba ne odgovara traženju „xyz”." in none and "0 od 4" in none
    assert [e.name for e, _ in db.exercises("BUČ")] == ["Goblet čučanj"]


# ---------- a programme's days (stage 2) ----------

def test_days_are_added_saved_moved_and_deleted():
    """"+ Dodaj dan" makes a day after the last (Dan 1, 2, 3) and opens its
    editor. Its form saves a title (one line, its spaces single), a
    suggested weekday ("" none, "0"–"6") and an intro (its line breaks
    kept); a weekday that is none or a title past 160 is refused with the
    sentence. ↑ / ↓ swap two days, their numbers with them (the deferred
    constraint sees the swap whole), nothing at an end; ✕ takes the day and
    its items, the later days moving up, the exercises staying in the
    library."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    made = []
    for _ in range(3):
        r = ct.post(f"/treninzi/{pid}/dani", follow_redirects=False)
        made.append(int(re.fullmatch(rf"/treninzi/{pid}/dan/(\d+)/uredi", r.headers["location"]).group(1)))
    d1, d2, d3 = made
    assert [(d.id, d.position, d.label) for d in db.get_program(pid).days] == [(d1, 1, "Dan 1"), (d2, 2, "Dan 2"), (d3, 3, "Dan 3")]
    assert ct.post("/treninzi/987654/dani").status_code == 404

    edit = f"/treninzi/{pid}/dan/{d2}/uredi"
    r = ct.post(f"/treninzi/{pid}/dan/{d2}", data={"title": "  Gornji   dio ", "weekday": "3",
                                                    "intro": "  Lagano.\n\n\n\nPolako.  "}, follow_redirects=False)
    assert location(r) == f"{edit}?ok=Spremljeno."
    day = db.get_day(d2)
    assert (day.title, day.weekday, day.intro, day.label) == ("Gornji dio", 3, "Lagano.\n\nPolako.", "Dan 2 · Gornji dio")
    page = ct.get(edit).text
    assert 'value="Gornji dio"' in page and '<option value="3" selected>Četvrtak</option>' in page
    assert '<option value="">Bez preporuke</option>' in page and ">Lagano.\n\nPolako.</textarea>" in page
    ct.post(f"/treninzi/{pid}/dan/{d2}", data={"title": "Gornji dio", "weekday": "", "intro": ""})
    assert db.get_day(d2).weekday is None
    assert '<option value="" selected>Bez preporuke</option>' in ct.get(edit).text
    for bad in ("7", "-1", "x", "1.0", " 3"):
        r = ct.post(f"/treninzi/{pid}/dan/{d2}", data={"title": "Novo", "weekday": bad}, follow_redirects=False)
        assert location(r) == f"{edit}?error=Odaberi dan u tjednu.", bad
    r = ct.post(f"/treninzi/{pid}/dan/{d2}", data={"title": "x" * 161}, follow_redirects=False)
    assert location(r) == f"{edit}?error=Naslov može imati najviše 160 znakova."
    assert db.get_day(d2).title == "Gornji dio"

    r = ct.post(f"/treninzi/{pid}/dan/{d3}/pomak", data={"smjer": "gore"}, follow_redirects=False)
    assert r.headers["location"] == f"/treninzi/{pid}/uredi#dan-{d3}"
    assert [(d.id, d.position) for d in db.get_program(pid).days] == [(d1, 1), (d3, 2), (d2, 3)]
    assert db.get_day(d2).label == "Dan 3 · Gornji dio"
    assert not db.move_day(d1, "gore") and not db.move_day(d2, "dolje") and not db.move_day(d1, "x")
    assert not db.move_day(987654, "gore")
    assert db.move_day(d1, "dolje")
    assert [d.id for d in db.get_program(pid).days] == [d3, d1, d2]

    eid = db.create_exercise("Plank")
    db.add_day_item(d1, eid, "trening")
    r = ct.post(f"/treninzi/{pid}/dan/{d1}/obrisi", follow_redirects=False)
    assert location(r) == f"/treninzi/{pid}/uredi?ok=Dan je obrisan."
    assert [(d.id, d.position) for d in db.get_program(pid).days] == [(d3, 1), (d2, 2)]
    assert db.get_day(d1) is None and db.exercise(eid) is not None and db.exercises()[0][1] == 0
    assert db.delete_day(d1) is None                                        # gone already


def test_days_are_numbered_once_when_adds_race():
    """Eight "+ Dodaj dan" at once: the programme's row is locked while the
    next number is read, so the eight days are Dan 1 … Dan 8."""
    pid = db.create_program("T", None)
    made: list[int | None] = []
    threads = [threading.Thread(target=lambda: made.append(db.add_day(pid))) for _ in range(8)]
    for th in threads: th.start()
    for th in threads: th.join()
    assert None not in made and len(made) == 8
    assert [d.position for d in db.get_program(pid).days] == list(range(1, 9))


def test_items_go_into_a_section_and_say_what_the_day_asks():
    """An exercise goes last into the chosen section and the editor comes
    back at its row; a choice that is no exercise, or a section that is
    none, adds nothing ("Odaberi vježbu iz baze."). A row's form saves the
    section, sets, reps or seconds, rest and the note (stripped); an empty
    number is none. Refused with the sentence, the row unchanged: a number
    out of range or not a number ("Neispravan broj."), reps and seconds
    both, a note past 500. Moved to another section, it goes last in it;
    ↑ / ↓ move it within its section only; ✕ takes it out of the day, the
    library keeps the exercise."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    a, b, c, d = (db.create_exercise(n) for n in ("Goblet čučanj", "Čučanj s vlastitom težinom", "Plank", "Istezanje"))
    base = f"/treninzi/{pid}/dan/{did}"
    made = {}
    for eid, section in ((a, "trening"), (b, "zagrijavanje"), (c, "trening"), (d, "istezanje")):
        r = ct.post(f"{base}/stavke", data={"exercise_id": str(eid), "section": section}, follow_redirects=False)
        made[eid] = int(re.fullmatch(rf"{base}/uredi#stavka-(\d+)", r.headers["location"]).group(1))
    ia, ib, ic, id_ = (made[x] for x in (a, b, c, d))

    def layout():
        return {k: [i.id for i in v] for k, v in db.get_day(did).by_section.items()}

    assert layout() == {"zagrijavanje": [ib], "trening": [ia, ic], "istezanje": [id_]}
    assert [i.position for i in db.get_day(did).items] == [1, 2, 3, 4]
    assert [(i.sets, i.reps, i.seconds, i.rest_seconds, i.note) for i in db.get_day(did).items] == [(None, None, None, None, "")] * 4
    for bad, section in (("", "trening"), ("abc", "trening"), ("²", "trening"), ("987654", "trening"),
                         ("99999999999", "trening"), (str(a), "kardio")):
        r = ct.post(f"{base}/stavke", data={"exercise_id": bad, "section": section}, follow_redirects=False)
        assert location(r) == f"{base}/uredi?error=Odaberi vježbu iz baze.", (bad, section)
    assert len(db.get_day(did).items) == 4
    assert ct.post(f"/treninzi/{pid}/dan/987654/stavke", data={"exercise_id": str(a)}).status_code == 404

    def save(item_id, **fields):
        data = {"section": "trening", "sets": "", "reps": "", "seconds": "", "rest": "", "note": ""} | fields
        return ct.post(f"{base}/stavke/{item_id}", data=data, follow_redirects=False)

    def stored(item_id):
        i = db.get_day_item(item_id)
        return i.section, i.sets, i.reps, i.seconds, i.rest_seconds, i.note

    r = save(ia, sets="3", reps="10", rest="60", note="  8 kg  ")
    assert location(r) == f"{base}/uredi?ok=Spremljeno.&stavka={ia}#stavka-{ia}"
    assert stored(ia) == ("trening", 3, 10, None, 60, "8 kg")
    # the word stands in the row (the page comes back scrolled to it), not at the top
    page = ct.get(f"{base}/uredi?ok=Spremljeno.&stavka={ia}").text
    assert page.count('<div class="alert ok') == 1
    assert '<div class="alert ok st-alert" role="status">Spremljeno.</div>' in page.split(f'id="stavka-{ia}"')[1].split("</form>")[0]
    page = ct.get(f"{base}/uredi?error=Neispravan+broj.&stavka={ia}").text
    assert page.count('<div class="alert') == 1
    assert '<div class="alert st-alert" role="alert"><span>Neispravan broj.</span></div>' in page.split(f'id="stavka-{ia}"')[1].split("</form>")[0]
    page = ct.get(f"{base}/uredi?error=Neispravan+broj.&stavka=987654").text    # no such row: the top, as usual
    assert page.count('<div class="alert') == 1 and 'class="alert st-alert"' not in page and 'class="alert" role="alert"' in page
    save(ic, sets=" 3 ", seconds="40", rest="0")
    assert stored(ic) == ("trening", 3, None, 40, 0, "")
    save(ic, seconds="30")                                                  # emptied numbers are none
    assert stored(ic) == ("trening", None, None, 30, None, "")
    save(ic, sets="99", reps="999", rest="3600", note="x" * 500)
    assert stored(ic) == ("trening", 99, 999, None, 3600, "x" * 500)
    save(ic, sets="1", seconds="3600")
    assert stored(ic)[:4] == ("trening", 1, None, 3600)
    before = stored(ia)
    refusals = [({"sets": "0"}, "Neispravan broj."), ({"sets": "100"}, "Neispravan broj."), ({"sets": "abc"}, "Neispravan broj."),
                ({"sets": "-1"}, "Neispravan broj."), ({"sets": "3.5"}, "Neispravan broj."), ({"sets": "²"}, "Neispravan broj."),
                ({"reps": "0"}, "Neispravan broj."), ({"reps": "1000"}, "Neispravan broj."),
                ({"seconds": "0"}, "Neispravan broj."), ({"seconds": "3601"}, "Neispravan broj."),
                ({"rest": "3601"}, "Neispravan broj."), ({"rest": "-5"}, "Neispravan broj."),
                ({"sets": "3", "reps": "10", "seconds": "30"}, "Upiši ponavljanja ili sekunde, ne oboje."),
                ({"note": "x" * 501}, "Napomena može imati najviše 500 znakova."),
                ({"section": "kardio"}, "Odaberi dio dana.")]
    for fields, sentence in refusals:
        r = save(ia, **fields)
        assert location(r) == f"{base}/uredi?error={sentence}&stavka={ia}#stavka-{ia}", fields
    assert stored(ia) == before
    assert ct.post(f"{base}/stavke/987654", data={"sets": "3"}).status_code == 404

    save(ia, section="zagrijavanje", sets="2", reps="15", rest="30")       # another section: last in it
    assert layout() == {"zagrijavanje": [ib, ia], "trening": [ic], "istezanje": [id_]}
    assert db.get_day_item(ia).position == 5
    r = ct.post(f"{base}/stavke/{ia}/pomak", data={"smjer": "gore"}, follow_redirects=False)
    assert r.headers["location"] == f"{base}/uredi#stavka-{ia}"
    assert layout()["zagrijavanje"] == [ia, ib]
    for item_id, smjer in ((ia, "gore"), (ib, "dolje"), (ic, "gore"), (ic, "dolje"), (id_, "gore"), (ia, "x")):
        assert not db.move_day_item(item_id, smjer), (item_id, smjer)      # never out of its section
    assert layout() == {"zagrijavanje": [ia, ib], "trening": [ic], "istezanje": [id_]}
    assert not db.move_day_item(987654, "gore")

    r = ct.post(f"{base}/stavke/{ic}/obrisi", follow_redirects=False)
    assert r.headers["location"] == f"{base}/uredi"
    assert layout() == {"zagrijavanje": [ia, ib], "trening": [], "istezanje": [id_]}
    assert db.exercise(c) is not None and not db.delete_day_item(ic)


def test_a_foreign_day_or_item_is_404():
    """A day under another programme's address, an item under another day's,
    and ids that are none: 404 on every page and route, nothing changed. A
    client's day of a programme not his is 403, as the programme is."""
    ct, ivan, ana = trainer_with_clients()
    a, b = db.create_program("A", None, "pocetna", "cijelo"), db.create_program("B", None, "pocetna", "cijelo")
    da, db_ = db.add_day(a), db.add_day(b)
    eid = db.create_exercise("Plank")
    ia = db.add_day_item(da, eid, "trening")
    foreign = f"/treninzi/{b}/dan/{da}"
    assert ct.get(foreign).status_code == 404 and ct.get(f"{foreign}/uredi").status_code == 404
    assert client_for("ivan@test.local").get(foreign).status_code == 404
    for path, data in ((foreign, {"title": "X"}), (f"{foreign}/video/ukloni", {}), (f"{foreign}/pomak", {"smjer": "dolje"}),
                       (f"{foreign}/obrisi", {}), (f"{foreign}/stavke", {"exercise_id": str(eid)}),
                       (f"{foreign}/stavke/{ia}", {"sets": "3"}), (f"{foreign}/stavke/{ia}/pomak", {"smjer": "gore"}),
                       (f"{foreign}/stavke/{ia}/obrisi", {}),
                       (f"/treninzi/{b}/dan/{db_}/stavke/{ia}", {"sets": "3"}), (f"/treninzi/{b}/dan/{db_}/stavke/{ia}/obrisi", {}),
                       (f"/treninzi/{a}/dan/{db_}/stavke/{ia}/pomak", {"smjer": "gore"})):
        assert ct.post(path, data=data).status_code == 404, path
    assert day_upload(ct, b, da, "u.mp4", MP4).status_code == 404 and list(config.MEDIA_DIR.glob("*")) == []
    for path in ("/treninzi/987654/dan/1", f"/treninzi/{a}/dan/987654", f"/treninzi/{a}/dan/987654/uredi"):
        assert ct.get(path).status_code == 404, path
    assert [(d.id, d.title) for d in db.get_program(a).days] == [(da, "")] and len(db.get_program(b).days) == 1
    assert [(i.id, i.sets) for i in items_of(a)] == [(ia, None)]
    ca = client_for("ana@test.local")                                        # pocetna / gornji: A is not hers
    assert ca.get(f"/treninzi/{a}/dan/{da}").status_code == 403


# ---------- the editors ----------

def test_the_programme_editor_lists_its_days():
    """Its lead says what a programme is now; a row per day: its label (a
    link to its editor), "ponedjeljak · 2 vježbe" muted, Uredi, ↑ / ↓
    (disabled at the ends) and ✕, which asks first; "+ Dodaj dan" under
    them. No exercise list, picker or dose hint any more."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    page = ct.get(f"/treninzi/{pid}/uredi").text
    assert ('Trening ima dane; svaki dan ima zagrijavanje, trening i istezanje, a vježbe biraš iz '
            '<a class="tlink" href="/treninzi/vjezbe">baze vježbi</a>.') in page
    assert f'<a class="act act-quiet" href="/treninzi/{pid}">pogledaj kako polaznik vidi →</a>' in page
    assert '<p class="hint">Trening još nema dana — dodaj prvi.</p>' in page
    assert (f'<form method="post" action="/treninzi/{pid}/dani" class="days-add">\n'
            '  <button type="submit" class="btn btn-sm">+ Dodaj dan</button>') in page
    d1, d2 = db.add_day(pid), db.add_day(pid)
    db.update_day(d1, "Cijelo tijelo", 0, "")
    for n in ("Plank", "Sklekovi"):
        hold(pid, db.create_exercise(n))
    page = ct.get(f"/treninzi/{pid}/uredi").text
    assert "Trening još nema dana" not in page
    rows = page.split('<div class="card it-row" id="dan-')[1:]
    assert [r.split('"')[0] for r in rows] == [str(d1), str(d2)]
    found = [re.search(r'<a class="it-name" href="([^"]+)">([^<]*)</a>\s*<span class="it-note">([^<]*)</span>', r).groups()
             for r in rows]
    assert found == [(f"/treninzi/{pid}/dan/{d1}/uredi", "Dan 1 · Cijelo tijelo", "ponedjeljak · 2 vježbe"),
                     (f"/treninzi/{pid}/dan/{d2}/uredi", "Dan 2", "0 vježbi")]
    assert f'<a class="btn btn-quiet btn-sm" href="/treninzi/{pid}/dan/{d1}/uredi">Uredi</a>' in rows[0]
    assert re.search(r'disabled style="opacity:.35;"\s+aria-label="Pomakni gore: Dan 1 · Cijelo tijelo"', rows[0])
    assert re.search(r'<button class="btn-ghost btn-sm" \s+aria-label="Pomakni dolje: Dan 1 · Cijelo tijelo"', rows[0])
    assert re.search(r'disabled style="opacity:.35;"\s+aria-label="Pomakni dolje: Dan 2"', rows[1])
    assert (f'action="/treninzi/{pid}/dan/{d1}/obrisi" style="margin:0; display:inline;"\n'
            '              data-confirm-title="Obrisati dan?"\n'
            '              data-confirm="„Dan 1 · Cijelo tijelo” se briše s popisom vježbi; same vježbe ostaju u bazi vježbi."\n'
            '              data-confirm-cta="Obriši dan">') in rows[0]
    assert 'id="dodaj"' not in page and 'name="exercise_id"' not in page and "Doza uz naziv" not in page


def test_the_day_editor_shows_each_row_and_its_form():
    """The day editor: crumbs to the programme's editor, "Dan N", the lead
    with the way to the client's page, the day's form, the intro video's
    card, then every section's caption with its rows ("Nema vježbi." when
    it has none): the exercise's name (a link to it), whether it has a
    clip, ↑ / ↓ / ✕ naming forms that stand after the list, and the row's
    own form, its values in it. "Obriši dan" at the bottom asks first."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    goblet, plank = db.create_exercise("Goblet čučanj"), db.create_exercise("Plank")
    upload(ct, plank, "p.mp4", MP4)
    ig, ip = hold(pid, goblet), hold(pid, plank)
    db.update_day_item(ig, "trening", 4, 10, None, 60, "16 kg")
    db.update_day_item(ip, "trening", 3, None, 40, None, "")
    page = ct.get(f"/treninzi/{pid}/dan/{did}/uredi").text
    assert (f'<nav class="crumbs" aria-label="Putanja"><a href="/treninzi">Treninzi</a><span class="sep">/</span>'
            f'<a href="/treninzi/{pid}/uredi">Cijelo tijelo — početna</a><span class="sep">/</span>'
            '<span class="here">Dan 1</span></nav>\n<h1>Dan 1</h1>') in page
    assert ("Naslov, preporučeni dan u tjednu i uvod; ispod toga vježbe po dijelovima — serije, ponavljanja ili "
            "sekunde, odmor i napomena.") in page
    assert f'<a class="act act-quiet" href="/treninzi/{pid}/dan/{did}">pogledaj kako polaznik vidi →</a>' in page
    assert 'placeholder="npr. Cijelo tijelo"' in page and "Kratko objašnjenje treninga — polaznik ga gleda prije prve vježbe." in page
    assert re.findall(r'<h3 class="st-cap" id="dio-(\w+)">([^<]*)</h3>', page) == [
        ("zagrijavanje", "Zagrijavanje"), ("trening", "Trening"), ("istezanje", "Istezanje")]
    assert page.count('<p class="hint st-none">Nema vježbi.</p>') == 2
    rows = page.split('<div class="card it-row" id="stavka-')[1:]
    assert [r.split('"')[0] for r in rows] == [str(ig), str(ip)]
    assert f'<a class="it-name" href="/treninzi/vjezbe/{goblet}">Goblet čučanj</a>' in rows[0]
    assert '<span class="it-video">bez videa</span>' in rows[0] and '<span class="it-video has">video ✓</span>' in rows[1]
    assert re.search(rf'form="st-gore-{ig}" class="btn-ghost btn-sm"\s+disabled', rows[0])
    assert re.search(rf'form="st-dolje-{ig}" class="btn-ghost btn-sm"\s+aria-label="Pomakni dolje: Goblet čučanj"', rows[0])
    assert re.search(rf'form="st-dolje-{ip}" class="btn-ghost btn-sm"\s+disabled', rows[1])
    assert f'form="st-x-{ig}" class="btn-ghost btn-sm" aria-label="Makni iz dana: Goblet čučanj">✕</button>' in rows[0]
    form = rows[0].split('<form class="st-form"')[1].split("</form>")[0]
    assert f'action="/treninzi/{pid}/dan/{did}/stavke/{ig}"' in form
    assert '<option value="trening" selected>Trening</option>' in form and '<option value="zagrijavanje">Zagrijavanje</option>' in form
    values = dict(re.findall(r'name="(\w+)"[^>]*?value="([^"]*)"', form))
    assert values == {"sets": "4", "reps": "10", "seconds": "", "rest": "60", "note": "16 kg"}
    assert 'name="sets" inputmode="numeric" min="1" max="99"' in form and 'name="reps" inputmode="numeric" min="1" max="999"' in form
    assert 'name="seconds" inputmode="numeric" min="1" max="3600"' in form and 'name="rest" inputmode="numeric" min="0" max="3600"' in form
    assert [lab for lab in re.findall(r'<label for="st-\d+-\w+">([^<]*)</label>', form)] == [
        "Dio", "Serije", "Ponavljanja", "Sekunde", "Odmor (s)", "Napomena"]
    after = page.split('<h2 style="font-size:1.05rem; margin:30px 0 12px;">Dodaj vježbu</h2>')[0].split("</section>")[-1]
    assert (f'<form id="st-x-{ig}" method="post" action="/treninzi/{pid}/dan/{did}/stavke/{ig}/obrisi"\n'
            '      data-confirm-title="Maknuti vježbu iz dana?"\n'
            '      data-confirm="„Goblet čučanj” izlazi iz ovog dana; u bazi vježbi ostaje."\n'
            '      data-confirm-cta="Makni"></form>') in after
    assert f'<form id="st-gore-{ip}" method="post" action="/treninzi/{pid}/dan/{did}/stavke/{ip}/pomak"><input type="hidden" name="smjer" value="gore"></form>' in after
    assert ('data-confirm-title="Obrisati dan?"\n'
            '      data-confirm="„Dan 1” se briše s popisom vježbi; same vježbe ostaju u bazi vježbi."\n'
            '      data-confirm-cta="Obriši dan">\n'
            '  <button type="submit" class="btn-ghost">Obriši dan</button>') in page


def test_the_day_editors_picker_adds_into_the_chosen_section():
    """"Dodaj vježbu" is a select of the library (name · tags, the
    alphabet's order) and a select of the section, opening on Trening, then
    Dodaj and "Nova vježba →" (back to this day's editor); the exercise
    goes into the chosen section, pointing at the library row. An empty
    library says so, with the way to make one."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    edit = f"/treninzi/{pid}/dan/{did}/uredi"
    page = ct.get(edit).text
    assert "Baza vježbi je prazna — prvo dodaj vježbu." in page and 'name="exercise_id"' not in page
    assert f'href="/treninzi/vjezbe/nova?natrag={edit}">Nova vježba →</a>' in page
    plank = db.create_exercise("Plank", tags="core, kod kuće")
    cucanj = db.create_exercise("Čučanj s vlastitom težinom")
    biceps = db.create_exercise("Biceps pregib")
    page = ct.get(edit).text
    options = re.findall(r'<option value="(\d*)"[^>]*>([^<]*)</option>', page.split('id="add-ex"')[1].split("</select>")[0])
    assert [(v, unescape(t)) for v, t in options] == [("", "Odaberi vježbu…"), (str(biceps), "Biceps pregib"),
                                                       (str(cucanj), "Čučanj s vlastitom težinom"), (str(plank), "Plank · core, kod kuće")]
    sections = re.findall(r'<option value="(\w+)"( selected)?>([^<]*)</option>', page.split('id="add-dio"')[1].split("</select>")[0])
    assert sections == [("zagrijavanje", "", "Zagrijavanje"), ("trening", " selected", "Trening"), ("istezanje", "", "Istezanje")]
    assert '<label for="add-ex">Vježba iz baze</label>' in page and '<label for="add-dio">Dio</label>' in page
    assert f'href="/treninzi/vjezbe/nova?natrag={edit}">Nova vježba →</a>' in page
    r = ct.post(f"/treninzi/{pid}/dan/{did}/stavke", data={"exercise_id": str(plank), "section": "istezanje"},
                follow_redirects=False)
    item = db.get_day(did).items[0]
    assert r.headers["location"] == f"{edit}#stavka-{item.id}"
    assert (item.exercise_id, item.section, item.position, item.exercise.name) == (plank, "istezanje", 1, "Plank")
    r = ct.post(f"/treninzi/{pid}/dan/{did}/stavke", data={"exercise_id": str(biceps)}, follow_redirects=False)
    assert db.get_day(did).items[1].section == "trening"                    # none named: trening
    page = ct.get(f"{edit}?vjezba={cucanj}").text
    assert f'<option value="{cucanj}" selected>Čučanj s vlastitom težinom</option>' in page
    assert '<option value="" disabled>Odaberi vježbu…</option>' in page


def test_nova_vjezba_comes_back_to_the_editor_and_ignores_a_foreign_path():
    """From the day editor's "Nova vježba →" (natrag=/treninzi/<id>/dan/<id>/uredi)
    the new exercise comes back there, chosen in the picker; its form keeps
    the way back and Odustani leads there. Any natrag that is not a treninzi
    path is ignored: the new exercise's page."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None)
    did = db.add_day(pid)
    back = f"/treninzi/{pid}/dan/{did}/uredi"
    form = ct.get(f"/treninzi/vjezbe/nova?natrag={back}").text
    assert f'<input type="hidden" name="natrag" value="{back}">' in form and f'href="{back}">Odustani</a>' in form
    r = ct.post("/treninzi/vjezbe/nova", data={"name": "Plank", "natrag": back}, follow_redirects=False)
    eid = db.exercises()[0][0].id
    assert r.status_code == 303 and unquote(r.headers["location"]) == f"{back}?vjezba={eid}&ok=Vježba je spremljena.#dodaj"
    page = ct.get(f"{back}?vjezba={eid}").text
    assert f'<option value="{eid}" selected>Plank</option>' in page
    assert '<option value="" disabled>Odaberi vježbu…</option>' in page
    r = ct.post("/treninzi/vjezbe/nova", data={"name": "Plank", "natrag": back})               # refused: the way back kept
    assert r.status_code == 400 and f'<input type="hidden" name="natrag" value="{back}">' in r.text
    for n, foreign in enumerate(("https://evil.example/x", "//evil.example/treninzi/", "/admin", "/treninzi/../admin",
                                 f"{back}?x=1", "javascript:alert(1)", "treninzi/1/uredi", "/treninzi/1/uredi\r\nX: y")):
        r = ct.post("/treninzi/vjezbe/nova", data={"name": f"Vježba {n}", "natrag": foreign}, follow_redirects=False)
        made = next(e.id for e, _ in db.exercises() if e.name == f"Vježba {n}")
        assert r.headers["location"].startswith(f"/treninzi/vjezbe/{made}?ok="), foreign
        assert 'name="natrag"' not in ct.get("/treninzi/vjezbe/nova", params={"natrag": foreign}).text, foreign
    assert 'href="/treninzi/vjezbe">Odustani</a>' in ct.get("/treninzi/vjezbe/nova").text


# ---------- the client ----------

def test_the_clients_programme_page_lists_the_days():
    """A programme's page: its days as cards, each one link to its day's
    page, its label and, muted, the weekday it suggests and how many
    exercises it holds ("1 vježba", "2 vježbe", "5 vježbi"); none: "Trening
    još nema dana." (the trainer: "… — dodaj prvi u uređivanju."). The
    client's list says how many days a programme has."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("Tjedan 1", "Uvod u program.", "pocetna", "cijelo")
    ci = client_for("ivan@test.local")
    page = ci.get(f"/treninzi/{pid}").text
    assert '<p class="hint" style="margin-bottom:6px;">0 dana</p>' in page
    assert '<p class="hint">Trening još nema dana.</p>' in page and "dodaj prvi" not in page
    assert '<p class="hint">Trening još nema dana — dodaj prvi u uređivanju.</p>' in ct.get(f"/treninzi/{pid}").text
    d1, d2, d3 = db.add_day(pid), db.add_day(pid), db.add_day(pid)
    db.update_day(d1, "Cijelo tijelo", 0, "")
    db.update_day(d3, "", 4, "")
    exercises = [db.create_exercise(f"Vježba {n}") for n in range(8)]
    for n, eid in enumerate(exercises):
        hold(pid, eid, day=1 if n < 2 else 2 if n < 3 else 3)
    page = ci.get(f"/treninzi/{pid}").text
    assert '<p class="hint" style="margin-bottom:6px;">3 dana</p>' in page
    cards = re.findall(r'<a class="card day-card" href="([^"]+)">\s*<span class="dc-main">\s*<strong>([^<]*)</strong>\s*'
                       r'<span class="hint">([^<]*)</span>', page)
    assert cards == [(f"/treninzi/{pid}/dan/{d1}", "Dan 1 · Cijelo tijelo", "Preporučeno: ponedjeljak · 2 vježbe"),
                     (f"/treninzi/{pid}/dan/{d2}", "Dan 2", "1 vježba"),
                     (f"/treninzi/{pid}/dan/{d3}", "Dan 3", "Preporučeno: petak · 5 vježbi")]
    assert "Uvod u program." in page and "Uredi trening" not in page and "Trening još nema dana" not in page
    assert '<div class="hint">3 dana · Uvod u program.</div>' in ci.get("/treninzi").text
    db.delete_day(d3)
    db.delete_day(d2)
    assert '<div class="hint">1 dan · Uvod u program.</div>' in ci.get("/treninzi").text


def test_the_day_page_prints_the_whole_list():
    """A day's page: crumbs, its label, "Preporučeno: ponedjeljak · 3
    vježbe", its intro; then each section that holds an exercise under its
    caption, in the sections' order, and each exercise a <details> row:
    "Vježba n" counted across the day, the name, the dose, the rest line and
    the note; open, its clip (preload none) or "Vježba još nema videa.",
    what one rep is and how it is done. The trainer gets "Uredi dan"."""
    ct, *_ = trainer_with_clients()
    goblet = db.create_exercise("Goblet čučanj", "Pete na podu.\nTrup uspravan.", "Do paralele i natrag.")
    upload(ct, goblet, "g.mp4", MP4)
    clip = db.exercise(goblet).video
    plank = db.create_exercise("Plank", "Lopatice aktivne.")
    stretch = db.create_exercise("Istezanje stražnje lože")
    pid = db.create_program("Tjedan 1", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    db.update_day(did, "Cijelo tijelo", 0, "Lagano.\nBez žurbe.")
    i1 = hold(pid, plank)
    db.update_day_item(i1, "trening", 3, None, 40, 45, "")
    i2 = hold(pid, goblet, "zagrijavanje")
    db.update_day_item(i2, "zagrijavanje", 2, 15, None, 30, "8 kg")
    i3 = hold(pid, stretch, "istezanje")
    db.update_day_item(i3, "istezanje", None, None, 30, None, "po nozi")
    ci = client_for("ivan@test.local")
    page = ci.get(f"/treninzi/{pid}/dan/{did}").text
    assert (f'<a href="/treninzi">Treninzi</a><span class="sep">/</span><a href="/treninzi/{pid}">Tjedan 1</a>'
            '<span class="sep">/</span><span class="here">Dan 1</span></nav>\n<h1>Dan 1 · Cijelo tijelo</h1>') in page
    assert '<p class="hint">Preporučeno: ponedjeljak · 3 vježbe</p>' in page
    assert '<p class="day-intro">Lagano.\nBez žurbe.</p>' in page and "Uredi dan" not in page and "<title>Dan 1 · Cijelo tijelo" in page
    assert re.findall(r'<h2 class="dx-cap" id="dio-(\w+)">([^<]*)</h2>', page) == [
        ("zagrijavanje", "Zagrijavanje"), ("trening", "Trening"), ("istezanje", "Istezanje")]
    rows = page.split('<details class="card ex">')[1:]
    heads = [re.search(r'<span class="dx-n">([^<]*)</span>\s*<span class="dx-line"><span class="dx-name">([^<]*)</span>'
                       r'(?:<span class="dx-dose">([^<]*)</span>)?</span>\s*(?:<span class="dx-sub">([^<]*)</span>)?', r).groups()
             for r in rows]
    assert heads == [("Vježba 1", "Goblet čučanj", "2 × 15", "Odmor između serija: 30 s · 8 kg"),
                     ("Vježba 2", "Plank", "3 × 40 s", "Odmor između serija: 45 s"),
                     ("Vježba 3", "Istezanje stražnje lože", "30 s", "po nozi")]
    assert '<span class="dx-go" aria-hidden="true">▷</span>' in rows[0]
    assert f'<video src="/media/{clip}" controls playsinline preload="none"></video>' in rows[0]
    assert "<strong>Jedno ponavljanje:</strong> Do paralele i natrag.</p>" in rows[0]
    assert '<p class="pre">Pete na podu.\nTrup uspravan.</p>' in rows[0]
    assert "Vježba još nema videa." in rows[1] and "<video" not in rows[1] and "Jedno ponavljanje" not in rows[1]
    assert '<p class="pre">Lopatice aktivne.</p>' in rows[1] and "Vježba još nema videa." in rows[2]
    assert ci.get(f"/media/{clip}").status_code == 200
    assert (f'<a class="btn btn-quiet btn-sm" href="/treninzi/{pid}/dan/{did}/uredi">Uredi dan</a>'
            in ct.get(f"/treninzi/{pid}/dan/{did}").text)

    db.delete_day_item(i3)                                                  # a section with none is not on the page
    db.update_day_item(i2, "zagrijavanje", None, None, None, None, "")     # nothing set: no dose, no line
    page = ci.get(f"/treninzi/{pid}/dan/{did}").text
    assert [k for k, _ in re.findall(r'<h2 class="dx-cap" id="dio-(\w+)">([^<]*)</h2>', page)] == ["zagrijavanje", "trening"]
    first = page.split('<details class="card ex">')[1].split("</summary>")[0]
    assert 'class="dx-dose"' not in first and 'class="dx-sub"' not in first
    db.update_day(did, "", None, "")
    page = ci.get(f"/treninzi/{pid}/dan/{did}").text
    assert "<h1>Dan 1</h1>" in page and '<p class="hint">2 vježbe</p>' in page and '<p class="day-intro">' not in page

    empty = db.add_day(pid)
    page = ci.get(f"/treninzi/{pid}/dan/{empty}").text
    assert '<p class="hint">0 vježbi</p>' in page and "Dan još nema vježbi." in page and '<h2 class="dx-cap"' not in page
    assert "Dan još nema vježbi — dodaj ih u uređivanju." in ct.get(f"/treninzi/{pid}/dan/{empty}").text


def test_a_days_intro_video_is_stored_replaced_removed_and_watched(monkeypatch):
    """A day's intro video, as an exercise's clip: stored under a new name
    (dan-<id>-<hex>.<ext>) and shown on the editor and, first, on the
    client's day page; replaced, the old file goes; a file that is not a
    clip, one over VIDEO_MAX_MB and no file are refused with the sentence;
    "Ukloni video" deletes it. /media serves it to staff and to a client
    the programme is matched to, 403 to another; a day deleted takes its
    file."""
    ct, ivan, ana = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    edit, view = f"/treninzi/{pid}/dan/{did}/uredi", f"/treninzi/{pid}/dan/{did}"
    cap = config.VIDEO_MAX_MB
    page = ct.get(edit).text
    assert '<h2 id="dan-video-h">Uvodni video</h2>' in page and f"Video (mp4, mov ili webm, do {cap} MB)" in page
    assert ">Dodaj video</button>" in page and "<video" not in page
    assert ("iPhone: Postavke → Kamera → Formati → „Najkompatibilnije”, inače Chrome na Androidu i Windowsu ne može "
            "reproducirati snimku.") in page

    r = day_upload(ct, pid, did, "uvod.MP4", MP4)
    assert location(r) == f"{edit}?ok=Video je spremljen."
    first = db.get_day(did).intro_video
    assert re.fullmatch(rf"dan-{did}-[0-9a-f]{{16}}\.mp4", first) and (config.MEDIA_DIR / first).read_bytes() == MP4
    page = ct.get(edit).text
    assert f'<video src="/media/{first}" controls playsinline preload="metadata"></video>' in page
    assert ">Zamijeni video</button>" in page and 'form="dan-video-x" class="btn-ghost btn-sm">Ukloni video</button>' in page
    ci, ca = client_for("ivan@test.local"), client_for("ana@test.local")
    view_page = ci.get(view).text
    assert ('<p class="hint">Uvodni video — pogledaj ga prije treninga.</p>\n'
            f'    <video src="/media/{first}" controls playsinline preload="metadata"></video>') in view_page
    assert [p.id for p in db.video_programs(first)] == [pid]
    assert ct.get(f"/media/{first}").content == MP4 and ci.get(f"/media/{first}").status_code == 200
    assert ca.get(f"/media/{first}").status_code == 403

    day_upload(ct, pid, did, "uvod.webm", WEBM, "video/webm")
    second = db.get_day(did).intro_video
    assert second.endswith(".webm") and not (config.MEDIA_DIR / first).exists()
    for filename, data in (("uvod.avi", MP4), ("uvod.mp4", PNG), ("uvod.webm", MP4)):
        assert location(day_upload(ct, pid, did, filename, data)) == f"{edit}?error={UNSUPPORTED}", filename
    monkeypatch.setattr(config, "VIDEO_MAX_MB", 1)
    r = day_upload(ct, pid, did, "big.mp4", MP4 + b"\x00" * (1024 * 1024))
    assert location(r) == f"{edit}?error=Video je prevelik — najviše 1 MB."
    monkeypatch.setattr(config, "VIDEO_MAX_MB", cap)
    assert location(day_upload(ct, pid, did, "", b"")) == f"{edit}?error=Odaberi video."
    assert db.get_day(did).intro_video == second and sorted(p.name for p in config.MEDIA_DIR.iterdir()) == [second]

    r = ct.post(f"{edit[:-6]}/video/ukloni", follow_redirects=False)
    assert location(r) == f"{edit}?ok=Video je uklonjen."
    assert db.get_day(did).intro_video is None and list(config.MEDIA_DIR.iterdir()) == []
    assert "<video" not in ci.get(view).text and "Uvodni video" not in ci.get(view).text
    assert db.video_programs(second) is None and ct.get(f"/media/{second}").status_code == 404

    day_upload(ct, pid, did, "uvod.mp4", MP4)
    third = db.get_day(did).intro_video
    ct.post(f"/treninzi/{pid}/dan/{did}/obrisi")
    assert db.get_day(did) is None and not (config.MEDIA_DIR / third).exists()


# ---------- the migrations ----------

def _migration(file: str):
    path = pathlib.Path(__file__).parents[1] / "alembic" / "versions" / file
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _run(step) -> None:
    """A revision's upgrade() or downgrade(), run for real on qmt_test."""
    with db.engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        step()


def _tables() -> set[str]:
    return set(sa_inspect(db.engine).get_table_names())


def _diff_tables(d) -> set[str]:
    """The table a compare_metadata diff is about."""
    d = d[0] if isinstance(d, list) else d
    kind, obj = d[0], d[1]
    if kind.startswith("modify_") or kind in ("add_column", "remove_column"):
        return {d[2]}
    if kind in ("add_table", "remove_table"):
        return {obj.name}
    if kind in ("add_fk", "remove_fk"):
        return {obj.parent.name}
    return {obj.table.name}                                                 # an index or a constraint


def _schema_diffs(tables: set[str]) -> list:
    """What compare_metadata finds between qmt_test and the models, about
    these tables (the rest of the schema has its own, older drift)."""
    from alembic.autogenerate import compare_metadata
    with db.engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    return [d for d in diffs if _diff_tables(d) & tables]


TRENINZI = {"programs", "program_days", "program_day_items", "program_items", "exercises", "exercise_alternatives"}


def _old_items() -> list[tuple]:
    with db.engine.connect() as conn:
        return [tuple(r) for r in conn.execute(sa_text(
            "SELECT program_id, position, title, body, media_name, media_kind FROM program_items ORDER BY program_id, position"))]


def _flat_items() -> list[tuple]:
    """program_items as stage 1 shaped them: (programme, place, exercise, note)."""
    with db.engine.connect() as conn:
        return [tuple(r) for r in conn.execute(sa_text(
            "SELECT program_id, position, exercise_id, note FROM program_items ORDER BY program_id, position"))]


def _flat_library() -> list[tuple]:
    """The library as stage 1 shaped it, in the alphabet's order: name,
    instructions, clip, and how many programmes' flat items hold it."""
    with db.engine.connect() as conn:
        rows = conn.execute(sa_text(
            "SELECT e.name, e.instructions, e.video, count(DISTINCT i.program_id) FROM exercises e "
            "LEFT JOIN program_items i ON i.exercise_id = e.id GROUP BY e.id")).all()
    return sorted((tuple(r) for r in rows), key=lambda r: alpha_key(r[0]))


def _flat_notes(*pids: int) -> list[list[tuple[str, str]]]:
    """Each programme's flat items in order: (its exercise's name, its note)."""
    with db.engine.connect() as conn:
        rows = conn.execute(sa_text("SELECT i.program_id, e.name, i.note FROM program_items i "
                                    "JOIN exercises e ON e.id = i.exercise_id ORDER BY i.program_id, i.position")).all()
    return [[(name, note) for p, name, note in rows if p == pid] for pid in pids]


def test_the_migration_splits_a_body_into_the_items_dose_and_the_exercises_cue():
    """split_body: a first line that starts with a digit once trimmed is a
    dose, the item's note, and the rest, trimmed, is the candidate for the
    exercise's instructions; a body whose first line is no dose is all
    instructions; one that is only a dose line all note."""
    split = _migration("4c2e8a6f1d39_exercise_library.py").split_body
    assert split("3 × 8 · 8 kg\nPete cijelo vrijeme na podu, trup uspravan.") == (
        "3 × 8 · 8 kg", "Pete cijelo vrijeme na podu, trup uspravan.")                 # prod's every body
    assert split("Lopatice aktivne.\nGluteusi stisnuti.") == ("", "Lopatice aktivne.\nGluteusi stisnuti.")
    assert split("2 × 10 sporih ponavljanja") == ("2 × 10 sporih ponavljanja", "")
    assert split("  \n 3 × 30 s po strani \n\n  Drži kukove ravno.  \n") == ("3 × 30 s po strani", "Drži kukove ravno.")
    assert split("Tri serije po 8\n3 × 8") == ("", "Tri serije po 8\n3 × 8")       # a dose further down is text
    assert split("²/₃ raspona\nPolako.") == ("", "²/₃ raspona\nPolako.")              # an ASCII digit only
    assert split(None) == split("") == split("  \n ") == ("", "")


def _library() -> list[tuple]:
    return [(e.name, e.instructions, e.video, n) for e, n in db.exercises()]


def test_the_migration_folds_the_items_into_the_library_and_back(capsys):
    """4c2e8a6f1d39, run on qmt_test shaped as before it (items typed by
    hand: title, body, media), prod's bodies among them ("DOSE\\nCUE"): each
    body split (its dose the item's note), an exercise per name, trimmed and
    compared casefolded ("Goblet čučanj" in one programme and "GOBLET
    ČUČANJ " in another are one, named as the first writes it), its
    instructions the first cue (a shared exercise gets it once, its doses
    differing per item), its clip the first video; an image, a second clip
    and a cue not kept are printed to the log, their files left in storage;
    every item points at its exercise, the four columns gone and a note in
    their place; the library's tables are the model's. Downgrade puts the
    columns back (the body the note and the instructions, a line between
    them) and drops the tables; a second upgrade folds them again into the
    same library and the same notes, printing nothing. Then 7c3bf996c983 on
    top makes the items days, and every table is the models'."""
    mig = _migration("4c2e8a6f1d39_exercise_library.py")
    assert (mig.revision, mig.down_revision) == ("4c2e8a6f1d39", "b18ebed39701")
    with db.engine.begin() as conn:                                         # the tables as before the revision
        conn.execute(sa_text("DROP TABLE program_day_items, program_days, exercise_alternatives, exercises"))
        conn.execute(sa_text("CREATE TABLE program_items (id serial PRIMARY KEY, "
                             "program_id integer NOT NULL REFERENCES programs (id) ON DELETE CASCADE, "
                             "position integer NOT NULL, title varchar(160) NOT NULL, body text, "
                             "media_name varchar(200), media_kind varchar(8))"))
        conn.execute(sa_text("CREATE INDEX ix_program_items_program_id ON program_items (program_id)"))
    p1 = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    p2 = db.create_program("Cijelo tijelo — srednja", None, "srednja", "cijelo")
    p3 = db.create_program("Core control", None)
    cue = "Pete cijelo vrijeme na podu, trup uspravan."
    rows = [(p1, 1, "Goblet čučanj", f"3 × 8 · 8 kg\n{cue}", "a1.mp4", "video"),            # a dose and the cue
            (p1, 2, "Plank", "Lopatice aktivne.", "p1.png", "img"),                       # no dose: all instructions
            (p2, 1, "GOBLET  ČUČANJ ", f"4 × 10 · 16 kg\n{cue}", None, None),             # the same cue, another dose
            (p2, 2, "Plank", "3 × 40 s", None, None),                                    # only a dose: all note
            (p3, 1, "Mrtvo dizanje", None, None, None),
            (p3, 2, "goblet čučanj", "2 × 10 sporih ponavljanja\nDrugi tekst.", "a2.mp4", "video"),
            (p3, 3, "Bočni plank", "  3 × 30 s po strani  ", None, None)]
    with db.engine.begin() as conn:
        for pid, position, title, body, media, kind in rows:
            conn.execute(sa_text("INSERT INTO program_items (program_id, position, title, body, media_name, media_kind) "
                                 "VALUES (:p, :n, :t, :b, :m, :k)"),
                         {"p": pid, "n": position, "t": title, "b": body, "m": media, "k": kind})
    _run(mig.upgrade)
    log = capsys.readouterr().out
    assert "image p1.png dropped" in log and "clip a2.mp4 dropped, the exercise keeps a1.mp4" in log
    assert log.count("not kept") == 1 and "its instructions are not kept" in log and "'Drugi tekst.'" in log
    assert {c["name"] for c in sa_inspect(db.engine).get_columns("program_items")} == {
        "id", "program_id", "position", "exercise_id", "note"}
    library = [("Bočni plank", "", None, 1), ("Goblet čučanj", cue, "a1.mp4", 3), ("Mrtvo dizanje", "", None, 1),
               ("Plank", "Lopatice aktivne.", None, 2)]
    notes = [[("Goblet čučanj", "3 × 8 · 8 kg"), ("Plank", "")], [("Goblet čučanj", "4 × 10 · 16 kg"), ("Plank", "3 × 40 s")],
             [("Mrtvo dizanje", ""), ("Goblet čučanj", "2 × 10 sporih ponavljanja"), ("Bočni plank", "3 × 30 s po strani")]]
    assert _flat_library() == library and _flat_notes(p1, p2, p3) == notes
    assert _schema_diffs({"exercises", "exercise_alternatives"}) == []      # what create_all makes, to the index
    with pytest.raises(Exception, match="uq_exercises_name"):                # the name's index is there
        with db.engine.begin() as conn:
            conn.execute(sa_text("INSERT INTO exercises (name) VALUES ('PLANK')"))

    _run(mig.downgrade)
    assert not {"exercises", "exercise_alternatives"} & _tables()
    assert "note" not in {c["name"] for c in sa_inspect(db.engine).get_columns("program_items")}
    assert _old_items() == [(p1, 1, "Goblet čučanj", f"3 × 8 · 8 kg\n{cue}", "a1.mp4", "video"),
                            (p1, 2, "Plank", "Lopatice aktivne.", None, None),
                            (p2, 1, "Goblet čučanj", f"4 × 10 · 16 kg\n{cue}", "a1.mp4", "video"),
                            (p2, 2, "Plank", "3 × 40 s\nLopatice aktivne.", None, None),
                            (p3, 1, "Mrtvo dizanje", None, None, None),
                            (p3, 2, "Goblet čučanj", f"2 × 10 sporih ponavljanja\n{cue}", "a1.mp4", "video"),
                            (p3, 3, "Bočni plank", "3 × 30 s po strani", None, None)]
    _run(mig.upgrade)
    assert capsys.readouterr().out == ""                                     # nothing left to drop
    assert _flat_library() == library and _flat_notes(p1, p2, p3) == notes

    _run(_migration("7c3bf996c983_program_days.py").upgrade)                 # and on to the days
    assert "program_items" not in _tables() and _schema_diffs(TRENINZI) == []
    assert _library() == library
    assert [[(i.exercise.name, i.sets, i.reps, i.seconds, i.note) for i in items_of(p)] for p in (p1, p2, p3)] == [
        [("Goblet čučanj", 3, 8, None, "8 kg"), ("Plank", None, None, None, "")],
        [("Goblet čučanj", 4, 10, None, "16 kg"), ("Plank", 3, None, 40, "")],
        [("Mrtvo dizanje", None, None, None, ""), ("Goblet čučanj", 2, 10, None, "sporih ponavljanja"),
         ("Bočni plank", 3, None, 30, "po strani")]]


# the notes the days' migration parses, and what it makes of each
DOSES = [("3 × 8 · 8 kg", (3, 8, None, "8 kg")), ("3 × 20 s", (3, None, 20, "")),
         ("3 × 5 (s koljena)", (3, 5, None, "s koljena")), ("3 × 6 po nozi", (3, 6, None, "po nozi")),
         ("3 × 10 · 2 × 6 kg", (3, 10, None, "2 × 6 kg")), ("", (None, None, None, "")),
         ("Tempo 3-1-1", (None, None, None, "Tempo 3-1-1"))]


def test_the_days_migration_parses_a_dose():
    """parse_dose: "S × N" at the start is the sets and the reps, or the
    seconds when a unit (s, sek, sec) follows; what follows, a leading "·"
    or dash and the spaces stripped and one pair of parentheses around it
    removed, is the note; a note that does not start with a dose is kept
    whole."""
    parse = _migration("7c3bf996c983_program_days.py").parse_dose
    for note, parsed in DOSES:
        assert parse(note) == parsed, note
    assert parse("3 × 10 po nozi · 2 × 8 kg") == (3, 10, None, "po nozi · 2 × 8 kg")
    assert parse("3x30 SEK") == (3, None, 30, "") and parse("2 X 45 sec – lagano") == (2, None, 45, "lagano")
    assert parse("2 × 10 sporih ponavljanja") == (2, 10, None, "sporih ponavljanja")    # "s" of a word is no unit
    assert parse("3 × 8 — (a) i (b)") == (3, 8, None, "(a) i (b)")                    # not one pair around it all
    assert parse("100 × 8") == (None, None, None, "100 × 8") and parse(None) == (None, None, None, "")


def test_the_days_migration_folds_the_items_into_days_and_back(capsys):
    """7c3bf996c983, run on qmt_test shaped as before it (stage 1's flat
    items, each note its razina's dose): a programme with items gets ONE day
    (Dan 1, no title, no weekday, no intro) holding them in their order in
    section trening, no rest, each note parsed; one with none gets no day;
    a line is printed per programme; program_items goes and the tables are
    the models'. Downgrade puts program_items back, a programme's items
    counting on across its days in each day's display order, each note its
    dose and its note joined by " · ", and drops the days; a second upgrade
    folds them again."""
    mig = _migration("7c3bf996c983_program_days.py")
    assert (mig.revision, mig.down_revision) == ("7c3bf996c983", "4c2e8a6f1d39")
    with db.engine.begin() as conn:                                         # the tables as before the revision
        conn.execute(sa_text("DROP TABLE program_day_items, program_days"))
        conn.execute(sa_text("CREATE TABLE program_items (id serial PRIMARY KEY, "
                             "program_id integer NOT NULL REFERENCES programs (id) ON DELETE CASCADE, "
                             "position integer NOT NULL, "
                             "exercise_id integer NOT NULL REFERENCES exercises (id) ON DELETE RESTRICT, "
                             "note text NOT NULL DEFAULT '')"))
        conn.execute(sa_text("CREATE INDEX ix_program_items_program_id ON program_items (program_id)"))
        conn.execute(sa_text("CREATE INDEX ix_program_items_exercise_id ON program_items (exercise_id)"))
    p1 = db.create_program("Cijelo tijelo — srednja", None, "srednja", "cijelo")
    p2 = db.create_program("Prazan", None)
    ids = [db.create_exercise(f"Vježba {n}") for n in range(len(DOSES))]
    with db.engine.begin() as conn:
        for n, (eid, (note, _)) in enumerate(zip(ids, DOSES), start=1):
            conn.execute(sa_text("INSERT INTO program_items (program_id, position, exercise_id, note) VALUES (:p, :n, :e, :t)"),
                         {"p": p1, "n": n, "e": eid, "t": note})
    _run(mig.upgrade)
    assert capsys.readouterr().out == f"[7c3bf996c983] programs {p1} ('Cijelo tijelo — srednja'): Dan 1 with 7 exercises\n"
    assert "program_items" not in _tables() and _schema_diffs(TRENINZI) == []
    days = db.get_program(p1).days
    assert [(d.position, d.title, d.weekday, d.intro, d.intro_video) for d in days] == [(1, "", None, "", None)]
    assert [(i.position, i.section, i.exercise_id, i.rest_seconds) for i in days[0].items] == [
        (n, "trening", eid, None) for n, eid in enumerate(ids, start=1)]
    assert [(i.sets, i.reps, i.seconds, i.note) for i in days[0].items] == [parsed for _, parsed in DOSES]
    assert db.get_program(p2).days == []

    # a second day, and sections: the way back counts on across the days, each in its display order
    first, second = days[0].id, db.add_day(p1)
    warm = db.add_day_item(first, ids[0], "zagrijavanje")
    db.update_day_item(warm, "zagrijavanje", 2, None, None, None, "")
    stretch = db.add_day_item(second, ids[1], "istezanje")
    db.update_day_item(stretch, "istezanje", 2, None, 30, None, "po nozi")
    reps = db.add_day_item(second, ids[2], "zagrijavanje")
    db.update_day_item(reps, "zagrijavanje", None, 10, None, 30, "")
    _run(mig.downgrade)
    assert not {"program_days", "program_day_items"} & _tables()
    back = ["2 serije", "3 × 8 · 8 kg", "3 × 20 s", "3 × 5 · s koljena", "3 × 6 · po nozi", "3 × 10 · 2 × 6 kg", "",
            "Tempo 3-1-1", "10 ponavljanja", "2 × 30 s · po nozi"]
    exercises = [ids[0], *ids, ids[2], ids[1]]
    assert _flat_items() == [(p1, n, eid, note) for n, (eid, note) in enumerate(zip(exercises, back), start=1)]
    _run(mig.upgrade)
    assert capsys.readouterr().out.endswith("Dan 1 with 10 exercises\n")
    assert "program_items" not in _tables() and _schema_diffs(TRENINZI) == []
    assert [(i.exercise_id, i.section, i.sets, i.reps, i.seconds, i.note) for i in items_of(p1)][:3] == [
        (ids[0], "trening", None, None, None, "2 serije"), (ids[0], "trening", 3, 8, None, "8 kg"),
        (ids[1], "trening", 3, None, 20, "")]


def test_nutricionizam_links_to_mojimakrosi():
    make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    page = c.get("/nutricionizam").text
    assert "MojiMakrosi" in page and config.MOJIMAKROSI_URL in page


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
SHOWN_ALTS = """() => [...document.querySelectorAll('#altList label')].filter(l => !l.hidden && l.offsetHeight > 0)
                       .map(l => l.textContent.trim().split(' · ')[0])"""


def _phone(browser, server: str, email: str):
    """A 390px touch phone logged in as `email`: (context, page, errors)."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    pg = ctx.new_page(); errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
    pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    pg.goto(server + "/login")
    pg.evaluate("() => localStorage.setItem('qmt-a2hs', 'installed')")
    pg.fill("main input[name=email]", email); pg.fill("main input[name=password]", "lozinka123")
    pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
    return ctx, pg, errors


def test_the_trainer_builds_the_library_on_a_phone(server):
    """At 390px, touch: the trainer opens the library from the ☰ drawer's
    Admin rows (Vježbe), makes "Goblet čučanj" with two similar exercises
    found through the filter, sees it in the list, then opens a day's
    editor and adds it with the picker. The page never scrolls sideways (the
    list, the exercise's page, the editor); no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    for name, tags in (("Plank", "core, kod kuće"), ("Sklekovi", "prsa, kod kuće"), ("Biceps pregib", "ruke, bučice")):
        db.create_exercise(name, tags=tags)
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _phone(browser, server, "trener@test.local")

        def check(ok: bool, what: str) -> None:
            if not ok:
                problems.append(what)

        pg.tap(".nav-burger")
        with pg.expect_navigation():
            pg.tap("#mainNav >> text=Vježbe")
        pg.wait_for_load_state("networkidle")
        check(pg.url == server + "/treninzi/vjezbe", f"Vježbe in the drawer led to {pg.url}")
        check(pg.evaluate(OVERFLOW) == 0, f"the list overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap("text=+ Nova vježba")
        pg.wait_for_load_state("networkidle")
        pg.fill("#ex-name", "Goblet čučanj")
        pg.fill("#ex-instr", "Pete na podu, trup uspravan.")
        pg.fill("#ex-rep", "Spust do paralele i natrag.")
        pg.fill("#ex-tags", "noge, bučice")
        check(pg.is_visible("#altFilter"), "the filter is not shown")
        pg.fill("#altFilter", "KUĆ")
        shown = pg.evaluate(SHOWN_ALTS)
        check(shown == ["Plank", "Sklekovi"], f"the filter 'KUĆ' shows {shown}")
        pg.press("#altFilter", "Enter")                    # the keyboard's Go: filters, never saves
        pg.wait_for_timeout(400)
        check(pg.url == server + "/treninzi/vjezbe/nova" and len(db.exercises()) == 3,
              f"Enter in the filter sent the form: {pg.url}, {len(db.exercises())} exercises")
        for name in shown:
            pg.tap(f"#altList label:has-text('{name}')")
        pg.fill("#altFilter", "")
        check(pg.evaluate(SHOWN_ALTS) == ["Biceps pregib", "Plank", "Sklekovi"], f"the filter cleared shows {pg.evaluate(SHOWN_ALTS)}")
        check(pg.evaluate(OVERFLOW) == 0, f"the new exercise's form overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap("main form.ex-card button[type=submit]")
        pg.wait_for_load_state("networkidle")
        made = next((e for e, _ in db.exercises() if e.name == "Goblet čučanj"), None)
        check(made is not None and pg.url.split("?")[0] == f"{server}/treninzi/vjezbe/{made.id}", f"Spremi led to {pg.url}")
        if made:
            similar = [x.name for x in db.exercise(made.id).alternatives]
            check(similar == ["Plank", "Sklekovi"] and made.tags == "noge, bučice", f"saved: {similar}, {made.tags!r}")
            check(pg.is_visible("text=Vježba je spremljena — dodaj joj video."), "no ok alert")
            check(pg.evaluate(OVERFLOW) == 0, f"the exercise's page overflows by {pg.evaluate(OVERFLOW)}px")
        pg.goto(server + "/treninzi/vjezbe"); pg.wait_for_load_state("networkidle")
        listed = pg.evaluate("() => [...document.querySelectorAll('.ex-name')].map(n => n.textContent)")
        check(listed == ["Biceps pregib", "Goblet čučanj", "Plank", "Sklekovi"], f"the list: {listed}")
        check(pg.evaluate(OVERFLOW) == 0, f"the list overflows by {pg.evaluate(OVERFLOW)}px")
        pg.goto(f"{server}/treninzi/{pid}/dan/{did}/uredi"); pg.wait_for_load_state("networkidle")
        if made:
            pg.select_option("#add-ex", str(made.id))
            with pg.expect_navigation():
                pg.tap("#dodaj button[type=submit]")
            pg.wait_for_load_state("networkidle")
            check(item_names(pid) == ["Goblet čučanj"], f"the programme holds {item_names(pid)}")
            check(pg.is_visible(f'a.it-name[href="/treninzi/vjezbe/{made.id}"]'), "the item's row is not there")
        check(pg.evaluate(OVERFLOW) == 0, f"the day editor overflows by {pg.evaluate(OVERFLOW)}px")
        problems += errors
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


def test_the_trainer_builds_a_day_on_a_phone(server):
    """At 390px, touch: the trainer opens a programme's editor, adds a day
    ("+ Dodaj dan", which opens its editor), adds "Goblet čučanj" into
    Zagrijavanje with the picker, sets 2 × 15 and 30 s of rest on its row
    and saves, then follows "pogledaj kako polaznik vidi →" to the client's
    day page and sees the row: "Vježba 1", the name, "2 × 15", "Odmor između
    serija: 30 s"; a tap opens it in place. The matched client sees the
    same. The programme's editor, the day's editor and the day's page never
    scroll sideways; no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)
    make_user("ivan@test.local")                                           # pocetna / cijelo: the programme's
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    goblet = db.create_exercise("Goblet čučanj", "Pete na podu, trup uspravan.", "Spust do paralele.", "noge, bučice")
    db.create_exercise("Plank", tags="core")
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    def summary_text(pg) -> str:                                            # the DOM's words, not the CSS's capitals
        return " ".join((pg.locator("details.ex summary").first.text_content() or "").split())

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _phone(browser, server, "trener@test.local")
        pg.goto(f"{server}/treninzi/{pid}/uredi"); pg.wait_for_load_state("networkidle")
        check(pg.is_visible("text=Trening još nema dana — dodaj prvi."), "the empty editor says nothing")
        check(pg.evaluate(OVERFLOW) == 0, f"the programme's editor overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap("form.days-add button")
        pg.wait_for_load_state("networkidle")
        days = db.get_program(pid).days
        did = days[0].id if days else 0
        check(len(days) == 1 and pg.url == f"{server}/treninzi/{pid}/dan/{did}/uredi", f"+ Dodaj dan led to {pg.url}")
        pg.select_option("#add-ex", str(goblet))
        pg.select_option("#add-dio", "zagrijavanje")
        with pg.expect_navigation():
            pg.tap("#dodaj button[type=submit]")
        pg.wait_for_load_state("networkidle")
        items = db.get_day(did).items if did else []
        check([(i.exercise_id, i.section) for i in items] == [(goblet, "zagrijavanje")], f"the day holds {items}")
        if items:
            row = f"#stavka-{items[0].id}"
            check(pg.url.endswith(f"/uredi{row}"), f"Dodaj led to {pg.url}")
            pg.fill(f"{row} input[name=sets]", "2")
            pg.fill(f"{row} input[name=reps]", "15")
            pg.fill(f"{row} input[name=rest]", "30")
            with pg.expect_navigation():
                pg.tap(f"{row} .st-go button")
            pg.wait_for_load_state("networkidle")
            it = db.get_day_item(items[0].id)
            check((it.section, it.sets, it.reps, it.seconds, it.rest_seconds) == ("zagrijavanje", 2, 15, None, 30),
                  f"saved {it.section, it.sets, it.reps, it.seconds, it.rest_seconds}")
            check("Spremljeno." in (pg.text_content(".alert.ok") or ""), "no ok alert")
            check(pg.input_value(f"{row} input[name=reps]") == "15", "the row's form lost what was saved")
        check(pg.evaluate(OVERFLOW) == 0, f"the day's editor overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap("text=pogledaj kako polaznik vidi →")
        pg.wait_for_load_state("networkidle")
        check(pg.url == f"{server}/treninzi/{pid}/dan/{did}", f"the client's page is {pg.url}")

        def sees_the_row(page, who: str) -> None:
            text = summary_text(page)
            check(page.is_visible("h2.dx-cap#dio-zagrijavanje") and all(
                w in text for w in ("Vježba 1", "Goblet čučanj", "2 × 15", "Odmor između serija: 30 s")),
                f"{who}'s row says {text!r}")
            page.locator("details.ex summary").first.tap()
            page.wait_for_timeout(200)
            check(page.locator("details.ex").first.evaluate("d => d.open")
                  and page.is_visible("text=Pete na podu, trup uspravan.") and page.is_visible("text=Vježba još nema videa."),
                  f"{who}'s row did not open")
            check(page.evaluate(OVERFLOW) == 0, f"the day's page overflows by {page.evaluate(OVERFLOW)}px for {who}")

        sees_the_row(pg, "the trainer")
        problems += errors
        ctx.close()
        ctx, pg, errors = _phone(browser, server, "ivan@test.local")
        pg.goto(f"{server}/treninzi/{pid}/dan/{did}"); pg.wait_for_load_state("networkidle")
        sees_the_row(pg, "the client")
        problems += errors
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"
