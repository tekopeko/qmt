"""In-place editable copy: src/qmt/copy.py (the slots and their caps),
POST /copy/{key} (the save), _copy.html (the macros), the editor in base.html,
the landing's announcements (rows since 18.10.2026: their fields edited
through virtual keys on the same routes, "+ Dodaj najavu" and "Obriši
najavu", the cap of eight, and the migration that made the two old sets of
slots rows), their photos (POST /copy/{key}/slika, GET /slika/{name}), the
reference prices (the price.<plan>.* and addon.* slots), and the migration
that turned the offer cards' bullets into lists.

The browser half is the net under the texts. Their design limits were lifted
on 16.10.2026 (src/qmt/copy.py): it starts the app in a thread, fills every
slot with a long text — once with words, once with one unbreakable word —
gives the first announcement's text three lines and a photo behind it, and
measures the pages at four widths.
Nothing may overflow or be cut, and the cards' prices stay level. It proves
no design; that pass comes once the copy is final. On the way it walks the
landing's rows of cards, the announcements' among them (one card per view;
they move on by themselves, on a phone and on a desktop, and hold still when
they must), the editor's switch and photo pills, adding and deleting a card, and the
install banner's week between asks.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import re
import threading
import time
from datetime import date
from html import unescape

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from qmt import auth, config, copy, db, storage
from qmt.models import PLAN_TYPES, Base, User
from qmt.web.app import addon_amounts, app, reference_prices

PAGES = ("/", "/moja-clanarina", "/prehrana")  # every page that has editable text


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # Photos land in a throwaway dir, never the real data/uploads, and never
    # the real R2 bucket: a developer's .env may carry live R2_* keys (as in
    # tests/test_programs.py). The browser test's server is a thread of this
    # process, and storage reads config at every call: it sees these too.
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "")
    yield


def make_user(email: str, is_trainer: bool = False, plans: tuple[str, ...] = ()) -> int:
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    db.update_profile(u.id, email.split("@")[0], "Test", date(1990, 1, 1), "")
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


# ---------- the route ----------

def test_only_a_trainer_saves_and_the_limit_and_reset_hold():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    key, slot = "hero.kicker", copy.SLOTS["hero.kicker"]

    assert TestClient(app).post(f"/copy/{key}", data={"text": "x"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{key}", data={"text": "x"}).status_code == 403

    t = client_for("trener@test.local")
    r = t.post(f"/copy/{key}", data={"text": "  Novi   uvodni\n tekst.  "})   # spaces collapse, the line break stays
    assert r.status_code == 200 and r.json() == {"ok": True, "text": "Novi uvodni\ntekst.", "default": False}
    page = TestClient(app).get("/").text                                    # everyone reads the edit, in a .t span
    assert '<span class="t">Novi uvodni\ntekst.</span>' in page             # (span.t prints the line break)
    assert 'data-copy="hero.kicker"' not in page                            # ...without editor markup
    assert (f'<span class="ed t" data-copy="{key}" data-max="2000" data-label="{slot.label}">'
            "Novi uvodni\ntekst.</span>") in t.get("/").text                 # the editor has it
    r = t.post(f"/copy/{key}", data={"text": " a \n\n\n\n b "})              # one empty line at most
    assert r.json()["text"] == "a\n\nb" and db.copy_texts()[key] == "a\n\nb"

    r = t.post(f"/copy/{key}", data={"text": "x" * 2001})                   # the cap: against a stray paste
    assert r.status_code == 400 and r.json()["error"] == "Najviše 2000 znakova — ovo ih ima 2001."
    assert t.post(f"/copy/{key}", data={"text": "x" * 2000}).status_code == 200
    assert t.post("/copy/no.such.slot", data={"text": "x"}).status_code == 404

    for blank in ("   ", " \n \n\n "):                                       # empty = back to the default,
        t.post(f"/copy/{key}", data={"text": "Nešto."})                     # line breaks alone are empty too
        r = t.post(f"/copy/{key}", data={"text": blank})
        assert r.json() == {"ok": True, "text": slot.default, "default": True}
    assert slot.default in TestClient(app).get("/").text and db.copy_texts() == {}

    t.post(f"/copy/{key}", data={"text": "Opet novi."})                     # reset=1 does the same
    r = t.post(f"/copy/{key}", data={"text": "ignoriran", "reset": "1"})
    assert r.json() == {"ok": True, "text": slot.default, "default": True} and db.copy_texts() == {}


def test_a_list_slot_takes_edits_additions_and_removals_within_its_limits():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    key, slot = "offer.dvorana.points", copy.SLOTS["offer.dvorana.points"]
    d = list(slot.default)

    assert TestClient(app).post(f"/copy/{key}", data={"text": "x", "index": "0"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{key}", data={"text": "x", "index": "0"}).status_code == 403

    t = client_for("trener@test.local")
    def post(**data):
        return t.post(f"/copy/{key}", data=data)

    r = post(text="  Grupe   do 8 ", index="1")                             # edit one item
    assert r.status_code == 200 and r.json() == {"ok": True, "items": [d[0], "Grupe do 8", d[2]], "default": False}
    r = post(text="Četvrta stavka", index="3")                              # index == count appends
    assert r.json()["items"] == [d[0], "Grupe do 8", d[2], "Četvrta stavka"]
    assert json.loads(db.copy_texts()[key]) == r.json()["items"]            # one row, a JSON array
    page = TestClient(app).get("/").text                                    # everyone reads it...
    assert "Četvrta stavka" in page and f'data-copy="{key}"' not in page and 'class="ed-x"' not in page
    page = t.get("/").text                                                  # ...the editor gets a span per item
    assert page.count(f'data-copy="{key}"') == 4 and 'data-index="3"' in page

    r = post(text="", index="0")                                            # empty text removes the item
    assert r.json() == {"ok": True, "items": ["Grupe do 8", d[2], "Četvrta stavka"], "default": False}
    assert post(text="").json()["items"] == ["Grupe do 8", d[2], "Četvrta stavka"]    # no index: nothing to remove
    assert post(text="  ", index="3").json()["items"] == ["Grupe do 8", d[2], "Četvrta stavka"]  # nothing at n
    assert post(text="x").status_code == 400                                # a text needs an index
    assert post(text="x", index="9").status_code == 400                     # past the end
    assert post(text="x", index="-1").status_code == 400
    assert post(text="x", index="dva").status_code == 400

    for n in range(3, 12):                                                  # up to twelve...
        assert post(text=f"Stavka {n}", index=str(n)).status_code == 200
    r = post(text="Trinaesta", index="12")                                  # ...and not one more
    assert r.status_code == 400 and r.json()["error"] == "Najviše 12 stavki."
    r = post(text="x" * 2001, index="0")
    assert r.status_code == 400 and r.json()["error"] == "Najviše 2000 znakova — ovo ih ima 2001."
    assert post(text="x" * 2000, index="0").status_code == 200
    assert len(json.loads(db.copy_texts()[key])) == 12
    r = post(text=" Prvi red \n\n\n drugi red ", index="1")                # an item keeps its line breaks too
    assert r.json()["items"][1] == "Prvi red\n\ndrugi red"
    assert '<li><span class="t">Prvi red\n\ndrugi red</span></li>' in TestClient(app).get("/").text

    r = post(text="ignoriran", reset="1")                                   # Zadano: the whole default list
    assert r.json() == {"ok": True, "items": d, "default": True} and key not in db.copy_texts()

    for _ in d:                                                             # an emptied list stays empty...
        post(text="", index="0")
    assert json.loads(db.copy_texts()[key]) == []
    page = TestClient(app).get("/").text                                    # ...and a visitor sees no bullets
    assert d[1] not in page and d[2] not in page and "Grupni treninzi u Dubravi." in page
    assert 'data-list="offer.dvorana.points"' in t.get("/").text            # the editor can still add one


# ---------- the announcements: rows, edited through virtual keys ----------

def examples() -> list[int]:
    """The two example cards, as the migration leaves a database where
    nobody edited them (copy.ANNOUNCEMENT_EXAMPLES): their ids, in order."""
    ids = []
    for example in copy.ANNOUNCEMENT_EXAMPLES:
        a = db.add_announcement(None)
        for column, text in example.items():
            db.set_announcement_field(a.id, column, text, None)
        ids.append(a.id)
    return ids


def test_an_announcements_texts_are_edited_in_place_through_their_virtual_keys():
    make_user("ivan@test.local"); uid = make_user("trener@test.local", is_trainer=True)
    one, two = examples()
    key = f"aktualno.{one}.title"
    assert TestClient(app).post(f"/copy/{key}", data={"text": "x"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{key}", data={"text": "x"}).status_code == 403
    assert db.announcement(one).title == "Treninzi za penziće"

    t = client_for("trener@test.local")
    r = t.post(f"/copy/{key}", data={"text": "  Treninzi   za\n penziće  "})   # cleaned as a slot's text is
    assert r.status_code == 200 and r.json() == {"ok": True, "text": "Treninzi za\npenziće", "default": False}
    assert db.announcement(one).title == "Treninzi za\npenziće" and db.announcement(one).updated_by == uid
    page = TestClient(app).get("/").text                                    # everyone reads it, in a .t span
    assert '<h2><span class="t">Treninzi za\npenziće</span></h2>' in page and f'data-copy="{key}"' not in page
    assert (f'<h2><span class="ed t" data-copy="{key}" data-max="2000" data-label="Najava 1: naslov">'
            "Treninzi za\npenziće</span></h2>") in t.get("/").text          # the editor's span names its card
    for field, column in (("tag", "tag"), ("when", "when_text"), ("text", "body"), ("cta", "cta")):
        r = t.post(f"/copy/aktualno.{two}.{field}", data={"text": f"Novo: {field}"})
        assert r.json() == {"ok": True, "text": f"Novo: {field}", "default": False}, field
        assert getattr(db.announcement(two), column) == f"Novo: {field}", field
    page = t.get("/").text
    for field, word in (("tag", "oznaka"), ("when", "termin"), ("text", "tekst"), ("cta", "gumb")):
        assert f'data-copy="aktualno.{two}.{field}" data-max="2000" data-label="Najava 2: {word}">Novo: {field}</span>' in page

    r = t.post(f"/copy/{key}", data={"text": "x" * 2001})                   # the cap, as a slot's
    assert r.status_code == 400 and r.json()["error"] == "Najviše 2000 znakova — ovo ih ima 2001."
    assert t.post(f"/copy/{key}", data={"text": "x" * 2000}).status_code == 200
    for blank in ("   ", " \n \n\n "):                                       # empty: the new card's placeholder,
        t.post(f"/copy/{key}", data={"text": "Nešto."})                     # as an emptied slot's default
        r = t.post(f"/copy/{key}", data={"text": blank})
        assert r.json() == {"ok": True, "text": "Nova najava", "default": True} and db.announcement(one).title == "Nova najava"
    t.post(f"/copy/{key}", data={"text": "Opet."})                          # reset=1 (Zadano) does the same
    r = t.post(f"/copy/{key}", data={"text": "ignoriran", "reset": "1"})
    assert r.json() == {"ok": True, "text": "Nova najava", "default": True}

    for bad in ("aktualno.99.title", f"aktualno.{one}.naslov", f"aktualno.{one}.when_text", f"aktualno.{one}",
                f"aktualno.{one}.title.x", "aktualno.x.title", f"aktualno.0{one}.title", "aktualno.1234567890.title",
                "event1.title"):                                            # no such card, field or slot
        assert t.post(f"/copy/{bad}", data={"text": "x"}).status_code == 404, bad
    assert db.copy_texts() == {}                                            # none of it lands in site_copy


def test_an_announcement_is_switched_on_and_off_and_takes_nothing_else():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    one, _ = examples()
    key = f"aktualno.{one}.show"
    assert TestClient(app).post(f"/copy/{key}", data={"text": "off"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{key}", data={"text": "off"}).status_code == 403
    assert db.announcement(one).shown is True

    t = client_for("trener@test.local")
    r = t.post(f"/copy/{key}", data={"text": "off"})                        # answered as a FlagSlot is
    assert r.status_code == 200 and r.json() == {"ok": True, "on": False, "default": False}
    assert db.announcement(one).shown is False
    r = t.post(f"/copy/{key}", data={"text": "on"})
    assert r.json() == {"ok": True, "on": True, "default": False} and db.announcement(one).shown is True
    for bad in ("maybe", "", " off", "OFF", "1"):                          # exactly "on" or "off"
        r = t.post(f"/copy/{key}", data={"text": bad})
        assert r.status_code == 400 and r.json() == {"ok": False, "error": "Nepoznata vrijednost."}, bad
    assert db.announcement(one).shown is True                               # a refused value changes nothing
    t.post(f"/copy/{key}", data={"text": "off"})                            # reset=1: on again
    r = t.post(f"/copy/{key}", data={"text": "off", "reset": "1"})
    assert r.json() == {"ok": True, "on": True, "default": True} and db.announcement(one).shown is True
    assert db.copy_texts() == {}


def test_the_announcements_show_what_is_on_and_the_editor_keeps_what_is_off():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    one, two = examples()
    first, second = (example["title"] for example in copy.ANNOUNCEMENT_EXAMPLES)
    page = TestClient(app).get("/").text                                    # both, in the hero:
    assert 'id="aktualno"' in page and first in page and second in page    # under the headline, above the photo
    assert page.index("<h1") < page.index('id="aktualno"') < page.index('class="stage"')
    assert page.count('<a class="act" href="/#kontakt"><span class="t">Javi nam se</span></a>') == 2
    assert '<div class="evs swipe-row" id="aktualno" data-auto="5000">' in page          # a phone's swipe row,
    assert '<div class="dots" role="group" aria-label="Aktualno" hidden></div>' in page  # its dots the script's

    db.set_announcement_shown(two, False)                                   # one off: gone from a visitor's page
    for c in (TestClient(app), client_for("ivan@test.local")):              # and a client's, the one left alone
        page = c.get("/").text
        assert first in page and second not in page and 'class="evs swipe-row single"' in page
        assert 'is-off"' not in page
    page = client_for("trener@test.local").get("/").text                    # the editor has it, marked off
    assert second in page and 'data-flag-group' in page and 'class="evs swipe-row single"' in page
    assert f'<article class="card event is-off" data-flag="aktualno.{two}.show" data-image="aktualno.{two}.image">' in page

    db.set_announcement_shown(one, False)                                   # both off: not even their box
    page = TestClient(app).get("/").text
    assert 'id="aktualno"' not in page and first not in page and second not in page and 'aria-label="Aktualno"' not in page
    page = client_for("trener@test.local").get("/").text                    # the editor keeps both, and the box
    assert '<div class="evs swipe-row is-off" id="aktualno"' in page and first in page and second in page
    assert page.count('<article class="card event is-off" data-flag="') == 2
    assert page.count('aria-pressed="false">Skriveno</button>') == 2


ADD = '<form method="post" action="/aktualno/nova" class="ed-add-ann"><button type="submit" class="act">+ Dodaj najavu</button></form>'
DROP = '<button type="submit" aria-label="Obriši najavu">Obriši najavu</button></form>'


def test_a_visitor_gets_the_shown_cards_in_order_and_only_the_editor_adds_and_deletes():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    ids = [db.add_announcement(None).id for _ in range(3)]
    for i, title in zip(ids, ("Prva najava", "Druga najava", "Treća najava")):
        db.set_announcement_field(i, "title", title, None)
    db.set_announcement_shown(ids[1], False)
    for c in (TestClient(app), client_for("ivan@test.local")):
        page = c.get("/").text                                              # the shown ones, in creation order
        assert "Druga najava" not in page and page.index("Prva najava") < page.index("Treća najava")
        assert page.count('<article class="card event">') == 2
        for mark in (ADD, DROP, 'action="/aktualno/', 'class="ed-ann-x"', 'class="ed-add-ann"'):
            assert mark not in page, mark
    page = client_for("trener@test.local").get("/").text                    # the editor: every one, in order,
    assert page.index("Prva najava") < page.index("Druga najava") < page.index("Treća najava")
    assert page.count(DROP) == 3 and page.count(ADD) == 1                   # each with its "Obriši najavu"
    for n, i in enumerate(ids, start=1):
        assert f'<form method="post" action="/aktualno/{i}/obrisi" class="ed-ann-x">{DROP}' in page
        assert f'data-label="Najava {n}: naslov">' in page                  # the bar names a card by its place
    # "+ Dodaj najavu" after the row's dots, before the photo
    assert page.index('<div class="dots" role="group" aria-label="Aktualno" hidden></div>') < page.index(ADD) < page.index('class="stage"')


def test_two_quick_adds_never_pass_the_cap():
    """Eight is the cap even when taps race: with six cards, six adds at
    once land two (the count and the next position are read under a lock),
    and no position is taken twice."""
    for _ in range(6):
        db.add_announcement(None)
    landed = []
    threads = [threading.Thread(target=lambda: landed.append(db.add_announcement(None) is not None)) for _ in range(6)]
    for th in threads: th.start()
    for th in threads: th.join()
    assert sorted(landed) == [False] * 4 + [True] * 2
    assert [a.position for a in db.announcements(all=True)] == list(range(1, 9))


# ---------- the announcements' photos ----------

UNSUPPORTED = {"ok": False, "error": "Nepodržan format — dozvoljeno: jpg, png, webp."}


def picture(w: int, h: int, fmt: str = "JPEG", orientation: int | None = None, mode: str = "RGB") -> bytes:
    """A real image, made here: Pillow has to open what is posted. A JPEG
    carries EXIF, a camera's make and, when given, the orientation a phone
    stores instead of turning the pixels."""
    im, buf, extra = Image.new(mode, (w, h), (180, 60, 40, 128)[:len(mode)]), io.BytesIO(), {}
    if fmt == "JPEG":
        exif = Image.Exif()
        exif[0x010F] = "QMT testna kamera"                                 # Make
        if orientation:
            exif[0x0112] = orientation                                      # Orientation
        extra["exif"] = exif.tobytes()
    im.save(buf, fmt, **extra)
    return buf.getvalue()


def stored(r, ann_id: int) -> str:
    """The name a good upload to card `ann_id` answers with."""
    d = r.json()
    m = re.fullmatch(rf"/slika/(aktualno-{ann_id}-[0-9a-f]{{16}}\.jpg)", d.get("url") or "")
    assert r.status_code == 200 and d["ok"] is True and m, d
    return m.group(1)


def test_a_photo_goes_up_only_from_an_editor_and_only_as_a_real_image():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    one, _ = examples(); url = f"/copy/aktualno.{one}.image/slika"
    good = {"slika": ("foto.jpg", picture(300, 200), "image/jpeg")}

    r = TestClient(app).post(url, files=good)
    assert r.status_code == 401 and r.json()["ok"] is False
    assert client_for("ivan@test.local").post(url, files=good).status_code == 403

    t = client_for("trener@test.local")
    for unknown in ("no.such.slot", "aktualno.99.image", f"aktualno.{one}.slika", "event1.image"):
        assert t.post(f"/copy/{unknown}/slika", files=good).status_code == 404, unknown
    for text in (f"aktualno.{one}.title", f"aktualno.{one}.show", "hero.kicker"):   # a text, or the switch,
        r = t.post(f"/copy/{text}/slika", files=good)                              # takes no photo
        assert r.status_code == 400 and r.json() == {"ok": False, "error": "Ovdje ne ide slika."}, text
    for name, data in (("foto.txt", b"samo tekst"), ("foto.gif", picture(30, 20, "GIF")),   # by the name,
                       ("foto.jpg", b"ovo nije slika"), ("foto.jpg", picture(30, 20, "GIF")),  # and by what is in it:
                       ("foto.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64), ("foto.jpg", b"")):  # Pillow must open it
        r = t.post(url, files={"slika": (name, data, "image/jpeg")})
        assert r.status_code == 400 and r.json() == UNSUPPORTED, name
    r = t.post(url)                                                         # no file at all
    assert r.status_code == 400 and r.json() == UNSUPPORTED
    r = t.post(url, files={"slika": ("velika.jpg", b"\0" * (16 * 1024 * 1024), "image/jpeg")})
    assert r.status_code == 400 and r.json() == {"ok": False, "error": "Slika je veća od 15 MB."}
    assert db.announcement(one).image is None                               # nothing recorded, nothing stored
    assert not config.MEDIA_DIR.exists() or not any(config.MEDIA_DIR.iterdir())


def test_a_photo_is_stored_upright_small_and_bare_and_its_card_shows_it_to_everyone():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    one, two = examples(); t = client_for("trener@test.local")
    # a phone's photo, its pixels on their side and EXIF orientation 6 to turn them
    name = stored(t.post(f"/copy/aktualno.{one}.image/slika",
                         files={"slika": ("IMG_0001.JPG", picture(2400, 1600, orientation=6), "image/jpeg")}), one)
    path = config.MEDIA_DIR / name
    assert db.announcement(one).image == name and path.is_file()
    with Image.open(path) as im:
        assert im.format == "JPEG" and im.size == (1067, 1600)             # upright, its long side 1600
        assert im.info.get("progressive") and not im.getexif() and "exif" not in im.info   # no camera, no place

    for c in (TestClient(app), client_for("ivan@test.local")):             # a visitor and a client: card 1 on the photo
        page = c.get("/").text
        assert re.search(r'<article class="card event has-img" data-photo>\s*<img class="bg" src="/slika/'
                         + re.escape(name) + r'" alt="" loading="eager" decoding="async">\s*<span class="tag">', page)
        assert page.count('class="card event has-img"') == 1 and page.count('<article class="card event">') == 1
        for mark in ("data-image", 'class="ed-img"', 'class="ed-img-x"', 'id="edImgFile"'):
            assert mark not in page, mark
    page = t.get("/").text                                                  # the editor: both cards take a photo
    assert f'<article class="card event has-img" data-photo data-flag="aktualno.{one}.show" data-image="aktualno.{one}.image">' in page
    assert f'<article class="card event" data-flag="aktualno.{two}.show" data-image="aktualno.{two}.image">' in page
    assert re.search(rf'<button type="button" class="ed-img" data-copy="aktualno\.{one}\.image" data-label="Najava 1: slika">'
                     r'Promijeni sliku</button>\s*<button type="button" class="ed-img-x" aria-label="Ukloni sliku" '
                     rf'data-copy="aktualno\.{one}\.image">Ukloni sliku</button>', page)
    assert (f'<button type="button" class="ed-img" data-copy="aktualno.{two}.image" data-label="Najava 2: slika">'
            'Dodaj sliku</button>') in page
    assert page.count('class="ed-img-x"') == 1 and page.count('id="edImgFile"') == 1

    r = TestClient(app).get(f"/slika/{name}")                              # anyone gets it, to keep for a year
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content == path.read_bytes()
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    db.set_announcement_shown(one, False)                                   # a hidden card's too: its editor sees it
    assert TestClient(app).get(f"/slika/{name}").status_code == 200
    (config.MEDIA_DIR / "3f9a1c2b4d5e6f70.jpg").write_bytes(path.read_bytes())   # a programme's media: on no card
    for other in ("nema.jpg", "3f9a1c2b4d5e6f70.jpg", "../x", "..%2Fx", "..jpg"):
        assert TestClient(app).get(f"/slika/{other}").status_code == 404, other


def test_a_new_photo_replaces_the_old_and_ukloni_takes_photo_and_row():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    one, _ = examples(); t = client_for("trener@test.local"); key = f"aktualno.{one}.image"
    names = [stored(t.post(f"/copy/{key}/slika", files={"slika": (f, data, kind)}), one) for f, data, kind in (
        ("prva.jpeg", picture(2400, 1600), "image/jpeg"),
        ("druga.webp", picture(800, 600, "WEBP"), "image/webp"),
        ("treca.png", picture(300, 200, "PNG", mode="RGBA"), "image/png"))]   # small, with transparency
    assert len(set(names)) == 3 and db.announcement(one).image == names[2]
    assert [n for n in names if (config.MEDIA_DIR / n).exists()] == names[2:]   # each one replaced the one before
    assert [TestClient(app).get(f"/slika/{n}").status_code for n in names] == [404, 404, 200]   # nor is it served
    with Image.open(config.MEDIA_DIR / names[2]) as im:
        assert im.format == "JPEG" and im.mode == "RGB" and im.size == (300, 200)   # a JPEG, never enlarged

    r = t.post(f"/copy/{key}", data={"text": names[2]})                     # no text ever lands on a card's photo
    assert r.status_code == 400 and r.json() == {"ok": False, "error": f"Sliku šalje /copy/{key}/slika."}
    assert TestClient(app).post(f"/copy/{key}", data={"reset": "1"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{key}", data={"reset": "1"}).status_code == 403
    assert db.announcement(one).image == names[2] and (config.MEDIA_DIR / names[2]).is_file()

    r = t.post(f"/copy/{key}", data={"reset": "1"})                         # Ukloni sliku: the name and the file go
    assert r.status_code == 200 and r.json() == {"ok": True, "url": None, "default": True}
    assert db.announcement(one).image is None and not any(config.MEDIA_DIR.iterdir())
    page = TestClient(app).get("/").text                                    # and the card is plain again
    assert 'class="card event has-img"' not in page and "/slika/" not in page
    assert page.count('<article class="card event">') == 2
    page = t.get("/").text
    assert 'data-label="Najava 1: slika">Dodaj sliku</button>' in page and 'class="ed-img-x"' not in page
    assert t.post(f"/copy/{key}", data={"reset": "1"}).json() == {"ok": True, "url": None, "default": True}   # none: the same

    with pytest.raises(ValueError):                                         # a name that is a path is no photo
        db.set_announcement_image(one, "../../.env")
    assert db.announcement(one).image is None


def test_a_photo_sent_for_a_card_deleted_meanwhile_is_not_kept(monkeypatch):
    """The card is deleted while its photo goes up (stored, not yet
    recorded): the answer is 404 and the new file goes too, so nothing is
    left in storage that no card names."""
    make_user("trener@test.local", is_trainer=True)
    one, _ = examples(); t = client_for("trener@test.local")
    save = storage.save

    def save_then_delete(name, local_path, content_type):
        save(name, local_path, content_type)
        db.delete_announcement(one)
    monkeypatch.setattr(storage, "save", save_then_delete)
    r = t.post(f"/copy/aktualno.{one}.image/slika", files={"slika": ("foto.jpg", picture(300, 200), "image/jpeg")})
    assert r.status_code == 404 and r.json() == {"ok": False, "error": "Nepoznat tekst."}
    assert db.announcement(one) is None and not any(config.MEDIA_DIR.iterdir())


def test_the_editor_adds_cards_up_to_eight_and_deletes_them_with_their_photos():
    make_user("ivan@test.local"); uid = make_user("trener@test.local", is_trainer=True)
    for path in ("/aktualno/nova", "/aktualno/1/obrisi"):                  # a guest logs in first; a client may not
        r = TestClient(app).post(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", path
        assert client_for("ivan@test.local").post(path, follow_redirects=False).status_code == 403, path
    assert db.announcements(all=True) == []

    t = client_for("trener@test.local")                                     # none at all: the editor's box is
    box = t.get("/").text.split('id="aktualno"')[1].split('class="stage"')[0]   # empty but for "+ Dodaj najavu"
    assert "<article" not in box and ADD in box
    assert 'id="aktualno"' not in TestClient(app).get("/").text            # a visitor gets nothing

    for _ in range(8):
        r = t.post("/aktualno/nova", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/#aktualno"
    cards = db.announcements(all=True)
    assert [a.position for a in cards] == list(range(1, 9))                 # in creation order
    for a in cards:                                                         # the placeholders, shown, no photo
        assert {column: getattr(a, column) for column in copy.ANNOUNCEMENT_BLANK} == copy.ANNOUNCEMENT_BLANK
        assert a.shown and a.image is None and a.updated_by == uid
    assert TestClient(app).get("/").text.count('<article class="card event">') == 8
    page = t.get("/").text
    assert ADD not in page and page.count(DROP) == 8                        # full: no "+ Dodaj najavu"
    r = t.post("/aktualno/nova", follow_redirects=False)                    # a ninth is refused, and he is told
    assert r.status_code == 303 and r.headers["location"] == "/?error=Najvi%C5%A1e+8+najava.#aktualno"
    assert len(db.announcements(all=True)) == 8
    assert '<span>Najviše 8 najava.</span>' in t.get(r.headers["location"]).text

    first = cards[0]                                                        # one with a photo
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    photo = config.MEDIA_DIR / f"aktualno-{first.id}-0123456789abcdef.jpg"
    photo.write_bytes(picture(300, 200))
    db.set_announcement_image(first.id, photo.name)
    assert client_for("ivan@test.local").post(f"/aktualno/{first.id}/obrisi", follow_redirects=False).status_code == 403
    assert db.announcement(first.id) is not None and photo.is_file()
    r = t.post(f"/aktualno/{first.id}/obrisi", follow_redirects=False)      # Obriši najavu: the card, then its photo
    assert r.status_code == 303 and r.headers["location"] == "/#aktualno"
    assert db.announcement(first.id) is None and not photo.exists()
    assert TestClient(app).get(f"/slika/{photo.name}").status_code == 404
    r = t.post(f"/aktualno/{first.id}/obrisi", follow_redirects=False)      # gone already: nothing to do
    assert r.status_code == 303 and r.headers["location"] == "/#aktualno" and len(db.announcements(all=True)) == 7
    assert ADD in t.get("/").text                                           # room again,
    t.post("/aktualno/nova")                                                # and a new card comes last
    assert [a.position for a in db.announcements(all=True)] == list(range(2, 10))


def _migration(file: str):
    path = pathlib.Path(__file__).parents[1] / "alembic" / "versions" / file
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def test_the_migration_turns_the_two_announcement_slots_into_rows():
    """b48179fcf538: the event1.* / event2.* rows of site_copy become the
    first two announcements, what was edited where it was, else the old
    defaults (its own copy, which must agree with copy.ANNOUNCEMENT_EXAMPLES);
    the switch and the photo carried over; the event rows gone. And back."""
    mig = _migration("b48179fcf538_announcements.py"); uid = make_user("trener@test.local", is_trainer=True)
    with db.engine.begin() as conn:                                         # nobody edited them: the two examples
        mig.fold_events(conn)
    cards = db.announcements()
    assert [{column: getattr(a, column) for column in copy.ANNOUNCEMENT_BLANK} for a in cards] == list(copy.ANNOUNCEMENT_EXAMPLES)
    assert [(a.position, a.shown, a.image, a.updated_by) for a in cards] == [(1, True, None, None), (2, True, None, None)]
    for a in cards:
        db.delete_announcement(a.id)

    for key, text in [("event1.title", "Treninzi za umirovljenike"), ("event1.show", "off"),
                      ("event1.image", "aktualno-1-0123456789abcdef.jpg"),
                      ("event2.cta", "Prijavi se"), ("event2.show", "on"), ("event2.image", "../../.env"),
                      ("hero.kicker", "Ostaje kakav jest.")]:
        db.set_copy(key, text, uid)
    with db.engine.begin() as conn:
        mig.fold_events(conn)
    one, two = db.announcements(all=True)
    assert {column: getattr(one, column) for column in copy.ANNOUNCEMENT_BLANK} == {
        **copy.ANNOUNCEMENT_EXAMPLES[0], "title": "Treninzi za umirovljenike"}
    assert (one.position, one.shown, one.image, one.updated_by) == (1, False, "aktualno-1-0123456789abcdef.jpg", uid)
    assert {column: getattr(two, column) for column in copy.ANNOUNCEMENT_BLANK} == {**copy.ANNOUNCEMENT_EXAMPLES[1], "cta": "Prijavi se"}
    assert (two.position, two.shown, two.image) == (2, True, None)          # a path is no photo
    assert db.copy_texts() == {"hero.kicker": "Ostaje kakav jest."}         # the event rows gone, the rest kept
    page = TestClient(app).get("/").text                                    # and the page reads the rows
    assert "Prijavi se" in page and "Treninzi za umirovljenike" not in page and 'data-photo>' not in page

    with db.engine.begin() as conn:                                         # the way back: what differs from the defaults
        mig.unfold_events(conn)
    assert db.copy_texts() == {"hero.kicker": "Ostaje kakav jest.", "event1.title": "Treninzi za umirovljenike",
                               "event1.show": "off", "event1.image": "aktualno-1-0123456789abcdef.jpg",
                               "event2.cta": "Prijavi se"}


def test_the_migration_folds_the_old_bullet_slots_into_lists():
    mig = _migration("1b09c249c2c6_offer_points_lists.py"); uid = make_user("trener@test.local", is_trainer=True)
    for key, text in [("offer.online.p1", "Prva"), ("offer.online.p2", "Druga"), ("offer.online.p3", "Treća"),
                      ("offer.individualno.p2", "U paru"),             # only the middle one edited
                      ("hero.kicker", "Ostaje kakav jest.")]:
        db.set_copy(key, text, uid)
    with db.engine.begin() as conn:
        mig.fold_points(conn)
    texts = db.copy_texts()
    assert json.loads(texts["offer.online.points"]) == ["Prva", "Druga", "Treća"]
    # the bullets nobody edited come back as the old defaults, in their places
    assert json.loads(texts["offer.individualno.points"]) == ["Rad 1:1, po dogovoru", "U paru", "Rehabilitacija"]
    assert "offer.dvorana.points" not in texts                              # never edited: no row, new defaults
    assert not [k for k in texts if re.fullmatch(r"offer\.\w+\.p\d", k)]   # the old rows are gone
    assert texts["hero.kicker"] == "Ostaje kakav jest."
    page = TestClient(app).get("/").text
    assert "U paru" in page and "Treća" in page                             # and the page reads them

    with db.engine.begin() as conn:                                         # the way back
        mig.split_points(conn)
    texts = db.copy_texts()
    assert [texts[f"offer.online.p{n}"] for n in (1, 2, 3)] == ["Prva", "Druga", "Treća"]
    assert texts["offer.individualno.p2"] == "U paru" and not [k for k in texts if k.endswith(".points")]


def test_every_slot_is_on_a_page_and_only_editors_see_the_editor():
    """Every slot is on a page the editor opens, so none is out of his reach.
    It may be on more than one (18.10.2026): a price (price.<plan>.*)
    prints on the landing's card and on /moja-clanarina, and so does an
    add-on amount (addon.*: the landing's cards, the prehrana plan's hint),
    one fact in both places, and a save updates every copy of it on the
    page it is made on. A list, a switch and a photo keep their shape on
    each page they are on; a visitor and a client get no editor markup, the
    announcements' (rows, not slots) included."""
    make_user("ivan@test.local", plans=("grupni",)); make_user("trener@test.local", is_trainer=True)
    examples()
    t = client_for("trener@test.local"); seen: dict[str, list[str]] = {}
    for path in PAGES:
        page = t.get(path).text
        assert 'id="copyToggle"' in page, path
        for key, slot in copy.SLOTS.items():
            if f'data-copy="{key}"' in page:
                seen.setdefault(key, []).append(path)
                if isinstance(slot, copy.ListSlot):     # one list, an editable span per item
                    assert page.count(f'data-list="{key}"') == 1, key
                    assert page.count(f'data-copy="{key}"') == len(slot.default), key
                if isinstance(slot, copy.FlagSlot):     # a switch: its toggle, once
                    assert page.count(f'data-copy="{key}"') == 1 and f'class="ed-flag" data-copy="{key}"' in page, key
                if isinstance(slot, copy.ImageSlot):    # a photo: its "Dodaj sliku", once (none is set here;
                    # with one, "Ukloni sliku" carries the key as well)
                    assert page.count(f'data-copy="{key}"') == 1 and f'class="ed-img" data-copy="{key}"' in page, key
    assert set(seen) == set(copy.SLOTS), f"slots on no page: {set(copy.SLOTS) - set(seen)}"
    for c in (TestClient(app), client_for("ivan@test.local")):
        for path in PAGES:
            page = c.get(path).text
            if c.get(path, follow_redirects=False).status_code == 200:
                for mark in ("data-copy", "copyToggle", "data-list", 'class="ed-x"', 'ed-add"', 'class="ed-flag"', "data-flag",
                             'class="ed-img"', "data-image", 'class="ed-ann-x"', 'class="ed-add-ann"', 'action="/aktualno/'):
                    assert mark not in page, (path, mark)


