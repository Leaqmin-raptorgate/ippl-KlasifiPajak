"""Password hashing, JWT, and opaque identifier helpers.

Only the standard library is used: PBKDF2-HMAC-SHA256 for passwords and
HS256 for the session token the API spec pins. No algorithm is negotiated.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

_PBKDF2_ITERATIONS = 600_000
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class InvalidToken(Exception):
    """A token is malformed, carries the wrong algorithm, or has expired."""


def now_utc() -> datetime:
    """Naive UTC instant, matching the ERD's ``DATETIME(6)`` contract."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(value: datetime) -> str:
    """Render an instant as the API's ``YYYY-MM-DDTHH:mm:ssZ``."""
    return value.replace(microsecond=0).isoformat() + "Z"


def hash_password(password: str) -> str:
    """Salt and stretch a password with PBKDF2-HMAC-SHA256."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Compare a candidate constant-time against the stored digest."""
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations),
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def create_jwt(
    user_id: str, jti: str, issued_at: datetime, expires_at: datetime, secret: str
) -> str:
    """Encode the five claims the contract requires, pinned to HS256."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "jti": jti,
        "iat": int(issued_at.replace(tzinfo=timezone.utc).timestamp()),
        "exp": int(expires_at.replace(tzinfo=timezone.utc).timestamp()),
    }
    segments = [
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return ".".join(segments + [_b64url(signature)])


def decode_jwt(token: str, secret: str) -> dict:
    """Verify an HS256 token and return its claims.

    ``none`` and every other algorithm are rejected, as is an expired token.
    """
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
        header = json.loads(_b64url_decode(header_segment))
        payload = json.loads(_b64url_decode(payload_segment))
        signature = _b64url_decode(signature_segment)
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidToken("malformed token") from exc
    if header.get("alg") != "HS256":
        raise InvalidToken("unsupported algorithm")
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{header_segment}.{payload_segment}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(signature, expected):
        raise InvalidToken("bad signature")
    if not all(claim in payload for claim in ("sub", "jti", "iat", "exp")):
        raise InvalidToken("missing claim")
    if time.time() > payload["exp"]:
        raise InvalidToken("expired")
    return payload


def session_expiry(issued_at: datetime, hours: int) -> datetime:
    return issued_at + timedelta(hours=hours)


def new_id(prefix: str) -> str:
    """Prefix plus a 26-character Crockford ULID-shaped identifier."""
    value = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return prefix + "".join(reversed(chars))


def new_jti() -> str:
    """A UUID v4, which the contract uses as the JWT ``jti`` and session id."""
    return str(uuid.uuid4())


def device_label(user_agent: str) -> str:
    """Browser family and OS only, never the raw user agent."""
    ua = user_agent or ""
    browser = next(
        (
            name
            for name in ("Edg", "Firefox", "Chrome", "Safari", "Opera")
            if name.lower() in ua.lower()
        ),
        "Peramban",
    )
    system = next(
        (
            name
            for name in ("Windows", "Android", "iOS", "Macintosh", "Linux")
            if name.lower() in ua.lower()
        ),
        "Sistem",
    )
    return f"{browser} di {system}"
