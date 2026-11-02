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
    AuditEventOut,
    AuditTrailOut,
    ClarificationAnswer,
    ClarificationOption,
    ClarificationOut,
    ClassificationOut,
    OverrideIn,
    PaginationOut,
    ReclassifyIn,
    TransactionCreate,
    TransactionListOut,
    TransactionOut,
    TransactionUpdate,
)
from app.security import iso_utc, new_id, now_utc
from app.services.profile import find_profile
from app.services.snapshot import DISCLAIMER
from app.services.snapshots_store import (
    get_berlaku,
    lock_profile,
    mark_usang,
    month_keys_through,
    rebuild,
)

VERSION_CONFLICT_MESSAGE = "Data ini sudah diubah di perangkat lain. Muat ulang, lalu simpan lagi."

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


def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def _stale_and_rebuild(
    db: Session,
    profile,
    ruleset: Ruleset,
    *,
    from_month: int,
    end_month: int = 12,
) -> list:
    """Mark affected months usang then recompute them (FR-23a / API §5.12/§5.22).

    Lock order: profile FOR UPDATE first, then snapshot rows inside
    ``mark_usang`` / ``rebuild`` (never snapshots-before-profile).
    """
    keys = month_keys_through(ruleset.tax_year, from_month, end_month=end_month)
    lock_profile(db, profile)
    mark_usang(db, profile, keys)
    return rebuild(db, profile, ruleset, month_keys=keys, only_usang=False)


def _require_profile(db: Session, user: User, tax_year: int):
    profile = find_profile(db, user, tax_year)
    if profile is None:
        raise ApiError(
            404,
            "PROFILE_NOT_FOUND",
            "Profil untuk tahun pajak berjalan belum dibuat.",
        )
    return profile


