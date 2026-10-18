"""Request and response shapes for the account endpoints."""

from pydantic import BaseModel, ConfigDict, Field, StrictStr


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


class RevokedOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    revoked: bool


class ProfileUpdate(BaseModel):
    """The business fields accepted by ``PUT /profiles/{tax_year}``."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str = ""
    entity_type: str = "orang_pribadi"
    nib_status: str = "unknown"
    nib_last_4: str | None = None
    kbli_code: str = ""
    business_description: str = ""
    marital_status: str = "unknown"
    spouse_aggregation_active: bool = False
    is_new_taxpayer_current_year: bool = False
    spouse_current_usaha_idr: int = Field(default=0, ge=0)
    spouse_current_pekerjaan_bebas_idr: int = Field(default=0, ge=0)
    spouse_current_already_final_idr: int = Field(default=0, ge=0)
    prior_user_usaha_idr: int = Field(default=0, ge=0)
    prior_user_pekerjaan_bebas_idr: int = Field(default=0, ge=0)
    prior_user_already_final_idr: int = Field(default=0, ge=0)
    prior_spouse_usaha_idr: int = Field(default=0, ge=0)
    prior_spouse_pekerjaan_bebas_idr: int = Field(default=0, ge=0)
    prior_spouse_already_final_idr: int = Field(default=0, ge=0)


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
    is_new_taxpayer_current_year: bool
    version: int
    spouse_current_usaha_idr: int
    spouse_current_pekerjaan_bebas_idr: int
    spouse_current_already_final_idr: int
    prior_user_usaha_idr: int
    prior_user_pekerjaan_bebas_idr: int
    prior_user_already_final_idr: int
    prior_spouse_usaha_idr: int
    prior_spouse_pekerjaan_bebas_idr: int
    prior_spouse_already_final_idr: int
    audit_trail: tuple[AuditEntry, ...]
