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

from .. import auth, config, db

app = FastAPI(title="QMT")
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, https_only=config.IS_PROD)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

WEEKDAYS = ["Ponedjeljak", "Utorak", "Srijeda", "Četvrtak", "Petak", "Subota", "Nedjelja"]
WEEKDAYS_SHORT = ["pon", "uto", "sri", "čet", "pet", "sub", "ned"]


def _safe_next(nxt: str | None) -> str:
    """Only same-app paths — a `next` from the query string must never become
    an open redirect to another site ("//evil.com", "https://...")."""
    if nxt and nxt.startswith("/") and not nxt.startswith("//") and ":" not in nxt.split("?")[0]:
        return nxt
    return "/"


def current_user(request: Request):
    uid = request.session.get("user_id")
    return db.get_user(uid) if uid else None


def _ctx(request: Request, user, **extra):
    return {"request": request, "user": user, "weekdays_short": WEEKDAYS_SHORT,
            "mojimakrosi_url": config.MOJIMAKROSI_URL,
            "max_media_mb": config.MAX_MEDIA_MB, **extra}


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
    request.session["user_id"] = u.id
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
    return templates.TemplateResponse(request, "landing.html",
                                      _ctx(request, current_user(request), gallery=gallery))


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
    return RedirectResponse(f"/raspored?week={(d - timedelta(days=d.weekday())).isoformat()}", status_code=303)


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
    """(user, program) if the requester may SEE this programme, else raise."""
    user = current_user(request)
    if user is None:
        return None, None
    p = db.get_program(program_id)
    if p is None:
        raise HTTPException(status_code=404)
    if not user.is_trainer and p.user_id != user.id:
        raise HTTPException(status_code=403, detail="Ovo nije tvoj trening.")
    return user, p


@app.get("/treninzi", response_class=HTMLResponse)
def treninzi(request: Request):
    user = current_user(request)
    if user is None:
        from urllib.parse import quote
        return RedirectResponse(f"/login?next={quote('/treninzi')}", status_code=303)
    if user.is_trainer:
        return templates.TemplateResponse(request, "treninzi_admin.html", _ctx(
            request, user, rows=db.all_programs(), clients=db.list_clients()))
    return templates.TemplateResponse(request, "treninzi.html", _ctx(
        request, user, programs=db.programs_for(user.id)))


@app.post("/treninzi")
def create_program(request: Request, user_id: int = Form(...), title: str = Form(...),
                   intro: str = Form("")):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    title = title.strip()
    if not title:
        return RedirectResponse("/treninzi?error=Naziv+je+obavezan.", status_code=303)
    pid = db.create_program(user_id, title, intro.strip() or None)
    return RedirectResponse(f"/treninzi/{pid}/uredi", status_code=303)


@app.get("/treninzi/{program_id}", response_class=HTMLResponse)
def program_view(request: Request, program_id: int):
    user, p = _program_or_403(request, program_id)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    with db.session_scope() as s:
        client = s.get(db.User, p.user_id)
    return templates.TemplateResponse(request, "trening_view.html", _ctx(
        request, user, p=p, client=client))


@app.get("/treninzi/{program_id}/uredi", response_class=HTMLResponse)
def program_edit_page(request: Request, program_id: int):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    p = db.get_program(program_id)
    if p is None:
        raise HTTPException(status_code=404)
    with db.session_scope() as s:
        client = s.get(db.User, p.user_id)
    return templates.TemplateResponse(request, "trening_edit.html", _ctx(
        request, user, p=p, client=client))


@app.post("/treninzi/{program_id}/edit")
def program_edit(request: Request, program_id: int, title: str = Form(...),
                 intro: str = Form("")):
    user, redirect = _require_trainer(request)
    if redirect:
        return redirect
    db.update_program(program_id, title.strip() or "Trening", intro.strip() or None)
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
    if not user.is_trainer and p.user_id != user.id:
        raise HTTPException(status_code=403, detail="Ovo nije tvoj sadržaj.")
    path = config.MEDIA_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type=_MEDIA_TYPES.get(path.suffix.lower()))


@app.get("/nutricionizam", response_class=HTMLResponse)
def nutricionizam(request: Request):
    return templates.TemplateResponse(request, "nutricionizam.html",
                                      _ctx(request, current_user(request)))


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
