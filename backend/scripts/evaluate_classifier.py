"""Offline evaluation of the rule classifier against the human review workbook (NFR-01).

Reads the ``Review`` sheet of ``candidate_label_review.xlsx`` (header row holds
``id``). Row meaning, decided by the human reviewer:

- ``approved`` / ``corrected`` with a valid ``final_label`` and a reviewer:
  a labelled example.
- ``needs_clarification`` with a reviewer: an abstention example. The correct
  outcome is that the classifier asks (FR-14) rather than picks a category.
- ``exclude`` with a reviewer and a reason in ``review_note``: left out, listed.
- Anything without a reviewer is unreviewed. Scoring refuses unless
  ``--allow-partial`` is given, and the count is always reported.

Only the rule tier (``app.classify.rules``) is scored. No model is called
(FR-12, FR-13). The report records the dataset hash and the rule-table hash,
so a result can be tied to the exact data and rules that produced it.

Usage::

    python backend/scripts/evaluate_classifier.py REVIEW.xlsx \
        [--allow-partial] [--threshold T] [--json OUT.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from openpyxl.utils.exceptions import InvalidFileException  # noqa: E402

from app.classify.rules import RULES, classify  # noqa: E402
from app.services.config import DEFAULTS  # noqa: E402

#: The ruleset's rule threshold (``T_rule``), not a number chosen here.
DEFAULT_THRESHOLD = float(DEFAULTS["T_rule"])

CATEGORIES = ("usaha", "pekerjaan_bebas", "already_final", "non_object")
CLARIFY = "clarify"
OUTCOMES = (*CATEGORIES, CLARIFY)

_REQUIRED = "A reviewed dataset is required."
_LABELLED = {"approved", "corrected"}
_DECISIONS = {*_LABELLED, "needs_clarification", "exclude", "pending"}


@dataclass(frozen=True)
class Example:
    id: str
    description: str
    expected: str


@dataclass
class Dataset:
    examples: list[Example] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)
    unreviewed: list[str] = field(default_factory=list)


class DatasetError(ValueError):
    """A reviewed row is malformed; the message names the row id."""


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def load_review_workbook(path: Path) -> Dataset:
    """Read the Review sheet into labelled, abstention, excluded and unreviewed rows."""
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True)
    try:
        return _dataset_from_review(wb["Review"])
    finally:
        wb.close()


def _dataset_from_review(ws) -> Dataset:
    """Turn a Review worksheet into a dataset. The caller closes the workbook."""
    rows = ws.iter_rows(values_only=True)
    header: list[str] | None = None
    for row in rows:
        if row and _text(row[0]) == "id":
            header = [_text(v) for v in row]
            break
    if header is None:
        raise DatasetError("Review sheet has no header row starting with 'id'.")
    col = {name: i for i, name in enumerate(header)}
    for name in ("id", "description", "decision", "final_label", "reviewer", "review_note"):
        if name not in col:
            raise DatasetError(f"Review sheet is missing column '{name}'.")

    dataset = Dataset()
    errors: list[str] = []
    for row in rows:
        rid = _text(row[col["id"]]) if row else ""
        if not rid:
            continue
        description = _text(row[col["description"]])
        decision = _text(row[col["decision"]]).lower()
        label = _text(row[col["final_label"]])
        reviewer = _text(row[col["reviewer"]])
        note = _text(row[col["review_note"]])

        if not reviewer or decision in {"", "pending"}:
            # No reviewer, or no decision yet: not reviewed, whatever else is in the row.
            dataset.unreviewed.append(rid)
        elif decision not in _DECISIONS:
            errors.append(f"{rid}: unknown decision '{decision}'")
        elif decision in _LABELLED:
            if label not in CATEGORIES:
                errors.append(f"{rid}: {decision} needs final_label in {CATEGORIES}, got '{label}'")
            else:
                dataset.examples.append(Example(rid, description, label))
        elif decision == "needs_clarification":
            dataset.examples.append(Example(rid, description, CLARIFY))
        elif not note:
            errors.append(f"{rid}: exclude needs a reason in review_note")
        else:
            dataset.excluded.append((rid, note))
    if errors:
        raise DatasetError("; ".join(errors))
    return dataset


def predict_rules(description: str, threshold: float = DEFAULT_THRESHOLD) -> str:
    """Rule tier only: a category, or ``clarify`` when the rules do not decide."""
    category, _, _, requires_clarification, _ = classify(description, threshold)
    return CLARIFY if requires_clarification else category


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def score(examples: list[Example], predict: Callable[[str], str]) -> dict:
    """Accuracy, coverage, per-category precision/recall/F1, abstention, confusion."""
    confusion = {exp: dict.fromkeys(OUTCOMES, 0) for exp in OUTCOMES}
    mismatches = []
    for ex in examples:
        got = predict(ex.description)
        confusion[ex.expected][got] += 1
        if got != ex.expected:
            mismatches.append({"id": ex.id, "expected": ex.expected, "predicted": got})

    labelled = [ex for ex in examples if ex.expected != CLARIFY]
    n = len(labelled)
    correct = sum(confusion[c][c] for c in CATEGORIES)
    answered = sum(confusion[c][p] for c in CATEGORIES for p in CATEGORIES)

    per_category = {}
    for c in CATEGORIES:
        support = sum(confusion[c].values())
        predicted = sum(confusion[e][c] for e in OUTCOMES)
        tp = confusion[c][c]
        precision = _ratio(tp, predicted)
        recall = _ratio(tp, support)
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else None
        )
        per_category[c] = {"support": support, "precision": precision, "recall": recall, "f1": f1}

    n_clarify = sum(confusion[CLARIFY].values())
    abstained = confusion[CLARIFY][CLARIFY]
    return {
        "labelled": {
            "n": n,
            "correct": correct,
            "accuracy": _ratio(correct, n),
            "answered": answered,
            "coverage": _ratio(answered, n),
            "answered_accuracy": _ratio(correct, answered),
        },
        "per_category": per_category,
        "should_clarify": {
            "n": n_clarify,
            "abstained": abstained,
            "abstention_rate": _ratio(abstained, n_clarify),
            "confident_wrong": n_clarify - abstained,
        },
        "confusion": confusion,
        "mismatches": mismatches,
    }


def _rules_version(threshold: float = DEFAULT_THRESHOLD) -> str:
    """Hash every field that can change an outcome, plus the threshold."""
    table = "\n".join(
        f"{r.id}|{r.category}|{r.phrase}|{r.confidence}|{r.decisive}|{r.weak}|{r.citation}"
        for r in RULES
    )
    return hashlib.sha256(f"{table}\nthreshold={threshold}".encode("utf-8")).hexdigest()


def _fmt(value: float | None) -> str:
    return "  n/a" if value is None else f"{value:5.2f}"


def _print_report(report: dict) -> None:
    lab = report["result"]["labelled"]
    cla = report["result"]["should_clarify"]
    counts = report["counts"]
    print(f"Dataset: {report['dataset']['path']} (sha256 {report['dataset']['sha256'][:12]})")
    print(
        f"Rules: {report['classifier']['rules_version'][:12]}  tier=rules_only  "
        f"threshold={report['classifier']['threshold']}"
    )
    print(
        f"Rows: labelled={counts['labelled']} should_clarify={counts['should_clarify']} "
        f"excluded={counts['excluded']} unreviewed={counts['unreviewed']}"
    )
    print(
        f"Labelled: accuracy={_fmt(lab['accuracy'])} coverage={_fmt(lab['coverage'])} "
        f"answered_accuracy={_fmt(lab['answered_accuracy'])} ({lab['correct']}/{lab['n']})"
    )
    print(
        f"Should-clarify: abstained {cla['abstained']}/{cla['n']} "
        f"(rate {_fmt(cla['abstention_rate'])}), confident_wrong={cla['confident_wrong']}"
    )
    print("\ncategory          support  prec  recall    f1")
    for c, m in report["result"]["per_category"].items():
        print(
            f"{c:<17} {m['support']:>7} {_fmt(m['precision'])} {_fmt(m['recall'])} {_fmt(m['f1'])}"
        )
    short = {
        "usaha": "usa",
        "pekerjaan_bebas": "pb",
        "already_final": "fin",
        "non_object": "non",
        CLARIFY: "clr",
    }
    print("\nconfusion (rows=expected, cols=predicted)")
    print(" " * 6 + "".join(f"{short[p]:>6}" for p in OUTCOMES))
    for e in OUTCOMES:
        print(
            f"{short[e]:<6}"
            + "".join(f"{report['result']['confusion'][e][p]:>6}" for p in OUTCOMES)
        )
    if report["result"]["mismatches"]:
        print("\nmismatches:")
        for m in report["result"]["mismatches"]:
            print(f"  {m['id']}: expected {m['expected']}, predicted {m['predicted']}")


def main(argv: list[str] | None = None) -> int:
    """Exit 0 with a report, or 2 when the dataset is missing, unreviewed or malformed."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--json", type=Path, dest="json_out")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="minimum rule confidence (default: the ruleset's T_rule)",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    path: Path = args.dataset
    if path.suffix.lower() != ".xlsx" or not path.is_file():
        print(f"{_REQUIRED} Pass the review workbook (.xlsx).", file=sys.stderr)
        return 2
    try:
        dataset = load_review_workbook(path)
    except (DatasetError, KeyError, OSError, zipfile.BadZipFile, InvalidFileException) as exc:
        print(f"{_REQUIRED} {exc}", file=sys.stderr)
        return 2
    if dataset.unreviewed and not args.allow_partial:
        print(
            f"{_REQUIRED} {len(dataset.unreviewed)} unreviewed rows "
            f"(first: {', '.join(dataset.unreviewed[:5])}). Add a reviewer or pass --allow-partial.",
            file=sys.stderr,
        )
        return 2

    result = score(dataset.examples, lambda text: predict_rules(text, args.threshold))
    report = {
        "dataset": {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
        "classifier": {
            "tier": "rules_only",
            "rules_version": _rules_version(args.threshold),
            "threshold": args.threshold,
            "model_called": False,
        },
        "counts": {
            "labelled": result["labelled"]["n"],
            "should_clarify": result["should_clarify"]["n"],
            "excluded": len(dataset.excluded),
            "unreviewed": len(dataset.unreviewed),
        },
        "excluded": dataset.excluded,
        "unreviewed": dataset.unreviewed,
        "result": result,
    }
    _print_report(report)
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
