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
  with "0%" and "0/12 treninga odrađeno", a dark pill "Kreni na trening" (#171717 with a light gradient hairline; it reads white in a small capture).
- Right: a dark card (`#141414`, 24px radius, 1px `#372a34` border) headed
  "TJEDAN 4 - TRENUTNI TJEDAN ˅ ——— 3 TRENINGA" (an accordion: the chevron
  collapses the week, `app-16`), holding three photo cards "TRENING 1/2/3"
  (chip top-right), "Tjedan 4", the name, the same dark pill "Pokreni trening".
- Home Challenge mode (`app-17`, text only): the same hero for "Challenge 18",
  "Završi challenge", weeks 1–4 as accordions with "1. TRENING Gluteus i
  noge" etc., then two rows of photo cards: PREPORUČENO ZA TEBE ("3x tjedno",
  "Challenge 18", "Napredni") and OSTALI IZAZOVI ("Summer Quick Workouts",
  "Početnik"), each with "Vidi sve". These are the "Novo" cards from the
  owner's phone screenshots (chips, italic title, a dark pill).
- Then a purple gradient banner "STAY CONSISTENT!", the FAQ in two columns,
  "Rezultati govore sami za sebe" (before/after photo carousel), footer.
- Pages load slowly (3–30 s) behind a skeleton (`app-18`) and fade in.
- `app-21-dashboard-after-payment-2026-10-30.png` (the owner's capture, a
  fresh account right after paying, desktop 2876×1688 retina): the page the
  payment lands on is this dashboard in Home Challenge mode, and it is LIGHT
  here (a pale grey-blue page, white cards), where the 17.10. trial captures
  were dark. The header pill "Home Challenge | Gym Program" with the bell and
  ☰ as white circles; left, the hero photo card "BOK TANA!" (italic uppercase),
  "Nastavi gdje si stala:", "Summer Quick Workouts", "Napredak … 0%", the
  thin bar, "0/12 treninga odrađeno", two dark pills "Kreni na trening" and
  "Završi challenge", ‹ › arrows above the card; right, a white card
  "TJEDAN 1 ˅" holding the training photo cards one under another, each
  with a dark chip "1. TRENING" top-left, the name bottom-left ("Gluteus i
  noge") and a white-outlined pill "Pokreni trening" bottom-right. Saved on
  the way to the Gym Program's training page (the exercise list with checkmarks).
- `app-22-dashboard-gym-program-paid-2026-10-30.png` (the same account, the
  Gym Program tab, desktop 2864×1614 retina): the dashboard is DARK again in
  this mode (the owner: "When logged in the whole app landing page looks
  differently": the mode, not the account, sets the theme; Home Challenge
  light, Gym Program dark). Left, the hero photo card "BOK TANA!", "Nastavi
  gdje si stala:", "PRVI TRENING DONJI DIO TIJELA" (uppercase, not italic),
  "Napredak … 0%", the bar, "0/12 treninga odrađeno", one white-outlined pill
  "Kreni na trening"; right, a dark card "TJEDAN 2 - TRENUTNI TJEDAN ˅ ——— 3
  TRENINGA" holding the training photo cards one under another: the chip
  "TRENING 1" top-RIGHT here, "Tjedan 2" small and the name bottom-left,
  "Pokreni trening" bottom-right. The week opens on the current one (week
  2 for a fresh account: the programme runs by calendar weeks, 3 trainings a
  week, 12 in all).
- `app-23-dashboard-home-challenge-week-accordion-2026-10-30.png` (Home
  Challenge, `?mode=challenge`, desktop 2880×1776 retina): the weeks as an
  accordion in the right card, "TJEDAN 1 ›" shut and "TJEDAN 2 ˅" open, its
  trainings numbered through the challenge ("4. TRENING Gluteus, noge i core",
  "5. TRENING"), the chip top-LEFT in this mode; the owner: "You can scroll
  through tjedan 2 to tjedan 4", so every week is reachable, none locked by
  the calendar. For QMT's programme page: the days as such cards in one
  column, any of them openable, the number in the chip.
- `app-24-home-challenge-preporuceno-za-tebe-2026-10-30.png` (Home Challenge,
  further down, desktop 2834×1466 retina; `app-17` had this section as text
  only): "PREPORUČENO ZA TEBE" under a short orange-to-pink bar at its left,
  then photo cards three to a row (≈560×420, 24px radius, a bottom gradient):
  a white chip top-right "3x tjedno" / "4x tjedno", the name bottom-left
  ("Summer Quick Workouts", "Challenge 16" …, white, bold, not italic), a
  pale pill "Početnik" under it and a round › at the right end. The
  programmes the questionnaire's answers fit, as a catalogue to pick from:
  the shape for QMT's /treninzi list once a client has more than one
  programme (today's rows carry the same facts as text).
- `app-25-home-challenge-training-page-paid-2026-10-30.png` (`/video/208?challenge=16`,
  a paid account, desktop 2880×1738 retina): the Home Challenge training page
  as `app-19` has it, now with the video playing (16:38 of 41:11, a PORTRAIT
  video letterboxed in the full-width native player): one video per training,
  "← Povratak na Challenge" and the dark pill "✓ Završi trening" on one line,
  the pale note "Rekviziti: čvrsti naslon (za hip thrust), bučice ili girja, mini
  elastična traka", the comments at the right. The owner (30.10.2026): "When
  I enter a training in the home challenge tab it really is one video … It
  only mentions which equipment is necessary there." Whether the Gym Program's
  training page is the same, or the exercise list with a checkmark per
  exercise he remembers, is the open capture.
- `app-26-moj-profil-paid-2026-10-30.png` (`/user/profile`, desktop 2858×1584
  retina; `app-07` was the trial's): the light profile page, sharp: the pill
  "SHAPE CLUB · Česta pitanja" with the bell and ☰, "Ovdje možeš promijeniti
  svoje podatke.", the white accordion card "Profil i kontakt — Osnovni
  podaci, fotografija i obavijesti." open (a ˄ circle at the right): the
  avatar circle with "Promijeni sliku" (dark pill) and "Ukloni" (red outline),
  "JPG, PNG ili GIF. Max 5MB.", the IME and E-MAIL floating-label inputs, the
  newsletter checkbox, "Pošalji link za reset lozinke" (underlined); then
  "Preferencije treninga — Prilagodi treninge prema svom ritmu." with the
  select "PREFERIRANI BROJ TRENINGA TJEDNO 3".
- The Gym Program's "TJEDAN 2 - TRENUTNI TJEDAN" on 30.10.2026, a day after
  paying (`app-22`; the URL is `/dashboard?mode=gym`), and "TJEDAN 4 -
  TRENUTNI TJEDAN" on 17.10.2026 (`app-10`, the trial): the Gym Program runs
  on ONE shared four-week calendar, not from each member's start. The two
  dates fit a cycle that began on Monday 22.9. (week 4 = 13.–19.10.) and the
  next on 20.10. (week 2 = 27.10.–2.11.): a member who joins mid-cycle lands
  in the running week, the earlier weeks behind her, "0/12 treninga" all the
  same. Not a bug, a cohort model. The Home Challenge is the other model,
  per member from week 1 with every week reachable (`app-23`); QMT's days
  ("Dan 1 … Dan N", done whenever) follow the second.

## The Gym Program's training page (`/gym-program-video/1212`, a paid account, 30.10.2026; `app-27…`)

**The owner was right: a Gym Program training is exercise by exercise**, not
one video (that is the Home Challenge's page, `app-19` / `app-25`). What the
page holds (`app-27`, desktop 2880×1742 retina, the first open):

- **A segmented progress bar across the top**, one segment per exercise
  (seven here), inside a rounded track: the first segment filled white, the
  rest grey.
- Under it one line: "← Povratak" at the left, then the exercise's name,
  "Rumunjsko mrtvo dizanje bučicama", and at the right a pale pill "Završi
  Trening".
- **One exercise's video**, a portrait clip of 0:22 looped in the native
  player, letterboxed in a wide dark rounded box, with round ‹ › buttons at
  the box's left and right edges to step to the previous / next exercise.
- **A first-open tour** (coach marks) over it: a dark card anchored to the
  bar, a blue ring counting down ("26"), "1/6", a "Preskoči" pill, the
  sentence "Ovdje vidiš napredak kroz vježbe. Kad spremiš progres, stavka
  postaje zelena.", a hairline, "Nazad" (muted) and "Dalje" (white) pills.
  Six steps, each pointing at a part of the page; the owner: "when opening
  for the first time, it has a guide here". So progress is SAVED per
  exercise ("spremiš progres": presumably sets / reps / weight), and the
  saved item turns green in the list.
- `app-28…32`: the tour's steps 2–6 (the owner, 30.10.2026), which show the
  whole page under them. **The page, top to bottom:**
  1. The segmented bar, then the line "← Povratak · Rumunjsko mrtvo dizanje
     bučicama … Završi Trening".
  2. The video box with ‹ › (tour 2: "Povuci lijevo/desno za promjenu vježbe
     bez izlaska iz videa.": a swipe on a phone).
  3. Under it two columns. **Left, the current exercise's card**: the eyebrow
     "TRENUTNA VJEŽBA" with a chip "5/11" (this is exercise 5 of 11), a ⇄
     button at the card's right (tour 5: "Ne odgovara ti vježba? Ovdje otvaraš
     zamjene."), the name as the h1, the target "10 REP", then **the set log**,
     a table SET · REP · KG · AKCIJE with a row per planned set (1, 2, 3), REP
     prefilled with the plan (10) and KG with the last weight (20) or 0, a round
     "+" under it to add a set, and a wide dark pill "Spremi" (tour 3: "Upiši
     ponavljanja i kilažu za svaki set. Možeš brzo uređivati polja."; tour 4:
     "Spremi unos kako bi set bio označen i progres zapisan."). So progress is a
     LOG of reps × kg per set, saved per exercise, and the saved exercise turns
     green in the list (tour 1).
     **Right, two cards**: "MUZIKA UZ TRENING" (Spotify · "Otvori u Spotifyju",
     three buttons Spotify / YouTube / YouTube Music: links out, nothing more) and
     **"VJEŽBE", the day's whole list** in sections with letter-spaced eyebrows,
     "ZAGRIJAVANJE" (Vježba 1 Bodyweight RDL · 1 X 15 REP · "Odmor između
     serija: —"; Vježba 2 Rock back · 1 X 15 REP; Vježba 3 Čučanj izdržaj uz zid ·
     2 X 30 SEK · "30–45 sec") and "TRENING" (Vježba 4 Leg press · 3 X 10 REP;
     "TRENUTNA VJEŽBA" Rumunjsko mrtvo dizanje bučicama · 3 X 10 REP, its card
     outlined). Each item: a thumbnail at the left, the eyebrow "VJEŽBA n", the
     name in bold, the dose (sets × reps, or sets × seconds), the rest line, a
     note line when there is one; at the right a round ▷ (jump to it) and a
     round ⇄ (swap it).
  4. **The swap modal** (tour 6: "Odaberi zamjensku vježbu. Tvoj log ostaje
     povezan s treningom."): "Zamijeni vježbu", ✕, "Slične vježbe", a list of
     alternatives from the library, each "ZAMJENA" + the name ("Rumunjsko mrtvo
     dizanje šipkom", "Jednonožni RDL") with ⇄ at the right; the page blurred
     behind. The log stays with the training whichever exercise is done.
- Measured in words (desktop, dark, a faint purple tint): cards 24px radius on
  `#141414`-ish with a 1px lighter hairline, eyebrows letter-spaced uppercase in
  muted grey, the h1 Inter 700 ≈36px, inputs dark rounded 12px boxes, the
  primary "Spremi" a black pill, the tour card a near-black 24px card with a
  blue countdown ring. The video clips are PORTRAIT, ~20 s, looped.
- Still to capture: the page after "Spremi" (a green item, a filled segment)
  and what "Završi Trening" opens.

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

## Phone width (iPhone 16 Pro Max, 440 px, walked 17.10.2026 evening)

**Cut short after the dashboard's first screen.** The owner's tab was in
DevTools device mode (440×956, DPR 3, iPhone UA). The dashboard was measured
there and its top captured; then the emulated size fell back to the real tab
area (330×689, DPR 2; the iPhone UA stayed) and the tab went hidden, so the
menu walk was never started. Not captured at phone width: the menu sheet,
Home Challenge, Moj napredak, Moj profil, Billing, Social Club, Pogodnosti,
Nagradna igra, TDEE and the two trial-lock modals. The fall-back most likely
came from the capture tool itself: Claude in Chrome's `zoom` (and, once the
tab was hidden, its plain screenshot) sets the same device metrics DevTools
sets. A retry needs the Chrome window visible throughout and plain
screenshots only.

Files in `phone/`:

- `phone-01-dashboard-gym-top.jpg`: the first screen at 440 px (only
  220×459, half the CSS width: the size a plain capture of the device-mode
  view comes out at).
- `phone-02-dashboard-gym-header-hero-detail.jpg`: the header and the hero
  card at 440 px, sharp (660×690).
- `phone-330px-01-dashboard-stay-consistent.jpg`,
  `phone-330px-02-dashboard-faq.jpg`: **not** the phone, the page at 330 px
  after the fall-back; kept for the banner's and the FAQ's detail and for the
  header running off both edges.

What changes from the desktop layout (dashboard):

- The header is the same centred row (the frosted pill with the two tabs,
  the bell, ☰), smaller: the pill 257×46, the bell a 44 px and ☰ a 40 px
  circle, 11–12 px apart, fixed 24 px from the top. Its parts add up to
  364 px and do not shrink: at 330 px the row runs off both edges (the 330px
  shots), so a 360 px phone would lose 2 px a side (inferred, not seen).
- One column, 408 px wide with a 16 px gutter: the hero card (408×306) above
  the week card (desktop: side by side, ≈640 px each). The training cards
  (374×224) stay one under another as on desktop, 16 px apart, but the
  "Pokreni trening" pill drops under the training's name (desktop: beside it).
- Type shrinks: the greeting is 18 px (desktop 36).
- The FAQ is one column (desktop: two), every answer open; the results
  carousel shows one 400×400 photo per view.
- The pills "Kreni na trening" / "Pokreni trening" are dark (#171717 with a
  white-to-clear gradient hairline), on the desktop capture `app-10` too; the
  desktop notes above call them white.
- The Crisp chat bubble (54 px, 14 px from the corner) sits over the cards.

Measured at 440×956 (DOM, computed styles):

- Page: a gradient #191819 → #372a34 (50%) → #171717 over black; body Inter
  16/24; Rubik only for the footer's "Shape Club" (italic 800, 24 px).
- Header pill: rgba(255,255,255,.9), 1 px #e5e5e5, fully round, padding 8,
  backdrop blur 16 px, shadow `0 10px 15px -3px, 0 4px 6px -4px` at 10%
  black. Tabs 28 px tall, padding 8/16, Inter 600 12 px; inactive #525252,
  active white on a sliding #171717 pill 121×32. Bell rgba(255,255,255,.9)
  with a #404040 icon, ☰ white; both 1 px #e5e5e5 and the same shadow.
- Hero card: radius 24, overflow hidden, the photo under a bottom gradient
  (60% black → clear), padding 32. Greeting italic 700 18/28 uppercase;
  "Nastavi gdje si stala:" 14/20 at 80% white; the training's name 700
  20/28; the progress track 8 px, 20% white, fully round.
- Primary pill: a 150×34 wrapper, fully round, its 1 px transparent border
  painted by `background: padding-box #171717, border-box
  linear-gradient(to bottom, …)` (white at 50% → 30% → 14% → 0% opacity);
  the button inside 148×32, padding 8/28, Inter 600 12/16, white.
  "Pokreni trening" is the same at 146×34, its gradient starting at 100%.
- Week card: #141414, 1 px #372a34, radius 24, padding 16, the same shadow;
  its header "TJEDAN 4 - TRENUTNI TJEDAN" 12/16 uppercase, 0.6 px tracking,
  70% white.
- Training card: radius 16, overflow hidden, the same shadow; the chip
  "TRENING 1" 16 px in from the top right, 102×32, #171717, fully round,
  padding 8/20, 600 12/16 uppercase; the name 500 18/28.
- STAY CONSISTENT: 408×252, radius 24, padding 64/32, a gradient to the
  right #1e3a8a → #581c87 over a photo; the title italic 700 36/40
  uppercase, the line under it 20 px.
- FAQ: heading 500 20/28; lead 16 px #737373; questions 500 16/24 white;
  answers 16 px weight 300 #a3a3a3.
- Results: heading 700 30/36; a Flickity carousel, slides 400×400 radius 10.
- Footer #171717, 396 px tall. The page is 4162 px tall: hero at 112, week
  card 450, banner 1282, FAQ 1655, results 3167, footer 3767.

### The owner's full-page captures (DevTools "Capture full size screenshot", 17.10.2026, 22:23–22:34)

Taken by the owner in the same device mode (iPhone 16 Pro Max, 440 px, DPR
3, so 1320 px wide), whole pages in one image each, JPEG here from his PNGs:

- `phone-10-dashboard-gym-program-full.jpg` — the Gym Program dashboard, all
  4162 CSS px (hero, week card with three trainings, STAY CONSISTENT, FAQ,
  results carousel, footer).
- `phone-11-dashboard-home-challenge-full.jpg` — the Home Challenge view:
  the "Challenge 18" hero, the weeks, then the challenge card rows
  (PREPORUČENO ZA TEBE, OSTALI IZAZOVI: "Challenge 9", "Napredni", "3x
  tjedno" chips, a round › button bottom right). The capture is cut at the
  tool's 16384 px limit and the cards' photos are grey placeholders: they
  load lazily and the full-page capture does not wait for them. The layout
  is what matters here; the photos are in the owner's earlier phone shots.
- `phone-12-moj-napredak-full.jpg` — the activity page: tabs, week strip,
  daily goals, month grid, the Aktivnost card.
- `phone-13-moj-profil-full.jpg` — the profile with every accordion open.
- `phone-14-billing-full.jpg` — the billing page (PAKET, period, status,
  the three buttons, PROMIJENI PAKET, RAČUNI).

- `phone-15-social-club-full.jpg` — Social Club: the photo cards with "n
  novo" chips, one under another.
- `phone-16-nagradna-igra-full.jpg` — the prize-game article page.
- `phone-17-menu-open-over-billing.jpg` — the ☰ menu open on a phone: a white
  sheet under the pill, the same items as on desktop, over the billing page.
- `phone-18-crisp-chat-widget.jpg` — the chat widget ("Razgovor", Martina's
  greeting, a message box): their "privatni chat".

Still not captured at phone width: Pogodnosti, TDEE Kalkulator, the
trial-lock modal, the training page. Not needed for QMT's design.

## A training page (`/video/181?challenge=14`, opened 17.10.2026 22:5x, desktop; `app-19`, `app-20`)

Opened with "Pokreni trening" on a challenge's first training (the second
training the account has opened; nothing was played and "Završi trening" was
not pressed — that button is what counts a training as done for the trial's
limit of 5). What the page is:

- **A native `<video>` across the whole width** (1440×605 at 1440 px, the
  browser's own controls: play, 0:00, volume, fullscreen, ⋮), from
  `cdn.shapeclub.app`, paused on open. No custom player, no exercise list,
  no timer: a training is one video.
- **Under it, two columns.** Left: "← Povratak na Challenge" (a link) and a
  dark pill "✓ Završi trening" on one line, then a pale pink note box
  "Rekviziti: stolica, mini elastična traka, bučice, pilates lopta
  (neobavezno)". Right: "Komentari", a feed of comments (avatar or
  initials, name in the brand purple, text, "oko 1 mjesec • Odgovori", a
  heart with a like count), Martina answering in the thread ("Boss"
  badge), and a "Pošalji komentar" box with a send icon pinned at the
  bottom. The feed scrolls in its own box; the page itself is 1169 px.
- The comments are the community: every training has its own thread.
- For QMT's /treninzi: the video-first page with one note line under it is
  the right amount of chrome; the comments are a Shape thing (Martina's
  brand), not something a studio's programme page needs.
