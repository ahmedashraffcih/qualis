from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from qualis.domain.models import DatasetScore, DimensionScore

if TYPE_CHECKING:
    from qualis.domain.enums import DQDimension
    from qualis.domain.models import CheckResult


def compute_dimension_scores(
    results: list[CheckResult],
    dataset: str,
) -> list[DimensionScore]:
    """Group *results* by dimension and compute per-dimension scores.

    Returns a list of ``DimensionScore`` objects sorted by dimension value,
    one entry per dimension found in *results*.  An empty *results* list
    returns an empty list.
    """
    if not results:
        return []

    buckets: dict[DQDimension, list[CheckResult]] = defaultdict(list)
    for result in results:
        # Skipped checks (unexecuted stubs like `sql` / `custom`) must NOT
        # contribute to the dimension score — otherwise an unrun check
        # would silently boost or drag the aggregate.
        if result.skipped:
            continue
        buckets[result.rule.dimension].append(result)

    dimension_scores: list[DimensionScore] = []
    for dimension in sorted(buckets, key=lambda d: d.value):
        bucket = buckets[dimension]
        total = len(bucket)
        passed = sum(1 for r in bucket if r.passed)
        failed = total - passed
        score = passed / total if total else 0.0
        dimension_scores.append(
            DimensionScore(
                dimension=dimension,
                dataset=dataset,
                total_checks=total,
                passed=passed,
                failed=failed,
                score=score,
            )
        )

    return dimension_scores


def compute_dataset_score(
    dimension_scores: list[DimensionScore],
    weights: dict[DQDimension, float],
    dataset: str,
    total_violations: int,
    critical_violations: int,
) -> DatasetScore:
    """Compute a weighted aggregate score across *dimension_scores*.

    Each dimension's contribution is ``score * weight`` where the weight is
    looked up from *weights* (defaulting to ``dim.weight`` if not present).
    Returns 0.0 aggregate when *dimension_scores* is empty.
    """
    if not dimension_scores:
        return DatasetScore(
            dataset=dataset,
            dimension_scores=dimension_scores,
            aggregate_score=0.0,
            total_violations=total_violations,
            critical_violations=critical_violations,
        )

    weighted_sum = 0.0
    weight_total = 0.0
    for dim_score in dimension_scores:
        w = weights.get(dim_score.dimension, dim_score.weight)
        weighted_sum += dim_score.score * w
        weight_total += w

    aggregate = weighted_sum / weight_total if weight_total else 0.0

    return DatasetScore(
        dataset=dataset,
        dimension_scores=dimension_scores,
        aggregate_score=aggregate,
        total_violations=total_violations,
        critical_violations=critical_violations,
    )
