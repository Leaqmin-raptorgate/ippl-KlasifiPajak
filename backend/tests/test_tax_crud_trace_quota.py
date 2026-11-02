"""M50 Tax lane tests with catalog TC ids (asserted, not docstring-only)."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import ClassificationEvent, MonthSnapshot, Profile, QuotaCounter, User
from app.security import now_utc
from app.services.snapshot import DISCLAIMER
from app.services.snapshots_store import freeze_today_jakarta, today_jakarta

AUTH = {
    "email": "taxlane@example.com",
    "username": "taxlaneuser",
    "password": "PasswordMinimal10",
}

EXACT_DISCLAIMER = "DOKUMEN KERJA (WORKPAPER) — BUKAN SPT RESMI DAN BUKAN PRODUK DJP/CORETAX."


def _register(client, **overrides):
    payload = dict(AUTH)
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload)


def _login(client, email=None, password=None):
    return client.post(
        "/api/v1/auth/login",
        json={
            "identifier": email or AUTH["email"],
            "password": password or AUTH["password"],
        },
    )


def _auth(client):
    assert _register(client).status_code == 201
    assert _login(client).status_code == 200


def _profile(client, **overrides):
    payload = {
        "version": 1,
        "name": "Toko Tax Lane",
        "entity_type": "orang_pribadi",
        "nib_status": "has_nib",
        "nib_last_4": "4321",
        "kbli_code": "47111",
        "business_description": "Penjualan sembako",
        "marital_status": "no",
        "spouse_aggregation_active": False,
        "is_new_taxpayer_current_year": True,
    }
    payload.update(overrides)
    return client.put("/api/v1/profiles/2026", json=payload)


def _tx(client, **overrides):
    payload = {
        "amount_idr": 12_500_000,
        "tx_date": "2026-10-15",
        "client_name": "PT Sumber Makmur",
        "description": "Penjualan sembako",
        "invoice_no": "INV-TAX-001",
        "withheld_tax_amount_idr": 0,
        "source_channel": "corporate_client",
    }
    payload.update(overrides)
    return client.post("/api/v1/transactions", json=payload)


def _assert_one_berlaku_contiguous(db, profile_id: str, month_key: str) -> int:
    rows = db.scalars(
        select(MonthSnapshot)
        .where(
            MonthSnapshot.profile_id == profile_id,
            MonthSnapshot.month_key == month_key,
        )
        .order_by(MonthSnapshot.version)
    ).all()
    assert rows, f"expected snapshots for {month_key}"
    berlaku = [r for r in rows if r.status == "berlaku"]
    assert len(berlaku) == 1, [(r.version, r.status) for r in rows]
    versions = [r.version for r in rows]
    assert versions == list(range(1, len(rows) + 1)), versions
    assert berlaku[0].version == versions[-1]
    return berlaku[0].version


def test_tc_4_3_41_edit_amount_rebuilds_and_bumps_version(client):
    """TC-4.3-41 FR-08 — edit amount; dashboard changes; prior month row usang."""
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()
    assert body["version"] == 1

    edited = client.put(
        f"/api/v1/transactions/{body['id']}",
        json={
            "amount_idr": 20_000_000,
            "tx_date": "2026-10-15",
            "client_name": "PT Sumber Makmur",
            "description": "Penjualan sembako",
            "invoice_no": "INV-TAX-001",
            "withheld_tax_amount_idr": 0,
            "source_channel": "corporate_client",
            "version": 1,
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == 2
    assert edited.json()["amount_idr"] == 20_000_000

    dashboard = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
    assert dashboard["thresholds"]["pita_500_juta"]["ytd_usaha_omzet_idr"] == 20_000_000
    assert all(row["status"] == "berlaku" for row in dashboard["monthly_summaries"])

    me = client.get("/api/v1/auth/me").json()
    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        rows = db.scalars(
            select(MonthSnapshot)
            .where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-10",
            )
            .order_by(MonthSnapshot.version)
        ).all()
        assert any(r.status == "usang" for r in rows)
        assert rows[-1].status == "berlaku"
    finally:
        db.close()


def test_tc_4_3_42_put_moves_month_rebuilds_earlier_through_december(client):
    """TC-4.3-42 — move tx_date Oct→Mar rebuilds March through Jakarta as_of month.

    API §5.12 names "through December" as the ordered free-band band; API §2.4
    caps materialised months at today's Jakarta month for the current year.
    """
    with freeze_today_jakarta(date(2026, 11, 2)):
        _auth(client)
        assert _profile(client).status_code == 200
        body = _tx(client).json()
        me = client.get("/api/v1/auth/me").json()
        db = SessionLocal()
        try:
            profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
            before_march = _assert_one_berlaku_contiguous(db, profile.id, "2026-03")
        finally:
            db.close()

        moved = client.put(
            f"/api/v1/transactions/{body['id']}",
            json={
                "amount_idr": 12_500_000,
                "tx_date": "2026-03-10",
                "client_name": "PT Sumber Makmur",
                "description": "Penjualan sembako",
                "invoice_no": "INV-TAX-001",
                "withheld_tax_amount_idr": 0,
                "source_channel": "corporate_client",
                "version": 1,
            },
        )
        assert moved.status_code == 200, moved.text

        db = SessionLocal()
        try:
            profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
            after_march = _assert_one_berlaku_contiguous(db, profile.id, "2026-03")
            assert after_march > before_march
            # October and November (as_of month) stay single berlaku; December must
            # not exist while today is still November (§2.4).
            _assert_one_berlaku_contiguous(db, profile.id, "2026-10")
            _assert_one_berlaku_contiguous(db, profile.id, "2026-11")
            dec = db.scalars(
                select(MonthSnapshot).where(
                    MonthSnapshot.profile_id == profile.id,
                    MonthSnapshot.month_key == "2026-12",
                )
            ).all()
            assert dec == []
        finally:
            db.close()


def test_tc_4_3_43_put_stale_version_conflict(client):
    """TC-4.3-43 / API §5.12 — stale version → 409; no partial write."""
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()
    stale = client.put(
        f"/api/v1/transactions/{body['id']}",
        json={
            "amount_idr": 1_000_000,
            "tx_date": "2026-10-15",
            "client_name": "PT Sumber Makmur",
            "description": "Penjualan sembako",
            "invoice_no": "INV-TAX-001",
            "withheld_tax_amount_idr": 0,
            "source_channel": "corporate_client",
            "version": 99,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    got = client.get(f"/api/v1/transactions/{body['id']}").json()
    assert got["amount_idr"] == 12_500_000
    assert got["version"] == 1


def test_tc_4_3_44_put_other_account_is_404(client):
    """TC-4.3-44 — PUT another account's transaction → 404 TRANSACTION_NOT_FOUND."""
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()

    other = TestClient(client.app)
    assert (
        other.post(
            "/api/v1/auth/register",
            json={
                "email": "putidor@example.com",
                "username": "putidor",
                "password": "PasswordMinimal10",
            },
        ).status_code
        == 201
    )
    assert (
        other.post(
            "/api/v1/auth/login",
            json={"identifier": "putidor@example.com", "password": "PasswordMinimal10"},
        ).status_code
        == 200
    )
    resp = other.put(
        f"/api/v1/transactions/{body['id']}",
        json={
            "amount_idr": 1,
            "tx_date": "2026-10-15",
            "client_name": "X",
            "description": "Y",
            "invoice_no": "Z",
            "withheld_tax_amount_idr": 0,
            "source_channel": "other",
            "version": 1,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "TRANSACTION_NOT_FOUND"


def test_tc_4_3_45_description_only_keeps_classification(client):
    """TC-4.3-45 — description-only edit stores text; classification not re-run;
    snapshot version is not bumped (hash no-op / Argon finding 4)."""
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()
    assert body["category"] == "usaha"
    me = client.get("/api/v1/auth/me").json()
    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        before_version = _assert_one_berlaku_contiguous(db, profile.id, "2026-10")
        before_hash = db.scalar(
            select(MonthSnapshot.input_hash).where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-10",
                MonthSnapshot.status == "berlaku",
            )
        )
    finally:
        db.close()

    edited = client.put(
        f"/api/v1/transactions/{body['id']}",
        json={
            "amount_idr": body["amount_idr"],
            "tx_date": "2026-10-15",
            "client_name": body["client_name"],
            "description": "Penjualan sembako — catatan tambahan",
            "invoice_no": body["invoice_no"],
            "withheld_tax_amount_idr": 0,
            "source_channel": "corporate_client",
            "version": 1,
        },
    )
    assert edited.status_code == 200
    assert edited.json()["category"] == "usaha"
    assert edited.json()["source"] == "rule"
    assert "catatan tambahan" in edited.json()["description"]

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        after_version = _assert_one_berlaku_contiguous(db, profile.id, "2026-10")
        assert after_version == before_version
        after_hash = db.scalar(
            select(MonthSnapshot.input_hash).where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-10",
                MonthSnapshot.status == "berlaku",
            )
        )
        assert after_hash == before_hash
        # Create already left an usang sibling (seed v1 → create v2). Description-only
        # must not add another version / usang row.
        usang_versions = [
            r.version
            for r in db.scalars(
                select(MonthSnapshot).where(
                    MonthSnapshot.profile_id == profile.id,
                    MonthSnapshot.month_key == "2026-10",
                    MonthSnapshot.status == "usang",
                )
            ).all()
        ]
        assert max(usang_versions, default=0) < after_version
    finally:
        db.close()


