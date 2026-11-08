"""Payment gateway adapters and notification validation (FR-PAY-03, FR-PAY-07)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from typing import Any, Protocol

import httpx2


class GatewayUnavailable(RuntimeError):
    """The gateway is unconfigured or the payment request failed."""


class GatewayAdapter(Protocol):
    """Provider-independent creation and verification of gateway requests."""

    def create_payment(self, order_id: str, amount_idr: int) -> str:
        """Create a payment and return its redirect URL."""
        ...

    def verify_notification(self, payload: dict[str, Any]) -> bool:
        """Check notification authenticity without reading application data."""
        ...


def parse_gross_amount(amount: str) -> int:
    """Parse decimal-text integer rupiah after signature verification (FR-PAY-03)."""
    if not isinstance(amount, str) or not re.fullmatch(r"[0-9]+(?:\.0{1,2})?", amount):
        raise ValueError("gross_amount must be non-negative integer rupiah")
    return int(amount.split(".", 1)[0])


def normalize_status(status: str, fraud_status: str = "") -> str:
    """Normalize gateway statuses without granting entitlement to unknown events."""
    if status == "settlement" or (status == "capture" and fraud_status == "accept"):
        return "settlement"
    if status in {"pending", "authorize"} or (status == "capture" and fraud_status == "challenge"):
        return "pending"
    if status in {"deny", "cancel", "failure"}:
        return "fail"
    if status == "expire":
        return "expire"
    return "ignored"


class FakeGatewayAdapter:
    """In-memory gateway that returns a preconfigured payment URL."""

    def __init__(
        self,
        payment_url: str = "https://gateway.example.test/payment",
        *,
        signature_valid: bool = True,
    ) -> None:
        self.payment_url = payment_url
        self.signature_valid = signature_valid
        self.calls: list[dict[str, Any]] = []

    def create_payment(self, order_id: str, amount_idr: int) -> str:
        """Record the order and return the fake redirect URL."""
        self.calls.append({"order_id": order_id, "amount_idr": amount_idr})
        return self.payment_url

    def verify_notification(self, payload: dict[str, Any]) -> bool:
        """Return the configured signature decision."""
        return self.signature_valid


class MidtransAdapter:
    """Snap client with sandbox default and signed notification verification."""

    def __init__(
        self,
        *,
        server_key: str,
        is_production: bool = False,
        transport: Any = None,
        timeout_s: float = 30,
    ) -> None:
        if not is_production and server_key.startswith("Mid-server-"):
            raise ValueError("Production server key cannot be used in sandbox")
        self.server_key = server_key
        self.is_production = is_production
        self.base_url = (
            "https://app.midtrans.com/snap/v1/transactions"
            if is_production
            else "https://app.sandbox.midtrans.com/snap/v1/transactions"
        )
        self.transport = transport
        self.timeout_s = timeout_s

    def verify_notification(self, payload: dict[str, Any]) -> bool:
        """Verify SHA512 against exact received string fields in constant time."""
        if not self.server_key or not isinstance(payload, dict):
            return False
        fields = [
            payload.get(name)
            for name in ("order_id", "status_code", "gross_amount", "signature_key")
        ]
        if any(not isinstance(value, str) or not value for value in fields):
            return False
        order_id, status_code, gross_amount, signature = fields
        digest = hashlib.sha512(
            (order_id + status_code + gross_amount + self.server_key).encode("utf-8")
        ).hexdigest()
        try:
            return hmac.compare_digest(digest, signature)
        except TypeError:
            return False

    def create_payment(self, order_id: str, amount_idr: int) -> str:
        """Create a Snap payment with an explicit 24-hour expiry."""
        if not self.server_key:
            raise GatewayUnavailable("Payment gateway is not configured")
        if not isinstance(order_id, str) or not re.fullmatch(r"[A-Za-z0-9._~-]{1,50}", order_id):
            raise ValueError("Invalid order ID")
        if isinstance(amount_idr, bool) or not isinstance(amount_idr, int) or amount_idr <= 0:
            raise ValueError("amount_idr must be a positive integer")
        token = base64.b64encode(f"{self.server_key}:".encode("utf-8")).decode("ascii")
        body = {
            "transaction_details": {"order_id": order_id, "gross_amount": amount_idr},
            "expiry": {"duration": 24, "unit": "hour"},
        }
        try:
            with httpx2.Client(transport=self.transport, timeout=self.timeout_s) as client:
                response = client.post(
                    self.base_url, headers={"Authorization": f"Basic {token}"}, json=body
                )
                response.raise_for_status()
                url = response.json()["redirect_url"]
                if not isinstance(url, str) or not url:
                    raise ValueError("Missing redirect URL")
                return url
        except (httpx2.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise GatewayUnavailable("Payment gateway failed") from exc
