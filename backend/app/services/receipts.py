"""Paid receipt upload, OCR candidates, and private file cleanup (FR-06, FR-06a, FR-06b).

Bytes live under ``RECEIPT_STORAGE_ROOT``, never in a BLOB and never in logs.
Candidates are stored on the image row only. A transaction is created later,
from the values the user confirms.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import threading
import time
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.classify.model_client import ModelUnavailable, OpenAICompatibleClient
from app.engine import Ruleset
from app.models import ReceiptImage, User
from app.models import Transaction as TransactionRow
from app.security import new_id, now_utc

# Read inside functions. Tests replace this global; do not copy it at import.

log = logging.getLogger(__name__)
RECEIPT_STORAGE_ROOT = os.environ.get("RECEIPT_STORAGE_ROOT", "/var/lib/klasifipajak/receipts")

_MAX_BYTES = 8 * 1024 * 1024
# Set before every decode. Below Pillow's default bomb ceiling so a
# process-wide None cannot turn the check off. About 8000 x 5000.
_MAX_IMAGE_PIXELS = 40_000_000
_UPLOAD_LIMIT = 30
_UPLOAD_WINDOW_S = 3600.0
_RETENTION = timedelta(days=7)

_PAID_MESSAGE = "Fitur unggah struk OCR hanya tersedia bagi pengguna berbayar aktif."
_CONSENT_MESSAGE = "Persetujuan pemrosesan AI diperlukan sebelum fitur ini digunakan."
_SIZE_MESSAGE = "Ukuran berkas melebihi batas maksimum 8 MB."
_TYPE_MESSAGE = "Berkas harus berupa JPEG atau PNG."
_RATE_MESSAGE = "Terlalu banyak unggahan struk. Coba lagi dalam satu jam."
_NOT_FOUND = "Transaksi tidak ditemukan."

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG"
_DATE_TEXT = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BIGINT_MAX = 9_223_372_036_854_775_807

OCR_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "amount_idr": {"type": ["integer", "null"]},
        "tx_date": {"type": ["string", "null"]},
        "client_name": {"type": ["string", "null"], "maxLength": 255},
        "invoice_no": {"type": ["string", "null"], "maxLength": 64},
    },
    "required": ["amount_idr", "tx_date", "client_name", "invoice_no"],
}

_rate_lock = threading.Lock()
_upload_hits: dict[str, list[float]] = {}


class _UnconfiguredOcrClient:
    """OCR stand-in used when the model environment is incomplete (FR-06a)."""

    def complete(
        self, messages: list[dict[str, Any]], *, response_schema: dict | None = None
    ) -> Any:
        """Refuse without opening a connection."""
        raise ModelUnavailable("OCR model is not configured")


def get_ocr_client() -> Any:
    """Build an OCR client from the environment at call time (FR-06).

    ``AI_BASE_URL``, ``AI_API_KEY``, and ``AI_MODEL_OCR`` must all be non-empty.
    Otherwise the returned client raises ``ModelUnavailable`` and does not
    connect. ``AI_TIMEOUT_S`` is read here as well.
    """
    base = os.environ.get("AI_BASE_URL", "").strip()
    key = os.environ.get("AI_API_KEY", "").strip()
    model = os.environ.get("AI_MODEL_OCR", "").strip()
    if not base or not key or not model:
        return _UnconfiguredOcrClient()
    return OpenAICompatibleClient(
        base_url=base,
        api_key=key,
        model=model,
        timeout_s=_timeout_s(),
    )


def read_bounded(source: Any) -> bytes:
    """Read an upload, stopping one byte past the 8 MB gate (FR-06)."""
    chunks: list[bytes] = []
    total = 0
    while total <= _MAX_BYTES:
        chunk = source.read(1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > _MAX_BYTES:
            break
    raw = b"".join(chunks)
    if len(raw) > _MAX_BYTES:
        return raw[: _MAX_BYTES + 1]
    return raw


def upload_receipt(db: Session, user: User, raw: bytes, content_type: str | None) -> dict:
    """Store one stripped receipt and its OCR candidates (FR-06, FR-06a).

    Paid, consent, size, and type gates all run before a file is created.
    A model failure leaves the candidates null and still returns the image.
    """
    _require_paid(user)
    _require_consent(user)
    if len(raw) > _MAX_BYTES:
        raise ApiError(422, "IMAGE_EXCEEDS_SIZE_LIMIT", _SIZE_MESSAGE)
    mime = _agreed_mime(raw, content_type)
    if mime is None:
        raise ApiError(422, "IMAGE_TYPE_NOT_SUPPORTED", _TYPE_MESSAGE)
    # Use up the hourly slot first, so a file that fails to decode still counts.
    _consume_upload_slot(user.id)
    encoded = _reencode(raw, mime)

    now = now_utc()
    if _purge_expired_unconfirmed(db, user.id, now):
        db.commit()

    image_id = new_id("img_")
    extension = "jpg" if mime == "image/jpeg" else "png"
    storage_key = f"receipts/{now.year:04d}/{now.month:02d}/{image_id}.{extension}"
    try:
        _write_bytes(storage_key, encoded)
        columns = _extract_candidates(encoded, mime)
        db.add(
            ReceiptImage(
                id=image_id,
                user_id=user.id,
                storage_key=storage_key,
                mime_type=mime,
                size_bytes=len(encoded),
                candidate_amount_idr=columns["amount_idr"],
                candidate_tx_date=columns["tx_date"],
                candidate_client_name=columns["client_name"],
                candidate_invoice_no=columns["invoice_no"],
                created_at=now,
                expires_at_utc=now + _RETENTION,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        _delete_bytes(storage_key)
        raise
    return {"image_id": image_id, "candidate_fields": _public_candidates(columns)}


def receipt_bytes(db: Session, user: User, image_id: str) -> tuple[bytes, str]:
    """Return one owner's stripped receipt, or an opaque not-found (FR-06)."""
    image = _owned_image(db, user.id, image_id)
    path = _path_for_key(image.storage_key)
    if path is None:
        raise ApiError(404, "TRANSACTION_NOT_FOUND", _NOT_FOUND)
    try:
        data = path.read_bytes()
    except OSError:
        raise ApiError(404, "TRANSACTION_NOT_FOUND", _NOT_FOUND) from None
    return data, image.mime_type


