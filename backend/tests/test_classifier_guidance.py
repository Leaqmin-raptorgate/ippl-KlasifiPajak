"""Classifier, clarification, onboarding and guidance contracts (FR-11, FR-14, FR-48)."""

from datetime import date

import pytest
from sqlalchemy import select
from test_tax_crud_trace_quota import _auth, _profile, _tx

from app.classify.rules import RULES, classify
from app.db import SessionLocal
from app.engine import Profile as TaxProfile
from app.engine import Transaction, compute
from app.models import MonthSnapshot, Profile
from app.services.snapshots_store import freeze_today_jakarta


@pytest.mark.parametrize("description", ["konsejuk", "terjualah", "tokoferol", "pelayanan bebas"])
def test_fr11_rule_terms_require_word_boundaries(description):
    """FR-11: substrings inside unrelated words cannot classify a transaction."""
    assert classify(description)[3] is True


@pytest.mark.parametrize(
    "description",
    [
        "jual endorsement",
        "penjualan influencer",
        "jual adsense",
        "jual distributor pemasaran berjenjang",
    ],
)
def test_fr11_creator_and_mlm_take_precedence_over_sale(description):
    """FR-11: creator and distributor phrases identify independent work."""
    category, _, _, clarification, _ = classify(description)
    assert category == "pekerjaan_bebas"
    assert clarification is False


@pytest.mark.parametrize("description", ["Sewa kamar kos dari penghuni", "uang kos bulan ini"])
def test_fr11_kos_rent_is_final_building_rent(description):
    """FR-11: renting out kos rooms is building rent under PPh 4(2), not 0,5% turnover."""
    category, rule_id, _, clarification, _ = classify(description)
    assert (category, rule_id, clarification) == ("already_final", "already_final.kos", False)


def test_fr11_ongkos_does_not_trigger_kos_rule():
    """FR-11: 'kos' inside 'ongkos' is not a kos rental."""
    assert classify("ongkos kirim")[1] != "already_final.kos"


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Proyek renovasi dapur, bukti potong PPh final", "already_final"),
        ("Galian pondasi, sudah final di bukti potong", "already_final"),
        ("Sewa lahan parkir ke tetangga", "already_final"),
        ("Setor tunai dari dompet pribadi", "non_object"),
        ("Pindah saldo antar akun", "non_object"),
        ("Top up e-wallet", "non_object"),
        ("Jual sepeda bekas, bukan usaha", "non_object"),
        ("Kiriman dari orang tua", "non_object"),
        ("Pesangon dari perusahaan", "non_object"),
        ("Komisi perantara penjualan tanah", "pekerjaan_bebas"),
        ("endorse produk sepatu", "pekerjaan_bebas"),
    ],
)
def test_fr11_decisive_signals_win_over_sale_words(description, expected):
    """FR-11: final-tax markers, own-money flows and listed professions decide first."""
    category, _, _, clarification, _ = classify(description)
    assert (category, clarification) == (expected, False)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("hasil jualan gorengan", "usaha"),
        ("orderan kaos polos lunas", "usaha"),
        ("Pembayaran order 20 botol kecap", "usaha"),
        ("byr pesanan rendang", "usaha"),
        ("Jasa pemasangan kanopi", "usaha"),
        ("sablon kaos komunitas", "usaha"),
        ("Jasa penerjemahan jurnal", "pekerjaan_bebas"),
        ("editing video wedding", "pekerjaan_bebas"),
        ("ngajar les gitar", "pekerjaan_bebas"),
        ("Jasa pembukuan toko kelontong klien", "pekerjaan_bebas"),
    ],
)
def test_fr11_common_turnover_phrasings_classify(description, expected):
    """FR-11: everyday phrasing for goods, trade services and professions is recognised."""
    category, _, _, clarification, _ = classify(description)
    assert (category, clarification) == (expected, False)


@pytest.mark.parametrize(
    "description",
    [
        "Penjualan kaos dan honor seminar",
        "Jual buku sekaligus workshop menulis",
        "Honor jasa perbaikan printer",
    ],
)
def test_fr14_mixed_usaha_and_profession_asks_instead_of_guessing(description):
    """FR-14: a row carrying both a sale and a profession signal goes to clarification."""
    assert classify(description)[3] is True


