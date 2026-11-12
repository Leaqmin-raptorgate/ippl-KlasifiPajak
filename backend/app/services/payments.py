"""Offline-testable payment orders and authenticated webhook processing (FR-PAY-01..08)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.models import PaymentEvent, SubscriptionOrder, User
from app.payments.adapter import (
    GatewayUnavailable,
    MidtransAdapter,
    normalize_status,
    parse_gross_amount,
)
from app.security import iso_utc, new_id, now_utc
from app.services.subscription import PLANS

# Single source of truth for price and duration: /subscriptions/status advertises PLANS.
_PLAN = PLANS[0]
PLAN_ID = _PLAN["plan_id"]
PLAN_AMOUNT_IDR = _PLAN["price_idr"]
PLAN_DURATION = timedelta(days=_PLAN["duration_days"])

# Midtrans sends offset-less transaction_time in WIB (UTC+7). Not zoneinfo: the
# slim image may lack tzdata.
_WIB = timezone(timedelta(hours=7))


def _is_production() -> bool:
    return os.environ.get("MIDTRANS_IS_PRODUCTION", "false").lower() == "true"


def get_gateway_adapter() -> MidtransAdapter:
    """Construct the configured gateway; missing keys fail closed on use."""
    return MidtransAdapter(
        server_key=os.environ.get("MIDTRANS_SERVER_KEY", ""),
        is_production=_is_production(),
    )


def has_pending_order(db: Session, user: User) -> bool:
    """Return whether this account has an unexpired pending payment (FR-35)."""
    return (
        db.scalar(
            select(SubscriptionOrder.id)
            .where(
                SubscriptionOrder.user_id == user.id,
                SubscriptionOrder.status == "pending",
                # A row without a link is still being created, or the process died.
                SubscriptionOrder.payment_url != "",
                SubscriptionOrder.expires_at_utc > now_utc(),
            )
            .limit(1)
        )
        is not None
    )


def _order_out(order: SubscriptionOrder) -> dict:
    body = {
        "order_id": order.id,
        "plan_id": order.plan_id,
        "amount_idr": order.amount_idr,
        "status": order.status,
        "created_at": iso_utc(order.created_at),
        "expires_at_utc": iso_utc(order.expires_at_utc),
    }
    if order.status == "pending":
        body["payment_url"] = order.payment_url
    return body


def create_order(db: Session, user: User, plan_id: str) -> tuple[dict, bool]:
    """Reserve one pending order under the account lock, then call the gateway unlocked."""
    if plan_id != PLAN_ID:
        raise ApiError(422, "INVALID_PLAN", "Paket langganan tidak dikenal.")
    instant = now_utc()
    # Serializes concurrent order creation for the same account without locking
    # any database row while waiting on the external gateway.
    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None:
        raise ApiError(404, "USER_NOT_FOUND", "Pengguna tidak ditemukan.")
    pending = db.scalar(
        select(SubscriptionOrder)
        .where(
            SubscriptionOrder.user_id == user.id,
            SubscriptionOrder.plan_id == plan_id,
            SubscriptionOrder.status == "pending",
        )
        .with_for_update()
    )
    if pending is not None and pending.expires_at_utc > instant:
        if not pending.payment_url and (instant - pending.created_at) > timedelta(minutes=1):
            pending.status = "fail"
            db.flush()
        else:
            result = _order_out(pending)
            db.commit()
            if not result["payment_url"]:
                raise ApiError(
                    503, "PAYMENT_GATEWAY_UNAVAILABLE", "Pembayaran sedang disiapkan. Coba lagi."
                )
            return result, False
    elif pending is not None:
        pending.status = "expire"
        db.flush()
    order = SubscriptionOrder(
        id=new_id("ord_"),
        user_id=user.id,
        plan_id=plan_id,
        amount_idr=PLAN_AMOUNT_IDR,
        status="pending",
        payment_url="",
        created_at=instant,
        expires_at_utc=instant + timedelta(hours=24),
    )
    db.add(order)
    db.commit()
    order_id = order.id
    try:
        payment_url = get_gateway_adapter().create_payment(order_id, PLAN_AMOUNT_IDR)
        if not isinstance(payment_url, str) or not payment_url:
            raise GatewayUnavailable("Missing payment URL")
    except (GatewayUnavailable, ValueError):
        # A failed gateway call never changes entitlement. Release the pending
        # slot so the user can retry immediately.
        row = db.scalar(
            select(SubscriptionOrder).where(SubscriptionOrder.id == order_id).with_for_update()
        )
        if row is not None and row.status == "pending":
            row.status = "fail"
        db.commit()
        raise ApiError(
            503, "PAYMENT_GATEWAY_UNAVAILABLE", "Pembayaran belum tersedia. Coba lagi."
        ) from None
    row = db.scalar(
        select(SubscriptionOrder).where(SubscriptionOrder.id == order_id).with_for_update()
    )
    if row is None or row.user_id != user.id or row.status != "pending":
        db.rollback()
        raise ApiError(503, "PAYMENT_GATEWAY_UNAVAILABLE", "Pembayaran belum tersedia. Coba lagi.")
    row.payment_url = payment_url
    result = _order_out(row)
    db.commit()
    return result, True


def _notice_transaction_time(payload: dict[str, Any], received_at: datetime) -> datetime:
    """Use the notice clock when it parses; otherwise keep the receipt time."""
    parsed = _parse_notice_time(payload.get("transaction_time"))
    return parsed if parsed is not None else received_at


def _parse_notice_time(raw: Any) -> datetime | None:
    """Parse transaction_time to naive UTC. A Midtrans clock has no offset and is WIB."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if "T" in text or text.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    try:
        local = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_WIB)
    except ValueError:
        return None
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def list_orders(db: Session, user: User) -> list[dict]:
    """Return this account's payment history (FR-PAY-02)."""
    rows = db.scalars(
        select(SubscriptionOrder)
        .where(SubscriptionOrder.user_id == user.id)
        .order_by(SubscriptionOrder.created_at.desc(), SubscriptionOrder.id.desc())
    ).all()
    return [_order_out(row) for row in rows]


