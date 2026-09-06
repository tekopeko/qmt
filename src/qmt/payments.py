"""Card payments — Stripe subscriptions, one per plan, renewing monthly.

The contract with the rest of the app is deliberately thin:

- /cjenik shows Stripe's own Price amounts (cached), "na upit" without them.
- "Pretplati se" creates a Checkout Session in subscription mode; the user id
  and plan ride along as SUBSCRIPTION metadata, so every invoice Stripe ever
  raises for it can be traced back without trusting anything client-side.
- Access is granted ONLY by the signed `invoice.paid` webhook, which calls the
  same `db.record_payment` as cash — the membership dates do the gating, exactly
  as before. Never by the success redirect: a client can reach that URL
  without paying.
- Cancellation is the client's, in Stripe's portal. `subscription.deleted`
  clears the link; the month already paid stays valid and the plan lapses on
  dospijeće by itself — "when it lapses, access closes", as the owner asked.

Stripe's API changes shape between versions (an invoice's subscription lives
at `invoice.subscription` before 2025 and `invoice.parent.subscription_details`
after). The helpers below read both, and the webhook re-fetches the
Subscription for its metadata rather than trusting the invoice's copy.
"""

from __future__ import annotations

import time
from decimal import Decimal

from . import config, db
from .models import PLAN_LABELS, PLAN_TYPES

_price_cache: tuple[float, dict] = (0.0, {})
PRICE_TTL_S = 600


def enabled() -> bool:
    return config.stripe_enabled()


def _stripe():
    import stripe

    stripe.api_key = config.STRIPE_SECRET_KEY
    return stripe


def price_ids(plan: str) -> dict[int | None, str]:
    """{sessions: price_id} for a plan — {None: id} for a flat monthly plan,
    {8: id, 12: id, 16: id} for a tiered one (only tiers that have a Price)."""
    if plan in config.STRIPE_TIER_PRICES:
        return {n: pid for n, pid in config.STRIPE_TIER_PRICES[plan].items() if pid}
    pid = config.STRIPE_PRICES.get(plan, "")
    return {None: pid} if pid else {}


def sellable_plans() -> set[str]:
    """Plans with at least one configured Stripe Price — the only ones that
    get a button."""
    if not enabled():
        return set()
    return {p for p in PLAN_TYPES if price_ids(p)}


# ---------- prices for /cjenik ----------

def price_table() -> dict[str, dict]:
    """Per sellable plan, from Stripe, cached for PRICE_TTL_S:
      flat:   {"amount": Decimal, "currency": "EUR"}
      tiered: {"currency": "EUR", "tiers": [{"sessions": 8, "amount": Decimal}, ...]}
    Any failure yields the last good table (or {}) — the page then shows the
    reference price, never an error."""
    global _price_cache
    if not enabled():
        return {}
    ts, table = _price_cache
    if table and time.time() - ts < PRICE_TTL_S:
        return table
    try:
        st = _stripe()
        table = {}
        for plan in sellable_plans():
            ids = price_ids(plan)
            if None in ids:
                pr = st.Price.retrieve(ids[None])
                table[plan] = {"amount": Decimal(pr["unit_amount"]) / 100,
                               "currency": str(pr["currency"]).upper()}
            else:
                tiers, cur = [], "EUR"
                for n in sorted(ids):
                    pr = st.Price.retrieve(ids[n])
                    cur = str(pr["currency"]).upper()
                    tiers.append({"sessions": n, "amount": Decimal(pr["unit_amount"]) / 100})
                table[plan] = {"currency": cur, "tiers": tiers}
        _price_cache = (time.time(), table)
        return table
    except Exception:
        return _price_cache[1]


# ---------- checkout + portal ----------

def ensure_customer(user) -> str:
    """The user's Stripe Customer id, creating one on first use so every
    subscription and the portal hang off the same record."""
    if user.stripe_customer_id:
        return user.stripe_customer_id
    st = _stripe()
    c = st.Customer.create(email=user.email, name=user.full_name or None,
                           metadata={"qmt_user_id": str(user.id)})
    db.set_stripe_customer(user.id, c["id"])
    return c["id"]


