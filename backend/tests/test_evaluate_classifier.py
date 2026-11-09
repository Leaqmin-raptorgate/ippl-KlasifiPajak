"""Offline classifier evaluation contract (FR-11, FR-14, NFR-01).

The scorer reads the human review workbook directly. Only rows with a reviewer
count. ``needs_clarification`` rows are scored as abstention examples instead
of being dropped, and unreviewed rows are never silently left out.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from scripts import evaluate_classifier as ev

HEADER = [
    "id",
    "description",
    "candidate_label",
    "decision",
    "final_label",
    "reviewer",
    "review_note",
    "status",
    "client_name",
    "source_channel",
    "original_note",
]


def _workbook(path: Path, rows: list[tuple]) -> Path:
    """Build a workbook shaped like candidate_label_review.xlsx (header on row 8)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Review"
    ws.cell(2, 1, "KlasifiPajak candidate label review")
    for col, name in enumerate(HEADER, start=1):
        ws.cell(8, col, name)
    for r, (rid, desc, decision, label, reviewer, note) in enumerate(rows, start=9):
        values = [
            rid,
            desc,
            "usaha",
            decision,
            label,
            reviewer,
            note,
            "=formula",
            "Klien",
            "other",
            "",
        ]
        for col, value in enumerate(values, start=1):
            ws.cell(r, col, value)
    wb.save(path)
    return path


def test_candidate_csv_is_still_refused(tmp_path):
    """NFR-01: the unreviewed candidate CSV is never scored."""
    path = tmp_path / "candidate_transactions.csv"
    path.write_text("id,description\nC001,x\n", encoding="utf-8")
    assert ev.main([str(path)]) == 2


def test_missing_file_is_refused(tmp_path):
    assert ev.main([str(tmp_path / "nope.xlsx")]) == 2


