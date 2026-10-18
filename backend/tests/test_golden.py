"""Golden cases from the KlasifiPajak SRS appendix, resolved against the FR text.

Two appendix phrases disagree with the functional requirements. The tests
follow the requirements:

- TC-GOLDEN-RATE. Appendix says "YTD below band" and tax 5_000. FR-4.2 says
   1_000_000 fully taxable usaha yields 5_000, and FR-4.3 exempts omzet inside
   the band. The fixture fills the band first, then taxes the 1_000_000.
- TC-GOLDEN-58. Appendix says exemption remaining is 0 after the first
  50_000_000 of user omzet. The v2.5 provisional TODO(PASAL-58) default keeps
  spouse omzet out of the band, so 350_000_000 of user omzet is all exempt.
  The 50_000_000 figure is the taxable slice only under the older shared-band
  reading, which the provisional default replaced.

TC-GOLDEN-CAP-* cases come from PP 20/2026. Elucidation examples are quoted
from SPEC/KlasifiPajak/PP_20_Tahun_2026.pdf. Arithmetic cases built on Pasal 58
ayat (1) huruf a are labelled arithmetic, not attributed to an elucidation
example.
"""

from dataclasses import replace

from app.engine import Profile, Transaction, compute
from app.engine.types import (
    PRIOR_YEAR_UNSET,
    WITHHOLD_BELUM_DIPERHITUNGKAN,
    WITHHOLD_KURANG_POTONG,
    WITHHOLD_NIHIL,
)

BAND = 500_000_000
CAP = 4_800_000_000


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
        "spouse_aggregation_active": False,
        "spouse_usaha_omzet_ytd": 0,
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


def _ruleset_with(**overrides):
    """The shipped ruleset with a few keys replaced, for rounding checks."""
    from dataclasses import replace

    from app.engine.ruleset import load_ruleset

    return replace(load_ruleset(), **overrides)


def test_tc_golden_58(ruleset):
    """Spouse 200_000_000 does not reduce the user's band. FR-21, PMK 164/2023."""
    snapshot = compute(
        [_tx("user", 350_000_000, "2026-08-01")],
        _profile(
            spouse_has_usaha_income="yes",
            spouse_aggregation_active=True,
            spouse_usaha_omzet_ytd=200_000_000,
        ),
        ruleset,
    )
    line = _line(snapshot, "user")
    assert snapshot.spouse_omzet_applied == 200_000_000
    assert line.exempt == 350_000_000
    assert line.taxable == 0
    assert line.final_tax == 0
    assert snapshot.exemption_remaining == 150_000_000
    assert snapshot.final_tax == 0


# --- TC-ARITH portion tests (SRS FR-18, NFR-03) ---------------------------


def test_tc_arith_500(ruleset):
    """Exactly Rp 500.000.000 cumulatively has a taxable portion of 0."""
    snapshot = compute(
        [
            _tx("jan", 200_000_000, "2026-01-10"),
            _tx("feb", 300_000_000, "2026-02-10"),
        ],
        _profile(),
        ruleset,
    )
    assert snapshot.exempt_omzet == BAND
    assert snapshot.taxable_omzet == 0
    assert snapshot.final_tax == 0
    assert snapshot.exemption_remaining == 0


def test_tc_arith_500001(ruleset):
    """Rp 500.000.001 has a taxable portion of 1, and the tax is 0 both ways."""
    rows = [
        _tx("jan", 200_000_000, "2026-01-10"),
        _tx("feb", 300_000_000, "2026-02-10"),
        _tx("mar", 1, "2026-03-10"),
    ]
    for rule in ("floor", "round_half_up"):
        snapshot = compute(rows, _profile(), _ruleset_with(rounding_rule=rule))
        assert snapshot.exempt_omzet == BAND
        assert snapshot.taxable_omzet == 1
        assert snapshot.final_tax == 0


def test_round_half_up_differs_from_floor_only_above_half_a_rupiah(ruleset):
    """Rounding is a ruleset parameter, and floor stays the default."""
    rows = [_tx("fill", BAND, "2026-01-01"), _tx("odd", 300, "2026-01-02")]
    floor_tax = compute(rows, _profile(), _ruleset_with(rounding_rule="floor"))
    half_tax = compute(rows, _profile(), _ruleset_with(rounding_rule="round_half_up"))
    assert floor_tax.final_tax == 1
    assert half_tax.final_tax == 2
    assert ruleset.rounding_rule == "floor"


