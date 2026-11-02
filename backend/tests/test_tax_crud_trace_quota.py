"""M50 Tax lane: CRUD, override, audit trail, snapshot versioning, quotas.

TC ids referenced: TC-4.3-41…52, TC-4.5-54…59, TC-4.6-24…32, API §5.17 VERSION_CONFLICT.
"""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import MonthSnapshot

AUTH = {
    "email": "taxlane@example.com",
    "username": "taxlaneuser",
    "password": "PasswordMinimal10",
}


def _register(client, **overrides):
    payload = dict(AUTH)
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload)


def _login(client):
    return client.post(
        "/api/v1/auth/login",
        json={"identifier": AUTH["email"], "password": AUTH["password"]},
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


def test_tc_4_3_41_edit_amount_rebuilds_and_bumps_version(client):
    """TC-4.3-41 FR-08 — edit amount; dashboard changes; version increments."""
    _auth(client)
    assert _profile(client).status_code == 200
    created = _tx(client)
    assert created.status_code == 201
    body = created.json()
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


def test_tc_4_3_43_put_stale_version_conflict(client):
    """TC-4.3-43 / API §5.12 — stale version → 409 VERSION_CONFLICT."""
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


def test_override_and_audit_trail_fr16a(client):
    """FR-16a / API §5.18–5.19 — override records user_override on the jejak."""
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client).json()
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
    assert last["ytd_usaha_omzet_after_idr"] == 0
    assert "ruleset_id" in last


def test_reclassify_rules_layer(client):
    """API §5.9 — reclassify runs keyword pipeline atomically."""
    _auth(client)
    assert _profile(client).status_code == 200
    body = _tx(client, description="fee konsultasi", invoice_no="INV-RECLASS").json()
    # description has fee → pekerjaan_bebas; create already classified
    assert body["category"] == "pekerjaan_bebas"
    # override to usaha then reclassify back via rules
    client.post(
        f"/api/v1/transactions/{body['id']}/override",
        json={"new_category": "usaha"},
    )
    result = client.post(
        "/api/v1/transactions/reclassify",
        json={"transaction_ids": [body["id"]]},
    )
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["reclassified_count"] == 1
    assert payload["results"][0]["new_category"] == "pekerjaan_bebas"
    assert payload["results"][0]["source"] == "rule"


def test_tc_4_5_54_58_recalculate_marks_usang_and_inserts_berlaku(client):
    """TC-4.5-54 / TC-4.5-58 — prior berlaku → usang; new berlaku version+1."""
    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201

    before = client.get("/api/v1/tax/snapshots/2026/2026-10")
    assert before.status_code == 200, before.text
    assert before.json()["status"] == "berlaku"
    # Profile PUT wrote v1; create_transaction rebuild wrote the current berlaku.
    before_version = before.json()["version"]
    assert before_version >= 1
    first_hash = before.json()["input_hash"]

    recalc = client.post("/api/v1/tax/snapshots/2026/recalculate")
    assert recalc.status_code == 200, recalc.text
    assert recalc.json()["status"] == "berlaku"
    assert recalc.json()["recalculated_months_count"] >= 1

    after = client.get("/api/v1/tax/snapshots/2026/2026-10")
    assert after.status_code == 200
    assert after.json()["status"] == "berlaku"
    assert after.json()["version"] == before_version + 1
    assert after.json()["input_hash"] == first_hash  # same inputs → same hash

    # Prior version is retained as usang (not overwritten) — D-11 / HB-16.
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(MonthSnapshot)
            .where(MonthSnapshot.month_key == "2026-10")
            .order_by(MonthSnapshot.version)
        ).all()
        assert len(rows) >= 2
        assert any(r.status == "usang" and r.version == before_version for r in rows)
        assert rows[-1].status == "berlaku"
        assert rows[-1].version == before_version + 1
    finally:
        db.close()

    # Dashboard only surfaces berlaku rows (D-11 read filter).
    dashboard = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
    oct_rows = [r for r in dashboard["monthly_summaries"] if r["month"] == "2026-10"]
    assert len(oct_rows) == 1
    assert oct_rows[0]["status"] == "berlaku"
    assert oct_rows[0]["version"] == before_version + 1


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
    assert "WORKPAPER" in body["disclaimer"]
    assert client.get("/api/v1/tax/snapshots/2026/2026-01").status_code == 200


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
    from datetime import timedelta

    from app.models import User
    from app.security import now_utc

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


def test_hb12_cap_eq_stays_eligible_dashboard(client):
    """HB-12 residual — prior_combined == 4_800_000_000 stays scheme_eligible."""
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


