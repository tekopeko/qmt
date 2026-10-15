"""Texts the trainer or owner may edit in place.

Each slot is a piece of copy on a public page with a character limit that its
box can take: at the limit the layout still holds at 360, 390, 900 and 1280px.
That is not a guess — tests/test_copy.py fills EVERY slot to its limit (with
words, and with one unbreakable word) and measures the pages, so a limit that
is too generous fails the suite. Defaults are the texts the templates shipped
with: nothing changes until someone edits.

Adding a slot is one line here plus `{{ c.t("the.key") }}` in the template
(see _copy.html). The tests pick it up by themselves: every slot must appear
on a page, and every page must still fit.

A ListSlot is a list of short texts the editor can add to and remove from, not
only retype — the bullets on the landing's offer cards. It is stored as ONE
site_copy row whose text is a JSON array of cleaned, non-empty strings; no row
means the default list. Its limits are a count (max_items) and a length per
item (max_chars), and the browser test fills every list to both at once.
Printed with `{{ c.points("the.key") }}`.
"""
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Slot:
    default: str
    max: int        # characters; whitespace is collapsed before counting
    label: str      # what the editor sees while editing


@dataclass(frozen=True)
class ListSlot:
    default: tuple[str, ...]
    max_items: int  # how many items the list may hold
    max_chars: int  # characters per item, counted as for Slot.max
    label: str      # the editor shows it with the item's number ("…: stavka 2")


# the online tiers' bullets: tier 1's own defaults, and placeholders for 2 and 3
ONLINE_POINTS = ("Program po tvojoj razini i cilju", "Video upute za svaku vježbu",
                 "Mjesečni Zoom poziv ili susret s trenerom")

