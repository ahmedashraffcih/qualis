"""Rule suggestion engine — deterministic heuristics over a table profile.

Generates DQ rule suggestions using statistical observations:
- not_null when 0 nulls observed
- unique when column is likely an ID
- in_set when low-cardinality (<= 10 distinct)
- between when numeric/date with observed min/max
- not_negative when numeric with min >= 0
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from qualis.domain.enums import DQDimension, RuleType, Severity
from qualis.domain.models import Rule
from qualis.domain.params import (
    BetweenParams,
    InSetParams,
    NotNegativeParams,
    NotNullParams,
    UniqueParams,
)

if TYPE_CHECKING:
    from qualis.discover.profiler import ColumnProfile, TableProfile

Confidence = Literal["high", "medium", "low"]

_LOW_CARDINALITY_THRESHOLD = 10
_NUMERIC_TYPES = frozenset({"integer", "float"})


@dataclass(frozen=True)
class RuleSuggestion:
    rule: Rule
    confidence: Confidence
    rationale: str


def _rule_id(dataset: str, column: str | None, check: str) -> str:
    col_part = column or "table"
    return f"DQ-{check.upper()}-{dataset}-{col_part}"


def suggest_rules(profile: TableProfile) -> list[RuleSuggestion]:
    """Generate deterministic rule suggestions from a table profile."""
    suggestions: list[RuleSuggestion] = []
    dataset = profile.table

    for col in profile.columns:
        suggestions.extend(_suggest_for_column(dataset, col))

    return suggestions


def _suggest_for_column(dataset: str, col: ColumnProfile) -> list[RuleSuggestion]:
    out: list[RuleSuggestion] = []

    if col.total_count > 0 and col.null_count == 0:
        # ID-like columns are nearly always business-required; treat them as critical.
        is_id_or_pk = col.is_likely_id or col.name.lower() in {"id", "pk", "uuid"}
        not_null_severity = Severity.CRITICAL if is_id_or_pk else Severity.WARNING
        out.append(
            RuleSuggestion(
                rule=Rule(
                    id=_rule_id(dataset, col.name, "not_null"),
                    name=f"{col.name} must not be null",
                    dimension=DQDimension.COMPLETENESS,
                    rule_type=RuleType.AGGREGATE,
                    severity=not_null_severity,
                    dataset=dataset,
                    column=col.name,
                    check="not_null",
                    params=NotNullParams(),
                ),
                confidence="high",
                rationale=f"0 nulls observed in {col.total_count} rows",
            )
        )

    if col.is_likely_id:
        non_null = col.total_count - col.null_count
        is_named_id = col.name.lower().endswith("id")
        confidence: Confidence = "high" if is_named_id else "medium"
        # Named IDs are foundational — duplicate IDs break downstream joins.
        unique_severity = Severity.CRITICAL if is_named_id else Severity.WARNING
        out.append(
            RuleSuggestion(
                rule=Rule(
                    id=_rule_id(dataset, col.name, "unique"),
                    name=f"{col.name} must be unique",
                    dimension=DQDimension.UNIQUENESS,
                    rule_type=RuleType.AGGREGATE,
                    severity=unique_severity,
                    dataset=dataset,
                    column=col.name,
                    check="unique",
                    params=UniqueParams(),
                ),
                confidence=confidence,
                rationale=(
                    f"distinct/{non_null} non-null rows = {col.distinct_fraction:.0%}; "
                    f"name suggests identifier"
                ),
            )
        )

    if (
        col.inferred_type == "string"
        and 0 < col.distinct_count <= _LOW_CARDINALITY_THRESHOLD
        and col.sample_values
    ):
        out.append(
            RuleSuggestion(
                rule=Rule(
                    id=_rule_id(dataset, col.name, "in_set"),
                    name=f"{col.name} must be one of the observed values",
                    dimension=DQDimension.VALIDITY,
                    rule_type=RuleType.AGGREGATE,
                    severity=Severity.WARNING,
                    dataset=dataset,
                    column=col.name,
                    check="in_set",
                    params=InSetParams(values=list(col.sample_values)),
                ),
                confidence="high",
                rationale=f"{col.distinct_count} distinct values observed",
            )
        )

    if (
        col.inferred_type in _NUMERIC_TYPES or col.inferred_type == "date"
    ) and col.min_value is not None and col.max_value is not None:
        out.append(
            RuleSuggestion(
                rule=Rule(
                    id=_rule_id(dataset, col.name, "between"),
                    name=f"{col.name} must be within observed range",
                    dimension=DQDimension.VALIDITY,
                    rule_type=RuleType.AGGREGATE,
                    severity=Severity.WARNING,
                    dataset=dataset,
                    column=col.name,
                    check="between",
                    params=BetweenParams(min=col.min_value, max=col.max_value),
                ),
                confidence="medium",
                rationale=f"observed range [{col.min_value}, {col.max_value}]",
            )
        )

    if col.inferred_type in _NUMERIC_TYPES and col.min_value is not None:
        try:
            if float(col.min_value) >= 0:
                out.append(
                    RuleSuggestion(
                        rule=Rule(
                            id=_rule_id(dataset, col.name, "not_negative"),
                            name=f"{col.name} must be non-negative",
                            dimension=DQDimension.REASONABILITY,
                            rule_type=RuleType.AGGREGATE,
                            severity=Severity.WARNING,
                            dataset=dataset,
                            column=col.name,
                            check="not_negative",
                            params=NotNegativeParams(),
                        ),
                        confidence="medium",
                        rationale=f"all observed values are >= 0 (min = {col.min_value})",
                    )
                )
        except (ValueError, TypeError):
            pass

    return out
