---
name: qmt-design
description: >-
  QMT's design system and UI review method — the one source for fonts, colours,
  buttons, cards, spacing, states, modals, and the phone-first verification every
  screen must pass. Use this skill for ANY change that touches what a user sees:
  editing a Jinja template or CSS in src/qmt/web/templates, adding a page, button,
  form, card, banner or modal, restyling anything, reviewing a screenshot the owner
  sent, making something "look more professional / consistent / cleaner", or
  comparing QMT to another app. Trigger even when the request is small ("just move
  this button", "change that colour") — consistency is exactly what small edits
  erode. Also use it when asked to audit, QA or test the UI on phone and desktop.
---

# QMT design

QMT is a small Croatian studio's booking app. Its look comes from the logo — red
on near-black — and from one idea: **a client on a phone, between two trainings,
should never wonder what a screen is asking of them.** Everything below serves
that. The system is already in the code; this skill exists so no change drifts
from it, and so every change is *measured* before it is called done.

Two references live next to this file. Read them when you touch the relevant area:

- `references/tokens.md` — every CSS token with its light and dark value.
  **Generated** from `base.html` by `scripts/extract_tokens.py`; never hand-edit it,
  regenerate it after a token change.
- `references/components.md` — the component catalog: which class to use for what,
  the exact hover/focus behaviour, and the page-level conventions (karton rows,
  pricing cards, calendar). Read before adding any control or card.
- `references/patterns.md` — patterns borrowed from stronger consumer apps
  (shapeclub.app, measured 25.9.2026): floating nav pill, login modal, install
  banner, photo cards with metadata chips, pricing tiers. Read when building
  something the app does not have yet.

## The system in one screen

**Type.** Two families, loaded once in `base.html`: **PT Sans 700** for display
(`--font-display`, always uppercase — `h1`–`h3` inherit this), **Inter** for
everything else (`--font-body`, weights 400–800). Body 16px / 1.55. Page titles
1.7–2rem, section titles 1.05rem, card titles 1.02rem, hints .82–.92rem. Numbers
that line up (dates, times, prices, counts) get `font-variant-numeric: tabular-nums`.

**Colour.** Named tokens only — never a raw hex that works in one theme. The palette
is deliberately small:

| role | token | use |
|---|---|---|
| page / card / inset | `--bg` / `--surface` / `--surface-2` | three greys, no more |
| hairline | `--line` | every border and divider |
| text / secondary | `--text` / `--muted` | there is no third text colour |
| brand | `--accent` (text) · `--accent-fill` (button fill) · `--accent-dim` (tint) | **the one loud colour — spend it on actions and the current state, never on decoration** |
| positive state | `--good` (text) · `--good-fill` / `--good-ink` (button) | "you have this", success |
| absence / caution | `--warn` (karton only, amber) | the one non-brand hue, defined per theme in `karton.html` |

Both themes are first-class: every token has a dark and a light value, the page
pre-paints the saved theme, and a design that only looks right in one is wrong.

**Shape.** Rounded, soft, no boxes: cards 16px, controls 12px, small buttons 10px,
pills 999px. Hairline borders (`1px var(--line)`) instead of heavy edges. One soft
shadow (`--shadow`) on cards; the red glow (`--shadow-btn`) is the **hero's
voice only** — a small button inside a card or table row carries no glow.

**Rhythm.** Page padding `clamp(14px, 4vw, 40px)`, content max-width 1100px,
cards padded 16–24px, 8/10/12/14/18/26px gaps. Related rows share one baseline:
when cards sit in a grid, reserve equal heights for variable text (`min-height`
on the copy block) and pin the footer with `margin-top: auto` so CTAs align across
the row — measured, not eyeballed.

## Buttons — pick by the question the row is asking

| class | shape | when |
|---|---|---|
| `.btn` | filled `--accent-fill`, 12px, glow | **the** primary action of a page or hero — one per screen |
| `.btn.btn-sm` | filled, 10px, **no glow** | the primary action inside a card ("Rezerviraj termin →", "Spremi") |
| `.btn-ghost` | surface + hairline | secondary action beside a primary |
| `.btn-quiet` | `--accent-dim` tint + accent text | a quiet accent action in a table row |
| `.act` | grey pill, 999px | the app's discrete row action — Uredi, Ispuni osvrt, Otvori raspored |
| `.act.act-quiet` | text-only pill | the least important action in a row — Obriši, Poništi, Upravljaj |
| `.tlink` | accent text, no underline | a link **inside a sentence**; never a pill mid-sentence |

Rules that came from real mistakes, keep them:

- **Same class → same look on `<a>` and `<button>`.** The base `button:hover` sets a
  red background; any custom class must declare its own hover background or a
  `<button>` goes red while the `<a>` beside it does not. `a.btn-sm`/`a.act` also
  need `text-decoration: none` explicitly.
- **No underlined links anywhere, resting or hovered.** Underlines read as
  unfinished. Standalone links become `.act` pills; in-sentence links are `.tlink`
  (colour shift on hover, no underline).
- **Hover deepens, never floods.** Tinted buttons get a stronger tint on hover
  (`color-mix`), not a solid fill — the amber "Nisam bio/la" once flooded solid and
  was called ugly within the hour.
- **Hover-only controls must stay reachable on touch.** Hide behind
  `@media (hover: hover)` only, and keep `:focus-within` as the keyboard path.
- **Removing anything a user wrote asks first.** Add `data-confirm`,
  `data-confirm-title`, `data-confirm-cta` to the form; `base.html` turns it into
  the styled dialog. No native `confirm()`.
- **Every row of actions shares one footprint** — same pill height, so right edges
  line up. Mixing a 31px pill with a 22px text button reads as misaligned even when
  the maths is right.

## States must be said, not implied

A card or row always states which situation the user is in before offering an
action: *"✓ Tvoja pretplata — obnavlja se 4.10."*, *"Aktivna članarina
(gotovina)"*, *"Nemaš ovu članarinu"*, *"Nisam bio/la"*. Colour reinforces the
statement (green = have, grey = open, amber = absence, red = act) but never
carries it alone — a razina badge says "Razina 2 od 3" under its colour ramp.
Only offer what the user can actually do: a guest never sees "Rezerviraj termin",
a plan-less client never sees a booking CTA, a subscribed client sees their own
tier's price rather than the range.

## Modals and prompts

One styled `<dialog>` idiom (`.fb-modal`): hairline card, 16px radius, backdrop
`rgba(0,0,0,.55)`, `margin: auto` restored (the global reset kills it), close ✕
top-right, `autofocus` on the **primary** action so the first thing the user sees
is not a focus ring on the ✕. Two buttons max, primary on the right. Used for the
post-login osvrt prompt and every `data-confirm`.

## Phones are the primary device — verify, don't reason

Before calling any UI work done:

1. Run the dev server with the demo seed and execute
   `python .claude/skills/qmt-design/scripts/audit.py`. It walks every page as
   anon / client / owner, both themes, 1280px and 390px, and reports overflow,
   WCAG-AA contrast, tap targets under 32px, unlabelled controls, missing alt,
   heading order. It compares against `references/audit-baseline.json` — the
   findings already reviewed (mostly the contrast checker's "ratio 1" on tinted
   elements) — and reports only what is **new**. Overflow must be 0 and new
   findings must be 0: fix them, or, after a deliberate review, re-record with
   `--save-baseline` and say why in the commit.
2. Take **one** Playwright screenshot per message (several large images in one
   session make later images unreadable) at the width that matters — usually
   390px — and look at it. Measure alignment with `getBoundingClientRect`, not by
   eye, when the question is "do these line up".
3. Touch targets: `@media (pointer: coarse)` grows `.btn-sm`/`.act`; keep new
   controls ≥32px on a coarse pointer.
4. Both themes. If a colour only exists in one `[data-theme]` block, it is a bug.
5. Text that sits on a photograph (chips, captions over an image) gets a
   `data-photo` attribute on its container: the audit counts it instead of
   scoring it, because no colour math can see the image. Keep such text white
   over a dark gradient (`.stage::after`) so it reads on any photo.

## How to make a change

1. Read the relevant reference (tokens / components / patterns).
2. Reuse an existing class; add a page-level rule only for a shape the app does
   not have, and put it in that page's `{% block head %}` with a comment saying
   *why* it exists. Promote to `base.html` when a second page needs it.
3. Run the audit, screenshot 390px, fix, re-run.
4. If a token changed, `python .claude/skills/qmt-design/scripts/extract_tokens.py`.
5. Commit with the reason in the message — the codebase's comments and commits
   explain *why*, and future edits depend on that.
