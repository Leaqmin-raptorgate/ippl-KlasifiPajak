"""Security-lane hardening and F-AUTH coverage (M50 / D-05 / D-07).

TC ids referenced in briefs/M50-security.md and proposals/testing/TC-4.10.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config.settings import _jwt_secret
from app.db import SessionLocal
from app.logging_redaction import RedactingFilter, redact_text
from app.main import app
from app.models import AuthRateLimit, PasswordResetToken, User
from app.models import Session as SessionRow
from app.schemas.account import PasswordResetRequestIn
from app.security import (
    InvalidToken,
    create_jwt,
    decode_jwt,
    hash_reset_token,
    now_utc,
    verify_password,
)
from app.services import auth as auth_service

AUTH = {
    "email": "user@example.com",
    "username": "adityaputra",
    "password": "PasswordMinimal10",
}


def _client() -> TestClient:
    return TestClient(app)


def _register(client: TestClient, **overrides):
    payload = dict(AUTH)
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload)


def _login(client: TestClient, identifier: str | None = None, password: str | None = None):
    return client.post(
        "/api/v1/auth/login",
        json={
            "identifier": identifier or AUTH["email"],
            "password": password or AUTH["password"],
        },
    )


def _legacy_pbkdf2(password: str) -> str:
    salt = b"0123456789abcdef"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"


# --- HB-01 JWT fail-closed ----------------------------------------------------


def test_tc_hard_15_jwt_secret_fail_closed_in_production(monkeypatch):
    """TC-HARD-15: production refuses empty / placeholder / short secrets."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _jwt_secret()
    monkeypatch.setenv("JWT_SECRET", "dev-secret-change-me")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _jwt_secret()
    monkeypatch.setenv("JWT_SECRET", "short")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _jwt_secret()
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    assert _jwt_secret() == "x" * 32


def test_tc_hard_16_rejects_non_hs256_algorithms():
    """TC-HARD-16: alg=none / non-HS256 → InvalidToken."""
    secret = "test-secret-change-me-32bytes-min!!"
    issued = now_utc()
    good = create_jwt("usr_x", "jti-1", issued, issued + timedelta(hours=1), secret)

    def _forge(alg: str) -> str:
        header = (
            base64.urlsafe_b64encode(
                json.dumps({"alg": alg, "typ": "JWT"}, separators=(",", ":")).encode()
            )
            .rstrip(b"=")
            .decode()
        )
        payload = good.split(".")[1]
        return f"{header}.{payload}.AAAA"

    with pytest.raises(InvalidToken):
        decode_jwt(_forge("none"), secret)
    with pytest.raises(InvalidToken):
        decode_jwt(_forge("RS256"), secret)
    # Smoke: valid HS256 still works.
    assert decode_jwt(good, secret)["sub"] == "usr_x"


# --- HB-02 argon2id + rehash --------------------------------------------------


def test_tc_sec_pwd_01_register_stores_argon2id(client):
    """TC-SEC-PWD-01: registered hash is argon2id, not plaintext."""
    assert _register(client).status_code == 201
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email_norm == AUTH["email"]))
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert "PasswordMinimal10" not in user.password_hash
        assert verify_password(AUTH["password"], user.password_hash)
    finally:
        db.close()


def test_tc_sec_pwd_02_login_with_argon2id(client):
    """TC-SEC-PWD-02: login succeeds after argon2id register."""
    assert _register(client).status_code == 201
    response = _login(client)
    assert response.status_code == 200
    assert client.cookies.get("kp_session")


def test_tc_hard_17_rehashes_legacy_pbkdf2_on_login(client):
    """TC-HARD-17: PBKDF2 row upgrades to argon2id on successful login."""
    assert _register(client).status_code == 201
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email_norm == AUTH["email"]))
        user.password_hash = _legacy_pbkdf2(AUTH["password"])
        db.commit()
        assert user.password_hash.startswith("pbkdf2_sha256$")
    finally:
        db.close()

    assert _login(client).status_code == 200

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email_norm == AUTH["email"]))
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password(AUTH["password"], user.password_hash)
    finally:
        db.close()

    # Subsequent login still works.
    other = _client()
    assert _login(other).status_code == 200


# --- HB-04 INVALID_EMAIL ------------------------------------------------------


def test_tc_sec_em_01_invalid_email_rejected(client):
    """TC-SEC-EM-01: bad email shapes → 422 INVALID_EMAIL."""
    for bad in ("bukanemail", "a@b", "a@b.c d", "user@@example.com", "foo@bar"):
        # Trailing/leading internal space cases; strip-only local with mid spaces.
        response = _register(client, email=bad, username=f"u{abs(hash(bad)) % 10_000}")
        assert response.status_code == 422, bad
        assert response.json()["error"]["code"] == "INVALID_EMAIL", bad


def test_tc_sec_em_02_email_casefold_duplicate(client):
    """TC-SEC-EM-02: casefold duplicate → 409."""
    assert _register(client, email="User@Example.com").status_code == 201
    duplicate = _register(client, email="user@example.com", username="othername")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "IDENTIFIER_ALREADY_EXISTS"


