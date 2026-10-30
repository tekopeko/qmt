"""Training-programme (treninzi) tests: authorization, ordering, and since
30.10.2026 the library of exercises (/treninzi/vjezbe).

The owner (29.-30.10.2026): "We should have a database of exercises which he
can choose from and add them to different training programmes that will be
modular. Each exercise will have a video connected to it which will show the
exercise and show what one rep means." An exercise is a row (`Exercise`:
name, unique whatever its case, instructions, what one rep is, a clip, free
tags, and the similar exercises a client may later swap one for, one row a
pair, read both ways); a programme's items point at it, so one held by a
programme cannot be deleted. Amir builds the library on its own pages, and
the programme editor picks from it. The client's page lists the programme's
exercises as before, each from the library. Migration 4c2e8a6f1d39 folds the
items typed by hand until then into the library; the round trip is run for
real on qmt_test. The browser half walks the trainer through the library on
a phone.
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
from qmt.models import Base, alpha_key
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


def pairs() -> set[tuple[int, int]]:
    """exercise_alternatives as stored: (exercise_id, alternative_id)."""
    with db.engine.connect() as conn:
        return {tuple(r) for r in conn.execute(sa_text("SELECT exercise_id, alternative_id FROM exercise_alternatives"))}


def names(page: str) -> list[str]:
    """The library list's exercises, in order."""
    return [unescape(n) for n in re.findall(r'<span class="ex-name">([^<]*)</span>', page)]


def item_names(pid: int) -> list[str]:
    return [it.exercise.name for it in db.get_program(pid).items]


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
    from qmt import upitnik

    assert db.ensure_online_skeletons() == len(upitnik.LEVELS) * len(upitnik.GOALS)
    assert db.ensure_online_skeletons() == 0            # second run adds nothing
    rows = [(p, ni) for p, ni in db.all_programs() if p.level]
    combos = {(p.level, p.goal) for p, _ in rows}
    assert combos == {(lv, g) for lv in upitnik.LEVELS for g in upitnik.GOALS}
    # every slot ships with default exercises — no combo renders empty...
    assert all(ni > 0 for _, ni in rows)
    counts = {p.id: ni for p, ni in rows}
    db.ensure_online_skeletons()                        # ...and reruns never duplicate them
    assert {p.id: ni for p, ni in db.all_programs() if p.level} == counts

    # a slot the trainer emptied-and-refilled keeps HIS content: any item blocks the backfill
    pid = next(p.id for p, _ in rows)
    for item in db.get_program(pid).items:
        db.delete_item(item.id)
    db.add_item(pid, db.create_exercise("Trenerova vježba", "5 × 5"))
    db.ensure_online_skeletons()
    assert item_names(pid) == ["Trenerova vježba"]


