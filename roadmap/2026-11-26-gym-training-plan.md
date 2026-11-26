# The plan agreed on 26.11.2026 — acting as a member, and gym trainings built like online ones

Amir's feedback on the builds of 25.11. (a WhatsApp screenshot the owner sent), the
owner's notes to him, and what the owner and Fable settled in the conversation that
followed. Nothing here is built until STATUS.md says so.

## Amir, 07:50–08:10

> Brijem da je majstor sve odradio. Jedino nije složio na isti način ovaj dnevnik treninga
> koji oni sami upisuju. Tj. tu ne mogu staviti kružni dio. I u tjelesnu kompoziciju nije
> dozvolio da dodam dokument. I ja kao admin nigdje ne mogu vidjeti trenutne članove niti
> im zadavati vježbe. Kažem moram samo razraditi kako složiti ovo oko njihovih treninga
> koje sami upisuju da npr. nema nigdje da stavi kvačicu... Pauza itd...

What Fable found on prod the same day: no upload was refused (the log holds no
`POST /karton/masa`; he had opened two members' kartons, where the trainer's view is
read-only: the document field is on one's own karton, inside "Upiši"); every member is
listed on Admin → Trenutne članarine with "Karton →", which nobody would look for there;
the gym log is the plain form of 23.11. (exercise, sets, reps, kg: no parts, no circuit,
no tick, no pause).

## The owner's notes to Amir, 11:20–11:25

1. "Znači dođe netko na trening, Šoša im da vježbu, on si zapiše kaj mu je dao u
   aplikaciji i kolko je čega odradio na taj dan. Kolko je zadano a kolko je napravio i
   onda kvačica."
2. "dodat karton dopuštenje Šoši"
3. "reciklirat online trening izgled na karton trening"
4. "broj telefona neka bude obavezno ili mail barem, jedan neki kontakt mora bit"
5. "visinu maknut iz profila u karton i takve sitnice"

## What was settled (the owner's words, then the decision)

**The load next time** — "this is okay for now, but make sure this is rounded to a logical
number i.e. an integer for reps of pushups for example". Reps are whole already, weights
go in 0.5 kg; seconds were the odd one (30 s rated 9–10 gave 27 s): seconds move in steps
of 5.

**Circuits, one screen per round** — "yes, and this one screen will have multiple videos,
I think this is an okay design for now". Stays as built.

**Sets** — "Lets increase the 12 sets to 20 sets limit." Online and gym alike.

**Acting as a member** — "What if we have a user selection somewhere in the app for the
admins much higher in the hierarchy and then Amir can look at the app just like the user
sees the app and he can do everything the user does in the same way?" … "so that nothing
is lost in the communication or display between him and the user". Agreed, with Fable's
guardrails, none objected to:
- Staff (the trainer and the owner) step into a MEMBER's account only, never a trainer's
  or the owner's.
- A bar on every page says whose account it is and ends it; it also ends at logout and
  after 30 minutes idle.
- The member's rules hold there (no plan, no booking; the paket; the 4 h cutoff). The one
  exception, the owner's: staff edit a gym training after the member's window has closed.
- Closed there: card payments, and sending the upitnik (its consent is the member's own).
- Every change made this way is recorded (who, as whom, what, when) — "Only a record for
  me": the owner reads it, the member sees no mark.
- It lives in Admin ▾ ("Gledaj kao član", a search by name), with shortcuts on a termin's
  roster, on Trenutne članarine and on the trainer's view of a karton, which stays (it
  shows what a member never sees).
- It replaces the two things Fable had proposed first: a member search on the Karton tab
  and write access for the trainer card by card on a member's karton.

**Korisnici** — "Admin -> korisnici can stay only for me".

**The phone** — "If a user gave his email, and he did in order to register, then lets not
require the phone number mandatory, but if a user didnt give it, when he opens the app a
popup reminder should appear similarly how a popup appears as a notification to install
the app on the phone".

**The profile** — "Only height" moves to the karton.

**The gym training** —
- "I would remove the 'dodaj trening' and automatically add the training with its title
  already after a user booked it and he can already edit it 4 hours before the training up
  until the next day. Amir can also edit it later." … "and me of course, the owner." …
  "The training should have a date and time written on it so that there is no confusion
  which training they edit."
- "they should be able to edit this training in the exact same way like Amir does for the
  online trainings and Amir should be able to edit that as well"; Amir's "reciklirat online
  trening izgled na karton trening": the online day's editor and its player (parts,
  circuits, the tick per set, the pause).
- "Everyone does his own type of training. Amir wont prepare gym trainings ahead of time,
  but live. So either the user does it himself when he is there or Amir does it for them."
- **One screen, no "Kreni"** (later the same day): "Will the user be able to add
  exercises dynamically like add an exercise, do it, check that he did it and input the
  weight and number of reps and then add the second exercises only after? Maybe a whole
  'Kreni' kind of dynamic does not apply to gym trainings the best way." Fable agreed (the
  player assumes the whole training is known before it starts, true online, not in the
  gym) and proposed, and the owner took ("yes, design the third build this way"): the
  training is ONE page that grows as it goes. "+ Dodaj vježbu" is always there; an added
  exercise is a card, open, with what was given (zadano, optional: it fills the rows) and
  its set rows, which he corrects to what he did and ticks, a tick saving that set and
  starting the pause; the next exercise is added when he gets to it; "Završi trening" at
  the bottom is the osvrt. What carries over from online: the parts and circuits (a
  circuit ticked a round at a time), the tick, the pause timer, the optional rating, the
  clip under "Kako se izvodi", the templates (a slot is a card he taps to choose its
  exercise). What does not, for the gym: Kreni / Nastavi and the exercise-by-exercise
  walk, a separate editing screen for members (Amir keeps the full editor for his
  templates), the training's running clock. Online stays as it is.
