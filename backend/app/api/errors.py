"""One error shape for every endpoint.

API v1.2.2 section 2.5 pins ``{"error": {"code", "message"}}``. Messages are
Indonesian because the frontend keys its text on the code and shows the
message as written.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config.settings import Settings

_SESSION_COOKIE_CLEAR_CODES = frozenset({"session_expired", "session_revoked"})


class ApiError(Exception):
    """A contract error with a stable code and an Indonesian message."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def install_error_handler(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle(_: Request, exc: ApiError) -> JSONResponse:
        response = JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
        # API §2.6 / B5: session death must clear kp_session with the same flags.
        if exc.code in _SESSION_COOKIE_CLEAR_CODES:
            settings = Settings()
            response.delete_cookie(
                "kp_session",
                path="/",
                httponly=True,
                samesite="lax",
                secure=settings.is_production,
            )
        return response
