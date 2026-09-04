# Where the last session left off — 4.9.2026.

Read `CLAUDE.md` first; this file only carries what isn't obvious from the code.

## Deploy state

Everything is committed and pushed to `master` (auto-deploys to Railway →
qmt.mojimakrosi.com). Last commits, newest first:

- `cbc7244` topbar holds one row at every width (the YouTube header)
- `52cdab1` avatar dropdown: Profil, theme, Odjava
- `e45de2c` active membership becomes a door to what it unlocks
- `b8932a5` profil: članarina overview + billing history
- `b328562` payments ledger + owner statistika; entry profile lands on the homepage

All migrations apply automatically on deploy. 59 tests green.

## ⚠️ OPEN — the header still looks wrong to the owner

The owner reported the topbar/avatar menu "looks bad, doesn't fit" and, after
`cbc7244` deployed, said **"it's still broken"**. The last session could not see the
screenshots (image-size limit poisoned by earlier oversized images), so this was never
visually confirmed — **start here, with a screenshot in a fresh session.**

What was already measured and fixed (so don't redo it): before `cbc7244` the bar
wrapped to two rows between ~860 and 1200px (62px → 108px tall) and tab labels wrapped
at 861px. After the fix, a Playwright audit at 16 widths (1600 → 360) for both an owner
(8 tabs) and a client (5 tabs) reported: single row, bar 62–63px, zero bar overflow,
zero page overflow, account menu fully inside the viewport at 360px.

So whatever is still wrong is something the measurements don't capture — likely visual:
spacing, the menu panel's look, contrast, the "QMT" short wordmark, or the avatar
itself. Get one screenshot, then fix.

Useful audit snippet (drive with Playwright, `channel="chrome"`; the bundled Chromium
is version-mismatched on this machine):

```python
pg.evaluate("""() => {const tb=document.querySelector('.topbar');
  return {h: tb.getBoundingClientRect().height, ov: tb.scrollWidth-tb.clientWidth,
          pageOv: document.documentElement.scrollWidth-document.documentElement.clientWidth};}""")
```

## Owed by the owner (blocking, not code)

- Real prices for `/cjenik` (currently "na upit").
- Landing/service copy and exercise videos — he said he'd write the text himself.
- Stripe account for QUALITY MOVEMENT TRAINING d.o.o. + accountant's Fiskalizacija 2.0
  flow, before card payments can be built.

## Testing the whole pipeline on prod

1. As owner, open **Online treninzi** once — that creates the nine programme slots and
   fills them with default exercises.
2. Sign up with an unused allowlist alias (`tvrtko.doresic+qmt1@gmail.com`, `+qmt2`,
   `+qmt3` — check /korisnici for which are taken), verify by email (the owner gets a
   "Novi korisnik" notice at the same time).
3. Log in → bounced to the profile form → fill it → lands on the landing page.
4. Online treninzi tab is absent until the owner records an **Online trening** uplata on
   /clanarine; then the upitnik appears, and filling it reveals the matched programme.
5. /statistika (owner) shows the uplata; the client's /profil shows plan dates and
   billing history.

## Notes for the next session

- Croatian UI throughout; the owner reviews visually and by screenshot, so verify UI
  work in a real browser (Playwright) rather than by reasoning about CSS.
- Keep screenshots to one per message — several oversized images in one conversation
  make every later image unreadable.
