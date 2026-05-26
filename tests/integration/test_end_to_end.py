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
