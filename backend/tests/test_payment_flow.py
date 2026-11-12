"""Payment routes and entitlement transitions with an offline gateway (FR-PAY-01..08)."""

import hashlib
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from test_tax_crud_trace_quota import _auth

from app.db import SessionLocal
from app.models import PaymentEvent, SubscriptionOrder, User
from app.security import now_utc
from app.services.payments import _is_production, get_gateway_adapter

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


def _notice(
    order_id,
    status="settlement",
    amount="25000.00",
    fraud="accept",
    status_code="200",
    server_key=SERVER_KEY,
):
    """FR-PAY-03: independently compute the exact signed text."""
    payload = {
        "order_id": order_id,
        "status_code": status_code,
        "gross_amount": amount,
        "transaction_status": status,
        "fraud_status": fraud,
    }
    payload["signature_key"] = hashlib.sha512(
        (order_id + status_code + amount + server_key).encode()
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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("false", False),
        pytest.param(None, False, id="unset"),
        ("", False),
    ],
)
def test_is_production_flag(monkeypatch, raw, expected):
    """MIDTRANS_IS_PRODUCTION is true only for the lowercase word true."""
    if raw is None:
        monkeypatch.delenv("MIDTRANS_IS_PRODUCTION", raising=False)
    else:
        monkeypatch.setenv("MIDTRANS_IS_PRODUCTION", raw)
    assert _is_production() is expected