- Exercises: "Amir said we dont separate exercises between online and dvoranski. They are
  all the same." No flag; the whole library everywhere.
- The rating: "I would still put the feedback per exercise available but optional. The
  automatic adjustment of reps is only for online". The osvrt at the end (Napor, Osjećaj,
  Komentar) stays.
- Templates: "the user should be able to choose a dvoranski programme as a template and
  then edit the exercises there" … "for gym trainings, we will devise two templates with no
  particular exercises connected to them. Two templates are the most popular which Amir has
  to create. So when choosing a dvoranski template, there will be several template which
  are only tagged for the gym but with no particular exercises, only slots to put them in.
  Also no hard cap on the number of exercises or anything." A template is a training of a
  dvoranski programme: its parts, which of them are circuits, and empty slots (a row with
  no exercise yet, optionally a hint and numbers) that the member or Amir fills from the
  library; a copy, the template itself never changed. Every gym member is offered every
  template (a gym-only member has no razina).
- Parts: "Lets have Glavni dio A, B and C but lets also allow Amir to rename them." A
  third main part, and a name of its own for any part of a training (Fable's reading: per
  training, so a template's parts say what they are; the default names stay).
- The diary shows each exercise planned and done; the exercise history and the maxes read
  it. The plain form of 23.11. goes; what it stored stays readable. "Trening izvan termina"
  stays for a training with no booking.
- A cancelled booking takes its training with it.

**Added the same day, after build 1 went live** —
- "can we add everything the trainer sees the admin (me) sees": the owner is staff by rule
  (`app._is_staff`), whatever his trainer flag; built with build 2.
- "the grammatically correct term should be 'otvori kao član' not 'člana'": the button is
  "Otvori kao član", and Fable applied the same rule to the feature's name, "Gledaj kao
  član"; built with build 2.

**Added in the evening, while build 3's first part was in review** (the owner testing
on the live site) —
- "Can we call this 'Tip Programa' instead of 'Tip Treninga' since that is the name of the
  Programme and not of the training. We have Program->Trening->Vjezbe hierarchy.": the
  label on both programme forms and its refusal's sentence; shipped with build 3's part A.
- Where staff open a member's app. He looked for it on his own Karton tab ("I still can't
  see an option to see the karton as another user here"), then, with a screenshot of a
  member's card on Trenutne članarine: "I would remove the 'Karton ->' and the 'Kao član
  ->' buttons here and only leave the 'Admin -> gledaj kao član option' as well as the
  'Otvori kao član' amber button on the Karton tab of the Admin and Trainer with a search
  bar where a user can be searched. The button to open as another user should also be in
  amber." And of the line above the cards ("Stranica koju vide članovi — cjenik, tekstovi
  i cijene uređuju se tamo: Moja članarina →"): "I would also remove this, this is now
  obsolete." Fable's reading and the one consequence it guards: with "Karton →" gone the
  trainer's read-only view has no link Amir can reach (Korisnici's is the owner's), and it
  is the only place that shows the upitnik's "Zahtijeva pregled", the pain flag and every
  answer; so staff acting as a member see those on his karton. Its own small build, after
  part A.
- The member's sex, for the grammar: "on login do we know the sex of the user and then to
  use the correct grammar instead of 'Tvoji online treninzi i treninzi koje upišeš
  sam/a.'" We do not (an account holds a name, a birth date, a phone, a height). Fable
  proposed an optional "Spol" on the profile, the slash forms ("sam/a", "bio/la",
  "siguran/na") resolved by it wherever a text prints, his own retyped texts too, as they
  are until a member says; the owner: "yes". Built after the gym training.
- One pytest at a time on the Mac (8 GB; other sessions test other repositories): wait for
  the others, targeted files while working, the whole suite once at the end of a step.

Not asked for, so not built: Amir preparing a termin's training for the whole group; a
gym/online flag on an exercise; blocks beyond the five parts ("if Amir needs more, he will
ask for a bigger change").

## The builds, in order (one at a time: one tree, one test database)

1. **Acting as a member, and the small things**: "Gledaj kao član" with its bar, its
   record and its shortcuts; seconds in steps of 5; 20 sets; the height on the karton; the
   phone reminder. (Live 26.11.2026, `65121a6`: STATUS.md.)
2. **A training's parts**: Glavni dio C, a part's own name, and in a dvoranski programme
   the empty slots (Amir's templates). (Live 26.11.2026, `fe64c69`: STATUS.md.)
3. **The gym training**: made at the booking, one page that grows as the training goes
   (add, zadano, tick what was done, the osvrt), started empty or from a template; the
   diary, the history and the maxes; the plain form retired. In two parts: **A**, the page,
   its rules, the diary (live 26.11.2026, `e92a6af`: STATUS.md); **B**, a part's own name and
   circuits ticked a round at a time, a dvoranski programme's training as a template, a
   slot's card.
4. **Where staff open a member's app** (the evening's addition above): the Karton tab's
   search and amber button, the two buttons and the obsolete line off Trenutne članarine,
   every such button amber, the trainer-only parts of the upitnik block while acting.
5. **"Spol"** and the slash forms resolved by it.
