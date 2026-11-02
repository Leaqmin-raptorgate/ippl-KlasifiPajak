"""Shared fixtures.

The suite runs against a disposable MySQL 8 schema, never the application
schema. Set ``DATABASE_URL`` to point elsewhere before running it.
"""

import os

# ARGON review isolation: dedicated schema so parallel lanes do not clobber us.
os.environ.setdefault(
    "DATABASE_URL",
    "mysql+pymysql://klasifipajak:klasifipajak@127.0.0.1:3306/klasifipajak_sec_m50",
)
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-change-me")
# ARGON-1: do not force TRUSTED_PROXY_COUNT=1; tests that need XFF set it themselves.

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: F401,E402  (registers the mappers)
from app.db import Base, engine  # noqa: E402
from app.engine.ruleset import load_ruleset  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def ruleset():
    """Academic PP 20/2026 ruleset shipped in the package."""
    return load_ruleset()


@pytest.fixture(autouse=True)
def fresh_database():
    """Every test starts with empty tables and leaves none behind."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    return TestClient(app)
