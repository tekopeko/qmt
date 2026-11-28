"""FastAPI routes: login/signup, the week calendar, booking, trainer admin.

Small enough that auth is a helper called at the top of each route rather than
middleware — if this grows routes the way mojimakrosi did, promote it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from jinja2 import pass_context

from starlette.middleware.sessions import SessionMiddleware

from .. import auth, config, copy, db, grammar, mailer, payments, reminders, storage, upitnik
from ..models import (FEELING_LABELS, ONLINE_TIER_SLOTS, ONLINE_TIERS, PAYMENT_METHODS, PLAN_ABBR,
                      PLAN_LABELS, PLAN_TYPES, SECTIONS, SESSION_KINDS, SEXES, WEEKDAYS as DAY_WEEKDAYS,
                      add_month, alpha_key, duration_text, effort_of, fold, matches, plural, sub_month)

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """A daily job without cron infra: a background loop ticks every 6 hours.
    run_once() is claim-idempotent, so extra ticks and restarts are free, and a
    second replica racing this one is harmless."""
    import asyncio

    async def _tick():
        await asyncio.sleep(30)                    # let migrations/boot settle
        while True:
            try:
                sent = await asyncio.to_thread(reminders.run_once)
                if any(sent.values()):
                    print(f"[reminders] {sent}")
            except Exception as e:                 # never kill the app over email
                print(f"[reminders] failed: {e}")
            await asyncio.sleep(6 * 3600)

    task = asyncio.create_task(_tick())
    yield
    task.cancel()


class _ActingGuard:
    """Staff acting as a member (26.11.2026): the check before every route,
    _acting_guard (the section "staff act as a member" below). Pure ASGI:
    it reads the session, the query and the headers, never the body."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await _acting_guard(self.app, scope, receive, send)


app = FastAPI(title="QMT", lifespan=_lifespan)
# The guard is added FIRST: a middleware added later wraps the ones before
# it, so SessionMiddleware is outside the guard and the session (its
# scope["session"]) is there when the guard runs.
app.add_middleware(_ActingGuard)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, https_only=config.IS_PROD)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["COPY"] = copy.SLOTS      # the editable texts and their limits (_copy.html)
templates.env.globals["copy_items"] = copy.items_for   # a list slot's items (_copy.html, points)
templates.env.globals["copy_rows"] = copy.rows_for     # a rows slot's rows (_copy.html, rows)
templates.env.globals["copy_flag"] = copy.flag_on      # a flag slot: on or off
templates.env.globals["copy_image"] = copy.image_name  # an image slot: its file's name, or None
templates.env.globals["CAP"] = copy.CAP                # a text's cap, where no slot says it (_copy.html, field)
templates.env.globals["ANNOUNCEMENT"] = copy.ANNOUNCEMENT_SLOTS   # an announcement's fields (landing.html, #aktualno)
templates.env.globals["GYM"] = copy.GYM_CARD_SLOTS     # a gym card's fields (landing.html, #dvorana)
templates.env.globals["QUESTION"] = copy.UPITNIK_QUESTION_SLOTS   # a question's texts (upitnik.html)
# the guide's sections by number, 1 … 11: its slots are vodic.<n>.* (_vodic.html)
templates.env.globals["VODIC_SECTIONS"] = range(1, len(copy.VODIC_SECTIONS) + 1)
# the karton's texts by area, (caption, keys), for the panel "Svi tekstovi
# kartona" on a staff member's own karton in edit mode (karton.html, 25.11.2026)
templates.env.globals["KARTON_PANEL"] = copy.KARTON_PANEL
# an online tier's QMove card, whose title slot is the tier's name (moja_clanarina.html, Paket)
templates.env.globals["ONLINE_TIER_SLOTS"] = ONLINE_TIER_SLOTS
# an online programme's day (30.10.2026): its sections in their order, the
# weekday it suggests ("ponedjeljak"), and a noun after its count, "7 vježbi"
templates.env.globals["SECTIONS"] = SECTIONS
templates.env.globals["WEEKDAYS"] = DAY_WEEKDAYS
templates.env.globals["plural"] = plural
# a programme as the library's pages name it, "Booty build (napredna razina)"
# (vjezba.html: the programmes that hold an exercise)
templates.env.filters["program_name"] = db.program_name


@pass_context
def _gendered(ctx, text):
    """A text as this page's reader reads it (27.11.2026, the slash forms:
    grammar.gendered by the context's `rod`, _ctx): the filter `gendered`,
    which _copy.html's macros print every text through, and every flash
    and refusal a template prints. For a reader who has not said his sex
    (rod None, every guest) the text itself."""
    return grammar.gendered(text, ctx.get("rod"))


templates.env.filters["gendered"] = _gendered


@pass_context
def _copy_text(ctx, key: str, texts: dict[str, str]):
    """A slot's text where no span can hold it: an attribute (a confirm's
    words, a placeholder), a script's word, a select's option, and the
    templates' conditions on a text being there. As the page's reader reads
    it since 27.11.2026 (the slash forms, as _gendered), which no condition
    minds: a text resolved is never emptied."""
    return grammar.gendered(texts.get(key, copy.SLOTS[key].default), ctx.get("rod"))


# a price slot's text as the page prints it, and whether it is a number at
# all: "€" follows "50" and "od 30", not "na upit" (landing.html,
# _plan_price.html), nor an amount that carries its own (21.10.2026: a gym
# card's yearly price, typed with its sign where the landing added none,
# is its plan's price.<plan>.year_amount slot since migration 6e2b9d41c7a3)
templates.env.globals["copy_text"] = _copy_text
templates.env.tests["priced"] = lambda text: any(ch.isdigit() for ch in str(text)) and "€" not in str(text)


@pass_context
def _copy_on(ctx, key: str) -> bool:
    """Whether the element around slot `key` prints at all (25.11.2026, the
    member-facing pages' optional texts): always for an editor (an emptied
    text is his empty box, which edit mode shows: _copy.html's opt), else
    while the slot holds a text, so an emptied lead, hint, kicker, chip or
    empty line is no element for a reader, nor its gap."""
    return bool(ctx.get("can_edit_copy")) or bool((ctx.get("copy_texts") or {}).get(key, copy.SLOTS[key].default))


templates.env.globals["copy_on"] = _copy_on
# /tekstovi (25.11.2026): every plain text by page and area (copy.TEXT_PAGES)
templates.env.globals["TEXT_PAGES"] = copy.TEXT_PAGES


def _numeric(text) -> bool:
    """A text that holds a number at all, any digit ("50", "od 30", "60–80";
    not "na upit"): a price whose bazna cijena prints, a base that is one
    (23.11.2026: the Jinja test `numeric`, and copy_save's first price)."""
    return any(ch.isdigit() for ch in str(text))


templates.env.tests["numeric"] = _numeric
# every price's bazna cijena (23.11.2026): a price slot's base slot, a gym
# card's price column's base column (_plan_price.html's base, landing.html)
templates.env.globals["BASE_OF"] = copy.BASE_OF
templates.env.globals["GYM_BASE_OF"] = copy.GYM_CARD_BASE_OF
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

WEEKDAYS = ["Ponedjeljak", "Utorak", "Srijeda", "Četvrtak", "Petak", "Subota", "Nedjelja"]
WEEKDAYS_SHORT = ["pon", "uto", "sri", "čet", "pet", "sub", "ned"]
# the month view's label, "listopad 2026." (the nominative: it stands alone)
MONTHS = ["siječanj", "veljača", "ožujak", "travanj", "svibanj", "lipanj",
          "srpanj", "kolovoz", "rujan", "listopad", "studeni", "prosinac"]

# Where an ACTIVE plan takes you — every "aktivna članarina" state is a door,
# not a label. (path, the copy slot of the button's words: app.door.*, the
# gym owner's text since 25.11.2026, "Rezerviraj termin" …)
PLAN_LINKS = {
    "grupni": ("/raspored", "app.door.raspored"),
    "individualni": ("/raspored", "app.door.raspored"),
    "poluindividualni": ("/raspored", "app.door.raspored"),
    "rehabilitacija": ("/raspored", "app.door.raspored"),
    "online": ("/treninzi", "app.door.online"),
    "prehrana": ("/prehrana", "app.door.prehrana"),
}

# The prices (what the site says a plan costs) and the MojiMakrosi add-on's
# amounts are copy slots since 18.10.2026, price.<plan>.* and addon.*, which
# the gym owner edits in place; their defaults are copy.REFERENCE_PRICES and
# copy.MOJIMAKROSI_ADDON, the shop's numbers. They are every price a page
# shows: no Stripe Price overrides them (the owner's call, 18.10.2026: his
# friend's numbers are the truth, and Stripe's Prices are to be aligned to
# them). Code reads them through these two, over the edited texts
# (db.copy_texts(), the dict _ctx puts in a template as copy_texts); a
# template prints the same slots with c.t(), so an editor can open them.

def reference_prices(texts: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Plan -> (amount, unit), the monthly price as the site says it: the
    edited price.<plan>.* slots, else their defaults. No note: the
    price.<plan>.note slots left the registry on 21.10.2026 (a row one of
    them left in site_copy is never read)."""
    def text(key: str) -> str:
        return texts.get(key, copy.SLOTS[key].default)
    return {plan: (text(f"price.{plan}.amount"), text(f"price.{plan}.unit")) for plan in copy.REFERENCE_PRICES}


def addon_amounts(texts: dict[str, str]) -> dict[str, str]:
    """Where ("dvorana", "online") -> the MojiMakrosi add-on's amount in €:
    the edited addon.<where> slot, else its default."""
    return {where: texts.get(f"addon.{where}", copy.SLOTS[f"addon.{where}"].default)
            for where in copy.MOJIMAKROSI_ADDON}



def _safe_next(nxt: str | None) -> str:
    """Only same-app paths — a `next` from the query string must never become
    an open redirect to another site ("//evil.com", "https://..."). Nor a
    backslash or a control character anywhere in it (Fable's review,
    27.11.2026, when the exit of a member's view got a GET with `kamo`):
    browsers read "/\\evil.com" as "//evil.com", and a tab or a newline
    inside a Location is dropped by some."""
    if (nxt and nxt.startswith("/") and not nxt.startswith("//") and ":" not in nxt.split("?")[0]
            and "\\" not in nxt and not any(ord(ch) < 32 or ord(ch) == 127 for ch in nxt)):
        return nxt
    return "/"


def current_user(request: Request):
    """Who the request is for. While a staff member acts as a member (since
    26.11.2026, "Gledaj kao član": the session's as_user_id) it is that
    MEMBER, so every page and route behaves exactly as for him; the staff
    member is the actor, kept beside him (request.state.actor, and the pair
    as request.state.acting: _acting / _actor). Only a staff member acts, only as a member:
    _acting_guard drops a session that holds anything else before any route
    runs, and should one change under a request (an account made staff
    meanwhile) the answer is nobody, never the staff member himself."""
    uid = request.session.get("user_id")
    user = db.get_user(uid) if uid else None
    member_id = request.session.get("as_user_id")
    acting = None
    if user is not None and member_id is not None:
        member = db.get_user(member_id) if _can_edit_copy(user) else None
        if member is None or _can_edit_copy(member):
            request.state.acting = request.state.actor = None
            return None
        acting = (user, member)
    request.state.acting = acting
    request.state.actor = acting[0] if acting else None
    return acting[1] if acting else user


def _acting(request: Request):
    """(the staff member, the member) while the session acts as a member,
    else None (current_user's, read once a request)."""
    if "as_user_id" not in request.session:
        return None
    if not hasattr(request.state, "acting"):
        current_user(request)
    return request.state.acting


def _actor(request: Request):
    """The staff member acting as the member current_user returns, while he
    does; else None."""
    acting = _acting(request)
    return acting[0] if acting else None


def _is_owner(user) -> bool:
    """The app owner = the OWNER_EMAIL account (mojimakrosi's owner-by-email
    pattern). Only the owner manages roles; trainers run the gym. Ownership
    stays with the env var — it is deliberately NOT hand-over-able in-app."""
    return bool(user and config.OWNER_EMAIL
                and (user.email or "").strip().lower() == config.OWNER_EMAIL)


def _is_staff(user) -> bool:
    """Staff: a trainer or the owner, by rule (26.11.2026, the owner: "can
    we add everything the trainer sees the admin (me) sees"). The owner sees
    and may do everything a trainer does whatever his trainer flag (on prod
    his account carries it; this takes the dependence away), and keeps what
    is his alone (_require_owner: roles, /statistika, the acting record).
    Every decision about what a viewer sees or may do as staff asks this,
    never `is_trainer` alone; the flag itself is the datum /korisnici reads
    and grants (db.set_trainer*)."""
    return bool(user and (user.is_trainer or _is_owner(user)))


def _can_edit_copy(user) -> bool:
    """May this viewer edit the public copy in place, the announcements
    among it? Staff (_is_staff): the trainer and the owner."""
    return _is_staff(user)


def _has_online(user) -> bool:
    """May this user see Online treninzi at all? Staff always (the trainer
    and, since 26.11.2026 whatever his flag, the owner); clients only with
    an active `online` plan (the tab is a paid product, not a teaser)."""
    return bool(user) and (_is_staff(user) or "online" in db.active_plan_kinds(user.id))


def _has_gym(user) -> bool:
    """May this user see Dvoranski treninzi (27.11.2026, build 2 of
    roadmap/2026-11-27-dvoranski-treninzi-plan.md; the owner: "I would show
    the tab only to members with a gym plan. Similarly how a online training
    tab shows only to members with an online plan.")? _has_online's twin:
    staff always; a member while a plan that books termini runs
    (SESSION_KINDS: grupni, individualni, poluindividualni,
    rehabilitacija; active as active_plan_kinds has it, until dospijeće).
    While staff act as a member it is asked of the member (current_user):
    his plans decide, as for every tab."""
    return bool(user) and (_is_staff(user) or bool(set(SESSION_KINDS) & db.active_plan_kinds(user.id)))


def _pop_feedback_prompt(request: Request, user):
    """One-shot after login: the termini he still owes his training
    (db.pending_feedback: ended, inside the training's window, neither a
    finished gym training nor an osvrt or absence of before). The flag is
    popped on the FIRST page rendered, so the prompt asks once per login and
    never follows the client around the app. Already being on the karton,
    on the Dvoranski treninzi tab (27.11.2026: its open trainings listed)
    or on a training's page counts as answered — the ways in are right
    there. Since 26.11.2026 (build 3) its way leads to the newest owed
    termin's training (since 27.11.2026 /dvoranski/termin/<id>), where
    "Završi trening" is the osvrt."""
    if user is None or not request.session.pop("fb_prompt", False):
        return None
    if request.url.path.startswith(("/karton", "/dvoranski")):
        return None
    pending = db.pending_feedback(user.id)
    if not pending:
        return None
    latest = pending[0].starts_at.astimezone(config.TZ)
    # formatted here: the prompt renders on whatever page the login landed on,
    # and those contexts carry no tz
    return {"count": len(pending), "title": pending[0].title, "session_id": pending[0].id,
            "when": f"{WEEKDAYS_SHORT[latest.weekday()]} {latest:%-d.%-m. %H:%M}"}


def _ctx(request: Request, user, copy_texts: dict[str, str] | None = None, **extra):
    # while a staff member acts as a member: the bar over every page names
    # the member (kao) and its pages carry his id (base.html: body data-kao)
    acting = _acting(request)
    show_online, show_gym = _has_online(user), _has_gym(user)
    # a tab's view (27.11.2026, the session's as_scope): the page is the
    # member's, its top bar the staff member's own (his tabs, Admin ▾, his
    # avatar), every link of it the exit (base.html's bar_href); elsewhere
    # the bar is the page's user's, as it always was
    tab = acting is not None and "as_scope" in request.session
    bar = acting[0] if tab else user
    return {"request": request, "user": user, "weekdays_short": WEEKDAYS_SHORT,
            "actor": acting[0] if acting else None, "kao": acting[1] if acting else None,
            "kao_tab": tab, "bar_user": bar, "bar_staff": _can_edit_copy(bar), "bar_owner": _is_owner(bar),
            "bar_online": _has_online(bar) if tab else show_online,
            "bar_gym": _has_gym(bar) if tab else show_gym,
            "mojimakrosi_url": config.MOJIMAKROSI_URL,
            "show_online": show_online,
            "show_gym": show_gym,
            "plan_links": PLAN_LINKS,
            "signup_open": config.signup_open(),
            "signup_mode": config.signup_mode(),
            # in-place editable copy: the edited texts (a route that has read
            # them already passes its dict), and whether this viewer may edit
            "copy_texts": db.copy_texts() if copy_texts is None else copy_texts,
            "can_edit_copy": _can_edit_copy(user),
            # whose sex the page's slash forms read as (27.11.2026, the
            # filter gendered and copy_text): the user the page is for, the
            # member while staff act as him, None for a guest and for one
            # who has not said; the trainer's view of a karton passes the
            # member's (_render_karton)
            "rod": getattr(user, "sex", None),
            "feedback_prompt": _pop_feedback_prompt(request, user),
            "is_owner": _is_owner(user), **extra}


# ---------- auth ----------

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str | None = None):
    return templates.TemplateResponse(request, "login.html",
                                      _ctx(request, None, next=_safe_next(next)))


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...),
          next: str = Form("/")):
    dest = _safe_next(next)
    u = db.get_user_by_email(email)
    if u is None or not auth.verify_password(password, u.password_hash):
        from urllib.parse import quote
        return RedirectResponse(f"/login?error=Pogrešan+email+ili+lozinka.&next={quote(dest)}",
                                status_code=303)
    if not u.email_verified:
        # correct password but unproven inbox: re-issue the link instead of a dead end
        return _send_verification(request, u.email)
    # a new login is a new identity: whatever view as a member the session
    # held (26.11.2026) ends with the old one
    for key in _ACTING_KEYS:
        request.session.pop(key, None)
    request.session["user_id"] = u.id
    # Owed osvrti are asked for once, on the first page this login renders —
    # the flag only arms the prompt, _pop_feedback_prompt decides if there is
    # anything to ask about. Staff (the trainer, the owner) book no termini.
    if not _is_staff(u):
        request.session["fb_prompt"] = True
    # New clients first complete their basic info (ime, prezime, datum) —
    # the profil page explains itself; staff are exempt.
    if not _is_staff(u) and not u.profile_complete:
        return RedirectResponse("/profil?dopuni=1", status_code=303)
    # Homepage by default; back to the page that bounced them here otherwise —
    # someone who clicked "Rezerviraj termin" must land in the calendar, not
    # back on the landing page mid-task.
    return RedirectResponse(dest, status_code=303)


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse(request, "signup.html", _ctx(request, None))


@app.post("/signup")
def signup(request: Request, name: str = Form(""), email: str = Form(...),
           password: str = Form(...)):
    if config.signup_mode() == "closed":
        # the page itself says registration is closed; nothing is created
        return RedirectResponse("/signup", status_code=303)
    email = email.strip().lower()
    if not auth.email_ok(email):
        return RedirectResponse("/signup?error=Neispravna+email+adresa.", status_code=303)
    if not config.email_allowed(email):
        return RedirectResponse(
            "/signup?error=Registracija+je+samo+uz+poziv+trenera.", status_code=303)
    if not auth.password_ok(password):
        return RedirectResponse("/signup?error=Lozinka+mora+imati+barem+8+znakova.", status_code=303)
    if db.get_user_by_email(email) is not None:
        return RedirectResponse("/signup?error=Račun+već+postoji+—+prijavi+se.", status_code=303)
    try:
        db.create_user(email, name, auth.hash_password(password))
    except Exception:
        # check-then-insert race: two simultaneous signups for the same email —
        # the unique constraint wins, the loser gets the same message as above.
        return RedirectResponse("/signup?error=Račun+već+postoji+—+prijavi+se.", status_code=303)
    return _send_verification(request, email)


def _send_verification(request: Request, email: str):
    """Email the verify link, or in dev show it on-page. Never on-page in prod —
    there the link would be world-readable."""
    link = f"{config.PUBLIC_BASE_URL}/auth/verify?token={auth.make_verify_token(email)}"
    sent = mailer.send_verification_email(email, link)
    if not sent and config.IS_PROD:
        # /login, not /signup: an unverified member logging in lands here too,
        # and with registration closed the signup page would only confuse them
        return RedirectResponse(
            "/login?error=Slanje+emaila+nije+uspjelo+—+javi+se+treneru.", status_code=303)
    return templates.TemplateResponse(request, "verify_sent.html", _ctx(
        request, None, email=email, dev_link=None if sent else link))


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    # the shop window, not the door back in — logging out is not a prelude to
    # logging in again
    return RedirectResponse("/", status_code=303)


# ---------- editable copy ----------

@app.post("/copy/{key}")
def copy_save(request: Request, key: str, text: str = Form(""), index: str = Form(""),
              reset: str = Form(""), part: str = Form(""), remove: str = Form(""), add: str = Form(""),
              rod: str = Form("")):
    """Save one edited text (_copy_save), what is stored always the text as
    typed, its slash forms and all. Since 27.11.2026 (the slash forms) the
    editor's script posts the sex its page's reader reads as (`rod`: the
    editor's own, the member's on the trainer's view of a karton; nothing
    for none), and the answer then carries the text to show beside each it
    stores (_shown); with none, the answer as it was."""
    return _shown(_copy_save(request, key, text, index, reset, part, remove, add), rod if rod in SEXES else None)


def _shown(answer: JSONResponse, sex: str | None) -> JSONResponse:
    """POST /copy/{key}'s answer for a page whose reader is of `sex` (the
    slash forms, 27.11.2026): beside each text it carries, the text that
    page shows (grammar.gendered), so the editor shows it once edit mode
    ends, no reload: "shown" beside a text ("text", and each of "also"),
    "shown_items" beside a list's "items", "shown_rows" beside a table's
    "rows". A refusal, a switch's or a photo's answer, and every answer for
    no sex, stay as they were."""
    if sex is None:
        return answer
    data = json.loads(answer.body)
    if not data.get("ok"):
        return answer
    if isinstance(data.get("text"), str):
        data["shown"] = grammar.gendered(data["text"], sex)
    for extra in data.get("also", ()):
        extra["shown"] = grammar.gendered(extra["text"], sex)
    if "items" in data:
        data["shown_items"] = [grammar.gendered(t, sex) for t in data["items"]]
    if "rows" in data:
        data["shown_rows"] = [[grammar.gendered(t, sex) for t in row] for row in data["rows"]]
    return JSONResponse(data, status_code=answer.status_code)


def _copy_save(request: Request, key: str, text: str, index: str, reset: str, part: str, remove: str,
               add: str) -> JSONResponse:
    """Save one edited text (the in-place editor in base.html posts here).
    JSON in both directions: this is called by fetch, never by a form. The
    limit is the slot's, enforced here as well as in the browser; reset=1
    puts the template's default back. An emptied text is stored empty
    since 20.10.2026 (a visitor then gets nothing for it), except a
    required slot's, a number (copy.Slot.required), whose default comes
    back, as every text's did before. A list slot is edited
    one item at a time (see _copy_save_list); a flag slot is switched, its
    text "on" or "off" and nothing else. An image slot takes only reset=1,
    which removes its photo; a photo goes up through POST /copy/{key}/slika,
    so no text can ever land in an image slot. An announcement's field (a
    row, not a slot: aktualno.<id>.<field>) is edited the same way, by the
    type its field has (see _copy_save_announcement), and so is a gym
    card's (dvorana.<id>.<field>, see _copy_save_gym_card) and an upitnik
    question's (upitnik.<id>.<field>, see _copy_save_question). A rows slot
    (the opening hours) is edited a cell or a row at a time, and an
    emptied cell stays empty (see _copy_save_rows)."""
    user = current_user(request)
    if user is None:
        return JSONResponse({"ok": False, "error": "Prijava je istekla — prijavi se ponovno."}, status_code=401)
    if not _can_edit_copy(user):
        return JSONResponse({"ok": False, "error": "Tekstove uređuje samo trener."}, status_code=403)
    slot = copy.SLOTS.get(key)
    if slot is None:
        found = _announcement_field(key)
        if found is not None:
            return _copy_save_announcement(key, *found, text, reset, user.id)
        found = _gym_card_field(key)
        if found is not None:
            return _copy_save_gym_card(*found, text, index, reset, user.id)
        found = _upitnik_field(key)
        if found is not None:
            return _copy_save_question(*found, text, index, reset, user.id)
        return JSONResponse({"ok": False, "error": "Nepoznat tekst."}, status_code=404)
    if isinstance(slot, copy.ListSlot):
        return _copy_save_list(key, slot, text, index, reset, user.id)
    if isinstance(slot, copy.RowsSlot):
        return _copy_save_rows(key, slot, text, index, part, remove, add, reset, user.id)
    if isinstance(slot, copy.FlagSlot):
        if reset == "1":
            db.reset_copy(key)
            return JSONResponse({"ok": True, "on": slot.default, "default": True})
        if text not in ("on", "off"):
            return JSONResponse({"ok": False, "error": "Nepoznata vrijednost."}, status_code=400)
        db.set_copy(key, text, user.id)
        return JSONResponse({"ok": True, "on": text == "on", "default": False})
    if isinstance(slot, copy.ImageSlot):
        if reset != "1":
            return JSONResponse({"ok": False, "error": f"Sliku šalje /copy/{key}/slika."}, status_code=400)
        # the row first, so no page names a file that is gone; then the file
        old = copy.image_name(key, db.copy_texts())
        db.reset_copy(key)
        if old:
            storage.delete(old)
        return JSONResponse({"ok": True, "url": None, "default": True})
    cleaned = "" if reset == "1" else copy.clean(text)
    if len(cleaned) > slot.max:
        return JSONResponse({"ok": False, "error": f"Najviše {slot.max} znakova — ovo ih ima {len(cleaned)}."},
                            status_code=400)
    if reset == "1" or (not cleaned and slot.required):
        db.reset_copy(key)
        return JSONResponse({"ok": True, "text": slot.default, "default": True})
    db.set_copy(key, cleaned, user.id)      # an emptied optional text is stored as ""
    answer = {"ok": True, "text": cleaned, "default": False}
    # A price's first number is its bazna cijena too (23.11.2026): the base
    # of a price that held none ("na upit", a new card's) starts at the price
    # the gym owner types, the price applied on the day it is first offered.
    # Only from a text with no number to one: after that the base is his to
    # retype, and Zadano (above) never touches it. `also` names what changed
    # beside the saved text, for the editor to redraw (base.html).
    base = copy.BASE_OF.get(key)
    if base and _numeric(cleaned) and not _numeric(db.copy_texts().get(base, copy.SLOTS[base].default)):
        db.set_copy(base, cleaned, user.id)
        answer["also"] = [{"key": base, "text": cleaned}]
    return JSONResponse(answer)


# A row's field as the editor names it: an announcement's
# aktualno.<id>.<field>, a gym card's dvorana.<id>.<field> (year_price: an
# underscore), an upitnik question's upitnik.<id>.<field> (the upitnik's
# slots, upitnik.title or upitnik.part1.h, have no number there, and the
# old upitnik.q<n>.* keys are no key at all now, nor a follow-up's
# upitnik.<id>.followup_text since 27.10.2026). At most nine digits, so no
# id is past what the column can hold.
_ANNOUNCEMENT_KEY = re.compile(r"aktualno\.([1-9][0-9]{0,8})\.([a-z]+)")
_GYM_CARD_KEY = re.compile(r"dvorana\.([1-9][0-9]{0,8})\.([a-z_]+)")
_UPITNIK_KEY = re.compile(r"upitnik\.([1-9][0-9]{0,8})\.([a-z_]+)")


def _row_field(pattern: re.Pattern, slots: dict, get, key: str) -> tuple[int, str, object] | None:
    """A virtual key's row, field and slot (`slots`: how each field is
    edited), or None: not such a key (`pattern`), a field such a row does
    not have, or a row that is not there (`get`, by id)."""
    m = pattern.fullmatch(key)
    if m is None or m.group(2) not in slots or get(int(m.group(1))) is None:
        return None
    return int(m.group(1)), m.group(2), slots[m.group(2)]


def _announcement_field(key: str) -> tuple[int, str, copy.Slot | copy.FlagSlot | copy.ImageSlot] | None:
    """A virtual key's card, field and slot (copy.ANNOUNCEMENT_SLOTS: how
    the field is edited), or None: not such a key, a field a card does not
    have, or a card that is not there."""
    return _row_field(_ANNOUNCEMENT_KEY, copy.ANNOUNCEMENT_SLOTS, db.announcement, key)


def _gym_card_field(key: str) -> tuple[int, str, copy.Slot | copy.ListSlot | copy.FlagSlot] | None:
    """The same for a gym card (dvorana.<id>.<field>, copy.GYM_CARD_SLOTS)."""
    return _row_field(_GYM_CARD_KEY, copy.GYM_CARD_SLOTS, db.gym_card, key)


def _upitnik_field(key: str) -> tuple[int, str, copy.Slot | copy.ListSlot] | None:
    """The same for an upitnik question (upitnik.<id>.<field>,
    copy.UPITNIK_QUESTION_SLOTS)."""
    return _row_field(_UPITNIK_KEY, copy.UPITNIK_QUESTION_SLOTS, db.upitnik_question, key)


def _copy_save_row(slot, text: str, reset: str, set_shown, set_text, also=None) -> JSONResponse:
    """A row's switch or text (an announcement's, a gym card's; an upitnik
    question's text, set_shown None: its switch is POST
    /upitnik/pitanje/{id}), answered as
    copy_save answers for a slot of its type: the switch takes "on" or
    "off" (reset=1: its default, on) and hands it to set_shown(on); a text
    is cleaned and capped and handed to set_text(cleaned), which stores it
    and returns what it stored: an emptied one stays empty (no row's text
    is required), and reset=1 hands it the row's placeholder, the slot's
    default, "default": true. `also` (a gym card's price, 23.11.2026)
    takes what a text save (never reset=1) stored and returns the other
    texts it changed with it, [{"key", "text"}], the answer's "also" when
    there are any. A setter's LookupError (the row deleted meanwhile) is
    the caller's to answer."""
    if isinstance(slot, copy.FlagSlot):
        if reset == "1":
            on = slot.default
        elif text in ("on", "off"):
            on = text == "on"
        else:
            return JSONResponse({"ok": False, "error": "Nepoznata vrijednost."}, status_code=400)
        set_shown(on)
        return JSONResponse({"ok": True, "on": on, "default": reset == "1"})
    if reset == "1":
        return JSONResponse({"ok": True, "text": set_text(slot.default), "default": True})
    cleaned = copy.clean(text)
    if len(cleaned) > slot.max:
        return JSONResponse({"ok": False, "error": f"Najviše {slot.max} znakova — ovo ih ima {len(cleaned)}."},
                            status_code=400)
    answer = {"ok": True, "text": set_text(cleaned), "default": False}
    more = also(answer["text"]) if also is not None else []
    if more:
        answer["also"] = more
    return JSONResponse(answer)


def _copy_save_announcement(key: str, ann_id: int, field: str, slot, text: str, reset: str,
                            user_id: int) -> JSONResponse:
    """One change to an announcement's field, answered as copy_save answers
    for a slot of its type: the switch and a text as _copy_save_row does
    (an emptied text stays empty, reset=1 is the new card's placeholder
    again, copy.ANNOUNCEMENT_BLANK); the photo only reset=1, which removes
    the row's name and the file. A card deleted meanwhile answers 404, as an
    unknown key does."""
    try:
        if isinstance(slot, copy.ImageSlot):
            if reset != "1":
                return JSONResponse({"ok": False, "error": f"Sliku šalje /copy/{key}/slika."}, status_code=400)
            old = db.set_announcement_image(ann_id, None, user_id)    # the row first, then the file
            if old:
                storage.delete(old)
            return JSONResponse({"ok": True, "url": None, "default": True})
        return _copy_save_row(
            slot, text, reset, lambda on: db.set_announcement_shown(ann_id, on, user_id),
            lambda cleaned: db.set_announcement_field(ann_id, copy.ANNOUNCEMENT_COLUMNS[field], cleaned, user_id))
    except LookupError:
        return JSONResponse({"ok": False, "error": "Nepoznat tekst."}, status_code=404)


def _copy_save_gym_card(card_id: int, field: str, slot, text: str, index: str, reset: str,
                        user_id: int) -> JSONResponse:
    """One change to a gym card's field (dvorana.<id>.<field>), answered as
    copy_save answers for a slot of its type: the switch and a text as an
    announcement's (_copy_save_row; an emptied text stays empty, reset=1 is
    the new card's placeholder again, copy.GYM_CARD_BLANK); a list, the
    bullets or the extra lines (20.10.2026), as a list slot's, one item at
    a time by `index` (_edit_list), kept in the column its field names, and
    reset=1 puts the new card's back: its two bullets, no extra lines. A
    card deleted meanwhile answers 404, as an unknown key does."""
    try:
        if isinstance(slot, copy.ListSlot):
            if reset == "1":
                items = db.set_gym_card_list(card_id, field, list(slot.default), user_id)
                return JSONResponse({"ok": True, "items": items, "default": True})
            card = db.gym_card(card_id)
            if card is None:
                raise LookupError(f"no gym card {card_id}")
            items = card.list_items(field)
            return _edit_list(items, items == list(slot.default), slot, text, index,
                              lambda changed: db.set_gym_card_list(card_id, field, changed, user_id))
        base = copy.GYM_CARD_BASE_OF.get(field)

        def first_price(stored: str) -> list[dict]:
            """The card's own price's first number is its bazna cijena too
            (23.11.2026), as a price slot's is (copy_save): when the price
            now holds a number and its base column none."""
            card = db.gym_card(card_id)
            if card is None or not _numeric(stored) or _numeric(getattr(card, base)):
                return []
            return [{"key": f"dvorana.{card_id}.{base}",
                     "text": db.set_gym_card_field(card_id, copy.GYM_CARD_COLUMNS[base], stored, user_id)}]

        return _copy_save_row(
            slot, text, reset, lambda on: db.set_gym_card_shown(card_id, on, user_id),
            lambda cleaned: db.set_gym_card_field(card_id, copy.GYM_CARD_COLUMNS[field], cleaned, user_id),
            also=first_price if base else None)
    except LookupError:
        return JSONResponse({"ok": False, "error": "Nepoznat tekst."}, status_code=404)


def _copy_save_question(question_id: int, field: str, slot, text: str, index: str, reset: str,
                        user_id: int) -> JSONResponse:
    """One change to an upitnik question's text (upitnik.<id>.<field>),
    answered as copy_save answers for a slot of its type: a text as a gym
    card's (_copy_save_row; an emptied text stays empty, reset=1 is a new
    question's placeholder again, copy.UPITNIK_BLANK); the options as a
    list slot's, one item at a time by `index` (_edit_list), and reset=1
    puts the two placeholders back. The options keep at least
    upitnik.MIN_OPTIONS: removing one past that is refused, or a choice
    has nothing to choose (a client's answer is an option's text, so an
    option re-worded or removed never garbles one already stored). An
    option re-worded in place (27.10.2026) carries into the conditions
    that named it (db.set_upitnik_question_options: renamed). A question
    deleted meanwhile answers 404, as an unknown key does."""
    try:
        if isinstance(slot, copy.ListSlot):
            if reset == "1":
                items = db.set_upitnik_question_options(question_id, list(slot.default), user_id)
                return JSONResponse({"ok": True, "items": items, "default": True})
            question = db.upitnik_question(question_id)
            if question is None:
                raise LookupError(f"no upitnik question {question_id}")
            items = question.option_items
            if len(items) <= upitnik.MIN_OPTIONS and not copy.clean(text):
                try:
                    removes = 0 <= int(index) < len(items)   # an emptied item at an index removes it (_edit_list)
                except ValueError:
                    removes = False
                if removes:
                    return JSONResponse({"ok": False, "error": "Pitanje treba bar dva odgovora."}, status_code=400)
            before = list(items)                        # _edit_list changes items in place
            return _edit_list(items, items == list(slot.default), slot, text, index,
                              lambda changed: db.set_upitnik_question_options(
                                  question_id, changed, user_id, renamed=_renamed(before, changed, index)))
        return _copy_save_row(
            slot, text, reset, None,
            lambda cleaned: db.set_upitnik_question_field(question_id, copy.UPITNIK_QUESTION_COLUMNS[field],
                                                          cleaned, user_id))
    except LookupError:
        return JSONResponse({"ok": False, "error": "Nepoznat tekst."}, status_code=404)


def _renamed(before: list[str], after: list[str], index: str) -> tuple[str, str] | None:
    """The option an edit re-worded, (old text, new text): one replaced in
    place, at an index within the list, the list as long as it was. None
    for an option added, removed, or saved as it was."""
    try:
        i = int(index)
    except ValueError:
        return None
    if 0 <= i < len(before) == len(after) and before[i] != after[i]:
        return before[i], after[i]
    return None


def _copy_save_list(key: str, slot: copy.ListSlot, text: str, index: str, reset: str,
                    user_id: int) -> JSONResponse:
    """One change to a list slot. reset=1 puts the default list back; any
    other change is _edit_list's, made to the stored list (no row: the
    default list) and stored as the slot's one row. (An upitnik question's
    options were list slots until 26.10.2026: a row's since,
    _copy_save_question.)"""
    if reset == "1":
        db.reset_copy(key)
        return JSONResponse({"ok": True, "items": list(slot.default), "default": True})
    stored = db.copy_texts().get(key)
    items = copy.load_items(stored, slot)
    return _edit_list(items, stored is None, slot, text, index,
                      lambda items: db.set_copy(key, copy.dump_items(items), user_id))


def _copy_save_rows(key: str, slot: copy.RowsSlot, text: str, index: str, part: str, remove: str, add: str,
                    reset: str, user_id: int) -> JSONResponse:
    """One change to a rows slot (the landing's opening hours), made to the
    stored rows (no row: the default rows) and stored as the slot's one
    row: reset=1 puts the default rows back; add=1 appends a row of
    placeholders (copy.ROW_BLANK), at most max_rows; index=i with remove=1
    removes row i; index=i with part ("0" or "1") sets that cell to `text`,
    cleaned and capped as every text is. An emptied cell stays empty, the
    one text with no default to come back (a row has none per cell), and a
    row left with two empty cells goes. The answer is always the whole
    table, so the editor redraws it with fresh indexes."""
    def ok(rows: list[list[str]], default: bool) -> JSONResponse:
        return JSONResponse({"ok": True, "rows": rows, "default": default})

    def bad(error: str) -> JSONResponse:
        return JSONResponse({"ok": False, "error": error}, status_code=400)

    if reset == "1":
        db.reset_copy(key)
        return ok([list(row) for row in slot.default], True)
    rows = copy.load_rows(db.copy_texts().get(key), slot)
    if add == "1":
        if len(rows) >= slot.max_rows:
            return bad(f"Najviše {slot.max_rows} redova.")
        rows.append(list(copy.ROW_BLANK))
    else:
        try:
            i = int(index)
        except ValueError:
            return bad("Nepoznat red.")
        if not 0 <= i < len(rows):
            return bad("Nepoznat red.")
        if remove == "1":
            del rows[i]
        elif part in ("0", "1"):
            cleaned = copy.clean(text)
            if len(cleaned) > slot.max_chars:
                return bad(f"Najviše {slot.max_chars} znakova — ovo ih ima {len(cleaned)}.")
            rows[i][int(part)] = cleaned
            if not any(rows[i]):
                del rows[i]
        else:
            return bad("Nepoznato polje.")
    db.set_copy(key, copy.dump_rows(rows), user_id)
    return ok(rows, False)


def _edit_list(items: list[str], untouched: bool, slot: copy.ListSlot, text: str, index: str,
               write) -> JSONResponse:
    """One change to a list (a list slot's, a gym card's lists): `index`
    says which item: 0..n-1 replaces that item with `text`, n appends `text`
    as a new one, and an empty text removes the item at `index` (with no
    index, or at n, there is nothing to remove and nothing changes: the
    answer's "default" is then `untouched`). The slot's limits hold. A
    changed list goes to write(items). The answer is always the whole list,
    so the editor can redraw it with fresh indexes."""
    def ok(items: list[str], default: bool) -> JSONResponse:
        return JSONResponse({"ok": True, "items": items, "default": default})

    def bad(error: str) -> JSONResponse:
        return JSONResponse({"ok": False, "error": error}, status_code=400)

    cleaned = copy.clean(text)
    try:
        i = int(index) if index.strip() else None
    except ValueError:
        return bad("Nepoznata stavka.")
    if i is None:
        return bad("Nepoznata stavka.") if cleaned else ok(items, untouched)
    if not 0 <= i <= len(items):
        return bad("Nepoznata stavka.")
    if not cleaned:
        if i == len(items):
            return ok(items, untouched)
        del items[i]
    else:
        if len(cleaned) > slot.max_chars:
            return bad(f"Najviše {slot.max_chars} znakova — ovo ih ima {len(cleaned)}.")
        if i == len(items):
            if len(items) >= slot.max_items:
                return bad(f"Najviše {slot.max_items} stavki.")
            items.append(cleaned)
        else:
            items[i] = cleaned
    write(items)
    return ok(items, False)


# An announcement's photo (copy.ImageSlot) arrives as a phone took it: a
# camera's JPEG is a few MB, 15 leaves room for the biggest. What is kept is
# the shrunk JPEG, a few hundred kB.
IMAGE_MB = 15
IMAGE_PX = 1600      # its long side once stored, at most: a card on a wide screen, twice over
_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
# what Pillow must find inside, whatever the name says; MPO is a phone's JPEG
# that carries a second picture (a depth map), Pillow's name for it
_IMAGE_FORMATS = ("JPEG", "MPO", "PNG", "WEBP")
_IMAGE_UNSUPPORTED = "Nepodržan format — dozvoljeno: jpg, png, webp."


def _shrink_image(raw: Path, px: int = IMAGE_PX) -> bytes:
    """A photo as the app keeps it, from the file an upload was spooled to
    (`raw`, already under IMAGE_MB): turned upright (a phone keeps the
    rotation in EXIF), shrunk to `px` on its long side (IMAGE_PX, 1600, by
    default; never enlarged) and saved as a progressive JPEG with no EXIF
    at all (the camera, the place and the time stay out of it); its bytes.
    ValueError: no image Pillow can read, a broken one, or one of a kind
    not in _IMAGE_FORMATS, whatever its name says. An announcement's photo
    (copy_image_upload) and, since 23.11.2026, a member's monthly photo on
    the karton (karton_photo); since 25.11.2026 a karton document that is an
    image, at DOC_PX (_store_document)."""
    import io

    from PIL import Image, ImageOps

    try:
        with Image.open(raw) as im:
            if im.format not in _IMAGE_FORMATS:
                raise ValueError(f"not a photo: {im.format}")
            # a JPEG decodes straight at the smallest scale the shrink
            # still has room in: a 48 MP photo at a quarter, in a
            # sixteenth of the memory
            scale = min(1, px / max(im.size))
            im.draft("RGB", (max(1, round(im.width * scale)), max(1, round(im.height * scale))))
            photo = ImageOps.exif_transpose(im).convert("RGB")
    except Exception as e:                               # not an image Pillow can read, or a broken one
        raise ValueError("not a photo") from e
    photo.thumbnail((px, px))                                     # never enlarges
    out = io.BytesIO()
    photo.save(out, "JPEG", quality=82, progressive=True)        # no exif= given: none is written
    return out.getvalue()


@app.post("/copy/{key}/slika")
def copy_image_upload(request: Request, key: str, slika: UploadFile | None = File(None)):
    """Put a photo behind an announcement: the editor's file picker posts it
    here (multipart, the file as `slika`), JSON back as from POST /copy/{key}.
    Turned upright (a phone keeps the rotation in EXIF), shrunk to IMAGE_PX
    on its long side (never enlarged) and kept as a progressive JPEG with no
    EXIF at all: the camera, the place and the time stay off a public page.
    Each upload gets a new name, which is what lets /slika have browsers keep
    a photo for good; the slot's previous photo is deleted once the new one
    is recorded. Removing it is reset=1 on POST /copy/{key}. An
    announcement's photo (aktualno.<id>.image, a row's) goes the same way."""
    user = current_user(request)
    if user is None:
        return JSONResponse({"ok": False, "error": "Prijava je istekla — prijavi se ponovno."}, status_code=401)
    if not _can_edit_copy(user):
        return JSONResponse({"ok": False, "error": "Tekstove uređuje samo trener."}, status_code=403)
    slot, ann_id = copy.SLOTS.get(key), None
    if slot is None:
        found = _announcement_field(key)
        if found is None:
            return JSONResponse({"ok": False, "error": "Nepoznat tekst."}, status_code=404)
        ann_id, _, slot = found
    if not isinstance(slot, copy.ImageSlot):
        return JSONResponse({"ok": False, "error": "Ovdje ne ide slika."}, status_code=400)

    def bad(error: str) -> JSONResponse:
        return JSONResponse({"ok": False, "error": error}, status_code=400)

    if slika is None or Path(slika.filename or "").suffix.lower() not in _IMAGE_SUFFIXES:
        return bad(_IMAGE_UNSUPPORTED)
    import secrets
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:       # whatever is left in it goes, a refusal's bytes too
        raw, out = Path(tmp) / "upload", Path(tmp) / "slika.jpg"
        # spooled first in 1 MB chunks, as _save_video does: the cap trips
        # before Pillow reads a byte, let alone storage
        total = 0
        with raw.open("wb") as f:
            while chunk := slika.file.read(1 << 20):
                total += len(chunk)
                if total > IMAGE_MB * 1024 * 1024:
                    return bad(f"Slika je veća od {IMAGE_MB} MB.")
                f.write(chunk)
        try:
            out.write_bytes(_shrink_image(raw))          # upright, small, bare (above)
        except ValueError:
            return bad(_IMAGE_UNSUPPORTED)
        # a new name at every upload: an announcement's carries its card's id
        # (aktualno-3-…), a slot's its key
        stem = f"aktualno-{ann_id}" if ann_id is not None else key.replace(".", "-")
        name = f"{stem}-{secrets.token_hex(8)}.jpg"
        storage.save(name, out, "image/jpeg")
    if ann_id is not None:
        try:
            old = db.set_announcement_image(ann_id, name, user.id)
        except LookupError:                              # the card was deleted while its photo went up
            storage.delete(name)
            return JSONResponse({"ok": False, "error": "Nepoznat tekst."}, status_code=404)
    else:
        old = copy.image_name(key, db.copy_texts())
        db.set_copy(key, name, user.id)
    if old:
        storage.delete(old)
    return JSONResponse({"ok": True, "url": f"/slika/{name}"})


@app.get("/slika/{name}")
def slika(name: str):
    """An announcement's photo, for anyone: the landing is public, and so is
    what is on it. The one exception to "media only through the auth-gated
    /media": it serves a name only while an announcement (or an ImageSlot
    row) holds it, a hidden card's too (its editor sees it), so no
    programme's media (a client's content) can be reached through it, nor a
    photo once it is replaced or removed. A name is new with every upload, so
    the file may be cached for a year, immutable. On R2 the bytes are proxied,
    not redirected: /media's presigned link is for private access, a new URL
    on every request that no cache can keep; a public page wants one stable
    address the browser can keep."""
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=404)
    texts = db.copy_texts()
    held = {copy.image_name(k, texts) for k, s in copy.SLOTS.items() if isinstance(s, copy.ImageSlot)}
    held |= {a.image for a in db.announcements(all=True) if a.image}
    if name not in held:
        raise HTTPException(status_code=404)
    cache = {"Cache-Control": "public, max-age=31536000, immutable"}
    if storage.r2_enabled():
        try:
            body, _ = storage.stream(name)
        except FileNotFoundError:
            raise HTTPException(status_code=404)

        def chunks():
            try:
                while chunk := body.read(64 * 1024):
                    yield chunk
            finally:
                body.close()
        return StreamingResponse(chunks(), media_type="image/jpeg", headers=cache)
    path = storage.local_path(name)
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/jpeg", headers=cache)


