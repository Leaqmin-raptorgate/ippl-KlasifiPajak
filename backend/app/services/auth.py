"""Account and session use cases. No route builds a query."""

import unicodedata
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.config.settings import Settings
from app.models import Session as SessionRow
from app.models import User
from app.schemas.account import LoginIn, RegisterIn
from app.security import (
    InvalidToken,
    create_jwt,
    decode_jwt,
    device_label,
    hash_password,
    new_id,
    new_jti,
    now_utc,
    session_expiry,
    verify_password,
)

MIN_PASSWORD_LENGTH = 10


def normalize_identifier(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _display(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def register(db: Session, payload: RegisterIn) -> User:
    """Create an account. No session is created."""
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
    return user


def login(
    db: Session, payload: LoginIn, settings: Settings, user_agent: str
) -> tuple[User, SessionRow]:
    """Authenticate and insert one session. A sixth login revokes the oldest."""
    identifier = normalize_identifier(payload.identifier)
    user = db.scalar(
        select(User).where((User.email_norm == identifier) | (User.username_norm == identifier))
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise ApiError(401, "INVALID_CREDENTIALS", "Identitas atau kata sandi tidak valid.")
    issued = now_utc()
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
