"""End-to-end checks for the authenticated slice under ``/api/v1``."""

from fastapi.testclient import TestClient

from app.main import app

AUTH = {
    "email": "user@example.com",
    "username": "adityaputra",
    "password": "PasswordMinimal10",
}


def _register(client, **overrides):
    payload = dict(AUTH)
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload)


def _login(client):
    return client.post(
        "/api/v1/auth/login",
        json={"identifier": AUTH["email"], "password": AUTH["password"]},
    )


def _authenticated(client):
    assert _register(client).status_code == 201
    response = _login(client)
    assert response.status_code == 200
    return response


def _profile(client, **overrides):
    payload = {
        "version": 1,
        "name": "Toko Sumber Makmur",
        "entity_type": "orang_pribadi",
        "nib_status": "has_nib",
        "nib_last_4": "0123",
        "kbli_code": "47111",
        "business_description": "Penjualan sembako",
        "marital_status": "no",
        "spouse_aggregation_active": False,
        "is_new_taxpayer_current_year": True,
    }
    payload.update(overrides)
    return client.put("/api/v1/profiles/2026", json=payload)


def _transaction(client, **overrides):
    payload = {
        "amount_idr": 12_500_000,
        "tx_date": "2026-10-15",
        "client_name": "PT Sumber Makmur",
        "description": "Penjualan sembako",
        "invoice_no": "INV-2026-104",
        "withheld_tax_amount_idr": 62_500,
        "source_channel": "corporate_client",
    }
    payload.update(overrides)
    return client.post("/api/v1/transactions", json=payload)


def test_register_login_me_and_logout(client):
    created = _register(client)
    assert created.status_code == 201
    body = created.json()
    assert body["user_id"].startswith("usr_")
    assert body["email"] == AUTH["email"]

    login = _login(client)
    assert login.status_code == 200
    assert login.json()["token"] is None
    assert client.cookies.get("kp_session")

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == AUTH["username"]

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert logout.json() == {"revoked": True}
    assert client.get("/api/v1/auth/me").status_code == 401


def test_non_browser_login_returns_a_token(client):
    _register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": AUTH["username"], "password": AUTH["password"]},
        headers={"X-Client-Type": "non-browser"},
    )
    assert response.status_code == 200
    token = response.json()["token"]
    assert token and token.count(".") == 2
    allowed = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert allowed.status_code == 200


def test_register_rejects_short_password_and_duplicate_identifiers(client):
    assert _register(client, password="short").status_code == 422
    assert _register(client).status_code == 201
    duplicate = _register(client, email="USER@example.com")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "IDENTIFIER_ALREADY_EXISTS"


def test_login_rejects_a_wrong_password_with_the_generic_message(client):
    _register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": AUTH["email"], "password": "WrongPassword123"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_protected_routes_require_a_session(client):
    for method, path in (
        ("get", "/api/v1/auth/me"),
        ("get", "/api/v1/profiles/2026"),
        ("get", "/api/v1/transactions"),
        ("get", "/api/v1/tax/dashboard"),
    ):
        assert getattr(client, method)(path).status_code == 401


def test_profile_round_trip_masks_the_nib_and_audits(client):
    _authenticated(client)
    saved = _profile(client)
    assert saved.status_code == 200
    body = saved.json()
    assert body["nib_masked"] == "*********0123"
    assert body["version"] == 2
    assert body["audit_trail"]

    fetched = client.get("/api/v1/profiles/2026")
    assert fetched.status_code == 200
    assert fetched.json()["nib_masked"] == "*********0123"


def test_profile_rejects_bad_values_and_stale_versions(client):
    _authenticated(client)
    assert _profile(client, entity_type="perseroan").status_code == 422
    assert _profile(client, nib_last_4="12").status_code == 422
    assert _profile(client).status_code == 200
    stale = _profile(client, version=1)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