# --- HB-03 rate limits --------------------------------------------------------


def test_tc_sec_rl_01_sixth_register_from_same_ip_is_limited(client):
    """TC-SEC-RL-01 / register 5/IP/15min → 6th 429."""
    for i in range(5):
        response = _register(
            client,
            email=f"u{i}@example.com",
            username=f"user{i}",
        )
        assert response.status_code == 201, response.text
    sixth = _register(client, email="u5@example.com", username="user5")
    assert sixth.status_code == 429
    assert sixth.json()["error"]["code"] == "RATE_LIMITED"


def test_tc_4_10_62_sixth_login_same_identity_is_limited(client):
    """TC-4.10-62: 6th login attempt for one identity → 429."""
    assert _register(client).status_code == 201
    for _ in range(5):
        bad = _login(client, password="WrongPassword123")
        assert bad.status_code == 401
    sixth = _login(client, password="WrongPassword123")
    assert sixth.status_code == 429
    assert sixth.json()["error"]["code"] == "RATE_LIMITED"


# --- HB-05 cookie clear -------------------------------------------------------


def test_tc_hard_18_logout_clears_cookie_with_matching_flags(client):
    """TC-HARD-18 / TC-4.10-35: logout clears kp_session; replay → 401."""
    assert _register(client).status_code == 201
    login = _login(client)
    assert login.status_code == 200
    token = client.cookies.get("kp_session")
    assert token

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    # Set-Cookie clear should be present; jar should drop the session.
    set_cookie = logout.headers.get("set-cookie", "").lower()
    assert "kp_session" in set_cookie
    assert "path=/" in set_cookie

    # Replay the old bearer token → session_revoked.
    replay = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] in {"session_revoked", "UNAUTHENTICATED"}


# --- HB-06 / HB-07 redaction + cookie-only ------------------------------------


def test_tc_hard_19_and_sec_log_01_redaction_filter():
    """TC-HARD-19 / TC-SEC-LOG-01: redactor strips secrets and emails."""
    sample = "password=PasswordMinimal10 token=abc kp_session=eyJ.x user@example.com"
    redacted = redact_text(sample)
    assert "PasswordMinimal10" not in redacted
    assert "abc" not in redacted or "[REDACTED]" in redacted
    assert "user@example.com" not in redacted

    record = logging.LogRecord(
        name="app.auth",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="login password=%s",
        args=("SecretPass12",),
        exc_info=None,
    )
    RedactingFilter().filter(record)
    assert "SecretPass12" not in str(record.msg) + str(record.args)


def test_tc_hard_20_browser_login_omits_body_token(client):
    """TC-HARD-20 / TC-SEC-CORS-01: browser login has token=null; non-browser gets token."""
    assert _register(client).status_code == 201
    browser = _login(client)
    assert browser.status_code == 200
    assert browser.json()["token"] is None
    assert client.cookies.get("kp_session")

    other = _client()
    non_browser = other.post(
        "/api/v1/auth/login",
        json={"identifier": AUTH["email"], "password": AUTH["password"]},
        headers={"X-Client-Type": "non-browser"},
    )
    assert non_browser.status_code == 200
    assert non_browser.json()["token"] and non_browser.json()["token"].count(".") == 2


# --- F-AUTH password reset ----------------------------------------------------


def test_tc_4_10_40_reset_request_is_generic_for_unknown_email(client):
    """TC-4.10-40: unknown email → same generic 200 message."""
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "ghost@example.com"},
    )
    assert response.status_code == 200
    assert "Jika surel terdaftar" in response.json()["message"]


def test_tc_4_10_38_reset_confirm_revokes_sessions_and_is_single_use(client):
    """TC-4.10-38 / 39 / 43: confirm updates password, revokes sessions, single-use."""
    assert _register(client).status_code == 201
    assert _login(client).status_code == 200
    old_token = client.cookies.get("kp_session")

    db = SessionLocal()
    try:
        plaintext = auth_service.request_password_reset(
            db, PasswordResetRequestIn(email=AUTH["email"]), client_ip="9.9.9.9"
        )
        assert plaintext
        row = db.scalar(select(PasswordResetToken))
        assert row is not None
        assert row.token_hash == hash_reset_token(plaintext)
        assert plaintext not in row.token_hash
    finally:
        db.close()

    confirm = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": plaintext, "new_password": "NewPasswordMinimal10"},
    )
    assert confirm.status_code == 200

    # Old session revoked.
    replay = _client().get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert replay.status_code == 401

    # New password works.
    fresh = _client()
    assert (
        fresh.post(
            "/api/v1/auth/login",
            json={"identifier": AUTH["email"], "password": "NewPasswordMinimal10"},
        ).status_code
        == 200
    )

    # Second use of the same token fails.
    again = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": plaintext, "new_password": "AnotherPassword10"},
    )
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "TOKEN_INVALID_OR_EXPIRED"


