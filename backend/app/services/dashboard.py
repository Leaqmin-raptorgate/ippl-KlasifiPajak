"""Dashboard read model.

It reads stored snapshots. The one write is `refresh_if_due`, which rebuilds
and commits snapshots once per Jakarta day when a future-dated row has become
due; the dashboard itself does no tax arithmetic beyond summing stored figures.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.engine import Ruleset
from app.engine.compute import _prior_gross_revenue
from app.models import MonthSnapshot, Profile, User
from app.services.config import get_config
from app.services.profile import find_profile
from app.services.snapshot import DISCLAIMER
from app.services.snapshots_store import profile_to_engine, rebuild, today_jakarta
from app.services.transactions import provisional_usaha_total


def dashboard(
    db: Session,
    user: User,
    tax_year: int,
    ruleset: Ruleset,
    *,
    refresh: bool = True,
) -> dict:
    """Return stored dashboard figures. ``refresh`` is false for read-only callers."""
    profile = find_profile(db, user, tax_year)
    if profile is None:
        raise ApiError(
            404,
            "PROFILE_NOT_FOUND",
            "Profil untuk tahun pajak yang dipilih belum dibuat.",
        )
    if refresh:
        refresh_if_due(db, profile, ruleset)
    rows = db.scalars(
        select(MonthSnapshot)
        .where(
            MonthSnapshot.profile_id == profile.id,
            MonthSnapshot.status == "berlaku",
        )
        .order_by(MonthSnapshot.month_key)
    ).all()

    usaha_ytd = sum(row.usaha_omzet_idr for row in rows)
    pekerjaan_ytd = sum(row.pekerjaan_bebas_omzet_idr for row in rows)
    already_final_ytd = sum(row.already_final_omzet_idr for row in rows)
    aggregation = profile.spouse_aggregation_active
    spouse_current = (
        profile.spouse_current_usaha_idr
        + profile.spouse_current_pekerjaan_bebas_idr
        + profile.spouse_current_already_final_idr
        if aggregation and ruleset.spouse_in_cap
        else 0
    )
    combined_ytd = usaha_ytd + pekerjaan_ytd + already_final_ytd + spouse_current
    cap_warning_percent = int(get_config(db, "cap_warning_percent"))

    status = rows[-1].scheme_eligibility_status if rows else "scheme_eligible"
    next_year = rows[-1].next_year_ineligible if rows else False
    prior_amount, prior_tag = _prior_combined(profile, ruleset)
    split_month = next((row.month_key for row in rows if row.porsi_kena_idr > 0), None)
    remaining = max(0, ruleset.exemption_band_idr - usaha_ytd)
    annotation = next((row.annotation for row in rows if row.annotation), "")

    # Provisional rows are excluded from the calculation until clarified.
    provisional = provisional_usaha_total(db, user, tax_year)
    if provisional:
        note = (
            "Rp "
            + f"{provisional:,}".replace(",", ".")
            + " belum terklasifikasi dan tidak dihitung"
        )
        annotation = f"{annotation} {note}".strip() if annotation else note

    return {
        "metadata": {
            "ruleset_id": ruleset.ruleset_id,
            "effective_date": ruleset.effective_date,
            "rounding_rule": ruleset.rounding_rule,
            "disclaimer": DISCLAIMER,
        },
        "thresholds": {
            "pita_500_juta": {
                "limit_idr": ruleset.exemption_band_idr,
                "ytd_usaha_omzet_idr": usaha_ytd,
                "remaining_free_band_idr": remaining if status == "scheme_eligible" else 0,
                "split_month": split_month,
                "provisional_omzet_idr": provisional,
                "annotation": annotation,
            },
            "eligibility_prior_year_cap_4_8m": {
                "limit_idr": ruleset.eligibility_cap_idr,
                "combined_prior_year_gross_idr": prior_amount,
                "resolution_source": prior_tag,
                "status": status,
            },
            "monitoring_current_year_cap_4_8m": {
                "limit_idr": ruleset.eligibility_cap_idr,
                "cap_warning_percent": cap_warning_percent,
                "cap_warning": combined_ytd * 100
                >= ruleset.eligibility_cap_idr * cap_warning_percent,
                "ytd_usaha_omzet_idr": usaha_ytd,
                "provisional_usaha_omzet_idr": provisional,
                "ytd_pekerjaan_bebas_omzet_idr": pekerjaan_ytd,
                "ytd_already_final_omzet_idr": already_final_ytd,
                "spouse_current_year_usaha_omzet_idr": (
                    profile.spouse_current_usaha_idr if aggregation else 0
                ),
                "spouse_current_year_pekerjaan_bebas_omzet_idr": (
                    profile.spouse_current_pekerjaan_bebas_idr if aggregation else 0
                ),
                "spouse_current_year_already_final_omzet_idr": (
                    profile.spouse_current_already_final_idr if aggregation else 0
                ),
                "ytd_combined_gross_idr": combined_ytd,
                "next_year_ineligible": next_year,
            },
            "pasal_58": {
                "spouse_aggregation_active": aggregation,
                "badge_label": ("Pasal 58 aktif" if aggregation else "Pasal 58 tidak aktif"),
            },
        },
        "monthly_summaries": [
            {
                "month": row.month_key,
                "version": row.version,
                "status": row.status,
                "scheme_eligibility_status": row.scheme_eligibility_status,
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
                "input_hash": row.input_hash,
                "annotation": row.annotation,
            }
            for row in rows
        ],
    }


def _prior_combined(profile: Profile, ruleset: Ruleset) -> tuple[int, str]:
    """Amount and source tag from the engine prior-year function (FR-19)."""
    return _prior_gross_revenue(profile_to_engine(profile), ruleset.spouse_in_cap)


def refresh_if_due(db: Session, profile: Profile, ruleset: Ruleset) -> None:
    """Refresh once per Jakarta date so newly due transactions enter snapshots."""
    today = today_jakarta()
    if profile.snapshot_checked_through is None or profile.snapshot_checked_through < today:
        rebuild(db, profile, ruleset)
        db.commit()
