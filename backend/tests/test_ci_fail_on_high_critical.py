"""Unit tests for scripts/ci/fail_on_high_critical.py (TC-HARD-04 / HB-23)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "ci" / "fail_on_high_critical.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("fail_on_high_critical", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


gate = _load_gate()


# Known FIRST.org examples / calculator anchors.
VECTOR_CRITICAL = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"  # 9.8
VECTOR_HIGH = "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H"  # 8.8
VECTOR_MEDIUM = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:N"  # 5.3
VECTOR_LOW = "CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N"  # 1.8


def _audit(*vuln_ids: str, package: str = "demo", version: str = "1.0.0") -> dict[str, Any]:
    return {
        "dependencies": [
            {
                "name": package,
                "version": version,
                "vulns": [{"id": vid} for vid in vuln_ids],
            }
        ]
    }


def test_score_cvss3_critical_high_medium_low():
    assert gate.score_cvss3_vector(VECTOR_CRITICAL) == pytest.approx(9.8)
    assert gate.score_cvss3_vector(VECTOR_HIGH) == pytest.approx(8.8)
    assert gate.score_cvss3_vector(VECTOR_MEDIUM) == pytest.approx(5.3)
    assert gate.score_cvss3_vector(VECTOR_LOW) == pytest.approx(1.8)
    assert gate._level_from_cvss(9.8) == "CRITICAL"
    assert gate._level_from_cvss(8.8) == "HIGH"
    assert gate._level_from_cvss(5.3) == "MEDIUM"
    assert gate._level_from_cvss(1.8) == "LOW"


def test_resolve_severity_from_cvss_vector_string():
    osv = {"severity": [{"type": "CVSS_V3", "score": VECTOR_CRITICAL}]}
    assert gate.resolve_severity(osv) == "CRITICAL"
    osv_med = {"severity": [{"type": "CVSS_V3", "score": VECTOR_MEDIUM}]}
    assert gate.resolve_severity(osv_med) == "MEDIUM"


def test_resolve_severity_prefers_database_specific_label():
    osv = {
        "database_specific": {"severity": "medium"},
        "severity": [{"type": "CVSS_V3", "score": VECTOR_CRITICAL}],
    }
    assert gate.resolve_severity(osv) == "MEDIUM"


def test_resolve_severity_missing_is_unknown():
    assert gate.resolve_severity({}) == "UNKNOWN"
    assert gate.resolve_severity({"severity": []}) == "UNKNOWN"
    assert gate.resolve_severity({"severity": [{"type": "CVSS_V3", "score": "not-a-vector"}]}) == (
        "UNKNOWN"
    )


def test_main_high_or_critical_vector_fails(tmp_path: Path):
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(_audit("VULN-CRIT")), encoding="utf-8")

    def fake_fetch(vid: str, timeout: float = 30.0):
        return {"severity": [{"type": "CVSS_V3", "score": VECTOR_CRITICAL}]}

    with patch.object(gate, "fetch_osv", side_effect=fake_fetch):
        assert gate.main(["--input", str(audit_path)]) == 1


def test_main_medium_vector_passes(tmp_path: Path):
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(_audit("VULN-MED")), encoding="utf-8")

    def fake_fetch(vid: str, timeout: float = 30.0):
        return {"severity": [{"type": "CVSS_V3", "score": VECTOR_MEDIUM}]}

    with patch.object(gate, "fetch_osv", side_effect=fake_fetch):
        assert gate.main(["--input", str(audit_path)]) == 0


def test_main_missing_severity_is_unknown_fail_closed(tmp_path: Path):
    """Policy: unresolved severity → UNKNOWN → fail (unless --allow-unknown)."""
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(_audit("VULN-NONE")), encoding="utf-8")

    with patch.object(gate, "fetch_osv", return_value={}):
        assert gate.main(["--input", str(audit_path)]) == 1
        assert gate.main(["--input", str(audit_path), "--allow-unknown"]) == 0


def test_main_network_error_fail_closed(tmp_path: Path):
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(_audit("VULN-NET")), encoding="utf-8")

    with patch.object(gate, "fetch_osv", side_effect=TimeoutError("osv unreachable")):
        assert gate.main(["--input", str(audit_path)]) == 1


def test_main_invalid_json_fail_closed(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    assert gate.main(["--input", str(bad)]) == 1


def test_main_no_vulnerabilities_ok(tmp_path: Path):
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps({"dependencies": []}), encoding="utf-8")
    assert gate.main(["--input", str(audit_path)]) == 0


def test_main_missing_file_fails(tmp_path: Path):
    missing = tmp_path / "no-such-audit.json"
    assert gate.main(["--input", str(missing)]) == 1


def test_main_empty_file_fails(tmp_path: Path):
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    assert gate.main(["--input", str(empty)]) == 1
    whitespace = tmp_path / "ws.json"
    whitespace.write_text("   \n\t  ", encoding="utf-8")
    assert gate.main(["--input", str(whitespace)]) == 1


def test_main_root_list_fails(tmp_path: Path):
    path = tmp_path / "list.json"
    path.write_text("[]", encoding="utf-8")
    assert gate.main(["--input", str(path)]) == 1


def test_main_dependencies_missing_fails(tmp_path: Path):
    path = tmp_path / "no-deps.json"
    path.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    assert gate.main(["--input", str(path)]) == 1


def test_main_dependencies_not_list_fails(tmp_path: Path):
    path = tmp_path / "bad-deps.json"
    path.write_text(json.dumps({"dependencies": {"name": "x"}}), encoding="utf-8")
    assert gate.main(["--input", str(path)]) == 1


@pytest.mark.parametrize(
    "label,expected",
    [
        ("UNSPECIFIED", "UNKNOWN"),
        ("NONE", "UNKNOWN"),
        ("WEIRD_LABEL", "UNKNOWN"),
        ("MODERATE", "MODERATE"),
        ("medium", "MEDIUM"),
        ("LOW", "LOW"),
        ("HIGH", "HIGH"),
        ("CRITICAL", "CRITICAL"),
        (" critical ", "CRITICAL"),
    ],
)
def test_resolve_severity_database_specific_allowlist(label: str, expected: str):
    osv = {"database_specific": {"severity": label}}
    assert gate.resolve_severity(osv) == expected


def test_resolve_severity_max_across_cvss_entries():
    """First entry low, later entry high → MAX wins (HIGH), not first parseable."""
    osv = {
        "severity": [
            {"type": "CVSS_V3", "score": VECTOR_LOW},
            {"type": "CVSS_V3", "score": VECTOR_HIGH},
        ]
    }
    assert gate.resolve_severity(osv) == "HIGH"


def test_main_clean_dependencies_exits_zero(tmp_path: Path):
    """Valid clean pip-audit JSON with empty deps → exit 0."""
    audit_path = tmp_path / "clean.json"
    audit_path.write_text(json.dumps({"dependencies": []}), encoding="utf-8")
    assert gate.main(["--input", str(audit_path)]) == 0


def test_main_unspecified_label_fail_closed(tmp_path: Path):
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(_audit("VULN-UNSPEC")), encoding="utf-8")

    with patch.object(
        gate,
        "fetch_osv",
        return_value={"database_specific": {"severity": "UNSPECIFIED"}},
    ):
        assert gate.main(["--input", str(audit_path)]) == 1


def test_main_moderate_label_passes(tmp_path: Path):
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(_audit("VULN-MOD")), encoding="utf-8")

    with patch.object(
        gate,
        "fetch_osv",
        return_value={"database_specific": {"severity": "MODERATE"}},
    ):
        assert gate.main(["--input", str(audit_path)]) == 0