def test_tc_4_10_42_reset_request_rate_limited(client):
    """TC-4.10-42: reset request shares login identity/IP limits."""
    assert _register(client).status_code == 201
    for _ in range(5):
        assert (
            client.post(
                "/api/v1/auth/password-reset/request",
                json={"email": AUTH["email"]},
            ).status_code
            == 200
        )
    sixth = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": AUTH["email"]},
    )
    assert sixth.status_code == 429


# --- F-AUTH sessions ----------------------------------------------------------


def test_tc_4_10_32_64_list_sessions_created_at_alias(client):
    """TC-4.10-32 / 64 / TC-SEC-SES-01: list sessions; created_at = issued_at_utc."""
    assert _register(client).status_code == 201
    assert _login(client).status_code == 200
    response = client.get("/api/v1/auth/sessions")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["current"] is True
    assert "created_at" in items[0]
    assert items[0]["created_at"].endswith("Z")

    db = SessionLocal()
    try:
        row = db.scalar(select(SessionRow))
        from app.security import iso_utc

        assert items[0]["created_at"] == iso_utc(row.issued_at_utc)
        assert items[0]["id"] == row.id
    finally:
        db.close()


def test_tc_4_10_33_34_revoke_one_and_others(client):
    """TC-4.10-33 / 34: revoke one session; revoke-all-others keeps current."""
    assert _register(client).status_code == 201
    # Create two extra sessions via non-browser logins.
    tokens = []
    for _ in range(2):
        r = client.post(
            "/api/v1/auth/login",
            json={"identifier": AUTH["email"], "password": AUTH["password"]},
            headers={"X-Client-Type": "non-browser"},
        )
        assert r.status_code == 200
        tokens.append(r.json()["token"])

    # Current browser session.
    assert _login(client).status_code == 200
    listed = client.get("/api/v1/auth/sessions").json()["items"]
    assert len(listed) >= 2
    other = next(item for item in listed if not item["current"])
    assert client.delete(f"/api/v1/auth/sessions/{other['id']}").json() == {"revoked": True}
    missing = client.delete("/api/v1/auth/sessions/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404

    revoked = client.delete("/api/v1/auth/sessions")
    assert revoked.status_code == 200
    assert revoked.json()["revoked_count"] >= 1
    # Current still valid.
    assert client.get("/api/v1/auth/me").status_code == 200


# --- F-AUTH delete account ----------------------------------------------------


def test_tc_4_10_44_45_47_delete_account(client):
    """TC-4.10-44 / 45 / 47: confirmation gate; cascade; re-register allowed."""
    assert _register(client).status_code == 201
    assert _login(client).status_code == 200

    bad = client.request(
        "DELETE",
        "/api/v1/account",
        json={"confirmation": "hapus akun saya"},
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "CONFIRMATION_TEXT_MISMATCH"

    ok = client.request(
        "DELETE",
        "/api/v1/account",
        json={"confirmation": "HAPUS AKUN SAYA"},
    )
    assert ok.status_code == 200
    assert ok.json()["deleted"] is True
    assert client.get("/api/v1/auth/me").status_code == 401

    # Same identity may register again.
    fresh = _client()
    assert _register(fresh).status_code == 201


def test_tc_4_10_63_login_ip_limit_twenty(client, monkeypatch):
    """TC-4.10-63 / H-03: 21st login from the same IP → 429 RATE_LIMITED.

    Registers users from distinct IPs (TRUSTED_PROXY_COUNT=1) so register-ip
    buckets stay separate, then fires logins from one shared login-ip bucket.
    """
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    shared_ip = "203.0.113.63"
    for i in range(21):
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"ipuser{i}@example.com",
                "username": f"ipuser{i}",
                "password": AUTH["password"],
            },
            headers={"X-Forwarded-For": f"198.51.100.{i}"},
        )
        assert reg.status_code == 201, reg.text

    for i in range(20):
        bad = client.post(
            "/api/v1/auth/login",
            json={"identifier": f"ipuser{i}@example.com", "password": "WrongPassword123"},
            headers={"X-Forwarded-For": shared_ip},
        )
        assert bad.status_code == 401, (i, bad.text)

    twenty_first = client.post(
        "/api/v1/auth/login",
        json={"identifier": "ipuser20@example.com", "password": "WrongPassword123"},
        headers={"X-Forwarded-For": shared_ip},
    )
    assert twenty_first.status_code == 429
    assert twenty_first.json()["error"]["code"] == "RATE_LIMITED"


def test_tc_4_10_39_reset_token_expires_after_30_minutes(client):
    """TC-4.10-39: reset confirm after expires_at_utc → 400 TOKEN_INVALID_OR_EXPIRED."""
    assert _register(client).status_code == 201
    db = SessionLocal()
    try:
        plaintext = auth_service.request_password_reset(
            db, PasswordResetRequestIn(email=AUTH["email"]), client_ip="9.9.9.10"
        )
        assert plaintext
        row = db.scalar(select(PasswordResetToken))
        assert row is not None
        row.expires_at_utc = now_utc() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    expired = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": plaintext, "new_password": "NewPasswordMinimal10"},
    )
    assert expired.status_code == 400
    assert expired.json()["error"]["code"] == "TOKEN_INVALID_OR_EXPIRED"


