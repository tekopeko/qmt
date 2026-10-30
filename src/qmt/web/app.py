"""FastAPI routes: login/signup, the week calendar, booking, trainer admin.

Small enough that auth is a helper called at the top of each route rather than
middleware — if this grows routes the way mojimakrosi did, promote it.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from starlette.middleware.sessions import SessionMiddleware

from .. import auth, config, copy, db, mailer, payments, reminders, storage, upitnik
from ..models import (FEELING_LABELS, ONLINE_TIER_SLOTS, ONLINE_TIERS, PAYMENT_METHODS, PLAN_ABBR,
                      PLAN_LABELS, PLAN_TYPES, SESSION_KINDS, add_month, sub_month)

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


app = FastAPI(title="QMT", lifespan=_lifespan)
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
# an online tier's QMove card, whose title slot is the tier's name (moja_clanarina.html, Paket)
templates.env.globals["ONLINE_TIER_SLOTS"] = ONLINE_TIER_SLOTS
# a price slot's text as the page prints it, and whether it is a number at
# all: "€" follows "50" and "od 30", not "na upit" (landing.html,
# _plan_price.html), nor an amount that carries its own (21.10.2026: a gym
# card's yearly price, typed with its sign where the landing added none,
# is its plan's price.<plan>.year_amount slot since migration 6e2b9d41c7a3)
templates.env.globals["copy_text"] = lambda key, texts: texts.get(key, copy.SLOTS[key].default)
templates.env.tests["priced"] = lambda text: any(ch.isdigit() for ch in str(text)) and "€" not in str(text)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

WEEKDAYS = ["Ponedjeljak", "Utorak", "Srijeda", "Četvrtak", "Petak", "Subota", "Nedjelja"]
WEEKDAYS_SHORT = ["pon", "uto", "sri", "čet", "pet", "sub", "ned"]
# the month view's label, "listopad 2026." (the nominative: it stands alone)
MONTHS = ["siječanj", "veljača", "ožujak", "travanj", "svibanj", "lipanj",
          "srpanj", "kolovoz", "rujan", "listopad", "studeni", "prosinac"]

# Where an ACTIVE plan takes you — every "aktivna članarina" state is a door,
# not a label. (path, button text)
PLAN_LINKS = {
    "grupni": ("/raspored", "Rezerviraj termin"),
    "individualni": ("/raspored", "Rezerviraj termin"),
    "poluindividualni": ("/raspored", "Rezerviraj termin"),
    "rehabilitacija": ("/raspored", "Rezerviraj termin"),
    "online": ("/treninzi", "Otvori online treninge"),
    "prehrana": ("/prehrana", "Otvori prehranu"),
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
    an open redirect to another site ("//evil.com", "https://...")."""
    if nxt and nxt.startswith("/") and not nxt.startswith("//") and ":" not in nxt.split("?")[0]:
        return nxt
    return "/"


def current_user(request: Request):
    uid = request.session.get("user_id")
    return db.get_user(uid) if uid else None


def _is_owner(user) -> bool:
    """The app owner = the OWNER_EMAIL account (mojimakrosi's owner-by-email
    pattern). Only the owner manages roles; trainers run the gym. Ownership
    stays with the env var — it is deliberately NOT hand-over-able in-app."""
    return bool(user and config.OWNER_EMAIL
                and (user.email or "").strip().lower() == config.OWNER_EMAIL)


def _can_edit_copy(user) -> bool:
    """May this viewer edit the public copy in place, the announcements
    among it? The trainer and the owner."""
    return bool(user and (user.is_trainer or _is_owner(user)))


def _has_online(user) -> bool:
    """May this user see Online treninzi at all? Trainer always; clients only
    with an active `online` plan (the tab is a paid product, not a teaser)."""
    return bool(user) and (user.is_trainer or "online" in db.active_plan_kinds(user.id))