def checkout_url(user, plan: str, sessions: int | None = None) -> str:
    """A Checkout Session URL for one plan's monthly subscription; `sessions`
    picks the tier (8/12/16) for a tiered plan and is ignored for flat ones."""
    ids = price_ids(plan)
    if not enabled() or not ids:
        raise ValueError("Ovaj plan se ne može platiti karticom.")
    key = None if None in ids else sessions
    if key not in ids:
        raise ValueError("Odaberi broj treninga.")
    st = _stripe()
    base = config.PUBLIC_BASE_URL
    meta = {"qmt_user_id": str(user.id), "qmt_plan": plan,
            "qmt_sessions": str(key or "")}
    session = st.checkout.Session.create(
        mode="subscription",
        customer=ensure_customer(user),
        line_items=[{"price": ids[key], "quantity": 1}],
        success_url=f"{base}/profil?ok=Pretplata+je+aktivirana+—+članarina+se+obnavlja+automatski.",
        cancel_url=f"{base}/cjenik",
        locale="hr",
        metadata=meta,
        subscription_data={"metadata": meta},
    )
    return session["url"]


def portal_url(user) -> str:
    """Stripe's hosted portal: change card, cancel, see invoices."""
    st = _stripe()
    session = st.billing_portal.Session.create(
        customer=ensure_customer(user), return_url=f"{config.PUBLIC_BASE_URL}/profil")
    return session["url"]


# ---------- webhook ----------

def parse_event(payload: bytes, sig_header: str):
    """Verified event or raises — the signature is the whole security model."""
    return _stripe().Webhook.construct_event(payload, sig_header, config.STRIPE_WEBHOOK_SECRET)


def _as_dict(obj) -> dict:
    """Plain dict from a StripeObject, a dict, or nothing. stripe-python 15
    made StripeObject NOT a mapping — dict(obj) raises — so metadata must go
    through to_dict()."""
    if obj is None:
        return {}
    if hasattr(obj, "to_dict"):
        return dict(obj.to_dict())
    if isinstance(obj, dict):
        return dict(obj)
    return {}


def _get(obj, *path, default=None):
    """Tolerant nested read across dicts / StripeObjects."""
    cur = obj
    for key in path:
        if cur is None:
            return default
        try:
            cur = cur[key] if not isinstance(key, int) else cur[key]
        except (KeyError, IndexError, TypeError):
            try:
                cur = getattr(cur, key)
            except AttributeError:
                return default
    return default if cur is None else cur


def _invoice_subscription_id(inv) -> str | None:
    # 2025+ API shape first, then the classic one
    sub = _get(inv, "parent", "subscription_details", "subscription") or _get(inv, "subscription")
    if isinstance(sub, str):
        return sub
    return _get(sub, "id")


def _plan_from(meta: dict | None, price_id: str | None) -> tuple[str | None, int | None]:
    """(plan, sessions) from subscription metadata, falling back to the price
    id — so a subscription created by hand in the dashboard still resolves."""
    meta = meta or {}
    plan = meta.get("qmt_plan")
    if plan in PLAN_TYPES:
        try:
            n = int(meta.get("qmt_sessions") or 0)
        except ValueError:
            n = 0
        return plan, (n or None)
    for p in PLAN_TYPES:
        for n, pid in price_ids(p).items():
            if pid == price_id:
                return p, n
    return None, None


def handle_event(event) -> str:
    """Apply one verified event; returns a short outcome for logs/tests.
    Unknown types are ignored — Stripe only needs a 200."""
    kind = _get(event, "type", default="")
    obj = _get(event, "data", "object")

    if kind == "invoice.paid":
        sub_id = _invoice_subscription_id(obj)
        if not sub_id:
            return "ignored: no subscription on invoice"
        sub = _stripe().Subscription.retrieve(sub_id)
        meta = _as_dict(_get(sub, "metadata"))
        try:
            user_id = int(meta.get("qmt_user_id", ""))
        except ValueError:
            return "ignored: no qmt_user_id"
        price_id = _get(obj, "lines", "data", 0, "price", "id") or \
            _get(obj, "lines", "data", 0, "pricing", "price_details", "price")
        plan, sessions = _plan_from(meta, price_id)
        if plan is None:
            return "ignored: unknown plan"
        if db.get_user(user_id) is None:
            return "ignored: unknown user"
        cents = _get(obj, "amount_paid", default=0) or 0
        db.record_payment(user_id, plan, method="stripe",
                          amount_eur=Decimal(cents) / 100,
                          stripe_invoice_id=_get(obj, "id"),
                          stripe_subscription_id=sub_id,
                          sessions_per_cycle=sessions)
        return f"paid: {PLAN_LABELS.get(plan, plan)} for user {user_id}"

    if kind == "customer.subscription.updated":
        sub_id = _get(obj, "id")
        flag = bool(_get(obj, "cancel_at_period_end", default=False))
        return "updated" if db.set_subscription_cancelling(sub_id, flag) else "ignored: unknown subscription"

    if kind == "customer.subscription.deleted":
        return "deleted" if db.clear_subscription(_get(obj, "id")) else "ignored: unknown subscription"

    return f"ignored: {kind}"
