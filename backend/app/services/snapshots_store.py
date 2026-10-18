"""Persist month snapshots from stored transactions.

The engine remains the only calculator. This module maps stored rows onto engine
inputs, runs it once, and writes one row per month from January through today's
Asia/Jakarta month. A write replaces the range inside the caller's transaction.
"""

from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
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


def rebuild(db: Session, profile: ProfileRow, ruleset: Ruleset) -> list[MonthSnapshot]:
    """Recompute every month through today for one stored profile."""
    rows = db.scalars(
        select(TransactionRow).where(
            TransactionRow.user_id == profile.user_id,
            TransactionRow.tx_date >= date(ruleset.tax_year, 1, 1),
            TransactionRow.tx_date <= date(ruleset.tax_year, 12, 31),
        )
    ).all()
    engine_rows = [transaction_to_engine(row) for row in rows]
    engine_profile = profile_to_engine(profile)
    as_of = today_jakarta()
    snapshot = compute(engine_rows, engine_profile, ruleset, as_of)

    if snapshot.prior_year_resolution_source == "unverifiable":
        status = "unverifiable"
        annotation = UNVERIFIABLE_ANNOTATION
    elif snapshot.prior_year_ineligible:
        status = "scheme_ineligible"
        annotation = INELIGIBLE_ANNOTATION
    else:
        status = "scheme_eligible"
        annotation = ""

    existing = {
        row.month_key: row
        for row in db.scalars(select(MonthSnapshot).where(MonthSnapshot.profile_id == profile.id))
    }
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

        snapshot_row = existing.get(month_key)
        if snapshot_row is None:
            snapshot_row = MonthSnapshot(
                id=new_id("snap_"), profile_id=profile.id, month_key=month_key
            )
            db.add(snapshot_row)
            existing[month_key] = snapshot_row

        snapshot_row.status = "berlaku"
        snapshot_row.ruleset_id = ruleset.ruleset_id
        snapshot_row.effective_date = date.fromisoformat(ruleset.effective_date)
        snapshot_row.rounding_rule = ruleset.rounding_rule
        snapshot_row.scheme_eligibility_status = status
        snapshot_row.next_year_ineligible = snapshot.next_year_at_risk
        snapshot_row.prior_year_resolution_source = snapshot.prior_year_resolution_source
        snapshot_row.input_hash = (
            engine_month.input_hash
            if engine_month
            else month_input_hash(
                [transaction_to_engine(row) for row in month_rows],
                engine_profile,
                ruleset,
                month_key,
            )
        )
        snapshot_row.usaha_omzet_idr = engine_month.usaha_omzet if engine_month else 0
        snapshot_row.porsi_bebas_idr = engine_month.exempt if engine_month else 0
        snapshot_row.porsi_kena_idr = engine_month.taxable if engine_month else 0
        snapshot_row.tax_0_5_pct_idr = engine_month.final_tax if engine_month else 0
        snapshot_row.withheld_tax_idr = engine_month.withheld if engine_month else 0
        snapshot_row.sisa_bayar_idr = engine_month.sisa_bayar_idr if engine_month else 0
        snapshot_row.overwithheld_excess_idr = (
            engine_month.overwithheld_excess_idr if engine_month else 0
        )
        snapshot_row.overwithheld_status = engine_month.withhold_status if engine_month else "nihil"
        snapshot_row.pekerjaan_bebas_omzet_idr = categories["pekerjaan_bebas"]
        snapshot_row.already_final_omzet_idr = categories["already_final"]
        snapshot_row.non_object_omzet_idr = categories["non_object"]
        snapshot_row.annotation = annotation
        written.append(snapshot_row)

    # Months beyond the current Jakarta month do not exist yet.
    stale = [row for key, row in existing.items() if key > f"{ruleset.tax_year}-{last_month:02d}"]
    if stale:
        db.execute(delete(MonthSnapshot).where(MonthSnapshot.id.in_([r.id for r in stale])))
    db.flush()
    return written
