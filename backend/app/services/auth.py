"""Account and session use cases. No route builds a query."""

from __future__ import annotations

import hmac
import unicodedata
from datetime import timedelta

from sqlalchemy import inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.config.settings import Settings
from app.logging_redaction import get_logger
from app.models import AuthRateLimit, PasswordResetToken, User
from app.models import Session as SessionRow
from app.schemas.account import (
    DeleteAccountIn,
    LoginIn,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    RegisterIn,
    SessionItemOut,
    validate_email_shape,
)
from app.security import (
    InvalidToken,
    create_jwt,
    decode_jwt,
    device_label,
    hash_password,
    hash_reset_token,
    iso_utc,
    new_id,
    new_jti,
    new_reset_token,
    now_utc,
    password_needs_rehash,
    session_expiry,
    verify_password,
)

MIN_PASSWORD_LENGTH = 10
RESET_TOKEN_MINUTES = 30
RATE_WINDOW_MINUTES = 15
REGISTER_IP_LIMIT = 5
LOGIN_ID_LIMIT = 5
LOGIN_IP_LIMIT = 20
ACCOUNT_CONFIRMATION = "HAPUS AKUN SAYA"
GENERIC_RESET_MESSAGE = (
    "Jika surel terdaftar pada sistem, petunjuk atur ulang kata sandi telah dikirimkan."
)
RESET_SUCCESS_MESSAGE = "Kata sandi berhasil diperbarui. Seluruh sesi aktif telah dibatalkan."
ACCOUNT_DELETED_MESSAGE = (
    "Seluruh data profil, transaksi, citra, dan cuplikan pajak Anda telah dihapus secara permanen."
)

log = get_logger("app.auth")

# Precomputed argon2id digest used only to equalize login timing when the
# identifier is unknown (API §5.2 / Code Review B1).
_DUMMY_PASSWORD_HASH = hash_password("__klasifipajak_timing_pad__")


