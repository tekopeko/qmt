# The plan agreed on 28.11.2026 — an admin view of its own, status colours, members grouped by plan

What the owner and Fable settled on 28.11.2026, after the Karton and Dvoranski treninzi
searches of 27–28.11. Nothing here is built until STATUS.md says so.

## The owner's words

"we changed our minds and I would like to separate all admin operations in the admin
menu. So the 'gledaj kao član' stays, but I would remove the search bar and all other
admin operations from the Karton and Dvoranski treninzi and Online treninzi into separate
admin tabs in admin->Kartoni admin->Dvoranski treninzi and admin->Online treninzi and all
functionalities of an admin are there. I am also thinking about completely removing the
'normal user' part of the Admin account i.e. so that I and Amir have only admin related
tabs."

Then, of two accounts for one person: "What do you think of an option where we have a
button which switches from his admin and his member view? Then he doesnt need to have 2
different accounts? I am planning to add also a feature where a user's logo is in a
different color depending on his subscription status (green->active, amber -> grace
period, red->inactive subscription). We can then have a separate color for the admin logo
… The Admin view gets its own color for an admin."

"Whenever a user is displayed, his name should also be colored in green, amber or red
depending on the subscription status. For example in the 'gledaj kao član' or in the
karton search bar of users."

"We should also somehow separate users which are for gym and for online trainings … Amir
just wants to somehow group this many users he will have."

## What was settled

**Two views of one staff account** (the owner: a switch, not two accounts; "yes"). A
trainer's and the owner's account has an admin view and a member view, switched in the
avatar's menu.

- **Admin view**: three tabs, each a menu ("Three tabs is fine"), and the owner's fourth:
  **Članovi** (Kartoni: a member's karton, read and write; Trenutne članarine; Gledaj kao
  član; Korisnici, the owner's), **Treninzi** (Raspored: the week with its rosters;
  Termini; Dvoranski treninzi: a member's trainings prepared and added, and Predlošci;
  Online treninzi: the programmes; Vježbe), **Sadržaj** (Tekstovi, Početna, Upitnik,
  Vodič), **Statistika** (the owner's).
- **Member view**: the member's tabs as a member has them, the staff member's own karton
  and trainings in it; no member search, no programme table, no templates. A staff
  account there counts as holding every plan ("yes"), and books no termin, as today.
- **Texts are edited in place in the member view and on the shared pages**, as today.
  The pill inside "Gledaj kao član", agreed an hour earlier, is not built: the member
  view makes it needless.
- The front page and Prehrana are the public site, shared by both views.
- **After a login a staff account is in the admin view** ("By default when logging and
  opening the Admin's account I would put it in the admin view mode") and lands on the
  front page, as every login does; the switch lands there too ("why not landing page?
  The landing home page should exist in both modes").
- **The bar follows the page**: the account remembers its view, the switch changes it,
  and a page of the other side opened directly (a bookmark, a typed address, a link) is
  shown and takes the view along, so nobody meets a member's page under the admin bar or
  an error at a saved link; a shared page keeps the view it was opened in.
- "Gledaj kao član" stays as it is (the whole app as a member). The searches leave the
  member tabs: a member's karton is opened from Članovi → Kartoni, his trainings from
  Treninzi → Dvoranski treninzi, each in the one-tab view built on 28.11.

**A member's status, one rule, one colour** (the avatar, and his name wherever a member
is shown): amber when any of his plans is in its grace week (a payment is due); else
green when any plan runs; else red when he had a plan and none runs; grey when he never
had one ("neutral grey is fine"). The admin view's avatar has a colour of its own, picked
at design time, unlike the four, in both themes. No word beside the name ("no need for
the extra word for the status"): the colour is the sign; a label a screen reader reads
stays, unseen. **The "Gledaš kao" strip names the member in his colour too** ("I would
recolor the user here as well, maybe then choose a different color for the 'gledas kao'
strip"): amber now says a payment is due, so it stops meaning "someone else's account":
the strip and the buttons that lead into a member's account ("Kao član →", "Otvori kao
član", "Otvori →") take the admin's colour, the strip a dark bar in both themes as the
topbar is, the name on it in the member's status colour.

**Members grouped by what they hold now, never by a stored group.** A member is a gym
member while a gym plan of his runs (grupni, individualni, poluindividualni,
rehabilitacija), an online member while his online plan runs, both when both, and he
moves by himself when he switches. The member lists carry four chips: Svi · Dvorana ·
Online · Bez članarine. "Bez članarine" is every member with no running gym or online
plan (lapsed, or never subscribed): apart from the other two, and with them it is
everyone. Dvoranski treninzi opens on Dvorana, Kartoni on Svi. A list of online members
under Online treninzi is not built ("I dont see a need for that yet since that wouldnt
give anything the Karton tab doesnt already provide").

## The builds, in the agreed order

1. **What is in progress** (its own entries in STATUS.md): staff plan a member's training
   outside a termin ahead, it counts in his membership, only for gym members; the edit
   pill hidden while the phone's menu is open.
2. **The two views and the admin tabs.** The switch; the admin bar and its pages (Kartoni
   and Dvoranski treninzi as lists of members that open the one-tab view; the programme
   table and the templates under Treninzi); the searches, the table and the templates off
   the member tabs; a staff account's member view.
3. **The status colours**: the avatar and every member's name.
4. **The chips** on the member lists.

Later, if asked: a list of online members under Online treninzi; one screen for member
and exercise.

## What was built (28.11.2026; STATUS.md has each entry)

All four builds, the same day, in this order. Two things changed on the way, both the
owner's: the switch and the login land on the front page, not Raspored ("The landing home
page should exist in both modes"), and Početna is a plain tab of the admin bar, first as in
a member's row, not an item of Sadržaj ("on the same place as the user view so that its
always available"). The admin's colour is an indigo ("Yes, the indigo is fine, especially
in the dark mode. LAter on we might change the colors on the light mode."), and with it the
"Gledaš kao" strip went dark and the buttons into a member's account left amber, which now
says a payment is due.
