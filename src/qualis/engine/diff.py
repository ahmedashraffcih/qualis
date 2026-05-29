from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qualis.domain.enums import DQDimension
    from qualis.domain.models import DatasetScore, DimensionScore


@dataclass(frozen=True)
class DimensionDelta:
    """Delta between two snapshots for a single DQ dimension."""

    dimension: DQDimension
    before_score: float | None  # None if dimension wasn't in the before report
    after_score: float | None  # None if dimension isn't in the after report
    delta: float  # after - before (positive = improvement)
    before_checks: str  # "8/10" format
    after_checks: str  # "9/10" format


@dataclass(frozen=True)
class ScoreDiff:
    """Full comparison between two DatasetScore snapshots."""

    dataset: str
    before_aggregate: float
    after_aggregate: float
    aggregate_delta: float
    dimension_deltas: list[DimensionDelta]
    before_violations: int
    after_violations: int


def _checks_str(ds: DimensionScore | None) -> str:
    """Format passed/total as a string, e.g. '8/10'. Returns '—' when absent."""
    if ds is None:
        return "—"
    return f"{ds.passed}/{ds.total_checks}"


def compute_diff(before: DatasetScore, after: DatasetScore) -> ScoreDiff:
    """Compare two DatasetScore snapshots and produce a delta report.

    Parameters
    ----------
    before:
        The earlier ``DatasetScore`` (baseline).
    after:
        The later ``DatasetScore`` (result of the change under evaluation).

    Returns
    -------
    ScoreDiff
        A frozen dataclass containing per-dimension and aggregate deltas.
    """
    before_by_dim: dict[DQDimension, DimensionScore] = {
        ds.dimension: ds for ds in before.dimension_scores
    }
    after_by_dim: dict[DQDimension, DimensionScore] = {
        ds.dimension: ds for ds in after.dimension_scores
    }

    all_dims: set[DQDimension] = set(before_by_dim) | set(after_by_dim)

    deltas: list[DimensionDelta] = []
    for dim in sorted(all_dims, key=lambda d: d.value):
        b = before_by_dim.get(dim)
        a = after_by_dim.get(dim)
        before_score = b.score if b is not None else None
        after_score = a.score if a is not None else None
        # Delta: treat missing side as 0.0 for arithmetic
        delta = (after_score if after_score is not None else 0.0) - (
            before_score if before_score is not None else 0.0
        )
        deltas.append(
            DimensionDelta(
                dimension=dim,
                before_score=before_score,
                after_score=after_score,
                delta=delta,
                before_checks=_checks_str(b),
                after_checks=_checks_str(a),
            )
        )

    return ScoreDiff(
        dataset=after.dataset,
        before_aggregate=before.aggregate_score,
        after_aggregate=after.aggregate_score,
        aggregate_delta=after.aggregate_score - before.aggregate_score,
        dimension_deltas=deltas,
        before_violations=before.total_violations,
        after_violations=after.total_violations,
    )