# ---------- the reference prices ----------

# The reference table as app.py held it until 18.10.2026, when it became the
# price slots' defaults (copy.REFERENCE_PRICES, no note as ""): what the site
# said before anyone edited a price. Less prehrana's note ("3 € uz dvoranu,
# 5 € uz online"), which left the registry the same day: its hint is the
# add-on's two amounts (the addon.* slots), so each is typed in one place.
SHOP = {
    "grupni": ("60–80", "/ paket", "8, 12 ili 16 treninga"),
    "individualni": ("35", "/ trening", ""),
    "poluindividualni": ("25", "/ trening", ""),
    "rehabilitacija": ("od 30", "/ tretman", "paketi od 5 i 10 tretmana"),
    "online": ("50", "/ mjesečno", ""),
    "prehrana": ("od 3", "/ mjesečno", ""),
}


def shown(html: str) -> str:
    """What a reader sees of some markup: tags dropped, entities read,
    whitespace (a non-breaking space too) collapsed."""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def test_the_price_slots_start_as_the_shops_prices():
    """The reference prices are copy slots since 18.10.2026, plain texts the
    editor opens like any other: per plan an amount, a unit and a note, and
    the MojiMakrosi add-on's amount beside online and beside the dvorana.
    Their defaults are the table the site printed before, so nothing says a
    different price until someone edits one; the edited text wins. Prehrana
    has no note slot: a row the old one may have left is never read."""
    assert set(SHOP) == set(PLAN_TYPES)
    for plan, parts in SHOP.items():
        for part, label, default in zip(("amount", "unit", "note"), ("iznos", "jedinica", "napomena"), parts):
            if (plan, part) == ("prehrana", "note"):     # its hint is the add-on's amounts
                assert f"price.{plan}.{part}" not in copy.SLOTS
                continue
            slot = copy.SLOTS[f"price.{plan}.{part}"]
            assert type(slot) is copy.Slot and slot.max == copy.CAP, (plan, part)
            assert slot.default == default and slot.label == f"Cijena · {plan}: {label}", (plan, part)
    assert copy.SLOTS["addon.online"] == copy.Slot("5", copy.CAP, "MojiMakrosi dodatak uz online (€)")
    assert copy.SLOTS["addon.dvorana"] == copy.Slot("3", copy.CAP, "MojiMakrosi dodatak uz dvoranu (€)")
    assert reference_prices({}) == SHOP and addon_amounts({}) == {"dvorana": "3", "online": "5"}
    edited = {"price.online.amount": "45", "price.grupni.note": "Paketi", "addon.dvorana": "4",
              "price.prehrana.note": "3 € uz dvoranu"}
    assert reference_prices(edited)["online"] == ("45", "/ mjesečno", "")
    assert reference_prices(edited)["grupni"] == ("60–80", "/ paket", "Paketi")
    assert reference_prices(edited)["prehrana"] == ("od 3", "/ mjesečno", "")
    assert addon_amounts(edited) == {"dvorana": "4", "online": "5"}


