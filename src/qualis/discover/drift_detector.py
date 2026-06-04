"""Drift detector — orchestrates comparing live profiles against snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qualis.discover.profiler import TableProfile, profile_table
from qualis.discover.snapshot_store import SnapshotStore  # noqa: TC001
from qualis.domain.drift import DriftFinding, compare_snapshots
from qualis.domain.snapshot import ColumnSnapshot, ProfileSnapshot

if TYPE_CHECKING:
    from qualis.domain.models import Rule


def snapshot_from_profile(rule_id: str, dataset: str, profile: TableProfile) -> ProfileSnapshot:
    """Capture a TableProfile as an immutable ProfileSnapshot for a rule."""
    columns = tuple(
        ColumnSnapshot(
            column=col.name,
            inferred_type=col.inferred_type,
            total_count=col.total_count,
            null_count=col.null_count,
            null_fraction=col.null_fraction,
            distinct_count=col.distinct_count,
            distinct_fraction=col.distinct_fraction,
            min_value=col.min_value,
            max_value=col.max_value,
            sample_values=tuple(col.sample_values),
        )
        for col in profile.columns
    )
    return ProfileSnapshot(
        rule_id=rule_id,
        dataset=dataset,
        table=profile.table,
        captured_at=ProfileSnapshot.now_iso(),
        row_count=profile.row_count,
        columns=columns,
    )


def detect_drift(
    adapter: object,
    store: SnapshotStore,
    rules: list[Rule],
) -> dict[str, list[DriftFinding]]:
    """Profile each rule's table in the live database, compare to its snapshot.

    Returns a mapping rule_id -> list of findings (empty when no drift).
    Rules without a snapshot are skipped silently.
    """
    findings_by_rule: dict[str, list[DriftFinding]] = {}
    for rule in rules:
        if not store.exists(rule.id):
            continue
        baseline = store.load(rule.id)
        current_profile = profile_table(adapter, baseline.table)
        current_snapshot = snapshot_from_profile(
            rule_id=rule.id,
            dataset=baseline.dataset,
            profile=current_profile,
        )
        findings_by_rule[rule.id] = compare_snapshots(baseline, current_snapshot)
    return findings_by_rule
