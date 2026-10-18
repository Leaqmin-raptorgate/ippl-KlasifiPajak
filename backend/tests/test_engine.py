"""Engine checks that are not appendix golden cases."""

from datetime import date, datetime
from pathlib import Path

import pytest

from app.engine import Profile, Transaction, compute

BAND = 500_000_000


def _tx(tx_id, amount, on="2026-01-15", category="usaha", withheld=0):
    return Transaction(
        id=tx_id,
        amount=amount,
        date=on,
        category=category,
        withheld_tax_amount=withheld,
    )


def test_omzet_inside_the_band_is_exempt(ruleset):
    snapshot = compute([_tx("small", 1_000_000)], Profile(), ruleset)
    assert snapshot.final_tax == 0
    assert snapshot.exempt_omzet == 1_000_000
    assert snapshot.exemption_remaining == BAND - 1_000_000


def test_spouse_omzet_is_ignored_without_the_pasal_58_flag(ruleset):
    """FR-21 / UC-13b: marital status alone never moves a figure."""
    snapshot = compute(
        [_tx("user", 350_000_000)],
        Profile(spouse_has_usaha_income="yes", spouse_usaha_omzet_ytd=200_000_000),
        ruleset,
    )
    assert snapshot.spouse_omzet_applied == 0
    assert snapshot.taxable_omzet == 0
    assert snapshot.final_tax == 0


def test_crossing_the_cap_in_the_current_year_keeps_the_rate(ruleset):
    """FR-20: over the cap this year is next year's problem, not this year's rate.

    PP 20/2026 Pasal 57 ayat (2) huruf e and ayat (4) put the loss of the Final
    scheme on the following tax years. The crossing year is still taxed at 0.5%
    through December.
    """
    snapshot = compute(
        [
            _tx("under", 4_700_000_000, "2026-03-01"),
            _tx("cross", 200_000_000, "2026-04-01"),
        ],
        Profile(),
        ruleset,
    )
    cross = next(line for line in snapshot.lines if line.transaction_id == "cross")
    assert snapshot.current_year_crossed_cap is True
    assert snapshot.next_year_at_risk is True
    assert snapshot.prior_year_ineligible is False
    assert cross.scheme_ineligible is False
    assert cross.taxable == 200_000_000
    assert cross.final_tax == 1_000_000
    assert snapshot.final_tax == 21_000_000 + 1_000_000


def test_same_inputs_are_bit_identical(ruleset):
    rows = [
        _tx("b", 50_000_000, "2026-06-15"),
        _tx("a", 480_000_000, "2026-05-31"),
    ]
    first = compute(rows, Profile(), ruleset)
    second = compute(list(reversed(rows)), Profile(), ruleset)
    assert first == second
    assert first.input_hash == second.input_hash


def test_floor_division_does_not_use_floats(ruleset):
    snapshot = compute(
        [
            _tx("fill", BAND, "2026-01-01"),
            _tx("odd", 100, "2026-01-02"),
        ],
        Profile(),
        ruleset,
    )
    odd = next(line for line in snapshot.lines if line.transaction_id == "odd")
    assert odd.final_tax == 0


def test_rejects_bad_category(ruleset):
    with pytest.raises(ValueError):
        compute([_tx("x", 1_000, category="jasa")], Profile(), ruleset)


def test_rejects_bool_amount(ruleset):
    with pytest.raises(TypeError):
        compute([_tx("x", True)], Profile(), ruleset)


def test_rejects_timestamp(ruleset):
    with pytest.raises(TypeError):
        compute(
            [_tx("x", 1_000, on=datetime(2026, 1, 1, 10, 0))],
            Profile(),
            ruleset,
        )


def test_accepts_date_object(ruleset):
    snapshot = compute(
        [_tx("x", 1_000, on=date(2026, 1, 2))],
        Profile(),
        ruleset,
    )
    assert snapshot.lines[0].date == "2026-01-02"


def test_month_once_rounding_accumulates_taxable_rows_within_same_month(ruleset):
    """Two taxable rows of Rp 100 in the same month yield Rp 1 under floor division."""
    snapshot = compute(
        [
            _tx("fill", BAND, "2026-01-01"),
            _tx("odd1", 100, "2026-01-02"),
            _tx("odd2", 100, "2026-01-03"),
        ],
        Profile(),
        ruleset,
    )
    odd1 = next(line for line in snapshot.lines if line.transaction_id == "odd1")
    odd2 = next(line for line in snapshot.lines if line.transaction_id == "odd2")
    assert odd1.final_tax == 0
    assert odd2.final_tax == 1
    jan = next(m for m in snapshot.months if m.month == "2026-01")
    assert jan.taxable == 200
    assert jan.final_tax == 1
    assert snapshot.final_tax == 1


def test_month_once_rounding_resets_across_different_months(ruleset):
    """Two taxable rows of Rp 100 in separate months each yield Rp 0 under floor division."""
    snapshot = compute(
        [
            _tx("fill", BAND, "2026-01-01"),
            _tx("odd1", 100, "2026-01-02"),
            _tx("odd2", 100, "2026-02-02"),
        ],
        Profile(),
        ruleset,
    )
    odd1 = next(line for line in snapshot.lines if line.transaction_id == "odd1")
    odd2 = next(line for line in snapshot.lines if line.transaction_id == "odd2")
    assert odd1.final_tax == 0
    assert odd2.final_tax == 0
    assert snapshot.final_tax == 0


def test_engine_source_has_no_network_or_rate_literals():
    root = Path(__file__).resolve().parents[1] / "app" / "engine"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for banned in ("httpx", "requests", "urllib", "openai", "openrouter", "socket"):
        assert banned not in text
    assert "500000000" not in text
    assert "4800000000" not in text
