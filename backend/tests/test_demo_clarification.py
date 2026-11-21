"""FR-14: the demo account has a row that asks for clarification."""

import importlib.util
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Transaction, User
from app.services.snapshots_store import freeze_today_jakarta


def test_seed_includes_a_clarification(client):
    path = Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py"
    spec = importlib.util.spec_from_file_location("demo_seed_clarification", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with freeze_today_jakarta(date(2026, 11, 17)):
        module.main()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email_norm == "gratis@klasifipajak.demo"))
        row = db.scalar(
            select(Transaction).where(
                Transaction.user_id == user.id, Transaction.invoice_no == "INV-G-003"
            )
        )
        assert row is not None
        assert row.requires_clarification is True
