from __future__ import annotations

import pytest

from qualis.domain.condition import (
    ConditionError,
    evaluate_condition,
    parse_condition,
)


class TestParseAccepts:
    @pytest.mark.parametrize(
        "text",
        [
            "status = 'active'",
            "amount > 100",
            "amount >= 100.5",
            "balance > -100",  # signed literal (review condition C1)
            "temp < -40.5",
            "region != 'EU'",
            "code <> 'X'",
            "deleted_at IS NULL",
            "deleted_at IS NOT NULL",
            "severity IN ('FATAL', 'SERIOUS')",
            "severity IN ('FATAL')",  # single-element is fine
            "severity NOT IN ('TEST')",
            "status = 'active' AND amount > 0",
            "status = 'active' OR status = 'pending'",
            "(status = 'a' OR status = 'b') AND amount > 0",
            "a = 1 AND b = 2 AND c = 3",
        ],
    )
    def test_valid_conditions_parse(self, text: str) -> None:
        assert parse_condition(text) is not None

    def test_case_insensitive_keywords(self) -> None:
        assert parse_condition("x is null and y in ('a')") is not None


class TestParseRejects:
    @pytest.mark.parametrize(
        "text",
        [
            "1=1; DROP TABLE users",  # statement smuggling
            "id IN (SELECT id FROM other)",  # subquery
            "lower(status) = 'active'",  # function call
            "amount > other_column",  # cross-column comparison
            "status = \"active\"",  # double-quoted string literal
            "status LIKE 'a%'",  # operator outside grammar
            "severity IN ()",  # empty IN (review condition C1)
            "status = 'unterminated",  # broken literal
            "AND status = 'a'",  # dangling operator
            "status = 'a' AND",  # trailing operator
            "",  # empty
            "   ",  # blank
            "status = 'a' -- comment",  # comment smuggling
        ],
    )
    def test_forbidden_conditions_raise(self, text: str) -> None:
        with pytest.raises(ConditionError):
            parse_condition(text)

    def test_error_carries_offending_text(self) -> None:
        with pytest.raises(ConditionError) as excinfo:
            parse_condition("lower(status) = 'active'")
        assert "lower" in str(excinfo.value)


class TestEvaluate:
    def _check(self, text: str, row: dict[str, object]) -> bool:
        return evaluate_condition(parse_condition(text), row)

    def test_string_equality(self) -> None:
        assert self._check("status = 'active'", {"status": "active"})
        assert not self._check("status = 'active'", {"status": "closed"})

    def test_numeric_comparison_coerces(self) -> None:
        assert self._check("amount > 100", {"amount": 150})
        assert self._check("amount > 100", {"amount": "150"})  # stringly-typed rows
        assert not self._check("amount > 100", {"amount": 50})

    def test_signed_literal(self) -> None:
        assert self._check("balance > -100", {"balance": -50})
        assert not self._check("balance > -100", {"balance": -200})

    def test_null_semantics_sql_like(self) -> None:
        # NULL fails every comparison (SQL three-valued logic collapses to False)
        assert not self._check("amount > 100", {"amount": None})
        assert not self._check("status = 'active'", {"status": None})
        assert not self._check("status != 'active'", {"status": None})
        assert self._check("status IS NULL", {"status": None})
        assert not self._check("status IS NOT NULL", {"status": None})

    def test_in_and_not_in(self) -> None:
        assert self._check("sev IN ('A', 'B')", {"sev": "A"})
        assert not self._check("sev IN ('A', 'B')", {"sev": "C"})
        assert self._check("sev NOT IN ('A')", {"sev": "B"})
        assert not self._check("sev NOT IN ('A')", {"sev": None})  # NULL: not counted

    def test_boolean_combinators_and_parens(self) -> None:
        row = {"s": "a", "n": 5}
        assert self._check("s = 'a' AND n > 1", row)
        assert not self._check("s = 'b' AND n > 1", row)
        assert self._check("s = 'b' OR n > 1", row)
        assert self._check("(s = 'b' OR s = 'a') AND n < 10", row)

    def test_missing_column_raises_located_error(self) -> None:
        with pytest.raises(ConditionError, match="no_such_col"):
            self._check("no_such_col = 'x'", {"other": 1})


class TestColumnsReferenced:
    def test_columns_are_collected(self) -> None:
        expr = parse_condition("(a = 1 OR b IS NULL) AND c IN ('x')")
        assert expr.columns() == {"a", "b", "c"}
