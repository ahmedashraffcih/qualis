from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qualis.domain.enums import RuleStatus

if TYPE_CHECKING:
    from qualis.domain.enums import DQDimension, RuleType, Severity
    from qualis.domain.params import CheckParams


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    dimension: DQDimension
    rule_type: RuleType
    severity: Severity
    dataset: str
    column: str | None
    check: str
    params: CheckParams
    # Optional -- defaults preserve backwards compatibility
    condition: str | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    # New in v0.3.0: lifecycle, lineage, programme metadata
    status: RuleStatus = RuleStatus.ACTIVE
    version: int | None = None
    supersedes: str | None = None
    deprecated_at: str | None = None
    approved_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Violation:
    rule: Rule
    record_id: str | None
    actual_value: Any
    expected: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckResult:
    rule: Rule
    passed: bool
    violation_count: int
    violations: list[Violation]
    rows_checked: int
    # Skipped checks did NOT execute (e.g. stubbed `sql` / `custom` types
    # that require an out-of-band implementation). They are excluded from
    # aggregate score so an unrun check cannot silently report 100/100.
    skipped: bool = False
    skip_reason: str = ""


@dataclass(frozen=True)
class DimensionScore:
    dimension: DQDimension
    dataset: str
    total_checks: int
    passed: int
    failed: int
    score: float
    weight: float = 1.0


@dataclass(frozen=True)
class DatasetScore:
    dataset: str
    dimension_scores: list[DimensionScore]
    aggregate_score: float
    total_violations: int
    critical_violations: int
