from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from qualis.domain.enums import DQDimension
from qualis.report.loader import load_report

if TYPE_CHECKING:
    from pathlib import Path


def _write_report(path: Path) -> None:
    payload = {
        "dataset": "accidents",
        "dimension_scores": [
            {
                "dimension": "completeness",
                "dataset": "accidents",
                "total_checks": 3,
                "passed": 2,
                "failed": 1,
                "score": 0.6666666666666666,
                "weight": 1.0,
            },
            {
                "dimension": "validity",
                "dataset": "accidents",
                "total_checks": 2,
                "passed": 2,
                "failed": 0,
                "score": 1.0,
                "weight": 1.0,
            },
        ],
        "aggregate_score": 0.83,
        "total_violations": 1,
        "critical_violations": 1,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestLoadReport:
    def test_loads_valid_report(self, tmp_path: Path) -> None:
        report_path = tmp_path / "report.json"
        _write_report(report_path)
        score = load_report(report_path)
        assert score.dataset == "accidents"
        assert score.aggregate_score == 0.83
        assert score.total_violations == 1
        assert len(score.dimension_scores) == 2

    def test_reconstructs_dimension_enum(self, tmp_path: Path) -> None:
        report_path = tmp_path / "report.json"
        _write_report(report_path)
        score = load_report(report_path)
        dims = {ds.dimension for ds in score.dimension_scores}
        assert DQDimension.COMPLETENESS in dims
        assert DQDimension.VALIDITY in dims

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_report(tmp_path / "nonexistent.json")
