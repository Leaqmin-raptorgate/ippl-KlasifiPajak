"""Engine checks that are not appendix golden cases."""

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from app.engine import Profile, Transaction, compute
from app.engine.compute import month_input_hash, month_next_year_at_risk

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


def _april_hash(ruleset, rows):
    profile = Profile(is_new_taxpayer_current_year=True)
    return month_input_hash(rows, profile, ruleset, "2026-04")


def test_month_hash_changes_when_an_earlier_usaha_amount_changes(ruleset):
    """FR-22: a month's figures depend on earlier usaha omzet, so its hash does too."""
    base = [_tx("a", 450_000_000, "2026-03-10"), _tx("b", 100_000_000, "2026-04-10")]
    edited = [_tx("a", 600_000_000, "2026-03-10"), _tx("b", 100_000_000, "2026-04-10")]
    assert _april_hash(ruleset, base) != _april_hash(ruleset, edited)


def test_month_hash_changes_when_an_earlier_pekerjaan_bebas_amount_changes(ruleset):
    """FR-22, FR-20: earlier pekerjaan bebas gross moves the cumulative cap position."""
    usaha = _tx("b", 100_000_000, "2026-04-10")
    base = [_tx("a", 1_000_000, "2026-03-10", "pekerjaan_bebas"), usaha]
    edited = [_tx("a", 5_000_000_000, "2026-03-10", "pekerjaan_bebas"), usaha]
    assert _april_hash(ruleset, base) != _april_hash(ruleset, edited)


def test_month_hash_ignores_moving_equal_totals_between_earlier_months(ruleset):
    """FR-22: only the totals before the month matter, not which earlier month holds them."""
    april = _tx("c", 100_000_000, "2026-04-10")
    base = [
        _tx("a", 300_000_000, "2026-01-10"),
        _tx("b", 100_000_000, "2026-02-10"),
        april,
    ]
    shifted = [
        _tx("a", 100_000_000, "2026-01-10"),
        _tx("b", 300_000_000, "2026-02-10"),
        april,
    ]
    assert _april_hash(ruleset, base) == _april_hash(ruleset, shifted)


def test_month_hash_ignores_rows_in_later_months(ruleset):
    """FR-22: rows after the month cannot move its figures, so they leave its hash alone."""
    base = [_tx("a", 450_000_000, "2026-03-10"), _tx("b", 100_000_000, "2026-04-10")]
    with_later = [*base, _tx("c", 700_000_000, "2026-05-10")]
    assert _april_hash(ruleset, base) == _april_hash(ruleset, with_later)


@pytest.mark.parametrize("aggregation", [False, True])
@pytest.mark.parametrize("spouse_in_cap", [False, True])
def test_month_cap_flags_include_spouse_only_when_both_switches_are_active(
    ruleset, aggregation, spouse_in_cap
):
    """FR-20, FR-21: spouse gross at the cap is eligible; one extra rupiah crosses it."""
    ruleset = replace(ruleset, spouse_in_cap=spouse_in_cap)
    third = ruleset.eligibility_cap_idr // 3
    profile = Profile(
        is_new_taxpayer_current_year=True,
        spouse_aggregation_active=aggregation,
        spouse_usaha_omzet_ytd=third,
        spouse_current_pekerjaan_bebas_omzet=third,
        spouse_current_already_final_omzet=ruleset.eligibility_cap_idr - 2 * third,
    )
    rows = [_tx("april", 1, "2026-04-10")]
    snapshot = compute(rows, profile, ruleset, "2026-04-30")
    assert month_next_year_at_risk(rows, profile, ruleset, "2026-01") is False
    expected = aggregation and spouse_in_cap
    assert snapshot.months[0].next_year_at_risk is expected
    assert month_next_year_at_risk(rows, profile, ruleset, "2026-04") is expected
    assert snapshot.next_year_at_risk is expected


def test_engine_source_has_no_network_or_rate_literals():
    root = Path(__file__).resolve().parents[1] / "app" / "engine"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for banned in ("httpx", "requests", "urllib", "openai", "openrouter", "socket"):
        assert banned not in text
    assert "500000000" not in text
    assert "4800000000" not in text


def test_fr20_last_month_cap_flag_matches_snapshot_for_mixed_categories(ruleset):
    """FR-20: non-object income does not count toward the combined gross cap."""
    rows = [
        _tx("business", 200_000_000, "2026-01-10"),
        _tx("freelance", 100_000_000, "2026-02-10", "pekerjaan_bebas"),
        _tx("final", 100_000_000, "2026-03-10", "already_final"),
        _tx("excluded", ruleset.eligibility_cap_idr + 1, "2026-03-11", "non_object"),
        _tx("last", 1_000_000, "2026-04-10"),
    ]
    snapshot = compute(rows, Profile(), ruleset, "2026-04-30")
    assert snapshot.next_year_at_risk is False
    assert snapshot.months[-1].month == "2026-04"
    assert snapshot.months[-1].next_year_at_risk is snapshot.next_year_at_risk


def test_fr22_month_contexts_match_month_summaries_and_empty_month_hashes(ruleset):
    """FR-20, FR-22: contexts agree with computed months and empty-month hashes."""
    from app.engine.compute import month_contexts

    profile = Profile(is_new_taxpayer_current_year=True)
    rows = [
        _tx("march", 450_000_000, "2026-03-10"),
        _tx("april", 100_000_000, "2026-04-10"),
        _tx("freelance", ruleset.eligibility_cap_idr, "2026-05-10", "pekerjaan_bebas"),
    ]
    keys = ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    contexts = month_contexts(rows, profile, ruleset, keys)
    snapshot = compute(rows, profile, ruleset, "2026-06-30")
    assert set(contexts) == set(keys)
    for month in snapshot.months:
        assert contexts[month.month].input_hash == month.input_hash
        assert contexts[month.month].next_year_at_risk is month.next_year_at_risk
    for key in ("2026-02", "2026-05", "2026-06"):
        assert contexts[key].input_hash == month_input_hash(rows, profile, ruleset, key)
        assert contexts[key].next_year_at_risk is month_next_year_at_risk(
            rows, profile, ruleset, key
        )


@pytest.mark.parametrize("month", ["2026-4", "2026-13", "٢٠٢٦-01"])
def test_fr22_month_helpers_reject_invalid_months(ruleset, month):
    """FR-22: month keys use four ASCII year digits and a two-digit calendar month."""
    from app.engine.compute import month_contexts

    for helper in (month_input_hash, month_next_year_at_risk):
        with pytest.raises(ValueError, match="^month must be YYYY-MM$"):
            helper([], Profile(), ruleset, month)
    with pytest.raises(ValueError, match="^month must be YYYY-MM$"):
        month_contexts([], Profile(), ruleset, [month])


def test_fr22_month_helpers_accept_valid_month(ruleset):
    """FR-22: a valid calendar month is accepted by every month helper."""
    from app.engine.compute import month_contexts

    profile = Profile()
    context = month_contexts([], profile, ruleset, ["2026-04"])["2026-04"]
    assert context.input_hash == month_input_hash([], profile, ruleset, "2026-04")
    assert context.next_year_at_risk is month_next_year_at_risk([], profile, ruleset, "2026-04")
