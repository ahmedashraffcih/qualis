from __future__ import annotations

import logging
import math
from decimal import Decimal, InvalidOperation
from typing import Any

from qualis.domain.condition import (
    ConditionError,
    ConditionExpr,
    parse_condition,
)
from qualis.domain.enums import CheckType
from qualis.domain.models import (
    MAX_SAMPLE_VIOLATIONS,
    CheckResult,
    Rule,
    Violation,
)
from qualis.domain.params import (
    BetweenParams,
    CrossDatasetParams,
    InSetParams,
    ReferenceLookupParams,
    RegexParams,
    RowCountParams,
)

logger = logging.getLogger(__name__)


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
        sample_rows: int | None = None,
    ) -> None:
        self._adapter = adapter
        self._schema = schema
        self._reference_data = reference_data
        # When set AND the adapter exposes the optional
        # ``fetch_violation_samples`` capability, failing checks attach up to
        # min(sample_rows, MAX_SAMPLE_VIOLATIONS) real rows as evidence.
        self._sample_rows = sample_rows

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_rule(self, rule: Rule) -> CheckResult:
        """Evaluate a single rule and return its ``CheckResult``."""
        condition: ConditionExpr | None = None
        if rule.condition:
            try:
                condition = parse_condition(rule.condition)
            except ConditionError as exc:
                # Loader validation is the real gate; this is defence in
                # depth for rules constructed programmatically.
                return self._skipped(rule, f"invalid condition: {exc}")
            if not getattr(self._adapter, "supports_conditions", False):
                # Honesty rule (AgDR-0005): never run a conditioned rule
                # unfiltered on an adapter that cannot apply the condition.
                return self._skipped(
                    rule,
                    f"adapter {type(self._adapter).__name__} does not "
                    f"support rule conditions",
                )
        if rule.check == CheckType.NOT_NULL:
            return self._check_not_null(rule, condition)
        if rule.check == CheckType.UNIQUE:
            return self._check_unique(rule, condition)
        if rule.check == CheckType.BETWEEN:
            return self._check_between(rule, condition)
        if rule.check == CheckType.REGEX:
            return self._check_regex(rule, condition)
        if rule.check == CheckType.IN_SET:
            return self._check_in_set(rule, condition)
        if rule.check == CheckType.ROW_COUNT:
            return self._check_row_count(rule, condition)
        if rule.check == CheckType.NOT_NEGATIVE:
            return self._check_not_negative(rule, condition)
        if rule.check == CheckType.REFERENCE_LOOKUP:
            return self._check_reference_lookup(rule, condition)
        if rule.check == CheckType.CROSS_DATASET_ASSERTION:
            return self._check_cross_dataset(rule, condition)
        if rule.check in (CheckType.SQL, CheckType.CUSTOM):
            return self._check_stub(rule)
        # Fallback for unknown check types — return a passing stub
        return self._check_stub(rule)

    @staticmethod
    def _cond_kwargs(condition: ConditionExpr | None) -> dict[str, Any]:
        """Only pass the kwarg when a condition exists — unconditioned calls
        stay byte-compatible with adapters that predate conditions."""
        return {"condition": condition} if condition is not None else {}

    def _skipped(self, rule: Rule, reason: str) -> CheckResult:
        return CheckResult(
            rule=rule,
            passed=False,
            violation_count=0,
            violations=[],
            rows_checked=0,
            skipped=True,
            skip_reason=reason,
        )

    def _vacuous(
        self, rule: Rule, condition: ConditionExpr | None, total: int
    ) -> CheckResult | None:
        """Zero-row conditioned population → skipped (AgDR-0005).

        Applies to column-level checks only; ``row_count`` legitimately
        counts an empty population.
        """
        if condition is not None and total == 0:
            return self._skipped(rule, "condition matched no rows")
        return None

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

    def _sample(
        self,
        rule: Rule,
        *,
        expected: str,
        actual_value: Any = None,
        kind: str | None = None,
        sql_params: dict[str, Any] | None = None,
        condition: ConditionExpr | None = None,
    ) -> list[Violation]:
        """Build the bounded violations sample for a failing check.

        When sampling is requested (``sample_rows``), the check names its
        *kind*, and the adapter exposes the optional
        ``fetch_violation_samples`` capability, the sample holds up to
        ``min(sample_rows, MAX_SAMPLE_VIOLATIONS)`` real failing rows
        (``record_id``/``actual_value`` populated). Otherwise — including on
        a sampling error, which is logged, never raised — the sample is a
        single representative placeholder. ``CheckResult.violation_count``
        remains authoritative either way.
        """
        if (
            self._sample_rows
            and kind is not None
            and hasattr(self._adapter, "fetch_violation_samples")
        ):
            schema, table = self._dataset_parts(rule)
            limit = min(self._sample_rows, MAX_SAMPLE_VIOLATIONS)
            try:
                rows = self._adapter.fetch_violation_samples(
                    schema,
                    table,
                    rule.column or "",
                    kind,
                    sql_params or {},
                    limit,
                    **self._cond_kwargs(condition),
                )
            except Exception as exc:
                logger.warning(
                    "violation sampling failed for rule %s (%s); "
                    "falling back to placeholder sample",
                    rule.id,
                    exc,
                )
            else:
                if rows:
                    return [
                        Violation(
                            rule=rule,
                            record_id=(
                                str(r["record_id"])
                                if r.get("record_id") is not None
                                else None
                            ),
                            actual_value=r.get("actual_value"),
                            expected=expected,
                        )
                        for r in rows[:limit]
                    ]
        return [
            Violation(
                rule=rule,
                record_id=None,
                actual_value=actual_value,
                expected=expected,
            )
        ][:MAX_SAMPLE_VIOLATIONS]

    def _check_not_null(
        self, rule: Rule, condition: ConditionExpr | None = None
    ) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        result: dict[str, int] = self._adapter.check_not_null(
            schema, table, column, **self._cond_kwargs(condition)
        )
        null_count = result.get("null_count", 0)
        total = result.get("total_count", 0)
        if (vacuous := self._vacuous(rule, condition, total)) is not None:
            return vacuous
        violations = (
            self._sample(rule, expected="non-null value", kind="not_null", condition=condition)
            if null_count
            else []
        )
        return CheckResult(
            rule=rule,
            passed=null_count == 0,
            violation_count=null_count,
            violations=violations,
            rows_checked=total,
        )

    def _check_unique(
        self, rule: Rule, condition: ConditionExpr | None = None
    ) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        result: dict[str, int] = self._adapter.check_unique(
            schema, table, column, **self._cond_kwargs(condition)
        )
        dup_count = result.get("duplicate_count", 0)
        total = result.get("total_count", 0)
        if (vacuous := self._vacuous(rule, condition, total)) is not None:
            return vacuous
        violations = (
            self._sample(rule, expected="unique value", kind="unique", condition=condition)
            if dup_count
            else []
        )
        return CheckResult(
            rule=rule,
            passed=dup_count == 0,
            violation_count=dup_count,
            violations=violations,
            rows_checked=total,
        )

    def _check_between(
        self, rule: Rule, condition: ConditionExpr | None = None
    ) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        params = rule.params
        if not isinstance(params, BetweenParams):
            return self._check_stub(rule)
        result: dict[str, int] = self._adapter.check_between(
            schema,
            table,
            column,
            params.min,
            params.max,
            **self._cond_kwargs(condition),
        )
        out_count = result.get("out_of_range_count", 0)
        total = result.get("total_count", 0)
        if (vacuous := self._vacuous(rule, condition, total)) is not None:
            return vacuous
        violations = (
            self._sample(
                rule,
                expected=f"between {params.min} and {params.max}",
                kind="between",
                sql_params={"min": params.min, "max": params.max},
                condition=condition,
            )
            if out_count
            else []
        )
        return CheckResult(
            rule=rule,
            passed=out_count == 0,
            violation_count=out_count,
            violations=violations,
            rows_checked=total,
        )

    def _check_regex(
        self, rule: Rule, condition: ConditionExpr | None = None
    ) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        params = rule.params
        if not isinstance(params, RegexParams):
            return self._check_stub(rule)
        result: dict[str, int] = self._adapter.check_regex(
            schema, table, column, params.pattern, **self._cond_kwargs(condition)
        )
        non_matching = result.get("non_matching_count", 0)
        total = result.get("total_count", 0)
        if (vacuous := self._vacuous(rule, condition, total)) is not None:
            return vacuous
        violations = (
            self._sample(
                rule,
                expected=f"matches pattern {params.pattern!r}",
                kind="regex",
                sql_params={"pattern": params.pattern},
                condition=condition,
            )
            if non_matching
            else []
        )
        return CheckResult(
            rule=rule,
            passed=non_matching == 0,
            violation_count=non_matching,
            violations=violations,
            rows_checked=total,
        )

    def _check_in_set(
        self, rule: Rule, condition: ConditionExpr | None = None
    ) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        params = rule.params
        if not isinstance(params, InSetParams):
            return self._check_stub(rule)
        result: dict[str, int] = self._adapter.check_in_set(
            schema, table, column, params.values, **self._cond_kwargs(condition)
        )
        invalid = result.get("invalid_count", 0)
        total = result.get("total_count", 0)
        if (vacuous := self._vacuous(rule, condition, total)) is not None:
            return vacuous
        violations = (
            self._sample(
                rule,
                expected=f"one of {params.values}",
                kind="in_set",
                sql_params={"values": params.values},
                condition=condition,
            )
            if invalid
            else []
        )
        return CheckResult(
            rule=rule,
            passed=invalid == 0,
            violation_count=invalid,
            violations=violations,
            rows_checked=total,
        )

    def _check_row_count(
        self, rule: Rule, condition: ConditionExpr | None = None
    ) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        params = rule.params
        if not isinstance(params, RowCountParams):
            return self._check_stub(rule)
        result: dict[str, int] = self._adapter.check_row_count(
            schema, table, **self._cond_kwargs(condition)
        )
        count = result.get("row_count", 0)
        below_min = params.min is not None and count < params.min
        above_max = params.max is not None and count > params.max
        failed = below_min or above_max
        violations = (
            self._sample(
                rule,
                expected=f"row count between {params.min} and {params.max}",
                actual_value=count,
            )
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

    @staticmethod
    def _finite_decimal(value: Any) -> Decimal | None:
        """Convert an adapter aggregate to a finite Decimal, or None.

        ``None`` signals "not comparable" — NaN/Infinity from a float-column
        SUM, or a value Decimal cannot parse. The caller fails the check
        explicitly rather than comparing garbage (AgDR-0008).
        """
        if value is None:
            return None
        if isinstance(value, float) and not math.isfinite(value):
            return None
        try:
            d = Decimal(str(value))
        except InvalidOperation:
            return None
        if d.is_nan() or d.is_infinite():
            return None
        return d

    def _check_cross_dataset(
        self, rule: Rule, condition: ConditionExpr | None = None
    ) -> CheckResult:
        """Compare one aggregate between the rule's dataset and a reference.

        Table-level check (``violation_count`` ∈ {0,1}, row_count
        precedent). Two independent adapter calls — each leg is bounded by
        the per-statement timeout separately; the pair is not a consistent
        snapshot (documented in AgDR-0008). The rule's ``condition``
        applies to the TARGET leg only.
        """
        params = rule.params
        if not isinstance(params, CrossDatasetParams):
            return self._check_stub(rule)
        if not hasattr(self._adapter, "check_aggregate"):
            return self._skipped(
                rule,
                f"adapter {type(self._adapter).__name__} does not "
                f"implement cross_dataset_assertion",
            )

        schema, table = self._dataset_parts(rule)
        if "." in params.reference_dataset:
            ref_schema, ref_table = params.reference_dataset.split(".", 1)
        else:
            ref_schema, ref_table = self._schema, params.reference_dataset

        column = rule.column
        ref_column = params.reference_column or column

        if (schema, table, column) == (ref_schema, ref_table, ref_column):
            logger.warning(
                "rule %s compares a dataset to itself (%s.%s) — the "
                "assertion is trivially true; check reference_dataset",
                rule.id,
                schema,
                table,
            )

        # Detected, never guessed (AgDR-0006 precedent): probe the
        # reference before querying it, so a typo'd reference_dataset is a
        # located skip instead of a mid-run traceback.
        if hasattr(self._adapter, "table_exists") and not self._adapter.table_exists(
            ref_schema, ref_table
        ):
            return self._skipped(
                rule,
                f"reference dataset {ref_schema}.{ref_table} not found "
                f"in the checked database",
            )

        target_raw = self._adapter.check_aggregate(
            schema, table, params.metric, column, **self._cond_kwargs(condition)
        ).get("value")
        ref_raw = self._adapter.check_aggregate(
            ref_schema, ref_table, params.metric, ref_column
        ).get("value")

        target = self._finite_decimal(target_raw)
        ref = self._finite_decimal(ref_raw)
        expected_base = (
            f"{params.metric} within {params.tolerance_pct}% of "
            f"{ref_schema}.{ref_table}"
        )

        if target is None or ref is None:
            return CheckResult(
                rule=rule,
                passed=False,
                violation_count=1,
                violations=self._sample(
                    rule,
                    expected=f"finite aggregate for {expected_base}",
                    actual_value=f"target={target_raw!r} reference={ref_raw!r}",
                ),
                rows_checked=0,
            )

        # Zero-baseline convention (drift._relative_change): never divide.
        if ref == 0:
            failed = target != 0
            note = " (baseline was zero)" if failed else ""
        else:
            tolerance = Decimal(params.tolerance_pct) / Decimal(100)
            failed = abs(target - ref) / abs(ref) > tolerance
            note = ""

        violations = (
            self._sample(
                rule,
                expected=expected_base + note,
                actual_value=f"target={target} reference={ref}",
            )
            if failed
            else []
        )
        return CheckResult(
            rule=rule,
            passed=not failed,
            violation_count=1 if failed else 0,
            violations=violations,
            rows_checked=0,
        )

    def _check_not_negative(
        self, rule: Rule, condition: ConditionExpr | None = None
    ) -> CheckResult:
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        result: dict[str, int] = self._adapter.check_not_negative(
            schema, table, column, **self._cond_kwargs(condition)
        )
        negative = result.get("negative_count", 0)
        total = result.get("total_count", 0)
        if (vacuous := self._vacuous(rule, condition, total)) is not None:
            return vacuous
        violations = (
            self._sample(
                rule,
                expected="non-negative value",
                kind="not_negative",
                condition=condition,
            )
            if negative
            else []
        )
        return CheckResult(
            rule=rule,
            passed=negative == 0,
            violation_count=negative,
            violations=violations,
            rows_checked=total,
        )

    def _check_reference_lookup(
        self, rule: Rule, condition: ConditionExpr | None = None
    ) -> CheckResult:
        if not isinstance(rule.params, ReferenceLookupParams):
            return self._check_stub(rule)
        if rule.params.reference_schema is not None:
            return self._check_reference_join(rule, condition)
        if self._reference_data is None:
            # No reference data adapter wired in — record a violation so
            # the rule isn't silently skipped.
            return CheckResult(
                rule=rule, passed=False, violation_count=1,
                violations=self._sample(
                    rule, expected="reference data adapter not configured"
                ),
                rows_checked=0,
            )
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        valid_values = list(self._reference_data.load_values(
            rule.params.reference, rule.params.key_column,
        ))
        # Pushdown is required — the old full-column Python diff fallback is
        # removed (AgDR-0006): unbounded memory guarding a path no shipped
        # adapter needs. Honesty skip instead.
        if not hasattr(self._adapter, "check_reference_lookup"):
            return self._skipped(
                rule,
                f"adapter {type(self._adapter).__name__} does not implement "
                f"reference_lookup pushdown",
            )
        result = self._adapter.check_reference_lookup(
            schema, table, column, valid_values,
            **self._cond_kwargs(condition),
        )
        invalid = result.get("invalid_count", 0)
        total = result.get("total_count", 0)
        if (vacuous := self._vacuous(rule, condition, total)) is not None:
            return vacuous
        expected = (
            f"value present in {rule.params.reference}.{rule.params.key_column}"
        )
        violations = (
            self._sample(
                rule,
                expected=expected,
                kind="reference_lookup",
                sql_params={"valid_values": valid_values},
                condition=condition,
            )
            if invalid
            else []
        )
        return CheckResult(
            rule=rule, passed=invalid == 0,
            violation_count=invalid, violations=violations,
            rows_checked=total,
        )

    def _check_reference_join(
        self, rule: Rule, condition: ConditionExpr | None = None
    ) -> CheckResult:
        """JOIN-mode reference lookup — detected co-location (AgDR-0006).

        The author opted in via ``reference_schema``; the adapter's
        ``table_exists`` probe must confirm the reference table actually
        lives in the checked database. Detection failures skip loudly —
        silently falling back to the values path would mask a
        misconfiguration. The capability contract is a NULL-safe
        ``NOT EXISTS`` correlated subquery (review condition C1).
        """
        assert isinstance(rule.params, ReferenceLookupParams)
        params = rule.params
        ref_schema = params.reference_schema or ""
        if not hasattr(self._adapter, "check_reference_join"):
            return self._skipped(
                rule,
                f"adapter {type(self._adapter).__name__} does not support "
                f"reference JOIN pushdown",
            )
        if not self._adapter.table_exists(ref_schema, params.reference):
            return self._skipped(
                rule,
                f"reference table {ref_schema}.{params.reference} "
                f"not found in the checked database",
            )
        schema, table = self._dataset_parts(rule)
        column = rule.column or ""
        result: dict[str, int] = self._adapter.check_reference_join(
            schema,
            table,
            column,
            ref_schema,
            params.reference,
            params.key_column,
            **self._cond_kwargs(condition),
        )
        invalid = result.get("invalid_count", 0)
        total = result.get("total_count", 0)
        if (vacuous := self._vacuous(rule, condition, total)) is not None:
            return vacuous
        expected = (
            f"value present in {ref_schema}.{params.reference}."
            f"{params.key_column}"
        )
        violations = (
            self._sample(
                rule,
                expected=expected,
                kind="reference_join",
                sql_params={
                    "reference_schema": ref_schema,
                    "reference": params.reference,
                    "key_column": params.key_column,
                },
                condition=condition,
            )
            if invalid
            else []
        )
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
