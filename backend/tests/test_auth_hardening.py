"""Security-lane hardening and F-AUTH coverage (M50 / D-05 / D-07).

TC ids referenced in briefs/M50-security.md and proposals/testing/TC-4.10.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config.settings import _jwt_secret
from app.db import SessionLocal
from app.logging_redaction import RedactingFilter, redact_text
from app.main import app
from app.models import PasswordResetToken, User
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


def test_disclaimer_remains_workpaper_spelling():
    """Canonical disclaimer spelling lock (D-07)."""
    from app.services.snapshot import DISCLAIMER

    assert "WORKPAPER" in DISCLAIMER
    assert "WORKOBER" not in DISCLAIMER
