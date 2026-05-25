from __future__ import annotations

import pytest

from qualis.adapters.in_memory.adapter import InMemoryAdapter
from qualis.domain.enums import DQDimension, RuleType, Severity
from qualis.domain.models import Rule
from qualis.domain.params import BetweenParams, NotNullParams, RegexParams, UniqueParams
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
    def test_sql_check_returns_passing_stub(self, engine: RuleEngine) -> None:
        from qualis.domain.params import SqlParams

        rule = _make_rule(
            check="sql",
            column=None,
            params=SqlParams(expression="SELECT COUNT(*) FROM records WHERE val IS NULL"),
        )
        result = engine.evaluate_rule(rule)
        assert result.passed
        assert result.violation_count == 0


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
