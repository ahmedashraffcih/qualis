from __future__ import annotations

import dataclasses

import pytest

from qualis.domain.enums import DQDimension, RuleType, Severity
from qualis.domain.models import (
    CheckResult,
    DatasetScore,
    DimensionScore,
    Rule,
    Violation,
)
from qualis.domain.params import BetweenParams, NotNullParams, UniqueParams


def _make_rule(
    *,
    rule_id: str = "rule-001",
    name: str = "Email not null",
    dimension: DQDimension = DQDimension.COMPLETENESS,
    rule_type: RuleType = RuleType.ROW_LEVEL,
    severity: Severity = Severity.CRITICAL,
    dataset: str = "public.users",
    column: str | None = "email",
    check: str = "not_null",
    params: object = None,
) -> Rule:
    return Rule(
        id=rule_id,
        name=name,
        dimension=dimension,
        rule_type=rule_type,
        severity=severity,
        dataset=dataset,
        column=column,
        check=check,
        params=params if params is not None else NotNullParams(),
    )


class TestRule:
    def test_construction_required_fields(self) -> None:
        rule = _make_rule()
        assert rule.id == "rule-001"
        assert rule.name == "Email not null"
        assert rule.dimension is DQDimension.COMPLETENESS
        assert rule.rule_type is RuleType.ROW_LEVEL
        assert rule.severity is Severity.CRITICAL
        assert rule.dataset == "public.users"
        assert rule.column == "email"
        assert rule.check == "not_null"
        assert isinstance(rule.params, NotNullParams)

    def test_defaults(self) -> None:
        rule = _make_rule()
        assert rule.condition is None
        assert rule.description == ""
        assert rule.tags == []

    def test_with_optional_fields(self) -> None:
        rule = Rule(
            id="r-002",
            name="Age range",
            dimension=DQDimension.VALIDITY,
            rule_type=RuleType.ROW_LEVEL,
            severity=Severity.WARNING,
            dataset="public.users",
            column="age",
            check="between",
            params=BetweenParams(min="0", max="120"),
            condition="age IS NOT NULL",
            description="Age must be between 0 and 120",
            tags=["pii", "demographics"],
        )
        assert rule.condition == "age IS NOT NULL"
        assert rule.description == "Age must be between 0 and 120"
        assert rule.tags == ["pii", "demographics"]

    def test_is_frozen(self) -> None:
        rule = _make_rule()
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            rule.name = "mutated"  # type: ignore[misc]

    def test_frozen_id(self) -> None:
        rule = _make_rule()
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            rule.id = "new-id"  # type: ignore[misc]

    def test_column_none_table_level_rule(self) -> None:
        rule = _make_rule(column=None, check="row_count", params=UniqueParams())
        assert rule.column is None

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(Rule)

    def test_equality(self) -> None:
        r1 = _make_rule()
        r2 = _make_rule()
        assert r1 == r2

    def test_inequality_different_id(self) -> None:
        r1 = _make_rule(rule_id="rule-001")
        r2 = _make_rule(rule_id="rule-002")
        assert r1 != r2


class TestViolation:
    def test_construction(self) -> None:
        rule = _make_rule()
        v = Violation(
            rule=rule,
            record_id="row-42",
            actual_value=None,
            expected="non-null value",
        )
        assert v.rule is rule
        assert v.record_id == "row-42"
        assert v.actual_value is None
        assert v.expected == "non-null value"
        assert v.context == {}

    def test_with_context(self) -> None:
        rule = _make_rule()
        v = Violation(
            rule=rule,
            record_id="row-1",
            actual_value="bad",
            expected="valid email",
            context={"source": "import", "batch": "2024-01-01"},
        )
        assert v.context["source"] == "import"
        assert v.context["batch"] == "2024-01-01"

    def test_record_id_none(self) -> None:
        rule = _make_rule()
        v = Violation(rule=rule, record_id=None, actual_value=0, expected="> 0")
        assert v.record_id is None

    def test_is_frozen(self) -> None:
        rule = _make_rule()
        v = Violation(rule=rule, record_id="r1", actual_value=None, expected="x")
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            v.record_id = "mutated"  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(Violation)


class TestCheckResult:
    def test_construction_passing(self) -> None:
        rule = _make_rule()
        result = CheckResult(
            rule=rule,
            passed=True,
            violation_count=0,
            violations=[],
            rows_checked=100,
        )
        assert result.rule is rule
        assert result.passed is True
        assert result.violation_count == 0
        assert result.violations == []
        assert result.rows_checked == 100

    def test_construction_failing(self) -> None:
        rule = _make_rule()
        v = Violation(rule=rule, record_id="r1", actual_value=None, expected="non-null")
        result = CheckResult(
            rule=rule,
            passed=False,
            violation_count=1,
            violations=[v],
            rows_checked=50,
        )
        assert result.passed is False
        assert result.violation_count == 1
        assert len(result.violations) == 1

    def test_is_frozen(self) -> None:
        rule = _make_rule()
        result = CheckResult(
            rule=rule, passed=True, violation_count=0, violations=[], rows_checked=10
        )
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            result.passed = False  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(CheckResult)


