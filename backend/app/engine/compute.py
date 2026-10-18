"""Deterministic Final PPh engine.

The language model is not used here. Inputs are classified transactions,
profile threshold flags, a ruleset, and an as-of date.

Calculation order:
1. Only category usaha counts as omzet for the 0.5% base.
2. Scheme eligibility for the current year is decided by prior-year gross
   revenue alone: usaha + pekerjaan_bebas + already_final, gross (Pasal 58
   ayat (1) huruf a), plus spouse gross when the Pasal 58 aggregation flag is
   set and the ruleset says spouse omzet joins the cap. Over the cap, every
   usaha row of the current year is scheme_ineligible and taxed 0.
3. Otherwise usaha is walked in calendar-date order, then id.
4. Spouse omzet only participates when the profile sets
   spouse_aggregation_active. Whether it fills the free band or only the
   eligibility cap is a ruleset switch (FR-21, PMK 164/2023 Lampiran B).
5. User omzet inside the free band is exempt. User omzet above the band is
   taxed at the ruleset rate and rounded by the ruleset rounding rule.
6. Crossing the cap in the current year does NOT change the current year's
   rate. It only sets current_year_crossed_cap, which tells the reader the
   next tax year is at risk (FR-20, Pasal 57 ayat (2) huruf e dan ayat (4)).
7. Withholding is reconciled per month against the month's tax. An excess is
   surfaced as belum_diperhitungkan, never carried forward (FR-23).

Callers must pass Asia/Jakarta calendar dates. This module does not convert
timestamps.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

from app.engine.types import (
    PRIOR_YEAR_REPORTED,
    PRIOR_YEAR_UNSET,
    PRIOR_YEAR_UNVERIFIABLE,
    WITHHOLD_BELUM_DIPERHITUNGKAN,
    WITHHOLD_KURANG_POTONG,
    WITHHOLD_NIHIL,
    Line,
    MonthSummary,
    Profile,
    Ruleset,
    Snapshot,
    Transaction,
)

_CATEGORIES = frozenset({"usaha", "pekerjaan_bebas", "already_final", "non_object"})
_CAP_CATEGORIES = frozenset({"pekerjaan_bebas", "already_final"})
_SPOUSE_FLAGS = frozenset({"yes", "no", "unknown"})
_ROUNDING_RULES = frozenset({"floor", "round_half_up"})

#: SRS FR-22 pins the canonical hash format with a version prefix.
_INPUT_HASH_PREFIX = "v1:"


def disclaimer(ruleset_id: str, as_of_date: str) -> str:
    """Sentence required on every screen that shows a tax amount."""
    return (
        f"Computation under ruleset {ruleset_id} as of {as_of_date}. "
        "Not a filed return. Consult a licensed tax consultant for filing."
    )


def month_input_hash(
    transactions: list[Transaction] | tuple[Transaction, ...],
    profile: Profile,
    ruleset: Ruleset,
    month: str,
) -> str:
    """Canonical digest for one month, including a month with no rows.

    API v1.2.2 section 2.4 requires every month through the as-of month to
    carry a real digest even when its transaction list is empty.
    """
    _validate_ruleset(ruleset)
    _validate_profile(profile)
    ordered = tuple(
        sorted((_normalize(tx) for tx in transactions), key=lambda tx: (tx.date, tx.id))
    )
    return _input_hash(ordered, profile, ruleset, month)


def compute(
    transactions: list[Transaction] | tuple[Transaction, ...],
    profile: Profile,
    ruleset: Ruleset,
    as_of_date: str | date | None = None,
) -> Snapshot:
    """Return a tax snapshot. Same inputs and ruleset always return the same figures."""
    _validate_ruleset(ruleset)
    _validate_profile(profile)
    labeled_as_of = _date_str(ruleset.effective_date if as_of_date is None else as_of_date)
    normalized = tuple(_normalize(tx) for tx in transactions)
    ordered = tuple(sorted(normalized, key=lambda tx: (tx.date, tx.id)))

    spouse_ytd, spouse_prior = _spouse_figures(profile, ruleset)
    cap_spouse_prior = spouse_prior if ruleset.spouse_in_cap else 0
    cap_spouse_ytd = spouse_ytd if ruleset.spouse_in_cap else 0

    prior_gross, prior_source = _prior_gross_revenue(profile)
    prior_gross += cap_spouse_prior
    if prior_source == PRIOR_YEAR_UNSET and cap_spouse_prior:
        prior_source = f"{PRIOR_YEAR_UNSET}+spouse"
    prior_ineligible = prior_source == PRIOR_YEAR_UNVERIFIABLE or _over_cap(
        prior_gross, ruleset.eligibility_cap_idr, ruleset.ineligible_when
    )

    lines = _allocate(ordered, ruleset, prior_ineligible, spouse_ytd)
    months = _months(lines, ordered, profile, ruleset)
    ytd = sum(line.counted_in_usaha_omzet for line in lines)
    exempt = sum(line.exempt for line in lines)
    taxable = sum(line.taxable for line in lines)
    ineligible_amt = sum(line.scheme_ineligible_amount for line in lines)
    if prior_ineligible:
        exemption_used = 0
        exemption_remaining = 0
    else:
        exemption_used = min(ruleset.exemption_band_idr, exempt + taxable)
        exemption_remaining = ruleset.exemption_band_idr - exemption_used
    current_gross = ytd + sum(line.amount for line in lines if line.category in _CAP_CATEGORIES)
    next_year_at_risk = _over_cap(
        current_gross + cap_spouse_ytd, ruleset.eligibility_cap_idr, ruleset.ineligible_when
    )
    return Snapshot(
        ruleset_id=ruleset.ruleset_id,
        as_of_date=labeled_as_of,
        input_hash=_input_hash(ordered, profile, ruleset, None),
        disclaimer=disclaimer(ruleset.ruleset_id, labeled_as_of),
        kap_kjs=ruleset.kap_kjs,
        prior_year_ineligible=prior_ineligible,
        current_year_crossed_cap=next_year_at_risk,
        next_year_at_risk=next_year_at_risk,
        prior_year_resolution_source=prior_source,
        prior_year_gross_revenue=prior_gross,
        ytd_usaha_omzet=ytd,
        spouse_omzet_applied=spouse_ytd,
        aggregated_omzet=spouse_ytd + ytd,
        exemption_band_idr=ruleset.exemption_band_idr,
        exemption_used=exemption_used,
        exemption_remaining=exemption_remaining,
        exempt_omzet=exempt,
        taxable_omzet=taxable,
        scheme_ineligible_omzet=ineligible_amt,
        final_tax=sum(line.final_tax for line in lines),
        withheld=sum(line.withheld_tax_amount for line in lines if line.category == "usaha"),
        self_paid=sum(line.self_paid for line in lines),
        overwithheld_excess_idr=sum(month.overwithheld_excess_idr for month in months),
        pekerjaan_bebas_total=sum(
            line.amount for line in lines if line.category == "pekerjaan_bebas"
        ),
        already_final_total=sum(line.amount for line in lines if line.category == "already_final"),
        non_object_total=sum(line.amount for line in lines if line.category == "non_object"),
        lines=lines,
        months=months,
    )


def _spouse_figures(profile: Profile, ruleset: Ruleset) -> tuple[int, int]:
    """Spouse omzet that participates at all.

    Marital status on its own changes no figure. Only the Pasal 58 aggregation
    flag does, per FR-21 and UC-13b, which keep it separate from the FR-03
    marital-status field. Current and prior figures are summed across the three
    categories that join the cap.
    """
    if not profile.spouse_aggregation_active:
        return 0, 0
    current = (
        profile.spouse_usaha_omzet_ytd
        + profile.spouse_current_pekerjaan_bebas_omzet
        + profile.spouse_current_already_final_omzet
    )
    prior_values = (
        profile.spouse_prior_year_omzet,
        profile.prior_spouse_usaha_omzet,
        profile.prior_spouse_pekerjaan_bebas_omzet,
        profile.prior_spouse_already_final_omzet,
    )
    prior = sum(value for value in prior_values if value is not None)
    return current, prior


def _allocate(
    ordered: tuple[Transaction, ...],
    ruleset: Ruleset,
    prior_ineligible: bool,
    spouse_ytd: int,
) -> tuple[Line, ...]:
    """Split usaha rows into the free portion and the rounded taxable portion.

    Rounding is done once per month cumulatively across rows in the same
    calendar month, rather than rounding each row independently.

    Crossing the cap in the current year is not decided here. It is read from
    the snapshot's aggregated gross, so kerja bebas and already_final count.
    """
    band = ruleset.exemption_band_idr
    if ruleset.spouse_in_band:
        band = max(0, band - spouse_ytd)
    user_before = 0
    month_taxable: dict[str, int] = {}
    month_tax: dict[str, int] = {}
    lines: list[Line] = []
    for tx in ordered:
        if tx.category != "usaha":
            lines.append(_other_line(tx))
            continue
        if prior_ineligible:
            lines.append(_ineligible_line(tx))
            user_before += tx.amount
            continue
        band_left = max(0, band - user_before)
        exempt = min(tx.amount, band_left)
        taxable = tx.amount - exempt

        m = tx.date[:7]
        prev_cum_taxable = month_taxable.get(m, 0)
        new_cum_taxable = prev_cum_taxable + taxable
        month_taxable[m] = new_cum_taxable

        prev_cum_tax = month_tax.get(m, 0)
        new_cum_tax = _tax(new_cum_taxable, ruleset)
        month_tax[m] = new_cum_tax

        line_tax = new_cum_tax - prev_cum_tax
        lines.append(_usaha_line(tx, exempt=exempt, taxable=taxable, tax=line_tax))
        user_before += tx.amount
    return tuple(lines)


def _prior_gross_revenue(profile: Profile) -> tuple[int, str]:
    """Prior-year gross revenue that decides scheme eligibility (Pasal 58(1)(a)).

    Returns the amount and how it was resolved. The three sources are the API
    spec enum. ``None`` on the new-taxpayer flag is the legacy engine-fixture
    form and infers the source: any supplied figure means a manually reported
    profile, no figures at all means a first-year taxpayer.
    """
    user_values = (
        profile.prior_year_usaha_omzet,
        profile.prior_year_pekerjaan_bebas_omzet,
        profile.prior_year_already_final_omzet,
    )
    spouse_values = (
        profile.prior_spouse_usaha_omzet,
        profile.prior_spouse_pekerjaan_bebas_omzet,
        profile.prior_spouse_already_final_omzet,
    )
    if profile.is_new_taxpayer_current_year is True:
        return 0, PRIOR_YEAR_UNSET
    supplied = any(value is not None for value in user_values + spouse_values)
    if supplied:
        return sum(value for value in user_values if value is not None), PRIOR_YEAR_REPORTED
    if profile.is_new_taxpayer_current_year is False:
        return 0, PRIOR_YEAR_UNVERIFIABLE
    return 0, PRIOR_YEAR_UNSET


def _usaha_line(
    tx: Transaction,
    *,
    exempt: int,
    taxable: int,
    tax: int,
) -> Line:
    return Line(
        transaction_id=tx.id,
        date=tx.date,
        month=tx.date[:7],
        category=tx.category,
        amount=tx.amount,
        withheld_tax_amount=tx.withheld_tax_amount,
        counted_in_usaha_omzet=tx.amount,
        exempt=exempt,
        taxable=taxable,
        scheme_ineligible_amount=0,
        scheme_ineligible=False,
        final_tax=tax,
        self_paid=_self_paid(tax, tx.withheld_tax_amount),
    )


def _ineligible_line(tx: Transaction) -> Line:
    """A row that cannot use the Final scheme because of the prior-year cap."""
    return Line(
        transaction_id=tx.id,
        date=tx.date,
        month=tx.date[:7],
        category=tx.category,
        amount=tx.amount,
        withheld_tax_amount=tx.withheld_tax_amount,
        counted_in_usaha_omzet=tx.amount,
        exempt=0,
        taxable=0,
        scheme_ineligible_amount=tx.amount,
        scheme_ineligible=True,
        final_tax=0,
        self_paid=0,
    )


def _other_line(tx: Transaction) -> Line:
    return Line(
        transaction_id=tx.id,
        date=tx.date,
        month=tx.date[:7],
        category=tx.category,
        amount=tx.amount,
        withheld_tax_amount=tx.withheld_tax_amount,
        counted_in_usaha_omzet=0,
        exempt=0,
        taxable=0,
        scheme_ineligible_amount=0,
        scheme_ineligible=False,
        final_tax=0,
        self_paid=0,
    )


def _withhold_status(tax: int, withheld: int) -> str:
    """Reconcile one month of withholding against that month's tax (FR-23)."""
    if withheld > tax:
        return WITHHOLD_BELUM_DIPERHITUNGKAN
    if tax > withheld:
        return WITHHOLD_KURANG_POTONG
    return WITHHOLD_NIHIL


