"""Value types for the tax engine. Amounts are integer rupiah."""

from dataclasses import dataclass


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
    """Threshold inputs. This app taxes only the user's own transactions."""

    spouse_has_usaha_income: str = "unknown"
    spouse_usaha_omzet_ytd: int = 0
    prior_year_usaha_omzet: int = 0


@dataclass(frozen=True)
class Ruleset:
    """Numeric rules loaded from data. The engine does not hardcode rates."""

    ruleset_id: str
    as_of_date: str
    final_rate_numerator: int
    final_rate_denominator: int
    exemption_band_idr: int
    eligibility_cap_idr: int
    ineligible_when: str
    kap_kjs: str


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
    """Usaha totals for one calendar month."""

    month: str
    usaha_omzet: int
    exempt: int
    taxable: int
    scheme_ineligible_amount: int
    final_tax: int
    withheld: int
    self_paid: int


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
    pekerjaan_bebas_total: int
    already_final_total: int
    non_object_total: int
    lines: tuple[Line, ...]
    months: tuple[MonthSummary, ...]
