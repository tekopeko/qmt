# Online treninzi: a library of exercises, programmes made of days, a player — spec (29.10.2026)

Status: **spec, awaiting the owner's OK.** Written by Fable from the owner's answers of
29.10.2026; nothing of it is built. Builds in three stages (below), each shippable.

## What the owner asked

"For each group he needs to add the training programme per days which the user will
declare as an exercise performed one by one. We should have a database of exercises which
he can choose from and add them to different training programmes that will be modular.
Each exercise will have a video connected to it which will show the exercise and show what
one rep means." (Shape Club's model: a library of exercises with a short looping video
each, workouts assembled from it, a player that walks the client through exercise by
exercise.) His decisions:

1. **Days:** "Dan 1, … Dan N with suggested days in the week but the user can do them
   whenever he wants."
2. **Per exercise:** sets × reps, or seconds, rest between sets, a note. "That is it for now."
3. **Videos:** Amir records them on a phone, one per exercise showing one rep; the guide
   (`/vodic`) also promises an intro video and a full training video per training (= per
   day). 100 MB a video, "we will change that when we get the actual videos". No
   transcoding for now.
4. **The tick:** stored, "so that we have a record of a user's history. He can repeat the
   training if he wants."

What stays: the matching (a client sees the programmes of their razina × cilj, idea 3), the
tiers' bullets unenforced, the auth-gated `/media` and the R2 backend (`storage.py`).

## Today

A programme (`Program`: title, level, goal, intro) is a flat list of `ProgramItem`s typed by
hand (title, body, one optional media file, image or video). No shared library, no days, no
per-exercise tick, no history of online trainings (the karton's `TrainingLog` is the osvrt
of a termin in the gym).

## Data model

- **`Exercise`** — the library. `name` (160), `instructions` (Text: how it is done), `rep_note`
  (Text: what one rep is), `video` (a stored media name, or NULL), `tags` (Text, comma list:
  muscle group / equipment, free words for now; the later routing by equipment reads them),
  `created_at` / `updated_at`. An exercise used by any day cannot be deleted (refused with
  the programmes named); an unused one can. Nothing else is soft: a renamed exercise is
  renamed everywhere, which is the point of a library.
