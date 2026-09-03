"""Online-trening onboarding upitnik: fixed questions, points per answer.

The score routes a client into a razina (početna/srednja/napredna — the
owner's grouping from the roadmap voice note); the goal question is not
scored — it picks WHICH programmes fit, not how hard they should be.
Questions live in code, not the DB: the trainer doesn't edit them ad hoc,
and changing them means re-thinking the scoring anyway.
"""

from __future__ import annotations

LEVELS = {
    "pocetna": "Početna razina",
    "srednja": "Srednja razina",
    "napredna": "Napredna razina",
}

GOALS = {
    "cijelo": "Cijelo tijelo",
    "gornji": "Gornji dio tijela",
    "donji": "Donji dio tijela",
}

# (label, points) — order matters, the form posts the option's index.
QUESTIONS = [
    {"key": "staz", "text": "Koliko dugo redovito treniraš?",
     "options": [("Ne treniram", 0), ("Manje od 6 mjeseci", 1),
                 ("6 mjeseci – 2 godine", 2), ("Više od 2 godine", 3)]},
    {"key": "tjedno", "text": "Koliko treninga tjedno trenutno odradiš?",
     "options": [("Nijedan", 0), ("1–2", 1), ("3–4", 2), ("5 ili više", 3)]},
    {"key": "sklekovi", "text": "Koliko sklekova napraviš u jednoj seriji?",
     "options": [("0–5", 0), ("6–15", 1), ("16–30", 2), ("Više od 30", 3)]},
    {"key": "cucanj", "text": "Kakvo je tvoje iskustvo s čučnjem pod opterećenjem?",
     "options": [("Nikad ga nisam radio/la", 0), ("Povremeno, lakši utezi", 1),
                 ("Redovito treniram", 2), ("Radim teške serije", 3)]},
    {"key": "ozljede", "text": "Imaš li ozljede ili bolove koji ograničavaju trening?",
     "options": [("Da, značajno", 0), ("Povremeno", 1), ("Ne", 2)]},
]

MAX_SCORE = sum(max(p for _, p in q["options"]) for q in QUESTIONS)


def score_answers(picked: dict[str, int]) -> tuple[int, str]:
    """picked: question key → chosen option index (validated by the caller).

    Thresholds split MAX_SCORE (14) roughly in thirds — same intent as the
    owner's "ovisno o ocjeni baci ga u početnike, srednje ili napredne".
    """
    total = sum(q["options"][picked[q["key"]]][1] for q in QUESTIONS)
    if total <= 5:
        level = "pocetna"
    elif total <= 10:
        level = "srednja"
    else:
        level = "napredna"
    return total, level