SLOTS: dict[str, Slot | ListSlot] = {
    # ---- landing: hero ----
    "hero.kicker": Slot("Zagreb · Dubrava", 24, "Mala oznaka iznad naslova"),
    "hero.h1a": Slot("Kvaliteta pokreta", 18, "Naslov, bijeli red"),
    "hero.h1b": Slot("prije svega", 18, "Naslov, crveni red"),
    "hero.lead": Slot("Male grupe do 8 polaznika, individualni rad 1:1 i programi povratka nakon ozljede "
                      "— vođeni znanjem, ne trendovima.", 160, "Uvodni tekst"),
    # shown to a member without a bookable plan, under "Pogledaj cjenik"
    "hero.note": Slot("Nemaš aktivnu članarinu za treninge — cjenik ti pokazuje sve opcije.", 100,
                      "Napomena članu bez članarine"),
    # ---- landing: the photo card ----
    "stage.title": Slot("Dvorana u Dubravi", 20, "Naslov na fotografiji"),
    "stage.text": Slot("Jedan prostor za sve — grupni treninzi, individualni rad i rehabilitacija, "
                       "s trenerom koji te poznaje.", 110, "Tekst na fotografiji (nije na mobitelu)"),
    "stage.chip1": Slot("do 8 polaznika", 16, "Oznaka na fotografiji, lijeva"),
    "stage.chip2": Slot("07–20 h", 10, "Oznaka na fotografiji, desna"),
    # ---- landing: the offer ----
    "offer.kicker": Slot("Ponuda", 16, "Mala oznaka iznad ponude"),
    "offer.h2": Slot("Odaberi kako treniraš", 28, "Naslov ponude"),
    # three tiers of the online plan. Tier 1's monthly price is the online
    # plan's own (Stripe, else the reference price); every other price is text
    # until a plan exists for it. The "Mjesečno / Godišnje" switch under the
    # cards shows one price per card.
    "offer.online.title": Slot("QMove START", 14, "Online 1: naziv"),
    "offer.online.lead": Slot("Treniraj gdje god jesi.", 48, "Online 1: podnaslov"),
    "offer.online.points": ListSlot(ONLINE_POINTS, 6, 44, "Online 1: stavka"),
    "offer.online.year_price": Slot("na upit", 9, "Online 1: godišnja cijena"),
    "offer.online.year_unit": Slot("", 11, "Online 1: uz godišnju cijenu"),
    "offer.online2.title": Slot("QMove PRO", 14, "Online 2: naziv"),
    "offer.online2.lead": Slot("Treniraj gdje god jesi.", 48, "Online 2: podnaslov"),
    "offer.online2.points": ListSlot(ONLINE_POINTS, 6, 44, "Online 2: stavka"),
    "offer.online2.price": Slot("na upit", 9, "Online 2: mjesečna cijena"),
    "offer.online2.unit": Slot("", 11, "Online 2: uz mjesečnu cijenu"),
    "offer.online2.year_price": Slot("na upit", 9, "Online 2: godišnja cijena"),
    "offer.online2.year_unit": Slot("", 11, "Online 2: uz godišnju cijenu"),
    "offer.online3.title": Slot("QMove ELITE", 14, "Online 3: naziv"),
    "offer.online3.lead": Slot("Treniraj gdje god jesi.", 48, "Online 3: podnaslov"),
    "offer.online3.points": ListSlot(ONLINE_POINTS, 6, 44, "Online 3: stavka"),
    "offer.online3.price": Slot("na upit", 9, "Online 3: mjesečna cijena"),
    "offer.online3.unit": Slot("", 11, "Online 3: uz mjesečnu cijenu"),
    "offer.online3.year_price": Slot("na upit", 9, "Online 3: godišnja cijena"),
    "offer.online3.year_unit": Slot("", 11, "Online 3: uz godišnju cijenu"),
    # ---- landing: the gym, a quieter section below the online tiers ----
    # Both cards are tiers too: the monthly price is the plan's own, the yearly
    # one text until a plan exists for it; the gym's own "Mjesečno / Godišnje"
    # switch is one choice with the tiers'.
    "gym.kicker": Slot("Dvorana", 16, "Mala oznaka iznad dvorane"),
    "gym.h2": Slot("Treninzi u dvorani", 28, "Naslov: dvorana"),
    "offer.dvorana.title": Slot("Dvorana", 14, "Dvorana: naziv"),
    "offer.dvorana.lead": Slot("Grupni treninzi u Dubravi.", 48, "Dvorana: podnaslov"),
    "offer.dvorana.points": ListSlot(("Male grupe do 8 polaznika", "8, 12 ili 16 treninga mjesečno",
                                      "Termin rezerviraš u aplikaciji"), 6, 44, "Dvorana: stavka"),
    "offer.dvorana.year_price": Slot("na upit", 9, "Dvorana: godišnja cijena"),
    "offer.dvorana.year_unit": Slot("", 11, "Dvorana: uz godišnju cijenu"),
    "offer.individualno.title": Slot("Individualno", 14, "Individualno: naziv"),
    "offer.individualno.lead": Slot("Trener samo za tebe.", 48, "Individualno: podnaslov"),
    # the prices of these used to follow the bullets; they are one line under
    # the card's price now (landing.html, .price-note), so a bullet is free text
    "offer.individualno.points": ListSlot(("Rad 1:1, po dogovoru", "U dvoje ili troje", "Rehabilitacija"),
                                          6, 44, "Individualno: stavka"),
    "offer.individualno.year_price": Slot("na upit", 9, "Individualno: godišnja cijena"),
    "offer.individualno.year_unit": Slot("", 11, "Individualno: uz godišnju cijenu"),
    "offer.addon": Slot("MojiMakrosi prehrana", 26, "Naziv dodatka za prehranu"),
    # ---- landing: info ----
    "info.hours.h": Slot("Radno vrijeme", 16, "Naslov: radno vrijeme"),
    "info.hours.d1": Slot("pon · sri · čet · pet", 22, "Radno vrijeme, dani 1"),
    "info.hours.t1": Slot("07:00 – 20:00", 22, "Radno vrijeme, sati 1"),
    "info.hours.d2": Slot("uto", 22, "Radno vrijeme, dani 2"),
    "info.hours.t2": Slot("individualni termini", 22, "Radno vrijeme, sati 2"),
    "info.hours.d3": Slot("sub · ned", 22, "Radno vrijeme, dani 3"),
    "info.hours.t3": Slot("zatvoreno", 22, "Radno vrijeme, sati 3"),
    "info.where.h": Slot("Gdje smo", 16, "Naslov: adresa"),
    "info.contact.h": Slot("Kontakt", 16, "Naslov: kontakt"),
    "footer": Slot("© Quality Movement Training, Zagreb", 60, "Podnožje"),
    # ---- cjenik (members) ----
    "cjenik.hint": Slot("Svaka usluga je zasebna članarina — plaća se mjesečno, sljedeća uplata dospijeva "
                        "mjesec dana nakon zadnje.", 200, "Cjenik: uvodna rečenica"),
    "cjenik.grupni": Slot("Satni termini u malim grupama do 8 polaznika — rezerviraš u rasporedu.", 90, "Cjenik: grupni"),
    "cjenik.individualni": Slot("Rad 1:1 s trenerom, termini po dogovoru.", 90, "Cjenik: individualni"),
    "cjenik.poluindividualni": Slot("Trening u dvoje ili troje — pola puta između grupe i 1:1.", 90, "Cjenik: poluindividualni"),
    "cjenik.rehabilitacija": Slot("Programi povratka nakon ozljede, 1:1 stručno vođeni.", 90, "Cjenik: rehabilitacija"),
    "cjenik.online": Slot("Programi po tvojoj razini i cilju, s video uputama — gdje god jesi.", 90, "Cjenik: online"),
    "cjenik.prehrana": Slot("Vođenje prehrane uz aplikaciju MojiMakrosi i zdrave recepte.", 90, "Cjenik: prehrana"),
    "cjenik.note": Slot("Za upis se javi treneru u dvorani.", 60, "Cjenik: napomena uz plan koji nemaš"),
    # ---- prehrana ----
    "prehrana.h1": Slot("Prehrana ide uz trening", 36, "Prehrana: naslov"),
    "prehrana.note": Slot("Pristup je na poziv — javi se treneru ako se ne možeš registrirati.", 120, "Prehrana: napomena"),
}


def clean(text: str) -> str:
    """What gets stored: whitespace collapsed to single spaces, no newlines —
    every slot is one run of text, the box decides where it wraps."""
    return " ".join(text.split())


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
