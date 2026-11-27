"""Texts the trainer or owner may edit in place.

Each slot is a piece of copy on a public page. Until 16.10.2026 every slot had
a character limit its box could take, proven in a browser at four widths. The
owner lifted those limits that day: the copy comes first, and a design pass
fits the boxes to it once the texts are final. What is left is a cap, CAP
characters (2000) per text or list item and CAP_ITEMS (12) items per list: a
guard against a stray paste, not a design limit. Line breaks are kept
(clean() below) and show: _copy.html prints every text in a .t span, which
base.html sets in white-space: pre-line. tests/test_copy.py now guards
overflow only: long texts and line breaks may make a box tall, never widen or
clip a page. Defaults are the texts the templates shipped with: nothing
changes until someone edits.

Adding a slot is one line here plus `{{ c.t("the.key") }}` in the template
(see _copy.html). The tests pick it up by themselves: every slot must appear
on a page, and no page may overflow with it.

An emptied text stays empty since 20.10.2026 (the owner: "once he removes
the text, the text box and the space it occupies gets removed"): POST
/copy/{key} stores it as "", a visitor gets nothing for it (_copy.html), and
the editor keeps an empty box to click in edit mode. Zadano (reset=1) is
how a default comes back. The numbers are the exception, a Slot with
required=True (every price.<plan>.amount and .year_amount, addon.online,
addon.dvorana: "the number is the only thing that is not free text"):
emptied, its default comes back, as every text's did until that day. A
list's emptied item goes and a row's emptied cell stays empty, as before.

A ListSlot is a list of short texts the editor can add to and remove from, not
only retype — the bullets on the landing's offer cards. It is stored as ONE
site_copy row whose text is a JSON array of cleaned, non-empty strings; no row
means the default list. Its caps are a count (max_items) and a length per item
(max_chars). Printed with `{{ c.points("the.key") }}`.

The extra lines are ListSlots too, whose default is empty (20.10.2026, the
owner: "Can we also create a functionality to add text cells?"): plain
lines of text, no bullet, that the editor adds with "+ Dodaj tekst" and
removes with a ✕, under every card's bullets on the landing, in its contact
block and under its headline (the *.extra slots below; a gym card's are its
row's, GYM_CARD_SLOTS["extra"]). Printed with `{{ c.lines("the.key") }}`,
the same list as c.points prints. Until a line exists a visitor gets
nothing for one, so the page is as it was ("It doesnt change anything with
the current design right? Only if someone actually adds the text").

A RowsSlot is a table of rows of two texts the editor can add to and remove
from, not only retype — the landing's opening hours (20.10.2026, the owner's
friend: he emptied "uto" and the box stayed; "make it rows which can be
removed"). It is stored as ONE site_copy row whose text is a JSON array of
two-item arrays; no row means the default rows. A cell may be empty: that
is the point, "uto" with nothing beside it stays so, and an emptied cell is
the one text that does not get a default back (a row has none per cell). A
row whose two cells are both empty goes. Its caps are a count (max_rows)
and a length per cell (max_chars). Printed with `{{ c.rows("the.key") }}`.

A FlagSlot is a switch, not a text: whether a part of a page shows at all.
It is stored like any slot, as the text "on" or "off"; no row means the
default. Read with `copy_flag("the.key", copy_texts)` (flag_on below). In
edit mode the editor flips it with a toggle (.ed-flag, base.html); a visitor
never gets the markup of what a flag hides.

An ImageSlot is a photo, not a text, the way Shape's photo cards carry
theirs. It is stored like any slot, its text the stored file's name; no row
means no photo. Only POST /copy/{key}/slika writes it: the upload is turned
upright, shrunk to a 1600px JPEG and kept where programme media is kept
(storage.py: R2 on prod), and reset=1 on POST /copy/{key} removes file and
row. Read with `copy_image("the.key", copy_texts)` (image_name below). The
photo is public, as the landing is: GET /slika/{name} serves the names an
ImageSlot or an announcement holds and nothing else. In edit mode the editor
picks a file with "Dodaj sliku" / "Promijeni sliku" and removes it with
"Ukloni sliku" (.ed-img, base.html).

The landing's announcements (#aktualno, in the hero) are what both types are
for, and since 18.10.2026 they are rows, not slots: the gym owner adds,
hides and deletes them himself, up to eight (models.Announcement, db.py;
until then two fixed sets of slots, event1.* / event2.*). The editor edits
them as it edits slots, through virtual keys, aktualno.<id>.<field>, on the
same routes (POST /copy/{key} and /copy/{key}/slika, app.py):
ANNOUNCEMENT_SLOTS below says how each field is edited (a text is a Slot
whose default is a new card's placeholder, the switch a FlagSlot, the photo
an ImageSlot) and ANNOUNCEMENT_COLUMNS where a row keeps a text. No entry of
SLOTS is a flag or a photo since then (but for the tiers' three add-on
switches, from 20.10.2026 until their line went on 21.10.2026); the types
stay for the announcements, and for any slot that is one.

The gym's cards (#dvorana, under the online tiers) went the same way on
20.10.2026: Dvorana and Individualno were two fixed sets of slots
(offer.dvorana.* / offer.individualno.*), and the gym owner adds his own
offers beside them now, hides and deletes them, up to eight
(models.GymCard, db.py). The editor names their fields with virtual keys,
dvorana.<id>.<field>, on POST /copy/{key}: GYM_CARD_SLOTS below says how
each is edited (a text a Slot, the bullets and the extra lines a ListSlot
each, the switch a FlagSlot; no photo) and GYM_CARD_COLUMNS where a row
keeps a text.

The upitnik's questions (/upitnik) went the same way on 26.10.2026: the
gym owner's fifteen were fixed in code, only their words slots
(upitnik.q<n>.*), and he adds, removes, hides, reorders and classifies
them now (models.UpitnikQuestion, db.py; the owner: "so that Amir can
also add or remove questions from the questionnaire"). The editor names
their texts with virtual keys, upitnik.<id>.<field>, on POST /copy/{key}:
UPITNIK_QUESTION_SLOTS below (a text a Slot, the options a ListSlot) and
UPITNIK_QUESTION_COLUMNS. What a question is and does (its part, kind,
scoring, role, switch, and since 27.10.2026 the earlier question and the
answer it is asked after) is no text: POST /upitnik/pitanje/{id}. The words
around the questions stay slots (upitnik.*: the title, the parts'
headings, yes / no, the consent, the buttons, the pain sentence).

The guide through the training (29.10.2026, the owner: "a guide through
the training" that a client reads before the questionnaire, "editable text
which Amir can change as he likes") is slots too, vodic.*: the gym owner's
text in eleven sections (VODIC_SECTIONS below), each the same four slots,
a heading, its lines, a list and the lines under the list, any of them
empty if he likes; then the guide's title and its button. _vodic.html
prints it, on /upitnik's first screen and on /vodic.

The karton's texts (25.11.2026, the owner: "In the moji karton tab, lets
allow the admin to change all of the text, like in other tabs as well")
are slots too, karton.<area>.<name>: every static text karton.html
prints, its headings, leads, hints, empty lines, kickers, chips, form
labels, buttons, links, <summary> texts, table headers, the exercise
block's words and the confirm dialogs' texts, the member's own karton, a
staff member's own and the trainer's view of a client each with its own
variant where they differ (karton.staff.*). Their defaults are the texts
as the page printed them, so nothing changes until someone edits; a
control's words are required (its default comes back when emptied), a
lead, a hint, a kicker, a chip or an empty line is not (emptied, a reader
gets nothing for it). A text in an attribute (a confirm's, a placeholder)
prints with copy_text, and the editor reaches it, and every text only a
member or the trainer's view shows, in the panel "Svi tekstovi kartona"
at the bottom of his own karton in edit mode (KARTON_AREAS, KARTON_PANEL).
What stays code there: a sentence built around a value (the head line,
"Razina 2 od 3 — …", "napor 7/10", "3 vježbe", "6 od 8 vježbi · 38 min",
"Karton — <ime>", a confirm that names a value, the photo field's label
and since 25.11.2026 the document fields' with their size in MB, the
exercise history's "Zadnji put: …" and "Procjena maksimuma: …", the line
the script writes for an exercise gone from the library), the tables'
cells, LEVELS, FEELING_LABELS and the months
(the app's words everywhere), the upitnik's own questions and answers
(rows and slots of their own), the routes' flashes, every aria-label and
alt, the page's <title>, the crumbs and the nav. Since 26.11.2026 (build 3:
the gym training) the exercise block's words and the osvrt form's left the
registry with the plain form they printed in (karton.log.*, five of
karton.osvrt.*, karton.diary.fill, karton.outside.save,
karton.staff.no_osvrt), and a termin's row and the upcoming termini say the
training's state and its way in (karton.diary.gym_*, karton.termini.gym_*).

The gym training's page (karton_trening.html and its osvrt's,
karton_trening_osvrt.html; 26.11.2026, build 3) prints slots of its own,
gym.<area>.<name> (the landing's gym.kicker and gym.h2 are the landing's),
and the player's where the same words do the same job (the set table's
headers, the rating, the rest bar, "Kako se izvodi", "Završi trening", the
finish screen's osvrt fields).

Every other member-facing text since 25.11.2026 (the owner to Amir:
"svugdje ikad uvest pravilo da može uređivat"; to Fable: "If there is a
place where he is not allowed to change text, lets allow it"): every
static text of every page a member or a guest reaches is a slot,
<page>.<area>.<name>, its default the text the page printed, so nothing
changes until someone edits. The raspored (raspored.*: the week, the
phone's day and sheet, the month, "Tvoj sljedeći termin", the dialogs, the
gate, the trainer's variants), the online list, a programme and a day
(treninzi.*, program.*, dan.*), the player, its finish screen and its
leave dialog (player.*, kraj.*, leave.*), the profile (profil.*), the
login pages and the login window (auth.*: where the page and the window
say the same words, one slot prints in both), base.html's own pieces, the
error page and the Mjesečno / Godišnje switch (app.*, period.*), and what
was still a literal on the landing (landing.*), /moja-clanarina
(clanarina.*) and /prehrana (prehrana.*). Required as the karton's: a
control's words and a caption before a value ("Odmor između serija:");
not a lead, a hint, a kicker, a chip, a state's word, an empty line or a
placeholder, whose element a reader then does not get (_copy.html's opt,
the pages' copy_on). A text in an attribute or a script prints with
copy_text. Where the same words do the same job in two places (a page and
its window, the online pages' exercise words), one slot prints in both.
TEXT_PAGES below groups every plain slot by page and area for /tekstovi
(Admin ▾ → Tekstovi), where the editor reaches the texts only a member or
a guest ever sees. What stays code: a sentence built around a value (a
count, a date, a name, a number, a plural that follows a count: "odrađen
2×", "6 od 8 vježbi", "Krug 2", "za 3 dana"; its fixed words are a slot
only when they read as a phrase of their own: "Preporučeno:", "Članarina
vrijedi do"), the tables' cells and whatever a row or a model prints
(PLAN_LABELS, SECTIONS, LEVELS, GOALS, FEELING_LABELS, the weekdays, the
months, "danas" / "sutra" / "jučer"), the routes' flashes and refusals,
the emails, every aria-label, alt, title attribute and <title>, the
crumbs, the nav (its room is measured), the editor's own controls, the
strip over every page while staff act as a member (26.11.2026, "Gledaš
kao: …", "Izađi": staff's own chrome), the studio's address, phone and
email (each the text of the link it opens) and the dev server's own lines.
Since 26.11.2026 also the phone reminder's three texts (app.phone.*, the
install banner's card for a member with no phone number).
tests/test_copy_rule.py holds the rule for the pages to come: a literal
text on such a page fails it.

The price slots (18.10.2026) are plain Slots with one job: every price the
site shows, whether or not Stripe is configured (app.py, reference_prices
and _offer_prices). No Stripe Price overrides them (the owner's call, the
same day: his friend's numbers are the truth); Stripe's Prices are to be
aligned to them in one place when card payments return, and until then only
the tier picker inside the checkout forms (_tiers.html) and a subscriber's
tier switch show a Stripe amount, the one the card is charged. Per plan an
amount and a unit (price.<plan>.amount / .unit), and for the gym's five
plans a yearly amount and unit too (price.<plan>.year_amount / .year_unit,
21.10.2026: the yearly price of the plan's card on /moja-clanarina and of
the landing's gym card the plan prices). No note under a price since that
day: a /moja-clanarina card is one text (cjenik.<plan>.text, below). And
the MojiMakrosi add-on's amount beside online and beside the dvorana
(addon.online / addon.dvorana: the prehrana plan's hint is the one place
they print since 21.10.2026), so the gym owner retypes a price the way he
retypes any text. The amount is text, printed as typed with " €" after it
when it holds a number ("60–80", "od 30"; not "na upit"). Their defaults
are REFERENCE_PRICES, YEARLY_PRICE and MOJIMAKROSI_ADDON below, the shop's
numbers. Most of them print on two pages, the landing and /moja-clanarina,
the only slots that do: one number, one slot, so an edit shows wherever
that number does.

Every price has its bazna cijena since 23.11.2026 (Croatia's Pravilnik o
isticanju bazne cijene proizvoda, NN 132/2026, in force since 17.11.2026:
beside each retail price the base price, for a service the one applied on
10.9.2026): a slot of its own beside each price slot (BASE_OF: price key ->
base key, price.<plan>.base / .year_base, offer.online*.base / .year_base,
addon.*.base), a number, so required, and the words before it,
price.base_label ("Bazna cijena na 10.9.2026.", the owner's words of 24.11.2026:
the law's day named). It prints under its price, "Bazna
cijena: 50 €", wherever the price holds a number and, for a visitor, the
base does too. The first number typed into a price whose base holds none
becomes its base as well (app.py, copy_save); Zadano never touches a base.
A gym card's own prices have theirs in its row (GYM_CARD_BASE_OF).
"""
import json
import re
from dataclasses import dataclass

from .models import ONLINE_TIER_SLOTS, ONLINE_TIERS, PLAN_LABELS

CAP = 2000       # characters per text or list item, counted after clean()
CAP_ITEMS = 12   # items per list


@dataclass(frozen=True)
class Slot:
    default: str
    max: int        # characters, counted after clean(); CAP for every slot
    label: str      # what the editor sees while editing
    # a number (price.<plan>.amount, addon.*): emptied, its default comes
    # back; any other text stays empty when emptied (20.10.2026)
    required: bool = False


@dataclass(frozen=True)
class ListSlot:
    default: tuple[str, ...]
    max_items: int  # how many items the list may hold
    max_chars: int  # characters per item, counted as for Slot.max
    label: str      # the editor shows it with the item's number ("…: stavka 2")


@dataclass(frozen=True)
class RowsSlot:
    default: tuple[tuple[str, str], ...]
    max_rows: int   # how many rows the table may hold
    max_chars: int  # characters per cell, counted as for Slot.max
    label: str      # the editor shows it with the row's number and the cell's word ("…, red 2: sati")
    cell_labels: tuple[str, str]   # the two cells' words, in the editor's bar


# a new row ("+ Dodaj red", POST /copy/{key} with add=1): these placeholders
# to retype, the hours table's words (the one RowsSlot)
ROW_BLANK = ("dan", "sati")


@dataclass(frozen=True)
class FlagSlot:
    default: bool   # True: shown until someone switches it off
    label: str      # what the editor's toggle stands for ("Najava 1: prikazano")


@dataclass(frozen=True)
class ImageSlot:
    label: str      # what the editor's bar names while a photo goes up ("Najava 1: slika")


# the online tiers' bullets: tier 1's own defaults, and placeholders for 2 and 3
ONLINE_POINTS = ("Program po tvojoj razini", "Video upute za svaku vježbu",
                 "Mjesečni Zoom poziv ili susret s trenerom")

# Reference prices from the owner's Shopify shop (read 6.9.2026). Units are
# the shop's own: most of the business is per trening / per paket, only
# Online is a monthly plan. (amount text, unit). Since 18.10.2026 they are
# the defaults of the price slots (price.<plan>.*, in SLOTS below), which
# the gym owner edits in place: the pages print the slots and nothing else,
# a Stripe Price neither (app.py, reference_prices), so this table is what
# they say until someone edits. The shop's notes under two of them ("8, 12
# ili 16 treninga", "paketi od 5 i 10 tretmana") were price.<plan>.note
# slots until 21.10.2026: lines of those plans' texts since (PLAN_TEXTS).
REFERENCE_PRICES = {
    "grupni": ("60–80", "/ paket"),
    "individualni": ("35", "/ trening"),
    "poluindividualni": ("25", "/ trening"),
    "rehabilitacija": ("od 30", "/ tretman"),
    "online": ("50", "/ mjesečno"),
    "prehrana": ("od 3", "/ mjesečno"),
}

# A gym plan's yearly price until the gym owner types one (amount text,
# unit): the defaults of the price.<plan>.year_amount / .year_unit slots of
# every plan but online (21.10.2026), whose three QMove tiers have their
# landing cards' yearly prices (offer.online*.year_price / .year_unit).
YEARLY_PRICE = ("na upit", "")

