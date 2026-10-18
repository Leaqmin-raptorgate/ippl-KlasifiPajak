"""Shared FastAPI dependencies."""

from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.config.settings import Settings
from app.db import get_db
from app.models import Session as SessionRow
from app.models import User
from app.services.auth import authenticate


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: SessionRow


def get_settings() -> Settings:
    return Settings()


def current_session(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    """Read the session cookie or Bearer token and load its session row."""
    token = request.cookies.get("kp_session")
    if not token:
        header = request.headers.get("Authorization", "")
        scheme, _, value = header.partition(" ")
        if scheme.lower() == "bearer" and value:
            token = value
    if not token:
        raise ApiError(401, "UNAUTHENTICATED", "Sesi tidak ditemukan.")
    user, session = authenticate(db, token, settings)
    return AuthContext(user=user, session=session)
