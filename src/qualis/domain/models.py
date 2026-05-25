from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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
    condition: str | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)


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
