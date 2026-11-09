"""Storage-lane migration and hardening checks (M50 / HB-18 / HB-21).

TC ids: TC-HARD-12, TC-HARD-23, TC-HARD-24, TC-HARD-25, TC-HARD-26.

Static checks that read repo-root infra files (Dockerfile, docker/mysql-init.sql)
skip when those paths are absent — the runtime image only COPYs ``backend/``.

Migration wipe/upgrade always targets a database whose name ends in ``_test``
(default ``klasifipajak_migrate_test``), never the application schema.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pymysql
import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from alembic import command

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
DOCKERFILE = REPO_ROOT / "Dockerfile"
MYSQL_INIT = REPO_ROOT / "docker" / "mysql-init.sql"

# Dedicated schema for alembic wipe/upgrade (never the app DB).
_DEFAULT_MIGRATE_TEST_DB = "klasifipajak_migrate_test"


def _mysql_host() -> str:
    return os.environ.get("MYSQL_HOST", "127.0.0.1")


def _mysql_port() -> int:
    return int(os.environ.get("MYSQL_PORT", "3306"))


def _database_name(url: str) -> str:
    path = urlparse(url).path.lstrip("/")
    return path.split("?")[0]


def _with_database(url: str, database: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{database}"))


def require_test_schema(url: str) -> str:
    """Refuse URLs whose schema name does not end in ``_test``.

    Hard guard for wipe/upgrade helpers so a mis-set ``MIGRATE_DATABASE_URL``
    cannot drop the application schema (conftest promise).
    """
    name = _database_name(url)
    if not name.endswith("_test"):
        raise ValueError(
            f"refusing to operate on non-test schema {name!r}; "
            "migration tests require a database name ending in '_test'"
        )
    return name


def _migrate_test_url() -> str:
    """DSN for alembic wipe/upgrade: migrate credentials, ``*_test`` schema."""
    test_db = os.environ.get("MYSQL_MIGRATE_TEST_DATABASE", _DEFAULT_MIGRATE_TEST_DB)
    raw = os.environ.get("MIGRATE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if raw:
        name = _database_name(raw)
        if name.endswith("_test"):
            return raw
        return _with_database(raw, test_db)
    user = os.environ.get("MYSQL_MIGRATE_USER", "klasifipajak_migrate")
    password = os.environ.get("MYSQL_MIGRATE_PASSWORD", "klasifipajak_migrate")
    return f"mysql+pymysql://{user}:{password}@{_mysql_host()}:{_mysql_port()}/{test_db}"


def _app_dsn() -> str:
    """Runtime DML user DSN (matches docker/mysql-init.sql + compose)."""
    if url := os.environ.get("APP_DATABASE_URL"):
        return url
    user = os.environ.get("MYSQL_APP_USER", "klasifipajak_app")
    password = os.environ.get("MYSQL_APP_PASSWORD", "klasifipajak_app")
    database = os.environ.get("MYSQL_APP_DATABASE", "klasifipajak")
    return f"mysql+pymysql://{user}:{password}@{_mysql_host()}:{_mysql_port()}/{database}"


def _migrate_dsn() -> str:
    """DDL migration user DSN for the runtime grant probe (may be app schema)."""
    if url := os.environ.get("MIGRATE_DATABASE_URL"):
        # Grant probe may use migrate_test; rewrite to app schema if needed.
        # Prefer explicit APP migrate path via MYSQL_MIGRATE_* + klasifipajak.
        pass
    if url := os.environ.get("MIGRATE_DATABASE_URL"):
        # If pointed at *_test, still OK for DDL probe; also allow app schema URL
        # via MYSQL_MIGRATE_APP_DATABASE_URL.
        if app_url := os.environ.get("MIGRATE_APP_DATABASE_URL"):
            return app_url
        return url
    user = os.environ.get("MYSQL_MIGRATE_USER", "klasifipajak_migrate")
    password = os.environ.get("MYSQL_MIGRATE_PASSWORD", "klasifipajak_migrate")
    database = os.environ.get("MYSQL_MIGRATE_DATABASE", "klasifipajak")
    return f"mysql+pymysql://{user}:{password}@{_mysql_host()}:{_mysql_port()}/{database}"


@pytest.fixture(autouse=True)
def fresh_database():
    """Override conftest: migration tests own the schema lifecycle."""
    yield


def _alembic_config(url: str, monkeypatch: pytest.MonkeyPatch) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    monkeypatch.setenv("MIGRATE_DATABASE_URL", url)
    return cfg


def _wipe_schema(url: str) -> None:
    require_test_schema(url)
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


def test_wipe_schema_refuses_non_test_database():
    """Hard guard: wiping klasifipajak (no _test suffix) raises."""
    with pytest.raises(ValueError, match="non-test schema"):
        require_test_schema("mysql+pymysql://klasifipajak_migrate:x@127.0.0.1:3306/klasifipajak")
    with pytest.raises(ValueError, match="non-test schema"):
        _wipe_schema("mysql+pymysql://klasifipajak_migrate:x@127.0.0.1:3306/klasifipajak")
    assert (
        require_test_schema("mysql+pymysql://u:p@127.0.0.1:3306/klasifipajak_migrate_test")
        == "klasifipajak_migrate_test"
    )


def test_migrate_test_url_rewrites_app_schema(monkeypatch):
    """MIGRATE_DATABASE_URL on /klasifipajak is rewritten to *_test."""
    monkeypatch.setenv(
        "MIGRATE_DATABASE_URL",
        "mysql+pymysql://klasifipajak_migrate:klasifipajak_migrate@127.0.0.1:3306/klasifipajak",
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = _migrate_test_url()
    assert _database_name(url) == "klasifipajak_migrate_test"
    assert "klasifipajak_migrate" in url


def test_tc_hard_12_alembic_upgrade_empty_to_head_and_downgrade(monkeypatch):
    """TC-HARD-12: alembic upgrade empty→head (and downgrade back to base)."""
    migrate_url = _migrate_test_url()
    if not _mysql_reachable(migrate_url):
        pytest.skip(f"MySQL not reachable for migrate test URL={migrate_url}")
    _wipe_schema(migrate_url)
    cfg = _alembic_config(migrate_url, monkeypatch)
    old = os.getcwd()
    try:
        os.chdir(BACKEND_ROOT)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    finally:
        os.chdir(old)

    engine = create_engine(migrate_url, pool_pre_ping=True)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "c45af872b930"
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
    assert "klasifipajak_migrate_test" in sql
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
    # Prefer migrate credentials against a schema they can DDL (test or app).
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
        err = str(raised.value)
        assert "1142" in err or "denied" in err.lower() or "CREATE" in err
    app_engine.dispose()

    migrate_engine = create_engine(migrate_url, pool_pre_ping=True)
    with migrate_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS `{probe}`"))
        conn.execute(text(f"CREATE TABLE `{probe}` (id INT PRIMARY KEY)"))
        conn.execute(text(f"DROP TABLE `{probe}`"))
    migrate_engine.dispose()


def test_tc_hard_24_uk_fk_indexes_present_after_upgrade(monkeypatch):
    """TC-HARD-24: UK/FK/indexes from ERD r3 + D-11 present after upgrade."""
    migrate_url = _migrate_test_url()
    if not _mysql_reachable(migrate_url):
        pytest.skip(f"MySQL not reachable for migrate test URL={migrate_url}")
    _wipe_schema(migrate_url)
    cfg = _alembic_config(migrate_url, monkeypatch)
    old = os.getcwd()
    try:
        os.chdir(BACKEND_ROOT)
        command.upgrade(cfg, "head")
    finally:
        os.chdir(old)

    engine = create_engine(migrate_url, pool_pre_ping=True)
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

        # ERD r3: pending_slot STORED generated + unique index
        slot = conn.execute(
            text(
                """
                SELECT EXTRA, GENERATION_EXPRESSION
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'subscription_orders'
                  AND COLUMN_NAME = 'pending_slot'
                """
            )
        ).one()
        slot_extra, slot_expr = slot
        assert "GENERATED" in slot_extra.upper() and "STORED" in slot_extra.upper()
        assert slot_expr is not None and "pending" in slot_expr.lower()
        assert "plan_id" in slot_expr
        uk_so = {
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'subscription_orders'
                      AND CONSTRAINT_TYPE = 'UNIQUE'
                    """
                )
            ).fetchall()
        }
        assert "uq_subscription_orders_pending_slot" in uk_so

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


