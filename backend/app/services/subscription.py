"""Subscription and quota read/write models.

Paid entitlement is derived from ``users.paid_flag`` and ``valid_until_utc``
(FR-35). Quota counters live in ``quota_counters`` with ERD r3 / D-02 column
names ``ai_classification_used`` and ``assistant_chat_used``. Free limits are
10 / 15; paid ceilings are the ruleset values (200 / 200). Month keys and the
reset instant use Asia/Jakarta (FR-34, FR-39).
"""

import time as time_module
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.engine import Ruleset
from app.models import QuotaCounter, User
from app.security import iso_utc, new_id, now_utc

JAKARTA = ZoneInfo("Asia/Jakarta")

PLANS = ({"plan_id": "monthly_25k", "duration_days": 30, "price_idr": 25_000},)

FREE_AI_LIMIT = 10
FREE_ASSISTANT_LIMIT = 15


def is_paid_active(user: User, now: datetime | None = None) -> bool:
    instant = now or now_utc()
    # API §2.6: active at exactly valid_until_utc, inactive after that instant.
    return bool(
        user.paid_flag and user.valid_until_utc is not None and user.valid_until_utc >= instant
    )


def subscription_status(user: User, has_pending_order: bool = False) -> dict:
    """FR-35: derive the tier from paid_flag and the validity instant."""
    now = now_utc()
    if is_paid_active(user, now):
        tier = "berbayar"
        active = True
    elif has_pending_order:
        tier = "pending"
        active = False
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


# MySQL InnoDB: deadlock victim (1213) / lock wait timeout (1205).
_TRANSIENT_LOCK_ERRNOS = frozenset({1205, 1213})
_ENSURE_COUNTER_ATTEMPTS = 8
_ENSURE_COUNTER_BACKOFF_SEC = (0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4)


def _is_transient_lock_error(exc: OperationalError) -> bool:
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    args = getattr(orig, "args", ()) or ()
    return bool(args) and args[0] in _TRANSIENT_LOCK_ERRNOS


def _ensure_counter(db: Session, user: User, month_key: str) -> tuple[QuotaCounter, bool]:
    """Load or insert the month counter; race-safe on the (user_id, month_key) UK.

    Uses a savepoint so a concurrent first-GET loses the insert cleanly. After
    ``IntegrityError``, a locking re-select (current read) sees the winner under
    MySQL REPEATABLE READ. Transient InnoDB deadlocks (1213) and lock-wait
    timeouts (1205) retry with short backoff. Caller still commits only when
    ``created`` is True (GET /quotas stays non-committing on an existing
    counter).
    """
    last_lock_error: OperationalError | None = None
    for attempt in range(_ENSURE_COUNTER_ATTEMPTS):
        try:
            row = db.scalar(
                select(QuotaCounter).where(
                    QuotaCounter.user_id == user.id,
                    QuotaCounter.month_key == month_key,
                )
            )
            if row is not None:
                return row, False
            try:
                with db.begin_nested():
                    row = QuotaCounter(
                        id=new_id("qc_"),
                        user_id=user.id,
                        month_key=month_key,
                        ai_classification_used=0,
                        assistant_chat_used=0,
                    )
                    db.add(row)
                    db.flush()
                return row, True
            except IntegrityError:
                # Locking read bypasses the RR snapshot so we observe the
                # committed winner instead of retrying inserts forever.
                row = db.scalar(
                    select(QuotaCounter)
                    .where(
                        QuotaCounter.user_id == user.id,
                        QuotaCounter.month_key == month_key,
                    )
                    .with_for_update()
                )
                if row is not None:
                    return row, False
                db.expire_all()
                continue
        except OperationalError as exc:
            if not _is_transient_lock_error(exc):
                raise
            last_lock_error = exc
            # Deadlock aborts the whole MySQL transaction; clear session state.
            db.rollback()
            delay = _ENSURE_COUNTER_BACKOFF_SEC[min(attempt, len(_ENSURE_COUNTER_BACKOFF_SEC) - 1)]
            time_module.sleep(delay)
            continue
    row = db.scalar(
        select(QuotaCounter)
        .where(
            QuotaCounter.user_id == user.id,
            QuotaCounter.month_key == month_key,
        )
        .with_for_update()
    )
    if row is None:
        if last_lock_error is not None:
            raise last_lock_error
        raise RuntimeError("quota counter insert raced without a surviving row")
    return row, False


def quotas(db: Session, user: User, ruleset: Ruleset) -> dict:
    """FR-34, FR-39: calendar-month counters in Asia/Jakarta."""
    month_key, reset = _jakarta_month_key()
    row, created = _ensure_counter(db, user, month_key)
    paid = is_paid_active(user)
    ai_limit = ruleset.quota_ai_classification if paid else FREE_AI_LIMIT
    chat_limit = ruleset.quota_assistant_chat if paid else FREE_ASSISTANT_LIMIT
    ai_used = int(row.ai_classification_used)
    chat_used = int(row.assistant_chat_used)
    # Persist a newly created zero-row so later reads see it; never commit on a
    # pure read of an existing counter (API §5.26 / review finding #9).
    if created:
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
    db: Session,
    *,
    user_id: str,
    paid_flag: bool,
    valid_until: datetime | None,
) -> dict:
    """Test-support paid_flag adapter (API §5.31 / HB-29). Caller gates env.

    Looks up the user inside the service (AGENTS.md / REVIEW.md layering:
    routes must not run ORM queries).
    """
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise ApiError(404, "USER_NOT_FOUND", "Pengguna tidak ditemukan.")
    user.paid_flag = paid_flag
    user.valid_until_utc = valid_until
    db.commit()
    return {
        "updated": True,
        "paid_flag": paid_flag,
        "valid_until": iso_utc(valid_until) if valid_until is not None else None,
    }
