from __future__ import annotations

from qualis.domain.enums import DQDimension
from qualis.domain.models import DatasetScore, DimensionScore
from qualis.engine.diff import compute_diff


def _dim(dimension: DQDimension, score: float, passed: int, total: int) -> DimensionScore:
    return DimensionScore(
        dimension=dimension,
        dataset="accidents",
        total_checks=total,
        passed=passed,
        failed=total - passed,
        score=score,
    )


def _dataset(
    dims: list[DimensionScore], aggregate: float, violations: int = 0,
) -> DatasetScore:
    return DatasetScore(
        dataset="accidents",
        dimension_scores=dims,
        aggregate_score=aggregate,
        total_violations=violations,
        critical_violations=0,
    )


class TestComputeDiff:
    def test_identical_scores_zero_delta(self) -> None:
        dims = [_dim(DQDimension.COMPLETENESS, 0.8, 8, 10)]
        before = _dataset(dims, 0.8)
        after = _dataset(dims, 0.8)
        result = compute_diff(before, after)
        assert result.aggregate_delta == 0.0
        assert result.dimension_deltas[0].delta == 0.0

    def test_improvement_positive_delta(self) -> None:
        before = _dataset([_dim(DQDimension.COMPLETENESS, 0.5, 5, 10)], 0.5)
        after = _dataset([_dim(DQDimension.COMPLETENESS, 0.9, 9, 10)], 0.9)
        result = compute_diff(before, after)
        assert result.aggregate_delta == 0.4
        assert result.dimension_deltas[0].delta == 0.4
        assert result.dimension_deltas[0].before_checks == "5/10"
        assert result.dimension_deltas[0].after_checks == "9/10"

    def test_regression_negative_delta(self) -> None:
        before = _dataset([_dim(DQDimension.VALIDITY, 0.9, 9, 10)], 0.9)
        after = _dataset([_dim(DQDimension.VALIDITY, 0.6, 6, 10)], 0.6)
        result = compute_diff(before, after)
        assert result.aggregate_delta < 0
        assert result.dimension_deltas[0].delta < 0

    def test_new_dimension_in_after(self) -> None:
        before = _dataset([_dim(DQDimension.COMPLETENESS, 1.0, 1, 1)], 1.0)
        after = _dataset(
            [
                _dim(DQDimension.COMPLETENESS, 1.0, 1, 1),
                _dim(DQDimension.VALIDITY, 0.5, 1, 2),
            ],
            0.75,
        )
        result = compute_diff(before, after)
        validity = next(
            d for d in result.dimension_deltas if d.dimension == DQDimension.VALIDITY
        )
        assert validity.before_score is None
        assert validity.after_score == 0.5
        assert validity.before_checks == "—"

    def test_removed_dimension_in_after(self) -> None:
        before = _dataset(
            [
                _dim(DQDimension.COMPLETENESS, 1.0, 1, 1),
                _dim(DQDimension.UNIQUENESS, 1.0, 1, 1),
            ],
            1.0,
        )
        after = _dataset([_dim(DQDimension.COMPLETENESS, 1.0, 1, 1)], 1.0)
        result = compute_diff(before, after)
        uniqueness = next(
            d for d in result.dimension_deltas if d.dimension == DQDimension.UNIQUENESS
        )
        assert uniqueness.before_score == 1.0
        assert uniqueness.after_score is None
        assert uniqueness.after_checks == "—"

    def test_violation_counts_carried(self) -> None:
        before = _dataset([_dim(DQDimension.COMPLETENESS, 0.5, 1, 2)], 0.5, violations=5)
        after = _dataset([_dim(DQDimension.COMPLETENESS, 1.0, 2, 2)], 1.0, violations=0)
        result = compute_diff(before, after)
        assert result.before_violations == 5
        assert result.after_violations == 0
