"""One error shape for every endpoint.

API v1.3.2 section 2.5 pins ``{"error": {"code", "message"}}``. Messages are
Indonesian because the frontend keys its text on the code and shows the
message as written. Request validation uses that same envelope. This module
does not add ``field`` or ``field_errors``; nothing else in the API returns them.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config.settings import Settings

_SESSION_COOKIE_CLEAR_CODES = frozenset({"session_expired", "session_revoked"})


class ApiError(Exception):
    """A contract error with a stable code and an Indonesian message."""

    def __init__(self, status: int, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field


def install_error_handler(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = {str(item["loc"][-1]): "Nilai bidang ini tidak valid." for item in exc.errors()}
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Data yang dikirim tidak valid.",
                    "field_errors": fields,
                }
            },
        )

    @app.exception_handler(ApiError)
    async def _handle(_: Request, exc: ApiError) -> JSONResponse:
        response = JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
        if exc.field:
            response = JSONResponse(
                status_code=exc.status,
                content={"error": {"code": exc.code, "message": exc.message, "field": exc.field}},
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

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        loc = []
        errors = exc.errors()
        if errors:
            loc = [str(part) for part in errors[0].get("loc", ()) if part != "body"]
        field = loc[-1] if loc else ""
        if field:
            message = f"Isian {field} tidak valid. Periksa data yang dikirim, lalu coba lagi."
        else:
            message = "Isian tidak valid. Periksa data yang dikirim, lalu coba lagi."
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "VALIDATION_ERROR", "message": message}},
        )
