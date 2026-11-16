"""FR-PAY-01: Snap return URLs use the configured frontend origin."""

import json

import httpx2
import pytest

from app.config.settings import frontend_base_url
from app.payments.adapter import MidtransAdapter
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
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://example.test/")
    monkeypatch.setenv("MIDTRANS_SERVER_KEY", "SB-Mid-server-fake")
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx2.Response(200, json={"redirect_url": "https://gateway.example.test/pay"})

    adapter = get_gateway_adapter()
    assert isinstance(adapter, MidtransAdapter)
    adapter.transport = httpx2.MockTransport(handler)
    adapter.create_payment("ord_1", 25000)
    assert seen["callbacks"] == {
        "finish": "https://example.test/langganan/kembali",
        "error": "https://example.test/langganan/kembali",
    }
