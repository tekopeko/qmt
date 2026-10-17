# Shape Club — the logged-in app (walked 17.10.2026, desktop 1440px, a trial account)

Screenshots `app-01…18.jpg` (desktop only: the Chrome extension could not
resize the window, and the session is a cookie no other browser can reuse,
so no phone captures; the owner's own phone screenshots are in the parent
folder). Their app renders a route a few seconds after the URL changes and
locks several pages during the trial, so a few captures are of modals or
mid-transition; what each page HOLDS is written here from the page text.

## The map (menu ☰, top right; the pill holds "Home Challenge | Gym Program" on the dashboard, elsewhere the wordmark + "Česta pitanja")

| Menu item | Route | What it is | In the trial |
|---|---|---|---|
| Naslovnica | `/dashboard` (`?mode=challenge` for Home Challenge) | the programme dashboard, below | open |
| TDEE Kalkulator | `/nutrition` | a light form page: Dob, Spol, Težina, Visina, Razina aktivnosti, "Izračunaj", "Preuzmi E-Book" | open |
| E-book | `/ebook/prirucnik` | the recipe/advice e-book | LOCKED ("Sadržaj je zaključan — Odaberi pretplatu / Možda kasnije") |
| Mjerenja | `/user/measurements` | body measurements + progress photos (the prize game needs 2 months of them) | LOCKED ("Sadržaj nije dostupan u probnom periodu — Započni plaćanje / Možda kasnije") |
| Nagradna igra | `/nagradna-igra` | a light article page: prizes, rules, dates, "Otvori Mjerenja" | open |
| Pogodnosti | `/pogodnosti` | partner discount codes; stat tiles AKTIVNO SADA / PARTNERI | "Trial korisnice nemaju pristup pogodnostima" |
| Social Club | `/social-club` | photo cards with "n novo" chips: Recepti i prehrana, Motivacija, Q&A, Gym Girls, Home Girls (a community feed) | open |
| Česta pitanja | `/dashboard#faq` | the FAQ block on the dashboard | open |
| Moj napredak | `/user/activity` | the ONLY calendar in the app, below | open |
| Moj profil | `/user/profile` | accordions: Profil i kontakt, Preferencije treninga, Mjerenja (zadnje), Uređaji, Pretplata i naplata (→ Billing) | open |
| Billing | `/user/billing` | the subscription page, below | open |

**There is no class scheduler / timetable.** Shape Club is programme-based:
a month's programme = weeks × 3 trainings, each a video session started
from a card. Nothing is booked, nothing has a time or a place. Martina's
contact with clients is the "privatni chat" (Crisp widget, bottom right)
and the Social Club feed.

## Dashboard (`app-10…18`)

- Left: a big "Nastavi gdje si stala" photo card: `BOK TANAMANA!` (Inter 36px
  700 italic uppercase), the current training's name, a thin progress bar
  with "0%" and "0/12 treninga odrađeno", a white pill "Kreni na trening".
- Right: a dark card (`#141414`, 24px radius, 1px `#372a34` border) headed
  "TJEDAN 4 - TRENUTNI TJEDAN ˅ ——— 3 TRENINGA" (an accordion: the chevron
  collapses the week, `app-16`), holding three photo cards "TRENING 1/2/3"
  (chip top-right), "Tjedan 4", the name, a white pill "Pokreni trening".
- Home Challenge mode (`app-17`, text only): the same hero for "Challenge 18",
  "Završi challenge", weeks 1–4 as accordions with "1. TRENING Gluteus i
  noge" etc., then two rows of photo cards: PREPORUČENO ZA TEBE ("3x tjedno",
  "Challenge 18", "Napredni") and OSTALI IZAZOVI ("Summer Quick Workouts",
  "Početnik"), each with "Vidi sve". These are the "Novo" cards from the
  owner's phone screenshots (chips, italic title, white pill).
- Then a purple gradient banner "STAY CONSISTENT!", the FAQ in two columns,
  "Rezultati govore sami za sebe" (before/after photo carousel), footer.
