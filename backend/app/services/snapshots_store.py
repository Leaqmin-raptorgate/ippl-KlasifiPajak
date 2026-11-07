"""Persist month snapshots from stored transactions.

The engine remains the only calculator. This module maps stored rows onto engine
inputs, runs it once, and writes one *berlaku* row per month in the requested
range.

Profile changes that affect figures call ``mark_usang`` and then rebuild.
Transaction writes rebuild directly, retaining months whose hashes are unchanged.
POST recalculate handles only ``usang`` months. Changed months receive a new
version; the hash covers earlier months and the risk flag is cumulative
(FR-20, FR-22, FR-23a).

Race safety: ``rebuild`` takes ``SELECT … FOR UPDATE`` on the profile row as
its first statement, before any snapshot / max(version) read. MySQL ``1062``
collisions on UK ``uq_month_snapshots_version`` ``(profile_id, month_key,
version)`` retry inside a savepoint; exhausted retries surface as ``409
VERSION_CONFLICT``. Any other ``IntegrityError`` is re-raised.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.engine import Profile as EngineProfile
from app.engine import Ruleset, compute
from app.engine import Transaction as EngineTransaction
from app.engine.compute import month_contexts
from app.models import MonthSnapshot
from app.models import Profile as ProfileRow
from app.models import Transaction as TransactionRow
from app.security import new_id, now_utc

JAKARTA = ZoneInfo("Asia/Jakarta")

INELIGIBLE_ANNOTATION = (
    "Fasilitas PPh Final 0,5% tidak berlaku (peredaran bruto tahun lalu melebihi Rp 4,8 miliar)."
)
UNVERIFIABLE_ANNOTATION = "Peredaran bruto tahun lalu belum tersedia."

_VERSION_INSERT_RETRIES = 3

VERSION_CONFLICT_MESSAGE = "Data ini sudah diubah di perangkat lain. Muat ulang, lalu simpan lagi."

# Matches Storage Alembic ``uq_month_snapshots_version`` / ERD r3 UK.
SNAPSHOT_VERSION_UK_NAME = "uq_month_snapshots_version"


_TODAY_JAKARTA_OVERRIDE: ContextVar[date | None] = ContextVar(
    "today_jakarta_override", default=None
)


def today_jakarta() -> date:
    """Calendar date in Asia/Jakarta (API §2.4). Overridable in tests."""
    override = _TODAY_JAKARTA_OVERRIDE.get()
    if override is not None:
        return override
    return now_utc().replace(tzinfo=ZoneInfo("UTC")).astimezone(JAKARTA).date()


@contextmanager
def freeze_today_jakarta(frozen: date):
    """Pin ``today_jakarta()`` for the current context (tests)."""
    token = _TODAY_JAKARTA_OVERRIDE.set(frozen)
    try:
        yield
    finally:
        _TODAY_JAKARTA_OVERRIDE.reset(token)


def as_of_for_tax_year(tax_year: int, today: date | None = None) -> date | None:
    """Bagian B cutoff (API §2.4 / §5.11).

    Current year → today (Jakarta); past year → 31 Dec of that year; future →
    None (no snapshots).
    """
    day = today or today_jakarta()
    if tax_year > day.year:
        return None
    if tax_year < day.year:
        return date(tax_year, 12, 31)
    return day


def snapshot_end_month(tax_year: int, today: date | None = None) -> int:
    """Last month_key month to materialise (0 = none for a future tax year)."""
    day = today or today_jakarta()
    if tax_year > day.year:
        return 0
    if tax_year < day.year:
        return 12
    return day.month


def profile_to_engine(profile: ProfileRow) -> EngineProfile:
    return EngineProfile(
        spouse_has_usaha_income="yes" if profile.spouse_aggregation_active else "no",
        spouse_aggregation_active=profile.spouse_aggregation_active,
        spouse_usaha_omzet_ytd=profile.spouse_current_usaha_idr,
        spouse_prior_year_omzet=0,
        prior_year_usaha_omzet=profile.prior_user_usaha_idr,
        prior_year_pekerjaan_bebas_omzet=profile.prior_user_pekerjaan_bebas_idr,
        prior_year_already_final_omzet=profile.prior_user_already_final_idr,
        is_new_taxpayer_current_year=profile.is_new_taxpayer_current_year,
        spouse_current_pekerjaan_bebas_omzet=profile.spouse_current_pekerjaan_bebas_idr,
        spouse_current_already_final_omzet=profile.spouse_current_already_final_idr,
        prior_spouse_usaha_omzet=profile.prior_spouse_usaha_idr,
        prior_spouse_pekerjaan_bebas_omzet=profile.prior_spouse_pekerjaan_bebas_idr,
        prior_spouse_already_final_omzet=profile.prior_spouse_already_final_idr,
    )


def transaction_to_engine(row: TransactionRow) -> EngineTransaction:
    return EngineTransaction(
        id=row.id,
        amount=row.amount_idr,
        date=row.tx_date.isoformat(),
        category=row.category,
        withheld_tax_amount=row.withheld_tax_amount_idr,
    )


def month_keys_through(tax_year: int, start_month: int, *, end_month: int = 12) -> list[str]:
    """Inclusive month_key list from ``start_month`` through ``end_month``."""
    first = max(1, min(12, start_month))
    last = max(first, min(12, end_month))
    return [f"{tax_year}-{index:02d}" for index in range(first, last + 1)]


def mark_usang(db: Session, profile: ProfileRow, month_keys: list[str] | None = None) -> int:
    """Mark berlaku rows ``usang`` for FR-23a stale signalling (API §5.22).

    When ``month_keys`` is None every berlaku row for the profile is marked.
    Returns how many rows flipped.
    """
    conditions = [
        MonthSnapshot.profile_id == profile.id,
        MonthSnapshot.status == "berlaku",
    ]
    if month_keys is not None:
        if not month_keys:
            return 0
        conditions.append(MonthSnapshot.month_key.in_(month_keys))
    rows = db.scalars(select(MonthSnapshot).where(*conditions).with_for_update()).all()
    for row in rows:
        row.status = "usang"
    db.flush()
    return len(rows)


def lock_profile(db: Session, profile: ProfileRow) -> None:
    """Exclusive lock on the profile row — must be acquired BEFORE any
    snapshot or transaction mutation lock (profile → tx → snapshots).
    """
    db.execute(
        text("SELECT id FROM profiles WHERE id = :id FOR UPDATE"),
        {"id": profile.id},
    )


def _lock_snapshots(db: Session, profile_id: str) -> None:
    db.execute(
        text("SELECT id FROM month_snapshots WHERE profile_id = :pid FOR UPDATE"),
        {"pid": profile_id},
    )


def _next_version(db: Session, profile_id: str, month_key: str) -> int:
    row = db.execute(
        text(
            "SELECT COALESCE(MAX(version), 0) AS v FROM month_snapshots "
            "WHERE profile_id = :pid AND month_key = :mk FOR UPDATE"
        ),
        {"pid": profile_id, "mk": month_key},
    ).one()
    return int(row.v) + 1


def _mark_month_usang(db: Session, profile_id: str, month_key: str) -> None:
    priors = db.scalars(
        select(MonthSnapshot)
        .where(
            MonthSnapshot.profile_id == profile_id,
            MonthSnapshot.month_key == month_key,
            MonthSnapshot.status == "berlaku",
        )
        .with_for_update()
    ).all()
    for prior in priors:
        prior.status = "usang"


def _raise_version_conflict() -> None:
    raise ApiError(409, "VERSION_CONFLICT", VERSION_CONFLICT_MESSAGE)


def is_month_snapshot_version_conflict(exc: IntegrityError) -> bool:
    """True only for MySQL 1062 on ``uq_month_snapshots_version``.

    Other integrity faults (FK 1452, unrelated 1062, etc.) must not become
    ``409 VERSION_CONFLICT``.
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    args = getattr(orig, "args", ()) or ()
    if not args or args[0] != 1062:
        return False
    message = args[1] if len(args) > 1 else str(orig)
    return SNAPSHOT_VERSION_UK_NAME in str(message)


