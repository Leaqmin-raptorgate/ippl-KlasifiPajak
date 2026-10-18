"""HTTP checks for Bagian A against KlasifiPajak API v1.2.2.

The point of these is section 3.3: the served figure equals the engine result
field for field, and the January digest equals the document's normative vector.
"""

import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine import Profile, Transaction, compute  # noqa: E402
from app.engine.ruleset import load_ruleset  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.snapshot import TransactionIn  # noqa: E402

BAND = 500_000_000
NORMATIVE_HASH = "v1:1d31077627dffd7d9e13276931a34e482a36f60fe1984f120f8dac28253d0090"

client = TestClient(app)


def _normative_request():
    return {
        "tax_year": 2026,
        "as_of_date": "2026-01-31",
        "profile": {
            "entity_type": "orang_pribadi",
            "marital_status": "yes",
            "spouse_aggregation_active": True,
            "is_new_taxpayer_current_year": False,
            "spouse_current_year_usaha_omzet_idr": 400_000_000,
            "spouse_current_year_pekerjaan_bebas_omzet_idr": 0,
            "spouse_current_year_already_final_omzet_idr": 0,
            "prior_year_gross_user": {
                "usaha_idr": 1_200_000_000,
                "pekerjaan_bebas_idr": 0,
                "already_final_idr": 0,
            },
            "prior_year_gross_spouse": {
                "usaha_idr": 750_000_000,
                "pekerjaan_bebas_idr": 0,
                "already_final_idr": 0,
            },
        },
        "transactions": [
            {
                "id": "tx-001",
                "tx_date": "2026-01-15",
                "amount_idr": 1_200_000_000,
                "category": "usaha",
                "withheld_tax_amount_idr": 0,
            }
        ],
    }


def _body(amount=1_200_000_000, **profile):
    merged = {"is_new_taxpayer_current_year": True}
    merged.update(profile)
    return {
        "tax_year": 2026,
        "as_of_date": "2026-07-31",
        "profile": merged,
        "transactions": [
            {"id": "a", "tx_date": "2026-07-10", "amount_idr": amount, "category": "usaha"}
        ],
    }


def test_health_reports_ok_only():
    """Section 3.1 fixes the body; it carries no ruleset id."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ruleset_is_served_from_data_not_inlined():
    response = client.get("/ruleset")
    assert response.status_code == 200
    body = response.json()
    assert body["ruleset_id"] == "pp20-2026-academic-1"
    assert body["tax_year"] == 2026
    assert body["effective_date"] == "2026-09-26"
    assert body["spouse_in_band"] is False
    assert body["spouse_in_cap"] is True
    assert body["rate_numerator"] == 1
    assert body["rate_denominator"] == 200
    assert body["free_band_idr"] == BAND
    assert body["gross_cap_idr"] == 4_800_000_000


def test_snapshot_matches_the_normative_example():
    """Section 3.3's own example, including its digest."""
    response = client.post("/snapshot", json=_normative_request())
    assert response.status_code == 200
    body = response.json()
    assert body["scheme_eligibility_status"] == "scheme_eligible"
    assert body["prior_year_resolution_source"] == "manual_profile"
    assert body["prior_year_combined_gross_idr"] == 1_950_000_000
    assert body["current_year_combined_gross_idr"] == 1_600_000_000
    assert body["next_year_ineligible"] is False
    assert body["remaining_free_band_idr"] == 0
    assert len(body["months"]) == 1
    january = body["months"][0]
    assert january["month"] == "2026-01"
    assert january["input_hash"] == NORMATIVE_HASH
    assert january["porsi_bebas_idr"] == 500_000_000
    assert january["porsi_kena_idr"] == 700_000_000
    assert january["tax_0_5_pct_idr"] == 3_500_000


def test_snapshot_matches_the_engine_field_for_field():
    body = client.post("/snapshot", json=_body()).json()
    expected = compute(
        [Transaction(id="a", amount=1_200_000_000, date="2026-07-10", category="usaha")],
        Profile(is_new_taxpayer_current_year=True),
        load_ruleset(),
        as_of_date="2026-07-31",
    )
    assert body["ruleset_id"] == expected.ruleset_id
    assert body["effective_date"] == "2026-09-26"
    assert body["months"][6]["input_hash"] == expected.months[0].input_hash
    assert body["months"][6]["tax_0_5_pct_idr"] == expected.final_tax == 3_500_000
    assert body["months"][6]["porsi_bebas_idr"] == expected.exempt_omzet == BAND
    assert body["months"][6]["porsi_kena_idr"] == expected.taxable_omzet == 700_000_000


