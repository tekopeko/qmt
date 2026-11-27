"""The slash forms of the app's texts, resolved by the reader's sex.

27.11.2026, build 5 of roadmap/2026-11-26-gym-training-plan.md. The owner,
of his own karton's "Tvoji online treninzi i treninzi koje upišeš sam/a.":
"on login do we know the sex of the user and then to use the correct
grammar instead of" that. A text that does not know its reader says both
forms with a slash, "bio/la", "sam/a", "siguran/na", and the gym owner
retypes his own texts so too. A member may say his sex on the profile
(models.User.sex: "f", "m", NULL for not said), and gendered(text, sex) is
the text he reads: for no sex the text itself, character for character;
for "m" every slash form its masculine word, for "f" its feminine one.

What is stored, and what an editor edits, is always the text with its
slashes: this only reads. Where it is asked (app.py): every copy macro
(_copy.html) and copy_text, the flashes and the routes' refusals, the
upitnik's questions, the password-reset email.

A slash form is a whole token of the text (split at its white space):
letters, a slash and one of three endings, and nothing after the ending
but punctuation ("bio/la.", "sam/a,", "siguran/na?"). A token with
anything before its letters is none („bio/la” in quotes, "(sam/a)"), nor
one with a digit, a second slash or a letter after its ending: "24/7",
"km/h", "da/ne", "i/ili", "n/a", "/ paket", a path, an address. The rules:

- "/la" after a word that ends in "o" (the l-participle): masculine the
  word, feminine the word with that "o" made "la" (bio/la -> bila,
  stao/la -> stala, počeo/la -> počela), but for two closed groups, by the
  tables below: the fleeting a (every word that ends in "šao", došao ->
  došla, Dobrodošao -> Dobrodošla, and FLEETING_LA: mogao -> mogla) and the
  -jeti verbs (JETI: htio -> htjela);
- "/na" after a word that ends in "an": feminine the word with that "an"
  made "na" (siguran/na -> sigurna, spreman/na -> spremna);
- "/a" after a word of two letters or more: feminine the word and "a"
  (sam/a -> sama, usmjeren/a -> usmjerena, on/a -> ona), but for the
  adjectives with a fleeting a, by a table (FLEETING_A: siguran -> sigurna).

The word's own capitals stay ("Dobrodošao/la" -> "Dobrodošla", "BIO/LA" ->
"BILA"); what follows the ending stays as it was. A form the rules do not
cover ("tvoj/na": no "an" before "/na"; "spremio/na"; a word of one letter
before "/a") is left as it is, for either sex.

Two whole words are a slash form too (Fable's review, 27.11.2026: the gym
owner's guide says "Spreman/spremna za početak?" and "bio/bila"), in the
two cases where the second can be nothing but the first's feminine: an
l-participle and its feminine ("bio/bila", "došao/došla", "htio/htjela":
the "/la" rule's own answer), and an adjective of FLEETING_A and its
feminine ("spreman/spremna", "siguran/sigurna"). Nothing else that has a
whole word after its slash is touched: "dan/dana", "mjesec/mjeseca",
"tjedan/tjedana" are a noun's forms by number, which a rule of "the word
and an a" would take for a woman's.
"""

from __future__ import annotations

import os
import re

# The two closed groups of "/la" (the l-participle), whole words in lower
# case, the masculine -> the feminine. A word is matched whole, never by its
# ending ("dozvolio" is no "volio": dozvolila, not dozvoljela); so a prefixed
# form ("izrekao", "poželio") that wants its group's feminine is a line of
# its own. To add a word: its masculine and its feminine, both in lower case,
# in the group it belongs to (the capitals are the text's: "Rekao/la" gives
# "Rekla" from "rekao": "rekla").
#
# The fleeting a: the masculine has an "a" the feminine drops ("mogao" ->
# "mogla"). Every word that ends in "šao" is one by rule (FLEETING_SAO:
# došao, Dobrodošao, išao, našao, prošao), these by name.
FLEETING_LA = {
    "mogao": "mogla", "pomogao": "pomogla", "rekao": "rekla", "stigao": "stigla", "postigao": "postigla",
    "digao": "digla", "podigao": "podigla", "legao": "legla", "pekao": "pekla", "vukao": "vukla",
    "povukao": "povukla", "izvukao": "izvukla", "obukao": "obukla", "tukao": "tukla", "pobjegao": "pobjegla",
    "izrekao": "izrekla", "stekao": "stekla", "dotakao": "dotakla", "svukao": "svukla", "privukao": "privukla",
}
FLEETING_SAO = ("šao", "šla")
# The -jeti verbs: the feminine takes a j the masculine has not ("htio" ->
# "htjela", "vidio" -> "vidjela").
JETI = {
    "htio": "htjela", "volio": "voljela", "želio": "željela", "vidio": "vidjela", "živio": "živjela",
    "smio": "smjela", "uspio": "uspjela", "razumio": "razumjela", "trpio": "trpjela", "letio": "letjela",
    "šutio": "šutjela",
    # with a prefix (a word is matched whole), and the -nijeti verbs ("donio" -> "donijela")
    "poželio": "poželjela", "zaželio": "zaželjela", "zavolio": "zavoljela", "doživio": "doživjela",
    "preživio": "preživjela", "uvidio": "uvidjela", "predvidio": "predvidjela", "dospio": "dospjela",
    "svidio": "svidjela", "prebolio": "preboljela", "donio": "donijela", "odnio": "odnijela",
    "prenio": "prenijela", "unio": "unijela", "iznio": "iznijela", "podnio": "podnijela", "ponio": "ponijela",
}
# The adjectives with a fleeting a, for "/a": the feminine drops the
# masculine's last "a" ("siguran" -> "sigurna", "dobar" -> "dobra"; "/na",
# "siguran/na", says so itself). Whole words in lower case, as the groups
# above; to add one, its masculine and its feminine.
FLEETING_A = {
    "siguran": "sigurna", "nesiguran": "nesigurna", "spreman": "spremna", "umoran": "umorna",
    "odmoran": "odmorna", "sretan": "sretna", "zadovoljan": "zadovoljna", "slobodan": "slobodna",
    "svjestan": "svjesna", "dužan": "dužna", "potreban": "potrebna", "gladan": "gladna", "žedan": "žedna",
    "bolestan": "bolesna", "aktivan": "aktivna", "uporan": "uporna", "ponosan": "ponosna", "snažan": "snažna",
    "miran": "mirna", "točan": "točna", "uspješan": "uspješna", "dosljedan": "dosljedna", "dobar": "dobra",
}

