"""The member's sex, for the grammar (27.11.2026, build 5 of
roadmap/2026-11-26-gym-training-plan.md). The owner, of his own karton's
"Tvoji online treninzi i treninzi koje upišeš sam/a.": "on login do we know
the sex of the user and then to use the correct grammar instead of" that;
Fable proposed an optional "Spol" on the profile, with which the app
resolves the slash forms for each member wherever a text prints, the texts
Amir retypes himself too, and leaves them as they are for anyone who has
not said; the owner: "yes".

The datum (users.sex, migration 3d9a6f2c8b51, run for real on qmt_test
there and back) and the profile's field; the resolver (qmt.grammar),
table-driven over every slash form the registry and the default questions
hold today, its rules, its tables, the tokens it must never touch, and the
identity for no sex; where it applies: the copy macros, copy_text (an
attribute, a script's word), the flashes (the four sentences in code that
carry a slash form, each on its path), a JSON sentence to a script, the
upitnik's questions on /upitnik and on the karton's "Odgovori", the
password-reset email; whose sex: the member's while staff act as him, the
member's on the trainer's view of his karton. The editor keeps the stored
text: a span resolved for him carries it (data-raw), a save answers with
the text to show beside the one stored, and in a browser edit mode shows
"sam/a", leaving it "sam", no reload. A reader who has not said (every
account today, every guest) and an editor who has not get their pages as
the resolver never ran: the slash forms as stored, no mark of a sex, the
same bytes whatever the stored sex once the resolver is the identity.
"""

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

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect, text as sa_text
from sqlalchemy.exc import IntegrityError

from qmt import auth, config, copy, db, grammar, mailer, upitnik
from qmt.models import SEXES, Base, Booking, User
from qmt.web import app as web
from qmt.web.app import app

PORT = 8119    # test_copy's 8111, test_raspored_ui's / test_upitnik_ui's 8112, test_nav's 8113, test_programs' 8114,
               # test_player's 8115, test_karton's 8116, test_kao's 8117, test_gym's 8118


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # never the real data/uploads, never a real R2 bucket (a developer's .env
    # may carry live R2_* keys); the browser test's server is a thread of this process
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "")
    yield


def make_user(email: str, is_trainer: bool = False, plans: tuple[str, ...] = (), sex: str | None = None) -> int:
    """A verified account with a complete profile, `plans` recorded today
    and `sex` given ("f", "m"; None: not said, as every account starts)."""
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    db.update_profile(u.id, email.split("@")[0], "Test", date(1990, 1, 1), "", sex=sex)
    if is_trainer:
        with db.session_scope() as s:
            s.get(User, u.id).is_trainer = True
    for plan in plans:
        db.record_payment(u.id, plan)
    return u.id


def set_sex(uid: int, sex: str | None) -> None:
    with db.session_scope() as s:
        s.get(User, uid).sex = sex


def client_for(email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"email": email, "password": "lozinka123"}, follow_redirects=False)
    assert r.status_code == 303, "login failed"
    return c


def location(r) -> str:
    """A redirect's location as a person reads it ("+" a space)."""
    return unquote(r.headers["location"]).replace("+", " ")


def attended(uid: int, hours_ago: float = 3) -> int:
    """A finished termin uid was booked into (booked directly: book()
    refuses a past one); its id."""
    sid = db.add_oneoff_session("Grupni trening", datetime.now(config.TZ) - timedelta(hours=hours_ago), 60, 8, None)
    with db.session_scope() as s:
        s.add(Booking(user_id=uid, session_id=sid))
    return sid


def seed_questions() -> None:
    """The upitnik's questions as they start (copy.UPITNIK_DEFAULT_QUESTIONS)."""
    for question in copy.UPITNIK_DEFAULT_QUESTIONS:
        db.add_upitnik_question(None, question)


def answered(uid: int) -> None:
    """A version-2 upitnik of uid's, saved: q5 (trenirao/la) at 7, q10
    (motiviran/a) at 8, the rest as a client might leave them."""
    answers = {"q1": "Opće zdravlje i kretanje", "q5": 7, "q6": 6, "q10": 8, "q15": False}
    db.save_onboarding(uid, json.dumps(answers, ensure_ascii=False), 6.4, "srednja", upitnik.GOAL, version=2,
                       pain_level=None, pain_high=False, needs_review=False, consented_at=datetime.now(config.TZ))


def span(page: str, key: str) -> list[str]:
    """Every editor's span of slot `key` on a page, its whole opening tag
    and text: '<span class="ed t" data-copy="…" …>text'."""
    return re.findall(rf'<span class="ed t" data-copy="{re.escape(key)}"[^>]*>[^<]*', page)


# ---------- the datum ----------

def _migration(file: str):
    path = pathlib.Path(__file__).parents[1] / "alembic" / "versions" / file
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _run(step) -> None:
    """A revision's upgrade() or downgrade(), run for real on qmt_test."""
    with db.engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        step()


def _takes(sql: str, **params) -> bool:
    """Whether the database takes a statement (a CHECK refuses it: False)."""
    try:
        with db.engine.begin() as conn:
            conn.execute(sa_text(sql), params)
        return True
    except IntegrityError:
        return False


def _users_diffs() -> list:
    """What compare_metadata finds between qmt_test and the models about users."""
    from alembic.autogenerate import compare_metadata
    with db.engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    out = []
    for d in diffs:
        d0 = d[0] if isinstance(d, list) else d
        kind, obj = d0[0], d0[1]
        table = (d0[2] if kind.startswith("modify_") or kind in ("add_column", "remove_column")
                 else obj.name if kind in ("add_table", "remove_table")
                 else obj.parent.name if kind in ("add_fk", "remove_fk") else obj.table.name)
        if table == "users":
            out.append(d)
    return out


def test_the_migration_adds_the_sex_and_its_check_and_back():
    """3d9a6f2c8b51, run on qmt_test as before it (users without sex, two
    accounts in it): the column as the model has it (String(1), NULL), no
    account given one, its CHECK taking f, m and NULL and refusing any
    other; downgrade drops it, the accounts staying; a second upgrade makes
    it again, every account not said."""
    mig = _migration("3d9a6f2c8b51_users_sex.py")
    assert (mig.revision, mig.down_revision) == ("3d9a6f2c8b51", "36d6e2c97de7")
    assert mig.SEXES == tuple(SEXES)                                            # its own copy agrees with the model's
    ivan, ana = make_user("ivan@test.local"), make_user("ana@test.local")
    with db.engine.begin() as conn:                                             # the table as before the revision
        conn.execute(sa_text("ALTER TABLE users DROP COLUMN sex"))
    assert "sex" not in {c["name"] for c in sa_inspect(db.engine).get_columns("users")}
    _run(mig.upgrade)
    assert _users_diffs() == []
    col = {c["name"]: c for c in sa_inspect(db.engine).get_columns("users")}["sex"]
    assert col["nullable"] and str(col["type"]) == "VARCHAR(1)" and col["default"] is None
    assert [db.get_user(u).sex for u in (ivan, ana)] == [None, None]
    assert {c["name"] for c in sa_inspect(db.engine).get_check_constraints("users")} == {"ck_users_sex"}
    for value in ("f", "m", None):
        assert _takes("UPDATE users SET sex = :v WHERE id = :i", v=value, i=ivan), value
    for value in ("x", "F", "M", "ž", ""):
        assert not _takes("UPDATE users SET sex = :v WHERE id = :i", v=value, i=ivan), value
    _takes("UPDATE users SET sex = 'f' WHERE id = :i", i=ana)
    _run(mig.downgrade)
    assert "sex" not in {c["name"] for c in sa_inspect(db.engine).get_columns("users")}
    with db.engine.connect() as conn:
        assert [r[0] for r in conn.execute(sa_text("SELECT email FROM users ORDER BY id"))] == [
            "ivan@test.local", "ana@test.local"]
    _run(mig.upgrade)
    assert _users_diffs() == [] and [db.get_user(u).sex for u in (ivan, ana)] == [None, None]