# /moja-clanarina's "Dodaj plan" cards, one text each (21.10.2026, the
# owner: "every tab is one big text cell except the number"): the
# cjenik.<plan>.text slot of a gym plan, cjenik.online.<tier>.text of each
# QMove tier (in SLOTS below). Until that day a card was a lead (the
# cjenik.<plan> slot), a note under its price (price.<plan>.note) and two
# hints, each its own box: "Za upis se javi treneru u dvorani." where the
# plan is not sold by card (cjenik.note) and the line under its card button
# (clanarina.card_hint). Their default texts, a line each, are the new
# slot's: a plan's lines here (the lead, then the note where it had one),
# then the two hints (PLAN_TEXT_END), so a card says what it said. Each
# tier starts with the online plan's. Migration 6e2b9d41c7a3 carries what
# was edited into the new slots.
PLAN_TEXTS = {
    "grupni": ("Satni termini u malim grupama do 8 polaznika — rezerviraš u rasporedu.", "8, 12 ili 16 treninga"),
    "individualni": ("Rad 1:1 s trenerom, termini po dogovoru.",),
    "poluindividualni": ("Trening u dvoje ili troje — pola puta između grupe i 1:1.",),
    "rehabilitacija": ("Programi povratka nakon ozljede, 1:1 stručno vođeni.", "paketi od 5 i 10 tretmana"),
    "online": ("Programi po tvojoj razini, s video uputama — gdje god jesi.",),
    "prehrana": ("Vođenje prehrane uz aplikaciju MojiMakrosi i zdrave recepte.",),
}
PLAN_TEXT_END = ("Za upis se javi treneru u dvorani.", "Mjesečno, otkazivo bilo kad. Ili gotovinom u dvorani.")

# MojiMakrosi (the prehrana app) as a monthly add-on, as the owner set it on
# 5.10.2026: cheaper beside a plan in the dvorana, dearer for online-only
# clients. The defaults of the addon.* slots (below), which the prehrana
# plan's hint on /moja-clanarina prints ("3 € uz dvoranu, 5 € uz online",
# _plan_price.html): one slot per number. No landing card carries an add-on
# line (the gym's since 20.10.2026, the QMove tiers' since 21.10.2026).
MOJIMAKROSI_ADDON = {"dvorana": "3", "online": "5"}

# The online-trening upitnik (/upitnik, 26.10.2026): the gym owner's final
# version. Its four parts' headings are slots (upitnik.part<n>.h, in SLOTS
# below), as are its title, intro, yes / no, the consent, the buttons and
# the pain sentence. Its questions are rows since 26.10.2026
# (models.UpitnikQuestion; UPITNIK_DEFAULT_QUESTIONS and the rest below).
UPITNIK_PARTS = ("Dio 1: Tvoj cilj i raspored", "Dio 2: Tvoje iskustvo i navike (ocijeni od 1 do 10)",
                 "Dio 3: Dodatno o tebi", "Dio 4: Zdravlje i sigurnost")


# The guide through the training (29.10.2026, the owner: "a guide through
# the training", shown "without the emojis, designed with the same qmt
# design skill … for now put it before the questionnaire. This should
# again be editable text which Amir can change as he likes"): the gym
# owner's (Amir Šoša's) introduction, /upitnik's first screen and /vodic
# (_vodic.html prints it in both places; the first sign-up and the first
# payment are to lead to it later). Eleven sections, each the same four
# slots (VODIC_PARTS), so the editor finds one shape everywhere:
# vodic.<n>.h, the heading; vodic.<n>.text, lines under it; vodic.<n>.points,
# a list (a ListSlot, up to 12: the offer cards' bullets); vodic.<n>.after,
# lines under the list. Any of them may be empty, and an empty one prints
# nothing for a reader (no heading, no list). Then the guide's title and
# its button (vodic.title, vodic.cta, in SLOTS below). His emoji are gone,
# his bullet marks ("✅ 🔹 🔴") with them: the list's own dots replace them.
# His consent line ("Pristajem …") is not here: the questionnaire asks it
# at its end (upitnik.consent).
def _section(h: str = "", text: str = "", points: tuple[str, ...] = (), after: str = "") -> dict:
    """One section of the guide as it starts: its four slots' defaults."""
    return {"h": h, "text": text, "points": points, "after": after}


VODIC_SECTIONS = (
    _section(text="Trening nije samo niz vježbi. To je proces razumijevanja vlastitog tijela, svojih navika i "
                  "ciljeva.\n"
                  "Ova aplikacija osmišljena je kako bi ti pružila jasnoću, strukturu i podršku, bez zbunjujućih "
                  "mitova, bez pretjerivanja i bez ekstremnih pristupa.\n"
                  "Sve što vidiš ovdje (treninzi, prehrana, izazovi, savjeti i edukacija) temelji se na godinama "
                  "iskustva u radu s ljudima koji žele stvarnu, dugoročnu promjenu."),
    _section("Tko sam ja?",
             "Moje ime je Amir Šoša.\n"
             "Po struci sam kineziolog, kineziterapeut i fitness trener.\n"
             "U trenerskom poslu sam preko 20 godina, a u fitnessu i rehabilitaciji 15 godina. Radio sam s "
             "rekreativcima, sportašima i osobama s posebnim potrebama pokreta.\n"
             "Specijalizirao sam se za:",
             ("Funkcionalni pokret", "Zdravlje kralježnice", "Individualizirani trening",
              "Praktična rješenja za svakodnevni život, uključujući pomoć kod bolova u leđima")),
    _section("Zašto je ova aplikacija drugačija?",
             "Ovdje nećeš pronaći „instant” rješenja niti prazna obećanja.\n"
             "Pronaći ćeš smislene treninge, konkretne upute, realan pristup i podršku na svakom koraku.\n"
             "Ovo je tvoj vodič za:",
             ("Kretanje bez boli", "Jače, funkcionalnije tijelo", "Dosljednost u vježbanju",
              "Trening koji se uklapa u tvoj život, a ne obrnuto")),
    _section("Spreman/spremna za početak?",
             "Ako si tu, znači da želiš više od samog „vježbanja”. Želiš razumjeti svoje tijelo i naučiti "
             "trenirati pametno, ne samo naporno. To je prvi i najvažniji korak.\n"
             "Rezultati dolaze kad je sustav dobar, a ovaj je sustav stvoren upravo za to."),
    _section("Prije nego što počneš vježbati",
             "Tvoje zdravlje i sigurnost su nam na prvom mjestu. Prije početka preporučujemo sportsko-medicinski "
             "pregled kako bi bio/bila sigurna da možeš trenirati bez ograničenja. Nije uvjet za korištenje "
             "aplikacije, ali je preporuka za tvoje dobro.\n"
             "Crvene zastave koje ne smiješ ignorirati. Odmah prekini trening ako osjetiš:",
             ("Bol u zglobovima tijekom vježbanja", "Oštru bol u mišiću",
              "Bol ili pritisak u prsima, ili nedostatak zraka",
              "Hladan znoj, vrtoglavicu, mučninu ili zujanje u ušima"),
             "Ako se bilo što od ovoga pojavi, nemoj ignorirati i obrati se liječniku ili stručnjaku. Ova "
             "aplikacija ne zamjenjuje stručnu procjenu uživo, već ti pruža najbolje moguće smjernice."),
    _section("Razine treninga i kako ih koristiti",
             "Ovisno o rezultatima upitnika, bit ćeš usmjeren/a u jedan od tri programa:",
             ("Početni: za one koji tek počinju ili se vraćaju nakon duže pauze",
              "Srednji: za osobe s umjerenom razinom kondicije i iskustva",
              "Napredni: za one koji već redovito treniraju i žele više izazova")),
    _section("Okvirna preporuka učestalosti",
             points=("Početni: 2-3 puta tjedno", "Srednji: 3-4 puta tjedno", "Napredni: 4-5 puta tjedno"),
             after="Ovo su preporuke. Program se prilagođava tvom rasporedu, pa ako imaš manje vremena, svoje mjesto "
                   "imaš i u programu QMove 2x60."),
    _section("U svakom treningu pronaći ćeš 2 videa",
             points=("Uvodni video: objašnjava kako se trening provodi, na što paziti i koje su sigurnosne "
                     "smjernice.",
                     "Trening video: prikazuje cijeli trening sa smanjenim brojem ponavljanja, uz detaljno "
                     "objašnjenje svake vježbe."),
             after="Prije svakog treninga uvijek prvo pogledaj uvodni video. Tako ćeš znati što te čeka i izbjeći "
                   "nepotrebne greške."),
    _section("Važna smjernica",
             "Ako nisi siguran/a gdje pripadaš ili te aplikacija smjesti između razina, uvijek je bolje krenuti s "
             "prethodnom razinom i napraviti kvalitetnu bazu.\n"
             "Cilj nije brzina, već dosljednost i kontinuitet.\n"
             "Polagani, pametni napredak donosi dugoročne rezultate."),
    _section("Preporučeni vodiči",
             "Prije prvog treninga pogledaj dva kratka vodiča:",
             ("ABC of Fitness: osnove treninga (oko 10-15 minuta)", "ABC of Nutrition: osnove prehrane"),
             "Nisu obavezni, ali će ti uštedjeti puno vremena i zbunjenosti."),
    _section("Ispuni anketni upitnik",
             "Upitnik će nam pomoći da te smjestimo u najprikladniji program: početni, srednji ili napredni.\n"
             "Tvoji odgovori ostaju povjerljivi, a rezultat automatski otvara odgovarajuće treninge.\n"
             "Kad završiš upitnik, aplikacija će te usmjeriti dalje."),
)
# a section's four slots, vodic.<n>.<part>, and each one's word in the
# editor's bar after the section's number ("Vodič 5: naslov"; a list's
# item gets its number after it, "Vodič 5: stavka 2")
VODIC_PARTS = {"h": "naslov", "text": "tekst", "points": "stavka", "after": "tekst ispod popisa"}