def test_tc_4_3_46_rejects_non_positive_amount(client):
    """TC-4.3-46 — amount ≤ 0 rejected by validation."""
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()
    bad = client.put(
        f"/api/v1/transactions/{body['id']}",
        json={
            "amount_idr": 0,
            "tx_date": "2026-10-15",
            "client_name": "PT Sumber Makmur",
            "description": "Penjualan sembako",
            "invoice_no": "INV-TAX-001",
            "withheld_tax_amount_idr": 0,
            "source_channel": "corporate_client",
            "version": 1,
        },
    )
    assert bad.status_code == 422


def test_tc_4_3_47_failed_rebuild_after_edit_leaves_usang(client, monkeypatch):
    """TC-4.3-47 — mark_usang then fault mid-rebuild leaves cuplikan usang (FR-23a)."""
    from app.engine.ruleset import load_ruleset
    from app.services import snapshots_store
    from app.services.snapshots_store import mark_usang

    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    me = client.get("/api/v1/auth/me").json()

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        mark_usang(db, profile, ["2026-10"])
        db.commit()
    finally:
        db.close()

    def boom(*args, **kwargs):
        raise RuntimeError("injected engine fault")

    monkeypatch.setattr(snapshots_store, "compute", boom)

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        try:
            snapshots_store.rebuild(db, profile, load_ruleset(), only_usang=True)
            db.commit()
            raised = False
        except RuntimeError:
            db.rollback()
            raised = True
        assert raised
    finally:
        db.close()

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        assert (
            db.scalars(
                select(MonthSnapshot).where(
                    MonthSnapshot.profile_id == profile.id,
                    MonthSnapshot.month_key == "2026-10",
                    MonthSnapshot.status == "berlaku",
                )
            ).all()
            == []
        )
        assert db.scalars(
            select(MonthSnapshot).where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-10",
                MonthSnapshot.status == "usang",
            )
        ).all()
    finally:
        db.close()


def test_tc_4_3_48_delete_cascades_events_and_rebuilds(client):
    """TC-4.3-48 FR-09 — DELETE removes row + events; dashboard zeros."""
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()
    deleted = client.delete(f"/api/v1/transactions/{body['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": body["id"]}
    assert client.get(f"/api/v1/transactions/{body['id']}").status_code == 404
    trail = client.get(f"/api/v1/transactions/{body['id']}/audit-trail")
    assert trail.status_code == 404
    dashboard = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
    assert dashboard["thresholds"]["pita_500_juta"]["ytd_usaha_omzet_idr"] == 0


def test_tc_4_3_49_delete_other_account_is_404(client):
    """TC-4.3-49 — cannot delete another account's transaction."""
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()

    other = TestClient(client.app)
    assert (
        other.post(
            "/api/v1/auth/register",
            json={
                "email": "other@example.com",
                "username": "otheruser",
                "password": "PasswordMinimal10",
            },
        ).status_code
        == 201
    )
    assert (
        other.post(
            "/api/v1/auth/login",
            json={"identifier": "other@example.com", "password": "PasswordMinimal10"},
        ).status_code
        == 200
    )
    assert other.delete(f"/api/v1/transactions/{body['id']}").status_code == 404


