"""Test-support routes (API §5.31 and §5.32). Mounted only when APP_ENV=test.

Fail-closed: each handler also refuses non-loopback callers using
``request.client.host`` only — never ``X-Forwarded-For`` (ARGON-4 / G-28).
"""

from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, StrictStr
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.db import get_db
from app.security import iso_utc
from app.services import auth as auth_service
from app.services import subscription as subscription_service

router = APIRouter()

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class PasswordResetTokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: StrictStr


class PasswordResetTokenOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    reset_token: str
    expires_at_utc: str


def _empty_404() -> Response:
    return Response(status_code=404, content=b"")


def _is_test_env() -> bool:
    return os.environ.get("APP_ENV") == "test"


def _is_loopback(request: Request) -> bool:
    """Judge loopback from the peer address only — never from XFF."""
    host = request.client.host if request.client else None
    return host in _LOOPBACK_HOSTS


# Peer hosts accepted by the subscription override. ``testclient`` is Starlette's
# default TestClient address; the password-reset route does not use it.
_OVERRIDE_HOSTS = frozenset({"127.0.0.1", "::1", "testclient", "localhost"})


@router.post("/test-support/subscription-override", response_model=None)
def subscription_override(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    """API §5.31 — not mounted outside APP_ENV=test; still 404 off loopback."""
    if not _is_test_env():
        return Response(status_code=404)
    host = (request.client.host if request.client else "") or ""
    if host not in _OVERRIDE_HOSTS:
        return Response(status_code=404)
    user_id = payload.get("user_id")
    if not user_id:
        raise ApiError(404, "USER_NOT_FOUND", "Pengguna tidak ditemukan.")
    raw = payload.get("valid_until")
    valid_until = None
    if raw:
        valid_until = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
    return subscription_service.set_subscription_override(
        db,
        user_id=str(user_id),
        paid_flag=bool(payload.get("paid_flag")),
        valid_until=valid_until,
    )


@router.post(
    "/test-support/password-reset-token",
    response_model=PasswordResetTokenOut,
    responses={404: {"description": "Not mounted / non-loopback / non-test"}},
)
def password_reset_token(
    payload: PasswordResetTokenIn,
    request: Request,
    db: Session = Depends(get_db),
) -> PasswordResetTokenOut | Response:
    """API §5.32: mint a reset token without sending mail (test/loopback only)."""
    if not _is_test_env() or not _is_loopback(request):
        return _empty_404()
    plaintext, expires = auth_service.mint_password_reset_token_for_tests(db, payload.email)
    return PasswordResetTokenOut(
        reset_token=plaintext,
        expires_at_utc=iso_utc(expires),
    )
