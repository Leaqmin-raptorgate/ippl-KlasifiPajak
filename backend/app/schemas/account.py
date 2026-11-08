"""Request and response shapes for the account endpoints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app.api.errors import ApiError


def validate_email_shape(email: str) -> str:
    """Simple shape check from API §5.1 → 422 INVALID_EMAIL on failure."""
    value = email.strip() if isinstance(email, str) else ""
    if not value or len(value) > 254 or any(ch.isspace() for ch in value) or value.count("@") != 1:
        raise ApiError(422, "INVALID_EMAIL", "Format surel tidak sah.")
    local, _, domain = value.partition("@")
    if not local or not domain or "." not in domain:
        raise ApiError(422, "INVALID_EMAIL", "Format surel tidak sah.")
    return value


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: StrictStr
    username: StrictStr
    password: StrictStr


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: StrictStr
    password: StrictStr


class RegisterOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    email: str
    username: str
    created_at: str


class LoginOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    expires_at: str
    token: str | None = None


class MeOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    email: str
    username: str
    ai_consent_at: str | None = None


class RevokedOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    revoked: bool


class MessageOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str


class PasswordResetRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: StrictStr


class PasswordResetConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: StrictStr
    new_password: StrictStr


class SessionItemOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    device_label: str
    created_at: str
    last_seen_at: str
    current: bool


class SessionListOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[SessionItemOut]


class RevokedCountOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    revoked_count: int


class DeleteAccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: StrictStr


class DeleteAccountOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    deleted: bool
    message: str


class ProfileUpdate(BaseModel):
    """The business fields accepted by ``PUT /profiles/{tax_year}``."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str = Field(default="", max_length=255)
    entity_type: str = "orang_pribadi"
    nib_status: Literal["has_nib", "no_nib", "unknown"] = "unknown"
    nib_last_4: str | None = None
    kbli_code: str = Field(default="", max_length=16)
    business_description: str = Field(default="", max_length=255)
    marital_status: Literal["yes", "no", "unknown"] = "unknown"
    spouse_tax_status: Literal["unmarried", "separate", "joint", "unknown"] = "unknown"
    has_selected_article_17: bool | None = None
    has_sole_proprietor_company: bool | None = None
    receives_salary: bool | None = None
    spouse_aggregation_active: bool = False
    is_new_taxpayer_current_year: bool | None = None
    spouse_current_usaha_idr: int = Field(default=0, ge=0)
    spouse_current_pekerjaan_bebas_idr: int = Field(default=0, ge=0)
    spouse_current_already_final_idr: int = Field(default=0, ge=0)
    prior_user_usaha_idr: int | None = Field(default=None, ge=0)
    prior_user_pekerjaan_bebas_idr: int | None = Field(default=None, ge=0)
    prior_user_already_final_idr: int | None = Field(default=None, ge=0)
    prior_spouse_usaha_idr: int | None = Field(default=None, ge=0)
    prior_spouse_pekerjaan_bebas_idr: int | None = Field(default=None, ge=0)
    prior_spouse_already_final_idr: int | None = Field(default=None, ge=0)


class AuditEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    changed_at: str
    field: str
    old_value: str
    new_value: str


class ProfileOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    user_id: str
    tax_year: int
    name: str
    entity_type: str
    nib_status: str
    nib_masked: str | None
    kbli_code: str
    business_description: str
    marital_status: str
    spouse_aggregation_active: bool
    spouse_tax_status: str
    has_selected_article_17: bool | None
    has_sole_proprietor_company: bool | None
    receives_salary: bool | None
    is_new_taxpayer_current_year: bool | None
    version: int
    spouse_current_usaha_idr: int
    spouse_current_pekerjaan_bebas_idr: int
    spouse_current_already_final_idr: int
    prior_user_usaha_idr: int | None
    prior_user_pekerjaan_bebas_idr: int | None
    prior_user_already_final_idr: int | None
    prior_spouse_usaha_idr: int | None
    prior_spouse_pekerjaan_bebas_idr: int | None
    prior_spouse_already_final_idr: int | None
    audit_trail: tuple[AuditEntry, ...]