def test_transaction_is_stored_classified_and_counted_in_the_dashboard(client):
    _authenticated(client)
    assert _profile(client).status_code == 200

    created = _transaction(client)
    assert created.status_code == 201
    body = created.json()
    assert body["category"] == "usaha"
    assert body["classification"]["rule_id"] == "usaha.sale"
    assert body["classification"]["requires_clarification"] is False

    listed = client.get("/api/v1/transactions?tax_year=2026")
    assert listed.status_code == 200
    assert listed.json()["pagination"]["total_items"] == 1

    dashboard = client.get("/api/v1/tax/dashboard?tax_year=2026")
    assert dashboard.status_code == 200
    thresholds = dashboard.json()["thresholds"]
    assert thresholds["pita_500_juta"]["ytd_usaha_omzet_idr"] == 12_500_000
    assert thresholds["monitoring_current_year_cap_4_8m"]["ytd_combined_gross_idr"] == 12_500_000
    assert dashboard.json()["monthly_summaries"]


def test_duplicate_invoice_is_rejected(client):
    _authenticated(client)
    assert _profile(client).status_code == 200
    assert _transaction(client).status_code == 201
    duplicate = _transaction(client)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_INVOICE_TRANSACTION"


def test_transaction_requires_a_profile_and_a_2026_date(client):
    _authenticated(client)
    assert _transaction(client).status_code == 422

    assert _profile(client).status_code == 200
    out_of_range = _transaction(client, tx_date="2027-01-10", invoice_no="INV-X")
    assert out_of_range.status_code == 422
    assert out_of_range.json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_an_unrecognized_description_goes_to_clarification(client):
    _authenticated(client)
    assert _profile(client).status_code == 200
    created = _transaction(client, description="Sesuatu yang tidak jelas", invoice_no="INV-UNKNOWN")
    assert created.status_code == 201
    classification = created.json()["classification"]
    assert classification["requires_clarification"] is True
    assert classification["confidence"] == 0.0


def test_subscription_status_and_quota_limits(client):
    _authenticated(client)
    status = client.get("/api/v1/subscriptions/status")
    assert status.status_code == 200
    body = status.json()
    assert body["subscription_tier"] == "gratis"
    assert body["paid_flag"] is False
    assert body["available_plans"][0]["price_idr"] == 25_000

    quotas = client.get("/api/v1/quotas").json()
    assert quotas["timezone"] == "Asia/Jakarta"
    assert quotas["ai_classification"]["limit"] == 200
    assert quotas["assistant_chat"]["limit"] == 200
    assert quotas["ai_classification"]["used"] == 0


def test_paid_flag_switches_the_tier(client):
    _authenticated(client)
    from datetime import timedelta

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import User
    from app.security import now_utc

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username_norm == AUTH["username"]))
        user.paid_flag = True
        user.valid_until_utc = now_utc() + timedelta(days=30)
        db.commit()
    finally:
        db.close()

    body = client.get("/api/v1/subscriptions/status").json()
    assert body["subscription_tier"] == "berbayar"
    assert body["paid_flag"] is True
    assert body["valid_until_local"] is not None


# --- Clarification flow -------------------------------------------------------
# A row the keyword table cannot place is stored provisionally as ``usaha`` with
# ``requires_clarification`` set. These cover the question being askable, being
# answerable, and the answer actually moving the figure out of the band.

UNCLASSIFIABLE = {
    "amount_idr": 7_000_000,
    "tx_date": "2026-10-20",
    "client_name": "Dinasichletan",
    "description": "qqqq zzzz xxxx",  # matches no rule phrase
    "invoice_no": "INV-2026-900",
    "withheld_tax_amount_idr": 0,
    "source_channel": "corporate_client",
}


def _provisional(client):
    """Create a row that lands provisional, and return its id."""
    response = _transaction(client, **UNCLASSIFIABLE)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["classification"]["requires_clarification"] is True
    assert body["classification"]["confidence"] == 0.0
    return body["id"]


def test_an_unrecognised_row_is_stored_provisional_not_as_a_confident_answer():
    client = _client_fresh()
    _authenticated(client)
    _profile(client)
    body = _transaction(client, **UNCLASSIFIABLE).json()
    assert body["category"] == "usaha"  # a placeholder, not a determination
    assert body["classification"]["requires_clarification"] is True
    assert body["classification"]["confidence"] == 0.0


def test_every_row_carries_its_classification_flag():
    """A client must never have to infer provisional-ness from an absent object."""
    client = _client_fresh()
    _authenticated(client)
    _profile(client)
    _transaction(client)
    _provisional(client)
    items = client.get("/api/v1/transactions?per_page=100").json()["items"]
    assert len(items) == 2
    assert all(item["classification"] is not None for item in items)
    flags = sorted(item["classification"]["requires_clarification"] for item in items)
    assert flags == [False, True]


