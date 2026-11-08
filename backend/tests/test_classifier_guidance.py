"""Classifier, clarification, onboarding and guidance contracts (FR-11, FR-14, FR-48)."""

from datetime import date

import pytest
from test_tax_crud_trace_quota import _auth, _profile, _tx

from app.classify.rules import RULES, classify
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
        ("Pembatalan order, uang dikembalikan penjual", "non_object"),
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
