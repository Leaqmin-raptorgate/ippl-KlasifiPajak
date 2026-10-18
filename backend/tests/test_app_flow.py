"""End-to-end checks for the authenticated slice under ``/api/v1``."""

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
