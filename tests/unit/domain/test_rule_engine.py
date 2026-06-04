from __future__ import annotations

import pytest

from qualis.adapters.in_memory.adapter import InMemoryAdapter
from qualis.domain.enums import DQDimension, RuleType, Severity
from qualis.domain.models import Rule
from qualis.domain.params import (
    BetweenParams,
    InSetParams,
    NotNegativeParams,
    NotNullParams,
    RegexParams,
    RowCountParams,
    UniqueParams,
)
from qualis.domain.rule_engine import RuleEngine

SCHEMA = "test"
TABLE = "records"
DATASET = f"{SCHEMA}.{TABLE}"


def _make_rule(
    *,
    rule_id: str = "r-001",
    check: str,
    column: str | None = "value",
    params: object,
) -> Rule:
    return Rule(
        id=rule_id,
        name=f"Test {check}",
        dimension=DQDimension.COMPLETENESS,
        rule_type=RuleType.ROW_LEVEL,
        severity=Severity.CRITICAL,
        dataset=DATASET,
        column=column,
        check=check,
        params=params,
    )


@pytest.fixture()
def adapter() -> InMemoryAdapter:
    """InMemoryAdapter pre-loaded with a test table containing various bad data.

    Note: ``check_between`` uses lexicographic (string) comparison, so date
    strings are used for the ``event_date`` column to ensure well-defined ordering.
    """
    db = InMemoryAdapter()
    db.add_table(
        SCHEMA,
        TABLE,
        [
            {"id": "1", "value": None, "event_date": "2022-06-01", "code": "AB-123"},
            {"id": "2", "value": "dup", "event_date": "2022-07-15", "code": "AB-456"},
            {"id": "3", "value": "dup", "event_date": "2022-08-20", "code": "INVALID"},
            {"id": "4", "value": "ok", "event_date": "2025-01-01", "code": "CD-789"},
        ],
    )
    return db


@pytest.fixture()
def engine(adapter: InMemoryAdapter) -> RuleEngine:
    return RuleEngine(adapter, schema=SCHEMA)


class TestNotNull:
    def test_finds_null(self, engine: RuleEngine) -> None:
        rule = _make_rule(check="not_null", column="value", params=NotNullParams())
        result = engine.evaluate_rule(rule)
        assert not result.passed
        assert result.violation_count == 1
        assert result.rows_checked == 4

    def test_passes_when_no_nulls(self, engine: RuleEngine) -> None:
        rule = _make_rule(check="not_null", column="id", params=NotNullParams())
        result = engine.evaluate_rule(rule)
        assert result.passed
        assert result.violation_count == 0


class TestUnique:
    def test_finds_duplicate(self, engine: RuleEngine) -> None:
        rule = _make_rule(check="unique", column="value", params=UniqueParams())
        result = engine.evaluate_rule(rule)
        assert not result.passed
        assert result.violation_count >= 1

    def test_passes_when_unique(self, engine: RuleEngine) -> None:
        rule = _make_rule(check="unique", column="id", params=UniqueParams())
        result = engine.evaluate_rule(rule)
        assert result.passed


class TestBetween:
    def test_passes_when_in_range(self, engine: RuleEngine) -> None:
        # All dates fall between 2020-01-01 and 2026-01-01 (lexicographic ordering)
        rule = _make_rule(
            check="between",
            column="event_date",
            params=BetweenParams(min="2020-01-01", max="2026-01-01"),
        )
        result = engine.evaluate_rule(rule)
        assert result.passed
        assert result.violation_count == 0

    def test_finds_out_of_range(self, engine: RuleEngine) -> None:
        # 2025-01-01 is outside the range 2022-01-01 to 2023-01-01
        rule = _make_rule(
            check="between",
            column="event_date",
            params=BetweenParams(min="2022-01-01", max="2023-01-01"),
        )
        result = engine.evaluate_rule(rule)
        assert not result.passed
        assert result.violation_count >= 1


class TestRegex:
    def test_finds_non_matching(self, engine: RuleEngine) -> None:
        # Only "AB-123", "AB-456", "CD-789" match; "INVALID" does not.
        rule = _make_rule(
            check="regex",
            column="code",
            params=RegexParams(pattern=r"^[A-Z]{2}-\d+$"),
        )
        result = engine.evaluate_rule(rule)
        assert not result.passed
        assert result.violation_count >= 1

    def test_passes_when_all_match(self, engine: RuleEngine) -> None:
        # All ids are numeric strings
        rule = _make_rule(
            check="regex",
            column="id",
            params=RegexParams(pattern=r"^\d+$"),
        )
        result = engine.evaluate_rule(rule)
        assert result.passed