# ---------- calendar ----------

def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    """Public landing — the shop window. Booking lives at /raspored (auth).

    The gallery is whatever images sit in static/gallery/ (sorted by name) —
    adding a photo is a file drop, not a code change.
    """
    gallery_dir = Path(__file__).parent / "static" / "gallery"
    gallery = sorted(
        f.name for f in gallery_dir.glob("*")
        if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
    ) if gallery_dir.is_dir() else []
    user = current_user(request)
    plans = db.active_plan_kinds(user.id) if user else set()
    # the online plan's tier: of the three QMove cards, the one that is his
    my_tier = db.online_tier(user.id) if user else None
    # members always see prices; guests see them unless PUBLIC_PRICES=off
    show_prices = bool(user) or config.prices_public()
    texts = db.copy_texts()
    # the announcements (#aktualno): a visitor's are the shown ones; an
    # editor's every one, a hidden one marked off, and "+ Dodaj najavu"
    # while there is room for another
    editor = _can_edit_copy(user)
    news = db.announcements(all=editor)
    # the gym's cards (#dvorana) the same way, and "+ Dodaj karticu"; a
    # card's note names its other plans (plan_labels)
    gym = db.gym_cards(all=editor)
    return templates.TemplateResponse(request, "landing.html", _ctx(
        request, user, copy_texts=texts, gallery=gallery, my_plans=plans, my_tier=my_tier,
        show_prices=show_prices, announcements=news,
        can_add=editor and len(news) < db.MAX_ANNOUNCEMENTS,
        gym_cards=gym, can_add_gym=editor and len(gym) < db.MAX_GYM_CARDS, plan_labels=PLAN_LABELS))


# ---------- the announcements: add, delete and move (their fields: POST /copy/{key}) ----------

@app.post("/aktualno/nova")
def aktualno_nova(request: Request):
    """The editor's "+ Dodaj najavu" (edit mode, a plain form): a new card
    after the last one, with placeholder texts to retype in place, shown, no
    photo. Back to the landing's announcements; at the cap with a sentence
    why."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    if db.add_announcement(user.id) is None:
        return RedirectResponse(f"/?error=Najviše+{db.MAX_ANNOUNCEMENTS}+najava.#aktualno", status_code=303)
    return RedirectResponse("/#aktualno", status_code=303)


@app.post("/aktualno/{ann_id}/obrisi")
def aktualno_obrisi(request: Request, ann_id: int):
    """The editor's "Obriši najavu" (edit mode, a plain form the pill sends
    at its second tap): the card goes, then its photo's file. A card already
    gone is nothing to do."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    image = db.delete_announcement(ann_id)
    if image:
        storage.delete(image)
    return RedirectResponse("/#aktualno", status_code=303)


@app.post("/aktualno/{ann_id}/pomak")
def aktualno_pomak(request: Request, ann_id: int, smjer: str = Form("")):
    """The editor's ↑ / ↓ (edit mode, a plain form, 29.10.2026): the card
    trades places with the one before it (smjer=gore) or after it (dolje),
    in the order of every card, the hidden too. Back to it on the landing
    (#najava-<id>, the editor's article; the page comes back in edit mode,
    the one-shot flag base.html sets). At either end, for a card gone or a
    direction that is neither, nothing moves and it comes back the same
    way."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    db.move_announcement(ann_id, smjer, user.id)
    return RedirectResponse(f"/#najava-{ann_id}", status_code=303)


# ---------- the gym's cards: add and delete (their fields: POST /copy/{key}) ----------

@app.post("/dvorana/nova")
def dvorana_nova(request: Request):
    """The editor's "+ Dodaj karticu" (edit mode, a plain form): a new card
    after the last of the gym's, with placeholder texts to retype in place,
    shown, standing for no plan (its own price, the contact for a button).
    Back to the gym's section; at the cap with a sentence why."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    if db.add_gym_card(user.id) is None:
        return RedirectResponse(f"/?error=Najviše+{db.MAX_GYM_CARDS}+kartica.#dvorana", status_code=303)
    return RedirectResponse("/#dvorana", status_code=303)


