"""Read-only assistant HTTP endpoint (FR-27, FR-28)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, StrictStr
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, current_session
from app.db import get_db
from app.services import assistant

router = APIRouter()


class AssistantQueryIn(BaseModel):
    """One natural-language question about the caller's own stored data."""

    model_config = ConfigDict(extra="forbid")

    question: StrictStr


@router.post("/assistant/query")
def assistant_query(
    payload: AssistantQueryIn,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> dict:
    """Answer from stored rows, or refuse, without archiving the question."""
    return assistant.answer(db, context.user, payload.question)
