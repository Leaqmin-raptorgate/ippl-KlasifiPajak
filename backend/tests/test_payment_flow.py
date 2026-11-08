"""Payment routes and entitlement transitions with an offline gateway (FR-PAY-01..08)."""

import hashlib
from datetime import timedelta

import pytest
from sqlalchemy import select
from test_tax_crud_trace_quota import _auth

from app.db import SessionLocal
from app.models import PaymentEvent, User
from app.security import now_utc

SERVER_KEY = "SB-Mid-server-offline-test"


@pytest.fixture
def fake_gateway(monkeypatch):
    """FR-PAY-01: isolate every request from the real gateway."""
    from app.payments.adapter import FakeGatewayAdapter
    from app.services import payments

    fake = FakeGatewayAdapter()
    monkeypatch.setenv("MIDTRANS_SERVER_KEY", SERVER_KEY)
    monkeypatch.setattr(payments, "get_gateway_adapter", lambda: fake)
    return fake


def _order(client):
    response = client.post("/api/v1/subscriptions/orders", json={"plan_id": "monthly_25k"})
    assert response.status_code == 201, response.text
    return response.json()


def _notice(order_id, status="settlement", amount="25000.00", fraud="accept"):
    """FR-PAY-03: independently compute the exact signed text."""
    payload = {
        "order_id": order_id,
        "status_code": "200",
        "gross_amount": amount,
        "transaction_status": status,
        "fraud_status": fraud,
    }
    payload["signature_key"] = hashlib.sha512(
        (order_id + "200" + amount + SERVER_KEY).encode()
    ).hexdigest()
    return payload


def _user(user_id):
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.id == user_id))


def test_fr_pay01_reuses_pending_order_and_lists_only_own_orders(client, fake_gateway):
    _auth(client)
    order = _order(client)
    reused = client.post("/api/v1/subscriptions/orders", json={"plan_id": "monthly_25k"})
    assert reused.status_code == 200
    assert reused.json()["order_id"] == order["order_id"]
    assert order["amount_idr"] == 25_000
    assert order["payment_url"] and order["status"] == "pending"
    history = client.get("/api/v1/subscriptions/orders")
    assert history.status_code == 200
    items = history.json() if isinstance(history.json(), list) else history.json()["items"]
    assert [item["order_id"] for item in items] == [order["order_id"]]
    assert client.get("/api/v1/subscriptions/status").json()["subscription_tier"] == "pending"


def test_fr_pay03_signature_is_checked_before_order_lookup(client, fake_gateway):
    payload = _notice("missing")
    payload["signature_key"] = "invalid"
    response = client.post("/api/v1/webhooks/payment", json=payload)
    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "INVALID_WEBHOOK_SIGNATURE"


def test_fr_pay03_signed_amount_mismatch_cannot_activate(client, fake_gateway):
    _auth(client)
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    order = _order(client)
    response = client.post(
        "/api/v1/webhooks/payment", json=_notice(order["order_id"], amount="25001.00")
    )
    assert response.status_code == 400
    assert _user(user_id).paid_flag is False


def test_fr_pay03_capture_then_duplicate_settlement_adds_days_once(client, fake_gateway):
    _auth(client)
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    order = _order(client)
    before = now_utc()
    captured = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"], "capture"))
    assert captured.status_code == 200, captured.text
    first = _user(user_id)
    assert first.paid_flag is True
    assert before + timedelta(days=30) <= first.valid_until_utc <= now_utc() + timedelta(days=30)
    duplicate = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"]))
    assert duplicate.status_code == 200
    assert _user(user_id).valid_until_utc == first.valid_until_utc
    expired = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"], "expire"))
    assert expired.status_code == 200
    assert _user(user_id).valid_until_utc == first.valid_until_utc


@pytest.mark.parametrize(
    "status", ["refund", "partial_refund", "chargeback", "partial_chargeback", "unknown-new-status"]
)
def test_fr_pay03_ignored_status_is_recorded_without_entitlement(client, fake_gateway, status):
    _auth(client)
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    order = _order(client)
    response = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"], status))
    assert response.status_code == 200, response.text
    assert _user(user_id).paid_flag is False
    with SessionLocal() as db:
        events = db.scalars(select(PaymentEvent).where(PaymentEvent.user_id == user_id)).all()
        assert any(event.raw_status == status for event in events)


def test_fr_pay03_late_settlement_after_expiry_activates(client, fake_gateway):
    _auth(client)
    order = _order(client)
    assert (
        client.post(
            "/api/v1/webhooks/payment", json=_notice(order["order_id"], "expire")
        ).status_code
        == 200
    )
    assert (
        client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"])).status_code == 200
    )
    assert client.get("/api/v1/subscriptions/status").json()["paid_flag"] is True