def test_tc_4_10_40_reset_known_and_unknown_messages_identical(client):
    """TC-4.10-40: known and unknown emails return the same generic message body."""
    assert _register(client).status_code == 201
    known = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": AUTH["email"]},
    )
    unknown = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "nobody-elsewhere@example.com"},
    )
    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json() == unknown.json()
    assert known.json()["message"] == auth_service.GENERIC_RESET_MESSAGE


def test_tc_4_10_44_delete_account_cascades_profile_tx_and_pii(client):
    """TC-4.10-44: DELETE /account removes profile, transactions, sessions, and user PII."""
    assert _register(client).status_code == 201
    assert _login(client).status_code == 200

    profile = client.put(
        "/api/v1/profiles/2026",
        json={
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
        },
    )
    assert profile.status_code == 200, profile.text
    tx = client.post(
        "/api/v1/transactions",
        json={
            "amount_idr": 12_500_000,
            "tx_date": "2026-10-15",
            "client_name": "PT Sumber Makmur",
            "description": "Penjualan sembako",
            "invoice_no": "INV-2026-104",
            "withheld_tax_amount_idr": 62_500,
            "source_channel": "corporate_client",
        },
    )
    assert tx.status_code == 201, tx.text

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email_norm == AUTH["email"]))
        assert user is not None
        user_id = user.id
        from app.models import Profile, Transaction

        assert db.scalar(select(Profile).where(Profile.user_id == user_id)) is not None
        assert db.scalar(select(Transaction).where(Transaction.user_id == user_id)) is not None
    finally:
        db.close()

    deleted = client.request(
        "DELETE",
        "/api/v1/account",
        json={"confirmation": "HAPUS AKUN SAYA"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    db = SessionLocal()
    try:
        from sqlalchemy import func

        from app.models import Profile, Transaction

        assert db.get(User, user_id) is None
        assert (
            db.scalar(
                select(func.count()).select_from(User).where(User.email_norm == AUTH["email"])
            )
            == 0
        )
        assert (
            db.scalar(select(func.count()).select_from(Profile).where(Profile.user_id == user_id))
            == 0
        )
        assert (
            db.scalar(
                select(func.count()).select_from(Transaction).where(Transaction.user_id == user_id)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count()).select_from(SessionRow).where(SessionRow.user_id == user_id)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(PasswordResetToken)
                .where(PasswordResetToken.user_id == user_id)
            )
            == 0
        )
        # receipt_images is out of this slice (Storage); cascade no-ops when absent.
        assert not auth_service._table_exists(db, "receipt_images")
    finally:
        db.close()


def test_h08_cookie_flags_httponly_samesite_secure_on_set_and_clear(client, monkeypatch):
    """H-08 (no dedicated TC id in catalog): kp_session set/clear carry HttpOnly, SameSite=Lax, Secure when production.

    Secure cookies are not stored by HTTP TestClient, so the production clear path
    authenticates with a Bearer token from a non-browser login and still asserts
    the Set-Cookie flags on the logout response.
    """
    assert _register(client).status_code == 201

    # Non-production: HttpOnly + SameSite=lax; Secure omitted.
    login = _login(client)
    assert login.status_code == 200
    set_cookie = login.headers.get("set-cookie", "")
    lowered = set_cookie.lower()
    assert "kp_session=" in lowered
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    assert "secure" not in lowered

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    clear = logout.headers.get("set-cookie", "").lower()
    assert "kp_session" in clear
    assert "httponly" in clear
    assert "samesite=lax" in clear
    assert "path=/" in clear
    assert "secure" not in clear

    # Production: Secure must be present on both set and clear (HB-05 / H-08).
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "prod-secret-change-me-32bytes-ok!")

    other = _client()
    prod_login = other.post(
        "/api/v1/auth/login",
        json={"identifier": AUTH["email"], "password": AUTH["password"]},
    )
    assert prod_login.status_code == 200
    prod_set = prod_login.headers.get("set-cookie", "").lower()
    assert "httponly" in prod_set
    assert "samesite=lax" in prod_set
    assert "secure" in prod_set
    assert "path=/" in prod_set

    # Bearer auth avoids depending on Secure cookie persistence over http://testserver.
    bearer = other.post(
        "/api/v1/auth/login",
        json={"identifier": AUTH["email"], "password": AUTH["password"]},
        headers={"X-Client-Type": "non-browser"},
    )
    assert bearer.status_code == 200
    token = bearer.json()["token"]
    assert token

    prod_logout = other.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert prod_logout.status_code == 200
    prod_clear = prod_logout.headers.get("set-cookie", "").lower()
    assert "kp_session" in prod_clear
    assert "httponly" in prod_clear
    assert "samesite=lax" in prod_clear
    assert "secure" in prod_clear
    assert "path=/" in prod_clear