def test_every_month_through_as_of_exists_and_has_its_own_hash():
    body = client.post(
        "/snapshot",
        json={
            "tax_year": 2026,
            "as_of_date": "2026-03-31",
            "profile": {"is_new_taxpayer_current_year": True},
            "transactions": [
                {
                    "id": "jan",
                    "tx_date": "2026-01-10",
                    "amount_idr": 10_000_000,
                    "category": "usaha",
                },
                {
                    "id": "feb",
                    "tx_date": "2026-02-10",
                    "amount_idr": 10_000_000,
                    "category": "usaha",
                },
            ],
        },
    ).json()
    months = body["months"]
    assert [month["month"] for month in months] == ["2026-01", "2026-02", "2026-03"]
    assert all(month["input_hash"].startswith("v1:") for month in months)
    assert months[0]["input_hash"] != months[1]["input_hash"]
    assert months[2]["tax_0_5_pct_idr"] == 0


def test_snapshot_is_deterministic_across_calls():
    first = client.post("/snapshot", json=_body()).json()
    second = client.post("/snapshot", json=_body()).json()
    assert first == second


@pytest.mark.parametrize("bad", ["500", 500.0, True, -1, 0])
def test_money_rejects_everything_but_a_plain_int(bad):
    response = client.post("/snapshot", json=_body(amount=bad))
    assert response.status_code == 422


def test_whole_decimal_is_rejected_in_process():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TransactionIn(
            id="a",
            amount_idr=Decimal("500"),
            tx_date="2026-07-10",
            category="usaha",
        )


def test_unknown_category_is_rejected():
    response = client.post(
        "/snapshot",
        json={
            "tax_year": 2026,
            "as_of_date": "2026-07-31",
            "profile": {},
            "transactions": [
                {"id": "a", "tx_date": "2026-07-10", "amount_idr": 500, "category": "jasa"}
            ],
        },
    )
    assert response.status_code == 422


def test_timestamp_instead_of_calendar_date_is_rejected():
    response = client.post(
        "/snapshot",
        json={
            "tax_year": 2026,
            "as_of_date": "2026-07-31T00:00:00",
            "profile": {},
            "transactions": [],
        },
    )
    assert response.status_code == 422


def test_unknown_field_is_rejected():
    body = _body()
    body["profile"]["spouse_aggregation_actve"] = True
    assert client.post("/snapshot", json=body).status_code == 422


def test_missing_prior_year_is_unverifiable_and_taxes_nothing():
    """Section 2.3: a non-new taxpayer without prior figures yields tax 0."""
    body = client.post(
        "/snapshot",
        json={
            "tax_year": 2026,
            "as_of_date": "2026-07-31",
            "profile": {"is_new_taxpayer_current_year": False},
            "transactions": [
                {"id": "a", "tx_date": "2026-07-10", "amount_idr": 900_000_000, "category": "usaha"}
            ],
        },
    ).json()
    assert body["scheme_eligibility_status"] == "unverifiable"
    assert body["prior_year_resolution_source"] == "unverifiable"
    assert body["months"][6]["tax_0_5_pct_idr"] == 0


def test_new_taxpayer_ignores_prior_numbers():
    body = client.post(
        "/snapshot",
        json={
            "tax_year": 2026,
            "as_of_date": "2026-07-31",
            "profile": {
                "is_new_taxpayer_current_year": True,
                "prior_year_gross_user": {"usaha_idr": 9_000_000_000},
            },
            "transactions": [
                {"id": "a", "tx_date": "2026-07-10", "amount_idr": 600_000_000, "category": "usaha"}
            ],
        },
    ).json()
    assert body["scheme_eligibility_status"] == "scheme_eligible"
    assert body["prior_year_resolution_source"] == "first_year_taxpayer"
    assert body["prior_year_combined_gross_idr"] == 0
    assert body["months"][6]["tax_0_5_pct_idr"] == 500_000


def test_engine_layer_has_no_sql_or_http_client():
    """Invariant 3: the engine is pure maths."""
    root = Path(__file__).resolve().parents[1] / "app" / "engine"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for banned in ("sqlalchemy", "pymysql", "fastapi", "httpx", "requests"):
            assert banned not in text, f"{path} mentions {banned}"
