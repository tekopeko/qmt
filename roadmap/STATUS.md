# Where the last session left off — 17.10.2026.

Read `CLAUDE.md` first; this file only carries what isn't obvious from the code.

## 15.10.2026 — Opus implements, Fable reviews

The owner's rule: implementations are delegated to `opus-worker` (Opus 5.5,
`effort: max`), Fable designs and briefs, then reads the diff and re-runs the
tests and the audit before anything ships. `QMT_DELEGATE=on` on his machine.
First task under the rule: the landing's offer becomes three online tiers
(the gym cards move to a section below), bullets become editable lists, and
the tiers are a swipe carousel with dots on phones.

Built (Opus draft, awaiting review): `#usluge` holds QMove START / PRO
(featured) / ELITE, each with a monthly and a yearly price behind a
"Mjesečno / Godišnje" switch; only START's monthly price is a real plan's,
the rest are copy slots the owner types. Dvorana and Individualno sit in
`#dvorana` below. Bullets are `ListSlot`s (up to 6 × 44 characters, one
`site_copy` row of JSON each); migration `1b09c249c2c6` folds the old
`offer.<card>.p1..p3` rows into them, so the owner's prod edits carry over.

15.10.2026, second task (Opus draft, awaiting review): after a booking on `/raspored` the ok alert offers "Isti termin svaki tjedan do …", which books the same weekly slot for the rest of the paid period (`db.book_series`, `POST /book/{id}/series`; no schema change).

15.10.2026, third task (Opus draft, awaiting review): the gym (`#dvorana`) has the Mjesečno / Godišnje switch too, one choice with the tiers' (either switch flips every card on the page): Dvorana and Individualno keep their real monthly prices, the yearly ones are copy slots (`offer.dvorana.year_*`, `offer.individualno.year_*`), and on phones the two cards are a swipe row with two dots, one carousel (`.swipe-row`) for both sections.

16.10.2026 (Opus draft, reviewed, live): the owner lifted the copy limits (the copy first, a design pass once it is final): every slot takes up to 2000 characters (lists 12 items), line breaks are kept and show (`span.t`, pre-line), Enter is a new line in the editor and ⌘/Ctrl+Enter saves; `tests/test_copy.py` guards overflow and clipping only, and the photo card's caption is clamped inside the card.

16.10.2026, second task (Opus draft, reviewed, live): the landing has an announcements section, `#aktualno`, between the gym and the gallery: the owner's two cards for the month ("Treninzi za penziće" and "Pilates za cure" as examples to retype: chip, title, when, text, a grey "Javi nam se" to the contact), each switched off in edit mode by a new slot type, `FlagSlot` ("on" / "off" stored as copy, no schema change). A hidden card is not on a visitor's page, and with both hidden neither is the section; the editor sees it dimmed in edit mode only. Same task: on phones the three tiers' swipe row opens on PRO, the featured middle card.

16.10.2026, third task (Opus draft, reviewed, live): the announcements are the first thing on the page (the owner: "more horizontal", "even before the first photo"). `#aktualno` is two wide strips in the hero, between the headline and the photo: chip, title over when, text and a grey "Javi nam se" in one row that wraps when a text is long (a column below 700px). They take the place of the hero's lead, its member button ("Rezerviraj termin" / "Pogledaj cjenik") and the note under it, gone for everyone; a member's way in is the tabs and the offer cards' buttons. The section head went too, and with it the slots `hero.lead`, `hero.note`, `events.kicker` and `events.h2` (any rows for them in prod's `site_copy` are harmless, nothing reads them; no migration). The strip's title is an `h2`, not the card's `h3`: it sits straight under the `h1` (the audit's heading order).

16.10.2026, fourth task (Opus draft, reviewed, live): the announcements move like Shape's "Novo u Shape Clubu" cards. On phones (<900px) `#aktualno` is a swipe row with dots, like the tiers', running to the screen's edges, and it moves on by itself every 5 s (`data-auto`, the owner's number): quiet while a finger, a mouse or the focus is on the row or its dots, with the whole delay again once they leave; no tick in a hidden tab or with the row off the screen; never under reduced motion. One card shown takes the whole row (`.single`, set server-side again); the dots script skips cards that are not shown and makes none for fewer than two. On a desktop the two cards now sit side by side (the owner: "one next to the other, not under"), each a header line (chip, title over when, the link) over its text, one card alone a centred 760px column. Same task: the install banner (`#a2hs`) comes back a week after each dismissal until the app is installed (the owner: it should still appear for people who did not install); `qmt-a2hs` holds when it was dismissed, an old `"no"` counts as long ago (those phones see it once more), and an accepted native prompt stores `"installed"` (never again, as before). No schema change.