def test_tc_sec_ses_idor_cannot_revoke_another_users_session(client):
    """TC-SEC-SES-IDOR (review id; NFR-04): user B cannot revoke user A's session."""
    assert _register(client).status_code == 201
    assert _login(client).status_code == 200
    a_sessions = client.get("/api/v1/auth/sessions").json()["items"]
    a_session_id = a_sessions[0]["id"]

    b = _client()
    assert (
        b.post(
            "/api/v1/auth/register",
            json={
                "email": "other@example.com",
                "username": "otheruser",
                "password": AUTH["password"],
            },
        ).status_code
        == 201
    )
    assert (
        b.post(
            "/api/v1/auth/login",
            json={"identifier": "other@example.com", "password": AUTH["password"]},
        ).status_code
        == 200
    )

    idor = b.delete(f"/api/v1/auth/sessions/{a_session_id}")
    assert idor.status_code == 404
    assert idor.json()["error"]["code"] == "SESSION_NOT_FOUND"

    # A's session remains usable.
    assert client.get("/api/v1/auth/me").status_code == 200
    still = client.get("/api/v1/auth/sessions").json()["items"]
    assert any(item["id"] == a_session_id and item["current"] for item in still)


def test_tc_sec_pwd_param_argon2_encoding_locks_m_t_p(client):
    """TC-SEC-PWD-PARAM (review id; H-02): stored hash encodes m=19456,t=2,p=1."""
    assert _register(client).status_code == 201
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email_norm == AUTH["email"]))
        assert user is not None
        # $argon2id$v=19$m=19456,t=2,p=1$salt$hash
        assert user.password_hash.startswith("$argon2id$")
        parts = user.password_hash.split("$")
        assert parts[1] == "argon2id"
        assert "m=19456" in parts[3]
        assert "t=2" in parts[3]
        assert "p=1" in parts[3]
    finally:
        db.close()


def test_tc_sec_pwd_bound_reset_confirm_rejects_short_password(client):
    """TC-SEC-PWD-BOUND (review id): reset confirm with len 9 → 422 PASSWORD_TOO_SHORT."""
    assert _register(client).status_code == 201
    db = SessionLocal()
    try:
        plaintext = auth_service.request_password_reset(
            db, PasswordResetRequestIn(email=AUTH["email"]), client_ip="9.9.9.11"
        )
        assert plaintext
    finally:
        db.close()

    short = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": plaintext, "new_password": "ShortPass"},  # 9 chars
    )
    assert short.status_code == 422
    assert short.json()["error"]["code"] == "PASSWORD_TOO_SHORT"

    ok = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": plaintext, "new_password": "LongEnough1"},  # 11 chars
    )
    assert ok.status_code == 200


def test_tc_sec_b1_login_unknown_runs_dummy_argon2_verify(client):
    """TC-SEC-B1: unknown identifier still calls verify_password (timing pad)."""
    with patch.object(
        auth_service, "verify_password", wraps=auth_service.verify_password
    ) as mocked:
        response = client.post(
            "/api/v1/auth/login",
            json={"identifier": "missing@example.com", "password": "WhateverPass1"},
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert mocked.call_count >= 1
    # Dummy hash must be the precomputed pad, not a user row.
    assert mocked.call_args.args[1] == auth_service._DUMMY_PASSWORD_HASH


def test_tc_sec_b2_reset_request_equal_work_known_and_unknown(client):
    """TC-SEC-B2: known and unknown reset requests both mint+hash a token."""
    assert _register(client).status_code == 201
    with (
        patch.object(auth_service, "new_reset_token", wraps=auth_service.new_reset_token) as mint,
        patch.object(
            auth_service, "hash_reset_token", wraps=auth_service.hash_reset_token
        ) as hashed,
    ):
        known = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": AUTH["email"]},
        )
        unknown = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "absent-peer@example.com"},
        )
    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json() == unknown.json()
    assert mint.call_count == 2
    assert hashed.call_count == 2


def test_tc_sec_b3_confirm_invalidates_sibling_unused_tokens(client):
    """TC-SEC-B3: successful confirm marks all other unused tokens used."""
    assert _register(client).status_code == 201
    db = SessionLocal()
    try:
        first = auth_service.request_password_reset(
            db, PasswordResetRequestIn(email=AUTH["email"]), client_ip="9.9.9.20"
        )
        # Force a second unused token without going through N3 invalidation.
        from app.security import new_id, new_reset_token

        second_plain = new_reset_token()
        user = db.scalar(select(User).where(User.email_norm == AUTH["email"]))
        db.add(
            PasswordResetToken(
                id=new_id("rst_"),
                user_id=user.id,
                token_hash=hash_reset_token(second_plain),
                expires_at_utc=now_utc() + timedelta(minutes=30),
                used_at=None,
            )
        )
        db.commit()
        unused_before = db.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
        ).all()
        assert len(unused_before) >= 2
    finally:
        db.close()

    confirm = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": first, "new_password": "BrandNewPassword10"},
    )
    assert confirm.status_code == 200

    db = SessionLocal()
    try:
        still_unused = db.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.used_at.is_(None),
            )
        ).all()
        assert still_unused == []
        # Sibling plaintext must no longer confirm.
        sibling = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": second_plain, "new_password": "AnotherPassword10"},
        )
        assert sibling.status_code == 400
        assert sibling.json()["error"]["code"] == "TOKEN_INVALID_OR_EXPIRED"
    finally:
        db.close()


