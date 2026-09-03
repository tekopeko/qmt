"""Email verification + password reset flows."""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import pytest
from fastapi.testclient import TestClient

from qmt import auth, db
from qmt.models import Base
from qmt.web.app import app


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    yield


def signup(c, email="ivan@test.local"):
    return c.post("/signup", data={"name": "Ivan", "email": email,
                                   "password": "lozinka123"}, follow_redirects=False)


def test_unverified_cannot_log_in_and_verify_link_fixes_it():
    c = TestClient(app)
    r = signup(c)
    assert "Link (dev)" in r.text or "Provjeri email" in r.text

    # correct password, unverified -> bounced back to the verify page, no session
    r = c.post("/login", data={"email": "ivan@test.local", "password": "lozinka123"},
               follow_redirects=False)
    assert r.status_code == 200 and "Provjeri" in r.text or "Link (dev)" in r.text
    assert TestClient(app).get("/raspored", follow_redirects=False).status_code == 303

    from urllib.parse import unquote
    token = auth.make_verify_token("ivan@test.local")
    r = c.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert "potvrđen" in unquote(r.headers["location"])

    r = c.post("/login", data={"email": "ivan@test.local", "password": "lozinka123"},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/profil?dopuni=1"  # fresh signup -> complete the profile first


def test_garbage_verify_token_is_rejected():
    c = TestClient(app)
    r = c.get("/auth/verify?token=nije-token", follow_redirects=False)
    assert "error" in r.headers["location"]


def test_password_reset_roundtrip_and_single_use():
    c = TestClient(app)
    signup(c)
    db.mark_email_verified("ivan@test.local")
    u = db.get_user_by_email("ivan@test.local")
    token = auth.make_reset_token(u.email, u.password_hash)

    from urllib.parse import unquote
    r = c.post("/reset", data={"token": token, "password": "novalozinka1"},
               follow_redirects=False)
    assert "promijenjena" in unquote(r.headers["location"])

    # old password dead, new one works
    r = c.post("/login", data={"email": "ivan@test.local", "password": "lozinka123"},
               follow_redirects=False)
    assert "error" in r.headers["location"]
    r = c.post("/login", data={"email": "ivan@test.local", "password": "novalozinka1"},
               follow_redirects=False)
    assert r.headers["location"] == "/profil?dopuni=1"  # signup-fresh account, profile not yet filled

    # the SAME token again must be dead (marker changed with the hash)
    r = c.post("/reset", data={"token": token, "password": "trecalozinka2"},
               follow_redirects=False)
    from urllib.parse import unquote as _uq
    assert "iskorišten" in _uq(r.headers["location"]) or "error" in r.headers["location"]


def test_forgot_does_not_reveal_whether_account_exists():
    c = TestClient(app)
    a = c.post("/forgot", data={"email": "nepostoji@test.local"})
    b_resp = c.post("/forgot", data={"email": "ivan@test.local"})
    assert a.status_code == b_resp.status_code == 200


def test_owner_notified_once_on_first_verification(monkeypatch):
    from qmt import mailer

    sent = []
    monkeypatch.setattr(mailer, "send_new_user_notice",
                        lambda owner, email, name: sent.append((owner, email, name)) or True)

    c = TestClient(app)
    signup(c)
    token = auth.make_verify_token("ivan@test.local")
    c.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert sent == [("trener@test.local", "ivan@test.local", "Ivan")]

    # a re-clicked link verifies nothing new -> no second notice
    c.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert len(sent) == 1


def test_owner_verifying_own_account_sends_no_notice(monkeypatch):
    from qmt import mailer

    sent = []
    monkeypatch.setattr(mailer, "send_new_user_notice",
                        lambda *a: sent.append(a) or True)

    # the owner's address bypasses the allowlist by design
    c = TestClient(app)
    c.post("/signup", data={"name": "T", "email": "trener@test.local",
                            "password": "lozinka123"}, follow_redirects=False)
    token = auth.make_verify_token("trener@test.local")
    c.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert sent == []


def test_notice_failure_never_blocks_verification(monkeypatch):
    from qmt import mailer

    def boom(*a):
        raise RuntimeError("resend down")

    monkeypatch.setattr(mailer, "send_new_user_notice", boom)
    c = TestClient(app)
    signup(c)
    token = auth.make_verify_token("ivan@test.local")
    r = c.get(f"/auth/verify?token={token}", follow_redirects=False)
    from urllib.parse import unquote
    assert "potvrđen" in unquote(r.headers["location"])   # verified regardless
