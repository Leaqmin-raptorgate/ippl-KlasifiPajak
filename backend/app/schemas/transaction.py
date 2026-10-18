"""Request and response shapes for transactions."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

SourceChannel = Literal["marketplace", "corporate_client", "retail", "other"]


class TransactionCreate(BaseModel):
    """Body of ``POST /transactions``."""

    model_config = ConfigDict(extra="forbid")

    amount_idr: StrictInt = Field(gt=0)
    tx_date: date
    client_name: str = ""
    description: str = ""
    invoice_no: str | None = None
    withheld_tax_amount_idr: StrictInt = Field(default=0, ge=0)
    source_channel: SourceChannel = "other"


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
