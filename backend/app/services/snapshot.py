"""Use-case functions for the stateless engine surface.

One function per use case. This layer owns the transaction boundary in the
storage release; the Bagian A functions run no SQL.
"""

from datetime import date

from app.engine import Profile, Ruleset, Snapshot, Transaction, compute
from app.engine.compute import month_input_hash
from app.engine.ruleset import load_ruleset
from app.schemas.snapshot import MonthOut, ProfileIn, SnapshotIn, SnapshotOut, TransactionIn

__all__ = [
    "DISCLAIMER",
    "active_ruleset",
    "build_snapshot",
    "engine_profile",
    "engine_snapshot",
    "to_wire",
]

#: Exact workpaper disclaimer from API v1.2.2 section 3.3.
DISCLAIMER = "DOKUMEN KERJA (WORKPAPER) — BUKAN SPT RESMI DAN BUKAN PRODUK DJP/CORETAX."


def active_ruleset(ruleset_path=None) -> Ruleset:
    """Load the ruleset this process serves."""
    return load_ruleset(ruleset_path)


def engine_profile(profile: ProfileIn) -> Profile:
    """Map the wire profile onto the engine's threshold inputs.

    An absent prior-year block stays ``None`` so the engine can tell "not
    supplied" from a reported nil (FR-03).
    """
    prior_user = profile.prior_year_gross_user
    prior_spouse = profile.prior_year_gross_spouse
    return Profile(
        spouse_has_usaha_income="yes" if profile.spouse_aggregation_active else "no",
        spouse_aggregation_active=profile.spouse_aggregation_active,
        spouse_usaha_omzet_ytd=profile.spouse_current_year_usaha_omzet_idr,
        spouse_prior_year_omzet=0,
        prior_year_usaha_omzet=None if prior_user is None else prior_user.usaha_idr,
        prior_year_pekerjaan_bebas_omzet=(
            None if prior_user is None else prior_user.pekerjaan_bebas_idr
        ),
        prior_year_already_final_omzet=(
            None if prior_user is None else prior_user.already_final_idr
        ),
        is_new_taxpayer_current_year=profile.is_new_taxpayer_current_year,
        spouse_current_pekerjaan_bebas_omzet=(
            profile.spouse_current_year_pekerjaan_bebas_omzet_idr
        ),
        spouse_current_already_final_omzet=(profile.spouse_current_year_already_final_omzet_idr),
        prior_spouse_usaha_omzet=(None if prior_spouse is None else prior_spouse.usaha_idr),
        prior_spouse_pekerjaan_bebas_omzet=(
            None if prior_spouse is None else prior_spouse.pekerjaan_bebas_idr
        ),
        prior_spouse_already_final_omzet=(
            None if prior_spouse is None else prior_spouse.already_final_idr
        ),
    )


def engine_transactions(rows: list[TransactionIn]) -> list[Transaction]:
    """Map wire rows onto engine transactions."""
    return [
        Transaction(
            id=row.id,
            amount=row.amount_idr,
            date=row.tx_date.isoformat(),
            category=row.category,
            withheld_tax_amount=row.withheld_tax_amount_idr,
        )
        for row in rows
    ]


def engine_snapshot(
    transactions: list[Transaction],
    profile: Profile,
    ruleset: Ruleset,
    as_of_date: date | str,
) -> Snapshot:
    """Run the deterministic engine. No model, no storage."""
    return compute(transactions, profile, ruleset, as_of_date)


def _eligibility_status(snapshot: Snapshot) -> str:
    if snapshot.prior_year_resolution_source == "unverifiable":
        return "unverifiable"
    if snapshot.prior_year_ineligible:
        return "scheme_ineligible"
    return "scheme_eligible"


