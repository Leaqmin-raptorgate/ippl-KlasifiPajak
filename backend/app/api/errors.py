"""One error shape for every endpoint.

API v1.2.2 section 2.5 pins ``{"error": {"code", "message"}}``. Messages are
Indonesian because the frontend keys its text on the code and shows the
message as written.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


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
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
