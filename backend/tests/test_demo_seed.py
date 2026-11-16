"""FR-14, FR-19, FR-22: the demo seed drives the dashboard and compute path."""

import importlib.util
from datetime import date
from pathlib import Path

from app.services.snapshots_store import freeze_today_jakarta


def test_seed_demo_is_repeatable_and_dashboard_figures_match_compute(client):
    path = Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py"
    spec = importlib.util.spec_from_file_location("seed_demo", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with freeze_today_jakarta(date(2026, 11, 17)):
        module.main()
        module.main()
        login = client.post(
            "/api/v1/auth/login",
            json={"identifier": "berbayar@klasifipajak.demo", "password": "DemoBayar10"},
        )
        assert login.status_code == 200, login.text
        response = client.get("/api/v1/tax/dashboard?tax_year=2026")
        assert response.status_code == 200, response.text
        dashboard = response.json()
        band = dashboard["thresholds"]["pita_500_juta"]
        cap = dashboard["thresholds"]["monitoring_current_year_cap_4_8m"]
        assert band["limit_idr"] == 500_000_000
        assert band["ytd_usaha_omzet_idr"] == 3_925_000_000
        assert band["remaining_free_band_idr"] == 0
        assert cap["limit_idr"] == 4_800_000_000
        assert cap["ytd_combined_gross_idr"] == 3_932_500_000
        assert cap["cap_warning"] is True
        assert sum(row["tax_0_5_pct_idr"] for row in dashboard["monthly_summaries"]) == 17_125_000
        transactions = client.get("/api/v1/transactions?tax_year=2026").json()
        assert transactions["pagination"]["total_items"] == 3
