"""Static, cited guidance selected for a taxpayer (FR-49)."""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.engine import Ruleset
from app.models import User
from app.services.dashboard import dashboard
from app.services.profile import find_profile
from app.services.snapshot import DISCLAIMER


def guidance(db: Session, user: User, ruleset: Ruleset) -> dict:
    """Return the applicable ruleset guidance and disclaimer."""
    profile = find_profile(db, user, ruleset.tax_year)
    if profile is None:
        raise ApiError(
            404, "PROFILE_NOT_FOUND", "Profil untuk tahun pajak yang dipilih belum dibuat."
        )
    items = json.loads(
        (Path(__file__).parent.parent / "guidance" / f"{ruleset.ruleset_id}.json").read_text()
    )
    monitoring = dashboard(db, user, ruleset.tax_year, ruleset)["thresholds"][
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