def test_read_sex_takes_f_m_or_nothing_and_update_profile_keeps_it_unless_named():
    """db.read_sex: "f" and "m" (models.SEXES, spaces around them dropped),
    "" or spaces for not said (None); anything else "Neispravan spol.".
    db.update_profile(…, sex=…) checks it again, and a caller that names
    none (KEEP) leaves the stored one."""
    assert SEXES == {"f": "Žensko", "m": "Muško"} and list(SEXES) == ["f", "m"]
    for raw, sex in (("f", "f"), ("m", "m"), (" m ", "m"), ("", None), ("  ", None), (None, None)):
        assert db.read_sex(raw) == sex, raw
    for raw in ("x", "F", "M", "ž", "fm", "žensko", "Žensko", "0", "none"):
        with pytest.raises(ValueError, match="Neispravan spol."):
            db.read_sex(raw)
    uid = make_user("ivan@test.local")
    assert db.get_user(uid).sex is None                                         # nothing is filled
    db.update_profile(uid, "Ivan", "Horvat", date(1990, 1, 1), "", sex="f")
    assert db.get_user(uid).sex == "f"
    db.update_profile(uid, "Ivan", "Horvat", date(1990, 1, 1), "")              # KEEP: names none
    assert db.get_user(uid).sex == "f"
    with pytest.raises(ValueError, match="Neispravan spol."):
        db.update_profile(uid, "Ivo", "Horvat", date(1990, 1, 1), "", sex="x")
    assert (db.get_user(uid).sex, db.get_user(uid).name) == ("f", "Ivan")       # nothing changed
    db.update_profile(uid, "Ivan", "Horvat", date(1990, 1, 1), "", sex=None)
    assert db.get_user(uid).sex is None


# ---------- the resolver ----------

# Every slash form the registry and the default questions hold today (27.11.2026),
# where it is, its whole text and what a woman and a man read: (where, text, feminine,
# masculine). The profile's hint quotes one („bio/la”: no whole token of letters) and
# reads alike; the old questionnaire's option (QUESTIONS_V1) is the karton's.
FORMS = (
    ("vodic.title", "Dobrodošao/la u vodič kroz trening", "Dobrodošla u vodič kroz trening",
     "Dobrodošao u vodič kroz trening"),
    ("vodic.6.text", "Ovisno o rezultatima upitnika, bit ćeš usmjeren/a u jedan od tri programa:",
     "Ovisno o rezultatima upitnika, bit ćeš usmjerena u jedan od tri programa:",
     "Ovisno o rezultatima upitnika, bit ćeš usmjeren u jedan od tri programa:"),
    ("vodic.9.text", None, "Ako nisi sigurna gdje pripadaš", "Ako nisi siguran gdje pripadaš"),
    ("karton.diary.lead", None, "ili označi da nisi bila.", "ili označi da nisi bio."),
    ("karton.diary.absent_chip", "Nisam bio/la", "Nisam bila", "Nisam bio"),
    ("karton.diary.absent", "Nisam bio/la", "Nisam bila", "Nisam bio"),
    ("karton.confirm.absent_title", "Nisi bio/la na terminu?", "Nisi bila na terminu?", "Nisi bio na terminu?"),
    ("karton.confirm.absent_cta", "Da, nisam bio/la", "Da, nisam bila", "Da, nisam bio"),
    ("karton.staff.own_diary_lead", "Tvoji online treninzi i treninzi koje upišeš sam/a.",
     "Tvoji online treninzi i treninzi koje upišeš sama.", "Tvoji online treninzi i treninzi koje upišeš sam."),
    ("dan.state.open", "U tijeku — nastavi gdje si stao/la.", "U tijeku — nastavi gdje si stala.",
     "U tijeku — nastavi gdje si stao."),
    # the gym training's template chooser (27.11.2026, the dvoranski treninzi's build 1)
    ("gym.chooser.own", "ili složi sam/a:", "ili složi sama:", "ili složi sam:"),
    ("profil.welcome", None, "Dobrodošla! Dopuni osnovne podatke", "Dobrodošao! Dopuni osnovne podatke"),
    ("profil.form.sex_hint", "Da ti se aplikacija obraća u pravom rodu: „bio” ili „bila”, ne „bio/la”.",
     "Da ti se aplikacija obraća u pravom rodu: „bio” ili „bila”, ne „bio/la”.",
     "Da ti se aplikacija obraća u pravom rodu: „bio” ili „bila”, ne „bio/la”."),
    ("profil.account.since", "Registriran/a od", "Registrirana od", "Registriran od"),
    ("app.confirm.title", "Jesi li siguran/na?", "Jesi li sigurna?", "Jesi li siguran?"),
    ("q5.text", "Koliko redovito si trenirao/la u zadnjih 6 mjeseci (2x tjedno ili više)?",
     "Koliko redovito si trenirala u zadnjih 6 mjeseci (2x tjedno ili više)?",
     "Koliko redovito si trenirao u zadnjih 6 mjeseci (2x tjedno ili više)?"),
    ("q6.text", "Kako bi ocijenio/la svoju fizičku kondiciju?", "Kako bi ocijenila svoju fizičku kondiciju?",
     "Kako bi ocijenio svoju fizičku kondiciju?"),
    ("q10.text", "Koliko si motiviran/a za promjenu i dosljednost?", "Koliko si motivirana za promjenu i dosljednost?",
     "Koliko si motiviran za promjenu i dosljednost?"),
    ("q10.high", "jako sam motiviran/a", "jako sam motivirana", "jako sam motiviran"),
    ("v1.cucanj.options[0]", "Nikad ga nisam radio/la", "Nikad ga nisam radila", "Nikad ga nisam radio"),
)
# a token that holds a letter, a slash and an ending, as the scan below finds one
SLASH_TOKEN = re.compile(r"\S*[^\W\d_]/(?:la|na|a)\b\S*", re.I)