def test_pending_slot_generated_behaviour(monkeypatch):
    """ERD pending_slot: UK rejects duplicate pending; null user_id / non-pending → NULL."""
    migrate_url = _migrate_test_url()
    if not _mysql_reachable(migrate_url):
        pytest.skip(f"MySQL not reachable for migrate test URL={migrate_url}")
    _wipe_schema(migrate_url)
    cfg = _alembic_config(migrate_url, monkeypatch)
    old = os.getcwd()
    try:
        os.chdir(BACKEND_ROOT)
        command.upgrade(cfg, "head")
    finally:
        os.chdir(old)

    engine = create_engine(migrate_url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users
                  (id, email, email_norm, username, username_norm, password_hash,
                   paid_flag, created_at)
                VALUES
                  ('u-slot', 's@ex.com', 's@ex.com', 'slot', 'slot', 'x', 0, UTC_TIMESTAMP(6))
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO subscription_orders
                  (id, user_id, plan_id, amount_idr, status, payment_url,
                   expires_at_utc, created_at)
                VALUES
                  ('o1', 'u-slot', 'monthly_25k', 25000, 'pending', '',
                   UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))
                """
            )
        )
        slot = conn.execute(
            text("SELECT pending_slot FROM subscription_orders WHERE id = 'o1'")
        ).scalar()
        assert slot == "u-slot:monthly_25k"

    # Duplicate pending must hit uq_subscription_orders_pending_slot (own txn).
    with engine.connect() as conn:
        trans = conn.begin()
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO subscription_orders
                      (id, user_id, plan_id, amount_idr, status, payment_url,
                       expires_at_utc, created_at)
                    VALUES
                      ('o2', 'u-slot', 'monthly_25k', 25000, 'pending', '',
                       UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))
                    """
                )
            )
            trans.commit()
        trans.rollback()

    with engine.begin() as conn:
        # Non-pending → NULL slot (allows another row with same user/plan after expire)
        conn.execute(text("UPDATE subscription_orders SET status = 'expire' WHERE id = 'o1'"))
        assert (
            conn.execute(
                text("SELECT pending_slot FROM subscription_orders WHERE id = 'o1'")
            ).scalar()
            is None
        )
        conn.execute(
            text(
                """
                INSERT INTO subscription_orders
                  (id, user_id, plan_id, amount_idr, status, payment_url,
                   expires_at_utc, created_at)
                VALUES
                  ('o3', 'u-slot', 'monthly_25k', 25000, 'settlement', '',
                   UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))
                """
            )
        )
        assert (
            conn.execute(
                text("SELECT pending_slot FROM subscription_orders WHERE id = 'o3'")
            ).scalar()
            is None
        )

        # Nulling user_id clears the slot (account delete behavior)
        conn.execute(
            text(
                """
                INSERT INTO subscription_orders
                  (id, user_id, plan_id, amount_idr, status, payment_url,
                   expires_at_utc, created_at)
                VALUES
                  ('o4', 'u-slot', 'monthly_25k', 25000, 'pending', '',
                   UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))
                """
            )
        )
        assert (
            conn.execute(
                text("SELECT pending_slot FROM subscription_orders WHERE id = 'o4'")
            ).scalar()
            == "u-slot:monthly_25k"
        )
        conn.execute(text("UPDATE subscription_orders SET user_id = NULL WHERE id = 'o4'"))
        assert (
            conn.execute(
                text("SELECT pending_slot FROM subscription_orders WHERE id = 'o4'")
            ).scalar()
            is None
        )
    engine.dispose()


