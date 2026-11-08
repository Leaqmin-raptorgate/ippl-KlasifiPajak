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
#: Must stay in sync with the JWT_SECRET line in ``.env.example``.
_ENV_EXAMPLE_JWT_SECRET = "CHANGE_ME_TO_A_LONG_RANDOM_STRING"
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


def _env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _ai_timeout_s() -> float:
    raw = _env_str("AI_TIMEOUT_S", "30") or "30"
    try:
        return float(raw)
    except ValueError:
        return 30.0


def _smtp_port() -> int:
    raw = _env_str("SMTP_PORT", "587") or "587"
    try:
        return int(raw)
    except ValueError:
        return 587


def _jwt_secret() -> str:
    """Resolve the HS256 secret, refusing unsafe values outside development/test.

    HB-01 / TC-HARD-15: production (and any non-dev/test env) must not boot with
    an empty secret, the built-in placeholder, the ``.env.example`` placeholder
    (or any ``CHANGE_ME...`` marker value), or a secret shorter than 32 bytes.
    """
    secret = os.environ.get("JWT_SECRET", _DEV_PLACEHOLDER_SECRET)
    env = _app_env()
    if env in ("development", "test"):
        return secret or _DEV_PLACEHOLDER_SECRET
    stripped = (secret or "").strip()
    if (
        not stripped
        or secret == _DEV_PLACEHOLDER_SECRET
        or stripped == _ENV_EXAMPLE_JWT_SECRET
        or stripped.upper().startswith("CHANGE_ME")
        or len(stripped.encode("utf-8")) < _MIN_JWT_SECRET_LEN
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
    ai_base_url: str = field(default_factory=lambda: _env_str("AI_BASE_URL"))
    ai_api_key: str = field(default_factory=lambda: _env_str("AI_API_KEY"))
    ai_model_classifier: str = field(default_factory=lambda: _env_str("AI_MODEL_CLASSIFIER"))
    ai_model_ocr: str = field(default_factory=lambda: _env_str("AI_MODEL_OCR"))
    ai_model_assistant: str = field(default_factory=lambda: _env_str("AI_MODEL_ASSISTANT"))
    ai_timeout_s: float = field(default_factory=_ai_timeout_s)
    smtp_host: str = field(default_factory=lambda: _env_str("SMTP_HOST"))
    smtp_port: int = field(default_factory=_smtp_port)
    smtp_username: str = field(default_factory=lambda: _env_str("SMTP_USERNAME"))
    smtp_password: str = field(default_factory=lambda: _env_str("SMTP_PASSWORD"))
    smtp_from: str = field(default_factory=lambda: _env_str("SMTP_FROM"))
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
