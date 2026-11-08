"""Payment HTTP endpoints; payment business logic lives in services."""

from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, current_session
from app.db import get_db
from app.services import payments

router = APIRouter()


class CreateOrderIn(BaseModel):
    """Selected subscription plan (FR-PAY-01)."""

    model_config = ConfigDict(extra="forbid")
    plan_id: str


@router.post("/subscriptions/orders")
def create_order(
    payload: CreateOrderIn,
    response: Response,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> dict:
    """Create or reuse the caller's subscription order."""
    order, created = payments.create_order(db, context.user, payload.plan_id)
    response.status_code = 201 if created else 200
    return order


@router.get("/subscriptions/orders")
def list_orders(
    context: AuthContext = Depends(current_session), db: Session = Depends(get_db)
) -> dict:
    """List the caller's own orders."""
    return {"items": payments.list_orders(db, context.user)}


@router.post("/webhooks/payment")
def payment_notification(payload: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    """Accept a signed notification from the payment gateway."""
    return payments.process_notification(db, payload)
