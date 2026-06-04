"""ProfileSnapshot — a frozen-in-time view of a table's column statistics.

Captured per-table (NOT per-rule — that caused N-times duplicate drift
findings when N rules referenced the same table). The drift engine
compares the current profile against this baseline and attributes
findings to all rules that reference the affected column.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class ColumnSnapshot:
    """Frozen statistics for one column at snapshot time."""

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
    """A snapshot of a table profile — one per table, not per rule."""

    table: str
    captured_at: str  # ISO 8601 UTC
    row_count: int
    columns: tuple[ColumnSnapshot, ...] = field(default_factory=tuple)

    @staticmethod
    def now_iso() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")
