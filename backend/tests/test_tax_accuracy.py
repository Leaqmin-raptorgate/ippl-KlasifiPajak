"""Tax eligibility and ledger regression cases (FR-03, FR-10, FR-19, FR-35)."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_tax_crud_trace_quota import _auth, _profile, _tx

from app.classify.rules import classify
from app.db import SessionLocal
from app.engine import Profile, Transaction, compute
from app.models import Transaction as TransactionRow
from app.services.snapshots_store import freeze_today_jakarta
from app.services.subscription import _is_paid_active


@pytest.mark.parametrize(
    ("new", "aggregate", "user", "spouse", "source", "gross", "ineligible"),
    [
        (True, False, (None, None, None), (None, None, None), "first_year_taxpayer", 0, False),
        (
            True,
            True,
            (None, None, None),
            (4_800_000_001, 0, 0),
            "manual_profile",
            4_800_000_001,
            True,
        ),
        (True, True, (None, None, None), (0, None, 0), "unverifiable", 0, True),
        (False, False, (0, 0, 0), (None, None, None), "manual_profile", 0, False),
        (False, False, (0, None, 0), (0, 0, 0), "unverifiable", 0, True),
        (False, True, (0, 0, 0), (4_800_000_001, 0, 0), "manual_profile", 4_800_000_001, True),
        (False, True, (0, 0, None), (0, 0, 0), "unverifiable", 0, True),
        (False, True, (0, 0, 0), (0, None, 0), "unverifiable", 0, True),
    ],
)
def test_tc_prior_blank_engine(ruleset, new, aggregate, user, spouse, source, gross, ineligible):
    """FR-19 / UC-13a: omitted prior figures are distinct from reported zero."""
    profile = Profile(
        is_new_taxpayer_current_year=new,
        spouse_aggregation_active=aggregate,
        prior_year_usaha_omzet=user[0],
        prior_year_pekerjaan_bebas_omzet=user[1],
        prior_year_already_final_omzet=user[2],
        prior_spouse_usaha_omzet=spouse[0],
        prior_spouse_pekerjaan_bebas_omzet=spouse[1],
        prior_spouse_already_final_omzet=spouse[2],
    )
    result = compute([Transaction("row", 600_000_000, "2026-01-01", "usaha")], profile, ruleset)
    assert result.prior_year_resolution_source == source
    assert result.prior_year_gross_revenue == gross
    assert result.prior_year_ineligible is ineligible
    if ineligible:
        assert result.final_tax == 0


def test_tc_prior_blank_profile_api(client):
    """FR-03 / FR-19: absent figures persist as blanks and cannot establish eligibility."""
    with freeze_today_jakarta(date(2026, 11, 2)):
        _auth(client)
        response = _profile(client, is_new_taxpayer_current_year=False)
        assert response.status_code == 200, response.text
        assert response.json()["prior_user_usaha_idr"] is None
        prior = client.get("/api/v1/tax/dashboard?tax_year=2026").json()["thresholds"][
            "eligibility_prior_year_cap_4_8m"
        ]
        assert prior["status"] == "unverifiable"
        assert prior["resolution_source"] == "unverifiable"


def test_tc_class_unresolved_excluded_until_answered(client):
    """FR-10 / FR-17: clarification rebuilds the affected month and later months."""
    with freeze_today_jakarta(date(2026, 3, 15)):
        _auth(client)
        assert _profile(client).status_code == 200
        unresolved = _tx(
            client,
            amount_idr=600_000_000,
            tx_date="2026-01-15",
            description="Tidak jelas",
            invoice_no="A",
        )
        assert unresolved.status_code == 201, unresolved.text
        assert unresolved.json()["classification"]["requires_clarification"]
        assert (
            _tx(client, amount_idr=500_000_000, tx_date="2026-02-15", invoice_no="B").status_code
            == 201
        )
        before = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
        band = before["thresholds"]["pita_500_juta"]
        assert band["provisional_omzet_idr"] == 600_000_000
        assert band["ytd_usaha_omzet_idr"] == 500_000_000
        assert sum(m["tax_0_5_pct_idr"] for m in before["monthly_summaries"]) == 0
        answered = client.post(
            f"/api/v1/transactions/{unresolved.json()['id']}/clarification",
            json={"category": "usaha", "version": 1},
        )
        assert answered.status_code == 200, answered.text
        after = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
        assert after["thresholds"]["pita_500_juta"]["provisional_omzet_idr"] == 0
        months = {m["month"]: m for m in after["monthly_summaries"]}
        assert months["2026-01"]["tax_0_5_pct_idr"] == 500_000
        assert months["2026-02"]["tax_0_5_pct_idr"] == 2_500_000


@pytest.mark.parametrize(
    "description", ["bunga deposito", "bunga bank", "dividen", "hadiah undian"]
)
def test_fr10_non_business_excluded_from_cap(description):
    """FR-10 / FR-20: non-business receipts do not count as turnover."""
    assert classify(description)[0] == "non_object"


def test_fr10_business_rent_remains_final():
    assert classify("sewa tanah")[0] == "already_final"


def test_fr05_whitespace_invoice_is_null_for_create_and_update(client):
    _auth(client)
    assert _profile(client).status_code == 200
    first = _tx(client, invoice_no="   ")
    second = _tx(client, invoice_no=" \t ")
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["invoice_no"] is None
    payload = {
        key: first.json()[key]
        for key in (
            "amount_idr",
            "tx_date",
            "client_name",
            "description",
            "withheld_tax_amount_idr",
            "source_channel",
            "version",
        )
    }
    payload["invoice_no"] = "  "
    updated = client.put(f"/api/v1/transactions/{first.json()['id']}", json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["invoice_no"] is None
    with SessionLocal() as db:
        row = db.scalar(select(TransactionRow).where(TransactionRow.id == first.json()["id"]))
        assert row.invoice_no is None and row.invoice_no_norm is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("nib_status", "invalid"),
        ("marital_status", "invalid"),
        ("nib_last_4", None),
        ("name", "x" * 256),
        ("kbli_code", "x" * 17),
        ("business_description", "x" * 256),
    ],
)
def test_fr03_invalid_profile_fields_return_field_errors(client, field, value):
    _auth(client)
    response = _profile(client, **{field: value})
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] and error["message"]
    assert error.get("field") == field or field in error.get("field_errors", {})


@pytest.mark.parametrize(
    "field,value",
    [("client_name", "x" * 256), ("description", "x" * 256), ("invoice_no", "x" * 65)],
)
def test_fr05_long_transaction_fields_return_field_errors(client, field, value):
    _auth(client)
    assert _profile(client).status_code == 200
    response = _tx(client, **{field: value})
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] and error["message"]
    assert error.get("field") == field or field in error.get("field_errors", {})


def test_fr23a_dashboard_refreshes_when_future_date_arrives(client):
    with freeze_today_jakarta(date(2026, 11, 2)):
        _auth(client)
        assert _profile(client).status_code == 200
        assert _tx(client, tx_date="2026-11-03").status_code == 201
        before = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
        assert before["thresholds"]["pita_500_juta"]["ytd_usaha_omzet_idr"] == 0
    with freeze_today_jakarta(date(2026, 11, 3)):
        after = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
        assert after["thresholds"]["pita_500_juta"]["ytd_usaha_omzet_idr"] == 12_500_000


def test_fr03_profile_audit_masks_nib(client):
    _auth(client)
    first = _profile(client)
    assert first.status_code == 200
    changed = _profile(client, version=first.json()["version"], nib_last_4="1234")
    assert changed.status_code == 200, changed.text
    trail = [item for item in changed.json()["audit_trail"] if item["field"] == "nib_last_4"]
    assert trail
    assert trail[-1]["old_value"] == "*********4321"
    assert trail[-1]["new_value"] == "*********1234"


def test_fr35_subscription_active_at_expiry_boundary():
    instant = datetime(2026, 11, 7, 12, 0)
    user = SimpleNamespace(paid_flag=True, valid_until_utc=instant)
    assert _is_paid_active(user, instant) is True
    assert _is_paid_active(user, instant + timedelta(microseconds=1)) is False


@pytest.mark.parametrize("environment", ["development", "production"])
def test_fr_pay07_override_route_is_not_mounted_outside_test(environment):
    """FR-PAY-07: test support is absent from application routing in non-test environments."""
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env.update(APP_ENV=environment, JWT_SECRET="x" * 40)
    code = (
        "from app.main import app; "
        "assert '/api/v1/test-support/subscription-override' "
        "not in app.openapi()['paths']"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_fr_pay07_test_support_rejects_non_loopback_server_address():
    """FR-PAY-07: a non-loopback server cannot expose the override."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, base_url="http://0.0.0.0:8000", client=("127.0.0.1", 50000)) as public:
        response = public.post("/api/v1/test-support/subscription-override", json={})
    assert response.status_code == 404


@pytest.mark.parametrize("field", ["client_name", "description"])
def test_fr05_blank_required_transaction_fields_rejected(client, field):
    """FR-05: a required transaction field cannot be blank."""
    _auth(client)
    assert _profile(client).status_code == 200
    response = _tx(client, **{field: "   "})
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] and error["message"]
    assert error.get("field") == field or field in error.get("field_errors", {})
