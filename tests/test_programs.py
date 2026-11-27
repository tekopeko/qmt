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
day. Since 23.11.2026 a day has two main parts (the owner, for Amir:
"'glavni dio A' and 'glavni dio B'"): `trening` reads "Glavni dio A" and
`trening_b` is "Glavni dio B" (migration dc22ce1ed7e6).

Since 24.11.2026 an exercise of a day may ask for reps and seconds together
(the owner: "5 reps of 30 seconds of plank"; migration 30815c99e7d2 dropped
the CHECK that refused it), its dose "3 × 5 × 30 s"; and a programme is
online or dvoranski (`Program.venue`, migration 49a70497e58a): a dvoranski
one is the trainer's own plan for the gym, which no client lists or opens.
Both migrations run for real on qmt_test, there and back. Since 27.11.2026
(build 3 of the dvoranski treninzi) neither programme form asks "Vrsta":
every new programme is online, an edited one keeps the stored kind.

Since 25.11.2026 (the owner, for Amir's circuits: "we need to allow Amir to
add exercises which go into one circle of exercises. And for each of those
exercises, the number of reps, the weight if applicable etc.") an item has a
planned weight (`kg`, migration d0ed87d5c98f, run for real there and back),
each part of the day editor ends with "+ Dodaj vježbu u ovaj dio", the add
card takes the numbers too, and a circuit part's row form asks no rest at all
(no pause between a circuit's exercises).
"""

from __future__ import annotations

import importlib.util
import io
import os
import pathlib
import re
import threading
import time
from decimal import Decimal
from html import unescape
from urllib.parse import quote, unquote

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
from qmt.models import SECTIONS, VENUES, Base, ProgramDay, ProgramDayItem, alpha_key, fold, matches
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


def read(markup: str) -> str:
    """Some markup as a reader reads it: tags dropped where they stand,
    entities read, whitespace collapsed (the pages' words are copy slots'
    spans since 25.11.2026, beside the values they name)."""
    return " ".join(unescape(re.sub(r"<[^>]+>", "", markup)).split())


def sub(row: str) -> str | None:
    """A day page's exercise row's muted line (.dx-sub: its rests and its
    note), as read; None for a row with none."""
    m = re.search(r'<span class="dx-sub">(.*?)</span>\s*</span>\s*<span class="dx-go"', row, re.S)
    return read(m.group(1)) if m else None


def ed(key: str, text: str) -> str:
    """The pattern of a slot's span on a staff member's view: the editor's
    span (its key on it), holding `text` (25.11.2026)."""
    return rf'<span class="ed t" data-copy="{re.escape(key)}"[^>]*>{re.escape(text)}</span>'


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


def make_user(email: str, is_trainer: bool = False, level: str = "pocetna") -> int:
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
        # all-zero answers, its goal cijelo, its razina `level`, which is
        # what these tests vary: since 23.11.2026 a client sees every
        # programme of his razina, whatever its type (db.programs_for_level).
        import json

        from qmt import upitnik
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


def trainer_with_clients():
    make_user("trener@test.local", is_trainer=True)
    ivan = make_user("ivan@test.local")                 # pocetna
    ana = make_user("ana@test.local", level="srednja")  # another razina: ivan's programmes are not hers
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


# a row of the library's list: what its <a> tag holds after the class (its
# href, its data-find and, when the search drops it, hidden) and its name; a
# piece of the page cut after the tag (a row split off it) is its name alone
ROW = re.compile(r'(?:<a class="ex-row"([^>]*)>\s*)?<span class="ex-name">([^<]*)</span>')


def all_names(page: str) -> list[str]:
    """The library list's rows, in order, the hidden ones too (since
    23.11.2026 a ?q= page holds every row, the ones it drops `hidden`)."""
    return [unescape(n) for _, n in ROW.findall(page)]


def names(page: str) -> list[str]:
    """The library list's exercises a reader sees, in order: the rows not
    `hidden` (a quoted value never counts: a name may hold the word)."""
    return [unescape(n) for attrs, n in ROW.findall(page) if " hidden" not in re.sub(r'"[^"]*"', "", attrs)]


def line(page: str, cls: str) -> tuple[str, bool] | None:
    """A line of the library's page by its class, its words as read (the
    tags in it dropped) and whether it is hidden: the count ("ex-found",
    "2 od 4 · prikaži sve") and the none line ("ex-none"); None without one."""
    m = re.search(rf'<p class="(?:[^"]* )?{cls}"[^>]*?( hidden)?>(.*?)</p>', page, re.S)   # (aria-live between)
    return m and (" ".join(unescape(re.sub(r"<[^>]+>", "", m.group(2))).split()), m.group(1) is not None)


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

def client_groups(page: str) -> list[tuple[str, list[str]]]:
    """A client's /treninzi as he reads it (since 23.11.2026): each group's
    caption, its type's label ("" for a group under none), and the titles
    of the programmes under it, in order."""
    main = page.split("<main", 1)[1].split("</main>", 1)[0]
    groups = []
    for sec in main.split("<section")[1:]:
        sec = sec.split("</section>", 1)[0]
        cap = re.search(r'<h2 class="dx-cap" id="tip-[a-z]+">([^<]*)</h2>', sec)
        groups.append((unescape(cap.group(1)) if cap else "",
                       [unescape(t) for t in re.findall(r"<strong>([^<]*)</strong>", sec)]))
    return groups


def test_a_client_sees_every_programme_of_his_razina_whatever_its_type():
    """Matching IS the access, and since 23.11.2026 by razina alone (the
    owner: "I want to allow the users to be able to access all types of
    training. The questionnaire only determines the level of fitness and
    the trainings are available for everybody."): ivan (početna, his v1
    goal cijelo) sees a početna programme of every type, Core among them,
    each type's under its caption in the types' order (Cijelo tijelo,
    Gornji dio tijela, Donji dio tijela, Core), each type's by title, and
    opens each; ana (srednja) sees none of them and is refused each. The
    head pill says his razina alone. Re-tagging a programme's razina moves
    its audience at once; a programme with no razina is staff's only."""
    ct, ivan, ana = trainer_with_clients()
    r = ct.post("/treninzi", data={"title": "Tjedan 1", "level": "pocetna",
                                   "goal": "cijelo"}, follow_redirects=False)
    assert "/uredi" in r.headers["location"]
    pid = int(r.headers["location"].split("/")[2])
    others = [db.create_program(title, None, "pocetna", goal)
              for title, goal in (("Core B", "core"), ("Noge", "donji"), ("Core A", "core"), ("Gornji blok", "gornji"))]
    ci, ca = client_for("ivan@test.local"), client_for("ana@test.local")

    page = ci.get("/treninzi").text
    assert client_groups(page) == [("Cijelo tijelo", ["Tjedan 1"]), ("Gornji dio tijela", ["Gornji blok"]),
                                   ("Donji dio tijela", ["Noge"]), ("Core", ["Core A", "Core B"])]
    assert '<section aria-labelledby="tip-core">\n    <h2 class="dx-cap" id="tip-core">Core</h2>' in page
    assert re.search(r'padding:4px 10px;">\s*Početna razina</span>', page) and "· Cijelo tijelo" not in page
    assert [p.title for p in db.programs_for_level("pocetna")] == ["Tjedan 1", "Gornji blok", "Noge", "Core A", "Core B"]
    for p in (pid, *others):
        assert ci.get(f"/treninzi/{p}").status_code == 200 and db.client_can_view(db.get_program(p), ivan), p
        assert ca.get(f"/treninzi/{p}").status_code == 403 and not db.client_can_view(db.get_program(p), ana), p
    ana_page = ca.get("/treninzi").text
    assert client_groups(ana_page) == [] and "Programi za tvoju razinu još se pripremaju." in ana_page

    # re-tagging the razina instantly moves the audience — no hand-outs anywhere
    ct.post(f"/treninzi/{pid}/edit", data={"title": "Tjedan 1", "level": "srednja",
                                           "goal": "gornji"}, follow_redirects=False)
    assert ca.get(f"/treninzi/{pid}").status_code == 200
    assert ci.get(f"/treninzi/{pid}").status_code == 403
    assert client_groups(ca.get("/treninzi").text) == [("Gornji dio tijela", ["Tjedan 1"])]
    assert client_groups(ci.get("/treninzi").text)[0] == ("Gornji dio tijela", ["Gornji blok"])

    # a programme with no razina is trainer-only
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
    assert re.search(r'<p class="hint" data-opt>' + ed("program.empty_staff", "Program još nema treninga — dodaj prvi u uređivanju.")
                     + "</p>", view)
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
    assert '<p class="hint" style="margin-top:22px;"><span class="t">Trening još nema vježbi.</span></p>' in client_day


def test_a_client_is_told_what_is_not_there_yet():
    """A client whose razina has no programme (another razina's is not
    his): "Programi za tvoju razinu još se pripremaju." (since 23.11.2026;
    "Program za tvoju kombinaciju još se priprema." until then); one whose
    programme has no day sees it listed, "0 treninga", and its page says
    "Program još nema treninga.". What he opens makes nothing either. The
    page's lead says what the upitnik decides: "Programi tvoje razine —
    određuje je upitnik."."""
    trainer_with_clients()
    db.create_program("Srednji blok", None, "srednja", "cijelo")            # ana's razina
    ci = client_for("ivan@test.local")                                      # pocetna
    page = ci.get("/treninzi").text
    assert ('<p style="margin-bottom:6px;"><strong><span class="t">Programi za tvoju razinu još se pripremaju.</span></strong></p>\n'
            '    <p class="hint"><span class="t">Trener slaže sadržaj — provjeri uskoro.</span></p>') in page
    assert '<p class="hint"><span class="t">Programi tvoje razine — određuje je upitnik.</span></p>' in page
    assert "kombinacij" not in page and "cilj" not in page
    assert "Srednji blok" not in page and stored_counts() == (1, 0, 0, 0)
    pid = db.create_program("Tjedan 1", None, "pocetna", "gornji")
    page = ci.get("/treninzi").text
    assert "još se priprema" not in page and f'href="/treninzi/{pid}"' in page and '<div class="hint">0 treninga</div>' in page
    assert client_groups(page) == [("Gornji dio tijela", ["Tjedan 1"])]
    assert '<p class="hint"><span class="t">Program još nema treninga.</span></p>' in ci.get(f"/treninzi/{pid}").text
    assert stored_counts() == (2, 0, 0, 0)


def test_a_client_without_the_upitnik_is_told_it_decides_his_razina():
    """A client with the online plan and no upitnik gets its card, whose
    line says the upitnik places him in a razina and the programmes open at
    once (since 23.11.2026, no cilj: the razina is all it decides)."""
    make_user("trener@test.local", is_trainer=True)
    uid = make_user("ivan@test.local")
    with db.engine.begin() as conn:
        conn.execute(sa_text("DELETE FROM onboarding_responses WHERE user_id = :u"), {"u": uid})
    page = client_for("ivan@test.local").get("/treninzi").text
    assert ('<p class="hint" style="margin-top:2px;"><span class="t">Prema odgovorima te svrstavamo u razinu '
            '(početna / srednja / napredna) — programi se otvaraju odmah.</span></p>') in page
    assert "Ispuni upitnik" in page and "<section" not in page.split("<main", 1)[1]


def test_the_trainers_treninzi_page_says_he_makes_the_programmes():
    """The lead says what is automatic (the matching, by razina since
    23.11.2026, every type of it) and what is his (the programmes, their
    days and exercises), what a razina with no programme tells its client,
    and since 24.11.2026 that a dvoranski programme is his alone: since
    27.11.2026 (build 3 of the dvoranski treninzi, no form makes a new one)
    only while one exists. The form is "Novi program", its button "Kreiraj
    i dodaj treninge", which opens the new programme's editor, the
    programme with no day."""
    ct, *_ = trainer_with_clients()
    page = ct.get("/treninzi").text
    lead = ("Sve je automatski: upitnik svrsta polaznika u razinu, a on odmah vidi sve programe te razine, po tipu "
            "treninga — ništa se ne dodjeljuje ručno. Programe slažeš sam: za svaku razinu napravi programe po tipu "
            "pa im dodaj treninge i vježbe. Razina bez programa polazniku kaže da se programi još pripremaju.")
    gym = " Dvoranski programi su samo tvoji: polaznici ih ne vide."
    assert f'<p class="hint"> {lead} </p>' in " ".join(page.split()) and gym.strip() not in page
    assert '<h2 style="font-size:1.05rem; margin-bottom:12px;">Novi program</h2>' in page
    assert '<button type="submit">Kreiraj i dodaj treninge</button>' in page
    assert 'placeholder="npr. Gornji dio tijela — tjedan 2"' in page
    for gone in ("skice se stvore same", "devet osnovnih varijanti", "Dodatni program", "Kreiraj i dodaj vježbe"):
        assert gone not in page, gone
    r = ct.post("/treninzi", data={"title": "Tjedan 1", "level": "srednja", "goal": "donji"}, follow_redirects=False)
    pid = db.all_programs()[0][0].id
    assert r.headers["location"] == f"/treninzi/{pid}/uredi" and stored_counts() == (1, 0, 0, 0)
    assert gym.strip() not in ct.get("/treninzi").text                      # an online one: still not
    gid = db.create_program("Snaga u dvorani", None, "pocetna", "cijelo", "dvorana")
    assert f'<p class="hint"> {lead}{gym} </p>' in " ".join(ct.get("/treninzi").text.split())
    db.delete_program(gid)
    assert gym.strip() not in ct.get("/treninzi").text


def test_a_programme_is_one_of_four_types_core_last():
    """A programme's type ("Tip programa" on both its forms since 26.11.2026, "Tip treninga" from 23.11., "Cilj" until
    23.11.2026; the column stays `goal`) is one of four since 23.11.2026
    (the owner: "we need 'cijelo tijelo' 'gornji dio tijela' 'donji dio
    tijela', but also 'core'"), Core last, in "Novi program" and "Uredi
    program" alike; staff's table names it under "Tip", a razina's
    programmes in the types' order (Core fourth). A type or a razina that
    is none is refused on both routes, "Odaberi razinu i tip programa.",
    nothing stored or changed."""
    ct, *_ = trainer_with_clients()
    types = [("cijelo", "Cijelo tijelo"), ("gornji", "Gornji dio tijela"), ("donji", "Donji dio tijela"),
             ("core", "Core")]
    page = ct.get("/treninzi").text
    assert '<div class="field"><label for="np-goal">Tip programa</label>' in page and ">Cilj<" not in page
    assert '<th style="padding:8px 6px;">Tip</th><th>Program</th>' in page
    new = page.split('id="np-goal"')[1].split("</select>")[0]
    assert re.findall(r'<option value="(\w+)">([^<]*)</option>', new) == types
    r = ct.post("/treninzi", data={"title": "Core 1", "level": "srednja", "goal": "core"}, follow_redirects=False)
    pid = int(r.headers["location"].split("/")[2])
    p = db.get_program(pid)
    assert (p.title, p.level, p.goal) == ("Core 1", "srednja", "core")
    for title, goal in (("Gornji", "gornji"), ("Cijelo", "cijelo"), ("Donji", "donji")):
        db.create_program(title, None, "srednja", goal)
    table = ct.get("/treninzi").text
    srednja = table.split("Srednja razina</td>")[1].split("Napredna razina</td>")[0]
    assert re.findall(r'<td style="padding:9px 6px; white-space:nowrap;">([^<]*)</td>', srednja) == [l for _, l in types]
    edit = ct.get(f"/treninzi/{pid}/uredi").text
    assert '<div class="field"><label for="pe-goal">Tip programa</label>' in edit and ">Cilj<" not in edit
    sel = edit.split('id="pe-goal"')[1].split("</select>")[0]
    assert re.findall(r'<option value="(\w+)" (?:selected)?>([^<]*)</option>', sel) == types
    assert '<option value="core" selected>Core</option>' in sel
    for bad in ({"level": "srednja", "goal": "ruke"}, {"level": "x", "goal": "core"}):
        r = ct.post("/treninzi", data={"title": "X", **bad}, follow_redirects=False)
        assert location(r) == "/treninzi?error=Odaberi razinu i tip programa.", bad
        r = ct.post(f"/treninzi/{pid}/edit", data={"title": "X", **bad}, follow_redirects=False)
        assert location(r) == f"/treninzi/{pid}/uredi?error=Odaberi razinu i tip programa.", bad
    p = db.get_program(pid)
    assert stored_counts()[0] == 4 and (p.title, p.level, p.goal) == ("Core 1", "srednja", "core")


# ---------- a programme is online or dvoranski (24.11.2026) ----------

# the forms' grid of selects (Tip programa, Razina; Vrsta too until 27.11.2026)
VENUE_GRID = 'style="display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:0 12px;"'


def test_neither_programme_form_asks_vrsta():
    """A programme's "Vrsta" (models.VENUES: online or dvoranski, 24.11.2026)
    is asked by neither form since 27.11.2026 (build 3 of the dvoranski
    treninzi; the owner: "I dont like the fact that I need to go to 'Online
    treninzi' and create a new programme there which is not applicable to
    gym trainings": a gym training starts from Amir's templates). "Novi
    program" holds Tip programa and Razina in their auto-fit grid, no Vrsta,
    and makes every programme online, whatever is posted (a `venue` of
    dvorana, of nothing, of junk: ignored, never refused). "Uredi program"
    holds none either and keeps the stored one: a dvoranski programme
    edited stays dvoranski (its title saved, its chip beside the h1), an
    online one online, whatever is posted. The CHECK still holds."""
    ct, *_ = trainer_with_clients()
    assert VENUES == {"online": "Online", "dvorana": "Dvoranski"}
    page = ct.get("/treninzi").text
    form = page.split('<form method="post" action="/treninzi" class="card"')[1].split("</form>")[0]
    assert VENUE_GRID in form and form.index('id="np-goal"') < form.index('id="np-level"')
    assert "Vrsta" not in form and 'name="venue"' not in form and "Dvoranski" not in form
    assert re.findall(r'<label for="np-(\w+)">', form) == ["title", "goal", "level", "intro"]

    def new(title: str, **venue) -> int:
        r = ct.post("/treninzi", data={"title": title, "level": "pocetna", "goal": "cijelo", **venue},
                    follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].endswith("/uredi"), venue
        return int(r.headers["location"].split("/")[2])

    made = [new("Dvorana A", venue="dvorana"), new("Online A", venue="online"), new("Bez vrste"), new("Krivo", venue="x")]
    assert [db.get_program(p).venue for p in made] == ["online"] * 4
    gym = db.create_program("Dvorana B", None, "pocetna", "cijelo", "dvorana")    # one there from before
    for pid in (gym, made[0]):
        edit = ct.get(f"/treninzi/{pid}/uredi").text
        pe = edit.split(f'<form method="post" action="/treninzi/{pid}/edit"')[1].split("</form>")[0]
        assert VENUE_GRID in pe and "Vrsta" not in pe and 'name="venue"' not in pe and "Dvoranski" not in pe, pid
        assert re.findall(r'<label for="([\w-]+)">', pe) == ["pe-goal", "pe-level", "pt", "pi"], pid

    def edit_to(pid: int, title: str, **venue):
        return ct.post(f"/treninzi/{pid}/edit", data={"title": title, "level": "pocetna", "goal": "cijelo", **venue},
                       follow_redirects=False)

    for venue in ({"venue": "online"}, {}, {"venue": "x"}):
        assert location(edit_to(gym, "Dvorana C", **venue)) == f"/treninzi/{gym}/uredi?ok=Spremljeno.", venue
        assert (db.get_program(gym).title, db.get_program(gym).venue) == ("Dvorana C", "dvorana"), venue
    assert '<h1>Uredi program <span class="venue-chip">dvoranski</span></h1>' in ct.get(f"/treninzi/{gym}/uredi").text
    assert location(edit_to(made[1], "Online B", venue="dvorana")) == f"/treninzi/{made[1]}/uredi?ok=Spremljeno."
    assert (db.get_program(made[1]).title, db.get_program(made[1]).venue) == ("Online B", "online")
    assert stored_counts()[0] == 5
    with pytest.raises(IntegrityError):                                     # the CHECK: nothing else is stored
        db.create_program("Y", None, "pocetna", "cijelo", "kardio")


