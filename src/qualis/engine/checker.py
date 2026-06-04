from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from qualis.domain.enums import DQDimension, Severity
from qualis.domain.rule_engine import RuleEngine
from qualis.domain.scoring import compute_dataset_score, compute_dimension_scores

if TYPE_CHECKING:
    from qualis.domain.models import CheckResult, DatasetScore, Rule


class CheckRunner:
    """Orchestrates rule evaluation, optional redaction, and scoring.

    Parameters
    ----------
    adapter:
        Any object that satisfies ``DatabasePort`` — passed through to
        ``RuleEngine`` without importing from the ports layer.
    rules:
        The list of ``Rule`` objects to evaluate.
    weights:
        Per-dimension weight overrides for the aggregate score calculation.
    schema:
        Optional default schema forwarded to ``RuleEngine``.
    redact:
        When ``True``, replace ``actual_value`` on every ``Violation`` with
        ``"[REDACTED]"`` before the caller sees the results.
    """

    def __init__(
        self,
        adapter: Any,
        rules: list[Rule],
        weights: dict[DQDimension, float],
        schema: str = "",
        redact: bool = False,
        sample_rows: int | None = None,
    ) -> None:
        self._engine = RuleEngine(adapter, schema, sample_rows=sample_rows)
        self._rules = rules
        self._weights = weights
        self._redact = redact

    def run(self) -> DatasetScore:
        """Evaluate all rules and return an aggregated ``DatasetScore``."""
        score, _ = self.run_detailed()
        return score

    def run_detailed(self) -> tuple[DatasetScore, list[CheckResult]]:
        """Evaluate all rules and return both the score and individual results.

        Returns
        -------
        tuple[DatasetScore, list[CheckResult]]
            A 2-tuple of ``(DatasetScore, list[CheckResult])`` so callers that
            need per-rule detail (e.g. the HTML report drilldown) can access it
            without re-running the engine.
        """
        results = self._engine.evaluate_all(self._rules)

        if self._redact:
            results = [self._redact_result(r) for r in results]

        datasets = {r.rule.dataset for r in results}
        dataset = next(iter(datasets)) if datasets else "unknown"

        total_violations = sum(r.violation_count for r in results)
        critical_violations = sum(
            r.violation_count
            for r in results
            if r.rule.severity == Severity.CRITICAL
        )

        dim_scores = compute_dimension_scores(results, dataset)
        score = compute_dataset_score(
            dim_scores,
            self._weights,
            dataset,
            total_violations=total_violations,
            critical_violations=critical_violations,
        )
        return score, results

    @staticmethod
    def _redact_result(result: CheckResult) -> CheckResult:
        """Return *result* with every sampled violation's actual_value redacted.

        Rebuilds the frozen ``Violation`` / ``CheckResult`` instances via
        ``dataclasses.replace`` — cheap now that ``violations`` is a bounded
        sample (see ``MAX_SAMPLE_VIOLATIONS``). Results without sampled
        violations are returned unchanged.
        """
        if not result.violations:
            return result
        redacted = [
            replace(v, actual_value="[REDACTED]") for v in result.violations
        ]
        return replace(result, violations=redacted)
