"""Amir's templates of a gym training (27.11.2026, build 3 of
roadmap/2026-11-27-dvoranski-treninzi-plan.md).

The owner: "In the start, there would be two templates. […]"; of a third:
"Amir will create the third template later and give it a name"; of where they
were made until now: "I dont like the fact that I need to go to 'Online
treninzi' and create a new programme there which is not applicable to gym
trainings." A template is its blocks alone ("The template's stations are
empty").

Staff's two pages under the tab Dvoranski treninzi: the list,
/dvoranski/predlosci, and a template's editor, /dvoranski/predlosci/<id>; who
reaches them (the trainer and the owner; a member 403, a guest to the login,
staff acting as a member refused as every staff page) and the way in on
staff's own /dvoranski; every write and every refusal's sentence (db and
routes: a template made, renamed, moved, deleted; a block added of each kind,
a Kružni set's numbers, a block moved and removed; the caps, 12 and 40); the
two races (the gym_templates table's lock); the member's chooser following the
templates (db.gym_templates: the ones with a block); and a walk on a phone, a
template made by staff and taken by a member. "Vrsta" off the programme forms
is tests/test_programs.py's.
"""

from __future__ import annotations

import os
import re
import threading
import time
from datetime import date
from html import unescape
from urllib.parse import unquote

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import httpx
import pytest
from fastapi.testclient import TestClient

from qmt import auth, config, db
from qmt.models import Base, User
from qmt.web.app import app

PORT = 8121    # test_copy's 8111, test_raspored_ui's / test_upitnik_ui's 8112, test_nav's 8113, test_programs' 8114,
               # test_player's 8115, test_karton's 8116, test_kao's 8117, test_gym's 8118, test_spol's 8119,
               # test_dvoranski's 8120

LIST = "/dvoranski/predlosci"
LEAD = ("Od predloška član kreće kad otvori prazan trening: stanice i kružni setovi redom, bez vježbi. "
        "Vježbe i brojke upisuje sam.")
FREE = "Član blokove vidi ovim redom; svaki može preskočiti, ukloniti ili dodati svoj."
EMPTY = "prazan — članovi ga ne vide"
CONFIRM = ('data-confirm-title="Obrisati predložak?" data-confirm="Treninzi koji su već krenuli od njega ostaju '
           'kakvi jesu." data-confirm-cta="Obriši"')


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # nothing here stores media, but the server thread shares this process's
    # config: never a developer's real R2 bucket (as tests/test_gym.py)
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "")
    yield


def make_user(email: str, is_trainer: bool = False, plans: tuple[str, ...] = ("grupni",)) -> int:
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    db.update_profile(u.id, email.split("@")[0].capitalize(), "Test", date(1990, 1, 1), "")
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


def location(r) -> str:
    """A redirect's location as a person reads it ("+" a space)."""
    return unquote(r.headers["location"]).replace("+", " ")


def staff() -> tuple[TestClient, TestClient]:
    """The trainer (coach, no plan) and the owner (trener@test.local, no
    trainer flag: staff by rule), logged in, and the two templates."""
    make_user("coach@test.local", is_trainer=True, plans=())
    make_user("trener@test.local", plans=())
    db.reset_gym_templates()
    return client_for("coach@test.local"), client_for("trener@test.local")


def main_of(page: str) -> str:
    return page.split("<main", 1)[1].split("</main>", 1)[0]


def rows_of(page: str) -> list[tuple[int, str, str]]:
    """The list's rows in order: (the template's id, its name, its facts)."""
    return [(int(i), unescape(name), unescape(facts)) for i, name, facts in re.findall(
        r'<div class="card it-row" id="predlozak-(\d+)">\s*<a class="it-name" href="/dvoranski/predlosci/\1">'
        r'([^<]*)</a>\s*<span class="it-note">([^<]*)</span>', page)]


def row_of(page: str, tid: int) -> str:
    """A template's row on the list, to the next row or the add card."""
    return re.split(r'<div class="card it-row"|<form method="post" action="/dvoranski/predlosci" class|'
                    r'<div class="tp-cap"', page.split(f'id="predlozak-{tid}"')[1])[0]


def blocks_on(page: str) -> list[tuple[int, str]]:
    """The editor's block rows in order: (the block's id, its label)."""
    return [(int(i), label) for i, label in re.findall(
        r'<div class="card it-row" id="blok-(\d+)">\s*<span class="tp-kind">([^<]*)</span>', page)]


def block_row(page: str, bid: int) -> str:
    """A block's row on the editor, to the next row or the adds."""
    return re.split(r'<div class="card it-row"|<div class="tp-adds">|<p class="hint tp-cap">',
                    page.split(f'id="blok-{bid}"')[1])[0]


def stored(tid: int) -> list[tuple[str, int | None, int | None, int | None]]:
    """A template's blocks as stored, in order: (kind, rows, Krug, pause)."""
    return [(b.kind, b.slots, b.rounds, b.rest_seconds) for b in db.gym_template(tid).blocks]


def chooser(page: str) -> list[tuple[str, str]]:
    """A training page's template chooser: (each template's name, its facts), in order."""
    return [(unescape(n), unescape(f)) for n, f in re.findall(
        r'<span class="gt-tpl-name">([^<]*)</span>(?:<span class="gt-tpl-facts">([^<]*)</span>)?', page)]


