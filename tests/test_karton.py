"""Karton: access control, the upitnik's gate on online treninzi, diary
ownership. The upitnik itself (its scoring, its route, its block on the
karton) is tests/test_upitnik.py.

Since 23.11.2026 (Amir: "da si on može sam upisati koji trening je radio …
izračun maksova, na primjer ako radi bench, napravi mi sa 90 kila 6
ponavljanja … da mu automatski kalkulira njegov maks u benchu"; the owner's
decisions the same day) a training's osvrt carries the exercises done
(TrainingLog.sets, migration f43e976906a1, run for real on qmt_test there and
back): picked from the library with the day editor's combobox, then sets
with reps and kilograms, several exercises per training. The same block is
in the osvrt of a termin, in its edit, and in a training outside a termin
(dated by the member). The page's script builds every block: the library is
on the page once, as JSON, and a stored log is its form's data; without the
script there is no block, and the routes read the blocks only with the log=1
the script adds (db.read_log), so an edit sent without it keeps its log. The
diary shows how many exercises and their sets ("Serije", the online passes'
too, the client's as the trainer's). The karton estimates each exercise's
max (db.estimated_maxes: Epley's formula over the best set, gym and online
alike, a bodyweight exercise's most reps). The browser half fills the osvrt
on a phone, with the script and without it.

The karton's part 2, the same day (Amir: "tjelesna visina, tjelesna masa,
onda slika jednomjesečno … ograničenja koja će se on napisati, bolovi itd.";
the owner: "Height is one number, weight a dated history, limitations a free
text, the photo optional and shrunk like the landing's photos, visible to the
member and Amir only"; migration 0401f7fb9861, run for real on qmt_test there
and back): the height on /profil and in the karton's head line, the weight
card (one value a day, the history, its ✕), "Ograničenja i bolovi" (the
member's text, the trainer's amber chip), and "Napredak — fotografije" (one
photo a month, shrunk and bare as an announcement's, served by /media to the
member and staff only), in a test client, under racing writes and on a
phone.

Since 24.11.2026 staff (the trainer, the owner) have a karton of their own
at /karton (the owner: "Lets show the Karton tab in the Admin view as well
so that Amir can check out the changes we made there"): a member's, less
the upitnik card and the termini. And the maxes never count a set that
holds seconds: since the same day an online exercise may ask for reps and
seconds, its sets {"reps": 5, "seconds": 30}.

Since 25.11.2026 the karton is one column, the diary last (the owner:
"Everything should be one above the other and the 'dnevnik treninga'
should be last"; from 1000px its cards in two columns above the diary:
"if you have more room on the PC layout, you can use more columns"), read
in a browser on the three views; and its texts are copy slots, printed in
spans (bare() reads through them; tests/test_copy.py proves them).

The karton again, the same day (Amir: "U ograničenja i bolovi treba dodati
mogućnost da se doda slika ili pdf. … Tjelesna masa tu bi promijenio u
tjelesna kompozicija gdje opet mogu dodati pdf ili sliku ili samo upisati
ručno masu"; the owner: "We need a search bar for each user. Admins can
access everyone's karton and search a particular exercise."; migration
2b7e4c9a61d3, run for real on qmt_test there and back): documents under the
limitations (a PDF as it came, an image shrunk; ten at most, under the
member's row lock), "Tjelesna kompozicija" (an entry a mass, a document or
both), /media serving each kind to its member and staff only, and
"Povijest vježbe" (db.logged_exercises, db.exercise_history: every time
an exercise was done, gym and online alike), in a test client, under
racing writes and on a phone."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import threading
import time
from datetime import date, datetime, timedelta
from html import unescape
from urllib.parse import unquote

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import io
from decimal import Decimal

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import inspect as sa_inspect, text as sa_text
from sqlalchemy.exc import IntegrityError

from qmt import auth, config, copy, db, storage
from qmt.models import Base, Booking, User
from qmt.web.app import _month_label, app

PORT = 8116    # test_copy's server is 8111, test_raspored_ui's and test_upitnik_ui's 8112, test_nav's 8113, test_programs' 8114, test_player's 8115


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # the karton's photos (23.11.2026) land in a throwaway dir, never the
    # real data/uploads, and never a real R2 bucket: a developer's .env may
    # carry live R2_* keys (as in tests/test_programs.py). The browser
    # test's server is a thread of this process, and storage reads config
    # at every call: it sees these too.
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "")
    yield


def make_user(email: str, is_trainer: bool = False,
              plans: tuple[str, ...] = ("online",), complete: bool = True) -> int:
    from datetime import date

    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    if complete:  # incomplete profiles bounce login to /profil
        db.update_profile(u.id, email.split("@")[0], "Test", date(1990, 1, 1), "")
    if is_trainer:
        with db.session_scope() as s:
            s.get(User, u.id).is_trainer = True
    for plan in plans:
        db.record_payment(u.id, plan)
    return u.id


def client_for(email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"email": email, "password": "lozinka123"},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/", "login failed"
    return c


def bare(html: str) -> str:
    """A page with its texts' spans unwrapped: since 25.11.2026 every static
    text of the karton is a copy slot, printed in a span (a member's
    span.t, the editor's span.ed.t with its key and label); unwrapped, the
    markup around a text reads as it did, so an assertion about it keeps
    its meaning. tests/test_copy.py proves the spans themselves."""
    return re.sub(r'<span class="(?:ed )?t"[^>]*>(.*?)</span>', r"\1", html, flags=re.S)


def karton_only(page: str) -> str:
    """A staff member's own karton without the editor's panel "Svi tekstovi
    kartona" (25.11.2026: every karton text, those only a member or the
    trainer's view shows among them, at the bottom of his page, in edit mode
    only): what the page itself shows him."""
    return page.split('<section class="card k-texts"')[0]


def seed_questions() -> None:
    """The upitnik's questions: the gym owner's fifteen, as the migration
    makes them (copy.UPITNIK_DEFAULT_QUESTIONS)."""
    for question in copy.UPITNIK_DEFAULT_QUESTIONS:
        db.add_upitnik_question(None, question)


def filled_upitnik() -> dict[str, str]:
    """A whole upitnik (version 2) as the form posts it, to the fifteen
    (seed_questions): each choice's first option, every scale at 2 (the
    score 2.0: početna; no pain to ask about), no injuries, the consent
    ticked."""
    form = {f"q{q['id']}": q["options"][0] for q in copy.UPITNIK_DEFAULT_QUESTIONS if q["kind"] == "choice"}
    form.update({f"q{q['id']}": "2" for q in copy.UPITNIK_DEFAULT_QUESTIONS if q["kind"] == "scale"})
    form.update({"q15": "ne", "consent": "da"})
    return form


# ---------- karton access ----------

def test_karton_self_other_and_trainer():
    ivan = make_user("ivan@test.local")
    make_user("ana@test.local")
    make_user("trener@test.local", is_trainer=True)

    ci = client_for("ivan@test.local")
    assert ci.get("/karton").status_code == 200
    # the /karton/{id} route is trainer-only — even for one's own id
    assert ci.get(f"/karton/{ivan}").status_code == 403
    ca = client_for("ana@test.local")
    assert ca.get(f"/karton/{ivan}").status_code == 403

    ct = client_for("trener@test.local")
    assert ct.get(f"/karton/{ivan}").status_code == 200
    # since 24.11.2026 the trainer has a karton of his own (until then: bounced to članarine)
    r = ct.get("/karton", follow_redirects=False)
    assert r.status_code == 200 and "<h1>Moj karton</h1>" in bare(r.text)


def test_staff_have_a_karton_of_their_own():
    """Since 24.11.2026 (the owner: "Lets show the Karton tab in the Admin
    view as well so that Amir can check out the changes we made there")
    /karton is staff's own as a member's: the trainer's, and the owner's
    who does not train. Neither has the upitnik card (staff never fill it)
    nor "Nadolazeći termini" (they book none), and the empty diary says
    "Još nema treninga u dnevniku." with no way to book. The rest is a
    member's: "+ Dodaj trening izvan termina" stores his training, the
    maxes count it, his weight and his limitations save, and his finished
    online pass (staff use the player) is in his diary. A client's karton,
    /karton/<id>, is as it was for him: its crumbs, its upitnik block and
    its termini; and a client's own keeps both."""
    ivan = make_user("ivan@test.local")                                       # an online plan, no upitnik yet
    amir = make_user("amir@test.local", is_trainer=True, plans=())
    make_user("trener@test.local", plans=())                                  # the owner (OWNER_EMAIL), not a trainer
    ex = library("Potisak s klupe", "Plank")
    ca, co = client_for("amir@test.local"), client_for("trener@test.local")
    for c in (ca, co):
        page = bare(karton_only(c.get("/karton").text))
        assert "<h1>Moj karton</h1>" in page
        for gone in ('<section class="upitnik', "Upitnik još nije ispunjen", "Ispuni upitnik",
                     "dio zasebne članarine", 'id="termini-h"', "Nadolazeći termini", "rezerviraj prvi"):
            assert gone not in page, gone
        assert '<p class="hint">Još nema treninga u dnevniku.</p>' in page and 'id="trening-novi"' in page
        assert 'id="masa"' in page and 'id="ogranicenja"' in page and 'id="napredak"' in page

    today = config.today()
    r = ca.post("/karton/trening", data={"effort": "6", "day": today.isoformat(), **LOG,
                                          **block(0, ex["Potisak s klupe"], (6, "90"))}, follow_redirects=False)
    [log] = db.training_logs(amir)
    assert location(r) == f"/karton?ok=Trening je spremljen.#log-{log.id}"
    assert location(ca.post("/karton/masa", data={"kg": "82,5", "day": today.isoformat()}, follow_redirects=False)) == \
        "/karton?ok=Masa je spremljena.#masa"
    ca.post("/karton/ogranicenja", data={"text": "Staro koljeno."})
    pid = db.create_program("Online", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    it = db.add_day_item(did, ex["Plank"], "trening")
    db.update_day_item(it, "trening", 3, None, 40, None, None, "")
    ca.post(f"/treninzi/{pid}/dan/{did}/kreni")
    ca.post(f"/treninzi/{pid}/dan/{did}/vjezba/1", data={"rows": "1", "item": str(it), "sec_1": "40"})
    ca.post(f"/treninzi/{pid}/dan/{did}/kraj", data={"effort": "5"})
    [done] = db.passes(amir)
    page = ca.get("/karton").text
    assert f'id="log-{log.id}"' in page and f'id="pass-{done.id}"' in page and "Još nema treninga" not in karton_only(page)
    assert sets_lines(page.split(f'id="pass-{done.id}"')[1].split('<div class="log-entry')[0]) == ["Plank: 40 s"]
    assert maxes_rows(page) == [("Potisak s klupe", "108 kg", f"90 kg × 6 · {today.strftime('%-d.%-m.%Y.')} dvorana")]
    assert '<p class="ms-val">82,5 kg</p>' in page and "Staro koljeno." in page
    assert "Nadolazeći termini" not in karton_only(page) and '<section class="upitnik' not in page

    seen = ca.get(f"/karton/{ivan}").text                                     # a client's: as before
    assert '<nav class="crumbs" aria-label="Putanja"><a href="/clanarine">Trenutne članarine</a>' in seen
    assert 'id="termini-h"' in seen and "Upitnik još nije ispunjen." in seen and 'id="trening-novi"' not in seen
    own = client_for("ivan@test.local").get("/karton").text                  # and his own
    assert 'id="termini-h"' in own and "Ispuni upitnik" in own and "rezerviraj prvi" in own


# ---------- upitnik gates online treninzi ----------

def test_programs_hidden_until_upitnik_filled():
    make_user("trener@test.local", is_trainer=True)
    make_user("ivan@test.local")                # has the online plan, no upitnik
    seed_questions()
    pid = db.create_program("Online blok A", None, "pocetna", "cijelo")

    ci = client_for("ivan@test.local")
    page = ci.get("/treninzi").text
    assert "Online blok A" not in page          # programme exists, stays hidden
    assert "Ispuni upitnik" in page
    assert ci.get(f"/treninzi/{pid}").status_code == 403   # direct URL too

    # a low score -> pocetna: the programme of that razina opens automatically (by razina alone since 23.11.2026)
    ci.post("/upitnik", data=filled_upitnik(), follow_redirects=False)
    page = ci.get("/treninzi").text
    assert "Online blok A" in page
    assert ci.get(f"/treninzi/{pid}").status_code == 200


# ---------- online tab gated on the plan ----------

def test_online_tab_gated_without_plan():
    make_user("trener@test.local", is_trainer=True, plans=())
    ivan = make_user("ivan@test.local", plans=())      # no online plan
    pid = db.create_program("Online blok B", None, "pocetna", "cijelo")

    ci = client_for("ivan@test.local")
    page = ci.get("/raspored").text
    assert "Online treninzi" not in page               # tab gone from the nav
    page = ci.get("/treninzi").text                    # direct URL: gate card
    assert "dio zasebne članarine" in page and "Online blok B" not in page
    assert ci.get(f"/treninzi/{pid}").status_code == 403
    r = ci.get("/upitnik", follow_redirects=False)     # upitnik gated too
    assert r.status_code == 303 and "error" in r.headers["location"]

    db.record_payment(ivan, "online")                  # plan paid -> tab back
    assert "Online treninzi" in ci.get("/raspored").text
    assert "Ispuni upitnik" in ci.get("/treninzi").text


# ---------- profil ----------

def test_incomplete_profile_bounces_login_then_saves():
    make_user("ivan@test.local", plans=(), complete=False)
    c = TestClient(app)
    r = c.post("/login", data={"email": "ivan@test.local", "password": "lozinka123"},
               follow_redirects=False)
    assert r.headers["location"] == "/profil?dopuni=1"

    # a half-filled form is still incomplete -> stays on the form
    r = c.post("/profil", data={"name": "Ivan", "last_name": "Horvat"},
               follow_redirects=False)
    assert r.headers["location"].startswith("/profil?ok=")

    # finishing the entry form drops them on the landing page, not back here
    r = c.post("/profil", data={"name": "Ivan", "last_name": "Horvat",
                                "birth_date": "1992-04-01", "phone": "091 111 222"},
               follow_redirects=False)
    assert r.headers["location"].startswith("/?ok=")
    u = db.get_user_by_email("ivan@test.local")
    assert u.full_name == "Ivan Horvat" and u.profile_complete
    assert u.birth_date.isoformat() == "1992-04-01"

    # a LATER edit is not the entry pass — it stays on the profile page
    r = c.post("/profil", data={"name": "Ivan", "last_name": "Horvat",
                                "birth_date": "1992-04-01", "phone": "091 222 333"},
               follow_redirects=False)
    assert r.headers["location"].startswith("/profil?ok=")

    r = c.post("/login", data={"email": "ivan@test.local", "password": "lozinka123"},
               follow_redirects=False)
    assert r.headers["location"] == "/"                # complete -> normal login

    # garbage birth date refused
    r = c.post("/profil", data={"name": "Ivan", "last_name": "Horvat",
                                "birth_date": "3000-01-01"}, follow_redirects=False)
    assert "error" in r.headers["location"]


# ---------- post-training feedback ----------

def attended_session(uid: int, hours_ago: float = 3, duration: int = 60) -> int:
    """A finished termin the user was booked into (booked directly — book()
    rightly refuses past sessions)."""
    sid = db.add_oneoff_session("Grupni trening",
                                datetime.now(config.TZ) - timedelta(hours=hours_ago),
                                duration, 8, None)
    with db.session_scope() as s:
        s.add(Booking(user_id=uid, session_id=sid))
    return sid


def test_feedback_prompted_after_attended_session():
    ivan = make_user("ivan@test.local")
    sid = attended_session(ivan)
    ci = client_for("ivan@test.local")

    assert [s.id for s in db.pending_feedback(ivan)] == [sid]
    assert "Kako je bilo?" in ci.get("/karton").text

    r = ci.post(f"/karton/feedback/{sid}",
                data={"effort": "7", "feeling": "dobro", "note": "Čučanj 3×8 · 60 kg"},
                follow_redirects=False)
    assert "ok=" in r.headers["location"]
    logs = db.training_logs(ivan)
    assert len(logs) == 1
    assert logs[0].session_id == sid and logs[0].effort == 7 and logs[0].feeling == "dobro"
    assert db.pending_feedback(ivan) == []           # prompt is gone

    # one feedback per termin
    r = ci.post(f"/karton/feedback/{sid}", data={"effort": "5"}, follow_redirects=False)
    assert "error" in r.headers["location"]
    assert len(db.training_logs(ivan)) == 1


def test_login_prompts_for_owed_feedback_once():
    ivan = make_user("ivan@test.local")
    sid = attended_session(ivan)
    ci = client_for("ivan@test.local")           # logging in arms the prompt

    first = ci.get("/").text
    assert 'id="fbPrompt"' in first              # asked on the page the login landed on
    assert "Grupni trening" in first             # and it names the termin
    assert "/karton#osvrti" in first             # primary action goes to the forms

    assert 'id="fbPrompt"' not in ci.get("/").text   # exactly once per login

    # nothing owed -> the next login says nothing
    ci.post(f"/karton/feedback/{sid}", data={"effort": "6"}, follow_redirects=False)
    assert 'id="fbPrompt"' not in client_for("ivan@test.local").get("/").text


def test_login_straight_to_karton_skips_the_prompt():
    ivan = make_user("ivan@test.local")
    attended_session(ivan)
    c = TestClient(app)
    r = c.post("/login", data={"email": "ivan@test.local", "password": "lozinka123",
                               "next": "/karton"}, follow_redirects=False)
    assert r.headers["location"] == "/karton"

    page = c.get("/karton").text
    assert 'id="fbPrompt"' not in page           # the forms are already on screen
    assert "Kako je bilo?" in page
    assert 'id="fbPrompt"' not in c.get("/").text    # and it doesn't ambush the next page


def test_feedback_needs_attended_and_finished_session():
    ivan = make_user("ivan@test.local")
    make_user("ana@test.local")
    ci = client_for("ivan@test.local")

    # still running (started 10 min ago, lasts 60) -> refused, not yet pending
    running = attended_session(ivan, hours_ago=10 / 60)
    assert db.pending_feedback(ivan) == []
    r = ci.post(f"/karton/feedback/{running}", data={"effort": "5"}, follow_redirects=False)
    assert "error" in r.headers["location"]

    # somebody else's session -> refused
    ana = db.get_user_by_email("ana@test.local").id
    theirs = attended_session(ana)
    r = ci.post(f"/karton/feedback/{theirs}", data={"effort": "5"}, follow_redirects=False)
    assert "error" in r.headers["location"]
    assert db.training_logs(ivan) == []

    # canceled session never asks for feedback
    sid = attended_session(ivan)
    db.set_session_canceled(sid, True)
    assert db.pending_feedback(ivan) == []


def test_feedback_is_editable_by_its_author_only():
    ivan = make_user("ivan@test.local")
    make_user("ana@test.local")
    sid = attended_session(ivan)
    ci = client_for("ivan@test.local")
    ci.post(f"/karton/feedback/{sid}",
            data={"effort": "7", "feeling": "dobro", "note": "Prvi zapis"},
            follow_redirects=False)
    entry = db.training_logs(ivan)[0]

    # the osvrt is readable in the dnevnik, and carries its own editor
    page = ci.get("/karton").text
    assert "Prvi zapis" in page
    assert f'id="log-{entry.id}"' in page
    assert f"/karton/log/{entry.id}/edit" in page

    r = ci.post(f"/karton/log/{entry.id}/edit",
                data={"effort": "4", "feeling": "", "note": "Ipak lakše"},
                follow_redirects=False)
    assert "ok=" in r.headers["location"]
    edited = db.training_logs(ivan)[0]
    assert (edited.effort, edited.feeling, edited.note) == (4, None, "Ipak lakše")
    assert edited.session_id == sid and edited.date == entry.date   # facts stay put

    # somebody else's osvrt, and nonsense values, are both refused
    ca = client_for("ana@test.local")
    ca.post(f"/karton/log/{entry.id}/edit", data={"effort": "9", "note": "tuđe"},
            follow_redirects=False)
    r = ci.post(f"/karton/log/{entry.id}/edit", data={"effort": "44"},
                follow_redirects=False)
    assert "error" in r.headers["location"]
    still = db.training_logs(ivan)[0]
    assert (still.effort, still.note) == (4, "Ipak lakše")


def test_absence_is_logged_without_touching_the_shared_termin():
    ivan = make_user("ivan@test.local")
    ana = make_user("ana@test.local")
    sid = attended_session(ivan)
    with db.session_scope() as s:                     # ana was in the same termin
        s.add(Booking(user_id=ana, session_id=sid))
    ci = client_for("ivan@test.local")

    # every past termin is in the dnevnik, osvrt or not
    page = ci.get("/karton").text
    assert f'action="/karton/absent/{sid}"' in page

    r = ci.post(f"/karton/absent/{sid}", follow_redirects=False)
    assert "ok=" in r.headers["location"]
    entry = db.training_logs(ivan)[0]
    assert entry.absent and entry.session_id == sid
    assert entry.effort is None and entry.feeling is None
    assert db.pending_feedback(ivan) == []            # it stops asking

    with db.session_scope() as s:                     # the termin itself is untouched
        assert not s.get(db.TrainingSession, sid).canceled
    assert [x.id for x in db.pending_feedback(ana)] == [sid]   # ana is still asked

    # one row per termin: an osvrt can't follow an absence, and vice versa
    r = ci.post(f"/karton/feedback/{sid}", data={"effort": "5"}, follow_redirects=False)
    assert "error" in r.headers["location"]
    r = ci.post(f"/karton/absent/{sid}", follow_redirects=False)
    assert "error" in r.headers["location"]
    # an absence has nothing to edit — undo it by deleting, then write the osvrt
    assert not db.update_training_log(entry.id, ivan, 5, None, "ipak sam bio")
    ci.post(f"/karton/log/{entry.id}/delete", follow_redirects=False)
    assert [x.id for x in db.pending_feedback(ivan)] == [sid]


def test_feedback_delete_own_only():
    ivan = make_user("ivan@test.local")
    make_user("ana@test.local")
    sid = attended_session(ivan)
    ci = client_for("ivan@test.local")
    ci.post(f"/karton/feedback/{sid}", data={"effort": "6"}, follow_redirects=False)
    entry = db.training_logs(ivan)[0]

    ca = client_for("ana@test.local")
    assert ca.post(f"/karton/log/{entry.id}/delete").status_code == 404
    assert len(db.training_logs(ivan)) == 1

    r = ci.post(f"/karton/log/{entry.id}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert db.training_logs(ivan) == []
    assert [s.id for s in db.pending_feedback(ivan)] == [sid]   # prompt returns


# ---------- the exercise log on a training (23.11.2026) ----------

def library(*rows) -> dict[str, int]:
    """Exercises made in the library, each a name or (name, tags): name -> id."""
    out = {}
    for row in rows:
        name, tags = (row, "") if isinstance(row, str) else row
        out[name] = db.create_exercise(name, tags=tags)
    return out


def block(n: int, exercise: int | str, *sets: tuple) -> dict[str, str]:
    """An exercise block as a karton form posts it: ex_<n> and a row per set,
    reps_<n>_<i> / kg_<n>_<i> (i from 1), each set (reps, kg) as typed."""
    form = {f"ex_{n}": str(exercise)}
    for i, (reps, kg) in enumerate(sets, start=1):
        form[f"reps_{n}_{i}"], form[f"kg_{n}_{i}"] = str(reps), str(kg)
    return form


def logged(exercise_id: int, name: str, *sets: tuple) -> dict:
    """A log's entry as db.read_log builds it: sets (reps, kg)."""
    return {"exercise_id": exercise_id, "name": name, "sets": [{"reps": r, "kg": float(k)} for r, k in sets],
            "at": datetime.now(config.TZ).isoformat(timespec="seconds")}


# what the page's script adds to a form whose exercise blocks it built: the
# routes read the blocks only with it (without the script there are none)
LOG = {"log": "1"}
HINT = "Upiši vježbe i serije — iz njih se računaju tvoji maksimumi. Sekunde (plank i slično) upiši u komentar."


def library_json(page: str) -> list:
    """The library the page carries once for the exercise log (#library-json),
    parsed; its raw text must hold no "</" (nothing can close the script)."""
    raw = page.split('<script type="application/json" id="library-json">')[1].split("</script>")[0]
    assert "</" not in raw and "<" not in raw
    return json.loads(raw)


def data_log(page: str, fid: str) -> list:
    """A form's stored exercise log as its fieldset carries it (data-log), parsed."""
    m = re.search(rf'<fieldset class="xl" data-xl="{fid}" data-log=\'([^\']*)\' hidden>', page)
    assert m, f"no fieldset {fid}"
    return json.loads(unescape(m.group(1)))


def refused(form: dict) -> str | None:
    """read_log's sentence for a form it refuses; None when it takes it."""
    try:
        db.read_log(form)
    except ValueError as err:
        return str(err)
    return None


def location(r) -> str:
    """A redirect's location as a person reads it ("+" a space)."""
    return unquote(r.headers["location"]).replace("+", " ")


def entry(page: str, log_id: int) -> str:
    """A diary row of the page, a training's (log-<id>), to the next row."""
    return page.split(f'id="log-{log_id}"')[1].split('<div class="log-entry')[0]


def read_part(row: str) -> str:
    """A row's reading half (its edit form cut off)."""
    return row.split('<form class="le-edit"')[0]


def sets_lines(chunk: str) -> list[str]:
    """The "Serije" lines of a piece of a page: "Potisak s klupe: 6 × 90 kg · …"."""
    return [unescape(re.sub(r"<[^>]+>", "", li)) for li in re.findall(r"<li><strong>.*?</li>", chunk, re.S)]


def stored(user_id: int) -> list[tuple]:
    """A client's training logs: (session, date, effort, feeling, note, [(exercise, name, sets)])."""
    return [(x.session_id, x.date, x.effort, x.feeling, x.note,
             [(e["exercise_id"], e["name"], e["sets"]) for e in x.set_items]) for x in db.training_logs(user_id)]


def test_read_log_keeps_the_blocks_with_sets_in_their_order():
    """db.read_log reads the blocks in their numbers' order (n 0, 4, 9, 10:
    numbers, not text; a gap is fine), each block's sets in theirs (i 2, 10),
    and keeps a block only when a set is typed: one with no exercise and no
    set, and one with an exercise and no set, are dropped. A set with reps
    and no weight is a bodyweight set, kg 0. The same exercise twice is two
    entries. Each entry snapshots the library's name (renamed later, the
    entry keeps it) and the moment it was logged. Fields that are no block's
    are ignored."""
    ex = library(("Potisak s klupe", "prsa, šipka"), ("Zgibovi", "leđa"), ("Goblet čučanj", "noge"))
    bench, pull, goblet = ex["Potisak s klupe"], ex["Zgibovi"], ex["Goblet čučanj"]
    form = {**block(0, bench, (6, "90"), (5, "92,5"), ("", "")),
            "ex_1": "", "reps_1_1": "", "kg_1_1": " ",                    # nothing at all: dropped
            **block(10, bench, (6, "85")),                                # after 9: numbers, not text
            **block(4, pull, (9, "")),                                    # a bodyweight set: kg 0
            "ex_9": str(goblet), "reps_9_10": "8", "kg_9_10": "20", "reps_9_2": "10", "kg_9_2": "16",
            **block(7, goblet, ("", ""), ("", "")),                       # an exercise and no set: dropped
            "effort": "7", "note": "x", "ex_x": "1", "reps_3": "5", "kg_2_1_1": "5"}
    entries = db.read_log(form)
    assert [(e["exercise_id"], e["name"], e["sets"]) for e in entries] == [
        (bench, "Potisak s klupe", [{"reps": 6, "kg": 90.0}, {"reps": 5, "kg": 92.5}]),
        (pull, "Zgibovi", [{"reps": 9, "kg": 0.0}]),
        (goblet, "Goblet čučanj", [{"reps": 10, "kg": 16.0}, {"reps": 8, "kg": 20.0}]),
        (bench, "Potisak s klupe", [{"reps": 6, "kg": 85.0}])]
    assert len({e["at"] for e in entries}) == 1 and datetime.fromisoformat(entries[0]["at"]).tzinfo is not None
    db.update_exercise(bench, "Bench press", "", "", "prsa")              # a snapshot: the name when logged
    assert entries[0]["name"] == "Potisak s klupe" and db.read_log(block(0, bench, (5, 80)))[0]["name"] == "Bench press"
    assert db.read_log({}) == [] and db.read_log({"ex_0": str(bench)}) == [] and db.read_log({"effort": "7"}) == []


def test_read_log_refuses_what_it_cannot_store():
    """Sets with no exercise ("Odaberi vježbu s popisa.", the block's select
    empty or not posted at all), an exercise that is not in the library, or
    no number ("Nepoznata vježba."), a set's number read_sets refuses
    ("Neispravan broj."), more than 20 sets in a block ("Najviše 20
    serija."; 12 until 26.11.2026, the owner: "Lets increase the 12 sets to
    20 sets limit."), more than 15 exercises ("Najviše 15 vježbi."; 15 go)."""
    ex = library("Potisak s klupe")
    bench = ex["Potisak s klupe"]
    assert refused({"ex_0": "", "reps_0_1": "8", "kg_0_1": ""}) == "Odaberi vježbu s popisa."
    assert refused({"reps_3_1": "", "kg_3_1": "20"}) == "Odaberi vježbu s popisa."
    assert refused({**block(0, bench, (5, 80)), **block(1, "", (5, 80))}) == "Odaberi vježbu s popisa."
    assert refused(block(0, bench + 1000, (8, 20))) == "Nepoznata vježba."
    assert refused(block(0, "abc", (8, 20))) == "Nepoznata vježba."
    assert refused(block(0, "1e3", (8, 20))) == "Nepoznata vježba."
    for reps, kg in (("-1", ""), ("8", "20,3"), ("8", "501"), ("1000", ""), ("osam", ""), ("8", "2.25")):
        assert refused(block(0, bench, (reps, kg))) == "Neispravan broj.", (reps, kg)
    assert refused(block(0, bench, *[(5, 20)] * 21)) == "Najviše 20 serija."
    assert len(db.read_log(block(0, bench, *[(5, 20)] * 20))[0]["sets"]) == 20
    fifteen = {k: v for n in range(15) for k, v in block(n, bench, (5, 20)).items()}
    assert len(db.read_log(fifteen)) == 15
    assert refused({**fifteen, **block(15, bench, (5, 20))}) == "Najviše 15 vježbi."
    assert len(db.read_log({**fifteen, **block(15, bench, ("", ""))})) == 15      # an empty sixteenth is dropped


def test_an_osvrt_logs_its_exercises_for_the_client_and_the_trainer():
    """"Ispuni osvrt" with two exercises: stored with the osvrt, in their
    order; the client's diary row says "2 vježbe" under the comment and
    folds their sets under "Serije" ("Potisak s klupe: 6 × 90 kg · 5 × 92,5
    kg", "Zgibovi: 9"), the trainer's view too. The form carries its
    exercise log empty and hidden (the script builds its blocks: no select,
    no row on the page), and the page the library once, as JSON in the
    alphabet's order ([id, name, tags], escaped: a name with </script> in
    it closes nothing), and the block the script clones, with no library in
    it. The trainer's view has none of it."""
    ivan = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    ex = library(("Zgibovi", "leđa"), ("Potisak s klupe", "prsa, šipka"), ("Čučanj </script><b> 'x' & \"y\"", "noge"))
    bench, pull, odd = ex["Potisak s klupe"], ex["Zgibovi"], ex["Čučanj </script><b> 'x' & \"y\""]
    sid = attended_session(ivan)
    ci = client_for("ivan@test.local")
    page = ci.get("/karton").text
    form = bare(page.split(f'action="/karton/feedback/{sid}"')[1].split("</form>")[0])
    assert (f'<fieldset class="xl" data-xl="fb-{sid}" data-log=\'[]\' hidden>' in form
            and "<legend>Vježbe (neobavezno)</legend>" in form and HINT in form
            and '<div class="xl-blocks"></div>' in form
            and '<button type="button" class="act xl-add">+ Dodaj vježbu</button>' in form)
    assert not re.search(r'name="(ex|reps|kg)_', form) and 'name="log"' not in form    # no block, no log=1
    # napor and osjećaj, and the photo's month (part 2, 23.11.2026): no select of the library
    assert {n for n in re.findall(r'<select id="[^"]+" name="([^"]+)"', page)} == {"effort", "feeling", "mjesec"}
    assert library_json(page) == [[odd, "Čučanj </script><b> 'x' & \"y\"", "noge"],
                                  [bench, "Potisak s klupe", "prsa, šipka"], [pull, "Zgibovi", "leđa"]]
    template = page.split('<template id="ex-block">')[1].split("</template>")[0]
    assert "<select" not in template and "<option" not in template and "Potisak" not in template
    assert '<input type="hidden" value="">' in template and '<p class="xb-gone" hidden></p>' in template
    assert template.count('data-f="reps"') == 3 and template.count('data-f="kg"') == 3

    r = ci.post(f"/karton/feedback/{sid}", data={"effort": "7", "feeling": "dobro", "note": "Dobar dan.", **LOG,
                                                  **block(0, bench, (6, "90"), (5, "92,5")), **block(1, pull, (9, ""))},
                follow_redirects=False)
    assert location(r) == "/karton?ok=Osvrt je spremljen."
    assert [x[5] for x in stored(ivan)] == [[(bench, "Potisak s klupe", [{"reps": 6, "kg": 90.0}, {"reps": 5, "kg": 92.5}]),
                                             (pull, "Zgibovi", [{"reps": 9, "kg": 0.0}])]]
    [log] = db.training_logs(ivan)
    assert log.exercise_count == 2 and log.lines() == [("Potisak s klupe", ["6 × 90 kg", "5 × 92,5 kg"]), ("Zgibovi", ["9"])]
    trainer = client_for("trener@test.local").get(f"/karton/{ivan}").text
    for page in (ci.get("/karton").text, trainer):
        row = bare(read_part(entry(page, log.id)))
        assert "<p>Dobar dan.</p>" in row and '<div class="hint le-sub le-ex">2 vježbe</div>' in row
        assert row.index("<p>Dobar dan.</p>") < row.index("2 vježbe") < row.index("<summary>Serije</summary>")
        assert sets_lines(row) == ["Potisak s klupe: 6 × 90 kg · 5 × 92,5 kg", "Zgibovi: 9"]
        assert "Trening izvan termina" not in row and "Grupni trening ·" in row
    assert ("<fieldset" not in trainer and 'id="library-json"' not in trainer        # he writes nothing here
            and '<template id="ex-block">' not in trainer)


def test_the_edit_carries_its_log_as_data_and_replaces_it():
    """An osvrt's edit form carries its exercises as data for the script to
    build its blocks (data-log: each exercise's id, its name as logged,
    `gone` false, its sets), not as markup: no block is rendered. Saving
    with log=1 (what the script posts) replaces the whole log: a block
    removed is gone, a set changed is changed. A termin's date stays
    whatever is posted. An exercise deleted from the library since is
    `gone` (its block: nothing picked, a line naming it); saved as the
    script would post it (no exercise, its sets) it is refused and the log
    stays. log=1 with no block empties the log, and the row then shows
    neither the count nor "Serije"."""
    ivan = make_user("ivan@test.local")
    ex = library("Potisak s klupe", "Zgibovi", "Iskorak 'stražnji' </b>")
    bench, pull, lunge = ex["Potisak s klupe"], ex["Zgibovi"], ex["Iskorak 'stražnji' </b>"]
    sid = attended_session(ivan, hours_ago=30)
    db.add_session_feedback(ivan, sid, 7, None, "Prvi.",
                            sets=[logged(bench, "Potisak s klupe", (6, 90), (5, 92.5)), logged(pull, "Zgibovi", (9, 0))])
    [log] = db.training_logs(ivan)
    ci = client_for("ivan@test.local")
    page = ci.get("/karton").text
    assert data_log(page, f"ed-{log.id}") == [
        {"exercise_id": bench, "name": "Potisak s klupe", "gone": False, "sets": [{"reps": 6, "kg": 90.0}, {"reps": 5, "kg": 92.5}]},
        {"exercise_id": pull, "name": "Zgibovi", "gone": False, "sets": [{"reps": 9, "kg": 0.0}]}]
    form = page.split(f'action="/karton/log/{log.id}/edit"')[1].split("</form>")[0]
    assert not re.search(r'name="(ex|reps|kg)_', form) and 'name="day"' not in form   # no block; a termin's date is a fact

    r = ci.post(f"/karton/log/{log.id}/edit", data={"effort": "8", "note": "Drugi.", "day": "2024-01-01", **LOG,
                                                     **block(1, pull, (10, ""), (8, "5"))}, follow_redirects=False)
    assert location(r) == f"/karton?ok=Osvrt je spremljen.#log-{log.id}"
    assert stored(ivan) == [(sid, log.date, 8, None, "Drugi.", [(pull, "Zgibovi", [{"reps": 10, "kg": 0.0}, {"reps": 8, "kg": 5.0}])])]

    db.update_training_log(log.id, ivan, 8, None, "Drugi.", sets=[logged(lunge, "Iskorak 'stražnji' </b>", (10, 20))])
    db.delete_exercise(lunge)
    page = ci.get("/karton").text
    assert data_log(page, f"ed-{log.id}") == [
        {"exercise_id": lunge, "name": "Iskorak 'stražnji' </b>", "gone": True, "sets": [{"reps": 10, "kg": 20.0}]}]
    r = ci.post(f"/karton/log/{log.id}/edit", data={"effort": "8", "note": "Drugi.", **LOG, **block(0, "", (10, "20"))},
                follow_redirects=False)
    assert location(r) == "/karton?error=Odaberi vježbu s popisa."
    assert stored(ivan)[0][5] == [(lunge, "Iskorak 'stražnji' </b>", [{"reps": 10, "kg": 20.0}])]    # the log stays
    row = read_part(entry(ci.get("/karton").text, log.id))
    assert sets_lines(row) == ["Iskorak 'stražnji' </b>: 10 × 20 kg"]                       # the snapshot's name
    r = ci.post(f"/karton/log/{log.id}/edit", data={"effort": "8", "note": "Drugi.", **LOG}, follow_redirects=False)
    assert "ok=" in r.headers["location"] and stored(ivan)[0][5] == []
    row = read_part(entry(ci.get("/karton").text, log.id))
    assert "le-ex" not in row and "Serije" not in row


def test_a_form_without_the_script_logs_no_exercise_and_keeps_a_log():
    """Without the page's script there is no exercise block and no log=1,
    and the routes read no block, whatever the form holds: a termin's osvrt
    and a training outside a termin are stored with no exercise (their
    blocks ignored, even one the log would refuse), and an edit changes
    napor, osjećaj and komentar and keeps the log it has (a page that could
    not show the log never empties it)."""
    ivan = make_user("ivan@test.local")
    ex = library("Potisak s klupe")
    bench = ex["Potisak s klupe"]
    sid = attended_session(ivan)
    ci = client_for("ivan@test.local")
    r = ci.post(f"/karton/feedback/{sid}", data={"effort": "6", "note": "Bez skripte.",
                                                  **block(0, bench, (8, "20")), **block(1, "", (5, "x"))},
                follow_redirects=False)
    assert location(r) == "/karton?ok=Osvrt je spremljen."
    r = ci.post("/karton/trening", data={"effort": "5", "day": config.today().isoformat(), **block(0, bench, (8, "20"))},
                follow_redirects=False)
    assert "ok=" in r.headers["location"]
    assert sorted((x[0] is None, x[5]) for x in stored(ivan)) == [(False, []), (True, [])]
    osvrt = next(x for x in db.training_logs(ivan) if x.session_id == sid)
    db.update_training_log(osvrt.id, ivan, 6, None, "Bez skripte.", sets=[logged(bench, "Potisak s klupe", (6, 90))])
    r = ci.post(f"/karton/log/{osvrt.id}/edit", data={"effort": "9", "feeling": "odlicno", "note": "Promijenjeno.",
                                                       **block(0, bench, (1, "200"))}, follow_redirects=False)
    assert location(r) == f"/karton?ok=Osvrt je spremljen.#log-{osvrt.id}"
    assert [x for x in stored(ivan) if x[0] == sid] == [
        (sid, osvrt.date, 9, "odlicno", "Promijenjeno.", [(bench, "Potisak s klupe", [{"reps": 6, "kg": 90.0}])])]


def test_a_training_outside_a_termin():
    """"+ Dodaj trening izvan termina": a form above the diary's rows (the
    date today by default, never after it, not before 2020), napor (needed),
    osjećaj, a comment and the exercises; POST /karton/trening stores a row
    with no termin on that date and comes back to it. A date in the future,
    before 2020-01-01, empty or no date stores nothing ("Neispravan
    datum."). Its row says "Trening izvan termina" where a termin's title
    would be, its exercises as any osvrt's, for the client and the trainer;
    its edit form moves its date (by the same rules) and replaces its log;
    it is deleted as any osvrt. The termin owed an osvrt is still owed."""
    ivan = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    ex = library("Potisak s klupe", "Zgibovi")
    bench, pull = ex["Potisak s klupe"], ex["Zgibovi"]
    sid = attended_session(ivan)
    ci = client_for("ivan@test.local")
    today = config.today()
    earlier = today - timedelta(days=22)
    page = ci.get("/karton").text
    new = " ".join(bare(page).split('<div class="log-new" id="trening-novi">')[1].split("</form>")[0].split())
    assert page.index('id="trening-novi"') < page.index('class="log-entry')         # above the diary's rows
    assert ('<button type="button" class="act" onclick="qmtToggleForm(\'trening-novi\')">+ Dodaj trening izvan termina'
            '</button>') in new
    assert '<form class="le-edit" method="post" action="/karton/trening">' in new
    assert (f'<input id="nt-day" type="date" name="day" value="{today.isoformat()}" '
            f'min="2020-01-01" max="{today.isoformat()}" required>') in new
    assert '<select id="nt-effort" name="effort" required>' in new
    assert '<fieldset class="xl" data-xl="nt" data-log=\'[]\' hidden>' in new

    for day in ((today + timedelta(days=1)).isoformat(), "2019-12-31", "", "23.11.2026", "2026-02-30"):
        r = ci.post("/karton/trening", data={"effort": "6", "day": day, **LOG, **block(0, bench, (8, 80))},
                    follow_redirects=False)
        assert location(r) == "/karton?error=Neispravan datum.", day
    r = ci.post("/karton/trening", data={"effort": "6", **LOG, **block(0, bench, (8, 80))}, follow_redirects=False)
    assert location(r) == "/karton?error=Neispravan datum."
    r = ci.post("/karton/trening", data={"effort": "6", "day": earlier.isoformat(), **LOG, **block(0, "", (8, 80))},
                follow_redirects=False)
    assert location(r) == "/karton?error=Odaberi vježbu s popisa."
    r = ci.post("/karton/trening", data={"effort": "11", "day": earlier.isoformat()}, follow_redirects=False)
    assert location(r) == "/karton?error=Neispravan osvrt."
    assert db.training_logs(ivan) == []

    r = ci.post("/karton/trening", data={"effort": "6", "feeling": "dobro", "note": "Sam u teretani.",
                                          "day": "2020-01-01", **LOG, **block(0, bench, (8, "80"))}, follow_redirects=False)
    [log] = db.training_logs(ivan)
    assert location(r) == f"/karton?ok=Trening je spremljen.#log-{log.id}"
    assert stored(ivan) == [(None, date(2020, 1, 1), 6, "dobro", "Sam u teretani.",
                             [(bench, "Potisak s klupe", [{"reps": 8, "kg": 80.0}])])]
    assert [x.id for x in db.pending_feedback(ivan)] == [sid]
    for page in (ci.get("/karton").text, client_for("trener@test.local").get(f"/karton/{ivan}").text):
        row = bare(read_part(entry(page, log.id)))
        assert row.index('<div class="le-kicker">Trening izvan termina</div>') < row.index('<span class="when">')
        assert '<span class="when">sri 1.1.2020.</span>' in row and "Grupni trening" not in row
        assert '<div class="hint le-sub le-ex">1 vježba</div>' in row and sets_lines(row) == ["Potisak s klupe: 8 × 80 kg"]
    edit = " ".join(entry(ci.get("/karton").text, log.id).split('<form class="le-edit"')[1].split())
    assert (f'<input id="ed-day-{log.id}" type="date" name="day" value="2020-01-01" '
            f'min="2020-01-01" max="{today.isoformat()}" required>') in edit
    assert 'data-confirm-title="Obrisati trening?"' in entry(ci.get("/karton").text, log.id)

    r = ci.post(f"/karton/log/{log.id}/edit", data={"effort": "6", "day": "2030-01-01", **LOG, **block(0, bench, (8, 80))},
                follow_redirects=False)
    assert location(r) == "/karton?error=Neispravan datum." and stored(ivan)[0][1] == date(2020, 1, 1)
    r = ci.post(f"/karton/log/{log.id}/edit", data={"effort": "5", "day": earlier.isoformat(), "note": "Pomaknut.",
                                                     **LOG, **block(0, pull, (9, ""))}, follow_redirects=False)
    assert "ok=" in r.headers["location"]
    assert stored(ivan) == [(None, earlier, 5, None, "Pomaknut.", [(pull, "Zgibovi", [{"reps": 9, "kg": 0.0}])])]
    r = ci.post(f"/karton/log/{log.id}/delete", follow_redirects=False)
    assert location(r) == "/karton?ok=Zapis je obrisan." and db.training_logs(ivan) == []
    assert [x.id for x in db.pending_feedback(ivan)] == [sid]


def test_a_refused_log_stores_nothing():
    """A refusal comes back to the karton with its sentence and stores
    nothing, the osvrt's fields included: sets with no exercise, an
    exercise not in the library, a bad number; the termin is still owed its
    osvrt. Refused on an edit, the osvrt stays as it was."""
    ivan = make_user("ivan@test.local")
    ex = library("Potisak s klupe")
    bench = ex["Potisak s klupe"]
    sid = attended_session(ivan)
    ci = client_for("ivan@test.local")
    for form, sentence in ((block(0, "", (8, "20")), "Odaberi vježbu s popisa."),
                           (block(0, bench + 99, (8, "20")), "Nepoznata vježba."),
                           (block(0, bench, (8, "20,25")), "Neispravan broj.")):
        r = ci.post(f"/karton/feedback/{sid}", data={"effort": "7", "note": "Ne sprema se.", **LOG, **form},
                    follow_redirects=False)
        assert location(r) == f"/karton?error={sentence}"
    assert db.training_logs(ivan) == [] and [x.id for x in db.pending_feedback(ivan)] == [sid]
    ci.post(f"/karton/feedback/{sid}", data={"effort": "7", "note": "Prvi.", **LOG, **block(0, bench, (8, "20"))})
    [log] = db.training_logs(ivan)
    before = stored(ivan)
    r = ci.post(f"/karton/log/{log.id}/edit", data={"effort": "3", "note": "Drugi.", **LOG, **block(0, bench, (8, "x"))},
                follow_redirects=False)
    assert location(r) == "/karton?error=Neispravan broj." and stored(ivan) == before


# ---------- the estimated maxes (23.11.2026) ----------

def test_epley_and_the_half_kilo():
    """Epley's formula, kg × (1 + reps / 30), worked exactly: 90 × 6 = 108;
    a single is its weight, 100 × 1 = 100 (the formula is for two reps or
    more). The value shown is to the nearest 0.5 kg, a quarter rounded up:
    40 × 8 = 50,67 → 50,5; 22,5 × 9 = 29,25 → 29,5; 20 × 10 = 26,67 → 26,5;
    10 × 10 = 13,33 → 13,5."""
    for kg, reps, exact, shown in ((90, 6, 108, 108.0), (100, 1, 100, 100.0), (40, 8, 50.666, 50.5),
                                   (22.5, 9, 29.25, 29.5), (20, 10, 26.666, 26.5), (10, 10, 13.333, 13.5),
                                   (40, 12, 56, 56.0), (100, 2, 106.666, 106.5)):
        assert abs(float(db.epley(kg, reps)) - exact) < 0.001, (kg, reps)
        assert db._to_half(db.epley(kg, reps)) == shown, (kg, reps)


def online_pass(uid: int, exercises: dict[str, int], days_ago: int) -> int:
    """A finished online pass of uid's, `days_ago` days back: its day holds
    Goblet čučanj (swapped for Prednji čučanj, one of its swaps: 8 × 30 kg
    saved under the swap), Čučanj (15 reps, no weight) and Plank (60 s).
    Its id."""
    pid = db.create_program("Online", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    goblet, squat, plank = (db.add_day_item(did, exercises[n], "trening") for n in ("Goblet čučanj", "Čučanj", "Plank"))
    db.update_exercise(exercises["Goblet čučanj"], "Goblet čučanj", "", "", "", {exercises["Prednji čučanj"]})
    log = db.start_pass(uid, db.get_program(pid), db.get_day(did))
    db.swap_exercise(log.id, uid, db.get_day_item(goblet), exercises["Prednji čučanj"])
    db.save_sets(log.id, uid, db.get_day_item(goblet), [{"reps": 8, "kg": 30.0}], db.exercise(exercises["Prednji čučanj"]))
    db.save_sets(log.id, uid, db.get_day_item(squat), [{"reps": 15, "kg": 0.0}], db.exercise(exercises["Čučanj"]))
    db.save_sets(log.id, uid, db.get_day_item(plank), [{"seconds": 60}], db.exercise(exercises["Plank"]))
    db.finish_pass(log.id, uid, 6, None, "")
    with db.engine.begin() as conn:
        conn.execute(sa_text("UPDATE workout_logs SET started_at = started_at - make_interval(days => :d), "
                             "finished_at = finished_at - make_interval(days => :d) WHERE id = :i"),
                     {"d": days_ago, "i": log.id})
    return log.id


def test_estimated_maxes_best_set_per_exercise_gym_and_online():
    """db.estimated_maxes over a client's gym logs and finished online
    passes, set by set: the best one-rep max per exercise (Epley; a single
    its weight), on a tie the later day; a weight with more than 12 reps is
    not counted (Potisak's 80 × 15 would be 120), nor a timed set (Plank),
    nor a pass in progress (Potisak's 200 × 5), nor another client's sets;
    an exercise with only such sets has no max (Veslanje). A set with no
    weight is a bodyweight record, the most reps (Zgibovi: 11), kept only
    for an exercise with no one-rep max (Sklek's 10 × 10 kg beats its 20
    bodyweight reps). An online entry counts under the exercise done: the
    swapped one (Prednji čučanj), never the planned one (Goblet čučanj keeps
    its gym max). Named as the library names the exercise now (renamed:
    the new name), or, deleted, as it was logged; in the alphabet's order
    (Čučanj between Biceps and Dizanje, not after Zgibovi)."""
    ivan = make_user("ivan@test.local")
    ana = make_user("ana@test.local")
    ex = library("Potisak s klupe", "Rameni potisak", "Zgibovi", "Sklek", "Veslanje", "Goblet čučanj", "Prednji čučanj",
                 "Plank", "Biceps pregib", "Čučanj", "Dizanje na prste", "Mrtvo dizanje")
    assert db.estimated_maxes(ivan) == []
    today = config.today()
    db.add_training_log(ivan, today - timedelta(days=10), 6, "", sets=[
        logged(ex["Potisak s klupe"], "Potisak s klupe", (6, 90), (1, 100), (15, 80)),
        logged(ex["Rameni potisak"], "Rameni potisak", (8, 40)),
        logged(ex["Zgibovi"], "Zgibovi", (9, 0)),
        logged(ex["Sklek"], "Sklek", (20, 0)),
        logged(ex["Veslanje"], "Veslanje", (15, 30)),
        logged(ex["Goblet čučanj"], "Goblet čučanj", (10, 20)),
        logged(ex["Mrtvo dizanje"], "Mrtvo dizanje", (1, 100), (0, 120))])
    sid = attended_session(ivan, hours_ago=3 * 24)
    db.add_session_feedback(ivan, sid, 7, None, "", sets=[
        logged(ex["Rameni potisak"], "Rameni potisak", (8, 40)),                       # a tie: the later day wins
        logged(ex["Zgibovi"], "Zgibovi", (7, 0), (11, 0)),
        logged(ex["Sklek"], "Sklek", (10, 10)),
        logged(ex["Biceps pregib"], "Biceps pregib", (9, 22.5)),
        logged(ex["Dizanje na prste"], "Dizanje na prste", (12, 40))])
    termin_day = db.training_logs(ivan)[0].date
    pass_id = online_pass(ivan, ex, days_ago=5)
    pass_day = db.get_pass(pass_id, ivan).date
    pid = db.create_program("Snaga", None, "pocetna", "cijelo")                         # a pass in progress: not counted
    did = db.add_day(pid)
    it = db.add_day_item(did, ex["Potisak s klupe"], "trening")
    open_one = db.start_pass(ivan, db.get_program(pid), db.get_day(did))
    db.save_sets(open_one.id, ivan, db.get_day_item(it), [{"reps": 5, "kg": 200.0}], db.exercise(ex["Potisak s klupe"]))
    db.add_training_log(ana, today, 9, "", sets=[logged(ex["Potisak s klupe"], "Potisak s klupe", (5, 150))])
    db.update_exercise(ex["Rameni potisak"], "Rameni potisak s bučicama", "", "", "")
    db.delete_exercise(ex["Biceps pregib"])

    got = [(m.name, m.kind, m.value, m.reps, m.kg, m.on, m.source) for m in db.estimated_maxes(ivan)]
    assert got == [
        ("Biceps pregib", "1rm", 29.5, 9, 22.5, termin_day, "gym"),
        ("Čučanj", "reps", 15, 15, 0.0, pass_day, "online"),
        ("Dizanje na prste", "1rm", 56.0, 12, 40.0, termin_day, "gym"),
        ("Goblet čučanj", "1rm", 26.5, 10, 20.0, today - timedelta(days=10), "gym"),
        ("Mrtvo dizanje", "1rm", 100.0, 1, 100.0, today - timedelta(days=10), "gym"),
        ("Potisak s klupe", "1rm", 108.0, 6, 90.0, today - timedelta(days=10), "gym"),
        ("Prednji čučanj", "1rm", 38.0, 8, 30.0, pass_day, "online"),
        ("Rameni potisak s bučicama", "1rm", 50.5, 8, 40.0, termin_day, "gym"),
        ("Sklek", "1rm", 13.5, 10, 10.0, termin_day, "gym"),
        ("Zgibovi", "reps", 11, 11, 0.0, termin_day, "gym")]
    words = {m.name: (m.value_text, m.set_text, m.source_text) for m in db.estimated_maxes(ivan)}
    assert words["Potisak s klupe"] == ("108 kg", "90 kg × 6", "dvorana")
    assert words["Rameni potisak s bučicama"] == ("50,5 kg", "40 kg × 8", "dvorana")
    assert words["Biceps pregib"] == ("29,5 kg", "22,5 kg × 9", "dvorana")
    assert words["Zgibovi"] == ("11 ponavljanja", "11 ponavljanja", "dvorana")
    assert words["Čučanj"] == ("15 ponavljanja", "15 ponavljanja", "online")
    assert [m.name for m in db.estimated_maxes(ana)] == ["Potisak s klupe"]


def test_the_maxes_never_count_a_set_that_holds_seconds():
    """Since 24.11.2026 an online exercise may ask for reps and seconds
    (the plank's "3 × 5 × 30 s"), its sets saved {"reps": 5, "seconds":
    30}: such a set is no bodyweight record of 5 reps (nor of 8), as a
    timed {"seconds": 60} never was; another exercise's reps with no weight
    in the same pass still are. The karton's table says only that."""
    ivan = make_user("ivan@test.local")
    ex = library("Bočni plank", "Sklek")
    pid = db.create_program("Online", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    plank, push = (db.add_day_item(did, ex[n], "trening") for n in ("Bočni plank", "Sklek"))
    db.update_day_item(plank, "trening", 3, 5, 30, None, None, "")
    log = db.start_pass(ivan, db.get_program(pid), db.get_day(did))
    db.save_sets(log.id, ivan, db.get_day_item(plank), [{"reps": 5, "seconds": 30}, {"reps": 8, "seconds": 20}],
                 db.exercise(ex["Bočni plank"]))
    db.save_sets(log.id, ivan, db.get_day_item(push), [{"reps": 12, "kg": 0.0}], db.exercise(ex["Sklek"]))
    db.finish_pass(log.id, ivan, 6, None, "")
    assert [(m.name, m.kind, m.value) for m in db.estimated_maxes(ivan)] == [("Sklek", "reps", 12)]
    page = client_for("ivan@test.local").get("/karton").text
    assert maxes_rows(page) == [("Sklek", "12 ponavljanja", f"{config.today().strftime('%-d.%-m.%Y.')} online")]


def maxes_section(page: str) -> str:
    return page.split('<section class="card maxes" aria-labelledby="maxes-h">')[1].split("</section>")[0]


def maxes_rows(page: str) -> list[tuple[str, str, str]]:
    """The maxes table's rows as a reader reads them: (Vježba, Procjena, Iz)
    (since 25.11.2026 each name a link to its history, read through)."""
    rows = re.findall(r'<tr>\s*<th scope="row">(.*?)</th>\s*<td class="mx-val">([^<]*)</td>\s*<td>(.*?)</td>\s*</tr>',
                      maxes_section(page), re.S)
    return [(unescape(re.sub(r"<[^>]+>", "", a)), unescape(b), unescape(re.sub(r"<[^>]+>", "", c))) for a, b, c in rows]


def test_the_karton_shows_the_maxes_to_the_client_and_the_trainer():
    """"Procijenjeni maksimumi", a card between the upitnik block and the
    diary, for the client and the trainer alike: the hint (the formula, to
    12 reps, the bodyweight rule), then Vježba · Procjena · Iz ("90 kg × 6 ·
    12.11.2026. dvorana"; a bodyweight row's reps are its estimate, its Iz
    the date and the source alone, "12.11.2026. dvorana"). With no set logged:
    the hint and "Još nema serija — upiši vježbe uz osvrt treninga." (the
    client), "Još nema serija." (the trainer)."""
    ivan = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    ex = library("Potisak s klupe", "Zgibovi")
    ci, ct = client_for("ivan@test.local"), client_for("trener@test.local")
    hint = ('<p class="hint mx-hint">Iz najbolje serije svake vježbe, Epleyevom formulom (kg × (1 + ponavljanja / 30)), '
            'do 12 ponavljanja. Vježbe bez utega: najviše ponavljanja.</p>')
    for page, empty in ((ci.get("/karton").text, "Još nema serija — upiši vježbe uz osvrt treninga."),
                        (ct.get(f"/karton/{ivan}").text, "Još nema serija.")):
        section = bare(maxes_section(page))
        assert '<h2 id="maxes-h">Procijenjeni maksimumi</h2>' in section and hint in section
        assert f'<p class="mx-empty">{empty}</p>' in section and "<table>" not in section
        assert page.index('<section class="upitnik') < page.index('class="card maxes"') < page.index('<h2 id="osvrti">')
    day = date(2026, 11, 12)
    db.add_training_log(ivan, day, 7, "", sets=[logged(ex["Zgibovi"], "Zgibovi", (9, 0)),
                                                logged(ex["Potisak s klupe"], "Potisak s klupe", (6, 90), (8, 80))])
    expected = [("Potisak s klupe", "108 kg", "90 kg × 6 · 12.11.2026. dvorana"),
                ("Zgibovi", "9 ponavljanja", "12.11.2026. dvorana")]
    for page in (ci.get("/karton").text, ct.get(f"/karton/{ivan}").text):
        assert maxes_rows(page) == expected
        section = bare(maxes_section(page))
        assert ('<thead><tr><th scope="col">Vježba</th><th scope="col">Procjena</th><th scope="col">Iz</th></tr></thead>'
                in section and "mx-empty" not in section)


# ---------- the karton, part 2: height, weight, limitations, photos (23.11.2026) ----------

def short(d: date) -> str:
    """A day as the head line says it: "12.11.", "12.11.2025." in another year."""
    return f"{d.day}.{d.month}." + (f"{d.year}." if d.year != config.today().year else "")


def full(d: date) -> str:
    """A day as the weight card says it: "12.11.2026."."""
    return d.strftime("%-d.%-m.%Y.")


def age_of(born: date) -> int:
    today = config.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def text_of(chunk: str) -> str:
    """A piece of a page as a reader reads it: tags gone, spaces collapsed."""
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", chunk)).split())


def head_line(page: str) -> str:
    """The lead under the karton's h1, as read."""
    return text_of(page.split("</h1>")[1].split("</p>")[0])


def card(page: str, cls: str) -> str:
    """One of part 2's cards, its texts' spans unwrapped (bare): "card masa"
    (the rail's, "masa", until 25.11.2026), "card limits", "card photos"."""
    return bare(page.split(f'<section class="{cls}"')[1].split("</section>")[0])


def weight_list(chunk: str) -> list[str]:
    """The weight rows of a piece of a page: "12.11.2026. · 82,5 kg"."""
    return [unescape(x) for x in re.findall(r"<li><span>([^<]*)</span>", chunk)]


def picture(w: int, h: int, fmt: str = "JPEG", orientation: int | None = None, mode: str = "RGB") -> bytes:
    """A real image, made here (Pillow has to open what is posted): a JPEG
    carries EXIF, a camera's make and, when given, the orientation a phone
    stores instead of turning the pixels (test_copy's)."""
    im, buf, extra = Image.new(mode, (w, h), (180, 60, 40, 128)[:len(mode)]), io.BytesIO(), {}
    if fmt == "JPEG":
        exif = Image.Exif()
        exif[0x010F] = "QMT testna kamera"                                 # Make
        if orientation:
            exif[0x0112] = orientation                                      # Orientation
        extra["exif"] = exif.tobytes()
    im.save(buf, fmt, **extra)
    return buf.getvalue()


def stored_files() -> list[str]:
    return sorted(p.name for p in config.MEDIA_DIR.iterdir()) if config.MEDIA_DIR.exists() else []


def test_the_height_is_the_kartons_and_heads_it():
    """The height on the karton's "Tjelesna kompozicija" since 26.11.2026
    (the owner's note: "visinu maknut iz profila u karton"; a /profil field
    from 23.11.2026): on one's own karton, a member's and a staff member's,
    "Visina 178 cm" with a quiet "uredi" (with none, "Visina nije upisana"
    and "upiši") that opens its form, one field "Visina (cm)" (whole
    centimetres, 100–250, a number input) and Spremi / Odustani → POST
    /karton/visina: saved ("Visina je spremljena.", back at #masa); 99,
    251, "178,5", "178.5", "abc" and "-178" refused ("Neispravna
    visina."), nothing changed; empty clears it. The karton's head line
    says it, "Visina 178 cm" (the member's on its own line under the
    lead, the trainer's after the age), and the trainer's card reads it,
    no form; with no height neither line has it. /profil has no height
    any more: its field is gone, and a save that still posts one (an old
    page) keeps the stored height as it is, as does every profile save.
    The trainer's own karton has his own height form; a guest goes to
    log in."""
    ivan = make_user("ivan@test.local")
    trener = make_user("trener@test.local", is_trainer=True)
    ci, ct = client_for("ivan@test.local"), client_for("trener@test.local")
    profil = ci.get("/profil").text
    assert 'name="height"' not in profil and "p-height" not in profil and "Visina" not in profil
    page = ci.get("/karton").text
    masa = card(page, "card masa")
    assert ('<p class="hint ms-height">Visina nije upisana\n      <button type="button" class="act act-quiet" '
            "onclick=\"qmtToggleForm('visina')\">upiši</button></p>") in masa
    form = masa.split('<div class="ms-hgt" id="visina">')[1].split("</form>")[0]
    assert '<form class="le-edit" method="post" action="/karton/visina">' in form
    assert re.search(r'<label for="ms-height">Visina \(cm\)</label>\s*<input id="ms-height" type="number" name="visina" '
                     r'value=""\s+min="100" max="250" step="1" inputmode="numeric">', form)
    assert ">Spremi</button>" in form and "qmtToggleForm('visina')\">Odustani</button>" in form
    r = ci.post("/karton/visina", data={"visina": " 178 "}, follow_redirects=False)
    assert location(r) == "/karton?ok=Visina je spremljena.#masa" and db.get_user(ivan).height_cm == 178
    for bad in ("99", "251", "178,5", "178.5", "abc", "-178"):
        r = ci.post("/karton/visina", data={"visina": bad}, follow_redirects=False)
        assert location(r) == "/karton?error=Neispravna visina.#masa" and db.get_user(ivan).height_cm == 178, bad
    with pytest.raises(ValueError, match="Neispravna visina."):
        db.set_height(ivan, 300)
    page, seen = ci.get("/karton").text, ct.get(f"/karton/{ivan}").text
    assert head_line(page) == "Dnevnik treninga, upitnik i termini na jednom mjestu. Visina 178 cm"
    assert '<span class="k-body">Visina 178 cm</span>' in page
    assert head_line(seen) == f"ivan@test.local · {age_of(date(1990, 1, 1))} god. · Visina 178 cm"
    assert ('<p class="hint ms-height">Visina 178 cm\n      <button type="button" class="act act-quiet" '
            "onclick=\"qmtToggleForm('visina')\">uredi</button></p>") in card(page, "card masa")
    assert 'value="178"' in card(page, "card masa").split('id="visina"')[1].split("</form>")[0]
    masa = card(seen, "card masa")                                                    # the trainer reads it
    assert '<p class="hint ms-height">Visina 178 cm</p>' in masa and "visina" not in masa and "<form" not in masa
    old = {"name": "ivan", "last_name": "Test", "birth_date": "1990-01-01", "phone": ""}
    for height in ("", "190", "abc"):                                                 # /profil keeps it
        r = ci.post("/profil", data={**old, "height": height}, follow_redirects=False)
        assert location(r) == "/profil?ok=Podaci su spremljeni." and db.get_user(ivan).height_cm == 178, height
    r = ci.post("/karton/visina", data={"visina": ""}, follow_redirects=False)        # emptied: none
    assert location(r) == "/karton?ok=Visina je spremljena.#masa" and db.get_user(ivan).height_cm is None
    page, seen = ci.get("/karton").text, ct.get(f"/karton/{ivan}").text
    assert head_line(page) == "Dnevnik treninga, upitnik i termini na jednom mjestu." and '<span class="k-body">' not in page
    assert "Visina" not in head_line(seen) and "ms-height" not in card(seen, "card masa")
    assert "Visina nije upisana" in card(page, "card masa")
    own = card(karton_only(ct.get("/karton").text), "card masa")                       # staff's own karton: his form
    assert 'action="/karton/visina"' in own
    r = ct.post("/karton/visina", data={"visina": "185"}, follow_redirects=False)
    assert location(r) == "/karton?ok=Visina je spremljena.#masa"
    assert db.get_user(trener).height_cm == 185 and db.get_user(ivan).height_cm is None
    r = TestClient(app).post("/karton/visina", data={"visina": "180"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert "BMI" not in page and "ITM" not in page                                       # not asked


def test_read_weight_takes_a_comma_or_a_point_in_tenths_from_20_to_300():
    """db.read_weight: "82,5" and "82.5" alike, whole kilos too, in steps of
    0.1 within 20–300 (an exact Decimal); anything else "Neispravna masa."."""
    for raw, kg in (("82,5", "82.5"), ("82.5", "82.5"), (" 82 ", "82.0"), ("20", "20.0"), ("300", "300.0"),
                    ("82,50", "82.5"), ("19,9", None), ("300.1", None), ("82,55", None), ("", None), ("abc", None),
                    ("-80", None), ("1e2", None), ("82,", None), (",5", None), ("８２", None), ("82.5.1", None)):
        if kg is None:
            with pytest.raises(ValueError, match="Neispravna masa."):
                db.read_weight(raw)
        else:
            assert db.read_weight(raw) == Decimal(kg), raw


def test_a_weight_a_day_upserted_shown_and_deleted_own_only():
    """POST /karton/masa (the weight card's form): a weight and its day; a
    refusal ("Neispravna masa.", "Neispravan datum." for a day in the future,
    before 2020 or none) stores nothing. A second save on a day replaces the
    first: one row a day. The card: the newest day's value big and its date,
    the history newest first ("12.11.2026. · 82,5 kg"), each row's ✕ asking
    first; the head line "Masa 82,5 kg (12.11.)" (with the height, "Visina
    178 cm · Masa …"); none yet: "Još nije upisana.". The ✕ deletes the
    member's own rows only: another member's id, and one gone, are 404."""
    ivan = make_user("ivan@test.local")
    ana = make_user("ana@test.local")
    make_user("trener@test.local", is_trainer=True)
    ci, ct = client_for("ivan@test.local"), client_for("trener@test.local")
    page = ci.get("/karton").text
    assert '<p class="kc-empty">Još nije upisana.</p>' in card(page, "card masa") and "ms-list" not in card(page, "card masa")
    assert "Masa" not in head_line(page) and "Masa" not in head_line(ct.get(f"/karton/{ivan}").text)
    today = config.today()
    older, newer = today - timedelta(days=9), today - timedelta(days=2)
    for kg, day, error in (("19,9", newer, "Neispravna masa."), ("abc", newer, "Neispravna masa."),
                           ("80", today + timedelta(days=1), "Neispravan datum."),
                           ("80", date(2019, 12, 31), "Neispravan datum."), ("80", None, "Neispravan datum.")):
        r = ci.post("/karton/masa", data={"kg": kg, "day": day.isoformat() if day else ""}, follow_redirects=False)
        assert location(r) == f"/karton?error={error}#masa", (kg, day)
    assert db.weights(ivan) == []
    for kg, day in (("84", older), ("83.0", newer), ("82,5", newer)):                       # the second save that day replaces
        r = ci.post("/karton/masa", data={"kg": kg, "day": day.isoformat()}, follow_redirects=False)
        assert location(r) == "/karton?ok=Masa je spremljena.#masa"
    db.set_weight(ana, newer, Decimal("61"))
    assert [(w.measured_on, w.kg) for w in db.weights(ivan)] == [(newer, Decimal("82.5")), (older, Decimal("84.0"))]
    page, seen = ci.get("/karton").text, ct.get(f"/karton/{ivan}").text
    for p in (page, seen):
        masa = card(p, "card masa")          # a card of the column since 25.11.2026: its lines two spaces in
        assert f'<p class="ms-val">82,5 kg</p>\n  <p class="hint ms-date">{full(newer)}</p>' in masa
        assert weight_list(masa) == [f"{full(newer)} · 82,5 kg", f"{full(older)} · 84 kg"]
        assert "prikaži sve" not in masa and "Povijest" not in masa
    assert head_line(page).endswith(f"mjestu. Masa 82,5 kg ({short(newer)})")
    assert head_line(seen) == f"ivan@test.local · {age_of(date(1990, 1, 1))} god. · Masa 82,5 kg ({short(newer)})"
    newest = db.weights(ivan)[0]
    assert (f'<form method="post" action="/karton/masa/{newest.id}/obrisi"\n          data-confirm-title="Obrisati unos?"\n'
            f'          data-confirm="Unos 82,5 kg od {full(newer)} bit će trajno obrisan."\n          data-confirm-cta="Obriši unos">\n'
            f'      <button type="submit" class="k-x" aria-label="Obriši unos {full(newer)}">✕</button>') in card(page, "card masa")
    masa = card(seen, "card masa")                                                              # the trainer reads
    assert "<form" not in masa and "k-x" not in masa and "Upiši" not in masa
    assert '<button type="button" class="act" onclick="qmtToggleForm(\'masa\')">Upiši</button>' in card(page, "card masa")
    db.update_profile(ivan, "ivan", "Test", date(1990, 1, 1), "", height_cm=178)
    assert head_line(ci.get("/karton").text).endswith(f"mjestu. Visina 178 cm · Masa 82,5 kg ({short(newer)})")
    theirs = db.weights(ana)[0].id
    assert ci.post(f"/karton/masa/{theirs}/obrisi", follow_redirects=False).status_code == 404   # not his
    assert [w.id for w in db.weights(ana)] == [theirs]
    r = ci.post(f"/karton/masa/{newest.id}/obrisi", follow_redirects=False)
    assert location(r) == "/karton?ok=Unos je obrisan.#masa"
    assert ci.post(f"/karton/masa/{newest.id}/obrisi", follow_redirects=False).status_code == 404   # gone
    assert [w.measured_on for w in db.weights(ivan)] == [older]
    assert head_line(ci.get("/karton").text).endswith(f"Masa 84 kg ({short(older)})")
    assert TestClient(app).post("/karton/masa", data={"kg": "80", "day": today.isoformat()},
                                follow_redirects=False).headers["location"] == "/login"


def test_the_weight_history_shows_twelve_then_folds_the_rest():
    """Fourteen days of weights: the member's card lists the newest twelve,
    each with its ✕, and the two oldest under "prikaži sve"; the trainer's
    view reads the same card with no form and no ✕, the whole history
    folded under "Povijest", fourteen rows. With twelve he gets the list."""
    ivan = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    ci, ct = client_for("ivan@test.local"), client_for("trener@test.local")
    today = config.today()
    days = [today - timedelta(days=3 * k) for k in range(14)]                             # newest first
    for k, day in enumerate(days):
        db.set_weight(ivan, day, Decimal(80) + Decimal(k) / 10)
    rows = [f"{full(d)} · {str(Decimal(80) + Decimal(k) / 10).replace('.', ',')} kg" for k, d in enumerate(days)]
    masa = card(ci.get("/karton").text, "card masa")
    shown, folded = masa.split('<details class="sets"><summary>prikaži sve</summary>')
    assert weight_list(shown) == rows[:12] and weight_list(folded) == rows[12:]
    assert masa.count('class="k-x"') == 14
    masa = card(ct.get(f"/karton/{ivan}").text, "card masa")
    before, history = masa.split('<details class="sets"><summary>Povijest</summary>')
    assert weight_list(before) == [] and weight_list(history) == rows and "k-x" not in masa and "prikaži sve" not in masa
    for w in db.weights(ivan)[12:]:
        db.delete_weight(w.id, ivan)
    masa = card(ct.get(f"/karton/{ivan}").text, "card masa")
    assert weight_list(masa) == rows[:12] and "<details" not in masa


def test_two_weights_saved_on_one_day_at_once_leave_one_row():
    """Six saves for one day at once (two phones, a double tap): the upsert
    on the day's unique rule leaves one row, holding one of the six."""
    ivan = make_user("ivan@test.local")
    day, values = config.today(), [Decimal(80) + k for k in range(6)]
    threads = [threading.Thread(target=db.set_weight, args=(ivan, day, kg)) for kg in values]
    for th in threads: th.start()
    for th in threads: th.join()
    rows = db.weights(ivan)
    assert len(rows) == 1 and rows[0].measured_on == day and rows[0].kg in values


def test_the_limitations_are_the_members_text_and_the_trainers_flag():
    """POST /karton/ogranicenja: the member's text cleaned as copy is
    (spaces collapsed, three empty lines one, the ends trimmed), shown as
    saved under "Ograničenja i bolovi" (its line breaks, pre-line), a card
    between the upitnik block and the photos, which come before the maxes;
    2001 characters refused ("Najviše 2000 znakova."), nothing changed;
    emptied, "Nema upisanih ograničenja.". The member has Uredi and the
    textarea (the text in it); the trainer reads it, the amber "Ograničenja"
    chip in the card's head while it holds anything."""
    ivan = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    ci, ct = client_for("ivan@test.local"), client_for("trener@test.local")
    empty = '<p class="kc-empty">Nema upisanih ograničenja.</p>'
    page, seen = ci.get("/karton").text, ct.get(f"/karton/{ivan}").text
    assert empty in card(page, "card limits") and empty in card(seen, "card limits")
    assert "u-flag" not in card(seen, "card limits")
    assert (page.index('<section class="upitnik') < page.index('<section class="card limits"')
            < page.index('<section class="card photos"') < page.index('<section class="card maxes"'))
    r = ci.post("/karton/ogranicenja", data={"text": "  Bol u   koljenu.\r\n\r\n\r\n\r\nOzljeda ramena 2023.  \n\n"},
                follow_redirects=False)
    assert location(r) == "/karton?ok=Ograničenja su spremljena.#ogranicenja"
    text = "Bol u koljenu.\n\nOzljeda ramena 2023."
    assert db.get_user(ivan).limitations == text
    page, seen = ci.get("/karton").text, ct.get(f"/karton/{ivan}").text
    assert f'<p class="lim-text">{text}</p>' in card(page, "card limits") and f'<p class="lim-text">{text}</p>' in card(seen, "card limits")
    assert ('<h2 id="lim-h">Ograničenja i bolovi</h2>\n    <span class="u-flag pain">Ograničenja</span>'
            in card(seen, "card limits"))
    assert "u-flag" not in card(page, "card limits")                                     # his own: no flag
    assert '<button type="button" class="act" onclick="qmtToggleForm(\'ogranicenja\')">Uredi</button>' in card(page, "card limits")
    assert (f'placeholder="npr. bol u koljenu pri čučnju, stara ozljeda ramena">{text}</textarea>' in card(page, "card limits")
            and 'maxlength="2000"' in card(page, "card limits"))
    assert "<form" not in card(seen, "card limits") and "Uredi" not in card(seen, "card limits")
    r = ci.post("/karton/ogranicenja", data={"text": "x" * 2001}, follow_redirects=False)
    assert location(r) == "/karton?error=Najviše 2000 znakova.#ogranicenja" and db.get_user(ivan).limitations == text
    assert ci.post("/karton/ogranicenja", data={"text": "y" * 2000}, follow_redirects=False).status_code == 303
    assert db.get_user(ivan).limitations == "y" * 2000
    ci.post("/karton/ogranicenja", data={"text": " \n \n "}, follow_redirects=False)        # emptied
    assert db.get_user(ivan).limitations == ""
    seen = ct.get(f"/karton/{ivan}").text
    assert empty in card(seen, "card limits") and "u-flag" not in card(seen, "card limits")
    assert TestClient(app).post("/karton/ogranicenja", data={"text": "x"}, follow_redirects=False).headers["location"] == "/login"


def test_a_monthly_photo_is_shrunk_bare_and_one_a_month():
    """POST /karton/slika: the month it is OF (the select's twelve options,
    this month first and selected, "studeni 2026.") and the file. A phone's
    JPEG (2400 × 1600, EXIF orientation 6) is stored upright, 1600 px on its
    long side, a progressive JPEG with no EXIF, as
    napredak-<id>-<YYYYMM>-<hex>.jpg; a small PNG with transparency is a
    JPEG of its size (never enlarged). One a month: a second photo for the
    month replaces the first and its file goes; another month is a photo of
    its own. Refused, nothing stored: a month outside the twelve, a file
    that is no photo or not named as one, one over 15 MB. The card: the
    thumbnails, the newest month first, each a link to /media and its month
    under it, the member's ✕ (asks first); its button "Dodaj fotografiju",
    "Zamijeni ovomjesečnu" once this month has one; empty, "Još nema
    fotografija." and the member's hint. The ✕ deletes his own (the row,
    then the file); another member's is 404."""
    ivan = make_user("ivan@test.local")
    ana = make_user("ana@test.local")
    make_user("trener@test.local", is_trainer=True)
    ci, ct = client_for("ivan@test.local"), client_for("trener@test.local")
    months = db.photo_months()
    this, last = months[0], months[1]
    assert this == config.today().replace(day=1) and len(months) == 12 and len(set(months)) == 12
    page = ci.get("/karton").text
    photos = card(page, "card photos")
    options = re.findall(r'<option value="([0-9-]+)"( selected)?>([^<]*)</option>', photos)
    assert options == [(m.strftime("%Y-%m"), " selected" if m == this else "", _month_label(m)) for m in months]
    assert _month_label(date(2026, 11, 1)) == "studeni 2026." and _month_label(date(2025, 12, 1)) == "prosinac 2025."
    assert ('<button type="button" class="act" onclick="qmtToggleForm(\'napredak\')">Dodaj fotografiju</button>' in photos
            and '<p class="kc-empty">Još nema fotografija.</p>' in photos
            and "Jedna fotografija mjesečno, kad želiš — za usporedbu kroz vrijeme." in photos)
    assert ('<input id="ph-file" type="file" name="slika" accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp" required data-focus>'
            in photos and 'enctype="multipart/form-data"' in photos)
    seen = card(ct.get(f"/karton/{ivan}").text, "card photos")
    assert "<form" not in seen and "Još nema fotografija." in seen and "za usporedbu" not in seen

    def send(month: date | str, name: str, data: bytes, kind: str = "image/jpeg"):
        value = month if isinstance(month, str) else month.strftime("%Y-%m")
        return ci.post("/karton/slika", data={"mjesec": value}, files={"slika": (name, data, kind)}, follow_redirects=False)

    unsupported = "Nepodržan format — dozvoljeno: jpg, png, webp."
    for month, name, data, error in ((this.replace(year=this.year - 1), "a.jpg", picture(30, 20), "Neispravan mjesec."),
                                     ("2026-13", "a.jpg", picture(30, 20), "Neispravan mjesec."),
                                     ("", "a.jpg", picture(30, 20), "Neispravan mjesec."),
                                     (this, "foto.txt", b"samo tekst", unsupported),
                                     (this, "foto.gif", picture(30, 20, "GIF"), unsupported),
                                     (this, "foto.jpg", picture(30, 20, "GIF"), unsupported),
                                     (this, "foto.jpg", b"ovo nije slika", unsupported),
                                     (this, "velika.jpg", b"\0" * (16 * 1024 * 1024), "Slika je veća od 15 MB.")):
        assert location(send(month, name, data)) == f"/karton?error={error}#napredak", (month, name)
    assert db.photos(ivan) == [] and stored_files() == []

    r = send(this, "IMG_0001.JPG", picture(2400, 1600, orientation=6))
    assert location(r) == "/karton?ok=Fotografija je spremljena.#napredak"
    first = db.photos(ivan)[0].image
    assert re.fullmatch(rf"napredak-{ivan}-{this:%Y%m}-[0-9a-f]{{16}}\.jpg", first) and stored_files() == [first]
    with Image.open(config.MEDIA_DIR / first) as im:
        assert im.format == "JPEG" and im.size == (1067, 1600)                          # upright, its long side 1600
        assert im.info.get("progressive") and not im.getexif() and "exif" not in im.info   # no camera, no place
    r = send(this, "druga.png", picture(300, 200, "PNG", mode="RGBA"), "image/png")    # this month again: replaces
    assert location(r) == "/karton?ok=Fotografija je spremljena.#napredak"
    second = db.photos(ivan)[0].image
    assert second != first and [p.image for p in db.photos(ivan)] == [second] and stored_files() == [second]
    with Image.open(config.MEDIA_DIR / second) as im:
        assert im.format == "JPEG" and im.mode == "RGB" and im.size == (300, 200)       # never enlarged
    r = send(last, "treca.webp", picture(800, 600, "WEBP"), "image/webp")               # another month: its own
    assert location(r) == "/karton?ok=Fotografija je spremljena.#napredak"
    assert [(p.month, p.image) for p in db.photos(ivan)] == [(this, second), (last, db.photos(ivan)[1].image)]
    third = db.photos(ivan)[1].image
    assert third.startswith(f"napredak-{ivan}-{last:%Y%m}-") and stored_files() == sorted([second, third])

    page, seen = ci.get("/karton").text, ct.get(f"/karton/{ivan}").text
    for p in (page, seen):
        rows = re.findall(r'<li class="ph">\s*<a class="ph-img" href="/media/([^"]+)" target="_blank" rel="noopener">'
                          r'<img src="/media/([^"]+)" alt="Fotografija napretka, ([^"]+)" loading="lazy" decoding="async"></a>\s*'
                          r'<p class="ph-cap">([^<]*)</p>', card(p, "card photos"))
        assert rows == [(second, second, _month_label(this), _month_label(this)),
                        (third, third, _month_label(last), _month_label(last))]
    photos = card(page, "card photos")
    assert "Zamijeni ovomjesečnu</button>" in photos and "Još nema fotografija." not in photos
    one = db.photos(ivan)[0].id
    assert (f'<form class="ph-x" method="post" action="/karton/slika/{one}/obrisi"\n'
            f'            data-confirm-title="Obrisati fotografiju?"\n'
            f'            data-confirm="Fotografija za {_month_label(this)} bit će trajno obrisana."\n'
            f'            data-confirm-cta="Obriši fotografiju">\n'
            f'        <button type="submit" class="k-x" aria-label="Obriši fotografiju za {_month_label(this)}">✕</button>') in photos
    assert "ph-x" not in card(seen, "card photos") and "<form" not in card(seen, "card photos")

    db.set_photo(ana, this, f"napredak-{ana}-{this:%Y%m}-0123456789abcdef.jpg")
    theirs = db.photos(ana)[0].id
    assert ci.post(f"/karton/slika/{theirs}/obrisi", follow_redirects=False).status_code == 404   # not his
    assert [p.id for p in db.photos(ana)] == [theirs]
    r = ci.post(f"/karton/slika/{one}/obrisi", follow_redirects=False)                # his: the row, then the file
    assert location(r) == "/karton?ok=Fotografija je obrisana.#napredak"
    assert [p.image for p in db.photos(ivan)] == [third] and stored_files() == [third]
    assert ci.post(f"/karton/slika/{one}/obrisi", follow_redirects=False).status_code == 404       # gone
    assert "Dodaj fotografiju</button>" in card(ci.get("/karton").text, "card photos")   # this month has none again
    assert TestClient(app).post("/karton/slika", data={"mjesec": this.strftime("%Y-%m")},
                                files={"slika": ("a.jpg", picture(30, 20), "image/jpeg")},
                                follow_redirects=False).headers["location"] == "/login"


def test_media_shows_a_photo_to_its_member_and_staff_only(monkeypatch):
    """/media/<a progress photo>: the member whose photo it is (200, a JPEG,
    Cache-Control private), staff, the owner and a trainer alike (200),
    whatever their plans; another client is 403 (his online plan and the
    programmes it opens do not reach it), a guest goes to log in (303).
    Under R2 the member and staff get the 307 to the presigned link, private
    too, another client still 403. db.file_owner names the member (since
    25.11.2026; db.photo_owner until then); a name no karton file holds is
    none (a clip's stays a clip's: 404 when nothing holds it)."""
    ivan = make_user("ivan@test.local", plans=())
    make_user("ana@test.local")
    make_user("trener@test.local", plans=())                                       # the owner (OWNER_EMAIL), not a trainer
    make_user("amir@test.local", is_trainer=True, plans=())
    month = config.today().replace(day=1)
    ci = client_for("ivan@test.local")
    ci.post("/karton/slika", data={"mjesec": month.strftime("%Y-%m")}, files={"slika": ("a.jpg", picture(400, 300), "image/jpeg")})
    name = db.photos(ivan)[0].image
    assert db.file_owner(name) == ivan and db.file_owner("vjezba-1-0000000000000000.mp4") is None
    body = (config.MEDIA_DIR / name).read_bytes()
    for who in ("ivan@test.local", "trener@test.local", "amir@test.local"):
        r = client_for(who).get(f"/media/{name}")
        assert r.status_code == 200 and r.content == body, who
        assert r.headers["content-type"] == "image/jpeg" and r.headers["cache-control"] == "private", who
    assert client_for("ana@test.local").get(f"/media/{name}").status_code == 403
    r = TestClient(app).get(f"/media/{name}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert ci.get("/media/napredak-0-000000-0000000000000000.jpg").status_code == 404   # held by no photo, no clip
    monkeypatch.setattr(storage, "r2_enabled", lambda: True)
    monkeypatch.setattr(storage, "presigned_url", lambda n, expires_s=600: f"https://r2.example/{n}?sig=1")
    for who in ("ivan@test.local", "amir@test.local"):
        r = client_for(who).get(f"/media/{name}", follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == f"https://r2.example/{name}?sig=1", who
        assert r.headers["cache-control"] == "private", who
    assert client_for("ana@test.local").get(f"/media/{name}", follow_redirects=False).status_code == 403


def test_two_photos_for_one_month_at_once_leave_one_and_name_every_other():
    """Six photos filed to one month at once (db.set_photo, as six uploads
    landing together): under the member's row lock they take turns, so one
    row is left, holding one of them, and every other name comes back to
    exactly one caller as the photo it replaced, for its file to go: no
    file is left behind, none is named twice."""
    ivan = make_user("ivan@test.local")
    month = config.today().replace(day=1)
    names = [f"napredak-{ivan}-{month:%Y%m}-{k:016x}.jpg" for k in range(6)]
    replaced, errors = [], []

    def file(name: str) -> None:
        try:
            replaced.append(db.set_photo(ivan, month, name))
        except Exception as err:                       # an IntegrityError here would be the race lost
            errors.append(repr(err))

    threads = [threading.Thread(target=file, args=(n,)) for n in names]
    for th in threads: th.start()
    for th in threads: th.join()
    rows = db.photos(ivan)
    assert errors == [] and len(rows) == 1
    olds = [r for r in replaced if r is not None]
    assert replaced.count(None) == 1 and len(olds) == 5 and sorted(olds + [rows[0].image]) == sorted(names)


# ---------- the karton again (25.11.2026): documents, "Tjelesna kompozicija", an exercise's history ----------

# a PDF as small as can be (what is stored must be these bytes, as they came)
PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
       b"trailer<</Root 1 0 R>>\n%%EOF\n")
UNSUPPORTED_DOC = "Nepodržan format — dozvoljeno: pdf, jpg, png, webp."


def send_doc(c: TestClient, data: bytes, name: str, kind: str = "application/pdf", naziv: str | None = None):
    """A document under the limitations as the card's form posts it."""
    form = {} if naziv is None else {"naziv": naziv}
    return c.post("/karton/ogranicenja/dokument", data=form, files={"dokument": (name, data, kind)},
                  follow_redirects=False)


def doc_rows(chunk: str) -> list[tuple[str, str, str, str]]:
    """The documents' rows of a piece of a page (its spans unwrapped), as
    read: (the stored file it links to, its name, its chip, its date)."""
    return [(f, unescape(n), unescape(re.sub(r"<[^>]+>", "", chip)), day) for f, n, chip, day in re.findall(
        r'<li><div class="doc-main"><a class="tlink doc-name" href="/media/([^"]+)" target="_blank" rel="noopener">'
        r'([^<]*)</a>\s*<div class="doc-meta">(.*?)<span>([^<]*)</span></div></div>', chunk, re.S)]


def test_documents_under_the_limitations_for_the_member_and_the_trainer():
    """POST /karton/ogranicenja/dokument (25.11.2026, Amir: "U ograničenja i
    bolovi treba dodati mogućnost da se doda slika ili pdf"): the member's
    "Dodaj dokument" beside Uredi opens its own form (the file, data-focus,
    and "Naziv (neobavezno)", 80 characters) under the caption "Dokumenti",
    which his card carries before he has one. A PDF named by hand (cleaned)
    is stored as it came, nalaz-<id>-<hex>.pdf; a phone's photo with no name
    is named by its own file name (its path gone, cut to 80), turned upright
    and shrunk to 2400 px on its long side, a JPEG with no EXIF,
    nalaz-<id>-<hex>.jpg. The list, newest first, each its name a link to
    /media (a new tab), its chip ("PDF", "slika") and its date: the
    member's with his ✕ (asking first, naming it), the trainer's read only,
    whose amber "Ograničenja" shows with a document and no text. Refused,
    nothing stored: another format, a GIF named .jpg, a fake PDF (a .pdf
    that is no PDF, a JPEG named .pdf), no file, one over 15 MB. The ✕
    deletes his own (the row, then the file); another member's, or one
    gone, is 404; a guest is sent to log in."""
    ivan = make_user("ivan@test.local")
    ana = make_user("ana@test.local")
    make_user("trener@test.local", is_trainer=True)
    ci, ct = client_for("ivan@test.local"), client_for("trener@test.local")
    lim = card(ci.get("/karton").text, "card limits")
    assert ('<button type="button" class="act" onclick="qmtToggleForm(\'ogranicenja\')">Uredi</button>'
            '<button type="button" class="act" onclick="qmtToggleForm(\'lim-docs\')">Dodaj dokument</button>') in lim
    assert '<div class="lim-docs" id="lim-docs">\n    <h3>Dokumenti</h3>' in lim and 'class="doc-list"' not in lim
    assert ('<form class="le-edit" method="post" action="/karton/ogranicenja/dokument" enctype="multipart/form-data">' in lim
            and '<label for="doc-file">Dokument (pdf, jpg, png ili webp, do 15 MB)</label>' in lim
            and ('<input id="doc-file" type="file" name="dokument" accept="application/pdf,image/jpeg,image/png,'
                 'image/webp,.pdf,.jpg,.jpeg,.png,.webp" required data-focus>') in lim
            and '<label for="doc-name">Naziv (neobavezno)</label>' in lim
            and '<input id="doc-name" type="text" name="naziv" maxlength="80" autocomplete="off">' in lim)
    seen = card(ct.get(f"/karton/{ivan}").text, "card limits")
    assert "lim-docs" not in seen and "u-flag" not in seen and "<form" not in seen    # nothing to read, no flag

    for name, data, kind, error in (("nalaz.txt", b"samo tekst", "text/plain", UNSUPPORTED_DOC),
                                    ("nalaz.gif", picture(30, 20, "GIF"), "image/gif", UNSUPPORTED_DOC),
                                    ("nalaz.jpg", picture(30, 20, "GIF"), "image/jpeg", UNSUPPORTED_DOC),
                                    ("nalaz.pdf", b"ovo nije pdf", "application/pdf", UNSUPPORTED_DOC),
                                    ("nalaz.pdf", picture(30, 20), "application/pdf", UNSUPPORTED_DOC),
                                    ("", b"", "application/octet-stream", UNSUPPORTED_DOC),       # no file chosen
                                    ("velik.pdf", b"%PDF-" + b"\0" * (16 * 1024 * 1024), "application/pdf",
                                     "Dokument je veći od 15 MB.")):
        assert location(send_doc(ci, data, name, kind)) == f"/karton?error={error}#ogranicenja", name
    assert db.limitation_files(ivan) == [] and stored_files() == []

    r = send_doc(ci, PDF, "nalaz.pdf", naziv="  Nalaz   MR\tkoljena  ")
    assert location(r) == "/karton?ok=Dokument je spremljen.#ogranicenja"                  # the flash names no file
    long = "fizijatar_" * 10 + ".JPG"
    r = send_doc(ci, picture(3000, 4000, orientation=6), "C:\\Users\\ivan\\Slike\\" + long, "image/jpeg", naziv=" ")
    assert location(r) == "/karton?ok=Dokument je spremljen.#ogranicenja"
    img, pdf = db.limitation_files(ivan)                                                    # the newest first
    assert pdf.name == "Nalaz MR koljena" and re.fullmatch(rf"nalaz-{ivan}-[0-9a-f]{{16}}\.pdf", pdf.file)
    assert (config.MEDIA_DIR / pdf.file).read_bytes() == PDF                                # as it came
    assert img.name == long[:80] and re.fullmatch(rf"nalaz-{ivan}-[0-9a-f]{{16}}\.jpg", img.file)
    with Image.open(config.MEDIA_DIR / img.file) as im:
        assert im.format == "JPEG" and im.size == (2400, 1800)                              # upright, 2400 on its long side
        assert not im.getexif() and "exif" not in im.info
    assert stored_files() == sorted([pdf.file, img.file])
    assert db.doc_name("", "") == "Dokument" and db.doc_name(None, "/a/b/ ") == "Dokument"

    today = config.today().strftime("%-d.%-m.%Y.")
    rows = [(img.file, long[:80], "slika", today), (pdf.file, "Nalaz MR koljena", "PDF", today)]
    page, seen = card(ci.get("/karton").text, "card limits"), card(ct.get(f"/karton/{ivan}").text, "card limits")
    assert doc_rows(page) == rows and doc_rows(seen) == rows
    assert (f'action="/karton/ogranicenja/dokument/{pdf.id}/obrisi"' in page
            and 'data-confirm-title="Obrisati dokument?"' in page
            and 'data-confirm="Dokument „Nalaz MR koljena” bit će trajno obrisan."' in page
            and 'data-confirm-cta="Obriši dokument"' in page
            and '<button type="submit" class="k-x" aria-label="Obriši dokument Nalaz MR koljena">✕</button>' in page)
    assert "<form" not in seen and "k-x" not in seen and "Dodaj dokument" not in seen        # the trainer reads
    assert '<h2 id="lim-h">Ograničenja i bolovi</h2>\n    <span class="u-flag pain">Ograničenja</span>' in seen
    assert '<p class="kc-empty">Nema upisanih ograničenja.</p>' in seen                     # a document, no text: flagged

    db.add_limitation_file(ana, f"nalaz-{ana}-0123456789abcdef.pdf", "Njen nalaz")
    theirs = db.limitation_files(ana)[0].id
    assert ci.post(f"/karton/ogranicenja/dokument/{theirs}/obrisi", follow_redirects=False).status_code == 404
    assert [d.id for d in db.limitation_files(ana)] == [theirs]
    r = ci.post(f"/karton/ogranicenja/dokument/{pdf.id}/obrisi", follow_redirects=False)
    assert location(r) == "/karton?ok=Dokument je obrisan.#ogranicenja"
    assert [d.id for d in db.limitation_files(ivan)] == [img.id] and stored_files() == [img.file]
    assert ci.post(f"/karton/ogranicenja/dokument/{pdf.id}/obrisi", follow_redirects=False).status_code == 404   # gone
    assert TestClient(app).post("/karton/ogranicenja/dokument", files={"dokument": ("a.pdf", PDF, "application/pdf")},
                                follow_redirects=False).headers["location"] == "/login"


def test_ten_documents_at_most_even_when_they_come_at_once():
    """At most ten documents under a member's limitations
    (db.MAX_LIMITATION_FILES): filed at nine by eight uploads at once
    (three rounds, back to nine after each), they take turns under his row
    lock, one is the tenth and every other is refused ("Najviše 10
    dokumenata."), never eleven. At ten the route refuses before it stores
    a byte, and the card offers no "Dodaj dokument" (nor its form), its ten
    rows listed."""
    ivan = make_user("ivan@test.local")
    for k in range(9):
        db.add_limitation_file(ivan, f"nalaz-{ivan}-{k:016x}.pdf", f"Nalaz {k}")
    for round_ in range(3):
        added, refused_with, start = [], [], threading.Barrier(8)

        def file(k: int) -> None:
            start.wait()
            try:
                added.append(db.add_limitation_file(ivan, f"nalaz-{ivan}-{k:016x}.pdf", f"Nalaz {k}"))
            except ValueError as err:
                refused_with.append(str(err))

        threads = [threading.Thread(target=file, args=(100 * (round_ + 1) + k,)) for k in range(8)]
        for th in threads: th.start()
        for th in threads: th.join()
        assert len(added) == 1 and refused_with == ["Najviše 10 dokumenata."] * 7, (round_, added, refused_with)
        assert len(db.limitation_files(ivan)) == 10, round_
        if round_ < 2:
            db.delete_limitation_file(added[0], ivan)                              # nine again
    ci = client_for("ivan@test.local")
    r = send_doc(ci, PDF, "jedanaesti.pdf")
    assert location(r) == "/karton?error=Najviše 10 dokumenata.#ogranicenja" and stored_files() == []
    lim = card(ci.get("/karton").text, "card limits")
    assert "Dodaj dokument" not in lim and 'id="doc-file"' not in lim and len(doc_rows(lim)) == 10
    assert "<h3>Dokumenti</h3>" in lim


def body_rows(chunk: str) -> list[str]:
    """The entries of "Tjelesna kompozicija" in a piece of a page, as read:
    "12.11.2026. · 82,5 kg · InBody.pdf"."""
    return [text_of(x) for x in re.findall(r"<li><span>(.*?)</span>", chunk, re.S)]


def body_links(chunk: str) -> list[tuple[str, str]]:
    """The entries' documents in a piece of a page: (the stored file, the link's name)."""
    return [(f, unescape(n)) for f, n in re.findall(
        r'<a class="tlink" href="/media/([^"]+)" target="_blank" rel="noopener">([^<]*)</a>', chunk)]


def test_a_body_entry_is_a_mass_a_document_or_both():
    """POST /karton/masa, multipart since 25.11.2026 (Amir: "Tjelesna masa
    tu bi promijenio u tjelesna kompozicija gdje opet mogu dodati pdf ili
    sliku ili samo upisati ručno masu"): the card is "Tjelesna kompozicija",
    its form Kilogrami (no longer required), Datum, the document and the
    hint. An entry is a mass alone, a document alone (a PDF stored as it
    came, sastav-<id>-<YYYYMMDD>-<hex>.pdf, its link named by the upload's
    own name) or both (an image, shrunk to 2400 px); neither is refused
    ("Upiši masu ili dodaj dokument."), and so is a bad mass beside a good
    document and a fake PDF: nothing stored. A second save that day keeps
    what it does not give (a mass keeps the day's document) and replaces
    what it gives (a document: the old file goes). The big value and the
    head line are the newest entry that has a mass, past a newer document
    alone. The history: "12.11.2026. · 82,5 kg", "· 81 kg · vaga.jpg",
    with no mass the date and the link alone, the trainer's the same with
    no form; the ✕ deletes the entry and its file."""
    ivan = make_user("ivan@test.local")
    make_user("trener@test.local", is_trainer=True)
    ci, ct = client_for("ivan@test.local"), client_for("trener@test.local")
    today = config.today()
    d1, d2, d3 = today - timedelta(days=5), today - timedelta(days=3), today - timedelta(days=1)

    def send(day: date, kg: str = "", doc: tuple | None = None):
        return ci.post("/karton/masa", data={"kg": kg, "day": day.isoformat()},
                       files={"dokument": doc or ("", b"", "application/octet-stream")}, follow_redirects=False)

    masa = card(ci.get("/karton").text, "card masa")
    assert '<h2 id="masa-h">Tjelesna kompozicija</h2>' in masa
    assert ('<form class="le-edit" method="post" action="/karton/masa" enctype="multipart/form-data">' in masa
            and '<input id="ms-kg" type="number" name="kg" min="20" max="300" step="0.1" inputmode="decimal"></div>' in masa
            and '<label for="ms-doc">Dokument (pdf, jpg, png ili webp, do 15 MB)</label>' in masa
            and ('<input id="ms-doc" type="file" name="dokument" accept="application/pdf,image/jpeg,image/png,image/webp,'
                 '.pdf,.jpg,.jpeg,.png,.webp"></div>') in masa
            and ('<p class="hint ms-hint">Upiši masu, dodaj dokument (npr. ispis analize sastava tijela) ili oboje.</p>'
                 in masa))
    for kg, doc, error in (("", None, "Upiši masu ili dodaj dokument."),
                           ("19", ("InBody.pdf", PDF, "application/pdf"), "Neispravna masa."),
                           ("", ("InBody.pdf", b"nije pdf", "application/pdf"), UNSUPPORTED_DOC),
                           ("", ("InBody.docx", b"PK", "application/octet-stream"), UNSUPPORTED_DOC)):
        assert location(send(d1, kg, doc)) == f"/karton?error={error}#masa", (kg, doc and doc[0])
    assert db.weights(ivan) == [] and stored_files() == []

    assert location(send(d1, "82,5")) == "/karton?ok=Masa je spremljena.#masa"
    assert location(send(d2, "81", ("vaga.jpg", picture(3000, 2000), "image/jpeg"))) == \
        "/karton?ok=Masa i dokument su spremljeni.#masa"
    assert location(send(d3, doc=("InBody 24.11.pdf", PDF, "application/pdf"))) == "/karton?ok=Dokument je spremljen.#masa"
    rows = {w.measured_on: w for w in db.weights(ivan)}
    assert (rows[d1].kg, rows[d1].file, rows[d1].file_name) == (Decimal("82.5"), None, "")
    assert rows[d2].kg == Decimal("81.0") and rows[d2].file_name == "vaga.jpg"
    assert re.fullmatch(rf"sastav-{ivan}-{d2:%Y%m%d}-[0-9a-f]{{16}}\.jpg", rows[d2].file)
    with Image.open(config.MEDIA_DIR / rows[d2].file) as im:
        assert im.format == "JPEG" and im.size == (2400, 1600)
    assert rows[d3].kg is None and rows[d3].file_name == "InBody 24.11.pdf"
    assert re.fullmatch(rf"sastav-{ivan}-{d3:%Y%m%d}-[0-9a-f]{{16}}\.pdf", rows[d3].file)
    assert (config.MEDIA_DIR / rows[d3].file).read_bytes() == PDF
    assert stored_files() == sorted([rows[d2].file, rows[d3].file])

    for p in (ci.get("/karton").text, ct.get(f"/karton/{ivan}").text):
        masa = card(p, "card masa")
        assert f'<p class="ms-val">81 kg</p>\n  <p class="hint ms-date">{full(d2)}</p>' in masa     # past the newer document
        assert body_rows(masa) == [f"{full(d3)} · InBody 24.11.pdf", f"{full(d2)} · 81 kg · vaga.jpg", f"{full(d1)} · 82,5 kg"]
        assert body_links(masa) == [(rows[d3].file, "InBody 24.11.pdf"), (rows[d2].file, "vaga.jpg")]
    assert head_line(ci.get("/karton").text).endswith(f"Masa 81 kg ({short(d2)})")
    masa = card(ci.get("/karton").text, "card masa")
    assert f'data-confirm="Unos od {full(d3)} i njegov dokument bit će trajno obrisani."' in masa
    assert f'data-confirm="Unos 81 kg od {full(d2)} i njegov dokument bit će trajno obrisani."' in masa
    assert f'data-confirm="Unos 82,5 kg od {full(d1)} bit će trajno obrisan."' in masa
    assert "<form" not in card(ct.get(f"/karton/{ivan}").text, "card masa")

    old = rows[d2].file                                       # the same days again: what is given replaces,
    assert location(send(d3, "80,5")) == "/karton?ok=Masa je spremljena.#masa"            # the rest stays
    assert location(send(d2, doc=("InBody 22.11.pdf", PDF, "application/pdf"))) == "/karton?ok=Dokument je spremljen.#masa"
    rows = {w.measured_on: w for w in db.weights(ivan)}
    assert (rows[d3].kg, rows[d3].file_name) == (Decimal("80.5"), "InBody 24.11.pdf")
    assert (rows[d2].kg, rows[d2].file_name) == (Decimal("81.0"), "InBody 22.11.pdf") and rows[d2].file.endswith(".pdf")
    assert stored_files() == sorted([rows[d2].file, rows[d3].file]) and old not in stored_files()   # the old file gone
    assert len(db.weights(ivan)) == 3
    assert head_line(ci.get("/karton").text).endswith(f"Masa 80,5 kg ({short(d3)})")

    gone = rows[d3].file
    r = ci.post(f"/karton/masa/{rows[d3].id}/obrisi", follow_redirects=False)            # the entry, then its file
    assert location(r) == "/karton?ok=Unos je obrisan.#masa" and gone not in stored_files()
    r = ci.post(f"/karton/masa/{rows[d1].id}/obrisi", follow_redirects=False)            # a mass alone: no file to go
    assert location(r) == "/karton?ok=Unos je obrisan.#masa" and stored_files() == [rows[d2].file]
    assert [w.measured_on for w in db.weights(ivan)] == [d2]
    with pytest.raises(ValueError, match="Upiši masu ili dodaj dokument."):
        db.set_weight(ivan, today)
    with pytest.raises(ValueError, match="not a file name"):
        db.set_weight(ivan, today, None, file="../etc/passwd")


def test_documents_saved_for_one_day_at_once_leave_one_and_name_every_other():
    """Six documents filed to one day at once (db.set_weight, as six uploads
    landing together): under the member's row lock they take turns, so one
    entry is left, holding one of them, and every other name comes back to
    exactly one caller as the document it replaced, for its file to go: no
    file is left behind, none is named twice, no save fails."""
    ivan = make_user("ivan@test.local")
    day = config.today()
    names = [f"sastav-{ivan}-{day:%Y%m%d}-{k:016x}.pdf" for k in range(6)]
    replaced, errors, start = [], [], threading.Barrier(6)

    def file(name: str) -> None:
        start.wait()
        try:
            replaced.append(db.set_weight(ivan, day, None, file=name, file_name="InBody.pdf"))
        except Exception as err:                       # an IntegrityError here would be the race lost
            errors.append(repr(err))

    threads = [threading.Thread(target=file, args=(n,)) for n in names]
    for th in threads: th.start()
    for th in threads: th.join()
    rows = db.weights(ivan)
    assert errors == [] and len(rows) == 1 and rows[0].kg is None
    olds = [r for r in replaced if r is not None]
    assert replaced.count(None) == 1 and len(olds) == 5 and sorted(olds + [rows[0].file]) == sorted(names)


def test_media_serves_every_karton_file_to_its_member_and_staff_only(monkeypatch):
    """/media/<a karton file> since 25.11.2026 (db.file_owner: a progress
    photo, a document under the limitations, a PDF or an image, and a
    document of "Tjelesna kompozicija"): the member whose file it is and
    staff (a trainer, the owner) 200, another member 403, a guest 303 to
    log in; typed by the stored name (a PDF application/pdf, an image
    image/jpeg), Cache-Control private, X-Content-Type-Options nosniff, and
    a PDF inline under its stored name (no header carries the name he
    typed). Under R2 the member and staff get the 307 to the presigned
    link, private; another member is still 403."""
    ivan = make_user("ivan@test.local", plans=())
    make_user("ana@test.local")
    make_user("trener@test.local", plans=())                                       # the owner (OWNER_EMAIL)
    make_user("amir@test.local", is_trainer=True, plans=())
    ci = client_for("ivan@test.local")
    month = config.today().replace(day=1)
    ci.post("/karton/slika", data={"mjesec": month.strftime("%Y-%m")}, files={"slika": ("a.jpg", picture(400, 300), "image/jpeg")})
    send_doc(ci, PDF, "nalaz.pdf", naziv="Tajni nalaz")
    send_doc(ci, picture(500, 400), "sken.png", "image/png")
    ci.post("/karton/masa", data={"day": config.today().isoformat()}, files={"dokument": ("InBody.pdf", PDF, "application/pdf")})
    names = {"photo": db.photos(ivan)[0].image, "pdf": next(d.file for d in db.limitation_files(ivan) if d.is_pdf),
             "image": next(d.file for d in db.limitation_files(ivan) if not d.is_pdf), "body": db.weights(ivan)[0].file}
    assert all(db.file_owner(n) == ivan for n in names.values()) and db.file_owner("nalaz-0-0000000000000000.pdf") is None
    for kind, name in names.items():
        pdf = name.endswith(".pdf")
        body = (config.MEDIA_DIR / name).read_bytes()
        for who in ("ivan@test.local", "trener@test.local", "amir@test.local"):
            r = client_for(who).get(f"/media/{name}")
            assert r.status_code == 200 and r.content == body, (kind, who)
            assert r.headers["content-type"] == ("application/pdf" if pdf else "image/jpeg"), (kind, who)
            assert r.headers["cache-control"] == "private" and r.headers["x-content-type-options"] == "nosniff", (kind, who)
            if pdf:
                assert r.headers["content-disposition"] == f'inline; filename="{name}"', (kind, who)
                assert "Tajni" not in str(r.headers)
            else:
                assert "content-disposition" not in r.headers, (kind, who)
        assert client_for("ana@test.local").get(f"/media/{name}").status_code == 403, kind
        r = TestClient(app).get(f"/media/{name}", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", kind
    monkeypatch.setattr(storage, "r2_enabled", lambda: True)
    monkeypatch.setattr(storage, "presigned_url", lambda n, expires_s=600: f"https://r2.example/{n}?sig=1")
    for name in names.values():
        for who in ("ivan@test.local", "amir@test.local"):
            r = client_for(who).get(f"/media/{name}", follow_redirects=False)
            assert r.status_code == 307 and r.headers["location"] == f"https://r2.example/{name}?sig=1", (name, who)
            assert r.headers["cache-control"] == "private", (name, who)
        assert client_for("ana@test.local").get(f"/media/{name}", follow_redirects=False).status_code == 403, name


def a_termin(uid: int, title: str, days_ago: int) -> int:
    """A finished termin of `title` uid was booked into, days ago; its id."""
    sid = db.add_oneoff_session(title, datetime.now(config.TZ) - timedelta(days=days_ago), 60, 8, None)
    with db.session_scope() as s:
        s.add(Booking(user_id=uid, session_id=sid))
    return sid


def a_pass(uid: int, pid: int, did: int, saves: list[tuple], days_ago: int) -> int:
    """A finished online pass of uid's through day did, started days ago:
    each save (the item, the sets, the similar exercise swapped in or
    None) as the player makes it. Its id."""
    log = db.start_pass(uid, db.get_program(pid), db.get_day(did))
    for item_id, sets, swap in saves:
        item = db.get_day_item(item_id)
        if swap:
            db.swap_exercise(log.id, uid, item, swap)
        db.save_sets(log.id, uid, item, sets, db.exercise(swap or item.exercise_id))
    db.finish_pass(log.id, uid, 6, None, "")
    with db.engine.begin() as conn:
        conn.execute(sa_text("UPDATE workout_logs SET started_at = started_at - make_interval(days => :d), "
                             "finished_at = finished_at - make_interval(days => :d) WHERE id = :i"),
                     {"d": days_ago, "i": log.id})
    return log.id


def history_world() -> tuple[int, int, dict[str, int]]:
    """ivan's trainings for the history's tests (ana's, a client's too): a
    termin "Snaga" 10 days ago (Potisak s klupe twice, 6 × 90 and 8 × 80,
    then 5 × 95; Iskorak 10 × 20), a training outside a termin 6 days ago
    (Zgibovi 9, Potisak s klupe 6 × 92,5), two online passes of "Trening 1"
    4 and 2 days ago (Goblet čučanj 10 × 20 and Plank 40 s; then Goblet
    swapped for Prednji čučanj 8 × 30 and Plank 45 s); ana's training
    (Potisak 5 × 150). Then Potisak is renamed and Iskorak deleted from the
    library. (ivan, ana, the exercises' ids)."""
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    ex = library("Potisak s klupe", "Iskorak", "Zgibovi", "Goblet čučanj", "Prednji čučanj", "Plank")
    db.add_session_feedback(ivan, a_termin(ivan, "Snaga", 10), 7, None, "", sets=[
        logged(ex["Potisak s klupe"], "Potisak s klupe", (6, 90), (8, 80)), logged(ex["Iskorak"], "Iskorak", (10, 20)),
        logged(ex["Potisak s klupe"], "Potisak s klupe", (5, 95))])
    db.add_training_log(ivan, config.today() - timedelta(days=6), 6, "", sets=[
        logged(ex["Zgibovi"], "Zgibovi", (9, 0)), logged(ex["Potisak s klupe"], "Potisak s klupe", (6, 92.5))])
    pid = db.create_program("Online", None, "pocetna", "cijelo")
    did = db.add_day(pid)
    goblet, plank = db.add_day_item(did, ex["Goblet čučanj"], "trening"), db.add_day_item(did, ex["Plank"], "trening")
    db.update_day_item(plank, "trening", 2, None, 40, None, None, "")
    db.update_exercise(ex["Goblet čučanj"], "Goblet čučanj", "", "", "", {ex["Prednji čučanj"]})
    a_pass(ivan, pid, did, [(goblet, [{"reps": 10, "kg": 20.0}], None), (plank, [{"seconds": 40}], None)], 4)
    a_pass(ivan, pid, did, [(goblet, [{"reps": 8, "kg": 30.0}], ex["Prednji čučanj"]), (plank, [{"seconds": 45}], None)], 2)
    db.add_training_log(ana, config.today(), 9, "", sets=[logged(ex["Potisak s klupe"], "Potisak s klupe", (5, 150))])
    db.update_exercise(ex["Potisak s klupe"], "Potisak s klupe (šipka)", "", "", "")
    db.delete_exercise(ex["Iskorak"])
    return ivan, ana, ex


def test_logged_exercises_and_an_exercises_history():
    """db.logged_exercises and db.exercise_history (25.11.2026) read what
    the maxes read: a termin's osvrt (where: the termin's title), a training
    outside a termin ("Trening izvan termina") and the finished online
    passes (where: the day's label as the pass keeps it; a swapped exercise
    under the swap, never the plan's), never another member's. Each
    exercise once, in the alphabet's order, named by the library now
    (renamed: the new name) or, deleted, by the name it was logged under;
    `times` the trainings that hold it (logged twice in one training: once,
    its sets in one row, in the order logged), `last_on` its newest day. A
    history newest first, each its day, source, where and sets as the
    history prints them ("6 × 92,5 kg", "9", "45 s"); none for an exercise
    he never logged."""
    ivan, ana, ex = history_world()
    today = config.today()
    ago = lambda n: today - timedelta(days=n)                                     # noqa: E731
    assert [(e.name, e.exercise_id, e.times, e.last_on) for e in db.logged_exercises(ivan)] == [
        ("Goblet čučanj", ex["Goblet čučanj"], 1, ago(4)), ("Iskorak", ex["Iskorak"], 1, ago(10)),
        ("Plank", ex["Plank"], 2, ago(2)), ("Potisak s klupe (šipka)", ex["Potisak s klupe"], 2, ago(6)),
        ("Prednji čučanj", ex["Prednji čučanj"], 1, ago(2)), ("Zgibovi", ex["Zgibovi"], 1, ago(6))]
    assert [(e.name, e.times) for e in db.logged_exercises(ana)] == [("Potisak s klupe (šipka)", 1)]

    def history(uid: int, name: str) -> list[tuple]:
        return [(d.on, d.source, d.source_text, d.where, list(d.sets)) for d in db.exercise_history(uid, ex[name])]

    assert history(ivan, "Potisak s klupe") == [
        (ago(6), "gym", "dvorana", "Trening izvan termina", ["6 × 92,5 kg"]),
        (ago(10), "gym", "dvorana", "Snaga", ["6 × 90 kg", "8 × 80 kg", "5 × 95 kg"])]
    assert history(ivan, "Plank") == [(ago(2), "online", "online", "Trening 1", ["45 s"]),
                                      (ago(4), "online", "online", "Trening 1", ["40 s"])]
    assert history(ivan, "Goblet čučanj") == [(ago(4), "online", "online", "Trening 1", ["10 × 20 kg"])]   # not the swap's
    assert history(ivan, "Prednji čučanj") == [(ago(2), "online", "online", "Trening 1", ["8 × 30 kg"])]
    assert history(ivan, "Zgibovi") == [(ago(6), "gym", "dvorana", "Trening izvan termina", ["9"])]
    assert history(ivan, "Iskorak") == [(ago(10), "gym", "dvorana", "Snaga", ["10 × 20 kg"])]       # deleted: still his
    assert history(ana, "Potisak s klupe") == [(today, "gym", "dvorana", "Trening izvan termina", ["5 × 150 kg"])]
    assert db.exercise_history(ivan, 999999) == [] and db.exercise_history(ana, ex["Plank"]) == []
    assert [len(db.exercise_history(ivan, e.exercise_id)) for e in db.logged_exercises(ivan)] == \
        [e.times for e in db.logged_exercises(ivan)]                                    # times: the rows of its history


def hist_card(page: str) -> str:
    """"Povijest vježbe", its texts' spans unwrapped."""
    return bare(page.split('<section class="card hist" id="povijest-vjezbe"')[1].split("</section>")[0])


def test_the_history_card_on_the_three_views():
    """"Povijest vježbe" (25.11.2026), right after the maxes, on the
    member's own karton, a staff member's own and the trainer's view of a
    client: a GET form to that karton (back at the card), the exercises it
    holds as a native select's options (the script's combobox reads
    #hx-json: [id, name, "2× · zadnji put …"]), and "Prikaži". With
    ?vjezba=<id>: the exercise's name, "Zadnji put: … · dvorana" and that
    time's sets, its estimated max ("Procjena maksimuma: 111 kg", the maxes'
    own number), then every time, newest first, the newest ten and the rest
    under "prikaži sve". An id the karton does not hold (another member's
    exercise, a word): "Ta vježba nije u ovom kartonu."; nothing logged:
    "Još nema upisanih vježbi." and no form. A client never reaches another
    member's karton. Each maxes row's name links to its history."""
    ivan, ana, ex = history_world()
    amir = make_user("amir@test.local", is_trainer=True, plans=())
    ci, ct = client_for("ivan@test.local"), client_for("amir@test.local")
    today = config.today()
    ago = lambda n: (today - timedelta(days=n)).strftime("%-d.%-m.%Y.")          # noqa: E731
    for c, path in ((ci, "/karton"), (ct, f"/karton/{ivan}")):
        page = c.get(path).text
        assert page.index('class="card maxes"') < page.index('id="povijest-vjezbe"') < page.index('class="card termini"')
        hc = hist_card(page)
        assert '<h2 id="hist-h">Povijest vježbe</h2>' in hc
        assert f'<form class="hx-form" method="get" action="{path}#povijest-vjezbe">' in hc
        assert '<label for="hx-ex">Vježba</label>' in hc and '<select id="hx-ex" name="vjezba" data-chosen="">' in hc
        assert re.findall(r'<option value="(\d+)">([^<]*)</option>', hc) == [
            (str(e.exercise_id), e.name) for e in db.logged_exercises(ivan)]
        assert '<button type="submit" class="btn-sm btn-signal">Prikaži</button>' in hc and 'class="hx"' not in hc
        rows = json.loads(hc.split('<script type="application/json" id="hx-json">')[1].split("</script>")[0])
        assert rows[2] == [ex["Plank"], "Plank", f"2× · zadnji put {ago(2)}"] and len(rows) == 6
        assert [(a, b) for a, b, _ in rows] == [(e.exercise_id, e.name) for e in db.logged_exercises(ivan)]
        for m in db.estimated_maxes(ivan):                                            # the maxes link here
            assert f'<a class="tlink" href="?vjezba={m.exercise_id}#povijest-vjezbe">' in maxes_section(page)

        hc = hist_card(c.get(f"{path}?vjezba={ex['Potisak s klupe']}").text)
        assert f'data-chosen="{ex["Potisak s klupe"]}"' in hc
        assert f'<option value="{ex["Potisak s klupe"]}" selected>Potisak s klupe (šipka)</option>' in hc
        assert '<h3 class="hx-name">Potisak s klupe (šipka)</h3>' in hc
        assert f'<p class="hx-last">Zadnji put: {ago(6)} · dvorana</p>' in hc
        assert '<p class="hx-sets"><span class="set">6 × 92,5 kg</span></p>' in hc
        max_line = next(m.value_text for m in db.estimated_maxes(ivan) if m.exercise_id == ex["Potisak s klupe"])
        assert max_line == "111 kg"                                                     # 92,5 × 6, its best set
        assert '<p class="hx-max">Procjena maksimuma: <strong>111 kg</strong></p>' in hc
        assert [text_of(li) for li in re.findall(r"<li>(.*?)</li>", hc, re.S)] == [
            f"{ago(6)} dvorana · Trening izvan termina 6 × 92,5 kg",
            f"{ago(10)} dvorana · Snaga 6 × 90 kg · 8 × 80 kg · 5 × 95 kg"]
        assert "<details" not in hc
        hc = hist_card(c.get(f"{path}?vjezba={ex['Plank']}").text)                    # timed: no max
        assert '<p class="hx-last">Zadnji put: ' + ago(2) + " · online</p>" in hc and "hx-max" not in hc
        for bad in ("999999", "abc", "0", "-1", "9" * 5000, str(ex["Iskorak"] + 1000)):
            hc = hist_card(c.get(f"{path}?vjezba={bad}").text)
            assert '<p class="kc-empty">Ta vježba nije u ovom kartonu.</p>' in hc and 'class="hx"' not in hc, bad
            assert '<form class="hx-form"' in hc
    hc = hist_card(client_for("ana@test.local").get(f"/karton?vjezba={ex['Plank']}").text)   # his exercise, her karton
    assert '<p class="kc-empty">Ta vježba nije u ovom kartonu.</p>' in hc
    assert ci.get(f"/karton/{ana}?vjezba={ex['Potisak s klupe']}").status_code == 403         # never another's karton

    for k in range(12):                                         # twelve trainings more: ten shown, the rest folded
        db.add_training_log(ivan, today - timedelta(days=20 + k), 5, "", sets=[logged(ex["Zgibovi"], "Zgibovi", (k + 1, 0))])
    hc = hist_card(ci.get(f"/karton?vjezba={ex['Zgibovi']}").text)
    shown, folded = hc.split('<details class="sets"><summary>prikaži sve</summary>')
    assert len(re.findall(r"<li>", shown)) == 10 and len(re.findall(r"<li>", folded)) == 3
    assert text_of(re.findall(r"<li>(.*?)</li>", folded, re.S)[-1]) == f"{(today - timedelta(days=31)).strftime('%-d.%-m.%Y.')} dvorana · Trening izvan termina 12"

    hc = hist_card(client_for("amir@test.local").get("/karton").text)                 # a staff member's own: nothing yet
    assert '<p class="kc-empty">Još nema upisanih vježbi.</p>' in hc and "<form" not in hc and "hx-json" not in hc
    db.add_training_log(amir, today, 6, "", sets=[logged(ex["Plank"], "Plank", (3, 0))])
    hc = hist_card(client_for("amir@test.local").get(f"/karton?vjezba={ex['Plank']}").text)
    assert '<form class="hx-form" method="get" action="/karton#povijest-vjezbe">' in hc
    assert f'<p class="hx-last">Zadnji put: {today.strftime("%-d.%-m.%Y.")} · dvorana</p>' in hc


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


def _columns() -> dict[str, dict]:
    return {c["name"]: c for c in sa_inspect(db.engine).get_columns("training_logs")}


# the karton's documents (25.11.2026): limitation_files, a weight's document
DOCUMENTS = "2b7e4c9a61d3_karton_documents.py"


def test_the_sets_migration_adds_the_column_and_takes_it_away():
    """f43e976906a1, run on qmt_test as before it (training_logs without
    sets, an osvrt in it): the column as the model has it, Text, NOT NULL,
    '[]' by default; the osvrt already there has an empty log, a row
    inserted without one too, and a log is stored; downgrade drops the
    column, the osvrt staying, and a second upgrade adds it again, empty."""
    mig = _migration("f43e976906a1_training_logs_sets.py")
    assert (mig.revision, mig.down_revision) == ("f43e976906a1", "dc22ce1ed7e6")
    ivan = make_user("ivan@test.local")
    ex = library("Potisak s klupe")
    log_id = db.add_training_log(ivan, date(2026, 11, 20), 6, "Prije.")
    with db.engine.begin() as conn:                                          # the table as before the revision
        conn.execute(sa_text("ALTER TABLE training_logs DROP COLUMN sets"))
    assert "sets" not in _columns()
    _run(mig.upgrade)
    assert _schema_diffs("training_logs") == []
    col = _columns()["sets"]
    assert not col["nullable"] and col["default"] == "'[]'::text"
    assert stored(ivan) == [(None, date(2026, 11, 20), 6, None, "Prije.", [])]
    with db.engine.begin() as conn:                                          # its default, a row as bare as can be
        assert conn.execute(sa_text("INSERT INTO training_logs (user_id, date, note) VALUES (:u, '2026-11-21', '') "
                                    "RETURNING sets"), {"u": ivan}).scalar_one() == "[]"
    db.update_training_log(log_id, ivan, 6, None, "Prije.", sets=[logged(ex["Potisak s klupe"], "Potisak s klupe", (6, 90))])
    assert db.estimated_maxes(ivan)[0].value == 108.0
    _run(mig.downgrade)
    assert "sets" not in _columns()
    with db.engine.connect() as conn:
        assert conn.execute(sa_text("SELECT effort, note FROM training_logs WHERE id = :i"), {"i": log_id}).one() == (6, "Prije.")
    _run(mig.upgrade)
    assert _schema_diffs("training_logs") == [] and [x[5] for x in stored(ivan)] == [[], []]


def test_the_body_migration_adds_the_columns_and_the_tables_and_takes_them_away():
    """0401f7fb9861, run on qmt_test as before it (users without height_cm
    and limitations, neither table, members in it): the columns and the
    tables as the models have them (users.height_cm SmallInteger NULL,
    users.limitations Text NOT NULL '' by default; weights and
    progress_photos), the members already there with no height and an empty
    text. In SQL: one value a day and one photo a month (a second row is
    refused), another day, month or member is a row of its own, and a
    member's rows go with him. Downgrade takes the tables and the columns
    away, the members staying; a second upgrade brings them back, empty.
    The documents' revision (2b7e4c9a61d3, 25.11.2026) runs on top each way:
    weights is the model's only with it."""
    mig = _migration("0401f7fb9861_karton_body_and_photos.py")
    assert (mig.revision, mig.down_revision) == ("0401f7fb9861", "f43e976906a1")
    docs = _migration(DOCUMENTS)
    ivan = make_user("ivan@test.local")
    ana = make_user("ana@test.local", plans=())
    with db.engine.begin() as conn:                                          # the schema as before the revision
        conn.execute(sa_text("DROP TABLE limitation_files"))                 # (2b7e4c9a61d3's: made again on top)
        conn.execute(sa_text("DROP TABLE progress_photos"))
        conn.execute(sa_text("DROP TABLE weights"))
        conn.execute(sa_text("ALTER TABLE users DROP COLUMN height_cm, DROP COLUMN limitations"))
    assert not {"weights", "progress_photos"} & set(sa_inspect(db.engine).get_table_names())
    _run(mig.upgrade)
    _run(docs.upgrade)
    for table in ("users", "weights", "progress_photos"):
        assert _schema_diffs(table) == [], table
    cols = {c["name"]: c for c in sa_inspect(db.engine).get_columns("users")}
    assert cols["height_cm"]["nullable"] and str(cols["height_cm"]["type"]) == "SMALLINT"
    assert not cols["limitations"]["nullable"] and cols["limitations"]["default"] == "''::text"
    assert {t: {(u["name"], tuple(u["column_names"])) for u in sa_inspect(db.engine).get_unique_constraints(t)}
            for t in ("weights", "progress_photos")} == {"weights": {("uq_weights_user_day", ("user_id", "measured_on"))},
                                                         "progress_photos": {("uq_progress_photos_user_month", ("user_id", "month"))}}
    with db.engine.begin() as conn:
        assert conn.execute(sa_text("SELECT height_cm, limitations FROM users WHERE id = :i"), {"i": ivan}).one() == (None, "")
        conn.execute(sa_text("INSERT INTO weights (user_id, measured_on, kg) VALUES (:i, '2026-11-12', 82.5), "
                             "(:i, '2026-11-13', 82.4), (:a, '2026-11-12', 61)"), {"i": ivan, "a": ana})
        conn.execute(sa_text("INSERT INTO progress_photos (user_id, month, image) VALUES (:i, '2026-11-01', 'a.jpg'), "
                             "(:i, '2026-10-01', 'b.jpg'), (:a, '2026-11-01', 'c.jpg')"), {"i": ivan, "a": ana})
    for sql in ("INSERT INTO weights (user_id, measured_on, kg) VALUES (:i, '2026-11-12', 80)",
                "INSERT INTO progress_photos (user_id, month, image) VALUES (:i, '2026-11-01', 'd.jpg')"):
        with pytest.raises(IntegrityError):
            with db.engine.begin() as conn:
                conn.execute(sa_text(sql), {"i": ivan})
    assert [(w.measured_on, w.kg, w.kg_text) for w in db.weights(ivan)] == [(date(2026, 11, 13), Decimal("82.4"), "82,4"),
                                                                            (date(2026, 11, 12), Decimal("82.5"), "82,5")]
    with db.engine.begin() as conn:                                          # a member's rows go with him
        conn.execute(sa_text("DELETE FROM users WHERE id = :a"), {"a": ana})
        assert conn.execute(sa_text("SELECT count(*) FROM weights WHERE user_id = :a"), {"a": ana}).scalar_one() == 0
        assert conn.execute(sa_text("SELECT count(*) FROM progress_photos WHERE user_id = :a"), {"a": ana}).scalar_one() == 0
    _run(docs.downgrade)
    _run(mig.downgrade)
    assert not {"weights", "progress_photos"} & set(sa_inspect(db.engine).get_table_names())
    assert not {"height_cm", "limitations"} & {c["name"] for c in sa_inspect(db.engine).get_columns("users")}
    with db.engine.connect() as conn:
        assert conn.execute(sa_text("SELECT email FROM users WHERE id = :i"), {"i": ivan}).scalar_one() == "ivan@test.local"
    _run(mig.upgrade)
    _run(docs.upgrade)
    for table in ("users", "weights", "progress_photos"):
        assert _schema_diffs(table) == [], table
    assert db.weights(ivan) == [] and db.photos(ivan) == [] and db.get_user(ivan).limitations == ""


def test_the_documents_migration_makes_the_mass_optional_and_takes_it_back():
    """2b7e4c9a61d3 (25.11.2026), run on qmt_test as before it (weights
    with kg NOT NULL and no document, no limitation_files, a weight in it):
    the table and the weights' two columns and CHECK as the models have
    them; the weight already there keeps its mass, no document, file_name
    ''. In SQL an entry with neither a mass nor a document is refused
    (ck_weights_kg_or_file); a member's documents go with him. Downgrade
    deletes the entry with no mass (its file stays in storage: the
    migration touches no file), keeps the one with a mass (its document's
    name gone with the column), drops the table and the columns, kg NOT
    NULL again; a second upgrade brings them back, the masses as they
    were."""
    mig = _migration(DOCUMENTS)
    assert (mig.revision, mig.down_revision) == ("2b7e4c9a61d3", "fc1840b0a981")
    ivan = make_user("ivan@test.local")
    ana = make_user("ana@test.local", plans=())
    with db.engine.begin() as conn:                                          # the schema as before the revision
        conn.execute(sa_text("DROP TABLE limitation_files"))
        conn.execute(sa_text("ALTER TABLE weights DROP CONSTRAINT ck_weights_kg_or_file, DROP COLUMN file, "
                             "DROP COLUMN file_name, ALTER COLUMN kg SET NOT NULL"))
        conn.execute(sa_text("INSERT INTO weights (user_id, measured_on, kg) VALUES (:i, '2026-11-12', 82.5)"), {"i": ivan})
    assert "limitation_files" not in sa_inspect(db.engine).get_table_names()
    _run(mig.upgrade)
    for table in ("weights", "limitation_files"):
        assert _schema_diffs(table) == [], table
    cols = {c["name"]: c for c in sa_inspect(db.engine).get_columns("weights")}
    assert cols["kg"]["nullable"] and cols["file"]["nullable"] and not cols["file_name"]["nullable"]
    assert "ck_weights_kg_or_file" in {c["name"] for c in sa_inspect(db.engine).get_check_constraints("weights")}
    assert [i["column_names"] for i in sa_inspect(db.engine).get_indexes("limitation_files")] == [["user_id"]]
    assert [(w.measured_on, w.kg, w.file, w.file_name) for w in db.weights(ivan)] == [
        (date(2026, 11, 12), Decimal("82.5"), None, "")]
    with pytest.raises(IntegrityError, match="ck_weights_kg_or_file"):
        with db.engine.begin() as conn:
            conn.execute(sa_text("INSERT INTO weights (user_id, measured_on) VALUES (:i, '2026-11-13')"), {"i": ivan})
    db.set_weight(ivan, date(2026, 11, 14), None, file=f"sastav-{ivan}-20261114-0123456789abcdef.pdf", file_name="InBody.pdf")
    db.set_weight(ivan, date(2026, 11, 12), None, file=f"sastav-{ivan}-20261112-0123456789abcdef.pdf", file_name="Vaga.pdf")
    db.add_limitation_file(ivan, f"nalaz-{ivan}-0123456789abcdef.pdf", "Nalaz")
    db.add_limitation_file(ana, f"nalaz-{ana}-0123456789abcdef.pdf", "Njen")
    assert [(w.measured_on, w.kg, w.file_name) for w in db.weights(ivan)] == [
        (date(2026, 11, 14), None, "InBody.pdf"), (date(2026, 11, 12), Decimal("82.5"), "Vaga.pdf")]
    with db.engine.begin() as conn:                                          # a member's documents go with him
        conn.execute(sa_text("DELETE FROM users WHERE id = :a"), {"a": ana})
        assert conn.execute(sa_text("SELECT count(*) FROM limitation_files WHERE user_id = :a"), {"a": ana}).scalar_one() == 0
    _run(mig.downgrade)
    assert "limitation_files" not in sa_inspect(db.engine).get_table_names()
    cols = {c["name"]: c for c in sa_inspect(db.engine).get_columns("weights")}
    assert not {"file", "file_name"} & set(cols) and not cols["kg"]["nullable"]
    with db.engine.connect() as conn:                                        # the document alone is gone, the mass stays
        assert conn.execute(sa_text("SELECT measured_on, kg FROM weights WHERE user_id = :i"), {"i": ivan}).all() == [
            (date(2026, 11, 12), Decimal("82.5"))]
    _run(mig.upgrade)
    for table in ("weights", "limitation_files"):
        assert _schema_diffs(table) == [], table
    assert [(w.measured_on, w.kg, w.file, w.file_name) for w in db.weights(ivan)] == [
        (date(2026, 11, 12), Decimal("82.5"), None, "")]
    assert db.limitation_files(ivan) == []


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
# a form's exercise blocks as the page holds them: each block's number, the
# combobox's text, the exercise picked (the hidden ex_<n>) and its name,
# its rows' fields as name=value, whether "+ serija" shows, the list open,
# the focus in the combobox, the line under it, a gone exercise's line
BLOCKS = """form => [...document.querySelector(form).querySelectorAll('.xb')].map(b => {
  const q = b.querySelector('[role="combobox"]'), l = b.querySelector('.cbx-list'), v = b.querySelector('input[type="hidden"]');
  const gone = b.querySelector('.xb-gone');
  return {n: b.dataset.n, typed: q ? q.value : null, chosen: v.value, field: v.name,
          rows: [...b.querySelectorAll('tbody input')].map(i => i.name + '=' + i.value), more: !b.querySelector('.xb-add').hidden,
          open: l ? !l.hidden : false, focused: document.activeElement === q,
          error: (b.querySelector('.cbx-err') || {}).textContent || '', gone: gone.hidden ? '' : gone.textContent};
})"""
# a form's exercise log as a reader meets it: shown, "+ Dodaj vježbu" shown, log=1 in it
XL = """form => { const xl = document.querySelector(form + ' fieldset.xl'), add = xl.querySelector('.xl-add');
  return {shown: !xl.hidden && xl.offsetHeight > 0, add: !add.hidden && add.offsetHeight > 0,
          log: (xl.querySelector('input[name="log"]') || {}).value || null}; }"""


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


def test_the_exercise_log_on_a_phone(server):
    """At 390px, touch, ivan opens "Ispuni osvrt" on a finished termin: its
    exercise log is shown by the script, empty, log=1 in it. "+ Dodaj
    vježbu" adds a block, its combobox focused and its list open: "pot" and
    Enter pick Potisak s klupe, two sets typed; a second block is added and
    taken away ("Ukloni vježbu", the focus back on "+ Dodaj vježbu"); a
    third (numbered 2: the gap stays) gets "zgib", Enter and "+ serija", a
    fourth row. Spremi osvrt: the row says "2 vježbe", its "Serije" open on
    a tap, the maxes say 108 kg and 10 ponavljanja (its Iz the date and
    "dvorana" alone), beside the older osvrt's Iskorak, gone from the
    library, under the name it was logged with. "Uredi" on that row builds
    its blocks from the data:
    each exercise in its box, its sets in the rows; the first taken away and
    a set changed, Spremi replaces the log. An older osvrt whose exercise
    has left the library builds its block with nothing picked and the line
    naming it; its Spremi stops at "Odaberi vježbu s popisa.". A training
    outside a termin with a set typed and no exercise is not sent either.
    The page never scrolls sideways; no page errors. Without JavaScript
    there is no exercise block (no select of the library on the page): an
    osvrt's edit sends napor and komentar, and its log stays as it was."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    ivan = make_user("ivan@test.local")
    ex = library(("Potisak s klupe", "prsa, šipka"), ("Zgibovi", "leđa, bodyweight"), ("Goblet čučanj", "noge, girja"),
                 ("Plank", "core"), ("Iskorak", "noge"))
    sid = attended_session(ivan)
    older = attended_session(ivan, hours_ago=2 * 24)
    db.add_session_feedback(ivan, older, 5, None, "Staro.", sets=[logged(ex["Iskorak"], "Iskorak", (10, 20))])
    old_log = next(x.id for x in db.training_logs(ivan) if x.session_id == older)
    db.delete_exercise(ex["Iskorak"])
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _phone(browser, server, "ivan@test.local")
        pg.goto(server + "/karton"); pg.wait_for_load_state("networkidle")
        check(pg.evaluate(OVERFLOW) == 0, f"the karton overflows by {pg.evaluate(OVERFLOW)}px")
        # (vjezba: "Povijest vježbe"'s picker without the script, his logged exercises, not the library)
        check(pg.locator("select:not([name=effort]):not([name=feeling]):not([name=mjesec]):not([name=vjezba])").count() == 0, "a select of the library is on the page")
        form = f"#s-{sid} form.le-edit"
        pg.tap(f"#s-{sid} button.act:has-text('Ispuni osvrt')")
        check(pg.is_visible(form), "Ispuni osvrt did not open the form")
        xl = pg.evaluate(XL, form)
        check(xl == {"shown": True, "add": True, "log": "1"} and pg.evaluate(BLOCKS, form) == [],
              f"the form's log at first: {xl}, {pg.evaluate(BLOCKS, form)}")
        pg.select_option(f"#fb-effort-{sid}", "8")
        pg.tap(f"{form} .xl-add")
        st = pg.evaluate(BLOCKS, form)
        check(len(st) == 1 and st[0]["n"] == "0" and st[0]["field"] == "ex_0" and st[0]["focused"] and st[0]["open"]
              and st[0]["more"] and st[0]["rows"] == ["reps_0_1=", "kg_0_1=", "reps_0_2=", "kg_0_2=", "reps_0_3=", "kg_0_3="],
              f"+ Dodaj vježbu added: {st}")
        pg.keyboard.type("pot")
        pg.keyboard.press("Enter")
        st = pg.evaluate(BLOCKS, form)
        check(st[0]["chosen"] == str(ex["Potisak s klupe"]) and st[0]["typed"] == "Potisak s klupe" and not st[0]["open"],
              f"'pot' and Enter picked: {st[0]}")
        pg.fill(f"{form} input[name=reps_0_1]", "6"); pg.fill(f"{form} input[name=kg_0_1]", "90")
        pg.fill(f"{form} input[name=reps_0_2]", "5"); pg.fill(f"{form} input[name=kg_0_2]", "92.5")
        pg.tap(f"{form} .xl-add")
        pg.tap(f"{form} .xl-hint")                                          # a tap outside its open list shuts it …
        pg.tap(f'{form} .xb[data-n="1"] .xb-x')                             # … and the block is taken away again
        check([b["n"] for b in pg.evaluate(BLOCKS, form)] == ["0"]
              and pg.evaluate(f"() => document.activeElement === document.querySelector('{form} .xl-add')"),
              f"Ukloni vježbu left: {pg.evaluate(BLOCKS, form)}")
        pg.tap(f"{form} .xl-add")
        pg.keyboard.type("zgib")
        pg.keyboard.press("Enter")
        pg.tap(f'{form} .xb[data-n="2"] .xb-add')
        st = pg.evaluate(BLOCKS, form)
        check([b["n"] for b in st] == ["0", "2"] and st[1]["chosen"] == str(ex["Zgibovi"])
              and st[1]["rows"][-2:] == ["reps_2_4=", "kg_2_4="], f"zgib, Enter and + serija: {st}")
        pg.fill(f"{form} input[name=reps_2_1]", "9"); pg.fill(f"{form} input[name=reps_2_4]", "10")
        pg.evaluate("() => document.activeElement.blur()")
        check(pg.evaluate(OVERFLOW) == 0, f"the open form overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap(f"{form} button[type=submit]")
        pg.wait_for_load_state("networkidle")
        logs = {x.session_id: x for x in db.training_logs(ivan)}
        new = logs.get(sid)
        check(new is not None and new.lines() == [("Potisak s klupe", ["6 × 90 kg", "5 × 92,5 kg"]), ("Zgibovi", ["9", "10"])],
              f"stored: {new and new.lines()}")
        if new:
            row = f"#log-{new.id}"
            check((pg.text_content(f"{row} .le-ex") or "").strip() == "2 vježbe", "the row does not say 2 vježbe")
            pg.tap(f"{row} details.sets > summary")
            pg.wait_for_timeout(200)
            lines = pg.locator(f"{row} details.sets li").all_text_contents()
            check(pg.locator(f"{row} details.sets").evaluate("d => d.open")
                  and lines == ["Potisak s klupe: 6 × 90 kg · 5 × 92,5 kg", "Zgibovi: 9 · 10"], f"Serije: {lines}")
            mx = pg.evaluate("() => [...document.querySelectorAll('.maxes tbody tr')].map(tr => [...tr.cells].map(c => c.textContent.replace(/\\s+/g, ' ').trim()))")
            day = new.date.strftime("%-d.%-m.%Y.")
            gone_day = next(x.date for x in db.training_logs(ivan) if x.id == old_log).strftime("%-d.%-m.%Y.")
            check(mx == [["Iskorak", "26,5 kg", f"20 kg × 10 · {gone_day} dvorana"],          # gone from the library: as logged
                         ["Potisak s klupe", "108 kg", f"90 kg × 6 · {day} dvorana"], ["Zgibovi", "10 ponavljanja", f"{day} dvorana"]],
                  f"the maxes: {mx}")
            check(pg.evaluate(OVERFLOW) == 0, f"the karton with the log overflows by {pg.evaluate(OVERFLOW)}px")
            # its edit: the blocks built from the data, the exercise in the box, the sets in the rows
            edit = f"{row} form.le-edit"
            pg.tap(f"{row} button.act:has-text('Uredi')")
            st = pg.evaluate(BLOCKS, edit)
            check([(b["n"], b["typed"], b["chosen"], b["rows"]) for b in st] == [
                ("0", "Potisak s klupe", str(ex["Potisak s klupe"]),
                 ["reps_0_1=6", "kg_0_1=90", "reps_0_2=5", "kg_0_2=92.5", "reps_0_3=", "kg_0_3="]),
                ("1", "Zgibovi", str(ex["Zgibovi"]), ["reps_1_1=9", "kg_1_1=", "reps_1_2=10", "kg_1_2=", "reps_1_3=", "kg_1_3="])]
                  and pg.evaluate(XL, edit)["log"] == "1", f"the edit's blocks: {st}")
            pg.tap(f'{edit} .xb[data-n="0"] .xb-x')
            pg.fill(f"{edit} input[name=reps_1_1]", "12")
            with pg.expect_navigation():
                pg.tap(f"{edit} button[type=submit]")
            pg.wait_for_load_state("networkidle")
            saved = next((x for x in db.training_logs(ivan) if x.session_id == sid), None)
            check(saved is not None and saved.lines() == [("Zgibovi", ["12", "10"])], f"the edit stored {saved and saved.lines()}")
        # an exercise gone from the library: nothing picked, the line naming it, Spremi stops
        old = f"#log-{old_log} form.le-edit"
        pg.tap(f"#log-{old_log} button.act:has-text('Uredi')")
        st = pg.evaluate(BLOCKS, old)
        check(len(st) == 1 and st[0]["chosen"] == "" and st[0]["typed"] == "" and st[0]["rows"][:2] == ["reps_0_1=10", "kg_0_1=20"]
              and st[0]["gone"] == "„Iskorak” više nije u bazi vježbi — odaberi drugu vježbu ili ukloni ovu.",
              f"the gone exercise's block: {st}")
        url = pg.url
        pg.tap(f"{old} button[type=submit]")
        pg.wait_for_timeout(400)
        st = pg.evaluate(BLOCKS, old)
        check(pg.url == url and st[0]["error"] == "Odaberi vježbu s popisa." and st[0]["focused"],
              f"Spremi with the gone exercise: {pg.url}, {st}")
        check([x.lines() for x in db.training_logs(ivan) if x.id == old_log] == [[("Iskorak", ["10 × 20 kg"])]],
              "the gone exercise's log changed")
        pg.goto(server + "/karton"); pg.wait_for_load_state("networkidle")
        pg.tap("#trening-novi > button.act")
        pg.select_option("#nt-effort", "5")
        pg.tap("#trening-novi .xl-add")
        pg.fill("#trening-novi input[name=reps_0_1]", "8")
        url = pg.url
        pg.tap("#trening-novi button[type=submit]")
        pg.wait_for_timeout(400)
        st = pg.evaluate(BLOCKS, "#trening-novi form")
        check(pg.url == url and len(db.training_logs(ivan)) == 2, f"a set with no exercise was sent: {pg.url}")
        check(st[0]["error"] == "Odaberi vježbu s popisa." and st[0]["focused"], f"no word at Spremi: {st}")
        check(pg.evaluate(OVERFLOW) == 0, f"the training outside a termin overflows by {pg.evaluate(OVERFLOW)}px")
        problems += errors
        ctx.close()

        ctx = browser.new_context(viewport={"width": 390, "height": 844}, java_script_enabled=False)
        pg = ctx.new_page()
        pg.goto(server + "/login")
        pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
        with pg.expect_navigation():
            pg.click("main button[type=submit]")
        pg.goto(server + "/karton"); pg.wait_for_load_state("networkidle")
        saved = next((x for x in db.training_logs(ivan) if x.session_id == sid), None)
        if saved:
            edit = f"#log-{saved.id} form.le-edit"
            pg.evaluate(f"() => document.getElementById('log-{saved.id}').classList.add('editing')")   # as its toggle opens it
            check(pg.is_visible(edit) and not pg.is_visible(f"{edit} fieldset.xl") and pg.locator(f"{edit} .xb").count() == 0
                  and pg.locator("select:not([name=effort]):not([name=feeling]):not([name=mjesec]):not([name=vjezba])").count() == 0
                  and pg.locator(f'{edit} input[name="log"]').count() == 0, "without JS an exercise block or log=1 is there")
            pg.select_option(f"#ed-effort-{saved.id}", "3")
            pg.fill(f"#ed-note-{saved.id}", "Bez skripte.")
            check(pg.evaluate(OVERFLOW) == 0, f"without JS the edit overflows by {pg.evaluate(OVERFLOW)}px")
            # the keyboard sends it: the focus on Spremi, Enter (no pointer waits on a page without JS)
            pg.focus(f"{edit} button[type=submit]")
            with pg.expect_navigation():
                pg.keyboard.press("Enter")
            after = next((x for x in db.training_logs(ivan) if x.session_id == sid), None)
            check(after is not None and (after.effort, after.note, after.lines()) == (3, "Bez skripte.", [("Zgibovi", ["12", "10"])]),
                  f"without JS the edit stored {after and (after.effort, after.note, after.lines())}")
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# the cards' places on the page: [top, left, width] of each (the diary's
# heading for the diary)
PLACES = """() => Object.fromEntries(['.upitnik', '#ogranicenja', '#masa', '#napredak', '.maxes', '.termini', '#osvrti'].map(s => {
  const r = document.querySelector(s).getBoundingClientRect(); return [s, [Math.round(r.top + scrollY), Math.round(r.left), Math.round(r.width)]]; }))"""


def test_the_body_cards_on_a_phone(server):
    """At 390px, touch, on ivan's karton: the cards one under the other in
    their order (25.11.2026), the upitnik block, the limitations, the
    weight, the photos, the maxes, the termini, the diary last; every card
    fits the screen. "Upiši"
    opens the weight form, the focus in Kilogrami, Datum today: 82.5 and
    Spremi, and the card says 82,5 kg and today, its history one row, the
    head line "Masa 82,5 kg (…)". "Uredi" opens the textarea, focused: two
    lines and Spremi, shown on two lines. "Dodaj fotografiju" opens the
    photo form, the focus on the file: a photo chosen and Spremi, one
    thumbnail of this month that loads through /media, the button now
    "Zamijeni ovomjesečnu". The page never scrolls sideways; no page
    errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    ivan = make_user("ivan@test.local")
    today = config.today()
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _phone(browser, server, "ivan@test.local")
        pg.goto(server + "/karton"); pg.wait_for_load_state("networkidle")
        check(pg.evaluate(OVERFLOW) == 0, f"the karton overflows by {pg.evaluate(OVERFLOW)}px")
        at = pg.evaluate(PLACES)
        check(at[".upitnik"][0] < at["#ogranicenja"][0] < at["#masa"][0] < at["#napredak"][0] < at[".maxes"][0]
              < at[".termini"][0] < at["#osvrti"][0]
              and all(left >= 0 and left + width <= 390 for _, left, width in at.values()), f"the cards' places: {at}")
        # the weight
        pg.tap("#masa .kc-head .act")
        check(pg.is_visible("#masa > form.le-edit") and pg.evaluate("() => document.activeElement.id") == "ms-kg"
              and pg.input_value("#ms-day") == today.isoformat(), "Upiši: the form, its focus or its day")
        pg.fill("#ms-kg", "82.5")
        check(pg.evaluate(OVERFLOW) == 0, f"the weight form overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap("#masa > form.le-edit button[type=submit]")
        pg.wait_for_load_state("networkidle")
        check([(w.measured_on, w.kg) for w in db.weights(ivan)] == [(today, Decimal("82.5"))], f"stored: {db.weights(ivan)}")
        check(pg.text_content("#masa .ms-val") == "82,5 kg" and pg.text_content("#masa .ms-date") == full(today)
              and pg.locator("#masa .ms-list li > span").all_text_contents() == [f"{full(today)} · 82,5 kg"],
              "the card after Spremi")
        check(pg.text_content(".k-body") == f"Masa 82,5 kg ({short(today)})", f"the head line: {pg.text_content('.k-body')}")
        check(pg.evaluate(OVERFLOW) == 0, f"the weight card overflows by {pg.evaluate(OVERFLOW)}px")
        # the limitations
        pg.tap("#ogranicenja .kc-head .act")
        check(pg.is_visible("#lim-input") and pg.evaluate("() => document.activeElement.id") == "lim-input"
              and not pg.is_visible("#ogranicenja .kc-empty"), "Uredi: the textarea, its focus, the empty line gone")
        pg.fill("#lim-input", "Bol u desnom koljenu.\nBez skokova.")
        check(pg.evaluate(OVERFLOW) == 0, f"the limitations' form overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap("#ogranicenja button[type=submit]")
        pg.wait_for_load_state("networkidle")
        check(db.get_user(ivan).limitations == "Bol u desnom koljenu.\nBez skokova.", "the limitations stored")
        check(pg.evaluate("() => document.querySelector('#ogranicenja .lim-text').innerText") == "Bol u desnom koljenu.\nBez skokova.",
              "the limitations shown on two lines")
        # the photo
        pg.tap("#napredak .kc-head .act")
        check(pg.is_visible("#ph-file") and pg.evaluate("() => document.activeElement.id") == "ph-file"
              and pg.input_value("#ph-month") == today.strftime("%Y-%m"), "Dodaj fotografiju: the form, its focus or its month")
        check(pg.evaluate(OVERFLOW) == 0, f"the photo form overflows by {pg.evaluate(OVERFLOW)}px")
        pg.set_input_files("#ph-file", files=[{"name": "foto.jpg", "mimeType": "image/jpeg", "buffer": picture(900, 1200)}])
        with pg.expect_navigation():
            pg.tap("#napredak button[type=submit]")
        pg.wait_for_load_state("networkidle")
        pg.locator("#napredak").scroll_into_view_if_needed()
        pg.wait_for_function("() => [...document.querySelectorAll('#napredak .ph img')].every(i => i.complete)")
        thumbs = pg.evaluate("""() => [...document.querySelectorAll('#napredak .ph')].map(li => {
          const img = li.querySelector('img'), r = li.querySelector('.ph-img').getBoundingClientRect();
          return [li.querySelector('.ph-cap').textContent, img.naturalWidth > 0, Math.round(r.width), Math.round(r.height)]; })""")
        check(thumbs == [[_month_label(today.replace(day=1)), True, 120, 160]], f"the thumbnails: {thumbs}")
        check((pg.text_content("#napredak .kc-head .act") or "").strip() == "Zamijeni ovomjesečnu", "the photo button")
        check(pg.evaluate(OVERFLOW) == 0, f"the photos overflow by {pg.evaluate(OVERFLOW)}px")
        problems += errors
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# how much each card's content is wider than the card (0 for none), by its id
WIDER = """() => Object.fromEntries(['ogranicenja', 'masa', 'povijest-vjezbe'].map(id => {
  const el = document.getElementById(id); return [id, el.scrollWidth - el.clientWidth]; }))"""


def test_the_documents_and_the_history_on_a_phone(server):
    """At 390px, touch, on ivan's karton (25.11.2026): "Dodaj dokument"
    opens the documents' own form (the text's stays shut), the focus on the
    file: a PDF whose name is one long word and Spremi, back at the card,
    its row there (cut to 80, "PDF", today), the name wrapping inside the
    card. "Upiši" on "Tjelesna kompozicija", the focus in Kilogrami: no
    mass, yesterday, a document and Spremi: a row of the date and the link,
    the big value still the mass of before. "Povijest vježbe": "Prikaži"
    with nothing picked stays, "Odaberi vježbu s popisa." under the box; a
    tap in the picker opens its list (a row its name over "1× · zadnji put
    …"), "pot" and Enter pick, "Prikaži" goes to ?vjezba= at the card,
    which shows the exercise, its time and its max. At 360px the same page
    with both forms open. Nothing is wider than its card, the page never
    scrolls sideways; no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    ivan = make_user("ivan@test.local")
    ex = library("Potisak s klupe", "Zgibovi")
    today, yday = config.today(), config.today() - timedelta(days=1)
    db.set_weight(ivan, today - timedelta(days=3), Decimal("82"))
    db.add_training_log(ivan, today - timedelta(days=2), 7, "", sets=[logged(ex["Potisak s klupe"], "Potisak s klupe", (6, 90))])
    long = "Nalaz_magnetske_rezonance_desnog_koljena_s_misljenjem_specijalista_ortopedije_i_preporukama.pdf"
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _phone(browser, server, "ivan@test.local")
        pg.goto(server + "/karton"); pg.wait_for_load_state("networkidle")
        check(pg.evaluate(OVERFLOW) == 0, f"the karton overflows by {pg.evaluate(OVERFLOW)}px")
        # a document under the limitations
        pg.tap("#ogranicenja .kc-head button:has-text('Dodaj dokument')")
        check(pg.is_visible("#lim-docs form.le-edit") and not pg.is_visible("#lim-input")
              and pg.evaluate("() => document.activeElement.id") == "doc-file",
              "Dodaj dokument: its form, the text's shut, the focus on the file")
        pg.set_input_files("#doc-file", files=[{"name": long, "mimeType": "application/pdf", "buffer": PDF}])
        check(pg.evaluate(OVERFLOW) == 0, f"the documents' form overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap("#lim-docs button[type=submit]")
        pg.wait_for_load_state("networkidle")
        check(pg.url.endswith("/karton?ok=Dokument%20je%20spremljen.#ogranicenja"), f"after the document: {pg.url}")
        rows = pg.locator("#lim-docs .doc-list li").all_inner_texts()
        check([r.split("\n")[:3] for r in rows] == [[long[:80], "PDF", today.strftime("%-d.%-m.%Y.")]], f"the documents: {rows}")
        name = pg.locator("#lim-docs .doc-name").bounding_box()
        box = pg.locator("#ogranicenja").bounding_box()
        check(name["x"] + name["width"] <= box["x"] + box["width"] and name["height"] > 30,
              f"the long name does not wrap inside the card: {name}, {box}")
        # a document alone in "Tjelesna kompozicija"
        pg.tap("#masa .kc-head .act")
        check(pg.evaluate("() => document.activeElement.id") == "ms-kg", "Upiši: the focus is not in Kilogrami")
        pg.fill("#ms-day", yday.isoformat())
        pg.set_input_files("#ms-doc", files=[{"name": "InBody.pdf", "mimeType": "application/pdf", "buffer": PDF}])
        check(pg.evaluate(OVERFLOW) == 0, f"the body form overflows by {pg.evaluate(OVERFLOW)}px")
        with pg.expect_navigation():
            pg.tap("#masa > form.le-edit button[type=submit]")
        pg.wait_for_load_state("networkidle")
        check(pg.locator("#masa .ms-list li > span").all_text_contents()
              == [f"{full(yday)} · InBody.pdf", f"{full(today - timedelta(days=3))} · 82 kg"]
              and pg.text_content("#masa .ms-val") == "82 kg", "the body card after the document")
        check(pg.get_attribute("#masa .ms-list a", "href") == "/media/" + db.weights(ivan)[0].file
              and pg.get_attribute("#masa .ms-list a", "target") == "_blank", "the document's link")
        # the history: nothing picked, then a pick
        pg.locator("#povijest-vjezbe").scroll_into_view_if_needed()
        url = pg.url
        pg.tap("#povijest-vjezbe button[type=submit]")
        pg.wait_for_timeout(300)
        check(pg.url == url and pg.text_content("#hx-ex-err") == "Odaberi vježbu s popisa.",
              f"Prikaži with nothing picked: {pg.url}, {pg.text_content('#hx-ex-err')!r}")
        pg.tap("#hx-ex-q")
        listed = pg.locator("#hx-ex-list [role=option]").all_inner_texts()
        check(pg.is_visible("#hx-ex-list") and [x.split("\n") for x in listed] == [
            ["Potisak s klupe", f"1× · zadnji put {(today - timedelta(days=2)).strftime('%-d.%-m.%Y.')}"]],
              f"the picker's list: {listed}")
        pg.keyboard.type("pot")
        pg.keyboard.press("Enter")
        check(pg.input_value("#hx-ex") == str(ex["Potisak s klupe"]), "pot and Enter did not pick")
        with pg.expect_navigation():
            pg.tap("#povijest-vjezbe button[type=submit]")
        pg.wait_for_load_state("networkidle")
        check(pg.url.endswith(f"/karton?vjezba={ex['Potisak s klupe']}#povijest-vjezbe"), f"Prikaži went to {pg.url}")
        check(pg.text_content("#povijest-vjezbe .hx-name") == "Potisak s klupe"
              and pg.text_content("#povijest-vjezbe .hx-max") == "Procjena maksimuma: 108 kg"
              and pg.input_value("#hx-ex-q") == "Potisak s klupe", "the history after Prikaži")
        check(pg.evaluate(OVERFLOW) == 0 and set(pg.evaluate(WIDER).values()) == {0},
              f"390px: overflow {pg.evaluate(OVERFLOW)}, wider {pg.evaluate(WIDER)}")
        problems += [f"390px {e}" for e in errors]
        ctx.close()

        ctx = browser.new_context(viewport={"width": 360, "height": 780}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(server + "/login"); pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); localStorage.setItem('qmt-phone', String(Date.now())); }")
        pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
        pg.goto(f"{server}/karton?vjezba={ex['Potisak s klupe']}"); pg.wait_for_load_state("networkidle")
        pg.evaluate("() => { qmtToggleForm('lim-docs'); qmtToggleForm('masa'); document.activeElement.blur(); }")
        check(pg.is_visible("#lim-docs form.le-edit") and pg.is_visible("#masa > form.le-edit"), "360px: the forms shut")
        check(pg.evaluate(OVERFLOW) == 0 and set(pg.evaluate(WIDER).values()) == {0},
              f"360px: overflow {pg.evaluate(OVERFLOW)}, wider {pg.evaluate(WIDER)}")
        problems += [f"360px {e}" for e in errors]
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


# ---------- the page's order and columns (25.11.2026) ----------

# The karton as it lies: the visible h2s' words in the page's order, each
# card's box (top and bottom on the page) and how much its content is wider
# than it, the diary's box (its .k-sec), the page's overflow.
LAYOUT = """() => {
  const vis = el => !!el && el.getClientRects().length > 0;
  const box = el => { const r = el.getBoundingClientRect();
    return {top: r.top + scrollY, bottom: r.bottom + scrollY, left: r.left, right: r.right, width: r.width}; };
  const cards = ['.upitnik', '#ogranicenja', '#masa', '#napredak', '.maxes', '#povijest-vjezbe', '.termini']
    .map(s => [s, document.querySelector(s)]).filter(([, el]) => vis(el));
  return {heads: [...document.querySelectorAll('main h2')].filter(vis).map(h => h.textContent.replace(/\\s+/g, ' ').trim()),
          cards: cards.map(([s, el]) => ({name: s, ...box(el), wide: el.scrollWidth - el.clientWidth})),
          diary: box(document.getElementById('osvrti').parentElement),
          overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}"""


def _lies_wrong(at: dict, heads: list[str], w: int) -> list[str]:
    """What is wrong with a karton as LAYOUT read it at w px (nothing: []):
    its headings not `heads`, an overflow, a card whose content is wider than
    it, the diary not under every card. Below 1000px a card whose left edge
    is not the diary's, or that is not under the one before; from 1000px
    the limitations and the weight, and the photos and the maxes, not each
    a row of two equal columns (one top, one bottom, one width, 20px
    apart), the upitnik block, the exercise's history (since 25.11.2026)
    or the termini not across both, a row not under the one before, the
    diary not as wide as the two columns."""
    out, got, diary = [], at["cards"], at["diary"]
    if at["heads"] != heads:
        out.append(f"the headings {at['heads']}")
    if at["overflow"]:
        out.append(f"the page overflows by {at['overflow']}px")
    out += [f"{c['name']}'s content is {c['wide']}px wider than it" for c in got if c["wide"] > 0]
    if any(diary["top"] < c["bottom"] - 1 for c in got):
        out.append(f"the diary ({diary['top']:.0f}) is not under every card")
    if w < 1000:                                         # one column: one left edge, each under the one before
        if any(abs(c["left"] - diary["left"]) > 1 for c in got):
            out.append(f"the left edges {[round(c['left']) for c in got]}, the diary's {diary['left']:.0f}")
        if any(b["top"] < a["bottom"] - 1 for a, b in zip(got, got[1:])):
            out.append(f"a card beside another: {[(c['name'], round(c['top'])) for c in got]}")
        return out
    named = {c["name"]: c for c in got}
    left, right = named["#ogranicenja"]["left"], named["#masa"]["right"]
    for a, b in ((named["#ogranicenja"], named["#masa"]), (named["#napredak"], named[".maxes"])):
        if (abs(a["top"] - b["top"]) > 1 or abs(a["bottom"] - b["bottom"]) > 1 or abs(a["width"] - b["width"]) > 1
                or abs(b["left"] - a["right"] - 20) > 1 or abs(a["left"] - left) > 1 or abs(b["right"] - right) > 1):
            out.append(f"{a['name']} and {b['name']} are not one row of two equal columns: {a}, {b}")
    for span in (".upitnik", "#povijest-vjezbe", ".termini"):
        if span in named and (abs(named[span]["left"] - left) > 1 or abs(named[span]["right"] - right) > 1):
            out.append(f"{span} does not span both columns: {named[span]}")
    rows = [[named[n] for n in row if n in named]
            for row in ((".upitnik",), ("#ogranicenja", "#masa"), ("#napredak", ".maxes"), ("#povijest-vjezbe",), (".termini",))]
    rows = [row for row in rows if row]
    if any(min(c["top"] for c in b) < max(c["bottom"] for c in a) - 1 for a, b in zip(rows, rows[1:])):
        out.append(f"a row is not under the one before: {[(c['name'], round(c['top'])) for c in got]}")
    if abs(diary["left"] - left) > 1 or abs(diary["right"] - right) > 1:
        out.append(f"the diary ({diary['left']:.0f}–{diary['right']:.0f}) is not the columns' width")
    return out


def test_the_karton_is_one_column_then_two_in_its_order(server):
    """The karton's order (25.11.2026, the owner: "Everything should be one
    above the other and the 'dnevnik treninga' should be last"): the
    upitnik block, "Ograničenja i bolovi", "Tjelesna kompozicija"
    ("Tjelesna masa" until the same day's later build), "Napredak —
    fotografije", "Procijenjeni maksimumi", "Povijest vježbe" (the same
    later build), "Nadolazeći termini" (not on a staff member's own),
    "Dnevnik treninga" last, read from the headings on the member's own
    karton, a staff member's own and the trainer's view of the member, at
    390 (touch), 999, 1000 and 1280px. Below 1000px one column: every
    card's left edge the diary's, each under the one before, none beside
    another. From 1000px (the owner: "if you have more room on the PC
    layout, you can use more columns") two equal columns: the upitnik
    block across both, the limitations beside the weight and the photos
    beside the maxes (a top edge shared, one width, one height, 20px
    apart), the history across both under them, and the termini across
    both, as they were before it; the diary under every card, as wide as
    the two columns. No card's content is wider than
    the card (fourteen weights, a document, a photo, the maxes, an
    exercise's history, a booking); the page never scrolls sideways."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    from qmt import upitnik
    seed_questions()
    ivan = make_user("ivan@test.local")
    trener = make_user("trener@test.local", is_trainer=True, plans=())
    client_for("ivan@test.local").post("/upitnik", data=filled_upitnik(), follow_redirects=False)
    ex = library("Potisak s klupe", "Zgibovi s vlastitom težinom tijela")
    today = config.today()
    for uid in (ivan, trener):
        for k in range(14):
            db.set_weight(uid, today - timedelta(days=3 * k), Decimal(80) + Decimal(k) / 10)
        db.add_training_log(uid, today - timedelta(days=2), 7, "", sets=[
            logged(ex["Potisak s klupe"], "Potisak s klupe", (6, 90)),
            logged(ex["Zgibovi s vlastitom težinom tijela"], "Zgibovi s vlastitom težinom tijela", (9, 0))])
        config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        name = f"napredak-{uid}-{today:%Y%m}-0123456789abcdef.jpg"
        Image.new("RGB", (600, 800), (70, 92, 112)).save(config.MEDIA_DIR / name, "JPEG")
        db.set_photo(uid, today.replace(day=1), name)
        db.add_limitation_file(uid, f"nalaz-{uid}-0123456789abcdef.pdf", "Nalaz MR koljena")
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) + timedelta(days=1), 60, 8, None)
    with db.session_scope() as s:
        s.add(Booking(user_id=ivan, session_id=sid))
    level = upitnik.LEVELS[db.get_onboarding(ivan).level]
    cards = ["Ograničenja i bolovi", "Tjelesna kompozicija", "Napredak — fotografije", "Procijenjeni maksimumi",
             "Povijest vježbe"]
    bench = f"?vjezba={ex['Potisak s klupe']}"                                  # the history shown, the card at its tallest
    views = (("ivan@test.local", "/karton" + bench, [level, *cards, "Nadolazeći termini", "Dnevnik treninga"]),
             ("trener@test.local", "/karton" + bench, [*cards, "Dnevnik treninga"]),
             ("trener@test.local", f"/karton/{ivan}", [level, *cards, "Nadolazeći termini", "Dnevnik treninga"]))
    problems: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for email, path, heads in views:
            for w in (390, 999, 1000, 1280):
                phone = w < 600
                ctx = browser.new_context(viewport={"width": w, "height": 900}, has_touch=phone, is_mobile=phone)
                pg = ctx.new_page()
                pg.goto(server + "/login")
                pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); localStorage.setItem('qmt-phone', String(Date.now())); }")
                pg.fill("main input[name=email]", email); pg.fill("main input[name=password]", "lozinka123")
                pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
                pg.goto(server + path); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
                at = pg.evaluate(LAYOUT)
                problems += [f"{email} {path} {w}px: {p}" for p in _lies_wrong(at, heads, w)]
                ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"


def test_an_exercise_takes_twenty_sets_on_a_phone(server):
    """At 390px, touch: in a training outside a termin, an exercise
    block's "+ serija" adds a row at a tap up to 20 (12 until 26.11.2026,
    the owner: "Lets increase the 12 sets to 20 sets limit."), then goes;
    every row's inputs 44px tall, the page never wider than the screen;
    Spremi stores the 20 sets. No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    ivan = make_user("ivan@test.local")
    ex = library(("Potisak s klupe", "prsa, šipka"))
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx, pg, errors = _phone(browser, server, "ivan@test.local")
        pg.goto(server + "/karton"); pg.wait_for_load_state("networkidle")
        form = "#trening-novi form.le-edit"
        pg.tap("#trening-novi > button.act")
        pg.select_option("#nt-effort", "7")
        pg.tap(f"{form} .xl-add")
        pg.keyboard.type("pot"); pg.keyboard.press("Enter")
        for _ in range(30):
            if not pg.is_visible(f"{form} .xb-add"):
                break
            pg.tap(f"{form} .xb-add")
        rows = pg.locator(f"{form} .xb tbody tr").count()
        heights = pg.evaluate(f"() => [...document.querySelectorAll('{form} .xb tbody input')].map(i => i.getBoundingClientRect().height)")
        check(rows == 20 and not pg.is_visible(f"{form} .xb-add"), f"+ serija stopped at {rows} rows")
        check(len(heights) == 40 and min(heights) >= 44, f"the inputs' heights: {sorted(set(heights))}")
        check(pg.evaluate(OVERFLOW) == 0, f"the karton overflows by {pg.evaluate(OVERFLOW)}px with 20 rows")
        for i in range(1, 21):
            pg.fill(f"{form} input[name=reps_0_{i}]", "5"); pg.fill(f"{form} input[name=kg_0_{i}]", "40")
        with pg.expect_navigation():
            pg.tap(f"{form} button[type=submit]")
        pg.wait_for_load_state("networkidle")
        logs = db.training_logs(ivan)
        check(len(logs) == 1 and logs[0].set_items[0]["exercise_id"] == ex["Potisak s klupe"]
              and logs[0].set_items[0]["sets"] == [{"reps": 5, "kg": 40.0}] * 20, "the 20 sets were not stored")
        problems += errors
        ctx.close()
        browser.close()
    print("\n".join(problems))
    assert not problems, f"{len(problems)} problems, listed above"
