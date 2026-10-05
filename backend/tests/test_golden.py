"""Golden cases from the KlasifiPajak SRS appendix, resolved against the FR text.

Two appendix phrases disagree with the functional requirements. The tests
follow the requirements:

- TC-GOLDEN-RATE. Appendix says "YTD below band" and tax 5_000. FR-4.2 says
  1_000_000 fully taxable usaha yields 5_000, and FR-4.3 exempts omzet inside
  the band. The fixture fills the band first, then taxes the 1_000_000.
- TC-GOLDEN-58. Appendix says exemption remaining is 0 after the first
  50_000_000 of user omzet. FR-4.5 says spouse omzet consumes the shared band
  first. Spouse 200_000_000 leaves 300_000_000. Of the user's 350_000_000,
  300_000_000 is exempt and 50_000_000 is taxable. The 50_000_000 figure is
  the taxable slice.
"""

from app.engine import Profile, Transaction, compute

BAND = 500_000_000


def _tx(tx_id, amount, on, category="usaha", withheld=0):
    return Transaction(
        id=tx_id,
        amount=amount,
        date=on,
        category=category,
        withheld_tax_amount=withheld,
    )


def _profile(**kwargs):
    fields = {
        "spouse_has_usaha_income": "no",
        "spouse_usaha_omzet_ytd": 0,
        "prior_year_usaha_omzet": 0,
    }
    fields.update(kwargs)
    return Profile(**fields)


def _line(snapshot, tx_id):
    return next(line for line in snapshot.lines if line.transaction_id == tx_id)


def test_tc_golden_rate(ruleset):
    """1_000_000 fully taxable usaha is taxed at 0.5% and tagged with the ruleset."""
    snapshot = compute(
        [
            _tx("fill", BAND, "2026-01-15"),
            _tx("taxable", 1_000_000, "2026-02-01"),
        ],
        _profile(),
        ruleset,
        as_of_date="2026-09-26",
    )
    line = _line(snapshot, "taxable")
    assert line.exempt == 0
    assert line.taxable == 1_000_000
    assert line.final_tax == 5_000
    assert snapshot.final_tax == 5_000
    assert snapshot.ruleset_id == "pp20-2026-academic-1"
    assert snapshot.as_of_date == "2026-09-26"
    assert "pp20-2026-academic-1" in snapshot.disclaimer
    assert "2026-09-26" in snapshot.disclaimer
    assert "Not a filed return" in snapshot.disclaimer


def test_tc_golden_split(ruleset):
    """June crosses the band: 20_000_000 exempt, 30_000_000 taxable, tax 150_000."""
    snapshot = compute(
        [
            _tx("may", 480_000_000, "2026-05-31"),
            _tx("june", 50_000_000, "2026-06-15"),
        ],
        _profile(),
        ruleset,
    )
    june = next(month for month in snapshot.months if month.month == "2026-06")
    assert june.exempt == 20_000_000
    assert june.taxable == 30_000_000
    assert june.final_tax == 150_000
    assert snapshot.exemption_remaining == 0
    assert snapshot.final_tax == 150_000


def test_tc_golden_below(ruleset):
    """Year usaha of 400_000_000 stays inside the band, so Final tax is 0."""
    snapshot = compute(
        [_tx("year", 400_000_000, "2026-03-01")],
        _profile(),
        ruleset,
    )
    assert snapshot.ytd_usaha_omzet == 400_000_000
    assert snapshot.exempt_omzet == 400_000_000
    assert snapshot.taxable_omzet == 0
    assert snapshot.final_tax == 0
    assert snapshot.exemption_remaining == 100_000_000


def test_tc_golden_pb(ruleset):
    """Pekerjaan bebas does not enter UMKM omzet or the 0.5% base."""
    snapshot = compute(
        [_tx("fee", 10_000_000, "2026-04-01", category="pekerjaan_bebas")],
        _profile(),
        ruleset,
    )
    assert snapshot.ytd_usaha_omzet == 0
    assert snapshot.final_tax == 0
    assert snapshot.pekerjaan_bebas_total == 10_000_000
    assert _line(snapshot, "fee").counted_in_usaha_omzet == 0


def test_tc_golden_refund(ruleset):
    """A non_object refund does not change usaha omzet."""
    snapshot = compute(
        [
            _tx("sale", 10_000_000, "2026-04-02"),
            _tx("refund", 5_000_000, "2026-04-03", category="non_object"),
        ],
        _profile(),
        ruleset,
    )
    assert snapshot.ytd_usaha_omzet == 10_000_000
    assert snapshot.non_object_total == 5_000_000
    assert snapshot.final_tax == 0


def test_tc_golden_withhold(ruleset):
    """Fully taxable 2_000_000 with 10_000 withheld leaves self-paid 0."""
    snapshot = compute(
        [
            _tx("fill", BAND, "2026-01-20"),
            _tx("paid", 2_000_000, "2026-02-02", withheld=10_000),
        ],
        _profile(),
        ruleset,
    )
    line = _line(snapshot, "paid")
    assert line.final_tax == 10_000
    assert line.self_paid == 0
    assert snapshot.withheld == 10_000


def test_tc_golden_48_prior(ruleset):
    """Prior-year omzet of 4_900_000_000 makes current usaha scheme_ineligible."""
    snapshot = compute(
        [_tx("now", 1_000_000, "2026-01-10")],
        _profile(prior_year_usaha_omzet=4_900_000_000),
        ruleset,
    )
    line = _line(snapshot, "now")
    assert snapshot.prior_year_ineligible is True
    assert line.scheme_ineligible is True
    assert line.final_tax == 0
    assert snapshot.final_tax == 0
    assert snapshot.taxable_omzet == 0
    assert snapshot.ytd_usaha_omzet == 1_000_000


def test_tc_golden_58(ruleset):
    """Spouse 200_000_000 consumes the band first; 50_000_000 of user omzet is taxable."""
    snapshot = compute(
        [_tx("user", 350_000_000, "2026-08-01")],
        _profile(
            spouse_has_usaha_income="yes",
            spouse_usaha_omzet_ytd=200_000_000,
        ),
        ruleset,
    )
    line = _line(snapshot, "user")
    assert snapshot.spouse_omzet_applied == 200_000_000
    assert line.exempt == 300_000_000
    assert line.taxable == 50_000_000
    assert line.final_tax == 250_000
    assert snapshot.exemption_remaining == 0
    assert snapshot.final_tax == 250_000
