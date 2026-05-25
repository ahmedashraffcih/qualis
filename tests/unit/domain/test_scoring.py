from __future__ import annotations

import pytest

from qualis.domain.enums import DQDimension, RuleType, Severity
from qualis.domain.models import CheckResult, Rule
from qualis.domain.params import NotNullParams
from qualis.domain.scoring import compute_dataset_score, compute_dimension_scores

DATASET = "public.orders"


def _make_rule(
    *,
    rule_id: str = "r-001",
    dimension: DQDimension = DQDimension.COMPLETENESS,
) -> Rule:
    return Rule(
        id=rule_id,
        name=f"Test {rule_id}",
        dimension=dimension,
        rule_type=RuleType.ROW_LEVEL,
        severity=Severity.CRITICAL,
        dataset=DATASET,
        column="col",
        check="not_null",
        params=NotNullParams(),
    )


def _make_result(rule: Rule, *, passed: bool) -> CheckResult:
    return CheckResult(
        rule=rule,
        passed=passed,
        violation_count=0 if passed else 1,
        violations=[],
        rows_checked=10,
    )


class TestComputeDimensionScores:
    def test_all_passing_gives_score_1(self) -> None:
        rule1 = _make_rule(rule_id="r-001")
        rule2 = _make_rule(rule_id="r-002")
        results = [_make_result(rule1, passed=True), _make_result(rule2, passed=True)]
        scores = compute_dimension_scores(results, DATASET)
        assert len(scores) == 1
        assert scores[0].score == pytest.approx(1.0)

    def test_partial_failure_gives_score_0_5(self) -> None:
        rule1 = _make_rule(rule_id="r-001")
        rule2 = _make_rule(rule_id="r-002")
        results = [_make_result(rule1, passed=True), _make_result(rule2, passed=False)]
        scores = compute_dimension_scores(results, DATASET)
        assert len(scores) == 1
        assert scores[0].score == pytest.approx(0.5)
        assert scores[0].passed == 1
        assert scores[0].failed == 1

    def test_multiple_dimensions_grouped(self) -> None:
        comp_rule = _make_rule(rule_id="c-001", dimension=DQDimension.COMPLETENESS)
        val_rule = _make_rule(rule_id="v-001", dimension=DQDimension.VALIDITY)
        results = [
            _make_result(comp_rule, passed=True),
            _make_result(val_rule, passed=False),
        ]
        scores = compute_dimension_scores(results, DATASET)
        assert len(scores) == 2
        by_dim = {s.dimension: s for s in scores}
        assert by_dim[DQDimension.COMPLETENESS].score == pytest.approx(1.0)
        assert by_dim[DQDimension.VALIDITY].score == pytest.approx(0.0)

    def test_empty_results_returns_empty_list(self) -> None:
        scores = compute_dimension_scores([], DATASET)
        assert scores == []

    def test_results_sorted_by_dimension(self) -> None:
        rules = [
            _make_rule(rule_id="v-001", dimension=DQDimension.VALIDITY),
            _make_rule(rule_id="c-001", dimension=DQDimension.COMPLETENESS),
            _make_rule(rule_id="u-001", dimension=DQDimension.UNIQUENESS),
        ]
        results = [_make_result(r, passed=True) for r in rules]
        scores = compute_dimension_scores(results, DATASET)
        dimensions = [s.dimension.value for s in scores]
        assert dimensions == sorted(dimensions)


class TestComputeDatasetScore:
    def _dim_score(
        self,
        dimension: DQDimension,
        score: float,
        weight: float = 1.0,
    ) -> object:
        from qualis.domain.models import DimensionScore

        return DimensionScore(
            dimension=dimension,
            dataset=DATASET,
            total_checks=1,
            passed=1 if score == 1.0 else 0,
            failed=0 if score == 1.0 else 1,
            score=score,
            weight=weight,
        )

    def test_weighted_aggregation(self) -> None:
        # 0.9 * 0.6 + 1.0 * 0.4 = 0.54 + 0.40 = 0.94
        from qualis.domain.models import DimensionScore

        dim_scores = [
            DimensionScore(
                dimension=DQDimension.COMPLETENESS,
                dataset=DATASET,
                total_checks=1,
                passed=1,
                failed=0,
                score=0.9,
                weight=1.0,
            ),
            DimensionScore(
                dimension=DQDimension.VALIDITY,
                dataset=DATASET,
                total_checks=1,
                passed=1,
                failed=0,
                score=1.0,
                weight=1.0,
            ),
        ]
        weights = {
            DQDimension.COMPLETENESS: 0.6,
            DQDimension.VALIDITY: 0.4,
        }
        result = compute_dataset_score(dim_scores, weights, DATASET, 0, 0)
        assert result.aggregate_score == pytest.approx(0.94)

    def test_equal_weights_average(self) -> None:
        from qualis.domain.models import DimensionScore

        dim_scores = [
            DimensionScore(
                dimension=DQDimension.COMPLETENESS,
                dataset=DATASET,
                total_checks=1,
                passed=1,
                failed=0,
                score=1.0,
                weight=1.0,
            ),
            DimensionScore(
                dimension=DQDimension.VALIDITY,
                dataset=DATASET,
                total_checks=1,
                passed=0,
                failed=1,
                score=0.0,
                weight=1.0,
            ),
        ]
        result = compute_dataset_score(dim_scores, {}, DATASET, 1, 0)
        # (1.0 + 0.0) / 2 = 0.5
        assert result.aggregate_score == pytest.approx(0.5)

    def test_empty_scores_returns_zero(self) -> None:
        result = compute_dataset_score([], {}, DATASET, 0, 0)
        assert result.aggregate_score == pytest.approx(0.0)
        assert result.dimension_scores == []

    def test_dataset_score_carries_violations(self) -> None:
        from qualis.domain.models import DimensionScore

        dim_scores = [
            DimensionScore(
                dimension=DQDimension.COMPLETENESS,
                dataset=DATASET,
                total_checks=5,
                passed=4,
                failed=1,
                score=0.8,
            )
        ]
        result = compute_dataset_score(dim_scores, {}, DATASET, 3, 2)
        assert result.total_violations == 3
        assert result.critical_violations == 2
