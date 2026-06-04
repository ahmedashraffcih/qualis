from __future__ import annotations

import pytest

from qualis.domain.drift import (
    DriftSeverity,
    compare_columns,
    compare_snapshots,
)
from qualis.domain.snapshot import ColumnSnapshot, ProfileSnapshot


def make_col(
    *,
    name: str = "email",
    null_fraction: float = 0.0,
    distinct_fraction: float = 1.0,
    total_count: int = 1000,
    sample_values: tuple[str, ...] = (),
) -> ColumnSnapshot:
    return ColumnSnapshot(
        column=name,
        inferred_type="string",
        total_count=total_count,
        null_count=int(total_count * null_fraction),
        null_fraction=null_fraction,
        distinct_count=int(total_count * distinct_fraction),
        distinct_fraction=distinct_fraction,
        min_value=None,
        max_value=None,
        sample_values=sample_values,
    )


def test_no_drift_when_identical() -> None:
    base = make_col()
    findings = compare_columns("R1", base, base)
    assert findings == []


def test_small_change_suppressed_below_notice() -> None:
    base = make_col(null_fraction=0.10)
    current = make_col(null_fraction=0.104)  # +4%
    findings = compare_columns("R1", base, current)
    assert findings == []


def test_notice_severity_on_15_percent_change() -> None:
    base = make_col(null_fraction=0.10)
    current = make_col(null_fraction=0.115)  # +15%
    findings = [f for f in compare_columns("R1", base, current) if f.metric == "null_fraction"]
    assert len(findings) == 1
    assert findings[0].severity == DriftSeverity.NOTICE


def test_warning_severity_on_30_percent_change() -> None:
    base = make_col(null_fraction=0.10)
    current = make_col(null_fraction=0.13)  # +30%
    findings = [f for f in compare_columns("R1", base, current) if f.metric == "null_fraction"]
    assert findings[0].severity == DriftSeverity.WARNING


def test_critical_severity_on_large_change() -> None:
    base = make_col(null_fraction=0.10)
    current = make_col(null_fraction=0.50)  # +400%
    findings = [f for f in compare_columns("R1", base, current) if f.metric == "null_fraction"]
    assert findings[0].severity == DriftSeverity.CRITICAL


def test_zero_baseline_with_nonzero_current_is_critical() -> None:
    base = make_col(null_fraction=0.0)
    current = make_col(null_fraction=0.01)
    findings = [f for f in compare_columns("R1", base, current) if f.metric == "null_fraction"]
    assert findings[0].severity == DriftSeverity.CRITICAL
    assert findings[0].note == "baseline was zero"


def test_new_categorical_value_is_critical() -> None:
    base = make_col(sample_values=("active", "inactive"))
    current = make_col(sample_values=("active", "inactive", "suspended"))
    findings = [f for f in compare_columns("R1", base, current) if f.metric == "new_categories"]
    assert len(findings) == 1
    assert findings[0].severity == DriftSeverity.CRITICAL
    assert "suspended" in findings[0].current


def test_compare_snapshots_skips_columns_missing_in_current() -> None:
    base = ProfileSnapshot(
        rule_id="R1",
        dataset="ds",
        table="t",
        captured_at="2026-01-01T00:00:00+00:00",
        row_count=100,
        columns=(make_col(name="email"), make_col(name="phone")),
    )
    current = ProfileSnapshot(
        rule_id="R1",
        dataset="ds",
        table="t",
        captured_at="2026-06-01T00:00:00+00:00",
        row_count=100,
        columns=(make_col(name="email"),),  # phone gone
    )
    findings = compare_snapshots(base, current)
    assert findings == []


def test_snapshot_is_frozen() -> None:
    snap = ProfileSnapshot(
        rule_id="R1",
        dataset="ds",
        table="t",
        captured_at="2026-01-01T00:00:00+00:00",
        row_count=100,
    )
    from dataclasses import FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        snap.row_count = 200  # type: ignore[misc]