def test_tc_4_3_50_delete_sole_month_tx_zeroes_snapshot(client):
    """TC-4.3-50 — deleting the only tx of a month leaves zero money fields."""
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()
    assert client.delete(f"/api/v1/transactions/{body['id']}").status_code == 200
    snap = client.get("/api/v1/tax/snapshots/2026/2026-10")
    assert snap.status_code == 200
    assert snap.json()["usaha_omzet_idr"] == 0
    assert snap.json()["status"] == "berlaku"


def test_tc_4_3_52_delete_without_session_is_401():
    """TC-4.3-52 — unauthenticated DELETE → 401."""
    from app.main import app

    bare = TestClient(app)
    resp = bare.delete("/api/v1/transactions/tx_does_not_exist")
    assert resp.status_code == 401


def test_api_5_17_clarification_version_conflict(client):
    """API §5.17 — clarification with mismatched version → 409 VERSION_CONFLICT."""
    _auth(client)
    assert _profile(client).status_code == 200
    created = _tx(
        client,
        description="qqqq zzzz xxxx",
        invoice_no="INV-CLAR-VER",
        client_name="Dinas",
    )
    assert created.status_code == 201
    tx_id = created.json()["id"]
    assert created.json()["classification"]["requires_clarification"] is True

    conflict = client.post(
        f"/api/v1/transactions/{tx_id}/clarification",
        json={"category": "usaha", "version": 99},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "VERSION_CONFLICT"


def test_override_and_audit_trail_fr16a(client):
    """FR-16a / API §5.18–5.19 — override records user_override on the jejak.

    Spec create example amount is Rp12.500.000 (§5.11). Override of the sole
    usaha row to pekerjaan_bebas: before includes the row (12_500_000), after=0.
    """
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()
    assert body["amount_idr"] == 12_500_000
    assert body["category"] == "usaha"
    create_evt = client.get(f"/api/v1/transactions/{body['id']}/audit-trail").json()["events"][0]
    assert create_evt["ytd_usaha_omzet_before_idr"] == 0
    assert create_evt["ytd_usaha_omzet_after_idr"] == 12_500_000

    overridden = client.post(
        f"/api/v1/transactions/{body['id']}/override",
        json={"new_category": "pekerjaan_bebas", "note": "Honor narasumber"},
    )
    assert overridden.status_code == 200, overridden.text
    assert overridden.json()["category"] == "pekerjaan_bebas"
    assert overridden.json()["source"] == "user_override"
    assert overridden.json()["version"] == 2

    trail = client.get(f"/api/v1/transactions/{body['id']}/audit-trail")
    assert trail.status_code == 200
    events = trail.json()["events"]
    assert len(events) >= 2
    last = events[-1]
    assert last["source"] == "user_override"
    assert last["new_category"] == "pekerjaan_bebas"
    assert last["ytd_usaha_omzet_before_idr"] == 12_500_000
    assert last["ytd_usaha_omzet_after_idr"] == 0
    assert "ruleset_id" in last


def test_tc_pr4_aud_01_audit_trail_append_only(client):
    """TC-PR4-AUD-01 — classification_events have no public update/delete; cascade only on tx delete."""
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()
    client.post(
        f"/api/v1/transactions/{body['id']}/override",
        json={"new_category": "already_final", "note": "x"},
    )
    trail = client.get(f"/api/v1/transactions/{body['id']}/audit-trail").json()["events"]
    assert len(trail) >= 2

    # No API to mutate events.
    assert client.put(f"/api/v1/transactions/{body['id']}/audit-trail").status_code in {
        404,
        405,
        422,
    }
    assert client.delete(f"/api/v1/transactions/{body['id']}/audit-trail").status_code in {
        404,
        405,
        422,
    }

    db = SessionLocal()
    try:
        events = db.scalars(
            select(ClassificationEvent).where(ClassificationEvent.transaction_id == body["id"])
        ).all()
        assert len(events) >= 2
        victim = events[0]
        # Direct ORM delete of an event is not exposed; after tx delete they cascade.
        event_id = victim.id
    finally:
        db.close()

    assert client.delete(f"/api/v1/transactions/{body['id']}").status_code == 200
    db = SessionLocal()
    try:
        left = db.scalars(
            select(ClassificationEvent).where(ClassificationEvent.id == event_id)
        ).all()
        assert left == []
    finally:
        db.close()


def test_reclassify_rules_layer(client):
    """API §5.9 — reclassify runs keyword pipeline atomically.

    After override to usaha, FR-16a before includes Rp12.500.000; reclassify back
    to pekerjaan_bebas records before=12_500_000, after=0 (§5.19 / Argon #3).
    """
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client, description="fee konsultasi", invoice_no="INV-RECLASS").json()
    assert body["category"] == "pekerjaan_bebas"
    assert body["amount_idr"] == 12_500_000
    client.post(
        f"/api/v1/transactions/{body['id']}/override",
        json={"new_category": "usaha"},
    )
    override_evt = client.get(f"/api/v1/transactions/{body['id']}/audit-trail").json()["events"][-1]
    assert override_evt["ytd_usaha_omzet_before_idr"] == 0
    assert override_evt["ytd_usaha_omzet_after_idr"] == 12_500_000

    result = client.post(
        "/api/v1/transactions/reclassify",
        json={"transaction_ids": [body["id"]]},
    )
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["reclassified_count"] == 1
    assert payload["results"][0]["new_category"] == "pekerjaan_bebas"
    reclass_evt = client.get(f"/api/v1/transactions/{body['id']}/audit-trail").json()["events"][-1]
    assert reclass_evt["source"] == "rule"
    assert reclass_evt["ytd_usaha_omzet_before_idr"] == 12_500_000
    assert reclass_evt["ytd_usaha_omzet_after_idr"] == 0

    assert payload["results"][0]["source"] == "rule"