@app.post("/dvorana/{card_id}/obrisi")
def dvorana_obrisi(request: Request, card_id: int):
    """The editor's "Obriši karticu" (edit mode, a plain form the pill sends
    at its second tap). A card already gone is nothing to do."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    db.delete_gym_card(card_id)
    return RedirectResponse("/#dvorana", status_code=303)


@app.get("/cjenik")
def cjenik(request: Request):
    """The old price list's address. Its plans and prices moved to
    /moja-clanarina on 18.10.2026; links to it live on in emails already sent
    (mailer.send_membership_reminder) and old bookmarks. A member is sent on,
    the query kept (a ?error= / ?ok= still shows) and the #plan-<key> fragment
    kept by the browser (the new page's cards carry the same ids); a guest is
    sent to log in as before (members only since 28.9.2026)."""
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/cjenik')}", status_code=303)
    query = request.url.query
    return RedirectResponse("/moja-clanarina" + (f"?{query}" if query else ""), status_code=303)


def _subscribed_tier(m, table: dict) -> dict | None:
    """The tier ({"sessions", "amount"}) a card subscription of a tiered plan
    pays for, from Stripe's prices; None for cash, a flat plan, or no prices.
    The tier switch offers the others. The card's Cijena is the price slots
    like every price since 18.10.2026; its Paket fact says the tier."""
    pr = table.get(m.plan)
    if not (m.stripe_subscription_id and pr and pr.get("tiers")):
        return None
    return next((t for t in pr["tiers"] if t["sessions"] == m.sessions_per_cycle), None)


@app.get("/moja-clanarina", response_class=HTMLResponse)
def moja_clanarina(request: Request):
    """The member's plans and money in one place (18.10.2026, Shape Club's
    billing page in QMT's look; it took over /cjenik's price list and
    /profil's članarina and payment history). "Tvoji planovi": a card per
    plan held, active or lapsed, that says its state in words and offers
    what fits how it is paid; "Dodaj plan": the plans not held, with their
    prices; "Računi": the ledger. Card actions render only while Stripe is
    configured. The trainer and the owner (who manage members on /clanarine)
    see it with no plans of their own: the page's texts are edited here."""
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/moja-clanarina')}", status_code=303)
    # the trainer and the owner see it too, with no plans of their own: it is
    # where they edit its texts in place (copy slots cjenik.* and clanarina.*,
    # the plans' names here, plan.<plan>.name, the prices, price.<plan>.* and
    # the QMove tiers' offer.online*.*, and the add-on's amounts, addon.*)
    today = config.today()
    # Stripe's Prices, for the forms that charge them only: the tier picker
    # in a checkout form and a subscriber's tier switch. Every price line
    # prints the slots (_plan_price.html).
    table = payments.price_table()
    texts = db.copy_texts()
    memberships = db.memberships_for(user.id)
    order = {p: i for i, p in enumerate(PLAN_TYPES)}
    plans = []
    # active plans first, lapsed after, each in PLAN_TYPES order
    for m in sorted(memberships, key=lambda m: (not m.is_active(today), order.get(m.plan, len(order)))):
        active = m.is_active(today)
        cancelling = bool(m.stripe_subscription_id) and m.cancel_at_period_end
        days_left = (m.dospijece - today).days
        # the state in words; the colour only reinforces it. (its words' slot,
        # clanarina.chip.<kind>, since 25.11.2026 the gym owner's text; its
        # class; the relative day after "dospijeva", code: "sutra", "za 3 dana")
        if not active:
            chip = ("lapsed", "lapsed", "")
        elif cancelling:
            chip = ("cancelling", "off", "")
        elif days_left <= 7:
            chip = ("due", "due", _relative_day(m.dospijece, today))
        else:
            chip = ("active", "ok", "")
        # the card's heading is the plan.<plan>.name slot (the template)
        plans.append({"key": m.plan, "active": active, "chip": chip,
                      # the grace week: next_payment has passed, dospijeće has not
                      "overdue": active and today > m.next_payment,
                      # lapsed while the month that began at the due date still
                      # runs: an uplata buys that month (db.next_cycle), not one from today
                      "continues": not active and today < add_month(m.next_payment),
                      "paid_on": m.paid_on, "next_payment": m.next_payment, "dospijece": m.dospijece,
                      "sessions": m.sessions_per_cycle,
                      # the online plan's QMove tier, its Paket fact (NULL: the base tier);
                      # "tier" below is Stripe's, a card subscription's
                      "tier_key": ((m.tier if m.tier in ONLINE_TIERS else "start")
                                   if m.plan == "online" else None),
                      # "n od N u ovom ciklusu" means something only while the plan runs
                      "usage": db.cycle_usage(user.id, m.plan) if active else None,
                      "subscribed": bool(m.stripe_subscription_id),
                      "auto_renew": m.auto_renew, "cancelling": cancelling,
                      "tier": _subscribed_tier(m, table)})
    held = {m.plan for m in memberships}
    ledger = [{"paid_on": p.paid_on, "label": PLAN_LABELS.get(p.plan, p.plan),
               "method": PAYMENT_METHODS.get(p.method, p.method), "amount": p.amount_eur}
              for p in db.payments_for(user.id)]
    return templates.TemplateResponse(request, "moja_clanarina.html", _ctx(
        request, user, copy_texts=texts, plans=plans,
        # Dodaj plan, the plans not held, in two groups (21.10.2026): the
        # online plan's three QMove tiers (all of them, or none while he
        # holds online) and the gym's plans, the rest in PLAN_TYPES order
        add_tiers=[] if "online" in held else list(ONLINE_TIERS),
        add_gym=[p for p in PLAN_TYPES if p != "online" and p not in held], prices=table,
        sellable=payments.sellable_plans(),
        ledger=ledger, show_amounts=any(r["amount"] is not None for r in ledger),
        # the portal manages a subscription — a customer record alone (a
        # checkout that was abandoned) has nothing to show there
        has_portal=payments.enabled() and bool(user.stripe_customer_id)
                   and any(p["auto_renew"] or p["cancelling"] for p in plans)))


def _card_by_member() -> RedirectResponse:
    """A card payment started while a staff member acts as the member
    (26.11.2026): closed, nothing sent to Stripe. The member starts it
    himself: the card and the contract are his."""
    from urllib.parse import quote
    return RedirectResponse("/moja-clanarina?error=" + quote("Plaćanje karticom pokreće član sam."), status_code=303)


@app.post("/placanje/portal")
def placanje_portal(request: Request):
    """Stripe's hosted portal: change card, cancel, download invoices."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if _actor(request):
        return _card_by_member()
    if not payments.enabled() or not user.stripe_customer_id:
        return RedirectResponse("/moja-clanarina?error=Nemaš+aktivnu+pretplatu+karticom.", status_code=303)
    try:
        return RedirectResponse(payments.portal_url(user), status_code=303)
    except Exception as e:
        print(f"[stripe] portal failed for user {user.id}: {e}")
        return RedirectResponse("/moja-clanarina?error=Portal+trenutno+nije+dostupan.", status_code=303)


@app.post("/placanje/{plan}/promjena")
def placanje_promjena(request: Request, plan: str, sessions: int = Form(...)):
    """Switch an existing subscription to another tier of the same plan."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if _actor(request):
        return _card_by_member()
    from urllib.parse import quote
    try:
        payments.change_tier(user, plan, sessions)
    except ValueError as e:
        return RedirectResponse(f"/moja-clanarina?error={quote(str(e))}#plan-{plan}", status_code=303)
    except Exception as e:
        print(f"[stripe] tier change failed for user {user.id}/{plan}: {e}")
        return RedirectResponse("/moja-clanarina?error=Promjena+trenutno+nije+moguća+—+pokušaj+kasnije.",
                                status_code=303)
    return RedirectResponse(
        f"/moja-clanarina?ok={quote(f'Paket promijenjen na {sessions} treninga mjesečno.')}#plan-{plan}",
        status_code=303)


@app.post("/placanje/{plan}")
def placanje(request: Request, plan: str, sessions: int | None = Form(None), tier: str = Form("")):
    """Start a monthly card subscription for one plan — hands off to Stripe
    Checkout. Access is NOT granted here; the signed webhook does that.
    `tier`: the QMove tier a /moja-clanarina online card names (21.10.2026),
    accepted and ignored for now: Stripe has one flat online Price until
    go-live (DEPLOY.md: online needs three, one per tier, and the code that
    maps them), so a card subscription records START."""
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/moja-clanarina')}", status_code=303)
    if _actor(request):
        return _card_by_member()
    if plan not in PLAN_TYPES or plan not in payments.sellable_plans():
        return RedirectResponse("/moja-clanarina?error=Ovaj+plan+se+ne+može+platiti+karticom.",
                                status_code=303)
    if any(m.plan == plan and m.stripe_subscription_id for m in db.memberships_for(user.id)):
        return RedirectResponse("/moja-clanarina?error=Pretplata+za+ovaj+plan+već+postoji.",
                                status_code=303)
    try:
        return RedirectResponse(payments.checkout_url(user, plan, sessions), status_code=303)
    except ValueError as e:                      # no tier picked on a tiered plan
        from urllib.parse import quote
        return RedirectResponse(f"/moja-clanarina?error={quote(str(e))}#plan-{plan}", status_code=303)
    except Exception as e:
        print(f"[stripe] checkout failed for user {user.id}/{plan}: {e}")   # never silent again
        return RedirectResponse("/moja-clanarina?error=Plaćanje+trenutno+nije+dostupno+—+pokušaj+kasnije.",
                                status_code=303)


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Stripe → us. The signature is the entire auth; a bad one is a 400 and a
    good one is applied idempotently (invoice ids are unique in the ledger)."""
    from fastapi.responses import PlainTextResponse

    if not payments.enabled():
        return PlainTextResponse("stripe not configured", status_code=503)
    payload = await request.body()
    try:
        event = payments.parse_event(payload, request.headers.get("stripe-signature", ""))
    except Exception:
        return PlainTextResponse("bad signature", status_code=400)
    try:
        outcome = payments.handle_event(event)
    except Exception as e:                       # a 5xx makes Stripe retry later
        print(f"[stripe] {e}")
        return PlainTextResponse("error", status_code=500)
    return PlainTextResponse(outcome, status_code=200)


def _relative_day(d: date, today: date) -> str:
    """The next-termin card's hint: "danas", "sutra", "za 3 dana" (21, 31:
    "za 21 dan", like _termin's count)."""
    n = (d - today).days
    if n <= 0:
        return "danas"
    if n == 1:
        return "sutra"
    return f"za {n} {'dan' if n % 10 == 1 and n % 100 != 11 else 'dana'}"


def _iso_day(value: str | None) -> date | None:
    """A ?day= / form `day` as a date; anything else is None (dropped)."""
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _month_start(value: str | None, today: date) -> date:
    """?month=YYYY-MM as that month's 1st. Missing or garbage is today's
    month; so is a year the grid could not step past (1, 9999)."""
    try:
        first = date.fromisoformat(f"{value}-01") if value else None
    except ValueError:
        first = None
    if first is None or not 1 < first.year < 9999:
        return today.replace(day=1)
    return first.replace(day=1)


def _month_overview(user_id: int, first: date, today: date, booked: set[date]) -> dict:
    """The month view (phones, clients): Monday-first weeks of seven days,
    from the Monday on or before the 1st to the Sunday on or after the last
    day. Each day carries what its cell says (the paid period's tint from
    db.covered_days, the dot of a booking of mine, today's ring) and the
    week a tap on it opens."""
    nxt = add_month(first)
    start, stop = _monday_of(first), nxt - timedelta(days=1)
    stop += timedelta(days=6 - stop.weekday())                  # that week's Sunday
    covered = db.covered_days(user_id, start, stop)
    weeks = []
    for w in range((stop - start).days // 7 + 1):
        monday = start + timedelta(days=7 * w)
        weeks.append([{"date": d, "in_month": d.month == first.month, "is_today": d == today,
                       "past": d < today, "covered": d in covered, "has_mine": d in booked,
                       "week": monday.isoformat()}
                      for d in (monday + timedelta(days=i) for i in range(7))])
    return {"month": first, "month_label": f"{MONTHS[first.month - 1]} {first.year}.",
            "prev_month": sub_month(first).isoformat()[:7], "next_month": nxt.isoformat()[:7],
            "this_month": first == today.replace(day=1), "month_weeks": weeks}


# A series run that left dates out comes back with them in the query
# (#seriesDlg, calendar.html): the dates as ISO days and each skipped one's
# reason as a key, _refusal's reason made ASCII; the template says them in
# words. "prozor" and "razdoblje" cannot happen in a run (its dates are the
# window's and the period's), "prošao" only on an offer reopened late.
SKIP_KEYS = {"popunjen": "popunjen", "otkazan": "otkazan", "već rezervirano": "rezervirano",
             "zatvoren": "zatvoren", "prošao": "prosao", "prozor": "prozor", "razdoblje": "razdoblje"}


def _series_report(res: dict) -> dict:
    """The query a series run's page comes back with when the run left
    dates out (a skipped date, a spent paket), for the dialog; {} when it
    booked every date it had."""
    if not res["skipped"] and res["stopped"] != "paket":
        return {}
    return {"booked": ",".join(d.isoformat() for d in res["booked"]),
            "skipped": ",".join(f"{d.isoformat()}:{SKIP_KEYS.get(why, why)}" for d, why in res["skipped"]),
            "paket": res["quota"] if res["stopped"] == "paket" else None}


def _read_series_report(booked: str | None, skipped: str | None, paket: str | None) -> dict | None:
    """_series_report's query back: {"booked": [dates], "skipped": [(date,
    key)], "quota": the paket size or None}, or None when nothing was left
    out (no dialog). A date that is not one, a key that is no reason, a
    paket that is no number: dropped."""
    dates = [d for d in (_iso_day(x) for x in (booked or "").split(",")[:10]) if d]
    misses = []
    for part in (skipped or "").split(",")[:10]:
        when, _, key = part.partition(":")
        when = _iso_day(when)
        if when and key in SKIP_KEYS.values():
            misses.append((when, key))
    quota = int(paket) if paket and paket.isdigit() and 0 < int(paket) < 1000 else None
    return {"booked": dates, "skipped": misses, "quota": quota} if misses or quota else None


@app.get("/raspored", response_class=HTMLResponse)
def calendar(request: Request, week: str | None = None, series: str | None = None,
             day: str | None = None, view: str | None = None, month: str | None = None,
             booked: str | None = None, skipped: str | None = None, paket: str | None = None):
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/raspored')}", status_code=303)
    # the trainer's week, by rule staff's (_is_staff, 26.11.2026: the owner's
    # too, whatever his trainer flag): no month view, no booking window, no
    # gate, the rosters, no series
    staff = _is_staff(user)

    today = config.today()
    now = datetime.now(config.TZ)
    # the booking window (db.booking_window): this week and BOOKING_WEEKS - 1
    # more. A client's week navigation ends at its last week, and a week past
    # it shows him nothing, which nobody could book yet; the trainer, who
    # plans the timetable, walks every week
    window_last = db.booking_window(today)[1]
    last_monday = window_last - timedelta(days=6)
    plans = db.memberships_for(user.id)
    beyond_window, period_until = False, None
    # ?view=month: a client's month overview (the phone's "Mjesec") in the
    # week grid's place. A trainer has no month view: the week page it is.
    month_view = view == "month" and not staff
    if month_view:
        shown_month = _month_start(month, today)
        # no grid, strip or sheet to fill: the week is only where "Tjedan"
        # (and a ✕'s way back) leads, the month's today, else its 1st
        selected_day = today if shown_month == today.replace(day=1) else shown_month
        monday, days = _monday_of(selected_day), []
    else:
        try:
            monday = _monday_of(date.fromisoformat(week)) if week else _monday_of(today)
        except ValueError:
            monday = _monday_of(today)               # garbage ?week= falls back to now
        db.materialize_week(monday)

        beyond_window = not staff and monday > last_monday
        start = datetime(monday.year, monday.month, monday.day, tzinfo=config.TZ)
        rows = [] if beyond_window else db.sessions_between(start, start + timedelta(days=7), now)
        mine = db.user_booking_ids(user.id, [r["session"].id for r in rows])
        my_plans = db.active_plan_kinds(user.id)
        # a client's running plans and their dospijeće: a termin after it
        # cannot be booked (db._refusal's "razdoblje"), so its row offers
        # nothing and the week says until when the plan runs; a weekly
        # repeat stops at the earlier of it and the window's last day
        # (db._series_dates). Never the trainer's: he does not book.
        paid_until = {} if staff else {m.plan: m.dospijece for m in plans if m.is_active(today)}

        # Group into 7 day columns; precompute everything the template needs so it
        # stays logic-free.
        days = []
        for i in range(7):
            d = monday + timedelta(days=i)
            sessions = []
            for r in rows:
                sess = r["session"]
                local = sess.starts_at.astimezone(config.TZ)
                if local.date() != d:
                    continue
                until = paid_until.get(sess.kind)
                bound = min(until, window_last) if until else None
                after_period = bool(until) and d > until
                if after_period:
                    period_until = min(period_until or until, until)
                sessions.append({
                    "id": sess.id, "title": sess.title,
                    "time": local.strftime("%H:%M"),
                    "end": (local + timedelta(minutes=sess.duration_min)).strftime("%H:%M"),
                    "booked": r["booked"], "capacity": sess.capacity,
                    "full": r["booked"] >= sess.capacity,
                    "canceled": sess.canceled,
                    "past": sess.starts_at <= now,
                    # empty, and CLOSE_EMPTY_HOURS or less to go (db.is_closed)
                    "closed": r["closed"],
                    "mine": sess.id in mine,
                    "can_cancel": sess.id in mine and now < db.cancel_deadline(sess),
                    "one_on_one": sess.capacity == 1,
                    # may this client book this kind? (trainer never books via UI)
                    "allowed": staff or sess.kind in my_plans,
                    # after his plan's dospijeće: nothing to book here yet
                    "after_period": after_period,
                    # from the weekly timetable: the phone's sheet offers the
                    # "isti termin svaki tjedan do …" checkbox on these, with
                    # the series' bound, while a later week falls inside it
                    "weekly": sess.template_id is not None,
                    "repeat_until": (bound if sess.template_id is not None and bound
                                     and d + timedelta(days=7) <= bound else None),
                })
            # key is "sessions", NOT "items" — Jinja resolves dict.items to the builtin method
            days.append({"date": d, "name": WEEKDAYS[i], "is_today": d == today, "sessions": sessions,
                         # the day strip's dot: a booking of the client's own that day
                         "has_mine": any(s["mine"] for s in sessions)})

        # The day a phone shows (one day at a time, chosen on the day strip):
        # ?day= when it falls in this week, else today when the week holds it,
        # else the week's first day with termini, else its Monday.
        picked = _iso_day(day)
        if any(d["date"] == picked for d in days):
            selected_day = picked
        elif any(d["is_today"] for d in days):
            selected_day = today
        else:
            selected_day = next((d["date"] for d in days if d["sessions"]), monday)

    # "Moje rezervacije" as day columns mirroring the week grid. my_upcoming()
    # is chronological, so grouping consecutive rows by local date suffices —
    # and it may span two weeks, hence dates (not weekdays) as the group key.
    mine_days = []
    mine = db.my_upcoming(user.id)
    for sess in mine:
        local = sess.starts_at.astimezone(config.TZ)
        if not mine_days or mine_days[-1]["date"] != local.date():
            mine_days.append({"date": local.date(), "name": WEEKDAYS[local.weekday()],
                              "is_today": local.date() == today, "sessions": []})
        mine_days[-1]["sessions"].append({
            "id": sess.id, "date": local.date(),
            "time": local.strftime("%H:%M"),
            "end": (local + timedelta(minutes=sess.duration_min)).strftime("%H:%M"),
            "title": sess.title,
            "canceled": sess.canceled,
            "one_on_one": sess.capacity == 1,
            # the card's ✕: cancel_booking()'s own rule (a termin the trainer
            # canceled can always be dropped), so the two never disagree
            "can_cancel": sess.canceled or now < db.cancel_deadline(sess),
        })

    # "Tvoj sljedeći termin": the soonest booking (a trainer-canceled one
    # included, it says so), answered at the top of the page. Clients only.
    next_booking = None
    if mine_days and not staff:
        first = mine_days[0]
        next_booking = dict(first["sessions"][0], name=first["name"],
                            relative=_relative_day(first["date"], today))
        # its gym training's way in while the training is open (26.11.2026,
        # build 3: from its cancel deadline, since 27.11.2026 the window's
        # start, until the end of the next day)
        next_booking["gym_open"] = not mine[0].canceled and db.gym_window_open(mine[0].starts_at, now)

    # Right after a booking (POST /book adds ?series=<id>): offer the same slot
    # on every following week of the paid period. Only on the client's own
    # booking; trainers do not book. A garbage id simply offers nothing (and
    # one past Postgres' integer range never reaches a query, where it 500s).
    series_offer = None
    try:
        series_id = int(series) if series else None
    except ValueError:
        series_id = None
    if series_id and 0 < series_id < 2**31 and not staff \
            and db.user_booking_ids(user.id, [series_id]):
        preview = db.series_preview(user.id, series_id)
        if preview:
            series_offer = dict(preview, session_id=series_id, noun=_termin(preview["n"]))

    overview = {}
    if month_view:
        overview = _month_overview(user.id, shown_month, today, {d["date"] for d in mine_days})
        # "Članarina vrijedi do …": the furthest dospijeće of an active plan that books termini
        overview["valid_until"] = max((m.dospijece for m in plans
                                       if m.plan in SESSION_KINDS and m.is_active(today)), default=None)

    return templates.TemplateResponse(request, "calendar.html", _ctx(
        request, user,
        days=days, monday=monday, series_offer=series_offer, selected_day=selected_day,
        prev_week=(monday - timedelta(days=7)).isoformat(),
        # none past the window's last week for a client (the phone's swipe too)
        next_week=(None if not staff and monday >= last_monday
                   else (monday + timedelta(days=7)).isoformat()),
        beyond_window=beyond_window, weeks_ahead=db.weeks_text(config.BOOKING_WEEKS),
        # the week's termini after a running plan's dospijeće: the earliest
        # such dospijeće, said once under the termini
        period_until=period_until,
        series_report=None if staff else _read_series_report(booked, skipped, paket),
        mine_days=mine_days, next_booking=next_booking, cutoff_hours=config.CANCEL_CUTOFF_HOURS,
        # with no plan running a client is told booking needs one (the plans
        # themselves are on /moja-clanarina since 18.10.2026)
        has_active_plan=any(m.is_active(today) for m in plans),
        view="month" if month_view else "week", **overview,
    ))


def _redirect_back(week: str, error: str | None = None, ok: str | None = None,
                   cta: str | None = None, series: int | None = None,
                   day: str = "", report: dict | None = None) -> RedirectResponse:
    """Back to the calendar, on the right week, with feedback visible.
    The separator depends on whether `back` already has a query string —
    "/&error=..." is not a query string and the message silently vanishes.
    `cta` turns a refusal into an offer: it carries a PLAN KIND, never a URL —
    the alert builds the link itself, so a crafted ?cta= cannot become an
    off-site href. `series` (a session id) asks the calendar to offer that
    booking's weekly repeat. `day` is the day a phone was showing (ISO; any
    other value is dropped), so the page comes back on it. `report` is a
    series run's dates left out (_series_report), for the dialog."""
    from urllib.parse import quote

    back = f"/raspored?week={week}" if week else "/raspored"
    shown = _iso_day(day)
    for key, val in (("day", shown and shown.isoformat()), ("error", error), ("ok", ok),
                     ("cta", cta), ("series", series), *(report or {}).items()):
        if val:
            back += ("&" if "?" in back else "?") + f"{key}=" + quote(str(val))
    return RedirectResponse(back, status_code=303)


@app.post("/book/{session_id}")
def book(request: Request, session_id: int, week: str = Form(""), series: str = Form(""),
         day: str = Form("")):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        db.book(user.id, session_id)
    except db.MembershipRequired as e:
        # the one refusal with a fix: send the price of the plan they just tried
        return _redirect_back(week, str(e), cta=e.kind, day=day)
    except db.BookingError as e:
        return _redirect_back(week, str(e), day=day)
    if series == "1":
        # the phone's sheet: "Isti termin svaki tjedan" ticked, so the repeat
        # runs now (db.book_series' rules) and there is nothing left to offer.
        # The booking above stands whatever the series says.
        try:
            res = db.book_series(user.id, session_id)
        except db.BookingError as e:
            return _redirect_back(week, "Rezervirano ✓, ali " + _lower_first(str(e)), day=day)
        text, any_more = _series_feedback(res)
        # a date left out: the dialog says which and why (#seriesDlg)
        report = _series_report(res)
        if not any_more:
            # the booking stands, the repeat found nothing to add: say so
            # without contradicting the ✓ ("nijedan termin nije rezerviran")
            why = text.split(" — ", 1)[1] if " — " in text else ""
            return _redirect_back(week, ok="Rezervirano ✓ — samo ovaj termin" + (", " + why if why else "."),
                                  day=day, report=report)
        return _redirect_back(week, ok="Rezervirano ✓ — " + _lower_first(text), day=day, report=report)
    return _redirect_back(week, ok="Rezervirano ✓", series=session_id, day=day)


def _lower_first(text: str) -> str:
    """A message continued after "Rezervirano ✓ — " / ", ali ": the
    _series_feedback style, lower case after the dash."""
    return text[:1].lower() + text[1:]


def _termin(n: int) -> str:
    """The noun after a count: 1 termin, 3 termina, 21 termin."""
    return "termin" if n % 10 == 1 and n % 100 != 11 else "termina"


def _series_feedback(res: dict) -> tuple[str, bool]:
    """(alert text, ok?) after a series run: the dates booked, the dates
    skipped and why, a spent paket. Nothing booked at all is an error."""
    def days(ds):
        return ", ".join(f"{d:%-d.%-m.}" for d in ds)

    tail = []
    if res["skipped"]:
        tail.append("preskočeno " + ", ".join(f"{d:%-d.%-m.} ({why})" for d, why in res["skipped"]))
    n = len(res["booked"])
    if n:
        if res["stopped"] == "paket":
            tail.append(f"paket od {res['quota']} treninga je popunjen, ostatak nije rezerviran")
        return " — ".join([f"Rezervirano još {n} {_termin(n)}: {days(res['booked'])}", *tail]), True
    if res["stopped"] == "paket":
        tail.append(f"paket od {res['quota']} treninga je popunjen")
    elif not tail:
        tail.append(f"do {res['until']:%-d.%-m.} nema više termina")
    return " — ".join(["Nijedan termin nije rezerviran", *tail]) + ".", False


@app.post("/book/{session_id}/series")
def book_series(request: Request, session_id: int, week: str = Form(""), day: str = Form("")):
    """"Isti termin svaki tjedan": the slot just booked, on every later week
    of the booking window up to the plan's dospijeće (the rules are
    db.book_series'). A date left out opens the dialog (#seriesDlg)."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not db.user_booking_ids(user.id, [session_id]):
        # the offer only ever follows the client's own booking
        return _redirect_back(week, "Nemaš rezervaciju za ovaj termin.", day=day)
    try:
        res = db.book_series(user.id, session_id)
    except db.MembershipRequired as e:
        return _redirect_back(week, str(e), cta=e.kind, day=day)
    except db.BookingError as e:
        return _redirect_back(week, str(e), day=day)
    text, ok = _series_feedback(res)
    report = _series_report(res)
    return (_redirect_back(week, ok=text, day=day, report=report) if ok
            else _redirect_back(week, text, day=day, report=report))


@app.post("/cancel/{session_id}")
def cancel(request: Request, session_id: int, week: str = Form(""), day: str = Form("")):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        db.cancel_booking(user.id, session_id)
    except db.BookingError as e:
        return _redirect_back(week, str(e), day=day)
    return _redirect_back(week, ok="Rezervacija je otkazana.", day=day)


@app.get("/auth/verify")
def auth_verify(request: Request, token: str = ""):
    email = auth.read_verify_token(token)
    if email is None:
        return RedirectResponse(
            "/login?error=Link+nije+valjan+ili+je+istekao+—+prijavi+se+za+novi.", status_code=303)
    newly = db.mark_email_verified(email)
    if newly is None:
        return RedirectResponse("/login?error=Račun+ne+postoji.", status_code=303)
    # Owner hears about REAL arrivals only: first verification, never a
    # re-clicked link, never the owner verifying their own account.
    if newly and config.OWNER_EMAIL and email.strip().lower() != config.OWNER_EMAIL:
        u = db.get_user_by_email(email)
        try:
            mailer.send_new_user_notice(config.OWNER_EMAIL, email,
                                        u.full_name if u else None)
        except Exception:
            pass   # never block a verification on the courtesy mail
    return RedirectResponse("/login?ok=Email+je+potvrđen+—+prijavi+se.", status_code=303)


@app.get("/forgot", response_class=HTMLResponse)
def forgot_page(request: Request):
    return templates.TemplateResponse(request, "forgot.html", _ctx(request, None))


@app.post("/forgot")
def forgot(request: Request, email: str = Form(...)):
    email = email.strip().lower()
    u = db.get_user_by_email(email)
    # Same response whether or not the account exists — no enumeration.
    if u is None:
        return templates.TemplateResponse(request, "verify_sent.html", _ctx(
            request, None, email=email, dev_link=None, reset_mode=True))
    link = f"{config.PUBLIC_BASE_URL}/reset?token={auth.make_reset_token(u.email, u.password_hash)}"
    sent = mailer.send_password_reset_email(u.email, link, u.sex)     # its slash form as the account's (27.11.2026)
    if not sent and config.IS_PROD:
        return RedirectResponse("/forgot?error=Slanje+emaila+nije+uspjelo.", status_code=303)
    return templates.TemplateResponse(request, "verify_sent.html", _ctx(
        request, None, email=email, dev_link=None if sent else link, reset_mode=True))


@app.get("/reset", response_class=HTMLResponse)
def reset_page(request: Request, token: str = ""):
    if auth.read_reset_token(token) is None:
        return RedirectResponse("/forgot?error=Link+nije+valjan+ili+je+istekao.", status_code=303)
    return templates.TemplateResponse(request, "reset.html", _ctx(request, None, token=token))


@app.post("/reset")
def reset(request: Request, token: str = Form(...), password: str = Form(...)):
    data = auth.read_reset_token(token)
    if data is None:
        return RedirectResponse("/forgot?error=Link+nije+valjan+ili+je+istekao.", status_code=303)
    if not auth.password_ok(password):
        from urllib.parse import quote
        return RedirectResponse(f"/reset?token={quote(token)}&error=Lozinka+mora+imati+barem+8+znakova.",
                                status_code=303)
    email, marker = data
    if not db.reset_password(email, auth.hash_password(password), marker):
        return RedirectResponse("/forgot?error=Link+je+već+iskorišten+—+zatraži+novi.", status_code=303)
    return RedirectResponse("/login?ok=Lozinka+je+promijenjena+—+prijavi+se.", status_code=303)


# ---------- trainer admin ----------

def _require_trainer(request: Request):
    """A staff route (_is_staff: the trainer and the owner)."""
    user = current_user(request)
    if user is None:
        return None, RedirectResponse("/login", status_code=303)
    if not _is_staff(user):
        raise HTTPException(status_code=403, detail="Samo trener")
    return user, None


def _require_owner(request: Request):
    user = current_user(request)
    if user is None:
        return None, RedirectResponse("/login", status_code=303)
    if not _is_owner(user):
        raise HTTPException(status_code=403, detail="Samo vlasnik aplikacije")
    return user, None


# ---------- staff act as a member ("Gledaj kao član", 26.11.2026) ----------
#
# The owner: "What if we have a user selection somewhere in the app for the
# admins much higher in the hierarchy and then Amir can look at the app just
# like the user sees the app and he can do everything the user does in the
# same way?" … "so that nothing is lost in the communication or display
# between him and the user". While a staff member (the trainer, the owner)
# is "in" a member's account, current_user IS the member: every page and
# every route behaves as for him (his plans, his gates; a staff route
# refuses as it refuses any member), the staff member the actor beside him.
# The session holds it: as_user_id (the member), as_seen (the last request's
# time, for the idle limit), as_back (where "Izađi" goes), and since
# 27.11.2026 as_scope for a tab's view (below). Closed while acting: a card
# payment (_card_by_member) and sending the upitnik (its consent is the
# member's). Every write done so is recorded (ActingLog), for the owner
# alone.
#
# Two ways in (27.11.2026). The whole app, as since 26.11.2026: Admin ▾ →
# Gledaj kao član, a roster's "Kao član →", the read-only karton's "Otvori
# kao član". And a tab's view, the two searches' (the Karton tab's, POST
# /karton/clan, and Dvoranski treninzi's, POST /dvoranski/clan; the owner:
# "When entered via the karton tab search, I dont want to view the whole app
# as that user ... but only that karton tab. If then Amir or I switch the
# tab, then its no longer that users view."): as_scope set, the member's
# Karton and Dvoranski treninzi are his (_in_member_tab), read and write,
# and any other request ends the view before it runs (_acting_guard) and
# runs as the staff member's own; the bar over its pages is staff's own,
# every link of it the exit (GET /kao/izlaz?kamo=…).

_ACTING_KEYS = ("as_user_id", "as_seen", "as_back", "as_scope")
# the paths that never depend on who asks (the static files, the
# announcements' photos, the service worker, the healthcheck; since
# 27.11.2026 the two a browser may fetch on its own, 404 for everyone, so
# that one never ends a tab's view): let be
_ACTING_FREE = ("/static/", "/slika/", "/sw.js", "/healthz", "/favicon.ico", "/apple-touch-icon")
# the two writes a page drawn for another identity may always send: the way
# out of the view and out of the session
_ACTING_EXITS = ("/kao/izlaz", "/logout")
ACTING_EXPIRED = "Pregled kao član je istekao — odaberi člana ponovno."
ACTING_ENDED = "Pregled kao član je završen — ništa nije spremljeno."
ACTING_STALE = "Stranica je bila otvorena prije ulaska u pregled kao član — ništa nije spremljeno."
ACTING_REFUSED = "U račun trenera ili vlasnika se ne ulazi."
# a page asked for off the member's two areas ends a tab's view: the page,
# the staff member's own, says so once (its slash form his)
ACTING_LEFT = "Izašao/la si iz pregleda člana."
# a tab's view (27.11.2026): the member's two areas, every address under them
# his, but these, which are staff's (the two searches, the templates; and the
# read-only view /karton/<id>, _in_member_tab)
_TAB_AREAS = ("/karton", "/dvoranski")
_TAB_STAFF = ("/karton/clan", "/dvoranski/clan", "/dvoranski/predlosci")


def _in_member_tab(path: str) -> bool:
    """In a tab's view (the session's as_scope), whether a request is the
    member's: his Karton and his Dvoranski treninzi, every address under
    them (his forms, his trainings, their writes), and /media (his files,
    his exercises' clips); not the staff routes under those two, the
    searches (/karton/clan, /dvoranski/clan), the read-only view of a karton
    (/karton/<id>) and the templates (/dvoranski/predlosci…). A path is read
    without its trailing slash."""
    p = path.rstrip("/") or "/"
    if p.startswith("/media/"):
        return True
    if not any(p == area or p.startswith(area + "/") for area in _TAB_AREAS):
        return False
    if re.fullmatch(r"/karton/[0-9]+", p):
        return False
    return not any(p == staff or p.startswith(staff + "/") for staff in _TAB_STAFF)


def _asks_for_page(request: Request) -> bool:
    """Whether a GET is a page asked for (a link followed, an address typed,
    a reload): a browser's navigation says so in Sec-Fetch-Mode
    ("navigate") or Sec-Fetch-Dest ("document"); one that sends no
    Sec-Fetch-* names HTML in its Accept. An image, a script, a fetch() is
    no page. The mode comes first (Fable's review, 27.11.2026, in a browser
    with the app's service worker, which every returning visitor has): the
    worker hands a navigation on with fetch(e.request), and Chromium sends
    that with Sec-Fetch-Dest "empty" and Sec-Fetch-Mode "navigate": read by
    its Dest alone, no page under the service worker was ever one."""
    if request.headers.get("sec-fetch-mode") == "navigate":
        return True
    dest = request.headers.get("sec-fetch-dest")
    if dest:
        return dest == "document"
    return "text/html" in request.headers.get("accept", "")


def _with_flash(request: Request, text: str) -> str:
    """The very address asked for (its path and its query, an `ok` of its
    own left out) with `text` as its ok flash."""
    from urllib.parse import quote, urlencode

    pairs = [(k, v) for k, v in request.query_params.multi_items() if k != "ok"] + [("ok", text)]
    return quote(request.url.path) + "?" + urlencode(pairs)


def _clock() -> float:
    """Now, as the idle limit counts it (epoch seconds)."""
    import time

    return time.time()


def _acting_check(user_id, member_id) -> tuple[str, object, object]:
    """The session's view as a member, checked against the accounts now:
    ("ok", the staff member, the member); ("actor", …) when the one logged
    in is gone or no longer staff; ("member", …) when the member is gone or
    has become staff."""
    actor = db.get_user(user_id) if isinstance(user_id, int) else None
    if actor is None or not _can_edit_copy(actor):
        return "actor", None, None
    member = db.get_user(member_id) if isinstance(member_id, int) else None
    if member is None or _can_edit_copy(member):
        return "member", actor, None
    return "ok", actor, member


def _record_acting(actor, member, method: str, path: str, status: int | None) -> None:
    """A row of the record (db.record_acting); a failure to write it is
    printed, never raised: the request it records stands."""
    try:
        db.record_acting(actor, member, method, path, status)
    except Exception as e:
        print(f"[kao] the record of {method} {path} failed: {e!r}")


async def _acting_guard(app_, scope, receive, send) -> None:
    """Before every route (_ActingGuard, inside SessionMiddleware).

    Not acting: a write (any method but GET, HEAD, OPTIONS) that names a
    member (the page it came from was drawn while acting: ?kao= / X-QMT-Kao)
    executes nothing, back to /kao saying the view has ended. Acting: the
    session is checked first. An actor who is no longer staff (or gone) is
    dropped to /, a member who is gone or has become staff, and a view idle
    for config.ACT_AS_IDLE_MINUTES, drop to /kao saying it expired: the three
    keys go and NOTHING runs, GET or POST (a form left open on the member's
    karton must never save into the staff member's own, nor anything else
    run as him), but a logout, which runs. In a tab's view (as_scope, since
    27.11.2026) a request off the member's two areas (_in_member_tab) and no
    exit ends the view before it runs, the keys gone, and is the staff
    member's own: a page asked for (_asks_for_page) is sent on to its very
    address saying so ("Izašao/la si iz pregleda člana."), so nobody takes
    his own page for the member's; a write that still names a member (its
    marker) runs nothing, back to /kao saying the view has ended, as any
    such write outside a view; anything else runs, as his. Then the last
    request's time is stamped, and a write runs only when its page was
    drawn for this member (its marker is his id; base.html adds it to every
    form and fetch of a page drawn while acting): else nothing, back to his
    karton saying so. "Izađi" and the logout always pass. A write that runs
    as the member is recorded with its status (None when the app failed),
    never failing the request."""
    if scope["type"] != "http" or scope["path"].startswith(_ACTING_FREE):
        await app_(scope, receive, send)
        return
    from urllib.parse import quote

    from starlette.concurrency import run_in_threadpool

    request = Request(scope)
    session, path, method = request.session, scope["path"], scope["method"]
    write = method not in ("GET", "HEAD", "OPTIONS")
    leaving = path in _ACTING_EXITS
    marker = request.query_params.get("kao") or request.headers.get("x-qmt-kao") or ""
    member_id = session.get("as_user_id")
    if member_id is None:
        if write and marker and not leaving:
            await RedirectResponse("/kao?error=" + quote(ACTING_ENDED), status_code=303)(scope, receive, send)
            return
        await app_(scope, receive, send)
        return
    verdict, actor, member = await run_in_threadpool(_acting_check, session.get("user_id"), member_id)
    seen, now = session.get("as_seen"), _clock()
    if verdict == "ok" and not (isinstance(seen, (int, float)) and now - seen <= config.ACT_AS_IDLE_MINUTES * 60):
        verdict = "expired"
    if verdict != "ok":
        for key in _ACTING_KEYS:
            session.pop(key, None)
        if path == "/logout":
            await app_(scope, receive, send)
            return
        where = "/" if verdict == "actor" else "/kao?error=" + quote(ACTING_EXPIRED)
        await RedirectResponse(where, status_code=303)(scope, receive, send)
        return
    if "as_scope" in session and not leaving and not _in_member_tab(path):
        # a tab's view, and a request off the member's two areas: the view
        # ends before anything runs, and the request is the staff member's
        for key in _ACTING_KEYS:
            session.pop(key, None)
        if write and marker:
            await RedirectResponse("/kao?error=" + quote(ACTING_ENDED), status_code=303)(scope, receive, send)
            return
        if not write and _asks_for_page(request):
            await RedirectResponse(_with_flash(request, ACTING_LEFT), status_code=303)(scope, receive, send)
            return
        await app_(scope, receive, send)
        return
    session["as_seen"] = int(now)
    if write and not leaving and marker != str(member_id):
        await RedirectResponse("/karton?error=" + quote(ACTING_STALE), status_code=303)(scope, receive, send)
        return
    if not write:
        await app_(scope, receive, send)
        return
    status = None

    async def answered(message) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        await send(message)

    try:
        await app_(scope, receive, answered)
    finally:
        await run_in_threadpool(_record_acting, actor, member, method, path, status)


def _kao_members() -> list[dict]:
    """Every member staff may act as (an account that is neither a trainer
    nor the owner), in the alphabet's order (his full name, the email for
    one with none: models.alpha_key), each {"user", "name" (his full name,
    else his email), "plans" (his running plans by their names, PLAN_LABELS
    in PLAN_TYPES' order, joined by " · "; "" for none)}: /kao's rows and,
    since 26.11.2026 (build 4), the Karton tab's picker, one list (since
    27.11.2026 its search, which opens his karton)."""
    today = config.today()
    order = {p: i for i, p in enumerate(PLAN_TYPES)}
    members = []
    for row in db.memberships_overview():
        u = row["user"]
        if _can_edit_copy(u):                        # the owner, listed there when he does not train
            continue
        running = sorted((m.plan for m in row["plans"] if m.is_active(today)), key=lambda p: order.get(p, len(order)))
        members.append({"user": u, "name": u.full_name or u.email,
                        "plans": " · ".join(PLAN_LABELS.get(p, p) for p in running)})
    members.sort(key=lambda m: (alpha_key(m["name"]), m["user"].email))
    return members


@app.get("/kao", response_class=HTMLResponse)
def kao_page(request: Request):
    """"Gledaj kao član" (Admin ▾'s first item): every member (_kao_members)
    with his running plans (none: "bez članarine"), and "Otvori →", POST
    /kao/<id>. A search filters the rows as it is typed (the page's script;
    the whole list without it). The owner also gets the way to the record
    (/kao/zapisi)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "kao.html", _ctx(request, user, members=_kao_members()))


@app.get("/kao/zapisi", response_class=HTMLResponse)
def kao_zapisi(request: Request):
    """"Radnje u ime članova", the record (the owner's alone: "Only a record
    for me"): every entry into a member's account and every write done as
    one, newest first, db.ACTING_LOG_PAGE (100) a page (?str=2, "Novije" /
    "Starije"): when (Zagreb), who, as whom, what (the method and the
    path), the status."""
    user, redirect = _require_owner(request)
    if redirect:
        return redirect
    raw = request.query_params.get("str", "")
    page = int(raw) if re.fullmatch(r"[1-9][0-9]{0,5}", raw) else 1
    rows, older = db.acting_log(page)
    return templates.TemplateResponse(request, "kao_zapisi.html", _ctx(
        request, user, rows=rows, page=page, older=older, tz=config.TZ))


@app.post("/kao/izlaz")
def kao_izlaz(request: Request):
    """"Izađi" (the bar's): the view as a member ends, back where it was
    entered from (as_back; /kao by default). Always passes the guard's
    check of the page's identity, as the logout does."""
    back = request.session.get("as_back")
    for key in _ACTING_KEYS:
        request.session.pop(key, None)
    return RedirectResponse(_safe_next(back) if back else "/kao", status_code=303)


@app.get("/kao/izlaz")
def kao_izlaz_go(request: Request, kamo: str = ""):
    """Every link of the bar over a tab's view (27.11.2026: staff's own bar,
    base.html's bar_href) is this: the view ends (ending one is safe, a GET
    may) and the link goes where it says, `kamo` (a local path,
    _safe_next), no flash for a step this deliberate; with no `kamo`, where
    "Izađi" goes. An exit, as "Izađi" and the logout: the guard lets it
    pass. A GET: no row of the record."""
    back = request.session.get("as_back")
    for key in _ACTING_KEYS:
        request.session.pop(key, None)
    if kamo.strip():
        return RedirectResponse(_safe_next(kamo), status_code=303)
    return RedirectResponse(_safe_next(back) if back else "/kao", status_code=303)


def _enter_member(request: Request, user, member, natrag: str, kamo: str, tab: bool = False):
    """Into `member`'s account as `user` (staff: the route asks
    _require_trainer first), POST /kao/{id}'s way in (the Karton tab's POST
    /kao's too, from build 4 until 27.11.2026, when its field came to open
    his karton instead): into a member's only ("U račun trenera ili vlasnika
    se ne ulazi.", back to /kao). `natrag`, where "Izađi" returns (/kao by
    default), and `kamo`, where to land (his karton by default), each a
    local path (_safe_next). `tab` (27.11.2026, the two searches'): a tab's
    view, the session's as_scope, his Karton and Dvoranski treninzi alone
    (_acting_guard); else the whole app, as_scope gone. The entry is the
    record's first row (the route's own path); the osvrt prompt is not
    armed by it."""
    from urllib.parse import quote

    if _can_edit_copy(member):
        return RedirectResponse("/kao?error=" + quote(ACTING_REFUSED), status_code=303)
    request.session["as_user_id"] = member.id
    request.session["as_seen"] = int(_clock())
    request.session["as_back"] = _safe_next(natrag) if natrag.strip() else "/kao"
    if tab:
        request.session["as_scope"] = "tab"
    else:
        request.session.pop("as_scope", None)
    request.session.pop("fb_prompt", None)
    _record_acting(user, member, "POST", request.url.path, 303)
    return RedirectResponse(_safe_next(kamo) if kamo.strip() else "/karton", status_code=303)


@app.post("/kao/{user_id}")
def kao_enter(request: Request, user_id: int, natrag: str = Form(""), kamo: str = Form("")):
    """Into a member's account from the picker (/kao's "Otvori →"), a
    termin's roster or the trainer's view of a karton: a trainer or the
    owner (a member, a guest never reaches it; while acting this is the
    member's, who is refused too), _enter_member's rules; an account that
    is not there is 404."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    member = db.get_user(user_id)
    if member is None:
        raise HTTPException(status_code=404)
    return _enter_member(request, user, member, natrag, kamo)


@app.get("/tekstovi", response_class=HTMLResponse)
def tekstovi_page(request: Request):
    """Every plain text of the app on one page (25.11.2026, the owner: "If
    there is a place where he is not allowed to change text, lets allow
    it"): Admin ▾ → Tekstovi, the trainer's and the owner's. Page by page in
    the nav's order, each by area (copy.TEXT_PAGES), every plain slot its
    label over its text, which edit mode edits in place (POST /copy/{key},
    as anywhere): the texts only a member or a guest sees among them (the
    calendar's, the player's, the login pages', the dialogs', a confirm's,
    a placeholder's). Its search filters as it is typed (the script; the
    whole list without it)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    total = sum(len(keys) for *_, areas in copy.TEXT_PAGES for _, keys in areas)
    return templates.TemplateResponse(request, "tekstovi.html", _ctx(request, user, total=total))


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    # the timetable as the same 7-column week the clients see, but editable
    days = [{"name": name, "templates": []} for name in WEEKDAYS]
    for t in db.list_templates():                # already weekday+time ordered
        end = (t.start_min + t.duration_min) % (24 * 60)
        days[t.weekday]["templates"].append({
            "id": t.id, "title": t.title, "active": t.active, "kind": t.kind,
            "capacity": t.capacity, "note": t.note,
            "time": f"{t.start_min // 60:02d}:{t.start_min % 60:02d}",
            "end": f"{end // 60:02d}:{end % 60:02d}",
        })
    return templates.TemplateResponse(request, "admin.html", _ctx(
        request, user, days=days, weekdays=WEEKDAYS,
        kinds=SESSION_KINDS, kind_labels=PLAN_LABELS,
    ))


@app.post("/admin/templates")
def add_template(request: Request, title: str = Form(...), weekday: int = Form(...),
                 time: str = Form(...), duration_min: int = Form(60),
                 capacity: int = Form(8), note: str = Form(""),
                 kind: str = Form("grupni")):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    try:
        h, m = map(int, time.split(":"))
        assert 0 <= weekday <= 6 and 0 <= h <= 23 and 0 <= m <= 59 and kind in SESSION_KINDS
    except (ValueError, AssertionError):
        return RedirectResponse("/admin?error=Neispravan+dan+ili+vrijeme.", status_code=303)
    db.add_template(title.strip(), weekday, h * 60 + m,
                    max(15, min(240, duration_min)), max(1, min(40, capacity)),
                    note.strip() or None, kind)
    return RedirectResponse("/admin", status_code=303)


def _parse_slot(weekday: int, time: str):
    h, m = map(int, time.split(":"))
    if not (0 <= weekday <= 6 and 0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError
    return h * 60 + m


@app.get("/admin/templates/{template_id}", response_class=HTMLResponse)
def edit_template_page(request: Request, template_id: int):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    t = db.get_template(template_id)
    if t is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "template_edit.html", _ctx(
        request, user, t=t, weekdays=WEEKDAYS,
        kinds=SESSION_KINDS, kind_labels=PLAN_LABELS,
        time_value=f"{t.start_min // 60:02d}:{t.start_min % 60:02d}",
    ))


@app.post("/admin/templates/{template_id}/edit")
def edit_template(request: Request, template_id: int, title: str = Form(...),
                  weekday: int = Form(...), time: str = Form(...),
                  duration_min: int = Form(60), capacity: int = Form(8),
                  note: str = Form(""), kind: str = Form("grupni")):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    try:
        start_min = _parse_slot(weekday, time)
        if kind not in SESSION_KINDS:
            raise ValueError
    except ValueError:
        return RedirectResponse(f"/admin/templates/{template_id}?error=Neispravan+dan+ili+vrijeme.",
                                status_code=303)
    db.update_template(template_id, title.strip(), weekday, start_min,
                       max(15, min(240, duration_min)), max(1, min(40, capacity)),
                       note.strip() or None, kind)
    return RedirectResponse("/admin?ok=Stavka+je+ažurirana.+Buduci+termini+bez+rezervacija+su+preračunati.",
                            status_code=303)


@app.post("/admin/templates/{template_id}/delete")
def delete_template(request: Request, template_id: int):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    db.delete_template(template_id)
    return RedirectResponse("/admin?ok=Stavka+je+obrisana.", status_code=303)


@app.post("/admin/templates/{template_id}/toggle")
def toggle_template(request: Request, template_id: int, active: str = Form("")):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    db.set_template_active(template_id, active == "1")
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/session/{session_id}", response_class=HTMLResponse)
def session_roster(request: Request, session_id: int):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    with db.session_scope() as s:
        sess = s.get(db.TrainingSession, session_id)
    if sess is None:
        raise HTTPException(status_code=404)
    people = db.roster(session_id)
    return templates.TemplateResponse(request, "roster.html", _ctx(
        request, user, sess=sess,
        local_time=sess.starts_at.astimezone(config.TZ),
        people=people,
        # "Kao član →" on a member's row (26.11.2026), never on staff's
        staff_ids={p.id for p in people if _can_edit_copy(p)},
    ))


@app.post("/admin/session/{session_id}/cancel")
def cancel_session(request: Request, session_id: int, undo: str = Form("")):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    db.set_session_canceled(session_id, undo != "1")
    return RedirectResponse(f"/admin/session/{session_id}", status_code=303)


@app.post("/admin/oneoff")
def add_oneoff(request: Request, title: str = Form(...), day: str = Form(...),
               time: str = Form(...), duration_min: int = Form(60),
               capacity: int = Form(1), note: str = Form(""),
               kind: str = Form("grupni")):
    """One-off session outside the weekly timetable (extra 1:1, workshop...)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    try:
        d = date.fromisoformat(day)
        h, m = map(int, time.split(":"))
        starts = datetime(d.year, d.month, d.day, h, m, tzinfo=config.TZ)
        assert starts > datetime.now(config.TZ) and kind in SESSION_KINDS
    except (ValueError, AssertionError):
        return RedirectResponse("/admin?error=Neispravan+datum+ili+vrijeme.", status_code=303)
    db.add_oneoff_session(title.strip(), starts, max(15, min(240, duration_min)),
                          max(1, min(40, capacity)), note.strip() or None, kind)
    return RedirectResponse(f"/raspored?week={(d - timedelta(days=d.weekday())).isoformat()}", status_code=303)


# ---------- profil (basic info, prompted after signup) ----------

@app.get("/profil", response_class=HTMLResponse)
def profil_page(request: Request):
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/profil')}", status_code=303)
    # the person's own data only: plans, uplate and računi are /moja-clanarina's
    # (tz: the Račun card's registration date, in the studio's time zone;
    # sexes: "Spol"'s options after its none, 27.11.2026)
    return templates.TemplateResponse(request, "profil.html", _ctx(
        request, user, first_login="dopuni" in request.query_params, tz=config.TZ, sexes=SEXES))


@app.post("/profil")
async def profil_save(request: Request, name: str = Form(...), last_name: str = Form(...),
                      birth_date: str = Form(""), phone: str = Form("")):
    """The profile's fields, every one as posted. The height, a field here
    from 23.11.2026, is the karton's since 26.11.2026 (the owner's note:
    "visinu maknut iz profila u karton"; POST /karton/visina): nothing here
    reads it, and a save keeps the stored one. "Spol" (27.11.2026,
    db.read_sex: "f", "m", "" for not said; anything else refused, nothing
    saved): a form that posts none (a page drawn before the field) keeps
    the stored one. It is read off the form itself: FastAPI takes an
    emptied field for one not sent, and "" here is "Ne želim navesti".
    Staff acting as the member set his: it is his profile (the record has
    the write)."""
    sex = (await request.form()).get("sex")
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    born = None
    if birth_date.strip():
        try:
            born = date.fromisoformat(birth_date)
            assert date(1900, 1, 1) <= born <= config.today()
        except (ValueError, AssertionError):
            return RedirectResponse("/profil?error=Neispravan+datum+rođenja.", status_code=303)
    if not name.strip() or not last_name.strip():
        return RedirectResponse("/profil?error=Ime+i+prezime+su+obavezni.", status_code=303)
    try:
        if sex is not None and not isinstance(sex, str):
            raise ValueError(db.BAD_SEX)                          # a file where a choice goes
        given = db.KEEP if sex is None else db.read_sex(sex)
    except ValueError as e:
        from urllib.parse import quote
        return RedirectResponse("/profil?error=" + quote(str(e)), status_code=303)
    entry_pass = not user.profile_complete       # the after-sign-up completion
    db.update_profile(user.id, name, last_name, born, phone, sex=given)
    if entry_pass and born is not None:
        # done onboarding: drop them on the landing page, not back on the form
        # (still incomplete -> stay here so they can finish)
        from urllib.parse import quote

        return RedirectResponse("/?ok=" + quote("Profil je spremljen — dobrodošli!"),
                                status_code=303)
    return RedirectResponse("/profil?ok=Podaci+su+spremljeni.", status_code=303)


# ---------- karton (personal file: upitnik + diary + calendar) ----------

def _diary_rows(subject_id: int) -> list[dict]:
    """The dnevnik, newest first: every past termin this client booked, each
    carrying what was written about it — an osvrt, a "nisam bio/la", or nothing
    yet. Session-less legacy rows keep their place by date. Nothing is dropped:
    an osvrt whose termin falls outside booking_history's window still shows.
    Since 30.10.2026 his finished online passes (db.passes) join them by when
    they were started, each with its day's number of exercises now (`size`,
    None for a day that is gone or holds no exercise now) and, since
    4.11.2026, how many of those it saved (`done`: an entry whose exercise
    has left the day since is not counted; with no size, every entry).

    Since 26.11.2026 (build 3) his gym trainings join them (db.gym_trainings):
    a termin's rides on its termin's row (`gym`; the template shows it once
    it holds anything), each termin's row saying whether its training is
    his to write now (`open`: db.gym_window_open); one outside a termin (or
    let go of its termin, or of a termin past booking_history's twenty, or
    of one still ahead that holds something) has a row of its own, `open`
    by db.gym_can_write. A termin's training that holds nothing and no row
    of its termin here is no row: its termin says so once it is past."""
    from datetime import datetime, time

    sessions = db.booking_history(subject_id)
    logs = db.training_logs(subject_id)
    gyms = db.gym_trainings(subject_id)
    now = datetime.now(config.TZ)
    by_session = {x.session_id: x for x in logs if x.session_id}
    gym_by_session = {g.session_id: g for g in gyms if g.session_id}

    rows, attached, gym_attached = [], set(), set()
    for s in sessions:
        log = by_session.get(s.id)
        if log is not None:
            attached.add(log.id)
        g = gym_by_session.get(s.id)
        if g is not None:
            gym_attached.add(g.id)
        rows.append({"session": s, "log": log, "gym": g, "at": s.starts_at.astimezone(config.TZ),
                     "open": db.gym_window_open(s.starts_at, now)})
    for x in logs:
        if x.id in attached:
            continue
        at = (x.session.starts_at.astimezone(config.TZ) if x.session
              else datetime.combine(x.date, time(0), tzinfo=config.TZ))
        rows.append({"session": x.session, "log": x, "at": at})
    for g in gyms:
        if g.id in gym_attached or (g.session_id is not None and not g.holds_anything):
            continue
        at = (g.starts_at.astimezone(config.TZ) if g.starts_at is not None
              else datetime.combine(g.held_on, time(0), tzinfo=config.TZ))
        rows.append({"session": None, "log": None, "gym": g, "at": at, "open": db.gym_can_write(g, now)})
    workouts = db.passes(subject_id)
    held = db.day_item_ids({w.day_id for w in workouts if w.day_id is not None})
    for w in workouts:
        ids = held.get(w.day_id)             # None: the day gone, or holding no exercise now
        rows.append({"session": None, "log": None, "workout": w, "at": w.started_at.astimezone(config.TZ),
                     "size": len(ids) if ids else None, "done": w.done_in(ids) if ids else w.done_count})
    rows.sort(key=lambda r: r["at"], reverse=True)
    return rows


# The weight card's history (23.11.2026): the newest twelve in the list,
# the rest under "prikaži sve" (the member's); the trainer's view folds the
# whole of a longer one under "Povijest".
WEIGHTS_SHOWN = 12
# An exercise's history on the karton (25.11.2026, "Povijest vježbe"): the
# newest ten times, the rest under "prikaži sve".
HISTORY_SHOWN = 10


def _body_line(height_cm: int | None, latest) -> str:
    """The karton's head line of the body (23.11.2026): "Visina 178 cm ·
    Masa 82,5 kg (12.11.)", the height from the profile and the newest
    entry that has a mass (a models.Weight, None for none; since 25.11.2026
    an entry may be a document alone) with its day (_date_text: its year in
    another year), each part only when it is known; "" for none."""
    parts = []
    if height_cm:
        parts.append(f"Visina {height_cm} cm")
    if latest is not None:
        parts.append(f"Masa {latest.kg_text} kg ({_date_text(latest.measured_on)})")
    return " · ".join(parts)


def _month_label(d: date) -> str:
    """A month as the karton's photos name it, "studeni 2026." (the
    nominative, as the month view's label)."""
    return f"{MONTHS[d.month - 1]} {d.year}."


