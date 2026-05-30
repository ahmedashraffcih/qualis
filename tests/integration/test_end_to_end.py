"""End-to-end integration tests for Qualis CLI."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from qualis.cli.main import app

runner = CliRunner()
EXAMPLE = Path(__file__).parent.parent.parent / "examples" / "traffic_safety"


class TestInitCommand:
    def test_creates_scaffold(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "rules").is_dir()
        assert (tmp_path / "rules" / "completeness.yaml").exists()

    def test_creates_gitignore(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / ".gitignore").exists()
        content = (tmp_path / ".gitignore").read_text()
        assert ".env" in content

    def test_idempotent(self, tmp_path: Path) -> None:
        runner.invoke(app, ["init", str(tmp_path)])
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0


class TestValidateCommand:
    def test_validates_example_rules(self) -> None:
        result = runner.invoke(app, ["validate", "--rules", str(EXAMPLE / "rules")])
        assert result.exit_code == 0
        assert "rule(s) valid" in result.output

    def test_reports_rule_count(self) -> None:
        result = runner.invoke(app, ["validate", "--rules", str(EXAMPLE / "rules")])
        assert "6 rule(s) valid" in result.output

    def test_fails_on_missing_dir(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["validate", "--rules", str(tmp_path / "nonexistent")])
        assert result.exit_code == 1

    def test_fails_on_bad_yaml(self, tmp_path: Path) -> None:
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        bad_file = rules_dir / "bad.yaml"
        bad_file.write_text(
            "rules:\n  - id: X\n    name: X\n    dimension: bogus\n"
            "    severity: critical\n    dataset: d\n    column: c\n"
            "    check: not_null\n"
        )
        result = runner.invoke(app, ["validate", "--rules", str(rules_dir)])
        assert result.exit_code == 1


class TestCheckCommand:
    def test_check_with_sample_csv(self) -> None:
        result = runner.invoke(app, [
            "check",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
        ])
        assert result.exit_code == 0

    def test_check_outputs_score(self) -> None:
        result = runner.invoke(app, [
            "check",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
        ])
        assert "QUALIS" in result.output or "Score" in result.output

    def test_fail_on_score_threshold(self) -> None:
        result = runner.invoke(app, [
            "check",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--fail-on-score", "99",
        ])
        assert result.exit_code == 1
        assert "below threshold" in result.output

    def test_passes_on_low_threshold(self) -> None:
        result = runner.invoke(app, [
            "check",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--fail-on-score", "1",
        ])
        assert result.exit_code == 0

    def test_json_output(self) -> None:
        result = runner.invoke(app, [
            "check",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--output-format", "json",
        ])
        assert result.exit_code == 0
        assert "aggregate_score" in result.output

    def test_missing_rules_dir(self) -> None:
        result = runner.invoke(app, [
            "check",
            "--rules", "/nonexistent/path",
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
        ])
        assert result.exit_code == 1


class TestReportCommand:
    def test_html_report_creates_file(self, tmp_path: Path) -> None:
        output = tmp_path / "test-report.html"
        result = runner.invoke(app, [
            "report",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--format", "html",
            "--output", str(output),
        ])
        assert result.exit_code == 0
        assert output.exists()

    def test_html_report_contains_qualis_branding(self, tmp_path: Path) -> None:
        output = tmp_path / "test-report.html"
        runner.invoke(app, [
            "report",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--format", "html",
            "--output", str(output),
        ])
        content = output.read_text(encoding="utf-8")
        assert "Qualis" in content

    def test_html_report_contains_data_quality(self, tmp_path: Path) -> None:
        output = tmp_path / "test-report.html"
        runner.invoke(app, [
            "report",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--format", "html",
            "--output", str(output),
        ])
        content = output.read_text(encoding="utf-8")
        assert "Data Quality" in content

    def test_json_report_creates_file(self, tmp_path: Path) -> None:
        output = tmp_path / "test-report.json"
        result = runner.invoke(app, [
            "report",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--format", "json",
            "--output", str(output),
        ])
        assert result.exit_code == 0
        assert output.exists()

    def test_json_report_is_valid_json(self, tmp_path: Path) -> None:
        import json

        output = tmp_path / "test-report.json"
        runner.invoke(app, [
            "report",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--format", "json",
            "--output", str(output),
        ])
        data = json.loads(output.read_text(encoding="utf-8"))
        assert "aggregate_score" in data

    def test_json_report_contains_dimension_scores(self, tmp_path: Path) -> None:
        import json

        output = tmp_path / "test-report.json"
        runner.invoke(app, [
            "report",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--format", "json",
            "--output", str(output),
        ])
        data = json.loads(output.read_text(encoding="utf-8"))
        assert "dimension_scores" in data

    def test_fail_on_score_exits_1(self, tmp_path: Path) -> None:
        output = tmp_path / "test-report.html"
        result = runner.invoke(app, [
            "report",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--format", "html",
            "--output", str(output),
            "--fail-on-score", "99",
        ])
        assert result.exit_code == 1

    def test_fail_on_score_0_never_fails(self, tmp_path: Path) -> None:
        output = tmp_path / "test-report.html"
        result = runner.invoke(app, [
            "report",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--format", "html",
            "--output", str(output),
            "--fail-on-score", "0",
        ])
        assert result.exit_code == 0

    def test_missing_rules_dir_exits_1(self, tmp_path: Path) -> None:
        output = tmp_path / "r.html"
        result = runner.invoke(app, [
            "report",
            "--rules", "/nonexistent/path",
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--output", str(output),
        ])
        assert result.exit_code == 1

    def test_missing_sample_file_exits_1(self, tmp_path: Path) -> None:
        output = tmp_path / "r.html"
        result = runner.invoke(app, [
            "report",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(tmp_path / "nonexistent.csv"),
            "--output", str(output),
        ])
        assert result.exit_code == 1


class TestDiffCommand:
    def _make_report(self, tmp_path: Path, name: str) -> Path:
        """Generate a JSON report from the example data."""
        output = tmp_path / name
        runner.invoke(app, [
            "report",
            "--rules", str(EXAMPLE / "rules"),
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--format", "json",
            "--output", str(output),
        ])
        return output

    def test_diff_two_identical_reports(self, tmp_path: Path) -> None:
        report = self._make_report(tmp_path, "before.json")
        result = runner.invoke(app, ["diff", str(report), str(report)])
        assert result.exit_code == 0

    def test_diff_json_output(self, tmp_path: Path) -> None:
        report = self._make_report(tmp_path, "before.json")
        result = runner.invoke(app, [
            "diff", str(report), str(report), "--output-format", "json",
        ])
        assert result.exit_code == 0
        assert "aggregate_delta" in result.output

    def test_diff_missing_before_exits_1(self, tmp_path: Path) -> None:
        report = self._make_report(tmp_path, "after.json")
        result = runner.invoke(app, [
            "diff", str(tmp_path / "nonexistent.json"), str(report),
        ])
        assert result.exit_code == 1

    def test_fail_on_regression_with_regressed_dimension(self, tmp_path: Path) -> None:
        import json

        # Hand-craft a "before" report with a high validity score and an
        # "after" with a lower one to force a regression.
        before = tmp_path / "before.json"
        after = tmp_path / "after.json"
        before.write_text(json.dumps({
            "dataset": "accidents",
            "dimension_scores": [{
                "dimension": "validity", "dataset": "accidents",
                "total_checks": 2, "passed": 2, "failed": 0, "score": 1.0, "weight": 1.0,
            }],
            "aggregate_score": 1.0, "total_violations": 0, "critical_violations": 0,
        }))
        after.write_text(json.dumps({
            "dataset": "accidents",
            "dimension_scores": [{
                "dimension": "validity", "dataset": "accidents",
                "total_checks": 2, "passed": 1, "failed": 1, "score": 0.5, "weight": 1.0,
            }],
            "aggregate_score": 0.5, "total_violations": 1, "critical_violations": 0,
        }))
        result = runner.invoke(app, [
            "diff", str(before), str(after), "--fail-on-regression",
        ])
        assert result.exit_code == 1
        assert "Regression detected" in result.output


class TestDiscoverCommand:
    def test_discover_batch_creates_rules_file(self, tmp_path: Path) -> None:
        output = tmp_path / "discovered.yaml"
        result = runner.invoke(app, [
            "discover",
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--output", str(output),
            "--batch",
        ])
        assert result.exit_code == 0
        assert output.exists()

    def test_discovered_rules_validate(self, tmp_path: Path) -> None:
        output = tmp_path / "rules" / "discovered.yaml"
        runner.invoke(app, [
            "discover",
            "--sample", str(EXAMPLE / "data" / "accidents.csv"),
            "--output", str(output),
            "--batch",
        ])
        # The discovered rules file must validate via qualis validate
        validate_result = runner.invoke(app, ["validate", "--rules", str(output.parent)])
        assert validate_result.exit_code == 0
        assert "rule(s) valid" in validate_result.output

    def test_missing_sample_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(app, [
            "discover",
            "--sample", str(tmp_path / "nonexistent.csv"),
            "--output", str(tmp_path / "out.yaml"),
            "--batch",
        ])
        assert result.exit_code == 1