def get_transaction_for_update(db: Session, user: User, transaction_id: str) -> TransactionRow:
    """Load one owned row under ``SELECT … FOR UPDATE`` (API §5.12 TOCTOU guard)."""
    row = db.scalar(
        select(TransactionRow)
        .where(
            TransactionRow.id == transaction_id,
            TransactionRow.user_id == user.id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(404, "TRANSACTION_NOT_FOUND", "Transaksi tidak ditemukan.")
    return row


def _owned_transaction_exists(db: Session, user: User, transaction_id: str) -> bool:
    """Unlocked ownership probe so IDOR stays ``TRANSACTION_NOT_FOUND`` (not profile 404)."""
    return (
        db.scalar(
            select(TransactionRow.id).where(
                TransactionRow.id == transaction_id,
                TransactionRow.user_id == user.id,
            )
        )
        is not None
    )


def _assert_expected_version(row: TransactionRow, expected: int | None) -> None:
    """Raise 409 VERSION_CONFLICT when the client-supplied version does not match."""
    if expected is None:
        return
    if expected != row.version:
        raise ApiError(409, "VERSION_CONFLICT", VERSION_CONFLICT_MESSAGE)


def _claim_transaction_version(db: Session, user: User, transaction_id: str, expected: int) -> int:
    """Conditional version bump: ``UPDATE … WHERE version=:expected``.

    Returns the new version on success. ``rowcount==0`` → 409 (or 404 if gone).
    Call only after ``lock_profile`` so lock order stays profile → tx.
    """
    from sqlalchemy import update

    result = db.execute(
        update(TransactionRow)
        .where(
            TransactionRow.id == transaction_id,
            TransactionRow.user_id == user.id,
            TransactionRow.version == expected,
        )
        .values(version=expected + 1)
    )
    if result.rowcount == 1:
        return expected + 1
    exists = db.scalar(
        select(TransactionRow.id).where(
            TransactionRow.id == transaction_id,
            TransactionRow.user_id == user.id,
        )
    )
    if exists is None:
        raise ApiError(404, "TRANSACTION_NOT_FOUND", "Transaksi tidak ditemukan.")
    raise ApiError(409, "VERSION_CONFLICT", VERSION_CONFLICT_MESSAGE)


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
    _stale_and_rebuild(db, profile, ruleset, from_month=payload.tx_date.month)
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
    if not _owned_transaction_exists(db, user, transaction_id):
        raise ApiError(404, "TRANSACTION_NOT_FOUND", "Transaksi tidak ditemukan.")
    profile = _require_profile(db, user, ruleset.tax_year)
    lock_profile(db, profile)
    row = get_transaction_for_update(db, user, transaction_id)
    if not row.requires_clarification:
        raise ApiError(
            409,
            "CLARIFICATION_NOT_REQUIRED",
            "Baris ini sudah terklasifikasi, jadi tidak ada pertanyaan yang menunggu.",
        )
    if payload.version is not None:
        if payload.version != row.version:
            raise ApiError(
                409,
                "VERSION_CONFLICT",
                "Baris sudah berubah di tempat lain. Muat ulang sebelum menjawab.",
            )
        _claim_transaction_version(db, user, transaction_id, payload.version)
        row.version = payload.version + 1
    else:
        row.version += 1

    before = _usaha_total(db, user.id, exclude_id=row.id)
    old_category = row.category
    row.category = payload.category
    row.source = "user_clarification"
    row.requires_clarification = False
    row.confidence = 1.0
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
    _stale_and_rebuild(db, profile, ruleset, from_month=row.tx_date.month)
    db.commit()
    return row_out(row)


def update_transaction(
    db: Session,
    user: User,
    transaction_id: str,
    payload: TransactionUpdate,
    ruleset: Ruleset,
) -> TransactionOut:
    """PUT /transactions/{id} — optimistic concurrency via ``version`` (FR-08).

    Classification is not re-run on a field edit (UC-05a A1). Snapshots from the
    earlier of the old and new month through December are rebuilt (API §5.12).

    Lock order: profile → transaction (FOR UPDATE + conditional version claim)
    → snapshots. Parallel PUTs with the same expected version yield exactly one
    2xx; the rest are 409 VERSION_CONFLICT.
    """
    if payload.source_channel not in _SOURCE_CHANNELS:
        raise ApiError(422, "INVALID_SOURCE_CHANNEL", "Saluran sumber tidak dikenal.")
    if payload.tx_date.year != ruleset.tax_year:
        raise ApiError(
            422,
            "INVALID_DATE_RANGE",
            f"Tanggal transaksi di luar tahun pajak {ruleset.tax_year}.",
        )
    if not _owned_transaction_exists(db, user, transaction_id):
        raise ApiError(404, "TRANSACTION_NOT_FOUND", "Transaksi tidak ditemukan.")
    profile = _require_profile(db, user, ruleset.tax_year)
    lock_profile(db, profile)
    row = get_transaction_for_update(db, user, transaction_id)
    _assert_expected_version(row, payload.version)

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
                TransactionRow.id != row.id,
            )
        )
        if duplicate is not None:
            raise ApiError(
                409,
                "DUPLICATE_INVOICE_TRANSACTION",
                "Nomor faktur ini sudah tercatat untuk klien, nominal, dan tanggal yang sama.",
            )

    old_month = row.tx_date.month
    # Conditional UPDATE claims the version slot; rowcount==0 → 409.
    _claim_transaction_version(db, user, transaction_id, payload.version)
    row.tx_date = payload.tx_date
    row.amount_idr = payload.amount_idr
    row.withheld_tax_amount_idr = payload.withheld_tax_amount_idr
    row.client_name = payload.client_name.strip()
    row.client_name_norm = client_norm
    row.description = payload.description.strip()
    row.invoice_no = payload.invoice_no or None
    row.invoice_no_norm = invoice_norm
    row.source_channel = payload.source_channel
    row.version = payload.version + 1
    db.flush()
    start = min(old_month, payload.tx_date.month)
    _stale_and_rebuild(db, profile, ruleset, from_month=start, end_month=12)
    db.commit()
    return row_out(row)


def delete_transaction(db: Session, user: User, transaction_id: str, ruleset: Ruleset) -> dict:
    """DELETE /transactions/{id} — cascade classification events, rebuild (FR-09).

    Lock order: profile → transaction FOR UPDATE → snapshots.
    """
    if not _owned_transaction_exists(db, user, transaction_id):
        raise ApiError(404, "TRANSACTION_NOT_FOUND", "Transaksi tidak ditemukan.")
    profile = _require_profile(db, user, ruleset.tax_year)
    lock_profile(db, profile)
    row = get_transaction_for_update(db, user, transaction_id)

    for event in db.scalars(
        select(ClassificationEvent).where(ClassificationEvent.transaction_id == row.id)
    ).all():
        db.delete(event)
    deleted_month = row.tx_date.month
    db.delete(row)
    db.flush()
    _stale_and_rebuild(db, profile, ruleset, from_month=deleted_month, end_month=12)
    db.commit()
    return {"deleted": True, "id": transaction_id}


