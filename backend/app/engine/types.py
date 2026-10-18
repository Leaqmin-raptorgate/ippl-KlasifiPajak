"""Value types for the tax engine. Amounts are integer rupiah."""

from dataclasses import dataclass

#: Categories accepted by the engine. Mirrors the SRS FR-10 enum.
CATEGORIES = ("usaha", "pekerjaan_bebas", "already_final", "non_object")

#: How a prior-year gross figure was resolved. The wire values are the three
#: API v1.2.2 enum members; the legacy names stay as aliases so existing
#: engine tests keep reading the same intent.
PRIOR_YEAR_UNSET = "first_year_taxpayer"
PRIOR_YEAR_REPORTED = "manual_profile"
PRIOR_YEAR_UNVERIFIABLE = "unverifiable"

#: Withholding reconciliation states, SRS FR-23 and TC-WITHHOLD-EQUAL.
WITHHOLD_NIHIL = "nihil"
WITHHOLD_KURANG_POTONG = "kurang_potong"
WITHHOLD_BELUM_DIPERHITUNGKAN = "belum_diperhitungkan"


@dataclass(frozen=True)
class Transaction:
    """One classified income row."""

    id: str
    amount: int
    date: str
    category: str
    withheld_tax_amount: int = 0


@dataclass(frozen=True)
class Profile:
    """Threshold inputs. This app taxes only the user's own transactions.

    Prior-year gross revenue is split by category because PP 20/2026 Pasal 58
    ayat (1) huruf a aggregates usaha and pekerjaan bebas, final or not, to
    decide scheme eligibility for the year being computed.

    The three ``prior_year_*`` fields are optional on purpose. SRS FR-03
    requires an empty field to read as *not filled in*, not as zero, so a new
    taxpayer with no history stays distinguishable from a taxpayer who
    genuinely reported nil. ``None`` means unset.

    ``spouse_has_usaha_income`` and ``spouse_aggregation_active`` are separate
    fields. FR-03 records marital status; FR-21 and UC-13b record the Pasal 58
    aggregation flag. Neither is derived from the other.
    """

    spouse_has_usaha_income: str = "unknown"
    spouse_aggregation_active: bool = False
    spouse_usaha_omzet_ytd: int = 0
    spouse_prior_year_omzet: int = 0
    prior_year_usaha_omzet: int | None = None
    prior_year_pekerjaan_bebas_omzet: int | None = None
    prior_year_already_final_omzet: int | None = None
    is_new_taxpayer_current_year: bool | None = None
    spouse_current_pekerjaan_bebas_omzet: int = 0
    spouse_current_already_final_omzet: int = 0
    prior_spouse_usaha_omzet: int | None = None
    prior_spouse_pekerjaan_bebas_omzet: int | None = None
    prior_spouse_already_final_omzet: int | None = None


@dataclass(frozen=True)
class Ruleset:
    """Numeric rules loaded from data. The engine does not hardcode rates."""

    ruleset_id: str
    tax_year: int
    effective_date: str
    final_rate_numerator: int
    final_rate_denominator: int
    exemption_band_idr: int
    eligibility_cap_idr: int
    ineligible_when: str
    kap_kjs: str
    rounding_rule: str = "floor"
    spouse_in_band: bool = False
    spouse_in_cap: bool = True
    rate_str: str = ""
    quota_ai_classification: int = 200
    quota_assistant_chat: int = 200


@dataclass(frozen=True)
class Line:
    """How one transaction was treated."""

    transaction_id: str
    date: str
    month: str
    category: str
    amount: int
    withheld_tax_amount: int
    counted_in_usaha_omzet: int
    exempt: int
    taxable: int
    scheme_ineligible_amount: int
    scheme_ineligible: bool
    final_tax: int
    self_paid: int


@dataclass(frozen=True)
class MonthSummary:
    """Usaha totals for one calendar month.

    Withholding is reconciled per month, not per row, because SRS FR-23 sums
    ``withheld_tax_amount_idr`` for the month and compares it against that
    month's tax. Both figures are non-negative and any excess is surfaced,
    never carried into another month.
    """

    month: str
    usaha_omzet: int
    exempt: int
    taxable: int
    scheme_ineligible_amount: int
    final_tax: int
    withheld: int
    self_paid: int
    sisa_bayar_idr: int
    overwithheld_excess_idr: int
    withhold_status: str
    input_hash: str


@dataclass(frozen=True)
class Snapshot:
    """Result of one calculation. Figures are integer rupiah."""

    ruleset_id: str
    as_of_date: str
    input_hash: str
    disclaimer: str
    kap_kjs: str
    prior_year_ineligible: bool
    current_year_crossed_cap: bool
    next_year_at_risk: bool
    prior_year_resolution_source: str
    prior_year_gross_revenue: int
    ytd_usaha_omzet: int
    spouse_omzet_applied: int
    aggregated_omzet: int
    exemption_band_idr: int
    exemption_used: int
    exemption_remaining: int
    exempt_omzet: int
    taxable_omzet: int
    scheme_ineligible_omzet: int
    final_tax: int
    withheld: int
    self_paid: int
    overwithheld_excess_idr: int
    pekerjaan_bebas_total: int
    already_final_total: int
    non_object_total: int
    lines: tuple[Line, ...]
    months: tuple[MonthSummary, ...]