SLOTS: dict[str, Slot | ListSlot | RowsSlot | FlagSlot | ImageSlot] = {
    # ---- landing: hero ----
    "hero.kicker": Slot("Zagreb · Dubrava", CAP, "Mala oznaka iznad naslova"),
    "hero.h1a": Slot("Kvaliteta pokreta", CAP, "Naslov, bijeli red"),
    "hero.h1b": Slot("prije svega", CAP, "Naslov, crveni red"),
    # lines under the headline, none until the editor adds one (20.10.2026)
    "hero.extra": ListSlot((), CAP_ITEMS, CAP, "Naslovnica: dodatni tekst"),
    # ---- landing: the photo card ----
    "stage.title": Slot("Dvorana u Dubravi", CAP, "Naslov na fotografiji"),
    "stage.text": Slot("Jedan prostor za sve — grupni treninzi, individualni rad i rehabilitacija, "
                       "s trenerom koji te poznaje.", CAP, "Tekst na fotografiji (nije na mobitelu)"),
    "stage.chip1": Slot("do 8 polaznika", CAP, "Oznaka na fotografiji, lijeva"),
    "stage.chip2": Slot("07–20 h", CAP, "Oznaka na fotografiji, desna"),
    # ---- landing: the offer ----
    "offer.kicker": Slot("Ponuda", CAP, "Mala oznaka iznad ponude"),
    "offer.h2": Slot("Odaberi kako treniraš", CAP, "Naslov ponude"),
    # three tiers of the online plan. Tier 1's monthly price is the online
    # plan's own (the price.online.* slots); every other price is text until
    # a plan exists for it. The "Mjesečno / Godišnje" switch under the
    # cards shows one price per card. Each card is a tier of the online
    # plan (models.ONLINE_TIER_SLOTS, 20.10.2026) and its title is the
    # tier's name everywhere in the app: /clanarine's selects and flash,
    # the Paket fact on /moja-clanarina (online_tier_names below).
    # No MojiMakrosi line on the tiers since 21.10.2026 (the owner: "lets
    # leave out the moji makrosi out of here completely"): their add-on
    # words and switches (offer.online*.addon / .addon_unit / .addon_on,
    # 20.10.2026) left the registry, with no migration: a site_copy row a
    # removed key left behind is never read. Their amount, addon.online
    # (below), prints in the prehrana plan's hint alone now.
    # .extra: the tier's lines under its bullets, none until the editor adds
    # one (20.10.2026).
    "offer.online.title": Slot("QMove START", CAP, "Online 1: naziv"),
    "offer.online.lead": Slot("Treniraj gdje god jesi.", CAP, "Online 1: podnaslov"),
    "offer.online.points": ListSlot(ONLINE_POINTS, CAP_ITEMS, CAP, "Online 1: stavka"),
    "offer.online.extra": ListSlot((), CAP_ITEMS, CAP, "Online 1: dodatni tekst"),
    "offer.online.year_price": Slot("na upit", CAP, "Online 1: godišnja cijena"),
    "offer.online.year_unit": Slot("", CAP, "Online 1: uz godišnju cijenu"),
    "offer.online2.title": Slot("QMove PRO", CAP, "Online 2: naziv"),
    "offer.online2.lead": Slot("Treniraj gdje god jesi.", CAP, "Online 2: podnaslov"),
    "offer.online2.points": ListSlot(ONLINE_POINTS, CAP_ITEMS, CAP, "Online 2: stavka"),
    "offer.online2.extra": ListSlot((), CAP_ITEMS, CAP, "Online 2: dodatni tekst"),
    "offer.online2.price": Slot("na upit", CAP, "Online 2: mjesečna cijena"),
    "offer.online2.unit": Slot("", CAP, "Online 2: uz mjesečnu cijenu"),
    "offer.online2.year_price": Slot("na upit", CAP, "Online 2: godišnja cijena"),
    "offer.online2.year_unit": Slot("", CAP, "Online 2: uz godišnju cijenu"),
    "offer.online3.title": Slot("QMove ELITE", CAP, "Online 3: naziv"),
    "offer.online3.lead": Slot("Treniraj gdje god jesi.", CAP, "Online 3: podnaslov"),
    "offer.online3.points": ListSlot(ONLINE_POINTS, CAP_ITEMS, CAP, "Online 3: stavka"),
    "offer.online3.extra": ListSlot((), CAP_ITEMS, CAP, "Online 3: dodatni tekst"),
    "offer.online3.price": Slot("na upit", CAP, "Online 3: mjesečna cijena"),
    "offer.online3.unit": Slot("", CAP, "Online 3: uz mjesečnu cijenu"),
    "offer.online3.year_price": Slot("na upit", CAP, "Online 3: godišnja cijena"),
    "offer.online3.year_unit": Slot("", CAP, "Online 3: uz godišnju cijenu"),
    # ---- landing: the gym, a quieter section below the online tiers ----
    # Its cards are rows since 20.10.2026, not slots (GYM_CARD_* below); the
    # section's kicker and heading stay slots.
    "gym.kicker": Slot("Dvorana", CAP, "Mala oznaka iznad dvorane"),
    "gym.h2": Slot("Treninzi u dvorani", CAP, "Naslov: dvorana"),
    # ---- landing: what was still a literal until 25.11.2026 (the owner:
    # "If there is a place where he is not allowed to change text, lets
    # allow it"): the featured card's chip, the price's place while a guest
    # sees no prices, the buttons that follow the visitor (a member's
    # "Odaberi plan →", a guest's "Registriraj se →" while registration is
    # open, else "Javi nam se →", a gym card without plans' too; the owner
    # of the plan gets its door, app.door.* below), and the gallery's
    # caption. Not slots: the studio's address, phone and email (each the
    # text of the link it opens: the map, tel:, mailto:) ----
    "landing.offer.featured": Slot("Najpopularnije", CAP, "Početna · ponuda: oznaka istaknute kartice"),
    # in a price's place (PUBLIC_PRICES=off), which keeps the cards' feet level: required
    "landing.offer.no_prices": Slot("Cijene nakon prijave", CAP, "Početna · ponuda: umjesto cijene, dok ih gost ne vidi",
                                    required=True),
    "landing.cta.choose": Slot("Odaberi plan →", CAP, "Početna · ponuda: gumb za člana", required=True),
    "landing.cta.signup": Slot("Registriraj se →", CAP, "Početna · ponuda: gumb za gosta (otvorena registracija)",
                               required=True),
    "landing.cta.contact": Slot("Javi nam se →", CAP, "Početna · ponuda: gumb Javi nam se", required=True),
    "landing.gallery.kicker": Slot("Galerija", CAP, "Početna · galerija: mala oznaka"),
    "landing.gallery.title": Slot("Iz dvorane", CAP, "Početna · galerija: naslov", required=True),
    # ---- prices: every price the site shows (no Stripe Price overrides them) ----
    # Per plan its amount and unit, the defaults REFERENCE_PRICES above: the
    # landing prints them on a card (Individualno's muted line two more
    # plans'), /moja-clanarina on the plan's card, with or without a Stripe
    # Price for the plan (app.py). Beside them, for every plan but online,
    # its yearly amount and unit (21.10.2026; YEARLY_PRICE: "na upit"): its
    # "Dodaj plan" card's yearly price on /moja-clanarina, and on the
    # landing the yearly price of the gym card the plan prices (its first
    # plan: Dvorana's grupni, Individualno's individualni), one number, one
    # slot. The amounts are required (a number: emptied, its default comes
    # back); the units are free text, which an editor may empty. No note
    # under a price since 21.10.2026 (a card's one text, cjenik.<plan>.text).
    **{f"price.{plan}.{part}": Slot(text, CAP, f"Cijena · {plan}: {label}", required=part in ("amount", "year_amount"))
       for plan, row in REFERENCE_PRICES.items()
       for part, label, text in zip(("amount", "unit", "year_amount", "year_unit"),
                                    ("iznos", "jedinica", "godišnji iznos", "godišnja jedinica"),
                                    row + (YEARLY_PRICE if plan != "online" else ()))},
    # the words before a plan's price in a gym card's line of its other
    # plans (Individualno's "u dvoje ili troje 25 € / trening ·
    # rehabilitacija od 30 € / tretman", landing.html, plan_note), free
    # text the gym owner retypes there since 20.10.2026; the number stays
    # the plan's amount slot. Only these two: they are the plans a card has
    # after its first (GYM_CARD_EXAMPLES), and nothing edits a card's plans.
    "price.poluindividualni.word": Slot("u dvoje ili troje", CAP, "Cijena · poluindividualni: tekst ispred iznosa"),
    "price.rehabilitacija.word": Slot("rehabilitacija", CAP, "Cijena · rehabilitacija: tekst ispred iznosa"),
    # the MojiMakrosi add-on's amount in €, beside the dvorana and beside
    # online: printed only in the prehrana plan's hint on /moja-clanarina
    # ("3 € uz dvoranu, 5 € uz online", _plan_price.html), on no landing
    # card since 21.10.2026 (the gym's since 20.10.2026); numbers, so required
    "addon.online": Slot(MOJIMAKROSI_ADDON["online"], CAP, "MojiMakrosi dodatak uz online (€)", required=True),
    "addon.dvorana": Slot(MOJIMAKROSI_ADDON["dvorana"], CAP, "MojiMakrosi dodatak uz dvoranu (€)", required=True),
    # ---- the bazna cijena beside every price (23.11.2026; BASE_OF below) ----
    # The words printed before every base amount ("Bazna cijena na 10.9.2026.: 50 €",
    # the template puts the colon after them), then each price's base:
    # per plan its amount's (default the amount's own) and, but for online,
    # its yearly amount's ("na upit", as the yearly amount); each QMove
    # tier's typed prices' ("na upit", as they are); the add-on's two
    # amounts' (theirs). All numbers, so required: emptied, the default
    # comes back. Migration 8a67c43d0bb4 started every base the gym owner
    # had typed a price for at that price's text.
    "price.base_label": Slot("Bazna cijena na 10.9.2026.", CAP, "Bazna cijena na 10.9.2026.: natpis uz svaku cijenu", required=True),
    **{f"price.{plan}.{part}": Slot(text, CAP, f"Cijena · {plan}: {label}", required=True)
       for plan, row in REFERENCE_PRICES.items()
       for part, label, text in (("base", "bazni iznos", row[0]),
                                 *((("year_base", "bazni godišnji iznos", YEARLY_PRICE[0]),) if plan != "online" else ()))},
    "offer.online.year_base": Slot("na upit", CAP, "Online 1: bazna godišnja cijena", required=True),
    "offer.online2.base": Slot("na upit", CAP, "Online 2: bazna mjesečna cijena", required=True),
    "offer.online2.year_base": Slot("na upit", CAP, "Online 2: bazna godišnja cijena", required=True),
    "offer.online3.base": Slot("na upit", CAP, "Online 3: bazna mjesečna cijena", required=True),
    "offer.online3.year_base": Slot("na upit", CAP, "Online 3: bazna godišnja cijena", required=True),
    "addon.online.base": Slot(MOJIMAKROSI_ADDON["online"], CAP, "MojiMakrosi dodatak uz online: bazna cijena (€)",
                              required=True),
    "addon.dvorana.base": Slot(MOJIMAKROSI_ADDON["dvorana"], CAP, "MojiMakrosi dodatak uz dvoranu: bazna cijena (€)",
                               required=True),
    # ---- landing: aktualno: rows since 18.10.2026, not slots (ANNOUNCEMENT_* below) ----
    # ---- landing: info ----
    "info.hours.h": Slot("Radno vrijeme", CAP, "Naslov: radno vrijeme"),
    # the hours as rows (20.10.2026; six fixed slots info.hours.d1 … t3
    # until migration 1a7c144b582a folded them in): days and hours per row
    "info.hours.rows": RowsSlot((("pon · sri · čet · pet", "07:00 – 20:00"), ("uto", "individualni termini"),
                                 ("sub · ned", "zatvoreno")), CAP_ITEMS, CAP, "Radno vrijeme", ("dani", "sati")),
    # lines under the hours' table and under the contact rows, none until
    # the editor adds one (20.10.2026)
    "info.hours.extra": ListSlot((), CAP_ITEMS, CAP, "Radno vrijeme: dodatni tekst"),
    "info.where.h": Slot("Gdje smo", CAP, "Naslov: adresa"),
    "info.contact.h": Slot("Kontakt", CAP, "Naslov: kontakt"),
    "info.contact.extra": ListSlot((), CAP_ITEMS, CAP, "Kontakt: dodatni tekst"),
    "footer": Slot("© Quality Movement Training, Zagreb", CAP, "Podnožje"),
    # ---- cjenik (members) ----
    "cjenik.hint": Slot("Svaka usluga je zasebna članarina — plaća se mjesečno, sljedeća uplata dospijeva "
                        "mjesec dana nakon zadnje.", CAP, "Cjenik: uvodna rečenica"),
    # "Dodaj plan"'s cards, one text each (21.10.2026; PLAN_TEXTS above): a
    # gym plan's, and each QMove tier's, which start alike
    **{f"cjenik.{plan}.text": Slot("\n".join(lines + PLAN_TEXT_END), CAP, f"Članarina: tekst plana · {plan}")
       for plan, lines in PLAN_TEXTS.items() if plan != "online"},
    **{f"cjenik.online.{tier}.text": Slot("\n".join(PLAN_TEXTS["online"] + PLAN_TEXT_END), CAP,
                                          f"Članarina: tekst plana · online {n}")
       for n, tier in enumerate(ONLINE_TIERS, start=1)},
    # ---- moja članarina (18.10.2026): the rest of the page's own words ----
    # The lead, the plans' texts and the prices are the cjenik.* and price.*
    # slots above. Since 25.11.2026 the facts' captions, the chips' words,
    # the ledger's headers and the status box's fixed words are slots too
    # (below); its dates and numbers stay code.
    "clanarina.h.plans": Slot("Tvoji planovi", CAP, "Članarina: naslov · Tvoji planovi"),
    "clanarina.h.add": Slot("Dodaj plan", CAP, "Članarina: naslov · Dodaj plan"),
    # "Dodaj plan"'s two groups (21.10.2026), each with its Mjesečno /
    # Godišnje switch: the online plan's three QMove tiers, the gym's plans
    "clanarina.h.online": Slot("Online treninzi", CAP, "Članarina: naslov · Online treninzi"),
    "clanarina.h.gym": Slot("Treninzi u dvorani", CAP, "Članarina: naslov · Treninzi u dvorani"),
    "clanarina.h.bills": Slot("Računi", CAP, "Članarina: naslov · Računi"),
    # the card a member without a plan sees instead of Tvoji planovi; an
    # editor sees it too, under a caption, so its two sentences are in reach
    "clanarina.none.title": Slot("Nemaš aktivnu članarinu — bez nje rezervacija nije moguća.", CAP,
                                 "Članarina: bez plana, prva rečenica"),
    "clanarina.none.text": Slot("Za upis se javi treneru u dvorani — plaćanje gotovinom ili karticom.", CAP,
                                "Članarina: bez plana, druga rečenica"),
    "clanarina.bills.empty": Slot("Još nema zabilježenih uplata.", CAP, "Članarina: nema uplata"),
    # what was still a literal on the page until 25.11.2026, in its order:
    # the title; a plan held's card (its kicker, its chip's words, its
    # facts' captions, its status box's fixed words around its dates, a
    # subscriber's portal and tier switch, a cash member's way onto the
    # card, a lapsed plan's button and line); "Dodaj plan"'s chip and
    # button; the prehrana plan's hint's words after each add-on amount
    # (_plan_price.html; the amounts are the addon.* slots); the ledger's
    # portal and headers. The card's door is app.door.* (below), the words
    # of the plan's page, the landing's too. Not slots: a chip's "za 3
    # dana" (a count), "16 treninga mjesečno", "3 od 8 u ovom ciklusu", the
    # tier switch's buttons and its confirm's title and text (a count, an
    # amount), and "Ovo vidi član bez članarine:" (the editor's caption)
    "clanarina.h.title": Slot("Moja članarina", CAP, "Članarina: naslov stranice", required=True),
    "clanarina.plan.kicker": Slot("Paket", CAP, "Članarina · plan: mala oznaka iznad naziva"),
    "clanarina.chip.active": Slot("aktivna", CAP, "Članarina · plan: oznaka aktivna"),
    "clanarina.chip.due": Slot("dospijeva", CAP, "Članarina · plan: oznaka dospijeva (prije broja dana)"),
    "clanarina.chip.lapsed": Slot("istekla", CAP, "Članarina · plan: oznaka istekla"),
    "clanarina.chip.cancelling": Slot("otkazana · vrijedi do kraja", CAP, "Članarina · plan: oznaka otkazane pretplate"),
    "clanarina.fact.price": Slot("Cijena", CAP, "Članarina · plan: Cijena", required=True),
    "clanarina.fact.paid": Slot("Uplaćeno", CAP, "Članarina · plan: Uplaćeno", required=True),
    "clanarina.fact.next": Slot("Sljedeća uplata", CAP, "Članarina · plan: Sljedeća uplata", required=True),
    "clanarina.fact.until": Slot("Vrijedi do", CAP, "Članarina · plan: Vrijedi do", required=True),
    "clanarina.fact.paket": Slot("Paket", CAP, "Članarina · plan: Paket (broj treninga ili razina)", required=True),
    "clanarina.fact.used": Slot("Iskorišteno", CAP, "Članarina · plan: Iskorišteno", required=True),
    # the status box: each state's fixed words around its dates
    "clanarina.status.lapsed": Slot("Članarina je istekla", CAP, "Članarina · stanje: istekla, prije datuma"),
    "clanarina.status.restart": Slot("Nova uplata počinje od", CAP, "Članarina · stanje: istekla, nova uplata od"),
    "clanarina.status.restart_now": Slot("dana uplate.", CAP, "Članarina · stanje: istekla, nova uplata od dana uplate"),
    "clanarina.status.cancelling": Slot("Pretplata je otkazana i vrijedi do", CAP,
                                        "Članarina · stanje: otkazana pretplata, prije datuma"),
    "clanarina.status.renews": Slot("Pretplata se obnavlja automatski", CAP,
                                    "Članarina · stanje: pretplata karticom, prije datuma"),
    "clanarina.status.by_card": Slot("karticom.", CAP, "Članarina · stanje: pretplata karticom, iza datuma"),
    "clanarina.status.overdue": Slot("Uplata je dospjela", CAP, "Članarina · stanje: dospjela uplata, prije datuma"),
    "clanarina.status.grace": Slot("— članarina vrijedi još do", CAP, "Članarina · stanje: dospjela uplata, vrijedi još do"),
    "clanarina.status.pay_gym": Slot("Uplatu obavi u dvorani, gotovinom ili karticom.", CAP,
                                     "Članarina · stanje: dospjela uplata, gdje se plaća"),
    "clanarina.status.valid": Slot("Članarina vrijedi do", CAP, "Članarina · stanje: aktivna, prije datuma"),
    "clanarina.status.next": Slot("Sljedeću uplatu obavi do", CAP, "Članarina · stanje: aktivna, sljedeća uplata do"),
    "clanarina.status.where": Slot("— u dvorani, gotovinom ili karticom.", CAP, "Članarina · stanje: aktivna, gdje se plaća"),
    "clanarina.portal": Slot("Kartica, računi, otkazivanje", CAP, "Članarina · plan: gumb Stripe portala", required=True),
    "clanarina.switch.kicker": Slot("Promijeni paket", CAP, "Članarina · plan: mala oznaka promjene paketa"),
    "clanarina.switch.cta": Slot("Promijeni", CAP, "Članarina · promjena paketa: gumb potvrde", required=True),
    "clanarina.to_card.hint": Slot("Prebaci na karticu — obnavlja se automatski od sljedeće uplate:", CAP,
                                   "Članarina · plan: uz prelazak na karticu"),
    "clanarina.to_card.go": Slot("Prebaci na karticu", CAP, "Članarina · plan: gumb Prebaci na karticu", required=True),
    "clanarina.subscribe": Slot("Pretplati se karticom", CAP, "Članarina: gumb Pretplati se karticom", required=True),
    "clanarina.lapsed.hint": Slot("Mjesečno, otkazivo bilo kad. Ili gotovinom u dvorani.", CAP,
                                  "Članarina · plan: ispod gumba istekle članarine"),
    "clanarina.add.featured": Slot("Najpopularnije", CAP, "Članarina · dodaj plan: oznaka istaknutog plana"),
    "clanarina.addon.gym": Slot("uz dvoranu", CAP, "Članarina · prehrana: iza iznosa uz dvoranu"),
    "clanarina.addon.online": Slot("uz online", CAP, "Članarina · prehrana: iza iznosa uz online"),
    "clanarina.bills.portal": Slot("Računi i kartica u Stripe portalu", CAP, "Članarina · računi: gumb Stripe portala",
                                   required=True),
    "clanarina.bills.col_date": Slot("Datum", CAP, "Članarina · računi: stupac Datum", required=True),
    "clanarina.bills.col_plan": Slot("Plan · način", CAP, "Članarina · računi: stupac Plan · način", required=True),
    "clanarina.bills.col_amount": Slot("Iznos", CAP, "Članarina · računi: stupac Iznos", required=True),
    # The plans' names on /moja-clanarina and nowhere else: the headings of
    # its cards, a plan held and a plan to add. Their defaults are
    # PLAN_LABELS, which stay fixed everywhere else, this page's ledger
    # included: the timetable's rows, /clanarine, the emails and the alerts
    # name the app's own records, and those do not change with the copy.
    **{f"plan.{plan}.name": Slot(label, CAP, f"Članarina: naziv plana · {plan}")
       for plan, label in PLAN_LABELS.items()},
    # ---- prehrana ----
    # since 25.11.2026 every text of the page: the kicker, the two
    # paragraphs (each split at its bold words, which keep their weight:
    # the words before, the bold ones, the words after) and the button
    "prehrana.kicker": Slot("Prehrana", CAP, "Prehrana: mala oznaka iznad naslova"),
    "prehrana.h1": Slot("Prehrana ide uz trening", CAP, "Prehrana: naslov"),
    "prehrana.text_a": Slot("Za praćenje prehrane koristimo", CAP, "Prehrana · tekst: prije naziva aplikacije"),
    "prehrana.text_app": Slot("MojiMakrosi", CAP, "Prehrana · tekst: naziv aplikacije (podebljano)"),
    "prehrana.text_b": Slot("— aplikaciju u koju opišeš što si jeo svojim riječima, a ona izračuna kalorije i "
                            "makronutrijente te ih usporedi s tvojim ciljevima.", CAP,
                            "Prehrana · tekst: iza naziva aplikacije"),
    "prehrana.hint_a": Slot("Račun na MojiMakrosima je za sada", CAP, "Prehrana · račun: prije podebljane riječi"),
    "prehrana.hint_bold": Slot("odvojen", CAP, "Prehrana · račun: podebljana riječ"),
    "prehrana.hint_b": Slot("od QMT računa — registriraj se istom email adresom, da ih kasnije možemo povezati u "
                            "jedan.", CAP, "Prehrana · račun: iza podebljane riječi"),
    "prehrana.open": Slot("Otvori MojiMakrose ↗", CAP, "Prehrana: gumb Otvori MojiMakrose", required=True),
    "prehrana.note": Slot("Pristup je na poziv — javi se treneru ako se ne možeš registrirati.", CAP, "Prehrana: napomena"),
    # ---- upitnik (26.10.2026): its words around the questions (the
    # questions are rows since 26.10.2026: UPITNIK_* below) ----
    "upitnik.title": Slot("Q Move upitnik", CAP, "Upitnik: naslov"),
    "upitnik.intro": Slot("Odgovori su potrebni da bismo ti odredili razinu treninga. Traje oko 2 minute.", CAP,
                          "Upitnik: uvod"),
    **{f"upitnik.part{n}.h": Slot(text, CAP, f"Upitnik: naslov dijela {n}")
       for n, text in enumerate(UPITNIK_PARTS, start=1)},
    "upitnik.yes": Slot("Da", CAP, "Upitnik: odgovor Da"),
    "upitnik.no": Slot("Ne", CAP, "Upitnik: odgovor Ne"),
    "upitnik.consent": Slot("Pristajem na obradu podataka o zdravlju radi izrade programa treninga.", CAP,
                            "Upitnik: privola"),
    "upitnik.submit": Slot("Spremi upitnik", CAP, "Upitnik: gumb za spremanje"),
    "upitnik.back": Slot("Nazad", CAP, "Upitnik: gumb Nazad"),
    "upitnik.next": Slot("Dalje", CAP, "Upitnik: gumb Dalje"),
    # in the flash after saving and on the karton, when the pain question
    # (the row whose role is "pain") is 7 or more
    "upitnik.pain_note": Slot("Zbog čestih bolova krećeš od početne razine — javi se treneru prije prvog treninga.",
                              CAP, "Upitnik: poruka uz česte bolove"),
    # ---- the guide through the training (29.10.2026; VODIC_SECTIONS above):
    # /upitnik's first screen and /vodic. Its title, each section's four
    # slots, its button; none required (an emptied one stays empty) ----
    "vodic.title": Slot("Dobrodošao/la u vodič kroz trening", CAP, "Vodič: naslov"),
    **{f"vodic.{n}.{part}": (ListSlot(section[part], CAP_ITEMS, CAP, f"Vodič {n}: {word}") if part == "points"
                             else Slot(section[part], CAP, f"Vodič {n}: {word}"))
       for n, section in enumerate(VODIC_SECTIONS, start=1) for part, word in VODIC_PARTS.items()},
    "vodic.cta": Slot("Idemo na upitnik!", CAP, "Vodič: gumb"),
    # ---- the karton (/karton, /karton/<id>; 25.11.2026, the owner: "In the
    # moji karton tab, lets allow the admin to change all of the text, like in
    # other tabs as well"): every static text karton.html prints, in the
    # page's order, area by area (KARTON_AREAS below: the panel "Svi tekstovi
    # kartona" lists them so). A control's words are required (a heading, a
    # button, a link, a label, a <summary>, a table header, a confirm's three
    # texts): emptied, the default comes back; a lead, a hint, a kicker, a
    # chip and an empty line are not, and an emptied one prints nothing. The
    # words before a link carry the dash that leads to it ("Visina nije
    # upisana —"); the period after the link is the template's. The trainer's
    # view of a client and a staff member's own karton have their own
    # variants (karton.staff.*). Not slots: the sentences built around a
    # value (the head line, "Razina 2 od 3 — …", "napor 7/10", "3 vježbe", a
    # date, a name, a count, a confirm that names a value, the photo field's
    # label with its size in MB), the tables' cells, LEVELS, FEELING_LABELS,
    # the months, the upitnik's own questions and answers, the routes'
    # flashes, every aria-label and alt, the crumbs and the nav ----
    "karton.head.title": Slot("Moj karton", CAP, "Karton: naslov", required=True),
    "karton.head.lead": Slot("Dnevnik treninga, upitnik i termini na jednom mjestu.", CAP, "Karton: uvodna rečenica"),
    "karton.upitnik.eyebrow": Slot("Online trening — upitnik", CAP, "Karton · upitnik: mala oznaka"),
    "karton.upitnik.redo": Slot("Ispuni ponovno", CAP, "Karton · upitnik: gumb Ispuni ponovno", required=True),
    "karton.upitnik.old": Slot("Stari upitnik —", CAP, "Karton · upitnik: stari upitnik, prije poveznice"),
    "karton.upitnik.old_link": Slot("ispuni novi", CAP, "Karton · upitnik: poveznica na novi upitnik", required=True),
    "karton.upitnik.none_title": Slot("Upitnik još nije ispunjen", CAP, "Karton · upitnik: naslov dok nije ispunjen",
                                      required=True),
    "karton.upitnik.none_text": Slot("Prema odgovorima te svrstavamo u razinu — programi se otvaraju odmah.", CAP,
                                     "Karton · upitnik: tekst dok nije ispunjen"),
    "karton.upitnik.fill": Slot("Ispuni upitnik", CAP, "Karton · upitnik: gumb Ispuni upitnik", required=True),
    "karton.upitnik.no_plan": Slot("Online treninzi su dio zasebne članarine — javi se treneru za pristup.", CAP,
                                   "Karton · upitnik: bez online članarine"),
    "karton.limits.title": Slot("Ograničenja i bolovi", CAP, "Karton · ograničenja: naslov", required=True),
    "karton.limits.edit": Slot("Uredi", CAP, "Karton · ograničenja: gumb Uredi", required=True),
    "karton.limits.empty": Slot("Nema upisanih ograničenja.", CAP, "Karton · ograničenja: kad nema teksta"),
    "karton.limits.placeholder": Slot("npr. bol u koljenu pri čučnju, stara ozljeda ramena", CAP,
                                      "Karton · ograničenja: primjer u praznom polju"),
    "karton.limits.save": Slot("Spremi", CAP, "Karton · ograničenja: gumb Spremi", required=True),
    "karton.limits.cancel": Slot("Odustani", CAP, "Karton · ograničenja: gumb Odustani", required=True),
    # the documents under the limitations (25.11.2026, Amir: "U ograničenja i
    # bolovi treba dodati mogućnost da se doda slika ili pdf"): the member's
    # button beside Uredi, the list's caption, the form's name field and its
    # buttons (the file field's label says its size in MB: code), each
    # document's chip
    "karton.limits.add_doc": Slot("Dodaj dokument", CAP, "Karton · ograničenja: gumb Dodaj dokument", required=True),
    "karton.limits.docs": Slot("Dokumenti", CAP, "Karton · ograničenja: naslov popisa dokumenata", required=True),
    "karton.limits.doc_name": Slot("Naziv (neobavezno)", CAP, "Karton · ograničenja: polje Naziv dokumenta",
                                   required=True),
    "karton.limits.doc_save": Slot("Spremi", CAP, "Karton · ograničenja: gumb Spremi dokument", required=True),
    "karton.limits.doc_cancel": Slot("Odustani", CAP, "Karton · ograničenja: gumb Odustani od dokumenta",
                                     required=True),
    "karton.limits.chip_pdf": Slot("PDF", CAP, "Karton · ograničenja: oznaka PDF"),
    "karton.limits.chip_image": Slot("slika", CAP, "Karton · ograničenja: oznaka slike"),
    # "Tjelesna kompozicija" since 25.11.2026 (Amir: "Tjelesna masa tu bi
    # promijenio u tjelesna kompozicija gdje opet mogu dodati pdf ili sliku ili
    # samo upisati ručno masu"; "Tjelesna masa" until then): its entries a
    # mass, a document, or both
    "karton.weight.title": Slot("Tjelesna kompozicija", CAP, "Karton · masa: naslov", required=True),
    "karton.weight.add": Slot("Upiši", CAP, "Karton · masa: gumb Upiši", required=True),
    # the height, here since 26.11.2026 (the owner's note: "visinu maknut iz
    # profila u karton"; /profil's field until then, whose link "uredi" /
    # "upiši je na profilu" led there: karton.weight.height_edit, .no_height
    # and .no_height_link left the registry, new keys for new words, so an
    # edit of the old ones never prints in a new place): the toggle beside
    # the height, the line with none and its toggle, the form's field and
    # its two buttons
    "karton.weight.height_change": Slot("uredi", CAP, "Karton · masa: gumb uz visinu", required=True),
    "karton.weight.height_none": Slot("Visina nije upisana", CAP, "Karton · masa: bez visine"),
    "karton.weight.height_add": Slot("upiši", CAP, "Karton · masa: gumb upiši visinu", required=True),
    "karton.weight.height_field": Slot("Visina (cm)", CAP, "Karton · masa: polje Visina", required=True),
    "karton.weight.height_save": Slot("Spremi", CAP, "Karton · masa: gumb Spremi visinu", required=True),
    "karton.weight.height_cancel": Slot("Odustani", CAP, "Karton · masa: gumb Odustani od visine", required=True),
    "karton.weight.empty": Slot("Još nije upisana.", CAP, "Karton · masa: kad nema unosa"),
    "karton.weight.kg": Slot("Kilogrami", CAP, "Karton · masa: polje Kilogrami", required=True),
    "karton.weight.day": Slot("Datum", CAP, "Karton · masa: polje Datum", required=True),
    "karton.weight.hint": Slot("Upiši masu, dodaj dokument (npr. ispis analize sastava tijela) ili oboje.", CAP,
                               "Karton · masa: savjet u obrascu"),
    "karton.weight.save": Slot("Spremi", CAP, "Karton · masa: gumb Spremi", required=True),
    "karton.weight.cancel": Slot("Odustani", CAP, "Karton · masa: gumb Odustani", required=True),
    "karton.weight.more": Slot("prikaži sve", CAP, "Karton · masa: starije unose prikaži sve", required=True),
    "karton.photos.title": Slot("Napredak — fotografije", CAP, "Karton · fotografije: naslov", required=True),
    "karton.photos.add": Slot("Dodaj fotografiju", CAP, "Karton · fotografije: gumb Dodaj", required=True),
    "karton.photos.replace": Slot("Zamijeni ovomjesečnu", CAP, "Karton · fotografije: gumb Zamijeni", required=True),
    "karton.photos.month": Slot("Mjesec", CAP, "Karton · fotografije: polje Mjesec", required=True),
    "karton.photos.rule": Slot("Jedna fotografija po mjesecu: nova za isti mjesec zamjenjuje staru.", CAP,
                               "Karton · fotografije: pravilo ispod polja"),
    "karton.photos.save": Slot("Spremi", CAP, "Karton · fotografije: gumb Spremi", required=True),
    "karton.photos.cancel": Slot("Odustani", CAP, "Karton · fotografije: gumb Odustani", required=True),
    "karton.photos.empty": Slot("Još nema fotografija.", CAP, "Karton · fotografije: kad nema fotografija"),
    "karton.photos.hint": Slot("Jedna fotografija mjesečno, kad želiš — za usporedbu kroz vrijeme.", CAP,
                               "Karton · fotografije: savjet"),
    "karton.maxes.title": Slot("Procijenjeni maksimumi", CAP, "Karton · maksimumi: naslov", required=True),
    "karton.maxes.hint": Slot("Iz najbolje serije svake vježbe, Epleyevom formulom (kg × (1 + ponavljanja / 30)), "
                              "do 12 ponavljanja. Vježbe bez utega: najviše ponavljanja.", CAP,
                              "Karton · maksimumi: objašnjenje"),
    "karton.maxes.col_exercise": Slot("Vježba", CAP, "Karton · maksimumi: stupac Vježba", required=True),
    "karton.maxes.col_value": Slot("Procjena", CAP, "Karton · maksimumi: stupac Procjena", required=True),
    "karton.maxes.col_from": Slot("Iz", CAP, "Karton · maksimumi: stupac Iz", required=True),
    "karton.maxes.empty": Slot("Još nema serija — upiši vježbe u svoj trening.", CAP,
                               "Karton · maksimumi: kad nema serija"),
    # "Povijest vježbe" (25.11.2026, the owner: "We need a search bar for each
    # user. Admins can access everyone's karton and search a particular
    # exercise."): the card's heading, the picker's label and its button, the
    # fold of the older times, the two empty states ("Zadnji put: …",
    # "Procjena maksimuma: …" are built around a value: code)
    "karton.history.title": Slot("Povijest vježbe", CAP, "Karton · povijest vježbe: naslov", required=True),
    "karton.history.exercise": Slot("Vježba", CAP, "Karton · povijest vježbe: polje Vježba", required=True),
    "karton.history.show": Slot("Prikaži", CAP, "Karton · povijest vježbe: gumb Prikaži", required=True),
    "karton.history.more": Slot("prikaži sve", CAP, "Karton · povijest vježbe: starije prikaži sve", required=True),
    "karton.history.empty": Slot("Još nema upisanih vježbi.", CAP, "Karton · povijest vježbe: kad nema vježbi"),
    "karton.history.unknown": Slot("Ta vježba nije u ovom kartonu.", CAP,
                                   "Karton · povijest vježbe: vježba nije u kartonu"),
    "karton.termini.title": Slot("Nadolazeći termini", CAP, "Karton · termini: naslov", required=True),
    "karton.termini.canceled": Slot("OTKAZANO", CAP, "Karton · termini: oznaka otkazanog termina"),
    "karton.termini.empty": Slot("Nema rezervacija.", CAP, "Karton · termini: kad nema rezervacija"),
    "karton.termini.open": Slot("Otvori raspored →", CAP, "Karton · termini: poveznica na raspored", required=True),
    # a termin's gym training (26.11.2026, build 3): its way in while it is
    # open (the raspored's "Tvoj sljedeći termin" prints the same slot), and
    # once under the list when it opens, the hours between the two (code)
    "karton.termini.gym_link": Slot("Upiši trening →", CAP, "Karton · termini: poveznica Upiši trening (i na rasporedu)",
                                    required=True),
    "karton.termini.gym_before": Slot("Trening upisuješ od", CAP,
                                      "Karton · termini: kad se upisuje trening, prije broja sati"),
    "karton.termini.gym_after": Slot("h prije termina do kraja idućeg dana.", CAP,
                                     "Karton · termini: kad se upisuje trening, iza broja sati"),
    "karton.diary.title": Slot("Dnevnik treninga", CAP, "Karton · dnevnik: naslov", required=True),
    "karton.diary.lead": Slot("Svaki odrađeni termin završi ovdje — upiši trening (vježbe, serije, osvrt) ili "
                              "označi da nisi bio/la.", CAP, "Karton · dnevnik: uvodna rečenica"),
    "karton.diary.online": Slot("Online trening", CAP, "Karton · dnevnik: oznaka online treninga"),
    "karton.diary.outside": Slot("Trening izvan termina", CAP, "Karton · dnevnik: oznaka treninga izvan termina"),
    "karton.diary.edit": Slot("Uredi", CAP, "Karton · dnevnik: gumb Uredi", required=True),
    "karton.diary.delete": Slot("Obriši", CAP, "Karton · dnevnik: gumb Obriši", required=True),
    "karton.diary.absent_chip": Slot("Nisam bio/la", CAP, "Karton · dnevnik: oznaka izostanka"),
    "karton.diary.undo": Slot("Poništi", CAP, "Karton · dnevnik: gumb Poništi", required=True),
    "karton.diary.canceled": Slot("Otkazano", CAP, "Karton · dnevnik: oznaka otkazanog termina"),
    # a termin's row with no gym training yet (26.11.2026, build 3: "Ispuni
    # osvrt" went with its form), inside its window and after it, and a
    # training's way in from its row
    "karton.diary.gym_none_open": Slot("Trening još nije upisan.", CAP, "Karton · dnevnik: trening još nije upisan"),
    "karton.diary.gym_fill": Slot("Upiši trening", CAP, "Karton · dnevnik: gumb Upiši trening", required=True),
    "karton.diary.gym_none": Slot("Trening nije upisan.", CAP, "Karton · dnevnik: trening nije upisan"),
    "karton.diary.gym_open": Slot("Otvori trening", CAP, "Karton · dnevnik: gumb Otvori trening", required=True),
    "karton.diary.absent": Slot("Nisam bio/la", CAP, "Karton · dnevnik: gumb Nisam bio/la", required=True),
    "karton.diary.sets": Slot("Serije", CAP, "Karton · dnevnik: Serije", required=True),
    "karton.diary.empty": Slot("Još nema odrađenih termina —", CAP, "Karton · dnevnik: prazan dnevnik, prije poveznice"),
    "karton.diary.empty_link": Slot("rezerviraj prvi", CAP, "Karton · dnevnik: poveznica na raspored", required=True),
    "karton.outside.add": Slot("+ Dodaj trening izvan termina", CAP, "Karton · trening izvan termina: gumb Dodaj",
                               required=True),
    "karton.outside.title": Slot("Trening izvan termina", CAP, "Karton · trening izvan termina: naslov obrasca",
                                 required=True),
    "karton.outside.day": Slot("Datum", CAP, "Karton · trening izvan termina: polje Datum", required=True),
    "karton.outside.create": Slot("Dodaj trening", CAP, "Karton · trening izvan termina: gumb Dodaj trening",
                                  required=True),
    "karton.outside.cancel": Slot("Odustani", CAP, "Karton · trening izvan termina: gumb Odustani", required=True),
    "karton.osvrt.effort": Slot("Napor (1 lagano – 10 maksimalno)", CAP, "Karton · osvrt: polje Napor", required=True),
    "karton.osvrt.feeling": Slot("Osjećaj", CAP, "Karton · osvrt: polje Osjećaj", required=True),
    "karton.osvrt.note_edit": Slot("Komentar", CAP, "Karton · osvrt: polje Komentar pri uređivanju", required=True),
    "karton.osvrt.edit_save": Slot("Spremi", CAP, "Karton · osvrt: gumb Spremi pri uređivanju", required=True),
    "karton.osvrt.edit_cancel": Slot("Odustani", CAP, "Karton · osvrt: gumb Odustani pri uređivanju", required=True),
    "karton.confirm.weight_title": Slot("Obrisati unos?", CAP, "Karton · brisanje mase: naslov", required=True),
    "karton.confirm.weight_cta": Slot("Obriši unos", CAP, "Karton · brisanje mase: gumb", required=True),
    "karton.confirm.photo_title": Slot("Obrisati fotografiju?", CAP, "Karton · brisanje fotografije: naslov",
                                       required=True),
    "karton.confirm.photo_cta": Slot("Obriši fotografiju", CAP, "Karton · brisanje fotografije: gumb", required=True),
    "karton.confirm.doc_title": Slot("Obrisati dokument?", CAP, "Karton · brisanje dokumenta: naslov", required=True),
    "karton.confirm.doc_cta": Slot("Obriši dokument", CAP, "Karton · brisanje dokumenta: gumb", required=True),
    "karton.confirm.osvrt_title": Slot("Obrisati osvrt?", CAP, "Karton · brisanje osvrta: naslov", required=True),
    "karton.confirm.osvrt_text": Slot("Napor, osjećaj, komentar i vježbe bit će trajno obrisani. Termin ostaje u "
                                      "dnevniku i osvrt možeš ispuniti ponovno.", CAP,
                                      "Karton · brisanje osvrta: tekst", required=True),
    "karton.confirm.osvrt_cta": Slot("Obriši osvrt", CAP, "Karton · brisanje osvrta: gumb", required=True),
    "karton.confirm.outside_title": Slot("Obrisati trening?", CAP, "Karton · brisanje treninga: naslov", required=True),
    "karton.confirm.outside_text": Slot("Trening izvan termina bit će trajno obrisan: datum, napor, osjećaj, "
                                        "komentar i vježbe.", CAP, "Karton · brisanje treninga: tekst", required=True),
    "karton.confirm.outside_cta": Slot("Obriši trening", CAP, "Karton · brisanje treninga: gumb", required=True),
    "karton.confirm.absent_title": Slot("Nisi bio/la na terminu?", CAP, "Karton · izostanak: naslov", required=True),
    "karton.confirm.absent_text": Slot("Termin se miče iz dnevnika kao odrađen trening i ostaje zabilježen kao "
                                       "izostanak. Uvijek ga možeš vratiti klikom na Poništi.", CAP,
                                       "Karton · izostanak: tekst", required=True),
    "karton.confirm.absent_cta": Slot("Da, nisam bio/la", CAP, "Karton · izostanak: gumb", required=True),
    # the variants: a staff member's own karton (24.11.2026) and the
    # trainer's view of a client's (/karton/<id>), where they differ from a
    # member's own
    "karton.staff.own_lead": Slot("Tvoj vlastiti karton: dnevnik treninga, maksimumi, masa i fotografije.", CAP,
                                  "Karton · osoblje: uvodna rečenica"),
    "karton.staff.review": Slot("Zahtijeva pregled", CAP, "Karton · pogled trenera: oznaka Zahtijeva pregled"),
    "karton.staff.old": Slot("Stari upitnik.", CAP, "Karton · pogled trenera: stari upitnik"),
    "karton.staff.answers": Slot("Odgovori", CAP, "Karton · pogled trenera: Odgovori", required=True),
    "karton.staff.upitnik_none": Slot("Upitnik još nije ispunjen.", CAP,
                                      "Karton · pogled trenera: upitnik nije ispunjen"),
    "karton.staff.limits_flag": Slot("Ograničenja", CAP, "Karton · pogled trenera: oznaka Ograničenja"),
    "karton.staff.weight_history": Slot("Povijest", CAP, "Karton · pogled trenera: Povijest mase", required=True),
    "karton.staff.maxes_empty": Slot("Još nema serija.", CAP, "Karton · pogled trenera: kad nema serija"),
    "karton.staff.diary_lead": Slot("Odrađeni termini i osvrti.", CAP, "Karton · pogled trenera: uvodna rečenica dnevnika"),
    "karton.staff.own_diary_lead": Slot("Tvoji online treninzi i treninzi koje upišeš sam/a.", CAP,
                                        "Karton · osoblje: uvodna rečenica dnevnika"),
    "karton.staff.diary_empty": Slot("Još nema odrađenih termina.", CAP, "Karton · pogled trenera: prazan dnevnik"),
    "karton.staff.own_diary_empty": Slot("Još nema treninga u dnevniku.", CAP, "Karton · osoblje: prazan dnevnik"),
    # ==== every other page a member or a guest reaches (25.11.2026, the
    # owner to Amir: "svugdje ikad uvest pravilo da može uređivat"; to
    # Fable: "If there is a place where he is not allowed to change text,
    # lets allow it"): every static text the page prints, <page>.<area>.<name>,
    # page by page in the page's order, its default the text the page
    # printed, character for character. A control's words are required, as
    # the karton's (a heading, a button, a link, a label, a <summary>, a
    # table header, a confirm's three texts, and a caption before a value,
    # "Odmor između serija:"); a lead, a hint, a kicker, a chip, a state's
    # word, an empty line and a placeholder are not. Where the same words
    # do the same job in two places of a page (or of the online pages, or
    # of a page and its window), one slot prints in both. What stays code
    # is in the module's docstring. ====
    # ---- the raspored (calendar.html): a client's week, the phone's day
    # view, the month, the sheet, "Tvoj sljedeći termin", the dialogs and the
    # booking gate, and the trainer's variants ----
    "raspored.series.booked": Slot("Rezervirano ✓", CAP, "Raspored · ponavljanje: potvrda Rezervirano ✓"),
    "raspored.series.until": Slot("Isti termin svaki tjedan do", CAP,
                                  "Raspored · ponavljanje: Isti termin svaki tjedan do (gumb i kvačica)", required=True),
    "raspored.report.title": Slot("Nisu rezervirani svi termini", CAP, "Raspored · izvještaj ponavljanja: naslov",
                                  required=True),
    "raspored.report.booked": Slot("Rezervirano:", CAP, "Raspored · izvještaj ponavljanja: Rezervirano:", required=True),
    "raspored.report.nothing": Slot("ništa", CAP, "Raspored · izvještaj ponavljanja: kad nije rezervirano ništa"),
    "raspored.report.skipped": Slot("Nije rezervirano:", CAP, "Raspored · izvještaj ponavljanja: Nije rezervirano:",
                                    required=True),
    # the reasons a date was not booked, after its date ("2.12. — termin je
    # popunjen"), by the redirect's key (app.SKIP_KEYS)
    **{f"raspored.report.why_{key}": Slot(text, CAP, f"Raspored · izvještaj ponavljanja: razlog, {text}", required=True)
       for key, text in (("popunjen", "termin je popunjen"), ("otkazan", "termin je otkazan"),
                         ("rezervirano", "već imaš rezervaciju"), ("zatvoren", "termin je zatvoren"),
                         ("prosao", "termin je već prošao"), ("prozor", "termin je predaleko unaprijed"),
                         ("razdoblje", "članarina tada ne vrijedi"))},
    "raspored.report.ok": Slot("U redu", CAP, "Raspored · izvještaj ponavljanja: gumb U redu (i u prozoru termina)",
                               required=True),
    "raspored.head.title": Slot("Raspored", CAP, "Raspored: naslov", required=True),
    "raspored.week.prev": Slot("← prošli tjedan", CAP, "Raspored · tjedan: gumb prošli tjedan", required=True),
    "raspored.week.today": Slot("danas", CAP, "Raspored · tjedan: gumb danas (i u mjesecu)", required=True),
    "raspored.week.next": Slot("idući tjedan →", CAP, "Raspored · tjedan: gumb idući tjedan", required=True),
    "raspored.view.week": Slot("Tjedan", CAP, "Raspored · prikaz: Tjedan", required=True),
    "raspored.view.month": Slot("Mjesec", CAP, "Raspored · prikaz: Mjesec", required=True),
    "raspored.next.kicker": Slot("Tvoj sljedeći termin", CAP, "Raspored · sljedeći termin: mala oznaka"),
    "raspored.next.canceled": Slot("OTKAZANO", CAP, "Raspored · sljedeći termin: oznaka otkazanog (i u Moje rezervacije)"),
    "raspored.next.cutoff": Slot("Otkazivanje do", CAP,
                                 "Raspored · sljedeći termin: Otkazivanje do, prije broja sati (i u Moje rezervacije)"),
    "raspored.month.prev": Slot("‹ prošli mjesec", CAP, "Raspored · mjesec: gumb prošli mjesec", required=True),
    "raspored.month.next": Slot("idući mjesec ›", CAP, "Raspored · mjesec: gumb idući mjesec", required=True),
    "raspored.month.legend_covered": Slot("članarina aktivna", CAP, "Raspored · mjesec: legenda, članarina aktivna"),
    "raspored.month.legend_mine": Slot("tvoja rezervacija", CAP, "Raspored · mjesec: legenda, tvoja rezervacija"),
    "raspored.month.legend_today": Slot("danas", CAP, "Raspored · mjesec: legenda, danas"),
    "raspored.plan.until": Slot("Članarina vrijedi do", CAP,
                                "Raspored · članarina: Članarina vrijedi do, prije datuma (mjesec i tjedan)"),
    "raspored.month.none": Slot("Nemaš aktivnu članarinu za treninge u dvorani.", CAP, "Raspored · mjesec: bez članarine"),
    "raspored.gate.link": Slot("Pogledaj cjenik →", CAP, "Raspored · članarina: poveznica Pogledaj cjenik (mjesec i tjedan)",
                               required=True),
    "raspored.week.beyond": Slot("Termini se objavljuju", CAP,
                                 "Raspored · tjedan: Termini se objavljuju, prije broja tjedana"),
    "raspored.week.empty": Slot("Ovaj tjedan nema termina.", CAP, "Raspored · tjedan: tjedan bez termina"),
    "raspored.week.add": Slot("Dodaj ih u rasporedu →", CAP, "Raspored · tjedan: trenerova poveznica na termine",
                              required=True),
    # a termin's state, the card's line and the phone's row alike
    "raspored.state.canceled": Slot("otkazano", CAP, "Raspored · termin: stanje otkazano"),
    "raspored.state.closed": Slot("zatvoreno", CAP, "Raspored · termin: stanje zatvoreno"),
    "raspored.state.mine": Slot("rezervirano ✓", CAP, "Raspored · termin: stanje rezervirano ✓"),
    "raspored.state.free": Slot("slobodno", CAP, "Raspored · termin: stanje slobodno (1:1)"),
    "raspored.state.taken": Slot("zauzeto", CAP, "Raspored · termin: stanje zauzeto (1:1)"),
    "raspored.state.full": Slot("puno", CAP, "Raspored · termin: stanje puno (red na mobitelu)"),
    "raspored.trainer.roster": Slot("Polaznici", CAP, "Raspored · termin: trenerov gumb Polaznici", required=True),
    "raspored.termin.cancel": Slot("Otkaži", CAP, "Raspored · termin: gumb Otkaži", required=True),
    "raspored.termin.need": Slot("potrebna članarina", CAP, "Raspored · termin: potrebna članarina"),
    "raspored.termin.book": Slot("Rezerviraj", CAP, "Raspored · termin: gumb Rezerviraj (i u prozoru termina)",
                                 required=True),
    "raspored.day.none": Slot("Nema termina", CAP, "Raspored · dan: dan bez termina"),
    "raspored.gate.none": Slot("Nemaš aktivnu članarinu — bez nje rezervacija nije moguća.", CAP,
                               "Raspored · članarina: bez članarine"),
    "raspored.gate.renew": Slot("— za kasnije termine produlji članarinu.", CAP,
                                "Raspored · članarina: iza datuma, produlji članarinu"),
    "raspored.gate.renew_link": Slot("Moja članarina →", CAP, "Raspored · članarina: poveznica Moja članarina",
                                     required=True),
    "raspored.mine.title": Slot("Moje rezervacije", CAP, "Raspored · moje rezervacije: naslov", required=True),
    # the phone's bottom sheet: its buttons, its note, the lead its script writes
    "raspored.sheet.cancel": Slot("Odustani", CAP, "Raspored · prozor termina: gumb Odustani", required=True),
    "raspored.sheet.late": Slot("Otkazivanje je moguće do", CAP,
                                "Raspored · prozor termina: Otkazivanje je moguće do, prije broja sati"),
    "raspored.sheet.booked": Slot("Rezervirano", CAP, "Raspored · prozor termina: rezervirani termin"),
    "raspored.sheet.free": Slot("Termin je slobodan.", CAP, "Raspored · prozor termina: slobodan termin 1:1"),
    # the confirms (base.html's #confirmDlg); their text names the termin: code
    "raspored.confirm.cancel_title": Slot("Otkazati rezervaciju?", CAP, "Raspored · otkazivanje: naslov potvrde",
                                          required=True),
    "raspored.confirm.cancel_cta": Slot("Otkaži rezervaciju", CAP,
                                        "Raspored · otkazivanje: gumb potvrde (i u prozoru termina)", required=True),
    "raspored.confirm.drop_title": Slot("Maknuti otkazani termin?", CAP, "Raspored · otkazani termin: naslov potvrde",
                                        required=True),
    "raspored.confirm.drop_cta": Slot("Makni", CAP, "Raspored · otkazani termin: gumb potvrde", required=True),
    # ---- the online treninzi: the client's list (treninzi.html; staff's is
    # treninzi_admin.html), a programme (trening_view.html), a day
    # (trening_day.html), staff's variants on these too ----
    "treninzi.head.title": Slot("Moji online treninzi", CAP, "Online treninzi · popis: naslov", required=True),
    "treninzi.head.lead": Slot("Programi tvoje razine — određuje je upitnik.", CAP, "Online treninzi · popis: uvodna rečenica"),
    "treninzi.no_plan.title": Slot("Online treninzi su dio zasebne članarine.", CAP,
                                   "Online treninzi · popis: bez online članarine, prva rečenica"),
    "treninzi.no_plan.text": Slot("Javi se treneru za pristup — plaćanje gotovinom ili karticom u dvorani.", CAP,
                                  "Online treninzi · popis: bez online članarine, druga rečenica"),
    "treninzi.upitnik.title": Slot("Ispuni upitnik za online trening", CAP, "Online treninzi · popis: naslov upitnika",
                                   required=True),
    "treninzi.upitnik.text": Slot("Prema odgovorima te svrstavamo u razinu (početna / srednja / napredna) — programi se "
                                  "otvaraju odmah.", CAP, "Online treninzi · popis: tekst upitnika"),
    "treninzi.upitnik.fill": Slot("Ispuni upitnik", CAP, "Online treninzi · popis: gumb Ispuni upitnik", required=True),
    "treninzi.level.redo": Slot("promijeni (ispuni upitnik ponovno)", CAP, "Online treninzi · popis: poveznica uz razinu",
                                required=True),
    "treninzi.empty.title": Slot("Programi za tvoju razinu još se pripremaju.", CAP,
                                 "Online treninzi · popis: nema programa, prva rečenica"),
    "treninzi.empty.text": Slot("Trener slaže sadržaj — provjeri uskoro.", CAP,
                                "Online treninzi · popis: nema programa, druga rečenica"),
    "program.head.venue": Slot("dvoranski", CAP, "Online treninzi · program: oznaka dvoranski (trener)"),
    "program.edit": Slot("Uredi program", CAP, "Online treninzi · program: gumb Uredi program (trener)", required=True),
    "program.state.open": Slot("u tijeku", CAP, "Online treninzi · program: trening u tijeku"),
    "program.state.stale": Slot("nedovršen", CAP, "Online treninzi · program: nedovršen trening"),
    "program.empty": Slot("Program još nema treninga.", CAP, "Online treninzi · program: bez treninga"),
    "program.empty_staff": Slot("Program još nema treninga — dodaj prvi u uređivanju.", CAP,
                                "Online treninzi · program: bez treninga (trener)"),
    "dan.meta.suggested": Slot("Preporučeno:", CAP, "Online treninzi · trening: Preporučeno: (i na programu)",
                               required=True),
    "dan.meta.circuit": Slot("kružni trening", CAP, "Online treninzi · trening: oznaka kružni trening (i na programu)"),
    "dan.state.new": Slot("Još nije odrađen.", CAP, "Online treninzi · trening: još nije odrađen"),
    "dan.state.open": Slot("U tijeku — nastavi gdje si stao/la.", CAP, "Online treninzi · trening: u tijeku"),
    "dan.go.start": Slot("Kreni", CAP, "Online treninzi · trening: gumb Kreni", required=True),
    "dan.go.resume": Slot("Nastavi", CAP, "Online treninzi · trening: gumb Nastavi", required=True),
    "dan.drop.button": Slot("Odbaci započeti trening", CAP, "Online treninzi · trening: gumb Odbaci započeti trening",
                            required=True),
    # its confirm, the finish screen's "Odbaci trening" asks the same
    "dan.drop.title": Slot("Odbaciti započeti trening?", CAP,
                           "Online treninzi · odbacivanje: naslov potvrde (i na kraju treninga)", required=True),
    "dan.drop.text": Slot("Spremljene serije ovog pokušaja se brišu. Trening možeš započeti ponovno.", CAP,
                          "Online treninzi · odbacivanje: tekst potvrde (i na kraju treninga)", required=True),
    "dan.drop.cta": Slot("Odbaci", CAP, "Online treninzi · odbacivanje: gumb potvrde (i na kraju treninga)", required=True),
    "dan.edit": Slot("Uredi trening", CAP, "Online treninzi · trening: gumb Uredi trening (trener)", required=True),
    "dan.video.hint": Slot("Uvodni video — pogledaj ga prije treninga.", CAP, "Online treninzi · trening: uz uvodni video"),
    # an exercise's words, the day's list, the player's card and its list alike
    "dan.exercise.rest_between": Slot("Odmor između serija:", CAP,
                                      "Online treninzi · vježba: Odmor između serija: (i u izvođenju)", required=True),
    "dan.exercise.rest_after": Slot("Odmor nakon vježbe:", CAP,
                                    "Online treninzi · vježba: Odmor nakon vježbe: (i u izvođenju)", required=True),
    "dan.exercise.no_video": Slot("Vježba još nema videa.", CAP, "Online treninzi · vježba: bez videa (i u izvođenju)"),
    "dan.exercise.rep": Slot("Jedno ponavljanje:", CAP, "Online treninzi · vježba: Jedno ponavljanje: (i u izvođenju)",
                             required=True),
    # a dvoranski programme's empty slot on the day's page (26.11.2026: staff's,
    # no client reaches such a day), its hint after it: "Prazno mjesto · čučanj";
    # since part B of the gym training also a slot's card there, the same words
    # for the same thing (a member's copy of such a day)
    "dan.slot": Slot("Prazno mjesto", CAP, "Online treninzi · trening: Prazno mjesto (dvoranski, trener; i trening "
                     "u dvorani)", required=True),
    "dan.empty": Slot("Trening još nema vježbi.", CAP, "Online treninzi · trening: bez vježbi"),
    "dan.empty_staff": Slot("Trening još nema vježbi — dodaj ih u uređivanju.", CAP,
                            "Online treninzi · trening: bez vježbi (trener)"),
    "dan.history.title": Slot("Povijest", CAP, "Online treninzi · trening: naslov Povijest", required=True),
    "dan.history.sets": Slot("Serije", CAP, "Online treninzi · trening: Serije u povijesti", required=True),
    # ---- the player (trening_player.html): the bar's line, a circuit's
    # round, a normal step, the swap list, the day's list and its dock, the
    # rest bar; the finish screen (trening_kraj.html) and the leave dialog
    # (_pass_leave.html), on both ----
    "player.top.back": Slot("← Natrag", CAP, "Trening · traka: poveznica Natrag", required=True),
    "player.finish": Slot("Završi trening", CAP, "Trening: Završi trening (traka, prozor za izlazak, nedovršen trening)",
                          required=True),
    "player.round.kicker": Slot("Kružni dio", CAP, "Trening · krug: mala oznaka"),
    "player.saved": Slot("✓ Spremljeno", CAP, "Trening: oznaka Spremljeno (vježba i krug)"),
    "player.round.intro": Slot("Vježbe idu jedna za drugom, bez pauze.", CAP, "Trening · krug: uvodna rečenica"),
    "player.round.rest": Slot("Odmor nakon kruga:", CAP, "Trening · krug: Odmor nakon kruga:", required=True),
    "player.col.set": Slot("Set", CAP, "Trening · vježba: stupac Set", required=True),
    "player.col.reps": Slot("Pon.", CAP, "Trening: stupac Pon. (vježba i krug)", required=True),
    "player.col.kg": Slot("Kg", CAP, "Trening: stupac Kg (vježba i krug)", required=True),
    "player.col.sec": Slot("Sek.", CAP, "Trening: stupac Sek. (vježba i krug)", required=True),
    "player.rate.round": Slot("Koliko je bio težak ovaj krug?", CAP, "Trening · krug: pitanje o težini", required=True),
    "player.optional": Slot("(neobavezno)", CAP, "Trening: (neobavezno) (ocjena, osjećaj, komentar)"),
    "player.round.done": Slot("odrađen", CAP, "Trening · krug: gumb, iza broja kruga", required=True),
    "player.round.done_last": Slot("odrađen — završi", CAP, "Trening · krug: gumb zadnjeg kruga, iza broja kruga",
                                   required=True),
    "player.skip": Slot("Preskoči →", CAP, "Trening: poveznica Preskoči (vježba i krug)", required=True),
    "player.skip_last": Slot("Preskoči i završi", CAP, "Trening: poveznica Preskoči i završi (vježba i krug)",
                             required=True),
    "player.step.kicker": Slot("Trenutna vježba", CAP, "Trening · vježba: mala oznaka"),
    "player.step.swapped_for": Slot("Zamjena za:", CAP, "Trening · vježba: Zamjena za:", required=True),
    "player.step.how": Slot("Kako se izvodi", CAP, "Trening · vježba: Kako se izvodi", required=True),
    "player.step.extra_set": Slot("dodatna serija", CAP, "Trening · vježba: oznaka dodatne serije"),
    "player.rate.step": Slot("Koliko je bilo teško?", CAP, "Trening · vježba: pitanje o težini", required=True),
    "player.step.save": Slot("Spremi", CAP, "Trening · vježba: gumb Spremi", required=True),
    "player.step.save_last": Slot("Spremi i završi", CAP, "Trening · vježba: gumb Spremi i završi", required=True),
    "player.swap.toggle": Slot("⇄ Zamijeni vježbu", CAP, "Trening · zamjena: Zamijeni vježbu", required=True),
    "player.swap.title": Slot("Slične vježbe", CAP, "Trening · zamjena: naslov Slične vježbe", required=True),
    "player.swap.back": Slot("Vrati", CAP, "Trening · zamjena: gumb Vrati, prije naziva vježbe", required=True),
    "player.list.title": Slot("Vježbe", CAP, "Trening · popis vježbi: naslov (i na traci dolje)", required=True),
    "player.list.circuit": Slot("kružno", CAP, "Trening · popis vježbi: oznaka kružno"),
    "player.list.swapped": Slot("(zamjena)", CAP, "Trening · popis vježbi: oznaka (zamjena)"),
    "player.rest.head": Slot("Odmor", CAP, "Trening · odmor: oznaka Odmor", required=True),
    "player.rest.go": Slot("Kreni", CAP, "Trening · odmor: oznaka Kreni na kraju odmora", required=True),
    "player.rest.skip": Slot("Preskoči odmor", CAP, "Trening · odmor: gumb Preskoči odmor", required=True),
    "kraj.kicker_done": Slot("Trening odrađen", CAP, "Trening · kraj: mala oznaka"),
    "kraj.kicker_stale": Slot("Nedovršen trening", CAP, "Trening · kraj: mala oznaka nedovršenog treninga"),
    "kraj.stale_tail": Slot("Spremi osvrt ili trening odbaci.", CAP, "Trening · kraj: nedovršen trening, druga rečenica"),
    "kraj.effort": Slot("Napor", CAP, "Trening · kraj: Napor", required=True),
    "kraj.effort_low": Slot("1 = lagano", CAP, "Trening · kraj: uz 1 na ljestvici"),
    "kraj.effort_high": Slot("10 = maksimalno", CAP, "Trening · kraj: uz 10 na ljestvici"),
    "kraj.feeling": Slot("Osjećaj", CAP, "Trening · kraj: Osjećaj", required=True),
    "kraj.note": Slot("Komentar", CAP, "Trening · kraj: polje Komentar", required=True),
    "kraj.note_placeholder": Slot("npr. kilaže, što je išlo dobro/loše", CAP, "Trening · kraj: primjer u komentaru"),
    "kraj.save": Slot("Spremi trening", CAP, "Trening · kraj: gumb Spremi trening", required=True),
    "kraj.back": Slot("Natrag na vježbe", CAP, "Trening · kraj: poveznica Natrag na vježbe", required=True),
    "kraj.drop": Slot("Odbaci trening", CAP, "Trening · kraj: gumb Odbaci trening (i u prozoru za izlazak)", required=True),
    "leave.title": Slot("Završiti trening?", CAP, "Trening · izlazak: naslov prozora", required=True),
    "leave.lead_player": Slot("Trening je u tijeku. Završi ga osvrtom ili ga odbaci — odbačenom se brišu spremljene "
                              "serije ovog pokušaja.", CAP, "Trening · izlazak: tekst za vrijeme vježbi"),
    "leave.lead_kraj": Slot("Osvrt još nije spremljen. Spremi ga i trening je završen, ili trening odbaci — odbačenom "
                            "se brišu spremljene serije.", CAP, "Trening · izlazak: tekst na kraju treninga"),
    "leave.error": Slot("Nije uspjelo — pokušaj ponovno.", CAP, "Trening · izlazak: kad odbacivanje ne uspije",
                        required=True),
    "leave.back": Slot("Natrag na osvrt", CAP, "Trening · izlazak: gumb Natrag na osvrt", required=True),
    # ---- the gym training (karton_trening.html and its osvrt,
    # karton_trening_osvrt.html; 26.11.2026, build 3 of
    # roadmap/2026-11-26-gym-training-plan.md): a member's training in the
    # gym, one page that grows as it goes. Where the same words do the same
    # job as in the player (the set table's headers, the rating's question,
    # the rest bar, "Kako se izvodi", "Jedno ponavljanje:", "Završi trening")
    # or on its finish screen (the osvrt's Napor, Osjećaj, Komentar, "Spremi
    # trening"), that slot prints in both: player.*, dan.*, kraj.*. Not
    # slots: the date and the time, the window's end ("četvrtka 26.11. u
    # ponoć"), a mark ("2/3"), a set's and the zadano's numbers, the osvrt's
    # facts ("napor 7/10 · Dobro"), the crumbs ----
    "gym.head.kicker": Slot("Trening u dvorani", CAP, "Trening u dvorani: mala oznaka"),
    "gym.head.outside": Slot("Trening izvan termina", CAP, "Trening u dvorani: naslov treninga izvan termina",
                             required=True),
    "gym.head.date_change": Slot("promijeni datum", CAP, "Trening u dvorani: gumb promijeni datum", required=True),
    "gym.head.date_field": Slot("Datum", CAP, "Trening u dvorani: polje Datum", required=True),
    "gym.head.date_save": Slot("Spremi", CAP, "Trening u dvorani: gumb Spremi datum", required=True),
    # the state's line under the date: the window's end after the first (code;
    # its words a caption before a value, so required); the other two whole
    # sentences, which emptied print no line
    "gym.state.open": Slot("Upis je otvoren do", CAP, "Trening u dvorani · stanje: Upis je otvoren do, prije dana",
                           required=True),
    "gym.state.closed": Slot("Upis je zatvoren — trener ga i dalje može urediti.", CAP,
                             "Trening u dvorani · stanje: upis zatvoren"),
    "gym.state.staff": Slot("Za člana je upis zatvoren; uređuješ kao trener.", CAP,
                            "Trening u dvorani · stanje: trener izvan članova roka"),
    "gym.empty": Slot("Trening je još prazan — dodaj prvu vježbu.", CAP, "Trening u dvorani: prazan trening"),
    # part B (26.11.2026): the templates while the training holds no row,
    # each part's "Uredi dio" and a circuit's caption ("· kružno · 3 kruga
    # · odmor 90 s": kružno the player's slot, the count and the seconds
    # code); a round's rating, its button's word and its fields' headers
    # are the player's (player.rate.round, player.round.done, player.col.*),
    # a slot's name the day page's (dan.slot)
    "gym.template.open": Slot("Odaberi gotov trening", CAP, "Trening u dvorani · predložak: gumb Odaberi gotov trening",
                              required=True),
    "gym.part.edit": Slot("Uredi dio", CAP, "Trening u dvorani · dio: gumb Uredi dio", required=True),
    "gym.part.name": Slot("Naziv dijela", CAP, "Trening u dvorani · dio: polje Naziv dijela", required=True),
    "gym.part.circuit": Slot("Kružni dio", CAP, "Trening u dvorani · dio: kvačica Kružni dio", required=True),
    "gym.part.rounds": Slot("Krugova", CAP, "Trening u dvorani · dio: polje Krugova", required=True),
    "gym.part.rest": Slot("Odmor nakon kruga (s)", CAP, "Trening u dvorani · dio: polje Odmor nakon kruga",
                          required=True),
    "gym.part.save": Slot("Spremi", CAP, "Trening u dvorani · dio: gumb Spremi", required=True),
    "gym.part.rest_caption": Slot("odmor", CAP, "Trening u dvorani · dio: odmor u naslovu kružnog dijela, prije sekundi",
                                  required=True),
    # an exercise's card
    "gym.card.planned": Slot("Zadano:", CAP, "Trening u dvorani · vježba: Zadano:, prije zadanog", required=True),
    "gym.card.add_set": Slot("+ serija", CAP, "Trening u dvorani · vježba: gumb + serija", required=True),
    "gym.card.save": Slot("Spremi", CAP, "Trening u dvorani · vježba: gumb Spremi (bez JavaScripta)", required=True),
    "gym.card.failed": Slot("Nije spremljeno — pokušaj ponovno.", CAP,
                            "Trening u dvorani · vježba: kad se kvačica ne spremi", required=True),
    "gym.card.done": Slot("Odrađeno:", CAP, "Trening u dvorani · vježba: Odrađeno:, prije serija", required=True),
    "gym.card.edit": Slot("Uredi zadano", CAP, "Trening u dvorani · vježba: gumb Uredi zadano", required=True),
    "gym.card.remove": Slot("Ukloni vježbu", CAP, "Trening u dvorani · vježba: gumb Ukloni vježbu", required=True),
    # what was given: "Uredi zadano"'s fields and the add card's, one slot each
    "gym.form.section": Slot("Dio", CAP, "Trening u dvorani · zadano: polje Dio", required=True),
    "gym.form.sets": Slot("Serije", CAP, "Trening u dvorani · zadano: polje Serije", required=True),
    "gym.form.reps": Slot("Ponavljanja", CAP, "Trening u dvorani · zadano: polje Ponavljanja", required=True),
    "gym.form.seconds": Slot("Sekunde", CAP, "Trening u dvorani · zadano: polje Sekunde", required=True),
    "gym.form.kg": Slot("Kilaža (kg)", CAP, "Trening u dvorani · zadano: polje Kilaža", required=True),
    "gym.form.rest": Slot("Pauza (s)", CAP, "Trening u dvorani · zadano: polje Pauza", required=True),
    "gym.form.note": Slot("Napomena", CAP, "Trening u dvorani · zadano: polje Napomena", required=True),
    "gym.form.save": Slot("Spremi", CAP, "Trening u dvorani · zadano: gumb Spremi", required=True),
    # a slot's card (part B): its combobox's field is the add card's (gym.add.exercise)
    "gym.slot.pick": Slot("Odaberi", CAP, "Trening u dvorani · prazno mjesto: gumb Odaberi", required=True),
    "gym.slot.remove": Slot("Ukloni", CAP, "Trening u dvorani · prazno mjesto: gumb Ukloni", required=True),
    # "Dodaj vježbu", the card at the bottom
    "gym.add.title": Slot("Dodaj vježbu", CAP, "Trening u dvorani · dodaj vježbu: naslov", required=True),
    "gym.add.exercise": Slot("Vježba", CAP, "Trening u dvorani · dodaj vježbu: polje Vježba", required=True),
    "gym.add.planned": Slot("Zadano (neobavezno)", CAP, "Trening u dvorani · dodaj vježbu: Zadano (neobavezno)",
                            required=True),
    "gym.add.go": Slot("Dodaj", CAP, "Trening u dvorani · dodaj vježbu: gumb Dodaj", required=True),
    # the osvrt once saved, and the page's foot
    "gym.done.title": Slot("Osvrt", CAP, "Trening u dvorani · kraj: naslov spremljenog osvrta", required=True),
    "gym.done.edit": Slot("Uredi osvrt", CAP, "Trening u dvorani · kraj: gumb Uredi osvrt", required=True),
    "gym.foot.empty": Slot("Isprazni trening", CAP, "Trening u dvorani · kraj: gumb Isprazni trening", required=True),
    "gym.foot.delete": Slot("Obriši trening", CAP, "Trening u dvorani · kraj: gumb Obriši trening", required=True),
    # the osvrt's page (its fields the finish screen's: kraj.*)
    "gym.osvrt.kicker": Slot("Osvrt na trening", CAP, "Trening u dvorani · osvrt: mala oznaka"),
    "gym.osvrt.back": Slot("Natrag na trening", CAP, "Trening u dvorani · osvrt: poveznica Natrag na trening",
                           required=True),
    # the confirms (base.html's #confirmDlg)
    "gym.confirm.remove_title": Slot("Ukloniti vježbu?", CAP, "Trening u dvorani · uklanjanje vježbe: naslov",
                                     required=True),
    "gym.confirm.remove_text": Slot("Upisane serije ove vježbe se brišu.", CAP,
                                    "Trening u dvorani · uklanjanje vježbe: tekst", required=True),
    "gym.confirm.remove_cta": Slot("Ukloni vježbu", CAP, "Trening u dvorani · uklanjanje vježbe: gumb", required=True),
    "gym.confirm.empty_title": Slot("Isprazniti trening?", CAP, "Trening u dvorani · pražnjenje: naslov", required=True),
    "gym.confirm.empty_text": Slot("Sve vježbe i upisane serije ovog treninga se brišu.", CAP,
                                   "Trening u dvorani · pražnjenje: tekst", required=True),
    "gym.confirm.empty_cta": Slot("Isprazni", CAP, "Trening u dvorani · pražnjenje: gumb", required=True),
    "gym.confirm.delete_title": Slot("Obrisati trening?", CAP, "Trening u dvorani · brisanje: naslov", required=True),
    "gym.confirm.delete_text": Slot("Trening izvan termina briše se sa svim vježbama, serijama i osvrtom.", CAP,
                                    "Trening u dvorani · brisanje: tekst", required=True),
    "gym.confirm.delete_cta": Slot("Obriši trening", CAP, "Trening u dvorani · brisanje: gumb", required=True),
    # ---- the profile (profil.html) ----
    "profil.head.title": Slot("Profil", CAP, "Profil: naslov", required=True),
    "profil.head.lead": Slot("Tvoji osnovni podaci — vidi ih samo trener.", CAP, "Profil: uvodna rečenica"),
    "profil.welcome": Slot("Dobrodošao/la! Dopuni osnovne podatke da te trener zna voditi — treba nam minuta.", CAP,
                           "Profil: dobrodošlica pri prvoj prijavi"),
    "profil.form.name": Slot("Ime", CAP, "Profil: polje Ime", required=True),
    "profil.form.last": Slot("Prezime", CAP, "Profil: polje Prezime", required=True),
    "profil.form.born": Slot("Datum rođenja", CAP, "Profil: polje Datum rođenja", required=True),
    "profil.form.phone": Slot("Telefon (neobavezno)", CAP, "Profil: polje Telefon", required=True),
    "profil.form.phone_placeholder": Slot("09x xxx xxxx", CAP, "Profil: primjer u polju Telefon"),
    # (no height since 26.11.2026: the karton's, karton.weight.height_*)
    "profil.form.save": Slot("Spremi podatke", CAP, "Profil: gumb Spremi podatke", required=True),
    "profil.account.title": Slot("Račun", CAP, "Profil · račun: naslov", required=True),
    "profil.account.since": Slot("Registriran/a od", CAP, "Profil · račun: Registriran/a od, prije datuma"),
    "profil.link": Slot("Moja članarina — planovi, uplate i računi →", CAP, "Profil: poveznica na Moja članarina",
                        required=True),
    # ---- logging in and signing up: the pages (login.html, signup.html,
    # forgot.html, reset.html, verify_sent.html) and base.html's login
    # window; the words the page and the window share are one slot ----
    "auth.email": Slot("Email", CAP, "Prijava i registracija: polje Email (stranice i prozor)", required=True),
    "auth.password": Slot("Lozinka", CAP, "Prijava: polje Lozinka (stranica i prozor)", required=True),
    "auth.forgot_link": Slot("Zaboravljena lozinka?", CAP, "Prijava: poveznica Zaboravljena lozinka (stranica i prozor)",
                             required=True),
    "auth.login.title": Slot("Prijava", CAP, "Prijava: naslov (i kartica u prozoru)", required=True),
    "auth.login.lead": Slot("Quality Movement Training — rezervacija termina.", CAP, "Prijava: uvodna rečenica"),
    "auth.login.submit": Slot("Prijavi se", CAP, "Prijava: gumb Prijavi se (stranica i prozor)", required=True),
    "auth.login.no_account": Slot("Nemaš račun?", CAP, "Prijava: Nemaš račun?, prije poveznice"),
    "auth.login.signup_link": Slot("Registriraj se", CAP, "Prijava: poveznica Registriraj se", required=True),
    "auth.login.invite_only": Slot("— samo uz poziv trenera", CAP, "Prijava: iza poveznice, samo uz poziv"),
    "auth.closed": Slot("Registracija novih članova je trenutno zatvorena.", CAP,
                        "Prijava i registracija: registracija zatvorena (obje stranice)"),
    "auth.signup.title": Slot("Registracija", CAP, "Registracija: naslov (i kartica u prozoru)", required=True),
    "auth.signup.lead_open": Slot("Otvori račun, odaberi članarinu i rezerviraj prvi termin.", CAP,
                                  "Registracija: uvodna rečenica (otvorena registracija)"),
    "auth.signup.invite": Slot("Račun zasad mogu otvoriti samo pozvani članovi — javi se treneru za pozivnicu.", CAP,
                               "Registracija: samo uz poziv (stranica i prozor)"),
    "auth.signup.name": Slot("Ime (neobavezno)", CAP, "Registracija: polje Ime (stranica i prozor)", required=True),
    "auth.signup.name_placeholder": Slot("npr. Ivan Horvat", CAP, "Registracija: primjer u polju Ime (stranica i prozor)"),
    "auth.signup.password": Slot("Lozinka (barem 8 znakova)", CAP, "Registracija: polje Lozinka (stranica i prozor)",
                                 required=True),
    "auth.signup.submit": Slot("Otvori račun", CAP, "Registracija: gumb Otvori račun (stranica i prozor)", required=True),
    "auth.signup.have_account": Slot("Već imaš račun?", CAP, "Registracija: Već imaš račun?, prije poveznice"),
    "auth.signup.login_link": Slot("Prijavi se", CAP, "Registracija: poveznica Prijavi se", required=True),
    "auth.forgot.title": Slot("Nova lozinka", CAP, "Zaboravljena lozinka: naslov", required=True),
    "auth.forgot.lead": Slot("Upiši email — poslat ćemo ti link za postavljanje nove lozinke.", CAP,
                             "Zaboravljena lozinka: uvodna rečenica"),
    "auth.forgot.submit": Slot("Pošalji link", CAP, "Zaboravljena lozinka: gumb Pošalji link", required=True),
    "auth.back_to_login": Slot("← natrag na prijavu", CAP,
                               "Zaboravljena lozinka: poveznica natrag na prijavu (i na Provjeri email)", required=True),
    "auth.reset.title": Slot("Postavi novu lozinku", CAP, "Nova lozinka: naslov", required=True),
    "auth.reset.lead": Slot("Link vrijedi sat vremena i može se iskoristiti jednom.", CAP, "Nova lozinka: uvodna rečenica"),
    "auth.reset.password": Slot("Nova lozinka (barem 8 znakova)", CAP, "Nova lozinka: polje Nova lozinka", required=True),
    "auth.reset.submit": Slot("Spremi lozinku", CAP, "Nova lozinka: gumb Spremi lozinku", required=True),
    "auth.verify.title": Slot("Provjeri email", CAP, "Provjeri email: naslov", required=True),
    "auth.verify.sent_to": Slot("Poslali smo link za potvrdu na", CAP, "Provjeri email: prije adrese"),
    "auth.verify.click": Slot("Klikni ga i račun je spreman — link vrijedi", CAP, "Provjeri email: koliko vrijedi link"),
    "auth.verify.hours": Slot("24 sata", CAP, "Provjeri email: 24 sata (podebljano)"),
    "auth.verify.reset_valid": Slot("Link vrijedi", CAP, "Provjeri email · nova lozinka: koliko vrijedi link"),
    "auth.verify.reset_hours": Slot("1 sat", CAP, "Provjeri email · nova lozinka: 1 sat (podebljano)"),
    "auth.modal.title": Slot("Dobrodošli natrag", CAP, "Prozor prijave: naslov", required=True),
    "auth.modal.title_signup": Slot("Otvori račun", CAP, "Prozor prijave: naslov na kartici Registracija", required=True),
    # ---- the app's own pieces: a plan's door (PLAN_LINKS' pages: the
    # button an owner of the plan gets on /moja-clanarina and on the
    # landing), base.html's error alert's link, the install banner, the
    # confirm dialog's default words, the osvrt prompt after a login, the
    # error page (error.html) and the Mjesečno / Godišnje switch
    # (_period.html; _tiers.html prints a count and an amount alone) ----
    "app.door.raspored": Slot("Rezerviraj termin", CAP, "Aplikacija · vrata plana: termini (Moja članarina, Početna)",
                              required=True),
    "app.door.online": Slot("Otvori online treninge", CAP, "Aplikacija · vrata plana: online (Moja članarina, Početna)",
                            required=True),
    "app.door.prehrana": Slot("Otvori prehranu", CAP, "Aplikacija · vrata plana: prehrana (Moja članarina, Početna)",
                              required=True),
    "app.alert.prices": Slot("Pogledaj cjenik →", CAP, "Aplikacija · poruka bez članarine: poveznica na cjenik",
                             required=True),
    "app.install.title": Slot("Dodaj na početni zaslon", CAP, "Aplikacija · instalacija: naslov", required=True),
    "app.install.lead": Slot("Raspored i karton jednim dodirom, kao aplikacija.", CAP, "Aplikacija · instalacija: tekst"),
    "app.install.ios_press": Slot("Pritisni", CAP, "Aplikacija · instalacija (iPhone): korak 1, prije Podijeli"),
    "app.install.ios_share": Slot("Podijeli", CAP, "Aplikacija · instalacija (iPhone): Podijeli (podebljano)"),
    "app.install.ios_where": Slot("u pregledniku", CAP, "Aplikacija · instalacija (iPhone): korak 1, iza ikone"),
    "app.install.android_menu": Slot("Otvori izbornik preglednika", CAP, "Aplikacija · instalacija (Android): korak 1"),
    "app.install.pick": Slot("Odaberi", CAP, "Aplikacija · instalacija: korak 2, prije stavke"),
    "app.install.pick_item": Slot("„Dodaj na početni zaslon”", CAP, "Aplikacija · instalacija: korak 2, stavka (podebljano)"),
    "app.install.ok": Slot("U redu", CAP, "Aplikacija · instalacija: gumb U redu", required=True),
    "app.install.go": Slot("Instaliraj", CAP, "Aplikacija · instalacija: gumb Instaliraj", required=True),
    # the phone reminder (26.11.2026, the owner: "if a user didnt give it,
    # when he opens the app a popup reminder should appear"): the install
    # banner's card for a member with no phone number
    "app.phone.title": Slot("Dodaj broj mobitela", CAP, "Aplikacija · broj mobitela: naslov", required=True),
    "app.phone.lead": Slot("Da ti se trener može javiti ako se termin promijeni.", CAP,
                           "Aplikacija · broj mobitela: tekst"),
    "app.phone.go": Slot("Upiši broj", CAP, "Aplikacija · broj mobitela: gumb Upiši broj", required=True),
    "app.confirm.title": Slot("Jesi li siguran/na?", CAP, "Aplikacija · potvrda: naslov kad stranica ne kaže svoj",
                              required=True),
    "app.confirm.cancel": Slot("Odustani", CAP, "Aplikacija · potvrda: gumb Odustani", required=True),
    "app.confirm.go": Slot("Potvrdi", CAP, "Aplikacija · potvrda: gumb kad stranica ne kaže svoj", required=True),
    "app.feedback.title": Slot("Kako je bilo?", CAP, "Aplikacija · osvrt nakon prijave: naslov", required=True),
    "app.feedback.one": Slot("Jedan odrađen termin još čeka tvoj osvrt.", CAP,
                             "Aplikacija · osvrt nakon prijave: jedan termin čeka osvrt"),
    "app.feedback.note": Slot("Kratko: napor, osjećaj i komentar — pomaže treneru posložiti sljedeći trening.", CAP,
                              "Aplikacija · osvrt nakon prijave: tekst"),
    "app.feedback.later": Slot("Kasnije", CAP, "Aplikacija · osvrt nakon prijave: gumb Kasnije", required=True),
    "app.feedback.fill": Slot("Ispuni osvrt", CAP, "Aplikacija · osvrt nakon prijave: gumb Ispuni osvrt", required=True),
    "app.error.back": Slot("← Na raspored", CAP, "Aplikacija · stranica greške: poveznica Na raspored", required=True),
    # the switch's words: edited on /tekstovi only (printed plain, no box):
    # in edit mode the switch must keep switching, the yearly prices behind
    # it being edited in place
    "period.month": Slot("Mjesečno", CAP, "Mjesečno / Godišnje: gumb Mjesečno", required=True),
    "period.year": Slot("Godišnje", CAP, "Mjesečno / Godišnje: gumb Godišnje", required=True),
}

