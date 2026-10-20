"""In-place editable copy: src/qmt/copy.py (the slots and their caps),
POST /copy/{key} (the save), _copy.html (the macros), the editor in base.html,
the landing's announcements (rows since 18.10.2026: their fields edited
through virtual keys on the same routes, "+ Dodaj najavu" and "Obriši
najavu", the cap of eight, and the migration that made the two old sets of
slots rows), their photos (POST /copy/{key}/slika, GET /slika/{name}), the
gym's cards (rows since 20.10.2026, the same way: virtual keys, "+ Dodaj
karticu" and "Obriši karticu", the cap of eight, their migration), the
reference prices (the price.<plan>.* and addon.* slots), the migration
that turned the offer cards' bullets into lists, and the opening hours'
rows (a RowsSlot since 20.10.2026: cells, rows removed and added, and the
migration that folded the six old slots in, with the QMove tiers' add-on
words, one slot each since the same day).

The browser half is the net under the texts. Their design limits were lifted
on 16.10.2026 (src/qmt/copy.py): it starts the app in a thread, fills every
slot with a long text — once with words, once with one unbreakable word —
gives the first announcement's text three lines and a photo behind it, and
measures the pages at four widths.
Nothing may overflow or be cut, and the cards' prices stay level. It proves
no design; that pass comes once the copy is final. On the way it walks the
landing's rows of cards, the announcements' among them (one card per view;
they move on by themselves, on a phone and on a desktop, and hold still when
they must), the editor's switch and photo pills, adding and deleting a card, the
gym's cards added, hidden and deleted, the opening hours' rows removed, added
and emptied, and the install banner's week between asks.
Beside the walk, on the same server: /clanarine's add form, whose script
shows the tier select that fits the chosen plan (the online plan's QMove
tiers are the landing cards' titles; the rest is in tests/test_clanarina.py).
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
from qmt.models import PLAN_TYPES, Base, SiteCopy, User
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
    key, slot = "offer.online.points", copy.SLOTS["offer.online.points"]
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
    start = TestClient(app).get("/").text.split('id="usluge"')[1].split('class="card offer')[1]   # QMove START's card:
    assert d[1] not in start and d[2] not in start and "<ul>" not in start  # a visitor sees no bullets
    assert "Treniraj gdje god jesi." in start
    assert 'data-list="offer.online.points"' in t.get("/").text             # the editor can still add one


# ---------- the opening hours: a rows slot ----------

HOURS = "info.hours.rows"


def hours(page: str) -> str:
    """The landing's hours table (#kontakt), from its heading to the table's end."""
    return page.split('id="kontakt"')[1].split("</table>")[0]


def test_a_rows_slot_is_one_json_array_of_pairs_and_reads_anything_else_as_its_default():
    """copy.RowsSlot (20.10.2026): a table of rows of two texts, stored as
    one site_copy row, a JSON array of [days, hours] pairs, each cell
    cleaned as a text is. A cell may be empty; a row whose two cells are
    both empty is dropped, on the way in and on the way out. A stored text
    that cannot be read as such an array reads as the default rows, and an
    empty array is an emptied table."""
    slot = copy.SLOTS[HOURS]
    assert slot == copy.RowsSlot((("pon · sri · čet · pet", "07:00 – 20:00"), ("uto", "individualni termini"),
                                  ("sub · ned", "zatvoreno")), 12, 2000, "Radno vrijeme", ("dani", "sati"))
    assert copy.ROW_BLANK == ("dan", "sati")
    assert not [k for k in copy.SLOTS if re.fullmatch(r"info\.hours\.[dt]\d", k)]   # the six old slots are gone
    d = [list(row) for row in slot.default]
    assert copy.load_rows(None, slot) == d and copy.rows_for(HOURS, {}) == d

    rows = [["pon - pet", "07:00 – 21:00"], ["uto", ""], ["", "po dogovoru"]]
    raw = copy.dump_rows(rows)
    assert json.loads(raw) == rows and copy.load_rows(raw, slot) == rows and copy.rows_for(HOURS, {HOURS: raw}) == rows
    assert "pon · sri" in copy.dump_rows(slot.default)                     # readable as stored (no \u escapes)
    assert json.loads(copy.dump_rows([("  a   b ", " \n c \n\n\n d "), ("", " \n "), ("x", "")])) == [
        ["a b", "c\n\nd"], ["x", ""]]                                       # cleaned; two empty cells: the row goes
    assert copy.load_rows('[["a", "b"], ["", "  "], [" c ", ""]]', slot) == [["a", "b"], ["c", ""]]
    assert copy.load_rows("[]", slot) == []                                 # an emptied table stays empty
    for bad in ("", "nije json", "null", "{}", '"tekst"', "[1, 2]", '[["a"]]', '[["a", "b", "c"]]',
                '[["a", "b"], "c"]', '{"0": ["a", "b"]}'):
        assert copy.load_rows(bad, slot) == d, bad


def test_a_rows_slot_takes_cells_and_rows_added_and_removed_within_its_limits():
    """POST /copy/info.hours.rows, the editor's way: index + part + text
    sets a cell (cleaned, the cap every text has), and an EMPTY text leaves
    it empty: a row has no default per cell, the exception to "empty is the
    default". A row left with two empty cells goes; index + remove=1
    removes a row; add=1 appends one with the placeholders, at most twelve;
    reset=1 puts the default rows back. The answer is always the whole
    table, so the editor redraws it with fresh indexes. A rows slot takes
    no photo, as a text slot takes none."""
    make_user("ivan@test.local"); uid = make_user("trener@test.local", is_trainer=True)
    slot, d = copy.SLOTS[HOURS], [list(row) for row in copy.SLOTS[HOURS].default]
    assert TestClient(app).post(f"/copy/{HOURS}", data={"text": "x", "index": "0", "part": "0"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{HOURS}", data={"add": "1"}).status_code == 403
    assert HOURS not in db.copy_texts()

    t = client_for("trener@test.local")
    def post(**data):
        return t.post(f"/copy/{HOURS}", data=data)

    r = post(text="  pon   -  pet ", index="0", part="0")                  # one cell, cleaned
    assert r.status_code == 200 and r.json() == {"ok": True, "rows": [["pon - pet", d[0][1]], d[1], d[2]], "default": False}
    assert post(text="07:00 – 21:00", index="0", part="1").json()["rows"][0] == ["pon - pet", "07:00 – 21:00"]
    assert json.loads(db.copy_texts()[HOURS]) == [["pon - pet", "07:00 – 21:00"], d[1], d[2]]   # one row, pairs
    r = post(text=" \n ", index="1", part="1")                              # emptied: the cell stays empty
    assert r.json() == {"ok": True, "rows": [["pon - pet", "07:00 – 21:00"], ["uto", ""], d[2]], "default": False}
    r = post(text="", index="1", part="0")                                  # and its other cell: the row goes
    assert r.json()["rows"] == [["pon - pet", "07:00 – 21:00"], d[2]]
    r = post(index="1", remove="1")                                         # ✕: a row goes
    assert r.json() == {"ok": True, "rows": [["pon - pet", "07:00 – 21:00"]], "default": False}
    r = post(add="1")                                                       # + Dodaj red: the placeholders, last
    assert r.json() == {"ok": True, "rows": [["pon - pet", "07:00 – 21:00"], ["dan", "sati"]], "default": False}
    assert json.loads(db.copy_texts()[HOURS]) == r.json()["rows"]

    for bad in ({"text": "x"}, {"text": "x", "part": "0"}, {"text": "x", "index": "2", "part": "0"},
                {"text": "x", "index": "-1", "part": "0"}, {"text": "x", "index": "dva", "part": "0"},
                {"remove": "1"}, {"index": "2", "remove": "1"}):              # no such row
        r = post(**bad)
        assert r.status_code == 400 and r.json() == {"ok": False, "error": "Nepoznat red."}, bad
    for bad in ({"text": "x", "index": "0"}, {"text": "x", "index": "0", "part": "2"},
                {"text": "x", "index": "0", "part": "dani"}):              # no such cell
        r = post(**bad)
        assert r.status_code == 400 and r.json() == {"ok": False, "error": "Nepoznato polje."}, bad
    r = post(text="x" * 2001, index="0", part="1")                          # the cap, every text's
    assert r.status_code == 400 and r.json()["error"] == "Najviše 2000 znakova — ovo ih ima 2001."
    assert post(text="x" * 2000, index="0", part="1").status_code == 200
    r = post(text=" Prvi red \n\n\n drugi red ", index="0", part="0")      # a cell keeps its line breaks
    assert r.json()["rows"][0][0] == "Prvi red\n\ndrugi red"
    assert json.loads(db.copy_texts()[HOURS]) == r.json()["rows"]           # nothing refused was stored
    for n in range(2, 12):                                                  # up to twelve rows...
        assert len(post(add="1").json()["rows"]) == n + 1
    r = post(add="1")                                                       # ...and not one more
    assert r.status_code == 400 and r.json() == {"ok": False, "error": "Najviše 12 redova."}
    assert len(json.loads(db.copy_texts()[HOURS])) == 12
    assert t.post(f"/copy/{HOURS}/slika", files={"slika": ("foto.jpg", picture(300, 200), "image/jpeg")}).json() == {
        "ok": False, "error": "Ovdje ne ide slika."}                        # no photo, as a text slot

    r = post(text="ignoriran", reset="1")                                   # Zadano: the whole default table
    assert r.json() == {"ok": True, "rows": d, "default": True} and HOURS not in db.copy_texts()
    for _ in d:                                                             # an emptied table stays empty...
        assert post(index="0", remove="1").status_code == 200
    assert db.copy_texts()[HOURS] == "[]"
    with db.session_scope() as s:                                           # who wrote it
        assert s.get(SiteCopy, HOURS).updated_by == uid
    page = TestClient(app).get("/").text                                    # ...a visitor gets no table
    assert "<table" not in page.split('id="kontakt"')[1].split("</section>")[0]
    after = t.get("/").text.split(f'<table data-rows="{HOURS}" data-max="2000" data-max-rows="12" '
                                  'data-label="Radno vrijeme" data-cell0="dani" data-cell1="sati">')[1]
    assert "<tr>" not in after.split("</table>")[0]                         # ...the editor an empty one to add to
    assert after.split("</table>")[1].lstrip().startswith('<button type="button" class="act ed-add">+ Dodaj red</button>')


def test_the_landing_prints_the_hours_from_their_rows():
    """The hours print from the slot: on a fresh database its three default
    rows, the days in td.d, the hours beside them; an emptied cell an empty
    <td> for a visitor (an empty .ed to click for the editor); a removed row
    is gone. The editor's cells name their row and cell in the bar ("Radno
    vrijeme, red 2: sati"), each row has its ✕, the table its "+ Dodaj
    red", which is gone at twelve rows."""
    make_user("trener@test.local", is_trainer=True)
    page = TestClient(app).get("/").text
    assert hours(page).count("<tr>") == 3
    for days, time in copy.SLOTS[HOURS].default:
        assert f'<tr><td class="d"><span class="t">{days}</span></td><td><span class="t">{time}</span></td></tr>' in page
    t = client_for("trener@test.local")
    t.post(f"/copy/{HOURS}", data={"text": "", "index": "1", "part": "1"})    # "uto", nothing beside it
    t.post(f"/copy/{HOURS}", data={"index": "2", "remove": "1"})              # sub · ned: gone
    table = hours(TestClient(app).get("/").text)
    assert '<tr><td class="d"><span class="t">uto</span></td><td></td></tr>' in table
    assert table.count("<tr>") == 2 and "sub · ned" not in table and "zatvoreno" not in table
    table = hours(t.get("/").text)
    cell = ('<td><span class="ed t" data-copy="info.hours.rows" data-index="1" data-part="1" data-max="2000" '
            'data-label="Radno vrijeme, red 2: sati"></span></td>')
    assert ('<tr><td class="d"><span class="ed t" data-copy="info.hours.rows" data-index="1" data-part="0" data-max="2000" '
            f'data-label="Radno vrijeme, red 2: dani">uto</span></td>{cell}<td class="ed-xc"><button type="button" '
            'class="ed-x" aria-label="Ukloni red 2">✕</button></td></tr>') in table
    assert table.count('class="ed-x"') == 2
    assert '<button type="button" class="act ed-add">+ Dodaj red</button>' in t.get("/").text
    for _ in range(10):
        t.post(f"/copy/{HOURS}", data={"add": "1"})
    page = t.get("/").text                                                  # twelve: no more to add
    assert hours(page).count("<tr>") == 12 and '<button type="button" class="act ed-add" hidden>+ Dodaj red</button>' in page


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