def _payment_event_fingerprint(conn) -> dict:
    """Columns, unique keys, rows, and alembic version for payment_events."""
    columns = [
        row[0]
        for row in conn.execute(
            text(
                """
                SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payment_events'
                ORDER BY ORDINAL_POSITION
                """
            )
        ).fetchall()
    ]
    unique_keys = [
        row[0]
        for row in conn.execute(
            text(
                """
                SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'payment_events'
                  AND CONSTRAINT_TYPE = 'UNIQUE'
                ORDER BY CONSTRAINT_NAME
                """
            )
        ).fetchall()
    ]
    rows = conn.execute(
        text(
            """
            SELECT id, order_id, status, raw_status
            FROM payment_events
            ORDER BY id
            """
        )
    ).fetchall()
    version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return {
        "columns": columns,
        "unique_keys": unique_keys,
        "rows": [tuple(row) for row in rows],
        "version": version,
    }


def test_payment_event_downgrade_refuses_duplicate_normalized_status(monkeypatch):
    """c45af872b930 downgrade must not drop raw history that shares a status.

    Two events with the same order_id and normalized status but different
    raw_status make the old unique key impossible. Downgrade -1 refuses and
    leaves the table unchanged. A single remaining row still downgrades.
    """
    migrate_url = _migrate_test_url()
    if not _mysql_reachable(migrate_url):
        pytest.skip(f"MySQL not reachable for migrate test URL={migrate_url}")
    _wipe_schema(migrate_url)
    cfg = _alembic_config(migrate_url, monkeypatch)
    old = os.getcwd()
    try:
        os.chdir(BACKEND_ROOT)
        command.upgrade(cfg, "head")
    finally:
        os.chdir(old)

    engine = create_engine(migrate_url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users
                  (id, email, email_norm, username, username_norm, password_hash,
                   paid_flag, created_at)
                VALUES
                  ('u-raw', 'raw@ex.com', 'raw@ex.com', 'rawuser', 'rawuser', 'x',
                   0, UTC_TIMESTAMP(6))
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO subscription_orders
                  (id, user_id, plan_id, amount_idr, status, payment_url,
                   expires_at_utc, created_at)
                VALUES
                  ('ord-raw', 'u-raw', 'monthly_25k', 25000, 'settlement', '',
                   UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO payment_events
                  (id, order_id, user_id, status, raw_status, gross_amount_idr,
                   transaction_time, received_at)
                VALUES
                  ('pe1', 'ord-raw', 'u-raw', 'settlement', 'capture', 25000,
                   UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)),
                  ('pe2', 'ord-raw', 'u-raw', 'settlement', 'settlement', 25000,
                   UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))
                """
            )
        )
        before = _payment_event_fingerprint(conn)
    assert before["version"] == "c45af872b930"
    assert "raw_status" in before["columns"]
    assert before["unique_keys"] == ["uq_payment_events_order_raw_status"]
    assert len(before["rows"]) == 2

    try:
        os.chdir(BACKEND_ROOT)
        with pytest.raises(RuntimeError, match="normalized status"):
            command.downgrade(cfg, "-1")
    finally:
        os.chdir(old)

    with engine.connect() as conn:
        after_refuse = _payment_event_fingerprint(conn)
    assert after_refuse == before

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM payment_events WHERE id = 'pe2'"))

    try:
        os.chdir(BACKEND_ROOT)
        command.downgrade(cfg, "-1")
    finally:
        os.chdir(old)

    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        columns = [
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT COLUMN_NAME FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payment_events'
                    """
                )
            ).fetchall()
        ]
        remaining = conn.execute(text("SELECT id, status FROM payment_events")).fetchall()
    engine.dispose()
    assert version == "b19e6a25c70a"
    assert "raw_status" not in columns
    assert remaining == [("pe1", "settlement")]


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