# The karton's texts by area (25.11.2026), in the page's order: the caption
# each area has in the panel "Svi tekstovi kartona" at the bottom of a staff
# member's own karton in edit mode (karton.html), which lists every
# karton.* slot under its area's caption, so the texts only a member, the
# trainer's view or a confirm dialog shows are in his reach too.
KARTON_AREAS = {"head": "Zaglavlje", "upitnik": "Upitnik", "limits": "Ograničenja i bolovi",
                "weight": "Tjelesna kompozicija", "photos": "Napredak — fotografije", "maxes": "Procijenjeni maksimumi",
                "history": "Povijest vježbe",
                "termini": "Nadolazeći termini", "diary": "Dnevnik treninga", "outside": "Trening izvan termina",
                "osvrt": "Osvrt na trening", "confirm": "Prozori za potvrdu",
                "staff": "Pogled trenera i karton osoblja"}
# (caption, the area's keys in registry order) per area, for the panel
KARTON_PANEL = tuple((caption, tuple(key for key in SLOTS if key.startswith(f"karton.{area}.")))
                     for area, caption in KARTON_AREAS.items())

# /tekstovi (25.11.2026, Admin ▾ → Tekstovi): every plain text of the app
# on one page, the ones only a member or a guest ever sees among them, so
# the editor reaches each. By page, in the nav's order, each page by area,
# from the keys' prefixes: (the page's caption, the address a staff member
# opens it at or None, whether the page has lists, tables or cards of its
# own besides, ((the area's caption, its prefixes), …)). A key goes to the
# first area, in this order, one of whose prefixes it starts with (a prefix
# may be a whole key: "cjenik.hint" before "cjenik."). Lists, tables, switches and photos (ListSlot,
# RowsSlot, FlagSlot, ImageSlot) and the rows' texts (the announcements,
# the gym's cards, the upitnik's questions) are edited on their page only.
_TEXT_RULES = (
    ("Početna", "/", True, (
        ("Naslovnica", ("hero.", "stage.")),
        ("Ponuda", ("offer.", "landing.offer.", "landing.cta.")),
        ("Dvorana", ("gym.kicker", "gym.h2")),   # the gym training's gym.<area>.* are its own page's
        ("Galerija", ("landing.gallery.",)),
        ("Radno vrijeme i kontakt", ("info.",)),
        ("Podnožje", ("footer",)))),
    ("Raspored", "/raspored", False, (
        ("Zaglavlje i tjedan", ("raspored.head.", "raspored.week.", "raspored.view.")),
        ("Tvoj sljedeći termin", ("raspored.next.",)),
        ("Mjesec", ("raspored.month.",)),
        ("Članarina", ("raspored.plan.", "raspored.gate.")),
        ("Termini", ("raspored.state.", "raspored.trainer.", "raspored.termin.", "raspored.day.")),
        ("Moje rezervacije", ("raspored.mine.",)),
        ("Ponavljanje i izvještaj", ("raspored.series.", "raspored.report.")),
        ("Prozor termina", ("raspored.sheet.",)),
        ("Prozori za potvrdu", ("raspored.confirm.",)))),
    ("Karton", "/karton", False, tuple((caption, (f"karton.{area}.",)) for area, caption in KARTON_AREAS.items())),
    ("Online treninzi", "/treninzi", False, (
        ("Popis programa", ("treninzi.",)),
        ("Program", ("program.",)),
        ("Trening", ("dan.meta.", "dan.state.", "dan.go.", "dan.drop.", "dan.edit", "dan.video.", "dan.slot",
                     "dan.empty", "dan.history.")),
        ("Vježba", ("dan.exercise.",)))),
    ("Trening (izvođenje)", None, False, (
        ("Traka i zajedničko", ("player.top.", "player.finish", "player.saved", "player.optional", "player.skip",
                                "player.col.")),
        ("Vježba", ("player.step.", "player.rate.step")),
        ("Krug", ("player.round.", "player.rate.round")),
        ("Zamjena", ("player.swap.",)),
        ("Popis vježbi", ("player.list.",)),
        ("Odmor", ("player.rest.",)),
        ("Kraj treninga", ("kraj.",)),
        ("Prozor za izlazak", ("leave.",)))),
    # the gym training (26.11.2026, build 3): a member's own page, no one
    # address for staff to open (a training of theirs outside a termin is
    # one, a member's they reach as the member)
    ("Trening u dvorani", None, False, (
        ("Zaglavlje", ("gym.head.", "gym.state.", "gym.empty")),
        ("Predložak", ("gym.template.",)),
        ("Dio i krugovi", ("gym.part.",)),
        ("Vježba", ("gym.card.", "gym.form.")),
        ("Prazno mjesto", ("gym.slot.",)),
        ("Dodaj vježbu", ("gym.add.",)),
        ("Kraj treninga", ("gym.done.", "gym.foot.")),
        ("Osvrt", ("gym.osvrt.",)),
        ("Prozori za potvrdu", ("gym.confirm.",)))),
    ("Moja članarina", "/moja-clanarina", False, (
        ("Zaglavlje", ("clanarina.h.title", "cjenik.hint")),
        ("Tvoji planovi", ("clanarina.h.plans", "clanarina.plan.", "clanarina.chip.", "clanarina.fact.",
                           "clanarina.status.", "clanarina.portal", "clanarina.switch.", "clanarina.to_card.",
                           "clanarina.lapsed.", "clanarina.none.")),
        ("Dodaj plan", ("clanarina.h.add", "clanarina.h.online", "clanarina.h.gym", "clanarina.add.",
                        "clanarina.subscribe", "cjenik.")),
        ("Nazivi planova", ("plan.",)),
        ("Cijene", ("price.", "addon.", "clanarina.addon.")),
        ("Računi", ("clanarina.h.bills", "clanarina.bills.")))),
    ("Prehrana", "/prehrana", False, (("Prehrana", ("prehrana.",)),)),
    ("Upitnik", "/upitnik", True, (("Upitnik", ("upitnik.",)),)),
    ("Vodič", "/vodic", True, (("Naslov i gumb", ("vodic.title", "vodic.cta")),
                               *((f"Odjeljak {n}", (f"vodic.{n}.",)) for n in range(1, len(VODIC_SECTIONS) + 1)))),
    ("Profil", "/profil", False, (("Profil", ("profil.",)),)),
    ("Prijava i registracija", None, False, (
        ("Zajedničko", ("auth.email", "auth.password", "auth.forgot_link")),
        ("Prijava", ("auth.login.",)),
        ("Registracija", ("auth.closed", "auth.signup.")),
        ("Zaboravljena lozinka", ("auth.forgot.", "auth.back_to_login")),
        ("Nova lozinka", ("auth.reset.",)),
        ("Provjeri email", ("auth.verify.",)),
        ("Prozor prijave", ("auth.modal.",)))),
    ("Aplikacija", None, False, (
        ("Vrata planova", ("app.door.",)),
        ("Poruka bez članarine", ("app.alert.",)),
        ("Instalacija", ("app.install.",)),
        ("Broj mobitela", ("app.phone.",)),
        ("Prozor za potvrdu", ("app.confirm.",)),
        ("Osvrt nakon prijave", ("app.feedback.",)),
        ("Stranica greške", ("app.error.",)),
        ("Mjesečno / Godišnje", ("period.",)))),
)