def _pop_feedback_prompt(request: Request, user):
    """One-shot after login: termini finished in the last 7 days that still have
    no osvrt. The flag is popped on the FIRST page rendered, so the prompt asks
    once per login and never follows the client around the app. Already being on
    the karton counts as answered — the forms are right there."""
    if user is None or not request.session.pop("fb_prompt", False):
        return None
    if request.url.path.startswith("/karton"):
        return None
    pending = db.pending_feedback(user.id)
    if not pending:
        return None
    latest = pending[0].starts_at.astimezone(config.TZ)
    # formatted here: the prompt renders on whatever page the login landed on,
    # and those contexts carry no tz
    return {"count": len(pending), "title": pending[0].title,
            "when": f"{WEEKDAYS_SHORT[latest.weekday()]} {latest:%-d.%-m. %H:%M}"}


def _ctx(request: Request, user, copy_texts: dict[str, str] | None = None, **extra):
    return {"request": request, "user": user, "weekdays_short": WEEKDAYS_SHORT,
            "mojimakrosi_url": config.MOJIMAKROSI_URL,
            "show_online": _has_online(user),
            "plan_links": PLAN_LINKS,
            "signup_open": config.signup_open(),
            "signup_mode": config.signup_mode(),
            # in-place editable copy: the edited texts (a route that has read
            # them already passes its dict), and whether this viewer may edit
            "copy_texts": db.copy_texts() if copy_texts is None else copy_texts,
            "can_edit_copy": _can_edit_copy(user),
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
    request.session["user_id"] = u.id
    # Owed osvrti are asked for once, on the first page this login renders —
    # the flag only arms the prompt, _pop_feedback_prompt decides if there is
    # anything to ask about.
    if not u.is_trainer:
        request.session["fb_prompt"] = True
    # New clients first complete their basic info (ime, prezime, datum) —
    # the profil page explains itself; trainers are exempt.
    if not u.is_trainer and not u.profile_complete:
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
              reset: str = Form(""), part: str = Form(""), remove: str = Form(""), add: str = Form("")):
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
    return JSONResponse({"ok": True, "text": cleaned, "default": False})


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


def _copy_save_row(slot, text: str, reset: str, set_shown, set_text) -> JSONResponse:
    """A row's switch or text (an announcement's, a gym card's; an upitnik
    question's text, set_shown None: its switch is POST
    /upitnik/pitanje/{id}), answered as
    copy_save answers for a slot of its type: the switch takes "on" or
    "off" (reset=1: its default, on) and hands it to set_shown(on); a text
    is cleaned and capped and handed to set_text(cleaned), which stores it
    and returns what it stored: an emptied one stays empty (no row's text
    is required), and reset=1 hands it the row's placeholder, the slot's
    default, "default": true. A setter's LookupError (the row deleted
    meanwhile) is the caller's to answer."""
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
    return JSONResponse({"ok": True, "text": set_text(cleaned), "default": False})


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
        return _copy_save_row(
            slot, text, reset, lambda on: db.set_gym_card_shown(card_id, on, user_id),
            lambda cleaned: db.set_gym_card_field(card_id, copy.GYM_CARD_COLUMNS[field], cleaned, user_id))
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

    unsupported = "Nepodržan format — dozvoljeno: jpg, png, webp."
    if slika is None or Path(slika.filename or "").suffix.lower() not in _IMAGE_SUFFIXES:
        return bad(unsupported)
    import secrets
    import tempfile

    from PIL import Image, ImageOps

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
            with Image.open(raw) as im:
                if im.format not in _IMAGE_FORMATS:
                    return bad(unsupported)
                # a JPEG decodes straight at the smallest scale the shrink
                # still has room in: a 48 MP photo at a quarter, in a
                # sixteenth of the memory
                scale = min(1, IMAGE_PX / max(im.size))
                im.draft("RGB", (max(1, round(im.width * scale)), max(1, round(im.height * scale))))
                photo = ImageOps.exif_transpose(im).convert("RGB")
        except Exception:                                # not an image Pillow can read, or a broken one
            return bad(unsupported)
        photo.thumbnail((IMAGE_PX, IMAGE_PX))                         # never enlarges
        photo.save(out, "JPEG", quality=82, progressive=True)        # no exif= given: none is written
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
        # the state in words; the colour only reinforces it
        if not active:
            chip = ("istekla", "lapsed")
        elif cancelling:
            chip = ("otkazana · vrijedi do kraja", "off")
        elif days_left <= 7:
            chip = (f"dospijeva {_relative_day(m.dospijece, today)}", "due")
        else:
            chip = ("aktivna", "ok")
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


