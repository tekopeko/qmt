# Patterns worth borrowing

Measured on shapeclub.app (25.9.2026, real browser, computed styles) — a
successful Croatian consumer fitness app. Not a brand to copy (their palette is
light-gradient + navy + purple-grey; ours is red on near-black), but several of
their *structures* are stronger than ours and translate directly into QMT tokens.
Each entry says what they do, why it works, and how it maps to QMT.

## 1. Floating nav pill

**Theirs:** the header is not a bar — it's a white pill (`999px`, soft shadow)
floating over the page, ~440px wide, holding exactly three things: wordmark,
one text link ("Česta pitanja"), one filled CTA ("Prijava"). Not sticky.

**Why it works:** nothing competes with the content; the single CTA is
unmissable. **Map to QMT:** our topbar carries up to eight tabs for the owner, so
the pill is wrong for logged-in screens — but the *guest* landing could use it:
wordmark · Cjenik · [Prijava] [Registriraj se]. Keep the one-row rule.

## 2. Login as a modal, not a page — BUILT 25.9.2026 (`#authDlg` in base.html)

**Theirs:** "Prijava" opens a centred modal over a blurred, dimmed page:
overlay `rgba(6,8,54,.45)` + `backdrop-filter: blur(6px)`; panel 412px, white,
~24px radius, 32px padding; title "Dobrodošla natrag" with ✕ top-right; a
**segmented control** Prijava | Registracija inside the same modal (both forms
live in one panel, the inactive one hidden); "Continue with Google" then an "ILI"
divider; labelled inputs 51px tall, 14px radius, faint tinted background
(`#f9fafc`) and a 1px tinted border; "Zaboravljena lozinka" right-aligned under
the password; a Turnstile widget; primary button black pill, left-aligned.

**Why it works:** the user never loses the page they were on; login and register
are one decision away from each other; the blur makes the modal feel lighter
than a page.

**Map to QMT** (`.fb-modal` already has the dialog idiom):
- `<dialog id="authDlg" class="fb-modal">` opened by the topbar Prijava /
  Registriraj se buttons and by the hero CTAs; the current `/login` and `/signup`
  pages stay as the no-JS / deep-link fallback (`?next=` keeps working).
- Backdrop: `rgba(0,0,0,.55)` + `backdrop-filter: blur(6px)` — add the blur to
  `.fb-modal::backdrop`, it is the part that makes it feel premium.
- Segmented Prijava | Registracija at the top: two `<button role="tab">`s in a
  `--surface-2` track, active one `--surface` + shadow (the same shape as the
  cjenik tier pills); the register pane shows the allowlist hint while
  `signup_open` is false.
- Inputs: our 12px radius is fine; raise height to ~48px on the auth form only,
  they are the whole content. Password field gets an eye toggle.
- Primary `.btn` full-width **or** left-aligned — not both a full-width button
  and a pill row. "Zaboravljena lozinka?" as `.tlink`, right-aligned.
- No Google/Turnstile in v1 — sign-up is invite-only; revisit with `SIGNUP_OPEN`.

## 3. "Dodaj na početni zaslon" install banner — BUILT 25.9.2026 (`#a2hs` in base.html)

**Theirs:** a fixed card at the bottom of the phone viewport (16px inset each
side and from the bottom, ~358px wide), dark, holding: app icon, app name,
title "Dodaj na početni zaslon", a two-step instruction that is
**platform-specific** (iOS: "Pritisni Share → Odaberi Dodaj na početni zaslon";
Android: "otvori izbornik preglednika → Add to Home screen", and if the browser
offers the native prompt, a real install button instead), a ✕ in the corner, and
a **full-width** quiet "U redu" dismiss (translucent white, 12px radius). The
app's own icon sits top-left with name + "Dodaj na početni zaslon" beside it —
it reads like an OS install sheet, which is the point.

**Why it works:** a PWA that nobody installs is a website; the banner turns the
manifest into a habit. Instructions differ per platform because iOS has no
install prompt API.

**Map to QMT** (QMT is already a PWA: manifest, icons, `/sw.js`):
- Show only on phones (`pointer: coarse`), only in a browser tab (not when
  `display-mode: standalone`), only to logged-in clients, after their second
  visit, and never again once dismissed (`localStorage['qmt-a2hs']`).
- Android/Chrome: capture `beforeinstallprompt`, show a `.btn.btn-sm` "Instaliraj"
  that calls `prompt()`. iOS: the two-step Share instruction with the share
  glyph. Both: "U redu" as `.act.act-quiet`.
- Style with our tokens: `.card` on `--surface`, hairline, 16px radius,
  `--shadow`, icon from `static/icons/`; 16px inset; `z-index` above the topbar.

## 4. Photo card with metadata chips

**Theirs:** the hero is one large photo card (~1060px wide, 40px radius, dark
gradient at the bottom) with small pills pinned to the corners — "3/4x tjedno",
"Gym", "Početnici / Napredni" — and an italic uppercase title over the image.

**Map to QMT:** the online programme catalogue (`/treninzi`) is the natural home:
one card per programme with its razina × cilj as chips ("Srednja", "Gornji dio")
and the trainer's photo/video still behind. Our chips are `.chip`; the uppercase
title is PT Sans by default. Use once the owner's videos exist.

## 5. Pricing presentation

**Theirs:** three plans side by side, each with a monthly price and the annual
price under it ("20 EUR / mj · 240 EUR / god"), named plans (Shape Home / Unlimited
/ Gym), the middle one visually preferred. No "na upit" anywhere.

**Map to QMT:** already close (`/cjenik`). What to take: show the **annual** price
under the monthly the day annual Prices exist in Stripe — it is where the
subscription margin is; and prefer one tier visually (the 12-treninga pill is
already preselected — give it a "najpopularnije" chip).

## 6. Social proof section

**Theirs:** "Rezultati govore sami za sebe" — a before/after photo carousel,
plain dark background, no cards. **Map to QMT:** the landing's gallery band is the
slot; the owner supplies photos with consent. Keep captions optional.

## What not to borrow

- Their body text and headline colours vary by section (black on gradient,
  white on dark); QMT keeps two text colours per theme — consistency is the
  smaller app's advantage.
- Italic display type: PT Sans uppercase is our display voice; do not add Rubik.
- Six background colours; we have three greys and stay there.