def _text_pages() -> tuple:
    """_TEXT_RULES with each plain Slot's key in its area, the areas' keys
    in registry order and an area with none left out (tests/test_copy_rule.py:
    every plain slot is in one area, none in two)."""
    place = {key: next(((page, area) for page, _, _, areas in _TEXT_RULES for area, prefixes in areas
                        if key.startswith(prefixes)), None)
             for key, slot in SLOTS.items() if type(slot) is Slot}
    pages = []
    for page, href, lists, areas in _TEXT_RULES:
        rows = tuple((area, tuple(k for k, at in place.items() if at == (page, area))) for area, _ in areas)
        pages.append((page, href, lists, tuple(r for r in rows if r[1])))
    return tuple(pages)


# (page caption, href or None, has lists of its own, ((area caption, keys), …)), the nav's order
TEXT_PAGES = _text_pages()

# Every price the site shows -> the slot of its bazna cijena (23.11.2026;
# Croatia's Pravilnik o isticanju bazne cijene proizvoda, NN 132/2026, in
# force since 17.11.2026: beside each retail price its base price, for a
# service the one applied on 10.9.2026, or on the day it was first offered
# after that). The templates look a price's base up here (a Jinja global,
# app.py: _plan_price.html's base and base_paren) and print it under the
# price, "Bazna cijena na 10.9.2026.: 50 €"; POST /copy/{key} fills a base with its
# price's first number (app.py, copy_save). A gym card's own prices have
# theirs in its row (GYM_CARD_BASE_OF, below).
BASE_OF = {
    **{f"price.{plan}.amount": f"price.{plan}.base" for plan in REFERENCE_PRICES},
    **{f"price.{plan}.year_amount": f"price.{plan}.year_base" for plan in REFERENCE_PRICES if plan != "online"},
    "offer.online.year_price": "offer.online.year_base",
    "offer.online2.price": "offer.online2.base",
    "offer.online2.year_price": "offer.online2.year_base",
    "offer.online3.price": "offer.online3.base",
    "offer.online3.year_price": "offer.online3.year_base",
    "addon.online": "addon.online.base",
    "addon.dvorana": "addon.dvorana.base",
}

