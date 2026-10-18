"""Subscription and quota read models for the demo slice.

The paid flag is stored on the account. No order, payment, or counter table
exists yet, so usage is reported as zero and a missing counter never invents a
paid tier. Caps come from the ruleset, not from this module.
"""

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.engine import Ruleset
from app.models import User
from app.security import iso_utc, now_utc

JAKARTA = ZoneInfo("Asia/Jakarta")

PLANS = ({"plan_id": "monthly_25k", "duration_days": 30, "price_idr": 25_000},)


def subscription_status(user: User) -> dict:
    """FR-35: derive the tier from paid_flag and the validity instant."""
    now = now_utc()
    if user.paid_flag and user.valid_until_utc is not None and user.valid_until_utc > now:
        tier = "berbayar"
        active = True
    elif user.paid_flag:
        tier = "kedaluwarsa"
        active = False
    else:
        tier = "gratis"
        active = False
    local = (
        user.valid_until_utc.replace(tzinfo=timezone.utc).astimezone(JAKARTA).isoformat()
        if user.valid_until_utc is not None
        else None
    )
    return {
        "subscription_tier": tier,
        "paid_flag": active,
        "valid_until_utc": (
            iso_utc(user.valid_until_utc) if user.valid_until_utc is not None else None
        ),
        "valid_until_local": local,
        "available_plans": list(PLANS),
    }


def quotas(ruleset: Ruleset) -> dict:
    """FR-34, FR-43: calendar-month counters in Asia/Jakarta.

    Usage is zero until the counter table lands. The limits are ruleset data.
    """
    now = now_utc()
    local = now.replace(tzinfo=timezone.utc).astimezone(JAKARTA)
    next_month = (
        date(local.year + 1, 1, 1) if local.month == 12 else date(local.year, local.month + 1, 1)
    )
    reset = datetime.combine(next_month, time.min, tzinfo=JAKARTA)
    return {
        "month_key": local.strftime("%Y-%m"),
        "timezone": "Asia/Jakarta",
        "reset_timestamp_utc": reset.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ai_classification": {
            "used": 0,
            "limit": ruleset.quota_ai_classification,
            "status": "active",
        },
        "assistant_chat": {
            "used": 0,
            "limit": ruleset.quota_assistant_chat,
            "status": "active",
        },
    }
