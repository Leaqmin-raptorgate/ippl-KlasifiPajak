"""Ruleset files. Numbers live here, not in the engine.

This package ships tax year 2026 only (`pp20-2026-academic-1`). A different
tax year needs its own ruleset rule. Spouse turnover for 2026 follows
PP 20/2026 Pasal 58 ayat (2) and ayat (3). The Penjelasan to ayat (2)
includes a minor child's turnover in the husband-and-wife combination.
Ayat (3) also includes a single-person company founded by the couple.
Neither amount is an engine input. `spouse_in_cap` and `spouse_in_band`
stay ruleset data, and the Rp500m band is unchanged.

`spouse_tax_status` maps to `spouse_aggregation_active` for 2026 as follows.
`unmarried` is false (no spouse). `separate` (PH or MT) is true under
Pasal 58(2). `joint` is false as a product assumption: the couple uses one
account, so the spouse's turnover is already in it. `unknown` is false, the
result may be inexact, and that choice is not signed off. When a profile
save includes `spouse_tax_status`, the stored flag is true only for
`separate`. Omitting the status stores the flag that was sent.
"""

from app.engine.ruleset.load import load_ruleset

__all__ = ["load_ruleset"]