# ---- the landing's announcements (#aktualno, in the hero) ----
# Rows of the announcements table (models.Announcement), not slots: the
# owner's cards for the month (a new group, a course), as many as he adds, up
# to db.MAX_ANNOUNCEMENTS. Each one is switched off in edit mode when it is
# over (a hidden card is not on a visitor's page at all, and with none shown
# neither is their box), may carry a photo behind it, and its link always
# leads to the contact (/#kontakt). The dicts below are keyed by the row's
# columns.

# a new card ("+ Dodaj najavu"): these placeholders to retype, shown, no photo
ANNOUNCEMENT_BLANK = {"tag": "Novo", "title": "Nova najava", "when_text": "Kada i gdje",
                      "body": "Kratki opis — klikni i upiši.", "cta": "Javi nam se"}

# the two examples the landing shipped with (the event1.* / event2.* slots'
# defaults until 18.10.2026), the cards of the demo seed (scripts/seed_demo.py);
# the migration that made them rows carries its own copy
ANNOUNCEMENT_EXAMPLES = (
    {"tag": "Novo", "title": "Treninzi za penziće", "when_text": "Utorkom i četvrtkom u 10:00",
     "body": "Lagani grupni treninzi za zlatne godine: snaga, ravnoteža i pokretljivost u ugodnom "
             "tempu, uz stručno vodstvo. Prijave u dvorani ili porukom.",
     "cta": "Javi nam se"},
    {"tag": "Nova grupa", "title": "Pilates za cure", "when_text": "Srijedom u 18:00",
     "body": "Pilates u maloj grupi: jezgra, držanje i opuštanje, za sve razine. Prijave u tijeku.",
     "cta": "Javi nam se"},
)

