"""The rule that every text a member or a guest reads is editable in place
(25.11.2026, the owner to Amir: "svugdje ikad uvest pravilo da može
uređivat"; to Fable: "If there is a place where he is not allowed to change
text, lets allow it"), held for the pages to come.

A static scan of every member-facing template (the pages a member or a
guest reaches and the partials they print; the staff-only templates stay
as they are): Jinja's comments, tags and expressions, the <script> and
<style> blocks, the <title> block (the page's title stays code) and main's
class block stripped, then the HTML tags; what is left, and the literal
words of the attributes a reader meets in a confirm or a field (placeholder,
data-confirm, data-confirm-title, data-confirm-cta: a value inside them is
an expression, stripped), is a template's literal text. Every fragment that
holds a letter must be a copy slot (src/qmt/copy.py, printed with c.t,
c.opt or copy_text) or be in ALLOWED, the fragments that stay code, each
group with its reason (CLAUDE.md, "Every member-facing text"). An allowed
fragment the template no longer prints goes from the list too: it stays
short and true.

Then /tekstovi's grouping (copy.TEXT_PAGES): every plain slot in exactly one
page's area, in the nav's order; and every slot of this build printed by a
template or by the code (a slot no page prints would only be a row there).
"""

from __future__ import annotations

import os
import re
from html import unescape
from pathlib import Path

# as every module, before qmt is imported (config reads them once): never the
# dev DB, and the suite's owner, whichever module the run imports first
os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["OWNER_EMAIL"] = "trener@test.local"

from qmt import copy
from qmt.web import app as web

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "qmt" / "web" / "templates"
APP = Path(web.__file__).read_text()

ATTRS = ("placeholder", "data-confirm", "data-confirm-title", "data-confirm-cta")
LETTER = re.compile(r"[^\W\d_]")
JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)
FIX = "make it a slot (copy.py) or add it to the allowlist with the reason"


def fragments(source: str) -> set[str]:
    """A template's literal texts that hold a letter (the module's docstring)."""
    src = re.sub(r"\{#.*?#\}", " ", source, flags=re.S)
    src = re.sub(r"\{%-?\s*block (title|main_class)\s*-?%\}.*?\{%-?\s*endblock\s*-?%\}", " ", src, flags=re.S)
    src = re.sub(r"<(script|style)\b.*?</\1\s*>", " ", src, flags=re.S | re.I)
    out = set()
    # an attribute's value may hold an expression with quotes in it: tags and
    # attributes are found on the source with every expression masked
    masked = JINJA.sub(lambda m: "\x00" * len(m.group(0)), src)
    for tag in re.finditer(r"<[a-zA-Z][^>]*>", masked):
        for name in ATTRS:
            for m in re.finditer(rf'\s{name}="([^"]*)"', masked[tag.start():tag.end()]):
                raw = src[tag.start() + m.start(1):tag.start() + m.end(1)]
                for part in JINJA.split(raw):
                    part = " ".join(unescape(part).split())
                    if LETTER.search(part):
                        out.add(f"@{name}: {part}")
    text = re.sub(r"<[^>]*>", "\n", JINJA.sub("\n", src))
    for part in text.split("\n"):
        part = " ".join(unescape(part).split())
        if LETTER.search(part):
            out.add(part)
    return out


