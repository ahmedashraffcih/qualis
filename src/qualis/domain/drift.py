"""Drift comparison — compares a current profile against a stored snapshot.

Severity ladder:
    INFO     — within ±5% of baseline; report only
    NOTICE   — within ±15%; track but don't alert
    WARNING  — within ±30%; likely affects rule validity
    CRITICAL — > ±30% drift OR new categorical values appeared

Drift is dimensionless: each finding names the metric, the baseline value,
the current value, the relative change, and a 4-level severity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from qualis.domain.snapshot import ColumnSnapshot, ProfileSnapshot  # noqa: TC001


class DriftSeverity(StrEnum):
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class DriftFinding:
    rule_id: str
    column: str
    metric: str
    baseline: str
    current: str
    relative_change: float | None  # None when the metric is categorical
    severity: DriftSeverity
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
    rule_id: str,
    baseline: ColumnSnapshot,
    current: ColumnSnapshot,
) -> list[DriftFinding]:
    """Yield one finding per drifting metric between baseline and current."""
    findings: list[DriftFinding] = []

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
                    rule_id=rule_id,
                    column=baseline.column,
                    metric=metric,
                    baseline=str(base_v),
                    current=str(cur_v),
                    relative_change=None,
                    severity=DriftSeverity.CRITICAL,
                    note="baseline was zero",
                )
            )
            continue
        severity = _severity_from_change(rel)
        if severity == DriftSeverity.INFO:
            continue  # only surface NOTICE and above
        findings.append(
            DriftFinding(
                rule_id=rule_id,
                column=baseline.column,
                metric=metric,
                baseline=str(base_v),
                current=str(cur_v),
                relative_change=rel,
                severity=severity,
            )
        )

    new_categories = set(current.sample_values) - set(baseline.sample_values)
    if new_categories and baseline.sample_values:
        findings.append(
            DriftFinding(
                rule_id=rule_id,
                column=baseline.column,
                metric="new_categories",
                baseline=", ".join(sorted(baseline.sample_values)),
                current=", ".join(sorted(new_categories)),
                relative_change=None,
                severity=DriftSeverity.CRITICAL,
                note=f"{len(new_categories)} new value(s) not present at acceptance",
            )
        )

    return findings


def compare_snapshots(
    baseline: ProfileSnapshot,
    current: ProfileSnapshot,
) -> list[DriftFinding]:
    """Compare two ProfileSnapshots — match by column name, ignore missing."""
    current_by_name = {c.column: c for c in current.columns}
    findings: list[DriftFinding] = []
    for base_col in baseline.columns:
        cur_col = current_by_name.get(base_col.column)
        if cur_col is None:
            continue
        findings.extend(compare_columns(baseline.rule_id, base_col, cur_col))
    return findings
