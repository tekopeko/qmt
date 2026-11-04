"""Training-programme (treninzi) tests: authorization, ordering, the library
of exercises (/treninzi/vjezbe, 30.10.2026) and, since the same day, the
programmes' days (stage 2 of roadmap/2026-10-29-online-treninzi-spec.md).

The owner (29.-30.10.2026): "We should have a database of exercises which he
can choose from and add them to different training programmes that will be
modular. Each exercise will have a video connected to it which will show the
exercise and show what one rep means." An exercise is a row (`Exercise`:
name, unique whatever its case, instructions, what one rep is, a clip, free
tags, and the exercises a client may swap it for); a programme's days' items
point at it. Amir builds the library on its own pages.

Since 4.11.2026 a swap has a direction (the owner: "Amir wants it so that he
can choose A -> B but not B -> A for some pairs"): a row of
exercise_alternatives, (A, B), lets a client doing A do B instead; a mutual
pair is two rows. An exercise's form ("Zamjene za ovu vježbu") sets its own
rows only, and its page says which exercises it may stand in for. No
migration: the rows stay as Amir ticked them (each on the page of the
exercise it may be replaced from), only the reading narrowed.

Since 4.11.2026 (the owner: "allow Amir to delete exercises even if they are
part of some training and that the programme/training stays but it will just
be without that exercise and allow that there is a training with no
exercises") an exercise is deleted whatever holds it: it leaves every day
that held it (the foreign key is CASCADE, migration 45c543c860f3, run for
real on qmt_test there and back), the days and the programmes stay.

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

Since the same day nothing makes, fills or refills a programme but Amir (the
owner: "he should be able to create a training with no exercises, if he does
that its his fault, okay? No refilling either way please, no default,
everything modular so that he can change it."): opening /treninzi makes
nothing, a programme with no day and a day with no exercise stay so, and a
client is told what is not there yet.

Since 2.11.2026 (Amir's wish, via the owner: "so that it is clear") a day
reads "Trening 1 … Trening N", the programme around it "program", and the
section `trening` "Glavni dio"; the model, the routes and the ids still say
day.
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
from sqlalchemy.exc import IntegrityError

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


def stored_counts() -> tuple[int, ...]:
    """(programmes, days, their items, exercises) as stored."""
    with db.engine.connect() as conn:
        return tuple(conn.execute(sa_text(f"SELECT count(*) FROM {t}")).scalar_one()
                     for t in ("programs", "program_days", "program_day_items", "exercises"))


def admin_row(page: str, title: str) -> tuple[str, str, bool] | None:
    """A programme's row in the trainer's /treninzi table: its Dani, its
    Vježbe and whether "prazno!" stands beside them; None without one."""
    m = re.search(rf'<td><strong>{re.escape(title)}</strong></td>\s*<td>(\d+)</td>\s*'
                  rf'<td>(\d+)( <span[^>]*>prazno!</span>)?</td>', page)
    return m and (m.group(1), m.group(2), m.group(3) is not None)


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


def test_opening_treninzi_makes_no_programme_and_no_exercise():
    """Nothing makes a programme but Amir (30.10.2026): the trainer's
    /treninzi lists what there is and makes nothing, no programme, day,
    item or exercise, on an empty database (each razina "Nema programa za
    ovu razinu.") and on one with a programme, however often it opens."""
    ct, *_ = trainer_with_clients()
    assert stored_counts() == (0, 0, 0, 0)
    for _ in range(2):
        page = ct.get("/treninzi").text
        assert stored_counts() == (0, 0, 0, 0) and db.all_programs() == []
    assert page.count("Nema programa za ovu razinu.") == 3
    pid = db.create_program("Tjedan 1", None, "srednja", "gornji")
    hold(pid, db.create_exercise("Plank"))
    assert stored_counts() == (1, 1, 1, 1)
    for _ in range(2):
        page = ct.get("/treninzi").text
        assert stored_counts() == (1, 1, 1, 1)
    assert [p.id for p, _, _ in db.all_programs()] == [pid]
    assert page.count("Nema programa za ovu razinu.") == 2 and admin_row(page, "Tjedan 1") == ("1", "1", False)


def test_a_programme_whose_last_day_is_deleted_stays_with_none():
    """Its last day deleted, a programme has no day and gets none back:
    not from /treninzi, nor from its own pages (the trainer's, a client's).
    The table shows it with 0 days and 0 exercises, "prazno!"; its editor
    says "Program još nema treninga — dodaj prvi.", and its delete no
    longer promises a refill."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    hold(pid, db.create_exercise("Plank"))
    r = ct.post(f"/treninzi/{pid}/dan/{did}/obrisi", follow_redirects=False)
    assert location(r) == f"/treninzi/{pid}/uredi?ok=Trening je obrisan."
    assert stored_counts() == (1, 0, 0, 1)
    ct.get("/treninzi")
    view, editor = ct.get(f"/treninzi/{pid}").text, ct.get(f"/treninzi/{pid}/uredi").text
    ci = client_for("ivan@test.local")                                      # pocetna / cijelo: his
    assert ci.get("/treninzi").status_code == 200 and ci.get(f"/treninzi/{pid}").status_code == 200
    table = ct.get("/treninzi").text                                        # again, after its pages
    assert stored_counts() == (1, 0, 0, 1) and db.get_program(pid).days == []
    assert admin_row(table, "Cijelo tijelo — početna") == ("0", "0", True)
    assert '<p class="hint">Program još nema treninga — dodaj prvi u uređivanju.</p>' in view
    assert '<p class="hint">Program još nema treninga — dodaj prvi.</p>' in editor
    assert ('data-confirm="„Cijelo tijelo — početna” — briše se program s treninzima i vježbama; '
            'same vježbe i njihovi videi ostaju u bazi vježbi."') in editor
    assert "Prazan slot" not in editor and "osnovnim vježbama" not in editor


def test_a_day_whose_last_exercise_is_removed_stays_empty():
    """Its last exercise taken out (✕), a day stays, with none, and gets
    none back: not from /treninzi, nor from the programme's pages or its
    own (the trainer's, a client's). The table shows 1 day and 0
    exercises, "prazno!"; the client's day says "Trening još nema vježbi."."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    iid = hold(pid, db.create_exercise("Plank"))
    day = f"/treninzi/{pid}/dan/{did}"
    r = ct.post(f"{day}/stavke/{iid}/obrisi", follow_redirects=False)
    assert r.headers["location"] == f"{day}/uredi"
    assert stored_counts() == (1, 1, 0, 1)
    for path in ("/treninzi", f"/treninzi/{pid}", f"/treninzi/{pid}/uredi", day, f"{day}/uredi"):
        assert ct.get(path).status_code == 200, path
    ci = client_for("ivan@test.local")                                      # pocetna / cijelo: his
    assert ci.get("/treninzi").status_code == 200 and ci.get(f"/treninzi/{pid}").status_code == 200
    client_day = ci.get(day).text
    table = ct.get("/treninzi").text
    assert stored_counts() == (1, 1, 0, 1) and [len(d.items) for d in db.get_program(pid).days] == [0]
    assert admin_row(table, "Cijelo tijelo — početna") == ("1", "0", True)
    assert '<p class="hint" style="margin-top:22px;">Trening još nema vježbi.</p>' in client_day


def test_a_client_is_told_what_is_not_there_yet():
    """A client whose combination has no programme (another combination's
    is not his): "Program za tvoju kombinaciju još se priprema."; one whose
    programme has no day sees it listed, "0 treninga", and its page says
    "Program još nema treninga.". What he opens makes nothing either."""
    trainer_with_clients()
    db.create_program("Gornji blok", None, "pocetna", "gornji")             # ana's combination
    ci = client_for("ivan@test.local")                                      # pocetna / cijelo
    page = ci.get("/treninzi").text
    assert '<p style="margin-bottom:6px;"><strong>Program za tvoju kombinaciju još se priprema.</strong></p>' in page
    assert "Gornji blok" not in page and stored_counts() == (1, 0, 0, 0)
    pid = db.create_program("Tjedan 1", None, "pocetna", "cijelo")
    page = ci.get("/treninzi").text
    assert "još se priprema" not in page and f'href="/treninzi/{pid}"' in page and '<div class="hint">0 treninga</div>' in page
    assert '<p class="hint">Program još nema treninga.</p>' in ci.get(f"/treninzi/{pid}").text
    assert stored_counts() == (2, 0, 0, 0)


def test_the_trainers_treninzi_page_says_he_makes_the_programmes():
    """The lead says what is automatic (the matching) and what is his (the
    programmes, their days and exercises), and what a combination with no
    programme tells its client; the form is "Novi program", its button
    "Kreiraj i dodaj treninge", which opens the new programme's editor, the
    programme with no day."""
    ct, *_ = trainer_with_clients()
    page = ct.get("/treninzi").text
    lead = ("Sve je automatski: upitnik svrsta polaznika u razinu i cilj, a on odmah vidi programe označene tom "
            "kombinacijom — ništa se ne dodjeljuje ručno. Programe slažeš sam: za svaku kombinaciju koju nudiš "
            "napravi program pa mu dodaj treninge i vježbe. Kombinacija bez programa polazniku kaže da se program "
            "još priprema.")
    assert f'<p class="hint"> {lead} </p>' in " ".join(page.split())
    assert '<h2 style="font-size:1.05rem; margin-bottom:12px;">Novi program</h2>' in page
    assert '<button type="submit">Kreiraj i dodaj treninge</button>' in page
    assert 'placeholder="npr. Gornji dio tijela — tjedan 2"' in page
    for gone in ("skice se stvore same", "devet osnovnih varijanti", "Dodatni program", "Kreiraj i dodaj vježbe"):
        assert gone not in page, gone
    r = ct.post("/treninzi", data={"title": "Tjedan 1", "level": "srednja", "goal": "donji"}, follow_redirects=False)
    pid = db.all_programs()[0][0].id
    assert r.headers["location"] == f"/treninzi/{pid}/uredi" and stored_counts() == (1, 0, 0, 0)


def test_a_day_says_its_label_and_an_item_its_dose_and_rest():
    """A day's label is "Trening N", with its title "Trening N · title";
    its items read section by section in their order, each in position
    order. An item's dose is the list's words: sets × reps, sets × seconds,
    reps or seconds alone, sets alone, nothing; its rest "60 s" or
    nothing."""
    assert ProgramDay(position=2, title="").label == "Trening 2"
    assert ProgramDay(position=1, title="Cijelo tijelo").label == "Trening 1 · Cijelo tijelo"

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
    assert location(r) == "/treninzi?ok=Program je obrisan."
    assert db.get_program(pid) is None and db.get_day(did) is None
    assert db.exercise(eid).video == name and (config.MEDIA_DIR / name).is_file()
    assert not (config.MEDIA_DIR / intro).exists()
    assert ("briše se program s treninzima i vježbama; same vježbe i njihovi videi ostaju u bazi vježbi."
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


def save_swaps(ct: TestClient, eid: int, name: str, *ticked: int) -> None:
    """The exercise's form posted as the trainer: its name, these ticked."""
    r = ct.post(f"/treninzi/vjezbe/{eid}", data={"name": name, "alternative": [str(t) for t in ticked]},
                follow_redirects=False)
    assert r.status_code == 303, r.text


def swaps(eid: int) -> list[str]:
    """The exercises a client may swap this one for (Exercise.alternatives)."""
    return [x.name for x in db.exercise(eid).alternatives]


def stands(eid: int) -> list[str]:
    """The exercises this one may stand in for (Exercise.stands_in_for)."""
    return [x.name for x in db.exercise(eid).stands_in_for]


def test_a_swap_is_a_direction_its_exercises_form_sets():
    """A row of exercise_alternatives is a direction (4.11.2026, the owner:
    "Amir wants it so that he can choose A -> B but not B -> A for some
    pairs"): ticked on A's form, B is stored as (A, B) and read one way, A's
    swaps are B and B's none, B stands in for A. B's form ticking A stores
    (B, A), a mutual pair of two rows; B's form unticking A takes (B, A)
    only, A's row stays; A's form unticking B takes (A, B) and leaves (B,
    A). Its own id, an unknown one and a row held already store nothing; a
    row the other way is the other form's own, stored; a deleted exercise
    takes its rows either way."""
    ct, *_ = trainer_with_clients()
    a, b, c = (db.create_exercise(n) for n in ("Goblet čučanj", "Iskorak", "Čučanj s vlastitom težinom"))

    save_swaps(ct, a, "Goblet čučanj", b, c)
    assert pairs() == {(a, b), (a, c)}
    assert swaps(a) == ["Čučanj s vlastitom težinom", "Iskorak"] and swaps(b) == [] == swaps(c)
    assert stands(a) == [] and stands(b) == ["Goblet čučanj"] == stands(c)
    save_swaps(ct, b, "Iskorak", a)                                   # the other direction: two rows
    assert pairs() == {(a, b), (a, c), (b, a)}
    assert swaps(b) == ["Goblet čučanj"] and stands(a) == ["Iskorak"] and stands(b) == ["Goblet čučanj"]
    save_swaps(ct, b, "Iskorak")                                      # B's untick: its own row only
    assert pairs() == {(a, b), (a, c)} and swaps(a) == ["Čučanj s vlastitom težinom", "Iskorak"]
    save_swaps(ct, b, "Iskorak", a)
    save_swaps(ct, a, "Goblet čučanj", c)                             # A's untick: (A, B) goes, (B, A) stays
    assert pairs() == {(a, c), (b, a)}
    assert swaps(a) == ["Čučanj s vlastitom težinom"] and swaps(b) == ["Goblet čučanj"] and stands(b) == []
    save_swaps(ct, a, "Goblet čučanj", a, c, 987654)                  # its own id, an unknown one, (A, C) held
    assert pairs() == {(a, c), (b, a)}
    save_swaps(ct, c, "Čučanj s vlastitom težinom", a)                # (C, A): C's own, though (A, C) is there
    assert pairs() == {(a, c), (b, a), (c, a)} and stands(a) == ["Čučanj s vlastitom težinom", "Iskorak"]
    db.delete_exercise(a)
    assert pairs() == set() and swaps(b) == [] == swaps(c) and stands(c) == []


def alt_rows(page: str) -> list[tuple[int, bool, bool]]:
    """"Zamjene za ovu vježbu"'s rows in order: (the exercise's id, ticked,
    tagged "u oba smjera")."""
    box = page.split('id="altList"')[1].split("</div>")[0]
    return [(int(v), bool(on), '<span class="alt-back">· u oba smjera</span>' in rest) for v, on, rest in
            re.findall(r'<input type="checkbox" name="alternative" value="(\d+)"( checked)?>(.*?)</label>', box, re.S)]


def stands_line(page: str) -> tuple[str, list[tuple[str, str]]] | None:
    """The line under the list as read, and its links (href, name); None
    without one."""
    m = re.search(r'<p class="hint alt-for">(.*?)</p>', page, re.S)
    if m is None:
        return None
    links = [(h, unescape(n)) for h, n in re.findall(r'<a class="tlink" href="([^"]+)">([^<]*)</a>', m.group(1))]
    return unescape(re.sub(r"<[^>]+>", "", m.group(1))), links


def test_the_page_says_which_way_a_swap_goes():
    """The section is "Zamjene za ovu vježbu" with its one hint; a ticked
    row is this -> that; a ticked row whose exercise may also be swapped
    for this one (the reverse row: a mutual pair) carries "u oba smjera"
    after its tags, a muted span (text, not a control), and an unticked row
    none, the reverse row or not; under the list "Zamjena je za: A, B."
    names the exercises this one may stand in for, in the alphabet's order,
    each a .tlink to its page (where that direction is ticked). An exercise
    in no mutual pair has no tag, one that stands in for none no line, a
    new one's page neither. The filter is "Filtriraj zamjene", a new
    exercise's lead names "zamjene". A refused save keeps the ticks as
    posted, the reverse rows (the tags' half) and the line as stored."""
    ct, *_ = trainer_with_clients()
    ids = {n: db.create_exercise(n, tags=t) for n, t in (("Goblet čučanj", "noge"), ("Čučanj skok", ""),
                                                         ("Čučanj s vlastitom težinom", "kod kuće"), ("Iskorak", ""))}
    g, j, b, i = (ids[n] for n in ("Goblet čučanj", "Čučanj skok", "Čučanj s vlastitom težinom", "Iskorak"))
    db.update_exercise(j, "Čučanj skok", "", "", "", {g, b})                  # the jump: to the goblet, the plain squat
    db.update_exercise(g, "Goblet čučanj", "", "", "noge", {b, i})            # the goblet: the plain squat, the lunge
    db.update_exercise(b, "Čučanj s vlastitom težinom", "", "", "kod kuće", {g})   # and back to the goblet
    page = ct.get(f"/treninzi/vjezbe/{g}").text
    assert "<legend>Zamjene za ovu vježbu</legend>" in page and "<legend>Slične vježbe</legend>" not in page
    assert ('<p class="hint">Polaznik smije odraditi označene vježbe umjesto ove. Da ova vježba zamijeni neku '
            'drugu, označi je na stranici te vježbe.</p>') in page
    assert alt_rows(page) == [(b, True, True), (i, True, False), (j, False, False)]  # Č s … before Č sk …
    assert ('Čučanj s vlastitom težinom <span class="tags">· kod kuće</span> '
            '<span class="alt-back">· u oba smjera</span></span></label>') in page       # after its tags
    assert 'aria-label="Filtriraj zamjene"' in page
    assert stands_line(page) == ("Zamjena je za: Čučanj s vlastitom težinom, Čučanj skok.",
                                 [(f"/treninzi/vjezbe/{b}", "Čučanj s vlastitom težinom"),
                                  (f"/treninzi/vjezbe/{j}", "Čučanj skok")])
    for href, name in stands_line(page)[1]:                                   # each its page
        assert f'<h1>{name}</h1>' in ct.get(href).text
    page = ct.get(f"/treninzi/vjezbe/{b}").text                               # the jump unticked: no tag
    assert alt_rows(page) == [(g, True, True), (j, False, False), (i, False, False)]
    assert stands_line(page)[0] == "Zamjena je za: Čučanj skok, Goblet čučanj."
    page = ct.get(f"/treninzi/vjezbe/{j}").text                               # stands in for none
    assert alt_rows(page) == [(b, True, False), (g, True, False), (i, False, False)]
    assert stands_line(page) is None and 'class="alt-back"' not in page
    page = ct.get(f"/treninzi/vjezbe/{i}").text                               # stands in for Goblet, ticks none
    assert alt_rows(page) == [(b, False, False), (j, False, False), (g, False, False)]
    assert stands_line(page) == ("Zamjena je za: Goblet čučanj.", [(f"/treninzi/vjezbe/{g}", "Goblet čučanj")])
    assert 'class="alt-back"' not in page
    page = ct.get("/treninzi/vjezbe/nova").text
    assert "<legend>Zamjene za ovu vježbu</legend>" in page and 'class="alt-back"' not in page
    assert stands_line(page) is None
    assert '<p class="hint">Upute, jedno ponavljanje, oznake i zamjene; video joj dodaješ kad je spremiš.</p>' in page
    assert [x for x, _, _ in alt_rows(page)] == [b, j, g, i]

    r = ct.post(f"/treninzi/vjezbe/{g}", data={"name": "Iskorak", "tags": "noge", "alternative": [str(j)]})
    assert r.status_code == 400 and "Vježba s tim imenom već postoji." in r.text
    assert alt_rows(r.text) == [(j, True, True), (b, False, False), (i, False, False)]   # j ticked, j -> g stored
    assert stands_line(r.text)[0] == "Zamjena je za: Čučanj s vlastitom težinom, Čučanj skok."
    assert pairs() == {(j, g), (j, b), (g, b), (g, i), (b, g)}                # nothing saved


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


def confirm_text(page: str) -> str:
    """What "Obriši vježbu" asks (its form's data-confirm), as read."""
    m = re.search(r'class="ex-delete"\s*data-confirm-title="Obrisati vježbu\?"\s*data-confirm="([^"]*)"\s*'
                  r'data-confirm-cta="Obriši vježbu">', page)
    return unescape(m.group(1))


def updated(pid: int):
    with db.engine.connect() as conn:
        return conn.execute(sa_text("SELECT updated_at FROM programs WHERE id = :p"), {"p": pid}).scalar_one()


def test_an_exercise_is_deleted_out_of_every_training_that_holds_it():
    """Held by programmes, an exercise is deleted all the same (4.11.2026):
    its confirm says so first, naming where it is (as the lead does, up to
    three, then "…"), and what stays; deleted, its items leave every day of
    every programme that held them, the days and the programmes stay (one
    emptied too: "Trening još nema vježbi."), the holding programmes'
    updated_at moves (another's not), its pairs and its clip go, and the
    library's flash says how many trainings it left ("treninga" for every
    N). One no training holds says "Vježba je obrisana."; one gone already,
    the same; an exercise deleted cannot be added to a day."""
    ct, ivan, _ = trainer_with_clients()
    eid = db.create_exercise("Goblet čučanj")
    other = db.create_exercise("Iskorak")
    plank = db.create_exercise("Plank")
    db.update_exercise(eid, "Goblet čučanj", "", "", "", {other})
    upload(ct, eid, "g.mp4", MP4)
    upload(ct, other, "i.mp4", MP4)
    clip, other_clip = db.exercise(eid).video, db.exercise(other).video
    progs = {t: db.create_program(t, None) for t in ("Donji dio tijela — srednja", "Core control",
                                                     "Cijelo tijelo — početna", "Bez nje")}
    progs["Zadnji"] = db.create_program("Zadnji", None, "pocetna", "cijelo")   # ivan's combination
    hold(progs["Core control"], plank)
    hold(progs["Core control"], eid)
    hold(progs["Core control"], eid, "zagrijavanje", day=2)                   # one programme, two of its days
    hold(progs["Donji dio tijela — srednja"], eid)
    hold(progs["Cijelo tijelo — početna"], eid, "istezanje")
    hold(progs["Zadnji"], eid)                                                # the day's only exercise
    hold(progs["Bez nje"], plank)
    page = ct.get(f"/treninzi/vjezbe/{eid}").text
    assert ('<p class="hint">U 4 programa: Cijelo tijelo — početna, Core control, Donji dio tijela — srednja, '
            'Zadnji (početna razina).</p>' in page)
    assert confirm_text(page) == ("„Goblet čučanj” se briše iz baze vježbi, s uputama i videom, i izlazi iz svakog "
                                  "treninga koji je drži (u 4 programa: Cijelo tijelo — početna, Core control, "
                                  "Donji dio tijela — srednja …). Treninzi ostaju bez nje; odrađeni treninzi u "
                                  "kartonima zadrže njezino ime.")
    with db.engine.begin() as conn:
        conn.execute(sa_text("UPDATE programs SET updated_at = '2026-01-01 12:00+01'"))
    before = updated(progs["Bez nje"])
    r = ct.post(f"/treninzi/vjezbe/{eid}/obrisi", follow_redirects=False)
    assert r.status_code == 303 and location(r) == "/treninzi/vjezbe?ok=Vježba je obrisana i maknuta iz 5 treninga."
    assert '<div class="alert ok" role="status">Vježba je obrisana i maknuta iz 5 treninga.</div>' in ct.get(
        r.headers["location"]).text
    assert db.exercise(eid) is None and not (config.MEDIA_DIR / clip).exists()
    assert pairs() == set() and db.exercise(other).alternatives == []
    assert [item_names(progs[t]) for t in ("Core control", "Donji dio tijela — srednja", "Cijelo tijelo — početna",
                                           "Zadnji", "Bez nje")] == [["Plank"], [], [], [], ["Plank"]]
    assert [len(db.get_program(progs[t]).days) for t in ("Core control", "Donji dio tijela — srednja",
                                                         "Cijelo tijelo — početna", "Zadnji")] == [2, 1, 1, 1]
    assert stored_counts() == (5, 6, 2, 2)
    assert all(updated(progs[t]) > before for t in progs if t != "Bez nje") and updated(progs["Bez nje"]) == before
    emptied = db.get_program(progs["Zadnji"]).days[0].id
    page = client_for("ivan@test.local").get(f"/treninzi/{progs['Zadnji']}/dan/{emptied}").text
    assert '<p class="hint" style="margin-top:22px;">Trening još nema vježbi.</p>' in page
    assert db.add_day_item(emptied, eid, "trening") is None and stored_counts() == (5, 6, 2, 2)

    assert db.delete_exercise(eid) is None                                  # gone already: nothing to do
    r = ct.post(f"/treninzi/vjezbe/{eid}/obrisi", follow_redirects=False)
    assert location(r) == "/treninzi/vjezbe?ok=Vježba je obrisana."
    assert "Još nije ni u jednom programu." in (page := ct.get(f"/treninzi/vjezbe/{other}").text)
    assert confirm_text(page) == "„Iskorak” se briše iz baze vježbi, s uputama i videom."
    r = ct.post(f"/treninzi/vjezbe/{other}/obrisi", follow_redirects=False)  # none held it
    assert location(r) == "/treninzi/vjezbe?ok=Vježba je obrisana."
    assert db.exercise(other) is None and not (config.MEDIA_DIR / other_clip).exists()
    assert db.delete_exercise(plank) == (None, 2)                           # no clip; two days, two programmes
    assert stored_counts() == (5, 6, 0, 0) and [d.items for d in db.get_program(progs["Bez nje"]).days] == [[]]


def lock_waiters() -> int:
    """How many client connections to the test database wait on a lock now,
    asked afresh (one transaction would see one snapshot of the activity)."""
    with db.engine.connect() as conn:
        return conn.execute(sa_text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                                    "AND backend_type = 'client backend' AND wait_event_type = 'Lock'")).scalar_one()


def a_lock_waiter() -> int:
    """Wait (5 s at most) until a connection waits on a lock; how many do."""
    for _ in range(100):
        if lock_waiters():
            break
        time.sleep(0.05)
    return lock_waiters()


def test_an_exercise_added_while_it_is_deleted_is_not_added():
    """delete_exercise takes the exercise's row, then the rows of the
    programmes that hold it; add_day_item takes the exercise's row (FOR KEY
    SHARE, the foreign key's own lock) before the programme's. So the two
    never wait on each other in a circle: here a delete holds the exercise
    (as delete_exercise does first) while an add into a programme that
    holds it starts and waits; the delete then takes the programme (as
    delete_exercise does next) at once and deletes, and the add finds the
    exercise gone and adds nothing. (Programme first, as add_day_item took
    them until 4.11.2026, the add held the programme while it waited on the
    exercise, and the delete's turn for the programme closed the circle: a
    deadlock.)"""
    trainer_with_clients()
    eid = db.create_exercise("Bird dog")
    pid = db.create_program("Core control", None)
    hold(pid, eid)
    second = db.add_day(pid)
    got, errors = [], []

    def add():
        try:
            got.append(db.add_day_item(second, eid, "trening"))
        except Exception as e:                                              # pragma: no cover - reported below
            errors.append(e)

    conn = db.engine.connect()
    adding = threading.Thread(target=add)
    try:
        conn.execute(sa_text("SET LOCAL lock_timeout = '5s'"))             # this transaction's: never the pool's
        conn.execute(sa_text("SELECT id FROM exercises WHERE id = :e FOR UPDATE"), {"e": eid})
        adding.start()
        assert a_lock_waiter() == 1                                         # the add waits on the exercise
        conn.execute(sa_text("SELECT id FROM programs WHERE id = :p FOR UPDATE"), {"p": pid})
        conn.execute(sa_text("DELETE FROM exercises WHERE id = :e"), {"e": eid})
        conn.commit()
    finally:
        conn.close()
        adding.join(timeout=10)
    assert not errors and got == [None]
    assert stored_counts() == (1, 2, 0, 0) and [d.items for d in db.get_program(pid).days] == [[], []]


def test_an_exercise_saved_while_it_is_deleted_never_deadlocks(monkeypatch):
    """update_exercise and delete_exercise on one exercise at once (two
    threads): each takes the table's lock first (_EXERCISES_LOCK), so one
    waits for the other whole. Here the save holds the lock and is about to
    write the row when the delete starts: the delete waits on the lock,
    holding nothing of the row; the save writes and commits (True), and the
    delete then deletes the row as saved, out of its one day ((None, 1)).
    (Row first, as delete_exercise took it until 4.11.2026, the delete held
    the row the save was about to write and waited on the table the save
    held: a deadlock.)"""
    trainer_with_clients()
    eid = db.create_exercise("Bird dog")
    hold(db.create_program("Core control", None), eid)
    original, holding, got, errors = db._set_alternatives, threading.Event(), {}, []

    def paused(s, exercise_id, wanted):
        holding.set()                                                       # the save holds the table's lock
        a_lock_waiter()                                                     # until the delete waits on a lock
        return original(s, exercise_id, wanted)                             # its first query writes the row

    monkeypatch.setattr(db, "_set_alternatives", paused)

    def run(key: str, call) -> None:
        try:
            got[key] = call()
        except Exception as e:                                              # pragma: no cover - reported below
            errors.append(e)

    saving = threading.Thread(target=run, args=("save", lambda: db.update_exercise(eid, "Bird dog 2", "", "", "")))
    deleting = threading.Thread(target=run, args=("delete", lambda: db.delete_exercise(eid)))
    saving.start()
    assert holding.wait(5)
    deleting.start()
    saving.join(15)
    deleting.join(15)
    assert not errors, errors
    assert got == {"save": True, "delete": (None, 1)}
    assert db.exercise(eid) is None and stored_counts() == (1, 1, 0, 0)


def test_a_clip_saved_while_its_exercise_is_deleted_waits_its_turn():
    """set_exercise_video takes the table's lock first, as delete_exercise
    does (4.11.2026): while a delete holds it, the clip's save waits holding
    nothing of the exercise's row, so the delete takes the row at once
    (NOWAIT) and deletes it, and the save then finds the exercise gone
    (LookupError: the route deletes the file it stored). (Row first, the
    save would hold the row the delete waits on and wait for its UPDATE on
    the table the delete holds: a deadlock.)"""
    eid = db.create_exercise("Bird dog")
    got = []

    def save():
        try:
            got.append(db.set_exercise_video(eid, "vjezba-x.mp4"))
        except Exception as e:
            got.append(e)

    conn = db.engine.connect()
    saving = threading.Thread(target=save)
    try:
        conn.execute(sa_text("SET LOCAL lock_timeout = '5s'"))             # this transaction's: never the pool's
        conn.execute(sa_text(db._EXERCISES_LOCK))                           # as delete_exercise does first
        saving.start()
        assert a_lock_waiter() == 1                                         # the save waits on the table
        conn.execute(sa_text("SELECT id FROM exercises WHERE id = :e FOR UPDATE NOWAIT"), {"e": eid})
        conn.execute(sa_text("DELETE FROM exercises WHERE id = :e"), {"e": eid})
        conn.commit()
    finally:
        conn.close()
        saving.join(timeout=10)
    assert len(got) == 1 and isinstance(got[0], LookupError) and db.exercise(eid) is None


def test_a_programme_is_named_with_its_razina_on_the_library_pages():
    """Programmes may share a title, one per razina (the owner, 30.10.2026:
    three live "Booty build"s, and "U 17 programa: …, Booty build, …" sent
    him to the wrong one): the exercise's page and its delete's confirm
    name a programme that has a razina by its title and the razina's label,
    lower-cased, "Booty build (napredna razina)", in the alphabet's order;
    one without a razina is its title. The confirm names three, then "…";
    one programme is "u 1 programu"."""
    ct, *_ = trainer_with_clients()
    eid = db.create_exercise("Plank")
    for level in ("pocetna", "srednja", "napredna"):
        hold(db.create_program("Booty build", None, level, "donji"), eid)
    hold(db.create_program("Core control", None), eid)
    names = ["Booty build (napredna razina)", "Booty build (početna razina)", "Booty build (srednja razina)", "Core control"]
    assert [db.program_name(p) for p in db.exercise_programs(eid)] == names
    page = ct.get(f"/treninzi/vjezbe/{eid}").text
    assert f'<p class="hint">U 4 programa: {", ".join(names)}.</p>' in page
    assert ("(u 4 programa: Booty build (napredna razina), Booty build (početna razina), "
            "Booty build (srednja razina) …). Treninzi ostaju bez nje;") in confirm_text(page)
    one = db.create_exercise("Bird dog")
    hold(db.create_program("Core control", None, "srednja", "cijelo"), one)
    page = ct.get(f"/treninzi/vjezbe/{one}").text
    assert '<p class="hint">U 1 programu: Core control (srednja razina).</p>' in page
    assert confirm_text(page) == ("„Bird dog” se briše iz baze vježbi, s uputama i videom, i izlazi iz svakog "
                                  "treninga koji je drži (u 1 programu: Core control (srednja razina)). Treninzi "
                                  "ostaju bez nje; odrađeni treninzi u kartonima zadrže njezino ime.")


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
    assert 'data-confirm="Video vježbe „Plank” bit će obrisan. Upute, oznake i zamjene ostaju."' in page
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
    """"+ Dodaj trening" makes a day after the last (Trening 1, 2, 3) and
    opens its editor. Its form saves a title (one line, its spaces single), a
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
    assert [(d.id, d.position, d.label) for d in db.get_program(pid).days] == [
        (d1, 1, "Trening 1"), (d2, 2, "Trening 2"), (d3, 3, "Trening 3")]
    assert ct.post("/treninzi/987654/dani").status_code == 404

    edit = f"/treninzi/{pid}/dan/{d2}/uredi"
    r = ct.post(f"/treninzi/{pid}/dan/{d2}", data={"title": "  Gornji   dio ", "weekday": "3",
                                                    "intro": "  Lagano.\n\n\n\nPolako.  "}, follow_redirects=False)
    assert location(r) == f"{edit}?ok=Spremljeno."
    day = db.get_day(d2)
    assert (day.title, day.weekday, day.intro, day.label) == ("Gornji dio", 3, "Lagano.\n\nPolako.", "Trening 2 · Gornji dio")
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
    assert db.get_day(d2).label == "Trening 3 · Gornji dio"
    assert not db.move_day(d1, "gore") and not db.move_day(d2, "dolje") and not db.move_day(d1, "x")
    assert not db.move_day(987654, "gore")
    assert db.move_day(d1, "dolje")
    assert [d.id for d in db.get_program(pid).days] == [d3, d1, d2]

    eid = db.create_exercise("Plank")
    db.add_day_item(d1, eid, "trening")
    r = ct.post(f"/treninzi/{pid}/dan/{d1}/obrisi", follow_redirects=False)
    assert location(r) == f"/treninzi/{pid}/uredi?ok=Trening je obrisan."
    assert [(d.id, d.position) for d in db.get_program(pid).days] == [(d3, 1), (d2, 2)]
    assert db.get_day(d1) is None and db.exercise(eid) is not None and db.exercises()[0][1] == 0
    assert db.delete_day(d1) is None                                        # gone already


def test_days_are_numbered_once_when_adds_race():
    """Eight "+ Dodaj trening" at once: the programme's row is locked while
    the next number is read, so the eight days are Trening 1 … Trening 8."""
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
                ({"section": "kardio"}, "Odaberi dio treninga.")]
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
    """"Uredi program": its lead says what a programme is now; under
    "Treninzi" a row per day: its label (a link to its editor),
    "ponedjeljak · 2 vježbe" muted, Uredi, ↑ / ↓ (disabled at the ends) and
    ✕, which asks first; "+ Dodaj trening" under them. No exercise list,
    picker or dose hint any more."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    page = ct.get(f"/treninzi/{pid}/uredi").text
    assert "<h1>Uredi program</h1>" in page and '<h2 style="font-size:1.05rem; margin-bottom:12px;">Treninzi</h2>' in page
    assert ('Program ima treninge; svaki trening ima zagrijavanje, glavni dio i istezanje, a vježbe biraš iz '
            '<a class="tlink" href="/treninzi/vjezbe">baze vježbi</a>.') in page
    assert f'<a class="act act-quiet" href="/treninzi/{pid}">pogledaj kako polaznik vidi →</a>' in page
    assert '<p class="hint">Program još nema treninga — dodaj prvi.</p>' in page
    assert (f'<form method="post" action="/treninzi/{pid}/dani" class="days-add">\n'
            '  <button type="submit" class="btn btn-sm">+ Dodaj trening</button>') in page
    d1, d2 = db.add_day(pid), db.add_day(pid)
    db.update_day(d1, "Cijelo tijelo", 0, "")
    for n in ("Plank", "Sklekovi"):
        hold(pid, db.create_exercise(n))
    page = ct.get(f"/treninzi/{pid}/uredi").text
    assert "Program još nema treninga" not in page
    rows = page.split('<div class="card it-row" id="dan-')[1:]
    assert [r.split('"')[0] for r in rows] == [str(d1), str(d2)]
    found = [re.search(r'<a class="it-name" href="([^"]+)">([^<]*)</a>\s*<span class="it-note">([^<]*)</span>', r).groups()
             for r in rows]
    assert found == [(f"/treninzi/{pid}/dan/{d1}/uredi", "Trening 1 · Cijelo tijelo", "ponedjeljak · 2 vježbe"),
                     (f"/treninzi/{pid}/dan/{d2}/uredi", "Trening 2", "0 vježbi")]
    assert f'<a class="btn btn-quiet btn-sm" href="/treninzi/{pid}/dan/{d1}/uredi">Uredi</a>' in rows[0]
    assert re.search(r'disabled style="opacity:.35;"\s+aria-label="Pomakni gore: Trening 1 · Cijelo tijelo"', rows[0])
    assert re.search(r'<button class="btn-ghost btn-sm" \s+aria-label="Pomakni dolje: Trening 1 · Cijelo tijelo"', rows[0])
    assert re.search(r'disabled style="opacity:.35;"\s+aria-label="Pomakni dolje: Trening 2"', rows[1])
    assert (f'action="/treninzi/{pid}/dan/{d1}/obrisi" style="margin:0; display:inline;"\n'
            '              data-confirm-title="Obrisati trening?"\n'
            '              data-confirm="„Trening 1 · Cijelo tijelo” se briše s popisom vježbi; same vježbe ostaju u bazi vježbi."\n'
            '              data-confirm-cta="Obriši trening">\n'
            '          <button class="btn-ghost btn-sm" aria-label="Obriši trening: Trening 1 · Cijelo tijelo">✕</button>') in rows[0]
    assert 'id="dodaj"' not in page and 'name="exercise_id"' not in page and "Doza uz naziv" not in page


def test_the_day_editor_shows_each_row_and_its_form():
    """The day editor: crumbs to the programme's editor, "Trening N" (its
    <title> too), the lead with the way to the client's page, the day's
    form, the intro video's card, then every section's caption with its
    rows ("Nema vježbi." when it has none): the exercise's name (a link to
    it), whether it has a clip, ↑ / ↓ / ✕ naming forms that stand after
    the list, and the row's own form, its values in it. "Obriši trening"
    at the bottom asks first."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    goblet, plank = db.create_exercise("Goblet čučanj"), db.create_exercise("Plank")
    upload(ct, plank, "p.mp4", MP4)
    ig, ip = hold(pid, goblet), hold(pid, plank)
    db.update_day_item(ig, "trening", 4, 10, None, 60, 90, "16 kg")
    db.update_day_item(ip, "trening", 3, None, 40, None, None, "")
    page = ct.get(f"/treninzi/{pid}/dan/{did}/uredi").text
    assert (f'<nav class="crumbs" aria-label="Putanja"><a href="/treninzi">Treninzi</a><span class="sep">/</span>'
            f'<a href="/treninzi/{pid}/uredi">Cijelo tijelo — početna</a><span class="sep">/</span>'
            '<span class="here">Trening 1</span></nav>\n<h1>Trening 1</h1>') in page
    assert "<title>Uredi: Trening 1 — Cijelo tijelo — početna — QMT</title>" in page
    assert ("Naslov, preporučeni dan u tjednu i uvod; ispod toga vježbe po dijelovima — serije, ponavljanja ili "
            "sekunde, odmor i napomena.") in page
    assert ("„Odmor (s)” je odmor između serija, a „Nakon vježbe (s)” odmor prije sljedeće vježbe: polaznik za oba "
            "dobiva odbrojavanje koje može preskočiti.") in page
    assert f'<a class="act act-quiet" href="/treninzi/{pid}/dan/{did}">pogledaj kako polaznik vidi →</a>' in page
    assert 'placeholder="npr. Cijelo tijelo"' in page and "Kratko objašnjenje treninga — polaznik ga gleda prije prve vježbe." in page
    assert re.findall(r'<h3 class="st-cap" id="dio-(\w+)">([^<]*)</h3>', page) == [
        ("zagrijavanje", "Zagrijavanje"), ("trening", "Glavni dio"), ("istezanje", "Istezanje")]
    assert page.count('<p class="hint st-none">Nema vježbi.</p>') == 2
    rows = page.split('<div class="card it-row" id="stavka-')[1:]
    assert [r.split('"')[0] for r in rows] == [str(ig), str(ip)]
    assert f'<a class="it-name" href="/treninzi/vjezbe/{goblet}">Goblet čučanj</a>' in rows[0]
    assert '<span class="it-video">bez videa</span>' in rows[0] and '<span class="it-video has">video ✓</span>' in rows[1]
    assert re.search(rf'form="st-gore-{ig}" class="btn-ghost btn-sm"\s+disabled', rows[0])
    assert re.search(rf'form="st-dolje-{ig}" class="btn-ghost btn-sm"\s+aria-label="Pomakni dolje: Goblet čučanj"', rows[0])
    assert re.search(rf'form="st-dolje-{ip}" class="btn-ghost btn-sm"\s+disabled', rows[1])
    assert f'form="st-x-{ig}" class="btn-ghost btn-sm" aria-label="Makni iz treninga: Goblet čučanj">✕</button>' in rows[0]
    form = rows[0].split('<form class="st-form"')[1].split("</form>")[0]
    assert f'action="/treninzi/{pid}/dan/{did}/stavke/{ig}"' in form
    assert '<option value="trening" selected>Glavni dio</option>' in form and '<option value="zagrijavanje">Zagrijavanje</option>' in form
    values = dict(re.findall(r'name="(\w+)"[^>]*?value="([^"]*)"', form))
    assert values == {"sets": "4", "reps": "10", "seconds": "", "rest": "60", "rest_after": "90", "note": "16 kg"}
    assert 'name="sets" inputmode="numeric" min="1" max="99"' in form and 'name="reps" inputmode="numeric" min="1" max="999"' in form
    assert 'name="seconds" inputmode="numeric" min="1" max="3600"' in form and 'name="rest" inputmode="numeric" min="0" max="3600"' in form
    assert 'name="rest_after" inputmode="numeric" min="0" max="3600"' in form
    assert [lab for lab in re.findall(r'<label for="st-\d+-\w+">([^<]*)</label>', form)] == [
        "Dio", "Serije", "Ponavljanja", "Sekunde", "Odmor (s)", "Nakon vježbe (s)", "Napomena"]
    second = rows[1].split('<form class="st-form"')[1].split("</form>")[0]          # none set: an empty field
    assert dict(re.findall(r'name="(\w+)"[^>]*?value="([^"]*)"', second))["rest_after"] == ""
    after = page.split('<h2 style="font-size:1.05rem; margin:30px 0 12px;">Dodaj vježbu</h2>')[0].split("</section>")[-1]
    assert (f'<form id="st-x-{ig}" method="post" action="/treninzi/{pid}/dan/{did}/stavke/{ig}/obrisi"\n'
            '      data-confirm-title="Maknuti vježbu iz treninga?"\n'
            '      data-confirm="„Goblet čučanj” izlazi iz ovog treninga; u bazi vježbi ostaje."\n'
            '      data-confirm-cta="Makni"></form>') in after
    assert f'<form id="st-gore-{ip}" method="post" action="/treninzi/{pid}/dan/{did}/stavke/{ip}/pomak"><input type="hidden" name="smjer" value="gore"></form>' in after
    assert ('data-confirm-title="Obrisati trening?"\n'
            '      data-confirm="„Trening 1” se briše s popisom vježbi; same vježbe ostaju u bazi vježbi."\n'
            '      data-confirm-cta="Obriši trening">\n'
            '  <button type="submit" class="btn-ghost">Obriši trening</button>') in page


def test_the_day_editors_picker_adds_into_the_chosen_section():
    """"Dodaj vježbu" is a select of the library (name · tags, the
    alphabet's order) and a select of the section, opening on Glavni dio,
    then Dodaj and "Nova vježba →" (back to this day's editor); the
    exercise goes into the chosen section, pointing at the library row. An
    empty library says so, with the way to make one."""
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
    assert sections == [("zagrijavanje", "", "Zagrijavanje"), ("trening", " selected", "Glavni dio"), ("istezanje", "", "Istezanje")]
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
    exercises it holds ("1 vježba", "2 vježbe", "5 vježbi"); none: "Program
    još nema treninga." (the trainer: "… — dodaj prvi u uređivanju.", and
    "Uredi program"). The client's list says how many days a programme has
    ("1 trening", "2 treninga", "3 treninga")."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("Tjedan 1", "Uvod u program.", "pocetna", "cijelo")
    ci = client_for("ivan@test.local")
    page = ci.get(f"/treninzi/{pid}").text
    assert '<p class="hint" style="margin-bottom:6px;">0 treninga</p>' in page
    assert '<p class="hint">Program još nema treninga.</p>' in page and "dodaj prvi" not in page
    trainers = ct.get(f"/treninzi/{pid}").text
    assert '<p class="hint">Program još nema treninga — dodaj prvi u uređivanju.</p>' in trainers
    assert f'<a class="btn btn-quiet btn-sm" href="/treninzi/{pid}/uredi">Uredi program</a>' in trainers
    d1, d2, d3 = db.add_day(pid), db.add_day(pid), db.add_day(pid)
    db.update_day(d1, "Cijelo tijelo", 0, "")
    db.update_day(d3, "", 4, "")
    exercises = [db.create_exercise(f"Vježba {n}") for n in range(8)]
    for n, eid in enumerate(exercises):
        hold(pid, eid, day=1 if n < 2 else 2 if n < 3 else 3)
    page = ci.get(f"/treninzi/{pid}").text
    assert '<p class="hint" style="margin-bottom:6px;">3 treninga</p>' in page
    cards = re.findall(r'<a class="card day-card" href="([^"]+)">\s*<span class="dc-main">\s*<strong>([^<]*)</strong>\s*'
                       r'<span class="hint">([^<]*)</span>', page)
    assert cards == [(f"/treninzi/{pid}/dan/{d1}", "Trening 1 · Cijelo tijelo", "Preporučeno: ponedjeljak · 2 vježbe"),
                     (f"/treninzi/{pid}/dan/{d2}", "Trening 2", "1 vježba"),
                     (f"/treninzi/{pid}/dan/{d3}", "Trening 3", "Preporučeno: petak · 5 vježbi")]
    assert "Uvod u program." in page and "Uredi program" not in page and "Program još nema treninga" not in page
    assert '<div class="hint">3 treninga · Uvod u program.</div>' in ci.get("/treninzi").text
    db.delete_day(d3)
    assert '<div class="hint">2 treninga · Uvod u program.</div>' in ci.get("/treninzi").text
    db.delete_day(d2)
    assert '<div class="hint">1 trening · Uvod u program.</div>' in ci.get("/treninzi").text


def test_the_day_page_prints_the_whole_list():
    """A day's page: crumbs, its label, "Preporučeno: ponedjeljak · 3
    vježbe", its intro; then each section that holds an exercise under its
    caption, in the sections' order, and each exercise a <details> row:
    "Vježba n" counted across the day, the name, the dose, the rest line and
    the note; open, its clip (preload none) or "Vježba još nema videa.",
    what one rep is and how it is done. The trainer gets "Uredi trening"."""
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
    db.update_day_item(i1, "trening", 3, None, 40, 45, None, "")
    i2 = hold(pid, goblet, "zagrijavanje")
    db.update_day_item(i2, "zagrijavanje", 2, 15, None, 30, None, "8 kg")
    i3 = hold(pid, stretch, "istezanje")
    db.update_day_item(i3, "istezanje", None, None, 30, None, None, "po nozi")
    ci = client_for("ivan@test.local")
    page = ci.get(f"/treninzi/{pid}/dan/{did}").text
    assert (f'<a href="/treninzi">Treninzi</a><span class="sep">/</span><a href="/treninzi/{pid}">Tjedan 1</a>'
            '<span class="sep">/</span><span class="here">Trening 1</span></nav>\n<h1>Trening 1 · Cijelo tijelo</h1>') in page
    assert '<p class="hint">Preporučeno: ponedjeljak · 3 vježbe</p>' in page
    assert '<p class="day-intro">Lagano.\nBez žurbe.</p>' in page and "Uredi trening" not in page
    assert "<title>Trening 1 · Cijelo tijelo — Tjedan 1 — QMT</title>" in page
    assert re.findall(r'<h2 class="dx-cap" id="dio-(\w+)">([^<]*)</h2>', page) == [
        ("zagrijavanje", "Zagrijavanje"), ("trening", "Glavni dio"), ("istezanje", "Istezanje")]
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
    assert (f'<a class="btn btn-quiet btn-sm" href="/treninzi/{pid}/dan/{did}/uredi">Uredi trening</a>'
            in ct.get(f"/treninzi/{pid}/dan/{did}").text)

    db.delete_day_item(i3)                                                  # a section with none is not on the page
    db.update_day_item(i2, "zagrijavanje", None, None, None, None, None, "")   # nothing set: no dose, no line
    page = ci.get(f"/treninzi/{pid}/dan/{did}").text
    assert [k for k, _ in re.findall(r'<h2 class="dx-cap" id="dio-(\w+)">([^<]*)</h2>', page)] == ["zagrijavanje", "trening"]
    first = page.split('<details class="card ex">')[1].split("</summary>")[0]
    assert 'class="dx-dose"' not in first and 'class="dx-sub"' not in first
    db.update_day(did, "", None, "")
    page = ci.get(f"/treninzi/{pid}/dan/{did}").text
    assert "<h1>Trening 1</h1>" in page and '<p class="hint">2 vježbe</p>' in page and '<p class="day-intro">' not in page

    empty = db.add_day(pid)
    page = ci.get(f"/treninzi/{pid}/dan/{empty}").text
    assert '<p class="hint">0 vježbi</p>' in page and "Trening još nema vježbi." in page and '<h2 class="dx-cap"' not in page
    assert "Trening još nema vježbi — dodaj ih u uređivanju." in ct.get(f"/treninzi/{pid}/dan/{empty}").text


def test_the_rest_after_an_exercise_is_saved_refused_and_shown():
    """30.10.2026, the player's rest timers: a row's "Nakon vježbe (s)"
    (rest_after, 0–3600, empty is none) is the rest after the exercise,
    before the next one. Saved as the others; refused out of range or not
    a number ("Neispravan broj.", the row unchanged). The item words it as
    it words the rest between sets ("90 s"), and the day page's muted line
    prints it after that one: "Odmor između serija: 60 s · Odmor nakon
    vježbe: 90 s · 8 kg", each part only when set; with none, nothing of
    it."""
    assert [ProgramDayItem(rest_after_seconds=r).rest_after_text for r in (90, 0, None)] == ["90 s", "0 s", ""]
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    ig, ip = hold(pid, db.create_exercise("Goblet čučanj")), hold(pid, db.create_exercise("Plank"))
    base = f"/treninzi/{pid}/dan/{db.get_program(pid).days[0].id}"

    def save(item_id, **fields):
        data = {"section": "trening", "sets": "3", "reps": "10", "seconds": "", "rest": "60", "rest_after": "",
                "note": "8 kg"} | fields
        return ct.post(f"{base}/stavke/{item_id}", data=data, follow_redirects=False)

    def rests(item_id):
        it = db.get_day_item(item_id)
        return it.rest_seconds, it.rest_after_seconds

    def lines() -> list[str]:
        return re.findall(r'<span class="dx-sub">([^<]*)</span>', client_for("ivan@test.local").get(base).text)

    assert location(save(ig, rest_after="90")) == f"{base}/uredi?ok=Spremljeno.&stavka={ig}#stavka-{ig}"
    assert rests(ig) == (60, 90)
    for bad in ("3601", "-1", "abc", "1.5", "²", "90 s"):
        r = save(ig, rest_after=bad)
        assert location(r) == f"{base}/uredi?error=Neispravan broj.&stavka={ig}#stavka-{ig}", bad
    assert rests(ig) == (60, 90)
    with pytest.raises(ValueError, match="Neispravan broj."):
        db.update_day_item(ig, "trening", 3, 10, None, 60, 3601, "")
    for value, kept in (("0", 0), ("3600", 3600), ("", None)):
        save(ip, reps="", seconds="40", rest="", rest_after=value, note="")
        assert rests(ip) == (None, kept), value
    assert lines() == ["Odmor između serija: 60 s · Odmor nakon vježbe: 90 s · 8 kg"]   # Plank: nothing set, no line
    save(ig, rest="", note="", rest_after="90")
    save(ip, reps="", seconds="40", rest="45", note="po strani", rest_after="")
    assert lines() == ["Odmor nakon vježbe: 90 s", "Odmor između serija: 45 s · po strani"]
    save(ig)                                                                # emptied: none, nothing of it
    assert lines() == ["Odmor između serija: 60 s · 8 kg", "Odmor između serija: 45 s · po strani"]


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
# 4f9d6f7103ad, the rest after an exercise, and 45c543c860f3, the items' key to
# their exercise CASCADE (4.11.2026): a test that builds program_day_items with
# 7c3bf996c983 runs them on top, so the table is the model's again
REST_AFTER = "4f9d6f7103ad_program_day_items_rest_after.py"
CASCADE = "45c543c860f3_program_day_items_exercise_cascade.py"


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
    top makes the items days (and 4f9d6f7103ad gives them the rest after an
    exercise), and every table is the models'."""
    mig = _migration("4c2e8a6f1d39_exercise_library.py")
    assert (mig.revision, mig.down_revision) == ("4c2e8a6f1d39", "b18ebed39701")
    with db.engine.begin() as conn:                                         # the tables as before the revision
        # (workout_logs, 3890252ee50f's, points at program_days: it goes first)
        conn.execute(sa_text("DROP TABLE workout_logs, program_day_items, program_days, exercise_alternatives, exercises"))
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
    _run(_migration(REST_AFTER).upgrade)                                     # and their rest after an exercise
    _run(_migration(CASCADE).upgrade)                                        # and their key to it, CASCADE
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
    folds them again. (4f9d6f7103ad follows each upgrade: the items' rest
    after an exercise, a later column the models have; and 45c543c860f3,
    their key to the exercise CASCADE, as the models have it.)"""
    mig = _migration("7c3bf996c983_program_days.py")
    rest_after, cascade = _migration(REST_AFTER), _migration(CASCADE)
    assert (mig.revision, mig.down_revision) == ("7c3bf996c983", "4c2e8a6f1d39")
    with db.engine.begin() as conn:                                         # the tables as before the revision
        # (workout_logs, 3890252ee50f's, points at program_days: it goes first)
        conn.execute(sa_text("DROP TABLE workout_logs, program_day_items, program_days"))
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
    _run(rest_after.upgrade)
    _run(cascade.upgrade)
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
    db.update_day_item(warm, "zagrijavanje", 2, None, None, None, None, "")
    stretch = db.add_day_item(second, ids[1], "istezanje")
    db.update_day_item(stretch, "istezanje", 2, None, 30, None, None, "po nozi")
    reps = db.add_day_item(second, ids[2], "zagrijavanje")
    db.update_day_item(reps, "zagrijavanje", None, 10, None, 30, None, "")
    _run(mig.downgrade)
    assert not {"program_days", "program_day_items"} & _tables()
    back = ["2 serije", "3 × 8 · 8 kg", "3 × 20 s", "3 × 5 · s koljena", "3 × 6 · po nozi", "3 × 10 · 2 × 6 kg", "",
            "Tempo 3-1-1", "10 ponavljanja", "2 × 30 s · po nozi"]
    exercises = [ids[0], *ids, ids[2], ids[1]]
    assert _flat_items() == [(p1, n, eid, note) for n, (eid, note) in enumerate(zip(exercises, back), start=1)]
    _run(mig.upgrade)
    _run(rest_after.upgrade)
    _run(cascade.upgrade)
    assert capsys.readouterr().out.endswith("Dan 1 with 10 exercises\n")
    assert "program_items" not in _tables() and _schema_diffs(TRENINZI) == []
    assert [(i.exercise_id, i.section, i.sets, i.reps, i.seconds, i.note) for i in items_of(p1)][:3] == [
        (ids[0], "trening", None, None, None, "2 serije"), (ids[0], "trening", 3, 8, None, "8 kg"),
        (ids[1], "trening", 3, None, 20, "")]


def test_the_rest_after_migration_adds_the_column_and_takes_it_away():
    """4f9d6f7103ad, run on qmt_test as before it (program_day_items without
    rest_after_seconds, an item in it with its rest between sets): the
    column as the model has it, the item already there with none (no rest
    after it until Amir types one), the rest of the row as it was;
    downgrade drops the column, the item staying, and a second upgrade adds
    it again."""
    mig = _migration(REST_AFTER)
    assert (mig.revision, mig.down_revision) == ("4f9d6f7103ad", "3890252ee50f")
    pid = db.create_program("T", None, "pocetna", "cijelo")
    iid = hold(pid, db.create_exercise("Plank"))
    db.update_day_item(iid, "trening", 3, None, 40, 60, 90, "po strani")
    with db.engine.begin() as conn:                                         # the table as before the revision
        conn.execute(sa_text("ALTER TABLE program_day_items DROP COLUMN rest_after_seconds"))
    _run(mig.upgrade)
    assert _schema_diffs(TRENINZI) == []
    it = db.get_day_item(iid)
    assert (it.sets, it.seconds, it.rest_seconds, it.rest_after_seconds, it.note) == (3, 40, 60, None, "po strani")
    db.update_day_item(iid, "trening", 3, None, 40, 60, 90, "po strani")
    assert db.get_day_item(iid).rest_after_seconds == 90
    _run(mig.downgrade)
    assert "rest_after_seconds" not in {c["name"] for c in sa_inspect(db.engine).get_columns("program_day_items")}
    with db.engine.connect() as conn:
        assert conn.execute(sa_text("SELECT sets, seconds, rest_seconds, note FROM program_day_items WHERE id = :i"),
                            {"i": iid}).one() == (3, 40, 60, "po strani")
    _run(mig.upgrade)
    assert _schema_diffs(TRENINZI) == [] and db.get_day_item(iid).rest_after_seconds is None


def _exercise_rule() -> str | None:
    """The ON DELETE rule of the items' key to their exercise, as the
    database reports it (the key's name and target checked on the way)."""
    [fk] = [f for f in sa_inspect(db.engine).get_foreign_keys("program_day_items")
            if f["constrained_columns"] == ["exercise_id"]]
    assert (fk["name"], fk["referred_table"], fk["referred_columns"]) == (
        "program_day_items_exercise_id_fkey", "exercises", ["id"])
    return fk["options"].get("ondelete")


def _delete_refused(eid: int) -> bool:
    """Does the database refuse a plain DELETE of the exercise (RESTRICT)?
    When it does not, the exercise is gone."""
    try:
        with db.engine.begin() as conn:
            conn.execute(sa_text("DELETE FROM exercises WHERE id = :e"), {"e": eid})
    except IntegrityError:
        return True
    return False


def test_the_cascade_migration_lets_an_exercise_go_with_its_items_and_back():
    """45c543c860f3, run on qmt_test as before it (the items' key to their
    exercise ON DELETE RESTRICT: a plain delete of an exercise a day holds
    is refused): the key is CASCADE, its name kept, the tables the models'
    and the items as they were; downgrade puts RESTRICT back (refused
    again), and a second upgrade CASCADE, under which deleting the exercise
    takes its item and leaves the day and its other item."""
    mig = _migration(CASCADE)
    assert (mig.revision, mig.down_revision) == ("45c543c860f3", "b61e8d5bf1db")
    pid = db.create_program("T", None, "pocetna", "cijelo")
    eid, keep = db.create_exercise("Bird dog"), db.create_exercise("Plank")
    gone, stays = hold(pid, eid), hold(pid, keep)
    with db.engine.begin() as conn:                                         # the key as before the revision
        conn.execute(sa_text("ALTER TABLE program_day_items DROP CONSTRAINT program_day_items_exercise_id_fkey, "
                             "ADD CONSTRAINT program_day_items_exercise_id_fkey FOREIGN KEY (exercise_id) "
                             "REFERENCES exercises (id) ON DELETE RESTRICT"))
    assert _exercise_rule() == "RESTRICT" and _schema_diffs(TRENINZI) != [] and _delete_refused(eid)
    _run(mig.upgrade)
    assert _exercise_rule() == "CASCADE" and _schema_diffs(TRENINZI) == []
    assert [i.id for i in items_of(pid)] == [gone, stays]
    _run(mig.downgrade)
    assert _exercise_rule() == "RESTRICT" and _delete_refused(eid)
    assert [i.id for i in items_of(pid)] == [gone, stays]
    _run(mig.upgrade)
    assert _exercise_rule() == "CASCADE" and _schema_diffs(TRENINZI) == []
    assert not _delete_refused(eid) and db.exercise(eid) is None
    assert [i.id for i in items_of(pid)] == [stays] and len(db.get_program(pid).days) == 1


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
    ("+ Dodaj trening", which opens its editor), adds "Goblet čučanj" into
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
        check(pg.is_visible("text=Program još nema treninga — dodaj prvi."), "the empty editor says nothing")
        check(pg.evaluate(OVERFLOW) == 0, f"the programme's editor overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap("form.days-add button")
        pg.wait_for_load_state("networkidle")
        days = db.get_program(pid).days
        did = days[0].id if days else 0
        check(len(days) == 1 and pg.url == f"{server}/treninzi/{pid}/dan/{did}/uredi", f"+ Dodaj trening led to {pg.url}")
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
