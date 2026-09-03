"""Training-programme (treninzi) tests: authorization, upload, ordering."""

from __future__ import annotations

import io
import os

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import pytest
from fastapi.testclient import TestClient

from datetime import timedelta

from qmt import auth, config, db
from qmt.models import Base, User
from qmt.web.app import app

TODAY = config.today()

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)  # enough to be a non-empty "image"


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # media lands in a throwaway dir, never the real data/uploads
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
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
        # (the gates have their own tests). All-zero answers -> pocetna.
        import json

        from qmt import upitnik
        db.record_payment(u.id, "online")
        picked = {q["key"]: 0 for q in upitnik.QUESTIONS}
        score, level = upitnik.score_answers(picked)
        db.save_onboarding(u.id, json.dumps(picked), score, level, goal)
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
    db.add_item(pid, "Trenerova vježba", "5 × 5", None, None)
    db.ensure_online_skeletons()
    assert [i.title for i in db.get_program(pid).items] == ["Trenerova vježba"]


def test_clients_cannot_create_or_edit():
    ct, ivan, _ = trainer_with_clients()
    pid = db.create_program("T", None, "pocetna", "cijelo")
    ci = client_for("ivan@test.local")
    assert ci.post("/treninzi", data={"title": "X", "level": "pocetna",
                                      "goal": "cijelo"}).status_code == 403
    assert ci.get(f"/treninzi/{pid}/uredi").status_code == 403
    assert ci.post(f"/treninzi/{pid}/items", data={"title": "X"}).status_code == 403
    assert ci.post(f"/treninzi/{pid}/delete").status_code == 403


def test_item_upload_and_media_gating():
    ct, ivan, ana = trainer_with_clients()
    pid = db.create_program("S medijem", None, "pocetna", "cijelo")   # ivan's combo
    r = ct.post(f"/treninzi/{pid}/items",
                data={"title": "Čučanj", "body": "3x10"},
                files={"media": ("cucanj.png", io.BytesIO(PNG), "image/png")},
                follow_redirects=False)
    assert r.status_code == 303 and "error" not in r.headers["location"]
    p = db.get_program(pid)
    name = p.items[0].media_name
    assert name and p.items[0].media_kind == "img"
    assert (config.MEDIA_DIR / name).is_file()

    assert client_for("ivan@test.local").get(f"/media/{name}").status_code == 200
    assert client_for("ana@test.local").get(f"/media/{name}").status_code == 403
    anon = TestClient(app).get(f"/media/{name}", follow_redirects=False)
    assert anon.status_code == 303 and "/login" in anon.headers["location"]


def test_media_rejects_bad_type_and_traversal():
    ct, ivan, _ = trainer_with_clients()
    pid = db.create_program("T", None)
    r = ct.post(f"/treninzi/{pid}/items",
                data={"title": "X"},
                files={"media": ("napad.exe", io.BytesIO(b"MZ..."), "application/x-msdownload")},
                follow_redirects=False)
    assert "error=" in r.headers["location"]               # refused, message shown
    assert db.get_program(pid).items == []                 # nothing half-created
    assert ct.get("/media/..%2f..%2fetc%2fpasswd").status_code == 404


def test_item_reorder_and_delete_keep_positions_dense():
    ct, ivan, _ = trainer_with_clients()
    pid = db.create_program("T", None)
    for name in ("A", "B", "C"):
        db.add_item(pid, name, None, None, None)
    a, b, c = [i.id for i in db.get_program(pid).items]

    db.move_item(c, "up")                                   # A, C, B
    assert [i.title for i in db.get_program(pid).items] == ["A", "C", "B"]
    db.move_item(a, "up")                                   # top stays put
    assert [i.title for i in db.get_program(pid).items] == ["A", "C", "B"]

    db.delete_item(c)
    items = db.get_program(pid).items
    assert [i.title for i in items] == ["A", "B"]
    assert [i.position for i in items] == [1, 2]            # gap closed


def test_delete_program_removes_media_files():
    ct, ivan, _ = trainer_with_clients()
    pid = db.create_program("T", None)
    ct.post(f"/treninzi/{pid}/items", data={"title": "V"},
            files={"media": ("v.png", io.BytesIO(PNG), "image/png")})
    name = db.get_program(pid).items[0].media_name
    assert (config.MEDIA_DIR / name).is_file()
    ct.post(f"/treninzi/{pid}/delete")
    assert db.get_program(pid) is None
    assert not (config.MEDIA_DIR / name).is_file()          # no orphaned upload


def test_nutricionizam_links_to_mojimakrosi():
    make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    page = c.get("/nutricionizam").text
    assert "MojiMakrosi" in page and config.MOJIMAKROSI_URL in page
