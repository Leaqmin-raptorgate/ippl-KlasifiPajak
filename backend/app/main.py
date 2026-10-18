"""ASGI entry point for the KlasifiPajak API.

Bagian A is the engine on the loopback interface; Bagian B is the authenticated
application surface under ``/api/v1``. Bagian A is not mounted in production.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handler
from app.api.routes import router as engine_router
from app.api.routes_app import router as app_router
from app.config.settings import Settings
from app.db import init_db

settings = Settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description=(
        "Deterministic Final PPh engine over classified transactions. "
        "A workpaper computation, not a filed return."
    ),
    lifespan=lifespan,
)

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
