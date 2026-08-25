"""FastAPI routes: login/signup, the week calendar, booking, trainer admin.

Small enough that auth is a helper called at the top of each route rather than
middleware — if this grows routes the way mojimakrosi did, promote it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .. import auth, config, db

app = FastAPI(title="QMT")
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, https_only=config.IS_PROD)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

WEEKDAYS = ["Ponedjeljak", "Utorak", "Srijeda", "Četvrtak", "Petak", "Subota", "Nedjelja"]
WEEKDAYS_SHORT = ["pon", "uto", "sri", "čet", "pet", "sub", "ned"]


def current_user(request: Request):
    uid = request.session.get("user_id")
    return db.get_user(uid) if uid else None


def _ctx(request: Request, user, **extra):
    return {"request": request, "user": user, "weekdays_short": WEEKDAYS_SHORT,
            "mojimakrosi_url": config.MOJIMAKROSI_URL, **extra}


# ---------- auth ----------

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", _ctx(request, None))


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    u = db.get_user_by_email(email)
    if u is None or not auth.verify_password(password, u.password_hash):
        return RedirectResponse("/login?error=Pogrešan+email+ili+lozinka.", status_code=303)
    request.session["user_id"] = u.id
    return RedirectResponse("/", status_code=303)


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
        u = db.create_user(email, name, auth.hash_password(password))
    except Exception:
        # check-then-insert race: two simultaneous signups for the same email —
        # the unique constraint wins, the loser gets the same message as above.
        return RedirectResponse("/signup?error=Račun+već+postoji+—+prijavi+se.", status_code=303)
    request.session["user_id"] = u.id
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------- calendar ----------

def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


@app.get("/", response_class=HTMLResponse)
def calendar(request: Request, week: str | None = None):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    today = config.today()
    try:
        monday = _monday_of(date.fromisoformat(week)) if week else _monday_of(today)
    except ValueError:
        monday = _monday_of(today)               # garbage ?week= falls back to now
    db.materialize_week(monday)

    start = datetime(monday.year, monday.month, monday.day, tzinfo=config.TZ)
    rows = db.sessions_between(start, start + timedelta(days=7))
    mine = db.user_booking_ids(user.id, [r["session"].id for r in rows])
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
            })
        # key is "sessions", NOT "items" — Jinja resolves dict.items to the builtin method
        days.append({"date": d, "name": WEEKDAYS[i], "is_today": d == today, "sessions": sessions})

    return templates.TemplateResponse(request, "calendar.html", _ctx(
        request, user,
        days=days, monday=monday,
        prev_week=(monday - timedelta(days=7)).isoformat(),
        next_week=(monday + timedelta(days=7)).isoformat(),
        upcoming=db.my_upcoming(user.id),
        tz=config.TZ,
    ))


def _redirect_back(week: str, error: str | None = None, ok: str | None = None) -> RedirectResponse:
    """Back to the calendar, on the right week, with feedback visible.
    The separator depends on whether `back` already has a query string —
    "/&error=..." is not a query string and the message silently vanishes."""
    from urllib.parse import quote

    back = f"/?week={week}" if week else "/"
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


# ---------- trainer admin ----------

def _require_trainer(request: Request):
    user = current_user(request)
    if user is None:
        return None, RedirectResponse("/login", status_code=303)
    if not user.is_trainer:
        raise HTTPException(status_code=403, detail="Samo trener")
    return user, None


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "admin.html", _ctx(
        request, user, templates_list=db.list_templates(), weekdays=WEEKDAYS,
    ))


@app.post("/admin/templates")
def add_template(request: Request, title: str = Form(...), weekday: int = Form(...),
                 time: str = Form(...), duration_min: int = Form(60),
                 capacity: int = Form(8), note: str = Form("")):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    try:
        h, m = map(int, time.split(":"))
        assert 0 <= weekday <= 6 and 0 <= h <= 23 and 0 <= m <= 59
    except (ValueError, AssertionError):
        return RedirectResponse("/admin?error=Neispravan+dan+ili+vrijeme.", status_code=303)
    db.add_template(title.strip(), weekday, h * 60 + m,
                    max(15, min(240, duration_min)), max(1, min(40, capacity)),
                    note.strip() or None)
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
        time_value=f"{t.start_min // 60:02d}:{t.start_min % 60:02d}",
    ))


@app.post("/admin/templates/{template_id}/edit")
def edit_template(request: Request, template_id: int, title: str = Form(...),
                  weekday: int = Form(...), time: str = Form(...),
                  duration_min: int = Form(60), capacity: int = Form(8),
                  note: str = Form("")):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    try:
        start_min = _parse_slot(weekday, time)
    except ValueError:
        return RedirectResponse(f"/admin/templates/{template_id}?error=Neispravan+dan+ili+vrijeme.",
                                status_code=303)
    db.update_template(template_id, title.strip(), weekday, start_min,
                       max(15, min(240, duration_min)), max(1, min(40, capacity)),
                       note.strip() or None)
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
               capacity: int = Form(1), note: str = Form("")):
    """One-off session outside the weekly timetable (extra 1:1, workshop...)."""
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    try:
        d = date.fromisoformat(day)
        h, m = map(int, time.split(":"))
        starts = datetime(d.year, d.month, d.day, h, m, tzinfo=config.TZ)
        assert starts > datetime.now(config.TZ)
    except (ValueError, AssertionError):
        return RedirectResponse("/admin?error=Neispravan+datum+ili+vrijeme.", status_code=303)
    db.add_oneoff_session(title.strip(), starts, max(15, min(240, duration_min)),
                          max(1, min(40, capacity)), note.strip() or None)
    return RedirectResponse(f"/?week={(d - timedelta(days=d.weekday())).isoformat()}", status_code=303)


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


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
