"""ProfileSnapshot — a frozen-in-time view of a column's statistics.

Captured at rule-acceptance and stored as JSON; the drift engine compares
the current profile against this baseline to detect data shifts that
invalidate rule assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class ColumnSnapshot:
    """Frozen statistics for one column at acceptance time."""

    column: str
    inferred_type: str
    total_count: int
    null_count: int
    null_fraction: float
    distinct_count: int
    distinct_fraction: float
    min_value: str | None
    max_value: str | None
    sample_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProfileSnapshot:
    """A snapshot of a table profile taken when a rule was accepted."""

    rule_id: str
    dataset: str
    table: str
    captured_at: str  # ISO 8601 UTC
    row_count: int
    columns: tuple[ColumnSnapshot, ...] = field(default_factory=tuple)

    @staticmethod
    def now_iso() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")
