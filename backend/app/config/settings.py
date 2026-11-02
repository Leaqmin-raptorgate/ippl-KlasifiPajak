"""Environment-derived settings.

Thresholds and quotas live here because they are configurable. Tax rates and
bands do not, because they belong to the ruleset (invariant 9).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

#: Origins allowed to call the API. The Vue dev server is the default; a
#: deployed frontend is added through ``CORS_ORIGINS`` at startup.
DEFAULT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

_DEV_PLACEHOLDER_SECRET = "dev-secret-change-me"
_MIN_JWT_SECRET_LEN = 32


def _cors_origins() -> tuple[str, ...]:
    if os.environ.get("APP_ENV") == "production":
        return ("https://app.klasifipajak.id",)
    raw = os.environ.get("CORS_ORIGINS", "")
    extra = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
    return DEFAULT_ORIGINS + extra


def _ruleset_path() -> Path | None:
    raw = os.environ.get("RULESET_PATH", "")
    return Path(raw) if raw.strip() else None


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "mysql+pymysql://klasifipajak:klasifipajak@127.0.0.1:3306/klasifipajak",
    )


def _app_env() -> str:
    return os.environ.get("APP_ENV", "development")


def _jwt_secret() -> str:
    """Resolve the HS256 secret, refusing unsafe values outside development/test.

    HB-01 / TC-HARD-15: production (and any non-dev/test env) must not boot with
    an empty secret, the built-in placeholder, or a secret shorter than 32 bytes.
    """
    secret = os.environ.get("JWT_SECRET", _DEV_PLACEHOLDER_SECRET)
    env = _app_env()
    if env in ("development", "test"):
        return secret or _DEV_PLACEHOLDER_SECRET
    if (
        not secret
        or secret.strip() == ""
        or secret == _DEV_PLACEHOLDER_SECRET
        or len(secret.encode("utf-8")) < _MIN_JWT_SECRET_LEN
    ):
        raise RuntimeError(
            "JWT_SECRET must be set to a non-default value of at least "
            f"{_MIN_JWT_SECRET_LEN} bytes when APP_ENV={env!r} "
            "(HB-01 fail-closed)."
        )
    return secret


@dataclass(frozen=True)
class Settings:
    """Startup configuration."""

    app_name: str = "KlasifiPajak"
    cors_origins: tuple[str, ...] = field(default_factory=_cors_origins)
    ruleset_path: Path | None = field(default_factory=_ruleset_path)
    database_url: str = field(default_factory=_database_url)
    jwt_secret: str = field(default_factory=_jwt_secret)
    session_hours: int = 12
    session_idle_minutes: int = 30
    max_sessions: int = 5

    @property
    def app_env(self) -> str:
        return _app_env()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        """True under ``APP_ENV=test``, the only environment where the
        ``paid_flag`` test adapter may run (FR-PAY-07)."""
        return os.environ.get("APP_ENV") == "test"
