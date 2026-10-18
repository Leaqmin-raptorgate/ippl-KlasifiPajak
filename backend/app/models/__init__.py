"""SQLAlchemy tables for the slice that stores accounts and tax data.

Names and columns follow ERD v1.2.2. Money is ``BIGINT`` rupiah; instants are
UTC ``DateTime`` values written by the application. Tables outside today's
slice (password reset, receipts, quotas, orders, payment events) are not
declared yet.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_norm: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    username_norm: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    paid_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    valid_until_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    device_label: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    issued_at_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("user_id", "tax_year"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), default="orang_pribadi", nullable=False)
    nib_status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    nib_last_4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    kbli_code: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    business_description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    marital_status: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)
    spouse_aggregation_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_new_taxpayer_current_year: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    spouse_current_usaha_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    spouse_current_pekerjaan_bebas_idr: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    spouse_current_already_final_idr: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    prior_user_usaha_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    prior_user_pekerjaan_bebas_idr: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    prior_user_already_final_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    prior_spouse_usaha_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    prior_spouse_pekerjaan_bebas_idr: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    prior_spouse_already_final_idr: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )


class ProfileChange(Base):
    __tablename__ = "profile_changes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), nullable=False, index=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    new_value: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    image_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tx_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount_idr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    withheld_tax_amount_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    client_name_norm: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    invoice_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_no_norm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_channel: Mapped[str] = mapped_column(String(32), default="other", nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    requires_clarification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ClassificationEvent(Base):
    __tablename__ = "classification_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.id"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    citation: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    old_category: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    new_category: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    ytd_usaha_before_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    ytd_usaha_after_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    ruleset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)


class MonthSnapshot(Base):
    __tablename__ = "month_snapshots"
    __table_args__ = (UniqueConstraint("profile_id", "month_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), nullable=False, index=True)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="berlaku", nullable=False)
    ruleset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    rounding_rule: Mapped[str] = mapped_column(String(16), nullable=False)
    scheme_eligibility_status: Mapped[str] = mapped_column(String(32), nullable=False)
    next_year_ineligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prior_year_resolution_source: Mapped[str] = mapped_column(String(32), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    usaha_omzet_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    porsi_bebas_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    porsi_kena_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tax_0_5_pct_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    withheld_tax_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    sisa_bayar_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    overwithheld_excess_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    overwithheld_status: Mapped[str] = mapped_column(String(32), default="nihil", nullable=False)
    pekerjaan_bebas_omzet_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    already_final_omzet_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    non_object_omzet_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    annotation: Mapped[str] = mapped_column(String(255), default="", nullable=False)


__all__ = [
    "ClassificationEvent",
    "MonthSnapshot",
    "Profile",
    "ProfileChange",
    "Session",
    "Transaction",
    "User",
]
