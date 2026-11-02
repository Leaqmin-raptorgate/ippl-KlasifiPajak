"""Storage-lane migration and hardening checks (M50 / HB-18 / HB-21).

TC ids: TC-HARD-12, TC-HARD-23, TC-HARD-24, TC-HARD-25, TC-HARD-26.

Static checks that read repo-root infra files (Dockerfile, docker/mysql-init.sql)
skip when those paths are absent — the runtime image only COPYs ``backend/``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pymysql
import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

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


def _mysql_host() -> str:
    return os.environ.get("MYSQL_HOST", "127.0.0.1")


def _mysql_port() -> int:
    return int(os.environ.get("MYSQL_PORT", "3306"))


def _app_dsn() -> str:
    """Runtime DML user DSN (matches docker/mysql-init.sql + compose)."""
    if url := os.environ.get("APP_DATABASE_URL"):
        return url
    user = os.environ.get("MYSQL_APP_USER", "klasifipajak_app")
    password = os.environ.get("MYSQL_APP_PASSWORD", "klasifipajak_app")
    database = os.environ.get("MYSQL_APP_DATABASE", "klasifipajak")
    return f"mysql+pymysql://{user}:{password}@{_mysql_host()}:{_mysql_port()}/{database}"


def _migrate_dsn() -> str:
    """DDL migration user DSN (matches docker/mysql-init.sql + compose)."""
    if url := os.environ.get("MIGRATE_DATABASE_URL"):
        return url
    user = os.environ.get("MYSQL_MIGRATE_USER", "klasifipajak_migrate")
    password = os.environ.get("MYSQL_MIGRATE_PASSWORD", "klasifipajak_migrate")
    database = os.environ.get("MYSQL_MIGRATE_DATABASE", "klasifipajak")
    return f"mysql+pymysql://{user}:{password}@{_mysql_host()}:{_mysql_port()}/{database}"


@pytest.fixture(autouse=True)
def fresh_database():
    """Override conftest: migration tests own the schema lifecycle."""
    yield


def _alembic_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
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


def _mysql_reachable(url: str) -> bool:
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


def test_tc_hard_12_alembic_upgrade_empty_to_head_and_downgrade():
    """TC-HARD-12: alembic upgrade empty→head (and downgrade back to base)."""
    if not _mysql_reachable(MIGRATE_URL):
        pytest.skip(f"MySQL not reachable for MIGRATE_URL={MIGRATE_URL}")
    _wipe_schema(MIGRATE_URL)
    cfg = _alembic_config(MIGRATE_URL)
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
        assert version == "1320d317fad2"
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
    """TC-HARD-23 (static): init SQL defines distinct app (DML) vs migrate (DDL) users.

    Skips inside the runtime image, which only COPYs ``backend/`` and has no
    ``docker/mysql-init.sql`` at the repo root.
    """
    if not MYSQL_INIT.is_file():
        pytest.skip(
            f"docker/mysql-init.sql not present at {MYSQL_INIT} "
            "(runtime image copies backend/ only; host/CI checkout runs this assert)"
        )
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
    assert not re.search(
        r"GRANT\s+[^;]*\b(CREATE|ALTER|DROP|INDEX|REFERENCES)\b[^;]*klasifipajak_app",
        sql,
        re.I,
    )


def test_tc_hard_23_runtime_app_denied_migrate_allowed_ddl():
    """TC-HARD-23 (runtime): app user cannot DDL; migrate user can.

    Credentials/host come from env matching ``docker/mysql-init.sql`` / compose
    (``APP_DATABASE_URL`` / ``MIGRATE_DATABASE_URL`` or ``MYSQL_APP_*`` /
    ``MYSQL_MIGRATE_*``). Skips when MySQL or those users are unreachable.
    """
    app_url = _app_dsn()
    migrate_url = _migrate_dsn()
    if not _mysql_reachable(app_url):
        pytest.skip(f"app MySQL user not reachable ({app_url.split('@')[-1]})")
    if not _mysql_reachable(migrate_url):
        pytest.skip(f"migrate MySQL user not reachable ({migrate_url.split('@')[-1]})")

    probe = "tc_hard_23_probe_ddl"
    app_engine = create_engine(app_url, pool_pre_ping=True)
    with app_engine.connect() as conn:
        with pytest.raises((OperationalError, ProgrammingError, pymysql.err.Error)) as raised:
            conn.execute(text(f"CREATE TABLE `{probe}` (id INT PRIMARY KEY)"))
            conn.commit()
        # MySQL 1142 = ER_TABLEACCESS_DENIED_ERROR
        err = str(raised.value)
        assert "1142" in err or "denied" in err.lower() or "CREATE" in err
    app_engine.dispose()

    migrate_engine = create_engine(migrate_url, pool_pre_ping=True)
    with migrate_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS `{probe}`"))
        conn.execute(text(f"CREATE TABLE `{probe}` (id INT PRIMARY KEY)"))
        conn.execute(text(f"DROP TABLE `{probe}`"))
    migrate_engine.dispose()


def test_tc_hard_24_uk_fk_indexes_present_after_upgrade():
    """TC-HARD-24: UK/FK/indexes from ERD r3 + D-11 present after upgrade."""
    if not _mysql_reachable(MIGRATE_URL):
        pytest.skip(f"MySQL not reachable for MIGRATE_URL={MIGRATE_URL}")
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

        # ERD r3: null-safe transactions UK via STORED generated duplicate_key
        gen = conn.execute(
            text(
                """
                SELECT EXTRA, GENERATION_EXPRESSION, COLLATION_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'transactions'
                  AND COLUMN_NAME = 'duplicate_key'
                """
            )
        ).one()
        extra, expression, gen_collation = gen
        assert "GENERATED" in extra.upper()
        assert "STORED" in extra.upper()
        assert expression is not None and "invoice_no_norm" in expression
        assert gen_collation == "utf8mb4_bin"

        uk_tx = {
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'transactions'
                      AND CONSTRAINT_TYPE = 'UNIQUE'
                    """
                )
            ).fetchall()
        }
        assert "uq_transactions_duplicate_key" in uk_tx

        uk_tx_cols = [
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'transactions'
                      AND CONSTRAINT_NAME = 'uq_transactions_duplicate_key'
                    ORDER BY ORDINAL_POSITION
                    """
                )
            ).fetchall()
        ]
        assert uk_tx_cols == ["duplicate_key"]

        # ERD r3: norm columns use utf8mb4_bin (not 0900_ai_ci)
        coll_rows = conn.execute(
            text(
                """
                SELECT TABLE_NAME, COLUMN_NAME, COLLATION_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND (
                    (TABLE_NAME = 'users' AND COLUMN_NAME IN ('email_norm', 'username_norm'))
                    OR (TABLE_NAME = 'transactions'
                        AND COLUMN_NAME IN ('client_name_norm', 'invoice_no_norm'))
                  )
                """
            )
        ).fetchall()
        got = {(r[0], r[1]): r[2] for r in coll_rows}
        for key in (
            ("users", "email_norm"),
            ("users", "username_norm"),
            ("transactions", "client_name_norm"),
            ("transactions", "invoice_no_norm"),
        ):
            assert got.get(key) == "utf8mb4_bin", f"{key} collation={got.get(key)}"

        # ERD r3: instants are DATETIME(6)
        dt_type = conn.execute(
            text(
                """
                SELECT COLUMN_TYPE FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'users' AND COLUMN_NAME = 'created_at'
                """
            )
        ).scalar()
        assert dt_type == "datetime(6)"
    engine.dispose()


def test_tc_hard_25_dockerfile_non_root_user():
    """TC-HARD-25: Dockerfile runs as non-root USER.

    Skips inside the runtime image (``COPY backend`` only; no repo-root Dockerfile).
    """
    if not DOCKERFILE.is_file():
        pytest.skip(
            f"Dockerfile not present at {DOCKERFILE} "
            "(runtime image copies backend/ only; host/CI checkout runs this assert)"
        )
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^USER\s+appuser\s*$", text, re.M)
    assert "useradd" in text


def test_tc_hard_26_dockerfile_healthcheck():
    """TC-HARD-26: Dockerfile HEALTHCHECK probes /health.

    Skips inside the runtime image (``COPY backend`` only; no repo-root Dockerfile).
    """
    if not DOCKERFILE.is_file():
        pytest.skip(
            f"Dockerfile not present at {DOCKERFILE} "
            "(runtime image copies backend/ only; host/CI checkout runs this assert)"
        )
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^HEALTHCHECK\b", text, re.M)
    assert "/health" in text


def test_init_db_create_all_fail_closed_allowlist(monkeypatch):
    """create_all runs only when APP_ENV casefolded is development or test."""
    import app.db as db_mod

    calls: list[object] = []

    def fake_create_all(bind):  # noqa: ANN001
        calls.append(bind)

    monkeypatch.setattr(db_mod.Base.metadata, "create_all", fake_create_all)

    for env, expect_call in (
        ("development", True),
        ("Development", True),
        ("test", True),
        ("TEST", True),
        ("production", False),
        ("staging", False),
        ("", False),
        ("prod", False),
    ):
        calls.clear()
        monkeypatch.setenv("APP_ENV", env)
        # Settings() reads env at property access time for app_env
        monkeypatch.setattr(db_mod, "_settings", db_mod.Settings())
        db_mod.init_db()
        assert bool(calls) is expect_call, f"APP_ENV={env!r} calls={calls}"