def override_category(
    db: Session,
    user: User,
    transaction_id: str,
    payload: OverrideIn,
    ruleset: Ruleset,
) -> TransactionOut:
    """POST /transactions/{id}/override — no model call (FR-16 / API §5.18).

    Lock order: profile → transaction FOR UPDATE → snapshots. Serializes concurrent
    overrides on the same row even though the body carries no ``version``.
    """
    if not _owned_transaction_exists(db, user, transaction_id):
        raise ApiError(404, "TRANSACTION_NOT_FOUND", "Transaksi tidak ditemukan.")
    profile = _require_profile(db, user, ruleset.tax_year)
    lock_profile(db, profile)
    row = get_transaction_for_update(db, user, transaction_id)

    before = _usaha_total(db, user.id, exclude_id=row.id)
    old_category = row.category
    row.category = payload.new_category
    row.source = "user_override"
    row.requires_clarification = False
    row.confidence = 1.0
    row.version += 1
    after = before + row.amount_idr if payload.new_category == "usaha" else before
    db.add(
        ClassificationEvent(
            id=new_id("evt_"),
            transaction_id=row.id,
            recorded_at=now_utc(),
            source=row.source,
            rule_id="",
            citation="",
            old_category=old_category,
            new_category=payload.new_category,
            note=(payload.note or "").strip(),
            ytd_usaha_before_idr=before,
            ytd_usaha_after_idr=after,
            ruleset_id=ruleset.ruleset_id,
            effective_date=date.fromisoformat(ruleset.effective_date),
        )
    )
    _stale_and_rebuild(db, profile, ruleset, from_month=row.tx_date.month, end_month=12)
    db.commit()
    return row_out(row)


def reclassify_transactions(
    db: Session, user: User, payload: ReclassifyIn, ruleset: Ruleset
) -> dict:
    """POST /transactions/reclassify — atomic rules-layer rerun (API §5.9).

    This slice has no model fallback; exhausted AI quota is therefore a no-op for
    reservation. Each id runs the same keyword pipeline as create. One unknown
    id fails the whole request with no writes.
    """
    profile = _require_profile(db, user, ruleset.tax_year)
    # Lock order: profile first, then each transaction FOR UPDATE in sorted id
    # order (avoids lock-order inversion across concurrent reclassify calls).
    lock_profile(db, profile)

    ids = list(payload.transaction_ids)
    locked: dict[str, TransactionRow] = {}
    for tx_id in sorted(set(ids)):
        try:
            locked[tx_id] = get_transaction_for_update(db, user, tx_id)
        except ApiError as exc:
            if exc.code == "TRANSACTION_NOT_FOUND":
                raise ApiError(
                    404,
                    "TRANSACTION_NOT_FOUND",
                    "Satu atau lebih transaksi tidak ditemukan pada akun Anda.",
                ) from exc
            raise
    rows = []
    for tx_id in ids:
        row = locked.get(tx_id)
        if row is None:
            raise ApiError(
                404,
                "TRANSACTION_NOT_FOUND",
                "Satu atau lebih transaksi tidak ditemukan pada akun Anda.",
            )
        rows.append(row)

    results = []
    for row in rows:
        old_category = row.category
        category, rule_id, confidence, requires_clarification, citation = classify(
            f"{row.description} {row.client_name}"
        )
        before = _usaha_total(db, user.id, exclude_id=row.id)
        row.category = category
        row.source = "rule"
        row.rule_id = rule_id
        row.confidence = confidence
        row.requires_clarification = requires_clarification
        row.version += 1
        after = before + row.amount_idr if category == "usaha" else before
        db.add(
            ClassificationEvent(
                id=new_id("evt_"),
                transaction_id=row.id,
                recorded_at=now_utc(),
                source=row.source,
                rule_id=rule_id,
                citation=citation,
                old_category=old_category,
                new_category=category,
                note="" if not requires_clarification else "Menunggu klarifikasi pengguna.",
                ytd_usaha_before_idr=before,
                ytd_usaha_after_idr=after,
                ruleset_id=ruleset.ruleset_id,
                effective_date=date.fromisoformat(ruleset.effective_date),
            )
        )
        results.append(
            {
                "id": row.id,
                "old_category": old_category,
                "new_category": category,
                "source": row.source,
            }
        )
    start = min(r.tx_date.month for r in rows)
    _stale_and_rebuild(db, profile, ruleset, from_month=start, end_month=12)
    db.commit()
    return {"reclassified_count": len(results), "results": results}


