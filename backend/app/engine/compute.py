"""Deterministic Final PPh engine.

The language model is not used here. Inputs are classified transactions,
profile threshold flags, a ruleset, and an as-of date.

Calculation order:
1. Only category usaha counts as omzet.
2. If prior-year usaha omzet is over the ruleset cap, the Final scheme does
   not apply. Current usaha is marked scheme_ineligible and taxed 0.
3. Otherwise usaha is walked in calendar-date order, then id.
4. Spouse omzet counts toward the exemption band and the cap only when
   spouse_has_usaha_income is yes. It is not taxed here.
5. User omzet inside the shared exemption band is exempt. User omzet above
   the band and at or below the cap is taxed with integer floor division.
6. User omzet above the cap is scheme_ineligible and not taxed here.
7. Stored withholding reduces that line's self-paid. It is never inferred.

Callers must pass Asia/Jakarta calendar dates. This module does not convert
timestamps.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

from app.engine.types import (
    Line,
    MonthSummary,
    Profile,
    Ruleset,
    Snapshot,
    Transaction,
)

_CATEGORIES = frozenset(
    {"usaha", "pekerjaan_bebas", "already_final", "non_object"}
)
_SPOUSE_FLAGS = frozenset({"yes", "no", "unknown"})


def disclaimer(ruleset_id: str, as_of_date: str) -> str:
    """Sentence required on every screen that shows a tax amount."""
    return (
        f"Computation under ruleset {ruleset_id} as of {as_of_date}. "
        "Not a filed return. Consult a licensed tax consultant for filing."
    )


def compute(
    transactions: list[Transaction] | tuple[Transaction, ...],
    profile: Profile,
    ruleset: Ruleset,
    as_of_date: str | date | None = None,
) -> Snapshot:
    """Return a tax snapshot. Same inputs and ruleset always return the same figures."""
    _validate_ruleset(ruleset)
    _validate_profile(profile)
    labeled_as_of = _date_str(ruleset.as_of_date if as_of_date is None else as_of_date)
    normalized = tuple(_normalize(tx) for tx in transactions)
    ordered = tuple(sorted(normalized, key=lambda tx: (tx.date, tx.id)))
    spouse = (
        profile.spouse_usaha_omzet_ytd
        if profile.spouse_has_usaha_income == "yes"
        else 0
    )
    prior_ineligible = _over_cap(
        profile.prior_year_usaha_omzet,
        ruleset.eligibility_cap_idr,
        ruleset.ineligible_when,
    )
    lines, crossed = _allocate(ordered, ruleset, spouse, prior_ineligible)
    months = _months(lines)
    ytd = sum(line.counted_in_usaha_omzet for line in lines)
    exempt = sum(line.exempt for line in lines)
    taxable = sum(line.taxable for line in lines)
    ineligible_amt = sum(line.scheme_ineligible_amount for line in lines)
    if prior_ineligible:
        exemption_used = 0
        exemption_remaining = 0
    else:
        exemption_used = min(ruleset.exemption_band_idr, spouse + exempt + taxable)
        exemption_remaining = ruleset.exemption_band_idr - exemption_used
    return Snapshot(
        ruleset_id=ruleset.ruleset_id,
        as_of_date=labeled_as_of,
        input_hash=_input_hash(ordered, profile, ruleset),
        disclaimer=disclaimer(ruleset.ruleset_id, labeled_as_of),
        kap_kjs=ruleset.kap_kjs,
        prior_year_ineligible=prior_ineligible,
        current_year_crossed_cap=crossed,
        ytd_usaha_omzet=ytd,
        spouse_omzet_applied=spouse,
        aggregated_omzet=spouse + ytd,
        exemption_band_idr=ruleset.exemption_band_idr,
        exemption_used=exemption_used,
        exemption_remaining=exemption_remaining,
        exempt_omzet=exempt,
        taxable_omzet=taxable,
        scheme_ineligible_omzet=ineligible_amt,
        final_tax=sum(line.final_tax for line in lines),
        withheld=sum(
            line.withheld_tax_amount for line in lines if line.category == "usaha"
        ),
        self_paid=sum(line.self_paid for line in lines),
        pekerjaan_bebas_total=sum(
            line.amount for line in lines if line.category == "pekerjaan_bebas"
        ),
        already_final_total=sum(
            line.amount for line in lines if line.category == "already_final"
        ),
        non_object_total=sum(
            line.amount for line in lines if line.category == "non_object"
        ),
        lines=lines,
        months=months,
    )


def _allocate(
    ordered: tuple[Transaction, ...],
    ruleset: Ruleset,
    spouse: int,
    prior_ineligible: bool,
) -> tuple[tuple[Line, ...], bool]:
    cap = ruleset.eligibility_cap_idr
    band = ruleset.exemption_band_idr
    user_before = 0
    crossed = False
    lines: list[Line] = []
    for tx in ordered:
        if tx.category != "usaha":
            lines.append(_other_line(tx))
            continue
        if prior_ineligible or spouse + user_before >= cap:
            if not prior_ineligible:
                crossed = True
            lines.append(_ineligible_line(tx))
            user_before += tx.amount
            continue
        room = cap - (spouse + user_before)
        if tx.amount > room:
            eligible = room
            ineligible = tx.amount - room
            crossed = True
        else:
            eligible = tx.amount
            ineligible = 0
        band_left = band - min(band, spouse + user_before)
        exempt = min(eligible, band_left)
        taxable = eligible - exempt
        tax = _tax(taxable, ruleset)
        lines.append(
            _usaha_line(
                tx,
                exempt=exempt,
                taxable=taxable,
                ineligible=ineligible,
                tax=tax,
            )
        )
        user_before += tx.amount
    return tuple(lines), crossed


def _usaha_line(
    tx: Transaction,
    *,
    exempt: int,
    taxable: int,
    ineligible: int,
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
        scheme_ineligible_amount=ineligible,
        scheme_ineligible=ineligible > 0,
        final_tax=tax,
        self_paid=_self_paid(tax, tx.withheld_tax_amount),
    )


def _ineligible_line(tx: Transaction) -> Line:
    return _usaha_line(tx, exempt=0, taxable=0, ineligible=tx.amount, tax=0)


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


def _months(lines: tuple[Line, ...]) -> tuple[MonthSummary, ...]:
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
        )
        for month, row in sorted(buckets.items())
    )


def _tax(taxable: int, ruleset: Ruleset) -> int:
    return taxable * ruleset.final_rate_numerator // ruleset.final_rate_denominator


def _self_paid(tax: int, withheld: int) -> int:
    remaining = tax - withheld
    if remaining < 0:
        return 0
    return remaining


def _input_hash(
    ordered: tuple[Transaction, ...],
    profile: Profile,
    ruleset: Ruleset,
) -> str:
    payload = {
        "profile": {
            "spouse_has_usaha_income": profile.spouse_has_usaha_income,
            "spouse_usaha_omzet_ytd": profile.spouse_usaha_omzet_ytd,
            "prior_year_usaha_omzet": profile.prior_year_usaha_omzet,
        },
        "ruleset": {
            "ruleset_id": ruleset.ruleset_id,
            "final_rate_numerator": ruleset.final_rate_numerator,
            "final_rate_denominator": ruleset.final_rate_denominator,
            "exemption_band_idr": ruleset.exemption_band_idr,
            "eligibility_cap_idr": ruleset.eligibility_cap_idr,
            "ineligible_when": ruleset.ineligible_when,
        },
        "transactions": [
            {
                "id": tx.id,
                "amount": tx.amount,
                "date": tx.date,
                "category": tx.category,
                "withheld_tax_amount": tx.withheld_tax_amount,
            }
            for tx in ordered
        ],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    _rupiah("spouse_usaha_omzet_ytd", profile.spouse_usaha_omzet_ytd, allow_zero=True)
    _rupiah("prior_year_usaha_omzet", profile.prior_year_usaha_omzet, allow_zero=True)


def _validate_ruleset(ruleset: Ruleset) -> None:
    if not isinstance(ruleset, Ruleset):
        raise TypeError("ruleset must be a Ruleset")
    if not isinstance(ruleset.ruleset_id, str) or ruleset.ruleset_id.strip() == "":
        raise ValueError("ruleset_id must be a non-empty string")
    _date_str(ruleset.as_of_date)
    _rupiah("final_rate_numerator", ruleset.final_rate_numerator, allow_zero=True)
    _rupiah("final_rate_denominator", ruleset.final_rate_denominator, allow_zero=False)
    _rupiah("exemption_band_idr", ruleset.exemption_band_idr, allow_zero=True)
    _rupiah("eligibility_cap_idr", ruleset.eligibility_cap_idr, allow_zero=True)
    if ruleset.ineligible_when != "gt":
        raise ValueError("ineligible_when must be gt")
    if not isinstance(ruleset.kap_kjs, str) or ruleset.kap_kjs.strip() == "":
        raise ValueError("kap_kjs must be a non-empty string")


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
