"""Subscription and quota read/write models.

Paid entitlement is derived from ``users.paid_flag`` and ``valid_until_utc``
(FR-35). Quota counters live in ``quota_counters`` with ERD r3 / D-02 column
names ``ai_classification_used`` and ``assistant_chat_used``. Free limits are
10 / 15; paid ceilings are the ruleset values (200 / 200). Month keys and the
reset instant use Asia/Jakarta (FR-34, FR-39).
"""

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine import Ruleset
from app.models import QuotaCounter, User
from app.security import iso_utc, new_id, now_utc

JAKARTA = ZoneInfo("Asia/Jakarta")

PLANS = ({"plan_id": "monthly_25k", "duration_days": 30, "price_idr": 25_000},)

FREE_AI_LIMIT = 10
FREE_ASSISTANT_LIMIT = 15


def _is_paid_active(user: User, now: datetime | None = None) -> bool:
    instant = now or now_utc()
    return bool(
        user.paid_flag and user.valid_until_utc is not None and user.valid_until_utc > instant
    )


def subscription_status(user: User) -> dict:
    """FR-35: derive the tier from paid_flag and the validity instant."""
    now = now_utc()
    if _is_paid_active(user, now):
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


def _jakarta_month_key(now: datetime | None = None) -> tuple[str, datetime]:
    instant = now or now_utc()
    local = instant.replace(tzinfo=timezone.utc).astimezone(JAKARTA)
    next_month = (
        date(local.year + 1, 1, 1) if local.month == 12 else date(local.year, local.month + 1, 1)
    )
    reset = datetime.combine(next_month, time.min, tzinfo=JAKARTA)
    return local.strftime("%Y-%m"), reset


def _ensure_counter(db: Session, user: User, month_key: str) -> QuotaCounter:
    row = db.scalar(
        select(QuotaCounter).where(
            QuotaCounter.user_id == user.id,
            QuotaCounter.month_key == month_key,
        )
    )
    if row is None:
        row = QuotaCounter(
            id=new_id("qc_"),
            user_id=user.id,
            month_key=month_key,
            ai_classification_used=0,
            assistant_chat_used=0,
        )
        db.add(row)
        db.flush()
    return row


def quotas(db: Session, user: User, ruleset: Ruleset) -> dict:
    """FR-34, FR-39: calendar-month counters in Asia/Jakarta."""
    month_key, reset = _jakarta_month_key()
    row = _ensure_counter(db, user, month_key)
    paid = _is_paid_active(user)
    ai_limit = ruleset.quota_ai_classification if paid else FREE_AI_LIMIT
    chat_limit = ruleset.quota_assistant_chat if paid else FREE_ASSISTANT_LIMIT
    ai_used = int(row.ai_classification_used)
    chat_used = int(row.assistant_chat_used)
    db.commit()
    return {
        "month_key": month_key,
        "timezone": "Asia/Jakarta",
        "reset_timestamp_utc": reset.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ai_classification": {
            "used": ai_used,
            "limit": ai_limit,
            "status": "exhausted" if ai_used >= ai_limit else "active",
        },
        "assistant_chat": {
            "used": chat_used,
            "limit": chat_limit,
            "status": "exhausted" if chat_used >= chat_limit else "active",
        },
    }


def set_subscription_override(
    db: Session, user: User, *, paid_flag: bool, valid_until: datetime | None
) -> dict:
    """Test-support paid_flag adapter (API §5.31 / HB-29). Caller gates env."""
    user.paid_flag = paid_flag
    user.valid_until_utc = valid_until
    db.commit()
    return {
        "updated": True,
        "paid_flag": paid_flag,
        "valid_until": iso_utc(valid_until) if valid_until is not None else None,
    }
