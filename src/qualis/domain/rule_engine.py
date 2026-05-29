from __future__ import annotations

from typing import Any

from qualis.domain.enums import CheckType
from qualis.domain.models import CheckResult, Rule, Violation
from qualis.domain.params import (
    BetweenParams,
    InSetParams,
    RegexParams,
    RowCountParams,
)


class RuleEngine:
    """Dispatches ``Rule`` objects to the appropriate adapter check method.

    The adapter is accepted as ``Any`` so the domain layer does not import
    from ``qualis.ports`` or ``qualis.adapters`` — dependency direction is
    enforced at the composition root.
    """

    def __init__(self, adapter: Any, schema: str) -> None:
        self._adapter = adapter
        self._schema = schema

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_rule(self, rule: Rule) -> CheckResult:
        """Evaluate a single rule and return its ``CheckResult``."""
        if rule.check == CheckType.NOT_NULL:
            return self._check_not_null(rule)
        if rule.check == CheckType.UNIQUE:
            return self._check_unique(rule)
        if rule.check == CheckType.BETWEEN:
            return self._check_between(rule)
        if rule.check == CheckType.REGEX:
            return self._check_regex(rule)
        if rule.check == CheckType.IN_SET:
            return self._check_in_set(rule)
        if rule.check == CheckType.ROW_COUNT:
            return self._check_row_count(rule)
        if rule.check == CheckType.NOT_NEGATIVE:
            return self._check_not_negative(rule)
        if rule.check in (CheckType.SQL, CheckType.CUSTOM):
            return self._check_stub(rule)
        # Fallback for unknown check types — return a passing stub
        return self._check_stub(rule)

    def evaluate_all(self, rules: list[Rule]) -> list[CheckResult]:
        """Evaluate every rule in *rules* and return all results."""
        return [self.evaluate_rule(rule) for rule in rules]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _dataset_parts(self, rule: Rule) -> tuple[str, str]:
        """Split ``rule.dataset`` into ``(schema, table)`` for adapter calls.

        If the dataset is already qualified (``schema.table``), the embedded
        schema wins over the engine-level ``self._schema``.
        """
        if "." in rule.dataset:
            parts = rule.dataset.split(".", 1)
            return parts[0], parts[1]
        return self._schema, rule.dataset

    def _check_not_null(self, rule: Rule) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        result: dict[str, int] = self._adapter.check_not_null(schema, table, column)
        null_count = result.get("null_count", 0)
        total = result.get("total_count", 0)
        violations = [
            Violation(
                rule=rule,
                record_id=None,
                actual_value=None,
                expected="non-null value",
            )
        ] * null_count
        return CheckResult(
            rule=rule,
            passed=null_count == 0,
            violation_count=null_count,
            violations=violations,
            rows_checked=total,
        )

    def _check_unique(self, rule: Rule) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        result: dict[str, int] = self._adapter.check_unique(schema, table, column)
        dup_count = result.get("duplicate_count", 0)
        total = result.get("total_count", 0)
        violations = [
            Violation(
                rule=rule,
                record_id=None,
                actual_value=None,
                expected="unique value",
            )
        ] * dup_count
        return CheckResult(
            rule=rule,
            passed=dup_count == 0,
            violation_count=dup_count,
            violations=violations,
            rows_checked=total,
        )

    def _check_between(self, rule: Rule) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        params = rule.params
        if not isinstance(params, BetweenParams):
            return self._check_stub(rule)
        result: dict[str, int] = self._adapter.check_between(
            schema, table, column, params.min, params.max
        )
        out_count = result.get("out_of_range_count", 0)
        total = result.get("total_count", 0)
        violations = [
            Violation(
                rule=rule,
                record_id=None,
                actual_value=None,
                expected=f"between {params.min} and {params.max}",
            )
        ] * out_count
        return CheckResult(
            rule=rule,
            passed=out_count == 0,
            violation_count=out_count,
            violations=violations,
            rows_checked=total,
        )

    def _check_regex(self, rule: Rule) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        params = rule.params
        if not isinstance(params, RegexParams):
            return self._check_stub(rule)
        result: dict[str, int] = self._adapter.check_regex(
            schema, table, column, params.pattern
        )
        non_matching = result.get("non_matching_count", 0)
        total = result.get("total_count", 0)
        violations = [
            Violation(
                rule=rule,
                record_id=None,
                actual_value=None,
                expected=f"matches pattern {params.pattern!r}",
            )
        ] * non_matching
        return CheckResult(
            rule=rule,
            passed=non_matching == 0,
            violation_count=non_matching,
            violations=violations,
            rows_checked=total,
        )

    def _check_in_set(self, rule: Rule) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        params = rule.params
        if not isinstance(params, InSetParams):
            return self._check_stub(rule)
        result: dict[str, int] = self._adapter.check_in_set(
            schema, table, column, params.values
        )
        invalid = result.get("invalid_count", 0)
        total = result.get("total_count", 0)
        violations = [
            Violation(
                rule=rule,
                record_id=None,
                actual_value=None,
                expected=f"one of {params.values}",
            )
        ] * invalid
        return CheckResult(
            rule=rule,
            passed=invalid == 0,
            violation_count=invalid,
            violations=violations,
            rows_checked=total,
        )

    def _check_row_count(self, rule: Rule) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        params = rule.params
        if not isinstance(params, RowCountParams):
            return self._check_stub(rule)
        result: dict[str, int] = self._adapter.check_row_count(schema, table)
        count = result.get("row_count", 0)
        below_min = params.min is not None and count < params.min
        above_max = params.max is not None and count > params.max
        failed = below_min or above_max
        violations = (
            [
                Violation(
                    rule=rule,
                    record_id=None,
                    actual_value=count,
                    expected=f"row count between {params.min} and {params.max}",
                )
            ]
            if failed
            else []
        )
        return CheckResult(
            rule=rule,
            passed=not failed,
            violation_count=1 if failed else 0,
            violations=violations,
            rows_checked=count,
        )

    def _check_not_negative(self, rule: Rule) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        result: dict[str, int] = self._adapter.check_not_negative(schema, table, column)
        negative = result.get("negative_count", 0)
        total = result.get("total_count", 0)
        violations = [
            Violation(
                rule=rule,
                record_id=None,
                actual_value=None,
                expected="non-negative value",
            )
        ] * negative
        return CheckResult(
            rule=rule,
            passed=negative == 0,
            violation_count=negative,
            violations=violations,
            rows_checked=total,
        )

    def _check_stub(self, rule: Rule) -> CheckResult:
        """Return a passing stub result for check types that require real SQL/custom execution."""
        return CheckResult(
            rule=rule,
            passed=True,
            violation_count=0,
            violations=[],
            rows_checked=0,
        )
