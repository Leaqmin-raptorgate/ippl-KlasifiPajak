"""AI and OCR processing consent (FR-27)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, current_session
from app.db import get_db
from app.services import assistant

router = APIRouter()


class AiConsentIn(BaseModel):
    """Explicit choice to allow or withdraw AI processing."""

    model_config = ConfigDict(extra="forbid")

    consent: bool


@router.put("/ai-consent")
def update_ai_consent(
    payload: AiConsentIn,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> dict:
    """Record consent in UTC, or clear it when the caller withdraws."""
    return assistant.set_ai_consent(db, context.user, payload.consent)
