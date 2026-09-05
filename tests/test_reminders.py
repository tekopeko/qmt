"""Reminder pass: who gets mailed, exactly once per occasion, retried on failure."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import pytest

from qmt import auth, config, db, reminders
from qmt.models import Base, Booking, Membership, User


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    yield


@pytest.fixture
def outbox(monkeypatch):
    """Email capture: enabled mailer whose sends can be told to fail."""
    sent = {"clanarina": [], "termin": [], "fail": False}
    monkeypatch.setattr(config, "email_enabled", lambda: True)

    def fake_membership(to, plan_label, dospijece):
        if sent["fail"]:
            return False
        sent["clanarina"].append((to, plan_label, dospijece))
        return True

    def fake_termin(to, termini):
        if sent["fail"]:
            return False
        sent["termin"].append((to, termini))
        return True

    monkeypatch.setattr(reminders.mailer, "send_membership_reminder", fake_membership)
    monkeypatch.setattr(reminders.mailer, "send_termin_reminder", fake_termin)
    return sent


def make_user(email: str) -> int:
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    return u.id


def expiring_membership(uid: int, plan: str = "grupni", days_to_dospijece: int = 2) -> None:
    """A plan whose dospijeće is `days_to_dospijece` days away."""
    db.record_payment(uid, plan)
    with db.session_scope() as s:
        m = s.query(Membership).filter_by(user_id=uid, plan=plan).one()
        m.next_payment = config.today() + timedelta(
            days=days_to_dospijece - Membership.GRACE_DAYS)


def session_tomorrow(hour: int = 18) -> int:
    at = datetime.combine(config.today() + timedelta(days=1),
                          datetime.min.time(), tzinfo=config.TZ).replace(hour=hour)
    return db.add_oneoff_session("Grupni trening", at, 60, 8, None)


def test_membership_reminder_once_per_cycle(outbox):
    ivan = make_user("ivan@test.local")
    expiring_membership(ivan, days_to_dospijece=2)

    assert reminders.run_once()["clanarina"] == 1
    assert outbox["clanarina"][0][0] == "ivan@test.local"
    assert reminders.run_once()["clanarina"] == 0          # same cycle: silent

    # a new uplata starts a new cycle — when IT nears dospijeće, remind again
    db.record_payment(ivan, "grupni")
    with db.session_scope() as s:
        m = s.query(Membership).filter_by(user_id=ivan, plan="grupni").one()
        m.next_payment = config.today() - timedelta(days=Membership.GRACE_DAYS - 1)
    assert reminders.run_once()["clanarina"] == 1


def test_membership_outside_window_is_silent(outbox):
    ivan = make_user("ivan@test.local")
    expiring_membership(ivan, days_to_dospijece=15)        # far away
    ana = make_user("ana@test.local")
    expiring_membership(ana, days_to_dospijece=-2)         # already lapsed
    assert reminders.run_once()["clanarina"] == 0


def test_termin_reminder_day_before_once(outbox):
    ivan = make_user("ivan@test.local")
    s1 = session_tomorrow(18)
    with db.session_scope() as s:
        s.add(Booking(user_id=ivan, session_id=s1))

    assert reminders.run_once()["termin"] == 1
    to, termini = outbox["termin"][0]
    assert to == "ivan@test.local" and len(termini) == 1
    assert "Grupni trening" in termini[0][0]
    assert reminders.run_once()["termin"] == 0             # not twice

    # a second booking made AFTER the first pass still gets reminded
    s2 = session_tomorrow(19)
    with db.session_scope() as s:
        s.add(Booking(user_id=ivan, session_id=s2))
    assert reminders.run_once()["termin"] == 1
    assert len(outbox["termin"][1][1]) == 1                # only the new one


def test_canceled_session_not_reminded(outbox):
    ivan = make_user("ivan@test.local")
    sid = session_tomorrow()
    with db.session_scope() as s:
        s.add(Booking(user_id=ivan, session_id=sid))
    db.set_session_canceled(sid, True)
    assert reminders.run_once()["termin"] == 0


def test_failed_send_is_retried(outbox):
    ivan = make_user("ivan@test.local")
    expiring_membership(ivan)
    outbox["fail"] = True
    assert reminders.run_once() == {"clanarina": 0, "termin": 0, "failed": 1}
    outbox["fail"] = False
    assert reminders.run_once()["clanarina"] == 1          # claim was released


def test_disabled_mailer_claims_nothing(outbox, monkeypatch):
    monkeypatch.setattr(config, "email_enabled", lambda: False)
    ivan = make_user("ivan@test.local")
    expiring_membership(ivan)
    assert reminders.run_once() == {"clanarina": 0, "termin": 0, "failed": 0}
    # nothing was claimed, so enabling email later still sends
    monkeypatch.setattr(config, "email_enabled", lambda: True)
    assert reminders.run_once()["clanarina"] == 1
