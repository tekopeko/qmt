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

A ListSlot is a list of short texts the editor can add to and remove from, not
only retype — the bullets on the landing's offer cards. It is stored as ONE
site_copy row whose text is a JSON array of cleaned, non-empty strings; no row
means the default list. Its caps are a count (max_items) and a length per item
(max_chars). Printed with `{{ c.points("the.key") }}`.

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
SLOTS is a flag or a photo since; the types stay for the announcements, and
for any slot that is one.

The gym's cards (#dvorana, under the online tiers) went the same way on
20.10.2026: Dvorana and Individualno were two fixed sets of slots
(offer.dvorana.* / offer.individualno.*), and the gym owner adds his own
offers beside them now, hides and deletes them, up to eight
(models.GymCard, db.py). The editor names their fields with virtual keys,
dvorana.<id>.<field>, on POST /copy/{key}: GYM_CARD_SLOTS below says how
each is edited (a text a Slot, the bullets a ListSlot, the switch a
FlagSlot; no photo) and GYM_CARD_COLUMNS where a row keeps a text.

The price slots (18.10.2026) are plain Slots with one job: every price the
site shows, whether or not Stripe is configured (app.py, reference_prices
and _offer_prices). No Stripe Price overrides them (the owner's call, the
same day: his friend's numbers are the truth); Stripe's Prices are to be
aligned to them in one place when card payments return, and until then only
the tier picker inside the checkout forms (_tiers.html) and a subscriber's
tier switch show a Stripe amount, the one the card is charged. Per plan an
amount, a unit and a note (price.<plan>.amount / .unit / .note; prehrana has
no note, its hint is the add-on's two amounts), and the MojiMakrosi add-on's
amount beside online and beside the dvorana (addon.online / addon.dvorana),
so the gym owner retypes a price the way he retypes any text. The amount is
text, printed as typed with " €" after it ("60–80", "od 30"). Their
defaults are REFERENCE_PRICES and MOJIMAKROSI_ADDON below, the shop's
numbers. Most of them print on two pages, the landing and /moja-clanarina,
the only slots that do: one number, one slot, so an edit shows wherever
that number does.
"""
import json
import re
from dataclasses import dataclass

from .models import ONLINE_TIER_SLOTS, PLAN_LABELS

CAP = 2000       # characters per text or list item, counted after clean()
CAP_ITEMS = 12   # items per list


@dataclass(frozen=True)
class Slot:
    default: str
    max: int        # characters, counted after clean(); CAP for every slot
    label: str      # what the editor sees while editing


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
# Online is a monthly plan. (amount text, unit, note): a None note is an
# empty note slot to fill, a row with no third item (prehrana) gets none.
# Since 18.10.2026 they are the defaults of the price slots (price.<plan>.*,
# in SLOTS below), which the gym owner edits in place: the pages print the
# slots and nothing else, a Stripe Price neither (app.py, reference_prices),
# so this table is what they say until someone edits.
REFERENCE_PRICES = {
    "grupni": ("60–80", "/ paket", "8, 12 ili 16 treninga"),
    "individualni": ("35", "/ trening", None),
    "poluindividualni": ("25", "/ trening", None),
    "rehabilitacija": ("od 30", "/ tretman", "paketi od 5 i 10 tretmana"),
    "online": ("50", "/ mjesečno", None),
    # no note: the hint under its price is the add-on's two amounts, the
    # addon.* slots (_plan_price.html), so each number is typed in one place
    "prehrana": ("od 3", "/ mjesečno"),
}

# MojiMakrosi (the prehrana app) as a monthly add-on, as the owner set it on
# 5.10.2026: cheaper beside a plan in the dvorana, dearer for online-only
# clients. The defaults of the addon.* slots (below), which the prehrana
# plan's hint on /moja-clanarina prints ("3 € uz dvoranu, 5 € uz online",
# _plan_price.html), and the landing's online tiers the online one (the gym's
# cards carry no add-on line since 20.10.2026): one slot per number.
MOJIMAKROSI_ADDON = {"dvorana": "3", "online": "5"}

SLOTS: dict[str, Slot | ListSlot | RowsSlot | FlagSlot | ImageSlot] = {
    # ---- landing: hero ----
    "hero.kicker": Slot("Zagreb · Dubrava", CAP, "Mala oznaka iznad naslova"),
    "hero.h1a": Slot("Kvaliteta pokreta", CAP, "Naslov, bijeli red"),
    "hero.h1b": Slot("prije svega", CAP, "Naslov, crveni red"),
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
    # Each tier's MojiMakrosi line is its own words around the one amount
    # (addon.online, below): .addon before it, .addon_unit after it
    # (20.10.2026, the owner: "a similar treatment of the three QMOVE
    # tabs"; one offer.addon for all three until then).
    "offer.online.title": Slot("QMove START", CAP, "Online 1: naziv"),
    "offer.online.lead": Slot("Treniraj gdje god jesi.", CAP, "Online 1: podnaslov"),
    "offer.online.points": ListSlot(ONLINE_POINTS, CAP_ITEMS, CAP, "Online 1: stavka"),
    "offer.online.addon": Slot("MojiMakrosi prehrana", CAP, "Online 1: dodatak za prehranu"),
    "offer.online.addon_unit": Slot("€ / mjesečno", CAP, "Online 1: uz cijenu dodatka"),
    "offer.online.year_price": Slot("na upit", CAP, "Online 1: godišnja cijena"),
    "offer.online.year_unit": Slot("", CAP, "Online 1: uz godišnju cijenu"),
    "offer.online2.title": Slot("QMove PRO", CAP, "Online 2: naziv"),
    "offer.online2.lead": Slot("Treniraj gdje god jesi.", CAP, "Online 2: podnaslov"),
    "offer.online2.points": ListSlot(ONLINE_POINTS, CAP_ITEMS, CAP, "Online 2: stavka"),
    "offer.online2.addon": Slot("MojiMakrosi prehrana", CAP, "Online 2: dodatak za prehranu"),
    "offer.online2.addon_unit": Slot("€ / mjesečno", CAP, "Online 2: uz cijenu dodatka"),
    "offer.online2.price": Slot("na upit", CAP, "Online 2: mjesečna cijena"),
    "offer.online2.unit": Slot("", CAP, "Online 2: uz mjesečnu cijenu"),
    "offer.online2.year_price": Slot("na upit", CAP, "Online 2: godišnja cijena"),
    "offer.online2.year_unit": Slot("", CAP, "Online 2: uz godišnju cijenu"),
    "offer.online3.title": Slot("QMove ELITE", CAP, "Online 3: naziv"),
    "offer.online3.lead": Slot("Treniraj gdje god jesi.", CAP, "Online 3: podnaslov"),
    "offer.online3.points": ListSlot(ONLINE_POINTS, CAP_ITEMS, CAP, "Online 3: stavka"),
    "offer.online3.addon": Slot("MojiMakrosi prehrana", CAP, "Online 3: dodatak za prehranu"),
    "offer.online3.addon_unit": Slot("€ / mjesečno", CAP, "Online 3: uz cijenu dodatka"),
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
    # Per plan its amount, unit and note, the defaults REFERENCE_PRICES above
    # (prehrana: no note): the landing prints the amount and the unit on a
    # card (Individualno's muted line two more plans'), /moja-clanarina all
    # three, with or without a Stripe Price for the plan (app.py, _offer_prices).
    **{f"price.{plan}.{part}": Slot(text or "", CAP, f"Cijena · {plan}: {label}")
       for plan, row in REFERENCE_PRICES.items()
       for part, label, text in zip(("amount", "unit", "note"), ("iznos", "jedinica", "napomena"), row)},
    # the words before a plan's price in a gym card's line of its other
    # plans (Individualno's "u dvoje ili troje 25 € / trening ·
    # rehabilitacija od 30 € / tretman", landing.html, plan_note), free
    # text the gym owner retypes there since 20.10.2026; the number stays
    # the plan's amount slot. Only these two: they are the plans a card has
    # after its first (GYM_CARD_EXAMPLES), and nothing edits a card's plans.
    "price.poluindividualni.word": Slot("u dvoje ili troje", CAP, "Cijena · poluindividualni: tekst ispred iznosa"),
    "price.rehabilitacija.word": Slot("rehabilitacija", CAP, "Cijena · rehabilitacija: tekst ispred iznosa"),
    # the MojiMakrosi add-on's amount in €: online beside the landing's online
    # tiers, both in the prehrana plan's hint (the gym's cards print none)
    "addon.online": Slot(MOJIMAKROSI_ADDON["online"], CAP, "MojiMakrosi dodatak uz online (€)"),
    "addon.dvorana": Slot(MOJIMAKROSI_ADDON["dvorana"], CAP, "MojiMakrosi dodatak uz dvoranu (€)"),
    # ---- landing: aktualno: rows since 18.10.2026, not slots (ANNOUNCEMENT_* below) ----
    # ---- landing: info ----
    "info.hours.h": Slot("Radno vrijeme", CAP, "Naslov: radno vrijeme"),
    # the hours as rows (20.10.2026; six fixed slots info.hours.d1 … t3
    # until migration 1a7c144b582a folded them in): days and hours per row
    "info.hours.rows": RowsSlot((("pon · sri · čet · pet", "07:00 – 20:00"), ("uto", "individualni termini"),
                                 ("sub · ned", "zatvoreno")), CAP_ITEMS, CAP, "Radno vrijeme", ("dani", "sati")),
    "info.where.h": Slot("Gdje smo", CAP, "Naslov: adresa"),
    "info.contact.h": Slot("Kontakt", CAP, "Naslov: kontakt"),
    "footer": Slot("© Quality Movement Training, Zagreb", CAP, "Podnožje"),
    # ---- cjenik (members) ----
    "cjenik.hint": Slot("Svaka usluga je zasebna članarina — plaća se mjesečno, sljedeća uplata dospijeva "
                        "mjesec dana nakon zadnje.", CAP, "Cjenik: uvodna rečenica"),
    "cjenik.grupni": Slot("Satni termini u malim grupama do 8 polaznika — rezerviraš u rasporedu.", CAP, "Cjenik: grupni"),
    "cjenik.individualni": Slot("Rad 1:1 s trenerom, termini po dogovoru.", CAP, "Cjenik: individualni"),
    "cjenik.poluindividualni": Slot("Trening u dvoje ili troje — pola puta između grupe i 1:1.", CAP, "Cjenik: poluindividualni"),
    "cjenik.rehabilitacija": Slot("Programi povratka nakon ozljede, 1:1 stručno vođeni.", CAP, "Cjenik: rehabilitacija"),
    "cjenik.online": Slot("Programi po tvojoj razini i cilju, s video uputama — gdje god jesi.", CAP, "Cjenik: online"),
    "cjenik.prehrana": Slot("Vođenje prehrane uz aplikaciju MojiMakrosi i zdrave recepte.", CAP, "Cjenik: prehrana"),
    "cjenik.note": Slot("Za upis se javi treneru u dvorani.", CAP, "Cjenik: napomena uz plan koji nemaš"),
    # ---- moja članarina (18.10.2026): the rest of the page's own words ----
    # The lead, the plans' texts and the prices are the cjenik.* and price.*
    # slots above. Not slots: the sentences built around a date or a number
    # (the status box, the chips, the facts and their captions) and the
    # ledger's headers.
    "clanarina.h.plans": Slot("Tvoji planovi", CAP, "Članarina: naslov · Tvoji planovi"),
    "clanarina.h.add": Slot("Dodaj plan", CAP, "Članarina: naslov · Dodaj plan"),
    "clanarina.h.bills": Slot("Računi", CAP, "Članarina: naslov · Računi"),
    # the card a member without a plan sees instead of Tvoji planovi; an
    # editor sees it too, under a caption, so its two sentences are in reach
    "clanarina.none.title": Slot("Nemaš aktivnu članarinu — bez nje rezervacija nije moguća.", CAP,
                                 "Članarina: bez plana, prva rečenica"),
    "clanarina.none.text": Slot("Za upis se javi treneru u dvorani — plaćanje gotovinom ili karticom.", CAP,
                                "Članarina: bez plana, druga rečenica"),
    # under "Pretplati se karticom", which shows only while Stripe is
    # configured; an editor gets it regardless (moja_clanarina.html)
    "clanarina.card_hint": Slot("Mjesečno, otkazivo bilo kad. Ili gotovinom u dvorani.", CAP,
                                "Članarina: uz plaćanje karticom"),
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
# and how each is edited: a text as a Slot, its default the placeholder an
# empty save (or Zadano) puts back; the switch as a FlagSlot, on by default;
# the photo as an ImageSlot. The label is the field's word in the editor's
# bar, after the card's number ("Najava 2: naslov", landing.html).
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

# a new card ("+ Dodaj karticu"): these placeholders to retype, shown, no plans
GYM_CARD_BLANK = {"title": "Nova kartica", "lead": "Kratki opis — klikni i upiši.",
                  "points": ("Prva stavka — klikni i upiši", "Druga stavka"),
                  "price": "na upit", "unit": "", "year_price": "na upit", "year_unit": ""}

# the two cards the landing shipped with (the offer.dvorana.* /
# offer.individualno.* slots' defaults until 20.10.2026) and the plans they
# stand for, the first pricing each: the cards of the demo seed
# (scripts/seed_demo.py); the migration that made them rows carries its own
# copy. Their own price and unit are empty: a plan prices them.
GYM_CARD_EXAMPLES = (
    {"title": "Dvorana", "lead": "Grupni treninzi u Dubravi.",
     "points": ("Male grupe do 8 polaznika", "8, 12 ili 16 treninga mjesečno", "Termin rezerviraš u aplikaciji"),
     "price": "", "unit": "", "year_price": "na upit", "year_unit": "", "plans": "grupni"},
    {"title": "Individualno", "lead": "Trener samo za tebe.",
     # their prices are the line under the card's price (landing.html,
     # .price-note), so a bullet is free text
     "points": ("Rad 1:1, po dogovoru", "U dvoje ili troje", "Rehabilitacija"),
     "price": "", "unit": "", "year_price": "na upit", "year_unit": "",
     "plans": "individualni,poluindividualni,rehabilitacija"},
)

# A card's fields as the editor's virtual keys name them, dvorana.<id>.<field>,
# and how each is edited: a text as a Slot, its default the placeholder an
# empty save (or Zadano) puts back; the bullets as a ListSlot (Zadano puts
# the new card's two back); the switch as a FlagSlot, on by default. The
# label is the field's word in the editor's bar, after the card's number
# ("Kartica 2: naziv", landing.html). price / unit print only on a card
# that stands for no plan: a plan's card prints the plan's price slots.
GYM_CARD_SLOTS: dict[str, Slot | ListSlot | FlagSlot] = {
    "title": Slot(GYM_CARD_BLANK["title"], CAP, "naziv"),
    "lead": Slot(GYM_CARD_BLANK["lead"], CAP, "podnaslov"),
    "points": ListSlot(GYM_CARD_BLANK["points"], CAP_ITEMS, CAP, "stavka"),
    "price": Slot(GYM_CARD_BLANK["price"], CAP, "mjesečna cijena"),
    "unit": Slot(GYM_CARD_BLANK["unit"], CAP, "uz mjesečnu cijenu"),
    "year_price": Slot(GYM_CARD_BLANK["year_price"], CAP, "godišnja cijena"),
    "year_unit": Slot(GYM_CARD_BLANK["year_unit"], CAP, "uz godišnju cijenu"),
    "show": FlagSlot(True, "prikazano"),
}
# where a row keeps each text (the bullets and the switch have setters of
# their own: db.set_gym_card_points, db.set_gym_card_shown)
GYM_CARD_COLUMNS = {"title": "title", "lead": "lead", "price": "price", "unit": "unit",
                    "year_price": "year_price", "year_unit": "year_unit"}


def clean(text: str) -> str:
    """What gets stored. Line breaks are kept (they print: span.t in
    base.html). Within a line every run of spaces and tabs becomes one space
    and the line is trimmed; blank lines at the start and the end go, and
    three or more line breaks in a row become two (one empty line at most).
    An empty result means nothing was written: the default comes back, or a
    list item is removed (POST /copy/{key}); a row's cell is the exception,
    it stays empty (RowsSlot)."""
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
    return {tier: texts.get(f"{slot}.title", SLOTS[f"{slot}.title"].default)
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