def word(text: str, ok: bool = True) -> str:
    """A route's word as a page prints it, inside its row or its card."""
    return (f'<div class="alert ok tp-alert" role="status">{text}</div>' if ok
            else f'<div class="alert tp-alert" role="alert"><span>{text}</span></div>')


def top_has_no_word(page: str) -> bool:
    """The page's top (before its h1) prints no alert."""
    return 'class="alert' not in main_of(page).split("<h1>")[0]


# ---------- who reaches the two pages ----------

def test_the_list_and_the_editor_are_staffs_under_the_tab():
    """The trainer and the owner (staff by rule, no trainer flag of his):
    the list (its h1 and lead; a row per template in its order, its name in
    700 a link to its editor, its facts muted, the chooser's words; Uredi;
    ↑ / ↓, the first's ↑ and the last's ↓ disabled; ✕ asking; "+ Novi
    predložak" with Naziv, 80 characters at most) and a template's editor (a
    crumb back to the list, the name the h1, Naziv and Spremi, "Blokovi": a
    Stanica numbered, nothing to set; a Kružni set with Vježbi, Krugova and
    "Pauza nakon kruga (s)" and Spremi; each row ↑ / ↓ / ✕ with no confirm;
    "+ Stanica", "+ Kružni set", the muted line, "Obriši predložak" asking).
    Both pages light the tab Dvoranski treninzi, Admin ▾ not. A template
    that is none: 404."""
    coach, owner = staff()
    stanicni, kruzni = db.gym_templates(all=True)
    for c in (coach, owner):
        r = c.get(LIST)
        page = r.text
        assert r.status_code == 200 and "<title>Predlošci treninga — QMT</title>" in page
        assert f"<h1>Predlošci treninga</h1>\n<p class=\"hint\">{LEAD}</p>" in page
        assert rows_of(page) == [(stanicni.id, "Stanični trening", "6 stanica"),
                                 (kruzni.id, "Kružni trening", "1 stanica · kružni set · 4 kruga")]
        first, last = row_of(page, stanicni.id), row_of(page, kruzni.id)
        assert f'<a class="btn btn-quiet btn-sm" href="/dvoranski/predlosci/{stanicni.id}">Uredi</a>' in first
        assert 'disabled style="opacity:.35;"\n                    aria-label="Pomakni gore: Stanični trening">↑</button>' in first
        assert 'aria-label="Pomakni dolje: Stanični trening">↓</button>' in first and first.count("disabled") == 1
        assert 'disabled style="opacity:.35;"\n                    aria-label="Pomakni dolje: Kružni trening">↓</button>' in last
        assert last.count("disabled") == 1
        for tid, text in ((stanicni.id, first), (kruzni.id, last)):
            assert (f'<form method="post" action="/dvoranski/predlosci/{tid}/obrisi" style="margin:0; display:inline;"'
                    in text and " ".join(CONFIRM.split()) in " ".join(text.split()))
        assert ('<form method="post" action="/dvoranski/predlosci" class="card tp-new" id="novi">' in page
                and '<input id="tp-title" type="text" name="title" maxlength="80" required>' in page
                and '<button type="submit" class="btn btn-sm">+ Novi predložak</button>' in page)
        assert '<a href="/dvoranski" class="on">Dvoranski treninzi</a>' in page
        menu = page.split('id="adminMenu"')[1].split("</div>")[0]                   # Admin ▾: no item current
        assert 'class="navbtn menu-btn on"' not in page and 'aria-current="page"' not in menu
        assert top_has_no_word(page)

        r = c.get(f"{LIST}/{kruzni.id}")
        page = r.text
        assert r.status_code == 200 and "<title>Predložak: Kružni trening — QMT</title>" in page
        assert ('<nav class="crumbs" aria-label="Putanja"><a href="/dvoranski/predlosci">Predlošci treninga</a>'
                '<span class="sep">/</span><span class="here">Kružni trening</span></nav>\n<h1>Kružni trening</h1>') in page
        assert (f'<form method="post" action="/dvoranski/predlosci/{kruzni.id}/naziv" class="card tp-card" id="naziv">'
                in page and 'value="Kružni trening" maxlength="80" required>' in page)
        assert '<h2 id="tp-blocks-h">Blokovi</h2>' in page
        (s_id, s_label), (k_id, k_label) = blocks_on(page)
        assert (s_label, k_label) == ("Stanica 1", "Kružni set")
        station, circuit = block_row(page, s_id), block_row(page, k_id)
        assert 'class="tp-nums"' not in station and "<input" not in station        # nothing to set
        for bid, text in ((s_id, station), (k_id, circuit)):
            assert f'form="tb-x-{bid}" class="btn-ghost btn-sm"' in text
            assert f'<form id="tb-x-{bid}" method="post" action="/dvoranski/predlosci/{kruzni.id}/blok/{bid}/obrisi"></form>' in page
        assert re.findall(r'<label for="tb-\d+-(\w+)">([^<]*)</label>', circuit) == [
            ("slots", "Vježbi"), ("rounds", "Krugova"), ("rest", "Pauza nakon kruga (s)")]
        assert f'name="slots" inputmode="numeric" min="1" max="12"\n                   value="4" required>' in circuit
        assert f'name="rounds" inputmode="numeric" min="1" max="20"\n                   value="4" required>' in circuit
        assert f'name="rest" inputmode="numeric" min="0" max="3600"\n                   value="">' in circuit
        assert re.findall(r'name="vrsta" value="(\w+)">\s*<button type="submit" class="act">([^<]*)</button>', page) == [
            ("stanica", "+ Stanica"), ("kruzni", "+ Kružni set")]
        assert f'<p class="hint tp-free">{FREE}</p>' in page
        drop = page.split(f'action="/dvoranski/predlosci/{kruzni.id}/obrisi" class="ex-delete tp-drop"')[1].split("</form>")[0]
        assert " ".join(CONFIRM.split()) in " ".join(drop.split()) and '<button class="btn-ghost">Obriši predložak</button>' in drop
        assert '<a href="/dvoranski" class="on">Dvoranski treninzi</a>' in page and 'class="navbtn menu-btn on"' not in page
        assert c.get(f"{LIST}/999999").status_code == 404


