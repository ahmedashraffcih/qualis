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


# ---------------------------------------------------------------------------
# v0.3.0: status + metadata round-trip
# ---------------------------------------------------------------------------


def test_loader_reads_status_field(tmp_path: Path) -> None:
    from qualis.config.loader import load_rules_from_file
    from qualis.domain.enums import RuleStatus

    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        "rules:\n"
        "  - id: r1\n"
        '    name: "x"\n'
        "    dimension: completeness\n"
        "    severity: critical\n"
        "    dataset: d\n"
        "    column: c\n"
        "    check: not_null\n"
        "    status: needs_evidence\n",
        encoding="utf-8",
    )
    rules = load_rules_from_file(rules_file)
    assert rules[0].status == RuleStatus.NEEDS_EVIDENCE


def test_loader_defaults_status_to_active_when_absent(tmp_path: Path) -> None:
    from qualis.config.loader import load_rules_from_file
    from qualis.domain.enums import RuleStatus

    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        "rules:\n"
        "  - id: r1\n"
        '    name: "x"\n'
        "    dimension: completeness\n"
        "    severity: critical\n"
        "    dataset: d\n"
        "    column: c\n"
        "    check: not_null\n",
        encoding="utf-8",
    )
    rules = load_rules_from_file(rules_file)
    assert rules[0].status == RuleStatus.ACTIVE


def test_loader_reads_metadata_block(tmp_path: Path) -> None:
    from qualis.config.loader import load_rules_from_file

    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        "rules:\n"
        "  - id: r1\n"
        '    name: "x"\n'
        "    dimension: completeness\n"
        "    severity: critical\n"
        "    dataset: d\n"
        "    column: c\n"
        "    check: not_null\n"
        "    metadata:\n"
        "      owner: data-team\n"
        "      cde: true\n"
        "      frequency: daily\n",
        encoding="utf-8",
    )
    rules = load_rules_from_file(rules_file)
    assert rules[0].metadata["owner"] == "data-team"
    assert rules[0].metadata["cde"] is True
    assert rules[0].metadata["frequency"] == "daily"


def test_loader_parses_reference_lookup_rule(tmp_path: Path) -> None:
    from qualis.config.loader import load_rules_from_file
    from qualis.domain.params import ReferenceLookupParams

    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        "rules:\n"
        "  - id: r1\n"
        '    name: "country FK"\n'
        "    dimension: integrity\n"
        "    severity: critical\n"
        "    dataset: orders\n"
        "    column: country\n"
        "    check: reference_lookup\n"
        "    parameters:\n"
        "      reference: country_codes\n"
        "      key_column: code\n",
        encoding="utf-8",
    )
    rules = load_rules_from_file(rules_file)
    assert len(rules) == 1
    assert isinstance(rules[0].params, ReferenceLookupParams)
    assert rules[0].params.reference == "country_codes"
    assert rules[0].params.key_column == "code"