# --- TC-GOLDEN-CAP eligibility cases (SRS FR-19, FR-20) --------------------


def test_tc_golden_cap_first_year(ruleset):
    """TC-GOLDEN-CAP-FIRST-YEAR. No prior-year data, so v1 is eligible.

    Nona E registered 10 April 2026 (PP 20/2026 elucidation Contoh 2). Her
    first year has no prior year to check, so the 0.5% scheme applies.
    """
    snapshot = compute(
        [_tx("katering", 1_500_000_000, "2026-05-10")],
        _profile(),
        ruleset,
    )
    assert snapshot.prior_year_gross_revenue == 0
    assert snapshot.prior_year_resolution_source == PRIOR_YEAR_UNSET
    assert snapshot.prior_year_ineligible is False
    assert snapshot.exempt_omzet == BAND
    assert snapshot.taxable_omzet == 1_000_000_000
    assert snapshot.final_tax == 5_000_000


def test_tc_golden_cap_current_year(ruleset):
    """TC-GOLDEN-CAP-CURRENT-YEAR. Crossing the cap keeps this year's rate.

    Nona E, TP 2026: pekerjaan bebas as agen asuransi Rp3.500.000.000 plus
    usaha katering Rp1.500.000.000. The elucidation taxes the katering income
    at Final for 2026 and only removes the scheme for 2027, because the total
    Rp5.000.000.000 exceeded Rp4.800.000.000.
    """
    snapshot = compute(
        [
            _tx("asuransi", 3_500_000_000, "2026-05-10", category="pekerjaan_bebas"),
            _tx("katering", 1_500_000_000, "2026-06-10"),
        ],
        _profile(),
        ruleset,
    )
    assert snapshot.current_year_crossed_cap is True
    assert snapshot.next_year_at_risk is True
    assert snapshot.prior_year_ineligible is False
    assert snapshot.pekerjaan_bebas_total == 3_500_000_000
    assert snapshot.taxable_omzet == 1_000_000_000
    assert snapshot.final_tax == 5_000_000


def test_tc_golden_cap_prior_year(ruleset):
    """TC-GOLDEN-CAP-PRIOR-YEAR. Last year 5,2 Miliar, so this year loses it."""
    snapshot = compute(
        [_tx("now", 1_000_000, "2026-01-10")],
        _profile(prior_year_usaha_omzet=5_200_000_000),
        ruleset,
    )
    line = _line(snapshot, "now")
    assert snapshot.prior_year_gross_revenue == 5_200_000_000
    assert snapshot.prior_year_ineligible is True
    assert line.scheme_ineligible is True
    assert line.final_tax == 0
    assert snapshot.final_tax == 0
    assert snapshot.taxable_omzet == 0
    assert snapshot.ytd_usaha_omzet == 1_000_000


def test_tc_golden_cap_composition_fail(ruleset):
    """TC-GOLDEN-CAP-COMPOSITION-FAIL. Over by category, not by usaha alone.

    Arithmetic case on PP 20/2026 Pasal 58 ayat (1) huruf a, which aggregates
    usaha and pekerjaan bebas, final or not. This is deliberately not labelled
    as an elucidation example: Contoh 1 of Pasal 58 is about a registration
    date and proof documents, not a category sum.
    """
    snapshot = compute(
        [_tx("now", 1_000_000, "2026-01-10")],
        _profile(
            prior_year_usaha_omzet=3_000_000_000,
            prior_year_pekerjaan_bebas_omzet=1_500_000_000,
            prior_year_already_final_omzet=500_000_000,
        ),
        ruleset,
    )
    assert snapshot.prior_year_gross_revenue == 5_000_000_000
    assert snapshot.prior_year_ineligible is True
    assert snapshot.final_tax == 0


