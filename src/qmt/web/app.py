"""FastAPI routes: login/signup, the week calendar, booking, trainer admin.

Small enough that auth is a helper called at the top of each route rather than
middleware — if this grows routes the way mojimakrosi did, promote it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .. import auth, config, db, mailer, upitnik
from ..models import (FEELING_LABELS, PAYMENT_METHODS, PLAN_ABBR, PLAN_LABELS,
                      PLAN_TYPES, SESSION_KINDS)

app = FastAPI(title="QMT")
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, https_only=config.IS_PROD)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

WEEKDAYS = ["Ponedjeljak", "Utorak", "Srijeda", "Četvrtak", "Petak", "Subota", "Nedjelja"]
WEEKDAYS_SHORT = ["pon", "uto", "sri", "čet", "pet", "sub", "ned"]

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


def _ctx(request: Request, user, **extra):
    return {"request": request, "user": user, "weekdays_short": WEEKDAYS_SHORT,
            "mojimakrosi_url": config.MOJIMAKROSI_URL,
            "max_media_mb": config.MAX_MEDIA_MB,
            "show_online": _has_online(user),
            "plan_links": PLAN_LINKS,
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
        return RedirectResponse(
            "/signup?error=Slanje+emaila+nije+uspjelo+—+javi+se+treneru.", status_code=303)
    return templates.TemplateResponse(request, "verify_sent.html", _ctx(
        request, None, email=email, dev_link=None if sent else link))


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


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
    return templates.TemplateResponse(request, "landing.html", _ctx(
        request, user, gallery=gallery,
        my_plans=db.active_plan_kinds(user.id) if user else set()))


@app.get("/cjenik", response_class=HTMLResponse)
def cjenik(request: Request):
    """Plan pricing — public; the future card-payment entry point. Prices are
    placeholders until the owner supplies real ones."""
    user = current_user(request)
    return templates.TemplateResponse(request, "cjenik.html", _ctx(
        request, user, plans=PLAN_TYPES, plan_labels=PLAN_LABELS,
        my_plans=db.active_plan_kinds(user.id) if user else set()))


@app.get("/raspored", response_class=HTMLResponse)
def calendar(request: Request, week: str | None = None):
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/raspored')}", status_code=303)

    today = config.today()
    try:
        monday = _monday_of(date.fromisoformat(week)) if week else _monday_of(today)
    except ValueError:
        monday = _monday_of(today)               # garbage ?week= falls back to now
    db.materialize_week(monday)

    start = datetime(monday.year, monday.month, monday.day, tzinfo=config.TZ)
    rows = db.sessions_between(start, start + timedelta(days=7))
    mine = db.user_booking_ids(user.id, [r["session"].id for r in rows])
    my_plans = db.active_plan_kinds(user.id)
    now = datetime.now(config.TZ)

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
            cutoff = sess.starts_at - timedelta(hours=config.CANCEL_CUTOFF_HOURS)
            sessions.append({
                "id": sess.id, "title": sess.title,
                "time": local.strftime("%H:%M"),
                "end": (local + timedelta(minutes=sess.duration_min)).strftime("%H:%M"),
                "booked": r["booked"], "capacity": sess.capacity,
                "full": r["booked"] >= sess.capacity,
                "canceled": sess.canceled,
                "past": sess.starts_at <= now,
                "mine": sess.id in mine,
                "can_cancel": sess.id in mine and now < cutoff,
                "one_on_one": sess.capacity == 1,
                # may this client book this kind? (trainer never books via UI)
                "allowed": user.is_trainer or sess.kind in my_plans,
            })
        # key is "sessions", NOT "items" — Jinja resolves dict.items to the builtin method
        days.append({"date": d, "name": WEEKDAYS[i], "is_today": d == today, "sessions": sessions})

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
            "time": local.strftime("%H:%M"),
            "end": (local + timedelta(minutes=sess.duration_min)).strftime("%H:%M"),
            "title": sess.title,
            "canceled": sess.canceled,
            "one_on_one": sess.capacity == 1,
        })

    return templates.TemplateResponse(request, "calendar.html", _ctx(
        request, user,
        days=days, monday=monday,
        prev_week=(monday - timedelta(days=7)).isoformat(),
        next_week=(monday + timedelta(days=7)).isoformat(),
        mine_days=mine_days,
        memberships=[{"label": PLAN_LABELS.get(m.plan, m.plan),
                      "next_payment": m.next_payment, "dospijece": m.dospijece,
                      "active": m.is_active(today)}
                     for m in db.memberships_for(user.id)],
    ))


def _redirect_back(week: str, error: str | None = None, ok: str | None = None) -> RedirectResponse:
    """Back to the calendar, on the right week, with feedback visible.
    The separator depends on whether `back` already has a query string —
    "/&error=..." is not a query string and the message silently vanishes."""
    from urllib.parse import quote

    back = f"/raspored?week={week}" if week else "/raspored"
    for key, val in (("error", error), ("ok", ok)):
        if val:
            back += ("&" if "?" in back else "?") + f"{key}=" + quote(val)
    return RedirectResponse(back, status_code=303)


@app.post("/book/{session_id}")
def book(request: Request, session_id: int, week: str = Form("")):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        db.book(user.id, session_id)
    except db.BookingError as e:
        return _redirect_back(week, str(e))
    return _redirect_back(week, ok="Rezervirano ✓")


@app.post("/cancel/{session_id}")
def cancel(request: Request, session_id: int, week: str = Form("")):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        db.cancel_booking(user.id, session_id)
    except db.BookingError as e:
        return _redirect_back(week, str(e))
    return _redirect_back(week, ok="Rezervacija je otkazana.")


@app.get("/auth/verify")
def auth_verify(request: Request, token: str = ""):
    email = auth.read_verify_token(token)
    if email is None:
        return RedirectResponse(
            "/login?error=Link+nije+valjan+ili+je+istekao+—+prijavi+se+za+novi.", status_code=303)
    newly = db.mark_email_verified(email)
    if newly is None:
        return RedirectResponse("/login?error=Račun+ne+postoji+—+registriraj+se.", status_code=303)
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
    today = config.today()
    # "how long am I paid up for": the plan admits booking until dospijeće
    # (next payment + the grace week), so that date is the honest expiry.
    memberships = [{"label": PLAN_LABELS.get(m.plan, m.plan),
                    "plan": m.plan,
                    "paid_on": m.paid_on,
                    "next_payment": m.next_payment,
                    "dospijece": m.dospijece,
                    "active": m.is_active(today),
                    "days_left": (m.dospijece - today).days}
                   for m in db.memberships_for(user.id)]
    payments = [{"paid_on": p.paid_on, "label": PLAN_LABELS.get(p.plan, p.plan),
                 "method": PAYMENT_METHODS.get(p.method, p.method),
                 "amount": p.amount_eur}
                for p in db.payments_for(user.id)]
    return templates.TemplateResponse(request, "profil.html", _ctx(
        request, user,
        first_login="dopuni" in request.query_params,
        memberships=memberships, payments=payments,
        show_amounts=any(p["amount"] is not None for p in payments)))


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

def _render_karton(request: Request, viewer, subject, own: bool):
    import json

    onboarding = db.get_onboarding(subject.id)
    answers = json.loads(onboarding.answers) if onboarding else {}
    today = config.today()
    born = subject.birth_date
    age = (today.year - born.year - ((today.month, today.day) < (born.month, born.day))
           if born else None)
    return templates.TemplateResponse(request, "karton.html", _ctx(
        request, viewer, subject=subject, own=own, age=age,
        can_upitnik=own and _has_online(subject),
        onboarding=onboarding, answers=answers,
        questions=upitnik.QUESTIONS, levels=upitnik.LEVELS, goals=upitnik.GOALS,
        max_score=upitnik.MAX_SCORE,
        logs=db.training_logs(subject.id),
        pending=db.pending_feedback(subject.id) if own else [],
        feelings=FEELING_LABELS,
        upcoming=db.my_upcoming(subject.id),
        history=db.booking_history(subject.id),
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
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(8)}{suffix}"
    dest = config.MEDIA_DIR / name
    limit = config.MAX_MEDIA_MB * 1024 * 1024
    total = 0
    with open(dest, "wb") as f:
        while chunk := upload.file.read(1 << 20):
            total += len(chunk)
            if total > limit:
                f.close()
                dest.unlink(missing_ok=True)
                raise ValueError(f"Datoteka je veća od {config.MAX_MEDIA_MB} MB.")
            f.write(chunk)
    if total == 0:
        dest.unlink(missing_ok=True)
        return None, None
    return name, _MEDIA_KINDS[suffix]


def _unlink_media(name: str | None) -> None:
    if name:
        (config.MEDIA_DIR / name).unlink(missing_ok=True)


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
    path = config.MEDIA_DIR / name
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
    return templates.TemplateResponse(request, "clanarine.html", _ctx(
        request, user, rows=db.memberships_overview(),
        plans=PLAN_TYPES, plan_labels=PLAN_LABELS, today=config.today()))


@app.post("/clanarine/{user_id}/uplata")
def clanarine_uplata(request: Request, user_id: int, plan: str = Form(...),
                     method: str = Form("gotovina")):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    if plan not in PLAN_TYPES or method not in ("gotovina", "kartica"):
        raise HTTPException(status_code=400, detail="Nepoznat plan.")
    with db.session_scope() as s:
        target = s.get(db.User, user_id)
    if target is None:
        raise HTTPException(status_code=404)
    m = db.record_payment(user_id, plan, method)
    from urllib.parse import quote
    msg = (f"{PLAN_LABELS[plan]}: uplata evidentirana — sljedeća "
           f"{m.next_payment.strftime('%-d.%-m.%Y.')}")
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