16.10.2026, fifth task (Opus draft, reviewed, live): the owner can put a photo behind each announcement, like Shape's announcement cards (the owner: "an option for my friend the owner of the gym to also add an image in the background of the announcement"). A new slot type, `ImageSlot` (`event1.image`, `event2.image`), stores the file's name as copy (no schema change; no row = a plain card). In edit mode "Dodaj sliku" opens the phone's picker; `POST /copy/{key}/slika` takes jpg / png / webp up to 15 MB, turns it upright from EXIF, shrinks it to 1600px and stores a progressive JPEG without EXIF through `storage.save` (R2 on prod), deleting the slot's previous photo; "Ukloni sliku" (two taps) is `reset=1` on `POST /copy/{key}`. The photo is public: `GET /slika/{name}` serves only a name an `ImageSlot` row holds (never programme media), cached a year as immutable, the bytes proxied from R2 (`storage.open`) rather than redirected, so the URL is stable. The card turns into Shape's photo card (glass chip on top; white title, text and a white pill at the bottom; `data-photo` for the audit), and the plain card beside it moves its lines to its foot so both texts end level. Pillow is a new dependency.

17.10.2026 (Opus draft, reviewed, live): a client cancels a booking from "Moje rezervacije" on `/raspored` (the owner: "an x button with which I can cancel a reservation … a pop up with which a user can confirm he wants to cancel it"). Each card has a ✕ in its top-right corner (`.unbook-x`, 32px, muted) that opens the styled confirm dialog (`data-confirm`: "Otkazati rezervaciju?", the termin, "Otkaži rezervaciju") before `POST /cancel/{id}`; a termin the trainer canceled gets "Maknuti otkazani termin?" / "Makni". The week grid's "Otkaži" asks the same way now. The cutoff is 12 h (it was 3; `CANCEL_CUTOFF_HOURS` stays the override and is unset on Railway, so the default is prod's value): inside it the card says "Otkazivanje do 12 h prije termina" instead of offering a ✕. One rule in one place, `db.cancel_deadline`, which `cancel_booking` and both buttons ask. No schema change.

17.10.2026, second task (Opus draft, reviewed, live): one announcement at a time, as wide as the screen, like Shape's "Novo" cards (the owner: "this announcement thing should cover the entire screen, and not only half of it … same thing goes for the desktop view, only one announcement is shown over the entire width"). `#aktualno` is a snap scroller at every width, one card per view, each as wide as the row's content: the screen less the gutter on a phone, the hero's 1100px column on a desktop (exactly as wide as the photo under it), with nothing of the next card in view. Its dots show at every width and it moves on by itself every 5 s on a desktop too (hover holds it there, as touch and focus do). The desktop's two columns, `.single`'s 760px column and the "header line over a text line" are gone: a plain card from 900px is the one-line strip again (chip, title over when, the text, the link at the right end). A photo card is at least 320px tall from 900px (300px on a phone). In edit mode the two stack, one under the other, each the row's width and without dots, so the editor reaches a card he switched off. The hero's side gutter is `.hero-inner`'s padding at every width now (it was below 900px only), so the row's negative margins, which keep the card's shadow uncut, never overflow the hero; nothing else in the hero moved. Same task: the tiers' and the gym's swipe cards on phones are 92% of the row instead of 86% (the owner: "make them a little bigger so only a part of the next item is shown"): PRO still opens centred, with about 18px of START and ELITE on either side at 390px. No schema change.

## 5.10.2026 — the redesign is live; work continues on `master`

`redesign` was merged into `master` (one merge commit, so the whole redesign
reverts with `git revert -m 1 <merge>`) and deployed. There is no long-lived
branch any more: work happens on `master`, and every push deploys.

Same day, first fix on master: as owner on any window wider than 1200px the
avatar stuck out of the topbar pill (eight tabs + the full wordmark need 1086px,
the pill offers 1076). The wordmark now follows the room the tabs leave (a
container query on `.brand-slot`), bars with seven or more tabs run tight, and
the audit checks the pill itself.

6.10.2026 (built 5.10.), deployed: the homepage answers "what do you offer and what does it cost":
the six service cards became **three offer cards with prices** (Online /
Dvorana / Individualno, MojiMakrosi as an add-on: 5 € beside online, 3 € beside
a plan in the dvorana; the online plan includes a monthly Zoom call or a
meeting in person). The hero photo lost its service chips and is a link to the
cards. **Prices are public again** — the owner's call, reversing 28.9.; the
legal question behind that rule was not re-examined here, and
`PUBLIC_PRICES=off` is the one-variable way back. Card titles and copy are
placeholders for the owner to rewrite.

6.10., second change: the guest's bar is Shape's small pill (brand · Prijava
in red · Kontakt in dark; "Što nudimo" was tried and dropped — the photo leads
to the offer), and the hero lost its buttons and the "Već imaš račun?" line.

