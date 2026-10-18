"""Keyword rules used before any model call.

Data, not code: each row names a category, the phrases that select it, and the
rule id recorded on the classification event. The table is deliberately small;
a miss goes to clarification rather than a guessed model call in this slice.
"""

from dataclasses import dataclass

DEFAULT_CONFIDENCE = 0.9


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    phrase: str
    citation: str = ""


#: Ordered: the first matching phrase wins.
RULES: tuple[Rule, ...] = (
    Rule("non_object.transfer", "non_object", "transfer antar rekening"),
    Rule("non_object.topup", "non_object", "setor modal"),
    Rule("non_object.refund", "non_object", "pengembalian dana"),
    Rule("non_object.refund2", "non_object", "refund"),
    Rule("already_final.deposit", "already_final", "bunga deposito"),
    Rule("already_final.bank", "already_final", "bunga bank"),
    Rule("already_final.dividend", "already_final", "dividen"),
    Rule("already_final.rent", "already_final", "sewa tanah"),
    Rule("already_final.prize", "already_final", "hadiah undian"),
    Rule("pekerjaan_bebas.honor", "pekerjaan_bebas", "honor"),
    Rule("pekerjaan_bebas.fee", "pekerjaan_bebas", "fee"),
    Rule("pekerjaan_bebas.consult", "pekerjaan_bebas", "konsultasi"),
    Rule("pekerjaan_bebas.design", "pekerjaan_bebas", "jasa desain"),
    Rule("pekerjaan_bebas.speaker", "pekerjaan_bebas", "narasumber"),
    Rule("pekerjaan_bebas.freelance", "pekerjaan_bebas", "freelance"),
    Rule("usaha.sale", "usaha", "penjualan"),
    Rule("usaha.sale2", "usaha", "jual"),
    Rule("usaha.shop", "usaha", "toko"),
    Rule("usaha.grocery", "usaha", "sembako"),
    Rule("usaha.catering", "usaha", "katering"),
    Rule("usaha.boutique", "usaha", "butik"),
    Rule("usaha.service", "usaha", "servis"),
    Rule("usaha.product", "usaha", "produk"),
)


def classify(text: str) -> tuple[str, str, float, bool, str]:
    """Return category, rule id, confidence, clarification flag, citation.

    A row with no matching phrase is stored as ``usaha`` with zero confidence
    and ``requires_clarification`` set. The model fallback is not part of this
    slice, so the user answers the closed question instead.
    """
    haystack = text.casefold()
    for rule in RULES:
        if rule.phrase in haystack:
            return rule.category, rule.id, DEFAULT_CONFIDENCE, False, rule.citation
    return "usaha", "", 0.0, True, ""