def test_tc_4_5_54_58_mark_usang_then_recalculate(client):
    """TC-4.5-54 / TC-4.5-58 — mark usang then POST recalculate → new berlaku version+1."""
    from app.services.snapshots_store import mark_usang

    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    me = client.get("/api/v1/auth/me").json()

    before = client.get("/api/v1/tax/snapshots/2026/2026-10")
    assert before.status_code == 200
    before_version = before.json()["version"]
    before_hash = before.json()["input_hash"]

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        mark_usang(db, profile, ["2026-10"])
        db.commit()
    finally:
        db.close()

    # While usang, dashboard must not surface the stale row as the only truth
    # with old numbers pretending to be berlaku — GET month is 404 until recalc.
    assert client.get("/api/v1/tax/snapshots/2026/2026-10").status_code == 404

    recalc = client.post("/api/v1/tax/snapshots/2026/recalculate")
    assert recalc.status_code == 200, recalc.text
    assert recalc.json()["recalculated_months_count"] >= 1
    assert recalc.json()["status"] == "berlaku"

    after = client.get("/api/v1/tax/snapshots/2026/2026-10")
    assert after.status_code == 200
    assert after.json()["status"] == "berlaku"
    assert after.json()["version"] == before_version + 1
    assert after.json()["input_hash"] == before_hash

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        rows = db.scalars(
            select(MonthSnapshot)
            .where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-10",
            )
            .order_by(MonthSnapshot.version)
        ).all()
        assert any(r.status == "usang" and r.version == before_version for r in rows)
        assert rows[-1].status == "berlaku"
        assert rows[-1].version == before_version + 1
    finally:
        db.close()


def test_tc_4_5_55_triggers_mark_usang(client):
    """TC-4.5-55 — override / reclassify / prior-year profile change mark months usang then rebuild."""
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()
    me = client.get("/api/v1/auth/me").json()

    def oct_version():
        db = SessionLocal()
        try:
            profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
            return _assert_one_berlaku_contiguous(db, profile.id, "2026-10")
        finally:
            db.close()

    v0 = oct_version()
    assert (
        client.post(
            f"/api/v1/transactions/{body['id']}/override",
            json={"new_category": "pekerjaan_bebas"},
        ).status_code
        == 200
    )
    assert oct_version() > v0

    # Profile prior-year change (snapshot-affecting) marks + rebuilds.
    prof = client.get("/api/v1/profiles/2026").json()
    v1 = oct_version()
    put = client.put(
        "/api/v1/profiles/2026",
        json={
            "version": prof["version"],
            "name": prof["name"],
            "entity_type": prof["entity_type"],
            "nib_status": prof["nib_status"],
            "nib_last_4": "4321",
            "kbli_code": prof["kbli_code"],
            "business_description": prof["business_description"],
            "marital_status": prof["marital_status"],
            "spouse_aggregation_active": prof["spouse_aggregation_active"],
            "is_new_taxpayer_current_year": False,
            "prior_user_usaha_idr": 1000,
            "prior_user_pekerjaan_bebas_idr": 0,
            "prior_user_already_final_idr": 0,
            "spouse_current_usaha_idr": 0,
            "spouse_current_pekerjaan_bebas_idr": 0,
            "spouse_current_already_final_idr": 0,
            "prior_spouse_usaha_idr": 0,
            "prior_spouse_pekerjaan_bebas_idr": 0,
            "prior_spouse_already_final_idr": 0,
        },
    )
    assert put.status_code == 200, put.text
    assert oct_version() > v1


def test_tc_4_5_56_failed_recalc_leaves_usang(client, monkeypatch):
    """TC-4.5-56 — exception mid-rebuild rolls back; month stays usang (not old berlaku)."""
    from app.engine.ruleset import load_ruleset
    from app.services import snapshots_store
    from app.services.snapshots_store import mark_usang

    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    me = client.get("/api/v1/auth/me").json()

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        before_money = db.scalar(
            select(MonthSnapshot).where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-10",
                MonthSnapshot.status == "berlaku",
            )
        )
        assert before_money is not None
        frozen_omzet = before_money.usaha_omzet_idr
        mark_usang(db, profile, ["2026-10"])
        db.commit()
    finally:
        db.close()

    def boom_compute(*args, **kwargs):
        raise RuntimeError("injected compute fault")

    monkeypatch.setattr(snapshots_store, "compute", boom_compute)

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        try:
            snapshots_store.rebuild(db, profile, load_ruleset(), only_usang=True)
            db.commit()
            raised = False
        except RuntimeError:
            db.rollback()
            raised = True
        assert raised
    finally:
        db.close()

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        berlaku = db.scalars(
            select(MonthSnapshot).where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-10",
                MonthSnapshot.status == "berlaku",
            )
        ).all()
        assert berlaku == []
        usang = db.scalars(
            select(MonthSnapshot).where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-10",
                MonthSnapshot.status == "usang",
            )
        ).all()
        assert usang
        assert usang[-1].usaha_omzet_idr == frozen_omzet
    finally:
        db.close()


def test_tc_4_5_59_and_d11_usang_money_immutable(client):
    """TC-4.5-59 + D-11 — after bump, prior usang money fields stay frozen."""
    from app.services.snapshots_store import mark_usang

    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    me = client.get("/api/v1/auth/me").json()

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        v1 = db.scalar(
            select(MonthSnapshot).where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-10",
                MonthSnapshot.status == "berlaku",
            )
        )
        frozen = (
            v1.usaha_omzet_idr,
            v1.tax_0_5_pct_idr,
            v1.sisa_bayar_idr,
            v1.input_hash,
            v1.version,
        )
        mark_usang(db, profile, ["2026-10"])
        db.commit()
    finally:
        db.close()

    assert client.post("/api/v1/tax/snapshots/2026/recalculate").status_code == 200

    # Change inputs then mark+recalc again so a third version exists.
    body = client.get("/api/v1/transactions?page=1&per_page=10").json()["items"][0]
    client.put(
        f"/api/v1/transactions/{body['id']}",
        json={
            "amount_idr": 30_000_000,
            "tx_date": "2026-10-15",
            "client_name": body["client_name"],
            "description": body["description"],
            "invoice_no": body["invoice_no"],
            "withheld_tax_amount_idr": 0,
            "source_channel": body["source_channel"],
            "version": body["version"],
        },
    )

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        v1 = db.scalar(
            select(MonthSnapshot).where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-10",
                MonthSnapshot.version == frozen[4],
            )
        )
        assert v1.status == "usang"
        assert v1.usaha_omzet_idr == frozen[0]
        assert v1.tax_0_5_pct_idr == frozen[1]
        assert v1.sisa_bayar_idr == frozen[2]
        assert v1.input_hash == frozen[3]
        _assert_one_berlaku_contiguous(db, profile.id, "2026-10")
    finally:
        db.close()