def registry_texts() -> dict[str, str]:
    """Every text of the registry's defaults (a list's items, a table's
    cells by their place), the default questions' and the old
    questionnaire's, by where it is."""
    out = {}
    for key, slot in copy.SLOTS.items():
        default = getattr(slot, "default", None)
        if isinstance(default, str):
            out[key] = default
        elif isinstance(default, tuple):
            for i, item in enumerate(default):
                for j, text in enumerate((item,) if isinstance(item, str) else item):
                    out[f"{key}[{i}]" if isinstance(item, str) else f"{key}[{i}][{j}]"] = text
    for q in copy.UPITNIK_DEFAULT_QUESTIONS:
        for field in ("text", "low", "high"):
            out[f"q{q['id']}.{field}"] = q[field]
        for i, option in enumerate(q["options"]):
            out[f"q{q['id']}.options[{i}]"] = option
    for q in upitnik.QUESTIONS_V1:
        out[f"v1.{q['key']}.text"] = q["text"]
        for i, (option, _) in enumerate(q["options"]):
            out[f"v1.{q['key']}.options[{i}]"] = option
    return out


def test_every_slash_form_the_registry_holds_reads_as_each_sex():
    """The forms are listed here, every one (the scan finds no other; a new
    default with one is a line more), each text read by a woman, by a man,
    and by a reader who has not said (the text itself, the very object).
    The whole guide's ninth section, the diary's lead and the welcome are
    checked at their slash form's sentence."""
    texts = registry_texts()
    found = {where for where, text in texts.items() if SLASH_TOKEN.search(text)}
    assert found == {where for where, *_ in FORMS}, found ^ {where for where, *_ in FORMS}
    for where, text, feminine, masculine in FORMS:
        whole = texts[where]
        if text is not None:
            assert whole == text, where
            assert (grammar.gendered(whole, "f"), grammar.gendered(whole, "m")) == (feminine, masculine), where
        else:                                                                   # a long text: its sentence
            assert feminine in grammar.gendered(whole, "f") and masculine in grammar.gendered(whole, "m"), where
        assert grammar.gendered(whole, None) is whole, where
    # two whole words after one another: a form too, where the second can be
    # nothing but the first's feminine (Fable's review; the guide's own)
    assert "Spreman/spremna za početak?" in texts["vodic.4.h"]
    assert (grammar.gendered(texts["vodic.4.h"], "f"), grammar.gendered(texts["vodic.4.h"], "m")) == (
        texts["vodic.4.h"].replace("Spreman/spremna", "Spremna"), texts["vodic.4.h"].replace("Spreman/spremna", "Spreman"))
    assert "kako bi bio/bila siguran/sigurna da možeš" in texts["vodic.5.text"]
    assert "kako bi bila sigurna da možeš" in grammar.gendered(texts["vodic.5.text"], "f")
    assert "kako bi bio siguran da možeš" in grammar.gendered(texts["vodic.5.text"], "m")
    assert grammar.gendered(texts["vodic.5.text"], None) is texts["vodic.5.text"]


@pytest.mark.parametrize("text, feminine, masculine", [
    # "/la" after an "o": the word, the word with "o" made "la"
    ("bio/la", "bila", "bio"), ("stao/la", "stala", "stao"), ("rezervirao/la", "rezervirala", "rezervirao"),
    ("trenirao/la", "trenirala", "trenirao"), ("ocijenio/la", "ocijenila", "ocijenio"),
    ("tražio/la", "tražila", "tražio"), ("iskoristio/la", "iskoristila", "iskoristio"),
    ("registrirao/la", "registrirala", "registrirao"), ("počeo/la", "počela", "počeo"),
    # the fleeting a: every word that ends in "šao", and the table's
    ("došao/la", "došla", "došao"), ("Dobrodošao/la", "Dobrodošla", "Dobrodošao"), ("išao/la", "išla", "išao"),
    ("našao/la", "našla", "našao"), ("prošao/la", "prošla", "prošao"), ("otišao/la", "otišla", "otišao"),
    *[(f"{m}/la", f, m) for m, f in grammar.FLEETING_LA.items()],
    # the -jeti verbs
    *[(f"{m}/la", f, m) for m, f in grammar.JETI.items()],
    # "/na" after "an"
    ("siguran/na", "sigurna", "siguran"), ("spreman/na", "spremna", "spreman"), ("dužan/na", "dužna", "dužan"),
    # "/a" after two letters or more: the word and "a"
    ("sam/a", "sama", "sam"), ("usmjeren/a", "usmjerena", "usmjeren"), ("motiviran/a", "motivirana", "motiviran"),
    ("registriran/a", "registrirana", "registriran"), ("prijavljen/a", "prijavljena", "prijavljen"),
    ("on/a", "ona", "on"),
    # the adjectives with a fleeting a
    *[(f"{m}/a", f, m) for m, f in grammar.FLEETING_A.items()],
])
def test_each_rule_and_each_table_word(text, feminine, masculine):
    assert (grammar.gendered(text, "f"), grammar.gendered(text, "m")) == (feminine, masculine)


def test_the_tables_hold_the_briefs_words():
    """The two closed groups of "/la" and the adjectives with a fleeting a
    hold every word the brief names (adding one is a line in
    qmt/grammar.py; Fable's review added the prefixed and the -nijeti
    verbs: "poželio" -> "poželjela", "donio" -> "donijela")."""
    assert set(grammar.FLEETING_LA) >= {"mogao", "pomogao", "rekao", "stigao", "postigao", "digao", "podigao",
                                        "legao", "pekao", "vukao", "povukao", "izvukao", "obukao", "tukao",
                                        "pobjegao"}
    assert grammar.JETI.items() >= {"htio": "htjela", "volio": "voljela", "želio": "željela", "vidio": "vidjela",
                                    "živio": "živjela", "smio": "smjela", "uspio": "uspjela", "razumio": "razumjela",
                                    "trpio": "trpjela", "letio": "letjela", "šutio": "šutjela"}.items()
    assert (grammar.JETI["poželio"], grammar.JETI["donio"], grammar.FLEETING_LA["stekao"]) == (
        "poželjela", "donijela", "stekla")
    assert grammar.FLEETING_A["siguran"] == "sigurna" and grammar.FLEETING_A["svjestan"] == "svjesna"
    assert grammar.FLEETING_A["bolestan"] == "bolesna" and grammar.FLEETING_A["dobar"] == "dobra"
    assert set(grammar.FLEETING_A) == {"siguran", "nesiguran", "spreman", "umoran", "odmoran", "sretan", "zadovoljan",
                                       "slobodan", "svjestan", "dužan", "potreban", "gladan", "žedan", "bolestan",
                                       "aktivan", "uporan", "ponosan", "snažan", "miran", "točan", "uspješan",
                                       "dosljedan", "dobar"}
    assert grammar.gendered("dozvolio/la", "f") == "dozvolila"          # a word is matched whole, never its ending