def test_fr11_each_rule_has_confidence_and_result_uses_matched_rule():
    """FR-11: confidence belongs to the matched rule and is bounded."""
    for rule in RULES:
        assert 0 <= rule.confidence <= 1
        _, rule_id, confidence, requires_clarification, _ = classify(rule.phrase)
        matched = next(item for item in RULES if item.id == rule_id)
        assert not requires_clarification
        assert confidence == matched.confidence


def test_fr11_client_name_alone_does_not_classify(client):
    _auth(client)
    assert _profile(client).status_code == 200
    created = _tx(client, client_name="Toko Sembako", description="Pembayaran sesuatu")
    assert created.status_code == 201, created.text
    assert created.json()["classification"]["requires_clarification"] is True


def test_fr14_question_names_client_amount_and_closed_options(client):
    _auth(client)
    assert _profile(client).status_code == 200
    created = _tx(
        client, client_name="PT Contoh", description="Pembayaran sesuatu", amount_idr=12_500_000
    )
    assert created.status_code == 201, created.text
    response = client.get(f"/api/v1/transactions/{created.json()['id']}/clarification")
    assert response.status_code == 200, response.text
    question = response.json()
    assert "PT Contoh" in question["question"]
    assert "12.500.000" in question["question"]
    assert {option["value"] for option in question["options"]} == {
        "usaha",
        "pekerjaan_bebas",
        "already_final",
        "non_object",
    }
    assert all(option["label"] for option in question["options"])


