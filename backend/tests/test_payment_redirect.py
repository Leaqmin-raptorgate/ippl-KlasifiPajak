"""FR-PAY-01: Snap return URLs use the configured frontend origin."""

import hashlib
import json
import logging

import httpx2
import pytest
from sqlalchemy import select
from test_tax_crud_trace_quota import _auth

from app.config.settings import frontend_base_url
from app.db import SessionLocal
from app.models import SubscriptionOrder, User
from app.payments.adapter import FakeGatewayAdapter, MidtransAdapter
from app.services import payments
from app.services.payments import get_gateway_adapter


def test_local_default_and_trailing_slash(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
    assert frontend_base_url() == "http://127.0.0.1:5173"
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://example.test/")
    assert frontend_base_url() == "https://example.test"


@pytest.mark.parametrize(
    "value", ["", "ftp://example.test", "http://localhost:5173", "http://127.0.0.1:5173"]
)
def test_production_rejects_missing_invalid_or_local_url(monkeypatch, value):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FRONTEND_BASE_URL", value)
    with pytest.raises(ValueError):
        frontend_base_url()


def test_order_request_includes_configured_callbacks(monkeypatch):
    monkeypatch.setenv("MIDTRANS_SERVER_KEY", "SB-Mid-server-fake")
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx2.Response(200, json={"redirect_url": "https://gateway.example.test/pay"})

    adapter = get_gateway_adapter()
    assert isinstance(adapter, MidtransAdapter)
    adapter.transport = httpx2.MockTransport(handler)
    adapter.create_payment("ord_1", 25000, "https://example.test/langganan/kembali")
    assert seen["callbacks"] == {
        "finish": "https://example.test/langganan/kembali",
        "error": "https://example.test/langganan/kembali",
    }


def test_midtrans_adapter_requires_return_url():
    adapter = MidtransAdapter(server_key="SB-Mid-server-fake")
    with pytest.raises(ValueError, match="return_url is required"):
        adapter.create_payment("ord_1", 25000)
    with pytest.raises(ValueError, match="return_url is required"):
        adapter.create_payment("ord_1", 25000, "")


def test_create_order_invalid_frontend_url_logs_and_skips_insert(client, monkeypatch, caplog):
    monkeypatch.setenv("JWT_SECRET", "test-production-jwt-secret-at-least-32-bytes")
    _auth(client)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
    with caplog.at_level(logging.ERROR, logger="app.services.payments"):
        response = client.post("/api/v1/subscriptions/orders", json={"plan_id": "monthly_25k"})
    assert response.status_code == 503, response.text
    assert response.json() == {
        "error": {
            "code": "PAYMENT_GATEWAY_UNAVAILABLE",
            "message": "Pembayaran belum tersedia. Coba lagi.",
        }
    }
    assert "FRONTEND_BASE_URL is invalid or missing" in caplog.text
    with SessionLocal() as db:
        assert db.scalars(select(SubscriptionOrder)).all() == []


def test_webhook_settlement_succeeds_in_production_without_frontend_base_url(client, monkeypatch):
    _auth(client)
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    with monkeypatch.context() as mp:
        fake = FakeGatewayAdapter()
        mp.setattr(payments, "get_gateway_adapter", lambda: fake)
        order_resp = client.post("/api/v1/subscriptions/orders", json={"plan_id": "monthly_25k"})
        assert order_resp.status_code == 201, order_resp.text
        order_id = order_resp.json()["order_id"]

    key = "Mid-server-prod-test"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
    monkeypatch.setenv("MIDTRANS_IS_PRODUCTION", "true")
    monkeypatch.setenv("MIDTRANS_SERVER_KEY", key)
    real_client = httpx2.Client

    def status_handler(request):
        assert str(request.url) == f"https://api.midtrans.com/v2/{order_id}/status"
        return httpx2.Response(
            200,
            json={
                "order_id": order_id,
                "status_code": "200",
                "transaction_status": "settlement",
                "gross_amount": "25000.00",
                "fraud_status": "accept",
            },
        )

    monkeypatch.setattr(
        httpx2,
        "Client",
        lambda **kwargs: real_client(
            **{**kwargs, "transport": httpx2.MockTransport(status_handler)}
        ),
    )
    payload = {
        "order_id": order_id,
        "status_code": "200",
        "gross_amount": "25000.00",
        "transaction_status": "settlement",
        "fraud_status": "accept",
    }
    payload["signature_key"] = hashlib.sha512(f"{order_id}20025000.00{key}".encode()).hexdigest()
    response = client.post("/api/v1/webhooks/payment", json=payload)
    assert response.status_code == 200, response.text
    assert response.json() == {"acknowledged": True, "idempotent_duplicate": False}
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.id == user_id))
        order = db.scalar(select(SubscriptionOrder).where(SubscriptionOrder.id == order_id))
        assert user is not None and user.paid_flag is True
        assert order is not None and order.status == "settlement"
