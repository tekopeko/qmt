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
templates.env.globals["copy_flag"] = copy.flag_on      # a flag slot: on or off
templates.env.globals["copy_image"] = copy.image_name  # an image slot: its file's name, or None
templates.env.globals["CAP"] = copy.CAP                # a text's cap, where no slot says it (_copy.html, field)
templates.env.globals["ANNOUNCEMENT"] = copy.ANNOUNCEMENT_SLOTS   # an announcement's fields (landing.html, #aktualno)
templates.env.globals["GYM"] = copy.GYM_CARD_SLOTS     # a gym card's fields (landing.html, #dvorana)
# an online tier's QMove card, whose title slot is the tier's name (moja_clanarina.html, Paket)
templates.env.globals["ONLINE_TIER_SLOTS"] = ONLINE_TIER_SLOTS
# a price slot's text as the page prints it, and whether it is a number at
# all: "€" follows "50" and "od 30", not "na upit" (landing.html, _plan_price.html)
templates.env.globals["copy_text"] = lambda key, texts: texts.get(key, copy.SLOTS[key].default)
templates.env.tests["priced"] = lambda text: any(ch.isdigit() for ch in str(text))
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

def reference_prices(texts: dict[str, str]) -> dict[str, tuple[str, str, str]]:
    """Plan -> (amount, unit, note), the price as the site says it: the
    edited price.<plan>.* slots, else their defaults (no note: ""). A plan
    with no note slot (prehrana: its hint is the add-on's amounts) has ""
    for one, whatever site_copy may still hold under that key."""
    def text(key: str) -> str:
        if key not in copy.SLOTS:
            return ""
        return texts.get(key, copy.SLOTS[key].default)
    return {plan: (text(f"price.{plan}.amount"), text(f"price.{plan}.unit"), text(f"price.{plan}.note"))
            for plan in copy.REFERENCE_PRICES}


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
            "max_media_mb": config.MAX_MEDIA_MB,
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
              reset: str = Form("")):
    """Save one edited text (the in-place editor in base.html posts here).
    JSON in both directions: this is called by fetch, never by a form. The
    limit is the slot's, enforced here as well as in the browser; an empty
    text, or reset=1, puts the template's default back. A list slot is edited
    one item at a time (see _copy_save_list); a flag slot is switched, its
    text "on" or "off" and nothing else. An image slot takes only reset=1,
    which removes its photo; a photo goes up through POST /copy/{key}/slika,
    so no text can ever land in an image slot. An announcement's field (a
    row, not a slot: aktualno.<id>.<field>) is edited the same way, by the
    type its field has (see _copy_save_announcement), and so is a gym
    card's (dvorana.<id>.<field>, see _copy_save_gym_card)."""
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
        return JSONResponse({"ok": False, "error": "Nepoznat tekst."}, status_code=404)
    if isinstance(slot, copy.ListSlot):
        return _copy_save_list(key, slot, text, index, reset, user.id)
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
    if not cleaned:
        db.reset_copy(key)
        return JSONResponse({"ok": True, "text": slot.default, "default": True})
    db.set_copy(key, cleaned, user.id)
    return JSONResponse({"ok": True, "text": cleaned, "default": False})


# A row's field as the editor names it: an announcement's
# aktualno.<id>.<field>, a gym card's dvorana.<id>.<field> (year_price: an
# underscore). At most nine digits, so no id is past what the column can hold.
_ANNOUNCEMENT_KEY = re.compile(r"aktualno\.([1-9][0-9]{0,8})\.([a-z]+)")
_GYM_CARD_KEY = re.compile(r"dvorana\.([1-9][0-9]{0,8})\.([a-z_]+)")


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