def _insert_berlaku_month(
    db: Session,
    *,
    profile: ProfileRow,
    month_key: str,
    ruleset: Ruleset,
    scheme_status: str,
    annotation: str,
    next_year_ineligible: bool,
    prior_year_resolution_source: str,
    input_hash: str,
    engine_month,
    categories: dict[str, int],
) -> MonthSnapshot:
    """Mark prior berlaku → usang and insert version+1, retrying UK collisions."""
    last_error: IntegrityError | None = None
    for _attempt in range(_VERSION_INSERT_RETRIES):
        try:
            with db.begin_nested():
                _mark_month_usang(db, profile.id, month_key)
                next_version = _next_version(db, profile.id, month_key)
                snapshot_row = MonthSnapshot(
                    id=new_id("snap_"),
                    profile_id=profile.id,
                    month_key=month_key,
                    version=next_version,
                    status="berlaku",
                    ruleset_id=ruleset.ruleset_id,
                    effective_date=date.fromisoformat(ruleset.effective_date),
                    rounding_rule=ruleset.rounding_rule,
                    scheme_eligibility_status=scheme_status,
                    next_year_ineligible=next_year_ineligible,
                    prior_year_resolution_source=prior_year_resolution_source,
                    input_hash=input_hash,
                    usaha_omzet_idr=engine_month.usaha_omzet if engine_month else 0,
                    porsi_bebas_idr=engine_month.exempt if engine_month else 0,
                    porsi_kena_idr=engine_month.taxable if engine_month else 0,
                    tax_0_5_pct_idr=engine_month.final_tax if engine_month else 0,
                    withheld_tax_idr=engine_month.withheld if engine_month else 0,
                    sisa_bayar_idr=engine_month.sisa_bayar_idr if engine_month else 0,
                    overwithheld_excess_idr=(
                        engine_month.overwithheld_excess_idr if engine_month else 0
                    ),
                    overwithheld_status=(engine_month.withhold_status if engine_month else "nihil"),
                    pekerjaan_bebas_omzet_idr=categories["pekerjaan_bebas"],
                    already_final_omzet_idr=categories["already_final"],
                    non_object_omzet_idr=categories["non_object"],
                    annotation=annotation,
                )
                db.add(snapshot_row)
                db.flush()
                return snapshot_row
        except IntegrityError as exc:
            if not is_month_snapshot_version_conflict(exc):
                raise
            last_error = exc
            continue
    if last_error is not None:
        db.rollback()
        _raise_version_conflict()
    raise RuntimeError("unreachable")  # pragma: no cover