def _confirm_settlement(order_id: str, amount: int) -> None:
    """Require the Midtrans Status API to agree that this order is settled (spec 5.30).

    The signature does not cover transaction_status, so a signed notice alone is
    not proof of payment. An unreachable or erroring Status API raises 503 so
    Midtrans sends the notice again; a disagreement raises 409. Nothing is stored
    in either case.
    """
    try:
        body = get_gateway_adapter().get_transaction_status(order_id)
        if not isinstance(body, dict):
            raise GatewayUnavailable("Invalid status body")
        remote_status = body.get("transaction_status")
        remote_fraud = body.get("fraud_status", "")
        if not isinstance(remote_status, str) or not isinstance(remote_fraud, str):
            raise GatewayUnavailable("Invalid status body")
        remote_amount = parse_gross_amount(body.get("gross_amount"))
    except (GatewayUnavailable, ValueError):
        raise ApiError(
            503,
            "PAYMENT_GATEWAY_UNAVAILABLE",
            "Layanan pembayaran belum tersedia. Coba lagi nanti.",
        ) from None
    if (
        str(body.get("status_code", "")) != "200"
        or normalize_status(remote_status, remote_fraud) != "settlement"
        or remote_amount != amount
    ):
        raise ApiError(
            409,
            "PAYMENT_STATUS_MISMATCH",
            "Status pembayaran di Midtrans tidak sesuai dengan notifikasi.",
        )


