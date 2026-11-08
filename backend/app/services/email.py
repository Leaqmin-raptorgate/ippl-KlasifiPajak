"""Password-reset mail delivery (FR-41).

Importing this module does not open a socket. SMTP settings are read when a
message is sent, and the plaintext token is never written to a log.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.logging_redaction import get_logger

log = get_logger("app.email")

_NOT_CONFIGURED = "password reset mail not configured"


class EmailSender(Protocol):
    """Delivers one password-reset token to a mailbox (FR-41)."""

    def send_password_reset(self, recipient: str, token: str) -> None:
        """Send ``token`` to ``recipient``. Do not log ``token``."""


class FakeEmailSender:
    """In-memory sender for tests. Records recipient and plaintext only."""

    def __init__(self) -> None:
        self.deliveries: list[tuple[str, str]] = []

    def send_password_reset(self, recipient: str, token: str) -> None:
        """Record one delivery without writing the token to a log."""
        self.deliveries.append((recipient, token))


class _UnconfiguredEmailSender:
    """No-op sender used when ``SMTP_HOST`` is empty. Records nothing."""

    def send_password_reset(self, recipient: str, token: str) -> None:
        """Log that mail is not configured. The token is ignored."""
        del recipient, token
        log.info(_NOT_CONFIGURED)


class SmtpEmailSender:
    """Stdlib SMTP sender. Host and credentials are read at send time (FR-41)."""

    def send_password_reset(self, recipient: str, token: str) -> None:
        """Send a reset message. Never log the token or the message body."""
        host = os.environ.get("SMTP_HOST", "").strip()
        if not host:
            log.info(_NOT_CONFIGURED)
            return
        raw_port = os.environ.get("SMTP_PORT", "").strip() or "587"
        try:
            port = int(raw_port)
        except ValueError:
            port = 587
        username = os.environ.get("SMTP_USERNAME", "")
        password = os.environ.get("SMTP_PASSWORD", "")
        sender = os.environ.get("SMTP_FROM", "").strip() or username or "noreply@localhost"
        message = EmailMessage()
        message["Subject"] = "Atur ulang kata sandi KlasifiPajak"
        message["From"] = sender
        message["To"] = recipient
        message.set_content(
            "Gunakan token ini untuk mengatur ulang kata sandi KlasifiPajak.\n"
            "Token berlaku 30 menit dan hanya sekali pakai.\n\n"
            f"{token}\n"
        )
        client_cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        try:
            with client_cls(host, port, timeout=30) as smtp:
                smtp.ehlo()
                if port == 587:
                    smtp.starttls()
                    smtp.ehlo()
                if username:
                    smtp.login(username, password)
                smtp.send_message(message)
        except Exception:
            log.info("password reset mail failed")
            raise


def build_email_sender() -> EmailSender:
    """Return SMTP when ``SMTP_HOST`` is set, otherwise a sender that stores nothing."""
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return _UnconfiguredEmailSender()
    return SmtpEmailSender()
