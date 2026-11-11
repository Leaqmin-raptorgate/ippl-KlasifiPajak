"""Fixes from the 2026-11-10 review of the offline AI/OCR PR (R17-*)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_offline_features import (
    API,
    _jpeg_with_gps,
    _profile,
    _register_login,
    _set_ai_consent,
    _set_paid,
    _transaction,
)

from app.db import SessionLocal
from app.models import MonthSnapshot, ReceiptImage
from app.security import new_id


def _confirm_body(image_id: str, **overrides) -> dict:
    body = {
        "image_id": image_id,
        "confirmed_amount_idr": 54321,
        "confirmed_tx_date": "2026-10-16",
        "confirmed_client_name": "PT Nilai Pengguna",
        "confirmed_description": "Nilai yang dikonfirmasi pengguna",
        "confirmed_invoice_no": None,
        "withheld_tax_amount_idr": 0,
        "source_channel": "corporate_client",
    }
    body.update(overrides)
    return body


def _upload_receipt(client: TestClient, monkeypatch, tmp_path: Path, tag: str) -> str:
    from app.classify.model_client import FakeModelClient
    from app.services import receipts

    monkeypatch.setattr(receipts, "RECEIPT_STORAGE_ROOT", tmp_path, raising=False)
    fake = FakeModelClient(
        [{"amount_idr": 1, "tx_date": "2026-10-15", "client_name": "X", "invoice_no": None}]
    )
    monkeypatch.setattr(receipts, "get_ocr_client", lambda: fake)
    user_id = _register_login(client, email=f"{tag}@example.test", username=tag)
    _profile(client)
    _set_paid(user_id)
    _set_ai_consent(client)
    uploaded = client.post(
        f"{API}/transactions/ocr-upload", files={"file": ("r.jpg", _jpeg_with_gps(), "image/jpeg")}
    )
    assert uploaded.status_code == 200, uploaded.text
    return uploaded.json()["image_id"]


def test_r17_w1_assistant_reads_only_current_snapshot_versions(client):
    """Superseded (usang) versions must not crowd out or contradict the current month."""
    from app.services import assistant

    user_id = _register_login(client, email="r17w1@example.test", username="r17w1")
    _profile(client)
    _transaction(client, tx_date="2026-01-10")
    _transaction(client, tx_date="2026-03-10", invoice_no="OFFLINE-002")
    with SessionLocal() as db:
        rows = db.scalars(select(MonthSnapshot).where(MonthSnapshot.month_key == "2026-01")).all()
        base = next(row for row in rows if row.status == "berlaku")
        top = max(int(row.version) for row in rows)
        columns = {c.name: getattr(base, c.name) for c in MonthSnapshot.__table__.columns}
        for i in range(50):
            columns.update(id=new_id("snap_"), status="usang", version=top + 1 + i)
            db.add(MonthSnapshot(**columns))
        db.commit()
        tools = assistant._bind_tools(db, user_id)
        for name in ("baca_cuplikan", "baca_status_ambang"):
            months = [row["month_key"] for row in tools[name]()]
            assert months.count("2026-01") == 1, name
            assert "2026-03" in months, name


def test_r17_w2_a_second_confirm_of_one_receipt_makes_no_second_transaction(
    client, tmp_path, monkeypatch
):
    image_id = _upload_receipt(client, monkeypatch, tmp_path, "r17w2")
    first = client.post(f"{API}/transactions/ocr-confirm", json=_confirm_body(image_id))
    second = client.post(f"{API}/transactions/ocr-confirm", json=_confirm_body(image_id))
    assert first.status_code == 201, first.text
    assert second.status_code == 409
    items = client.get(f"{API}/transactions?per_page=100").json()["items"]
    assert len(items) == 1


def test_r17_w3_confirmed_receipt_without_a_rule_match_schedules_the_fallback(
    client, tmp_path, monkeypatch
):
    from app.services import classification_fallback

    calls: list[tuple] = []
    monkeypatch.setattr(classification_fallback, "run_fallback", lambda *a: calls.append(a))
    image_id = _upload_receipt(client, monkeypatch, tmp_path, "r17w3")
    response = client.post(
        f"{API}/transactions/ocr-confirm",
        json=_confirm_body(image_id, confirmed_description="zzz tidak dikenal"),
    )
    assert response.status_code == 201, response.text
    assert len(calls) == 1


def test_r17_w4_own_client_name_and_invoice_are_replaced_in_the_description():
    from app.services.classification_fallback import _scrub_own_identifiers

    text = _scrub_own_identifiers(
        "Jasa desain logo untuk budi santoso, faktur INV-77", "Budi Santoso", "INV-77"
    )
    assert "santoso" not in text.lower()
    assert "INV-77" not in text
    assert "[KLIEN]" in text and "[INVOICE]" in text
    # Under three characters is left alone.
    assert _scrub_own_identifiers("PT AB", "AB", None) == "PT AB"


def test_r17_w5_file_survives_a_rolled_back_delete_and_failures_are_recorded(
    client, tmp_path, monkeypatch
):
    from app.models import Transaction
    from app.services import receipts

    image_id = _upload_receipt(client, monkeypatch, tmp_path, "r17w5")
    created = client.post(f"{API}/transactions/ocr-confirm", json=_confirm_body(image_id))
    transaction_id = created.json()["transaction"]["id"]
    with SessionLocal() as db:
        key = db.get(ReceiptImage, image_id).storage_key
        row = db.get(Transaction, transaction_id)
        assert receipts.delete_receipt_for_transaction(db, row) == key
        db.rollback()  # e.g. the snapshot rebuild raised a 409
    assert (tmp_path / key).exists()

    monkeypatch.setattr(receipts, "_delete_bytes", lambda _key: False)
    assert receipts.remove_files([key]) == [key]
    assert key in (tmp_path / ".pending_deletions").read_text()
    monkeypatch.undo()
    monkeypatch.setattr(receipts, "RECEIPT_STORAGE_ROOT", tmp_path, raising=False)
    assert receipts.retry_pending_deletions() == 0
    assert not (tmp_path / key).exists()


def test_r17_w6_oversized_upload_is_413_before_auth(client):
    big = b"x" * (10 * 1024 * 1024)
    response = client.post(
        f"{API}/transactions/ocr-upload", files={"file": ("r.jpg", big, "image/jpeg")}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.parametrize("question", ["", "   ", "x" * 1001])
def test_r17_w7_bad_question_is_422(client, question):
    _register_login(client, email="r17w7@example.test", username="r17w7")
    response = client.post(f"{API}/assistant/query", json={"question": question})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_r17_w8_workpaper_reports_over_withholding(client):
    _register_login(client, email="r17w8@example.test", username="r17w8")
    _profile(client)
    # Rp100 juta is above the Rp500 juta band: 0,5% is Rp500.000. Withheld Rp800.000 leaves Rp300.000.
    _transaction(client, amount_idr=600_000_000, withheld_tax_amount_idr=800_000)
    body = client.get(f"{API}/recap/2026").json()
    assert body["total_overwithheld_excess_idr"] == 300_000
    assert body["overwithheld_note"]
    october = next(m for m in body["months"] if m["month"] == 10)
    assert october["overwithheld_excess_idr"] == 300_000
    assert october["sisa_bayar_idr"] == 0


def test_r17_n3_scrub_replaces_whole_tokens_of_four_or_more_characters():
    from app.services.assistant import _scrub_literals

    assert _scrub_literals("Budi Santoso dan Budi Santosoputra", ["Budi Santoso"]) == (
        "[REDACTED] dan Budi Santosoputra"
    )
    assert _literal_len_ok("web") is False and _literal_len_ok("webs") is True


def _literal_len_ok(text: str) -> bool:
    from app.services.assistant import _literal

    return bool(_literal(text))
