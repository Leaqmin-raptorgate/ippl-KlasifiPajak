"""Persist month snapshots from stored transactions.

The engine remains the only calculator. This module maps stored rows onto engine
inputs, runs it once, and writes one *berlaku* row per month from January
through today's Asia/Jakarta month.

D-11 / HB-16: a write never overwrites a berlaku row in place. The prior berlaku
row is marked ``usang`` and a new row is inserted with ``version + 1``. The
input_hash and ruleset stamp travel with every new row (B-08 H-07/H-08).

Race safety: ``rebuild`` takes ``SELECT … FOR UPDATE`` on the profile row (and
existing snapshot rows for that profile) so concurrent writers for the same
profile serialize. Inserts that still collide on the
``(profile_id, month_key, version)`` UK retry inside a savepoint (bounded).
"""

from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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

#: Bounded retries when two writers race past the row lock onto the same next version.
_VERSION_INSERT_RETRIES = 3


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


def mark_usang(db: Session, profile: ProfileRow, month_keys: list[str] | None = None) -> int:
    """Mark berlaku rows ``usang`` for FR-23a stale signalling.

    When ``month_keys`` is None every berlaku row for the profile is marked.
    Returns how many rows flipped.
    """
    conditions = [
        MonthSnapshot.profile_id == profile.id,
        MonthSnapshot.status == "berlaku",
    ]
    if month_keys is not None:
        conditions.append(MonthSnapshot.month_key.in_(month_keys))
    rows = db.scalars(select(MonthSnapshot).where(*conditions).with_for_update()).all()
    for row in rows:
        row.status = "usang"
    db.flush()
    return len(rows)


def _lock_profile_and_snapshots(db: Session, profile: ProfileRow) -> ProfileRow:
    """Serialize writers for one profile via row locks inside the caller's txn.

    Returns the caller's ``profile`` instance (not a re-loaded row) so unflushed
    mutations — e.g. profile PUT before rebuild — stay visible to the engine.
    """
    # Explicit SQL so the lock is always emitted even if the ORM identity map
    # already holds the Profile row from an earlier SELECT in this session.
    db.execute(
        text("SELECT id FROM profiles WHERE id = :id FOR UPDATE"),
        {"id": profile.id},
    )
    # Lock every existing snapshot row for this profile so version bumps see a
    # stable set (and so a concurrent rebuild cannot insert while we read max).
    db.execute(
        text("SELECT id FROM month_snapshots WHERE profile_id = :pid FOR UPDATE"),
        {"pid": profile.id},
    )
    return profile


def _next_version(db: Session, profile_id: str, month_key: str) -> int:
    # Locking read: under MySQL REPEATABLE READ a plain MAX() would keep the
    # pre-wait snapshot and collide with a writer we just serialized behind.
    row = db.execute(
        text(
            "SELECT COALESCE(MAX(version), 0) AS v FROM month_snapshots "
            "WHERE profile_id = :pid AND month_key = :mk FOR UPDATE"
        ),
        {"pid": profile_id, "mk": month_key},
    ).one()
    return int(row.v) + 1


def _mark_month_usang(db: Session, profile_id: str, month_key: str) -> None:
    """Flip every berlaku row for one month to usang (heals dual-berlaku too)."""
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
            # Savepoint rolled back; re-read max(version) on the next attempt.
            continue
    assert last_error is not None
    raise last_error


def rebuild(db: Session, profile: ProfileRow, ruleset: Ruleset) -> list[MonthSnapshot]:
    """Recompute every month through today for one stored profile.

    Each month that already has a berlaku row is versioned: every old berlaku
    becomes ``usang`` and a new ``berlaku`` row is inserted with ``version + 1``.
    Concurrent rebuilds for the same profile serialize on a profile row lock;
    UK collisions on ``(profile_id, month_key, version)`` retry up to
    ``_VERSION_INSERT_RETRIES`` times (per month and once more for the whole pass).
    """
    locked_profile = _lock_profile_and_snapshots(db, profile)

    last_error: IntegrityError | None = None
    for _pass in range(_VERSION_INSERT_RETRIES):
        try:
            with db.begin_nested():
                return _rebuild_locked(db, locked_profile, ruleset)
        except IntegrityError as exc:
            last_error = exc
            # Re-lock snapshot rows so the next pass sees committed peers.
            db.execute(
                text("SELECT id FROM month_snapshots WHERE profile_id = :pid FOR UPDATE"),
                {"pid": locked_profile.id},
            )
            continue
    assert last_error is not None
    raise last_error


def _rebuild_locked(
    db: Session, locked_profile: ProfileRow, ruleset: Ruleset
) -> list[MonthSnapshot]:
    rows = db.scalars(
        select(TransactionRow).where(
            TransactionRow.user_id == locked_profile.user_id,
            TransactionRow.tx_date >= date(ruleset.tax_year, 1, 1),
            TransactionRow.tx_date <= date(ruleset.tax_year, 12, 31),
        )
    ).all()
    engine_rows = [transaction_to_engine(row) for row in rows]
    engine_profile = profile_to_engine(locked_profile)
    as_of = today_jakarta()
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

    last_month = min(as_of.month, 12) if as_of.year == ruleset.tax_year else 12
    written: list[MonthSnapshot] = []
    engine_months = {month.month: month for month in snapshot.months}

    for index in range(1, last_month + 1):
        month_key = f"{ruleset.tax_year}-{index:02d}"
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

        snapshot_row = _insert_berlaku_month(
            db,
            profile=locked_profile,
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

    # Months beyond the current Jakarta month do not exist yet — drop future
    # berlaku placeholders left from an earlier as_of (keep usang history).
    future_berlaku = db.scalars(
        select(MonthSnapshot)
        .where(
            MonthSnapshot.profile_id == locked_profile.id,
            MonthSnapshot.status == "berlaku",
            MonthSnapshot.month_key > f"{ruleset.tax_year}-{last_month:02d}",
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