def process_notification(db: Session, payload: dict[str, Any]) -> dict:
    """Verify, record and apply a gateway event atomically (FR-PAY-03)."""
    # Always use the real verifier, even when order creation uses a fake gateway.
    try:
        verifier = MidtransAdapter(
            server_key=os.environ.get("MIDTRANS_SERVER_KEY", ""),
            is_production=_is_production(),
        )
    except ValueError:
        # Key and MIDTRANS_IS_PRODUCTION disagree: a controlled error, so the gateway retries.
        raise ApiError(
            503,
            "PAYMENT_GATEWAY_UNAVAILABLE",
            "Layanan pembayaran belum tersedia. Coba lagi nanti.",
        ) from None
    if not verifier.verify_notification(payload):
        raise ApiError(
            401, "INVALID_WEBHOOK_SIGNATURE", "Tanda tangan webhook pembayaran tidak sah."
        )
    order_id = payload["order_id"]
    status = payload.get("transaction_status")
    fraud_status = payload.get("fraud_status", "")
    if (
        not isinstance(status, str)
        or not status
        or len(status) > 255
        or not isinstance(fraud_status, str)
    ):
        raise ApiError(400, "INVALID_WEBHOOK_STATUS", "Status pembayaran tidak sah.")
    normalized = normalize_status(status, fraud_status)
    confirmed = False
    while True:
        # The preliminary read selects the account lock before the order lock, as
        # in create_order; the locked re-read below is authoritative.
        initial = db.scalar(select(SubscriptionOrder).where(SubscriptionOrder.id == order_id))
        if initial is None:
            raise ApiError(404, "ORDER_NOT_FOUND", "Pesanan tidak ditemukan.")
        owner = None
        if initial.user_id is not None:
            owner = db.scalar(select(User).where(User.id == initial.user_id).with_for_update())
        order = db.scalar(
            select(SubscriptionOrder)
            .where(SubscriptionOrder.id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if order is None:
            raise ApiError(404, "ORDER_NOT_FOUND", "Pesanan tidak ditemukan.")
        try:
            amount = parse_gross_amount(payload["gross_amount"])
        except ValueError:
            raise ApiError(400, "INVALID_ORDER_AMOUNT", "Nominal pembayaran tidak sah.") from None
        if amount != order.amount_idr:
            raise ApiError(
                400,
                "ORDER_AMOUNT_MISMATCH",
                "Nominal pembayaran pada notifikasi tidak cocok dengan pesanan.",
            )
        # Reject before insert so a non-200 settlement cannot duplicate-match a later 200.
        status_code = str(payload.get("status_code", ""))
        if normalized == "settlement" and status_code != "200":
            raise ApiError(400, "INVALID_WEBHOOK_STATUS", "Status pembayaran tidak sah.")
        existing = db.scalar(
            select(PaymentEvent.id)
            .where(
                PaymentEvent.order_id == order_id,
                PaymentEvent.raw_status == status,
                PaymentEvent.status == normalized,
            )
            .with_for_update()
        )
        if (
            normalized == "settlement"
            and existing is None
            and order.status != "settlement"
            and not confirmed
        ):
            # Only a notice that would grant access needs the Status API. Release
            # the locks first so the external call never holds a row lock, then
            # take them again and re-check everything.
            db.rollback()
            _confirm_settlement(order_id, amount)
            confirmed = True
            continue
        break
    duplicate = existing is not None or (
        normalized == "settlement" and order.status == "settlement"
    )
    if existing is None:
        instant = now_utc()
        db.add(
            PaymentEvent(
                id=new_id("payevt_"),
                order_id=order.id,
                user_id=order.user_id,
                status=normalized,
                raw_status=status,
                gross_amount_idr=amount,
                transaction_time=_notice_transaction_time(payload, instant),
                received_at=instant,
            )
        )
        if normalized == "settlement" and status_code == "200" and order.status != "settlement":
            order.status = "settlement"
            if owner is not None and order.user_id == owner.id:
                start = max(instant, owner.valid_until_utc) if owner.valid_until_utc else instant
                owner.paid_flag = True
                owner.valid_until_utc = start + PLAN_DURATION
        elif normalized in {"expire", "fail"} and order.status == "pending":
            # Spec 5.30: expire and fail do not replace each other; the first stays.
            order.status = normalized
        # Pending and ignored events never reverse a terminal status.
    db.commit()
    return {"acknowledged": True, "idempotent_duplicate": duplicate}
