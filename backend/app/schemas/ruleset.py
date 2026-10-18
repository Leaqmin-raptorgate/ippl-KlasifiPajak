"""Response shape for the active ruleset.

Field names follow KlasifiPajak API v1.2.2 section 3.2. The frontend never
inlines a rate or a ceiling.
"""

from pydantic import BaseModel, ConfigDict, StrictInt


class RulesetOut(BaseModel):
    """The ruleset exactly as the contract names it."""

    model_config = ConfigDict(frozen=True)

    ruleset_id: str
    tax_year: StrictInt
    effective_date: str
    rate_numerator: StrictInt
    rate_denominator: StrictInt
    rate_str: str
    free_band_idr: StrictInt
    gross_cap_idr: StrictInt
    rounding_rule: str
    spouse_in_band: bool
    spouse_in_cap: bool
    kap_kjs: str
