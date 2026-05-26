"""Unit tests for the HTML scorecard report generator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qualis import __version__
from qualis.domain.enums import DQDimension, RuleType, Severity
from qualis.domain.models import (
    CheckResult,
    DatasetScore,
    DimensionScore,
    Rule,
    Violation,
)
from qualis.domain.params import NotNullParams
from qualis.report.scorecard import generate_html_report, save_html_report

if TYPE_CHECKING:
    from pathlib import Path


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_rule(
    *,
    rule_id: str = "DQ-001",
    name: str = "Email not null",
    dimension: DQDimension = DQDimension.COMPLETENESS,
    severity: Severity = Severity.CRITICAL,
    dataset: str = "users",
    column: str | None = "email",
) -> Rule:
    return Rule(
        id=rule_id,
        name=name,
        dimension=dimension,
        rule_type=RuleType.ROW_LEVEL,
        severity=severity,
        dataset=dataset,
        column=column,
        check="not_null",
        params=NotNullParams(),
    )


def _make_dim_score(
    dimension: DQDimension,
    score: float,
    passed: int = 8,
    total: int = 10,
) -> DimensionScore:
    failed = total - passed
    return DimensionScore(
        dimension=dimension,
        dataset="users",
        total_checks=total,
        passed=passed,
        failed=failed,
        score=score,
    )


def _make_passing_dataset_score() -> DatasetScore:
    """Aggregate score of 0.95 — green band."""
    return DatasetScore(
        dataset="users",
        dimension_scores=[
            _make_dim_score(DQDimension.COMPLETENESS, 1.0, passed=10, total=10),
            _make_dim_score(DQDimension.VALIDITY, 0.9, passed=9, total=10),
        ],
        aggregate_score=0.95,
        total_violations=1,
        critical_violations=0,
    )


def _make_failing_dataset_score() -> DatasetScore:
    """Aggregate score of 0.55 — red band."""
    return DatasetScore(
        dataset="orders",
        dimension_scores=[
            _make_dim_score(DQDimension.COMPLETENESS, 0.5, passed=5, total=10),
        ],
        aggregate_score=0.55,
        total_violations=10,
        critical_violations=3,
    )


def _make_amber_dataset_score() -> DatasetScore:
    """Aggregate score of 0.78 — amber band."""
    return DatasetScore(
        dataset="products",
        dimension_scores=[
            _make_dim_score(DQDimension.COMPLETENESS, 0.78, passed=7, total=9),
        ],
        aggregate_score=0.78,
        total_violations=2,
        critical_violations=0,
    )


def _make_check_results(rule: Rule, passed: bool = True) -> CheckResult:
    violations: list[Violation] = (
        []
        if passed
        else [Violation(rule=rule, record_id=None, actual_value=None, expected="x")]
    )
    return CheckResult(
        rule=rule,
        passed=passed,
        violation_count=0 if passed else 1,
        violations=violations,
        rows_checked=100,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestGenerateHtmlReport:
    def test_returns_string(self) -> None:
        score = _make_passing_dataset_score()
        result = generate_html_report(score)
        assert isinstance(result, str)

    def test_returns_valid_html_skeleton(self) -> None:
        score = _make_passing_dataset_score()
        html = generate_html_report(score)
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    def test_score_number_appears_in_output(self) -> None:
        score = _make_passing_dataset_score()
        html = generate_html_report(score)
        # aggregate_score 0.95 → 95
        assert "95" in html

    def test_failing_score_number_appears(self) -> None:
        score = _make_failing_dataset_score()
        html = generate_html_report(score)
        # aggregate_score 0.55 → 55
        assert "55" in html

    def test_all_dimension_names_appear(self) -> None:
        score = _make_passing_dataset_score()
        html = generate_html_report(score)
        for dim in DQDimension:
            assert dim.value.capitalize() in html, f"Missing dimension: {dim.value}"

    def test_passing_score_uses_green_color(self) -> None:
        score = _make_passing_dataset_score()
        html = generate_html_report(score)
        # Green hero band
        assert "#16a34a" in html

    def test_failing_score_uses_red_color(self) -> None:
        score = _make_failing_dataset_score()
        html = generate_html_report(score)
        # Red hero band
        assert "#dc2626" in html

    def test_amber_score_uses_amber_color(self) -> None:
        score = _make_amber_dataset_score()
        html = generate_html_report(score)
        # Amber hero band
        assert "#d97706" in html

    def test_version_appears_in_footer(self) -> None:
        score = _make_passing_dataset_score()
        html = generate_html_report(score)
        assert __version__ in html

    def test_dataset_name_in_title(self) -> None:
        score = _make_passing_dataset_score()
        html = generate_html_report(score)
        assert "users" in html

    def test_critical_violations_count_shown(self) -> None:
        score = _make_failing_dataset_score()
        html = generate_html_report(score)
        assert "3" in html  # critical_violations

    def test_not_measured_shown_for_missing_dimensions(self) -> None:
        # Only COMPLETENESS is measured; the other 8 should show "not measured"
        score = _make_failing_dataset_score()
        html = generate_html_report(score)
        assert "not measured" in html

    def test_no_external_resources(self) -> None:
        score = _make_passing_dataset_score()
        html = generate_html_report(score)
        assert "cdn" not in html.lower()
        assert 'src="http' not in html
        assert 'href="http' not in html

    def test_self_contained_no_link_tags(self) -> None:
        score = _make_passing_dataset_score()
        html = generate_html_report(score)
        assert "<link " not in html

    def test_without_check_results_no_drilldown_table(self) -> None:
        score = _make_passing_dataset_score()
        html = generate_html_report(score, check_results=None)
        # drilldown table <thead> only rendered when checks list is non-empty
        assert "<thead>" not in html

    def test_with_check_results_shows_rule_id(self) -> None:
        rule = _make_rule(rule_id="DQ-COMP-001")
        cr = _make_check_results(rule, passed=True)
        score = _make_passing_dataset_score()
        html = generate_html_report(score, check_results=[cr])
        assert "DQ-COMP-001" in html

    def test_with_check_results_shows_pass_chip(self) -> None:
        rule = _make_rule(dimension=DQDimension.COMPLETENESS)
        cr = _make_check_results(rule, passed=True)
        score = _make_passing_dataset_score()
        html = generate_html_report(score, check_results=[cr])
        assert "PASS" in html

    def test_with_check_results_shows_fail_chip(self) -> None:
        rule = _make_rule(dimension=DQDimension.COMPLETENESS)
        cr = _make_check_results(rule, passed=False)
        score = _make_passing_dataset_score()
        html = generate_html_report(score, check_results=[cr])
        assert "FAIL" in html

    def test_qualis_branding_present(self) -> None:
        score = _make_passing_dataset_score()
        html = generate_html_report(score)
        assert "Qualis" in html

    def test_data_quality_label_present(self) -> None:
        score = _make_passing_dataset_score()
        html = generate_html_report(score)
        assert "Data Quality" in html

    def test_zero_score_uses_red(self) -> None:
        score = DatasetScore(
            dataset="empty",
            dimension_scores=[],
            aggregate_score=0.0,
            total_violations=0,
            critical_violations=0,
        )
        html = generate_html_report(score)
        assert "#dc2626" in html


class TestSaveHtmlReport:
    def test_creates_file(self, tmp_path: Path) -> None:
        score = _make_passing_dataset_score()
        output = tmp_path / "report.html"
        save_html_report(score, output)
        assert output.exists()

    def test_file_contains_html(self, tmp_path: Path) -> None:
        score = _make_passing_dataset_score()
        output = tmp_path / "report.html"
        save_html_report(score, output)
        content = output.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        score = _make_passing_dataset_score()
        output = tmp_path / "nested" / "deep" / "report.html"
        save_html_report(score, output)
        assert output.exists()

    def test_file_content_matches_generate(self, tmp_path: Path) -> None:
        score = _make_passing_dataset_score()
        output = tmp_path / "r.html"
        save_html_report(score, output)
        # Generated string and saved file should agree on the score
        assert "95" in output.read_text(encoding="utf-8")

    def test_with_check_results(self, tmp_path: Path) -> None:
        rule = _make_rule(rule_id="DQ-COMP-001")
        cr = _make_check_results(rule, passed=False)
        score = _make_passing_dataset_score()
        output = tmp_path / "report.html"
        save_html_report(score, output, check_results=[cr])
        content = output.read_text(encoding="utf-8")
        assert "DQ-COMP-001" in content