- Pages load slowly (3–30 s) behind a skeleton (`app-18`) and fade in.

## Moj napredak — the calendar (`app-08`; top part from the page text)

- `TANAMANA` as the h1, tabs "Aktivnost | Napredak | Tvoji Ciljevi".
- A week strip: pon 12 · uto 13 · … · ned 18 (the current week, the day as a
  circle), under it three daily goals with checkboxes: "Minimalno 2L vode",
  "Minimalno 8000 koraka", "Minimalno 7h sna".
- A month picker "Listopad ˅" over a black rounded month grid (PON…NED,
  28 29 30 1 … 31 1; the other month's days muted; today a ringed circle).
- "Aktivnost": a card "Nema aktivnosti — Nema zabilježenih treninga za 17.
  listopada" with a clock icon. A completed training lands here by date.
- For QMT: this is the shape of a client's karton/raspored day view — a
  month grid you tap, the day's termini listed under it. Our week calendar
  already books; the month grid + day list is the view a client scans.

## Moj profil (`app-07`; the rest from the page text)

Light page, "Ovdje možeš promijeniti svoje podatke.", accordion cards
(white, 24px radius, hairline): Profil i kontakt (avatar 80px, "Promijeni
sliku" / "Ukloni", IME, E-MAIL as floating-label inputs 16px radius,
newsletter checkbox, "Pošalji link za reset lozinke"); Preferencije treninga
(PREFERIRANI BROJ TRENINGA TJEDNO 3, RAZINA Napredni, TRAJANJE 45-60 min,
GLAVNI CILJ Oblikovanje tijela, TIP PROGRAMA Full body, OKRUŽENJE Teretana,
"Spremi promjene" — the onboarding answers, editable); Mjerenja (zadnje);
Uređaji ("Upravljaj aktivnim prijavama"); Pretplata i naplata (→ Billing).

## Billing (`/user/billing`, page text; the visual capture did not land)

"Billing — Upravljaj pretplatom, promjenama plana i zahtjevima za raskid.",
"Natrag na profil". Card "Pretplata i naplata": PAKET Shape Unlimited ·
Term: Monthly · Cijena: 50.00 EUR · "Probni period završava: 20. 10. 2026.
18:34:33" · Status: Probni period · buttons "Otvori billing portal" (Stripe
portal), "Plati odmah", "Otkaži pretplatu", "Otkazivanje i uvjeti". Card
"PROMIJENI PAKET": PAKET + TRAJANJE selects, "Primijeni promjenu", a note on
prorating. Card "RAČUNI": "Prikazano 0 od 0 — Još nema dostupnih računa".
For QMT this maps onto `/profil`'s članarina block + `/placanje/portal`.

## Measured styles (desktop)

- Body Inter 16px; dashboard h1 Inter 36px 700 italic uppercase; section h1
  30px 800–900; the wordmark "SHAPE CLUB" 20px 800 italic.
- Header pill: `rgba(255,255,255,.9)`, 9999px, 1px `#e5e5e5`, 6px padding;
  the active tab a black pill with white text; bell and ☰ as 50px circles.
- Dark pages: near-black with a faint purple tint; cards `#141414` 24px
  radius 1px `#372a34`; photo cards 16px with a bottom gradient.
- Light pages (TDEE, Nagradna igra, Pogodnosti, Profil, Billing): a pale
  blue→pink gradient background, white cards 16–24px radius with 1px
  `#e5e5e5`, inputs `rgba(255,255,255,.7)` 16px radius 1px `#d4d4d4` with
  small uppercase floating labels; primary button `#171717` white text 12px
  radius, 12/20px padding, 14px 600; stat tiles 16px radius, pink
  `#f6e7f2`; a magenta `rgb(241,29,100)` card for promos.
- Modals: white, 16–24px radius, title 20px 700, one dark primary + one
  ghost button, ✕ top right; the page blurred behind.