SEX_CODES = ("f", "m")          # models.SEXES' keys: the sexes a text resolves for

# a slash form, a whole token (the module's docstring): letters, "/", an
# ending or a whole word, then punctuation alone up to the token's end
_FORM = re.compile(r"(?<!\S)([^\W\d_]+)/([^\W\d_]+)([^\w\s/]*)(?!\S)")
_ENDINGS = ("la", "na", "a")


def _swap(word: str, masculine: str, feminine: str) -> str:
    """`word`, whose lower case ends in `masculine`, with that ending made
    `feminine`: the letters the two share at their start are the word's own
    (its capitals), the rest the feminine's, in capitals when the whole word
    is ("BIO" -> "BILA")."""
    start = len(word) - len(masculine)
    shared = len(os.path.commonprefix([masculine, feminine]))
    tail = feminine[shared:]
    return word[:start + shared] + (tail.upper() if word.isupper() else tail)


def _feminine(word: str, ending: str) -> str | None:
    """The feminine of a slash form's word before its `ending` ("la", "na",
    "a"), or None for a form the rules do not cover."""
    low = word.lower()
    if ending == "la":
        if low in JETI:
            return _swap(word, low, JETI[low])
        if low in FLEETING_LA:
            return _swap(word, low, FLEETING_LA[low])
        if low.endswith(FLEETING_SAO[0]):
            return _swap(word, *FLEETING_SAO)
        return _swap(word, "o", "la") if low.endswith("o") else None
    if ending == "na":
        return _swap(word, "an", "na") if low.endswith("an") else None
    if len(word) < 2:                                    # "/a": n/a
        return None
    return _swap(word, low, FLEETING_A[low]) if low in FLEETING_A else word + ("A" if word.isupper() else "a")


def _whole(word: str, second: str) -> str | None:
    """The feminine of a form of two whole words ("bio/bila",
    "Spreman/spremna"), in the first word's capitals ("Spremna"), or None
    when the second is not surely the first's feminine: it must be what
    the "/la" rule gives an l-participle, or an adjective of FLEETING_A's
    feminine (the module's docstring: never "the word and an a", a noun's
    forms by number look the same)."""
    low = word.lower()
    if low.endswith("o"):
        feminine = _feminine(word, "la")
    elif low in FLEETING_A:
        feminine = _feminine(word, "a")
    else:
        return None
    return feminine if feminine is not None and feminine.lower() == second.lower() else None


def gendered(text, sex):
    """`text` as a reader of `sex` reads it ("f", "m"; anything else, None
    above all, is a reader who has not said): every slash form its
    feminine or masculine word, a form the rules do not cover left as it
    is. For no sex, or a text with no slash, the very object given, so a
    page for such a reader is what it was, character for character. A
    str's subclass stays its class (a Markup stays safe: only letters
    change)."""
    if sex not in SEX_CODES or not isinstance(text, str) or "/" not in text:
        return text

    def one(m: re.Match) -> str:
        word, ending, after = m.group(1), m.group(2).lower(), m.group(3)
        feminine = _feminine(word, ending) if ending in _ENDINGS else _whole(word, m.group(2))
        if feminine is None:
            return m.group(0)
        return (feminine if sex == "f" else word) + after

    out = _FORM.sub(one, text)
    return out if type(text) is str else type(text)(out)
