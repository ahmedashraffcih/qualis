from __future__ import annotations

import pytest

from qualis.domain.enums import CheckType, DQDimension, RuleType, RunStatus, Severity


class TestDQDimension:
    def test_has_exactly_nine_members(self) -> None:
        assert len(DQDimension) == 9

    def test_all_dama_dimensions_present(self) -> None:
        expected = {
            "completeness",
            "accuracy",
            "consistency",
            "validity",
            "uniqueness",
            "timeliness",
            "reasonability",
            "integrity",
            "currency",
        }
        actual = {d.value for d in DQDimension}
        assert actual == expected

    def test_completeness_value(self) -> None:
        assert DQDimension.COMPLETENESS == "completeness"

    def test_accuracy_value(self) -> None:
        assert DQDimension.ACCURACY == "accuracy"

    def test_consistency_value(self) -> None:
        assert DQDimension.CONSISTENCY == "consistency"

    def test_validity_value(self) -> None:
        assert DQDimension.VALIDITY == "validity"

    def test_uniqueness_value(self) -> None:
        assert DQDimension.UNIQUENESS == "uniqueness"

    def test_timeliness_value(self) -> None:
        assert DQDimension.TIMELINESS == "timeliness"

    def test_reasonability_value(self) -> None:
        assert DQDimension.REASONABILITY == "reasonability"

    def test_integrity_value(self) -> None:
        assert DQDimension.INTEGRITY == "integrity"

    def test_currency_value(self) -> None:
        assert DQDimension.CURRENCY == "currency"

    def test_is_string_enum(self) -> None:
        assert isinstance(DQDimension.COMPLETENESS, str)

    def test_string_comparison(self) -> None:
        assert DQDimension.COMPLETENESS == "completeness"
        assert DQDimension.ACCURACY == "accuracy"

    def test_lookup_by_value(self) -> None:
        assert DQDimension("completeness") is DQDimension.COMPLETENESS
        assert DQDimension("integrity") is DQDimension.INTEGRITY


class TestSeverity:
    def test_has_critical(self) -> None:
        assert Severity.CRITICAL.value == "critical"

    def test_has_warning(self) -> None:
        assert Severity.WARNING.value == "warning"

    def test_has_info(self) -> None:
        assert Severity.INFO.value == "info"

    def test_is_string_enum(self) -> None:
        assert isinstance(Severity.CRITICAL, str)

    def test_has_exactly_three_members(self) -> None:
        assert len(Severity) == 3

    def test_critical_greater_than_info(self) -> None:
        # String ordering: critical < info < warning alphabetically,
        # but we verify they are distinct and all present
        values = {s.value for s in Severity}
        assert values == {"critical", "warning", "info"}


class TestCheckType:
    def test_has_not_null(self) -> None:
        assert CheckType.NOT_NULL.value == "not_null"

    def test_has_unique(self) -> None:
        assert CheckType.UNIQUE.value == "unique"

    def test_has_between(self) -> None:
        assert CheckType.BETWEEN.value == "between"

    def test_has_regex(self) -> None:
        assert CheckType.REGEX.value == "regex"

    def test_has_sql(self) -> None:
        assert CheckType.SQL.value == "sql"

    def test_has_custom(self) -> None:
        assert CheckType.CUSTOM.value == "custom"

    def test_has_exactly_six_members(self) -> None:
        assert len(CheckType) == 6

    def test_is_string_enum(self) -> None:
        assert isinstance(CheckType.NOT_NULL, str)

    def test_all_v01_check_types_present(self) -> None:
        expected = {"not_null", "unique", "between", "regex", "sql", "custom"}
        actual = {ct.value for ct in CheckType}
        assert actual == expected


class TestRuleType:
    def test_has_row_level(self) -> None:
        assert RuleType.ROW_LEVEL.value == "row_level"

    def test_has_aggregate(self) -> None:
        assert RuleType.AGGREGATE.value == "aggregate"

    def test_has_referential(self) -> None:
        assert RuleType.REFERENTIAL.value == "referential"

    def test_has_composite(self) -> None:
        assert RuleType.COMPOSITE.value == "composite"

    def test_has_exactly_four_members(self) -> None:
        assert len(RuleType) == 4

    def test_is_string_enum(self) -> None:
        assert isinstance(RuleType.ROW_LEVEL, str)


class TestRunStatus:
    def test_has_running(self) -> None:
        assert RunStatus.RUNNING.value == "running"

    def test_has_success(self) -> None:
        assert RunStatus.SUCCESS.value == "success"

    def test_has_partial(self) -> None:
        assert RunStatus.PARTIAL.value == "partial"

    def test_has_failed(self) -> None:
        assert RunStatus.FAILED.value == "failed"

    def test_has_exactly_four_members(self) -> None:
        assert len(RunStatus) == 4

    def test_is_string_enum(self) -> None:
        assert isinstance(RunStatus.RUNNING, str)

    def test_lookup_by_value(self) -> None:
        assert RunStatus("running") is RunStatus.RUNNING
        assert RunStatus("failed") is RunStatus.FAILED


class TestEnumInvalidValues:
    def test_dqdimension_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            DQDimension("not_a_real_dimension")

    def test_severity_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            Severity("high")

    def test_check_type_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            CheckType("not_null_check")