def test_tc_golden_cap_composition_pass(ruleset):
    """TC-GOLDEN-CAP-COMPOSITION-PASS. Same usaha, under the cap by category."""
    snapshot = compute(
        [_tx("now", 1_500_000_000, "2026-01-10")],
        _profile(
            prior_year_usaha_omzet=3_000_000_000,
            prior_year_pekerjaan_bebas_omzet=1_000_000_000,
            prior_year_already_final_omzet=500_000_000,
        ),
        ruleset,
    )
    assert snapshot.prior_year_gross_revenue == 4_500_000_000
    assert snapshot.prior_year_ineligible is False
    assert snapshot.exempt_omzet == BAND
    assert snapshot.taxable_omzet == 1_000_000_000
    assert snapshot.final_tax == 5_000_000
    assert snapshot.next_year_at_risk is False


def test_tc_golden_cap_spouse(ruleset):
    """TC-GOLDEN-CAP-SPOUSE. Spouse omzet joins the cap check, not the band.

    Tuan A and Nyonya Y (PP 20/2026 elucidation, Pasal 58 ayat (2)): his notaris
    income Rp3.000.000.000, her butik Rp2.000.000.000, and their child's
    Rp500.000.000 reach Rp5.500.000.000, which removes the scheme for 2027.
    Current-year tax is unchanged (Pasal 57 ayat (4)).
    """
    snapshot = compute(
        [_tx("butik", 2_000_000_000, "2026-06-10")],
        _profile(
            spouse_has_usaha_income="yes",
            spouse_aggregation_active=True,
            spouse_usaha_omzet_ytd=3_500_000_000,
        ),
        ruleset,
    )
    assert snapshot.prior_year_ineligible is False
    assert snapshot.current_year_crossed_cap is True
    assert snapshot.next_year_at_risk is True
    assert snapshot.spouse_omzet_applied == 3_500_000_000
    assert snapshot.exempt_omzet == BAND
    assert snapshot.taxable_omzet == 1_500_000_000
    assert snapshot.final_tax == 7_500_000


def test_tc_golden_cap_spouse_prior_year(ruleset):
    """Prior-year spouse omzet over cap makes current year scheme_ineligible."""
    snapshot = compute(
        [_tx("now", 1_000_000, "2026-01-10")],
        _profile(
            prior_year_usaha_omzet=3_000_000_000,
            spouse_has_usaha_income="yes",
            spouse_aggregation_active=True,
            spouse_prior_year_omzet=2_500_000_000,
        ),
        ruleset,
    )
    assert snapshot.prior_year_gross_revenue == 5_500_000_000
    assert snapshot.prior_year_ineligible is True
    assert snapshot.final_tax == 0


def test_tc_golden_cap_spouse_does_not_reduce_the_band(ruleset):
    """FR-21 with spouse_in_band false: spouse omzet never fills the band."""
    snapshot = compute(
        [_tx("user", 400_000_000, "2026-08-01")],
        _profile(
            spouse_has_usaha_income="yes",
            spouse_aggregation_active=True,
            spouse_usaha_omzet_ytd=300_000_000,
        ),
        ruleset,
    )
    assert snapshot.exempt_omzet == 400_000_000
    assert snapshot.taxable_omzet == 0
    assert snapshot.final_tax == 0
    assert snapshot.exemption_remaining == 100_000_000


# --- TC-GOLDEN-PASAL58-* (SRS v2.6 §4.5, PMK 164/2023 Lampiran B) --------


def test_tc_golden_pasal58_tuan_o(ruleset):
    """TC-GOLDEN-PASAL58-TUAN-O. His Rp 1,2 miliar omzet, her Rp 750 juta.

    Each PH/MT partner holds an independent Rp 500 juta band, so his omzet is
    fully exempt up to 500 juta and the spouse figure never fills his band. The
    pair totals Rp 1,95 miliar, well under the Rp 4,8 miliar cap.
    """
    snapshot = compute(
        [_tx("tuan-o", 1_200_000_000, "2026-07-10")],
        _profile(
            spouse_has_usaha_income="yes",
            spouse_aggregation_active=True,
            spouse_usaha_omzet_ytd=750_000_000,
        ),
        ruleset,
    )
    assert snapshot.exempt_omzet == 500_000_000
    assert snapshot.taxable_omzet == 700_000_000
    assert snapshot.final_tax == 3_500_000
    assert snapshot.next_year_at_risk is False