# A card's fields as the editor's virtual keys name them, aktualno.<id>.<field>,
# and how each is edited: a text as a Slot, its default the placeholder
# Zadano puts back (an emptied one stays empty since 20.10.2026: none is
# required); the switch as a FlagSlot, on by default; the photo as an
# ImageSlot. The label is the field's word in the editor's bar, after the
# card's number ("Najava 2: naslov", landing.html).
ANNOUNCEMENT_SLOTS: dict[str, Slot | FlagSlot | ImageSlot] = {
    "tag": Slot(ANNOUNCEMENT_BLANK["tag"], CAP, "oznaka"),
    "title": Slot(ANNOUNCEMENT_BLANK["title"], CAP, "naslov"),
    "when": Slot(ANNOUNCEMENT_BLANK["when_text"], CAP, "termin"),
    "text": Slot(ANNOUNCEMENT_BLANK["body"], CAP, "tekst"),
    "cta": Slot(ANNOUNCEMENT_BLANK["cta"], CAP, "gumb"),
    "show": FlagSlot(True, "prikazano"),
    "image": ImageSlot("slika"),
}
# where a row keeps each text ("when" is a keyword in too many places)
ANNOUNCEMENT_COLUMNS = {"tag": "tag", "title": "title", "when": "when_text", "text": "body", "cta": "cta"}