def test_a_member_a_guest_and_staff_acting_as_a_member_are_refused():
    """A member: both pages and every write 403, nothing changed. A guest:
    each to the login. Staff acting as a member: refused as every staff page
    (the page and every write 403 with the page's marker; a write without
    it the acting guard's, nothing run); back to their own, the pages
    again."""
    coach, _ = staff()
    ivan = make_user("ivan@test.local")
    tid = db.gym_templates(all=True)[1].id
    bid = db.gym_template(tid).blocks[1].id
    before = [(t.title, t.position, stored(t.id)) for t in db.gym_templates(all=True)]
    writes = [(LIST, {"title": "Moj"}), (f"{LIST}/{tid}/naziv", {"title": "Novi"}),
              (f"{LIST}/{tid}/pomak", {"smjer": "gore"}), (f"{LIST}/{tid}/blok", {"vrsta": "stanica"}),
              (f"{LIST}/{tid}/blok/{bid}", {"slots": "6", "rounds": "5", "rest": "60"}),
              (f"{LIST}/{tid}/blok/{bid}/pomak", {"smjer": "gore"}), (f"{LIST}/{tid}/blok/{bid}/obrisi", {}),
              (f"{LIST}/{tid}/obrisi", {})]
    ci = client_for("ivan@test.local")
    assert ci.get(LIST).status_code == 403 and ci.get(f"{LIST}/{tid}").status_code == 403
    for path, data in writes:
        assert ci.post(path, data=data, follow_redirects=False).status_code == 403, path
    anon = TestClient(app)
    for path in (LIST, f"{LIST}/{tid}"):
        r = anon.get(path, follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (303, "/login"), path
    for path, data in writes:
        r = anon.post(path, data=data, follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (303, "/login"), path
    assert coach.post(f"/kao/{ivan}", follow_redirects=False).status_code == 303
    assert coach.get(LIST).status_code == 403 and coach.get(f"{LIST}/{tid}").status_code == 403
    for path, data in writes:
        assert coach.post(f"{path}?kao={ivan}", data=data, follow_redirects=False).status_code == 403, path
        r = coach.post(path, data=data, follow_redirects=False)                # no marker: the guard's, nothing run
        assert location(r).startswith("/karton?error=Stranica je bila otvorena prije ulaska"), path
    assert [(t.title, t.position, stored(t.id)) for t in db.gym_templates(all=True)] == before
    coach.post("/kao/izlaz", headers={"X-QMT-Kao": str(ivan)})
    assert coach.get(LIST).status_code == 200 and coach.get(f"{LIST}/{tid}").status_code == 200


def test_the_way_in_is_on_staffs_own_tab_and_on_no_members():
    """Staff's own /dvoranski carries "Predlošci treninga →" (one .act)
    right under the lead; a member's never, nor the page staff see while
    acting as a member (his)."""
    coach, owner = staff()
    ivan = make_user("ivan@test.local")
    link = '<p class="dv-tpl"><a class="act" href="/dvoranski/predlosci">Predlošci treninga →</a></p>'
    for c in (coach, owner):
        page = c.get("/dvoranski").text
        head = main_of(page).split('<div class="dv">')[0]
        assert link in head and head.index('data-copy="gym.tab.lead"') < head.index(link)
        assert main_of(page).count('href="/dvoranski/predlosci"') == 1
    assert "/dvoranski/predlosci" not in client_for("ivan@test.local").get("/dvoranski").text
    coach.post(f"/kao/{ivan}")
    acting = coach.get("/dvoranski").text
    assert f'data-kao="{ivan}"' in acting and "/dvoranski/predlosci" not in acting


# ---------- the list's writes ----------

def test_a_template_is_made_renamed_moved_and_deleted():
    """"+ Novi predložak": a template of that name after the last, no
    block, then its editor; the list says "prazan — članovi ga ne vide". A
    name is needed and 80 characters at most ("Upiši naziv predloška.",
    "Najviše 80 znakova.": the sentence in the add card, not at the top,
    nothing made), stored on one line. Renamed on its editor (the word in
    its card, "Spremljeno.", or the same refusals there). Moved one place
    with ↑ / ↓ (the word in its row); at either end, or with a direction
    that is none, nothing moves and no word. Deleted (the list's top says
    so, the places closing up): a training made from it keeps its
    blocks."""
    coach, _ = staff()
    stanicni, kruzni = db.gym_templates(all=True)
    r = coach.post(LIST, data={"title": "  Snaga   i \n kružni "}, follow_redirects=False)
    [new] = [t for t in db.gym_templates(all=True) if t.id not in (stanicni.id, kruzni.id)]
    assert location(r) == f"{LIST}/{new.id}" and (new.title, new.position, new.blocks) == ("Snaga i kružni", 3, [])
    page = coach.get(location(r)).text
    assert "<h1>Snaga i kružni</h1>" in page and '<p class="hint">Prazan — članovi ga ne vide.</p>' in page
    assert rows_of(coach.get(LIST).text)[-1] == (new.id, "Snaga i kružni", EMPTY)
    for title, refusal in (("", "Upiši naziv predloška."), ("   ", "Upiši naziv predloška."),
                           ("x" * 81, "Najviše 80 znakova.")):
        r = coach.post(LIST, data={"title": title}, follow_redirects=False)
        assert location(r) == f"{LIST}?novi=1&error={refusal}#novi", title
        page = coach.get(r.headers["location"]).text
        card = page.split('class="card tp-new" id="novi">')[1].split("</form>")[0]
        assert word(refusal, ok=False) in card and top_has_no_word(page), title
    assert len(db.gym_templates(all=True)) == 3
    assert location(coach.post(LIST, data={"title": "y" * 80}, follow_redirects=False)).startswith(f"{LIST}/")
    long_one = db.gym_templates(all=True)[-1]
    assert (long_one.title, long_one.position) == ("y" * 80, 4)
    db.delete_gym_template(long_one.id)

    r = coach.post(f"{LIST}/{new.id}/naziv", data={"title": "Snaga 2"}, follow_redirects=False)
    assert location(r) == f"{LIST}/{new.id}?naziv=1&ok=Spremljeno.#naziv" and db.gym_template(new.id).title == "Snaga 2"
    page = coach.get(r.headers["location"]).text
    assert word("Spremljeno.") in page.split('id="naziv">')[1].split("</form>")[0] and top_has_no_word(page)
    for title, refusal in (("", "Upiši naziv predloška."), ("z" * 81, "Najviše 80 znakova.")):
        r = coach.post(f"{LIST}/{new.id}/naziv", data={"title": title}, follow_redirects=False)
        assert location(r) == f"{LIST}/{new.id}?naziv=1&error={refusal}#naziv", title
        page = coach.get(r.headers["location"]).text
        assert word(refusal, ok=False) in page.split('id="naziv">')[1].split("</form>")[0] and top_has_no_word(page)
    assert db.gym_template(new.id).title == "Snaga 2"
    assert coach.post(f"{LIST}/999999/naziv", data={"title": "X"}).status_code == 404

    def order() -> list[int]:
        return [t.id for t in db.gym_templates(all=True)]

    r = coach.post(f"{LIST}/{new.id}/pomak", data={"smjer": "gore"}, follow_redirects=False)
    assert location(r) == f"{LIST}?predlozak={new.id}&ok=Spremljeno.#predlozak-{new.id}"
    assert order() == [stanicni.id, new.id, kruzni.id]
    page = coach.get(r.headers["location"]).text
    assert word("Spremljeno.") in row_of(page, new.id) and top_has_no_word(page)
    assert [i for i, *_ in rows_of(page)] == order()
    r = coach.post(f"{LIST}/{stanicni.id}/pomak", data={"smjer": "dolje"}, follow_redirects=False)
    assert order() == [new.id, stanicni.id, kruzni.id]
    for tid, smjer in ((new.id, "gore"), (kruzni.id, "dolje"), (stanicni.id, "x"), (999999, "gore")):
        r = coach.post(f"{LIST}/{tid}/pomak", data={"smjer": smjer}, follow_redirects=False)
        assert location(r) == f"{LIST}?predlozak={tid}#predlozak-{tid}", (tid, smjer)   # no word
    assert order() == [new.id, stanicni.id, kruzni.id]
    assert [t.position for t in db.gym_templates(all=True)] == [1, 2, 3]

    ivan = make_user("ivan@test.local")
    training = db.add_gym_outside(ivan, config.today())
    db.apply_gym_template(training, ivan, kruzni.id)
    r = coach.post(f"{LIST}/{kruzni.id}/obrisi", follow_redirects=False)
    assert location(r) == f"{LIST}?ok=Predložak je obrisan."
    page = coach.get(r.headers["location"]).text
    assert '<div class="alert ok" role="status">Predložak je obrisan.</div>' in main_of(page).split("<h1>")[0]
    assert order() == [new.id, stanicni.id] and db.gym_template(kruzni.id) is None
    r = coach.post(f"{LIST}/{new.id}/obrisi", follow_redirects=False)       # the first: the others close up
    assert [(t.id, t.position) for t in db.gym_templates(all=True)] == [(stanicni.id, 1)]
    assert location(coach.post(f"{LIST}/{new.id}/obrisi", follow_redirects=False)) == LIST   # gone already: no word
    t = db.gym_training(training, ivan)                                     # the training keeps its own blocks
    assert [(b.kind, b.rounds, len(b.items)) for b in t.blocks] == [("stanica", None, 1), ("kruzni", 4, 4)]


def test_twelve_templates_at_most():
    """At twelve the add is not offered, its sentence in its place
    ("Najviše 12 predložaka."), and a thirteenth is refused with it, nothing
    made; one deleted, the add is back."""
    coach, _ = staff()
    for k in range(10):
        db.add_gym_template(f"Predložak {k}")
    assert len(db.gym_templates(all=True)) == 12
    page = coach.get(LIST).text
    assert 'class="card tp-new"' not in page and 'action="/dvoranski/predlosci" class' not in page
    cap = page.split('<div class="tp-cap" id="novi">')[1].split("</div>")[0]
    assert cap.strip() == '<p class="hint">Najviše 12 predložaka.</p>'
    r = coach.post(LIST, data={"title": "Trinaesti"}, follow_redirects=False)
    assert location(r) == f"{LIST}?novi=1&error=Najviše 12 predložaka.#novi"
    assert word("Najviše 12 predložaka.", ok=False) in coach.get(r.headers["location"]).text.split('id="novi"')[1]
    with pytest.raises(ValueError, match=r"^Najviše 12 predložaka\.$"):
        db.add_gym_template("Trinaesti")
    assert len(db.gym_templates(all=True)) == 12
    db.delete_gym_template(db.gym_templates(all=True)[-1].id)
    assert 'class="card tp-new" id="novi"' in coach.get(LIST).text


# ---------- the editor's writes ----------

def test_a_templates_blocks_are_added_set_moved_and_removed():
    """"+ Stanica" and "+ Kružni set" after the last (a Kružni set of 4 rows
    and 4 Krug, no pause), back at the new row, "Spremljeno." there. A
    Kružni set's numbers saved (Vježbi 1–12, Krugova 1–20, the pause 0–3600
    or empty for none) or refused ("Neispravan broj.", in its row, nothing
    changed); a Stanica has none (404), nor another template's block. A
    block moved one place (its word in its row; nothing at either end) and
    removed in one tap (the word in the blocks' section, the places closing
    up; gone already, no word). A kind that is none adds nothing (404)."""
    coach, _ = staff()
    tid = db.add_gym_template("Moj")
    other = db.gym_templates(all=True)[0]
    base = f"{LIST}/{tid}"
    r = coach.post(f"{base}/blok", data={"vrsta": "stanica"}, follow_redirects=False)
    [s_id] = [b.id for b in db.gym_template(tid).blocks]
    assert location(r) == f"{base}?blok={s_id}&ok=Spremljeno.#blok-{s_id}"
    page = coach.get(r.headers["location"]).text
    assert word("Spremljeno.") in block_row(page, s_id) and top_has_no_word(page)
    r = coach.post(f"{base}/blok", data={"vrsta": "kruzni"}, follow_redirects=False)
    k_id = db.gym_template(tid).blocks[1].id
    assert location(r) == f"{base}?blok={k_id}&ok=Spremljeno.#blok-{k_id}"
    assert stored(tid) == [("stanica", None, None, None), ("kruzni", 4, 4, None)]
    assert coach.post(f"{base}/blok", data={"vrsta": "x"}).status_code == 404 and len(stored(tid)) == 2
    assert coach.post(f"{LIST}/999999/blok", data={"vrsta": "stanica"}).status_code == 404

    def save(bid: int, slots: str, rounds: str, rest: str, at: int | None = None):
        return coach.post(f"{LIST}/{at or tid}/blok/{bid}", data={"slots": slots, "rounds": rounds, "rest": rest},
                          follow_redirects=False)

    r = save(k_id, "6", "5", "90")
    assert location(r) == f"{base}?blok={k_id}&ok=Spremljeno.#blok-{k_id}" and stored(tid)[1] == ("kruzni", 6, 5, 90)
    page = coach.get(r.headers["location"]).text
    row = block_row(page, k_id)
    assert word("Spremljeno.") in row and 'value="6" required>' in row and 'value="90">' in row
    save(k_id, "12", "20", "")                                              # the pause empty: none
    assert stored(tid)[1] == ("kruzni", 12, 20, None)
    save(k_id, "1", "1", "0")
    assert stored(tid)[1] == ("kruzni", 1, 1, 0)
    for slots, rounds, rest in (("0", "4", ""), ("13", "4", ""), ("", "4", ""), ("4", "0", ""), ("4", "21", ""),
                                ("4", "", ""), ("4", "4", "3601"), ("4", "4", "-1"), ("x", "4", ""), ("4", "4", "1,5")):
        r = save(k_id, slots, rounds, rest)
        assert location(r) == f"{base}?blok={k_id}&error=Neispravan broj.#blok-{k_id}", (slots, rounds, rest)
    page = coach.get(r.headers["location"]).text
    assert word("Neispravan broj.", ok=False) in block_row(page, k_id) and top_has_no_word(page)
    assert stored(tid)[1] == ("kruzni", 1, 1, 0)                             # nothing changed
    assert save(s_id, "4", "4", "").status_code == 404                       # a Stanica has nothing to set
    assert save(other.blocks[0].id, "4", "4", "").status_code == 404         # another template's block
    assert save(k_id, "4", "4", "", at=other.id).status_code == 404
    assert stored(tid)[1] == ("kruzni", 1, 1, 0)

    r = coach.post(f"{base}/blok/{k_id}/pomak", data={"smjer": "gore"}, follow_redirects=False)
    assert location(r) == f"{base}?blok={k_id}&ok=Spremljeno.#blok-{k_id}"
    assert [b.id for b in db.gym_template(tid).blocks] == [k_id, s_id]
    page = coach.get(r.headers["location"]).text
    assert blocks_on(page) == [(k_id, "Kružni set"), (s_id, "Stanica 1")] and word("Spremljeno.") in block_row(page, k_id)
    for bid, smjer in ((k_id, "gore"), (s_id, "dolje"), (k_id, "x"), (other.blocks[0].id, "dolje")):
        r = coach.post(f"{base}/blok/{bid}/pomak", data={"smjer": smjer}, follow_redirects=False)
        assert location(r) == f"{base}?blok={bid}#blok-{bid}", (bid, smjer)          # nothing moves, no word
    assert [b.id for b in db.gym_template(tid).blocks] == [k_id, s_id]
    assert [b.position for b in db.gym_template(other.id).blocks] == [1, 2, 3, 4, 5, 6]

    s2 = db.add_gym_template_block(tid, "stanica")
    page = coach.get(base).text
    assert blocks_on(page) == [(k_id, "Kružni set"), (s_id, "Stanica 1"), (s2, "Stanica 2")]
    r = coach.post(f"{base}/blok/{s_id}/obrisi", follow_redirects=False)
    assert location(r) == f"{base}?blokovi=1&ok=Stanica je uklonjena.#blokovi"
    assert [(b.id, b.position) for b in db.gym_template(tid).blocks] == [(k_id, 1), (s2, 2)]   # closed up
    page = coach.get(r.headers["location"]).text
    section = page.split('<h2 id="tp-blocks-h">Blokovi</h2>')[1].split('<div class="tp-rows">')[0]
    assert word("Stanica je uklonjena.") in section and top_has_no_word(page)
    assert blocks_on(page) == [(k_id, "Kružni set"), (s2, "Stanica 1")]
    assert location(coach.post(f"{base}/blok/{s_id}/obrisi", follow_redirects=False)) == f"{base}#blokovi"   # gone
    r = coach.post(f"{base}/blok/{k_id}/obrisi", follow_redirects=False)
    assert location(r) == f"{base}?blokovi=1&ok=Kružni set je uklonjen.#blokovi"
    assert stored(tid) == [("stanica", None, None, None)] and db.gym_template(tid).blocks[0].position == 1
    assert location(coach.post(f"{base}/blok/{other.blocks[0].id}/obrisi", follow_redirects=False)) == f"{base}#blokovi"
    assert len(db.gym_template(other.id).blocks) == 6                       # another template's: untouched


def test_forty_blocks_at_most():
    """A template holds 40 blocks at most, a training's own cap and its
    sentence ("Najviše 40 stanica i kružnih setova."): at 40 the two adds
    are not offered, the sentence in their place, and one more is refused
    with it in the blocks' section, nothing added."""
    coach, _ = staff()
    tid = db.add_gym_template("Puno")
    for k in range(40):
        db.add_gym_template_block(tid, "kruzni" if k % 5 == 0 else "stanica")
    page = coach.get(f"{LIST}/{tid}").text
    assert len(blocks_on(page)) == 40 and 'class="tp-adds"' not in page
    assert '<p class="hint tp-cap">Najviše 40 stanica i kružnih setova.</p>' in page
    r = coach.post(f"{LIST}/{tid}/blok", data={"vrsta": "stanica"}, follow_redirects=False)
    assert location(r) == f"{LIST}/{tid}?blokovi=1&error=Najviše 40 stanica i kružnih setova.#blokovi"
    section = coach.get(r.headers["location"]).text.split('<h2 id="tp-blocks-h">Blokovi</h2>')[1].split('<div class="tp-rows">')[0]
    assert word("Najviše 40 stanica i kružnih setova.", ok=False) in section
    with pytest.raises(ValueError, match=r"^Najviše 40 stanica i kružnih setova\.$"):
        db.add_gym_template_block(tid, "kruzni")
    assert len(stored(tid)) == 40


# ---------- the races ----------

def _race(n: int, work) -> list[str]:
    """`work(k)` in n threads at the same moment: the errors."""
    errors, gate = [], threading.Barrier(n)

    def run(k):
        try:
            gate.wait()
            work(k)
        except Exception as e:                                              # reported by the caller
            errors.append(repr(e))

    threads = [threading.Thread(target=run, args=(k,)) for k in range(n)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    return errors


def test_two_new_templates_at_once_at_eleven_make_twelve():
    """Two "+ Novi predložak" at the same moment with eleven templates there
    (each add takes the gym_templates table's lock, then counts), five
    times: twelve, the other refused ("Najviše 12 predložaka."), every
    template its own place."""
    staff()
    for k in range(9):
        db.add_gym_template(f"Predložak {k}")
    for times in range(5):
        assert len(db.gym_templates(all=True)) == 11
        errors = _race(2, lambda k, times=times: db.add_gym_template(f"Utrka {times}-{k}"))
        tpls = db.gym_templates(all=True)
        assert len(tpls) == 12 and len(errors) == 1 and "Najviše 12 predložaka." in errors[0], errors
        assert len({t.position for t in tpls}) == 12
        db.delete_gym_template(tpls[-1].id)
    assert [t.position for t in db.gym_templates(all=True)] == list(range(1, 12))


def test_two_new_blocks_at_once_on_one_template_take_two_places():
    """Eight "+ Stanica" / "+ Kružni set" on one template at the same moment
    (the table's lock), three times: eight blocks more each time, every one
    its own place; at 38, four at once add two, the others refused at the
    cap."""
    staff()
    tid = db.add_gym_template("Utrka")
    for times in (1, 2, 3):
        assert not _race(8, lambda k: db.add_gym_template_block(tid, "kruzni" if k % 2 else "stanica"))
        positions = [b.position for b in db.gym_template(tid).blocks]
        assert len(positions) == 8 * times and sorted(positions) == list(range(1, 8 * times + 1))
    for _ in range(14):
        db.add_gym_template_block(tid, "stanica")
    errors = _race(4, lambda k: db.add_gym_template_block(tid, "stanica"))
    assert len(db.gym_template(tid).blocks) == 40 and len(errors) == 2
    assert all("Najviše 40 stanica i kružnih setova." in e for e in errors)


# ---------- the member's chooser follows ----------

def test_the_members_chooser_follows_the_templates():
    """A member's chooser (an empty training's page) offers the templates
    that hold a block, in their order: a new one with no block is not
    there, once it holds blocks it is, last, with its facts; renamed, by its
    new name; moved, in its new place; one emptied again, gone. A training
    made from a three-block template has those three blocks, as set (a
    Kružni set's rows, Krug and pause), and keeps them whatever happens to
    the template after. A template with no block is refused if posted (a
    page drawn before its blocks went): "Odaberi predložak s popisa.",
    nothing changed."""
    coach, _ = staff()
    stanicni, kruzni = db.gym_templates(all=True)
    ivan = make_user("ivan@test.local")
    tid = db.add_gym_outside(ivan, config.today())
    ci = client_for("ivan@test.local")
    page_url = f"/dvoranski/trening/{tid}"
    start = [("Stanični trening", "6 stanica"), ("Kružni trening", "1 stanica · kružni set · 4 kruga")]
    assert chooser(ci.get(page_url).text) == start
    coach.post(LIST, data={"title": "Snaga"})
    snaga = db.gym_templates(all=True)[-1].id
    assert chooser(ci.get(page_url).text) == start                           # no block: offered to nobody
    assert [t.id for t in db.gym_templates()] == [stanicni.id, kruzni.id]
    for vrsta in ("stanica", "kruzni", "stanica"):
        coach.post(f"{LIST}/{snaga}/blok", data={"vrsta": vrsta})
    k_id = db.gym_template(snaga).blocks[1].id
    coach.post(f"{LIST}/{snaga}/blok/{k_id}", data={"slots": "3", "rounds": "5", "rest": "60"})
    assert chooser(ci.get(page_url).text) == start + [("Snaga", "1 stanica · kružni set · 5 krugova · 1 stanica")]
    coach.post(f"{LIST}/{snaga}/naziv", data={"title": "Snaga i krug"})
    coach.post(f"{LIST}/{snaga}/pomak", data={"smjer": "gore"})
    coach.post(f"{LIST}/{snaga}/pomak", data={"smjer": "gore"})
    assert [n for n, _ in chooser(ci.get(page_url).text)] == ["Snaga i krug", "Stanični trening", "Kružni trening"]

    r = ci.post(f"{page_url}/predlozak", data={"predlozak": str(snaga)}, follow_redirects=False)
    assert r.status_code == 303
    t = db.gym_training(tid, ivan)
    assert [(b.kind, b.rounds, b.rest_seconds, len(b.items)) for b in t.blocks] == [
        ("stanica", None, None, 1), ("kruzni", 5, 60, 3), ("stanica", None, None, 1)]
    assert all(it.exercise_id is None and it.done == "[]" for b in t.blocks for it in b.items)   # its stations empty
    coach.post(f"{LIST}/{snaga}/blok/{k_id}/obrisi")                         # the template changes: the training not
    coach.post(f"{LIST}/{snaga}/naziv", data={"title": "Drugo"})
    assert [(b.kind, b.rounds, len(b.items)) for b in db.gym_training(tid, ivan).blocks] == [
        ("stanica", None, 1), ("kruzni", 5, 3), ("stanica", None, 1)]

    for b in db.gym_template(snaga).blocks:                                 # emptied: gone from the chooser
        coach.post(f"{LIST}/{snaga}/blok/{b.id}/obrisi")
    other = db.add_gym_outside(ivan, config.today())
    assert [n for n, _ in chooser(ci.get(f"/dvoranski/trening/{other}").text)] == ["Stanični trening", "Kružni trening"]
    r = ci.post(f"/dvoranski/trening/{other}/predlozak", data={"predlozak": str(snaga)}, follow_redirects=False)
    assert location(r) == f"/dvoranski/trening/{other}?predlozak=1&error=Odaberi predložak s popisa.#predlozak"
    assert db.gym_training(other, ivan).blocks == []
    with pytest.raises(ValueError, match=r"^Odaberi predložak s popisa\.$"):
        db.apply_gym_template(other, ivan, snaga)


# ---------- in a browser, on a phone ----------

@pytest.fixture(scope="module")
def server():
    import uvicorn
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/healthz", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{PORT}"
    srv.should_exit = True
    th.join(timeout=5)


OVERFLOW = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"


def test_a_template_made_by_staff_and_taken_by_a_member_on_a_phone(server):
    """At 390px with touch, as the trainer: the tab's "Predlošci treninga →"
    to the list, a template made ("+ Novi predložak") → its editor, "+
    Stanica" and "+ Kružni set" added, the set's Krugova changed and saved
    ("Spremljeno." in its row), the two swapped with the set's ↑; then as a
    member, his empty training's chooser offers it, and a training made from
    it shows the blocks in that order (its overview: the Kružni set, then
    the Stanica). No page scrolls sideways at 390 or 360px, the list and the
    editor alike. No page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("coach@test.local", is_trainer=True, plans=())
    ivan = make_user("ivan@test.local")
    db.reset_gym_templates()
    tid = db.add_gym_outside(ivan, config.today())
    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        errors: list[str] = []

        def phone(email: str):
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(f"page error: {e}"))
            pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
            pg.goto(server + "/login")
            pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); localStorage.setItem('qmt-phone', String(Date.now())); }")
            pg.fill("main input[name=email]", email)
            pg.fill("main input[name=password]", "lozinka123")
            pg.click("main button[type=submit]")
            pg.wait_for_load_state("networkidle")
            if pg.locator("#fbPrompt[open], dialog[open]").count():           # the login's prompt: later
                pg.keyboard.press("Escape")
            return ctx, pg

        def wide(pg, where: str) -> None:
            for w, h in ((390, 844), (360, 780)):
                pg.set_viewport_size({"width": w, "height": h})
                check(pg.evaluate(OVERFLOW) == 0, f"{where} at {w}px overflows by {pg.evaluate(OVERFLOW)}px")
            pg.set_viewport_size({"width": 390, "height": 844})

        def go(pg, tap: str) -> None:
            with pg.expect_navigation():
                pg.locator(tap).first.tap()
            pg.wait_for_load_state("networkidle")

        ctx, pg = phone("coach@test.local")
        pg.goto(server + "/dvoranski")
        pg.wait_for_load_state("networkidle")
        go(pg, 'main a[href="/dvoranski/predlosci"]')
        check(pg.url == server + LIST, f"Predlošci treninga → led to {pg.url}")
        wide(pg, "the list")
        pg.locator("#tp-title").tap()
        pg.fill("#tp-title", "Moj predložak")
        go(pg, "form.tp-new button[type=submit]")
        [made] = [t for t in db.gym_templates(all=True) if t.title == "Moj predložak"] or [None]
        check(made is not None and pg.url == server + f"{LIST}/{made.id}" if made else False, f"the add led to {pg.url}")
        if made:
            go(pg, 'form:has(input[value="stanica"]) button')
            go(pg, 'form:has(input[value="kruzni"]) button')
            s_id, k_id = [b.id for b in db.gym_template(made.id).blocks]
            check(pg.url.endswith(f"#blok-{k_id}"), f"the add came back at {pg.url}")
            pg.locator(f"#tb-{k_id}-rounds").fill("5")
            go(pg, f"#blok-{k_id} form.tp-nums button[type=submit]")
            check(db.gym_template(made.id).blocks[1].rounds == 5, "Krugova was not saved")
            check(pg.locator(f"#blok-{k_id} .alert.ok").inner_text().strip() == "Spremljeno.", "no word in its row")
            go(pg, f'#blok-{k_id} button[form="tb-gore-{k_id}"]')
            labels = pg.evaluate("() => [...document.querySelectorAll('.tp-rows .tp-kind')].map(e => e.textContent)")
            check(labels == ["Kružni set", "Stanica 1"], f"after the swap the editor reads {labels}")
            check([b.id for b in db.gym_template(made.id).blocks] == [k_id, s_id], "the swap was not stored")
            wide(pg, "the editor")
        ctx.close()

        ctx, pg = phone("ivan@test.local")
        pg.goto(server + f"/dvoranski/trening/{tid}")
        pg.wait_for_load_state("networkidle")
        names = pg.evaluate("() => [...document.querySelectorAll('.gt-tpl-name')].map(e => e.textContent)")
        check(names == ["Stanični trening", "Kružni trening", "Moj predložak"], f"the chooser offers {names}")
        facts = pg.locator('.gt-tpl-row:has-text("Moj predložak") .gt-tpl-facts')
        check(facts.count() == 1 and facts.inner_text() == "kružni set · 5 krugova · 1 stanica",
              "its facts in the chooser")
        go(pg, '.gt-tpl-row:has-text("Moj predložak")')
        kinds = pg.evaluate("() => [...document.querySelectorAll('#pregled a.pl-row')].map(a => a.dataset.kind)")
        check(kinds == ["kruzni", "stanica"], f"the training's overview reads {kinds}")
        t = db.gym_training(tid, ivan)
        check([(b.kind, b.rounds) for b in t.blocks] == [("kruzni", 5), ("stanica", None)], "the training's blocks")
        wide(pg, "the training made from it")
        ctx.close()
        browser.close()
    assert not problems and not errors, problems + errors
