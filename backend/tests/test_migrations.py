"""Storage-lane migration and hardening checks (M50 / HB-18 / HB-21).

TC ids: TC-HARD-12, TC-HARD-23, TC-HARD-24, TC-HARD-25, TC-HARD-26.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
DOCKERFILE = REPO_ROOT / "Dockerfile"
MYSQL_INIT = REPO_ROOT / "docker" / "mysql-init.sql"

MIGRATE_URL = os.environ.get(
    "MIGRATE_DATABASE_URL",
    os.environ.get(
        "DATABASE_URL",
        "mysql+pymysql://klasifipajak_migrate:klasifipajak_migrate@127.0.0.1:3306/klasifipajak",
    ),
)


@pytest.fixture(autouse=True)
def fresh_database():
    """Override conftest: migration tests own the schema lifecycle."""
    yield


def _alembic_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    # env.py prefers MIGRATE_DATABASE_URL
    os.environ["MIGRATE_DATABASE_URL"] = url
    return cfg


def _wipe_schema(url: str) -> None:
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        rows = conn.execute(text("SHOW TABLES")).fetchall()
        for (table,) in rows:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    engine.dispose()


def test_tc_hard_12_alembic_upgrade_empty_to_head_and_downgrade():
    """TC-HARD-12: alembic upgrade empty→head (and downgrade back to base)."""
    _wipe_schema(MIGRATE_URL)
    cfg = _alembic_config(MIGRATE_URL)
    # cwd must be backend so script_location=alembic resolves
    old = os.getcwd()
    try:
        os.chdir(BACKEND_ROOT)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    finally:
        os.chdir(old)

    engine = create_engine(MIGRATE_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "2ee6fe5471b9"
        tables = {row[0] for row in conn.execute(text("SHOW TABLES")).fetchall()}
    engine.dispose()
    for required in (
        "users",
        "month_snapshots",
        "receipt_images",
        "quota_counters",
        "subscription_orders",
        "payment_events",
        "password_reset_tokens",
        "auth_rate_limits",
        "alembic_version",
    ):
        assert required in tables


def test_tc_hard_23_app_vs_migrate_mysql_grants_in_init_sql():
    """TC-HARD-23: init SQL defines distinct app (DML) vs migrate (DDL) users."""
    sql = MYSQL_INIT.read_text(encoding="utf-8")
    assert "klasifipajak_app" in sql
    assert "klasifipajak_migrate" in sql
    assert re.search(
        r"GRANT\s+SELECT\s*,\s*INSERT\s*,\s*UPDATE\s*,\s*DELETE\s+ON\s+klasifipajak\.\*\s+TO\s+'klasifipajak_app'",
        sql,
        re.I,
    )
    assert re.search(
        r"GRANT\s+ALL\s+PRIVILEGES\s+ON\s+klasifipajak\.\*\s+TO\s+'klasifipajak_migrate'",
        sql,
        re.I,
    )
    # App user must not be granted DDL verbs in this file.
    assert not re.search(
        r"GRANT\s+[^;]*\b(CREATE|ALTER|DROP|INDEX|REFERENCES)\b[^;]*klasifipajak_app",
        sql,
        re.I,
    )


def test_tc_hard_24_uk_fk_indexes_present_after_upgrade():
    """TC-HARD-24: UK/FK/indexes from ERD + D-11 present after upgrade."""
    _wipe_schema(MIGRATE_URL)
    cfg = _alembic_config(MIGRATE_URL)
    old = os.getcwd()
    try:
        os.chdir(BACKEND_ROOT)
        command.upgrade(cfg, "head")
    finally:
        os.chdir(old)

    engine = create_engine(MIGRATE_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        # D-11 UK (profile_id, month_key, version)
        uk = conn.execute(
            text(
                """
                SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'month_snapshots'
                  AND CONSTRAINT_TYPE = 'UNIQUE'
                """
            )
        ).fetchall()
        uk_names = {row[0] for row in uk}
        assert "uq_month_snapshots_version" in uk_names

        uk_cols = [
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'month_snapshots'
                      AND CONSTRAINT_NAME = 'uq_month_snapshots_version'
                    ORDER BY ORDINAL_POSITION
                    """
                )
            ).fetchall()
        ]
        assert uk_cols == ["profile_id", "month_key", "version"]

        # Index (profile_id, month_key, status)
        idx_cols = [
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT COLUMN_NAME FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'month_snapshots'
                      AND INDEX_NAME = 'ix_month_snapshots_profile_month_status'
                    ORDER BY SEQ_IN_INDEX
                    """
                )
            ).fetchall()
        ]
        assert idx_cols == ["profile_id", "month_key", "status"]

        # Sample FKs
        fks = {
            (row[0], row[1], row[2])
            for row in conn.execute(
                text(
                    """
                    SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND REFERENCED_TABLE_NAME IS NOT NULL
                    """
                )
            ).fetchall()
        }
        assert ("month_snapshots", "profile_id", "profiles") in fks
        assert ("transactions", "image_id", "receipt_images") in fks
        assert ("quota_counters", "user_id", "users") in fks
        assert ("payment_events", "order_id", "subscription_orders") in fks
    engine.dispose()


def test_tc_hard_25_dockerfile_non_root_user():
    """TC-HARD-25: Dockerfile runs as non-root USER."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^USER\s+appuser\s*$", text, re.M)
    assert "useradd" in text


def test_tc_hard_26_dockerfile_healthcheck():
    """TC-HARD-26: Dockerfile HEALTHCHECK probes /health."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^HEALTHCHECK\b", text, re.M)
    assert "/health" in text
