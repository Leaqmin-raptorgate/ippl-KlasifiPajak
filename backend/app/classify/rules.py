"""Keyword rules used before any model call (FR-11, FR-14).

Data, not code: each row names a category, the phrase that selects it, and the
rule id recorded on the classification event. A miss goes to clarification
rather than a guess.

Matching, in order:

1. The first matching ``decisive`` rule wins outright. These are signals that
   settle the category whatever else the text says: a final-tax marker, an
   own-money or refund flow, employment income, land or building rent, and the
   professions Pasal 56(4) names explicitly (creator, affiliate, broker).
2. Otherwise the non-``weak`` matches are used (weak phrases, such as ``toko``
   or ``fee``, often name the client or a side cost rather than the income).
   If none, the weak matches are used.
3. If those matches point to more than one category, the row is mixed and goes
   to clarification (FR-14). Otherwise the first of them wins.

Rule changes on 2026-11-08 were tuned on the dev label set only; see
``outputs/label-review-20261108/HELDOUT_FREEZE.md`` beside the repository.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    """One keyword rule.

    ``confidence`` is how sure a match of this phrase is, from 0 to 1.
    It is not a tax rate, and the value on each row is not retuned here.
    """

    id: str
    category: str
    phrase: str
    citation: str = ""
    confidence: float = 0.9
    decisive: bool = False
    weak: bool = False


def _d(rule_id: str, category: str, phrase: str) -> Rule:
    return Rule(rule_id, category, phrase, decisive=True)


#: Ordered: decisive rules first, then ordinary and weak rules.
RULES: tuple[Rule, ...] = (
    # Final-tax markers on a bukti potong.
    _d("already_final.marker_pph", "already_final", "pph final"),
    _d("already_final.marker_tagged", "already_final", "bertanda final"),
    _d("already_final.marker_done", "already_final", "sudah final"),
    _d("already_final.marker_withheld", "already_final", "pemotongan final"),
    _d("already_final.marker_cut", "already_final", "dipotong final"),
    # Own money, refunds, family, employment and passive income.
    _d("non_object.transfer", "non_object", "transfer antar rekening"),
    _d("non_object.own_account", "non_object", "rekening sendiri"),
    _d("non_object.own_wallet", "non_object", "dompet pribadi"),
    _d("non_object.move_balance", "non_object", "pindah saldo"),
    _d("non_object.topup_wallet", "non_object", "top up"),
    _d("non_object.topup", "non_object", "setor modal"),
    _d("non_object.cash_deposit", "non_object", "setor tunai"),
    _d("non_object.refund", "non_object", "pengembalian dana"),
    _d("non_object.return", "non_object", "pengembalian"),
    _d("non_object.returned", "non_object", "dikembalikan"),
    _d("non_object.cancel", "non_object", "pembatalan"),
    _d("non_object.refund2", "non_object", "refund"),
    _d("non_object.not_business", "non_object", "bukan usaha"),
    _d("non_object.parents", "non_object", "orang tua"),
    _d("non_object.crypto", "non_object", "kripto"),
    _d("non_object.btc", "non_object", "btc"),
    _d("already_final.deposit", "non_object", "bunga deposito"),
    _d("already_final.bank", "non_object", "bunga bank"),
    _d("already_final.dividend", "non_object", "dividen"),
    _d("already_final.prize", "non_object", "hadiah undian"),
    _d("non_object.salary", "non_object", "gaji"),
    _d("non_object.severance", "non_object", "pesangon"),
    _d("non_object.employer", "non_object", "pemberi kerja"),
    _d("non_object.social_aid", "non_object", "bantuan sosial"),
    _d("non_object.bansos", "non_object", "bansos"),
    _d("non_object.loan", "non_object", "pinjaman"),
    _d("non_object.inheritance", "non_object", "warisan"),
    # Land and building rent, final under UU PPh Pasal 4(2).
    _d("already_final.rent", "already_final", "sewa tanah"),
    _d("already_final.rent_land", "already_final", "sewa lahan"),
    _d("already_final.rent_building", "already_final", "sewa bangunan"),
    _d("already_final.rent_house", "already_final", "sewa rumah"),
    _d("already_final.rent_shophouse", "already_final", "sewa ruko"),
    # Kos rooms are building rent (developer decision 2026-11-08).
    _d("already_final.kos", "already_final", "kos"),
    # Professions Pasal 56(4) names explicitly.
    _d("pekerjaan_bebas.endorsement", "pekerjaan_bebas", "endorsement"),
    _d("pekerjaan_bebas.endorse", "pekerjaan_bebas", "endorse"),
    _d("pekerjaan_bebas.influencer", "pekerjaan_bebas", "influencer"),
    _d("pekerjaan_bebas.adsense", "pekerjaan_bebas", "adsense"),
    _d("pekerjaan_bebas.mlm", "pekerjaan_bebas", "distributor pemasaran berjenjang"),
    _d("pekerjaan_bebas.affiliate", "pekerjaan_bebas", "affiliate"),
    _d("pekerjaan_bebas.broker", "pekerjaan_bebas", "perantara"),
    # Ordinary profession signals.
    Rule("pekerjaan_bebas.translator", "pekerjaan_bebas", "penerjemah"),
    Rule("pekerjaan_bebas.translation", "pekerjaan_bebas", "penerjemahan"),
    Rule("pekerjaan_bebas.programming", "pekerjaan_bebas", "jasa pemrograman"),
    Rule("pekerjaan_bebas.website", "pekerjaan_bebas", "website"),
    Rule("pekerjaan_bebas.app", "pekerjaan_bebas", "pembuatan aplikasi"),
    Rule("pekerjaan_bebas.bookkeeping", "pekerjaan_bebas", "pembukuan"),
    Rule("pekerjaan_bebas.editing", "pekerjaan_bebas", "editing"),
    Rule("pekerjaan_bebas.video", "pekerjaan_bebas", "produksi video"),
    Rule("pekerjaan_bebas.photographer", "pekerjaan_bebas", "fotografer"),
    Rule("pekerjaan_bebas.honorarium", "pekerjaan_bebas", "honorarium"),
    Rule("pekerjaan_bebas.honor", "pekerjaan_bebas", "honor"),
    Rule("pekerjaan_bebas.consult", "pekerjaan_bebas", "konsultasi"),
    Rule("pekerjaan_bebas.design", "pekerjaan_bebas", "jasa desain"),
    Rule("pekerjaan_bebas.desain", "pekerjaan_bebas", "desain"),
    Rule("pekerjaan_bebas.speaker", "pekerjaan_bebas", "narasumber"),
    Rule("pekerjaan_bebas.mentoring", "pekerjaan_bebas", "mentoring"),
    Rule("pekerjaan_bebas.workshop", "pekerjaan_bebas", "workshop"),
    Rule("pekerjaan_bebas.teach", "pekerjaan_bebas", "mengajar"),
    Rule("pekerjaan_bebas.teach_slang", "pekerjaan_bebas", "ngajar"),
    Rule("pekerjaan_bebas.tutoring", "pekerjaan_bebas", "les"),
    Rule("pekerjaan_bebas.freelance", "pekerjaan_bebas", "freelance"),
    # Goods and trade services (usaha).
    Rule("usaha.reseller", "usaha", "reseller"),
    Rule("usaha.workshop", "usaha", "bengkel"),
    Rule("usaha.sale", "usaha", "penjualan"),
    Rule("usaha.sale2", "usaha", "jual"),
    Rule("usaha.jualan", "usaha", "jualan"),
    Rule("usaha.order", "usaha", "order"),
    Rule("usaha.order_slang", "usaha", "orderan"),
    Rule("usaha.order_id", "usaha", "pesanan"),
    Rule("usaha.procurement", "usaha", "pengadaan"),
    Rule("usaha.tokopedia", "usaha", "tokopedia"),
    Rule("usaha.shopee", "usaha", "shopee"),
    Rule("usaha.grocery", "usaha", "sembako"),
    Rule("usaha.catering", "usaha", "katering"),
    Rule("usaha.boutique", "usaha", "butik"),
    Rule("usaha.service", "usaha", "servis"),
    Rule("usaha.install", "usaha", "pemasangan"),
    Rule("usaha.repair", "usaha", "perbaikan"),
    Rule("usaha.screenprint", "usaha", "sablon"),
    Rule("usaha.paint", "usaha", "ngecat"),
    Rule("usaha.ride_hailing", "usaha", "ojol"),
    # Weak: often the client's name or a side cost, not the income itself.
    Rule("usaha.shop", "usaha", "toko", weak=True),
    Rule("usaha.product", "usaha", "produk", weak=True),
    Rule("pekerjaan_bebas.fee", "pekerjaan_bebas", "fee", weak=True),
)


_COMPILED_RULES = tuple(
    (rule, re.compile(r"(?<!\w)" + re.escape(rule.phrase) + r"(?!\w)", re.IGNORECASE))
    for rule in RULES
)

_CLARIFY = ("usaha", "", 0.0, True, "")


def classify(text: str, threshold: float = 0.8) -> tuple[str, str, float, bool, str]:
    """Classify a description; mixed or unknown rows go to clarification (FR-11, FR-14).

    ``threshold`` is the minimum rule confidence that may be applied. A match
    below it goes to clarification. The default is 0.8 and is not retuned here.
    """
    matches = [rule for rule, pattern in _COMPILED_RULES if pattern.search(text)]
    if not matches:
        return _CLARIFY
    decisive = [rule for rule in matches if rule.decisive]
    if decisive:
        chosen = decisive[0]
    else:
        pool = [rule for rule in matches if not rule.weak] or matches
        if len({rule.category for rule in pool}) > 1:
            return _CLARIFY
        chosen = pool[0]
    if chosen.confidence < threshold:
        return _CLARIFY
    return chosen.category, chosen.id, chosen.confidence, False, chosen.citation
