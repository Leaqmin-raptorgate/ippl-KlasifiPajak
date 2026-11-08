"""AI and OCR processing consent (FR-27)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, current_session
from app.db import get_db
from app.security import iso_utc
from app.services import assistant

router = APIRouter()


class AiConsentIn(BaseModel):
    """Explicit choice to allow or withdraw AI processing."""

    model_config = ConfigDict(extra="forbid")

    consent: bool


@router.get("/ai-consent")
def get_ai_consent(
    context: AuthContext = Depends(current_session),
) -> dict:
    """Return the current consent status and timestamp (FR-27)."""
    stamp = context.user.ai_consent_at
    return {
        "consent": stamp is not None,
        "ai_consent_at": iso_utc(stamp) if stamp is not None else None,
    }


@router.put("/ai-consent")
def update_ai_consent(
    payload: AiConsentIn,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> dict:
    """Record consent in UTC, or clear it when the caller withdraws."""
    return assistant.set_ai_consent(db, context.user, payload.consent)