def build_snapshot(request: SnapshotIn, ruleset: Ruleset) -> SnapshotOut:
    """Run the deterministic engine and shape one wire response."""
    profile = engine_profile(request.profile)
    transactions = engine_transactions(request.transactions)
    snapshot = engine_snapshot(transactions, profile, ruleset, request.as_of_date)
    return to_wire(request, snapshot, profile, ruleset)


def to_wire(
    request: SnapshotIn,
    snapshot: Snapshot,
    profile: Profile,
    ruleset: Ruleset,
) -> SnapshotOut:
    """Render every month from January through the as-of month."""
    status = _eligibility_status(snapshot)
    as_of_month = request.as_of_date.strftime("%Y-%m")
    existing = {month.month: month for month in snapshot.months}

    by_month: dict[str, dict[str, int]] = {}
    for row in request.transactions:
        key = row.tx_date.strftime("%Y-%m")
        bucket = by_month.setdefault(
            key,
            {
                "pekerjaan_bebas": 0,
                "already_final": 0,
                "non_object": 0,
            },
        )
        if row.category in bucket:
            bucket[row.category] += row.amount_idr

    months: list[MonthOut] = []
    for month in _month_range(request.tax_year, as_of_month):
        engine_month = existing.get(month)
        bucket = by_month.get(month, {})
        months.append(
            MonthOut(
                month=month,
                input_hash=(
                    engine_month.input_hash
                    if engine_month
                    else month_input_hash(
                        [
                            tx
                            for tx in engine_transactions(request.transactions)
                            if tx.date[:7] == month
                        ],
                        profile,
                        ruleset,
                        month,
                    )
                ),
                scheme_eligibility_status=status,
                usaha_omzet_idr=engine_month.usaha_omzet if engine_month else 0,
                porsi_bebas_idr=engine_month.exempt if engine_month else 0,
                porsi_kena_idr=engine_month.taxable if engine_month else 0,
                tax_0_5_pct_idr=engine_month.final_tax if engine_month else 0,
                withheld_tax_idr=engine_month.withheld if engine_month else 0,
                sisa_bayar_idr=engine_month.sisa_bayar_idr if engine_month else 0,
                overwithheld_excess_idr=(
                    engine_month.overwithheld_excess_idr if engine_month else 0
                ),
                overwithheld_status=engine_month.withhold_status if engine_month else "nihil",
                pekerjaan_bebas_omzet_idr=bucket.get("pekerjaan_bebas", 0),
                already_final_omzet_idr=bucket.get("already_final", 0),
                non_object_omzet_idr=bucket.get("non_object", 0),
            )
        )

    spouse_current = (
        profile.spouse_usaha_omzet_ytd
        + profile.spouse_current_pekerjaan_bebas_omzet
        + profile.spouse_current_already_final_omzet
        if profile.spouse_aggregation_active and ruleset.spouse_in_cap
        else 0
    )
    current_combined = (
        snapshot.ytd_usaha_omzet
        + snapshot.pekerjaan_bebas_total
        + snapshot.already_final_total
        + spouse_current
    )
    return SnapshotOut(
        tax_year=request.tax_year,
        as_of_date=request.as_of_date.isoformat(),
        ruleset_id=snapshot.ruleset_id,
        effective_date=ruleset.effective_date,
        rounding_rule=ruleset.rounding_rule,
        scheme_eligibility_status=status,
        prior_year_resolution_source=snapshot.prior_year_resolution_source,
        prior_year_combined_gross_idr=snapshot.prior_year_gross_revenue,
        current_year_combined_gross_idr=current_combined,
        next_year_ineligible=snapshot.next_year_at_risk,
        spouse_aggregation_active=profile.spouse_aggregation_active,
        remaining_free_band_idr=snapshot.exemption_remaining,
        months=tuple(months),
        disclaimer=DISCLAIMER,
    )


def _month_range(tax_year: int, last_month: str) -> list[str]:
    last = int(last_month[:7].split("-")[1])
    return [f"{tax_year}-{month:02d}" for month in range(1, last + 1)]