def rebuild(
    db: Session,
    profile: ProfileRow,
    ruleset: Ruleset,
    *,
    month_keys: list[str] | None = None,
    only_usang: bool = False,
) -> list[MonthSnapshot]:
    """Recompute snapshot months for one profile under the profile-row lock.

    Parameters
    ----------
    month_keys:
        When set, only these months are candidates (still filtered by
        ``only_usang`` when that flag is true). When ``None`` and
        ``only_usang`` is false, checks January through the Jakarta as-of
        month. Months whose current hashes match are retained (FR-22, FR-23a).
    only_usang:
        When true (POST recalculate / API §5.22), only months whose current
        status is ``usang`` are recomputed. Untouched ``berlaku`` rows stay.
    """
    # Profile FOR UPDATE is the first statement — before any snapshot or
    # max(version) read (lock order: profile → tx → snapshots).
    lock_profile(db, profile)
    _lock_snapshots(db, profile.id)

    last_error: IntegrityError | None = None
    for _pass in range(_VERSION_INSERT_RETRIES):
        try:
            with db.begin_nested():
                return _rebuild_locked(
                    db,
                    profile,
                    ruleset,
                    month_keys=month_keys,
                    only_usang=only_usang,
                )
        except IntegrityError as exc:
            if not is_month_snapshot_version_conflict(exc):
                raise
            last_error = exc
            _lock_snapshots(db, profile.id)
            continue
        except ApiError:
            raise
    if last_error is not None:
        db.rollback()
        _raise_version_conflict()
    raise RuntimeError("unreachable")  # pragma: no cover