def test_a_provisional_row_offers_exactly_the_four_categories():
    client = _client_fresh()
    _authenticated(client)
    _profile(client)
    transaction_id = _provisional(client)
    response = client.get(f"/api/v1/transactions/{transaction_id}/clarification")
    assert response.status_code == 200
    body = response.json()
    assert body["transaction_id"] == transaction_id
    assert [option["value"] for option in body["options"]] == [
        "usaha",
        "pekerjaan_bebas",
        "already_final",
        "non_object",
    ]
    assert body["question"]


def test_a_classified_row_has_no_question_to_answer():
    client = _client_fresh()
    _authenticated(client)
    _profile(client)
    created = _transaction(client).json()
    assert created["classification"]["requires_clarification"] is False
    response = client.get(f"/api/v1/transactions/{created['id']}/clarification")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CLARIFICATION_NOT_REQUIRED"


def test_answering_moves_the_row_out_of_the_usaha_band():
    client = _client_fresh()
    _authenticated(client)
    _profile(client)
    transaction_id = _provisional(client)

    before = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
    assert before["thresholds"]["pita_500_juta"]["provisional_omzet_idr"] == 7_000_000

    answered = client.post(
        f"/api/v1/transactions/{transaction_id}/clarification",
        json={"category": "pekerjaan_bebas", "version": 1},
    )
    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert body["category"] == "pekerjaan_bebas"
    assert body["source"] == "user_clarification"
    assert body["classification"]["requires_clarification"] is False
    assert body["version"] == 2

    after = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
    assert after["thresholds"]["pita_500_juta"]["provisional_omzet_idr"] == 0
    # The placeholder never belonged in the classified band.
    assert after["thresholds"]["pita_500_juta"]["ytd_usaha_omzet_idr"] == 0
    assert after["thresholds"]["pita_500_juta"]["remaining_free_band_idr"] == 500_000_000


def test_the_question_is_askable_only_once():
    client = _client_fresh()
    _authenticated(client)
    _profile(client)
    transaction_id = _provisional(client)
    assert (
        client.post(
            f"/api/v1/transactions/{transaction_id}/clarification",
            json={"category": "pekerjaan_bebas"},
        ).status_code
        == 200
    )
    again = client.post(
        f"/api/v1/transactions/{transaction_id}/clarification",
        json={"category": "usaha"},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "CLARIFICATION_NOT_REQUIRED"


def test_a_stale_answer_is_refused_rather_than_silently_applied():
    client = _client_fresh()
    _authenticated(client)
    _profile(client)
    transaction_id = _provisional(client)
    stale = client.post(
        f"/api/v1/transactions/{transaction_id}/clarification",
        json={"category": "pekerjaan_bebas", "version": 99},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


def test_the_band_reports_how_much_of_it_is_still_unconfirmed():
    client = _client_fresh()
    _authenticated(client)
    _profile(client)
    _transaction(client, amount_idr=10_000_000, invoice_no="INV-A", description="jasa desain")
    _provisional(client)
    pita = client.get("/api/v1/tax/dashboard?tax_year=2026").json()["thresholds"]["pita_500_juta"]
    assert pita["provisional_omzet_idr"] == 7_000_000
    assert "belum terklasifikasi" in pita["annotation"]
    # Reported alongside the band, never netted out of it.
    assert pita["ytd_usaha_omzet_idr"] >= pita["provisional_omzet_idr"]


def test_one_account_cannot_read_or_answer_another_accounts_question():
    client = _client_fresh()
    _authenticated(client)
    _profile(client)
    transaction_id = _provisional(client)

    other = _client_fresh()
    assert _register(other, email="lain@example.com", username="lain").status_code == 201
    assert (
        other.post(
            "/api/v1/auth/login",
            json={"identifier": "lain@example.com", "password": AUTH["password"]},
        ).status_code
        == 200
    )
    assert other.get(f"/api/v1/transactions/{transaction_id}/clarification").status_code == 404
    assert (
        other.post(
            f"/api/v1/transactions/{transaction_id}/clarification", json={"category": "usaha"}
        ).status_code
        == 404
    )


def _client_fresh():
    """A client with no cookie jar, so each test starts signed out."""
    return TestClient(app)
