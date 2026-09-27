"""Load a ruleset JSON file into a Ruleset."""

import json
from pathlib import Path

from klasifipajak.engine.types import Ruleset


def default_ruleset_path() -> Path:
    """Path of the academic PP 20/2026 ruleset shipped with this package."""
    return Path(__file__).with_name("pp20_2026.json")


def load_ruleset(path: Path | None = None) -> Ruleset:
    """Read a ruleset file. Missing keys are an error, not a silent default."""
    ruleset_path = default_ruleset_path() if path is None else Path(path)
    data = json.loads(ruleset_path.read_text(encoding="utf-8"))
    required = (
        "ruleset_id",
        "as_of_date",
        "final_rate_numerator",
        "final_rate_denominator",
        "exemption_band_idr",
        "eligibility_cap_idr",
        "ineligible_when",
        "kap_kjs",
    )
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"ruleset missing keys: {missing}")
    return Ruleset(
        ruleset_id=data["ruleset_id"],
        as_of_date=data["as_of_date"],
        final_rate_numerator=data["final_rate_numerator"],
        final_rate_denominator=data["final_rate_denominator"],
        exemption_band_idr=data["exemption_band_idr"],
        eligibility_cap_idr=data["eligibility_cap_idr"],
        ineligible_when=data["ineligible_when"],
        kap_kjs=data["kap_kjs"],
    )
