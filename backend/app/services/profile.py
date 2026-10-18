"""Profile use cases. Versioned updates with an audit trail."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.engine import Ruleset
from app.models import Profile as ProfileRow
from app.models import ProfileChange, User
from app.schemas.account import AuditEntry, ProfileOut, ProfileUpdate
from app.security import new_id, now_utc
from app.services.snapshots_store import rebuild

_NIB = re.compile(r"^\d{4}$")
_BUSINESS_FIELDS = (
    "name",
    "entity_type",
    "nib_status",
    "nib_last_4",
    "kbli_code",
    "business_description",
    "marital_status",
    "spouse_aggregation_active",
    "is_new_taxpayer_current_year",
    "spouse_current_usaha_idr",
    "spouse_current_pekerjaan_bebas_idr",
    "spouse_current_already_final_idr",
    "prior_user_usaha_idr",
    "prior_user_pekerjaan_bebas_idr",
    "prior_user_already_final_idr",
    "prior_spouse_usaha_idr",
    "prior_spouse_pekerjaan_bebas_idr",
    "prior_spouse_already_final_idr",
)


def find_profile(db: Session, user: User, tax_year: int) -> ProfileRow | None:
    return db.scalar(
        select(ProfileRow).where(
            ProfileRow.user_id == user.id,
            ProfileRow.tax_year == tax_year,
        )
    )


def get_profile(db: Session, user: User, tax_year: int) -> ProfileOut:
    profile = find_profile(db, user, tax_year)
    if profile is None:
        raise ApiError(
            404,
            "PROFILE_NOT_FOUND",
            "Profil untuk tahun pajak yang dipilih belum dibuat.",
        )
    return profile_out(db, profile)


def update_profile(
    db: Session, user: User, tax_year: int, payload: ProfileUpdate, ruleset: Ruleset
) -> ProfileOut:
    profile = find_profile(db, user, tax_year)
    if profile is None:
        profile = ProfileRow(
            id=new_id("prf_"),
            user_id=user.id,
            tax_year=tax_year,
            version=1,
        )
        db.add(profile)
        db.flush()
        current_version = 1
    else:
        current_version = profile.version

    if payload.version != current_version:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "Data ini sudah diubah di perangkat lain. Muat ulang, lalu simpan lagi.",
        )
    if payload.entity_type != "orang_pribadi":
        raise ApiError(
            422,
            "ENTITY_TYPE_NOT_SUPPORTED",
            "KlasifiPajak v1 hanya mendukung wajib pajak orang_pribadi.",
        )
    if payload.nib_last_4 is not None and not _NIB.match(payload.nib_last_4):
        raise ApiError(
            422,
            "INVALID_NIB_FORMAT",
            "Kolom nib_last_4 harus berupa tepat 4 digit angka.",
        )

    changed = False
    for field in _BUSINESS_FIELDS:
        new_value = getattr(payload, field)
        old_value = getattr(profile, field)
        if new_value != old_value:
            db.add(
                ProfileChange(
                    id=new_id("chg_"),
                    profile_id=profile.id,
                    changed_at=now_utc(),
                    field=field,
                    old_value="" if old_value is None else str(old_value),
                    new_value="" if new_value is None else str(new_value),
                )
            )
            setattr(profile, field, new_value)
            changed = True

    if changed:
        profile.version = current_version + 1
        rebuild(db, profile, ruleset)
    db.commit()
    return profile_out(db, profile)


def profile_out(db: Session, profile: ProfileRow) -> ProfileOut:
    audit = db.scalars(
        select(ProfileChange)
        .where(ProfileChange.profile_id == profile.id)
        .order_by(ProfileChange.changed_at)
    ).all()
    masked = f"*********{profile.nib_last_4}" if profile.nib_last_4 else None
    return ProfileOut(
        id=profile.id,
        user_id=profile.user_id,
        tax_year=profile.tax_year,
        name=profile.name,
        entity_type=profile.entity_type,
        nib_status=profile.nib_status,
        nib_masked=masked,
        kbli_code=profile.kbli_code,
        business_description=profile.business_description,
        marital_status=profile.marital_status,
        spouse_aggregation_active=profile.spouse_aggregation_active,
        is_new_taxpayer_current_year=profile.is_new_taxpayer_current_year,
        version=profile.version,
        spouse_current_usaha_idr=profile.spouse_current_usaha_idr,
        spouse_current_pekerjaan_bebas_idr=profile.spouse_current_pekerjaan_bebas_idr,
        spouse_current_already_final_idr=profile.spouse_current_already_final_idr,
        prior_user_usaha_idr=profile.prior_user_usaha_idr,
        prior_user_pekerjaan_bebas_idr=profile.prior_user_pekerjaan_bebas_idr,
        prior_user_already_final_idr=profile.prior_user_already_final_idr,
        prior_spouse_usaha_idr=profile.prior_spouse_usaha_idr,
        prior_spouse_pekerjaan_bebas_idr=profile.prior_spouse_pekerjaan_bebas_idr,
        prior_spouse_already_final_idr=profile.prior_spouse_already_final_idr,
        audit_trail=tuple(
            AuditEntry(
                changed_at=row.changed_at.isoformat() + "Z",
                field=row.field,
                old_value=row.old_value,
                new_value=row.new_value,
            )
            for row in audit
        ),
    )
