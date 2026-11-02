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

_PASSWORDISH = re.compile(
    r"(?i)(password|new_password|token|kp_session|authorization|webhook_secret|server_key)"
    r"([\"'\s:=]+)([^\s\"']+)"
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_NIB_LONG = re.compile(r"\b\d{13,22}\b")

_CONFIGURED = False


class RedactingFilter(logging.Filter):
    """Replace known secret patterns in log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            sensitive_msg = False
            if isinstance(record.msg, str):
                sensitive_msg = bool(_PASSWORDISH.search(record.msg)) or any(
                    key in record.msg.lower() for key in _SENSITIVE_KEYS
                )
                record.msg = redact_text(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: redact_value(k, v) for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    if sensitive_msg:
                        record.args = tuple(
                            "[REDACTED]" if isinstance(a, str) else a for a in record.args
                        )
                    else:
                        record.args = tuple(
                            redact_text(a) if isinstance(a, str) else a for a in record.args
                        )
        except Exception:  # pragma: no cover - never break logging
            pass
        return True


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
    out = _PASSWORDISH.sub(r"\1\2[REDACTED]", text)
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