def _copy_save_row(slot, text: str, reset: str, set_shown, set_text) -> JSONResponse:
    """A row's switch or text (an announcement's, a gym card's), answered as
    copy_save answers for a slot of its type: the switch takes "on" or
    "off" (reset=1: its default, on) and hands it to set_shown(on); a text
    is cleaned and capped and handed to set_text(cleaned), which stores it
    and returns what it stored: for an empty one (or reset=1) the row's
    placeholder, "default": true. A setter's LookupError (the row deleted
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
    cleaned = "" if reset == "1" else copy.clean(text)
    if len(cleaned) > slot.max:
        return JSONResponse({"ok": False, "error": f"Najviše {slot.max} znakova — ovo ih ima {len(cleaned)}."},
                            status_code=400)
    return JSONResponse({"ok": True, "text": set_text(cleaned), "default": not cleaned})


def _copy_save_announcement(key: str, ann_id: int, field: str, slot, text: str, reset: str,
                            user_id: int) -> JSONResponse:
    """One change to an announcement's field, answered as copy_save answers
    for a slot of its type: the switch and a text as _copy_save_row does
    (an empty text the new card's placeholder again,
    copy.ANNOUNCEMENT_BLANK); the photo only reset=1, which removes the
    row's name and the file. A card deleted meanwhile answers 404, as an
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
    announcement's (_copy_save_row; an empty text the new card's
    placeholder again, copy.GYM_CARD_BLANK); the bullets as a list slot's,
    one item at a time by `index` (_edit_list), and reset=1 puts the new
    card's two bullets back. A card deleted meanwhile answers 404, as an
    unknown key does."""
    try:
        if isinstance(slot, copy.ListSlot):
            if reset == "1":
                items = db.set_gym_card_points(card_id, list(slot.default), user_id)
                return JSONResponse({"ok": True, "items": items, "default": True})
            card = db.gym_card(card_id)
            if card is None:
                raise LookupError(f"no gym card {card_id}")
            items = card.point_items
            return _edit_list(items, items == list(slot.default), slot, text, index,
                              lambda changed: db.set_gym_card_points(card_id, changed, user_id))
        return _copy_save_row(
            slot, text, reset, lambda on: db.set_gym_card_shown(card_id, on, user_id),
            lambda cleaned: db.set_gym_card_field(card_id, copy.GYM_CARD_COLUMNS[field], cleaned, user_id))
    except LookupError:
        return JSONResponse({"ok": False, "error": "Nepoznat tekst."}, status_code=404)


def _copy_save_list(key: str, slot: copy.ListSlot, text: str, index: str, reset: str,
                    user_id: int) -> JSONResponse:
    """One change to a list slot. reset=1 puts the default list back; any
    other change is _edit_list's, made to the stored list (no row: the
    default list) and stored as the slot's one row."""
    if reset == "1":
        db.reset_copy(key)
        return JSONResponse({"ok": True, "items": list(slot.default), "default": True})
    stored = db.copy_texts().get(key)
    return _edit_list(copy.load_items(stored, slot), stored is None, slot, text, index,
                      lambda items: db.set_copy(key, copy.dump_items(items), user_id))