@app.post("/placanje/portal")
def placanje_portal(request: Request):
    """Stripe's hosted portal: change card, cancel, download invoices."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
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
    month_view = view == "month" and not user.is_trainer
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

        beyond_window = not user.is_trainer and monday > last_monday
        start = datetime(monday.year, monday.month, monday.day, tzinfo=config.TZ)
        rows = [] if beyond_window else db.sessions_between(start, start + timedelta(days=7), now)
        mine = db.user_booking_ids(user.id, [r["session"].id for r in rows])
        my_plans = db.active_plan_kinds(user.id)
        # a client's running plans and their dospijeće: a termin after it
        # cannot be booked (db._refusal's "razdoblje"), so its row offers
        # nothing and the week says until when the plan runs; a weekly
        # repeat stops at the earlier of it and the window's last day
        # (db._series_dates). Never the trainer's: he does not book.
        paid_until = {} if user.is_trainer else {m.plan: m.dospijece for m in plans if m.is_active(today)}

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
                    "allowed": user.is_trainer or sess.kind in my_plans,
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
    for sess in db.my_upcoming(user.id):
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
    if mine_days and not user.is_trainer:
        first = mine_days[0]
        next_booking = dict(first["sessions"][0], name=first["name"],
                            relative=_relative_day(first["date"], today))

    # Right after a booking (POST /book adds ?series=<id>): offer the same slot
    # on every following week of the paid period. Only on the client's own
    # booking; trainers do not book. A garbage id simply offers nothing (and
    # one past Postgres' integer range never reaches a query, where it 500s).
    series_offer = None
    try:
        series_id = int(series) if series else None
    except ValueError:
        series_id = None
    if series_id and 0 < series_id < 2**31 and not user.is_trainer \
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
        next_week=(None if not user.is_trainer and monday >= last_monday
                   else (monday + timedelta(days=7)).isoformat()),
        beyond_window=beyond_window, weeks_ahead=db.weeks_text(config.BOOKING_WEEKS),
        # the week's termini after a running plan's dospijeće: the earliest
        # such dospijeće, said once under the termini
        period_until=period_until,
        series_report=None if user.is_trainer else _read_series_report(booked, skipped, paket),
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
    sent = mailer.send_password_reset_email(u.email, link)
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
    user = current_user(request)
    if user is None:
        return None, RedirectResponse("/login", status_code=303)
    if not (user.is_trainer or _is_owner(user)):
        raise HTTPException(status_code=403, detail="Samo trener")
    return user, None


def _require_owner(request: Request):
    user = current_user(request)
    if user is None:
        return None, RedirectResponse("/login", status_code=303)
    if not _is_owner(user):
        raise HTTPException(status_code=403, detail="Samo vlasnik aplikacije")
    return user, None


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
    return templates.TemplateResponse(request, "roster.html", _ctx(
        request, user, sess=sess,
        local_time=sess.starts_at.astimezone(config.TZ),
        people=db.roster(session_id),
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
    # (tz: the Račun card's registration date, in the studio's time zone)
    return templates.TemplateResponse(request, "profil.html", _ctx(
        request, user, first_login="dopuni" in request.query_params, tz=config.TZ))


@app.post("/profil")
def profil_save(request: Request, name: str = Form(...), last_name: str = Form(...),
                birth_date: str = Form(""), phone: str = Form("")):
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
    entry_pass = not user.profile_complete       # the after-sign-up completion
    db.update_profile(user.id, name, last_name, born, phone)
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
    an osvrt whose termin falls outside booking_history's window still shows."""
    from datetime import datetime, time

    sessions = db.booking_history(subject_id)
    logs = db.training_logs(subject_id)
    by_session = {x.session_id: x for x in logs if x.session_id}

    rows, attached = [], set()
    for s in sessions:
        log = by_session.get(s.id)
        if log is not None:
            attached.add(log.id)
        rows.append({"session": s, "log": log, "at": s.starts_at.astimezone(config.TZ)})
    for x in logs:
        if x.id in attached:
            continue
        at = (x.session.starts_at.astimezone(config.TZ) if x.session
              else datetime.combine(x.date, time(0), tzinfo=config.TZ))
        rows.append({"session": x.session, "log": x, "at": at})
    rows.sort(key=lambda r: r["at"], reverse=True)
    return rows


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
    return templates.TemplateResponse(request, "karton.html", _ctx(
        request, viewer, copy_texts=texts, subject=subject, own=own, age=age,
        can_upitnik=own and _has_online(subject),
        onboarding=onboarding, answers=answers,
        levels=upitnik.LEVELS, goals=upitnik.GOALS, max_score_v1=upitnik.MAX_SCORE_V1,
        u_rows=u_rows, u_chips=u_chips, u_score=u_score, pain_ask=upitnik.PAIN_ASK, pain_where=pain_where,
        pain_note=texts.get("upitnik.pain_note", copy.SLOTS["upitnik.pain_note"].default),
        diary=_diary_rows(subject.id),
        # just-finished termini open their osvrt form straight away; older ones
        # keep it folded so the diary stays a list, not a wall of forms
        pending_ids={x.id for x in pending},
        feelings=FEELING_LABELS,
        upcoming=db.my_upcoming(subject.id),
        today=config.today(), tz=config.TZ,
    ))


