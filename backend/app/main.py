"""ASGI entry point for the KlasifiPajak API.

Bagian A is the engine on the loopback interface; Bagian B is the authenticated
application surface under ``/api/v1``. Bagian A is not mounted in production.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handler
from app.api.routes import router as engine_router
from app.api.routes_app import router as app_router
from app.api.routes_assistant import router as assistant_router
from app.api.routes_consent import router as consent_router
from app.api.routes_payments import router as payments_router
from app.api.routes_recap import router as recap_router
from app.api.routes_receipts import router as receipts_router
from app.api.routes_test_support import refuse_non_loopback_test_bind
from app.api.routes_test_support import router as test_support_router
from app.api.upload_limit import UploadSizeLimitMiddleware
from app.config.settings import Settings
from app.db import init_db

settings = Settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    refuse_non_loopback_test_bind(os.environ.get("BIND_HOST"))
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.5.0",
    description=(
        "Deterministic Final PPh engine over classified transactions. "
        "A workpaper computation, not a filed return."
    ),
    lifespan=lifespan,
)

# Added first, so it sits inside CORS and a 413 still carries the CORS headers.
app.add_middleware(UploadSizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Client-Type"],
)

install_error_handler(app)

if not settings.is_production:
    app.include_router(engine_router)
app.include_router(app_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")
app.include_router(recap_router, prefix="/api/v1")
app.include_router(consent_router, prefix="/api/v1")
app.include_router(assistant_router, prefix="/api/v1")
app.include_router(receipts_router, prefix="/api/v1")
# API §5.31–§5.32: test-support routes mount only under APP_ENV=test.
if settings.is_test:
    app.include_router(test_support_router, prefix="/api/v1")