- **`Program`** stays as it is (the nine matched slots + whatever Amir adds).
- **`ProgramDay`** — `program_id`, `position` (Dan 1 … Dan N, the editor's ↑ / ↓),
  `title` (160, optional: "Cijelo tijelo"), `weekday` (0–6 or NULL: "preporučeno:
  ponedjeljak"; a suggestion only, never a gate), `intro` (Text), `intro_video`,
  `training_video` (stored media names, the guide's two videos, optional). Positions unique
  per programme, deferred (the announcements' / questions' pattern, so ↑ / ↓ swap in one
  commit).
- **`ProgramDayItem`** — `day_id`, `position`, `exercise_id` (FK, RESTRICT), `sets` (int),
  `reps` (int, NULL) or `seconds` (int, NULL): one of the two, `rest_seconds` (int, NULL),
  `note` (Text). Replaces `ProgramItem`.
- **`WorkoutLog`** — the client's record of one pass through a day: `user_id`,
  `program_id`, `day_id` (SET NULL on delete: the row keeps `day_title` and `program_title`
  snapshots), `started_at`, `finished_at` (NULL while in progress), `done` (JSON: the
  items ticked, `[{"item": id, "name": "Čučanj", "at": iso}]`, snapshots so a later edit of
  the day never garbles the history, the upitnik's rule), then the osvrt at the end:
  `effort` (RPE 1–10), `feeling`, `note` (the termin osvrt's shape, `FEELING_LABELS`). A day
  can be repeated: every pass is a new row. One row in progress per (user, day) at a time;
  a pass left open can be resumed or dropped.
- **Migration:** each existing `Program` gets one day ("Dan 1", no weekday) holding its
  items in order; each item's `title` becomes an `Exercise` (one per distinct name; `body`
  → `instructions`, a video media → `video`, an image media is dropped with a note in the
  log), and the day's items point to them with sets / reps empty. `program_items` goes.
  Downgrade, best effort: the days' items back as flat items.

## Pages

**Amir (trainer / owner), plain admin forms, the `/admin` style, not the in-place copy editor:**

- `/treninzi/vjezbe` — the library: a searchable list (name, tags, a ✓ when it has a video,
  "u N programa"), "+ Nova vježba"; `/treninzi/vjezbe/{id}`: name, instructions, rep note,
  tags, the video (upload, replace, remove; the player shows it right there), "Obriši"
  (refused while used). Admin ▾ gets the item "Vježbe".
- `/treninzi/{id}` (the programme, as now) grows days: a list of day cards (Dan 1 … Dan N,
  the weekday, the count of exercises), "+ Dodaj dan", each day's ↑ / ↓ and "Obriši dan"
  (two taps). `/treninzi/{id}/dan/{day}`: title, weekday select, intro, the two videos, then
  the exercises: a row per item (the exercise's name, sets × reps or seconds, rest, note,
  ↑ / ↓, ✕), "+ Dodaj vježbu" with a picker from the library (search by name / tag; "+
  Nova vježba" opens the library form and comes back).

**The client:**

- `/treninzi` as now (their matched programmes) → `/treninzi/{id}`: the programme's intro,
  its days as cards: "Dan 1 · Cijelo tijelo · preporučeno pon", the state said in words
  ("još nije odrađen" / "odrađen 2× · zadnji put 12.11." / "u tijeku — nastavi"), any day
  openable any time.
- `/treninzi/{id}/dan/{n}`: the intro, the intro video first (the guide: "always watch the
  intro video first"), the full training video, the list of exercises (name, sets × reps),
  "Kreni" (starts a `WorkoutLog`; "Nastavi" when one is open).
- **The player** `/treninzi/{id}/dan/{n}/vjezba/{k}` — one exercise per screen, the
  questionnaire's one-task layout (the small pill, the brand alone, a 640px column, the
  upitnik's progress bar "3 / 8"): the rep video (`<video playsinline muted loop
  preload="metadata">`, a poster from the first frame), the name, sets × reps or seconds,
  rest, the note, the instructions folded under "Kako se izvodi", then ONE primary
  "Odrađeno" (ticks it in the log, goes on), a quiet "Preskoči", "Nazad". Works without JS
  (each tick a plain POST). The last screen: "Trening odrađen" + the osvrt (RPE, feeling,
  note, the karton's prompt reused) → `finished_at`.
- **The karton** shows online trainings in the diary beside the termini ("Dan 2 ·
  Cijelo tijelo · 6/6 vježbi · 12.11.", the osvrt), and Amir's read-only view the same.

## Videos

- Upload on the exercise form and the day form: mp4 / mov / webm, up to `VIDEO_MAX_MB`
  (env, default 100), through `storage.py` (local disk in dev, R2 on prod), served only by
  the auth-gated `/media` (presigned 307 on R2), never cached by the SW.
- **No transcoding now**: the file is stored as it comes and the browser plays it as it is.
  The known trap: an iPhone records HEVC (`.mov`) by default, which Chrome on Android and
  Windows does not play; Amir sets Camera → Formats → "Most Compatible" (H.264) before
  recording, and the upload form says so. Transcoding (ffmpeg on the box: H.264 720p, a
  poster frame, a capped bitrate) is the later step if the real videos need it.
- Sizes: 100 exercises × ~20 MB ≈ 2 GB on R2; fine.

## Stages

1. **The library** — `Exercise`, the two admin pages, the video upload, the migration of
   today's items into it (the client's pages unchanged: a programme still lists its
   exercises, now from the library).
2. **Days** — `ProgramDay` / `ProgramDayItem`, the day editor, the client's programme page
   with day cards and the day page (no player yet: the day page lists the exercises with
   their videos).
3. **The player and the history** — `WorkoutLog`, the one-exercise screens, the osvrt at the
   end, the karton's rows, "u tijeku" / "odrađen N×".

## What Shape Club's Gym Program adds (captured 30.10.2026, `data/design-reference/shape-club/app/app-27…33`)

The owner was right: a Gym Program training there is exercise by exercise, and it
holds more than the spec above. Each is a decision for the owner before stage 1:

1. **A set log, not a tick.** Under the current exercise a table SET · REP · KG, a
   row per planned set, REP prefilled with the plan and KG with the last weight,
   "+" to add a set, "Spremi" saves it and the exercise turns green in the list.
   Proposed for QMT: `WorkoutLog.done` becomes a per-exercise entry of sets
   `[{"reps": 10, "kg": 20}, …]` (seconds for a timed exercise), saved with one
   button; a tick is the case of saving the plan unchanged. The karton then
   shows real progress (the weights over time), which the owner wants kept.
2. **Sections within a day.** "ZAGRIJAVANJE" and "TRENING" (a cool-down likely).
   Proposed: `ProgramDayItem.section` (zagrijavanje / trening / istezanje), the
   list grouped by it.
3. **The whole day's list beside the player**, every item with its dose
   ("3 X 10 REP", "2 X 30 SEK"), "Odmor između serija", a note, ▷ to jump to it,
   and the current one outlined; a segmented bar at the top, one segment per
   exercise. Proposed: the same on QMT's day page (on a phone the list under the
   player, the bar on top), in QMT's tokens.
4. **Swapping an exercise** for a similar one ("Zamijeni vježbu — Slične
   vježbe"; the log stays with the training). Needs "similar exercises" in the
   library, Amir's work per exercise. Proposed: stage 4, after the three, if the
   owner wants it; the library gets an `alternatives` relation then.
5. **A first-open tour** (six coach marks). Proposed: later, if at all; the
   questionnaire's guide pattern (`/vodic`) can carry a short "kako se koristi"
   text instead.
6. **Music links** (Spotify / YouTube). Not for QMT.

## Open, to settle with Amir through the owner

- Tags: free words are enough for now, or a fixed list (mišićna skupina, oprema)?
- A cap on days per programme (none planned; 1–7 expected).
- The osvrt at the end of an online day: the termin's three fields, or fewer?
