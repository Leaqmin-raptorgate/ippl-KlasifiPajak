"""Transaction use cases: list, create, classify, and rebuild snapshots."""

import math
import unicodedata
from calendar import monthrange
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.classify.rules import classify
from app.engine import Ruleset
from app.models import ClassificationEvent, User
from app.models import Transaction as TransactionRow
from app.schemas.transaction import (
    ClassificationOut,
    PaginationOut,
    TransactionCreate,
    TransactionListOut,
    TransactionOut,
)
from app.security import new_id, now_utc
from app.services.profile import find_profile
from app.services.snapshots_store import rebuild

_SOURCE_CHANNELS = frozenset({"marketplace", "corporate_client", "retail", "other"})


def normalize_text(value: str) -> str:
    """NFKC, collapse whitespace, casefold. The database does not casefold."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _out(row: TransactionRow, classification: ClassificationOut | None = None) -> TransactionOut:
    return TransactionOut(
        id=row.id,
        version=row.version,
        tx_date=row.tx_date,
        client_name=row.client_name,
        invoice_no=row.invoice_no,
        amount_idr=row.amount_idr,
        withheld_tax_amount_idr=row.withheld_tax_amount_idr,
        source_channel=row.source_channel,
        category=row.category,
        source=row.source,
        description=row.description,
        classification=classification,
    )


def list_transactions(
    db: Session,
    user: User,
    *,
    page: int,
    per_page: int,
    tax_year: int | None,
    month: str | None,
    client_name: str | None,
    invoice_no: str | None,
) -> TransactionListOut:
    per_page = max(1, min(per_page, 100))
    page = max(1, page)
    conditions = [TransactionRow.user_id == user.id]
    if tax_year is not None:
        conditions.append(
            TransactionRow.tx_date.between(date(tax_year, 1, 1), date(tax_year, 12, 31))
        )
    if month:
        year, month_number = (int(part) for part in month.split("-"))
        conditions.append(
            TransactionRow.tx_date.between(
                date(year, month_number, 1), _last_day(year, month_number)
            )
        )
    if client_name:
        conditions.append(TransactionRow.client_name_norm.like(f"%{normalize_text(client_name)}%"))
    if invoice_no:
        conditions.append(TransactionRow.invoice_no_norm == normalize_text(invoice_no))

    total = db.scalar(select(func.count()).select_from(TransactionRow).where(*conditions)) or 0
    rows = db.scalars(
        select(TransactionRow)
        .where(*conditions)
        .order_by(TransactionRow.tx_date.desc(), TransactionRow.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    return TransactionListOut(
        items=tuple(_out(row) for row in rows),
        pagination=PaginationOut(
            current_page=page,
            per_page=per_page,
            total_items=total,
            total_pages=max(1, math.ceil(total / per_page)) if total else 0,
        ),
    )


def create_transaction(
    db: Session, user: User, payload: TransactionCreate, ruleset: Ruleset
) -> TransactionOut:
    """Store one row, classify it with the keyword table, and rebuild snapshots.

    A row no rule recognizes is stored as provisional ``usaha`` with
    ``requires_clarification`` set and zero confidence. This slice has no model
    fallback, so the closed question is the next step instead of a guess.
    """
    if payload.source_channel not in _SOURCE_CHANNELS:
        raise ApiError(422, "INVALID_SOURCE_CHANNEL", "Saluran sumber tidak dikenal.")
    if payload.tx_date.year != ruleset.tax_year:
        raise ApiError(
            422,
            "INVALID_DATE_RANGE",
            f"Tanggal transaksi di luar tahun pajak {ruleset.tax_year}.",
        )
    profile = find_profile(db, user, ruleset.tax_year)
    if profile is None or not profile.nib_status:
        raise ApiError(
            422,
            "NIB_STATUS_NOT_CONFIGURED",
            "Status NIB untuk tahun pajak berjalan harus diisi sebelum mencatat transaksi pertama.",
        )

    client_norm = normalize_text(payload.client_name)
    invoice_norm = normalize_text(payload.invoice_no) if payload.invoice_no else None
    if invoice_norm:
        duplicate = db.scalar(
            select(TransactionRow.id).where(
                TransactionRow.user_id == user.id,
                TransactionRow.client_name_norm == client_norm,
                TransactionRow.invoice_no_norm == invoice_norm,
                TransactionRow.amount_idr == payload.amount_idr,
                TransactionRow.tx_date == payload.tx_date,
            )
        )
        if duplicate is not None:
            raise ApiError(
                409,
                "DUPLICATE_INVOICE_TRANSACTION",
                "Nomor faktur ini sudah tercatat untuk klien, nominal, dan tanggal yang sama.",
            )

    category, rule_id, confidence, requires_clarification, citation = classify(
        f"{payload.description} {payload.client_name}"
    )
    row = TransactionRow(
        id=new_id("tx_"),
        user_id=user.id,
        tx_date=payload.tx_date,
        amount_idr=payload.amount_idr,
        withheld_tax_amount_idr=payload.withheld_tax_amount_idr,
        client_name=payload.client_name.strip(),
        client_name_norm=client_norm,
        description=payload.description.strip(),
        invoice_no=payload.invoice_no or None,
        invoice_no_norm=invoice_norm,
        source_channel=payload.source_channel,
        category=category,
        source="rule",
        confidence=confidence,
        rule_id=rule_id,
        requires_clarification=requires_clarification,
        version=1,
    )
    db.add(row)
    db.flush()

    before = _usaha_total(db, user.id, exclude_id=row.id)
    after = before + payload.amount_idr if category == "usaha" else before
    db.add(
        ClassificationEvent(
            id=new_id("evt_"),
            transaction_id=row.id,
            recorded_at=now_utc(),
            source=row.source,
            rule_id=rule_id,
            citation=citation,
            old_category="",
            new_category=category,
            note="" if not requires_clarification else "Menunggu klarifikasi pengguna.",
            ytd_usaha_before_idr=before,
            ytd_usaha_after_idr=after,
            ruleset_id=ruleset.ruleset_id,
            effective_date=date.fromisoformat(ruleset.effective_date),
        )
    )
    rebuild(db, profile, ruleset)
    db.commit()

    return _out(
        row,
        ClassificationOut(
            category=category,
            source=row.source,
            confidence=confidence,
            rule_id=rule_id,
            requires_clarification=requires_clarification,
        ),
    )


def _usaha_total(db: Session, user_id: str, *, exclude_id: str) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(TransactionRow.amount_idr), 0)).where(
            TransactionRow.user_id == user_id,
            TransactionRow.category == "usaha",
            TransactionRow.id != exclude_id,
        )
    )
    return int(total or 0)


def _last_day(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])