def test_capitals_two_forms_and_the_punctuation_after_a_form():
    """The word's own capitals stay; two forms in one text each resolve; a
    form before a full stop, a comma, a question mark, a closing bracket
    or quote keeps what follows it; a text's line breaks and spaces stay."""
    for text, feminine, masculine in (
            ("Dobrodošao/la!", "Dobrodošla!", "Dobrodošao!"), ("BIO/LA", "BILA", "BIO"), ("Htio/la", "Htjela", "Htio"),
            ("HTIO/LA", "HTJELA", "HTIO"), ("On/a je", "Ona je", "On je"), ("SIGURAN/NA", "SIGURNA", "SIGURAN"),
            ("Bio/la sam spreman/na.", "Bila sam spremna.", "Bio sam spreman."),
            ("nisi bio/la prijavljen/a.", "nisi bila prijavljena.", "nisi bio prijavljen."),
            ("Jesi li siguran/na? Nisam bio/la, sam/a sam.", "Jesi li sigurna? Nisam bila, sama sam.",
             "Jesi li siguran? Nisam bio, sam sam."),
            ("Rekao/la si: „idemo” — bio/la si tu)", "Rekla si: „idemo” — bila si tu)", "Rekao si: „idemo” — bio si tu)"),
            ("bio/la”", "bila”", "bio”"), ("sam/a…", "sama…", "sam…"),
            ("Prvi red bio/la\n\n  drugi sam/a ", "Prvi red bila\n\n  drugi sama ", "Prvi red bio\n\n  drugi sam ")):
        assert (grammar.gendered(text, "f"), grammar.gendered(text, "m")) == (feminine, masculine), text


@pytest.mark.parametrize("text, feminine, masculine", [
    ("bio/bila", "bila", "bio"), ("Bio/bila", "Bila", "Bio"), ("došao/došla", "došla", "došao"),
    ("htio/htjela", "htjela", "htio"), ("radio/radila.", "radila.", "radio."), ("mogao/mogla", "mogla", "mogao"),
    ("Spreman/spremna za početak?", "Spremna za početak?", "Spreman za početak?"),
    ("siguran/sigurna", "sigurna", "siguran"), ("SPREMAN/SPREMNA", "SPREMNA", "SPREMAN"),
    ("kako bi bio/bila siguran/sigurna, da", "kako bi bila sigurna, da", "kako bi bio siguran, da"),
])
def test_two_whole_words_are_a_form_where_the_second_is_surely_the_feminine(text, feminine, masculine):
    """An l-participle and its feminine, an adjective of the fleeting-a
    table and its feminine (Fable's review, 27.11.2026: the guide's
    "Spreman/spremna", "bio/bila"); nothing else with a whole word after
    its slash (the tokens below)."""
    assert (grammar.gendered(text, "f"), grammar.gendered(text, "m")) == (feminine, masculine)


@pytest.mark.parametrize("text", [
    "24/7", "km/h", "da/ne", "i/ili", "n/a", "N/A", "https://qmt.hr/a", "http://primjer.hr/la", "www.qmt.hr/na",
    "ivan/a@qmt.hr", "ana@qmt.hr/a", "/a", "/la", "/ paket", "60–80 / paket", "/static/a", "a/b/la", "sam/a/b",
    "bio/la2", "bio/la_x", "bio/lak", "sam/ab", "(sam/a)", "„bio/la”", "\"sam/a\"", "x/la", "tvoj/na", "spremio/na",
    "bio/la-ova", "sam/A1", "2x/la", "",
    # two whole words that are no gendered pair: a noun's forms by number above all
    "dan/dana", "mjesec/mjeseca", "tjedan/tjedana", "trening/treninga", "sat/sata", "plan/plana", "termin/termina",
    "on/ona", "online/offline", "auto/automobil", "bio/bile", "spreman/spremni", "motiviran/motivirana",
])
def test_a_token_that_is_no_slash_form_never_changes(text):
    """No whole token of letters, a slash and an ending with nothing but
    punctuation after it, or one the rules do not cover: as it is, for
    either sex."""
    assert grammar.gendered(text, "f") == text and grammar.gendered(text, "m") == text


def test_no_sex_is_the_identity():
    """For a reader who has not said (None, and any value that is no sex)
    the text comes back as the very object, character for character: every
    text the registry and the questions hold, a Markup safe as it was, and
    anything that is no text at all."""
    from markupsafe import Markup
    for text in registry_texts().values():
        for sex in (None, "", "x", "F", "žensko"):
            assert grammar.gendered(text, sex) is text
    safe = Markup("<b>Nisam bio/la</b> sam/a")
    assert grammar.gendered(safe, None) is safe
    out = grammar.gendered(safe, "f")
    assert isinstance(out, Markup) and str(out) == "<b>Nisam bio/la</b> sama"      # "<b>Nisam" is no word alone
    for thing in (None, 7, ["bio/la"]):
        assert grammar.gendered(thing, "f") is thing


# ---------- the profile ----------

def field(page: str) -> str:
    """The profile's "Spol" field, its label to its end."""
    return page.split('<div class="field"><label for="p-sex">', 1)[1].split("</div>", 1)[0]


def test_the_profile_has_spol_after_the_birth_date_its_three_slots_and_tekstovi():
    """/profil's "Spol": after "Datum rođenja", before the phone, a native
    select named sex, the none option first ("Ne želim navesti") and then
    models.SEXES in their order (Žensko, Muško), the stored one selected;
    its label "Spol (neobavezno)" and its hint under it (described by it).
    The three are slots: the label and the none option required (a
    control's words), the hint optional (emptied, no element and no
    aria-describedby for a reader); /tekstovi lists them under Profil. No
    other page asks for it: no reminder, nothing at sign-up."""
    ivan = make_user("ivan@test.local")
    page = client_for("ivan@test.local").get("/profil").text
    assert page.index('for="p-born"') < page.index('for="p-sex"') < page.index('for="p-phone"')
    f = field(page)
    assert f.startswith('<span class="t">Spol (neobavezno)</span></label>')
    assert '<select id="p-sex" name="sex" aria-describedby="p-sex-hint">' in f
    assert re.findall(r'<option value="([^"]*)"( selected)?>([^<]*)</option>', f) == [
        ("", "", "Ne želim navesti"), ("f", "", "Žensko"), ("m", "", "Muško")]
    assert ('<p class="hint p-sex-hint" id="p-sex-hint"><span class="t">Da ti se aplikacija obraća u pravom rodu: '
            '„bio” ili „bila”, ne „bio/la”.</span></p>') in f
    set_sex(ivan, "m")
    f = field(client_for("ivan@test.local").get("/profil").text)
    assert '<option value="m" selected>Muško</option>' in f and '<option value="f">Žensko</option>' in f
    slots = {k: copy.SLOTS[k] for k in ("profil.form.sex", "profil.form.sex_none", "profil.form.sex_hint")}
    assert [(s.default, s.required) for s in slots.values()] == [
        ("Spol (neobavezno)", True), ("Ne želim navesti", True),
        ("Da ti se aplikacija obraća u pravom rodu: „bio” ili „bila”, ne „bio/la”.", False)]
    profil = next(areas for page_, *_, areas in copy.TEXT_PAGES if page_ == "Profil")
    assert all(k in profil[0][1] for k in slots)
    trener = make_user("trener@test.local", is_trainer=True)
    t = client_for("trener@test.local")
    tekstovi = t.get("/tekstovi").text
    assert all(f'data-copy="{k}"' in tekstovi for k in slots)
    db.set_copy("profil.form.sex_none", "Radije ne bih", trener)
    db.set_copy("profil.form.sex_hint", "", trener)
    f = field(client_for("ivan@test.local").get("/profil").text)
    assert '<option value="">Radije ne bih</option>' in f and "p-sex-hint" not in f
    assert 'aria-describedby' not in f
    assert '<select id="p-sex" name="sex" aria-describedby="p-sex-hint">' in field(t.get("/profil").text)   # his box
    for path in ("/", "/raspored", "/karton", "/moja-clanarina"):
        assert 'name="sex"' not in client_for("ivan@test.local").get(path).text, path
    signup = TestClient(app).get("/signup").text
    assert 'name="sex"' not in signup and "Spol" not in signup


