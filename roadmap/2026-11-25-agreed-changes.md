# Changes agreed with Amir (25.11.2026) — the queue

The owner sent his own chat notes to Amir (18:06–18:13) and said each in English. Amir's
morning message (06:52) is the first block. Nothing here is built until STATUS.md says so.

## Amir, 06:52 (feedback on the karton)

> Sve je napravio. 1. U ograničenja i bolovi treba dodati mogućnost da se doda slika ili
> pdf. 2. Tjelesna masa tu bi promijenio u tjelesna kompozicija gdje opet mogu dodati pdf
> ili sliku ili samo upisati ručno masu.

## The owner's notes to Amir, 18:06–18:13, and his words to Fable

1. "za ove kaj idu u gym da mogu složit treninge isto kao i Amir kad radi online treninge"
   — "When someone finishes a training in the gym, he should be able to input everything
   he did there from the list of exercises like Amir does it for online trainings. He can
   put the exercise, number of reps, difficulty etc like so far when giving a feedback."
   **Exists since 23.11.2026**: the osvrt's "Vježbe" block and "+ Dodaj trening izvan
   termina" on the karton (exercises from the library, sets × reps × kg). The owner was
   told where; what may still be missing shows after he tries it.
2. "Za krugove dodat da može dodat vježbe i onda on označi koje krugove koje je odradio.
   Pauza ide na kraju kruga a između vježbi nikakva pauza. (Broj krugova, kilaža, itd
   iste vježbe kao i ove ubaci)" — "For circular exercises, we need to allow Amir to add
   exercises which go into one circle of exercises. And for each of those exercises, the
   number of reps, the weight if applicable etc." (sent with a screenshot of the editor's
   "Kružno" form over an empty part, "Nema vježbi"). Fable's reading: add exercises
   right inside a part; a planned weight per exercise ("Kilaža"); in the player a circuit
   is ticked a ROUND at a time (one screen per round: its exercises, reps and weights),
   the rest after the round, no pause between exercises.
3. "search unutar kartona vježbe kad je radio i kaj je zadnje radio" — "We need a search
   bar for each user. Admins can access everyone's karton and search a particular
   exercise": on a karton, pick an exercise he has logged and see when he did it and
   what he did last.
4. "svugdje ikad uvest pravilo da može uređivat" — "If there is a place where he is not
   allowed to change text, lets allow it." Fable's scope: every page a member or a guest
   sees (raspored, the online treninzi pages, the player, the finish screen, profil, the
   login pages and the modal); not the staff-only admin screens, the emails, the routes'
   flashes and refusals, or sentences built around a value.
5. "odjava umjesto 12 sati neka bude isto 4 sata" — "Instead of 12 hours ahead of
   training for a cancellation, lets allow 4 hours." `CANCEL_CUTOFF_HOURS` 12 → 4 (the
   code's default and the box's env file, which sets it).
6. "Ako je odradio sklek na prvom treningu i teška mu je, neka ta ista vježba idući put
   bude ista ili mrvicu lakša ovisno kaj je recenzirao" — "For the feedback on a
   particular exercise online, if someone gave a feedback on a particular exercise of 7
   or harder then the next appearance of that particular exercise does not increase its
   difficulty but stays the same or if its 9 or 10 out of 10 difficulty, then it gets
   slightly reduced by a certain percentage." This answers
   `2026-11-24-progression-rule.md` (reading 2: the app adjusts the load of the same
   exercise next time), with a rating PER EXERCISE. Fable's proposed numbers, put to the
   owner: rated 6 or lower, a little more next time (+5% of the weight, to the nearest
   0.5 kg and at least +0.5 kg; a bodyweight exercise +1 rep; a timed one +5 s); 7 or 8,
   the same; 9 or 10, a little less (−10%, at least one step down).

Also the same day, on the karton's layout: "Everything should be one above the other and
the 'dnevnik treninga' should be last", then "This is a good order, but if you have more
room on the PC layout, you can use more columns, you can be the judge."

## The order of the builds (one at a time: one tree, one test database)

1. The karton's texts editable in place, with the new layout (in progress).
2. The karton again: Amir's documents and "Tjelesna kompozicija", the exercise search,
   and the 4-hour cancellation.
3. The player: circuits ticked a round at a time, a planned weight, exercises added
   inside a part; then the per-exercise rating and the adjusted load.
4. Editable text on every member-facing page.
