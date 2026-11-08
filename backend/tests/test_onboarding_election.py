"""Onboarding answers must affect both guidance and deterministic totals (FR-48)."""

from datetime import date

from test_tax_crud_trace_quota import _auth, _profile, _tx

from app.services.snapshots_store import freeze_today_jakarta


def test_fr48_article17_election_suppresses_final_tax_and_round_trips(client):
    """FR-48: users who elected normal rates must not receive a 0.5% figure."""
    with freeze_today_jakarta(date(2026, 11, 2)):
        _auth(client)
        profile = _profile(client, has_selected_article_17=True)
        assert profile.status_code == 200, profile.text
        assert profile.json()["has_selected_article_17"] is True
        assert _tx(client, amount_idr=600_000_000).status_code == 201
        dashboard = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
        assert sum(row["tax_0_5_pct_idr"] for row in dashboard["monthly_summaries"]) == 0
        assert (
            dashboard["thresholds"]["eligibility_prior_year_cap_4_8m"]["status"]
            != "scheme_eligible"
        )
        guidance = client.get("/api/v1/guidance")
        assert guidance.status_code == 200
        cited = [item for item in guidance.json()["items"] if item["id"] == "article17"]
        assert cited
        assert "17" in cited[0]["text"]
        assert cited[0]["citation"]


def test_fr48_unknown_answers_remain_unknown_after_profile_read(client):
    """FR-48: missing onboarding answers must not become a negative answer."""
    _auth(client)
    assert _profile(client).status_code == 200
    response = client.get("/api/v1/profiles/2026")
    assert response.status_code == 200
    for field in ("has_selected_article_17", "has_sole_proprietor_company", "receives_salary"):
        assert field in response.json()
        assert response.json()[field] is None