def test_tc_4_5_noop_recalc_does_not_bump(client):
    """No-op recalc (nothing usang / same hash) does not bump version."""
    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    before = client.get("/api/v1/tax/snapshots/2026/2026-10").json()["version"]
    recalc = client.post("/api/v1/tax/snapshots/2026/recalculate")
    assert recalc.status_code == 200
    assert recalc.json()["recalculated_months_count"] == 0
    after = client.get("/api/v1/tax/snapshots/2026/2026-10").json()["version"]
    assert after == before


def test_tc_4_5_60_exactly_one_berlaku_after_n_recalcs(client):
    """TC-4.5-60 — N>=5 mark+recalc cycles leave exactly one berlaku; versions contiguous."""
    from app.services.snapshots_store import mark_usang

    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    me = client.get("/api/v1/auth/me").json()
    n = 5
    for _ in range(n):
        db = SessionLocal()
        try:
            profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
            mark_usang(db, profile, ["2026-10"])
            db.commit()
        finally:
            db.close()
        assert client.post("/api/v1/tax/snapshots/2026/recalculate").status_code == 200

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        ver = _assert_one_berlaku_contiguous(db, profile.id, "2026-10")
        assert ver >= n
    finally:
        db.close()


def test_tc_4_5_61_concurrent_rebuilds_one_berlaku(client):
    """TC-4.5-61 — two MySQL sessions rebuild same usang month → one berlaku."""
    import threading

    from app.engine.ruleset import load_ruleset
    from app.services.snapshots_store import mark_usang, rebuild

    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    me = client.get("/api/v1/auth/me").json()

    setup = SessionLocal()
    try:
        profile = setup.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        profile_id = profile.id
        mark_usang(setup, profile, ["2026-10"])
        setup.commit()
    finally:
        setup.close()

    barriers = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker() -> None:
        barriers.wait(timeout=10)
        db = SessionLocal()
        try:
            profile = db.scalar(select(Profile).where(Profile.id == profile_id))
            rebuild(db, profile, load_ruleset(), only_usang=True)
            db.commit()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
            db.rollback()
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive()
    assert not errors, errors

    db = SessionLocal()
    try:
        _assert_one_berlaku_contiguous(db, profile_id, "2026-10")
    finally:
        db.close()


def test_tc_4_5_62_integrity_error_version_retry(client, monkeypatch):
    """TC-4.5-62 — stale next-version UK hit retries and still lands one berlaku."""
    from app.engine.ruleset import load_ruleset
    from app.services import snapshots_store
    from app.services.snapshots_store import mark_usang

    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    me = client.get("/api/v1/auth/me").json()

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        before = _assert_one_berlaku_contiguous(db, profile.id, "2026-10")
        mark_usang(db, profile, ["2026-10"])
        db.flush()

        real_next = snapshots_store._next_version
        state = {"stale_hits": 0}

        def flaky_next(session, profile_id: str, month_key: str) -> int:
            real = real_next(session, profile_id, month_key)
            if month_key == "2026-10" and state["stale_hits"] == 0:
                state["stale_hits"] += 1
                return max(real - 1, 1)
            return real

        monkeypatch.setattr(snapshots_store, "_next_version", flaky_next)
        snapshots_store.rebuild(db, profile, load_ruleset(), only_usang=True)
        db.commit()
        assert state["stale_hits"] == 1
        after = _assert_one_berlaku_contiguous(db, profile.id, "2026-10")
        assert after == before + 1
    finally:
        db.close()


def test_tc_4_5_63_exhausted_retries_return_409(client, monkeypatch):
    """TC-4.5-63 — exhausted UK retries → 409 VERSION_CONFLICT; no partial berlaku write."""
    from app.api.errors import ApiError
    from app.engine.ruleset import load_ruleset
    from app.services import snapshots_store
    from app.services.snapshots_store import mark_usang

    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    me = client.get("/api/v1/auth/me").json()

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        before = _assert_one_berlaku_contiguous(db, profile.id, "2026-10")
        mark_usang(db, profile, ["2026-10"])
        db.commit()
    finally:
        db.close()

    def always_stale(session, profile_id: str, month_key: str) -> int:
        # Always collide with an existing version number.
        return 1

    monkeypatch.setattr(snapshots_store, "_next_version", always_stale)

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        try:
            snapshots_store.rebuild(db, profile, load_ruleset(), only_usang=True)
            db.commit()
            raised = None
        except ApiError as exc:
            raised = exc
        assert raised is not None
        assert raised.status == 409
        assert raised.code == "VERSION_CONFLICT"
    finally:
        db.close()

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        berlaku = db.scalars(
            select(MonthSnapshot).where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-10",
                MonthSnapshot.status == "berlaku",
            )
        ).all()
        # Rolled back: still no berlaku (usang retained from before the failed rebuild).
        assert berlaku == []
        usang = db.scalars(
            select(MonthSnapshot).where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-10",
                MonthSnapshot.status == "usang",
                MonthSnapshot.version == before,
            )
        ).all()
        assert len(usang) == 1
    finally:
        db.close()


def test_tc_4_6_29_fr47_month_jejak(client):
    """TC-4.6-29 FR-47 — GET month snapshot returns stamp + hash + status."""
    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    snap = client.get("/api/v1/tax/snapshots/2026/2026-10")
    assert snap.status_code == 200
    body = snap.json()
    assert body["status"] == "berlaku"
    assert body["ruleset_id"]
    assert body["input_hash"].startswith("v1:")
    assert body["disclaimer"] == DISCLAIMER


def test_tc_hard_31_exact_workpaper_disclaimer(client):
    """TC-HARD-31 — dashboard + month snapshot use the D-07/API §3.3 disclaimer exactly."""
    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    assert DISCLAIMER == EXACT_DISCLAIMER
    dashboard = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
    assert dashboard["metadata"]["disclaimer"] == EXACT_DISCLAIMER
    snap = client.get("/api/v1/tax/snapshots/2026/2026-10").json()
    assert snap["disclaimer"] == EXACT_DISCLAIMER


