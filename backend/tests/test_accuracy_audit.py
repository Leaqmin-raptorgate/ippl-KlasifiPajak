"""Audit totals use the same confirmed, arrived rows as snapshots (FR-10, FR-16a)."""

from datetime import date

import pytest
from sqlalchemy import select
from test_tax_crud_trace_quota import _auth, _profile, _tx

from app.db import SessionLocal
from app.models import ConfigChangeLog
from app.services.snapshots_store import freeze_today_jakarta


@pytest.mark.parametrize("resolution", ["clarification", "override", "reclassify"])
def test_fr16a_provisional_audit_tracks_confirmed_turnover_only(client, resolution):
    """FR-10, FR-16a: provisional placeholder categories never add audit turnover."""
    with freeze_today_jakarta(date(2026, 11, 2)):
        _auth(client)
        assert _profile(client).status_code == 200
        created = _tx(client, description="Pembayaran ambigu", amount_idr=1_000_000).json()
        tx_id = created["id"]
        events = client.get(f"/api/v1/transactions/{tx_id}/audit-trail").json()["events"]
        assert events[0]["ytd_usaha_omzet_before_idr"] == 0
        assert events[0]["ytd_usaha_omzet_after_idr"] == 0
        if resolution == "clarification":
            response = client.post(
                f"/api/v1/transactions/{tx_id}/clarification", json={"category": "usaha"}
            )
        elif resolution == "override":
            response = client.post(
                f"/api/v1/transactions/{tx_id}/override", json={"new_category": "usaha"}
            )
        else:
            response = client.post(
                "/api/v1/transactions/reclassify", json={"transaction_ids": [tx_id]}
            )
        assert response.status_code == 200, response.text
        events = client.get(f"/api/v1/transactions/{tx_id}/audit-trail").json()["events"]
        expected = 0 if resolution == "reclassify" else 1_000_000
        assert events[-1]["ytd_usaha_omzet_before_idr"] == 0
        assert events[-1]["ytd_usaha_omzet_after_idr"] == expected


def test_fr16a_future_rows_are_not_in_audit_ytd(client):
    """FR-05, FR-16a: a future-dated row is stored without entering arrived turnover."""
    with freeze_today_jakarta(date(2026, 11, 2)):
        _auth(client)
        assert _profile(client).status_code == 200
        row = _tx(client, tx_date="2026-11-03").json()
        events = client.get(f"/api/v1/transactions/{row['id']}/audit-trail").json()["events"]
        assert events[-1]["ytd_usaha_omzet_after_idr"] == 0


def test_fr44_configuration_changes_are_logged(client):
    """FR-44: operational threshold changes preserve their actor and previous value."""
    from app.services.config import get_config, set_config

    with SessionLocal() as db:
        assert get_config(db, "T_rule") == "0.80"
        set_config(db, "T_rule", "0.85", actor="offline-test")
        assert get_config(db, "T_rule") == "0.85"
        changes = db.scalars(select(ConfigChangeLog)).all()
        assert len(changes) == 1
        assert changes[0].config_key == "T_rule"
        assert changes[0].actor == "offline-test"


def test_cap_warning_percent_is_stored_as_whole_number(client):
    """A value such as "80.0" is normalised so the dashboard's int() read cannot fail."""
    from app.services.config import get_config, set_config

    with SessionLocal() as db:
        set_config(db, "cap_warning_percent", "90.0", actor="offline-test")
        assert get_config(db, "cap_warning_percent") == "90"
        with pytest.raises(ValueError):
            set_config(db, "cap_warning_percent", "90.5", actor="offline-test")
