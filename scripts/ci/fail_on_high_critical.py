#!/usr/bin/env python3
"""Fail when pip-audit JSON reports HIGH or CRITICAL vulnerabilities.

pip-audit has no native severity filter. Its JSON lists vulnerability ids
(CVE / GHSA / PYSEC) but not severity. This script:

1. Reads pip-audit ``-f json`` output (stdin or --input).
2. For each vuln id, fetches OSV (``GET https://api.osv.dev/v1/vulns/{id}``).
3. Resolves severity from, in order:
   - ``database_specific.severity`` (GitHub Advisory: CRITICAL/HIGH/MEDIUM/LOW)
   - numeric CVSS base score in ``severity[]`` when present
   - CVSS vector strings in ``severity[].score`` (CVSS:3.0 / 3.1 self-contained;
     CVSS:4.0 via the pinned ``cvss`` package when installed)
     (CRITICAL >= 9.0, HIGH >= 7.0, MEDIUM >= 4.0, else LOW)
4. Exits 1 if any HIGH/CRITICAL finding remains; otherwise exits 0.

Fail-closed policy (default):
  - Network / HTTP errors other than 404 while looking up OSV → UNKNOWN → fail
  - Missing or unresolvable severity → UNKNOWN → fail
  - Invalid / missing pip-audit JSON → exit 1
  - Pass ``--allow-unknown`` to soften UNKNOWN (not used in CI)

Network is required only when vulnerabilities are present. Zero vulns → no
OSV calls. Used by the ``pip-audit`` CI job (TC-HARD-04 / HB-23).

CVSS:4.0 justification: the official macrovector tables are large; we optionally
use the pure-Python ``cvss==3.6`` wheel (~31 KB) when installed in CI. CVSS 3.x
scoring stays self-contained with no extra dependency.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.request
from typing import Any

OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{id}"
FAIL_LEVELS = frozenset({"HIGH", "CRITICAL"})

# CVSS v3.x metric weights (FIRST.org CVSS 3.1 §7.4).
_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
_AC = {"L": 0.77, "H": 0.44}
_PR_U = {"N": 0.85, "L": 0.62, "H": 0.27}
_PR_C = {"N": 0.85, "L": 0.68, "H": 0.5}
_UI = {"N": 0.85, "R": 0.62}
_CIA = {"N": 0.0, "L": 0.22, "H": 0.56}


def _roundup(value: float) -> float:
    """CVSS 3.1 Roundup (FIRST.org Appendix A) — float-safe to 1 decimal."""
    int_input = int(round(value * 100_000))
    if int_input % 10_000 == 0:
        return int_input / 100_000.0
    return (math.floor(int_input / 10_000) + 1) / 10.0


def _parse_vector_metrics(vector: str) -> dict[str, str] | None:
    """Parse ``CVSS:x.y/AV:N/...`` into a metric map; None if malformed."""
    if not vector.startswith("CVSS:"):
        return None
    parts = vector.split("/")
    if len(parts) < 2:
        return None
    metrics: dict[str, str] = {}
    for part in parts[1:]:
        if ":" not in part:
            return None
        key, value = part.split(":", 1)
        if not key or not value or key in metrics:
            return None
        metrics[key] = value
    return metrics


def score_cvss3_vector(vector: str) -> float | None:
    """Return CVSS 3.0/3.1 base score for a vector string, or None."""
    if not (vector.startswith("CVSS:3.0/") or vector.startswith("CVSS:3.1/")):
        return None
    m = _parse_vector_metrics(vector)
    if m is None:
        return None
    required = ("AV", "AC", "PR", "UI", "S", "C", "I", "A")
    if any(k not in m for k in required):
        return None
    try:
        scope = m["S"]
        if scope not in ("U", "C"):
            return None
        av, ac, ui = _AV[m["AV"]], _AC[m["AC"]], _UI[m["UI"]]
        pr = (_PR_C if scope == "C" else _PR_U)[m["PR"]]
        c, i, a = _CIA[m["C"]], _CIA[m["I"]], _CIA[m["A"]]
    except KeyError:
        return None

    iss = 1.0 - ((1.0 - c) * (1.0 - i) * (1.0 - a))
    if scope == "U":
        impact = 6.42 * iss
    else:
        impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
    exploitability = 8.22 * av * ac * pr * ui
    if impact <= 0:
        return 0.0
    if scope == "U":
        return _roundup(min(impact + exploitability, 10.0))
    return _roundup(min(1.08 * (impact + exploitability), 10.0))


def score_cvss4_vector(vector: str) -> float | None:
    """Return CVSS 4.0 base score when the optional ``cvss`` package is present."""
    if not vector.startswith("CVSS:4.0/"):
        return None
    try:
        from cvss import CVSS4  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        return float(CVSS4(vector).scores()[0])
    except Exception:  # noqa: BLE001 — malformed vector → treat as unparsed
        return None


def score_cvss_vector(vector: str) -> float | None:
    """Dispatch CVSS:3.x (self-contained) and CVSS:4.0 (optional dep)."""
    score = score_cvss3_vector(vector)
    if score is not None:
        return score
    return score_cvss4_vector(vector)


def _score_from_severity_entry(entry: dict[str, Any]) -> float | None:
    """Extract a numeric CVSS base score from an OSV severity entry."""
    score = entry.get("score")
    if isinstance(score, (int, float)):
        return float(score)
    if isinstance(score, str):
        stripped = score.strip()
        try:
            return float(stripped)
        except ValueError:
            pass
        return score_cvss_vector(stripped)
    return None


def _level_from_cvss(score: float) -> str:
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW"


def resolve_severity(osv: dict[str, Any]) -> str:
    """Return CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN for one OSV document."""
    db = osv.get("database_specific") or {}
    label = db.get("severity")
    if isinstance(label, str) and label.strip():
        return label.strip().upper()

    for entry in osv.get("severity") or []:
        if not isinstance(entry, dict):
            continue
        numeric = _score_from_severity_entry(entry)
        if numeric is not None:
            return _level_from_cvss(numeric)

    return "UNKNOWN"


def fetch_osv(vuln_id: str, timeout: float = 30.0) -> dict[str, Any] | None:
    url = OSV_VULN_URL.format(id=urllib.request.quote(vuln_id, safe=""))
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def iter_findings(audit: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return (package, version, vuln_id) triples from pip-audit JSON."""
    out: list[tuple[str, str, str]] = []
    for dep in audit.get("dependencies") or []:
        name = dep.get("name") or "?"
        version = dep.get("version") or "?"
        for vuln in dep.get("vulns") or []:
            vid = vuln.get("id")
            if vid:
                out.append((name, version, vid))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        "-i",
        help="Path to pip-audit JSON (default: stdin)",
    )
    parser.add_argument(
        "--allow-unknown",
        action="store_true",
        help="Do not fail when severity cannot be resolved (default: fail closed)",
    )
    args = parser.parse_args(argv)

    try:
        raw = open(args.input, encoding="utf-8").read() if args.input else sys.stdin.read()
        audit = json.loads(raw or "{}")
        if not isinstance(audit, dict):
            print("FAIL: pip-audit JSON root must be an object", file=sys.stderr)
            return 1
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read pip-audit JSON ({exc})", file=sys.stderr)
        return 1

    findings = iter_findings(audit)
    if not findings:
        print("pip-audit gate: no vulnerabilities reported")
        return 0

    blockers: list[str] = []
    reports: list[str] = []
    severity_cache: dict[str, str] = {}

    for pkg, ver, vid in findings:
        if vid not in severity_cache:
            try:
                osv = fetch_osv(vid)
            except Exception as exc:  # noqa: BLE001 — fail closed
                severity_cache[vid] = "UNKNOWN"
                reports.append(f"  ! {pkg}=={ver} {vid}: OSV lookup failed ({exc})")
                if not args.allow_unknown:
                    blockers.append(
                        f"  - {pkg}=={ver} {vid} severity=UNKNOWN (lookup failed: {exc})"
                    )
                continue
            severity_cache[vid] = "UNKNOWN" if osv is None else resolve_severity(osv)

        level = severity_cache[vid]
        line = f"  - {pkg}=={ver} {vid} severity={level}"
        reports.append(line)
        if level in FAIL_LEVELS:
            blockers.append(line)
        elif level == "UNKNOWN" and not args.allow_unknown:
            blockers.append(line + " (unresolved; treat as blocker)")

    print("pip-audit gate findings:")
    print("\n".join(reports))

    if blockers:
        print("\nFAIL: high/critical (or unresolved) vulnerabilities:")
        print("\n".join(blockers))
        return 1

    print("\nOK: no high/critical vulnerabilities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