def test_between_without_min_max_raises(tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        "rules:\n"
        "  - id: r1\n"
        '    name: "amt range"\n'
        "    dimension: validity\n"
        "    severity: warning\n"
        "    dataset: orders\n"
        "    column: amount\n"
        "    check: between\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"between.*requires.*min.*max"):
        load_rules_from_file(rules_file)


def test_regex_without_pattern_raises(tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        "rules:\n"
        "  - id: r1\n"
        '    name: "email format"\n'
        "    dimension: validity\n"
        "    severity: warning\n"
        "    dataset: users\n"
        "    column: email\n"
        "    check: regex\n"
        "    parameters: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"regex.*requires.*pattern"):
        load_rules_from_file(rules_file)


def test_in_set_without_values_raises(tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        "rules:\n"
        "  - id: r1\n"
        '    name: "status set"\n'
        "    dimension: validity\n"
        "    severity: warning\n"
        "    dataset: orders\n"
        "    column: status\n"
        "    check: in_set\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"in_set.*requires.*values"):
        load_rules_from_file(rules_file)


def test_duplicate_rule_ids_raise(tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        "rules:\n"
        "  - id: DUP-1\n"
        '    name: "first"\n'
        "    dimension: completeness\n"
        "    severity: critical\n"
        "    dataset: t\n"
        "    column: a\n"
        "    check: not_null\n"
        "  - id: DUP-1\n"
        '    name: "second (shadow)"\n'
        "    dimension: completeness\n"
        "    severity: critical\n"
        "    dataset: t\n"
        "    column: b\n"
        "    check: not_null\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate rule id"):
        load_rules_from_file(rules_file)


class TestConditionValidation:
    """AgDR-0005: the loader is the condition trust boundary (located errors)."""

    def test_valid_condition_loads(self) -> None:
        rule = _parse_rule_helper({"condition": "status = 'active'"})
        assert rule.condition == "status = 'active'"

    def test_invalid_condition_fails_located(self) -> None:
        import pytest

        with pytest.raises(ValueError, match=r"rule 'r-cond'.*DROP"):
            _parse_rule_helper({"condition": "1=1; DROP TABLE x"}, rule_id="r-cond")


def _parse_rule_helper(extra: dict[str, object], rule_id: str = "r-1"):
    from qualis.config.loader import _parse_rule

    data: dict[str, object] = {
        "id": rule_id,
        "name": "n",
        "dimension": "completeness",
        "severity": "critical",
        "dataset": "d",
        "column": "c",
        "check": "not_null",
    }
    data.update(extra)
    return _parse_rule(data)


class TestReferenceJoinIdentifierValidation:
    """AgDR-0006 C4: JOIN-mode names must be plain identifiers at load."""

    def test_hostile_key_column_rejected(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="key_column"):
            _parse_rule_helper({
                "check": "reference_lookup",
                "parameters": {
                    "reference": "countries",
                    "key_column": 'x" = "x" OR 1=1 --',
                    "reference_schema": "refs",
                },
            })

    def test_values_mode_reference_may_be_a_path(self) -> None:
        rule = _parse_rule_helper({
            "check": "reference_lookup",
            "parameters": {
                "reference": "data/country_codes.csv",
                "key_column": "code",
            },
        })
        assert rule.params.reference == "data/country_codes.csv"

    def test_empty_reference_schema_means_default_schema(self) -> None:
        rule = _parse_rule_helper({
            "check": "reference_lookup",
            "parameters": {
                "reference": "countries",
                "key_column": "code",
                "reference_schema": "",
            },
        })
        assert rule.params.reference_schema == ""


class TestCrossDatasetAssertionLoading:
    """Load-time trust boundary for cross_dataset_assertion (AgDR-0008)."""

    @staticmethod
    def _yaml(
        *,
        metric: str = "row_count",
        reference_dataset: str = "staging.orders",
        extra_params: str = "",
        column_line: str = "",
    ) -> str:
        return (
            "rules:\n"
            "  - id: xds-1\n"
            "    name: fact vs staging\n"
            "    dimension: consistency\n"
            "    severity: critical\n"
            "    dataset: marts.orders\n"
            f"{column_line}"
            "    check: cross_dataset_assertion\n"
            "    parameters:\n"
            f"      metric: {metric}\n"
            f"      reference_dataset: {reference_dataset}\n"
            f"{extra_params}"
        )

    def test_loads_valid_row_count_rule(self, tmp_path: Path) -> None:
        p = tmp_path / "xds.yaml"
        p.write_text(
            self._yaml(extra_params="      tolerance_pct: '2'\n"), encoding="utf-8"
        )
        from qualis.domain.params import CrossDatasetParams

        (rule,) = load_rules_from_file(p)
        assert isinstance(rule.params, CrossDatasetParams)
        assert rule.params.metric == "row_count"
        assert rule.params.tolerance_pct == "2"

    def test_metric_whitelist_rejects_count_distinct(self, tmp_path: Path) -> None:
        p = tmp_path / "xds.yaml"
        p.write_text(self._yaml(metric="count_distinct"), encoding="utf-8")
        with pytest.raises(ValueError, match="count_distinct"):
            load_rules_from_file(p)

    def test_metric_whitelist_rejects_injection(self, tmp_path: Path) -> None:
        p = tmp_path / "xds.yaml"
        p.write_text(
            self._yaml(metric="'row_count; DROP TABLE x--'"), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="metric"):
            load_rules_from_file(p)

    def test_reference_dataset_identifier_validation(self, tmp_path: Path) -> None:
        p = tmp_path / "xds.yaml"
        p.write_text(
            self._yaml(reference_dataset="'staging.\"orders\"; --'"),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="identifier"):
            load_rules_from_file(p)

    def test_reference_dataset_too_many_parts_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "xds.yaml"
        p.write_text(self._yaml(reference_dataset="db.staging.orders"), encoding="utf-8")
        with pytest.raises(ValueError, match=r"identifier|parts"):
            load_rules_from_file(p)

    def test_sum_requires_rule_column(self, tmp_path: Path) -> None:
        p = tmp_path / "xds.yaml"
        p.write_text(self._yaml(metric="sum"), encoding="utf-8")
        with pytest.raises(ValueError, match="column"):
            load_rules_from_file(p)

    def test_sum_with_column_loads(self, tmp_path: Path) -> None:
        p = tmp_path / "xds.yaml"
        p.write_text(
            self._yaml(metric="sum", column_line="    column: amount\n"),
            encoding="utf-8",
        )
        (rule,) = load_rules_from_file(p)
        assert rule.column == "amount"

    def test_reference_column_identifier_validation(self, tmp_path: Path) -> None:
        p = tmp_path / "xds.yaml"
        p.write_text(
            self._yaml(
                metric="sum",
                column_line="    column: amount\n",
                extra_params="      reference_column: '\"amt\"; --'\n",
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="identifier"):
            load_rules_from_file(p)

    def test_negative_tolerance_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "xds.yaml"
        p.write_text(
            self._yaml(extra_params="      tolerance_pct: '-1'\n"), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="tolerance"):
            load_rules_from_file(p)

    def test_non_numeric_tolerance_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "xds.yaml"
        p.write_text(
            self._yaml(extra_params="      tolerance_pct: 'lots'\n"), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="tolerance"):
            load_rules_from_file(p)

    def test_missing_reference_dataset_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "xds.yaml"
        p.write_text(
            "rules:\n"
            "  - id: xds-1\n"
            "    name: incomplete\n"
            "    dimension: consistency\n"
            "    severity: critical\n"
            "    dataset: marts.orders\n"
            "    check: cross_dataset_assertion\n"
            "    parameters:\n"
            "      metric: row_count\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="reference_dataset"):
            load_rules_from_file(p)
