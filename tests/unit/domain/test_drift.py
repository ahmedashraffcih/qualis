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
    inferred_type: str = "string",
    null_fraction: float = 0.0,
    distinct_fraction: float = 1.0,
    total_count: int = 1000,
    distinct_count: int | None = None,
    sample_values: tuple[str, ...] = (),
) -> ColumnSnapshot:
    return ColumnSnapshot(
        column=name,
        inferred_type=inferred_type,
        total_count=total_count,
        null_count=int(total_count * null_fraction),
        null_fraction=null_fraction,
        distinct_count=distinct_count if distinct_count is not None
            else int(total_count * distinct_fraction),
        distinct_fraction=distinct_fraction,
        min_value=None,
        max_value=None,
        sample_values=sample_values,
    )


def test_no_drift_when_identical() -> None:
    base = make_col()
    findings = compare_columns("t", base, base)
    assert findings == []


def test_small_change_suppressed_below_notice() -> None:
    base = make_col(null_fraction=0.10)
    current = make_col(null_fraction=0.104)  # +4%
    findings = compare_columns("t", base, current)
    assert findings == []


def test_notice_severity_on_15_percent_change() -> None:
    base = make_col(null_fraction=0.10)
    current = make_col(null_fraction=0.115)  # +15%
    findings = [f for f in compare_columns("t", base, current) if f.metric == "null_fraction"]
    assert len(findings) == 1
    assert findings[0].severity == DriftSeverity.NOTICE


def test_warning_severity_on_30_percent_change() -> None:
    base = make_col(null_fraction=0.10)
    current = make_col(null_fraction=0.13)  # +30%
    findings = [f for f in compare_columns("t", base, current) if f.metric == "null_fraction"]
    assert findings[0].severity == DriftSeverity.WARNING


def test_critical_severity_on_large_change() -> None:
    base = make_col(null_fraction=0.10)
    current = make_col(null_fraction=0.50)
    findings = [f for f in compare_columns("t", base, current) if f.metric == "null_fraction"]
    assert findings[0].severity == DriftSeverity.CRITICAL


def test_zero_baseline_with_nonzero_current_is_critical() -> None:
    base = make_col(null_fraction=0.0)
    current = make_col(null_fraction=0.01)
    findings = [f for f in compare_columns("t", base, current) if f.metric == "null_fraction"]
    assert findings[0].severity == DriftSeverity.CRITICAL
    assert findings[0].note == "baseline was zero"


def test_new_categorical_value_on_categorical_column_is_critical() -> None:
    base = make_col(
        inferred_type="string",
        distinct_count=2,
        sample_values=("active", "inactive"),
    )
    current = make_col(
        inferred_type="string",
        distinct_count=3,
        sample_values=("active", "inactive", "suspended"),
    )
    findings = [f for f in compare_columns("t", base, current) if f.metric == "new_categories"]
    assert len(findings) == 1
    assert findings[0].severity == DriftSeverity.CRITICAL
    assert "suspended" in findings[0].current


def test_new_categories_suppressed_on_continuous_numerics() -> None:
    """Regression: float columns with many distinct values must not emit
    spurious new_categories findings — random sample churn is not drift."""
    base = make_col(
        inferred_type="float",
        distinct_count=485,
        sample_values=("100", "250", "500", "75"),
    )
    current = make_col(
        inferred_type="float",
        distinct_count=490,
        sample_values=("100", "200", "300", "175"),  # different sample
    )
    findings = [f for f in compare_columns("t", base, current) if f.metric == "new_categories"]
    assert findings == []


def test_new_categories_suppressed_above_categorical_threshold() -> None:
    """A string column with hundreds of distinct values is functionally
    continuous (e.g. free-text). Don't emit new_categories noise."""
    base = make_col(
        inferred_type="string",
        distinct_count=50,
        sample_values=("a", "b", "c"),
    )
    current = make_col(
        inferred_type="string",
        distinct_count=55,
        sample_values=("a", "b", "c", "d"),
    )
    findings = [f for f in compare_columns("t", base, current) if f.metric == "new_categories"]
    assert findings == []