def card_on(page: str, key: str) -> str:
    """A plan's card on /moja-clanarina, up to the next card or section."""
    start = page.rindex("<", 0, page.index(f'id="plan-{key}"'))
    ends = [page.find(m, page.index(">", start)) for m in ('id="plan-', 'class="mc-sec"', "</main>")]
    return page[start:min(i for i in ends if i > 0)]


def test_an_edited_price_shows_on_the_landing_and_on_moja_clanarina():
    """The gym owner retypes a price in place and it shows, as typed with
    " €" after it, wherever that plan's price does: QMove START's card on the
    landing and the online plan's card on /moja-clanarina. The add-on's
    amount the same, on both gym cards and in the prehrana plan's hint on
    /moja-clanarina (one slot, no number of its own there); Individualno's
    line reads the two other plans' slots. "Zadano" brings the shop's number
    back and leaves no row."""
    make_user("ivan@test.local", plans=("online",)); make_user("trener@test.local", is_trainer=True)
    t = client_for("trener@test.local")
    for key, text in (("price.online.amount", "45"), ("addon.dvorana", "4"),
                      ("price.poluindividualni.amount", "28"), ("price.rehabilitacija.unit", "/ dolazak")):
        assert t.post(f"/copy/{key}", data={"text": text}).json() == {"ok": True, "text": text, "default": False}, key

    page = TestClient(app).get("/").text                                    # a visitor's landing
    offer, gym = page.split('id="usluge"')[1].split('id="dvorana"')
    start = offer.split('class="card offer')[1]
    assert "45 € / mjesečno" in shown(start)
    assert offer.count('+<span class="t">5</span> € / mjesečno') == 3      # the online tiers keep theirs
    dvorana, individualno = gym.split('class="card offer')[1:3]
    for c in (dvorana, individualno):
        assert '+<span class="t">4</span> € / mjesečno' in c
    assert "u dvoje ili troje 28 € / trening · rehabilitacija od 30 € / dolazak" in shown(individualno)
    mine = client_for("ivan@test.local").get("/moja-clanarina").text
    assert "Cijena 45 € / mjesečno" in shown(card_on(mine, "online"))
    assert "od 3 € / mjesečno 4 € uz dvoranu, 5 € uz online" in shown(card_on(mine, "prehrana"))

    page = t.get("/").text                                                  # the editor gets them as slots
    start = page.split('id="usluge"')[1].split('class="card offer')[1]
    assert ('<b><span class="ed t" data-copy="price.online.amount" data-max="2000" '
            'data-label="Cijena · online: iznos">45</span> €</b>') in start
    individualno = page.split('id="dvorana"')[1].split('class="card offer')[2]
    for key in ("poluindividualni.amount", "poluindividualni.unit", "rehabilitacija.amount", "rehabilitacija.unit"):
        assert f'data-copy="price.{key}"' in individualno.split('class="price-note"')[1], key
    mc = t.get("/moja-clanarina").text
    assert 'data-copy="price.online.amount"' in mc
    prehrana = card_on(mc, "prehrana")                                      # its hint: the two add-on slots
    assert 'data-copy="addon.dvorana"' in prehrana and 'data-copy="addon.online"' in prehrana
    assert "price.prehrana.note" not in mc

    r = t.post("/copy/price.online.amount", data={"reset": "1"})            # Zadano: the shop's 50, no row
    assert r.json() == {"ok": True, "text": "50", "default": True} and "price.online.amount" not in db.copy_texts()
    assert "50 € / mjesečno" in shown(TestClient(app).get("/").text.split('id="usluge"')[1].split('class="card offer')[1])