def test_the_profile_saves_clears_refuses_junk_and_keeps_what_a_form_does_not_post():
    """POST /profil: sex=f / m is stored, "" clears it ("Ne želim navesti"),
    anything else is refused with "Neispravan spol." and nothing at all is
    saved; a form that posts no sex (a page drawn before the field) keeps
    the stored one."""
    ivan = make_user("ivan@test.local")
    ci = client_for("ivan@test.local")
    old = {"name": "Ivan", "last_name": "Horvat", "birth_date": "1990-01-01", "phone": ""}
    for posted, stored in (("f", "f"), ("m", "m"), ("", None), ("f", "f")):
        r = ci.post("/profil", data={**old, "sex": posted}, follow_redirects=False)
        assert location(r) == "/profil?ok=Podaci su spremljeni." and db.get_user(ivan).sex == stored, posted
    for junk in ("x", "F", "žensko", "fm", "1"):
        r = ci.post("/profil", data={**old, "name": "Ivo", "sex": junk}, follow_redirects=False)
        assert location(r) == "/profil?error=Neispravan spol.", junk
        assert (db.get_user(ivan).sex, db.get_user(ivan).name) == ("f", "Ivan"), junk
    r = ci.post("/profil", data={**old, "phone": "091 234 5678"}, follow_redirects=False)   # no sex posted
    assert location(r) == "/profil?ok=Podaci su spremljeni."
    assert (db.get_user(ivan).sex, db.get_user(ivan).phone) == ("f", "091 234 5678")
    page = ci.get("/profil?error=Neispravan spol.").text
    assert '<span>Neispravan spol.</span>' in page


def test_staff_acting_as_a_member_set_his_sex_and_the_record_has_it():
    """Staff in a member's account set his "Spol" as he would (it is his
    profile): his row changes, the staff member's not; the record names the
    write."""
    ivan = make_user("ivan@test.local", plans=("grupni",))
    trener = make_user("trener@test.local", is_trainer=True, sex="m")
    t = client_for("trener@test.local")
    assert t.post(f"/kao/{ivan}", follow_redirects=False).status_code == 303
    r = t.post(f"/profil?kao={ivan}", data={"name": "ivan", "last_name": "Test", "birth_date": "1990-01-01",
                                            "phone": "", "sex": "f"}, follow_redirects=False)
    assert location(r) == "/profil?ok=Podaci su spremljeni."
    assert (db.get_user(ivan).sex, db.get_user(trener).sex) == ("f", "m")
    rows, _ = db.acting_log()
    assert (rows[0].method, rows[0].path, rows[0].status, rows[0].member_id) == ("POST", "/profil", 303, ivan)


# ---------- where it applies: a member's pages ----------

def member_pages(c: TestClient) -> dict[str, str]:
    """A member's karton (a finished termin of his with nothing written:
    its row's "Nisam bio/la" and the confirm it asks), his upitnik (the
    guide first, then the questions) and his profile."""
    return {"karton": c.get("/karton").text, "upitnik": c.get("/upitnik").text, "profil": c.get("/profil").text}


def setup_member(sex: str | None) -> tuple[int, int]:
    """ivan, grupni and online, a finished termin he owes; the questions."""
    seed_questions()
    ivan = make_user("ivan@test.local", plans=("grupni", "online"), sex=sex)
    return ivan, attended(ivan)


@pytest.mark.parametrize("sex, word, sure, trained, motivated, welcome, since", [
    ("f", "bila", "sigurna", "trenirala", "motivirana", "Dobrodošla", "Registrirana od"),
    ("m", "bio", "siguran", "trenirao", "motiviran", "Dobrodošao", "Registriran od"),
    (None, "bio/la", "siguran/na", "trenirao/la", "motiviran/a", "Dobrodošao/la", "Registriran/a od"),
])
def test_a_member_reads_every_text_in_his_form(sex, word, sure, trained, motivated, welcome, since):
    """A member who gave "f", one who gave "m", one who has not: his karton
    (the diary's lead, his finished termin's "Nisam bio/la", the confirm's
    title and button in its attributes, base.html's default confirm title
    in a script: copy_text), the upitnik (the guide's title, a question, a
    scale's end), his profile; the stored texts unchanged, and no mark of
    the editor's on any of it."""
    ivan, sid = setup_member(sex)
    ci = client_for("ivan@test.local")
    pages = member_pages(ci)
    karton = pages["karton"]
    assert f"ili označi da nisi {word}.</span>" in karton
    assert f'<button type="submit" class="act act-absent"><span class="t">Nisam {word}</span></button>' in karton
    assert f'data-confirm-title="Nisi {word} na terminu?"' in karton and f'data-confirm-cta="Da, nisam {word}"' in karton
    assert f'form.dataset.confirmTitle || "Jesi li {sure}?"' in karton
    up = pages["upitnik"]
    assert f'<span class="t">{welcome} u vodič kroz trening</span>' in up
    assert f'<span class="t">Koliko redovito si {trained} u zadnjih 6 mjeseci (2x tjedno ili više)?</span>' in up
    assert f'<span>10 = <span class="t">jako sam {motivated}</span></span>' in up
    assert f'<span class="t">{since}</span>' in pages["profil"]
    for page in pages.values():
        assert ' data-raw="' not in page and ' data-rod="' not in page and 'data-copy="' not in page
    assert db.copy_texts() == {}
    # and a text the gym owner retypes with a slash form of his own
    db.set_copy("karton.diary.title", "Dnevnik — jesi li bio/la redovit/a?", None)
    db.set_copy("raspored.sheet.booked", "Rezervirao/la si", None)
    karton, raspored = ci.get("/karton").text, ci.get("/raspored").text
    if sex is None:
        assert '<span class="t">Dnevnik — jesi li bio/la redovit/a?</span>' in karton
        assert 'BOOKED = "Rezervirao/la si"' in raspored
    else:
        regular = "redovita" if sex == "f" else "redovit"
        booked = "Rezervirala si" if sex == "f" else "Rezervirao si"
        assert f'<span class="t">Dnevnik — jesi li {word} {regular}?</span>' in karton
        assert f'BOOKED = "{booked}"' in raspored                               # a script's word (copy_text)