def test_tc_4_6_24_free_quota_counters(client):
    """TC-4.6-24 FR-39 — free limits 10/15; used starts at 0; Jakarta month_key."""
    _auth(client)
    quotas = client.get("/api/v1/quotas").json()
    assert quotas["timezone"] == "Asia/Jakarta"
    assert quotas["ai_classification"]["used"] == 0
    assert quotas["ai_classification"]["limit"] == 10
    assert quotas["assistant_chat"]["limit"] == 15
    assert quotas["ai_classification"]["status"] == "active"
    assert len(quotas["month_key"]) == 7


def test_tc_4_6_25_paid_quota_limits(client):
    """TC-4.6-25 — paid active → limit 200/200."""
    _auth(client)
    me = client.get("/api/v1/auth/me").json()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.id == me["user_id"]))
        user.paid_flag = True
        user.valid_until_utc = now_utc() + timedelta(days=30)
        db.commit()
    finally:
        db.close()
    quotas = client.get("/api/v1/quotas").json()
    assert quotas["ai_classification"]["limit"] == 200
    assert quotas["assistant_chat"]["limit"] == 200


def test_tc_4_6_26_quota_boundaries_free_and_paid(client):
    """TC-4.6-26 — used=limit-1 → active; used=limit → exhausted (free 10/15, paid 200)."""
    _auth(client)
    me = client.get("/api/v1/auth/me").json()
    # Ensure counter row exists.
    client.get("/api/v1/quotas")

    def set_used(ai: int, chat: int):
        db = SessionLocal()
        try:
            row = db.scalar(select(QuotaCounter).where(QuotaCounter.user_id == me["user_id"]))
            assert row is not None
            row.ai_classification_used = ai
            row.assistant_chat_used = chat
            db.commit()
        finally:
            db.close()

    set_used(9, 14)
    q = client.get("/api/v1/quotas").json()
    assert q["ai_classification"]["limit"] == 10
    assert q["ai_classification"]["status"] == "active"
    assert q["assistant_chat"]["limit"] == 15
    assert q["assistant_chat"]["status"] == "active"

    set_used(10, 15)
    q = client.get("/api/v1/quotas").json()
    assert q["ai_classification"]["status"] == "exhausted"
    assert q["assistant_chat"]["status"] == "exhausted"

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.id == me["user_id"]))
        user.paid_flag = True
        user.valid_until_utc = now_utc() + timedelta(days=30)
        db.commit()
    finally:
        db.close()

    set_used(199, 199)
    q = client.get("/api/v1/quotas").json()
    assert q["ai_classification"]["limit"] == 200
    assert q["ai_classification"]["status"] == "active"
    assert q["assistant_chat"]["status"] == "active"

    set_used(200, 200)
    q = client.get("/api/v1/quotas").json()
    assert q["ai_classification"]["status"] == "exhausted"
    assert q["assistant_chat"]["status"] == "exhausted"


def test_tc_4_6_27_quotas_are_session_scoped(client):
    """TC-4.6-27 — another account sees its own counters, not ours."""
    _auth(client)
    me = client.get("/api/v1/auth/me").json()
    client.get("/api/v1/quotas")
    db = SessionLocal()
    try:
        row = db.scalar(select(QuotaCounter).where(QuotaCounter.user_id == me["user_id"]))
        row.ai_classification_used = 7
        db.commit()
    finally:
        db.close()

    other = TestClient(client.app)
    assert (
        other.post(
            "/api/v1/auth/register",
            json={
                "email": "quotaother@example.com",
                "username": "quotaother",
                "password": "PasswordMinimal10",
            },
        ).status_code
        == 201
    )
    assert (
        other.post(
            "/api/v1/auth/login",
            json={
                "identifier": "quotaother@example.com",
                "password": "PasswordMinimal10",
            },
        ).status_code
        == 200
    )
    theirs = other.get("/api/v1/quotas").json()
    assert theirs["ai_classification"]["used"] == 0
    mine = client.get("/api/v1/quotas").json()
    assert mine["ai_classification"]["used"] == 7


def test_tc_4_6_28_month_key_follows_asia_jakarta(client):
    """TC-4.6-28 — month_key matches Asia/Jakarta calendar month."""
    from zoneinfo import ZoneInfo

    _auth(client)
    quotas = client.get("/api/v1/quotas").json()
    jakarta = now_utc().replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Jakarta"))
    assert quotas["month_key"] == jakarta.strftime("%Y-%m")
    assert quotas["timezone"] == "Asia/Jakarta"


def test_tc_4_6_30_missing_month_snapshot_is_404(client):
    """TC-4.6-30 — month without a cuplikan → 404 SNAPSHOT_NOT_FOUND."""
    from app.services.snapshots_store import mark_usang

    _auth(client)
    assert _profile(client).status_code == 200
    me = client.get("/api/v1/auth/me").json()
    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        # Remove November if present so GET is empty.
        for row in db.scalars(
            select(MonthSnapshot).where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-11",
            )
        ).all():
            db.delete(row)
        db.commit()
    finally:
        db.close()
    # If today is before Nov in a frozen clock this may still 200 from seed —
    # force usang+delete berlaku via mark then delete all Nov rows.
    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        mark_usang(db, profile, ["2026-11"])
        for row in db.scalars(
            select(MonthSnapshot).where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.month_key == "2026-11",
            )
        ).all():
            db.delete(row)
        db.commit()
    finally:
        db.close()
    resp = client.get("/api/v1/tax/snapshots/2026/2026-11")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SNAPSHOT_NOT_FOUND"


def test_tc_4_6_31_snapshot_requires_session(client):
    """TC-4.6-31 — unauthenticated month jejak → 401."""
    from app.main import app

    bare = TestClient(app)
    assert bare.get("/api/v1/tax/snapshots/2026/2026-10").status_code == 401


def test_tc_4_6_32_input_hash_is_v1_prefixed(client):
    """TC-4.6-32 — month input_hash is the v1: digests used by NFR-02 goldens."""
    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    body = client.get("/api/v1/tax/snapshots/2026/2026-10").json()
    assert body["input_hash"].startswith("v1:")
    assert len(body["input_hash"]) > 10


