"""Shared fixtures for engine tests."""

import pytest

from klasifipajak.ruleset import load_ruleset


@pytest.fixture
def ruleset():
    """Academic PP 20/2026 ruleset shipped in the package."""
    return load_ruleset()