def test_a_dvoranski_programme_is_staffs_only():
    """A dvoranski programme (24.11.2026) is the trainer's own plan for the
    gym. A client of its razina has it neither in his list (his online one
    he has: db.programs_for_level) nor behind any address: its page, its
    day, its player (Kreni, an exercise, its save, the finish screen) and
    its clips (an exercise only it holds, its day's intro video) are 403,
    db.client_can_view false, no pass opened. Staff see it, a muted
    "dvoranski" after its title in the /treninzi table and beside the h1 on
    its page and in its editor (an online one carries none), watch its
    clips and run its player: Kreni, a save, the osvrt, a finished pass of
    their own. Made online (db.update_program: no form does since
    27.11.2026, build 3 of the dvoranski treninzi), it is the client's at
    once."""
    ct, ivan, _ = trainer_with_clients()
    trainer = db.get_user_by_email("trener@test.local").id
    gym = db.create_program("Snaga u dvorani", None, "pocetna", "cijelo", "dvorana")
    online = db.create_program("Snaga online", None, "pocetna", "cijelo")
    did = db.add_day(gym)
    lift = db.create_exercise("Mrtvo dizanje")                              # only the gym programme holds it
    iid = hold(gym, lift)
    db.update_day_item(iid, "trening", 3, 5, None, 120, None, "")
    upload(ct, lift, "m.mp4", MP4)
    day_upload(ct, gym, did, "d.mp4", MP4)
    clip, intro = db.exercise(lift).video, db.get_day(did).intro_video
    day = f"/treninzi/{gym}/dan/{did}"
    ci = client_for("ivan@test.local")

    assert client_groups(ci.get("/treninzi").text) == [("Cijelo tijelo", ["Snaga online"])]
    assert [p.id for p in db.programs_for_level("pocetna")] == [online]
    assert not db.client_can_view(db.get_program(gym), ivan) and db.client_can_view(db.get_program(online), ivan)
    for r in (ci.get(f"/treninzi/{gym}"), ci.get(day), ci.post(f"{day}/kreni"), ci.get(f"{day}/vjezba/1"),
              ci.post(f"{day}/vjezba/1", data={"rows": "1", "item": str(iid), "reps_1": "5", "kg_1": "100"}),
              ci.get(f"{day}/kraj"), ci.get(f"/media/{clip}"), ci.get(f"/media/{intro}")):
        assert r.status_code == 403, r.request.url
    assert db.passes(ivan) == [] and db.open_pass(ivan, did) is None

    table = ct.get("/treninzi").text
    assert '<td><strong>Snaga u dvorani</strong> <span class="venue-chip">dvoranski</span></td>' in table
    assert '<td><strong>Snaga online</strong></td>' in table and table.count('class="venue-chip"') == 1
    assert re.search(r'<h1>Snaga u dvorani <span class="venue-chip" data-opt>' + ed("program.head.venue", "dvoranski")
                     + "</span></h1>", ct.get(f"/treninzi/{gym}").text)
    assert '<h1>Uredi program <span class="venue-chip">dvoranski</span></h1>' in ct.get(f"/treninzi/{gym}/uredi").text
    assert "<h1>Snaga online</h1>" in ct.get(f"/treninzi/{online}").text
    assert "<h1>Uredi program</h1>" in ct.get(f"/treninzi/{online}/uredi").text
    assert ct.get(f"/media/{clip}").status_code == 200 and ct.get(f"/media/{intro}").status_code == 200
    r = ct.post(f"{day}/kreni", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"{day}/vjezba/1"
    assert ct.get(f"{day}/vjezba/1").status_code == 200
    r = ct.post(f"{day}/vjezba/1", data={"rows": "1", "item": str(iid), "reps_1": "5", "kg_1": "100"}, follow_redirects=False)
    assert r.headers["location"] == f"{day}/kraj"
    r = ct.post(f"{day}/kraj", data={"effort": "7"}, follow_redirects=False)
    assert location(r) == f"{day}?ok=Trening je spremljen."
    [done] = db.passes(trainer)
    assert (done.program_title, done.effort, done.done_items[iid]["sets"]) == ("Snaga u dvorani", 7, [{"reps": 5, "kg": 100.0}])

    db.update_program(gym, "Snaga u dvorani", None, "pocetna", "cijelo", "online")
    assert ci.get(f"/treninzi/{gym}").status_code == 200 and ci.get(f"/media/{clip}").status_code == 200
    assert [title for _, titles in client_groups(ci.get("/treninzi").text) for title in titles] == [
        "Snaga online", "Snaga u dvorani"]
    assert client_for("ana@test.local").get(f"/treninzi/{gym}").status_code == 403   # another razina's: still not hers


def test_the_demo_seed_makes_its_nine_programmes_none_of_them_core():
    """scripts/seed_demo.py's programmes walk its DEMO_PROGRAMS (since
    23.11.2026, not upitnik.GOALS, which holds Core now: the demo's
    exercises hold one core exercise, so Core has no demo programme), so
    the dev reset still makes its nine, a razina × its three types, each
    titled by its type and razina, each with a Trening 1; a client of
    srednja (the demo's ivan) sees that razina's three, Cijelo tijelo
    first. That one's Trening 1, the day the audit walks, does its Glavni
    dio A as a circuit (24.11.2026, DEMO_CIRCUIT: 2 rounds, 90 s between
    them; since 25.11.2026 no pause between its exercises, so the seed gives
    them none of their own: their stored rests do not apply there), its
    other parts normal."""
    from qmt import upitnik

    path = pathlib.Path(__file__).parents[1] / "scripts" / "seed_demo.py"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    seed = importlib.util.module_from_spec(spec); spec.loader.exec_module(seed)
    assert list(seed.DEMO_PROGRAMS) == ["cijelo", "gornji", "donji"] and list(upitnik.GOALS) == [
        "cijelo", "gornji", "donji", "core"]
    seed.seed_program()
    rows = [(p.level, p.goal, p.title, nd) for p, nd, _ in db.all_programs()]
    assert sorted((lv, g) for lv, g, *_ in rows) == sorted((lv, g) for lv in upitnik.LEVELS for g in seed.DEMO_PROGRAMS)
    assert all(nd >= 1 for *_, nd in rows) and len(rows) == 9
    assert ("napredna", "donji", "Donji dio tijela — napredna razina") in [r[:3] for r in rows]
    mine = db.programs_for_level("srednja")
    assert [p.title for p in mine] == [
        "Cijelo tijelo — srednja razina", "Gornji dio tijela — srednja razina", "Donji dio tijela — srednja razina"]
    first, second = mine[0].days
    assert seed.DEMO_CIRCUIT == ("trening", 2, 90)
    assert [(c.section, c.rounds, c.rest_seconds) for c in first.circuits] == [("trening", 2, 90)] and first.has_circuit
    assert [(it.exercise.name, it.rest_after_seconds) for it in first.by_section["trening"]] == [
        ("Goblet čučanj", seed.DEMO_REST_AFTER), ("Sklekovi", seed.DEMO_REST_AFTER),
        ("Veslanje u pretklonu", seed.DEMO_REST_AFTER), ("Plank", seed.DEMO_REST_AFTER)]   # stored, not applying
    assert second.circuits == [] and all(not p.days[0].circuits for p in mine[1:])


def test_the_demo_seed_makes_its_template():
    """scripts/seed_demo.py's template (26.11.2026, build 2: TEMPLATE,
    TEMPLATE_PARTS): after the nine programmes (seed_program), seed_template
    makes one dvoranski programme, "Predložak — kružni trening" (srednja,
    cijelo), which no client lists; its Trening 1 holds slots alone:
    Zagrijavanje two ("mobilnost", "aktivacija"), Glavni dio A renamed "Krug
    1", a circuit of 3 rounds, 90 s after a round, four ("čučanj",
    "potisak", "povlačenje", "core"), each 10 reps, Istezanje one; no
    exercise, so no "kružni trening" said. ivan's programme is still found
    by its razina and type (the seed's own lookups ask for an online one)."""
    from qmt import upitnik

    path = pathlib.Path(__file__).parents[1] / "scripts" / "seed_demo.py"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    seed = importlib.util.module_from_spec(spec); spec.loader.exec_module(seed)
    seed.seed_program()
    seed.seed_template()
    rows = db.all_programs()
    assert len(rows) == 10 and [p.title for p, *_ in rows if p.venue == "dvorana"] == ["Predložak — kružni trening"]
    [pid] = [p.id for p, *_ in rows if p.venue == "dvorana"]
    p = db.get_program(pid)
    assert (p.title, p.level, p.goal, p.venue) == ("Predložak — kružni trening", "srednja", "cijelo", "dvorana")
    [day] = p.days
    assert [(k, [(it.hint, it.sets, it.reps, it.seconds, it.kg) for it in rows]) for k, rows in day.by_section.items()] == [
        ("zagrijavanje", [("mobilnost", None, None, None, None), ("aktivacija", None, None, None, None)]),
        ("trening", [(hint, None, 10, None, None) for hint in ("čučanj", "potisak", "povlačenje", "core")]),
        ("trening_b", []), ("trening_c", []), ("istezanje", [("", None, None, None, None)])]
    assert all(it.is_slot for it in day.items) and day.exercise_items == [] and day.slots_text == "7 praznih mjesta"
    assert [(x.section, x.title) for x in day.parts] == [("trening", "Krug 1")] and day.part_label("trening") == "Krug 1"
    assert [(c.section, c.rounds, c.rest_seconds) for c in day.circuits] == [("trening", 3, 90)] and not day.has_circuit
    assert [x.title for x in db.programs_for_level("srednja")] == [
        "Cijelo tijelo — srednja razina", "Gornji dio tijela — srednja razina", "Donji dio tijela — srednja razina"]
    assert seed.TEMPLATE == ("Predložak — kružni trening", "srednja", "cijelo") and "cijelo" in upitnik.GOALS


def test_a_day_says_its_label_and_an_item_its_dose_and_rest():
    """A day's label is "Trening N", with its title "Trening N · title";
    its items read section by section in their order, each in position
    order. An item's dose is the list's words: sets × reps, sets × seconds,
    and since 24.11.2026 sets × reps × seconds ("3 × 5 × 30 s": 5 reps of
    30 s) and reps × seconds with no sets ("5 × 30 s"), reps or seconds
    alone, sets alone, nothing; its rest "60 s" or nothing."""
    assert ProgramDay(position=2, title="").label == "Trening 2"
    assert ProgramDay(position=1, title="Cijelo tijelo").label == "Trening 1 · Cijelo tijelo"

    def dose(sets=None, reps=None, seconds=None):
        return ProgramDayItem(sets=sets, reps=reps, seconds=seconds).dose

    assert [dose(3, 10), dose(3, None, 30), dose(3, 5, 30), dose(1, 1, 3600), dose(None, 5, 30), dose(None, 1, 10),
            dose(None, 10), dose(None, 1), dose(None, 3), dose(None, None, 30),
            dose(3), dose(1), dose(5), dose(21), dose(12), dose()] == [
        "3 × 10", "3 × 30 s", "3 × 5 × 30 s", "1 × 1 × 3600 s", "5 × 30 s", "1 × 10 s",
        "10 ponavljanja", "1 ponavljanje", "3 ponavljanja", "30 s",
        "3 serije", "1 serija", "5 serija", "21 serija", "12 serija", ""]
    assert [ProgramDayItem(rest_seconds=r).rest_text for r in (60, 0, None)] == ["60 s", "0 s", ""]
    day = ProgramDay(position=1, title="")
    day.items = [ProgramDayItem(position=1, section="trening", note="a"), ProgramDayItem(position=2, section="istezanje", note="b"),
                 ProgramDayItem(position=3, section="zagrijavanje", note="c"), ProgramDayItem(position=4, section="trening", note="d")]
    assert {k: [i.note for i in v] for k, v in day.by_section.items()} == {
        "zagrijavanje": ["c"], "trening": ["a", "d"], "trening_b": [], "trening_c": [], "istezanje": ["b"]}
    # two main parts (23.11.2026), three since 26.11.2026
    assert list(day.by_section) == ["zagrijavanje", "trening", "trening_b", "trening_c", "istezanje"]
    assert ProgramDay(position=1, title="").by_section == {"zagrijavanje": [], "trening": [], "trening_b": [],
                                                           "trening_c": [], "istezanje": []}


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
    assert '<p class="hint" style="margin-top:22px;"><span class="t">Trening još nema vježbi.</span></p>' in page
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
    to a client only through a programme matched to him (his razina,
    whatever its type since 23.11.2026: a Core one here), a day of it
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
    pid = db.create_program("S videom", None, "pocetna", "core")            # ivan's razina, a Core programme
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
    whose name or tags hold every word of it, whatever its case (since
    23.11.2026, models.matches: "noge kuce" two tags, "goblet noge" the
    name and a tag, "cuc plank" nothing); blank shows all; none matching
    says so. Since the same day the search filters as it is typed (the
    browser test below), so every row is on the page, ?q= too, the ones it
    drops `hidden`, each with its data-find ("name · tags", the name alone
    without tags); the count line and the none line are always there,
    hidden while they say nothing; the input is autocomplete="off". An
    empty library says "Još nema vježbi." with the button, and no script."""
    ct, *_ = trainer_with_clients()
    page = ct.get("/treninzi/vjezbe").text
    assert "<h1>Vježbe</h1>" in page and "Još nema vježbi." in page and 'href="/treninzi/vjezbe/nova">+ Nova vježba</a>' in page
    assert '<p class="hint ex-found"' not in page and "a.ex-row[data-find]" not in page   # no list, no script
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
    every = ["Biceps pregib", "Čučanj s vlastitom težinom", "Goblet čučanj", "Plank"]
    assert names(page) == all_names(page) == every
    assert "Još nema vježbi." not in page and 'role="search"' in page and 'name="q" value=""' in page
    assert 'aria-label="Traži vježbu po nazivu ili oznaci" autocomplete="off">' in page   # no browser history over the list
    assert line(page, "ex-found") == ("4 od 4 · prikaži sve", True)                       # no q: there, hidden
    assert line(page, "ex-none") == ("Nijedna vježba ne odgovara traženju „”.", True)
    assert re.search(r'</a>\s*<p class="ex-none" hidden>[^\n]*</p>\s*</div>', page)       # the list's last child
    rows = {names(r)[0]: r for r in page.split('<a class="ex-row" ')[1:]}
    assert 'data-find="Plank · core, kod kuće">' in rows["Plank"] and 'data-find="Biceps pregib">' in rows["Biceps pregib"]
    assert f'href="/treninzi/vjezbe/{ids["Plank"]}"' in rows["Plank"] and '<span class="has">video ✓</span>' in rows["Plank"]
    assert "<span>bez videa</span>" in rows["Goblet čučanj"] and "<span>u 2 programa</span>" in rows["Goblet čučanj"]
    assert "<span>u 1 programu</span>" in rows["Plank"] and "<span>ni u jednom programu</span>" in rows["Biceps pregib"]
    assert 'class="ex-tag"' not in rows["Biceps pregib"]
    assert names(ct.get("/treninzi/vjezbe?q=ČUČANJ").text) == ["Čučanj s vlastitom težinom", "Goblet čučanj"]
    found = ct.get("/treninzi/vjezbe?q=Kod+kuće").text
    assert names(found) == ["Čučanj s vlastitom težinom", "Plank"] and 'value="Kod kuće"' in found
    assert line(found, "ex-found") == ("2 od 4 · prikaži sve", False)
    assert all_names(found) == every                                                      # every row, the others hidden
    assert [n for n in all_names(found) if n not in names(found)] == ["Biceps pregib", "Goblet čučanj"]
    assert line(found, "ex-none") == ("Nijedna vježba ne odgovara traženju „Kod kuće”.", True)
    blank = ct.get("/treninzi/vjezbe?q=+++").text
    assert names(blank) == every and line(blank, "ex-found")[1] and 'name="q" value=""' in blank
    none = ct.get("/treninzi/vjezbe?q=xyz").text
    assert names(none) == [] and all_names(none) == every
    assert line(none, "ex-none") == ("Nijedna vježba ne odgovara traženju „xyz”.", False)
    assert line(none, "ex-found") == ("0 od 4 · prikaži sve", False)
    assert [e.name for e, _ in db.exercises("BUČ")] == ["Goblet čučanj"]
    # every word in the name or the tags, folded, in any order (models.matches)
    for q, kept in (("noge kuce", ["Čučanj s vlastitom težinom"]),       # two words of its tags
                    ("cucanj tezinom", ["Čučanj s vlastitom težinom"]),  # two of its name: not Goblet čučanj
                    ("goblet NOGE", ["Goblet čučanj"]),                  # one of the name, one of the tags
                    ("kuće   core", ["Plank"]), ("cuc plank", [])):       # every word on one row
        assert names(ct.get("/treninzi/vjezbe", params={"q": q}).text) == kept, q
        assert [e.name for e, _ in db.exercises(q)] == kept, q
    assert matches("", "Plank") and matches("  ", "") and not matches("plank", "", "")


def test_the_search_folds_the_croatian_letters():
    """The exercise searches fold alike since 23.11.2026 (the owner: "when I
    start searching for an exercise starting with 'add' it shows the
    adductor exercises"): models.fold lowers the case, takes č and ć to c,
    đ to d, š to s and ž to z, and drops every other mark; the library's
    ?q= matches the name and the tags with it, so "cuc", "ČUČ" and "čuč"
    find the squat and not the plank, "kuc" its tag "kod kuće", "dacki"
    a name with Đ. (The day editor's "Dodaj vježbu" and an exercise's swaps
    fold with base.html's qmtFold, the same table: the browser tests.)"""
    assert fold("Čučanj ĐŠŽĆ") == "cucanj dszc"
    assert fold("  Crème brûlée ") == "  creme brulee " and fold("") == ""
    ct, *_ = trainer_with_clients()
    for n, t in (("Čučanj s vlastitom težinom", "noge, kod kuće"), ("Plank", "core"), ("Đački iskorak", "noge, bučice")):
        db.create_exercise(n, tags=t)
    for q in ("cuc", "ČUČ", "čuč", "Cucanj"):
        assert names(ct.get("/treninzi/vjezbe", params={"q": q}).text) == ["Čučanj s vlastitom težinom"], q
    assert names(ct.get("/treninzi/vjezbe", params={"q": "kuc"}).text) == ["Čučanj s vlastitom težinom"]
    assert names(ct.get("/treninzi/vjezbe", params={"q": "dacki"}).text) == ["Đački iskorak"]
    assert names(ct.get("/treninzi/vjezbe", params={"q": "BUCICE"}).text) == ["Đački iskorak"]
    assert [e.name for e, _ in db.exercises("ČUČ")] == ["Čučanj s vlastitom težinom"]


# ---------- the library's tags as chips (23.11.2026) ----------
# The owner: "Can we also add a search helper where we can search the items
# used in the exercise like for example 'girja' and then show all exercises
# with 'girja' in the dropdown?" Under both exercise searches, the library's
# and the day editor's "Dodaj vježbu", a row of chips, one per tag Amir uses.

def test_tag_counts_count_each_tag_folded_in_its_most_frequent_spelling():
    """db.tag_counts: every tag of the library with how many exercises
    carry it, counted folded ("TRX" and "trx" one tag, "Leđa" and "leđa"
    one; an exercise counts a tag once, whatever it repeats), each in its
    most frequent spelling (a tie: the first in the alphabet's order,
    "bucica" before "bučica"; spellings the alphabet cannot part, upper
    case first, "TRX" before "trx"), the most used first, then the
    alphabet's order; a tag one exercise carries is there, with 1; an
    exercise with no tags adds nothing."""
    assert db.tag_counts() == []
    for name, tags in (("A", "trx, Leđa, girja"), ("B", "TRX, leđa"), ("C", "trx, leđa, TRX"), ("D", "girja, bučica"),
                       ("E", "leđa, hip thurst"), ("F", ""), ("G", "bucica")):
        db.create_exercise(name, tags=tags)
    assert db.tag_counts() == [("leđa", 4), ("trx", 3), ("bucica", 2), ("girja", 2), ("hip thurst", 1)]
    db.create_exercise("H", tags="TRX, BUČICA")                            # trx 2, TRX 2; a third way of bučica
    assert db.tag_counts() == [("leđa", 4), ("TRX", 4), ("bucica", 3), ("girja", 2), ("hip thurst", 1)]
    db.create_exercise("I", tags="trx")                                    # 3 trx to 2 TRX
    assert db.tag_counts()[:2] == [("trx", 5), ("leđa", 4)]


# the tags' row as served (_tagbar.html): a button per chip, its tag (its
# words the same) and whether it is hidden; "još N" a button of its own
CHIP = re.compile(r'<button type="button" class="tag-chip" data-tag="([^"]*)" aria-pressed="false"( hidden)?>([^<]*)</button>')
MORE = re.compile(r'<button type="button" class="tag-chip tag-more">([^<]*)</button>')
TAGBAR = '<div class="tagbar" role="group" aria-label="Oznake" hidden>'


def tag_row(page: str) -> tuple[list[tuple[str, bool]], str | None] | None:
    """The page's row of chips (the one outside any <noscript>): each
    chip's tag and whether it is hidden, and "još N"'s words (None without
    one); None without a row."""
    page = re.sub(r"<noscript>.*?</noscript>", "", page, flags=re.S)
    m = re.search(re.escape(TAGBAR) + r"(.*?)</div>", page, re.S)
    if not m:
        return None
    chips = CHIP.findall(m.group(1))
    assert all(tag == words for tag, _, words in chips), chips
    more = MORE.search(m.group(1))
    return [(unescape(t), bool(h)) for t, h, _ in chips], more and more.group(1)


def tag_links(page: str) -> list[tuple[str, str, bool]]:
    """The library's <noscript> row: each link's words, its href and
    whether it is pressed (aria-current)."""
    m = re.search(r"<noscript>(.*?)</noscript>", page, re.S)
    return [(unescape(t), unescape(h), bool(on)) for h, on, t in
            re.findall(r'<a class="tag-chip" href="([^"]*)"( aria-current="true")?>([^<]*)</a>', m.group(1))] if m else []


# tag -> how many exercises carry it: 15 tags at least two exercises carry
# and a typo one carries (tag_library())
TAG_USES = {"girja": 6, "bučica": 5, "bodyweight": 5, "trx": 4, "iskorak": 4, "noge": 4, "core": 3, "hinge": 3,
            "leđa": 3, "horizontalni potisak": 3, "čučanj": 2, "sklek": 2, "most": 2, "rame": 2, "antirotacija": 2,
            "hip thurst": 1}
TAG_ORDER = ["girja", "bodyweight", "bučica", "iskorak", "noge", "trx", "core", "hinge", "horizontalni potisak",
             "leđa", "antirotacija", "čučanj", "most", "rame", "sklek"]          # the most used first, then the alphabet's


def tag_library() -> None:
    """Six exercises carrying TAG_USES: exercise n every tag more than n-1
    exercises carry."""
    for n in range(1, 7):
        db.create_exercise(f"Vježba {n}", tags=", ".join(t for t, k in TAG_USES.items() if k >= n))


def test_the_tags_are_chips_under_both_searches():
    """Under the library's search and in the day editor's "Dodaj vježbu"
    the library's tags as chips, the same row on both (_tagbar.html): a
    group labelled "Oznake", rendered hidden (the script shows it), a
    button per tag at least two exercises carry (a tag one carries is no
    chip: the typos), the most used first, each type="button" (none sends a
    form) and not pressed; the first 12 shown, the rest hidden behind "još
    N". On the library the row stands between the search and the count
    line, and a browser without JavaScript gets a <noscript> row of links
    instead, every chip shown, each to the list filtered by its tag (the
    server's ?q=), the one that is the whole of ?q= (folded) pressed
    (aria-current) and linking back to the whole list. In the day editor
    the row stands inside "Dodaj vježbu"'s form, above its fields (the
    combobox's open list, under the input, never covers it), with no links
    (the select is the picker without JS). No tag
    carried twice: no row on either page."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    edit = f"/treninzi/{pid}/dan/{did}/uredi"
    db.create_exercise("Plank", tags="core, hip thurst")                    # every tag carried once: no chip
    for page in (ct.get("/treninzi/vjezbe").text, ct.get(edit).text):
        assert tag_row(page) is None and 'class="tag-chip' not in page
    with db.engine.begin() as conn:
        conn.execute(sa_text("DELETE FROM exercises"))
    tag_library()
    assert db.tag_counts() == [(t, TAG_USES[t]) for t in TAG_ORDER] + [("hip thurst", 1)]

    lib = ct.get("/treninzi/vjezbe").text
    assert tag_row(lib) == ([(t, i >= 12) for i, t in enumerate(TAG_ORDER)], "još 3")
    assert re.search(r'</div>\s*' + re.escape(TAGBAR) + r'.*?</div>\s*<noscript>.*?</noscript>\s*<p class="hint ex-found"',
                     lib.split('<div class="ex-tools">')[1].split("</form>", 1)[1], re.S)
    assert tag_links(lib) == [(t, "/treninzi/vjezbe?q=" + quote(t), False) for t in TAG_ORDER]
    assert 'data-tag="hip thurst"' not in lib and "q=hip" not in lib           # its exercise's row keeps it as a tag
    on = ct.get("/treninzi/vjezbe", params={"q": "GIRJA"}).text           # the whole of ?q=, folded
    assert [(t, on) for t, _, on in tag_links(on) if on] == [("girja", True)]
    assert '<a class="tag-chip" href="/treninzi/vjezbe" aria-current="true">girja</a>' in on
    two = ct.get("/treninzi/vjezbe", params={"q": "horizontalni   potisak"}).text
    assert [t for t, _, on in tag_links(two) if on] == ["horizontalni potisak"]
    assert not any(on for *_, on in tag_links(ct.get("/treninzi/vjezbe", params={"q": "girja noge"}).text))
    assert tag_row(on) == tag_row(lib)                                    # the script presses them: none served pressed

    day = ct.get(edit).text
    assert tag_row(day) == tag_row(lib) and tag_links(day) == [] and "<noscript>" not in day.split('id="dodaj"')[1]
    form = day.split('<form id="dodaj"')[1].split("</form>")[0]
    assert re.search(r'class="card add-ex">\s*' + re.escape(TAGBAR) + r'.*?</div>\s*<div class="add-fields">', form, re.S)   # above the fields


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
    back at the add card (25.11.2026: until then at its row); a choice
    that is no exercise, or a section that is none, adds nothing ("Odaberi
    vježbu iz baze.": in the card, a section that is none at the top). A row's form saves the
    section, sets, reps and / or seconds (both since 24.11.2026: their own
    test, below), rest and the note (stripped); an empty number is none.
    Refused with the sentence, the row unchanged: a number out of range or
    not a number ("Neispravan broj."), a note past 500, a section that is
    none. Moved to another section, it goes last in it;
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
        made[eid] = max(i.id for i in db.get_day(did).items)
        assert location(r) == (f"{base}/uredi?dodaj={section}&ok=Dodano u {SECTIONS[section]}: "
                               f"{db.get_day_item(made[eid]).exercise.name}.#dodaj")
    ia, ib, ic, id_ = (made[x] for x in (a, b, c, d))

    def layout():
        return {k: [i.id for i in v] for k, v in db.get_day(did).by_section.items()}

    assert layout() == {"zagrijavanje": [ib], "trening": [ia, ic], "trening_b": [], "trening_c": [], "istezanje": [id_]}
    assert [i.position for i in db.get_day(did).items] == [1, 2, 3, 4]
    assert [(i.sets, i.reps, i.seconds, i.rest_seconds, i.note) for i in db.get_day(did).items] == [(None, None, None, None, "")] * 4
    for bad, section in (("", "trening"), ("abc", "trening"), ("²", "trening"), ("987654", "trening"),
                         ("99999999999", "trening"), (str(a), "kardio")):
        r = ct.post(f"{base}/stavke", data={"exercise_id": bad, "section": section}, follow_redirects=False)
        to = f"{base}/uredi?error=Odaberi vježbu iz baze." if section == "kardio" else \
            f"{base}/uredi?dodaj=trening&error=Odaberi vježbu iz baze.#dodaj"
        assert location(r) == to, (bad, section)
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
                ({"sets": "3", "reps": "10", "seconds": "3601"}, "Neispravan broj."),
                ({"note": "x" * 501}, "Napomena može imati najviše 500 znakova."),
                ({"section": "kardio"}, "Odaberi dio treninga.")]
    for fields, sentence in refusals:
        r = save(ia, **fields)
        assert location(r) == f"{base}/uredi?error={sentence}&stavka={ia}#stavka-{ia}", fields
    assert stored(ia) == before
    assert ct.post(f"{base}/stavke/987654", data={"sets": "3"}).status_code == 404

    save(ia, section="zagrijavanje", sets="2", reps="15", rest="30")       # another section: last in it
    assert layout() == {"zagrijavanje": [ib, ia], "trening": [ic], "trening_b": [], "trening_c": [], "istezanje": [id_]}
    assert db.get_day_item(ia).position == 5
    r = ct.post(f"{base}/stavke/{ia}/pomak", data={"smjer": "gore"}, follow_redirects=False)
    assert r.headers["location"] == f"{base}/uredi#stavka-{ia}"
    assert layout()["zagrijavanje"] == [ia, ib]
    for item_id, smjer in ((ia, "gore"), (ib, "dolje"), (ic, "gore"), (ic, "dolje"), (id_, "gore"), (ia, "x")):
        assert not db.move_day_item(item_id, smjer), (item_id, smjer)      # never out of its section
    assert layout() == {"zagrijavanje": [ia, ib], "trening": [ic], "trening_b": [], "trening_c": [], "istezanje": [id_]}
    assert not db.move_day_item(987654, "gore")

    r = ct.post(f"{base}/stavke/{ic}/obrisi", follow_redirects=False)
    assert r.headers["location"] == f"{base}/uredi"
    assert layout() == {"zagrijavanje": [ia, ib], "trening": [], "trening_b": [], "trening_c": [], "istezanje": [id_]}
    assert db.exercise(c) is not None and not db.delete_day_item(ic)


def test_an_item_asks_for_reps_and_seconds_together():
    """Since 24.11.2026 (the owner: "5 reps of 30 seconds of plank"; until
    then "Upiši ponavljanja ili sekunde, ne oboje."), a row saves reps and
    seconds together, through its form and through db.update_day_item
    alike, each within its limits as ever; its form shows both, and its
    dose says them, "3 × 5 × 30 s" with sets and "5 × 30 s" without, on the
    client's day page too. Emptied, either goes alone again. The editor's
    lead says so: "Ponavljanja i sekunde mogu zajedno: 5 ponavljanja po 30
    s."."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    iid = hold(pid, db.create_exercise("Bočni plank 1. razina - bodyweight"))
    base = f"/treninzi/{pid}/dan/{did}"

    def save(**fields):
        data = {"section": "trening", "sets": "", "reps": "", "seconds": "", "rest": "", "rest_after": "", "note": ""}
        return ct.post(f"{base}/stavke/{iid}", data=data | fields, follow_redirects=False)

    def stored():
        it = db.get_day_item(iid)
        return it.sets, it.reps, it.seconds, it.rest_seconds, it.dose

    r = save(sets="3", reps="5", seconds="30", rest="60")                  # the owner's photo: 3 × 5 of 30 s
    assert location(r) == f"{base}/uredi?ok=Spremljeno.&stavka={iid}#stavka-{iid}"
    assert stored() == (3, 5, 30, 60, "3 × 5 × 30 s")
    page = ct.get(f"{base}/uredi").text
    assert "Ponavljanja i sekunde mogu zajedno: 5 ponavljanja po 30 s." in page
    form = page.split(f'id="stavka-{iid}"')[1].split('<form class="st-form"')[1].split("</form>")[0]
    assert {k: v for k, v in re.findall(r'name="(\w+)"[^>]*?value="([^"]*)"', form) if k in ("sets", "reps", "seconds")} == {
        "sets": "3", "reps": "5", "seconds": "30"}
    client_day = client_for("ivan@test.local").get(base).text
    assert '<span class="dx-name">Bočni plank 1. razina - bodyweight</span><span class="dx-dose">3 × 5 × 30 s</span>' in client_day
    assert db.update_day_item(iid, "trening", None, 5, 30, None, None, "")
    assert stored() == (None, 5, 30, None, "5 × 30 s")
    assert db.update_day_item(iid, "trening", 99, 999, 3600, 0, 0, "")     # each at its limit
    assert stored()[:3] == (99, 999, 3600)
    for sets, reps, seconds in ((3, 1000, 30), (3, 5, 3601), (3, 0, 30), (100, 5, 30)):
        with pytest.raises(ValueError, match="Neispravan broj."):
            db.update_day_item(iid, "trening", sets, reps, seconds, None, None, "")
    assert stored()[:3] == (99, 999, 3600)
    save(sets="3", seconds="30")                                            # reps emptied: seconds alone
    assert stored() == (3, None, 30, None, "3 × 30 s")
    save(sets="3", reps="5")                                                # seconds emptied: reps alone
    assert stored() == (3, 5, None, None, "3 × 5")


def test_an_item_asks_for_a_weight():
    """Since 25.11.2026 (the owner, for Amir's circuits: "the number of
    reps, the weight if applicable etc."; migration d0ed87d5c98f) an item
    may ask for a weight, `kg`: "Kilaža (kg)" on its row form after
    Ponavljanja and Sekunde, 0.5–500 in steps of 0.5, "2,5" or "2.5"
    (db.read_item_kg; the input's value with a point), empty none; anything
    else "Neispravan broj.", the row unchanged (db.update_day_item's own
    check too). A caller of update_day_item that names no weight keeps it.
    The dose says it after a middle dot, "3 × 10 · 20 kg", "10
    ponavljanja · 20 kg", "30 s · 20 kg", "3 × 5 × 30 s · 20 kg" (round_dose
    too: "5 × 30 s · 20 kg"), a half with a comma, the weight alone with
    nothing else; the client's day page prints it."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    iid = hold(pid, db.create_exercise("Goblet čučanj"))
    base = f"/treninzi/{pid}/dan/{did}"

    def save(**fields):
        data = {"section": "trening", "sets": "3", "reps": "10", "seconds": "", "kg": "", "rest": "", "rest_after": "",
                "note": ""}
        return ct.post(f"{base}/stavke/{iid}", data=data | fields, follow_redirects=False)

    def kg_of():
        return db.get_day_item(iid).kg

    for typed, kept in (("20", Decimal(20)), ("2,5", Decimal("2.5")), ("2.5", Decimal("2.5")), (" 0,5 ", Decimal("0.5")),
                        ("500", Decimal(500)), ("", None)):
        r = save(kg=typed)
        assert location(r) == f"{base}/uredi?ok=Spremljeno.&stavka={iid}#stavka-{iid}", typed
        assert kg_of() == kept, typed
    save(kg="22,5")
    form = ct.get(f"{base}/uredi").text.split(f'id="stavka-{iid}"')[1].split('<form class="st-form"')[1].split("</form>")[0]
    assert dict(re.findall(r'name="(\w+)"[^>]*?value="([^"]*)"', form))["kg"] == "22.5"
    for bad in ("0", "0,25", "500,5", "501", "-1", "abc", "2,55", "1e2", "²"):
        r = save(kg=bad)
        assert location(r) == f"{base}/uredi?error=Neispravan broj.&stavka={iid}#stavka-{iid}", bad
    assert kg_of() == Decimal("22.5")
    for bad in (0, Decimal("0.25"), Decimal("500.5"), 501, -1, True, "20"):
        with pytest.raises(ValueError, match="^Neispravan broj.$"):
            db.update_day_item(iid, "trening", 3, 10, None, None, None, "", kg=bad)
    assert db.update_day_item(iid, "trening", 4, 10, None, None, None, "")    # no weight named: kept
    assert kg_of() == Decimal("22.5")
    assert db.read_item_kg("") is None and db.read_item_kg(" ") is None and db.read_item_kg("2,5") == Decimal("2.5")
    page = client_for("ivan@test.local").get(base).text
    assert '<span class="dx-name">Goblet čučanj</span><span class="dx-dose">4 × 10 · 22,5 kg</span>' in page

    def doses(sets=None, reps=None, seconds=None, kg=None):
        it = ProgramDayItem(sets=sets, reps=reps, seconds=seconds, kg=kg)
        return it.dose, it.round_dose

    assert [doses(3, 10, kg=20), doses(None, 10, kg=20), doses(None, None, 30, kg=Decimal("20.0")), doses(3, 5, 30, kg=20),
            doses(3, kg=Decimal("2.5")), doses(kg=20), doses(3, 10)] == [
        ("3 × 10 · 20 kg", "10 ponavljanja · 20 kg"), ("10 ponavljanja · 20 kg", "10 ponavljanja · 20 kg"),
        ("30 s · 20 kg", "30 s · 20 kg"), ("3 × 5 × 30 s · 20 kg", "5 × 30 s · 20 kg"),
        ("3 serije · 2,5 kg", "2,5 kg"), ("20 kg", "20 kg"), ("3 × 10", "10 ponavljanja")]


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
    ca = client_for("ana@test.local")                                        # srednja: A is not hers
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
    assert ('Program ima treninge; svaki trening ima zagrijavanje, glavni dio A, B i C te istezanje, a vježbe biraš iz '
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
    assert ("Naslov, preporučeni dan u tjednu i uvod; ispod toga vježbe po dijelovima (zagrijavanje, glavni dio A, "
            "B i C te istezanje) — serije, ponavljanja, sekunde, kilaža, odmor i napomena.\n  Ponavljanja i sekunde "
            "mogu zajedno: 5 ponavljanja po 30 s.") in page
    assert "ili sekunde" not in page and "ne oboje" not in page                 # both may be set (24.11.2026)
    assert ("„Odmor (s)” je odmor između serija, a „Nakon vježbe (s)” odmor prije sljedeće vježbe: polaznik za oba "
            "dobiva odbrojavanje koje može preskočiti.") in page
    assert f'<a class="act act-quiet" href="/treninzi/{pid}/dan/{did}">pogledaj kako polaznik vidi →</a>' in page
    assert 'placeholder="npr. Cijelo tijelo"' in page and "Kratko objašnjenje treninga — polaznik ga gleda prije prve vježbe." in page
    assert re.findall(r'<h3 class="st-cap" id="dio-(\w+)">([^<]*)</h3>', page) == [
        ("zagrijavanje", "Zagrijavanje"), ("trening", "Glavni dio A"), ("trening_b", "Glavni dio B"),
        ("trening_c", "Glavni dio C"), ("istezanje", "Istezanje")]
    assert page.count('<p class="hint st-none">Nema vježbi.</p>') == 4
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
    assert '<option value="trening" selected>Glavni dio A</option>' in form and '<option value="zagrijavanje">Zagrijavanje</option>' in form
    assert '<option value="trening_b">Glavni dio B</option>' in form
    values = dict(re.findall(r'name="(\w+)"[^>]*?value="([^"]*)"', form))
    assert values == {"sets": "4", "reps": "10", "seconds": "", "kg": "", "rest": "60", "rest_after": "90",
                      "note": "16 kg"}
    assert 'name="sets" inputmode="numeric" min="1" max="99"' in form and 'name="reps" inputmode="numeric" min="1" max="999"' in form
    assert 'name="seconds" inputmode="numeric" min="1" max="3600"' in form and 'name="rest" inputmode="numeric" min="0" max="3600"' in form
    assert 'name="rest_after" inputmode="numeric" min="0" max="3600"' in form
    assert 'name="kg" inputmode="decimal" min="0.5" max="500" step="0.5"' in form
    assert [lab for lab in re.findall(r'<label for="st-\d+-\w+">([^<]*)</label>', form)] == [
        "Dio", "Serije", "Ponavljanja", "Sekunde", "Kilaža (kg)", "Odmor (s)", "Nakon vježbe (s)", "Napomena"]
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
    alphabet's order) and a select of the section, opening on Glavni dio A,
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
    assert sections == [("zagrijavanje", "", "Zagrijavanje"), ("trening", " selected", "Glavni dio A"),
                        ("trening_b", "", "Glavni dio B"), ("trening_c", "", "Glavni dio C"), ("istezanje", "", "Istezanje")]
    assert '<label for="add-ex">Vježba iz baze</label>' in page and '<label for="add-dio">Dio</label>' in page
    assert f'href="/treninzi/vjezbe/nova?natrag={edit}">Nova vježba →</a>' in page
    r = ct.post(f"/treninzi/{pid}/dan/{did}/stavke", data={"exercise_id": str(plank), "section": "istezanje"},
                follow_redirects=False)
    item = db.get_day(did).items[0]
    assert location(r) == f"{edit}?dodaj=istezanje&ok=Dodano u Istezanje: Plank.#dodaj"   # the add card (25.11.2026)
    assert (item.exercise_id, item.section, item.position, item.exercise.name) == (plank, "istezanje", 1, "Plank")
    assert (item.sets, item.reps, item.seconds, item.kg) == (None, None, None, None)      # nothing asked: none
    r = ct.post(f"/treninzi/{pid}/dan/{did}/stavke", data={"exercise_id": str(biceps)}, follow_redirects=False)
    assert db.get_day(did).items[1].section == "trening"                    # none named: trening
    page = ct.get(f"{edit}?vjezba={cucanj}").text
    assert f'<option value="{cucanj}" selected>Čučanj s vlastitom težinom</option>' in page
    assert '<option value="" disabled>Odaberi vježbu…</option>' in page


def test_an_exercise_is_added_inside_a_part_with_its_numbers():
    """"+ Dodaj vježbu u ovaj dio" (25.11.2026; the owner: "we need to allow
    Amir to add exercises which go into one circle of exercises. And for
    each of those exercises, the number of reps, the weight if applicable
    etc."): each part of the day editor ends with it, an .act link to the
    add card with that part chosen (?dodaj=<key>#dodaj: its Dio selected,
    the picker the page's autofocus; a key that is none, neither). The add
    card takes the numbers too, all optional: Serije, Ponavljanja, Sekunde,
    Kilaža (kg), so a row is complete in one step (db.add_day_item); after
    an add the page comes back to the card (?dodaj=<the part>#dodaj), its
    Dio as it was and its picker focused, the card saying "Dodano u Glavni
    dio A: Sklekovi." (the page's top none). A refused number adds nothing,
    its sentence in the card, the Dio and the exercise kept (?vjezba=); no
    exercise chosen "Odaberi vježbu iz baze.", in the card too."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    skl, plank = db.create_exercise("Sklekovi"), db.create_exercise("Plank")
    db.set_circuit(did, "trening", 3, 60)
    edit, add_url = f"/treninzi/{pid}/dan/{did}/uredi", f"/treninzi/{pid}/dan/{did}/stavke"
    page = ct.get(edit).text
    links = re.findall(r'<a class="act st-add" href="([^"]+)" data-dio="(\w+)">\+ Dodaj vježbu u ovaj dio</a>', page)
    assert links == [(f"{edit}?dodaj={k}#dodaj", k) for k in SECTIONS]
    for key in SECTIONS:                                                     # each its part's last line
        part = page.split(f'<section class="st-sec" aria-labelledby="dio-{key}">')[1].split("</section>")[0]
        assert part.rstrip().endswith(f'data-dio="{key}">+ Dodaj vježbu u ovaj dio</a>'), key

    def card(page: str) -> str:
        return page.split('<form id="dodaj"')[1].split("</form>")[0]

    add = card(page)
    assert '<option value="trening" selected>Glavni dio A</option>' in add and " autofocus" not in add
    assert re.findall(r'<label for="add-(\w+)">([^<]*)</label>', add) == [
        ("ex", "Vježba iz baze"), ("dio", "Dio"), ("sets", "Serije"), ("reps", "Ponavljanja"), ("secs", "Sekunde"),
        ("kg", "Kilaža (kg)")]
    nums = add.split('<div class="add-nums">')[1]
    for attrs in ('name="sets" inputmode="numeric" min="1" max="99"', 'name="reps" inputmode="numeric" min="1" max="999"',
                  'name="seconds" inputmode="numeric" min="1" max="3600"',
                  'name="kg" inputmode="decimal" min="0.5" max="500" step="0.5"'):
        assert attrs in nums, attrs
    add = card(ct.get(f"{edit}?dodaj=trening_b").text)
    assert '<option value="trening_b" selected>Glavni dio B</option>' in add and 'name="exercise_id" required autofocus>' in add
    add = card(ct.get(f"{edit}?dodaj=kardio").text)
    assert '<option value="trening" selected>Glavni dio A</option>' in add and " autofocus" not in add

    r = ct.post(add_url, data={"exercise_id": str(skl), "section": "trening", "sets": "", "reps": "10", "seconds": "",
                               "kg": "2,5"}, follow_redirects=False)
    assert location(r) == f"{edit}?dodaj=trening&ok=Dodano u Glavni dio A: Sklekovi.#dodaj"
    [it] = db.get_day(did).items
    assert (it.exercise_id, it.section, it.sets, it.reps, it.seconds, it.kg, it.rest_seconds, it.rest_after_seconds,
            it.note) == (skl, "trening", None, 10, None, Decimal("2.5"), None, None, "")
    page = ct.get(r.headers["location"].split("#")[0]).text
    assert page.count('<div class="alert') == 1                              # in the card, not at the top
    add = card(page)
    assert '<div class="alert ok" role="status">Dodano u Glavni dio A: Sklekovi.</div>' in add
    assert '<option value="trening" selected>Glavni dio A</option>' in add and 'required autofocus>' in add
    r = ct.post(add_url, data={"exercise_id": str(plank), "section": "trening", "sets": "3", "seconds": "40"},
                follow_redirects=False)
    assert location(r) == f"{edit}?dodaj=trening&ok=Dodano u Glavni dio A: Plank.#dodaj"
    assert [(i.exercise_id, i.sets, i.reps, i.seconds, i.kg, i.round_dose) for i in db.get_day(did).items] == [
        (skl, None, 10, None, Decimal("2.5"), "10 ponavljanja · 2,5 kg"), (plank, 3, None, 40, None, "40 s")]

    for field, value in (("sets", "0"), ("reps", "1000"), ("seconds", "3601"), ("kg", "0,25"), ("kg", "x"),
                         ("sets", "abc"), ("kg", "501")):
        r = ct.post(add_url, data={"exercise_id": str(plank), "section": "trening_b", field: value},
                    follow_redirects=False)
        assert location(r) == f"{edit}?dodaj=trening_b&error=Neispravan broj.&vjezba={plank}#dodaj", (field, value)
    assert len(db.get_day(did).items) == 2                                   # a refused number adds nothing
    page = ct.get(f"{edit}?dodaj=trening_b&error=Neispravan+broj.&vjezba={plank}").text
    add = card(page)
    assert page.count('<div class="alert') == 1 and '<div class="alert" role="alert"><span>Neispravan broj.</span></div>' in add
    assert '<option value="trening_b" selected>Glavni dio B</option>' in add and f'<option value="{plank}" selected>Plank</option>' in add
    r = ct.post(add_url, data={"exercise_id": "", "section": "istezanje", "reps": "10"}, follow_redirects=False)
    assert location(r) == f"{edit}?dodaj=istezanje&error=Odaberi vježbu iz baze.#dodaj"
    for numbers in ({"sets": 0}, {"reps": 1000}, {"seconds": 0}, {"kg": Decimal("0.25")}, {"kg": 600}):
        with pytest.raises(ValueError, match="^Neispravan broj.$"):
            db.add_day_item(did, skl, "trening_b", **numbers)
    assert len(db.get_day(did).items) == 2
    made = db.add_day_item(did, skl, "trening_b", 3, 10, None, 20)
    it = db.get_day_item(made)
    assert (it.section, it.position, it.sets, it.reps, it.seconds, it.kg, it.dose) == (
        "trening_b", 3, 3, 10, None, Decimal(20), "3 × 10 · 20 kg")


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
    assert '<p class="hint"><span class="t">Program još nema treninga.</span></p>' in page and "dodaj prvi" not in page
    trainers = ct.get(f"/treninzi/{pid}").text
    assert re.search(r'<p class="hint" data-opt>' + ed("program.empty_staff", "Program još nema treninga — dodaj prvi u uređivanju.")
                     + "</p>", trainers)
    assert re.search(f'<a class="btn btn-quiet btn-sm" href="/treninzi/{pid}/uredi">' + ed("program.edit", "Uredi program")
                     + "</a>", trainers)
    d1, d2, d3 = db.add_day(pid), db.add_day(pid), db.add_day(pid)
    db.update_day(d1, "Cijelo tijelo", 0, "")
    db.update_day(d3, "", 4, "")
    exercises = [db.create_exercise(f"Vježba {n}") for n in range(8)]
    for n, eid in enumerate(exercises):
        hold(pid, eid, day=1 if n < 2 else 2 if n < 3 else 3)
    page = ci.get(f"/treninzi/{pid}").text
    assert '<p class="hint" style="margin-bottom:6px;">3 treninga</p>' in page
    cards = [(href, day, read(hint)) for href, day, hint in re.findall(
        r'<a class="card day-card" href="([^"]+)">\s*<span class="dc-main">\s*<strong>([^<]*)</strong>\s*'
        r'<span class="hint">(.*?)</span>\s*</span>\s*<span class="dc-go"', page, re.S)]
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
    assert '<p class="hint"><span class="t">Preporučeno:</span> ponedjeljak · 3 vježbe</p>' in page
    assert '<p class="day-intro">Lagano.\nBez žurbe.</p>' in page and "Uredi trening" not in page
    assert "<title>Trening 1 · Cijelo tijelo — Tjedan 1 — QMT</title>" in page
    assert re.findall(r'<h2 class="dx-cap" id="dio-(\w+)">([^<]*)</h2>', page) == [   # none in B: no B
        ("zagrijavanje", "Zagrijavanje"), ("trening", "Glavni dio A"), ("istezanje", "Istezanje")]
    rows = page.split('<details class="card ex">')[1:]
    heads = [re.search(r'<span class="dx-n">([^<]*)</span>\s*<span class="dx-line"><span class="dx-name">([^<]*)</span>'
                       r'(?:<span class="dx-dose">([^<]*)</span>)?</span>', r).groups() + (sub(r),)
             for r in rows]
    assert heads == [("Vježba 1", "Goblet čučanj", "2 × 15", "Odmor između serija: 30 s · 8 kg"),
                     ("Vježba 2", "Plank", "3 × 40 s", "Odmor između serija: 45 s"),
                     ("Vježba 3", "Istezanje stražnje lože", "30 s", "po nozi")]
    assert '<span class="dx-go" aria-hidden="true">▷</span>' in rows[0]
    assert f'<video src="/media/{clip}" controls playsinline preload="none"></video>' in rows[0]
    assert '<strong><span class="t">Jedno ponavljanje:</span></strong> Do paralele i natrag.</p>' in rows[0]
    assert '<p class="pre">Pete na podu.\nTrup uspravan.</p>' in rows[0]
    assert "Vježba još nema videa." in rows[1] and "<video" not in rows[1] and "Jedno ponavljanje" not in rows[1]
    assert '<p class="pre">Lopatice aktivne.</p>' in rows[1] and "Vježba još nema videa." in rows[2]
    assert ci.get(f"/media/{clip}").status_code == 200
    assert re.search(f'<a class="btn btn-quiet btn-sm" href="/treninzi/{pid}/dan/{did}/uredi">' + ed("dan.edit", "Uredi trening")
                     + "</a>", ct.get(f"/treninzi/{pid}/dan/{did}").text)

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
        page = client_for("ivan@test.local").get(base).text
        return [s for s in (sub(r) for r in page.split('<details class="card ex">')[1:]) if s is not None]

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
    assert ('<p class="hint"><span class="t">Uvodni video — pogledaj ga prije treninga.</span></p>\n'
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


def test_a_day_has_three_main_parts_a_b_and_c():
    """Since 23.11.2026 (the owner, for Amir: "an option to add 'glavni dio
    A' and 'glavni dio B', so two separate main parts of a training") and
    26.11.2026 ("Lets have Glavni dio A, B and C"): a day's sections are
    five, trening reading "Glavni dio A" (every item already there in it),
    trening_b "Glavni dio B" and trening_c "Glavni dio C" after them.
    add_day_item takes trening_c (an item put there first still reads after
    A and B: the order is the parts', not the positions') and refuses a part
    that is none (None, nothing added); update_day_item moves an item into
    C, last in it, and refuses a part that is none with "Odaberi dio
    treninga.", as a row's form does; C may be a circuit. The day's page
    captions the parts that hold an exercise, A, B, then C, counting the
    exercises across them, and so does the player's list, C's rounds the
    last steps; the editor captions all five, and every Dio select offers
    them, "Dodaj vježbu"'s opening on Glavni dio A."""
    ct, ivan, _ = trainer_with_clients()
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")   # ivan's: pocetna / cijelo
    did = db.add_day(pid)
    ex = {n: db.create_exercise(n) for n in ("Goblet čučanj", "Plank", "Sklekovi", "Iskorak", "Most")}
    c1 = db.add_day_item(did, ex["Iskorak"], "trening_c")                 # C's first, before A's and B's
    a1 = db.add_day_item(did, ex["Goblet čučanj"], "trening")
    b1 = db.add_day_item(did, ex["Plank"], "trening_b")
    a2 = db.add_day_item(did, ex["Sklekovi"], "trening")
    assert None not in (c1, a1, b1, a2)
    assert db.add_day_item(did, ex["Most"], "trening_d") is None and len(db.get_day(did).items) == 4

    def layout() -> dict[str, list[str]]:
        return {k: [i.exercise.name for i in v] for k, v in db.get_day(did).by_section.items()}

    assert layout() == {"zagrijavanje": [], "trening": ["Goblet čučanj", "Sklekovi"], "trening_b": ["Plank"],
                        "trening_c": ["Iskorak"], "istezanje": []}
    base = f"/treninzi/{pid}/dan/{did}"
    edit = f"{base}/uredi"
    r = ct.post(f"{base}/stavke/{a2}", data={"section": "trening_c", "sets": "3", "reps": "10"},
                follow_redirects=False)                                     # a row's Dio: into C, last in it
    assert unquote(r.headers["location"]) == f"{edit}?ok=Spremljeno.&stavka={a2}#stavka-{a2}"
    assert layout() == {"zagrijavanje": [], "trening": ["Goblet čučanj"], "trening_b": ["Plank"],
                        "trening_c": ["Iskorak", "Sklekovi"], "istezanje": []}
    with pytest.raises(ValueError, match="Odaberi dio treninga."):
        db.update_day_item(a1, "trening_d", None, None, None, None, None, "")
    r = ct.post(f"{base}/stavke/{a1}", data={"section": "trening_d"}, follow_redirects=False)
    assert unquote(r.headers["location"]) == f"{edit}?error=Odaberi dio treninga.&stavka={a1}#stavka-{a1}"
    assert db.get_day_item(a1).section == "trening"
    r = ct.post(f"{base}/dio/trening_c/krug", data={"circuit": "1", "rounds": "2", "rest": "30"},
                follow_redirects=False)                                     # C as a circuit
    assert location(r) == f"{edit}?ok=Spremljeno.&dio=trening_c#dio-trening_c" and circuits_of(did) == {"trening_c": (2, 30)}

    ci = client_for("ivan@test.local")
    page = ci.get(base).text
    assert re.findall(r'<h2 class="dx-cap" id="dio-(\w+)">([^<]*)</h2>', page) == [
        ("trening", "Glavni dio A"), ("trening_b", "Glavni dio B"), ("trening_c", "Glavni dio C")]
    assert re.search(r'<h2 class="dx-cap" id="dio-trening_c">Glavni dio C</h2>\s*<p class="dx-circ">Kružno · 2 kruga · '
                     r'odmor između krugova 30 s</p>', page)
    assert re.findall(r'<span class="dx-n">([^<]*)</span>\s*<span class="dx-line"><span class="dx-name">([^<]*)</span>', page) == [
        ("Vježba 1", "Goblet čučanj"), ("Vježba 2", "Plank"), ("Vježba 3", "Iskorak"), ("Vježba 4", "Sklekovi")]
    ci.post(f"{base}/kreni")
    day = db.get_day(did)
    assert [(s.item.id if s.item else None, s.round) for s in web_steps(day)] == [
        (a1, None), (b1, None), (None, 1), (None, 2)]                       # A, B, then C's two rounds
    player = ci.get(f"{base}/vjezba/1").text
    assert [read(h) for h in re.findall(r'<h3 class="dx-cap">(.*?)</h3>', player)] == [
        "Glavni dio A", "Glavni dio B", "Glavni dio C · kružno · 2 kruga"]
    assert re.findall(r'<span class="dx-name">([^<]*?)(?: <span|</span>)', player.split('id="popis"')[1]) == [
        "Goblet čučanj", "Plank", "Iskorak", "Sklekovi"]
    round_one = ci.get(f"{base}/vjezba/3").text
    assert '<h1 class="pl-name" id="pl-name">Glavni dio C</h1>' in round_one and "Krug 1 od 2" in round_one
    assert "<title>Glavni dio C — Trening 1 — QMT</title>" in round_one

    page = ct.get(edit).text
    assert re.findall(r'<h3 class="st-cap" id="dio-(\w+)">([^<]*)</h3>', page) == [
        ("zagrijavanje", "Zagrijavanje"), ("trening", "Glavni dio A"), ("trening_b", "Glavni dio B"),
        ("trening_c", "Glavni dio C"), ("istezanje", "Istezanje")]
    for select in re.findall(r'<select id="(?:st-\d+-dio|add-dio)" name="section">(.*?)</select>', page, re.S):
        assert re.findall(r'<option value="(\w+)"', select) == ["zagrijavanje", "trening", "trening_b", "trening_c",
                                                                "istezanje"]
    add = page.split('id="add-dio"')[1].split("</select>")[0]
    assert '<option value="trening" selected>Glavni dio A</option>' in add and '<option value="trening_c">Glavni dio C</option>' in add


def web_steps(day) -> list:
    """The player's steps through a day as the routes make them (app._steps
    over its exercises in display order)."""
    from qmt.web import app as web
    return web._steps(day, web._day_items(day))


# ---------- a part as a circuit (24.11.2026, kružni trening) ----------

def circuits_of(did: int) -> dict[str, tuple]:
    """A day's circuits as stored: section -> (rounds, rest between rounds)."""
    with db.engine.connect() as conn:
        return {s: (r, t) for s, r, t in conn.execute(sa_text(
            "SELECT section, rounds, rest_seconds FROM program_day_circuits WHERE day_id = :d"), {"d": did})}


def test_a_part_is_made_a_circuit_and_a_normal_one_again():
    """db.set_circuit makes a part of a day a circuit: 2–20 rounds and a rest
    between rounds of 0–3600 s or none, a part that is one taking the new
    numbers; db.clear_circuit makes it a normal one again (nothing to do
    for one that is none). Each moves the programme's updated_at. Refused
    with the sentence, nothing changed: rounds outside 2–20 or none or no
    integer, a rest outside 0–3600 ("Neispravan broj."), a section that is
    none ("Odaberi dio treninga."); a day that is gone is False. The day
    reads them (circuit(section), has_circuit: a circuit on a part that
    holds an exercise) and says them ("Kružno · 3 kruga · odmor između
    krugova 120 s", the rest only when set); a day deleted takes them (the
    CASCADE). The item's sets and rest between sets stay stored all along.
    Its round dose is its dose without its sets."""
    pid = db.create_program("T", None, "pocetna", "cijelo")
    iid = hold(pid, db.create_exercise("Goblet čučanj"))
    did = db.get_program(pid).days[0].id
    db.update_day_item(iid, "trening", 3, 10, None, 60, 15, "16 kg")
    assert not db.get_day(did).has_circuit and db.get_day(did).circuit("trening") is None

    before = updated(pid)
    assert db.set_circuit(did, "trening", 3, 120) and circuits_of(did) == {"trening": (3, 120)}
    assert updated(pid) > before
    day = db.get_day(did)
    assert (day.circuit("trening").line, day.circuit("trening").rounds_text, day.circuit("istezanje")) == (
        "Kružno · 3 kruga · odmor između krugova 120 s", "3 kruga", None)
    assert day.has_circuit
    assert db.set_circuit(did, "trening", 20, None) and circuits_of(did) == {"trening": (20, None)}   # one row, new numbers
    assert db.get_day(did).circuit("trening").line == "Kružno · 20 krugova"                       # no rest: none said
    assert db.set_circuit(did, "trening", 2, 0)
    assert db.get_day(did).circuit("trening").line == "Kružno · 2 kruga · odmor između krugova 0 s"
    assert db.set_circuit(did, "istezanje", 5, 3600) and circuits_of(did) == {"trening": (2, 0), "istezanje": (5, 3600)}
    assert db.get_day(did).circuit("istezanje").rounds_text == "5 krugova"
    for rounds, rest in ((1, 60), (21, 60), (0, None), (None, 60), (True, 60), (3.0, 60), (3, -1), (3, 3601), (3, 1.5)):
        with pytest.raises(ValueError, match="^Neispravan broj.$"):
            db.set_circuit(did, "trening", rounds, rest)
    for call in (lambda: db.set_circuit(did, "kardio", 3, 60), lambda: db.clear_circuit(did, "kardio"),
                 lambda: db.set_circuit(did, "kardio", 99, 60)):
        with pytest.raises(ValueError, match="^Odaberi dio treninga.$"):
            call()
    assert circuits_of(did) == {"trening": (2, 0), "istezanje": (5, 3600)}
    assert not db.set_circuit(987654, "trening", 3, 60) and not db.clear_circuit(987654, "trening")

    before = updated(pid)
    assert db.clear_circuit(did, "trening") and circuits_of(did) == {"istezanje": (5, 3600)} and updated(pid) > before
    assert db.clear_circuit(did, "trening") and circuits_of(did) == {"istezanje": (5, 3600)}     # none: nothing to do
    assert not db.get_day(did).has_circuit             # istezanje is one, and holds no exercise
    it = db.get_day_item(iid)
    assert (it.sets, it.reps, it.rest_seconds, it.rest_after_seconds, it.note) == (3, 10, 60, 15, "16 kg")

    def round_dose(sets=None, reps=None, seconds=None):
        return ProgramDayItem(sets=sets, reps=reps, seconds=seconds).round_dose

    assert [round_dose(3, 10), round_dose(3, None, 30), round_dose(3, 5, 30), round_dose(None, 1), round_dose(None, 5, 30),
            round_dose(3), round_dose()] == ["10 ponavljanja", "30 s", "5 × 30 s", "1 ponavljanje", "5 × 30 s", "", ""]

    db.set_circuit(did, "trening", 3, 60)
    other = db.add_day(pid)
    db.set_circuit(other, "trening", 2, None)
    db.delete_day(did)                                  # the CASCADE: its circuits go with it, another day's stay
    assert circuits_of(did) == {} and circuits_of(other) == {"trening": (2, None)}


def circuit_section(page: str, key: str) -> str:
    """The day editor's part `key`: its caption to its first row."""
    return page.split(f'<section class="st-sec" aria-labelledby="dio-{key}">')[1].split('<div class="st-rows">')[0]


def test_the_editor_makes_a_part_a_circuit_and_back():
    """The day editor (24.11.2026): under every part's caption a <details
    class="st-circ"> whose summary says the part's state, "Kružno:
    isključeno", or "Kružno · 3 kruga · odmor između krugova 120 s" (.on),
    and whose one form (POST …/dio/<key>/krug: "Kružni dio", Krugova 3 when
    new, "Odmor između krugova (s)" empty for none, Spremi) makes the part a
    circuit or, unticked, a normal one again, whatever the numbers say. The
    save comes back at the part (?dio=<key>#dio-<key>), its alert printed
    there and none at the top, the details open after a refusal
    ("Neispravan broj.": rounds 1, 21, none or no number, a rest of 3601;
    nothing changed); a section that is none comes back at the top
    ("Odaberi dio treninga."), a day of another programme 404, a client
    403 and a guest to log in. Both leads say a part can be a circuit."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    hold(pid, db.create_exercise("Goblet čučanj"))
    did = db.get_program(pid).days[0].id
    edit, base = f"/treninzi/{pid}/dan/{did}/uredi", f"/treninzi/{pid}/dan/{did}"
    lead = "Svaki dio može biti kružni: vježbe idu jedna za drugom, s odmorom između krugova."
    page = ct.get(edit).text
    assert lead in page and lead in ct.get(f"/treninzi/{pid}/uredi").text
    for key in SECTIONS:
        part = circuit_section(page, key)
        assert '<details class="st-circ">\n    <summary>Kružno: isključeno</summary>' in part, key
        assert f'<form class="st-circ-form" method="post" action="{base}/dio/{key}/krug">' in part
        assert '<label class="st-check"><input type="checkbox" name="circuit" value="1"> Kružni dio</label>' in part
        assert re.search(rf'<label for="krug-{key}-rounds">Krugova</label>\s*<input id="krug-{key}-rounds" type="number" '
                         r'name="rounds" inputmode="numeric" min="2" max="20"\s*value="3">', part)
        assert re.search(rf'<label for="krug-{key}-rest">Odmor između krugova \(s\)</label>\s*<input id="krug-{key}-rest" '
                         r'type="number" name="rest" inputmode="numeric" min="0" max="3600"\s*value="">', part)
        assert '<div class="st-go"><button type="submit" class="btn btn-sm">Spremi</button></div>' in part
        assert "st-circ-hint" not in part and " open>" not in part

    r = ct.post(f"{base}/dio/trening/krug", data={"circuit": "1", "rounds": "3", "rest": "120"}, follow_redirects=False)
    assert location(r) == f"{edit}?ok=Spremljeno.&dio=trening#dio-trening" and circuits_of(did) == {"trening": (3, 120)}
    page = ct.get(f"{edit}?ok=Spremljeno.&dio=trening").text
    assert page.count('<div class="alert ok') == 1                          # in the part, not at the top
    part = circuit_section(page, "trening")
    assert re.search(r'<h3 class="st-cap" id="dio-trening">Glavni dio A</h3>\s*'
                     r'<div class="alert ok st-alert" role="status">Spremljeno.</div>\s*<div class="st-tools">\s*'
                     r'<details class="st-circ on">\s*'
                     r'<summary>Kružno · 3 kruga · odmor između krugova 120 s</summary>', part)
    assert 'name="circuit" value="1" checked> Kružni dio' in part and re.search(r'name="rounds"[^>]*value="3"', part)
    assert re.search(r'name="rest"[^>]*value="120"', part) and " open>" not in part
    assert "Kružno: isključeno" in circuit_section(page, "zagrijavanje")
    ct.post(f"{base}/dio/trening/krug", data={"circuit": "1", "rounds": "20", "rest": ""})
    assert circuits_of(did) == {"trening": (20, None)}
    assert "<summary>Kružno · 20 krugova</summary>" in circuit_section(ct.get(edit).text, "trening")
    assert re.search(r'name="rest"[^>]*value=""', circuit_section(ct.get(edit).text, "trening"))

    for data in ({"rounds": "1"}, {"rounds": "21"}, {"rounds": ""}, {"rounds": "abc"}, {"rounds": "3.5"}, {"rest": "3601"},
                 {"rest": "-5"}, {"rest": "x"}):
        r = ct.post(f"{base}/dio/trening/krug", data={"circuit": "1", "rounds": "3", "rest": "60", **data}, follow_redirects=False)
        assert location(r) == f"{edit}?error=Neispravan broj.&dio=trening#dio-trening", data
    assert circuits_of(did) == {"trening": (20, None)}
    page = ct.get(f"{edit}?error=Neispravan+broj.&dio=trening").text
    assert page.count('<div class="alert') == 1
    part = circuit_section(page, "trening")
    assert '<div class="alert st-alert" role="alert"><span>Neispravan broj.</span></div>' in part
    assert '<details class="st-circ on" open>' in part                       # its form open again
    assert '<details class="st-circ">' in circuit_section(page, "istezanje")  # the others closed
    r = ct.post(f"{base}/dio/kardio/krug", data={"circuit": "1", "rounds": "3"}, follow_redirects=False)
    assert location(r) == f"{edit}?error=Odaberi dio treninga."              # no such part: the top
    page = ct.get(f"{edit}?error=Odaberi+dio+treninga.&dio=kardio").text
    assert page.count('<div class="alert') == 1 and 'class="alert st-alert"' not in page

    r = ct.post(f"{base}/dio/trening/krug", data={"rounds": "abc", "rest": "x"}, follow_redirects=False)   # unticked
    assert location(r) == f"{edit}?ok=Spremljeno.&dio=trening#dio-trening" and circuits_of(did) == {}
    assert "<summary>Kružno: isključeno</summary>" in circuit_section(ct.get(edit).text, "trening")
    other = db.create_program("B", None, "pocetna", "cijelo")
    assert ct.post(f"/treninzi/{other}/dan/{did}/dio/trening/krug", data={"circuit": "1", "rounds": "3"}).status_code == 404
    ci, anon = client_for("ivan@test.local"), TestClient(app)
    assert ci.post(f"{base}/dio/trening/krug", data={"circuit": "1", "rounds": "3"}).status_code == 403
    r = anon.post(f"{base}/dio/trening/krug", data={"circuit": "1", "rounds": "3"}, follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/login") and circuits_of(did) == {}


def test_a_circuit_parts_rows_ask_no_sets_and_no_rests_and_keep_them():
    """In a circuit part a muted hint says what changes (since 25.11.2026:
    "U kružnom dijelu vježbe idu jedna za drugom, bez pauze: upiši
    ponavljanja ili sekunde i kilažu. Odmor je nakon kruga."), and each
    row's form asks no Serije, no Odmor (s) (24.11.2026) and no Nakon vježbe
    (s) (25.11.2026: no pause between a circuit's exercises), none of which
    applies there: Dio, Ponavljanja, Sekunde, Kilaža (kg), Napomena,
    Spremi, and a hidden `circuit`. Its save keeps the item's stored sets,
    rest between sets and rest after it (into a normal part too, where they
    apply again), the other numbers saved as ever; a normal part's rows ask
    all of them, as before."""
    ct, *_ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    goblet, plank = hold(pid, db.create_exercise("Goblet čučanj")), hold(pid, db.create_exercise("Plank"), "trening_b")
    did = db.get_program(pid).days[0].id
    db.update_day_item(goblet, "trening", 3, 10, None, 60, 15, "16 kg")
    db.update_day_item(plank, "trening_b", 3, None, 40, 45, 90, "")
    db.set_circuit(did, "trening", 3, 120)
    edit, base = f"/treninzi/{pid}/dan/{did}/uredi", f"/treninzi/{pid}/dan/{did}"
    page = ct.get(edit).text
    hint = ("U kružnom dijelu vježbe idu jedna za drugom, bez pauze: upiši ponavljanja ili sekunde i kilažu. "
            "Odmor je nakon kruga.")
    assert f'<p class="hint st-circ-hint">{hint}</p>' in circuit_section(page, "trening")
    assert page.count('<p class="hint st-circ-hint">') == 1                 # the circuit part's alone

    def form_of(page: str, iid: int) -> str:
        return page.split(f'id="stavka-{iid}"')[1].split('<form class="st-form"')[1].split("</form>")[0]

    circ_form, normal_form = form_of(page, goblet), form_of(page, plank)
    assert re.findall(r'<label for="st-\d+-\w+">([^<]*)</label>', circ_form) == [
        "Dio", "Ponavljanja", "Sekunde", "Kilaža (kg)", "Napomena"]
    assert '<input type="hidden" name="circuit" value="1">' in circ_form and 'name="sets"' not in circ_form
    assert 'name="rest"' not in circ_form and 'name="rest_after"' not in circ_form
    assert '<div class="st-go"><button type="submit" class="btn btn-sm">Spremi</button></div>' in circ_form
    assert dict(re.findall(r'name="(\w+)"[^>]*?value="([^"]*)"', circ_form)) == {
        "circuit": "1", "reps": "10", "seconds": "", "kg": "", "note": "16 kg"}
    assert re.findall(r'<label for="st-\d+-\w+">([^<]*)</label>', normal_form) == [
        "Dio", "Serije", "Ponavljanja", "Sekunde", "Kilaža (kg)", "Odmor (s)", "Nakon vježbe (s)", "Napomena"]
    assert 'name="circuit"' not in normal_form

    def stored(iid):
        it = db.get_day_item(iid)
        return it.section, it.sets, it.reps, it.seconds, it.rest_seconds, it.rest_after_seconds, it.note, it.kg

    r = ct.post(f"{base}/stavke/{goblet}", data={"circuit": "1", "section": "trening", "reps": "12", "seconds": "",
                                                 "kg": "20", "note": "pete na podu", "sets": "9", "rest": "9",
                                                 "rest_after": "9"}, follow_redirects=False)
    assert location(r) == f"{edit}?ok=Spremljeno.&stavka={goblet}#stavka-{goblet}"
    assert stored(goblet) == ("trening", 3, 12, None, 60, 15, "pete na podu", 20)   # the three kept, whatever is posted
    r = ct.post(f"{base}/stavke/{goblet}", data={"circuit": "1", "section": "trening", "reps": "0"}, follow_redirects=False)
    assert location(r) == f"{edit}?error=Neispravan broj.&stavka={goblet}#stavka-{goblet}"
    assert stored(goblet) == ("trening", 3, 12, None, 60, 15, "pete na podu", 20)
    ct.post(f"{base}/stavke/{goblet}", data={"circuit": "1", "section": "trening_b", "reps": "12", "kg": "20"})
    assert stored(goblet) == ("trening_b", 3, 12, None, 60, 15, "", 20)    # into a normal part: they apply again
    form = form_of(ct.get(edit).text, goblet)
    values = dict(re.findall(r'name="(\w+)"[^>]*?value="([^"]*)"', form))
    assert (values["sets"], values["rest"], values["rest_after"], values["kg"]) == ("3", "60", "15", "20")
    assert 'name="circuit"' not in form
    ct.post(f"{base}/stavke/{plank}", data={"section": "trening_b", "sets": "", "reps": "", "seconds": "40", "rest": "",
                                            "rest_after": "", "note": ""})
    assert stored(plank) == ("trening_b", None, None, 40, None, None, "", None)   # a normal part's form: as ever


def test_the_day_page_and_the_programme_say_a_circuit():
    """A circuit part on the client's day page (24.11.2026): its caption,
    then the muted line "Kružno · 3 kruga · odmor između krugova 120 s" (the
    rest only when set), its rows the dose of a round ("10 ponavljanja",
    "40 s", "5 × 30 s") and under it the note alone (since 25.11.2026 no
    rest of an exercise's applies there: no pause between a circuit's
    exercises); a normal part as before. The day's
    lead and its card on the programme's page say "kružni trening"; a
    circuit on a part that holds no exercise does not. While a pass is open
    a circuit's row is "2/3" (muted, its words for a screen reader) when
    some of its rounds are saved and "✓" when all are; a normal row's ✓ as
    before."""
    ct, ivan, _ = trainer_with_clients()
    pid = db.create_program("Tjedan 1", None, "pocetna", "cijelo")
    ex = {n: db.create_exercise(n) for n in ("Čučanj", "Goblet čučanj", "Plank", "Bočni plank")}
    warm = hold(pid, ex["Čučanj"], "zagrijavanje")
    goblet, plank, side = (hold(pid, ex[n]) for n in ("Goblet čučanj", "Plank", "Bočni plank"))
    did = db.get_program(pid).days[0].id
    db.update_day(did, "Cijelo tijelo", 0, "")
    db.update_day_item(warm, "zagrijavanje", 2, 15, None, 30, 20, "")
    db.update_day_item(goblet, "trening", 3, 10, None, 60, 15, "16 kg")
    db.update_day_item(plank, "trening", 3, None, 40, 45, None, "")
    db.update_day_item(side, "trening", 2, 5, 30, 30, 10, "")
    ci = client_for("ivan@test.local")
    base = f"/treninzi/{pid}/dan/{did}"

    def heads(page: str) -> list[tuple]:
        return [re.search(r'<span class="dx-n">([^<]*)</span>\s*<span class="dx-line"><span class="dx-name">([^<]*)</span>'
                          r'(?:<span class="dx-dose">(.*?)</span>)?</span>', r).groups() + (sub(r),)
                for r in page.split('<details class="card ex">')[1:]]

    def card(page: str) -> str:
        return read(re.findall(r'<strong>[^<]*</strong>\s*<span class="hint">(.*?)</span>\s*</span>\s*<span class="dc-go"',
                               page, re.S)[0])

    db.set_circuit(did, "istezanje", 3, 60)                                 # a part that holds nothing: no circuit to do
    page = ci.get(base).text
    assert '<p class="hint"><span class="t">Preporučeno:</span> ponedjeljak · 4 vježbe</p>' in page and "kružn" not in page.split("<main")[1]
    assert card(ci.get(f"/treninzi/{pid}").text) == "Preporučeno: ponedjeljak · 4 vježbe"

    db.set_circuit(did, "trening", 3, 120)
    page = ci.get(base).text
    assert '<p class="hint"><span class="t">Preporučeno:</span> ponedjeljak · 4 vježbe · <span class="t">kružni trening</span></p>' in page
    assert card(ci.get(f"/treninzi/{pid}").text) == "Preporučeno: ponedjeljak · 4 vježbe · kružni trening"
    assert re.search(r'<h2 class="dx-cap" id="dio-trening">Glavni dio A</h2>\s*'
                     r'<p class="dx-circ">Kružno · 3 kruga · odmor između krugova 120 s</p>\s*<div class="dx-list">', page)
    assert page.count('class="dx-circ"') == 1                               # the warm-up is a normal part
    assert heads(page) == [("Vježba 1", "Čučanj", "2 × 15", "Odmor između serija: 30 s · Odmor nakon vježbe: 20 s"),
                           ("Vježba 2", "Goblet čučanj", "10 ponavljanja", "16 kg"),
                           ("Vježba 3", "Plank", "40 s", None),
                           ("Vježba 4", "Bočni plank", "5 × 30 s", None)]
    db.set_circuit(did, "trening", 2, None)
    assert '<p class="dx-circ">Kružno · 2 kruga</p>' in ci.get(base).text

    db.set_circuit(did, "trening", 3, 120)
    ci.post(f"{base}/kreni")
    log = db.open_pass(ivan, did)
    db.save_sets(log.id, ivan, db.get_day_item(warm), [{"reps": 15, "kg": 0.0}], db.exercise(ex["Čučanj"]))
    items = db.get_day(did).by_section["trening"]                           # one write a round (25.11.2026)
    for r, goblet_set in ((1, {"reps": 10, "kg": 16.0}), (2, {"reps": 10, "kg": 16.0}), (3, None)):
        db.save_circuit_round(log.id, ivan, items, r, {goblet: goblet_set, plank: {"seconds": 40}, side: None})
    page = ci.get(base).text
    assert [h[2] for h in heads(page)] == [
        '<span class="dx-ok" role="img" aria-label="spremljeno">✓</span> 2 × 15',
        '<span class="dx-rounds" role="img" aria-label="spremljeno 2 od 3 kruga">2/3</span> 10 ponavljanja',
        '<span class="dx-ok" role="img" aria-label="spremljeno">✓</span> 40 s', "5 × 30 s"]
    db.set_circuit(did, "trening", 5, 120)                                  # five rounds: "od 5 krugova"
    assert 'aria-label="spremljeno 2 od 5 krugova">2/5</span>' in ci.get(base).text
    assert 'aria-label="spremljeno 3 od 5 krugova">3/5</span>' in ci.get(base).text


# ---------- a part's own name and a dvoranski day's slots (26.11.2026, build 2) ----------
# The owner: "Lets have Glavni dio A, B and C but lets also allow Amir to
# rename them."; and for the gym trainings, templates "with no particular
# exercises connected to them … only slots to put them in."

def gym_day(title: str = "Predložak", level: str = "pocetna"):
    """A dvoranski programme (staff's own: no client lists or opens it) and
    its Trening 1: (pid, did, its page, its editor)."""
    pid = db.create_program(title, None, level, "cijelo", "dvorana")
    did = db.add_day(pid)
    base = f"/treninzi/{pid}/dan/{did}"
    return pid, did, base, f"{base}/uredi"


def parts_of(did: int) -> dict[str, str]:
    """A day's parts' own names as stored: section -> title."""
    with db.engine.connect() as conn:
        return dict(conn.execute(sa_text("SELECT section, title FROM program_day_parts WHERE day_id = :d"),
                                 {"d": did}).all())


def test_a_part_takes_a_name_of_its_own_on_its_day_alone():
    """db.set_part_name: a part of a day takes a name of its own, which
    ProgramDay.part_label says in place of the default ("Glavni dio A") and
    part_title alone; a new name replaces it (one row), an empty one deletes
    the row, the default back. The name is cleaned to one line; 60
    characters are taken, 61 refused ("Najviše 60 znakova.", nothing
    changed); a section that is none is refused ("Odaberi dio treninga."), a
    day that is gone False. Each save moves the programme's updated_at.
    Another day of the same programme keeps the defaults; a day deleted
    takes its names (CASCADE)."""
    pid, did, *_ = gym_day()
    other = db.add_day(pid)
    day = db.get_day(did)
    assert [day.part_label(k) for k in SECTIONS] == list(SECTIONS.values()) and day.part_title("trening") == ""
    before = updated(pid)
    assert db.set_part_name(did, "trening", "Krug 1") and parts_of(did) == {"trening": "Krug 1"} and updated(pid) > before
    day = db.get_day(did)
    assert (day.part_label("trening"), day.part_title("trening"), day.part_label("trening_b")) == (
        "Krug 1", "Krug 1", "Glavni dio B")
    assert db.set_part_name(did, "trening", "Krug 2") and parts_of(did) == {"trening": "Krug 2"}     # changed: one row
    assert db.set_part_name(did, "istezanje", "  Opuštanje \n i   disanje ")
    assert parts_of(did)["istezanje"] == "Opuštanje i disanje"
    assert db.set_part_name(did, "trening_c", "x" * 60) and parts_of(did)["trening_c"] == "x" * 60
    with pytest.raises(ValueError, match="^Najviše 60 znakova.$"):
        db.set_part_name(did, "trening_c", "y" * 61)
    for bad in ("kardio", "", "TRENING"):
        with pytest.raises(ValueError, match="^Odaberi dio treninga.$"):
            db.set_part_name(did, bad, "Snaga")
    assert parts_of(did) == {"trening": "Krug 2", "istezanje": "Opuštanje i disanje", "trening_c": "x" * 60}
    before = updated(pid)
    assert db.set_part_name(did, "trening", "  \n ") and "trening" not in parts_of(did) and updated(pid) > before
    assert db.get_day(did).part_label("trening") == "Glavni dio A"                  # emptied: the default back
    assert db.set_part_name(did, "trening_b", "") and "trening_b" not in parts_of(did)  # none to empty: nothing to do
    assert parts_of(other) == {} and [db.get_day(other).part_label(k) for k in SECTIONS] == list(SECTIONS.values())
    assert not db.set_part_name(987654, "trening", "Krug 1")
    db.delete_day(did)
    assert parts_of(did) == {}


def test_two_renames_at_once_leave_one_row():
    """Two "Preimenuj" saves of one part at once (two tabs): one row, its
    name one of the two (the day's locks, and the row written ON CONFLICT
    on the part's key)."""
    pid, did, *_ = gym_day()
    barrier, errors = threading.Barrier(2), []

    def rename(title: str) -> None:
        try:
            barrier.wait(timeout=5)
            db.set_part_name(did, "trening", title)
        except Exception as err:                                            # reported below
            errors.append(err)

    threads = [threading.Thread(target=rename, args=(t,)) for t in ("Krug 1", "Snaga")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert errors == []
    with db.engine.connect() as conn:
        rows = conn.execute(sa_text("SELECT title FROM program_day_parts WHERE day_id = :d"), {"d": did}).all()
    assert len(rows) == 1 and rows[0][0] in ("Krug 1", "Snaga")


def test_a_renamed_part_is_named_on_every_page_of_its_day():
    """The day editor's "Preimenuj": beside each part's "Kružno", in one
    row (.st-tools), a <details class="st-circ st-name"> whose one form
    posts "Naziv dijela" (maxlength 60, its placeholder the default, its
    value the name) to …/dio/<key>/naziv; back at the part with
    ?dio=<key>&naziv=1, "Spremljeno." printed there (none at the top). A
    renamed part's caption in the editor is its name and its default in
    brackets; the Dio options of that day's forms, the add card's line
    ("Dodano u Krug 1: Plank."), the day page's caption, the player's list
    and a circuit round's h1 and title say the name alone; another day of
    the programme keeps the defaults. A refusal ("Najviše 60 znakova.")
    comes back at the part, its "Preimenuj" open again and "Kružno" not (a
    "Kružno" refusal the other way round); a section that is none at the
    top; emptied, the default back. A client 403, a guest to log in,
    another programme's day 404."""
    ct, ivan, _ = trainer_with_clients()
    pid = db.create_program("Kružni — početna", None, "pocetna", "cijelo")    # ivan's (online): the player is his
    did = db.add_day(pid)
    goblet, plank = db.create_exercise("Goblet čučanj"), db.create_exercise("Plank")
    gi = db.add_day_item(did, goblet, "trening")
    db.update_day_item(gi, "trening", None, 10, None, None, None, "")
    db.set_circuit(did, "trening", 2, 60)
    base, edit = f"/treninzi/{pid}/dan/{did}", f"/treninzi/{pid}/dan/{did}/uredi"
    page = ct.get(edit).text
    for key, label in SECTIONS.items():
        part = circuit_section(page, key)
        assert re.search(r'<div class="st-tools">\s*<details class="st-circ[ "]', part), key
        assert ('<details class="st-circ st-name">\n    <summary>Preimenuj</summary>\n'
                f'    <form class="st-name-form" method="post" action="{base}/dio/{key}/naziv">') in part, key
        assert re.search(rf'<label for="naziv-{key}">Naziv dijela</label>\s*<input id="naziv-{key}" type="text" '
                         rf'name="title" maxlength="60" value="" placeholder="{label}">', part), key

    r = ct.post(f"{base}/dio/trening/naziv", data={"title": "  Krug   1 "}, follow_redirects=False)
    assert location(r) == f"{edit}?ok=Spremljeno.&dio=trening&naziv=1#dio-trening" and parts_of(did) == {"trening": "Krug 1"}
    page = ct.get(f"{edit}?ok=Spremljeno.&dio=trening&naziv=1").text
    assert page.count('<div class="alert ok') == 1                          # in the part, not at the top
    assert re.search(r'<h3 class="st-cap" id="dio-trening">Krug 1 <span class="st-cap-def">\(Glavni dio A\)</span></h3>\s*'
                     r'<div class="alert ok st-alert" role="status">Spremljeno.</div>', page)
    assert re.findall(r'<h3 class="st-cap" id="dio-(\w+)">([^<]*)</h3>', page) == [
        (k, label) for k, label in SECTIONS.items() if k != "trening"]      # the others: their defaults
    part = circuit_section(page, "trening")
    assert 'name="title" maxlength="60" value="Krug 1" placeholder="Glavni dio A">' in part and " open>" not in part
    named = [("zagrijavanje", "Zagrijavanje"), ("trening", "Krug 1"), ("trening_b", "Glavni dio B"),
             ("trening_c", "Glavni dio C"), ("istezanje", "Istezanje")]
    selects = re.findall(r'<select id="(?:st-\d+-dio|add-dio)" name="section">(.*?)</select>', page, re.S)
    assert len(selects) == 2 and all(re.findall(r'<option value="(\w+)"[^>]*>([^<]*)</option>', s) == named for s in selects)
    r = ct.post(f"{base}/stavke", data={"exercise_id": str(plank), "section": "trening"}, follow_redirects=False)
    assert location(r) == f"{edit}?dodaj=trening&ok=Dodano u Krug 1: Plank.#dodaj"

    ci = client_for("ivan@test.local")
    assert re.findall(r'<h2 class="dx-cap" id="dio-(\w+)">([^<]*)</h2>', ci.get(base).text) == [("trening", "Krug 1")]
    ci.post(f"{base}/kreni")
    step = ci.get(f"{base}/vjezba/1").text                                  # round 1 of the circuit
    assert '<h1 class="pl-name" id="pl-name">Krug 1</h1>' in step and "<title>Krug 1 — Trening 1 — QMT</title>" in step
    assert [read(h) for h in re.findall(r'<h3 class="dx-cap">(.*?)</h3>', step)] == ["Krug 1 · kružno · 2 kruga"]
    other = db.add_day(pid)
    db.add_day_item(other, plank, "trening")
    assert re.findall(r'<h2 class="dx-cap" id="dio-(\w+)">([^<]*)</h2>', ci.get(f"/treninzi/{pid}/dan/{other}").text) == [
        ("trening", "Glavni dio A")]                                        # another day: the default

    r = ct.post(f"{base}/dio/trening/naziv", data={"title": "x" * 61}, follow_redirects=False)
    assert location(r) == f"{edit}?error=Najviše 60 znakova.&dio=trening&naziv=1#dio-trening"
    assert parts_of(did) == {"trening": "Krug 1"}
    part = circuit_section(ct.get(f"{edit}?error=Najvi%C5%A1e+60+znakova.&dio=trening&naziv=1").text, "trening")
    assert '<div class="alert st-alert" role="alert"><span>Najviše 60 znakova.</span></div>' in part
    assert '<details class="st-circ st-name" open>' in part and '<details class="st-circ on">' in part
    part = circuit_section(ct.get(f"{edit}?error=Neispravan+broj.&dio=trening").text, "trening")    # Kružno's
    assert '<details class="st-circ on" open>' in part and '<details class="st-circ st-name">' in part
    r = ct.post(f"{base}/dio/kardio/naziv", data={"title": "Snaga"}, follow_redirects=False)
    assert location(r) == f"{edit}?error=Odaberi dio treninga."
    r = ct.post(f"{base}/dio/trening/naziv", data={"title": ""}, follow_redirects=False)
    assert location(r) == f"{edit}?ok=Spremljeno.&dio=trening&naziv=1#dio-trening" and parts_of(did) == {}
    assert '<h3 class="st-cap" id="dio-trening">Glavni dio A</h3>' in ct.get(edit).text
    elsewhere = db.create_program("B", None, "pocetna", "cijelo")
    assert ct.post(f"/treninzi/{elsewhere}/dan/{did}/dio/trening/naziv", data={"title": "X"}).status_code == 404
    assert ci.post(f"{base}/dio/trening/naziv", data={"title": "X"}).status_code == 403
    r = TestClient(app).post(f"{base}/dio/trening/naziv", data={"title": "X"}, follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/login") and parts_of(did) == {}


def test_a_slot_goes_only_into_a_dvoranski_day():
    """db.add_day_slot: a row with no exercise, last in its section, its
    hint cleaned to one line and cut to 80 ("" none), its numbers an item's
    (a refused one adds nothing, "Neispravan broj."); a section that is none
    None, a day gone None; an online programme's day refused ("Prazna mjesta
    idu samo u dvoranske programe."). Through the add card's "Dodaj prazno
    mjesto" (POST …/mjesto: the card's Dio and numbers and its Natuknica),
    there on a dvoranski day with an empty library too, back at the card as
    after an exercise, "Dodano u Krug 1: prazno mjesto."; an online day's
    editor offers no such way and the route refuses it. A client 403."""
    ct, *_ = trainer_with_clients()
    pid, did, base, edit = gym_day()
    before = updated(pid)
    first = db.add_day_slot(did, "trening")
    assert updated(pid) > before
    second = db.add_day_slot(did, "trening", "  čučanj \n  stražnji ", 3, 10, None, Decimal("20"))
    third = db.add_day_slot(did, "trening_c", "x" * 120, None, None, 40)
    rows = {it.id: it for it in db.get_day(did).items}
    assert [(rows[i].exercise_id, rows[i].exercise, rows[i].is_slot, rows[i].section, rows[i].position, rows[i].hint)
            for i in (first, second, third)] == [
        (None, None, True, "trening", 1, ""), (None, None, True, "trening", 2, "čučanj stražnji"),
        (None, None, True, "trening_c", 3, "x" * 80)]
    assert (rows[second].sets, rows[second].reps, rows[second].kg, rows[second].dose) == (3, 10, Decimal("20"), "3 × 10 · 20 kg")
    assert (rows[third].seconds, rows[third].dose) == (40, "40 s")
    for numbers in ({"sets": 0}, {"reps": 1000}, {"seconds": 3601}, {"kg": Decimal("0.25")}):
        with pytest.raises(ValueError, match="^Neispravan broj.$"):
            db.add_day_slot(did, "trening", "", **numbers)
    assert db.add_day_slot(did, "kardio") is None and db.add_day_slot(987654, "trening") is None
    assert len(db.get_day(did).items) == 3
    online = db.create_program("Online", None, "pocetna", "cijelo")
    od = db.add_day(online)
    with pytest.raises(ValueError, match="^Prazna mjesta idu samo u dvoranske programe.$"):
        db.add_day_slot(od, "trening", "čučanj")
    assert db.get_day(od).items == []

    db.set_part_name(did, "trening", "Krug 1")
    page = ct.get(edit).text                                                # the library is empty: the slot's way stays
    card = page.split('<form id="dodaj"')[1].split("</form>")[0]
    assert "Baza vježbi je prazna — prvo dodaj vježbu." in card and 'id="add-ex"' not in card
    assert '<option value="trening" selected>Krug 1</option>' in card and 'id="add-sets"' in card
    assert '<label for="add-hint">Natuknica (neobavezno)</label>' in card
    assert '<input id="add-hint" type="text" name="hint" maxlength="80" aria-describedby="add-hint-h">' in card
    assert "npr. čučanj, potisak — sužava popis vježbi kad se mjesto popunjava</p>" in card
    assert (f'<button type="submit" class="btn btn-sm" formaction="{base}/mjesto" formnovalidate>Dodaj prazno mjesto'
            '</button>') in card
    r = ct.post(f"{base}/mjesto", data={"section": "trening", "hint": "potisak", "reps": "8", "kg": "2,5", "exercise_id": ""},
                follow_redirects=False)
    assert location(r) == f"{edit}?dodaj=trening&ok=Dodano u Krug 1: prazno mjesto.#dodaj"
    made = db.get_day(did).items[-1]
    assert (made.is_slot, made.section, made.hint, made.reps, made.kg) == (True, "trening", "potisak", 8, Decimal("2.5"))
    r = ct.post(f"{base}/mjesto", data={"section": "istezanje"}, follow_redirects=False)
    assert location(r) == f"{edit}?dodaj=istezanje&ok=Dodano u Istezanje: prazno mjesto.#dodaj"
    r = ct.post(f"{base}/mjesto", data={"section": "trening_b", "sets": "0"}, follow_redirects=False)
    assert location(r) == f"{edit}?dodaj=trening_b&error=Neispravan broj.#dodaj"
    r = ct.post(f"{base}/mjesto", data={"section": "kardio"}, follow_redirects=False)
    assert location(r) == f"{edit}?error=Odaberi dio treninga."
    assert len(db.get_day(did).items) == 5
    page = ct.get(f"{edit}?dodaj=trening&ok=Dodano+u+Krug+1%3A+prazno+mjesto.").text
    assert page.count('<div class="alert') == 1
    assert '<div class="alert ok" role="status">Dodano u Krug 1: prazno mjesto.</div>' in page.split('<form id="dodaj"')[1]

    db.create_exercise("Plank")
    online_page = ct.get(f"/treninzi/{online}/dan/{od}/uredi").text         # an online day: no such way
    assert 'class="add-slot"' not in online_page and 'id="add-hint"' not in online_page and "formaction=" not in online_page
    assert "prazna mjesta" not in online_page.split("<main")[1].split("<script")[0]      # nor its lead's sentence
    r = ct.post(f"/treninzi/{online}/dan/{od}/mjesto", data={"section": "trening"}, follow_redirects=False)
    assert location(r) == (f"/treninzi/{online}/dan/{od}/uredi?dodaj=trening&error=Prazna mjesta idu samo u dvoranske "
                           "programe.#dodaj")
    assert db.get_day(od).items == []
    ci, anon = client_for("ivan@test.local"), TestClient(app)
    assert ci.post(f"{base}/mjesto", data={"section": "trening"}).status_code == 403
    r = anon.post(f"{base}/mjesto", data={"section": "trening"}, follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/login") and len(db.get_day(did).items) == 5


def test_a_programme_holding_a_slot_is_not_made_online():
    """db.update_program: a dvoranski programme a day of which holds a slot
    is not made online ("Program ima prazna mjesta — popuni ih ili obriši
    prije nego postane online.", nothing saved, its title neither: a client
    must never meet a slot). The programme's form asks no Vrsta since
    27.11.2026 (build 3 of the dvoranski treninzi): one that posts online
    saves the title and keeps the programme dvoranski, its slot as it was.
    Its other saves pass; once no slot is left it is made online."""
    ct, *_ = trainer_with_clients()
    pid, did, *_ = gym_day("Predložak")
    slot = db.add_day_slot(did, "trening", "čučanj")
    refused = "Program ima prazna mjesta — popuni ih ili obriši prije nego postane online."
    with pytest.raises(ValueError, match=f"^{refused}$"):
        db.update_program(pid, "Novi naziv", None, "pocetna", "cijelo", "online")
    assert (db.get_program(pid).title, db.get_program(pid).venue) == ("Predložak", "dvorana")
    r = ct.post(f"/treninzi/{pid}/edit", data={"title": "Novi", "level": "pocetna", "goal": "cijelo", "venue": "online"},
                follow_redirects=False)
    assert location(r) == f"/treninzi/{pid}/uredi?ok=Spremljeno."
    assert (db.get_program(pid).title, db.get_program(pid).venue) == ("Novi", "dvorana")
    assert [it.id for it in db.get_day(did).items if it.is_slot] == [slot]
    db.update_program(pid, "Predložak 2", None, "srednja", "core", None)    # kept dvoranski: saved
    db.update_program(pid, "Predložak 3", None, "srednja", "core", "dvorana")
    assert (db.get_program(pid).title, db.get_program(pid).level) == ("Predložak 3", "srednja")
    db.fill_slot(slot, db.create_exercise("Goblet čučanj"))
    db.update_program(pid, "Predložak 3", None, "srednja", "core", "online")
    assert db.get_program(pid).venue == "online"


def test_a_slots_row_in_the_editor():
    """A slot's row in the day editor: where an exercise's row has its
    name, "Prazno mjesto" and the hint muted after a middle dot
    (.it-slot-name: no link, no "video ✓"), ↑ / ↓ / ✕ as any row (named
    "Prazno mjesto · čučanj"; ✕ asks "Maknuti prazno mjesto?"), its form the
    row form plus "Natuknica" (maxlength 80), and under it "Popuni vježbom"
    (rendered hidden, the script's: data-hint the hint, a hidden exercise_id
    posting to …/stavke/<id>/vjezba, "Postavi"). Its hint and numbers are
    saved by its form (the hint cleaned and cut to 80), it moves within its
    section and is deleted as any row."""
    ct, *_ = trainer_with_clients()
    pid, did, base, edit = gym_day()
    goblet = db.create_exercise("Goblet čučanj", tags="noge")
    gi = db.add_day_item(did, goblet, "trening")
    a = db.add_day_slot(did, "trening", "čučanj", 3, 10)
    b = db.add_day_slot(did, "trening")
    page = ct.get(edit).text
    rows = page.split('<div class="card it-row" id="stavka-')[1:]
    assert [r.split('"')[0] for r in rows] == [str(gi), str(a), str(b)]
    assert '<span class="it-slot-name">Prazno mjesto <span class="it-note">· čučanj</span></span>' in rows[1]
    assert '<span class="it-slot-name">Prazno mjesto</span>' in rows[2]
    assert "it-video" not in rows[1] and 'class="it-name"' not in rows[1] and '<span class="it-video">bez videa</span>' in rows[0]
    assert re.search(rf'form="st-dolje-{a}" class="btn-ghost btn-sm"\s+aria-label="Pomakni dolje: Prazno mjesto · čučanj">',
                     rows[1])
    assert f'form="st-x-{b}" class="btn-ghost btn-sm" aria-label="Makni iz treninga: Prazno mjesto">✕</button>' in rows[2]
    form = rows[1].split('<form class="st-form"')[1].split("</form>")[0]
    assert re.findall(r'<label for="st-\d+-\w+">([^<]*)</label>', form) == [
        "Dio", "Serije", "Ponavljanja", "Sekunde", "Kilaža (kg)", "Odmor (s)", "Nakon vježbe (s)", "Natuknica", "Napomena"]
    assert f'<input id="st-{a}-hint" type="text" name="hint" maxlength="80" value="čučanj"' in form
    assert 'name="hint"' not in rows[0] and "st-fill" not in rows[0]
    fill = rows[1].split('<details class="st-circ st-fill"')[1].split("</details>")[0]
    assert fill.startswith(' data-hint="čučanj" hidden>\n        <summary>Popuni vježbom</summary>')
    assert f'<form class="st-fill-form" method="post" action="{base}/stavke/{a}/vjezba">' in fill
    assert f'<label for="st-{a}-fill">Vježba iz baze</label>' in fill
    assert f'<input type="hidden" id="st-{a}-fill" name="exercise_id" value="">' in fill
    assert '<button type="submit" class="btn btn-sm">Postavi</button>' in fill
    assert '<details class="st-circ st-fill" data-hint="" hidden>' in rows[2]
    after = page.split('<h2 style="font-size:1.05rem; margin:30px 0 12px;">Dodaj vježbu</h2>')[0].split("</section>")[-1]
    assert (f'<form id="st-x-{a}" method="post" action="{base}/stavke/{a}/obrisi"\n'
            '      data-confirm-title="Maknuti prazno mjesto?"\n'
            '      data-confirm="Prazno mjesto „čučanj” izlazi iz ovog treninga."\n'
            '      data-confirm-cta="Makni"></form>') in after
    assert 'data-confirm="Prazno mjesto izlazi iz ovog treninga."' in after

    r = ct.post(f"{base}/stavke/{a}", data={"section": "trening_b", "sets": "4", "reps": "12", "seconds": "", "rest": "60",
                                            "rest_after": "", "kg": "", "note": "s bučicom", "hint": "  čučanj \n  stražnji "},
                follow_redirects=False)
    assert location(r) == f"{edit}?ok=Spremljeno.&stavka={a}#stavka-{a}"
    it = db.get_day_item(a)
    assert (it.is_slot, it.section, it.sets, it.reps, it.rest_seconds, it.note, it.hint) == (
        True, "trening_b", 4, 12, 60, "s bučicom", "čučanj stražnji")
    ct.post(f"{base}/stavke/{a}", data={"section": "trening_b", "hint": "y" * 100})
    assert db.get_day_item(a).hint == "y" * 80
    ct.post(f"{base}/stavke/{b}/pomak", data={"smjer": "gore"})            # within its section: above the exercise
    assert [i.id for i in db.get_day(did).by_section["trening"]] == [b, gi]
    ct.post(f"{base}/stavke/{b}/obrisi")
    assert [i.id for i in db.get_day(did).items] == [gi, a] and db.get_day_item(b) is None


def test_a_slot_is_filled_from_the_library():
    """db.fill_slot ("Popuni vježbom" → "Postavi"): the exercise goes into
    the slot, an ordinary row from then on, its place, numbers, note and
    hint kept (the hint unshown, kept by its form, which posts none); an
    exercise not in the library "Nepoznata vježba.", a row that is no slot
    "Mjesto je već popunjeno.", nothing changed; a row gone False. Through
    its route (…/stavke/<id>/vjezba) back at the row, "Spremljeno." in it;
    none chosen "Odaberi vježbu s popisa."; a refusal with ?popuni=1 opens
    its "Popuni vježbom" again (the row form's own refusal does not). A
    client 403, a guest to log in, another programme's day 404."""
    ct, *_ = trainer_with_clients()
    pid, did, base, edit = gym_day()
    goblet, plank = db.create_exercise("Goblet čučanj", tags="noge"), db.create_exercise("Plank")
    a = db.add_day_slot(did, "trening", "čučanj")
    db.update_day_item(a, "trening", 3, 10, None, 60, 90, "pete na podu", kg=Decimal("16"))
    b = db.add_day_slot(did, "trening_b", "core")
    before = updated(pid)
    assert db.fill_slot(a, goblet) and updated(pid) > before
    it = db.get_day_item(a)
    assert (it.is_slot, it.exercise_id, it.exercise.name, it.section, it.position, it.sets, it.reps, it.rest_seconds,
            it.rest_after_seconds, it.note, it.kg, it.hint) == (False, goblet, "Goblet čučanj", "trening", 1, 3, 10, 60, 90,
                                                                  "pete na podu", Decimal("16"), "čučanj")
    with pytest.raises(ValueError, match="^Mjesto je već popunjeno.$"):
        db.fill_slot(a, plank)
    with pytest.raises(ValueError, match="^Nepoznata vježba.$"):
        db.fill_slot(b, 987654)
    assert db.get_day_item(a).exercise_id == goblet and db.get_day_item(b).is_slot
    assert not db.fill_slot(987654, plank)
    row = ct.get(edit).text.split(f'id="stavka-{a}"')[1].split('<div class="card it-row"')[0]
    assert f'<a class="it-name" href="/treninzi/vjezbe/{goblet}">Goblet čučanj</a>' in row
    assert "Prazno mjesto" not in row and "· čučanj" not in row and 'name="hint"' not in row and "st-fill" not in row
    ct.post(f"{base}/stavke/{a}", data={"section": "trening", "sets": "4", "reps": "10"})   # its form posts no hint: kept
    assert (db.get_day_item(a).sets, db.get_day_item(a).hint) == (4, "čučanj")

    r = ct.post(f"{base}/stavke/{b}/vjezba", data={"exercise_id": str(plank)}, follow_redirects=False)
    assert location(r) == f"{edit}?ok=Spremljeno.&stavka={b}#stavka-{b}" and db.get_day_item(b).exercise_id == plank
    page = ct.get(f"{edit}?ok=Spremljeno.&stavka={b}").text
    assert page.count('<div class="alert') == 1
    assert '<div class="alert ok st-alert" role="status">Spremljeno.</div>' in page.split(f'id="stavka-{b}"')[1].split("</form>")[0]
    c = db.add_day_slot(did, "trening", "povlačenje")
    for data, said in (({"exercise_id": ""}, "Odaberi vježbu s popisa."), ({"exercise_id": "abc"}, "Odaberi vježbu s popisa."),
                       ({"exercise_id": "987654"}, "Nepoznata vježba.")):
        r = ct.post(f"{base}/stavke/{c}/vjezba", data=data, follow_redirects=False)
        assert location(r) == f"{edit}?error={said}&popuni=1&stavka={c}#stavka-{c}", data
    r = ct.post(f"{base}/stavke/{a}/vjezba", data={"exercise_id": str(plank)}, follow_redirects=False)
    assert location(r) == f"{edit}?error=Mjesto je već popunjeno.&popuni=1&stavka={a}#stavka-{a}"
    assert db.get_day_item(c).is_slot and db.get_day_item(a).exercise_id == goblet
    row = ct.get(f"{edit}?error=Nepoznata+vje%C5%BEba.&popuni=1&stavka={c}").text.split(f'id="stavka-{c}"')[1]
    assert '<div class="alert st-alert" role="alert"><span>Nepoznata vježba.</span></div>' in row.split("</form>")[0]
    assert '<details class="st-circ st-fill" data-hint="povlačenje" hidden open>' in row
    page = ct.get(f"{edit}?error=Neispravan+broj.&stavka={c}").text         # the row form's refusal: Popuni stays shut
    assert '<details class="st-circ st-fill" data-hint="povlačenje" hidden>' in page
    ci, anon = client_for("ivan@test.local"), TestClient(app)
    assert ci.post(f"{base}/stavke/{c}/vjezba", data={"exercise_id": str(plank)}).status_code == 403
    r = anon.post(f"{base}/stavke/{c}/vjezba", data={"exercise_id": str(plank)}, follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/login")
    elsewhere = db.create_program("B", None, "pocetna", "cijelo", "dvorana")
    assert ct.post(f"/treninzi/{elsewhere}/dan/{did}/stavke/{c}/vjezba", data={"exercise_id": str(plank)}).status_code == 404
    assert db.get_day_item(c).is_slot


def test_a_slot_is_no_exercise_anywhere_else():
    """A slot is not an exercise outside its editor: "7 vježbi" counts
    exercises, the slots said after the count when there are any
    (ProgramDay.slots_text, models.plural's forms: "1 prazno mjesto", "3
    prazna mjesta", "5 praznih mjesta") on the day page's lead, its card on
    the programme's page and its row in the programme's editor; the day
    page lists a slot as a muted row ("Prazno mjesto · čučanj", its dose
    and its rests, no <details>, no "Vježba n"; its words the copy slot
    dan.slot); a day of slots alone offers no Kreni and Kreni starts
    nothing there; a circuit on a part of slots alone is no "kružni
    trening"; db.day_item_ids and the staff's table count exercises; the
    library's counts, an exercise's programmes, /media's and
    delete_exercise do not trip on a NULL."""
    def text(n: int) -> str:
        day = ProgramDay(position=1, title="")
        day.items = [ProgramDayItem(position=i, section="trening") for i in range(1, n + 1)]
        return day.slots_text

    assert [text(n) for n in (0, 1, 2, 4, 5, 11, 12, 14, 21, 22, 25)] == [
        "", "1 prazno mjesto", "2 prazna mjesta", "4 prazna mjesta", "5 praznih mjesta", "11 praznih mjesta",
        "12 praznih mjesta", "14 praznih mjesta", "21 prazno mjesto", "22 prazna mjesta", "25 praznih mjesta"]
    ct, *_ = trainer_with_clients()
    trainer = db.get_user_by_email("trener@test.local").id
    pid, did, base, edit = gym_day()
    goblet, plank = db.create_exercise("Goblet čučanj"), db.create_exercise("Plank")
    db.set_exercise_video(goblet, "vjezba-1-0123456789abcdef.mp4")
    warm = db.add_day_slot(did, "zagrijavanje", "mobilnost")
    gi = db.add_day_item(did, goblet, "trening", 3, 10)
    squat = db.add_day_slot(did, "trening", "čučanj", 3, 10)
    db.update_day_item(squat, "trening", 3, 10, None, 60, None, "")
    pi = db.add_day_item(did, plank, "trening_b", None, None, 40)
    db.set_circuit(did, "zagrijavanje", 2, None)                            # a circuit on slots alone
    day = db.get_day(did)
    assert [it.id for it in day.exercise_items] == [gi, pi] and day.slot_count == 2 and not day.has_circuit
    assert {k: [it.id for it in v] for k, v in day.exercises_by_section.items()} == {
        "zagrijavanje": [], "trening": [gi], "trening_b": [pi], "trening_c": [], "istezanje": []}
    page = ct.get(base).text
    assert '<p class="hint">2 vježbe · 2 prazna mjesta</p>' in page and "kružn" not in page.split("<main")[1]
    assert re.findall(r'<span class="dx-n">([^<]*)</span>', page) == ["Vježba 1", "Vježba 2"]
    assert page.count('<details class="card ex">') == 2
    slots = re.findall(r'<div class="card dx-slot">(.*?)\n      </div>', page, re.S)
    words = [" ".join(unescape(re.sub(r"<[^>]+>", " ", x)).split()) for x in slots]          # each tag a space
    assert words == ["Prazno mjesto · mobilnost", "Prazno mjesto · čučanj 3 × 10 Odmor između serija: 60 s"]
    assert all('data-copy="dan.slot"' in x and "<details" not in x for x in slots)
    card = re.search(r'<span class="hint">(.*?)</span>\s*</span>\s*<span class="dc-go"', ct.get(f"/treninzi/{pid}").text, re.S)
    assert read(card.group(1)) == "2 vježbe · 2 prazna mjesta"
    assert '<span class="it-note">2 vježbe · 2 prazna mjesta</span>' in ct.get(f"/treninzi/{pid}/uredi").text
    db.set_circuit(did, "trening", 2, 30)
    assert db.get_day(did).has_circuit                                     # one holding an exercise: kružni trening

    alone = db.add_day(pid)
    db.add_day_slot(alone, "trening", "čučanj")
    page = ct.get(f"/treninzi/{pid}/dan/{alone}").text
    assert '<p class="hint">0 vježbi · 1 prazno mjesto</p>' in page
    assert 'class="go"' not in page and "/kreni" not in page                # no Kreni on slots alone
    r = ct.post(f"/treninzi/{pid}/dan/{alone}/kreni", follow_redirects=False)
    assert r.headers["location"] == f"/treninzi/{pid}/dan/{alone}" and db.open_pass(trainer, alone) is None

    assert db.day_item_ids([did, alone]) == {did: {gi, pi}}
    assert [(p.id, nd, ni) for p, nd, ni in db.all_programs()] == [(pid, 2, 2)]
    # staff's table says the slots beside the exercises, and a programme of
    # slots alone is not flagged "prazno!" (Fable's review, 26.11.2026)
    assert db.program_slot_counts() == {pid: 3}
    table = ct.get("/treninzi").text
    assert re.search(r'<td>2 <span class="hint slots-n"[^>]*>· 3 prazna mjesta</span></td>', table) and "prazno!" not in table
    only = db.create_program("Predložak", None, "srednja", "cijelo", venue="dvorana")
    db.add_day_slot(db.add_day(only), "trening", "")
    bare = db.create_program("Prazan", None, "srednja", "cijelo")
    table = ct.get("/treninzi").text
    assert re.search(r'<td>0 <span class="hint slots-n"[^>]*>· 1 prazno mjesto</span></td>', table)
    assert admin_row(table, "Prazan") == ("0", "0", True) and table.count("prazno!") == 1
    for extra in (only, bare):
        db.delete_program(extra)
    assert [(e.name, n) for e, n in db.exercises()] == [("Goblet čučanj", 1), ("Plank", 1)]
    assert [p.id for p in db.exercise_programs(goblet)] == [pid]
    assert [p.id for p in db.video_programs("vjezba-1-0123456789abcdef.mp4")] == [pid]
    assert db.delete_exercise(plank) == (None, 1)
    assert [(it.id, it.is_slot) for it in db.get_day(did).items] == [(warm, True), (gi, False), (squat, True)]


def test_the_player_leaves_the_slots_out():
    """The player on a dvoranski day (staff's, 26.11.2026): a slot is no
    step (a circuit part's round holds its exercises alone, a part of slots
    alone is none), has no row in the list, no caption of its own, no mark
    (the day page's slot rows neither, a saved round's exercise its "1/2"),
    and the dock counts the exercises."""
    ct, *_ = trainer_with_clients()
    pid, did, base, _ = gym_day()
    goblet, plank = db.create_exercise("Goblet čučanj"), db.create_exercise("Plank")
    db.add_day_slot(did, "zagrijavanje", "mobilnost")
    gi = db.add_day_item(did, goblet, "trening", None, 10)
    db.add_day_slot(did, "trening", "potisak", None, 10)
    pi = db.add_day_item(did, plank, "trening_b", 3, None, 40)
    db.add_day_slot(did, "trening_b", "core")
    db.set_circuit(did, "trening", 2, 60)
    assert [(s.item.id if s.item else None, s.round, [it.id for it in s.items]) for s in web_steps(db.get_day(did))] == [
        (None, 1, [gi]), (None, 2, [gi]), (pi, None, [])]
    r = ct.post(f"{base}/kreni", follow_redirects=False)
    assert r.headers["location"] == f"{base}/vjezba/1"
    page = ct.get(f"{base}/vjezba/1").text
    assert re.findall(r'<div class="cr-row" id="cr-(\d+)">', page) == [str(gi)]
    assert page.split('<div class="pl-segs" aria-hidden="true">')[1].split("</div>")[0].count("<span") == 3
    side = page.split('id="popis"')[1].split("</aside>")[0]
    assert [read(h) for h in re.findall(r'<h3 class="dx-cap">(.*?)</h3>', side)] == [
        "Glavni dio A · kružno · 2 kruga", "Glavni dio B"]
    assert re.findall(r'<span class="dx-name">([^<]*?)(?: <span|</span>)', side) == ["Goblet čučanj", "Plank"]
    assert read(re.search(r'<a class="pl-dock" href="#popis">(.*?)</a>', page, re.S).group(1)) == "Vježbe · 0/2 ✓"
    r = ct.post(f"{base}/vjezba/1", data={"part": "trening", "round": "1", f"reps_{gi}": "10", f"kg_{gi}": ""},
                follow_redirects=False)
    assert r.headers["location"] == f"{base}/vjezba/2?odmor=60"
    from qmt.web import app as web
    day, log = db.get_day(did), db.open_pass(db.get_user_by_email("trener@test.local").id, did)
    assert {k: m.text for k, m in web._marks(day, web._day_items(day), log.done_items).items()} == {gi: "1/2"}
    page = ct.get(f"{base}/vjezba/2").text
    assert read(re.search(r'<a class="pl-dock" href="#popis">(.*?)</a>', page, re.S).group(1)) == "Vježbe · 1/2 ✓"
    day_page = ct.get(base).text
    slot_rows = re.findall(r'<div class="card dx-slot">(.*?)\n      </div>', day_page, re.S)
    assert len(slot_rows) == 3 and not any("dx-rounds" in x or "dx-ok" in x for x in slot_rows)
    assert day_page.count('class="dx-rounds"') == 1                        # the round's exercise alone


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
# 4f9d6f7103ad, the rest after an exercise, 45c543c860f3, the items' key to
# their exercise CASCADE (4.11.2026), and 30815c99e7d2, reps and seconds
# together (24.11.2026: the CHECK 7c3bf996c983 made goes, and Alembic's
# compare sees a CHECK by its name): a test that builds program_day_items with
# 7c3bf996c983 runs them on top, so the table is the model's again
REST_AFTER = "4f9d6f7103ad_program_day_items_rest_after.py"
CASCADE = "45c543c860f3_program_day_items_exercise_cascade.py"
REPS_AND_SECONDS = "30815c99e7d2_program_day_items_reps_and_seconds.py"
# fc1840b0a981 (24.11.2026, kružni trening): program_day_circuits, whose key
# points at program_days, so a test that drops the days drops it first and
# makes it again on top
CIRCUITS = "fc1840b0a981_program_day_circuits.py"
# d0ed87d5c98f (25.11.2026): program_day_items.kg, the planned weight, a
# column the models have: a test that builds the items' table again runs it
# on top too
KG = "d0ed87d5c98f_program_day_items_kg.py"
# a7d3c5e9f214 (26.11.2026, build 2): Glavni dio C (the CHECK), the parts'
# own names (program_day_parts, whose key points at program_days: a test
# that drops the days drops it first and makes it again on top) and the
# slots (program_day_items.exercise_id NULLable, its hint)
PARTS = "a7d3c5e9f214_day_parts_and_slots.py"
# c4e1b7f9a2d6 (26.11.2026, build 3): the gym trainings, whose items' key
# points at exercises: a test that drops the library drops them first and
# makes them again on top; and 36d6e2c97de7 (build 3, part B) their parts,
# whose key points at the trainings: dropped before them, made after them;
# and 9b4e2d7f1c58 (27.11.2026, the dvoranski treninzi's build 1) their
# blocks and the templates: the models' gym tables since, dropped before
# the trainings, made on top of the parts (which it drops)
GYM = "c4e1b7f9a2d6_gym_trainings.py"
GYM_PARTS = "36d6e2c97de7_gym_training_parts.py"
GYM_BLOCKS = "9b4e2d7f1c58_gym_training_blocks.py"


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
    exercise; fc1840b0a981 the days' circuits; d0ed87d5c98f the items'
    planned weight; a7d3c5e9f214 Glavni dio C, the parts' names and the
    slots; c4e1b7f9a2d6 the gym trainings, whose items point at the
    library; 36d6e2c97de7 their parts; 9b4e2d7f1c58 their blocks and the
    templates), and every table is the models'."""
    mig = _migration("4c2e8a6f1d39_exercise_library.py")
    assert (mig.revision, mig.down_revision) == ("4c2e8a6f1d39", "b18ebed39701")
    with db.engine.begin() as conn:                                         # the tables as before the revision
        # (workout_logs, 3890252ee50f's, program_day_circuits, fc1840b0a981's, and
        # program_day_parts, a7d3c5e9f214's, point at program_days, and
        # gym_training_items, c4e1b7f9a2d6's, at exercises: they go first, and
        # with them the gym's other tables, 9b4e2d7f1c58's blocks and templates)
        conn.execute(sa_text("DROP TABLE gym_template_blocks, gym_templates, gym_training_items, gym_training_blocks, "
                             "gym_trainings, workout_logs, program_day_circuits, program_day_parts, program_day_items, "
                             "program_days, exercise_alternatives, exercises"))
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
    _run(_migration(REPS_AND_SECONDS).upgrade)                               # and reps with seconds, no CHECK
    _run(_migration(CIRCUITS).upgrade)                                       # and the days' circuits
    _run(_migration(KG).upgrade)                                             # and the items' planned weight
    _run(_migration(PARTS).upgrade)                                          # and C, the parts' names, the slots
    _run(_migration(GYM).upgrade)                                            # and the gym trainings
    _run(_migration(GYM_PARTS).upgrade)                                      # and their parts (part B)
    _run(_migration(GYM_BLOCKS).upgrade)                                     # and their blocks, the templates
    assert "program_items" not in _tables() and "gym_training_parts" not in _tables() and _schema_diffs(
        TRENINZI | {"program_day_circuits", "program_day_parts", "gym_trainings", "gym_training_items",
                    "gym_training_blocks", "gym_templates", "gym_template_blocks"}) == []
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
    after an exercise, a later column the models have; 45c543c860f3, their
    key to the exercise CASCADE, as the models have it; and 30815c99e7d2,
    which drops the reps-or-seconds CHECK the models no longer have; and
    fc1840b0a981, the days' circuits, a later table every day is loaded
    with, whose key points at the days: it goes before the downgrade; and
    d0ed87d5c98f, the items' planned weight, a later column the models
    have; and a7d3c5e9f214, Glavni dio C, the parts' names, a later table
    whose key points at the days (it goes first too), and the slots.)"""
    mig = _migration("7c3bf996c983_program_days.py")
    rest_after, cascade, both = _migration(REST_AFTER), _migration(CASCADE), _migration(REPS_AND_SECONDS)
    circuits, kg, parts = _migration(CIRCUITS), _migration(KG), _migration(PARTS)
    assert (mig.revision, mig.down_revision) == ("7c3bf996c983", "4c2e8a6f1d39")
    with db.engine.begin() as conn:                                         # the tables as before the revision
        # (workout_logs, 3890252ee50f's, program_day_circuits, fc1840b0a981's, and
        # program_day_parts, a7d3c5e9f214's, point at program_days: they go first)
        conn.execute(sa_text("DROP TABLE workout_logs, program_day_circuits, program_day_parts, program_day_items, "
                             "program_days"))
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
    _run(both.upgrade)
    _run(circuits.upgrade)
    _run(kg.upgrade)
    _run(parts.upgrade)
    assert capsys.readouterr().out == f"[7c3bf996c983] programs {p1} ('Cijelo tijelo — srednja'): Dan 1 with 7 exercises\n"
    assert "program_items" not in _tables() and _schema_diffs(TRENINZI | {"program_day_circuits", "program_day_parts"}) == []
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
    _run(parts.downgrade)                                                    # they point at the days: they go first
    _run(circuits.downgrade)
    _run(mig.downgrade)
    assert not {"program_days", "program_day_items"} & _tables()
    back = ["2 serije", "3 × 8 · 8 kg", "3 × 20 s", "3 × 5 · s koljena", "3 × 6 · po nozi", "3 × 10 · 2 × 6 kg", "",
            "Tempo 3-1-1", "10 ponavljanja", "2 × 30 s · po nozi"]
    exercises = [ids[0], *ids, ids[2], ids[1]]
    assert _flat_items() == [(p1, n, eid, note) for n, (eid, note) in enumerate(zip(exercises, back), start=1)]
    _run(mig.upgrade)
    _run(rest_after.upgrade)
    _run(cascade.upgrade)
    _run(both.upgrade)
    _run(circuits.upgrade)
    _run(kg.upgrade)
    _run(parts.upgrade)
    assert capsys.readouterr().out.endswith("Dan 1 with 10 exercises\n")
    assert "program_items" not in _tables() and _schema_diffs(TRENINZI | {"program_day_circuits", "program_day_parts"}) == []
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


def test_the_two_main_parts_migration_lets_an_item_into_b_and_back():
    """dc22ce1ed7e6, run on qmt_test as before it (the section's CHECK
    naming three: an item put into trening_b is refused): the CHECK names
    four, its name kept, and an item goes into trening_b; downgrade folds
    every item of trening_b into trening, its place kept, and the CHECK
    refuses trening_b again; a second upgrade lets it in once more."""
    mig = _migration("dc22ce1ed7e6_two_main_parts.py")
    assert (mig.revision, mig.down_revision) == ("dc22ce1ed7e6", "8a67c43d0bb4")
    assert mig.SECTIONS == ("zagrijavanje", "trening", "trening_b", "istezanje")   # its revision's four (C: a7d3c5e9f214)
    pid = db.create_program("T", None, "pocetna", "cijelo")
    a, b = hold(pid, db.create_exercise("Goblet čučanj")), hold(pid, db.create_exercise("Plank"))

    def into_b(item: int) -> bool:
        """Whether the database takes trening_b for an item."""
        try:
            with db.engine.begin() as conn:
                conn.execute(sa_text("UPDATE program_day_items SET section = 'trening_b' WHERE id = :i"), {"i": item})
            return True
        except IntegrityError:
            return False

    def sections() -> list[tuple[int, str, int]]:
        with db.engine.connect() as conn:
            return [tuple(r) for r in conn.execute(sa_text("SELECT id, section, position FROM program_day_items ORDER BY id"))]

    with db.engine.begin() as conn:                                         # the CHECK as before the revision
        conn.execute(sa_text("ALTER TABLE program_day_items DROP CONSTRAINT ck_program_day_items_section, "
                             "ADD CONSTRAINT ck_program_day_items_section "
                             "CHECK (section IN ('zagrijavanje', 'trening', 'istezanje'))"))
    assert not into_b(b)
    _run(mig.upgrade)
    assert into_b(b) and sections() == [(a, "trening", 1), (b, "trening_b", 2)]
    _run(mig.downgrade)
    assert sections() == [(a, "trening", 1), (b, "trening", 2)] and not into_b(a)
    _run(mig.upgrade)
    assert into_b(a) and sections() == [(a, "trening_b", 1), (b, "trening", 2)]


def _takes(sql: str, **params) -> bool:
    """Whether the database takes this write (no CHECK refuses it)."""
    try:
        with db.engine.begin() as conn:
            conn.execute(sa_text(sql), params)
        return True
    except IntegrityError:
        return False


def test_the_reps_and_seconds_migration_lets_an_item_ask_both_and_back():
    """30815c99e7d2, run on qmt_test as before it (the CHECK
    ck_program_day_items_reps_or_seconds: an item with reps and seconds is
    refused): the CHECK goes, the tables the models', and an item holds
    both; downgrade keeps such an item's reps and drops its seconds (one
    with seconds alone keeps them), and the CHECK refuses both again; a
    second upgrade lets them in once more."""
    mig = _migration("30815c99e7d2_program_day_items_reps_and_seconds.py")
    assert (mig.revision, mig.down_revision) == ("30815c99e7d2", "0401f7fb9861")
    pid = db.create_program("T", None, "pocetna", "cijelo")
    both, timed = hold(pid, db.create_exercise("Bočni plank")), hold(pid, db.create_exercise("Plank"))
    db.update_day_item(timed, "trening", 3, None, 40, None, None, "")
    both_sql = "UPDATE program_day_items SET sets = 3, reps = 5, seconds = 30 WHERE id = :i"

    def numbers() -> list[tuple]:
        with db.engine.connect() as conn:
            return [tuple(r) for r in conn.execute(sa_text("SELECT id, sets, reps, seconds FROM program_day_items ORDER BY id"))]

    with db.engine.begin() as conn:                                         # the CHECK as before the revision
        conn.execute(sa_text("ALTER TABLE program_day_items ADD CONSTRAINT ck_program_day_items_reps_or_seconds "
                             "CHECK (reps IS NULL OR seconds IS NULL)"))
    assert not _takes(both_sql, i=both) and _schema_diffs(TRENINZI) != []   # the models have it no more
    _run(mig.upgrade)
    assert _schema_diffs(TRENINZI) == [] and _takes(both_sql, i=both)
    assert numbers() == [(both, 3, 5, 30), (timed, 3, None, 40)] and db.get_day_item(both).dose == "3 × 5 × 30 s"
    _run(mig.downgrade)
    assert numbers() == [(both, 3, 5, None), (timed, 3, None, 40)] and not _takes(both_sql, i=both)
    assert _schema_diffs(TRENINZI) != []
    _run(mig.upgrade)
    assert _schema_diffs(TRENINZI) == [] and _takes(both_sql, i=both) and numbers()[0] == (both, 3, 5, 30)


def test_the_venue_migration_makes_every_programme_online_and_back():
    """49a70497e58a, run on qmt_test as before it (programs without venue,
    two programmes in it): the column as the model has it (String(8), NOT
    NULL, 'online' by default), every programme there online, a row
    inserted without one online, its CHECK refusing a venue that is none of
    online and dvorana; downgrade drops the column, the programmes staying;
    a second upgrade makes them online again."""
    mig = _migration("49a70497e58a_programs_venue.py")
    assert (mig.revision, mig.down_revision) == ("49a70497e58a", "30815c99e7d2")
    assert mig.VENUES == tuple(VENUES)                                      # its own copy agrees with the model's
    a = db.create_program("A", None, "pocetna", "cijelo")
    b = db.create_program("B", None, "srednja", "core", "dvorana")
    with db.engine.begin() as conn:                                         # the table as before the revision
        conn.execute(sa_text("ALTER TABLE programs DROP COLUMN venue"))
    assert "venue" not in {c["name"] for c in sa_inspect(db.engine).get_columns("programs")}
    _run(mig.upgrade)
    assert _schema_diffs({"programs"}) == []
    col = {c["name"]: c for c in sa_inspect(db.engine).get_columns("programs")}["venue"]
    assert not col["nullable"] and str(col["type"]) == "VARCHAR(8)" and col["default"] == "'online'::character varying"
    assert [(db.get_program(p).title, db.get_program(p).venue) for p in (a, b)] == [("A", "online"), ("B", "online")]
    with db.engine.begin() as conn:
        assert conn.execute(sa_text("INSERT INTO programs (title) VALUES ('C') RETURNING venue")).scalar_one() == "online"
    assert _takes("UPDATE programs SET venue = 'dvorana' WHERE id = :i", i=b)
    assert not _takes("UPDATE programs SET venue = 'teretana' WHERE id = :i", i=a)
    assert [p.title for p in db.programs_for_level("srednja")] == []         # b is dvoranski now
    _run(mig.downgrade)
    assert "venue" not in {c["name"] for c in sa_inspect(db.engine).get_columns("programs")}
    with db.engine.connect() as conn:
        assert [r[0] for r in conn.execute(sa_text("SELECT title FROM programs ORDER BY id"))] == ["A", "B", "C"]
    _run(mig.upgrade)
    assert _schema_diffs({"programs"}) == [] and {db.get_program(p).venue for p in (a, b)} == {"online"}


def test_the_circuit_migration_makes_the_table_and_takes_it_away():
    """fc1840b0a981 (24.11.2026, kružni trening), run on qmt_test as before
    it (no program_day_circuits, a day with an item in it): the table as the
    model has it, no part a circuit (every one stays normal); one row per
    part (the primary key, day and section); its CHECKs refuse 1 or 21
    rounds and a rest of -1 or 3601, taking 2, 20, 0, 3600 and none; a day
    deleted takes its rows (CASCADE). Downgrade drops the table, the days and
    their items staying; a second upgrade makes it again, empty."""
    mig = _migration(CIRCUITS)
    assert (mig.revision, mig.down_revision) == ("fc1840b0a981", "49a70497e58a")
    pid = db.create_program("T", None, "pocetna", "cijelo")
    iid = hold(pid, db.create_exercise("Plank"))
    did, gone = db.get_program(pid).days[0].id, db.add_day(pid)
    with db.engine.begin() as conn:                                         # the database as before the revision
        conn.execute(sa_text("DROP TABLE program_day_circuits"))
    assert "program_day_circuits" not in _tables()
    _run(mig.upgrade)
    assert _schema_diffs({"program_day_circuits"}) == [] and circuits_of(did) == {}
    assert [c["name"] for c in sa_inspect(db.engine).get_columns("program_day_circuits")] == [
        "day_id", "section", "rounds", "rest_seconds"]
    assert sa_inspect(db.engine).get_pk_constraint("program_day_circuits")["constrained_columns"] == ["day_id", "section"]
    insert = "INSERT INTO program_day_circuits (day_id, section, rounds, rest_seconds) VALUES (:d, :s, :r, :t)"
    for section, rounds, rest in (("zagrijavanje", 1, 60), ("zagrijavanje", 21, 60), ("zagrijavanje", 3, -1),
                                  ("zagrijavanje", 3, 3601), ("zagrijavanje", None, 60)):
        assert not _takes(insert, d=did, s=section, r=rounds, t=rest), (rounds, rest)
    for section, rounds, rest in (("zagrijavanje", 2, 0), ("trening", 20, 3600), ("trening_b", 3, None)):
        assert _takes(insert, d=did, s=section, r=rounds, t=rest), (section, rounds, rest)
    assert not _takes(insert, d=did, s="trening", r=3, t=60)                # one row per part
    assert _takes(insert, d=gone, s="trening", r=3, t=60)
    day = db.get_day(did)                                                    # the model reads the rows
    assert (day.circuit("trening").rounds, day.circuit("trening_b").rest_seconds, day.has_circuit) == (20, None, True)
    db.delete_day(gone)
    assert circuits_of(gone) == {} and len(circuits_of(did)) == 3
    _run(mig.downgrade)
    assert "program_day_circuits" not in _tables()
    with db.engine.connect() as conn:                                       # (the models read the table with every day)
        assert conn.execute(sa_text("SELECT d.id, i.id FROM program_days d JOIN program_day_items i ON i.day_id = d.id "
                                    "WHERE d.program_id = :p"), {"p": pid}).all() == [(did, iid)]
    _run(mig.upgrade)
    assert _schema_diffs({"program_day_circuits"}) == [] and circuits_of(did) == {} and db.get_day(did).circuits == []


def test_the_kg_migration_adds_the_column_and_takes_it_away():
    """d0ed87d5c98f (25.11.2026), run on qmt_test as before it
    (program_day_items without kg, an item in it): the column as the model
    has it (Numeric(5, 1), NULL), the item already there with none (nothing
    planned until Amir types one), the rest of its row as it was; a weight
    saved then; downgrade drops the column, the item staying, and a second
    upgrade adds it again, empty."""
    mig = _migration(KG)
    assert (mig.revision, mig.down_revision) == ("d0ed87d5c98f", "2b7e4c9a61d3")
    pid = db.create_program("T", None, "pocetna", "cijelo")
    iid = hold(pid, db.create_exercise("Goblet čučanj"))
    db.update_day_item(iid, "trening", 3, 10, None, 60, 90, "pete na podu")
    with db.engine.begin() as conn:                                         # the table as before the revision
        conn.execute(sa_text("ALTER TABLE program_day_items DROP COLUMN kg"))
    assert _schema_diffs(TRENINZI) != []
    _run(mig.upgrade)
    assert _schema_diffs(TRENINZI) == []
    col = {c["name"]: c for c in sa_inspect(db.engine).get_columns("program_day_items")}["kg"]
    assert col["nullable"] and str(col["type"]) == "NUMERIC(5, 1)"
    it = db.get_day_item(iid)
    assert (it.sets, it.reps, it.rest_seconds, it.rest_after_seconds, it.note, it.kg) == (3, 10, 60, 90, "pete na podu", None)
    db.update_day_item(iid, "trening", 3, 10, None, 60, 90, "pete na podu", kg=Decimal("22.5"))
    assert (db.get_day_item(iid).kg, db.get_day_item(iid).dose) == (Decimal("22.5"), "3 × 10 · 22,5 kg")
    _run(mig.downgrade)
    assert "kg" not in {c["name"] for c in sa_inspect(db.engine).get_columns("program_day_items")}
    with db.engine.connect() as conn:
        assert conn.execute(sa_text("SELECT sets, reps, note FROM program_day_items WHERE id = :i"),
                            {"i": iid}).one() == (3, 10, "pete na podu")
    _run(mig.upgrade)
    assert _schema_diffs(TRENINZI) == [] and db.get_day_item(iid).kg is None


def _items(did: int) -> list[tuple]:
    """A day's items as stored, in position order: (id, section, position, exercise)."""
    with db.engine.connect() as conn:
        return [tuple(r) for r in conn.execute(sa_text(
            "SELECT id, section, position, exercise_id FROM program_day_items WHERE day_id = :d ORDER BY position"),
            {"d": did})]


def test_the_parts_migration_adds_c_the_names_and_the_slots_and_back():
    """a7d3c5e9f214 (26.11.2026, build 2), run on qmt_test as before it
    (its own downgrade from the models' tables: the CHECK naming four
    sections, no program_day_parts, exercise_id NOT NULL, no hint): the
    CHECK names five, program_day_parts as the model has it, exercise_id
    NULLable and hint there (String(80), NOT NULL, '' by default), every
    item already there with its exercise and no hint; the tables the
    models'. Downgrade with a C item, a slot, a circuit on C, a part's name
    and a B item placed after C's present: the names' table goes, the slot
    is deleted, the hint goes and exercise_id is NOT NULL again, C's
    circuit goes (A's stays), C's items are at the end of B in their order,
    and the CHECK refuses trening_c again; a second upgrade lets C, a name
    and a slot in once more."""
    mig = _migration(PARTS)
    assert (mig.revision, mig.down_revision) == ("a7d3c5e9f214", "5e8c1a3f7b92")
    assert mig.SECTIONS == tuple(SECTIONS)                                  # its own copy agrees with the model's
    pid = db.create_program("T", None, "pocetna", "cijelo", "dvorana")
    did = db.add_day(pid)
    ex = {n: db.create_exercise(n) for n in ("Goblet čučanj", "Plank", "Sklekovi", "Most", "Bočni plank")}
    a = db.add_day_item(did, ex["Goblet čučanj"], "trening")
    b = db.add_day_item(did, ex["Plank"], "trening_b")
    insert = "INSERT INTO program_day_items (day_id, position, section, note) VALUES (:d, 99, 'trening', '')"
    _run(mig.downgrade)                                                     # the database as before the revision
    assert "program_day_parts" not in _tables()
    assert "hint" not in {c["name"] for c in sa_inspect(db.engine).get_columns("program_day_items")}
    assert not _takes("UPDATE program_day_items SET section = 'trening_c' WHERE id = :i", i=a)
    assert not _takes(insert, d=did)                                        # no exercise: refused (NOT NULL)
    _run(mig.upgrade)
    assert _schema_diffs(TRENINZI | {"program_day_parts"}) == []
    assert [c["name"] for c in sa_inspect(db.engine).get_columns("program_day_parts")] == ["day_id", "section", "title"]
    assert sa_inspect(db.engine).get_pk_constraint("program_day_parts")["constrained_columns"] == ["day_id", "section"]
    cols = {c["name"]: c for c in sa_inspect(db.engine).get_columns("program_day_items")}
    assert cols["exercise_id"]["nullable"] and not cols["hint"]["nullable"] and str(cols["hint"]["type"]) == "VARCHAR(80)"
    assert cols["hint"]["default"] == "''::character varying"
    assert [(i.id, i.section, i.hint, i.exercise_id) for i in db.get_day(did).items] == [
        (a, "trening", "", ex["Goblet čučanj"]), (b, "trening_b", "", ex["Plank"])]
    c1 = db.add_day_item(did, ex["Sklekovi"], "trening_c")                  # position 3
    c2 = db.add_day_item(did, ex["Most"], "trening_c")                      # 4
    b2 = db.add_day_item(did, ex["Bočni plank"], "trening_b")               # 5: a B item after C's
    slot = db.add_day_slot(did, "trening", "čučanj")                        # 6
    db.set_part_name(did, "trening", "Krug 1")
    db.set_circuit(did, "trening_c", 2, 30)
    db.set_circuit(did, "trening", 3, 60)
    assert _items(did) == [(a, "trening", 1, ex["Goblet čučanj"]), (b, "trening_b", 2, ex["Plank"]),
                           (c1, "trening_c", 3, ex["Sklekovi"]), (c2, "trening_c", 4, ex["Most"]),
                           (b2, "trening_b", 5, ex["Bočni plank"]), (slot, "trening", 6, None)]
    _run(mig.downgrade)
    assert "program_day_parts" not in _tables() and circuits_of(did) == {"trening": (3, 60)}
    assert _items(did) == [(a, "trening", 1, ex["Goblet čučanj"]), (b, "trening_b", 2, ex["Plank"]),
                           (b2, "trening_b", 5, ex["Bočni plank"]), (c1, "trening_b", 8, ex["Sklekovi"]),
                           (c2, "trening_b", 9, ex["Most"])]                 # the slot gone; C at the end of B
    assert not _takes("UPDATE program_day_items SET section = 'trening_c' WHERE id = :i", i=a)
    assert not _takes(insert, d=did)
    _run(mig.upgrade)
    assert _schema_diffs(TRENINZI | {"program_day_parts"}) == []
    assert _takes("UPDATE program_day_items SET section = 'trening_c' WHERE id = :i", i=c2)
    assert db.add_day_slot(did, "trening", "potisak") and db.set_part_name(did, "trening", "Krug 1")
    day = db.get_day(did)
    assert (day.part_label("trening"), day.slot_count, [it.id for it in day.by_section["trening_c"]]) == ("Krug 1", 1, [c2])


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
    pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); localStorage.setItem('qmt-phone', String(Date.now())); }")
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
            pg.tap("#add-ex-q")                    # the combobox (23.11.2026): a few letters, then a row tapped
            pg.keyboard.type("gob")
            pg.tap(f'#add-ex-list [role="option"][data-id="{made.id}"]')
            check(pg.input_value("#add-ex") == str(made.id), f"the tapped row chose {pg.input_value('#add-ex')!r}")
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
    ("+ Dodaj trening", which opens its editor), taps "+ Dodaj vježbu u
    ovaj dio" under Zagrijavanje (25.11.2026: in place, no reload: the add
    card's Dio set to it, the card scrolled to, the focus in the picker,
    its list shut), picks "Goblet čučanj" and types 2 × 15 in the card's
    numbers, adds it (back at the card: "Dodano u Zagrijavanje: Goblet
    čučanj.", its Dio as it was, the focus in the picker), sets 30 s of
    rest on its row and saves, then follows "pogledaj kako polaznik vidi →"
    to the client's day page and sees the row: "Vježba 1", the name, "2 ×
    15", "Odmor između serija: 30 s"; a tap opens it in place. The matched
    client sees the same. The programme's editor, the day's editor and the
    day's page never scroll sideways; no page errors."""
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
        edit = f"{server}/treninzi/{pid}/dan/{did}/uredi"
        check(len(days) == 1 and pg.url == edit, f"+ Dodaj trening led to {pg.url}")
        picker = """() => { const q = document.getElementById('add-ex-q').getBoundingClientRect();
                            return {dio: document.getElementById('add-dio').value,
                                    focused: document.activeElement && document.activeElement.id,
                                    open: !document.getElementById('add-ex-list').hidden,
                                    seen: q.top >= 0 && q.bottom <= innerHeight}; }"""
        st = pg.evaluate(picker)
        check(not st["seen"] and st["focused"] != "add-ex-q", f"the add card in view before the tap: {st}")
        pg.tap('a.st-add[data-dio="zagrijavanje"]')                         # in place: no navigation
        pg.wait_for_timeout(300)
        st = pg.evaluate(picker)
        check(pg.url == edit and st["dio"] == "zagrijavanje" and st["focused"] == "add-ex-q" and not st["open"]
              and st["seen"], f"+ Dodaj vježbu u ovaj dio: {pg.url}, {st}")
        pg.keyboard.type("goblet")                 # the combobox (23.11.2026): typed, Enter picks the first row
        pg.keyboard.press("Enter")
        pg.fill("#add-sets", "2")
        pg.fill("#add-reps", "15")
        check(pg.evaluate(OVERFLOW) == 0, f"the add card overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap("#dodaj button[type=submit]")
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(200)
        items = db.get_day(did).items if did else []
        check([(i.exercise_id, i.section, i.sets, i.reps) for i in items] == [(goblet, "zagrijavanje", 2, 15)],
              f"the day holds {[(i.exercise_id, i.section, i.sets, i.reps) for i in items]}")
        st = pg.evaluate(picker)
        check(unquote(pg.url) == f"{edit}?dodaj=zagrijavanje&ok=Dodano u Zagrijavanje: Goblet čučanj.#dodaj",
              f"Dodaj led to {unquote(pg.url)}")
        check((pg.text_content("#dodaj .alert.ok") or "") == "Dodano u Zagrijavanje: Goblet čučanj."
              and st["dio"] == "zagrijavanje" and st["focused"] == "add-ex-q" and not st["open"],
              f"back at the card: {pg.text_content('#dodaj .alert.ok')!r}, {st}")
        if items:
            row = f"#stavka-{items[0].id}"
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


CBX = """() => {
  const q = document.getElementById('add-ex-q'), l = document.getElementById('add-ex-list'), s = document.getElementById('add-ex');
  const opts = [...l.querySelectorAll('[role="option"]')], qr = q.getBoundingClientRect(), lr = l.getBoundingClientRect();
  return {open: !l.hidden, expanded: q.getAttribute('aria-expanded'), typed: q.value, chosen: s.value,
          hidden: s.hidden && s.offsetHeight === 0, required: s.required,
          label: !!document.querySelector('label[for="add-ex-q"]'), shown: opts.map(o => o.querySelector('.cbx-name').textContent),
          active: (a => a ? a.querySelector('.cbx-name').textContent : null)(document.getElementById(q.getAttribute('aria-activedescendant') || '')),
          focused: document.activeElement === q, error: document.getElementById('add-ex-err').textContent,
          wide: Math.round(lr.width) === Math.round(qr.width) || l.hidden};
}"""


def test_dodaj_vjezbu_filters_as_it_is_typed_on_a_phone(server):
    """"Dodaj vježbu" is a combobox at 390px, touch (23.11.2026, the owner:
    "start typing in the exercise and then show only those"): the select
    stays in the form, hidden and no longer required (it carries the value
    posted), its label naming the input. A focus opens the list of every
    exercise in the alphabet's order, as wide as the input; "cuc" keeps the
    two squats, the one whose name starts with it first, and not the plank,
    the first active; Enter picks it (the select's value, the name in the
    input, the list shut, the focus kept, nothing sent). Typing again
    clears the select; Enter picks again. Dodaj adds it to the day (its row
    on the page). Dodaj with nothing chosen sends nothing and says
    "Odaberi vježbu s popisa." under the input. ?vjezba=<id> (back from
    "Nova vježba") shows that name. Without JS the select is the picker it
    was: shown and required, no combobox."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    ids = {n: db.create_exercise(n, tags=t) for n, t in (("Goblet čučanj", "noge, bučice"), ("Plank", "core"),
                                                         ("Čučanj s vlastitom težinom", "noge, kod kuće"),
                                                         ("Biceps pregib", ""))}
    edit = f"{server}/treninzi/{pid}/dan/{did}/uredi"
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _phone(browser, server, "trener@test.local")
        pg.goto(edit); pg.wait_for_load_state("networkidle")
        st = pg.evaluate(CBX)
        check(st["hidden"] and not st["required"] and st["label"] and not st["open"] and st["typed"] == "",
              f"the combobox at load: {st}")
        pg.tap("#dodaj button[type=submit]")                                 # nothing chosen: nothing sent
        pg.wait_for_timeout(400)
        st = pg.evaluate(CBX)
        check(pg.url == edit and db.get_day(did).items == [], f"Dodaj with nothing chosen went to {pg.url}")
        check(st["error"] == "Odaberi vježbu s popisa." and st["focused"], f"Dodaj with nothing chosen says: {st}")
        check(pg.is_visible("#add-ex-err"), "the line under the input is not shown")
        pg.evaluate("() => document.getElementById('add-ex-q').blur()")
        pg.tap("#add-ex-q")
        st = pg.evaluate(CBX)
        check(st["open"] and st["expanded"] == "true" and st["wide"]
              and st["shown"] == ["Biceps pregib", "Čučanj s vlastitom težinom", "Goblet čučanj", "Plank"]
              and st["active"] is None, f"a focus does not open every exercise: {st}")
        pg.keyboard.type("cuc")
        st = pg.evaluate(CBX)
        check(st["shown"] == ["Čučanj s vlastitom težinom", "Goblet čučanj"] and "Plank" not in st["shown"]
              and st["active"] == "Čučanj s vlastitom težinom", f"'cuc' shows: {st}")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(300)
        st = pg.evaluate(CBX)
        check(st["chosen"] == str(ids["Čučanj s vlastitom težinom"]) and st["typed"] == "Čučanj s vlastitom težinom"
              and not st["open"] and st["focused"] and st["error"] == "" and pg.url == edit, f"Enter picked: {st}")
        pg.keyboard.press("Backspace")                                       # typing again: nothing chosen
        st = pg.evaluate(CBX)
        check(st["chosen"] == "" and st["open"], f"typing after a pick kept the choice: {st}")
        pg.keyboard.type("m")
        pg.keyboard.press("Enter")
        check(pg.evaluate(CBX)["chosen"] == str(ids["Čučanj s vlastitom težinom"]), "Enter did not pick again")
        with pg.expect_navigation():
            pg.tap("#dodaj button[type=submit]")
        pg.wait_for_load_state("networkidle")
        check(item_names(pid) == ["Čučanj s vlastitom težinom"], f"the day holds {item_names(pid)}")
        check(pg.is_visible(f'a.it-name[href="/treninzi/vjezbe/{ids["Čučanj s vlastitom težinom"]}"]'),
              "the added exercise's row is not on the page")
        check(pg.evaluate(OVERFLOW) == 0, f"the day's editor overflows by {pg.evaluate(OVERFLOW)}px")
        pg.goto(f"{edit}?vjezba={ids['Plank']}#dodaj"); pg.wait_for_load_state("networkidle")
        st = pg.evaluate(CBX)
        check(st["typed"] == "Plank" and st["chosen"] == str(ids["Plank"]), f"?vjezba= shows: {st}")
        problems += errors
        ctx.close()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, java_script_enabled=False)
        pg = ctx.new_page()
        pg.goto(server + "/login")
        pg.fill("main input[name=email]", "trener@test.local"); pg.fill("main input[name=password]", "lozinka123")
        with pg.expect_navigation():
            pg.click("main button[type=submit]")
        pg.goto(edit); pg.wait_for_load_state("networkidle")
        check(pg.is_visible("#add-ex") and pg.get_attribute("#add-ex", "required") is not None
              and pg.locator("#add-ex-q").count() == 0, "without JS the select is not the picker it was")
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


LIB = """() => {
  const q = document.querySelector('form.ex-search input[name="q"]'), b = document.querySelector('form.ex-search button');
  const found = document.querySelector('.ex-found'), none = document.querySelector('.ex-none');
  const seen = el => !el.hidden && el.offsetHeight > 0;
  return {shown: [...document.querySelectorAll('a.ex-row')].filter(seen).map(a => a.querySelector('.ex-name').textContent),
          typed: q.value, path: location.pathname, search: location.search, traži: seen(b),
          count: seen(found) ? found.textContent.trim().split(' · ')[0] : null,
          none: seen(none) ? none.textContent.trim() : null,
          focused: document.activeElement === q, stayed: window.__stayed === true};
}"""


def test_the_library_filters_as_it_is_typed_on_a_phone(server):
    """The library's search filters as it is typed at 390px, touch
    (23.11.2026, the owner: "I want this to be in real time i.e. when I
    search the dropdown changes"): "Traži" is gone and the count line hidden
    until the box holds text; "cuc" keeps the two squats (every word in the
    name or the tags, folded), "2 od 4", and the address follows (?q=cuc,
    replaced, a little after the last key, no navigation); Enter sends
    nothing and lets the focus go (the phone's keyboard closes); "cucx" keeps none and says
    so, „cucx”, "0 od 4"; the box emptied shows all, the count hidden, the
    address bare; "kod kuce", two words of a tag, keeps the plank and the
    squat; "prikaži sve" shows all in place, the address bare, the focus in
    the box. ?q=plank opened shows the plank alone before the script (the
    server's hidden rows) and after it, "1 od 4". The page never scrolls
    sideways; no page errors. Without JS ?q=cuc is the form it was: the two
    squats, "Traži", the count, no none line."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)
    for n, t in (("Plank", "core, kod kuće"), ("Goblet čučanj", "noge, bučice"),
                 ("Čučanj s vlastitom težinom", "noge, kod kuće"), ("Biceps pregib", "")):
        db.create_exercise(n, tags=t)
    every = ["Biceps pregib", "Čučanj s vlastitom težinom", "Goblet čučanj", "Plank"]
    squats = ["Čučanj s vlastitom težinom", "Goblet čučanj"]
    lib, box = f"{server}/treninzi/vjezbe", 'form.ex-search input[name="q"]'
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _phone(browser, server, "trener@test.local")
        pg.goto(lib); pg.wait_for_load_state("networkidle")
        st = pg.evaluate(LIB)
        check(st["shown"] == every and not st["traži"] and st["count"] is None and st["none"] is None,
              f"the bare page: {st}")
        pg.evaluate("() => { window.__stayed = true; }")                   # a navigation would drop it
        pg.tap(box)
        pg.keyboard.type("cuc")
        st = pg.evaluate(LIB)
        check(st["shown"] == squats and st["count"] == "2 od 4" and st["none"] is None and st["stayed"], f"'cuc' shows: {st}")
        pg.wait_for_timeout(400)                                           # the address follows a little after
        st = pg.evaluate(LIB)
        check((st["path"], st["search"]) == ("/treninzi/vjezbe", "?q=cuc") and st["stayed"], f"'cuc' left the address: {st}")
        check(pg.evaluate(OVERFLOW) == 0, f"the list filtered overflows by {pg.evaluate(OVERFLOW)}px")
        pg.keyboard.press("Enter")                                         # the keyboard's Go: nothing sent,
        pg.wait_for_timeout(400)                                           # the keyboard closed (the focus let go)
        st = pg.evaluate(LIB)
        check(st["stayed"] and st["shown"] == squats and st["typed"] == "cuc" and st["search"] == "?q=cuc"
              and not st["focused"], f"Enter changed something: {st}")
        pg.tap(box)
        pg.keyboard.type("x")
        pg.wait_for_timeout(400)
        st = pg.evaluate(LIB)
        check(st["shown"] == [] and st["none"] == "Nijedna vježba ne odgovara traženju „cucx”."
              and st["count"] == "0 od 4" and st["search"] == "?q=cucx", f"'cucx' shows: {st}")
        check(pg.evaluate(OVERFLOW) == 0, f"the none line overflows by {pg.evaluate(OVERFLOW)}px")
        pg.fill(box, "")
        pg.wait_for_timeout(400)
        st = pg.evaluate(LIB)
        check(st["shown"] == every and st["count"] is None and st["none"] is None
              and (st["path"], st["search"]) == ("/treninzi/vjezbe", ""), f"the box emptied shows: {st}")
        pg.keyboard.type("kod kuce")                                       # two words of the tag "kod kuće"
        pg.wait_for_timeout(400)
        st = pg.evaluate(LIB)
        check(st["shown"] == ["Čučanj s vlastitom težinom", "Plank"] and st["count"] == "2 od 4"
              and st["search"] == "?q=kod%20kuce", f"'kod kuce' shows: {st}")
        pg.tap(".ex-found a")                                              # "prikaži sve": in place
        pg.wait_for_timeout(400)
        st = pg.evaluate(LIB)
        check(st["stayed"] and st["shown"] == every and st["typed"] == "" and st["count"] is None
              and (st["path"], st["search"]) == ("/treninzi/vjezbe", "") and st["focused"],
              f"'prikaži sve' left: {st}")
        r = pg.goto(lib + "?q=plank")
        check(names(r.text()) == ["Plank"] and all_names(r.text()) == every, f"?q=plank as served: {names(r.text())}")
        pg.wait_for_load_state("networkidle")
        st = pg.evaluate(LIB)
        check(st["shown"] == ["Plank"] and st["count"] == "1 od 4" and st["typed"] == "plank"
              and st["search"] == "?q=plank" and not st["traži"], f"?q=plank shows: {st}")
        check(pg.evaluate(OVERFLOW) == 0, f"?q=plank overflows by {pg.evaluate(OVERFLOW)}px")
        problems += errors
        ctx.close()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, java_script_enabled=False)
        pg = ctx.new_page()
        pg.goto(server + "/login")
        pg.fill("main input[name=email]", "trener@test.local"); pg.fill("main input[name=password]", "lozinka123")
        with pg.expect_navigation():
            pg.click("main button[type=submit]")
        pg.goto(lib + "?q=cuc"); pg.wait_for_load_state("networkidle")
        shown = pg.locator("a.ex-row:visible .ex-name").all_text_contents()
        check(shown == squats and pg.is_visible("form.ex-search button") and pg.is_visible(".ex-found")
              and "2 od 4" in " ".join((pg.text_content(".ex-found") or "").split()) and not pg.is_visible(".ex-none"),
              f"without JS ?q=cuc shows {shown}, Traži {pg.is_visible('form.ex-search button')}, "
              f"the count {pg.is_visible('.ex-found')}, the none line {pg.is_visible('.ex-none')}")
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# the browser tests' library for the chips: 13 exercises whose tags make 14
# chips (noge 5; bodyweight, bučica, girja, hinge, horizontalni potisak 3;
# antirotacija, chest, glute, iskorak, leđa, most, rame, TRX 2: "TRX" and
# "trx" one tag) and three tags carried once (čučanj, core, horizontalno
# povlačenje: no chip)
CHIP_LIBRARY = (("Goblet čučanj", "čučanj, noge, girja"), ("Swing", "hinge, girja"),
                ("Mrtvo dizanje s girjom", "hinge, noge, girja"), ("Rumunjsko mrtvo dizanje", "hinge, noge, bučica"),
                ("Sklek", "horizontalni potisak, bodyweight"), ("Potisak s bučicama", "horizontalni potisak, bučica"),
                ("TRX veslanje", "horizontalno povlačenje, TRX"), ("TRX sklek", "horizontalni potisak, trx"),
                ("Plank", "core, bodyweight"), ("Iskorak", "iskorak, noge, bodyweight"),
                ("Iskorak s bučicama", "iskorak, noge, bučica"),
                ("Vježba A", "rame, most, glute, chest, leđa, antirotacija"),
                ("Vježba B", "rame, most, glute, chest, leđa, antirotacija"))
CHIP_ORDER = ["noge", "bodyweight", "bučica", "girja", "hinge", "horizontalni potisak", "antirotacija", "chest", "glute",
              "iskorak", "leđa", "most", "rame", "TRX"]
# the tags' row as a reader sees it: shown, the chips shown, the pressed
# ones, "još N", the box's text and focus, the chips' lowest height
TAGS = """() => {
  const bar = document.querySelector('.tagbar'), box = document.querySelector('form.ex-search input[name="q"], #add-ex-q');
  const seen = el => !el.hidden && el.offsetHeight > 0, chips = [...bar.querySelectorAll('.tag-chip[data-tag]')];
  const more = bar.querySelector('.tag-more');
  return {row: seen(bar), chips: chips.filter(seen).map(c => c.textContent),
          pressed: chips.filter(c => c.getAttribute('aria-pressed') === 'true').map(c => c.textContent),
          more: more && seen(more) ? more.textContent : null, typed: box.value, focused: document.activeElement === box,
          low: Math.min(...chips.filter(seen).map(c => c.getBoundingClientRect().height))};
}"""


def test_a_tag_chip_filters_the_library_on_a_phone(server):
    """The library's chips at 390px, touch (23.11.2026): the script shows
    the row, the first 12 chips and "još 2", each 36px at least. A tap on
    "girja" puts it in the box, presses the chip and filters the list
    ("3 od 13"), the address following (?q=girja), the focus kept off the
    box (no phone keyboard over the list); a tap on "hinge" adds its word
    ("girja hinge") and narrows; a second tap on "girja" takes its word out
    ("hinge") and releases it. The ✕ in the box empties it: every chip
    released, every row back. A tag typed by hand presses its chip once its
    word is whole ("nog" none, "NOGE" noge), and a chip tapped then joins
    the typed words ("NOGE bučica"); "prikaži sve" releases them. A two-word
    tag goes in and out as its two words. "još 2" shows the rest and goes;
    "TRX" keeps both spellings' exercises. The page never scrolls sideways;
    no page errors. Without JS the <noscript> row of links is the helper:
    "girja" opens ?q=girja, its link pressed."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)
    for name, tags in CHIP_LIBRARY:
        db.create_exercise(name, tags=tags)
    lib, box = f"{server}/treninzi/vjezbe", 'form.ex-search input[name="q"]'
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    def chip(tag: str) -> str:
        return f'.tagbar .tag-chip[data-tag="{tag}"]'

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _phone(browser, server, "trener@test.local")
        pg.goto(lib); pg.wait_for_load_state("networkidle")
        st = pg.evaluate(TAGS)
        check(st["row"] and st["chips"] == CHIP_ORDER[:12] and st["more"] == "još 2" and st["pressed"] == []
              and st["low"] >= 36, f"the row at load: {st}")
        check(pg.evaluate(OVERFLOW) == 0, f"the library with its chips overflows by {pg.evaluate(OVERFLOW)}px")
        pg.tap(chip("girja"))
        st, rows = pg.evaluate(TAGS), pg.evaluate(LIB)
        check(st["typed"] == "girja" and st["pressed"] == ["girja"] and not st["focused"]
              and rows["shown"] == ["Goblet čučanj", "Mrtvo dizanje s girjom", "Swing"] and rows["count"] == "3 od 13",
              f"a tap on girja: {st}, {rows}")
        pg.wait_for_timeout(400)
        check(pg.evaluate(LIB)["search"] == "?q=girja", f"the address after girja: {pg.evaluate(LIB)}")
        pg.tap(chip("hinge"))
        st, rows = pg.evaluate(TAGS), pg.evaluate(LIB)
        check(st["typed"] == "girja hinge" and st["pressed"] == ["girja", "hinge"]
              and rows["shown"] == ["Mrtvo dizanje s girjom", "Swing"], f"girja, then hinge: {st}, {rows}")
        pg.tap(chip("girja"))                                              # pressed: its word goes
        st, rows = pg.evaluate(TAGS), pg.evaluate(LIB)
        check(st["typed"] == "hinge" and st["pressed"] == ["hinge"]
              and rows["shown"] == ["Mrtvo dizanje s girjom", "Rumunjsko mrtvo dizanje", "Swing"],
              f"girja tapped again: {st}, {rows}")
        pg.focus(box)                                                      # the ✕ at the box's right end
        r = pg.locator(box).bounding_box()
        pg.touchscreen.tap(r["x"] + r["width"] - 18, r["y"] + r["height"] / 2)
        pg.wait_for_timeout(300)
        st, rows = pg.evaluate(TAGS), pg.evaluate(LIB)
        check(st["typed"] == "" and st["pressed"] == [] and len(rows["shown"]) == 13 and rows["count"] is None,
              f"the ✕: {st}, {rows}")
        pg.focus(box)
        pg.keyboard.type("nog")
        check(pg.evaluate(TAGS)["pressed"] == [], f"'nog' pressed {pg.evaluate(TAGS)['pressed']}")
        pg.fill(box, "NOGE")
        st, rows = pg.evaluate(TAGS), pg.evaluate(LIB)
        check(st["pressed"] == ["noge"] and len(rows["shown"]) == 5, f"'NOGE' typed: {st}, {rows}")
        pg.tap(chip("bučica"))
        st, rows = pg.evaluate(TAGS), pg.evaluate(LIB)
        check(st["typed"] == "NOGE bučica" and st["pressed"] == ["noge", "bučica"]
              and rows["shown"] == ["Iskorak s bučicama", "Rumunjsko mrtvo dizanje"], f"NOGE, then bučica: {st}, {rows}")
        pg.tap(".ex-found a")                                              # "prikaži sve"
        st = pg.evaluate(TAGS)
        check(st["typed"] == "" and st["pressed"] == [], f"'prikaži sve': {st}")
        pg.tap(chip("horizontalni potisak"))
        st, rows = pg.evaluate(TAGS), pg.evaluate(LIB)
        check(st["typed"] == "horizontalni potisak" and st["pressed"] == ["horizontalni potisak"]
              and rows["shown"] == ["Potisak s bučicama", "Sklek", "TRX sklek"], f"a two-word tag: {st}, {rows}")
        pg.tap(chip("horizontalni potisak"))
        check(pg.evaluate(TAGS)["typed"] == "", f"a two-word tag tapped again: {pg.evaluate(TAGS)}")
        pg.tap(".tagbar .tag-more")
        st = pg.evaluate(TAGS)
        check(st["chips"] == CHIP_ORDER and st["more"] is None and pg.locator(".tagbar .tag-more").count() == 0,
              f"'još 2': {st}")
        check(pg.evaluate(OVERFLOW) == 0, f"every chip shown overflows by {pg.evaluate(OVERFLOW)}px")
        pg.tap(chip("TRX"))
        st, rows = pg.evaluate(TAGS), pg.evaluate(LIB)
        check(st["pressed"] == ["TRX"] and rows["shown"] == ["TRX sklek", "TRX veslanje"], f"TRX: {st}, {rows}")
        problems += errors
        ctx.close()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, java_script_enabled=False)
        pg = ctx.new_page()
        pg.goto(server + "/login")
        pg.fill("main input[name=email]", "trener@test.local"); pg.fill("main input[name=password]", "lozinka123")
        with pg.expect_navigation():
            pg.click("main button[type=submit]")
        pg.goto(lib); pg.wait_for_load_state("networkidle")
        links = pg.locator("a.tag-chip:visible").all_text_contents()
        check(links == CHIP_ORDER and pg.locator("button.tag-chip:visible").count() == 0,
              f"without JS the links are {links}")
        with pg.expect_navigation():
            pg.click('a.tag-chip:visible >> text="girja"')
        shown = pg.locator("a.ex-row:visible .ex-name").all_text_contents()
        check(pg.url.endswith("/treninzi/vjezbe?q=girja") and shown == ["Goblet čučanj", "Mrtvo dizanje s girjom", "Swing"]
              and pg.get_attribute('a.tag-chip[aria-current="true"]', "href") == "/treninzi/vjezbe",
              f"without JS girja led to {pg.url}, {shown}")
        check(pg.evaluate(OVERFLOW) == 0, f"without JS the links overflow by {pg.evaluate(OVERFLOW)}px")
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


def test_a_tag_chip_opens_dodaj_vjezbu_filtered_on_a_phone(server):
    """The day editor's chips at 390px, touch (23.11.2026): the script
    shows the row under the fields (12 chips and "još 2"); a tap on "girja"
    puts it in the combobox's input, leaves the focus there and opens its
    list with the girja exercises, the chip pressed; a pick puts the
    exercise's name in the input and releases the chip; Dodaj adds it. No
    sideways scroll, no page errors. Without JS the row stays hidden (the
    select is the picker)."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)
    pid = db.create_program("Cijelo tijelo — početna", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    ids = {name: db.create_exercise(name, tags=tags) for name, tags in CHIP_LIBRARY}
    edit = f"{server}/treninzi/{pid}/dan/{did}/uredi"
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _phone(browser, server, "trener@test.local")
        pg.goto(edit); pg.wait_for_load_state("networkidle")
        st = pg.evaluate(TAGS)
        check(st["row"] and st["chips"] == CHIP_ORDER[:12] and st["more"] == "još 2" and st["low"] >= 36,
              f"the row at load: {st}")
        bar, q = pg.locator(".tagbar").bounding_box(), pg.locator("#add-ex-q").bounding_box()
        go = pg.locator("#dodaj button[type=submit]").bounding_box()
        check(bar["y"] + bar["height"] <= q["y"] and q["y"] + q["height"] <= go["y"],
              f"the row is not above the fields (the open list must never cover it): {bar}, {q}, {go}")
        pg.tap('.tagbar .tag-chip[data-tag="girja"]')
        st, cbx = pg.evaluate(TAGS), pg.evaluate(CBX)
        check(st["typed"] == "girja" and st["focused"] and st["pressed"] == ["girja"], f"a tap on girja: {st}")
        check(cbx["open"] and cbx["expanded"] == "true" and cbx["chosen"] == ""
              and cbx["shown"] == ["Goblet čučanj", "Mrtvo dizanje s girjom", "Swing"], f"the list after girja: {cbx}")
        check(pg.evaluate(OVERFLOW) == 0, f"the day's editor overflows by {pg.evaluate(OVERFLOW)}px")
        pg.tap('#add-ex-list [role="option"] >> text="Swing"')
        st, cbx = pg.evaluate(TAGS), pg.evaluate(CBX)
        check(st["typed"] == "Swing" and st["pressed"] == [] and cbx["chosen"] == str(ids["Swing"]) and not cbx["open"],
              f"a pick: {st}, {cbx}")
        with pg.expect_navigation():
            pg.tap("#dodaj button[type=submit]")
        pg.wait_for_load_state("networkidle")
        check(item_names(pid) == ["Swing"], f"the day holds {item_names(pid)}")
        problems += errors
        ctx.close()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, java_script_enabled=False)
        pg = ctx.new_page()
        pg.goto(server + "/login")
        pg.fill("main input[name=email]", "trener@test.local"); pg.fill("main input[name=password]", "lozinka123")
        with pg.expect_navigation():
            pg.click("main button[type=submit]")
        pg.goto(edit); pg.wait_for_load_state("networkidle")
        check(pg.locator(".tagbar").count() == 1 and not pg.is_visible(".tagbar") and pg.is_visible("#add-ex"),
              "without JS the day editor's chips show")
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


def test_the_trainer_builds_a_template_on_a_phone(server):
    """At 390px, touch (26.11.2026, build 2): the trainer opens the seed's
    template's editor (scripts/seed_demo.py's seed_template: a dvoranski
    day of slots alone, its Glavni dio A "Krug 1" and a circuit), its
    caption "Krug 1 (Glavni dio A)"; adds a slot through the add card's
    "Dodaj prazno mjesto" (Dio Krug 1, 12 reps, Natuknica "iskorak", Enter
    in it: the slot, never an exercise), back at the card saying "Dodano u
    Krug 1: prazno mjesto."; fills the "čučanj" slot: "Popuni vježbom" opens
    its combobox with "čučanj" typed in and its list already narrowed to
    the two squats, a tap picks "Goblet čučanj" and Postavi makes the row an
    ordinary one, "Spremljeno." in it; then renames Glavni dio B "Snaga"
    through its "Preimenuj". The page never scrolls sideways at 390 or
    360px (the forms open too); no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)
    path = pathlib.Path(__file__).parents[1] / "scripts" / "seed_demo.py"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    seed = importlib.util.module_from_spec(spec); spec.loader.exec_module(seed)
    seed.seed_template()
    goblet = db.create_exercise("Goblet čučanj", tags="noge, bučice")
    db.create_exercise("Čučanj s vlastitom težinom", tags="noge")
    db.create_exercise("Plank", tags="core")
    [pid] = [p.id for p, *_ in db.all_programs()]
    did = db.get_program(pid).days[0].id
    squat = next(it.id for it in db.get_day(did).items if it.hint == "čučanj")
    edit = f"{server}/treninzi/{pid}/dan/{did}/uredi"
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    shown = """id => [...document.querySelectorAll('#' + id + '-list [role="option"] .cbx-name')].map(n => n.textContent)"""
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _phone(browser, server, "trener@test.local")
        pg.goto(edit); pg.wait_for_load_state("networkidle")
        check(" ".join(pg.text_content("#dio-trening").split()) == "Krug 1 (Glavni dio A)",
              f"the renamed part's caption: {pg.text_content('#dio-trening')!r}")
        check(pg.evaluate(OVERFLOW) == 0, f"the template's editor overflows by {pg.evaluate(OVERFLOW)}px")

        pg.select_option("#add-dio", "trening")                            # "Dodaj prazno mjesto": the card's Dio and numbers
        pg.fill("#add-reps", "12")
        pg.tap("#add-hint")
        pg.keyboard.type("iskorak")
        with pg.expect_navigation():
            pg.keyboard.press("Enter")                                      # its own button, never "Dodaj"
        pg.wait_for_load_state("networkidle")
        made = db.get_day(did).items[-1]
        check((made.is_slot, made.section, made.hint, made.reps) == (True, "trening", "iskorak", 12),
              f"the slot made: {(made.is_slot, made.section, made.hint, made.reps)}")
        check(pg.is_visible("#dodaj >> text=Dodano u Krug 1: prazno mjesto."), "the add card says nothing")

        fill = f"st-{squat}-fill"
        pg.locator(f"#stavka-{squat} details.st-fill > summary").tap()
        pg.wait_for_timeout(300)
        check(pg.input_value(f"#{fill}-q") == "čučanj" and pg.is_visible(f"#{fill}-list"),
              f"Popuni vježbom opened on {pg.input_value(f'#{fill}-q')!r}, its list shown: {pg.is_visible(f'#{fill}-list')}")
        check(pg.evaluate(shown, fill) == ["Čučanj s vlastitom težinom", "Goblet čučanj"],
              f"the list narrowed by the hint: {pg.evaluate(shown, fill)}")
        check(pg.evaluate(OVERFLOW) == 0, f"the open combobox overflows the page by {pg.evaluate(OVERFLOW)}px")
        pg.tap(f'#{fill}-list [role="option"][data-id="{goblet}"]')
        check(pg.input_value(f"#{fill}") == str(goblet), f"the tap chose {pg.input_value(f'#{fill}')!r}")
        with pg.expect_navigation():
            pg.tap(f"#stavka-{squat} .st-fill-form button[type=submit]")
        pg.wait_for_load_state("networkidle")
        it = db.get_day_item(squat)
        check((it.exercise_id, it.hint) == (goblet, "čučanj"), f"the slot filled: {(it.exercise_id, it.hint)}")
        check(pg.is_visible(f'#stavka-{squat} a.it-name[href="/treninzi/vjezbe/{goblet}"]')
              and pg.is_visible(f"#stavka-{squat} >> text=Spremljeno."), "the filled row is not an ordinary one, or says nothing")

        part = 'section[aria-labelledby="dio-trening_b"]'
        pg.locator(f"{part} details.st-name > summary").tap()
        pg.fill("#naziv-trening_b", "Snaga")
        check(pg.evaluate(OVERFLOW) == 0, f"Preimenuj open overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap(f"{part} .st-name-form button[type=submit]")
        pg.wait_for_load_state("networkidle")
        check(parts_of(did) == {"trening": "Krug 1", "trening_b": "Snaga"}, f"the names: {parts_of(did)}")
        check(" ".join(pg.text_content("#dio-trening_b").split()) == "Snaga (Glavni dio B)",
              f"the renamed caption: {pg.text_content('#dio-trening_b')!r}")
        check(pg.evaluate(OVERFLOW) == 0, f"the editor overflows by {pg.evaluate(OVERFLOW)}px at 390")
        pg.set_viewport_size({"width": 360, "height": 780})
        for summary in ('section[aria-labelledby="dio-trening"] details.st-name > summary',
                        'section[aria-labelledby="dio-zagrijavanje"] details.st-circ:not(.st-name) > summary',
                        "details.st-fill > summary"):
            pg.locator(summary).first.tap()
        pg.wait_for_timeout(200)
        check(pg.evaluate(OVERFLOW) == 0, f"the editor, its forms open, overflows by {pg.evaluate(OVERFLOW)}px at 360")
        problems += errors
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"