# ---- the landing's gym cards (#dvorana, under the online tiers) ----
# Rows of the gym_cards table (models.GymCard), not slots, since 20.10.2026
# (the owner: "lets add an option so that my friend can add new tabs, just
# like in the announcement part"): Dvorana, Individualno and the offers the
# gym owner adds beside them, up to db.MAX_GYM_CARDS. Each is switched off
# in edit mode when it is over (a hidden card is not on a visitor's page,
# and with none shown neither is the section). The dicts below are keyed by
# the row's columns. A card stands for plans or for none (models.GymCard);
# one he adds stands for none: his own price and the contact.

# a new card ("+ Dodaj karticu"): these placeholders to retype, shown, no
# plans, no extra lines, no base prices (the first number typed into a
# price becomes its base too, app.py: 23.11.2026)
GYM_CARD_BLANK = {"title": "Nova kartica", "lead": "Kratki opis — klikni i upiši.",
                  "points": ("Prva stavka — klikni i upiši", "Druga stavka"), "extra": (),
                  "price": "na upit", "unit": "", "year_price": "na upit", "year_unit": "",
                  "base_price": "", "base_year_price": ""}

# the two cards the landing shipped with (the offer.dvorana.* /
# offer.individualno.* slots' defaults until 20.10.2026) and the plans they
# stand for, the first pricing each: the cards of the demo seed
# (scripts/seed_demo.py); the migration that made them rows carries its own
# copy. Their own price and unit are empty: a plan prices them (and since
# 21.10.2026 their yearly price too, its price.<plan>.year_* slots: their
# own year_price / year_unit are never printed, nor their own bases since
# 23.11.2026, base_price / base_year_price: a plan's are its slots').
GYM_CARD_EXAMPLES = (
    {"title": "Dvorana", "lead": "Grupni treninzi u Dubravi.",
     "points": ("Male grupe do 8 polaznika", "8, 12 ili 16 treninga mjesečno", "Termin rezerviraš u aplikaciji"),
     "extra": (), "price": "", "unit": "", "year_price": "na upit", "year_unit": "", "base_price": "",
     "base_year_price": "", "plans": "grupni"},
    {"title": "Individualno", "lead": "Trener samo za tebe.",
     # their prices are the line under the card's price (landing.html,
     # .price-note), so a bullet is free text
     "points": ("Rad 1:1, po dogovoru", "U dvoje ili troje", "Rehabilitacija"),
     "extra": (), "price": "", "unit": "", "year_price": "na upit", "year_unit": "", "base_price": "",
     "base_year_price": "", "plans": "individualni,poluindividualni,rehabilitacija"},
)

# A card's fields as the editor's virtual keys name them, dvorana.<id>.<field>,
# and how each is edited: a text as a Slot, its default the placeholder
# Zadano puts back (an emptied one stays empty since 20.10.2026: none is
# required); the bullets as a ListSlot (Zadano puts the new card's two
# back), and its extra lines under them as one too (20.10.2026: none until
# the editor adds one, and Zadano empties them); the switch as a FlagSlot,
# on by default. The label is the field's word in the editor's bar, after
# the card's number ("Kartica 2: naziv", landing.html). price / unit and
# year_price / year_unit print only on a card that stands for no plan: a
# plan's card prints the plan's price slots (its yearly ones since
# 21.10.2026, price.<plan>.year_amount / .year_unit). base_price /
# base_year_price (23.11.2026) are those two prices' bazna cijena, under
# them where they print (GYM_CARD_BASE_OF; the slots' BASE_OF for a plan's).
GYM_CARD_SLOTS: dict[str, Slot | ListSlot | FlagSlot] = {
    "title": Slot(GYM_CARD_BLANK["title"], CAP, "naziv"),
    "lead": Slot(GYM_CARD_BLANK["lead"], CAP, "podnaslov"),
    "points": ListSlot(GYM_CARD_BLANK["points"], CAP_ITEMS, CAP, "stavka"),
    "extra": ListSlot(GYM_CARD_BLANK["extra"], CAP_ITEMS, CAP, "dodatni tekst"),
    "price": Slot(GYM_CARD_BLANK["price"], CAP, "mjesečna cijena"),
    "unit": Slot(GYM_CARD_BLANK["unit"], CAP, "uz mjesečnu cijenu"),
    "year_price": Slot(GYM_CARD_BLANK["year_price"], CAP, "godišnja cijena"),
    "year_unit": Slot(GYM_CARD_BLANK["year_unit"], CAP, "uz godišnju cijenu"),
    "base_price": Slot(GYM_CARD_BLANK["base_price"], CAP, "bazna mjesečna cijena"),
    "base_year_price": Slot(GYM_CARD_BLANK["base_year_price"], CAP, "bazna godišnja cijena"),
    "show": FlagSlot(True, "prikazano"),
}
# where a row keeps each text (its lists, the bullets and the extra lines,
# and the switch have setters of their own: db.set_gym_card_list, each list
# in the column its field names, and db.set_gym_card_shown)
GYM_CARD_COLUMNS = {"title": "title", "lead": "lead", "price": "price", "unit": "unit",
                    "year_price": "year_price", "year_unit": "year_unit",
                    "base_price": "base_price", "base_year_price": "base_year_price"}
# a card's own price -> the column of its bazna cijena (23.11.2026), as
# BASE_OF maps a price slot to its base's
GYM_CARD_BASE_OF = {"price": "base_price", "year_price": "base_year_price"}

# ---- the upitnik's questions (/upitnik) ----
# Rows of the upitnik_questions table (models.UpitnikQuestion), not slots,
# since 26.10.2026 (the owner: "so that Amir can also add or remove
# questions from the questionnaire"): the gym owner adds, removes, hides,
# reorders and classifies them in edit mode, up to
# db.MAX_UPITNIK_QUESTIONS; until then the fifteen were fixed in code and
# only their words were slots (upitnik.q<n>.text / .options / .low / .high,
# upitnik.q14b.text, upitnik.q15b.text). No emoji in them (the owner,
# 26.10.2026: "remove all emojis and emoticons from questions").


def _question(n: int, part: int, kind: str, text: str, options: tuple[str, ...] = (), low: str = "",
              high: str = "", scoring: str = "", role: str = "", parent: int | None = None,
              condition: str = "") -> dict:
    """One of the default questions, a row's values (its id too: the
    answers' key, q<n>; and the question it is asked after, with the
    answer that asks it, for one that is)."""
    return {"id": n, "part": part, "kind": kind, "text": text, "options": options, "low": low, "high": high,
            "scoring": scoring, "role": role, "parent_id": parent, "condition": condition}


# The gym owner's questions as the rows start, in their order: the demo
# seed's (scripts/seed_demo.py, db.add_upitnik_question) and a test's. The
# migrations that made them rows (3f8a6c2d9b71, the fifteen with ids 1–15:
# the answers stored before it keep their meaning) and the two follow-ups
# questions (5c1e7a9d2b48, which gives them the next ids, 16 and 17, on a
# database that starts from these) carry their own copies. Part 1, q1–q4
# (choices): the goal, the days a week, the minutes, the place, for the
# programme's content later, scored never. Part 2, q5–q11 (scales): the
# score, q5–q7 trening baza and q8–q11 navike. Part 3, q12–q13 (scales):
# for the trainer only. Part 4: q14 the pain question (a scale) with q16
# under it, where it hurts, asked at 4 or more, and q15 the injuries
# question (yes / no) with q17 under it, a short note, asked at yes.
UPITNIK_DEFAULT_QUESTIONS = (
    _question(1, 1, "choice", "Koji je tvoj glavni cilj?",
              ("Gubitak težine", "Povećanje snage i mišićne mase", "Bolja kondicija i izdržljivost",
               "Rehabilitacija / rješavanje bolova", "Opće zdravlje i kretanje")),
    _question(2, 1, "choice", "Koliko dana tjedno možeš trenirati?", ("2", "3", "4", "5+")),
    _question(3, 1, "choice", "Koliko minuta imaš za jedan trening?", ("do 30", "30-45", "45-60", "60+")),
    _question(4, 1, "choice", "Gdje ćeš trenirati?",
              ("Kod kuće bez opreme", "Kod kuće s osnovnom opremom", "U teretani")),
    _question(5, 2, "scale", "Koliko redovito si trenirao/la u zadnjih 6 mjeseci (2x tjedno ili više)?",
              low="uopće nisam", high="stalno i dosljedno", scoring="baza"),
    _question(6, 2, "scale", "Kako bi ocijenio/la svoju fizičku kondiciju?",
              low="vrlo loša", high="izvrsna", scoring="baza"),
    _question(7, 2, "scale", "Kako ocjenjuješ svoje poznavanje treninga?",
              low="ne znam ništa", high="znam sve i izvodim ispravno", scoring="baza"),
    _question(8, 2, "scale", "Paziš li redovito na prehranu?", low="uopće ne", high="uvijek", scoring="navike"),
    _question(9, 2, "scale", "Vodiš li aktivan životni stil izvan treninga (šetnje, kretanje)?",
              low="sjedim cijeli dan", high="stalno sam u pokretu", scoring="navike"),
    _question(10, 2, "scale", "Koliko si motiviran/a za promjenu i dosljednost?",
              low="uopće nisam", high="jako sam motiviran/a", scoring="navike"),
    _question(11, 2, "scale", "Koliko prosječno spavaš po noći?", low="manje od 4h", high="više od 8h",
              scoring="navike"),
    _question(12, 3, "scale", "Koristiš li dodatke prehrani (vitamini, minerali, kreatin...)?",
              low="nikad", high="redovito"),
    _question(13, 3, "scale", "Koliko ti je važna osobna briga o zdravlju i tijelu?",
              low="nije mi prioritet", high="izuzetno važno"),
    _question(14, 4, "scale", "Imaš li često bolove (leđa, vrat, kuk...)?", low="nikad", high="vrlo često",
              role="pain"),
    _question(16, 4, "text", "Gdje te boli?", parent=14, condition=">=4"),
    _question(15, 4, "yesno", "Imaš li ozljede, operacije ili zdravstvena ograničenja koja trebamo znati?",
              role="injuries"),
    _question(17, 4, "text", "Opiši ukratko.", parent=15, condition="yes"),
)

# a new question ("+ Dodaj pitanje"): a scale in part 2 that scores
# nothing, shown, asked always, after the last, with these placeholders to
# retype; its options are ready for the day it becomes a choice (a choice
# keeps two at least). A scale's ends print as "1 = …" and "10 = …".
UPITNIK_BLANK = {"part": 2, "kind": "scale", "text": "Novo pitanje", "options": ("Prvi odgovor", "Drugi odgovor"),
                 "low": "…", "high": "…", "scoring": "", "role": ""}

# A question's texts as the editor's virtual keys name them,
# upitnik.<id>.<field>, and how each is edited: a text as a Slot, its
# default the placeholder Zadano puts back (an emptied one stays empty: none
# is required), the options as a ListSlot (a choice's, and a multi's; app.py
# keeps two at least, upitnik.MIN_OPTIONS, and Zadano puts the placeholders
# back). The label is the field's word in the editor's bar, after the
# question's number ("Pitanje 7: tekst", "Pitanje 7: odgovor 2"). Its
# settings (part, kind, scoring, role, shown, the question it is asked
# after and the answer: parent_id, condition) are no texts: POST
# /upitnik/pitanje/{id} (qmt.upitnik.settings, qmt.upitnik.condition).
# A role's follow-up text was one of them until 27.10.2026 (followup_text):
# the follow-ups are questions of their own since.
UPITNIK_QUESTION_SLOTS: dict[str, Slot | ListSlot] = {
    "text": Slot(UPITNIK_BLANK["text"], CAP, "tekst"),
    "options": ListSlot(UPITNIK_BLANK["options"], CAP_ITEMS, CAP, "odgovor"),
    "low": Slot(UPITNIK_BLANK["low"], CAP, "uz 1"),
    "high": Slot(UPITNIK_BLANK["high"], CAP, "uz 10"),
}
# where a row keeps each text (its options have a setter of their own:
# db.set_upitnik_question_options)
UPITNIK_QUESTION_COLUMNS = {"text": "text", "low": "low", "high": "high"}


def clean(text: str) -> str:
    """What gets stored. Line breaks are kept (they print: span.t in
    base.html). Within a line every run of spaces and tabs becomes one space
    and the line is trimmed; blank lines at the start and the end go, and
    three or more line breaks in a row become two (one empty line at most).
    An empty result is an emptied text (POST /copy/{key}): stored as "",
    except a required slot's (a number), whose default comes back; a list
    item is removed; a row's cell stays empty (RowsSlot)."""
    lines = (" ".join(line.split()) for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines).strip("\n"))


def load_items(raw: str | None, slot: ListSlot) -> list[str]:
    """A list slot's items: the stored JSON array, or the default list when
    nothing is stored (or the row cannot be read as a list)."""
    if raw is None:
        return list(slot.default)
    try:
        data = json.loads(raw)
    except ValueError:
        return list(slot.default)
    if not isinstance(data, list):
        return list(slot.default)
    return [t for t in (clean(str(x)) for x in data) if t]


def dump_items(items: list[str]) -> str:
    """What a list slot stores: a JSON array of cleaned, non-empty items."""
    return json.dumps([t for t in (clean(x) for x in items) if t], ensure_ascii=False)


def items_for(key: str, texts: dict[str, str]) -> list[str]:
    """The items a page prints for list slot `key`, given the edited texts
    (db.copy_texts()). Templates call it as copy_items (see _copy.html)."""
    return load_items(texts.get(key), SLOTS[key])


def load_rows(raw: str | None, slot: RowsSlot) -> list[list[str]]:
    """A rows slot's rows, each [first, second], cleaned: the stored JSON
    array of two-item arrays, or the default rows when nothing is stored
    (or the row cannot be read as such an array). A cell may be empty; a
    row whose two cells are both empty is dropped."""
    default = [list(row) for row in slot.default]
    if raw is None:
        return default
    try:
        data = json.loads(raw)
    except ValueError:
        return default
    if not isinstance(data, list) or not all(isinstance(row, list) and len(row) == 2 for row in data):
        return default
    rows = [[clean(str(a)), clean(str(b))] for a, b in data]
    return [row for row in rows if any(row)]


def dump_rows(rows) -> str:
    """What a rows slot stores: a JSON array of [first, second] pairs of
    cleaned texts, a row whose two cells are both empty dropped."""
    cleaned = [[clean(a), clean(b)] for a, b in rows]
    return json.dumps([row for row in cleaned if any(row)], ensure_ascii=False)


def rows_for(key: str, texts: dict[str, str]) -> list[list[str]]:
    """The rows a page prints for rows slot `key`, given the edited texts
    (db.copy_texts()). Templates call it as copy_rows (see _copy.html)."""
    return load_rows(texts.get(key), SLOTS[key])


def online_tier_names(texts: dict[str, str]) -> dict[str, str]:
    """Each online tier (models.ONLINE_TIERS) -> its name, given the edited
    texts (db.copy_texts()): its QMove card's title slot as the gym owner
    typed it, else the default ("QMove START"), as c.t prints it."""
    # an emptied title (stored "", since 20.10.2026) is no name for a
    # record: the default stands in on /clanarine and /moja-clanarina
    return {tier: texts.get(f"{slot}.title") or SLOTS[f"{slot}.title"].default
            for tier, slot in ONLINE_TIER_SLOTS.items()}


def flag_on(key: str, texts: dict[str, str]) -> bool:
    """Whether flag slot `key` is on, given the edited texts
    (db.copy_texts()): a stored "on" or "off", else the default (no row, or a
    row that is neither). Templates call it as copy_flag."""
    stored = texts.get(key)
    if stored in ("on", "off"):
        return stored == "on"
    return SLOTS[key].default


def image_name(key: str, texts: dict[str, str]) -> str | None:
    """The stored photo's file name for image slot `key`, given the edited
    texts (db.copy_texts()), or None: no row, or a row that is empty or names
    a path rather than a file ("/", "\\" or ".." in it), which is never let
    near storage. Templates call it as copy_image."""
    name = texts.get(key)
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    return name