def audit_trail(db: Session, user: User, transaction_id: str) -> AuditTrailOut:
    """GET /transactions/{id}/audit-trail from classification_events (FR-16a)."""
    get_transaction(db, user, transaction_id)  # ownership / 404
    events = db.scalars(
        select(ClassificationEvent)
        .where(ClassificationEvent.transaction_id == transaction_id)
        .order_by(ClassificationEvent.recorded_at.asc(), ClassificationEvent.id.asc())
    ).all()
    out = []
    for event in events:
        out.append(
            AuditEventOut(
                timestamp=iso_utc(event.recorded_at),
                source=event.source,
                rule_id=event.rule_id,
                citation=event.citation,
                assigned_category=event.new_category,
                old_category=event.old_category,
                new_category=event.new_category,
                note=event.note,
                ytd_usaha_omzet_before_idr=event.ytd_usaha_before_idr,
                ytd_usaha_omzet_after_idr=event.ytd_usaha_after_idr,
                ruleset_id=event.ruleset_id,
                effective_date=event.effective_date.isoformat(),
            )
        )
    return AuditTrailOut(events=tuple(out))


def recalculate_snapshots(db: Session, user: User, tax_year: int, ruleset: Ruleset) -> dict:
    """POST /tax/snapshots/{tax_year}/recalculate (FR-23a / API §5.22).

    Only months marked ``usang`` are recomputed. Matching ``input_hash`` is a
    no-op (no version bump).
    """
    if tax_year != ruleset.tax_year:
        raise ApiError(422, "INVALID_DATE_RANGE", f"Tahun pajak harus {ruleset.tax_year}.")
    profile = find_profile(db, user, tax_year)
    if profile is None:
        raise ApiError(
            404,
            "PROFILE_NOT_FOUND",
            "Profil untuk tahun pajak yang dipilih belum dibuat.",
        )
    written = rebuild(db, profile, ruleset, only_usang=True)
    db.commit()
    return {
        "recalculated_tax_year": tax_year,
        "recalculated_months_count": len(written),
        "status": "berlaku",
    }


def month_snapshot(db: Session, user: User, tax_year: int, month: str, ruleset: Ruleset) -> dict:
    """GET /tax/snapshots/{tax_year}/{month} — FR-47 jejak cuplikan bulan."""
    if tax_year != ruleset.tax_year:
        raise ApiError(422, "INVALID_DATE_RANGE", f"Tahun pajak harus {ruleset.tax_year}.")
    profile = find_profile(db, user, tax_year)
    if profile is None:
        raise ApiError(
            404,
            "PROFILE_NOT_FOUND",
            "Profil untuk tahun pajak yang dipilih belum dibuat.",
        )
    month_key = month if len(month) == 7 else f"{tax_year}-{int(month):02d}"
    row = get_berlaku(db, profile, month_key)
    if row is None:
        raise ApiError(404, "SNAPSHOT_NOT_FOUND", "Cuplikan bulan yang diminta tidak ada.")
    return {
        "month": row.month_key,
        "version": row.version,
        "status": row.status,
        "ruleset_id": row.ruleset_id,
        "effective_date": row.effective_date.isoformat(),
        "rounding_rule": row.rounding_rule,
        "scheme_eligibility_status": row.scheme_eligibility_status,
        "next_year_ineligible": row.next_year_ineligible,
        "prior_year_resolution_source": row.prior_year_resolution_source,
        "input_hash": row.input_hash,
        "usaha_omzet_idr": row.usaha_omzet_idr,
        "porsi_bebas_idr": row.porsi_bebas_idr,
        "porsi_kena_idr": row.porsi_kena_idr,
        "tax_0_5_pct_idr": row.tax_0_5_pct_idr,
        "withheld_tax_idr": row.withheld_tax_idr,
        "sisa_bayar_idr": row.sisa_bayar_idr,
        "overwithheld_excess_idr": row.overwithheld_excess_idr,
        "overwithheld_status": row.overwithheld_status,
        "pekerjaan_bebas_omzet_idr": row.pekerjaan_bebas_omzet_idr,
        "already_final_omzet_idr": row.already_final_omzet_idr,
        "non_object_omzet_idr": row.non_object_omzet_idr,
        "annotation": row.annotation,
        "disclaimer": DISCLAIMER,
    }


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