def test_findings_carry_affected_rules() -> None:
    base = make_col(null_fraction=0.10)
    current = make_col(null_fraction=0.50)
    findings = compare_columns(
        "orders", base, current, affected_rules=("DQ-001", "DQ-002")
    )
    assert findings[0].affected_rules == ("DQ-001", "DQ-002")


def make_snapshot(*cols: ColumnSnapshot, table: str = "t") -> ProfileSnapshot:
    return ProfileSnapshot(
        table=table,
        captured_at="2026-01-01T00:00:00+00:00",
        row_count=100,
        columns=cols,
    )


def test_dropped_column_is_critical_finding() -> None:
    """Regression for the silent skip: a column missing from the current
    profile used to be dropped from the diff without a trace."""
    base = make_snapshot(make_col(name="email"), make_col(name="phone"))
    current = make_snapshot(make_col(name="email"))
    findings = compare_snapshots(base, current)
    assert len(findings) == 1
    f = findings[0]
    assert f.metric == "column_dropped"
    assert f.column == "phone"
    assert f.severity == DriftSeverity.CRITICAL
    assert f.relative_change is None
    assert f.current == "absent"


def test_added_column_is_notice_finding() -> None:
    base = make_snapshot(make_col(name="email"))
    current = make_snapshot(make_col(name="email"), make_col(name="loyalty_tier"))
    findings = compare_snapshots(base, current)
    assert len(findings) == 1
    f = findings[0]
    assert f.metric == "column_added"
    assert f.column == "loyalty_tier"
    assert f.severity == DriftSeverity.NOTICE
    assert f.relative_change is None
    assert f.baseline == "absent"


def test_type_change_is_warning_finding() -> None:
    base = make_col(name="zip", inferred_type="integer")
    current = make_col(name="zip", inferred_type="string")
    findings = [f for f in compare_columns("t", base, current) if f.metric == "type_changed"]
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == DriftSeverity.WARNING
    assert f.baseline == "integer"
    assert f.current == "string"
    assert f.relative_change is None


def test_type_change_surfaces_through_compare_snapshots() -> None:
    base = make_snapshot(make_col(name="zip", inferred_type="integer"))
    current = make_snapshot(make_col(name="zip", inferred_type="string"))
    findings = [f for f in compare_snapshots(base, current) if f.metric == "type_changed"]
    assert len(findings) == 1


def test_dropped_column_carries_affected_rules() -> None:
    base = make_snapshot(make_col(name="phone"))
    current = make_snapshot()
    findings = compare_snapshots(base, current, rules_by_column={"phone": ("DQ-007",)})
    assert findings[0].metric == "column_dropped"
    assert findings[0].affected_rules == ("DQ-007",)


def test_empty_current_reports_all_columns_dropped() -> None:
    base = make_snapshot(make_col(name="a"), make_col(name="b"))
    current = make_snapshot()
    findings = compare_snapshots(base, current)
    assert [f.column for f in findings] == ["a", "b"]
    assert all(f.metric == "column_dropped" for f in findings)


def test_empty_baseline_reports_all_columns_added() -> None:
    base = make_snapshot()
    current = make_snapshot(make_col(name="a"), make_col(name="b"))
    findings = compare_snapshots(base, current)
    assert [f.column for f in findings] == ["a", "b"]
    assert all(f.metric == "column_added" for f in findings)


def test_rename_reports_one_drop_and_one_add() -> None:
    """No rename inference in v1: a rename is reported as drop + add."""
    base = make_snapshot(make_col(name="phone"))
    current = make_snapshot(make_col(name="phone_number"))
    findings = compare_snapshots(base, current)
    metrics = {f.metric: f.column for f in findings}
    assert metrics == {"column_dropped": "phone", "column_added": "phone_number"}


def test_identical_schemas_produce_no_schema_findings() -> None:
    base = make_snapshot(make_col(name="email"), make_col(name="phone"))
    findings = compare_snapshots(base, base)
    assert findings == []


def test_snapshot_is_frozen() -> None:
    snap = ProfileSnapshot(
        table="t",
        captured_at="2026-01-01T00:00:00+00:00",
        row_count=100,
    )
    from dataclasses import FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        snap.row_count = 200  # type: ignore[misc]