# The member-facing templates (the brief of 25.11.2026, its decision 1, and
# the karton of the same day): every page a member or a guest reaches, and
# the partials they print. Since 26.11.2026 (build 3) the gym training's two
# pages, the rest bar the player and it share, and the tag chips its "Dodaj
# vježbu" prints (the day editor's and the library's until then).
MEMBER_TEMPLATES = (
    "base.html", "landing.html", "calendar.html", "karton.html", "treninzi.html", "trening_view.html",
    "trening_day.html", "trening_player.html", "trening_kraj.html", "_pass_leave.html", "moja_clanarina.html",
    "_plan_price.html", "_period.html", "_tiers.html", "prehrana.html", "upitnik.html", "_vodic.html", "vodic.html",
    "profil.html", "login.html", "signup.html", "forgot.html", "reset.html", "verify_sent.html", "error.html",
    "karton_trening.html", "karton_trening_osvrt.html", "_rest_bar.html", "_tagbar.html",
)
# The templates only staff reach: they stay as they are (the owner was told so).
STAFF_TEMPLATES = (
    "admin.html", "clanarine.html", "korisnici.html", "statistika.html", "roster.html", "template_edit.html",
    "treninzi_admin.html", "trening_edit.html", "trening_day_edit.html", "vjezbe.html", "vjezba.html",
    "tekstovi.html", "kao.html", "kao_zapisi.html",
)

