"""FR-PAY-01: pass the configured return URL through order creation."""

from test_tax_crud_trace_quota import _auth

from app.payments.adapter import FakeGatewayAdapter
from app.services import payments


def test_order_passes_configured_return_url_to_fake_gateway(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://example.test/")
    fake = FakeGatewayAdapter()
    monkeypatch.setattr(payments, "get_gateway_adapter", lambda: fake)
    _auth(client)
    response = client.post("/api/v1/subscriptions/orders", json={"plan_id": "monthly_25k"})
    assert response.status_code == 201
    assert fake.calls[0]["return_url"] == "https://example.test/langganan/kembali"