@app.get("/karton", response_class=HTMLResponse)
def karton_self(request: Request):
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/karton')}", status_code=303)
    if user.is_trainer:
        # the trainer has no karton of their own — their view is per-client
        return RedirectResponse("/clanarine", status_code=303)
    return _render_karton(request, user, user, own=True)


@app.get("/karton/{user_id}", response_class=HTMLResponse)
def karton_client(request: Request, user_id: int):
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


@app.post("/karton/feedback/{session_id}")
def karton_feedback(request: Request, session_id: int, effort: int = Form(...),
                    feeling: str = Form(""), note: str = Form("")):
    """Post-training osvrt — offered by the app after a booked termin ends,
    never a free-floating diary entry."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not 1 <= effort <= 10 or (feeling and feeling not in FEELING_LABELS):
        return RedirectResponse("/karton?error=Neispravan+osvrt.", status_code=303)
    try:
        db.add_session_feedback(user.id, session_id, effort,
                                feeling or None, note.strip())
    except db.BookingError as e:
        from urllib.parse import quote
        return RedirectResponse(f"/karton?error={quote(str(e))}", status_code=303)
    return RedirectResponse("/karton?ok=Osvrt+je+spremljen.", status_code=303)


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
                    feeling: str = Form(""), note: str = Form("")):
    """The client corrects their own osvrt — same fields, same rules as writing it."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not 1 <= effort <= 10 or (feeling and feeling not in FEELING_LABELS):
        return RedirectResponse("/karton?error=Neispravan+osvrt.", status_code=303)
    if not db.update_training_log(log_id, user.id, effort, feeling or None, note.strip()):
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


# ---------- treninzi (custom training programmes) ----------

# The exercises' clips (the library, 30.10.2026): what a file may be by its
# extension, the content type it is stored and served with, and the bytes it
# must start with (sniffed, so a file of another kind renamed is refused
# before it is stored). An MP4 or a QuickTime .mov is ISO base media, its
# first box "ftyp" at byte 4; a WebM is EBML, 1A 45 DF A3 at byte 0.
_VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}
_VIDEO_SIGNATURES = {".mp4": (4, b"ftyp"), ".mov": (4, b"ftyp"), ".webm": (0, b"\x1a\x45\xdf\xa3")}
_VIDEO_UNSUPPORTED = "Nepodržan format — dozvoljeno: mp4, mov, webm."


