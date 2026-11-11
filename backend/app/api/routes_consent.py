"""AI and OCR processing consent (FR-27)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, current_session
from app.db import get_db
from app.schemas.account import AiConsentOut
from app.services import assistant

router = APIRouter()


class AiConsentIn(BaseModel):
    """Explicit choice to allow or withdraw AI processing."""

    model_config = ConfigDict(extra="forbid")

    consent: bool


@router.get("/ai-consent", response_model=AiConsentOut)
def get_ai_consent(
    context: AuthContext = Depends(current_session),
) -> dict:
    """Return the current consent status and timestamp (FR-27)."""
    return assistant.consent_out(context.user.ai_consent_at)


@router.put("/ai-consent", response_model=AiConsentOut)
def update_ai_consent(
    payload: AiConsentIn,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> dict:
    """Record consent in UTC, or clear it when the caller withdraws."""
    return assistant.set_ai_consent(db, context.user, payload.consent)