def test_tc_sec_b4_atomic_reset_consume_requires_rowcount(client):
    """TC-SEC-B4: second confirm of the same token fails (atomic used_at)."""
    assert _register(client).status_code == 201
    db = SessionLocal()
    try:
        plaintext = auth_service.request_password_reset(
            db, PasswordResetRequestIn(email=AUTH["email"]), client_ip="9.9.9.21"
        )
    finally:
        db.close()

    first = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": plaintext, "new_password": "AtomicPass01"},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": plaintext, "new_password": "AtomicPass02"},
    )
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "TOKEN_INVALID_OR_EXPIRED"


def test_tc_sec_b5_session_revoked_and_expired_clear_kp_session_cookie(client):
    """TC-SEC-B5 / API §2.6: session_revoked and session_expired clear kp_session."""
    assert _register(client).status_code == 201
    assert _login(client).status_code == 200
    assert client.cookies.get("kp_session")

    # Revoke current session in DB, then hit /me with the sticky cookie.
    db = SessionLocal()
    try:
        row = db.scalar(select(SessionRow))
        assert row is not None
        row.revoked_at = now_utc()
        db.commit()
    finally:
        db.close()

    revoked = client.get("/api/v1/auth/me")
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "session_revoked"
    clear = revoked.headers.get("set-cookie", "").lower()
    assert "kp_session" in clear
    assert "httponly" in clear
    assert "samesite=lax" in clear
    assert "path=/" in clear

    # Fresh login, then expire the session row.
    other = _client()
    assert _login(other).status_code == 200
    db = SessionLocal()
    try:
        row = db.scalars(select(SessionRow).where(SessionRow.revoked_at.is_(None))).first()
        assert row is not None
        row.expires_at_utc = now_utc() - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    expired = other.get("/api/v1/auth/me")
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "session_expired"
    clear2 = expired.headers.get("set-cookie", "").lower()
    assert "kp_session" in clear2
    assert "httponly" in clear2
    assert "samesite=lax" in clear2
    assert "path=/" in clear2


def test_tc_sec_n1_jwt_sub_must_match_session_user(client):
    """TC-SEC-N1: forged JWT sub that disagrees with session.user_id → 401."""
    assert _register(client).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": AUTH["email"], "password": AUTH["password"]},
        headers={"X-Client-Type": "non-browser"},
    )
    assert login.status_code == 200
    token = login.json()["token"]
    import os

    secret = os.environ.get("JWT_SECRET", "test-secret-change-me")
    claims_session = decode_jwt(token, secret)
    # Re-sign with a mismatched sub but the real jti.
    forged = create_jwt(
        "usr_forged_other_account______",
        claims_session["jti"],
        now_utc(),
        now_utc() + timedelta(hours=1),
        secret,
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_tc_sec_n2_reset_request_rejects_invalid_email(client):
    """TC-SEC-N2 / HB-04: password-reset request validates email shape."""
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "bukanemail"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_EMAIL"


def test_tc_sec_n3_new_reset_request_invalidates_prior_unused_tokens(client):
    """TC-SEC-N3: issuing a new reset token marks prior unused tokens used."""
    assert _register(client).status_code == 201
    db = SessionLocal()
    try:
        first = auth_service.request_password_reset(
            db, PasswordResetRequestIn(email=AUTH["email"]), client_ip="9.9.9.22"
        )
        second = auth_service.request_password_reset(
            db, PasswordResetRequestIn(email=AUTH["email"]), client_ip="9.9.9.23"
        )
        assert first and second and first != second
        rows = db.scalars(select(PasswordResetToken)).all()
        unused = [r for r in rows if r.used_at is None]
        assert len(unused) == 1
        assert unused[0].token_hash == hash_reset_token(second)
    finally:
        db.close()

    stale = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": first, "new_password": "ShouldNotWork1"},
    )
    assert stale.status_code == 400


def test_disclaimer_remains_workpaper_spelling():
    """Canonical disclaimer spelling lock (D-07)."""
    from app.services.snapshot import DISCLAIMER

    assert "WORKPAPER" in DISCLAIMER
    assert "WORKOBER" not in DISCLAIMER


# --- ARGON external review follow-ups ----------------------------------------