# a sentence built around a value: the fixed words whose grammar hangs on a
# count, a date, a name or a number (a slot when they read as a phrase of
# their own: "Preporučeno:", "Članarina vrijedi do", not these)
ALLOWED: dict[str, set[str]] = {
    "base.html": {
        # the nav: the tabs, Admin ▾ and its items, the drawer's captions,
        # the account menu (the bar's room is measured: tests/test_nav.py)
        "Kao član", "Početna", "Raspored", "Karton", "Online treninzi", "Moja članarina", "Prehrana", "Admin",
        "Gledaj kao član", "Termini", "Trenutne članarine", "Upitnik", "Vježbe", "Tekstovi", "Korisnici",
        "Statistika", "Prijava", "Registriraj se", "Kontakt", "Profil", "Tamna tema", "Odjava",
        # the strip over every page while staff act as a member (26.11.2026):
        # staff's own chrome, which a member never reads
        "Gledaš kao:", "Izađi",
        # the brand, in the bar and on the install banner
        "Quality Movement Training", "QMT",
        # the copy editor's own bar (staff, edit mode)
        "✎ Uredi tekstove", "Enter = novi red · ⌘/Ctrl+Enter = spremi", "Spremi", "Zadano", "Odustani",
        # the osvrt prompt's sentence for 2 or more: its plural follows the count
        "odrađena termina još čekaju tvoj osvrt.", "odrađenih termina još čeka tvoj osvrt.",
    },
    "landing.html": {
        # the editor's own controls (edit mode only)
        "Ukloni sliku", "Obriši najavu", "+ Dodaj najavu", "Obriši karticu", "+ Dodaj karticu",
        # the studio's address and email: each the text of the link it opens (the map, mailto:)
        "Virovska ulica 1, 10040 Zagreb", "qualitymovementtraining@gmail.com",
    },
    "calendar.html": {
        # a confirm that names the termin (its title, day and time)
        "@data-confirm: u", "@data-confirm: Mjesto se oslobađa za druge.", "@data-confirm: . Mjesto se oslobađa za druge.",
        # a value's sentence: the repeat's count, the paket's size, the hours, the weeks, the places
        "— još", "Paket od", "treninga je popunjen, ostatak nije rezerviran.", "h prije termina", "h prije termina.",
        "unaprijed.", "mjesta",
    },
    "karton.html": {
        # the karton's own build (25.11.2026, CLAUDE.md "The karton's texts"):
        # its value sentences, the confirms that name a value, the fields
        # whose label says a size in MB, the crumb, the editor's panel
        "@data-confirm: Unos", "@data-confirm: kg", "@data-confirm: od", "@data-confirm: i njegov dokument bit će trajno obrisani.",
        "@data-confirm: kg od", "@data-confirm: bit će trajno obrisan.", "@data-confirm: Dokument „",
        "@data-confirm: ” bit će trajno obrisan.", "@data-confirm: Fotografija za", "@data-confirm: bit će trajno obrisana.",
        "kg", "Trenutne članarine", "Karton —", "god.", "Bolovi", "bodova", "Razina",
        "od 3 — programi na /treninzi prate ovu razinu.", "Dokument (pdf, jpg, png ili webp, do", "MB)", "Visina", "cm",
        "Fotografija (jpg, png ili webp, do", "Zadnji put:", "Procjena maksimuma:", "napor", "od",
        "Svi tekstovi kartona",
        "Ovdje su i tekstovi koje vidi samo član ili su u prozorima za potvrdu. Promjena u prozorima i poljima vidi "
        "se nakon osvježavanja stranice.",
        # the trainer's view's way into the member's account (26.11.2026):
        # staff's own chrome, as the strip over a page while acting; since
        # build 4 the Karton tab's too (staff's own karton: its field's label
        # and the no-JS select's first option), and the caption over what
        # only the trainer reads of the upitnik while staff act as a member
        "Otvori kao član", "Član", "Odaberi člana…", "Vidi samo trener",
    },
    "trening_view.html": {
        "Treninzi",                          # the crumb
        "· odrađen",                         # "odrađen 2×": a count
    },
    "trening_day.html": {
        "Treninzi", "Trening",               # the crumbs ("Trening 2")
        "Vježba",                            # "Vježba 3": a count's label, as "Trening 2"
        "· napor",                           # the history's line: "napor 7", a value
    },
    "trening_player.html": {
        "Krug", "od",                        # "Krug 2 od 3", "Krug 2": the round's number
        "Vježba",                            # "Vježba 3"
        "Odrađena serija",                   # a screen reader's words, as an aria-label
    },
    "karton_trening.html": {
        "Karton", "Trening",                 # the crumbs (26.11.2026, the gym training)
        "Krug",                              # "Krug 2", a circuit's round's number (part B), as the player's
    },
    "_tagbar.html": {"još"},                 # "još 5": a count (the tag chips past the first twelve)
    "trening_kraj.html": {
        "od",                                # "6 od 8 vježbi"
        "Započet", "i nije završen — nastavak više nije moguć.",   # around its day ("jučer")
    },
    "moja_clanarina.html": {
        # the tier switch's confirm around a count and an amount
        "@data-confirm: Novi paket vrijedi odmah —",
        "@data-confirm: mjesečno. Razliku za ostatak ovog ciklusa Stripe obračuna na sljedećem računu.",
        "@data-confirm-title: Promijeniti na", "@data-confirm-title: treninga?",
        "treninga mjesečno", "od", "u ovom ciklusu", "treninga ·",   # counts
        "Ovo vidi član bez članarine:",      # the editor's caption over his preview
    },
    "_tiers.html": {"treninga ·"},           # "16 treninga · 80 €": a count and an amount
    "upitnik.html": {
        # the editor's own controls of a question (edit mode only)
        "Obriši pitanje", "Dio", "Vrsta", "Bodovanje", "Uloga", "Pita se", "Uvijek", "Samo ako …", "Pitanje",
        "Odgovor", "ili više", "Nijedno pitanje se ne boduje — svi dobivaju početnu razinu.",
        "Ovo vidi član koji odgovori", "ili više:", "+ Dodaj pitanje",
    },
    "verify_sent.html": {
        "Link (dev)", "Email nije konfiguriran (dev) — evo linka:",   # the dev server's, never on prod
        "Ako račun za", "postoji, poslali smo link za novu lozinku.",   # around the address typed
    },
}


def test_every_member_facing_template_is_scanned_and_the_staff_ones_are_not():
    """The scan's list is every template there is, but the staff-only ones."""
    every = {p.name for p in TEMPLATES.glob("*.html")}
    assert set(MEMBER_TEMPLATES) | set(STAFF_TEMPLATES) | {"_copy.html"} == every
    assert not set(MEMBER_TEMPLATES) & set(STAFF_TEMPLATES)
    assert set(ALLOWED) <= set(MEMBER_TEMPLATES)