# ---------- the gym's cards: rows, edited through virtual keys ----------

def gym_examples() -> list[int]:
    """The gym's two cards, Dvorana and Individualno, as the migration
    leaves a database where nobody edited them (copy.GYM_CARD_EXAMPLES,
    their plans with them): their ids, in order."""
    return [db.add_gym_card(None, example).id for example in copy.GYM_CARD_EXAMPLES]


def gym_texts(card_id: int) -> dict:
    """A gym card's row, spelled as copy.GYM_CARD_EXAMPLES spells one."""
    g = db.gym_card(card_id)
    return {**{column: getattr(g, column) for column in copy.GYM_CARD_COLUMNS.values()},
            "points": tuple(g.point_items), "plans": g.plans}


def test_a_gym_cards_texts_are_edited_in_place_through_their_virtual_keys():
    make_user("ivan@test.local"); uid = make_user("trener@test.local", is_trainer=True)
    one, two = gym_examples()
    key = f"dvorana.{one}.title"
    assert TestClient(app).post(f"/copy/{key}", data={"text": "x"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{key}", data={"text": "x"}).status_code == 403
    assert db.gym_card(one).title == "Dvorana"

    t = client_for("trener@test.local")
    r = t.post(f"/copy/{key}", data={"text": "  Grupa   do\n 10  "})           # cleaned as a slot's text is
    assert r.status_code == 200 and r.json() == {"ok": True, "text": "Grupa do\n10", "default": False}
    assert db.gym_card(one).title == "Grupa do\n10" and db.gym_card(one).updated_by == uid
    page = TestClient(app).get("/").text                                    # everyone reads it, in a .t span
    assert '<h3><span class="t">Grupa do\n10</span></h3>' in page and f'data-copy="{key}"' not in page
    assert (f'<h3><span class="ed t" data-copy="{key}" data-max="2000" data-label="Kartica 1: naziv">'
            "Grupa do\n10</span></h3>") in t.get("/").text                 # the editor's span names its card
    words = {"lead": "podnaslov", "price": "mjesečna cijena", "unit": "uz mjesečnu cijenu",
             "year_price": "godišnja cijena", "year_unit": "uz godišnju cijenu"}
    third = db.add_gym_card(None).id                                        # a card of no plan: its own price shows
    for field in words:
        r = t.post(f"/copy/dvorana.{third}.{field}", data={"text": f"Novo: {field}"})
        assert r.json() == {"ok": True, "text": f"Novo: {field}", "default": False}, field
        assert getattr(db.gym_card(third), field) == f"Novo: {field}", field
    page = t.get("/").text
    for field, word in words.items():
        assert (f'data-copy="dvorana.{third}.{field}" data-max="2000" data-label="Kartica 3: {word}">'
                f"Novo: {field}</span>") in page, field

    r = t.post(f"/copy/{key}", data={"text": "x" * 2001})                   # the cap, as a slot's
    assert r.status_code == 400 and r.json()["error"] == "Najviše 2000 znakova — ovo ih ima 2001."
    assert t.post(f"/copy/{key}", data={"text": "x" * 2000}).status_code == 200
    for field in ("title", "lead", "price", "unit", "year_price", "year_unit"):
        blank = copy.GYM_CARD_BLANK[field]                                  # empty: the new card's placeholder,
        t.post(f"/copy/dvorana.{two}.{field}", data={"text": "Nešto."})      # as an emptied slot's default
        r = t.post(f"/copy/dvorana.{two}.{field}", data={"text": " \n \n\n "})
        assert r.json() == {"ok": True, "text": blank, "default": True}, field
        assert getattr(db.gym_card(two), field) == blank, field
        t.post(f"/copy/dvorana.{two}.{field}", data={"text": "Opet."})       # reset=1 (Zadano) does the same
        r = t.post(f"/copy/dvorana.{two}.{field}", data={"text": "ignoriran", "reset": "1"})
        assert r.json() == {"ok": True, "text": blank, "default": True}, field
    assert db.gym_card(two).plans == copy.GYM_CARD_EXAMPLES[1]["plans"]     # its plans: no key reaches them

    for bad in ("dvorana.99.title", f"dvorana.{one}.naziv", f"dvorana.{one}.shown", f"dvorana.{one}.plans",
                f"dvorana.{one}.image", f"dvorana.{one}.position", f"dvorana.{one}.Title", f"dvorana.{one}",
                f"dvorana.{one}.title.x", "dvorana.x.title", f"dvorana.0{one}.title", "dvorana.1234567890.title",
                f"aktualno.{one}.title", "offer.dvorana.title", "offer.individualno.points"):   # no such card, field or slot
        assert t.post(f"/copy/{bad}", data={"text": "x"}).status_code == 404, bad
    assert db.copy_texts() == {}                                            # none of it lands in site_copy


def test_a_gym_cards_bullets_are_a_list_edited_item_by_item():
    """dvorana.<id>.points is edited as a list slot is: an item by its
    index, n appends, an empty text removes, at most 12 items of 2000
    characters; Zadano (reset=1) puts the new card's two placeholder
    bullets back. The row keeps them as a JSON array."""
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    one, _ = gym_examples()
    key, d = f"dvorana.{one}.points", list(copy.GYM_CARD_EXAMPLES[0]["points"])
    assert TestClient(app).post(f"/copy/{key}", data={"text": "x", "index": "0"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{key}", data={"text": "x", "index": "0"}).status_code == 403

    t = client_for("trener@test.local")
    def post(**data):
        return t.post(f"/copy/{key}", data=data)

    r = post(text="  Male grupe   do 10 polaznika ", index="0")              # edit one item (prod's own words)
    first = "Male grupe do 10 polaznika"
    assert r.status_code == 200 and r.json() == {"ok": True, "items": [first, d[1], d[2]], "default": False}
    r = post(text="Četvrta stavka", index="3")                              # index == count appends
    assert r.json()["items"] == [first, d[1], d[2], "Četvrta stavka"]
    assert json.loads(db.gym_card(one).points) == r.json()["items"]         # the row's column, a JSON array
    page = TestClient(app).get("/").text                                    # everyone reads it...
    assert '<li><span class="t">Četvrta stavka</span></li>' in page and f'data-copy="{key}"' not in page
    page = t.get("/").text                                                  # ...the editor gets a span per item
    assert page.count(f'data-copy="{key}"') == 4
    assert f'<ul data-list="{key}" data-max="2000" data-max-items="12" data-label="Kartica 1: stavka">' in page

    r = post(text="", index="1")                                            # empty text removes the item
    left = [first, d[2], "Četvrta stavka"]
    assert r.json() == {"ok": True, "items": left, "default": False}
    assert post(text="").json()["items"] == left                            # no index: nothing to remove
    assert post(text="  ", index="3").json()["items"] == left               # nothing at n
    for bad in ({"text": "x"}, {"text": "x", "index": "9"}, {"text": "x", "index": "-1"}, {"text": "x", "index": "dva"}):
        assert post(**bad).status_code == 400, bad
    for n in range(3, 12):                                                  # up to twelve...
        assert post(text=f"Stavka {n}", index=str(n)).status_code == 200
    r = post(text="Trinaesta", index="12")                                  # ...and not one more
    assert r.status_code == 400 and r.json()["error"] == "Najviše 12 stavki."
    r = post(text="x" * 2001, index="0")
    assert r.status_code == 400 and r.json()["error"] == "Najviše 2000 znakova — ovo ih ima 2001."
    assert len(db.gym_card(one).point_items) == 12

    r = post(text="ignoriran", reset="1")                                   # Zadano: the new card's two bullets
    blank = list(copy.GYM_CARD_BLANK["points"])
    assert r.json() == {"ok": True, "items": blank, "default": True} and db.gym_card(one).point_items == blank
    for _ in blank:                                                         # an emptied list stays empty...
        post(text="", index="0")
    assert db.gym_card(one).points == "[]"
    dvorana = TestClient(app).get("/").text.split('id="dvorana"')[1].split('class="card offer')[1]
    assert "<ul>" not in dvorana and "Grupni treninzi u Dubravi." in dvorana   # ...and a visitor sees no bullets
    assert f'data-list="{key}"' in t.get("/").text                          # the editor can still add one
    assert db.copy_texts() == {}


def test_a_gym_card_is_switched_on_and_off_and_takes_nothing_else():
    make_user("ivan@test.local"); make_user("trener@test.local", is_trainer=True)
    one, _ = gym_examples()
    key = f"dvorana.{one}.show"
    assert TestClient(app).post(f"/copy/{key}", data={"text": "off"}).status_code == 401
    assert client_for("ivan@test.local").post(f"/copy/{key}", data={"text": "off"}).status_code == 403
    assert db.gym_card(one).shown is True

    t = client_for("trener@test.local")
    r = t.post(f"/copy/{key}", data={"text": "off"})                        # answered as a FlagSlot is
    assert r.status_code == 200 and r.json() == {"ok": True, "on": False, "default": False}
    assert db.gym_card(one).shown is False
    r = t.post(f"/copy/{key}", data={"text": "on"})
    assert r.json() == {"ok": True, "on": True, "default": False} and db.gym_card(one).shown is True
    for bad in ("maybe", "", " off", "OFF", "1"):                          # exactly "on" or "off"
        r = t.post(f"/copy/{key}", data={"text": bad})
        assert r.status_code == 400 and r.json() == {"ok": False, "error": "Nepoznata vrijednost."}, bad
    assert db.gym_card(one).shown is True                                   # a refused value changes nothing
    t.post(f"/copy/{key}", data={"text": "off"})                            # reset=1: on again
    r = t.post(f"/copy/{key}", data={"text": "off", "reset": "1"})
    assert r.json() == {"ok": True, "on": True, "default": True} and db.gym_card(one).shown is True
    assert f'class="ed-flag" data-copy="{key}" data-label="Kartica 1: prikazano"' in t.get("/").text
    assert db.copy_texts() == {}


ADD_GYM = '<form method="post" action="/dvorana/nova" class="ed-add-gym"><button type="submit" class="act">+ Dodaj karticu</button></form>'
DROP_GYM = '<button type="submit" aria-label="Obriši karticu">Obriši karticu</button></form>'


def test_the_editor_adds_gym_cards_up_to_eight_and_deletes_them():
    make_user("ivan@test.local"); uid = make_user("trener@test.local", is_trainer=True)
    for path in ("/dvorana/nova", "/dvorana/1/obrisi"):                    # a guest logs in first; a client may not
        r = TestClient(app).post(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", path
        assert client_for("ivan@test.local").post(path, follow_redirects=False).status_code == 403, path
    assert db.gym_cards(all=True) == []

    t = client_for("trener@test.local")                                     # none at all: the editor's section is
    gym = t.get("/").text.split('id="dvorana"')[1].split("</section>")[0]  # empty but for "+ Dodaj karticu"
    assert 'class="card offer' not in gym and ADD_GYM in gym
    assert 'id="dvorana"' not in TestClient(app).get("/").text             # a visitor gets nothing

    one, two = gym_examples()
    for _ in range(6):
        r = t.post("/dvorana/nova", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/#dvorana"
    cards = db.gym_cards(all=True)
    assert [g.position for g in cards] == list(range(1, 9)) and [g.id for g in cards[:2]] == [one, two]
    texts = {column: copy.GYM_CARD_BLANK[column] for column in copy.GYM_CARD_COLUMNS.values()}
    for g in cards[2:]:                                                     # the placeholders, shown, no plan
        assert {column: getattr(g, column) for column in texts} == texts
        assert g.point_items == list(copy.GYM_CARD_BLANK["points"]) and g.shown and g.plans == "" and g.plan_keys == []
        assert g.updated_by == uid
    assert TestClient(app).get("/").text.split('id="dvorana"')[1].count('class="card offer') == 8
    page = t.get("/").text
    assert ADD_GYM not in page and page.count(DROP_GYM) == 8                # full: no "+ Dodaj karticu"
    for n, g in enumerate(cards, start=1):                                  # each card's own, and its place in the bar
        assert f'<form method="post" action="/dvorana/{g.id}/obrisi" class="ed-gym-x">{DROP_GYM}' in page
        assert f'data-copy="dvorana.{g.id}.title" data-max="2000" data-label="Kartica {n}: naziv">' in page
    r = t.post("/dvorana/nova", follow_redirects=False)                     # a ninth is refused, and he is told
    assert r.status_code == 303 and r.headers["location"] == "/?error=Najvi%C5%A1e+8+kartica.#dvorana"
    assert len(db.gym_cards(all=True)) == 8
    assert '<span>Najviše 8 kartica.</span>' in t.get(r.headers["location"]).text

    assert client_for("ivan@test.local").post(f"/dvorana/{one}/obrisi", follow_redirects=False).status_code == 403
    assert db.gym_card(one) is not None
    r = t.post(f"/dvorana/{one}/obrisi", follow_redirects=False)            # Obriši karticu: the card goes,
    assert r.status_code == 303 and r.headers["location"] == "/#dvorana"   # Dvorana's as any other
    assert db.gym_card(one) is None and "Dvorana</span></h3>" not in TestClient(app).get("/").text
    r = t.post(f"/dvorana/{one}/obrisi", follow_redirects=False)            # gone already: nothing to do
    assert r.status_code == 303 and r.headers["location"] == "/#dvorana" and len(db.gym_cards(all=True)) == 7
    assert ADD_GYM in t.get("/").text                                       # room again,
    t.post("/dvorana/nova")                                                 # and a new card comes last
    assert [g.position for g in db.gym_cards(all=True)] == list(range(2, 10))


def test_two_quick_gym_adds_never_pass_the_cap():
    """Eight is the cap even when taps race, as for the announcements: with
    six cards, six adds at once land two (the count and the next position
    are read under a lock), and no position is taken twice."""
    for _ in range(6):
        db.add_gym_card(None)
    landed = []
    threads = [threading.Thread(target=lambda: landed.append(db.add_gym_card(None) is not None)) for _ in range(6)]
    for th in threads: th.start()
    for th in threads: th.join()
    assert sorted(landed) == [False] * 4 + [True] * 2
    assert [g.position for g in db.gym_cards(all=True)] == list(range(1, 9))


def test_the_migration_turns_the_two_gym_slots_into_rows():
    """78d539161185: the offer.dvorana.* / offer.individualno.* rows of
    site_copy become the first two gym cards, what was edited where it was
    (on prod the gym owner had retyped Dvorana's title, "Grupa", and its
    first bullet: they must survive), else the old defaults (its own copy,
    which must agree with copy.GYM_CARD_EXAMPLES), each with its plans; the
    folded rows gone, the rest kept. And back, only what differs from the
    defaults."""
    mig = _migration("78d539161185_gym_cards.py"); uid = make_user("trener@test.local", is_trainer=True)
    with db.engine.begin() as conn:                                         # nobody edited them: the two examples
        mig.fold_gym(conn)
    cards = db.gym_cards()
    assert [gym_texts(g.id) for g in cards] == [dict(example) for example in copy.GYM_CARD_EXAMPLES]
    assert [(g.position, g.shown, g.updated_by) for g in cards] == [(1, True, None), (2, True, None)]
    with db.engine.begin() as conn:                                         # and back: nothing differs, no row
        mig.unfold_gym(conn)
    assert db.copy_texts() == {}
    for g in cards:
        db.delete_gym_card(g.id)

    bullets = ["Male grupe do 10 polaznika", "8, 12 ili 16 treninga mjesečno", "Termin rezerviraš u aplikaciji"]
    for key, text in [("offer.dvorana.title", "Grupa"), ("offer.dvorana.points", json.dumps(bullets, ensure_ascii=False)),
                      ("offer.individualno.year_price", "1200"), ("offer.individualno.points", "nije lista"),
                      ("hero.kicker", "Ostaje kakav jest.")]:
        db.set_copy(key, text, uid)
    with db.engine.begin() as conn:
        mig.fold_gym(conn)
    dvorana, individualno = db.gym_cards(all=True)
    assert gym_texts(dvorana.id) == {**copy.GYM_CARD_EXAMPLES[0], "title": "Grupa", "points": tuple(bullets)}
    assert (dvorana.position, dvorana.shown, dvorana.updated_by) == (1, True, uid)
    assert gym_texts(individualno.id) == {**copy.GYM_CARD_EXAMPLES[1], "year_price": "1200"}   # a list it cannot read: the defaults
    assert db.copy_texts() == {"hero.kicker": "Ostaje kakav jest."}         # the folded rows gone, the rest kept
    page = TestClient(app).get("/").text                                    # and the page reads the rows
    assert '<h3><span class="t">Grupa</span></h3>' in page and '<span class="t">Male grupe do 10 polaznika</span>' in page

    with db.engine.begin() as conn:                                         # the way back: what differs from the defaults
        mig.unfold_gym(conn)
    assert db.copy_texts() == {"hero.kicker": "Ostaje kakav jest.", "offer.dvorana.title": "Grupa",
                               "offer.dvorana.points": json.dumps(bullets, ensure_ascii=False),
                               "offer.individualno.year_price": "1200"}


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
    page = TestClient(app).get("/").text                                    # and the page reads them (the gym's
    assert "Treća" in page                                                  # lists: rows since 78d539161185)

    with db.engine.begin() as conn:                                         # the way back
        mig.split_points(conn)
    texts = db.copy_texts()
    assert [texts[f"offer.online.p{n}"] for n in (1, 2, 3)] == ["Prva", "Druga", "Treća"]
    assert texts["offer.individualno.p2"] == "U paru" and not [k for k in texts if k.endswith(".points")]


TIER_ADDONS = ("offer.online.addon", "offer.online2.addon", "offer.online3.addon")


def test_the_migration_folds_the_hours_into_rows_and_the_addon_into_each_tier():
    """1a7c144b582a: the six info.hours.* rows of site_copy become one
    info.hours.rows row holding the three rows as the site showed them: on
    prod the gym owner had retyped "pon - pet", "07:00 – 21:00" and
    "konzultacije po dogovoru", and they must come through; the cells nobody
    edited are the old defaults (its own copy, which must agree with
    copy.py's), and who touched the hours last, and when, is the latest of
    the six. An edited offer.addon becomes every tier's word. Nothing
    edited: nothing written. The old rows go, the rest stays. And back,
    only what differs from the defaults."""
    mig = _migration("1a7c144b582a_hours_rows.py")
    uid = make_user("trener@test.local", is_trainer=True); other = make_user("ivan@test.local")
    assert [list(row) for row in mig.OLD_HOURS] == [list(row) for row in copy.SLOTS[HOURS].default]
    assert all(mig.OLD_ADDON == copy.SLOTS[key].default for key in TIER_ADDONS) and mig.TIER_ADDONS == TIER_ADDONS
    with db.engine.begin() as conn:                                         # nobody edited them: nothing to fold,
        mig.fold_hours(conn); mig.fold_addon(conn)
    with db.engine.begin() as conn:                                         # nor to unfold
        mig.unfold_hours(conn); mig.unfold_addon(conn)
    assert db.copy_texts() == {}

    for key, text, by in [("info.hours.d1", "pon - pet", uid), ("offer.addon", "MM prehrana", uid),
                          ("info.hours.t1", "07:00 – 21:00", uid), ("hero.kicker", "Ostaje kakav jest.", uid),
                          ("info.hours.t2", "konzultacije po dogovoru", other)]:   # prod's three, the last by another
        db.set_copy(key, text, by)
    with db.session_scope() as s:
        last = s.get(SiteCopy, "info.hours.t2").updated_at
    with db.engine.begin() as conn:
        mig.fold_hours(conn); mig.fold_addon(conn)
    texts = db.copy_texts()
    assert json.loads(texts[HOURS]) == [["pon - pet", "07:00 – 21:00"], ["uto", "konzultacije po dogovoru"],
                                        ["sub · ned", "zatvoreno"]]
    assert [texts[key] for key in TIER_ADDONS] == ["MM prehrana"] * 3
    assert set(texts) == {HOURS, *TIER_ADDONS, "hero.kicker"}               # the old rows gone, the rest kept
    with db.session_scope() as s:                                           # the latest of the six
        assert (s.get(SiteCopy, HOURS).updated_at, s.get(SiteCopy, HOURS).updated_by) == (last, other)
    page = TestClient(app).get("/").text                                    # and the page reads them
    for days, time in json.loads(texts[HOURS]):
        assert f'<tr><td class="d"><span class="t">{days}</span></td><td><span class="t">{time}</span></td></tr>' in page
    assert page.count('<p class="addon"><span class="t">MM prehrana</span>') == 3

    with db.engine.begin() as conn:                                         # the way back: what differs from the defaults
        mig.unfold_hours(conn); mig.unfold_addon(conn)
    assert db.copy_texts() == {"hero.kicker": "Ostaje kakav jest.", "info.hours.d1": "pon - pet",
                               "info.hours.t1": "07:00 – 21:00", "info.hours.t2": "konzultacije po dogovoru",
                               "offer.addon": "MM prehrana"}
    # best effort, as its docstring says: an emptied cell goes back as an
    # empty text, a removed row as its old default (three fixed rows)
    for key in ("offer.addon", "info.hours.d1", "info.hours.t1", "info.hours.t2"):
        db.reset_copy(key)
    db.set_copy(HOURS, copy.dump_rows([["pon - pet", ""], ["uto", "individualni termini"]]), uid)
    with db.engine.begin() as conn:
        mig.unfold_hours(conn); mig.unfold_addon(conn)
    assert db.copy_texts() == {"hero.kicker": "Ostaje kakav jest.", "info.hours.d1": "pon - pet", "info.hours.t1": ""}


def test_every_slot_is_on_a_page_and_only_editors_see_the_editor():
    """Every slot is on a page the editor opens, so none is out of his reach.
    It may be on more than one (18.10.2026): a price (price.<plan>.*)
    prints on the landing's card and on /moja-clanarina, and so does an
    add-on amount (addon.*: the landing's cards, the prehrana plan's hint),
    one fact in both places, and a save updates every copy of it on the
    page it is made on. A list, a switch and a photo keep their shape on
    each page they are on; a visitor and a client get no editor markup, the
    announcements' and the gym's cards' (rows, not slots) included."""
    make_user("ivan@test.local", plans=("grupni",)); make_user("trener@test.local", is_trainer=True)
    examples(); gym_examples()
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
                if isinstance(slot, copy.RowsSlot):     # one table, an editable span per cell
                    assert page.count(f'data-rows="{key}"') == 1, key
                    assert page.count(f'data-copy="{key}"') == 2 * len(slot.default), key
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
                for mark in ("data-copy", "copyToggle", "data-list", "data-rows", "data-part", 'class="ed-xc"',
                             'class="ed-x"', 'ed-add"', 'class="ed-flag"', "data-flag",
                             'class="ed-img"', "data-image", 'class="ed-ann-x"', 'class="ed-add-ann"', 'action="/aktualno/',
                             'class="ed-pills"', 'class="ed-gym-x"', 'class="ed-add-gym"', 'action="/dvorana/', "; --cols-edit:"):
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
    landing and the online plan's card on /moja-clanarina, and the same for
    a gym card that stands for a plan (a row since 20.10.2026): Dvorana's
    price is grupni's slot, the one /moja-clanarina's grupni card prints.
    The dvorana add-on's amount the same, in the prehrana plan's hint on
    /moja-clanarina (one slot, no number of its own there), and on no
    landing card: the gym's cards carry no add-on line since 20.10.2026.
    Individualno's line reads the two other plans' slots. "Zadano" brings
    the shop's number back and leaves no row."""
    make_user("ivan@test.local", plans=("online",)); make_user("trener@test.local", is_trainer=True)
    gym_examples()
    t = client_for("trener@test.local")
    for key, text in (("price.online.amount", "45"), ("addon.dvorana", "4"), ("price.grupni.amount", "65"),
                      ("price.poluindividualni.amount", "28"), ("price.rehabilitacija.unit", "/ dolazak")):
        assert t.post(f"/copy/{key}", data={"text": text}).json() == {"ok": True, "text": text, "default": False}, key

    page = TestClient(app).get("/").text                                    # a visitor's landing
    offer, gym = page.split('id="usluge"')[1].split('id="dvorana"')
    start = offer.split('class="card offer')[1]
    assert "45 € / mjesečno" in shown(start)
    assert offer.count('+<span class="t">5</span> <span class="t">€ / mjesečno</span>') == 3   # the online tiers keep theirs
    dvorana, individualno = gym.split('class="card offer')[1:3]
    for c in (dvorana, individualno):                                      # no add-on line on the gym's cards
        assert 'class="addon"' not in c and '+<span class="t">4</span>' not in c
    assert "u dvoje ili troje 28 € / trening · rehabilitacija od 30 € / dolazak" in shown(individualno)
    assert "65 € / paket" in shown(dvorana) and "60–80" not in dvorana     # the gym's plan card: grupni's slot
    mine = client_for("ivan@test.local").get("/moja-clanarina").text
    assert "Cijena 45 € / mjesečno" in shown(card_on(mine, "online"))
    assert "65 € / paket" in shown(card_on(mine, "grupni")) and "60–80" not in card_on(mine, "grupni")
    assert "od 3 € / mjesečno 4 € uz dvoranu, 5 € uz online" in shown(card_on(mine, "prehrana"))

    page = t.get("/").text                                                  # the editor gets them as slots
    start = page.split('id="usluge"')[1].split('class="card offer')[1]
    assert ('<b><span class="ed t" data-copy="price.online.amount" data-max="2000" '
            'data-label="Cijena · online: iznos">45</span> €</b>') in start
    dvorana, individualno = page.split('id="dvorana"')[1].split('class="card offer')[1:3]
    assert ('<b><span class="ed t" data-copy="price.grupni.amount" data-max="2000" '
            'data-label="Cijena · grupni: iznos">65</span> €</b>') in dvorana   # the same slot, his to open here
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


def test_the_words_around_a_price_are_free_text_and_the_number_its_own_slot():
    """20.10.2026 (the owner, of Individualno's line: "a third option where
    there is free text, but the number has to be input somewhere separately
    and if there is no input number, it falls back to the default"): the
    words before each price in the line are slots (price.<plan>.word), the
    number stays the plan's amount slot (on /moja-clanarina too), and an
    emptied amount is its default again on both pages. The QMove tiers'
    MojiMakrosi line the same way ("a similar treatment of the three QMOVE
    tabs"): each tier's own words before and after the one amount
    (offer.online*.addon / .addon_unit; addon.online, which all three
    print), so an edit on one tier changes that tier's line only."""
    make_user("ivan@test.local", plans=("online",)); make_user("trener@test.local", is_trainer=True)
    gym_examples()
    t = client_for("trener@test.local")

    def line(page: str) -> str:                     # Individualno's line, as a visitor reads it
        card = page.split('id="dvorana"')[1].split('class="card offer')[2]
        return shown(card.split('<p class="price-note">')[1].split("</p>")[0])

    assert line(TestClient(app).get("/").text) == "u dvoje ili troje 25 € / trening · rehabilitacija od 30 € / tretman"
    r = t.post("/copy/price.poluindividualni.word", data={"text": "  u   paru "})
    assert r.json() == {"ok": True, "text": "u paru", "default": False}
    assert t.post("/copy/price.rehabilitacija.word", data={"text": "rehab"}).json()["text"] == "rehab"
    assert t.post("/copy/price.poluindividualni.amount", data={"text": "28"}).json()["text"] == "28"
    page = TestClient(app).get("/").text
    assert line(page) == "u paru 28 € / trening · rehab od 30 € / tretman"
    dvorana = page.split('id="dvorana"')[1].split('class="card offer')[1]  # its room copy follows the words
    assert '<p class="price-note room" aria-hidden="true"><span class="t">u paru</span>' in dvorana
    r = t.post("/copy/price.poluindividualni.amount", data={"text": " "})  # no number: the default comes back,
    assert r.json() == {"ok": True, "text": "25", "default": True}
    assert line(TestClient(app).get("/").text) == "u paru 25 € / trening · rehab od 30 € / tretman"
    assert "25 € / trening" in shown(card_on(client_for("ivan@test.local").get("/moja-clanarina").text, "poluindividualni"))
    individualno = t.get("/").text.split('id="dvorana"')[1].split('class="card offer')[2]   # the editor's: slots
    assert ('<span class="ed t" data-copy="price.poluindividualni.word" data-max="2000" '
            'data-label="Cijena · poluindividualni: tekst ispred iznosa">u paru</span>') in individualno
    assert ('<span class="ed t" data-copy="price.rehabilitacija.word" data-max="2000" '
            'data-label="Cijena · rehabilitacija: tekst ispred iznosa">rehab</span>') in individualno
    t.post("/copy/price.poluindividualni.word", data={"reset": "1"})       # Zadano: the shipped words
    assert line(TestClient(app).get("/").text).startswith("u dvoje ili troje 25 € / trening · rehab")

    def addons(page: str) -> list[str]:             # the three tiers' MojiMakrosi lines, as a visitor reads them
        tiers = page.split('id="usluge"')[1].split('id="dvorana"')[0].split('class="card offer')[1:]
        return [" ".join(unescape(re.sub(r"<[^>]+>", "", c.split('<p class="addon">')[1].split("</p>")[0])).split())
                for c in tiers]

    assert addons(TestClient(app).get("/").text) == ["MojiMakrosi prehrana +5 € / mjesečno"] * 3
    assert t.post("/copy/offer.online2.addon_unit", data={"text": "€ mjesečno uz PRO"}).json()["default"] is False
    assert addons(TestClient(app).get("/").text) == ["MojiMakrosi prehrana +5 € / mjesečno",
                                                     "MojiMakrosi prehrana +5 € mjesečno uz PRO",
                                                     "MojiMakrosi prehrana +5 € / mjesečno"]   # PRO's line only
    t.post("/copy/offer.online3.addon", data={"text": "Prehrana"}); t.post("/copy/addon.online", data={"text": "6"})
    assert addons(TestClient(app).get("/").text) == ["MojiMakrosi prehrana +6 € / mjesečno",
                                                     "MojiMakrosi prehrana +6 € mjesečno uz PRO", "Prehrana +6 € / mjesečno"]
    offer = t.get("/").text.split('id="usluge"')[1].split('id="dvorana"')[0]
    for n, slot in enumerate(("offer.online", "offer.online2", "offer.online3"), start=1):   # each tier's own slots
        assert offer.count(f'data-copy="{slot}.addon" data-max="2000" data-label="Online {n}: dodatak za prehranu">') == 1
        assert offer.count(f'data-copy="{slot}.addon_unit" data-max="2000" data-label="Online {n}: uz cijenu dodatka">') == 1
    assert offer.count('data-copy="addon.online"') == 3 and "offer.addon" not in copy.SLOTS


# ---------- the layout, measured in a browser ----------
#
# No slot has a design limit since 16.10.2026 (src/qmt/copy.py): the copy
# comes first, and a design pass fits the boxes to it once it is final. So
# this proves no design at a limit; it proves the net under the texts. Long
# texts (300 characters, lists of 12 items of 60, the hours' table 12 rows of
# 300-character cells, its ✕s too in edit mode) and line breaks may make a
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
# online tiers and the gym's two (its rows, as the migration leaves them; the
# editor's third is GYM's, below). On a wide screen the tiers are three columns
# and the gym two; below 900px each is a swipe row of cards 92% as wide as its
# content (a card and a sliver of the next, the owner's call of 17.10.2026)
# with a dot per card (made by the script, so the count and the labels follow
# the cards), and starts on its featured card, centred, with that card's dot
# lit: the tiers on QMove PRO in the middle, the gym (no featured card) on its
# first. The shown prices are level across a row either way, at their bottom
# edge as in MEASURE (the featured tier hangs 16px past its neighbours on a
# desktop, so the row check above can miss it; this one cannot). The tiers
# carry the MojiMakrosi add-on line, the gym's cards none (20.10.2026).
LANDING = r"""([w, strict]) => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().width > 0; };
  const out = [], top = el => el.getBoundingClientRect().top, price = card => [...card.querySelectorAll('.price')].find(vis);
  const level = (cards, what) => { if (!strict) return;       // one unbreakable word: it only must not widen
    const b = cards.map(c => Math.round(price(c).getBoundingClientRect().bottom));
    if (Math.max(...b) - Math.min(...b) > 1) out.push(`${what} prices not level: ${b.join(', ')}`); };
  // [section, cards, name, how far a card may stand out of the row on a desktop, the card a phone starts on, an add-on line]
  for (const [sec, n, what, slack, first, addon] of [['#usluge', 3, 'tier', 17, 1, true], ['#dvorana', 2, 'gym', 1, 0, false]]) {
    const row = document.querySelector(`${sec} .swipe-row`), cards = row ? [...row.children] : [];
    const dots = [...document.querySelectorAll(`${sec} .dots button`)].filter(vis);
    if (cards.length !== n || !cards.every(c => c.classList.contains('offer'))) { out.push(`${cards.length} ${what} cards`); continue; }
    const addons = cards.filter(c => c.querySelector('.addon')).length;
    if (addons !== (addon ? n : 0)) out.push(`${addons} of the ${n} ${what} cards carry the add-on line`);
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

# The gym's cards (#dvorana; rows since 20.10.2026), n of them shown, measured
# with the default texts (a price is one line, so their tops can be compared).
# From 900px a grid of min(n, 3) columns, each at most 380px: two cards the
# 760px they always were, three as wide as the tiers' row; centred, the shown
# prices' tops level in each row of the grid. Below 900px the swipe row: every
# card 92% of the row's content, a sliver of the next in view, a dot per card
# (none for one). Never wider than the page.
GYM = r"""(n) => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().width > 0; };
  const out = [], row = document.querySelector('#dvorana .gym-grid'), de = document.documentElement, box = el => el.getBoundingClientRect();
  if (!row) return ['no gym row'];
  const cards = [...row.children].filter(vis), price = c => [...c.querySelectorAll('.price')].find(vis);
  if (cards.length !== n) out.push(`${cards.length} gym cards shown, not ${n}`);
  if (de.scrollWidth - de.clientWidth > 0) out.push(`the page overflows by ${de.scrollWidth - de.clientWidth}px`);
  if (innerWidth >= 900) {
    const cols = Math.min(n, 3), got = getComputedStyle(row).gridTemplateColumns.split(' ').length;
    if (got !== cols) out.push(`the gym cards are in ${got} columns, not ${cols}`);
    const r = box(row), want = Math.min(cols * 380, row.parentElement.clientWidth);
    if (Math.abs(r.width - want) > 1) out.push(`the gym row is ${r.width}px wide, not ${want}px`);
    if (Math.abs(r.left + r.width / 2 - de.clientWidth / 2) > 1) out.push(`the gym row is not centred: ${r.left}-${r.right}`);
    const rows = {};
    for (const c of cards) (rows[Math.round(box(c).top)] ||= []).push(box(price(c)).top);
    for (const tops of Object.values(rows))
      if (Math.max(...tops) - Math.min(...tops) > 1) out.push(`the gym prices' tops are not level: ${tops.map(Math.round).join(', ')}`);
  } else {
    const cs = getComputedStyle(row), room = row.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    cards.forEach((c, i) => { const w = box(c).width;
      if (Math.abs(w - .92 * room) > 1) out.push(`gym card ${i + 1} is ${Math.round(w)}px, not 92% of its row's ${Math.round(room)}px`); });
    if (cards.length > 1 && box(row).right - box(cards[1]).left < 8) out.push('no sliver of the second gym card in view');
    const dots = [...document.querySelectorAll('#dvorana .dots button')].filter(vis);
    if (dots.length !== (n > 1 ? n : 0)) out.push(`${dots.length} dots under ${n} gym cards`);
  }
  return out;
}"""

# The gym's cards in edit mode on a phone: one under the other, each the
# row's width, a grid that does not scroll, no dots; the switch and "Obriši
# karticu" side by side at a card's top, and nothing of a card outside it;
# "+ Dodaj karticu" under them; nothing wider than the page.
GYM_EDIT = r"""() => {
  const vis = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const out = [], row = document.querySelector('#dvorana .gym-grid'), de = document.documentElement, box = el => el.getBoundingClientRect();
  const cards = [...row.children].filter(vis), cs = getComputedStyle(row);
  const room = row.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  if (cs.display !== 'grid' || row.scrollWidth > row.clientWidth) out.push(`the gym row is ${cs.display}, ${row.scrollWidth - row.clientWidth}px to scroll`);
  if (!cards.every((c, i) => !i || box(c).top >= box(cards[i - 1]).bottom - 1)) out.push('the gym cards are not one under the other');
  cards.forEach((c, i) => { if (Math.abs(box(c).width - room) > 1) out.push(`gym card ${i + 1} is ${box(c).width}px, its row's ${room}px`); });
  if (getComputedStyle(row.nextElementSibling).display !== 'none') out.push('dots under the stacked gym cards');
  if (de.scrollWidth - de.clientWidth > 0) out.push(`the page overflows by ${de.scrollWidth - de.clientWidth}px`);
  for (const c of cards) { const b = box(c), f = c.querySelector('.ed-flag'), x = c.querySelector('.ed-gym-x > button');
    if (!f || !x || !vis(f) || !vis(x)) { out.push("a gym card without its pills"); continue; }
    if (Math.abs(box(f).top - box(x).top) > 1) out.push("a gym card's pills are not side by side");
    for (const el of c.querySelectorAll('.ed-flag, .ed-gym-x > button, span.t')) { if (!vis(el)) continue; const e = box(el);
      if (e.left < b.left - 1 || e.right > b.right + 1 || e.top < b.top - 1 || e.bottom > b.bottom + 1)
        out.push(`"${el.textContent.trim().slice(0, 12)}…" leaves its gym card`); } }
  const add = document.querySelector('#dvorana .ed-add-gym');
  if (!add || !vis(add) || box(add).top < box(row).bottom - 1) out.push('no "+ Dodaj karticu" under the gym cards');
  return out;
}"""

# Mjesečno / Godišnje: a switch under each row (the tiers', the gym's), each
# its own section's choice since 20.10.2026 (the owner: "unlink them"): the
# tiers open on Godišnje, the gym on Mjesečno. Every card of a section shows
# exactly its own switch's price, and each switch says it.
PERIOD = r"""([tiers, gym]) => {
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && el.getBoundingClientRect().width > 0; };
  const want = {usluge: tiers, dvorana: gym}, out = [];
  for (const c of document.querySelectorAll('#usluge .offer, #dvorana .offer')) {
    const sec = c.closest('section').id, shown = [...c.querySelectorAll('.price')].filter(vis).map(x => x.dataset.period);
    if (shown.join() !== want[sec]) out.push(`a card in #${sec} shows "${shown.join('+')}" for ${want[sec]}`);
  }
  const switches = [...document.querySelectorAll('.period')], where = switches.map(s => s.closest('section').id);
  if (where.join() !== 'usluge,dvorana') out.push(`switches in: ${where.join(', ')}`);
  for (const sw of switches) {
    const sec = sw.closest('section').id, said = [...sw.querySelectorAll('[aria-selected="true"]')].map(b => b.dataset.period);
    if (said.join() !== want[sec]) out.push(`the #${sec} switch says "${said.join('+')}" for ${want[sec]}`);
  }
  return out;
}"""

# The opening hours in edit mode (a rows slot, #kontakt): a ✕ per row,
# each in its own cell and a 32px target; the page and the table's column
# no wider than their boxes; nothing of the table (its cells' texts, its ✕s,
# "+ Dodaj red") outside the info card, and no ✕ past the table. Scoped, as
# EDIT_ROW is: MEASURE in edit mode would count the lists' ✕, which hangs
# past its item on purpose.
EDIT_HOURS = r"""() => {
  const vis = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const out = [], de = document.documentElement, box = el => el.getBoundingClientRect();
  const table = document.querySelector('#kontakt table[data-rows]');
  if (!table) return ['no hours table for the editor'];
  const card = box(table.closest('.info-card')), col = table.parentElement, edge = box(table).right;
  if (de.scrollWidth - de.clientWidth > 0) out.push(`the page overflows by ${de.scrollWidth - de.clientWidth}px`);
  if (col.scrollWidth - col.clientWidth > 0) out.push(`the hours' column overflows by ${col.scrollWidth - col.clientWidth}px`);
  const rows = table.querySelectorAll('tr').length, xs = [...table.querySelectorAll('.ed-x')].filter(vis);
  if (xs.length !== rows) out.push(`${xs.length} ✕ shown for ${rows} rows`);
  for (const x of xs) { const b = box(x);
    if (b.width < 32 || b.height < 32) out.push(`a row's ✕ is ${b.width}x${b.height}`);
    if (b.right > edge + 1) out.push(`a row's ✕ reaches ${Math.round(b.right - edge)}px past the table`); }
  for (const el of [...table.querySelectorAll('span.t, .ed-x'), ...col.querySelectorAll('.ed-add')].filter(vis)) { const b = box(el);
    if (b.left < card.left - 1 || b.right > card.right + 1 || b.top < card.top - 1 || b.bottom > card.bottom + 1)
      out.push(`"${el.textContent.trim().slice(0, 12)}…" leaves the info card`); }
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
    gym_examples()                                    # and the gym's two cards

    def fill(make):
        for key, slot in copy.SLOTS.items():
            if isinstance(slot, (copy.FlagSlot, copy.ImageSlot)):   # a switch and a photo, not texts
                continue
            if isinstance(slot, copy.ListSlot):         # every list 12 items long, each item 60 characters
                db.set_copy(key, copy.dump_items([make(min(slot.max_chars, ITEM))] * min(slot.max_items, ITEMS)), None)
            elif isinstance(slot, copy.RowsSlot):       # every table 12 rows long, each cell 300 characters
                db.set_copy(key, copy.dump_rows([[make(min(slot.max_chars, LONG))] * 2] * min(slot.max_rows, ITEMS)), None)
            else:                                       # every text 300 characters
                db.set_copy(key, make(min(slot.max, LONG)), None)
        for a in db.announcements(all=True):            # and every text of every announcement; they stay
            for column in copy.ANNOUNCEMENT_BLANK:      # on (both show), the photo below
                db.set_announcement_field(a.id, column, make(LONG), None)
        for g in db.gym_cards(all=True):                # every text of every gym card, its bullets 12 of 60
            for column in copy.GYM_CARD_COLUMNS.values():
                db.set_gym_card_field(g.id, column, make(LONG), None)
            db.set_gym_card_points(g.id, [make(ITEM)] * ITEMS, None)
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

    def gym_rows(pw):
        """The gym's cards as rows in a browser, the editor's way, with the
        default texts. At 1280px the two cards are two columns. In edit mode
        "+ Dodaj karticu" adds a third: the page comes back on #dvorana,
        still in edit mode, the new card last with its placeholders and no
        plan; out of edit mode the three are three columns, as wide as the
        tiers' row, the prices level, the new card's own "na upit" its price
        and "Javi nam se →" its button. At 390px they are the swipe row, a
        card 92% wide and a sliver of the next; in edit mode they stack,
        without dots, and the third switched off stays, dimmed but for its
        switch. Reloaded out of edit mode it is gone, and at 1280px the row
        is two columns again, for the editor and for a guest. Its "Obriši
        karticu" asks first ("Obriši?", the card still there); the second
        tap deletes it: the two cards the walks after this one expect. No
        page errors on the way."""
        out, errs = [], []

        def opened(w, email):
            phone = w < 600
            ctx = pw.chromium.launch().new_context(viewport={"width": w, "height": 900}, has_touch=phone, is_mobile=phone)
            pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(f"{w}px: {e}"))
            if email:
                pg.goto(server + "/login"); pg.fill("main input[name=email]", email); pg.fill("main input[name=password]", "lozinka123")
                pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
            pg.goto(server + "/#dvorana"); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
            return pg

        wide = opened(1280, "trener@test.local")
        out += [f"1280px, two cards: {p}" for p in wide.evaluate(GYM, 2)]
        wide.click("#copyToggle")
        with wide.expect_navigation():
            wide.click(".ed-add-gym button")
        wide.wait_for_load_state("networkidle")
        cards = db.gym_cards(all=True)
        third = cards[-1].id
        if len(cards) != 3 or cards[2].plan_keys or cards[2].title != copy.GYM_CARD_BLANK["title"]:
            out.append(f"+ Dodaj karticu left the cards {[(g.id, g.title[:12], g.plans) for g in cards]}")
        seen = wide.evaluate("""() => [document.body.classList.contains('editing'), location.hash,
                                       document.querySelectorAll('#dvorana .gym-grid > .offer').length]""")
        if seen != [True, "#dvorana", 3]:
            out.append(f"after + Dodaj karticu (edit mode, the address' #, the cards): {seen}")
        wide.click("#copyToggle")                                      # Gotovo: the visitor's view
        out += [f"1280px, three cards: {p}" for p in wide.evaluate(GYM, 3)]
        new = f'[data-flag="dvorana.{third}.show"]'
        seen = wide.evaluate("""(card) => { const c = document.querySelector(card);
          return [[...c.querySelectorAll('.price')].filter(p => getComputedStyle(p).display !== 'none').map(p => p.textContent.trim()).join(),
                  c.querySelector('.foot a').textContent.trim()]; }""", new)
        if seen != ["na upit", "Javi nam se →"]:
            out.append(f"the new card's price and button: {seen}")

        phone = opened(390, "trener@test.local")
        out += [f"390px, three cards: {p}" for p in phone.evaluate(GYM, 3)]
        phone.click("#copyToggle")
        out += [f"390px edit mode: {p}" for p in phone.evaluate(GYM_EDIT)]
        phone.locator(f"{new} .ed-flag").click()
        try:
            phone.wait_for_function("(card) => document.querySelector(card).classList.contains('is-off')", arg=new, timeout=5000)
        except PlaywrightTimeout:
            out.append("the new card's switch did not switch it off")
        seen = phone.evaluate("""(card) => { const c = document.querySelector(card), o = el => +getComputedStyle(el).opacity;
          return [c.getBoundingClientRect().height > 0, o(c.querySelector('h3')), o(c.querySelector('.ed-flag')),
                  o(c.querySelector('.ed-gym-x > button'))]; }""", new)
        if seen != [True, 0.55, 1, 0.55]:
            out.append(f"a gym card switched off in edit mode (shown, its title's, its switch's and its Obriši karticu's opacity): {seen}")
        out += [f"390px edit mode, one off: {p}" for p in phone.evaluate(GYM_EDIT)]
        if db.gym_card(third).shown:
            out.append("the switch was not stored")
        phone.click("#copyToggle"); phone.reload(); phone.wait_for_load_state("networkidle")   # out of edit mode
        out += [f"390px, one off: {p}" for p in phone.evaluate(GYM, 2)]
        wide.reload(); wide.wait_for_load_state("networkidle")
        out += [f"1280px, one off: {p}" for p in wide.evaluate(GYM, 2)]
        guest = opened(1280, None)
        out += [f"1280px guest, one off: {p}" for p in guest.evaluate(GYM, 2)]

        wide.click("#copyToggle")                                      # Obriši karticu: two taps
        x = wide.locator(f"{new} .ed-gym-x > button")
        x.click()
        if x.text_content() != "Obriši?" or db.gym_card(third) is None:
            out.append(f"one tap on Obriši karticu: {x.text_content()!r}, the card {'there' if db.gym_card(third) else 'gone'}")
        with wide.expect_navigation():
            x.click()
        wide.wait_for_load_state("networkidle")
        left, shown = [g.id for g in db.gym_cards(all=True)], wide.locator("#dvorana .gym-grid > .offer").count()
        if len(left) != 2 or third in left or shown != 2:
            out.append(f"the second tap on Obriši karticu left the cards {left}, {shown} on the page")
        wide.click("#copyToggle")                                      # Gotovo
        for pg in (wide, phone, guest):
            pg.context.browser.close()
        return [f"[gym rows] {p}" for p in out + [f"js: {e}" for e in errs]]

    def hours_rows(pw):
        """The opening hours as rows in a browser, the editor's way, with the
        default rows, at 390px on a touch screen and at 1280px. In edit mode
        every row carries its ✕ and the table its "+ Dodaj red". The ✕ on
        the second row asks first ("Ukloni?", the row still stored); its
        second tap removes it, and the table is redrawn with two rows,
        renumbered (the cells' indexes and bar labels, the ✕s' names), as
        stored. "+ Dodaj red" adds a third, "dan" / "sati". A cell emptied
        and saved stays, empty (the bar says so before Spremi), its row
        kept, and a visitor's table has that empty cell. Nothing of the
        table leaves its card (EDIT_HOURS); no page errors. The default rows
        are put back for the walks after this one."""
        out, errs, slot = [], [], copy.SLOTS[HOURS]
        d = [list(row) for row in slot.default]
        stored = lambda: copy.load_rows(db.copy_texts().get(HOURS), slot)
        cells = """() => [...document.querySelectorAll('#kontakt table[data-rows] tr')].map(tr =>
          [...tr.querySelectorAll('.ed')].map(s => [s.dataset.index, s.dataset.part, s.dataset.label, s.textContent])
          .concat([tr.querySelector('.ed-x').getAttribute('aria-label')]))"""
        rows = "(n) => document.querySelectorAll('#kontakt table[data-rows] tr').length === n"
        for w in (390, 1280):
            phone = w < 600
            ctx = pw.chromium.launch().new_context(viewport={"width": w, "height": 900}, has_touch=phone, is_mobile=phone)
            pg = ctx.new_page(); pg.on("pageerror", lambda e, w=w: errs.append(f"{w}px: {e}"))
            pg.goto(server + "/login"); pg.fill("main input[name=email]", "trener@test.local")
            pg.fill("main input[name=password]", "lozinka123"); pg.click("main button[type=submit]")
            pg.wait_for_load_state("networkidle")
            pg.goto(server + "/#kontakt"); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
            pg.click("#copyToggle")
            table = pg.locator("#kontakt table[data-rows]")
            add = pg.locator("#kontakt table[data-rows] + .ed-add")
            seen = [table.locator("tr").count(), table.locator(".ed-x:visible").count(), add.is_visible()]
            if seen != [3, 3, True]:
                out.append(f"{w}px: in edit mode (rows, ✕ shown, + Dodaj red shown): {seen}")
            out += [f"{w}px edit mode: {p}" for p in pg.evaluate(EDIT_HOURS)]

            x = table.locator("tr").nth(1).locator(".ed-x")              # ✕ on the second row: two taps
            x.click()
            if x.text_content() != "Ukloni?" or stored() != d:
                out.append(f"{w}px: one tap on a row's ✕: {x.text_content()!r}, stored {stored()}")
            x.click()
            try:
                pg.wait_for_function(rows, arg=2, timeout=5000)
            except PlaywrightTimeout:
                out.append(f"{w}px: the second tap on the ✕ did not leave two rows")
            want = [[["0", "0", "Radno vrijeme, red 1: dani", d[0][0]], ["0", "1", "Radno vrijeme, red 1: sati", d[0][1]], "Ukloni red 1"],
                    [["1", "0", "Radno vrijeme, red 2: dani", d[2][0]], ["1", "1", "Radno vrijeme, red 2: sati", d[2][1]], "Ukloni red 2"]]
            if pg.evaluate(cells) != want or stored() != [d[0], d[2]]:
                out.append(f"{w}px: after the ✕ the table is {pg.evaluate(cells)}, stored {stored()}")

            add.click()                                                   # + Dodaj red
            try:
                pg.wait_for_function(rows, arg=3, timeout=5000)
            except PlaywrightTimeout:
                out.append(f"{w}px: + Dodaj red added no row")
            last = pg.evaluate(cells)[-1]
            if [c[3] for c in last[:2]] != ["dan", "sati"] or last[2] != "Ukloni red 3" or stored() != [d[0], d[2], ["dan", "sati"]]:
                out.append(f"{w}px: + Dodaj red left {last}, stored {stored()}")

            hours_cell = table.locator("tr").nth(0).locator('[data-part="1"]')   # the first row's hours, emptied
            hours_cell.click()
            hours_cell.fill("")
            bar = [pg.locator(f"#copyBar {s}").text_content() for s in (".cb-label", ".cb-msg")] + [pg.locator("#cbReset").text_content()]
            if bar != ["Radno vrijeme, red 1: sati", "Prazno: Spremi ostavlja polje prazno.", "Zadano (cijela tablica)"]:
                out.append(f"{w}px: the bar over an emptied cell says {bar}")
            pg.click("#cbSave")
            try:
                pg.wait_for_function("""() => { const s = document.querySelector('#kontakt table[data-rows] [data-index="0"][data-part="1"]');
                  return s && s.textContent === '' && document.getElementById('copyBar').hidden; }""", timeout=5000)
            except PlaywrightTimeout:
                out.append(f"{w}px: the emptied cell did not save as an empty cell")
            if stored() != [[d[0][0], ""], d[2], ["dan", "sati"]] or pg.evaluate(cells)[0][1][3] != "":
                out.append(f"{w}px: after emptying a cell the table is {pg.evaluate(cells)}, stored {stored()}")
            out += [f"{w}px edit mode, changed: {p}" for p in pg.evaluate(EDIT_HOURS)]
            pg.click("#copyToggle")                                       # Gotovo: the ✕s' column goes
            if pg.evaluate("[...document.querySelectorAll('#kontakt td.ed-xc')].some(td => getComputedStyle(td).display !== 'none')"):
                out.append(f"{w}px: out of edit mode the ✕s' column still shows")
            visitor = TestClient(app).get("/").text.split('id="kontakt"')[1].split("</table>")[0]
            if f'<tr><td class="d"><span class="t">{d[0][0]}</span></td><td></td></tr>' not in visitor or visitor.count("<tr>") != 3:
                out.append(f"{w}px: a visitor's table is not the edited one with its empty cell")
            db.reset_copy(HOURS)
            ctx.browser.close()
        return [f"[hours rows] {p}" for p in out + [f"js: {e}" for e in errs]]

    def hours_edit(pg):
        """The hours table in edit mode with the walk's texts (fill(): twelve
        rows of 300-character cells): EDIT_HOURS, then Gotovo."""
        pg.click("#copyToggle")
        out = pg.evaluate(EDIT_HOURS)
        pg.click("#copyToggle")
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

    def walk(pw, email, widths, label, strict=True, lines=False, switch=(), auto=(), photos=(), adds=(), one_line=False,
             hours=()):
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
                problems += [f"{where} on load: {p}" for p in pg.evaluate(PERIOD, ["year", "month"])]   # the tiers yearly, the gym monthly
                # each switch flips its own section only: each pressed both
                # ways, the same checks after every press. The tiers'
                # Mjesečno with the gym on Godišnje, and the gym's Mjesečno
                # with the tiers on Godišnje: a press that reached the other
                # section would show. The last press leaves both as they loaded.
                for sec, period, now in (("#dvorana", "year", ["year", "year"]), ("#usluge", "month", ["month", "year"]),
                                         ("#usluge", "year", ["year", "year"]), ("#dvorana", "month", ["year", "month"])):
                    pg.click(f'{sec} .period button[data-period="{period}"]')
                    did = f"{where} {sec} {period}:"
                    problems += [f"{did} {p}" for p in pg.evaluate(PERIOD, now)]
                    problems += [f"{did} {p}" for p in pg.evaluate(MEASURE, strict)["problems"]]
                    problems += [f"{did} {p}" for p in pg.evaluate(LANDING, [w, strict])]
                if w in hours:                              # the editor's hours table in edit mode, long cells
                    problems += [f"{where} hours: {p}" for p in hours_edit(pg)]
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
        problems += gym_rows(pw)                      # the gym's cards added, hidden and deleted (the default texts)
        problems += hours_rows(pw)                    # the hours' rows removed, added and emptied (the default rows)
        fill(words)                                   # long texts: 300 characters, lists of 12, the hours 12 rows
        problems += walk(pw, None, (360, 390, 900, 1280), "words", auto=(390, 1280))
        problems += still(pw)                         # under reduced motion: never by themselves
        problems += walk(pw, "trener@test.local", (360, 390, 900, 1280), "words", switch=(390, 1280), photos=(390,),
                         adds=(390, 1280), hours=(390,))
        problems += walk(pw, "ivan@test.local", (360, 1280), "words")
        problems += banner(pw)                        # the install banner's week between asks
        db.set_announcement_field(one, "body", LINES, None)   # line breaks: the first announcement's text in three lines
        problems += walk(pw, None, (390, 1280), "lines", lines=True)
        problems += walk(pw, "trener@test.local", (390,), "lines", lines=True)
        fill(lambda n: "W" * n)                       # one unbreakable word: must wrap, never widen
        problems += walk(pw, "trener@test.local", (360, 1280), "one-word", strict=False, hours=(360,))
    print("\n".join(problems))
    assert not problems, f"{len(problems)} layout problems, listed above"


def test_the_clanarine_add_form_shows_the_select_that_fits_the_plan(server):
    """/clanarine's add form in a browser at 1280px, as the trainer: the
    plan chosen decides which of its two tier selects shows, Treninga
    mjesečno for grupni, Paket (the online plan's QMove tiers) for online,
    neither for another plan, on load and at every change (the page's
    script). Without JavaScript both show, as before. No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True)
    uid = make_user("ivan@test.local")                # no plan: every plan to add, grupni first
    form = f'form[action="/clanarine/{uid}/uplata"]:has(select[name="plan"])'
    seen, errs = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for js in (True, False):
            ctx = browser.new_context(viewport={"width": 1280, "height": 900}, java_script_enabled=js)
            pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(server + "/login"); pg.fill("main input[name=email]", "trener@test.local")
            pg.fill("main input[name=password]", "lozinka123"); pg.click("main button[type=submit]")
            pg.wait_for_load_state("networkidle")
            pg.goto(server + "/clanarine"); pg.wait_for_load_state("networkidle")
            f = pg.locator(form)
            shows = lambda: tuple(f.locator(f'select[name="{name}"]').is_visible() for name in ("sessions", "tier"))
            seen.append((js, "load", shows()))
            for plan in ("online", "grupni", "individualni", "online", "prehrana"):
                f.locator('select[name="plan"]').select_option(plan)
                seen.append((js, plan, shows()))
            ctx.close()
        browser.close()
    # (sessions shown, tier shown) after each choice
    script = [("load", (True, False)), ("online", (False, True)), ("grupni", (True, False)),
              ("individualni", (False, False)), ("online", (False, True)), ("prehrana", (False, False))]
    plain = [(step, (True, True)) for step, _ in script]
    assert seen == [(True, *s) for s in script] + [(False, *s) for s in plain], seen
    assert not errs, errs


def test_an_amount_without_a_number_prints_without_the_euro_sign():
    """"na upit" is a price the owner may type; "na upit €" is not. A number
    keeps its sign: "50 €"."""
    make_user("ivan@test.local", plans=("grupni",)); make_user("trener@test.local", is_trainer=True)
    gym_examples()                                                          # Individualno's line prints it on the landing
    db.set_copy("price.rehabilitacija.amount", "na upit", None)
    landing = TestClient(app).get("/").text
    mine = client_for("ivan@test.local").get("/moja-clanarina").text
    for page in (landing, mine):
        assert "na upit</span>" in page                                      # printed
        assert "na upit</span> €" not in page and "na upit</span>&nbsp;€" not in page   # bare
    assert "50</span> €</b>" in landing                                     # a number keeps its €
    assert "50</span> € <small>" in mine
