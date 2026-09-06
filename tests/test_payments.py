"""Stripe subscriptions: signed webhooks grant months idempotently; checkout
and portal hand off; nothing works without configuration."""

from __future__ import annotations

import json
import os
import time
from datetime import timedelta
from decimal import Decimal

os.environ["DATABASE_URL"] = "postgresql+psycopg:///qmt_test"
os.environ["ALLOWED_EMAILS"] = "ivan@test.local,ana@test.local"
os.environ["OWNER_EMAIL"] = "trener@test.local"

import pytest
import stripe
from fastapi.testclient import TestClient

from qmt import auth, config, db, payments
from qmt.models import Base, Membership, Payment
from qmt.web.app import app

SECRET = "whsec_test_secret"


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    payments._price_cache = (0.0, {})
    yield


@pytest.fixture
def stripe_on(monkeypatch):
    """Configured Stripe with the network calls stubbed out."""
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(config, "STRIPE_PRICES", {**{p: "" for p in config.STRIPE_PRICES},
                                                  "grupni": "price_grupni", "online": "price_online"})
    subs: dict[str, dict] = {}
    calls = {"customers": 0, "checkouts": [], "portals": 0}

    monkeypatch.setattr(stripe.Subscription, "retrieve",
                        staticmethod(lambda sid, **kw: subs[sid]))
    monkeypatch.setattr(stripe.Price, "retrieve", staticmethod(
        lambda pid, **kw: {"unit_amount": 5000, "currency": "eur", "recurring": {"interval": "month"}}))

    def customer_create(**kw):
        calls["customers"] += 1
        return {"id": f"cus_{calls['customers']}"}
    monkeypatch.setattr(stripe.Customer, "create", staticmethod(customer_create))

    def checkout_create(**kw):
        calls["checkouts"].append(kw)
        return {"url": "https://checkout.stripe.com/c/pay/test"}
    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(checkout_create))

    def portal_create(**kw):
        calls["portals"] += 1
        return {"url": "https://billing.stripe.com/p/session/test"}
    monkeypatch.setattr(stripe.billing_portal.Session, "create", staticmethod(portal_create))
    return {"subs": subs, "calls": calls}


def make_user(email: str) -> int:
    from datetime import date
    u = db.create_user(email, email.split("@")[0], auth.hash_password("lozinka123"))
    db.mark_email_verified(email)
    db.update_profile(u.id, email.split("@")[0], "Test", date(1990, 1, 1), "")
    return u.id


def client_for(email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"email": email, "password": "lozinka123"}, follow_redirects=False)
    assert r.status_code == 303, "login failed"
    return c


def signed(event: dict, secret: str = SECRET) -> tuple[bytes, str]:
    """A payload + Stripe-Signature header exactly as Stripe would send it."""
    payload = json.dumps(event).encode()
    ts = int(time.time())
    sig = stripe.WebhookSignature._compute_signature(f"{ts}.{payload.decode()}", secret)
    return payload, f"t={ts},v1={sig}"


def invoice_paid(inv_id: str, sub_id: str, cents: int = 5000, new_shape: bool = True) -> dict:
    inv = {"id": inv_id, "amount_paid": cents,
           "lines": {"data": [{"price": {"id": "price_grupni"}}]}}
    if new_shape:      # 2025+ API: subscription under parent.subscription_details
        inv["parent"] = {"subscription_details": {"subscription": sub_id}}
    else:              # classic shape
        inv["subscription"] = sub_id
    return {"type": "invoice.paid", "data": {"object": inv}}


def post_event(event: dict, secret: str = SECRET):
    payload, header = signed(event, secret)
    return TestClient(app).post("/stripe/webhook", content=payload,
                                headers={"stripe-signature": header,
                                         "content-type": "application/json"})


# ---------- webhook ----------

def test_webhook_refuses_bad_signature_and_unconfigured(stripe_on, monkeypatch):
    ivan = make_user("ivan@test.local")
    stripe_on["subs"]["sub_1"] = {"id": "sub_1", "metadata": {"qmt_user_id": str(ivan), "qmt_plan": "grupni"}}
    r = post_event(invoice_paid("in_1", "sub_1"), secret="whsec_wrong")
    assert r.status_code == 400
    assert db.active_plan_kinds(ivan) == set()           # nothing granted

    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")
    assert post_event(invoice_paid("in_1", "sub_1")).status_code == 503


def test_invoice_paid_grants_a_month_exactly_once(stripe_on):
    ivan = make_user("ivan@test.local")
    stripe_on["subs"]["sub_1"] = {"id": "sub_1", "metadata": {"qmt_user_id": str(ivan), "qmt_plan": "grupni"}}

    r = post_event(invoice_paid("in_1", "sub_1"))
    assert r.status_code == 200 and r.text.startswith("paid")
    assert db.active_plan_kinds(ivan) == {"grupni"}
    m = db.memberships_for(ivan)[0]
    assert m.stripe_subscription_id == "sub_1" and m.auto_renew
    first_due = m.next_payment
    with db.session_scope() as s:
        p = s.query(Payment).one()
        assert (p.method, p.amount_eur, p.stripe_invoice_id) == ("stripe", Decimal("50.00"), "in_1")

    # Stripe redelivers — same invoice id → no second month, no second ledger row
    assert post_event(invoice_paid("in_1", "sub_1")).status_code == 200
    assert db.memberships_for(ivan)[0].next_payment == first_due
    with db.session_scope() as s:
        assert s.query(Payment).count() == 1

    # next month's invoice (classic API shape) extends from the due date
    assert post_event(invoice_paid("in_2", "sub_1", new_shape=False)).status_code == 200
    m = db.memberships_for(ivan)[0]
    assert m.next_payment > first_due
    assert m.next_payment == db._add_month(first_due)


