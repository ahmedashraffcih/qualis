from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from qualis.config.loader import load_rules_from_directory, load_rules_from_file
from qualis.domain.enums import DQDimension, Severity
from qualis.domain.params import BetweenParams, NotNullParams

FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "rules"


class TestLoadRulesFromFile:
    def test_loads_two_rules(self) -> None:
        rules = load_rules_from_file(FIXTURE_DIR / "completeness.yaml")
        assert len(rules) == 2

    def test_first_rule_is_not_null(self) -> None:
        rules = load_rules_from_file(FIXTURE_DIR / "completeness.yaml")
        rule = rules[0]
        assert rule.id == "DQ-COMP-001"
        assert rule.name == "Accident date required"
        assert rule.dimension is DQDimension.COMPLETENESS
        assert rule.severity is Severity.CRITICAL
        assert rule.check == "not_null"
        assert isinstance(rule.params, NotNullParams)

    def test_between_params_parsed(self) -> None:
        rules = load_rules_from_file(FIXTURE_DIR / "completeness.yaml")
        rule = rules[1]
        assert rule.check == "between"
        assert isinstance(rule.params, BetweenParams)
        assert rule.params.min == "2010-01-01"

    def test_today_template_resolved(self) -> None:
        rules = load_rules_from_file(FIXTURE_DIR / "completeness.yaml")
        rule = rules[1]
        assert isinstance(rule.params, BetweenParams)
        assert "{{" not in rule.params.max
        assert rule.params.max == date.today().isoformat()

    def test_invalid_dimension_raises(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            "rules:\n"
            "  - id: x\n"
            "    name: bad\n"
            "    dimension: BOGUS_DIM\n"
            "    severity: critical\n"
            "    dataset: ds\n"
            "    column: col\n"
            "    check: not_null\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="dimension"):
            load_rules_from_file(bad_yaml)

    def test_typo_in_check_raises_with_suggestion(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "typo.yaml"
        bad_yaml.write_text(
            "rules:\n"
            "  - id: x\n"
            "    name: typo check\n"
            "    dimension: completeness\n"
            "    severity: critical\n"
            "    dataset: ds\n"
            "    column: col\n"
            "    check: not_nul\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="not_null"):
            load_rules_from_file(bad_yaml)

    def test_auto_generated_id_when_omitted(self, tmp_path: Path) -> None:
        no_id_yaml = tmp_path / "no_id.yaml"
        no_id_yaml.write_text(
            "rules:\n"
            "  - name: auto id rule\n"
            "    dimension: completeness\n"
            "    severity: warning\n"
            "    dataset: orders\n"
            "    column: status\n"
            "    check: not_null\n",
            encoding="utf-8",
        )
        rules = load_rules_from_file(no_id_yaml)
        assert len(rules) == 1
        rule = rules[0]
        assert rule.id == "completeness-orders-status-not_null"


class TestLoadRulesFromDirectory:
    def test_loads_from_directory(self) -> None:
        rules = load_rules_from_directory(FIXTURE_DIR)
        assert len(rules) >= 2

    def test_directory_with_multiple_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.yaml").write_text(
            "rules:\n"
            "  - id: A-001\n"
            "    name: A rule\n"
            "    dimension: completeness\n"
            "    severity: critical\n"
            "    dataset: ds\n"
            "    column: col\n"
            "    check: not_null\n",
            encoding="utf-8",
        )
        (tmp_path / "b.yml").write_text(
            "rules:\n"
            "  - id: B-001\n"
            "    name: B rule\n"
            "    dimension: validity\n"
            "    severity: warning\n"
            "    dataset: ds\n"
            "    column: col\n"
            "    check: unique\n",
            encoding="utf-8",
        )
        rules = load_rules_from_directory(tmp_path)
        assert len(rules) == 2
        ids = {r.id for r in rules}
        assert "A-001" in ids
        assert "B-001" in ids
