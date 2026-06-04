"""Drift detector — orchestrates comparing live profiles against snapshots."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from qualis.discover.profiler import TableProfile, profile_table
from qualis.discover.snapshot_store import SnapshotStore  # noqa: TC001
from qualis.domain.drift import DriftFinding, compare_snapshots
from qualis.domain.snapshot import ColumnSnapshot, ProfileSnapshot

if TYPE_CHECKING:
    from qualis.domain.models import Rule


def snapshot_from_profile(profile: TableProfile) -> ProfileSnapshot:
    """Capture a TableProfile as an immutable ProfileSnapshot for the table."""
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
        table=profile.table,
        captured_at=ProfileSnapshot.now_iso(),
        row_count=profile.row_count,
        columns=columns,
    )


def _rules_by_table_column(rules: list[Rule]) -> dict[str, dict[str, tuple[str, ...]]]:
    """Group rules into ``{table: {column: (rule_id, ...)}}``."""
    out: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for rule in rules:
        col = rule.column or "*"
        out[rule.dataset][col].append(rule.id)
    return {t: {c: tuple(ids) for c, ids in cols.items()} for t, cols in out.items()}


def detect_drift(
    adapter: object,
    store: SnapshotStore,
    rules: list[Rule],
) -> dict[str, list[DriftFinding]]:
    """Profile each referenced table once and compare against its snapshot.

    Returns a mapping ``table_name -> list of findings``. Tables without
    a snapshot are skipped silently. Each finding includes the tuple of
    affected rule ids drawn from ``rules``.
    """
    table_rules = _rules_by_table_column(rules)
    findings_by_table: dict[str, list[DriftFinding]] = {}
    for table, rules_by_column in table_rules.items():
        if not store.exists(table):
            continue
        baseline = store.load(table)
        current_profile = profile_table(adapter, table)
        current_snapshot = snapshot_from_profile(current_profile)
        findings_by_table[table] = compare_snapshots(
            baseline=baseline,
            current=current_snapshot,
            rules_by_column=rules_by_column,
        )
    return findings_by_table
