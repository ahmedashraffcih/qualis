"""Evidence captured at rule-suggestion time.

The practitioner critique: a one-line rationale ("4 distinct values
observed") is not enough evidence for a reviewer to sign off on a
production rule. The reviewer needs the underlying profile numbers,
samples, what was consulted from context, and a violation preview.

This module holds that data as immutable structures. The suggester
populates them; the writer persists them to a sidecar YAML; the CLI
renders them in the review screen.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProfileEvidence:
    """Statistical snapshot of the column that drove a suggestion.

    Stored verbatim so the reviewer can see exactly what the suggester
    saw at the moment it decided.
    """

    total_rows: int
    null_count: int
    null_fraction: float
    distinct_count: int
    distinct_fraction: float
    min_value: str | None
    max_value: str | None
    top_values: list[tuple[str, int]]  # (value, count), descending; up to 10


@dataclass(frozen=True)
class SuggestionEvidence:
    """Full evidence trail for one rule suggestion.

    Carries the profile snapshot, the heuristic that fired, what was
    consulted from declared context, and (optionally) the estimated
    violation rate if the rule were applied to the profiled data today.
    """

    profile: ProfileEvidence
    heuristic: str  # e.g., "not_null", "in_set", "between"
    heuristic_reason: str  # short human-readable summary
    sentinels_consulted: list[str] = field(default_factory=list)
    exceptions_consulted: list[str] = field(default_factory=list)
    estimated_violation_rate: float | None = None  # 0.0-1.0; None if not computed