def _edit_list(items: list[str], untouched: bool, slot: copy.ListSlot, text: str, index: str,
               write) -> JSONResponse:
    """One change to a list (a list slot's, a gym card's bullets): `index`
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
        # spooled first in 1 MB chunks, as _save_media does: the cap trips
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


# ---------- the announcements: add and delete (their fields: POST /copy/{key}) ----------

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
    # the plans' names here, plan.<plan>.name, the prices, price.<plan>.*,
    # and the add-on's amounts, addon.*)
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
        add_plans=[p for p in PLAN_TYPES if p not in held], prices=table,
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
def placanje(request: Request, plan: str, sessions: int | None = Form(None)):
    """Start a monthly card subscription for one plan — hands off to Stripe
    Checkout. Access is NOT granted here; the signed webhook does that."""
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


@app.get("/raspored", response_class=HTMLResponse)
def calendar(request: Request, week: str | None = None, series: str | None = None,
             day: str | None = None, view: str | None = None, month: str | None = None):
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/raspored')}", status_code=303)

    today = config.today()
    now = datetime.now(config.TZ)
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

        start = datetime(monday.year, monday.month, monday.day, tzinfo=config.TZ)
        rows = db.sessions_between(start, start + timedelta(days=7))
        mine = db.user_booking_ids(user.id, [r["session"].id for r in rows])
        my_plans = db.active_plan_kinds(user.id)

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
                sessions.append({
                    "id": sess.id, "title": sess.title,
                    "time": local.strftime("%H:%M"),
                    "end": (local + timedelta(minutes=sess.duration_min)).strftime("%H:%M"),
                    "booked": r["booked"], "capacity": sess.capacity,
                    "full": r["booked"] >= sess.capacity,
                    "canceled": sess.canceled,
                    "past": sess.starts_at <= now,
                    "mine": sess.id in mine,
                    "can_cancel": sess.id in mine and now < db.cancel_deadline(sess),
                    "one_on_one": sess.capacity == 1,
                    # may this client book this kind? (trainer never books via UI)
                    "allowed": user.is_trainer or sess.kind in my_plans,
                    # from the weekly timetable: the phone's sheet offers the
                    # "isti termin svaki tjedan" checkbox only for these
                    "weekly": sess.template_id is not None,
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

    plans = db.memberships_for(user.id)
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
        next_week=(monday + timedelta(days=7)).isoformat(),
        mine_days=mine_days, next_booking=next_booking, cutoff_hours=config.CANCEL_CUTOFF_HOURS,
        # with no plan running a client is told booking needs one (the plans
        # themselves are on /moja-clanarina since 18.10.2026)
        has_active_plan=any(m.is_active(today) for m in plans),
        view="month" if month_view else "week", **overview,
    ))


def _redirect_back(week: str, error: str | None = None, ok: str | None = None,
                   cta: str | None = None, series: int | None = None,
                   day: str = "") -> RedirectResponse:
    """Back to the calendar, on the right week, with feedback visible.
    The separator depends on whether `back` already has a query string —
    "/&error=..." is not a query string and the message silently vanishes.
    `cta` turns a refusal into an offer: it carries a PLAN KIND, never a URL —
    the alert builds the link itself, so a crafted ?cta= cannot become an
    off-site href. `series` (a session id) asks the calendar to offer that
    booking's weekly repeat. `day` is the day a phone was showing (ISO; any
    other value is dropped), so the page comes back on it."""
    from urllib.parse import quote

    back = f"/raspored?week={week}" if week else "/raspored"
    shown = _iso_day(day)
    for key, val in (("day", shown and shown.isoformat()), ("error", error), ("ok", ok),
                     ("cta", cta), ("series", series)):
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
        if not any_more:
            # the booking stands, the repeat found nothing to add: say so
            # without contradicting the ✓ ("nijedan termin nije rezerviran")
            why = text.split(" — ", 1)[1] if " — " in text else ""
            return _redirect_back(week, ok="Rezervirano ✓ — samo ovaj termin" + (", " + why if why else "."), day=day)
        return _redirect_back(week, ok="Rezervirano ✓ — " + _lower_first(text), day=day)
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
    """"Isti termin svaki tjedan": the slot just booked, on every following
    week of the paid period (the rules are db.book_series')."""
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
    return _redirect_back(week, ok=text, day=day) if ok else _redirect_back(week, text, day=day)


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
    today = config.today()
    born = subject.birth_date
    age = (today.year - born.year - ((today.month, today.day) < (born.month, born.day))
           if born else None)
    pending = db.pending_feedback(subject.id) if own else []
    return templates.TemplateResponse(request, "karton.html", _ctx(
        request, viewer, subject=subject, own=own, age=age,
        can_upitnik=own and _has_online(subject),
        onboarding=onboarding, answers=answers,
        questions=upitnik.QUESTIONS, levels=upitnik.LEVELS, goals=upitnik.GOALS,
        max_score=upitnik.MAX_SCORE,
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


@app.get("/upitnik", response_class=HTMLResponse)
def upitnik_page(request: Request):
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/upitnik')}", status_code=303)
    if not _has_online(user):
        return RedirectResponse(
            "/karton?error=Upitnik+je+dio+online+članarine+—+javi+se+treneru.", status_code=303)
    if user.is_trainer:
        return RedirectResponse("/treninzi", status_code=303)
    import json

    existing = db.get_onboarding(user.id)
    return templates.TemplateResponse(request, "upitnik.html", _ctx(
        request, user, questions=upitnik.QUESTIONS, goals=upitnik.GOALS,
        picked=json.loads(existing.answers) if existing else {},
        picked_goal=existing.goal if existing else None,
    ))


@app.post("/upitnik")
async def upitnik_submit(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _has_online(user):
        return RedirectResponse(
            "/karton?error=Upitnik+je+dio+online+članarine+—+javi+se+treneru.", status_code=303)
    form = await request.form()
    import json

    picked: dict[str, int] = {}
    try:
        for q in upitnik.QUESTIONS:
            idx = int(form[q["key"]])
            if not 0 <= idx < len(q["options"]):
                raise ValueError
            picked[q["key"]] = idx
        goal = str(form["goal"])
        if goal not in upitnik.GOALS:
            raise ValueError
    except (KeyError, ValueError):
        return RedirectResponse("/upitnik?error=Odgovori+na+sva+pitanja.", status_code=303)
    score, level = upitnik.score_answers(picked)
    db.save_onboarding(user.id, json.dumps(picked), score, level, goal)
    # straight to the programmes — the routing is the whole point of the upitnik
    return RedirectResponse(
        f"/treninzi?ok=Upitnik+je+spremljen+—+{upitnik.LEVELS[level].replace(' ', '+')}.",
        status_code=303)


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

_MEDIA_KINDS = {
    ".jpg": "img", ".jpeg": "img", ".png": "img", ".webp": "img", ".gif": "img",
    ".mp4": "video", ".mov": "video", ".m4v": "video", ".webm": "video",
}
_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif", ".mp4": "video/mp4",
    ".mov": "video/quicktime", ".m4v": "video/x-m4v", ".webm": "video/webm",
}


def _save_media(upload: UploadFile | None) -> tuple[str | None, str | None]:
    """Store an uploaded exercise image/video; returns (filename, kind).

    Chunked to a size cap — a phone video can be huge and must fail cleanly,
    not fill the disk. Raises ValueError with a Croatian message on refusal.
    """
    if upload is None or not (upload.filename or "").strip():
        return None, None
    import secrets

    suffix = Path(upload.filename).suffix.lower()
    if suffix not in _MEDIA_KINDS:
        raise ValueError("Nepodržan format — dozvoljeno: jpg, png, webp, gif, mp4, mov, webm.")
    import tempfile

    name = f"{secrets.token_hex(8)}{suffix}"
    limit = config.MAX_MEDIA_MB * 1024 * 1024
    total = 0
    # spool locally first — the size cap must trip BEFORE any bytes reach R2
    tmp = Path(tempfile.mkstemp(suffix=suffix)[1])
    with open(tmp, "wb") as f:
        while chunk := upload.file.read(1 << 20):
            total += len(chunk)
            if total > limit:
                f.close()
                tmp.unlink(missing_ok=True)
                raise ValueError(f"Datoteka je veća od {config.MAX_MEDIA_MB} MB.")
            f.write(chunk)
    if total == 0:
        tmp.unlink(missing_ok=True)
        return None, None
    storage.save(name, tmp, _MEDIA_TYPES.get(suffix))
    return name, _MEDIA_KINDS[suffix]


def _unlink_media(name: str | None) -> None:
    if name:
        storage.delete(name)


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


@app.get("/treninzi/{program_id}", response_class=HTMLResponse)
def program_view(request: Request, program_id: int):
    user, p = _program_or_403(request, program_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "trening_view.html", _ctx(
        request, user, p=p))


@app.get("/treninzi/{program_id}/uredi", response_class=HTMLResponse)
def program_edit_page(request: Request, program_id: int):
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
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    for name in db.delete_program(program_id):
        _unlink_media(name)
    return RedirectResponse("/treninzi?ok=Trening+je+obrisan.", status_code=303)


@app.post("/treninzi/{program_id}/items")
async def item_add(request: Request, program_id: int, title: str = Form(...),
                   body: str = Form(""), media: UploadFile | None = File(None)):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    if db.get_program(program_id) is None:
        raise HTTPException(status_code=404)
    from urllib.parse import quote
    try:
        media_name, media_kind = _save_media(media)
    except ValueError as e:
        return RedirectResponse(f"/treninzi/{program_id}/uredi?error={quote(str(e))}",
                                status_code=303)
    db.add_item(program_id, title.strip() or "Vježba", body.strip() or None,
                media_name, media_kind)
    return RedirectResponse(f"/treninzi/{program_id}/uredi", status_code=303)


@app.post("/treninzi/{program_id}/items/{item_id}/edit")
async def item_edit(request: Request, program_id: int, item_id: int,
                    title: str = Form(...), body: str = Form(""),
                    media: UploadFile | None = File(None)):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    from urllib.parse import quote
    try:
        media_name, media_kind = _save_media(media)
    except ValueError as e:
        return RedirectResponse(f"/treninzi/{program_id}/uredi?error={quote(str(e))}",
                                status_code=303)
    old = db.update_item(item_id, title.strip() or "Vježba", body.strip() or None,
                         media_name, media_kind)
    if media_name:
        _unlink_media(old)
    return RedirectResponse(f"/treninzi/{program_id}/uredi?ok=Spremljeno.", status_code=303)


@app.post("/treninzi/{program_id}/items/{item_id}/delete")
def item_delete(request: Request, program_id: int, item_id: int):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    _unlink_media(db.delete_item(item_id))
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
    """Programme media — auth-gated, never a public static mount: a custom
    programme is personal content, visible to its client and the trainer only."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=404)
    p = db.media_owner_program(name)
    if p is None:
        raise HTTPException(status_code=404)
    if not user.is_trainer and (not _has_online(user)
                                or not db.client_can_view(p, user.id)):
        raise HTTPException(status_code=403, detail="Ovo nije tvoj sadržaj.")
    if storage.r2_enabled():
        # auth just passed — hand out a short-lived direct link; the bytes
        # come from Cloudflare, the bucket itself stays private
        return RedirectResponse(storage.presigned_url(name), status_code=307)
    path = storage.local_path(name)
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type=_MEDIA_TYPES.get(path.suffix.lower()))


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
    # the online tiers by name for the forms' Paket selects: the QMove
    # cards' titles, the gym owner's text (renaming a card renames the tier)
    return templates.TemplateResponse(request, "clanarine.html", _ctx(
        request, user, copy_texts=texts, rows=db.memberships_overview(),
        plans=PLAN_TYPES, plan_labels=PLAN_LABELS, today=config.today(),
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
           f"sljedeća {m.next_payment.strftime('%-d.%-m.%Y.')}")
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