def normalize_identifier(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _display(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def _client_ip(raw: str | None) -> str:
    if not raw:
        return "0.0.0.0"
    # First hop only; X-Forwarded-For may list several.
    return raw.split(",")[0].strip() or "0.0.0.0"


def _window_start():
    """Floor the current UTC instant to a 15-minute bucket."""
    now = now_utc()
    return now.replace(
        minute=(now.minute // RATE_WINDOW_MINUTES) * RATE_WINDOW_MINUTES, second=0, microsecond=0
    )


def _hit(db: Session, subject: str, limit: int) -> None:
    """Increment a rate-limit counter and raise 429 when the limit is exceeded."""
    window = _window_start()
    row = db.get(AuthRateLimit, {"subject": subject, "window_start_utc": window})
    if row is None:
        row = AuthRateLimit(subject=subject, window_start_utc=window, hit_count=0)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            # Concurrent first insert for the same window (N5).
            db.rollback()
            row = db.get(AuthRateLimit, {"subject": subject, "window_start_utc": window})
            if row is None:
                raise
    if row.hit_count >= limit:
        db.commit()
        raise ApiError(
            429,
            "RATE_LIMITED",
            "Terlalu banyak percobaan. Coba lagi dalam 15 menit.",
        )
    row.hit_count += 1
    db.commit()


def enforce_register_rate_limit(db: Session, client_ip: str) -> None:
    _hit(db, f"ip:{_client_ip(client_ip)}", REGISTER_IP_LIMIT)


def enforce_login_rate_limits(db: Session, identifier: str, client_ip: str) -> None:
    # Identity first (5), then IP (20) — API §5.2.
    _hit(db, f"id:{normalize_identifier(identifier)}", LOGIN_ID_LIMIT)
    _hit(db, f"ip:{_client_ip(client_ip)}", LOGIN_IP_LIMIT)


def enforce_reset_rate_limits(db: Session, email: str, client_ip: str) -> None:
    # Same window as login; checked before the generic response (API §5.2 / §5.4).
    _hit(db, f"id:{normalize_identifier(email)}", LOGIN_ID_LIMIT)
    _hit(db, f"ip:{_client_ip(client_ip)}", LOGIN_IP_LIMIT)


def register(db: Session, payload: RegisterIn, client_ip: str = "0.0.0.0") -> User:
    """Create an account. No session is created."""
    enforce_register_rate_limit(db, client_ip)
    validate_email_shape(payload.email)
    if len(payload.password) < MIN_PASSWORD_LENGTH:
        raise ApiError(
            422,
            "PASSWORD_TOO_SHORT",
            "Kata sandi harus memiliki panjang minimal 10 karakter.",
        )
    email = _display(payload.email)
    username = _display(payload.username)
    if not email or "@" not in email or not username:
        raise ApiError(422, "IDENTIFIER_REQUIRED", "Surel dan nama pengguna wajib diisi.")
    email_norm = normalize_identifier(email)
    username_norm = normalize_identifier(username)
    exists = db.scalar(
        select(User.id).where(
            (User.email_norm == email_norm) | (User.username_norm == username_norm)
        )
    )
    if exists is not None:
        raise ApiError(
            409,
            "IDENTIFIER_ALREADY_EXISTS",
            "Surel atau nama pengguna sudah terdaftar.",
        )
    user = User(
        id=new_id("usr_"),
        email=email,
        email_norm=email_norm,
        username=username,
        username_norm=username_norm,
        password_hash=hash_password(payload.password),
        paid_flag=False,
        created_at=now_utc(),
    )
    db.add(user)
    db.commit()
    log.info("user registered user_id=%s", user.id)
    return user


def login(
    db: Session,
    payload: LoginIn,
    settings: Settings,
    user_agent: str,
    client_ip: str = "0.0.0.0",
) -> tuple[User, SessionRow]:
    """Authenticate and insert one session. A sixth login revokes the oldest."""
    enforce_login_rate_limits(db, payload.identifier, client_ip)
    identifier = normalize_identifier(payload.identifier)
    user = db.scalar(
        select(User).where((User.email_norm == identifier) | (User.username_norm == identifier))
    )
    if user is None:
        # B1: always pay argon2id verify cost so timing does not leak existence.
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        log.info("login failed for identifier_norm=%s", identifier)
        raise ApiError(401, "INVALID_CREDENTIALS", "Identitas atau kata sandi tidak valid.")
    if not verify_password(payload.password, user.password_hash):
        log.info("login failed for identifier_norm=%s", identifier)
        raise ApiError(401, "INVALID_CREDENTIALS", "Identitas atau kata sandi tidak valid.")
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    issued = now_utc()
    # Expired / revoked rows are pruned on a later login (ERD sessions note).
    for stale in db.scalars(
        select(SessionRow).where(
            SessionRow.user_id == user.id,
            (SessionRow.revoked_at.is_not(None)) | (SessionRow.expires_at_utc <= issued),
        )
    ).all():
        db.delete(stale)
    session = SessionRow(
        id=new_jti(),
        user_id=user.id,
        device_label=device_label(user_agent),
        issued_at_utc=issued,
        expires_at_utc=session_expiry(issued, settings.session_hours),
        last_seen_at=issued,
        revoked_at=None,
    )
    db.add(session)
    db.flush()
    active = db.scalars(
        select(SessionRow)
        .where(
            SessionRow.user_id == user.id,
            SessionRow.revoked_at.is_(None),
            SessionRow.expires_at_utc > issued,
        )
        .order_by(SessionRow.last_seen_at)
    ).all()
    for stale in active[: max(0, len(active) - settings.max_sessions)]:
        stale.revoked_at = issued
    db.commit()
    log.info("login ok user_id=%s session_id=%s", user.id, session.id)
    return user, session


def authenticate(db: Session, token: str, settings: Settings) -> tuple[User, SessionRow]:
    """Decode an HS256 token and load its unrevoked, unexpired session row."""
    try:
        claims = decode_jwt(token, settings.jwt_secret)
    except InvalidToken as exc:
        raise ApiError(401, "UNAUTHENTICATED", "Sesi tidak valid.") from exc
    session = db.get(SessionRow, claims["jti"])
    now = now_utc()
    if session is None:
        raise ApiError(401, "UNAUTHENTICATED", "Sesi tidak valid.")
    if claims.get("sub") != session.user_id:
        # N1: JWT sub must match the session row's user.
        raise ApiError(401, "UNAUTHENTICATED", "Sesi tidak valid.")
    if session.revoked_at is not None:
        raise ApiError(401, "session_revoked", "Sesi ini sudah dibatalkan.")
    if now > session.expires_at_utc:
        raise ApiError(401, "session_expired", "Sesi telah berakhir. Silakan masuk kembali.")
    if now - session.last_seen_at > timedelta(minutes=settings.session_idle_minutes):
        raise ApiError(401, "session_expired", "Sesi tidak aktif terlalu lama.")
    if now - session.last_seen_at > timedelta(minutes=1):
        session.last_seen_at = now
        db.commit()
    user = db.get(User, session.user_id)
    if user is None:
        raise ApiError(401, "UNAUTHENTICATED", "Sesi tidak valid.")
    return user, session


def logout(db: Session, session: SessionRow) -> None:
    """Revoke only this jti."""
    try:
        session.revoked_at = now_utc()
        db.commit()
    except Exception as exc:  # pragma: no cover - driver failure path
        db.rollback()
        raise ApiError(
            500,
            "REVOCATION_FAILED",
            "Gagal membatalkan sesi pada basis data. Silakan coba lagi.",
        ) from exc


def token_for(user: User, session: SessionRow, settings: Settings) -> str:
    return create_jwt(
        user.id,
        session.id,
        session.issued_at_utc,
        session.expires_at_utc,
        settings.jwt_secret,
    )


def request_password_reset(
    db: Session, payload: PasswordResetRequestIn, client_ip: str = "0.0.0.0"
) -> str:
    """Always return the generic message; never reveal whether the email exists."""
    # N2 / HB-04: shape check before rate limit so 422 does not leak existence.
    validate_email_shape(payload.email)
    enforce_reset_rate_limits(db, payload.email, client_ip)
    email_norm = normalize_identifier(payload.email)
    user = db.scalar(select(User).where(User.email_norm == email_norm))
    # B2: always mint + hash so known/unknown pay the same CPU before branching.
    plaintext = new_reset_token()
    digest = hash_reset_token(plaintext)
    if user is not None:
        now = now_utc()
        # N3: invalidate older unused tokens for this user when issuing a new one.
        db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        row = PasswordResetToken(
            id=new_id("rst_"),
            user_id=user.id,
            token_hash=digest,
            expires_at_utc=now + timedelta(minutes=RESET_TOKEN_MINUTES),
            used_at=None,
        )
        db.add(row)
        db.commit()
        # Plaintext is returned only to the caller that can deliver mail / tests.
        # Routes discard it and respond with the generic message only.
        log.info("password reset token issued user_id=%s", user.id)
        return plaintext
    # Unknown email: mint+hash already done; touch the DB with a no-op UPDATE so
    # known/unknown pay a similar round-trip (B2) without inserting a fake row.
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == "__timing_pad__",
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now_utc())
    )
    db.commit()
    log.info("password reset requested for unknown email")
    return ""


def confirm_password_reset(db: Session, payload: PasswordResetConfirmIn) -> None:
    if len(payload.new_password) < MIN_PASSWORD_LENGTH:
        raise ApiError(
            422,
            "PASSWORD_TOO_SHORT",
            "Kata sandi baru harus memiliki panjang minimal 10 karakter.",
        )
    digest = hash_reset_token(payload.token)
    now = now_utc()
    # B4: atomic single-use consume — only one concurrent caller can win.
    result = db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == digest,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at_utc >= now,
        )
        .values(used_at=now)
    )
    if result.rowcount != 1:
        raise ApiError(
            400,
            "TOKEN_INVALID_OR_EXPIRED",
            "Token atur ulang kata sandi tidak sah atau telah kedaluwarsa.",
        )
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == digest))
    if row is None or not hmac.compare_digest(row.token_hash, digest):
        raise ApiError(
            400,
            "TOKEN_INVALID_OR_EXPIRED",
            "Token atur ulang kata sandi tidak sah atau telah kedaluwarsa.",
        )
    user = db.get(User, row.user_id)
    if user is None:
        raise ApiError(
            400,
            "TOKEN_INVALID_OR_EXPIRED",
            "Token atur ulang kata sandi tidak sah atau telah kedaluwarsa.",
        )
    user.password_hash = hash_password(payload.new_password)
    # B3: invalidate every other unused reset token for this user in the same txn.
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    for session in db.scalars(select(SessionRow).where(SessionRow.user_id == user.id)).all():
        if session.revoked_at is None:
            session.revoked_at = now
    db.commit()
    log.info("password reset confirmed user_id=%s", user.id)