def confirm_receipt(
    db: Session,
    user: User,
    *,
    image_id: str,
    confirmed_amount_idr: int,
    confirmed_tx_date: date,
    confirmed_client_name: str,
    confirmed_description: str,
    confirmed_invoice_no: str | None,
    withheld_tax_amount_idr: int,
    source_channel: str,
    ruleset: Ruleset,
    background=None,
) -> dict:
    """Create a transaction from confirmed fields only (FR-06b).

    ``candidate_*`` on the image row is never copied onto the transaction.
    Classification stays inside ``create_transaction``.
    """
    _require_paid(user)
    image = _owned_image(db, user.id, image_id)
    # Serialize concurrent confirms of one receipt: the second waits here, then
    # sees the first one's transaction below.
    image = db.scalar(
        select(ReceiptImage)
        .where(ReceiptImage.id == image.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = now_utc()
    if image is None or (image.expires_at_utc is not None and image.expires_at_utc < now):
        raise ApiError(404, "TRANSACTION_NOT_FOUND", _NOT_FOUND)
    existing = db.scalar(select(TransactionRow.id).where(TransactionRow.image_id == image.id))
    if existing is not None:
        raise ApiError(409, "RECEIPT_ALREADY_CONFIRMED", "Struk sudah dikaitkan dengan transaksi.")

    from app.schemas.transaction import TransactionCreate
    from app.services.transactions import create_transaction

    payload = TransactionCreate(
        amount_idr=confirmed_amount_idr,
        tx_date=confirmed_tx_date,
        client_name=confirmed_client_name,
        description=confirmed_description,
        invoice_no=confirmed_invoice_no,
        withheld_tax_amount_idr=withheld_tax_amount_idr,
        source_channel=source_channel,
    )
    created = create_transaction(
        db, user, payload, ruleset, background=background, image_id=image.id
    )
    return {"image_id": image.id, "transaction": created.model_dump(mode="json")}


def delete_receipt_for_transaction(db: Session, row: TransactionRow) -> str | None:
    """Detach a transaction's receipt and return the storage key to remove (FR-09).

    The file is NOT deleted here: the caller commits the database work first
    and then calls ``remove_files``, so a rolled-back request never loses bytes.
    The receipt row goes only when no other transaction still references it.
    """
    image_id = row.image_id
    if not image_id:
        return None
    image = db.get(ReceiptImage, image_id)
    if image is None:
        return None
    other = db.scalar(
        select(TransactionRow.id).where(
            TransactionRow.image_id == image_id,
            TransactionRow.id != row.id,
        )
    )
    if other is not None:
        return None
    key = image.storage_key
    row.image_id = None
    db.flush()
    db.delete(image)
    return key


def purge_expired_receipts(db: Session) -> int:
    """Delete expired receipt rows and files that no transaction references.

    Returns how many rows were removed and commits that work. A linked receipt
    is kept even when ``expires_at_utc`` is already past. There is no scheduler;
    ``python -m app.scripts.purge_receipts`` calls this.
    """
    now = now_utc()
    referenced = (
        select(TransactionRow.id).where(TransactionRow.image_id == ReceiptImage.id).exists()
    )
    rows = db.scalars(
        select(ReceiptImage).where(ReceiptImage.expires_at_utc < now, ~referenced)
    ).all()
    removed = 0
    for row in rows:
        if not _delete_bytes(row.storage_key):
            continue
        db.delete(row)
        removed += 1
    db.commit()
    retry_pending_deletions()
    return removed


def delete_user_files(db: Session, user_id: str) -> list[str]:
    """Return the storage keys of every receipt stored for this account (FR-06, FR-42).

    Deletes nothing and does not commit. Call it while the ``receipt_images``
    rows still exist, commit the account deletion, then pass the keys to
    ``remove_files``.
    """
    rows = db.scalars(select(ReceiptImage).where(ReceiptImage.user_id == user_id)).all()
    return [row.storage_key for row in rows]


def _pending_file() -> Path:
    return Path(RECEIPT_STORAGE_ROOT) / ".pending_deletions"


def remove_files(storage_keys: list[str | None]) -> list[str]:
    """Delete files after the database commit. Failures are logged and recorded.

    A key that cannot be removed is appended to ``.pending_deletions`` under the
    storage root; ``retry_pending_deletions`` (run by the purge job) tries again,
    so a file cannot outlive its row unnoticed (FR-42). Returns the failed keys.
    """
    failed = [key for key in storage_keys if key and not _delete_bytes(key)]
    if failed:
        log.error("receipt files not deleted: %d (queued for retry)", len(failed))
        try:
            with _pending_file().open("a", encoding="utf-8") as handle:
                handle.writelines(f"{key}\n" for key in failed)
        except OSError:
            log.error("could not record pending receipt deletions")
    return failed


def retry_pending_deletions() -> int:
    """Retry keys recorded by ``remove_files``. Returns how many are still pending."""
    path = _pending_file()
    try:
        keys = [
            line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
    except OSError:
        return 0
    still = [key for key in dict.fromkeys(keys) if not _delete_bytes(key)]
    try:
        if still:
            path.write_text("".join(f"{key}\n" for key in still), encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
    except OSError:
        pass
    return len(still)


def _require_paid(user: User) -> None:
    from app.services.subscription import is_paid_active

    if not is_paid_active(user):
        raise ApiError(403, "PAID_SUBSCRIPTION_REQUIRED", _PAID_MESSAGE)


def _require_consent(user: User) -> None:
    if user.ai_consent_at is None:
        raise ApiError(403, "AI_CONSENT_REQUIRED", _CONSENT_MESSAGE)


def _timeout_s() -> float:
    raw = os.environ.get("AI_TIMEOUT_S", "").strip()
    if not raw:
        return 30.0
    try:
        value = float(raw)
    except ValueError:
        return 30.0
    if value <= 0:
        return 30.0
    return value


def _prune_upload_hits(now: float) -> None:
    """Drop stamps, and keys, that are outside the rolling hour."""
    expired: list[str] = []
    for key, stamps in _upload_hits.items():
        fresh = [stamp for stamp in stamps if now - stamp < _UPLOAD_WINDOW_S]
        if fresh:
            _upload_hits[key] = fresh
        else:
            expired.append(key)
    for key in expired:
        del _upload_hits[key]


def _consume_upload_slot(user_id: str) -> None:
    """Allow 30 uploads per user per rolling hour, in this process only."""
    now = time.monotonic()
    with _rate_lock:
        _prune_upload_hits(now)
        hits = _upload_hits.get(user_id, [])
        if len(hits) >= _UPLOAD_LIMIT:
            raise ApiError(429, "RATE_LIMITED", _RATE_MESSAGE)
        hits.append(now)
        _upload_hits[user_id] = hits


def _agreed_mime(raw: bytes, content_type: str | None) -> str | None:
    media = (content_type or "").split(";", 1)[0].strip().lower()
    if raw.startswith(_JPEG_MAGIC) and media == "image/jpeg":
        return "image/jpeg"
    if raw.startswith(_PNG_MAGIC) and media == "image/png":
        return "image/png"
    return None


def _reencode(raw: bytes, mime: str) -> bytes:
    """Decode, drop metadata, and encode again in the same format (FR-06)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(raw)) as image:
                # Check the header size before decoding, instead of changing
                # Pillow's process-wide MAX_IMAGE_PIXELS.
                width, height = image.size
                if width * height > _MAX_IMAGE_PIXELS:
                    raise ValueError("image exceeds the pixel limit")
                image.load()
                clean = _without_metadata(image, mime)
                buffer = io.BytesIO()
                if mime == "image/jpeg":
                    clean.save(buffer, format="JPEG", quality=90)
                else:
                    clean.save(buffer, format="PNG")
                encoded = buffer.getvalue()
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            UnidentifiedImageError,
            OSError,
            ValueError,
            SyntaxError,
        ):
            raise ApiError(422, "IMAGE_TYPE_NOT_SUPPORTED", _TYPE_MESSAGE) from None
    if mime == "image/jpeg" and not encoded.startswith(_JPEG_MAGIC):
        raise ApiError(422, "IMAGE_TYPE_NOT_SUPPORTED", _TYPE_MESSAGE)
    if mime == "image/png" and not encoded.startswith(_PNG_MAGIC):
        raise ApiError(422, "IMAGE_TYPE_NOT_SUPPORTED", _TYPE_MESSAGE)
    return encoded


def _without_metadata(image: Image.Image, mime: str) -> Image.Image:
    """Apply EXIF orientation, then copy pixels so EXIF, XMP, and GPS are dropped."""
    working = ImageOps.exif_transpose(image)
    if mime == "image/jpeg" and working.mode not in ("L", "RGB", "CMYK"):
        working = working.convert("RGB")
    elif mime == "image/png" and working.mode not in ("1", "L", "LA", "RGB", "RGBA"):
        working = working.convert("RGBA" if "A" in working.getbands() else "RGB")
    return Image.frombytes(working.mode, working.size, working.tobytes())


def _empty_columns() -> dict[str, Any]:
    return {
        "amount_idr": None,
        "tx_date": None,
        "client_name": None,
        "invoice_no": None,
    }


def _public_candidates(columns: dict[str, Any]) -> dict[str, Any]:
    tx_date = columns["tx_date"]
    return {
        "amount_idr": columns["amount_idr"],
        "tx_date": tx_date.isoformat() if isinstance(tx_date, date) else None,
        "client_name": columns["client_name"],
        "invoice_no": columns["invoice_no"],
    }


def _extract_candidates(encoded: bytes, mime: str) -> dict[str, Any]:
    """Read candidate fields. Any model or parse failure yields nulls (FR-06a)."""
    try:
        client = get_ocr_client()
        payload = client.complete(_ocr_messages(encoded, mime), response_schema=OCR_RESPONSE_SCHEMA)
        return _parse_candidates(payload)
    except Exception:
        return _empty_columns()


def _ocr_messages(encoded: bytes, mime: str) -> list[dict[str, Any]]:
    token = base64.b64encode(encoded).decode("ascii")
    return [
        {
            "role": "system",
            "content": (
                "Extract fields from one receipt image. "
                "Return JSON with amount_idr, tx_date, client_name, and invoice_no. "
                "Use null when a field is not readable. Do not calculate tax."
            ),
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Extract the receipt fields."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{token}"}},
            ],
        },
    ]


def _parse_candidates(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            return _empty_columns()
    if not isinstance(payload, dict):
        return _empty_columns()
    columns = _empty_columns()
    columns["amount_idr"] = _amount_or_none(payload.get("amount_idr"))
    columns["tx_date"] = _date_or_none(payload.get("tx_date"))
    columns["client_name"] = _text_or_none(payload.get("client_name"), 255)
    columns["invoice_no"] = _text_or_none(payload.get("invoice_no"), 64)
    return columns


def _amount_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < -_BIGINT_MAX or value > _BIGINT_MAX:
        return None
    return value


def _date_or_none(value: Any) -> date | None:
    if not isinstance(value, str) or _DATE_TEXT.fullmatch(value) is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _text_or_none(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > limit:
        return None
    return text


def _owned_image(db: Session, user_id: str, image_id: str) -> ReceiptImage:
    image = db.scalar(
        select(ReceiptImage).where(ReceiptImage.id == image_id, ReceiptImage.user_id == user_id)
    )
    if image is None:
        raise ApiError(404, "TRANSACTION_NOT_FOUND", _NOT_FOUND)
    return image


def _purge_expired_unconfirmed(db: Session, user_id: str, now: datetime) -> bool:
    """Drop this user's expired images that no transaction references (FR-06).

    Bytes are deleted before the row. A referenced image is kept, including
    one whose ``expires_at_utc`` was left unchanged at confirm time.
    """
    referenced = (
        select(TransactionRow.id).where(TransactionRow.image_id == ReceiptImage.id).exists()
    )
    rows = db.scalars(
        select(ReceiptImage).where(
            ReceiptImage.user_id == user_id,
            ReceiptImage.expires_at_utc < now,
            ~referenced,
        )
    ).all()
    removed = False
    for row in rows:
        if not _delete_bytes(row.storage_key):
            continue
        db.delete(row)
        removed = True
    return removed


def _path_for_key(storage_key: str) -> Path | None:
    """Resolve a relative key and reject anything outside the storage root."""
    if (
        not storage_key
        or "\\" in storage_key
        or "\x00" in storage_key
        or storage_key.startswith(("/", "\\"))
    ):
        return None
    relative = Path(storage_key)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        return None
    root = Path(RECEIPT_STORAGE_ROOT).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        return None
    return path


def _write_bytes(storage_key: str, data: bytes) -> None:
    path = _path_for_key(storage_key)
    if path is None:
        raise RuntimeError("receipt storage key is outside the storage root")
    root = Path(RECEIPT_STORAGE_ROOT).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.parent.resolve().is_relative_to(root):
        raise RuntimeError("receipt storage key is outside the storage root")
    temporary = path.with_name(f".{path.name}.partial")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _delete_bytes(storage_key: str) -> bool:
    """Delete a stored file. True when no in-root file remains."""
    path = _path_for_key(storage_key)
    if path is None:
        return True
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True
