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
    ClarificationAnswer,
    ClarificationOption,
    ClarificationOut,
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

#: The four engine categories. A clarification resolves to exactly one of them
#: (AGENTS.md invariant 2), so the options list is this list, in this order.
_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("usaha", "Usaha"),
    ("pekerjaan_bebas", "Pekerjaan bebas"),
    ("already_final", "Final tersendiri"),
    ("non_object", "Bukan objek"),
)

#: Asked once, in one form, for every row the keyword table could not place.
_CLARIFICATION_QUESTION = (
    "Aturan tidak mengenali keterangan baris ini, jadi kategorinya masih sementara. "
    "Pilih perlakuan yang sebenarnya terjadi."
)


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
        items=tuple(row_out(row) for row in rows),
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

    return row_out(row)


def get_transaction(db: Session, user: User, transaction_id: str) -> TransactionRow:
    """Load one row owned by this user. Every query is scoped by ``user_id``."""
    row = db.scalar(
        select(TransactionRow).where(
            TransactionRow.id == transaction_id,
            TransactionRow.user_id == user.id,
        )
    )
    if row is None:
        raise ApiError(404, "TRANSACTION_NOT_FOUND", "Transaksi tidak ditemukan.")
    return row


def row_out(row: TransactionRow) -> TransactionOut:
    """Project a stored row together with its classification detail.

    ``classification`` is always present, never ``null``. A client that has to
    infer "is this row provisional?" from an absent object gets it wrong the
    moment two rows disagree about whether they carry rule metadata. The flag to
    branch on is ``requires_clarification``; ``confidence`` is how sure the
    classifier is, which is a different question.
    """
    return _out(
        row,
        ClassificationOut(
            category=row.category,
            source=row.source,
            confidence=row.confidence,
            rule_id=row.rule_id,
            requires_clarification=row.requires_clarification,
        ),
    )


def clarification_for(db: Session, user: User, transaction_id: str) -> ClarificationOut:
    """The question a provisional row is waiting on.

    A row that a rule already placed has no question, and asking is a 404 with
    ``CLARIFICATION_NOT_REQUIRED`` rather than an empty question the client has
    to special-case.
    """
    row = get_transaction(db, user, transaction_id)
    if not row.requires_clarification:
        raise ApiError(
            404,
            "CLARIFICATION_NOT_REQUIRED",
            "Baris ini sudah terklasifikasi, jadi tidak ada pertanyaan yang menunggu.",
        )
    return ClarificationOut(
        transaction_id=row.id,
        provisional_category=row.category,
        question=_CLARIFICATION_QUESTION,
        options=tuple(
            ClarificationOption(value=value, label=label) for value, label in _CATEGORIES
        ),
    )


def answer_clarification(
    db: Session,
    user: User,
    transaction_id: str,
    payload: ClarificationAnswer,
    ruleset: Ruleset,
) -> TransactionOut:
    """Resolve a provisional row from the user's answer.

    The answer is recorded with source ``user_clarification`` and the
    provisional category moves out of the exemption band if it was sitting
    there, because the band only ever holds classified ``usaha`` turnover.
    """
    row = get_transaction(db, user, transaction_id)
    if payload.version is not None and payload.version != row.version:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "Baris sudah berubah di tempat lain. Muat ulang sebelum menjawab.",
        )
    if not row.requires_clarification:
        raise ApiError(
            409,
            "CLARIFICATION_NOT_REQUIRED",
            "Baris ini sudah terklasifikasi, jadi tidak ada pertanyaan yang menunggu.",
        )

    profile = find_profile(db, user, ruleset.tax_year)
    if profile is None:
        raise ApiError(
            404,
            "PROFILE_NOT_FOUND",
            "Profil untuk tahun pajak berjalan belum dibuat.",
        )

    before = _usaha_total(db, user.id, exclude_id=row.id)
    old_category = row.category
    row.category = payload.category
    row.source = "user_clarification"
    row.requires_clarification = False
    row.confidence = 1.0
    row.version += 1
    after = before + row.amount_idr if payload.category == "usaha" else before

    db.add(
        ClassificationEvent(
            id=new_id("evt_"),
            transaction_id=row.id,
            recorded_at=now_utc(),
            source=row.source,
            rule_id=row.rule_id,
            citation="",
            old_category=old_category,
            new_category=payload.category,
            note="Dijawab pengguna melalui klarifikasi.",
            ytd_usaha_before_idr=before,
            ytd_usaha_after_idr=after,
            ruleset_id=ruleset.ruleset_id,
            effective_date=date.fromisoformat(ruleset.effective_date),
        )
    )
    rebuild(db, profile, ruleset)
    db.commit()
    return row_out(row)


def _usaha_total(db: Session, user_id: str, *, exclude_id: str) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(TransactionRow.amount_idr), 0)).where(
            TransactionRow.user_id == user_id,
            TransactionRow.category == "usaha",
            TransactionRow.id != exclude_id,
        )
    )
    return int(total or 0)


def provisional_usaha_total(db: Session, user: User, tax_year: int) -> int:
    """Omzet that is sitting in ``usaha`` only as a placeholder.

    A row the keyword table could not place is stored provisionally as ``usaha``
    so it has a column value, not because that is the answer. It still lands in
    the exemption band until the user clarifies it, so the read model has to be
    able to say how much of the band is unconfirmed rather than let it pass as a
    classified figure.
    """
    total = db.scalar(
        select(func.coalesce(func.sum(TransactionRow.amount_idr), 0)).where(
            TransactionRow.user_id == user.id,
            TransactionRow.category == "usaha",
            TransactionRow.requires_clarification.is_(True),
            TransactionRow.tx_date.between(date(tax_year, 1, 1), date(tax_year, 12, 31)),
        )
    )
    return int(total or 0)


def _last_day(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])