def test_an_option_reads_in_his_form_and_posts_the_stored_text():
    """A choice's option with a slash form (the gym owner's): a member who
    gave "f" reads it in her form, and its radio's value is the row's text
    as stored; her upitnik saves, the answer the stored text."""
    seed_questions()
    db.set_upitnik_question_options(4, ["Kod kuće, sam/a", "U teretani"], None)
    ana = make_user("ana@test.local", plans=("online",), sex="f")
    ca = client_for("ana@test.local")
    page = ca.get("/upitnik").text
    assert '<input type="radio" name="q4" value="Kod kuće, sam/a" required><span class="t">Kod kuće, sama</span>' in page
    form = {f"q{q['id']}": q["options"][0] for q in copy.UPITNIK_DEFAULT_QUESTIONS if q["kind"] == "choice"}
    form.update({f"q{q['id']}": "2" for q in copy.UPITNIK_DEFAULT_QUESTIONS if q["kind"] == "scale"})
    form.update({"q4": "Kod kuće, sam/a", "q15": "ne", "consent": "da"})
    r = ca.post("/upitnik", data=form, follow_redirects=False)
    assert location(r).startswith("/treninzi?ok=Upitnik je spremljen")
    assert json.loads(db.get_onboarding(ana).answers)["q4"] == "Kod kuće, sam/a"


def test_the_four_sentences_in_code_arrive_in_his_form():
    """The sentences in code that carry a slash form, each on its path: the
    paket spent and the termin already held (book(), POST /book: the
    raspored's ?error=, base.html's alert), the absence of a termin he was
    not booked into and the absence noted (POST /karton/absent: the
    karton's ?error= and ?ok=, base.html's alerts). The address carries the
    sentence as the code says it; the page says it as its reader reads it:
    a woman her form, one who has not said the sentence as it is."""
    for sex, word, used, held, booked in (("f", "bila", "Iskoristila", "rezervirala", "prijavljena"),
                                          (None, "bio/la", "Iskoristio/la", "rezervirao/la", "prijavljen/a")):
        Base.metadata.drop_all(db.engine); Base.metadata.create_all(db.engine)
        ivan = make_user("ivan@test.local", sex=sex)
        db.record_payment(ivan, "grupni", sessions_per_cycle=1)
        soon = datetime.now(config.TZ).replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=1)
        first, second = (db.add_oneoff_session("Grupni trening", soon + timedelta(hours=h), 60, 8, None) for h in (0, 1))
        ci = client_for("ivan@test.local")
        assert ci.post(f"/book/{first}", follow_redirects=False).status_code == 303
        r = ci.post(f"/book/{second}", follow_redirects=False)                  # the paket of one is spent
        assert location(r).startswith("/raspored?error=Iskoristio/la si svih 1 treninga u ciklusu"), location(r)
        assert f"<span>{used} si svih 1 treninga u ciklusu" in ci.get(r.headers["location"]).text
        db.record_payment(ivan, "grupni", sessions_per_cycle=None)              # unlimited: the next refusal
        r = ci.post(f"/book/{first}", follow_redirects=False)
        assert location(r) == "/raspored?error=Već si rezervirao/la ovaj termin.", location(r)
        assert f"<span>Već si {held} ovaj termin.</span>" in ci.get(r.headers["location"]).text
        other = attended(make_user("ana@test.local"))
        r = ci.post(f"/karton/absent/{other}", follow_redirects=False)
        assert location(r) == "/karton?error=Termin ne postoji ili nisi bio/la prijavljen/a."
        assert f"<span>Termin ne postoji ili nisi {word} {booked}.</span>" in ci.get(r.headers["location"]).text
        r = ci.post(f"/karton/absent/{attended(ivan)}", follow_redirects=False)
        assert location(r) == "/karton?ok=Zabilježeno — nisi bio/la na terminu."
        page = ci.get(r.headers["location"]).text
        assert f'<div class="alert ok" role="status">Zabilježeno — nisi {word} na terminu.</div>' in page
        assert f'<span class="chip"><span class="t">Nisam {word}</span></span>' in page    # his absence's row


def test_a_sentence_a_script_says_is_resolved_in_its_route(monkeypatch):
    """The gym training's tick answers its script in JSON ({"ok", "error",
    "mark"}): its sentence as the member reads it (no sentence of today
    carries a slash form: one does here)."""
    monkeypatch.setattr(web, "GYM_EMPTY_ROW", "Nisi upisao/la broj — sam/a ga upiši.")
    for sex, said in (("f", "Nisi upisala broj — sama ga upiši."), ("m", "Nisi upisao broj — sam ga upiši."),
                      (None, "Nisi upisao/la broj — sam/a ga upiši.")):
        Base.metadata.drop_all(db.engine); Base.metadata.create_all(db.engine)
        ana = make_user("ana@test.local", plans=("grupni",), sex=sex)
        tid = db.add_gym_outside(ana, config.today())
        bid = db.add_gym_block(tid, ana, "stanica")                          # a Stanica (27.11.2026, the blocks)
        db.set_gym_station(bid, ana, db.create_exercise("Goblet čučanj"), 3, 10, None, 20, 60)
        item = db.gym_training(tid, ana).blocks[0].item
        r = client_for("ana@test.local").post(
            f"/dvoranski/trening/{tid}/blok/{bid}/odradeno", headers={"Accept": "application/json"},
            data={"polja": ",".join(db.set_fields(item)), "rows": "1", "reps_1": "", "kg_1": ""})
        assert r.status_code == 400 and r.json() == {"ok": False, "error": said, "mark": "", "done": False}, sex


def test_the_karton_reads_its_members_form_for_staff_too():
    """The trainer's view of a member's karton reads as the member's sex,
    whatever the trainer's (the texts there are about him): his absence's
    chip, the upitnik's "Odgovori", each question by the member whose
    answers they are, the editor's span resolved with its stored text
    beside it; and staff acting as the member read his form, as he does."""
    seed_questions()
    ana = make_user("ana@test.local", plans=("grupni", "online"), sex="f")
    answered(ana)
    trener = make_user("trener@test.local", is_trainer=True, sex="m")
    ca = client_for("ana@test.local")
    ca.post(f"/karton/absent/{attended(ana)}")
    t = client_for("trener@test.local")
    view = t.get(f"/karton/{ana}").text
    assert ('<span class="chip"><span class="ed t" data-copy="karton.diary.absent_chip" data-max="2000" '
            'data-label="Karton · dnevnik: oznaka izostanka" data-raw="Nisam bio/la">Nisam bila</span></span>') in view
    assert "<li>Koliko redovito si trenirala u zadnjih 6 mjeseci (2x tjedno ili više)? — <strong>7 / 10</strong></li>" in view
    assert "<li>Koliko si motivirana za promjenu i dosljednost? — <strong>8 / 10</strong></li>" in view
    assert 'id="copyToggle" aria-pressed="false" data-rod="f"' in view       # the page's reader: hers
    own = t.get("/karton").text                                              # his own karton: his
    assert 'data-rod="m"' in own and ">Tvoji online treninzi i treninzi koje upišeš sam.</span>" in own
    assert t.post(f"/kao/{ana}", follow_redirects=False).status_code == 303
    as_her = t.get("/karton").text                                           # acting: her form, as she reads it
    assert '<span class="chip"><span class="t">Nisam bila</span></span>' in as_her
    assert "<li>Koliko redovito si trenirala u zadnjih 6 mjeseci (2x tjedno ili više)? — <strong>7 / 10</strong></li>" in as_her
    assert ' data-raw="' not in as_her and ' data-rod="' not in as_her
    t.post("/kao/izlaz", follow_redirects=False)
    set_sex(ana, None)                                                       # not said: as stored, the trainer's view too
    view = t.get(f"/karton/{ana}").text
    assert ">Nisam bio/la</span></span>" in view and ' data-rod="' not in view and ' data-raw="' not in view
    assert "<li>Koliko redovito si trenirao/la u zadnjih 6 mjeseci (2x tjedno ili više)? — <strong>7 / 10</strong></li>" in view