def _months(
    lines: tuple[Line, ...],
    ordered: tuple[Transaction, ...],
    profile: Profile,
    ruleset: Ruleset,
) -> tuple[MonthSummary, ...]:
    """Usaha totals and withholding reconciliation per calendar month.

    ``self_paid`` is the sum of the per-row clamped figures and can differ from
    ``sisa_bayar_idr``, which is the authoritative FR-23 monthly reconciliation
    of the month's summed withholding against the month's tax.
    """
    buckets: dict[str, list[int]] = {}
    for line in lines:
        if line.category != "usaha":
            continue
        row = buckets.setdefault(line.month, [0, 0, 0, 0, 0, 0, 0])
        row[0] += line.counted_in_usaha_omzet
        row[1] += line.exempt
        row[2] += line.taxable
        row[3] += line.scheme_ineligible_amount
        row[4] += line.final_tax
        row[5] += line.withheld_tax_amount
        row[6] += line.self_paid
    return tuple(
        MonthSummary(
            month=month,
            usaha_omzet=row[0],
            exempt=row[1],
            taxable=row[2],
            scheme_ineligible_amount=row[3],
            final_tax=row[4],
            withheld=row[5],
            self_paid=row[6],
            sisa_bayar_idr=max(0, row[4] - row[5]),
            overwithheld_excess_idr=max(0, row[5] - row[4]),
            withhold_status=_withhold_status(row[4], row[5]),
            input_hash=_input_hash(ordered, profile, ruleset, month),
        )
        for month, row in sorted(buckets.items())
    )


