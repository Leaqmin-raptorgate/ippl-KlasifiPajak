"""Receipt OCR routes (FR-06, FR-06a, FR-06b).

Thin by rule: read the upload or the confirmed fields, then call one service.
The router is mounted at ``/api/v1`` by the application entrypoint.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, current_session, get_settings
from app.config.settings import Settings
from app.db import get_db
from app.services import receipts as receipt_service
from app.services.snapshot import active_ruleset

router = APIRouter()

SourceChannel = Literal["marketplace", "corporate_client", "retail", "other"]


class OcrConfirmIn(BaseModel):
    """Body of ``POST /transactions/ocr-confirm`` (FR-06b).

    Only confirmed fields are accepted. OCR candidates are not part of this body.
    """

    model_config = ConfigDict(extra="forbid")

    image_id: str = Field(min_length=1, max_length=64)
    confirmed_amount_idr: StrictInt = Field(gt=0)
    confirmed_tx_date: date
    confirmed_client_name: str = Field(min_length=1, max_length=255)
    confirmed_description: str = Field(min_length=1, max_length=255)
    confirmed_invoice_no: str | None = Field(default=None, max_length=64)
    withheld_tax_amount_idr: StrictInt = Field(default=0, ge=0)
    source_channel: SourceChannel = "other"

    @field_validator("confirmed_client_name", "confirmed_description")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Kolom wajib diisi.")
        return value


@router.post("/transactions/ocr-upload")
def ocr_upload(
    file: UploadFile = File(...),
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> dict:
    """Accept one JPEG or PNG and return candidates, not a transaction (FR-06)."""
    raw = receipt_service.read_bounded(file.file)
    return receipt_service.upload_receipt(db, context.user, raw, file.content_type)


@router.get("/transactions/receipt-images/{image_id}")
def get_receipt_image(
    image_id: str,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> Response:
    """Return one owned receipt. No paid gate. Missing and foreign ids are 404."""
    body, mime = receipt_service.receipt_bytes(db, context.user, image_id)
    return Response(content=body, media_type=mime, headers={"Cache-Control": "private, no-store"})


@router.post("/transactions/ocr-confirm", status_code=201)
def ocr_confirm(
    payload: OcrConfirmIn,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Save a transaction from the confirmed receipt fields (FR-06b)."""
    ruleset = active_ruleset(settings.ruleset_path)
    return receipt_service.confirm_receipt(
        db,
        context.user,
        image_id=payload.image_id,
        confirmed_amount_idr=payload.confirmed_amount_idr,
        confirmed_tx_date=payload.confirmed_tx_date,
        confirmed_client_name=payload.confirmed_client_name,
        confirmed_description=payload.confirmed_description,
        confirmed_invoice_no=payload.confirmed_invoice_no,
        withheld_tax_amount_idr=payload.withheld_tax_amount_idr,
        source_channel=payload.source_channel,
        ruleset=ruleset,
    )