def test_unreviewed_rows_block_scoring_unless_partial_is_explicit(tmp_path, capsys):
    """Rows without a reviewer are counted, never silently dropped."""
    path = _workbook(
        tmp_path / "r.xlsx",
        [
            ("C1", "Penjualan kaos", "approved", "usaha", "Rina", ""),
            ("C2", "Penjualan sepatu", "approved", "usaha", "", ""),
            ("C3", "Penjualan tas", "pending", "", "", ""),
        ],
    )
    assert ev.main([str(path)]) == 2
    assert "2 unreviewed" in capsys.readouterr().err

    out = tmp_path / "report.json"
    assert ev.main([str(path), "--allow-partial", "--json", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["counts"]["unreviewed"] == 2
    assert report["counts"]["labelled"] == 1


@pytest.mark.parametrize(
    "row",
    [
        ("C1", "Penjualan kaos", "approved", "", "Rina", ""),
        ("C1", "Penjualan kaos", "corrected", "omzet", "Rina", ""),
        ("C1", "Penjualan kaos", "maybe", "usaha", "Rina", ""),
        ("C1", "Penjualan kaos", "exclude", "", "Rina", ""),
    ],
)
def test_invalid_reviewed_rows_are_rejected(tmp_path, capsys, row):
    """A reviewed row needs a valid label; an exclusion needs a reason."""
    path = _workbook(tmp_path / "r.xlsx", [row])
    assert ev.main([str(path)]) == 2
    assert "C1" in capsys.readouterr().err


def test_load_maps_decisions_to_expected_outcomes(tmp_path):
    path = _workbook(
        tmp_path / "r.xlsx",
        [
            ("C1", "Penjualan kaos", "approved", "usaha", "Rina", ""),
            ("C2", "Jasa desain logo", "corrected", "pekerjaan_bebas", "Rina", ""),
            ("C3", "dana masuk", "needs_clarification", "", "Rina", ""),
            ("C4", "baris uji rusak", "exclude", "", "Rina", "duplikat"),
        ],
    )
    dataset = ev.load_review_workbook(path)
    assert [(e.id, e.expected) for e in dataset.examples] == [
        ("C1", "usaha"),
        ("C2", "pekerjaan_bebas"),
        ("C3", ev.CLARIFY),
    ]
    assert dataset.excluded == [("C4", "duplikat")]
    assert dataset.unreviewed == []


def test_score_metrics_with_injected_predictor():
    """Metric arithmetic is checked against a fixed predictor, not the live rules."""
    examples = [
        ev.Example("e1", "a", "usaha"),
        ev.Example("e2", "b", "usaha"),
        ev.Example("e3", "c", "pekerjaan_bebas"),
        ev.Example("e4", "d", "non_object"),
        ev.Example("k1", "e", ev.CLARIFY),
        ev.Example("k2", "f", ev.CLARIFY),
    ]
    predictions = {
        "a": "usaha",
        "b": "pekerjaan_bebas",
        "c": "pekerjaan_bebas",
        "d": ev.CLARIFY,
        "e": ev.CLARIFY,
        "f": "usaha",
    }
    result = ev.score(examples, predictions.__getitem__)

    labelled = result["labelled"]
    assert labelled["n"] == 4
    assert labelled["correct"] == 2
    assert labelled["accuracy"] == pytest.approx(0.5)
    assert labelled["answered"] == 3
    assert labelled["coverage"] == pytest.approx(0.75)
    assert labelled["answered_accuracy"] == pytest.approx(2 / 3)

    per = result["per_category"]
    # k2 should have clarified but was predicted usaha: a false positive for usaha.
    assert per["usaha"]["precision"] == pytest.approx(0.5)
    assert per["usaha"]["recall"] == pytest.approx(0.5)
    assert per["pekerjaan_bebas"]["precision"] == pytest.approx(0.5)
    assert per["pekerjaan_bebas"]["recall"] == pytest.approx(1.0)
    assert per["non_object"]["precision"] is None
    assert per["non_object"]["recall"] == pytest.approx(0.0)
    assert per["already_final"] == {"support": 0, "precision": None, "recall": None, "f1": None}

    clarify = result["should_clarify"]
    assert clarify == {"n": 2, "abstained": 1, "abstention_rate": 0.5, "confident_wrong": 1}

    cm = result["confusion"]
    assert cm["usaha"]["usaha"] == 1
    assert cm["usaha"]["pekerjaan_bebas"] == 1
    assert cm["pekerjaan_bebas"]["pekerjaan_bebas"] == 1
    assert cm["non_object"][ev.CLARIFY] == 1
    assert cm[ev.CLARIFY]["usaha"] == 1
    assert [m["id"] for m in result["mismatches"]] == ["e2", "e4", "k2"]


def test_rules_predictor_uses_description_and_clarifies_on_no_match():
    """FR-11/FR-14: the offline rule tier abstains instead of guessing."""
    assert ev.predict_rules("Penjualan 6 pcs kaos") == "usaha"
    assert ev.predict_rules("dana masuk") == ev.CLARIFY


def test_report_records_provenance(tmp_path):
    """The report names the dataset hash, the classifier version, and that no model ran."""
    path = _workbook(
        tmp_path / "r.xlsx",
        [("C1", "Penjualan kaos", "approved", "usaha", "Rina", "")],
    )
    out = tmp_path / "report.json"
    assert ev.main([str(path), "--json", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert len(report["dataset"]["sha256"]) == 64
    assert report["dataset"]["path"].endswith("r.xlsx")
    assert len(report["classifier"]["rules_version"]) == 64
    assert report["classifier"]["tier"] == "rules_only"
    assert report["classifier"]["model_called"] is False
    assert "split" not in report
    assert report["counts"] == {"labelled": 1, "should_clarify": 0, "excluded": 0, "unreviewed": 0}


def test_split_flag_is_not_accepted(tmp_path, capsys):
    """Argument parsing no longer accepts ``--split``."""
    with pytest.raises(SystemExit) as help_exit:
        ev.main(["--help"])
    assert help_exit.value.code == 0
    assert "--split" not in capsys.readouterr().out

    path = _workbook(
        tmp_path / "r.xlsx", [("C1", "Penjualan kaos", "approved", "usaha", "Rina", "")]
    )
    with pytest.raises(SystemExit) as split_exit:
        ev.main([str(path), "--split", "heldout"])
    assert split_exit.value.code != 0
    assert "--split" in capsys.readouterr().err


def test_scorer_never_imports_the_model_client():
    """NFR-01: evaluation is offline; the model client is not reachable from it."""
    source = Path(ev.__file__).read_text(encoding="utf-8")
    assert "model_client" not in source
