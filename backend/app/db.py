"""Database engine and request-scoped sessions.

MySQL 8 is the only supported store (ERD r3). Instants are UTC
``DATETIME(6)`` values written by the application. Schema changes go through
Alembic; ``create_all`` is fail-closed to an explicit APP_ENV allowlist.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import Settings

# create_all only for local/dev and the test suite — never staging/prod/empty.
_CREATE_ALL_ENVS = frozenset({"development", "test"})


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
    """Create tables only when ``APP_ENV`` is development or test (fail-closed).

    Production and any other/unknown env must use Alembic
    (``alembic upgrade head``). Tests also call ``Base.metadata.create_all``
    directly in conftest.
    """
    import app.models  # noqa: F401  (registers the mappers)

    if _settings.app_env.casefold() not in _CREATE_ALL_ENVS:
        return
    Base.metadata.create_all(engine)
