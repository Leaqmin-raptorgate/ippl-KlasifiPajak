"""Workpaper recap routes (FR-31, FR-32, FR-36).

Thin by rule: validate the year and the paid gate, then call one service.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, current_session, get_settings
from app.api.errors import ApiError
from app.config.settings import Settings
from app.db import get_db
from app.services import recap as recap_service
from app.services.snapshot import active_ruleset
from app.services.subscription import _is_paid_active

router = APIRouter()

_PAID_PDF_MESSAGE = "Fitur unduh berkas workpaper PDF hanya tersedia bagi pengguna berbayar aktif."


def _checked_ruleset(tax_year: int, settings: Settings):
    """Reject a year the active ruleset does not serve."""
    ruleset = active_ruleset(settings.ruleset_path)
    if tax_year != ruleset.tax_year:
        raise ApiError(422, "INVALID_DATE_RANGE", f"Tahun pajak harus {ruleset.tax_year}.")
    return ruleset


@router.get("/recap/{tax_year}")
def get_recap(
    tax_year: int,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return the stored annual workpaper for one tax year (FR-31 / FR-36)."""
    ruleset = _checked_ruleset(tax_year, settings)
    return recap_service.annual_recap(db, context.user, tax_year, ruleset)


@router.post("/recap/{tax_year}/pdf")
def post_recap_pdf(
    tax_year: int,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Stream one workpaper PDF for an active paid account (FR-32 / FR-36)."""
    ruleset = _checked_ruleset(tax_year, settings)
    if not _is_paid_active(context.user):
        raise ApiError(403, "PAID_SUBSCRIPTION_REQUIRED", _PAID_PDF_MESSAGE)
    payload = recap_service.workpaper_pdf(db, context.user, tax_year, ruleset)
    filename = f'attachment; filename="Workpaper_PPh_Final_{tax_year}.pdf"'
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": filename},
    )
