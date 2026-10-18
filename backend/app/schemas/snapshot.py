"""Request and response shapes for a tax snapshot.

Field names follow KlasifiPajak API v1.2.2 sections 3.3 and 2.4. Money is a
strict integer rupiah; a date is a Jakarta calendar date, never a timestamp.
"""

import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictInt, StrictStr

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _reject_non_int(value):
    """Rupiah must arrive as a real integer.

    Pydantic's strict integer still accepts a whole ``Decimal``, which is
    exactly the kind of near-integer that produces a plausible wrong figure.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("rupiah must be an integer, not a string, float or Decimal")
    return value


def _reject_timestamp(value):
    """Accept a calendar date only. A timestamp would smuggle a timezone in."""
    if isinstance(value, datetime):
        raise ValueError("date must be a calendar date, not a timestamp")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        if not _ISO_DATE.match(value):
            raise ValueError("date must be YYYY-MM-DD")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("date must be a real calendar date") from exc
    raise ValueError("date must be a YYYY-MM-DD string")


#: Rupiah. Strict so no string, float or Decimal is ever silently accepted.
Rupiah = Annotated[StrictInt, BeforeValidator(_reject_non_int), Field(ge=0)]
#: A rupiah amount that must be greater than zero.
PositiveRupiah = Annotated[StrictInt, BeforeValidator(_reject_non_int), Field(gt=0)]
#: An ISO-8601 calendar date. Timestamps are refused (invariant 7).
CalendarDate = Annotated[date, BeforeValidator(_reject_timestamp)]

Kategori = Literal["usaha", "pekerjaan_bebas", "already_final", "non_object"]
MaritalStatus = Literal["yes", "no", "unknown"]


class PriorYearGross(BaseModel):
    """One party's prior-year gross split by category (Pasal 58 ayat (1))."""

    model_config = ConfigDict(extra="forbid")

    usaha_idr: Rupiah = 0
    pekerjaan_bebas_idr: Rupiah = 0
    already_final_idr: Rupiah = 0


class ProfileIn(BaseModel):
    """Threshold inputs. FR-03, FR-21, FR-22."""

    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["orang_pribadi"] = "orang_pribadi"
    marital_status: MaritalStatus = "unknown"
    spouse_aggregation_active: bool = False
    is_new_taxpayer_current_year: bool = False
    spouse_current_year_usaha_omzet_idr: Rupiah = 0
    spouse_current_year_pekerjaan_bebas_omzet_idr: Rupiah = 0
    spouse_current_year_already_final_omzet_idr: Rupiah = 0
    prior_year_gross_user: PriorYearGross | None = None
    prior_year_gross_spouse: PriorYearGross | None = None


class TransactionIn(BaseModel):
    """One already-classified income row."""

    model_config = ConfigDict(extra="forbid")

    id: StrictStr = Field(min_length=1)
    tx_date: CalendarDate
    amount_idr: PositiveRupiah
    category: Kategori
    withheld_tax_amount_idr: Rupiah = 0


class SnapshotIn(BaseModel):
    """A stateless calculation request."""

    model_config = ConfigDict(extra="forbid")

    tax_year: StrictInt = 2026
    as_of_date: CalendarDate
    profile: ProfileIn = Field(default_factory=ProfileIn)
    transactions: list[TransactionIn] = Field(default_factory=list)


class MonthOut(BaseModel):
    """One month of the calculation, including a month with no rows."""

    model_config = ConfigDict(frozen=True)

    month: StrictStr
    input_hash: StrictStr
    scheme_eligibility_status: StrictStr
    usaha_omzet_idr: Rupiah
    porsi_bebas_idr: Rupiah
    porsi_kena_idr: Rupiah
    tax_0_5_pct_idr: Rupiah
    withheld_tax_idr: Rupiah
    sisa_bayar_idr: Rupiah
    overwithheld_excess_idr: Rupiah
    overwithheld_status: StrictStr
    pekerjaan_bebas_omzet_idr: Rupiah
    already_final_omzet_idr: Rupiah
    non_object_omzet_idr: Rupiah


class SnapshotOut(BaseModel):
    """The engine result in the section 3.3 wire shape."""

    model_config = ConfigDict(frozen=True)

    tax_year: StrictInt
    as_of_date: StrictStr
    ruleset_id: StrictStr
    effective_date: StrictStr
    rounding_rule: StrictStr
    scheme_eligibility_status: StrictStr
    prior_year_resolution_source: StrictStr
    prior_year_combined_gross_idr: Rupiah
    current_year_combined_gross_idr: Rupiah
    next_year_ineligible: bool
    spouse_aggregation_active: bool
    remaining_free_band_idr: Rupiah
    months: tuple[MonthOut, ...]
    disclaimer: StrictStr