def test_tc_golden_pasal58_nyonya_l(ruleset):
    """TC-GOLDEN-PASAL58-NYONYA-L. The mirror image: her Rp 750 juta, his Rp 1,2 miliar.

    The asymmetry against TC-GOLDEN-PASAL58-TUAN-O is deliberate. Because the
    larger omzet sits on opposite sides, a spouse_in_band switch running the
    wrong way would break one case or the other, so the pair pins its direction.
    """
    snapshot = compute(
        [_tx("nyonya-l", 750_000_000, "2026-07-10")],
        _profile(
            spouse_has_usaha_income="yes",
            spouse_aggregation_active=True,
            spouse_usaha_omzet_ytd=1_200_000_000,
        ),
        ruleset,
    )
    assert snapshot.exempt_omzet == 500_000_000
    assert snapshot.taxable_omzet == 250_000_000
    assert snapshot.final_tax == 1_250_000
    assert snapshot.next_year_at_risk is False


def test_tc_golden_pasal58_param_band(ruleset):
    """TC-GOLDEN-PASAL58-PARAM-BAND. The switch is data, read without a code change.

    Setting spouse_in_band true shares the band, so the Rp 750 juta spouse
    figure consumes it entirely and the whole Rp 1,2 miliar is taxable. Only the
    ruleset differs from TC-GOLDEN-PASAL58-TUAN-O; the code is untouched.
    """
    shared_band = replace(ruleset, spouse_in_band=True)
    snapshot = compute(
        [_tx("tuan-o", 1_200_000_000, "2026-07-10")],
        _profile(
            spouse_has_usaha_income="yes",
            spouse_aggregation_active=True,
            spouse_usaha_omzet_ytd=750_000_000,
        ),
        shared_band,
    )
    assert snapshot.exempt_omzet == 0
    assert snapshot.taxable_omzet == 1_200_000_000
    assert snapshot.final_tax == 6_000_000
    assert (
        snapshot.input_hash
        != compute(
            [_tx("tuan-o", 1_200_000_000, "2026-07-10")],
            _profile(
                spouse_has_usaha_income="yes",
                spouse_aggregation_active=True,
                spouse_usaha_omzet_ytd=750_000_000,
            ),
            ruleset,
        ).input_hash
    )


def test_tc_withhold_equal(ruleset):
    """TC-WITHHOLD-EQUAL. Rp 50.000 tax against Rp 50.000 withheld is nihil.

    Rp 510.000.000 of usaha omzet leaves Rp 10.000.000 taxable after the band,
    and 10.000.000 at 1/200 is Rp 50.000.
    """
    snapshot = compute(
        [_tx("proyek", 510_000_000, "2026-04-01", withheld=50_000)],
        _profile(),
        ruleset,
    )
    assert snapshot.final_tax == 50_000
    month = snapshot.months[0]
    assert month.month == "2026-04"
    assert month.withheld == 50_000
    assert month.sisa_bayar_idr == 0
    assert month.overwithheld_excess_idr == 0
    assert month.withhold_status == WITHHOLD_NIHIL


def test_fr_23_excess_is_surfaced_and_never_carried_forward(ruleset):
    """FR-23. Over-withholding is reported, not moved into another month.

    January's Rp 40.000 excess is disclosed but not credited against February,
    so February still owes its full Rp 2.550.000.
    """
    snapshot = compute(
        [
            _tx("jan", 510_000_000, "2026-01-10", withheld=90_000),
            _tx("feb", 510_000_000, "2026-02-10", withheld=0),
        ],
        _profile(),
        ruleset,
    )
    january, february = snapshot.months
    assert january.final_tax == 50_000
    assert january.withhold_status == WITHHOLD_BELUM_DIPERHITUNGKAN
    assert january.overwithheld_excess_idr == 40_000
    assert january.sisa_bayar_idr == 0
    # The band is annual, so February is fully taxable.
    assert february.final_tax == 2_550_000
    assert february.withhold_status == WITHHOLD_KURANG_POTONG
    assert february.sisa_bayar_idr == 2_550_000
    assert february.overwithheld_excess_idr == 0
    assert snapshot.overwithheld_excess_idr == 40_000
