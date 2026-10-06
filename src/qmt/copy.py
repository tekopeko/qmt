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
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Slot:
    default: str
    max: int        # characters; whitespace is collapsed before counting
    label: str      # what the editor sees while editing


SLOTS: dict[str, Slot] = {
    # ---- landing: hero ----
    "hero.kicker": Slot("Zagreb · Dubrava", 24, "Mala oznaka iznad naslova"),
    "hero.h1a": Slot("Kvaliteta pokreta", 18, "Naslov, bijeli red"),
    "hero.h1b": Slot("prije svega", 18, "Naslov, crveni red"),
    "hero.lead": Slot("Male grupe do 8 polaznika, individualni rad 1:1 i programi povratka nakon ozljede "
                      "— vođeni znanjem, ne trendovima.", 160, "Uvodni tekst"),
    # ---- landing: the photo card ----
    "stage.title": Slot("Dvorana u Dubravi", 20, "Naslov na fotografiji"),
    "stage.text": Slot("Jedan prostor za sve — grupni treninzi, individualni rad i rehabilitacija, "
                       "s trenerom koji te poznaje.", 110, "Tekst na fotografiji (nije na mobitelu)"),
    "stage.chip1": Slot("do 8 polaznika", 16, "Oznaka na fotografiji, lijeva"),
    "stage.chip2": Slot("07–20 h", 10, "Oznaka na fotografiji, desna"),
    # ---- landing: the offer ----
    "offer.kicker": Slot("Ponuda", 16, "Mala oznaka iznad ponude"),
    "offer.h2": Slot("Odaberi kako treniraš", 28, "Naslov ponude"),
    "offer.online.title": Slot("Online", 14, "Kartica 1: naziv"),
    "offer.online.lead": Slot("Treniraj gdje god jesi.", 48, "Kartica 1: podnaslov"),
    "offer.online.p1": Slot("Program po tvojoj razini i cilju", 44, "Kartica 1: stavka 1"),
    "offer.online.p2": Slot("Video upute za svaku vježbu", 44, "Kartica 1: stavka 2"),
    "offer.online.p3": Slot("Mjesečni Zoom poziv ili susret s trenerom", 44, "Kartica 1: stavka 3"),
    "offer.dvorana.title": Slot("Dvorana", 14, "Kartica 2: naziv"),
    "offer.dvorana.lead": Slot("Grupni treninzi u Dubravi.", 48, "Kartica 2: podnaslov"),
    "offer.dvorana.p1": Slot("Male grupe do 8 polaznika", 44, "Kartica 2: stavka 1"),
    "offer.dvorana.p2": Slot("8, 12 ili 16 treninga mjesečno", 44, "Kartica 2: stavka 2"),
    "offer.dvorana.p3": Slot("Termin rezerviraš u aplikaciji", 44, "Kartica 2: stavka 3"),
    "offer.individualno.title": Slot("Individualno", 14, "Kartica 3: naziv"),
    "offer.individualno.lead": Slot("Trener samo za tebe.", 48, "Kartica 3: podnaslov"),
    "offer.individualno.p1": Slot("Rad 1:1, po dogovoru", 44, "Kartica 3: stavka 1"),
    # the price follows these two on the same line, so they get less room
    "offer.individualno.p2": Slot("U dvoje ili troje", 26, "Kartica 3: stavka 2 (cijena slijedi)"),
    "offer.individualno.p3": Slot("Rehabilitacija", 26, "Kartica 3: stavka 3 (cijena slijedi)"),
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
