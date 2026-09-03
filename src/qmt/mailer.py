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


def send_new_user_notice(owner_email: str, new_email: str, full_name: str | None) -> bool:
    """Tell the owner a new user just VERIFIED (mojimakrosi's pattern — sign-up
    alone can be a bot row that never opens its inbox)."""
    import html as _html

    # Escaped: name and email are attacker-controlled and land in the owner's
    # mail client as HTML.
    who = _html.escape(f"{full_name} <{new_email}>" if full_name else new_email)
    return _send(owner_email, "Novi korisnik — QMT", f"""
      <div style="font-family:sans-serif;max-width:480px">
        <h2>Quality Movement Training</h2>
        <p>Novi korisnik je potvrdio račun:</p>
        <p style="font-size:16px;font-weight:700">{who}</p>
        <p style="color:#777;font-size:13px">Članarinu mu dodijeli na stranici Članarine.</p>
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