def test_the_reset_email_reads_as_the_accounts_sex(monkeypatch):
    """The password-reset email's "tražio/la" as the account's sex (none:
    as it is); the verification email stays as it is."""
    sent = []
    monkeypatch.setattr(mailer, "_send", lambda to, subject, html: sent.append((to, subject, html)) or True)
    for email, sex in (("ana@test.local", "f"), ("ivan@test.local", "m"), ("sara@test.local", None)):
        make_user(email, sex=sex)
        assert TestClient(app).post("/forgot", data={"email": email}).status_code == 200
    by = {to: html for to, _, html in sent}
    assert "Ako nisi ti tražila promjenu, ignoriraj poruku" in by["ana@test.local"]
    assert "Ako nisi ti tražio promjenu, ignoriraj poruku" in by["ivan@test.local"]
    assert "Ako nisi ti tražio/la promjenu, ignoriraj poruku" in by["sara@test.local"]
    # that word alone: the rest of the email, its link's token aside, as it was
    same = {to: re.sub(r"token=[^\"]+", "token=…", html) for to, html in by.items()}
    assert same["sara@test.local"].count("tražio/la") == 1
    assert same["sara@test.local"].replace("tražio/la", "tražila") == same["ana@test.local"]
    assert same["sara@test.local"].replace("tražio/la", "tražio") == same["ivan@test.local"]
    sent.clear()
    mailer.send_verification_email("ana@test.local", "http://x/verify")
    assert "Ako se nisi ti\n        registrirao/la, slobodno ignoriraj" in sent[0][2]


# ---------- the editor keeps the stored text ----------

def test_an_editor_with_a_sex_reads_the_resolved_text_beside_the_stored_one():
    """The trainer (here the owner) who gave "m": outside edit mode the
    resolved text, the stored one in data-raw on the span (a slot, a list's
    item, a table's cell, an upitnik question's text), the toggle saying
    whose (data-rod); a span whose text reads alike carries none."""
    seed_questions()
    trener = make_user("trener@test.local", is_trainer=True, sex="m")
    db.set_copy("info.hours.rows", copy.dump_rows([["sam/a", "07–20"], ["sub", "zatvoreno"]]), trener)
    db.set_copy("offer.online.points", copy.dump_items(["Treniraš sam/a", "Video upute"]), trener)
    t = client_for("trener@test.local")
    own = t.get("/karton").text
    assert ('<span class="ed t" data-copy="karton.staff.own_diary_lead" data-max="2000" data-label="Karton · osoblje: '
            'uvodna rečenica dnevnika" data-raw="Tvoji online treninzi i treninzi koje upišeš sam/a.">Tvoji online '
            'treninzi i treninzi koje upišeš sam.') in span(own, "karton.staff.own_diary_lead")
    assert all("data-raw" not in s for s in span(own, "karton.diary.title"))   # reads alike: no stored text beside it
    assert own.count('data-rod="m"') == 1
    landing = t.get("/").text
    assert 'data-index="0" data-part="0" data-max="2000" data-label="Radno vrijeme, red 1: dani" data-raw="sam/a">sam</span>' in landing
    assert 'data-index="0" data-max="2000" data-label="Online 1: stavka" data-raw="Treniraš sam/a">Treniraš sam</span>' in landing
    page = t.get("/upitnik").text
    assert ('data-label="Pitanje 5: tekst" data-raw="Koliko redovito si trenirao/la u zadnjih 6 mjeseci (2x tjedno ili '
            'više)?">Koliko redovito si trenirao u zadnjih 6 mjeseci (2x tjedno ili više)?</span>') in page


def test_an_editor_with_no_sex_reads_and_edits_what_he_does_today():
    """The trainer who has not said: every span his stored text as it is,
    no data-raw, no data-rod; a save's answer as it was (no shown text)."""
    seed_questions()
    make_user("trener@test.local", is_trainer=True)
    t = client_for("trener@test.local")
    for path in ("/karton", "/upitnik", "/", "/profil", "/tekstovi", "/vodic"):
        page = t.get(path).text
        assert ' data-raw="' not in page and ' data-rod="' not in page, path
    assert span(t.get("/karton").text, "karton.staff.own_diary_lead")[0].endswith(
        ">Tvoji online treninzi i treninzi koje upišeš sam/a.")
    key = "karton.staff.own_diary_lead"
    r = t.post(f"/copy/{key}", data={"text": "Treninzi koje si upisao/la sam/a."}).json()
    assert r == {"ok": True, "text": "Treninzi koje si upisao/la sam/a.", "default": False}


def test_a_save_answers_with_the_stored_text_and_the_one_to_show():
    """POST /copy/{key} with the page's sex (the editor's script posts it,
    rod): what is stored is the text as typed, and the answer carries
    beside it the text to show (shown), for every kind of text the editor
    saves: a slot (and Zadano), a list's item, a table's cell, a row's
    field (an announcement's), an upitnik question's text and option. With
    no sex, or one that is none, the answer as it was."""
    seed_questions()
    trener = make_user("trener@test.local", is_trainer=True, sex="m")
    t = client_for("trener@test.local")
    key = "karton.staff.own_diary_lead"
    r = t.post(f"/copy/{key}", data={"text": "Treninzi koje si upisao/la sam/a.", "rod": "f"}).json()
    assert r == {"ok": True, "text": "Treninzi koje si upisao/la sam/a.", "default": False,
                 "shown": "Treninzi koje si upisala sama."}
    assert db.copy_texts()[key] == "Treninzi koje si upisao/la sam/a."           # stored as typed
    r = t.post(f"/copy/{key}", data={"reset": "1", "rod": "m"}).json()        # Zadano
    assert r == {"ok": True, "text": copy.SLOTS[key].default, "default": True,
                 "shown": "Tvoji online treninzi i treninzi koje upišeš sam."}
    for rod in ("", "x", "žensko"):
        assert "shown" not in t.post(f"/copy/{key}", data={"text": "sam/a", "rod": rod}).json(), rod
    r = t.post("/copy/offer.online.points", data={"text": "Treniraš sam/a", "index": "0", "rod": "f"}).json()
    assert r["items"][0] == "Treniraš sam/a" and r["shown_items"] == ["Treniraš sama", *r["items"][1:]]
    r = t.post("/copy/info.hours.rows", data={"text": "bio/la", "index": "1", "part": "1", "rod": "f"}).json()
    assert r["rows"][1] == ["uto", "bio/la"] and r["shown_rows"][1] == ["uto", "bila"]
    assert r["shown_rows"][0] == r["rows"][0]
    ann = db.add_announcement(trener).id
    r = t.post(f"/copy/aktualno.{ann}.title", data={"text": "Jesi li spreman/na?", "rod": "m"}).json()
    assert r == {"ok": True, "text": "Jesi li spreman/na?", "default": False, "shown": "Jesi li spreman?"}
    r = t.post("/copy/upitnik.5.text", data={"text": "Jesi li trenirao/la?", "rod": "f"}).json()
    assert (r["text"], r["shown"]) == ("Jesi li trenirao/la?", "Jesi li trenirala?")
    r = t.post("/copy/upitnik.1.options", data={"text": "Sam/a", "index": "0", "rod": "f"}).json()
    assert r["items"][0] == "Sam/a" and r["shown_items"][0] == "Sama"
    assert db.upitnik_question(1).option_items[0] == "Sam/a"
    r = t.post("/copy/hero.kicker", data={"text": "x" * 2001, "rod": "f"})
    assert r.status_code == 400 and "shown" not in r.json()                   # a refusal as it was


