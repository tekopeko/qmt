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
ONLINE_POINTS = ("Program po tvojoj razini i cilju", "Video upute za svaku vježbu",
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
    "online": ("Programi po tvojoj razini i cilju, s video uputama — gdje god jesi.",),
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
    # slots above. Not slots: the sentences built around a date or a number
    # (the status box, the chips, the facts and their captions) and the
    # ledger's headers.
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
    # The plans' names on /moja-clanarina and nowhere else: the headings of
    # its cards, a plan held and a plan to add. Their defaults are
    # PLAN_LABELS, which stay fixed everywhere else, this page's ledger
    # included: the timetable's rows, /clanarine, the emails and the alerts
    # name the app's own records, and those do not change with the copy.
    **{f"plan.{plan}.name": Slot(label, CAP, f"Članarina: naziv plana · {plan}")
       for plan, label in PLAN_LABELS.items()},
    # ---- prehrana ----
    "prehrana.h1": Slot("Prehrana ide uz trening", CAP, "Prehrana: naslov"),
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
# plans, no extra lines
GYM_CARD_BLANK = {"title": "Nova kartica", "lead": "Kratki opis — klikni i upiši.",
                  "points": ("Prva stavka — klikni i upiši", "Druga stavka"), "extra": (),
                  "price": "na upit", "unit": "", "year_price": "na upit", "year_unit": ""}

# the two cards the landing shipped with (the offer.dvorana.* /
# offer.individualno.* slots' defaults until 20.10.2026) and the plans they
# stand for, the first pricing each: the cards of the demo seed
# (scripts/seed_demo.py); the migration that made them rows carries its own
# copy. Their own price and unit are empty: a plan prices them (and since
# 21.10.2026 their yearly price too, its price.<plan>.year_* slots: their
# own year_price / year_unit are never printed).
GYM_CARD_EXAMPLES = (
    {"title": "Dvorana", "lead": "Grupni treninzi u Dubravi.",
     "points": ("Male grupe do 8 polaznika", "8, 12 ili 16 treninga mjesečno", "Termin rezerviraš u aplikaciji"),
     "extra": (), "price": "", "unit": "", "year_price": "na upit", "year_unit": "", "plans": "grupni"},
    {"title": "Individualno", "lead": "Trener samo za tebe.",
     # their prices are the line under the card's price (landing.html,
     # .price-note), so a bullet is free text
     "points": ("Rad 1:1, po dogovoru", "U dvoje ili troje", "Rehabilitacija"),
     "extra": (), "price": "", "unit": "", "year_price": "na upit", "year_unit": "",
     "plans": "individualni,poluindividualni,rehabilitacija"},
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
# 21.10.2026, price.<plan>.year_amount / .year_unit).
GYM_CARD_SLOTS: dict[str, Slot | ListSlot | FlagSlot] = {
    "title": Slot(GYM_CARD_BLANK["title"], CAP, "naziv"),
    "lead": Slot(GYM_CARD_BLANK["lead"], CAP, "podnaslov"),
    "points": ListSlot(GYM_CARD_BLANK["points"], CAP_ITEMS, CAP, "stavka"),
    "extra": ListSlot(GYM_CARD_BLANK["extra"], CAP_ITEMS, CAP, "dodatni tekst"),
    "price": Slot(GYM_CARD_BLANK["price"], CAP, "mjesečna cijena"),
    "unit": Slot(GYM_CARD_BLANK["unit"], CAP, "uz mjesečnu cijenu"),
    "year_price": Slot(GYM_CARD_BLANK["year_price"], CAP, "godišnja cijena"),
    "year_unit": Slot(GYM_CARD_BLANK["year_unit"], CAP, "uz godišnju cijenu"),
    "show": FlagSlot(True, "prikazano"),
}
# where a row keeps each text (its lists, the bullets and the extra lines,
# and the switch have setters of their own: db.set_gym_card_list, each list
# in the column its field names, and db.set_gym_card_shown)
GYM_CARD_COLUMNS = {"title": "title", "lead": "lead", "price": "price", "unit": "unit",
                    "year_price": "year_price", "year_unit": "year_unit"}

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