Later on 6.10.: **the texts are editable in place** by the trainer or owner —
46 of them (the whole landing, the cjenik descriptions, the prehrana page),
each with a character limit its box can take; `src/qmt/copy.py` is the list,
`tests/test_copy.py` proves the limits in a real browser. The editor is the
"✎ Uredi tekstove" button at the bottom right of a page. Migration
`e5a7c3b9d1f2` (site_copy). And the guest bar lost "Što nudimo" again:
Prijava is red, Kontakt dark.

And the phone check became a hook: the audit walks 360px as well as 390px
(which at once found two overflows live on prod — the membership table on
/raspored and the contact email on the landing, both fixed), has a ~30 s
`--phone` mode, and a Stop hook runs it whenever UI files changed.

Also new, and only about how Claude works here: delegation to an Opus 5.5
worker sits behind the `QMT_DELEGATE` flag (off by default) — see "Models" in
`CLAUDE.md`.

## 28.9.2026 — prices members-only, registration closed (deployed)

On legal advice the owner received (public prices would need the prior price
shown beside them, the way shop shelves do), `/cjenik` became members-only and
registration closed. Guests see no price, no Cjenik tab and no "Registriraj
se"; service cards say "Javi nam se" → `#kontakt`. Existing accounts log in as
always. The switch is `SIGNUP_MODE` (unset = closed); it replaced `SIGNUP_OPEN`.
To show prices publicly again the cjenik needs the prior-price display first.
The owner's Shopify shop, where the reference prices came from, is outside
this app and still shows them publicly.

## Deploy state

`master` is deployed (Railway auto-deploys on push) and carries everything:
the Shape-club-style redesign, the 28.9. hotfix, the login modal and the
install banner. 91 tests green.

## What this session shipped (25.9.)

- **`qmt-design` skill** (`.claude/skills/qmt-design/`): SKILL.md, generated
  `tokens.md`, the component catalog, borrowed patterns from shapeclub.app, and
  `scripts/audit.py` — a measured audit (overflow, WCAG contrast, tap targets,
  labels, alt, heading order) across every page × role × theme × width, with a
  reviewed baseline so runs report only what is new. The contrast checker now
  alpha-composites backgrounds; the old "ratio 1" false positives are gone.
- **Login/registration modal** (`#authDlg`) and **install banner** (`#a2hs`,
  phones only) — on master.
- **Redesign** (built on a branch, merged 5.10.) — Shape's structure in QMT's colours:
  floating dark-glass topbar pill; pill buttons everywhere; radius scale
  28/20/12 (`--r-xl/--r-lg/--r-md`); landing rebuilt (kicker, centred hero,
  photo stage with on-photo chips, italic uppercase service titles); cjenik
  with a raised "Najpopularnije" grupni card; owned plans and memberships marked
  by tinted borders instead of inset bars; page headers unified (`main > h1`);
  `--accent-tint-ink` for accent text on the accent tint (chips now clear AA).
  Verified: 90 tests, 0 overflow, 0 new audit findings, screenshots at 1280 and
  390 in both themes.

## Next up

1. **Hero photography from the owner.** The only photo asset
   (`static/gallery/dvorana-1.jpg`) has a wall print in its upper third — the
   crop hides it, but real photos would lift the landing more than any CSS.
2. Owner writes landing/service copy and records videos (his explicit wish —
   don't draft copy for him beyond placeholders).
3. **Stripe go-live** (owner): the d.o.o.'s Stripe account, real prices, the
   accountant's Fiskalizacija 2.0 flow. Switching accounts means clearing
   `stripe_customer_id` / `stripe_subscription_id` on users (sandbox ids are
   meaningless in the live account). Sandbox is fully verified on prod:
   prices, checkout, webhook, tier switch 12→16→12.
4. Pricing questions parked: the QMT + mojimakrosi bundle and the Prehrana
   plan (needs an entitlement bridge between the two apps).

## Testing the whole pipeline on prod

1. As owner, open **Online treninzi** once — creates the nine programme slots.
2. Registration is closed while `SIGNUP_MODE` is unset. To test it, set
   `SIGNUP_MODE=invite` on Railway, sign up with an unused allowlist alias
   (`tvrtko.doresic+qmt1/2/3@gmail.com`), verify by email (owner gets the "Novi
   korisnik" notice), then unset it again.
3. Login → profile form → landing. Online tab appears only after an Online
   uplata on /clanarine; upitnik then routes to the matched programme.
4. Reminders: `python scripts/send_reminders.py` on Railway forces a pass;
   check the `reminders` table for claims.
5. Stripe sandbox: /cjenik → Pretplati se → card 4242… → webhook 200 →
   `payments` row with `method="stripe"`; /placanje/portal for the tier switch.

## Notes for the next session

- Croatian UI; the owner writes the copy — don't polish text.
- Verify UI in a real browser (Playwright) at 390px; one screenshot per message.
- Run `python .claude/skills/qmt-design/scripts/audit.py` before calling any UI
  work done; `--save-baseline` only after a deliberate review, and say why in
  the commit.