templates.env.globals["month_label"] = _month_label


def _render_karton(request: Request, viewer, subject, own: bool):
    import json

    onboarding = db.get_onboarding(subject.id)
    answers = json.loads(onboarding.answers) if onboarding else {}
    texts = db.copy_texts()
    # The upitnik block. A version-2 response: its score ("6,4 / 10"), part
    # 1's answers as chips, and for the trainer every answer it holds under
    # its question as the gym owner words it now (every question there is,
    # a hidden one too, a conditional one indented under the one it is
    # asked after; one deleted since under "(pitanje uklonjeno)": a
    # client's answers are never dropped), and where it hurts, the pain
    # flag's words (upitnik.pain_where: the answer to the free-text question
    # asked after the pain question). A version-1 row: its answers as
    # QUESTIONS_V1 reads them.
    pain_where = None
    if onboarding is not None and onboarding.version >= 2:
        rows = db.upitnik_questions()
        yes, no = (texts.get(f"upitnik.{k}") or copy.SLOTS[f"upitnik.{k}"].default for k in ("yes", "no"))
        u_rows = upitnik.answer_rows(answers, rows, yes, no)
        u_chips, u_score = upitnik.chips(answers, rows), upitnik.score_text(onboarding.score)
        pain_where = upitnik.pain_where(answers, rows)
    else:
        u_rows, u_chips, u_score = upitnik.answer_rows_v1(answers), [], None
    today = config.today()
    born = subject.birth_date
    age = (today.year - born.year - ((today.month, today.day) < (born.month, born.day))
           if born else None)
    pending = db.pending_feedback(subject.id) if own else []
    diary = _diary_rows(subject.id)
    # the upcoming termini; their way into a gym training ("Upiši trening →",
    # 26.11.2026, build 3) went with build 2 of the dvoranski treninzi
    # (27.11.2026): the tab lists the open ones, the karton keeps the record
    upcoming = db.my_upcoming(subject.id)
    # the body and the photos (23.11.2026, Amir's karton, part 2): the
    # weights, the newest day first (the rail card's value and history, the
    # head line's "Masa"), the photos, the newest month first, and for the
    # member's own photo form the months a photo may be filed to, this one
    # first (its button says "Zamijeni ovomjesečnu" when this month has one)
    weights = db.weights(subject.id)
    photos = db.photos(subject.id)
    # "Tjelesna kompozicija" (25.11.2026): an entry may be a document with no
    # mass; the card's value and the head line's "Masa" are the newest entry
    # that has one. The documents under the limitations, the newest first.
    latest_kg = next((w for w in weights if w.kg is not None), None)
    docs = db.limitation_files(subject.id)
    # "Povijest vježbe" (25.11.2026): the exercises this karton holds (its
    # picker, #hx-json: [id, name, "5× · zadnji put 23.11.2026."]), and with
    # ?vjezba=<id> one of them, every time it was done and its estimated max
    # (the maxes' own); an id the karton does not hold says so
    maxes = db.estimated_maxes(subject.id)
    logged = db.logged_exercises(subject.id)
    hx, hx_unknown, picked = None, False, request.query_params.get("vjezba", "").strip()
    if picked:
        # a library id, or since 26.11.2026 an exercise gone from the library
        # in a gym training, read under its name's negative key (db.gone_key)
        pick = int(picked) if re.fullmatch(r"-?[0-9]{1,10}", picked) else None
        found = next((e for e in logged if e.exercise_id == pick), None)
        if found is None:
            hx_unknown = True
        else:
            hx = {"exercise": found, "rows": db.exercise_history(subject.id, found.exercise_id),
                  "max": next((m for m in maxes if m.exercise_id == found.exercise_id), None)}
    hx_rows = [[e.exercise_id, e.name, f"{e.times}× · zadnji put {e.last_on.strftime('%-d.%-m.%Y.')}"]
               for e in logged]
    # a staff member's own karton (24.11.2026): his diary (his online passes,
    # his trainings outside a termin), maxes, weight, limitations and photos
    # as a member's; no upitnik card (staff never fill it: POST /upitnik
    # refuses them) and no termini (they book none)
    staff_own = own and _can_edit_copy(subject)
    # and since 27.11.2026 the search for a member at its top (the way into
    # his app from 26.11.2026, build 4, until then; since the evening of
    # 27.11.2026 into a tab's view of him, POST /karton/clan):
    # _member_find.html over every member /kao lists, in its order
    find_members = _kao_members() if staff_own else []
    find_rows = _find_rows(find_members)
    # the slash forms read as the member's (27.11.2026): the texts here are
    # about him, the trainer's view of his karton too
    return templates.TemplateResponse(request, "karton.html", _ctx(
        request, viewer, copy_texts=texts, subject=subject, own=own, age=age, staff_own=staff_own, rod=subject.sex,
        can_upitnik=own and not staff_own and _has_online(subject),
        onboarding=onboarding, answers=answers,
        levels=upitnik.LEVELS, goals=upitnik.GOALS, max_score_v1=upitnik.MAX_SCORE_V1,
        u_rows=u_rows, u_chips=u_chips, u_score=u_score, pain_ask=upitnik.PAIN_ASK, pain_where=pain_where,
        pain_note=texts.get("upitnik.pain_note", copy.SLOTS["upitnik.pain_note"].default),
        diary=diary,
        # the termini he still owes his training stand out in the diary
        pending_ids={x.id for x in pending},
        feelings=FEELING_LABELS,
        upcoming=upcoming,
        maxes=maxes, first_day=db.FIRST_DAY,
        weights=weights, weights_shown=WEIGHTS_SHOWN, latest_kg=latest_kg,
        body_line=_body_line(subject.height_cm, latest_kg),
        photos=photos, photo_months=db.photo_months(today) if own else [],
        month_has_photo=any(p.month == today.replace(day=1) for p in photos),
        limitations_max=db.LIMITATIONS_MAX, image_mb=IMAGE_MB,
        docs=docs, docs_max=db.MAX_LIMITATION_FILES, doc_name_max=db.DOC_NAME_MAX,
        logged=logged, hx=hx, hx_unknown=hx_unknown, hx_rows=hx_rows, hx_shown=HISTORY_SHOWN,
        karton_path="/karton" if own else f"/karton/{subject.id}",
        # the trainer's view of a member's karton: "Otvori kao član" (26.11.2026)
        can_act=not own and not _can_edit_copy(subject),
        find_members=find_members, find_rows=find_rows,
        today=config.today(), tz=config.TZ,
    ))


@app.get("/karton", response_class=HTMLResponse)
def karton_self(request: Request):
    """The viewer's own karton: a member's, and since 24.11.2026 staff's too
    (the owner: "Lets show the Karton tab in the Admin view as well so that
    Amir can check out the changes we made there"; until then a trainer was
    sent to /clanarine). While staff act as a member it is the member's (in
    a tab's view too: the Karton tab's search, POST /karton/clan, lands
    here). A client's read-only karton is /karton/{id}, staff's."""
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/karton')}", status_code=303)
    return _render_karton(request, user, user, own=True)


PICK_MEMBER = "Odaberi člana s popisa."


def _find_rows(members: list[dict]) -> list[list]:
    """The search for a member's rows (_member_find.html's #kf-json, the
    Karton tab's and Dvoranski treninzi's, one list: _kao_members), for
    base.html's combobox: [id, the name (the row's first line), "email ·
    plans" (its muted second line; "bez članarine" for none; the plans alone
    for one named by his email), the email (what typing matches besides the
    name: never the plans; "" for one named by it)]."""
    rows = []
    for m in members:
        email = m["user"].email
        named = m["name"] != email
        plans = m["plans"] or "bez članarine"
        rows.append([m["user"].id, m["name"], f"{email} · {plans}" if named else plans, email if named else ""])
    return rows


def _find_member(request: Request, user, clan: str, tab: str, refused: str):
    """The two searches' entry (27.11.2026, evening; the owner: "when he
    enters the karton tab via the search bar, it should be read and write,
    just like going to Admin->gledaj kao član ... When entered via the
    karton tab search, I dont want to view the whole app as that user"):
    `clan`, 1–9 digits (its spaces aside) naming a member (an account that
    is neither a trainer nor the owner: _kao_members' rule) → a tab's view
    of him (_enter_member, `tab` both where "Izađi" returns and where it
    lands: his own page there, every form of his); nothing, junk, an id
    naming nobody or a staff account → `refused` saying "Odaberi člana s
    popisa.", nothing entered, no row. `user` is the staff member the route
    let in (_require_trainer)."""
    from urllib.parse import quote

    raw = clan.strip()
    member = db.get_user(int(raw)) if re.fullmatch(r"[0-9]{1,9}", raw) else None
    if member is None or _can_edit_copy(member):
        return RedirectResponse(refused + quote(PICK_MEMBER), status_code=303)
    return _enter_member(request, user, member, tab, tab, tab=True)


@app.post("/karton/clan")
def karton_find(request: Request, clan: str = Form("")):
    """The Karton tab's search (27.11.2026; a GET to his read-only karton
    until the evening, the owner then: "when he enters the karton tab via
    the search bar, it should be read and write"): staff's (a member 403,
    while acting in the whole app too; in a tab's view the guard has ended
    it first, so the staff member asks). A member picked → a tab's view of
    him, landing on his /karton (_find_member); refused, back to the Karton
    tab saying so. Declared before /karton/{user_id}."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    return _find_member(request, user, clan, "/karton", "/karton?error=")


@app.get("/karton/clan")
def karton_find_gone(request: Request):
    """The search's GET of 27.11.2026 (it opened a member's read-only
    karton) went with the evening's build: a GET enters nothing, so a page
    or a link still holding it lands on the Karton tab, where the search
    is. Staff's (a member 403). Declared before /karton/{user_id}, which
    would take "clan" for an id."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    return RedirectResponse("/karton", status_code=303)


@app.get("/karton/{user_id}", response_class=HTMLResponse)
def karton_client(request: Request, user_id: int):
    """A member's karton, read only, staff's. For some hours of 27.11.2026
    it was the owner's alone (the owner: "I would then not even allow him to
    open that"), then the Karton tab's search (GET /karton/clan) made it the
    trainer's way to a member's karton (the owner: "that user's Karton is
    opened, not the whole app as his view"), until the same evening's
    build, when the search came to open a tab's view of him instead (POST
    /karton/clan): Korisnici's "Karton" leads here, its "Otvori kao član"
    the whole app. Staff's in a tab's view too (_in_member_tab)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    with db.session_scope() as s:
        subject = s.get(db.User, user_id)
    if subject is None:
        raise HTTPException(status_code=404)
    return _render_karton(request, user, subject, own=False)


@app.get("/vodic", response_class=HTMLResponse)
def vodic_page(request: Request):
    """The guide through the training (29.10.2026, the owner: "a guide
    through the training", the gym owner's text, copy.VODIC_SECTIONS) on a
    page of its own: the guide /upitnik opens on, the same partial
    (_vodic.html), its button a link to /upitnik?od=1, which opens on the
    first question (the guide read). For members, a plan or not, and for
    the trainer and the owner, who retype its texts here or on /upitnik; a
    guest is sent to log in. In no nav and linked from nowhere yet: the
    first sign-up and the first payment are to lead here later (the
    owner), one link each."""
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/vodic')}", status_code=303)
    return templates.TemplateResponse(request, "vodic.html", _ctx(request, user))


@app.get("/upitnik", response_class=HTMLResponse)
def upitnik_page(request: Request, od: str = ""):
    """The online-trening upitnik (qmt.upitnik, version 2 since 26.10.2026),
    one question per screen, its questions the rows of upitnik_questions in
    their order (qmt.upitnik.steps), a conditional one (27.10.2026) only
    when the answer it is asked after is given (the page's script, from
    each step's data-parent and its condition). A client with an online
    plan fills it, from the first question every time: a refill starts
    fresh, nothing is preselected; he is asked the shown questions that no
    hidden question mutes (upitnik.client_steps, built from every row, so
    a hidden question hides the questions asked after it). The
    trainer and the owner get it too, a plan or not: this is where they
    edit it (they never submit it: POST /upitnik refuses them). Their page
    holds every question, a hidden one marked off (a step only in edit
    mode), and in edit mode each question's controls (its switch, ↑ / ↓,
    "Obriši pitanje", its settings, "Pita se" among them), the lines under
    them that say what the settings do and when it is asked, the scoring's
    summary above the first question, and "+ Dodaj pitanje" under the last
    while there is room for another. Since 29.10.2026 it opens on the guide
    through the training (_vodic.html: the gym owner's introduction, before
    question 1), a refill too, the editor's preview too; with ?od=1 (the
    guide read: /vodic's button, a refused submission) on the first
    question. The form's data-start names that step."""
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/upitnik')}", status_code=303)
    editor = _can_edit_copy(user)
    if not editor and not _has_online(user):
        return RedirectResponse(
            "/karton?error=Upitnik+je+dio+online+članarine+—+javi+se+treneru.", status_code=303)
    rows = db.upitnik_questions()
    steps = upitnik.steps(rows) if editor else upitnik.client_steps(rows)
    # the questions others are asked after (shown ones that a deletion
    # would leave asked of everyone): their "Obriši pitanje" says so
    parents = {q.parent for q in steps if q.condition and q.shown and q.parent is not None} if editor else set()
    # where it opens: the guide, or with ?od=1 the first question asked (an
    # editor's first row may be hidden; with none at all, the last screen)
    first = next((q.id for q in steps if q.shown and not q.muted), "end")
    return templates.TemplateResponse(request, "upitnik.html", _ctx(
        request, user, steps=steps, scale=upitnik.SCALE, yes=upitnik.YES, no=upitnik.NO,
        text_max=upitnik.TEXT_MAX, pain_high_at=upitnik.PAIN_HIGH,
        start=f"step-{first}" if od == "1" else "step-vodic",
        last_row=len(rows), summary=upitnik.scoring_summary(steps) if editor else None,
        lines={q.id: upitnik.setting_line(q) for q in steps} if editor else {},
        ifs={q.id: upitnik.condition_line(q) for q in steps} if editor else {},
        blocked=upitnik.blocked_moves(steps) if editor else {}, parents=parents,
        kinds=upitnik.KINDS, scorings=upitnik.SCORING, roles=upitnik.ROLE_LABELS, role_kinds=upitnik.ROLES,
        parts=upitnik.PARTS, cond_kinds=upitnik.CONDITION_KINDS, short=upitnik.short,
        answer_choices=upitnik.answer_choices,
        can_add_question=editor and len(rows) < db.MAX_UPITNIK_QUESTIONS))


@app.post("/upitnik")
async def upitnik_submit(request: Request):
    """A filled upitnik: every question asked (the shown rows no hidden
    question mutes, as they are now: upitnik.client_steps) must be
    answered (upitnik.read: a choice with one of its options
    as the row holds them now, a multi with one or more of them, a scale
    1–10, yes / no, a free text; a conditional question when the answer it
    is asked after was given) and the consent ticked, or back to the form
    saying why, nothing stored. Then scored and leveled over the same questions
    (upitnik.evaluate: the scored scales, the safety rules), saved with the
    goal upitnik.GOAL, and straight to the programmes: the flash names the
    level, and for a client in pain adds the sentence that sends him to the
    trainer first (upitnik.pain_note). The trainer and the owner edit the
    questionnaire and never fill it (the page they get is the editor's: a
    choice is his options list, no radio): refused. A refusal comes back
    with ?od=1, on the first question (29.10.2026): whoever sends the form
    has read the guide that stands before it."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if _actor(request):
        # staff acting as the member (26.11.2026): his consent is his own
        from urllib.parse import quote
        return RedirectResponse(
            "/upitnik?od=1&error=" + quote("Upitnik ispunjava član sam — privola mora biti njegova."), status_code=303)
    if _can_edit_copy(user):
        return RedirectResponse(
            "/upitnik?od=1&error=Upitnik+ispunjavaju+članovi+—+ovdje+se+uređuju+samo+tekstovi.", status_code=303)
    if not _has_online(user):
        return RedirectResponse(
            "/karton?error=Upitnik+je+dio+online+članarine+—+javi+se+treneru.", status_code=303)
    form = await request.form()
    import json
    from urllib.parse import quote

    texts = db.copy_texts()
    asked = upitnik.client_steps(db.upitnik_questions())
    # every value a field was sent with (a multi's ticks are several), each
    # cleaned as a copy text is, so an option's text compares as the row
    # stored it (a browser sends a line break inside one as CRLF)
    posted = {key: [copy.clean(v) for v in form.getlist(key) if isinstance(v, str)] for key in form.keys()}
    try:
        answers = upitnik.read(posted, asked)
    except ValueError:
        return RedirectResponse("/upitnik?od=1&error=Odgovori+na+sva+pitanja.", status_code=303)
    if not any(posted.get("consent", ())):
        return RedirectResponse("/upitnik?od=1&error=" + quote("Potvrdi pristanak na obradu podataka o zdravlju."),
                                status_code=303)
    result = upitnik.evaluate(answers, asked)
    db.save_onboarding(user.id, json.dumps(answers, ensure_ascii=False), result.score, result.level, upitnik.GOAL,
                       version=upitnik.VERSION, pain_level=result.pain_level, pain_high=result.pain_high,
                       needs_review=result.needs_review, consented_at=datetime.now(config.TZ))
    # straight to the programmes — the routing is the whole point of the upitnik
    flash = f"Upitnik je spremljen — {upitnik.LEVELS[result.level]}."
    note = texts.get("upitnik.pain_note", copy.SLOTS["upitnik.pain_note"].default)
    if result.pain_high and note:
        flash += f" {note}"
    return RedirectResponse("/treninzi?ok=" + quote(flash), status_code=303)


# ---------- the upitnik's questions: added, set, moved, deleted (their texts: POST /copy/{key}) ----------
# The editor's controls in edit mode on /upitnik (the trainer, the owner).
# "nova" is declared before "{question_id}": a path parameter that fails
# its int is a 422, never the next route.

@app.post("/upitnik/pitanje/nova")
def upitnik_pitanje_nova(request: Request):
    """The editor's "+ Dodaj pitanje" (edit mode, a plain form): a new
    question after the last one, a scale in part 2 that scores nothing,
    shown, with placeholder texts to retype in place (copy.UPITNIK_BLANK).
    Back to it on /upitnik; at the cap with a sentence why."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    question = db.add_upitnik_question(user.id)
    if question is None:
        return RedirectResponse(f"/upitnik?error=Najviše+{db.MAX_UPITNIK_QUESTIONS}+pitanja.", status_code=303)
    return RedirectResponse(f"/upitnik#step-q{question.id}", status_code=303)


@app.post("/upitnik/pitanje/{question_id}")
async def upitnik_pitanje(request: Request, question_id: int):
    """A question's settings, as the editor's controls post them at a
    change (fetch, JSON back, as POST /copy/{key}): part ("1"–"4"), kind
    (choice, multi, scale, yesno, text), scoring ("", baza, navike: a
    scale's), role ("", pain: a scale, injuries: a yes / no; taking one
    another question holds takes it from that one), shown ("on" / "off"),
    and since 27.10.2026 its "Pita se", two fields posted together:
    parent_id (an earlier question's id) and condition (the answer to it
    that asks this one: "yes" / "no", an option's text, ">=N"), both empty
    for always. The rules are qmt.upitnik.settings' and
    qmt.upitnik.condition's (the question before it, no circle, an answer
    it can give), their sentence the 400's error; a question that is not
    there is a 404. The answer is the row's settings as stored ("on": its
    switch, as a flag's answer says it)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    form = await request.form()
    changes = {key: value for key, value in form.items() if isinstance(value, str)}
    try:
        q = db.set_upitnik_question(question_id, changes, user.id)
    except LookupError:
        return JSONResponse({"ok": False, "error": "Nepoznato pitanje."}, status_code=404)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "id": q.id, "part": q.part, "kind": q.kind, "scoring": q.scoring,
                         "role": q.role, "shown": q.shown, "on": q.shown, "parent_id": q.parent_id,
                         "condition": q.condition})


@app.post("/upitnik/pitanje/{question_id}/pomak")
def upitnik_pitanje_pomak(request: Request, question_id: int, smjer: str = Form("")):
    """The editor's ↑ / ↓ (edit mode, a plain form): the question trades
    places with the one before it (smjer=gore) or after it (dolje), in the
    order of every question, the hidden too. Back to it on /upitnik; at
    either end nothing moves. A move that would put a question before the
    one it is asked after (27.10.2026) is refused: back to the top of the
    page, where the sentence shows ("Potpitanje ne može ići ispred svog
    pitanja."; his page says it at the press already, data-refuse)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    try:
        db.move_upitnik_question(question_id, smjer, user.id)
    except ValueError as e:
        from urllib.parse import quote
        return RedirectResponse("/upitnik?error=" + quote(str(e)), status_code=303)
    return RedirectResponse(f"/upitnik#step-q{question_id}", status_code=303)


@app.post("/upitnik/pitanje/{question_id}/obrisi")
def upitnik_pitanje_obrisi(request: Request, question_id: int):
    """The editor's "Obriši pitanje" (edit mode, a plain form the pill sends
    at its second tap): the question goes; the answers clients gave it stay
    (the karton prints them under "(pitanje uklonjeno)"). Back to /upitnik,
    at the question that was before it (the first one, when it was first).
    A question already gone is nothing to do."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    ids = [q.id for q in db.upitnik_questions()]
    near = None
    if question_id in ids:
        i = ids.index(question_id)
        rest = ids[:i] + ids[i + 1:]
        near = rest[max(i - 1, 0)] if rest else None
    db.delete_upitnik_question(question_id)
    return RedirectResponse("/upitnik" + (f"#step-q{near}" if near else ""), status_code=303)


@app.post("/karton/absent/{session_id}")
def karton_absent(request: Request, session_id: int):
    """"Nisam bio/la" — recorded against this client only; the termin itself is
    shared and stays as it was."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        db.mark_session_absent(user.id, session_id)
    except db.BookingError as e:
        from urllib.parse import quote
        return RedirectResponse(f"/karton?error={quote(str(e))}", status_code=303)
    return RedirectResponse("/karton?ok=Zabilježeno+—+nisi+bio/la+na+terminu.",
                            status_code=303)


@app.post("/karton/log/{log_id}/edit")
def karton_log_edit(request: Request, log_id: int, effort: int = Form(...),
                    feeling: str = Form(""), note: str = Form(""), day: str | None = Form(None)):
    """The client corrects their own osvrt — same fields, same rules as
    writing it was: a TrainingLog row of the plain form of 23.11.2026 (none
    is made since 26.11.2026, build 3), its napor, osjećaj and komentar; its
    exercises are read only since then. A training outside a termin's date
    may move too (`day`, db.read_day: the form of such a row posts it), a
    termin's never (db.update_training_log keeps it). A refusal changes
    nothing and says why."""
    from urllib.parse import quote

    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not 1 <= effort <= 10 or (feeling and feeling not in FEELING_LABELS):
        return RedirectResponse("/karton?error=Neispravan+osvrt.", status_code=303)
    try:
        when = None if day is None else db.read_day(day)
        saved = db.update_training_log(log_id, user.id, effort, feeling or None, note.strip(), day=when)
    except ValueError as e:
        return RedirectResponse(f"/karton?error={quote(str(e))}", status_code=303)
    if not saved:
        return RedirectResponse("/karton?error=Zapis+ne+postoji.", status_code=303)
    return RedirectResponse(f"/karton?ok=Osvrt+je+spremljen.#log-{log_id}", status_code=303)


@app.post("/karton/log/{log_id}/delete")
def karton_log_delete(request: Request, log_id: int):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not db.delete_training_log(log_id, user.id):
        raise HTTPException(status_code=404)
    return RedirectResponse("/karton?ok=Zapis+je+obrisan.", status_code=303)


# ---------- the karton's body and photos (23.11.2026, Amir's karton, part 2) ----------
#
# The member's own: his weight on a day, his limitations and pains, a photo
# of a month. Each route writes for the member logged in and comes back to
# its card on /karton (#masa, #ogranicenja, #napredak) with what happened;
# a refusal stores nothing and says why. A delete matches his own rows only
# (another member's id is 404).

def _karton_back(card: str, error: str | None = None, ok: str | None = None) -> RedirectResponse:
    from urllib.parse import quote

    query = f"error={quote(error)}" if error else f"ok={quote(ok or '')}"
    return RedirectResponse(f"/karton?{query}#{card}", status_code=303)


def _spool_upload(upload: UploadFile, raw: Path) -> bool:
    """An upload spooled to `raw` in 1 MB chunks, to IMAGE_MB (15) at most:
    False as soon as it is bigger (the cap trips before Pillow reads a byte,
    let alone storage; the caller's temp dir takes what was written). The
    karton's monthly photo and its documents (25.11.2026)."""
    total = 0
    with raw.open("wb") as f:
        while chunk := upload.file.read(1 << 20):
            total += len(chunk)
            if total > IMAGE_MB * 1024 * 1024:
                return False
            f.write(chunk)
    return True


# A karton document (25.11.2026, Amir: "U ograničenja i bolovi treba dodati
# mogućnost da se doda slika ili pdf … tjelesna kompozicija gdje opet mogu
# dodati pdf ili sliku"): a PDF, kept as it came, or an image, shrunk as the
# photos are but to a larger side, so a photographed printout stays legible.
DOC_PX = 2400
_DOC_SUFFIXES = (".pdf",) + _IMAGE_SUFFIXES
_DOC_UNSUPPORTED = "Nepodržan format — dozvoljeno: pdf, jpg, png, webp."
# what /media serves a member's file as, by its stored name's extension
_MEMBER_FILE_TYPES = {".pdf": "application/pdf", ".jpg": "image/jpeg"}


def _store_document(upload: UploadFile | None, stem: str) -> str | None:
    """A karton document stored (25.11.2026): its new name, `stem` and a
    random part (nalaz-<user id>-<hex>.<ext> under the limitations,
    sastav-<user id>-<YYYYMMDD>-<hex>.<ext> for an entry of "Tjelesna
    kompozicija"); None when no file came (none chosen: its name empty).
    A PDF by its name (.pdf) AND its first bytes (%PDF-), stored as it is
    (application/pdf); an image by its name (jpg / png / webp) and by what
    Pillow finds, shrunk to DOC_PX (_shrink_image: upright, no EXIF) and
    stored as .jpg (image/jpeg); at most IMAGE_MB (_spool_upload). ValueError
    with the sentence to show: another format, a fake PDF, an image Pillow
    cannot read ("Nepodržan format — dozvoljeno: pdf, jpg, png, webp."), one
    too big; nothing is stored then."""
    if upload is None or not (upload.filename or "").strip():
        return None
    import secrets
    import tempfile

    suffix = Path(upload.filename.replace("\\", "/")).suffix.lower()
    if suffix not in _DOC_SUFFIXES:
        raise ValueError(_DOC_UNSUPPORTED)
    with tempfile.TemporaryDirectory() as tmp:       # whatever is left in it goes, a refusal's bytes too
        raw = Path(tmp) / "upload"
        if not _spool_upload(upload, raw):
            raise ValueError(f"Dokument je veći od {IMAGE_MB} MB.")
        if suffix == ".pdf":
            with raw.open("rb") as f:
                if f.read(5) != b"%PDF-":                 # a file of another kind renamed
                    raise ValueError(_DOC_UNSUPPORTED)
            name, path, kind = f"{stem}-{secrets.token_hex(8)}.pdf", raw, "application/pdf"
        else:
            path = Path(tmp) / "dokument.jpg"
            try:
                path.write_bytes(_shrink_image(raw, DOC_PX))
            except ValueError:
                raise ValueError(_DOC_UNSUPPORTED) from None
            name, kind = f"{stem}-{secrets.token_hex(8)}.jpg", "image/jpeg"
        storage.save(name, path, kind)
    return name


@app.post("/karton/masa")
def karton_weight(request: Request, kg: str = Form(""), day: str = Form(""),
                  dokument: UploadFile | None = File(None)):
    """An entry of the member's "Tjelesna kompozicija" on a day (the card's
    form, multipart since 25.11.2026): a mass, kg 20–300 in steps of 0.1,
    "82,5" or "82.5" (db.read_weight: "Neispravna masa."), a document
    (_store_document: a PDF or an image, sastav-<id>-<YYYYMMDD>-<hex>, its
    link named by the upload's own name), or both; neither, "Upiši masu ili
    dodaj dokument."; the day not in the future, not before 2020
    (db.read_day: "Neispravan datum."). A second save that day replaces
    what it gives and keeps what it does not (db.set_weight), a document
    replaced deleted from storage. A refusal stores nothing."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        on = db.read_day(day)
        mass = db.read_weight(kg) if kg.strip() else None
        if mass is None and (dokument is None or not (dokument.filename or "").strip()):
            raise ValueError(db.NO_MASS_NOR_FILE)
        name = _store_document(dokument, f"sastav-{user.id}-{on:%Y%m%d}")
    except ValueError as e:
        return _karton_back("masa", error=str(e))
    try:
        old = db.set_weight(user.id, on, mass, file=name,
                            file_name=db.doc_name("", dokument.filename) if name else "")
    except (ValueError, LookupError) as e:               # the account went while its file went up
        if name:
            storage.delete(name)
        if isinstance(e, LookupError):
            return RedirectResponse("/login", status_code=303)
        return _karton_back("masa", error=str(e))
    if old:
        storage.delete(old)
    ok = ("Masa i dokument su spremljeni." if mass is not None and name else
          "Masa je spremljena." if mass is not None else "Dokument je spremljen.")
    return _karton_back("masa", ok=ok)


@app.post("/karton/masa/{weight_id}/obrisi")
def karton_weight_delete(request: Request, weight_id: int):
    """An entry of the member's own taken out of his history (its ✕ asks
    first): the row, then its document's file; another member's, or one
    gone, is 404."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    name = db.delete_weight(weight_id, user.id)
    if name is None:
        raise HTTPException(status_code=404)
    if name:
        storage.delete(name)
    return _karton_back("masa", ok="Unos je obrisan.")


@app.post("/karton/visina")
def karton_height(request: Request, visina: str = Form("")):
    """The member's height, on his karton's "Tjelesna kompozicija" since
    26.11.2026 (the owner's note: "visinu maknut iz profila u karton"; on
    /profil until then): "uredi" / "upiši" opens its one field, whole
    centimetres 100–250 (db.read_height: "Neispravna visina.", nothing
    changed), empty to clear it. Back at the card (#masa)."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        height_cm = db.read_height(visina)
    except ValueError as e:
        return _karton_back("masa", error=str(e))
    db.set_height(user.id, height_cm)
    return _karton_back("masa", ok="Visina je spremljena.")


@app.post("/karton/ogranicenja")
def karton_limitations(request: Request, text: str = Form("")):
    """The member's limitations and pains, his own text (the card's Uredi):
    cleaned as copy is, at most 2000 characters (db.set_limitations:
    "Najviše 2000 znakova."), empty for none. The trainer reads it on
    /karton/{id}, flagged when it is not empty."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        db.set_limitations(user.id, text)
    except ValueError as e:
        return _karton_back("ogranicenja", error=str(e))
    except LookupError:
        return RedirectResponse("/login", status_code=303)
    return _karton_back("ogranicenja", ok="Ograničenja su spremljena.")


