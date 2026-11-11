"""Atomic AI classification quota for one Jakarta calendar month (FR-34, FR-43).

The caller owns the transaction. Neither function commits or rolls back, so a
conditional update can hold its row lock until that caller commits.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models import User
from app.services.subscription import FREE_AI_LIMIT, _jakarta_month_key, is_paid_active

_RESERVE_SQL = (
    "UPDATE quota_counters "
    "SET ai_classification_used = ai_classification_used + 1 "
    "WHERE user_id = :user_id AND month_key = :month_key "
    "AND ai_classification_used < :limit"
)
_REFUND_SQL = (
    "UPDATE quota_counters "
    "SET ai_classification_used = ai_classification_used - 1 "
    "WHERE user_id = :user_id AND month_key = :month_key "
    "AND ai_classification_used > 0"
)
_PAID_AI_DEFAULT = 200


def _ruleset_path() -> Path:
    configured = Settings().ruleset_path
    if configured is not None:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "engine" / "ruleset" / "pp20_2026.json"


def _paid_ai_limit() -> int:
    """Paid ceiling from ``quota_ai_classification`` (FR-43). Default 200."""
    try:
        data = json.loads(_ruleset_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _PAID_AI_DEFAULT
    if not isinstance(data, dict):
        return _PAID_AI_DEFAULT
    value = data.get("quota_ai_classification", _PAID_AI_DEFAULT)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return _PAID_AI_DEFAULT
    return value


def _limit_for(db: Session, user_id: str) -> int | None:
    """Free limit, or the ruleset ceiling when the paid flag is active (FR-34, FR-43)."""
    user = db.get(User, user_id)
    if user is None:
        return None
    if is_paid_active(user):
        return _paid_ai_limit()
    return FREE_AI_LIMIT


def try_reserve_ai(db: Session, user_id: str) -> bool:
    """Reserve one AI unit on the current month row (FR-34, FR-43).

    True only when the conditional update changes exactly one row. Does not
    insert a counter and does not commit or roll back.
    """
    limit = _limit_for(db, user_id)
    if limit is None:
        return False
    month_key, _reset = _jakarta_month_key()
    result = db.execute(
        text(_RESERVE_SQL),
        {"user_id": user_id, "month_key": month_key, "limit": limit},
    )
    return result.rowcount == 1


def refund_ai(db: Session, user_id: str) -> None:
    """Return one reserved AI unit on the current month row, never below zero (FR-34).

    Does not commit or roll back.
    """
    month_key, _reset = _jakarta_month_key()
    db.execute(text(_REFUND_SQL), {"user_id": user_id, "month_key": month_key})