# ---------- the layout, measured in a browser ----------
#
# No slot has a design limit since 16.10.2026 (src/qmt/copy.py): the copy
# comes first, and a design pass fits the boxes to it once it is final. So
# this proves no design at a limit; it proves the net under the texts. Long
# texts (300 characters, lists of 12 items of 60) and line breaks may make a
# box tall, but nothing may widen a page or leave the topbar's pill, an
# editable span never changes a font, nothing is cut by a box that hides its
# overflow, and the cards' prices stay level across each row. The first
# announcement sits on a photo all along: a long text makes it taller too.

WORDS = ("trening snaga pokret zdravlje tehnika grupa trener dvorana program "
         "ravnoteža mobilnost izdržljivost oporavak sprava").split()

LONG, ITEMS, ITEM = 300, 12, 60     # a long text; a list of 12 items, 60 characters each
LINES = "Male grupe do 8 polaznika.\nIndividualni rad 1:1.\nPovratak nakon ozljede."   # a text in three lines
PHOTO_NAME = "aktualno-1-0123456789abcdef.jpg"                     # the first announcement's photo (fill())
IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")   # the install banner's iOS steps


def words(n: int) -> str:
    """n characters of real-looking words."""
    out, i = "", 0
    while len(out) < n:
        out = f"{out} {WORDS[i % len(WORDS)]}".strip(); i += 1
    out = out[:n]
    return out[:-1] + "x" if out.endswith(" ") else out