def _tax(taxable: int, ruleset: Ruleset) -> int:
    """Tax one taxable amount, rounded by the ruleset rounding rule."""
    if taxable == 0:
        return 0
    numerator = taxable * ruleset.final_rate_numerator
    denominator = ruleset.final_rate_denominator
    if ruleset.rounding_rule == "floor":
        return numerator // denominator
    if ruleset.rounding_rule == "round_half_up":
        return (2 * numerator + denominator) // (2 * denominator)
    raise ValueError("rounding_rule must be floor or round_half_up")


def _self_paid(tax: int, withheld: int) -> int:
    remaining = tax - withheld
    if remaining < 0:
        return 0
    return remaining


def _input_hash(
    ordered: tuple[Transaction, ...],
    profile: Profile,
    ruleset: Ruleset,
    month: str | None,
) -> str:
    """Canonical SHA-256 digest over everything that can move a figure.

    API v1.2.2 section 4 pins the payload: sorted keys, no separator
    whitespace, UTF-8, pure integers, ISO-8601 dates, and a ``v1:`` version
    prefix. A month hashes only that month's transactions. Fields that cannot
    change a result, such as a computation timestamp or display-only
    ``rate_str``, are absent by construction.
    """
    _, prior_source = _prior_gross_revenue(profile)
    new_taxpayer = profile.is_new_taxpayer_current_year
    if not isinstance(new_taxpayer, bool):
        new_taxpayer = prior_source == PRIOR_YEAR_UNSET
    spouse_prior_usaha = profile.prior_spouse_usaha_omzet
    if spouse_prior_usaha is None and profile.spouse_prior_year_omzet:
        spouse_prior_usaha = profile.spouse_prior_year_omzet
    selected = ordered if month is None else tuple(tx for tx in ordered if tx.date[:7] == month)
    payload = {
        "month": month,
        "profile_context": {
            "is_new_taxpayer_current_year": new_taxpayer,
            "prior_year_gross_spouse": {
                "already_final_idr": profile.prior_spouse_already_final_omzet or 0,
                "pekerjaan_bebas_idr": profile.prior_spouse_pekerjaan_bebas_omzet or 0,
                "usaha_idr": spouse_prior_usaha or 0,
            },
            "prior_year_gross_user": {
                "already_final_idr": profile.prior_year_already_final_omzet or 0,
                "pekerjaan_bebas_idr": profile.prior_year_pekerjaan_bebas_omzet or 0,
                "usaha_idr": profile.prior_year_usaha_omzet or 0,
            },
            "prior_year_resolution_source": prior_source,
            "spouse_aggregation_active": profile.spouse_aggregation_active,
            "spouse_current_year_already_final_omzet_idr": (
                profile.spouse_current_already_final_omzet
            ),
            "spouse_current_year_pekerjaan_bebas_omzet_idr": (
                profile.spouse_current_pekerjaan_bebas_omzet
            ),
            "spouse_current_year_usaha_omzet_idr": profile.spouse_usaha_omzet_ytd,
        },
        "ruleset": {
            "effective_date": ruleset.effective_date,
            "free_band_idr": ruleset.exemption_band_idr,
            "gross_cap_idr": ruleset.eligibility_cap_idr,
            "rate_denominator": ruleset.final_rate_denominator,
            "rate_numerator": ruleset.final_rate_numerator,
            "rounding_rule": ruleset.rounding_rule,
            "ruleset_id": ruleset.ruleset_id,
            "spouse_in_band": ruleset.spouse_in_band,
            "spouse_in_cap": ruleset.spouse_in_cap,
        },
        "tax_year": ruleset.tax_year,
        "transactions": [
            {
                "amount_idr": tx.amount,
                "category": tx.category,
                "id": tx.id,
                "tx_date": tx.date,
                "withheld_tax_amount_idr": tx.withheld_tax_amount,
            }
            for tx in selected
        ],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return _INPUT_HASH_PREFIX + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize(tx: Transaction) -> Transaction:
    if not isinstance(tx, Transaction):
        raise TypeError("transactions must be Transaction instances")
    if not isinstance(tx.id, str) or tx.id.strip() == "":
        raise ValueError("transaction id must be a non-empty string")
    _rupiah("amount", tx.amount, allow_zero=False)
    _rupiah("withheld_tax_amount", tx.withheld_tax_amount, allow_zero=True)
    if tx.category not in _CATEGORIES:
        raise ValueError("category must be usaha, pekerjaan_bebas, already_final, or non_object")
    return Transaction(
        id=tx.id,
        amount=tx.amount,
        date=_date_str(tx.date),
        category=tx.category,
        withheld_tax_amount=tx.withheld_tax_amount,
    )


def _validate_profile(profile: Profile) -> None:
    if not isinstance(profile, Profile):
        raise TypeError("profile must be a Profile")
    if profile.spouse_has_usaha_income not in _SPOUSE_FLAGS:
        raise ValueError("spouse_has_usaha_income must be yes, no, or unknown")
    if not isinstance(profile.spouse_aggregation_active, bool):
        raise TypeError("spouse_aggregation_active must be a bool")
    _rupiah("spouse_usaha_omzet_ytd", profile.spouse_usaha_omzet_ytd, allow_zero=True)
    _rupiah("spouse_prior_year_omzet", profile.spouse_prior_year_omzet, allow_zero=True)
    _rupiah(
        "spouse_current_pekerjaan_bebas_omzet",
        profile.spouse_current_pekerjaan_bebas_omzet,
        allow_zero=True,
    )
    _rupiah(
        "spouse_current_already_final_omzet",
        profile.spouse_current_already_final_omzet,
        allow_zero=True,
    )
    for name in (
        "prior_year_usaha_omzet",
        "prior_year_pekerjaan_bebas_omzet",
        "prior_year_already_final_omzet",
        "prior_spouse_usaha_omzet",
        "prior_spouse_pekerjaan_bebas_omzet",
        "prior_spouse_already_final_omzet",
    ):
        value = getattr(profile, name)
        if value is not None:
            _rupiah(name, value, allow_zero=True)


def _validate_ruleset(ruleset: Ruleset) -> None:
    if not isinstance(ruleset, Ruleset):
        raise TypeError("ruleset must be a Ruleset")
    if not isinstance(ruleset.ruleset_id, str) or ruleset.ruleset_id.strip() == "":
        raise ValueError("ruleset_id must be a non-empty string")
    if not isinstance(ruleset.tax_year, int) or isinstance(ruleset.tax_year, bool):
        raise TypeError("tax_year must be an int")
    _date_str(ruleset.effective_date)
    _rupiah("final_rate_numerator", ruleset.final_rate_numerator, allow_zero=True)
    _rupiah("final_rate_denominator", ruleset.final_rate_denominator, allow_zero=False)
    _rupiah("exemption_band_idr", ruleset.exemption_band_idr, allow_zero=True)
    _rupiah("eligibility_cap_idr", ruleset.eligibility_cap_idr, allow_zero=True)
    if ruleset.ineligible_when != "gt":
        raise ValueError("ineligible_when must be gt")
    if ruleset.rounding_rule not in _ROUNDING_RULES:
        raise ValueError("rounding_rule must be floor or round_half_up")
    if not isinstance(ruleset.kap_kjs, str) or ruleset.kap_kjs.strip() == "":
        raise ValueError("kap_kjs must be a non-empty string")
    for name in ("spouse_in_band", "spouse_in_cap"):
        if not isinstance(getattr(ruleset, name), bool):
            raise TypeError(f"{name} must be a bool")


def _over_cap(amount: int, cap: int, when: str) -> bool:
    if when == "gt":
        return amount > cap
    raise ValueError("ineligible_when must be gt")


def _rupiah(name: str, value: int, *, allow_zero: bool) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int rupiah amount")
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name} must be a positive integer rupiah amount")


def _date_str(value: str | date) -> str:
    if isinstance(value, datetime):
        raise TypeError("pass a calendar date, not a timestamp")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise ValueError("date must be YYYY-MM-DD") from exc
    raise TypeError("date must be a date or YYYY-MM-DD string")
