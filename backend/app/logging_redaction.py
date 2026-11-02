"""Structured logging with redaction of secrets and PII (HB-06 / NFR-04).

Never emit passwords, reset plaintext, ``kp_session`` values, webhook secrets,
full NIB strings, or image bytes. Import :func:`configure_redacted_logging`
once at process start (routes_app does this).
"""

from __future__ import annotations

import logging
import re
from typing import Any

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "new_password",
        "old_password",
        "token",
        "reset_token",
        "kp_session",
        "authorization",
        "jwt",
        "jwt_secret",
        "webhook_secret",
        "server_key",
        "signature",
        "nib",
        "nib_full",
        "image_bytes",
        "receipt_bytes",
    }
)

_SENSITIVE_KEY_ALT = (
    "password|new_password|old_password|token|reset_token|kp_session|"
    "jwt_secret|webhook_secret|server_key|signature"
)

# Key=value forms (password=..., token: ..., kp_session=...).
_PASSWORDISH = re.compile(rf"(?i)\b({_SENSITIVE_KEY_ALT})([\"'\s:=]+)([^\s\"']+)")

# Authorization: <scheme> <credentials> — redact the whole value (ARGON-3).
_AUTHORIZATION = re.compile(r"(?i)\b(authorization)(\s*[:=]\s*)([^\r\n,;]+)")

# Cookie / Set-Cookie kp_session=...
_COOKIE_SESSION = re.compile(r"(?i)((?:(?:^|[;\s])|(?:set-cookie\s*[:=]\s*))kp_session=)([^\s;]+)")

# ``password=%s`` / ``token: %s`` — which positional args bind to secret keys.
_SENSITIVE_BEFORE_PERCENT = re.compile(rf"(?i)\b({_SENSITIVE_KEY_ALT})\s*[:=]\s*$")

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_NIB_LONG = re.compile(r"\b\d{13,22}\b")
_JWT_SHAPED = re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
_ARGON_OR_PBKDF = re.compile(r"^(\$argon2|pbkdf2_sha256\$)")

_CONFIGURED = False


class RedactingFilter(logging.Filter):
    """Replace known secret patterns in log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            original_msg = record.msg if isinstance(record.msg, str) else None
            if isinstance(record.msg, str):
                record.msg = redact_text(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: redact_value(k, v) for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    # ARGON-3: redact only sensitive args (not every string when
                    # the message merely mentions "password" / "token").
                    sensitive_slots = (
                        _sensitive_percent_indices(original_msg) if original_msg else set()
                    )
                    redacted_args: list[Any] = []
                    for idx, arg in enumerate(record.args):
                        if not isinstance(arg, str):
                            redacted_args.append(arg)
                            continue
                        if idx in sensitive_slots or is_sensitive_value(arg):
                            redacted_args.append("[REDACTED]")
                        else:
                            redacted_args.append(redact_text(arg))
                    record.args = tuple(redacted_args)
        except Exception:  # pragma: no cover - never break logging
            pass
        return True


def _sensitive_percent_indices(msg: str) -> set[int]:
    """Return positional arg indexes bound to a sensitive ``key=%s`` slot."""
    indices: set[int] = set()
    arg_i = 0
    i = 0
    length = len(msg)
    while i < length:
        if msg[i] == "%" and i + 1 < length:
            nxt = msg[i + 1]
            if nxt == "%":
                i += 2
                continue
            if nxt == "s":
                if _SENSITIVE_BEFORE_PERCENT.search(msg[:i]):
                    indices.add(arg_i)
                arg_i += 1
                i += 2
                continue
        i += 1
    return indices


def is_sensitive_value(value: str) -> bool:
    """True when a log argument itself looks like a secret (not a user id)."""
    if not value:
        return False
    if _EMAIL.search(value):
        return True
    if _JWT_SHAPED.match(value):
        return True
    if _ARGON_OR_PBKDF.match(value):
        return True
    if _PASSWORDISH.search(value) or _AUTHORIZATION.search(value):
        return True
    if _COOKIE_SESSION.search(value):
        return True
    return False


def redact_value(key: str, value: Any) -> Any:
    if key.lower() in _SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(k, v) for k, v in value.items()}
    return value


def redact_text(text: str) -> str:
    if not text:
        return text
    out = _AUTHORIZATION.sub(r"\1\2[REDACTED]", text)
    out = _COOKIE_SESSION.sub(r"\1[REDACTED]", out)
    out = _PASSWORDISH.sub(r"\1\2[REDACTED]", out)
    out = _EMAIL.sub("[REDACTED_EMAIL]", out)
    out = _NIB_LONG.sub("[REDACTED_NIB]", out)
    return out


def configure_redacted_logging() -> None:
    """Attach the redacting filter to the root and app loggers once."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    filt = RedactingFilter()
    root = logging.getLogger()
    root.addFilter(filt)
    for name in ("app", "uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).addFilter(filt)
    if not root.handlers:
        logging.basicConfig(level=logging.INFO)
        for handler in root.handlers:
            handler.addFilter(filt)
    _CONFIGURED = True


def get_logger(name: str = "app") -> logging.Logger:
    configure_redacted_logging()
    return logging.getLogger(name)
