from __future__ import annotations

from typing import Any

from qualis.domain.enums import CheckType
from qualis.domain.models import CheckResult, Rule, Violation
from qualis.domain.params import (
    BetweenParams,
    InSetParams,
    ReferenceLookupParams,
    RegexParams,
    RowCountParams,
)


class RuleEngine:
    """Dispatches ``Rule`` objects to the appropriate adapter check method.

    The adapter is accepted as ``Any`` so the domain layer does not import
    from ``qualis.ports`` or ``qualis.adapters`` — dependency direction is
    enforced at the composition root.
    """

    def __init__(
        self,
        adapter: Any,
        schema: str,
        reference_data: Any = None,
    ) -> None:
        self._adapter = adapter
        self._schema = schema
        self._reference_data = reference_data

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
        if rule.check == CheckType.REFERENCE_LOOKUP:
            return self._check_reference_lookup(rule)
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

    def _check_reference_lookup(self, rule: Rule) -> CheckResult:
        if not isinstance(rule.params, ReferenceLookupParams):
            return self._check_stub(rule)
        if self._reference_data is None:
            # No reference data adapter wired in — record a violation so
            # the rule isn't silently skipped.
            return CheckResult(
                rule=rule, passed=False, violation_count=1,
                violations=[Violation(
                    rule=rule, record_id=None, actual_value=None,
                    expected="reference data adapter not configured",
                )],
                rows_checked=0,
            )
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        valid_values = list(self._reference_data.load_values(
            rule.params.reference, rule.params.key_column,
        ))
        # Prefer adapter SQL pushdown when available; fall back to in-memory
        # diff via query() for adapters that don't implement it.
        if hasattr(self._adapter, "check_reference_lookup"):
            result = self._adapter.check_reference_lookup(
                schema, table, column, valid_values,
            )
            invalid = result.get("invalid_count", 0)
            total = result.get("total_count", 0)
        else:
            rows = self._adapter.query(f'SELECT "{column}" FROM "{schema}"."{table}"')
            valid_set = set(valid_values)
            invalid = sum(
                1 for r in rows
                if r.get(column) is not None and r.get(column) not in valid_set
            )
            total = len(rows)
        violations = [
            Violation(
                rule=rule, record_id=None, actual_value=None,
                expected=f"value present in {rule.params.reference}.{rule.params.key_column}",
            )
        ] * invalid
        return CheckResult(
            rule=rule, passed=invalid == 0,
            violation_count=invalid, violations=violations,
            rows_checked=total,
        )

    def _check_stub(self, rule: Rule) -> CheckResult:
        """Return a SKIPPED result for check types Qualis cannot execute itself.

        ``sql`` and ``custom`` rules require an out-of-band implementation
        (an analyst-supplied SQL fragment, or a user-supplied Python
        handler). Until that wiring exists, Qualis must NOT report these
        as passing — that would let unrun checks contribute 100% to the
        aggregate score and mask real failures. They are marked SKIPPED
        and excluded from the scoring denominator.
        """
        check_name = rule.check.value if hasattr(rule.check, "value") else str(rule.check)
        reason = (
            f"check type {check_name!r} is not executable in the engine yet "
            f"(rule {rule.id})"
        )
        return CheckResult(
            rule=rule,
            passed=False,
            violation_count=0,
            violations=[],
            rows_checked=0,
            skipped=True,
            skip_reason=reason,
        )