class TestSqlStub:
    def test_sql_check_is_marked_skipped_not_passing(self, engine: RuleEngine) -> None:
        """Regression: stub checks must NOT report passed=True.

        An unexecuted ``sql`` rule used to silently count as passing — a
        rule that never ran would contribute 100% to the aggregate. The
        engine now marks these SKIPPED so scoring excludes them.
        """
        from qualis.domain.params import SqlParams

        rule = _make_rule(
            check="sql",
            column=None,
            params=SqlParams(expression="SELECT COUNT(*) FROM records WHERE val IS NULL"),
        )
        result = engine.evaluate_rule(rule)
        assert result.skipped is True
        assert result.passed is False
        assert "not executable" in result.skip_reason
        assert result.violation_count == 0

    def test_custom_check_is_marked_skipped(self, engine: RuleEngine) -> None:
        from qualis.domain.params import CustomParams

        rule = _make_rule(
            check="custom",
            column=None,
            params=CustomParams(handler="my_module.my_handler"),
        )
        result = engine.evaluate_rule(rule)
        assert result.skipped is True
        assert result.passed is False

    def test_skipped_checks_excluded_from_dimension_score(self) -> None:
        """A skipped check must not boost or drag the dimension score."""
        from qualis.domain.enums import DQDimension
        from qualis.domain.models import CheckResult
        from qualis.domain.params import NotNullParams, SqlParams
        from qualis.domain.scoring import compute_dimension_scores

        passed = CheckResult(
            rule=_make_rule(rule_id="r1", check="not_null", column="x", params=NotNullParams()),
            passed=True, violation_count=0, violations=[], rows_checked=10,
        )
        sql_rule = _make_rule(
            rule_id="r2", check="sql", column=None, params=SqlParams(expression="x"),
        )
        skipped = CheckResult(
            rule=sql_rule,
            passed=False, violation_count=0, violations=[], rows_checked=0,
            skipped=True, skip_reason="stub",
        )
        scores = compute_dimension_scores([passed, skipped], dataset="t")
        # Only the executed check should appear in the bucket
        completeness_score = next(s for s in scores if s.dimension == DQDimension.COMPLETENESS)
        assert completeness_score.total_checks == 1
        assert completeness_score.score == 1.0


class TestEvaluateAll:
    def test_evaluates_multiple_rules(self, engine: RuleEngine) -> None:
        rules = [
            _make_rule(rule_id="r-001", check="not_null", column="value", params=NotNullParams()),
            _make_rule(rule_id="r-002", check="unique", column="id", params=UniqueParams()),
        ]
        results = engine.evaluate_all(rules)
        assert len(results) == 2
        # First rule has a null → fails
        assert not results[0].passed
        # Second rule all ids are unique → passes
        assert results[1].passed


class TestInSet:
    def test_finds_invalid_code(self, engine: RuleEngine) -> None:
        rule = _make_rule(
            check="in_set", column="code",
            params=InSetParams(values=["AB-123", "AB-456", "CD-789"]),
        )
        result = engine.evaluate_rule(rule)
        # "INVALID" is not in the set
        assert not result.passed
        assert result.violation_count == 1

    def test_all_valid(self, engine: RuleEngine) -> None:
        rule = _make_rule(
            check="in_set", column="code",
            params=InSetParams(values=["AB-123", "AB-456", "INVALID", "CD-789"]),
        )
        result = engine.evaluate_rule(rule)
        assert result.passed


class TestRowCount:
    def test_passes_when_in_range(self, engine: RuleEngine) -> None:
        rule = _make_rule(check="row_count", column=None, params=RowCountParams(min=1, max=10))
        result = engine.evaluate_rule(rule)
        assert result.passed

    def test_fails_when_below_min(self, engine: RuleEngine) -> None:
        rule = _make_rule(check="row_count", column=None, params=RowCountParams(min=100))
        result = engine.evaluate_rule(rule)
        assert not result.passed
        assert result.violation_count == 1

    def test_fails_when_above_max(self, engine: RuleEngine) -> None:
        rule = _make_rule(check="row_count", column=None, params=RowCountParams(max=2))
        result = engine.evaluate_rule(rule)
        assert not result.passed