def test_hb12_cap_eq_stays_eligible_dashboard(client):
    """HB-12 / TC-4.5-27 — prior_combined == 4_800_000_000 stays scheme_eligible."""
    _auth(client)
    assert (
        _profile(
            client,
            is_new_taxpayer_current_year=False,
            prior_user_usaha_idr=4_800_000_000,
            prior_user_pekerjaan_bebas_idr=0,
            prior_user_already_final_idr=0,
        ).status_code
        == 200
    )
    assert _tx(client).status_code == 201
    dashboard = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
    prior = dashboard["thresholds"]["eligibility_prior_year_cap_4_8m"]
    assert prior["combined_prior_year_gross_idr"] == 4_800_000_000
    assert prior["status"] == "scheme_eligible"


def test_tc_4_5_28_hb12_plus_one_ineligible(client):
    """TC-4.5-28 / HB-12 +1 — prior_combined 4_800_000_001 → scheme_ineligible."""
    _auth(client)
    assert (
        _profile(
            client,
            is_new_taxpayer_current_year=False,
            prior_user_usaha_idr=4_800_000_001,
            prior_user_pekerjaan_bebas_idr=0,
            prior_user_already_final_idr=0,
        ).status_code
        == 200
    )
    assert _tx(client).status_code == 201
    dashboard = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
    prior = dashboard["thresholds"]["eligibility_prior_year_cap_4_8m"]
    assert prior["combined_prior_year_gross_idr"] == 4_800_000_001
    assert prior["status"] == "scheme_ineligible"


def test_tc_4_3_64_parallel_puts_same_version_one_winner(client):
    """TC-4.3-64 — N≥8 parallel PUTs at the same version: exactly one 2xx.

    Adapted from review-pr4-scratch/pr4_concurrency_stress.py (direct service
    path). Losers must be 409 VERSION_CONFLICT; final row.version == start+1.
    """
    import threading
    from collections import Counter

    from app.api.errors import ApiError
    from app.engine.ruleset import load_ruleset
    from app.models import Transaction as TransactionRow
    from app.schemas.transaction import TransactionUpdate
    from app.services import transactions as tx_svc

    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()
    tx_id = body["id"]
    start_version = body["version"]
    assert start_version == 1
    me = client.get("/api/v1/auth/me").json()
    user_id = me["user_id"]

    n = 8
    barrier = threading.Barrier(n)
    outcomes: Counter = Counter()
    lock = threading.Lock()
    ruleset = load_ruleset()

    def worker(i: int) -> None:
        barrier.wait(timeout=30)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.id == user_id))
            payload = TransactionUpdate(
                amount_idr=12_500_000 + (i + 1) * 1000,
                tx_date=__import__("datetime").date(2026, 10, 15),
                client_name="PT Sumber Makmur",
                description="Penjualan sembako",
                invoice_no="INV-TAX-001",
                withheld_tax_amount_idr=0,
                source_channel="corporate_client",
                version=start_version,
            )
            tx_svc.update_transaction(db, user, tx_id, payload, ruleset)
            with lock:
                outcomes["2xx"] += 1
        except ApiError as exc:
            db.rollback()
            with lock:
                if exc.status == 409 and exc.code == "VERSION_CONFLICT":
                    outcomes["409_VERSION_CONFLICT"] += 1
                else:
                    outcomes[f"api:{exc.status}:{exc.code}"] += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            with lock:
                outcomes[f"OTHER:{type(exc).__name__}"] += 1
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
        assert not t.is_alive()

    assert outcomes["2xx"] == 1, dict(outcomes)
    assert outcomes["409_VERSION_CONFLICT"] == n - 1, dict(outcomes)
    assert sum(outcomes.values()) == n

    db = SessionLocal()
    try:
        row = db.scalar(select(TransactionRow).where(TransactionRow.id == tx_id))
        assert row is not None
        assert row.version == start_version + 1
        profile = db.scalar(select(Profile).where(Profile.user_id == user_id))
        _assert_one_berlaku_contiguous(db, profile.id, "2026-10")
    finally:
        db.close()


def test_tc_4_5_64_concurrent_put_and_recalculate_no_deadlock(client):
    """TC-4.5-64 — concurrent PUT + recalculate on same profile: no deadlock.

    One thread marks usang + recalculates; peers issue PUTs. Outcomes must be
    2xx or 409 only (no OperationalError 1213 / 5xx-class). Snapshots keep
    exactly one berlaku per month.
    """
    import threading
    from collections import Counter
    from datetime import date

    from sqlalchemy.exc import OperationalError

    from app.api.errors import ApiError
    from app.engine.ruleset import load_ruleset
    from app.models import Transaction as TransactionRow
    from app.schemas.transaction import TransactionUpdate
    from app.services import transactions as tx_svc
    from app.services.snapshots_store import mark_usang, rebuild

    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()
    tx_id = body["id"]
    me = client.get("/api/v1/auth/me").json()
    user_id = me["user_id"]
    ruleset = load_ruleset()

    # Leave October usang so recalculate has work to do.
    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == user_id))
        profile_id = profile.id
        mark_usang(db, profile, ["2026-10"])
        db.commit()
    finally:
        db.close()

    n_put = 4
    barrier = threading.Barrier(n_put + 1)
    outcomes: Counter = Counter()
    lock = threading.Lock()

    def put_worker(i: int) -> None:
        barrier.wait(timeout=30)
        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.id == user_id))
            row = db.scalar(select(TransactionRow).where(TransactionRow.id == tx_id))
            ver = row.version
            payload = TransactionUpdate(
                amount_idr=12_500_000 + (i + 1) * 500,
                tx_date=date(2026, 10, 15),
                client_name="PT Sumber Makmur",
                description="Penjualan sembako",
                invoice_no="INV-TAX-001",
                withheld_tax_amount_idr=0,
                source_channel="corporate_client",
                version=ver,
            )
            tx_svc.update_transaction(db, user, tx_id, payload, ruleset)
            with lock:
                outcomes["put_2xx"] += 1
        except ApiError as exc:
            db.rollback()
            with lock:
                if exc.status == 409 and exc.code == "VERSION_CONFLICT":
                    outcomes["put_409"] += 1
                else:
                    outcomes[f"put_api:{exc.status}:{exc.code}"] += 1
        except OperationalError as exc:
            db.rollback()
            with lock:
                outcomes[f"put_deadlock:{exc.orig.args[0] if exc.orig else exc}"] += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            with lock:
                outcomes[f"put_OTHER:{type(exc).__name__}"] += 1
        finally:
            db.close()

    def recalc_worker() -> None:
        barrier.wait(timeout=30)
        db = SessionLocal()
        try:
            profile = db.scalar(select(Profile).where(Profile.id == profile_id))
            rebuild(db, profile, ruleset, only_usang=True)
            db.commit()
            with lock:
                outcomes["recalc_ok"] += 1
        except ApiError as exc:
            db.rollback()
            with lock:
                if exc.status == 409 and exc.code == "VERSION_CONFLICT":
                    outcomes["recalc_409"] += 1
                else:
                    outcomes[f"recalc_api:{exc.status}:{exc.code}"] += 1
        except OperationalError as exc:
            db.rollback()
            with lock:
                outcomes[f"recalc_deadlock:{exc.orig.args[0] if exc.orig else exc}"] += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            with lock:
                outcomes[f"recalc_OTHER:{type(exc).__name__}"] += 1
        finally:
            db.close()

    threads = [threading.Thread(target=put_worker, args=(i,)) for i in range(n_put)]
    threads.append(threading.Thread(target=recalc_worker))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
        assert not t.is_alive()

    assert not any("deadlock" in k for k in outcomes), dict(outcomes)
    assert not any(k.startswith("put_OTHER") or k.startswith("recalc_OTHER") for k in outcomes), (
        dict(outcomes)
    )
    assert outcomes.get("recalc_ok", 0) + outcomes.get("recalc_409", 0) == 1, dict(outcomes)
    assert outcomes.get("put_2xx", 0) + outcomes.get("put_409", 0) == n_put, dict(outcomes)

    db = SessionLocal()
    try:
        _assert_one_berlaku_contiguous(db, profile_id, "2026-10")
    finally:
        db.close()