def test_fr_pay07_production_webhook_unknown_order_is_not_found(client, monkeypatch):
    """FR-PAY-07: a production-shaped key must not turn a signed unknown order into 500."""
    key = "Mid-server-test-not-real"
    monkeypatch.setenv("MIDTRANS_SERVER_KEY", key)
    monkeypatch.setenv("MIDTRANS_IS_PRODUCTION", "true")
    response = client.post(
        "/api/v1/webhooks/payment", json=_notice("missing-order", server_key=key)
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_fr_pay03_settlement_with_non_200_status_code_is_refused(client, fake_gateway):
    """FR-PAY-03: a signed settlement whose status code is not 200 is not stored."""
    _auth(client)
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    order = _order(client)
    response = client.post(
        "/api/v1/webhooks/payment", json=_notice(order["order_id"], status_code="201")
    )
    assert response.status_code == 400, response.text
    assert _user(user_id).paid_flag is False
    with SessionLocal() as db:
        events = db.scalars(
            select(PaymentEvent).where(PaymentEvent.order_id == order["order_id"])
        ).all()
        assert events == []


def test_fr_pay03_rejected_settlement_does_not_block_later_success(client, fake_gateway):
    """FR-PAY-03: refusing a non-200 settlement leaves a later 200 settlement able to activate."""
    _auth(client)
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    order = _order(client)
    refused = client.post(
        "/api/v1/webhooks/payment", json=_notice(order["order_id"], status_code="201")
    )
    assert refused.status_code == 400, refused.text
    assert _user(user_id).paid_flag is False
    before = now_utc()
    accepted = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"]))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["idempotent_duplicate"] is False
    user = _user(user_id)
    assert user.paid_flag is True
    first_until = user.valid_until_utc
    assert before + timedelta(days=30) <= first_until <= now_utc() + timedelta(days=30)
    duplicate = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"]))
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["idempotent_duplicate"] is True
    assert _user(user_id).valid_until_utc == first_until


def test_fr_pay01_stuck_pending_without_url_becomes_fail_not_expire(client, fake_gateway):
    """FR-PAY-01: an unexpired empty payment URL older than a minute is failed, not expired."""
    _auth(client)
    order = _order(client)
    with SessionLocal() as db:
        row = db.scalar(select(SubscriptionOrder).where(SubscriptionOrder.id == order["order_id"]))
        row.payment_url = ""
        row.created_at = now_utc() - timedelta(minutes=2)
        assert row.expires_at_utc > now_utc()
        db.commit()
    again = client.post("/api/v1/subscriptions/orders", json={"plan_id": "monthly_25k"})
    assert again.status_code == 201, again.text
    assert again.json()["order_id"] != order["order_id"]
    with SessionLocal() as db:
        old = db.scalar(select(SubscriptionOrder).where(SubscriptionOrder.id == order["order_id"]))
        assert old.status == "fail"


def test_fr_pay03_stores_payload_transaction_time(client, fake_gateway):
    """The notice clock is stored; paid days still start from the receipt time."""
    _auth(client)
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    order = _order(client)
    before = now_utc()
    payload = _notice(order["order_id"])
    payload["transaction_time"] = "2020-01-09 18:27:19"
    response = client.post("/api/v1/webhooks/payment", json=payload)
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        event = db.scalar(select(PaymentEvent).where(PaymentEvent.order_id == order["order_id"]))
        assert event is not None
        # Midtrans sends WIB (UTC+7) without an offset; 18:27:19 WIB is 11:27:19 UTC.
        assert event.transaction_time == datetime(2020, 1, 9, 11, 27, 19)
        assert before <= event.received_at <= now_utc()
    user = _user(user_id)
    assert user.paid_flag is True
    assert before + timedelta(days=30) <= user.valid_until_utc <= now_utc() + timedelta(days=30)


def test_fr_pay03_iso_transaction_time_is_stored(client, fake_gateway):
    """An ISO transaction_time from the notice is stored as naive UTC."""
    _auth(client)
    order = _order(client)
    payload = _notice(order["order_id"], "expire")
    payload["transaction_time"] = "2026-10-18T10:30:00Z"
    response = client.post("/api/v1/webhooks/payment", json=payload)
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        event = db.scalar(select(PaymentEvent).where(PaymentEvent.order_id == order["order_id"]))
        assert event is not None
        assert event.transaction_time == datetime(2026, 10, 18, 10, 30)


def test_fr_pay03_missing_or_unreadable_transaction_time_uses_receipt_time(client, fake_gateway):
    """No usable notice clock keeps today's receipt time and still accepts the event."""
    _auth(client)
    order = _order(client)
    before = now_utc()
    missing = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"], "pending"))
    assert missing.status_code == 200, missing.text
    with SessionLocal() as db:
        event = db.scalar(
            select(PaymentEvent).where(
                PaymentEvent.order_id == order["order_id"],
                PaymentEvent.raw_status == "pending",
            )
        )
        assert event is not None
        assert before <= event.transaction_time <= now_utc()
        assert event.transaction_time == event.received_at
    before_bad = now_utc()
    bad = _notice(order["order_id"], "expire")
    bad["transaction_time"] = "not-a-time"
    response = client.post("/api/v1/webhooks/payment", json=bad)
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        event = db.scalar(
            select(PaymentEvent).where(
                PaymentEvent.order_id == order["order_id"],
                PaymentEvent.raw_status == "expire",
            )
        )
        assert event is not None
        assert before_bad <= event.transaction_time <= now_utc()
        assert event.transaction_time == event.received_at


def test_fr_pay02_list_returns_payment_url_only_while_pending(client, fake_gateway):
    """History includes the pay link only while the order is still pending."""
    _auth(client)
    order = _order(client)
    listed = client.get("/api/v1/subscriptions/orders")
    assert listed.status_code == 200, listed.text
    pending = listed.json()["items"]
    assert pending[0]["order_id"] == order["order_id"]
    assert pending[0]["status"] == "pending"
    assert pending[0]["payment_url"] == order["payment_url"]
    settled = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"]))
    assert settled.status_code == 200, settled.text
    items = client.get("/api/v1/subscriptions/orders").json()["items"]
    assert items[0]["status"] == "settlement"
    assert "payment_url" not in items[0]


def _status_of(order_id):
    with SessionLocal() as db:
        return db.scalar(select(SubscriptionOrder.status).where(SubscriptionOrder.id == order_id))


@pytest.mark.parametrize("first,second", [("expire", "deny"), ("deny", "expire")])
def test_fr_pay05_expire_and_fail_do_not_replace_each_other(client, fake_gateway, first, second):
    """Spec 5.30: the first of expire/fail stays; a later one does not overwrite it."""
    _auth(client)
    order = _order(client)
    for status in (first, second):
        response = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"], status))
        assert response.status_code == 200, response.text
    expected = "expire" if first == "expire" else "fail"
    assert _status_of(order["order_id"]) == expected


@pytest.mark.parametrize("first", ["expire", "deny"])
def test_fr_pay05_settlement_still_wins_after_expire_or_fail(client, fake_gateway, first):
    _auth(client)
    order = _order(client)
    client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"], first))
    response = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"]))
    assert response.status_code == 200, response.text
    assert _status_of(order["order_id"]) == "settlement"


def test_fr_pay03_key_and_production_flag_mismatch_is_503_not_500(client, monkeypatch):
    """A live-looking key with the sandbox flag must not crash the webhook."""
    monkeypatch.setenv("MIDTRANS_SERVER_KEY", "Mid-server-live-looking")
    monkeypatch.setenv("MIDTRANS_IS_PRODUCTION", "false")
    response = client.post("/api/v1/webhooks/payment", json=_notice("any"))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PAYMENT_GATEWAY_UNAVAILABLE"


def test_fr35_order_without_payment_url_is_not_pending(client, fake_gateway):
    """An order with no link (gateway call in flight or crashed) does not show as pending."""
    _auth(client)
    order = _order(client)
    assert client.get("/api/v1/subscriptions/status").json()["subscription_tier"] == "pending"
    with SessionLocal() as db:
        row = db.scalar(select(SubscriptionOrder).where(SubscriptionOrder.id == order["order_id"]))
        row.payment_url = ""
        db.commit()
    assert client.get("/api/v1/subscriptions/status").json()["subscription_tier"] != "pending"


# --- Status API confirmation (spec 5.30, review finding R16-W3) ---


def _event_count(order_id):
    with SessionLocal() as db:
        return len(db.scalars(select(PaymentEvent).where(PaymentEvent.order_id == order_id)).all())


def test_fr_pay03_status_api_agrees_grants_access_once(client, fake_gateway):
    """The Status API is asked once; agreement grants 30 days and a replay adds none."""
    _auth(client)
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    order = _order(client)
    first = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"]))
    assert first.status_code == 200, first.text
    assert first.json() == {"acknowledged": True, "idempotent_duplicate": False}
    assert fake_gateway.status_calls == [order["order_id"]]
    granted = _user(user_id)
    assert granted.paid_flag is True
    replay = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"]))
    assert replay.status_code == 200, replay.text
    assert replay.json()["idempotent_duplicate"] is True
    assert _user(user_id).valid_until_utc == granted.valid_until_utc
    # A replay does not need a second gateway call.
    assert fake_gateway.status_calls == [order["order_id"]]
    assert _event_count(order["order_id"]) == 1


@pytest.mark.parametrize(
    "remote",
    [
        {"transaction_status": "pending", "status_code": "201"},
        {"transaction_status": "expire", "status_code": "407"},
        {"transaction_status": "capture", "fraud_status": "challenge"},
        {"transaction_status": "settlement", "gross_amount": "1000.00"},
        {"transaction_status": "settlement", "status_code": "201"},
    ],
)
def test_fr_pay03_status_api_disagrees_grants_nothing(client, fake_gateway, remote):
    """A signed settlement that Midtrans does not confirm is not stored and grants nothing."""
    _auth(client)
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    order = _order(client)
    fake_gateway.script_status(fake_gateway.status_body(order["order_id"], **remote))
    response = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"]))
    assert response.status_code == 409, response.text
    assert response.json() == {
        "error": {
            "code": "PAYMENT_STATUS_MISMATCH",
            "message": "Status pembayaran di Midtrans tidak sesuai dengan notifikasi.",
        }
    }
    assert _user(user_id).paid_flag is False
    assert _status_of(order["order_id"]) == "pending"
    assert _event_count(order["order_id"]) == 0


def test_fr_pay03_status_api_unreachable_is_retryable_and_then_succeeds(client, fake_gateway):
    """Unreachable Status API: 503, nothing stored; the same notice later settles once."""
    from app.payments.adapter import GatewayUnavailable

    _auth(client)
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    order = _order(client)
    fake_gateway.script_status(GatewayUnavailable("timeout"))
    failed = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"]))
    assert failed.status_code == 503, failed.text
    assert failed.json() == {
        "error": {
            "code": "PAYMENT_GATEWAY_UNAVAILABLE",
            "message": "Layanan pembayaran belum tersedia. Coba lagi nanti.",
        }
    }
    assert _user(user_id).paid_flag is False
    assert _status_of(order["order_id"]) == "pending"
    assert _event_count(order["order_id"]) == 0
    retried = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"]))
    assert retried.status_code == 200, retried.text
    assert retried.json()["idempotent_duplicate"] is False
    assert _user(user_id).paid_flag is True
    assert _status_of(order["order_id"]) == "settlement"
    assert fake_gateway.status_calls == [order["order_id"]] * 2


def test_fr_pay03_status_api_unreadable_body_is_retryable(client, fake_gateway):
    """A Status API body without a readable amount is treated as an error, not a mismatch."""
    _auth(client)
    order = _order(client)
    fake_gateway.script_status({"order_id": order["order_id"], "status_code": "200"})
    response = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"]))
    assert response.status_code == 503, response.text
    assert _status_of(order["order_id"]) == "pending"


def test_fr_pay03_non_settlement_notices_skip_status_api(client, fake_gateway):
    """Pending, expire and fail notices never grant access, so they need no Status API call."""
    _auth(client)
    order = _order(client)
    for status in ("pending", "expire"):
        response = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"], status))
        assert response.status_code == 200, response.text
    assert fake_gateway.status_calls == []


def test_fr_pay05_later_expire_does_not_reverse_confirmed_settlement(client, fake_gateway):
    _auth(client)
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    order = _order(client)
    assert (
        client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"])).status_code == 200
    )
    for status in ("pending", "expire", "deny"):
        response = client.post("/api/v1/webhooks/payment", json=_notice(order["order_id"], status))
        assert response.status_code == 200, response.text
    assert _status_of(order["order_id"]) == "settlement"
    assert _user(user_id).paid_flag is True


@pytest.mark.parametrize(
    ("raw", "host"),
    [
        ("true", "https://api.midtrans.com/v2"),
        ("TRUE", "https://api.midtrans.com/v2"),
        ("1", "https://api.sandbox.midtrans.com/v2"),
        ("false", "https://api.sandbox.midtrans.com/v2"),
        ("", "https://api.sandbox.midtrans.com/v2"),
        (None, "https://api.sandbox.midtrans.com/v2"),
    ],
)
def test_status_api_host_follows_is_production_flag(monkeypatch, raw, host):
    """Spec 5.30: the Status API host follows _is_production(), so true in any case is production."""
    monkeypatch.setenv("MIDTRANS_SERVER_KEY", "Mid-server-not-real")
    if raw is None:
        monkeypatch.delenv("MIDTRANS_IS_PRODUCTION", raising=False)
    else:
        monkeypatch.setenv("MIDTRANS_IS_PRODUCTION", raw)
    if host.startswith("https://api.sandbox"):
        # A production-shaped key is refused by the sandbox adapter; use a sandbox key.
        monkeypatch.setenv("MIDTRANS_SERVER_KEY", "SB-Mid-server-not-real")
    assert get_gateway_adapter().status_base_url == host


def _settle_in_database(order_id, user_id):
    """Settle the order the way a concurrent notification would, and commit."""
    with SessionLocal() as db:
        order = db.scalar(select(SubscriptionOrder).where(SubscriptionOrder.id == order_id))
        owner = db.scalar(select(User).where(User.id == user_id))
        instant = now_utc()
        order.status = "settlement"
        owner.paid_flag = True
        owner.valid_until_utc = max(instant, owner.valid_until_utc or instant) + timedelta(days=30)
        db.add(
            PaymentEvent(
                id="payevt_concurrent",
                order_id=order_id,
                user_id=user_id,
                status="settlement",
                raw_status="settlement",
                gross_amount_idr=25_000,
                transaction_time=instant,
                received_at=instant,
            )
        )
        db.commit()


def test_fr_pay03_settlement_during_status_call_is_not_granted_twice(client, fake_gateway):
    """A settlement committed while the Status API call is in flight is not granted again."""
    _auth(client)
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    order = _order(client)
    order_id = order["order_id"]

    def concurrent_settlement(called_order_id):
        _settle_in_database(called_order_id, user_id)
        return fake_gateway.status_body(called_order_id)

    fake_gateway.script_status(concurrent_settlement)
    response = client.post("/api/v1/webhooks/payment", json=_notice(order_id))
    assert response.status_code == 200, response.text
    assert response.json() == {"acknowledged": True, "idempotent_duplicate": True}
    assert fake_gateway.status_calls == [order_id]
    assert _event_count(order_id) == 1
    granted = _user(user_id)
    assert granted.paid_flag is True
    # Exactly one 30-day grant: the one made inside the Status call.
    assert granted.valid_until_utc <= now_utc() + timedelta(days=30, minutes=1)
    assert _status_of(order_id) == "settlement"