class TestNotNegative:
    def test_all_non_negative(self) -> None:
        db = InMemoryAdapter()
        db.add_table(SCHEMA, TABLE, [{"amount": 10}, {"amount": 0}, {"amount": 5}])
        engine = RuleEngine(db, schema=SCHEMA)
        rule = _make_rule(check="not_negative", column="amount", params=NotNegativeParams())
        result = engine.evaluate_rule(rule)
        assert result.passed

    def test_finds_negative(self) -> None:
        db = InMemoryAdapter()
        db.add_table(SCHEMA, TABLE, [{"amount": 10}, {"amount": -5}, {"amount": 3}])
        engine = RuleEngine(db, schema=SCHEMA)
        rule = _make_rule(check="not_negative", column="amount", params=NotNegativeParams())
        result = engine.evaluate_rule(rule)
        assert not result.passed
        assert result.violation_count == 1


# ---------------------------------------------------------------------------
# v0.3.0: reference_lookup check
# ---------------------------------------------------------------------------


def test_reference_lookup_finds_invalid_keys() -> None:
    from qualis.adapters.in_memory.reference_data import InMemoryReferenceData
    from qualis.domain.params import ReferenceLookupParams

    db = InMemoryAdapter()
    db.add_table("public", "orders", [
        {"order_id": 1, "country": "US"},
        {"order_id": 2, "country": "ZZ"},  # invalid
        {"order_id": 3, "country": "GB"},
    ])
    ref = InMemoryReferenceData()
    ref.register("country_codes", "code", ["US", "GB", "DE"])

    rule = Rule(
        id="r1", name="x", dimension=DQDimension.INTEGRITY,
        rule_type=RuleType.REFERENTIAL, severity=Severity.CRITICAL,
        dataset="orders", column="country", check="reference_lookup",
        params=ReferenceLookupParams(reference="country_codes", key_column="code"),
    )
    engine = RuleEngine(db, schema="public", reference_data=ref)
    result = engine.evaluate_rule(rule)
    assert not result.passed
    assert result.violation_count == 1


def test_reference_lookup_passes_when_all_keys_valid() -> None:
    from qualis.adapters.in_memory.reference_data import InMemoryReferenceData
    from qualis.domain.params import ReferenceLookupParams

    db = InMemoryAdapter()
    db.add_table("public", "orders", [
        {"order_id": 1, "country": "US"},
        {"order_id": 2, "country": "GB"},
    ])
    ref = InMemoryReferenceData()
    ref.register("country_codes", "code", ["US", "GB", "DE"])

    rule = Rule(
        id="r1", name="x", dimension=DQDimension.INTEGRITY,
        rule_type=RuleType.REFERENTIAL, severity=Severity.CRITICAL,
        dataset="orders", column="country", check="reference_lookup",
        params=ReferenceLookupParams(reference="country_codes", key_column="code"),
    )
    engine = RuleEngine(db, schema="public", reference_data=ref)
    result = engine.evaluate_rule(rule)
    assert result.passed


class _HugeCountAdapter:
    """Stub adapter reporting massive failure counts without materialising rows.

    Used to prove the bounded-violations invariant: building the result must
    not allocate per-failing-row objects, so the stub returns counts only —
    exactly the contract real adapters follow.
    """

    def check_not_null(self, schema: str, table: str, column: str) -> dict[str, int]:
        return {"null_count": 1_000_000, "total_count": 1_000_000}


class TestBoundedViolations:
    def test_violations_list_is_bounded_under_massive_count(self) -> None:
        from qualis.domain.models import MAX_SAMPLE_VIOLATIONS

        engine = RuleEngine(_HugeCountAdapter(), schema=SCHEMA)
        rule = _make_rule(check="not_null", column="value", params=NotNullParams())
        result = engine.evaluate_rule(rule)
        assert result.violation_count == 1_000_000  # authoritative count
        assert 1 <= len(result.violations) <= MAX_SAMPLE_VIOLATIONS
        assert not result.passed

    def test_passing_check_has_empty_violations(self, engine: RuleEngine) -> None:
        rule = _make_rule(check="not_null", column="id", params=NotNullParams())
        result = engine.evaluate_rule(rule)
        assert result.violation_count == 0
        assert result.violations == []

    def test_failing_check_sample_carries_expected(self, engine: RuleEngine) -> None:
        rule = _make_rule(check="not_null", column="value", params=NotNullParams())
        result = engine.evaluate_rule(rule)
        assert result.violation_count == 1
        assert len(result.violations) == 1
        assert result.violations[0].expected == "non-null value"

    def test_row_count_sample_carries_actual_count(self, engine: RuleEngine) -> None:
        rule = _make_rule(
            check="row_count",
            column=None,
            params=RowCountParams(min=10, max=100),
        )
        result = engine.evaluate_rule(rule)
        assert not result.passed
        assert result.violations[0].actual_value == 4
        assert "row count between 10 and 100" in result.violations[0].expected
