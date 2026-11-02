"""Bagian B: the authenticated application surface under ``/api/v1``.

Thin by rule: validate, call one service, return. No route builds a query.
"""

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, current_session, get_settings
from app.api.errors import ApiError
from app.config.settings import Settings
from app.db import get_db
from app.schemas.account import (
    LoginIn,
    LoginOut,
    MeOut,
    ProfileOut,
    ProfileUpdate,
    RegisterIn,
    RegisterOut,
    RevokedOut,
)
from app.schemas.transaction import (
    AuditTrailOut,
    ClarificationAnswer,
    ClarificationOut,
    OverrideIn,
    ReclassifyIn,
    TransactionCreate,
    TransactionListOut,
    TransactionOut,
    TransactionUpdate,
)
from app.security import iso_utc
from app.services import auth as auth_service
from app.services import dashboard as dashboard_service
from app.services import profile as profile_service
from app.services import subscription as subscription_service
from app.services import transactions as transaction_service
from app.services.snapshot import active_ruleset

router = APIRouter()


@router.post("/auth/register", status_code=201, response_model=RegisterOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> RegisterOut:
    user = auth_service.register(db, payload)
    return RegisterOut(
        user_id=user.id,
        email=user.email,
        username=user.username,
        created_at=iso_utc(user.created_at),
    )


@router.post("/auth/login", response_model=LoginOut)
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LoginOut:
    user, session = auth_service.login(db, payload, settings, request.headers.get("User-Agent", ""))
    token = auth_service.token_for(user, session, settings)
    non_browser = request.headers.get("X-Client-Type") == "non-browser"
    if not non_browser:
        response.set_cookie(
            "kp_session",
            token,
            httponly=True,
            samesite="lax",
            path="/",
            max_age=settings.session_hours * 3600,
            secure=settings.is_production,
        )
    return LoginOut(
        user_id=user.id,
        expires_at=iso_utc(session.expires_at_utc),
        token=token if non_browser else None,
    )


@router.post("/auth/logout", response_model=RevokedOut)
def logout(
    response: Response,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> RevokedOut:
    auth_service.logout(db, context.session)
    response.delete_cookie("kp_session", path="/")
    return RevokedOut(revoked=True)


@router.get("/auth/me", response_model=MeOut)
def me(context: AuthContext = Depends(current_session)) -> MeOut:
    return MeOut(
        user_id=context.user.id,
        email=context.user.email,
        username=context.user.username,
    )


@router.get("/profiles/{tax_year}", response_model=ProfileOut)
def get_profile(
    tax_year: int,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> ProfileOut:
    return profile_service.get_profile(db, context.user, tax_year)


@router.put("/profiles/{tax_year}", response_model=ProfileOut)
def put_profile(
    tax_year: int,
    payload: ProfileUpdate,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProfileOut:
    ruleset = active_ruleset(settings.ruleset_path)
    if tax_year != ruleset.tax_year:
        raise ApiError(422, "INVALID_DATE_RANGE", f"Tahun pajak harus {ruleset.tax_year}.")
    return profile_service.update_profile(db, context.user, tax_year, payload, ruleset)


@router.get("/transactions", response_model=TransactionListOut)
def list_transactions(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    tax_year: int | None = None,
    month: str | None = None,
    client_name: str | None = None,
    invoice_no: str | None = None,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> TransactionListOut:
    return transaction_service.list_transactions(
        db,
        context.user,
        page=page,
        per_page=per_page,
        tax_year=tax_year,
        month=month,
        client_name=client_name,
        invoice_no=invoice_no,
    )


@router.post("/transactions", status_code=201, response_model=TransactionOut)
def create_transaction(
    payload: TransactionCreate,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TransactionOut:
    ruleset = active_ruleset(settings.ruleset_path)
    return transaction_service.create_transaction(db, context.user, payload, ruleset)


@router.get("/transactions/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    transaction_id: str,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> TransactionOut:
    return transaction_service.row_out(
        transaction_service.get_transaction(db, context.user, transaction_id)
    )


@router.get("/transactions/{transaction_id}/clarification", response_model=ClarificationOut)
def get_clarification(
    transaction_id: str,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> ClarificationOut:
    """The closed question a provisional row waits on. 404 when there is none."""
    return transaction_service.clarification_for(db, context.user, transaction_id)


@router.post("/transactions/{transaction_id}/clarification", response_model=TransactionOut)
def answer_clarification(
    transaction_id: str,
    payload: ClarificationAnswer,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TransactionOut:
    """Resolve a provisional row and rebuild the snapshots it feeds."""
    ruleset = active_ruleset(settings.ruleset_path)
    return transaction_service.answer_clarification(
        db, context.user, transaction_id, payload, ruleset
    )


@router.get("/tax/dashboard")
def dashboard(
    tax_year: int = Query(default=2026),
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    ruleset = active_ruleset(settings.ruleset_path)
    if tax_year != ruleset.tax_year:
        raise ApiError(422, "INVALID_DATE_RANGE", f"Tahun pajak harus {ruleset.tax_year}.")
    return dashboard_service.dashboard(db, context.user, tax_year, ruleset)


@router.get("/quotas")
def get_quotas(
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return subscription_service.quotas(db, context.user, active_ruleset(settings.ruleset_path))


@router.get("/subscriptions/status")
def get_subscription_status(
    context: AuthContext = Depends(current_session),
) -> dict:
    return subscription_service.subscription_status(context.user)


@router.put("/transactions/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: str,
    payload: TransactionUpdate,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TransactionOut:
    """Edit one owned row with optimistic concurrency (FR-08 / API §5.12)."""
    ruleset = active_ruleset(settings.ruleset_path)
    return transaction_service.update_transaction(
        db, context.user, transaction_id, payload, ruleset
    )


@router.delete("/transactions/{transaction_id}")
def delete_transaction(
    transaction_id: str,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Delete one owned row and cascade its classification events (FR-09)."""
    ruleset = active_ruleset(settings.ruleset_path)
    return transaction_service.delete_transaction(db, context.user, transaction_id, ruleset)


@router.post("/transactions/{transaction_id}/override", response_model=TransactionOut)
def override_transaction(
    transaction_id: str,
    payload: OverrideIn,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TransactionOut:
    """Manual category override without a model call (API §5.18)."""
    ruleset = active_ruleset(settings.ruleset_path)
    return transaction_service.override_category(db, context.user, transaction_id, payload, ruleset)


@router.post("/transactions/reclassify")
def reclassify_transactions(
    payload: ReclassifyIn,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Re-run the keyword pipeline on a list of owned rows (API §5.9)."""
    ruleset = active_ruleset(settings.ruleset_path)
    return transaction_service.reclassify_transactions(db, context.user, payload, ruleset)


@router.get("/transactions/{transaction_id}/audit-trail", response_model=AuditTrailOut)
def get_audit_trail(
    transaction_id: str,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> AuditTrailOut:
    """Per-transaction classification jejak (FR-16a / API §5.19)."""
    return transaction_service.audit_trail(db, context.user, transaction_id)


@router.post("/tax/snapshots/{tax_year}/recalculate")
def recalculate_snapshots(
    tax_year: int,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Mark usang then insert versioned berlaku rows (FR-23a / API §5.22)."""
    ruleset = active_ruleset(settings.ruleset_path)
    return transaction_service.recalculate_snapshots(db, context.user, tax_year, ruleset)


@router.get("/tax/snapshots/{tax_year}/{month}")
def get_month_snapshot(
    tax_year: int,
    month: str,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Monthly snapshot jejak for one month (FR-47 / API §5.21)."""
    ruleset = active_ruleset(settings.ruleset_path)
    return transaction_service.month_snapshot(db, context.user, tax_year, month, ruleset)


@router.post("/test-support/subscription-override", response_model=None)
def subscription_override(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """HB-29 / API §5.31 — fail-closed outside APP_ENV=test on loopback."""
    if not settings.is_test:
        return Response(status_code=404)
    host = (request.client.host if request.client else "") or ""
    if host not in {"127.0.0.1", "::1", "testclient", "localhost"}:
        return Response(status_code=404)
    from datetime import datetime

    from sqlalchemy import select

    from app.models import User

    user_id = payload.get("user_id")
    user = db.scalar(select(User).where(User.id == user_id)) if user_id else None
    if user is None:
        raise ApiError(404, "USER_NOT_FOUND", "Pengguna tidak ditemukan.")
    raw = payload.get("valid_until")
    valid_until = None
    if raw:
        valid_until = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
    return subscription_service.set_subscription_override(
        db,
        user,
        paid_flag=bool(payload.get("paid_flag")),
        valid_until=valid_until,
    )