@app.post("/karton/ogranicenja/dokument")
def karton_limitation_doc(request: Request, naziv: str = Form(""), dokument: UploadFile | None = File(None)):
    """A document under the member's limitations (25.11.2026; the card's
    "Dodaj dokument", multipart): the file (_store_document: a PDF or an
    image, nalaz-<user id>-<hex>), and the name its list shows, "Naziv
    (neobavezno)", 80 characters, or the upload's own name, or "Dokument"
    (db.doc_name). At most ten (db.add_limitation_file: "Najviše 10
    dokumenata."). A refusal stores nothing and says why; the flash names
    no file."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if len(db.limitation_files(user.id)) >= db.MAX_LIMITATION_FILES:      # said before a byte is stored
        return _karton_back("ogranicenja", error=db.TOO_MANY_FILES)
    try:
        name = _store_document(dokument, f"nalaz-{user.id}")
        if name is None:
            raise ValueError(_DOC_UNSUPPORTED)
    except ValueError as e:
        return _karton_back("ogranicenja", error=str(e))
    try:
        db.add_limitation_file(user.id, name, db.doc_name(naziv, dokument.filename))
    except (ValueError, LookupError) as e:               # the tenth went in meanwhile, or the account went
        storage.delete(name)
        if isinstance(e, LookupError):
            return RedirectResponse("/login", status_code=303)
        return _karton_back("ogranicenja", error=str(e))
    return _karton_back("ogranicenja", ok="Dokument je spremljen.")


@app.post("/karton/ogranicenja/dokument/{file_id}/obrisi")
def karton_limitation_doc_delete(request: Request, file_id: int):
    """A document of the member's own deleted (its ✕ asks first): the row,
    then its file; another member's, or one gone, is 404."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    name = db.delete_limitation_file(file_id, user.id)
    if name is None:
        raise HTTPException(status_code=404)
    storage.delete(name)
    return _karton_back("ogranicenja", ok="Dokument je obrisan.")


@app.post("/karton/slika")
def karton_photo(request: Request, mjesec: str = Form(""), slika: UploadFile | None = File(None)):
    """A member's photo of a month (the photo card's form, multipart): the
    month it is OF, this one or one of the eleven before it (db.read_month:
    "Neispravan mjesec."), and the file, jpg / png / webp by its name and by
    what Pillow finds in it, at most IMAGE_MB (15) MB, spooled as an
    announcement's photo is, then _shrink_image's (upright, 1600 px on its
    long side at most, a progressive JPEG with no EXIF), stored as
    napredak-<user id>-<YYYYMM>-<hex>.jpg. One a month: a photo that month
    had is replaced (db.set_photo) and its file deleted once no row names
    it. Served by /media to the member and staff only."""
    import secrets
    import tempfile

    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        month = db.read_month(mjesec)
    except ValueError as e:
        return _karton_back("napredak", error=str(e))
    if slika is None or Path(slika.filename or "").suffix.lower() not in _IMAGE_SUFFIXES:
        return _karton_back("napredak", error=_IMAGE_UNSUPPORTED)
    with tempfile.TemporaryDirectory() as tmp:       # whatever is left in it goes, a refusal's bytes too
        raw, out = Path(tmp) / "upload", Path(tmp) / "slika.jpg"
        # spooled in 1 MB chunks to the cap, as copy_image_upload does
        if not _spool_upload(slika, raw):
            return _karton_back("napredak", error=f"Slika je veća od {IMAGE_MB} MB.")
        try:
            out.write_bytes(_shrink_image(raw))
        except ValueError:
            return _karton_back("napredak", error=_IMAGE_UNSUPPORTED)
        name = f"napredak-{user.id}-{month:%Y%m}-{secrets.token_hex(8)}.jpg"
        storage.save(name, out, "image/jpeg")
    try:
        old = db.set_photo(user.id, month, name)
    except LookupError:                                  # the account went while its photo went up
        storage.delete(name)
        return RedirectResponse("/login", status_code=303)
    if old:
        storage.delete(old)
    return _karton_back("napredak", ok="Fotografija je spremljena.")


@app.post("/karton/slika/{photo_id}/obrisi")
def karton_photo_delete(request: Request, photo_id: int):
    """A photo of the member's own deleted (its ✕ asks first): the row,
    then its file; another member's, or one gone, is 404."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    name = db.delete_photo(photo_id, user.id)
    if name is None:
        raise HTTPException(status_code=404)
    storage.delete(name)
    return _karton_back("napredak", ok="Fotografija je obrisana.")


# ---------- the gym training (26.11.2026, build 3; since 27.11.2026 blocks, at /dvoranski) ----------
#
# roadmap/2026-11-26-gym-training-plan.md, build 3; the owner: "I would
# remove the 'dodaj trening' and automatically add the training with its
# title already after a user booked it" … "The training should have a date
# and time written on it so that there is no confusion which training they
# edit." Since 27.11.2026 (build 1 of roadmap/2026-11-27-dvoranski-treninzi-
# plan.md; the owner: "A gym training consists of 'Stanica' and 'Kružni
# set'"; "not static: the online player's layout") a member's training
# (models.GymTraining) is a row of blocks on ONE page in the player's layout
# (karton_trening.html, /dvoranski/trening/<id>): the segmented strip, "←
# Natrag", the clock from the first tick, "Završi trening"; the head; the
# block on screen as the main card (?blok=<id>: by default the first not
# done; every one done, the "what next" card; none at all, the template
# chooser); the overview of every block (#pregled), its end "+ Stanica" and
# "+ Kružni set"; the foot. A Stanica is its one exercise: empty, ONE form
# (the exercise and what is asked) and "Kreni"; started, its set table, a
# tick per set that saves (rule 4, a fetch POST, JSON back) and starts the
# pause bar, its rating, "Nastavi trening" (the next block not done) and
# "Završi trening". A Kružni set is set up (its rows, Krugova, the pause
# after a Krug; "Kreni" opens Krug 1), then done a Krug at a time, each Krug
# one form ("Krug 2 odrađen"), a saved one corrected during the pause
# ("Spremi izmjene"). The routes are the effective user's own (current_user:
# the member, staff acting as him too): another member's training is 404.
# Every write asks db.gym_can_write, `staff` being app._actor; a refused one
# changes nothing and says so in the main card. The old addresses
# (/karton/termin/<id>/trening, /karton/trening/<id> and its osvrt) lead
# here, query kept; their writes went. Since build 2 (27.11.2026) the pages
# hang under the tab "Dvoranski treninzi" (GET /dvoranski, below): its tab
# lit, "← Natrag" to it (the karton's diary row for a viewer with no tab),
# and a training outside a termin made there (POST /dvoranski/trening; the
# Karton's own form, POST /karton/trening, went).

# the end of a training's window as its state line says it: "do četvrtka 26.11. u ponoć"
WEEKDAYS_GEN = ("ponedjeljka", "utorka", "srijede", "četvrtka", "petka", "subote", "nedjelje")
GYM_SAVED = "Spremljeno."
# a tick on a row that holds no number (an exercise asked nothing: its
# inputs start empty): refused, so that a tick shown is always a set saved
GYM_EMPTY_ROW = "Upiši broj pa označi seriju."
# the clock shows while the training's first tick is at most this old
GYM_CLOCK_HOURS = 4


def _gym_staff(request: Request) -> bool:
    """Staff acting as the member (rule 1: they write at any time)."""
    return _actor(request) is not None


def _gym_of(request: Request, training_id: int):
    """(the effective user, his training) for a route; (None, None) for a
    guest; 404 for a training that is not his."""
    user = current_user(request)
    if user is None:
        return None, None
    t = db.gym_training(training_id, user.id)
    if t is None:
        raise HTTPException(status_code=404)
    return user, t


def _gym_block(t, block_id: int):
    """A block of this training, or 404."""
    b = next((x for x in t.blocks if x.id == block_id), None)
    if b is None:
        raise HTTPException(status_code=404)
    return b


def _gym_url(training_id: int, anchor: str = "", **query) -> str:
    """The training's page with its query (None leaves a key out) and an
    anchor: /dvoranski/trening/<id>?blok=<b>&error=…#krug-<b>-<n>."""
    from urllib.parse import urlencode

    pairs = [(k, str(v)) for k, v in query.items() if v is not None]
    return f"/dvoranski/trening/{training_id}" + (f"?{urlencode(pairs)}" if pairs else "") + (f"#{anchor}" if anchor else "")


def _gym_back(training_id: int, anchor: str = "", **query) -> RedirectResponse:
    return RedirectResponse(_gym_url(training_id, anchor, **query), status_code=303)


def _gym_until(starts_at: datetime) -> str:
    """When a termin's training closes for its member, its state line's
    words after "Upis je otvoren do": the day after the termin, "četvrtka
    26.11. u ponoć" (its midnight: db.gym_window)."""
    day = starts_at.astimezone(config.TZ).date() + timedelta(days=1)
    return f"{WEEKDAYS_GEN[day.weekday()]} {day.day}.{day.month}. u ponoć"


def _gym_when(t) -> str:
    """The training's date and time as its page says them, right under its
    title: "srijeda 25.11.2026. · 18:00" (a termin's, its start), "srijeda
    25.11.2026." (outside a termin, its date)."""
    if t.starts_at is not None:
        at = t.starts_at.astimezone(config.TZ)
        return f"{DAY_WEEKDAYS[at.weekday()]} {at:%-d.%-m.%Y.} · {at:%H:%M}"
    return f"{DAY_WEEKDAYS[t.held_on.weekday()]} {t.held_on:%-d.%-m.%Y.}"


def _gym_rows(it) -> list[dict]:
    """A Stanica's set table, {"reps", "kg", "sec": an input's value,
    "ticked"} per row: the ticked sets as saved, then a row per planned set
    left (three when no Serije was given), each prefilled with what was
    asked (its reps, seconds and kg) and nothing else (rule 5: no load next
    time here)."""
    planned = min(it.sets or 3, db.MAX_SETS)
    first = {"reps": "" if it.reps is None else str(it.reps), "kg": _kg_value(it.kg),
             "sec": "" if it.seconds is None else str(it.seconds)}
    rows = [dict(_set_values(st), ticked=True) for st in it.done_sets[:db.MAX_SETS]]
    return rows + [dict(first, ticked=False) for _ in range(planned - len(rows))]


def _gym_krugs(b, want: int | None, just: int | None) -> list[dict]:
    """A Kružni set's Krug as the page shows them, in order: {"n", "saved",
    "open", "line" (a saved one's folded line), "rows": per row a Krug takes
    inputs for (GymTrainingBlock.round_rows) {"it", "fields" (db.set_fields),
    "reps", "kg", "sec"}}. Shown: every saved Krug (folded, a `<details>`
    opened again to be corrected; the one just saved, `just`, open with
    "Spremi izmjene") and the Krug on screen, the first not saved (open;
    `want`, the Krug a refused save came back to, open too); a later one
    not saved is not. First values: what this Krug saved, else what the
    Krug before did, else what was asked (rule 5: no load next time)."""
    if not b.circuit or not b.rounds:
        return []
    saved, current, rows = b.rounds_saved, b.current_round, b.round_rows
    out = []
    for n in range(1, b.rounds + 1):
        if n not in saved and n != current:
            continue
        cells = []
        for it in rows:
            mine = it.round_set(n)
            before = it.round_set(n - 1) if n > 1 else None
            if mine is not None:
                values = _set_values(mine)
            elif before is not None:
                values = _set_values(before)
            else:
                values = {"reps": "" if it.reps is None else str(it.reps), "kg": _kg_value(it.kg),
                          "sec": "" if it.seconds is None else str(it.seconds)}
            cells.append({"it": it, "fields": db.set_fields(it), **values})
        out.append({"n": n, "saved": n in saved, "open": n == current or n == just or n == want,
                    "line": b.round_line(n), "rows": cells})
    return out


def _gym_next(t, b) -> str:
    """"Nastavi trening"'s target from block `b`: the next block after it
    that is not done, else the first not done before it, else the "what
    next" card (?dalje=1)."""
    blocks = t.blocks
    k = next((i for i, x in enumerate(blocks) if x.id == b.id), -1)
    later = [x for x in blocks[k + 1:] if not x.done]
    earlier = [x for x in blocks[:max(k, 0)] if not x.done]
    target = (later or earlier or [None])[0]
    return _gym_url(t.id, blok=target.id) if target is not None else _gym_url(t.id, dalje=1)


def _gym_next_empty(t, block_id: int) -> int | None:
    """"Spremi" on an empty block (28.11.2026): the next block after
    `block_id` that holds no exercise, else the first such before it, else
    None (every block is written)."""
    blocks = t.blocks
    k = next((i for i, x in enumerate(blocks) if x.id == block_id), -1)
    empty = [x for x in blocks[k + 1:] + blocks[:max(k, 0)] if not x.exercise_rows]
    return empty[0].id if empty else None


def _gym_saved(training_id: int, user_id: int, block_id: int) -> RedirectResponse:
    """Where "Spremi" on an empty block leads: the next block that holds no
    exercise, "Spremljeno." in it; with none left, back at this one."""
    t = db.gym_training(training_id, user_id)
    nxt = _gym_next_empty(t, block_id) if t is not None else None
    return _gym_back(training_id, "glavno", blok=nxt or block_id, ok=GYM_SAVED)


def _gym_overview(t, shown, writable: bool) -> list[dict]:
    """The overview's rows (#pregled), every block in order (read only:
    the blocks that hold an exercise, each with its record's lines):
    {"b", "label" (a Stanica's "Stanica 1"; a Kružni set's is a slot, None
    here), "name" (a Stanica's exercise, "" for an empty block), "facts"
    (what was asked; "4 vježbe · krug 2/4"), "mark", "cur" (the one on
    screen), "href", "lines"}."""
    out = []
    for b in t.blocks if writable else t.record_blocks:
        it = b.item
        out.append({"b": b, "label": None if b.circuit else f"Stanica {t.station_number(b)}",
                    "name": "" if b.circuit or it is None or it.is_slot else it.name, "facts": b.facts,
                    "mark": b.mark, "cur": shown is not None and b.id == shown.id,
                    "href": _gym_url(t.id, blok=b.id), "lines": [] if writable else b.lines()})
    return out


def _gym_page(request: Request, user, t, status_code: int = 200):
    """The training's page (karton_trening.html; the module's comment above
    this section). Its state line: a termin's training open to its member
    says until when ("Upis je otvoren do četvrtka 26.11. u ponoć"), closed
    after it ("Upis je zatvoren — trener ga i dalje može urediti.", read
    only: the head, the state line and the overview of what was done),
    before it rule 2's sentence; staff acting as him outside his window "Za
    člana je upis zatvoren; uređuješ kao trener."; a training outside a
    termin none. The query: ?blok=<id> the block on screen, ?dalje=1 the
    "what next" card, ?uredi=1 its "Uredi" open, ?krug=<n> a Krug to show
    open (Kreni's Krug 1, a refused save's), ?spremljen=<n> the Krug just
    saved (open, "Spremi izmjene"), ?kreni=1 the focus in a started
    station's first set, ?red=<id> in a Kružni set's new row, ?odmor=<s>
    (1–3600, anything else ignored) the pause bar at load, ?predlozak=1 the
    chooser's word."""
    q = request.query_params
    now = datetime.now(config.TZ)
    staff = _gym_staff(request)
    writable = db.gym_can_write(t, now, staff)
    state_key, state_text = None, ""
    if t.session_id is not None:
        if db.gym_can_write(t, now):
            state_key, state_text = "gym.state.open", _gym_until(t.starts_at)
        elif staff:
            state_key = "gym.state.staff"
        elif t.starts_at is not None and now < db.gym_window(t.starts_at)[0]:
            state_text = db.gym_opens_text()
        else:
            state_key = "gym.state.closed"
    asked = _id(q.get("blok"))
    shown = next((b for b in t.blocks if b.id == asked), None)
    if shown is None and q.get("dalje") != "1":
        shown = next((b for b in t.blocks if not b.done), None)
    view = None                                     # the main card
    if writable:
        view = ("chooser" if not t.blocks else "next" if shown is None
                else "circuit" if shown.circuit else "station")
    krug = _id(q.get("krug")) if shown is not None and shown.circuit else None
    just = _id(q.get("spremljen")) if shown is not None and shown.circuit else None
    setup = view == "circuit" and not shown.rounds_saved and krug is None
    templates_ = db.gym_templates() if writable and (not t.blocks or not t.ticked) else []
    rest = _id(q.get("odmor"))
    first = t.first_tick
    clock = (first.astimezone(config.TZ).isoformat(timespec="seconds")
             if writable and t.finished_at is None and first is not None
             and now - first <= timedelta(hours=GYM_CLOCK_HOURS) else "")
    total = len(t.blocks)
    station = view == "station"
    # a form's word comes back to the main card (?blok=, the block on screen)
    # or to the chooser (?predlozak=1, while it is on the page: the main
    # card's, or the foot's before the first tick), never to the page's top
    at_chooser = q.get("predlozak") == "1" and (view == "chooser" or (bool(t.blocks) and bool(templates_)))
    in_card = view in ("station", "circuit") and asked is not None and shown.id == asked and not at_chooser
    here = at_chooser or in_card
    texts = db.copy_texts()
    return templates.TemplateResponse(request, "karton_trening.html", _ctx(
        request, user, copy_texts=texts, t=t, when=_gym_when(t), writable=writable, state_key=state_key,
        state_text=state_text, can_date=writable and t.session_id is None and t.outside, view=view, shown=shown,
        kicker=f"Stanica {t.station_number(shown)} od {t.stations_count}" if station else "",
        rows=_gym_rows(shown.item) if station and shown.started and not shown.item.gone else [],
        fields=",".join(db.set_fields(shown.item)) if station else "",
        fixed=station and bool(shown.item.done_sets),
        setup=setup, krugs=_gym_krugs(shown, krug, just) if view == "circuit" and not setup else [],
        krug_head=(f"Krug {shown.current_round} od {shown.rounds}" if shown.current_round is not None
                   else shown.rounds_text) if view == "circuit" else "",
        next_href=_gym_next(t, shown) if shown is not None and writable else "",
        overview=_gym_overview(t, shown if view in ("station", "circuit") else None, writable),
        strip=[("cur" if shown is not None and b.id == shown.id and view != "next" else "done" if b.done else "")
               for b in t.blocks] if writable else [],
        segments=total <= SEGMENTS_MAX, track=round(100 * sum(1 for b in t.blocks if b.done) / total) if total else 0,
        done_n=sum(1 for b in t.blocks if b.done), n_blocks=total, clock=clock,
        templates_=templates_, can_add=writable and total < db.GYM_MAX_BLOCKS,
        uredi=q.get("uredi") == "1", krug_word=krug, red=_id(q.get("red")), focus_set=q.get("kreni") == "1",
        odmor=rest if writable and rest is not None and 1 <= rest <= 3600 else None,
        at_chooser=at_chooser, in_card=in_card, here=here,
        # "← Natrag": the tab (build 2, 27.11.2026), for staff acting as the
        # member whatever his plans (the evening of 27.11.2026: the page is
        # theirs for anyone, the gate the member's alone); a member with no
        # tab (his gym plan lapsed) the karton's diary row, as build 1's
        back="/dvoranski" if _has_gym(user) or staff else
        f"/karton#{'gt-%d' % t.id if t.holds_anything or t.session_id is None else 's-%d' % t.session_id}",
        library_rows=[[e.id, e.name, e.tags] for e, _ in db.exercises()] if writable and view in ("station", "circuit") else [],
        tags=_tag_chips() if writable and station else [], max_sets=db.MAX_SETS, first_day=db.FIRST_DAY,
        today=config.today()), status_code=status_code)


def _same_query(request: Request, path: str) -> RedirectResponse:
    """An old address's way to its new one, its query kept."""
    query = request.url.query
    return RedirectResponse(path + (f"?{query}" if query else ""), status_code=303)


@app.get("/karton/termin/{session_id}/trening")
def gym_from_termin_old(request: Request, session_id: int):
    """The old address of a termin's training (26.11.2026–27.11.2026):
    /dvoranski/termin/<id>, its query kept."""
    return _same_query(request, f"/dvoranski/termin/{session_id}")


@app.get("/karton/trening/{training_id}")
def gym_page_old(request: Request, training_id: int):
    """The old address of a training's page: /dvoranski/trening/<id>."""
    return _same_query(request, f"/dvoranski/trening/{training_id}")


@app.get("/karton/trening/{training_id}/osvrt")
def gym_osvrt_old(request: Request, training_id: int):
    """The old address of a training's osvrt: /dvoranski/trening/<id>/osvrt."""
    return _same_query(request, f"/dvoranski/trening/{training_id}/osvrt")


# ---------- the tab "Dvoranski treninzi" (27.11.2026, build 2) ----------
#
# roadmap/2026-11-27-dvoranski-treninzi-plan.md, build 2; the owner: "how
# long would it take to create a new tab called 'Dvoranski treninzi' in the
# same level of hierarchy as the 'Online treninzi' … Maybe it would make
# sense for the user to only input in the 'Dvoranski treninzi' tab but Amir
# and I can always check the user's Karton?" … "I would show the tab only to
# members with a gym plan." Members write their gym trainings there, the
# Karton keeps the record (its diary, each row a link into the training's
# page). The tab is _has_gym's: a member with a running plan that books
# termini, staff always, while staff act as a member his plans.

# when a termin's training opens for its member, as staff acting as him read
# it on a later termin's card: "u petak 28.11. u 14:00" (the weekday after
# "u", the accusative)
WEEKDAYS_ACC = ("ponedjeljak", "utorak", "srijedu", "četvrtak", "petak", "subotu", "nedjelju")


def _gym_opens_for(starts_at: datetime) -> str:
    """A later termin's card's line for staff acting as its member (27.11.2026):
    when its training opens for him, its window's start (db.gym_window, the
    booking's cancel deadline): "Članu se otvara u petak 28.11. u 14:00."."""
    at = db.gym_window(starts_at)[0].astimezone(config.TZ)
    return f"Članu se otvara u {WEEKDAYS_ACC[at.weekday()]} {at.day}.{at.month}. u {at:%H:%M}."


def _gym_facts(t) -> str:
    """What a training on the tab's card holds, one muted line: "3 vježbe"
    (none while no exercise is chosen), its saved osvrt's facts after it
    ("3 vježbe · napor 7/10 · Dobro"); "" for none or nothing."""
    if t is None:
        return ""
    return " · ".join(([t.count_text] if t.exercise_items else []) + ([t.osvrt_text] if t.osvrt_text else []))


@app.get("/dvoranski", response_class=HTMLResponse)
def dvoranski_page(request: Request):
    """The tab's page (dvoranski.html): a guest to the login; a member with
    no gym plan the gate, as /treninzi's for one with no online plan ("Dvoranski
    treninzi su dio članarine za dvoranu."); staff always, for their own
    trainings; staff acting as a member (either way in) his page whatever
    his plans (27.11.2026, evening: the actor decides, as POST
    /dvoranski/trening). "Otvoreni treninzi" since that evening is
    everything still being written (the owner, of "Zadnji treninzi", which
    went: "remove it, only list the active trainings"), one card each, in
    this order: his booked termini whose training he may write now
    (db.gym_open_termini, the soonest first: the termin's title, its date
    and time, until when, what it holds, "Upiši trening" while it holds no
    block, else "Nastavi trening", → /dvoranski/termin/<id>); his trainings
    outside a termin with no osvrt saved, held today or yesterday (the
    termin's own rule, "until the end of the day after it"; the newest
    first: "Trening izvan termina" where it has no title of its own, its
    date, what it holds, the same two buttons, → its page); and for staff
    acting as him every later booked termin of his, however far ahead
    (db.gym_later_termini, the soonest first: "Članu se otvara u …" where
    the member's card says until when, "Pripremi trening" while it holds no
    block). None of them: his next booked termin and when its training
    opens, or "Nemaš otvorenih treninga.". "Trening izvan termina", the
    form (POST /dvoranski/trening; a refused date's sentence in it). Staff's
    own page (never while acting, never a member's) has the search for a
    member at its top (_member_find.html, the Karton tab's, POST
    /dvoranski/clan; its refusal at the page's top, ?trazi=1). The way to
    the karton's diary at the page's foot."""
    from urllib.parse import quote

    user = current_user(request)
    if user is None:
        return RedirectResponse(f"/login?next={quote('/dvoranski')}", status_code=303)
    staff_view = _gym_staff(request)
    has_plan = _has_gym(user) or staff_view
    cards, next_text = [], ""
    if has_plan:
        now = datetime.now(config.TZ)
        today = now.date()
        gyms = db.gym_trainings(user.id)
        by_session = {g.session_id: g for g in gyms if g.session_id is not None}
        for s in db.gym_open_termini(user.id, now):
            t = by_session.get(s.id)
            cards.append({
                # _gym_when reads a termin's start as a training's: "srijeda 25.11.2026. · 18:00"
                "kind": "open", "id": s.id, "title": s.title, "when": _gym_when(s), "until": _gym_until(s.starts_at),
                "holds": _gym_facts(t), "started": t is not None and bool(t.blocks)})
        # a training outside a termin (or let go of its termin) still being
        # written: no osvrt, held today or yesterday (gym_trainings: the newest first)
        for g in gyms:
            if g.session_id is None and g.finished_at is None and today - timedelta(days=1) <= g.held_on <= today:
                cards.append({"kind": "outside", "id": g.id, "title": g.title, "when": _gym_when(g),
                              "holds": _gym_facts(g), "started": bool(g.blocks)})
        if staff_view:
            for s in db.gym_later_termini(user.id, now):
                t = by_session.get(s.id)
                cards.append({"kind": "later", "id": s.id, "title": s.title, "when": _gym_when(s),
                              "opens": _gym_opens_for(s.starts_at), "holds": _gym_facts(t),
                              "started": t is not None and bool(t.blocks)})
        if not cards:
            nxt = next((s for s in db.my_upcoming(user.id) if not s.canceled), None)
            if nxt is not None:
                at = nxt.starts_at.astimezone(config.TZ)
                next_text = f"{nxt.title}, {WEEKDAYS_SHORT[at.weekday()]} {at:%-d.%-m.} u {at:%H:%M}"
    # the search for a member (staff's own page: never while acting, when
    # the page is the member's, nor a member's), the Karton tab's own
    find_members = _kao_members() if _can_edit_copy(user) else []
    error = request.query_params.get("error", "")
    find_error = request.query_params.get("trazi") == "1" and bool(error)
    return templates.TemplateResponse(request, "dvoranski.html", _ctx(
        request, user, has_plan=has_plan, cards=cards, next_text=next_text, gym_hours=config.CANCEL_CUTOFF_HOURS,
        error="" if find_error else error, find_error=find_error,
        find_members=find_members, find_rows=_find_rows(find_members),
        first_day=db.FIRST_DAY, today=config.today()))


@app.post("/dvoranski/clan")
def dvoranski_find(request: Request, clan: str = Form("")):
    """The search on staff's own Dvoranski treninzi (27.11.2026, evening; the
    owner: "We need a similar search bar on the top of the 'Dvoranski
    treninzi' tab where Amir can choose to enter that tab of a specific user
    and input a training for him"): the Karton tab's (_find_member), a
    member picked → a tab's view of him, landing on his /dvoranski, "Izađi"
    back here; refused, back here saying so at the page's top (?trazi=1:
    the page's own error is its form's). Staff's (a member 403)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    return _find_member(request, user, clan, "/dvoranski", "/dvoranski?trazi=1&error=")


@app.post("/dvoranski/trening")
def gym_outside(request: Request, day: str = Form("")):
    """"Dodaj trening" on the tab's "Trening izvan termina" (27.11.2026,
    build 2; the Karton's "+ Dodaj trening izvan termina" from 26.11.2026
    until then, POST /karton/trening): a gym training outside a termin on
    that date (db.read_day: not in the future, not before 2020;
    db.add_gym_outside), then its page, where it is written as a termin's
    is. Made by a member with a gym plan, by staff for themselves, and by
    staff acting as a member whatever his plans (rule 1's "at any time": the
    actor decides); anyone else back to the tab, which turns him away,
    nothing made. A date refused: back at the form, its sentence there."""
    from urllib.parse import quote

    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not (_has_gym(user) or _gym_staff(request)):
        return RedirectResponse("/dvoranski", status_code=303)
    try:
        when = db.read_day(day)
    except ValueError as e:
        return RedirectResponse(f"/dvoranski?error={quote(str(e))}#trening-novi", status_code=303)
    return RedirectResponse(f"/dvoranski/trening/{db.add_gym_outside(user.id, when)}", status_code=303)


# ---------- Amir's templates (27.11.2026, build 3 of the dvoranski treninzi) ----------
#
# roadmap/2026-11-27-dvoranski-treninzi-plan.md, build 3; the owner: "In the
# start, there would be two templates. […]"; "Amir will create the third
# template later and give it a name"; "I dont like the fact that I need to go
# to 'Online treninzi' and create a new programme there which is not
# applicable to gym trainings." Staff's two pages under the tab (lit there:
# base.html's every /dvoranski page), the way in staff's own /dvoranski's
# "Predlošci treninga →": the list (dvoranski_predlosci.html) and a
# template's editor, its name and its blocks (dvoranski_predlozak.html). A
# template is its blocks alone, a Stanica's exercise and numbers the
# member's (the owner: "The template's stations are empty"). Every route is
# _require_trainer's: a member 403, a guest to the login, and while staff act
# as a member refused as every staff page. A save or a move comes back at its
# row (?predlozak=<id> on the list, ?blok=<id> on the editor), the name's at
# its card (?naziv=1), an add refused or a block removed in its section
# (?novi=1, ?blokovi=1): the word there ("Spremljeno."), never at the page's
# top; a template deleted, the list's top. Staff's own words (literals).

GYM_TEMPLATES_URL = "/dvoranski/predlosci"


def _tpl_url(template_id: int | None = None, anchor: str = "", **query) -> str:
    """An address of the templates' pages: the list (no id) or a template's
    editor, with its query (a value that is None or empty left out) and its
    anchor."""
    from urllib.parse import urlencode

    path = GYM_TEMPLATES_URL if template_id is None else f"{GYM_TEMPLATES_URL}/{template_id}"
    q = urlencode({k: v for k, v in query.items() if v not in (None, "")})
    return path + (f"?{q}" if q else "") + (f"#{anchor}" if anchor else "")


@app.get("/dvoranski/predlosci", response_class=HTMLResponse)
def gym_templates_page(request: Request):
    """"Predlošci treninga": every template in its order (the member's
    chooser's), its name in 700 a link to its editor, its facts (the
    chooser's words; one with no block "prazan — članovi ga ne vide"),
    Uredi, ↑ / ↓ and ✕ (asks); under them "+ Novi predložak" (not at the
    cap: its sentence in its place); none, "Još nema predložaka."."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    tpls = db.gym_templates(all=True)
    return templates.TemplateResponse(request, "dvoranski_predlosci.html", _ctx(
        request, user, tpls=tpls, can_add=len(tpls) < db.GYM_MAX_TEMPLATES, too_many=db.TOO_MANY_TEMPLATES,
        title_max=db.GYM_TEMPLATE_TITLE_MAX))


@app.post("/dvoranski/predlosci")
def gym_template_new(request: Request, title: str = Form("")):
    """"+ Novi predložak": a template of that name after the last, with no
    block (db.add_gym_template), then its editor. Refused ("Upiši naziv
    predloška.", "Najviše 80 znakova.", "Najviše 12 predložaka."): the
    sentence in the add card (?novi=1#novi), nothing made."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    try:
        template_id = db.add_gym_template(title)
    except ValueError as e:
        return RedirectResponse(_tpl_url(anchor="novi", novi=1, error=str(e)), status_code=303)
    return RedirectResponse(_tpl_url(template_id), status_code=303)


@app.get("/dvoranski/predlosci/{template_id}", response_class=HTMLResponse)
def gym_template_page(request: Request, template_id: int):
    """A template's editor: a crumb back to the list, its name the h1;
    Naziv and Spremi; then "Blokovi", a row per block in its order (a
    Stanica, numbered among the stations as a member's overview numbers
    them, nothing to set; a Kružni set with its three numbers in one small
    form), each with ↑ / ↓ and ✕ (one tap); "+ Stanica" and "+ Kružni set"
    after the last (not at 40: its sentence in their place), the muted line
    on the member's freedom, and "Obriši predložak" at the bottom (asks).
    None such: 404."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    tpl = db.gym_template(template_id)
    if tpl is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "dvoranski_predlozak.html", _ctx(
        request, user, tpl=tpl, can_add=len(tpl.blocks) < db.GYM_MAX_BLOCKS, too_many=db.TOO_MANY_BLOCKS,
        title_max=db.GYM_TEMPLATE_TITLE_MAX, max_rows=db.GYM_MAX_ROWS, rounds=db.GYM_ROUNDS))