def test_argon1_client_ip_xff_parsing(monkeypatch):
    """ARGON-1: XFF client index is parts[len-trusted]; trusted=0 ignores XFF."""
    from unittest.mock import Mock

    from app.api.routes_app import _client_ip

    def make_request(xff: str | None, peer: str = "10.0.0.1"):
        req = Mock()
        req.headers = {}
        if xff is not None:
            req.headers["X-Forwarded-For"] = xff
        req.client = Mock()
        req.client.host = peer
        return req

    # trusted=0 → ignore XFF entirely
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "0")
    assert _client_ip(make_request("1.2.3.4, 203.0.113.9", peer="10.0.0.1")) == "10.0.0.1"

    # trusted=1 → rightmost hop is the client the proxy saw
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    assert _client_ip(make_request("1.2.3.4, 203.0.113.9")) == "203.0.113.9"
    # spoofed prefix must not win
    assert _client_ip(make_request("198.51.100.1, 203.0.113.50")) == "203.0.113.50"

    # trusted=2
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "2")
    assert _client_ip(make_request("spoof, 203.0.113.7, 10.1.1.1")) == "203.0.113.7"

    # short header → fall back to peer
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "2")
    assert _client_ip(make_request("only-one", peer="10.0.0.9")) == "10.0.0.9"

    # garbage / empty parts → fall back
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    assert _client_ip(make_request("  ,  , ", peer="10.0.0.8")) == "10.0.0.8"
    assert _client_ip(make_request(None, peer="10.0.0.7")) == "10.0.0.7"


def test_argon2a_login_ip_does_not_block_register(client, monkeypatch):
    """ARGON-2a: login-ip and register-ip are separate buckets on a NAT IP."""
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    shared = "203.0.113.80"
    assert (
        client.post(
            "/api/v1/auth/register",
            json={**AUTH, "email": "nat0@example.com", "username": "nat0"},
            headers={"X-Forwarded-For": "198.51.100.1"},
        ).status_code
        == 201
    )
    # Burn 5 login attempts from the shared NAT IP (identity bucket separate).
    for i in range(5):
        bad = client.post(
            "/api/v1/auth/login",
            json={"identifier": "nat0@example.com", "password": "WrongPassword123"},
            headers={"X-Forwarded-For": shared},
        )
        assert bad.status_code == 401, bad.text
    # Registration from the same NAT IP must still succeed (register-ip unused).
    ok = client.post(
        "/api/v1/auth/register",
        json={
            "email": "nat1@example.com",
            "username": "nat1",
            "password": AUTH["password"],
        },
        headers={"X-Forwarded-For": shared},
    )
    assert ok.status_code == 201, ok.text


def test_argon2b_email_and_username_share_login_id_bucket(client):
    """ARGON-2b: email and username logins share one login-id bucket per user."""
    assert _register(client).status_code == 201
    # 3 failures via email + 2 via username = 5; 6th must 429.
    for _ in range(3):
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"identifier": AUTH["email"], "password": "WrongPassword123"},
            ).status_code
            == 401
        )
    for _ in range(2):
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"identifier": AUTH["username"], "password": "WrongPassword123"},
            ).status_code
            == 401
        )
    sixth = client.post(
        "/api/v1/auth/login",
        json={"identifier": AUTH["email"], "password": "WrongPassword123"},
    )
    assert sixth.status_code == 429
    assert sixth.json()["error"]["code"] == "RATE_LIMITED"


def test_argon2c_ip_block_does_not_increment_id_bucket(client, monkeypatch):
    """ARGON-2c: once login-ip is exhausted, further attempts do not burn login-id."""
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    # Victim registers from a clean IP.
    assert (
        client.post(
            "/api/v1/auth/register",
            json=AUTH,
            headers={"X-Forwarded-For": "198.51.100.2"},
        ).status_code
        == 201
    )
    attacker_ip = "203.0.113.66"
    # Exhaust the 20/IP login bucket against a non-existent account (own id bucket).
    for i in range(20):
        r = client.post(
            "/api/v1/auth/login",
            json={"identifier": f"attacker{i}@ex.com", "password": "WrongPassword123"},
            headers={"X-Forwarded-For": attacker_ip},
        )
        assert r.status_code in {401, 429}, r.text
    # IP is now blocked; attempts against the victim must 429 without locking them.
    blocked = client.post(
        "/api/v1/auth/login",
        json={"identifier": AUTH["email"], "password": "WrongPassword123"},
        headers={"X-Forwarded-For": attacker_ip},
    )
    assert blocked.status_code == 429
    # Victim can still fail-login 5 times from their own IP.
    for i in range(5):
        r = client.post(
            "/api/v1/auth/login",
            json={"identifier": AUTH["email"], "password": "WrongPassword123"},
            headers={"X-Forwarded-For": "198.51.100.2"},
        )
        assert r.status_code == 401, (i, r.text)


