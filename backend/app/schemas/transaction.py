"""Request and response shapes for transactions."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

SourceChannel = Literal["marketplace", "corporate_client", "retail", "other"]


class TransactionCreate(BaseModel):
    """Body of ``POST /transactions``."""

    model_config = ConfigDict(extra="forbid")

    amount_idr: StrictInt = Field(gt=0)
    tx_date: date
    client_name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=255)
    invoice_no: str | None = Field(default=None, max_length=64)
    withheld_tax_amount_idr: StrictInt = Field(default=0, ge=0)
    source_channel: SourceChannel = "other"

    @field_validator("client_name", "description")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Kolom wajib diisi.")
        return value


class ClassificationOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str
    source: str
    confidence: float
    rule_id: str
    requires_clarification: bool


class TransactionOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    version: int
    tx_date: date
    client_name: str
    invoice_no: str | None
    amount_idr: int
    withheld_tax_amount_idr: int
    source_channel: str
    category: str
    source: str
    description: str
    classification: ClassificationOut | None = None


class ClarificationOption(BaseModel):
    """One answer to a clarification question."""

    model_config = ConfigDict(frozen=True)

    value: Literal["usaha", "pekerjaan_bebas", "already_final", "non_object"]
    label: str


class ClarificationOut(BaseModel):
    """The closed question a provisional row is waiting on."""

    model_config = ConfigDict(frozen=True)

    transaction_id: str
    provisional_category: str
    question: str
    options: tuple[ClarificationOption, ...]


class ClarificationAnswer(BaseModel):
    """Body of ``POST /transactions/{id}/clarification``."""

    model_config = ConfigDict(extra="forbid")

    category: Literal["usaha", "pekerjaan_bebas", "already_final", "non_object"]
    #: Sent when the client holds a row it read earlier. A mismatch is a 409
    #: rather than a silent overwrite.
    version: int | None = None


class PaginationOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    current_page: int
    per_page: int
    total_items: int
    total_pages: int


class TransactionListOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[TransactionOut, ...]
    pagination: PaginationOut


class TransactionUpdate(BaseModel):
    """Body of ``PUT /transactions/{id}`` — create fields plus ``version``."""

    model_config = ConfigDict(extra="forbid")

    amount_idr: StrictInt = Field(gt=0)
    tx_date: date
    client_name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=255)
    invoice_no: str | None = Field(default=None, max_length=64)
    withheld_tax_amount_idr: StrictInt = Field(default=0, ge=0)
    source_channel: SourceChannel = "other"
    version: int = Field(ge=1)

    @field_validator("client_name", "description")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Kolom wajib diisi.")
        return value


class OverrideIn(BaseModel):
    """Body of ``POST /transactions/{id}/override``."""

    model_config = ConfigDict(extra="forbid")

    new_category: Literal["usaha", "pekerjaan_bebas", "already_final", "non_object"]
    note: str | None = None


class ReclassifyIn(BaseModel):
    """Body of ``POST /transactions/reclassify``."""

    model_config = ConfigDict(extra="forbid")

    transaction_ids: list[str] = Field(min_length=1)


class AuditEventOut(BaseModel):
    """One classification_events row on the audit-trail wire (API §5.19 / D-02)."""

    model_config = ConfigDict(frozen=True)

    timestamp: str
    source: str
    rule_id: str = ""
    citation: str = ""
    assigned_category: str = ""
    old_category: str = ""
    new_category: str = ""
    note: str = ""
    ytd_usaha_omzet_before_idr: int = 0
    ytd_usaha_omzet_after_idr: int = 0
    ruleset_id: str = ""
    effective_date: str = ""


class AuditTrailOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    events: tuple[AuditEventOut, ...]
