from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from qualis.github.comment import format_pr_comment, render_comment_from_file

if TYPE_CHECKING:
    from pathlib import Path


def _report(score: float, dimension_scores: list[dict[str, Any]] | None = None,
            violations: int = 0, critical: int = 0) -> dict[str, Any]:
    return {
        "dataset": "accidents",
        "dimension_scores": dimension_scores or [],
        "aggregate_score": score,
        "total_violations": violations,
        "critical_violations": critical,
    }


def _dim(name: str, score: float, total: int = 1) -> dict[str, Any]:
    passed = round(score * total)
    return {
        "dimension": name,
        "dataset": "accidents",
        "total_checks": total,
        "passed": passed,
        "failed": total - passed,
        "score": score,
        "weight": 1.0,
    }


class TestStatusLabels:
    def test_passing_report_shows_pass_emoji_and_label(self) -> None:
        out = format_pr_comment(_report(0.95))
        assert "✅" in out
        assert "PASSING" in out

    def test_warning_report_shows_warn_emoji_and_label(self) -> None:
        out = format_pr_comment(_report(0.75))
        assert "⚠️" in out
        assert "WARNING" in out

    def test_failing_report_shows_fail_emoji_and_label(self) -> None:
        out = format_pr_comment(_report(0.30))
        assert "❌" in out
        assert "FAILING" in out


class TestDimensionTable:
    def test_all_dimensions_appear(self) -> None:
        dims = [
            _dim("completeness", 1.0),
            _dim("validity", 0.5),
            _dim("uniqueness", 0.0),
        ]
        out = format_pr_comment(_report(0.5, dims))
        assert "Completeness" in out
        assert "Validity" in out
        assert "Uniqueness" in out

    def test_score_percentages_appear(self) -> None:
        dims = [_dim("validity", 0.5)]
        out = format_pr_comment(_report(0.5, dims))
        assert "50%" in out


class TestViolations:
    def test_violation_count_appears_when_nonzero(self) -> None:
        out = format_pr_comment(_report(0.5, violations=4, critical=2))
        assert "4 violations" in out
        assert "2 critical" in out

    def test_violation_line_omitted_when_zero(self) -> None:
        out = format_pr_comment(_report(0.95))
        assert "violations" not in out.lower() or "0 violations" not in out


class TestCommitSha:
    def test_commit_sha_appears_in_footer(self) -> None:
        out = format_pr_comment(_report(0.95), commit_sha="abc1234def5678")
        assert "abc1234" in out

    def test_short_sha_only_seven_chars(self) -> None:
        out = format_pr_comment(_report(0.95), commit_sha="abc1234def5678")
        # Long form should not appear
        assert "abc1234def5678" not in out


class TestLineCount:
    def test_typical_9_dimension_report_under_20_lines(self) -> None:
        dims = [
            _dim(name, 0.8) for name in [
                "completeness", "accuracy", "consistency", "validity",
                "uniqueness", "timeliness", "reasonability", "integrity", "currency",
            ]
        ]
        out = format_pr_comment(_report(0.8, dims, violations=3, critical=1))
        assert len(out.splitlines()) < 20


class TestRenderFromFile:
    def test_reads_json_and_formats(self, tmp_path: Path) -> None:
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(_report(0.95, [_dim("completeness", 1.0)])))
        out = render_comment_from_file(report_path)
        assert "Qualis Data Quality Report" in out
        assert "PASSING" in out