@pytest.fixture(scope="module")
def server():
    import uvicorn
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8111, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True); th.start()
    for _ in range(100):
        try:
            if httpx.get("http://127.0.0.1:8111/healthz", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    yield "http://127.0.0.1:8111"
    srv.should_exit = True; th.join(timeout=5)


MEASURE = r"""(strict) => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().width > 0; };
  const px = v => parseFloat(v) || 0, out = {problems: []};
  const de = document.documentElement;
  if (de.scrollWidth - de.clientWidth > 0) out.problems.push(`page overflows by ${de.scrollWidth - de.clientWidth}px`);
  for (const el of document.querySelectorAll('main *')) {
    if (!vis(el)) continue; const cs = getComputedStyle(el);
    if (cs.overflowX === 'auto' || cs.overflowX === 'scroll') continue;
    if (el.scrollWidth - el.clientWidth > 2 && el.clientWidth > 0) out.problems.push(`${el.tagName.toLowerCase()}.${(el.className || '').toString().slice(0, 30)} overflows its box by ${el.scrollWidth - el.clientWidth}px`);
  }
  const tb = document.querySelector('.topbar');
  if (tb) { const cs = getComputedStyle(tb), r = tb.getBoundingClientRect(), l = r.left + px(cs.borderLeftWidth) + px(cs.paddingLeft), rr = r.right - px(cs.borderRightWidth) - px(cs.paddingRight);
    for (const k of [...tb.children].filter(k => vis(k) && getComputedStyle(k).position !== 'absolute')) { const b = k.getBoundingClientRect(); if (b.right - rr > 0.5 || l - b.left > 0.5) out.problems.push('topbar child leaves the pill'); } }
  // typography: an editable span never changes the font of what it sits in
  // (a flag's toggle and a photo's pills are buttons of their own, not texts)
  for (const el of document.querySelectorAll('[data-copy]:not(.ed-flag):not(.ed-img):not(.ed-img-x)')) { const a = getComputedStyle(el), b = getComputedStyle(el.parentElement);
    if (a.fontFamily !== b.fontFamily || a.fontSize !== b.fontSize || a.fontWeight !== b.fontWeight) out.problems.push(`${el.dataset.copy} changes the font`); }
  // nothing is cut: a text (span.t, every viewer's, editor or not) never
  // reaches past an ancestor that hides its overflow. The one clamp on
  // purpose is the photo card's caption (.stage .copy, landing.html): what is
  // in it counts as far as it shows, and the caption must sit in the card.
  const hides = cs => ['hidden', 'clip'].includes(cs.overflowX) || ['hidden', 'clip'].includes(cs.overflowY);
  for (const el of document.querySelectorAll('span.t')) {
    if (!vis(el)) continue;
    let {left: l, top: t, right: r, bottom: b} = el.getBoundingClientRect();
    for (let a = el.parentElement; a; a = a.parentElement) {
      if (!hides(getComputedStyle(a))) continue;
      const box = a.getBoundingClientRect();
      if (a.matches('.stage .copy')) { l = Math.max(l, box.left); t = Math.max(t, box.top); r = Math.min(r, box.right); b = Math.min(b, box.bottom); continue; }
      if (l < box.left - 1 || t < box.top - 1 || r > box.right + 1 || b > box.bottom + 1) {
        const what = el.dataset.copy || `${el.parentElement.tagName.toLowerCase()}.${el.parentElement.className}`;
        out.problems.push(`${what} "${el.textContent.slice(0, 12)}…" is cut by ${a.tagName.toLowerCase()}.${(a.className || '').toString().slice(0, 30)}`); break; }
    }
  }
  if (!strict) return out;      // one unbreakable word: it may wrap anywhere, it must only never widen or be cut
  // rows of cards: the prices sit level across each row. A price is text the
  // owner may make any length, so it may wrap: it is measured at its bottom
  // edge, which the foot pinned to the bottom of a landing card keeps level
  // whatever is typed (a card raised by a transform on purpose is measured
  // as if it were not)
  const ty = el => { const m = getComputedStyle(el).transform.match(/matrix\(([^)]+)\)/); return m ? px(m[1].split(',')[5]) : 0; };
  // a tier card holds a monthly and a yearly price; the one shown is measured
  const price = card => [...card.querySelectorAll('.price')].find(vis);
  for (const sel of ['.offer', '.plan']) { const rows = {};
    for (const card of document.querySelectorAll(sel)) { const top = Math.round((card.getBoundingClientRect().top - ty(card)) / 20); (rows[top] ||= []).push(Math.round(price(card).getBoundingClientRect().bottom - ty(card))); }
    for (const bottoms of Object.values(rows)) if (Math.max(...bottoms) - Math.min(...bottoms) > 1) out.problems.push(`${sel} prices not level: ${bottoms.join(', ')}`); }
  return out;
}"""

# The landing's two offer sections, each a row of cards (.swipe-row): the three
# online tiers and the gym's two. On a wide screen the tiers are three columns
# and the gym two; below 900px each is a swipe row of cards 92% as wide as its
# content (a card and a sliver of the next, the owner's call of 17.10.2026)
# with a dot per card (made by the script, so the count and the labels follow
# the cards), and starts on its featured card, centred, with that card's dot
# lit: the tiers on QMove PRO in the middle, the gym (no featured card) on its
# first. The shown prices are level across a row either way, at their bottom
# edge as in MEASURE (the featured tier hangs 16px past its neighbours on a
# desktop, so the row check above can miss it; this one cannot).
LANDING = r"""([w, strict]) => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().width > 0; };
  const out = [], top = el => el.getBoundingClientRect().top, price = card => [...card.querySelectorAll('.price')].find(vis);
  const level = (cards, what) => { if (!strict) return;       // one unbreakable word: it only must not widen
    const b = cards.map(c => Math.round(price(c).getBoundingClientRect().bottom));
    if (Math.max(...b) - Math.min(...b) > 1) out.push(`${what} prices not level: ${b.join(', ')}`); };
  // [section, cards, name, how far a card may stand out of the row on a desktop, the card a phone starts on]
  for (const [sec, n, what, slack, first] of [['#usluge', 3, 'tier', 17, 1], ['#dvorana', 2, 'gym', 1, 0]]) {
    const row = document.querySelector(`${sec} .swipe-row`), cards = row ? [...row.children] : [];
    const dots = [...document.querySelectorAll(`${sec} .dots button`)].filter(vis);
    if (cards.length !== n || !cards.every(c => c.classList.contains('offer'))) { out.push(`${cards.length} ${what} cards`); continue; }
    if (w < 900) {
      if (getComputedStyle(row).overflowX !== 'auto' || row.scrollWidth <= row.clientWidth) out.push(`the ${what} cards do not scroll sideways`);
      const snaps = cards.filter(c => getComputedStyle(c).scrollSnapAlign.includes('center'));
      if (snaps.length !== n) out.push(`${snaps.length} ${what} cards snap`);
      const rcs = getComputedStyle(row), room = row.clientWidth - parseFloat(rcs.paddingLeft) - parseFloat(rcs.paddingRight);
      cards.forEach((c, i) => { const cw = c.getBoundingClientRect().width;
        if (Math.abs(cw - .92 * room) > 1) out.push(`${what} card ${i + 1} is ${Math.round(cw)}px, not 92% of its row's ${Math.round(room)}px`); });
      if (dots.length !== n) out.push(`${dots.length} dots under the ${what} cards`);
      dots.forEach((d, i) => { const r = d.getBoundingClientRect();
        if (r.width < 32 || r.height < 32) out.push(`a ${what} dot is ${r.width}x${r.height}`);
        if (d.getAttribute('aria-label') !== `Kartica ${i + 1} od ${n}`) out.push(`${what} dot ${i + 1} says "${d.getAttribute('aria-label')}"`); });
      const lit = dots.findIndex(d => d.getAttribute('aria-current') === 'true');
      if (lit !== first) out.push(`the ${what} row starts on card ${lit + 1}, not ${first + 1}`);
      if (first) { const g = row.getBoundingClientRect(), r = cards[first].getBoundingClientRect(), off = r.left + r.width / 2 - (g.left + g.width / 2);
        if (!cards[first].classList.contains('featured')) out.push(`${what} card ${first + 1} is not the featured one`);
        if (Math.abs(off) > 4) out.push(`the featured ${what} card is ${Math.round(off)}px off its row's centre`); }
    } else {
      if (dots.length) out.push(`dots under the ${what} cards on a wide screen`);
      const cols = getComputedStyle(row).gridTemplateColumns.split(' ').length;
      if (cols !== n) out.push(`the ${what} cards are in ${cols} columns`);
      const t = cards.map(top); if (Math.max(...t) - Math.min(...t) > slack) out.push(`the ${what} cards are not one row: ${t.join(', ')}`);
    }
    level(cards, what);
  }
  return out;
}"""

# The announcements (#aktualno, in the hero), the two the migration leaves,
# both on in every walk (fill() leaves the switches alone), the first over a
# photo. One card per view at every
# width: a scroller whose card is as wide as its content box, the second card
# on the same line one content width and one gap further (none of it in
# view), a dot per card under it (32px or more, labelled), the first lit on
# load. Below 900px the row is exactly as wide as the screen (it runs to the
# edges like the tiers' row; the hero keeps its gutter for the rest). From
# 900px the card is the hero's column, at most 1100px (the row's border box is
# wider by the padding that keeps the card's shadow), and exactly 1100px at
# 1280px. At every width the card is as wide as the photo under it, and the
# two are one height, so the row does not change height as they change.
# one_line: from 900px a plain card is one line again (chip, title over when,
# the text taking the room, the link at the right end), so its text sits on
# its title's line: their middles level, as the strip centres what is on a
# line. Checked with the default texts only: the 300-character ones wrap
# every piece onto a line of its own, as they should.
AKTUALNO = r"""([w, oneLine]) => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().width > 0; };
  const out = [], row = document.querySelector('#aktualno');
  if (!row) return ['no announcements'];
  const cards = [...row.querySelectorAll('.event')].filter(vis), dots = [...document.querySelectorAll('#aktualno + .dots button')].filter(vis);
  if (cards.length !== 2) out.push(`${cards.length} announcements shown`);
  const hs = cards.map(c => c.getBoundingClientRect().height);
  if (Math.max(...hs) - Math.min(...hs) > 1) out.push(`the announcements are not one height: ${hs.map(Math.round).join(', ')}`);
  const cs = getComputedStyle(row), r = row.getBoundingClientRect(), box = cards.map(c => c.getBoundingClientRect());
  const room = row.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight), gap = parseFloat(cs.columnGap) || 0;
  if (!row.classList.contains('swipe-row') || cs.overflowX !== 'auto' || row.scrollWidth <= row.clientWidth) out.push('the announcements are not a scroller');
  box.forEach((b, i) => { if (Math.abs(b.width - room) > 1) out.push(`announcement ${i + 1} is ${b.width}px wide, its row's content ${room}px`); });
  if (box.length === 2) {
    if (Math.abs(box[0].top - box[1].top) > 1) out.push(`the announcements are not on one line: ${box[0].top}, ${box[1].top}`);
    if (Math.abs(box[1].left - box[0].left - (room + gap)) > 1)
      out.push(`the second announcement is ${box[1].left - box[0].left}px after the first, not one per view (${room} + ${gap})`);
    if (box[1].left < r.right - 1) out.push(`${Math.round(r.right - box[1].left)}px of the second announcement show beside the first`);
  }
  const photo = document.querySelector('.stage').getBoundingClientRect();
  if (box.length && (Math.abs(box[0].left - photo.left) > 1 || Math.abs(box[0].right - photo.right) > 1))
    out.push(`the announcement (${box[0].left}-${box[0].right}) is not as wide as the photo under it (${photo.left}-${photo.right})`);
  if (dots.length !== 2) out.push(`${dots.length} dots under the announcements`);
  dots.forEach((d, i) => { const b = d.getBoundingClientRect();
    if (b.width < 32 || b.height < 32) out.push(`an announcement dot is ${b.width}x${b.height}`);
    if (d.getAttribute('aria-label') !== `Kartica ${i + 1} od 2`) out.push(`announcement dot ${i + 1} says "${d.getAttribute('aria-label')}"`); });
  const lit = dots.findIndex(d => d.getAttribute('aria-current') === 'true');
  if (lit !== 0) out.push(`the announcements start on card ${lit + 1}, not 1`);
  if (w < 900) {
    if (Math.abs(r.width - innerWidth) > 1 || Math.abs(r.left) > 1) out.push(`the announcements' row is ${r.width}px wide at ${r.left}, the screen ${innerWidth}px`);
  } else {
    if (room > 1100.5) out.push(`an announcement is ${room}px wide, past the hero's 1100px column`);
    if (w >= 1280) box.forEach((b, i) => { if (Math.abs(b.width - 1100) > 1) out.push(`announcement ${i + 1} is ${b.width}px wide, not the column's 1100px`); });
    if (oneLine) for (const c of cards.filter(c => !c.classList.contains('has-img'))) {
      const mid = sel => { const b = c.querySelector(sel).getBoundingClientRect(); return (b.top + b.bottom) / 2; };
      if (Math.abs(mid('.text') - mid('.head')) > 2) out.push("a plain announcement's text is not on its title's line");
    }
  }
  return out;
}"""

# The first announcement over a photo (fill() gives it one, written into this
# test's own MEDIA_DIR). The photo loaded (so the server thread read the same
# patched config) and covers the card; every text, the chip and the link sit
# inside the card, which a long text makes taller: nothing in it is clamped,
# unlike the stage's caption (MEASURE allows no cut here). A column at every
# width, at least its min-height tall (300px; from 900px a wide banner's
# 320px): the chip at the top, then the title, the text and the link, which
# sits at the bottom. The type is white.
PHOTO = r"""() => {
  const out = [], card = document.querySelector('#aktualno .event.has-img'), box = el => el.getBoundingClientRect();
  if (!card) return ['no announcement over a photo'];
  if (!card.hasAttribute('data-photo')) out.push('the photo card carries no data-photo');
  const img = card.firstElementChild, c = box(card), cs = getComputedStyle(card);
  if (!img || !img.matches('img.bg')) return [...out, "the photo is not the card's first child"];
  if (!img.complete || !img.naturalWidth) out.push(`the photo did not load: ${img.getAttribute('src')}`);
  const r = box(img), at = b => [b.left, b.top, b.width, b.height].map(Math.round).join(',');
  if (['left', 'top', 'right', 'bottom'].some(k => Math.abs(r[k] - c[k]) > 1)) out.push(`the photo (${at(r)}) does not cover its card (${at(c)})`);
  if (c.height < (innerWidth < 900 ? 300 : 320) - 1) out.push(`the photo card is ${Math.round(c.height)}px tall`);
  for (const el of card.querySelectorAll('span.t, .tag, .act')) { const b = box(el);
    if (b.width && (b.left < c.left - 1 || b.top < c.top - 1 || b.right > c.right + 1 || b.bottom > c.bottom + 1))
      out.push(`"${el.textContent.trim().slice(0, 12)}…" leaves the photo card`); }
  const [tag, head, text, foot] = ['.tag', '.head', '.text', '.foot'].map(s => box(card.querySelector(s)));
  if (Math.abs(tag.top - c.top - parseFloat(cs.paddingTop)) > 2) out.push(`the photo card's chip is ${Math.round(tag.top - c.top)}px from its top`);
  if (Math.abs(c.bottom - parseFloat(cs.paddingBottom) - foot.bottom) > 2) out.push(`the photo card's link is ${Math.round(c.bottom - foot.bottom)}px from its bottom`);
  if (!(tag.bottom <= head.top + 1 && head.bottom <= text.top + 1 && text.bottom <= foot.top + 1))
    out.push("the photo card is not a column of chip, title, text and link");
  // the room is above the title (its auto margin), not in a text box grown under the words
  const words = card.querySelector('.text span.t');
  if (words && text.bottom - words.getBoundingClientRect().bottom > 4) out.push("the photo card's text box grows: its title is not at the bottom");
  for (const s of ['h2', '.when']) if (getComputedStyle(card.querySelector(s)).color !== 'rgb(255, 255, 255)') out.push(`the photo card's ${s} is not white`);
  return out;
}"""

# The announcements in edit mode (add_drop, with three cards): one under the
# other, the page and the hero no wider than the screen, nothing in the row
# or in "+ Dodaj najavu" wider than its box, and nothing in a card (its
# texts, its link, its pills) outside it. Scoped to them: MEASURE in edit
# mode would also count the lists' ✕, which hangs 6px past its item on
# purpose (base.html, .ed-x).
EDIT_ROW = r"""() => {
  const vis = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const de = document.documentElement, hero = document.querySelector('.hero-inner'), out = [];
  const cards = [...document.querySelectorAll('#aktualno .event')].filter(vis), box = el => el.getBoundingClientRect();
  if (!cards.every((c, i) => !i || box(c).top >= box(cards[i - 1]).bottom - 1)) out.push('the cards are not one under the other');
  if (de.scrollWidth - de.clientWidth > 0) out.push(`the page overflows by ${de.scrollWidth - de.clientWidth}px`);
  if (hero.scrollWidth - hero.clientWidth > 0) out.push(`the hero overflows by ${hero.scrollWidth - hero.clientWidth}px`);
  for (const el of document.querySelectorAll('#aktualno *, .ed-add-ann *')) {
    if (!vis(el) || ['auto', 'scroll'].includes(getComputedStyle(el).overflowX)) continue;
    if (el.scrollWidth - el.clientWidth > 2 && el.clientWidth > 0)
      out.push(`${el.tagName.toLowerCase()}.${el.className} overflows its box by ${el.scrollWidth - el.clientWidth}px`);
  }
  for (const card of cards) { const c = box(card);
    for (const el of card.querySelectorAll('span.t, .tag, .act, .ed-flag, .ed-img, .ed-img-x, .ed-ann-x > button')) {
      if (!vis(el)) continue; const b = box(el);
      if (b.left < c.left - 1 || b.right > c.right + 1 || b.top < c.top - 1 || b.bottom > c.bottom + 1)
        out.push(`"${el.textContent.trim().slice(0, 12)}…" leaves its card`);
    }
  }
  return out;
}"""

# Mjesečno / Godišnje: one choice, two switches (under the tiers, under the
# gym). Every card of both sections shows exactly the chosen price, and both
# switches say it.
PERIOD = r"""(p) => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && el.getBoundingClientRect().width > 0; };
  const out = [];
  for (const c of document.querySelectorAll('#usluge .offer, #dvorana .offer')) {
    const shown = [...c.querySelectorAll('.price')].filter(vis).map(x => x.dataset.period);
    if (shown.join() !== p) out.push(`a card in #${c.closest('section').id} shows "${shown.join('+')}" for ${p}`);
  }
  const switches = [...document.querySelectorAll('.period')], where = switches.map(s => s.closest('section').id);
  if (where.join() !== 'usluge,dvorana') out.push(`switches in: ${where.join(', ')}`);
  for (const sw of switches) {
    const said = [...sw.querySelectorAll('[aria-selected="true"]')].map(b => b.dataset.period);
    if (said.join() !== p) out.push(`the #${sw.closest('section').id} switch says "${said.join('+')}" for ${p}`);
  }
  return out;
}"""

# The first announcement's text in three lines (LINES): the line breaks show,
# so its span.t is three lines tall, not the one line the same words take
# without them.
EVENT_TEXT = r"""() => {
  const t = document.querySelector('#aktualno .event .text span.t');
  if (!t) return ['no span.t in the first announcement\'s text'];
  const cs = getComputedStyle(t), lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.2;
  const n = t.getBoundingClientRect().height / lh;
  return n < 2.5 ? [`the three-line announcement text shows as ${n.toFixed(1)} lines`] : [];
}"""


def test_layout_holds_with_long_texts_and_line_breaks(server):
    pytest.importorskip("playwright")
    from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright
    make_user("trener@test.local", is_trainer=True); make_user("ivan@test.local", plans=("grupni",))
    one, two = examples()                             # the landing's two announcements, as the migration leaves them
    CARD = f'[data-image="aktualno.{one}.image"]'     # the first one, in the editor's markup

    def fill(make):
        for key, slot in copy.SLOTS.items():
            if isinstance(slot, (copy.FlagSlot, copy.ImageSlot)):   # a switch and a photo, not texts
                continue
            if isinstance(slot, copy.ListSlot):         # every list 12 items long, each item 60 characters
                db.set_copy(key, copy.dump_items([make(min(slot.max_chars, ITEM))] * min(slot.max_items, ITEMS)), None)
            else:                                       # every text 300 characters
                db.set_copy(key, make(min(slot.max, LONG)), None)
        for a in db.announcements(all=True):            # and every text of every announcement; they stay
            for column in copy.ANNOUNCEMENT_BLANK:      # on (both show), the photo below
                db.set_announcement_field(a.id, column, make(LONG), None)
        photo_on()

    def photo_on():
        """The first announcement over a photo, the second plain: every walk
        measures a photo card beside a plain one, or among them in a phone's
        row. Written where the server thread will look for it, this test's
        own MEDIA_DIR (the autouse fixture)."""
        config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1600, 900), (70, 92, 112)).save(config.MEDIA_DIR / PHOTO_NAME, "JPEG", quality=82)
        db.set_announcement_image(one, PHOTO_NAME)

    def photo_edit(pg):
        """The editor's photo pills in a browser (base.html), on the first
        card in edit mode. "Promijeni sliku" opens the file picker; the
        chosen file goes up, and the card shows the new photo at once (first
        in the card, .has-img, data-photo) with its pills, the photo it
        replaced deleted. "Ukloni sliku" asks first ("Ukloni?"), and its
        second tap leaves the card plain, row and file gone. "Dodaj sliku"
        then puts a photo on the plain card. The walks' photo is put back,
        the page reloaded, for what follows."""
        out, card = [], pg.locator(f"#aktualno {CARD}")

        def send(before):
            """A file picked with the card's .ed-img: the problems seen, and the stored name."""
            with pg.expect_file_chooser() as chooser:
                card.locator(".ed-img").click()
            chooser.value.set_files({"name": "nova.jpg", "mimeType": "image/jpeg", "buffer": picture(1200, 800)})
            try:
                pg.wait_for_function("""([card, before]) => { const i = document.querySelector(card).firstElementChild;
                  return i.matches('img.bg') && i.getAttribute('src') !== before && i.complete && i.naturalWidth > 0; }""",
                                     arg=[CARD, before], timeout=10000)
            except PlaywrightTimeout:
                return ["a photo sent from the editor did not show first in its card"], ""
            name = db.announcement(one).image or ""
            seen = pg.evaluate("""(card) => { const c = document.querySelector(card);
              return [c.classList.contains('has-img'), c.hasAttribute('data-photo'), c.firstElementChild.getAttribute('src'),
                      [...c.querySelectorAll('.ed-img, .ed-img-x')].map(b => b.textContent), document.getElementById('copyBar').hidden]; }""", CARD)
            if seen != [True, True, f"/slika/{name}", ["Promijeni sliku", "Ukloni sliku"], True] or not name.startswith(f"aktualno-{one}-"):
                return [f"after an upload the card is {seen}, the row {name!r}"], name
            return [], name

        pg.click("#copyToggle")
        problems, name = send(f"/slika/{PHOTO_NAME}")                  # Promijeni sliku
        out += problems
        if (config.MEDIA_DIR / PHOTO_NAME).exists():
            out.append("the photo an upload replaced is still stored")
        x = card.locator(".ed-img-x")
        x.click()
        if x.text_content() != "Ukloni?" or db.announcement(one).image != name:
            out.append(f"one tap on Ukloni sliku: {x.text_content()!r}, the row {db.announcement(one).image!r}")
        x.click()
        try:
            pg.wait_for_function("""(card) => { const c = document.querySelector(card);
              return !c.classList.contains('has-img') && !c.hasAttribute('data-photo') && !c.querySelector('img.bg, .ed-img-x')
                     && c.querySelector('.ed-img').textContent === 'Dodaj sliku'; }""", arg=CARD, timeout=10000)
        except PlaywrightTimeout:
            out.append("the second tap on Ukloni sliku did not leave the card plain")
        if db.announcement(one).image is not None or (config.MEDIA_DIR / name).exists():
            out.append("after Ukloni sliku its name or its file is still there")
        problems, name = send(None)                                    # Dodaj sliku, on the plain card
        out += [f"onto a plain card: {p}" for p in problems]
        pg.click("#copyToggle")                                        # Gotovo: edit mode persists in the tab otherwise
        photo_on(); pg.reload(); pg.wait_for_load_state("networkidle")
        return out

    def flip(pg):
        """The editor's switch in a browser: in edit mode the first
        announcement, switched off, stays on the page with its content dimmed
        (not its toggle), and both cards show one under the other, each the
        row's width: a grid, not a scroller, so the editor reaches the one
        that is off (it has no dot), and no dots under them; the row's
        negative margins widen neither the page nor the hero. After a reload it
        is gone and the second is alone (.single on their box), as wide as the
        row's content, with no dots. The same at every width. Switched back on
        for the walks after this one."""
        out = []
        pg.click("#copyToggle"); pg.locator("#aktualno .ed-flag").first.click()
        pg.wait_for_function("""() => { const b = document.querySelector('#aktualno .ed-flag');
          return b.getAttribute('aria-pressed') === 'false' && b.closest('.event').classList.contains('is-off'); }""", timeout=5000)
        seen = pg.evaluate("""() => { const c = document.querySelector('#aktualno .event'), o = el => +getComputedStyle(el).opacity;
          return [c.getBoundingClientRect().height > 0, o(c.querySelector('.head')), o(c.querySelector('.ed-flag')),
                  o(c.querySelector('.ed-ann-x > button'))]; }""")
        if seen != [True, 0.55, 1, 0.55]:
            out.append(f"a strip switched off in edit mode (shown, its title block's, its toggle's and its Obriši najavu's "
                       f"opacity): {seen}")
        stacked = pg.evaluate("""() => { const row = document.querySelector('#aktualno'), cs = getComputedStyle(row);
          const [a, b] = [...row.querySelectorAll('.event')].map(c => c.getBoundingClientRect());
          const de = document.documentElement, hero = row.parentElement;
          return {grid: cs.display, scrolls: row.scrollWidth !== row.clientWidth, dots: getComputedStyle(row.nextElementSibling).display,
                  room: row.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight), widths: [a.width, b.width],
                  under: b.top >= a.bottom - 1, lefts: [a.left, b.left],
                  overflow: [de.scrollWidth - de.clientWidth, hero.scrollWidth - hero.clientWidth]}; }""")
        if (stacked["grid"] != "grid" or stacked["scrolls"] or stacked["dots"] != "none" or not stacked["under"]
                or abs(stacked["lefts"][0] - stacked["lefts"][1]) > 1 or any(abs(x - stacked["room"]) > 1 for x in stacked["widths"])
                or stacked["overflow"] != [0, 0]):
            out.append(f"in edit mode, one announcement off, they are not one under the other, each the row's width, without dots "
                       f"and without overflow (the page's, the hero's): {stacked}")
        pg.click("#copyToggle")                                        # Gotovo, then the visitor's view
        pg.reload(); pg.wait_for_load_state("networkidle")
        cards = pg.locator("#aktualno .event")
        if cards.nth(0).is_visible() or not cards.nth(1).is_visible():
            out.append("after a reload the card switched off shows, or the other one does not")
        alone = pg.evaluate("""() => { const row = document.querySelector('#aktualno'), cs = getComputedStyle(row), [a, b] = row.querySelectorAll('.event');
          return {single: row.classList.contains('single'), off: getComputedStyle(a).display, width: b.getBoundingClientRect().width,
                  room: row.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight),
                  dots: document.querySelectorAll('#aktualno + .dots button').length, hidden: row.nextElementSibling.hidden}; }""")
        if not alone["single"] or alone["off"] != "none":
            out.append(f"after a reload their box is not .single, or the card switched off is not display: none: {alone}")
        if abs(alone["width"] - alone["room"]) > 1:
            out.append(f"the one announcement left is {alone['width']}px of the row's {alone['room']}px")
        if alone["dots"] or not alone["hidden"]:
            out.append(f"one announcement left, and {alone['dots']} dots under it (their box hidden: {alone['hidden']})")
        if db.announcement(one).shown:
            out.append("the switch was not stored")
        out += pg.evaluate(MEASURE, True)["problems"]
        db.set_announcement_shown(one, True)
        return out

    def add_drop(pg):
        """The editor's "+ Dodaj najavu" and "Obriši najavu" in a browser.
        In edit mode the first adds a card: the page comes back on
        #aktualno with three, the new one last with its placeholders, and
        three dots under them (outside edit mode again). In edit mode the
        three stack, nothing overflowing, and the new card's "Obriši najavu"
        asks first ("Obriši?" at one tap, the card still there); its second
        tap deletes it, and the page comes back with the two cards of the
        walks."""
        out = []
        pg.click("#copyToggle")
        with pg.expect_navigation():
            pg.click(".ed-add-ann button")
        pg.wait_for_load_state("networkidle")
        cards = db.announcements(all=True)
        if [a.id for a in cards[:2]] != [one, two] or len(cards) != 3 or cards[2].title != copy.ANNOUNCEMENT_BLANK["title"]:
            out.append(f"+ Dodaj najavu left the cards {[(a.id, a.title[:12]) for a in cards]}")
        seen = pg.evaluate("""() => [document.querySelectorAll('#aktualno .event').length,
                                     document.querySelectorAll('#aktualno + .dots button').length,
                                     document.querySelector('#aktualno .event:last-child h2').textContent, location.hash]""")
        if seen != [3, 3, copy.ANNOUNCEMENT_BLANK["title"], "#aktualno"]:
            out.append(f"after + Dodaj najavu (cards, dots, the last one's title, the address' #): {seen}")
        if not pg.evaluate("document.body.classList.contains('editing')"):   # it comes back in edit mode by itself
            out.append("after + Dodaj najavu the page is not in edit mode any more")
        out += pg.evaluate(EDIT_ROW)
        x = pg.locator("#aktualno .event").nth(2).locator(".ed-ann-x > button")
        x.click()
        if x.text_content() != "Obriši?" or len(db.announcements(all=True)) != 3:
            out.append(f"one tap on Obriši najavu: {x.text_content()!r}, {len(db.announcements(all=True))} cards")
        with pg.expect_navigation():
            x.click()
        pg.wait_for_load_state("networkidle")
        left, shown = [a.id for a in db.announcements(all=True)], pg.locator("#aktualno .event").count()
        if left != [one, two] or shown != 2:
            out.append(f"the second tap on Obriši najavu left the cards {left}, {shown} on the page")
        pg.click("#copyToggle")                                        # Gotovo
        return out

    ROW = "document.querySelector('#aktualno')"
    STATE = f"() => [{ROW}.scrollLeft, [...document.querySelectorAll('#aktualno + .dots button')].map(d => d.getAttribute('aria-current')).join()]"
    IN_VIEW = f"() => window.scrollTo({{top: scrollY + {ROW}.getBoundingClientRect().top - 60, behavior: 'instant'}})"

    def advance(pg, touch):
        """The announcements move on by themselves (the landing's script), on
        a phone and on a desktop: with their row on the screen (the long texts
        push it below the fold, and off the screen it holds still), the second
        card is in and its dot lit within one tick (5 s) and the glide. A
        person on the row holds it, about a second before the next tick was
        due: on a phone a touch starts the whole delay again, so nothing moves
        for the 2 s after the finger lifts; on a desktop the mouse over the
        row keeps it still, the same 2 s. The mouse starts away from the row,
        or it would hold the row from the start."""
        if not touch:
            pg.mouse.move(0, 0)
        pg.evaluate(IN_VIEW)
        try:
            t = pg.wait_for_function(f"""() => {{ const d = document.querySelectorAll('#aktualno + .dots button');
              return d.length === 2 && d[1].getAttribute('aria-current') === 'true' && {ROW}.scrollLeft > 0 && performance.now(); }}""",
              timeout=8000).json_value()
        except PlaywrightTimeout:
            return [f"the announcements did not move on by themselves in 8 s: {pg.evaluate(STATE)}"]
        pg.wait_for_function(f"() => performance.now() > {t + 3500}")      # the next tick about a second away
        h = pg.locator("#aktualno .event").nth(1).locator("h2").bounding_box()
        x, y = h["x"] + h["width"] / 2, h["y"] + h["height"] / 2
        if touch:
            pg.touchscreen.tap(x, y)
        else:
            pg.mouse.move(x, y)
        before = pg.evaluate(STATE); pg.wait_for_timeout(2000); after = pg.evaluate(STATE)
        how = "a touch" if touch else "the mouse came over them"
        return [] if after == before else [f"the announcements moved within 2 s of {how}: {before} -> {after}"]

    def still(pw):
        """Under reduced motion the announcements never move by themselves
        (a swipe and the dots still work): 6.5 s on, with their row on the
        screen, the first card is still the one in view."""
        ctx = pw.chromium.launch().new_context(viewport={"width": 390, "height": 900}, has_touch=True, is_mobile=True,
                                               reduced_motion="reduce")
        pg = ctx.new_page(); pg.goto(server + "/"); pg.wait_for_load_state("networkidle")
        pg.evaluate(IN_VIEW); pg.wait_for_timeout(6500); seen = pg.evaluate(STATE)
        ctx.browser.close()
        return [] if seen == [0, "true,false"] else [f"[reduced motion 390px] the announcements moved by themselves: {seen}"]

    def banner(pw):
        """The install banner (base.html) asks again a week after it was
        dismissed, until the app is installed. On an iPhone it shows at load
        (the share-sheet steps, no native prompt to wait for), so each case
        is one reload, from the second page on: dismissed with its ✕ just
        now, or six days ago, it stays away; eight days ago, or the old "no"
        (one dismissal was for good before 16.10.2026), it is back; and
        "installed" (the native prompt accepted) keeps it away."""
        out, ctx = [], pw.chromium.launch().new_context(viewport={"width": 390, "height": 900}, has_touch=True,
                                                         is_mobile=True, user_agent=IPHONE)
        pg = ctx.new_page()
        pg.goto(server + "/login"); pg.fill("main input[name=email]", "ivan@test.local"); pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
        pg.goto(server + "/prehrana")                 # the second page with the banner: it asks
        if not pg.locator("#a2hs").is_visible():
            out.append("not shown on the second page")
        pg.click("#a2hs .a2hs-x"); stored = pg.evaluate("localStorage.getItem('qmt-a2hs')"); pg.reload()
        if pg.locator("#a2hs").is_visible() or not (stored or "").isdigit():
            out.append(f"dismissed with its ✕ ({stored!r} stored), it is back at once")
        for when, value, back in (("six days ago", "Date.now() - 6 * 864e5", False), ("eight days ago", "Date.now() - 8 * 864e5", True),
                                  ('with the old "no"', "'no'", True), ('as "installed"', "'installed'", False)):
            pg.evaluate(f"localStorage.setItem('qmt-a2hs', String({value}))"); pg.reload()
            if pg.locator("#a2hs").is_visible() != back:
                out.append(f"dismissed {when}, it is {'still away' if back else 'back'}")
        ctx.browser.close()
        return [f"[install banner 390px] {p}" for p in out]

    def walk(pw, email, widths, label, strict=True, lines=False, switch=(), auto=(), photos=(), adds=(), one_line=False):
        problems = []
        for w in widths:
            phone = w < 600
            ctx = pw.chromium.launch().new_context(viewport={"width": w, "height": 900}, has_touch=phone, is_mobile=phone)
            pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            if email:
                pg.goto(server + "/login"); pg.fill("main input[name=email]", email); pg.fill("main input[name=password]", "lozinka123")
                pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
            for path in PAGES if email else ("/",):
                pg.goto(server + path); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
                where = f"[{label} {email or 'guest'} {w}px {path}]"
                problems += [f"{where} {p}" for p in pg.evaluate(MEASURE, strict)["problems"]]
                if path != "/":
                    continue
                if lines:
                    problems += [f"{where} {p}" for p in pg.evaluate(EVENT_TEXT)]
                problems += [f"{where} {p}" for p in pg.evaluate(LANDING, [w, strict])]
                problems += [f"{where} {p}" for p in pg.evaluate(AKTUALNO, [w, one_line])]
                problems += [f"{where} {p}" for p in pg.evaluate(PHOTO)]
                if w in auto:                               # the announcements moving by themselves, on a phone and a desktop
                    problems += [f"{where} {p}" for p in advance(pg, phone)]
                if not all(pg.locator(f"{sec} .period").is_visible() for sec in ("#usluge", "#dvorana")):
                    problems.append(f"{where} no Mjesečno / Godišnje switch under each row"); continue
                problems += [f"{where} on load: {p}" for p in pg.evaluate(PERIOD, "month")]   # monthly first
                # either switch flips both sections: each pressed both ways,
                # the same checks after every press
                for sec, period in (("#usluge", "year"), ("#dvorana", "month"), ("#dvorana", "year"), ("#usluge", "month")):
                    pg.click(f'{sec} .period button[data-period="{period}"]')
                    did = f"{where} {sec} {period}:"
                    problems += [f"{did} {p}" for p in pg.evaluate(PERIOD, period)]
                    problems += [f"{did} {p}" for p in pg.evaluate(MEASURE, strict)["problems"]]
                    problems += [f"{did} {p}" for p in pg.evaluate(LANDING, [w, strict])]
                if w in photos:                             # the editor's photo pills, on a phone
                    problems += [f"{where} photo: {p}" for p in photo_edit(pg)]
                if w in switch:                             # the editor's switch, on a phone and a wide screen
                    problems += [f"{where} switch: {p}" for p in flip(pg)]
                if w in adds:                               # the editor adds a card and deletes it, likewise
                    problems += [f"{where} add/delete: {p}" for p in add_drop(pg)]
            problems += [f"[{label} {w}px] js: {e}" for e in errs]
            ctx.browser.close()
        return problems

    with sync_playwright() as pw:
        photo_on()                                    # the default texts, the first announcement over a photo:
        problems = walk(pw, None, (900, 1280), "defaults", one_line=True)   # a plain one is one line on a wide screen
        fill(words)                                   # long texts: 300 characters, lists of 12
        problems += walk(pw, None, (360, 390, 900, 1280), "words", auto=(390, 1280))
        problems += still(pw)                         # under reduced motion: never by themselves
        problems += walk(pw, "trener@test.local", (360, 390, 900, 1280), "words", switch=(390, 1280), photos=(390,),
                         adds=(390, 1280))
        problems += walk(pw, "ivan@test.local", (360, 1280), "words")
        problems += banner(pw)                        # the install banner's week between asks
        db.set_announcement_field(one, "body", LINES, None)   # line breaks: the first announcement's text in three lines
        problems += walk(pw, None, (390, 1280), "lines", lines=True)
        problems += walk(pw, "trener@test.local", (390,), "lines", lines=True)
        fill(lambda n: "W" * n)                       # one unbreakable word: must wrap, never widen
        problems += walk(pw, "trener@test.local", (360, 1280), "one-word", strict=False)
    print("\n".join(problems))
    assert not problems, f"{len(problems)} layout problems, listed above"


def test_an_amount_without_a_number_prints_without_the_euro_sign():
    """"na upit" is a price the owner may type; "na upit €" is not. A number
    keeps its sign: "50 €"."""
    make_user("ivan@test.local", plans=("grupni",)); make_user("trener@test.local", is_trainer=True)
    db.set_copy("price.rehabilitacija.amount", "na upit", None)
    landing = TestClient(app).get("/").text
    mine = client_for("ivan@test.local").get("/moja-clanarina").text
    for page in (landing, mine):
        assert "na upit</span>" in page                                      # printed
        assert "na upit</span> €" not in page and "na upit</span>&nbsp;€" not in page   # bare
    assert "50</span> €</b>" in landing                                     # a number keeps its €
    assert "50</span> € <small>" in mine