def test_tc_argon_asof_future_tx_excluded_from_snapshots_and_dashboard(client):
    """Argon #2 / API §2.4 §5.11 — future-dated usaha is stored but excluded.

    With today frozen to 2026-11-02, a 2026-12-15 usaha tx must not change
    usaha_ytd, remaining_free_band_idr, or monthly_summaries; no month rows
    past November exist.
    """
    with freeze_today_jakarta(date(2026, 11, 2)):
        _auth(client)
        assert _profile(client).status_code == 200
        assert _tx(client).status_code == 201  # 2026-10-15 usaha 12.5M

        before = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
        assert before["thresholds"]["pita_500_juta"]["ytd_usaha_omzet_idr"] == 12_500_000
        remaining_before = before["thresholds"]["pita_500_juta"]["remaining_free_band_idr"]
        months_before = [m["month"] for m in before["monthly_summaries"]]
        assert "2026-11" in months_before
        assert "2026-12" not in months_before

        future = _tx(
            client,
            tx_date="2026-12-15",
            invoice_no="INV-FUTURE-001",
            amount_idr=50_000_000,
            description="Penjualan sembako desember",
        )
        assert future.status_code == 201, future.text
        assert future.json()["category"] == "usaha"

        after = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
        assert after["thresholds"]["pita_500_juta"]["ytd_usaha_omzet_idr"] == 12_500_000
        assert after["thresholds"]["pita_500_juta"]["remaining_free_band_idr"] == remaining_before
        months_after = [m["month"] for m in after["monthly_summaries"]]
        assert months_after == months_before
        assert "2026-12" not in months_after

        me = client.get("/api/v1/auth/me").json()
        db = SessionLocal()
        try:
            profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
            past_nov = db.scalars(
                select(MonthSnapshot).where(
                    MonthSnapshot.profile_id == profile.id,
                    MonthSnapshot.month_key > "2026-11",
                )
            ).all()
            assert past_nov == []
        finally:
            db.close()


def test_tc_argon_month_path_foo_is_422(client):
    """Argon #5 / API §5.21 — non-numeric month path is 422 INVALID_DATE_RANGE."""
    _auth(client)
    assert _profile(client).status_code == 200
    resp = client.get("/api/v1/tax/snapshots/2026/foo")
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "INVALID_DATE_RANGE"

    resp13 = client.get("/api/v1/tax/snapshots/2026/13")
    assert resp13.status_code == 422
    assert resp13.json()["error"]["code"] == "INVALID_DATE_RANGE"

    resp_year = client.get("/api/v1/tax/snapshots/2025/2025-10")
    assert resp_year.status_code == 422
    assert resp_year.json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_tc_argon_quota_ensure_counter_race(client):
    """Argon #6 — concurrent first GET /quotas of a month: one insert, no error."""
    import threading
    from collections import Counter

    _auth(client)
    me = client.get("/api/v1/auth/me").json()
    user_id = me["user_id"]

    # Ensure no counter row yet for the current Jakarta month.
    month_key = today_jakarta().strftime("%Y-%m")
    db = SessionLocal()
    try:
        existing = db.scalars(
            select(QuotaCounter).where(
                QuotaCounter.user_id == user_id,
                QuotaCounter.month_key == month_key,
            )
        ).all()
        for row in existing:
            db.delete(row)
        db.commit()
    finally:
        db.close()

    barrier = threading.Barrier(8)
    outcomes: Counter = Counter()
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait(timeout=30)
        # Each thread uses its own TestClient session cookie via login.
        from app.main import app

        local = TestClient(app)
        assert (
            local.post(
                "/api/v1/auth/login",
                json={"identifier": AUTH["email"], "password": AUTH["password"]},
            ).status_code
            == 200
        )
        try:
            resp = local.get("/api/v1/quotas")
            with lock:
                outcomes[f"status:{resp.status_code}"] += 1
                if resp.status_code == 200:
                    outcomes["ok"] += 1
        except Exception as exc:  # noqa: BLE001
            with lock:
                outcomes[f"exc:{type(exc).__name__}"] += 1

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
        assert not t.is_alive()

    assert outcomes.get("ok", 0) == 8, dict(outcomes)
    assert not any(k.startswith("exc:") for k in outcomes), dict(outcomes)

    db = SessionLocal()
    try:
        rows = db.scalars(
            select(QuotaCounter).where(
                QuotaCounter.user_id == user_id,
                QuotaCounter.month_key == month_key,
            )
        ).all()
        assert len(rows) == 1
    finally:
        db.close()