def test_argon2d_hit_atomic_no_lost_increments(client):
    """ARGON-2d: concurrent _hit callers do not lose increments (MySQL upsert)."""
    import threading

    from app.db import SessionLocal

    subject = "login-ip:198.51.100.77"
    n_threads = 25
    barrier = threading.Barrier(n_threads)
    errors: list[BaseException] = []

    def worker() -> None:
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            try:
                auth_service._hit(db, subject, limit=10_000)
            except Exception as exc:  # noqa: BLE001 — collect for assertion
                errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == [], errors

    db = SessionLocal()
    try:
        row = db.get(
            AuthRateLimit,
            {"subject": subject, "window_start_utc": auth_service._window_start()},
        )
        assert row is not None
        assert row.hit_count == n_threads
    finally:
        db.close()


def test_argon3_authorization_and_cookie_redaction_and_selective_args():
    """ARGON-3: full Authorization value + Cookie kp_session; user.id survives."""
    from app.logging_redaction import RedactingFilter, is_sensitive_value, redact_text

    bearer = (
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.signaturepart"
    )
    redacted = redact_text(bearer)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
    assert "[REDACTED]" in redacted

    basic = "authorization: Basic dXNlcjpwYXNz"
    assert "dXNlcjpwYXNz" not in redact_text(basic)

    cookie = "Cookie: theme=dark; kp_session=eyJ.abc.def; other=1"
    cookie_out = redact_text(cookie)
    assert "eyJ.abc.def" not in cookie_out
    assert "theme=dark" in cookie_out

    set_cookie = "Set-Cookie: kp_session=secretjwtvalue; Path=/; HttpOnly"
    assert "secretjwtvalue" not in redact_text(set_cookie)

    # sensitive_msg must NOT redact a plain user id just because msg says password
    record = logging.LogRecord(
        name="app.auth",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="password reset token issued user_id=%s",
        args=("usr_abc123_not_a_secret________",),
        exc_info=None,
    )
    RedactingFilter().filter(record)
    combined = str(record.msg) + str(record.args)
    assert "usr_abc123_not_a_secret________" in combined
    assert not is_sensitive_value("usr_abc123_not_a_secret________")

    # But a JWT-shaped arg is redacted
    jwt_arg = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.sig"
    record2 = logging.LogRecord(
        name="app.auth",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token issued %s",
        args=(jwt_arg,),
        exc_info=None,
    )
    RedactingFilter().filter(record2)
    assert jwt_arg not in str(record2.args)


def test_argon4_test_support_password_reset_token_loopback_and_fail_closed(client, monkeypatch):
    """ARGON-4 / TC-4.10-41 / TC-SEC-TS-01: §5.32 loopback-only; 404 outside test."""
    assert _register(client).status_code == 201

    loopback = TestClient(app, client=("127.0.0.1", 50000))
    ok = loopback.post(
        "/api/v1/test-support/password-reset-token",
        json={"email": AUTH["email"]},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["reset_token"]
    assert "expires_at_utc" in body

    # Non-loopback peer → empty 404 (XFF must not count)
    remote = TestClient(app, client=("203.0.113.10", 50000))
    denied = remote.post(
        "/api/v1/test-support/password-reset-token",
        json={"email": AUTH["email"]},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert denied.status_code == 404
    assert denied.content == b""

    # Outside test mode → 404 even from loopback
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "production-secret-at-least-32-bytes-long")
    outside = TestClient(app, client=("127.0.0.1", 50000))
    prod = outside.post(
        "/api/v1/test-support/password-reset-token",
        json={"email": AUTH["email"]},
    )
    assert prod.status_code == 404
    assert prod.content == b""
    monkeypatch.setenv("APP_ENV", "test")


def test_argon5_revoke_other_sessions_skips_expired(client):
    """ARGON-5: revoked_count matches GET /auth/sessions (ignores expired rows)."""
    assert _register(client).status_code == 201
    # Current session
    assert _login(client).status_code == 200
    # Second active session via non-browser
    other = _client()
    login2 = other.post(
        "/api/v1/auth/login",
        json={"identifier": AUTH["email"], "password": AUTH["password"]},
        headers={"X-Client-Type": "non-browser"},
    )
    assert login2.status_code == 200
    # Third session already expired (should not count)
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email_norm == AUTH["email"]))
        db.add(
            SessionRow(
                id="jti_expired_argon5________________",
                user_id=user.id,
                device_label="expired-device",
                issued_at_utc=now_utc() - timedelta(hours=5),
                expires_at_utc=now_utc() - timedelta(minutes=1),
                last_seen_at=now_utc() - timedelta(hours=4),
                revoked_at=None,
            )
        )
        db.commit()
        listed_before = [
            s
            for s in db.scalars(
                select(SessionRow).where(
                    SessionRow.user_id == user.id,
                    SessionRow.revoked_at.is_(None),
                    SessionRow.expires_at_utc > now_utc(),
                )
            ).all()
        ]
        assert len(listed_before) == 2  # current + other; expired excluded
    finally:
        db.close()

    listed = client.get("/api/v1/auth/sessions")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 2

    revoked = client.delete("/api/v1/auth/sessions")
    assert revoked.status_code == 200
    # Only the other active session is revoked — not the expired one.
    assert revoked.json()["revoked_count"] == 1
