"""Database engine and request-scoped sessions.

MySQL 8 is the only supported store (ERD r3). Instants are UTC
``DATETIME(6)`` values written by the application. Schema changes go through
Alembic only — ``create_all`` is never invoked at API boot (HB-18 / B-11).
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import Settings


class Base(DeclarativeBase):
    """Declarative base for every table."""


_settings = Settings()
engine = create_engine(_settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Yield one session and close it after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Register mappers; do not create tables.

    Schema is applied by ``alembic upgrade head`` (compose migrate service /
    ops). Tests call ``Base.metadata.create_all`` in conftest only. Fail-closed
    when ``APP_ENV`` is unset or any non-test runtime: never ``create_all`` here
    (B-11), so a DML-only app user cannot hit MySQL 1142 on boot.
    """
    import app.models  # noqa: F401  (registers the mappers)
