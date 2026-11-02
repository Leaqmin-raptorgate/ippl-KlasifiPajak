"""Persist month snapshots from stored transactions.

The engine remains the only calculator. This module maps stored rows onto engine
inputs, runs it once, and writes one *berlaku* row per month in the requested
range.

D-11 / HB-16 / API §5.22: input-changing paths call ``mark_usang`` for affected
months; ``rebuild`` (and POST recalculate) recompute only ``usang`` months (or
missing months in a range). A write never overwrites a berlaku row in place:
the prior berlaku is marked ``usang`` and a new row is inserted with
``version + 1``, unless the recomputed ``input_hash`` equals the current
berlaku hash (no-op, no bump).

Race safety: ``rebuild`` takes ``SELECT … FOR UPDATE`` on the profile row as
its first statement, before any snapshot / max(version) read. UK collisions on
``(profile_id, month_key, version)`` retry inside a savepoint; exhausted
retries surface as ``409 VERSION_CONFLICT``.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.engine import Profile as EngineProfile
from app.engine import Ruleset, compute
from app.engine import Transaction as EngineTransaction
from app.engine.compute import month_input_hash
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


def today_jakarta() -> date:
    return now_utc().replace(tzinfo=ZoneInfo("UTC")).astimezone(JAKARTA).date()


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


def _lock_profile(db: Session, profile: ProfileRow) -> None:
    """First statement of a rebuild: exclusive lock on the profile row."""
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
        ``only_usang`` is false, rebuilds January through December of the
        ruleset tax year for any missing/usang month in that band.
    only_usang:
        When true (POST recalculate / API §5.22), only months whose current
        status is ``usang`` are recomputed. Untouched ``berlaku`` rows stay.
    """
    # BLOCKER 1: profile FOR UPDATE is the first statement — before any
    # snapshot or max(version) read.
    _lock_profile(db, profile)
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
    rows = db.scalars(
        select(TransactionRow).where(
            TransactionRow.user_id == profile.user_id,
            TransactionRow.tx_date >= date(ruleset.tax_year, 1, 1),
            TransactionRow.tx_date <= date(ruleset.tax_year, 12, 31),
        )
    ).all()
    engine_rows = [transaction_to_engine(row) for row in rows]
    engine_profile = profile_to_engine(profile)
    # Through December so §5.12 PUT range (earliest month → Dec) is computable.
    as_of = date(ruleset.tax_year, 12, 31)
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
    today = today_jakarta()
    default_end = 12 if today.year != ruleset.tax_year else max(today.month, 1)

    if month_keys is None:
        candidate_keys = month_keys_through(ruleset.tax_year, 1, end_month=default_end)
    else:
        candidate_keys = list(month_keys)

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
        target_keys = sorted(usang_keys - berlaku_keys)
    else:
        # Create/update path: rebuild the candidate band; leave matching-hash
        # berlaku untouched (hash no-op).
        target_keys = candidate_keys

    written: list[MonthSnapshot] = []
    for month_key in target_keys:
        engine_month = engine_months.get(month_key)
        month_rows = [row for row in rows if row.tx_date.strftime("%Y-%m") == month_key]
        categories = {"pekerjaan_bebas": 0, "already_final": 0, "non_object": 0}
        for row in month_rows:
            if row.category in categories:
                categories[row.category] += row.amount_idr

        input_hash = (
            engine_month.input_hash
            if engine_month
            else month_input_hash(
                [transaction_to_engine(row) for row in month_rows],
                engine_profile,
                ruleset,
                month_key,
            )
        )

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
            next_year_ineligible=snapshot.next_year_at_risk,
            prior_year_resolution_source=snapshot.prior_year_resolution_source,
            input_hash=input_hash,
            engine_month=engine_month,
            categories=categories,
        )
        written.append(snapshot_row)

    # Drop future berlaku placeholders beyond "today" only on the default seed
    # path. Explicit month_keys (e.g. §5.12 earliest→Dec) must keep Dec.
    if month_keys is None:
        future_berlaku = db.scalars(
            select(MonthSnapshot)
            .where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.status == "berlaku",
                MonthSnapshot.month_key > f"{ruleset.tax_year}-{default_end:02d}",
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
