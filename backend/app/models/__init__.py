"""SQLAlchemy tables aligned with ERD r3 + D-11 snapshot versioning.

Money is ``BIGINT`` rupiah; instants are UTC ``DateTime(fsp=6)`` values written
by the application. Norm columns use collation ``utf8mb4_bin``. Stub tables
cover ERD entities not yet exercised by routes so Alembic can emit a full
empty→head revision.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# ERD: *_norm / email_norm / username_norm are utf8mb4_bin (app does NFKC+casefold).
_NORM = dict(collation="utf8mb4_bin")
# ERD instants are DATETIME(6) holding UTC.
_DT6 = MySQLDateTime(fsp=6)

# Null-safe FR-07 duplicate key: NULL when invoice_no_norm IS NULL so MySQL
# unique index allows many blank-invoice rows (ERD Keys transactions).
_TX_DUP_SQL = (
    "CASE WHEN invoice_no_norm IS NULL THEN NULL ELSE CONCAT("
    "user_id, CHAR(31), client_name_norm, CHAR(31), invoice_no_norm, CHAR(31), "
    "CAST(amount_idr AS CHAR(20)), CHAR(31), DATE_FORMAT(tx_date, '%Y-%m-%d')"
    ") END"
)

# ERD Keys subscription_orders: at most one pending per (user_id, plan_id).
_PENDING_SLOT_SQL = (
    "CASE WHEN status = 'pending' AND user_id IS NOT NULL "
    "THEN CONCAT(user_id, ':', plan_id) ELSE NULL END"
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_norm: Mapped[str] = mapped_column(String(320, **_NORM), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    username_norm: Mapped[str] = mapped_column(String(64, **_NORM), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    paid_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    valid_until_utc: Mapped[datetime | None] = mapped_column(_DT6, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_DT6, nullable=False)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    device_label: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    issued_at_utc: Mapped[datetime] = mapped_column(_DT6, nullable=False)
    expires_at_utc: Mapped[datetime] = mapped_column(_DT6, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(_DT6, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(_DT6, nullable=True)


class PasswordResetToken(Base):
    """ERD ``password_reset_tokens`` (stub until auth reset routes land)."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at_utc: Mapped[datetime] = mapped_column(_DT6, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(_DT6, nullable=True)


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
    changed_at: Mapped[datetime] = mapped_column(_DT6, nullable=False)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    new_value: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class ReceiptImage(Base):
    """ERD ``receipt_images`` (stub; D-01 bytes I/O is out of this PR)."""

    __tablename__ = "receipt_images"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_amount_idr: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    candidate_tx_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    candidate_client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_invoice_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(_DT6, nullable=False)
    expires_at_utc: Mapped[datetime] = mapped_column(_DT6, nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("duplicate_key", name="uq_transactions_duplicate_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    image_id: Mapped[str | None] = mapped_column(
        ForeignKey("receipt_images.id"), nullable=True, index=True
    )
    tx_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount_idr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    withheld_tax_amount_idr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    client_name_norm: Mapped[str] = mapped_column(String(255, **_NORM), default="", nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    invoice_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_no_norm: Mapped[str | None] = mapped_column(String(64, **_NORM), nullable=True)
    source_channel: Mapped[str] = mapped_column(String(32), default="other", nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    requires_clarification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # STORED generated; NULL when invoice_no_norm IS NULL (ERD r3 Keys).
    duplicate_key: Mapped[str | None] = mapped_column(
        String(512, **_NORM),
        Computed(_TX_DUP_SQL, persisted=True),
        nullable=True,
    )


class ClassificationEvent(Base):
    __tablename__ = "classification_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.id"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(_DT6, nullable=False)
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
    """Month tax snapshot. D-11: UK includes ``version``; index supports berlaku reads."""

    __tablename__ = "month_snapshots"
    __table_args__ = (
        UniqueConstraint("profile_id", "month_key", "version", name="uq_month_snapshots_version"),
        Index(
            "ix_month_snapshots_profile_month_status",
            "profile_id",
            "month_key",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), nullable=False, index=True)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
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


class QuotaCounter(Base):
    """ERD ``quota_counters`` (D-02 column names)."""

    __tablename__ = "quota_counters"
    __table_args__ = (
        UniqueConstraint("user_id", "month_key", name="uq_quota_counters_user_month"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    ai_classification_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assistant_chat_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SubscriptionOrder(Base):
    """ERD ``subscription_orders`` (stub until Midtrans; pending_slot generated)."""

    __tablename__ = "subscription_orders"
    __table_args__ = (UniqueConstraint("pending_slot", name="uq_subscription_orders_pending_slot"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    plan_id: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_idr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # STORED generated; NULL unless status='pending' and user_id set (ERD Keys).
    pending_slot: Mapped[str | None] = mapped_column(
        String(96),
        Computed(_PENDING_SLOT_SQL, persisted=True),
        nullable=True,
    )
    payment_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    expires_at_utc: Mapped[datetime] = mapped_column(_DT6, nullable=False)
    created_at: Mapped[datetime] = mapped_column(_DT6, nullable=False)


class PaymentEvent(Base):
    """ERD ``payment_events`` (stub until Midtrans webhook)."""

    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("order_id", "status", name="uq_payment_events_order_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("subscription_orders.id"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    gross_amount_idr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transaction_time: Mapped[datetime] = mapped_column(_DT6, nullable=False)
    received_at: Mapped[datetime] = mapped_column(_DT6, nullable=False)


class AuthRateLimit(Base):
    """ERD ``auth_rate_limits`` (no FK to users)."""

    __tablename__ = "auth_rate_limits"
    __table_args__ = (PrimaryKeyConstraint("subject", "window_start_utc"),)

    subject: Mapped[str] = mapped_column(String(320), nullable=False)
    window_start_utc: Mapped[datetime] = mapped_column(_DT6, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


__all__ = [
    "AuthRateLimit",
    "ClassificationEvent",
    "MonthSnapshot",
    "PasswordResetToken",
    "PaymentEvent",
    "Profile",
    "ProfileChange",
    "QuotaCounter",
    "ReceiptImage",
    "Session",
    "SubscriptionOrder",
    "Transaction",
    "User",
]
