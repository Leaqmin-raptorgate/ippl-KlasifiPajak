"""Bagian A: the stateless engine on the loopback interface.

No session, no database. Mounted only for development and test (API v1.2.2
section 3). Thin by rule: validate, call one service, return.
"""

from fastapi import APIRouter

from app.config.settings import Settings
from app.schemas.ruleset import RulesetOut
from app.schemas.snapshot import SnapshotIn, SnapshotOut
from app.services.snapshot import active_ruleset, build_snapshot

router = APIRouter()
_settings = Settings()


def _ruleset_out() -> RulesetOut:
    ruleset = active_ruleset(_settings.ruleset_path)
    return RulesetOut(
        ruleset_id=ruleset.ruleset_id,
        tax_year=ruleset.tax_year,
        effective_date=ruleset.effective_date,
        rate_numerator=ruleset.final_rate_numerator,
        rate_denominator=ruleset.final_rate_denominator,
        rate_str=ruleset.rate_str,
        free_band_idr=ruleset.exemption_band_idr,
        gross_cap_idr=ruleset.eligibility_cap_idr,
        rounding_rule=ruleset.rounding_rule,
        spouse_in_band=ruleset.spouse_in_band,
        spouse_in_cap=ruleset.spouse_in_cap,
        kap_kjs=ruleset.kap_kjs,
    )


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. API v1.2.2 section 3.1 fixes the body."""
    return {"status": "ok"}


@router.get("/ruleset", response_model=RulesetOut)
def ruleset() -> RulesetOut:
    """Serve the active ruleset so no client inlines a rate or a ceiling."""
    return _ruleset_out()


@router.post("/snapshot", response_model=SnapshotOut)
def snapshot(request: SnapshotIn) -> SnapshotOut:
    """Compute one snapshot. Stateless: no transaction is persisted."""
    return build_snapshot(request, active_ruleset(_settings.ruleset_path))