class TestDimensionScore:
    def test_perfect_score(self) -> None:
        ds = DimensionScore(
            dimension=DQDimension.COMPLETENESS,
            dataset="public.users",
            total_checks=10,
            passed=10,
            failed=0,
            score=1.0,
        )
        assert ds.score == 1.0
        assert ds.failed == 0
        assert ds.weight == 1.0  # default

    def test_partial_score(self) -> None:
        ds = DimensionScore(
            dimension=DQDimension.VALIDITY,
            dataset="public.orders",
            total_checks=10,
            passed=7,
            failed=3,
            score=0.7,
        )
        assert ds.score == 0.7
        assert ds.passed == 7
        assert ds.failed == 3

    def test_zero_score(self) -> None:
        ds = DimensionScore(
            dimension=DQDimension.UNIQUENESS,
            dataset="public.events",
            total_checks=5,
            passed=0,
            failed=5,
            score=0.0,
        )
        assert ds.score == 0.0

    def test_custom_weight(self) -> None:
        ds = DimensionScore(
            dimension=DQDimension.ACCURACY,
            dataset="public.products",
            total_checks=4,
            passed=4,
            failed=0,
            score=1.0,
            weight=2.0,
        )
        assert ds.weight == 2.0

    def test_is_frozen(self) -> None:
        ds = DimensionScore(
            dimension=DQDimension.COMPLETENESS,
            dataset="ds",
            total_checks=1,
            passed=1,
            failed=0,
            score=1.0,
        )
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            ds.score = 0.5  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(DimensionScore)


class TestDatasetScore:
    def _dim_score(self, passed: int, failed: int) -> DimensionScore:
        return DimensionScore(
            dimension=DQDimension.COMPLETENESS,
            dataset="public.users",
            total_checks=passed + failed,
            passed=passed,
            failed=failed,
            score=passed / (passed + failed) if (passed + failed) else 0.0,
        )

    def test_construction(self) -> None:
        dim_scores = [self._dim_score(8, 2), self._dim_score(10, 0)]
        score = DatasetScore(
            dataset="public.users",
            dimension_scores=dim_scores,
            aggregate_score=0.9,
            total_violations=2,
            critical_violations=1,
        )
        assert score.dataset == "public.users"
        assert len(score.dimension_scores) == 2
        assert score.aggregate_score == 0.9
        assert score.total_violations == 2
        assert score.critical_violations == 1

    def test_no_violations(self) -> None:
        score = DatasetScore(
            dataset="public.clean",
            dimension_scores=[],
            aggregate_score=1.0,
            total_violations=0,
            critical_violations=0,
        )
        assert score.total_violations == 0
        assert score.critical_violations == 0

    def test_is_frozen(self) -> None:
        score = DatasetScore(
            dataset="ds",
            dimension_scores=[],
            aggregate_score=1.0,
            total_violations=0,
            critical_violations=0,
        )
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            score.aggregate_score = 0.5  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(DatasetScore)


# ---------------------------------------------------------------------------
# v0.3.0: Rule lifecycle, lineage, and metadata fields
# ---------------------------------------------------------------------------


def test_rule_has_default_status_active() -> None:
    from qualis.domain.enums import DQDimension, RuleStatus, RuleType, Severity
    from qualis.domain.models import Rule
    from qualis.domain.params import NotNullParams

    rule = Rule(
        id="r", name="r", dimension=DQDimension.COMPLETENESS,
        rule_type=RuleType.AGGREGATE, severity=Severity.CRITICAL,
        dataset="d", column="c", check="not_null", params=NotNullParams(),
    )
    assert rule.status == RuleStatus.ACTIVE


def test_rule_lineage_fields_default_to_none() -> None:
    from qualis.domain.enums import DQDimension, RuleType, Severity
    from qualis.domain.models import Rule
    from qualis.domain.params import NotNullParams

    rule = Rule(
        id="r", name="r", dimension=DQDimension.COMPLETENESS,
        rule_type=RuleType.AGGREGATE, severity=Severity.CRITICAL,
        dataset="d", column="c", check="not_null", params=NotNullParams(),
    )
    assert rule.version is None
    assert rule.supersedes is None
    assert rule.deprecated_at is None
    assert rule.approved_by is None


def test_rule_metadata_defaults_to_empty_dict() -> None:
    from qualis.domain.enums import DQDimension, RuleType, Severity
    from qualis.domain.models import Rule
    from qualis.domain.params import NotNullParams

    rule = Rule(
        id="r", name="r", dimension=DQDimension.COMPLETENESS,
        rule_type=RuleType.AGGREGATE, severity=Severity.CRITICAL,
        dataset="d", column="c", check="not_null", params=NotNullParams(),
    )
    assert rule.metadata == {}


def test_rule_can_carry_custom_metadata() -> None:
    from qualis.domain.enums import DQDimension, RuleType, Severity
    from qualis.domain.models import Rule
    from qualis.domain.params import NotNullParams

    rule = Rule(
        id="r", name="r", dimension=DQDimension.COMPLETENESS,
        rule_type=RuleType.AGGREGATE, severity=Severity.CRITICAL,
        dataset="d", column="c", check="not_null", params=NotNullParams(),
        metadata={"owner": "data-team", "cde": True, "frequency": "daily"},
    )
    assert rule.metadata["owner"] == "data-team"
    assert rule.metadata["cde"] is True


def test_existing_rule_construction_still_works() -> None:
    """Backwards-compat: existing call-sites must keep working."""
    from qualis.domain.enums import DQDimension, RuleType, Severity
    from qualis.domain.models import Rule
    from qualis.domain.params import NotNullParams

    rule = Rule(
        id="r", name="r", dimension=DQDimension.COMPLETENESS,
        rule_type=RuleType.AGGREGATE, severity=Severity.CRITICAL,
        dataset="d", column="c", check="not_null", params=NotNullParams(),
    )
    assert rule.id == "r"