def test_ensure_online_skeletons_makes_one_library_row_per_name():
    """The nine slots' default exercises are library rows, one per name,
    reused across the slots (Goblet čučanj in the six of cijelo and donji);
    an exercise of the name Amir made first, in another case, is the one
    they use, his instructions kept; a rerun makes none. Each slot's item
    notes its razina's dose (the defaults' until 30.10.2026, kept), and the
    library's instructions are the cues alone, never a dose."""
    mine = db.create_exercise("goblet ČUČANJ", "Moje upute.")
    db.ensure_online_skeletons()
    rows = db.exercises()
    library = [e.name for e, _ in rows]
    assert len(library) == 10 and len({n.casefold() for n in library}) == 10
    assert library == sorted(library, key=alpha_key)
    used = {e.name: n for e, n in rows}
    assert used["goblet ČUČANJ"] == 6 and used["Veslanje u pretklonu"] == 6 and used["Plank"] == 3
    assert db.exercise(mine).instructions == "Moje upute."
    for p, _ in db.all_programs():
        want = {"cijelo": ["goblet ČUČANJ", "Sklekovi", "Veslanje u pretklonu", "Plank"],
                "gornji": ["Potisak s bučicama na klupi", "Veslanje u pretklonu", "Potisak iznad glave", "Biceps pregib"],
                "donji": ["goblet ČUČANJ", "Iskorak unatrag", "Rumunjsko mrtvo dizanje", "Glute most"]}[p.goal]
        assert item_names(p.id) == want, p.title
    assert db.exercise(next(e.id for e, _ in rows if e.name == "Plank")).instructions == "Lopatice aktivne, gluteusi stisnuti."
    assert not [e.name for e, _ in rows if e.instructions[:1].isdigit()]
    notes = {(p.level, p.goal): [i.note for i in db.get_program(p.id).items] for p, _ in db.all_programs()}
    assert notes[("pocetna", "cijelo")] == ["3 × 8 · 8 kg", "3 × 5 (s koljena)", "3 × 10 · 2 × 6 kg", "3 × 20 s"]
    assert notes[("napredna", "cijelo")] == ["4 × 12 · 24 kg", "4 × 15", "4 × 12 · 2 × 14 kg", "3 × 60 s"]
    assert notes[("srednja", "donji")] == ["4 × 10 · 20 kg", "3 × 10 po nozi · 2 × 8 kg", "4 × 10 · 24 kg", "3 × 15 · 10 kg"]
    assert notes[("srednja", "gornji")][1] == "4 × 10 · 2 × 12 kg"          # Veslanje: its dose per cilj too
    db.ensure_online_skeletons()
    assert len(db.exercises()) == 10


def test_clients_cannot_create_or_edit():
    ct, ivan, _ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    ci = client_for("ivan@test.local")
    assert ci.post("/treninzi", data={"title": "X", "level": "pocetna",
                                      "goal": "cijelo"}).status_code == 403
    assert ci.get(f"/treninzi/{pid}/uredi").status_code == 403
    assert ci.post(f"/treninzi/{pid}/items", data={"exercise_id": "1"}).status_code == 403
    assert ci.post(f"/treninzi/{pid}/delete").status_code == 403


def test_item_reorder_and_delete_keep_positions_dense():
    ct, ivan, _ = trainer_with_clients()
    pid = db.create_program("T", None)
    for name in ("A", "B", "C"):
        db.add_item(pid, db.create_exercise(name))
    a, b, c = [i.id for i in db.get_program(pid).items]

    db.move_item(c, "up")                                   # A, C, B
    assert item_names(pid) == ["A", "C", "B"]
    db.move_item(a, "up")                                   # top stays put
    assert item_names(pid) == ["A", "C", "B"]

    ct.post(f"/treninzi/{pid}/items/{c}/delete")            # ✕: out of the programme...
    items = db.get_program(pid).items
    assert [i.exercise.name for i in items] == ["A", "B"]
    assert [i.position for i in items] == [1, 2]            # gap closed
    assert [e.name for e, _ in db.exercises()] == ["A", "B", "C"]   # ...the exercise stays in the library


