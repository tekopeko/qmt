"""Transactional email via Resend — the only file that talks to it (lazy httpx).

Every sender returns False when no API key is configured, so callers fall back
to showing the link on-page (dev only — app.py refuses that path in prod).
"""

from __future__ import annotations

from . import config


def _send(to: str, subject: str, html: str) -> bool:
    if not config.email_enabled():
        return False
    import httpx

    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
        json={"from": config.EMAIL_FROM, "to": [to], "subject": subject, "html": html},
        timeout=15,
    )
    return r.status_code in (200, 201)


def _button(url: str, label: str) -> str:
    return (f'<a href="{url}" style="display:inline-block;background:#e10600;color:#fff;'
            f'padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:600">{label}</a>')


def send_verification_email(to: str, link: str) -> bool:
    return _send(to, "Potvrdi svoj QMT račun", f"""
      <div style="font-family:sans-serif;max-width:480px">
        <h2>Quality Movement Training</h2>
        <p>Bok! Potvrdi da je ovo tvoja adresa i račun je spreman:</p>
        <p>{_button(link, "Potvrdi email")}</p>
        <p style="color:#777;font-size:13px">Link vrijedi 24 sata. Ako se nisi ti
        registrirao/la, slobodno ignoriraj ovu poruku.</p>
      </div>""")


def send_password_reset_email(to: str, link: str) -> bool:
    return _send(to, "Nova lozinka za QMT", f"""
      <div style="font-family:sans-serif;max-width:480px">
        <h2>Quality Movement Training</h2>
        <p>Zatražena je promjena lozinke za tvoj račun:</p>
        <p>{_button(link, "Postavi novu lozinku")}</p>
        <p style="color:#777;font-size:13px">Link vrijedi 1 sat i može se iskoristiti
        jednom. Ako nisi ti tražio/la promjenu, ignoriraj poruku — lozinka ostaje ista.</p>
      </div>""")