def test_init_db_never_calls_create_all(monkeypatch):
    """B-11 / HB-18: init_db must not create_all for any APP_ENV (including unset)."""
    import app.db as db_mod

    calls: list[object] = []

    def fake_create_all(bind):  # noqa: ANN001
        calls.append(bind)

    monkeypatch.setattr(db_mod.Base.metadata, "create_all", fake_create_all)
    # HB-01: production/staging Settings() fail closed on a default JWT secret.
    monkeypatch.setenv("JWT_SECRET", "merge-test-jwt-secret-0123456789abcdef")

    for env in ("development", "test", "production", "staging", "", "prod"):
        calls.clear()
        if env == "":
            monkeypatch.delenv("APP_ENV", raising=False)
        else:
            monkeypatch.setenv("APP_ENV", env)
        monkeypatch.setattr(db_mod, "_settings", db_mod.Settings())
        db_mod.init_db()
        assert calls == [], f"APP_ENV={env!r} unexpectedly called create_all"


def test_compose_migrate_before_api():
    """Compose runs alembic as migrate user before api (HB-18 fresh volume)."""
    compose = REPO_ROOT / "docker-compose.yml"
    if not compose.is_file():
        pytest.skip("docker-compose.yml absent (runtime image copies backend/ only)")
    text = compose.read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s*migrate:\s*$", text)
    assert "alembic" in text and "upgrade" in text
    assert "service_completed_successfully" in text
    assert "klasifipajak_migrate" in text
