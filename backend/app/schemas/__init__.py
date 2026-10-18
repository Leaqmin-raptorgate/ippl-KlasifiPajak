"""Request and response shapes for the API layer.

Amounts are strict integers. Pydantic will not be allowed to coerce ``"500"``,
``500.0`` or ``Decimal("500")`` into rupiah, because a float that reaches the
tax path produces a wrong figure that still looks plausible (invariant 5).
"""

from app.schemas.ruleset import RulesetOut
from app.schemas.snapshot import MonthOut, SnapshotIn, SnapshotOut

__all__ = [
    "MonthOut",
    "RulesetOut",
    "SnapshotIn",
    "SnapshotOut",
]