def _save_video(upload: UploadFile | None, exercise_id: int) -> str | None:
    """Store an uploaded exercise clip; its new file name
    (vjezba-<id>-<hex>.<ext>), or None when no file came (or an empty one).

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
        name = f"vjezba-{exercise_id}-{secrets.token_hex(8)}{suffix}"
        storage.save(name, tmp, _VIDEO_TYPES[suffix])
        return name
    finally:
        tmp.unlink(missing_ok=True)          # a refusal's bytes; a stored file has moved on already


# Where "Nova vježba →" in the programme editor comes back to once the
# exercise is made: a path of the treninzi pages, nothing else (no other
# site, no other page of the app, no query).
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
    if not user.is_trainer:
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
    if user.is_trainer:
        db.ensure_online_skeletons()             # fresh deploys heal themselves
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
        return templates.TemplateResponse(request, "treninzi_admin.html", _ctx(
            request, user, groups=groups, untagged=untagged,
            levels=upitnik.LEVELS, goals=upitnik.GOALS))
    has_plan = _has_online(user)
    onboarding = db.get_onboarding(user.id) if has_plan else None
    # gates stack: no `online` plan -> only the gate card; with a plan but no
    # upitnik -> only the prompt; then the matched programmes render — the
    # whole online side is automatic, nothing is handed out per client
    programs = (db.programs_for_combo(onboarding.level, onboarding.goal)
                if onboarding else [])
    return templates.TemplateResponse(request, "treninzi.html", _ctx(
        request, user, programs=programs, onboarding=onboarding,
        has_plan=has_plan, levels=upitnik.LEVELS, goals=upitnik.GOALS))


@app.post("/treninzi")
def create_program(request: Request, title: str = Form(...), intro: str = Form(""),
                   level: str = Form(...), goal: str = Form(...)):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    title = title.strip()
    if not title:
        return RedirectResponse("/treninzi?error=Naziv+je+obavezan.", status_code=303)
    if level not in upitnik.LEVELS or goal not in upitnik.GOALS:
        return RedirectResponse("/treninzi?error=Odaberi+razinu+i+cilj.", status_code=303)
    pid = db.create_program(title, intro.strip() or None, level, goal)
    return RedirectResponse(f"/treninzi/{pid}/uredi", status_code=303)


# ---------- the library of exercises (Amir's, 30.10.2026) ----------
# Declared before /treninzi/{program_id}: that path would take "vjezbe" for a
# programme's id.

@app.get("/treninzi/vjezbe", response_class=HTMLResponse)
def vjezbe(request: Request, q: str = ""):
    """The library: every exercise in the alphabet's order, its tags, whether
    it has a clip and how many programmes hold it; `q` keeps those whose name
    or tags hold it, whatever its case."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    q = " ".join(q.split())
    every = db.exercises()
    rows = db.exercises(q) if q else every
    return templates.TemplateResponse(request, "vjezbe.html", _ctx(
        request, user, rows=rows, q=q, total=len(every)))