# ---------- a reader who has not said: his pages as they were ----------

READER_PAGES = ("/karton", "/raspored", "/upitnik", "/vodic", "/treninzi", "/moja-clanarina", "/prehrana", "/",
                "/profil")


def unselected(html: str) -> str:
    """A page with the profile's "Spol" showing none chosen: the one place
    a page shows the sex itself, to its own member (his select)."""
    return re.sub(r'(<option value="[fm]") selected>', r"\1>", html)


def test_the_sex_reaches_a_readers_page_through_the_resolver_alone(monkeypatch):
    """A member's pages (a finished termin of his, the upitnik's questions),
    once with no sex and once with "f" while the resolver is the identity:
    the same bytes but for his own profile's select, which shows his choice,
    so a sex changes a reader's page nowhere but in the words the resolver
    gives it (no attribute, no mark). And with no sex the resolver is the
    identity, so such a reader's page is what the templates print with no
    resolver at all. A guest's pages, the same way. The editor's: the same
    but for the toggle's data-rod."""
    seed_questions()
    ivan = make_user("ivan@test.local", plans=("grupni", "online"))
    attended(ivan)
    trener = make_user("trener@test.local", is_trainer=True)
    ci, t, guest = client_for("ivan@test.local"), client_for("trener@test.local"), TestClient(app)
    for c in (ci, t):
        c.get("/raspored")                                                    # the login's one-shot prompt, and the week
    def pages(c, paths=READER_PAGES):
        return {p: c.get(p).text for p in paths}
    before, before_staff = pages(ci), pages(t, ("/karton", "/upitnik", "/", "/tekstovi", "/profil"))
    before_guest = pages(guest, ("/", "/prehrana", "/login", "/signup", "/forgot"))
    assert "Nisam bio/la" in before["/karton"] and "trenirao/la" in before["/upitnik"]
    real = grammar.gendered
    monkeypatch.setattr(grammar, "gendered", lambda text, sex: text)
    set_sex(ivan, "f"); set_sex(trener, "m")
    now = pages(ci)
    assert '<option value="f" selected>Žensko</option>' in now["/profil"]
    assert {p: unselected(html) for p, html in now.items()} == before
    assert {p: unselected(html).replace(' data-rod="m"', "", 1)
            for p, html in pages(t, before_staff).items()} == before_staff
    assert pages(guest, before_guest) == before_guest
    monkeypatch.setattr(grammar, "gendered", real)
    after = pages(ci)
    assert "Nisam bila" in after["/karton"] and "trenirala" in after["/upitnik"] and after != before
    set_sex(ivan, None); set_sex(trener, None)
    assert pages(ci) == before and pages(t, before_staff) == before_staff


# ---------- in a browser ----------

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


def test_edit_mode_shows_the_stored_text_and_a_save_shows_the_resolved_one_with_no_reload(server):
    """The owner, "m", on his own karton at 390px on a touch screen: the
    diary's lead reads "… upišeš sam." (the page's and the editor's panel's
    span alike); edit mode shows "… sam/a.", leaving it "… sam." again.
    Retyped in edit mode with a new slash form, it is stored as typed and
    shows so while edit mode lasts, and as he reads it once it ends; a
    heading with no slash form retyped with one the same. All of it with
    no reload; no page errors."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    make_user("trener@test.local", is_trainer=True, sex="m")
    key, title = "karton.staff.own_diary_lead", "karton.weight.title"
    raw, shown = copy.SLOTS[key].default, "Tvoji online treninzi i treninzi koje upišeš sam."
    problems, errs = [], []

    def check(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    def texts(k: str) -> list[str]:
        return pg.evaluate("(k) => [...document.querySelectorAll(`[data-copy=\"${k}\"]`)].map(e => e.textContent)", k)

    def saved(k: str, text: str) -> None:
        pg.tap("#cbSave")
        try:
            pg.wait_for_function("() => document.getElementById('copyBar').hidden", timeout=5000)
        except Exception:
            problems.append(f"{k}: Spremi did not close the bar")
        check(db.copy_texts().get(k) == text, f"{k} stored {db.copy_texts().get(k)!r}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(server + "/login"); pg.evaluate("() => { localStorage.setItem('qmt-a2hs', 'installed'); localStorage.setItem('qmt-phone', String(Date.now())); }")
        pg.fill("main input[name=email]", "trener@test.local"); pg.fill("main input[name=password]", "lozinka123")
        pg.click("main button[type=submit]"); pg.wait_for_load_state("networkidle")
        pg.goto(server + "/karton"); pg.wait_for_load_state("networkidle")
        pg.evaluate("() => { window.qmtSame = 1; }")                          # a reload would lose it
        check(texts(key) == [shown, shown], f"outside edit mode: {texts(key)}")
        pg.tap("#copyToggle")
        check(texts(key) == [raw, raw], f"edit mode: {texts(key)}")
        pg.tap("#copyToggle")
        check(texts(key) == [shown, shown], f"edit mode left: {texts(key)}")
        pg.tap("#copyToggle")
        lead = pg.locator(f'.k-sec [data-copy="{key}"]')
        lead.tap(); lead.fill("Treninzi koje si upisao/la sam/a.")
        saved(key, "Treninzi koje si upisao/la sam/a.")
        check(texts(key) == ["Treninzi koje si upisao/la sam/a."] * 2, f"saved, in edit mode: {texts(key)}")
        heading = pg.locator(f'#masa-h [data-copy="{title}"]')
        heading.tap(); heading.fill("Jesi li spreman/na?")
        saved(title, "Jesi li spreman/na?")
        check(texts(title)[0] == "Jesi li spreman/na?", f"the heading, in edit mode: {texts(title)}")
        pg.tap("#copyToggle")
        check(texts(key) == ["Treninzi koje si upisao sam."] * 2, f"saved, edit mode left: {texts(key)}")
        check(set(texts(title)) == {"Jesi li spreman?"}, f"the heading, edit mode left: {texts(title)}")
        check(lead.get_attribute("data-raw") == "Treninzi koje si upisao/la sam/a.", "the lead's stored text")
        pg.tap("#copyToggle")
        check(texts(title)[0] == "Jesi li spreman/na?", f"the heading, edit mode again: {texts(title)}")
        pg.tap("#copyToggle")
        check(pg.evaluate("() => window.qmtSame") == 1, "the page was reloaded")
        check(pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth") == 0,
              "the page overflows")
        browser.close()
    print("\n".join(problems + errs))
    assert not problems and not errs, f"{len(problems + errs)} problems, listed above"
