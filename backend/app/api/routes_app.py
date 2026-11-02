"""Bagian B: the authenticated application surface under ``/api/v1``.

Thin by rule: validate, call one service, return. No route builds a query.
"""

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, current_session, get_settings
from app.api.errors import ApiError
from app.config.settings import Settings
from app.db import get_db
from app.logging_redaction import configure_redacted_logging
from app.schemas.account import (
    DeleteAccountIn,
    DeleteAccountOut,
    LoginIn,
    LoginOut,
    MeOut,
    MessageOut,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    ProfileOut,
    ProfileUpdate,
    RegisterIn,
    RegisterOut,
    RevokedCountOut,
    RevokedOut,
    SessionListOut,
)
from app.schemas.transaction import (
    ClarificationAnswer,
    ClarificationOut,
    TransactionCreate,
    TransactionListOut,
    TransactionOut,
)
from app.security import iso_utc
from app.services import auth as auth_service
from app.services import dashboard as dashboard_service
from app.services import profile as profile_service
from app.services import subscription as subscription_service
from app.services import transactions as transaction_service
from app.services.auth import (
    ACCOUNT_DELETED_MESSAGE,
    GENERIC_RESET_MESSAGE,
    RESET_SUCCESS_MESSAGE,
)
from app.services.snapshot import active_ruleset

configure_redacted_logging()

router = APIRouter()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "0.0.0.0"


@router.post("/auth/register", status_code=201, response_model=RegisterOut)
def register(
    payload: RegisterIn,
    request: Request,
    db: Session = Depends(get_db),
) -> RegisterOut:
    user = auth_service.register(db, payload, client_ip=_client_ip(request))
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
    user, session = auth_service.login(
        db,
        payload,
        settings,
        request.headers.get("User-Agent", ""),
        client_ip=_client_ip(request),
    )
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
    settings: Settings = Depends(get_settings),
) -> RevokedOut:
    auth_service.logout(db, context.session)
    # HB-05: clear flags must match set_cookie (path/httponly/samesite/secure).
    response.delete_cookie(
        "kp_session",
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
    return RevokedOut(revoked=True)


@router.get("/auth/me", response_model=MeOut)
def me(context: AuthContext = Depends(current_session)) -> MeOut:
    return MeOut(
        user_id=context.user.id,
        email=context.user.email,
        username=context.user.username,
    )


@router.post("/auth/password-reset/request", response_model=MessageOut)
def password_reset_request(
    payload: PasswordResetRequestIn,
    request: Request,
    db: Session = Depends(get_db),
) -> MessageOut:
    # Discard plaintext; never leak account existence (API §5.4).
    auth_service.request_password_reset(db, payload, client_ip=_client_ip(request))
    return MessageOut(message=GENERIC_RESET_MESSAGE)


@router.post("/auth/password-reset/confirm", response_model=MessageOut)
def password_reset_confirm(
    payload: PasswordResetConfirmIn,
    db: Session = Depends(get_db),
) -> MessageOut:
    auth_service.confirm_password_reset(db, payload)
    return MessageOut(message=RESET_SUCCESS_MESSAGE)


@router.get("/auth/sessions", response_model=SessionListOut)
def list_sessions(
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> SessionListOut:
    items = auth_service.list_sessions(db, context.user, context.session)
    return SessionListOut(items=items)


@router.delete("/auth/sessions/{session_id}", response_model=RevokedOut)
def revoke_one_session(
    session_id: str,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> RevokedOut:
    auth_service.revoke_session(db, context.user, session_id)
    return RevokedOut(revoked=True)


@router.delete("/auth/sessions", response_model=RevokedCountOut)
def revoke_other_sessions(
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> RevokedCountOut:
    count = auth_service.revoke_other_sessions(db, context.user, context.session)
    return RevokedCountOut(revoked_count=count)


@router.delete("/account", response_model=DeleteAccountOut)
def delete_account(
    payload: DeleteAccountIn,
    response: Response,
    context: AuthContext = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DeleteAccountOut:
    auth_service.delete_account(db, context.user, payload)
    response.delete_cookie(
        "kp_session",
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
    return DeleteAccountOut(deleted=True, message=ACCOUNT_DELETED_MESSAGE)


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
    settings: Settings = Depends(get_settings),
) -> dict:
    return subscription_service.quotas(active_ruleset(settings.ruleset_path))


@router.get("/subscriptions/status")
def get_subscription_status(
    context: AuthContext = Depends(current_session),
) -> dict:
    return subscription_service.subscription_status(context.user)
