#!/usr/bin/env python3
"""Fail when pip-audit JSON reports HIGH or CRITICAL vulnerabilities.

pip-audit has no native severity filter. Its JSON lists vulnerability ids
(CVE / GHSA / PYSEC) but not severity. This script:

1. Reads pip-audit ``-f json`` output (stdin or --input).
2. For each vuln id, fetches OSV (``GET https://api.osv.dev/v1/vulns/{id}``).
3. Resolves severity from, in order:
   - ``database_specific.severity`` (GitHub Advisory: CRITICAL/HIGH/MEDIUM/LOW)
   - numeric CVSS base score in ``severity[]`` when present
     (CRITICAL >= 9.0, HIGH >= 7.0)
4. Exits 1 if any HIGH/CRITICAL finding remains; otherwise exits 0.

Network is required only when vulnerabilities are present. Zero vulns → no
OSV calls. Used by the ``pip-audit`` CI job (TC-HARD-04 / HB-23).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{id}"
FAIL_LEVELS = frozenset({"HIGH", "CRITICAL"})


def _score_from_severity_entry(entry: dict[str, Any]) -> float | None:
    """Extract a numeric CVSS base score from an OSV severity entry."""
    score = entry.get("score")
    if isinstance(score, (int, float)):
        return float(score)
    if isinstance(score, str):
        # Plain number as string.
        try:
            return float(score)
        except ValueError:
            pass
        # Vector strings (CVSS:3.1/...) do not embed the base score.
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

    raw = open(args.input, encoding="utf-8").read() if args.input else sys.stdin.read()
    audit = json.loads(raw or "{}")

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
