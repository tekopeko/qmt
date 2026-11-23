# Karton: Amir's wish list (23.11.2026) — queued

Amir's message, relayed by the owner on 23.11.2026, verbatim:

> Ok, treba mi karton svakog polaznika u kojem će biti ime, prezime koje će oni sami
> ispuniti. Znači ime, prezime, sve što je u anketi, tjelesna visina, tjelesna masa, onda
> slika jednomjesečno koja će biti proizvoljna i po želji, i u principu treba mi, ako ćeš
> moći za svakog klijenta, da si on može sam upisati koji trening je radio, to je da li će
> to biti u treninzima ili gdje. I po mogućnosti, a ja mislim da to nije neki preveliki
> problem, izračun maksova, na primjer ako radi bench, napravi mi sa 90 kila 6 ponavljanja,
> ono piše i da mu automatski kalkulira njegov maks u benchu. Ako napravi, ne znam, 9 zgib,
> ok, kužiš, rameni potisak sa 40 kila 8 ponavljanja, da mu se izračuna za rameni potisak
> maks itd. Znači maksimalne vrijednosti izračunane, to je procijenjene temeljem određene
> vježbe. Da, to bi bilo u kartonu. I naravno da u kartonu može ući u povijest svojih
> treninga i svega ostalog. Naravno tu će biti ograničenja koja će se on napisati, bolovi
> itd.

The owner's decisions the same day: **height needs no history**; everything else as
listed. **Queued behind** the tag chips / "Core" / level-only matching build of 23.11.2026;
nothing started.

## What already exists (every member, whatever plan)

- `/karton`: the questionnaire's result and answers, the diary (every gym termin with its
  osvrt — napor 1–10, osjećaj, a free comment, or "Nisam bio/la" — and every finished
  online pass with its sets), the termini. `/karton/{id}` is Amir's read-only view.
- `/profil`: name, surname, birth date, phone, filled by the member.
- The online player's set log (exercise from the library, sets × reps × kg, `WorkoutLog.done`).

## What is new

1. **An exercise log on a gym termin.** Today the osvrt has only the free comment: no
   exercise picker, no sets / reps / kg. The natural shape is the player's set log on the
   termin's osvrt (exercises picked from the library with the folded search, sets × reps
   × kg or seconds), stored so the maxes below can read it. Open: where it lives on the
   page (the osvrt dialog after login, the karton row, the calendar's termin) and whether a
   member may log a training he did on his own, outside a termin ("da si on može sam
   upisati koji trening je radio … da li će to biti u treninzima ili gdje").
2. **Estimated maxes** per exercise on the karton, from any logged set, gym or online: a
   standard formula (Epley, 1RM = w × (1 + reps / 30): 90 kg × 6 ≈ 108 kg), the best
   estimate per exercise, and when it was set. Bodyweight exercises (9 zgibova): reps
   alone, or bodyweight + load if the weight is known. Online passes can feed it from day
   one.
3. **Height** (one value, no history) and **weight** (with its history, a value per date)
   on the profile or the karton; Amir reads them on his view.
4. **A monthly photo**, optional, the member's own: stored like the other media (R2 on
   prod, auth-gated `/media`), one per month at most or free, shown on the karton as a
   dated row; only the member and staff see it.
5. **Ograničenja / bolovi**: a free text of the member's own on the karton, beside the
   questionnaire's pain and injury answers.

## Before the brief

- Who edits what: the member his own values; Amir reads all of it on `/karton/{id}` (and
  may need to log a termin's exercises for a member who did not).
- The gym log's data model: reuse `WorkoutLog` (a pass with no programme day, the termin's
  id in a new column) or a new table; the maxes read both.
- The formula and its words on the page ("procijenjeni maks").
- The photo's size cap and its deletion.