def _rebuild_locked(
    db: Session,
    profile: ProfileRow,
    ruleset: Ruleset,
    *,
    month_keys: list[str] | None,
    only_usang: bool,
) -> list[MonthSnapshot]:
    today = today_jakarta()
    as_of = as_of_for_tax_year(ruleset.tax_year, today)
    default_end = snapshot_end_month(ruleset.tax_year, today)

    # Load every stored row for the tax year (including future-dated); the
    # engine and category totals below only see tx_date <= as_of (§2.4/§5.11).
    # A locking read returns the latest committed rows. A plain read would use
    # the REPEATABLE READ view fixed before this call waited on the profile lock,
    # and miss a row a concurrent write committed meanwhile (FR-08, FR-23a).
    rows = db.scalars(
        select(TransactionRow)
        .where(
            TransactionRow.user_id == profile.user_id,
            TransactionRow.tx_date >= date(ruleset.tax_year, 1, 1),
            TransactionRow.tx_date <= date(ruleset.tax_year, 12, 31),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()

    if as_of is None or default_end == 0:
        # Future tax year: no months. Drop any stray berlaku placeholders.
        future_berlaku = db.scalars(
            select(MonthSnapshot)
            .where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.status == "berlaku",
            )
            .with_for_update()
        ).all()
        if future_berlaku:
            db.execute(
                delete(MonthSnapshot).where(MonthSnapshot.id.in_([r.id for r in future_berlaku]))
            )
        db.flush()
        return []

    included = [row for row in rows if row.tx_date <= as_of]
    engine_rows = [transaction_to_engine(row) for row in included]
    engine_profile = profile_to_engine(profile)
    snapshot = compute(engine_rows, engine_profile, ruleset, as_of)

    if snapshot.prior_year_resolution_source == "unverifiable":
        scheme_status = "unverifiable"
        annotation = UNVERIFIABLE_ANNOTATION
    elif snapshot.prior_year_ineligible:
        scheme_status = "scheme_ineligible"
        annotation = INELIGIBLE_ANNOTATION
    else:
        scheme_status = "scheme_eligible"
        annotation = ""

    engine_months = {month.month: month for month in snapshot.months}
    end_key = f"{ruleset.tax_year}-{default_end:02d}"

    if month_keys is None:
        candidate_keys = month_keys_through(ruleset.tax_year, 1, end_month=default_end)
    else:
        # Never materialize months beyond the current Jakarta cutoff.
        candidate_keys = [key for key in month_keys if key <= end_key]

    if only_usang:
        # §5.22: only months currently without a berlaku row (stale after
        # mark_usang). Historical usang siblings of a live berlaku are ignored.
        conditions = [
            MonthSnapshot.profile_id == profile.id,
            MonthSnapshot.status == "usang",
        ]
        if month_keys is not None:
            conditions.append(MonthSnapshot.month_key.in_(candidate_keys))
        usang_keys = {
            row.month_key for row in db.scalars(select(MonthSnapshot).where(*conditions)).all()
        }
        berlaku_keys = {
            row.month_key
            for row in db.scalars(
                select(MonthSnapshot).where(
                    MonthSnapshot.profile_id == profile.id,
                    MonthSnapshot.status == "berlaku",
                )
            ).all()
        }
        target_keys = sorted(key for key in (usang_keys - berlaku_keys) if key <= end_key)
    else:
        # Create/update path: rebuild the candidate band; leave matching-hash
        # berlaku untouched (hash no-op).
        target_keys = candidate_keys

    contexts = month_contexts(engine_rows, engine_profile, ruleset, target_keys)
    written: list[MonthSnapshot] = []
    for month_key in target_keys:
        engine_month = engine_months.get(month_key)
        month_rows = [row for row in included if row.tx_date.strftime("%Y-%m") == month_key]
        categories = {"pekerjaan_bebas": 0, "already_final": 0, "non_object": 0}
        for row in month_rows:
            if row.category in categories:
                categories[row.category] += row.amount_idr

        context = contexts[month_key]
        input_hash = context.input_hash
        month_next_year = context.next_year_at_risk

        current_berlaku = db.scalar(
            select(MonthSnapshot)
            .where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == month_key,
                MonthSnapshot.status == "berlaku",
            )
            .with_for_update()
        )
        if current_berlaku is not None and current_berlaku.input_hash == input_hash:
            # No-op: inputs unchanged — keep the berlaku row, no version bump.
            written.append(current_berlaku)
            continue

        # D-11 / §5.22: once a month is usang (or missing), insert version+1.
        # Hash no-op above only skips when a berlaku row already matches.
        snapshot_row = _insert_berlaku_month(
            db,
            profile=profile,
            month_key=month_key,
            ruleset=ruleset,
            scheme_status=scheme_status,
            annotation=annotation,
            next_year_ineligible=month_next_year,
            prior_year_resolution_source=snapshot.prior_year_resolution_source,
            input_hash=input_hash,
            engine_month=engine_month,
            categories=categories,
        )
        written.append(snapshot_row)

    # Always drop berlaku placeholders past the Jakarta as_of month (§2.4).
    future_berlaku = db.scalars(
        select(MonthSnapshot)
        .where(
            MonthSnapshot.profile_id == profile.id,
            MonthSnapshot.status == "berlaku",
            MonthSnapshot.month_key > end_key,
        )
        .with_for_update()
    ).all()
    if future_berlaku:
        db.execute(
            delete(MonthSnapshot).where(MonthSnapshot.id.in_([r.id for r in future_berlaku]))
        )
    db.flush()
    return written


def get_berlaku(db: Session, profile: ProfileRow, month_key: str) -> MonthSnapshot | None:
    """The current berlaku row for one month, or None."""
    return db.scalar(
        select(MonthSnapshot).where(
            MonthSnapshot.profile_id == profile.id,
            MonthSnapshot.month_key == month_key,
            MonthSnapshot.status == "berlaku",
        )
    )