def _assert_one_berlaku_contiguous(db, profile_id: str, month_key: str) -> int:
    """Exactly one berlaku; usang versions are a contiguous prefix below it."""
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
    assert len(berlaku) == 1, f"expected 1 berlaku, got {[(r.version, r.status) for r in rows]}"
    versions = [r.version for r in rows]
    assert versions == list(range(1, len(rows) + 1)), versions
    assert berlaku[0].version == versions[-1]
    return berlaku[0].version


def test_tc_4_5_60_exactly_one_berlaku_after_n_recalcs(client):
    """TC-4.5-60 — N>=5 recalcs leave exactly one berlaku; versions 1..N contiguous."""
    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201

    me = client.get("/api/v1/auth/me").json()
    n = 5
    for _ in range(n):
        assert client.post("/api/v1/tax/snapshots/2026/recalculate").status_code == 200

    db = SessionLocal()
    try:
        from app.models import Profile

        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        assert profile is not None
        # create_transaction already rebuilt once after profile PUT's v1, so
        # total versions >= n + 2; invariant is one berlaku + contiguous ints.
        ver = _assert_one_berlaku_contiguous(db, profile.id, "2026-10")
        assert ver >= n
        # Every other month through Jakarta "today" also has a single berlaku.
        months = db.scalars(
            select(MonthSnapshot.month_key).where(MonthSnapshot.profile_id == profile.id).distinct()
        ).all()
        for month_key in months:
            _assert_one_berlaku_contiguous(db, profile.id, month_key)
    finally:
        db.close()

    dashboard = client.get("/api/v1/tax/dashboard?tax_year=2026").json()
    oct_rows = [r for r in dashboard["monthly_summaries"] if r["month"] == "2026-10"]
    assert len(oct_rows) == 1
    assert oct_rows[0]["status"] == "berlaku"


def test_tc_4_5_61_concurrent_rebuilds_one_berlaku(client):
    """TC-4.5-61 — two MySQL sessions rebuild same profile → one berlaku, contiguous."""
    import threading

    from app.engine.ruleset import load_ruleset
    from app.models import Profile
    from app.services.snapshots_store import rebuild

    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    me = client.get("/api/v1/auth/me").json()

    setup = SessionLocal()
    try:
        profile_id = setup.scalar(select(Profile.id).where(Profile.user_id == me["user_id"]))
        assert profile_id
    finally:
        setup.close()

    barriers = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker() -> None:
        # Open the transaction only after the barrier so MySQL RR does not pin
        # a pre-lock snapshot before we wait on SELECT … FOR UPDATE.
        barriers.wait(timeout=10)
        db = SessionLocal()
        try:
            profile = db.scalar(select(Profile).where(Profile.id == profile_id))
            assert profile is not None
            rebuild(db, profile, load_ruleset())
            db.commit()
        except BaseException as exc:  # noqa: BLE001 — collect for main thread
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
        months = db.scalars(
            select(MonthSnapshot.month_key).where(MonthSnapshot.profile_id == profile_id).distinct()
        ).all()
        for month_key in months:
            _assert_one_berlaku_contiguous(db, profile_id, month_key)
    finally:
        db.close()


def test_tc_4_5_62_integrity_error_version_retry(client, monkeypatch):
    """TC-4.5-62 — stale next-version that hits the UK retries and still lands one berlaku."""
    from app.engine.ruleset import load_ruleset
    from app.models import Profile
    from app.services import snapshots_store

    _auth(client)
    assert _profile(client).status_code == 200
    assert _tx(client).status_code == 201
    me = client.get("/api/v1/auth/me").json()

    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == me["user_id"]))
        assert profile is not None
        before = _assert_one_berlaku_contiguous(db, profile.id, "2026-10")

        real_next = snapshots_store._next_version
        state = {"stale_hits": 0}

        def flaky_next(session, profile_id: str, month_key: str) -> int:
            real = real_next(session, profile_id, month_key)
            # First attempt for October returns an already-used version → IntegrityError.
            if month_key == "2026-10" and state["stale_hits"] == 0:
                state["stale_hits"] += 1
                return max(real - 1, 1)
            return real

        monkeypatch.setattr(snapshots_store, "_next_version", flaky_next)
        rebuild_written = snapshots_store.rebuild(db, profile, load_ruleset())
        db.commit()
        assert state["stale_hits"] == 1
        assert any(row.month_key == "2026-10" for row in rebuild_written)
        after = _assert_one_berlaku_contiguous(db, profile.id, "2026-10")
        assert after == before + 1
    finally:
        db.close()
