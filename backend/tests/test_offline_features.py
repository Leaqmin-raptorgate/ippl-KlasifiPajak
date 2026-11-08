"""Offline security and workpaper checks for FR-06, FR-31, FR-41, FR-27 (TC-OFFLINE-*)."""

from __future__ import annotations

import io
import logging
from datetime import timedelta
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select

from app.db import SessionLocal
from app.models import MonthSnapshot, PasswordResetToken, QuotaCounter, User
from app.security import hash_reset_token, now_utc
from app.services.snapshot import DISCLAIMER

API = "/api/v1"
PASSWORD = "PasswordMinimal10"


def _register_login(client: TestClient, *, email: str, username: str) -> str:
    """Create a test account, log in, and return the session user's id."""
    response = client.post(
        f"{API}/auth/register",
        json={"email": email, "username": username, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    response = client.post(f"{API}/auth/login", json={"identifier": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client.get(f"{API}/auth/me").json()["user_id"]


def _profile(client: TestClient) -> dict:
    """Create a profile with explicit zero prior-year amounts (FR-03)."""
    response = client.put(
        f"{API}/profiles/2026",
        json={
            "version": 1,
            "name": "Toko Contoh Offline",
            "entity_type": "orang_pribadi",
            "nib_status": "no_nib",
            "nib_last_4": None,
            "kbli_code": "47111",
            "business_description": "Penjualan barang",
            "marital_status": "no",
            "spouse_tax_status": "unmarried",
            "spouse_aggregation_active": False,
            "is_new_taxpayer_current_year": True,
            "prior_user_usaha_idr": 0,
            "prior_user_pekerjaan_bebas_idr": 0,
            "prior_user_already_final_idr": 0,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _transaction(client: TestClient, **overrides) -> dict:
    """Create a synthetic ledger row through the public transaction path."""
    payload = {
        "amount_idr": 1_000_000,
        "tx_date": "2026-10-15",
        "client_name": "PT Contoh Offline",
        "description": "Penjualan barang dagangan",
        "invoice_no": "OFFLINE-001",
        "withheld_tax_amount_idr": 0,
        "source_channel": "corporate_client",
    }
    payload.update(overrides)
    response = client.post(f"{API}/transactions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _set_paid(user_id: str, paid: bool = True) -> None:
    """Set an account's local entitlement without using a test-support route."""
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.id == user_id))
        assert user is not None
        user.paid_flag = paid
        user.valid_until_utc = now_utc() + timedelta(days=30) if paid else None
        db.commit()
    finally:
        db.close()


def _set_ai_consent(client: TestClient, consent: bool = True) -> None:
    """Record the account's explicit AI/OCR data-processing choice."""
    response = client.put(f"{API}/ai-consent", json={"consent": consent})
    assert response.status_code == 200, response.text


def _jpeg_with_gps() -> bytes:
    """Build a tiny synthetic JPEG whose EXIF GPS IFD is present before upload."""
    image = Image.new("RGB", (3, 3), color=(30, 90, 140))
    exif = Image.Exif()
    exif[34853] = {
        1: "N",
        2: (Fraction(6), Fraction(12), Fraction(0)),
        3: "E",
        4: (Fraction(106), Fraction(48), Fraction(0)),
    }
    output = io.BytesIO()
    image.save(output, format="JPEG", exif=exif)
    original = Image.open(io.BytesIO(output.getvalue())).getexif()
    assert original.get_ifd(34853)
    return output.getvalue()


def _quota_chat_used(user_id: str) -> int:
    """Read the persisted assistant success counter for the current month."""
    db = SessionLocal()
    try:
        row = db.scalar(select(QuotaCounter).where(QuotaCounter.user_id == user_id))
        assert row is not None
        return row.assistant_chat_used
    finally:
        db.close()


def test_tc_pdf_requires_paid_entitlement_and_renders_locked_disclaimer(
    client, tmp_path, monkeypatch
):
    """TC-OFFLINE-PDF, FR-31/FR-36: PDF is paid-only, Unicode-safe, and ephemeral."""
    from app.services import recap

    monkeypatch.setattr(recap, "PDF_OUTPUT_ROOT", tmp_path, raising=False)
    user_id = _register_login(client, email="offline-pdf@example.test", username="offlinepdf")
    _profile(client)
    _transaction(client)

    free = client.post(f"{API}/recap/2026/pdf")
    assert free.status_code == 403
    assert free.json()["error"]["code"] == "PAID_SUBSCRIPTION_REQUIRED"
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]

    _set_paid(user_id)
    dashboard = client.get(f"{API}/tax/dashboard?tax_year=2026")
    assert dashboard.status_code == 200, dashboard.text
    recap = client.get(f"{API}/recap/2026")
    assert recap.status_code == 200, recap.text
    response = client.post(f"{API}/recap/2026/pdf")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert 'filename="Workpaper_PPh_Final_2026.pdf"' in response.headers.get(
        "content-disposition", ""
    )
    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(response.content)).pages
    )
    assert DISCLAIMER == "DOKUMEN KERJA (WORKPAPER) — BUKAN SPT RESMI DAN BUKAN PRODUK DJP/CORETAX."
    assert DISCLAIMER in text
    assert "bukan spt" in text.lower()
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]

    dashboard_totals = dashboard.json()["thresholds"]["monitoring_current_year_cap_4_8m"]
    recap_totals = recap.json()
    assert recap_totals["total_usaha_omzet_idr"] == dashboard_totals["ytd_usaha_omzet_idr"]
    assert (
        recap_totals["total_pekerjaan_bebas_omzet_idr"]
        == dashboard_totals["ytd_pekerjaan_bebas_omzet_idr"]
    )


def test_tc_pdf_refuses_or_rebuilds_stale_snapshot_before_rendering(client):
    """TC-OFFLINE-PDF-STALE, FR-31: a stale snapshot is never emitted as current."""
    user_id = _register_login(client, email="offline-stale@example.test", username="offlinestale")
    profile = _profile(client)
    _transaction(client)
    _set_paid(user_id)
    db = SessionLocal()
    try:
        row = db.scalar(
            select(MonthSnapshot)
            .where(MonthSnapshot.profile_id == profile["id"])
            .order_by(MonthSnapshot.version.desc())
        )
        assert row is not None
        row.status = "usang"
        db.commit()
    finally:
        db.close()

    response = client.post(f"{API}/recap/2026/pdf")
    assert response.status_code in (200, 409)
    if response.status_code == 200:
        db = SessionLocal()
        try:
            latest = db.scalar(
                select(MonthSnapshot)
                .where(MonthSnapshot.profile_id == profile["id"])
                .order_by(MonthSnapshot.version.desc())
            )
            assert latest is not None and latest.status == "berlaku"
        finally:
            db.close()


@pytest.mark.parametrize(
    ("filename", "content", "expected_code"),
    [
        ("receipt.jpg", b"not-jpeg", "IMAGE_TYPE_NOT_SUPPORTED"),
        ("receipt.png", b"\x89PNG\r\n\x1a\n" + b"invalid", "IMAGE_TYPE_NOT_SUPPORTED"),
    ],
)
def test_tc_ocr_rejects_invalid_images_without_storage(
    client, tmp_path, monkeypatch, filename, content, expected_code
):
    """TC-OFFLINE-OCR-INPUT, FR-06: invalid formats do not leave files behind."""
    from app.services import receipts

    monkeypatch.setattr(receipts, "RECEIPT_STORAGE_ROOT", tmp_path, raising=False)
    user_id = _register_login(
        client, email=f"ocr-input-{filename}@example.test", username=f"ocr{filename[0]}"
    )
    _set_paid(user_id)
    _set_ai_consent(client)
    response = client.post(
        f"{API}/transactions/ocr-upload",
        files={
            "file": (filename, content, "image/jpeg" if filename.endswith("jpg") else "image/png")
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == expected_code
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_tc_ocr_paid_gate_consent_and_8mb_limit_leave_no_files(client, tmp_path, monkeypatch):
    """TC-OFFLINE-OCR-GATES, FR-06/NFR-16: entitlement, consent, and size gate first."""
    from app.services import receipts

    monkeypatch.setattr(receipts, "RECEIPT_STORAGE_ROOT", tmp_path, raising=False)
    user_id = _register_login(client, email="ocr-gates@example.test", username="ocrgates")
    image = _jpeg_with_gps()

    free = client.post(
        f"{API}/transactions/ocr-upload", files={"file": ("x.jpg", image, "image/jpeg")}
    )
    assert free.status_code == 403
    assert free.json()["error"]["code"] == "PAID_SUBSCRIPTION_REQUIRED"
    _set_paid(user_id)
    unconsented = client.post(
        f"{API}/transactions/ocr-upload", files={"file": ("x.jpg", image, "image/jpeg")}
    )
    assert unconsented.status_code == 403
    assert unconsented.json()["error"]["code"] == "AI_CONSENT_REQUIRED"
    _set_ai_consent(client)

    oversize = client.post(
        f"{API}/transactions/ocr-upload",
        files={"file": ("x.jpg", b"\xff\xd8\xff" + b"x" * (8 * 1024 * 1024), "image/jpeg")},
    )
    assert oversize.status_code == 422
    assert oversize.json()["error"]["code"] == "IMAGE_EXCEEDS_SIZE_LIMIT"
    assert list(tmp_path.rglob("*")) == []


def test_tc_ocr_strips_gps_owner_get_is_private_and_confirm_uses_user_values(
    client, tmp_path, monkeypatch
):
    """TC-OFFLINE-OCR-PRIVACY, FR-06a/FR-06b: strip metadata and require confirmation."""
    from app.classify.model_client import FakeModelClient
    from app.services import receipts

    monkeypatch.setattr(receipts, "RECEIPT_STORAGE_ROOT", tmp_path, raising=False)
    fake = FakeModelClient(
        [
            {
                "amount_idr": 12345,
                "tx_date": "2026-10-15",
                "client_name": "Toko Kandidat",
                "invoice_no": "OCR-1",
            }
        ]
    )
    monkeypatch.setattr(receipts, "get_ocr_client", lambda: fake)
    user_id = _register_login(client, email="ocr-privacy@example.test", username="ocrprivacy")
    _profile(client)
    _set_paid(user_id)
    _set_ai_consent(client)
    original = _jpeg_with_gps()
    uploaded = client.post(
        f"{API}/transactions/ocr-upload", files={"file": ("receipt.jpg", original, "image/jpeg")}
    )
    assert uploaded.status_code == 200, uploaded.text
    data = uploaded.json()
    assert set(data) == {"image_id", "candidate_fields"}
    assert data["candidate_fields"]["amount_idr"] == 12345
    image_id = data["image_id"]
    image = client.get(f"{API}/transactions/receipt-images/{image_id}")
    assert image.status_code == 200
    assert image.headers["cache-control"] == "private, no-store"
    processed = Image.open(io.BytesIO(image.content))
    assert processed.format == "JPEG"
    assert processed.getexif().get(34853) is None

    other = TestClient(client.app)
    _register_login(other, email="ocr-other@example.test", username="ocrother")
    denied = other.get(f"{API}/transactions/receipt-images/{image_id}")
    assert denied.status_code == 404

    confirmed = client.post(
        f"{API}/transactions/ocr-confirm",
        json={
            "image_id": image_id,
            "confirmed_amount_idr": 54321,
            "confirmed_tx_date": "2026-10-16",
            "confirmed_client_name": "PT Nilai Pengguna",
            "confirmed_description": "Nilai yang dikonfirmasi pengguna",
            "confirmed_invoice_no": "USER-OK-1",
            "withheld_tax_amount_idr": 0,
            "source_channel": "corporate_client",
        },
    )
    assert confirmed.status_code == 201, confirmed.text
    transaction = confirmed.json().get("transaction", confirmed.json())
    assert transaction["amount_idr"] == 54321
    assert transaction["tx_date"] == "2026-10-16"
    assert transaction["client_name"] == "PT Nilai Pengguna"
    assert transaction["invoice_no"] == "USER-OK-1"

    reconfirm = client.post(
        f"{API}/transactions/ocr-confirm",
        json={
            "image_id": image_id,
            "confirmed_amount_idr": 54321,
            "confirmed_tx_date": "2026-10-16",
            "confirmed_client_name": "PT Nilai Pengguna",
            "confirmed_description": "Nilai yang dikonfirmasi pengguna",
            "confirmed_invoice_no": "USER-OK-1",
            "withheld_tax_amount_idr": 0,
            "source_channel": "corporate_client",
        },
    )
    assert reconfirm.status_code == 409
    assert reconfirm.json()["error"]["code"] == "RECEIPT_ALREADY_CONFIRMED"


def test_tc_ocr_second_confirm_of_one_receipt_conflicts_and_delete_removes_it(
    client, tmp_path, monkeypatch
):
    """One receipt confirms once. A second confirm is 409 and creates no row."""
    from app.classify.model_client import FakeModelClient
    from app.models import ReceiptImage
    from app.models import Transaction as TransactionRow
    from app.services import receipts

    monkeypatch.setattr(receipts, "RECEIPT_STORAGE_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(
        receipts,
        "get_ocr_client",
        lambda: FakeModelClient(
            [
                {
                    "amount_idr": None,
                    "tx_date": None,
                    "client_name": None,
                    "invoice_no": None,
                }
            ]
        ),
    )
    user_id = _register_login(client, email="ocr-once@example.test", username="ocronce")
    _profile(client)
    _set_paid(user_id)
    _set_ai_consent(client)
    uploaded = client.post(
        f"{API}/transactions/ocr-upload",
        files={"file": ("receipt.jpg", _jpeg_with_gps(), "image/jpeg")},
    )
    assert uploaded.status_code == 200, uploaded.text
    image_id = uploaded.json()["image_id"]
    # A different invoice so the rejection is the receipt, not the duplicate-invoice rule.
    first_body = {
        "image_id": image_id,
        "confirmed_amount_idr": 54321,
        "confirmed_tx_date": "2026-10-16",
        "confirmed_client_name": "PT Nilai Pengguna",
        "confirmed_description": "Nilai yang dikonfirmasi pengguna",
        "confirmed_invoice_no": "USER-ONCE-1",
        "withheld_tax_amount_idr": 0,
        "source_channel": "corporate_client",
    }
    confirmed = client.post(f"{API}/transactions/ocr-confirm", json=first_body)
    assert confirmed.status_code == 201, confirmed.text
    transaction = confirmed.json().get("transaction", confirmed.json())
    assert transaction["amount_idr"] == 54321
    assert transaction["tx_date"] == "2026-10-16"
    assert transaction["client_name"] == "PT Nilai Pengguna"
    assert transaction["invoice_no"] == "USER-ONCE-1"
    assert client.get(f"{API}/transactions/receipt-images/{image_id}").status_code == 200

    db = SessionLocal()
    try:
        count = len(
            db.scalars(select(TransactionRow).where(TransactionRow.user_id == user_id)).all()
        )
    finally:
        db.close()
    assert count == 1

    again = client.post(
        f"{API}/transactions/ocr-confirm",
        json={
            **first_body,
            "confirmed_amount_idr": 1000,
            "confirmed_invoice_no": "USER-ONCE-2",
        },
    )
    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "RECEIPT_ALREADY_CONFIRMED"

    db = SessionLocal()
    try:
        rows = db.scalars(select(TransactionRow).where(TransactionRow.user_id == user_id)).all()
        assert len(rows) == count
        assert db.get(ReceiptImage, image_id) is not None
    finally:
        db.close()

    deleted = client.delete(f"{API}/transactions/{transaction['id']}")
    assert deleted.status_code == 200, deleted.text
    db = SessionLocal()
    try:
        assert db.get(ReceiptImage, image_id) is None
        assert db.get(TransactionRow, transaction["id"]) is None
    finally:
        db.close()
    assert client.get(f"{API}/transactions/receipt-images/{image_id}").status_code == 404
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_tc_ocr_confirm_race_past_invoice_precheck_is_duplicate_invoice(
    client, tmp_path, monkeypatch
):
    """A lost invoice race is the invoice conflict, not a receipt conflict.

    The duplicate pre-check is forced to miss, so the second receipt hits the
    ``duplicate_key`` unique index. That must stay ``DUPLICATE_INVOICE_TRANSACTION``.
    """
    from app.classify.model_client import FakeModelClient
    from app.models import Transaction as TransactionRow
    from app.services import receipts
    from app.services import transactions as tx_services

    monkeypatch.setattr(receipts, "RECEIPT_STORAGE_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(
        receipts,
        "get_ocr_client",
        lambda: FakeModelClient(
            [
                {
                    "amount_idr": None,
                    "tx_date": None,
                    "client_name": None,
                    "invoice_no": None,
                },
                {
                    "amount_idr": None,
                    "tx_date": None,
                    "client_name": None,
                    "invoice_no": None,
                },
            ]
        ),
    )
    user_id = _register_login(client, email="ocr-race@example.test", username="ocrrace")
    _profile(client)
    _set_paid(user_id)
    _set_ai_consent(client)

    def _upload() -> str:
        uploaded = client.post(
            f"{API}/transactions/ocr-upload",
            files={"file": ("receipt.jpg", _jpeg_with_gps(), "image/jpeg")},
        )
        assert uploaded.status_code == 200, uploaded.text
        return uploaded.json()["image_id"]

    first_image = _upload()
    second_image = _upload()
    assert first_image != second_image
    body = {
        "confirmed_amount_idr": 54321,
        "confirmed_tx_date": "2026-10-16",
        "confirmed_client_name": "PT Nilai Pengguna",
        "confirmed_description": "Nilai yang dikonfirmasi pengguna",
        "confirmed_invoice_no": "USER-RACE-1",
        "withheld_tax_amount_idr": 0,
        "source_channel": "corporate_client",
    }
    first = client.post(
        f"{API}/transactions/ocr-confirm",
        json={**body, "image_id": first_image},
    )
    assert first.status_code == 201, first.text

    calls = {"n": 0}

    def _miss_precheck(*_args, **_kwargs):
        calls["n"] += 1
        return None

    monkeypatch.setattr(tx_services, "find_duplicate_invoice_id", _miss_precheck)
    again = client.post(
        f"{API}/transactions/ocr-confirm",
        json={**body, "image_id": second_image},
    )
    assert calls["n"] >= 1
    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "DUPLICATE_INVOICE_TRANSACTION"
    assert again.json()["error"]["code"] != "RECEIPT_ALREADY_CONFIRMED"

    db = SessionLocal()
    try:
        rows = db.scalars(select(TransactionRow).where(TransactionRow.user_id == user_id)).all()
        assert len(rows) == 1
        assert rows[0].image_id == first_image
    finally:
        db.close()


def test_tc_assistant_consent_and_success_quota_are_fail_closed(client, monkeypatch):
    """TC-OFFLINE-ASSISTANT, FR-27/FR-28: consent and safe fallback consume no quota."""
    from app.classify.model_client import FakeModelClient, ModelUnavailable
    from app.services import assistant

    user_id = _register_login(
        client, email="assistant-offline@example.test", username="assistantoffline"
    )
    _profile(client)
    _transaction(client)
    fake = FakeModelClient(["Sisa pajak Anda adalah Rp 999.999.999.", ModelUnavailable("offline")])
    monkeypatch.setattr(assistant, "get_model_client", lambda: fake)

    no_consent = client.post(f"{API}/assistant/query", json={"question": "Jelaskan ringkasan saya"})
    assert no_consent.status_code == 403
    assert no_consent.json()["error"]["code"] == "AI_CONSENT_REQUIRED"
    res1 = client.put(f"{API}/ai-consent", json={"consent": True})
    assert res1.status_code == 200
    first_stamp = res1.json()["ai_consent_at"]
    assert first_stamp is not None
    res2 = client.put(f"{API}/ai-consent", json={"consent": True})
    assert res2.status_code == 200
    assert res2.json()["ai_consent_at"] == first_stamp
    initial = client.get(f"{API}/quotas").json()["assistant_chat"]["used"]

    invented = client.post(f"{API}/assistant/query", json={"question": "Berapa pajak saya?"})
    assert invented.status_code == 200, invented.text
    assert "999.999.999" not in invented.json()["answer"]
    assert _quota_chat_used(user_id) == initial

    failed = client.post(f"{API}/assistant/query", json={"question": "Berapa sisa bulan ini?"})
    assert failed.status_code == 200, failed.text
    assert _quota_chat_used(user_id) == initial
    assert len(fake.calls) == 2


def test_tc_assistant_quota_exhaustion_skips_model_call(client, monkeypatch):
    """TC-OFFLINE-ASSISTANT-QUOTA, FR-27: exhausted free quota never calls the model."""
    from app.classify.model_client import FakeModelClient
    from app.services import assistant

    user_id = _register_login(
        client, email="assistant-quota@example.test", username="assistantquota"
    )
    _profile(client)
    _set_ai_consent(client)
    fake = FakeModelClient(["This response must not be used."])
    monkeypatch.setattr(assistant, "get_model_client", lambda: fake)
    client.get(f"{API}/quotas")
    db = SessionLocal()
    try:
        counter = db.scalar(select(QuotaCounter).where(QuotaCounter.user_id == user_id))
        assert counter is not None
        counter.assistant_chat_used = 15
        db.commit()
    finally:
        db.close()

    response = client.post(f"{API}/assistant/query", json={"question": "Jelaskan data saya"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "FREE_CHAT_QUOTA_EXHAUSTED"
    assert fake.calls == []


def test_tc_email_reset_sends_plaintext_only_to_sender_and_never_logs_it(
    client, caplog, monkeypatch
):
    """TC-OFFLINE-EMAIL, FR-41: reset token reaches the sender, never logs or storage."""
    from app.services import auth

    user_id = _register_login(client, email="reset-offline@example.test", username="resetoffline")

    class Sender:
        def __init__(self):
            self.deliveries: list[tuple[str, str]] = []

        def send_password_reset(self, recipient: str, token: str) -> None:
            self.deliveries.append((recipient, token))

    sender = Sender()
    monkeypatch.setattr(auth, "get_email_sender", lambda: sender)
    caplog.set_level(logging.INFO)
    response = client.post(
        f"{API}/auth/password-reset/request", json={"email": "reset-offline@example.test"}
    )
    assert response.status_code == 200
    assert sender.deliveries and sender.deliveries[0][0] == "reset-offline@example.test"
    plaintext = sender.deliveries[0][1]
    assert plaintext not in response.text
    assert plaintext not in caplog.text

    db = SessionLocal()
    try:
        row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
        assert row is not None
        assert row.token_hash == hash_reset_token(plaintext)
        assert row.token_hash != plaintext
    finally:
        db.close()
