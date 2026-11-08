"""Static, cited guidance selected for a taxpayer (FR-49)."""

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.engine import Ruleset
from app.models import User
from app.services.dashboard import dashboard
from app.services.profile import find_profile
from app.services.snapshot import DISCLAIMER


@lru_cache(maxsize=16)
def _load_guidance_items(ruleset_id: str) -> list[dict]:
    path = Path(__file__).parent.parent / "guidance" / f"{ruleset_id}.json"
    if not path.is_file():
        raise ApiError(
            500, "RULESET_GUIDANCE_NOT_FOUND", f"Panduan ruleset {ruleset_id} tidak ditemukan."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def guidance(db: Session, user: User, ruleset: Ruleset) -> dict:
    """Return the applicable ruleset guidance and disclaimer.

    Does not refresh snapshots. The dashboard route owns that write.
    """
    profile = find_profile(db, user, ruleset.tax_year)
    if profile is None:
        raise ApiError(
            404, "PROFILE_NOT_FOUND", "Profil untuk tahun pajak yang dipilih belum dibuat."
        )
    items = _load_guidance_items(ruleset.ruleset_id)
    monitoring = dashboard(db, user, ruleset.tax_year, ruleset, refresh=False)["thresholds"][
        "monitoring_current_year_cap_4_8m"
    ]
    conditions = {"always", profile.spouse_tax_status}
    if profile.has_selected_article_17:
        conditions.add("article17")
    elif profile.has_selected_article_17 is None:
        conditions.add("article17_unknown")
    if profile.has_sole_proprietor_company:
        conditions.add("company")
    elif profile.has_sole_proprietor_company is None:
        conditions.add("company_unknown")
    if profile.is_new_taxpayer_current_year is None:
        conditions.add("new_taxpayer_unknown")
    if monitoring["cap_warning"]:
        conditions.add("cap_warning")
    return {
        "ruleset_id": ruleset.ruleset_id,
        "effective_date": ruleset.effective_date,
        "disclaimer": DISCLAIMER,
        "items": [
            {k: item[k] for k in ("id", "text", "citation")}
            for item in items
            if item["condition"] in conditions
        ],
    }