def list_sessions(db: Session, user: User, current: SessionRow) -> list[SessionItemOut]:
    rows = db.scalars(
        select(SessionRow)
        .where(
            SessionRow.user_id == user.id,
            SessionRow.revoked_at.is_(None),
            SessionRow.expires_at_utc > now_utc(),
        )
        .order_by(SessionRow.issued_at_utc.desc())
    ).all()
    return [
        SessionItemOut(
            id=row.id,
            device_label=row.device_label,
            created_at=iso_utc(row.issued_at_utc),
            last_seen_at=iso_utc(row.last_seen_at),
            current=row.id == current.id,
        )
        for row in rows
    ]


def revoke_session(db: Session, user: User, session_id: str) -> None:
    row = db.get(SessionRow, session_id)
    if row is None or row.user_id != user.id:
        raise ApiError(404, "SESSION_NOT_FOUND", "Sesi tidak ditemukan.")
    if row.revoked_at is None:
        row.revoked_at = now_utc()
        db.commit()


def revoke_other_sessions(db: Session, user: User, current: SessionRow) -> int:
    now = now_utc()
    count = 0
    for row in db.scalars(
        select(SessionRow).where(
            SessionRow.user_id == user.id,
            SessionRow.id != current.id,
            SessionRow.revoked_at.is_(None),
        )
    ).all():
        row.revoked_at = now
        count += 1
    db.commit()
    return count