def test_cash_plan_taken_over_by_subscription_extends_from_due_date(stripe_on):
    ivan = make_user("ivan@test.local")
    db.record_payment(ivan, "grupni")                    # cash today
    due = db.memberships_for(ivan)[0].next_payment
    stripe_on["subs"]["sub_9"] = {"id": "sub_9", "metadata": {"qmt_user_id": str(ivan), "qmt_plan": "grupni"}}
    post_event(invoice_paid("in_9", "sub_9"))
    m = db.memberships_for(ivan)[0]
    assert m.next_payment == db._add_month(due)          # not shortened
    assert m.stripe_subscription_id == "sub_9"


def test_cancel_and_delete_keep_paid_time_but_stop_renewing(stripe_on):
    ivan = make_user("ivan@test.local")
    stripe_on["subs"]["sub_1"] = {"id": "sub_1", "metadata": {"qmt_user_id": str(ivan), "qmt_plan": "grupni"}}
    post_event(invoice_paid("in_1", "sub_1"))

    r = post_event({"type": "customer.subscription.updated",
                    "data": {"object": {"id": "sub_1", "cancel_at_period_end": True}}})
    assert r.text == "updated"
    m = db.memberships_for(ivan)[0]
    assert m.cancel_at_period_end and not m.auto_renew
    page = client_for("ivan@test.local").get("/profil").text
    assert "otkazana" in page

    r = post_event({"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_1"}}})
    assert r.text == "deleted"
    m = db.memberships_for(ivan)[0]
    assert m.stripe_subscription_id is None
    assert db.active_plan_kinds(ivan) == {"grupni"}      # the paid month stays valid


def test_unknown_user_or_plan_is_ignored(stripe_on):
    stripe_on["subs"]["sub_x"] = {"id": "sub_x", "metadata": {"qmt_user_id": "999", "qmt_plan": "grupni"}}
    r = post_event(invoice_paid("in_x", "sub_x"))
    assert r.status_code == 200 and r.text.startswith("ignored")
    ivan = make_user("ivan@test.local")
    stripe_on["subs"]["sub_y"] = {"id": "sub_y", "metadata": {"qmt_user_id": str(ivan), "qmt_plan": "nema"}}
    ev = invoice_paid("in_y", "sub_y")
    ev["data"]["object"]["lines"]["data"][0]["price"]["id"] = "price_unknown"
    r = post_event(ev)
    assert r.text.startswith("ignored")
    with db.session_scope() as s:
        assert s.query(Payment).count() == 0 and s.query(Membership).count() == 0


# ---------- checkout / portal / cjenik ----------

def test_checkout_creates_one_customer_and_hands_off(stripe_on):
    ivan = make_user("ivan@test.local")
    c = client_for("ivan@test.local")
    r = c.post("/placanje/grupni", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("https://checkout.stripe.com/")
    kw = stripe_on["calls"]["checkouts"][0]
    assert kw["mode"] == "subscription"
    assert kw["subscription_data"]["metadata"] == {"qmt_user_id": str(ivan), "qmt_plan": "grupni"}
    assert kw["line_items"] == [{"price": "price_grupni", "quantity": 1}]
    assert db.get_user(ivan).stripe_customer_id == "cus_1"

    c.post("/placanje/online", follow_redirects=False)   # second plan reuses the customer
    assert stripe_on["calls"]["customers"] == 1
    assert stripe_on["calls"]["checkouts"][1]["customer"] == "cus_1"

    # a plan without a price is not sellable; a stranger is sent to login
    assert "platiti+karticom" in c.post("/placanje/prehrana", follow_redirects=False).headers["location"]
    assert TestClient(app).post("/placanje/grupni", follow_redirects=False).headers["location"].startswith("/login")


def test_no_double_subscription_and_portal_needs_a_customer(stripe_on):
    ivan = make_user("ivan@test.local")
    stripe_on["subs"]["sub_1"] = {"id": "sub_1", "metadata": {"qmt_user_id": str(ivan), "qmt_plan": "grupni"}}
    post_event(invoice_paid("in_1", "sub_1"))
    c = client_for("ivan@test.local")
    assert "postoji" in c.post("/placanje/grupni", follow_redirects=False).headers["location"]

    # never checked out through us → no customer → no portal
    assert "/profil?error" in c.post("/placanje/portal", follow_redirects=False).headers["location"]
    db.set_stripe_customer(ivan, "cus_7")
    r = c.post("/placanje/portal", follow_redirects=False)
    assert r.headers["location"].startswith("https://billing.stripe.com/")


def test_cjenik_shows_stripe_prices_or_na_upit(stripe_on, monkeypatch):
    make_user("ivan@test.local")
    r = client_for("ivan@test.local").get("/cjenik")
    assert r.status_code == 200
    page = r.text
    assert "50,00 €" in page and "Pretplati se karticom" in page
    assert "na upit" in page                               # plans without a price

    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")   # unconfigured: exactly today's page
    payments._price_cache = (0.0, {})
    r = client_for("ivan@test.local").get("/cjenik")
    assert r.status_code == 200, r.text[-400:]
    page = r.text
    assert "50,00 €" not in page and "Pretplati se" not in page
    assert "Za upis se javi treneru" in page              # the cash-only copy


def test_disabled_stripe_touches_nothing(monkeypatch):
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")
    assert not payments.enabled()
    assert payments.sellable_plans() == set() and payments.price_table() == {}