def _exercise_page(request: Request, user, e, form: dict | None = None, error: str | None = None,
                   natrag: str | None = None, status_code: int = 200):
    """An exercise's form page: a new one (e None) or one of the library. With
    `form`, what was posted and refused (a name taken, say), shown again under
    the error. The similar exercises to tick are every other exercise, the
    ticked ones first, each group in the alphabet's order."""
    if form is None:
        form = ({"name": e.name, "instructions": e.instructions, "rep_note": e.rep_note, "tags": e.tags,
                 "alternatives": {a.id for a in e.alternatives}} if e is not None else
                {"name": "", "instructions": "", "rep_note": "", "tags": "", "alternatives": set()})
    choices = [x for x, _ in db.exercises() if e is None or x.id != e.id]
    choices.sort(key=lambda x: x.id not in form["alternatives"])      # stable: the alphabet within each
    return templates.TemplateResponse(request, "vjezba.html", _ctx(
        request, user, e=e, v=form, choices=choices, error=error, natrag=natrag,
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
    "Nova vježba →" came from (`natrag`, the programme editor), the new
    exercise chosen in its picker."""
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
    """The form's one POST: the texts and the similar exercises together."""
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
        name = _save_video(video, exercise_id)
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
    """Delete an exercise nothing holds, then its clip; one a programme holds
    stays, its page saying where it is."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    try:
        video = db.delete_exercise(exercise_id)
    except ValueError as err:
        return RedirectResponse(f"/treninzi/vjezbe/{exercise_id}?error={quote(str(err))}", status_code=303)
    if video:
        storage.delete(video)
    return RedirectResponse("/treninzi/vjezbe?ok=Vje%C5%BEba+je+obrisana.", status_code=303)


@app.get("/treninzi/{program_id}", response_class=HTMLResponse)
def program_view(request: Request, program_id: int):
    user, p = _program_or_403(request, program_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "trening_view.html", _ctx(
        request, user, p=p))


@app.get("/treninzi/{program_id}/uredi", response_class=HTMLResponse)
def program_edit_page(request: Request, program_id: int, vjezba: str = ""):
    """The programme's editor; its picker offers the whole library, the
    exercise `vjezba` chosen (one just made through "Nova vježba →")."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    p = db.get_program(program_id)
    if p is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "trening_edit.html", _ctx(
        request, user, p=p, levels=upitnik.LEVELS, goals=upitnik.GOALS,
        choices=[e for e, _ in db.exercises()], chosen=_id(vjezba)))


@app.post("/treninzi/{program_id}/edit")
def program_edit(request: Request, program_id: int, title: str = Form(...),
                 intro: str = Form(""), level: str = Form(...), goal: str = Form(...)):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    if level not in upitnik.LEVELS or goal not in upitnik.GOALS:
        return RedirectResponse(f"/treninzi/{program_id}/uredi?error=Odaberi+razinu+i+cilj.",
                                status_code=303)
    db.update_program(program_id, title.strip() or "Trening", intro.strip() or None,
                      level, goal)
    return RedirectResponse(f"/treninzi/{program_id}/uredi?ok=Spremljeno.", status_code=303)


@app.post("/treninzi/{program_id}/delete")
def program_delete(request: Request, program_id: int):
    """The programme and its items go; the exercises and their clips stay in
    the library."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    db.delete_program(program_id)
    return RedirectResponse("/treninzi?ok=Trening+je+obrisan.", status_code=303)


@app.post("/treninzi/{program_id}/items")
def item_add(request: Request, program_id: int, exercise_id: str = Form("")):
    """"+ Dodaj vježbu": an exercise of the library, last in the programme.
    An item has nothing of its own to edit since 30.10.2026 (the exercise
    holds the texts and the clip), so no item edit route: another exercise
    is ✕ and this, then ↑ / ↓."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    if db.get_program(program_id) is None:
        raise HTTPException(status_code=404)
    back = f"/treninzi/{program_id}/uredi"
    chosen = _id(exercise_id)
    if chosen is None or db.add_item(program_id, chosen) is None:
        return RedirectResponse(f"{back}?error=Odaberi+vje%C5%BEbu+iz+baze.", status_code=303)
    return RedirectResponse(f"{back}#dodaj", status_code=303)


@app.post("/treninzi/{program_id}/items/{item_id}/delete")
def item_delete(request: Request, program_id: int, item_id: int):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    db.delete_item(item_id)
    return RedirectResponse(f"/treninzi/{program_id}/uredi", status_code=303)


@app.post("/treninzi/{program_id}/items/{item_id}/move")
def item_move(request: Request, program_id: int, item_id: int, dir: str = Form(...)):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    db.move_item(item_id, "up" if dir == "up" else "down")
    return RedirectResponse(f"/treninzi/{program_id}/uredi", status_code=303)


@app.get("/media/{name}")
def media(request: Request, name: str):
    """An exercise's clip — auth-gated, never a public static mount: staff
    (the trainer, the owner) watch any, a client one whose exercise is in a
    programme he is matched to, while his online plan runs."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=404)
    programs = db.video_programs(name)
    if programs is None:
        raise HTTPException(status_code=404)
    staff = user.is_trainer or _is_owner(user)
    if not staff and (not _has_online(user)
                      or not any(db.client_can_view(p, user.id) for p in programs)):
        raise HTTPException(status_code=403, detail="Ovo nije tvoj sadržaj.")
    if storage.r2_enabled():
        # auth just passed — hand out a short-lived direct link; the bytes
        # come from Cloudflare, the bucket itself stays private
        return RedirectResponse(storage.presigned_url(name), status_code=307)
    path = storage.local_path(name)
    if not path.is_file():
        raise HTTPException(status_code=404)
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
