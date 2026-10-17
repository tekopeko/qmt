# Shape Club — design reference (screenshots)

Saved 17.10.2026 from shapeclub.app, logged in, for QMT's own design work.
Not ours; a reference only, never served by the app.

## Onboarding questionnaire (`/onboarding/preferences`)

`upitnik-1…5`: the five steps, one question per screen, the last two at
desktop width (2874px wide, a retina capture). What to borrow for QMT's
upitnik (`/upitnik`):

- one narrow centred column (≈1120px), the small wordmark alone at the top,
  no topbar, nothing else on the page: one question, nothing to compete with it
- a thin progress bar above the question (filled part white, the rest a dark
  grey; ≈20% per step), no step numbers
- the question as the page's h1, large, bold, left-aligned
- the answers as full-width rows (≈120px tall) with a letter badge A / B / C
  at the left, a hairline border on a slightly lighter surface; the chosen
  row inverts to white with black text and a ✓ at the right end
- a muted "Nazad" link under the rows, no "Dalje": choosing an answer advances
- the background a near-black with a faint purple tint

## Buying a subscription ("Potvrdi kupnju pretplate" → Stripe)

`pretplata-1…4`: the confirmation sheet (desktop and phone), the contract
page it links to, and the Stripe Checkout it hands over to. The contract's
text is in `ugovor-o-pretplatama-shape-2026-03-11.md` (theirs: structure
only, see its header). The flow, step by step:

1. **A confirmation sheet before Stripe** (a modal on a desktop, a tall
   sheet on a phone, the page blurred behind): title "Potvrdi kupnju
   pretplate", lead "Pregledaj detalje kupnje prije nastavka na naplatu."
   Then three boxes: TRENUTNO → NOVI PLAN (the current plan or "Nema aktivne
   pretplate" with a note, an arrow, the new plan's name and "Mjesečno ·
   50 EUR"); POČETAK RAZDOBLJA / PREDVIĐENI KRAJ RAZDOBLJA (timestamps to
   the second); a sentence on the trial ("probni period od 3 dana …
   ograničen na 5 dovršenih treninga … naplata kreće odmah po završetku");
   NAČIN AKTIVACIJE as a two-button segmented choice, "Probni period" /
   "Odmah naplata". Labels are small uppercase letter-spaced captions over
   the values.
2. **Two consent checkboxes**, both required before the primary button
   wakes up: (a) "Prihvaćam uvjete pretplatničkih programa definirane u
   ugovoru o pretplatama i uvjetima korištenja" (two links), and (b)
   "Potvrđujem početak korištenja usluge odmah i upoznat/a sam da nakon
   prve naplate jednostrani raskid ugovora više nije moguć." — the waiver
   of the 14-day withdrawal right for digital content, which Croatian
   consumer law needs as an explicit consent (their contract §2.2).
3. **Buttons**: "Odustani" (ghost) and "Nastavi na naplatu" (primary,
   disabled until both boxes are ticked).
4. **The contract page** is a light, document-like page: a small tag,
   the title, a gradient underline, "Verzija · Zadnje ažuriranje", an intro
   box, numbered sections with red numerals.
5. **Stripe Checkout** (hosted): "Try Shape Unlimited / 2 days free / Then
   €50.00 per month starting …", Apple Pay, Link, card, Google Pay, the
   trial sentence repeated under the form. Note the mismatch: the app says
   3 days, Stripe says 2 — keep the trial length in ONE place when QMT does
   this.

What QMT will need for the same step (roadmap item 4, card payments; the
d.o.o.'s Stripe account, prices and fiscalization are still the owner's):
a confirmation sheet of this shape between `/cjenik` and Checkout, with the
plan, the period, and the two consents; its own "Ugovor o pretplatama" and
"Uvjeti korištenja" pages written for Quality Movement Training by the
owner's lawyer or accountant, versioned with a date; a decision on a trial
and its limits; and the same facts shown once more by Stripe.

## The logged-in app

`app/README.md` and `app/app-01…18.jpg`: the map of every page behind the
login (dashboard, programmes, Moj napredak's calendar, profile, billing,
what the trial locks) and the measured styles. The finding that matters:
**Shape Club has no class scheduler**; it is programme-based (week × 3
video trainings), and its only calendar is the client's activity month grid.