def test_a_member_facing_template_prints_no_literal_text_but_the_allowed():
    """Every literal text of a member-facing template is a slot or allowed
    with its reason; an allowed one the template no longer prints is taken
    off the list."""
    problems = []
    for name in MEMBER_TEMPLATES:
        found, allowed = fragments((TEMPLATES / name).read_text()), ALLOWED.get(name, set())
        problems += [f"{name}: {f!r} — {FIX}" for f in sorted(found - allowed)]
        problems += [f"{name}: {f!r} is allowed but no longer printed: take it off the list" for f in sorted(allowed - found)]
    assert not problems, "\n".join(problems)
    # short (118 on 25.11.2026, most of them the nav, the karton's and the
    # upitnik editor's; 125 since 26.11.2026: the gym training's crumbs and
    # the tag chips' count; 128 since build 4 the same day: the Karton tab's
    # way into a member's app, its label and its select's first option, and
    # the caption "Vidi samo trener" while staff act as a member; 129 since
    # build 3's part B, the gym training's round "Krug 2"): a long list
    # means texts were left out
    assert sum(len(v) for v in ALLOWED.values()) <= 129


def test_the_scan_sees_a_new_literal_and_strips_what_is_code():
    """The scan itself: a literal word in a tag's text, a placeholder and a
    confirm's words are found; a slot's call, a comment, a script, a style,
    the title and an expression inside an attribute are not."""
    source = ('{% block title %}Naslov — QMT{% endblock %}{# Komentar #}<style>.a { content: "Stil"; }</style>'
              '<script>var x = "Skripta";</script><p class="hint">{{ c.t("raspored.head.title") }} Novi tekst</p>'
              '<input placeholder="npr. nešto"><form data-confirm-title="{{ copy_text(\'x\', t) }}" '
              'data-confirm="{{ s.title }} bit će obrisan." data-confirm-cta="{{ "Makni" if a else "Otkaži" }}">'
              '<button>{{ "Kreni" if a else "Stani" }}</button>')
    assert fragments(source) == {"Novi tekst", "@placeholder: npr. nešto", "@data-confirm: bit će obrisan."}


def test_every_plain_slot_is_on_the_texts_page_once():
    """/tekstovi's grouping (copy.TEXT_PAGES): every plain Slot in exactly
    one page's area, none twice, no list, table, switch or photo among them;
    the pages in the nav's order, an address where staff open the page, the
    lists' line where the page has lists, tables or cards of its own; each
    area's keys in the registry's order."""
    plain = [k for k, s in copy.SLOTS.items() if type(s) is copy.Slot]
    placed = [k for *_, areas in copy.TEXT_PAGES for _, keys in areas for k in keys]
    assert sorted(placed) == sorted(plain) and len(placed) == len(set(placed))
    assert [page for page, *_ in copy.TEXT_PAGES] == [
        "Početna", "Raspored", "Karton", "Online treninzi", "Trening (izvođenje)", "Trening u dvorani",
        "Moja članarina", "Prehrana", "Upitnik", "Vodič", "Profil", "Prijava i registracija", "Aplikacija"]
    assert {page: href for page, href, *_ in copy.TEXT_PAGES} == {
        "Početna": "/", "Raspored": "/raspored", "Karton": "/karton", "Online treninzi": "/treninzi",
        "Trening (izvođenje)": None, "Trening u dvorani": None, "Moja članarina": "/moja-clanarina",
        "Prehrana": "/prehrana", "Upitnik": "/upitnik", "Vodič": "/vodic", "Profil": "/profil",
        "Prijava i registracija": None, "Aplikacija": None}
    assert [page for page, _, lists, _ in copy.TEXT_PAGES if lists] == ["Početna", "Upitnik", "Vodič"]
    order = {k: n for n, k in enumerate(copy.SLOTS)}
    for page, _, _, areas in copy.TEXT_PAGES:
        assert areas and all(keys for _, keys in areas), page
        for area, keys in areas:
            assert list(keys) == sorted(keys, key=order.get), (page, area)
    karton = next(areas for page, *_, areas in copy.TEXT_PAGES if page == "Karton")
    assert karton == copy.KARTON_PANEL                       # the karton's areas are its panel's


