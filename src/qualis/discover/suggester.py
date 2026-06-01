"""Rule suggestion engine — deterministic heuristics over a table profile.

Generates DQ rule suggestions using statistical observations:
- not_null when 0 nulls observed
- unique when column is likely an ID
- in_set when low-cardinality (<= 10 distinct)
- between when numeric/date with observed min/max
- not_negative when numeric with min >= 0

The suggester optionally consults a DatasetContext to skip declared
sentinels (e.g., 0 = "unknown" in some tables) and exceptions. Without
context, behaviour matches v0.2.x — useful for backwards compatibility
but the practitioner warning applies: ungrounded rules can be
"confidently wrong at scale."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from qualis.discover.evidence_builder import build_profile_evidence
from qualis.domain.context import EMPTY_CONTEXT, DatasetContext
from qualis.domain.enums import DQDimension, RuleType, Severity
from qualis.domain.evidence import SuggestionEvidence
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
    """One rule suggestion with its supporting evidence.

    The evidence is the source of truth — ``rationale`` is a derived
    property that returns ``evidence.heuristic_reason`` for backwards
    compatibility with existing callers.
    """

    rule: Rule
    confidence: Confidence
    evidence: SuggestionEvidence

    @property
    def rationale(self) -> str:
        return self.evidence.heuristic_reason


def _rule_id(dataset: str, column: str | None, check: str) -> str:
    col_part = column or "table"
    return f"DQ-{check.upper()}-{dataset}-{col_part}"


def _evidence(
    col: ColumnProfile,
    heuristic: str,
    reason: str,
    sentinels_consulted: list[str] | None = None,
    exceptions_consulted: list[str] | None = None,
) -> SuggestionEvidence:
    return SuggestionEvidence(
        profile=build_profile_evidence(col, top_values=[]),
        heuristic=heuristic,
        heuristic_reason=reason,
        sentinels_consulted=sentinels_consulted or [],
        exceptions_consulted=exceptions_consulted or [],
    )


def suggest_rules(
    profile: TableProfile,
    context: DatasetContext | None = None,
) -> list[RuleSuggestion]:
    """Generate deterministic rule suggestions from a table profile.

    ``context`` (optional) holds user-declared sentinels and exceptions
    that the suggester should respect. When absent, the suggester
    behaves exactly as in v0.2.x — useful for backwards compatibility
    but reviewers should treat the output as ungrounded.
    """
    ctx = context if context is not None else EMPTY_CONTEXT
    suggestions: list[RuleSuggestion] = []
    for col in profile.columns:
        suggestions.extend(_suggest_for_column(profile.table, col, ctx))
    return suggestions


def _suggest_for_column(
    dataset: str,
    col: ColumnProfile,
    ctx: DatasetContext,
) -> list[RuleSuggestion]:
    out: list[RuleSuggestion] = []
    column_ctx = ctx.get_column(col.name)
    sentinel_values = {s.value for s in column_ctx.sentinels}

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
                evidence=_evidence(
                    col, "not_null", f"0 nulls observed in {col.total_count} rows",
                ),
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
                evidence=_evidence(
                    col, "unique",
                    f"distinct/{non_null} non-null rows = {col.distinct_fraction:.0%}; "
                    "name suggests identifier",
                ),
            )
        )

    if (
        col.inferred_type == "string"
        and 0 < col.distinct_count <= _LOW_CARDINALITY_THRESHOLD
        and col.sample_values
    ):
        # Skip declared sentinels — they are valid placeholders the data
        # itself cannot resolve. The practitioner case: 0 = "unknown" in
        # some tables, invalid in others. Codifying it as "valid" via
        # in_set ships the failure mode at scale.
        filtered_values = [v for v in col.sample_values if v not in sentinel_values]
        consulted = sorted(sentinel_values & set(col.sample_values))
        if filtered_values:
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
                        params=InSetParams(values=filtered_values),
                    ),
                    # MEDIUM confidence: we know only what we observed, not
                    # the authoritative valid domain. New codes added next
                    # week would break this rule. Reviewer must verify
                    # against source of truth (data catalog, reference data,
                    # domain owner) before accepting.
                    confidence="medium",
                    evidence=_evidence(
                        col, "in_set",
                        f"{col.distinct_count} distinct values observed in profiled data — "
                        "verify against the authoritative valid domain before accepting",
                        sentinels_consulted=consulted,
                    ),
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
                evidence=_evidence(
                    col, "between",
                    f"observed range [{col.min_value}, {col.max_value}]",
                ),
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
                        evidence=_evidence(
                            col, "not_negative",
                            f"all observed values are >= 0 (min = {col.min_value})",
                        ),
                    )
                )
        except (ValueError, TypeError):
            pass

    return out