@pytest.mark.parametrize(
    ("status", "aggregation"),
    [("unmarried", False), ("separate", True), ("joint", False), ("unknown", False)],
)
def test_fr48_spouse_status_sets_aggregation_and_preserves_blanks(client, status, aggregation):
    _auth(client)
    response = _profile(
        client,
        spouse_tax_status=status,
        spouse_aggregation_active=not aggregation,
        is_new_taxpayer_current_year=False,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["spouse_tax_status"] == status
    assert body["spouse_aggregation_active"] is aggregation
    for owner in ("user", "spouse"):
        for category in ("usaha", "pekerjaan_bebas", "already_final"):
            assert body[f"prior_{owner}_{category}_idr"] is None


def test_fr49_guidance_is_profile_applicable_cited_and_disclaimed(client):
    _auth(client)
    assert _profile(client, spouse_tax_status="separate").status_code == 200
    response = client.get("/api/v1/guidance")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ruleset_id"] and body["effective_date"]
    assert "DOKUMEN KERJA" in body["disclaimer"]
    assert body["items"]
    assert all(item["id"] and item["text"] and item["citation"] for item in body["items"])
    assert any(
        "pasangan" in item["text"].lower() or "PH/MT" in item["text"] for item in body["items"]
    )


def test_reclassify_reads_rule_threshold_once(client, monkeypatch):
    """A multi-row reclassify loads T_rule once for the whole request."""
    _auth(client)
    assert _profile(client).status_code == 200
    first = _tx(client, description="Penjualan sembako", invoice_no="INV-ONCE-A").json()
    second = _tx(client, description="Jasa penerjemahan", invoice_no="INV-ONCE-B").json()
    calls = {"n": 0}
    from app.services import transactions as transaction_service

    real = transaction_service.get_config

    def wrapped(db, key):
        if key == "T_rule":
            calls["n"] += 1
        return real(db, key)

    monkeypatch.setattr(transaction_service, "get_config", wrapped)
    response = client.post(
        "/api/v1/transactions/reclassify",
        json={"transaction_ids": [first["id"], second["id"]]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["reclassified_count"] == 2
    assert calls["n"] == 1


def _stored_snapshot_state(user_id: str):
    db = SessionLocal()
    try:
        profile = db.scalar(select(Profile).where(Profile.user_id == user_id))
        rows = db.scalars(
            select(MonthSnapshot)
            .where(MonthSnapshot.profile_id == profile.id)
            .order_by(MonthSnapshot.month_key, MonthSnapshot.version)
        ).all()
        stored = tuple((row.id, row.month_key, row.version, row.status) for row in rows)
        return profile.snapshot_checked_through, stored
    finally:
        db.close()


def test_fr49_guidance_does_not_persist_snapshot_refresh(client):
    """FR-49: GET /guidance must not advance snapshot_checked_through or write snapshots."""
    with freeze_today_jakarta(date(2026, 11, 2)):
        _auth(client)
        assert _profile(client).status_code == 200
        user_id = client.get("/api/v1/auth/me").json()["user_id"]
    before_through, before_rows = _stored_snapshot_state(user_id)
    assert before_through == date(2026, 11, 2)
    assert before_rows
    with freeze_today_jakarta(date(2026, 11, 3)):
        response = client.get("/api/v1/guidance")
        assert response.status_code == 200, response.text
    after_through, after_rows = _stored_snapshot_state(user_id)
    assert after_through == before_through
    assert after_rows == before_rows


@pytest.mark.parametrize(("amount", "warning"), [(3_839_999_999, False), (3_840_000_000, True)])
def test_tc_cap_warning_exact_integer_boundary(client, amount, warning):
    """FR-50: the 80 percent notice does not itself make next year ineligible."""
    with freeze_today_jakarta(date(2026, 11, 2)):
        _auth(client)
        assert _profile(client).status_code == 200
        response = _tx(client, amount_idr=amount)
        assert response.status_code == 201, response.text
        monitoring = client.get("/api/v1/tax/dashboard?tax_year=2026").json()["thresholds"][
            "monitoring_current_year_cap_4_8m"
        ]
        assert monitoring["cap_warning_percent"] == 80
        assert monitoring["cap_warning"] is warning
        assert monitoring["next_year_ineligible"] is False


@pytest.mark.parametrize(
    ("description", "rule_id"),
    [
        ("bunga deposito", "non_object.deposit"),
        ("bunga bank", "non_object.bank"),
        ("bunga tabungan", "non_object.savings"),
        ("dividen", "non_object.dividend"),
        ("hadiah undian", "non_object.prize"),
    ],
)
def test_passive_interest_dividend_and_lottery_are_non_object(description, rule_id):
    """FR-11: deposit interest, savings interest, dividends and lottery prizes are non_object.

    The owner decided this on 2026-11-23. The stored id names ``non_object``.
    These phrases are not the 0,5% usaha base.
    """
    category, got_rule, _, needs_clarification, _ = classify(description)
    assert needs_clarification is False
    assert (category, got_rule) == ("non_object", rule_id)
    assert not got_rule.startswith("already_final")


def test_fr10_business_rent_remains_final():
    assert classify("sewa tanah")[0] == "already_final"


_CAP_PROBE = 4_800_000_001


@pytest.mark.parametrize(
    ("description", "category", "rule_id", "in_base", "in_cap"),
    [
        ("penjualan barang", "usaha", "usaha.sale", True, True),
        ("jasa penerjemahan", "pekerjaan_bebas", "pekerjaan_bebas.translation", False, True),
        ("sewa tanah", "already_final", "already_final.rent", False, True),
        ("sewa bangunan", "already_final", "already_final.rent_building", False, True),
        ("bunga deposito", "non_object", "non_object.deposit", False, False),
        ("bunga bank", "non_object", "non_object.bank", False, False),
        ("bunga tabungan", "non_object", "non_object.savings", False, False),
        ("dividen", "non_object", "non_object.dividend", False, False),
        ("hadiah undian", "non_object", "non_object.prize", False, False),
        ("hadiah lomba", None, "", False, False),
        ("pemberian orang tua", "non_object", "non_object.parents", False, False),
    ],
)
def test_income_matrix_pins_today_category_base_and_cap(
    description, category, rule_id, in_base, in_cap, ruleset
):
    """Pin the category, the 0,5% base, and the Rp 4,8 miliar test.

    Deposit interest, savings interest, dividends and ``hadiah undian`` are
    ``non_object``: out of the base and out of the test. Land or building
    rent stays ``already_final`` and stays in the test. ``hadiah lomba`` is
    a competition prize, not a lottery, so it stays clarification and is not
    passed to the engine. ``hadiah undian`` is the only prize phrase that
    classifies.
    """
    got_category, got_rule, _, needs_clarification, _ = classify(description)
    profile = TaxProfile(is_new_taxpayer_current_year=True)
    if category is None:
        assert needs_clarification is True
        assert got_rule == ""
        assert got_category == "usaha"
        snapshot = compute([], profile, ruleset, "2026-11-01")
    else:
        assert needs_clarification is False
        assert (got_category, got_rule) == (category, rule_id)
        snapshot = compute(
            [
                Transaction(
                    id="row",
                    amount=_CAP_PROBE,
                    date="2026-06-15",
                    category=got_category,
                )
            ],
            profile,
            ruleset,
            "2026-11-01",
        )
        totals = {
            "usaha": snapshot.ytd_usaha_omzet,
            "pekerjaan_bebas": snapshot.pekerjaan_bebas_total,
            "already_final": snapshot.already_final_total,
            "non_object": snapshot.non_object_total,
        }
        assert totals[category] == _CAP_PROBE
        assert all(amount == 0 for name, amount in totals.items() if name != category)
    assert (snapshot.ytd_usaha_omzet == _CAP_PROBE) is in_base
    assert (snapshot.final_tax > 0) is in_base
    assert snapshot.current_year_crossed_cap is in_cap


@pytest.mark.parametrize(
    "description",
    [
        "Pembayaran les privat dari orang tua murid",
        "Jasa konsultasi dari pemberi kerja lama",
        "Penjualan pulsa dan top up e-wallet pelanggan",
        "Jual kaos, refund 1 pcs",
        "Sewa ruko dan pembatalan",
        "Dividen dan sewa tanah",
        "Bunga deposito, penjualan kaos",
        "Hadiah undian sewa bangunan",
        "Bunga tabungan dan jasa penerjemahan",
        "Bunga bank dan kos",
        "Sewa tanah dan gaji",
        # ``penjual`` is an ordinary sale word beside a refund phrase.
        "Pembatalan order, uang dikembalikan penjual",
    ],
)
def test_decisive_match_does_not_override_a_different_category(description):
    """A decisive phrase next to a phrase for another category asks instead of picking."""
    category, _, _, needs_clarification, _ = classify(description)
    assert needs_clarification is True
    assert category == "usaha"


@pytest.mark.parametrize(
    "description",
    ["Jual sepeda bekas, bukan usaha", "Penjualan, sudah final", "Honor narasumber, PPh final"],
)
def test_explicit_statement_still_settles_the_category(description):
    """``bukan usaha`` and a final-tax marker name the answer, so they are not second-guessed."""
    assert classify(description)[3] is False


@pytest.mark.parametrize("description", ["bunga", "Bunga", "hadiah", "tabungan"])
def test_bare_interest_savings_or_prize_words_stay_clarification(description):
    """A lone bunga can be lending-business interest. hadiah or tabungan alone is not this rule."""
    category, rule_id, _, needs_clarification, _ = classify(description)
    assert needs_clarification is True
    assert rule_id == ""
    assert category == "usaha"


@pytest.mark.parametrize(
    ("description", "category", "rule_id"),
    [
        ("sewa tanah", "already_final", "already_final.rent"),
        ("Sewa kamar kos dari penghuni", "already_final", "already_final.kos"),
        (
            "Proyek renovasi dapur, bukti potong PPh final",
            "already_final",
            "already_final.marker_pph",
        ),
        ("penjualan barang", "usaha", "usaha.sale"),
        ("Jasa penerjemahan jurnal", "pekerjaan_bebas", "pekerjaan_bebas.translation"),
        ("Dividen dan gaji bulan ini", "non_object", "non_object.dividend"),
    ],
)
def test_unrelated_categories_stay_put(description, category, rule_id):
    """Rent, kos, a final-tax marker, a shop sale and a Pasal 56 phrase keep their categories."""
    got_category, got_rule, _, needs_clarification, _ = classify(description)
    assert needs_clarification is False
    assert (got_category, got_rule) == (category, rule_id)


def test_usaha_plus_personal_dividend_stays_under_the_cap(ruleset):
    """Usaha of Rp 4_750_000_000 plus a personal dividend of Rp 100_000_000.

    The owner's worked example (2026-11-23): the test counts Rp 4_750_000_000.
    The old ``already_final`` mapping would count Rp 4_850_000_000 and flag the
    cap. The dividend is also outside the 0,5% base, so tax matches usaha alone.
    """
    category, rule_id, _, needs_clarification, _ = classify("dividen")
    assert needs_clarification is False
    assert category == "non_object"
    assert rule_id == "non_object.dividend"
    profile = TaxProfile(is_new_taxpayer_current_year=True)
    usaha = Transaction(id="usaha", amount=4_750_000_000, date="2026-06-01", category="usaha")
    dividend = Transaction(id="dividen", amount=100_000_000, date="2026-06-02", category=category)
    as_of = "2026-11-01"
    usaha_only = compute([usaha], profile, ruleset, as_of)
    snapshot = compute([usaha, dividend], profile, ruleset, as_of)
    counted = (
        snapshot.ytd_usaha_omzet + snapshot.pekerjaan_bebas_total + snapshot.already_final_total
    )
    assert snapshot.ytd_usaha_omzet == 4_750_000_000
    assert snapshot.non_object_total == 100_000_000
    assert snapshot.already_final_total == 0
    assert counted == 4_750_000_000
    assert counted <= ruleset.eligibility_cap_idr
    assert counted + 100_000_000 > ruleset.eligibility_cap_idr
    assert snapshot.current_year_crossed_cap is False
    assert snapshot.final_tax == usaha_only.final_tax
    assert usaha_only.final_tax > 0
    counted_as_final = compute(
        [
            usaha,
            Transaction(
                id="dividen",
                amount=100_000_000,
                date="2026-06-02",
                category="already_final",
            ),
        ],
        profile,
        ruleset,
        as_of,
    )
    assert counted_as_final.current_year_crossed_cap is True
    assert counted_as_final.already_final_total == 100_000_000


@pytest.mark.parametrize(
    "description", ["dijual online", "menjual kue", "Penjual sayur", "Dijual lewat Shopee"]
)
def test_inflected_roots_match_usaha(description):
    assert classify(description)[0] == "usaha"
    assert classify(description)[3] is False


@pytest.mark.parametrize("description", ["terjualah", "tokoferol", "dijualah"])
def test_unrelated_words_around_a_root_do_not_match(description):
    assert classify(description)[3] is True


def _clarification_question(client, **overrides):
    _auth(client)
    assert _profile(client).status_code == 200
    created = _tx(client, description="zzz tidak dikenal", **overrides)
    assert created.status_code == 201, created.text
    response = client.get(f"/api/v1/transactions/{created.json()['id']}/clarification")
    assert response.status_code == 200, response.text
    return response.json()["question"]


def test_clarification_question_leaves_a_comma_in_the_client_name_alone(client):
    question = _clarification_question(
        client, client_name="PT Maju, Tbk", amount_idr=12_500_000, invoice_no="INV-C-1"
    )
    assert question.startswith("Penghasilan dari PT Maju, Tbk sebesar Rp 12.500.000: ")


def test_clarification_question_omits_the_client_clause_when_it_is_empty(client):
    _auth(client)
    assert _profile(client).status_code == 200
    created = _tx(client, description="zzz tidak dikenal", invoice_no="INV-C-2")
    assert created.status_code == 201, created.text
    with SessionLocal() as db:
        from app.models import Transaction as TransactionRow

        row = db.get(TransactionRow, created.json()["id"])
        row.client_name = ""
        db.commit()
    response = client.get(f"/api/v1/transactions/{created.json()['id']}/clarification")
    assert response.json()["question"].startswith("Penghasilan sebesar Rp 12.500.000: ")


def test_every_guidance_condition_can_be_produced():
    """A condition no profile can produce is dead guidance that nobody would ever see."""
    import json
    from pathlib import Path

    path = Path(__file__).parent.parent / "app" / "guidance" / "pp20-2026-academic-1.json"
    conditions = {item["condition"] for item in json.loads(path.read_text(encoding="utf-8"))}
    producible = {
        "always",
        "unmarried",
        "separate",
        "joint",
        "unknown",
        "article17",
        "article17_unknown",
        "company",
        "company_unknown",
        "new_taxpayer_unknown",
        "cap_warning",
    }
    assert conditions <= producible


@pytest.mark.parametrize(
    ("description", "category", "rule_id"),
    [
        ("Bunga deposito dipotong PPh final", "non_object", "non_object.deposit"),
        ("Bunga bank sudah final", "non_object", "non_object.bank"),
        ("Bunga tabungan bertanda final", "non_object", "non_object.savings"),
        ("Dividen pemotongan final", "non_object", "non_object.dividend"),
        ("Hadiah undian dipotong final", "non_object", "non_object.prize"),
        ("Sewa tanah dipotong PPh final", "already_final", "already_final.rent"),
        ("Sewa bangunan sudah final", "already_final", "already_final.rent_building"),
        ("Sewa kamar kos bertanda final", "already_final", "already_final.kos"),
    ],
)
def test_passive_and_rent_sources_outrank_generic_final_withholding_markers(
    description, category, rule_id
):
    """Generic withholding wording does not override passive-income or rent source rules."""
    got_category, got_rule, _, needs_clarification, _ = classify(description)
    assert needs_clarification is False
    assert (got_category, got_rule) == (category, rule_id)


@pytest.mark.parametrize(
    "description",
    [
        "Bunga deposito dan penjualan kaos, dipotong PPh final",
        "Dividen dan jasa penerjemahan, PPh final",
        "Hadiah undian dan sewa tanah, dipotong PPh final",
        "Sewa tanah dan penjualan kaos, PPh final",
        "Sewa tanah dan gaji, dipotong PPh final",
        "Sewa tanah pribadi (bukan usaha), dipotong PPh final",
        "Dividen bukan usaha dan sewa tanah, dipotong PPh final",
    ],
)
def test_passive_or_rent_with_withholding_and_other_source_still_clarifies(description):
    """Generic withholding or bukan usaha wording cannot silence a specific source conflict."""
    category, _, _, needs_clarification, _ = classify(description)
    assert needs_clarification is True
    assert category == "usaha"


def test_withholding_worded_dividend_with_4_75b_usaha_stays_under_cap(ruleset):
    """Worked cap check: Rp 100M dividend with PPh final wording stays non_object and under cap."""
    category, rule_id, _, needs_clarification, _ = classify(
        "Dividen pemegang saham dipotong PPh final"
    )
    assert needs_clarification is False
    assert (category, rule_id) == ("non_object", "non_object.dividend")
    profile = TaxProfile(is_new_taxpayer_current_year=True)
    snapshot = compute(
        [
            Transaction(id="usaha", amount=4_750_000_000, date="2026-06-01", category="usaha"),
            Transaction(id="dividen", amount=100_000_000, date="2026-06-02", category=category),
        ],
        profile,
        ruleset,
        "2026-11-01",
    )
    counted = (
        snapshot.ytd_usaha_omzet + snapshot.pekerjaan_bebas_total + snapshot.already_final_total
    )
    assert counted == 4_750_000_000
    assert snapshot.non_object_total == 100_000_000
    assert snapshot.current_year_crossed_cap is False


def test_separate_final_income_guidance_explains_existing_rows_and_dividend_rules(client):
    _auth(client)
    assert _profile(client).status_code == 200
    items = client.get("/api/v1/guidance").json()["items"]
    item = next(entry for entry in items if entry["id"] == "separate_final_income")
    assert "aturan PPh masing-masing" in item["text"]
    assert "Klasifikasi ulang" in item["text"]
    assert (
        "dividen yang diterima sebagai pemegang saham, dan hadiah undian dikenai PPh final"
        not in item["text"]
    )