# the slots of this build (25.11.2026): the pages that had none, and what
# was still a literal on the landing, /moja-clanarina and /prehrana
BUILD_PREFIXES = ("raspored.", "treninzi.", "program.", "dan.", "player.", "kraj.", "leave.", "profil.", "auth.",
                  "app.", "period.", "landing.")
BUILD_KEYS = {
    "clanarina.h.title", "clanarina.plan.kicker", "clanarina.fact.price", "clanarina.fact.paid",
    "clanarina.fact.next", "clanarina.fact.until", "clanarina.fact.paket", "clanarina.fact.used",
    "clanarina.portal", "clanarina.switch.kicker", "clanarina.switch.cta", "clanarina.to_card.hint",
    "clanarina.to_card.go", "clanarina.subscribe", "clanarina.lapsed.hint", "clanarina.add.featured",
    "clanarina.addon.gym", "clanarina.addon.online", "clanarina.bills.portal", "clanarina.bills.col_date",
    "clanarina.bills.col_plan", "clanarina.bills.col_amount",
    "prehrana.kicker", "prehrana.text_a", "prehrana.text_app", "prehrana.text_b", "prehrana.hint_a",
    "prehrana.hint_bold", "prehrana.hint_b", "prehrana.open"}
BUILD = [k for k in copy.SLOTS if k.startswith(BUILD_PREFIXES) or k in BUILD_KEYS
         or k.startswith(("clanarina.chip.", "clanarina.status."))]


def test_every_slot_of_this_build_is_printed_by_a_template_or_the_code():
    """Each one's key is written in a template or in app.py (PLAN_LINKS' doors),
    but the two families a template names by a value: the reasons a date
    was not booked (raspored.report.why_<key>: the redirect's reason keys,
    app.SKIP_KEYS) and a plan's chip (clanarina.chip.<kind>: the kinds
    app.py gives it). Every one a plain Slot of every text's cap, its label
    unique in the editor's bar. 270 since 26.11.2026: the profile's
    "Visina (cm)" left (the karton's since), the phone reminder's three
    came (app.phone.*); 271 the same day, a dvoranski day's empty slot on
    the day's page (dan.slot, "Prazno mjesto"); 274 since 27.11.2026, the
    profile's "Spol": its label, its none option and its hint
    (profil.form.sex*)."""
    assert len(BUILD) == 274
    sources = APP + "".join((TEMPLATES / n).read_text() for n in MEMBER_TEMPLATES)
    why = {k for k in BUILD if k.startswith("raspored.report.why_")}
    chips = {k for k in BUILD if k.startswith("clanarina.chip.")}
    assert why == {f"raspored.report.why_{key}" for key in web.SKIP_KEYS.values()}
    assert "raspored.report.why_" in sources
    assert {k.rsplit(".", 1)[1] for k in chips} == {"active", "due", "lapsed", "cancelling"}
    assert all(re.search(rf'chip = \("{k.rsplit(".", 1)[1]}", ', APP) for k in chips)
    unused = [k for k in BUILD if k not in why | chips and f'"{k}"' not in sources and f"'{k}'" not in sources]
    assert not unused, f"slots no page prints: {unused}"
    for key in BUILD:
        slot = copy.SLOTS[key]
        assert type(slot) is copy.Slot and slot.max == copy.CAP and slot.label, key
        assert slot.default and copy.clean(slot.default) == slot.default, key
    labels = [copy.SLOTS[k].label for k in copy.SLOTS if type(copy.SLOTS[k]) is copy.Slot]
    assert len(labels) == len(set(labels))                   # the bar names each text apart
