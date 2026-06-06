"""Drift comparison — compares a current profile against a stored snapshot.

Severity ladder:
    INFO     — within ±5% of baseline; report only
    NOTICE   — within ±15%; track but don't alert
    WARNING  — within ±30%; likely affects rule validity
    CRITICAL — > ±30% drift OR new categorical values appeared

Drift is dimensionless: each finding names the metric, the baseline value,
the current value, the relative change, and a 4-level severity. Findings
are emitted ONCE per (table, column, metric) regardless of how many
rules reference the column — the affected rule_ids are attached so users
can see which rules' assumptions broke.

Schema changes are drift too (a silently altered table must not pass):
    column_dropped — CRITICAL: a baseline column is missing from the
                     current profile; every rule referencing it is attached
    column_added   — NOTICE: a column not present at snapshot time
    type_changed   — WARNING: the inferred type flipped (likely affects
                     rule validity — e.g. integer → string breaks between)
A rename has no inference in v1 — it reports as one drop + one add.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from qualis.domain.snapshot import ColumnSnapshot, ProfileSnapshot  # noqa: TC001

# Continuous-numeric heuristic: above this distinct-count we treat the
# column as continuous and skip categorical-drift detection (sample-value
# churn on float columns is pure noise, not signal).
_CATEGORICAL_DISTINCT_THRESHOLD = 20


class DriftSeverity(StrEnum):
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class DriftFinding:
    table: str
    column: str
    metric: str
    baseline: str
    current: str
    relative_change: float | None  # None when the metric is categorical
    severity: DriftSeverity
    affected_rules: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


def _severity_from_change(rel: float) -> DriftSeverity:
    abs_rel = abs(rel)
    if abs_rel <= 0.05:
        return DriftSeverity.INFO
    if abs_rel <= 0.15:
        return DriftSeverity.NOTICE
    if abs_rel <= 0.30:
        return DriftSeverity.WARNING
    return DriftSeverity.CRITICAL


def _relative_change(baseline: float, current: float) -> float | None:
    if baseline == 0:
        return None if current == 0 else float("inf")
    return (current - baseline) / baseline


def compare_columns(
    table: str,
    baseline: ColumnSnapshot,
    current: ColumnSnapshot,
    affected_rules: tuple[str, ...] = (),
) -> list[DriftFinding]:
    """Yield one finding per drifting metric between baseline and current."""
    findings: list[DriftFinding] = []

    # Schema-level signal first: a type flip likely invalidates every rule
    # on the column, so it leads the column's findings.
    if baseline.inferred_type != current.inferred_type:
        findings.append(
            DriftFinding(
                table=table,
                column=baseline.column,
                metric="type_changed",
                baseline=baseline.inferred_type,
                current=current.inferred_type,
                relative_change=None,
                severity=DriftSeverity.WARNING,
                affected_rules=affected_rules,
                note="inferred type changed since snapshot",
            )
        )

    for metric, base_v, cur_v in (
        ("null_fraction", baseline.null_fraction, current.null_fraction),
        ("distinct_fraction", baseline.distinct_fraction, current.distinct_fraction),
        ("total_count", float(baseline.total_count), float(current.total_count)),
    ):
        rel = _relative_change(base_v, cur_v)
        if rel is None:
            continue
        if rel == float("inf"):
            findings.append(
                DriftFinding(
                    table=table,
                    column=baseline.column,
                    metric=metric,
                    baseline=str(base_v),
                    current=str(cur_v),
                    relative_change=None,
                    severity=DriftSeverity.CRITICAL,
                    affected_rules=affected_rules,
                    note="baseline was zero",
                )
            )
            continue
        severity = _severity_from_change(rel)
        if severity == DriftSeverity.INFO:
            continue  # only surface NOTICE and above
        findings.append(
            DriftFinding(
                table=table,
                column=baseline.column,
                metric=metric,
                baseline=str(base_v),
                current=str(cur_v),
                relative_change=rel,
                severity=severity,
                affected_rules=affected_rules,
            )
        )

    # Categorical drift — only emit when the column is genuinely categorical
    # (small distinct count). Continuous numerics churn in their sample
    # values between any two runs and would produce spurious CRITICAL
    # findings on every drift execution.
    # Numeric columns are never "categorical" for drift purposes — their
    # sample values churn between runs even when the distribution is stable.
    # Categorical drift only makes sense for string / boolean / date columns
    # with a small distinct count.
    looks_categorical = (
        baseline.distinct_count <= _CATEGORICAL_DISTINCT_THRESHOLD
        and current.distinct_count <= _CATEGORICAL_DISTINCT_THRESHOLD
        and baseline.inferred_type not in {"float", "integer"}
    )
    new_categories = set(current.sample_values) - set(baseline.sample_values)
    if looks_categorical and new_categories and baseline.sample_values:
        findings.append(
            DriftFinding(
                table=table,
                column=baseline.column,
                metric="new_categories",
                baseline=", ".join(sorted(baseline.sample_values)),
                current=", ".join(sorted(new_categories)),
                relative_change=None,
                severity=DriftSeverity.CRITICAL,
                affected_rules=affected_rules,
                note=f"{len(new_categories)} new value(s) not present at snapshot time",
            )
        )

    return findings


def compare_snapshots(
    baseline: ProfileSnapshot,
    current: ProfileSnapshot,
    rules_by_column: dict[str, tuple[str, ...]] | None = None,
) -> list[DriftFinding]:
    """Compare two ProfileSnapshots — one finding per drifting (column, metric).

    ``rules_by_column`` maps column name to the tuple of rule ids that
    reference it; attached to each finding so users see which rules are
    invalidated by the drift. Defaults to empty (the caller may not
    have rule context).
    """
    rules_by_column = rules_by_column or {}
    current_by_name = {c.column: c for c in current.columns}
    findings: list[DriftFinding] = []
    for base_col in baseline.columns:
        cur_col = current_by_name.get(base_col.column)
        if cur_col is None:
            # A disappeared column is the loudest schema drift there is —
            # never skip it silently (that was the pre-v0.6 behaviour).
            findings.append(
                DriftFinding(
                    table=baseline.table,
                    column=base_col.column,
                    metric="column_dropped",
                    baseline=base_col.inferred_type,
                    current="absent",
                    relative_change=None,
                    severity=DriftSeverity.CRITICAL,
                    affected_rules=rules_by_column.get(base_col.column, ()),
                    note="column missing from current profile",
                )
            )
            continue
        findings.extend(
            compare_columns(
                table=baseline.table,
                baseline=base_col,
                current=cur_col,
                affected_rules=rules_by_column.get(base_col.column, ()),
            )
        )

    # Second pass: columns present now that weren't at snapshot time.
    baseline_names = {c.column for c in baseline.columns}
    for cur_col in current.columns:
        if cur_col.column in baseline_names:
            continue
        findings.append(
            DriftFinding(
                table=baseline.table,
                column=cur_col.column,
                metric="column_added",
                baseline="absent",
                current=cur_col.inferred_type,
                relative_change=None,
                severity=DriftSeverity.NOTICE,
                affected_rules=rules_by_column.get(cur_col.column, ()),
                note="column not present at snapshot time",
            )
        )
    return findings
