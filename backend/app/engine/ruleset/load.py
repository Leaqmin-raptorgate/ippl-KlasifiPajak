"""Load a ruleset JSON file into a Ruleset."""

import json
from pathlib import Path

from app.engine.types import Ruleset

_ROUNDING_RULES = frozenset({"floor", "round_half_up"})


def default_ruleset_path() -> Path:
    """Path of the academic PP 20/2026 ruleset shipped with this package."""
    return Path(__file__).with_name("pp20_2026.json")


def load_ruleset(path: Path | None = None) -> Ruleset:
    """Read a ruleset file. Missing keys are an error, not a silent default."""
    ruleset_path = default_ruleset_path() if path is None else Path(path)
    data = json.loads(ruleset_path.read_text(encoding="utf-8"))
    required = (
        "ruleset_id",
        "tax_year",
        "effective_date",
        "final_rate_numerator",
        "final_rate_denominator",
        "exemption_band_idr",
        "eligibility_cap_idr",
        "ineligible_when",
        "kap_kjs",
        "spouse_in_band",
        "spouse_in_cap",
    )
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"ruleset missing keys: {missing}")
    rounding_rule = data.get("rounding_rule", "floor")
    if rounding_rule not in _ROUNDING_RULES:
        raise ValueError(f"rounding_rule must be one of {sorted(_ROUNDING_RULES)}")
    for key in ("spouse_in_band", "spouse_in_cap"):
        if not isinstance(data[key], bool):
            raise ValueError(f"{key} must be true or false")
    rate_str = data.get("rate_label") or "{}/{}".format(
        data["final_rate_numerator"], data["final_rate_denominator"]
    )
    return Ruleset(
        ruleset_id=data["ruleset_id"],
        tax_year=data["tax_year"],
        effective_date=data["effective_date"],
        final_rate_numerator=data["final_rate_numerator"],
        final_rate_denominator=data["final_rate_denominator"],
        exemption_band_idr=data["exemption_band_idr"],
        eligibility_cap_idr=data["eligibility_cap_idr"],
        ineligible_when=data["ineligible_when"],
        kap_kjs=data["kap_kjs"],
        rounding_rule=rounding_rule,
        spouse_in_band=data["spouse_in_band"],
        spouse_in_cap=data["spouse_in_cap"],
        rate_str=rate_str,
        quota_ai_classification=data.get("quota_ai_classification", 200),
        quota_assistant_chat=data.get("quota_assistant_chat", 200),
    )