@app.post("/dvoranski/predlosci/{template_id}/naziv")
def gym_template_rename(request: Request, template_id: int, title: str = Form("")):
    """The editor's Naziv (db.rename_gym_template): back at its card
    (?naziv=1#naziv), "Spremljeno." or the refusal's sentence there."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    try:
        saved = db.rename_gym_template(template_id, title)
    except ValueError as e:
        return RedirectResponse(_tpl_url(template_id, "naziv", naziv=1, error=str(e)), status_code=303)
    if not saved:
        raise HTTPException(status_code=404)
    return RedirectResponse(_tpl_url(template_id, "naziv", naziv=1, ok="Spremljeno."), status_code=303)


@app.post("/dvoranski/predlosci/{template_id}/pomak")
def gym_template_move(request: Request, template_id: int, smjer: str = Form("")):
    """↑ / ↓ on the list (`smjer` gore / dolje, db.move_gym_template): back
    at its row (#predlozak-<id>), "Spremljeno." there when it moved; at
    either end, for a template gone or a direction that is neither, nothing
    moves and no word."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    moved = db.move_gym_template(template_id, smjer)
    return RedirectResponse(_tpl_url(anchor=f"predlozak-{template_id}", predlozak=template_id,
                                     ok="Spremljeno." if moved else None), status_code=303)


@app.post("/dvoranski/predlosci/{template_id}/obrisi")
def gym_template_delete(request: Request, template_id: int):
    """The list's ✕ and the editor's "Obriši predložak" (each asks first):
    the template and its blocks go (db.delete_gym_template); the trainings
    made from it keep theirs. Back at the list, "Predložak je obrisan." at
    its top (one already gone: the list, no word)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    if not db.delete_gym_template(template_id):
        return RedirectResponse(_tpl_url(), status_code=303)
    return RedirectResponse(_tpl_url(ok="Predložak je obrisan."), status_code=303)


@app.post("/dvoranski/predlosci/{template_id}/blok")
def gym_template_block_add(request: Request, template_id: int, vrsta: str = Form("")):
    """"+ Stanica" (`vrsta` stanica) and "+ Kružni set" (kruzni: 4 rows, 4
    Krug), after the last block (db.add_gym_template_block): back at the
    new row, "Spremljeno." there. Refused at 40 ("Najviše 40 stanica i
    kružnih setova."): in the blocks' section (?blokovi=1#blokovi), nothing
    added. A template gone, or a kind that is none: 404."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    try:
        block_id = db.add_gym_template_block(template_id, vrsta)
    except ValueError as e:
        return RedirectResponse(_tpl_url(template_id, "blokovi", blokovi=1, error=str(e)), status_code=303)
    if block_id is None:
        raise HTTPException(status_code=404)
    return RedirectResponse(_tpl_url(template_id, f"blok-{block_id}", blok=block_id, ok="Spremljeno."),
                            status_code=303)


@app.post("/dvoranski/predlosci/{template_id}/blok/{block_id}")
def gym_template_block_save(request: Request, template_id: int, block_id: int, slots: str = Form(""),
                            rounds: str = Form(""), rest: str = Form("")):
    """A Kružni set's three numbers: Vježbi (`slots`, 1–12), Krugova
    (`rounds`, 1–20), "Pauza nakon kruga (s)" (`rest`, 0–3600, empty for
    none): db.set_gym_template_block. Back at its row (?blok=<id>), its word
    there: "Spremljeno." or "Neispravan broj." (nothing changed). Not this
    template's block, or a Stanica: 404."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    try:
        saved = db.set_gym_template_block(template_id, block_id, _count(slots), _count(rounds), _count(rest))
    except ValueError as e:
        return RedirectResponse(_tpl_url(template_id, f"blok-{block_id}", blok=block_id, error=str(e)),
                                status_code=303)
    if not saved:
        raise HTTPException(status_code=404)
    return RedirectResponse(_tpl_url(template_id, f"blok-{block_id}", blok=block_id, ok="Spremljeno."),
                            status_code=303)


@app.post("/dvoranski/predlosci/{template_id}/blok/{block_id}/pomak")
def gym_template_block_move(request: Request, template_id: int, block_id: int, smjer: str = Form("")):
    """↑ / ↓ on the editor (`smjer` gore / dolje,
    db.move_gym_template_block): back at its row, "Spremljeno." there when
    it moved; at either end, for a block gone or a direction that is
    neither, nothing moves and no word."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    moved = db.move_gym_template_block(template_id, block_id, smjer)
    return RedirectResponse(_tpl_url(template_id, f"blok-{block_id}", blok=block_id,
                                     ok="Spremljeno." if moved else None), status_code=303)


@app.post("/dvoranski/predlosci/{template_id}/blok/{block_id}/obrisi")
def gym_template_block_delete(request: Request, template_id: int, block_id: int):
    """✕ on the editor, one tap (nothing a member wrote is in a template):
    the block goes (db.delete_gym_template_block). Back in the blocks'
    section, its word there ("Stanica je uklonjena." / "Kružni set je
    uklonjen.", the training page's); a block already gone, no word."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    kind = db.delete_gym_template_block(template_id, block_id)
    word = {"stanica": "Stanica je uklonjena.", "kruzni": "Kružni set je uklonjen."}.get(kind)
    return RedirectResponse(_tpl_url(template_id, "blokovi", blokovi=1 if word else None, ok=word), status_code=303)


@app.get("/dvoranski/termin/{session_id}")
def gym_from_termin(request: Request, session_id: int):
    """A termin's training (rule 2): the member's, made the first time it
    is opened (db.gym_training_for: his booking, the termin not canceled,
    the window open for a member; staff acting as him at any time), then
    its page. A refusal: his karton, its sentence at the top. The way in
    from the tab's "Otvoreni treninzi" (27.11.2026), the karton's diary
    rows, the raspored's "Tvoj sljedeći termin", the login's osvrt prompt,
    and a roster's "Kao član →"."""
    from urllib.parse import quote

    user = current_user(request)
    if user is None:
        return RedirectResponse(f"/login?next={quote(request.url.path)}", status_code=303)
    try:
        training_id = db.gym_training_for(user.id, session_id, staff=_gym_staff(request))
    except db.BookingError as e:
        return RedirectResponse(f"/karton?error={quote(str(e))}", status_code=303)
    return RedirectResponse(f"/dvoranski/trening/{training_id}", status_code=303)


@app.get("/dvoranski/trening/{training_id}", response_class=HTMLResponse)
def gym_page(request: Request, training_id: int):
    """A training's page, the member's own (another's 404)."""
    from urllib.parse import quote

    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse(f"/login?next={quote(request.url.path)}", status_code=303)
    return _gym_page(request, user, t)


def _gym_osvrt(request: Request, user, t, error: str | None = None, form: dict | None = None,
               status_code: int = 200):
    """The osvrt's page (karton_trening_osvrt.html): the finish screen's
    clothes, its napor, osjećaj and comment the saved ones (or what a
    refused one posted)."""
    v = form or {"effort": t.effort, "feeling": t.feeling or "", "note": t.note or ""}
    return templates.TemplateResponse(request, "karton_trening_osvrt.html", _ctx(
        request, user, t=t, when=_gym_when(t), feelings=FEELING_LABELS, error=error, v=v), status_code=status_code)


@app.get("/dvoranski/trening/{training_id}/osvrt", response_class=HTMLResponse)
def gym_osvrt_page(request: Request, training_id: int):
    """"Završi trening" (and "Uredi osvrt"): the osvrt. Not writable now:
    the training's page, which says so."""
    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not db.gym_can_write(t, staff=_gym_staff(request)):
        return RedirectResponse(f"/dvoranski/trening/{training_id}", status_code=303)
    return _gym_osvrt(request, user, t)


@app.post("/dvoranski/trening/{training_id}/osvrt")
def gym_osvrt_save(request: Request, training_id: int, effort: str = Form(""), feeling: str = Form(""),
                   note: str = Form("")):
    """The osvrt saved (db.finish_gym_training: napor 1–10, osjećaj, a
    comment), then the karton at the training's diary row, "Trening je
    spremljen."; a refused one the page again, its sentence and what was
    chosen; a training no longer writable its page, saying so."""
    from urllib.parse import quote

    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        saved = db.finish_gym_training(training_id, user.id, _id(effort), feeling or None, note,
                                       staff=_gym_staff(request))
    except ValueError as e:
        return _gym_osvrt(request, user, t, error=str(e), status_code=400,
                          form={"effort": _id(effort), "feeling": feeling, "note": note})
    except db.BookingError as e:
        return _gym_back(training_id, error=str(e))
    if not saved:
        raise HTTPException(status_code=404)
    # back where "← Natrag" leads (Fable's review of build 2, 27.11.2026): the
    # tab for a viewer who has it (staff acting as the member always), a
    # termin's training still open there with its napor; the karton's diary
    # row for one who has not, as build 1's
    if _has_gym(user) or _gym_staff(request):
        return RedirectResponse(f"/dvoranski?ok={quote('Trening je spremljen.')}", status_code=303)
    return RedirectResponse(f"/karton?ok={quote('Trening je spremljen.')}#gt-{training_id}", status_code=303)


@app.post("/dvoranski/trening/{training_id}/predlozak")
def gym_template(request: Request, training_id: int, predlozak: str = Form("")):
    """"Odaberi predložak" (and "Promijeni predložak"): a template's blocks
    in place of the training's while no set is ticked in it
    (db.apply_gym_template), then the page on its first block. Refused
    ("Odaberi predložak s popisa.", "Trening je već započet — predložak se
    više ne može zamijeniti."): its sentence at the chooser (?predlozak=1),
    nothing changed."""
    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        saved = db.apply_gym_template(training_id, user.id, _id(predlozak), staff=_gym_staff(request))
    except (ValueError, db.BookingError) as e:
        return _gym_back(training_id, "predlozak", predlozak=1, error=str(e))
    if not saved:
        raise HTTPException(status_code=404)
    return _gym_back(training_id)


@app.post("/dvoranski/trening/{training_id}/blok")
def gym_block_add(request: Request, training_id: int, vrsta: str = Form("")):
    """"+ Stanica" (`vrsta` stanica) and "+ Kružni set" (kruzni), after the
    last block (db.add_gym_block: at most 40), then the page on it: a
    Stanica's form, a Kružni set's setup. Refused: its sentence at the
    page's top."""
    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        block_id = db.add_gym_block(training_id, user.id, vrsta, staff=_gym_staff(request))
    except (ValueError, db.BookingError) as e:
        return _gym_back(training_id, error=str(e))
    if block_id is None:
        raise HTTPException(status_code=404)
    return _gym_back(training_id, blok=block_id)


@app.post("/dvoranski/trening/{training_id}/blok/{block_id}/obrisi")
def gym_block_delete(request: Request, training_id: int, block_id: int):
    """"Ukloni stanicu" / "Ukloni kružni set" (db.delete_gym_block, its sets
    with it: the page asks first while it holds one), then the page on the
    first block not done, the word at its top."""
    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    b = _gym_block(t, block_id)
    try:
        db.delete_gym_block(block_id, user.id, staff=_gym_staff(request), training_id=training_id)
    except db.BookingError as e:
        return _gym_back(training_id, blok=block_id, error=str(e))
    return _gym_back(training_id, ok="Kružni set je uklonjen." if b.circuit else "Stanica je uklonjena.")


@app.post("/dvoranski/trening/{training_id}/blok/{block_id}/stanica")
def gym_station_save(request: Request, training_id: int, block_id: int, exercise_id: str = Form(""),
                     sets: str = Form(""), reps: str = Form(""), kg: str = Form(""), rest: str = Form(""),
                     seconds: str = Form(""), note: str = Form(""), uredi: str = Form(""),
                     spremi: str = Form("")):
    """A Stanica's exercise and plan in one write ("Kreni"; an empty
    station's "Spremi", `spremi`, since 28.11.2026; "Uredi"'s "Spremi",
    `uredi`): the exercise (needed while it holds none: "Odaberi vježbu s
    popisa."; fixed once a set is ticked), Serije, Ponavljanja, Opterećenje
    (kg), Pauza (s), Vrijeme (s), Komentar (db.set_gym_station). Kreni: the
    station back started, the focus in its first set (?kreni=1); an empty
    station's Spremi: the next block that holds no exercise, "Spremljeno."
    in it (a training written one block after another: Amir preparing a
    member's; with none left, this station); Uredi's Spremi: back at it,
    "Spremljeno.". Refused: its sentence in the card, the form open again
    (?uredi=1 for a started one), nothing changed."""
    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    _gym_block(t, block_id)
    again = 1 if uredi else None
    try:
        saved = db.set_gym_station(block_id, user.id, _id(exercise_id), _count(sets), _count(reps), _count(seconds),
                                   db.read_item_kg(kg), _count(rest), note, staff=_gym_staff(request),
                                   training_id=training_id)
    except (ValueError, db.BookingError) as e:
        return _gym_back(training_id, "glavno", blok=block_id, uredi=again, error=str(e))
    if not saved:
        raise HTTPException(status_code=404)
    if uredi:
        return _gym_back(training_id, "glavno", blok=block_id, ok=GYM_SAVED)
    if spremi:
        return _gym_saved(training_id, user.id, block_id)
    return _gym_back(training_id, "glavno", blok=block_id, kreni=1)


@app.post("/dvoranski/trening/{training_id}/blok/{block_id}/odradeno")
async def gym_station_done(request: Request, training_id: int, block_id: int):
    """A Stanica's tick (rule 4, "a tick saves"): its set table's rows that
    hold a number, `rows` rows of reps_n / kg_n (sec_n: the shape what was
    asked makes, db.set_fields, named by the form's `polja`, a page drawn
    for another shape refused as the player refuses a changed day), saved
    whole (db.save_gym_done). The page's script posts the ticked rows alone
    at each tick, untick or change of a ticked row (fetch, Accept:
    application/json: {"ok", "error", "mark", "done"}, 400 with the
    sentence for a refusal; a ticked row with no number in it is one,
    GYM_EMPTY_ROW, "Upiši broj pa označi seriju.", nothing saved); without
    it the table's "Spremi" posts every row, back at the station."""
    as_json = "application/json" in request.headers.get("accept", "")
    user, t = _gym_of(request, training_id)
    if user is None:
        if as_json:
            return JSONResponse({"ok": False, "error": "Prijavi se ponovno.", "mark": "", "done": False},
                                status_code=401)
        return RedirectResponse("/login", status_code=303)
    b = _gym_block(t, block_id)
    form = await request.form()

    def field(name: str) -> str:
        value = form.get(name)
        return value if isinstance(value, str) else ""

    def answer(error: str | None = None, mark: str = "", done: bool = False):
        if as_json:
            # the script says the sentence as it comes: as its member reads
            # it (the slash forms, 27.11.2026; a redirect's is the page's)
            return JSONResponse({"ok": error is None, "error": grammar.gendered(error or "", user.sex), "mark": mark,
                                 "done": done}, status_code=400 if error else 200)
        return _gym_back(training_id, "glavno", blok=block_id, error=error, ok=None if error else GYM_SAVED)

    it = b.item
    # a Kružni set's rows are saved a Krug at a time (gym_round_save), never
    # by a tick: a page drawn for a Stanica no longer there is refused
    if b.circuit or it is None or field("polja") != ",".join(db.set_fields(it)):
        return answer(DAY_CHANGED)
    fields = db.set_fields(it)
    n = min(max(_id(field("rows")) or 0, 0), 30)
    raw = [{f: field(f"{SET_INPUTS[f]}_{i}") for f in fields} for i in range(1, n + 1)]
    # the script posts the ticked rows alone: one with no number in it is no
    # set (read_sets would drop it, the page still showing its tick), so the
    # whole save is refused and the page unticks it; the no-JS "Spremi"
    # posts every row, the empty ones dropped
    if as_json and any(not any(value.strip() for value in row.values()) for row in raw):
        return answer(GYM_EMPTY_ROW)
    try:
        typed = any(value.strip() for row in raw for value in row.values())
        sets = db.read_sets(raw, fields) if typed else []
        saved = db.save_gym_done(block_id, user.id, sets, staff=_gym_staff(request), training_id=training_id)
    except (ValueError, db.BookingError) as e:
        return answer(str(e))
    if not saved:
        raise HTTPException(status_code=404)
    it.done = json.dumps(sets)                        # the detached copy, for its mark
    return answer(mark=it.mark, done=b.done)


@app.post("/dvoranski/trening/{training_id}/blok/{block_id}/ocjena")
async def gym_block_rate(request: Request, training_id: int, block_id: int):
    """A block's rating, its own small write (db.rate_gym_block: `effort`
    1–10, empty for none): a Stanica's "Koliko je bilo teško?", a Kružni
    set's "Koliko je bio težak ovaj kružni set?". The page's script sends
    it at a tap (fetch, Accept: application/json: {"ok", "error"}); without
    it the form's "Spremi", back at the block."""
    as_json = "application/json" in request.headers.get("accept", "")
    user, t = _gym_of(request, training_id)
    if user is None:
        if as_json:
            return JSONResponse({"ok": False, "error": "Prijavi se ponovno."}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    _gym_block(t, block_id)
    form = await request.form()
    raw = form.get("effort")
    try:
        saved = db.rate_gym_block(block_id, user.id, db.read_effort(raw if isinstance(raw, str) else ""),
                                  staff=_gym_staff(request), training_id=training_id)
        error = None
    except (ValueError, db.BookingError) as e:
        saved, error = True, str(e)
    if not saved:
        raise HTTPException(status_code=404)
    if as_json:
        return JSONResponse({"ok": error is None, "error": grammar.gendered(error or "", user.sex)},
                            status_code=400 if error else 200)
    return _gym_back(training_id, "glavno", blok=block_id, error=error, ok=None if error else GYM_SAVED)


@app.post("/dvoranski/trening/{training_id}/blok/{block_id}/plan")
async def gym_circuit_plan(request: Request, training_id: int, block_id: int):
    """A Kružni set's rows and plan in one write (db.save_gym_circuit): its
    rows, the page's own (`stavke`), each vjezba_<id> (a library exercise,
    or empty: an empty row is let be), reps_<id>, kg_<id>, sec_<id>;
    Krugova (`rounds`) and "Pauza nakon kruga (s)" (`rest`). Then "+
    vježba" (`dodaj`: a row more, db.add_gym_row, at most 12) or a row's ✕
    (`ukloni`, its id: db.delete_gym_row, the page asks first while it
    holds a set; what was typed in that row goes with it, the save keeping
    it as stored), each after the save, so a refused save removes and adds
    nothing; back at the form, after "+ vježba" with the new row's picker
    focused (?red=); else "Kreni" (`kreni`, the setup's): Krug 1 open
    (?krug=1), or with every row empty the setup again, "Upiši bar jednu
    vježbu."; "Uredi"'s Spremi: the set back, "Spremljeno.". Refused: its
    sentence in the card, the form open again (?uredi=1)."""
    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    b = _gym_block(t, block_id)
    form = await request.form()

    def field(name: str) -> str:
        value = form.get(name)
        return value if isinstance(value, str) else ""

    staff = _gym_staff(request)
    drop = _id(field("ukloni"))
    drawn = [x for x in (_id(v) for v in field("stavke").split(",")) if x is not None]
    stored = {it.id: it for it in b.items}

    def row(iid: int) -> dict:
        if iid == drop and iid in stored:            # the row the ✕ takes out: as it is stored
            it = stored[iid]
            return {"exercise_id": it.exercise_id, "reps": it.reps, "kg": it.kg, "seconds": it.seconds}
        return {"exercise_id": _id(field(f"vjezba_{iid}")), "reps": _count(field(f"reps_{iid}")),
                "kg": db.read_item_kg(field(f"kg_{iid}")), "seconds": _count(field(f"sec_{iid}"))}

    try:
        if drop is not None and drop not in drawn:
            raise ValueError(db.GYM_CHANGED)
        rows = {iid: row(iid) for iid in drawn}
        if not db.save_gym_circuit(block_id, user.id, rows, _count(field("rounds")), _count(field("rest")),
                                   staff=staff, training_id=training_id):
            raise HTTPException(status_code=404)
        if drop is not None and not db.delete_gym_row(drop, user.id, staff=staff, training_id=training_id):
            raise ValueError(db.GYM_CHANGED)
        added = None
        if field("dodaj"):
            added = db.add_gym_row(block_id, user.id, staff=staff, training_id=training_id)
    except (ValueError, db.BookingError) as e:
        return _gym_back(training_id, "glavno", blok=block_id, uredi=1, error=str(e))
    if field("dodaj"):
        return _gym_back(training_id, f"red-{added}", blok=block_id, uredi=1, red=added)
    if drop is not None:
        return _gym_back(training_id, "glavno", blok=block_id, uredi=1)
    if field("spremi") and not b.rounds_saved:
        # the setup's "Spremi" (28.11.2026): written, and the next block that
        # holds no exercise opens, as an empty station's
        return _gym_saved(training_id, user.id, block_id)
    if field("kreni") and not b.rounds_saved:
        if all(r["exercise_id"] is None for r in rows.values()):
            # "Kreni" with every row empty (Fable's review, 27.11.2026): a Krug
            # needs an exercise, so the setup stays and says so; what was typed
            # is saved
            return _gym_back(training_id, "glavno", blok=block_id, uredi=1, error=db.NO_ROUND_EXERCISE)
        return _gym_back(training_id, "glavno", blok=block_id, krug=1)
    return _gym_back(training_id, "glavno", blok=block_id, ok=GYM_SAVED)


@app.post("/dvoranski/trening/{training_id}/blok/{block_id}/krug/{n}")
async def gym_round_save(request: Request, training_id: int, block_id: int, n: int):
    """A Krug of a Kružni set ("Krug 2 odrađen"; on a saved one "Spremi
    izmjene"): each row's inputs, reps_<item id>, kg_<item id>,
    sec_<item id> (its db.set_fields; every one empty: not done in this
    Krug) and the rows the page was drawn for (`stavke`), saved whole
    (db.save_gym_round). Back at it (?spremljen=<n>#krug-<b>-<n>: the Krug
    open under its ✓ with "Spremi izmjene", the next one under it), the
    pause bar counting the set's pause after a Krug at load (?odmor=, a
    first save's only: a correction is made during the pause). Refused
    ("Upiši bar jednu vježbu.", "Neispravan broj.", a page drawn for other
    rows, a Krug past its Krug: GYM_CHANGED): back at that Krug, open, its
    sentence in it, nothing saved."""
    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    b = _gym_block(t, block_id)
    form = await request.form()

    def field(name: str) -> str:
        value = form.get(name)
        return value if isinstance(value, str) else ""

    rows = b.round_rows
    drawn = sorted(x for x in (_id(v) for v in field("stavke").split(",")) if x is not None)
    first = n not in b.rounds_saved
    try:
        if not b.circuit or not b.rounds or not 1 <= n <= b.rounds or drawn != sorted(it.id for it in rows):
            raise ValueError(db.GYM_CHANGED)
        raw = {it.id: {f: field(f"{SET_INPUTS[f]}_{it.id}") for f in db.set_fields(it)} for it in rows}
        sets = {it.id: None if all(not v.strip() for v in raw[it.id].values())
                else db.read_sets([raw[it.id]], db.set_fields(it))[0] for it in rows}
        saved = db.save_gym_round(block_id, user.id, n, sets, staff=_gym_staff(request), training_id=training_id)
    except (ValueError, db.BookingError) as e:
        return _gym_back(training_id, f"krug-{block_id}-{n}", blok=block_id, krug=n, error=str(e))
    if not saved:
        raise HTTPException(status_code=404)
    rest = b.rest_seconds if first else None
    return _gym_back(training_id, f"krug-{block_id}-{n}", blok=block_id, spremljen=n, odmor=rest or None)


@app.post("/dvoranski/trening/{training_id}/blok/{block_id}/krugovi")
def gym_rounds_change(request: Request, training_id: int, block_id: int, smjer: str = Form("")):
    """"+ krug" (`smjer` plus) and "− krug" (minus): a Kružni set's Krug one
    more, or its last one less, never a saved one ("Zadnji krug je već
    upisan — ne može se ukloniti.") and never below 1 (db.set_gym_rounds);
    back at it, the word in its card."""
    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    _gym_block(t, block_id)
    try:
        db.set_gym_rounds(block_id, user.id, {"plus": 1, "minus": -1}.get(smjer, 0), staff=_gym_staff(request),
                          training_id=training_id)
    except (ValueError, db.BookingError) as e:
        return _gym_back(training_id, "glavno", blok=block_id, error=str(e))
    return _gym_back(training_id, "glavno", blok=block_id)


@app.post("/dvoranski/trening/{training_id}/isprazni")
def gym_empty(request: Request, training_id: int):
    """"Isprazni trening": every block and its sets go, the training and its
    osvrt stay (db.empty_gym_training); its page offers the templates."""
    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        db.empty_gym_training(training_id, user.id, staff=_gym_staff(request))
    except db.BookingError as e:
        return _gym_back(training_id, error=str(e))
    return _gym_back(training_id, ok="Trening je ispražnjen.")


@app.post("/dvoranski/trening/{training_id}/datum")
def gym_day(request: Request, training_id: int, day: str = Form("")):
    """"promijeni datum", a training outside a termin's (db.read_day's
    rules; db.set_gym_day); a termin's training, or one let go of its
    termin, has no such form: 404."""
    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if t.session_id is not None or not t.outside:
        raise HTTPException(status_code=404)
    try:
        db.set_gym_day(training_id, user.id, db.read_day(day), staff=_gym_staff(request))
    except (ValueError, db.BookingError) as e:
        return _gym_back(training_id, error=str(e))
    return _gym_back(training_id, ok="Datum je spremljen.")


@app.post("/dvoranski/trening/{training_id}/obrisi")
def gym_delete(request: Request, training_id: int):
    """"Obriši trening", a training outside a termin's (or one let go of its
    termin), its blocks and osvrt with it (db.delete_gym_training); a
    termin's goes with its booking: 404 here. Then the tab (the karton for a
    viewer who has none)."""
    user, t = _gym_of(request, training_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if t.session_id is not None:
        raise HTTPException(status_code=404)
    try:
        db.delete_gym_training(training_id, user.id, staff=_gym_staff(request))
    except db.BookingError as e:
        return _gym_back(training_id, error=str(e))
    if _has_gym(user) or _gym_staff(request):         # the tab for a viewer who has it, as the osvrt's save
        return RedirectResponse("/dvoranski?ok=Trening+je+obrisan.", status_code=303)
    return RedirectResponse("/karton?ok=Trening+je+obrisan.#osvrti", status_code=303)


# ---------- treninzi (custom training programmes) ----------

# The exercises' clips (the library, 30.10.2026): what a file may be by its
# extension, the content type it is stored and served with, and the bytes it
# must start with (sniffed, so a file of another kind renamed is refused
# before it is stored). An MP4 or a QuickTime .mov is ISO base media, its
# first box "ftyp" at byte 4; a WebM is EBML, 1A 45 DF A3 at byte 0.
_VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}
_VIDEO_SIGNATURES = {".mp4": (4, b"ftyp"), ".mov": (4, b"ftyp"), ".webm": (0, b"\x1a\x45\xdf\xa3")}
_VIDEO_UNSUPPORTED = "Nepodržan format — dozvoljeno: mp4, mov, webm."


def _save_video(upload: UploadFile | None, prefix: str) -> str | None:
    """Store an uploaded clip, an exercise's or a day's intro video; its new
    file name, the prefix the caller names it by and a random part
    (vjezba-<id>-<hex>.<ext>, dan-<id>-<hex>.<ext>), or None when no file
    came (or an empty one).

    Spooled to a temp file in 1 MB chunks to a size cap, config.VIDEO_MAX_MB:
    a phone video can be huge and must fail cleanly, not fill the disk, and
    the cap trips BEFORE any byte reaches R2. Then its first bytes must be its
    kind's (_VIDEO_SIGNATURES). Raises ValueError with the Croatian sentence
    to show on a refusal. No transcoding (the spec): stored as it comes."""
    if upload is None or not (upload.filename or "").strip():
        return None
    import secrets
    import tempfile

    suffix = Path(upload.filename).suffix.lower()
    if suffix not in _VIDEO_TYPES:
        raise ValueError(_VIDEO_UNSUPPORTED)
    limit = config.VIDEO_MAX_MB * 1024 * 1024
    total, head = 0, b""
    fd, tmp_name = tempfile.mkstemp(suffix=suffix)
    tmp = Path(tmp_name)
    try:
        with open(fd, "wb") as f:
            while chunk := upload.file.read(1 << 20):
                total += len(chunk)
                if total > limit:
                    raise ValueError(f"Video je prevelik — najviše {config.VIDEO_MAX_MB} MB.")
                head += chunk[:max(0, 16 - len(head))]
                f.write(chunk)
        if total == 0:
            return None
        at, magic = _VIDEO_SIGNATURES[suffix]
        if head[at:at + len(magic)] != magic:
            raise ValueError(_VIDEO_UNSUPPORTED)
        name = f"{prefix}-{secrets.token_hex(8)}{suffix}"
        storage.save(name, tmp, _VIDEO_TYPES[suffix])
        return name
    finally:
        tmp.unlink(missing_ok=True)          # a refusal's bytes; a stored file has moved on already


# Where "Nova vježba →" in the day editor comes back to once the exercise
# is made: a path of the treninzi pages, nothing else (no other site, no
# other page of the app, no query).
_NATRAG = re.compile(r"/treninzi/[0-9A-Za-z/_-]*")


def _natrag(path: str | None) -> str | None:
    return path if path and _NATRAG.fullmatch(path) else None


def _id(value: str | None) -> int | None:
    """A posted or queried row id: ASCII digits, nine at most (an integer
    column's), else None. str.isdigit() would let "²" through to int()."""
    return int(value) if value and re.fullmatch(r"[0-9]{1,9}", value) else None


def _ids(values: list[str]) -> set[int]:
    """The ticked similar exercises, as posted (checkbox values): the ids."""
    return {i for i in map(_id, values) if i is not None}


def _program_or_403(request: Request, program_id: int):
    """(user, program) if the requester may SEE this programme, else raise.
    A client sees a programme only through an assignment; the library is
    trainer-only."""
    user = current_user(request)
    if user is None:
        return None, None
    p = db.get_program(program_id)
    if p is None:
        raise HTTPException(status_code=404)
    if not _is_staff(user):                          # staff see every programme (the owner too, 26.11.2026)
        # Paid product first, onboarding second: no active `online` plan means
        # no programme content at all; with a plan, the upitnik must still
        # route the client into a razina before assignments show.
        if not _has_online(user):
            raise HTTPException(status_code=403, detail="Online treninzi su dio zasebne članarine.")
        if db.get_onboarding(user.id) is None:
            raise HTTPException(status_code=403, detail="Prvo ispuni upitnik.")
        if not db.client_can_view(p, user.id):
            raise HTTPException(status_code=403, detail="Ovo nije tvoj trening.")
    return user, p


@app.get("/treninzi", response_class=HTMLResponse)
def treninzi(request: Request):
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/treninzi')}", status_code=303)
    if _is_staff(user):                              # staff's table (the owner's too, whatever his flag)
        rows = db.all_programs()
        goal_order = list(upitnik.GOALS)
        # one section per razina, goals in a fixed order inside each
        groups = [{"label": label,
                   "rows": sorted((r for r in rows if r[0].level == level),
                                  key=lambda r: (goal_order.index(r[0].goal)
                                                 if r[0].goal in upitnik.GOALS else 99,
                                                 r[0].title))}
                  for level, label in upitnik.LEVELS.items()]
        untagged = [r for r in rows if r[0].level not in upitnik.LEVELS]
        # a template's empty slots, said beside its count of exercises
        # (26.11.2026): "0 · 7 praznih mjesta", not "0 prazno!"
        slots = {pid: f"{n} {plural(n, 'prazno mjesto', 'prazna mjesta', 'praznih mjesta')}"
                 for pid, n in db.program_slot_counts().items()}
        # the lead's sentence on dvoranski programmes prints only while one
        # exists (27.11.2026, build 3: no form makes a new one)
        return templates.TemplateResponse(request, "treninzi_admin.html", _ctx(
            request, user, groups=groups, untagged=untagged, slots=slots,
            levels=upitnik.LEVELS, goals=upitnik.GOALS,
            has_gym_programs=any(p.venue == "dvorana" for p, *_ in rows)))
    has_plan = _has_online(user)
    onboarding = db.get_onboarding(user.id) if has_plan else None
    # gates stack: no `online` plan -> only the gate card; with a plan but no
    # upitnik -> only the prompt; then the matched programmes render — the
    # whole online side is automatic, nothing is handed out per client.
    # Since 23.11.2026 every programme of his razina, whatever its type, one
    # group per type that has one, in GOALS' order under its label; one of a
    # type not among them (none can be made: both forms require a type)
    # last, under no label
    programs = db.programs_for_level(onboarding.level) if onboarding else []
    groups = [(key, label, [p for p in programs if p.goal == key]) for key, label in upitnik.GOALS.items()]
    groups = [g for g in groups if g[2]]
    untyped = [p for p in programs if p.goal not in upitnik.GOALS]
    if untyped:
        groups.append(("", "", untyped))
    return templates.TemplateResponse(request, "treninzi.html", _ctx(
        request, user, groups=groups, onboarding=onboarding,
        has_plan=has_plan, levels=upitnik.LEVELS))


@app.post("/treninzi")
def create_program(request: Request, title: str = Form(...), intro: str = Form(""),
                   level: str = Form(...), goal: str = Form(...)):
    """"Novi program": its title, type, razina and intro; then its editor,
    the programme with no day. Every new programme is online since
    27.11.2026 (build 3 of the dvoranski treninzi; the owner: "I dont like
    the fact that I need to go to 'Online treninzi' and create a new
    programme there which is not applicable to gym trainings": a gym
    training starts from Amir's templates, /dvoranski/predlosci): the form
    asks no Vrsta, and a posted `venue` is ignored (Online or Dvoranski from
    24.11.2026 until then)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    title = title.strip()
    if not title:
        return RedirectResponse("/treninzi?error=Naziv+je+obavezan.", status_code=303)
    if level not in upitnik.LEVELS or goal not in upitnik.GOALS:
        return RedirectResponse("/treninzi?error=Odaberi+razinu+i+tip+programa.", status_code=303)
    pid = db.create_program(title, intro.strip() or None, level, goal)
    return RedirectResponse(f"/treninzi/{pid}/uredi", status_code=303)


# ---------- the library of exercises (Amir's, 30.10.2026) ----------
# Declared before /treninzi/{program_id}: that path would take "vjezbe" for a
# programme's id.

# The tags under both exercise searches (23.11.2026: _tagbar.html): a tag at
# least this many exercises carry is a chip; one carried by a single
# exercise is not (on prod those are typos: "hip thurst", "bučice").
TAG_CHIP_MIN = 2


def _tag_chips() -> list[str]:
    """The library's tags that are chips, the most used first, each in its
    most frequent spelling (db.tag_counts)."""
    return [t for t, n in db.tag_counts() if n >= TAG_CHIP_MIN]


@app.get("/treninzi/vjezbe", response_class=HTMLResponse)
def vjezbe(request: Request, q: str = ""):
    """The library: every exercise in the alphabet's order, its tags, whether
    it has a clip and how many programmes hold it. The search filters as it
    is typed since 23.11.2026 (the owner: "I want this to be in real time
    i.e. when I search the dropdown changes"), so every row is on the page,
    `q` or not: each with whether `q` keeps it (models.matches: every word
    in the name or the tags, folded), and the page's script hides the
    others as the box changes. The server marks them `hidden` too: that is
    the page without the script, and what a reload of the address the
    script keeps (?q=…) opens on. Under the search the tags as chips
    (23.11.2026, _tag_chips): without the script each links to its ?q=,
    the one that is the whole of `q` (`tag_on`, folded) pressed."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    q = " ".join(q.split())
    rows = [(e, n, matches(q, e.name, e.tags)) for e, n in db.exercises()]
    tags = _tag_chips()
    tag_on = next((t for t in tags if fold(t) == fold(q)), "") if q else ""
    return templates.TemplateResponse(request, "vjezbe.html", _ctx(
        request, user, rows=rows, q=q, found=sum(1 for *_, hit in rows if hit), total=len(rows),
        tags=tags, tag_on=tag_on))


def _exercise_page(request: Request, user, e, form: dict | None = None, error: str | None = None,
                   natrag: str | None = None, status_code: int = 200):
    """An exercise's form page: a new one (e None) or one of the library. With
    `form`, what was posted and refused (a name taken, say), shown again under
    the error. "Zamjene za ovu vježbu" (since 4.11.2026 a swap has a
    direction): every other exercise to tick, a tick a swap this one -> that
    one, the ticked ones first, each group in the alphabet's order. `reverse`
    is the exercises this one may stand in for (the reverse rows, as
    stored): a ticked row among them is a mutual pair and carries "u oba
    smjera" (an unticked one nothing), and the line under the list names
    them all (Exercise.stands_in_for)."""
    if form is None:
        form = ({"name": e.name, "instructions": e.instructions, "rep_note": e.rep_note, "tags": e.tags,
                 "alternatives": {a.id for a in e.alternatives}} if e is not None else
                {"name": "", "instructions": "", "rep_note": "", "tags": "", "alternatives": set()})
    choices = [x for x, _ in db.exercises() if e is None or x.id != e.id]
    choices.sort(key=lambda x: x.id not in form["alternatives"])      # stable: the alphabet within each
    return templates.TemplateResponse(request, "vjezba.html", _ctx(
        request, user, e=e, v=form, choices=choices, error=error, natrag=natrag,
        reverse={x.id for x in e.stands_in_for} if e is not None else set(),
        programs=db.exercise_programs(e.id) if e is not None else [],
        video_max_mb=config.VIDEO_MAX_MB), status_code=status_code)


@app.get("/treninzi/vjezbe/nova", response_class=HTMLResponse)
def vjezba_nova_page(request: Request, natrag: str = ""):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    return _exercise_page(request, user, None, natrag=_natrag(natrag))


@app.post("/treninzi/vjezbe/nova")
def vjezba_nova(request: Request, name: str = Form(""), instructions: str = Form(""),
                rep_note: str = Form(""), tags: str = Form(""), alternative: list[str] = Form([]),
                natrag: str = Form("")):
    """Make the exercise, then its page (to add the clip), or back where
    "Nova vježba →" came from (`natrag`, a day's editor), the new exercise
    chosen in its picker."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    back, wanted = _natrag(natrag), _ids(alternative)
    try:
        eid = db.create_exercise(name, instructions, rep_note, tags, wanted, user.id)
    except ValueError as err:
        form = {"name": name, "instructions": instructions, "rep_note": rep_note, "tags": tags, "alternatives": wanted}
        return _exercise_page(request, user, None, form=form, error=str(err), natrag=back, status_code=400)
    if back:
        return RedirectResponse(f"{back}?vjezba={eid}&ok={quote('Vježba je spremljena.')}#dodaj", status_code=303)
    return RedirectResponse(f"/treninzi/vjezbe/{eid}?ok={quote('Vježba je spremljena — dodaj joj video.')}",
                            status_code=303)


@app.get("/treninzi/vjezbe/{exercise_id}", response_class=HTMLResponse)
def vjezba_page(request: Request, exercise_id: int):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    e = db.exercise(exercise_id)
    if e is None:
        raise HTTPException(status_code=404)
    return _exercise_page(request, user, e)


@app.post("/treninzi/vjezbe/{exercise_id}")
def vjezba_save(request: Request, exercise_id: int, name: str = Form(""), instructions: str = Form(""),
                rep_note: str = Form(""), tags: str = Form(""), alternative: list[str] = Form([])):
    """The form's one POST: the texts and the exercises a client may swap
    this one for (its own direction) together."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    wanted = _ids(alternative)
    try:
        saved = db.update_exercise(exercise_id, name, instructions, rep_note, tags, wanted, user.id)
    except ValueError as err:
        e = db.exercise(exercise_id)
        if e is None:
            raise HTTPException(status_code=404)
        form = {"name": name, "instructions": instructions, "rep_note": rep_note, "tags": tags, "alternatives": wanted}
        return _exercise_page(request, user, e, form=form, error=str(err), status_code=400)
    if not saved:
        raise HTTPException(status_code=404)
    return RedirectResponse(f"/treninzi/vjezbe/{exercise_id}?ok=Spremljeno.", status_code=303)


@app.post("/treninzi/vjezbe/{exercise_id}/video")
def vjezba_video(request: Request, exercise_id: int, video: UploadFile | None = File(None)):
    """Store a clip and put it on the exercise; the one it had goes from
    storage once the row names the new one. Sync on purpose: FastAPI runs it
    in a thread, so storing 100 MB (to R2 on the box) never holds up the
    event loop."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    back = f"/treninzi/vjezbe/{exercise_id}"
    if db.exercise(exercise_id) is None:
        raise HTTPException(status_code=404)
    try:
        name = _save_video(video, f"vjezba-{exercise_id}")
    except ValueError as err:
        return RedirectResponse(f"{back}?error={quote(str(err))}", status_code=303)
    if name is None:
        return RedirectResponse(f"{back}?error={quote('Odaberi video.')}", status_code=303)
    try:
        old = db.set_exercise_video(exercise_id, name, user.id)
    except LookupError:                          # the exercise deleted while its clip went up
        storage.delete(name)
        raise HTTPException(status_code=404)
    if old:
        storage.delete(old)
    return RedirectResponse(f"{back}?ok={quote('Video je spremljen.')}", status_code=303)


@app.post("/treninzi/vjezbe/{exercise_id}/video/ukloni")
def vjezba_video_ukloni(request: Request, exercise_id: int):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    try:
        old = db.set_exercise_video(exercise_id, None, user.id)
    except LookupError:
        raise HTTPException(status_code=404)
    if old:
        storage.delete(old)
    return RedirectResponse(f"/treninzi/vjezbe/{exercise_id}?ok=Video+je+uklonjen.", status_code=303)


@app.post("/treninzi/vjezbe/{exercise_id}/obrisi")
def vjezba_obrisi(request: Request, exercise_id: int):
    """Delete an exercise, whatever holds it (4.11.2026), then its clip: it
    leaves every training (day) that held it, the trainings stay. Back on
    the library, the flash saying how many trainings it left ("Vježba je
    obrisana i maknuta iz 3 treninga."), or "Vježba je obrisana." when none
    held it (or it was gone already)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    video, days = db.delete_exercise(exercise_id) or (None, 0)
    if video:
        storage.delete(video)
    said = f"Vježba je obrisana i maknuta iz {days} treninga." if days else "Vježba je obrisana."
    return RedirectResponse(f"/treninzi/vjezbe?ok={quote(said)}", status_code=303)


@app.get("/treninzi/{program_id}", response_class=HTMLResponse)
def program_view(request: Request, program_id: int):
    """A programme: its intro, then its days as cards, each a link to its
    page and saying the viewer's state on it (30.10.2026: "odrađen 2×", "u
    tijeku", since 31.10.2026 "nedovršen" for a pass open too long; nothing
    for a day never done; db.day_states, one query)."""
    user, p = _program_or_403(request, program_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "trening_view.html", _ctx(
        request, user, p=p, states=db.day_states(user.id, [d.id for d in p.days])))


def _day_or_404(program_id: int, day_id: int):
    """A day of this programme, its items loaded; 404 when it is gone or is
    another programme's."""
    day = db.get_day(day_id)
    if day is None or day.program_id != program_id:
        raise HTTPException(status_code=404)
    return day


def _day_items(day) -> list:
    """The day's exercises in its display order, its sections in their
    order, each in position order (ProgramDay.by_section). The player walks
    them as steps (_steps: a circuit part round by round). A slot
    (26.11.2026: a dvoranski day's row with no exercise yet) is none of
    them: no step, no mark, not counted (ProgramDay.exercise_items)."""
    return day.exercise_items


@dataclass(frozen=True)
class Step:
    """One screen of the player: an exercise of the day (`item`, a
    ProgramDayItem), or since 25.11.2026 one round of a circuit part (the
    owner's note to Amir: "on označi koje krugove koje je odradio"):
    `round` (1-based), the part's circuit (ProgramDayCircuit) and its
    exercises (`items`, the day's order), `item` None. Until then (since
    24.11.2026) a circuit's step was one exercise of one round."""
    item: object | None = None
    round: int | None = None
    circuit: object | None = None
    items: tuple = ()

    @property
    def item_ids(self) -> list[int]:
        """The exercises on its screen: a normal step's one, a round's every one."""
        return [self.item.id] if self.item is not None else [it.id for it in self.items]


def _steps(day, items: list) -> list[Step]:
    """The player's steps through a day: `items` in the day's display order
    (_day_items), a normal part one step per item, a circuit part
    (ProgramDay.circuit) one step per round, its every exercise on it
    (25.11.2026; round 1, round 2, …). The player's k indexes them,
    1-based: step k is steps[k - 1]. A day with no circuit is its items,
    one step each, as ever."""
    parts: dict[str, list] = {}
    for it in items:                         # in display order: the parts come in SECTIONS' order
        parts.setdefault(it.section, []).append(it)
    steps: list[Step] = []
    for section, rows in parts.items():
        circ = day.circuit(section)
        if circ is None:
            steps += [Step(it) for it in rows]
            continue
        steps += [Step(round=r, circuit=circ, items=tuple(rows)) for r in range(1, circ.rounds + 1)]
    return steps


def _rounds_of(entry) -> set[int]:
    """The rounds a pass's entry (WorkoutLog.done_items') holds a set of: a
    circuit's exercise's, each set carrying its round
    (db.save_circuit_round)."""
    sets = entry.get("sets") if isinstance(entry, dict) and isinstance(entry.get("sets"), list) else []
    return {s["round"] for s in sets if isinstance(s, dict) and type(s.get("round")) is int}


def _saved(step: Step, done: dict) -> bool:
    """Whether the pass (its done_items) saved a step: a normal step when
    its item has an entry, a round when any exercise of it holds a set of
    that round (25.11.2026: an exercise left empty is not done in it)."""
    if step.item is not None:
        return step.item.id in done
    return any(step.round in _rounds_of(done.get(it.id)) for it in step.items)


@dataclass(frozen=True)
class Mark:
    """An exercise's saved mark (_marks): `text` "✓" or "2/3", `label` its
    words for a screen reader ("spremljeno 2 od 3 kruga")."""
    text: str
    label: str

    @property
    def full(self) -> bool:
        return self.text == "✓"


def _marks(day, items: list, done: dict) -> dict[int, Mark]:
    """Each exercise's saved mark while a pass is open, the day page's list
    and the player's: "✓" saved (a circuit's exercise: every round), "2/3"
    a circuit's exercise some of whose rounds are saved (24.11.2026); an
    exercise with nothing saved is not in it."""
    marks = {}
    for it in items:
        if it.id not in done:
            continue
        circ = day.circuit(it.section)
        n = None if circ is None else len({r for r in _rounds_of(done[it.id]) if r <= circ.rounds})
        if circ is None or n >= circ.rounds:
            marks[it.id] = Mark("✓", "spremljeno")
        elif n:
            marks[it.id] = Mark(f"{n}/{circ.rounds}", f"spremljeno {n} od {circ.rounds} "
                                                      + plural(circ.rounds, "kruga", "kruga", "krugova"))
    return marks


def _date_text(d: date) -> str:
    """A pass's day as the history prints it: "12.11.", "12.11.2025." in
    another year."""
    return f"{d.day}.{d.month}." + (f"{d.year}." if d.year != config.today().year else "")


templates.env.globals["pass_date"] = _date_text


def _when_text(d: date) -> str:
    """A day as the day page says it: "danas", "jučer", else its date
    (_date_text). The finish screen's stale sentence too (pass_when)."""
    today = config.today()
    return "danas" if d == today else "jučer" if d == today - timedelta(days=1) else _date_text(d)


templates.env.globals["pass_when"] = _when_text


def _state_line(state: dict, done_n: int, n_items: int, stale: bool) -> str:
    """The viewer's state on a day (db.day_state), in the day page's words:
    a pass in progress first (`stale`, its WorkoutLog.stale as the route
    judged it: one open too long, how much of the day's `n_items` it saved,
    `done_n`, and that it can only be finished or dropped, 31.10.2026; a day
    that holds no exercise now, every exercise the pass saved: "2 vježbe",
    WorkoutLog.done_text, 4.11.2026), then how often and when last, else
    none. The two lines that name no value ("U tijeku — nastavi gdje si
    stao/la.", "Još nije odrađen.") are copy slots since 25.11.2026,
    dan.state.open / .new, which the template prints: "" for those."""
    if state["open"] is not None:
        if stale:
            count = (f"{done_n} od {n_items} {plural(n_items, 'vježbe', 'vježbe', 'vježbi')}" if n_items
                     else state["open"].done_text)
            return (f"Nedovršen trening od {_when_text(state['open'].date)} ({count}) — nastavak nije moguć: "
                    "završi ga ili ga odbaci.")
        return ""
    if state["count"]:
        return f"Odrađen {state['count']}× · zadnji put {_when_text(state['last'])}"
    return ""


@app.get("/treninzi/{program_id}/dan/{day_id}", response_class=HTMLResponse)
def program_day_view(request: Request, program_id: int, day_id: int):
    """A day of a programme, the client's page (the trainer's too): its
    intro and intro video, then the whole list of its exercises in their
    sections, each with its dose, rest and note, its clip opened in place.
    Since 30.10.2026 (stage 3, the player) the viewer's state on it under
    the lead ("Još nije odrađen." / "Odrađen 2× · zadnji put 12.11." / "U
    tijeku — …"), "Kreni" into the player (or "Nastavi", with "Odbaci
    započeti trening", while a pass is open, whose saved exercises the list
    ticks), and at the bottom his last five passes ("Povijest"), each with
    its sets. A pass open too long (31.10.2026, WorkoutLog.stale) says so
    ("Nedovršen trening od jučer (6 od 8 vježbi) — …"), and "Završi trening"
    (its finish screen) stands in Kreni's place, Odbaci beside it. A circuit
    part (24.11.2026, kružni trening) says so under its caption, its rows
    the dose of a round, and while a pass is open a row's mark says its
    rounds (_marks: "✓" every round, "2/3" some)."""
    user, p = _program_or_403(request, program_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    day = _day_or_404(program_id, day_id)
    state = db.day_state(user.id, day_id)
    items, log = _day_items(day), state["open"]
    done = log.done_items if log is not None else {}
    stale = log is not None and log.stale()
    return templates.TemplateResponse(request, "trening_day.html", _ctx(
        request, user, p=p, day=day, state=state, stale=stale,
        state_line=_state_line(state, sum(1 for it in items if it.id in done), len(items), stale),
        marks=_marks(day, items, done), history=db.passes(user.id, day_id, limit=5), order=[it.id for it in items],
        feelings=FEELING_LABELS))


# ---------- the player (30.10.2026, stage 3 of the online treninzi spec) ----------
# The owner: a client does a day exercise by exercise, as on Shape Club's Gym
# Program page, the set log prefilled as Shape does it (reps from the plan,
# kg from the last saved log), the whole list beside it, the swap among the
# similar exercises, the osvrt at the end, and every pass kept. "Kreni" on a
# day opens a pass (db.start_pass), each exercise's screen saves its set log
# (db.save_sets) and may swap it (db.swap_exercise), the finish screen's
# osvrt closes it (db.finish_pass), "Odbaci" drops it (db.drop_pass). Every
# route goes through _program_or_403 and the day check, as the day's page: a
# client reaches only his matched programmes' days; staff may use it too,
# their passes their own (on the days, and since 24.11.2026 on their own
# karton's diary).
# A pass with no activity for PASS_STALE_HOURS (31.10.2026, the owner: no
# hanging training; WorkoutLog.stale) cannot be continued: Kreni / Nastavi,
# an exercise's screen, its save and its swap all lead to the finish screen,
# where it is finished or dropped. Leaving the player or the finish screen
# asks first (_pass_leave.html, the page's script).

def _day_base(program_id: int, day_id: int) -> str:
    return f"/treninzi/{program_id}/dan/{day_id}"


def _next_k(steps: list[Step], log) -> int:
    """Where "Kreni" / "Nastavi" lands: the first step the pass has not
    saved (_saved: a circuit's step its round), the last when it has saved
    them all."""
    done = log.done_items
    return next((n for n, st in enumerate(steps, start=1) if not _saved(st, done)), len(steps))


def _step_rest(step: Step) -> int | None:
    """The rest after a step, in seconds, which rides on its save's redirect
    (?odmor=: the next step's screen counts it down): a normal step's its
    item's rest after it; a round's the circuit's rest after a round, after
    the final round too (the pause before the next part), and nothing else
    (25.11.2026: no pause between a circuit's exercises, so no fallback to
    an exercise's own). None for none or 0."""
    if step.circuit is not None:
        return step.circuit.rest_seconds or None
    return step.item.rest_after_seconds or None


# the bar over the player: one segment per step while the day has at most
# this many, a single track past them (24.11.2026: a circuit multiplies the
# steps, and 60 segments do not fit a phone)
SEGMENTS_MAX = 40


def _kg_value(kg) -> str:
    """A weight as a number input's value: "20", "2.5" (its dot); "" for
    none (0)."""
    return f"{float(kg):g}" if kg else ""


# an item's planned weight in the day editor's Kilaža (kg) input (25.11.2026)
templates.env.filters["kg_value"] = _kg_value


def _set_values(st: dict) -> dict:
    """A saved set as its inputs' values, {"reps", "kg", "sec"}."""
    return {"reps": str(st.get("reps", "")), "kg": _kg_value(st.get("kg")), "sec": str(st.get("seconds", ""))}


def _first_values(it, st: dict | None, load) -> dict:
    """A set's first values in the player, {"reps", "kg", "sec"} as its
    inputs' values, from `st`, the client's set of last time at this place
    as the next time fills it (db.next_load's `next`: adjusted by the
    rating's band, as he did it with none; None when he never logged the
    exercise), and the plan (`it`): the PON. his reps when he rated an
    exercise he did with no weight (load.kind "reps"), else the plan's; the
    SEK. his seconds when he rated a timed one, else the plan's; the KG his
    weight when the set has one, else the plan's kg (25.11.2026), else
    none. With no rating that is the prefill as it was before the rating:
    the plan's reps and seconds, the last weights."""
    rated = load is not None and load.rated and st is not None
    reps = st.get("reps") if rated and load.kind == "reps" and "reps" in st else it.reps
    sec = st.get("seconds") if rated and load.kind == "seconds" and "seconds" in st else it.seconds
    kg = st.get("kg") if st is not None and (st.get("kg") or 0) > 0 else it.kg
    return {"reps": "" if reps is None else str(reps), "kg": _kg_value(kg), "sec": "" if sec is None else str(sec)}


def _at(sets: list, i: int):
    """Set i of a list, the last one's past them; None for none."""
    return (sets[i] if i < len(sets) else sets[-1]) if sets else None


def _log_rows(it, entry: dict | None, load) -> list[dict]:
    """The set log's rows for an item, as the player prints them, each
    {"reps", "kg", "sec": an input's value, "extra": a set past the plan's}
    (the page shows the item's fields of them, db.set_fields: reps and kg,
    seconds, or since 24.11.2026 reps and seconds): the sets this pass
    saved for it, as saved; else a row per planned set (the plan's sets, 1
    when it says none, MAX_SETS at most), each from the client's last time
    as the next time fills it (`load`, db.next_load: set i's, the last
    one's for a set past them) and the plan (_first_values: its reps and
    seconds, and since 25.11.2026 its kg where he has no weight); then one
    empty row more ("dodatna serija"), while there is room."""
    planned = min(it.sets or 1, db.MAX_SETS)
    if entry is not None:
        rows = [_set_values(s) for s in entry.get("sets", []) if isinstance(s, dict)]
    else:
        src = list(load.next) if load is not None else []
        rows = [_first_values(it, _at(src, i), load) for i in range(planned)]
    if len(rows) < db.MAX_SETS:
        rows.append({"reps": "", "kg": "", "sec": ""})
    for n, row in enumerate(rows, start=1):
        row["extra"] = n > planned
    return rows


def _round_blocks(user, log, step: Step, by_id: dict) -> list[dict]:
    """A round's exercises as its screen shows them (25.11.2026), in the
    day's order, each {"it", "ex" (the exercise done: the similar one the
    pass swapped in, else the plan's), "fields" (db.set_fields), "dose" (the
    planned dose of a round, round_dose, and after a rating the word for
    the next time: "10 ponavljanja · malo lakše"), "reps", "kg", "sec" (the
    inputs' first values)}: what this pass saved for it in this round, as
    saved; else _first_values from the set of this round's place last time
    (db.next_loads, this pass's entries of the round's exercises left out:
    the rounds before are this training, not last time) and, for the
    weight, this pass's in the round before when it has one."""
    done, swaps = log.done_items, log.swap_items
    exs = {it.id: by_id.get(swaps.get(it.id)) or by_id.get(it.exercise_id) or it.exercise for it in step.items}
    loads = db.next_loads(user.id, {ex.id for ex in exs.values()}, {(log.id, it.id) for it in step.items})
    blocks = []
    for it in step.items:
        ex, entry = exs[it.id], done.get(it.id)
        load = loads.get(ex.id)
        sets = [s for s in entry.get("sets", []) if isinstance(s, dict)] if isinstance(entry, dict) else []
        mine = next((s for s in sets if s.get("round") == step.round), None)
        if mine is not None:
            values = _set_values(mine)
        else:
            values = _first_values(it, _at(list(load.next) if load else [], step.round - 1), load)
            before = next((s for s in sets if s.get("round") == step.round - 1), None)
            if before is not None and (before.get("kg") or 0) > 0:
                values["kg"] = _kg_value(before["kg"])
        dose = " · ".join(w for w in (it.round_dose, load.short if load else "") if w)
        blocks.append({"it": it, "ex": ex, "fields": db.set_fields(it), "dose": dose, **values})
    return blocks


def _next_line(load) -> str:
    """The card's line under the dose (25.11.2026) when the client's newest
    entry of the exercise has a rating: "Prošli put (23.11.): 10 × 20 kg,
    težina 5 — malo više: 21 kg." ("…, težina 8 — ostaje isto.", "…,
    težina 9 — malo lakše: 18 kg."; reps and seconds in their own words,
    "… — malo više: 11 ponavljanja."); "" with no rating."""
    if load is None or not load.rated:
        return ""
    line = f"Prošli put ({_date_text(load.on)}): {load.done_text}, težina {load.effort} — {load.word}"
    return line + ("." if load.band == "same" else f": {load.next_text}.")


def _player(request: Request, user, p, day, steps: list[Step], k: int, log, error: str | None = None,
            posted=None, effort: int | None = None, status_code: int = 200, odmor: int | None = None):
    """Step k's screen in the pass `log` (_steps: an exercise, or since
    25.11.2026 a round of a circuit part): the bar (one segment per step, a
    single track past SEGMENTS_MAX), then an exercise's clip with ‹ ›, its
    card (the swapped one's name, clip and cues when the pass swapped it,
    "Zamjena za: …" naming the plan's; under the dose the line for the
    next time, _next_line), its set log (_log_rows; `posted`, what a
    refused save sent, kept under `error`), the rating (its entry's, or
    `effort` as posted) and the swap list (the plan's exercise's similar
    exercises, "Vrati …" first when swapped); or a round's card
    ("KRUŽNI DIO", "Krug 2 od 3", the part's name, its exercises with
    their inputs, _round_blocks, or `posted`'s; the round's rating; no
    clip box, no swap); and the day's whole list, each row a link to its
    exercise's first step not saved (its first when all are; a circuit's
    exercise its part's first round not saved), the exercises on screen
    ringed, its mark (_marks). `odmor` is the rest the client takes before
    this step (seconds, from the previous one's save: the form's
    data-odmor, which the script counts down at load); None for none."""
    step = steps[k - 1]
    it, circ = step.item, step.circuit
    items = _day_items(day)
    done, swaps = log.done_items, log.swap_items
    on_screen = [it] if it is not None else list(step.items)
    by_id = db.exercises_by_id({x.exercise_id for x in on_screen} | set(swaps.values()))
    step_saved = [_saved(st, done) for st in steps]
    first, unsaved = {}, {}
    for n, st in enumerate(steps, start=1):
        for item_id in st.item_ids:
            first.setdefault(item_id, n)
            if not step_saved[n - 1]:
                unsaved.setdefault(item_id, n)
    view = dict(
        p=p, day=day, items=items, steps=steps, step=step, k=k, n_steps=len(steps), n_items=len(items), log=log,
        done=done, done_n=sum(1 for x in items if x.id in done), saved=step_saved[k - 1], step_saved=step_saved,
        segments=len(steps) <= SEGMENTS_MAX, track=round(sum(step_saved) * 100 / len(steps), 2),
        links={item_id: unsaved.get(item_id, n) for item_id, n in first.items()}, cur=set(step.item_ids),
        marks=_marks(day, items, done), max_sets=db.MAX_SETS, odmor=odmor,
        swap_names={x.id: by_id[swaps[x.id]].name for x in items if x.id in swaps and swaps[x.id] in by_id},
        error=error or request.query_params.get("error"), base=_day_base(p.id, day.id))
    # the rests as their values ("60 s"; "" for none): the template prints
    # each after its words, copy slots since 25.11.2026 ("Odmor nakon kruga:",
    # "Odmor između serija:", "Odmor nakon vježbe:")
    if it is None:                                   # a round of a circuit part (25.11.2026)
        # its h1 and the page's title the part as the day names it (26.11.2026: "Krug 1", else "Glavni dio A")
        view.update(it=None, blocks=posted if posted is not None else _round_blocks(user, log, step, by_id),
                    effort=effort, title=day.part_label(circ.section), round_rest=circ.rest_text)
    else:
        planned = by_id.get(it.exercise_id) or it.exercise
        swapped = by_id.get(swaps[it.id]) if it.id in swaps else None
        ex = swapped or planned
        entry = done.get(it.id)
        load = db.next_load(user.id, ex.id, {(log.id, it.id)})
        view.update(it=it, ex=ex, planned=planned, swapped=swapped, title=ex.name,
                    alternatives=[a for a in planned.alternatives if swapped is None or a.id != swapped.id],
                    dose=it.dose, rest_between=it.rest_text, rest_after=it.rest_after_text, next_line=_next_line(load),
                    rows=posted if posted is not None else _log_rows(it, entry, load),
                    effort=effort if posted is not None else effort_of(entry), fields=db.set_fields(it))
    return templates.TemplateResponse(request, "trening_player.html", _ctx(request, user, **view),
                                      status_code=status_code)


def _pass_day(request: Request, program_id: int, day_id: int):
    """(user, programme, day, its steps: _steps) for the player's routes,
    or (None, …) for a guest; 403 / 404 as the day's page."""
    user, p = _program_or_403(request, program_id)
    if user is None:
        return None, None, None, None
    day = _day_or_404(program_id, day_id)
    return user, p, day, _steps(day, _day_items(day))


@app.post("/treninzi/{program_id}/dan/{day_id}/kreni")
def pass_start(request: Request, program_id: int, day_id: int):
    """"Kreni" (and "Nastavi": the same form): the viewer's pass through the
    day, a new one or the one in progress, then the first step it has not
    saved (step 1 of a new one; the last when all are; a circuit's round is
    saved when an exercise of it holds a set of it, _saved). A day with no exercise starts
    nothing, and a pass left open on it (its exercises deleted since,
    4.11.2026) goes to its finish screen (_past_the_end); a pass in progress
    that is stale (open too long) is not continued: its finish screen."""
    user, p, day, steps = _pass_day(request, program_id, day_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    base = _day_base(program_id, day_id)
    if not steps:
        if db.open_pass(user.id, day_id) is not None:
            return _past_the_end(base, steps)
        return RedirectResponse(base, status_code=303)
    log = db.start_pass(user.id, p, day)
    if log.stale():
        return RedirectResponse(f"{base}/kraj", status_code=303)
    return RedirectResponse(f"{base}/vjezba/{_next_k(steps, log)}", status_code=303)


# a save whose page was drawn for another list (its hidden item is not
# exercise k's: an exercise deleted from the day, or moved, since)
DAY_CHANGED = "Trening se u međuvremenu promijenio — provjeri vježbu i spremi ponovno."
# a set log's field (db.SET_SHAPES) -> its inputs' name on the page, n the row: reps_n, kg_n, sec_n
SET_INPUTS = {"reps": "reps", "kg": "kg", "seconds": "sec"}


def _past_the_end(base: str, steps: list) -> RedirectResponse:
    """Where a k past the day's count of steps goes, with a pass in progress
    (4.11.2026: an exercise deleted from the library leaves the day while a
    client is on its player, his page still counting the old list; since
    24.11.2026 a circuit switched off or given fewer rounds does the same):
    the day's last step, or the finish screen when none is left."""
    return RedirectResponse(f"{base}/vjezba/{len(steps)}" if steps else f"{base}/kraj", status_code=303)


@app.get("/treninzi/{program_id}/dan/{day_id}/vjezba/{k}", response_class=HTMLResponse)
def pass_exercise(request: Request, program_id: int, day_id: int, k: int, odmor: str = ""):
    """Step k of the day (1-based, its display order: _steps, an exercise,
    in a circuit part one round of it) in the viewer's pass in progress; k
    below 1 is 404, and without a pass in progress the day's page (where
    "Kreni" is), with a stale one (open too long) its finish screen. A k
    past the day's count of steps goes to its last step, or to the finish
    screen when it has none left (_past_the_end). `odmor` (the previous
    step's save: its rest after it, in seconds) starts the rest bar at
    load: an int 1–3600, anything else is ignored."""
    user, p, day, steps = _pass_day(request, program_id, day_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if k < 1:
        raise HTTPException(status_code=404)
    base = _day_base(program_id, day_id)
    log = db.open_pass(user.id, day_id)
    if log is None:
        return RedirectResponse(base, status_code=303)
    if log.stale():
        return RedirectResponse(f"{base}/kraj", status_code=303)
    if k > len(steps):
        return _past_the_end(base, steps)
    rest = _id(odmor)
    return _player(request, user, p, day, steps, k, log, odmor=rest if rest is not None and 1 <= rest <= 3600 else None)


@app.post("/treninzi/{program_id}/dan/{day_id}/vjezba/{k}")
async def pass_save(request: Request, program_id: int, day_id: int, k: int):
    """Exercise k's "Spremi": its set log, `rows` rows of reps_n and kg_n (a
    timed exercise's sec_n; since 24.11.2026 one that asks reps and seconds
    reps_n and sec_n: the item's db.set_fields), read by db.read_sets, and
    since 25.11.2026 its rating (`effort`, 1–10 or none: db.read_effort),
    saved into the pass (db.save_sets: the exercise done, the swapped one
    when swapped); then the next exercise, or the finish screen after the
    last. When the day's item (the plan's, swapped or not) has a rest after
    it, the next exercise comes with it (?odmor=<seconds>: its screen counts it down);
    the finish screen never does. A refusal comes back as the screen, its
    sentence under the name and what was typed kept. A stale pass (open too
    long) saves nothing: its finish screen. k below 1 is 404; a k past the
    day's count saves nothing either: the day's last exercise, or the
    finish screen when it has none left (_past_the_end). The form names its
    item (`item`, 4.11.2026): one that is not exercise k's now, or none, is
    refused as a bad number is (DAY_CHANGED), nothing saved: the page was
    drawn before the day changed, and its sets are not this exercise's (a
    `round` posted to it too: a round's page).
    A circuit's round (25.11.2026: one screen per round, its one button
    "Krug 2 odrađen") posts each exercise's inputs, reps_<item id>,
    kg_<item id>, sec_<item id> (its db.set_fields), the round's rating,
    and names its part (`part`, the section's key) and its `round`: either
    not step k's now is refused as a changed day is. An exercise with every
    input empty is not done in the round; the round is saved into the pass
    whole (db.save_circuit_round), "Upiši bar jednu vježbu." when nothing
    is done, and the next step comes with the circuit's rest after a round
    (_step_rest)."""
    user, p, day, steps = _pass_day(request, program_id, day_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if k < 1:
        raise HTTPException(status_code=404)
    base = _day_base(program_id, day_id)
    log = db.open_pass(user.id, day_id)
    if log is None:
        return RedirectResponse(base, status_code=303)
    if log.stale():
        return RedirectResponse(f"{base}/kraj", status_code=303)
    if k > len(steps):
        return _past_the_end(base, steps)
    form = await request.form()

    def field(name: str) -> str:
        value = form.get(name)
        return value if isinstance(value, str) else ""

    step = steps[k - 1]
    rated = _id(field("effort"))                     # a refused screen keeps the rating chosen, when it is one
    rated = rated if rated is not None and 1 <= rated <= 10 else None
    if step.item is None:
        return _round_save(request, user, p, day, steps, k, log, field, rated)
    it = step.item
    fields = db.set_fields(it)
    n = min(max(_id(field("rows")) or 1, 1), 30)
    raw = [{f: field(f"{SET_INPUTS[f]}_{i}") for f in fields} for i in range(1, n + 1)]

    def refused(sentence: str):
        # the screen again, what was typed back in its inputs: a weight with
        # a comma as a number input's value takes a dot, or the browser
        # would empty it
        planned = min(it.sets or 1, db.MAX_SETS)
        kept = [{"reps": r.get("reps", ""), "kg": r.get("kg", "").replace(",", "."), "sec": r.get("seconds", ""),
                 "extra": i > planned} for i, r in enumerate(raw, start=1)]
        return _player(request, user, p, day, steps, k, log, error=sentence, posted=kept, effort=rated,
                       status_code=400)

    if field("item") != str(it.id) or field("round") or field("part"):
        return refused(DAY_CHANGED)
    swaps = log.swap_items
    exercise = (db.exercises_by_id([swaps[it.id]]).get(swaps[it.id]) if it.id in swaps else None) or it.exercise
    try:
        sets = db.read_sets(raw, fields)
        saved = db.save_sets(log.id, user.id, it, sets, exercise, effort=db.read_effort(field("effort")))
    except ValueError as err:
        return refused(str(err))
    if not saved:
        return RedirectResponse(base, status_code=303)
    return _after_save(base, steps, k)


def _after_save(base: str, steps: list[Step], k: int) -> RedirectResponse:
    """Where a saved step goes: the next one, with the rest after this one
    (_step_rest, ?odmor=), or the finish screen after the last (never with
    a rest)."""
    if k == len(steps):
        return RedirectResponse(f"{base}/kraj", status_code=303)
    rest = _step_rest(steps[k - 1])
    return RedirectResponse(f"{base}/vjezba/{k + 1}" + (f"?odmor={rest}" if rest else ""), status_code=303)


def _round_save(request: Request, user, p, day, steps: list[Step], k: int, log, field, rated: int | None):
    """pass_save for a circuit's round (25.11.2026): each exercise of the
    part (as the day holds them now) read from its inputs, `field` the
    form's (reps_<item id>, kg_<item id>, sec_<item id>, its db.set_fields;
    every one empty: not done in this round), the rating (`effort`), saved
    whole (db.save_circuit_round). A `part` or a `round` that is not step
    k's now is refused as a changed day is (DAY_CHANGED); a refusal is the
    round's screen again, 400, its sentence, what was typed kept (`rated`,
    the rating chosen)."""
    step = steps[k - 1]
    base = _day_base(p.id, day.id)
    raw = {it.id: {f: field(f"{SET_INPUTS[f]}_{it.id}") for f in db.set_fields(it)} for it in step.items}

    def refused(sentence: str):
        # the round's screen again, each exercise's inputs as typed (a
        # weight's comma a dot, a number input's value)
        blocks = _round_blocks(user, log, step, db.exercises_by_id(
            {it.exercise_id for it in step.items} | set(log.swap_items.values())))
        for b in blocks:
            typed = raw[b["it"].id]
            b.update(reps=typed.get("reps", ""), kg=typed.get("kg", "").replace(",", "."), sec=typed.get("seconds", ""))
        return _player(request, user, p, day, steps, k, log, error=sentence, posted=blocks, effort=rated,
                       status_code=400)

    if field("part") != step.circuit.section or field("round") != str(step.round):
        return refused(DAY_CHANGED)
    try:
        sets = {it.id: None if all(not v.strip() for v in raw[it.id].values())
                else db.read_sets([raw[it.id]], db.set_fields(it))[0] for it in step.items}
        saved = db.save_circuit_round(log.id, user.id, step.items, step.round, sets,
                                      effort=db.read_effort(field("effort")))
    except ValueError as err:
        return refused(str(err))
    if not saved:
        return RedirectResponse(base, status_code=303)
    return _after_save(base, steps, k)


@app.post("/treninzi/{program_id}/dan/{day_id}/vjezba/{k}/zamjena")
def pass_swap(request: Request, program_id: int, day_id: int, k: int, exercise_id: str = Form(""),
              vrati: str = Form("")):
    """"⇄" in the swap list: a similar exercise in place of exercise k for
    this pass (`exercise_id`), or the plan's back (`vrati`); back on its
    screen, a refusal's sentence with it. A stale pass (open too long)
    swaps nothing: its finish screen. k below 1 is 404; a k past the day's
    count swaps nothing: the day's last exercise, or the finish screen when
    it has none left (_past_the_end, 4.11.2026). A swap is a normal step's:
    a circuit's round (25.11.2026) offers none, and one posted to it swaps
    nothing, back on its screen."""
    user, p, day, steps = _pass_day(request, program_id, day_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if k < 1:
        raise HTTPException(status_code=404)
    from urllib.parse import quote
    base = _day_base(program_id, day_id)
    log = db.open_pass(user.id, day_id)
    if log is None:
        return RedirectResponse(base, status_code=303)
    if log.stale():
        return RedirectResponse(f"{base}/kraj", status_code=303)
    if k > len(steps):
        return _past_the_end(base, steps)
    back = f"{base}/vjezba/{k}"
    if steps[k - 1].item is None:
        return RedirectResponse(back, status_code=303)
    try:
        db.swap_exercise(log.id, user.id, steps[k - 1].item, None if vrati else _id(exercise_id) or -1)
    except ValueError as err:
        return RedirectResponse(f"{back}?error={quote(str(err))}", status_code=303)
    return RedirectResponse(back, status_code=303)


def _finish_page(request: Request, user, p, day, log, error: str | None = None, form: dict | None = None,
                 status_code: int = 200):
    """The finish screen: the day, how many of its exercises the pass saved
    and how long it has run (WorkoutLog.active_seconds: a stale pass's to
    its last save), then the osvrt (`form`, what a refused one sent, kept
    under `error`). A stale pass (`stale`, open too long) says it was not
    finished and cannot be continued, with no way back to the exercises.
    The count is by exercise (one counts once it has any entry, a circuit's
    after one round too); "Natrag na vježbe" leads to the last step."""
    items = _day_items(day)
    done = log.done_items
    now = datetime.now(config.TZ)
    return templates.TemplateResponse(request, "trening_kraj.html", _ctx(
        request, user, p=p, day=day, log=log, n_items=len(items), done_n=sum(1 for x in items if x.id in done),
        n_steps=len(_steps(day, items)), elapsed=duration_text(log.active_seconds(now)), stale=log.stale(now),
        feelings=FEELING_LABELS, v=form or {"effort": None, "feeling": "", "note": ""}, error=error,
        base=_day_base(p.id, day.id)), status_code=status_code)


@app.get("/treninzi/{program_id}/dan/{day_id}/kraj", response_class=HTMLResponse)
def pass_end_page(request: Request, program_id: int, day_id: int):
    """The finish screen of the viewer's pass in progress (a stale one's
    too: where it is finished or dropped); without one, the day's page."""
    user, p, day, steps = _pass_day(request, program_id, day_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    log = db.open_pass(user.id, day_id)
    if log is None:
        return RedirectResponse(_day_base(program_id, day_id), status_code=303)
    return _finish_page(request, user, p, day, log)


@app.post("/treninzi/{program_id}/dan/{day_id}/kraj")
def pass_finish(request: Request, program_id: int, day_id: int, effort: str = Form(""), feeling: str = Form(""),
                note: str = Form("")):
    """"Spremi trening": the osvrt (napor 1–10, osjećaj or none, a comment)
    finishes the pass (db.finish_pass: its length the server's clock), then
    the day's page saying so. A refused osvrt ("Neispravan osvrt.") comes
    back as the finish screen, what was chosen kept."""
    user, p, day, steps = _pass_day(request, program_id, day_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    from urllib.parse import quote
    base = _day_base(program_id, day_id)
    log = db.open_pass(user.id, day_id)
    if log is None:
        return RedirectResponse(base, status_code=303)
    try:
        db.finish_pass(log.id, user.id, _id(effort), feeling or None, note)
    except ValueError as err:
        kept = {"effort": _id(effort), "feeling": feeling, "note": note}
        return _finish_page(request, user, p, day, log, error=str(err), form=kept, status_code=400)
    return RedirectResponse(f"{base}?ok={quote('Trening je spremljen.')}", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/odustani")
def pass_drop(request: Request, program_id: int, day_id: int):
    """"Odbaci": the viewer's pass in progress through the day is deleted,
    the sets it saved with it (a finished pass is never deleted here); back
    on the day's page."""
    user, p, day, steps = _pass_day(request, program_id, day_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    from urllib.parse import quote
    base = _day_base(program_id, day_id)
    log = db.open_pass(user.id, day_id)
    if log is None or not db.drop_pass(log.id, user.id):
        return RedirectResponse(base, status_code=303)
    return RedirectResponse(f"{base}?ok={quote('Započeti trening je odbačen.')}", status_code=303)


@app.get("/treninzi/{program_id}/uredi", response_class=HTMLResponse)
def program_edit_page(request: Request, program_id: int):
    """The programme's editor: its form, then its days (each opens the day
    editor, moves with ↑ / ↓ or goes with ✕) and "+ Dodaj trening"."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    p = db.get_program(program_id)
    if p is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "trening_edit.html", _ctx(
        request, user, p=p, levels=upitnik.LEVELS, goals=upitnik.GOALS))


@app.post("/treninzi/{program_id}/edit")
def program_edit(request: Request, program_id: int, title: str = Form(...),
                 intro: str = Form(""), level: str = Form(...), goal: str = Form(...)):
    """"Uredi program"'s form: its type, razina, title and intro. Its Vrsta
    is the stored one since 27.11.2026 (build 3 of the dvoranski treninzi:
    the form asks none, and a posted `venue` is ignored): a dvoranski
    programme stays one, its days' empty slots as they were (db.
    update_program, venue None)."""
    from urllib.parse import quote

    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    if level not in upitnik.LEVELS or goal not in upitnik.GOALS:
        return RedirectResponse(f"/treninzi/{program_id}/uredi?error=Odaberi+razinu+i+tip+programa.",
                                status_code=303)
    try:
        db.update_program(program_id, title.strip() or "Program", intro.strip() or None,
                          level, goal)
    except ValueError as err:
        return RedirectResponse(f"/treninzi/{program_id}/uredi?error={quote(str(err))}", status_code=303)
    return RedirectResponse(f"/treninzi/{program_id}/uredi?ok=Spremljeno.", status_code=303)


@app.post("/treninzi/{program_id}/delete")
def program_delete(request: Request, program_id: int):
    """The programme, its days and their items go, then the days' intro
    videos' files; the exercises and their clips stay in the library."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    for name in db.delete_program(program_id) or ():
        storage.delete(name)
    return RedirectResponse("/treninzi?ok=Program+je+obrisan.", status_code=303)


# ---------- a programme's days (30.10.2026, stage 2 of the online treninzi spec) ----------
# Amir's: each route through _require_trainer; a day that is not the
# programme's, and an item that is not the day's, is 404.

def _program_day(program_id: int, day_id: int):
    """(programme, day) for the editors, both loaded; 404 when either is gone
    or the day is another programme's."""
    p = db.get_program(program_id)
    day = db.get_day(day_id)
    if p is None or day is None or day.program_id != program_id:
        raise HTTPException(status_code=404)
    return p, day


def _day_item(program_id: int, day_id: int, item_id: int):
    """An item of this programme's day, or 404."""
    it = db.get_day_item(item_id)
    if it is None or it.day_id != day_id or it.day.program_id != program_id:
        raise HTTPException(status_code=404)
    return it


def _count(value: str | None) -> int | None:
    """A posted number of the day editor's row: "" (or spaces) is none;
    ASCII digits, nine at most, a number; anything else ValueError with
    db.BAD_NUMBER, the row's sentence."""
    value = (value or "").strip()
    if not value:
        return None
    if not re.fullmatch(r"[0-9]{1,9}", value):
        raise ValueError(db.BAD_NUMBER)
    return int(value)


@app.post("/treninzi/{program_id}/dani")
def day_add(request: Request, program_id: int):
    """"+ Dodaj trening": a day after the last, then its editor."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    day_id = db.add_day(program_id)
    if day_id is None:
        raise HTTPException(status_code=404)
    return RedirectResponse(f"/treninzi/{program_id}/dan/{day_id}/uredi", status_code=303)


@app.get("/treninzi/{program_id}/dan/{day_id}/uredi", response_class=HTMLResponse)
def day_edit_page(request: Request, program_id: int, day_id: int, vjezba: str = "", dodaj: str = ""):
    """A day's editor: its title, weekday and intro, its intro video, then
    its exercises per section, each with its own form (since 24.11.2026 each
    section's "Kružno" too: day_circuit_save; since 25.11.2026 each ends
    with "+ Dodaj vježbu u ovaj dio", ?dodaj=<key>#dodaj), and the add
    card: the picker, which offers the whole library, the exercise `vjezba`
    chosen (one just made through "Nova vježba →", or the one a refused
    add named), the library's tags as chips under it (23.11.2026,
    _tag_chips), its Dio the part `dodaj` names (Glavni dio A without one)
    and the picker focused then, and the numbers (25.11.2026). The add's
    word (?ok= / ?error= with ?dodaj=) stands in that card. Since
    26.11.2026 each part's "Preimenuj" (day_part_name_save) beside its
    "Kružno", every part named as the day names it (ProgramDay.part_label),
    and on a dvoranski programme's day the slots: the add card's "Dodaj
    prazno mjesto" (day_slot_add) and a slot's row with "Popuni vježbom"
    (day_slot_fill)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    p, day = _program_day(program_id, day_id)
    return templates.TemplateResponse(request, "trening_day_edit.html", _ctx(
        request, user, p=p, day=day, choices=[e for e, _ in db.exercises()], chosen=_id(vjezba),
        add_dio=dodaj if dodaj in SECTIONS else None, tags=_tag_chips(), video_max_mb=config.VIDEO_MAX_MB))


@app.post("/treninzi/{program_id}/dan/{day_id}")
def day_save(request: Request, program_id: int, day_id: int, title: str = Form(""), weekday: str = Form(""),
             intro: str = Form("")):
    """The day's form: title, suggested weekday ("" none, "0"–"6") and
    intro."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    _program_day(program_id, day_id)
    back = f"/treninzi/{program_id}/dan/{day_id}/uredi"
    try:
        if weekday not in ("", "0", "1", "2", "3", "4", "5", "6"):
            raise ValueError("Odaberi dan u tjednu.")
        saved = db.update_day(day_id, title, int(weekday) if weekday else None, intro)
    except ValueError as err:
        return RedirectResponse(f"{back}?error={quote(str(err))}", status_code=303)
    if not saved:
        raise HTTPException(status_code=404)
    return RedirectResponse(f"{back}?ok=Spremljeno.", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/video")
def day_video(request: Request, program_id: int, day_id: int, video: UploadFile | None = File(None)):
    """The day's intro video, as an exercise's clip: stored, put on the day,
    the one it had deleted once the row names the new one."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    _program_day(program_id, day_id)
    back = f"/treninzi/{program_id}/dan/{day_id}/uredi"
    try:
        name = _save_video(video, f"dan-{day_id}")
    except ValueError as err:
        return RedirectResponse(f"{back}?error={quote(str(err))}", status_code=303)
    if name is None:
        return RedirectResponse(f"{back}?error={quote('Odaberi video.')}", status_code=303)
    try:
        old = db.set_day_video(day_id, name)
    except LookupError:                          # the day deleted while its video went up
        storage.delete(name)
        raise HTTPException(status_code=404)
    if old:
        storage.delete(old)
    return RedirectResponse(f"{back}?ok={quote('Video je spremljen.')}", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/video/ukloni")
def day_video_ukloni(request: Request, program_id: int, day_id: int):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    _program_day(program_id, day_id)
    try:
        old = db.set_day_video(day_id, None)
    except LookupError:
        raise HTTPException(status_code=404)
    if old:
        storage.delete(old)
    return RedirectResponse(f"/treninzi/{program_id}/dan/{day_id}/uredi?ok=Video+je+uklonjen.", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/pomak")
def day_move(request: Request, program_id: int, day_id: int, smjer: str = Form("")):
    """↑ / ↓ in the programme's editor: the day trades places (and numbers)
    with its neighbour; back at its row."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    _program_day(program_id, day_id)
    db.move_day(day_id, smjer)
    return RedirectResponse(f"/treninzi/{program_id}/uredi#dan-{day_id}", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/obrisi")
def day_delete(request: Request, program_id: int, day_id: int):
    """The day and its items go, then its intro video's file; the later days
    move up. Its exercises stay in the library."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    _program_day(program_id, day_id)
    video = db.delete_day(day_id)
    if video:
        storage.delete(video)
    return RedirectResponse(f"/treninzi/{program_id}/uredi?ok=Trening+je+obrisan.", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/stavke")
def day_item_add(request: Request, program_id: int, day_id: int, exercise_id: str = Form(""),
                 section: str = Form("trening"), sets: str = Form(""), reps: str = Form(""),
                 seconds: str = Form(""), kg: str = Form("")):
    """"Dodaj vježbu": an exercise of the library, last in the chosen
    section, and since 25.11.2026 what the day asks of it at once (Serije,
    Ponavljanja, Sekunde, Kilaža (kg), each optional: db.add_day_item, a
    refused number adding nothing). Back at the add card (?dodaj=<the
    part>#dodaj), its Dio as it was and its picker focused, the card saying
    "Dodano u Glavni dio A: Sklekovi.", so several go in one after another;
    a refusal there too, the exercise kept chosen (?vjezba=); a section
    that is none at the top, as before."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    _, day = _program_day(program_id, day_id)
    back = f"/treninzi/{program_id}/dan/{day_id}/uredi"
    chosen = _id(exercise_id)
    if section not in SECTIONS:                      # no part to come back to: the top, as before
        return RedirectResponse(f"{back}?error=Odaberi+vje%C5%BEbu+iz+baze.", status_code=303)
    card = f"{back}?dodaj={section}"
    try:
        numbers = {"sets": _count(sets), "reps": _count(reps), "seconds": _count(seconds), "kg": db.read_item_kg(kg)}
        item_id = db.add_day_item(day_id, chosen, section, **numbers) if chosen is not None else None
    except ValueError as err:                        # a number refused: nothing added, the exercise kept chosen
        keep = f"&vjezba={chosen}" if chosen is not None else ""
        return RedirectResponse(f"{card}&error={quote(str(err))}{keep}#dodaj", status_code=303)
    if item_id is None:
        return RedirectResponse(f"{card}&error=Odaberi+vje%C5%BEbu+iz+baze.#dodaj", status_code=303)
    # the part as the day names it (26.11.2026: "Dodano u Krug 1: Sklekovi.")
    said = f"Dodano u {day.part_label(section)}: {db.get_day_item(item_id).exercise.name}."
    return RedirectResponse(f"{card}&ok={quote(said)}#dodaj", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/mjesto")
def day_slot_add(request: Request, program_id: int, day_id: int, section: str = Form("trening"),
                 hint: str = Form(""), sets: str = Form(""), reps: str = Form(""), seconds: str = Form(""),
                 kg: str = Form("")):
    """"Dodaj prazno mjesto" (26.11.2026, a dvoranski programme's day: the
    add card's second way, its own button posting the card's Dio and
    numbers here, with "Natuknica"): a slot last in the chosen section, no
    exercise yet, its hint and numbers (db.add_day_slot). Back at the add
    card as after an exercise (?dodaj=<the part>#dodaj), "Dodano u Krug 1:
    prazno mjesto."; a refusal there too (a number, "Neispravan broj."; an
    online programme's day, "Prazna mjesta idu samo u dvoranske
    programe."), nothing added; a section that is none at the top."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    _, day = _program_day(program_id, day_id)
    back = f"/treninzi/{program_id}/dan/{day_id}/uredi"
    if section not in SECTIONS:
        return RedirectResponse(f"{back}?error={quote(db.NO_SECTION)}", status_code=303)
    card = f"{back}?dodaj={section}"
    try:
        numbers = {"sets": _count(sets), "reps": _count(reps), "seconds": _count(seconds), "kg": db.read_item_kg(kg)}
        item_id = db.add_day_slot(day_id, section, hint, **numbers)
    except ValueError as err:
        return RedirectResponse(f"{card}&error={quote(str(err))}#dodaj", status_code=303)
    if item_id is None:                              # the day deleted meanwhile
        raise HTTPException(status_code=404)
    said = f"Dodano u {day.part_label(section)}: prazno mjesto."
    return RedirectResponse(f"{card}&ok={quote(said)}#dodaj", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/stavke/{item_id}")
def day_item_save(request: Request, program_id: int, day_id: int, item_id: int, section: str = Form("trening"),
                  sets: str = Form(""), reps: str = Form(""), seconds: str = Form(""), rest: str = Form(""),
                  rest_after: str = Form(""), note: str = Form(""), circuit: str = Form(""), kg: str = Form(""),
                  hint: str | None = Form(None)):
    """A row's form: its section, sets, reps and seconds (either or both
    since 24.11.2026), its planned weight (Kilaža (kg), 25.11.2026), rest
    (between sets), rest after it (before the next exercise) and note; an
    empty number is none. Back at the row, which carries the word
    ("Spremljeno." or the sentence of a refusal): `stavka` names it, so the
    page prints the alert in that row, not at its top, out of view on a
    phone scrolled to the row. A circuit part's row form (kružni trening)
    asks no sets, no rest between sets (24.11.2026) and no rest after it
    (25.11.2026: no pause between a circuit's exercises), which do not
    apply there, and says so (`circuit`): the item keeps the ones it has
    stored (db.KEEP), wherever its Dio takes it. A slot's row form
    (26.11.2026) posts its "Natuknica" too (`hint`); an exercise's posts
    none, and its row keeps the one it has."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    _day_item(program_id, day_id, item_id)
    back = f"/treninzi/{program_id}/dan/{day_id}/uredi"
    try:
        if circuit:                                  # none of the three applies there: kept as stored
            kept = db.KEEP, db.KEEP, db.KEEP
        else:
            kept = _count(sets), _count(rest), _count(rest_after)
        saved = db.update_day_item(item_id, section, kept[0], _count(reps), _count(seconds), kept[1], kept[2], note,
                                   kg=db.read_item_kg(kg), hint=db.KEEP if hint is None else hint)
    except ValueError as err:
        return RedirectResponse(f"{back}?error={quote(str(err))}&stavka={item_id}#stavka-{item_id}", status_code=303)
    if not saved:
        raise HTTPException(status_code=404)
    return RedirectResponse(f"{back}?ok=Spremljeno.&stavka={item_id}#stavka-{item_id}", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/stavke/{item_id}/vjezba")
def day_slot_fill(request: Request, program_id: int, day_id: int, item_id: int, exercise_id: str = Form("")):
    """A slot's "Popuni vježbom" → "Postavi" (26.11.2026): the exercise
    chosen from the library goes into the slot, which is an ordinary row
    from then on (db.fill_slot). Back at the row (?stavka=<id>#stavka-<id>)
    with "Spremljeno." or the refusal's sentence in it (none chosen
    "Odaberi vježbu s popisa.", "Nepoznata vježba.", a row that is no slot
    "Mjesto je već popunjeno."), and after a refusal its "Popuni vježbom"
    open again (`popuni`)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    _day_item(program_id, day_id, item_id)
    at = f"&stavka={item_id}#stavka-{item_id}"
    back = f"/treninzi/{program_id}/dan/{day_id}/uredi"
    chosen = _id(exercise_id)
    try:
        if chosen is None:
            raise ValueError(db.NO_EXERCISE)
        saved = db.fill_slot(item_id, chosen)
    except ValueError as err:
        return RedirectResponse(f"{back}?error={quote(str(err))}&popuni=1{at}", status_code=303)
    if not saved:
        raise HTTPException(status_code=404)
    return RedirectResponse(f"{back}?ok=Spremljeno.{at}", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/dio/{section}/krug")
def day_circuit_save(request: Request, program_id: int, day_id: int, section: str, circuit: str = Form(""),
                     rounds: str = Form(""), rest: str = Form("")):
    """A part's "Kružno" form in the day editor (24.11.2026, kružni
    trening): "Kružni dio" ticked makes the part a circuit, `rounds` rounds
    (2–20) and `rest` seconds between two rounds (0–3600, empty for none),
    db.set_circuit; unticked, the part is a normal one again
    (db.clear_circuit), whatever the numbers say. Back at the part
    (#dio-<key>), which carries the word ("Spremljeno." or the sentence of
    a refusal): `dio` names it, so the page prints the alert in that part,
    not at its top, and opens its form again after a refusal. A section
    that is none comes back at the top ("Odaberi dio treninga.")."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    _program_day(program_id, day_id)
    back = f"/treninzi/{program_id}/dan/{day_id}/uredi"
    at = f"&dio={section}#dio-{section}" if section in SECTIONS else ""
    try:
        if circuit:
            saved = db.set_circuit(day_id, section, _count(rounds), _count(rest))
        else:
            saved = db.clear_circuit(day_id, section)
    except ValueError as err:
        return RedirectResponse(f"{back}?error={quote(str(err))}{at}", status_code=303)
    if not saved:
        raise HTTPException(status_code=404)
    return RedirectResponse(f"{back}?ok=Spremljeno.{at}", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/dio/{section}/naziv")
def day_part_name_save(request: Request, program_id: int, day_id: int, section: str, title: str = Form("")):
    """A part's "Preimenuj" form in the day editor (26.11.2026; the owner:
    "Lets have Glavni dio A, B and C but lets also allow Amir to rename
    them."): "Naziv dijela", this day's own name for the part
    (db.set_part_name: one line; empty, the default back). Back at the part
    as its "Kružno" form answers (?dio=<key>#dio-<key>, the word printed
    there), and `naziv` says it was this form: after a refusal ("Najviše 60
    znakova.") its "Preimenuj" opens again, not "Kružno". A section that is
    none comes back at the top ("Odaberi dio treninga.")."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    _program_day(program_id, day_id)
    back = f"/treninzi/{program_id}/dan/{day_id}/uredi"
    at = f"&dio={section}&naziv=1#dio-{section}" if section in SECTIONS else ""
    try:
        saved = db.set_part_name(day_id, section, title)
    except ValueError as err:
        return RedirectResponse(f"{back}?error={quote(str(err))}{at}", status_code=303)
    if not saved:
        raise HTTPException(status_code=404)
    return RedirectResponse(f"{back}?ok=Spremljeno.{at}", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/stavke/{item_id}/pomak")
def day_item_move(request: Request, program_id: int, day_id: int, item_id: int, smjer: str = Form("")):
    """↑ / ↓ on a row: it trades places with its neighbour in its section."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    _day_item(program_id, day_id, item_id)
    db.move_day_item(item_id, smjer)
    return RedirectResponse(f"/treninzi/{program_id}/dan/{day_id}/uredi#stavka-{item_id}", status_code=303)


@app.post("/treninzi/{program_id}/dan/{day_id}/stavke/{item_id}/obrisi")
def day_item_delete(request: Request, program_id: int, day_id: int, item_id: int):
    """✕ on a row: the exercise leaves the day; the library keeps it."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    _day_item(program_id, day_id, item_id)
    db.delete_day_item(item_id)
    return RedirectResponse(f"/treninzi/{program_id}/dan/{day_id}/uredi", status_code=303)


@app.get("/media/{name}")
def media(request: Request, name: str):
    """An exercise's clip or a day's intro video — auth-gated, never a
    public static mount: staff (the trainer, the owner) watch any, a client
    one whose exercise is in a programme he is matched to (or may stand in
    for one that is: a swap's target, db.video_programs), or whose day is
    one of its days, while his online plan runs; since 26.11.2026 one of
    an exercise in one of his gym trainings, whatever his plans (the
    training's "Kako se izvodi", db.gym_clip). Since 23.11.2026 also a
    member's file from his karton (db.file_owner): his monthly photo, and
    since 25.11.2026 a document under his limitations or of his "Tjelesna
    kompozicija" (his health documents): the member whose file it is and
    staff see it, nobody else, whatever his plans; never public, never
    /slika, marked private, so no shared cache in front of the app keeps
    it, typed by its stored name (application/pdf, image/jpeg) and never
    sniffed, a PDF shown inline under its stored name (never the name the
    member typed: no header carries it)."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=404)
    staff = _is_staff(user)
    owner = db.file_owner(name)
    if owner is not None:
        if not staff and owner != user.id:
            raise HTTPException(status_code=403, detail="Ovo nije tvoj sadržaj.")
    else:
        programs = db.video_programs(name)
        if programs is None:
            raise HTTPException(status_code=404)
        # since 26.11.2026 (build 3) also an exercise's clip that is in one
        # of his gym trainings, whatever his plans (db.gym_clip)
        if not staff and not db.gym_clip(name, user.id) and (
                not _has_online(user) or not any(db.client_can_view(p, user.id) for p in programs)):
            raise HTTPException(status_code=403, detail="Ovo nije tvoj sadržaj.")
    private = {"Cache-Control": "private"} if owner is not None else None
    if storage.r2_enabled():
        # auth just passed — hand out a short-lived direct link; the bytes
        # come from Cloudflare, the bucket itself stays private
        return RedirectResponse(storage.presigned_url(name), status_code=307, headers=private)
    path = storage.local_path(name)
    if not path.is_file():
        raise HTTPException(status_code=404)
    if owner is not None:
        kind = _MEMBER_FILE_TYPES.get(path.suffix.lower(), "image/jpeg")
        headers = {**private, "X-Content-Type-Options": "nosniff"}
        if kind == "application/pdf":
            return FileResponse(path, media_type=kind, headers=headers, filename=name, content_disposition_type="inline")
        return FileResponse(path, media_type=kind, headers=headers)
    return FileResponse(path, media_type=_VIDEO_TYPES.get(path.suffix.lower()))


@app.get("/prehrana", response_class=HTMLResponse)
def prehrana(request: Request):
    return templates.TemplateResponse(request, "prehrana.html",
                                      _ctx(request, current_user(request)))


@app.get("/nutricionizam", include_in_schema=False)
def nutricionizam_legacy(request: Request):
    """Old name — keep bookmarks/links alive."""
    return RedirectResponse("/prehrana", status_code=301)


# ---------- članarine (trainer records cash/card payments by hand) ----------

@app.get("/clanarine", response_class=HTMLResponse)
def clanarine_page(request: Request):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    texts = db.copy_texts()
    today = config.today()
    rows = db.memberships_overview()
    for row in rows:
        # what an uplata recorded now buys, said beside its button
        # (db.next_cycle, the rule record_payment follows)
        row["next"] = {m.plan: db.next_cycle(m, today) for m in row["plans"]}
        # a lapsed plan's termini in its grace week: trained on trust, unpaid
        row["trust"] = {}
        for m in row["plans"]:
            n = db.trust_bookings(row["user"].id, m.plan) if not m.is_active(today) else 0
            if n:
                row["trust"][m.plan] = f"{n} {_termin(n)} na povjerenje — neplaćeno"
    # the online tiers by name for the forms' Paket selects: the QMove
    # cards' titles, the gym owner's text (renaming a card renames the tier)
    return templates.TemplateResponse(request, "clanarine.html", _ctx(
        request, user, copy_texts=texts, rows=rows,
        plans=PLAN_TYPES, plan_labels=PLAN_LABELS, today=today,
        # a plan not held starts from today (the add form's line)
        new_cycle=db.next_cycle(None, today),
        online_tier_names=copy.online_tier_names(texts)))


@app.post("/clanarine/{user_id}/uplata")
def clanarine_uplata(request: Request, user_id: int, plan: str = Form(...),
                     method: str = Form("gotovina"), sessions: int | None = Form(None),
                     tier: str | None = Form(None)):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    if plan not in PLAN_TYPES or method not in ("gotovina", "kartica"):
        raise HTTPException(status_code=400, detail="Nepoznat plan.")
    with db.session_scope() as s:
        target = s.get(db.User, user_id)
    if target is None:
        raise HTTPException(status_code=404)
    # the treninga a month only mean something for grupni; anything else is unlimited
    quota = sessions if (plan in config.STRIPE_TIER_PRICES and sessions in config.GRUPNI_TIERS) else None
    # the QMove tier only for online (none named: record_payment keeps the row's, START for a new one)
    online_tier = tier if (plan == "online" and tier in ONLINE_TIERS) else None
    m = db.record_payment(user_id, plan, method, sessions_per_cycle=quota, tier=online_tier)
    from urllib.parse import quote
    # the flash names the tier as grupni's names its treninga: by its card's title
    named = f" ({copy.online_tier_names(db.copy_texts())[m.tier]})" if plan == "online" else ""
    msg = (f"{PLAN_LABELS[plan]}{f' ({quota} treninga/mj)' if quota else ''}{named}: uplata evidentirana — "
           f"sljedeća {m.next_payment.strftime('%-d.%-m.%Y.')} (vrijedi do {m.dospijece.strftime('%-d.%-m.%Y.')})")
    return RedirectResponse(f"/clanarine?ok={quote(msg)}", status_code=303)


@app.post("/clanarine/{user_id}/ukloni")
def clanarine_ukloni(request: Request, user_id: int, plan: str = Form(...)):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    if not db.remove_membership(user_id, plan):
        raise HTTPException(status_code=404)
    return RedirectResponse("/clanarine?ok=Članarina+je+uklonjena.", status_code=303)


@app.exception_handler(HTTPException)
async def croatian_http_errors(request: Request, exc: HTTPException):
    """403/404 as small Croatian pages, not raw English JSON."""
    if exc.status_code in (403, 404):
        msg = "Nemaš ovlasti za ovu stranicu." if exc.status_code == 403 else "Stranica ne postoji."
        return templates.TemplateResponse(
            request, "error.html",
            _ctx(request, current_user(request), code=exc.status_code, message=msg),
            status_code=exc.status_code)
    from fastapi.exception_handlers import http_exception_handler

    return await http_exception_handler(request, exc)


@app.get("/statistika", response_class=HTMLResponse)
def statistika(request: Request):
    """Owner's traffic view: uplate per plan per month, from the ledger.
    Card payments will land here too once Stripe writes to the same table."""
    user, redirect = _require_owner(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "statistika.html", _ctx(
        request, user, stats=db.payment_stats(),
        plans=PLAN_TYPES, plan_abbr=PLAN_ABBR, plan_labels=PLAN_LABELS,
        method_labels=PAYMENT_METHODS))


# ---------- korisnici (owner only: roster + trainer grants) ----------

@app.get("/korisnici", response_class=HTMLResponse)
def users_page(request: Request):
    user, redirect = _require_owner(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "korisnici.html", _ctx(
        request, user, users=db.list_all_users(),
        owner_email=config.OWNER_EMAIL,
        plans_map={row["user"].id: row["plans"] for row in db.memberships_overview()},
        plan_labels=PLAN_LABELS, plan_abbr=PLAN_ABBR, today=config.today()))


@app.post("/korisnici/{user_id}/trainer")
def grant_trainer(request: Request, user_id: int, revoke: str = Form("")):
    user, redirect = _require_owner(request)
    if redirect:
        return redirect
    with db.session_scope() as s:
        target = s.get(db.User, user_id)
    if target is None:
        raise HTTPException(status_code=404)
    if revoke == "1" and _is_owner(target):
        return RedirectResponse("/korisnici?error=Vlasniku+se+uloga+ne+može+ukinuti.",
                                status_code=303)
    db.set_trainer_id(user_id, revoke != "1")
    from urllib.parse import quote
    msg = f"{target.name or target.email} " + ("više nije trener." if revoke == "1" else "je sada trener.")
    return RedirectResponse(f"/korisnici?ok={quote(msg)}", status_code=303)


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """Served from the root so the SW can control the whole origin —
    /static/sw.js could only control /static/."""
    path = Path(__file__).parent / "static" / "sw.js"
    return FileResponse(path, media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