def test_delete_program_keeps_the_exercises_and_their_clips():
    """A programme deleted takes its items, never the library's rows or
    their clips (other programmes may hold them)."""
    ct, ivan, _ = trainer_with_clients()
    pid = db.create_program("T", None)
    eid = db.create_exercise("V")
    upload(ct, eid, "v.mp4", MP4)
    db.add_item(pid, eid)
    name = db.exercise(eid).video
    ct.post(f"/treninzi/{pid}/delete")
    assert db.get_program(pid) is None
    assert db.exercise(eid).video == name and (config.MEDIA_DIR / name).is_file()
    assert "vježbe i njihovi videi ostaju u bazi vježbi" in ct.get(f"/treninzi/{db.create_program('U', None)}/uredi").text


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
    """Deleting is refused while any programme holds the exercise, the
    sentence naming them (up to three, in the alphabet's order, then "…";
    one programme, held twice, is one), on the page's alert too; once out of
    them all it goes, and its clip with it."""
    ct, *_ = trainer_with_clients()
    eid = db.create_exercise("Goblet čučanj")
    upload(ct, eid, "g.mp4", MP4)
    clip = db.exercise(eid).video
    progs = {t: db.create_program(t, None) for t in ("Donji dio tijela — srednja", "Core control", "Cijelo tijelo — početna",
                                                     "Zadnji")}
    held = [db.add_item(progs["Core control"], eid), db.add_item(progs["Core control"], eid)]
    with pytest.raises(ValueError) as refused:
        db.delete_exercise(eid)
    assert str(refused.value) == "Vježba je u 1 programu (Core control) — prvo je makni iz njega."
    held.append(db.add_item(progs["Donji dio tijela — srednja"], eid))
    with pytest.raises(ValueError) as refused:
        db.delete_exercise(eid)
    assert str(refused.value) == "Vježba je u 2 programa (Core control, Donji dio tijela — srednja) — prvo je makni iz njih."
    held += [db.add_item(progs["Cijelo tijelo — početna"], eid), db.add_item(progs["Zadnji"], eid)]
    r = ct.post(f"/treninzi/vjezbe/{eid}/obrisi", follow_redirects=False)
    sentence = "Vježba je u 4 programa (Cijelo tijelo — početna, Core control, Donji dio tijela — srednja …) — prvo je makni iz njih."
    assert r.status_code == 303 and unquote(r.headers["location"]).replace("+", " ") == f"/treninzi/vjezbe/{eid}?error={sentence}"
    page = ct.get(r.headers["location"]).text
    assert f'<div class="alert" role="alert"><span>{sentence}</span></div>' in unescape(page)
    assert ('<p class="hint">U 4 programa: Cijelo tijelo — početna, Core control, Donji dio tijela — srednja, Zadnji.</p>'
            in page)
    assert db.exercise(eid) is not None and (config.MEDIA_DIR / clip).is_file()
    for item_id in held:
        db.delete_item(item_id)
    r = ct.post(f"/treninzi/vjezbe/{eid}/obrisi", follow_redirects=False)
    assert unquote(r.headers["location"]).replace("+", " ") == "/treninzi/vjezbe?ok=Vježba je obrisana."
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
    to a client only through a programme matched to him (his online plan
    running); a guest goes to log in; a name no exercise holds is 404, a
    path never reaches storage."""
    ct, ivan, ana = trainer_with_clients()
    eid = db.create_exercise("Čučanj")
    upload(ct, eid, "c.mp4", MP4)
    name = db.exercise(eid).video
    ci, ca = client_for("ivan@test.local"), client_for("ana@test.local")
    assert ct.get(f"/media/{name}").status_code == 200
    assert ci.get(f"/media/{name}").status_code == 403                     # in no programme yet
    db.add_item(db.create_program("S videom", None, "pocetna", "cijelo"), eid)    # ivan's combo
    assert ci.get(f"/media/{name}").status_code == 200 and ci.get(f"/media/{name}").content == MP4
    assert ca.get(f"/media/{name}").status_code == 403
    anon = TestClient(app).get(f"/media/{name}", follow_redirects=False)
    assert anon.status_code == 303 and "/login" in anon.headers["location"]
    assert ct.get("/media/vjezba-1-0000000000000000.mp4").status_code == 404
    assert ct.get("/media/..%2f..%2fetc%2fpasswd").status_code == 404


# ---------- the library: the list and its search ----------

def test_the_list_and_its_search():
    """The list: every exercise in the alphabet's order, its tags as chips,
    "video ✓" / "bez videa", "u N programa" (one: "u 1 programu", none: "ni
    u jednom programu"). ?q= keeps those whose name or tags hold it,
    whatever its case; blank shows all; none matching says so. An empty
    library says "Još nema vježbi." with the button."""
    ct, *_ = trainer_with_clients()
    page = ct.get("/treninzi/vjezbe").text
    assert "<h1>Vježbe</h1>" in page and "Još nema vježbi." in page and 'href="/treninzi/vjezbe/nova">+ Nova vježba</a>' in page
    assert ('<p class="hint">Baza vježbi: svaki trening slaže se od njih. Vježba ima upute, što je jedno ponavljanje, '
            'oznake i video.</p>') in page
    ids = {n: db.create_exercise(n, tags=t) for n, t in (("Plank", "core, kod kuće"), ("Goblet čučanj", "noge, bučice"),
                                                         ("Čučanj s vlastitom težinom", "noge, kod kuće"), ("Biceps pregib", ""))}
    upload(ct, ids["Plank"], "p.webm", WEBM, "video/webm")
    for t in ("A", "B"):
        db.add_item(db.create_program(t, None), ids["Goblet čučanj"])
    db.add_item(db.create_program("C", None), ids["Plank"])
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


# ---------- the programme editor's picker, and the way back ----------

def test_the_editors_picker_adds_an_item_pointing_at_the_exercise():
    """"+ Dodaj vježbu" is a select of the library (name · tags, the
    alphabet's order) and Dodaj; an item added points at the chosen exercise
    and its row links to it; a choice that is no exercise adds nothing. The
    rows have no edit form any more: ↑ / ↓ and ✕. The lead says how the
    programme reaches a client and where its exercises come from."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    page = ct.get(f"/treninzi/{pid}/uredi").text
    assert "Baza vježbi je prazna — prvo dodaj vježbu." in page and 'name="exercise_id"' not in page
    assert ("Ovaj trening automatski vide polaznici kojima je upitnik odredio njegovu razinu i cilj." in page
            and 'Vježbe biraš iz <a class="tlink" href="/treninzi/vjezbe">baze vježbi</a>' in page)
    assert "u biblioteci" not in page and "dodijeli" not in page
    plank = db.create_exercise("Plank", tags="core, kod kuće")
    cucanj = db.create_exercise("Čučanj s vlastitom težinom")
    biceps = db.create_exercise("Biceps pregib")
    page = ct.get(f"/treninzi/{pid}/uredi").text
    options = re.findall(r'<option value="(\d*)"[^>]*>([^<]*)</option>', page.split('id="add-ex"')[1].split("</select>")[0])
    assert [(v, unescape(t)) for v, t in options] == [("", "Odaberi vježbu…"), (str(biceps), "Biceps pregib"),
                                                       (str(cucanj), "Čučanj s vlastitom težinom"), (str(plank), "Plank · core, kod kuće")]
    assert f'href="/treninzi/vjezbe/nova?natrag=/treninzi/{pid}/uredi">Nova vježba →</a>' in page
    r = ct.post(f"/treninzi/{pid}/items", data={"exercise_id": str(plank)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/treninzi/{pid}/uredi#dodaj"
    items = db.get_program(pid).items
    assert [(i.exercise_id, i.position) for i in items] == [(plank, 1)]
    page = ct.get(f"/treninzi/{pid}/uredi").text
    assert f'<a class="it-name" href="/treninzi/vjezbe/{plank}">Plank</a>' in page and '<span class="it-video">bez videa</span>' in page
    row = page.split('class="card it-row"')[1].split("</div>")[0]
    assert f"/items/{items[0].id}/move" in row and f"/items/{items[0].id}/delete" in row and "/edit" not in row
    assert items[0].note == "" and 'class="it-note"' not in row and '<p class="hint it-hint">' not in page   # no note
    for bad in ("", "abc", "²", "987654", "99999999999"):
        r = ct.post(f"/treninzi/{pid}/items", data={"exercise_id": bad}, follow_redirects=False)
        assert unquote(r.headers["location"]).replace("+", " ") == f"/treninzi/{pid}/uredi?error=Odaberi vježbu iz baze.", bad
    assert len(db.get_program(pid).items) == 1
    assert ct.post("/treninzi/987654/items", data={"exercise_id": str(plank)}).status_code == 404


def test_the_editor_shows_an_items_note_and_says_it_is_not_edited_yet():
    """An item's note (its razina's dose, from the migration or the slots'
    defaults) is muted right after the exercise's name in its row, and one
    hint above the rows says it is not edited in this stage (a title would
    never show on a phone); a programme with no note has no hint."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    goblet, plank = db.create_exercise("Goblet čučanj"), db.create_exercise("Plank")
    db.add_item(pid, goblet, note="3 × 8 · 8 kg")
    db.add_item(pid, plank)
    page = ct.get(f"/treninzi/{pid}/uredi").text
    rows = page.split('class="card it-row"')[1:]
    assert (f'<a class="it-name" href="/treninzi/vjezbe/{goblet}">Goblet čučanj</a>\n'
            '    <span class="it-note">3 × 8 · 8 kg</span>') in rows[0]
    assert 'class="it-note"' not in rows[1]
    assert ('<p class="hint it-hint">Doza uz naziv (npr. 3 × 8 · 8 kg) zasad se ne uređuje: serije, ponavljanja i '
            'odmor dolaze s danima treninga.</p>') in page
    assert 'name="note"' not in page                                    # nothing edits it here
    other = db.create_program("U", None)
    db.add_item(other, plank)
    assert '<p class="hint it-hint">' not in ct.get(f"/treninzi/{other}/uredi").text


def test_nova_vjezba_comes_back_to_the_editor_and_ignores_a_foreign_path():
    """From the editor's "Nova vježba →" (natrag=/treninzi/<id>/uredi) the
    new exercise comes back there, chosen in the picker; its form keeps the
    way back and Odustani leads there. Any natrag that is not a treninzi
    path is ignored: the new exercise's page."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None)
    back = f"/treninzi/{pid}/uredi"
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

def test_the_clients_programme_page_prints_the_library_exercise():
    """A client's programme lists its exercises from the library: the name,
    the item's note (its razina's dose) in bold when it has one, "Jedno
    ponavljanje: …" when it is set, the instructions, the clip (inline, with
    its controls) when it has one; and nothing of the library's pages."""
    ct, ivan, ana = trainer_with_clients()
    goblet = db.create_exercise("Goblet čučanj", "Pete na podu.\nTrup uspravan.", "Do paralele i natrag.")
    upload(ct, goblet, "g.mp4", MP4)
    clip = db.exercise(goblet).video
    plank = db.create_exercise("Plank", "Lopatice aktivne.")
    pid = db.create_program("Tjedan 1", None, "pocetna", "cijelo")
    db.add_item(pid, goblet, note="3 × 8 · 8 kg")
    db.add_item(pid, plank)
    page = client_for("ivan@test.local").get(f"/treninzi/{pid}").text
    assert "2 vježbi" in page
    cards = page.split('<div class="card" style="padding:0; overflow:hidden;">')[1:]
    assert 'Goblet čučanj</h3>' in cards[0] and 'Plank</h3>' in cards[1]
    note = '<p style="margin-top:8px; font-weight:700; white-space:pre-line; overflow-wrap:anywhere;">3 × 8 · 8 kg</p>'
    assert note in cards[0] and "font-weight:700" not in cards[1]
    assert "<strong>Jedno ponavljanje:</strong> Do paralele i natrag.</p>" in cards[0]
    assert ">Pete na podu.\nTrup uspravan.</p>" in cards[0]
    assert cards[0].index(note) < cards[0].index("Jedno ponavljanje") < cards[0].index("Pete na podu.")
    assert re.search(rf'<video controls playsinline preload="metadata"[^>]*\s+src="/media/{clip}"></video>', cards[0])
    assert "Jedno ponavljanje" not in cards[1] and "<video" not in cards[1] and ">Lopatice aktivne.</p>" in cards[1]
    assert "/treninzi/vjezbe" not in page and "Uredi trening" not in page
    assert client_for("ivan@test.local").get(f"/media/{clip}").status_code == 200


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


def _old_items() -> list[tuple]:
    with db.engine.connect() as conn:
        return [tuple(r) for r in conn.execute(sa_text(
            "SELECT program_id, position, title, body, media_name, media_kind FROM program_items ORDER BY program_id, position"))]


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


def _notes(*pids: int) -> list[list[str]]:
    return [[i.note for i in db.get_program(pid).items] for pid in pids]


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
    their place; the schema is the model's. Downgrade puts the columns back
    (the body the note and the instructions, a line between them) and drops
    the tables; a second upgrade folds them again into the same library and
    the same notes, printing nothing."""
    mig = _migration("4c2e8a6f1d39_exercise_library.py")
    assert (mig.revision, mig.down_revision) == ("4c2e8a6f1d39", "b18ebed39701")
    with db.engine.begin() as conn:                                         # the tables as before the revision
        conn.execute(sa_text("DROP TABLE exercise_alternatives"))
        conn.execute(sa_text("ALTER TABLE program_items DROP COLUMN exercise_id, DROP COLUMN note, "
                             "ADD COLUMN title varchar(160) NOT NULL, ADD COLUMN body text, "
                             "ADD COLUMN media_name varchar(200), ADD COLUMN media_kind varchar(8)"))
        conn.execute(sa_text("DROP TABLE exercises"))
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
    notes = [["3 × 8 · 8 kg", ""], ["4 × 10 · 16 kg", "3 × 40 s"], ["", "2 × 10 sporih ponavljanja", "3 × 30 s po strani"]]
    assert _library() == library and _notes(p1, p2, p3) == notes
    assert item_names(p1) == ["Goblet čučanj", "Plank"] and item_names(p3) == ["Mrtvo dizanje", "Goblet čučanj", "Bočni plank"]
    from alembic.autogenerate import compare_metadata
    with db.engine.connect() as conn:                                       # what create_all makes, to the index
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert [d for d in diffs if re.search(r"exercise|program_items", repr(d))] == []
    with pytest.raises(Exception, match="uq_exercises_name"):                # the name's index is there
        with db.engine.begin() as conn:
            conn.execute(sa_text("INSERT INTO exercises (name) VALUES ('PLANK')"))

    _run(mig.downgrade)
    assert not {"exercises", "exercise_alternatives"} & set(sa_inspect(db.engine).get_table_names())
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
    assert _library() == library and _notes(p1, p2, p3) == notes


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


def test_the_trainer_builds_the_library_on_a_phone(server):
    """At 390px, touch: the trainer opens the library from the ☰ drawer's
    Admin rows (Vježbe), makes "Goblet čučanj" with two similar exercises
    found through the filter, sees it in the list, then opens a programme's
    editor and adds it with the picker. The page never scrolls sideways (the
    list, the exercise's page, the editor); no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    for name, tags in (("Plank", "core, kod kuće"), ("Sklekovi", "prsa, kod kuće"), ("Biceps pregib", "ruke, bučice")):
        db.create_exercise(name, tags=tags)
    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(server + "/login")
        pg.evaluate("() => localStorage.setItem('qmt-a2hs', 'installed')")
        pg.fill("main input[name=email]", "trener@test.local"); pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")

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
        pg.goto(f"{server}/treninzi/{pid}/uredi"); pg.wait_for_load_state("networkidle")
        if made:
            pg.select_option("#add-ex", str(made.id))
            with pg.expect_navigation():
                pg.tap("#dodaj button[type=submit]")
            pg.wait_for_load_state("networkidle")
            check(item_names(pid) == ["Goblet čučanj"], f"the programme holds {item_names(pid)}")
            check(pg.is_visible(f'a.it-name[href="/treninzi/vjezbe/{made.id}"]'), "the item's row is not there")
        check(pg.evaluate(OVERFLOW) == 0, f"the editor overflows by {pg.evaluate(OVERFLOW)}px")
        problems += errors
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"
