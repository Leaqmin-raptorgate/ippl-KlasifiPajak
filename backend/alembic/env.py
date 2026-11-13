"""Alembic environment for KlasifiPajak (MySQL 8).

Uses ``MIGRATE_DATABASE_URL`` when set, otherwise ``DATABASE_URL``. The
migration MySQL user must hold DDL; the runtime app user must not.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  — register mappers on Base.metadata
from alembic import context
from app.db import Base

config = context.config

if config.config_file_name is not None:
    # Keep loggers that already exist. The default would disable every app logger
    # created before this runs (for example `app.services.payments` once a test
    # migrates in-process), and their records would silently vanish.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    return os.environ.get("MIGRATE_DATABASE_URL") or os.environ.get(
        "DATABASE_URL",
        "mysql+pymysql://klasifipajak_migrate:klasifipajak_migrate@127.0.0.1:3306/klasifipajak",
    )


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
