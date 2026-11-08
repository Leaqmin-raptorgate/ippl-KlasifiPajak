"""Tax eligibility and ledger regression cases (FR-03, FR-10, FR-19, FR-35)."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from test_tax_crud_trace_quota import _auth, _profile, _tx

from app.db import SessionLocal
from app.engine import Profile, Transaction, compute
from app.models import ClassificationEvent, MonthSnapshot
from app.models import Profile as ProfileRow
from app.models import Transaction as TransactionRow
from app.services import dashboard as dashboard_service
from app.services.dashboard import _prior_combined
from app.services.snapshots_store import freeze_today_jakarta, profile_to_engine
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


_PRIOR_USER = (1_000_000_000, 200_000_000, 50_000_000)
_PRIOR_SPOUSE = (300_000_000, 100_000_000, 50_000_000)
_PRIOR_EMPTY = (None, None, None)


def _stored_prior_profile(*, new, aggregate, user, spouse):
    """ORM-shaped profile. profile_to_engine reads these names and zeros legacy omzet."""
    return SimpleNamespace(
        has_selected_article_17=False,
        spouse_aggregation_active=aggregate,
        is_new_taxpayer_current_year=new,
        spouse_current_usaha_idr=0,
        spouse_current_pekerjaan_bebas_idr=0,
        spouse_current_already_final_idr=0,
        prior_user_usaha_idr=user[0],
        prior_user_pekerjaan_bebas_idr=user[1],
        prior_user_already_final_idr=user[2],
        prior_spouse_usaha_idr=spouse[0],
        prior_spouse_pekerjaan_bebas_idr=spouse[1],
        prior_spouse_already_final_idr=spouse[2],
    )


@pytest.mark.parametrize(
    ("new", "aggregate", "user", "spouse", "spouse_in_cap", "amount", "tag"),
    [
        (True, False, _PRIOR_EMPTY, _PRIOR_EMPTY, True, 0, "first_year_taxpayer"),
        (False, False, _PRIOR_EMPTY, _PRIOR_EMPTY, True, 0, "unverifiable"),
        (False, True, _PRIOR_USER, _PRIOR_SPOUSE, True, 1_700_000_000, "manual_profile"),
        (False, True, _PRIOR_USER, _PRIOR_SPOUSE, False, 1_250_000_000, "manual_profile"),
        (
            False,
            True,
            _PRIOR_USER,
            (300_000_000, None, 0),
            False,
            1_250_000_000,
            "manual_profile",
        ),
        (None, False, _PRIOR_EMPTY, _PRIOR_EMPTY, True, 0, "first_year_taxpayer"),
        (
            None,
            False,
            (5_200_000_000, None, None),
            _PRIOR_EMPTY,
            True,
            5_200_000_000,
            "manual_profile",
        ),
    ],
)
def test_prior_year_dashboard_and_engine_agree(
    ruleset, new, aggregate, user, spouse, spouse_in_cap, amount, tag
):
    """FR-19: dashboard and engine share prior-year amount and tag.

    Pasal 58(1)(a) tests last year's gross. Pasal 58(2) adds the spouse only
    when spouse_in_cap is true. The None flag is the legacy fixture, not a
    stored profile value.
    """
    stored = _stored_prior_profile(new=new, aggregate=aggregate, user=user, spouse=spouse)
    ruleset = replace(ruleset, spouse_in_cap=spouse_in_cap)
    dash_amount, dash_tag = _prior_combined(stored, ruleset)
    result = compute([], profile_to_engine(stored), ruleset)
    assert (dash_amount, dash_tag) == (
        result.prior_year_gross_revenue,
        result.prior_year_resolution_source,
    )
    assert dash_amount == amount
    assert dash_tag == tag


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


def _snapshot_count(profile_id: str) -> int:
    with SessionLocal() as db:
        return int(
            db.scalar(
                select(func.count())
                .select_from(MonthSnapshot)
                .where(MonthSnapshot.profile_id == profile_id)
            )
            or 0
        )


def _checked_through(profile_id: str) -> date | None:
    with SessionLocal() as db:
        return db.scalar(
            select(ProfileRow.snapshot_checked_through).where(ProfileRow.id == profile_id)
        )


def test_empty_profile_dashboard_checks_snapshots_once(client, monkeypatch):
    """A profile with no transactions is checked once per Jakarta day.

    The second dashboard load must not call rebuild again or insert snapshots.
    """
    today = date(2026, 11, 9)
    calls = {"n": 0}
    real_rebuild = dashboard_service.rebuild

    def counting_rebuild(*args, **kwargs):
        calls["n"] += 1
        return real_rebuild(*args, **kwargs)

    monkeypatch.setattr(dashboard_service, "rebuild", counting_rebuild)
    with freeze_today_jakarta(today):
        _auth(client)
        created = _profile(client)
        assert created.status_code == 200, created.text
        profile_id = created.json()["id"]
        first = client.get("/api/v1/tax/dashboard?tax_year=2026")
        assert first.status_code == 200, first.text
        assert _checked_through(profile_id) == today
        rows_after_first = _snapshot_count(profile_id)
        calls_after_first = calls["n"]
        second = client.get("/api/v1/tax/dashboard?tax_year=2026")
        assert second.status_code == 200, second.text
        assert calls["n"] == calls_after_first
        assert _snapshot_count(profile_id) == rows_after_first
        assert _checked_through(profile_id) == today


@pytest.mark.parametrize(
    "field,value",
    [("client_name", "x" * 256), ("description", "x" * 256), ("invoice_no", "x" * 65)],
)
def test_fr05_long_transaction_fields_return_field_errors(client, field, value):
    """FR-05: an over-long transaction field is rejected.

    The shared envelope has code and message only. The field name is in the
    message. There is no field or field_errors key.
    """
    _auth(client)
    assert _profile(client).status_code == 200
    response = _tx(client, **{field: value})
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert field in error["message"]
    assert "field" not in error and "field_errors" not in error


@pytest.mark.parametrize("field", ["client_name", "description"])
def test_fr05_blank_required_transaction_fields_rejected(client, field):
    """FR-05: a required transaction field cannot be blank."""
    _auth(client)
    assert _profile(client).status_code == 200
    response = _tx(client, **{field: "   "})
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert field in error["message"]
    assert "field" not in error and "field_errors" not in error


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
    """Invalid profile values stay rejected.

    The old assertion looked for ``error.field`` or ``error.field_errors``.
    The live contract (spec §2.5 and the error helper) is only
    ``{"error": {"code", "message"}}``. No handler returns those extra keys,
    so the expectation follows that envelope. The message still names the field.
    """
    _auth(client)
    response = _profile(client, **{field: value})
    assert response.status_code == 422, response.text
    body = response.json()
    assert "field_errors" not in body
    error = body["error"]
    assert set(error) == {"code", "message"}
    assert error["code"] and error["message"]
    assert field in error["message"]


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


def _ytd_ledger(transaction_id: str) -> list[tuple[int, int, str]]:
    """Stored ``ytd_usaha_before_idr`` / ``ytd_usaha_after_idr`` pairs, oldest first."""
    with SessionLocal() as db:
        rows = db.scalars(
            select(ClassificationEvent)
            .where(ClassificationEvent.transaction_id == transaction_id)
            .order_by(ClassificationEvent.recorded_at.asc(), ClassificationEvent.id.asc())
        ).all()
        return [(row.ytd_usaha_before_idr, row.ytd_usaha_after_idr, row.source) for row in rows]


def test_provisional_usaha_is_excluded_from_band_and_ledger(client):
    """FR-10 / FR-16a: a provisional row is outside the usaha band until answered.

    Answering it as usaha records before = X and after = X + amount.
    Overriding that answer away from usaha records the reverse pair.
    """
    prior = 12_500_000
    amount = 7_000_000
    with freeze_today_jakarta(date(2026, 11, 2)):
        _auth(client)
        assert _profile(client).status_code == 200
        confirmed = _tx(client, amount_idr=prior, invoice_no="INV-CONFIRMED")
        assert confirmed.status_code == 201, confirmed.text
        assert confirmed.json()["category"] == "usaha"
        assert confirmed.json()["classification"]["requires_clarification"] is False

        provisional = _tx(
            client,
            amount_idr=amount,
            description="Tidak jelas",
            invoice_no="INV-PROVISIONAL",
            client_name="Pembayar Tidak Dikenal",
        )
        assert provisional.status_code == 201, provisional.text
        body = provisional.json()
        assert body["classification"]["requires_clarification"] is True
        tx_id = body["id"]

        waiting = client.get("/api/v1/tax/dashboard?tax_year=2026").json()["thresholds"][
            "pita_500_juta"
        ]
        assert waiting["ytd_usaha_omzet_idr"] == prior
        assert waiting["provisional_omzet_idr"] == amount
        assert _ytd_ledger(tx_id) == [(prior, prior, "rule")]

        answered = client.post(
            f"/api/v1/transactions/{tx_id}/clarification",
            json={"category": "usaha", "version": 1},
        )
        assert answered.status_code == 200, answered.text
        assert _ytd_ledger(tx_id)[-1] == (prior, prior + amount, "user_clarification")
        trail = client.get(f"/api/v1/transactions/{tx_id}/audit-trail").json()["events"][-1]
        assert trail["ytd_usaha_omzet_before_idr"] == prior
        assert trail["ytd_usaha_omzet_after_idr"] == prior + amount

        overridden = client.post(
            f"/api/v1/transactions/{tx_id}/override",
            json={"new_category": "non_object", "note": "Bukan omzet usaha"},
        )
        assert overridden.status_code == 200, overridden.text
        assert _ytd_ledger(tx_id)[-1] == (prior + amount, prior, "user_override")
        trail = client.get(f"/api/v1/transactions/{tx_id}/audit-trail").json()["events"][-1]
        assert trail["ytd_usaha_omzet_before_idr"] == prior + amount
        assert trail["ytd_usaha_omzet_after_idr"] == prior
        band = client.get("/api/v1/tax/dashboard?tax_year=2026").json()["thresholds"][
            "pita_500_juta"
        ]
        assert band["ytd_usaha_omzet_idr"] == prior
        assert band["provisional_omzet_idr"] == 0
