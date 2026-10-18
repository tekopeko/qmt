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

A FlagSlot is a switch, not a text: whether a part of a page shows at all —
the hero's two announcements for the month (#aktualno), each one the owner
switches off when it is over. It is stored like any slot, as the text "on" or
"off"; no row means the default. Read with `copy_flag("the.key", copy_texts)`
(flag_on below). In edit mode the editor flips it with a toggle (.ed-flag,
base.html); a visitor never gets the markup of what a flag hides.

An ImageSlot is a photo, not a text: the background of one of the hero's
announcements, the way Shape's photo cards carry theirs. It is stored like any
slot, its text the stored file's name ("aktualno-1-3f9a1c….jpg"); no row means
no photo, a plain card. Only POST /copy/{key}/slika writes it: the upload is
turned upright, shrunk to a 1600px JPEG and kept where programme media is kept
(storage.py: R2 on prod), and reset=1 on POST /copy/{key} removes file and row.
Read with `copy_image("the.key", copy_texts)` (image_name below). The photo is
public, as the landing is: GET /slika/{name} serves the names an ImageSlot
holds and nothing else. In edit mode the editor picks a file with "Dodaj sliku"
/ "Promijeni sliku" and removes it with "Ukloni sliku" (.ed-img, base.html).

The price slots (18.10.2026) are plain Slots with one job: the reference
prices, what the site says a plan costs until a Stripe Price exists for it
(app.py, reference_prices and _offer_prices: a Stripe Price always wins, it
is what a subscription charges). Per plan an amount, a unit and a note
(price.<plan>.amount / .unit / .note), and the MojiMakrosi add-on's amount
beside online and beside the dvorana (addon.online / addon.dvorana), so the
gym owner retypes a price the way he retypes any text. The amount is text,
printed as typed with " €" after it ("60–80", "od 30"). Their defaults are
REFERENCE_PRICES and MOJIMAKROSI_ADDON below, the shop's numbers. Most of
them print on two pages, the landing and /moja-clanarina, the only slots
that do.
"""
import json
import re
from dataclasses import dataclass

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
class FlagSlot:
    default: bool   # True: shown until someone switches it off
    label: str      # what the editor's toggle stands for ("Događanje 1: prikazano")


@dataclass(frozen=True)
class ImageSlot:
    label: str      # what the editor's bar names while a photo goes up ("Događanje 1: slika")


# the online tiers' bullets: tier 1's own defaults, and placeholders for 2 and 3
ONLINE_POINTS = ("Program po tvojoj razini i cilju", "Video upute za svaku vježbu",
                 "Mjesečni Zoom poziv ili susret s trenerom")

# Reference prices from the owner's Shopify shop (read 6.9.2026): what the
# site says a plan costs until a Stripe Price exists for it; Stripe always
# wins. Units are the shop's own: most of the business is per trening / per
# paket, only Online is a monthly plan. (amount text, unit, note). Since
# 18.10.2026 they are the defaults of the price slots (price.<plan>.*, in
# SLOTS below), which the gym owner edits in place: the pages print the
# slots (app.py, reference_prices), so this table is what they say until
# someone edits.
REFERENCE_PRICES = {
    "grupni": ("60–80", "/ paket", "8, 12 ili 16 treninga"),
    "individualni": ("35", "/ trening", None),
    "poluindividualni": ("25", "/ trening", None),
    "rehabilitacija": ("od 30", "/ tretman", "paketi od 5 i 10 tretmana"),
    "online": ("50", "/ mjesečno", None),
    "prehrana": ("od 3", "/ mjesečno", "3 € uz dvoranu, 5 € uz online"),
}

# MojiMakrosi (the prehrana app) as a monthly add-on, as the owner set it on
# 5.10.2026: cheaper beside a plan in the dvorana, dearer for online-only
# clients. The defaults of the addon.* slots (below), which the landing's
# offer cards print; REFERENCE_PRICES["prehrana"]'s note says the same thing
# on /moja-clanarina, in a text of its own.
MOJIMAKROSI_ADDON = {"dvorana": "3", "online": "5"}

SLOTS: dict[str, Slot | ListSlot | FlagSlot | ImageSlot] = {
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
    # plan's own (Stripe, else the reference price); every other price is text
    # until a plan exists for it. The "Mjesečno / Godišnje" switch under the
    # cards shows one price per card.
    "offer.online.title": Slot("QMove START", CAP, "Online 1: naziv"),
    "offer.online.lead": Slot("Treniraj gdje god jesi.", CAP, "Online 1: podnaslov"),
    "offer.online.points": ListSlot(ONLINE_POINTS, CAP_ITEMS, CAP, "Online 1: stavka"),
    "offer.online.year_price": Slot("na upit", CAP, "Online 1: godišnja cijena"),
    "offer.online.year_unit": Slot("", CAP, "Online 1: uz godišnju cijenu"),
    "offer.online2.title": Slot("QMove PRO", CAP, "Online 2: naziv"),
    "offer.online2.lead": Slot("Treniraj gdje god jesi.", CAP, "Online 2: podnaslov"),
    "offer.online2.points": ListSlot(ONLINE_POINTS, CAP_ITEMS, CAP, "Online 2: stavka"),
    "offer.online2.price": Slot("na upit", CAP, "Online 2: mjesečna cijena"),
    "offer.online2.unit": Slot("", CAP, "Online 2: uz mjesečnu cijenu"),
    "offer.online2.year_price": Slot("na upit", CAP, "Online 2: godišnja cijena"),
    "offer.online2.year_unit": Slot("", CAP, "Online 2: uz godišnju cijenu"),
    "offer.online3.title": Slot("QMove ELITE", CAP, "Online 3: naziv"),
    "offer.online3.lead": Slot("Treniraj gdje god jesi.", CAP, "Online 3: podnaslov"),
    "offer.online3.points": ListSlot(ONLINE_POINTS, CAP_ITEMS, CAP, "Online 3: stavka"),
    "offer.online3.price": Slot("na upit", CAP, "Online 3: mjesečna cijena"),
    "offer.online3.unit": Slot("", CAP, "Online 3: uz mjesečnu cijenu"),
    "offer.online3.year_price": Slot("na upit", CAP, "Online 3: godišnja cijena"),
    "offer.online3.year_unit": Slot("", CAP, "Online 3: uz godišnju cijenu"),
    # ---- landing: the gym, a quieter section below the online tiers ----
    # Both cards are tiers too: the monthly price is the plan's own, the yearly
    # one text until a plan exists for it; the gym's own "Mjesečno / Godišnje"
    # switch is one choice with the tiers'.
    "gym.kicker": Slot("Dvorana", CAP, "Mala oznaka iznad dvorane"),
    "gym.h2": Slot("Treninzi u dvorani", CAP, "Naslov: dvorana"),
    "offer.dvorana.title": Slot("Dvorana", CAP, "Dvorana: naziv"),
    "offer.dvorana.lead": Slot("Grupni treninzi u Dubravi.", CAP, "Dvorana: podnaslov"),
    "offer.dvorana.points": ListSlot(("Male grupe do 8 polaznika", "8, 12 ili 16 treninga mjesečno",
                                      "Termin rezerviraš u aplikaciji"), CAP_ITEMS, CAP, "Dvorana: stavka"),
    "offer.dvorana.year_price": Slot("na upit", CAP, "Dvorana: godišnja cijena"),
    "offer.dvorana.year_unit": Slot("", CAP, "Dvorana: uz godišnju cijenu"),
    "offer.individualno.title": Slot("Individualno", CAP, "Individualno: naziv"),
    "offer.individualno.lead": Slot("Trener samo za tebe.", CAP, "Individualno: podnaslov"),
    # the prices of these used to follow the bullets; they are one line under
    # the card's price now (landing.html, .price-note), so a bullet is free text
    "offer.individualno.points": ListSlot(("Rad 1:1, po dogovoru", "U dvoje ili troje", "Rehabilitacija"),
                                          CAP_ITEMS, CAP, "Individualno: stavka"),
    "offer.individualno.year_price": Slot("na upit", CAP, "Individualno: godišnja cijena"),
    "offer.individualno.year_unit": Slot("", CAP, "Individualno: uz godišnju cijenu"),
    "offer.addon": Slot("MojiMakrosi prehrana", CAP, "Naziv dodatka za prehranu"),
    # ---- prices: the reference prices, what the site says until a Stripe Price exists ----
    # Per plan its amount, unit and note, the defaults REFERENCE_PRICES above:
    # the landing prints the amount and the unit on a card (Individualno's
    # muted line two more plans'), /moja-clanarina all three. A plan with a
    # Stripe Price prints that instead, not editable (app.py, _offer_prices).
    **{f"price.{plan}.{part}": Slot(text or "", CAP, f"Cijena · {plan}: {label}")
       for plan, row in REFERENCE_PRICES.items()
       for part, label, text in zip(("amount", "unit", "note"), ("iznos", "jedinica", "napomena"), row)},
    # the MojiMakrosi add-on's amount in €: beside the online tiers, beside the gym's cards
    "addon.online": Slot(MOJIMAKROSI_ADDON["online"], CAP, "MojiMakrosi dodatak uz online (€)"),
    "addon.dvorana": Slot(MOJIMAKROSI_ADDON["dvorana"], CAP, "MojiMakrosi dodatak uz dvoranu (€)"),
    # ---- landing: aktualno, in the hero between the headline and the photo ----
    # The owner's announcements for the month (a new group, a course): two
    # strips, the defaults are examples to retype. Each one is switched off in
    # edit mode when it is over (FlagSlot); a hidden strip is not on a
    # visitor's page at all, and with both hidden neither is their box. Each
    # one may carry a photo behind it (ImageSlot; no row: a plain card). The
    # strip's link always leads to the contact (/#kontakt).
    "event1.show": FlagSlot(True, "Događanje 1: prikazano"),
    "event1.image": ImageSlot("Događanje 1: slika"),
    "event1.tag": Slot("Novo", CAP, "Događanje 1: oznaka"),
    "event1.title": Slot("Treninzi za penziće", CAP, "Događanje 1: naslov"),
    "event1.when": Slot("Utorkom i četvrtkom u 10:00", CAP, "Događanje 1: termin"),
    "event1.text": Slot("Lagani grupni treninzi za zlatne godine: snaga, ravnoteža i pokretljivost u ugodnom "
                        "tempu, uz stručno vodstvo. Prijave u dvorani ili porukom.", CAP, "Događanje 1: tekst"),
    "event1.cta": Slot("Javi nam se", CAP, "Događanje 1: gumb"),
    "event2.show": FlagSlot(True, "Događanje 2: prikazano"),
    "event2.image": ImageSlot("Događanje 2: slika"),
    "event2.tag": Slot("Nova grupa", CAP, "Događanje 2: oznaka"),
    "event2.title": Slot("Pilates za cure", CAP, "Događanje 2: naslov"),
    "event2.when": Slot("Srijedom u 18:00", CAP, "Događanje 2: termin"),
    "event2.text": Slot("Pilates u maloj grupi: jezgra, držanje i opuštanje, za sve razine. Prijave u tijeku.",
                        CAP, "Događanje 2: tekst"),
    "event2.cta": Slot("Javi nam se", CAP, "Događanje 2: gumb"),
    # ---- landing: info ----
    "info.hours.h": Slot("Radno vrijeme", CAP, "Naslov: radno vrijeme"),
    "info.hours.d1": Slot("pon · sri · čet · pet", CAP, "Radno vrijeme, dani 1"),
    "info.hours.t1": Slot("07:00 – 20:00", CAP, "Radno vrijeme, sati 1"),
    "info.hours.d2": Slot("uto", CAP, "Radno vrijeme, dani 2"),
    "info.hours.t2": Slot("individualni termini", CAP, "Radno vrijeme, sati 2"),
    "info.hours.d3": Slot("sub · ned", CAP, "Radno vrijeme, dani 3"),
    "info.hours.t3": Slot("zatvoreno", CAP, "Radno vrijeme, sati 3"),
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
    # ---- prehrana ----
    "prehrana.h1": Slot("Prehrana ide uz trening", CAP, "Prehrana: naslov"),
    "prehrana.note": Slot("Pristup je na poziv — javi se treneru ako se ne možeš registrirati.", CAP, "Prehrana: napomena"),
}


def clean(text: str) -> str:
    """What gets stored. Line breaks are kept (they print: span.t in
    base.html). Within a line every run of spaces and tabs becomes one space
    and the line is trimmed; blank lines at the start and the end go, and
    three or more line breaks in a row become two (one empty line at most).
    An empty result means nothing was written: the default comes back, or a
    list item is removed (POST /copy/{key})."""
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


def flag_on(key: str, texts: dict[str, str]) -> bool:
    """Whether flag slot `key` is on, given the edited texts
    (db.copy_texts()): a stored "on" or "off", else the default (no row, or a
    row that is neither). Templates call it as copy_flag (landing.html)."""
    stored = texts.get(key)
    if stored in ("on", "off"):
        return stored == "on"
    return SLOTS[key].default


def image_name(key: str, texts: dict[str, str]) -> str | None:
    """The stored photo's file name for image slot `key`, given the edited
    texts (db.copy_texts()), or None: no row, or a row that is empty or names
    a path rather than a file ("/", "\\" or ".." in it), which is never let
    near storage. Templates call it as copy_image (landing.html)."""
    name = texts.get(key)
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    return name
