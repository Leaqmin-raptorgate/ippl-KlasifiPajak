"""Onboarding answers must affect both guidance and deterministic totals (FR-48)."""

from datetime import date

from test_tax_crud_trace_quota import _auth, _profile, _tx

from app.engine import Profile, Transaction, compute
from app.engine.types import PRIOR_YEAR_REPORTED, PRIOR_YEAR_UNSET, PRIOR_YEAR_UNVERIFIABLE
from app.models import Profile as ProfileRow
from app.services.snapshots_store import freeze_today_jakarta, profile_to_engine


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


def test_fr48_omitted_new_taxpayer_answer_is_null(client):
    """FR-48: a create that leaves the question out stores null, not false."""
    _auth(client)
    response = client.put(
        "/api/v1/profiles/2026",
        json={
            "version": 1,
            "name": "Toko Tax Lane",
            "entity_type": "orang_pribadi",
            "nib_status": "has_nib",
            "nib_last_4": "4321",
            "kbli_code": "47111",
            "business_description": "Penjualan sembako",
            "marital_status": "no",
            "spouse_aggregation_active": False,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_new_taxpayer_current_year"] is None


def test_fr48_new_taxpayer_null_true_and_false_round_trip(client):
    """FR-48: null, true, and false each persist, and null to true is audited."""
    _auth(client)
    current = _profile(client, is_new_taxpayer_current_year=None)
    assert current.status_code == 200, current.text
    body = current.json()
    assert body["is_new_taxpayer_current_year"] is None
    for value, old, new in ((True, "", "True"), (False, "True", "False"), (None, "False", "")):
        current = _profile(client, version=body["version"], is_new_taxpayer_current_year=value)
        assert current.status_code == 200, current.text
        body = current.json()
        assert body["is_new_taxpayer_current_year"] is value
        trail = [
            entry
            for entry in body["audit_trail"]
            if entry["field"] == "is_new_taxpayer_current_year"
        ]
        assert trail[-1]["old_value"] == old
        assert trail[-1]["new_value"] == new


def test_fr48_unanswered_new_taxpayer_is_unverifiable_until_figures_exist(ruleset):
    """FR-48: unknown is not the legacy first-year inference.

    The v2 hash stays a bool. Unknown with no figures resolves unverifiable, so
    it hashes differently from the legacy unset path. The same missing figures
    with an explicit false share that payload. Supplied user figures follow the
    explicit-false path (manual_profile).
    """
    row = Transaction("row", 600_000_000, "2026-01-01", "usaha")
    unknown = compute([row], Profile(new_taxpayer_unknown=True), ruleset)
    explicit_no = compute([row], Profile(is_new_taxpayer_current_year=False), ruleset)
    legacy = compute([row], Profile(), ruleset)
    assert unknown.prior_year_resolution_source == PRIOR_YEAR_UNVERIFIABLE
    assert unknown.prior_year_gross_revenue == 0
    assert explicit_no.prior_year_resolution_source == PRIOR_YEAR_UNVERIFIABLE
    assert legacy.prior_year_resolution_source == PRIOR_YEAR_UNSET
    assert unknown.input_hash.startswith("v2:")
    assert unknown.input_hash != legacy.input_hash
    assert unknown.input_hash == explicit_no.input_hash

    reported = compute(
        [row],
        Profile(
            new_taxpayer_unknown=True,
            prior_year_usaha_omzet=1_200_000_000,
            prior_year_pekerjaan_bebas_omzet=0,
            prior_year_already_final_omzet=0,
        ),
        ruleset,
    )
    assert reported.prior_year_resolution_source == PRIOR_YEAR_REPORTED
    assert reported.prior_year_gross_revenue == 1_200_000_000
    assert reported.prior_year_ineligible is False
    explicit_reported = compute(
        [row],
        Profile(
            is_new_taxpayer_current_year=False,
            prior_year_usaha_omzet=1_200_000_000,
            prior_year_pekerjaan_bebas_omzet=0,
            prior_year_already_final_omzet=0,
        ),
        ruleset,
    )
    assert reported.input_hash == explicit_reported.input_hash
    assert reported.input_hash != unknown.input_hash

    partial = compute(
        [row],
        Profile(
            new_taxpayer_unknown=True,
            spouse_aggregation_active=True,
            prior_year_usaha_omzet=0,
            prior_year_pekerjaan_bebas_omzet=0,
            prior_year_already_final_omzet=0,
        ),
        ruleset,
    )
    assert partial.prior_year_resolution_source == PRIOR_YEAR_UNVERIFIABLE
    assert partial.prior_year_gross_revenue == 0


def test_fr48_stored_unknown_marks_only_a_null_answer():
    """FR-48: the engine marker is set for a stored null, never for an explicit false."""
    unknown = profile_to_engine(
        ProfileRow(id="p-unknown", user_id="u", tax_year=2026, is_new_taxpayer_current_year=None)
    )
    answered_no = profile_to_engine(
        ProfileRow(id="p-no", user_id="u", tax_year=2026, is_new_taxpayer_current_year=False)
    )
    assert unknown.new_taxpayer_unknown is True
    assert unknown.is_new_taxpayer_current_year is None
    assert answered_no.new_taxpayer_unknown is False
    assert answered_no.is_new_taxpayer_current_year is False


def test_fr48_unknown_new_taxpayer_still_requires_prior_figures(client):
    """FR-48: unknown does not skip prior-year user figures the way a new taxpayer does."""
    with freeze_today_jakarta(date(2026, 11, 2)):
        _auth(client)
        blank = _profile(client, is_new_taxpayer_current_year=None)
        assert blank.status_code == 200, blank.text
        prior = client.get("/api/v1/tax/dashboard?tax_year=2026").json()["thresholds"][
            "eligibility_prior_year_cap_4_8m"
        ]
        assert prior["status"] == "unverifiable"
        assert prior["resolution_source"] == PRIOR_YEAR_UNVERIFIABLE
        assert prior["combined_prior_year_gross_idr"] == 0

        filled = _profile(
            client,
            version=blank.json()["version"],
            is_new_taxpayer_current_year=None,
            prior_user_usaha_idr=1_000_000,
            prior_user_pekerjaan_bebas_idr=2_000_000,
            prior_user_already_final_idr=3_000_000,
        )
        assert filled.status_code == 200, filled.text
        reported = client.get("/api/v1/tax/dashboard?tax_year=2026").json()["thresholds"][
            "eligibility_prior_year_cap_4_8m"
        ]
        assert reported["resolution_source"] == PRIOR_YEAR_REPORTED
        assert reported["status"] == "scheme_eligible"
        assert reported["combined_prior_year_gross_idr"] == 6_000_000


def test_fr48_unanswered_new_taxpayer_guidance_asks_to_answer_first(client):
    """FR-49: a null new-taxpayer answer is incomplete and surfaces that guidance."""
    _auth(client)
    created = _profile(client, is_new_taxpayer_current_year=None)
    assert created.status_code == 200, created.text
    guidance = client.get("/api/v1/guidance")
    assert guidance.status_code == 200, guidance.text
    matched = [item for item in guidance.json()["items"] if item["id"] == "new_taxpayer_unknown"]
    assert matched
    assert "terlebih dahulu" in matched[0]["text"]
    assert matched[0]["citation"]

    answered = _profile(
        client, version=created.json()["version"], is_new_taxpayer_current_year=False
    )
    assert answered.status_code == 200, answered.text
    later = client.get("/api/v1/guidance").json()["items"]
    assert all(item["id"] != "new_taxpayer_unknown" for item in later)


def test_fr48_assistant_context_passes_null_new_taxpayer(client, monkeypatch):
    """FR-48: the assistant profile context keeps null instead of coercing it to false."""
    from app.classify.model_client import FakeModelClient
    from app.services import assistant

    _auth(client)
    assert _profile(client, is_new_taxpayer_current_year=None).status_code == 200
    consent = client.put("/api/v1/ai-consent", json={"consent": True})
    assert consent.status_code == 200, consent.text
    fake = FakeModelClient(["Jawaban wajib pajak baru belum diisi."])
    monkeypatch.setattr(assistant, "get_model_client", lambda: fake)
    response = client.post("/api/v1/assistant/query", json={"question": "Jelaskan profil saya"})
    assert response.status_code == 200, response.text
    content = fake.calls[0]["messages"][1]["content"]
    assert '"is_new_taxpayer_current_year":null' in content


def test_profile_put_is_full_replace_for_onboarding_answers(client):
    """PUT replaces the whole profile: an omitted onboarding answer resets to unanswered."""
    _auth(client)
    first = _profile(client, has_selected_article_17=True)
    assert first.status_code == 200, first.text
    assert first.json()["has_selected_article_17"] is True
    version = first.json()["version"]

    # Same body without the field, as an older client would send it.
    second = _profile(client, version=version)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["has_selected_article_17"] is None
    assert any(
        entry["field"] == "has_selected_article_17"
        and entry["old_value"] == "True"
        and entry["new_value"] == ""
        for entry in body["audit_trail"]
    )
