"""Background AI classification after a rule miss (FR-12, FR-13, FR-34, FR-43, NFR-16).

The model runs only with consent, remaining quota, and an unchanged provisional
row. Quota is reserved and committed before the call, and refunded when no
answer is stored. This module does not import the tax engine.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classify.model_client import (
    CLASSIFICATION_SCHEMA,
    ModelUnavailable,
    OpenAICompatibleClient,
    build_classification_messages,
    validate_classification,
)
from app.db import SessionLocal
from app.logging_redaction import get_logger
from app.models import ClassificationEvent, Profile, User
from app.models import Transaction as TransactionRow
from app.security import new_id, now_utc
from app.services.ai_quota import refund_ai, try_reserve_ai
from app.services.config import get_config

log = get_logger("app.classification_fallback")

_HOUR_LIMIT = 120
_HOUR_SECONDS = 3600
_MAX_ATTEMPTS = 3
_hour_hits: dict[str, deque[float]] = {}
_hour_lock = threading.Lock()


def get_model_client() -> OpenAICompatibleClient:
    """Build the classifier client from the environment at call time (FR-12).

    An empty base URL, key, or model raises ``ModelUnavailable`` before any
    client object is constructed, so no socket is opened.
    """
    base = os.environ.get("AI_BASE_URL", "").strip()
    key = os.environ.get("AI_API_KEY", "").strip()
    model = os.environ.get("AI_MODEL_CLASSIFIER", "").strip()
    if not base or not key or not model:
        raise ModelUnavailable("Classification model provider is not configured")
    raw_timeout = os.environ.get("AI_TIMEOUT_S", "").strip()
    try:
        timeout = float(raw_timeout) if raw_timeout else 30.0
    except ValueError:
        timeout = 30.0
    return OpenAICompatibleClient(
        base_url=base,
        api_key=key,
        model=model,
        timeout_s=timeout,
    )


def run_fallback(transaction_id: str, user_id: str, version: int) -> None:
    """Try one AI classification for a provisional row and commit the outcome (FR-12).

    No-ops when consent is missing, the row changed, the hourly cap is spent,
    or the monthly quota cannot be reserved. A reserved unit is refunded when
    nothing is stored (FR-13, FR-34, NFR-16).
    """
    prepared: dict[str, Any] | None = None
    try:
        prepared = _prepare(transaction_id, user_id, version)
        if prepared is None:
            return
        result = None
        try:
            result = _ask(prepared)
        except Exception:
            log.info("classification fallback model call failed")
            result = None
        _finish(transaction_id, user_id, version, result)
    except Exception:
        log.info("classification fallback failed")
        if prepared is not None:
            _refund_quietly(user_id)


def _prune_hour_hits(now: float) -> None:
    """Drop stamps, and keys, that are outside the rolling hour."""
    cutoff = now - _HOUR_SECONDS
    expired: list[str] = []
    for key, hits in _hour_hits.items():
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if not hits:
            expired.append(key)
    for key in expired:
        del _hour_hits[key]


def _hourly_allow(user_id: str) -> bool:
    """Allow 120 fallback attempts per user per rolling hour (NFR-16)."""
    now = time.monotonic()
    with _hour_lock:
        _prune_hour_hits(now)
        hits = _hour_hits.get(user_id)
        if hits is None:
            hits = deque()
            _hour_hits[user_id] = hits
        if len(hits) >= _HOUR_LIMIT:
            return False
        hits.append(now)
        return True


def _eligible(
    db: Session, transaction_id: str, user_id: str, version: int
) -> TransactionRow | None:
    """Provisional rule row still owned by a consenting user (FR-12, NFR-16)."""
    user = db.get(User, user_id)
    if user is None or user.ai_consent_at is None:
        return None
    row = db.scalar(
        select(TransactionRow).where(
            TransactionRow.id == transaction_id,
            TransactionRow.user_id == user_id,
        )
    )
    if row is None or row.user_id != user_id:
        return None
    if row.source != "rule" or not row.requires_clarification or row.version != version:
        return None
    return row


def _prior_classifications(db: Session, row: TransactionRow) -> list[dict[str, str]]:
    """Up to five earlier decisions for this client, without names or NIB (FR-12, NFR-16)."""
    rows = db.scalars(
        select(TransactionRow)
        .where(
            TransactionRow.user_id == row.user_id,
            TransactionRow.client_name_norm == row.client_name_norm,
            TransactionRow.id != row.id,
            TransactionRow.requires_clarification.is_(False),
        )
        .order_by(TransactionRow.tx_date.desc(), TransactionRow.id.desc())
        .limit(5)
    ).all()
    return [{"category": item.category, "source": item.source} for item in rows]


def _prepare(transaction_id: str, user_id: str, version: int) -> dict[str, Any] | None:
    """Reserve one unit and return prompt fields, or None when the call must not run."""
    db = SessionLocal()
    try:
        row = _eligible(db, transaction_id, user_id, version)
        if row is None or not _hourly_allow(user_id):
            return None
        profile = db.scalar(
            select(Profile).where(
                Profile.user_id == user_id,
                Profile.tax_year == row.tx_date.year,
            )
        )
        event = db.scalar(
            select(ClassificationEvent)
            .where(ClassificationEvent.transaction_id == row.id)
            .order_by(ClassificationEvent.recorded_at.asc(), ClassificationEvent.id.asc())
        )
        prepared = {
            "description": _scrub_own_identifiers(row.description, row.client_name, row.invoice_no),
            "client_name": row.client_name,
            "amount_idr": int(row.amount_idr),
            "ruleset_id": event.ruleset_id if event is not None else "",
            "min_confidence": Decimal(get_config(db, "T_ai")),
            "nib_status": profile.nib_status if profile is not None else "",
            "kbli": profile.kbli_code if profile is not None else "",
            "priors": _prior_classifications(db, row),
        }
        # GET /quotas is not required first. Insert the month row, then reserve.
        from app.services.subscription import _ensure_counter, _jakarta_month_key

        user = db.get(User, user_id)
        if user is None:
            return None
        month_key, _reset = _jakarta_month_key()
        _ensure_counter(db, user, month_key)
        if not try_reserve_ai(db, user_id):
            return None
        db.commit()
        return prepared
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _quotes(query: str) -> list[dict[str, str]]:
    """At most five BM25 passages. Failures yield an empty list (FR-12)."""
    try:
        from app.classify.bm25 import search
    except Exception:
        return []
    try:
        found = search(query)
    except Exception:
        return []
    if not isinstance(found, list):
        return []
    quotes: list[dict[str, str]] = []
    for item in found[:5]:
        if not isinstance(item, dict):
            continue
        doc_id = item.get("id")
        text = item.get("text")
        citation = item.get("citation")
        if not all(isinstance(value, str) for value in (doc_id, text, citation)):
            continue
        quotes.append({"id": doc_id, "text": text, "citation": citation})
    return quotes


def _scrub_own_identifiers(
    description: str, client_name: str | None, invoice_no: str | None
) -> str:
    """Replace the row's own client name and invoice number inside the free text.

    The client name field is masked separately; this keeps the same name from
    leaving through the description or the BM25 query (FR-43, NFR-16).
    """
    for value, token in ((client_name, "[KLIEN]"), (invoice_no, "[INVOICE]")):
        text = (value or "").strip()
        if len(text) >= 3:
            description = re.sub(re.escape(text), token, description, flags=re.IGNORECASE)
    return description


def _ask(prepared: dict[str, Any]) -> Any:
    """Call the patched or live client at most three times (FR-12, FR-13, FR-38)."""
    context = {
        "nib_status": prepared["nib_status"],
        "kbli": prepared["kbli"],
        "prior_classifications": prepared["priors"],
        "quotes": _quotes(prepared["description"]),
    }
    messages = build_classification_messages(
        description=prepared["description"],
        client_name=prepared["client_name"],
        amount_idr=prepared["amount_idr"],
        ruleset_id=prepared["ruleset_id"],
        min_confidence=prepared["min_confidence"],
        context=context,
    )
    client = get_model_client()
    min_confidence = prepared["min_confidence"]
    for _attempt in range(_MAX_ATTEMPTS):
        try:
            raw = client.complete(messages, response_schema=CLASSIFICATION_SCHEMA)
        except ModelUnavailable:
            continue
        except Exception:
            continue
        parsed = validate_classification(raw, min_confidence=min_confidence)
        if parsed is not None:
            return parsed
    return None


def _finish(transaction_id: str, user_id: str, version: int, result: Any) -> None:
    """Store a valid result or refund the reserved unit (FR-13, FR-34)."""
    db = SessionLocal()
    try:
        stored = bool(result is not None and _store(db, transaction_id, user_id, version, result))
        if not stored:
            refund_ai(db, user_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _store(db: Session, transaction_id: str, user_id: str, version: int, result: Any) -> bool:
    """Apply the category under the profile lock, then rebuild snapshots (FR-13)."""
    from app.services import transactions as tx
    from app.services.snapshot import active_ruleset
    from app.services.snapshots_store import lock_profile, today_jakarta

    user = db.get(User, user_id)
    if user is None or user.ai_consent_at is None:
        return False
    ruleset = active_ruleset()
    profile = db.scalar(
        select(Profile).where(
            Profile.user_id == user_id,
            Profile.tax_year == ruleset.tax_year,
        )
    )
    if profile is None:
        return False
    lock_profile(db, profile)
    row = db.scalar(
        select(TransactionRow)
        .where(
            TransactionRow.id == transaction_id,
            TransactionRow.user_id == user_id,
        )
        .with_for_update()
    )
    if (
        row is None
        or row.user_id != user_id
        or row.source != "rule"
        or not row.requires_clarification
        or row.version != version
    ):
        return False
    db.refresh(user)
    if user.ai_consent_at is None:
        return False

    old_category = row.category
    old_needs_clarification = row.requires_clarification
    as_of = today_jakarta()
    before = tx._usaha_total(db, user_id, tax_year=ruleset.tax_year, as_of=as_of)
    row.category = result.category
    row.source = "ai"
    row.confidence = float(result.confidence)
    row.requires_clarification = False
    after = before
    if old_category == "usaha" and not old_needs_clarification and row.tx_date <= as_of:
        after -= int(row.amount_idr)
    if result.category == "usaha" and row.tx_date <= as_of:
        after += int(row.amount_idr)
    db.add(
        ClassificationEvent(
            id=new_id("evt_"),
            transaction_id=row.id,
            recorded_at=now_utc(),
            source=row.source,
            rule_id=row.rule_id,
            citation=result.citation[:255],
            old_category=old_category,
            new_category=result.category,
            note="",
            ytd_usaha_before_idr=before,
            ytd_usaha_after_idr=after,
            ruleset_id=ruleset.ruleset_id,
            effective_date=date.fromisoformat(ruleset.effective_date),
        )
    )
    db.flush()
    tx._stale_and_rebuild(db, profile, ruleset)
    return True


def _refund_quietly(user_id: str) -> None:
    """Best-effort refund after a failed finish. Never raises (FR-34, FR-38)."""
    db = SessionLocal()
    try:
        refund_ai(db, user_id)
        db.commit()
    except Exception:
        db.rollback()
        log.info("classification fallback quota refund failed")
    finally:
        db.close()
