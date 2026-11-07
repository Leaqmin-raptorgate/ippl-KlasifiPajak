"""Release version has one value in the Python package and the API."""

import re
import tomllib
from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parents[2]


def test_api_version_matches_pyproject():
    """CONTRIBUTING.md release step 2: pyproject.toml and main.py agree."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert app.version == project["version"]


def test_version_is_semver():
    """The release version is MAJOR.MINOR.PATCH, not a free-form string."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", app.version)
