"""Seed the two demo accounts.

Run from the project root:

    PYTHONPATH=backend .venv/bin/python backend/scripts/seed_demo.py

Idempotent: an existing account keeps its id, its password is reset to the
documented demo password, and transactions are skipped when their invoice
number already exists.
"""

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Transaction as TransactionRow  # noqa: E402
from app.models import User  # noqa: E402
from app.schemas.account import ProfileUpdate, RegisterIn  # noqa: E402
from app.schemas.transaction import TransactionCreate  # noqa: E402
from app.security import hash_password, now_utc  # noqa: E402
from app.services import auth as auth_service  # noqa: E402
from app.services import profile as profile_service  # noqa: E402
from app.services import transactions as transaction_service  # noqa: E402
from app.services.snapshot import active_ruleset  # noqa: E402

ACCOUNTS = (
    {
        "email": "gratis@klasifipajak.demo",
        "username": "gratis",
        "password": "DemoGratis10",
        "paid": False,
        "name": "Toko Sumber Makmur",
        "kbli": "47111",
        "description": "Penjualan sembako",
        "transactions": (
            {
                "tx_date": "2026-10-05",
                "amount_idr": 12_500_000,
                "client_name": "PT Sumber Makmur",
                "description": "Penjualan sembako",
                "invoice_no": "INV-G-001",
                "withheld_tax_amount_idr": 62_500,
                "source_channel": "corporate_client",
            },
            {
                "tx_date": "2026-10-12",
                "amount_idr": 4_000_000,
                "client_name": "Bapak Andi",
                "description": "Jasa konsultasi pajak",
                "invoice_no": "INV-G-002",
                "withheld_tax_amount_idr": 0,
                "source_channel": "retail",
            },
        ),
    },
    {
        "email": "berbayar@klasifipajak.demo",
        "username": "berbayar",
        "password": "DemoBayar10",
        "paid": True,
        "name": "Katering Berkah",
        "kbli": "56210",
        "description": "Katering dan penjualan makanan",
        "transactions": (
            {
                "tx_date": "2026-10-06",
                "amount_idr": 25_000_000,
                "client_name": "CV Berkah Jaya",
                "description": "Penjualan katering",
                "invoice_no": "INV-B-001",
                "withheld_tax_amount_idr": 125_000,
                "source_channel": "corporate_client",
            },
            {
                "tx_date": "2026-10-13",
                "amount_idr": 7_500_000,
                "client_name": "Ibu Sari",
                "description": "Jasa desain menu",
                "invoice_no": "INV-B-002",
                "withheld_tax_amount_idr": 0,
                "source_channel": "retail",
            },
        ),
    },
)


def normalise(value: str) -> str:
    return auth_service.normalize_identifier(value)


def ensure_user(db, spec: dict) -> User:
    user = db.scalar(select(User).where(User.email_norm == normalise(spec["email"])))
    if user is None:
        user = auth_service.register(
            db,
            RegisterIn(
                email=spec["email"],
                username=spec["username"],
                password=spec["password"],
            ),
        )
    else:
        user.password_hash = hash_password(spec["password"])
        db.commit()
    return user


def ensure_profile(db, user: User, spec: dict, ruleset) -> None:
    existing = profile_service.find_profile(db, user, ruleset.tax_year)
    profile_service.update_profile(
        db,
        user,
        ruleset.tax_year,
        ProfileUpdate(
            version=existing.version if existing is not None else 1,
            name=spec["name"],
            entity_type="orang_pribadi",
            nib_status="has_nib",
            nib_last_4="0123",
            kbli_code=spec["kbli"],
            business_description=spec["description"],
            marital_status="no",
            spouse_aggregation_active=False,
            is_new_taxpayer_current_year=True,
        ),
        ruleset,
    )


def ensure_transactions(db, user: User, spec: dict, ruleset) -> int:
    created = 0
    for row in spec["transactions"]:
        invoice = normalise(row["invoice_no"])
        exists = db.scalar(
            select(TransactionRow.id).where(
                TransactionRow.user_id == user.id,
                TransactionRow.invoice_no_norm == invoice,
            )
        )
        if exists is not None:
            continue
        transaction_service.create_transaction(
            db,
            user,
            TransactionCreate(**row),
            ruleset,
        )
        created += 1
    return created


def main() -> None:
    init_db()
    ruleset = active_ruleset()
    db = SessionLocal()
    try:
        for spec in ACCOUNTS:
            user = ensure_user(db, spec)
            ensure_profile(db, user, spec, ruleset)
            created = ensure_transactions(db, user, spec, ruleset)
            user.paid_flag = spec["paid"]
            user.valid_until_utc = now_utc() + timedelta(days=30) if spec["paid"] else None
            db.commit()
            print(f"{spec['username']}: paid={spec['paid']} transactions_added={created}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
