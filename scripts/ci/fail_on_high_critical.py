#!/usr/bin/env python3
"""Fail when pip-audit JSON reports HIGH or CRITICAL vulnerabilities.

pip-audit has no native severity filter. Its JSON lists vulnerability ids
(CVE / GHSA / PYSEC) but not severity. This script:

1. Reads pip-audit ``-f json`` output (stdin or --input).
2. For each vuln id, fetches OSV (``GET https://api.osv.dev/v1/vulns/{id}``).
3. Resolves severity as the MAX of:
   - ``database_specific.severity`` — allowlist only:
     HIGH/CRITICAL fail; MODERATE/MEDIUM/LOW pass (GHSA uses MODERATE);
     any other label → UNKNOWN → fail
   - numeric / vector CVSS scores in ``severity[]`` (MAX across entries;
     CVSS:3.x self-contained; CVSS:4.0 via pinned ``cvss`` when installed)
     (CRITICAL >= 9.0, HIGH >= 7.0, MEDIUM >= 4.0, else LOW)
   so a GHSA MEDIUM label cannot hide a CVSS 9.8.
4. Exits 1 if any HIGH/CRITICAL/UNKNOWN finding remains; otherwise exits 0.

Fail-closed policy (default):
  - Network / HTTP errors other than 404 while looking up OSV → UNKNOWN → fail
  - Missing or unresolvable severity → UNKNOWN → fail
  - Missing/empty input, malformed JSON, non-object root, or ``dependencies``
    missing / not a list / empty → exit 1
  - Malformed shapes (dep not a dict, ``vulns`` not a list,
    ``database_specific`` not a dict, etc.) → exit 1 with a clear message
  - Vuln entry with no id → UNKNOWN → fail
  - ``--pip-audit-rc 1`` with zero vulns in JSON → exit 1 (pip-audit claimed
    findings the gate cannot see)
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
# GHSA uses MODERATE; only these non-failing database_specific labels pass.
PASS_LABELS = frozenset({"MODERATE", "MEDIUM", "LOW"})
MISSING_VULN_ID = "<missing-id>"

# Higher rank wins when combining label + CVSS. UNKNOWN ranks highest so it
# always fails closed when present.
_SEVERITY_RANK = {
    "LOW": 1,
    "MEDIUM": 2,
    "MODERATE": 2,
    "HIGH": 3,
    "CRITICAL": 4,
    "UNKNOWN": 5,
}

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


def _max_severity(*levels: str | None) -> str:
    """Return the highest-ranked severity among non-None levels."""
    best: str | None = None
    for level in levels:
        if level is None:
            continue
        if best is None or _SEVERITY_RANK[level] > _SEVERITY_RANK[best]:
            best = level
    return best if best is not None else "UNKNOWN"


def _label_severity(osv: dict[str, Any]) -> str | None:
    """Parse database_specific.severity; None if absent."""
    db = osv.get("database_specific")
    if db is None:
        return None
    if not isinstance(db, dict):
        raise ValueError("database_specific must be an object")
    label = db.get("severity")
    if not isinstance(label, str) or not label.strip():
        return None
    normalized = label.strip().upper()
    if normalized in FAIL_LEVELS or normalized in PASS_LABELS:
        return normalized
    return "UNKNOWN"


def _cvss_severity(osv: dict[str, Any]) -> str | None:
    """MAX parseable CVSS level from severity[]; None if none parse."""
    entries = osv.get("severity")
    if entries is None:
        return None
    if not isinstance(entries, list):
        raise ValueError("severity must be a list")
    max_score: float | None = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        numeric = _score_from_severity_entry(entry)
        if numeric is not None:
            max_score = numeric if max_score is None else max(max_score, numeric)
    if max_score is None:
        return None
    return _level_from_cvss(max_score)


def resolve_severity(osv: dict[str, Any]) -> str:
    """Return CRITICAL/HIGH/MEDIUM/LOW/MODERATE/UNKNOWN for one OSV document.

    Takes the MAX of the allowlisted ``database_specific.severity`` label and
    the MAX CVSS score across ``severity[]``. A MEDIUM label cannot hide a
    CRITICAL CVSS vector.
    """
    if not isinstance(osv, dict):
        raise ValueError("OSV document must be an object")
    label = _label_severity(osv)
    cvss = _cvss_severity(osv)
    if label is None and cvss is None:
        return "UNKNOWN"
    return _max_severity(label, cvss)


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
    """Return (package, version, vuln_id) triples from pip-audit JSON.

    A vuln entry with a missing/empty id yields ``MISSING_VULN_ID`` so the
    gate can treat it as UNKNOWN. Raises ``ValueError`` on malformed shapes.
    """
    out: list[tuple[str, str, str]] = []
    deps = audit.get("dependencies")
    if not isinstance(deps, list):
        raise ValueError("dependencies must be a list")
    for index, dep in enumerate(deps):
        if not isinstance(dep, dict):
            raise ValueError(f"dependencies[{index}] must be an object")
        name = dep.get("name") or "?"
        version = dep.get("version") or "?"
        vulns = dep.get("vulns")
        if vulns is None:
            vulns = []
        if not isinstance(vulns, list):
            raise ValueError(f"dependencies[{index}].vulns must be a list")
        for vindex, vuln in enumerate(vulns):
            if not isinstance(vuln, dict):
                raise ValueError(f"dependencies[{index}].vulns[{vindex}] must be an object")
            vid = vuln.get("id")
            if isinstance(vid, str) and vid.strip():
                out.append((name, version, vid.strip()))
            else:
                out.append((name, version, MISSING_VULN_ID))
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
    parser.add_argument(
        "--pip-audit-rc",
        type=int,
        default=None,
        help="Exit code from pip-audit (0=clean, 1=vulns). If 1, JSON must list ≥1 vuln.",
    )
    args = parser.parse_args(argv)

    try:
        if args.input:
            path = args.input
            with open(path, encoding="utf-8") as fh:
                raw = fh.read()
        else:
            raw = sys.stdin.read()
    except OSError as exc:
        print(f"FAIL: cannot read pip-audit JSON ({exc})", file=sys.stderr)
        return 1

    if not raw or not raw.strip():
        print("FAIL: pip-audit JSON is missing or empty", file=sys.stderr)
        return 1

    try:
        audit = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"FAIL: cannot parse pip-audit JSON ({exc})", file=sys.stderr)
        return 1

    if not isinstance(audit, dict):
        print("FAIL: pip-audit JSON root must be an object", file=sys.stderr)
        return 1

    if "dependencies" not in audit or not isinstance(audit["dependencies"], list):
        print("FAIL: pip-audit JSON must include a dependencies list", file=sys.stderr)
        return 1

    if len(audit["dependencies"]) < 1:
        print(
            "FAIL: pip-audit JSON dependencies list is empty (nothing was audited)",
            file=sys.stderr,
        )
        return 1

    try:
        findings = iter_findings(audit)
    except ValueError as exc:
        print(f"FAIL: malformed pip-audit JSON ({exc})", file=sys.stderr)
        return 1

    if args.pip_audit_rc == 1 and not findings:
        print(
            "FAIL: pip-audit exited 1 but JSON reports zero vulnerabilities",
            file=sys.stderr,
        )
        return 1

    if not findings:
        print("pip-audit gate: no vulnerabilities reported")
        return 0

    blockers: list[str] = []
    reports: list[str] = []
    severity_cache: dict[str, str] = {}

    for pkg, ver, vid in findings:
        if vid == MISSING_VULN_ID:
            level = "UNKNOWN"
            line = f"  - {pkg}=={ver} {vid} severity={level}"
            reports.append(line)
            if not args.allow_unknown:
                blockers.append(line + " (missing vuln id; treat as blocker)")
            continue

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
            try:
                severity_cache[vid] = "UNKNOWN" if osv is None else resolve_severity(osv)
            except ValueError as exc:
                print(f"FAIL: malformed OSV document for {vid} ({exc})", file=sys.stderr)
                return 1

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
