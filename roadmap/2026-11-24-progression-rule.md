# The "no harder training after a hard one" rule (24.11.2026) — parked

The owner (24.11.2026): "One more thing we need to implement for online trainings. For
example if someone answers a survey and says a training was hard, then the same exercise
in the next training shouldnt increase its difficulty but stay as it is. The next harder
training gets postponed then. Lets say that if the user says the exercise was 7/10 or
harder, the training difficulty does not increase in the next one."

Then, the same day: "The rule about raising difficulty will come later. I will need to
talk with Amir some more about this." **Nothing is built; wait for the owner.**

## Why it needs an answer first

Nothing in the app gets harder on its own today: a day's sets and reps are what Amir
typed, the player pre-fills the weights the client used last time (`db.last_sets`), any
day of a programme opens at any time, and the effort (napor 1–10) is asked once per
training on the finish screen, not per exercise. So the rule needs something that
increases. The three readings put to the owner:

1. **The programme is a progression** (Fable's recommendation): Amir orders a
   programme's trainings from easier to harder (his exercise names already do: "Bočni
   plank 1. razina", "2. razina"), switched on per programme. A pass finished with napor
   6 or lower opens the next training; 7 or higher offers the same one again and keeps
   the harder one closed until a pass scores below 7. To confirm with it: the score that
   counts is the training's overall napor, and the later trainings are locked, not just
   "not recommended".
2. **The app raises the load itself**: the player suggests a little more than last time
   for the same exercise (+2.5 kg, or one more rep) unless the last training was rated 7
   or higher.
3. **The client's level moves up**: after enough trainings rated below 7 the client goes
   from početna to srednja; a hard rating delays it.
