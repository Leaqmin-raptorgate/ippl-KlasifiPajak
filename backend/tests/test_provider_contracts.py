"""Offline provider boundaries and classification gates (FR-12, FR-PAY-03)."""

import hashlib

import pytest


@pytest.fixture(autouse=True)
def fresh_database():
    """These protocol checks do not use storage or network providers."""
    yield


def test_fr_pay03_signature_uses_original_decimal_text():
    """FR-PAY-03: the signed amount retains its two decimal places."""
    from app.payments.adapter import MidtransAdapter

    key = "fake-sandbox-server-key"
    payload = {"order_id": "order-test", "status_code": "200", "gross_amount": "25000.00"}
    payload["signature_key"] = hashlib.sha512(
        b"order-test20025000.00fake-sandbox-server-key"
    ).hexdigest()
    adapter = MidtransAdapter(server_key=key)
    assert adapter.verify_notification(payload) is True
    assert adapter.verify_notification({**payload, "gross_amount": "25000"}) is False
    assert adapter.verify_notification({**payload, "signature_key": "wrong"}) is False


@pytest.mark.parametrize(
    "status,fraud,expected",
    [
        ("settlement", "", "settlement"),
        ("capture", "accept", "settlement"),
        ("capture", "challenge", "pending"),
        ("authorize", "", "pending"),
        ("pending", "", "pending"),
        ("deny", "", "fail"),
        ("cancel", "", "fail"),
        ("failure", "", "fail"),
        ("expire", "", "expire"),
        ("refund", "", "ignored"),
        ("partial_refund", "", "ignored"),
        ("chargeback", "", "ignored"),
        ("partial_chargeback", "", "ignored"),
        ("future-status", "", "ignored"),
    ],
)
def test_fr_pay03_all_gateway_statuses_are_normalized(status, fraud, expected):
    """FR-PAY-03: refunds and unknown statuses cannot silently grant entitlement."""
    from app.payments.adapter import normalize_status

    assert normalize_status(status, fraud) == expected


@pytest.mark.parametrize("amount", ["1.01", "-1.00", "NaN", "Infinity", "1e4", ""])
def test_fr_pay03_amount_parser_rejects_non_rupiah_values(amount):
    """FR-PAY-03: a signed notification still requires a valid integer-rupiah amount."""
    from app.payments.adapter import parse_gross_amount

    with pytest.raises(ValueError):
        parse_gross_amount(amount)


def test_fr_pay03_amount_parser_preserves_integer_rupiah():
    """FR-PAY-03: the plan price remains integer rupiah after signature verification."""
    from app.payments.adapter import parse_gross_amount

    assert parse_gross_amount("25000.00") == 25_000


def test_fr_pay07_gateway_defaults_to_sandbox_and_rejects_production_key():
    """FR-PAY-07: sandbox mode rejects a known production-key prefix."""
    from app.payments.adapter import MidtransAdapter

    adapter = MidtransAdapter(server_key="SB-Mid-server-fake")
    assert "sandbox.midtrans.com" in adapter.base_url
    with pytest.raises(ValueError):
        MidtransAdapter(server_key="Mid-server-production", is_production=False)