def _table_exists(db: Session, name: str) -> bool:
    return inspect(db.bind).has_table(name)


def delete_account(db: Session, user: User, payload: DeleteAccountIn) -> None:
    """Cascade-delete the account per API §5.6. Missing optional tables are skipped."""
    if payload.confirmation != ACCOUNT_CONFIRMATION:
        raise ApiError(
            422,
            "CONFIRMATION_TEXT_MISMATCH",
            "Teks konfirmasi penghapusan akun tidak sesuai.",
        )
    user_id = user.id

    # Payment tables: null user_id when present (API §5.6 order).
    if _table_exists(db, "subscription_orders"):
        db.execute(
            text("UPDATE subscription_orders SET user_id = NULL WHERE user_id = :uid"),
            {"uid": user_id},
        )
    if _table_exists(db, "payment_events"):
        db.execute(
            text("UPDATE payment_events SET user_id = NULL WHERE user_id = :uid"),
            {"uid": user_id},
        )

    # Sessions and reset tokens.
    for row in db.scalars(select(SessionRow).where(SessionRow.user_id == user_id)).all():
        db.delete(row)
    for row in db.scalars(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
    ).all():
        db.delete(row)

    # Profiles → changes + snapshots.
    from app.models import ClassificationEvent, MonthSnapshot, Profile, ProfileChange, Transaction

    profiles = db.scalars(select(Profile).where(Profile.user_id == user_id)).all()
    for profile in profiles:
        for snap in db.scalars(
            select(MonthSnapshot).where(MonthSnapshot.profile_id == profile.id)
        ).all():
            db.delete(snap)
        for change in db.scalars(
            select(ProfileChange).where(ProfileChange.profile_id == profile.id)
        ).all():
            db.delete(change)
        # Flush children first so MySQL FK checks pass (profile_changes → profiles).
        db.flush()
        db.delete(profile)
    db.flush()

    # Transactions → classification events; receipt_images if present.
    transactions = db.scalars(select(Transaction).where(Transaction.user_id == user_id)).all()
    for tx in transactions:
        for ev in db.scalars(
            select(ClassificationEvent).where(ClassificationEvent.transaction_id == tx.id)
        ).all():
            db.delete(ev)
        db.flush()
        db.delete(tx)
    db.flush()

    if _table_exists(db, "receipt_images"):
        # Filesystem purge is Storage's concern when the table exists; null-safe delete.
        db.execute(text("DELETE FROM receipt_images WHERE user_id = :uid"), {"uid": user_id})

    if _table_exists(db, "quota_counters"):
        db.execute(text("DELETE FROM quota_counters WHERE user_id = :uid"), {"uid": user_id})

    db.delete(user)
    db.commit()
    log.info("account deleted user_id=%s", user_id)
