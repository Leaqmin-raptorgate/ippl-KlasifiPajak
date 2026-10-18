"""Database engine and request-scoped sessions.

MySQL 8 is the only supported store (ERD v1.2.2). Instants are UTC
``DATETIME(6)`` values written by the application.
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
    """Create tables for a fresh local database."""
    import app.models  # noqa: F401  (registers the mappers)

    Base.metadata.create_all(engine)
